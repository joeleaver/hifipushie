"""The sea and its coast: water below a level out to the frame's edge, and the shore forms where land meets it.

"sea": {"level": 0, "land": zone, "wander": 0.3, "depth": 30, "shelf": m,
        "shore": "rocky" | "beach" | "cliffs",
        "cliffs": {"height": m | [lo, hi], "except": [addresses or zones], "only": [...]},
        "beaches": {name: {"at": address, "length": m, "width": m}},
        "coves": {name: {"at": address | compass word, "width": m, "depth": m, "beach": true}}}

Where the sea is: everything outside the `land` zone (an island: {"near": [x, y], "radius": m}; a coast: "north"), or
without one, the ground below `level` connected to the frame's edge. The coastline wanders (`wander`, 0 for the zone's
own outline). Coves bite horseshoe bays into the land (a mouth narrower than the bay, headlands either side). Offshore,
the seabed shelves down to `depth` below the level over `shelf` metres.

Shore forms, per stretch of coast (the default `shore`, cliffs, and named beaches; coves with "beach" get one at their
head):
  rocky   the land as it is, dropping steeply into the water.
  beach   the land graded down to the water: sand a few metres wide at a few percent, the ground behind easing down to
          it (the sea's "beach" zone is for sand cover).
  cliffs  the land ends in a face at ~70 deg from its top down to the sea floor. Where the land at the coast is lower
          than the asked height, the land ramps up to the cliff top from inland (fading inland, never a rim with lower
          ground behind it); the report measures each stretch's height.

Everything downstream sees the sea as a lake named "sea": shore addresses ("sea.south_shore": the coast on the land's
south side), sight lines ("see": ["sea"]), sites on the shore, the export's water. Zones "sea", "beach", "cliffs"
and "coast" (a band either side of the shoreline) are available to cover and routes.
"""

from __future__ import annotations

import math

import numpy as np
from scipy import ndimage

from . import noise
from .terrain import compass, smoothstep

CLIFF = math.radians(70)
STACK_CORE = 0.45  # a stack's heightfield core: its radius x this, sheer (the solid stack in the 3D tiles is the form)


def _cliff_face(T, sd, top, level, cl):
    """A sea cliff's face as a profile seaward of its lip: risers with one or two ledges on a tall face (tiers: a face
    of one even slope from lip to water read as a draped curtain), each ledge at a height that wanders along the coast
    and pinching out in places. Returns the height below the lip at each cell and the face's run (lip to foot, m)."""
    hgt = np.maximum(top - level, 0)
    tiers = float(cl.get("tiers", 1.0))
    pts = np.c_[T.P, np.full(len(T.P), 61.0)]

    def nz(scale, seed):
        return noise.fbm(pts, scale, 2, seed=seed).reshape(T.X.shape)
    one = smoothstep(12, 18, hgt) * tiers
    two = smoothstep(28, 36, hgt) * tiers
    r = np.tan(CLIFF + math.radians(8) * one)  # risers steeper where ledges take up the run
    f1 = np.where(two > 0.5, 0.34, 0.5) + 0.14 * (nz(70.0, 301) - 0.5)
    f2 = 0.66 + 0.12 * (nz(80.0, 303) - 0.5)
    D1 = np.clip(0.15 * hgt, 2.5 * T.cell, 9.0) * smoothstep(0.36, 0.55, nz(55.0, 302)) * one
    D2 = np.clip(0.13 * hgt, 2.5 * T.cell, 8.0) * smoothstep(0.36, 0.55, nz(45.0, 304)) * two
    d = np.maximum(-sd, 0)
    z1, z2 = f1 * hgt, np.maximum(f2 * hgt, f1 * hgt + 2 * T.cell)
    d1 = z1 / r
    drop = r * d
    # a ledge falls outward a little (a dead-level shelf read as a road)
    drop = np.where(d > d1, z1 + 0.08 * np.minimum(d - d1, D1) + r * np.maximum(d - d1 - D1, 0), drop)
    d2 = d1 + D1 + (z2 - z1 - 0.08 * D1) / r
    drop = np.where((d > d2) & (two > 0.01), z2 + 0.08 * np.minimum(d - d2, D2) + r * np.maximum(d - d2 - D2, 0),
                    drop)
    run = hgt / r + D1 + np.where(two > 0.01, D2, 0) - 0.08 * (D1 + D2) / r
    return drop, np.maximum(run, 0)


def _headland_sides(T, hl, p, inl, left, w):
    """Which side(s) of a cove get a headland: +1 = left looking inland from the mouth. "auto": the side where the land
    stands higher; "left"/"right", "both", "none", a compass side or an address."""
    if hl in ("auto", None, True):
        hi_left = T.height(p + left * 0.7 * w + inl * 0.1 * w) >= T.height(p - left * 0.7 * w + inl * 0.1 * w)
        return [1.0 if hi_left else -1.0]
    if hl in ("none", False):
        return []
    if hl == "both":
        return [1.0, -1.0]
    if hl in ("left", "right"):
        return [1.0 if hl == "left" else -1.0]
    cd = compass(hl)
    if cd is None:
        cd = T.address(hl)[0] - p
    return [1.0 if float(np.dot(cd, left)) >= 0 else -1.0]


def _coast_point(T, land, ref):
    """A point on the coastline: toward a compass direction from the land's middle, or the coast nearest an address.
    Returns (xy, inland unit vector)."""
    edge = land & ndimage.binary_dilation(~land)
    pts = np.stack([T.X[edge], T.Y[edge]], 1)
    c = np.array([T.X[land].mean(), T.Y[land].mean()])
    cd = compass(ref)
    if cd is not None:
        k = int(np.argmax((pts - c) @ cd))
    else:
        xy = T.address(ref)[0]
        k = int(np.argmin(np.linalg.norm(pts - xy, axis=1)))
    p = pts[k]
    # inland: down the gradient of the distance to the sea, smoothed, at that point
    sd = ndimage.gaussian_filter(ndimage.distance_transform_edt(land), 3)
    gy, gx = np.gradient(sd)
    iy, ix = int(round((p[1] - T.ys[0]) / T.cell)), int(round((p[0] - T.xs[0]) / T.cell))
    n = np.array([gx[iy, ix], gy[iy, ix]])
    if np.linalg.norm(n) < 1e-6:
        n = c - p
    return p, n / (np.linalg.norm(n) + 1e-9)


def _signed(land, cell):
    """Signed distance to the coastline in metres: positive on land."""
    return (ndimage.distance_transform_edt(land) - ndimage.distance_transform_edt(~land)) * cell


def _near(T, refs, reach, coves=None, sd=None):
    """A 0..1 mask within `reach` of each address or inside each zone (a cove: its whole bay and mouth). An address
    inland reaches the coast nearest it: its distance to the coast plus `reach` (a headland's peak is well back from
    its own cliffs)."""
    from . import terrain_design as design
    m = np.zeros(T.X.shape)
    for a in refs or []:
        if isinstance(a, str) and coves and a in coves:
            grow = ndimage.distance_transform_edt(~coves[a]["mask"]) * T.cell
            m = np.maximum(m, smoothstep(1.3 * reach, 0.7 * reach, grow))
            continue
        if isinstance(a, str) and (a in T.zones or a.startswith("quadrant:") or a in getattr(T, "vzones", {})) \
                or isinstance(a, dict):
            m = np.maximum(m, design.region(T, a))
            continue
        xy = T.address(a)[0]
        r = reach
        if sd is not None:
            iy = int(np.clip(round((xy[1] - T.ys[0]) / T.cell), 0, len(T.ys) - 1))
            ix = int(np.clip(round((xy[0] - T.xs[0]) / T.cell), 0, len(T.xs) - 1))
            r = reach + abs(float(sd[iy, ix]))
        m = np.maximum(m, smoothstep(1.3 * r, 0.7 * r, np.hypot(T.X - xy[0], T.Y - xy[1])))
    return m


def apply(T):
    S = T.spec.get("sea")
    T.sea = None
    if not S:
        return
    from . import terrain_design as design
    level = float(S.get("level", 0.0))
    k = T.k
    if "land" in S:
        land = design.region(T, S["land"]) > 0.5
    else:
        below = T.H < level
        lab, _ = ndimage.label(below)
        edge_ids = np.unique(np.r_[lab[0], lab[-1], lab[:, 0], lab[:, -1]])
        land = ~np.isin(lab, edge_ids[edge_ids > 0])
    if not land.any() or land.all():
        # (with the numbers: the first designer to meet this did the tilt's arithmetic by hand)
        H = T.H
        ed = {"north": H[-1], "south": H[0], "west": H[:, 0], "east": H[:, -1]}
        lows = ", ".join(f"{nm} {float(np.nanmin(e)):+.0f} m" for nm, e in ed.items())
        raise ValueError(f"sea: there's no coast (the land is {'everywhere' if land.all() else 'nowhere'}): the sea is "
                         f"at {level:g} m and the ground runs {float(np.nanmin(H)):+.0f} to {float(np.nanmax(H)):+.0f} m, "
                         f"lowest on each edge: {lows}. Give \"land\" a zone, or leave ground below the level reaching "
                         "the frame's edge (lower world.base, or tilt more steeply: the tilt pivots on the frame's "
                         "middle, so an edge drops by grade x half the frame)")
    # the coastline wanders: headlands and bights a few hundred metres apart (a zone's circle read as a compass drawing)
    # the coastline is a continuous field (signed distance), never re-cut from cells: a coast rethresholded to cells
    # built its cliffs as a staircase of blocks
    sd = ndimage.gaussian_filter(_signed(land, T.cell), 2.0)
    wander = float(S.get("wander", 0.3))
    if wander:
        pts = np.c_[T.P, np.full(len(T.P), 11.0)]
        n = noise.fbm(pts, max(0.05 * T.size, 120 * k), 3, seed=121).reshape(T.X.shape) - 0.5
        sd = sd + wander * 2 * n * max(0.03 * T.size, 60 * k)
    land = sd > 0
    # coves: bays wider inside than at the mouth, asymmetric: a rocky headland on one side running out past the mouth
    # (it narrows the mouth and shelters the bay), the bay swinging away from it, a beach at the head, the other side
    # lower. (A symmetric ellipse read as a round pond with low rims.)
    coves = {}
    raise_h = np.zeros(T.X.shape)  # headlands stand higher than the land about them
    head_m = np.zeros(T.X.shape)  # cliffs round each headland
    for name, cv in (S.get("coves") or {}).items():
        p, inl = _coast_point(T, land, cv.get("at", "south"))
        left = np.array([-inl[1], inl[0]])
        w, dp = float(cv.get("width", 0.08 * T.size)), float(cv.get("depth", 0.07 * T.size))
        sides = _headland_sides(T, cv.get("headland", "auto"), p, inl, left, w)
        hs = sides[0] if len(sides) == 1 else 0.0
        a = 0.6 * dp  # along the inland axis; centred so the coastline crosses it at ~2/3 of the bay's width
        c = p + inl * (dp - a) - left * hs * 0.12 * w  # (the bay swings away from its headland)
        v = np.stack([T.X - c[0], T.Y - c[1]], -1)
        u, sa = v @ inl, v @ left
        # the head is pushed further from the headland than the mouth (a hooked, zeta-shaped bay)
        sa = sa + hs * 0.18 * w * np.clip(u / a, -1, 1)
        half = np.where(sa * hs > 0, 0.42 * w, 0.58 * w) if hs else np.full(T.X.shape, 0.5 * w)
        lob = noise.fbm(np.c_[T.P, np.full(len(T.P), 13.0)], 0.5 * w, 2, seed=131 + len(coves)).reshape(T.X.shape) - 0.5
        q = (u / a) ** 2 + (sa / half) ** 2 + 0.25 * lob
        bay = q < 1.0
        sd = np.minimum(sd, (np.sqrt(np.maximum(q, 0)) - 1) * np.minimum(a, half))  # ~ distance outside the bay
        heads = []
        points = [(side, True) for side in sides] + ([(-hs, False)] if len(sides) == 1 else [])
        for side, major in points:
            # the headland: a tapering point from the bay's shoulder out past the mouth, hooking a little across it; the
            # other side gets a low rocky point (so the mouth is narrower than the bay on both sides)
            L = float(cv.get("headland_length", 0.55 * w)) * (1.0 if major else 0.6)
            b0 = p + left * side * (0.45 if major else 0.52) * w + inl * 0.1 * dp
            for _ in range(40):  # seated on the land (where the coast falls away beside the mouth, it stood at sea)
                iy = int(np.clip(round((b0[1] - T.ys[0]) / T.cell), 0, len(T.ys) - 1))
                ix = int(np.clip(round((b0[0] - T.xs[0]) / T.cell), 0, len(T.xs) - 1))
                if sd[iy, ix] > 0.05 * w:
                    break
                b0 = b0 + inl * 0.05 * w
            tip = b0 - inl * L - left * side * (0.22 if major else 0.12) * w
            seg = tip - b0
            t = np.clip(((T.X - b0[0]) * seg[0] + (T.Y - b0[1]) * seg[1]) / (seg @ seg), 0, 1)
            dl = np.hypot(T.X - (b0[0] + t * seg[0]), T.Y - (b0[1] + t * seg[1]))
            rad = (0.24 - 0.12 * t) * w * (1.0 if major else 0.6)
            wig = noise.fbm(np.c_[T.P, np.full(len(T.P), 17.0 + len(heads))], 0.2 * w, 2,
                            seed=141 + len(coves)).reshape(T.X.shape) - 0.5
            sdh = rad * (1 + 0.5 * wig) - dl
            sd = np.maximum(sd, np.where(q > 1.0, sdh, sd))  # (never into the bay)
            if not major:
                heads.append({"base": b0.tolist(), "tip": tip.tolist(), "height": None, "side": side})
                continue
            # its top: higher than the land behind, highest a little short of its tip (a point, not a ramp)
            hh = float(cv.get("headland_height", max(18.0, 0.22 * w)))
            ground = T.height(b0 + inl * 0.2 * w)
            crest = level + hh * (0.55 + 0.45 * np.sin(np.pi * np.clip(0.2 + 0.8 * t, 0, 1)))
            prof = np.clip(sdh / np.maximum(rad, 1e-6), 0, 1) ** 0.6
            raise_h = np.maximum(raise_h, np.where(sdh > 0, np.maximum(crest * prof + ground * (1 - prof), ground), 0))
            head_m = np.maximum(head_m, smoothstep(0.35 * w, 0.1 * w, -sdh) * (dl < rad + 0.4 * w))
            heads.append({"base": b0.tolist(), "tip": tip.tolist(), "height": hh, "side": side})
        # the cove sits in a hollow: the land round the bay (not its headland) eases down to a low rim a little over the
        # water (on a 55 m plateau every cove had been a pit ringed by 60 m walls, the "low point" as high as the rest)
        # (a cove without a beach is a cliffed inlet: no hollow unless asked; the hollow reaches 1.5 widths)
        rim = float(cv.get("rim", float(np.clip(0.1 * w, 4.0, 18.0)) if cv.get("beach", True) else -1.0))
        if rim >= 0:
            d_b = ndimage.distance_transform_edt(~bay) * T.cell
            low = level + rim + math.tan(math.radians(float(cv.get("rim_slope", 16)))) * d_b
            spare = np.zeros(T.X.shape, bool)
            for hd in heads:
                if hd["height"] is None:
                    continue
                b0, tip = np.array(hd["base"]), np.array(hd["tip"])
                seg = tip - b0
                t = np.clip(((T.X - b0[0]) * seg[0] + (T.Y - b0[1]) * seg[1]) / (seg @ seg), 0, 1)
                spare |= np.hypot(T.X - (b0[0] + t * seg[0]), T.Y - (b0[1] + t * seg[1])) < 0.3 * w
            fade = smoothstep(0, 0.2 * w, ndimage.distance_transform_edt(~spare) * T.cell) if spare.any() else 1.0
            # only the gentle land round it, and never more than a few tens of metres (on a volcano's collapse the
            # hollow had cut the amphitheatre walls 300 m down): designed slopes keep their form
            gy_, gx_ = np.gradient(ndimage.gaussian_filter(T.H, max(1.0, 10.0 / T.cell)), T.cell)
            gentle = smoothstep(22, 12, np.degrees(np.arctan(np.hypot(gx_, gy_))))
            cap = float(cv.get("rim_depth", np.clip(0.1 * w, 6.0, 25.0)))
            cut = np.minimum(np.clip(T.H - low, 0, None), cap) * fade * gentle * smoothstep(1.5 * w, 1.0 * w, d_b)
            T.H = T.H - ndimage.gaussian_filter(cut, max(1.0, 0.03 * w / T.cell))
        land = sd > 0
        head = c + inl * a + left * hs * 0.18 * w  # the bay's head, for its beach
        coves[name] = {"xy": c.tolist(), "mouth": p.tolist(), "head": head.tolist(), "inland": inl.tolist(),
                       "width": w, "depth": dp, "mask": bay, "headlands": heads}
    if raise_h.any():
        T.H = np.where((raise_h > T.H) & (sd > 0), raise_h, T.H)
    sd = ndimage.gaussian_filter(sd, 1.0)
    land = sd > 0
    # geos (zawns): narrow clefts cut back into a cliff coast, the sea running up them between vertical walls (a cliff
    # line with no inlets read as a sea wall with a ruler-straight top)
    cl0 = S.get("cliffs") or {}

    def cut_geo(p, inl, L, w):
        v = np.stack([T.X - p[0], T.Y - p[1]], -1)
        along, across = v @ inl, v @ np.array([-inl[1], inl[0]])
        t = np.clip(along / L, 0, 1)
        half = w / 2 * (1 - 0.6 * t) * (1 + 0.3 * np.sin(along / (0.3 * L + 1)))  # narrowing, a little kinked
        return np.where((along > -2 * T.cell) & (along < L), np.abs(across) - half, np.inf)

    geos = {}
    geo_mask = np.zeros(T.X.shape, bool)
    if isinstance(cl0.get("geos"), dict):  # placed: {name: {"at": address, "length": m, "width": m}}
        for gname, g in cl0["geos"].items():
            p, inl = _coast_point(T, land, g.get("at", "south"))
            L, w = float(g.get("length", 60.0)), max(1.5 * T.cell, float(g.get("width", 8.0)))
            cg = cut_geo(p - inl * 2 * T.cell, inl, L + 2 * T.cell, w)
            geo_mask |= cg < 0
            sd = np.minimum(sd, cg)
            geos[gname] = {"xy": p.tolist(), "inland": inl.tolist(), "length": L, "width": w,
                           "head": (p + inl * L).tolist()}
        land = sd > 0
    elif (S.get("shore") == "cliffs" or "cliffs" in S) and cl0.get("geos", 1):
        edge = land & ndimage.binary_dilation(~land)
        ey, ex = np.nonzero(edge)
        if len(ey):
            n_geo = int(cl0.get("geos")) if not isinstance(cl0.get("geos"), bool) and cl0.get("geos") is not None \
                else min(14, int(len(ey) * T.cell / 180))
            rng_g = np.random.default_rng(181)
            avoid = _near(T, cl0.get("except", []), 150 * k, coves, sd) if cl0.get("except") else 0 * sd
            if cl0.get("only") and S.get("shore") != "cliffs":  # cliffs only on some stretches: geos only there too
                avoid = np.maximum(avoid, 1 - _near(T, cl0["only"], 150 * k, coves, sd))  # (they cut 60 m slots into
                # a 6 m rocky shore elsewhere)
            gy_, gx_ = np.gradient(ndimage.gaussian_filter(sd, 3))
            done = []
            for j in rng_g.permutation(len(ey)):
                if len(done) >= n_geo:
                    break
                y, x = ey[j], ex[j]
                p = np.array([T.X[y, x], T.Y[y, x]])
                if avoid[y, x] > 0.3 or any(np.linalg.norm(p - q) < 90 * k + 10 * T.cell for q in done) or \
                        any(cv["mask"][max(y - 3, 0):y + 4, max(x - 3, 0):x + 4].any() for cv in coves.values()):
                    continue
                inl = np.array([gx_[y, x], gy_[y, x]])
                inl /= np.linalg.norm(inl) + 1e-9
                L = rng_g.uniform(25, 110) * max(k, 0.5) + 4 * T.cell
                w = max(1.5 * T.cell, rng_g.uniform(4, 12))
                cg = cut_geo(p, inl, L, 2 * w)
                geo_mask |= cg < 0
                sd = np.minimum(sd, cg)
                done.append(p)
            land = sd > 0

    # which form each stretch of coast takes: spread from the coastline along each cell's nearest coast point
    coast = land & ndimage.binary_dilation(~land)
    _, (cy, cx) = ndimage.distance_transform_edt(~coast, return_indices=True)
    shore = S.get("shore", "rocky")
    cl = S.get("cliffs") or {}
    wc = np.full(T.X.shape, 1.0 if shore == "cliffs" or ("cliffs" in S and "only" not in cl) else 0.0)
    if cl.get("only"):
        wc = np.maximum(wc, _near(T, cl["only"], 150 * k, coves, sd))
    if cl.get("except"):
        wc = np.minimum(wc, 1 - _near(T, cl["except"], 150 * k, coves, sd))
    wb = np.zeros(T.X.shape)  # named beaches (and coves' beaches): these win over a cliff coast
    beaches = dict(S.get("beaches") or {})
    for name, cv in coves.items():
        if (S.get("coves") or {})[name].get("beach", True):
            beaches[f"{name}_beach"] = {"at": cv["head"], "length": 0.8 * cv["width"]}
    foot = np.zeros(T.X.shape)  # beaches at the foot of the cliffs: the cliff stays, sand lies below it
    foot_w = []
    beach_at = {}
    for name, b in beaches.items():
        L = float(b.get("length", 150 * k))
        xy = T.address(b["at"])[0]
        cpts = np.stack([T.X[coast], T.Y[coast]], 1)  # on the coast nearest the address (an inland point missed it)
        xy = cpts[int(np.argmin(np.linalg.norm(cpts - xy, axis=1)))]
        beach_at[name] = xy.tolist()
        m = smoothstep(0.6 * L, 0.4 * L, np.hypot(T.X - xy[0], T.Y - xy[1]))
        if b.get("at_foot"):
            foot = np.maximum(foot, m)
            foot_w.append((m, float(b.get("width", 35.0))))
        else:
            wb = np.maximum(wb, m)
    # smooth the choice along the coast, then carry it inland and offshore from each cell's nearest coast point
    smooth = max(1.5, 40 * k / T.cell)
    wc_c = ndimage.gaussian_filter(np.where(coast, wc, 0.0), smooth) / np.maximum(
        ndimage.gaussian_filter(coast.astype(float), smooth), 1e-6)
    wb_c = ndimage.gaussian_filter(np.where(coast, wb, 0.0), smooth) / np.maximum(
        ndimage.gaussian_filter(coast.astype(float), smooth), 1e-6)
    wc, wb = np.clip(wc_c[cy, cx], 0, 1), np.clip(wb_c[cy, cx], 0, 1)
    if foot.any():
        foot_c = ndimage.gaussian_filter(np.where(coast, foot, 0.0), smooth) / np.maximum(
            ndimage.gaussian_filter(coast.astype(float), smooth), 1e-6)
        foot = np.clip(foot_c[cy, cx], 0, 1)
        wc = np.maximum(wc, foot)  # the cliff stands behind its foot beach
    wc = np.minimum(wc, 1 - wb)
    if head_m.any():  # a cove's headland ends in cliffs whatever the shore elsewhere
        head_c = ndimage.gaussian_filter(np.where(coast, head_m, 0.0), smooth) / np.maximum(
            ndimage.gaussian_filter(coast.astype(float), smooth), 1e-6)
        wc = np.maximum(wc, np.clip(1.6 * head_c[cy, cx], 0, 1) * (1 - wb))
    if shore == "beach":  # a beach coast: wherever it isn't cliffs
        wb = np.maximum(wb, 1 - wc)

    H = T.H
    depth = float(S.get("depth", 30.0 * max(k, 0.25)))
    shelf = float(S.get("shelf", max(0.08 * T.size, 10 * depth)))
    # cliffs: the land's top at the coast, at least the asked height (the land ramps up to it from inland)
    ch = cl.get("height", 30.0 * max(k, 0.3))
    lo_h, hi_h = (ch, ch) if isinstance(ch, (int, float)) else ch
    # a cliff coast juts and bays at tens of metres (headlands, bights, buttresses): its line moved in and out in plan,
    # so the lip and the foot move together (a cliff line smooth at that scale read as a long even wall)
    jut = float(cl.get("jut", 1.0))
    if jut > 0 and (wc > 0.5).any():
        A = jut * float(np.clip(0.8 * hi_h, 3.0, 30.0))
        pts = np.c_[T.P, np.full(len(T.P), 41.0)]
        big = noise.fbm(pts, max(3 * A, 25.0), 3, seed=191).reshape(T.X.shape) - 0.5
        rib = 1 - np.abs(2 * noise.fbm(pts, max(1.2 * A, 10.0), 2, seed=192).reshape(T.X.shape) - 1)  # sharp ribs
        wob = A * (1.6 * big + 0.5 * (rib - 0.5))
        near = smoothstep(3 * A + 4 * T.cell, A, np.abs(sd))  # only about the coastline
        if geo_mask.any():  # (not across a geo: the wobble closed a 7 m cleft)
            near = near * (1 - np.clip(ndimage.gaussian_filter(geo_mask.astype(float), 3.0) * 3, 0, 1))
        sd = sd + wc * near * wob
        land = sd > 0
        coast = land & ndimage.binary_dilation(~land)
        _, (cy, cx) = ndimage.distance_transform_edt(~coast, return_indices=True)
    sea_floor = level - 1.0 - (depth - 1.0) * smoothstep(0, shelf, -sd)
    var = noise.fbm(np.c_[T.P, np.full(len(T.P), 17.0)], max(0.06 * T.size, 150 * k), 2, seed=141).reshape(T.X.shape)
    want = level + lo_h + (hi_h - lo_h) * np.clip(1.6 * (var - 0.5) + 0.5, 0, 1)
    for ref, hv in (cl.get("heights") or {}).items():  # per stretch: {zone or address: m | [lo, hi]}
        lo2, hi2 = (hv, hv) if isinstance(hv, (int, float)) else hv
        m = _near(T, [ref], 150 * k, coves, sd)
        want = want * (1 - m) + (level + lo2 + (hi2 - lo2) * np.clip(1.6 * (var - 0.5) + 0.5, 0, 1)) * m
    # the cliff top at each cell's nearest coast point, smoothed along the coast (cell to cell it made a sawtooth crown)
    top_c = ndimage.gaussian_filter(np.where(coast, np.maximum(H, want), 0.0), smooth) / np.maximum(
        ndimage.gaussian_filter(coast.astype(float), smooth), 1e-6)
    top_here = top_c[cy, cx]
    ramp = float(cl.get("ramp", 0.12))  # how the land climbs to meet a raised cliff top: fades inland at this grade
    raised = np.maximum(H, top_here - ramp * np.maximum(sd, 0))
    # the lip rolls over (slope-over-wall): the top falls a little toward the edge before the face (a knife-edge lip
    # read as a sawn block)
    # (the roll-over wanders along the coast: one even bevel read as a ruled lip)
    lipn = noise.fbm(np.c_[T.P, np.full(len(T.P), 43.0)], max(0.6 * hi_h, 8.0), 2, seed=193).reshape(T.X.shape)
    bev_h = float(cl.get("bevel", 0.12)) * np.maximum(top_here - level, 0) * np.clip(0.2 + 1.8 * lipn, 0.1, 1.8)
    bev_w = np.maximum(3 * bev_h, 2 * T.cell)
    raised = raised - bev_h * smoothstep(bev_w, 0, np.maximum(sd, 0)) ** 1.5
    drop, face_run = _cliff_face(T, sd, top_here, level, cl)
    cliff_face = (top_here - bev_h) - drop
    # beaches: sand from just under the level to a couple of metres up over `width`, the land behind easing down
    bw = float(S.get("beach_width", 30 * max(k, 0.5)))
    back = float(S.get("backshore", 4 * bw))
    beach = level - 0.6 + np.maximum(sd, -3 * bw) * (2.6 / bw)
    beach_land = np.where(sd < bw, beach, H * smoothstep(bw, bw + back, sd) + (beach) * (1 - smoothstep(bw, bw + back, sd)))
    # rocky: the land as it is, kept dry at the shore, dropping into the water
    # (kept dry a few cells in from the shore only: uncapped, 0.2 * sd raised ground 400 m inland to 80 m)
    rocky = np.where(sd > 0, np.maximum(H, level + 0.4 + 0.2 * np.minimum(sd, 3 * T.cell)), np.minimum(H, level - 0.8 + 0.8 * sd))
    # low rocks: the land eased down to a metre or so above the water, ending in a strip of boulders at the waterline
    # (grass running down to the rocks; a beach grading left sand, a rocky shore a drop)
    wr = np.clip(1 - wc - wb, 0, 1) if shore in ("rocks", "low rocks", "rocky_low") else np.zeros(T.X.shape)
    rw = float(S.get("rocks_width", 6.0))
    rback = float(S.get("backshore", 4 * bw))
    rock_top = level + 0.3 + np.clip(sd, 0, rw) * (1.2 / rw)
    ease = smoothstep(rw, rw + rback, sd)
    rock_land = np.where(sd < rw, rock_top, H * ease + (level + 1.5) * (1 - ease))
    rock_land = np.where(H < rock_land, np.maximum(H, level + 0.3), rock_land)  # (graded down, never raised)
    rock_off = np.minimum(np.maximum(level - 0.3 + sd * (0.8 / rw), sea_floor), level - 0.3)
    onshore = wc * raised + wb * beach_land + wr * rock_land + np.clip(1 - wc - wb - wr, 0, 1) * rocky
    # offshore of a cliff its face stands in the water, from the top down to the sea floor (clamping the first cells
    # offshore under the water had made every cliff a plumb wall at the coastline)
    below = np.minimum(sea_floor, np.where(sd > -3 * T.cell, level - 0.3, np.inf))
    offshore = wc * np.maximum(cliff_face, sea_floor) + wb * np.minimum(np.maximum(beach, sea_floor), level - 0.6) \
        + wr * rock_off + np.clip(1 - wc - wb - wr, 0, 1) * below
    # beaches at the foot of cliffs: a strip of sand below the face, the cliff standing behind it
    if foot.any():
        run = face_run
        fw = np.full(T.X.shape, 35.0)
        for m, w in foot_w:
            fw = np.where(m > 0.3, w, fw)
        x = (-sd - run) / fw  # 0 at the face's foot, 1 at the sand's seaward edge
        # dry sand most of the way out (1.8 -> 1.0 m), then shelving into the water
        sand = np.where(x < 0.75, level + 1.8 - 1.07 * x, level + 1.0 - 7.0 * (x - 0.75))
        offshore = np.where(foot > 0.5, np.where(x < 0, np.maximum(cliff_face, sand), np.maximum(sand, sea_floor)),
                            offshore)
    new = np.where(sd > 0, onshore, offshore)
    rocks_band = np.zeros(T.X.shape)
    if wr.max() > 0.05:  # boulders along the low-rock strip, from a little offshore to the grass's edge
        from .terrain_rock import facets
        lumps = noise.fbm(np.c_[T.P, np.full(len(T.P), 51.0)], max(1.2, 1.2 * T.cell), 2, seed=201).reshape(T.X.shape)
        blocky, _ = facets(T, lumps, max(2.0, 2.5 * T.cell), tilt=0.35, seed=202, crease=0.05)
        rocks_band = wr * smoothstep(-1.5 * rw, -0.5 * rw, sd) * smoothstep(1.1 * rw, 0.6 * rw, sd)
        bould = np.clip((blocky - 0.42) / 0.3, 0, 1) * 1.4  # blocks up to ~1.4 m, gaps of shingle between
        new = new + rocks_band * bould
    # a cove's head: a gentle apron behind its beach (the floor of the old collapse, room for a harbour), walled by the
    # scar where it meets higher ground; only ever cut down, and only inland of the head
    for name, cv in coves.items():
        ap = float((S.get("coves") or {})[name].get("apron", 0.35 * cv["width"]))
        if ap <= 0:
            continue
        hd, inl = np.array(cv["head"]), np.array(cv["inland"])
        dist = np.hypot(T.X - hd[0], T.Y - hd[1])
        ahead = (T.X - hd[0]) * inl[0] + (T.Y - hd[1]) * inl[1] > -0.5 * cv["width"]
        floor = level + 1.5 + 0.05 * dist
        # a headwall steeper than any flank, so it meets the ground within a short run (at 38 deg it ran up a 28 deg
        # cone to the summit)
        scar = floor + math.tan(math.radians(62)) * np.maximum(dist - ap, 0)
        opening = (S.get("coves") or {})[name].get("valley")
        if opening:  # the drowned mouth of a valley: the scar opens toward it, a road can come down (10%)
            tgt = T.address(opening)[0] if not (isinstance(opening, str) and opening in T.lines) else None
            line = T.lines[opening].xy if tgt is None else np.linspace(hd, tgt, 50)
            from scipy.spatial import cKDTree
            dl = cKDTree(line).query(T.P)[0].reshape(T.X.shape)
            half = 0.25 * cv["width"]
            gentle = floor + 0.10 * np.maximum(dist - ap, 0)
            # only near the cove: the apron and a headwall's run beyond it (aimed at a crater's rim, it cut a trench
            # all the way up and breached the rim)
            reach = ap + 1.5 * cv["width"]
            open_w = smoothstep(2 * half, half, dl) * smoothstep(reach, 0.8 * reach, dist)
            scar = scar * (1 - open_w) + np.maximum(gentle, scar * 0 + gentle) * open_w
        new = np.where((sd > 0) & ahead, np.minimum(new, scar), new)
        cv["apron"] = ap
    # below the cliffs: a wave-cut platform (rocks awash, a band out from the face's foot), and sea stacks standing off
    # the face (a smooth wall straight into deep water read as a dam)
    run = face_run
    out_of_foot = -sd - run  # metres seaward of the face's foot
    pw = float(cl.get("platform", max(3 * T.cell, 25 * k)))
    stacks = []
    st_mask = np.zeros(T.X.shape, bool)
    if pw > 0:
        rocks = noise.fbm(np.c_[T.P, np.full(len(T.P), 19.0)], 1.6 * T.cell, 3, seed=151).reshape(T.X.shape)
        fade = smoothstep(pw, 0.3 * pw, out_of_foot) * (out_of_foot > -T.cell)
        plat = level - 1.2 + 2.2 * rocks - 0.8 * np.clip(out_of_foot / pw, 0, 1)
        new = np.where((sd < 0) & (wc > 0.5) & (foot < 0.5), np.maximum(new, np.where(fade > 0, plat * fade + new * (1 - fade), new)), new)
    by, bx = np.nonzero(coast & (wc > 0.5) & (foot < 0.5))
    st_cfg = cl.get("stacks")
    st_at = st_cfg.get("at") if isinstance(st_cfg, dict) else None
    if isinstance(st_cfg, dict):
        n_st = int(st_cfg.get("count", 4))
    else:
        n_st = int(st_cfg if st_cfg is not None else min(8, int(len(by) * T.cell / 350))) if len(by) else 0
    if n_st > 0 and len(by):
        rng = np.random.default_rng(161)
        gy, gx = np.gradient(sd)  # the sea side of the coast: down the signed distance's gradient

        def seaward(y, x):
            v = -np.array([gx[y, x], gy[y, x]])
            return v / (np.linalg.norm(v) + 1e-9)

        places = []  # (xy of the stack's centre, the coast's top there, radius, height)
        if st_at is not None:  # a string of stacks off one point (a headland's tip), smaller further out
            xy = T.address(st_at)[0]
            j = int(np.argmin(np.hypot(T.X[by, bx] - xy[0], T.Y[by, bx] - xy[1])))
            y, x = by[j], bx[j]
            p, nrm = np.array([T.X[y, x], T.Y[y, x]]), seaward(y, x)
            side = np.array([-nrm[1], nrm[0]])
            top = float(top_here[y, x])
            out = float(run[y, x])
            for i in range(n_st):
                shrink = 0.8 ** i  # (smaller further out, height and girth: 1.0, 0.8, 0.64...; 0.9x read as a row of equals)
                r = max(2 * T.cell, rng.uniform(0.15, 0.28) * (top - level) * (0.6 + 0.4 * shrink))
                hg = (top - level) * rng.uniform(0.7, 0.95) * shrink
                skirt = hg / math.tan(math.radians(76))  # (its sides spread this far at the waterline)
                out += (2.0 if i == 0 else rng.uniform(1.6, 3.0)) * r + skirt  # (clear water between, uneven)
                c = p + nrm * out + side * rng.uniform(-0.8, 0.8) * r
                places.append((c, top, r, hg))
                out += r + skirt
        else:  # along the cliff coast, mostly off headlands (the land's convex bits), never crowded
            lap = ndimage.laplace(ndimage.gaussian_filter(sd, max(2.0, 60 * k / T.cell)))[by, bx]
            w = np.clip(-lap, 0, None) + 0.15 * np.abs(lap).mean() + 1e-9
            pick = rng.choice(len(by), size=min(n_st * 8, len(by)), replace=False, p=w / w.sum())
            for j in pick:
                if len(places) >= n_st:
                    break
                y, x = by[j], bx[j]
                p = np.array([T.X[y, x], T.Y[y, x]])
                if any(np.linalg.norm(p - c0) < 120 * k + 8 * T.cell for c0, *_ in places):
                    continue
                top = float(top_here[y, x])
                r = max(2 * T.cell, rng.uniform(0.15, 0.35) * (top - level))
                c = p + seaward(y, x) * (float(run[y, x]) + rng.uniform(1.2, 3.0) * r)
                places.append((c, top, r, (top - level) * rng.uniform(0.45, 0.95)))
        places = [pl for pl in places if pl[3] >= 2.0]  # (a "stack" under 2 m is a rock awash, not a stack)
        for c, top, r, hgt in places:
            # a stack is a broken pillar, not a turned one (smooth cylinders read as chimneys): a lobed, grooved outline,
            # sides stepping in as it rises, a tilted and notched top
            i_st = len(stacks)
            dx, dy = T.X - c[0], T.Y - c[1]
            d = np.hypot(dx, dy)
            th = np.arctan2(dy, dx)
            lob = noise.fbm(np.c_[T.P, np.full(len(T.P), 23.0 + i_st)], 0.7 * r, 3, seed=171 + i_st).reshape(T.X.shape)
            k_g = int(rng.integers(5, 9))
            grooves = 0.12 * np.cos(k_g * th + rng.uniform(0, 6.3)) + 0.06 * np.cos((k_g + 3) * th + rng.uniform(0, 6.3))
            d = d * (1 + 0.5 * (lob - 0.5) + grooves)
            tilt = rng.uniform(0.1, 0.35) * hgt / r
            tdir = rng.uniform(0, 2 * math.pi)
            top_z = level + hgt - tilt * np.clip(dx * math.cos(tdir) + dy * math.sin(tdir) + r, 0, 2 * r) * 0.5 \
                - 0.12 * hgt * np.clip(lob - 0.6, 0, None) / 0.4
            # a slim core with sheer sides: the 3D tiles stand a solid, layered, undercut stack over it
            # (terrain_mesh.Stack), which must hold the heightfield's stack inside (a wide 76 deg skirt made a fat foot
            # no undercut could cut into); ledges are the solid stack's beds
            core = STACK_CORE * r
            side = level + hgt - (d - core) * math.tan(math.radians(84))
            st = np.where(d < core, top_z, side)
            st = np.minimum(st, top_z)
            ok = (sd < 0) & (st > new)
            st_mask |= (sd < 0) & (d < 2.5 * r)
            new = np.where(ok, st, new)
            T.hard |= ok & (st > level)
            stacks.append({"xy": c.tolist(), "height": hgt, "radius": r})
    # talus: aprons of fallen blocks leaning on the cliff's foot, in patches, awash (a face straight into clean water
    # read as a dam wall)
    tal = float(cl.get("talus", 1.0))
    if tal > 0 and (wc > 0.5).any():
        from .terrain_rock import facets
        hgt = np.maximum(top_here - level, 0)
        run = face_run
        oof = -sd - run  # metres seaward of the face's foot
        aw = 0.5 * hgt + 2 * T.cell
        patch = smoothstep(0.42, 0.58, noise.fbm(np.c_[T.P, np.full(len(T.P), 47.0)], max(2.5 * hi_h, 25.0), 2,
                                                  seed=197).reshape(T.X.shape))
        lumps = noise.fbm(np.c_[T.P, np.full(len(T.P), 49.0)], max(1.5, 1.5 * T.cell), 2, seed=198).reshape(T.X.shape)
        blocky, _ = facets(T, lumps, max(3.0, 3 * T.cell), tilt=0.08, seed=199, crease=0.08)
        fan = np.clip(1 - np.maximum(oof, 0) / aw, 0, 1) ** 1.3
        # a fan leaning on the foot, its surface blocks a metre or two (steep random facets at this size made spikes)
        apron = level - 0.8 + tal * patch * (0.3 * hgt * fan + np.minimum(0.06 * hgt, 1.5) * (blocky - 0.5) * 2 * (fan > 0))
        on = (sd < 0) & (wc > 0.5) & (foot < 0.5) & (oof > -run) & (fan > 0)
        new = np.where(on, np.maximum(new, apron), new)
        T.hard |= on & (apron > level)
        st_mask |= on & (patch > 0.05)  # (the fine re-cut leaves it, like the stacks)
    cliffish = (wc > 0.5) | (foot > 0.5)  # (a cliff's face and its foot's sand stand offshore of the coastline)
    new = np.where(sd > 0, np.maximum(new, level + 0.3), np.where(cliffish, new, np.minimum(new, level - 0.3)))
    # a geo is the sea running up a cleft: its floor under water all the way to its head (the face formula measured from
    # its walls, then the platform and talus, left a 7 m geo's floor 3-6 m up: a dry trench hanging in the cliff)
    if geo_mask.any():
        gfloor = level - 1.0 - 2.0 * smoothstep(0, 4 * T.cell, -sd)
        new = np.where(geo_mask & (sd < 0), np.minimum(new, gfloor), new)
    T.H = new
    face = (sd < 0) & (sd > -((hi_h + depth) / math.tan(CLIFF) + 2 * T.cell)) & (wc > 0.5)
    T.hard |= face
    T.hardness = np.where(face, np.minimum(T.hardness, 0.05), T.hardness)
    T.sea = {"level": level, "land": land, "sd": sd, "wc": wc, "wb": wb, "foot": foot, "coves": coves, "want": want,
             "top": top_here, "bev_h": bev_h, "run": face_run, "bev_w": bev_w, "st_mask": st_mask,
             "beach_at": beach_at, "stacks": stacks, "geos": geos,
             "cliff_asked": (lo_h, hi_h), "beach_width": bw, "beaches": list(beaches), "rocks": rocks_band}
    T.masks.setdefault("coast", np.zeros(T.X.shape))
    T.masks["coast"] = np.maximum(T.masks["coast"], smoothstep(4 * T.cell, 0, np.abs(sd)))
    far = np.unravel_index(np.argmin(sd), sd.shape)  # the open sea: furthest from any land (a ring's mean is its hole)
    lk = {"xy": [float(T.X[far]), float(T.Y[far])], "level": level, "r": T.size,
          "id": len(T.lakes) + 1, "sea": True}
    T.lakes["sea"] = lk


def recut(T):
    """On a finer grid (terrain_detail): cut the cliffs again from their signed distance, so the face is a plane at the
    cliff's angle from its lip down to the water (resampled, it was the coarse grid's drape: a face 2 cells across
    became 4 soft ones) and the lip stands at its top. Stacks, foot beaches, routes and sites are left as they are."""
    S = getattr(T, "sea", None)
    if not S or not (S["wc"] > 0.5).any():
        return
    keep = np.zeros(T.X.shape, bool)
    for k in ("routes", "sites"):
        if k in T.masks:
            keep |= T.masks[k] > 0.05
    sd, level = S["sd"], S["level"]
    cliff = (S["wc"] > 0.5) & (S["foot"] < 0.5) & ~S["st_mask"] & ~keep
    face = (S["top"] - S["bev_h"]) - _cliff_face(T, sd, S["top"], level, T.spec["sea"].get("cliffs") or {})[0]
    H = T.H
    off = cliff & (sd < 0) & (face > level + 0.3)
    H = np.where(off, np.minimum(H, face), H)
    coarse = T.detail["cell"]
    lip = S["top"] - S["bev_h"] * smoothstep(S["bev_w"], 0, np.maximum(sd, 0)) ** 1.5
    on = cliff & (sd >= 0) & (sd < 1.5 * coarse)
    T.H = np.where(on, np.maximum(H, lip), H)


def cliff_feet(T, spacing=15.0):
    """Points along the foot of the sea cliffs, for placing things against the face (sea caves and notches as 3D
    volumes): [{"xy": foot [x, y], "z": the water level, "out": seaward unit [x, y], "height": cliff height m,
    "lip": [x, y] of the lip above}], every `spacing` metres along the cliff coast, stacks and talus left out."""
    S = getattr(T, "sea", None)
    if not S or not (S["wc"] > 0.5).any():
        return []
    sd, level = S["sd"], S["level"]
    land = sd > 0
    coast = land & ndimage.binary_dilation(~land) & (S["wc"] > 0.5) & (S["foot"] < 0.5)
    gy, gx = np.gradient(ndimage.gaussian_filter(sd, 2))
    ys, xs = np.nonzero(coast)
    out, taken = [], []
    order = np.lexsort((xs, ys))
    for j in order:
        y, x = ys[j], xs[j]
        p = np.array([T.X[y, x], T.Y[y, x]])
        if any(np.hypot(*(p - q)) < spacing for q in taken[-400:]):
            continue
        n = -np.array([gx[y, x], gy[y, x]])
        n /= np.linalg.norm(n) + 1e-9
        h = float(S["top"][y, x] - level)
        foot = p + n * float(S["run"][y, x]) if "run" in S else p + n * h / math.tan(CLIFF)
        iy = int(np.clip(round((foot[1] - T.ys[0]) / T.cell), 0, len(T.ys) - 1))
        ix = int(np.clip(round((foot[0] - T.xs[0]) / T.cell), 0, len(T.xs) - 1))
        if S["st_mask"][iy, ix] or h < 2:
            continue
        taken.append(p)
        out.append({"xy": [round(float(foot[0]), 2), round(float(foot[1]), 2)], "z": level,
                    "out": [round(float(n[0]), 3), round(float(n[1]), 3)], "height": round(h, 1),
                    "lip": [round(float(p[0]), 2), round(float(p[1]), 2)]})
    return out


def fill(T, lk):
    """The sea's water: ground below its level connected to the sea side of the coast (never limited to a radius)."""
    below = T.H < lk["level"]
    lab, _ = ndimage.label(below)
    ids = np.unique(lab[~T.sea["land"] & below])
    return np.isin(lab, ids[ids > 0])


def regions(T, name):
    """The sea's zones for cover and routes: sea, beach, cliffs, coast."""
    S = T.sea
    if name == "sea":
        return (~np.isnan(T.water) & (T.lake_id == T.lakes["sea"]["id"])).astype(float)
    if name == "beach":
        graded = S["wb"] * smoothstep(S["beach_width"] * 1.6, S["beach_width"], S["sd"]) * (S["sd"] > -S["beach_width"])
        at_foot = (S["foot"] > 0.5) & (S["sd"] < 0) & (T.H < S["level"] + 2.5)  # sand below the cliffs
        return np.maximum(graded, at_foot) * np.isnan(T.water)
    if name == "cliffs":
        return S["wc"] * smoothstep(-4 * T.cell, 0, S["sd"]) * smoothstep(3 * T.cell, 0, S["sd"])
    if name == "coast":
        return smoothstep(6 * T.cell, 0, np.abs(S["sd"]))
    if name == "rocks":  # the low-rock strip's boulders (shore "rocks")
        return np.clip(S["rocks"] * 1.5, 0, 1)
    return None


def report(T):
    S = T.sea
    if not S:
        return []
    lk = T.lakes["sea"]
    wet = T.lake_id == lk["id"]
    coast = S["land"] & ndimage.binary_dilation(~S["land"])
    length = coast.sum() * T.cell
    out = [f"sea: level {S['level']:.0f} m, {_area(wet.sum() * T.cell ** 2)} of water, {length / 1000:.1f} km of coast; "
           f"deepest {float((S['level'] - T.H[wet]).max()) if wet.any() else 0:.0f} m in the frame"]
    # cliffs as built: at each coast point with a cliff, the drop from the land's top just inland to the water
    by, bx = np.nonzero(coast & (S["wc"] > 0.5))
    if len(by):
        ring = 3
        tops = np.array([T.H[max(y - ring, 0):y + ring + 1, max(x - ring, 0):x + ring + 1].max() for y, x in zip(by, bx)])
        h = tops - S["level"]
        want = S["want"][by, bx] - S["level"]
        slope = T._slope()
        steep = np.array([slope[max(y - ring, 0):y + ring + 1, max(x - ring, 0):x + ring + 1].max() for y, x in zip(by, bx)])
        # judged against what was asked for each stretch (cliffs.heights), not the coast-wide range
        lo, hi = float(np.percentile(want, 5)), float(np.percentile(want, 95))
        tall = h > 1.3 * want + 5
        ok = (h >= 0.8 * want) & (steep >= 55) & ~tall
        out.append(f"sea cliffs (measured): {len(by) * T.cell / 1000:.1f} km of cliff coast, {np.percentile(h, 10):.0f}-"
                   f"{np.percentile(h, 90):.0f} m high (asked {lo:.0f}" + (f"-{hi:.0f}" if hi - lo > 1 else "")
                   + (" over the stretches" if (T.spec.get("sea") or {}).get("cliffs", {}).get("heights") else "")
                   + f"), steepest median {np.median(steep):.0f} deg; {100 * ok.mean():.0f}% as asked")
        if tall.mean() > 0.2:
            ty, tx = by[tall], bx[tall]
            T.warnings.append(f"sea cliffs: {100 * tall.mean():.0f}% of the cliff coast stands over 1.3x its asked height "
                              f"(up to {h.max():.0f} m, around [{T.X[ty, tx].mean():.0f}, {T.Y[ty, tx].mean():.0f}]): the "
                              f"land is that high where it meets the sea (a peak's flanks reaching past the coast). Widen the "
                              f"land, give that stretch its height (cliffs.heights), or let the peak's flanks come lower; the "
                              f"tool won't cut the land down under what you placed")
    for gname, g in S.get("geos", {}).items():  # does the sea run up it: the floor at its mouth and its head, as built
        p, inl = np.array(g["xy"]), np.array(g["inland"])
        pts_ = p + inl[None] * np.linspace(0, 0.9 * g["length"], 10)[:, None]
        fl = T.sample(pts_)
        gwet = T.sample(pts_, (~np.isnan(T.water)).astype(float)) > 0.5
        out.append(f"geo {gname}: {g['length']:.0f} m long, {g['width']:.0f} m wide; floor {fl[0] - S['level']:+.1f} m at the "
                   f"mouth, {fl[-1] - S['level']:+.1f} m at its head; the sea runs {100 * gwet.mean():.0f}% of the way up")
        if gwet.mean() < 0.7:
            T.warnings.append(f"geo {gname!r}: the sea reaches only {100 * gwet.mean():.0f}% of the way up it (its floor stands "
                              f"{fl.max() - S['level']:+.1f} m): move it onto a cliff stretch, or shorten it")
    bc = coast & ((S["wb"] > 0.5) | (S["foot"] > 0.5))
    if bc.any():
        # dry ground within 2.5 m of the water, next to the beach coast: its area over the beach's length is its width
        low = (np.isnan(T.water) & (T.H - S["level"] < 2.5) & ((S["wb"] > 0.5) | (S["foot"] > 0.5))
               & (S["sd"] < 6 * S["beach_width"]))
        lab, _ = ndimage.label(low)
        ids = np.unique(lab[ndimage.binary_dilation(bc, iterations=int(4 + 60 / T.cell)) & low])
        sand = np.isin(lab, ids[ids > 0]).sum() * T.cell ** 2
        length = bc.sum() * T.cell
        out.append(f"beaches (measured): {length:.0f} m of beach coast; the dry sand within 2.5 m of the water averages "
                   f"{sand / max(length, 1):.0f} m wide")
    if S.get("stacks"):
        hs = []
        for st in S["stacks"]:
            c = np.array(st["xy"])
            near = np.hypot(T.X - c[0], T.Y - c[1]) < st["radius"]
            hs.append(float(T.H[near].max() - S["level"]) if near.any() else 0.0)
        up = [h for h in hs if h >= 2.0]
        if up:
            out.append(f"sea stacks: {len(up)} standing {min(up):.0f}-{max(up):.0f} m out of the water off the cliffs")
        if len(up) < len(hs):
            out.append(f"  ({len(hs) - len(up)} placed stack(s) don't stand out of the water: the ground there was cut "
                       f"away after them (a cove, a geo) or they fell in deep water; move the string (`stacks.at`)")
    for name, cv in S["coves"].items():
        m = cv["mask"] & wet
        out.append(f"cove {name}: {_area(m.sum() * T.cell ** 2)} of water, {cv['depth']:.0f} m deep into the "
                   f"land, mouth at [{cv['mouth'][0]:.0f}, {cv['mouth'][1]:.0f}]" + _cove_shape(T, cv, wet))
    return out


def _cove_shape(T, cv, wet):
    """As built: the bay's widest water across, the mouth's narrowest gap between the land either side, each headland's
    top (m above the sea) and the shore height round the rest of the bay."""
    from scipy.spatial import cKDTree
    p, inl = np.array(cv["mouth"]), np.array(cv["inland"])
    left = np.array([-inl[1], inl[0]])
    rel = T.P - p
    u, sa = rel @ inl, rel @ left
    w, dp = cv["width"], cv["depth"]
    # water across the bay's axis, section by section from outside the mouth to the head: the run of water through the
    # bay's own axis (stacks count as water: they stand in the mouth, they don't close it)
    wetx = (T.sea["sd"] <= 0) | wet  # (the coastline itself: rocks awash and stacks in the mouth don't close it)
    axis_s = float(((np.array(cv["xy"]) - p) @ left))
    txt = ""
    widths = []
    for uu in np.arange(-0.3 * dp, dp, max(T.cell, dp / 40)):
        ss = np.arange(axis_s - 1.5 * w, axis_s + 1.5 * w, T.cell)
        pts = p + inl * uu + left * ss[:, None]
        wv = T.sample(pts, wetx.astype(float)) > 0.5
        k = int(np.argmin(np.abs(ss - axis_s)))
        if not wv[k]:
            widths.append((uu, 0.0))
            continue
        i0, i1 = k, k
        while i0 > 0 and wv[i0 - 1]:
            i0 -= 1
        while i1 < len(wv) - 1 and wv[i1 + 1]:
            i1 += 1
        open_ = i0 == 0 or i1 == len(wv) - 1
        widths.append((uu, np.inf if open_ else (i1 - i0 + 1) * T.cell))
    inner = [wd for uu, wd in widths if uu > 0.25 * dp and np.isfinite(wd)]
    bay_w = max(inner) if inner else 0.0
    u_b = next((uu for uu, wd in widths if wd == bay_w), dp / 2)
    mouth = [wd for uu, wd in widths if uu <= u_b and wd > 0]
    mouth_w = min(mouth) if mouth else 0.0
    if bay_w:
        txt += f"; the bay {bay_w:.0f} m across at its widest"
    if np.isfinite(mouth_w) and mouth_w > 0:
        txt += f", the mouth {mouth_w:.0f} m" + (" (sheltered)" if mouth_w < 0.8 * bay_w else
                                                  " (as wide as the bay: open, not sheltered)")
    else:
        txt += ", the mouth opens straight onto the sea (no narrowing: not sheltered)"
    lvl = T.sea["level"]
    for h in cv.get("headlands", []):
        b0, tip = np.array(h["base"]), np.array(h["tip"])
        seg = tip - b0
        t = np.clip(((T.P - b0) @ seg) / (seg @ seg), 0, 1)
        near = np.linalg.norm(T.P - (b0 + t[:, None] * seg), axis=1) < 0.25 * w
        top = float(T.H.ravel()[near & ~wet.ravel()].max() - lvl) if (near & ~wet.ravel()).any() else 0.0
        v = left * h["side"]
        side = ["north", "north-east", "east", "south-east", "south", "south-west", "west", "north-west"][
            int(round(math.degrees(math.atan2(v[0], v[1])) / 45)) % 8]
        kind = "headland" if h.get("height") is not None else "low point"
        txt += f"; {kind} on its {side} side tops {top:.0f} m"
    return txt


def _area(a):
    from .terrain import _area as f
    return f(a)
