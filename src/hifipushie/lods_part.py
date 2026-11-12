"""One part's LODs and all parts': the LOD shell, lod_part, card and ribbon LODs, lod_parts, thin_strands. Part of the LODs (lods.py has the overview)."""
from __future__ import annotations

import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from scipy.spatial import cKDTree

from . import lods
from .lods_pieces import (
    _decimate, _hull_pieces, _lift_made, _patch_offsets, _patches, _seat_patches, _small_pieces, _split,
    _welded_pieces,
)

def _lod_shell(p: dict, weights: tuple | None, ratio: float, shapes: bool = True) -> tuple[dict, tuple | None, dict]:
    """lod_part for a two-sided garment (cloth.export_part: p["shell"] = {"outer": n, "thickness": th}, triangles
    [0, n) the outer face, [n, 2n) the inner one a cloth's thickness in, the rest (made pieces, buttons) after).
    Decimating the two shells apart put the inner through the outer wherever their errors differed (0.8 mm apart,
    decimation error several mm): single-sided materials then showed the inner face, its normal pointing in, as
    BLACK TRIANGLES all over Garrett's jacket (17572 -> 4780). So the outer shell and the rest are decimated, and the
    inner shell is rebuilt from the decimated outer: offset along its normal, wound the other way, normal and
    bitangent sign negated, uv / tangent / weights / shapes copied."""
    n, th = int(p["shell"]["outer"]), float(p["shell"]["thickness"])
    m = int(p["shell"].get("made", 0)) if lods.LOD_MADE_SHEETS else 0  # (cloth.EXPORT_MADE_SHEETS: made fronts, backs, rims)
    m_rim = int(p["shell"].get("made_rim", 0)) if m else 0
    th_m = float(p["shell"].get("made_thickness", th))
    nt = len(p["corner_vert"]) // 3
    tri_keep = np.ones(nt, bool)
    tri_keep[n:2 * n] = False
    tri_keep[2 * n + m:2 * n + 2 * m + m_rim] = False  # (the made backs and rims: rebuilt from the decimated fronts)
    cm = np.repeat(tri_keep, 3)
    po = {k: v for k, v in p.items() if k != "shell"}
    po.update({k: np.asarray(p[k])[cm] for k in ("corner_vert", "uv", "normal", "tangent", "sign")})
    outer = np.zeros(int(tri_keep.sum()), bool)
    outer[:n] = True
    made = np.zeros_like(outer)
    made[n:n + m] = True
    small = (_small_pieces(po["corner_vert"], ~outer & ~made, lods.LOD_KEEP_PIECE) if lods.LOD_KEEP_PIECE
             else np.zeros_like(outer))
    small_o = (_patches(po, outer, _small_pieces(po["corner_vert"], outer, lods.LOD_KEEP_PIECE))
               if lods.LOD_KEEP_PIECE and lods.LOD_KEEP_OUTER_PIECES else np.zeros_like(outer))
    hull_x = 1.0
    if lods.LOD_KEEP_PIECE_HULL and small.any() and ratio < lods.LOD_KEEP_PIECE_RATIO:
        ns_ = int(small.sum())
        po, outer, small, small_o, made = _hull_pieces(po, outer, small, small_o, made)
        hull_x = ns_ / max(int(small.sum()), 1)  # (the pieces keep their triangle count: the hull is fewer to start)
    po["meshes"] = {"outer": outer & ~small_o, "rest": ~outer & ~small & ~made, "pieces": small,
                    "outer_pieces": small_o, "made": made}
    mr = None
    keep = 1.0 if ratio >= lods.LOD_KEEP_PIECE_RATIO else max(ratio, lods.LOD_KEEP_PIECE_FAR)
    floor_ = max(ratio, min(lods.LOD_MADE_FLOOR, lods.LOD_MADE_FLOOR_X * ratio)) if lods.LOD_MADE_FLOOR else ratio
    if lods.LOD_MADE_FLOOR:
        mr = {"outer": ratio, "rest": floor_, "pieces": min(1.0, keep * hull_x), "outer_pieces": keep, "made": floor_}
    elif small_o.any():
        mr = {"outer_pieces": keep}
    seat0 = None
    if lods.LOD_SEAT_PATCHES and small_o.any() and ratio < 1.0:  # (r58) the pieces' LOD0 offsets off the panel
        V0 = np.asarray(po["verts"], np.float64)
        vs0, _, _, off0, d0 = _patch_offsets(V0, np.asarray(po["corner_vert"], np.int64).reshape(-1, 3), outer & ~small_o,
                                             small_o, np.asarray(po["normal"], np.float64))
        seat0 = (V0[vs0], np.where(d0 < lods.LOD_SEAT_REACH, off0, 0.0))
    q, wq, r = lod_part(po, weights, ratio, shapes=shapes, mesh_ratios=mr)
    qm = q.pop("meshes")
    mo = np.asarray(qm["outer"], bool) | np.asarray(qm["outer_pieces"], bool)
    mm = np.asarray(qm["made"], bool) & ~mo
    T = np.asarray(q["corner_vert"], np.int64).reshape(-1, 3)
    V = np.asarray(q["verts"], np.float64)
    if seat0 is not None:
        V = V.copy()
        r = dict(r, patches_seated=_seat_patches(V, T, np.asarray(qm["outer"], bool), np.asarray(qm["outer_pieces"], bool),
                                                 np.asarray(q["normal"], np.float64), *seat0))
        q = dict(q, verts=V.astype(np.float32))
    ms = mo | mm  # (the outer shell and the made fronts: each gets its back rebuilt from it)
    vu, inv = np.unique(T[ms], return_inverse=True)
    vn = np.zeros((len(vu), 3))
    np.add.at(vn, inv.ravel(), np.asarray(q["normal"], np.float64)[np.repeat(ms, 3)])
    vn /= np.maximum(np.linalg.norm(vn, axis=1, keepdims=True), 1e-12)
    vth = np.full(len(vu), th)
    if mm.any():
        vth[np.isin(vu, T[mm])] = th_m
    nv0 = len(V)
    Tin = np.full_like(T, -1)
    Tin[ms] = (inv.reshape(-1, 3) + nv0)[:, [0, 2, 1]]
    C = np.arange(len(T) * 3).reshape(-1, 3)
    rest = ~ms
    out = dict(q)
    out["verts"] = np.r_[V, V[vu] - vn * vth[:, None]].astype(np.float32)
    out["corner_vert"] = np.r_[T[mo].ravel(), Tin[mo].ravel(), T[mm].ravel(), Tin[mm].ravel(),
                               T[rest].ravel()].astype(np.int64)
    for k, sg in (("uv", 1), ("normal", -1), ("tangent", 1), ("sign", -1)):
        a = np.asarray(q[k])
        out[k] = np.concatenate([a[C[mo].ravel()], sg * a[C[mo][:, [0, 2, 1]].ravel()], a[C[mm].ravel()],
                                 sg * a[C[mm][:, [0, 2, 1]].ravel()], a[C[rest].ravel()]]).astype(np.float32)
    if q.get("vcolor") is not None:
        out["vcolor"] = np.r_[q["vcolor"], np.asarray(q["vcolor"])[vu]].astype(np.float32)
    if q.get("shapes"):
        out["shapes"] = {nm: (np.r_[d, np.asarray(d)[vu]], np.r_[a0, -np.asarray(a0)[vu]], np.r_[a1, -np.asarray(a1)[vu]])
                         for nm, (d, a0, a1) in q["shapes"].items()}
    if wq is not None:
        wq = (np.r_[wq[0], np.asarray(wq[0])[vu]], np.r_[wq[1], np.asarray(wq[1])[vu]].astype(np.float32))
    out["shell"] = {"outer": int(mo.sum()), "thickness": th}
    if mm.any():  # (the next LOD decimates the made sheets the same way)
        out["shell"].update(made=int(mm.sum()), made_rim=0, made_thickness=th_m)
    if lods.LOD_MADE_GAP and (~mo).any() and mo.any():
        r = dict(r, made_lifted=_lift_made(out, int(mo.sum())))
    r = dict(r, triangles0=nt, triangles=len(out["corner_vert"]) // 3, shell=True, made_sheets=int(mm.sum()))
    return out, wq, r


def lod_part(p: dict, weights: tuple | None, ratio: float, mesh_ratios: dict | None = None,
             shapes: bool = True) -> tuple[dict, tuple | None, dict]:
    """(part dict as write_glb takes it, its (joints, weights) or None, report) at `ratio` of p's triangles."""
    if p.get("shell") and not p.get("meshes"):
        return _lod_shell(p, weights, ratio, shapes=shapes)
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
    pieces, target = [], 0
    for L in np.unique(lab):
        tf = np.flatnonzero(lab == L)
        Tl = T[tf]
        vs, Tl_loc = np.unique(Tl, return_inverse=True)
        Tl_loc = Tl_loc.reshape(-1, 3)
        Vl = P0[vs]
        r_ = ratio
        if mesh_ratios and meshes and tri_mesh is not None:  # (a native head and its body: their own shares)
            r_ = float(mesh_ratios.get(mnames[int(tri_mesh[tf[0]])], ratio))
        target += len(tf) if r_ >= 0.999 else int(round(len(tf) * r_))
        if len(tf) < lods.MIN_PATCH or r_ >= 0.999:
            Vd, Fd = Vl, Tl_loc
            kept += len(tf)
        else:
            Vd, Fd = _decimate(Vl, Tl_loc, int(round(len(tf) * r_)))
            decim += len(tf)
            if len(Fd) == 0:
                Vd, Fd = Vl, Tl_loc
        pieces.append((L, tf, vs, Tl_loc, Vl, Vd, Fd))
    welded = False
    got = sum(len(pc[6]) for pc in pieces)
    if lods.LOD_WELD and ratio < 0.999 and got > lods.LOD_WELD_OVER * max(target, 1) and got > lods.MIN_PATCH:
        pieces, welded = _welded_pieces(p, pieces, src, tri_mesh, mnames, ratio, mesh_ratios, len(T)), True
        kept, decim = 0, len(T)
    for L, tf, vs, Tl_loc, Vl, Vd, Fd in pieces:
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
    rewound = 0
    if lods.LOD_REWIND and len(F) and ratio < 0.999:  # (r55) a collapse that folds a triangle over leaves it wound against
        # the normals its corners carry: rendered back-facing, it shades dark (the grey radial fans on rc2d's LOD2 coat
        # pockets: 64 of 135 triangles there, a single cloth layer; LOD0 / LOD1 clean). Wound the other way, it faces out.
        Vf = V[F]
        gn = np.cross(Vf[:, 1] - Vf[:, 0], Vf[:, 2] - Vf[:, 0])
        bad = (gn * nrm[F].sum(1)).sum(1) < 0
        if bad.any():
            F = F.copy()
            F[bad] = F[bad][:, [0, 2, 1]]
            rewound = int(bad.sum())
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
    keep_sh = {nm: v for nm, v in (p.get("shapes") or {}).items() if shapes or nm.startswith(lods.POSE_SHAPE)}
    if keep_sh:
        sh = {}
        for nm, (d, n0, n1) in keep_sh.items():
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
    rep = {"triangles0": len(c) // 3, "triangles": len(F), "kept_small": kept, "decimated_from": decim, "welded": welded, "rewound": rewound,
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
        room = max(ratio * n - (keep.sum() - c), lods.CARDS_MIN * c)  # (the cap alone loses the tail's silhouette)
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


def ribbon_fit(p: dict, max_triangles: int) -> tuple[dict, dict]:
    """Ribbon cards (the lashes) under a triangle cap: ribbon_lod at the largest share of whole ribbons that fits (their
    coverage held by the same widening). Unchanged when they already fit. Info: triangles0, triangles, ribbons,
    ribbons_kept, widen."""
    n = len(p["corner_vert"]) // 3
    if n <= max_triangles:
        return p, {"triangles0": n, "triangles": n, "ribbons": None, "ribbons_kept": None, "widen": 1.0}
    ratio = max_triangles / max(n, 1)
    while True:
        q, info = ribbon_lod(p, ratio)
        m = len(q["corner_vert"]) // 3
        if m <= max_triangles or ratio < 1e-3:
            break
        ratio *= 0.99
    return q, {"triangles0": n, "triangles": m, "ribbons": info.get("ribbons0", info.get("ribbons")),
               "ribbons_kept": info.get("ribbons"), "widen": float(info.get("widened", 1.0))}


def ribbon_lod(p: dict, ratio: float) -> tuple[dict, dict]:
    """Ribbon cards at a LOD (the eyelashes: lashes.build, each lash one strip of consecutive across-pairs of
    vertices): a share `ratio` of whole ribbons kept, evenly through their order (they run along the lid, so the
    kept ones still span it), each widened about its own middle line by 1 / ratio (at most RIBBON_WIDEN) so their
    coverage at the LOD's distance, the dark frame round the eye, stays. Vertices are kept (face shapes, weights
    index them); only triangles go. Ribbons are cards (every vertex a border): decimating them tears them."""
    c = np.asarray(p["corner_vert"], np.int64)
    T = c.reshape(-1, 3)
    n, nv = len(T), len(p["verts"])
    e = np.r_[T[:, [0, 1]], T[:, [1, 2]]]
    _, lab = connected_components(coo_matrix((np.ones(len(e)), (e[:, 0], e[:, 1])), shape=(nv, nv)), directed=False)
    rib = lab[T[:, 0]]
    ids = np.unique(rib)
    k = max(1, int(round(ratio * len(ids))))
    if k >= len(ids):
        return p, {"triangles0": n, "triangles": n, "ribbons": int(len(ids))}
    kept = ids[np.unique(np.round(np.linspace(0, len(ids) - 1, k)).astype(np.int64))]
    keep = np.isin(rib, kept)
    w = min(1.0 / max(ratio, 1e-6), lods.RIBBON_WIDEN)
    V = np.array(p["verts"], np.float64)
    used = np.unique(T[keep])
    pair = used[(used % 2 == 0) & np.isin(used + 1, used)]  # (across-pairs: vertex 2i and 2i + 1 of a ribbon)
    if len(pair) and w > 1.0:
        mid = 0.5 * (V[pair] + V[pair + 1])
        V[pair] = mid + w * (V[pair] - mid)
        V[pair + 1] = mid + w * (V[pair + 1] - mid)
    cm = np.repeat(keep, 3)
    q = {**p, "verts": V.astype(np.asarray(p["verts"]).dtype), "corner_vert": c[cm]}
    for k_ in ("uv", "normal", "tangent", "sign"):
        if k_ in p:
            q[k_] = np.asarray(p[k_])[cm]
    return q, {"triangles0": n, "triangles": int(keep.sum()), "ribbons": int(len(kept)), "ribbons0": int(len(ids)),
               "widened": round(w, 2)}


def lod_parts(parts: dict, rigged: dict | None, ratio, skip=(), cards: dict | None = None, mesh_ratios: dict | None = None,
              shapes: bool = True, ribbons=()) -> tuple[dict, dict | None, dict]:
    """Every part at `ratio` (parts named in `skip` are carried as they are; `cards` {part: layer ranges}: hair cards
    by whole layers, card_lod; `ribbons`: ribbon cards (the lashes) by whole ribbons, ribbon_lod)."""
    out, rep = {}, {}
    wts = dict((rigged or {}).get("weights") or {})
    neww = {}
    for pn, p in parts.items():
        w = wts.get(pn)
        if cards and pn in cards:
            out[pn], rep[pn] = card_lod(p, cards[pn], ratio(pn) if callable(ratio) else ratio)
            if w is not None:
                neww[pn] = w
            continue
        if pn in ribbons:
            q, rep[pn] = ribbon_lod(p, ratio(pn) if callable(ratio) else ratio)
            out[pn] = q if shapes or not q.get("shapes") else {k: v for k, v in q.items() if k != "shapes"}
            if w is not None:
                neww[pn] = w
            continue
        r_pn = ratio(pn) if callable(ratio) else ratio
        small_far = (len(p["corner_vert"]) // 3 < lods.MIN_PART and r_pn < lods.LOD_SMALL_FAR_RATIO and pn not in lods.LOD_SMALL_KEEP
                     and pn not in skip and lods.LOD_SMALL_FAR)
        if small_far:  # (r55) the far LOD: small parts halve too
            q, wq, r = lod_part(p, w, max(r_pn, lods.LOD_SMALL_FAR), mesh_ratios=mesh_ratios, shapes=shapes)
            out[pn], rep[pn] = q, dict(r, small_far=True)
            if wq is not None:
                neww[pn] = wq
            continue
        if pn in skip or len(p["corner_vert"]) // 3 < lods.MIN_PART:
            out[pn] = p if shapes or not p.get("shapes") else {
                **{k: v for k, v in p.items() if k != "shapes"},
                **({"shapes": {nm: v for nm, v in p["shapes"].items() if nm.startswith(lods.POSE_SHAPE)}}
                   if any(nm.startswith(lods.POSE_SHAPE) for nm in p["shapes"]) else {})}
            if w is not None:
                neww[pn] = w
            rep[pn] = {"triangles0": len(p["corner_vert"]) // 3, "triangles": len(p["corner_vert"]) // 3, "kept": True}
            continue
        q, wq, r = lod_part(p, w, ratio(pn) if callable(ratio) else ratio, mesh_ratios=mesh_ratios, shapes=shapes)
        out[pn] = q
        if wq is not None:
            neww[pn] = wq
        rep[pn] = r
    rig = dict(rigged, weights=neww) if rigged else None
    return out, rig, rep


def thin_strands(p: dict, share: float) -> tuple[dict, dict]:
    """A part made of separate strands (the lashes): whole strands kept, the largest first, to `share` of its
    triangles (vertices kept: weights and morph targets stay valid)."""
    T = np.asarray(p["corner_vert"], np.int64).reshape(-1, 3)
    n = len(T)
    if n == 0 or share >= 1:
        return p, {"triangles0": n, "triangles": n}
    nv = len(p["verts"])
    e = np.r_[T[:, [0, 1]], T[:, [1, 2]]]
    _, lab = connected_components(coo_matrix((np.ones(len(e)), (e[:, 0], e[:, 1])), shape=(nv, nv)), directed=False)
    strand = lab[T[:, 0]]
    V = np.asarray(p["verts"], np.float64)
    area = 0.5 * np.linalg.norm(np.cross(V[T[:, 1]] - V[T[:, 0]], V[T[:, 2]] - V[T[:, 0]]), axis=1)
    sa, sc = np.bincount(strand, area), np.bincount(strand)
    order = np.argsort(-sa)
    # spread the kept strands along each eye (every k-th by size rank is near enough: sizes vary along the lid)
    chosen = np.zeros(len(sa), bool)
    tot = 0
    for k in order:
        if sc[k] and tot + sc[k] <= share * n:
            chosen[k] = True
            tot += sc[k]
    keep = chosen[strand]
    cm = np.repeat(keep, 3)
    q = {**p, "corner_vert": p["corner_vert"][cm], "uv": p["uv"][cm], "normal": p["normal"][cm],
         "tangent": p["tangent"][cm], "sign": p["sign"][cm]}
    return q, {"triangles0": n, "triangles": int(keep.sum())}
