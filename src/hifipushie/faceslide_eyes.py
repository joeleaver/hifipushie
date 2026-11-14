"""The eye's sliders as fields: lid margins, the fold's turn, the left eye's fields, the joint's delta. Part of the face sliders (faceslide.py has the overview)."""
from __future__ import annotations

import numpy as np

from . import faceslide
from .faceslide import _g, _quad, _ss, template, values

def _margin_fields() -> dict:
    """lid_margin_upper / _lower for the subject's LEFT eye (GNM frame, metres at +1): the exterior skin from the rim
    (the exterior's open edge round the eye, held: the lid stays seated on the ball) out ~1 mm moved forward along
    the eye's axis, full from 1.0 to 1.8 mm out along the skin, back to nothing by 5 mm; faded at the canthi. Upper /
    lower by which rim vertex is nearest (above or below the corners' line)."""
    from scipy.spatial import cKDTree
    T = template()
    X, lm = T["X"], T["lm"]
    mm = 0.001
    c_in, c_out = lm[42], lm[45]
    w = float(np.linalg.norm(c_out - c_in))
    ex = (c_out - c_in) / w
    rim = T["rim"][X[T["rim"], 0] > 0]
    d, k = cKDTree(X[rim]).query(X)
    near_rim = X[rim][k]
    u_r = (near_rim - c_in) @ ex / w  # the nearest rim vertex's place along the corners' line
    y_line = c_in[1] + np.clip(u_r, 0, 1) * (c_out[1] - c_in[1])
    upper = near_rim[:, 1] > y_line
    prof = _ss(d / (0.7 * mm)) * _ss((5.0 * mm - d) / (3.0 * mm))
    # faded toward both canthi (there the upper / lower split by nearest rim vertex is ambiguous: a step folded quads)
    ends = _ss((u_r - 0.04) / 0.25) * _ss((0.96 - u_r) / 0.25)
    for c in (c_in, c_out):
        ends = ends * _ss((np.linalg.norm(X - c, axis=1) - 2 * mm) / (5 * mm))
    m = T["ext"] & (X[:, 0] > 0.004) & (d < 5.0 * mm) & (X[:, 2] > c_in[2] - 0.02)
    fwd = np.array([0.0, 0.0, 1.0])
    base = (m * prof * ends)[:, None] * fwd[None]
    F = {"lid_margin_upper": base * upper[:, None], "lid_margin_lower": base * (~upper)[:, None]}
    return {k: v * (faceslide.UNITS[k][0] * mm) for k, v in F.items()}


def _fold_turn(X, u, h, sel, H0, NY=None):
    """The crease's height over the margin per vertex (by its u): where the lid's own profile turns into its fold (the
    most concave point of depth against height, 2.5-8.5 mm, per u band: on a hooded lid the platform meets the fold's
    underside there), else the template's H0 (a smooth, convex lid has no turn of its own)."""
    mm = 0.001
    bands = np.linspace(0.05, 1.0, 8)
    hc_b, uc_b = [], []
    for u0, u1 in zip(bands[:-1], bands[1:]):
        s = sel & (u >= u0) & (u < u1) & (h > 1.0 * mm) & (h < 11 * mm)
        if s.sum() < 4:
            continue
        hs = np.arange(1.5, 10.6, 0.5) * mm
        o = np.argsort(h[s])  # (the lid's rows are 0.7-2.5 mm apart: the profile interpolated between them)
        ny = np.interp(hs, h[s][o], NY[s][o])
        ny = np.convolve(np.r_[ny[0], ny, ny[-1]], [0.25, 0.5, 0.25], "valid")
        # the turn: going up the lid, where the skin stops facing up (the platform) and faces down (the fold's
        # underside). (By the profile's concavity the margin roll's foot at ~3 mm won on every smooth lid)
        cross = np.flatnonzero((ny[:-1] > 0) & (ny[1:] <= 0) & (hs[:-1] >= 2.0 * mm) & (hs[1:] <= 9.0 * mm))
        if len(cross):
            i = int(cross[0])
            hc_b.append(hs[i] + (hs[i + 1] - hs[i]) * ny[i] / max(ny[i] - ny[i + 1], 1e-9))
            uc_b.append(0.5 * (u0 + u1))
    if len(hc_b) < 2:
        return H0
    hc = np.interp(np.clip(u, 0, 1), uc_b, np.convolve(np.r_[hc_b[0], hc_b, hc_b[-1]], [1 / 3] * 3, "valid"))
    return np.clip(hc, 2.5 * mm, 8.5 * mm)





def _left_fields(T: dict | None = None) -> dict:
    """Every slider's field for the subject's LEFT eye (+x), GNM frame, metres at +1 (T: template() or a head's
    head_template(V): the crease then sits on that head's own fold turn)."""
    from scipy.spatial import cKDTree
    T = T or template()
    X, n, lm = T["X"], T["n"], T["lm"]
    mm = 0.001
    c_in, c_out = lm[42], lm[45]
    w = float(np.linalg.norm(c_out - c_in))
    ex = (c_out - c_in) / w
    up = np.array([0.0, 1.0, 0.0])
    fwd = np.array([0.0, 0.0, 1.0])
    u = (X - c_in) @ ex / w
    uk = lambda p: float((p - c_in) @ ex / w)  # noqa: E731
    ym = _quad(np.array([0.0, uk(lm[43]), uk(lm[44]), 1.0]), np.array([c_in[1], lm[43][1], lm[44][1], c_out[1]]))
    yl = _quad(np.array([0.0, uk(lm[47]), uk(lm[46]), 1.0]), np.array([c_in[1], lm[47][1], lm[46][1], c_out[1]]))
    yb = _quad(np.array([uk(lm[i]) for i in range(22, 27)]), np.array([lm[i][1] for i in range(22, 27)]))
    uc = np.clip(u, 0.0, 1.0)  # (past the corners the curves hold their corner's height: a parabola run on dipped
    # under the outer corner and took the hood down onto the cheek)
    h = X[:, 1] - ym(uc)
    dl = yl(uc) - X[:, 1]
    span = np.maximum(yb(u) - ym(uc), 5 * mm)
    t = h / span
    # where the eye's fields live: exterior skin, this side, in front of the eye joints, near the eye
    near = T["ext"] & (X[:, 0] > 0.004) & (X[:, 2] > c_in[2] - 0.03) & (u > -0.6) & (u < 1.6) \
        & (h < 1.6 * span) & (dl < 0.03)
    upper = near & (h > 0)
    lower = near & (dl > 0)
    # nothing at the margins: their rows are ~0.3 mm apart and roll under, and near the corners h is ill-defined (a
    # ramp in h alone gave neighbours 0.003 and 0.25 mm there: thin quads turned over). By 3D distance from the
    # opening's rim (the exterior skin's edge round the eye) as well
    dm = cKDTree(X[T["rim"]]).query(X)[0]
    keep = _ss((dm - 1.8 * mm) / (3.0 * mm))
    lid_off = _ss((h - 1.5 * mm) / (3.0 * mm)) * keep
    low_off = _ss((dl - 1.0 * mm) / (2.5 * mm)) * keep
    tang_up = up[None] - (n @ up)[:, None] * n
    tang_up /= np.maximum(np.linalg.norm(tang_up, axis=1, keepdims=True), 1e-9)
    H0 = 6.2 * mm * (1 - 0.35 * np.square(2 * uc - 1.0))  # the crease, over the margin (template: ~6.2 mm mid)
    Ec = _ss((u - 0.08) / 0.16) * _ss((0.98 - u) / 0.22)  # just past the inner canthus .. under the hood laterally
    F = {}
    m = upper * lid_off
    # crease height: the lid's skin slides up along the surface over the crease (a taller platform), nothing at the
    # margin, back to nothing 4 mm over the crease: whatever crease rides on these vertices goes with them
    bump = np.where(h < H0, _ss(h / np.maximum(H0, 1e-6)), _ss((H0 + 4 * mm - h) / (4 * mm)))
    F["eye_crease_height"] = (m * Ec * bump)[:, None] * tang_up
    # crease depth: a FOLD, not a dimple: a shallow groove at the crease line and the skin just over it coming down and
    # forward over it, so the line is in its shadow (a Gaussian dent alone, at the template's height, sat on a hooded
    # lid's fold underside where it read as a row of divots: Tess). On a head (T["own"]) the line follows its own
    # fold turn
    Hc = _fold_turn(X, u, h, upper & (dm > 1.5 * mm), H0, n[:, 1]) if T.get("own") else H0
    faceslide._CACHE["last_crease"] = (Hc, H0, u, upper)  # (diagnostics: creasechk.py)
    # (widths: every feature >= ~2.5 mm across (FWHM): a 0.55 mm groove under a 0.85 mm lip read as a thin dark CUT
    # with a bright rim, a slit not a fold; a real fold is a rounded roll of skin with a broad soft shadow under it)
    groove = -0.55 * _g(h, Hc - 0.3 * mm, 1.2 * mm)
    over = 0.9 * _g(h, Hc + 1.9 * mm, 1.4 * mm)
    od = 0.55 * n - 0.6 * up[None]
    od /= np.maximum(np.linalg.norm(od, axis=1, keepdims=True), 1e-9)
    # (held off the margin less than the other lid fields: a low crease (Tess: 3 mm over the margin) was half faded)
    mc = upper * _ss((h - 1.0 * mm) / (2.0 * mm)) * _ss((dm - 1.2 * mm) / (2.0 * mm))
    F["eye_crease_depth"] = (mc * Ec)[:, None] * (groove[:, None] * n + over[:, None] * od)
    # platform show: the fold's edge (just over the crease) up and back
    Ef = _ss((u + 0.02) / 0.15) * _ss((1.08 - u) / 0.2)
    pf = _g(h, H0 + 1.4 * mm, 1.3 * mm)
    F["eye_platform"] = (m * Ef * pf)[:, None] * (0.55 * up - 0.85 * n)
    # hood: the fold above the crease down and forward, stronger toward the outer corner and on past it
    ph = _g(h, H0 + 2.6 * mm, 2.0 * mm) * _ss((h - H0 * 0.6) / (2 * mm))
    Eh = (0.35 + 0.65 * _ss((u - 0.1) / 0.8)) * _ss((u + 0.05) / 0.15) * _ss((1.35 - u) / 0.25)
    corner = _ss((np.linalg.norm(X - c_out, axis=1) - 2.5 * mm) / (9.0 * mm))  # (the rows crowd at the corner)
    F["eye_hood"] = (m * corner * Eh * ph)[:, None] * (-0.8 * up + 0.6 * n)
    El = _ss((u - 0.55) / 0.35) * _ss((1.45 - u) / 0.25)
    F["eye_hood_lateral"] = (m * corner * El * ph)[:, None] * (-0.8 * up + 0.6 * n)
    # sulcus / upper-lid fullness: the skin between the fold and the brow, along the normal
    Es = _ss((u + 0.05) / 0.2) * _ss((1.05 - u) / 0.25)
    F["eye_sulcus"] = (upper * Es * _g(t, 0.62, 0.17) * _ss((h - H0 - 1 * mm) / (2 * mm)))[:, None] * n
    # lower lid: the bag (fat over the lid-cheek junction) and the junction's crease under it
    Eb = _ss((u - 0.02) / 0.2) * _ss((1.08 - u) / 0.28)
    F["eye_bag"] = (lower * low_off * Eb * _g(dl, 3.6 * mm, 1.7 * mm))[:, None] * n
    F["eye_lidcheek"] = (lower * low_off * Eb * -_g(dl, 7.4 * mm, 1.0 * mm))[:, None] * n
    # tear trough: from under the inner canthus down and out (in u / dl millimetres)
    a = np.array([0.02 * w, 2.0 * mm])
    b = np.array([0.42 * w, 11.0 * mm])
    q = np.c_[u * w, dl]
    sseg = np.clip(((q - a) @ (b - a)) / float((b - a) @ (b - a)), 0, 1)
    dist = np.linalg.norm(q - (a + sseg[:, None] * (b - a)), axis=1)
    taper = _ss(sseg / 0.15) * _ss((1 - sseg) / 0.35)
    F["eye_tear_trough"] = (lower * low_off * taper * -_g(dist, 0, 1.1 * mm))[:, None] * n
    # brow ridge: the skin over the supraorbital rim forward (GNM's forward), from the upper lid's top third up over
    # the brow, the glabella half (both sides add there)
    hb = X[:, 1] - (yb(u) - 2.5 * mm)
    Ebr = _ss((u + 0.35) / 0.3) * _ss((1.3 - u) / 0.3)
    F["brow_ridge"] = (near * Ebr * _g(hb, 0, 4.5 * mm) * _ss((t - 0.35) / 0.3))[:, None] * fwd[None]
    # lateral brow descent: the brow's outer half and the skin under it down (not the margin)
    Ed = _ss((u - 0.45) / 0.5) * _ss((1.55 - u) / 0.25)
    F["brow_lateral"] = (near * Ed * _ss((t - 0.12) / 0.5) * _ss((1.6 - t) / 0.35) * (h > 0))[:, None] * -up
    # canthal tilt: the fissure turned about the eyeball's own forward axis (the lids slide over the ball, never off
    # it: lifting the corner region instead opened a slot at the outer corner), whole within ~1.1 eye radii of the
    # ball's centre, fading out by 2; per unit 4 degrees (outer corner up)
    ce = T["J"][2] if T["J"][2][0] > 0 else T["J"][3]
    rel = X - ce
    rr = np.linalg.norm(rel[:, :2], axis=1)
    th = np.radians(1.0)  # (unit: UNITS is in degrees for this one)
    rot = np.c_[rel[:, 0] * np.cos(th) - rel[:, 1] * np.sin(th) - rel[:, 0],
                rel[:, 0] * np.sin(th) + rel[:, 1] * np.cos(th) - rel[:, 1], np.zeros(len(X))]
    wr = 1 - _ss((rr - 1.1 * 0.5 * w) / (0.9 * 0.5 * w))
    F["canthal_tilt"] = (T["skin"] & (X[:, 0] > 0.004) & (X[:, 2] > ce[2] - 0.01))[:, None] * wr[:, None] * rot / mm
    # epicanthal fold: the inner upper lid's skin over the inner canthus: medial, down, a little forward
    pc = c_in + 1.6 * mm * up - 0.5 * mm * ex
    r_in = np.linalg.norm(X - pc, axis=1)
    # (with the lid insides and the caruncle: they move with the corner, or the rim folds against them; the canthus
    # itself held, the fold sliding over it, with soft ramps: tighter ones creased the corner > 60 deg)
    nears = T["skin"] & (X[:, 0] > 0.004) & (X[:, 2] > c_in[2] - 0.03)
    hold_c = _ss((np.linalg.norm(X - c_in, axis=1) - 0.5 * mm) / (4.0 * mm))
    F["epicanthal"] = (nears * _ss((h + 1.5 * mm) / (3.0 * mm)) * hold_c * _g(r_in, 0, 4.5 * mm))[:, None] \
        * (-0.75 * ex - 0.55 * up + 0.3 * n)
    # eye setback: the eyeball (with the eye joint: joint_delta) and the orbit's contents (lids, their insides, the
    # canthi) back as one, fading out across the orbital rim; the brow ridge above held (Tess needed eye_depth +
    # brow_ridge together for this: a heavy brow, an identity component past 2.6 sigma)
    rxy = np.linalg.norm((X - ce)[:, :2], axis=1)
    orbit = (T["skin"] | T["eyes"]) & (X[:, 0] > 0.004) & (X[:, 2] > ce[2] - 0.03)
    w_orb = np.where(T["eyes"] & (np.linalg.norm(X - ce, axis=1) < 0.02), 1.0,
                     (1 - _ss((rxy - 0.55 * w) / (0.45 * w))) * (1 - _ss((t - 0.55) / 0.35) * (h > 0)))
    F["eye_setback"] = (orbit * w_orb)[:, None] * -fwd[None]
    # malar rise: the cheek's front plane under the lower lid / bag (the zygoma's prominence) forward and up; the lid's
    # margin, the nasolabial side and the jaw held. Not the cheek's width
    pm = 0.5 * (lm[46] + lm[47]) + np.array([0.15 * w, -0.016, -0.004])
    rm = np.linalg.norm(((X - pm) * [1.0, 1.25, 0.6]), axis=1)
    mal = T["ext"] & (X[:, 0] > 0.004) & (X[:, 2] > pm[2] - 0.03) & (dl > 0)
    F["malar_rise"] = (mal * low_off * _g(rm, 0, 9.0 * mm))[:, None] * (0.8 * n + 0.45 * up[None])
    return {k: v * (faceslide.UNITS[k][0] * mm) for k, v in F.items()}


def joint_delta(sliders: dict | None) -> np.ndarray | None:
    """(4, 3) GNM-frame move of GNM's joints by the sliders (eye_setback takes the eye joints back with the balls),
    or None."""
    vals = values(sliders)
    if "eye_setback" not in vals or vals["eye_setback"] == (0.0, 0.0):
        return None
    J = template()["J"]
    D = np.zeros((4, 3))
    r, l_ = vals["eye_setback"]
    u = faceslide.UNITS["eye_setback"][0] * 0.001
    for j in (2, 3):
        D[j, 2] = -u * (l_ if J[j][0] > 0 else r)
    return D
