"""Mesh and LODs: meshing, the checks, silhouettes and outline measures, UV charts, the cluster / wood / mesh LODs,
the hull. Part of clutter (clutter.py has the overview)."""
from __future__ import annotations

import math

import numpy as np

from . import clutter
from .clutter_solid import Solid, _grad

def _onto(fn, V, h, steps=3):
    for _ in range(steps):
        g = _grad(fn, V, h)
        st = g * (fn(V) / np.maximum((g * g).sum(1), 1e-9))[:, None]
        ln = np.linalg.norm(st, axis=1, keepdims=True)
        V = V - st * np.minimum(1.0, 0.03 / np.maximum(ln, 1e-9))  # (never a long jump: a far vertex's Newton step can leave the form)
    return V


def _volume(solid: Solid, n=88):
    span = solid.hi - solid.lo
    vox = float(span.max()) / n
    ax = [solid.lo[i] + np.arange(int(span[i] / vox) + 2) * vox for i in range(3)]
    G = np.stack(np.meshgrid(*ax, indexing="ij"), -1).reshape(-1, 3)
    v = np.concatenate([solid.sd(G[i: i + 200000]) for i in range(0, len(G), 200000)]).reshape([len(a) for a in ax])
    return v, ax, vox


def _mesh(vol, ax, vox):
    from skimage import measure
    V, F, _, _ = measure.marching_cubes(vol, 0.0, spacing=(vox,) * 3)
    V = V + [ax[0][0], ax[1][0], ax[2][0]]
    F = np.ascontiguousarray(F[:, ::-1])  # (skimage winds for an increasing-inward field: ours is negative inside)
    c = V[F].mean(1)
    fn = np.cross(V[F[:, 1]] - V[F[:, 0]], V[F[:, 2]] - V[F[:, 0]])
    if (np.einsum("ij,ij->i", fn, c - V.mean(0))).sum() < 0:
        F = np.ascontiguousarray(F[:, ::-1])
    return V, F


def _sound(V, F) -> bool:
    """Closed and manifold: every edge has exactly two faces (pyfqmr can leave a fin: twin faces on one edge)."""
    if not len(F):
        return False
    e = np.sort(np.r_[F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]], axis=1)
    _, cnt = np.unique(e, axis=0, return_counts=True)
    return bool((cnt == 2).all())


def _decimate(V, F, target):
    """pyfqmr to a count: the result nearest the target from several aggressiveness values (a smooth pebble overshoots
    far below the target at a high one, a crisp block stalls above it at a low one), going on from a stall."""
    if len(F) <= target:
        return V, F
    import pyfqmr

    def run(V_, F_, agg, border=True):
        q = pyfqmr.Simplify()
        q.setMesh(np.ascontiguousarray(V_, np.float64), np.ascontiguousarray(F_, np.int32))
        q.simplify_mesh(target_count=int(target), aggressiveness=agg, preserve_border=border, verbose=False)
        V2, F2, _ = q.getMesh()
        return np.asarray(V2, float), np.asarray(F2, np.int64)
    best = None
    for agg in (5, 3, 7, 2, 1, 0.5, 9):
        r = run(V, F, agg)
        ok = _sound(*r)
        miss = abs(len(r[1]) - target) / target + (0.5 if len(r[1]) < 0.9 * target else 0.0) + (0.0 if ok else 10.0)
        if best is None or miss < best[0]:
            best = (miss, r)
        if ok and 0.95 * target <= len(r[1]) <= 1.08 * target:
            break
    best = best[1]
    for _ in range(4):  # (stalled far above the target: go on from where it stopped)
        if len(best[1]) <= 1.25 * target:
            break
        r = run(best[0], best[1], 9, False)
        if len(r[1]) >= len(best[1]) or len(r[1]) < 0.9 * target or not _sound(*r):
            break
        best = r
    return best


def _drop_specks(V, F, keep_share=0.02):
    """Pieces of a mesh too small to matter (a cluster's stone decimated to a sliver)."""
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components
    n = len(V)
    e = np.r_[F[:, [0, 1]], F[:, [1, 2]]]
    _, lab = connected_components(coo_matrix((np.ones(len(e)), (e[:, 0], e[:, 1])), (n, n)), directed=False)
    area = 0.5 * np.linalg.norm(np.cross(V[F[:, 1]] - V[F[:, 0]], V[F[:, 2]] - V[F[:, 0]]), axis=1)
    fl = lab[F[:, 0]]
    tot = np.bincount(fl, area, minlength=lab.max() + 1)
    cnt = np.bincount(fl, minlength=lab.max() + 1)
    ok = (tot[fl] > keep_share * tot.max()) & (cnt[fl] >= 4)
    return F[ok]


def mesh_check(V, F) -> dict:
    """A LOD's soundness with its chart seams welded: edges with one face (open) or more than two (non-manifold),
    faces of no area."""
    _, inv = np.unique(np.round(V, 6), axis=0, return_inverse=True)
    G = inv.reshape(-1)[F]
    e = np.sort(np.r_[G[:, [0, 1]], G[:, [1, 2]], G[:, [2, 0]]], axis=1)
    _, cnt = np.unique(e, axis=0, return_counts=True)
    ar = np.linalg.norm(np.cross(V[F[:, 1]] - V[F[:, 0]], V[F[:, 2]] - V[F[:, 0]]), axis=1)
    return {"triangles": int(len(F)), "open_edges": int((cnt == 1).sum()), "nonmanifold_edges": int((cnt > 2).sum()),
            "degenerate": int((ar < 1e-10).sum())}


def silhouette(V, F, azimuth, elevation=10.0, px=220.0, frame=None):
    """A mesh's filled outline from a direction (deg), orthographic: (mask, frame); frame = (x0, y0, w, h) px."""
    from PIL import Image, ImageDraw
    a, e = math.radians(azimuth), math.radians(elevation)
    d = np.array([math.cos(e) * math.cos(a), math.cos(e) * math.sin(a), math.sin(e)])
    r = np.array([-math.sin(a), math.cos(a), 0.0])
    u = np.cross(d, r)
    X, Y = V @ r * px, -(V @ u) * px
    if frame is None:
        x0, y0 = math.floor(X.min()) - 3, math.floor(Y.min()) - 3
        frame = (x0, y0, int(math.ceil(X.max()) - x0 + 4), int(math.ceil(Y.max()) - y0 + 4))
    im = Image.new("L", (frame[2], frame[3]), 0)
    dr = ImageDraw.Draw(im)
    T = np.stack([X[F] - frame[0], Y[F] - frame[1]], -1).reshape(len(F), 6)
    for t in T.tolist():
        dr.polygon(t, fill=255)
    return np.asarray(im) > 0, frame


def silhouette_iou(A, B, directions=8) -> list:
    """Outline IoU of mesh B against mesh A ((V, F) each) from `directions` azimuths round it (10 and 35 deg up)."""
    out = []
    for i in range(directions):
        m0, fr = silhouette(A[0], A[1], 360.0 * i / directions, 10.0 if i % 2 == 0 else 35.0)
        m1, _ = silhouette(B[0], B[1], 360.0 * i / directions, 10.0 if i % 2 == 0 else 35.0, frame=fr)
        out.append(float((m0 & m1).sum() / max((m0 | m1).sum(), 1)))
    return out


def outline_measures(V, F, directions=8) -> dict:
    """What a boulder's side outlines say (the measures read off reference photos): height / width, corners (the
    outline simplified to 4% of its size), the share of the outline that is straight (within 1.5% over a tenth of
    its length), top width / base width (at 80% / 20% of the height)."""
    hw, corners, taper = [], [], []
    for i in range(directions):
        m, _ = silhouette(V, F, 360.0 * i / directions, 5.0)
        rows = np.flatnonzero(m.any(1))
        cols = np.flatnonzero(m.any(0))
        h, w = len(rows), len(cols)
        hw.append(h / w)
        wid = lambda fr: m[rows[0] + int(fr * (h - 1))].sum()
        taper.append(wid(0.2) / max(wid(0.8), 1))
        # the outline as the row extents, simplified
        L = np.array([[np.flatnonzero(m[r])[0], r] for r in rows], float)
        Rr = np.array([[np.flatnonzero(m[r])[-1], r] for r in rows[::-1]], float)
        poly = np.r_[L, Rr]
        corners.append(len(_rdp(poly, 0.04 * max(h, w))))
    return {"height_over_width": round(float(np.mean(hw)), 3), "hw_range": [round(float(min(hw)), 2), round(float(max(hw)), 2)],
            "corners": round(float(np.mean(corners)), 1), "top_over_base": round(float(np.mean(taper)), 3)}


def _rdp(P, eps):
    if len(P) < 3:
        return P
    a, b = P[0], P[-1]
    ab = b - a
    l = np.linalg.norm(ab)
    d = np.abs(ab[0] * (P[:, 1] - a[1]) - ab[1] * (P[:, 0] - a[0])) / l if l > 1e-9 else np.linalg.norm(P - a, axis=1)
    i = int(d.argmax())
    if d[i] <= eps:
        return np.array([a, b])
    return np.r_[_rdp(P[: i + 1], eps)[:-1], _rdp(P[i:], eps)]


def _chart_axes(a, s):
    """A chart's picture axes in the solid's frame: (u axis index, u sign, row axis index, row sign). Side charts are
    upright (rows run down = -z), the top chart is a map (rows run -y), mirrored as seen from that side."""
    if a == 2:
        return (0, 1, 1, -s)
    h = 1 if a == 0 else 0
    return (h, (s if a == 0 else -s), 2, -1)


def _chart_rect(k, cell):
    """Chart k's pixel rectangle inside a variant's cell (3 x 2 charts): x0, y0, w, h."""
    w, h = cell // 3, cell // 2
    return (k % 3) * w, (k // 3) * h, w, h


def _uv_of(P, a, s, lo, hi, rect, margin=3):
    ui, us, ri, rs = _chart_axes(a, s)
    x0, y0, w, h = rect
    fu = (P[:, ui] - lo[ui]) / (hi[ui] - lo[ui])
    fr = (P[:, ri] - lo[ri]) / (hi[ri] - lo[ri])
    if us < 0:
        fu = 1 - fu
    if rs < 0:
        fr = 1 - fr
    return np.c_[x0 + margin + fu * (w - 2 * margin), y0 + margin + fr * (h - 2 * margin)]


def _pieces(V, F):
    """A mesh's connected pieces [(V, F)], largest surface first."""
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components
    n = len(V)
    e = np.r_[F[:, [0, 1]], F[:, [1, 2]]]
    k, lab = connected_components(coo_matrix((np.ones(len(e)), (e[:, 0], e[:, 1])), (n, n)), directed=False)
    out = []
    for c in range(k):
        f = F[lab[F[:, 0]] == c]
        if len(f) < 4:
            continue
        used = np.unique(f)
        re = np.full(n, -1)
        re[used] = np.arange(len(used))
        Vc, Fc = V[used], re[f]
        area = 0.5 * np.linalg.norm(np.cross(Vc[Fc[:, 1]] - Vc[Fc[:, 0]], Vc[Fc[:, 2]] - Vc[Fc[:, 0]]), axis=1).sum()
        out.append((area, Vc, Fc))
    out.sort(key=lambda t: -t[0])
    return out


def _join(parts):
    V, F, o = [], [], 0
    for v, f in parts:
        V.append(v)
        F.append(f + o)
        o += len(v)
    return np.concatenate(V), np.concatenate(F)


def cluster_lod(V, F, target):
    """A patch of stones at a budget: every stone its own greedy hull, faces shared by surface; the smallest stones
    are left out when their share would be under a tetrahedron-and-a-bit (never a folded sliver, never over budget)."""
    P = _pieces(V, F)
    while True:
        tot = sum(a ** 0.75 for a, _, _ in P)
        share = [max(int(target * a ** 0.75 / tot), 0) for a, _, _ in P]
        if len(P) > 1 and share[-1] < 8:
            P = P[:-1]
            continue
        break
    return _join([_hull(v, max(8, sh)) for (a, v, f), sh in zip(P, share)])


def wood_lod(solid, sides: int, rings: int, stubs: bool):
    """Driftwood at a low budget, built: every piece a tube of `sides` round its own axis (rings along the main stem,
    2 on a fork or stub), ends capped. A decimator leaves a thin stem a string of slivers."""
    out = []
    for W in solid.parts:
        main = W.segs[: W.n_main]
        chains = [main] + ([[sg] for sg in W.segs[W.n_main:]] if stubs else [[sg] for sg in W.segs[W.n_main:] if np.linalg.norm(sg[1] - sg[0]) > 0.2])
        for ch in chains:
            pts = [ch[0][0]] + [sg[1] for sg in ch]
            rad = [ch[0][2]] + [sg[3] for sg in ch]
            if len(pts) > rings:  # fewer rings: keep the ends, even picks between
                idx = np.unique(np.round(np.linspace(0, len(pts) - 1, rings)).astype(int))
                pts, rad = [pts[i] for i in idx], [rad[i] for i in idx]
            pts, rad = np.array(pts), np.array(rad)
            V, F = [], []
            up = np.array([0.0, 0.0, 1.0])
            for i, (c, r) in enumerate(zip(pts, rad)):
                d = pts[min(i + 1, len(pts) - 1)] - pts[max(i - 1, 0)]
                d /= np.linalg.norm(d)
                a = np.cross(d, up if abs(d[2]) < 0.9 else np.array([1.0, 0, 0]))
                a /= np.linalg.norm(a)
                b = np.cross(d, a)
                for k in range(sides):
                    t = 2 * math.pi * (k + 0.5) / sides
                    V.append(c + r * 1.08 * (math.cos(t) * a + math.sin(t) * b))
            for i in range(len(pts) - 1):
                for k in range(sides):
                    p0, p1 = i * sides + k, i * sides + (k + 1) % sides
                    q0, q1 = p0 + sides, p1 + sides
                    F += [[p0, p1, q1], [p0, q1, q0]]
            n = len(V)
            V += [pts[0], pts[-1]]
            for k in range(sides):
                F.append([n, (k + 1) % sides, k])
                e = (len(pts) - 1) * sides
                F.append([n + 1, e + k, e + (k + 1) % sides])
            V, F = np.array(V), np.array(F)
            # outward: flip if the first face points at the axis
            fn = np.cross(V[F[0, 1]] - V[F[0, 0]], V[F[0, 2]] - V[F[0, 0]])
            if fn @ (V[F[0]].mean(0) - pts[0]) < 0:
                F = F[:, ::-1]
            out.append((V, F))
    return _join(out)


def lod_mesh(solid: Solid, V, F, target, cfg, cell, origin, base, h, hull=False, pre=None):
    """One LOD: decimated (or `pre` = a mesh built for it), back on the field, split into charts (uv by position),
    smooth normals from the field (split where faces meet sharply), tangents from the charts."""
    if pre is not None:
        V2, F2 = pre
    elif hull:
        V2, F2 = _hull(V, target)
    else:
        V2, F2 = _decimate(V, F, target)
        F2 = _drop_specks(V2, F2) if solid.cluster else F2
        V2 = _onto(solid.sd, V2, h, 2)
    # (degenerate faces after the move)
    ar = np.linalg.norm(np.cross(V2[F2[:, 1]] - V2[F2[:, 0]], V2[F2[:, 2]] - V2[F2[:, 0]]), axis=1)
    F2 = F2[ar > 1e-9]
    fnorm = np.cross(V2[F2[:, 1]] - V2[F2[:, 0]], V2[F2[:, 2]] - V2[F2[:, 0]])
    fnorm /= np.maximum(np.linalg.norm(fnorm, axis=1, keepdims=True), 1e-12)
    if pre is None and not hull:  # a face the decimation turned inside out (between a bush's lobes) is culled: a hole. Turn it back
        gc = _grad(solid.sd, V2[F2].mean(1), max(h * 4, 0.012))
        turned = (fnorm * gc).sum(1) < 0
        if turned.any():
            F2 = F2.copy()
            F2[turned] = F2[turned][:, ::-1]
            fnorm[turned] *= -1
    N = _smooth_normal(solid, V2, h)
    # a flipped smooth normal (thin parts): take the faces' own
    vn = np.zeros_like(V2)
    for c in range(3):
        np.add.at(vn, F2[:, c], fnorm)
    vn /= np.maximum(np.linalg.norm(vn, axis=1, keepdims=True), 1e-12)
    bad = (N * vn).sum(1) < 0.2
    N[bad] = vn[bad]
    chart = np.array([clutter.CHARTS.index((int(a), int(np.sign(n[a]) or 1))) for n, a in zip(fnorm, np.abs(fnorm).argmax(1))])
    sharp = math.cos(math.radians(cfg["paint"]["normals"])) if cfg["paint"]["normals"] > 0 else -2.0
    # corners: (vertex, chart, own-normal flag) -> output vertex
    P, Nn, UV, T, idx, key = [], [], [], [], np.zeros_like(F2), {}
    for fi in range(len(F2)):
        a, s = clutter.CHARTS[chart[fi]]
        for c in range(3):
            v = int(F2[fi, c])
            own = (fnorm[fi] @ N[v]) < sharp
            kk = (v, int(chart[fi]), fi if own else -1)
            if kk not in key:
                key[kk] = len(P)
                P.append(V2[v])
                Nn.append(fnorm[fi] if own else N[v])
            idx[fi, c] = key[kk]
    P, Nn = np.array(P), np.array(Nn)
    UV = np.zeros((len(P), 2))
    T = np.zeros((len(P), 4))
    vchart = np.zeros(len(P), int)
    for (v, ch, _), o in key.items():
        vchart[o] = ch
    for ch, (a, s) in enumerate(clutter.CHARTS):
        m = vchart == ch
        if not m.any():
            continue
        rect = _chart_rect(ch, cell)
        px = _uv_of(P[m], a, s, solid.lo, solid.hi, rect)
        UV[m] = (px + origin) / base
        T[m] = _tangents(Nn[m], a, s)
    return {"V": P, "N": Nn, "UV": UV, "T": T, "F": idx, "triangles": int(len(idx)), "chart": chart}


def _smooth_normal(solid, P, h):
    g = _grad(solid.sd, P, max(h * 4, 0.012))
    return g / np.maximum(np.linalg.norm(g, axis=1, keepdims=True), 1e-9)


def _tangents(N, a, s):
    """glTF TANGENT for a chart: xyz = the picture's +u direction made square to the normal, w so that
    cross(N, T) * w points UP the picture (glTF's +Y of a normal map; rows run down)."""
    ui, us, ri, rs = _chart_axes(a, s)
    tu = np.zeros(3)
    tu[ui] = us
    up = np.zeros(3)
    up[ri] = -rs
    T = tu[None] - N * (N @ tu)[:, None]
    ln = np.linalg.norm(T, axis=1, keepdims=True)
    T = np.where(ln > 1e-6, T / np.maximum(ln, 1e-6), np.cross(N, up)[..., :])
    w = np.sign((np.cross(N, T) * up[None]).sum(1))
    w[w == 0] = 1
    return np.c_[T, w]


def _hull(V, faces):
    """A convex hull with at most `faces` triangles: (V, F) outward. Grown greedily: from the six axis extremes, the
    point farthest outside the hull so far is added until the count is reached (the best outline for the count)."""
    from scipy.spatial import ConvexHull
    h = ConvexHull(V)
    P = V[h.vertices]
    if len(h.simplices) > faces:
        pick = list(dict.fromkeys([int(P[:, a].argmax()) for a in range(3)] + [int(P[:, a].argmin()) for a in range(3)]))
        while True:
            try:
                hh = ConvexHull(P[pick])
            except Exception:
                hh = None
            if hh is not None and len(hh.simplices) + 2 > faces:
                break
            if hh is None:
                rest = [i for i in range(len(P)) if i not in pick]
                if not rest:
                    break
                pick.append(rest[0])
                continue
            out = (P @ hh.equations[:, :3].T + hh.equations[:, 3]).max(1)
            out[pick] = -1
            i = int(out.argmax())
            if out[i] <= 1e-6:
                break
            pick.append(i)
        P = P[pick]
        h = ConvexHull(P)
        P = P[h.vertices]
        h = ConvexHull(P)
    F = h.simplices.copy()
    c = P.mean(0)
    fn = np.cross(P[F[:, 1]] - P[F[:, 0]], P[F[:, 2]] - P[F[:, 0]])
    flip = (fn * (P[F].mean(1) - c)).sum(1) < 0
    F[flip] = F[flip][:, ::-1]
    return P, F
