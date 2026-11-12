"""The native head on the body: pivot, bib, seat, the neck's follow, its size and description, the style lift,
the neck field and fade. Part of the one mesh (onemesh.py has the overview)."""
from __future__ import annotations

import json

import numpy as np

from . import onemesh
from .onemesh import _reference, _similar, asset, body_params

def _pivot(params: dict) -> tuple:
    """Where GNM's HEAD JOINT (joint 1: the skull on the spine) lies on the MakeHuman body made from `params`, and the
    size of that body's own head over GNM's template: GNM's template fitted (translation + uniform scale) to the head
    the body carries, above the neck. -> (pivot (3,), k)."""
    from . import base_identity
    g = base_identity._gnm_data()
    r = _reference()
    a = asset()
    bd = onemesh.bound(params, 1.0)
    m = r["val"] & (a["g_lev"].astype(int) >= r["meta"]["RING"] + 12)  # (the skull and face: not the neck's rings)
    Xg = g["template_vertex_positions"].astype(float) @ onemesh._RG.T
    c0, c1, k = _similar(Xg[m], bd["B"][m])
    return c1 + k * (g["template_joint_positions"].astype(float)[1] @ onemesh._RG.T - c0), k


def _closest(X: np.ndarray, V: np.ndarray, T: np.ndarray, k: int = 12) -> tuple:
    """Closest points of a triangle mesh (V, T) to points X: (points (n, 3), barycentric (n, 3), triangle (n,))."""
    from scipy.spatial import cKDTree
    from .rig_template import _closest_on_triangles
    X = np.asarray(X, float)
    k = min(k, len(T))
    cand = cKDTree(V[T].mean(1)).query(X, k=k)[1].reshape(len(X), k)
    best, bb, bt = np.full(len(X), np.inf), np.zeros((len(X), 3)), np.zeros(len(X), int)
    for j in range(k):
        t = T[cand[:, j]]
        w, d = _closest_on_triangles(X, V[t[:, 0]], V[t[:, 1]], V[t[:, 2]])
        take = d < best
        best[take], bb[take], bt[take] = d[take], w[take], cand[take, j]
    return (bb[:, :, None] * V[T[bt]]).sum(1), bb, bt


def _bib() -> dict:
    """GNM's BIB: the part of its skin under the seam ring (rings 0 .. RING: the neck's base, the pit of the throat,
    the clavicle line, the slope of the trapezius), which the one mesh leaves out. {"tri": triangles (GNM vertex
    ids), "lev": ring per GNM vertex, "ids": its vertices}. It is GNM's own statement of how this head's neck meets
    shoulders: the head is seated by it and the body's neck base is laid on it (`_seat`, `_neck_follow`)."""
    if "bib" not in onemesh._CACHE:
        from . import base_identity
        g = base_identity._gnm_data()
        lev = asset()["g_lev"].astype(int)[:len(g["template_vertex_positions"])]
        ring = _reference()["meta"]["RING"]
        Q = np.asarray(g["quads"])
        Q = Q[((lev[Q] >= 0) & (lev[Q] <= ring)).all(1)]
        onemesh._CACHE["bib"] = {"tri": np.r_[Q[:, [0, 1, 2]], Q[:, [0, 2, 3]]], "lev": lev, "ids": np.unique(Q)}
    return onemesh._CACHE["bib"]


def _seat(params: dict, Vid: np.ndarray, Jid: np.ndarray) -> np.ndarray:
    """Where GNM's head joint goes on the MakeHuman body of `params`: the head is SEATED BY ITS OWN NECK BASE. Start
    skull on skull (`_pivot`), then move the head up / down and forward / back until its bib (GNM's own shoulder
    slope and throat, rings SEAT_RINGS) lies on the body's shoulders: least squares of the bib's distances to the
    body's surface along the surface's normal. Vid: GNM's evaluation of the identity (world axes, x size); Jid: its
    head joint. General: no constant of any one character in it."""
    key = ("seat", json.dumps(params, sort_keys=True, default=float), hash(Vid.tobytes()))
    if key in onemesh._CACHE:
        return onemesh._CACHE[key]
    mb = onemesh.bound(params, 1.0)["mh"]
    P = np.asarray(mb["P"], float)
    faces, i = [], 0
    for n in mb["S"]:
        faces.append(mb["L"][i:i + n])
        i += n
    T = np.array([(f[0], f[j], f[j + 1]) for f in faces for j in range(1, len(f) - 1)], int)
    piv = _pivot(params)[0]
    b = _bib()
    ids = b["ids"][(b["lev"][b["ids"]] >= onemesh.SEAT_RINGS[0]) & (b["lev"][b["ids"]] <= onemesh.SEAT_RINGS[1])]
    X0 = Vid[ids] - Jid  # the bib about the head joint
    zc = piv[2] + X0[:, 2].mean()
    T = T[(np.abs(P[T][:, :, 2] - zc) < 0.25).all(1) & (np.abs(P[T][:, :, 0]) < 0.3).all(1)]
    Nf = np.cross(P[T[:, 1]] - P[T[:, 0]], P[T[:, 2]] - P[T[:, 0]])
    Nf /= np.linalg.norm(Nf, axis=1, keepdims=True) + 1e-15
    t = np.zeros(3)
    for _ in range(12):
        X = piv + t + X0
        q, _, ti = _closest(X, P, T)
        n = Nf[ti]
        r = ((q - X) * n).sum(1)
        ok = np.linalg.norm(q - X, axis=1) < onemesh.SEAT_REACH
        if ok.sum() < 30:
            break
        A = n[ok][:, 1:]  # (y, z): the centre line stays the centre line
        dt = np.linalg.lstsq(A.T @ A + 1e-9 * np.eye(2), A.T @ r[ok], rcond=None)[0]
        t[1:] += dt
        if np.abs(dt).max() < 5e-5:
            break
    out = piv + t
    onemesh._CACHE[key] = out
    return out


def _neck_follow(rest: np.ndarray, start: np.ndarray, faces: list, n_body: int, ring: np.ndarray, reach: float,
                 bibV: np.ndarray) -> np.ndarray:
    """The body's neck base and shoulder slope LAID ON GNM's own bib next to the head, fading into the body's own
    shoulders: where the body's vertices go (n_body, 3). rest: the fused mesh as the body alone would have it;
    start: where the vertices start (the head's rows at GNM's places: fixed); bibV: every GNM vertex as placed.
    Each round the free vertices (the body's, within `reach` of the ring over the surface) are evened out ALONG the
    surface (toward their neighbours' mean, the normal's part left out) and put back on the target surface: the
    point of GNM's bib nearest them x w + the point of the body's own rest surface nearest them x (1 - w), w = 1
    from ring BIB_FULL up, 0 from BIB_NONE down. Nothing is pulled through space (the first version's displacement
    field dragged the trapezius 3 cm down to the ring: a column on a shelf); rows only slide on a surface that is
    GNM's by the head and the body's at the shoulders."""
    import scipy.sparse as sp
    from scipy.sparse.csgraph import dijkstra
    from . import retopo
    n = len(rest)
    tris = np.array([(f[0], f[j], f[j + 1]) for f in faces for j in range(1, len(f) - 1)], int)
    e = np.r_[tris[:, [0, 1]], tris[:, [1, 2]], tris[:, [2, 0]]]
    G = sp.coo_matrix((np.linalg.norm(rest[e[:, 0]] - rest[e[:, 1]], axis=1) + 1e-9, (e[:, 0], e[:, 1])), (n, n)).tocsr()
    G = G.maximum(G.T)
    dist = dijkstra(G, directed=False, indices=np.asarray(ring, int), min_only=True)
    free = np.flatnonzero((np.arange(n) < n_body) & (dist < reach))
    if not len(free):
        return start[:n_body].copy()
    A = (G > 0).astype(float)
    deg = np.asarray(A.sum(1)).ravel()
    edge = np.clip((reach - dist[free]) / (0.25 * reach), 0, 1)[:, None]  # nothing moves at the zone's rim
    b = _bib()
    lev = b["lev"].astype(float)
    Tr = tris[(dist[tris] < reach + 0.08).all(1)]  # the body's own surface round the zone (its neck included)
    Y = start.copy()
    for it in range(onemesh.FOLLOW_ITERS):
        if it % 4 == 0:
            N = retopo._vnormals(Y, tris)[free]
        d = (A[free] @ Y) / deg[free, None] - Y[free]
        X = Y[free] + 0.5 * edge * (d - (d * N).sum(1, keepdims=True) * N)
        qb, wb, tb = _closest(X, bibV, b["tri"])
        rho = (wb * lev[b["tri"][tb]]).sum(1)
        w = np.clip((rho - onemesh.BIB_NONE) / (onemesh.BIB_FULL - onemesh.BIB_NONE), 0, 1)
        w = (w * w * (3 - 2 * w))[:, None]
        qm = _closest(X, rest, Tr)[0]
        Y[free] = Y[free] + edge * ((1 - w) * qm + w * qb - Y[free])
    return Y[:n_body]


def native_size(base: dict) -> dict:
    """A native head's SIZE rule, and the neck ANSUR expects under it: {"stature" (the stated one: base.body.height, or
    MakeHuman's own for the age), "sex", "size" (base.head.size, else (stature / the sex's mean stature) ^ alpha: the
    head goes a little with the stature), "allometric": bool, "neck": ANSUR II's mean neck girth for this sex and
    stature (m), "neck_sd" (m)}. The same for any body: no constant of a character."""
    from . import makehuman
    params = body_params(base)
    user = base.get("head") or {}
    stature = float(params["height"]) if params.get("height") else float(np.asarray(makehuman.body(params)["P"])[:, 2].max())
    sex = float(np.clip(params.get("sex", 1.0), 0, 1))
    s0 = (1 - sex) * onemesh.ANSUR_STATURE[0] + sex * onemesh.ANSUR_STATURE[1]
    al = (1 - sex) * onemesh.ANSUR["head_height"][0][1] + sex * onemesh.ANSUR["head_height"][1][1]
    given = isinstance(user.get("size"), (int, float))
    size = float(user["size"]) if given else float((stature / s0) ** al)
    w = [(v0 * (stature / st0) ** a_, sd_) for (v0, a_, sd_), st0 in zip(onemesh.ANSUR["neck_girth"], onemesh.ANSUR_STATURE)]
    neck = (1 - sex) * w[0][0] + sex * w[1][0]
    return {"stature": stature, "sex": sex, "size": size, "allometric": not given, "neck": float(neck),
            "neck_sd": float(neck * ((1 - sex) * w[0][1] + sex * w[1][1]))}


def _native_desc(base: dict, hd: dict, params: dict) -> dict:
    """head_desc for attach "native": the head's scale is GNM's (x size), the body's height is solved so the top of
    the head stands at the stated stature, and hd["bound"]["native"] carries the placement."""
    from . import base_identity
    from . import makehuman
    g = base_identity._gnm_data()
    user = base.get("head") or {}
    stature = float(params["height"]) if params.get("height") else float(np.asarray(makehuman.body(params)["P"])[:, 2].max())
    sex = float(np.clip(params.get("sex", 1.0), 0, 1))
    s0 = (1 - sex) * onemesh.ANSUR_STATURE[0] + sex * onemesh.ANSUR_STATURE[1]

    # SIZE: GNM's head is an average adult's. People's heads grow a little with their stature (ANSUR: head measures go
    # as stature ^ ~0.27): by default the head is GNM's x that, 1.000 at the sex's mean stature (a 1.95 m man 1.026, a
    # 1.50 m woman 0.977). base.head.size = a number fixes it.
    al = (1 - sex) * onemesh.ANSUR["head_height"][0][1] + sex * onemesh.ANSUR["head_height"][1][1]
    size = float(user["size"]) if isinstance(user.get("size"), (int, float)) else float((stature / s0) ** al)
    # (The NECK's length cannot follow the stature the same way: lifting the seat for a tall body was tried and does
    # nothing, the body's neck base is laid on GNM's bib wherever it stands. GNM's neck is its own length x size; on a
    # very tall body the report flags "top of head over the pit of the throat" short. Known limit.)
    # the head's top over its pivot: GNM's evaluation of the identity (what the head will be, but for expression / pose)
    ci = base_identity._gnm_coeffs(g["identity_names"], hd.get("identity") or {}, hd.get("seed"), hd.get("spread", 1.0))
    ext = np.asarray(g["skin"], bool) & (np.asarray(g["groups"]["skin_exterior"]) > 0.5)
    Vy = (g["template_vertex_positions"][ext, 1] + np.tensordot(ci, g["vertex_identity_basis"][:, ext, 1], 1)).max()
    Jy = g["template_joint_positions"][1, 1] + float(np.tensordot(ci, g["joint_identity_basis"][:, 1, 1], 1))
    top = size * float(Vy - Jy)
    from . import humanstyle
    bs = humanstyle.active(base, humanstyle.BODY)

    Vid = size * ((g["template_vertex_positions"] + np.tensordot(ci, g["vertex_identity_basis"], 1)).astype(float) @ onemesh._RG.T)
    Jid = size * ((g["template_joint_positions"][1] + np.tensordot(ci, g["joint_identity_basis"][:, 1], 1)).astype(float) @ onemesh._RG.T)

    def seat(p):
        return _seat(p, Vid, Jid)

    def pivot_height(p):  # the head joint's height over the soles on the body as it will stand (a style's longer legs lift it)
        sp_ = seat(p)
        z = float(sp_[2])
        if bs:
            lift, dz = _style_lift(p, bs, sp_)
            z += float(lift[2]) - dz
        return z
    fit = {**params, "height": round(stature, 6)}
    for _ in range(3):  # (MakeHuman's height is a uniform scale and the sliders are ratios: the seat's height goes with it)
        fit = {**params, "height": round((stature - top) * float(fit["height"]) / pivot_height(fit), 6)}
    piv0, k = _pivot(fit)
    piv = seat(fit)
    hd = {k_: v for k_, v in hd.items() if k_ not in onemesh.NATIVE_DROP}
    hd["scale"] = round(size, 9)
    hd["subdivide"] = 0
    hd["bound"] = {"body": fit, "toward": 1.0,
                   "native": {"pivot": [round(float(x), 7) for x in piv], "size": size, "stature": round(stature, 6),
                              "own": round(float(k), 6), "own_pivot": [round(float(x), 7) for x in piv0]}}
    return hd


def _style_lift(params: dict, bs: dict, at) -> tuple:
    """(how the style's body sliders move the point `at` on the MakeHuman body of `params`, the soles' new height)."""
    key = ("lift", json.dumps([params, bs, [round(float(x), 6) for x in at]], sort_keys=True, default=float))
    if key not in onemesh._CACHE:
        from . import humanstyle
        from . import retopo_warp
        mb = onemesh.bound(params, 1.0)["mh"]
        J2, girth = humanstyle.body_targets(mb["J"], bs)
        V, _, _, fn, _ = retopo_warp._skeleton_warp(np.asarray(mb["P"], float), mb["J"], {"joints": {k: {"pos": v} for k, v in J2.items()}}, [], girth=girth)
        onemesh._CACHE[key] = (fn(np.atleast_2d(np.asarray(at, float)))[0][0] - np.asarray(at, float), float(V[:, 2].min()))
    return onemesh._CACHE[key]


def head_fade(head: dict) -> np.ndarray:
    """Per GNM vertex: how much of the head's own shape a vertex takes on a one-mesh head: `neck_fade`, or 1
    everywhere on a native head (GNM's own neck down to the seam ring)."""
    if (head.get("bound") or {}).get("native"):
        return np.ones(len(asset()["g_lev"]))
    return neck_fade()


def _neck_field(X: np.ndarray, faces: list, n_body: int, D_head: np.ndarray, ring: np.ndarray, reach: float) -> np.ndarray:
    """The body's neck moved to meet a head that is NOT where the body's own head was. X: the fused mesh at rest (the
    body's vertices, then the head's where the BODY would carry them); D_head: how far each head vertex is from there;
    ring: the seam ring's rows. -> the move of the body's vertices (n_body, 3): the smoothest (biharmonic, cotangent
    weights) field that equals D_head on the head, 0 on the body beyond `reach` metres (over the mesh) from the ring.
    The head's vertices are fixed, with their neighbours' neighbours: the surface keeps its slope across the ring."""
    import scipy.sparse as sp
    from scipy.sparse.csgraph import dijkstra
    from scipy.sparse.linalg import spsolve
    n = len(X)
    tris = np.array([(f[0], f[j], f[j + 1]) for f in faces for j in range(1, len(f) - 1)], int)
    e = np.r_[tris[:, [0, 1]], tris[:, [1, 2]], tris[:, [2, 0]]]
    G = sp.coo_matrix((np.linalg.norm(X[e[:, 0]] - X[e[:, 1]], axis=1) + 1e-9, (e[:, 0], e[:, 1])), (n, n)).tocsr()
    G = G.maximum(G.T)
    dist = dijkstra(G, directed=False, indices=np.asarray(ring, int), min_only=True)
    free = np.zeros(n, bool)
    free[:n_body] = dist[:n_body] < reach
    sub = free.copy()
    A = (G > 0).astype(float)
    for _ in range(3):
        sub = sub | (A @ sub > 0)
    idx = np.flatnonzero(sub)
    loc = np.full(n, -1)
    loc[idx] = np.arange(len(idx))
    T = loc[tris[sub[tris].all(1)]]
    P = X[idx]
    m = len(idx)
    W = sp.lil_matrix((m, m))
    area = np.zeros(m)
    for a_, b_, c_ in ((0, 1, 2), (1, 2, 0), (2, 0, 1)):  # the edge (a, b) gets cot of the angle at c
        u, v = P[T[:, a_]] - P[T[:, c_]], P[T[:, b_]] - P[T[:, c_]]
        cr = np.linalg.norm(np.cross(u, v), axis=1)
        cot = np.clip((u * v).sum(1) / np.maximum(cr, 1e-14), 0.05, 20.0)  # (slivers: kept positive, bounded)
        W = W + sp.coo_matrix((0.5 * cot, (T[:, a_], T[:, b_])), (m, m))
        np.add.at(area, T[:, c_], cr / 6.0)
    W = sp.csr_matrix(W)
    W = W + W.T
    L = sp.diags(np.asarray(W.sum(1)).ravel()) - W
    Q = (L @ sp.diags(1.0 / np.maximum(area, 1e-12)) @ L).tocsr()
    fr = loc[np.flatnonzero(free)]
    fx = np.setdiff1d(np.arange(m), fr)
    Dc = np.zeros((m, 3))
    hrows = idx[fx] >= n_body
    Dc[fx[hrows]] = D_head[idx[fx[hrows]] - n_body]
    rhs = -(Q[fr][:, fx] @ Dc[fx])
    Qff = Q[fr][:, fr].tocsc()
    out = np.zeros((n_body, 3))
    out[idx[fr]] = np.column_stack([spsolve(Qff, rhs[:, j]) for j in range(3)])
    # the rows next to the ring evened out ALONG the surface (GNM's ring is not parallel to the body's top loop: where
    # it dips, the bridge's rows were squeezed and folded): each vertex toward its neighbours' mean, the part along
    # the normal left out, the ring and everything beyond NATIVE_RELAX fixed
    Y = X.copy()
    Y[:n_body] += out
    Y[n_body:] += D_head
    mv = np.flatnonzero(free & (dist < onemesh.NATIVE_RELAX * reach / onemesh.NATIVE_REACH))
    if len(mv):
        from . import retopo
        deg = np.asarray(A.sum(1)).ravel()
        fade = np.clip((onemesh.NATIVE_RELAX * reach / onemesh.NATIVE_REACH - dist[mv]) / (0.3 * onemesh.NATIVE_RELAX * reach / onemesh.NATIVE_REACH), 0, 1)[:, None]
        for it in range(onemesh.NATIVE_RELAX_ITERS):
            if it % 5 == 0:
                N = retopo._vnormals(Y, tris)[mv]
            d = (A[mv] @ Y) / deg[mv, None] - Y[mv]
            Y[mv] += 0.5 * fade * (d - (d * N).sum(1, keepdims=True) * N)
        out = Y[:n_body] - X[:n_body]
    return out


def neck_fade() -> np.ndarray:
    """Per GNM vertex 0..1: how much of the head's OWN shape (identity, warp, fit, head size) a vertex takes. The
    asset's g_fade reaches 1 seven rings (~2 cm) above the stitch: a head 14% bigger than the body's, or a warp that
    moves the nape, then met the body's neck in a ledge (a collar round the neck's base; Garrett, 2026-10-08). This
    one rises over the neck's whole length (by ring: see NECK_RINGS), never above g_fade."""
    key = ("neck_fade",)
    if key in onemesh._CACHE:
        return onemesh._CACHE[key]
    from . import base_identity
    g = base_identity._gnm_data()
    a = asset()
    f = a["g_fade"].astype(float)
    Vt = g["template_vertex_positions"].astype(float)
    if not onemesh.NECK_FADE:
        onemesh._CACHE[key] = f
        return f
    # by RING above the stitch (GNM's neck rings climb toward the nape, so a height rule gave the nape no length at
    # all): the hand-over ends NECK_RINGS[0] rings up at the throat (under the chin, which keeps its whole shape) and
    # NECK_RINGS[1] rings up at the nape (the skull's base), in between by how far back a vertex lies (GNM: z forward)
    lev = a["g_lev"].astype(float)
    l0 = float(lev[(f > 0) & (f < 0.1)].min()) if ((f > 0) & (f < 0.1)).any() else float(lev[f > 0].min())
    ring = Vt[(lev >= l0) & (lev <= l0 + 2)]
    zc, zr = float(np.median(ring[:, 2])), max(float(np.ptp(ring[:, 2])) / 2, 1e-6)
    back = np.clip((zc - Vt[:, 2]) / zr * 0.5 + 0.5, 0, 1)
    n = onemesh.NECK_RINGS[0] + (onemesh.NECK_RINGS[1] - onemesh.NECK_RINGS[0]) * back * back * (3 - 2 * back)
    t = np.clip((lev - l0) / n, 0, 1)
    out = np.where(lev >= 0, np.minimum(f, t * t * (3 - 2 * t)), f)
    onemesh._CACHE[key] = out
    return out
