"""THE SEW'S SOLVER (F8, C324-): rigid first, then bend the game-cloth way; no stretch at any moment.

F7's sew (a global length solve + PULL nearer per round) stalled on the trousers: 66 rounds, 17 min, seams still open,
because it can't make the big moves (swing a whole piece round a leg). This one is dumber and faster:

1. RIGID (`rigid`): each soft piece moves as a solid (turn + slide about its own middle: six numbers a piece) to bring
   its seam partners as near as they can come (least squares on the sewn pairs' distances, the body a soft barrier at
   STANDOFF, stiff parts held). Zero stretch by construction: a rigid motion keeps every length.
2. BEND (`bend`): positions + a little velocity (Verlet, DAMP), each pass: the sewn pairs drawn together a share (ramped
   up over RAMP passes, at most STEP a pass), then every length (soft chains exact, every mesh edge at most its flat)
   iterated Gauss-Seidel in colour batches (no two links of a batch share a point: exact, vectorised), the body pushing
   out to the floor. Many cheap passes a second. The lengths are read after every pass (`worst_pct`: the most any link
   reads past its cut in the run).
3. STALL: every CHECK passes the summed seam gaps are read; falling by less than STALL_FRAC over STALL_WINDOW passes,
   or every seam within its tolerance: stop at once. A seam still open then is the gate's to name (chain_sew.gate_sew).

The caller (chain_sew.sew) then lays ONE exact projection (chain_net.project) over the result: every length at its cut.
Nothing names a garment or a limb.
"""
from __future__ import annotations

import time

import numpy as np

STANDOFF = 0.012  # m: the rigid step's barrier keeps sampled points this far off the body
BARRIER_W = 3.0  # weight of the body barrier against the sewn pairs (rigid step)
RIGID_SAMPLE = 300  # body-barrier points sampled per piece (rigid step)
DAMP = 0.97  # share of the last pass's velocity kept
PULL_SHARE = 0.5  # share of a sewn pair's gap closed per pass once ramped up
STEP = 0.004  # m: the most a sewn point is pulled in one pass
RAMP = 60  # passes over which the pull ramps from 0 to PULL_SHARE
ITERS = 6  # Gauss-Seidel sweeps over every length per pass (each with a share of the pull)
EXTRA = 10  # more sweeps (lengths alone) while a link reads past HOLD_PCT
HOLD_PCT = 1.0  # % past its cut a link may read after any pass (else more sweeps, then the pull halves)
BODY_EVERY = 2  # passes between body pushes (the body query is the costliest step)
PASSES = 3000  # most passes
CHECK = 25  # passes between gap reads
STALL_WINDOW = 150  # passes: the summed gap falling by less than STALL_FRAC over these = stalled
STALL_FRAC = 0.01
TOL = 0.002  # m: every sewn pair this near = closed (chain_sew.SEW_TOL)


def colours(i, j, n: int) -> list:
    """Links (i, j) split into batches no two of which share a point (greedy: each link the least colour free at both
    its ends; about twice the most links at a point)."""
    i, j = np.asarray(i, np.int64).tolist(), np.asarray(j, np.int64).tolist()
    used = [0] * n
    col = []
    for a, c in zip(i, j):
        m = used[a] | used[c]
        k = (~m & (m + 1)).bit_length() - 1
        col.append(k)
        used[a] |= 1 << k
        used[c] |= 1 << k
    col = np.asarray(col, np.int64)
    return [np.where(col == k)[0] for k in range(int(col.max()) + 1)] if len(col) else []


def _rot(w):
    th = float(np.linalg.norm(w))
    if th < 1e-12:
        return np.eye(3)
    k = w / th
    K = np.array([[0, -k[2], k[1]], [k[2], 0, -k[0]], [-k[1], k[0], 0]])
    return np.eye(3) + np.sin(th) * K + (1 - np.cos(th)) * K @ K


def rigid(X, pieces: list, sew, contact=None, held=None, standoff: float = STANDOFF) -> tuple[np.ndarray, dict]:
    """Each piece (an index array) turned + slid as a solid so its sewn pairs come as near as they can (least squares),
    the body (contact, optional) a soft barrier at `standoff`; `held` points never move (a piece holding any is
    skipped). Returns (X, read: seconds, rms pair gap before / after mm)."""
    from scipy.optimize import least_squares
    t0 = time.time()
    X = np.array(X, float)
    n = len(X)
    held = np.zeros(n, bool) if held is None else np.asarray(held, bool)
    S = np.asarray(sew, np.int64).reshape(-1, 2)
    pid = -np.ones(n, np.int64)
    free = [np.asarray(p, np.int64) for p in pieces if len(p) and not held[np.asarray(p)].any()]
    for k, p in enumerate(free):
        pid[p] = k
    S = S[(pid[S[:, 0]] >= 0) | (pid[S[:, 1]] >= 0)]
    if not free or not len(S):
        return X, {"s": 0.0, "pairs": 0}
    C = [X[p].mean(0) for p in free]
    rng = np.random.default_rng(0)
    samp = [rng.choice(p, min(len(p), RIGID_SAMPLE), replace=False) for p in free]

    def moved(q, idx):
        Y = X[idx].copy()
        k = pid[idx]
        for a in np.unique(k[k >= 0]):
            m = k == a
            Y[m] = (Y[m] - C[a]) @ _rot(q[6 * a:6 * a + 3]).T + C[a] + q[6 * a + 3:6 * a + 6]
        return Y

    def res(q):
        r = [(moved(q, S[:, 0]) - moved(q, S[:, 1])).ravel()]
        if contact is not None:
            for a, s in enumerate(samp):
                d = contact.query(moved(q, s))[0]
                r.append(BARRIER_W * np.sqrt(len(S) / len(s)) * np.maximum(standoff - d, 0.0))
        return np.concatenate(r)
    q0 = np.zeros(6 * len(free))
    g0 = float(np.sqrt(np.mean(np.sum((X[S[:, 0]] - X[S[:, 1]]) ** 2, 1))))
    sol = least_squares(res, q0, x_scale=np.tile([0.5, 0.5, 0.5, 0.1, 0.1, 0.1], len(free)), max_nfev=60)
    allp = np.concatenate(free)
    X[allp] = moved(sol.x, allp)
    g1 = float(np.sqrt(np.mean(np.sum((X[S[:, 0]] - X[S[:, 1]]) ** 2, 1))))
    return X, {"s": round(time.time() - t0, 2), "pairs": int(len(S)), "rms_gap_mm": [round(g0 * 1e3, 1), round(g1 * 1e3, 1)],
               "turns_deg": [round(float(np.degrees(np.linalg.norm(sol.x[6 * a:6 * a + 3]))), 1) for a in range(len(free))],
               "slides_mm": [round(float(np.linalg.norm(sol.x[6 * a + 3:6 * a + 6])) * 1e3, 1) for a in range(len(free))]}


def _gap_sum(X, S):
    return float(np.linalg.norm(X[S[:, 0]] - X[S[:, 1]], axis=1).sum())


def bend(X, i, j, L, exact, sew, held=None, floor=None, passes: int = PASSES, iters: int = ITERS,
         tol: float = TOL, log=None) -> tuple[np.ndarray, dict]:
    """Verlet + Gauss-Seidel lengths + a ramped seam pull + the body (floor: (contact, ids, gap)). Returns (X, read:
    passes, seconds, why it stopped (closed / stalled / passes), worst_pct (most any link read past its cut after any
    pass, %), gap_sum_mm per CHECK, max_gap_mm)."""
    t0 = time.time()
    X = np.array(X, float)
    n = len(X)
    held = np.zeros(n, bool) if held is None else np.asarray(held, bool)
    w = (~held).astype(float)
    i, j = np.asarray(i, np.int64), np.asarray(j, np.int64)
    L, exact = np.asarray(L, float), np.asarray(exact, bool)
    keep = ~(held[i] & held[j])
    i, j, L, exact = i[keep], j[keep], L[keep], exact[keep]
    batches = [(i[c], j[c], L[c], exact[c], w[i[c]], w[j[c]]) for c in colours(i, j, n)]
    S = np.asarray(sew, np.int64).reshape(-1, 2)
    S = S[~(held[S[:, 0]] & held[S[:, 1]])]
    ws = w[S[:, 0]] + w[S[:, 1]]
    cnt = np.maximum(np.bincount(S.ravel(), minlength=n), 1)
    gain, now = 1.0, 0.0
    Xp = X.copy()
    hist, worst, why = [], 0.0, "passes"
    r = 0
    for r in range(passes):
        V = (X - Xp) * DAMP
        Xp = X.copy()
        X = X + V * w[:, None]
        if floor is not None and r % BODY_EVERY == 0:  # the body first: the lengths have the last word
            ct, ids, gap = floor
            dd, nn = ct.query(X[ids])
            k = dd < gap
            push = np.minimum(gap - dd[k], STEP)[:, None] * nn[k]
            X[ids[k]] += push
            Xp[ids[k]] += push  # (a push is no velocity: the body never throws cloth)
        share = PULL_SHARE * min(1.0, (r + 1) / RAMP) * gain / iters
        for it in range(iters + EXTRA):
            if it < iters and len(S):  # the seam pull, a share each sweep (ramped, capped)
                d = X[S[:, 1]] - X[S[:, 0]]
                g = np.linalg.norm(d, axis=1)
                mv = np.minimum(share * g, STEP / iters) / np.maximum(g, 1e-12)
                corr = d * (mv / np.maximum(ws, 1e-12))[:, None]
                D = np.zeros_like(X)
                np.add.at(D, S[:, 0], corr * w[S[:, 0], None])
                np.add.at(D, S[:, 1], -corr * w[S[:, 1], None])
                X += D / cnt[:, None]
            for bi, bj, bL, bE, wi, wj in batches:  # the lengths, Gauss-Seidel by batch
                d = X[bj] - X[bi]
                l = np.maximum(np.linalg.norm(d, axis=1), 1e-12)
                c = l - bL
                c = np.where(bE, c, np.maximum(c, 0.0))
                sc = (c / l / np.maximum(wi + wj, 1e-12))[:, None] * d
                X[bi] += sc * wi[:, None]
                X[bj] -= sc * wj[:, None]
            if it >= iters - 1:
                l = np.linalg.norm(X[j] - X[i], axis=1)
                now = float(((l - L) / np.maximum(L, 1e-9)).max()) * 100
                if now <= HOLD_PCT:
                    break
        if now > HOLD_PCT:  # (the pull outran the lengths: gentler from here)
            gain = max(0.05, gain * 0.7)
        else:
            gain = min(1.0, gain * 1.02)
        worst = max(worst, now)
        if r % CHECK == 0 or r == passes - 1:
            gs = _gap_sum(X, S) if len(S) else 0.0
            hist.append((r, gs))
            gm = float(np.linalg.norm(X[S[:, 0]] - X[S[:, 1]], axis=1).max()) if len(S) else 0.0
            if log:
                log(r, round(gs * 1e3), round(gm * 1e3, 1), round(worst, 3))
            if gm <= tol:
                why = "closed"
                break
            back = [h for h in hist if h[0] <= r - STALL_WINDOW]
            if back and back[-1][1] - gs < STALL_FRAC * back[-1][1]:
                why = "stalled"
                break
    gm = float(np.linalg.norm(X[S[:, 0]] - X[S[:, 1]], axis=1).max()) if len(S) else 0.0
    return X, {"passes": r + 1, "s": round(time.time() - t0, 1), "why": why, "worst_pct": round(worst, 3),
               "max_gap_mm": round(gm * 1e3, 1), "gap_sum_mm": [(a, round(g * 1e3)) for a, g in hist]}
