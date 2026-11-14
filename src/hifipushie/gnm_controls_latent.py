"""The controls themselves: names and families, a control's coefficients, the vertices and fields it gives, zone stats, macro effects. Part of GNM's controls (gnm_controls.py has the overview)."""
from __future__ import annotations

import re

import numpy as np

from . import gnm_controls
from .gnm_controls import gnm, zones

# ---------------------------------------------------------------- the controls
def _sampler():
    from . import gnm_sampler
    return gnm_sampler


def names(family: str | None = None) -> list[str]:
    """Every control name (of one family)."""
    g = gnm()
    out = {"identity": [n for n in g["id_names"]],
           "region_pc": [f"pc:{r}{k}" for r in sorted(k for k in g["groups"] if k.endswith("_region")) for k in range(8)],
           "expr_eyes": [f"both_eye_region_{k:03d}" for k in range(100)],
           "expr_lower": [f"lower_face_region_{k:03d}" for k in range(150)],
           "expr_tongue": [n for n in g["ex_names"] if n.startswith("tongue")] + ["pupil"],
           "joints": [f"joint:{j}_{a}" for j in ("neck", "head") for a in "xyz"] + ["joint:eyes_x", "joint:eyes_y"],
           "sampler_latent": [f"z:{k:02d}" for k in range(64)] + [f"zpc:{k:02d}" for k in range(16)],
           "sampler_label": ["label:sex"] + [f"label:{e}" for e in ("middle_eastern", "asian", "white", "black")],
           "sampler_expr": [f"xclass:{n}" for n in ("surprise", "disgust", "suck", "compress_face", "stretch_face", "happy",
                                                     "squint", "platysma", "blow", "funneler", "smile_wide", "corners_down",
                                                     "pucker", "wink_left", "wink_right", "mouth_left", "mouth_right",
                                                     "lips_roll_in", "snarl", "tongue_center")],
           "blockin": _blockin_names()}
    if family:
        return out[family]
    return [n for f in gnm_controls.FAMILIES for n in out[f]]


def _blockin_names() -> list[str]:
    from . import blockin as bi, humanmacro as hm
    return list(hm.NAMES) + [f"nd:{n}" for n in bi.gap_names()] + ["sex", "eth0", "eth1", "eth2"]


def family(name: str) -> str:
    if name.startswith("pc:"):
        return "region_pc"
    if name.startswith("both_eye_region") or name.startswith(("left_eye_region", "right_eye_region")):
        return "expr_eyes"
    if name.startswith("lower_face_region"):
        return "expr_lower"
    if name.startswith("tongue") or name == "pupil" or name.startswith("pupil"):
        return "expr_tongue"
    if name.startswith("joint:"):
        return "joints"
    if name.startswith(("z:", "zpc:")):
        return "sampler_latent"
    if name.startswith("label:"):
        return "sampler_label"
    if name.startswith("xclass:"):
        return "sampler_expr"
    if re.fullmatch(r"(head|eyes|teeth)_\d{3}", name):
        return "identity"
    return "blockin"


def _latent_at():
    """The sampler's latent study point: z = 0 at the female / white class; its Jacobian (253 x 64) and SVD."""
    if "lat" not in gnm_controls._C:
        S = _sampler()
        lab = S.id_label("female", "white")
        J = S.identity().jac(np.zeros(64), lab)[:, :64]
        U, s, Vt = np.linalg.svd(J[:170], full_matrices=False)
        gnm_controls._C["lat"] = {"lab": lab, "J": J, "Vt": Vt, "s": s, "c0": S.identity()(np.zeros(64), lab)[0]}
    return gnm_controls._C["lat"]


def coefficients(name: str, amount: float = 1.0, base_id=None) -> tuple:
    """(identity (253,), expression (383,), rotations (4, 3) or None) for `amount` units of a control, on base_id
    (identity 253; default 0, the template). Linear families add amount x the unit; sampler latents and labels are
    DECODED (non-linear: the sampler's own head at that latent / label, not base_id + a direction)."""
    g = gnm()
    c = np.zeros(len(g["id_names"])) if base_id is None else np.array(base_id, float)
    e = np.zeros(len(g["ex_names"]))
    rot = None
    f = family(name)
    if f == "identity":
        c[g["id_names"].index(name)] += amount
    elif f in ("region_pc", "blockin"):
        from . import blockin as bi
        d = bi.direction(name)
        if name == "sex":
            d = d / 2
        c[:170] += amount * d
    elif f == "expr_eyes":
        k = int(name[-3:])
        for side in ("left", "right"):
            nm = f"{side}_eye_region_{k:03d}"
            if name.startswith(("both", side)):
                e[g["ex_names"].index(nm)] += amount
    elif f in ("expr_lower", "expr_tongue"):
        if name == "pupil":
            e[[i for i, n in enumerate(g["ex_names"]) if "pupil" in n]] += amount
        else:
            e[g["ex_names"].index(name)] += amount
    elif f == "joints":
        rot = np.zeros((4, 3))
        j, a = name[6:].rsplit("_", 1)
        ax = "xyz".index(a)
        rad = np.radians(10.0 * amount)
        if j == "eyes":
            rot[2, ax] = rot[3, ax] = rad
        else:
            rot[["neck", "head"].index(j), ax] = rad
    elif f == "sampler_latent":
        S, la = _sampler(), _latent_at()
        k = int(name.split(":")[1])
        zz = np.zeros(64)
        if name.startswith("z:"):
            zz[k] = amount
        else:
            zz = amount * la["Vt"][k]
        c = S.identity()(zz, la["lab"])[0]
    elif f == "sampler_label":
        S = _sampler()
        t = 0.5 + 0.5 * amount
        if name == "label:sex":
            lab = S.id_label(t, None)
        else:
            u = S.id_label(0.5, None)
            lab = u.copy()
            lab[2:] = (1 - t) * 0.25 + t * (np.arange(4) == S.ETH.index(name[6:]))
            if amount < 0:   # away from the class: the other three
                lab[2:] = (1 + amount) * 0.25 + (-amount) * (np.arange(4) != S.ETH.index(name[6:])) / 3.0
        c = S.identity()(np.zeros(64), lab)[0]
    elif f == "sampler_expr":
        S = _sampler()
        e = amount * S.expression()(np.zeros(64), S.ex_label(name[7:]))[0]
    return c, e, rot


def vertices(c=None, e=None, rot=None) -> np.ndarray:
    """GNM's head (GNM frame, metres) for identity c (253), expression e (383), joint rotations rot (4, 3 axis-angle)."""
    g = gnm()
    V = g["T"].copy()
    if c is not None and np.any(c):
        V += np.tensordot(np.asarray(c, np.float32), g["IB"][:len(c)], 1)
    if e is not None and np.any(e):
        V += np.tensordot(np.asarray(e, np.float32), g["EB"][:len(e)], 1)
    if rot is None or not np.any(rot):
        return V
    J = g["J"] + (np.tensordot(np.asarray(c, float), g["JB"][:len(c)], 1) if c is not None else 0)
    Wt = []
    for k, p in enumerate(g["parents"]):
        R = _rodrigues(rot[k])
        loc = J[k] if p < 0 else J[k] - J[p]
        M = np.eye(4)
        M[:3, :3], M[:3, 3] = R, loc
        Wt.append(M if p < 0 else Wt[p] @ M)
    out = np.zeros_like(V)
    for k in range(len(J)):
        A = Wt[k].copy()
        A[:3, 3] -= A[:3, :3] @ J[k]
        out += g["W"][k][:, None] * (V @ A[:3, :3].T + A[:3, 3])
    return out


def _rodrigues(r):
    r = np.asarray(r, float)
    a = np.linalg.norm(r)
    if a < 1e-12:
        return np.eye(3)
    k = r / a
    K = np.array([[0, -k[2], k[1]], [k[2], 0, -k[0]], [-k[1], k[0], 0]])
    return np.eye(3) + np.sin(a) * K + (1 - np.cos(a)) * K @ K


def field(name: str, base_id=None, h: float = 1.0) -> np.ndarray:
    """The control's move per unit (V, 3, metres, GNM frame): central difference over +-h (exact for the linear
    families)."""
    vp = vertices(*coefficients(name, h, base_id))
    vm = vertices(*coefficients(name, -h, base_id))
    return (vp - vm) / (2 * h)


def zone_stats(D: np.ndarray) -> np.ndarray:
    """(n zones, 6): tot, nrm, sgn, trans, deform, relief (mm per unit) of a move D (V, 3, metres). relief = the zone's
    mean normal move minus its 5 mm surround's: + the zone rises out of its surroundings (a groove gets shallower, a
    ridge stronger), - it sinks (a crease deepens)."""
    Z = zones()
    n = gnm_controls._C["normals"]
    sur = gnm_controls._C["surround"]
    out = np.zeros((len(gnm_controls.ZONES), len(gnm_controls.STATS)))
    for i, k in enumerate(gnm_controls.ZONES):
        idx = Z[k]
        if not len(idx):
            continue
        d = D[idx] * gnm_controls.MM
        dn = (d * n[idx]).sum(1)
        m = d.mean(0)
        rel = 0.0
        if len(sur[k]):
            rel = dn.mean() - ((D[sur[k]] * gnm_controls.MM) * n[sur[k]]).sum(1).mean()
        out[i] = [np.sqrt((d ** 2).sum(1).mean()), np.sqrt((dn ** 2).mean()), dn.mean(), np.linalg.norm(m),
                  np.sqrt(((d - m) ** 2).sum(1).mean()), rel]
    return out


def macro_effect(name: str, base_id=None) -> np.ndarray:
    """The macros (humanmacro, in their population sd) a control moves per unit (central difference)."""
    from . import humanmacro as hm
    sd = hm.table()["sd"]
    w = lambda V: np.c_[V[:, 0], -V[:, 2], V[:, 1]]  # noqa: E731
    mp = hm.measures(w(vertices(*coefficients(name, 1.0, base_id))))
    mn = hm.measures(w(vertices(*coefficients(name, -1.0, base_id))))
    return np.array([(mp[k] - mn[k]) / 2 / sd[i] for i, k in enumerate(hm.NAMES)])


def identity_direction(name: str) -> np.ndarray | None:
    """The control's move in the 170 head components per unit (None for expression / pose controls)."""
    f = family(name)
    if f in ("expr_eyes", "expr_lower", "expr_tongue", "joints", "sampler_expr"):
        return None
    cp, _, _ = coefficients(name, 1.0)
    cm, _, _ = coefficients(name, -1.0)
    return (cp - cm)[:170] / 2
