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
    "eye_setback": (2.0, "the eyeball and the orbit's contents back (deep-set), the brow ridge held; - = prominent eyes"),
    "malar_rise": (2.0, "the cheek's front plane under the lower lid forward and up (the zygoma's prominence), not its width"),
}
EYE_SLIDERS = tuple(UNITS)
UNITS.update({
    "lip_upper_roll": (1.2, "the upper vermilion rolled forward (eversion: fuller, catches light on top)"),
    "lip_lower_roll": (1.4, "the lower vermilion rolled forward (eversion: fuller, a shadow beneath)"),
    "lip_bow": (0.7, "a deeper Cupid's bow: the border's peaks up, its dip down"),
    "lip_tubercle": (0.8, "the upper lip's tubercle down and forward over the seam"),
    "mouth_corner": (0.9, "the commissures tucked in and back (deeper corners); - = fuller corners"),
    # vermilion heights: Farkas' adult norms (North American Caucasian) put the upper vermilion (ls-sto) at ~8.6 mm
    # (men) / 7.4 (women), SD ~1.5-1.8, and the lower (sto-li) at ~10 / 9, SD ~1.6-1.8 (from memory of the published
    # tables: verify before relying on the decimals). +-1 = about +-1.5 SD; at 1.0 / 1.2 mm a full lip was out of
    # reach (Tess: 5.1 -> 5.5 of her 6.4 at +1)
    "lip_upper_height": (2.5, "more upper vermilion shows: its border up, the seam held (red lip height, not projection)"),
    "lip_lower_height": (3.0, "more lower vermilion shows: its border down, the seam held"),
})
MOUTH_SLIDERS = tuple(k for k in UNITS if k not in EYE_SLIDERS)
# the nose (Joe: "we don't have good control over the width of the middle of the nose"; nose_width is the alar base,
# lm 31-35). Per side, mm at +1 (estimates from adult spreads: the nasal root ~17-20 mm wide, SD ~2; verify): the
# side walls out / in, the dorsal line, the alar base and the tip's position held
UNITS.update({
    "nose_radix_width": (1.5, "the root between the eyes wider (each side wall out), the inner canthi held"),
    "nose_dorsum_width": (2.0, "the middle vault wider: the bony / cartilage dorsum's side walls out"),
    "nose_tip_width": (1.5, "the tip's domes (the lobule) wider, separate from the alae"),
    "nose_dorsum_hump": (2.0, "a dorsal hump (the bony-cartilage junction forward); - = a scooped dorsum"),
})
NOSE_SLIDERS = ("nose_radix_width", "nose_dorsum_width", "nose_tip_width", "nose_dorsum_hump")
# coupled only (base.head.slider_mode "coupled": faceatlas; whole-model directions with no local morph): +1 = +1 sd
UNITS.update({"eye_opening": (1.0, "the lids' aperture (coupled only)"), "gonion_height": (1.0, "the jaw angle's height (coupled only)"),
              "ramus_angle": (1.0, "the ramus' slope from vertical (coupled only)")})
COUPLED_ONLY = ("eye_opening", "gonion_height", "ramus_angle")
# model extensions from MakeHuman's CC0 targets (faceext.py: carried onto GNM, the identity's part projected out):
# residual sliders, +1 = half MakeHuman's incr - decr difference (the field is stored in metres)
from .faceext import EXT as _EXT  # noqa: E402
UNITS.update({k: (1.0, v[3]) for k, v in _EXT.items()})
EXT_SLIDERS = tuple(_EXT)
# Tess's measured misses (2026-10-09): her nostrils show from the front under a small defined lobule; her lower
# vermilion is a short cushion ending well inside the corners (its visible width 0.40 of the mouth's, ours 0.82)
UNITS.update({
    "nostril_show": (1.2, "the alar rims up and the columella down: the nostrils show from the front"),
    "tip_definition": (0.8, "the lobule set off from the alae by a soft groove (a small, defined tip)"),
    "lip_lower_width": (2.0, "the lower vermilion's lateral reach: + = out to the corners, - = a short cushion "
                             "ending inside them (its border drawn up to the seam laterally)"),
})
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
# lid margins (eyedetail, 2026-10-09): GNM's lids taper to a ~1 mm rounded tip on the ball; a real margin is a flat face
# ~2 mm deep (the posterior edge on the ball: the waterline; the anterior edge: the lash line, where lashes.py roots).
# One-sided: thinner than the template would pull the lid's front into the ball.
UNITS.update({
    "lid_margin_upper": (0.9, "the upper lid's margin thicker: its lash edge forward of the waterline (a squared rim)"),
    "lid_margin_lower": (0.8, "the lower lid's margin thicker: a visible rim and waterline over the ball"),
})
MARGIN_SLIDERS = ("lid_margin_upper", "lid_margin_lower")
ONE_SIDED |= set(MARGIN_SLIDERS)
NAMES = tuple(UNITS)
_CACHE: dict = {}


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
    return {k: v * (UNITS[k][0] * mm) for k, v in F.items()}


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
    eyes_m = gnmloops.ext(np.asarray(g["groups"]["eyes"]) > 0.5, how="all")
    _CACHE["tpl"] = {"X": X, "n": n, "ext": ext, "skin": skin, "eyes": eyes_m, "rim": rim, "lm": lm, "mirror": mi,
                     "J": g["template_joint_positions"].astype(float)}
    return _CACHE["tpl"]


def head_template(V: np.ndarray) -> dict:
    """template()'s dict for a head of GNM's raw vertices V (its frame): positions with the loops, normals, landmarks;
    masks, rims and the mirror map are the template's."""
    from . import base as basemod
    from . import gnmloops
    T = dict(template())
    X = gnmloops.ext(np.asarray(V, float))
    Q = gnmloops.plan()["quads"]
    n = np.zeros_like(X)
    for a, b, c in ((0, 1, 3), (1, 2, 0), (2, 3, 1), (3, 0, 2)):
        np.add.at(n, Q[:, a], np.cross(X[Q[:, b]] - X[Q[:, a]], X[Q[:, c]] - X[Q[:, a]]))
    n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-15)
    g = basemod._gnm_data()
    T.update(X=X, n=n, lm=np.array([sum(float(w) * X[int(v)] for v, w in zip(r[0::2], r[1::2])) for r in g["lm68"]]),
             own=True)
    return T


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
    _CACHE["last_crease"] = (Hc, H0, u, upper)  # (diagnostics: creasechk.py)
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
    return {k: v * (UNITS[k][0] * mm) for k, v in F.items()}


def joint_delta(sliders: dict | None) -> np.ndarray | None:
    """(4, 3) GNM-frame move of GNM's joints by the sliders (eye_setback takes the eye joints back with the balls),
    or None."""
    vals = values(sliders)
    if "eye_setback" not in vals or vals["eye_setback"] == (0.0, 0.0):
        return None
    J = template()["J"]
    D = np.zeros((4, 3))
    r, l_ = vals["eye_setback"]
    u = UNITS["eye_setback"][0] * 0.001
    for j in (2, 3):
        D[j, 2] = -u * (l_ if J[j][0] > 0 else r)
    return D


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
    past_u = np.where(su > 1, _ss(1 - (su - 1) * (yU(x) - ySu(x)) / (PAST * mm)), 1.0)
    past_l = np.where(sl > 1, _ss(1 - (sl - 1) * (ySl(x) - yL(x)) / (PAST * mm)), 1.0)
    # (the heights move the border up to 2.5-3 mm: the skin past it follows over 8 mm, not 3: at 3 it folded)
    hu = np.where(su > 1, _ss(1 - (su - 1) * (yU(x) - ySu(x)) / (8 * mm)), 1.0)
    hl = np.where(sl > 1, _ss(1 - (sl - 1) * (ySl(x) - yL(x)) / (8 * mm)), 1.0)
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
    # vermilion height: the border slides away from the seam (the seam held, the skin past the border following over
    # ~3 mm): how much red lip shows, apart from how far it stands forward (the rolls)
    F["lip_upper_height"] = (upper * taper * hu * _ss((su - 0.15) / 0.85))[:, None] * up[None]  # (the seam
    # rows held: at -1 the lip went down through the lower one)
    F["lip_lower_height"] = (lower * taper * hl * _ss((sl - 0.15) / 0.85))[:, None] * -up[None]
    # lower lip width: its border laterally (the outer half, toward the corners) away from / toward the seam: + more red
    # out to the corners, - the lower lip a short cushion ending inside them (the seam and the middle held)
    lat_l = _ss((ax - 0.3) / 0.45) * (1 - _ss((ax - 1.05) / 0.15))
    F["lip_lower_width"] = (lower * hl * lat_l * _ss((sl - 0.15) / 0.85))[:, None] * -up[None]
    F["mouth_corner"] = np.zeros_like(X)
    for c in (lm[48], lm[54]):
        r = np.linalg.norm(X - c, axis=1)
        side = np.sign(c[0])
        F["mouth_corner"] += (T["skin"] * _g(r, 0, 3.5 * mm))[:, None] * (-0.85 * fwd + 0.35 * np.array([-side, 0, 0]))[None]  # (one direction: the corner's normals turn fast)
    return {k: v * (UNITS[k][0] * mm) for k, v in F.items()}


def _lip_rings() -> dict:
    """GNM's lips by topology (its raw ids): rings out from the skin's open mouth loop (the inner rolls' end) over the
    skin's quads; ring base.LIP_RING is the contact ring (landmarks 61-63 / 65-67 sit on it)."""
    if "lip_rings" in _CACHE:
        return _CACHE["lip_rings"]
    from collections import defaultdict

    from . import base as basemod
    g = basemod._gnm_data()
    skin = np.asarray(g["skin"], bool)
    Q = np.asarray(g["quads"])
    Q = Q[skin[Q].all(1)]
    e = np.sort(np.r_[Q[:, [0, 1]], Q[:, [1, 2]], Q[:, [2, 3]], Q[:, [3, 0]]], 1)
    ue, ce = np.unique(e, axis=0, return_counts=True)
    adj = defaultdict(set)
    for a, b in e:
        adj[a].add(b)
        adj[b].add(a)
    bd = np.unique(ue[ce == 1])
    X = np.asarray(g["template_vertex_positions"], float)
    lm = np.array([sum(float(w) * X[int(v)] for v, w in zip(r[0::2], r[1::2])) for r in g["lm68"]])
    mouth = 0.5 * (lm[62] + lm[66])
    loop = set(int(v) for v in bd[np.linalg.norm(X[bd] - mouth, axis=1) < 0.04])
    rings, seen, ring = [sorted(loop)], set(loop), loop
    for _ in range(basemod.LIP_RING + 16):  # (out past where the fade has died: ~1 mm a ring)
        nxt = set()
        for v in ring:
            nxt |= adj[v]
        nxt -= seen
        seen |= nxt
        ring = nxt
        rings.append(sorted(ring))
    _CACHE["lip_rings"] = {"rings": [np.array(r, int) for r in rings], "contact": basemod.LIP_RING,
                           "adj": {int(v): [int(u) for u in adj[v]] for r in rings for v in r},
                           "upper": np.asarray(g["groups"]["upper_lip"]) > np.asarray(g["groups"]["lower_lip"])}
    return _CACHE["lip_rings"]


def seal_delta(V: np.ndarray, amount: float = 1.0) -> np.ndarray:
    """(n, 3) GNM-frame move that closes the lips of head V (GNM's raw vertices, its frame) to `amount` of contact
    along the full width: the contact ring's upper and lower halves meet halfway (per x, the gap's y and z),
    everything from the open loop out to the contact ring moves whole (the rolls behind the contact go with it: no
    lip through the other), the lips beyond it fade out over ~5 mm (they shift, not squash). A rest mouth, not a
    pressed one: nothing goes past contact."""
    R = _lip_rings()
    D = np.zeros_like(V)
    for _ in range(SEAL_PASSES):  # (re-measured each pass: the contact ring's halves aren't single-valued in x)
        D = D + _seal_step(V + D, 1.0, R)
    return float(amount) * D


SEAL_PASSES = 3
PAST = 3.0  # mm: how far past the vermilion border the skin follows the rolls and the bow
CORNER_FREE = 0.0  # share of the mouth's width at each corner where the rolls are left to the membrane


def _seal_step(V, amount, R):
    rings, kc = R["rings"], R["contact"]
    C = rings[kc]
    x = V[C, 0]
    lo_x, hi_x = x.min(), x.max()
    # upper / lower half: GNM's own upper_lip / lower_lip groups (each ring splits 29 / 29). By height (above the
    # corners' line) a downturned, wide-open mouth put lower-lip vertices in the upper half: their edges to the
    # rolls stretched x6 (Tess)
    up_g = R["upper"]
    side = up_g[C]
    U, Lw = C[side], C[~side]
    if len(U) < 3 or len(Lw) < 3:
        return np.zeros_like(V)
    ou, ol = np.argsort(V[U, 0]), np.argsort(V[Lw, 0])
    U, Lw = U[ou], Lw[ol]
    gap_at = lambda xx: np.c_[[np.interp(xx, V[Lw, 0], V[Lw, k]) - np.interp(xx, V[U, 0], V[U, k]) for k in (1, 2)]].T  # noqa: E731
    import scipy.sparse as sp
    from scipy.sparse.linalg import spsolve
    D = np.zeros_like(V)
    # the contact ring's own move: each half halfway to the other (per x; touching or crossed: nothing)
    xx = np.clip(V[C, 0], lo_x, hi_x)
    gp = gap_at(xx)
    sgn = np.where(side, 0.5, -0.5)
    tgt = np.c_[np.zeros(len(C)), amount * sgn * np.minimum(gp[:, 0], 0.0), amount * sgn * gp[:, 1]]
    # everything else as a MEMBRANE over the lips' rings (a harmonic fill: the contact ring held at its move, the
    # outermost ring at 0, the rolls inside free): the travel spreads over every row in between. (Moving whole bands
    # with a fade by height stretched edges x4 and turned quads on wide-open, thin-lipped heads: Tess)
    ids = np.unique(np.concatenate(rings))
    loc = {int(v): i for i, v in enumerate(ids)}
    rows, cols = [], []
    for v in ids:
        for u in R["adj"].get(int(v), []):
            if u in loc:
                rows.append(loc[int(v)])
                cols.append(loc[u])
    n = len(ids)
    A = sp.coo_matrix((np.ones(len(rows)), (rows, cols)), (n, n)).tocsr()
    deg = np.asarray(A.sum(1)).ravel()
    Lp = sp.diags(deg) - A
    fixed = np.zeros(n, bool)
    val = np.zeros((n, 3))
    ci = np.array([loc[int(v)] for v in C])
    fixed[ci] = True
    val[ci] = tgt
    # the rolls inside the contact move whole with their own lip (by topology from the contact ring: by height the
    # rolls' quads straddle the middle; left free, the corners' rolls averaged both lips and turned over)
    up_of = {int(v): bool(s) for v, s in zip(C, side)}
    for k in range(kc - 1, -1, -1):
        for v in rings[k]:
            nb = [up_of[u] for u in R["adj"].get(int(v), []) if u in up_of]
            up_of[int(v)] = bool(R["upper"][v])  # (GNM's groups: see above)
    inner = np.array([int(v) for k in range(kc) for v in rings[k]], int)
    # ... except near the corners, where the two lips' rolls join: there the membrane spreads it (held whole, an
    # upper roll vertex going down beside a lower one going up stretched their edge x4: Tess's wide-open mouth)
    span = max(hi_x - lo_x, 1e-6)
    inner = inner[np.minimum(V[inner, 0] - lo_x, hi_x - V[inner, 0]) > CORNER_FREE * span]
    if len(inner):
        g_in = gap_at(np.clip(V[inner, 0], lo_x, hi_x))
        s_in = np.where([up_of[int(v)] for v in inner], 0.5, -0.5)
        ii = np.array([loc[int(v)] for v in inner])
        fixed[ii] = True
        val[ii] = np.c_[np.zeros(len(inner)), amount * s_in * np.minimum(g_in[:, 0], 0.0), amount * s_in * g_in[:, 1]]
    oi = np.array([loc[int(v)] for v in rings[-1]])
    fixed[oi] = True
    free = ~fixed
    if free.any():
        Lff = Lp[free][:, free].tocsc()
        rhs = -(Lp[free][:, fixed] @ val[fixed])
        val[free] = np.column_stack([spsolve(Lff, rhs[:, k]) for k in range(3)])
    D[ids] = val
    return D


def _nose_fields() -> dict:
    """The nose's sliders (whole nose, GNM frame, metres at +1). s along the dorsal line (lm 27 nasion = 0 .. lm 30 the
    tip = 1), x across from the midline: the widths move the side walls sideways in proportion to x (the dorsal line,
    x = 0, and the tip's position stay), held round the alar base (lm 31 / 35, the nostrils) and off the eyes' rims."""
    from scipy.spatial import cKDTree
    T = template()
    X, n, lm = T["X"], T["n"], T["lm"]
    mm = 0.001
    a, b = lm[27], lm[30]
    d = b - a
    L2 = float(d @ d)
    s = (X - a) @ d / L2
    x = X[:, 0] - 0.5 * (lm[31][0] + lm[35][0])
    ax = np.abs(x)
    hw_alar = 0.5 * abs(float(lm[35][0] - lm[31][0]))
    # the nose's own half-width along it: ~0.45 of the alar base at the root, 0.5 mid, 0.7 at the tip
    hw = hw_alar * np.interp(s, [0.0, 0.5, 0.85, 1.1], [0.45, 0.5, 0.65, 0.7])
    front = T["ext"] & (X[:, 2] > lm[27][2] - 0.02) & (s > -0.25) & (s < 1.2) & (ax < hw + 0.012)
    front &= X[:, 1] > lm[33][1] - 0.002  # (above the nostrils' floor)
    lat = _ss(ax / np.maximum(hw, 1e-4)) * (1 - _ss((ax - hw) / (6 * mm)))
    side = np.sign(x)[:, None] * np.array([1.0, 0.0, 0.0])
    alar = np.min([np.linalg.norm(X - lm[i], axis=1) for i in (31, 35, 32, 34)], axis=0)
    hold_alar = _ss((alar - 3.0 * mm) / (5.0 * mm))
    hold_eye = _ss((cKDTree(X[T["rim"]]).query(X)[0] - 4.0 * mm) / (5.0 * mm))
    F = {}
    F["nose_radix_width"] = (front * lat * _g(s, 0.1, 0.13) * hold_eye * hold_alar)[:, None] * side
    F["nose_dorsum_width"] = (front * lat * _g(s, 0.5, 0.15) * hold_alar * hold_eye)[:, None] * side
    # (held off the nostrils' insides: moving the rim's outside alone folded it against them)
    inner = T["skin"] & ~T["ext"] & (np.abs(x) < hw_alar + 0.005) & (X[:, 1] < lm[30][1]) & (X[:, 1] > lm[33][1] - 0.006)
    hold_nos = _ss((cKDTree(X[inner]).query(X)[0] - 1.5 * mm) / (3.5 * mm)) if inner.any() else 1.0
    tip = front * _g(s, 0.92, 0.1) * _ss(ax / (0.4 * hw_alar)) * (1 - _ss((ax - 0.75 * hw_alar) / (4 * mm)))
    F["nose_tip_width"] = (tip * hold_alar * hold_nos)[:, None] * side
    hump = front * _g(s, 0.45, 0.13) * _g(ax, 0, 0.6 * hw_alar)
    F["nose_dorsum_hump"] = hump[:, None] * np.array([0.0, 0.0, 1.0])[None]
    # nostril show: the alar rims (round lm 31 / 35, below the wings' middle) up, the columella (lm 33 up to the tip's
    # underside, the midline) down; the tip held
    up = np.array([0.0, 1.0, 0.0])
    rim = (front | (T["skin"] & (ax < hw_alar + 0.005))) & (X[:, 1] < lm[30][1])
    wing = np.min([np.linalg.norm(X - (lm[i] + np.array([0.0, -0.001, 0.0])), axis=1) for i in (31, 35)], axis=0)
    col = np.linalg.norm((X - 0.5 * (lm[33] + lm[30]))[:, [0, 1]] * [1.0, 0.6], axis=1)
    tipd = np.linalg.norm(X - lm[30], axis=1)
    hold_tip = _ss((tipd - 2.5 * mm) / (4 * mm))
    F["nostril_show"] = (rim * hold_tip)[:, None] * (_g(wing, 0, 3.0 * mm)[:, None] * up[None]
                                                    - 0.6 * (_g(col, 0, 2.0 * mm) * (ax < 3 * mm))[:, None] * up[None])
    # tip definition: a soft groove where the lobule meets each ala (from over the wing toward the domes), the
    # lobule's domes a little forward
    gp0 = lm[35] + np.array([-0.001, 0.0045, 0.002])
    gp1 = lm[30] + np.array([0.006, -0.002, -0.003])
    q = np.c_[np.abs(X[:, 0]), X[:, 1], X[:, 2]]
    seg = gp1 - gp0
    tt = np.clip((q - gp0) @ seg / float(seg @ seg), 0, 1)
    dseg = np.linalg.norm(q - (gp0 + tt[:, None] * seg), axis=1)
    groove = front * _g(dseg, 0, 1.3 * mm) * _ss(tt / 0.2) * _ss((1 - tt) / 0.25)
    domes = front * _g(np.linalg.norm(q - np.c_[np.full(len(X), 0.004), np.full(len(X), lm[30][1]), np.full(len(X), lm[30][2])], axis=1), 0, 2.5 * mm)
    F["tip_definition"] = -groove[:, None] * n + 0.35 * domes[:, None] * n
    mi = T["mirror"]  # (made exactly mirror symmetric: GNM's template is symmetric only to ~0.1 mm)
    return {k: 0.5 * (v + v[mi] * [-1.0, 1.0, 1.0]) * (UNITS[k][0] * mm) for k, v in F.items()}


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
        for k, dL in _margin_fields().items():  # (eyedetail) the lid margins' thickness
            out[k] = (dL[mi] * [-1.0, 1.0, 1.0], dL)
        wl = _ss((T["X"][:, 0] + 0.002) / 0.004)[:, None]
        for k, d in {**_mouth_fields(), **_nose_fields()}.items():
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
        from . import faceext
        tab = faceext.table()
        for k in EXT_SLIDERS:   # (the extensions: built by faceext.build into face_ext.npz)
            if k in tab:
                d = np.asarray(tab[k], float)
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


HEAD_FIELDS = ("eye_crease_depth",)  # sliders laid on the head's own shape (base.gnm_head passes V)


def head_fields(V: np.ndarray, names=HEAD_FIELDS) -> dict:
    """The HEAD_FIELDS on head V (GNM's raw vertices, its frame): ((n, 3) right, (n, 3) left), as fields()."""
    from . import gnmloops
    V = np.asarray(V, float)
    key = ("head_fields", hash(V.tobytes()), tuple(names))
    if key in _CACHE:
        return _CACHE[key]
    mi_raw = gnmloops._raw()["mirror"]
    mi = template()["mirror"]
    dL = _left_fields(head_template(V))
    dLm = _left_fields(head_template(V[mi_raw] * [-1.0, 1.0, 1.0]))  # the right eye as a left one
    out = {k: (dLm[k][mi] * [-1.0, 1.0, 1.0], dL[k]) for k in names}
    if len([k for k in _CACHE if isinstance(k, tuple) and k[0] == "head_fields"]) > 8:
        _CACHE.pop(next(k for k in _CACHE if isinstance(k, tuple) and k[0] == "head_fields"))
    _CACHE[key] = out
    return out


def delta(sliders: dict | None, V: np.ndarray | None = None) -> np.ndarray | None:
    """The sliders' sum, (n, 3) GNM frame, or None when none is set. V (the head's GNM vertices): HEAD_FIELDS are
    laid on its own shape (the crease on its own fold turn), not the template's."""
    vals = {k: v for k, v in values(sliders).items() if v != (0.0, 0.0)}
    if not vals:
        return None
    F = dict(fields())
    if V is not None and any(k in vals for k in HEAD_FIELDS):
        F.update(head_fields(V, tuple(k for k in HEAD_FIELDS if k in vals)))
    D = np.zeros_like(template()["X"])
    for k, (r, l_) in vals.items():
        if k not in F:  # (a coupled-only slider: faceatlas.COUPLED, nothing local to lay)
            continue
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


def nose_widths(img, P, mmpx: float) -> dict:
    """The nose's dorsal width read by SHADING, like with like on any picture lit by one light (the photo, or a render
    under the photo's fitted light): across the face (the detector's own axes) at the radix (MediaPipe 168) and the
    mid-dorsum (between 6 and 4), the luminance profile +-14 mm, smoothed over 1 mm; the dorsum is the bright band
    round the middle: its width at half the drop from its peak to the side walls' darkest (mm). The detector has
    no point on the dorsal lines: this is what an eye reads as the nose's width partway down."""
    from scipy.ndimage import gaussian_filter1d, map_coordinates

    from .likeness_eyes import frame
    P = np.asarray(P, float)
    a = np.asarray(img.convert("RGB"), float) / 255.0
    Y = 0.2126 * a[..., 0] + 0.7152 * a[..., 1] + 0.0722 * a[..., 2]
    ex, _ = frame(P)
    out = {}
    for name, c in (("radix_w", P[168]), ("dorsum_w", 0.5 * (P[6] + P[4]))):
        t = np.arange(-14.0, 14.01, 0.1)
        pts = c[None] + (t / mmpx)[:, None] * ex[None]
        prof = gaussian_filter1d(map_coordinates(Y, [pts[:, 1], pts[:, 0]], order=1), 1.0 / 0.1 / 2.355)
        mid = np.abs(t) <= 3.0
        j = int(np.flatnonzero(mid)[np.argmax(prof[mid])])
        peak = prof[j]
        edges = []
        for sgn in (-1, 1):
            k = np.arange(j, len(t)) if sgn > 0 else np.arange(j, -1, -1)
            low = float(prof[k].min())
            half = peak - 0.5 * (peak - low)
            hit = k[np.argmax(prof[k] <= half)] if (prof[k] <= half).any() else k[-1]
            edges.append(t[hit])
        out[name] = float(edges[1] - edges[0])
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
