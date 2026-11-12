"""A part in pieces: split and decimate, patch offsets and seating, patches, hull and small pieces, lifting made
sheets, seam welds, fold guards, deviation, welded pieces. Part of the LODs (lods.py has the overview)."""
from __future__ import annotations

import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from scipy.spatial import cKDTree

from . import lods
from .lods_under import face_grid, under_depth

def _split(p: dict, tri_mesh: np.ndarray | None):
    """glTF vertices of a part: (key rows -> unique split vertices: src vertex, uv, normal, tangent, sign; triangles
    over them (T, 3); patch label per triangle)."""
    c = np.asarray(p["corner_vert"], np.int64)
    rows = np.concatenate([c[:, None].astype(np.float64), p["uv"], p["normal"], p["tangent"], p["sign"][:, None]], 1)
    key = np.round(rows * 1e5).astype(np.int64)
    _, first, inv = np.unique(key, axis=0, return_index=True, return_inverse=True)
    inv = inv.ravel()
    T = inv.reshape(-1, 3)
    n = len(first)
    # patches: triangles sharing a split vertex (and the same mesh of a several-mesh part)
    e = np.r_[T[:, [0, 1]], T[:, [1, 2]], T[:, [2, 0]]]
    g = coo_matrix((np.ones(len(e)), (e[:, 0], e[:, 1])), shape=(n, n))
    _, vlab = connected_components(g, directed=False)
    lab = vlab[T[:, 0]]
    if tri_mesh is not None:
        lab = lab * (int(tri_mesh.max()) + 1) + tri_mesh
    return first, T, lab


def _decimate(V: np.ndarray, F: np.ndarray, target: int, border: bool = True) -> tuple[np.ndarray, np.ndarray]:
    """pyfqmr to `target` triangles; border=True keeps every border edge, False lets border vertices collapse into
    border vertices only (fqmr never merges a border vertex with an interior one), so borders stay borders, coarser."""
    import pyfqmr
    q = pyfqmr.Simplify()
    q.setMesh(np.ascontiguousarray(V, np.float64), np.ascontiguousarray(F, np.int32))
    q.simplify_mesh(target_count=max(int(target), 4), aggressiveness=7, preserve_border=border, verbose=False)
    v, f, _ = q.getMesh()
    return np.asarray(v, np.float64), np.asarray(f, np.int64)


def _patch_offsets(V: np.ndarray, T: np.ndarray, panel: np.ndarray, piece: np.ndarray, Nc: np.ndarray):
    """(r58) For the vertices of `piece` triangles: (vertex ids, closest points' barycentrics / triangles on the `panel`
    triangles, signed offsets along the panel face normals (oriented by the panel's corner normals Nc), distances)."""
    from .rig_template import _closest_on_triangles
    pt = np.flatnonzero(panel)
    RT = V[T[pt]]
    nf = np.cross(RT[:, 1] - RT[:, 0], RT[:, 2] - RT[:, 0])
    nf *= np.sign((nf * Nc.reshape(-1, 3, 3)[pt].sum(1)).sum(1))[:, None]
    nf /= np.maximum(np.linalg.norm(nf, axis=1, keepdims=True), 1e-12)
    vs = np.unique(T[piece])
    k = min(8, len(RT))
    _, cand = cKDTree(RT.mean(1)).query(V[vs], k=k)
    cand = np.asarray(cand).reshape(len(vs), k)
    d = np.full(len(vs), np.inf)
    tri = np.zeros(len(vs), np.int64)
    bary = np.zeros((len(vs), 3))
    for j in range(k):
        t = cand[:, j]
        b, dj = _closest_on_triangles(V[vs], RT[t, 0], RT[t, 1], RT[t, 2])
        w = dj < d
        d[w], tri[w], bary[w] = dj[w], t[w], b[w]
    cp = np.einsum("nk,nkd->nd", bary, RT[tri])
    off = ((V[vs] - cp) * nf[tri]).sum(1)
    return vs, cp, nf[tri], off, d


def _seat_patches(V: np.ndarray, T: np.ndarray, panel: np.ndarray, piece: np.ndarray, Nc: np.ndarray,
                  P0: np.ndarray, off0: np.ndarray, reach: float = None) -> int:
    """(r58) LOD_SEAT_PATCHES: piece vertices onto the decimated panel at the LOD0 offset of their nearest LOD0 piece
    vertex (P0, off0). In place on V; returns the vertices moved."""
    reach = lods.LOD_SEAT_REACH if reach is None else reach
    if not piece.any() or not panel.any() or not len(P0):
        return 0
    vs, cp, nf, _, d = _patch_offsets(V, T, panel, piece, Nc)
    o = off0[cKDTree(P0).query(V[vs])[1]]
    ok = d < reach
    V[vs[ok]] = cp[ok] + nf[ok] * o[ok, None]
    return int(ok.sum())


def _patches(p: dict, outer: np.ndarray, small: np.ndarray) -> np.ndarray:
    """small (outer triangles in small pieces) kept only for pieces that lie on the rest of the outer shell."""
    if not small.any() or small.sum() == outer.sum():
        return np.zeros_like(small)
    T = np.asarray(p["corner_vert"], np.int64).reshape(-1, 3)
    V = np.asarray(p["verts"], np.float64)
    from .rig_template import _closest_on_triangles
    RT = V[T[outer & ~small]]
    kd = cKDTree(RT.mean(1))
    idx = np.flatnonzero(small)
    u, inv = np.unique(T[idx], return_inverse=True)
    inv = inv.reshape(-1, 3)
    e = np.r_[inv[:, [0, 1]], inv[:, [1, 2]]]
    _, lab = connected_components(coo_matrix((np.ones(len(e)), (e[:, 0], e[:, 1])), shape=(len(u), len(u))), directed=False)
    k = min(8, len(RT))
    _, cand = kd.query(V[u], k=k)
    cand = cand.reshape(len(u), k)
    d = np.full(len(u), np.inf)
    for j in range(k):
        t = cand[:, j]
        d = np.minimum(d, _closest_on_triangles(V[u], RT[t, 0], RT[t, 1], RT[t, 2])[1])
    med = np.array([np.median(d[lab == L]) for L in range(lab.max() + 1)])
    out = np.zeros_like(small)
    out[idx] = med[lab[inv[:, 0]]] < lods.LOD_PATCH_GAP
    return out


def _hull_pieces(po: dict, outer: np.ndarray, small: np.ndarray, small_o: np.ndarray, made: np.ndarray | None = None):
    """po (corner arrays) with each connected piece among `small` replaced by its convex hull on its own vertices (each
    hull corner takes the attributes of the vertex's first corner in the piece, its normal turned to face the hull's
    outside); the hull triangles go last. Returns (po, outer, small, small_o) for the new triangle order."""
    from scipy.spatial import ConvexHull
    T = np.asarray(po["corner_vert"], np.int64).reshape(-1, 3)
    V = np.asarray(po["verts"], np.float64)
    idx = np.flatnonzero(small)
    u, inv = np.unique(T[idx], return_inverse=True)
    inv = inv.reshape(-1, 3)
    e = np.r_[inv[:, [0, 1]], inv[:, [1, 2]]]
    _, lab = connected_components(coo_matrix((np.ones(len(e)), (e[:, 0], e[:, 1])), shape=(len(u), len(u))), directed=False)
    tl = lab[inv[:, 0]]
    ckeys = [k for k in ("uv", "normal", "tangent", "sign") if po.get(k) is not None]
    newT, newc = [], {k: [] for k in ckeys}
    drop = np.zeros(len(T), bool)
    for c in np.unique(tl):
        tf = idx[tl == c]
        vids = np.unique(T[tf])
        if len(vids) < 5:
            continue
        sv_ = np.linalg.svd(V[vids] - V[vids].mean(0), compute_uv=False)
        if sv_[-1] < lods.LOD_KEEP_PIECE_HULL_FLAT * sv_[0]:  # (a flat piece: a label, a patch; its hull is the piece twice)
            continue
        try:
            h = ConvexHull(V[vids])
        except Exception:
            continue
        S = vids[h.simplices]
        nf = np.cross(V[S[:, 1]] - V[S[:, 0]], V[S[:, 2]] - V[S[:, 0]])
        flip = (nf * h.equations[:, :3]).sum(1) < 0
        S[flip] = S[flip][:, [0, 2, 1]]
        first = {}
        for ci, v in zip(np.arange(len(tf) * 3).reshape(-1, 3)[:, :].ravel(), T[tf].ravel()):
            first.setdefault(int(v), int(tf[ci // 3] * 3 + ci % 3))
        corners = np.array([first[int(v)] for v in S.ravel()])
        nrm_h = np.repeat(h.equations[:, :3], 3, 0)
        for k in ckeys:
            a = np.asarray(po[k])[corners]
            if k == "normal":
                a = np.asarray(a, np.float64)
                a = np.where(((a * nrm_h).sum(1) < 0.2)[:, None], nrm_h, a)
            newc[k].append(a)
        newT.append(S)
        drop[tf] = True
    if not newT:
        return (po, outer, small, small_o) if made is None else (po, outer, small, small_o, made)
    keepc = np.repeat(~drop, 3)
    out = dict(po)
    nT = np.concatenate(newT)
    out["corner_vert"] = np.r_[np.asarray(po["corner_vert"], np.int64)[keepc], nT.ravel()]
    for k in ckeys:
        out[k] = np.concatenate([np.asarray(po[k])[keepc], np.concatenate(newc[k]).astype(np.asarray(po[k]).dtype)])
    add = np.zeros(len(nT), bool)
    res = (out, np.r_[outer[~drop], add], np.r_[small[~drop], ~add], np.r_[small_o[~drop], add])
    return res if made is None else res + (np.r_[made[~drop], add],)


def _small_pieces(corner_vert, among: np.ndarray, max_tris: int) -> np.ndarray:
    """Triangles (of those in `among`) whose connected piece (shared vertices) has fewer than max_tris triangles."""
    T = np.asarray(corner_vert, np.int64).reshape(-1, 3)
    idx = np.flatnonzero(among)
    out = np.zeros(len(T), bool)
    if not len(idx):
        return out
    u, inv = np.unique(T[idx], return_inverse=True)
    inv = inv.reshape(-1, 3)
    e = np.r_[inv[:, [0, 1]], inv[:, [1, 2]]]
    _, lab = connected_components(coo_matrix((np.ones(len(e)), (e[:, 0], e[:, 1])), shape=(len(u), len(u))), directed=False)
    tl = lab[inv[:, 0]]
    out[idx] = np.bincount(tl)[tl] < max_tris
    return out


def _lift_made(out: dict, n: int, gap: float = None, reach: float = None) -> int:
    """(r54) Made pieces (triangles after the two shells) put back OVER their garment's decimated outer shell: decimated
    apart, the shell's error (mm) is bigger than a pocket's lift off it (~2.6 mm median on Tess's coat), so the coat came
    through the pockets / lapels. Positions only; returns the vertices moved. In place on out["verts"]."""
    gap = lods.LOD_MADE_GAP if gap is None else gap
    reach = lods.LOD_MADE_REACH if reach is None else reach
    cv = np.asarray(out["corner_vert"], np.int64)
    rest_c = cv[6 * n:]
    if not len(rest_c):
        return 0
    V = np.asarray(out["verts"], np.float64).copy()
    made = {"verts": V, "corner_vert": rest_c, "normal": np.asarray(out["normal"], np.float64)[6 * n:]}
    cover = {"verts": V, "corner_vert": cv[:3 * n]}
    vid, N, _, t = under_depth(made, [cover], reach)
    bad = np.isfinite(t) & (t > -gap)  # (the shell should be INSIDE a made piece: t <= -gap)
    if not bad.any():
        return 0
    D = np.zeros_like(V)
    D[vid[bad]] = (t[bad] + gap)[:, None] * N[bad]
    if lods.LOD_LIFT_RIGID and lods.LOD_KEEP_PIECE:  # (r56) a small piece (a button) moves as one: lifted vertex by vertex, rc2e's
        # LOD2 buttons (kept whole) came out lumpy. Each takes its largest lift along its mean lift direction.
        T = rest_c.reshape(-1, 3)
        sp = _small_pieces(rest_c, np.ones(len(T), bool), lods.LOD_KEEP_PIECE)
        if sp.any():
            u, inv = np.unique(T[sp], return_inverse=True)
            inv = inv.reshape(-1, 3)
            e = np.r_[inv[:, [0, 1]], inv[:, [1, 2]]]
            _, lab = connected_components(coo_matrix((np.ones(len(e)), (e[:, 0], e[:, 1])), shape=(len(u), len(u))),
                                          directed=False)
            for L in np.unique(lab):
                vs = u[lab == L]
                d = D[vs]
                mag = np.linalg.norm(d, axis=1)
                if mag.max() <= 0:
                    continue
                dirn = d.sum(0)
                dirn /= max(np.linalg.norm(dirn), 1e-12)
                D[vs] = dirn * mag.max()
    moved = np.linalg.norm(D, axis=1) > 0
    V += D
    out["verts"] = V.astype(np.float32)
    return int(moved.sum())


def _weld_seams(V: np.ndarray, F: np.ndarray, r: float) -> np.ndarray:
    """F with border vertices (on an edge of one triangle) within `r` of each other merged into one (the lowest index);
    triangles that collapse are dropped."""
    F = np.asarray(F, np.int64)
    if not len(F):
        return F
    E = np.sort(np.r_[F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]], 1)
    u, c = np.unique(E, axis=0, return_counts=True)
    bv = np.unique(u[c == 1])
    if len(bv) < 2:
        return F
    pr = cKDTree(V[bv]).query_pairs(r, output_type="ndarray")
    if not len(pr):
        return F
    n = len(bv)
    if lods.LOD_SEAM_WELD_NO_CHAIN:  # (r60) clusters grown pair by pair, nearest first, never joining two vertices of one edge
        # or two farther apart than r: the connected components of all pairs within r CHAINED along densely sampled
        # borders (consecutive vertices < r apart) into strips merged to one vertex, collapsing whole rows of triangles:
        # rc2j's LOD2 jeans lost the crotch (a slit at the fly, 41 mm off LOD0; 95 of 107 crotch vertices > 6 mm off)
        es = set(map(tuple, u.tolist()))
        Vb = V[bv]
        dpr = np.linalg.norm(Vb[pr[:, 0]] - Vb[pr[:, 1]], axis=1)
        par = np.arange(n)
        mem = {i: [i] for i in range(n)}

        def find(i):
            while par[i] != i:
                par[i] = par[par[i]]
                i = par[i]
            return i
        for a, b in pr[np.argsort(dpr)]:
            ra, rb = find(a), find(b)
            if ra == rb:
                continue
            ma, mb = mem[ra], mem[rb]
            ga, gb = bv[ma], bv[mb]
            if any((min(x, y), max(x, y)) in es for x in ga for y in gb):
                continue
            if np.linalg.norm(Vb[ma][:, None] - Vb[mb][None], axis=2).max() > r:
                continue
            par[rb] = ra
            mem[ra] = ma + mb
            del mem[rb]
        lab = np.array([find(i) for i in range(n)])
    else:
        _, lab = connected_components(coo_matrix((np.ones(len(pr)), (pr[:, 0], pr[:, 1])), shape=(n, n)), directed=False)
    rep = np.full(lab.max() + 1, np.iinfo(np.int64).max)
    np.minimum.at(rep, lab, bv)
    m = np.arange(len(V))
    m[bv] = rep[lab]
    F2 = m[F]
    ok = (F2[:, 0] != F2[:, 1]) & (F2[:, 1] != F2[:, 2]) & (F2[:, 2] != F2[:, 0])
    return F2[ok]


def _folds(V0, F0, V, F) -> np.ndarray:
    """New triangles (V, F) wound against the LOD0 triangle (V0, F0) nearest them (a collapse folded them over)."""
    if not len(F):
        return np.zeros(0, bool)
    P0 = V0[F0]
    n0 = np.cross(P0[:, 1] - P0[:, 0], P0[:, 2] - P0[:, 0])
    Pn = V[F]
    gn = np.cross(Pn[:, 1] - Pn[:, 0], Pn[:, 2] - Pn[:, 0])
    _, nn = cKDTree(P0.mean(1)).query(Pn.mean(1))
    return (gn * n0[nn]).sum(1) < 0


def _guard_folds(V0, F0, Vw, Fw, ratio, tgt):
    """(r56) Vw, Fw (F0 on V0 decimated) with its folds redone: see LOD_FOLD_GUARD."""
    bad = _folds(V0, F0, Vw, Fw)
    if not bad.any():
        return Vw, Fw
    Pn = Vw[Fw[bad]]
    reach = lods.LOD_FOLD_GROW * np.max([np.linalg.norm(Pn[:, (i + 1) % 3] - Pn[:, i], axis=1) for i in range(3)], 0)
    c0 = V0[F0].mean(1)
    kd = cKDTree(c0)
    cut = np.zeros(len(F0), bool)
    for c, rr in zip(Pn.mean(1), reach):
        cut[kd.query_ball_point(c, rr)] = True
    if cut.all() or not cut.any():
        return Vw, Fw
    Fr, Fs = F0[~cut], F0[cut]
    for x in lods.LOD_FOLD_GUARD:
        rs = min(1.0, x * ratio)
        ts = len(Fs) if rs >= 0.999 else int(round(len(Fs) * rs))
        Vs, Fs_ = (V0, Fs) if rs >= 0.999 else _decimate(V0, Fs, ts)
        Vr, Fr_ = _decimate(V0, Fr, max(tgt - len(Fs_), int(round(len(Fr) * ratio * 0.5))))
        if not (_folds(V0, F0, Vs, Fs_).any() or _folds(V0, F0, Vr, Fr_).any()):
            break
    else:
        Vs, Fs_ = V0, Fs
    return np.r_[Vr, Vs], np.r_[Fr_, Fs_ + len(Vr)]


def _deviation(V0: np.ndarray, V: np.ndarray, F: np.ndarray, k: int = 8) -> float:
    """the largest distance from a vertex of V0 to the triangles (V, F), sampled on a barycentric grid (k steps per edge)."""
    S = np.r_[np.einsum("gk,tkc->tgc", face_grid(k), V[F]).reshape(-1, 3), V]
    return float(cKDTree(S).query(V0)[0].max())


def _welded_pieces(p, pieces, src, tri_mesh, mnames, ratio, mesh_ratios, nt):
    """pieces as lod_part's per-patch loop makes them, from a welded decimation: each mesh (tri_mesh group) decimated on
    its part vertices (only true mesh borders kept), every new triangle given to the patch whose LOD0 triangle centroid
    is nearest its own; a patch's new vertices are then the corners of its triangles (split per patch, so uv seams
    stay seams)."""
    P = np.asarray(p["verts"], np.float64)
    Tall = np.zeros((nt, 3), np.int64)
    labt = np.zeros(nt, np.int64)
    info = {}
    for L, tf, vs, Tl_loc, Vl, Vd, Fd in pieces:
        Tall[tf] = src[vs[Tl_loc]]
        labt[tf] = L
        info[L] = (tf, vs, Tl_loc, Vl)
    grp = tri_mesh if tri_mesh is not None else np.zeros(nt, np.int64)
    out = []
    gtree = {}
    if lods.LOD_BORDER_SHARED and len(np.unique(grp)) > 1:  # (r59) each group's vertices, to find borders shared with another
        for g in np.unique(grp):
            gtree[g] = cKDTree(P[np.unique(Tall[grp == g])])
    for g in np.unique(grp):
        tg = np.flatnonzero(grp == g)
        r_ = ratio
        if mesh_ratios and tri_mesh is not None:
            r_ = float(mesh_ratios.get(mnames[int(g)], ratio))
        gv, Fl = np.unique(Tall[tg], return_inverse=True)
        Fl = Fl.reshape(-1, 3)
        if r_ >= 0.999 or len(tg) < lods.MIN_PATCH:
            Vw, Fw = P[gv], Fl
        else:
            tgt = int(round(len(tg) * r_))
            if lods.LOD_SEAM_WELD:  # (r53) sim seams closed first: border vertices this close are one vertex
                Fl = _weld_seams(P[gv], Fl, lods.LOD_SEAM_WELD)
            Vw, Fw = _decimate(P[gv], Fl, tgt)
            shared_, bo_ = False, False
            if gtree:  # (r59) a border this group shares with another (a fly / placket piece on its panel) must not move
                E_ = np.sort(np.r_[Fl[:, [0, 1]], Fl[:, [1, 2]], Fl[:, [2, 0]]], 1)
                u_, c_ = np.unique(E_, axis=0, return_counts=True)
                bv_ = P[gv][np.unique(u_[c_ == 1])]
                shared_ = len(bv_) > 0 and any(
                    np.isfinite(t_.query(bv_, distance_upper_bound=lods.LOD_SEAM_WELD)[0]).any() for g2, t_ in gtree.items() if g2 != g)
            if lods.LOD_BORDER_OVER and not shared_ and len(Fw) > lods.LOD_BORDER_OVER * max(tgt, 1):
                Vb, Fb = _decimate(P[gv], Fl, tgt, border=False)
                if 0 < len(Fb) < len(Fw):
                    Vw, Fw, bo_ = Vb, Fb, True
            if lods.LOD_DEV_MAX and len(Fw) and len(tg) >= lods.LOD_DEV_MIN_TRIS:  # (r60) a decimation that strays far from LOD0 is redone at a bigger target
                for _ in range(lods.LOD_DEV_TRIES):
                    if _deviation(P[gv], Vw, Fw) <= lods.LOD_DEV_MAX * (lods.LOD_DEV_REF / max(r_, 1e-3)) ** lods.LOD_DEV_POW:
                        break
                    tgt = int(round(tgt * lods.LOD_DEV_GROW))
                    if tgt >= len(Fl):
                        Vw, Fw = P[gv], Fl
                        break
                    Vw, Fw = _decimate(P[gv], Fl, tgt, border=not bo_)  # (as the pass it redoes: border collapses
                    # too where the border-over pass was taken)
            if len(Fw) == 0:
                Vw, Fw = P[gv], Fl
            if lods.LOD_FOLD_GUARD:
                Vw, Fw = _guard_folds(P[gv], Fl, Vw, Fw, r_, tgt)
        c0 = P[Tall[tg]].mean(1)
        _, nn = cKDTree(c0).query(Vw[Fw].mean(1))
        lab_new = labt[tg[nn]]
        for L in np.unique(lab_new):
            Fd_ = Fw[lab_new == L]
            u, Fd_loc = np.unique(Fd_, return_inverse=True)
            tf, vs, Tl_loc, Vl = info[L]
            out.append((L, tf, vs, Tl_loc, Vl, Vw[u], Fd_loc.reshape(-1, 3)))
    return out
