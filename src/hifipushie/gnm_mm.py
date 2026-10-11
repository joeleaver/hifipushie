"""Millimetre moves: a measure a driver can SEE (pupils apart, the forehead ahead of the nasion, the chin forward...) moved
1 mm with every other measure held in millimetres (gnmdrive, 2026-10-10).

The macros (humanmacro) are ratios over the interocular distance, so holding them while the eyes move apart scales the
whole head (head_size! moved the neck 10 mm and the skull 8 mm per sd). Here the held quantities are the readouts in mm,
so "eyes further apart" is the eyes alone: |dc| 0.62 per mm, the face's other skin 0.35 mm rms. A block-in move
`"mm:<measure>": mm` = the least-norm change of GNM's 170 head comps doing exactly that (linear, exact).
GNM frame for the readers: x left, y up, z forward, mm."""
from __future__ import annotations

import numpy as np

_C: dict = {}


def _space():
    if "sp" not in _C:
        from . import base as basemod, humanmacro as hm
        g = basemod._gnm_data()
        names = [str(n) for n in g["identity_names"]]
        comps = [i for i, n in enumerate(names) if n.startswith("head")]
        IB = np.asarray(g["vertex_identity_basis"])[comps].astype(np.float64)
        T = np.asarray(g["template_vertex_positions"], float)
        gr = {k: np.asarray(v, float) > 0.5 for k, v in g["groups"].items()}
        WL = np.zeros((68, len(T)))
        for i, r in enumerate(g["lm68"]):
            for v, x in zip(r[0::2], r[1::2]):
                WL[i, int(v)] += float(x)
        _C["sp"] = {"T": T, "IB": IB, "gr": gr, "WL": WL, "sets": hm.space()["sets"]}
    return _C["sp"]


def readers(V: np.ndarray) -> dict:
    """The measures (mm) on GNM-frame vertices V (m)."""
    sp = _space()
    S, gr = sp["sets"], sp["gr"]
    V = V * 1000
    L = sp["WL"] @ V
    eL, eR = V[gr["left_eye"]].mean(0), V[gr["right_eye"]].mean(0)
    pog = V[S["pog"]].mean(0)
    cr = V[S["cranium"]]
    fh = V[S["forehead"]].mean(0)
    return {
        "pupils_apart": abs(eL[0] - eR[0]),
        "eyes_forward": 0.5 * (eL[2] + eR[2]) - L[27, 2],
        "eyes_height": 0.5 * (eL[1] + eR[1]) - L[33, 1],
        "brows_over_eyes": L[[19, 24], 1].mean() - 0.5 * (eL[1] + eR[1]),
        "forehead_forward": fh[2] - L[27, 2],
        "tip_forward": L[30, 2] - L[33, 2],
        "subnasale_forward": L[33, 2] - 0.5 * (eL[2] + eR[2]),
        "upper_lip_forward": L[51, 2] - L[33, 2],
        "lower_lip_forward": L[57, 2] - L[51, 2],
        "chin_forward": pog[2] - L[57, 2],
        "philtrum_length": L[33, 1] - L[51, 1],
        "chin_length": L[57, 1] - L[8, 1],
        "nose_length": L[27, 1] - L[33, 1],
        "cheekbone_width": np.ptp(V[S["zyg"], 0]),
        "jaw_width": L[12, 0] - L[4, 0],
        "chin_width": L[10, 0] - L[6, 0],
        "mouth_width": L[54, 0] - L[48, 0],
        "nose_width": L[35, 0] - L[31, 0],
        "skull_width": np.ptp(cr[:, 0]),
        "skull_top": cr[:, 1].max() - L[27, 1],
        "skull_back": L[27, 2] - cr[:, 2].min(),
        "neck_width": np.ptp(V[S["neck"], 0]),
        "under_chin": L[8, 1] - V[S["under_chin"], 1].mean(),
        # held, never moved: where the face sits in the head's frame (else a move may slide the face: the measures
        # above are all relative, and a slid face reads as a shifted profile against the picture)
        "_face_x": L[:, 0].mean(), "_face_y": L[:, 1].mean(), "_face_z": L[:, 2].mean(),
    }


NAMES = ("pupils_apart", "eyes_forward", "eyes_height", "brows_over_eyes", "forehead_forward", "tip_forward",
         "subnasale_forward", "upper_lip_forward", "lower_lip_forward", "chin_forward", "philtrum_length",
         "chin_length", "nose_length", "cheekbone_width", "jaw_width", "chin_width", "mouth_width", "nose_width",
         "skull_width", "skull_top", "skull_back", "neck_width", "under_chin")
HELD = NAMES + ("_face_x", "_face_y", "_face_z")


def jacobian() -> np.ndarray:
    """(n readers, 170): mm per head comp (exact: the readers are linear in V up to the ptp / abs, linearised at GNM's
    template)."""
    if "J" not in _C:
        sp = _space()
        r0 = readers(sp["T"])
        J = np.zeros((len(HELD), 170))
        for k in range(170):
            r = readers(sp["T"] + sp["IB"][k] * 1e-3)
            J[:, k] = [(r[n] - r0[n]) / 1e-3 for n in HELD]
        _C["J"] = J
    return _C["J"]


def direction(name: str) -> np.ndarray:
    """`mm:<reader>`: the least-norm dc moving the reader +1 mm with every other reader held at 0 (170,)."""
    m = name[3:] if name.startswith("mm:") else name
    if m not in NAMES:
        raise ValueError(f"mm: one of {', '.join(NAMES)}")
    J = jacobian()
    i = NAMES.index(m)
    b = np.zeros(len(HELD))
    b[i] = 1.0
    return J.T @ np.linalg.solve(J @ J.T + 1e-6 * np.eye(len(J)), b)
