"""The toile's COLLAR (step 4, R3f, C497): draped on the toile as a part, as a tailor drapes it on the stand, never
drafted flat and fitted afterwards (R2-R3e drafted it flat at step 6 and fitted it round the neck: it always stood round
the neck like a ruffled band). Step 6 cuts it and unfolds the fall about the roll line (cut_collar.py).

THE DECLARATION (garment_toile's `collar`, needs "lapel"): {"stand_mm", "fall_mm" (both at CB, read off the reference),
"notch": a step-2 trace from the collar end's gorge corner to the collar point (its first corner)}.
THE NECK EDGE (one half, CB -> the collar end, mirrored for the other): the toile's neck seam (the toile mesh's free edge
along the neckline: the body pieces' own neck edge) from CB round to the over front's corner (the roll line carried up
meets it: the gorge's top), then the GORGE across the lapel's top to the notch trace's first point (the gorge corner:
where the collar end sits on the lapel).
THE STAND rises from each neck-edge point ON the toile's surface above the seam (the neck: it leans back with the neck),
square to the neck edge, by h(s): stand_mm behind the side neck point, tapering to H_MIN at the collar end; its top is
the ROLL LINE. THE FALL turns down at the roll line: back down over the stand GAP outside it, then on down over the toile
(the shoulders, the back below the neck seam; the lapel in front) square to the neck edge, GAP off it: its width
(fall_mm at CB: roll to outer edge along the cloth) covers the stand (h) and LIES OUT on the toile for the rest, walked
along the surface (R3f-2: a span of fall_mm from the roll landed 9.8 mm below the seam, close round the neck: a band,
outer x0.996 the neck flat; a tailored collar's fall lies out over the shoulders, its outer edge ~1.2-1.3 x the neck
edge). Between the roll and that outer edge the fall is a SPAN (stiff cloth bridges the hollow at the neck's foot;
hugging it made a fold the flat can't keep: 12 % strain), pushed out only where it would come nearer the toile than GAP; at the collar end it reaches the collar point (the notch trace's corner), the last columns'
walks turned toward it. The fall's OUTER EDGE is wherever the fall lands on the toile: its length follows, not a rule.
The mesh is one grid (rows: neck edge -> roll -> outer edge; columns: the right end -> CB -> the left end), folded at
the roll row; t.collar_grid = (rows, columns, the roll row). Nothing here knows a garment."""
from __future__ import annotations

import numpy as np

from .toile_style import LAPEL_LIFT_M, MIR, to_corner

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


def _hermite(P0, T0, P1, T1, w):
    """Points of the cubic from P0 (tangent T0) to P1 (tangent T1) at w (0..1); tangents scaled by the chord."""
    L = float(np.linalg.norm(P1 - P0))
    w = np.asarray(w, float)[:, None]
    h00, h10, h01, h11 = 2 * w**3 - 3 * w**2 + 1, w**3 - 2 * w**2 + w, -2 * w**3 + 3 * w**2, w**3 - w**2
    return h00 * P0 + h10 * L * T0 + h01 * P1 + h11 * L * T1


def _landing(down, R, fl, h):
    """Where along the walk down from the neck edge the fall lands: at least fl - h along the toile (the fall covers
    the stand, then lies on), and as far as a stiff span of fl from the roll R reaches (where the toile falls away from
    the roll, as over the shoulder at the side neck, the span lies out further than a walk that hugs the neck's side)."""
    s = np.r_[0, np.cumsum(np.linalg.norm(np.diff(down, axis=0), axis=1))]
    far = np.nonzero(np.linalg.norm(down - R, axis=1) >= fl)[0]
    a = float(s[far[0]]) if len(far) else float(s[-1])
    return max(fl - h, a, GAP)


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
    front = t.onto(E0 + np.multiply.outer(ramp, R0 - E0))  # (the front's neck: the toile's edge down to the gorge point)
    G3 = t.front_hit([G2[0]], [G2[1]])[0]
    gorge = t.onto(R0 + np.multiply.outer(ramp, G3 - R0))  # (the lapel's top, the gorge point -> the gorge corner)
    gorge = gorge + (LAPEL_LIFT_M * np.minimum(1, 4 * ramp))[:, None] * t.grad(gorge)
    Pc = t.front_hit([P2[0]], [P2[1]])[0]
    Pc = Pc + (LAPEL_LIFT_M + GAP) * t.grad(Pc[None])[0]
    o_len = lambda Z: float(np.linalg.norm(np.diff(Z, axis=0), axis=1).sum())
    s_neck, s_front = o_len(Q), o_len(front)
    s_hps = o_len(Q[: i_hps + 1])
    s_rl = s_neck + s_front
    B, s = _resample(np.r_[Q, front[1:], gorge[1:]], NC)
    s_end = float(s[-1])
    lift = np.clip((s - s_rl) / max(0.25 * (s_end - s_rl), 1e-9), 0, 1) * LAPEL_LIFT_M  # (on the lapel past the gorge point)
    T = np.gradient(B, axis=0)
    for _ in range(SMOOTH):
        T[1:-1] = 0.25 * T[:-2] + 0.5 * T[1:-1] + 0.25 * T[2:]
    T /= np.linalg.norm(T, axis=1, keepdims=True)
    h_side = SIDE_STAND * stand
    u = np.clip(s / max(s_neck, 1e-9), 0, 1)
    h = np.where(s <= s_neck, h_side + (stand - h_side) * np.cos(0.5 * np.pi * u) ** 2, H_MIN)
    # THE ONE ROLL LINE: the lapel's roll line carried straight on up past its top (the gorge point) to the side stand's
    # height; from there round the back, leaving the neck at SPAN_FROM, walked up the neck at h to CB; no stand past the
    # gorge point (the collar end lies on the lapel)
    T_r0 = _unit(rl[-1] - rl[-4])  # (up the lapel's roll line at its top)
    RH = R0 + (E0[2] + h_side - R0[2]) / max(T_r0[2], 1e-3) * T_r0  # (that line carried straight on to the side stand's
    s_b = SPAN_FROM * s_neck                                         # height above the seam's end)
    k_b = int(np.searchsorted(s, s_b))
    up_b = _walk(t, B[k_b], T[k_b], +1, h[k_b], lift[k_b])
    Pb = _at(up_b, h[k_b])  # (the roll walked up the neck where it starts to leave it)
    span = s > s[k_b]
    X = np.zeros((KS + KF + 1, NC, 3))
    tf = np.clip((s - s_neck) / max(s_end - s_neck, 1e-9), 0, 1)
    for c in range(NC):
        if s[c] <= s[k_b] or s[c] > s_rl:
            up = _walk(t, B[c], T[c], +1, h[c], lift[c])
            for r in range(KS + 1):
                X[r, c] = _at(up, h[c] * r / KS)
            continue
        if s[c] <= s_neck:  # (round the neck to the side: one curve, leaving the neck for the lapel's roll line)
            w = (s[c] - s[k_b]) / max(s_neck - s[k_b], 1e-9)
            Rr = _hermite(Pb, T[k_b], RH, -T_r0, [w])[0]
        else:               # (in front: the lapel's roll line itself, carried straight up from its top)
            Rr = RH + (R0 - RH) * (s[c] - s_neck) / max(s_front, 1e-9)
        if t.FD(Rr[None])[0] < lift[c]:
            Rr = _surface(t, Rr[None], lift[c])[0]
        h[c] = float(np.linalg.norm(Rr - B[c]))
        for r in range(KS + 1):
            X[r, c] = B[c] + (Rr - B[c]) * r / KS
    end_reach = float(np.linalg.norm(Pc - B[-1]))
    fl = fall + (h[-1] + end_reach - fall) * tf  # (the fall from the roll: at the end it reaches the collar point)
    bt = np.clip((s - s_rl) / max(s_end - s_rl, 1e-9), 0, 1) ** 2
    for c in range(NC):
        if span[c] and s[c] <= s_rl:  # (the stand leans out to the roll: the fall lands on from the roll's foot, away
            foot = t.onto(X[KS, c][None])[0]  # from the neck, not back toward it)
            n = t.grad(foot[None])[0]
            g0 = foot - B[c]
            g0 -= (g0 @ n) * n
            if np.linalg.norm(g0) < 1e-4:
                g0 = np.cross(n, T[c])
            down = _walk(t, foot + (lift[c] + GAP) * n, np.cross(_unit(g0), n), -1, 2 * fl[c], lift[c] + GAP, aim=Pc, b=bt[c])
            L = _at(down, _landing(down, X[KS, c], fl[c], 0.0))
            L = (1 - bt[c]) * L + bt[c] * Pc
            R = X[KS, c] + GAP * t.grad(X[KS, c][None])[0]
            for r in range(KS + 1, KS + KF + 1):
                X[r, c] = R + (L - R) * (r - KS) / KF
            continue
        down = _walk(t, B[c] + GAP * t.grad(B[c][None])[0], T[c], -1, 2 * fl[c], lift[c] + GAP, aim=Pc, b=bt[c])
        R = X[KS, c] + GAP * t.grad(X[KS, c][None])[0]
        L = _at(down, _landing(down, R, fl[c], h[c]))  # (the fall comes back over the stand, then lies OUT on the toile
        L = (1 - bt[c]) * L + bt[c] * Pc       # for the rest of its width: over the shoulders, its outer edge long)
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
    k_side = int(np.argmin(np.abs(s - s_neck)))
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
    return V, np.asarray(F, int)
