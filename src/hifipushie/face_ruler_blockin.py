"""A block-in model against its reference pictures: the expression set and its prior, and the model's head. Part of the face ruler (face_ruler.py has the overview)."""
from __future__ import annotations

import numpy as np

from .face_ruler import _C, _gnm

EXPR_SET = ("compress_face", "surprise", "squint", "lips_roll_in", "corners_down", "happy", "mouth_left", "mouth_right")


EXPR_SAY = {"compress_face": "frown / brows drawn down and together", "surprise": "brows raised (jaw dropped)", "squint": "squint",
            "lips_roll_in": "lips pressed", "corners_down": "mouth corners down", "happy": "smile (corners pulled)",
            "mouth_left": "mouth pulled to its left", "mouth_right": "mouth pulled to its right"}


# the reads an expression may explain: the INTERIOR ones. TRIED with the outlines in (solvereads): per-view expression then
# ate the profile (compress +0.9, surprise -0.9 on the 72 deg view: chin 10 mm back, the head 3.5 mm rms from the truth
# after three calls against 1.8 without the term): a silhouette cannot tell an expression from a shape.
EXPR_TYPES = ("landmark", "lid", "lip", "dense", "mp")


# (readmix, 2026-10-14) expression="lower": each picture's LOWER-FACE expression free (the mouth: a slight smile, lips pressed /
# rolled, corners down, mouth to one side), the upper face's classes PINNED at neutral (EXPR_PIN): solvereads' and groundtruth's
# per-view runs let squint / surprise / compress take the misfit ("finds 0.18 of 0.30 plus spurious surprise / squint");
# a side view's expression pinned too (its reads are the outline, which the expression never explains). MediaPipe's
# blendshape scores are NOT a gate: a slight smile (GNM's happy x0.3, dressed) scores mouthSmile 0.024, neutral 0.001
# (spikes/readmix/smilecal.py: on clay the score stays under 0.11 up to happy 0.3; one head scored 0 at 0.6)
EXPR_LOWER = ("happy", "lips_roll_in", "corners_down", "mouth_left", "mouth_right")


EXPR_PIN = 0.02


def expr_prior_of(expr, views) -> dict | None:
    if expr != "lower":
        return None
    out = {}
    for v in views:
        side = v["kind"] == "profile"
        out[v["kind"]] = {n: (0.0, EXPR_PIN) for n in EXPR_SET if side or n not in EXPR_LOWER}
    return out


EXPR_SD = 0.35              # prior sd of one expression coefficient (1 = GNM's full prototype of that expression class)


def expression_protos(names=EXPR_SET) -> np.ndarray:
    """(n, 383) GNM expression coefficients of the sampler's class prototypes (gnm_sampler.prototype)."""
    key = ("xproto", tuple(names))
    if key not in _C:
        from . import gnm_sampler
        _C[key] = np.array([gnm_sampler.prototype(n) for n in names], float)
    return _C[key]


def expression_coeffs(amounts: dict) -> dict:
    """{expression class: amount} -> base.head.expression's {GNM expression comp: value}."""
    from . import base as basemod
    names = [str(n) for n in basemod._gnm_data()["expression_names"]]
    e = sum(float(a) * expression_protos((k,))[0] for k, a in amounts.items())
    return {n: round(float(x), 5) for n, x in zip(names, np.atleast_1d(e)) if abs(x) >= 1e-4}


def _expr_fields(names) -> np.ndarray:
    """(n, V, 3): each prototype's move of GNM's vertices (raw GNM frame, m)."""
    key = ("xfield", tuple(names))
    if key not in _C:
        from . import gnm_controls
        EB = gnm_controls.gnm()["EB"]
        P = expression_protos(names)
        _C[key] = np.array([np.tensordot(e.astype(np.float32), EB[:len(e)], 1) for e in P], np.float32)
    return _C[key]


def model_head(spec: dict, c=None, kappa=None, expr=None) -> dict:
    """A block-in model (the one human mesh, GNM's head on it) as the ruler's model: the whole mesh for the picture's
    mask, the head's vertices with their move per GNM identity comp (as humanfit._silhouette: the head's carry and the
    stitch's fade), the measures of its GNM identity (gnm_mm, GNM's own mm). c: another identity (170) on the same model."""
    import copy
    from . import base as basemod, blockin as bi, gnm_mm, headfit, humanfit, likeness, onemesh
    if c is not None:
        spec = copy.deepcopy(spec)
        bi.set_identity(spec, c)
    st = humanfit.state(spec["base"])
    mesh = likeness.model_mesh_from_state(st)
    tpl, carry = st["tpl"], st["head"]["carry"]
    P = np.asarray(tpl["P"], float)
    gid = np.asarray(onemesh.asset()["gnm_id"], int)[np.asarray(tpl["fid"])]
    fade = np.asarray(onemesh.asset()["g_fade"], float)
    hv = (gid >= 0) & (fade[np.maximum(gid, 0)] > 0.3)
    if "mh" not in _C:
        g = basemod._gnm_data()
        names = [str(n) for n in g["identity_names"]]
        comps = [i for i, n in enumerate(names) if n.startswith("head")][:170]
        gg = _gnm()
        T, gr, sp = gg["sp"]["T"], gg["gr"], gg["sp"]
        Lt = sp["WL"] @ T
        ycut = 0.5 * (Lt[1, 1] + Lt[15, 1])
        from . import humanmacro as hm
        face = gr["hockey_mask"].copy()
        face[np.asarray(hm.space()["sets"]["under_chin"], int)] = True
        IBh = np.asarray(g["vertex_identity_basis"])[comps].astype(np.float32)
        _C["mh"] = {"face": face, "LB": np.einsum("lv,kvc->klc", sp["WL"], IBh.astype(np.float64)),
                    "IB": IBh,
                    "JB": np.array([g["joint_identity_basis"][i][2:4] for i in comps], float),
                    "hair": (~gr["hockey_mask"]) & (~gr["ears"]) & (T[:, 1] > ycut - 0.005)}
    mh = _C["mh"]
    R, sc = np.asarray(carry["R"], float), float(carry["s"])
    idx = np.where(hv)[0]
    jm = mh["JB"].mean(1, keepdims=True)
    nx = len(expr["names"]) if expr else 0
    B = np.zeros((170 + nx, len(P), 3), np.float32)
    Bh = sc * (mh["IB"][:, gid[idx]].astype(np.float64) - jm) @ R.T * fade[gid[idx]][None, :, None]
    # How much of GNM's own move the model's head really makes (the one mesh blends, stitches and re-seats the head):
    # measured once per model on one fixed identity step, as the slope of the head's real vertex moves on the basis'
    # (0.85-0.89 on the gk_s models; TRIED and wrong: taking each comp's uniform scaling out, "the head's size comes
    # from the body": the outline's residual tripled).
    if kappa is None:
        dlt = 1.2 * np.sin(1.7 * np.arange(170) + 0.3) / np.sqrt(85.0) * np.sqrt(170.0) / 6.0
        sp2 = copy.deepcopy(spec)
        bi.set_identity(sp2, bi.identity(spec) + dlt)
        P2 = np.asarray(humanfit.state(sp2["base"])["tpl"]["P"], float)
        a_, b_ = (P2[idx] - P[idx]).ravel(), np.tensordot(dlt, Bh, 1).ravel()
        kappa = float(a_ @ b_ / max(b_ @ b_, 1e-18))
        kres = float(np.linalg.norm(a_ - kappa * b_) / max(np.linalg.norm(a_), 1e-12))
    else:
        kres = None
    Bh = kappa * Bh
    B[:170, idx] = Bh.astype(np.float32)
    XLB = None
    if expr:      # EXPRESSION columns (solvereads): each prototype's move of the model's head vertices and landmarks, carried
        if "XB" not in expr:      # as the identity's are; how much of it the model really makes is measured once (kx)
            Fx = _expr_fields(expr["names"])
            XB = sc * Fx[:, gid[idx]].astype(np.float64) @ R.T * fade[gid[idx]][None, :, None]
            mix = {n: 0.3 * (-1) ** i for i, n in enumerate(expr["names"])}
            sp2 = copy.deepcopy(spec)
            e0 = dict(sp2["base"]["head"].get("expression") or {})
            for k_, v_ in expression_coeffs(mix).items():
                e0[k_] = float(e0.get(k_, 0.0)) + v_
            sp2["base"]["head"]["expression"] = e0
            P2 = np.asarray(humanfit.state(sp2["base"])["tpl"]["P"], float)
            a_, b_ = (P2[idx] - P[idx]).ravel(), np.tensordot(np.array(list(mix.values())), XB, 1).ravel()
            expr["kx"] = float(a_ @ b_ / max(b_ @ b_, 1e-18))
            expr["kx_res"] = float(np.linalg.norm(a_ - expr["kx"] * b_) / max(np.linalg.norm(a_), 1e-12))
            expr["XB"] = (expr["kx"] * XB).astype(np.float32)
            expr["XLB"] = expr["kx"] * sc * np.einsum("lv,kvc->klc", _gnm()["sp"]["WL"], Fx.astype(np.float64)) @ R.T
        B[170:, idx] = expr["XB"]
        XLB = expr["XLB"]
    F = np.asarray(mesh["F"])
    cid = bi.identity(spec)
    Vg = _gnm()["sp"]["T"] + np.tensordot(cid, _gnm()["sp"]["IB"], 1)
    r = gnm_mm.readers(Vg)
    hair = np.zeros(len(P), bool)
    hair[idx] = mh["hair"][gid[idx]]
    # the two eye centres (st L 68, 69) and their bases: paired with GNM's eye joints by side
    g0 = headfit._gnm()
    eyeB = kappa * sc * (mh["JB"] - jm) @ R.T               # (170, 2, 3)
    off = sc * (np.asarray(g0["J0"], float)[:2] - np.asarray(g0["J0"], float)[:2].mean(0)) @ R.T
    E = np.asarray(st["L"], float)[68:70]
    order = [int(np.argmin(np.linalg.norm(off - (e - E.mean(0)), axis=1))) for e in E]
    face = np.zeros(len(P), bool)
    face[idx] = mh["face"][gid[idx]]
    ears = np.zeros(len(P), bool)
    ears[idx] = _gnm()["gr"]["ears"][gid[idx]]
    LB = kappa * sc * (mh["LB"] - jm) @ R.T                  # (170, 68, 3): the 68 landmarks' moves
    eB = [eyeB[:, j] for j in order]
    if expr:
        LB = np.concatenate([LB, XLB])
        eB = [np.concatenate([e_, np.zeros((nx, 3))]) for e_ in eB]      # the eyeballs do not move with an expression
    return {"face": face, "ears": ears, "LB": LB, "c": cid, "V": P, "F": F[hv[F].all(1)], "B": B, "bnd": np.zeros(len(P), bool), "mesh": mesh, "L": st["L"],
            "Jm": gnm_mm.jacobian()[:len(gnm_mm.NAMES)], "measures": {n: float(r[n]) for n in gnm_mm.NAMES},
            "kind": "model", "hair": hair, "spec": spec, "eye_X": E, "eye_B": eB, "expr": expr,
            "kappa": kappa, "kappa_res": kres, "rebuild": lambda c2: model_head(spec, c2, kappa, expr), "gid": gid, "R": R, "sc": sc}
