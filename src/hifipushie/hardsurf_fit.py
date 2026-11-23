"""Hard surface from the point cloud: fit clean parts to the fused sculpt (MEASURE and IDEALISE; never press).

A fused point-cloud sculpt is lumpy (3 mm voxels, splat noise). Pressing a cage onto it re-imports the lumps; a hard-
surface artist instead fits clean primitives to it and bakes the detail. Each fitter returns a PART (a dict that
blender_hardsurf_build turns into a mesh, see hardsurf_parts.TYPES) plus the evidence it read:

- `turned(S, name, origin, axis, t0, t1, rmax, ...)`: anything turned on a lathe (wheels, cans, bottles, knobs, bells'
  crowns, pipes' ends). Votes over `angles` directions round the axis: a (t, r) cell is solid if most agree -> contour ->
  simplified profile. The vote throws out parts that touch it at a few angles and averages the noise round the
  revolution; a round shell with walls of 2+ voxels is traced fine. FAILS on parts that aren't round (warned: weak votes
  > 30 %), on shells thinner than ~2 voxels or noisy (a fused bell's mouth votes 0.2-0.5), and on non-round detail
  (lugs, bolts average away): read the vote map (`vote_text`) and draw the profile yourself; model the detail as its
  own parts (type radial).
- `profile_vote(S, axis, values, window)` + `sweep(...)`: a slab-like part (a seat, a plank, a crate wall, a sign)
  is its cross-section swept across its width. The vote over several parallel sections gives one clean profile; draw it
  off the vote (vote_text) or take `profile_from_vote`. `sweep` rounds the ends (quarter-round insets) and can blend in
  a second `side` profile over the outer part of the width (bucket bolsters).
- `trace_tube(S, start, direction)`: march along a round tube, re-centring on its cross-section; stops at a junction.
- `outline_loop(S, axis, value, window, inset)`: the biggest outline in a plane pulled in by a tube's radius (a frame).
- `ring_fit(S, centre, normal)`: centre + radius of a ring of surface in a thin slab (a wheel's rim, a steering ring).
All coordinates are the framed sculpt's (hardsurf_frame): z up, front -y, metres."""
from __future__ import annotations

import numpy as np
from scipy import ndimage
from skimage import measure, draw

from .hardsurf_solid import Solid, basis, circle_fit_2d


def _simplify(pts, tol):
    return measure.approximate_polygon(np.asarray(pts, float), tolerance=tol)


# ---------------------------------------------------------------- turned parts
def turned_profile(S: Solid, origin, axis, t0, t1, rmax, step=0.003, angles=36, keep=0.5, tol=0.003, sector=None):
    """(profile [(t, r)...] from the axis round the outside back to the axis, vote map V[t, r])"""
    ts, rs, V = S.votes(origin, axis, t0, t1, rmax, step, angles, sector)
    pad = np.zeros((V.shape[0] + 2, V.shape[1] + 1)); pad[1:-1, 1:] = V; pad[1:-1, 0] = V[:, 0]   # mirrored over the axis
    cs = measure.find_contours(pad, keep)
    if not cs:
        return [], V
    c = max(cs, key=len)
    t = t0 + (c[:, 0] - 1) * step; r = np.clip((c[:, 1] - 1) * step + step / 2, 0, None)
    pts = np.c_[t, r]; on = r < step * 0.75
    if on.any() and not on.all():                 # open the closed contour at the axis
        st = next(i for i in range(len(pts)) if on[i] and not on[(i + 1) % len(pts)])
        pts = np.roll(pts, -st, 0); on = np.roll(on, -st)
        end = 1 + int(np.argmax(on[1:])); pts = pts[: end + 1]; pts[0, 1] = pts[-1, 1] = 0
        if pts[0, 0] > pts[-1, 0]: pts = pts[::-1]
    return [tuple(map(float, p)) for p in _simplify(pts, tol)], V


def turned(S: Solid, name, origin, axis, t0, t1, rmax, step=0.003, angles=36, keep=0.5, tol=0.003, **part):
    prof, V = turned_profile(S, origin, axis, t0, t1, rmax, step, angles, keep, tol)
    if len(prof) < 3:
        raise ValueError(f"{name}: no solid round {origin} along {axis} (t {t0}..{t1}, r < {rmax}): check the axis")
    weak = float(((V > 0.15) & (V < 0.5)).sum() / max((V > 0.15).sum(), 1))
    d = dict(type="lathe", name=name, origin=list(map(float, origin)), axis=list(map(float, axis)), profile=prof,
             evidence={"vote_cells": int((V >= keep).sum()), "weak_fraction": round(weak, 3)})
    if weak > 0.3:      # measured: round parts (even a 6 mm cup wall) <= 0.24, a 2:1 ellipse 0.31, a blade 0.67
        d["warning"] = (f"{round(weak * 100)} % of the touched cells are weak votes: not round, or a shell thinner than "
                        "two voxels / noisy? read vote_text and draw the profile by hand")
    d.update(part); return d


def vote_text(V, rows, cols, keep=0.5) -> str:
    """the vote map as text an LLM can read: '#' > 0.7, '+' > keep, '.' > 0.2; rows/cols are the sample positions"""
    head = "      " + "".join(f"{c:+.2f}"[1:] if i % 5 == 0 else "" for i, c in enumerate(cols))
    out = [head]
    for a, row in zip(rows, V):
        out.append(f"{a:+.3f} " + "".join("#" if v > 0.7 else ("+" if v > keep else ("." if v > 0.2 else " ")) for v in row))
    return "\n".join(out)


# ---------------------------------------------------------------- swept slabs
def profile_vote(S: Solid, axis, values, window, step=0.006):
    """mean occupancy of parallel sections: (rows, cols, V) with rows/cols the two in-plane axes in xyz order"""
    A, B, V, _ = S.width_vote(axis, values, window, step)
    return A, B, V


def profile_from_vote(A, B, V, keep=0.5, tol=0.004, pick=None):
    """the biggest (or the one nearest `pick`) region of a vote map as a simplified closed 2D profile"""
    cs = measure.find_contours(np.pad(V, 1), keep)
    if not cs:
        raise ValueError("nothing in the vote above keep")
    st = A[1] - A[0]
    to = lambda c: np.c_[A[0] + (c[:, 0] - 1) * st, B[0] + (c[:, 1] - 1) * (B[1] - B[0])]
    if pick is None:
        c = max(cs, key=len)
    else:
        c = min(cs, key=lambda c_: np.linalg.norm(to(c_) - np.asarray(pick), axis=1).min())
    return [tuple(map(float, p)) for p in _simplify(to(c), tol)[:-1]]


def resample_closed(p, n, start_dir):
    """a closed 2D loop resampled to n points by length, counter-clockwise, starting furthest along start_dir"""
    p = np.asarray(p, float)
    if 0.5 * np.sum(p[:, 0] * np.roll(p[:, 1], -1) - np.roll(p[:, 0], -1) * p[:, 1]) < 0: p = p[::-1]
    k0 = int(np.argmax((p - p.mean(0)) @ np.asarray(start_dir, float))); p = np.vstack([p[k0:], p[:k0]])
    pc = np.vstack([p, p[:1]]); seg = np.r_[0, np.cumsum(np.linalg.norm(np.diff(pc, axis=0), axis=1))]
    out = []
    for s in np.linspace(0, seg[-1], n, endpoint=False):
        m = np.searchsorted(seg, s, side="right") - 1; f = (s - seg[m]) / max(seg[m + 1] - seg[m], 1e-9)
        out.append(pc[m] * (1 - f) + pc[m + 1] * f)
    return np.array(out)


def inset(profile, d, res=0.001):
    """a closed 2D profile pulled in by d (raster erosion + contour; no shapely). Returns None when nothing is left."""
    p = np.asarray(profile, float)
    if d <= 1e-6: return p
    lo = p.min(0) - 2 * res; n = np.ceil((p.max(0) + 2 * res - lo) / res).astype(int) + 1
    M = np.zeros(n, bool); rr, cc = draw.polygon((p[:, 0] - lo[0]) / res, (p[:, 1] - lo[1]) / res, n); M[rr, cc] = True
    E = ndimage.distance_transform_edt(M) * res > d
    if E.sum() < 4: return None
    cs = measure.find_contours(E.astype(float), 0.5)
    c = max(cs, key=len)
    return c * res + lo


def _area(p):
    p = np.asarray(p); return 0.5 * abs(np.sum(p[:, 0] * np.roll(p[:, 1], -1) - np.roll(p[:, 0], -1) * p[:, 1]))


def sweep_rings(profile, x0, x1, n=56, round_r=0.02, steps=4, mid=6, start_dir=(-1, -1), axis="x", side=None, side_from=0.55):
    """rings for a 'loft' part: `profile` (2D, in the other two axes in xyz order) swept from x0 to x1 along `axis` with
    quarter-round ends of radius round_r (thin profiles back the inset off so the ends never vanish); `side`: a second
    profile blended in smoothly over the outer (1 - side_from) of the half-width"""
    if side is not None:
        A_ = sweep_rings(profile, x0, x1, n, round_r, steps, mid, start_dir, axis)
        B_ = sweep_rings(side, x0, x1, n, round_r, steps, mid, start_dir, axis)
        i = "xyz".index(axis); xc, h = (x0 + x1) / 2, (x1 - x0) / 2; out = []
        for ra, rb in zip(A_, B_):
            w = float(np.clip((abs(ra[0][i] - xc) / h - side_from) / (1 - side_from), 0, 1)); w = w * w * (3 - 2 * w)
            out.append([[float(a * (1 - w) + b * w) for a, b in zip(pa, pb)] for pa, pb in zip(ra, rb)])
        return out
    st = [(round_r * (1 - np.cos(np.pi / 2 * k / steps)), round_r * (1 - np.sin(np.pi / 2 * k / steps))) for k in range(steps + 1)]
    xs = [(x0 + d, s) for d, s in st] + [(x0 + round_r + (x1 - x0 - 2 * round_r) * (q + 1) / (mid + 1), 0.0) for q in range(mid)] + \
         [(x1 - d, s) for d, s in reversed(st)]
    A0 = _area(profile); i = "xyz".index(axis); j, k = [q for q in range(3) if q != i]; rings = []
    for x, ins in xs:
        pg = inset(profile, ins)
        while pg is None or _area(pg) < 0.1 * A0:            # thin profiles: back the inset off
            ins *= 0.7; pg = inset(profile, ins)
        q = resample_closed(pg, n, start_dir); ring = []
        for a_, b_ in q:
            v = [0.0, 0.0, 0.0]; v[i] = float(x); v[j] = float(a_); v[k] = float(b_); ring.append(v)
        rings.append(ring)
    return rings


def sweep(name, profile, x0, x1, axis="x", n=56, round_r=0.02, steps=4, mid=6, side=None, side_from=0.55, **part):
    d = dict(type="loft", name=name, rings=sweep_rings(profile, x0, x1, n, round_r, steps, mid, axis=axis, side=side,
                                                       side_from=side_from), caps=True)
    d.update(part); return d


# ---------------------------------------------------------------- tubes, outlines, rings
def trace_tube(S: Solid, start, direction, step=0.02, maxlen=1.5, half=0.08, res=0.002, grow=1.8, turn=0.6):
    """march along a round tube from `start` in `direction`: each step looks at the cross-section, takes the solid blob
    nearest the predicted centre and re-centres on it. Stops at a junction (area jumps x`grow`), a gap, or maxlen.
    -> (centreline (k, 3), median radius)"""
    p = np.asarray(start, float); d = np.asarray(direction, float); d /= np.linalg.norm(d)
    pts, areas = [], []
    g = np.arange(-half, half, res); A, B = np.meshgrid(g, g, indexing="ij"); ci = len(g) // 2
    for _ in range(int(maxlen / step) + 1):
        _, u, v = basis(d)
        lab, k = ndimage.label(S.inside(p + A[..., None] * u + B[..., None] * v))
        if k == 0: break
        best = min(range(1, k + 1), key=lambda L: np.min(((np.argwhere(lab == L) - ci) ** 2).sum(1)))
        blob = np.argwhere(lab == best)
        if np.min(((blob - ci) ** 2).sum(1)) * res * res > 0.03 ** 2: break
        area = len(blob) * res * res
        if len(areas) > 2 and area > grow * np.median(areas): break
        cc = blob.mean(0); c3 = p + (g[0] + cc[0] * res) * u + (g[0] + cc[1] * res) * v
        if pts:
            nd = c3 - pts[-1]
            if np.linalg.norm(nd) > 1e-6: d = (1 - turn) * d + turn * nd / np.linalg.norm(nd); d /= np.linalg.norm(d)
        pts.append(c3); areas.append(area); p = c3 + d * step
    return np.array(pts), float(np.median(np.sqrt(np.array(areas) / np.pi))) if areas else 0.0


def outline_loop(S: Solid, axis, value, window, inset_by, step=0.003, tol=0.01):
    """the biggest outline in the plane axis=value, pulled in by `inset_by` (a tube's radius), simplified -> 3D loop"""
    A, B, M, (i, j, k) = S.section_mask(axis, value, window, step)
    c = max(measure.find_contours(np.pad(M.astype(float), 1), 0.5), key=len)
    p = np.c_[window[0] + (c[:, 0] - 1) * step, window[2] + (c[:, 1] - 1) * step]
    q = inset(p, inset_by)
    if q is None: raise ValueError("the outline vanishes at that inset")
    q = _simplify(q, tol)[:-1]; out = []
    for a_, b_ in q:
        v = [0.0, 0.0, 0.0]; v[i] = float(value); v[j] = float(a_); v[k] = float(b_); out.append(v)
    return out


def ring_fit(S: Solid, centre, normal, half=0.006, rmin=0.0, rmax=0.3, res=0.002):
    """a circle through the solid's boundary in the plane through `centre` (a wheel's rim seen side-on, a ring):
    -> (centre (3,), radius, mean error)"""
    n, u, v = basis(normal); o = np.asarray(centre, float)
    g = np.arange(-rmax, rmax, res); A, B = np.meshgrid(g, g, indexing="ij")
    M = S.inside(o + A[..., None] * u + B[..., None] * v)
    edge = M & ~ndimage.binary_erosion(M); P = np.c_[A[edge], B[edge]]
    r_ = np.hypot(P[:, 0], P[:, 1]); P = P[(r_ >= rmin) & (r_ <= rmax)]
    if len(P) < 10: raise ValueError("no boundary there")
    c, r, e = circle_fit_2d(P)
    for _ in range(4):                            # robust: keep the boundary near the fitted circle (the outer rim)
        dd = np.abs(np.linalg.norm(P - c, axis=1) - r); P2 = P[dd < max(3 * res, 2 * np.median(dd))]
        if len(P2) < 10: break
        c, r, e = circle_fit_2d(P2)
    return (o + c[0] * u + c[1] * v), float(r), float(e)
