"""CHAIN SETTLE (N2c of docs/proposals/step5_rewrite.md, "The build" 3): the ASSEMBLED garment (chain_lay.lay: every seam
one chain, every link at its cut) goes onto the body by bends only. Nothing is ever apart, so nothing is closed here.

Joe (2026-11-12): "in real life, the pieces would get assembled _before_ they get put on the body." A dresser puts the
made garment round the wearer; here the body GROWS inside it instead (the same thing seen from the garment):
- skeleton(body): the body's centre lines from its landmarks (torso from the crotch to the neck, head, shoulder line to
  each wrist and on to the hand, legs): a general frame, nothing per garment.
- grown(body, s): every body vertex moved towards its nearest skeleton point, to s of its distance (s = 1: the body).
  The garment is assembled round grown(body, ASSEMBLE_S) (arms through sleeves, neck through the collar: which way
  round) and then settled at each GROW stage.
- girth_pulls: step 3's girth loops each piece was drafted on (step 4's tapes) pull the piece's chain points at that
  height towards the loop at their own angle round it (soft; where the body was measured: never a pin).
- settle: chain_solve at each stage (links hard, seams one chain, contact with the grown body, bending, folds, the
  taped edge's and the girths' pulls, followers as a term) and chain_lay.measures after each.
"""
from __future__ import annotations

import numpy as np

from . import chain_lay, chain_solve
from .chain_core import Body, hand_of

ASSEMBLE_S = 0.3  # the frame the garment is assembled round: the body shrunk to this fraction towards its skeleton
GROW = (0.65, 1.0)  # the body's sizes the garment is settled at, in turn
GIRTH_BAND = 0.02  # m: chain points this near a girth loop's plane are pulled towards it
GIRTH_W = 0.3  # weight of a girth pull (the taped edge's is 1)


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


def _nearest(P, S):
    a, b = S[:, 0], S[:, 1]
    ab = b - a
    t = np.clip(((P[:, None] - a[None]) * ab[None]).sum(2) / np.maximum((ab * ab).sum(1), 1e-12)[None], 0, 1)
    Q = a[None] + t[..., None] * ab[None]
    d = np.linalg.norm(P[:, None] - Q, axis=2)
    return Q[np.arange(len(P)), d.argmin(1)]


def grown(body, s: float, segs=None) -> Body:
    """The body with every vertex at s of its distance from its nearest skeleton point (module doc)."""
    segs = skeleton(body) if segs is None else segs
    V = np.asarray(body.V, float)
    Q = _nearest(V, segs)
    return Body(Q + s * (V - Q), body.T, dict(body.at))


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


def settle(cnet, S, body, plan, stages=GROW, log=None) -> tuple:
    """(X, [report per stage]) (module doc)."""
    segs = skeleton(body)
    X = S["X0"]
    pulls = list(S["pulls"]) + girth_pulls(cnet, X)
    reps = []
    for s in stages:
        b = grown(body, s, segs)
        X, rep = chain_solve.solve(cnet, X, body=b, ties=S["ties"], folds=S["folds"], pulls=pulls, plies=S["plies"],
                                   log=log)
        rep["grown"] = s
        rep["measures"] = chain_lay.measures(cnet, X, plan, b.contact)
        rep["pulls_mm"] = pull_report(X, pulls)
        reps.append(rep)
    return X, reps
