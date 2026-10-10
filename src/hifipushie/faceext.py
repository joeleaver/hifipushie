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
    "mh_lowerlip_volume": ("mouth", "mouth-lowerlip-volume-incr", "mouth-lowerlip-volume-decr",
                           "the lower lip fuller (its pad forward and down: the pout's shadow under it); - = thinner "
                           "(MakeHuman; faces2 2026-10-10, for the lip stage's shading)"),
    "mh_lowerlip_middle": ("mouth", "mouth-lowerlip-middle-up", "mouth-lowerlip-middle-down",
                           "the lower lip's middle fuller: its border dips at the centre (-0.8 mm) and rises toward "
                           "the sides (+0.4 mm at half width), the skin under it following: a central pad; - = a flat, "
                           "even lower lip (MakeHuman 'lowerlip-middle'; faces3 2026-10-10, the central pad lever)"),
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


CORNER_HOLD = (0.003, 0.025)   # m: the mouth's corners held within the first; the hold's correction is biharmonic out
# to the second (faces3: a smoothstep release over 5 mm put a 2 mm step beside the corners: a groove under them in the
# 3/4 view at -1 of lowerlip_width, and the folds past it)


def corner_hold(d: np.ndarray, dc: np.ndarray) -> np.ndarray:
    """d with the mouth's corners held: a correction e = -d within CORNER_HOLD[0] of a corner landmark, 0 from
    CORNER_HOLD[1] out, biharmonic (the squared mesh Laplacian over GNM's quads) between: the hold spreads as smoothly
    as the mesh allows instead of a ramp."""
    import scipy.sparse as sp
    from scipy.sparse.linalg import spsolve
    smooth(np.zeros((len(d), 1)), 0)
    W = _C["adj"]                       # row-normalised adjacency (GNM's raw quads)
    fixed_in = dc <= CORNER_HOLD[0]
    free = (dc > CORNER_HOLD[0]) & (dc < CORNER_HOLD[1])
    e = np.zeros_like(d)
    e[fixed_in] = -d[fixed_in]
    if free.any():
        L = (sp.eye(len(d)) - W).tocsr()
        L = (L.T @ L).tocsr()   # biharmonic: a harmonic hold dimpled round the held disc (log-like, steep at its
        # edge: a crescent groove beside each corner in the renders); the thin-plate one is smooth through it
        Lff = L[free][:, free].tocsc()
        rhs = -(L[free][:, fixed_in] @ e[fixed_in])
        e[free] = np.column_stack([spsolve(Lff, rhs[:, k]) for k in range(d.shape[1])])
    return d + e
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
    """Skin quads of the template turned over by D, + neighbouring pairs folded (normals > 60 deg apart and 10 deg
    more than in the template): test_faceslide's criteria."""
    from . import faceslide, gnmloops
    if "fold" not in _C:
        T = faceslide.template()
        Q = gnmloops.plan()["quads"]
        Q = Q[T["skin"][Q].all(1)]
        ef = {}
        for qi, q in enumerate(Q):
            for k in range(4):
                ef.setdefault(tuple(sorted((int(q[k]), int(q[(k + 1) % 4])))), []).append(qi)
        _C["fold"] = (T["X"], Q, np.array([v for v in ef.values() if len(v) == 2]))
    X0, Q, pairs = _C["fold"]

    def nrm(X):
        n = np.cross(X[Q[:, 2]] - X[Q[:, 0]], X[Q[:, 3]] - X[Q[:, 1]])
        return n / np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-18)
    n0, n1 = nrm(X0), nrm(X0 + D)
    ang = lambda a: np.degrees(np.arccos(np.clip(a, -1, 1)))  # noqa: E731
    a0 = np.einsum("ij,ij->i", n0[pairs[:, 0]], n0[pairs[:, 1]])
    a1 = np.einsum("ij,ij->i", n1[pairs[:, 0]], n1[pairs[:, 1]])
    fold = (a1 < np.cos(np.radians(60))) & (ang(a1) - ang(a0) > 10)
    return int((np.einsum("ij,ij->i", n0, n1) < 0).sum() + fold.sum())


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


SMOOTH = 12          # Laplacian passes over GNM's skin (raw quads): MakeHuman's coarser mesh, read through its
# triangles, kinks the field from row to row: across the vermilion border (already 67 deg) 0.25 mm folded neighbours


def smooth(d: np.ndarray, n: int = SMOOTH) -> np.ndarray:
    from . import base as basemod
    import scipy.sparse as sp
    if "adj" not in _C:
        q = np.asarray(basemod._gnm_data()["quads"])
        e = np.r_[q[:, [0, 1]], q[:, [1, 2]], q[:, [2, 3]], q[:, [3, 0]]]
        m = len(basemod._gnm_data()["template_vertex_positions"])
        A = sp.coo_matrix((np.ones(len(e)), (e[:, 0], e[:, 1])), (m, m)).tocsr()
        A = ((A + A.T) > 0).astype(float)
        deg = np.asarray(A.sum(1)).ravel()
        _C["adj"] = sp.diags(1 / np.maximum(deg, 1)) @ A
    W = _C["adj"]
    for _ in range(n):
        d = 0.5 * d + 0.5 * (W @ d)
    return d


def build(names=None) -> dict:
    from . import base as basemod
    ext = np.asarray(basemod._gnm_data()["groups"]["skin_exterior"], float) > 0.5
    out = dict(np.load(TABLE)) if TABLE.exists() else {}
    for k in names or EXT:
        d, share, cn = field(k)
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


def field(k: str) -> tuple:
    """(extension k's field at +1 before its fold-free scale (template vertices incl. the loops), the share the
    identity's cheap directions made, their number)."""
    from . import base as basemod, faceslide, gnmloops
    g = basemod._gnm_data()
    T = faceslide.template()
    mi = T["mirror"]
    ext = np.asarray(g["groups"]["skin_exterior"], float) > 0.5
    if True:  # (one extension)
        grp, plus, minus, _ = EXT[k]
        d = 0.5 * (carry(grp, plus) - (carry(grp, minus) if minus else 0.0))
        d = smooth(d * ext[:, None])
        if grp == "mouth":   # the commissures held (GNM's corner is not MakeHuman's: its moves there, on the face's
            # shortest edges, turned the corner quads over at -1); before the projection, which it must not undo
            Xr = T["X"][:len(d)]
            dc = np.min([np.linalg.norm(Xr - T["lm"][i], axis=1) for i in (48, 54, 60, 64)], axis=0)
            d = corner_hold(d, dc)
            d = hold_rolls(d)
        m = np.linalg.norm(d, axis=1)
        reg = m > REGION * m.max()
        d, share, cn = minus_probable(d, reg)
        n = len(d)
        for it in range(3 if HOLD_CREASES else 1):
            if it:   # the holds put back a little of what the cheap directions make: alternate (3 rounds: < 3%)
                d = minus_probable(d[:n], reg)[0]
            if grp == "mouth" and HOLD_ROLLS:
                d = hold_rolls(d)
            d = gnmloops.ext(d[:n])
            d = 0.5 * (d + d[mi] * [-1.0, 1.0, 1.0])
            if HOLD_CREASES:
                d = hold_creases(d)
                d = 0.5 * (d + d[mi] * [-1.0, 1.0, 1.0])
    return d, share, cn


HOLD_ROLLS = not os.environ.get("HIFIPUSHIE_EXT_SHEAR_ROLLS")
HOLD_CREASES = float(os.environ.get("HIFIPUSHIE_EXT_CREASE", "45"))   # deg: template creases sharper than this
# move rigidly (0 = off)
CREASE_R = 0.003   # m: each crease vertex's neighbourhood (the rigid motion's fit and its reach)


def _pair_angle(X, Q, pairs):
    def nrm(Y):
        n = np.cross(Y[:, 2] - Y[:, 0], Y[:, 3] - Y[:, 1])
        return n / np.maximum(np.linalg.norm(n, axis=-1, keepdims=True), 1e-18)
    return np.arccos(np.clip(np.einsum("ij,ij->i", nrm(X[Q[pairs[:, 0]]]), nrm(X[Q[pairs[:, 1]]])), -1, 1))


def hold_creases(d: np.ndarray, sharp: float | None = None) -> np.ndarray:
    """The field made locally RIGID across the template's creases (pairs of skin quads whose normals are `sharp` to
    150 deg apart, where the field moves): around each crease vertex the small rigid motion (t + w x (x - c),
    linearised) is fitted to the field over its neighbours within CREASE_R and replaces it there, fully at the vertex,
    easing out to the neighbourhood's edge (overlapping neighbourhoods averaged; no extrapolation past them). Only
    rigid motions keep a crease's angle: a shear or an along-the-crease stretch turns its two sides against each other.
    Why (faces3, borderdiag.py): the carried MakeHuman mouth targets folded at 0.5-0.8 mm, not at the vermilion border
    but in the lips' inner roll (57-72 deg creases of 1-2 mm quads, inside the contact ring) near the corners, where
    the field's along-the-lip gradient sheared the roll's rows. The rows now move together, carried and turned,
    never sheared; away from creases the field is untouched."""
    sharp = HOLD_CREASES if sharp is None else sharp
    if not sharp:
        return d
    _turned(np.zeros_like(d))
    X0, Q, pairs = _C["fold"]
    if len(d) != len(X0):
        return d
    key = ("crease", round(sharp, 3))
    if key not in _C:
        a = np.degrees(_pair_angle(X0, Q, pairs))
        cv = np.unique(Q[pairs[(a > sharp) & (a < 150)]].ravel())
        from scipy.spatial import cKDTree
        _C[key] = (cv, cKDTree(X0).query_ball_point(X0[cv], CREASE_R))
    cv, near = _C[key]
    m = np.linalg.norm(d, axis=1)
    moving = np.flatnonzero(m[cv] > 1e-3 * max(m.max(), 1e-15))
    acc = np.zeros_like(d)
    wsum = np.zeros(len(d))
    for i in moving:
        nb = np.asarray(near[i], int)
        if len(nb) < 4:
            continue
        r = np.linalg.norm(X0[nb] - X0[cv[i]], axis=1)
        c = X0[nb].mean(0)
        P = X0[nb] - c
        A = np.zeros((3 * len(nb), 6))   # d_k = t + w x p_k = t - [p_k]x w
        A[:, :3] = np.tile(np.eye(3), (len(nb), 1))
        A[0::3, 4], A[0::3, 5] = P[:, 2], -P[:, 1]
        A[1::3, 3], A[1::3, 5] = -P[:, 2], P[:, 0]
        A[2::3, 3], A[2::3, 4] = P[:, 1], -P[:, 0]
        sol = np.linalg.lstsq(A, d[nb].ravel(), rcond=None)[0]
        rig = sol[:3] + np.cross(sol[3:], P)
        x = np.clip(1.0 - r / CREASE_R, 0.0, 1.0)
        w = x * x * (3 - 2 * x)
        np.add.at(acc, nb, w[:, None] * (rig - d[nb]))
        np.add.at(wsum, nb, w)
    return d + acc / np.maximum(wsum, 1.0)[:, None]
def hold_rolls(d: np.ndarray) -> np.ndarray:
    """The lips' inner rolls (the rings inside the contact ring, out of sight behind the closed lips) moved whole with
    their own lip's contact ring: each takes the move of the nearest contact-ring vertex of the same lip (GNM's
    upper_lip / lower_lip groups). Where the folds were (faces3, borderdiag.py): not the vermilion border but the
    rolls' rows (template creases 57-72 deg on quads a few tenths of a mm across): MakeHuman's field read there
    sheared them 0.03-0.25 mm and folded every mouth extension at 0.5-0.8 mm. Moving the rows together keeps them
    unsheared (faceslide's seal moves the rolls whole by the same rule)."""
    if not HOLD_ROLLS:
        return d
    from . import faceslide
    if "rolls" not in _C:   # per ring inward: each vertex's sources = its neighbours one ring further out (its
        # own lip's where it has any): the move carried down the roll's columns, not across them
        R = faceslide._lip_rings()
        up = np.asarray(R["upper"], bool)
        steps = []
        for k in range(R["contact"] - 1, -1, -1):
            outer = set(int(u) for u in R["rings"][k + 1])
            rows, cols = [], []
            for v in R["rings"][k]:
                nb = [u for u in R["adj"].get(int(v), []) if u in outer]
                nb = [u for u in nb if up[u] == up[v]] or nb
                if nb:
                    rows += [int(v)] * len(nb)
                    cols += nb
            steps.append((np.array(rows), np.array(cols)))
        _C["rolls"] = steps
    d = d.copy()
    for rows, cols in _C["rolls"]:
        acc = np.zeros((len(d), 3))
        cnt = np.zeros(len(d))
        np.add.at(acc, rows, d[cols])
        np.add.at(cnt, rows, 1.0)
        on = cnt > 0
        d[on] = acc[on] / cnt[on, None]
    return d


def table() -> dict:
    if "table" not in _C:
        _C["table"] = dict(np.load(TABLE)) if TABLE.exists() else {}
    return _C["table"]
