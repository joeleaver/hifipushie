"""Model extensions from MakeHuman's CC0 face targets (facesliders, 2026-10-09; Joe / the coordinator: where GNM's
identity can't reach a feature, ADD TO THE MODEL: a data-backed shape, not a one-off morph).

Each extension is a MakeHuman target pair (incr / decr, or up / down) carried onto GNM's head and stripped of what
GNM's identity can already make:
1. carry: MakeHuman's displacement (its base mesh, dm, Y up) is read at each GNM vertex's binding point on
   MakeHuman's reference body (onemesh's g_tri / g_bary, the same binding the one mesh is built on), turned into
   world metres and into GNM's frame (a similarity fitted between GNM's template and its bound positions g_neutral);
   +1 = half the incr - decr difference (the slider is linear: one field per side);
2. project out GNM: the least-squares identity move (GNM's 120 head components, over the head's skin) that best makes
   the field is subtracted, so what is left is ORTHOGONAL to the identity: the extension adds only what the model
   could not express (its share of the target is stored as "explained");
3. made mirror symmetric, held to the head's exterior skin, extended over the lids' loops.

`build()` writes face_ext.npz {name: (n, 3) metres at +1, "<name>__explained": share}; faceslide registers each as
a residual slider (UNITS, fields), split at the centre line like the mouth's. The MakeHuman targets: CC0, commit
a8bc2d54 of makehumancommunity/makehuman (assets "makehuman_face" / spikes/facesliders/mh_targets SOURCE.txt).
"""
from __future__ import annotations

import os
from pathlib import Path

import numpy as np

TABLE = Path(__file__).with_name("face_ext.npz")
TARGETS = Path(os.environ.get("HIFIPUSHIE_MH_FACE", "/mnt/data/hifipushie/facesliders/mh_targets"))
# slider name -> (group, + target, - target, what + means)
EXT = {
    "mh_lowerlip_width": ("mouth", "mouth-lowerlip-width-incr", "mouth-lowerlip-width-decr",
                          "the lower lip's vermilion wider to the corners; - = a short central cushion (MakeHuman)"),
    "mh_mouth_angles": ("mouth", "mouth-angles-up", "mouth-angles-down",
                        "the mouth's corners up; - = down-turned corners (MakeHuman)"),
    "mh_lowerlip_ext": ("mouth", "mouth-lowerlip-ext-up", "mouth-lowerlip-ext-down",
                        "the lower lip's outer ends up toward the corners; - = down (MakeHuman)"),
}
REGION = 0.03      # of the target's largest move: its region (the extension lives there)
_C: dict = {}


def _target(group: str, name: str) -> tuple:
    p = TARGETS / group / f"{name}.target"
    if not p.exists():
        raise FileNotFoundError(f"faceext: MakeHuman target {p} missing (CC0, makehumancommunity/makehuman a8bc2d54 "
                                f"makehuman/data/targets/{group}/; see spikes/facesliders/mh_targets SOURCE.txt)")
    rows = [ln.split() for ln in p.read_text().splitlines() if ln.strip() and not ln.startswith("#")]
    idx = np.array([int(r[0]) for r in rows], int)
    d = np.array([[float(x) for x in r[1:4]] for r in rows], float)
    return idx, np.c_[d[:, 0], -d[:, 2], d[:, 1]] * 0.1   # dm, Y up, facing +Z -> m, Z up, facing -Y


def _frame():
    """(R, s, t): world (MakeHuman's reference body) = s * gnm @ R.T + t, fitted on GNM's bound vertices."""
    if "frame" not in _C:
        from . import base as basemod, onemesh
        a = onemesh.asset()
        val = np.asarray(a["g_valid"], bool)
        A = basemod._gnm_data()["template_vertex_positions"].astype(float)[val]
        B = np.asarray(a["g_neutral"], float)[val]
        ca, cb = A.mean(0), B.mean(0)
        U, S, Vt = np.linalg.svd((B - cb).T @ (A - ca))
        D = np.diag([1.0, 1.0, np.sign(np.linalg.det(U @ Vt))])
        R = U @ D @ Vt
        s = float(np.trace(np.diag(S) @ D) / ((A - ca) ** 2).sum())
        _C["frame"] = (R, s, cb - s * ca @ R.T)
    return _C["frame"]


def carry(group: str, name: str) -> np.ndarray:
    """(17821, 3) a MakeHuman target's displacement at GNM's raw vertices, GNM's frame (0 where unbound)."""
    from . import onemesh
    a = onemesh.asset()
    idx, d = _target(group, name)
    n_mh = int(max(a["g_tri"].max(), idx.max())) + 1
    D = np.zeros((n_mh, 3))
    D[idx] = d
    tri, bar = np.asarray(a["g_tri"], int), np.asarray(a["g_bary"], float)
    dw = (bar[:, :, None] * D[tri]).sum(1) * np.asarray(a["g_valid"], bool)[:, None]
    R, s, _ = _frame()
    return dw @ R / s


def identity_basis() -> tuple:
    """(B (120, 3m), skin index (m,)): GNM's head identity components over the head's exterior skin vertices."""
    if "ib" not in _C:
        from . import base as basemod
        g = basemod._gnm_data()
        names = [str(x) for x in g["identity_names"]]
        comps = [i for i, x in enumerate(names) if x.startswith("head")][:120]
        sk = np.flatnonzero(np.asarray(g["groups"]["skin_exterior"], float) > 0.5)
        IB = np.asarray(g["vertex_identity_basis"])[comps][:, sk].astype(float)
        _C["ib"] = (IB.reshape(len(comps), -1), sk)
    return _C["ib"]


def project_out(d: np.ndarray) -> tuple:
    """(the field minus its least-squares identity part, the share of the field the identity explains)."""
    B, sk = identity_basis()
    y = d[sk].ravel()
    c = np.linalg.lstsq(B.T, y, rcond=None)[0]
    part = (B.T @ c).reshape(-1, 3)
    out = d.copy()
    out[sk] -= part
    return out, float(np.linalg.norm(part) / max(np.linalg.norm(y), 1e-15))


def local_orthogonal(d: np.ndarray, region: np.ndarray) -> np.ndarray:
    """The field closest to d that is zero outside `region` (its own support) AND orthogonal to the identity span
    (B x = 0): x_r = d_r - B_r^T (B_r B_r^T)^-1 B_r d_r over the region's skin vertices. Local and orthogonal at once
    (projecting over the whole head left the identity's global side effects all over it; cutting that back to the
    region brought ~half the identity part back)."""
    B, sk = identity_basis()
    on = region[sk]
    Br = B.reshape(B.shape[0], -1, 3)[:, on].reshape(B.shape[0], -1)
    y = d[sk][on].ravel()
    lam = 1e-9 * np.trace(Br @ Br.T) / len(Br)
    x = y - Br.T @ np.linalg.solve(Br @ Br.T + lam * np.eye(len(Br)), Br @ y)
    out = np.zeros_like(d)
    out[sk[on]] = x.reshape(-1, 3)
    return out


CORNER_HOLD = (0.0015, 0.004)   # m: the mouth's corners held within the first, released over the second
CHEAP = float(os.environ.get("HIFIPUSHIE_EXT_CHEAP", "4e-4"))   # m rms over the region a 1-sigma identity move
# makes along a direction: CHEAP and up = a probable move (a few sigmas make a mm)


def cheap_basis(region: np.ndarray) -> tuple:
    """(V (k, 3r) orthonormal field directions over the region's skin, s (k,)): the directions of the region's field
    the identity makes CHEAPLY (each sigma of identity moves the region by s_i >= CHEAP along v_i: the singular
    vectors of the identity basis restricted to the region)."""
    B, sk = identity_basis()
    on = region[sk]
    Br = B.reshape(B.shape[0], -1, 3)[:, on].reshape(B.shape[0], -1)
    U, S, Vt = np.linalg.svd(Br, full_matrices=False)
    keep = S / np.sqrt(max(int(on.sum()), 1)) >= CHEAP
    return Vt[keep], S[keep], sk[on]


def minus_probable(d: np.ndarray, region: np.ndarray) -> tuple:
    """(the target with its components along the identity's CHEAP directions over its region removed, the share
    removed, the number of such directions). GNM's 120 components can reproduce these local targets almost exactly
    (0.87-0.94) but only at 46-124 sigmas (spikes/facesliders/extcost.py): expressible, not probable. Projecting all
    of it out (local_orthogonal) left 0.3-0.5 mm of 3-5 mm targets; removing only what a few sigmas of identity make
    (directions moving the region >= CHEAP a sigma) leaves the extension what the population would not do: the
    solve then chooses between the identity (with its couplings) and the residual (local), and the two never
    double count (the extension is exactly orthogonal to the cheap directions)."""
    V, S, rows = cheap_basis(region)
    y = d[rows].ravel()
    made = V.T @ (V @ y)
    out = np.zeros_like(d)
    out[rows] = (y - made).reshape(-1, 3)
    return out, float(np.linalg.norm(made) / max(np.linalg.norm(y), 1e-15)), int(len(S))


def _turned(D) -> int:
    from . import faceslide, gnmloops
    T = faceslide.template()
    Q = gnmloops.plan()["quads"]
    Q = Q[T["skin"][Q].all(1)]
    X0 = T["X"]

    def nrm(X):
        n = np.cross(X[Q[:, 2]] - X[Q[:, 0]], X[Q[:, 3]] - X[Q[:, 1]])
        return n / np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-18)
    area = 0.5 * np.linalg.norm(np.cross(X0[Q[:, 2]] - X0[Q[:, 0]], X0[Q[:, 3]] - X0[Q[:, 1]]), axis=1)
    return int(((np.einsum("ij,ij->i", nrm(X0), nrm(X0 + D)) < 0) & (area > 1.5e-7)).sum())


def fold_free(d, margin: float = 0.8) -> float:
    """The slider's scale: 1 (MakeHuman's half difference) unless the field turns template quads over at -1 / +1
    (GNM's lip rows are thinner than MakeHuman's), then `margin` x the largest fold-free fraction."""
    if not (_turned(d) or _turned(-d)):
        return 1.0
    lo, hi = 0.0, 1.0
    for _ in range(14):
        mid = 0.5 * (lo + hi)
        lo, hi = (mid, hi) if not (_turned(mid * d) or _turned(-mid * d)) else (lo, mid)
    return margin * lo


def build(names=None) -> dict:
    from . import base as basemod, faceslide, gnmloops
    g = basemod._gnm_data()
    T = faceslide.template()
    mi = T["mirror"]
    ext = np.asarray(g["groups"]["skin_exterior"], float) > 0.5
    out = dict(np.load(TABLE)) if TABLE.exists() else {}
    for k in names or EXT:
        grp, plus, minus, _ = EXT[k]
        d = 0.5 * (carry(grp, plus) - (carry(grp, minus) if minus else 0.0))
        d = d * ext[:, None]
        if grp == "mouth":   # the commissures held (GNM's corner is not MakeHuman's: its moves there, on the face's
            # shortest edges, turned the corner quads over at -1); before the projection, which it must not undo
            Xr = T["X"][:len(d)]
            dc = np.min([np.linalg.norm(Xr - T["lm"][i], axis=1) for i in (48, 54, 60, 64)], axis=0)
            d = d * faceslide._ss((dc - CORNER_HOLD[0]) / CORNER_HOLD[1])[:, None]
        m = np.linalg.norm(d, axis=1)
        d, share, cn = minus_probable(d, m > REGION * m.max())
        d = gnmloops.ext(d)
        d = 0.5 * (d + d[mi] * [-1.0, 1.0, 1.0])
        sc = fold_free(d)
        d = d * sc
        out[f"{k}__scale"] = np.array(sc)
        out[k] = d.astype(np.float32)
        out[f"{k}__explained"] = np.array(share)
        out[f"{k}__cheap_dirs"] = np.array(cn)
        B, sk = identity_basis()
        raw = d[:len(ext)]
        out[f"{k}__identity_left"] = np.array(float(np.linalg.norm(np.linalg.lstsq(B.T, raw[sk].ravel(), rcond=None)[0] @ B)
                                                    / max(np.linalg.norm(raw[sk]), 1e-15)))
    np.savez(TABLE, **out)
    _C.pop("table", None)
    return out


def table() -> dict:
    if "table" not in _C:
        _C["table"] = dict(np.load(TABLE)) if TABLE.exists() else {}
    return _C["table"]
