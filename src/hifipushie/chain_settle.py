"""CHAIN SETTLE: the body's frame and the tapes' pulls the rolled panels are assembled and dressed with (N2d of
docs/proposals/step5_rewrite.md; chain_assemble). N2c's growing body (the garment settled by a full chain solve while the
body grew inside it) is gone with N2c's placement.
- skeleton(body): the body's centre lines from its landmarks (torso from the crotch to the neck, head, shoulder line to
  each wrist and on to the hand, legs): a general frame, nothing per garment. Assembly keeps the panels off it (which
  way round: arms in sleeves, neck in the collar).
- girth_pulls: step 3's girth loops each piece was drafted on (step 4's tapes) pull the piece's chain points at that
  height towards the loop at their own angle round it (soft; where the body was measured: never a pin).
- pull_report: mm from each pull's points to their targets.
"""
from __future__ import annotations

import numpy as np

from .chain_core import hand_of

GIRTH_BAND = 0.02  # m: chain points this near a girth loop's plane are pulled towards it
GIRTH_W = 0.3  # weight of a girth pull


def skeleton(body) -> np.ndarray:
    """(k, 2, 3) segments: the body's centre lines from its landmarks (module doc)."""
    at = {k: np.asarray(v, float) for k, v in body.at.items() if np.size(v) == 3}
    z = {k: float(v) for k, v in body.at.items() if np.size(v) == 1}
    V = np.asarray(body.V, float)
    neck = 0.5 * (at["cb_neck"] + at["cf_neck"])
    zc = z.get("crotch_z", V[:, 2].min() + 0.45 * np.ptp(V[:, 2]))
    band = V[np.abs(V[:, 2] - zc - 0.05) < 0.03]
    yc = float(band[:, 1].mean()) if len(band) else float(neck[1])
    hip = np.array([0.0, yc, zc])
    S = [(hip, neck), (neck, neck + [0, 0, 0.15])]
    for sg in (1.0, -1.0):
        m = np.array([sg, 1.0, 1.0])
        sh, el, wr = at["shoulder.L"] * m, at["elbow.L"] * m, at["wrist.L"] * m
        S += [(neck, sh), (sh, el), (el, wr), (wr, wr + 0.4 * (wr - el))]
        lx = 0.5 * float(np.abs(V[np.abs(V[:, 2] - zc + 0.1) < 0.02][:, 0]).max()) if len(V) else 0.09
        S += [(np.array([sg * lx, yc, zc]), np.array([sg * lx, yc, V[:, 2].min()]))]
    return np.array([np.array(s) for s in S])


def girth_pulls(cnet, X, weight=GIRTH_W, band=GIRTH_BAND) -> list:
    """Each piece's chain points near the plane of a girth loop it was drafted on, pulled to the loop at their angle."""
    st = cnet.M.get("starts") or {}
    T = st.get("tapes") or {}
    out = []
    for p, nm in enumerate(cnet.names):
        ids = np.unique(cnet.chain_v[cnet.chain_piece == p])
        for t in (st.get("pieces") or {}).get(nm) or []:
            if t not in T or T[t].get("kind") != "loop":
                continue
            Q = np.asarray(T[t]["pts"], float) * ([-1, 1, 1] if hand_of(nm) < 0 else [1, 1, 1])
            c = Q.mean(0)
            _, _, Vt = np.linalg.svd(Q - c)
            u, v, n = Vt
            sel = ids[np.abs((X[ids] - c) @ n) < band]
            if not len(sel):
                continue
            aq = np.arctan2((Q - c) @ v, (Q - c) @ u)
            ap = np.arctan2((X[sel] - c) @ v, (X[sel] - c) @ u)
            k = np.abs(np.angle(np.exp(1j * (ap[:, None] - aq[None])))).argmin(1)
            out.append({"ids": sel, "to": Q[k], "weight": weight, "name": f"{nm} on {t}"})
    return out


def pull_report(X, pulls) -> dict:
    """mm from each pull's points to their targets: {name: [mean, max]}."""
    return {p["name"]: [round(float(d.mean()) * 1e3, 1), round(float(d.max()) * 1e3, 1)]
            for p in pulls for d in [np.linalg.norm(X[p["ids"]] - p["to"], axis=1)]}
