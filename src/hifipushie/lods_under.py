"""Layers under covers: depth under a cover, orientation to covers, culling what is covered, ringed islands, stray
flaps, push_under_layers. Part of the LODs (lods.py has the overview)."""
from __future__ import annotations

import os
from pathlib import Path

import numpy as np
from scipy.spatial import cKDTree

from . import lods

def _vertex_out(p: dict) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """A part's vertices that carry its outward direction, that direction, and the follower pairs. A two-sided garment
    (p["shell"], as _lod_shell writes it: outer triangles, then the inner ones wound the other way, then the rest):
    the outer shell's vertices with their normals, each inner-shell vertex following its outer twin. Any other part:
    every used vertex with its corners' mean normal. Made pieces / buttons after the shells are left alone."""
    V = np.asarray(p["verts"], np.float64)
    cv = np.asarray(p["corner_vert"], np.int64)
    Nc = np.asarray(p["normal"], np.float64)
    if p.get("shell"):
        n = int(p["shell"]["outer"])
        co = cv[:3 * n]
        ci = cv[3 * n:6 * n].reshape(-1, 3)[:, [0, 2, 1]].ravel()  # the inner corners in their outer twins' order
        lead = co
        Nl = Nc[:3 * n]
        fol = np.c_[ci, co] if len(ci) == len(co) else np.zeros((0, 2), np.int64)
    else:
        lead, Nl, fol = cv, Nc, np.zeros((0, 2), np.int64)
    N = np.zeros_like(V)
    np.add.at(N, lead, Nl)
    vid = np.unique(lead)
    N = N[vid]
    N /= np.maximum(np.linalg.norm(N, axis=1, keepdims=True), 1e-12)
    fol = np.unique(fol, axis=0) if len(fol) else fol
    return vid, N, fol[fol[:, 0] != fol[:, 1]] if len(fol) else fol


def under_depth(p: dict, covers: list[dict], reach: float = lods.LOD_UNDER_REACH):
    """For each outward vertex of `p` (_vertex_out): the signed distance along its outward normal to the NEAREST
    surface of `covers` within `reach` either way (+ = the cover is outside it, as it should be; - = the vertex pokes
    through), nan where no cover is in reach."""
    vid, N, fol = _vertex_out(p)
    V = np.asarray(p["verts"], np.float64)
    if lods.LOD_UNDER_ORIENT and len(vid) and covers:  # (r67) a fold's vertex normal can point INTO the body: its cover then
        # reads as behind it (a poke) and the push moved it out (rc2s LOD0: 2 sweater vertices 5 mm out of the coat's
        # back, none before the push). Out = the side the nearest cover surface faces.
        Q, QN = _cover_samples(covers)
        d, j = cKDTree(Q).query(V[vid], distance_upper_bound=reach)
        ok = np.isfinite(d)
        flip = ok & ((N * QN[np.where(ok, j, 0)]).sum(1) < 0)
        if flip.any():
            N = np.where(flip[:, None], -N, N)
    if lods.LOD_UNDER_ORIENT:
        N = orient_to_covers(V[vid], N, covers, reach)
    return vid, N, fol, cover_depth(V[vid], N, covers, reach)


def _cover_samples(covers: list[dict]) -> tuple[np.ndarray, np.ndarray]:
    """Points on the covers' OUTER shells (triangle centres and corners) with their faces' outward normals."""
    Q, QN = [], []
    for c in covers:
        cv = np.asarray(c["corner_vert"], np.int64)
        if c.get("shell"):
            cv = cv[:3 * int(c["shell"]["outer"])]
        T = np.asarray(c["verts"], np.float64)[cv.reshape(-1, 3)]
        n = np.cross(T[:, 1] - T[:, 0], T[:, 2] - T[:, 0])
        n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-12)
        Q += [T.mean(1), T.reshape(-1, 3)]
        QN += [n, np.repeat(n, 3, 0)]
    return np.concatenate(Q), np.concatenate(QN)


def orient_to_covers(P: np.ndarray, N: np.ndarray, covers: list[dict], reach: float = lods.LOD_UNDER_REACH) -> np.ndarray:
    """(Garrett s7) N flipped where it points against the outward normal of the nearest cover vertex within `reach`.
    A garment's own winding can be mixed (Garrett's frozen shirt: about half its outer-shell normals point into the arm
    at the forearms), and push_under_layers moves a vertex "in" along its normal: a flipped one was driven OUT through
    the jacket sleeve (v6b: up to 39 mm, a white shirt mass over the right forearm at LOD0-2). The covers (the jacket's
    outer shell) know which way is out."""
    if not len(P) or not covers:
        return N
    cP, cN = [], []
    for c in covers:
        if "normal" not in c:  # (a cover without normals: nothing to orient by)
            continue
        cv_, cn_, _ = _vertex_out(c)
        if len(cv_):
            cP.append(np.asarray(c["verts"], np.float64)[cv_])
            cN.append(cn_)
    if not cP:
        return N
    d, i = cKDTree(np.concatenate(cP)).query(P)
    flip = (d < reach) & ((N * np.concatenate(cN)[np.minimum(i, sum(len(x) for x in cP) - 1)]).sum(1) < 0)
    return np.where(flip[:, None], -N, N)


def cover_depth(P: np.ndarray, N: np.ndarray, covers: list[dict], reach: float = lods.LOD_UNDER_REACH) -> np.ndarray:
    """under_depth's test for any points P with outward directions N (vertices, or face centroids: r57)."""
    tris = [np.asarray(c["verts"], np.float64)[np.asarray(c["corner_vert"], np.int64).reshape(-1, 3)] for c in covers]
    t_ = np.full(len(P), np.nan)
    if not tris or not sum(len(t) for t in tris) or not len(P):
        return t_
    T = np.concatenate(tris)
    A, E1, E2 = T[:, 0], T[:, 1] - T[:, 0], T[:, 2] - T[:, 0]
    cen = T.mean(1)
    rad = float(np.linalg.norm(T - cen[:, None], axis=2).max())
    tree = cKDTree(cen)
    for a, nb in enumerate(tree.query_ball_point(P, reach + rad)):
        if not nb:
            continue
        nb = np.asarray(nb)
        d = N[a]  # Moller-Trumbore along the line of the normal
        pv = np.cross(d, E2[nb])
        det = (E1[nb] * pv).sum(1)
        ok = np.abs(det) > 1e-12
        inv = np.where(ok, 1.0 / np.where(ok, det, 1.0), 0.0)
        tv = P[a] - A[nb]
        u = (tv * pv).sum(1) * inv
        qv = np.cross(tv, E1[nb])
        v = (qv @ d) * inv
        t = (E2[nb] * qv).sum(1) * inv
        eps = 1e-4
        hit = ok & (u >= -eps) & (v >= -eps) & (u + v <= 1 + eps) & (np.abs(t) < reach)
        if hit.any():  # (the nearest either way: a far hit across a limb or a fold is another layer's business)
            th_ = t[hit]
            t_[a] = th_[np.argmin(np.abs(th_))]
    return t_


def under_at_lod0(p: dict, covers: list[dict], reach: float = lods.LOD_UNDER_REACH, share: bool = False) -> tuple:
    """(r54) A part's outward vertices at LOD0 and whether each lies UNDER `covers` there (a cover in reach outside it):
    push_under_layers' `masks`, for parts worn under garments that are not garments themselves (socks, the body),
    so only what was under a garment at LOD0 is put back under it (a shoe over the jeans' hem stays over it)."""
    vid, N_, _, t = under_depth(p, covers, reach)
    under = np.isfinite(t) & (t > 0)
    if share:  # (r55) ... and the share of its vertices with a cover in reach that are under it
        return (np.asarray(p["verts"], np.float64)[vid], under, float(under.sum() / max(int(np.isfinite(t).sum()), 1)),
                np.isfinite(t) & (t < 0), N_)  # (and the vertices OVER a cover at LOD0, and (r59) their LOD0 normals)
    return np.asarray(p["verts"], np.float64)[vid], under


def cull_covered(p: dict, P0: np.ndarray, under0: np.ndarray, rim: float = lods.LOD_UNDER_CULL_RIM) -> np.ndarray:
    """(r60) keep mask per triangle of `p` (any LOD of a worn part): False where all three corners' nearest LOD0 outward
    point (P0, under_at_lod0's) was under a cover (under0) and lies more than `rim` from every LOD0 point that was not."""
    nt = len(p["corner_vert"]) // 3
    under0 = np.asarray(under0, bool)
    if not len(P0) or not under0.any():
        return np.ones(nt, bool)
    V = np.asarray(p["verts"], np.float64)
    deep = under0[cKDTree(P0).query(V)[1]]
    if (~under0).any():
        deep &= cKDTree(np.asarray(P0)[~under0]).query(V)[0] > rim
    T = np.asarray(p["corner_vert"], np.int64).reshape(-1, 3)
    return ~deep[T].all(1)


def face_grid(k: int) -> np.ndarray:
    """(r58) Barycentric sample weights inside a triangle: the centroid (r57's test) and a grid of k steps per edge
    without the corners."""
    if k <= 1:
        return np.full((1, 3), 1.0 / 3.0)
    B = np.array([(i, j, k - i - j) for i in range(k + 1) for j in range(k + 1 - i)], float) / k
    return np.r_[np.full((1, 3), 1.0 / 3.0), B[B.max(1) < 1.0 - 1e-9]]


def ringed_islands(F: np.ndarray, deep_t: np.ndarray, t: np.ndarray, nv: int, most: int | None = None) -> np.ndarray:
    """(r65) faces (rows of F) that stand deeper outside their cover than the face test trusts (deep_t < 0 where t, the
    trusted depth, is inf) but form a small island (<= most faces, sharing vertices) whose every neighbouring face is
    under the cover (t finite, >= 0): a flap poking through, not a garment running outside its cover (an open front's
    edge has neighbours with no cover: kept)."""
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components
    most = lods.LOD_UNDER_ISLAND if most is None else most
    deep = np.isfinite(deep_t) & (deep_t < 0) & ~np.isfinite(t)
    out = np.zeros(len(F), bool)
    if not deep.any() or not most:
        return out
    di = np.flatnonzero(deep)
    A = coo_matrix((np.ones(3 * len(di)), (np.repeat(np.arange(len(di)), 3), F[di].ravel())), shape=(len(di), nv)).tocsr()
    _, lab = connected_components(A @ A.T, directed=False)
    size = np.bincount(lab)
    vlab = np.full(nv, -1)
    vlab[F[di].ravel()] = np.repeat(lab, 3)
    rest = np.flatnonzero(~deep)
    touch = vlab[F[rest]]  # each other face's island (by any corner), -1 = none
    ok = np.ones(len(size), bool)
    bad_n = ~(np.isfinite(t[rest]) & (t[rest] >= 0))  # a neighbour not under the cover
    for k in range(3):
        m = (touch[:, k] >= 0) & bad_n
        ok[touch[m, k]] = False
    ringed = ok & (size <= most) & (np.bincount(vlab[vlab >= 0], minlength=len(size)) > 0)
    out[di] = ringed[lab]
    return out


def stray_flaps(p: dict, covers: list[dict], reach: float = lods.LOD_UNDER_REACH, far: float | None = None,
                most: int | None = None) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """(r66) push_under_layers' flaps: (vertex ids, how far outside, the cover's outward normal there). Candidates are
    outward vertices with no cover along their normal within `reach` (under_depth nan); "outside" = the nearest cover
    sample (outer-shell triangle centres and corners, normals from their faces) within `far` has the vertex on its outward
    side. Kept only as small islands (<= most vertices, by the part's faces) every neighbour of which lies under a cover."""
    far = lods.LOD_UNDER_STRAY if far is None else far
    most = lods.LOD_UNDER_ISLAND if most is None else most
    e = (np.zeros(0, np.int64), np.zeros(0), np.zeros((0, 3)))
    if not far or not covers:
        return e
    vid, N, fol, t = under_depth(p, covers, reach)
    cand = vid[~np.isfinite(t)]
    if not len(cand):
        return e
    Q, QN = [], []
    for c in covers:
        cv = np.asarray(c["corner_vert"], np.int64)
        if c.get("shell"):
            cv = cv[:3 * int(c["shell"]["outer"])]
        T = np.asarray(c["verts"], np.float64)[cv.reshape(-1, 3)]
        n = np.cross(T[:, 1] - T[:, 0], T[:, 2] - T[:, 0])
        n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-12)
        Q += [T.mean(1), T.reshape(-1, 3)]
        QN += [n, np.repeat(n, 3, 0)]
    Q, QN = np.concatenate(Q), np.concatenate(QN)
    V = np.asarray(p["verts"], np.float64)
    d, j = cKDTree(Q).query(V[cand], distance_upper_bound=far)
    ok = np.isfinite(d)
    j = np.where(ok, j, 0)
    s = ((V[cand] - Q[j]) * QN[j]).sum(1)
    out = ok & (s > 0)
    if not out.any():
        return e
    cand, s, nq = cand[out], s[out], QN[j[out]]
    tq = cover_depth(V[cand], nq, covers, far)  # and the cover really lies behind it along that normal (an open front's
    sure = np.isfinite(tq) & (tq < 0)           # edge, beside a lapel, has none there)
    cand, s, nq = cand[sure], -tq[sure], nq[sure]
    if not len(cand):
        return e
    F = np.asarray(p["corner_vert"], np.int64).reshape(-1, 3)
    if p.get("shell"):
        F = F[:int(p["shell"]["outer"])]
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components
    nv = len(V)
    E_ = np.concatenate([F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]])
    A = coo_matrix((np.ones(len(E_)), (E_[:, 0], E_[:, 1])), shape=(nv, nv)).tocsr()
    A = ((A + A.T) > 0).tocsr()
    # the island: these with the vertices already poking (cover inside them along their normal: the vertex test
    # moves those); every vertex next to it must lie under the cover
    pk = vid[np.isfinite(t) & (t < 0)]
    mem_ = np.union1d(cand, pk)
    sub = A[mem_][:, mem_]
    _, lab = connected_components(sub, directed=False)
    under = np.zeros(nv, bool)
    under[vid[np.isfinite(t) & (t >= 0)]] = True
    keep = np.zeros(len(mem_), bool)
    for k in range(lab.max() + 1):
        mem = mem_[lab == k]
        if len(mem) > most or not np.isin(mem, cand).any():
            continue
        ring = np.setdiff1d(A[mem].indices, mem)
        if len(ring) and under[ring].all():
            keep[lab == k] = True
    k_ = np.isin(cand, mem_[keep])
    return cand[k_], s[k_], nq[k_]


def push_under_layers(parts: dict, stack: dict, gap: float = lods.LOD_UNDER_GAP, reach: float = lods.LOD_UNDER_REACH,
                      rounds: int = 3, masks: dict | None = None, face_deep: float | None = None) -> dict:
    """(r53) After each garment is decimated ALONE for a LOD, the under garments are put back under the decimated
    covers: rc2's LOD1-3 showed the jeans through the coat skirt and the sweater through the coat's elbows / back
    (each decimation's error, several mm, is bigger than the layer gaps; LOD0 was clean). stack: {under part: [the
    parts over it, transitively]}. Every outward vertex of the under part whose nearest cover along its normal (within
    `reach`, either way) is less than `gap` outside it moves in along that normal to `gap` under it; a two-sided
    garment's inner shell moves with its outer one. Weights, uv, shapes are per vertex and stay; positions only.
    masks: {under part: under_at_lod0(...)}: (r54) only vertices whose nearest LOD0 vertex was under a cover move.
    Returns {under part: {"poking0", "poking", "moved"}} (poking: vertices with the cover inside them)."""
    rep = {}
    for un, ovs in stack.items():
        if un not in parts:
            continue
        covers = [parts[o] for o in ovs if o in parts]
        if not covers:
            continue
        p = dict(parts[un])
        V = np.asarray(p["verts"], np.float64).copy()
        moved = np.zeros(len(V), bool)
        poke0 = None
        pokef = 0
        nflap = 0
        if os.environ.get("HP_PUSH_DUMP"):  # (r67) stray_flaps' input as the export sees it (diagnosis)
            import pickle
            Path(os.environ["HP_PUSH_DUMP"]).mkdir(parents=True, exist_ok=True)
            with open(Path(os.environ["HP_PUSH_DUMP"]) / f"push_{un}_{len(p['corner_vert'])}.pkl", "wb") as fh:
                pickle.dump({"p": p, "covers": covers, "ovs": ovs, "gap": gap, "reach": reach}, fh)
        if lods.LOD_UNDER_STRAY:  # (r66) flaps through the cover that no normal-line test sees: in along the cover's normal
            fi, fs, fn = stray_flaps(p, covers, reach)
            if len(fi):
                dv = np.zeros_like(V)
                dv[fi] = -(fs + gap)[:, None] * fn
                fol0 = _vertex_out(p)[2]
                if len(fol0):
                    dv[fol0[:, 0]] = dv[fol0[:, 1]]
                    moved[fol0[:, 0]] |= np.isin(fol0[:, 1], fi)
                V = V + dv
                moved[fi] = True
                nflap = len(fi)
        for _ in range(rounds):
            p["verts"] = V
            vid, N, fol, t = under_depth(p, covers, reach)
            ok_ = None
            if masks and un in masks and len(masks[un][0]):
                ok_ = masks[un][1][cKDTree(masks[un][0]).query(V[vid])[1]]
                t = np.where(ok_, t, np.nan)
            bad = np.isfinite(t) & (t < gap)
            sv = np.zeros(len(V))
            sv[vid[bad]] = t[bad] - gap
            if lods.LOD_UNDER_FACES:  # (r57) a long face can poke through a cover that bends between its vertices, all of
                # them under (rc2f LOD1: three sweater faces 3.5 mm outside the coat beside the lapel, their vertices 2 mm
                # under): each outward face is tested along its normal too (r58: at a grid of points); a poking face moves its
                # corners in (along their own normals) until its worst point is `gap` under
                F_ = np.asarray(p["corner_vert"], np.int64).reshape(-1, 3)
                if p.get("shell"):
                    F_ = F_[:int(p["shell"]["outer"])]
                isv = np.zeros(len(V), bool)
                isv[vid] = True if ok_ is None else ok_
                F_ = F_[isv[F_].all(1)]
                if len(F_):
                    Nv = np.zeros_like(V)
                    Nv[vid] = N
                    nf = np.cross(V[F_[:, 1]] - V[F_[:, 0]], V[F_[:, 2]] - V[F_[:, 0]])
                    nf *= np.sign((nf * Nv[F_].sum(1)).sum(1))[:, None]
                    nf /= np.maximum(np.linalg.norm(nf, axis=1, keepdims=True), 1e-12)
                    B = face_grid(lods.LOD_UNDER_FACE_GRID)
                    tf = cover_depth(np.einsum("bk,fkd->fbd", B, V[F_]).reshape(-1, 3), np.repeat(nf, len(B), 0), covers,
                                     reach).reshape(len(F_), len(B))
                    fd_ = face_deep or lods.LOD_UNDER_FACE_DEEP
                    tall = np.where(np.isfinite(tf), tf, np.inf).min(1)
                    tf = np.where(np.isfinite(tf) & (tf > -fd_), tf, np.inf).min(1)
                    if lods.LOD_UNDER_ISLAND:  # (r65) a deep face is a poke after all when it is a small island ringed by faces
                        tf = np.where(ringed_islands(F_, tall, tf, len(V)), tall, tf)  # under the cover (rc2p's coat speck)
                    bf = np.isfinite(tf) & (tf < 0)
                    if bf.any():  # (r67) each corner moves along its own normal only as far as that normal goes in:
                        # depth / (its normal . the face's), and not at all when it turns > 60 deg from the face (a fold's
                        # corner whose normal points into the body moved 20 mm OUT: rc2q-s's coat-back speck WAS this push)
                        Fb = F_[bf]
                        al = np.einsum("fkd,fd->fk", Nv[Fb], nf[bf])
                        need = np.where(al >= lods.LOD_UNDER_FACE_ALIGN, (tf[bf] - gap)[:, None] / np.maximum(al, lods.LOD_UNDER_FACE_ALIGN), 0.0)
                        np.minimum.at(sv, Fb.ravel(), need.ravel())
                        pokef += int(bf.sum()) if poke0 is None else 0
            sel_ = sv[vid] < 0
            if poke0 is None:
                poke0 = int((np.isfinite(t) & (t < 0)).sum())
            if not sel_.any():
                break
            bad = sel_
            dv = np.zeros_like(V)
            dv[vid[bad]] = sv[vid[bad]][:, None] * N[bad]
            if len(fol):
                dv[fol[:, 0]] = dv[fol[:, 1]]
            V = V + dv
            moved[vid[bad]] = True
            if len(fol):
                moved[fol[:, 0]] |= moved[fol[:, 1]]
        p["verts"] = V
        vid, _, _, t = under_depth(p, covers, reach)
        if masks and un in masks and len(masks[un][0]):
            t = np.where(masks[un][1][cKDTree(masks[un][0]).query(V[vid])[1]], t, np.nan)
        if lods.LOD_UNDER_LOD0_NORMAL and masks and un in masks and len(masks[un]) > 3 and len(masks[un][0]):
            # (r59) a decimated mesh crumpled under its cover (rc2i's LOD2 sock top under the jeans hem: vertex normals every
            # way within 1 cm) is pushed along the wrong lines: what still pokes, or has no cover along its own normal,
            # moves along its nearest LOD0 vertex's normal instead
            nn_ = cKDTree(masks[un][0]).query(V[vid])[1]
            N0 = np.asarray(masks[un][3], np.float64)[nn_]
            ok0 = masks[un][1][nn_]
            sel0 = ok0 & ~(np.isfinite(t) & (t >= gap))
            if sel0.any():
                t0 = cover_depth(V[vid[sel0]], N0[sel0], covers, reach)
                b0 = np.isfinite(t0) & (t0 < gap)
                if b0.any():
                    ii = vid[sel0][b0]
                    V[ii] += (t0[b0] - gap)[:, None] * N0[sel0][b0]
                    moved[ii] = True
                    p["verts"] = V
                    vid, _, _, t = under_depth(p, covers, reach)
                    t = np.where(masks[un][1][cKDTree(masks[un][0]).query(V[vid])[1]], t, np.nan)
        if lods.LOD_UNDER_WORN_MAX and masks and un in masks:  # (r61) a worn part (the skin) moves at most this far: rc2l's
            # LOD3 neck was pushed up to 49 mm under the sweater's collar, its big triangles dragging the visible neck
            # above the collar into dark wedges (74 of 465 front-neck vertices moved)
            dv_ = V - np.asarray(parts[un]["verts"], np.float64)
            ln_ = np.linalg.norm(dv_, axis=1)
            far_ = ln_ > lods.LOD_UNDER_WORN_MAX
            V[far_] = np.asarray(parts[un]["verts"], np.float64)[far_] + dv_[far_] * (lods.LOD_UNDER_WORN_MAX / ln_[far_])[:, None]
        capped = 0
        if lods.LOD_UNDER_MAX_MOVE:  # (Garrett s8) a push-under is a few mm: a vertex sent further is a wrong normal or a
            # wrong cover (v6b: the shirt 39 mm out through the jacket sleeve), so no vertex moves more than the cap
            # (Tess r61 capped the skin at 10 mm the same way); what it leaves poking is reported
            V0 = np.asarray(parts[un]["verts"], np.float64)
            dv_ = V - V0
            dn_ = np.linalg.norm(dv_, axis=1)
            over_ = dn_ > lods.LOD_UNDER_MAX_MOVE
            capped = int(over_.sum())
            if capped:
                V = V0 + dv_ * np.minimum(1.0, lods.LOD_UNDER_MAX_MOVE / np.maximum(dn_, 1e-12))[:, None]
                p["verts"] = V
                vid, _, _, t = under_depth(p, covers, reach)
                if masks and un in masks and len(masks[un][0]):
                    t = np.where(masks[un][1][cKDTree(masks[un][0]).query(V[vid])[1]], t, np.nan)
        p["verts"] = V.astype(np.float32)
        parts[un] = p
        rep[un] = {"poking0": int(poke0 or 0), "poking": int((np.isfinite(t) & (t < 0)).sum()), "moved": int(moved.sum()),
                   "faces_poking0": pokef, "capped": capped, "flaps": nflap}
    return rep
