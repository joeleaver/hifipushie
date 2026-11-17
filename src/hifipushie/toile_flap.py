"""The toile's TURNED FLAP (step 4, R3f-9, C508): the lapels and the collar draped as ONE piece turned back about ONE
roll line, as a tailor sees it ("it's all supposed to be one piece with the lapels", Joe). R3f..R3f-8 draped the lapel
(toile_style) and the collar (toile_collar) as two parts: every collar fault lived at their joint (the roll kinked 40 deg
where the collar's roll met the lapel's, the gorge seam 7 mm open, the fall short of its roll).

THE ROLL LINE (one curve, left half; mirrored): from the break up the lapel's roll line (step 2's roll trace, moved with
the closure) to its top (the gorge point R0, on the neck edge), on up and round, tangent-continuous (a cubic Hermite
leaving R0 the way the lapel's roll arrives), to the side neck point at the stand's side height, then round the back of
the neck at the stand's height to CB (walked up the neck from the neck seam as toile_collar's stand: stand_mm at CB, the
collar's top beside the neck at the side read off the notch trace's top).
THE STAND (inside the roll, at the neck only): from the neck edge (the toile's neck seam CB -> the side neck point, then
the front's own neck edge down to R0) up to the roll: it leans back against the neck and dies out to nothing at R0,
where the roll comes down onto the chest.
OUTSIDE THE ROLL (turned back, lying on the toile): one region declared by its outer edge: round the back the collar's
fall (toile_collar's landing: over the stand, out on the shoulders to the reference's silhouette), in front the fall's
edge landing on the notch trace down to the collar point; the NOTCH (its bottom, the gorge corner: the notch trace's
first point); then the lapel's outer edge (toile_style.lapel_outline: from the lapel point, where its edge meets its
top, down to the break).
THE GORGE: one grid column from R0 (on the roll) to the gorge corner (on the outer edge), along the lapel's top; the
collar's columns lie behind it, the lapel's below it. Step 5's gorge mark is that column (mark_flap.py): both sides of
the gorge seam are the same vertices, equal by construction.
The mesh (one part, "flap"): the collar block, a grid (rows: neck edge -> roll (KS) -> outer edge; columns: the right
gorge -> CB -> the left gorge), and each lapel block (rows: the roll -> its outer edge; columns: the gorge -> the break),
sharing the gorge column's vertices; t.flap_layout = [rows, collar columns, roll row, lapel columns]. Numbers in
t.info["collar"] (the collar region) and t.info["flap"] (the roll's smoothness, the stand seen from the front, the
lapel's width). Nothing here knows a garment."""
from __future__ import annotations

import numpy as np

from .toile_collar import (GAP, H_MIN, KF, KS, NC, SIDE_STAND, SMOOTH, SPAN_FROM, CollarRefused, _at, _landing, _out,
                           _unit, _walk, corner_row, fair_rows, front_neck_edge, land_traced, neck_half, stand_seen,
                           traced_outer)
from .toile_style import LAPEL_LIFT_M, MIR, to_corner

NL = 24  # lapel columns (the gorge -> the break)
ROLL_FROM = 0.5  # of the back neck from CB: the roll walked up the neck behind this; from here on it is one curve to R0


def _len(Z):
    return float(np.linalg.norm(np.diff(Z, axis=0), axis=1).sum())


def hermite(P0, T0, P1, T1, u):
    """Cubic Hermite points at u (0..1) from P0 (tangent T0) to P1 (tangent T1); the tangents scaled by the chord."""
    L = float(np.linalg.norm(P1 - P0))
    u = np.asarray(u, float)[:, None]
    h00, h10, h01, h11 = 2 * u ** 3 - 3 * u ** 2 + 1, u ** 3 - 2 * u ** 2 + u, -2 * u ** 3 + 3 * u ** 2, u ** 3 - u ** 2
    return h00 * P0 + h10 * L * T0 + h01 * P1 + h11 * L * T1


TURN_ARC_M = 0.01  # the roll's turning read between chords this long either side of a point (equal arcs: the columns'
#                   spacing differs between the collar (~6 mm) and the lapel (~20 mm))


def turn_at(R, a) -> float:
    """The roll's turning (deg) at arc length a along polyline R: the chords TURN_ARC_M before and after it."""
    p, q, r = (_at(R, x) for x in (a - TURN_ARC_M, a, a + TURN_ARC_M))
    u, v = _unit(q - p), _unit(r - q)
    return float(np.degrees(np.arccos(np.clip(u @ v, -1, 1))))


def turns(R, step=0.005) -> tuple:
    """(arc lengths, the turning there) every step along R (module doc: a kink is a large turn over a short arc)."""
    s = np.arange(TURN_ARC_M, _len(R) - TURN_ARC_M, step)
    return s, np.array([turn_at(R, a) for a in s])


def lapel_block(t, G3):
    """(KF + 1, NL, 3): the lapel outside the roll, lying on the chest (LAPEL_LIFT_M off): rows the roll -> its outer
    edge, columns the gorge (R0 -> the gorge corner G3, along its top) -> the break."""
    g = t.lapel_geom
    x_roll, x_l, z_line, z_brk, z_top = g["x_roll"], g["x_l"], g["z_line"], g["z_brk"], g["z_top"]
    zz = np.linspace(z_brk, z_top, 400)
    xl = x_l(zz)
    above = zz >= z_line(xl)  # (the lapel point: its edge meets its top)
    k = int(np.argmax(above)) if above.any() else len(zz) - 1
    Lp = np.array([xl[k], z_line(xl[k])])
    ze = np.linspace(Lp[1], z_brk, 60)
    EDGE = np.c_[x_l(ze), ze]
    g2 = np.array([G3[0], G3[2]])
    OUT, _ = corner_row((np.c_[np.linspace(g2[0], Lp[0], 8), np.linspace(g2[1], Lp[1], 8)], EDGE), NL)
    zr = np.linspace(z_top, z_brk, NL)
    ROLL = np.c_[x_roll(zr), zr]
    Y = np.zeros((KF + 1, NL, 2))
    for r in range(KF + 1):
        Y[r] = ROLL + (OUT - ROLL) * r / KF
    P = t.front_hit(Y[..., 0].ravel(), Y[..., 1].ravel())
    P = P + LAPEL_LIFT_M * t.grad(P)
    return P.reshape(KF + 1, NL, 3), Lp


def collar_block(t, toile, R0, T_r0, R0_lift):
    """(KS + KF + 1, nc, 3) the collar region, left half, columns CB -> the gorge column (its last: R0 -> the gorge
    corner, set by the caller), and its numbers (module doc; the landing as toile_collar's)."""
    d = t.d["collar"]
    stand, fall = float(d["stand_mm"]) / 1000, float(d["fall_mm"]) / 1000
    tr = t.inp.traces[d["notch"]]
    sh = t.lapel_geom["shift"]
    NT = to_corner(tr)
    NT = NT + np.c_[sh(NT[:, 1]), np.zeros(len(NT))]
    Q, i_hps = neck_half(t, toile)
    E0 = Q[-1]
    front = front_neck_edge(t, toile, E0, R0, 40)
    B, s = corner_row((Q, front), NC)
    s_neck, s_rl = _len(Q), float(s[-1])
    G3 = t.front_hit([NT[0][0]], [NT[0][1]])[0]
    Pc = t.front_hit([NT[-1][0]], [NT[-1][1]])[0]
    Pc = Pc + (LAPEL_LIFT_M + GAP) * t.grad(Pc[None])[0]
    T = np.gradient(B, axis=0)
    for _ in range(SMOOTH):
        T[1:-1] = 0.25 * T[:-2] + 0.5 * T[1:-1] + 0.25 * T[2:]
    T /= np.linalg.norm(T, axis=1, keepdims=True)
    OT, SIL = traced_outer(t, tr, sh)
    h_side = SIDE_STAND * stand
    if SIL is not None:
        h_side = float(np.clip(SIL[:, 1].max() - E0[2], h_side, 2 * stand))
    back = s <= s_neck + 1e-9
    u = np.clip(s / max(s_neck, 1e-9), 0, 1)
    h = np.where(back, h_side + (stand - h_side) * np.cos(0.5 * np.pi * u) ** 2, H_MIN)
    wf = np.clip((s - s_neck) / max(s_rl - s_neck, 1e-9), 0, 1)
    lift = LAPEL_LIFT_M * wf  # (the stand comes off the neck onto the front's cloth toward R0: lifted over it)
    X = np.zeros((KS + KF + 1, NC, 3))
    for c in np.nonzero(back)[0]:  # (round the back: the stand walked up the neck to the roll)
        up = _walk(t, B[c], T[c], +1, h[c], 0.0)
        for r in range(KS + 1):
            X[r, c] = _at(up, h[c] * r / KS)
    k_h = int(np.nonzero(back)[0][-1])
    fr = np.nonzero(~back)[0]
    fl = np.full(NC, fall)
    k_b = int(np.searchsorted(s, SPAN_FROM * s_neck))
    k_r = int(np.searchsorted(s, ROLL_FROM * s_neck))
    X[:KS + 1, :k_r + 1] = fair_rows(t, X[:, :k_r + 1].copy(), KS, lift[:k_r + 1])[:KS + 1]  # (the stand faired)
    # THE ONE ROLL LINE from ROLL_FROM of the back neck on: on from the (faired) back's roll, tangent-continuous, past
    # the side neck point down to R0, arriving the way the lapel's roll leaves it (no kink at the old join; the turn
    # from round the neck to down the chest spread over the whole arc, not taken at the side neck point); never
    # re-faired (a fairing with its ends held bends the ends' tangents back toward the chord)
    hc = np.arange(k_r + 1, NC - 1)
    P0 = X[KS, k_r]
    T0 = _unit(X[KS, k_r] - X[KS, k_r - 2])
    uu = (s[hc] - s[k_r]) / max(s_rl - s[k_r], 1e-9)
    Hs = t.onto(hermite(P0, T0, R0_lift, -T_r0, uu))
    Hs = Hs + lift[hc, None] * t.grad(Hs)
    for i, c in enumerate(hc):
        for r in range(KS + 1):
            p = B[c] + (Hs[i] - B[c]) * r / KS
            X[r, c] = t.onto(p[None])[0] + (lift[c] * r / KS) * t.grad(p[None])[0]
        X[KS, c] = Hs[i]
        h[c] = float(np.linalg.norm(Hs[i] - B[c]))
    for c in range(k_h + 1):  # (round the back: the fall over the stand, out on the shoulders)
        R = X[KS, c] + GAP * t.grad(X[KS, c][None])[0]
        down = _walk(t, B[c] + GAP * t.grad(B[c][None])[0], T[c], -1, 2 * fl[c], GAP)
        L = _at(down, _landing(down, R, fl[c], h[c]))
        L = _out(t, L, B[c], SIL, GAP, (s[c] - s[k_b]) / max(s_neck - s[k_b], 1e-9))
        for r in range(KS + 1, KS + KF + 1):
            X[r, c] = R + (L - R) * (r - KS) / KF
    X[KS + 1:, :k_h + 1] = fair_rows(t, X[:, :k_h + 1].copy(), KS, lift[:k_h + 1])[KS + 1:]  # (the fall faired)
    if OT is not None:
        a_ot = np.r_[0, np.cumsum(np.linalg.norm(np.diff(OT, axis=0), axis=1))]
    s_pc = float(s[-2])  # (the column before the gorge column reaches the collar point)
    for c in fr[:-1]:  # (in front: the fall lands on the reference's outer edge, down to the collar point)
        R = X[KS, c] + GAP * t.grad(X[KS, c][None])[0]
        if c == NC - 2 or OT is None:
            L = Pc
        else:
            q = (s_pc - s[c]) / max(s_pc - s_neck, 1e-9) * a_ot[-1]
            L = land_traced(t, [np.interp(q, a_ot, OT[:, 0]), np.interp(q, a_ot, OT[:, 1])], B[c][1], lift[c] + GAP)
        for r in range(KS + 1, KS + KF + 1):
            X[r, c] = R + (L - R) * (r - KS) / KF
    for r in range(KS + 1):  # (the gorge column's stand: R0, standing H_MIN off it)
        X[r, -1] = R0 + (R0_lift - R0) * r / KS
    geo = dict(s=s, s_neck=s_neck, s_rl=s_rl, h=h, h_side=h_side, i_hps=k_h, B=B, Pc=Pc, G3=G3, stand=stand, fall=fall,
               s_front=_len(front))
    return X, geo


def _grid_faces(idx):
    """Faces of a grid of vertex ids idx (rows, cols): two per cell, R3f-8's winding."""
    F = []
    for r in range(idx.shape[0] - 1):
        for c in range(idx.shape[1] - 1):
            a, b, cc, dd = idx[r, c], idx[r, c + 1], idx[r + 1, c + 1], idx[r + 1, c]
            F += [[a, cc, b], [a, dd, cc]]
    return np.asarray(F, int)


def assemble(X, Y):
    """(V, F, layout): the collar block X (left half, CB first) mirrored into the full collar grid, the lapel blocks
    (Y: left; its mirror) sharing the gorge columns' vertices."""
    nr, ncb = X.shape[:2]
    Xf = np.concatenate([(X[:, ::-1] * MIR)[:, :-1], X], axis=1)
    ncf = Xf.shape[1]
    nl = Y.shape[1]
    V = [Xf.reshape(-1, 3)]
    n0 = nr * ncf
    idx_c = np.arange(n0).reshape(nr, ncf)
    YL = Y[:, 1:].reshape(-1, 3)
    YR = (Y[:, 1:] * MIR).reshape(-1, 3)
    V += [YL, YR]
    idx_l = np.c_[idx_c[KS:, -1], n0 + np.arange(len(YL)).reshape(KF + 1, nl - 1)]
    idx_r = np.c_[idx_c[KS:, 0], n0 + len(YL) + np.arange(len(YR)).reshape(KF + 1, nl - 1)]
    F = np.r_[_grid_faces(idx_c), _grid_faces(idx_l), _grid_faces(idx_r)[:, ::-1]]
    return np.concatenate(V), F, (nr, ncf, KS, nl)


def drape(t, toile):
    """(V, F) of the one flap (both halves); t.flap_layout; numbers in t.info["collar"] / ["flap"] (module doc)."""
    d = t.d["collar"]
    if float(d["fall_mm"]) <= float(d["stand_mm"]):
        raise CollarRefused(f"collar: fall {d['fall_mm']} mm is no deeper than the stand {d['stand_mm']} mm: it can't "
                            "cover the neck seam")
    tr = t.inp.traces.get(d["notch"])
    if tr is None or not (tr.get("corners") or []):
        raise CollarRefused(f"collar.notch: {d['notch']!r} must be a step-2 trace with a corner (the collar point)")
    rl = np.asarray(t.roll_line, float)
    R0 = rl[-1]
    NT = to_corner(tr)
    G2 = NT[0] + [float(t.lapel_geom["shift"](NT[0][1])), 0.0]
    G3 = t.front_hit([G2[0]], [G2[1]])[0]
    Y, Lp = lapel_block(t, G3)
    R0_lift = Y[0, 0]
    T_r0 = _unit(Y[0, 0] - Y[0, 1])  # (up the lapel's roll as it lies, at its top: the collar's roll leaves it so)
    X, geo = collar_block(t, toile, R0, T_r0, R0_lift)
    X[KS:, -1] = Y[:, 0]  # (the gorge column: the lapel's, one set of vertices)
    V, F, lay = assemble(X, Y)
    t.flap_layout = lay
    s, s_neck, B = geo["s"], geo["s_neck"], geo["B"]
    outer, roll = X[-1], X[KS]
    ROLL = np.r_[roll, Y[0, 1:]]  # (CB -> the side neck point -> R0 -> the break)
    sa, tn = turns(ROLL)
    s_join = _len(roll)  # (R0: where R3f-8's collar roll met the lapel's)
    kg = NC - 1
    k_side = geo["i_hps"]
    sd = t.FD(outer[s <= s_neck]) - GAP  # (round the back: the fall lies on the toile)
    nr, ncf = lay[0], lay[1]
    m = (s > s_neck) & (np.arange(NC) < kg)
    seen = stand_seen(V[: nr * ncf], _grid_faces(np.arange(nr * ncf).reshape(nr, ncf)), (nr, ncf, KS), toile,
                      np.r_[m[::-1][:-1], m])
    t.info["collar"] = {
        "stand_mm": geo["stand"] * 1000, "fall_mm": geo["fall"] * 1000, "notch": d["notch"],
        "neck_half_mm": round(s_neck * 1000, 1), "front_neck_mm": round(geo["s_front"] * 1000, 1),
        "gorge_mm": round(_len(Y[:, 0]) * 1000, 1), "stand_side_mm": round(geo["h_side"] * 1000, 1),
        "roll_half_mm": round(_len(roll) * 1000, 1), "outer_half_mm": round(_len(outer[:-1]) * 1000, 1),
        "outer_behind_half_mm": round(_len(outer[s <= s_neck]) * 1000, 1),
        "outer_out_side_mm": round(float(np.hypot(*(outer[k_side, :2] - t.cn)) - np.hypot(*(B[k_side, :2] - t.cn))) * 1000, 1),
        "outer_off_toile_mm": [round(float(np.abs(sd).mean()) * 1000, 2), round(float(np.abs(sd).max()) * 1000, 2)],
        "lands_below_seam_cb_mm": round(float(B[0, 2] - outer[0, 2]) * 1000, 1),
        "roll_above_seam_cb_mm": round(float(roll[0, 2] - B[0, 2]) * 1000, 1),
        "collar_point_miss_mm": round(float(np.linalg.norm(outer[-2] - geo["Pc"])) * 1000, 1),
        "stand_seen_front_pct": seen, "grid": [nr, ncf, KS]}
    t.info["flap"] = {
        "roll_join_deg": round(turn_at(ROLL, s_join), 1), "roll_turn_max_deg": round(float(tn.max()), 1),
        "roll_turn_max_at_mm": round(float(sa[np.argmax(tn)]) * 1000, 1), "roll_join_at_mm": round(s_join * 1000, 1),
        "roll_mm": round(_len(ROLL) * 1000, 1), "turn_arc_mm": TURN_ARC_M * 1000,
        "collar_outer_over_roll": round(_len(outer[:-1]) / max(_len(roll), 1e-9), 3),
        "lapel_point": np.round(Lp * 1000, 1).tolist(), "gorge_corner": np.round(G3 * 1000, 1).tolist(),
        "lapel_width_mm": round(float(max(np.min(np.linalg.norm(Y[0] - p, axis=1)) for p in Y[-1])) * 1000, 1),
        "layout": list(lay)}
    return V, F
