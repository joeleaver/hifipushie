"""The HANG stage of a garment fit as a short ZOZO settle under gravity, run on this machine (PROVISIONAL, Joe
2026-10-28: "We can provisionally use ZOZO, keep using it on the laptop for now, while we're figuring this out").

Design: our pattern + fit place the garment (pattern-aware, threads hard, per-piece misfit reads); ZOZO
(cloth_zozo.py, the release's own runner) settles it under gravity for SETTLE_S seconds, held ONLY by real supports
(the body's contact and friction; no pins, holds or carried pieces); our gates read the result. One code path, the
same settings for every garment; every number comes from the fabric table (cloth_job.PHYSICAL), the fit's own thread
model (pattern_form.FIT_THREAD_CAP, SHEAR_LOCK_DEG) or the runner's documented defaults. Selected by
pattern_form.HANG_SOLVER / garment key "hang_solver" = "zozo" (the old quasi-static hang stays "ours" for A/B).

The four handoff rules (the reference run, docs/state/zozo_ref.md, needed four workarounds; each is a rule here):
1. START STRAIN: ZOZO's strain limit is ISOTROPIC (the largest principal stretch, strain_toi.kernel.cpp
   shell_max_strain), while its Baraff-Witkin membrane already takes stretch along the threads (uv) apart from shear.
   A woven's threads cap ~2 % but its bias shears freely to the weave's jamming angle, and a sheared square's largest
   principal stretch is (1 + cap) sqrt(1 + sin(shear)): the most a woven can take is woven_limit() = (1 + cap)
   sqrt(1 + sin(lock)) - 1 (2 %, 35 deg: 27.9 %). That is the strain limit for wovens (a knit keeps its fabric's own
   limit, cloth.strain_limit_of). The limit then forbids only what the weave can't do; the threads are held by the
   membrane's stretch stiffness (fabric table) and READ after the settle (threads past cap p99, as fit_garment reads
   it). No local loosening (the reference's releaseIdx "lift").
2. CLEARANCE, DERIVED (round 2): an edge of length L lying on a surface of convex radius R dips by its chord sag
   (sagitta ~ L^2 / 8R), so a vertex at the solver's standoff is not enough: each vertex's contact plane lies at
   CLEARANCE (the runner's body_offset + contact_gap) + the sag of its longest incident SETTLED edge over the
   collider's tightest convex radius at its foot (Clearance; pattern_form on_form -> assemble(skin=...) and
   hard_threads via res["hard_skin_v"]). A coarse settle counts the coarse mesh's edges (settle_edge_len), so the
   coarse start needs no push-out either. What the linearised planes leave inside is REPORTED, never pushed.
3. MADE PIECES (collar, stand, cuffs, bands; cloth.made_pieces): rest as MADE = their intended worn shape from the
   draft (round 4, C252: made_rest, the placement's made shape: laid on the wrap, folded at the declared lines, the
   drape band's worn mesh), sent as in.npz "rest"; not as the fit left them (round 3: the fit's crumples became rest).
   The fabric table's interfacing bending (PHYSICAL interfacing_bend) on interfaced vertices.
   The start passes ZOZO's two frame-0 tests in the pre-flight: contact (legality, C249) and start strain
   (start_strain, C252: no face at or past its own limit, as the runner sets it).
4. FOLDS: every declared fold line (folds.py: hems, plackets, folded bands, a collar's fall line, cuff turn-backs)
   carries its bending REST ANGLE (folds.bend_reference: the flat pattern folded at its lines) and the pressed rows'
   stiffer bending (the runner's fold_press); made pieces rest folded as made.
Seams: ZOZO keeps a seam's two edges a contact gap apart (the ~1.3 mm light lines): the sewn vertices are WELDED after
the settle (cloth.cleanup's weld only: each sewn group at its mean, no smoothing, no push), as every ZOZO result is.
Coarse vs fine: settle(coarse=m) settles a coarse mesh of the same pattern (cloth.build place_only at m) started from
the fit carried over by pattern position, and carries the result back onto the fit's mesh the same way.
The fit's pattern gate decides (fit_garment refuses an unpassed pattern unless force=True, "only to look"); settle()
refuses unless told the gate passed or look=True."""
from __future__ import annotations

import json
import math
import os
import time
from pathlib import Path

import numpy as np

BODY_OFFSET = 0.002  # m: cloth_zozo's default body contact offset (job "body_offset")
CONTACT_GAP = 0.001  # m: cloth_zozo's default contact gap (job "contact_gap")
CLEARANCE = BODY_OFFSET + CONTACT_GAP  # m: the fit's contact planes and the solver's standoff, one number
SETTLE_S = 6.0  # s of settling (the reference: 144 frames at 24 fps)
FPS = 24
COARSE = 0.03  # m: the design loop's coarse settle (settle(coarse=COARSE))
ROOT = Path(os.environ.get("HIFIPUSHIE_ZOZO_HANG_DIR", "/mnt/data/hifipushie/zhang/jobs"))


def woven_limit(cap: float | None = None, lock_deg: float | None = None) -> float:
    """The largest principal stretch a woven can take, as a strain: threads at their cap, bias sheared to the jam."""
    from . import pattern_form as pf
    cap = pf.FIT_THREAD_CAP if cap is None else cap
    lock = pf.SHEAR_LOCK_DEG if lock_deg is None else lock_deg
    return (1.0 + cap) * math.sqrt(1.0 + math.sin(math.radians(lock))) - 1.0


def strain_limit(g: dict, B: dict | None) -> float:
    """ZOZO's strain limit for this garment: a knit's own (cloth.strain_limit_of), a woven's woven_limit()."""
    from . import cloth, pattern_form as pf
    lim_ = float((B or {}).get("stretch_limit") or 0.0)
    if lim_ > pf.KNIT_LIMIT:
        return cloth.strain_limit_of(g)
    return max(woven_limit(), cloth.strain_limit_of(g))


def vertex_normals(V: np.ndarray, T: np.ndarray) -> np.ndarray:
    V, T = np.asarray(V, float), np.asarray(T, np.int64)
    fn = np.cross(V[T[:, 1]] - V[T[:, 0]], V[T[:, 2]] - V[T[:, 0]])
    n = np.zeros_like(V)
    for k in range(3):
        np.add.at(n, T[:, k], fn)
    return n / np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-20)


def convex_radius_at(V, N, kd, P: np.ndarray, L: np.ndarray) -> np.ndarray:
    """The collider's tightest CONVEX radius around each point P, read at the chord's own scale L: every collider vertex
    q within L of P's nearest vertex p (lateral a, fall f = -n_p.(q - p) below p's tangent plane) implies the sphere
    through both, R = (a^2 + f^2) / 2f; the smallest over q with a >= L/4 (nearer ones are the mesh's own noise), or the
    6 nearest if none lie that far. inf where nothing falls away (flat or concave: a chord bridges it)."""
    _, near = kd.query(P)
    R = np.full(len(P), np.inf)
    for k, nb in enumerate(kd.query_ball_point(V[near], L + 1e-9)):
        p, n = V[near[k]], N[near[k]]
        d = V[nb] - p if nb else np.zeros((0, 3))
        ok = np.linalg.norm(d, axis=1) >= 0.25 * L[k] if len(d) else np.zeros(0, bool)
        if not ok.any():
            _, nb = kd.query(p, k=7)
            d = V[np.asarray(nb)[1:]] - p
            ok = np.ones(len(d), bool)
        d = d[ok]
        f = -(d @ n)
        a2 = np.maximum((d * d).sum(1) - f * f, 0.0)
        m = f > 1e-9
        if m.any():
            R[k] = float(((a2[m] + f[m] ** 2) / (2 * f[m])).min())
    return R


def edge_len_v(M: dict) -> np.ndarray:
    """Per cloth vertex: its longest incident edge at rest (the pattern, metres)."""
    uv, F = np.asarray(M["uv"], float), np.asarray(M["F"], np.int64)
    L = np.zeros(len(uv))
    for a, b in ((0, 1), (1, 2), (2, 0)):
        d = np.linalg.norm(uv[F[:, a]] - uv[F[:, b]], axis=1)
        np.maximum.at(L, F[:, a], d)
        np.maximum.at(L, F[:, b], d)
    return L


def sagitta(L, R):
    """How far a chord of length L across a convex surface of radius R dips below it: R - sqrt(R^2 - L^2 / 4) (~ L^2 / 8R;
    a chord longer than the bump's diameter clears it by at most R)."""
    L, R = np.asarray(L, float), np.asarray(R, float)
    with np.errstate(invalid="ignore"):
        s = R - np.sqrt(np.maximum(R * R - 0.25 * L * L, 0.0))
    return np.where(np.isfinite(R), np.where(L >= 2 * R, R, s), 0.0)


class Clearance:
    """THE LEGAL START, derived (zozo hang round 2): per cloth vertex, how far off the collider its contact plane lies so
    no edge of it comes nearer the collider than the solver's standoff: CLEARANCE (body offset + contact gap) + the chord
    sag (sagitta) of its longest incident settled edge L over the collider's tightest convex radius where the vertex
    is NOW (convex_radius_at, read at the chord's scale). colliders: [(V, T), ...] (the body; the garment under).
    Called as clr(X_v, v) -> metres for the vertices v at X_v (the fit's contact planes, re-taken as the cloth moves)."""

    def __init__(self, L: np.ndarray, colliders: list):
        from scipy.spatial import cKDTree
        self.L = np.asarray(L, float)
        self.cols = []
        for V, T in colliders:
            V = np.asarray(V, float)
            self.cols.append((V, vertex_normals(V, T), cKDTree(V)))

    def radius(self, Xv: np.ndarray, v: np.ndarray) -> np.ndarray:
        R = np.full(len(v), np.inf)
        for V, N, kd in self.cols:
            R = np.minimum(R, convex_radius_at(V, N, kd, Xv, self.L[v]))
        return R

    def __call__(self, Xv: np.ndarray, v: np.ndarray) -> np.ndarray:
        v = np.asarray(v, np.int64)
        if not len(v):
            return np.zeros(0)
        return CLEARANCE + sagitta(self.L[v], self.radius(np.asarray(Xv, float), v))


def clearance(X: np.ndarray, L: np.ndarray, colliders: list) -> np.ndarray:
    """Clearance(L, colliders) for every vertex at X (metres per vertex)."""
    return Clearance(L, colliders)(X, np.arange(len(X)))


# THE SOLVER'S OWN LEGALITY TEST (zozo hang round 3, C249; coordinator: "stop approximating"). ZOZO assembles three
# cloth / collision-mesh pair kinds (crates/ppf-cts-solver/src/kernels/contact/collision_narrow.kernel.cpp): a cloth
# VERTEX against a collider TRIANGLE (point-triangle), a collider VERTEX against a cloth TRIANGLE (triangle-point), a cloth
# EDGE against a collider EDGE (edge-edge). Each pair's separation is the exact closest-point vector; its offset is the
# two elements' contact-offsets summed (cloth tri default 0, datamodel/params.rs; the body BODY_OFFSET, cloth_zozo
# "body_offset"); embed_collision refuses the run ("contact starts overlapping") when !(d^2 > offset^2), i.e. d <= offset.
# The barrier acts within offset + ghat (ghat = the mean of the two contact-gaps: CONTACT_GAP both sides). LEGAL = every
# pair d > BODY_OFFSET (the pre-flight's refusal). The fit's last contact pass holds every pair at REACH = offset + ghat
# (= CLEARANCE): ZOZO's own advice, "give the initial geometry a small clearance so nothing starts in contact".
REACH = BODY_OFFSET + CONTACT_GAP
LEGAL_ITERS = 30  # push + re-thread rounds before the pass reports what is left (it never sends an illegal start)


def _pt_tri(P, A, B, C):
    """Closest points on triangles ABC to points P, row by row (Ericson, Real-Time Collision Detection 5.1.5): (Q, w)
    with Q = w0 A + w1 B + w2 C."""
    ab, ac, ap = B - A, C - A, P - A
    d1, d2 = (ab * ap).sum(1), (ac * ap).sum(1)
    bp = P - B
    d3, d4 = (ab * bp).sum(1), (ac * bp).sum(1)
    cp = P - C
    d5, d6 = (ab * cp).sum(1), (ac * cp).sum(1)
    va, vb, vc = d3 * d6 - d5 * d4, d5 * d2 - d1 * d6, d1 * d4 - d3 * d2
    n = len(P)
    w = np.zeros((n, 3))
    done = np.zeros(n, bool)

    def put(m, w0, w1, w2):
        m = m & ~done
        w[m, 0], w[m, 1], w[m, 2] = w0[m] if np.ndim(w0) else w0, w1[m] if np.ndim(w1) else w1, w2[m] if np.ndim(w2) else w2
        done[m] = True
    z, o = 0.0, 1.0
    put((d1 <= 0) & (d2 <= 0), o, z, z)
    put((d3 >= 0) & (d4 <= d3), z, o, z)
    put((d6 >= 0) & (d5 <= d6), z, z, o)
    with np.errstate(divide="ignore", invalid="ignore"):
        t = d1 / (d1 - d3)
        put((vc <= 0) & (d1 >= 0) & (d3 <= 0), 1 - t, t, z)
        t = d2 / (d2 - d6)
        put((vb <= 0) & (d2 >= 0) & (d6 <= 0), 1 - t, z, t)
        t = (d4 - d3) / ((d4 - d3) + (d5 - d6))
        put((va <= 0) & ((d4 - d3) >= 0) & ((d5 - d6) >= 0), z, 1 - t, t)
        den = va + vb + vc
        v_, w_ = vb / den, vc / den
        put(np.ones(n, bool), 1 - v_ - w_, v_, w_)
    Q = w[:, :1] * A + w[:, 1:2] * B + w[:, 2:] * C
    return Q, w


def _tri_radius(V, T):
    c = V[T].mean(1)
    return c, np.linalg.norm(V[T] - c[:, None], axis=2).max(1)


def _pairs_within(Pa, ra, Pb, rb, d):
    """Candidate pairs (i, j): ball i (centre Pa, radius ra) within d of ball j."""
    from scipy.spatial import cKDTree
    if not len(Pa) or not len(Pb):
        return np.zeros((0, 2), np.int64)
    L = cKDTree(Pb).query_ball_point(Pa, ra + float(rb.max()) + d)
    I = np.array([(i, k) for i, ks in enumerate(L) for k in ks], np.int64).reshape(-1, 2)
    if len(I):
        I = I[np.linalg.norm(Pa[I[:, 0]] - Pb[I[:, 1]], axis=1) < ra[I[:, 0]] + rb[I[:, 1]] + d]
    return I


def _edges(T):
    T = np.asarray(T, np.int64)
    return np.unique(np.sort(np.r_[T[:, [0, 1]], T[:, [1, 2]], T[:, [2, 0]]], 1), axis=0)


def contact_pairs(X, F, bV, bT, dmin: float, chunk: int = 200000) -> dict:
    """Every cloth / collider pair ZOZO assembles (point-triangle, triangle-point, edge-edge) whose exact distance is
    under dmin. Returns {"kind": [n] str ("vf" | "fv" | "ee"), "cloth": [n, 3] cloth vertex ids (-1 unused), "w": [n, 3]
    their weights, "body": [n] the collider element (triangle | vertex | edge row), "sep": [n, 3] the separation (cloth
    minus collider), "d": [n] metres}."""
    X, bV = np.asarray(X, float), np.asarray(bV, float)
    F, bT = np.asarray(F, np.int64), np.asarray(bT, np.int64)
    out = {k: [] for k in ("kind", "cloth", "w", "body", "sep", "d")}

    def add(kind, cv, w, be, sep, d):
        m = d < dmin
        if m.any():
            out["kind"].append(np.full(int(m.sum()), kind))
            out["cloth"].append(cv[m]), out["w"].append(w[m]), out["body"].append(be[m])
            out["sep"].append(sep[m]), out["d"].append(d[m])
    # (a box round the cloth: collider elements outside it can't be within dmin)
    lo, hi = X.min(0) - dmin, X.max(0) + dmin
    bc, br = _tri_radius(bV, bT)
    keep = np.where(((bc + br[:, None] > lo) & (bc - br[:, None] < hi)).all(1))[0]
    # cloth vertex vs collider triangle
    I = _pairs_within(X, np.zeros(len(X)), bc[keep], br[keep], dmin)
    for s in range(0, len(I), chunk):
        J = I[s:s + chunk]
        t = bT[keep[J[:, 1]]]
        Q, _ = _pt_tri(X[J[:, 0]], bV[t[:, 0]], bV[t[:, 1]], bV[t[:, 2]])
        sep = X[J[:, 0]] - Q
        cv = np.c_[J[:, 0], -np.ones((len(J), 2), np.int64)]
        add("vf", cv, np.c_[np.ones(len(J)), np.zeros((len(J), 2))], keep[J[:, 1]], sep, np.linalg.norm(sep, axis=1))
    # collider vertex vs cloth triangle
    cc, cr = _tri_radius(X, F)
    vb = np.where(((bV > lo) & (bV < hi)).all(1))[0]
    I = _pairs_within(bV[vb], np.zeros(len(vb)), cc, cr, dmin)
    for s in range(0, len(I), chunk):
        J = I[s:s + chunk]
        t = F[J[:, 1]]
        Q, w = _pt_tri(bV[vb[J[:, 0]]], X[t[:, 0]], X[t[:, 1]], X[t[:, 2]])
        sep = Q - bV[vb[J[:, 0]]]
        add("fv", t, w, vb[J[:, 0]], sep, np.linalg.norm(sep, axis=1))
    # cloth edge vs collider edge
    from .cloth import _seg_seg
    E, bE = _edges(F), _edges(bT)
    me, he = X[E].mean(1), 0.5 * np.linalg.norm(X[E[:, 0]] - X[E[:, 1]], axis=1)
    mb, hb = bV[bE].mean(1), 0.5 * np.linalg.norm(bV[bE[:, 0]] - bV[bE[:, 1]], axis=1)
    kb = np.where(((mb + hb[:, None] > lo) & (mb - hb[:, None] < hi)).all(1))[0]
    I = _pairs_within(me, he, mb[kb], hb[kb], dmin)
    for s in range(0, len(I), chunk):
        J = I[s:s + chunk]
        e, b = E[J[:, 0]], bE[kb[J[:, 1]]]
        p0, p1, q0, q1 = X[e[:, 0]], X[e[:, 1]], bV[b[:, 0]], bV[b[:, 1]]
        sa, tb, d = _seg_seg(p0, p1, q0, q1)
        sep = (p0 + sa[:, None] * (p1 - p0)) - (q0 + tb[:, None] * (q1 - q0))
        add("ee", np.c_[e, -np.ones(len(e), np.int64)], np.c_[1 - sa, sa, np.zeros(len(e))], kb[J[:, 1]], sep, d)
    if not out["d"]:
        return {"kind": np.zeros(0, str), "cloth": np.zeros((0, 3), np.int64), "w": np.zeros((0, 3)),
                "body": np.zeros(0, np.int64), "sep": np.zeros((0, 3)), "d": np.zeros(0)}
    return {k: np.concatenate(v) for k, v in out.items()}


def legality(X, F, bV, bT, offset: float = BODY_OFFSET) -> dict:
    """ZOZO's frame-0 test on this start: the pairs with d <= offset (illegal: the solver refuses the run) and the
    nearest pair. {"ok", "illegal", "min_mm", "by_kind", "worst": [(kind, cloth ids, body element, d mm, at xyz)]}."""
    P = contact_pairs(X, F, bV, bT, offset + 1e-9)
    bad = P["d"] <= offset
    Q = contact_pairs(X, F, bV, bT, REACH + 0.002)
    mn = float(Q["d"].min()) * 1000 if len(Q["d"]) else float("inf")
    o = np.argsort(P["d"])[:5]
    X = np.asarray(X, float)
    worst = [(str(P["kind"][i]), [int(c) for c in P["cloth"][i] if c >= 0], int(P["body"][i]),
              round(float(P["d"][i]) * 1000, 3), [round(float(x), 4) for x in X[P["cloth"][i][0]]]) for i in o]
    return {"ok": not bool(bad.any()), "illegal": int(bad.sum()), "min_mm": round(mn, 3),
            "in_reach": int((Q["d"] < REACH).sum()),
            "by_kind": {k: int(((P["kind"] == k) & bad).sum()) for k in ("vf", "fv", "ee")}, "worst": worst}


def push_out(X, P: dict, target: float) -> tuple[np.ndarray, int]:
    """Each pair under `target` moved apart along its own separation by its deficit: the cloth vertices the pair names
    (a vertex; a triangle's three; an edge's two) translate by (target - d) along sep / d, so the pair's distance grows
    by that deficit (a rigid move of the cloth element along the closest-point direction). A vertex in several pairs
    moves by the largest deficit along their deficit-weighted mean direction. Returns (X, vertices moved)."""
    X = np.array(X, float)
    if not len(P["d"]):
        return X, 0
    deficit = target - P["d"]
    n = P["sep"] / np.maximum(P["d"], 1e-12)[:, None]
    acc, mag = np.zeros_like(X), np.zeros(len(X))
    for k in range(3):
        c = P["cloth"][:, k]
        m = c >= 0
        np.add.at(acc, c[m], n[m] * deficit[m, None])
        np.maximum.at(mag, c[m], deficit[m])
    mv = np.where(mag > 0)[0]
    dirs = acc[mv] / np.maximum(np.linalg.norm(acc[mv], axis=1, keepdims=True), 1e-20)
    X[mv] += dirs * mag[mv, None]
    return X, len(mv)


def legal_start(res: dict, X, rethread=None, target: float = REACH, iters: int = LEGAL_ITERS, log=print,
                fixed: np.ndarray | None = None) -> tuple:
    """THE FIT'S LAST CONTACT PASS for a ZOZO hang (C249): every cloth / collider pair (ZOZO's own three kinds, exact
    distances, the collider ZOZO receives: collider(res)) held at `target` (REACH) or more: push the pairs under it apart
    (push_out), re-project the threads (rethread(res, X): the fit's threads-hard projection), repeat until none is under
    target (or iters; then the remainder is reported, and the pre-flight still refuses an illegal start).
    Returns (X, info)."""
    bV, bT = collider(res)
    F = np.asarray(res["mesh"]["F"], np.int64)
    X = np.asarray(X, float)
    fx = np.zeros(len(X), bool) if fixed is None else np.asarray(fixed, bool)
    Xfix = X[fx].copy()
    if fx.any():  # (CONSTRUCTED pieces, C258: prescribed, never pushed nor re-threaded; their faces aren't the cloth's)
        F = F[~fx[F].all(1)]
        _rt0 = rethread

        def rethread(res_, X_):
            Y = np.asarray(_rt0(res_, X_), float) if _rt0 is not None else np.asarray(X_, float)
            Y[fx] = Xfix
            return Y
    t0 = time.time()
    hist = []
    X0 = X.copy()
    for it in range(iters):
        P = contact_pairs(X, F, bV, bT, target)
        hist.append(len(P["d"]))
        if not len(P["d"]):
            break
        if len(hist) > 3 and hist[-1] >= min(hist[-4:-1]):
            break  # (the threads put back as many as the push takes out: tee2_ff sat at 27-29 for 25 rounds)
        X, _ = push_out(X, P, target)
        X[fx] = Xfix
        if rethread is not None:
            X = np.asarray(rethread(res, X), float)
    # CONTACT LAST (as hard_threads ends): what the threads put back under target is pushed out alone
    tail = []
    for it in range(iters):
        P = contact_pairs(X, F, bV, bT, target)
        tail.append(len(P["d"]))
        if not len(P["d"]) or (len(tail) > 3 and tail[-1] >= min(tail[-4:-1])):
            break  # (none left, or pairs the push can't separate further: reported; legal is d > offset, read below)
        X, _ = push_out(X, P, target)
        X[fx] = Xfix
    d_mv = np.linalg.norm(X - X0, axis=1) * 1000
    lg = legality(X, F, bV, bT)
    info = {"under_target": hist, "contact_last": tail, "target_mm": round(target * 1000, 3),
            "moved_mm": {"n": int((d_mv > 1e-3).sum()), "p99": round(float(np.percentile(d_mv, 99)), 3),
                         "max": round(float(d_mv.max()), 3)}, "legal": lg, "s": round(time.time() - t0, 1)}
    log(f"zozo_hang: legal start {json.dumps(info, default=str)}")
    return X, info


def coarse_mesh(g: dict, src, label: str, coarse: float = COARSE) -> dict:
    """The coarse settle's mesh of the same pattern (cloth.build place_only at `coarse`)."""
    from . import cloth
    gc = json.loads(json.dumps(g))
    gc["resolution"] = float(coarse)
    gc.pop("mesh_refine", None)
    return cloth.build(cloth._garment_for_sim(gc), src, label, log=lambda *_: None, place_only=True)


def settle_edge_len(M: dict, Mc: dict | None = None) -> np.ndarray:
    """Per vertex of the fit's mesh M: the longest edge the settled mesh lays across it: M's own, or (a coarse settle)
    the larger of M's and the coarse mesh's nearest vertex's in the same piece's pattern."""
    L = edge_len_v(M)
    if Mc is None:
        return L
    from scipy.spatial import cKDTree
    Lc = edge_len_v(Mc)
    uv, pid = np.asarray(M["uv"], float), np.asarray(M["piece"])
    uvc, pidc = np.asarray(Mc["uv"], float), np.asarray(Mc["piece"])
    for p in np.unique(pid):
        q, qc = np.where(pid == p)[0], np.where(pidc == p)[0]
        if len(qc):
            _, k = cKDTree(uvc[qc]).query(uv[q])
            L[q] = np.maximum(L[q], Lc[qc[k]])
    return L


def _bary_map(uv_from, F_from, pid_from, uv_to, pid_to):
    """For each point (uv_to, piece pid_to): (triangle of F_from, barycentric) in the same piece's pattern, nearest."""
    from scipy.spatial import cKDTree
    tri = np.zeros(len(uv_to), int)
    bc = np.zeros((len(uv_to), 3))
    fp = pid_from[F_from[:, 0]]
    for p in np.unique(pid_to):
        q = np.where(pid_to == p)[0]
        fs = np.where(fp == p)[0]
        if not len(fs):
            raise ValueError(f"piece {p}: no triangles to carry from")
        A, Bv, C = (uv_from[F_from[fs, k]] for k in range(3))
        cen = (A + Bv + C) / 3.0
        kk = min(12, len(fs))
        _, cand = cKDTree(cen).query(uv_to[q], k=kk)
        cand = np.asarray(cand).reshape(len(q), kk)
        best = np.full(len(q), np.inf)
        for j in range(kk):
            t = fs[cand[:, j]]
            a, b, c = uv_from[F_from[t, 0]], uv_from[F_from[t, 1]], uv_from[F_from[t, 2]]
            v0, v1, v2 = b - a, c - a, uv_to[q] - a
            den = v0[:, 0] * v1[:, 1] - v1[:, 0] * v0[:, 1]
            den = np.where(np.abs(den) < 1e-14, 1e-14, den)
            l1 = (v2[:, 0] * v1[:, 1] - v1[:, 0] * v2[:, 1]) / den
            l2 = (v0[:, 0] * v2[:, 1] - v2[:, 0] * v0[:, 1]) / den
            L = np.c_[1 - l1 - l2, l1, l2]
            out = -np.minimum(L, 0).sum(1)  # 0 inside
            m = out < best
            best[m] = out[m]
            tri[q[m]] = t[m]
            bc[q[m]] = L[m]
        bc[q] = np.clip(bc[q], 0, None)
        bc[q] /= bc[q].sum(1, keepdims=True)
    return tri, bc


def carry(X_from, uv_from, F_from, pid_from, uv_to, pid_to):
    """Positions on another mesh of the same pattern: each target vertex at its pattern point of the source surface."""
    tri, bc = _bary_map(np.asarray(uv_from, float), np.asarray(F_from), np.asarray(pid_from),
                        np.asarray(uv_to, float), np.asarray(pid_to))
    F_ = np.asarray(F_from)[tri]
    X_ = np.asarray(X_from, float)
    return (X_[F_] * bc[:, :, None]).sum(1)


def collider(res: dict) -> tuple[np.ndarray, np.ndarray]:
    """The static collider: the posed body, and the garment under (its fit as worn) for a layered garment."""
    b = res["body"]
    V, T = np.asarray(b.V, float), np.asarray(b.T, np.int64)
    u = res.get("form_under")
    if u is not None:
        uV, uF = np.asarray(u["A"], float), np.asarray(u["mesh"]["F"], np.int64)
        V, T = np.r_[V, uV], np.r_[T, uF + len(b.V)]
    return V, T


def sound_rest(R: np.ndarray, M: dict, names: list, lim: float) -> dict:
    """Which made pieces' rest R is a shape their cloth can take: every face (bar slivers of the flat mesh itself, a
    corner under 2 deg) within [1 / (1 + lim), 1 + lim] principal stretch of its cut (the solver's own limit). A made
    shape is the cut folded and curved, never stretched past what the cloth can be: round 4 found shirt t7's placement
    collar 26 % p99 / 89 % max stretched and 0.53 compressed against its cut (folded round the neck undeveloped), so
    it is no rest. {piece: {"ok", "max", "min"}}"""
    from . import cloth_zozo as cz
    F = np.asarray(M["F"])
    uv3 = np.c_[np.asarray(M["uv"], float), np.zeros(len(R))]
    fp = np.asarray(M["piece"])[F[:, 0]]
    e = [uv3[F[:, (i + 1) % 3]] - uv3[F[:, i]] for i in range(3)]
    ang = [np.degrees(np.arccos(np.clip(-(e[i] * e[i - 1]).sum(1) / np.maximum(
        np.linalg.norm(e[i], axis=1) * np.linalg.norm(e[i - 1], axis=1), 1e-20), -1, 1))) for i in range(3)]
    from . import pattern_form as pf
    ok_f = (np.minimum(np.minimum(ang[0], ang[1]), ang[2]) > 2.0) & ~np.asarray(pf.crease_faces(M), bool)  # (a fold row
    # creases inside its triangles: its cross thread is shorter by design)
    out = {}
    for nm in names:
        f = F[(fp == list(M["names"]).index(nm)) & ok_f]
        hi = cz._start_stretch(uv3, R, f)
        lo = 1.0 / np.maximum(cz._start_stretch(R, uv3, f), 1e-12)
        out[nm] = {"ok": bool(hi.max() <= 1 + lim and lo.min() >= 1 / (1 + lim)), "max": round(float(hi.max()), 3),
                   "min": round(float(lo.min()), 3)}
    return out


def made_rest(src: dict, Mw: dict) -> np.ndarray | None:
    """The made pieces' REST on mesh Mw (round 4, C252): their intended worn shape from the draft, not what the fit
    left of them. That is the placement's made shape (cloth.place -> B["start_unpushed"]: each piece laid on its wrap,
    folded at its declared fold lines (a collar's roll, a cuff's turn-back, a band's fold), the drape band's worn
    mesh for a draped piece (drape.draped_start); before the push clear of the body), carried by pattern position
    from the placement's mesh (the fit's coarse mesh when it refined) onto Mw. The fit's own shape of them was a worse
    rest: shirt t7's collar as fitted crumple p95 0.37 mm, roll twist 19 deg/cm, mirror 4.8 mm vs the placement's
    0.16 / 7.5 / 1.5; resting on it, ZOZO kept every crumple as rest. None: no placement kept."""
    U = (src.get("pieces") or {}).get("start_unpushed")
    if U is None:
        return None
    U = np.asarray(U, float)
    for key in ("mesh", "coarse", "coarse_mesh"):
        Ms = src.get(key)
        if Ms is not None and len(Ms["uv"]) == len(U):
            return carry(U, Ms["uv"], Ms["F"], Ms["piece"], Mw["uv"], Mw["piece"])
    return None


def start_strain(arrays: dict, jc: dict, top: int = 6) -> dict:
    """ZOZO's second frame-0 test (round 4, C252), mirrored: strainlimiting/strain_toi.kernel.cpp shell_strain_toi
    returns toi 0 for a face whose largest principal strain (shell_max_strain, vs its rest) is at or past its limit at
    the start and still past it after the full step ("ccd failed, strain limiting toi 0": the hoodie, round 3). The
    rest and the per-face limit are exactly what the runner hands the solver (cloth_zozo.flat_rest + face_limits: the
    made pieces' and declared bands' raised limits, the runner's lifted few). A face that starts past its own limit
    passes only if the first step happens to bring it back (the tee, round 3): the pre-flight refuses it.
    {"ok", "over", "faces", "by_piece": {piece: [n, worst strain %, its limit %]}, "worst": [(face, piece, %, lim %)]}"""
    from . import cloth_zozo as cz
    job = dict(jc)
    job.update(job.pop("zozo", None) or {})
    X, F = np.asarray(arrays["X"], float), np.asarray(arrays["F"], np.int64)
    if job.get("rest", "flat" if job.get("placement") == "smooth" else "placed") != "flat":
        return {"ok": True, "over": 0, "faces": len(F), "by_piece": {}, "worst": [], "note": "rest placed: start = rest"}
    fr = cz.flat_rest(job, arrays, X, F)
    fl = cz.face_limits(fr["lv"], fr["lim"], F)
    e = (fr["sig"] - 1.0).astype(np.float32)
    bad = e >= fl.astype(np.float32)
    fp = np.asarray(arrays["piece"])[F[:, 0]]
    by = {}
    for k, nm in enumerate(job["pieces"]):
        m = bad & (fp == k)
        if m.any():
            by[nm] = [int(m.sum()), round(float(e[m].max()) * 100, 1), round(float(fl[m].min()) * 100, 1)]
    w = np.where(bad)[0]
    w = w[np.argsort(-(e[w] - fl[w]))][:top]
    return {"ok": not bad.any(), "over": int(bad.sum()), "faces": len(F), "by_piece": by,
            "worst": [(int(f), job["pieces"][int(fp[f])], round(float(e[f]) * 100, 1), round(float(fl[f]) * 100, 1))
                      for f in w]}


def write_job(res: dict, X: np.ndarray, g: dict, jd: Path, frames: int | None = None, log=print,
              rest_src: dict | None = None, carry_mask: np.ndarray | None = None) -> dict:
    """The settle job for fit `res` placed at X (the fit's mesh): in.npz + job.json in jd. rest_src: the fit whose
    placement gives the made pieces' rest (made_rest; default res). Returns facts about it."""
    from . import cloth, cloth_job as cj, cloth_workflow as cwf, folds as foldmod
    from . import cloth_zozo as cz
    M, B = res["mesh"], res.get("pieces") or {}
    X = np.asarray(X, float)
    F = np.asarray(M["F"], np.int64)
    stiff = cloth.interfacing(B, M)
    made = cloth.made_pieces(M, stiff)
    fold_s = {}
    if M.get("folds"):
        fold_s["fold"] = foldmod.weights(M)
        fold_s["bend_rest"] = foldmod.bend_reference(M, np.c_[M["uv"], np.zeros(len(M["uv"]))], B.get("faces"))
    bV, bT = collider(res)
    import types
    near = cwf.start_in_standoff(X, M, types.SimpleNamespace(V=bV, T=bT), 0.9 * BODY_OFFSET)
    lim = strain_limit(g, B)
    pid = np.asarray(M["piece"])
    flat3 = np.c_[np.asarray(M["uv"], float), np.zeros(len(X))]
    mk = np.isin(pid, [list(M["names"]).index(n) for n in made])
    cm = np.zeros(len(X), bool) if carry_mask is None else np.asarray(carry_mask, bool)
    if cm.any():  # (CONSTRUCTED made pieces are prescribed, C258: no rest needed; the others keep round 5's)
        mk &= ~cm
    # round 5 (C254): the made pieces' worn shape from the draft and the body, the CUT developed onto it
    # (made_shape.made_rest: the collar's drape on the fitted neckline, the others the fit's shape smoothed); the
    # placement's made shape (made_rest) only if made_shape gives none
    R, ms_rep = None, None
    if mk.any():
        from . import made_shape as ms_
        from . import drape as dr_
        body = res["body"]
        vn_, tr_ = body.normals()
        bs_ = dr_.Surf(body.V, body.T, out=lambda P_: vn_[tr_.query(P_)[1]])
        mr = ms_.made_rest(res, X, g, made, res.get("fabric"), floors=(bs_,))
        R, ms_rep = mr["R"], mr["report"]
        log(f"zozo_hang: made shapes {json.dumps(ms_rep, default=str)}")
    if R is None and mk.any():
        R = made_rest(rest_src or res, M)
    snd = sound_rest(R, M, made, lim) if R is not None else {}
    if R is not None:  # (a piece whose made shape is no shape its cloth can take rests as fitted, and says so)
        for nm, v in snd.items():
            if not v["ok"]:
                sel_ = pid == list(M["names"]).index(nm)
                R[sel_] = X[sel_]
                log(f"zozo_hang: {nm}'s made shape is no rest (principal {v['min']}..{v['max']} of its cut, limit "
                    f"{lim * 100:.0f} %): it rests as fitted")
    flat3[mk] = (X if R is None else R)[mk]
    flat3[cm & np.isin(pid, [list(M["names"]).index(n) for n in made])] = X[cm & np.isin(pid, [list(M["names"]).index(n) for n in made])]  # (constructed made pieces rest as built; held seam rows flat)
    sig = cz._start_stretch(flat3, X, F)
    over = (sig > 1.0 + lim) & ~mk[F].all(1)
    arrays = dict(X=X, uv=np.asarray(M["uv"], float), F=F, sew=np.asarray(M["sew"], np.int64).reshape(-1, 2),
                  stitch=np.asarray(M.get("stitch", np.zeros((0, 2))), np.int64).reshape(-1, 2),
                  stiff=np.asarray(stiff, float), piece=pid.astype(np.int64), pins=np.zeros(0, np.int64),
                  bodyV=bV, bodyT=bT, **fold_s, **({"rest": R} if R is not None else {}))
    if cm.any():
        # CONSTRUCT, DON'T SOLVE (folds A/B path A, C258): the constructed folded pieces are held where they were built
        # for the whole settle (the runner's carry: pinned, no pose moves), the body cloth sewn to them at their seams
        # (a stitch to a held end draws the cloth to it); prescribed, and solid: free cloth meets them by contact
        ci_ = np.where(cm)[0].astype(np.int64)
        # (no hugIdx: the start is legal now (settle: contact pass before holding), so held pieces keep their contact.
        # Pass-through pins (allow_intersection) drop ALL contact of their elements: A_sh4's free body cloth crossed
        # the held collar / stand and ZOZO stopped at t 2.04 s, "intersection detected")
        arrays.update(carryIdx=ci_, carryPoses=X[ci_][None])
        # WHAT RESTS AS BUILT: only the constructed made pieces (the runner's restIdx path, flat_rest). The body cloth's
        # seam rows held with them rest flat like the rest of their piece: resting them "as they start" (carryIdx's
        # default) put a 3D rest beside the flat one in the same face (A_sh4: sleeve faces by the cuff rows read
        # 105-185 % strain at the start, 128-163 % at the fit itself; refused at frame 0)
        whole = cm & np.isin(pid, [list(M["names"]).index(n) for n in made])
        Rr = (np.asarray(R, float) if R is not None else np.asarray(X, float)).copy()
        Rr[whole] = X[whole]
        arrays.update(rest=Rr, restIdx=np.where(whole)[0].astype(np.int64))
    wraps = {nm: B["pieces"][nm]["wrap"].get("to", "torso") for nm in M["names"]
             if nm in (B.get("pieces") or {}) and isinstance(B["pieces"][nm].get("wrap"), dict)}
    decl = cloth.declared_pieces(B, M["names"]) if B else None
    cfg = {"fabric": res["fabric"], "name": f"zozo_hang:{jd.name}", "placement": "smooth", "wraps": wraps,
           "made": made, "strain_limit": lim, **({"declared": decl} if decl else {})}
    zz = dict(g.get("zozo") or {})
    if zz:
        cfg["zozo"] = zz
    jc = cj.job_config(cfg, list(M["names"]))
    n = int(frames or round(SETTLE_S * FPS))
    jc["stages"] = [{"name": "settle", "frames": n, "gravity": 1, "sew": True, "self_collision": True, "fixed": [],
                     "body": True}]
    jc["snap"] = FPS
    jd.mkdir(parents=True, exist_ok=True)
    np.savez(jd / "in.npz", **arrays)
    (jd / "job.json").write_text(json.dumps(jc, indent=1, default=cj._jsonable))
    pre = cj.preflight(arrays, cfg)
    lg = legality(X, F[~cm[F].any(1)], bV, bT)  # (ZOZO's own frame-0 test, C249; held vertices pass through)
    if not lg["ok"]:
        raise RuntimeError(f"zozo_hang: illegal start, the solver would refuse it at frame 0 ({lg['illegal']} cloth / "
                           f"collider pairs at or under the {BODY_OFFSET * 1000:.1f} mm contact offset, by kind "
                           f"{lg['by_kind']}; nearest {lg['min_mm']} mm; worst {lg['worst']}): not sent")
    ss = start_strain(arrays, jc)  # (ZOZO's second frame-0 test, C252)
    if not ss["ok"]:
        raise RuntimeError(f"zozo_hang: the start is past the strain limit, the solver would stop at frame 0 (strain "
                           f"limiting toi 0): {ss['over']} of {ss['faces']} faces at or past their limit, by piece "
                           f"[n, worst %, limit %] {ss['by_piece']}; worst {ss['worst']}: not sent (the fit made "
                           "cloth the fabric can't be: fix the fit / draft, never the limit)")
    facts = {"verts": len(X), "tris": len(F), "frames": n, "made": made, "strain_limit_pct": round(lim * 100, 1),
             "start_over_limit_pct": round(float(over.mean() * 100), 2),
             "start_stretch_p99_pct": round(float((np.percentile(sig[~mk[F].all(1)], 99) - 1) * 100), 1),
             "in_standoff": {p: v[0] for p, v in near.items()}, "preflight_ok": bool(pre["ok"]),
             "preflight_body_mm": pre.get("body_mm"), "preflight_body_pairs": pre.get("body_pairs"),
             "legality": {k: lg[k] for k in ("ok", "illegal", "min_mm", "in_reach")},
             "constructed": int(cm.sum()), "start_strain_ok": ss["ok"], "made_rest": {nm: ("made shape" if v["ok"] else f"as fitted (made shape {v['min']}..{v['max']})")
                           for nm, v in snd.items()} if R is not None else "as fitted"}
    log(f"zozo_hang: job {jd} {json.dumps(facts, default=str)}")
    return facts


def run(jd: Path, log=print, timeout: float = 3600) -> tuple:
    """The written job on this machine: the heavy slot + GPU (resources.heavy gpu=True), ZOZO's memory cap
    ($HIFIPUSHIE_ZOZO_MEM). Returns (out.npz arrays, log lines)."""
    from . import cloth_job as cj, resources
    cmd, env = cj.zozo_command(jd)
    with resources.heavy(f"zozo hang {jd.name}", log=log, kind="cloth_zozo", gpu=True, model=jd.name):
        cj.clear_strays(log)
        cj._stream(cmd, lambda m: None, timeout, env, "zozo hang settle")
    return cj.read_out(jd / "out.npz")


def weld(V: np.ndarray, M: dict, stiff=None) -> np.ndarray:
    """Each sewn group at its mean (cloth.cleanup's weld alone): a seam's two edges are one line of stitches."""
    from . import cloth
    X, _ = cloth.cleanup(V, M, None, {"smooth": 0, "weld": True, "seams": False, "press": False, "clear": 0.0,
                                      "kinks": False}, stiff)
    return X


def seam_gap_mm(V: np.ndarray, M: dict) -> dict:
    s = np.asarray(M["sew"]).reshape(-1, 2)
    if not len(s):
        return {}
    d = np.linalg.norm(V[s[:, 0]] - V[s[:, 1]], axis=1) * 1000
    return {"mean": round(float(d.mean()), 2), "p95": round(float(np.percentile(d, 95)), 2)}


def rethread_for(res: dict):
    """The fit's threads-hard projection for the legal-start pass (pattern_form.hard_threads, one relinearisation), or
    None for a garment over another (its layer rules are the fit's own, which that projection doesn't carry: styled_hard
    skips it for the same reason): there the pass only pushes."""
    from . import pattern_form as pf
    if res.get("form_under") is not None or not pf.THREADS_HARD:
        return None
    return lambda r, X: pf.hard_threads(r, X, None, relin=1)


FOLD_MODE = os.environ.get("HP_FOLD_MODE", "solve")  # "construct": folds A/B path A (C258); "solve": round 5


def fold_mode(g: dict) -> str:
    """How folded / made pieces meet the hang: "solve" (round 5: solved cloth resting as made) or "construct" (path A,
    C258: built into their worn shape and held out of the solve). Garment key "fold_mode" > env HP_FOLD_MODE."""
    return str((g or {}).get("fold_mode") or FOLD_MODE)


def construct(res: dict, X: np.ndarray, g: dict, log=print) -> tuple:
    """CONSTRUCT, DON'T SOLVE (folds A/B path A, C258): every made piece (cloth.made_pieces: collar + stand, cuffs,
    bands) built into its worn shape by geometry, from the draft and the body: made_shape.made_rest (the cut developed
    onto its worn target: the collar's drape on the fitted neckline, the others the fit smoothed), as one unit (sewn
    pieces developed together). A piece whose built shape is no shape its cloth can take (sound_rest) is kept as the
    fit placed it (the fit is the other geometric construction we have: the styled wrap / pull / smooth, C142-C146).
    Returns (X with the made pieces as built, mask of the constructed vertices, report)."""
    from . import cloth, made_shape as ms_, drape as dr_
    M, B = res["mesh"], res.get("pieces") or {}
    stiff = cloth.interfacing(B, M)
    made = cloth.made_pieces(M, stiff)
    pid = np.asarray(M["piece"])
    X = np.asarray(X, float).copy()
    if not made:
        return X, None, {"made": []}
    body = res["body"]
    vn_, tr_ = body.normals()
    bs_ = dr_.Surf(body.V, body.T, out=lambda P_: vn_[tr_.query(P_)[1]])
    mr = ms_.made_rest(res, X, g, made, res.get("fabric"), floors=(bs_,))
    lim = strain_limit(g, B)
    snd = sound_rest(mr["R"], M, made, lim)
    cm = np.zeros(len(X), bool)
    how = {}
    for nm in made:
        sel = pid == list(M["names"]).index(nm)
        cm |= sel
        if snd.get(nm, {}).get("ok"):
            X[sel] = mr["R"][sel]
            how[nm] = f"built (made_shape, cut ratio {snd[nm]['min']}..{snd[nm]['max']})"
        else:
            how[nm] = f"as fitted (built shape {snd.get(nm, {}).get('min')}..{snd.get(nm, {}).get('max')} of its cut)"
    # the body cloth's seam row sewn to a constructed piece is its attachment, held with it (A_sh1's pre-flight: the
    # neckline vertices sewn to a stand hugging the neck sat 1.5 mm off the body, inside the standoff: illegal free)
    sew = np.asarray(M["sew"], np.int64).reshape(-1, 2)
    part = sew[cm[sew[:, 0]] ^ cm[sew[:, 1]]]
    cm[part.ravel()] = True
    how["_seam_rows_held"] = int(len(part))
    log(f"zozo_hang: constructed {json.dumps(how)}")
    return X, cm, {"made": made, "how": how, "report": mr["report"]}


def settle(res: dict, X: np.ndarray, g: dict, tag: str, coarse: float | None = None, frames: int | None = None,
           gate_passed: bool = False, look: bool = False, model: str | None = None, garment: str | None = None,
           log=print, prepare_only: bool = False) -> tuple[np.ndarray | None, dict]:
    """The fit `res` placed at X, hung by a ZOZO settle. coarse: settle a coarse mesh of the pattern (m) and carry the
    result back (model / garment needed to build it). Returns (V on the fit's mesh, info)."""
    if not (gate_passed or look):
        raise RuntimeError("zozo_hang: the pattern gate has not passed (fit_garment force=True looks anyway)")
    M = res["mesh"]
    t0 = time.time()
    info = {"solver": "zozo", "provisional": True, "look_only": bool(look and not gate_passed), "coarse": coarse}
    if coarse:
        rc = res.get("zozo_coarse")  # (on_form(settle="coarse") built it and placed the fit at its clearance)
        if rc is None or abs(float(rc.get("coarse_res", -1)) - float(coarse)) > 1e-9:
            from . import pattern_form as pf, store
            src, _ = pf.form_source(model, garment, store.load(model), g)
            rc = coarse_mesh(g, src, f"{model}:{garment}", coarse)
            info["coarse_fit_clearance"] = False  # (the fit was placed for the fine mesh: the start may be refused)
        Mc = rc["mesh"]
        # (no push-out: the fit placed every vertex at the clearance of the longest edge the COARSE mesh lays across it,
        # settle_edge_len, so the coarse start's chords stay off the collider by construction, as the fine start's do)
        Xc = carry(X, M["uv"], M["F"], M["piece"], Mc["uv"], Mc["piece"])
        rc = dict(rc, form_under=res.get("form_under"), body=res["body"])
        info["build_s"] = round(time.time() - t0, 1)
        work, Xw = rc, Xc
    else:
        work, Xw = res, np.asarray(X, float)
    cm = None
    if fold_mode(g) == "construct":
        if coarse:
            raise RuntimeError("zozo_hang: fold_mode construct runs on the fit's own mesh (coarse=None)")
        Xw, cm, info["constructed"] = construct(res, Xw, g, log=log)
        # START LEGAL BEFORE HOLDING (path A, C258): the built / fitted made pieces hug the neck inside the solver's
        # standoff (A_sh1: 213 vertices 1.5 mm off the body < the 2.0 mm offset); held, nothing can move them, and the
        # pass below can't push their free neighbours out past them. So the same pass (ZOZO's own pair test, threads
        # re-projected) runs ONCE with nothing held: the made pieces and their neighbours go out together, as round 5's
        # free stand did; then they are frozen where that left them.
        Xw, info["legal_before_hold"] = legal_start(work, Xw, rethread=rethread_for(work), log=log, fixed=None)
    # THE LAST CONTACT PASS (C249): ZOZO's own pair test on the mesh it receives (fine, or the coarse one), held at REACH.
    # With pieces held it only READS (iters 0): pushing free cloth while the held rows are reset each round stretched
    # the faces between them (A_sh4 first prep: 4 sleeve faces by the held cuff rows 105-185 % of cap, frame-0 refused)
    Xw, info["legal_start"] = legal_start(work, Xw, rethread=rethread_for(work), log=log, fixed=cm,
                                          iters=0 if cm is not None else LEGAL_ITERS)
    jd = ROOT / tag
    info["job"] = write_job(work, Xw, g, jd, frames, log, rest_src=res, carry_mask=cm)
    if prepare_only:
        return None, dict(info, jd=str(jd), _work=work, _t0=t0)
    t1 = time.time()
    out, lines = run(jd, log)
    info["solve_s"] = round(time.time() - t1, 1)
    info["runner"] = [ln for ln in lines if "frames in" in ln or "seam gaps" in ln][-2:]
    return finish(res, X, out, info, coarse, jd, work, t0)


def finish(res: dict, X: np.ndarray, out: dict, info: dict, coarse=None, jd: Path | None = None, work: dict | None = None,
           t0: float | None = None) -> tuple[np.ndarray, dict]:
    """The solver's out.npz (run here, or elsewhere: NICO-TOP via the oxidegen route) back onto the fit: seams welded,
    threads re-projected (C251), carried back from a coarse mesh. settle(prepare_only=True) gives work / jd."""
    from . import cloth
    M = res["mesh"]
    work = work if work is not None else info.pop("_work", res)
    jd = Path(jd or info.get("jd"))
    t0 = t0 if t0 is not None else info.pop("_t0", time.time())
    info.pop("_work", None)
    info.pop("_t0", None)
    V = np.asarray(out["V"], float)
    Mw = work["mesh"]
    if "Vprev" in out:
        mv = np.linalg.norm(V - np.asarray(out["Vprev"], float), axis=1) * 1000
        info["last_motion_mm"] = {"p99": round(float(np.percentile(mv, 99)), 2), "max": round(float(mv.max()), 2)}
    info["seam_gap_raw_mm"] = seam_gap_mm(V, Mw)
    stiff = cloth.interfacing(work.get("pieces") or {}, Mw)
    V = weld(V, Mw, stiff)
    if coarse:
        V = carry(V, Mw["uv"], Mw["F"], Mw["piece"], M["uv"], M["piece"])
        V = weld(V, M, cloth.interfacing(res.get("pieces") or {}, M))
    # THE WELD STRETCHED THE SEAM ROWS (round 3, C251): ZOZO's raw tee settle read 0.0 % past cap; closing its ~1.05 mm
    # seam gap by moving only the sewn vertices (0.5 mm each over ~10 mm edges) put the faces along every seam ~5 % past
    # cap (p99 3.59 %, the top 1 % of faces 5 mm from a seam). So the weld is followed by the fit's own threads-hard
    # projection (seams sewn, threads within cap, contact last): tee 0.07 %, seam gaps 0, moves p99 2.7 mm
    rt = rethread_for(res)
    if rt is not None:
        Vw = V
        V = np.asarray(rt(res, V), float)
        mv = np.linalg.norm(V - Vw, axis=1) * 1000
        info["rethread_mm"] = {"p99": round(float(np.percentile(mv, 99)), 2), "max": round(float(mv.max()), 2)}
    if not coarse and (jd / "in.npz").exists():
        d_ = np.load(jd / "in.npz")
        if "carryIdx" in d_.files and len(d_["carryIdx"]):
            # CONSTRUCTED pieces stay as built (C258): the weld / re-thread never move them; a seam group holding a
            # constructed vertex is put at it (the body cloth comes to the collar, not the collar to it)
            ci_ = np.asarray(d_["carryIdx"], np.int64)
            Xc_ = np.asarray(d_["carryPoses"], float)[0]
            V[ci_] = Xc_
            held_ = np.full(len(V), -1)
            held_[ci_] = np.arange(len(ci_))
            for a_, b_ in np.asarray(M["sew"], np.int64).reshape(-1, 2):
                if held_[a_] >= 0 and held_[b_] < 0:
                    V[b_] = Xc_[held_[a_]]
                elif held_[b_] >= 0 and held_[a_] < 0:
                    V[a_] = Xc_[held_[b_]]
            info["constructed_kept"] = int(len(ci_))
    info["seam_gap_mm"] = seam_gap_mm(V, M)
    info["total_s"] = round(time.time() - t0, 1)
    np.savez(jd / "settled.npz", V=V, X=np.asarray(X, float))
    return V, info
