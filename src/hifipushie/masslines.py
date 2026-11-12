"""A long mass from its marks: the mark's own MIDDLE LINE, wherever it runs and however it bends, and its width
measured ACROSS that line. masses.py builds a "tube" from it.

Why (Baynard Racing, 2026-11-12): a tube read its mark in slices across a world axis. A slanted arm's slice is
wider than the arm, and each end was set in by that too-wide radius, so a 16 cm arm came out as an 8 cm chain of
4 cm balls (a blind agent could not thin it by any setting); a horn's sideways splay, which only its other view
shows, was dropped for one mean number.

How: the mark is drawn as a small picture; its two far ends are found by distance travelled INSIDE it (so a curl
has ends); bands of equal travel between them are its cross-sections: each band's middle is a point of the middle
line, and its area over its length along the line is the width there. The second view gives the third
coordinate and the depth, station by station, by lining the two middle lines up on their heights (a blob in the
second view, a limb seen end on, gives one place and one depth). An end that touches another marked mass runs on
under it (the joint sits at the mark's end, so the cap pokes in and the two join); a free end's cap stops where the
mark stops.
"""
from __future__ import annotations

import numpy as np


def project(line: np.ndarray, pts: np.ndarray):
    """Each point's place along a polyline [m, 2] (metres from its first point) and its distance from it."""
    seg = np.diff(line, axis=0)
    ln = np.maximum(np.hypot(*seg.T), 1e-12)
    start = np.concatenate([[0.0], np.cumsum(ln)])[:-1]
    best = np.full(len(pts), np.inf)
    at = np.zeros(len(pts))
    for i in range(len(seg)):
        t = np.clip(((pts - line[i]) @ seg[i]) / (ln[i] * ln[i]), 0.0, 1.0)
        d = np.hypot(*(pts - (line[i] + t[:, None] * seg[i])).T)
        k = d < best
        best[k], at[k] = d[k], start[i] + t[k] * ln[i]
    return at, best


def middle(pts: np.ndarray, res: float, touch: np.ndarray | None = None, bands: int = 28) -> dict:
    """The middle line of a mark given as a point cloud [n, 2] (metres; `res`: the size of the picture's pixel the
    points came from; `touch`: those of its points that lie against another mass's mark): {"c": [m, 2] points from
    one end to the other, "half": [m] half widths across it, "s": [m] metres along it, "length", "cut": [bool,
    bool]: that end is the middle of a cut across it (the mass runs on there), not a free tip, "lump": it is a
    short uncut lump and the line is only its long axis}."""
    from scipy import ndimage
    from skimage.graph import MCP_Geometric
    lo = pts.min(0) - 2 * res
    ij = np.floor((pts - lo) / res).astype(int)
    m = np.zeros(tuple(ij.max(0) + 3), bool)
    m[ij[:, 0], ij[:, 1]] = True
    m = ndimage.binary_fill_holes(ndimage.binary_closing(m, iterations=1) | m)
    lab, n = ndimage.label(m)
    if n > 1:
        m = lab == 1 + int(np.argmax(ndimage.sum(m, lab, range(1, n + 1))))
    cells = np.argwhere(m)
    if len(cells) < 12:
        raise ValueError("too small to find a middle line")
    cost = np.where(m, 1.0, -1.0)

    def travel(start):
        d = MCP_Geometric(cost).find_costs([tuple(int(v) for v in start)])[0]
        return np.where(m, d, np.nan)

    def far(d):
        return np.array(np.unravel_index(int(np.nanargmax(d)), d.shape))
    # 1. a first line, keeping to the middle (travel is dear near the edge). An end that is CUT (a short run of the
    #    mark's edge lying against another mass) is the middle of that cut. A free end is the far point by travel
    #    INSIDE the mark (so a curl has ends); a corner or a round tip is dropped back to where the path has reached
    #    the middle, and run on straight from there
    a = far(travel(cells[len(cells) // 2]))
    da = travel(a)
    b = far(da)
    wide = len(cells) / max(float(np.nanmax(da)), 1.0)  # a first width, cells
    near = lambda q: cells[int(np.argmin(((cells - q) ** 2).sum(1)))]  # noqa: E731
    cuts = []
    if touch is not None and len(touch) >= 3:
        tj = np.floor((touch - lo) / res).astype(int)
        tj = tj[(tj >= 0).all(1) & (tj < np.array(m.shape)).all(1)]
        T = np.zeros_like(m)
        T[tj[:, 0], tj[:, 1]] = True
        T &= m
        rim = m & ~ndimage.binary_erosion(m)
        over = (T & rim).sum() > 0.6 * rim.sum()  # touched nearly all round: it lies OVER that mass here, uncut
        labT, nT = ndimage.label(ndimage.binary_dilation(T, iterations=2), structure=np.ones((3, 3)))
        for i in range(1, nT + 1 if not over else 0):
            run = np.argwhere(T & (labT == i))
            if len(run) >= 3 and float(np.hypot(*np.ptp(run, axis=0))) <= 2.2 * wide:  # a run ACROSS it, not round it
                cuts.append(near(run.mean(0)))
        if len(cuts) > 2:  # the two furthest apart
            d = [(float(np.hypot(*(p - q))), i, j) for i, p in enumerate(cuts) for j, q in enumerate(cuts) if i < j]
            _, i, j = max(d)
            cuts = [cuts[i], cuts[j]]
    if len(cuts) == 2:
        a, b = cuts
    elif len(cuts) == 1:
        a = cuts[0]
        b = far(travel(a))
    cut = [len(cuts) >= 1, len(cuts) == 2]
    room = ndimage.distance_transform_edt(m)
    mcp = MCP_Geometric(np.where(m, (float(room.max()) / np.maximum(room, 0.5)) ** 2, -1.0))
    mcp.find_costs([tuple(int(v) for v in a)], [tuple(int(v) for v in b)])
    path = np.array(mcp.traceback(tuple(int(v) for v in b)), float)
    arc = np.concatenate([[0.0], np.cumsum(np.hypot(*np.diff(path, axis=0).T))])
    r = room[path[:, 0].astype(int), path[:, 1].astype(int)]

    def reached(idx):  # the first place where the room stops opening out fast (a corner or a round end is behind)
        for n_, i in enumerate(idx[:-1]):
            j = idx[min(n_ + 4, len(idx) - 1)]
            if (r[j] - r[i]) / max(abs(arc[j] - arc[i]), 1e-9) < 0.35:
                return int(i)
        return int(idx[-1])
    fwd = list(range(len(path)))
    i0 = 0 if cut[0] else reached(fwd)
    i1 = len(path) - 1 if cut[1] else reached(fwd[::-1])
    q = cells - cells.mean(0)
    val, vec = np.linalg.eigh(np.cov(q.T))
    axis, t, u = vec[:, 1], q @ vec[:, 1], q @ vec[:, 0]
    lump = np.sqrt(val[1] / max(val[0], 1e-9)) < 2.2 and len(cells) > 0.45 * np.ptp(t) * np.ptp(u)
    if not any(cut) and lump:
        # a short uncut lump (not a thin curl): its far points are opposite corners and no path between them runs
        # down its middle. Its long axis through its middle instead
        path = cells.mean(0) + np.outer(np.linspace(0.5 * t.min(), 0.5 * t.max(), 9), axis)
        arc = np.concatenate([[0.0], np.cumsum(np.hypot(*np.diff(path, axis=0).T))])
        r = np.full(len(path), wide / 2)
        i0, i1 = 0, len(path) - 1
    if i1 - i0 < 3:  # as wide as it is long: the middle third of the path gives a direction
        i0, i1 = len(path) // 3, max(2 * len(path) // 3, len(path) // 3 + 1)
    step = max(1, int(round(wide / 3)))
    core = path[i0:i1 + 1]
    pick = core[::step] if len(core) > 2 * step else core[[0, -1]]
    if not np.array_equal(pick[-1], core[-1]):
        pick = np.vstack([pick, core[-1]])
    c = (pick + 0.5) * res + lo
    xy = (cells + 0.5) * res + lo
    if len(c) < 2:
        raise ValueError("too small to find a middle line")
    # 2. straight sections: run the line on past both ends, lay every cell on it, and band by place along it
    w = wide * res

    def grow(i, way):  # run on from the core's end, along its direction over the next four rooms' length
        j = int(np.clip(np.searchsorted(arc, arc[i] + way * max(4.0 * r[i], 4.0)), 0, len(path) - 1)) if way > 0 else \
            int(np.clip(np.searchsorted(arc, arc[i] - max(4.0 * r[i], 4.0)), 0, len(path) - 1))
        if j == i:
            j = i1 if way > 0 else i0
        t = path[i] - path[j]
        return (path[i] + 0.5) * res + lo + t / max(float(np.hypot(*t)), 1e-9) * 3.0 * w
    line = np.vstack([grow(i0, +1), c, grow(i1, -1)])
    pts, area = xy, res * res  # the small picture's cells: two views' marks laid together count once
    at, _ = project(line, pts)
    cum = np.concatenate([[0.0], np.cumsum(np.hypot(*np.diff(line, axis=0).T))])
    s0 = float(cum[1]) if cut[0] else float(at.min())    # a cut end stops AT its cut; a free one where the mark does
    s1 = float(cum[-2]) if cut[1] else float(at.max())
    k = int(np.clip((s1 - s0) / (4.0 * res), 4, bands))
    edges = np.linspace(s0, s1, k + 1)
    which = np.digitize(at, edges) - 1
    which[at >= s1] = k - 1 if not cut[1] else k   # what lies past a cut is the neighbour's side of it: left out
    which[at < s0] = 0 if not cut[0] else -1
    on = lambda t: np.array([np.interp(t, cum, line[:, i]) for i in (0, 1)])  # noqa: E731
    c, half = [on(s0)], [0.0]
    for i in range(k):
        sel = which == i
        if sel.sum() >= 2:
            mid = (edges[i] + edges[i + 1]) / 2
            # past the ends of the first line the sections are part empty (a cut seldom runs square across, a tip
            # tapers): their middles would pull the line into a corner, so there it runs straight on
            c.append(pts[sel].mean(0) if cum[1] <= mid <= cum[-2] else on(mid))
            half.append(sel.sum() * area / (edges[i + 1] - edges[i]) / 2)
    c.append(on(s1))
    half.append(0.0)
    c, half = np.array(c), np.array(half)
    if len(c) < 4:
        raise ValueError("too small to find a middle line")
    half[0], half[-1] = half[1], half[-2]
    if len(c) >= 7:
        for _ in range(2):
            cs = c.copy()
            cs[1:-1] = (c[:-2] + 2 * c[1:-1] + c[2:]) / 4
            c = cs
        hp = np.pad(half, 1, mode="edge")
        half = np.array([np.median(hp[i:i + 3]) for i in range(len(half))])
    s = np.concatenate([[0.0], np.cumsum(np.hypot(*np.diff(c, axis=0).T))])
    return {"c": c, "half": half, "s": s, "length": float(s[-1]), "cut": cut, "lump": bool(not any(cut) and lump)}


def _resample(line: dict, n: int) -> dict:
    at = np.linspace(0.0, line["length"], n)
    return {"c": np.stack([np.interp(at, line["s"], line["c"][:, i]) for i in (0, 1)], 1),
            "half": np.interp(at, line["s"], line["half"]), "s": at, "length": line["length"]}


def _warp(za: np.ndarray, zb: np.ndarray):
    """Line two height runs up (dynamic time warping, ends pinned): for each i of za the matching place in zb (a
    fraction index), and the cost per step."""
    n, m = len(za), len(zb)
    d = np.abs(za[:, None] - zb[None, :])
    acc = np.full((n, m), np.inf)
    acc[0, 0] = d[0, 0]
    for i in range(n):
        for j in range(m):
            if i or j:
                best = min(acc[i - 1, j] if i else np.inf, acc[i, j - 1] if j else np.inf,
                           acc[i - 1, j - 1] if i and j else np.inf)
                acc[i, j] = d[i, j] + best
    i, j, pairs = n - 1, m - 1, [(n - 1, m - 1)]
    while i or j:
        opts = [(acc[i - 1, j - 1], i - 1, j - 1)] if i and j else []
        if i:
            opts.append((acc[i - 1, j], i - 1, j))
        if j:
            opts.append((acc[i, j - 1], i, j - 1))
        _, i, j = min(opts)
        pairs.append((i, j))
    hit = [[] for _ in range(n)]
    for i, j in pairs:
        hit[i].append(j)
    return np.array([float(np.mean(h)) for h in hit]), float(acc[-1, -1]) / len(pairs)


def tube(feature: str, f: dict, how: dict, notes: list) -> dict:
    """Joints and bones for a long mass. f: {"xz": pts, "yz": pts, "touch_xz": pts, "touch_yz": pts, "px"} (masses._flat)."""
    views = {k: f[k] for k in ("xz", "yz") if f.get(k) is not None and len(f[k]) >= 12}
    if not views:
        raise ValueError(f"{feature}: no mark in a flat view")
    lines = {}
    for k, p in views.items():
        try:
            lines[k] = middle(p, float(f.get("px") or 0.002), f.get("touch_" + k))
        except ValueError:
            pass
    if not lines:
        raise ValueError(f"{feature}: its mark is too small to find a middle line in")
    # the view that shows its length; one where it was cut off the outline shows it better than one where it lies
    # over the body
    # (and a slender mark shows a run better than a fat one of the same length: a horn from the side, not the front)
    key = max(lines, key=lambda k: lines[k]["length"] ** 2 / max(2 * float(np.median(lines[k]["half"])), 1e-6)
              * (1.5 if any(lines[k]["cut"]) else 1.0) * (1e-4 if f.get("line_" + k) else 1.0)
              * (0.05 if lines[k]["lump"] else 1.0))  # (a lump's line is only its long axis: a guess)
    okey = "yz" if key == "xz" else "xz"
    fine = 33
    P = _resample(lines[key], fine)
    third, depth, said = None, None, None
    if okey in lines:
        O = _resample(lines[okey], fine)
        # long enough there to have a middle line worth lining up (2.5 breadths); a stubbier mark's line leans
        # as its corners do, not as the thing does
        long_o = O["length"] >= 2.5 * 2 * float(np.median(O["half"])) and not lines[okey]["lump"]
        zp, zo = np.ptp(P["c"][:, 1]), np.ptp(O["c"][:, 1])
        if long_o and zo >= 0.5 * max(zp, 1e-6) and zp >= 0.35 * P["length"]:  # both show it running up or down
            fwd, cf = _warp(P["c"][:, 1], O["c"][:, 1])
            bwd, cb = _warp(P["c"][:, 1], O["c"][::-1, 1])
            j = fwd if cf <= cb else (fine - 1) - bwd
            idx = np.arange(fine)
            third = np.interp(j, idx, O["c"][:, 0])
            depth = np.interp(j, idx, O["half"])
        elif long_o and zp < 0.35 * P["length"] and zo < 0.35 * O["length"]:  # both run level: by place along it
            fl = float(np.abs(O["c"][:, 1] - P["c"][:, 1]).sum() > np.abs(O["c"][::-1, 1] - P["c"][:, 1]).sum())
            oc, oh = (O["c"][::-1], O["half"][::-1]) if fl else (O["c"], O["half"])
            third, depth = oc[:, 0].copy(), oh.copy()
        else:  # seen end on, or as a lump
            p = views[okey]
            zp_, zl = P["c"][:, 1], (float(p[:, 1].min()), float(p[:, 1].max()))
            if zp >= 0.35 * P["length"] and zl[1] - zl[0] >= 0.5 * zp:
                # a lump that spans the heights the line runs through (a horn seen from the front, foreshortened):
                # at each height its middle is where the thing is, and its half breadth how deep. A splay shows here
                gap = max(3.0 * float(f.get("px") or 0.002), 0.02 * (zl[1] - zl[0]))
                zc = np.clip(zp_, zl[0] + gap, zl[1] - gap)
                rows = [p[np.abs(p[:, 1] - z) <= gap, 0] for z in zc]
                mid = np.array([(r_.min() + r_.max()) / 2 if len(r_) else np.nan for r_ in rows])
                wid = np.array([(r_.max() - r_.min()) / 2 if len(r_) else np.nan for r_ in rows])
                ok = np.isfinite(mid)
                idx = np.arange(fine)
                third, depth = np.interp(idx, idx[ok], mid[ok]), np.interp(idx, idx[ok], wid[ok])
                kk = np.ones(5) / 5  # one row's edge is ragged: smooth along the line
                third = np.convolve(np.pad(third, 2, mode="edge"), kk, mode="valid")
                depth = np.convolve(np.pad(depth, 2, mode="edge"), kk, mode="valid")
                said = "its other view shows it foreshortened: where it is at each height, and how deep, from there"
            else:  # one place, and a depth that follows the width
                third = np.full(fine, float((p[:, 0].min() + p[:, 0].max()) / 2))
                depth = float(np.ptp(p[:, 0])) / 2 * P["half"] / max(float(P["half"].max()), 1e-9)
                said = "its other view shows it end on or as a lump: one place and one depth from there"
    else:
        other_axis = "y" if key == "xz" else "x"
        third = np.full(fine, float(how.get(other_axis, 0.0)))
        depth = P["half"].copy()
        notes.append(f"{feature}: marked in one flat view: round in section at {other_axis} {third[0]:+.3f} "
                     f"(give \"{other_axis}\", or mark its other view)")
    if f.get("line_" + okey) and okey in lines:  # a line there says where it runs; it has no width of its own
        depth = P["half"].copy()
        said = "marked by a line in its other view: it runs where the line does, round in section"
    if said:
        notes.append(f"{feature}: {said}")
    depth = np.maximum(depth, 0.002)
    width = np.maximum(P["half"], 0.002)
    r = np.maximum(width, depth)
    # joint 0 is the root: the one end that is cut (it runs on under the mass it lies against), else the higher end
    L = P["length"]
    cut = list(lines[key]["cut"])
    flip = (cut[1] and not cut[0]) or (cut[0] == cut[1] and P["c"][-1, 1] > P["c"][0, 1])
    if flip:
        P = {"c": P["c"][::-1], "half": P["half"][::-1], "s": P["s"], "length": L}
        third, depth, width, r, cut = third[::-1], depth[::-1], width[::-1], r[::-1], cut[::-1]
    whole = lambda v, s_, way: float(np.interp(np.clip(s_ + way * np.interp(s_, P["s"], width), 0, L), P["s"], v))  # noqa: E731
    # a free end's cap stops where the mark stops; a cut end's joint is set in 0.6 of its radius, so its cap pokes
    # 0.4 of it into the neighbour (enough to join; a whole radius swallowed a hoof at the end of a leg)
    rin = lambda s_, way: max(float(np.interp(s_, P["s"], r)), whole(r, s_, way))  # noqa: E731
    s0 = min(0.6 * rin(0.0, 1.0), 0.3 * L) if cut[0] else float(min(np.interp(min(r[0], 0.4 * L), P["s"], r), 0.4 * L))
    s1 = L - (min(0.6 * rin(L, -1.0), 0.3 * L) if cut[1] else
              float(min(np.interp(L - min(r[-1], 0.4 * L), P["s"], r), 0.4 * L)))
    n = max(2, int(how.get("joints", 4)))
    at = np.linspace(s0, s1, n)
    side = feature[-2:] if feature[-2:] in (".L", ".R") else ""
    base = feature[:len(feature) - len(side)]
    up = [0.0, -1.0, 0.0] if key == "xz" else [1.0, 0.0, 0.0]
    joints, bones, W, Dp = {}, {}, [], []
    for i, s in enumerate(at):
        u_, z = (float(np.interp(s, P["s"], P["c"][:, k])) for k in (0, 1))
        t = float(np.interp(s, P["s"], third))
        w, d = float(np.interp(s, P["s"], width)), float(np.interp(s, P["s"], depth))
        if (i == 0 and cut[0]) or (i == n - 1 and cut[1]):
            # a cut seldom runs square across: the sections right at it are part empty. Read a width further in
            way = 1.0 if i == 0 else -1.0
            w, d = max(w, whole(width, s, way)), max(d, whole(depth, s, way))
        pos = [u_, t, z] if key == "xz" else [t, u_, z]
        joints[f"{base}_j{i}{side}"] = {"pos": [round(v, 4) for v in pos], "r": round(max(w, d), 4)}
        W.append(w)
        Dp.append(d)
    for i in range(n - 1):
        r0, r1 = max(W[i], Dp[i]), max(W[i + 1], Dp[i + 1])
        bones[f"{base}_b{i}{side}"] = {"a": f"{base}_j{i}{side}", "b": f"{base}_j{i + 1}{side}", "r_a": round(r0, 4),
                                       "r_b": round(r1, 4), "up": up,
                                       "flat": [round((W[i] / r0 + W[i + 1] / r1) / 2, 3),
                                                round((Dp[i] / r0 + Dp[i + 1] / r1) / 2, 3)],
                                       "group": feature, "join": 0.004}
    ends = ["runs on under the mass it lies against" if c else "capped where its mark stops" for c in cut]
    notes.append(f"{feature}: {L * 1000:.0f} mm along its own middle line, {2 * float(np.median(width)) * 1000:.0f} mm "
                 f"across; root end {ends[0]}, far end {ends[1]}")
    return {"joints": joints, "bones": bones}
