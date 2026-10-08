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
VERSION = 8  # bump when the one mesh's built field changes (store's build key, base.surface's key; old paths keep theirs)
DIMORPHISM = 0.8  # as headfit's: under a seed's individuality MakeHuman's own difference reads as neither sex
ANCHORS = 48  # skin vertices a loose piece (eye, teeth, tongue) follows
HEAD_KEYS = ("toward", "dimorphism", "features", "follow_body", "like", "neck")  # head keys handled here (the
# rest are base.gnm_head's)


def applies(base: dict | None) -> bool:
    return bool(base) and ((base.get("body") or {}).get("source") == "human")


def asset() -> dict:
    if "asset" not in _CACHE:
        z = np.load(Path(__file__).with_name("human_mesh.npz"))
        _CACHE["asset"] = {k: z[k] for k in z.files}
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


def hook(V, J, head: dict, R, eye_mid, s: float, mid):
    """Called by base.gnm_head just before it places the head (GNM's frame): everything it made of GNM's template
    (identity, expression, regions, pose, eye size, planes...) is kept as a DIFFERENCE from the template, faded out
    toward the stitch, and laid on the head this body carries. Returns (V, J)."""
    from . import base as basemod
    g = basemod._gnm_data()
    a = asset()
    bd = bound(head["bound"]["body"], float(head["bound"].get("toward", 1.0)))
    Vt = g["template_vertex_positions"].astype(float)
    Jt = g["template_joint_positions"].astype(float)
    shift = mid - 0.5 * (Jt[2] + Jt[3])
    fade = a["g_fade"].astype(float)[:, None]
    Vn = mid + (bd["B"] - eye_mid) @ R / s + fade * ((V - Vt) - shift)
    if head.get("dim"):  # the sexes' difference a little past MakeHuman's own, on the head only (headfit's fields)
        from . import headfit
        d0 = {**head["dim"], "toward": 0.0, "amount": 1.0}
        dv = headfit.field_vertices(d0) - headfit.field_vertices({**d0, "dimorphism": 0.0})
        Vn = Vn + fade * dv * float(abs(J[2][0] - J[3][0]))
    Jn = np.array(J, float)
    Jn[2:4] = mid + (bd["eyes"] - eye_mid) @ R / s + ((J[2:4] - Jt[2:4]) - shift)
    if head.get("human_style"):  # (humanstyle.py) the style's head sliders, on the same vertices
        from . import humanstyle
        Vn, Jn = humanstyle.head_ops(Vn, Jn, head["human_style"], g, a["g_fade"].astype(float), g["lm68"])
    return Vn, Jn


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
            hd["warp"] = f["warp"]
        hd.pop("seed", None)  # (it is in the identity now)
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
    faces = [list(q) for q in f2d[mh_f]] + [list(q) for q in f2d[F[nb0:]]]
    h2d = np.full(len(ht["verts"]), -1)
    h2d[hrow] = len(mh_rows) + len(br) + np.arange(len(hrow))
    for f in ht["faces"]:
        q = h2d[f]
        if (q >= 0).all():
            faces.append([int(v) for v in q])
    assert min(min(f) for f in faces) >= 0
    from . import humanstyle
    Jb, bones, chin_z, face, chin_lm, carry_fn = mb["J"], mb["bones"], mb["chin_z"], mb["face"], float(ht["lm68"][8][2]), None
    chin_mh_ = float(P[__import__("hifipushie").headfit.table()["lm68"][8], 2])
    bs = humanstyle.active(base, humanstyle.BODY)
    if bs:  # (humanstyle.py) proportions: joints move and girths scale, and the mesh goes with them
        from . import retopo
        J2, girth = humanstyle.body_targets(Jb, bs)
        V, _, _, carry_fn, _ = retopo._skeleton_warp(V, Jb, {"joints": {k: {"pos": v} for k, v in J2.items()}}, [], girth=girth)
        mv = lambda X: carry_fn(np.atleast_2d(np.asarray(X, float)))[0]  # noqa: E731
        dz = float(V[:, 2].min())
        V = V - [0, 0, dz]
        Jb = {k: np.asarray(v, float) - [0, 0, dz] for k, v in J2.items()}
        bones = {n: (mv(h_)[0] - [0, 0, dz], mv(t_)[0] - [0, 0, dz]) for n, (h_, t_) in bones.items()}
        chin_z = float(mv([0, 0, chin_z])[0][2] - dz)
        face = {"landmarks": {"eye.L": (mv(face["landmarks"]["eye.L"])[0] - [0, 0, dz]).tolist()}}
        chin_lm = float(mv(ht["lm68"][8])[0][2] - dz)
        chin_mh_ = float(mv(P[__import__("hifipushie").headfit.table()["lm68"][8]])[0][2] - dz)
        _CACHE[("style_carry", key[1])] = (carry_fn, dz)
    out = {"name": "human", "P": V, "L": np.array([v for f in faces for v in f]), "S": np.array([len(f) for f in faces]),
           "J": Jb, "bones": bones, "rig": mb["rig"], "chin_z": chin_z, "face": face, "styled": bool(bs),
           "fid": fid, "head_rows": hrow, "n_body": len(mh_rows) + len(br), "n_mh": len(mh_rows),
           # the chin: the head's own landmark (clothes stay under it), and the body's vertex the old path measures at
           "chin_lm": chin_lm, "chin_mh": chin_mh_}
    _CACHE[key] = out
    return out


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


def weights(tpl: dict) -> tuple:
    """The template's skin weights over MakeHuman's bones: (bone names, (n, 8) bone indices, (n, 8) weights)."""
    a = asset()
    return [str(b) for b in a["bones"]], a["w_idx"][tpl["fid"]].astype(int), a["w"][tpl["fid"]].astype(float)
