"""ONE HUMAN MESH: `base: {"body": {"source": "human", ...MakeHuman's keys...}, "head": {...GNM's keys...}}`.

GNM's head topology stitched ONCE, offline, onto MakeHuman's body topology at the neck (human_mesh.npz, built by
spikes/onemesh/make_asset.py from the two packs; hand corrections in spikes/onemesh/edits.json). Nothing is grafted
when a character is built: no neck tube, no cross-fade of two point sets, no head scale, no weights copied across
a join.

How the one mesh takes its shape:
- The body is MakeHuman's (makehuman.body: age with measured growth, sex, weight, muscle, height, race, chest...).
- Every GNM skin vertex is BOUND to a point of MakeHuman's reference surface (3 body vertices + weights), so the
  body's own head (which MakeHuman shapes with the rest: a baby's, an old woman's) carries GNM's head: a similarity
  (the head's size) plus a remainder smoothed over GNM's mesh, held hard at the stitch (`bound`). Ears, lids' insides,
  nostrils and the mouth ride; eyes, teeth and tongue follow the skin beside them as rigid pieces with a scale.
- GNM's identity / expression components (and everything base.gnm_head does with them: fit, regions, pose,
  mouth_gap, eye size, planes, pushes, simplify) are applied on top, x the head's size, faded to nothing over the
  rings above the stitch (`hook`, called by base.gnm_head): the neck is always the body's.
- `template(base)` is the fused mesh as a body template (what base.source returns): MakeHuman's vertices below its
  neck loop, the bridge's, GNM's skin above its ring; `head(s, base)` is the head's dict (landmarks, eyes, carry) as
  base.head_of returns it, posed with the spec's joints by the same warp as the body.
- Skin weights are the asset's (`weights`): MakeHuman's hand-made ones, by index on the body and through the
  binding on the head.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

_CACHE: dict = {}
CLOSED_GAP = 0.0008     # m: a GNM-closed mouth (the contact ring's halves within this, corner to corner) gets the seam field
CLOSED_SEAL_V = (0.5,)  # its rows drawn toward the seam (base.SEAL_V's): the first only. The seal's three rows halved the
# vermilion border's turn; the first alone keeps the border and makes the seam a V (-60 / +27 deg each side, Tess)
VERSION = 15  # bump when the one mesh's built field changes (store's build key, base.surface's key; old paths keep theirs)
DIMORPHISM = 0.8  # as headfit's: under a seed's individuality MakeHuman's own difference reads as neither sex
ANCHORS = 48  # skin vertices a loose piece (eye, teeth, tongue) follows
HEAD_KEYS = ("toward", "dimorphism", "features", "follow_body", "like", "neck", "attach", "size")  # head keys handled
# here (the rest are base.gnm_head's)
# (headbody, 2026-10-12) base.head.attach "native": GNM's head UNTOUCHED, at GNM's own size (metres; x base.head.size),
# down to the seam ring (the asset's stitch, GNM's neck ring 13); the BODY is fitted to it (stature, neck). See `native`.
NATIVE_REACH = 0.11  # m over the body's surface from the seam ring: how far the body's neck / shoulders give to meet it
NATIVE_RELAX = 0.045  # m from the ring: the body's rows evened out along the surface after the move (the bridge)
NATIVE_RELAX_ITERS = 40
NATIVE_DROP = ("gnm_base", "gnm_base_rest", "gnm_base_blend", "gnm_base_age", "scale")  # head keys with no meaning there
_RG = np.array([[1.0, 0, 0], [0, 0, -1.0], [0, 1.0, 0]])  # GNM (Y up, facing +Z) -> world (Z up, facing -Y)


def applies(base: dict | None) -> bool:
    return bool(base) and ((base.get("body") or {}).get("source") == "human")


def asset() -> dict:
    if "asset" not in _CACHE:
        z = np.load(Path(__file__).with_name("human_mesh.npz"))
        from . import gnmloops  # the lids' extra edge loops, appended (gnmloops.py)
        _CACHE["asset"] = gnmloops.extend_asset({k: z[k] for k in z.files})
    return _CACHE["asset"]


def body_params(base: dict) -> dict:
    return {k: v for k, v in (base.get("body") or {}).items() if k != "source"}


def _reference() -> dict:
    """What the binding needs of MakeHuman's reference body and GNM's mesh, once per process."""
    if "ref" in _CACHE:
        return _CACHE["ref"]
    import scipy.sparse as sp
    from scipy.sparse.linalg import factorized
    from scipy.spatial import cKDTree

    from . import base as basemod
    from . import makehuman
    a = asset()
    meta = json.loads(str(a["meta"]))
    g = basemod._gnm_data()
    Pref = np.asarray(makehuman.body(json.loads(str(a["reference"])))["P"], float)
    val = a["g_valid"]
    tri, bar = a["g_tri"], a["g_bary"].astype(float)
    Tref = (bar[:, :, None] * Pref[tri]).sum(1)
    lev = a["g_lev"].astype(int)
    sk = np.flatnonzero(lev >= 0)  # GNM's skin component (with the mouth sock)
    loc = np.full(len(lev), -1)
    loc[sk] = np.arange(len(sk))
    quads = np.asarray(g["quads"])
    Q = loc[quads[(loc[quads] >= 0).all(1)]]
    e = np.r_[Q[:, [0, 1]], Q[:, [1, 2]], Q[:, [2, 3]], Q[:, [3, 0]]]
    m = len(sk)
    A = sp.coo_matrix((np.ones(len(e)), (e[:, 0], e[:, 1])), (m, m)).tocsr()
    A = ((A + A.T) > 0).astype(float)
    deg = np.asarray(A.sum(1)).ravel()
    L = sp.diags(np.where(deg > 0, 1.0, 0.0)) - sp.diags(1 / np.maximum(deg, 1)) @ A
    lips = (g["groups"]["upper_lip"] > 0.5) | (g["groups"]["lower_lip"] > 0.5)
    w = val[sk] * np.where(lips[sk], meta["LIPS"], 1.0)
    st = np.clip(1 - np.abs(lev[sk] - meta["RING"]) / meta["STIFF"], 0, 1)  # hard round the stitch: it must follow the body
    w = w * (1 + 400 * st * st)
    solve = factorized((sp.diags(w) + meta["LAM"] * (L.T @ L) + 1e-9 * sp.identity(m)).tocsc())
    X0 = a["g_neutral"].astype(float)
    head = val & (lev >= meta["RING"])  # the vertices the head's size is read from
    # loose pieces and the skin they follow
    part = a["g_part"].astype(int)
    outer = np.flatnonzero(val & (lev >= meta["RING"]))
    tree = cKDTree(X0[outer])
    pieces = []
    for ids in (2, 3, 4, 5, 6):
        pv = np.flatnonzero((part == ids) & (lev < 0))
        if len(pv):
            pieces.append((pv, outer[tree.query(X0[pv].mean(0), k=ANCHORS)[1]]))
    eye_anchor = [outer[tree.query(p, k=ANCHORS)[1]] for p in a["g_eye_j"].astype(float)]
    _CACHE["ref"] = {"Pref": Pref, "Tref": Tref, "sk": sk, "solve": solve, "w": w, "X0": X0, "head": head, "val": val,
                     "tri": tri, "bar": bar, "pieces": pieces, "eye_anchor": eye_anchor, "meta": meta,
                     "io_scale": float(a["io"][0] / a["io"][1])}
    return _CACHE["ref"]


def _similar(X0, X1):
    """(c0, c1, k): the translation and uniform scale that take points X0 to X1 (no rotation)."""
    c0, c1 = X0.mean(0), X1.mean(0)
    k = float(np.sqrt(((X1 - c1) ** 2).sum() / max(((X0 - c0) ** 2).sum(), 1e-30)))
    return c0, c1, k


def bound(params: dict, toward: float = 1.0) -> dict:
    """GNM's whole head (all its vertices, world frame of the MakeHuman body made from `params`) as that body's own
    head carries it: {"B": (17821, 3), "k": the head's size over the reference head's, "eyes": the two eye joints,
    "P": the body's vertices}. toward < 1 leaves part of GNM's own mean head in (0 = its mean proportions)."""
    key = ("bound", json.dumps(params, sort_keys=True, default=float), round(float(toward), 6))
    if key in _CACHE:
        return _CACHE[key]
    from . import makehuman
    r = _reference()
    a = asset()
    mb = makehuman.body(params)
    P = np.asarray(mb["P"], float)
    val, sk, X0 = r["val"], r["sk"], r["X0"]
    T = (r["bar"][:, :, None] * P[r["tri"]]).sum(1)
    c0, c1, k = _similar(r["Tref"][r["head"]], T[r["head"]])
    rem = np.where(val[:, None], T - (c1 + k * (r["Tref"] - c0)), 0.0)
    D = np.column_stack([r["solve"](r["w"] * rem[sk, j]) for j in range(3)])
    B = c1 + k * (X0 - c0)
    B[sk] += D
    if toward != 1.0:
        B[sk] += (1 - float(toward)) * k * (a["g_mean"].astype(float) * a["g_fade"][:, None])[sk]
    for pv, anc in r["pieces"]:  # eyes, teeth, tongue: rigid with a scale, as the skin beside them went
        a0, a1, ka = _similar(X0[anc], B[anc])
        B[pv] = a1 + ka * (X0[pv] - a0)
    eyes = []
    for p, anc in zip(a["g_eye_j"].astype(float), r["eye_anchor"]):
        a0, a1, ka = _similar(X0[anc], B[anc])
        eyes.append(a1 + ka * (p - a0))
    out = {"B": B, "k": k, "eyes": np.array(eyes), "P": P, "mh": mb}
    if len(_CACHE) > 24:
        for kk in [kk for kk in _CACHE if isinstance(kk, tuple) and kk[0] == "bound"][:4]:
            _CACHE.pop(kk)
    _CACHE[key] = out
    return out


def native(base: dict | None) -> bool:
    """base.head.attach == "native": the head is GNM's own evaluation under ONE similarity (its size in metres x
    base.head.size, a rigid placement on the body's skull pivot), every vertex from the seam ring up; nothing of the
    body's head, no blend above the ring, no style head sliders. The body gives: its height is set so the figure
    stands at the stated stature (base.body.height) under THIS head, and its neck / shoulders are moved to meet GNM's
    ring (`_neck_field`). `attach_report(base)` has the numbers."""
    return applies(base) and (base.get("head") or {}).get("attach") == "native"


def _pivot(params: dict) -> tuple:
    """Where GNM's HEAD JOINT (joint 1: the skull on the spine) lies on the MakeHuman body made from `params`, and the
    size of that body's own head over GNM's template: GNM's template fitted (translation + uniform scale) to the head
    the body carries, above the neck. -> (pivot (3,), k)."""
    from . import base as basemod
    g = basemod._gnm_data()
    r = _reference()
    a = asset()
    bd = bound(params, 1.0)
    m = r["val"] & (a["g_lev"].astype(int) >= r["meta"]["RING"] + 12)  # (the skull and face: not the neck's rings)
    Xg = g["template_vertex_positions"].astype(float) @ _RG.T
    c0, c1, k = _similar(Xg[m], bd["B"][m])
    return c1 + k * (g["template_joint_positions"].astype(float)[1] @ _RG.T - c0), k


def _native_desc(base: dict, hd: dict, params: dict) -> dict:
    """head_desc for attach "native": the head's scale is GNM's (x size), the body's height is solved so the top of
    the head stands at the stated stature, and hd["bound"]["native"] carries the placement."""
    from . import base as basemod
    from . import makehuman
    g = basemod._gnm_data()
    user = base.get("head") or {}
    size = float(user.get("size", 1.0))
    stature = float(params["height"]) if params.get("height") else float(np.asarray(makehuman.body(params)["P"])[:, 2].max())
    # the head's top over its pivot: GNM's evaluation of the identity (what the head will be, but for expression / pose)
    ci = basemod._gnm_coeffs(g["identity_names"], hd.get("identity") or {}, hd.get("seed"), hd.get("spread", 1.0))
    ext = np.asarray(g["skin"], bool) & (np.asarray(g["groups"]["skin_exterior"]) > 0.5)
    Vy = (g["template_vertex_positions"][ext, 1] + np.tensordot(ci, g["vertex_identity_basis"][:, ext, 1], 1)).max()
    Jy = g["template_joint_positions"][1, 1] + float(np.tensordot(ci, g["joint_identity_basis"][:, 1, 1], 1))
    top = size * float(Vy - Jy)
    from . import humanstyle
    bs = humanstyle.active(base, humanstyle.BODY)

    def pivot_height(p):  # the pivot's height over the soles on the body as it will stand (a style's longer legs lift it)
        z = float(_pivot(p)[0][2])
        if bs:
            lift, dz = _style_lift(p, bs, _pivot(p)[0])
            z += float(lift[2]) - dz
        return z
    fit = {**params, "height": round(stature, 6)}
    for _ in range(2):  # (MakeHuman's height is a uniform scale and the sliders are ratios: the pivot's height goes with it)
        fit = {**params, "height": round((stature - top) * float(fit["height"]) / pivot_height(fit), 6)}
    piv, k = _pivot(fit)
    hd = {k_: v for k_, v in hd.items() if k_ not in NATIVE_DROP}
    hd["scale"] = round(size, 9)
    hd["subdivide"] = 0
    hd["bound"] = {"body": fit, "toward": 1.0,
                   "native": {"pivot": [round(float(x), 7) for x in piv], "size": size, "stature": round(stature, 6),
                              "own": round(float(k), 6)}}
    return hd


def _style_lift(params: dict, bs: dict, at) -> tuple:
    """(how the style's body sliders move the point `at` on the MakeHuman body of `params`, the soles' new height)."""
    key = ("lift", json.dumps([params, bs, [round(float(x), 6) for x in at]], sort_keys=True, default=float))
    if key not in _CACHE:
        from . import humanstyle, retopo
        mb = bound(params, 1.0)["mh"]
        J2, girth = humanstyle.body_targets(mb["J"], bs)
        V, _, _, fn, _ = retopo._skeleton_warp(np.asarray(mb["P"], float), mb["J"], {"joints": {k: {"pos": v} for k, v in J2.items()}}, [], girth=girth)
        _CACHE[key] = (fn(np.atleast_2d(np.asarray(at, float)))[0][0] - np.asarray(at, float), float(V[:, 2].min()))
    return _CACHE[key]


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
    mv = np.flatnonzero(free & (dist < NATIVE_RELAX * reach / NATIVE_REACH))
    if len(mv):
        from . import retopo
        deg = np.asarray(A.sum(1)).ravel()
        fade = np.clip((NATIVE_RELAX * reach / NATIVE_REACH - dist[mv]) / (0.3 * NATIVE_RELAX * reach / NATIVE_REACH), 0, 1)[:, None]
        for it in range(NATIVE_RELAX_ITERS):
            if it % 5 == 0:
                N = retopo._vnormals(Y, tris)[mv]
            d = (A[mv] @ Y) / deg[mv, None] - Y[mv]
            Y[mv] += 0.5 * fade * (d - (d * N).sum(1, keepdims=True) * N)
        out = Y[:n_body] - X[:n_body]
    return out


NECK_RINGS = (10, 20)  # rings above the stitch over which the hand-over runs: at the throat, at the nape
NECK_FADE = True  # the head's own shape handed over to the body's through the whole neck (stitch -> chin level)


def neck_fade() -> np.ndarray:
    """Per GNM vertex 0..1: how much of the head's OWN shape (identity, warp, fit, head size) a vertex takes. The
    asset's g_fade reaches 1 seven rings (~2 cm) above the stitch: a head 14% bigger than the body's, or a warp that
    moves the nape, then met the body's neck in a ledge (a collar round the neck's base; Garrett, 2026-10-08). This
    one rises over the neck's whole length (by ring: see NECK_RINGS), never above g_fade."""
    key = ("neck_fade",)
    if key in _CACHE:
        return _CACHE[key]
    from . import base as basemod
    g = basemod._gnm_data()
    a = asset()
    f = a["g_fade"].astype(float)
    Vt = g["template_vertex_positions"].astype(float)
    if not NECK_FADE:
        _CACHE[key] = f
        return f
    # by RING above the stitch (GNM's neck rings climb toward the nape, so a height rule gave the nape no length at
    # all): the hand-over ends NECK_RINGS[0] rings up at the throat (under the chin, which keeps its whole shape) and
    # NECK_RINGS[1] rings up at the nape (the skull's base), in between by how far back a vertex lies (GNM: z forward)
    lev = a["g_lev"].astype(float)
    l0 = float(lev[(f > 0) & (f < 0.1)].min()) if ((f > 0) & (f < 0.1)).any() else float(lev[f > 0].min())
    ring = Vt[(lev >= l0) & (lev <= l0 + 2)]
    zc, zr = float(np.median(ring[:, 2])), max(float(np.ptp(ring[:, 2])) / 2, 1e-6)
    back = np.clip((zc - Vt[:, 2]) / zr * 0.5 + 0.5, 0, 1)
    n = NECK_RINGS[0] + (NECK_RINGS[1] - NECK_RINGS[0]) * back * back * (3 - 2 * back)
    t = np.clip((lev - l0) / n, 0, 1)
    out = np.where(lev >= 0, np.minimum(f, t * t * (3 - 2 * t)), f)
    _CACHE[key] = out
    return out


def hook(V, J, head: dict, R, eye_mid, s: float, mid):
    """Called by base.gnm_head just before it places the head (GNM's frame): everything it made of GNM's template
    (identity, expression, regions, pose, eye size, planes...) is kept as a DIFFERENCE from the template, faded out
    toward the stitch, and laid on the head this body carries. Returns (V, J)."""
    from . import base as basemod
    nat = head["bound"].get("native")
    if nat:  # (headbody) GNM's own evaluation, whole: only moved so its head joint lands on the body's skull pivot
        T = (np.asarray(nat["pivot"], float) - np.asarray(eye_mid, float)) @ R / s - np.asarray(J, float)[1] + mid
        return V + T, np.asarray(J, float) + T
    g = basemod._gnm_data()
    a = asset()
    bd = bound(head["bound"]["body"], float(head["bound"].get("toward", 1.0)))
    Vt = g["template_vertex_positions"].astype(float)
    Jt = g["template_joint_positions"].astype(float)
    shift = mid - 0.5 * (Jt[2] + Jt[3])
    fade = neck_fade()[:, None]
    Vn = mid + (bd["B"] - eye_mid) @ R / s + fade * ((V - Vt) - shift)
    gb = float(head.get("gnm_base", 0.0))
    gr = head.get("gnm_base_rest")
    if gb or gr:  # (faces6 spike) the head's BASE shape from GNM's template instead of the MakeHuman head the body carries,
        # scaled to that head's size, faded to the stitch: the MakeHuman head + dimorphism field added a fixed ~2.7 mm
        # landmark offset to every identity (narrower lower face, flatter cheeks, longer; f6_15)
        base_mh = mid + (bd["B"] - eye_mid) @ R / s
        G = Vt - 0.5 * (Jt[2] + Jt[3])
        w = (fade[:, 0] > 0.5)
        k = float(((base_mh[w] - mid) * G[w]).sum() / max((G[w] ** 2).sum(), 1e-12))
        if gr is None:
            wv = np.full(len(Vn), gb)
        else:   # (gnmcontrols) a REGIONAL base: gnm_base in the face (GNM's hockey mask, where its identity lives),
            # gnm_base_rest outside it (skull, ears, neck: MakeHuman's head where the body needs it), blended over
            # gnm_base_blend metres of the template
            wv = float(gr) + (gb - float(gr)) * face_weight(float(head.get("gnm_base_blend", 0.03)))
        Vn = Vn + (wv[:, None] * fade) * ((mid + k * G) - base_mh)
        ga = float(head.get("gnm_base_age", 0.0))
        age = float(head["bound"]["body"].get("age", 25.0))
        if ga and age > 25.0:   # (gnmcontrols) where GNM's template replaced MakeHuman's head, put back MakeHuman's
            # AGEING (its head at this age minus at 25, both at their eyes): GNM's face structure, MakeHuman's age
            b25 = bound({**head["bound"]["body"], "age": 25.0}, float(head["bound"].get("toward", 1.0)))
            mh25 = mid + (b25["B"] - _eye_mid(b25["mh"])) @ R / s
            Vn = Vn + ga * (wv[:, None] * fade) * (base_mh - mh25)
    if head.get("dim"):  # the sexes' difference a little past MakeHuman's own, on the head only (headfit's fields)
        from . import headfit
        d0 = {**head["dim"], "toward": 0.0, "amount": 1.0}
        dv = headfit.field_vertices(d0) - headfit.field_vertices({**d0, "dimorphism": 0.0})
        Vn = Vn + fade * dv * float(abs(J[2][0] - J[3][0]))
    Jn = np.array(J, float)
    Jn[2:4] = mid + (bd["eyes"] - eye_mid) @ R / s + ((J[2:4] - Jt[2:4]) - shift)
    if head.get("human_style"):  # (humanstyle.py) the style's head sliders, on the same vertices
        from . import humanstyle
        Vn, Jn = humanstyle.head_ops(Vn, Jn, head["human_style"], g, neck_fade(), g["lm68"])
    return Vn, Jn


def face_weight(blend: float = 0.03) -> np.ndarray:
    """Per GNM vertex: 1 in GNM's face (its hockey_mask group), falling smoothly to 0 at `blend` metres outside it."""
    key = ("face_w", round(blend, 5))
    if key not in _CACHE:
        from scipy.spatial import cKDTree
        from . import base as basemod
        g = basemod._gnm_data()
        Vt = g["template_vertex_positions"].astype(float)
        m = np.asarray(g["groups"]["hockey_mask"], float) > 0.5
        d = cKDTree(Vt[m]).query(Vt)[0]
        t = np.clip(1 - d / max(blend, 1e-6), 0, 1)
        _CACHE[key] = np.where(m, 1.0, t * t * (3 - 2 * t))
    return _CACHE[key]


def _eye_mid(mb: dict) -> np.ndarray:
    return np.array(mb["face"]["landmarks"]["eye.L"], float) * [0, 1, 1]


def head_desc(base: dict) -> dict:
    """The head dict base.gnm_head gets: the base's own head keys, the style layer, and what binds it to the body."""
    params = body_params(base)
    hd = {k: v for k, v in (base.get("head") or {}).items() if k not in HEAD_KEYS and k != "source"}
    toward = float((base.get("head") or {}).get("toward", 1.0))
    bd = bound(params, toward)
    st = base.get("style") or {}
    if st:  # as base.head_of: the style layer multiplies the head's own settings (the head's SIZE is the body's here)
        hd = {**hd, "eyes": float(hd.get("eyes", 1.0)) * float(st.get("eyes", 1.0)),
              "simplify": float(hd.get("simplify", 0.0)) + float(st.get("simplify", 0.0)),
              **({"shape": {**st["shape"], **(hd.get("shape") or {})}} if st.get("shape") else {}),
              **({"simplify_keep": st["simplify_keep"]} if "simplify_keep" in st and "simplify_keep" not in hd else {})}
    user = base.get("head") or {}
    if hd.get("seed") is not None or user.get("features"):
        # (headfit.py) the seed without its OWN age / sex / weight (the body gives the head those), and the features
        # (nose, jaw, lips... as moves of the landmarks) solved in GNM's identity components + a small warp
        from . import headfit
        pseudo = {"body": {"source": "makehuman", **params},
                  "head": {**{k: v for k, v in hd.items() if k in ("seed", "spread", "identity")}, "source": "gnm",
                           "follow_body": True, **({"features": user["features"]} if user.get("features") else {})}}
        f = headfit.follow(pseudo, pseudo["head"])
        hd["identity"] = f["identity"]
        if user.get("features"):
            # the features' warp first, then the head's own stored warps (fit_outline appends there): replacing them
            # dropped every outline fit on a human() with features (Tess, 2026-10-09: widths moved 0.0 mm in 3 rounds)
            own = hd.get("warp")
            own = [] if not own else (own if isinstance(own, list) else [own])
            hd["warp"] = [f["warp"], *own] if own else f["warp"]
        hd.pop("seed", None)  # (it is in the identity now)
    if user.get("attach") == "native":  # (headbody) GNM's head as GNM makes it; the body is fitted to it
        return _native_desc(base, hd, params)
    if user.get("attach") not in (None, "body"):
        raise ValueError('base.head.attach: "native" (GNM\'s head untouched at its own size, the body fitted) or "body" (default)')
    from . import humanstyle
    hs = humanstyle.active(base, humanstyle.HEAD + ("exaggerate",))
    if hs.get("exaggerate") is not None and hd.get("identity"):  # the same person, further from the mean
        hd["identity"] = {k: round(float(v) * hs["exaggerate"], 4) for k, v in hd["identity"].items()}
    hs.pop("exaggerate", None)
    if hs:
        hd["human_style"] = hs
    hd["scale"] = round(bd["k"] * _reference()["io_scale"], 9)
    dim = float(user.get("dimorphism", DIMORPHISM))
    sex = float(np.clip(params.get("sex", 1.0), 0, 1))
    if dim and abs(sex - 0.5) > 1e-6 and float(params.get("age", 25)) >= 12:
        from . import makehuman
        hd["dim"] = {"age": round(float(makehuman.table_age(params)), 3), "sex": sex, "weight": 0.5,
                     "dimorphism": round(dim * float(np.clip((float(params.get("age", 25)) - 12) / 6, 0, 1)), 4)}
    hd["subdivide"] = 0
    hd["bound"] = {"body": params, "toward": toward, **({"head_size": hs["head_size"]} if hs.get("head_size") else {})}
    return hd


def head_template(base: dict) -> dict:
    """The head in the body's own (template) pose: base.gnm_head's dict."""
    from . import base as basemod
    hd = head_desc(base)
    key = ("head_t", json.dumps(hd, sort_keys=True, default=float))
    if key not in _CACHE:
        mb = bound(hd["bound"]["body"], hd["bound"]["toward"])["mh"]
        _CACHE[key] = basemod.gnm_head(hd, _eye_mid(mb), np.array([0.0, 0.0, 1.0]))
    return _CACHE[key]


def _tkey(base: dict) -> str:
    from . import humanstyle
    return json.dumps([head_desc(base), humanstyle.active(base, humanstyle.BODY)], sort_keys=True, default=float)


def template(base: dict) -> dict:
    """The one mesh shaped for this base, as a body template (retopo.load_template's keys): P, L, S, J, face, chin_z,
    bones, rig; plus "fid" (each vertex's index in the asset's full topology, what carries uv and skin weights),
    "head_rows" (its head vertices: rows of head_template(base)["verts"]) and "mh_rows"."""
    hd = head_desc(base)
    key = ("tpl", _tkey(base))
    if key in _CACHE:
        return _CACHE[key]
    from . import base as basemod
    a = asset()
    g = basemod._gnm_data()
    bd = bound(hd["bound"]["body"], hd["bound"]["toward"])
    mb, P = bd["mh"], bd["P"]
    ht = head_template(base)
    n0, n_ring, n_all, nb0 = (int(x) for x in a["bridge"])
    # the head's vertices: GNM's skin (no sock) as gnm_head numbers it (after a lip zip), those above the stitch
    skin_ids = np.flatnonzero(g["skin"])
    if ht.get("skin_index") is not None:
        si = np.asarray(ht["skin_index"])
        gid = np.full(int(si.max()) + 1, -1)
        gid[si[si >= 0]] = skin_ids[si >= 0]
    else:
        gid = skin_ids
    keep_h = a["g2f"][gid] >= 0
    hrow = np.flatnonzero(keep_h)
    mh_rows = np.flatnonzero(a["m2f"] >= 0)
    br = np.arange(n0, n_all)
    Vb = (a["bind_w"][br].astype(float)[:, :, None] * P[a["bind_tri"][br]]).sum(1) + a["offset"][br]
    V = np.r_[P[mh_rows] + a["offset"][a["m2f"][mh_rows]], Vb, ht["verts"][hrow] + a["offset"][a["g2f"][gid[hrow]]]]
    fid = np.r_[a["m2f"][mh_rows], br, a["g2f"][gid[hrow]]]
    # faces: the body's and the bridge's from the asset (by asset index), the head's from gnm_head (it may have zipped)
    f2d = np.full(n_all, -1)
    f2d[fid] = np.arange(len(fid))
    F = a["faces"]
    mh_f = F[(a["mh_id"][F] >= 0).all(1)]
    faces = [list(q) for q in f2d[mh_f]] + [list(q) for q in f2d[F[nb0:int(a["n_raw_f"])]]]
    h2d = np.full(len(ht["verts"]), -1)
    h2d[hrow] = len(mh_rows) + len(br) + np.arange(len(hrow))
    for f in ht["faces"]:
        q = h2d[f]
        if (q >= 0).all():
            faces.append([int(v) for v in q])
    assert min(min(f) for f in faces) >= 0
    seal_field = None
    sealed = float(hd.get("lip_seal") or 0) >= 0.5 and hd.get("mouth_gap") is None
    if not sealed and ht.get("skin_index") is None and float(hd.get("lip_seal") or 0) < 0.5:
        # a mouth CLOSED BY GNM (its expression: blockin_lips / mouth_gap 0): the same field-only seam as a seal's,
        # lighter (gnm_atlas.md "## gnmdetail2"). As GNM shapes it, the closed contact is a 42-deg V between two coarse
        # rings (~3.5 mm apart) with the inner rolls crossing behind it (the upper 6.5 mm below the lower): the
        # field read a 2.5 mm forward-facing WALL there, a dark line 1.8 mm above the contact and a pale band under it
        # (Tess gd_T12L4), never the photo's slit
        from . import blockin_lips
        try:
            closed = float(np.max(blockin_lips.contact_gaps(ht, None, 1.0))) < CLOSED_GAP * 1000
        except (ValueError, IndexError, KeyError):
            closed = False
        sealed = closed
        seal_v = CLOSED_SEAL_V if closed else None
    else:
        seal_v = None
    if sealed and ht.get("skin_index") is None:
        # (faceslide / base._sealed_field) the closed mouth's field: the rolls inside the contact ring left out, the
        # contact rows overlapped
        from . import faceslide
        R = faceslide._lip_rings()
        row_of = np.full(len(a["g2f"]), -1)
        row_of[gid[hrow]] = len(mh_rows) + len(br) + np.arange(len(hrow))
        kc = R["contact"]
        inside = np.concatenate(R["rings"][:kc + 1])
        C = R["rings"][kc]
        rows = lambda ids: row_of[np.asarray(ids, int)][row_of[np.asarray(ids, int)] >= 0]  # noqa: E731
        seal_field = {"drop": rows(inside), "up": rows(C[R["upper"][C]]), "lo": rows(C[~R["upper"][C]]),
                      "outer": [(rows(r[R["upper"][r]]), rows(r[~R["upper"][r]])) for r in R["rings"][kc + 1:kc + 4]]}
        if seal_v is not None:
            seal_field["v"] = list(seal_v)
    nat = hd["bound"].get("native")
    if nat:  # (headbody) the body's neck and shoulders meet GNM's ring; the head's vertices are not touched
        nb = len(mh_rows) + len(br)
        rest = np.r_[V[:nb], bd["B"][gid[hrow]]]
        ring = nb + np.flatnonzero(a["g_lev"].astype(int)[gid[hrow]] == _reference()["meta"]["RING"])
        reach = NATIVE_REACH * float(P[:, 2].max()) / 1.7
        V[:nb] += _neck_field(rest, faces, nb, V[nb:] - rest[nb:], ring, reach)
    V, fid, faces, loop_rows = _with_loops(V, fid, faces, gid[hrow], len(mh_rows) + len(br))
    if len(loop_rows) and ht.get("loop_offsets") is not None:  # (faceslide.py) the sliders on the loops' vertices
        V[loop_rows] += ht["loop_offsets"]
    from . import humanstyle
    from . import headfit  # noqa: F401  (the lines below reach it through the package)
    Jb, bones, chin_z, face, chin_lm, carry_fn = mb["J"], mb["bones"], mb["chin_z"], mb["face"], float(ht["lm68"][8][2]), None
    chin_mh_ = float(P[__import__("hifipushie").headfit.table()["lm68"][8], 2])
    if nat:  # the head's bones and landmarks are the HEAD's: MakeHuman's (in its own head) taken about the pivot
        from . import makehuman
        piv, kk = np.asarray(nat["pivot"], float), float(nat["size"]) / float(nat["own"])
        sk = makehuman.skeleton()["bones"]
        kids, todo = {"head"}, ["head"]
        while todo:
            p_ = todo.pop()
            for n_, b_ in sk.items():
                if b_.get("parent") == p_ and n_ not in kids:
                    kids.add(n_)
                    todo.append(n_)
        bones = {n_: ((piv + kk * (h_ - piv), piv + kk * (t_ - piv)) if n_ in kids else (h_, t_)) for n_, (h_, t_) in bones.items()}
        Jb = {**Jb, "head": piv + kk * (np.asarray(Jb["head"], float) - piv)}
        face = {"landmarks": {"eye.L": [float(x) for x in max(ht["eyes"], key=lambda e_: e_[0])]}}
        chin_z = chin_mh_ = chin_lm
    bs = humanstyle.active(base, humanstyle.BODY)
    if bs:  # (humanstyle.py) proportions: joints move and girths scale, and the mesh goes with them
        from . import retopo
        J2, girth = humanstyle.body_targets(Jb, bs)
        V0, head_j = V, Jb["head"]
        V, _, _, carry_fn, _ = retopo._skeleton_warp(V, Jb, {"joints": {k: {"pos": v} for k, v in J2.items()}}, [], girth=girth)
        mv = lambda X: carry_fn(np.atleast_2d(np.asarray(X, float)))[0]  # noqa: E731
        mvh = mv
        if nat:  # (headbody) the head RIDES the styled body, rigid (the pivot's move); the body's neck meets it again
            nb = len(mh_rows) + len(br)
            tr = mv(nat["pivot"])[0] - np.asarray(nat["pivot"], float)
            carry_fn = lambda X, tr=tr: (np.atleast_2d(np.asarray(X, float)) + tr,)  # noqa: E731
            mvh = lambda X: carry_fn(X)[0]  # noqa: E731
            D = (V0[nb:] + tr) - V[nb:]
            V[:nb] += _neck_field(V, faces, nb, D, ring, reach)
            V[nb:] = V0[nb:] + tr
        dz = float(V[:, 2].min())
        V = V - [0, 0, dz]
        Jb = {k: np.asarray(v, float) - [0, 0, dz] for k, v in J2.items()}
        if nat:
            Jb["head"] = mvh(head_j)[0] - [0, 0, dz]
        bones = {n: ((mvh if nat and n in kids else mv)(h_)[0] - [0, 0, dz], (mvh if nat and n in kids else mv)(t_)[0] - [0, 0, dz])
                 for n, (h_, t_) in bones.items()}
        chin_z = float(mvh([0, 0, chin_z])[0][2] - dz)
        face = {"landmarks": {"eye.L": (mvh(face["landmarks"]["eye.L"])[0] - [0, 0, dz]).tolist()}}
        chin_lm = float(mvh(ht["lm68"][8])[0][2] - dz)
        chin_mh_ = float(mvh(P[__import__("hifipushie").headfit.table()["lm68"][8]])[0][2] - dz) if not nat else chin_lm
        _CACHE[("style_carry", key[1])] = (carry_fn, dz)
    out = {"name": "human", "P": V, "L": np.array([v for f in faces for v in f]), "S": np.array([len(f) for f in faces]),
           "J": Jb, "bones": bones, "rig": mb["rig"], "chin_z": chin_z, "face": face, "styled": bool(bs),
           "fid": fid, "head_rows": hrow, "loop_rows": loop_rows, "seal_field": seal_field, "n_body": len(mh_rows) + len(br), "n_mh": len(mh_rows),
           # the chin: the head's own landmark (clothes stay under it), and the body's vertex the old path measures at
           "chin_lm": chin_lm, "chin_mh": chin_mh_}
    _CACHE[key] = out
    return out


def _with_loops(V, fid, faces, head_gid, h0):
    """The lids' extra edge loops (gnmloops.py) cut into the fused mesh: each new vertex the mean of its parents
    (appended after every other vertex; asset ids after the asset's own), each cut face's first child in its place,
    the others appended. Old vertices and their order are untouched."""
    from . import gnmloops
    a = asset()
    par = gnmloops.plan()["parents"]
    row = np.full(gnmloops.N_RAW + len(par), -1)
    row[np.asarray(head_gid, int)] = h0 + np.arange(len(head_gid))
    rp = row[par]
    if not gnmloops.ENABLED or (rp < 0).any():  # (a lip zip or a cut that dropped one of the lid's vertices: no loops)
        return V, fid, faces, np.zeros(0, int)
    n = len(V)
    row[gnmloops.N_RAW:] = n + np.arange(len(par))
    V = np.r_[V, V[rp].mean(1)]
    fid = np.r_[fid, int(a["n_raw_v"]) + np.arange(len(par))]
    faces, _, _ = gnmloops._cut_faces(faces, row)
    return V, fid, faces, n + np.arange(len(par))


def _carried(ht: dict, mv, dz: float = 0.0) -> dict:
    """A head dict moved by a point map (the skeleton warp's): vertices, landmarks, eyes, plane, and the rotation and
    eye midpoint face shapes carry their deltas with."""
    from scipy.spatial import cKDTree

    from . import base as basemod
    from . import retopo
    sh = np.array([0.0, 0.0, dz])
    W = mv(ht["verts"]) - sh
    A0, A1 = ht["verts"] - ht["verts"].mean(0), W - W.mean(0)
    U, _, Vt = np.linalg.svd(A0.T @ A1)
    Rp = (U @ np.diag([1, 1, np.sign(np.linalg.det(U @ Vt))]) @ Vt).T
    N, h = basemod._normals_and_h(W, ht["faces"])
    cut, pn, band = ht["plane"]
    carry = dict(ht["carry"])
    carry["R"] = Rp @ carry["R"]
    carry["eye_mid"] = mv(carry["eye_mid"])[0] - sh
    k = float(np.sqrt((A1 ** 2).sum() / max((A0 ** 2).sum(), 1e-30)))
    out = dict(ht)
    out.update(verts=W, normals=N, h=h, hmax=float(h.max()), tree=cKDTree(W), eyes=[mv(e)[0] - sh for e in ht["eyes"]],
               eye_r=float(ht["eye_r"]) * k, forward=Rp @ ht["forward"], lm68=mv(ht["lm68"]) - sh,
               plane=(mv(cut)[0] - sh, Rp @ pn, band), carry=carry)
    if ht.get("gnm_world") is not None:  # (gnmnative) GNM's loose pieces (eyeballs, teeth, tongue) ride the same map
        out["gnm_world"] = mv(ht["gnm_world"]) - sh
    if ht.get("eye_gnm"):
        eg = ht["eye_gnm"]
        out["eye_gnm"] = {**{kk: (vv * k if isinstance(vv, float) and kk != "pupil" else vv) for kk, vv in eg.items()},
                          "axes": [Rp @ a for a in eg["axes"]],
                          "per_eye": [{kk: (Rp @ vv if kk == "axis" else vv if kk == "pupil" else vv * k) for kk, vv in q.items()}
                                      for q in eg["per_eye"]]}
    del retopo
    return out


def head_rest(base: dict) -> dict:
    """The head as the TEMPLATE has it (head_template, carried by the style's body sliders if any)."""
    tpl = template(base)
    ht = head_template(base)
    if not tpl.get("styled"):
        return ht
    key = ("head_rest", _tkey(base))
    if key not in _CACHE:
        fn, dz = _CACHE[("style_carry", _tkey(base))]
        _CACHE[key] = _carried(ht, lambda X: fn(np.atleast_2d(np.asarray(X, float)))[0], dz)
    return _CACHE[key]


def head(s: dict, base: dict) -> dict:
    """The head's dict for everything that asks base.head_of (landmarks, eyes, mouth, face shapes), in the pose the
    spec's joints give the body: the template-pose head carried by the same skeleton warp as the body's vertices."""
    from . import retopo
    tpl = template(base)
    ht = head_rest(base)
    used = {}
    for k in tpl["J"]:
        for n in (k, retopo._model_name(k)):
            if n in s["joints"]:
                used[k] = [round(float(x), 6) for x in s["joints"][n]["pos"]]
                break
    rest = {k: [round(float(x), 6) for x in v] for k, v in tpl["J"].items()}
    posed = any(np.linalg.norm(np.array(used[k]) - np.array(rest[k])) > 2e-5 for k in used)
    key = ("head_p", json.dumps([head_desc(base), used if posed else None, base.get("girth"), (base.get("style") or {}).get("human")],
                                sort_keys=True, default=float))
    if key in _CACHE:
        return _CACHE[key]
    out = dict(ht)
    out["one_mesh"] = True
    out["room"] = True
    if posed or base.get("girth"):
        from scipy.spatial import cKDTree
        girth = dict(base.get("girth") or {})
        for j, gv in list(girth.items()):
            if j.endswith(".L"):
                girth.setdefault(j[:-2] + ".R", gv)
        _, _, _, apply, _ = retopo._skeleton_warp(tpl["P"], tpl["J"], s, [], girth=girth)
        mv = lambda X: apply(np.atleast_2d(np.asarray(X, float)))[0]  # noqa: E731
        out = _carried(ht, mv)
        out["one_mesh"] = True
        out["room"] = True
    # what face shapes multiply GNM's deltas by: 0 at the stitch .. 1 on the head, x a style's head size
    out["carry"] = {**out["carry"], "fade": asset()["g_fade"].astype(float) * float(head_desc(base)["bound"].get("head_size", 1.0))}
    _CACHE[key] = out
    return out


def seam_ring(tpl: dict) -> np.ndarray:
    """The seam ring's rows in the one mesh's template, in order round the neck from the front centre (110 vertices:
    GNM's neck ring 13, the lowest ring of GNM's topology in the mesh; the body's bridge hangs from it)."""
    a = asset()
    row = np.full(int(np.max(tpl["fid"])) + 1, -1)
    row[np.asarray(tpl["fid"], int)] = np.arange(len(tpl["fid"]))
    return row[a["loop_a"].astype(int)]


def attach_report(base: dict) -> dict:
    """How the head sits on the body: {"native", "size" (the head over GNM's own evaluation), "head_height",
    "stature", "heads_tall", "eyes_apart", "eyeball_r" (m), "neck": {"head": GNM's girth at the seam ring, "body": the
    body's own there, "moved": the largest move of a body vertex to meet it}, "ignored": [keys with no effect],
    "text"}."""
    from . import base as basemod
    g = basemod._gnm_data()
    hd = head_desc(base)
    tpl = template(base)
    ht = head_rest(base)
    a = asset()
    nat = hd["bound"].get("native")
    W = np.asarray(ht["gnm_world"], float)
    skin = np.asarray(g["skin"], bool) & (np.asarray(g["groups"]["skin_exterior"]) > 0.5)
    lev = a["g_lev"].astype(int)
    ci = basemod._gnm_coeffs(g["identity_names"], hd.get("identity") or {}, hd.get("seed"), hd.get("spread", 1.0))
    Vg = (g["template_vertex_positions"] + np.tensordot(ci, g["vertex_identity_basis"], 1)).astype(float)
    m = skin & (lev >= _reference()["meta"]["RING"] + 12)
    size = float(np.sqrt(((W[m] - W[m].mean(0)) ** 2).sum() / ((Vg[m] - Vg[m].mean(0)) ** 2).sum()))
    P = np.asarray(tpl["P"], float)
    stature = float(P[:, 2].max() - P[:, 2].min())
    hh = float(W[skin][:, 2].max() - ht["lm68"][8][2])
    ring = seam_ring(tpl)
    girth = lambda X: float(np.linalg.norm(X - np.roll(X, -1, 0), axis=1).sum())  # noqa: E731
    bd = bound(hd["bound"]["body"], float(hd["bound"].get("toward", 1.0)))
    gid = a["gnm_id"].astype(int)[a["loop_a"].astype(int)]
    out = {"native": bool(nat), "size": size, "head_height": hh, "stature": stature, "heads_tall": stature / hh,
           "eyes_apart": float(np.linalg.norm(np.asarray(ht["eyes"][0]) - np.asarray(ht["eyes"][1]))), "eyeball_r": float(ht["eye_r"]),
           "neck": {"head": girth(P[ring]), "body": girth(bd["B"][gid])}, "ignored": []}
    if nat:
        user = base.get("head") or {}
        from . import humanstyle
        out["ignored"] = [f"base.head.{k}" for k in (*NATIVE_DROP, "dimorphism", "toward") if user.get(k) not in (None, 0, 0.0) and not (k == "gnm_base" and float(user[k]) == 1.0)] \
            + [f"base.style.human.{k}" for k in humanstyle.active(base, humanstyle.HEAD + ("exaggerate",))]
        mh_rows = np.flatnonzero(a["m2f"] >= 0)
        out["body_height"] = float(hd["bound"]["body"]["height"])
        out["own_head"] = float(nat["own"])
    t = [f"head: {'GNM native' if nat else 'carried by the body'}, {size:.3f} x GNM's own size; head height {hh * 1000:.0f} mm, eyes "
         f"{out['eyes_apart'] * 1000:.1f} mm apart, eyeball r {out['eyeball_r'] * 1000:.1f} mm (GNM 14.6)",
         f"figure: stature {stature:.3f} m = {out['heads_tall']:.2f} heads tall (measured adults ~7.5; MakeHuman's own bodies ~8.0)",
         f"neck at the seam ring: the head's girth {out['neck']['head'] * 1000:.0f} mm, the body's own {out['neck']['body'] * 1000:.0f} mm "
         f"({100 * (out['neck']['head'] / out['neck']['body'] - 1):+.0f} %)"
         + (": the body's neck and shoulders were moved to the head's" if nat else "")]
    if nat and abs(out["neck"]["head"] / out["neck"]["body"] - 1) > 0.12:
        t.append("  NOTE: head and body disagree about the neck by more than 12 %: a lighter / heavier body (base.body weight, "
                 "muscle) or a different head would meet with less reshaping")
    if nat and not 6.8 <= out["heads_tall"] <= 8.3:
        t.append(f"  NOTE: {out['heads_tall']:.1f} heads tall is outside what adults measure (6.8 .. 8.3): check base.body.height / age")
    if out["ignored"]:
        t.append("  ignored on a native head (they reshape or resize GNM's head): " + ", ".join(out["ignored"]))
    out["text"] = "\n".join(t)
    return out


def weights(tpl: dict) -> tuple:
    """The template's skin weights over MakeHuman's bones: (bone names, (n, 8) bone indices, (n, 8) weights)."""
    a = asset()
    return [str(b) for b in a["bones"]], a["w_idx"][tpl["fid"]].astype(int), a["w"][tpl["fid"]].astype(float)
