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
  "age": years (30),              drives wrinkles, uneven pigment, age spots, thinner drier skin; each can be set itself
  "variation": 1,                 strength of colour zones and mottling (0 = one flat tone)
  "detail": 1,                    strength of micro relief and wrinkles
  "oil": 0..1 (0.5),              sebum: lowers roughness on the T-zone (forehead, nose, chin)
  "thin": 0..1 (0.5),             thin skin shows blood, veins and under-eye colour more, and scatters more
  "sun": 0..1 (0.3),              sun exposure: uneven pigment, freckles' kin, age spots with age
  "zones": {layer: strength},     per-layer strength of the built-in colour zones (see ZONE_LAYERS), 0 turns one off
  "lips": {"blood": 1, "melanin": 1, "roughness": 0.36, "dry": 0}
  "features": {"freckles", "moles", "age_spots", "blemishes", "veins", "flush", "sunburn", "tan"}  (see FEATURES)
  "wrinkles": {"amount": null (from age) | 0..1, "<region>": 0..1}                                 (see WRINKLES)
  "hair": {"stubble", "brows", "body"}                                                             (see HAIR)
  "scars": [{"kind": "cut" | "surgical" | "burn" | "keloid" | "pockmarks", ...}]                   (see SCARS)
  "tattoos": [{"image": {...paint image...}, "age": years, "opacity"}]
  "makeup": {"foundation", "concealer", "blush", "contour", "highlight", "eyeshadow", "eyeliner", "mascara",
             "brows", "lipstick", "nails"}                                                         (see MAKEUP)
  "shading": {"subsurface": 0..1, "radius": [r, g, b], "scale": m, "specular": 0..1, "roughness": 0..1}
}
Anatomical zones (`zone` paint generator, for any layer of the model's own too): ZONES below, placed from the GNM
head's lm_* landmarks and the body's joints, sized in interocular distances on the face and joint radii on the body.
"""
from __future__ import annotations

import copy
import hashlib
import json

import numpy as np

from .spec import SpecError

VERSION = 1

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
    mel = MELANIN[0] * (MELANIN[1] / MELANIN[0]) ** p["melanin"] * melanin
    bl = (BLOOD[0] * (BLOOD[1] / BLOOD[0]) ** p["blood"]) * blood * (1 + 0.35 * max(-p["undertone"], 0))
    car = 0.1 + 0.45 * max(p["undertone"], 0) * (1 - 0.6 * p["melanin"]) - 0.1 * max(-p["undertone"], 0) + yellow
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
    "ear.L": [("lm_jaw_0.L", (0.12, 0.3, 0.2), (0.28, 0.42, 0.48))],
    "ear_lobe.L": [("lm_jaw_0.L", (0.1, 0.22, -0.12), (0.18, 0.22, 0.16))],
    "neck": [("neck", (0, -0.3, -0.45), (0.85, 0.95, 0.8))],
    "scalp": [("head", (0, 0.3, 0.75), (1.0, 1.25, 0.75))],
    "face": [("lm_nose_base", (0, 0.55, 0.15), (1.15, 1.0, 1.55))],
}
# zones made of others (their union)
UNIONS = {
    "nose": ["nose_bridge", "nose_tip", "nose_wing"], "eye_socket.L": ["under_eye.L", "eyelid.L", "eye_corner.L"],
    "t_zone": ["forehead", "glabella", "nose_bridge", "nose_tip", "chin"],
    "beard.L": ["jaw.L", "cheek_side.L", "upper_lip", "soul_patch", "chin", "under_chin"],
    "moustache": ["upper_lip"], "mid_face": ["cheek", "nose", "ear"],
}
LINES = {  # tapered lines: [(anchor, offset)], radius (interocular distances)
    "nasolabial.L": ([("lm_nostril.L", (0.1, 0.02, 0.05)), ("lm_mouth_corner.L", (0.2, 0.05, 0.1)),
                      ("lm_mouth_corner.L", (0.23, 0.08, -0.22))], [0.05, 0.075, 0.04]),
    "marionette.L": ([("lm_mouth_corner.L", (0.06, 0.02, -0.03)), ("lm_mouth_corner.L", (0.12, 0.05, -0.42))], [0.06, 0.035]),
    "brow.L": ([("lm_brow_inner.L", (0.0, 0, 0)), ("lm_brow_mid.L", (0, 0, 0)), ("lm_brow_outer.L", (0, 0, -0.01))],
               [0.085, 0.09, 0.045]),
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


def _joints(spec: dict) -> dict:
    from . import paint
    return {k: np.asarray(v["pos"], float) for k, v in paint._expanded(spec)["joints"].items() if "pos" in v}


def _radius(spec: dict, name: str) -> float:
    from . import paint
    return float(paint._expanded(spec)["joints"][name].get("r", 0.03))


def interocular(J: dict) -> float:
    for a, b in (("eye_front.L", "eye_front.R"), ("eye.L", "eye.R")):
        if a in J and b in J:
            return float(np.linalg.norm(J[a] - J[b]))
    if "lm_eye_inner.L" in J and "lm_eye_outer.L" in J:
        return float(2 * abs(0.5 * (J["lm_eye_inner.L"][0] + J["lm_eye_outer.L"][0])))
    return 0.063


def _side(name: str, side: str) -> str:
    return name[:-2] + side if side and name.endswith(".L") else name


def _mx(v, side: str):
    return [(-v[0] if side == ".R" else v[0]), v[1], v[2]]


def _unit(v):
    n = np.linalg.norm(v)
    return v / n if n > 1e-9 else np.array([0.0, 0.0, 1.0])


def _palm_normal(J: dict, s: str) -> np.ndarray:
    """Out of the palm of hand `s` (".L" / ".R"): across the knuckle row and the hand's length, the way the relaxed
    fingers curl."""
    w, a, b = J[f"wrist{s}"], J[f"finger1_0{s}"], J[f"finger4_0{s}"]
    n = _unit(np.cross(a - w, b - w))
    curl = sum(np.dot(J[f"finger{k}_3{s}"] - J[f"finger{k}_1{s}"] - (J[f"finger{k}_1{s}"] - J[f"finger{k}_0{s}"]) *
                      np.dot(J[f"finger{k}_3{s}"] - J[f"finger{k}_1{s}"], _unit(J[f"finger{k}_1{s}"] - J[f"finger{k}_0{s}"])) /
                      max(np.linalg.norm(J[f"finger{k}_1{s}"] - J[f"finger{k}_0{s}"]), 1e-9), n) for k in range(1, 5))
    if abs(curl) < 1e-4:  # straight fingers: the thumb sits on the palm's side of the index finger... use its root
        curl = np.dot(J[f"thumb_1{s}"] - a, n)
    return n if curl > 0 else -n


def _extensor(J: dict, a: str, j: str, b: str, fallback) -> np.ndarray:
    """The outer side of hinge j between a and b (the elbow's point, the kneecap)."""
    u, f = _unit(J[a] - J[j]), _unit(J[b] - J[j])
    inner = u + f
    return -_unit(inner) if np.linalg.norm(inner) > 0.12 else np.asarray(fallback, float)


def _sp(points, radii, soft=0.6, line=False) -> dict:
    return {"spot": {"at": [[round(float(x), 5) for x in p] for p in points],
                     "radius": [[round(float(x), 5) for x in (r if np.ndim(r) else [r] * 3)] for r in radii] if not line
                     else [round(float(r), 5) for r in radii], "soft": soft, **({"line": True} if line else {})}}


def _body_zone(spec: dict, J: dict, name: str, s: str, grow: float) -> list:
    """A body zone's mask entries on side s."""
    r = lambda j: _radius(spec, j) * grow  # noqa: E731
    need = lambda *js: [j for j in js if j not in J]  # noqa: E731
    base = name[:-2] if name.endswith(".L") else name
    if base == "shoulder":
        return [_sp([J[f"shoulder{s}"] + [0, 0, 0.4 * r(f"shoulder{s}")]], [1.5 * r(f"shoulder{s}")])]
    if base == "elbow":
        e = _extensor(J, f"shoulder{s}", f"elbow{s}", f"wrist{s}", [0, 1, 0])
        return [_sp([J[f"elbow{s}"] + 0.75 * r(f"elbow{s}") * e], [1.0 * r(f"elbow{s}")])]
    if base == "knee":
        e = _extensor(J, f"hip{s}", f"knee{s}", f"ankle{s}", [0, -1, 0])
        return [_sp([J[f"knee{s}"] + 0.8 * r(f"knee{s}") * e], [1.05 * r(f"knee{s}")])]
    if base in ("forearm", "upper_arm"):
        a, b = (f"elbow{s}", f"wrist{s}") if base == "forearm" else (f"shoulder{s}", f"elbow{s}")
        return [_sp([J[a], J[b]], [1.35 * r(a), 1.5 * r(b)], line=True)]
    if base == "chest":
        return [_sp([J["chest"] + [0, -1.0 * r("chest"), 1.6 * r("chest")]], [[2.4 * r("chest"), 1.6 * r("chest"), 2.2 * r("chest")]])]
    if base == "collarbone":
        return [_sp([J["neck"] + [0.9 * sx * r("neck"), -0.6 * r("neck"), -1.2 * r("neck")] for sx in (-1, 1)],
                    [[1.3 * r("neck"), 0.9 * r("neck"), 0.5 * r("neck")]] * 2)]
    if base in ("foot", "sole"):
        if need(f"ankle{s}", f"toe{s}"):
            raise SpecError(f"zone {name!r}: the model has no ankle/toe joints")
        c = 0.5 * (J[f"ankle{s}"] + J[f"toe{s}"])
        ball = _sp([c], [0.75 * np.linalg.norm(J[f"toe{s}"] - J[f"ankle{s}"]) * grow])
        return [ball] if base == "foot" else [ball, {"facing": [0, 0, -1], "range": [0.2, 0.7]}]
    # the hand
    miss = need(f"wrist{s}", *[f"finger{k}_{j}{s}" for k in range(1, 5) for j in range(4)])
    if miss:
        raise SpecError(f"zone {name!r}: the model has no hand joints ({miss[0]}...): a base body gives them")
    pn = _palm_normal(J, s)
    roots = [J[f"finger{k}_0{s}"] for k in range(1, 5)]
    centre = (J[f"wrist{s}"] + np.mean(roots, 0)) / 2
    width = np.linalg.norm(roots[0] - roots[3])
    tips = [J[f"finger{k}_3{s}"] for k in range(1, 5)] + [J[f"thumb_3{s}"]]
    span = max(np.linalg.norm(t - centre) for t in tips)
    hand = _sp([centre + 0.35 * (np.mean(tips, 0) - centre)], [1.25 * span * grow], soft=0.3)
    if base == "hand":
        return [hand]
    if base == "palm":
        return [hand, {"facing": [round(float(x), 4) for x in pn], "range": [0.0, 0.55]}]
    if base == "back_of_hand":
        return [_sp([centre - 0.3 * width * pn], [0.85 * width * grow]),
                {"facing": [round(float(x), 4) for x in -pn], "range": [0.1, 0.6]}]
    if base == "wrist_inner":
        return [_sp([J[f"wrist{s}"] + 0.6 * r(f"wrist{s}") * pn + 1.2 * r(f"wrist{s}") * _unit(J[f"elbow{s}"] - J[f"wrist{s}"])],
                    [1.5 * r(f"wrist{s}")])]
    chains = [[J[f"finger{k}_{j}{s}"] for j in range(4)] for k in range(1, 5)] + [[J[f"thumb_{j}{s}"] for j in range(4)]]
    rads = [[_radius(spec, f"finger{k}_{j}{s}") for j in range(4)] for k in range(1, 5)] + \
           [[_radius(spec, f"thumb_{j}{s}") for j in range(4)]]
    if base == "knuckles":  # the back of every finger joint
        pts, rr = [], []
        for ch, ra in zip(chains, rads):
            for j in range(3):
                rj = min(ra[j], 0.014)
                pts.append(ch[j] - 0.75 * rj * pn)
                rr.append((0.95 if j else 1.15) * rj * grow)
        return [_sp(pts, rr)]
    if base == "fingertips":
        return [_sp([0.3 * ch[2] + 0.7 * ch[3] for ch in chains], [1.1 * min(ra[2], 0.012) * grow for ra in rads])]
    if base == "nails":
        pts, rr = [], []
        for ch, ra in zip(chains, rads):
            rj = min(ra[2], 0.011)
            ax = _unit(ch[3] - ch[2])
            for t in (0.45, 0.75):
                pts.append(ch[2] + t * (ch[3] - ch[2]) - 0.85 * rj * pn)
                rr.append(0.62 * rj * grow)
        return [_sp(pts, rr, soft=0.35), {"facing": [round(float(x), 4) for x in -pn], "range": [0.15, 0.6]}]
    raise SpecError(f"no zone {name!r}")


def zone_names() -> list:
    names = set(FACE) | set(UNIONS) | set(LINES) | set(OUTLINES) | set(BODY) | set(EXTRA)
    return sorted(names | {n[:-2] + ".R" for n in names if n.endswith(".L")} | {n[:-2] for n in names if n.endswith(".L")})


def zone(spec: dict, name: str, grow: float = 1.0, what: str = "zone") -> list:
    """A zone as mask stack entries (spot / outline / facing generators)."""
    J = _joints(spec)
    io = interocular(J)
    stem, side = (name[:-2], name[-2:]) if name.endswith((".L", ".R")) else (name, "")
    sides = [side] if side else [".L", ".R"]
    try:
        if stem in ("lash_upper", "lash_lower"):
            # the lid's margin is the skin that touches the eyeball: found from the eyeballs themselves (a line drawn
            # from the lid landmarks sat behind the rim on one head and in the air on the next)
            eyes = [f"eye{sd}" for sd in sides]
            if any(e not in J for e in eyes):
                raise KeyError(eyes[0])
            up = stem == "lash_upper"
            return [{"near": eyes, "within": round((0.0024 if up else 0.0015) * grow, 5), "soft": round(0.0018 * grow, 5)},
                    {"axis": {"dir": [0, 0, 1], "at": eyes[0], "from": 0.0003 if up else -0.0003, "to": 0.0022 if up else -0.0022}}]
        if stem in OUTLINES:
            return [{"outline": {"points": OUTLINES[stem], "dir": [0, 1, 0], "soft": 0.0012 * grow, "depth": 0.03}}]
        key = stem + ".L" if stem + ".L" in FACE or stem + ".L" in UNIONS or stem + ".L" in LINES or stem + ".L" in BODY else stem
        if key in UNIONS:
            out = []
            for m in UNIONS[key]:
                for sd in (sides if key.endswith(".L") else [""]):
                    sub = zone(spec, _side(m, sd) if m.endswith(".L") else m, grow, what)
                    out.append({"mask": sub, **({"blend": "max"} if out else {})})
            return out
        if key in FACE:
            pts, rr = [], []
            for sd in (sides if key.endswith(".L") else [""]):
                for anchor, off, rad in FACE[key]:
                    pts.append(J[_side(anchor, sd)] + io * np.asarray(_mx(off, sd)))
                    rr.append(io * grow * np.asarray(rad))
            return [_sp(pts, rr)]
        if key in LINES:
            out = []
            for sd in sides:
                pl, rad = LINES[key]
                e = _sp([J[_side(a, sd)] + io * np.asarray(_mx(off, sd)) for a, off in pl], [io * grow * x for x in rad], soft=0.7, line=True)
                out.append({**e, **({"blend": "max"} if out else {})})
            return out
        if key in BODY:
            if not key.endswith(".L"):
                return _body_zone(spec, J, key, "", grow)
            out = []
            for sd in sides:
                out.append({"mask": _body_zone(spec, J, key, sd, grow), **({"blend": "max"} if out else {})})
            return out
    except KeyError as err:
        raise SpecError(f"{what}: zone {name!r} needs joint {err.args[0]!r}, which this model doesn't have (zones are "
                        f"placed from a base body's joints and a GNM head's lm_* landmarks)")
    raise SpecError(f"{what}: no zone {name!r} (zones: {', '.join(zone_names())})")


def uses_zones(layers_: dict) -> bool:
    return '"zone"' in json.dumps(layers_, default=str)


def expand_zones(spec: dict, ly: dict, what: str = "paint") -> dict:
    """A layer (or mask entry) with every "zone" generator replaced by the zone's own mask entries."""
    if not isinstance(ly, dict) or '"zone"' not in json.dumps(ly, default=str):
        return ly
    out = dict(ly)
    stack = [expand_zones(spec, e, what) for e in out.get("mask") or []]
    if "zone" in out:
        z = out.pop("zone")
        z = {"name": z} if isinstance(z, str) else z
        if not (isinstance(z, dict) and isinstance(z.get("name"), str) and set(z) <= {"name", "grow"}):
            raise SpecError(f"{what}: zone is a name or {{\"name\", \"grow\"}}")
        entries = zone(spec, z["name"], float(z.get("grow", 1.0)), what)
        if any(k in out for k in ("blend", "weight", "breakup", "levels", "invert", "blur")) and "mask" not in ly:
            out["mask"] = entries  # an entry of a stack: its zone becomes its nested mask
            return out
        stack = [{"mask": entries}] + stack  # a layer's flat key: multiplies what follows
    if stack:
        out["mask"] = stack
    return out


# ---- the description -> layers ----------------------------------------------------------------------------------

KEYS = {"part", "tone", "age", "variation", "detail", "oil", "thin", "sun", "zones", "lips", "features", "wrinkles",
        "hair", "scars", "tattoos", "makeup", "shading", "nails", "seed"}
ZONE_LAYERS = {"forehead_yellow": 1.0, "midface_red": 1.0, "nose_red": 1.0, "ears_red": 1.0, "lower_cool": 1.0,
               "under_eye": 1.0, "eyelids": 1.0, "neck": 1.0, "palms": 1.0, "soles": 1.0, "knuckles": 1.0,
               "elbows_knees": 1.0, "fingertips": 1.0, "nails": 1.0}


def _age_curve(age: float, a0: float, a1: float) -> float:
    """0 before a0, 1 from a1 on (smooth)."""
    t = float(np.clip((age - a0) / max(a1 - a0, 1e-9), 0, 1))
    return t * t * (3 - 2 * t)


def params(spec: dict) -> dict:
    """spec["skin"] with every default filled in (validated)."""
    sk = spec.get("skin") or {}
    if not isinstance(sk, dict):
        raise SpecError("skin is an object: {\"tone\": {...}, \"age\": ...}")
    bad = set(sk) - KEYS
    if bad:
        raise SpecError(f"skin: unknown keys {sorted(bad)} (have {', '.join(sorted(KEYS))})")
    age = float(sk.get("age", 30))
    if not 0 <= age <= 120:
        raise SpecError("skin age is in years")
    p = {"part": sk.get("part", "body"), "tone": tone_params(sk.get("tone")), "age": age, "seed": int(sk.get("seed", 0))}
    for k, d in (("variation", 1.0), ("detail", 1.0), ("oil", 0.5), ("thin", 0.5), ("sun", 0.3)):
        p[k] = float(sk.get(k, d))
        if not 0 <= p[k] <= 3:
            raise SpecError(f"skin {k} is a number 0..1 (up to 3 to exaggerate)")
    z = sk.get("zones") or {}
    bad = set(z) - set(ZONE_LAYERS)
    if bad:
        raise SpecError(f"skin zones: unknown {sorted(bad)} (have {', '.join(ZONE_LAYERS)})")
    p["zones"] = {**ZONE_LAYERS, **{k: float(v) for k, v in z.items()}}
    lips = sk.get("lips") or {}
    bad = set(lips) - {"blood", "melanin", "roughness", "dry"}
    if bad:
        raise SpecError(f"skin lips: unknown keys {sorted(bad)} (have blood, melanin, roughness, dry)")
    p["lips"] = {"blood": float(lips.get("blood", 1.0)), "melanin": float(lips.get("melanin", 1.0)),
                 "roughness": float(lips.get("roughness", 0.36)), "dry": float(lips.get("dry", 0.0))}
    sh = sk.get("shading") or {}
    bad = set(sh) - {"subsurface", "radius", "scale", "specular", "roughness", "coat", "coat_roughness", "sheen", "thickness"}
    if bad:
        raise SpecError(f"skin shading: unknown keys {sorted(bad)} (have subsurface, radius, scale, specular, roughness)")
    p["shading"] = sh
    for k in ("features", "wrinkles", "hair", "makeup", "nails"):
        p[k] = sk.get(k) or {}
        if not isinstance(p[k], dict):
            raise SpecError(f"skin {k} is an object")
    for k in ("scars", "tattoos"):
        p[k] = sk.get(k) or []
        if not isinstance(p[k], list):
            raise SpecError(f"skin {k} is a list")
    return p


def part_base(spec: dict) -> tuple[str, dict] | None:
    """(the skin part, its base channels): the tone's colour, roughness, specular and subsurface. Values the part's
    own definition gives win."""
    if not spec.get("skin"):
        return None
    p = params(spec)
    t, sh = p["tone"], p["shading"]
    old = _age_curve(p["age"], 45, 85)
    # subsurface: red travels furthest (Weyrich 2006: mean free paths ~[1.1-2.8, 0.6-1.3, 0.6-0.7] mm; darker skin
    # absorbs more and scatters less)
    weight = float(sh.get("subsurface", 1.0))
    radius = sh.get("radius") or [round(x, 4) for x in (1.0, 0.36 - 0.1 * t["melanin"], 0.2 - 0.08 * t["melanin"])]
    scale = float(sh.get("scale", (0.0016 + 0.001 * p["thin"]) * (1 - 0.45 * t["melanin"])))
    return p["part"], {"color": tone_rgb(t), "roughness": float(sh.get("roughness", _roughness(p))),
                       "specular": float(sh.get("specular", 0.36)),  # F0 0.028 (IOR 1.4): our 0.5 is 0.04
                       "subsurface": weight, "subsurface_radius": [float(x) for x in radius], "subsurface_scale": scale,
                       # the oily film is a second, tighter highlight over the skin's broad one (a dual lobe: Unreal's
                       # skin mixes two at 0.85); vellus hair gives a soft sheen at grazing angles
                       "coat": float(sh.get("coat", 0.04 + 0.16 * p["oil"])), "coat_roughness": float(sh.get("coat_roughness", 0.28)),
                       "sheen": float(sh.get("sheen", 0.12)), "sheen_roughness": 0.5,
                       "thickness": float(sh.get("thickness", 0.007)),  # light comes through what is thinner (ears, nostrils)
                       "_old": old}


def _roughness(p: dict) -> float:
    child = 1 - _age_curve(p["age"], 6, 18)
    return float(np.clip(0.46 - 0.05 * (p["oil"] - 0.5) + 0.06 * _age_curve(p["age"], 45, 85) - 0.03 * child, 0.2, 0.9))


def _z(*names, grow=1.0) -> list:
    """A mask stack: the union of zones."""
    return [{"zone": {"name": n, "grow": grow}, **({"blend": "max"} if i else {})} for i, n in enumerate(names)]


def layers(spec: dict) -> dict:
    """The skin's paint layers, in order: {"skin:<name>": layer}."""
    if not spec.get("skin"):
        return {}
    key = hashlib.sha1(json.dumps([spec["skin"], VERSION], sort_keys=True, default=str).encode()).hexdigest()
    J = _joints(spec)
    jk = hashlib.sha1(json.dumps(sorted((k, np.round(v, 5).tolist()) for k, v in J.items())).encode()).hexdigest()
    if _LAYERS.get("key") != (key, jk):
        _LAYERS.clear()
        _LAYERS.update(key=(key, jk), layers=_build(spec, J))
    return copy.deepcopy(_LAYERS["layers"])


_LAYERS: dict = {}


def _build(spec: dict, J: dict) -> dict:
    p = params(spec)
    part, t, seed = p["part"], p["tone"], p["seed"]
    no_pores = []
    var, det, age = p["variation"], p["detail"], p["age"]
    face = "lm_nose_tip" in J
    hands = "finger1_0.L" in J and "wrist.L" in J
    arms = all(k in J for k in ("shoulder.L", "elbow.L", "wrist.L"))
    legs = all(k in J for k in ("hip.L", "knee.L", "ankle.L"))
    feet = "toe.L" in J and "ankle.L" in J
    child = 1 - _age_curve(age, 6, 18)
    old = _age_curve(age, 45, 85)
    dark = t["melanin"]
    thin = p["thin"] + 0.3 * old + 0.15 * child
    T = lambda **kw: tone_rgb(t, **kw)  # noqa: E731
    out: dict = {}

    def add(name, strength=1.0, **ly):
        s = strength * p["zones"].get(name, 1.0)
        if s <= 0:
            return
        if "opacity" in ly:
            ly["opacity"] = round(float(np.clip(ly["opacity"] * s, 0, 1)), 4)
        out[f"skin:{name}"] = {"part": part, "_pre": True, **ly}

    # 1. colour zones: where blood shows (mid-face, ears, nose, fingertips), where it doesn't (forehead: yellower),
    #    the cooler lower third, thin skin round the eyes, lighter palms and soles, darker rougher joints
    if face:
        add("forehead_yellow", var, color=T(blood=0.62, yellow=0.5), opacity=0.5, mask=_z("forehead", "temple"))
        add("midface_red", var, color=T(blood=2.7 + 0.6 * child), opacity=0.62 + 0.12 * child,
            mask=_z("cheek", "cheekbone", "nose_bridge") + [{"zone": "chin", "blend": "max", "weight": 0.4}])
        add("nose_red", var, color=T(blood=3.0), opacity=0.5, mask=_z("nose_tip", "nose_wing"))
        add("ears_red", var, color=T(blood=3.2, melanin=1.05), opacity=0.6, mask=_z("ear"))
        add("lower_cool", var, color=T(blood=0.75, oxygenation=0.4, melanin=1.12, grey=0.12), opacity=0.34,
            mask=_z("jaw", "upper_lip", "soul_patch", "under_chin") + [{"zone": "cheek_side", "blend": "max", "weight": 0.5}])
        add("under_eye", var * (0.7 + 0.6 * thin), color=T(blood=1.7, oxygenation=0.3, melanin=1.25, epidermis=0.7),
            opacity=0.42, mask=_z("under_eye", "eye_corner"))
        add("eyelids", var, color=T(blood=1.9, oxygenation=0.55, melanin=1.1, epidermis=0.75), opacity=0.36, mask=_z("eyelid"))
        add("neck", var, color=T(blood=0.85, melanin=0.94), opacity=0.4, mask=_z("neck"))
    if hands:
        add("palms", 1.0, color=T(melanin=0.22 + 0.1 * (1 - dark), blood=1.7), opacity=0.85, mask=_z("palm"))
        add("knuckles", var, color=T(melanin=1.3 + 0.3 * dark, blood=1.55), opacity=0.42, mask=_z("knuckles"))
        add("fingertips", var, color=T(blood=2.3), opacity=0.4, mask=_z("fingertips"))
    if feet:
        add("soles", 1.0, color=T(melanin=0.25, blood=1.6), opacity=0.8, mask=_z("sole"))
    joints_ = (["elbow"] if arms else []) + (["knee"] if legs else [])
    if joints_:
        add("elbows_knees", var, color=T(melanin=1.3 + 0.35 * dark, blood=1.4, grey=0.1), opacity=0.4, mask=_z(*joints_))

    # 2. mottling: blood is never even (blotches of 1-2 cm, redder and paler), nor is pigment
    def mottle(name, scale, rng, sd, opacity, **tone):
        out[f"skin:{name}"] = {"part": part, "_pre": True, "color": T(**tone), "opacity": round(float(np.clip(opacity * var, 0, 1)), 4),
                               "mask": [{"noise": {"scale": scale, "range": rng, "seed": seed + sd, "octaves": 3}}]}
    mottle("mottle_red", 0.014, [0.42, 0.85], 11, 0.34 + 0.1 * thin, blood=2.0)
    mottle("mottle_pale", 0.02, [0.42, 0.88], 12, 0.3, blood=0.45, melanin=0.92)
    mottle("mottle_pigment", 0.032, [0.45, 0.8], 13, 0.2 + 0.25 * p["sun"] * (0.4 + old), melanin=1.3)
    mottle("mottle_fine", 0.0032, [0.45, 0.75], 14, 0.2, blood=1.7, melanin=1.15)
    mottle("mottle_fine_pale", 0.0045, [0.5, 0.8], 15, 0.16, blood=0.6, melanin=0.9)

    # 3. lips: thin epidermis over a lot of blood; less melanin than the face on light skin, still much on dark
    if face:
        lp = p["lips"]
        lm = (0.55 + 0.4 * dark) * lp["melanin"]
        le = 0.5 + 0.4 * dark  # dark lips keep most of their pigment: the upper one browner, the lower pinker
        out["skin:lips_upper"] = {"part": part, "_pre": True, "color": T(melanin=lm * 1.15, blood=6.0 * lp["blood"], epidermis=le,
                                                           oxygenation=0.62), "opacity": 0.85, "roughness": lp["roughness"] + 0.04,
                                  "mask": _z("lip_upper", grow=2.2)}
        out["skin:lips_lower"] = {"part": part, "_pre": True, "color": T(melanin=lm * 0.9, blood=7.0 * lp["blood"], epidermis=le - 0.08, oxygenation=0.68),
                                  "opacity": 0.85, "roughness": lp["roughness"], "mask": _z("lip_lower", grow=2.2)}
        # the vermilion border: a paler, slightly raised rim where lip meets skin (clearer on light skin)
        out["skin:lip_border"] = {"part": part, "_pre": True, "color": T(melanin=0.7, blood=0.8), "opacity": round(0.22 * (1 - 0.6 * dark), 3),
                                  "mask": [{"zone": {"name": "lips", "grow": 3.5}},
                                                              {"zone": {"name": "lips", "grow": 0.4}, "blend": "subtract"}]}
        out["skin:lip_seam"] = {"part": part, "_pre": True, "color": T(melanin=lm * 1.6, blood=3.2, oxygenation=0.5), "opacity": 0.7,
                                "mask": [{"spot": {"at": ["lm_mouth_corner.R", "lm_lip_inner_upper.R", "lm_lip_seam",
                                                          "lm_lip_inner_upper.L", "lm_mouth_corner.L"],
                                                   "radius": [0.0008, 0.0016, 0.0018, 0.0016, 0.0008], "soft": 0.8, "line": True}}]}
    if hands:
        add("nails", 1.0, color=T(melanin=0.12, blood=2.4, epidermis=0.4), opacity=0.75, roughness=0.22, specular=0.5,
            mask=_z("nails"))

    # 4. roughness: sebum on the T-zone, drier rougher joints, and it is never even
    base_r = _roughness(p)
    if face:
        out["skin:rough_tzone"] = {"part": part, "_pre": True, "roughness": round(float(np.clip(base_r - 0.07 - 0.12 * (p["oil"] - 0.3), 0.18, 0.9)), 3),
                                   "opacity": 0.8, "mask": _z("forehead", "glabella", "nose_bridge", "nose_tip", "nose_wing") +
                                   [{"zone": "chin", "blend": "max", "weight": 0.6}, {"zone": "eyelid", "blend": "max", "weight": 0.8}]}
    if hands or joints_:
        out["skin:rough_joints"] = {"part": part, "_pre": True, "roughness": round(min(base_r + 0.16, 0.95), 3), "opacity": 0.8,
                                    "mask": _z(*((["knuckles"] if hands else []) + joints_))}
    out["skin:rough_patches"] = {"part": part, "_pre": True, "roughness": round(min(base_r + 0.12 + 0.08 * dark, 0.95), 3), "opacity": 0.8,
                                 "mask": [{"noise": {"scale": 0.005, "range": [0.38, 0.72], "seed": seed + 21}}]}
    out["skin:rough_fine"] = {"part": part, "_pre": True, "roughness": round(min(base_r + 0.14, 0.95), 3), "opacity": 0.6,
                              "mask": [{"noise": {"scale": 0.0022, "range": [0.42, 0.7], "seed": seed + 23}}]}
    out["skin:rough_sheen"] = {"part": part, "_pre": True, "roughness": round(max(base_r - 0.1, 0.15), 3), "opacity": 0.6,
                               "mask": [{"noise": {"scale": 0.011, "range": [0.55, 0.85], "seed": seed + 22, "warp": 0.6}}]}

    from . import skin_features
    smooth = skin_features.build(spec, p, J, out, T, {"face": face, "hands": hands, "arms": arms, "legs": legs, "feet": feet,
                                                      "child": child, "old": old, "thin": thin, "base_r": base_r})
    no_pores = [{"mask": s, "blend": "subtract"} for s in smooth]  # scar tissue is smooth

    # last: micro relief (pores, the polygonal net of skin lines, the grain between them), over everything, ink and
    # make-up included: tiling swatches, relief + darker, rougher furrows (cavity: "pores catch no light")
    if det > 0:
        d = det * (1 - 0.45 * child) * (1 + 0.5 * dark)  # dark skin shows its highlight more: the same relief must break it up
        body_k = 1.0 + 0.5 * old
        micro = []
        if face:
            micro.append(("pores", "pores", 0.00021 * d * (0.8 + 0.4 * p["oil"]), _z("face") + [{"zone": "lips", "blend": "subtract"}]))
            micro.append(("lip_lines", "lips", 0.00014 * d * (1 + p["lips"]["dry"]), _z("lips")))
            micro.append(("lines", "lines", 0.00018 * d * body_k, [{"mask": _z("face"), "invert": True}]))
        else:
            micro.append(("lines", "lines", 0.00018 * d * body_k, None))
        if hands or joints_:
            micro.append(("coarse", "coarse", 0.00016 * d * body_k, _z(*((["knuckles"] if hands else []) + joints_), grow=1.25)))
        for name, sw, depth, mask in micro:
            stack = [{"tile": {"swatch": sw}}] + ([{"mask": mask, "blend": "multiply", "vertex": True}] if mask else []) + copy.deepcopy(no_pores)
            out[f"skin:micro_{name}"] = {"part": part, "_detail": True, "height": -round(depth, 7), "color": [0.8, 0.66, 0.62], "mix": "multiply",
                                         "opacity": round(min(0.6 * d, 1), 3), "roughness": round(min(base_r + 0.22, 0.95), 3),
                                         "mask": stack}
    return out


def export_recipe(spec: dict, out_dir, stem: str) -> dict | None:
    """What an engine needs beside the baked maps to shade this skin: the tiling micro-detail normal maps (written
    into out_dir; the unique maps hold everything down to the texel, the pores live here) and the scattering,
    coat and sheen numbers. Goes into the skin material's extras ("hifipushie_skin") and the export's json."""
    from pathlib import Path
    from . import paint, skin_swatch
    if not spec.get("skin"):
        return None
    base = part_base(spec)[1]
    details = []
    for name, ly in paint.layers(spec).items():
        if not ly.get("_detail"):
            continue
        tile = next((e["tile"] for e in ly.get("mask") or [] if "tile" in e), None)
        if tile is None:
            continue
        sw, depth = tile["swatch"], abs(float(ly["height"]))
        f = Path(out_dir) / f"{stem}_skin_{sw}_normal.png"
        skin_swatch.normal_map(sw, depth, f)
        where = {"micro_pores": "the face (not the lips)", "micro_lip_lines": "the lips", "micro_lines": "the body (everything but the face)",
                 "micro_coarse": "knuckles, elbows, knees"}.get(name[5:], name[5:])
        details.append({"layer": name[5:], "normal": f.name, "period_m": float(tile.get("size", skin_swatch.PERIOD[sw])),
                        "depth_m": round(depth, 7), "cavity_tint": ly.get("color"), "cavity_opacity": ly.get("opacity"),
                        "cavity_roughness": ly.get("roughness"), "where": where})
    r, sc = base["subsurface_radius"], base["subsurface_scale"]
    return {
        "detail": details,
        "detail_recipe": "Each detail normal map tiles: one repeat = period_m metres of skin. Lay it by world/object position "
                         "(triplanar by the normal: uv = position / period_m on the two axes across the dominant normal axis) or by "
                         "a uv with a known scale, blend its normal over the baked normal map (whiteout / reoriented), darken base "
                         "colour by cavity_tint x cavity_opacity and raise roughness toward cavity_roughness where the map's "
                         "normal leans (its furrows). To hide the repeat, mix in a second copy at 1.618 x the period by a "
                         "low-frequency (7 cm) noise. Fade the detail out with distance (past ~1.5 m it is sub-pixel).",
        "subsurface": {"weight": base["subsurface"], "mean_free_path_m": [round(float(x) * sc, 6) for x in r],
                       "note": "radius per channel (R, G, B): red travels furthest. Unreal: Subsurface Profile with Mean Free "
                               "Path Color = radius / max and Distance = max in cm; Unity HDRP: Diffusion Profile scattering "
                               "distance; Blender: Principled Subsurface Radius x Scale. glTF has no ratified subsurface "
                               "extension (KHR_materials_diffuse_transmission is a release candidate)."},
        "specular": {"f0": 0.028, "ior": 1.4, "coat": base["coat"], "coat_roughness": base["coat_roughness"],
                     "note": "a tight second lobe over the broad one (the oily film): KHR_materials_clearcoat in the GLB; "
                             "Unreal's dual specular (lobe mix) or Unity's dual lobe do the same"},
        "sheen": base["sheen"],
        "tone": tone_params((spec.get("skin") or {}).get("tone")), "base_color_srgb": base["color"],
    }


def reference() -> str:
    """The zones and the description's keys, for the skin_reference tool."""
    from . import skin_features
    z = zone_names()
    centre = [n for n in z if not n.endswith((".L", ".R")) and n + ".L" not in z]
    sided = [n for n in z if n + ".L" in z]
    return "\n".join([
        "ZONES (paint generator {\"zone\": name}; sided ones take .L / .R, the bare name is both sides):",
        "  centre: " + ", ".join(centre),
        "  sided:  " + ", ".join(sided),
        "",
        __doc__.split("spec[\"skin\"] = {", 1)[1].join(["spec[\"skin\"] = {", ""]).rsplit("Anatomical zones", 1)[0].rstrip(),
        "",
        skin_features.reference(),
        "",
        "TONE: fitzpatrick 1..6 = melanin " + ", ".join(f"{k}: {v}" for k, v in FITZPATRICK.items()) +
        "; albedo of the base tone (sRGB) at blood 0.4: " +
        ", ".join(f"F{k} {''.join(f'{int(round(c * 255)):02x}' for c in tone_rgb({'fitzpatrick': k}))}" for k in range(1, 7)),
        "BUILT-IN ZONE LAYERS (skin.zones: {layer: strength}): " + ", ".join(ZONE_LAYERS),
    ])
