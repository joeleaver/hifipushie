"""Volcanoes: a cone with a volcano's profile, a crater or caldera, radial gullies, collapse scars and lava flows.
Built into the base (large-scale ground, before texture, the sea and erosion), so everything after sees them as ground.
A lone peak made a dome and a crater was a basin inside a ring of peaks; lava was a rounded ridge painted dark (a "tan
bump" from the boat).

"volcanoes": {name: {"at": [x, y], "h": rim m, "type": "strato" | "shield" | "cinder",
                     "base_radius": m (its footprint on the ground beneath), "slope": deg (average flank), "top_slope": deg,
                     "crater": {"radius": m (the rim), "depth": m, "walls": deg, "breach": compass | address,
                                "lake": true | level m} | false,
                     "caldera": {...the same, a wide crater with cliff walls and a flat floor},
                     "gullies": 0..1,
                     "collapses": {name: {"toward": compass | address, "width": m, "depth": m, "head": 0..1,
                                          "reach": 0..1, "walls": deg, "debris": true}},
                     "flows": {name: {"from": "crater" | compass (a flank vent that side) | address, "length": m,
                                      "width": m, "thick": m, "toward"?: address | compass, "front": deg}}}}

Profiles (u: 0 at the rim, 1 at the foot; f: the height share): strato is concave (exponential, steep near the top,
easing to the foot: the average and the top slope pick its curvature), shield is convex (1 - u^p, a broad dome of low
slopes), cinder is nearly straight at the angle of repose. The footprint wanders a little with bearing, and the rim's
height too (its highest point is `h`).
Gullies (barrancos): radial V valleys, fading in below the rim and out at the foot, wandering and of uneven depth.
Collapses: a horseshoe amphitheatre cut into the flank (a U outline opening downslope, walls at `walls`, a floor
falling from `depth` below the flank at its head to daylight at `reach`), with hummocky debris spread beyond its mouth.
A crater's `breach` is a small collapse from the crater floor out through the rim.
Flows: traced down the ground as built (steepest descent of the ground smoothed at the flow's width, with inertia), so
they run down gullies and into scars. Each is a sheet `thick` metres deep (thicker at its toe) with steep margins and
front (`front`, default 38 deg), levees, pressure ridges bowed downstream, and blocky roughness. Where the ground
beside it is higher, the ground stays (a flow fills a gully). A flow reaching the sea builds a lava delta. Flows are
hard rock to the erosion.

Zones/addresses: the volcano's name (its summit: a sight target), "<v>.crater" (its floor's middle; a zone: the crater),
"<v>_rim@0.25" (a point on the rim, a quarter of the way round clockwise from north), each flow (a line: "flow@0.5"; a
zone), "lava" (every flow), each collapse (its floor; a zone), "debris" (every debris field).
"""

from __future__ import annotations

import math
import zlib

import numpy as np
from scipy import ndimage
from scipy.spatial import cKDTree

from . import noise
from .terrain import Line, _arclen, compass, smoothstep

TYPES = {  # average flank slope, top slope, crater radius (share of the footprint), crater depth (share of its radius)
    "strato": dict(avg=20.0, top=33.0, crater=0.09, depth=0.7, walls=38.0, gullies=0.6),
    "shield": dict(avg=6.0, top=2.0, crater=0.06, depth=0.25, walls=70.0, gullies=0.15),
    "cinder": dict(avg=30.0, top=31.0, crater=0.4, depth=0.5, walls=32.0, gullies=0.1),
}


def _seed(*parts) -> int:
    return zlib.crc32("/".join(map(str, parts)).encode()) % 100000


def _ang_noise(theta, scale, seed, octaves=3):
    """Noise continuous round a circle (0..1): fbm on the unit circle, `scale` radians across."""
    p = np.stack([np.cos(theta).ravel(), np.sin(theta).ravel(), np.full(theta.size, 0.37 * seed % 17)], 1)
    return noise.fbm(p, scale, octaves, seed=seed).reshape(np.shape(theta))


def _profile(kind, avg, top, u):
    """Height share f(u) from the rim (u=0, f=1) to the foot (u=1, f=0)."""
    u = np.clip(u, 0, 1)
    if kind == "shield":  # gently convex: the top at half the average slope, the foot at 1.5x
        return 1 - (0.5 * u + 0.5 * u ** 2)
    ratio = math.tan(math.radians(top)) / math.tan(math.radians(avg))  # top slope / average slope
    if ratio <= 1.02:
        a = 0.35  # (cinder: nearly straight, a slightly concave toe)
    else:  # a / (1 - e^-a) = ratio
        lo, hi = 1e-4, 30.0
        for _ in range(60):
            a = (lo + hi) / 2
            lo, hi = (a, hi) if a / (1 - math.exp(-a)) < ratio else (lo, a)
    return (np.exp(-a * u) - math.exp(-a)) / (1 - math.exp(-a))


def _dir(T, ref, centre):
    """A unit direction from the volcano's centre: a compass word, a bearing in degrees, or toward an address."""
    if isinstance(ref, (int, float)):
        a = math.radians(ref)
        return np.array([math.sin(a), math.cos(a)])
    d = compass(ref)
    if d is not None:
        return d
    xy = _xy(T, ref)
    v = xy - centre
    return v / (np.linalg.norm(v) + 1e-9)


def _xy(T, ref):
    if isinstance(ref, (list, tuple)):
        return np.array(ref[:2], float)
    return T._early_xy(ref) if getattr(T, "H", None) is None else T.address(ref)[0]


def build(T, H):
    """Stand every volcano on the base H; returns the new H. Records T.volcanoes, T.vzones and lines for flows."""
    T.volcanoes, T.vzones = {}, {}
    vs = T.spec.get("volcanoes") or {}
    if not vs:
        return H
    lava = np.zeros(T.X.shape, bool)
    debris = np.zeros(T.X.shape, bool)
    for name, v in vs.items():
        H = _cone(T, name, v, H)
    for name, v in vs.items():  # (collapses and flows after every cone: a flow may run off onto a neighbour)
        V = T.volcanoes[name]
        for cn, c in (V["collapses"]).items():
            H, m, deb = _collapse(T, name, cn, c, H)
            T.vzones[cn] = m
            debris |= deb
        for fn, f in (v.get("flows") or {}).items():
            H, m = _flow(T, name, fn, f, H)
            T.vzones[fn] = m
            lava |= m
    T.vzones["lava"] = lava
    T.vzones["debris"] = debris
    return H


def _cone(T, name, v, H):
    kind = v.get("type", "strato")
    if kind not in TYPES:
        raise ValueError(f"volcano {name!r}: type {kind!r}: use one of {sorted(TYPES)}")
    D = TYPES[kind]
    c = np.array(v["at"][:2], float)
    ground = float(T.sample(np.atleast_2d(c), H)[0])
    h = float(v.get("h", ground + T.world["relief"]))
    rise = h - ground
    if rise <= 0:
        raise ValueError(f"volcano {name!r}: its rim {h:.0f} m isn't above the ground there ({ground:.0f} m)")
    avg = float(v.get("slope", D["avg"]))
    cr = v.get("caldera") or v.get("crater", {})
    caldera = bool(v.get("caldera"))
    has_crater = cr is not False
    cr = cr if isinstance(cr, dict) else {}
    # the footprint: from the rim down at the average slope (a caldera's rim is wide: the foot is beyond it)
    rc_guess = float(cr.get("radius", 0))
    share = (0.3 if caldera else D["crater"]) if has_crater else 0.0
    R = float(v.get("base_radius", 0)) or (rc_guess + rise / math.tan(math.radians(avg)) if rc_guess
                                           else rise / math.tan(math.radians(avg)) / (1 - share))
    rc = float(cr.get("radius", share * R)) if has_crater else 0.0
    if "base_radius" in v:  # the footprint given: the average slope follows from it
        avg = math.degrees(math.atan(rise / max(R - rc, T.cell)))
    top = float(v.get("top_slope", D["top"] if kind != "strato" else max(D["top"], avg + 6)))
    if not has_crater:
        rc = max(2 * T.cell, 0.02 * R)  # a rounded summit instead
    if rc >= 0.8 * R:
        raise ValueError(f"volcano {name!r}: its crater ({rc:.0f} m radius) is nearly as wide as its footprint "
                         f"({R:.0f} m): widen base_radius or shrink the crater")
    walls = float(cr.get("walls", 65.0 if caldera else D["walls"]))
    depth = float(cr.get("depth", (0.45 if caldera else D["depth"]) * rc * math.tan(math.radians(walls))
                         if not caldera else 0.35 * rise))
    depth = min(depth, rc * math.tan(math.radians(walls)) * 0.98) if has_crater else 0.0
    sd = _seed(name)
    dx, dy = T.X - c[0], T.Y - c[1]
    d = np.hypot(dx, dy)
    th = np.arctan2(dx, dy)  # bearing clockwise from north
    # the footprint and the rim wander with bearing (a lathe-turned cone read as a model)
    Rt = R * (1 + 0.12 * (2 * _ang_noise(th, 1.1, sd) - 1))
    rim_n = _ang_noise(th, 0.9, sd + 1)
    rim_drop = 0.2 * depth if has_crater else 0.0
    top_h = h - rim_drop * (rim_n - rim_n.min()) / max(np.ptp(rim_n), 1e-6)  # its highest point is h
    u = (d - rc) / np.maximum(Rt - rc, T.cell)
    f = _profile(kind, avg, top, u)
    # the flank runs from the rim down to the ground where it stands (a blend, not an offset from the centre's ground:
    # a cone on a slope had its uphill rim raised by the slope, 43 m over its asked top)
    A = H * (1 - f) + top_h * f
    if has_crater:
        tw = math.tan(math.radians(walls))
        floor = h - depth
        pit = np.maximum(top_h - (rc - d) * tw, floor + 0.04 * depth * (d / rc) ** 2)  # (a faint dish, not a table)
        A = np.where(d < rc, pit, A)
    else:
        A = np.where(d < rc, top_h, A)  # a small rounded top
    Z = A - H
    # soften the rim's crease over a cell or two (a knife edge aliased into a sawtooth)
    near_rim = smoothstep(3 * T.cell, 1 * T.cell, np.abs(d - rc)) if has_crater else 0
    Z = Z * (1 - near_rim) + ndimage.gaussian_filter(Z, 1.0) * near_rim
    # gullies: radial valleys between rounded ribs, from a little below the rim to the foot
    g_amt = float(v.get("gullies", D["gullies"]))
    G = np.zeros(T.X.shape)
    if g_amt > 0:
        # two generations: gullies heading just below the rim, and twice as many starting mid-flank between them (the
        # lower flank is longer round, and real cones gather more gullies downslope); ~100 m apart at the foot
        spacing = max(5 * T.cell, 0.09 * (R - rc), 50.0)
        n = max(8, int(2 * math.pi * (rc + 0.5 * (R - rc)) / spacing / 2))
        pts = np.c_[T.P, np.full(len(T.P), 5.0)]
        warp = (noise.fbm(pts, 0.3 * R, 3, seed=sd + 2).reshape(T.X.shape) - 0.5) * 1.3 * math.pi / n
        depth_g = g_amt * 0.06 * rise * (0.6 + 0.4 * np.clip(f, 0, 1))
        for gen, (nn, u0, off) in enumerate(((n, 0.04, 0.0), (2 * n, 0.3, 0.25))):
            ph = (th + warp) * nn / (2 * math.pi) + off
            k = np.floor(ph)
            fr = ph - k
            v_shape = np.clip(1 - np.abs(fr - 0.5) / 0.26, 0, 1) ** 1.5  # narrow V gullies, broad ribs between
            each = 0.35 + 0.9 * _ang_noise(2 * math.pi * (k + 0.5) / nn, 0.05, sd + 3 + gen, 1)  # uneven depths
            fade = smoothstep(u0, u0 + 0.25, u) * smoothstep(1.05, 0.6, u)
            G = np.maximum(G, depth_g * (0.7 if gen else 1.0) * v_shape * each * fade * (d >= rc))
        # (never deeper than the flank is tall there: gullies died out into trenches on the plain)
        G = np.minimum(G, 0.5 * np.maximum(Z, 0))
    Z = Z - G
    on = (d < Rt * 1.02) & ((Z > 0.05) | (d < rc))
    Hn = np.where(on, H + np.where(d >= rc, np.maximum(Z, 0), Z), H)  # (inside the crater the pit is the ground)
    T.t = np.where(on, np.maximum(T.t, np.clip(f, 0, 1)), T.t)
    T.crest = np.maximum(T.crest, Hn)
    crater = d < rc if has_crater else np.zeros(T.X.shape, bool)
    rim = on & (np.abs(d - rc) < 2.5 * T.cell)  # the rim is a knife edge erosion would take 20-30 m off: it stands
    T.hard |= rim
    T.hardness = np.where(rim, 0.1, T.hardness)
    if has_crater:
        T._fixed_river |= crater & (Hn < floor + 0.1 * depth)  # water ends in the crater: base level for erosion
        wallm = crater & (Hn > floor + 0.15 * depth)
        if walls >= 45:  # cliff walls stand
            T.hard |= wallm
            T.hardness = np.where(wallm, 0.15, T.hardness)
    T.points[name] = (c, h)
    rim_xy = c + (rc if has_crater else 0) * np.stack([np.sin(np.linspace(0, 2 * np.pi, 180)),
                                                        np.cos(np.linspace(0, 2 * np.pi, 180))], 1)
    s, length = _arclen(rim_xy)
    T.lines[f"{name}_rim"] = Line(f"{name}_rim", "rim", rim_xy, np.full(len(rim_xy), h), s,
                                  {"closed": True, "length": length})
    T.volcanoes[name] = V = {"xy": c.tolist(), "h": h, "ground": ground, "R": R, "rc": rc, "depth": depth,
                             "floor": h - depth, "walls": walls, "kind": kind, "avg": avg, "top": top,
                             "caldera": caldera, "crater": crater, "footprint": on, "collapses": {}, "flows": {}}
    T.vzones[f"{name}.crater"] = crater
    colls = dict(v.get("collapses") or {})
    if has_crater and cr.get("breach") is not None:  # a breached crater: a small collapse from its floor out
        colls[f"{name}_breach"] = {"toward": cr["breach"], "width": 1.1 * rc, "head": 0.0, "_floor": h - depth,
                                   "reach": min(0.45, (rc + 0.35 * (R - rc)) / R), "walls": walls, "debris": False}
    V["collapses"] = colls
    if has_crater and cr.get("lake") and cr.get("breach") is not None:
        T.warnings.append(f"volcano {name!r}: a breached crater can't hold a lake (it drains through the breach): "
                          f"drop one of them")
    if has_crater and cr.get("lake"):  # a crater lake: a lake landform on its floor
        lvl = float(cr["lake"]) if not isinstance(cr["lake"], bool) else h - depth + 0.25 * depth
        lfs = T.spec.setdefault("landforms", {})
        fr_ = max(rc - depth / math.tan(math.radians(walls)), 0.3 * rc)
        lfs.setdefault(f"{name}_lake", {"type": "lake", "at": c.tolist(), "radius": fr_, "level": lvl,
                                        "depth": max(2.0, lvl - (h - depth) + 3.0), "dam": False, "lobes": 0.1})
    return Hn


def _collapse(T, vname, name, c, H):
    """A horseshoe amphitheatre in the flank opening toward `toward`: walls at `walls` deg, a floor from `depth` below
    the flank at its head, falling to daylight at `reach` (share of the footprint's radius), debris hummocks below."""
    V = T.volcanoes[vname]
    centre = np.array(V["xy"])
    R, rc = V["R"], V["rc"]
    a = _dir(T, c.get("toward", "south"), centre)
    p = np.array([-a[1], a[0]])
    W = float(c.get("width", 0.5 * R))
    head = float(c.get("head", 0.15)) * R
    reach = float(c.get("reach", 0.85)) * R
    rise = V["h"] - V["ground"]
    walls = math.radians(float(c.get("walls", 50)))
    vx, vy = T.X - centre[0], T.Y - centre[1]
    al = vx * a[0] + vy * a[1]
    ac = vx * p[0] + vy * p[1]
    hw = 0.5 * W * (1 + 0.6 * np.clip((al - head - 0.5 * W) / max(reach - head, 1), 0, 1))  # opening downslope
    cc = head + 0.5 * W
    sd = _seed(vname, name)
    # the outline: a round head, straight-ish sides; wandering a little (a stencil read as a stencil)
    pts = np.c_[T.P, np.full(len(T.P), 9.0)]
    wob = (noise.fbm(pts, 0.25 * W, 3, seed=sd).reshape(T.X.shape) - 0.5) * 0.18 * W
    e = np.where(al < cc, np.hypot(al - cc, ac) - 0.5 * W, np.abs(ac) - hw) + wob  # signed: negative inside
    head_xy = centre + a * head
    # the floor follows the flank's own long profile down the axis, sunk by `depth` at the head and rising to meet it at
    # the mouth (a straight floor from head to mouth stood above a concave cone's flank: the scar cut only its head)
    depth = float(c.get("depth", 0.3 * rise))
    axis = np.linspace(head, reach, 200)
    prof = ndimage.gaussian_filter1d(np.minimum.accumulate(T.sample(centre + axis[:, None] * a, H)), 3, mode="nearest")
    if "_floor" in c:  # a breach: from the crater's floor, out through the rim
        z0 = float(c["_floor"])
        sink = np.maximum(prof - z0, 0)
    else:
        sink = np.full(len(axis), depth)
    tt = np.clip((al - head) / max(reach - head, 1e-6), 0, 1)
    fall = sink * (1 - np.linspace(0, 1, len(axis))) ** 1.4  # deepest under the headwall: an amphitheatre
    zf = np.interp(al, axis, prof - fall, left=prof[0] - fall[0], right=prof[-1])
    z_head = float(prof[0] - fall[0])
    zf = zf + 0.02 * rise * (noise.fbm(pts, 0.15 * W, 2, seed=sd + 1).reshape(T.X.shape) - 0.5)
    C = zf + np.maximum(e, 0) * math.tan(walls)
    C = np.where(al > reach, np.inf, C)  # (beyond the mouth nothing is cut: a trench across the plain otherwise)
    C = np.where(al < head - 0.1 * W, np.maximum(C, zf + (head - 0.1 * W - al) * math.tan(walls)), C)
    Hn = np.minimum(H, C)
    cut = H - Hn
    scar = cut > 0.5
    wall = scar & (e > -2 * T.cell) & (cut > 0.1 * float(c.get("depth", 0.3 * rise)))
    T.hard |= wall
    T.hardness = np.where(wall, 0.2, T.hardness)
    deb = np.zeros(T.X.shape, bool)
    if c.get("debris", True):
        # hummocks: a field of mounds spread beyond the mouth (and a few on the scar's floor), heights by the scar
        rng = np.random.default_rng(sd)
        L = 1.4 * W
        n = int(np.clip(L * W / (0.08 * W) ** 2 * 0.35, 20, 400))
        ta = rng.uniform(-0.15, 1.0, n) ** 1.0
        al_m = reach - 0.1 * W + ta * L
        ac_m = rng.uniform(-1, 1, n) * 0.6 * W * (1 + 0.8 * np.clip(ta, 0, 1))
        rad = rng.uniform(0.03, 0.08, n) * W
        hgt = rng.uniform(0.3, 1.0, n) * min(0.035 * rise, 0.25 * W) * (1 - 0.6 * np.clip(ta, 0, 1))
        bump = np.zeros(T.X.shape)
        for i in range(n):
            q = centre + a * al_m[i] + p * ac_m[i]
            r2 = ((T.X - q[0]) ** 2 + (T.Y - q[1]) ** 2) / rad[i] ** 2
            m = r2 < 4
            bump[m] += hgt[i] * np.exp(-r2[m])
        Hn = Hn + bump
        deb = bump > 0.1 * hgt.mean()
    V["collapses"][name] = {"a": a.tolist(), "W": W, "head": head, "reach": reach, "scar": scar, "wall": wall,
                            "z_head": z_head, "debris": deb, "floor_xy": (centre + a * (0.5 * (head + reach))).tolist()}
    return Hn, scar, deb


def _vent(T, V, f, H):
    """Where a flow starts: over the crater's lowest rim (or its breach's mouth), a flank vent on a compass side, or an
    address."""
    centre = np.array(V["xy"])
    src = f.get("from", "crater")
    R, rc = V["R"], V["rc"]
    if src in ("crater", "summit"):
        br = [cl for n, cl in V["collapses"].items() if n.endswith("_breach")]
        if br:
            cl = br[0]
            return centre + np.array(cl["a"]) * (cl["reach"] + T.cell)
        if f.get("toward") is not None:
            a = _dir(T, f["toward"], centre)
        else:  # the rim's lowest point
            ang = np.linspace(0, 2 * np.pi, 72, endpoint=False)
            ring = centre + (rc + 1.5 * T.cell) * np.c_[np.sin(ang), np.cos(ang)]
            k = int(np.argmin(T.sample(ring, H)))
            a = np.array([np.sin(ang[k]), np.cos(ang[k])])
        return centre + a * (rc + 2 * T.cell)
    d = compass(src)
    if d is not None or isinstance(src, (int, float)):
        a = _dir(T, src, centre)
        return centre + a * (rc + 0.3 * (R - rc))
    return _xy(T, src)


def _flow(T, vname, name, f, H):
    V = T.volcanoes[vname]
    rise = V["h"] - V["ground"]
    width = float(f.get("width", max(0.06 * V["R"], 6 * T.cell)))
    thick = float(f.get("thick", float(np.clip(0.1 * width, 4.0, 30.0))))
    length = float(f.get("length", V["R"]))
    front = math.radians(float(f.get("front", 38)))
    sd = _seed(vname, name)
    p = _vent(T, V, f, H)
    Hs = ndimage.gaussian_filter(H, max(0.35 * width, 1.5 * T.cell) / T.cell)
    gy, gx = np.gradient(Hs, T.cell)
    sea = T.spec.get("sea")
    level = float(sea.get("level", 0.0)) if sea else None
    to = f.get("toward")
    step = 0.6 * T.cell
    path = [p.copy()]
    centre = np.array(V["xy"])
    prev = (p - centre) / (np.linalg.norm(p - centre) + 1e-9)
    (x0, y0), (x1, y1) = T.spec["extent"]
    run, flat, delta = 0.0, 0.0, 0.0
    while run < length:
        q = np.atleast_2d(path[-1])
        g = np.array([T.sample(q, gx)[0], T.sample(q, gy)[0]])
        down = -g / (np.linalg.norm(g) + 1e-9)
        slope = np.linalg.norm(g)
        want = down if slope > 0.01 else prev
        if to is not None:
            tv = _dir(T, to, path[-1])
            want = want + 0.35 * tv
        # (lava wanders: a slow random walk across the fall line, not a ruled line down the cone)
        side = np.array([-want[1], want[0]])
        want = want + 0.35 * side * (2 * noise.fbm(np.array([[run / (2.5 * width), 0.0, 1.0]]), 1.0, 2, seed=sd + 4)[0] - 1)
        d = 0.8 * prev + 0.2 * want  # lava has momentum: it doesn't turn on every bump
        d /= np.linalg.norm(d) + 1e-9
        nxt = path[-1] + d * step
        if not (x0 + T.cell < nxt[0] < x1 - T.cell and y0 + T.cell < nxt[1] < y1 - T.cell):
            break
        z = T.sample(np.atleast_2d(nxt), H)[0]
        if level is not None and z < level + 0.5:  # into the sea: a lava delta, a few widths out at most
            delta += step
            if delta > 1.2 * width:
                break
        flat = flat + step if slope < 0.02 else 0.0
        if flat > 2.5 * width:  # it ponds and stops
            break
        path.append(nxt)
        prev = d
        run += step
    xy = np.array(path)
    if len(xy) < 4:
        T.warnings.append(f"flow {name!r}: it had nowhere to run from its vent at [{p[0]:.0f}, {p[1]:.0f}]")
        return H, np.zeros(T.X.shape, bool)
    s, L = _arclen(xy)
    S = s * L
    nstep = max(1, len(xy))
    # width: narrow at the vent, wider down the flow, a bulbous toe; wandering along it
    wn = noise.fbm(np.c_[S / max(width, 1), np.zeros(nstep), np.full(nstep, 3.0)], 1.5, 2, seed=sd)
    hw = 0.5 * width * (0.6 + 0.5 * s) * (1 + 0.35 * (2 * wn - 1)) * (1 + 0.25 * smoothstep(0.8, 1.0, s))
    hw = np.maximum(hw, 1.5 * T.cell)
    ground = T.sample(xy, H)
    if level is not None:
        ground = np.maximum(ground, level + 1.0)  # (a delta stands a little above the water)
    sig = max(1.0, 0.5 * width / (L / nstep))
    zc = ndimage.gaussian_filter1d(ground, sig, mode="nearest")
    tk = thick * (0.7 + 0.3 * s) * (1 + 0.5 * smoothstep(0.75, 1.0, s))
    zc = zc + tk
    reach = hw.max() + tk.max() / math.tan(front) + 3 * T.cell
    dist, i = cKDTree(xy).query(T.P, distance_upper_bound=reach)
    near = np.isfinite(dist).reshape(T.X.shape)
    i = np.minimum(i, len(xy) - 1).reshape(T.X.shape)
    dist = np.where(near, dist.reshape(T.X.shape), np.inf)
    # lobate margins and toe: the edge wanders by a share of the width (a tube with a round end read as a lollipop)
    lob = noise.fbm(np.c_[T.P, np.full(len(T.P), 17.0)], 0.9 * width, 3, seed=sd + 5).reshape(T.X.shape)
    dist = dist + (2 * lob - 1) * 0.45 * hw[i]
    a = dist / hw[i]
    levee = 0.18 * tk[i] * smoothstep(0.55, 0.85, a) * smoothstep(1.05, 0.9, a)
    spacing = np.maximum(3 * T.cell, 0.45 * hw[i])
    a = np.where(near, a, 9.0)
    ph = (S[i] + 0.9 * a ** 2 * hw[i]) / spacing
    ridge = max(1.0, 0.08 * thick) * (0.5 + 0.5 * np.cos(2 * np.pi * ph)) * smoothstep(1.0, 0.6, a)
    pts = np.c_[T.P, np.full(len(T.P), 13.0)]
    blocky = (noise.fbm(pts, 2.5 * T.cell, 2, seed=sd + 1).reshape(T.X.shape) - 0.5) * min(3.0, 0.15 * thick) * 2
    top = zc[i] + levee + ridge + blocky
    F = top - np.maximum(dist - hw[i], 0) * math.tan(front)
    F = np.where(near, F, -np.inf)
    on = near & (F > H + 0.3)
    Hn = np.where(on, F, H)
    T.hardness = np.where(on, 0.05, T.hardness)  # young lava: erosion barely touches it
    T.hard |= on & (dist > 0.8 * hw[i])  # (its margins and front stand steep)
    T.lines[name] = Line(name, "flow", xy, zc, s, {"length": L, "width": width})
    V["flows"][name] = {"xy": xy, "hw": hw, "thick": thick, "front": math.degrees(front), "mask": on, "length": L,
                        "vent": p.tolist(), "delta": delta}
    return Hn, on


def settle(T, pre):
    """After erosion: a volcano's designed forms (gullies, rim, scars, flows) come back as they were before it, keeping
    the erosion's detail within the kind's gully depth (eroded freely, 20 m gullies were diffused into soft drapery and
    the rim lost 20-30 m)."""
    if not getattr(T, "volcanoes", None):
        return
    from .terrain_erode import protected
    on = np.zeros(T.X.shape, bool)
    for V in T.volcanoes.values():
        on |= V["footprint"]
        for cl in V["collapses"].values():
            on |= cl["scar"] | cl["debris"]
    on &= ~protected(T) & np.isnan(T.water)
    w = ndimage.gaussian_filter(on.astype(float), 1.0) * on
    g = T.world["gully"]
    T.H = T.H * (1 - w) + (pre + np.clip(T.H - pre, -g, 0.5 * g)) * w


# ---------------------------------------------------------------- measuring (the ground as built)

def _rim_measure(T, V):
    """Per bearing: the rim's top and its distance from the centre, out from the crater floor to where the ground
    stops standing near its highest (a shield's flat top ran on past its caldera's rim)."""
    c = np.array(V["xy"])
    ang = np.linspace(0, 2 * np.pi, 72, endpoint=False)
    dirs = np.c_[np.sin(ang), np.cos(ang)]
    rs = np.arange(0, V["rc"] + 0.5 * (V["R"] - V["rc"]), T.cell / 2)
    tops, rims = [], []
    for dvec in dirs:
        hs = T.sample(c + rs[:, None] * dvec)
        top = hs.max()
        k = int(np.argmax(hs >= top - max(1.0, 0.03 * V["depth"])))
        k = k + int(np.argmax(hs[k:])) if k < len(hs) - 1 and (np.diff(hs[k:k + 6]) > 0).all() else k
        tops.append(hs[k])
        rims.append(rs[k])
    return np.array(tops), np.array(rims), dirs, rs


def report(T) -> list[str]:
    out = []
    slope = T._slope()
    for name, V in getattr(T, "volcanoes", {}).items():
        c = np.array(V["xy"])
        d = np.hypot(T.X - c[0], T.Y - c[1])
        tops, rims, dirs, rs = _rim_measure(T, V)
        line = f"volcano {name} ({V['kind']}): top {tops.max():.0f} m (asked {V['h']:.0f})"
        if V["rc"] > 2.5 * T.cell and V["depth"] > 0:
            floor = float(np.percentile(T.H[V["crater"]], 3)) if V["crater"].any() else float("nan")
            wet = V["crater"] & ~np.isnan(T.water)
            line += (f"; crater {2 * np.median(rims):.0f} m across rim to rim, floor {floor:.0f} m, "
                     f"{np.median(tops) - floor:.0f} m deep below the rim's median ({tops.min() - floor:.0f} at its lowest "
                     f"point)" + (f", water at {float(np.nanmax(T.water[wet])):.0f} m" if wet.any() else ""))
            wallm = V["crater"] & (T.H > floor + 0.2 * (np.median(tops) - floor))
            if wallm.sum() > 5:
                line += f"; inner walls median {np.median(slope[wallm]):.0f} deg"
        out.append(line)
        # the flanks, by thirds of the way from the rim to the foot, where they aren't scarred or under lava
        u = (d - np.median(rims)) / max(V["R"] - np.median(rims), 1)
        clean = V["footprint"] & ~T.vzones.get("lava", np.zeros(T.X.shape, bool))
        for cl in V["collapses"].values():
            clean &= ~cl["scar"] & ~cl["debris"]
        clean &= np.isnan(T.water)
        thirds = []
        for lo, hi in ((0.02, 0.33), (0.33, 0.66), (0.66, 0.95)):
            m = clean & (u >= lo) & (u < hi)
            thirds.append(f"{np.median(slope[m]):.0f}" if m.sum() > 5 else "-")
        dry = V["footprint"] & np.isnan(T.water)
        reach = np.sqrt(dry.sum() * T.cell ** 2 / math.pi) if dry.any() else 0
        out.append(f"  flanks: median slope upper third {thirds[0]} deg, middle {thirds[1]}, lower {thirds[2]} "
                   f"(asked: average {V['avg']:.0f}" + (f", top {V['top']:.0f}" if V["kind"] == "strato" else "")
                   + f"); dry footprint ~{2 * reach:.0f} m across")
        for cn, cl in V["collapses"].items():
            if not cl["scar"].any():
                out.append(f"  collapse {cn}: cut nothing (its floor stands above the flank)")
                continue
            a = np.array(cl["a"])
            wal = cl["wall"] & np.isnan(T.water)
            # the headwall: the scar's rim round its head, above the floor just below it
            hxy = c + a * cl["head"]
            dh = np.hypot(T.X - hxy[0], T.Y - hxy[1])
            ring = ndimage.binary_dilation(cl["scar"], iterations=2) & ~cl["scar"] & (dh < 0.8 * cl["W"])
            fl_m = cl["scar"] & (np.hypot(T.X - (hxy[0] + a[0] * 0.6 * cl["W"]), T.Y - (hxy[1] + a[1] * 0.6 * cl["W"]))
                                 < 0.25 * cl["W"])
            head_h = float(np.median(T.H[ring]) - np.median(T.H[fl_m])) if ring.any() and fl_m.any() else float("nan")
            wid = cl["scar"].sum() * T.cell ** 2 / max(cl["reach"] - cl["head"], T.cell)
            out.append(f"  collapse {cn}: opens toward {_bearing(a)}, ~{wid:.0f} m wide, headwall {head_h:.0f} m "
                       f"above its floor, walls median {np.median(slope[wal]) if wal.sum() > 5 else float('nan'):.0f} "
                       f"deg" + (f"; debris {cl['debris'].sum() * T.cell ** 2 / 1e4:.1f} ha of hummocks"
                                 if cl["debris"].any() else ""))
        for fn, fl in V["flows"].items():
            m = measure_flow(T, fl)
            asked = ((T.spec["volcanoes"][name].get("flows") or {}).get(fn) or {}).get("length")
            if asked and fl["length"] < 0.9 * asked:
                why = "reached the sea" if fl["delta"] > T.cell else "ran out of slope (ponded) or reached the frame's edge"
                T.warnings.append(f"flow {fn!r}: {fl['length']:.0f} m of the asked {asked:.0f} m: it {why}")
            out.append(f"  flow {fn}: {fl['length']:.0f} m long from [{fl['vent'][0]:.0f}, {fl['vent'][1]:.0f}], "
                       f"{m['width'][0]:.0f}-{m['width'][1]:.0f} m wide, stands {m['proud'][0]:.0f}-{m['proud'][1]:.0f} m "
                       f"above the ground beside it (median {m['proud_med']:.0f}), margins median {m['margin']:.0f} deg, "
                       f"front {m['front']:.0f} m high" + (f"; a lava delta {fl['delta']:.0f} m into the sea"
                                                          if fl["delta"] > T.cell else ""))
            if m["proud_med"] < 2:
                T.warnings.append(f"flow {fn!r}: it hardly stands above the ground beside it (median "
                                  f"{m['proud_med']:.1f} m): it filled a gully; thicken it for a flow that reads")
    return out


def _bearing(a):
    ang = math.degrees(math.atan2(a[0], a[1])) % 360
    return ["north", "north-east", "east", "south-east", "south", "south-west", "west", "north-west"][
        int(round(ang / 45)) % 8]


def measure_flow(T, fl):
    """Width (where the lava is on top), how far its surface stands above the ground beside it (both sides at 1.6 half
    widths, the lower), margin slopes, and the front's height, at stations along it."""
    xy, hw, m = fl["xy"], fl["hw"], fl["mask"]
    slope = T._slope()
    tan = np.gradient(xy, axis=0)
    tan /= np.linalg.norm(tan, axis=1, keepdims=True) + 1e-9
    nrm = np.c_[-tan[:, 1], tan[:, 0]]
    widths, proud = [], []
    for j in np.linspace(0.1 * len(xy), 0.9 * len(xy), 12).astype(int):
        ds = np.arange(-2.5 * hw[j], 2.5 * hw[j], T.cell / 2)
        line = xy[j] + ds[:, None] * nrm[j]
        onl = m.ravel()[_cells(T, line)]
        if onl.sum() < 2:
            continue
        widths.append(onl.sum() * T.cell / 2)
        hs = T.sample(line)
        mid = hs[np.abs(ds) < 0.3 * hw[j]]
        beside = hs[np.abs(ds) > 1.6 * hw[j]]
        if len(mid) and len(beside):
            proud.append(float(np.median(mid) - np.median(np.sort(beside)[: max(1, len(beside) // 2)])))
    edge = m & ~ndimage.binary_erosion(m, iterations=2)
    toe = xy[-1]
    ahead = toe + tan[-1] * (np.arange(0, 6 * max(hw[-1], T.cell), T.cell / 2) - 2 * hw[-1])[:, None]
    hs = T.sample(ahead)
    return {"width": (min(widths), max(widths)) if widths else (0, 0),
            "proud": (min(proud), max(proud)) if proud else (0, 0),
            "proud_med": float(np.median(proud)) if proud else 0.0,
            "margin": float(np.median(slope[edge])) if edge.sum() > 5 else float("nan"),
            "front": float(hs.max() - hs[-1])}


def _cells(T, p):
    iy = np.clip(np.round((p[:, 1] - T.ys[0]) / T.cell).astype(int), 0, len(T.ys) - 1)
    ix = np.clip(np.round((p[:, 0] - T.xs[0]) / T.cell).astype(int), 0, len(T.xs) - 1)
    return iy * len(T.xs) + ix
