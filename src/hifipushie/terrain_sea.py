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
        if isinstance(a, str) and (a in T.zones or a.startswith("quadrant:")) or isinstance(a, dict):
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
    cliff_face = top_here - np.maximum(-sd, 0) * math.tan(CLIFF)
    # beaches: sand from just under the level to a couple of metres up over `width`, the land behind easing down
    bw = float(S.get("beach_width", 30 * max(k, 0.5)))
    back = float(S.get("backshore", 4 * bw))
    beach = level - 0.6 + np.maximum(sd, -3 * bw) * (2.6 / bw)
    beach_land = np.where(sd < bw, beach, H * smoothstep(bw, bw + back, sd) + (beach) * (1 - smoothstep(bw, bw + back, sd)))
    # rocky: the land as it is, kept dry at the shore, dropping into the water
    rocky = np.where(sd > 0, np.maximum(H, level + 0.4 + 0.2 * sd), np.minimum(H, level - 0.8 + 0.8 * sd))
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
    cliffish = (wc > 0.5) | (foot > 0.5)  # (a cliff's face and its foot's sand stand offshore of the coastline)
    new = np.where(sd > 0, np.maximum(new, level + 0.3), np.where(cliffish, new, np.minimum(new, level - 0.3)))
    T.H = new
    face = (sd < 0) & (sd > -((hi_h + depth) / math.tan(CLIFF) + 2 * T.cell)) & (wc > 0.5)
    T.hard |= face
    T.hardness = np.where(face, np.minimum(T.hardness, 0.05), T.hardness)
    T.sea = {"level": level, "land": land, "sd": sd, "wc": wc, "wb": wb, "foot": foot, "coves": coves, "want": want,
             "beach_at": beach_at,
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
    for name, cv in S["coves"].items():
        m = cv["mask"] & wet
        out.append(f"cove {name}: {_area(m.sum() * T.cell ** 2)} of sheltered water, {cv['depth']:.0f} m deep into the "
                   f"land, mouth at [{cv['mouth'][0]:.0f}, {cv['mouth'][1]:.0f}]")
    return out


def _area(a):
    from .terrain import _area as f
    return f(a)
