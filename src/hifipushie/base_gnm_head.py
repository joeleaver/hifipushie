"""gnm_head: a GNM head built for a spec (identity, expression, shape edits, eyes and mouth), ready to graft. Part of base (base.py has the overview)."""
from __future__ import annotations

import numpy as np
from scipy.spatial import cKDTree

from . import base
from . import retopo
from .base_gnm_parts import _gnm_pieces, _zip_lips, gnm_eyes, lip_close_delta
from .base_head_shape import _chin, _ears, _hood, _jawline, _lean, _nose_tip, _planes, _round_tip, _sstep
from .base_identity import _gnm_coeffs, _gnm_data, _local_smooth, fit_identity, pose_expression, regional_identity
from .base_imls import _catmull_clark, _normals_and_h

def gnm_head(head: dict, eye_mid: np.ndarray, up: np.ndarray) -> dict:
    """Google GNM's head skin, posed for the base: identity/expression applied (head["identity"] {name: value},
    head["seed"] for a random identity), eyes scaled about their centres (head["eyes"], e.g. 1.45: a stylised look),
    the head narrowed across (head["narrow"]), then scaled (head["scale"], default 1.4: the template's head height)
    and placed with its eye midpoint on eye_mid, its up along `up`. Returns the skin IMLS arrays, eye centres and
    radius, and the graft plane (point, normal, band) in world space."""
    g = _gnm_data()
    ident = dict(fit_identity(head["fit"])) if head.get("fit") else {}
    ident.update(head.get("identity") or {})  # given components win over fitted ones
    ci = _gnm_coeffs(g["identity_names"], ident, head.get("seed"), head.get("spread", 1.0))
    local_sliders = head.get("sliders")
    if local_sliders and head.get("slider_mode") == "coupled":  # (faceatlas.py) the sliders as WHOLE-MODEL moves: each
        # the conditional mean of the identity given its attribute's change (within the head's sex), named holds kept;
        # only what GNM can't express stays a local morph
        from . import faceatlas
        dc, local_sliders = faceatlas.slider_identity(local_sliders, head.get("slider_hold") or ())
        ci = ci.copy()
        ci[faceatlas._gnm()["comps"]] += dc
    from . import lidfold  # (eyedetail) the fold's overhang: the share GNM can express through the identity
    dfold = lidfold.identity_change(head)
    if dfold is not None:
        from . import faceatlas
        ci = ci.copy()
        ci[faceatlas._gnm()["comps"]] += dfold
    ce = _gnm_coeffs(g["expression_names"], head.get("expression"))
    V = g["template_vertex_positions"] + np.tensordot(ci, g["vertex_identity_basis"], 1) + \
        np.tensordot(ce, g["expression_basis"], 1)
    J = g["template_joint_positions"] + np.tensordot(ci, g["joint_identity_basis"], 1)
    V, J = V.astype(float), J.astype(float)
    Vg = V.copy()  # GNM's OWN evaluation (template + identity + expression, every component from the same
    # coefficients): what its loose pieces (eyeballs, teeth, tongue) are re-set from at the end (_gnm_pieces)
    En = np.tensordot(ce, g["expression_basis"], 1).astype(float)  # (the expression's share of it)
    slide = None
    if head.get("shape"):  # (faceslide.py) the older shape ops still work, but say what replaces them
        from . import faceslide
        for msg in faceslide.deprecated(head["shape"]):
            if msg not in base._WARNED:
                base._WARNED.add(msg)
                import warnings
                warnings.warn(msg, DeprecationWarning, stacklevel=2)
    if head.get("sliders"):  # (faceslide.py) the face sliders: morph targets on GNM's template + the lids' loops,
        # added like an identity component (everything after rides on them)
        from . import faceslide, gnmloops
        slide = faceslide.delta(local_sliders, V)  # (V: the crease on this head's own fold)
        if slide is not None:
            V = V + slide[:gnmloops.N_RAW]
            jd = faceslide.joint_delta(local_sliders)  # (eye_setback: the eye joints go back with the balls)
            if jd is not None:
                J = J + jd
            par = gnmloops.plan()["parents"]
            slide = slide[gnmloops.N_RAW:] - slide[par].mean(1)  # what the loops' vertices add over their parents'
    if head.get("field"):  # (headfit.py) MakeHuman's head of an age / sex / weight, as a displacement of the vertices
        from . import headfit
        V = V + headfit.field_vertices(head["field"]) * float(abs(J[2][0] - J[3][0]))
    if head.get("warp"):  # (headfit.py) what the identity space couldn't make of the body's head, as a smooth warp;
        # a list = several warps, each with its own reach, applied in order (humanfit.fit_outline adds a shorter one)
        for wp in (head["warp"] if isinstance(head["warp"], list) else [head["warp"]]):
            P_, C_ = np.asarray(wp["at"], float), np.asarray(wp["coef"], float)
            for a in range(0, len(V), 4096):
                d2 = ((V[a:a + 4096, None, :] - P_[None, :, :]) ** 2).sum(-1)
                V[a:a + 4096] += np.exp(-d2 / (2 * wp["sigma"] ** 2)) @ C_
    V = V + regional_identity(head.get("regions"))
    if head.get("pose"):  # landmark moves: a smile, lids, brows (least change of the regional expressions)
        dp = pose_expression(head["pose"], V, float(head.get("scale", 1.4)))
        V, Vg, En = V + dp, Vg + dp, En + dp
    if head.get("mouth_gap") is not None:  # the lips parted by this much (m, world; 0 = closed): the least change of
        # the lower-face expression components that sets the inner lips' distance (slightly parted lips left
        # flecks at the corners where the slit ran out)
        lmv = lambda X, i: sum(float(w) * X[int(v)] for v, w in zip(g["lm68"][i][0::2], g["lm68"][i][1::2]))
        lower = [i for i, nm in enumerate(g["expression_names"]) if str(nm).startswith("lower_face")][:40]
        gap = lambda X: float(np.linalg.norm(lmv(X, 62) - lmv(X, 66)))
        g0 = gap(V)
        a = np.array([gap(V + 1e-3 * g["expression_basis"][i]) - g0 for i in lower]) / 1e-3
        want = float(head["mouth_gap"]) / float(head.get("scale", 1.4))
        for _ in range(3):  # (the gap is a norm: a few linearised steps)
            c = a * (want - gap(V)) / max(float(a @ a), 1e-12)
            dp = np.tensordot(c, g["expression_basis"][lower], 1)
            V, Vg, En = V + dp, Vg + dp, En + dp
            a = np.array([gap(V + 1e-3 * g["expression_basis"][i]) - gap(V) for i in lower]) / 1e-3
    if head.get("lid_fold"):  # (projskin) the upper lid's fold in MESH space: GNM's own lid rings re-sectioned (platform,
        # slit, roll), local by construction; a blink unfolds it (gnm_fold.mesh_delta)
        from . import gnm_fold
        V = V + gnm_fold.mesh_delta(V - En, En, head["lid_fold"])
    k_eye = float(head.get("eyes", 1.0))
    r_eye = [float(np.median(np.linalg.norm(V[m] - J[2 + i], axis=1))) for i, m in enumerate(g["eye"])]
    esc = np.ones(len(V))  # how much the eye scaling magnifies each vertex's neighbourhood (face shapes carry deltas)
    if k_eye != 1.0:  # the eyes and the orbits round them scaled about each eye centre, fading out over ~2 radii
        for j in (2, 3):
            d = np.linalg.norm(V - J[j], axis=1)
            f = 1 + (k_eye - 1) * np.exp(-(d / (2.2 * r_eye[j - 2])) ** 2)
            V = J[j] + (V - J[j]) * f[:, None]
            esc *= f
    mid = 0.5 * (J[2] + J[3])
    V[:, 0] = mid[0] + (V[:, 0] - mid[0]) * float(head.get("narrow", 1.0))
    J[:, 0] = mid[0] + (J[:, 0] - mid[0]) * float(head.get("narrow", 1.0))
    shape = head.get("shape") or {}
    if float(shape.get("planes", 2.0)) != 2.0:  # front/side planes meeting at a tighter corner (temple, cheekbone)
        V, J[2:4] = _planes(V, J[2:4], float(shape["planes"]), g, float(shape.get("planes_hold_eyes", 0.8)),
                             float(shape.get("planes_keep_features", 1.0)))
    R = np.array([[1.0, 0, 0], [0, 0, -1.0], [0, 1.0, 0]])  # GNM: Y up, facing +Z -> Z up, facing -Y
    up = up / np.linalg.norm(up)
    R = retopo._rot_between(np.array([0, 0, 1.0]), up) @ R
    s = float(head.get("scale", 1.4))
    if head.get("bound"):  # (onemesh.py) the head its body carries, with all of the above laid on it and faded out
        # toward the stitch at the neck
        from . import onemesh
        V, J = onemesh.hook(V, J, head, R, np.asarray(eye_mid, float), s, mid)
        r_eye = [r * float(head["bound"].get("head_size", 1.0)) for r in r_eye]  # (a style's bigger head: its eyeballs too)
    if head.get("lip_seal") and head.get("mouth_gap") is None:  # (faceslide.seal_delta) the rest mouth closed: the
        # lips in contact along their width, by this share (0..1). On the head as it is now (after the body's hook,
        # which carries GNM's template lips at their own gap) but WITHOUT its expression, so a jaw or mouth expression
        # (and the face shapes, GNM's deltas by index) still open it. An explicit mouth_gap wins (it parts them)
        from . import faceslide
        E = np.tensordot(ce, g["expression_basis"], 1)
        if head.get("bound"):
            from . import onemesh as _om
            E = E * _om.head_fade(head)[:, None]
        V = V + faceslide.seal_delta(V - E, float(np.clip(head["lip_seal"], 0.0, 1.0)))
    elif head.get("lip_close") and head.get("mouth_gap") is None:  # GNM's own closing (lip_close_delta), where the
        # seal goes: after the body's hook (it carries the template lips at their own gap) and on the head WITHOUT
        # its expression, so a picture's smile or an open-mouth expression on top still opens it (a closing solved
        # INTO the expression, the lips step, clears lip_close: not doubled)
        E = np.tensordot(ce, g["expression_basis"], 1)
        if head.get("bound"):
            from . import onemesh as _om
            E = E * _om.head_fade(head)[:, None]
        dp = lip_close_delta(V - E, g, float(head.get("scale", 1.4)))
        V, Vg, En = V + dp, Vg + dp, En + dp
    pf = None
    if head.get("bound"):  # (the one mesh hands the head's own shape over to the body through the neck: neck_fade)
        from . import onemesh as _om
        pf = _om.head_fade(head)
    V = _gnm_pieces(V, Vg, g, En, pf)

    def place(X):
        return eye_mid + s * (X - mid) @ R.T
    # the graft plane through the neck's axis, tilted GNM_TILT down at the front: level, it ran into the jaw under the
    # chin (the chin sits ~6 mm over GNM_CUT) while the back must stay above the bib's open edge
    cut_y = base.GNM_CUT
    if head.get("plane_follows_chin"):  # (headfit.py) a longer or shorter jaw takes the plane with it: fixed, a low
        # chin sat in the graft band
        chin = sum(float(w) * V[int(v)] for v, w in zip(g["lm68"][8][0::2], g["lm68"][8][1::2]))
        cut_y = float(np.clip(base.GNM_CUT + (chin[1] - base.GNM_CHIN), 0.155, 0.21))
    cut = place(np.array([mid[0], cut_y, J[0][2]]))
    ta = np.radians(base.GNM_TILT)
    pn = R @ np.array([0.0, np.cos(ta), np.sin(ta)])
    lm = place(np.array([sum(float(w) * V[int(v)] for v, w in zip(row[0::2], row[1::2])) for row in g["lm68"]]))
    skin = g["skin"]
    Q = g["quads"][skin[g["quads"]].all(1)]
    remap = -np.ones(len(V), int)
    remap[np.flatnonzero(skin)] = np.arange(skin.sum())
    W = place(V[skin])
    faces = [list(q) for q in remap[Q]]
    if float(head.get("simplify", 0.0)) > 0:  # simpler planes (a feature-animation face): small forms smoothed away,
        # the lid rims, lips and nostrils kept (their weight fades to 0 within ~1.5 cm of those landmarks)
        E = retopo.edges(np.array([v for f in faces for v in f]), np.array([len(f) for f in faces]))
        deg = np.bincount(E.ravel(), minlength=len(W))
        keep = [lm[i] for i in (37, 38, 40, 41, 43, 44, 46, 47, 48, 51, 54, 57, 62, 66)
                + ((31, 33, 35) if not shape.get("nostrils") else ())]
        dk = np.min([np.linalg.norm(W - p, axis=1) for p in keep], axis=0)
        k0, k1 = head.get("simplify_keep", [0.006, 0.015])  # kept within k0 of those landmarks, fading over k1
        wv = np.clip((dk - float(k0) * s) / (float(k1) * s), 0, 1)
        # and the neck left as it is near the graft plane (its open edge moved under the smoothing: a ridge and
        # flecks round the neck's base, where the body's tube must meet it)
        wv = (wv * np.clip(((W - cut) @ pn - 0.02) / 0.03, 0, 1))[:, None]
        for _ in range(int(round(12 * float(head["simplify"])))):
            for lam in (0.5, -0.53):
                W = W + lam * wv * retopo._lap(W, E, deg)
    pushes = list(shape.get("push") or []) + list(shape.get("push_more") or [])  # push_more: a model's own bumps
    # added to its style sheet's (a model's "push" replaces the sheet's list: the shape dict merges key by key)
    def _pushes(W, lm, pushes):  # soft landmark-addressed bumps along the head's normals, mirrored: a buccal hollow under
        # the cheekbone, a proud cheekbone, a jaw corner. [{"lm": [ids] (their mean), "offset": [x, y, z] (m, world),
        # "radius": m, "amount": m}], Gaussian falloff (GNM's region groups have hard edges: pushed, they left steps)
        Nw = retopo._vnormals(W, np.array([(f[0], f[j], f[j + 1]) for f in faces for j in range(1, len(f) - 1)]))
        if head.get("bound") and len(W) == int(skin.sum()):  # (onemesh.py) its lips' inner rolls and lids'
            # insides are kept as GNM's own surfaces: pushed along THEIR normals (into the mouth, up, down) a corner
            # push turned the rolls out through the lips' corners. They take the nearest outer skin's normal
            ext = np.asarray(g["groups"]["skin_exterior"])[skin] > 0.5
            if (~ext).any() and ext.any():
                Nw = Nw.copy()
                Nw[~ext] = Nw[ext][cKDTree(W[ext]).query(W[~ext])[1]]
        mx = float(eye_mid[0])
        # a push with "dir" ([x, y, z] world, e.g. [0, 1, 0] = back) moves everything that way instead: a muzzle
        # pushed back along the normals opened the mouth (the lips' seam faces up and down)
        near = cKDTree(W).query(lm, k=24)[1]
        Nl = Nw[near].mean(1)  # the landmarks' normals smoothed (a lip seam vertex's own normal faces up or down)
        Nl /= np.linalg.norm(Nl, axis=1, keepdims=True)
        DW, DL = np.zeros_like(W), np.zeros_like(lm)
        for b in pushes:
            c = np.mean([lm[int(i)] for i in b["lm"]], axis=0) + np.asarray(b.get("offset", [0, 0, 0]), float)
            d = np.asarray(b["dir"], float) / np.linalg.norm(b["dir"]) if b.get("dir") is not None else None
            for side, cc in enumerate([c, np.array([2 * mx - c[0], c[1], c[2]])] if abs(c[0] - mx) > 1e-4 else [c]):
                fw = float(b["amount"]) * np.exp(-(np.linalg.norm(W - cc, axis=1) / float(b["radius"])) ** 2)
                fl = float(b["amount"]) * np.exp(-(np.linalg.norm(lm - cc, axis=1) / float(b["radius"])) ** 2)
                dd = None if d is None else (d * [-1, 1, 1] if side else d)  # the mirrored bump's dir mirrors too
                DW += fw[:, None] * (Nw if dd is None else dd)
                DL += fl[:, None] * (Nl if dd is None else dd)
        W = W + DW
        lm = lm + DL  # the landmarks ride along (lip outlines, the mouth fill and lid rims are placed from them)
        return W, lm
    if pushes:
        W, lm = _pushes(W, lm, pushes)
    if shape.get("under_eye") or shape.get("nostrils"):  # designed reductions: the under-eye crease filled, the
        # nostril holes closed to a shallow dent (a stylised nose shows no openings from the front)
        E = retopo.edges(np.array([v for f in faces for v in f]), np.array([len(f) for f in faces]))
        deg = np.bincount(E.ravel(), minlength=len(W))
        gs = {k: v[skin] for k, v in g["groups"].items()}
        if shape.get("under_eye"):
            dl = np.min([np.linalg.norm(W - lm[i], axis=1) for i in range(36, 48)], axis=0)
            infra = np.clip(gs["left_infraorbital_region"] + gs["right_infraorbital_region"]
                            + 0.5 * (gs["left_orbital_region"] + gs["right_orbital_region"])
                            + 0.7 * (gs["left_zygomatic_region"] + gs["right_zygomatic_region"]), 0, 1)
            for _ in range(6):  # feathered: the regions' hard edges left a step where the smoothing stopped
                infra = infra + 0.5 * retopo._lap(infra[:, None], E, deg)[:, 0]
            wv = infra * _sstep((dl - 0.0025 * s) / (0.004 * s)) * (1 - np.clip(gs["nose_region"], 0, 1))
            W = _local_smooth(W, E, deg, wv, 12 * float(shape["under_eye"]))
        if shape.get("nostrils"):
            dn = np.min([np.linalg.norm(W - lm[i], axis=1) for i in (31, 32, 33, 34, 35)], axis=0)
            wv = 1 - _sstep((dn - 0.006 * s) / (0.006 * s))
            W = _local_smooth(W, E, deg, wv, 12 * float(shape["nostrils"]))
    late = list(shape.get("push_late") or [])
    if shape.get("hollow"):  # hollow cheeks: a dent under the cheekbone, between the jaw contour and the mouth's
        # corner (the buccal hollow of a lean face), mirrored. m | {"amount", "radius", "at": [jaw lm, mouth lm], "share"}
        hc = shape["hollow"] if isinstance(shape["hollow"], dict) else {"amount": shape["hollow"]}
        a_, b_ = hc.get("at", [2, 48])
        sh_ = float(hc.get("share", 0.3))
        ids_ = [a_] * int(round(10 * (1 - sh_))) + [b_] * int(round(10 * sh_))
        c0 = np.mean([lm[int(i)] for i in ids_], axis=0)
        # the mean of two landmarks across a convex cheek lies INSIDE it: the dent is centred where a ray from it,
        # out at 37 deg from straight ahead toward its side, meets the cheek (straight ahead it met the lips' corner,
        # the nearest surface point was the side of the face)
        sx_ = np.sign(c0[0] - float(eye_mid[0])) or 1.0
        dr_ = np.array([0.6 * sx_, -0.8, 0.0])
        rel = W - c0
        t_ = rel @ dr_
        pp = np.linalg.norm(rel - t_[:, None] * dr_, axis=1)
        okr = (t_ > 0) & (pp < 0.004 * s)
        off_ = (W[okr][np.argmin(t_[okr])] - c0).tolist() if okr.any() else (W[np.argmin(np.linalg.norm(rel, axis=1))] - c0).tolist()
        late.append({"lm": ids_, "offset": off_, "radius": float(hc.get("radius", base.HOLLOW_RADIUS)) * s / 1.12,
                     "amount": -float(hc["amount"])})
    if shape.get("jaw_angle"):  # a bony jaw corner: the gonial angle (between lm 3 and 4) stands out, crisp, and the
        # soft under-jaw from the corner toward the chin is tucked up behind the jaw line, so the line reads as an edge.
        # m | {"amount", "tuck", "radius", "tuck_radius"}
        ja = shape["jaw_angle"] if isinstance(shape["jaw_angle"], dict) else {"amount": shape["jaw_angle"]}
        amt = float(ja["amount"])
        # GNM's jaw-contour landmarks lie on the cheek's side: the jaw's angle itself is ~33 mm behind lm 3 and 20 mm
        # lower (where the jaw's underside meets the neck on a section at lm 3's x; measured on Garrett's head)
        cg = lm[3] + np.array([0.0, 0.033, -0.020]) * s / 1.12
        late.append({"lm": [3], "offset": (W[np.argmin(np.linalg.norm(W - cg, axis=1))] - lm[3]).tolist(),
                     "radius": float(ja.get("radius", base.JAW_RADIUS)) * s / 1.12, "amount": amt})
        tk = float(ja.get("tuck", 1.2 * amt))
        if tk:
            ct = 0.5 * (lm[5] + lm[6])
            below = ct + np.array([0.0, 0.010, -0.010]) * s / 1.12  # under the jaw line and behind it (the head faces -y)
            # snapped onto the surface in its own x (the nearest vertex overall slid along the jaw toward the chin, and
            # the mirrored dent, which isn't snapped, came out at half the depth)
            band = np.abs(W[:, 0] - below[0]) < 0.002 * s
            cand = W[band] if band.any() else W
            late.append({"lm": [5, 6], "offset": (cand[np.argmin(np.linalg.norm(cand - below, axis=1))] - ct).tolist(),
                         "radius": float(ja.get("tuck_radius", base.JAW_TUCK_RADIUS)) * s / 1.12, "amount": -tk})
    if late:  # bumps after the under-eye/nostril smoothing (which erased pushes in its region: a
        # lifted upper cheek under the lower lid, filling the socket hollow that shaded as a dark ring)
        W, lm = _pushes(W, lm, late)
    if shape.get("jawline"):
        W, lm = _jawline(W, lm, np.asarray(g["groups"]["ears"])[skin] > 0.5, shape["jawline"], float(eye_mid[0]), s, faces)
    if shape.get("lean"):
        W, lm = _lean(W, lm, np.asarray(g["groups"]["ears"])[skin] > 0.5, shape["lean"], float(eye_mid[0]), s, faces)
    if shape.get("hood"):
        W, lm = _hood(W, lm, shape["hood"], np.asarray(g["groups"]["skin_exterior"])[skin] > 0.5)
    from . import headage
    if headage.wanted(shape):  # age as soft-tissue ops: nasolabial, prejowl, lid_fold, cheek_flat, lips_thin
        W, lm = headage.apply(W, lm, shape, faces, {k_: np.asarray(v_)[skin] for k_, v_ in g["groups"].items()
                                                     if len(np.asarray(v_)) == len(skin)},
                              float(eye_mid[0]), s, np.asarray(g["groups"]["skin_exterior"])[skin] > 0.5)
    if shape.get("nose_tip"):
        W, lm = _nose_tip(W, lm, shape["nose_tip"], s)
        if isinstance(shape["nose_tip"], dict) and shape["nose_tip"].get("round"):
            W, lm = _round_tip(W, lm, shape["nose_tip"]["round"], s, faces)
    if shape.get("chin"):
        W, lm = _chin(W, lm, shape["chin"], float(eye_mid[0]), s)
    if shape.get("ears"):
        W = _ears(W, np.asarray(g["groups"]["ears"])[skin] > 0.5, shape["ears"], float(eye_mid[0]), s)
    lipm = (np.asarray(g["groups"]["upper_lip_region"]) + np.asarray(g["groups"]["lower_lip_region"]) > 0.5)[skin]
    # how far the head's own shape ops (pushes, simplify, under_eye / nostrils, jawline ...) moved the lips off GNM's
    # surface: past MOUTH_PUSHED GNM's teeth no longer fit behind them (mouth_mode's fallback)
    mouth_off = float(np.linalg.norm(W[lipm] - place(V[skin])[lipm], axis=1).max()) if len(W) == int(skin.sum()) else 0.0
    skin_index, zipped = None, 0
    if head.get("mouth_gap") is not None and float(head["mouth_gap"]) < 0.0015 and head.get("zip_lips", True):
        W, faces, skin_index, zipped = _zip_lips(W, faces, 0.5 * (lm[62] + lm[66]))
    # what face shapes need to carry GNM expression deltas onto the head (faceshapes_gnm.GnmFace): the posed GNM vertices
    # in its own frame, the placement, the skin's polygons before subdividing (deltas subdivide like positions)
    carry = {"V": V, "esc": esc, "R": R, "s": s, "mid": mid, "eye_mid": np.asarray(eye_mid, float),
             "narrow": float(head.get("narrow", 1.0)), "skin": skin, "faces": [list(f) for f in faces],
             "skin_index": skin_index, "subdivide": int(head.get("subdivide", 1))}
    for _ in range(int(head.get("subdivide", 1))):
        W, faces = _catmull_clark(W, faces)
    N, h = _normals_and_h(W, faces)
    h = h * float(head.get("smooth", 1.0))
    # THE EYEBALLS. Default (gnmnative, 2026-10-12): GNM's OWN two-sphere eye, read off its eye vertices as they came
    # through everything above with the skin (identity, the eye scaling, the body's head, a style): the scleral sphere
    # where GNM puts it, its radius x the head's scale, limbus / cornea / pupil from the identity's eye components and
    # the pupil expression (gnm_eyes). GNM's lids, blink and eye expressions are shaped round that ball (its paper:
    # the scleral radius is HELD "maintaining eyelid compatibility"). No seat search, no radius of ours.
    back = -(R @ np.array([0, 0, 1.0]))
    eg = gnm_eyes(V, g)
    eye_gnm = None
    if head.get("eye_radius"):  # the OVERRIDE (blockin2; every head made 2026-10-10 .. 12 has it): an ABSOLUTE eyeball
        # radius (m, world; an adult's ~0.012) x head.eyes, seated by a search: the centre moves back along the face
        # from GNM's joint until the sphere clears every lid landmark by EYE_SEAT. The lids then stand ~1.1 mm off the
        # ball at the margin (they are GNM's, shaped on its 14.6 mm sphere).
        r_ball = float(head["eye_radius"]) * k_eye
        eyes = []
        for j in (2, 3):
            c = place(J[j])
            rim = lm[42:48] if c[0] > 0 else lm[36:42]
            lo, hi = -0.02, 0.02
            for _ in range(40):  # the smallest move back where every rim point is EYE_SEAT outside the sphere
                m = 0.5 * (lo + hi)
                if np.linalg.norm(rim - (c + m * back), axis=1).min() >= r_ball + base.EYE_SEAT:
                    hi = m
                else:
                    lo = m
            eyes.append(c + hi * back)
    else:
        eyes = [place(q["c"]) for q in eg]
        r_ball = s * float(np.mean([q["r"] for q in eg]))
        mean = lambda k: s * float(np.mean([q[k] for q in eg]))  # noqa: E731
        eye_gnm = {"limbus": mean("limbus"), "cornea_r": mean("cornea_r"), "apex": mean("apex"), "iris_r": mean("iris_r"),
                   "iris_depth": mean("iris_depth"), "pupil_r": mean("pupil_r"),
                   "pupil": float(np.mean([q["pupil"] for q in eg])),
                   "axes": [R @ q["axis"] for q in eg], "per_eye": [{k: (s * v if k not in ("axis", "c", "pupil") else v)
                                                                      for k, v in q.items() if k != "c"} for q in eg]}
    rim = lm[42:48]
    return {"verts": W, "faces": faces, "normals": N, "h": h, "hmax": float(h.max()), "tree": cKDTree(W),
            "eyes": eyes, "eye_r": r_ball, "forward": -back, "eye_gnm": eye_gnm, "mouth_off": mouth_off,
            "teeth_place": head.get("teeth_place"),  # (r37) rigid tooth-row placement, see gnm_mouth
            # every GNM vertex (skin, sock, eyeballs, teeth, tongue) as placed: one evaluation of GNM's bases
            "gnm_world": place(V),
            "eye_open": float(np.mean(rim[[1, 2], 2]) - np.mean(rim[[4, 5], 2])),  # the opening's height
            "lm68": lm, "skin_index": skin_index, "lips_zipped": zipped, "carry": carry,
            "plane": (cut, pn, s * base.GNM_BAND),
            # (faceslide.py) the sliders' own move of the lids' loop vertices over their parents' mean (world)
            "loop_offsets": None if slide is None else s * (slide * [float(head.get("narrow", 1.0)), 1, 1]) @ R.T}
