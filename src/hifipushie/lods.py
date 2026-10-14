"""Levels of detail for an exported character (asset.export(lods=[...])): every part's LOD0 low poly decimated to a
share of its triangles, ON THE SAME ATLAS (the LODs' GLBs reference LOD0's maps beside them), keeping what an engine
needs to swap them without a pop at the seams: skin weights, morph targets (face shapes), the native head / body split.

How: the part is cut into its glTF vertices' patches (one patch = triangles joined through vertices that share
position, uv, normal and tangent: a uv island inside one smoothing group, and the head / body meshes apart). Each patch
is decimated alone by quadric collapse (pyfqmr) with its BORDER held, so a uv seam, a hard edge and the head / body seam
ring keep their vertices exactly on both sides: no crack, no uv bleed across a chart. Every new vertex reads its
attributes at its closest point of its OWN patch of LOD0 (barycentric): uv, normal, tangent, the 4 bone weights (the
union of the corners' re-cut to 4), each face shape's move and normal turn, vertex colour. Border vertices sit on LOD0
vertices, so they read them exactly. Hair cards and the eyelash ribbons are cards (every vertex a border): they are not
decimated here (hair LODs are its card tiers)."""
from __future__ import annotations

import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from scipy.spatial import cKDTree

LOD_RATIOS = (0.5, 0.25, 0.12)  # share of LOD0's triangles per level (Joe's call: budgets per tier)
MIN_PATCH = 12  # triangles: smaller patches are kept as they are
HAIR_TIERS = ("main", "npc", "far")  # the hair's card tier at LOD1, 2, 3+ (hair.CARD_TIERS: one atlas for all)
MIN_PART = 1000  # triangles: smaller parts (eyes, teeth, props) are kept whole (the LOD3 eyes lost their cornea)
CARDS_MIN = 0.2  # a hair LOD keeps at least this share of its card layer's triangles (the biggest cards)


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


def _decimate(V: np.ndarray, F: np.ndarray, target: int) -> tuple[np.ndarray, np.ndarray]:
    import pyfqmr
    q = pyfqmr.Simplify()
    q.setMesh(np.ascontiguousarray(V, np.float64), np.ascontiguousarray(F, np.int32))
    q.simplify_mesh(target_count=max(int(target), 4), aggressiveness=7, preserve_border=True, verbose=False)
    v, f, _ = q.getMesh()
    return np.asarray(v, np.float64), np.asarray(f, np.int64)


def lod_part(p: dict, weights: tuple | None, ratio: float) -> tuple[dict, tuple | None, dict]:
    """(part dict as write_glb takes it, its (joints, weights) or None, report) at `ratio` of p's triangles."""
    from .rig_template import _closest_on_triangles
    meshes = p.get("meshes")
    mnames = list(meshes) if meshes else []
    tri_mesh = None
    if meshes:
        tri_mesh = np.zeros(len(p["corner_vert"]) // 3, np.int64)
        for k, mn in enumerate(mnames):
            tri_mesh[np.asarray(meshes[mn], bool)] = k
    first, T, lab = _split(p, tri_mesh)
    c = np.asarray(p["corner_vert"], np.int64)
    src = c[first]  # split vertex -> part vertex
    P0 = np.asarray(p["verts"], np.float64)[src]
    attrs = {"uv": np.asarray(p["uv"], np.float64)[first], "normal": np.asarray(p["normal"], np.float64)[first],
             "tangent": np.asarray(p["tangent"], np.float64)[first], "sign": np.asarray(p["sign"], np.float64)[first]}
    outV, outT, outLab, bary_src, out_mesh = [], [], [], [], []
    nv = 0
    kept = decim = 0
    for L in np.unique(lab):
        tf = np.flatnonzero(lab == L)
        Tl = T[tf]
        vs, Tl_loc = np.unique(Tl, return_inverse=True)
        Tl_loc = Tl_loc.reshape(-1, 3)
        Vl = P0[vs]
        if len(tf) < MIN_PATCH or ratio >= 0.999:
            Vd, Fd = Vl, Tl_loc
            kept += len(tf)
        else:
            Vd, Fd = _decimate(Vl, Tl_loc, int(round(len(tf) * ratio)))
            decim += len(tf)
            if len(Fd) == 0:
                Vd, Fd = Vl, Tl_loc
        # each new vertex: its closest point of this patch's LOD0 triangles
        A, B, C = Vl[Tl_loc[:, 0]], Vl[Tl_loc[:, 1]], Vl[Tl_loc[:, 2]]
        k = min(12, len(Tl_loc))
        _, cand = cKDTree((A + B + C) / 3).query(Vd, k=k)
        cand = cand.reshape(len(Vd), k)
        best = np.full(len(Vd), np.inf)
        bb = np.zeros((len(Vd), 3))
        bt = np.zeros(len(Vd), np.int64)
        for j in range(k):
            t = cand[:, j]
            b, d = _closest_on_triangles(Vd, A[t], B[t], C[t])
            m = d < best
            best[m], bb[m], bt[m] = d[m], b[m], t[m]
        corners = vs[Tl_loc[bt]]  # split vertex ids (n, 3)
        outV.append(Vd)
        outT.append(Fd + nv)
        bary_src.append((corners, bb))
        if tri_mesh is not None:
            out_mesh.append(np.full(len(Fd), int(tri_mesh[tf[0]])))
        nv += len(Vd)
    V = np.concatenate(outV)
    F = np.concatenate(outT)
    corners = np.concatenate([b[0] for b in bary_src])
    bb = np.concatenate([b[1] for b in bary_src])

    def interp(a):
        return np.einsum("nk,nk...->n...", bb, a[corners])
    uv = interp(attrs["uv"])
    nrm = interp(attrs["normal"])
    nrm /= np.maximum(np.linalg.norm(nrm, axis=1, keepdims=True), 1e-12)
    tan = interp(attrs["tangent"])
    tan -= (tan * nrm).sum(1, keepdims=True) * nrm
    tan /= np.maximum(np.linalg.norm(tan, axis=1, keepdims=True), 1e-12)
    sign = np.sign(attrs["sign"][corners[np.arange(len(V)), bb.argmax(1)]])
    sign[sign == 0] = 1.0
    cv = F.ravel()
    out = {"verts": V.astype(np.float32), "corner_vert": cv.astype(np.int64), "uv": uv[cv].astype(np.float32),
           "normal": nrm[cv].astype(np.float32), "tangent": tan[cv].astype(np.float32), "sign": sign[cv].astype(np.float32),
           "atlas": p.get("atlas", 0)}
    vsrc = src[corners]  # part vertices (n, 3) of each new vertex's triangle
    if p.get("vcolor") is not None:
        out["vcolor"] = np.einsum("nk,nkc->nc", bb, np.asarray(p["vcolor"], np.float64)[vsrc]).astype(np.float32)
    if p.get("shapes"):
        sh = {}
        for nm, (d, n0, n1) in p["shapes"].items():
            d_ = np.einsum("nk,nkc->nc", bb, np.asarray(d, np.float64)[vsrc])
            a0 = np.einsum("nk,nkc->nc", bb, np.asarray(n0, np.float64)[vsrc])
            a1 = np.einsum("nk,nkc->nc", bb, np.asarray(n1, np.float64)[vsrc])
            a0 /= np.maximum(np.linalg.norm(a0, axis=1, keepdims=True), 1e-12)
            a1 /= np.maximum(np.linalg.norm(a1, axis=1, keepdims=True), 1e-12)
            sh[nm] = (d_, a0, a1)
        out["shapes"] = sh
    if meshes:
        tm = np.concatenate(out_mesh)
        out["meshes"] = {mn: tm == k for k, mn in enumerate(mnames)}
        if p.get("shape_meshes") is not None:
            out["shape_meshes"] = p["shape_meshes"]
    w_out = None
    if weights is not None:
        J0, W0 = np.asarray(weights[0]), np.asarray(weights[1], np.float64)
        Jc, Wc = J0[vsrc], W0[vsrc] * bb[:, :, None]  # (n, 3, 4)
        Jf, Wf = Jc.reshape(len(V), -1), Wc.reshape(len(V), -1)
        # sum the same joint's shares, keep the 4 largest
        Jn = np.zeros((len(V), 4), J0.dtype)
        Wn = np.zeros((len(V), 4))
        acc: dict = {}
        order = np.argsort(-Wf, axis=1)
        for i in range(len(V)):
            acc.clear()
            for j in order[i]:
                w = Wf[i, j]
                if w <= 0:
                    break
                acc[Jf[i, j]] = acc.get(Jf[i, j], 0.0) + w
            top = sorted(acc.items(), key=lambda kv: -kv[1])[:4]
            for s, (jj, ww) in enumerate(top):
                Jn[i, s], Wn[i, s] = jj, ww
        Wn /= np.maximum(Wn.sum(1, keepdims=True), 1e-12)
        w_out = (Jn, Wn.astype(np.float32))
    rep = {"triangles0": len(c) // 3, "triangles": len(F), "kept_small": kept, "decimated_from": decim,
           "patches": int(len(np.unique(lab)))}
    return out, w_out, rep


def card_lod(p: dict, ranges: dict, ratio: float) -> tuple[dict, dict]:
    """Hair cards at a LOD: the export orders card triangles by layer (hair.export_cards: the cap, then layer0 (the
    base layer), layer1..., the tie), so a LOD keeps the cap, the tie and whole layers from the bottom up while they fit
    `ratio` of the triangles (at least the base layer)."""
    n = len(p["corner_vert"]) // 3
    keep = np.zeros(n, bool)
    for nm in ("cap", "tie"):
        if nm in ranges:
            s, c = ranges[nm]
            keep[s:s + c] = True
    layers = sorted((k for k in ranges if k.startswith("layer")), key=lambda k: int(k[5:]))
    for i, nm in enumerate(layers):
        s, c = ranges[nm]
        if i > 0 and keep.sum() + c > ratio * n:
            break
        keep[s:s + c] = True
    if keep.sum() > 1.05 * ratio * n and layers:
        # still over (a one-layer groom: tied hair): thin the top kept layer by whole cards, the biggest kept
        top = [nm for nm in layers if keep[ranges[nm][0]]][-1]
        s, c = ranges[top]
        T = np.asarray(p["corner_vert"], np.int64).reshape(-1, 3)[s:s + c]
        vs, Tl = np.unique(T, return_inverse=True)
        Tl = Tl.reshape(-1, 3)
        e = np.r_[Tl[:, [0, 1]], Tl[:, [1, 2]]]
        _, lab = connected_components(coo_matrix((np.ones(len(e)), (e[:, 0], e[:, 1])), shape=(len(vs), len(vs))),
                                      directed=False)
        card = lab[Tl[:, 0]]
        V = np.asarray(p["verts"], np.float64)
        area = 0.5 * np.linalg.norm(np.cross(V[T[:, 1]] - V[T[:, 0]], V[T[:, 2]] - V[T[:, 0]]), axis=1)
        csum = np.bincount(card, area)
        ccount = np.bincount(card)
        room = max(ratio * n - (keep.sum() - c), CARDS_MIN * c)  # (the cap alone loses the tail's silhouette)
        chosen = np.zeros(len(csum), bool)
        tot = 0
        for k in np.argsort(-csum):
            if tot + ccount[k] > room:
                continue
            chosen[k] = True
            tot += ccount[k]
        keep[s:s + c] = chosen[card]
    cm = np.repeat(keep, 3)
    q = {**p, "corner_vert": p["corner_vert"][cm], "uv": p["uv"][cm], "normal": p["normal"][cm],
         "tangent": p["tangent"][cm], "sign": p["sign"][cm]}
    return q, {"triangles0": n, "triangles": int(keep.sum()), "layers": [k for k in layers if keep[ranges[k][0]]]}


def lod_parts(parts: dict, rigged: dict | None, ratio: float, skip=(), cards: dict | None = None
              ) -> tuple[dict, dict | None, dict]:
    """Every part at `ratio` (parts named in `skip` are carried as they are; `cards` {part: layer ranges}: hair cards
    by whole layers, card_lod)."""
    out, rep = {}, {}
    wts = dict((rigged or {}).get("weights") or {})
    neww = {}
    for pn, p in parts.items():
        w = wts.get(pn)
        if cards and pn in cards:
            out[pn], rep[pn] = card_lod(p, cards[pn], ratio)
            if w is not None:
                neww[pn] = w
            continue
        if pn in skip or len(p["corner_vert"]) // 3 < MIN_PART:
            out[pn] = p
            if w is not None:
                neww[pn] = w
            rep[pn] = {"triangles0": len(p["corner_vert"]) // 3, "triangles": len(p["corner_vert"]) // 3, "kept": True}
            continue
        q, wq, r = lod_part(p, w, ratio)
        out[pn] = q
        if wq is not None:
            neww[pn] = wq
        rep[pn] = r
    rig = dict(rigged, weights=neww) if rigged else None
    return out, rig, rep
