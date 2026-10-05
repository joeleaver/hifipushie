"""The head follows the body: a GNM head (base.head) shaped by the MakeHuman body's age / sex / weight.

GNM's identities are seeded adults with no age or sex controls; MakeHuman's macro targets shape a whole head for any
age, sex and weight, on a FIXED topology. `makehuman_lm68.json` (made once by spikes/headfit/make_table.py: the two
neutral heads aligned, nearest vertices, forced symmetric, checked in a picture) names the MakeHuman vertices at GNM's
68 face landmarks plus four cranium points. For a body, the landmarks' MOVE from MakeHuman's reference head (an
average 25-year-old) to the body's own head, in interocular units round the eye midpoint, is added to the GNM head's
own landmarks (its seeded identity is kept: delta transfer, so the table's millimetres of mismatch cancel) and solved
in GNM's identity components by ridge least squares, eye centres held. The head's scale = the body's interocular
over the fitted GNM's, so the head is the body's own head's size.

base.head key `follow_body`: OFF unless asked (existing characters keep their heads bit for bit); true, or a strength
0..1.5 (how much of the move), turns it on. New characters on a MakeHuman body should set it. The head's own
`identity` entries and a given `scale` win over what it solves.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

_CACHE: dict = {}
N = 120  # identity components solved
LAM = 1.5e-6  # ridge on the components (they are in standard deviations; the equations in metres)
CLIP = 2.6
# what the body's head is trusted for: the outline, brows and nose in full; the lids and lips less (their moves are
# millimetres, near the table's own error, and pushed hard they tore the lid margins and twisted the lips)
W_LM = np.r_[np.ones(36), np.full(12, 0.3), np.full(12, 0.5), np.full(8, 0.15)]
CRANIUM = ("top", "back", "side.L", "side.R")
W_CRANIUM = 1.0
W_EYES = 4.0
W_DENSE = 0.45  # each of the ~350 dense pairs (cheeks, brow ridge, cranium, neck: what no landmark sees). They also
# hold the neck and bib to the body's own: left free, the fit flared the bib up to the graft plane (a stand-up collar)
# what the identity space leaves undone goes into a smooth warp of the head (Gaussian RBF on the points' residuals):
# GNM's components made 60-70% of a move, and a woman's or a child's face needs the rest (jaw and chin width, brow
# ridge, the neck's girth). SIGMA in interoculars; the lids and lips take little of it (W_LM)
WARP_SIGMA = 0.42
WARP_RIDGE = 0.02
WARP = 1.0


def table() -> dict:
    if "table" not in _CACHE:
        _CACHE["table"] = json.loads(Path(__file__).with_name("makehuman_lm68.json").read_text())
    return _CACHE["table"]


def applies(base: dict) -> bool:
    head = base.get("head") or {}
    if (base.get("body") or {}).get("source") != "makehuman" or head.get("source", "gnm") != "gnm":
        return False
    f = head.get("follow_body")
    return bool(f) and float(f) > 0


def _amount(head: dict) -> float:
    f = head.get("follow_body")
    return 1.0 if f is True else float(f)


def body_points(params: dict) -> tuple:
    """(72, 3) landmark + cranium points of the MakeHuman head for these body params, in GNM's frame (x = the head's
    left, y up, z forward), interocular units round the eye midpoint; and the interocular in metres."""
    from . import makehuman
    t = table()
    b = makehuman.body({k: v for k, v in params.items() if k != "height"})
    P = np.asarray(b["P"], float)
    if len(P) != t["vertices"]:
        raise ValueError(f"MakeHuman's mesh has {len(P)} vertices, the landmark table was made for {t['vertices']}: "
                         "remake it (spikes/headfit/make_table.py)")
    el = np.array(b["face"]["landmarks"]["eye.L"], float)
    io = 2 * abs(el[0])
    mid = el * [0, 1, 1]
    X = P[t["lm68"] + [t["extra"][k] for k in CRANIUM] + t["dense_mh"]] - mid
    return np.c_[X[:, 0], X[:, 2], -X[:, 1]] / io, io


def _gnm():
    from . import base
    g = base._gnm_data()
    if "gnm" not in _CACHE:
        t = table()
        names = [str(n) for n in g["identity_names"]]
        comps = [i for i, n in enumerate(names) if n.startswith("head")][:N]
        rows = ([list(zip(r[0::2], r[1::2])) for r in g["lm68"]] + [[(t["gnm_extra"][k], 1.0)] for k in CRANIUM]
                + [[(v, 1.0)] for v in t["dense_gnm"]])
        V0 = g["template_vertex_positions"].astype(float)
        B = g["vertex_identity_basis"]
        L0 = np.array([sum(float(w) * V0[int(v)] for v, w in r) for r in rows])
        LB = np.array([[sum(float(w) * B[i][int(v)] for v, w in r) for r in rows] for i in comps], float)  # (n, 72, 3)
        _CACHE["gnm"] = {"names": names, "comps": comps, "L0": L0, "LB": LB,
                         "J0": g["template_joint_positions"].astype(float)[2:4],
                         "JB": np.array([g["joint_identity_basis"][i][2:4] for i in comps], float)}
    return _CACHE["gnm"]


AXES = ({"sex": 1.0}, {"sex": 0.0}, {"age": 8}, {"age": 80}, {"weight": 0.9}, {"weight": 0.15})


def _solve(d, c0, io_g, w):
    """The components' change that moves the fitted points by d (interoculars) from the identity c0."""
    g = _gnm()
    mb = g["JB"].mean(1)  # (n, 3): how each component moves the eye midpoint
    A = ((g["LB"] - mb[:, None, :]) * w[None, :, None]).reshape(len(c0), -1).T
    b = ((d * io_g) * w[:, None]).ravel()
    Ae = (g["JB"] * W_EYES).reshape(len(c0), -1).T
    M = np.vstack([A, Ae])
    rhs = np.r_[b, np.zeros(Ae.shape[0])]
    dc = np.linalg.solve(M.T @ M + LAM * np.eye(len(c0)), M.T @ rhs)
    for _ in range(6):  # components past the clip are fixed there and the rest solved again
        fixed = np.abs(c0 + dc) >= CLIP
        if not fixed.any():
            break
        dcf = np.where(fixed, np.clip(c0 + dc, -CLIP, CLIP) - c0, 0.0)
        free = ~fixed
        Mf = M[:, free]
        dc = dcf.copy()
        dc[free] = np.linalg.solve(Mf.T @ Mf + LAM * np.eye(int(free.sum())), Mf.T @ (rhs - M @ dcf))
    return dc


def _body_axes(w):
    """Orthonormal directions in identity space along which MakeHuman's sex, age and weight move a head (from the
    mean). A seeded identity is a random person, and random people lean male or female, old or young, as much as
    the body's own move does: a seed that happened to be heavy-jawed left the woman a man. The seed keeps what is
    its own (everything across these directions); the body sets sex, age and weight."""
    if "axes" not in _CACHE:
        g = _gnm()
        t = table()
        Xr, _ = body_points(t["reference"])
        io = float(abs(g["J0"][0][0] - g["J0"][1][0]))
        z = np.zeros(len(g["comps"]))
        D = np.array([_solve(body_points({**t["reference"], **ax})[0] - Xr, z, io, w) for ax in AXES]).T
        _CACHE["axes"] = np.linalg.qr(D)[0]
    return _CACHE["axes"]


def follow(base: dict, head: dict) -> dict:
    """The head dict with the body's shape in it: "identity" (the seeded identity + the solved move; the head's own
    identity entries win) and "scale" (unless given). Cached."""
    body = {k: v for k, v in (base.get("body") or {}).items() if k != "source"}
    amount = _amount(head)
    key = json.dumps([body, head.get("seed"), head.get("spread", 1.0), amount], sort_keys=True, default=float)
    if key not in _CACHE:
        from . import base as basemod
        g = _gnm()
        t = table()
        Xb, io_b = body_points(body)
        Xr, _ = body_points(t["reference"])
        d = (Xb - Xr) * amount  # the move, interocular units
        c0 = basemod._gnm_coeffs(g["names"], None, head.get("seed"), head.get("spread", 1.0))[g["comps"]]
        L = g["L0"] + np.tensordot(c0, g["LB"], 1)
        J = g["J0"] + np.tensordot(c0, g["JB"], 1)
        io_g = float(abs(J[0][0] - J[1][0]))
        w = np.r_[W_LM, np.full(len(CRANIUM), W_CRANIUM), np.full(len(t["dense_gnm"]), W_DENSE)]
        Q = _body_axes(w)
        c0 = c0 - Q @ (Q.T @ c0) * min(amount, 1.0)  # the seed without its own sex / age / weight
        L = g["L0"] + np.tensordot(c0, g["LB"], 1)
        J = g["J0"] + np.tensordot(c0, g["JB"], 1)
        io_g = float(abs(J[0][0] - J[1][0]))
        # the landmarks relative to the eye midpoint move by d x interocular; the eye centres stay where they are
        # (the interocular held: the scale carries the head's size)
        dc = _solve(d, c0, io_g, w)
        c = np.clip(c0 + dc, -CLIP, CLIP)
        Lf = g["L0"] + np.tensordot(c, g["LB"], 1)
        Jf = g["J0"] + np.tensordot(c, g["JB"], 1)
        io_f = float(abs(Jf[0][0] - Jf[1][0]))
        got = ((Lf - Jf.mean(0)) / io_f - (L - J.mean(0)) / io_g)
        # the rest as a warp: residual moves (m, GNM's frame) at the fitted points, lids and lips by their trust
        trust = np.r_[W_LM, np.ones(len(CRANIUM) + len(t["dense_gnm"]))]
        res = (d - got) * io_f * trust[:, None] * WARP
        sg = WARP_SIGMA * io_f
        D2 = ((Lf[:, None, :] - Lf[None, :, :]) ** 2).sum(-1)
        K = np.exp(-D2 / (2 * sg * sg))
        coef = np.linalg.solve(K + WARP_RIDGE * np.eye(len(Lf)), res)
        after = got + (K @ coef) / io_f
        rms = lambda e: round(float(np.sqrt((e ** 2).sum(1).mean())), 4)
        _CACHE[key] = {"identity": {g["names"][i]: round(float(v), 4) for i, v in zip(g["comps"], c)},
                       "scale": round(io_b / io_f, 5),
                       "warp": {"at": np.round(Lf, 6).tolist(), "coef": np.round(coef, 7).tolist(), "sigma": round(sg, 6)},
                       "report": {"asked_io": rms(d), "left_identity_io": rms(got - d), "left_io": rms(after - d),
                                  "clipped": int((np.abs(c0 + dc) > CLIP).sum()), "max": round(float(np.abs(c).max()), 2)}}
    f = _CACHE[key]
    out = dict(head)
    out["identity"] = {**f["identity"], **(head.get("identity") or {})}
    out.setdefault("scale", f["scale"])
    out["plane_follows_chin"] = True
    out["warp"] = f["warp"]
    return out


def report(base: dict) -> dict:
    """How far the head followed: the move asked and what the identity space left undone (rms, interocular units)."""
    head = base.get("head") or {}
    if not applies(base):
        return {}
    follow(base, head)
    body = {k: v for k, v in (base.get("body") or {}).items() if k != "source"}
    return _CACHE[json.dumps([body, head.get("seed"), head.get("spread", 1.0), _amount(head)],
                             sort_keys=True, default=float)]["report"]
