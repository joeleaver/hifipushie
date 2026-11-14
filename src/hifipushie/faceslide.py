"""Face sliders: named morph targets on the one mesh's head (facesliders, 2026-10-09).

The user (2026-10-09): "If we need more control around the eye area, we'll have to update the mesh and/or sliders on
the one-mesh, we shouldn't just randomly sculpt." So: each slider is a displacement of GNM's template head (its 17821
vertices + the lids' loops, gnmloops.py), authored ONCE here from the template's own landmarks, in GNM's frame (mm on
the template), applied like an identity component (`base_gnm_head.gnm_head`: added to the vertices right after GNM's identity,
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

Where the code is (split by responsibility, as C424): this module is the family's base and holds EVERY constant (set
and read at faceslide.NAME: C422). faceslide_eyes: the eye's sliders as fields: lid margins, the fold's turn, the left
eye's fields, the joint's delta. faceslide_mouth: the mouth's sliders as fields: mouth fields, the lip rings, the seal
and its steps. faceslide_fields: every slider as one field set: the nose's fields, `fields`, `values`, the head's
fields, `delta`. faceslide_fit: reading the eye, the nose and the mouth from a render, and the least-change fit of the
sliders.
"""
from __future__ import annotations

import numpy as np
from . import moved

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
def _ext_units():
    from .faceext import table as _t
    tab = _t()
    return {k: (float(np.linalg.norm(np.asarray(tab[k], float), axis=1).max() * 1000) if k in tab else 1.0, v[3])
            for k, v in _EXT.items()}


UNITS.update(_ext_units())   # (mm at +1: the field's own largest move)
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
    from . import base_identity
    from . import gnmloops
    g = base_identity._gnm_data()
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
    from . import base_identity
    from . import gnmloops
    T = dict(template())
    X = gnmloops.ext(np.asarray(V, float))
    Q = gnmloops.plan()["quads"]
    n = np.zeros_like(X)
    for a, b, c in ((0, 1, 3), (1, 2, 0), (2, 3, 1), (3, 0, 2)):
        np.add.at(n, Q[:, a], np.cross(X[Q[:, b]] - X[Q[:, a]], X[Q[:, c]] - X[Q[:, a]]))
    n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-15)
    g = base_identity._gnm_data()
    T.update(X=X, n=n, lm=np.array([sum(float(w) * X[int(v)] for v, w in zip(r[0::2], r[1::2])) for r in g["lm68"]]),
             own=True)
    return T


SEAL_PASSES = 3
PAST = 3.0  # mm: how far past the vermilion border the skin follows the rolls and the bow
CORNER_FREE = 0.0  # share of the mouth's width at each corner where the rolls are left to the membrane


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


HEAD_FIELDS = ("eye_crease_depth",)  # sliders laid on the head's own shape (base_gnm_head.gnm_head passes V)


# The modules this one was split into (as C424). Its constants stay HERE (C422): tests/test_constants_address.py.
MODULES = ("faceslide_eyes", "faceslide_mouth", "faceslide_fields", "faceslide_fit")
__getattr__ = moved.refuse(__name__, MODULES)  # a name that moved says where it is now (C426)
