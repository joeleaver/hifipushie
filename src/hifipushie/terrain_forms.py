"""Forms cut into or stood on the ground: canyons (into a plateau, through horizontal strata), mesas, river water and
fords. A canyon kind needs these: ridges raised out of low ground made V-trenches with a hump for a rim.

canyons: {name: {"river": river, "rim": m, "width": m rim to rim, "floor": m,
                 "strata": {"bands": 3, "cliff": deg, "talus": m}}}
  The river gives the path and the floor's heights; the plateau stands at "rim" (default world.base). The walls climb
  through horizontal strata: each band a cliff (hard rock, stands) over a ledge (soft rock, lies back), with talus at
  the foot. Band elevations are the same all along the canyon, as in real ones; the ledges' slope is solved so the
  walls reach the rim at the asked width.
mesas: {name: {"at", "top": m, "radius": m, "cliff": deg, "talus": share of the height}}
fords: {name: {"on": "river@0.5", "width": m, "depth": m}}: a shallow, wide crossing routes may use.
Rivers carry water ("water": width m, default from the floor) that routes cross only at fords (or say they'd need a
bridge).
"""

from __future__ import annotations

import math

import numpy as np
from scipy import ndimage
from scipy.spatial import cKDTree

from . import noise
from .terrain import smoothstep

TALUS = math.radians(34)


def canyon_rivers(spec) -> set:
    return {c["river"] for c in (spec.get("canyons") or {}).values()}


def carve(T):
    T.canyons = {}
    for name, c in (T.spec.get("canyons") or {}).items():
        _canyon(T, name, c)
    for name, m in (T.spec.get("mesas") or {}).items():
        _mesa(T, name, m)


def _strata(T, lo, rim, st, width_half, floor_half):
    """Absolute-elevation strata between lo and rim: (z grid, cot of the slope at each z), talus height, and the
    ledge slope solved so the widest (deepest) section reaches the rim at width_half."""
    n = int(st.get("bands", 3))
    cliff = math.radians(st.get("cliff", 78))
    depth = max(rim - lo, 1.0)
    talus_h = float(st.get("talus", 0.15 * depth))
    z = np.linspace(lo, rim, 1024)
    u = (z - (lo + talus_h)) / max(depth - talus_h, 1e-6)
    frac = (u * n) % 1.0
    is_cliff = (frac > 0.25) & (u >= 0)  # the upper three quarters of each band is cliff, the lower quarter ledge
    hc = 0.75 * (depth - talus_h)
    hl = 0.25 * (depth - talus_h)
    run = width_half - floor_half - talus_h / math.tan(TALUS) - hc / math.tan(cliff)
    ledge = math.atan(hl / run) if run > hl / math.tan(math.radians(60)) else math.radians(60)
    cot = np.where(is_cliff, 1 / math.tan(cliff), 1 / math.tan(ledge))
    cot[u < 0] = 1 / math.tan(TALUS)
    return z, cot, talus_h, math.degrees(ledge), run > 0


def _canyon(T, name, c):
    L = T.lines[c["river"]]
    rim = float(c.get("rim", T.world["base"]))
    half = float(c.get("width", 800)) / 2
    fh = float(c.get("floor", 60)) / 2
    if fh >= 0.8 * half:
        raise ValueError(f"canyon {name!r}: floor {2 * fh:.0f} m is its floor's width (not a height), and it must be "
                         f"well under the rim-to-rim width {2 * half:.0f} m; the floor's heights come from its river")
    lo = float(L.h.min())
    z, cot, talus_h, ledge_deg, fits = _strata(T, lo, rim, c.get("strata") or {}, half, fh)
    if not fits:
        T.warnings.append(f"canyon {name!r}: {rim - lo:.0f} m deep won't fit {2 * half:.0f} m rim to rim with its "
                          f"cliffs; the ledges stand at 60 deg and it comes out narrower. Widen it or make it shallower")
    C = np.r_[0, np.cumsum((cot[1:] + cot[:-1]) / 2 * np.diff(z))]  # horizontal run to climb from lo to each z
    d, i = cKDTree(L.xy).query(T.P, distance_upper_bound=half * 1.6 + 5 * T.cell)
    d, i = d.reshape(T.X.shape), np.minimum(i, len(L.xy) - 1).reshape(T.X.shape)
    near = np.isfinite(d)
    # the rim's plan wanders: alcoves and buttresses, a few hundred metres apart
    pts = np.c_[T.P, np.zeros(len(T.P))]
    # (alcoves at least about the wall's height apart, and wandering by a share of the wall's run, not of the canyon's
    # half-width: a 520 m canyon's rim noise shredded its walls into spires)
    run = max(half - fh, 3 * T.cell)
    wob = (noise.fbm(pts, max(0.35 * half, 1.2 * (rim - lo)), 2, seed=81).reshape(T.X.shape) - 0.5) * 0.5 * min(half, run)
    # the wander is the rim's and the walls', never the floor's: it had pushed a floor off its river (a ford at a cliff)
    wob = wob * smoothstep(fh, fh + 0.4 * run, np.where(np.isfinite(d), d, 1e9))
    dd = np.where(near, np.maximum(d + wob, 0), np.inf) - fh
    hf = L.h[i]  # this section's floor
    # the run from this floor: talus first (from the local floor, whatever stratum it's in), then the strata above
    top_talus = hf + talus_h
    Ct = np.interp(top_talus, z, C)
    run_t = talus_h / math.tan(TALUS)
    zz = np.where(dd <= 0, hf,
                  np.where(dd <= run_t, hf + dd * math.tan(TALUS), np.interp(Ct + (dd - run_t), C, z)))
    zz = np.minimum(zz, rim)
    cut = near & (zz < T.H)
    T.H = np.where(cut, zz, T.H)
    T._canyon_plan = np.where(cut, zz, getattr(T, "_canyon_plan", np.full(T.X.shape, np.nan)))
    wall = cut & (dd > 0)
    steep = np.interp(zz, z, cot) < 0.5  # cliff strata (cot < 0.5: steeper than ~63 deg) stand as hard rock
    cliffs = wall & steep & (dd > run_t)
    T.hard = T.hard | cliffs
    T.hardness = np.where(cliffs, 0.03, T.hardness)  # canyon cliffs stand: strong rock, not soil
    T.canyons[name] = {"river": L.name, "rim": rim, "half": half, "floor": 2 * fh, "ledge": ledge_deg,
                       "depth": rim - lo, "wall": wall, "cliffs": cliffs,
                       "ledges": wall & ~steep & (dd > run_t)}


def measure_canyon(T, name):
    """The canyon as built: depth, rim-to-rim width at sections along it, and the slopes of its cliff and ledge strata
    (each wall cell's stratum from its built elevation). Never the plan's numbers."""
    cy = T.canyons[name]
    L = T.lines[cy["river"]]
    widths, depths = [], []
    for f in np.linspace(0.1, 0.9, 9):
        xy, _, tan = L.at(f)
        nrm = np.array([-tan[1], tan[0]])
        ds = np.arange(0, 1.7 * cy["half"] + 10 * T.cell, T.cell / 2)
        floor = T.height(xy)
        sides = []
        for sgn in (1, -1):
            hs = T.sample(xy + sgn * nrm * ds[:, None])
            plateau = float(np.percentile(hs[int(0.65 * len(hs)):], 25))  # (a mesa out there isn't the rim)
            up = np.nonzero(hs >= plateau - max(3.0, 0.03 * (plateau - floor)))[0]
            sides.append((ds[up[0]] if len(up) else np.nan, plateau))
        if all(np.isfinite(d) for d, _ in sides):
            widths.append(sides[0][0] + sides[1][0])
            depths.append(min(p for _, p in sides) - floor)
    slope = T._slope()
    dry = np.isnan(T.water)
    # where the plan put each cliff band and ledge, how steep the built ground is there
    q = lambda m: (float(np.median(slope[m])), float((slope[m] > 60).mean())) if m.sum() > 5 else (float("nan"), 0.0)
    return {"width": (min(widths), max(widths)) if widths else None, "depth": max(depths) if depths else None,
            "cliff": q(cy["cliffs"] & dry), "ledge": q(cy["ledges"] & dry)}


def _mesa(T, name, m):
    xy = T.address(m["at"])[0]
    r = float(m.get("radius", 150))
    ground = T.height(xy)
    top = float(m.get("top", ground + 0.15 * T.world["relief"]))
    hgt = top - ground
    if hgt <= 0:
        T.warnings.append(f"mesa {name!r}: its top {top:.0f} m isn't above the ground ({ground:.0f} m)")
        return
    cliff = math.radians(m.get("cliff", 80))
    talus = float(m.get("talus", 0.4)) * hgt
    pts = np.c_[T.P, np.full(len(T.P), 3.0)]
    d = np.hypot(T.X - xy[0], T.Y - xy[1])
    d = d * (1 + 0.18 * (noise.fbm(pts, 0.8 * r, 2, seed=91).reshape(T.X.shape) - 0.5) * 2)  # not a drum
    run_c = (hgt - talus) / math.tan(cliff)
    zz = np.where(d <= r, top, np.where(d <= r + run_c, top - (d - r) * math.tan(cliff),
                                        top - (hgt - talus) - (d - r - run_c) * math.tan(TALUS)))
    T.H = np.maximum(T.H, zz)
    ring = (d > r) & (d <= r + run_c)
    T.hard = T.hard | ring
    T.hardness = np.where(ring, 0.03, T.hardness)
    T.hardness = np.where(d <= r, 0.05, T.hardness)  # a caprock: the top stays flat (a soft top eroded into a dome)
    foot = r + run_c + talus / math.tan(TALUS)
    T.mesas = getattr(T, "mesas", {}) | {name: {"xy": xy.tolist(), "top": top, "radius": r, "topmask": d <= r,
                                                "ring": ring, "foot": foot}}


def settle(T):
    """After texture and erosion: canyon walls go back to their strata, keeping a few metres of the erosion's detail
    (eroded freely they became sand-draped mounds: cliffs built at 74 deg measured 51; kept from creeping they stood as
    pinnacles), except where a route or site was carved into them. A mesa's top is its caprock, flat to within the
    kind's surface roughness."""
    plan = getattr(T, "_canyon_plan", None)
    if plan is not None:
        from .terrain_erode import protected
        b = T.world["bumps"]
        on = np.isfinite(plan) & ~protected(T) & np.isnan(T.water)
        w = ndimage.gaussian_filter(on.astype(float), 1.0) * on
        near = np.where(np.isfinite(plan), plan, T.H)
        T.H = T.H * (1 - w) + (near + np.clip(T.H - near, -2 * b, b)) * w
        # the wandering rim plan closes some alcoves at ledge level into pits (erosion had silted them up; restoring
        # the strata reopened one 53 m deep): fill closed hollows in the walls to their spill level, as sediment would
        import fastscapelib as fs
        wet = ~np.isnan(T.water)
        status = {(int(a), int(c)): fs.NodeStatus.FIXED_VALUE for a, c in zip(*np.nonzero(wet))}
        grid = fs.RasterGrid(list(T.H.shape), [T.cell, T.cell], fs.NodeStatus.FIXED_VALUE, status)
        filled = np.asarray(fs.FlowGraph(grid, [fs.SingleFlowRouter(), fs.PFloodSinkResolver()])
                            .update_routes(T.H.copy())).reshape(T.H.shape)
        beds = np.zeros(T.X.shape, bool)  # (a road's own bed or a pad isn't filled over; its banks may be)
        for k in ("routes", "sites"):
            if k in T.masks:
                beds |= T.masks[k] > 0.05
        # hollows touching the walls: pockets in them, and gullies erosion cut through a wall that the restored wall
        # now dams
        hol, _ = ndimage.label((filled - T.H > 0.05) & ~wet)
        ids = np.unique(hol[ndimage.binary_dilation(np.isfinite(plan), iterations=2)])
        fill = np.isin(hol, ids[ids > 0]) & ~beds
        T.H = np.where(fill, np.maximum(T.H, filled), T.H)
    for m in getattr(T, "mesas", {}).values():
        b = min(0.3, 0.3 * T.world["bumps"])
        T.H = np.where(m["topmask"], np.clip(T.H, m["top"] - b, m["top"] + b), T.H)


def measure_mesa(T, name):
    m = T.mesas[name]
    xy = np.array(m["xy"])
    top = float(np.median(T.H[m["topmask"]]))
    near = np.hypot(T.X - xy[0], T.Y - xy[1]) < 1.5 * m["radius"]
    flat = near & (np.abs(T.H - top) < 2.0)
    lab, _ = ndimage.label(flat)
    k = lab[m["topmask"] & flat]
    area = (lab == np.bincount(k).argmax()).sum() * T.cell ** 2 if len(k) and k.max() > 0 else 0.0
    ang = np.linspace(0, 2 * np.pi, 48, endpoint=False)
    around = xy + 1.15 * m["foot"] * np.c_[np.cos(ang), np.sin(ang)]
    return {"top": top, "across": 2 * math.sqrt(area / math.pi), "cliff": float(np.median(T._slope()[m["ring"]])),
            "rise": top - float(np.median(T.sample(around)))}


def rim_address(T, ref):
    """"<canyon>.<side>_rim@s": on the plateau at the canyon's lip, s along its river; side = west/east/north/south
    or left/right (looking downstream). Returns (xy, h, direction into the canyon)."""
    head, _, s = ref.partition("@")
    cname, side = head.rsplit(".", 1)
    side = side[:-len("_rim")]
    cy = T.canyons[cname]
    L = T.lines[cy["river"]]
    xy, h, tan = L.at(float(s) if s else 0.5)
    nrm = np.array([-tan[1], tan[0]])  # left bank
    want = {"west": (-1, 0), "east": (1, 0), "north": (0, 1), "south": (0, -1)}
    if side in want:
        sgn = 1 if nrm @ np.array(want[side]) >= 0 else -1
    else:
        sgn = 1 if side == "left" else -1
    # the lip along this line (the rim's plan wanders): scanning in from well outside, the last point before the
    # ground falls away below the plateau
    ds = np.arange(1.7 * cy["half"], 0, -T.cell / 2)
    line = xy + sgn * nrm * ds[:, None]
    hs = T.sample(line)
    plateau = np.median(hs[:5])
    falls = np.nonzero(hs < plateau - max(3.0, 0.03 * cy["depth"]))[0]
    k = max(int(falls[0]) - 1, 0) if len(falls) else len(ds) - 1
    out = line[k]
    return out, T.height(out), -sgn * nrm


def _cells(T, p):
    iy = np.clip(np.round((p[:, 1] - T.ys[0]) / T.cell).astype(int), 0, len(T.ys) - 1)
    ix = np.clip(np.round((p[:, 0] - T.xs[0]) / T.cell).astype(int), 0, len(T.xs) - 1)
    return iy * len(T.xs) + ix


def water(T):
    """Rivers carry water (a channel a metre or so deep) except where they're dry; fords are wide and shallow."""
    fords = []
    for name, f in (T.spec.get("fords") or {}).items():
        xy, _, _ = T.address(f["on"])
        fords.append((name, xy, float(f.get("width", 15)), float(f.get("depth", 0.3))))
    T.fords = {n: {"xy": xy.tolist(), "width": w, "depth": dp,
                   "river": (T.spec.get("fords") or {})[n]["on"].split("@")[0]} for n, xy, w, dp in fords}
    T.river_water_lines = {}
    T.river_water = np.zeros(T.X.shape, bool)
    T.ford_mask = np.zeros(T.X.shape, bool)
    for L in (L for L in T.lines.values() if L.kind == "river"):
        r = (T.spec.get("rivers") or {}).get(L.name, {})
        wd = r.get("water", max(3.0, min(L.props["floor"] / 3, 25.0)))
        if not wd:
            continue
        # steep reaches carry a torrent, not a pool: the water narrows with the grade (a 25 m wide sheet of water
        # stood down a 66% volcano flank), to a few metres at 20%+
        step = np.linalg.norm(np.diff(L.xy, axis=0), axis=1)
        grade = np.r_[np.abs(np.diff(L.h)) / np.maximum(step, 1e-6), 0]
        grade = ndimage.uniform_filter1d(grade, max(3, int(30 / max(float(np.mean(step)), 1e-3))), mode="nearest")
        width = np.where(grade > 0.04, np.maximum(2.0, wd * np.clip((0.2 - grade) / 0.16, 0, 1)), wd)
        d, i = cKDTree(L.xy).query(T.P, distance_upper_bound=wd)
        d, i = d.reshape(T.X.shape), np.minimum(i, len(L.xy) - 1).reshape(T.X.shape)
        wet = np.isfinite(d) & np.isnan(T.water) & (d <= np.maximum(width[i], 0.75 * T.cell))
        wd = np.maximum(width[i], 0.75 * T.cell)
        # a river leaving a lake runs over the lake's dam at the lake's level: its bed carved at its own profile cut
        # the dam and drained a tarn to nothing
        hl = L.h.copy()
        for lk in T.lakes.values():
            if lk.get("area", 1) == 0:
                continue
            near = np.hypot(*(L.xy - np.array(lk["xy"])).T) < 1.5 * lk["r"]
            hl = np.where(near, np.maximum(hl, lk["level"]), hl)
        level = hl[i] + 0.2
        depth = 1.0
        for _, fxy, fw, fd in fords:
            nearf = np.hypot(T.X - fxy[0], T.Y - fxy[1]) < fw
            T.ford_mask |= nearf & wet
            depth = np.where(nearf, fd, depth)
        bed = level - depth * (1 - (d / wd) ** 2)
        T.H = np.where(wet, np.minimum(T.H, bed), T.H)
        T.water = np.where(wet, level, T.water)
        T.river_water |= wet
        under = ~np.isnan(T.water.ravel()[_cells(T, L.xy)]) & ~T.river_water.ravel()[_cells(T, L.xy)]
        T.river_water_lines[L.name] = {"xy": L.xy, "level": L.h + 0.2, "width": np.where(under, 0.0, width)}


# ---------------------------------------------------------------- peak forms

PEAK_FORMS = {  # arête slope for arêtes the ridges don't give, faces added up to this many, cirque hollows
    "pyramid": dict(arete=32.0, faces=4, hollow=0.0),
    "horn": dict(arete=40.0, faces=3, hollow=0.14),
}


def default_form(T):
    """Alpine kinds stand their summits as pyramids (a dome read as a hill); everything else keeps the old shape."""
    kind = T.world.get("kind") or ""
    return "pyramid" if any(k in kind for k in ("alpine", "cirque")) else None


def peak_forms(T, H):
    """Carve summits into their form: faces between arêtes, a point at the top. Each ridge leaving a peak is an arête at
    that ridge's own fall (so the ridge carries on unbroken); more arêtes fill the gaps up to the form's face count.
    Inside a sector the face is the plane through the summit and its two arêtes (continuous across them); a horn's
    faces are hollowed into cirques between sharp arêtes. The ground is cut down to the form, and raised to it near the
    top only (never a wall stood on low ground). Records T.peak_forms for the report and T.settle_mask."""
    T.peak_forms = {}
    dflt = default_form(T)
    for name, p in (T.spec.get("peaks") or {}).items():
        form = p.get("form", dflt)
        if not form or form == "dome":
            continue
        if form not in PEAK_FORMS:
            raise ValueError(f"peak {name!r}: form {form!r}: use one of {sorted(PEAK_FORMS) + ['dome']}")
        F = PEAK_FORMS[form]
        c, h = T.points[name]
        floor = float(np.percentile(H[np.hypot(T.X - c[0], T.Y - c[1]) < 0.15 * T.size], 5))
        rise = h - floor
        if rise <= 0:
            continue
        g_def = math.tan(math.radians(float(p.get("arete", F["arete"]))))
        aretes = []  # (bearing, tan of its fall)
        for L in T.lines.values():
            if L.kind != "ridge":
                continue
            dd = np.hypot(*(L.xy - c).T)
            i = int(np.argmin(dd))
            if dd[i] > 3 * T.cell:
                continue
            n = len(L.xy)
            closed = L.props.get("closed")
            reach = int(0.8 * rise / 0.5 / (T.cell / 2))  # samples out to where a 27 deg arête would reach the floor
            for sgn in (-1, 1):
                idx = i + sgn * np.arange(1, reach)
                idx = idx % n if closed else idx[(idx >= 0) & (idx < n)]
                if len(idx) < 4:
                    continue
                dist = np.hypot(*(L.xy[idx] - c).T)
                far = dist > max(0.12 * rise / 0.6, 3 * T.cell)  # (past its levelled top)
                if not far.any():
                    continue
                # the arête falls no faster than the ridge itself anywhere along it: its plane never cuts the ridge
                # (a col 48 m low); from the summit it falls at the ridge's gentlest average fall
                fall = float(np.min((h - L.h[idx][far]) / dist[far]))
                v = L.xy[idx[min(4, len(idx) - 1)]] - c
                aretes.append((math.atan2(v[0], v[1]) % (2 * math.pi), float(np.clip(fall, 0.2, 1.2))))
        aretes.sort()
        n_faces = int(p.get("faces", F["faces"]))
        rng = np.random.default_rng(_seed(name))
        if not aretes:
            a0 = rng.uniform(0, 2 * math.pi)
            aretes = [((a0 + 2 * math.pi * i / n_faces) % (2 * math.pi), g_def) for i in range(n_faces)]
        # fill the widest gaps until there are enough faces and no sector is wider than 150 deg
        while len(aretes) < n_faces or max(_gaps(aretes)) > math.radians(150):
            gaps = _gaps(aretes)
            k = int(np.argmax(gaps))
            b = (aretes[k][0] + gaps[k] / 2 + rng.uniform(-0.15, 0.15) * gaps[k]) % (2 * math.pi)
            aretes.append((b, g_def))
            aretes.sort()
        # the form is the upper part of the mountain: the faces run down ~70% of its rise (carving whole mountainsides
        # down low arêtes cut across the valley floor)
        Rc = min(0.8 * rise / float(np.median([g for _, g in aretes])), 0.35 * T.size)
        dx, dy = T.X - c[0], T.Y - c[1]
        r = np.hypot(dx, dy)
        th = np.arctan2(dx, dy) % (2 * math.pi)
        bear = np.array([a for a, _ in aretes])
        tg = np.array([g for _, g in aretes])
        j = (np.searchsorted(bear, th, side="right") - 1) % len(bear)  # the sector: from arête j to j+1
        j1 = (j + 1) % len(bear)
        e0x, e0y = np.sin(bear[j]), np.cos(bear[j])
        e1x, e1y = np.sin(bear[j1]), np.cos(bear[j1])
        det = e0x * e1y - e0y * e1x
        a = (dx * e1y - dy * e1x) / det
        b = (e0x * dy - e0y * dx) / det
        z = h - np.maximum(a, 0) * tg[j] - np.maximum(b, 0) * tg[j1]
        span = (bear[j1] - bear[j]) % (2 * math.pi)
        t_ang = ((th - bear[j]) % (2 * math.pi)) / np.maximum(span, 1e-6)
        hollow = F["hollow"] * float(p.get("hollow", 1.0))
        if hollow:
            u = np.clip(r / Rc, 0, 1)
            z = z - hollow * rise * np.sin(np.pi * t_ang) ** 1.5 * 4 * u * (1 - u)
        # other ridges, peaks and cols near it stand: the faces can't cut into their flanks (a big peak's face cut a
        # neighbouring col 110 m down)
        others = [(L.xy, L.h) for L in T.lines.values() if L.kind == "ridge"
                  and np.hypot(*(L.xy - c).T).min() > 3 * T.cell]
        own_pts = [(np.array([q]), np.array([hq])) for n2, (q, hq) in T.points.items()
                   if n2 != name and np.linalg.norm(q - c) > 3 * T.cell]
        if others or own_pts:
            from scipy.spatial import cKDTree
            pts = np.vstack([a for a, _ in others + own_pts])
            hs = np.concatenate([b for _, b in others + own_pts])
            dd, ii = cKDTree(pts).query(T.P, distance_upper_bound=0.5 * Rc)
            ok = np.isfinite(dd)
            guard = np.full(len(T.P), -np.inf)
            guard[ok] = hs[np.minimum(ii[ok], len(hs) - 1)] - dd[ok] * math.tan(math.radians(35))
            z = np.maximum(z, guard.reshape(T.X.shape))
        w_cut = smoothstep(Rc, 0.6 * Rc, r) * smoothstep(h - 0.8 * rise, h - 0.5 * rise, H)
        w_raise = smoothstep(0.45 * Rc, 0.12 * Rc, r)
        Hn = H * (1 - w_cut) + np.minimum(H, z) * w_cut
        Hn = Hn + np.maximum(z - Hn, 0) * w_raise
        # carving leaves hollows where the faces meet uncut ground: fill them to their lip, as scree and a tarn's silt
        # would (a cirque floor, not a 100 m pit)
        # (only hollows the carving made: a basin's floor inside the zone is a hollow already and stays one)
        from skimage.morphology import reconstruction
        zone = w_cut > 0.02
        top = max(Hn.max(), H.max())
        before = reconstruction(np.where(zone, top, H), H, method="erosion") - H
        after = reconstruction(np.where(zone, top, Hn), Hn, method="erosion") - Hn
        new_hollow = zone & (after > before + 0.5)
        lab, _ = ndimage.label(new_hollow)
        old = np.unique(lab[(before > 0.5) & new_hollow])
        new_hollow &= ~np.isin(lab, old[old > 0])
        H = np.where(new_hollow, Hn + after, Hn)
        T.settle_mask = np.maximum(getattr(T, "settle_mask", np.zeros(T.X.shape)), w_cut)
        ar = (np.minimum(t_ang, 1 - t_ang) * span * r < 1.5 * T.cell) & (r < 0.7 * Rc)  # the arêtes stand
        T.hard |= ar
        T.hardness = np.where(ar, np.minimum(T.hardness, 0.2), T.hardness)
        T.peak_forms[name] = {"form": form, "xy": c.tolist(), "h": h, "Rc": Rc, "aretes": aretes}
    return H


def _gaps(aretes):
    b = [a for a, _ in aretes]
    return [((b[(i + 1) % len(b)] - b[i]) % (2 * math.pi)) or 2 * math.pi for i in range(len(b))]


def _seed(name):
    import zlib
    return zlib.crc32(name.encode()) % 100000


def measure_peak(T, name):
    """As built: how far the ground falls in the first stretch from the summit (a dome barely falls), the faces' median
    slope, and how many arêtes run down from it."""
    pf = T.peak_forms[name]
    c = np.array(pf["xy"])
    top = T.summit(name)
    r = np.hypot(T.X - c[0], T.Y - c[1])
    near = max(3 * T.cell, 0.1 * pf["Rc"])
    ring = (r > 0.8 * near) & (r < 1.2 * near)
    fall = top - float(np.median(T.H[ring]))
    slope = T._slope()
    faces = (r > 0.15 * pf["Rc"]) & (r < 0.55 * pf["Rc"])
    return {"fall": fall, "at": near, "faces": float(np.median(slope[faces])) if faces.any() else float("nan"),
            "aretes": len(pf["aretes"])}
