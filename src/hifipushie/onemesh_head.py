"""The head of the one mesh: the hook into gnm_head, face weights, the head's description and template, the
head carried to a pose, the seam ring. Part of the one mesh (onemesh.py has the overview)."""
from __future__ import annotations

import json

import numpy as np

from . import onemesh
from .onemesh import _reference, asset, body_params
from .onemesh_native import _native_desc, _neck_field, _neck_follow, neck_fade

def hook(V, J, head: dict, R, eye_mid, s: float, mid):
    """Called by base_gnm_head.gnm_head just before it places the head (GNM's frame): everything it made of GNM's template
    (identity, expression, regions, pose, eye size, planes...) is kept as a DIFFERENCE from the template, faded out
    toward the stitch, and laid on the head this body carries. Returns (V, J)."""
    from . import base_identity
    nat = head["bound"].get("native")
    if nat:  # (headbody) GNM's own evaluation, whole: only moved so its head joint lands on the body's skull pivot
        T = (np.asarray(nat["pivot"], float) - np.asarray(eye_mid, float)) @ R / s - np.asarray(J, float)[1] + mid
        return V + T, np.asarray(J, float) + T
    g = base_identity._gnm_data()
    a = asset()
    bd = onemesh.bound(head["bound"]["body"], float(head["bound"].get("toward", 1.0)))
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
            b25 = onemesh.bound({**head["bound"]["body"], "age": 25.0}, float(head["bound"].get("toward", 1.0)))
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
    if key not in onemesh._CACHE:
        from scipy.spatial import cKDTree
        from . import base_identity
        g = base_identity._gnm_data()
        Vt = g["template_vertex_positions"].astype(float)
        m = np.asarray(g["groups"]["hockey_mask"], float) > 0.5
        d = cKDTree(Vt[m]).query(Vt)[0]
        t = np.clip(1 - d / max(blend, 1e-6), 0, 1)
        onemesh._CACHE[key] = np.where(m, 1.0, t * t * (3 - 2 * t))
    return onemesh._CACHE[key]


def _eye_mid(mb: dict) -> np.ndarray:
    return np.array(mb["face"]["landmarks"]["eye.L"], float) * [0, 1, 1]


def head_desc(base: dict) -> dict:
    """The head dict base_gnm_head.gnm_head gets: the base's own head keys, the style layer, and what binds it to the body."""
    params = body_params(base)
    hd = {k: v for k, v in (base.get("head") or {}).items() if k not in onemesh.HEAD_KEYS and k != "source"}
    toward = float((base.get("head") or {}).get("toward", 1.0))
    bd = onemesh.bound(params, toward)
    st = base.get("style") or {}
    if st:  # as base_measures.head_of: the style layer multiplies the head's own settings (the head's SIZE is the body's here)
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
    dim = float(user.get("dimorphism", onemesh.DIMORPHISM))
    sex = float(np.clip(params.get("sex", 1.0), 0, 1))
    if dim and abs(sex - 0.5) > 1e-6 and float(params.get("age", 25)) >= 12:
        from . import makehuman
        hd["dim"] = {"age": round(float(makehuman.table_age(params)), 3), "sex": sex, "weight": 0.5,
                     "dimorphism": round(dim * float(np.clip((float(params.get("age", 25)) - 12) / 6, 0, 1)), 4)}
    hd["subdivide"] = 0
    hd["bound"] = {"body": params, "toward": toward, **({"head_size": hs["head_size"]} if hs.get("head_size") else {})}
    return hd


def head_template(base: dict) -> dict:
    """The head in the body's own (template) pose: base_gnm_head.gnm_head's dict."""
    from . import base_gnm_head
    hd = head_desc(base)
    key = ("head_t", json.dumps(hd, sort_keys=True, default=float))
    if key not in onemesh._CACHE:
        mb = onemesh.bound(hd["bound"]["body"], hd["bound"]["toward"])["mh"]
        onemesh._CACHE[key] = base_gnm_head.gnm_head(hd, _eye_mid(mb), np.array([0.0, 0.0, 1.0]))
    return onemesh._CACHE[key]


def _tkey(base: dict) -> str:
    from . import humanstyle
    return json.dumps([head_desc(base), humanstyle.active(base, humanstyle.BODY)], sort_keys=True, default=float)


def template(base: dict) -> dict:
    """The one mesh shaped for this base, as a body template (retopo.load_template's keys): P, L, S, J, face, chin_z,
    bones, rig; plus "fid" (each vertex's index in the asset's full topology, what carries uv and skin weights),
    "head_rows" (its head vertices: rows of head_template(base)["verts"]) and "mh_rows"."""
    hd = head_desc(base)
    key = ("tpl", _tkey(base))
    if key in onemesh._CACHE:
        return onemesh._CACHE[key]
    from . import base_identity
    a = asset()
    g = base_identity._gnm_data()
    bd = onemesh.bound(hd["bound"]["body"], hd["bound"]["toward"])
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
            closed = float(np.max(blockin_lips.contact_gaps(ht, None, 1.0))) < onemesh.CLOSED_GAP * 1000
        except (ValueError, IndexError, KeyError):
            closed = False
        sealed = closed
        seal_v = onemesh.CLOSED_SEAL_V if closed else None
    else:
        seal_v = None
    if sealed and ht.get("skin_index") is None:
        # (faceslide / base_surface._sealed_field) the closed mouth's field: the rolls inside the contact ring left out, the
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
        reach = onemesh.NATIVE_REACH * float(P[:, 2].max()) / 1.7
        freach = onemesh.FOLLOW_REACH * float(P[:, 2].max()) / 1.7
        V[:nb] += _neck_field(rest, faces, nb, V[nb:] - rest[nb:], ring, reach)  # (a start; then laid on the bib)
        V[:nb] = _neck_follow(rest, V, faces, nb, ring, freach, np.asarray(ht["gnm_world"], float))
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
        piv0 = np.asarray(nat.get("own_pivot", nat["pivot"]), float)  # (where the body's own skull stood)
        sk = makehuman.skeleton()["bones"]
        kids, todo = {"head"}, ["head"]
        while todo:
            p_ = todo.pop()
            for n_, b_ in sk.items():
                if b_.get("parent") == p_ and n_ not in kids:
                    kids.add(n_)
                    todo.append(n_)
        bones = {n_: ((piv + kk * (h_ - piv0), piv + kk * (t_ - piv0)) if n_ in kids else (h_, t_)) for n_, (h_, t_) in bones.items()}
        Jb = {**Jb, "head": piv + kk * (np.asarray(Jb["head"], float) - piv0)}
        face = {"landmarks": {"eye.L": [float(x) for x in max(ht["eyes"], key=lambda e_: e_[0])]}}
        chin_z = chin_mh_ = chin_lm
    bs = humanstyle.active(base, humanstyle.BODY)
    if bs:  # (humanstyle.py) proportions: joints move and girths scale, and the mesh goes with them
        from . import retopo_warp
        J2, girth = humanstyle.body_targets(Jb, bs)
        V0, head_j = V, Jb["head"]
        V, _, _, carry_fn, _ = retopo_warp._skeleton_warp(V, Jb, {"joints": {k: {"pos": v} for k, v in J2.items()}}, [], girth=girth)
        mv = lambda X: carry_fn(np.atleast_2d(np.asarray(X, float)))[0]  # noqa: E731
        mvh = mv
        if nat:  # (headbody) the head RIDES the styled body, rigid (the pivot's move); the body's neck meets it again
            nb = len(mh_rows) + len(br)
            tr = mv(nat["pivot"])[0] - np.asarray(nat["pivot"], float)
            carry_fn = lambda X, tr=tr: (np.atleast_2d(np.asarray(X, float)) + tr,)  # noqa: E731
            mvh = lambda X: carry_fn(X)[0]  # noqa: E731
            restw = V.copy()  # (the styled body, the head where that body would carry it)
            restw[:nb] = mv(rest[:nb])
            restw[nb:len(rest)] = mv(rest[nb:])
            V[nb:] = V0[nb:] + tr
            V[:nb] = _neck_follow(restw, V, faces, nb, ring, freach, np.asarray(ht["gnm_world"], float) + tr)
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
        onemesh._CACHE[("style_carry", key[1])] = (carry_fn, dz)
    out = {"name": "human", "P": V, "L": np.array([v for f in faces for v in f]), "S": np.array([len(f) for f in faces]),
           "J": Jb, "bones": bones, "rig": mb["rig"], "chin_z": chin_z, "face": face, "styled": bool(bs),
           "fid": fid, "head_rows": hrow, "loop_rows": loop_rows, "seal_field": seal_field, "n_body": len(mh_rows) + len(br), "n_mh": len(mh_rows),
           # the chin: the head's own landmark (clothes stay under it), and the body's vertex the old path measures at
           "chin_lm": chin_lm, "chin_mh": chin_mh_}
    onemesh._CACHE[key] = out
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

    from . import base_imls
    from . import retopo
    sh = np.array([0.0, 0.0, dz])
    W = mv(ht["verts"]) - sh
    A0, A1 = ht["verts"] - ht["verts"].mean(0), W - W.mean(0)
    U, _, Vt = np.linalg.svd(A0.T @ A1)
    Rp = (U @ np.diag([1, 1, np.sign(np.linalg.det(U @ Vt))]) @ Vt).T
    N, h = base_imls._normals_and_h(W, ht["faces"])
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
    if key not in onemesh._CACHE:
        fn, dz = onemesh._CACHE[("style_carry", _tkey(base))]
        onemesh._CACHE[key] = _carried(ht, lambda X: fn(np.atleast_2d(np.asarray(X, float)))[0], dz)
    return onemesh._CACHE[key]


def head(s: dict, base: dict) -> dict:
    """The head's dict for everything that asks base_measures.head_of (landmarks, eyes, mouth, face shapes), in the pose the
    spec's joints give the body: the template-pose head carried by the same skeleton warp as the body's vertices."""
    from . import retopo
    from . import retopo_warp
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
    if key in onemesh._CACHE:
        return onemesh._CACHE[key]
    out = dict(ht)
    out["one_mesh"] = True
    out["room"] = True
    if posed or base.get("girth"):
        from scipy.spatial import cKDTree
        girth = dict(base.get("girth") or {})
        for j, gv in list(girth.items()):
            if j.endswith(".L"):
                girth.setdefault(j[:-2] + ".R", gv)
        _, _, _, apply, _ = retopo_warp._skeleton_warp(tpl["P"], tpl["J"], s, [], girth=girth)
        mv = lambda X: apply(np.atleast_2d(np.asarray(X, float)))[0]  # noqa: E731
        out = _carried(ht, mv)
        out["one_mesh"] = True
        out["room"] = True
    # what face shapes multiply GNM's deltas by: 0 at the stitch .. 1 on the head, x a style's head size
    out["carry"] = {**out["carry"], "fade": asset()["g_fade"].astype(float) * float(head_desc(base)["bound"].get("head_size", 1.0))}
    onemesh._CACHE[key] = out
    return out


def seam_ring(tpl: dict) -> np.ndarray:
    """The seam ring's rows in the one mesh's template, in order round the neck from the front centre (110 vertices:
    GNM's neck ring 13, the lowest ring of GNM's topology in the mesh; the body's bridge hangs from it)."""
    a = asset()
    row = np.full(int(np.max(tpl["fid"])) + 1, -1)
    row[np.asarray(tpl["fid"], int)] = np.arange(len(tpl["fid"]))
    return row[a["loop_a"].astype(int)]
