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
        raise ValueError("sea: there's no coast (the land is everywhere or nowhere): give \"land\" a zone, or leave "
                         "ground below the level reaching the frame's edge")
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
    # coves: horseshoe bays, the mouth narrower than the bay inside
    coves = {}
    for name, cv in (S.get("coves") or {}).items():
        p, inl = _coast_point(T, land, cv.get("at", "south"))
        w, dp = float(cv.get("width", 0.08 * T.size)), float(cv.get("depth", 0.07 * T.size))
        a = 0.6 * dp  # along the inland axis; centred so the coastline crosses it at ~2/3 of the bay's width
        c = p + inl * (dp - a)
        v = np.stack([T.X - c[0], T.Y - c[1]], -1)
        u, s = v @ inl, v @ np.array([-inl[1], inl[0]])
        lob = noise.fbm(np.c_[T.P, np.full(len(T.P), 13.0)], 0.5 * w, 2, seed=131 + len(coves)).reshape(T.X.shape) - 0.5
        q = (u / a) ** 2 + (s / (w / 2)) ** 2 + 0.25 * lob
        bay = q < 1.0
        sd = np.minimum(sd, (np.sqrt(np.maximum(q, 0)) - 1) * min(a, w / 2))  # ~ distance outside the bay
        land = sd > 0
        head = c + inl * a  # the bay's head, for its beach
        coves[name] = {"xy": c.tolist(), "mouth": p.tolist(), "head": head.tolist(), "inland": inl.tolist(),
                       "width": w, "depth": dp, "mask": bay}
    sd = ndimage.gaussian_filter(sd, 1.0)
    land = sd > 0
    # geos (zawns): narrow clefts cut back into a cliff coast, the sea running up them between vertical walls (a cliff
    # line with no inlets read as a sea wall with a ruler-straight top)
    cl0 = S.get("cliffs") or {}
    if (S.get("shore") == "cliffs" or "cliffs" in S) and cl0.get("geos", 1):
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
                v = np.stack([T.X - p[0], T.Y - p[1]], -1)
                along, across = v @ inl, v @ np.array([-inl[1], inl[0]])
                t = np.clip(along / L, 0, 1)
                half = w * (1 - 0.7 * t) * (1 + 0.3 * np.sin(along / (0.3 * L + 1)))  # narrowing, a little kinked
                cut = np.where((along > -2 * T.cell) & (along < L), np.abs(across) - half, np.inf)
                sd = np.minimum(sd, cut)
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
    if shore == "beach":  # a beach coast: wherever it isn't cliffs
        wb = np.maximum(wb, 1 - wc)

    H = T.H
    depth = float(S.get("depth", 30.0 * max(k, 0.25)))
    shelf = float(S.get("shelf", max(0.08 * T.size, 10 * depth)))
    sea_floor = level - 1.0 - (depth - 1.0) * smoothstep(0, shelf, -sd)
    # cliffs: the land's top at the coast, at least the asked height (the land ramps up to it from inland)
    ch = cl.get("height", 30.0 * max(k, 0.3))
    lo_h, hi_h = (ch, ch) if isinstance(ch, (int, float)) else ch
    var = noise.fbm(np.c_[T.P, np.full(len(T.P), 17.0)], max(0.06 * T.size, 150 * k), 2, seed=141).reshape(T.X.shape)
    want = level + lo_h + (hi_h - lo_h) * np.clip(1.6 * (var - 0.5) + 0.5, 0, 1)
    # the cliff top at each cell's nearest coast point, smoothed along the coast (cell to cell it made a sawtooth crown)
    top_c = ndimage.gaussian_filter(np.where(coast, np.maximum(H, want), 0.0), smooth) / np.maximum(
        ndimage.gaussian_filter(coast.astype(float), smooth), 1e-6)
    top_here = top_c[cy, cx]
    ramp = float(cl.get("ramp", 0.12))  # how the land climbs to meet a raised cliff top: fades inland at this grade
    raised = np.maximum(H, top_here - ramp * np.maximum(sd, 0))
    # the lip rolls over (slope-over-wall): the top falls a little toward the edge before the face (a knife-edge lip
    # read as a sawn block)
    bev_h = float(cl.get("bevel", 0.12)) * np.maximum(top_here - level, 0)
    bev_w = np.maximum(3 * bev_h, 2 * T.cell)
    raised = raised - bev_h * smoothstep(bev_w, 0, np.maximum(sd, 0)) ** 1.5
    cliff_face = (top_here - bev_h) - np.maximum(-sd, 0) * math.tan(CLIFF)
    # beaches: sand from just under the level to a couple of metres up over `width`, the land behind easing down
    bw = float(S.get("beach_width", 30 * max(k, 0.5)))
    back = float(S.get("backshore", 4 * bw))
    beach = level - 0.6 + np.maximum(sd, -3 * bw) * (2.6 / bw)
    beach_land = np.where(sd < bw, beach, H * smoothstep(bw, bw + back, sd) + (beach) * (1 - smoothstep(bw, bw + back, sd)))
    # rocky: the land as it is, kept dry at the shore, dropping into the water
    # (kept dry a few cells in from the shore only: uncapped, 0.2 * sd raised ground 400 m inland to 80 m)
    rocky = np.where(sd > 0, np.maximum(H, level + 0.4 + 0.2 * np.minimum(sd, 3 * T.cell)), np.minimum(H, level - 0.8 + 0.8 * sd))
    onshore = wc * raised + wb * beach_land + (1 - wc - wb) * rocky
    # offshore of a cliff its face stands in the water, from the top down to the sea floor (clamping the first cells
    # offshore under the water had made every cliff a plumb wall at the coastline)
    below = np.minimum(sea_floor, np.where(sd > -3 * T.cell, level - 0.3, np.inf))
    offshore = wc * np.maximum(cliff_face, sea_floor) + wb * np.minimum(np.maximum(beach, sea_floor), level - 0.6) \
        + (1 - wc - wb) * below
    # beaches at the foot of cliffs: a strip of sand below the face, the cliff standing behind it
    if foot.any():
        run = np.maximum(top_here - level, 0) / math.tan(CLIFF)
        fw = np.full(T.X.shape, 35.0)
        for m, w in foot_w:
            fw = np.where(m > 0.3, w, fw)
        x = (-sd - run) / fw  # 0 at the face's foot, 1 at the sand's seaward edge
        # dry sand most of the way out (1.8 -> 1.0 m), then shelving into the water
        sand = np.where(x < 0.75, level + 1.8 - 1.07 * x, level + 1.0 - 7.0 * (x - 0.75))
        offshore = np.where(foot > 0.5, np.where(x < 0, np.maximum(cliff_face, sand), np.maximum(sand, sea_floor)),
                            offshore)
    new = np.where(sd > 0, onshore, offshore)
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
    run = np.maximum(top_here - level, 0) / math.tan(CLIFF)
    out_of_foot = -sd - run  # metres seaward of the face's foot
    pw = float(cl.get("platform", max(3 * T.cell, 25 * k)))
    stacks = []
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
                r = max(2 * T.cell, rng.uniform(0.15, 0.28) * (top - level))
                hg = (top - level) * rng.uniform(0.65, 0.95) * (1 - 0.1 * i)
                skirt = hg / math.tan(math.radians(76))  # (its sides spread this far at the waterline)
                out += (2.0 if i == 0 else 1.4) * r + skirt  # (clear water between: they had merged into a shelf)
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
            steps = level + hgt * np.floor((1 - (d - 0.7 * r) / (1.2 * r)) * 3) / 3  # ledges down the sides
            side = level + hgt - (d - r) * math.tan(math.radians(76))
            st = np.where(d < r, top_z, np.maximum(side, np.minimum(steps, side + 0.25 * hgt)))
            st = np.minimum(st, top_z)
            ok = (sd < 0) & (st > new)
            new = np.where(ok, st, new)
            T.hard |= ok & (st > level)
            stacks.append({"xy": c.tolist(), "height": hgt, "radius": r})
    cliffish = (wc > 0.5) | (foot > 0.5)  # (a cliff's face and its foot's sand stand offshore of the coastline)
    new = np.where(sd > 0, np.maximum(new, level + 0.3), np.where(cliffish, new, np.minimum(new, level - 0.3)))
    T.H = new
    face = (sd < 0) & (sd > -((hi_h + depth) / math.tan(CLIFF) + 2 * T.cell)) & (wc > 0.5)
    T.hard |= face
    T.hardness = np.where(face, np.minimum(T.hardness, 0.05), T.hardness)
    T.sea = {"level": level, "land": land, "sd": sd, "wc": wc, "wb": wb, "foot": foot, "coves": coves, "want": want,
             "beach_at": beach_at, "stacks": stacks,
             "cliff_asked": (lo_h, hi_h), "beach_width": bw, "beaches": list(beaches)}
    T.masks.setdefault("coast", np.zeros(T.X.shape))
    T.masks["coast"] = np.maximum(T.masks["coast"], smoothstep(4 * T.cell, 0, np.abs(sd)))
    far = np.unravel_index(np.argmin(sd), sd.shape)  # the open sea: furthest from any land (a ring's mean is its hole)
    lk = {"xy": [float(T.X[far]), float(T.Y[far])], "level": level, "r": T.size,
          "id": len(T.lakes) + 1, "sea": True}
    T.lakes["sea"] = lk


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
        lo, hi = S["cliff_asked"]
        tall = h > 1.3 * max(hi, lo) + 5
        ok = (h >= 0.8 * want) & (steep >= 55) & ~tall
        out.append(f"sea cliffs (measured): {len(by) * T.cell / 1000:.1f} km of cliff coast, {np.percentile(h, 10):.0f}-"
                   f"{np.percentile(h, 90):.0f} m high (asked {lo:.0f}" + (f"-{hi:.0f}" if hi != lo else "")
                   + f"), steepest median {np.median(steep):.0f} deg; {100 * ok.mean():.0f}% as asked")
        if tall.mean() > 0.2:
            T.warnings.append(f"sea cliffs: {100 * tall.mean():.0f}% of the cliff coast stands over {1.3 * max(hi, lo) + 5:.0f} m "
                              f"(up to {h.max():.0f}): the land is that high where it meets the sea (a peak's flanks reaching "
                              f"past the coast). Widen the land, or let the peak's flanks come lower (a wider radius or "
                              f"gentler flanks); the tool won't cut the land down under what you placed")
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
        out.append(f"sea stacks: {len(hs)} standing {min(hs):.0f}-{max(hs):.0f} m out of the water off the cliffs")
    for name, cv in S["coves"].items():
        m = cv["mask"] & wet
        out.append(f"cove {name}: {_area(m.sum() * T.cell ** 2)} of sheltered water, {cv['depth']:.0f} m deep into the "
                   f"land, mouth at [{cv['mouth'][0]:.0f}, {cv['mouth'][1]:.0f}]")
    return out


def _area(a):
    from .terrain import _area as f
    return f(a)
