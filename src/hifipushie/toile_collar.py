"""The toile's COLLAR (step 4, R3f, C497): draped on the toile as a part, as a tailor drapes it on the stand, never
drafted flat and fitted afterwards (R2-R3e drafted it flat at step 6 and fitted it round the neck: it always stood round
the neck like a ruffled band). Step 6 cuts it and unfolds the fall about the roll line (cut_collar.py).

THE DECLARATION (garment_toile's `collar`, needs "lapel"): {"stand_mm", "fall_mm" (both at CB, read off the reference),
"notch": a step-2 trace from the collar end's gorge corner to the collar point (its first corner)}.
THE NECK EDGE (one half, CB -> the collar end, mirrored for the other): the toile's neck seam (the toile mesh's free edge
along the neckline) from CB to where it ends (near the side neck point: the opening takes the front), the front's neck
(the FRONT NECKLINE toile_style.front_neck cuts: the over front's own free edge, R3f-4) down to the lapel's roll line's top
(the gorge point), then the lapel's own top edge to the notch trace's first point (the gorge corner): the same runs the
garment pieces are cut with, so the collar's seams are theirs.
THE ROLL AND THE STAND (R3f-8, C507; a suit collar, the reference beside it): the stand leans back against the neck ALL
ROUND, walked up the neck / the toile from the neck edge: stand_mm at CB, at the side neck point the collar's top beside
the neck as the reference shows it (the notch trace's top, >= SIDE_STAND x stand_mm), tapering to nothing (H_MIN) at the
gorge point, where the roll meets the lapel's roll line (R3f-3..7 leant the stand OUT to the lapel's roll line carried
up: from the front the collar stood round the neck as a band, a shirt's). The neck edge has a column ON the gorge point
(corner_row: the row is the front's neck edge through its corner, the seam equal). THE FALL turns back about the roll
and covers the stand (stand_seen_front_pct: what of the stand in front of the side neck point shows from the front):
behind SPAN_FROM it comes back down over the stand and lies out on the toile (fall_mm at CB along the cloth, at least
fall - h past the seam, as far as a span of fall from the roll reaches); from SPAN_FROM to the side neck point carried
out over the shoulder to the reference's silhouette (land_out: the notch trace above the cloth is the fall seen edge-on
beside the neck); in front of the side neck point it lands on the notch trace where that lies over cloth (traced_outer,
land_traced), each column by its place between the side neck point and the end, reaching the collar point at the end.
Between the roll and the outer edge the fall is a SPAN pushed out only where it would come nearer the toile than GAP.
The mesh is one grid (rows: neck edge -> roll -> outer edge; columns: the right end -> CB -> the left end), folded at
the roll row; t.collar_grid = (rows, columns, the roll row). Nothing here knows a garment."""
from __future__ import annotations

import numpy as np

from .toile_style import LAPEL_LIFT_M, MIR, past_corner, to_corner

H_MIN = 0.002    # m: the "stand" past the gorge point (none: the collar end lies on the lapel; kept off zero for the flat)
SIDE_STAND = 2 / 3  # the stand at the neck seam's end (the side neck point) / at CB: the tailor's draft runs the roll line
#                    through 2/3 of the stand beyond the side neck point (classic lounge-jacket collar draft)
SPAN_FROM = 0.5  # of the back neck from CB: the roll leaves the neck here for the lapel's roll line carried up
GAP = 0.003      # m: the fall lies this far outside the stand / the toile (the cloth's thickness)
NC = 36          # columns per half
KS, KF = 4, 8    # stand rows, fall rows
STEP = 0.002     # m: walks over the toile's surface in steps of this
SMOOTH = 4       # passes of a 5-column average on the neck edge's tangent (the gorge's corner: walks would cross)
ROW_SMOOTH = 6   # passes of a 3-point average along each row (the walks cross where the neck edge turns into the gorge)
NECK_ON_M = 0.002  # m: a toile free-edge point this near the neckline is on the neck seam


class CollarRefused(ValueError):
    """A collar the toile can't drape (named)."""


def _resample(P, n):
    s = np.r_[0, np.cumsum(np.linalg.norm(np.diff(P, axis=0), axis=1))]
    t = np.linspace(0, s[-1], n)
    return np.c_[[np.interp(t, s, P[:, k]) for k in range(P.shape[1])]].T, t


def _at(P, a):
    """The point at arc length a along polyline P (clamped)."""
    s = np.r_[0, np.cumsum(np.linalg.norm(np.diff(P, axis=0), axis=1))]
    a = np.clip(a, 0, s[-1])
    return np.array([np.interp(a, s, P[:, k]) for k in range(3)])


def neck_half(t, toile):
    """(the neck seam on the toile from CB to the gorge's top (n, 3), the side neck point's index): the toile mesh's own
    free edge along the neckline (so the collar's neck edge IS the body pieces' neck edge), from CB round the left side
    to the over front's corner (where the front edge, the roll line carried up, meets the neck)."""
    from .toile_geom import boundary_loops
    cn = t.cn
    Vt = np.asarray(toile[0], float)
    ids = np.unique(np.concatenate([np.asarray(lp, int) for lp in boundary_loops(np.asarray(toile[1], int))]))
    N = Vt[ids[np.abs(t.phi_neck(Vt[ids])) < NECK_ON_M]]
    if len(N) < 10:
        raise CollarRefused("collar: the toile has no neck seam (no free edge along the neckline)")
    ang = np.arctan2(N[:, 0] - cn[0], N[:, 1] - cn[1])  # 0 at CB (behind, +y), pi/2 at the left side, pi in front
    o = np.argsort(ang)
    A, P = ang[o], N[o]
    cb = np.array([np.interp(0.0, A, P[:, i]) for i in range(3)])
    cb[0] = 0.0  # (the collar is mirrored across x = 0)
    Q, _ = _resample(np.r_[cb[None], P[A > 0]], 300)
    for _ in range(ROW_SMOOTH):  # (the mesh's free edge zigzags by its grid: faired along the line)
        Q[1:-1] = 0.25 * Q[:-2] + 0.5 * Q[1:-1] + 0.25 * Q[2:]
    return Q, int(np.argmax(np.abs(Q[:, 0] - cn[0])))


def _surface(t, P, off):
    """P on the toile's surface, off along its normal."""
    Q = t.onto(P)
    return Q + np.asarray(off, float).reshape(-1, 1) * t.grad(Q)


def _walk(t, p, T, sign, length, off, aim=None, b=0.0):
    """A walk over the toile's surface from p square to tangent T (sign +1: up, -1: down), off its surface by off; with
    aim, turned toward that point by b (0..1)."""
    out = [p]
    q, g_prev = p, None
    while len(out) < 2 or np.linalg.norm(np.diff(np.asarray(out), axis=0), axis=1).sum() < length:
        n = t.grad(q[None])[0]
        Tt = T - (T @ n) * n
        if np.linalg.norm(Tt) > 0.2 or g_prev is None:  # (the neck edge's tangent in this surface; where it dives
            g = np.cross(n, Tt)                          # into it, go on the way the walk was going)
        else:
            g = g_prev.copy()
        g -= (g @ n) * n
        if g_prev is None:
            g *= np.sign(g[2]) * sign or 1.0
        elif g @ g_prev < 0:
            g = -g
        g /= np.linalg.norm(g) + 1e-12
        g_prev = g
        if aim is not None and b > 0:
            a = aim - q
            a -= (a @ n) * n
            if np.linalg.norm(a) < STEP:
                out.append(aim)
                break
            g = (1 - b) * g + b * a / np.linalg.norm(a)
            g /= np.linalg.norm(g) + 1e-12
        q = _surface(t, (q + STEP * g)[None], off)[0]
        out.append(q)
    return np.asarray(out)


def fair_rows(t, X, ks, lift, span=None):
    """Each row but the neck edge faired along the columns (its ends kept), then back on its surface: the stand rows on
    the toile (+ lift) except in the span columns (there the stand stands off the body, leaning out to the roll line:
    pushed out only), the outer edge GAP outside it (where the fall lands), the fall's span between pushed out only
    where it would come nearer than GAP."""
    span = np.zeros(X.shape[1], bool) if span is None else span
    nr = X.shape[0]
    for r in range(1, nr):
        R = X[r].copy()
        for _ in range(ROW_SMOOTH):
            R[1:-1] = 0.25 * R[:-2] + 0.5 * R[1:-1] + 0.25 * R[2:]
        if r == nr - 1 or (r <= ks and not span.any()):
            X[r] = _surface(t, R, lift + (GAP if r > ks else 0.0))  # (the stand lies on the toile; the outer edge lands)
        elif r <= ks:
            X[r] = R
            X[r, ~span] = _surface(t, R[~span], lift[~span] if np.ndim(lift) else lift)
            inside = span & (t.FD(R) < 0.0)
            if inside.any():
                X[r, inside] = _surface(t, R[inside], lift[inside] if np.ndim(lift) else lift)
        else:  # (the fall spans: only pushed out where it would come nearer the toile than GAP)
            inside = t.FD(R) < lift + GAP
            X[r] = R
            if inside.any():
                X[r, inside] = _surface(t, R[inside], (lift + GAP)[inside] if np.ndim(lift) else lift + GAP)
    return X


def _landing(down, R, fl, h):
    """Where along the walk down from the neck edge the fall lands: at least fl - h along the toile (the fall covers
    the stand, then lies on), and as far as a stiff span of fl from the roll R reaches (where the toile falls away from
    the roll, as over the shoulder at the side neck, the span lies out further than a walk that hugs the neck's side)."""
    s = np.r_[0, np.cumsum(np.linalg.norm(np.diff(down, axis=0), axis=1))]
    far = np.nonzero(np.linalg.norm(down - R, axis=1) >= fl)[0]
    a = float(s[far[0]]) if len(far) else float(s[-1])
    return max(fl - h, a, GAP)


def traced_outer(t, tr, sh):
    """The collar's OUTER EDGE as the reference shows it in front of the side neck point (front view, x z): the notch
    trace past its first corner (the collar point) on up toward the neck, moved with the closure, as far as it lies over
    cloth (R3f-8: above that the trace is the fall's silhouette standing beside the neck, not an edge lying on the toile:
    lowered straight down onto the shoulder it stood the collar up as an ear); from the collar point. None if it has no
    part. Also (the whole trace, densified: the silhouette the fall reaches out to behind the side neck point)."""
    P = past_corner(tr)
    P = P + np.c_[sh(P[:, 1]), np.zeros(len(P))]
    if len(P) < 2:
        return None, None
    D, _ = _resample(P, max(8, int(np.linalg.norm(np.diff(P, axis=0), axis=1).sum() / 0.002)))
    on = [_on_cloth(t, q) for q in D]
    k = int(np.argmin(on)) if not all(on) else len(D)
    return (D[:k] if k >= 2 else None), D


def _on_cloth(t, xz):
    """Is there toile (below its neckline) under the front-view point (x, z)?"""
    P = t.front_hit([xz[0]], [xz[1]])[0]
    return bool(abs(P[0] - xz[0]) < 0.01 and t.phi_neck(P[None])[0] >= 0 and t.FD(P[None])[0] < 0.003)


def x_trace(D, z):
    """The silhouette's x at height z (front view; D from traced_outer, |x| growing as z falls)."""
    o = np.argsort(D[:, 1])
    return float(np.interp(z, D[o, 1], np.abs(D[o, 0])))


def land_out(t, B, D, off, reach=0.12):
    """Where the fall behind the side neck point lands to show the reference's silhouette (R3f-8): from the neck edge B
    out over the shoulder (horizontally away from the neck, on the toile) to where its front view crosses the traced
    silhouette D; None if it doesn't within reach."""
    d = np.r_[B[:2] - t.cn, 0.0]
    d /= np.linalg.norm(d) + 1e-12
    for k in range(1, int(reach / STEP)):
        P = t.onto((B + k * STEP * d)[None])[0]
        if abs(P[0]) >= x_trace(D, P[2]):
            return P + off * t.grad(P[None])[0]
    return None


def land_traced(t, xz, y_hint, off, step=0.002):
    """The toile point under a traced front-view point (x, z): the front's surface there, lowered at that x until it is
    on the toile (below its neckline: above it the collar can't lie on cloth), off its surface by off."""
    x, z = float(xz[0]), float(xz[1])
    for _ in range(60):
        P = t.front_hit([x], [z])[0]
        if abs(P[0] - x) < 0.01 and t.phi_neck(P[None])[0] >= 0 and P[1] < y_hint + 0.04:
            break
        z -= step
    return P + off * t.grad(P[None])[0]


def edge_run(V, F, keep, a, b, m):
    """(m, 3) or None: a mesh's free edge where keep(points) holds, in its loop's order, from a to b (a and b added)."""
    from .toile_geom import boundary_loops
    V = np.asarray(V, float)
    best = None
    for lp in boundary_loops(np.asarray(F, int)):
        lp = np.asarray(lp, int)
        on = keep(V[lp])
        if on.sum() >= 4 and (best is None or on.sum() > best[1].sum()):
            best = (lp, on)
    if best is None:
        return None
    lp, on = best
    if not on.all():
        r = int(np.argmin(on))  # (start the loop at a point off the run: the run is contiguous after it)
        lp, on = np.roll(lp, -r), np.roll(on, -r)
    P = V[lp[on]]
    if np.linalg.norm(P[0] - a) > np.linalg.norm(P[-1] - a):
        P = P[::-1]
    return _resample(np.r_[np.asarray(a)[None], P, np.asarray(b)[None]], m)[0]


def front_neck_edge(t, toile, E0, R0, m):
    """(m, 3): the front's neck, the over front's own free edge from the neck seam's end E0 down to the gorge point R0
    (the front neckline toile_style.front_neck cut: the collar's neck edge IS the front's, so the seam is equal); the
    surface chord E0 -> R0 when the toile has no such edge (no opening)."""
    xe = getattr(t, "x_edge", None)
    keep = lambda P: ((P[:, 0] > 0) & (P[:, 1] < t.yc) & (P[:, 2] > R0[2] - NECK_ON_M) & (P[:, 2] < E0[2] + NECK_ON_M)
                      & (np.abs(P[:, 0] - xe(P[:, 2])) < 1.5 * NECK_ON_M))
    E = edge_run(*toile, keep, E0, R0, m) if xe is not None else None
    return t.onto(E0 + np.multiply.outer(np.linspace(0, 1, m), R0 - E0)) if E is None else E


def gorge_edge(t, R0, G3, m):
    """(m, 3) or None: the lapel's own top edge (its gorge) from the gorge point R0 to the gorge corner G3."""
    lm, zl = getattr(t, "lapel_mesh", None), (getattr(t, "lapel_geom", None) or {}).get("z_line")
    if lm is None or zl is None:
        return None
    keep = lambda P: ((P[:, 2] > zl(P[:, 0]) - 1.5 * NECK_ON_M) & (P[:, 0] > R0[0] - NECK_ON_M)
                      & (P[:, 0] < G3[0] + NECK_ON_M))
    return edge_run(*lm, keep, R0, G3, m)

def _out(t, L, B, SIL, off, w):
    """The fall's landing L behind the side neck point, carried out over the shoulder toward the reference's
    silhouette (land_out) by w (0 at SPAN_FROM, 1 at the side neck point, smoothstep); never pulled back in."""
    w = float(np.clip(w, 0, 1))
    if SIL is None or w <= 0:
        return L
    Lo = land_out(t, B, SIL, off)
    if Lo is None or np.hypot(*(Lo[:2] - t.cn)) <= np.hypot(*(L[:2] - t.cn)):
        return L
    w = w * w * (3 - 2 * w)
    return t.onto(((1 - w) * L + w * Lo)[None])[0] + off * t.grad(L[None])[0]


def corner_row(runs, n):
    """(n, 3) points and their arc lengths along the runs joined end to end, a point ON every join (the corners: the
    side neck point, the gorge point), the n - 1 spans shared by length (each run at least one)."""
    L = np.array([float(np.linalg.norm(np.diff(R, axis=0), axis=1).sum()) for R in runs])
    k = np.maximum(1, np.round((n - 1) * L / L.sum()).astype(int))
    k[np.argmax(k)] += (n - 1) - int(k.sum())
    P, S, s0 = [], [], 0.0
    for i, (R, ki) in enumerate(zip(runs, k)):
        Ri, si = _resample(np.asarray(R, float), ki + 1)
        P.append(Ri if i == 0 else Ri[1:])
        S.append(s0 + (si if i == 0 else si[1:]))
        s0 += L[i]
    return np.concatenate(P), np.concatenate(S)


def stand_seen(V, F, grid, toile, cols, view="front", mpp=0.001):
    """% of the stand in the columns cols (the side neck point -> the gorge point: its faces' sample points) seen from
    the front, past the fall and the toile (R3f-8: a suit collar's fall covers its stand; a stand standing round the
    neck reads as a shirt's)."""
    from .toile_geom import VIEWS, _BARY, zbuffer
    nr, nc, ks = grid
    row = np.arange(len(F)) // (2 * (nc - 1))
    col = (np.arange(len(F)) % (2 * (nc - 1))) // 2
    S = np.einsum("bk,fkd->fbd", _BARY, V[F[(row < ks) & cols[col]]]).reshape(-1, 3)
    if not len(S):
        return 0.0
    U, D = np.array(VIEWS[view][0], float), np.array(VIEWS[view][1], float)
    box = ((float((S @ U).min()) - 0.01, float((S @ U).max()) + 0.01), (float(S[:, 2].min()) - 0.01, float(S[:, 2].max()) + 0.01))
    _, zb = zbuffer([(np.asarray(toile[0], float), np.asarray(toile[1], int), np.zeros((len(toile[1]), 3))),
                     (V, F[row >= ks], np.zeros(((row >= ks).sum(), 3)))], view, box, mpp)
    u = ((S @ U - box[0][0]) / mpp).astype(int)
    v = ((box[1][1] - S[:, 2]) / mpp).astype(int)
    seen = S @ D < zb[np.clip(v, 0, zb.shape[0] - 1), np.clip(u, 0, zb.shape[1] - 1)] - 0.001
    return round(100.0 * float(seen.mean()), 1)


def _unit(v):
    return v / (np.linalg.norm(v) + 1e-12)


def drape(t, toile):
    """(V, F) of the collar (both halves) and its numbers in t.info["collar"] (module doc)."""
    d = t.d["collar"]
    stand, fall = float(d["stand_mm"]) / 1000, float(d["fall_mm"]) / 1000
    if fall <= stand:
        raise CollarRefused(f"collar: fall {fall * 1000:.0f} mm is no deeper than the stand {stand * 1000:.0f} mm: it can't "
                            "cover the neck seam")
    tr = t.inp.traces.get(d["notch"])
    if tr is None or not (tr.get("corners") or []):
        raise CollarRefused(f"collar.notch: {d['notch']!r} must be a step-2 trace with a corner (the collar point)")
    rl = getattr(t, "roll_line", None)
    if rl is None or len(rl) < 4:
        raise CollarRefused("collar: needs the lapel's roll line (garment_toile part \"lapel\"): the collar's roll line "
                            "continues it")
    rl = np.asarray(rl, float)
    sh = t.lapel_geom["shift"]
    NT = to_corner(tr)
    NT = NT + np.c_[sh(NT[:, 1]), np.zeros(len(NT))]
    Q, i_hps = neck_half(t, toile)
    G2, P2 = NT[0], NT[-1]
    E0, R0 = Q[-1], rl[-1]  # (the neck seam's end; the lapel's roll line's top: the gorge point)
    m = 40
    ramp = np.linspace(0, 1, m)
    front = front_neck_edge(t, toile, E0, R0, m)  # (the front's neck: the toile's own edge down to the gorge point)
    G3 = t.front_hit([G2[0]], [G2[1]])[0]
    gorge = gorge_edge(t, R0, G3, m)  # (the lapel's own top, the gorge point -> the gorge corner)
    if gorge is None:
        gorge = t.onto(R0 + np.multiply.outer(ramp, G3 - R0))
        gorge = gorge + (LAPEL_LIFT_M * np.minimum(1, 4 * ramp))[:, None] * t.grad(gorge)
    Pc = t.front_hit([P2[0]], [P2[1]])[0]
    Pc = Pc + (LAPEL_LIFT_M + GAP) * t.grad(Pc[None])[0]
    o_len = lambda Z: float(np.linalg.norm(np.diff(Z, axis=0), axis=1).sum())
    s_neck, s_front = o_len(Q), o_len(front)
    s_hps = o_len(Q[: i_hps + 1])
    s_rl = s_neck + s_front
    B, s = corner_row((np.r_[Q, front[1:]], gorge), NC)  # (R3f-8: a column ON the gorge point (the corner): the row
    s_end = float(s[-1])                    # is the garment's neck edge through its corners, not a chord cutting them)
    lift = np.clip((s - s_rl) / max(0.25 * (s_end - s_rl), 1e-9), 0, 1) * LAPEL_LIFT_M  # (on the lapel past the gorge point)
    T = np.gradient(B, axis=0)
    for _ in range(SMOOTH):
        T[1:-1] = 0.25 * T[:-2] + 0.5 * T[1:-1] + 0.25 * T[2:]
    T /= np.linalg.norm(T, axis=1, keepdims=True)
    OT, SIL = traced_outer(t, tr, sh)
    h_side = SIDE_STAND * stand
    if SIL is not None:  # (R3f-8: the roll at the side neck point reaches the collar's top beside the neck as the
        h_side = float(np.clip(SIL[:, 1].max() - E0[2], h_side, 2 * stand))  # reference shows it (the trace's top))
    u = np.clip(s / max(s_neck, 1e-9), 0, 1)
    wf = np.clip((s - s_neck) / max(s_rl - s_neck, 1e-9), 0, 1)  # (R3f-8: in front of the side neck point the stand
    h = np.where(s <= s_neck, h_side + (stand - h_side) * np.cos(0.5 * np.pi * u) ** 2,  # still leans back against the
                 np.maximum(h_side * np.cos(0.5 * np.pi * wf) ** 2, H_MIN))             # neck, to nothing at the gorge)
    # THE ONE ROLL LINE: the lapel's roll line carried straight on up past its top (the gorge point) to the side stand's
    # height; from there round the back, leaving the neck at SPAN_FROM, walked up the neck at h to CB; no stand past the
    # gorge point (the collar end lies on the lapel)
    T_r0 = _unit(rl[-1] - rl[-4])  # (up the lapel's roll line at its top)
    s_b = SPAN_FROM * s_neck
    k_b = int(np.searchsorted(s, s_b))
    span = np.zeros(NC, bool)
    X = np.zeros((KS + KF + 1, NC, 3))
    tf = np.clip((s - s_neck) / max(s_end - s_neck, 1e-9), 0, 1)
    for c in range(NC):
        up = _walk(t, B[c], T[c], +1, h[c], lift[c])  # (the stand on the neck / the toile up from its neck edge,
        for r in range(KS + 1):                        # all round: it leans back against the neck, the fall over it)
            X[r, c] = _at(up, h[c] * r / KS)
    end_reach = float(np.linalg.norm(Pc - B[-1]))
    fl = fall + (h[-1] + end_reach - fall) * tf  # (the fall from the roll: at the end it reaches the collar point)
    bt = np.clip((s - s_rl) / max(s_end - s_rl, 1e-9), 0, 1) ** 2
    if OT is not None:  # (in front of the side neck point the fall lands where the reference shows its outer edge)
        a_ot = np.r_[0, np.cumsum(np.linalg.norm(np.diff(OT, axis=0), axis=1))]
    for c in range(NC):
        if OT is not None and s[c] > s_neck:
            q = (s_end - s[c]) / max(s_end - s_neck, 1e-9) * a_ot[-1]
            xz = [np.interp(q, a_ot, OT[:, 0]), np.interp(q, a_ot, OT[:, 1])]
            L = land_traced(t, xz, B[c][1], lift[c] + GAP) if c < NC - 1 else Pc
            R = X[KS, c] + GAP * t.grad(X[KS, c][None])[0]
            for r in range(KS + 1, KS + KF + 1):
                X[r, c] = R + (L - R) * (r - KS) / KF
            continue
        if span[c] and s[c] <= s_rl:  # (the stand leans out to the roll: the fall lands on from the roll's foot, away
            foot = t.onto(X[KS, c][None])[0]  # from the neck, not back toward it)
            n = t.grad(foot[None])[0]
            g0 = foot - B[c]
            g0 -= (g0 @ n) * n
            if np.linalg.norm(g0) < 1e-4:
                g0 = np.cross(n, T[c])
            down = _walk(t, foot + (lift[c] + GAP) * n, np.cross(_unit(g0), n), -1, 2 * fl[c], lift[c] + GAP, aim=Pc, b=bt[c])
            L = _at(down, max(fl[c] - float(np.linalg.norm(X[KS, c] - foot)), GAP))  # (over the roll to its foot, the rest on)
            L = _out(t, (1 - bt[c]) * L + bt[c] * Pc, B[c], SIL, lift[c] + GAP, (s[c] - s[k_b]) / max(s_neck - s[k_b], 1e-9))
            R = X[KS, c] + GAP * t.grad(X[KS, c][None])[0]
            for r in range(KS + 1, KS + KF + 1):
                X[r, c] = R + (L - R) * (r - KS) / KF
            continue
        down = _walk(t, B[c] + GAP * t.grad(B[c][None])[0], T[c], -1, 2 * fl[c], lift[c] + GAP, aim=Pc, b=bt[c])
        R = X[KS, c] + GAP * t.grad(X[KS, c][None])[0]
        L = _at(down, _landing(down, R, fl[c], h[c]))  # (the fall comes back over the stand, then lies OUT on the toile
        L = (1 - bt[c]) * L + bt[c] * Pc       # for the rest of its width: over the shoulders, its outer edge long)
        L = _out(t, L, B[c], SIL, lift[c] + GAP, (s[c] - s[k_b]) / max(s_neck - s[k_b], 1e-9))
        for r in range(KS + 1, KS + KF + 1):
            X[r, c] = R + (L - R) * (r - KS) / KF  # (a span from the roll: the fall bridges the hollow at the neck's foot)
    X = fair_rows(t, X, KS, lift, span)
    nr = KS + KF + 1
    XR = X[:, ::-1] * MIR
    Xf = np.concatenate([XR[:, :-1], X], axis=1)  # (columns: the right end -> CB -> the left end)
    nc = Xf.shape[1]
    F = []
    for r in range(nr - 1):
        for c in range(nc - 1):
            a, b, cc, dd = r * nc + c, r * nc + c + 1, (r + 1) * nc + c + 1, (r + 1) * nc + c
            F += [[a, cc, b], [a, dd, cc]]
    V = Xf.reshape(-1, 3)
    t.collar_grid = (nr, nc, KS)
    outer = X[-1]
    k_rl = max(1, int(np.searchsorted(s, s_rl)) - 1)
    k_side = int(np.argmin(np.abs(s - s_hps)))
    sd = t.FD(outer) - GAP - lift
    t.info["collar"] = {
        "stand_mm": stand * 1000, "fall_mm": fall * 1000, "notch": d["notch"],
        "neck_half_mm": round(s_neck * 1000, 1), "front_neck_mm": round(s_front * 1000, 1),
        "gorge_mm": round((s_end - s_rl) * 1000, 1), "stand_side_mm": round(h_side * 1000, 1),
        "roll_front_mm": round(o_len(X[KS][s > s_neck]) * 1000, 1),
        "roll_join_deg": round(float(np.degrees(np.arccos(np.clip(_unit(X[KS, k_rl] - X[KS, k_rl - 1]) @ -T_r0, -1, 1)))), 1),
        "outer_out_side_mm": round(float(np.hypot(*(outer[k_side, :2] - t.cn)) - np.hypot(*(B[k_side, :2] - t.cn))) * 1000, 1),
        "hps_from_cb_mm": round(s_hps * 1000, 1), "end_fall_mm": round(fl[-1] * 1000, 1),
        "roll_half_mm": round(o_len(X[KS]) * 1000, 1), "outer_half_mm": round(o_len(outer) * 1000, 1),
        "outer_behind_half_mm": round(o_len(outer[s <= s_hps]) * 1000, 1),
        "outer_off_toile_mm": [round(float(np.abs(sd).mean()) * 1000, 2), round(float(np.abs(sd).max()) * 1000, 2)],
        "lands_below_seam_cb_mm": round(float(B[0, 2] - outer[0, 2]) * 1000, 1),
        "roll_above_seam_cb_mm": round(float(X[KS, 0, 2] - B[0, 2]) * 1000, 1),
        "collar_point_miss_mm": round(float(np.linalg.norm(outer[-1] - Pc)) * 1000, 1),
        "grid": [nr, nc, KS]}
    F = np.asarray(F, int)
    m = (s > s_neck) & (s <= s_rl)
    t.info["collar"]["stand_seen_front_pct"] = stand_seen(V, F, (nr, nc, KS), toile, np.r_[m[::-1][:-1], m])
    return V, F
