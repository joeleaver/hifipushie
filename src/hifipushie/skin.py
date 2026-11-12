"""Human skin as a description: spec["skin"] expands into ordinary paint layers (as a material does) laid under the
model's own paint, plus the skin part's shading (subsurface, specular). Nothing here is a second paint system: every
layer it makes is built from paint generators (spot, noise, cells, outline, facing, tile, image), named
"skin:<layer>", shown by look(paint_layer="skin:freckles") and baked by the export like any other.
`guide(topic="skin")` is the artist's workflow (base tone -> zones -> large features -> fine features -> micro ->
cosmetics -> shading check); `skin_reference` lists the zones and every parameter's default.

spec["skin"] = {
  "part": "body",                 the part that is skin
  "tone": {"melanin": 0..1 | "fitzpatrick": 1..6, "blood": 0..1 (0.4), "undertone": -1 cool/pink .. +1 warm/golden,
           "oxygenation": 0..1 (0.75)},   a pigment model, not a colour: every layer below is this tone with more or
                                   less melanin and blood, so freckles, flush, lips, palms and scars stay right for
                                   any skin (`tone_rgb`)
  "sex": 0 female .. 1 male (unset: neither): the skin's sex-linked defaults, each still settable itself: a woman's
                                  finer thinner brows, darker lash lines, finer pores, fuller-coloured lips; a man's
                                  heavier brows and coarser skin. (Beard shadow is `hair.stubble`: off unless asked.)
  "age": years (30),              drives wrinkles, uneven pigment, age spots, thinner drier skin; each can be set itself
  "variation": 1,                 strength of colour zones and mottling (0 = one flat tone)
  "detail": 1,                    strength of micro relief and wrinkles
  "oil": 0..1 (0.5),              sebum: lowers roughness on the T-zone (forehead, nose, chin)
  "thin": 0..1 (0.5),             thin skin shows blood, veins and under-eye colour more, and scatters more
  "sun": 0..1 (0.3),              sun exposure: uneven pigment, freckles' kin, age spots with age
  "zones": {layer: strength},     per-layer strength of the built-in colour zones (see ZONE_LAYERS), 0 turns one off
  "zone_colors": {layer: [r, g, b]}  a zone layer's own colour replaced (linear 0..1; for the multiply levers lid_shade /
                                  under_eye_shade: the default is a hair cool, which turned some heads' sockets grey-lilac)
  "lips": {"blood": 1, "melanin": 1, "roughness": 0.36, "dry": 0, "gradient": 1 (darker toward the wet line and the
           corners, a lighter lower-lip body; 0 = one flat colour), "border": 1.5 (mm: the vermilion border's
           softness), "strength": 1 (0.2..2: x how much of the vermilion is the lips' own colour; a man's is 0.65 by default), "lower": {"blood": 1, "melanin": 1} (the lower
           lip's own colour, x the lips')}
  "features": {"freckles", "moles", "age_spots", "blemishes", "veins", "flush", "sunburn", "tan"}  (see FEATURES)
  "wrinkles": {"amount": null (from age) | 0..1, "<region>": 0..1}                                 (see WRINKLES)
  "fold_relief": "geometry" (default: skin.folds reshape the surface, skin_folds.prims) | "paint" (bump only)
  "fold_expressions": true (export: each fold's gain per face shape is baked into that shape's morph target,
                                  skin_folds.EXPRESSION: a lid's crease unfolds on a blink) | false (the folds ride the shapes rigidly)
  "folds": {name: amount | {"amount", "width", "depth", "roll", "L" / "R": {"amount", "shift", "extent"}}}   (see FOLDS: the
                                  soft-tissue lines and bulges the shape model does not make: nasolabial, marionette,
                                  tear_trough (+ the eye bag), lid_fold, mentolabial, glabella, mouth_corner; colour and
                                  painted relief, placed from landmarks + the placement skin_from_reference measures)
  "hair": {"stubble", "brows", "body"}                                                             (see HAIR)
  "scars": [{"kind": "cut" | "surgical" | "burn" | "keloid" | "pockmarks", ...}]                   (see SCARS)
  "tattoos": [{"image": {...paint image...}, "age": years, "opacity"}]
  "eyes": {"iris": "#5a3a1e", "iris_size": m (0.0118), "pupil": 0..1 (0.36 of the iris), "veins": 0..1 (0.4),
           "sclera": colour} | false   the eyeballs (the base's eyes part): see EYES
  "makeup": {"look": "natural" | "everyday" | "evening", "foundation", "concealer", "bronzer", "contour", "blush", "highlight",
             "eyeshadow", "eyeliner", "mascara", "brows", "lipstick", "nails"}                       (see MAKEUP)
  "shading": {"subsurface": 0..1, "radius": [r, g, b], "scale": m, "specular": 0..1, "roughness": 0..1,
                                  "rough_breakup": 0..1 (1: x the cm-scale roughness blotches; < 1 for a face meshed at 1 mm)}
  "projection": {...}             the reference pictures as the head's albedo + fine relief, in the head's own texture
                                  space (made by the skin_project tool: de-lit, filled; see skin_project.py). Laid over
                                  the skin's own colours and painted hair, under scars, tattoos and make-up.
  "stack": {...}                  the skin's colour as a STACK OF LAYER MAPS in the head's atlas, decomposed from the de-lit
                                  reference (skin_layers.py; made by skin_from_reference / skin_layers.apply): a base +
                                  pigment, redness, periorbital, brows, lips, beard, shade maps, each a multiply layer
                                  "skin:stack_<name>" with its own opacity (an edit changes one map); over the skin's
                                  broad colour layers, under every fine generator.
  "only": [groups]                lay only these groups of the description and nothing else, for a character whose skin
                                  is already painted by hand: "eyes" (the eyeball pictures, on the eyes part),
                                  "eye_rims" (caruncle and waterline, on the skin), "zones" (colour zones, mottling,
                                  nails), "lips", "roughness", "micro" (pores and lines), "features" (freckles ..
                                  wrinkles, hair, scars, tattoos, make-up), "shading" (the skin part's base colour,
                                  roughness, subsurface, coat: without it the part's own shading is untouched).
                                  ["eyes"] = just the painted irises on a hand-painted character.
}
Anatomical zones (`zone` paint generator, for any layer of the model's own too): ZONES below, placed from the GNM
head's lm_* landmarks and the body's joints, sized in interocular distances on the face and joint radii on the body.

Where the code is (split by responsibility, as C424): this module is the family's base and holds EVERY constant (set
and read at skin.NAME: C422). skin_zones: anatomical zones: the body's and the face's zones by name, on the model's
own joints. skin_params: the description's parameters: groups, the age curve, `params`, shading, a part's base colour,
roughness. skin_build: the description -> layers: `layers`, the build, the aperture keep-out, the export recipe,
`reference`.
"""
from __future__ import annotations

import numpy as np

from .spec import SpecError
from . import moved

CORNER_FADE = 0.003  # m: the vermilion's colour fades over the last ~3 mm before each commissure
UNDER_SHADE = 1.0  # skin.lips.under_shade: the lower lip's own shade on the skin under it (mouth_eye_bias: photos 5-17 L darker there, ours ~4)
RIM_LOWER = 1.0  # skin.lips.rim_lower: the pale rim's share under the LOWER lip (mouth_eye_bias)
VERSION = 12  # 12: the visible eye (lash frame past the outer canthus, darker lower line, inner canthus tip, occlusion .5) and lip volume (soft sheen, wet seam, pocketed corners, under_shade 1); 11: cells capped at detail 1, pores tint at most 0.3 (above detail 1 they printed as stubble dots); 10: stacked faces: pores everywhere the photos show them, cells' colour faint; 9: pores at full strength under a measured stack (projskin); 8: the face microrelief (cells network base, sparser pores; projskin); 4: lash_roots, eye film / occlusion (eyedetail); 5: the face's base map (skin4); 6: lower lip (gnmdetail2); 7: the vermilion's gradient and soft border (skinfolds)
LOWER_LIP = {"melanin": 0.72, "blood": 3.8, "epidermis": 0.0, "oxygenation": 0.66}  # x the lips' melanin / blood (see _build)
# the face's base map layers (skin_marks.base_map): opacities of blood up, blood or melanin down, melanin up; relief depth (m).
# x sqrt(variation) / sqrt(detail): tuned on Tess (variation .6, detail .45); linear, Garrett's 1.3 / 1.8 read as sandpaper
BASE_MAP = {"red": 0.4, "light": 0.36, "pigment": 0.3, "depth": 0.00011}

# ---- tone: melanin + haemoglobin -> albedo ----------------------------------------------------------------------
# A two-layer model in the spirit of Donner & Jensen 2006 / Jimenez et al. 2010, with Jacques' skin optics numbers
# (omlc.org/news/jan98/skinoptics.html): light crosses a melanin-bearing epidermis twice and is scattered back by a
# blood-bearing dermis (Kubelka-Munk). Spectra at 10 nm, colour matching by Wyman et al.'s analytic CIE fits.
_LAM = np.arange(400, 701, 10.0)
_HBO2 = np.array([266232, 466840, 480360, 246072, 102580, 62816, 44480, 33209, 26629, 23684, 20932, 20035, 24202, 39957,
                  53236, 43016, 32613, 44496, 50104, 14400, 3200, 1506, 942, 610, 442, 368, 320, 294, 277, 276, 290.0])
_HB = np.array([223296, 303956, 407560, 528600, 413280, 103292, 23389, 16156, 14550, 16684, 20862, 25774, 31590, 39036,
                46592, 53412, 53788, 45072, 37020, 28324, 14677, 9444, 6510, 5149, 4345, 3750, 3227, 2795, 2407, 2052,
                1794.0])  # molar extinction of oxy / deoxy haemoglobin (Prahl), cm-1 / M


def _g(lam, mu, s1, s2):
    return np.exp(-0.5 * ((lam - mu) / np.where(lam < mu, s1, s2)) ** 2)


_CMF = np.stack([1.056 * _g(_LAM, 599.8, 37.9, 31.0) + 0.362 * _g(_LAM, 442.0, 16.0, 26.7) - 0.065 * _g(_LAM, 501.1, 20.4, 26.2),
                 0.821 * _g(_LAM, 568.8, 46.9, 40.5) + 0.286 * _g(_LAM, 530.9, 16.3, 31.1),
                 1.217 * _g(_LAM, 437.0, 11.8, 36.0) + 0.681 * _g(_LAM, 459.0, 26.0, 13.8)])
_XYZ2RGB = np.array([[3.2404542, -1.5371385, -0.4985314], [-0.9692660, 1.8760108, 0.0415560],
                     [0.0556434, -0.2040259, 1.0572252]])
MELANIN = (0.013, 0.55)  # melanosome volume fraction of the epidermis at melanin 0 and 1 (Jacques: 1.3% .. 43%+)
BLOOD = (0.01, 0.12)  # blood volume fraction of the dermis at blood 0 and 1
FITZPATRICK = {1: 0.02, 2: 0.14, 3: 0.3, 4: 0.48, 5: 0.7, 6: 0.9}  # melanin (0..1) per Fitzpatrick type
# The very fair end (2026-10-10): with MELANIN[0] and a fixed carotene baseline, melanin 0 stopped at ITA 52 deg
# (L* 71, b* 16: Chardon / Del Bino's "light"), so "very light" skin (ITA > 55: L* ~70, b* ~12) was out of reach and
# rendered tan. Below FAIR_TO (F2), the melanosome fraction falls geometrically to MELANIN_FAIR and the carotene
# baseline to FAIR_CAROTENE of itself; F2 and darker are unchanged. Melanin 0: ITA ~59, F1: ~58, F2: 47.
MELANIN_FAIR, FAIR_TO, FAIR_CAROTENE = 0.005, 0.14, 0.4


def melanosomes(m: float) -> float:
    """The epidermis's melanosome volume fraction for the melanin slider m (0..1)."""
    hi = MELANIN[0] * (MELANIN[1] / MELANIN[0]) ** m
    if m >= FAIR_TO:
        return hi
    top = MELANIN[0] * (MELANIN[1] / MELANIN[0]) ** FAIR_TO
    return MELANIN_FAIR * (top / MELANIN_FAIR) ** (m / FAIR_TO)
PATH, BACK = 2.4, 0.045  # epidermal path (x 60 um), and the share of absorbed light the epidermis scatters back


def reflectance(mel: float, blood: float, oxy: float = 0.75, carotene: float = 0.3, epi: float = 1.0) -> np.ndarray:
    """Diffuse reflectance at _LAM for volume fractions mel (epidermis) and blood (dermis)."""
    base = 0.244 + 85.3 * np.exp(-(_LAM - 154) / 66.2)
    mu_mel = 6.6e11 * _LAM ** -3.33 + 130.0
    mu_car = 60.0 * np.exp(-0.5 * ((_LAM - 465) / 32) ** 2)  # carotenoids: a blue absorber (golden undertone)
    mu_epi = mel * mu_mel + (1 - mel) * base + carotene * mu_car
    mu_d = blood * 0.005356 * (oxy * _HBO2 + (1 - oxy) * _HB) + (1 - blood) * base
    mus = 2e5 * _LAM ** -1.5 + 2e12 * _LAM ** -4
    ks = 2 * mu_d / (0.75 * mus)
    rd = 1 + ks - np.sqrt(ks * ks + 2 * ks)
    t = np.exp(-mu_epi * 0.006 * PATH * epi)
    return t * rd + BACK * (1 - t) * t ** 0.2


def _srgb(refl: np.ndarray) -> np.ndarray:
    xyz = _CMF @ refl / (_CMF @ np.ones_like(refl)) * np.array([0.95047, 1.0, 1.08883])
    lin = np.clip(_XYZ2RGB @ xyz, 0, 1)
    return np.where(lin <= 0.0031308, lin * 12.92, 1.055 * lin ** (1 / 2.4) - 0.055)


def tone_params(tone: dict | None) -> dict:
    """The tone's own numbers: melanin and blood as 0..1 sliders, undertone, oxygenation."""
    t = dict(tone or {})
    bad = set(t) - {"melanin", "fitzpatrick", "blood", "undertone", "oxygenation"}
    if bad:
        raise SpecError(f"skin tone: unknown keys {sorted(bad)} (have melanin | fitzpatrick, blood, undertone, oxygenation)")
    if "fitzpatrick" in t and "melanin" not in t:
        f = float(t["fitzpatrick"])
        if not 1 <= f <= 6:
            raise SpecError("skin tone: fitzpatrick is 1 (very fair) .. 6 (deeply pigmented)")
        lo = int(np.floor(f))
        t["melanin"] = FITZPATRICK[lo] + (f - lo) * (FITZPATRICK[min(lo + 1, 6)] - FITZPATRICK[lo])
    out = {"melanin": float(t.get("melanin", 0.14)), "blood": float(t.get("blood", 0.4)),
           "undertone": float(t.get("undertone", 0.0)), "oxygenation": float(t.get("oxygenation", 0.75))}
    for k, (lo, hi) in {"melanin": (0, 1), "blood": (0, 1), "undertone": (-1, 1), "oxygenation": (0, 1)}.items():
        if not lo <= out[k] <= hi:
            raise SpecError(f"skin tone: {k} is {lo}..{hi}")
    return out


def tone_rgb(tone: dict | None, melanin: float = 1.0, blood: float = 1.0, oxygenation: float | None = None,
             epidermis: float = 1.0, yellow: float = 0.0, grey: float = 0.0) -> list:
    """The albedo (sRGB 0..1) of skin of this tone with `melanin` x its melanin, `blood` x its blood, thinner or
    thicker epidermis, more carotene (`yellow`), `grey`: mixed toward its own grey (dead, dry or covered skin)."""
    p = tone_params(tone)
    lo = melanosomes(p["melanin"])
    # pigment ADDED by a mark (freckles, moles, age spots: melanin > 1) counts on the unlowered curve, so freckles on
    # very fair skin stay as dark as before against a paler ground (they vanished when the multiplier ran on the floor)
    mel = lo * melanin if melanin <= 1 else lo + (melanin - 1) * MELANIN[0] * (MELANIN[1] / MELANIN[0]) ** p["melanin"]
    bl = (BLOOD[0] * (BLOOD[1] / BLOOD[0]) ** p["blood"]) * blood * (1 + 0.35 * max(-p["undertone"], 0))
    fair = FAIR_CAROTENE + (1 - FAIR_CAROTENE) * min(p["melanin"] / FAIR_TO, 1.0)
    car = 0.1 * fair + 0.45 * max(p["undertone"], 0) * (1 - 0.6 * p["melanin"]) - 0.1 * max(-p["undertone"], 0) + yellow
    rgb = _srgb(reflectance(min(mel, 0.95), min(bl, 0.5), p["oxygenation"] if oxygenation is None else oxygenation,
                            max(car, 0.0), epidermis))
    if grey:
        rgb = rgb + grey * (rgb.mean() - rgb)
    return [round(float(x), 4) for x in np.clip(rgb, 0, 1)]


# ---- anatomical zones --------------------------------------------------------------------------------------------
# name -> [(anchor joint, offset, radius)] in interocular distances (face) on the world axes: x toward the model's
# left, y toward its back, z up. A ".L" anchor makes a sided zone ("cheek.L" / "cheek.R"; "cheek" = both).
FACE = {
    "forehead": [("lm_nose_bridge", (0, 0.25, 0.85), (1.05, 0.9, 0.6)), ("lm_brow_outer.L", (0.0, 0.15, 0.55), (0.5, 0.6, 0.5)),
                 ("lm_brow_outer.R", (0.0, 0.15, 0.55), (0.5, 0.6, 0.5))],
    # where forehead LINES lie (r17, Garrett's photo: 3-4 long lines in the band ~.2-.65 of the way from the brows to the
    # hairline, the upper forehead smooth): a band over the brows, anchored on them, not the "forehead" colour zone
    # (centred .85 io over the nasion: lines masked by it sat up on the dome, under the hair)
    "forehead_lines": [("lm_brow_mid.L", (-0.15, 0.12, 0.31), (0.55, 0.7, 0.3)), ("lm_brow_mid.R", (0.15, 0.12, 0.31), (0.55, 0.7, 0.3))],
    "temple.L": [("lm_brow_outer.L", (0.22, 0.45, 0.15), (0.3, 0.45, 0.4))],
    "glabella": [("lm_nose_bridge", (0, -0.03, 0.2), (0.24, 0.3, 0.22))],
    "nose_bridge": [("lm_nose_bridge", (0, -0.12, -0.25), (0.2, 0.35, 0.35))],
    "nose_tip": [("lm_nose_tip", (0, 0.03, 0), (0.25, 0.25, 0.22))],
    "nose_wing.L": [("lm_nostril.L", (0.03, 0.02, 0.06), (0.17, 0.2, 0.17))],
    "cheek.L": [("lm_lid_lower.L", (0.12, 0.12, -0.6), (0.42, 0.45, 0.4))],
    "cheekbone.L": [("lm_eye_outer.L", (0.12, 0.25, -0.35), (0.4, 0.5, 0.22))],
    "cheek_side.L": [("lm_jaw_2.L", (-0.25, -0.5, 0.25), (0.4, 0.6, 0.5))],
    "under_eye.L": [("lm_lid_lower.L", (0, 0.02, -0.13), (0.33, 0.3, 0.13))],
    "eyelid.L": [("lm_lid_upper.L", (0, 0.03, 0.09), (0.34, 0.3, 0.11))],
    "eye_corner.L": [("lm_eye_inner.L", (0, 0, 0), (0.14, 0.2, 0.16))],
    "crows_feet.L": [("lm_eye_outer.L", (0.2, 0.2, 0.0), (0.24, 0.3, 0.26))],
    "upper_lip": [("lm_lip_upper", (0, 0.02, 0.12), (0.52, 0.4, 0.15))],
    "philtrum": [("lm_nose_base", (0, 0, -0.12), (0.12, 0.2, 0.14))],
    "mouth_corner.L": [("lm_mouth_corner.L", (0.05, 0.03, -0.03), (0.14, 0.2, 0.16))],
    "soul_patch": [("lm_lip_lower", (0, 0.03, -0.2), (0.3, 0.3, 0.14))],
    "chin": [("lm_chin", (0, 0.05, 0.22), (0.42, 0.4, 0.3))],
    "under_chin": [("lm_chin", (0, 0.45, -0.1), (0.7, 0.6, 0.3))],
    "jaw.L": [(f"lm_jaw_{k}.L", (-0.08, -0.1, 0.15), (0.3, 0.3, 0.3)) for k in range(1, 8)],
    # where a beard grows beside the mouth and under the jaw (the jaw's own spots are a string of beads along its edge)
    "jowl.L": [("lm_mouth_corner.L", (0.5, 0.38, -0.12), (0.52, 0.75, 0.47)), ("lm_mouth_corner.L", (0.25, 0.12, -0.45), (0.45, 0.5, 0.4))],
    "beard_neck": [("lm_chin", (0, 0.75, -0.42), (0.85, 0.75, 0.42))],
    "ear.L": [("lm_jaw_0.L", (0.12, 0.3, 0.2), (0.28, 0.42, 0.48))],
    "ear_lobe.L": [("lm_jaw_0.L", (0.1, 0.22, -0.12), (0.18, 0.22, 0.16))],
    "neck": [("neck", (0, -0.3, -0.45), (0.85, 0.95, 0.8))],
    "scalp": [("head", (0, 0.7, 1.0), (1.6, 2.0, 1.4))],  # the head joint is at brow height, the cranium ~1.5 io round it
    "face": [("lm_nose_base", (0, 0.55, 0.15), (1.15, 1.0, 1.55))],
}
# zones made of others (their union)
UNIONS = {
    "nose": ["nose_bridge", "nose_tip", "nose_wing"], "eye_socket.L": ["under_eye.L", "eyelid.L", "eye_corner.L"],
    "t_zone": ["forehead", "glabella", "nose_bridge", "nose_tip", "chin"],
    "beard.L": ["jaw.L", "cheek_side.L", "jowl.L", "upper_lip", "soul_patch", "chin", "under_chin", "beard_neck"],
    "moustache": ["upper_lip"], "mid_face": ["cheek", "nose", "ear"],
}
LINES = {  # tapered lines: [(anchor, offset)], radius (interocular distances)
    "nasolabial.L": ([("lm_nostril.L", (0.1, 0.02, 0.05)), ("lm_mouth_corner.L", (0.2, 0.05, 0.1)),
                      ("lm_mouth_corner.L", (0.23, 0.08, -0.22))], [0.05, 0.075, 0.04]),
    "marionette.L": ([("lm_mouth_corner.L", (0.06, 0.02, -0.03)), ("lm_mouth_corner.L", (0.12, 0.05, -0.42))], [0.06, 0.035]),
    "brow.L": ([("lm_brow_inner.L", (0.0, 0, 0)), ("lm_brow_mid.L", (0, 0, 0)), ("lm_brow_outer.L", (0, 0, -0.01))],
               [0.085, 0.09, 0.045]),
}
_VN = 17  # base_measures.VERM_N
_V = lambda k, rev=False: [f"verm_{k}{i:02d}" for i in (range(_VN - 1, -1, -1) if rev else range(_VN))]  # noqa: E731
OUTLINES_DENSE = {  # on a GNM head (base_measures._vermilion_joints): right corner -> left along the outer edge, back along
    # the inner one; "lips" border to border
    "lip_upper": _V("u") + _V("iu", True),
    "lip_lower": _V("il") + _V("l", True),
    "lips": _V("u") + _V("l", True)[1:-1],
}
OUTLINES = {  # closed landmark outlines seen from the front
    "lips": ["lm_mouth_corner.R", "lm_lip_upper_side.R", "lm_lip_peak.R", "lm_lip_upper", "lm_lip_peak.L",
             "lm_lip_upper_side.L", "lm_mouth_corner.L", "lm_lip_lower_side.L", "lm_lip_lower_mid.L", "lm_lip_lower",
             "lm_lip_lower_mid.R", "lm_lip_lower_side.R"],
    "lip_upper": ["lm_mouth_corner.R", "lm_lip_upper_side.R", "lm_lip_peak.R", "lm_lip_upper", "lm_lip_peak.L",
                  "lm_lip_upper_side.L", "lm_mouth_corner.L", "lm_lip_inner_upper.L", "lm_lip_inner_upper",
                  "lm_lip_inner_upper.R"],
    "lip_lower": ["lm_mouth_corner.R", "lm_lip_inner_lower.R", "lm_lip_inner_lower", "lm_lip_inner_lower.L",
                  "lm_mouth_corner.L", "lm_lip_lower_side.L", "lm_lip_lower_mid.L", "lm_lip_lower", "lm_lip_lower_mid.R",
                  "lm_lip_lower_side.R"],
}
EXTRA = ("lash_upper.L", "lash_lower.L")
BODY = ("shoulder.L", "elbow.L", "knee.L", "knuckles.L", "hand.L", "palm.L", "back_of_hand.L", "fingertips.L",
        "nails.L", "forearm.L", "upper_arm.L", "wrist_inner.L", "foot.L", "sole.L", "chest", "collarbone")

# ---- the description -> layers ----------------------------------------------------------------------------------
KEYS = {"part", "tone", "age", "variation", "detail", "oil", "thin", "sun", "zones", "lips", "features", "wrinkles",
        "hair", "scars", "tattoos", "makeup", "shading", "nails", "seed", "eyes", "sex", "only", "folds", "fold_relief", "fold_expressions",
        "projection", "stack", "zone_colors"}
GROUPS = ("shading", "zones", "lips", "roughness", "micro", "features", "eyes", "eye_rims")

ZONE_LAYERS = {"forehead_yellow": 1.0, "midface_red": 1.0, "nose_red": 1.0, "perioral_red": 1.0, "ears_red": 1.0, "lower_cool": 1.0,
               "under_eye": 1.0, "eyelids": 1.0, "periorbital": 0.0, "lid_shade": 0.0, "under_eye_shade": 0.0, "neck": 1.0, "palms": 1.0, "soles": 1.0, "knuckles": 1.0,
               "elbows_knees": 1.0, "fingertips": 1.0, "nails": 1.0}

AFTER_STACK = ("skin:lid_shade", "skin:under_eye_shade")   # zone levers kept over a measured stack, laid after it
OVER_STACK = ("skin:brow_shadow",)   # feature layers laid after the stack anyway: under one they are shader layers, not pre

_LAYERS: dict = {}


APERTURE_KEEP = (0.001, 0.0007)  # m: (within, soft) of the eyeballs where the skin's eye-region layers fade out
APERTURE_OWN = ("skin:waterline", "skin:caruncle", "skin:caruncle_wet", "skin:canthus", "skin:lashes", "skin:lid_crease_line")  # the margin's own colours (+ the fold line: the lid's platform lies within 1-2 mm of the ball, the keep-out erased it)


# The modules this one was split into (as C424). Its constants stay HERE (C422): tests/test_constants_address.py.
MODULES = ("skin_zones", "skin_params", "skin_build")
__getattr__ = moved.refuse(__name__, MODULES)  # a name that moved says where it is now (C426)
