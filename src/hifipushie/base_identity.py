"""A GNM head's identity: its data and coefficients, fitting the identity to measures, the posed expression,
region weights and regional identity. Part of base (base.py has the overview)."""
from __future__ import annotations

import json

import numpy as np

from . import retopo
from .base import GNM, _CACHE

def _gnm_data():
    if "gnm" not in _CACHE:
        from . import assets
        path = assets.path("gnm", GNM)  # says how to fetch it when missing
        z = np.load(path)
        names = list(z["vertex_group_names"])
        _CACHE["gnm"] = {k: z[k] for k in ("template_vertex_positions", "vertex_identity_basis", "expression_basis",
                                           "template_joint_positions", "joint_identity_basis", "quads",
                                           "identity_names", "expression_names")}
        # the skin without the mouth bag: its walls sit a few mm inside the lips and made the IMLS sparkle there
        _CACHE["gnm"]["skin"] = (z["vertex_groups"][names.index("skin")] > 0.5) & ~(z["vertex_groups"][names.index("mouth_sock")] > 0.5)
        rows = (path.parent.parent.parent / "landmarks" / "head_sparse_68.txt").read_text().split("\n")
        _CACHE["gnm"]["lm68"] = [[float(x) for x in r.split()] for r in rows if r.strip()]
        _CACHE["gnm"]["eye"] = [z["vertex_groups"][names.index(g)] > 0.5 for g in ("left_eye", "right_eye")]
        _CACHE["gnm"]["groups"] = {str(n): z["vertex_groups"][i] for i, n in enumerate(names)}
    return _CACHE["gnm"]


def _gnm_coeffs(names, given, seed=None, spread=1.0):
    c = np.zeros(len(names))
    if seed is not None:
        rng = np.random.default_rng(int(seed))
        head = np.array([n.startswith("head") for n in names])
        c[head] = rng.normal(0, spread, head.sum())
    for k, v in (given or {}).items():
        c[list(names).index(k)] = float(v)
    return c


FIT_KEYS = ("face_width", "jaw_width", "chin_width", "eye_chin", "eye_mouth", "eye_nose", "nose_width",
            "mouth_width", "eye_seam")


def _measures(V, J, lm):
    """Front-view face proportions (GNM frame, Y up), in metres: widths across the jaw line at the ears, at the
    jaw's angle and at the chin; drops from the eye line to the chin, the lower lip and the nose base; the nose's
    width at the wings, the mouth's corner to corner; the drop to the lips' seam (the philtrum's end); interocular."""
    io = J[2][0] - J[3][0]
    ey = 0.5 * (J[2][1] + J[3][1])
    return np.array([lm(16)[0] - lm(0)[0], lm(12)[0] - lm(4)[0], lm(10)[0] - lm(6)[0], ey - lm(8)[1],
                     ey - lm(57)[1], ey - lm(33)[1], lm(35)[0] - lm(31)[0], lm(54)[0] - lm(48)[0],
                     ey - 0.5 * (lm(62)[1] + lm(66)[1]), io])


def face_measures(head: dict) -> dict:
    """The head's FIT_KEYS as they came out (interocular units), to compare with a fit's targets or a style sheet."""
    g = _gnm_data()
    ident = dict(fit_identity(head["fit"])) if head.get("fit") else {}
    ident.update(head.get("identity") or {})
    ci = _gnm_coeffs(g["identity_names"], ident, head.get("seed"), head.get("spread", 1.0))
    V = g["template_vertex_positions"] + np.tensordot(ci, g["vertex_identity_basis"], 1)
    J = g["template_joint_positions"] + np.tensordot(ci, g["joint_identity_basis"], 1)
    m = _measures(V, J, lambda i: sum(w * V[int(v)] for v, w in zip(g["lm68"][i][0::2], g["lm68"][i][1::2])))
    return {k: round(float(m[j] / m[-1]), 3) for j, k in enumerate(FIT_KEYS)}


# pose: landmark moves (world m, before the head's scale) solved as the least change of GNM's regional expression
# components; every other landmark is held. Keys -> (landmark ids, direction in GNM's frame: x = the head's left,
# y up, z forward); ".L" landmarks mirror (x flips)
POSE = {"smile": ([48, 54], [0.35, 1.0, -0.15]),  # mouth corners up (and a little out and back)
        "mouth_width": ([48, 54], [1.0, 0.0, 0.0]),  # each corner out
        "lid_upper": ([37, 38, 43, 44], [0.0, -1.0, 0.0]),  # upper lid margins down (closes the eye)
        "lid_lower": ([40, 41, 46, 47], [0.0, 1.0, 0.0]),  # lower lid margins up (a smile's lower lid)
        "mouth_raise": (list(range(48, 68)), [0.0, 1.0, 0.0]),  # the whole mouth up (a shorter philtrum)
        "brow_inner": ([20, 21, 22, 23], [0.0, 1.0, 0.0]),  # inner brow up (open, kind; negative: a frown)
        "brow_outer": ([17, 18, 25, 26], [0.0, 1.0, 0.0])}  # outer brow up (negative: drooping, relaxed)


POSE_HOLD = 0.35  # weight of holding every landmark not moved (the rest of the face stays put)


def pose_expression(pose: dict, V: np.ndarray, scale: float) -> np.ndarray:
    """Expression components (lower face + both eye regions) for head["pose"] = {key: m}, POSE keys: ridge least
    squares on the 68 landmarks' displacements (exactly linear in the components). Returns the vertex offsets."""
    g = _gnm_data()
    unknown = set(pose) - set(POSE)
    if unknown:
        raise ValueError(f"base head pose: unknown {sorted(unknown)}; use {sorted(POSE)} (m, world)")
    key = ("pose", json.dumps(pose, sort_keys=True), round(float(scale), 5), float(V[0, 0]), float(V[-1, 1]))
    if key in _CACHE:
        return _CACHE[key]
    names = [str(n) for n in g["expression_names"]]
    comps = ([i for i, n in enumerate(names) if n.startswith("lower_face")][:60]
             + [i for i, n in enumerate(names) if n.startswith("left_eye")][:40]
             + [i for i, n in enumerate(names) if n.startswith("right_eye")][:40])
    rows = g["lm68"]
    if "pose_A" not in _CACHE:  # (constant: the landmarks' rows of the expression basis; 0.5e9 multiplies a call before)
        Wlm = np.zeros((68, len(V)))
        for i, r in enumerate(rows):
            for v, w in zip(r[0::2], r[1::2]):
                Wlm[i, int(v)] += float(w)
        B = g["expression_basis"][comps]  # (c, n, 3)
        _CACHE["pose_A"] = (Wlm, B, np.einsum("ln,cnd->ldc", Wlm, B).reshape(68 * 3, len(comps)))
    Wlm, B, A = _CACHE["pose_A"]
    t = np.zeros((68, 3))
    w = np.full((68, 3), POSE_HOLD)
    X0 = Wlm @ V
    mid_x = float(X0[:, 0].mean())
    for k, amount in pose.items():
        ids, d = POSE[k]
        for i in ids:
            dd = np.array(d, float)
            if X0[i, 0] < mid_x:  # the head's right side: mirrored
                dd[0] = -dd[0]
            t[i] += float(amount) / scale * dd / np.linalg.norm(d)
            w[i] = 1.0
    w, t = w.ravel(), t.ravel()
    lam = 1e-6
    c = np.linalg.solve((A * w[:, None]).T @ (A * w[:, None]) + lam * np.eye(len(comps)), (A * w[:, None]).T @ (t * w))
    out = np.tensordot(c, B, 1)
    _CACHE[key] = out
    return out


def fit_identity(target: dict, n: int = 80, lam: float = 2e-6) -> dict:
    """GNM head components (the first n) that give these face proportions, in interocular units (FIT_KEYS; e.g.
    {"face_width": 2.1, "jaw_width": 1.6}; keys left out keep the mean's), interocular held: ridge least squares
    on the landmark measurements (linear in the identity), components clipped to +-2.5 sigma. Cached."""
    key = ("fit", json.dumps(target, sort_keys=True), n)
    if key in _CACHE:
        return _CACHE[key]
    g = _gnm_data()
    V0, J0 = g["template_vertex_positions"].astype(float), g["template_joint_positions"].astype(float)

    def meas(V, J):
        return _measures(V, J, lambda i: sum(w * V[int(v)] for v, w in zip(g["lm68"][i][0::2], g["lm68"][i][1::2])))
    m0 = meas(V0, J0)
    head = [i for i, nm in enumerate(g["identity_names"]) if str(nm).startswith("head")][:n]
    A = np.array([meas(V0 + g["vertex_identity_basis"][i], J0 + g["joint_identity_basis"][i]) - m0 for i in head]).T
    unknown = set(target) - set(FIT_KEYS)
    if unknown:
        raise ValueError(f"base head fit: unknown {sorted(unknown)}; use {FIT_KEYS} (interocular units)")
    t = np.array([float(target.get(k, m0[j] / m0[-1])) for j, k in enumerate(FIT_KEYS)] + [1.0]) * m0[-1]
    # the first six keys hold the mean when left out (as they always did); the later ones are free unless given
    w = np.array([1.0 if (j < 6 or k in target) else 0.0 for j, k in enumerate(FIT_KEYS)] + [2.0])
    c = np.linalg.solve((A * w[:, None]).T @ (A * w[:, None]) + lam * np.eye(len(head)), (A * w[:, None]).T @ ((t - m0) * w))
    out = {str(g["identity_names"][i]): float(v) for i, v in zip(head, np.clip(c, -2.5, 2.5))}
    _CACHE[key] = out
    return out


def _lm_of(g, V):
    return np.array([sum(float(w) * V[int(v)] for v, w in zip(r[0::2], r[1::2])) for r in g["lm68"]])


def region_weight(groups, feather: int = 8) -> np.ndarray:
    """A soft weight over GNM's vertices: 1 on the named region groups (one name or a list), feathered by `feather`
    rounds of Laplacian smoothing over the head's quads (the groups have hard edges: a component applied on the bare
    group left a step at its border). Cached."""
    groups = [groups] if isinstance(groups, str) else list(groups)
    key = ("region_w", tuple(groups), int(feather))
    if key not in _CACHE:
        g = _gnm_data()
        unknown = [k for k in groups if k not in g["groups"]]
        if unknown:
            raise ValueError(f"base head regions: unknown group {unknown}; groups: {sorted(g['groups'])}")
        w = np.clip(sum(np.asarray(g["groups"][k], float) for k in groups), 0, 1)
        Q = g["quads"]
        E = retopo.edges(Q.ravel(), np.full(len(Q), 4))
        deg = np.maximum(np.bincount(E.ravel(), minlength=len(w)), 1)
        for _ in range(int(feather)):
            w = np.maximum(w, w + 0.5 * retopo._lap(w[:, None], E, deg)[:, 0])  # grows outward, never eats the group
        _CACHE[key] = w
    return _CACHE[key]


def near_weight(near: dict) -> np.ndarray:
    """A smooth bump over GNM's template vertices: {"lm": [ids] (their mean), "offset": [x, y, z] (GNM's frame: y up,
    z forward, m before the head's scale), "radius": m}, 1 at the centre, falling as a Gaussian. For regions no
    group covers (the soft tissue under the chin)."""
    g = _gnm_data()
    V = g["template_vertex_positions"].astype(float)
    c = _lm_of(g, V)[list(near["lm"])].mean(0) + np.asarray(near.get("offset", [0, 0, 0]), float)
    return np.exp(-(np.linalg.norm(V - c, axis=1) / float(near["radius"])) ** 2)


def regional_identity(regions) -> np.ndarray:
    """head["regions"] = [{"group": name | [names], "feather": rounds (default 8), "identity": {component: value}}]:
    GNM identity components applied only within a region (a feathered group weight): a nose or a chin fitted on its
    own (the whole-head components move the eyes and the jaw with it). A region may instead (or as well) be
    "near": {"lm", "offset", "radius"} (near_weight; the max of both). Offsets on GNM's vertices, in its frame."""
    g = _gnm_data()
    D = np.zeros_like(g["template_vertex_positions"], dtype=float)
    for r in regions or []:
        c = _gnm_coeffs(g["identity_names"], r.get("identity") or {})
        w = region_weight(r["group"], int(r.get("feather", 8))) if r.get("group") else 0.0
        if r.get("near"):
            w = np.maximum(w, near_weight(r["near"]))
        D += w[:, None] * np.tensordot(c, g["vertex_identity_basis"], 1)
    return D


def _local_smooth(W, E, deg, wv, iters):
    """Plain (shrinking) Laplacian smoothing weighted per vertex: fills creases and closes small cavities (the
    under-eye crease, nostril holes) where wv > 0."""
    for _ in range(int(iters)):
        W = W + 0.5 * wv[:, None] * retopo._lap(W, E, deg)
    return W
