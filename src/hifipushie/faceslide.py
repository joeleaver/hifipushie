"""Face sliders: named morph targets on the one mesh's head (facesliders, 2026-10-09).

The user (2026-10-09): "If we need more control around the eye area, we'll have to update the mesh and/or sliders on
the one-mesh, we shouldn't just randomly sculpt." So: each slider is a displacement of GNM's template head (its 17821
vertices + the lids' loops, gnmloops.py), authored ONCE here from the template's own landmarks, in GNM's frame (mm on
the template), applied like an identity component (`base.gnm_head`: added to the vertices right after GNM's identity,
so the landmarks, the pushes, the hook onto the body and every later op ride on it) and solved by the same
least-change fits. `base.head.sliders = {name: value | [right, left]}`, value in [-1, 1] = the adult population's
spread (an estimate per slider: UNITS, mm at +1), 0 = the template.

Anatomy (oculoplastic references: the supratarsal crease runs parallel to the lid margin, ~7-8 mm above the lashes
centrally in adult men (~6 mm in the template's mean), lower toward both ends, about the eye's width long, starting
just past the inner canthus and vanishing under the hood laterally; the pretarsal platform is the strip between the
lashes and the fold's edge; the fold is the preseptal skin + fat over the crease; the sulcus the hollow under the
brow; the lower lid's bag is orbital fat over the lid-cheek junction; the tear trough runs from the inner canthus
down and out along the orbital rim). Every field is zero at the lid margins (the lids' fit to the eyeball stays) and
on the eyeball, smooth (C1 windows), and mirrored (the right eye's is the left's through GNM's mirror map).

Sex-neutral: 0 is GNM's mean template (neither sex), the units are pooled adult spreads (estimates, not measured),
and the head's sex comes from the identity / dimorphism as before. The anatomy notes above give men's numbers where
the literature does; women's creases sit ~1-2 mm higher (crease_height near +1..+1.5) and their brow ridges lower
(brow_ridge negative): ranges reach 1.5, the fit holds to [-1, 1].

Coordinates per eye (template): u along the corner line (0 inner canthus .. 1 outer), h = height above the upper lid
margin's curve (a parabola through the corners and the two upper-lid landmarks), dl = depth under the lower lid's
curve, t = h / (brow - margin) at that u.
"""
from __future__ import annotations

import numpy as np

# name: (mm at +1, what + means)
UNITS = {
    "eye_crease_height": (1.2, "the supratarsal crease higher (a taller platform under it)"),
    "eye_crease_depth": (0.9, "a deeper crease (a defined fold line); - = no crease (a smooth lid)"),
    "eye_platform": (1.0, "more pretarsal platform shows: the fold's edge up and back; - = the fold over it"),
    "eye_hood": (1.4, "the fold above the crease down and forward, more at the outer half (hooding)"),
    "eye_hood_lateral": (1.4, "the hood's outer end only, reaching past the outer corner (lateral hooding)"),
    "eye_sulcus": (1.4, "a fuller upper lid under the brow; - = a hollow sulcus (the A-frame)"),
    "eye_bag": (1.0, "a bag under the lower lid (orbital fat)"),
    "eye_lidcheek": (0.8, "the lid-cheek junction's crease under the bag deeper"),
    "eye_tear_trough": (0.9, "the tear trough deeper (inner canthus down and out along the rim)"),
    "brow_ridge": (1.8, "the brow ridge and the skin over the supraorbital rim forward"),
    "brow_lateral": (1.8, "the brow's outer half (and the skin under it) down: lateral brow descent"),
    "canthal_tilt": (4.0, "the eye's fissure turned outer corner up, degrees at +1 (the lids turn on the ball)"),
    "epicanthal": (1.8, "an epicanthal fold: the inner upper lid's skin over the inner canthus (medial, down)"),
}
EYE_SLIDERS = tuple(UNITS)
UNITS.update({
    "lip_upper_roll": (1.2, "the upper vermilion rolled forward (eversion: fuller, catches light on top)"),
    "lip_lower_roll": (1.4, "the lower vermilion rolled forward (eversion: fuller, a shadow beneath)"),
    "lip_bow": (0.7, "a deeper Cupid's bow: the border's peaks up, its dip down"),
    "lip_tubercle": (0.8, "the upper lip's tubercle down and forward over the seam"),
    "mouth_corner": (0.9, "the commissures tucked in and back (deeper corners); - = fuller corners"),
})
MOUTH_SLIDERS = tuple(k for k in UNITS if k not in EYE_SLIDERS)
# the older shape ops as sliders (step 4): each op at its unit amount on a sex-neutral template adult, baked into a
# morph target by spikes/facesliders/bake_age.py (face_sliders_baked.npz). name: the op's base.head.shape at +1
BAKED = {
    "age_nasolabial": {"nasolabial": {"depth": 0.002}},
    "age_prejowl": {"prejowl": 0.002},
    "age_cheek_flat": {"cheek_flat": 0.002},
    "age_lid_fold": {"lid_fold": 0.002},
    "face_planes": {"planes": 2.6},
    "face_lean": {"lean": 0.003},
    "cheek_hollow": {"hollow": 0.004},
    "chin_cleft": {"chin": {"cleft": 0.0015}},
}
UNITS.update({
    "age_nasolabial": (2.0, "the nasolabial fold: a 2 mm crease on skin.LINES' line, the cheek standing over it"),
    "age_prejowl": (2.0, "the pre-jowl sulcus (2 mm) and the jowl over the jaw's border"),
    "age_cheek_flat": (2.0, "the mid cheek flattened 2 mm and slid down (the tear trough shows)"),
    "age_lid_fold": (2.0, "upper-lid skin come down over the lid (dermatochalasis), mostly the outer half"),
    "face_planes": (0.6, "front / side planes meeting at a tighter corner (shape.planes 2.0 -> 2.6)"),
    "face_lean": (3.0, "soft tissue thinned over the jaw's border (under the jaw, jowl, submental)"),
    "cheek_hollow": (4.0, "the buccal hollow under the cheekbone"),
    "chin_cleft": (1.5, "a mid-line groove on the chin's front"),
})
AGE_SLIDERS = tuple(BAKED)
# where a woman's mean sits on each slider whose population differs by sex (ESTIMATES from the oculoplastic and
# anthropometric literature, not measured on scans: women's supratarsal crease ~1-2 mm higher, a less projecting brow
# ridge, a little more platform show). A fit's window [-1, 1] is shifted by (1 - sex) x this (body.sex: 1 = male,
# 0 = female; the template is neither), and never past the value's own limit (+-1.5).
SEX_OFFSET = {"eye_crease_height": 1.2, "brow_ridge": -0.6, "eye_platform": 0.3}


def deprecated(shape: dict | None) -> list:
    """Messages for the older shape ops a head still uses (they work; the sliders replace them)."""
    out = []
    for path, sl in DEPRECATED.items():
        keys = path.split(".")[1:]
        d = shape or {}
        for k in keys[:-1]:
            d = d.get(k) if isinstance(d, dict) else None
        if isinstance(d, dict) and d.get(keys[-1]) not in (None, 0, 0.0) and not (keys[-1] == "planes" and d.get("planes") == 2.0):
            out.append(f"base.head.{path} is deprecated: use base.head.sliders {sl} (faceslide.py)")
    return out


def fit_window(name: str, sex: float = 0.5) -> tuple:
    """(lo, hi) a fit may move `name` within, centred on the head's sex (SEX_OFFSET)."""
    off = SEX_OFFSET.get(name, 0.0) * (1.0 - float(np.clip(sex, 0.0, 1.0)))  # a woman: the whole offset
    lo = 0.0 if name in ONE_SIDED else -1.0
    return float(max(lo + off, 0.0 if name in ONE_SIDED else -1.5)), float(min(1.0 + off, 1.5))
# the ops they replace (deprecated: they still work, for the models that use them; new work uses the sliders)
DEPRECATED = {"shape.nasolabial": "age_nasolabial", "shape.prejowl": "age_prejowl", "shape.cheek_flat": "age_cheek_flat",
              "shape.lid_fold": "age_lid_fold", "shape.planes": "face_planes", "shape.lean": "face_lean",
              "shape.hollow": "cheek_hollow", "shape.chin.cleft": "chin_cleft", "shape.hood": "eye_hood / eye_hood_lateral",
              "shape.eye_bag": "eye_bag / eye_lidcheek", "shape.lip_roll": "lip_upper_roll / lip_lower_roll",
              "shape.lip_bow": "lip_bow / lip_tubercle"}
# one-sided: the template (GNM's mean) has no epicanthal fold to take away, so [0, 1]
ONE_SIDED = {"epicanthal", "age_nasolabial", "age_prejowl", "age_cheek_flat", "age_lid_fold", "face_lean", "cheek_hollow",
             "chin_cleft", "face_planes"}  # (the ageing ops and the planes (rounder than 2.0 folded the cheeks): their negative would be a ridge, not youth)
NAMES = tuple(UNITS)
_CACHE: dict = {}


def _ss(x):
    x = np.clip(x, 0.0, 1.0)
    return x * x * (3 - 2 * x)


def _g(x, mu, sig):
    return np.exp(-0.5 * ((x - mu) / sig) ** 2)


def _quad(us, ys):
    A = np.c_[np.ones(len(us)), us, np.square(us)]
    c = np.linalg.lstsq(A, ys, rcond=None)[0]
    return lambda u: c[0] + c[1] * u + c[2] * u * u


def template() -> dict:
    """GNM's template with the loops: X (n, 3), normals, exterior mask, landmarks (68, 3), mirror map (n,)."""
    if "tpl" in _CACHE:
        return _CACHE["tpl"]
    from . import base as basemod
    from . import gnmloops
    g = basemod._gnm_data()
    X = gnmloops.ext(g["template_vertex_positions"].astype(float))
    Q = gnmloops.plan()["quads"]
    n = np.zeros_like(X)
    for a, b, c in ((0, 1, 3), (1, 2, 0), (2, 3, 1), (3, 0, 2)):
        np.add.at(n, Q[:, a], np.cross(X[Q[:, b]] - X[Q[:, a]], X[Q[:, c]] - X[Q[:, a]]))
    n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-15)
    ext = gnmloops.ext(np.asarray(g["groups"]["skin_exterior"]) > 0.5, how="all")
    lm = np.array([sum(float(w) * X[int(v)] for v, w in zip(r[0::2], r[1::2])) for r in g["lm68"]])
    mi = np.r_[gnmloops._raw()["mirror"], gnmloops.plan()["mirror"]]
    skin = gnmloops.ext(np.asarray(g["skin"], bool), how="all")
    Qe = Q[ext[Q].all(1)]  # the exterior skin's open edges round the eyes: the lids' rims
    e = np.sort(np.r_[Qe[:, [0, 1]], Qe[:, [1, 2]], Qe[:, [2, 3]], Qe[:, [3, 0]]], 1)
    ue, ce = np.unique(e, axis=0, return_counts=True)
    rim = np.unique(ue[ce == 1])
    eyes = np.asarray(g["template_joint_positions"], float)[2:4]
    rim = rim[np.min([np.linalg.norm(X[rim] - j, axis=1) for j in eyes], axis=0) < 0.03]
    _CACHE["tpl"] = {"X": X, "n": n, "ext": ext, "skin": skin, "rim": rim, "lm": lm, "mirror": mi, "J": g["template_joint_positions"].astype(float)}
    return _CACHE["tpl"]


def _left_fields() -> dict:
    """Every slider's field for the subject's LEFT eye (+x), GNM frame, metres at +1."""
    from scipy.spatial import cKDTree
    T = template()
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
    # crease depth: a groove at the crease along the margin's arch, the skin over it standing a little forward (a
    # fold edge, not a trench)
    prof = -_g(h, H0, 0.75 * mm) + 0.35 * _g(h, H0 + 1.7 * mm, 0.9 * mm)
    F["eye_crease_depth"] = (m * Ec * prof)[:, None] * n
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
    return {k: v * (UNITS[k][0] * mm) for k, v in F.items()}


def _mouth_fields() -> dict:
    """The mouth's sliders (whole mouth, GNM frame, metres at +1). Per x the lips are read between curves through
    the 68 landmarks: the upper border (48-54 over 49-53), the upper seam (60-64 over 61-63), the lower seam (64-60
    under 65-67) and the lower border (54-48 under 55-59); s = 0 at the seam .. 1 at the border."""
    T = template()
    X, n, lm = T["X"], T["n"], T["lm"]
    mm = 0.001
    up = np.array([0.0, 1.0, 0.0])
    fwd = np.array([0.0, 0.0, 1.0])

    def curve(ids):
        P = lm[list(ids)]
        o = np.argsort(P[:, 0])
        return lambda x: np.interp(x, P[o, 0], P[o, 1])  # noqa: E731
    yU = curve((48, 49, 50, 51, 52, 53, 54))
    ySu = curve((60, 61, 62, 63, 64))
    ySl = curve((60, 67, 66, 65, 64))
    yL = curve((48, 59, 58, 57, 56, 55, 54))
    x, y = X[:, 0], X[:, 1]
    hw = 0.5 * float(lm[54][0] - lm[48][0])
    zc = float(lm[[51, 57, 62, 66]][:, 2].mean())
    front = T["ext"] & (X[:, 2] > zc - 0.012) & (np.abs(x) < hw + 0.008)
    front &= (y < float(lm[33][1]) - 0.002) & (y > float(lm[8][1]) + 0.01)  # under the nose, over the chin
    su = (y - ySu(x)) / np.maximum(yU(x) - ySu(x), 1.5 * mm)
    sl = (ySl(x) - y) / np.maximum(ySl(x) - yL(x), 1.5 * mm)
    ax = np.abs(x) / hw
    taper = _ss((1.0 - ax) / 0.45)  # full over the middle, tucked at the corners
    upper = front & (y > ySu(x) - 0.3 * mm)
    lower = front & (y < ySl(x) + 0.3 * mm)
    # how far past each border the skin follows (fading over ~3 mm)
    past_u = np.where(su > 1, _ss(1 - (su - 1) * (yU(x) - ySu(x)) / (3 * mm)), 1.0)
    past_l = np.where(sl > 1, _ss(1 - (sl - 1) * (ySl(x) - yL(x)) / (3 * mm)), 1.0)
    seam_hold_u = _ss(su / 0.25)  # the contact ring stays where it is (no lip through the other)
    seam_hold_l = _ss(sl / 0.25)
    F = {}
    # eversion: the vermilion rolled forward (volume, not height); upper: peaks in its upper part (catches light on
    # top, a shadow under it); lower: its middle, a shadow beneath
    pu = upper * taper * past_u * _g(np.minimum(su, 1.6), 0.65, 0.35)
    F["lip_upper_roll"] = pu[:, None] * (0.9 * fwd + 0.25 * up * seam_hold_u[:, None])
    pl = lower * taper * past_l * _g(np.minimum(sl, 1.6), 0.5, 0.35)
    F["lip_lower_roll"] = pl[:, None] * (0.9 * fwd - 0.25 * up * seam_hold_l[:, None])
    # Cupid's bow: the border's peaks up and its dip down (the border band only, fading 3 mm into lip and skin)
    xp = 0.5 * abs(float(lm[52][0] - lm[50][0]))
    band = upper * _g(su, 1.0, 0.35) * seam_hold_u
    bow = _g(np.abs(x), xp, 0.45 * xp) - 0.8 * _g(x, 0.0, 0.45 * xp)
    F["lip_bow"] = (band * bow)[:, None] * up[None]
    # tubercle: the upper lip's middle down and forward over the seam
    tub = upper * _g(x, 0.0, 0.55 * xp) * _g(su, 0.25, 0.3)
    F["lip_tubercle"] = tub[:, None] * (0.85 * fwd - 0.4 * up * seam_hold_u[:, None])
    # corner tuck: the commissures in and back (a deeper corner; - = fuller corners)
    F["mouth_corner"] = np.zeros_like(X)
    for c in (lm[48], lm[54]):
        r = np.linalg.norm(X - c, axis=1)
        side = np.sign(c[0])
        F["mouth_corner"] += (T["skin"] * _g(r, 0, 3.5 * mm))[:, None] * (-0.85 * fwd + 0.35 * np.array([-side, 0, 0]))[None]  # (one direction: the corner's normals turn fast)
    return {k: v * (UNITS[k][0] * mm) for k, v in F.items()}


def fields() -> dict:
    """{name: ((n, 3) right side's, (n, 3) left side's)} metres at +1, GNM frame (n = GNM's + the loops' vertices).
    The eyes' are each eye's own (mirrored); the mouth's split at the centre line (smoothly)."""
    if "fields" not in _CACHE:
        T = template()
        mi = T["mirror"]
        out = {}
        for k, dL in _left_fields().items():
            dR = dL[mi] * [-1.0, 1.0, 1.0]
            out[k] = (dR, dL)
        wl = _ss((T["X"][:, 0] + 0.002) / 0.004)[:, None]
        for k, d in _mouth_fields().items():
            out[k] = (d * (1 - wl), d * wl)
        from pathlib import Path

        from . import gnmloops
        baked = Path(__file__).with_name("face_sliders_baked.npz")
        if baked.exists():  # (step 4: the older shape ops, baked by spikes/facesliders/bake_age.py)
            z = np.load(baked)
            # held off the lids' rims and the lips' contact (they were baked on a body's head, a few mm unlike the
            # template here: around those thin rolls the op's move turned the lips' border over, planes +1)
            from scipy.spatial import cKDTree
            X = T["X"]
            d_rim = cKDTree(X[T["rim"]]).query(X)[0]
            d_lip = cKDTree(T["lm"][48:68]).query(X)[0]
            hold = (T["ext"] * _ss((d_rim - 0.003) / 0.008) * _ss((d_lip - 0.003) / 0.005))[:, None]  # (exterior only)
            for k in BAKED:
                if k in z.files:
                    d = gnmloops.ext(z[k].astype(float))
                    d = hold * 0.5 * (d + d[mi] * [-1.0, 1.0, 1.0])  # (baked on a body's head: made exactly mirror symmetric)
                    out[k] = (d * (1 - wl), d * wl)
        _CACHE["fields"] = out
    return _CACHE["fields"]


def values(sliders: dict | None) -> dict:
    """{name: (right, left)} clipped to [-1.5, 1.5] (a fit's solve is held to [-1, 1]); unknown names refused."""
    out = {}
    for k, v in (sliders or {}).items():
        if k not in UNITS:
            raise ValueError(f"unknown face slider {k!r}; known: {', '.join(UNITS)}")
        r, l_ = (v, v) if np.isscalar(v) else (v[0], v[1])
        lo = 0.0 if k in ONE_SIDED else -1.5
        out[k] = (float(np.clip(r, lo, 1.5)), float(np.clip(l_, lo, 1.5)))
    return out


def delta(sliders: dict | None) -> np.ndarray | None:
    """The sliders' sum, (n, 3) GNM frame, or None when none is set."""
    vals = {k: v for k, v in values(sliders).items() if v != (0.0, 0.0)}
    if not vals:
        return None
    F = fields()
    D = np.zeros_like(template()["X"])
    for k, (r, l_) in vals.items():
        D += r * F[k][0] + l_ * F[k][1]
    return D


# ---- reading the eye from a render, and the least-change fit --------------------------------------------------------
def eye_camera(st: dict, yaw: float = 0.0) -> dict:
    """A fixed front camera at the subject's left eye (humanfit.project's dict), 0.5 m away, f 4000 px."""
    L = np.asarray(st["L"], float)
    return {"r": [0.0, 0.0, 0.0], "t": [0.0, 0.0, 0.5], "f": 4000.0, "size": [2000, 2000],
            "centre": (0.5 * (L[42] + L[45])).tolist(), "yaw": float(yaw)}


def _rows_of(st: dict, gids) -> np.ndarray:
    from . import onemesh
    gid = np.asarray(onemesh.asset()["gnm_exact"], int)[np.asarray(st["tpl"]["fid"])]
    row = {int(g): i for i, g in enumerate(gid) if g >= 0}
    return np.array([row[int(g)] for g in gids if int(g) in row], int)


def read_eyes(st: dict, cam: dict | None = None, px: int = 700) -> dict:
    """The subject's left eye read from a clay render through `cam` (default eye_camera): {"crease": mm from the
    upper lid margin up to the darkest line on the lid (2.5-12 mm over the pupil: the crease / the fold's edge;
    luminance, sub-pixel minimum), "crease_dark": lid luminance under it over the line's, "canthal_tilt": deg (the
    rim's inner -> outer corner as projected, + = outer up), "open": mm (the rim's upper -> lower edge over the
    pupil)}. Luminance reads the render (the loops and every slider show there); corners and opening read the
    rim's projected vertices."""
    from scipy.ndimage import map_coordinates

    from . import humanfit, likeness
    cam = cam or eye_camera(st)
    P = np.asarray(st["tpl"]["P"], float)
    L = np.asarray(st["L"], float)
    eye = 0.5 * (L[42] + L[45])
    rim = _rows_of(st, template()["rim"])
    rim = rim[np.linalg.norm(P[rim] - eye, axis=1) < 0.025]
    uv = humanfit.project(cam, P[rim])
    d = uv[int(np.argmax(uv[:, 0]))] - uv[int(np.argmin(uv[:, 0]))]
    mm_px = 0.001 * cam["f"] / float(cam["t"][2])  # px per mm at the eye's depth
    mid = 0.5 * (L[43] + L[44])
    c = humanfit.project(cam, mid[None])[0]
    near = np.abs(uv[:, 0] - c[0]) < 1.5 * mm_px
    top, bot = float(uv[near, 1].min()), float(uv[near, 1].max())
    out = {"canthal_tilt": float(np.degrees(np.arctan2(-d[1], abs(d[0])))), "open": (bot - top) / mm_px}
    box = (c[0] - 16 * mm_px, c[1] - 16 * mm_px, c[0] + 16 * mm_px, c[1] + 8 * mm_px)
    im, k = likeness.render(likeness.model_mesh_from_state(st), cam, box, px=px, brows=False)
    a = np.asarray(im.convert("RGB"), float) / 255.0
    Y = 0.2126 * a[..., 0] + 0.7152 * a[..., 1] + 0.0722 * a[..., 2]
    hs = np.arange(0.0, 14.0, 0.1)
    ys = (top - hs * mm_px - box[1]) * k
    prof = np.mean([map_coordinates(Y, [ys, (c[0] + dx * mm_px - box[0]) * k + 0 * hs], order=1)
                    for dx in (-0.6, 0.0, 0.6)], axis=0)
    win = np.flatnonzero((hs >= 2.5) & (hs <= 12.0))
    j = int(win[np.argmin(prof[win])])
    off = 0.0
    if 0 < j < len(hs) - 1:
        den = prof[j - 1] - 2 * prof[j] + prof[j + 1]
        off = float(np.clip(0.5 * (prof[j - 1] - prof[j + 1]) / den, -1, 1)) if abs(den) > 1e-12 else 0.0
    out["crease"] = float(hs[j] + 0.1 * off)
    under = prof[(hs >= 1.0) & (hs <= max(hs[j] - 1.0, 1.0))]
    out["crease_dark"] = float(np.median(under) / max(prof[j], 1e-6))
    return out


def read_mouth(st: dict, cam: dict | None = None, px: int = 500) -> dict:
    """The lips read from a clay render's depth pass through a front camera at the mouth: {"upper_proj", "lower_proj":
    mm the upper / lower vermilion's middle stands in front of the subnasale (lm 33), sampled over 1.5 mm}."""
    from . import humanfit, likeness
    L = np.asarray(st["L"], float)
    c3 = 0.5 * (L[51] + L[57])
    cam = cam or {"r": [0.0, 0.0, 0.0], "t": [0.0, 0.0, 0.5], "f": 6000.0, "size": [2000, 2000],
                  "centre": c3.tolist(), "yaw": 0.0}
    mm_px = 0.001 * cam["f"] / float(cam["t"][2])
    c = humanfit.project(cam, c3[None])[0]
    box = (c[0] - 30 * mm_px, c[1] - 30 * mm_px, c[0] + 30 * mm_px, c[1] + 20 * mm_px)
    _, k, ps = likeness.render(likeness.model_mesh_from_state(st), cam, box, px=px, brows=False, passes=True)
    zb = ps["zb"]

    def z_at(p):
        q = (humanfit.project(cam, np.asarray(p)[None])[0] - box[:2]) * k
        r = max(1, int(round(0.75 * mm_px * k)))
        y, x = int(round(q[1])), int(round(q[0]))
        w = zb[max(y - r, 0):y + r + 1, max(x - r, 0):x + r + 1]
        return float(np.median(w[np.isfinite(w)])) if np.isfinite(w).any() else float("nan")
    z0 = z_at(L[33])
    return {"upper_proj": 1000 * (z0 - z_at(0.4 * L[62] + 0.6 * L[51])),
            "lower_proj": 1000 * (z0 - z_at(0.5 * L[66] + 0.5 * L[57]))}


def fit(base: dict, targets: dict, names, read=None, hold: float = 0.15, iters: int = 4, step: float = 0.15,
        log=None, on_base: bool = False) -> dict:
    """The least change of the named sliders (both eyes together) that brings the read measures to their targets:
    targets {measure: (value, tolerance)}; read(state) -> {measure: value} (default read_eyes). Gauss-Newton on
    sum(((m - target) / tol)^2) + hold * sum((x - x0)^2), the Jacobian by central differences THROUGH the built head
    (humanfit.state: GNM's vertices, the loops' and every op after the sliders), x held to fit_window (centred on body.sex).
    Returns {"sliders", "before", "after", "steps"}."""
    import copy

    from . import humanfit
    read = read or read_eyes
    names = list(names)
    b0 = copy.deepcopy(base)
    sl0 = dict((b0.get("head") or {}).get("sliders") or {})
    x0 = np.array([float(np.mean(sl0.get(n, 0.0))) for n in names])
    sex = (b0.get("body") or {}).get("sex", 0.5)
    sex = {"female": 0.0, "male": 1.0}.get(sex, 0.5) if isinstance(sex, str) else float(sex)
    lo_, hi_ = np.array([fit_window(n, sex) for n in names]).T  # (centred on the head's sex: SEX_OFFSET)
    keys = list(targets)
    t = np.array([targets[k][0] for k in keys], float)
    tol = np.array([targets[k][1] for k in keys], float)

    def with_x(x):
        b = copy.deepcopy(b0)
        s = dict(sl0)
        s.update({n: round(float(v), 4) for n, v in zip(names, x)})
        b.setdefault("head", {})["sliders"] = s
        return b

    def r_of(x):
        m = read(with_x(x)) if on_base else read(humanfit.state(with_x(x)))  # (on_base: read(base), e.g. a matched pair)
        return np.array([m[k] for k in keys], float), m

    def cost(m_, x_):
        return float(np.sum(((m_ - t) / tol) ** 2) + hold * np.sum((x_ - x0) ** 2))

    x = x0.copy()
    m, before = r_of(x)
    steps = []
    for _ in range(iters):
        Jc = np.zeros((len(keys), len(names)))
        for j in range(len(names)):
            e = np.zeros(len(names))
            e[j] = step
            Jc[:, j] = (r_of(x + e)[0] - r_of(x - e)[0]) / (2 * step)
        A = Jc / tol[:, None]
        dx = -np.linalg.solve(A.T @ A + hold * np.eye(len(names)), A.T @ ((m - t) / tol) + hold * (x - x0))
        xn = np.clip(x + dx, lo_, hi_)
        mn, _ = r_of(xn)
        if cost(mn, xn) > cost(m, x):
            xn = np.clip(x + 0.5 * dx, lo_, hi_)
            mn, _ = r_of(xn)
            if cost(mn, xn) > cost(m, x):  # no better (a noisy reading, e.g. a detector): keep what we had
                steps.append({"x": [round(float(v), 4) for v in x], "miss": [round(float(v), 3) for v in (m - t) / tol],
                              "stopped": "no step improved"})
                break
        steps.append({"x": [round(float(v), 4) for v in xn], "miss": [round(float(v), 3) for v in (mn - t) / tol]})
        if log:
            log(steps[-1])
        x, m = xn, mn
        if np.all(np.abs(dx) < 0.01):
            break
    return {"sliders": {n: round(float(v), 4) for n, v in zip(names, x)}, "before": before,
            "after": dict(zip(keys, m.tolist())), "steps": steps}
