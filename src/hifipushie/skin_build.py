"""The description -> layers: `layers`, the build, the aperture keep-out, the export recipe, `reference`. Part of skin (skin.py has the spec)."""
from __future__ import annotations

import copy
import hashlib
import json

import numpy as np

from . import skin
from . import skin_params, skin_zones
from .skin import tone_params, tone_rgb
from .skin_params import _age_curve, _roughness, _z, group_of, params, shaded
from .skin_zones import zone_names

def layers(spec: dict) -> dict:
    """The skin's paint layers, in order: {"skin:<name>": layer}."""
    if not spec.get("skin"):
        return {}
    from . import base_gnm_parts, base_implied
    eg = base_implied.eye_native(spec) if (spec.get("base") or {}).get("eyes") else None  # (GNM's eye: its limbus and pupil
    # are the drawn iris' defaults, and come from the identity / expression, not from the joints)
    key = hashlib.sha1(json.dumps([spec["skin"], (spec.get("base") or {}).get("lashes"), skin.VERSION,
                                   [round(eg["limbus"], 6), round(eg["pupil"], 4)] if eg else None,
                                   # (GNM's own mouth: its gum and bag masks are made from the head as built)
                                   (spec.get("base") or {}).get("head") if base_gnm_parts.mouth_mode(spec.get("base") or {}) == "gnm"
                                   else None], sort_keys=True,
                                  default=str).encode()).hexdigest()
    J = skin_zones._joints(spec)
    jk = hashlib.sha1(json.dumps(sorted((k, np.round(v, 5).tolist()) for k, v in J.items())).encode()).hexdigest()
    if skin._LAYERS.get("key") != (key, jk):
        skin._LAYERS.clear()
        skin._LAYERS.update(key=(key, jk), layers=_build(spec, J))
    return copy.deepcopy(skin._LAYERS["layers"])


def _aperture_keep_out(spec: dict, part: str, out: dict) -> None:
    """The eye region's layers (zones round the eyes, wrinkles, make-up, anything addressed by an eye / lid / lash
    zone or landmark) fade out on the skin within ~1 mm of the eyeballs: the lid's margin and the skin rolling into
    the socket. There the waterline and caruncle are the colour (and the lash line, along the lashes' roots). Without
    this, the lid tints and lash bands darkened the margin and the 478-point detector read the dressed opening
    1.4 mm smaller than the clay's (Garrett, facesliders' eye diagnosis 2026-10-09)."""
    blobs = (spec.get("blobs") or {})
    eyes = [e for e in ("eye.L", "eye.R") if e in blobs or e.replace(".R", ".L") in blobs]
    if not eyes:
        from . import paint as _paint
        eb = _paint._expanded(spec).get("blobs") or {}
        eyes = [e for e in ("eye.L", "eye.R") if e in eb]
    if len(eyes) < 2:
        return
    # (every layer but the margin's own: zones are resolved to spots by here, so names can't pick the eye's ones, and
    # within 1 mm of the ball there is nothing else; the part's base tone stays under)
    # Cost: the pre-composited layers are evaluated per vertex (free in the shader); of the rest only the eye
    # region's, and per vertex ("vertex": true): a near mask on every layer ran Cycles out of shader stack (bake)
    import os
    if os.environ.get("HIFIPUSHIE_NO_KEEP_OUT"):  # (diagnostics: the layers as they were)
        return
    w, s = skin.APERTURE_KEEP
    eye_words =("eye", "lid", "lash", "crows", "socket", "tear")
    for name, ly in out.items():
        if name in skin.APERTURE_OWN or ly.get("part", part) != part:
            continue
        if ly.get("_pre"):
            ly["mask"] = list(ly.get("mask") or []) + [{"near": eyes, "within": w, "soft": s, "invert": True}]
        elif any(k in name for k in eye_words):
            ly["mask"] = list(ly.get("mask") or []) + [{"near": eyes, "within": w, "soft": s, "invert": True,
                                                        "vertex": True}]


def _build(spec: dict, J: dict) -> dict:
    p = params(spec)
    part, t, seed = p["part"], p["tone"], p["seed"]
    no_pores = []
    var, det, age = p["variation"], p["detail"], p["age"]
    det = det * (1 - 0.22 * p["fem"] + 0.12 * p["masc"])  # finer pores on a woman's face, coarser on a man's
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
        if name in p["zone_colors"]:
            ly["color"] = list(p["zone_colors"][name])
        out[f"skin:{name}"] = {"part": part, "_pre": True, **ly}

    # 1. colour zones: where blood shows (mid-face, ears, nose, fingertips), where it doesn't (forehead: yellower),
    #    the cooler lower third, thin skin round the eyes, lighter palms and soles, darker rougher joints
    if face:
        add("forehead_yellow", var, color=T(blood=0.62, yellow=0.5), opacity=0.5, mask=_z("forehead", "temple"))
        add("midface_red", var, color=T(blood=2.7 + 0.6 * child), opacity=0.62 + 0.12 * child,
            mask=_z("cheek", "cheekbone", "nose_bridge") + [{"zone": "chin", "blend": "max", "weight": 0.4}])
        add("nose_red", var, color=T(blood=3.0), opacity=0.5, mask=_z("nose_tip", "nose_wing"))
        # redness round the mouth (thin skin over the orbicularis, shaving on men): without it the chin-lip band read greener
        # than the cheeks and chin round it (a green band under Tess's lower lip)
        add("perioral_red", var, color=T(blood=2.2, melanin=1.02), opacity=0.36,
            mask=_z("upper_lip", "soul_patch", "mouth_corner") + [{"zone": "chin", "blend": "max", "weight": 0.6}])
        add("ears_red", var, color=T(blood=3.2, melanin=1.05), opacity=0.6, mask=_z("ear"))
        # (the lower face's cool cast is the beard's under the skin: faint on a woman; on Tess it read as a green band under her lip)
        add("lower_cool", var * (1 - 0.75 * p["fem"]), color=T(blood=0.75, oxygenation=0.4, melanin=1.12, grey=0.12), opacity=0.34,
            mask=_z("jaw", "upper_lip", "soul_patch", "under_chin") + [{"zone": "cheek_side", "blend": "max", "weight": 0.5}])
        add("under_eye", var * (0.7 + 0.6 * thin), color=T(blood=1.8, oxygenation=0.25, melanin=1.5, epidermis=0.7),   # (the tear trough: brown-violet)
            opacity=0.5, mask=_z("under_eye", "eye_corner"))
        add("eyelids", var, color=T(blood=1.9, oxygenation=0.55, melanin=1.1, epidermis=0.75), opacity=0.36, mask=_z("eyelid"))
        # periorbital pigment (off unless asked: skin.zones.periorbital; skin_read sets it from the references): the
        # whole socket, lid to tear trough, darker and browner (melanin and old blood in thin skin: deep-set and
        # tired eyes, many South Asian and Mediterranean faces)
        add("periorbital", 1.0, color=T(blood=1.5, oxygenation=0.35, melanin=2.2, epidermis=0.85), opacity=0.3,
            mask=_z("eyelid", "under_eye", "eye_corner", grow=1.15))
        # the upper lid's own darkening (off unless asked: skin.zones.lid_shade), on the eyelid zone alone: a NEUTRAL, a hair
        # cool multiply. Measured (skincheck "eye lid - cheek", the band 1-3 mm above the margin, r3 gate renders): the
        # photographed lid is darker than the cheek (Garrett dL -19 / -13, Tess -14 / -9) and a little LESS red and yellow
        # (da* -0.4 .. -3.8, db* -0.7 .. -4.5); ours -3 / +1 and warmer. So not melanin (it adds b*: L -13 costs b* +7),
        # not the blood-red "eyelids" zone (read orange), not periorbital (reaches the under-eye: a grey bruise; moved
        # nothing measurable on garrett_g9). Zone 1 multiplies by ~0.82, 1.66 by 0.7 (dL ~ -14 at L 65)
        add("lid_shade", 1.0, color=[0.7, 0.7, 0.74], mix="multiply", opacity=0.6, mask=_z("eyelid"))
        # the under-eye's own darkening (off unless asked: skin.zones.under_eye_shade), the tear trough alone: a slightly violet
        # multiply. Under a measured stack the "under_eye" zone is dropped with the other zones, so nothing moved the
        # under-eye / cheek row (ours 1.10-1.27 vs photo 1.05-1.20, lighter; r6 2026-10-16). Kept over a stack like lid_shade.
        add("under_eye_shade", 1.0, color=[0.74, 0.7, 0.74], mix="multiply", opacity=0.6, mask=_z("under_eye"))
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
    # (fine mottling up from 0.2 / 0.16: the 0.35-1.4 mm L bands measured 0.15-0.18 on Tess against 0.39-0.47 on her photo, skin3)
    mottle("mottle_fine", 0.0032, [0.45, 0.75], 14, 0.32, blood=1.7, melanin=1.15)
    mottle("mottle_fine_pale", 0.0045, [0.5, 0.8], 15, 0.26, blood=0.6, melanin=0.9)
    # 2b. the face's base skin per PIXEL, a unique map on the head's own surface (skin_marks_pores.base_map): blood and pigment
    # uneven at 1-4 mm, capillary threads beside the nose, and (micro_map, last) pores by zone + skin lines + a fine
    # undulation as relief. The mottles above are per vertex: nothing of theirs lives below ~3 mm (skin3 measured
    # Tess's 0.35-1.4 mm lightness bands at .16-.18 against .39-.47 on her photo)
    base_map = None
    if face and (var > 0 or det > 0):
        from . import skin_marks_pores
        bpath, bplace, _ = skin_marks_pores.base_map(spec, part, J, {"pore_size": round(1 - 0.15 * p["fem"] + 0.15 * p["masc"] + 0.25 * old, 3),
                                                              "seed": seed})
        base_map = lambda ch, lv=None: {"image": {"file": bpath, **bplace, "channel": ch}, **({"levels": lv} if lv else {})}  # noqa: E731
        if var > 0:
            out["skin:mottle_map_red"] = {"part": part, "color": T(blood=2.4), "opacity": round(min(skin.BASE_MAP["red"] * var ** 0.5, 1), 3),
                                          "mask": [base_map("g", [0.5, 1.0])]}
            out["skin:mottle_map_pigment"] = {"part": part, "color": T(melanin=1.6 + 1.2 * (1 - dark)), "opacity": round(min((skin.BASE_MAP["pigment"] + 0.2 * p["sun"]) * var ** 0.5, 1), 3),
                                              "mask": [base_map("b", [0.5, 1.0])]}
            # and lighter where either dips (less blood, less melanin): uneven both ways, the complexion's mean kept (one
            # way only tanned Tess); one layer for both dips, the shader's budget
            out["skin:mottle_map_light"] = {"part": part, "color": T(blood=0.55, melanin=0.55), "opacity": round(min(skin.BASE_MAP["light"] * var ** 0.5, 1), 3),
                                            "mask": [base_map("g", [0.5, 0.0]), {**base_map("b", [0.5, 0.0]), "blend": "max"}]}

    # 3. lips: thin epidermis over a lot of blood; less melanin than the face on light skin, still much on dark
    if face:
        lp = {**p["lips"], "blood": p["lips"]["blood"] * (1 + 0.25 * p["fem"])}
        lm = (0.55 + 0.4 * dark) * lp["melanin"]
        le = 0.5 + 0.4 * dark  # dark lips keep most of their pigment: the upper one browner, the lower pinker
        # the border's softness (lips.border, mm: the outline's own edge is 1.2 mm x grow): a vermilion ends in a
        # millimetre or two of mixed skin, the lower lip's more; at 1 mm both lips read as a cut-out fill (skinfolds)
        bg, bgl = lp["border"] / 1.2, 1.3 * lp["border"] / 1.2
        gr = lp["gradient"]
        # (tried, skinfolds: a `venous` control, less oxygenated blood, to darken lips without melanin's brown: 0.62 ->
        # 0.25 moved a lip 2 L and took 6 a* off: not a lever. What darkens a lip in this model is its melanin, and
        # lips.melanin is x the TONE's: on a very fair tone, 0.04, it needs 10-20 to reach a dark upper lip)
        ox = lambda o: o  # noqa: E731
        # lips.strength (skinfolds): how much of the vermilion is the lips' own colour (x the layers' opacity: 0.85, a
        # man's 0.65 by default). THE "STUCK" LIPS: at 0.65 a third of a man's lip is his skin's colour whatever
        # lips.blood / melanin say (blood saturates at 3): Garrett's upper lip stayed 11 L lighter than the painting's
        lop = round(float(np.clip((0.85 - 0.2 * p["masc"]) * lp["strength"], 0.0, 1.0)), 3)
        # ROUNDED, POCKETED CORNERS (mouth_eye_bias -> skin, 2026-10-15): in photos the red fades out before the
        # commissure and the corner itself is a small dark rounded pocket; our vermilion ran as a flat fill out to sharp
        # points (wide, thin, pasted on). The lips' own colour loses ~70 % over the last CORNER_FADE m of each corner
        _crn = ("verm_u00", f"verm_u{skin._VN - 1:02d}") if f"verm_u{skin._VN - 1:02d}" in J else ("lm_mouth_corner.R", "lm_mouth_corner.L")
        corner_fade = [{"spot": {"at": list(_crn), "radius": skin.CORNER_FADE, "soft": 1.0}, "blend": "subtract", "weight": 0.7}]
        out["skin:lips_upper"] = {"part": part, "_pre": True, "color": T(melanin=lm * 1.15, blood=6.0 * lp["blood"], epidermis=le,
                                                           oxygenation=ox(0.62)), "opacity": lop, "roughness": lp["roughness"] + 0.04,
                                  "mask": _z("lips", grow=bg) + corner_fade}  # (all the vermilion: the lower layer paints over its own
        # part next. Drawn as lip_upper (border -> the contact ring) it missed ~2/3 of the upper vermilion: seen from the
        # front the contact ring lies ABOVE the lip's own lower front, so the face's pale layers showed there and
        # skin.lips never reached the upper lip; the likeloop agent's "lip colour stuck")
        # the lower lip as pigmented as the upper, a little less: in photos (skin_refs, Tess) the lower lip's a* over
        # the skin is the upper's +1 (median), and it reads lighter by ~16 L, of which the light from above gives
        # ~13 on our heads (clay). At blood 7 / melanin 0.9 / thinner epidermis it read +7 a* redder and 6 L darker
        # than the upper in the albedo: an orange-red flat lower lip that hid its own shading (gnmdetail2)
        out["skin:lips_lower"] = {"part": part, "_pre": True, "color": T(melanin=lm * skin.LOWER_LIP["melanin"] * lp["lower"]["melanin"],
                                                                   blood=skin.LOWER_LIP["blood"] * lp["blood"] * lp["lower"]["blood"],
                                                                   epidermis=le + skin.LOWER_LIP["epidermis"], oxygenation=ox(skin.LOWER_LIP["oxygenation"])),
                                  "opacity": lop, "roughness": lp["roughness"], "mask": _z("lip_lower", grow=bgl) + corner_fade,
                                  **({"specular": round(lp["specular"], 3)} if lp.get("specular") is not None else {})}
        # the vermilion border: a paler, slightly raised rim where lip meets skin (clearer on light skin)
        rl = lp.get("rim_lower", skin.RIM_LOWER)
        rim = ([{"zone": {"name": "lips", "grow": 1.6}}] if rl >= 1.0 else
               [{"zone": {"name": "lip_upper", "grow": 1.6}}] if rl <= 0.0 else
               [{"zone": {"name": "lip_upper", "grow": 1.6}}, {"zone": {"name": "lip_lower", "grow": 1.6}, "blend": "max", "weight": rl}])
        out["skin:lip_border"] = {"part": part, "_pre": True, "color": T(melanin=0.7, blood=0.8), "opacity": round(0.22 * (1 - 0.6 * dark), 3),
                                  "mask": rim + [{"zone": {"name": "lips", "grow": 0.4}, "blend": "subtract"}]}
        # THE SHADE UNDER THE LOWER LIP (lips.under_shade; mouth_eye_bias): in photographs the skin just under the lower
        # lip is 5-17 L* darker than the skin over the upper lip (the everted pad's own shadow and the sulcus turning
        # away), deepest under the middle; our heads under the photo's fitted light showed ~4 (no overhang to cast it,
        # a frontal fill). Without it the lower lip reads as a flat band, thin, running to the corners. A soft warm
        # multiply band under the border, widest at the middle, never on the red.
        us = lp.get("under_shade", skin.UNDER_SHADE)
        if us > 0 and "lm_lip_lower" in J:
            # the lower lip's outline with a wide soft edge (its outer half falls off over ~2.5 mm under the border), off
            # the red, and only under the lip's middle (a wide flat ellipse under its centre: the pad's shadow fades
            # toward the corners)
            out["skin:lip_under_shade"] = {"part": part, "color": [0.56, 0.45, 0.42], "mix": "multiply",
                                           "opacity": round(min(1.0 * us, 1.0), 3),
                                           "mask": [{"zone": {"name": "lip_lower", "grow": 4.0}},
                                                    {"zone": {"name": "lips", "grow": 0.3}, "blend": "subtract"},
                                                    {"spot": {"at": [{"at": "lm_lip_lower", "offset": [0.0, 0.0, -0.002]}],
                                                              "radius": [[0.014, 0.012, 0.006]], "soft": 0.9}}]
                                           # (+ the commissures' rounded pockets: the same warm shade; one layer, the budget)
                                           + ([{"spot": {"at": list(_crn), "radius": 0.0022, "soft": 1.0}, "blend": "max",
                                                "weight": round(min(0.4 * lp["gradient"] / max(us, 1e-6), 1.0), 3)}] if lp["gradient"] > 0 else [])}
        # the lower lip's moist centre: smoother, so it catches a highlight (bare lips read matte and painted without it)
        if "lm_lip_lower" in J and "lm_lip_inner_lower" in J:
            # (a SOFT sheen on the lower lip's pad, not a gloss: Joe 2026-10-15, the export mouths read as wet plastic;
            # lips.roughness - 0.22 down to 0.12 was that. The pad's highlight comes broad and dim from the photo light)
            out["skin:lip_sheen"] = {"part": part, "_pre": True, "opacity": 0.8,
                                     "roughness": round(lp["sheen"] if lp.get("sheen") is not None else max(lp["roughness"] - 0.1, 0.24), 3),
                                     **({"specular": round(lp["specular"], 3)} if lp.get("specular") is not None else {}),
                                     "mask": [{"spot": {"at": [{"at": "lm_lip_lower", "offset": [0.0, -0.0005, 0.0028]}],
                                                        "radius": [[0.013, 0.007, 0.0032]], "soft": 1.0}}, {"zone": {"name": "lip_lower", "grow": 0.6}}]}
        # (the seam ends at the vermilion's own corners on a GNM head: lm_mouth_corner sits ~6 mm further out on the cheek
        # there, and the line ran on past the mouth as a dark slit; Garrett 2026-10-09)
        cr, cl = ("verm_u00", f"verm_u{skin._VN - 1:02d}") if f"verm_u{skin._VN - 1:02d}" in J else ("lm_mouth_corner.R", "lm_mouth_corner.L")
        # THE GRADIENT (lips.gradient; skinfolds): a vermilion is not one colour. Toward the wet line and into the
        # corners it is darker and more venous (thin, moist mucosa over the orbicularis, and less light gets there);
        # the lower lip's body is its lightest part. Wide soft lines along the seam, inside the vermilion only.
        if gr > 0 and "lm_lip_seam" in J:
            seam = [cr, "lm_lip_inner_upper.R", "lm_lip_seam", "lm_lip_inner_upper.L", cl]
            inner = T(melanin=lm * 1.5, blood=5.0 * lp["blood"], epidermis=le, oxygenation=0.45)
            out["skin:lip_inner"] = {"part": part, "_pre": True, "color": inner, "opacity": round(min(0.5 * gr, 1.0), 3),
                                     "mask": [{"spot": {"at": seam, "radius": [0.0022, 0.0042, 0.0048, 0.0042, 0.0022], "soft": 1.0, "line": True}},
                                              {"zone": {"name": "lips", "grow": 0.8}}]}
            # the commissures: a small dark ROUNDED pocket at each corner (multiply, a little inside the corner point
            # and onto the skin round it), not the vermilion's red carried into a point
            if not (lp.get("under_shade", skin.UNDER_SHADE) > 0 and "lm_lip_lower" in J):   # (else drawn in skin:lip_under_shade)
                out["skin:lip_corners"] = {"part": part, "color": [0.6, 0.47, 0.45], "mix": "multiply", "opacity": round(min(0.4 * gr, 0.8), 3),
                                           "mask": [{"spot": {"at": [cr, cl], "radius": 0.0022, "soft": 1.0}}]}
            if "lm_lip_lower" in J:
                out["skin:lip_body"] = {"part": part, "_pre": True,
                                        "color": T(melanin=lm * 0.45 * skin.LOWER_LIP["melanin"] * lp["lower"]["melanin"],
                                                   blood=0.8 * skin.LOWER_LIP["blood"] * lp["blood"] * lp["lower"]["blood"],
                                                   epidermis=le + skin.LOWER_LIP["epidermis"], oxygenation=0.72),
                                        "opacity": round(min(0.4 * gr, 1.0), 3),
                                        "mask": [{"spot": {"at": [{"at": "lm_lip_lower", "offset": [0.0, -0.0005, 0.003]}],
                                                           "radius": [[0.012, 0.006, 0.0032]], "soft": 1.0}}, {"zone": {"name": "lip_lower", "grow": 0.6}}]}
        # THE WET SEAM: darker than before and soft, darkest over the middle, thinning to nothing before the corners (a hard
        # even line running out to points read as drawn; mouth_eye_bias)
        out["skin:lip_seam"] = {"part": part, "_pre": True, "color": T(melanin=lm * 2.2, blood=3.0, oxygenation=0.42), "opacity": 0.85,
                                "mask": [{"spot": {"at": [cr, "lm_lip_inner_upper.R", "lm_lip_seam",
                                                          "lm_lip_inner_upper.L", cl],
                                                   "radius": [0.0002, 0.0017, 0.0021, 0.0017, 0.0002], "soft": 1.0, "line": True}}]}
    if hands:
        add("nails", 1.0, color=T(melanin=0.12, blood=2.4, epidermis=0.4), opacity=0.75, roughness=0.22, specular=0.5,
            mask=_z("nails"))

    # 4. roughness: sebum on the T-zone, drier rougher joints, and it is never even. The layers are offsets from the
    # part's OWN base: skin.shading.roughness when set (it was ignored here, so the rough_* layers at opacity .6-.85 laid
    # the oil-derived value over it: Garrett's shading.roughness .42 moved sheen 4.5 -> 4.5, Tess's .55 never showed; r6)
    base_r = float(p["shading"].get("roughness", _roughness(p)))
    if face:
        out["skin:rough_tzone"] = {"part": part, "_pre": True, "roughness": round(float(np.clip(base_r - 0.07 - 0.12 * (p["oil"] - 0.3), 0.18, 0.9)), 3),
                                   "opacity": 0.8, "mask": _z("forehead", "glabella", "nose_bridge", "nose_tip", "nose_wing") +
                                   [{"zone": "chin", "blend": "max", "weight": 0.6}, {"zone": "eyelid", "blend": "max", "weight": 0.8}]}
    if hands or joints_:
        out["skin:rough_joints"] = {"part": part, "_pre": True, "roughness": round(min(base_r + 0.16, 0.95), 3), "opacity": 0.8,
                                    "mask": _z(*((["knuckles"] if hands else []) + joints_))}
    # shading.rough_breakup (1): x the opacity of the cm-scale break-up (rough_patches 5 mm, rough_sheen 11 mm noise). At the
    # 7 mm scene mesh these per-vertex values were averaged away; the 1 mm face (scene_objects.face_refine) shows them as a camouflage
    # of +.12 roughness blotches over the cheek (assembly r67 maps_r_vs_s.png), which skin doesn't have: sebum varies by
    # region (rough_tzone / rough_cheeks), the sub-mm grain is pores. r23: answer "not meant"; lever for the 1 mm face.
    brk = float(p["shading"].get("rough_breakup", 1.0))
    out["skin:rough_patches"] = {"part": part, "_pre": True, "roughness": round(min(base_r + 0.12 + 0.08 * dark, 0.95), 3), "opacity": round(0.8 * brk, 3),
                                 "mask": [{"noise": {"scale": 0.005, "range": [0.38, 0.72], "seed": seed + 21}}]}
    out["skin:rough_fine"] = {"part": part, "_pre": True, "roughness": round(min(base_r + 0.14, 0.95), 3), "opacity": 0.6,
                              "mask": [{"noise": {"scale": 0.0022, "range": [0.42, 0.7], "seed": seed + 23}}]}
    if face:   # the cheeks hold little sheen (the photographs: a soft broad sheen on forehead and nose, matte cheeks)
        out["skin:rough_cheeks"] = {"part": part, "_pre": True, "roughness": round(min(base_r + 0.1, 0.9), 3), "opacity": 0.85,
                                    "mask": _z("cheek", "cheekbone", "cheek_side", "jaw", grow=1.0)}
    out["skin:rough_sheen"] = {"part": part, "_pre": True, "roughness": round(max(base_r - 0.1, 0.15), 3), "opacity": round(0.3 * brk, 3),
                               "mask": [{"noise": {"scale": 0.011, "range": [0.55, 0.85], "seed": seed + 22, "warp": 0.6}}]}

    from . import skin_features_build
    smooth = skin_features_build.build(spec, p, J, out, T, {"face": face, "hands": hands, "arms": arms, "legs": legs, "feet": feet,
                                                      "child": child, "old": old, "thin": thin, "base_r": base_r,
                                                      "fem": p["fem"], "masc": p["masc"]})
    no_pores = [{"mask": s, "blend": "subtract"} for s in smooth]  # scar tissue is smooth

    # last: micro relief (pores, the polygonal net of skin lines, the grain between them), over everything, ink and
    # make-up included: tiling swatches, relief + darker, rougher furrows (cavity: "pores catch no light")
    if det > 0:
        d = det * (1 - 0.45 * child) * (1 + 0.5 * dark)  # dark skin shows its highlight more: the same relief must break it up
        body_k = 1.0 + 0.5 * old
        micro = []
        if face:
            # THE FACE'S MICRORELIEF (projskin; Joe: "lots of big pores, but real skin has a sort of 'cells' look"): the
            # network of fine crossing furrows ("lines" swatch: polygonal plateaus, small pits at the crossings) is the
            # base everywhere on the face, finer on the lids and under the eye, deeper with age; the pores are a
            # second, sparser layer on the nose and central cheeks only (they were round pits everywhere, too big)
            age_k = 1.0 + 0.9 * old
            # (the cells' depth follows detail only up to 1: deeper, the swatch's tiling read as directional hatching /
            # "scales" in blind reviews (Garrett detail 2, a private head 1.6); detail above 1 deepens the pores instead)
            dc = min(d, 1.0)
            micro.append(("cells", "lines", 0.0003 * dc * age_k, _z("face") + [{"zone": "lips", "blend": "subtract"},
                                                                                {"mask": _z("eyelid", "under_eye", grow=1.2), "blend": "subtract"}]))
            micro.append(("cells_fine", "lines_fine", 0.00022 * dc * age_k, _z("eyelid", "under_eye", grow=1.2)))
            # (under a measured stack the pores are the face's visible grain everywhere the photographs show it: forehead,
            # cheeks, nose, chin; a blind review read the stacked face as wax with only the nose and cheeks pored)
            pz = ("nose_tip", "nose_wing", "cheek", "forehead", "chin", "upper_lip", "cheekbone", "temple") if p.get("stack") else ("nose_tip", "nose_wing", "cheek")
            micro.append(("pores", "pores", 0.00013 * d * (0.8 + 0.4 * p["oil"]), _z(*pz, grow=1.0) +
                          [{"zone": "lips", "blend": "subtract"}]))
            micro.append(("lip_lines", "lips", 0.00014 * d * (1 + p["lips"]["dry"]), _z("lips")))
            micro.append(("lines", "lines", 0.00013 * d * body_k, [{"mask": _z("face"), "invert": True}]))
        else:
            micro.append(("lines", "lines", 0.00013 * d * body_k, None))
        if hands or joints_:
            micro.append(("coarse", "coarse", 0.00016 * d * body_k, _z(*((["knuckles"] if hands else []) + joints_), grow=1.25)))
        for name, sw, depth, mask in micro:
            tile = {"swatch": "lines", "size": round(0.45 * 0.016, 5)} if sw == "lines_fine" else {"swatch": sw}   # (lids: cells ~0.2-0.5 mm)
            stack = [{"tile": tile}] + ([{"mask": mask, "blend": "multiply", "vertex": True}] if mask else []) + copy.deepcopy(no_pores)
            out[f"skin:micro_{name}"] = {"part": part, "_detail": True, "height": -round(depth, 7), "color": [0.7, 0.55, 0.5] if name == "pores" else [0.8, 0.66, 0.62], "mix": "multiply",
                                         "opacity": round(min(((0.15 if base_map is not None and not p.get("stack") else min(0.6, 0.3 / max(d, 1e-6)) if p.get("stack") else 0.3) if name == "pores" else 0.45 if name == "lip_lines" else (0.03 if p.get("stack") else 0.22) if name.startswith("cells") else 0.3) * d, 1), 3),   # (stacked: the cells' colour read as hatch strokes) "roughness": round(min(base_r + 0.22, 0.95), 3),
                                         "mask": stack}
        if base_map is not None:  # the face's own relief: baked into the export's unique normal map (not a tiling detail)
            out["skin:micro_map"] = {"part": part, "height": -round(skin.BASE_MAP["depth"] * d ** 0.5, 7), "mask": [base_map("r")] + copy.deepcopy(no_pores)}
            # (no cavity tint of its own: a pores-only colour layer changed nothing visible at face distance, and the
            # tiling pores' tint, 0.65 -> 0.3 here, were the dark specks a blind read called dirt)
    _aperture_keep_out(spec, part, out)
    if p.get("stack") and float(p["stack"].get("base_opacity", 1.0)) > 0:   # (projskin) the colour is the stack of measured maps: our own colour zones and mottle are not laid
        # over it (they painted over the stack's base: a stippled "moustache" above Tess's lip, blotches on her lids)
        # lid_shade stays: it is off unless asked and is the measured lid lever ("eye lid - cheek"); dropping it here made
        # every stacked head's lid_shade a silent no-op (r5: Garrett .5 and Tess .58 moved nothing; 2026-10-16)
        out = {k: v for k, v in out.items() if group_of(k) != "zones" or k.startswith("skin:stack_") or k in skin.AFTER_STACK}
        # ... and it goes AFTER the stack: laid first (zones come first), stack_base (normal mix, opacity 1) painted over it,
        # so r6's live lid_shade still moved nothing (upper lid / cheek .92 -> .92 Tess R, .97 -> .97 Garrett; 2026-10-16)
        for nm in skin.AFTER_STACK:
            if nm in out:
                ls = out.pop(nm)
                ks = list(out)
                last = max((i for i, k in enumerate(ks) if k.startswith("skin:stack_") or k in skin.AFTER_STACK), default=len(ks) - 1)
                out = {**{k: out[k] for k in ks[:last + 1]}, nm: ls, **{k: out[k] for k in ks[last + 1:]}}
        # ... and none of them is "_pre": pre layers are composited per vertex into the base the SHADER starts from, and
        # stack_base (an image layer, normal mix, opacity 1 over its coverage) paints over that base, so a pre layer under
        # the stack shows nowhere, whatever its order (lever check 2026-10-16: lid_shade .58 -> 1.2 moved lid - cheek
        # -6.1 -> -6.2, under_eye_shade 0 -> 1 moved under-eye / cheek 1.09 -> 1.10, brows.shadow 1 -> .35 moved nothing)
        for nm in (*skin.AFTER_STACK, *skin.OVER_STACK):
            if nm in out:
                out[nm].pop("_pre", None)
        # lips.over_stack (opt-in): the lips' own colour laid OVER the stack (it is "_pre", so under a stack stack_base
        # covered it: Tess's lips.melanin 12 changed nothing, her upper lip stayed the stack's, 7 L lighter than the photo;
        # r8 lever check 2026-10-16). Off by default: every stacked head's lips are the measured stack's today.
        if ((spec.get("skin") or {}).get("lips") or {}).get("over_stack"):
            # (r18: and the vermilion's own detail with it, in order: the lower lip's lighter body, the darker band toward
            # the wet line, the wet seam. Under a stack they stayed "_pre" and were covered, so over_stack lips were one flat
            # fill per lip with no parting line: Tess s25's "lipstick" read)
            for nm in ("skin:lips_upper", "skin:lips_lower", "skin:lip_body", "skin:lip_inner", "skin:lip_seam"):
                if nm in out:
                    ly = out.pop(nm); ly.pop("_pre", None); out[nm] = ly
    if p["only"] is not None:  # only some groups; without the shading nothing can be composited into the part's base
        out = {k: v for k, v in out.items() if group_of(k) in p["only"]}
        if "shading" not in p["only"]:
            for v in out.values():
                v.pop("_pre", None)
    return out


def export_recipe(spec: dict, out_dir, stem: str, baked: bool = False) -> dict | None:
    """What an engine needs beside the baked maps to shade this skin: the tiling micro-detail normal maps (written
    into out_dir; the unique maps hold everything down to the texel, the pores live here) and the scattering,
    coat and sheen numbers. Goes into the skin material's extras ("hifipushie_skin") and the export's json."""
    from pathlib import Path
    from . import paint, skin_swatch
    if not spec.get("skin") or not shaded(spec):
        return None
    base = skin_params.part_base(spec)[1]
    details = []
    for name, ly in paint.layers(spec).items():
        if not ly.get("_detail"):
            continue
        tile = next((e["tile"] for e in ly.get("mask") or [] if "tile" in e), None)
        if tile is None:
            continue
        sw, depth = tile["swatch"], abs(float(ly["height"]))
        tag = sw if name[5:] == f"micro_{sw}" else name[11:] if name.startswith("skin:micro_") else name[5:]   # (two layers share "lines": cells, cells_fine)
        f = Path(out_dir) / f"{stem}_skin_{tag}_normal.png"
        skin_swatch.normal_map(sw, depth, f)
        where = {"micro_pores": "nose and central cheeks", "micro_cells": "the face's microrelief network (not lids, under-eye, lips)",
                 "micro_cells_fine": "lids and under the eye (the finer network)", "micro_lip_lines": "the lips", "micro_lines": "the body (everything but the face)",
                 "micro_coarse": "knuckles, elbows, knees"}.get(name[5:], name[5:])
        details.append({"layer": name[5:], "normal": f.name, "period_m": float(tile.get("size", skin_swatch.PERIOD[sw])),
                        "depth_m": round(depth, 7), "cavity_tint": ly.get("color"), "cavity_opacity": ly.get("opacity"),
                        "cavity_roughness": ly.get("roughness"), "where": where, "baked": baked})
    r, sc = base["subsurface_radius"], base["subsurface_scale"]
    return {
        "detail": details,
        **({"detail_baked": "These details are ALREADY baked into the part's normal, roughness and base colour maps at the "
                            "atlas's texel (any glTF viewer shows them). The tiling maps are an optional close-up extra: "
                            "blend their normal only (no cavity tint / roughness: those are in the maps), faded in under "
                            "~0.5 m."} if baked else {}),
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
        **({"blink_multiply": {"file": "<atlas>_blink_multiply.png", "uv": "the atlas' own (as basecolor)",
                               "note": "the lid fold's crease line and the lid's occlusion, kept OUT of basecolor (paint is "
                                       "fixed on the skin: a blink pulls the lid over the eye and they would lie on the closed "
                                       "lid as a dark gash). Shade basecolor x lerp(1, blink_multiply, 1 - eyeBlink) with "
                                       "eyeBlink = the ARKit morph weight (eyeBlinkLeft / Right by the map's side), i.e. a "
                                       "wrinkle map driven by the blink: open eye = the full crease, closed = clean."}}
           if ((spec.get("skin") or {}).get("stack") or {}).get("crease") else {}),
        "tone": tone_params((spec.get("skin") or {}).get("tone")), "base_color_srgb": base["color"],
    }


def reference() -> str:
    """The zones and the description's keys, for the skin_reference tool."""
    from . import skin_features_marks
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
        skin_features_marks.reference(),
        "",
        "TONE: fitzpatrick 1..6 = melanin " + ", ".join(f"{k}: {v}" for k, v in skin.FITZPATRICK.items()) +
        "; albedo of the base tone (sRGB) at blood 0.4: " +
        ", ".join(f"F{k} {''.join(f'{int(round(c * 255)):02x}' for c in tone_rgb({'fitzpatrick': k}))}" for k in range(1, 7)),
        "BUILT-IN ZONE LAYERS (skin.zones: {layer: strength}): " + ", ".join(skin.ZONE_LAYERS),
        "",
        __import__("hifipushie.skin_folds", fromlist=["reference"]).reference(),
    ])
