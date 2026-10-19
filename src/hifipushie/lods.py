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

import os
from pathlib import Path

import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from scipy.spatial import cKDTree

LOD_RATIOS = (0.5, 0.25, 0.12)  # share of LOD0's triangles per level (Joe's call: budgets per tier)
MIN_PATCH = 12  # triangles: smaller patches are kept as they are
HAIR_TIERS = ("main", "npc", "far")  # the hair's card tier at LOD1, 2, 3+ (hair.CARD_TIERS: one atlas for all)
MIN_PART = 1000  # triangles: smaller parts (eyes, teeth, props) are kept whole (the LOD3 eyes lost their cornea)
LOD_SMALL_FAR_RATIO = 0.15  # (r55) ... except at LODs whose ratio for the part is below this (LOD3), where they keep
LOD_SMALL_FAR = 0.5  # this share: ~4.9k triangles of small parts (shoes, tongue, laces, lanyard, clip, socks) were LOD3's
# floor, 40% of its 12,360; at LOD3's distance (several metres) a shoe or a clip at half its triangles reads the same
LOD_SMALL_KEEP = ("eyes",)  # ... but never these (the cornea)
CARDS_MIN = 0.2  # a hair LOD keeps at least this share of its card layer's triangles (the biggest cards)


POSE_SHAPE = "corr_"  # pose correctives (correctives.py) stay in every LOD: a LOD without face shapes still bends

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


LOD_SEAT_PATCHES = True  # (r58) outer pieces kept whole (patch pockets) are re-seated on the DECIMATED panel at their LOD0
# offset: kept whole over a coarser panel that no longer matched them, rc2h's LOD2 left hip pocket stood off as a twisted
# flap and the left chest pocket crumpled (the panel came through it). Each piece vertex goes to its closest point on the
# decimated rest of the outer shell + its LOD0 signed offset along that face's normal (within LOD_SEAT_REACH).
LOD_SEAT_REACH = 0.02  # m


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
    reach = LOD_SEAT_REACH if reach is None else reach
    if not piece.any() or not panel.any() or not len(P0):
        return 0
    vs, cp, nf, _, d = _patch_offsets(V, T, panel, piece, Nc)
    o = off0[cKDTree(P0).query(V[vs])[1]]
    ok = d < reach
    V[vs[ok]] = cp[ok] + nf[ok] * o[ok, None]
    return int(ok.sum())


def _lod_shell(p: dict, weights: tuple | None, ratio: float, shapes: bool = True) -> tuple[dict, tuple | None, dict]:
    """lod_part for a two-sided garment (cloth.export_part: p["shell"] = {"outer": n, "thickness": th}, triangles
    [0, n) the outer face, [n, 2n) the inner one a cloth's thickness in, the rest (made pieces, buttons) after).
    Decimating the two shells apart put the inner through the outer wherever their errors differed (0.8 mm apart,
    decimation error several mm): single-sided materials then showed the inner face, its normal pointing in, as
    BLACK TRIANGLES all over Garrett's jacket (17572 -> 4780). So the outer shell and the rest are decimated, and the
    inner shell is rebuilt from the decimated outer: offset along its normal, wound the other way, normal and
    bitangent sign negated, uv / tangent / weights / shapes copied."""
    n, th = int(p["shell"]["outer"]), float(p["shell"]["thickness"])
    nt = len(p["corner_vert"]) // 3
    tri_keep = np.ones(nt, bool)
    tri_keep[n:2 * n] = False
    cm = np.repeat(tri_keep, 3)
    po = {k: v for k, v in p.items() if k != "shell"}
    po.update({k: np.asarray(p[k])[cm] for k in ("corner_vert", "uv", "normal", "tangent", "sign")})
    outer = np.zeros(int(tri_keep.sum()), bool)
    outer[:n] = True
    small = _small_pieces(po["corner_vert"], ~outer, LOD_KEEP_PIECE) if LOD_KEEP_PIECE else np.zeros_like(outer)
    small_o = (_patches(po, outer, _small_pieces(po["corner_vert"], outer, LOD_KEEP_PIECE))
               if LOD_KEEP_PIECE and LOD_KEEP_OUTER_PIECES else np.zeros_like(outer))
    hull_x = 1.0
    if LOD_KEEP_PIECE_HULL and small.any() and ratio < LOD_KEEP_PIECE_RATIO:
        ns_ = int(small.sum())
        po, outer, small, small_o = _hull_pieces(po, outer, small, small_o)
        hull_x = ns_ / max(int(small.sum()), 1)  # (the pieces keep their triangle count: the hull is fewer to start)
    po["meshes"] = {"outer": outer & ~small_o, "rest": ~outer & ~small, "pieces": small, "outer_pieces": small_o}
    mr = None
    keep = 1.0 if ratio >= LOD_KEEP_PIECE_RATIO else max(ratio, LOD_KEEP_PIECE_FAR)
    if LOD_MADE_FLOOR:
        mr = {"outer": ratio, "rest": max(ratio, min(LOD_MADE_FLOOR, LOD_MADE_FLOOR_X * ratio)), "pieces": min(1.0, keep * hull_x),
              "outer_pieces": keep}
    elif small_o.any():
        mr = {"outer_pieces": keep}
    seat0 = None
    if LOD_SEAT_PATCHES and small_o.any() and ratio < 1.0:  # (r58) the pieces' LOD0 offsets off the panel
        V0 = np.asarray(po["verts"], np.float64)
        vs0, _, _, off0, d0 = _patch_offsets(V0, np.asarray(po["corner_vert"], np.int64).reshape(-1, 3), outer & ~small_o,
                                             small_o, np.asarray(po["normal"], np.float64))
        seat0 = (V0[vs0], np.where(d0 < LOD_SEAT_REACH, off0, 0.0))
    q, wq, r = lod_part(po, weights, ratio, shapes=shapes, mesh_ratios=mr)
    qm = q.pop("meshes")
    mo = np.asarray(qm["outer"], bool) | np.asarray(qm["outer_pieces"], bool)
    T = np.asarray(q["corner_vert"], np.int64).reshape(-1, 3)
    co = np.repeat(mo, 3)
    V = np.asarray(q["verts"], np.float64)
    if seat0 is not None:
        V = V.copy()
        r = dict(r, patches_seated=_seat_patches(V, T, np.asarray(qm["outer"], bool), np.asarray(qm["outer_pieces"], bool),
                                                 np.asarray(q["normal"], np.float64), *seat0))
        q = dict(q, verts=V.astype(np.float32))
    vu, inv = np.unique(T[mo], return_inverse=True)
    vn = np.zeros((len(vu), 3))
    np.add.at(vn, inv.ravel(), np.asarray(q["normal"], np.float64)[co])
    vn /= np.maximum(np.linalg.norm(vn, axis=1, keepdims=True), 1e-12)
    nv0 = len(V)
    Ti = (inv.reshape(-1, 3) + nv0)[:, [0, 2, 1]]
    ci = np.arange(len(T) * 3).reshape(-1, 3)[mo][:, [0, 2, 1]].ravel()  # outer corners, in the inner's order
    out = dict(q)
    out["verts"] = np.r_[V, V[vu] - vn * th].astype(np.float32)
    Tr = T[~mo]
    cr = np.arange(len(T) * 3).reshape(-1, 3)[~mo].ravel()
    co_ = np.arange(len(T) * 3).reshape(-1, 3)[mo].ravel()
    out["corner_vert"] = np.r_[T[mo].ravel(), Ti.ravel(), Tr.ravel()].astype(np.int64)
    for k, sg in (("uv", 1), ("normal", -1), ("tangent", 1), ("sign", -1)):
        a = np.asarray(q[k])
        out[k] = np.concatenate([a[co_], sg * a[ci], a[cr]]).astype(np.float32)
    if q.get("vcolor") is not None:
        out["vcolor"] = np.r_[q["vcolor"], np.asarray(q["vcolor"])[vu]].astype(np.float32)
    if q.get("shapes"):
        out["shapes"] = {nm: (np.r_[d, np.asarray(d)[vu]], np.r_[a0, -np.asarray(a0)[vu]], np.r_[a1, -np.asarray(a1)[vu]])
                         for nm, (d, a0, a1) in q["shapes"].items()}
    if wq is not None:
        wq = (np.r_[wq[0], np.asarray(wq[0])[vu]], np.r_[wq[1], np.asarray(wq[1])[vu]].astype(np.float32))
    out["shell"] = {"outer": int(mo.sum()), "thickness": th}
    if LOD_MADE_GAP and (~mo).any() and mo.any():
        r = dict(r, made_lifted=_lift_made(out, int(mo.sum())))
    r = dict(r, triangles0=nt, triangles=len(out["corner_vert"]) // 3, shell=True)
    return out, wq, r


LOD_MADE_FLOOR = 0.35  # (r54) a two-sided garment's made pieces (pockets, collar, lapels, buttons: the triangles after its
# shells) keep at least this share at every LOD: at the coat's LOD2 share (0.11) its 1,176 made-piece triangles went to
# 134, the pockets became fans of a few long triangles and the decimated outer shell came through them (grey fans on the
# LOD1-3 fronts, r54/zoom4.png). ~1.2k triangles at LOD0, so the floor costs ~350 at LOD3.
LOD_MADE_FLOOR_X = 2.0  # (r55) ... but at most this x the LOD's ratio: the flat 0.35 put LOD3 164 over its 12,360 (lapels at
# 2 x the shell's resolution still read at LOD3's distance)
LOD_KEEP_PIECE = 200  # triangles: (r55) a made piece that is its own small connected piece (a button: 174) is decimated
# apart from the collar / lapels: decimated with them at the made floor, rc2d's buttons became grey cones. Kept whole ...
LOD_KEEP_PIECE_RATIO = 0.1  # ... at LODs whose ratio is at least this (LOD1, LOD2), and below it (LOD3) at
LOD_KEEP_OUTER_PIECES = True  # (r56) ... and so is a small piece of the OUTER shell (a patch pocket: 106 triangles, 62
# of their vertices on its border). Welded with the coat it was decimated with its border held: at LOD2 a fan of ~60
# long triangles from one vertex, the pale streaks the coordinator saw after LOD_REWIND. Its inner shell is rebuilt with
# the outer's. (LOD_FOLD_GUARD below did not help: the fan never bends, it is the border held around no interior.)
LOD_KEEP_PIECE_FAR = 0.15  # this share (a button is a few pixels at LOD3's switch distance)


LOD_PATCH_GAP = 0.006  # m: (r56) ... only a small outer piece lying ON the rest of the outer shell (its vertices' median
# distance to the rest's surface under this: a patch pocket ~2.6 mm) is kept whole: rc2f's sweater, its outer shell cut
# into many small pieces by the garment cull, stayed at 3,836 triangles from LOD1 to LOD2 (LOD2 2.4k over budget).


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
    out[idx] = med[lab[inv[:, 0]]] < LOD_PATCH_GAP
    return out


LOD_KEEP_PIECE_HULL = True  # (r61) at the far LOD (ratio below LOD_KEEP_PIECE_RATIO) a small made piece (a button) is
# replaced by its convex hull before it is decimated: fqmr took rc2l's 174-triangle buttons (a dome with four thread
# holes) to ~26 crumpled triangles at LOD3; the hull (on the piece's own vertices: uv, weights, shapes carried) is a clean
# lens that decimates to a clean lens


LOD_KEEP_PIECE_HULL_FLAT = 0.08  # ... not a piece flatter than this (thinnest / widest spread)


def _hull_pieces(po: dict, outer: np.ndarray, small: np.ndarray, small_o: np.ndarray):
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
        if sv_[-1] < LOD_KEEP_PIECE_HULL_FLAT * sv_[0]:  # (a flat piece: a label, a patch; its hull is the piece twice)
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
        return po, outer, small, small_o
    keepc = np.repeat(~drop, 3)
    out = dict(po)
    nT = np.concatenate(newT)
    out["corner_vert"] = np.r_[np.asarray(po["corner_vert"], np.int64)[keepc], nT.ravel()]
    for k in ckeys:
        out[k] = np.concatenate([np.asarray(po[k])[keepc], np.concatenate(newc[k]).astype(np.asarray(po[k]).dtype)])
    add = np.zeros(len(nT), bool)
    return out, np.r_[outer[~drop], add], np.r_[small[~drop], ~add], np.r_[small_o[~drop], add]


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


LOD_MADE_GAP = 0.001  # m: (r54) ... and every made-piece vertex whose garment's decimated outer shell lies less than this
LOD_MADE_REACH = 0.008  # m: ... inside it (within this along its normal, either way) is lifted out to this over it


LOD_LIFT_RIGID = True  # (r56) see _lift_made


def _lift_made(out: dict, n: int, gap: float = None, reach: float = None) -> int:
    """(r54) Made pieces (triangles after the two shells) put back OVER their garment's decimated outer shell: decimated
    apart, the shell's error (mm) is bigger than a pocket's lift off it (~2.6 mm median on Tess's coat), so the coat came
    through the pockets / lapels. Positions only; returns the vertices moved. In place on out["verts"]."""
    gap = LOD_MADE_GAP if gap is None else gap
    reach = LOD_MADE_REACH if reach is None else reach
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
    if LOD_LIFT_RIGID and LOD_KEEP_PIECE:  # (r56) a small piece (a button) moves as one: lifted vertex by vertex, rc2e's
        # LOD2 buttons (kept whole) came out lumpy. Each takes its largest lift along its mean lift direction.
        T = rest_c.reshape(-1, 3)
        sp = _small_pieces(rest_c, np.ones(len(T), bool), LOD_KEEP_PIECE)
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


LOD_REWIND = True  # (r55) see lod_part: folded-over decimated triangles wound to face their normals
LOD_WELD = True  # (r51) a part whose per-patch decimation misses its share (patch borders are kept: uv seams, smoothing
# groups) is decimated welded instead, per mesh, and each new triangle takes the uv island of the LOD0 triangle nearest it
LOD_WELD_OVER = 1.25  # ... when the per-patch result has more than this x the share's triangles. Tess's r50 body (a template
# wrap cut into many uv islands) stopped at 3,238 and the coat / jeans at ~3.5k / 3.0k from LOD1 to LOD3: the islands'
# borders were the floor, so LOD2 / LOD3 went over budgets.py's shares.
LOD_BORDER_OVER = 1.25  # (r52) a welded mesh still over this x its share is redecimated with border collapses allowed:
# pattern-piece cloth is mostly border (sim seams are not coincident vertices; rc2's LOD3 coat 3,492 triangles had 2,074
# border edges), so the coat / jeans / sweater stayed at 3.5k / 3.0k / 2.4k from LOD2 to LOD3 even welded.


LOD_BORDER_SHARED = False  # (r59, OFF after rc2j: changed nothing at LOD2 (the fly slit stayed, counts identical), +1.3k at LOD3 (jeans 346 -> 1012), neckline unchanged) the LOD_BORDER_OVER redecimation (border collapses) is skipped for a group of a part whose
# border touches another group of it (within LOD_SEAM_WELD): rc2i's LOD2 jeans opened a slit at the fly (body skin and the
# coat's inside seen through it: no jeans along the pick ray), its panel's border collapsed away from the made piece's
LOD_SEAM_WELD = 0.002  # m: (r53) in a welded decimation, BORDER vertices closer than this are joined first. The border
# collapses alone (LOD_BORDER_OVER) met the shares but opened the sim's seams (0.1-0.5 mm apart, not shared vertices):
# rc2b's LOD2 / 3 coat showed grey slits at its seams and pockets. Joined, a seam is an inner edge (decimated across like
# cloth) and only the true openings (hems, front edges, cuffs) stay borders.

LOD_SEAM_WELD_NO_CHAIN = True  # (r60) see _weld_seams


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
    if LOD_SEAM_WELD_NO_CHAIN:  # (r60) clusters grown pair by pair, nearest first, never joining two vertices of one edge
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


LOD_FOLD_GUARD = ()  # (r56, off: see LOD_KEEP_OUTER_PIECES; (2.0, 4.0) to try) a welded decimation that folds triangles over (rc2e's LOD2 coat pockets: 64 of 151;
# LOD_REWIND only turned them to face out, the pale fan streaks stayed) is redone with the LOD0 triangles around the
# folds cut out as their own piece (borders held, so the two pieces still share their cut) at these x the ratio in turn,
# kept whole when both still fold; the rest is decimated to what is left of the target.
LOD_FOLD_GROW = 2.0  # ... the cut-out: LOD0 triangles within this x a folded triangle's longest edge of its centroid


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
    reach = LOD_FOLD_GROW * np.max([np.linalg.norm(Pn[:, (i + 1) % 3] - Pn[:, i], axis=1) for i in range(3)], 0)
    c0 = V0[F0].mean(1)
    kd = cKDTree(c0)
    cut = np.zeros(len(F0), bool)
    for c, rr in zip(Pn.mean(1), reach):
        cut[kd.query_ball_point(c, rr)] = True
    if cut.all() or not cut.any():
        return Vw, Fw
    Fr, Fs = F0[~cut], F0[cut]
    for x in LOD_FOLD_GUARD:
        rs = min(1.0, x * ratio)
        ts = len(Fs) if rs >= 0.999 else int(round(len(Fs) * rs))
        Vs, Fs_ = (V0, Fs) if rs >= 0.999 else _decimate(V0, Fs, ts)
        Vr, Fr_ = _decimate(V0, Fr, max(tgt - len(Fs_), int(round(len(Fr) * ratio * 0.5))))
        if not (_folds(V0, F0, Vs, Fs_).any() or _folds(V0, F0, Vr, Fr_).any()):
            break
    else:
        Vs, Fs_ = V0, Fs
    return np.r_[Vr, Vs], np.r_[Fr_, Fs_ + len(Vr)]


LOD_DEV_MAX = 0.015  # m: (r60) a welded group's decimation whose farthest LOD0 vertex lies more than this off the result is
# redone with LOD_DEV_GROW x the target (up to LOD_DEV_TRIES times): fqmr reaches a small target by raising its error
# threshold until it collapses across a deep fold (rc2j's LOD2 jeans: the crotch bridged front to back, 41 mm off LOD0, the
# body seen through a slit at the fly; the outer shell at 0.11 = 369 triangles)
LOD_DEV_GROW = 1.3
LOD_DEV_MIN_TRIS = 1000  # (r61, = MIN_PART) groups with fewer LOD0 triangles than this are not redone (small parts: shoes, soles); at their small_far ratio (0.5) the bound is 3.3 mm, so the guard grew rc2l's LOD2 shoes 371 -> 629, soles 143 -> 243 (rc2i's were fine)
LOD_DEV_REF = 0.11  # ... LOD_DEV_MAX holds at this ratio and scales with (LOD_DEV_REF / ratio) ** LOD_DEV_POW (farther LODs, coarser)
LOD_DEV_POW = 1.0
LOD_DEV_TRIES = 2  # (4: LOD3 coat 976 -> 2304, over the LOD3 budget; 2: ~ +0.8k at LOD3, +1.0k at LOD2)


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
    if LOD_BORDER_SHARED and len(np.unique(grp)) > 1:  # (r59) each group's vertices, to find borders shared with another
        for g in np.unique(grp):
            gtree[g] = cKDTree(P[np.unique(Tall[grp == g])])
    for g in np.unique(grp):
        tg = np.flatnonzero(grp == g)
        r_ = ratio
        if mesh_ratios and tri_mesh is not None:
            r_ = float(mesh_ratios.get(mnames[int(g)], ratio))
        gv, Fl = np.unique(Tall[tg], return_inverse=True)
        Fl = Fl.reshape(-1, 3)
        if r_ >= 0.999 or len(tg) < MIN_PATCH:
            Vw, Fw = P[gv], Fl
        else:
            tgt = int(round(len(tg) * r_))
            if LOD_SEAM_WELD:  # (r53) sim seams closed first: border vertices this close are one vertex
                Fl = _weld_seams(P[gv], Fl, LOD_SEAM_WELD)
            Vw, Fw = _decimate(P[gv], Fl, tgt)
            shared_, bo_ = False, False
            if gtree:  # (r59) a border this group shares with another (a fly / placket piece on its panel) must not move
                E_ = np.sort(np.r_[Fl[:, [0, 1]], Fl[:, [1, 2]], Fl[:, [2, 0]]], 1)
                u_, c_ = np.unique(E_, axis=0, return_counts=True)
                bv_ = P[gv][np.unique(u_[c_ == 1])]
                shared_ = len(bv_) > 0 and any(
                    np.isfinite(t_.query(bv_, distance_upper_bound=LOD_SEAM_WELD)[0]).any() for g2, t_ in gtree.items() if g2 != g)
            if LOD_BORDER_OVER and not shared_ and len(Fw) > LOD_BORDER_OVER * max(tgt, 1):
                Vb, Fb = _decimate(P[gv], Fl, tgt, border=False)
                if 0 < len(Fb) < len(Fw):
                    Vw, Fw, bo_ = Vb, Fb, True
            if LOD_DEV_MAX and len(Fw) and len(tg) >= LOD_DEV_MIN_TRIS:  # (r60) a decimation that strays far from LOD0 is redone at a bigger target
                for _ in range(LOD_DEV_TRIES):
                    if _deviation(P[gv], Vw, Fw) <= LOD_DEV_MAX * (LOD_DEV_REF / max(r_, 1e-3)) ** LOD_DEV_POW:
                        break
                    tgt = int(round(tgt * LOD_DEV_GROW))
                    if tgt >= len(Fl):
                        Vw, Fw = P[gv], Fl
                        break
                    Vw, Fw = _decimate(P[gv], Fl, tgt, border=not bo_)  # (as the pass it redoes: border collapses
                    # too where the border-over pass was taken)
            if len(Fw) == 0:
                Vw, Fw = P[gv], Fl
            if LOD_FOLD_GUARD:
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
        if len(tf) < MIN_PATCH or r_ >= 0.999:
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
    if LOD_WELD and ratio < 0.999 and got > LOD_WELD_OVER * max(target, 1) and got > MIN_PATCH:
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
    if LOD_REWIND and len(F) and ratio < 0.999:  # (r55) a collapse that folds a triangle over leaves it wound against
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
    keep_sh = {nm: v for nm, v in (p.get("shapes") or {}).items() if shapes or nm.startswith(POSE_SHAPE)}
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


RIBBON_WIDEN = 3.0  # a ribbon LOD widens its kept ribbons by 1 / ratio, at most this (coverage at a distance)


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
    w = min(1.0 / max(ratio, 1e-6), RIBBON_WIDEN)
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
        small_far = (len(p["corner_vert"]) // 3 < MIN_PART and r_pn < LOD_SMALL_FAR_RATIO and pn not in LOD_SMALL_KEEP
                     and pn not in skip and LOD_SMALL_FAR)
        if small_far:  # (r55) the far LOD: small parts halve too
            q, wq, r = lod_part(p, w, max(r_pn, LOD_SMALL_FAR), mesh_ratios=mesh_ratios, shapes=shapes)
            out[pn], rep[pn] = q, dict(r, small_far=True)
            if wq is not None:
                neww[pn] = wq
            continue
        if pn in skip or len(p["corner_vert"]) // 3 < MIN_PART:
            out[pn] = p if shapes or not p.get("shapes") else {
                **{k: v for k, v in p.items() if k != "shapes"},
                **({"shapes": {nm: v for nm, v in p["shapes"].items() if nm.startswith(POSE_SHAPE)}}
                   if any(nm.startswith(POSE_SHAPE) for nm in p["shapes"]) else {})}
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


LOD_UNDER_GAP = 0.002  # m: (r53) an under garment's vertex is put at least this far under its cover at every LOD
LOD_UNDER_FACES = True  # (r57) push_under_layers also tests points inside faces (a long face pokes between vertices)
LOD_UNDER_FACE_GRID = 4  # (r58) ... a barycentric grid with this many steps per edge (corners left out) + the centroid (1 = the centroid alone):
# rc2h LOD2 showed a hexagonal sweater patch through the coat at her right armhole (flat-ID render + a ray pick: sweater
# 5 mm in front of the coat) where every vertex AND centroid was under it: the coat bends between them
LOD_UNDER_ORIENT = True  # (r67) under_depth: outward normals agree with the nearest cover's facing
LOD_UNDER_FACE_ALIGN = 0.5  # (r67) a poking face moves only corners whose normal is within 60 deg of its own
LOD_UNDER_FACE_DEEP = 0.008  # m: (r58) a face point more than this outside its cover is not a poke but a face that runs
# out from under the cover's edge (a sweater cuff past the coat sleeve: -20 mm at the grid points), left alone
LOD_UNDER_FACE_DEEP_FAR = 0.015  # m: (r61) ... at the far LOD (ratio below LOD_SMALL_FAR_RATIO: LOD3), where a coarse cover
# folds farther: rc2l's LOD3 sweater face stood 12 mm in front of the coat at her right armhole (an orange wedge), its
# vertices under (0.03 pushed a cuff out instead)
LOD_UNDER_LOD0_NORMAL = True  # (r59) see push_under_layers: a last pass along the LOD0 normals (parts with masks)
LOD_UNDER_WORN_MAX = 0.01  # m: (r61) see push_under_layers; 0 = off
LOD_UNDER_REACH = 0.02  # m: ... when its cover lies within this along the vertex's normal (either way)


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


def under_depth(p: dict, covers: list[dict], reach: float = LOD_UNDER_REACH):
    """For each outward vertex of `p` (_vertex_out): the signed distance along its outward normal to the NEAREST
    surface of `covers` within `reach` either way (+ = the cover is outside it, as it should be; - = the vertex pokes
    through), nan where no cover is in reach."""
    vid, N, fol = _vertex_out(p)
    V = np.asarray(p["verts"], np.float64)
    if LOD_UNDER_ORIENT and len(vid) and covers:  # (r67) a fold's vertex normal can point INTO the body: its cover then
        # reads as behind it (a poke) and the push moved it out (rc2s LOD0: 2 sweater vertices 5 mm out of the coat's
        # back, none before the push). Out = the side the nearest cover surface faces.
        Q, QN = _cover_samples(covers)
        d, j = cKDTree(Q).query(V[vid], distance_upper_bound=reach)
        ok = np.isfinite(d)
        flip = ok & ((N * QN[np.where(ok, j, 0)]).sum(1) < 0)
        if flip.any():
            N = np.where(flip[:, None], -N, N)
    if LOD_UNDER_ORIENT:
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


LOD_UNDER_MAX_MOVE = 0.010  # m: (Garrett s8) no push-under moves a garment vertex further (0 = no cap)
# LOD_UNDER_ORIENT (above) also gates orient_to_covers: (Garrett s7) the under part's "outward" normals agree with the nearest cover's outward


def orient_to_covers(P: np.ndarray, N: np.ndarray, covers: list[dict], reach: float = LOD_UNDER_REACH) -> np.ndarray:
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


def cover_depth(P: np.ndarray, N: np.ndarray, covers: list[dict], reach: float = LOD_UNDER_REACH) -> np.ndarray:
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


def under_at_lod0(p: dict, covers: list[dict], reach: float = LOD_UNDER_REACH, share: bool = False) -> tuple:
    """(r54) A part's outward vertices at LOD0 and whether each lies UNDER `covers` there (a cover in reach outside it):
    push_under_layers' `masks`, for parts worn under garments that are not garments themselves (socks, the body),
    so only what was under a garment at LOD0 is put back under it (a shoe over the jeans' hem stays over it)."""
    vid, N_, _, t = under_depth(p, covers, reach)
    under = np.isfinite(t) & (t > 0)
    if share:  # (r55) ... and the share of its vertices with a cover in reach that are under it
        return (np.asarray(p["verts"], np.float64)[vid], under, float(under.sum() / max(int(np.isfinite(t).sum()), 1)),
                np.isfinite(t) & (t < 0), N_)  # (and the vertices OVER a cover at LOD0, and (r59) their LOD0 normals)
    return np.asarray(p["verts"], np.float64)[vid], under


LOD_UNDER_CULL_FROM = 2  # (r60) from this LOD on, a part worn under garments (not the skin: socks) drops the faces whose
# LOD0 points were all under a garment more than LOD_UNDER_CULL_RIM from the nearest LOD0 point that was not: the LOD0 cull
# keeps a 40 mm rim under every opening (close up, a hem rides up), and rc2j's LOD2 showed that rim (the socks' tops) as a
# shard through the decimated jeans' calf, which pushing in along either normal did not cure (socks poking 42 -> 8)
LOD_UNDER_CULL_RIM = 0.015  # m
LOD_UNDER_CULL_GARMENTS_FROM = 1  # (Garrett s10) from this LOD on, an under GARMENT (the shirt) drops its faces that were
# deep under its covers at LOD0 the same way (cull_covered, the same rim): v7's LOD1 back showed a long white shirt shard down
# the right forearm sleeve where the decimated sleeve dips more than LOD_UNDER_MAX_MOVE under the LOD0 shirt (shirt poking
# 86 -> 36, 192 capped); a bigger push sent the shirt out through the other side (v6b), so the hidden faces go instead


def cull_covered(p: dict, P0: np.ndarray, under0: np.ndarray, rim: float = LOD_UNDER_CULL_RIM) -> np.ndarray:
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


LOD_UNDER_ISLAND = 24  # (r65) faces: a patch of faces deeper than LOD_UNDER_FACE_DEEP outside the cover is still a poke
# when it is a small island (at most this many faces) and every face around it is under the cover (rc2p LOD0: a 10-face
# sweater flap 8-22 mm through the coat's upper back, kept as "a face that runs outside" at every export); 0 = off


def ringed_islands(F: np.ndarray, deep_t: np.ndarray, t: np.ndarray, nv: int, most: int | None = None) -> np.ndarray:
    """(r65) faces (rows of F) that stand deeper outside their cover than the face test trusts (deep_t < 0 where t, the
    trusted depth, is inf) but form a small island (<= most faces, sharing vertices) whose every neighbouring face is
    under the cover (t finite, >= 0): a flap poking through, not a garment running outside its cover (an open front's
    edge has neighbours with no cover: kept)."""
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components
    most = LOD_UNDER_ISLAND if most is None else most
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


LOD_UNDER_STRAY = 0.03  # m (r66): an under-layer vertex with NO cover along its own normal (within the reach) but outside
# its cover's nearest surface (signed by the cover's outward normal) by up to this, in a small island ringed by vertices
# under the cover, is a flap through it: moved in along the cover's normal to the gap under it. rc2p/q's coat speck: a
# sweater flap 17-23 mm out of the coat's back whose vertex normals point sideways (0.78, -0.55, 0.28): along them no
# cover in reach, so neither the vertex nor the face test ever saw it (game_ready.md r66). 0 = off.


def stray_flaps(p: dict, covers: list[dict], reach: float = LOD_UNDER_REACH, far: float | None = None,
                most: int | None = None) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """(r66) push_under_layers' flaps: (vertex ids, how far outside, the cover's outward normal there). Candidates are
    outward vertices with no cover along their normal within `reach` (under_depth nan); "outside" = the nearest cover
    sample (outer-shell triangle centres and corners, normals from their faces) within `far` has the vertex on its outward
    side. Kept only as small islands (<= most vertices, by the part's faces) every neighbour of which lies under a cover."""
    far = LOD_UNDER_STRAY if far is None else far
    most = LOD_UNDER_ISLAND if most is None else most
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


def push_under_layers(parts: dict, stack: dict, gap: float = LOD_UNDER_GAP, reach: float = LOD_UNDER_REACH,
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
        if LOD_UNDER_STRAY:  # (r66) flaps through the cover that no normal-line test sees: in along the cover's normal
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
            if LOD_UNDER_FACES:  # (r57) a long face can poke through a cover that bends between its vertices, all of
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
                    B = face_grid(LOD_UNDER_FACE_GRID)
                    tf = cover_depth(np.einsum("bk,fkd->fbd", B, V[F_]).reshape(-1, 3), np.repeat(nf, len(B), 0), covers,
                                     reach).reshape(len(F_), len(B))
                    fd_ = face_deep or LOD_UNDER_FACE_DEEP
                    tall = np.where(np.isfinite(tf), tf, np.inf).min(1)
                    tf = np.where(np.isfinite(tf) & (tf > -fd_), tf, np.inf).min(1)
                    if LOD_UNDER_ISLAND:  # (r65) a deep face is a poke after all when it is a small island ringed by faces
                        tf = np.where(ringed_islands(F_, tall, tf, len(V)), tall, tf)  # under the cover (rc2p's coat speck)
                    bf = np.isfinite(tf) & (tf < 0)
                    if bf.any():  # (r67) each corner moves along its own normal only as far as that normal goes in:
                        # depth / (its normal . the face's), and not at all when it turns > 60 deg from the face (a fold's
                        # corner whose normal points into the body moved 20 mm OUT: rc2q-s's coat-back speck WAS this push)
                        Fb = F_[bf]
                        al = np.einsum("fkd,fd->fk", Nv[Fb], nf[bf])
                        need = np.where(al >= LOD_UNDER_FACE_ALIGN, (tf[bf] - gap)[:, None] / np.maximum(al, LOD_UNDER_FACE_ALIGN), 0.0)
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
        if LOD_UNDER_LOD0_NORMAL and masks and un in masks and len(masks[un]) > 3 and len(masks[un][0]):
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
        if LOD_UNDER_WORN_MAX and masks and un in masks:  # (r61) a worn part (the skin) moves at most this far: rc2l's
            # LOD3 neck was pushed up to 49 mm under the sweater's collar, its big triangles dragging the visible neck
            # above the collar into dark wedges (74 of 465 front-neck vertices moved)
            dv_ = V - np.asarray(parts[un]["verts"], np.float64)
            ln_ = np.linalg.norm(dv_, axis=1)
            far_ = ln_ > LOD_UNDER_WORN_MAX
            V[far_] = np.asarray(parts[un]["verts"], np.float64)[far_] + dv_[far_] * (LOD_UNDER_WORN_MAX / ln_[far_])[:, None]
        capped = 0
        if LOD_UNDER_MAX_MOVE:  # (Garrett s8) a push-under is a few mm: a vertex sent further is a wrong normal or a
            # wrong cover (v6b: the shirt 39 mm out through the jacket sleeve), so no vertex moves more than the cap
            # (Tess r61 capped the skin at 10 mm the same way); what it leaves poking is reported
            V0 = np.asarray(parts[un]["verts"], np.float64)
            dv_ = V - V0
            dn_ = np.linalg.norm(dv_, axis=1)
            over_ = dn_ > LOD_UNDER_MAX_MOVE
            capped = int(over_.sum())
            if capped:
                V = V0 + dv_ * np.minimum(1.0, LOD_UNDER_MAX_MOVE / np.maximum(dn_, 1e-12))[:, None]
                p["verts"] = V
                vid, _, _, t = under_depth(p, covers, reach)
                if masks and un in masks and len(masks[un][0]):
                    t = np.where(masks[un][1][cKDTree(masks[un][0]).query(V[vid])[1]], t, np.nan)
        p["verts"] = V.astype(np.float32)
        parts[un] = p
        rep[un] = {"poking0": int(poke0 or 0), "poking": int((np.isfinite(t) & (t < 0)).sum()), "moved": int(moved.sum()),
                   "faces_poking0": pokef, "capped": capped, "flaps": nflap}
    return rep


LASH_LODS = (0.5, 0.25, 0.1)  # share of the lashes' triangles kept at LOD1, 2, 3 (whole lashes, longest first): they
# were 4.9k at every LOD, more than the hero's whole eyes / mouth / lashes budget at LOD0 (budgets.json)


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
