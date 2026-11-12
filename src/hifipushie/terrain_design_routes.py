"""Routes and `apply`: the path search on the grid, breaks and their cuts, the profile, a route. Part of the terrain design layer (terrain_design.py has the overview)."""
from __future__ import annotations

import math

import numpy as np
from scipy import ndimage
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import dijkstra
from scipy.spatial import cKDTree

from . import terrain_design
from .terrain import Line, _arclen, smoothstep
from .terrain_design import region
from .terrain_design_sight import _cells, _ij
from .terrain_design_sites import _earthworks, _site
from .terrain_design_walls import _pass, _wall

# ---------------------------------------------------------------- walls, sites, routes
def apply(T):
    for name, p in (T.spec.get("passes") or {}).items():
        _pass(T, name, p)
    for name, b in T.basins.items():  # a basin's wall is its own inner face: only checked, never raised
        spec = (T.spec.get("basins") or {})[name].get("walls", {})
        T.walls[name] = {"inside": b["floor"], "band": b["width"], "raised": 0.0, "basin": True,
                         "spec": {"min_slope": b["min_slope"], "height": spec.get("height", 30),
                                  "except": spec.get("except", []) + list(T.passes), "gap": spec.get("gap", 90 * T.k)}}
        if b.get("mouth") is not None:
            T.walls[name]["mouth"] = b["mouth"]
    for name, w in (T.spec.get("walls") or {}).items():
        _wall(T, name, w)
    # sites in dependency order: one that overlooks or falls toward another is built after it (key order mattered)
    todo = dict(T.spec.get("sites") or {})
    while todo:
        ready = [n for n, s in todo.items()
                 if not any(isinstance(s.get(k), str) and s.get(k) in todo and s.get(k) != n
                            for k in ("at", "overlooks", "toward"))]
        for n in ready or list(todo)[:1]:  # (a cycle: build in the given order)
            _site(T, n, todo.pop(n))
    for st in T.sites.values():  # props face an address (a basket its tee): compass bearing, 0 north, 90 east
        pr = st.get("prop")
        if pr and pr.get("facing"):
            f = T.address(pr.pop("facing"))[0] - np.array(st["xy"])
            pr["yaw"] = round(float(np.degrees(np.arctan2(f[0], f[1]))) % 360, 1)
        elif pr:
            pr.pop("facing", None)
    for name, r in (T.spec.get("routes") or {}).items():
        _route(T, name, r)


def _path(T, H, cell, a, b, maxg, blocked, reach_only=False, penalty=None):
    """Least-cost grid path from a to b (row, col) on 32 headings; edges steeper than 1.2 x maxg are left out,
    gentler ones cost more as they near the limit, so the search winds (switchbacks) where it must."""
    ny, nx = H.shape
    idx = np.arange(ny * nx).reshape(ny, nx)
    rows, cols, wts = [], [], []
    for dy, dx in terrain_design._OFFS:
        ys0, ys1 = max(0, -dy), ny - max(0, dy)
        xs0, xs1 = max(0, -dx), nx - max(0, dx)
        A = idx[ys0:ys1, xs0:xs1]
        B = idx[ys0 + dy:ys1 + dy, xs0 + dx:xs1 + dx]
        length = cell * math.hypot(dy, dx)
        # each step may be up to BUMP metres off the grade: the carve evens out bumps that size (planning on ground
        # smoothed over 30 m instead hid 45 deg risers, so plans went where no road could be built)
        g = np.maximum(np.abs(H.ravel()[B] - H.ravel()[A]) - terrain_design.BUMP, 0) / length
        ok = (g <= maxg) & ~blocked.ravel()[A] & ~blocked.ravel()[B]
        wt = length * (1 + 3 * (g / (0.85 * maxg)) ** 2) + 0.2 * length  # slack below the limit: smoothing adds grade
        if penalty is not None:
            wt = wt + penalty.ravel()[B]
        for p, q in ((A, B), (B, A)):
            rows.append(p[ok]); cols.append(q[ok]); wts.append(wt[ok])
    G = coo_matrix((np.concatenate(wts), (np.concatenate(rows), np.concatenate(cols))), shape=(ny * nx, ny * nx)).tocsr()
    dist, pred = dijkstra(G, indices=idx[a], return_predecessors=True)
    if reach_only:
        return (np.isfinite(dist).reshape(ny, nx), b) if not np.isfinite(dist[idx[b]]) else None
    if not np.isfinite(dist[idx[b]]):
        return None
    out, k = [], idx[b]
    while k >= 0 and k != idx[a]:
        out.append(k)
        k = pred[k]
    out.append(idx[a])
    return np.array(out[::-1])


def _grid(T, r, cliffs=True, extra=None):
    """The search grid for a route: ground smoothed over ~30 m (the carve evens out smaller bumps anyway), except
    where earthworks already shaped it (a break's benches smoothed away are a cliff again), and what blocks it."""
    f = 2 if T.X.size > 400_000 else 1  # (at every other cell, one-cell cliff bands fell between samples)
    sm = ndimage.gaussian_filter(T.H, float(r.get("smooth", 6.0)) / T.cell / 2)  # nearly the real ground (see BUMP)
    ew = T.masks.get("earthworks", np.zeros(T.X.shape))
    H = np.where(ew > 0.5, T.H, sm)[::f, ::f]
    cell = T.cell * f
    lakes = getattr(T, "lake_id", np.zeros(T.X.shape, int)) > 0
    blocked = lakes[::f, ::f].copy()
    # true cliffs are walls to a road, however the smoothing sees them (a 70 deg canyon band smoothed read as 25%)
    if cliffs:
        cliff = (T._slope() > 50) & (ew <= 0.5)
        for a in [r["from"], *r.get("via", []), r["to"]]:  # a stop on a crest isn't walled in by its own steep sides
            xy = T.address(a)[0]
            cliff &= np.hypot(T.X - xy[0], T.Y - xy[1]) > 3 * T.cell * f + float(r.get("width", 5))
        blocked |= ndimage.maximum_filter(cliff, size=f)[::f, ::f] if f > 1 else cliff
    river = getattr(T, "river_water", np.zeros(T.X.shape, bool)) & ~getattr(T, "ford_mask", np.zeros(T.X.shape, bool))
    penalty = ndimage.binary_dilation(river, iterations=f)[::f, ::f] * 40.0 * cell  # wading/bridging costs: use fords
    for a in r.get("avoid", []):
        blocked |= region(T, a)[::f, ::f] > 0.5
    if r.get("stay_in"):
        blocked |= region(T, r["stay_in"])[::f, ::f] < 0.5
    if extra is not None:  # cells an earlier plan's legs crowded
        blocked |= ndimage.maximum_filter(extra, size=f)[::f, ::f] if f > 1 else extra
    return H, cell, blocked, penalty


def _cell_of(T, c, cell):
    return int(round((c[1] - T.ys[0]) / cell)), int(round((c[0] - T.xs[0]) / cell))


def _search(T, name, r, maxg, cliffs=True, extra=None):
    """The least-cost way through the stops at the asked grade, relaxing it if nothing connects. Returns (legs of
    [x, y] points, how much it was relaxed, where the asked grade ran out) or None when nothing connects at all."""
    stops = [r["from"], *r.get("via", []), r["to"]]
    H, cell, blocked, penalty = _grid(T, r, cliffs, extra)
    pts = []
    relaxed, strict_at = 1.0, None
    for a, b in zip(stops[:-1], stops[1:]):
        ca, cb = [T.address(x)[0] for x in (a, b)]
        ga, gb = _cell_of(T, ca, cell), _cell_of(T, cb, cell)
        path = None
        strict = _path(T, H, cell, ga, gb, maxg * 0.95, blocked, reach_only=True, penalty=penalty)  # how far the asked grade gets
        for relax in (1.0, 1.4, 2.0, 3.0):
            bl = blocked.copy()
            bl[ga] = bl[gb] = False
            path = _path(T, H, cell, ga, gb, maxg * relax * 0.95, bl, penalty=penalty)
            if path is not None:
                relaxed = max(relaxed, relax)
                break
        if path is None:
            if extra is not None:  # blocking crowded legs closed it off: the caller keeps its earlier plan
                return None
            if cliffs:  # the best it can do over the cliffs, drawn and judged as built (FAIL), rather than nothing
                found = _search(T, name, r, maxg, cliffs=False)
                if found is not None:
                    cove = getattr(T, "sea", None) and any(isinstance(x, str) and x in T.sea["coves"] or
                                                           (isinstance(x, str) and x in T.sites and
                                                            (T.spec.get("sites") or {}).get(x, {}).get("at") in T.sea["coves"])
                                                           for x in (a, b))
                    T.warnings.append(f"route {name!r}: cliffs over 50 deg close {a!r} off from {b!r} and no break "
                                      f"could be cut (max_break {r.get('max_break', 250):g} m): drawn over the cliff, "
                                      f"judged as built" + ("; a cove's scar walls in its apron: give the cove a "
                                                            "\"valley\" toward where the route goes" if cove else
                                                            "; move a stop or add a 'via' past the cliff"))
                return found
            wet = [x for x in (a, b) if isinstance(x, str) and getattr(T, "sea", None) and x in T.sea["coves"]]
            T.warnings.append(f"route {name!r}: no way from {a!r} to {b!r} (water or avoided zones close it off)"
                              + (f"; {wet[0]!r} is a cove, and a cove's address is its water: put a site at it "
                                 f"(\"at\": {wet[0]!r}: it stands on the apron) and route to the site" if wet else ""))
            return None
        if strict is not None and strict_at is None:
            reach, (gy, gx) = strict
            yy, xx = np.nonzero(reach)
            end = np.array([T.xs[0] + gx * cell, T.ys[0] + gy * cell])
            k = int(np.argmin(np.hypot(T.xs[0] + xx * cell - end[0], T.ys[0] + yy * cell - end[1])))
            strict_at = (np.array([T.xs[0] + xx[k] * cell, T.ys[0] + yy[k] * cell]), end)
        iy, ix = np.divmod(path, H.shape[1])
        leg = np.stack([T.xs[0] + ix * cell, T.ys[0] + iy * cell], 1)
        leg[0], leg[-1] = ca, cb
        pts.append(leg if not pts else leg[1:])
    return pts, relaxed, strict_at


def _breaks(T, name, r, maxg, width, tries=8):
    """Where nothing connects a route's stops at its grade, the barrier is the gap between what each end can reach
    (a cliff band, a cove's scar). Break it where it's thinnest: switchback legs at the route's grade cut across the
    step, the ground shaped into benches with rock cut between them. Then look again (a canyon has several bands)."""
    stops = [r["from"], *r.get("via", []), r["to"]]
    cuts = []
    keep_H, keep_ew = T.H.copy(), T.masks.get("earthworks", np.zeros(T.X.shape)).copy()
    opened = False
    for _ in range(tries):
        H, cell, blocked, penalty = _grid(T, r)
        opened = True
        pair = None
        for a, b in zip(stops[:-1], stops[1:]):
            ga, gb = _cell_of(T, T.address(a)[0], cell), _cell_of(T, T.address(b)[0], cell)
            ra = _path(T, H, cell, ga, gb, maxg * 0.95, blocked, reach_only=True, penalty=penalty)
            if ra is None:
                continue
            opened = False
            rb = _path(T, H, cell, gb, ga, maxg * 0.95, blocked, reach_only=True, penalty=penalty)
            if rb is None:
                continue
            ea = ra[0] & ~ndimage.binary_erosion(ra[0], border_value=1)  # (the frame's own edge isn't a barrier)
            eb = rb[0] & ~ndimage.binary_erosion(rb[0], border_value=1)
            if not ea.any() or not eb.any():
                continue
            pa = np.stack(np.nonzero(ea), 1)
            pb = np.stack(np.nonzero(eb), 1)
            kq = min(25, len(pb))  # several candidates each: the nearest far side may be the tallest
            d, j = cKDTree(pb).query(pa, k=kq)
            d, j = np.atleast_2d(d.T).T.reshape(len(pa), -1), np.atleast_2d(j.T).T.reshape(len(pa), -1)
            ia = np.repeat(np.arange(len(pa)), d.shape[1])
            d, j = d.ravel(), j.ravel()
            to_xy = lambda q: np.stack([T.xs[0] + q[:, 1] * cell, T.ys[0] + q[:, 0] * cell], 1)
            xa, xb = to_xy(pa[ia]), to_xy(pb[j])
            za, zb = T.sample(xa), T.sample(xb)
            drop = np.abs(za - zb)
            goal = T.address(b)[0]
            zg = T.height(goal)
            toward = np.abs(zb - zg) < np.abs(za - zg) - 2  # a break has to bring the route nearer its goal's height
            # the lowest and thinnest place in the barrier (the thinnest alone broke a cove's scar where it was 193 m
            # tall, when its sides come down toward the headlands), heading for the goal; never taller than max_break
            # near the route's own line between its stops: the thinnest place anywhere was the canyon's end at the
            # frame's edge, a kilometre off the way
            st = T.address(a)[0]
            ax = goal - st
            tt = np.clip(((xa + xb) / 2 - st) @ ax / max(ax @ ax, 1e-9), 0, 1)
            off = np.linalg.norm((xa + xb) / 2 - (st + tt[:, None] * ax), axis=1)
            cost = np.where((drop <= float(r.get("max_break", 250.0))) & (drop >= 5) & toward & (d > 0),
                            d + 2.0 * drop + 1.0 * off, np.inf)
            order = np.argsort(cost)
            pair = [(xa[i], xb[i]) for i in order[:12] if np.isfinite(cost[i])]  # the best few, tried in turn
            if pair:
                break
        if pair is None:  # every stretch connects at its grade now, or nothing can be broken
            break
        cut = None
        for A, B in pair:
            if T.height(A) < T.height(B):
                A, B = B, A
            zm = (T.height(A) + T.height(B)) / 2
            if any(np.hypot(*((A + B) / 2 - np.array(c["at"]))) < 50 and abs(zm - c["z"]) < 10 for c in cuts):
                continue  # broke there already (the same step, not the next band down)
            cut = _cut_break(T, name, A, B, maxg, width, r)  # None: no dry room beside that cliff; the next one
            if cut is not None:
                break
        if cut is None:
            break
        cuts.append(cut)
    if cuts and not opened:  # breaks that didn't open the way come out again: earthworks for nothing
        T.H, T.masks["earthworks"] = keep_H, keep_ew
        T.warnings.append(f"route {name!r}: breaks through its cliffs didn't open a way at its grade; none were kept")
        return []
    return cuts


def _cut_break(T, name, A, B, maxg, width, r):
    zA, zB = T.height(A), T.height(B)
    drop = zA - zB
    if drop < 3:
        return None
    g = 0.9 * maxg
    w_half = max(width / 2 + 2, 1.5 * T.cell * (2 if T.X.size > 400_000 else 1))
    # across the cliff is its own downhill direction at the crossing, not the line between the two points found either
    # side of it (they can lie diagonally along a canyon: the legs then dug a quarry into the plateau)
    gy, gx = np.gradient(ndimage.gaussian_filter(T.H, max(2.0, 0.25 * drop / T.cell)), T.cell)
    iy, ix = _ij(T, (A + B) / 2)
    dirv = -np.array([gx[iy, ix], gy[iy, ix]])
    if np.linalg.norm(dirv) < 1e-6:
        dirv = B - A
    dirv = dirv / (np.linalg.norm(dirv) + 1e-9)
    dl = max(float((B - A) @ dirv), 0.0)  # its distance across (the bottom leg ends on the same foot as B)
    tv = np.array([-dirv[1], dirv[0]])
    # the legs are as long as the cliff runs on beside the crossing: both its top and its foot staying near their
    # heights, on dry land (fixed 30 m legs made a 209 m canyon wall into 31 legs stacked in a 1 km trench; long fixed
    # legs ran into the sides of a cove's bowl)
    wet = ~np.isnan(T.water)
    tol = max(3.0, 0.15 * drop)

    def room(sg):
        s_ = np.arange(T.cell, float(r.get("leg", 300.0)), T.cell)
        top, foot = A + sg * tv * s_[:, None], B + sg * tv * s_[:, None]
        ok = ((np.abs(T.sample(top) - zA) < tol) & (np.abs(T.sample(foot) - zB) < tol)
              & ~wet.ravel()[_cells(T, top)] & ~wet.ravel()[_cells(T, foot)])
        bad = np.nonzero(~ok)[0]
        return float(s_[bad[0] - 1]) if len(bad) and bad[0] > 0 else (float(s_[-1]) if not len(bad) else 0.0)

    rooms = [room(1), room(-1)]
    if max(rooms) < max(20.0, 3 * width):  # no room beside this cliff for switchbacks
        return None
    if rooms[1] > rooms[0]:
        tv = -tv
    nlegs = max(1, int(math.ceil(drop / (g * max(rooms)))))
    leg = drop / (g * nlegs)
    # rock cut between the benches at up to 55 deg, the stack centred on the cliff
    sep = max(2 * w_half + 2 * T.cell, (g * leg) / math.tan(math.radians(55)))
    # the top leg starts at the step's top and the bottom one ends at its foot: spread across the step when it's wide
    # enough (centred on a wide canyon wall, the top leg began in mid-wall, joined to nothing), centred on the cliff
    # (cut into the land either side) when it's narrower than the stack
    if nlegs > 1 and dl >= (nlegs - 1) * sep:
        us = np.linspace(0, dl, nlegs)
    else:
        us = np.array([dl / 2 + (kk - (nlegs - 1) / 2) * sep for kk in range(nlegs)])
    V = np.stack([T.X - A[0], T.Y - A[1]], -1)
    uu, vv = V @ dirv, V @ tv
    vc = np.clip(vv, 0, leg)
    zleg = np.array([zA - g * (leg * kk + (vc if kk % 2 == 0 else leg - vc)) for kk in range(nlegs)])
    kf = np.clip(np.interp(uu, us, np.arange(nlegs)) if nlegs > 1 else np.zeros_like(uu), 0, nlegs - 1)
    k0 = np.floor(kf).astype(int)
    k1 = np.minimum(k0 + 1, nlegs - 1)
    t = kf - k0
    bench = min(0.45, w_half / max(sep, 1e-6))  # flat benches around each leg, rock cut between
    t = np.clip((t - bench) / max(1 - 2 * bench, 1e-6), 0, 1)
    S = np.take_along_axis(zleg, k0[None], 0)[0] * (1 - t) + np.take_along_axis(zleg, k1[None], 0)[0] * t
    # the top leg starts on the upper ground and the bottom one ends on the lower: extend the benches' ends there
    bank = max(15.0, 2 * T.cell)
    wgt = (smoothstep(-w_half - bank, -w_half, vv) * smoothstep(leg + w_half + bank, leg + w_half, vv)
           * smoothstep(us[0] - w_half - bank, us[0] - w_half, uu) * smoothstep(us[-1] + w_half + bank, us[-1] + w_half, uu))
    # no deeper than the step itself (plus a margin): along a curving scar on a cone the legs ran into rising ground and
    # cut 169 m
    lim = drop + 10.0
    wgt = wgt * smoothstep(lim + 10, lim, np.abs(S - T.H))
    before = T.H.copy()
    T.H = T.H * (1 - wgt) + S * wgt
    _earthworks(T, wgt)
    return {"route": name, "at": ((A + B) / 2).tolist(), "z": (zA + zB) / 2, "drop": drop, "legs": nlegs,
            "cut": float((before - T.H).max()), "fill": float((T.H - before).max())}


def _profile(T, pts, maxg, relax=1.0):
    """The planned way as dense points and its road height: the grid path's staircase smoothed, resampled evenly,
    graded to 0.92 of the limit both ways and pulled back toward the ground."""
    xy = np.vstack(pts)
    # (not smoothed: every way of smoothing the grid's staircase that was tried moved the road onto ground the search
    # hadn't checked, over cliff lips and down risers, and failed more roads as built)
    s, length = _arclen(xy)
    n = max(2, int(length / (T.cell / 2)))
    u = np.linspace(0, 1, n)
    xy = np.stack([np.interp(u, s, xy[:, 0]), np.interp(u, s, xy[:, 1])], 1)
    step = np.linalg.norm(np.diff(xy, axis=0), axis=1)  # true steps: shorter than length/(n-1) at corners
    ds = length / (n - 1)
    ground = T.sample(xy)
    h = ndimage.gaussian_filter1d(ground, 30 / ds, mode="nearest")
    gp = 0.85 * maxg  # planned with slack under the limit: the grid leaves about a metre of wiggle (24% on 20 at 0.92)
    # on a pad (a site it starts or ends at) the way is the pad's own surface: the road isn't carved there, so a bed
    # planned freely met the pad's edge as a 4-5 m step (every lane FAILED at 36-40% right at its pad)
    pads = getattr(T, "pads", None)
    pinned = (T.sample(xy, pads) > 0.3) if pads is not None else np.zeros(n, bool)
    if pinned.any():  # between two pads the grade must at least span their heights (planned at 85% of the limit, a
        # lane between pads 41 m apart in 390 m couldn't: the grading passes fought and left a 4 m step at one pad)
        idx = np.nonzero(pinned)[0]
        gaps = np.nonzero(np.diff(idx) > 1)[0]
        sc = np.r_[0, np.cumsum(step)]
        for g_ in gaps:
            a, b = idx[g_], idx[g_ + 1]
            need = abs(ground[b] - ground[a]) / max(sc[b] - sc[a], 1e-6)
            gp = max(gp, 1.02 * need)  # (past the limit too: an even grade that fails honestly, not a step at one pad)
            if need > maxg:
                T._pad_gap = (need, float(abs(ground[b] - ground[a])), float(sc[b] - sc[a]), xy[a], xy[b])
    for _ in range(30):  # grade limit both ways, pulled back toward the ground
        h[pinned] = ground[pinned]
        for i in range(1, n):
            h[i] = np.clip(h[i], h[i - 1] - gp * step[i - 1], h[i - 1] + gp * step[i - 1])
        for i in range(n - 2, -1, -1):
            h[i] = np.clip(h[i], h[i + 1] - gp * step[i], h[i + 1] + gp * step[i])
        h = 0.8 * h + 0.2 * ndimage.gaussian_filter1d(ground, 10 / ds, mode="nearest")
    h[pinned] = ground[pinned]
    for _ in range(8 if pinned.any() else 1):  # (alternating until both ways hold with the pads fixed)
        for i in range(1, n):
            if not pinned[i]:
                h[i] = np.clip(h[i], h[i - 1] - gp * step[i - 1], h[i - 1] + gp * step[i - 1])
        if not pinned.any():
            break
        for i in range(n - 2, -1, -1):
            if not pinned[i]:
                h[i] = np.clip(h[i], h[i + 1] - gp * step[i], h[i + 1] + gp * step[i])
    return xy, h, n


def _crowded(xy, h, width):
    """Points of later legs that pass too close to an earlier leg for both beds and a bank of at most 45 deg between."""
    s = np.r_[0, np.cumsum(np.linalg.norm(np.diff(xy, axis=0), axis=1))]
    reach = width + 4 + 40
    pairs = cKDTree(xy).query_pairs(reach, output_type="ndarray")
    if not len(pairs):
        return np.zeros(0, int)
    i, j = pairs[:, 0], pairs[:, 1]
    d = np.linalg.norm(xy[i] - xy[j], axis=1)
    along = np.abs(s[j] - s[i])
    need = width + 4 + np.abs(h[i] - h[j])  # beds apart by their width, and the bank between no steeper than 45 deg
    bad = (d < need) & (along > 3 * need + 2 * width)
    return np.unique(np.maximum(i[bad], j[bad]))


def _route(T, name, r):
    maxg = float(r.get("max_grade", 0.12))
    width = float(r.get("width", 5))
    stops = [r["from"], *r.get("via", []), r["to"]]
    cuts = _breaks(T, name, r, maxg, width) if r.get("breaks", True) else []
    T.breaks = getattr(T, "breaks", []) + cuts
    found = _search(T, name, r, maxg)
    if found is not None and found[1] > 1:  # walled off by cliffs it winds far and steep: over them may be better
        alt = _search(T, name, r, maxg, cliffs=False)
        if alt is not None and alt[1] <= found[1]:  # (a tie: as before cliffs were walls)
            found = alt
    if found is None:
        return
    pts, relaxed, strict_at = found
    if relaxed > 1:
        msg = (f"route {name!r}: nothing within {100 * maxg:.0f}% connects its stops; searched at "
               f"{100 * maxg * relaxed:.0f}% (the carve then eases what it can)")
        if strict_at is not None:  # say where the asked grade runs out and what's in the way
            near, end = strict_at
            dz = T.height(end) - T.height(near)
            dd = max(float(np.linalg.norm(end - near)), 1.0)
            msg += (f". At {100 * maxg:.0f}% it gets as far as [{near[0]:.0f}, {near[1]:.0f}], {dd:.0f} m short; from "
                    f"there the ground {'rises' if dz > 0 else 'falls'} {abs(dz):.0f} m to the stop ({100 * abs(dz) / dd:.0f}% "
                    f"straight): lower/raise the stop, add a 'via' where it can wind, or allow a steeper grade")
        T.warnings.append(msg)
    xy, h, n = _profile(T, pts, maxg, relaxed)
    # switchback legs need room between them for their beds and a bank of at most 45 deg: where the plan crowds them,
    # the later leg's cells are closed and it plans again, wider (built crowded, one leg's carve broke the other's
    # bed: a descent planned at 25% measured 167% as built)
    extra = np.zeros(T.X.shape, bool)
    for _ in range(int(r.get("uncrowd", 5))):
        bad = _crowded(xy, h, width)
        if not len(bad):
            break
        for p in xy[bad]:
            extra |= np.hypot(T.X - p[0], T.Y - p[1]) < width / 2 + T.cell
        again = _search(T, name, r, maxg, extra=extra)
        if again is None or again[1] > relaxed:
            T.warnings.append(f"route {name!r}: switchback legs crowd each other near [{xy[bad[0], 0]:.0f}, "
                              f"{xy[bad[0], 1]:.0f}] (too little room between them for a bank); the ground there may "
                              f"not hold both")
            break
        pts = again[0]
        xy, h, n = _profile(T, pts, maxg, relaxed)
    length = _arclen(xy)[1]
    if r.get("carve", True):
        # each cell follows the leg nearest in 3D (plan distance + height): where switchback legs pass close,
        # plan distance alone gave cells between them the other leg's height
        dk, ik = cKDTree(xy).query(T.P, k=6, distance_upper_bound=width / 2 + 120)
        hk = np.where(np.isfinite(dk), h[np.minimum(ik, n - 1)], np.inf)
        score = dk + np.abs(hk - T.H.ravel()[:, None])
        j = np.argmin(score, axis=1)
        d = dk[np.arange(len(j)), j].reshape(T.X.shape)
        i = ik[np.arange(len(j)), j].reshape(T.X.shape)
        near = np.isfinite(d)
        hr = np.where(near, h[np.minimum(i, n - 1)], T.H)
        half = max(width / 2, 0.75 * T.cell)  # narrower than the grid can't be flat on it
        bank = np.clip(np.abs(T.H - hr) / math.tan(math.radians(34)), 4.0, 40.0)
        w = np.where(near, smoothstep(half + bank, half, d), 0)
        # earthworks have a limit: past ~25 m of cut or fill a road is a bridge or a tunnel, not a causeway (a 65 m fill
        # built a tongue out over a canyon); left as it is, and the report says where
        # cut up to 25 m (a cutting); fill at the way's own scale: a 2 m mule trail doesn't stand on a 25 m bank (it
        # made knife-edge fins)
        deep = float(r.get("max_earthworks", 25.0))
        tall = float(r.get("max_fill", deep))  # (a 6-12 m default made trails fail down gullies: fins are the lesser evil)
        w *= np.where(hr > T.H, smoothstep(tall + 3, tall, hr - T.H), smoothstep(deep + 5, deep, T.H - hr))
        if hasattr(T, "pads"):  # a road arrives at a site; it doesn't bury or trench the pad (its bank it grades through:
            w *= 1 - T.pads  # left alone, the bank stood as a step where every road met its pad)
        before = T.H.copy()
        T.H = T.H * (1 - w) + hr * w
        _earthworks(T, w)
        cut, fill = float((before - T.H).max()), float((T.H - before).max())
        T.masks.setdefault("routes", np.zeros(T.X.shape))
        T.masks["routes"] = np.maximum(T.masks["routes"], np.where(near, smoothstep(width / 2 + 3, width / 2, d), 0))
    else:
        cut = fill = 0.0
    if max(cut, fill) > 15:
        T.warnings.append(f"route {name!r} cuts {cut:.0f} m / fills {fill:.0f} m somewhere: a trench or embankment; "
                          f"a gentler max_grade, a 'via' point, or accept it")
    straight = sum(float(np.linalg.norm(T.address(b)[0] - T.address(a)[0])) for a, b in zip(stops[:-1], stops[1:]))
    climb = abs(float(h[-1] - h[0]))
    need = max(straight, climb / maxg)  # winding down a 700 m wall at 15% needs 4.7 km: that's not a detour
    if length > 2 * max(need, 1.0):
        T.warnings.append(f"route {name!r} is {length:.0f} m where {need:.0f} m would do (the crow flies {straight:.0f} m, "
                          f"the climb needs {climb / maxg:.0f} m at its grade): it's detouring round something; check "
                          f"the map for what, or add a 'via'")
    s, _ = _arclen(xy)
    gap = getattr(T, "_pad_gap", None)
    T._pad_gap = None
    if gap is not None:
        T.warnings.append(f"route {name!r}: between the sites at [{gap[3][0]:.0f}, {gap[3][1]:.0f}] and [{gap[4][0]:.0f}, "
                          f"{gap[4][1]:.0f}] the ground falls {gap[1]:.0f} m in {gap[2]:.0f} m of road ({100 * gap[0]:.0f}%): "
                          f"no way at {100 * maxg:.0f}% joins those pad edges that directly. Add a 'via' so it winds, move a "
                          f"site, or allow the grade")
    T.routes[name] = Line(name, "route", xy, h, s, {"length": length, "max_grade": maxg, "width": width,
                                                   "cut": cut, "fill": fill, "relaxed": relaxed})
