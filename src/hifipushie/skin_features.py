"""The skin's feature layers (skin.py calls `build` between its colour zones and its micro relief): spots and marks,
wrinkles, hair, scars, tattoos, make-up. Each is a few ordinary paint layers ("skin:<name>").

Every feature takes a number (its amount, 0..1) or an object {"amount", ...its own keys..., "where": [zones]
(replaces its default zones), "mask": [paint mask entries] (multiplied in: confine it any way paint can), "seed"}.

FEATURES (skin.features):
  freckles   {"amount", "size": m (0.0018)}: small tan macules, more melanin, clustered on nose, cheeks, forehead,
             shoulders and forearms; two sizes.
  moles      {"amount", "at": [point, ...] (placed ones: joints / [x, y, z] / {"at", "offset"}), "size": m (0.0025)}:
             a few dark brown nevi, some raised.
  age_spots  amount (default from age x sun): larger, sharper-edged brown patches on temples, cheekbones, backs of
             hands, forearms.
  blemishes  {"amount", "size"}: acne: red papules with a raised, slightly shiny centre, on cheeks, chin, forehead, jaw.
  veins      amount (default from age and thin skin): blue-green branching lines on backs of hands, inner wrists,
             forearms, temples; raised on old hands.
  flush      amount: more blood in cheeks, nose and ears (exertion, cold, embarrassment, rosacea).
  sunburn    amount: red on what faces the sun (forehead, nose, cheekbones, shoulders).
  tan        {"amount", "mask"}: more melanin; give "mask" to leave tan lines (e.g. [{"zone": "upper_arm", "invert": true}]).
WRINKLES (skin.wrinkles; every amount defaults from age, 0 turns one off, > 1 exaggerates; "amount" scales all):
  forehead, glabella (the "11" between the brows), crows_feet, under_eye, nasolabial, marionette, lip_lines (round
  the mouth), neck (rings), crepe (fine cross-hatched skin: cheeks, neck, hands, with age).
HAIR (skin.hair; colours sRGB):
  brows      {"color", "density": 0..1 (0.8), "thickness": 1, "length": m (0.006), "grey": 0..1, "drop": m (0: the
             brow lower, onto the orbital rim), "arch": 1 (its slope: 0 = level), "soft": 0..1 (a soft mass rather
             than hairs one by one)}: hairs as strokes, growing up at the inner end and out along the brow.
  lashes     {"color", "amount": 0..1 (0.7)}: the lash lines darkened (upper more).
  stubble    {"amount", "color", "where", "size": 1 (the dots' size), "shadow": 1 (the under-skin shadow's strength; "shadow_color",
             "shadow_breakup": its noise, 0 = an even field: a dense stubble shadow reads as one grey-brown field),
             "grey": 0..1 (+ "grey_color": a share of white hairs: salt and pepper)}: the beard area: a shadow under the
             skin plus hair dots.
  scalp      {"amount", "color", "hairline": 0..1 (0.5: how far it comes down the forehead)}: a shaved or cropped
             head: the shadow of hair under the scalp's skin plus cut hairs, with a hairline. (Longer hair is geometry:
             groom_hair.)
  body       {"amount", "color"}: fine dark hairs on forearms, shins, chest.
SCARS (skin.scars: a list): {"kind": "cut" | "surgical" | "keloid" | "burn" | "pockmarks", "path": [points] (cut,
  surgical, keloid: along a line) | "at": point + "radius": m | "zone": name (burn, pockmarks, keloid: a patch),
  "width": m, "age": 0 fresh (red, raised) .. 1 old (pale, flat, slightly shiny), "normal": [x, y, z] (surgical: out of
  the skin there, for the stitch marks; default [0, -1, 0])}. Scar tissue has no pores: the micro relief stops on it.
TATTOOS (skin.tattoos: a list): {"image": {a paint image: "file" | "text", "at", "size", "dir", "wrap": "surface" |
  "cylinder", ...}, "age": years (2), "opacity": 0.9, "ink": "#1c2026" (text and alpha-only images)}: ink in the
  dermis: multiplied into the skin under its relief and highlights; with age the lines spread, black turns blue-green
  and colours fade.
"""
from __future__ import annotations

import colorsys
import hashlib
import json

import numpy as np

from .spec import SpecError

FEATURES = ("freckles", "moles", "age_spots", "blemishes", "veins", "flush", "sunburn", "tan")
WRINKLES = ("amount", "forehead", "glabella", "crows_feet", "under_eye", "nasolabial", "marionette", "lip_lines", "neck", "crepe")
HAIR = ("brows", "lashes", "stubble", "scalp", "body")
SCARS = ("cut", "surgical", "keloid", "burn", "pockmarks")
COMMON = {"amount", "where", "mask", "seed"}


def _opt(v, what: str, extra=()) -> dict | None:
    """A feature's value as {"amount", ...} (None when off)."""
    if v is None or v is False:
        return None
    if v is True:
        v = 1.0
    if isinstance(v, (int, float)):
        v = {"amount": float(v)}
    if not isinstance(v, dict):
        raise SpecError(f"skin {what}: a number (its amount) or an object")
    bad = set(v) - COMMON - set(extra)
    if bad:
        raise SpecError(f"skin {what}: unknown keys {sorted(bad)} (have {', '.join(sorted(COMMON | set(extra)))})")
    out = {"amount": 1.0, **v}
    return out if float(out["amount"]) > 0 else None


def _zones(names, grow=1.0) -> list:
    return [{"zone": {"name": n, "grow": grow}, **({"blend": "max"} if i else {})} for i, n in enumerate(names)]


def _where(o: dict, default: list, have: dict) -> list:
    """The feature's zones as one nested mask entry (zones the model has no joints for are left out)."""
    names = o.get("where") or [z for z in default if _has(z, have)]
    return [{"vertex": True, "mask": _zones(names)}] if names else []


BODY_NEED = {"shoulder": "arms", "elbow": "arms", "forearm": "arms", "upper_arm": "arms", "knee": "legs", "foot": "feet",
             "sole": "feet", "chest": "torso", "collarbone": "face"}


def _has(zone: str, have: dict) -> bool:
    stem = zone[:-2] if zone.endswith((".L", ".R")) else zone
    if stem in BODY_NEED:
        return bool(have.get(BODY_NEED[stem]))
    if stem in ("knuckles", "hand", "palm", "back_of_hand", "fingertips", "nails", "wrist_inner"):
        return bool(have.get("hands"))
    return bool(have.get("face"))


def _dots(scale: float, radius: float, share: float, seed: int, soft: float = 0.5) -> list:
    """Mask entries: round dots of `radius` (m), one in `share` of the cells of a `scale` (m) jittered lattice."""
    r = radius / scale
    e = [{"cells": {"scale": scale, "mode": "distance", "range": [round(r, 4), round(r * (1 - soft), 4)], "seed": seed}}]
    if share < 1:
        e.append({"cells": {"scale": scale, "mode": "id", "range": [round(1 - share - 0.02, 4), round(1 - share + 0.02, 4)], "seed": seed}})
    return e


def _lines(scale: float, width: float, dir_, factor: float, seed: int, warp: float = 0.0) -> list:
    """Mask entries: wandering lines `scale` (m) apart: the 0.5 contour of a noise stretched along dir (factor > 1:
    lines run along dir; < 1: sheets across it, e.g. horizontal rings with dir up)."""
    nz = {"scale": scale, "octaves": 2, "seed": seed, "stretch": {"dir": list(dir_), "factor": factor},
          **({"warp": warp} if warp else {})}
    w = float(np.clip(width, 0.005, 0.2))
    return [{"noise": {**nz, "range": [0.5 - w, 0.5 - 0.3 * w]}}, {"noise": {**nz, "range": [0.5 + w, 0.5 + 0.3 * w]}}]


def _hex(c) -> list:
    from .paint import colour
    return [round(float(x), 4) for x in colour(c, "skin hair color")]


def _shade(c, k: float) -> list:
    return [round(float(np.clip(x * k, 0, 1)), 4) for x in c]


def hair_default(tone: dict, age: float) -> list:
    """Hair colour when none is given: dark brown, greying from ~45."""
    g = float(np.clip((age - 55) / 30, 0, 1))
    base = np.array([0.13, 0.085, 0.06]) * (1.0 - 0.3 * tone["melanin"])
    return [round(float(x), 4) for x in base + g * (np.array([0.5, 0.5, 0.5]) - base)]


def build(spec: dict, p: dict, J: dict, out: dict, T, ctx: dict) -> list:
    """Adds the feature layers to `out`. Broad, soft layers are "_pre" (composited per vertex into the skin's base,
    paint.precomposite); what needs detail finer than the mesh (hairs, dots, lines, ink) stays a layer of the node
    program, built from tiling swatches, images and spots only: a renderer's shader has room for a few dozen such
    layers, and none for a hundred procedural ones. Returns the masks of skin without pores (scar tissue)."""
    part, t, seed, age = p["part"], p["tone"], p["seed"], p["age"]
    old, child, thin, base_r = ctx["old"], ctx["child"], ctx["thin"], ctx["base_r"]
    dark = t["melanin"]
    ctx = {**ctx, "torso": "chest" in J}
    ctx["smooth"] = []
    from . import paint as _paint
    ctx["eyes"] = all(e in (_paint._expanded(spec).get("blobs") or {}) for e in ("eye.L", "eye.R"))  # eyeballs: lid margins
    from . import lashes as _lashes
    ctx["lash_geometry"] = ctx["eyes"] and bool(_lashes.wanted(spec))  # lash ribbons (lashes.py) over the painted lines
    f0 = p["makeup"].get("foundation")
    cover = float(np.clip(f0 if isinstance(f0, (int, float)) else (f0 or {}).get("amount", 1.0 if f0 else 0.0), 0, 1)) if f0 else 0.0
    ctx["show"] = 1.0 - 0.75 * cover  # how much of the skin's own marks shows through foundation

    def layer(name, extra_mask=None, pre=False, **ly):
        if extra_mask:
            ly["mask"] = list(ly.get("mask") or []) + [{"mask": extra_mask}]
        if "opacity" in ly:
            ly["opacity"] = round(float(np.clip(ly["opacity"], 0, 1)), 4)
        if pre:
            ly.pop("height", None)
            ly["_pre"] = True
        out[f"skin:{name}"] = {"part": part, **ly}

    f = p["features"]
    bad = set(f) - set(FEATURES)
    if bad:
        raise SpecError(f"skin features: unknown {sorted(bad)} (have {', '.join(FEATURES)})")
    show = ctx["show"]

    # ---- broad colour: tan, sunburn, flush
    o = _opt(f.get("tan"), "features.tan")
    if o:
        bare = [z for z in ("palm", "sole", "lips") if _has(z, ctx)]  # what never tans
        layer("tan", o.get("mask"), pre=True, color=T(melanin=1 + 1.0 * o["amount"], blood=1.1), opacity=0.8,
              mask=(_where(o, [], ctx) or [{"levels": [0.0, 1.0]}]) + [{"mask": _zones(bare), "blend": "subtract"}] if bare else _where(o, [], ctx))
    o = _opt(f.get("sunburn"), "features.sunburn")
    if o:
        w = _where(o, ["forehead", "nose", "cheekbone", "shoulder", "collarbone"], ctx)
        layer("sunburn", o.get("mask"), pre=True, color=T(blood=4.5, oxygenation=0.85), opacity=0.6 * o["amount"],
              mask=w + [{"noise": {"scale": 0.03, "range": [0.2, 0.75], "seed": seed + 40}, "weight": 0.5}])
    o = _opt(f.get("flush"), "features.flush")
    if o:
        layer("flush", o.get("mask"), pre=True, color=T(blood=4.0, oxygenation=0.85), opacity=0.55 * o["amount"],
              mask=_where(o, ["cheek", "cheekbone", "nose_tip", "ear", "chin"], ctx) +
              [{"noise": {"scale": 0.012, "range": [0.25, 0.8], "seed": seed + 41, "warp": 0.8}, "weight": 0.6}])

    # ---- pigment spots
    o = _opt(f.get("freckles"), "features.freckles", ("size",))
    if o:
        a = float(o["amount"])
        k = float(o.get("size", 0.0018)) / 0.0018
        w = _where(o, ["nose", "cheek", "cheekbone", "forehead", "upper_lip", "chin", "shoulder", "forearm", "collarbone"], ctx)
        lo = float(np.clip(0.42 - 0.3 * min(a, 1.2), 0.04, 0.6))  # more of the swatch's faint macules show as it rises
        layer("freckles", o.get("mask"), color=T(melanin=2.6 + 1.6 * (1 - dark), blood=1.3), opacity=min(0.4 + 0.3 * a, 0.75) * show,
              mask=[{"tile": {"swatch": "freckles", "size": round(0.042 * k, 5), "range": [round(lo, 3), round(lo + 0.55, 3)], "vary": False}}] + w)
    o = _opt(f.get("moles"), "features.moles", ("at", "size"))
    if o:
        sz = float(o.get("size", 0.0025))
        sd = seed + int(o.get("seed", 0))
        stacks = []
        if not o.get("at") or (isinstance(f.get("moles"), dict) and "amount" in f["moles"]):
            hi = float(np.clip(0.955 - 0.05 * o["amount"], 0.8, 0.96))  # only the swatch's few strongest marks
            stacks.append([{"tile": {"swatch": "freckles", "size": round(0.06 * sz / 0.0016, 4), "range": [round(hi, 3), round(hi + 0.04, 3)],
                                     "vary": False, "rotate": True}}] + (_where(o, [], ctx)))
        if o.get("at"):
            pts = o["at"] if isinstance(o["at"], list) and not (len(o["at"]) == 3 and all(isinstance(x, (int, float)) for x in o["at"])) else [o["at"]]
            stacks.append([{"spot": {"at": pts, "radius": 0.5 * sz, "soft": 0.35}}])
        m = [{"mask": st, **({"blend": "max"} if i else {})} for i, st in enumerate(stacks)]
        layer("moles", o.get("mask"), color=T(melanin=9.0, blood=1.3), opacity=0.92, roughness=min(base_r + 0.08, 0.9), height=0.00022, mask=m)
    spots = f.get("age_spots", max(0.0, old * (0.35 + 1.2 * p["sun"])))
    o = _opt(spots, "features.age_spots", ("size",))
    if o:
        sz = float(o.get("size", 0.006))
        w = _where(o, ["temple", "cheekbone", "cheek_side", "back_of_hand", "forearm"], ctx) + \
            [{"vertex": True, "mask": _zones(["forehead", "scalp"]), "blend": "max", "weight": 0.35}] if ctx["face"] else _where(o, ["back_of_hand", "forearm"], ctx)
        a = float(np.clip(o["amount"], 0, 1.5))
        layer("age_spots", o.get("mask"), pre=True, color=T(melanin=1.6 + 2.9 * (1 - dark), blood=0.9), opacity=0.55 * show * (1 - 0.4 * dark),
              mask=[{"noise": {"scale": sz, "range": [0.74 - 0.14 * a, 0.78 - 0.14 * a], "seed": seed + 57, "octaves": 2, "warp": 0.5}}] + w)
        layer("age_spots_small", o.get("mask"), color=T(melanin=1.8 + 1.8 * (1 - dark), blood=0.9), opacity=0.5 * show * (1 - 0.4 * dark),
              mask=[{"tile": {"swatch": "freckles", "size": 0.11, "range": [0.62 - 0.2 * min(a, 1), 0.8 - 0.2 * min(a, 1)], "vary": False}}] + w)
    o = _opt(f.get("blemishes"), "features.blemishes", ("size",))
    if o:
        sz = float(o.get("size", 0.003))
        sd = seed + int(o.get("seed", 0))
        a = float(o["amount"])
        w = _where(o, ["cheek", "cheek_side", "chin", "forehead", "jaw", "nose_wing"], ctx)
        # the freckle swatch's marks at a larger size, another way up: the halo is a mark's whole extent, the bump its core
        size = round(0.06 * sz / 0.0013, 4)
        lo = float(np.clip(0.75 - 0.5 * min(a, 1.2), 0.1, 0.8))
        tile = {"swatch": "freckles", "size": size, "vary": False, "rotate": True}
        layer("blemish_halo", o.get("mask"), color=T(blood=5.5, oxygenation=0.8), opacity=0.75 * (0.5 + 0.5 * show),
              mask=[{"tile": {**tile, "range": [round(lo, 3), round(lo + 0.25, 3)]}}] + w)
        layer("blemish_bump", o.get("mask"), color=T(blood=6.5, melanin=1.15), opacity=0.6 * (0.5 + 0.5 * show), roughness=max(base_r - 0.14, 0.2),
              height=0.0004, mask=[{"tile": {**tile, "range": [round(lo + 0.3, 3), round(lo + 0.5, 3)]}}] + w)

    # ---- veins
    v_def = max(0.0, 0.25 * thin - 0.05 + 0.6 * old) * (1 - 0.6 * dark)
    o = _opt(f.get("veins", v_def), "features.veins")
    if o and o["amount"] > 0.05:
        a = float(o["amount"])
        groups = []
        if ctx["hands"] and ctx["arms"]:
            for sx in (".L", ".R"):
                d = J[f"wrist{sx}"] - J[f"elbow{sx}"]
                d = (d / max(np.linalg.norm(d), 1e-9)).round(3).tolist()
                groups.append((sx, d, [f"back_of_hand{sx}", f"wrist_inner{sx}", f"forearm{sx}"]))
        if ctx["face"] and (a > 0.5 or old > 0.3):
            groups.append(("", [0.3, 0.2, 1.0], ["temple"]))
        for i, (sx, d, zs) in enumerate(groups):
            zs = o.get("where") or zs
            rot = abs(d[2]) > 0.6  # the swatch's lines run across it: turned to run along the limb
            m = [{"tile": {"swatch": "wrinkles", "size": 0.075, "rotate": bool(rot), "range": [0.25, 0.8], "vary": False}}, {"vertex": True, "mask": _zones(zs)}]
            layer(f"veins{sx.replace('.', '_')}", o.get("mask"), color=[0.72, 0.84, 0.86], mix="multiply", opacity=min(0.5 * a, 0.9) * (0.6 if not sx else 1) * show,
                  mask=m, **({"height": round(0.0005 * old * min(a, 1.5), 6)} if sx and old > 0.2 else {}))

    _eyes(spec, p, J, out, layer, T, ctx)
    _wrinkles(p, J, layer, T, ctx)
    _hair(p, J, layer, T, ctx)
    _scars(spec, p, J, layer, T, ctx)
    _tattoos(spec, p, layer, ctx)
    from . import skin_makeup
    skin_makeup.build(spec, p, J, layer, T, ctx)
    return ctx["smooth"]


EYE_KEYS = ("iris", "iris_size", "pupil", "veins", "sclera", "tear", "waterline", "limbal", "limbal_width",
            "iris_contrast", "gloss", "occlusion")


def eye_base(spec: dict) -> tuple[str, dict] | None:
    """(the eyes part, its base channels) when skin.eyes paints them: the tear film as a clear coat over the matte
    iris and sclera (coat 1, roughness 0.03 x (2 - gloss); IOR 1.5 ~ the cornea's 1.376 and the film's 1.337 under
    Blender's coat): the sharp catchlight a photographed eye has. Values the part's own definition gives win."""
    e = (spec.get("skin") or {}).get("eyes")
    b = spec.get("base") or {}
    if e is False or not spec.get("skin") or not b.get("eyes"):
        return None
    e = e if isinstance(e, dict) else {}
    g = float(e.get("gloss", 1.0))
    if g <= 0:
        return None
    return b["eyes"], {"coat": round(min(g, 1.0), 3), "coat_roughness": round(0.03 * (2 - min(g, 1.0)), 4)}


def _eyes(spec, p, J, out, layer, T, ctx) -> None:
    """EYES (skin.eyes; on by default where the base has eyeballs; false turns it off and leaves the model's own eye
    paint): the eyeball is a painted picture laid on its front (skin_swatch.eye_image: an iris of radial fibres, a
    collarette, a limbal ring, a soft pupil; a sclera pinker toward its edge with fine vessels), under a wet film;
    shadowed where the lids lie on it; on the skin, the pink wet caruncle at the inner corner and the waterline of the
    lower lid. Lashes are geometry (base.lashes, lashes.py) over the lid margins darkened (skin.hair.lashes).
    {"iris": colour, "iris_size": m (the visible iris' diameter: adults 11-12.5 mm, 11.7 on average), "pupil": 0..1
    of the iris' radius (0.36; bright daylight 0.2-0.3), "veins": 0..1, "sclera": colour, "limbal": 0..1 (0.72: the
    dark ring at the iris' edge, darker and wider in the young), "limbal_width": share of the radius (0.2),
    "iris_contrast": the fibres' contrast (1), "gloss": 0..1 (1: the tear film, a clear coat over a matte iris and
    sclera: the sharp catchlight on the cornea), "occlusion": 0..1 (1: the lids' shadow on the ball, all round the
    lid contact and deepest under the upper lid; MetaHuman's eye-occlusion shell as paint), "tear": 0..1 (the
    meniscus: the bright wet line where the lower lid meets the ball), "waterline": 0..1}."""
    e = spec.get("skin", {}).get("eyes")
    if e is False or not ctx["eyes"] or "eye_front.L" not in J:
        return
    e = e if isinstance(e, dict) else {}
    bad = set(e) - set(EYE_KEYS)
    if bad:
        raise SpecError(f"skin eyes: unknown keys {sorted(bad)} (have {', '.join(EYE_KEYS)})")
    from . import paint as _paint
    from . import skin_swatch
    from .skin import interocular
    io = interocular(J)
    part = (_paint._expanded(spec)["blobs"]["eye.L"]).get("part", "body")
    iris = _hex(e.get("iris", "#5a3a1e"))
    old = ctx["old"]
    scl = _hex(e["sclera"]) if "sclera" in e else [round(x, 4) for x in (0.92 - 0.05 * old, 0.89 - 0.06 * old, 0.85 - 0.09 * old)]
    veins = float(e.get("veins", 0.4 + 0.4 * old))
    span = 2.1
    path = skin_swatch.eye_image(iris, float(e.get("pupil", 0.36)), veins, tuple(scl), p["seed"], span,
                                 limbal=float(e.get("limbal", 0.72)), contrast=float(e.get("iris_contrast", 1.0)),
                                 limbal_width=float(e.get("limbal_width", 0.2)))
    gloss = float(e.get("gloss", 1.0))
    occ = float(e.get("occlusion", 1.0))
    for sd in (".L", ".R"):
        c, f = J[f"eye{sd}"], J[f"eye_front{sd}"]
        r = float(np.linalg.norm(f - c))
        d = (f - c) / max(r, 1e-9)
        size = float(e.get("iris_size", 0.0118 * r / 0.0123)) * span
        nm = sd.replace(".", "_")
        out[f"skin:eye{nm}"] = {"part": part, "color": "image",
                                # under the film (the part's coat, eye_base) the iris and sclera are matte; without a
                                # film the old glassy surface
                                "roughness": round(0.04 + 0.36 * min(gloss, 1.0), 3), "specular": 0.6 - 0.2 * min(gloss, 1.0),
                                "image": {"file": str(path), "at": [round(float(x), 5) for x in f], "dir": [round(float(x), 4) for x in d],
                                          "size": [round(size, 5), round(size, 5)], "depth": round(1.2 * r, 5), "facing": 0.05}}
        # the lids' shadow on the ball (an eye-occlusion shell's job in a game head): deepest under the upper lid,
        # and a narrow soft band all round where the lids lie on the ball (the corners darkest)
        if occ > 0:
            out[f"skin:eye_shade{nm}"] = {"part": part, "color": [0.55, 0.5, 0.5], "mix": "multiply",
                                          "opacity": round(min(0.55 * occ, 1.0), 3),
                                          "mask": [{"axis": {"dir": [0, 0, 1], "at": f"eye{sd}", "from": round(0.1 * r, 5), "to": round(0.55 * r, 5)}},
                                                   {"spot": {"at": f"eye{sd}", "radius": round(1.6 * r, 5), "soft": 0.2}}]}
            out[f"skin:eye_occlusion{nm}"] = {"part": part, "color": [0.42, 0.36, 0.35], "mix": "multiply",
                                              "opacity": round(min(0.6 * occ, 1.0), 3),
                                              "mask": [{"near": ["base"], "within": round(0.02 * r, 5), "soft": round(0.09 * r, 5)}]}
        # the tear line: the strip of tear film standing where the lower lid meets the ball, a thin bright wet line
        if float(e.get("tear", 1.0)) > 0:
            out[f"skin:eye_tear{nm}"] = {"part": part, "color": [0.96, 0.95, 0.94], "opacity": round(0.4 * float(e.get("tear", 1.0)), 3),
                                         "roughness": 0.02, "specular": 1.0,
                                         "mask": [{"near": ["base"], "within": round(0.015 * r, 5), "soft": round(0.035 * r, 5)},
                                                  {"axis": {"dir": [0, 0, -1], "at": f"eye{sd}", "from": round(0.05 * r, 5), "to": round(0.2 * r, 5)}}]}
    # on the skin: the caruncle (the pink, wet corner by the nose) and the lower lid's waterline
    pts = [{"at": f"lm_eye_inner{sd}", "offset": [round(sx * 0.012 * io, 5), round(-0.02 * io, 5), 0.0]} for sd, sx in ((".L", 1), (".R", -1))]
    layer("caruncle", pre=True, color=T(blood=5.0, melanin=0.7), opacity=0.7, roughness=0.18,
          mask=[{"spot": {"at": pts, "radius": round(0.036 * io, 5), "soft": 0.6}}])
    if float(e.get("waterline", 1.0)) > 0:   # 0..1 (1): the pink wet rim; on a lid whose rim faces the camera it reads as lid
        layer("waterline", pre=True, color=T(blood=3.5, melanin=0.6), opacity=round(0.5 * float(e.get("waterline", 1.0)), 3),
              roughness=0.15, mask=_zones(["lash_lower"], 0.7))


def _wrinkles(p, J, layer, T, ctx) -> None:
    w = p["wrinkles"]
    bad = set(w) - set(WRINKLES)
    if bad:
        raise SpecError(f"skin wrinkles: unknown {sorted(bad)} (have {', '.join(WRINKLES)})")
    if not ctx["face"]:
        return
    from .skin import _age_curve, interocular
    age, det = p["age"], p["detail"]
    k_all = float(w.get("amount", 1.0)) * det
    io = interocular(J)
    base_r = ctx["base_r"]
    dflt = {"forehead": _age_curve(age, 26, 72), "glabella": _age_curve(age, 36, 75), "crows_feet": _age_curve(age, 28, 70),
            "under_eye": _age_curve(age, 30, 75), "nasolabial": 0.12 + 0.88 * _age_curve(age, 24, 80),
            "marionette": _age_curve(age, 42, 82), "lip_lines": _age_curve(age, 48, 85), "neck": 0.1 + 0.9 * _age_curve(age, 35, 80),
            "crepe": _age_curve(age, 50, 88)}
    amt = {k: float(w.get(k, d)) * k_all for k, d in dflt.items()}
    crease = [0.7, 0.58, 0.55]  # multiplied in: a crease is darker and a little redder (shadow + thin skin)

    def groove(name, a, depth, mask, tint=0.5):
        if a <= 0.02:
            return
        layer(f"wrinkle_{name}", height=-round(depth * min(a, 2.0), 7), color=crease, mix="multiply", opacity=min(tint * a, 0.8),
              roughness=min(base_r + 0.1, 0.95), mask=mask)

    def pt(j, off):
        return {"at": j, "offset": [round(float(x) * io, 5) for x in off]}

    def rays(lines, radius):
        """Lines as tapered spots: [(joint, start offset, end offset)] in interocular units, both sides mirrored."""
        stack = []
        for j, a0, a1 in lines:
            for sd, sx in ((".L", 1), (".R", -1)) if j.endswith(".L") else (("", 1),):
                jj = j[:-2] + sd if sd else j
                mid = [(a0[i] + a1[i]) / 2 for i in range(3)]
                P = [pt(jj, [sx * q[0], q[1], q[2]]) for q in (a0, mid, a1)]
                stack.append({"spot": {"at": P, "radius": [round(radius * io * k, 6) for k in (0.9, 1.0, 0.35)], "soft": 0.9, "line": True},
                              **({"blend": "max"} if stack else {})})
        return stack

    # the lines of expression, each a tapered groove, in one layer: every group's strength scales its own mask
    groups = [
        ("glabella", 1.0, rays([("lm_brow_inner.L", (-0.035, -0.01, 0.09), (-0.015, -0.01, -0.09))], 0.02)),
        ("crows_feet_rays", 0.7, rays([("lm_eye_outer.L", (0.06, 0.03, 0.01), (0.34, 0.22, 0.14)), ("lm_eye_outer.L", (0.07, 0.03, -0.02), (0.38, 0.25, -0.02)),
                                  ("lm_eye_outer.L", (0.06, 0.03, -0.05), (0.33, 0.22, -0.18)), ("lm_eye_outer.L", (0.05, 0.03, -0.09), (0.24, 0.16, -0.3))], 0.014)),
        ("under_eye_rays", 0.65, rays([("lm_lid_lower.L", (-0.22, 0.02, -0.07), (0.24, 0.06, -0.11)), ("lm_lid_lower.L", (-0.2, 0.02, -0.15), (0.28, 0.08, -0.2)),
                                  ("lm_lid_lower.L", (-0.12, 0.01, -0.24), (0.3, 0.1, -0.3))], 0.014)),
        ("nasolabial", 1.0, _zones(["nasolabial"], 1.45)), ("marionette", 0.9, _zones(["marionette"], 1.4))]
    amt["crows_feet_rays"], amt["under_eye_rays"] = 0.5 * amt["crows_feet"], 0.4 * amt["under_eye"]
    for nm, zs, size, rot in (("crows_feet", ["crows_feet"], 0.022, False), ("under_eye", ["under_eye"], 0.026, False)):
        a = amt[nm]
        if a > 0.02:  # a fan of fine creases of uneven depth, under the few drawn ones
            groove(nm + "_fine", a, 0.0004, [{"tile": {"swatch": "wrinkles", "size": size, "rotate": rot, "range": [0.5 - 0.42 * min(a, 1), 1.0],
                                                       "vary": False}}, {"vertex": True, "mask": _zones(zs, 1.1)}], 0.2)
    for lname, members in (("folds", ("glabella", "nasolabial", "marionette")), ("crows_feet", ("crows_feet_rays",)), ("under_eye", ("under_eye_rays",))):
        stack = []
        for name, k, m in groups:
            a = float(np.clip(amt[name] * k, 0, 1.6))
            if name not in members or a <= 0.03:
                continue
            stack.append({"mask": m + [{"levels": [0.0, round(1.6 / a, 3)]}], **({"blend": "max"} if stack else {})})
        if stack:  # (one mask of all ~20 tapered lines ran Cycles out of stack under the bump)
            layer(f"wrinkle_{lname}", height=-0.00065, color=crease, mix="multiply", opacity=0.75, roughness=min(base_r + 0.1, 0.95), mask=stack)
    # fields of lines: a tiling swatch of wandering lines, laid across (forehead, neck) or turned (above the lip)
    a = amt["forehead"]
    if a > 0.02:
        groove("forehead", a, 0.0011, [{"tile": {"swatch": "wrinkles", "size": 0.055, "range": [0.42 - 0.34 * min(a, 1), 1.0], "vary": False}},
                                        {"vertex": True, "mask": _zones(["forehead"], 0.85)}], 0.08)
    a = amt["lip_lines"]
    if a > 0.02:
        groove("lip_lines", a, 0.00022, [{"tile": {"swatch": "wrinkles", "size": 0.02, "rotate": True, "range": [0.55 - 0.45 * min(a, 1), 1.0], "vary": False}},
                                         {"vertex": True, "mask": _zones(["upper_lip", "soul_patch"], 0.95)}, {"zone": "lips", "blend": "subtract"}], 0.35)
    a = amt["neck"]
    if a > 0.02:
        groove("neck", a, 0.0005, [{"tile": {"swatch": "wrinkles", "size": 0.1, "range": [0.5 - 0.42 * min(a, 1), 1.0], "vary": False}}, {"vertex": True, "mask": _zones(["neck"], 0.9)}], 0.2)
    a = amt["crepe"]
    if a > 0.02:  # old skin: the primary lines deepen into a visible cross-hatch, the fine ones go
        # (relief first, hardly any tint: at bust distance crepe is a change of sheen, not drawn lines)
        zs = ["cheek", "cheek_side", "under_eye", "neck", "upper_lip", "jaw"] + \
             (["back_of_hand", "forearm"] if ctx["hands"] and ctx["arms"] else [])
        groove("crepe", a, 0.00016, [{"tile": {"swatch": "coarse", "size": 0.024, "range": [0.12, 1.0]}}, {"vertex": True, "mask": _zones(zs, 1.1)}], 0.1)
        groove("cheek_lines", a, 0.00026, [{"tile": {"swatch": "wrinkles", "size": 0.04, "rotate": True, "range": [0.35, 1.0], "vary": False}},
                                          {"vertex": True, "mask": _zones(["cheek", "cheek_side", "jaw"], 1.0)}], 0.1)


def _hair(p, J, layer, T, ctx) -> None:
    h = p["hair"]
    bad = set(h) - set(HAIR)
    if bad:
        raise SpecError(f"skin hair: unknown {sorted(bad)} (have {', '.join(HAIR)})")
    from .skin import interocular
    from . import skin_swatch
    t, age, seed = p["tone"], p["age"], p["seed"]
    base_r = ctx["base_r"]
    dflt = hair_default(t, age)
    if ctx["face"]:
        io = interocular(J)
        o = _opt(h.get("brows", 1.0), "hair.brows", ("color", "density", "thickness", "length", "grey", "drop", "soft", "arch"))
        if o:
            col = _hex(o["color"]) if "color" in o else dflt
            g = float(o.get("grey", 0.0))
            col = [round(c + g * (0.55 - c), 4) for c in col]
            fem, masc = ctx.get("fem", 0.0), ctx.get("masc", 0.0)
            dens = float(np.clip(o.get("density", 0.8 - 0.12 * fem + 0.1 * masc) * o["amount"], 0.05, 1.6))
            thick = float(o.get("thickness", 1.0 - 0.32 * fem + 0.12 * masc)) * (1 - 0.2 * ctx["child"])
            # the brow is a drawn picture of hairs (skin_swatch.brow_image), laid from the brow's landmarks
            a_, m_, b_ = J["lm_brow_inner.L"], J["lm_brow_mid.L"], J["lm_brow_outer.L"]
            span = float(np.linalg.norm(b_ - a_))
            width = 1.22 * span
            path, (wmm, hmm) = skin_swatch.brow_image(dens, thick, float(o.get("length", 0.006)) * 1000, width * 1000, seed)
            c = 0.5 * (a_ + b_)
            c[2] = (a_[2] + 2 * m_[2] + b_[2]) / 4 - 0.02 * io
            c[1] = m_[1]
            c[2] -= float(o.get("drop", 0.0))   # a heavy brow sits on the orbital rim, its lower edge at the lid's fold
            d = np.array([0.42, -1.0, 0.12])
            d /= np.linalg.norm(d)
            slope = float(np.degrees(np.arctan2(b_[2] - a_[2], np.linalg.norm((b_ - a_)[:2])))) * float(o.get("arch", 1.0))
            soft = float(o.get("soft", 0.0))    # 0..1: hairs read less one by one (fine, greying brows: a soft mass)
            img = {"file": str(path), "at": [round(float(x), 5) for x in c], "dir": [round(float(x), 4) for x in d],
                   "size": [round(width, 5), round(width * hmm / wmm, 5)], "rotate": round(slope, 2), "depth": 0.03,
                   "mirror": True, "mirror_image": True, "channel": "alpha"}  # (unmirrored, the other brow's hairs ran
            # toward the nose: "the left eyebrow is backwards")
            layer("brow_shadow", pre=True, color=_shade(col, 1.6) if sum(col) < 0.6 else col,
                  opacity=min(0.3 * min(dens, 1) + 0.06 + 0.45 * soft, 0.9), mask=_zones(["brow"], 0.9 * thick))
            layer("brow_hairs", color=col, opacity=round(0.95 * (1 - 0.45 * soft), 3), roughness=0.42, specular=0.45, height=0.00012, image=img)
        o = _opt(h.get("lashes", 0.7 if ctx["eyes"] else None), "hair.lashes", ("color",))
        if o:
            col = _hex(o["color"]) if "color" in o else _shade(dflt, 0.45)
            layer("lashes", color=col, opacity=0.9 * min(o["amount"] * (1 + 0.45 * ctx.get("fem", 0.0)) + 0.2, 1), roughness=0.4,
                  mask=_zones(["lash_upper"]) + [{"zone": "lash_lower", "blend": "max", "weight": 0.5}])
            if ctx.get("lash_geometry"):  # with lash geometry: the dense roots' tone along the margin (a tightline: what
                # makes a photographed upper lash line a dark band, not a fringe of separate hairs)
                layer("lash_roots", color=_shade(col, 0.45), mix="multiply", opacity=round(min(0.75 * o["amount"], 0.9), 3),
                      roughness=0.45, mask=_zones(["lash_upper"], 1.15) + [{"zone": {"name": "lash_lower", "grow": 1.1},
                                                                         "blend": "max", "weight": 0.45}])
        o = _opt(h.get("stubble"), "hair.stubble", ("color", "length", "size", "shadow", "shadow_color", "shadow_breakup", "grey", "grey_color"))
        if o:
            a = float(o["amount"])
            col = _hex(o["color"]) if "color" in o else dflt
            zs = o.get("where") or ["beard"]
            # where the beard grows: full on chin, lip and jaw, thinning up the cheek, none on the lips
            area = [{"vertex": True, "mask": _zones(zs)}, {"zone": "lips", "blend": "subtract"}]
            # hair under the skin: on light skin a cool grey-blue cast, on dark skin just darker
            cast = [round(float(c), 4) for c in (np.array(T(grey=0.75, melanin=1.0)) * (0.55 + 0.25 * t["melanin"]) + 0.2 * np.array(col))]
            sz_, shd, gr = float(o.get("size", 1.0)), float(o.get("shadow", 1.0)), float(o.get("grey", 0.0))
            cast = _hex(o["shadow_color"]) if "shadow_color" in o else cast
            layer("stubble_shadow", o.get("mask"), pre=True, color=cast, opacity=round(min(0.42 * min(a, 1.2) * shd, 0.95), 3),
                  mask=area + [{"noise": {"scale": 0.012, "range": [0.15, 0.6], "seed": seed + 100},
                                "weight": float(o.get("shadow_breakup", 0.45 if "shadow" not in o else 0.2))}])  # (breakup: 0 = an even field)
            layer("stubble", o.get("mask"), color=col, opacity=0.9 * min(0.5 + 0.5 * a, 1), roughness=min(base_r + 0.12, 0.9),
                  height=round(0.00007 * (1 + float(o.get("length", 0.0)) / 0.001), 7),
                  mask=[{"tile": {"swatch": "stubble", **({"size": round(0.012 * sz_, 5)} if sz_ != 1.0 else {}),
                                  "range": [round(0.45 - 0.35 * min(a, 1), 3), round(0.75 - 0.35 * min(a, 1), 3)]}}, {"mask": area}])
            if gr > 0:   # salt and pepper: a share of the hairs white (their own dots, another size so they never coincide)
                layer("stubble_grey", o.get("mask"), color=_hex(o.get("grey_color", "#cfcbc4")), opacity=round(0.9 * min(gr, 1.0), 3),
                      roughness=min(base_r + 0.05, 0.9), height=round(0.00007 * (1 + float(o.get("length", 0.0)) / 0.001), 7),
                      mask=[{"tile": {"swatch": "stubble", "size": round(0.012 * sz_ * 1.37, 5), "vary": False,
                                      "range": [round(0.45 - 0.35 * min(gr, 1), 3), round(0.75 - 0.35 * min(gr, 1), 3)]}}, {"mask": area}])
    o = _opt(h.get("scalp"), "hair.scalp", ("color", "hairline")) if ctx["face"] and "head" in J else None
    if o:
        from .skin import interocular
        io = interocular(J)
        a = float(o["amount"])
        col = _hex(o["color"]) if "color" in o else dflt
        hl = float(o.get("hairline", 0.5))
        # the hair-bearing scalp: the cranium behind a hairline that crosses the forehead and drops in front of the ears
        hd = J["head"]
        # one ellipsoid bigger than the skull (the head joint sits at brow height, the cranium ~1.5 interoculars
        # round it): where it leaves the skull is the hairline (~35 deg up the forehead at 0.5), the nape's edge and
        # the line over the ears; two side spots bring it down in front of and behind each ear.
        cy = round((0.8 + 0.6 * (0.5 - hl)) * io, 5)
        top = [{"at": "head", "offset": [0, cy, round(1.1 * io, 5)]}]
        sides = [{"at": "head", "offset": [round(sx * 1.1 * io, 5), round(0.3 * io, 5), round(-0.05 * io, 5)]} for sx in (1, -1)]
        area = [{"spot": {"at": top + sides, "radius": [[round(1.9 * io, 5), round(2.2 * io, 5), round(2.1 * io, 5)]] +
                          [[round(0.5 * io, 5), round(0.75 * io, 5), round(0.9 * io, 5)]] * 2, "soft": 0.06}},
                {"vertex": True, "mask": _zones(["ear"], 0.9), "blend": "subtract"},
                {"breakup": {"amount": 0.12, "scale": 0.006, "sharpness": 0.5, "seed": seed + 105}}]
        cast = [round(float(c), 4) for c in (0.45 * np.array(T(grey=0.7)) * (0.5 + 0.25 * t["melanin"]) + 0.55 * np.array(col))]  # cropped hair is mostly its own colour
        # matt: cut hair scatters, it doesn't shine like the oiled skin of a bald head (left glossy it read as a grey cap)
        layer("scalp_shadow", o.get("mask"), pre=True, color=cast, opacity=min(0.75 * a, 0.9), roughness=0.85, specular=0.12, mask=area)
        layer("scalp_stubble", o.get("mask"), color=col, opacity=0.9 * min(0.5 + 0.5 * a, 1), roughness=min(base_r + 0.15, 0.9), height=0.00008,
              mask=[{"tile": {"swatch": "stubble", "size": 0.009, "range": [round(0.4 - 0.32 * min(a, 1), 3), round(0.7 - 0.32 * min(a, 1), 3)]}},
                    {"vertex": True, "mask": area}])
    o = _opt(h.get("body"), "hair.body", ("color",))
    if o:
        col = _hex(o["color"]) if "color" in o else dflt
        zs = o.get("where") or [z for z in ("forearm", "chest", "back_of_hand") if _has(z, ctx)]
        if zs:
            rot = False
            if ctx["arms"] and any(z.startswith("forearm") for z in zs):
                d = J["wrist.L"] - J["elbow.L"]
                rot = abs(d[2]) < 0.6 * np.linalg.norm(d)  # hairs lie along the limb
            lo = 0.55 - 0.35 * min(o["amount"], 1.2)
            layer("body_hair", o.get("mask"), color=col, opacity=0.75,
                  mask=[{"tile": {"swatch": "hairs", "rotate": bool(rot), "range": [round(lo, 3), round(lo + 0.35, 3)], "vary": False}}, {"vertex": True, "mask": _zones(zs)}])


def _points(v, what):
    ok = isinstance(v, list) and len(v) >= 2 and not all(isinstance(x, (int, float)) for x in v)
    if not ok:
        raise SpecError(f"{what}: \"path\" is a list of 2+ points (joint | [x, y, z] | {{\"at\": joint, \"offset\"}})")
    return v


def _scars(spec, p, J, layer, T, ctx) -> None:
    from . import paint
    base_r, seed = ctx["base_r"], p["seed"]
    for i, sc in enumerate(p["scars"]):
        what = f"skin scars[{i}]"
        if not isinstance(sc, dict) or sc.get("kind") not in SCARS:
            raise SpecError(f"{what}: {{\"kind\": {' | '.join(SCARS)}, ...}}")
        bad = set(sc) - {"kind", "path", "at", "radius", "zone", "width", "age", "normal", "seed", "mask", "amount"}
        if bad:
            raise SpecError(f"{what}: unknown keys {sorted(bad)}")
        kind, old = sc["kind"], float(np.clip(sc.get("age", 1.0), 0, 1))
        sd = seed + 120 + 7 * i + int(sc.get("seed", 0))
        amt = float(sc.get("amount", 1.0))
        n = f"scar{i}_{kind}"
        # fresh: red-purple, swollen; healed: paler than the skin (no melanocytes), flat or sunk, smooth and a bit shiny
        col = T(melanin=1.0 - 0.75 * old, blood=4.5 - 3.9 * old, oxygenation=0.55 + 0.2 * old)
        if "path" in sc:
            pts = _points(sc["path"], what)
            w = float(sc.get("width", {"cut": 0.0016, "surgical": 0.0014, "keloid": 0.005}.get(kind, 0.002)))
            line = {"spot": {"at": pts, "radius": [round(0.5 * w * (0.55 if j in (0, len(pts) - 1) else 1.0), 6) for j in range(len(pts))],
                             "soft": 0.6, "line": True}}
            wide = {"spot": {"at": pts, "radius": round(1.6 * w, 6), "soft": 0.9, "line": True}}
            area = [line]
        else:
            if "zone" in sc:
                area = [{"zone": sc["zone"]}]
            elif "at" in sc:
                area = [{"spot": {"at": sc["at"], "radius": float(sc.get("radius", 0.02)), "soft": 0.35}}]
            else:
                raise SpecError(f"{what}: needs \"path\" (a line), or \"at\" + \"radius\" or \"zone\" (a patch)")
            plain = list(area)
            wide = None
            if kind in ("cut", "surgical"):
                raise SpecError(f"{what}: a {kind} scar runs along a \"path\"")
        m_extra = sc.get("mask")
        if kind in ("cut", "surgical"):
            layer(n + "_halo", m_extra, pre=True, color=T(blood=2.4 - 1.6 * old, melanin=1.1), opacity=0.35 * amt, mask=[wide])
            layer(n, m_extra, color=col, opacity=0.85 * amt, roughness=max(base_r - 0.14, 0.2),
                  height=round((0.00035 - 0.0005 * old) * amt, 7), mask=area)
            if kind == "surgical":  # stitch marks: paired dots either side, ~6 mm apart
                C = paint.resolve_spot(spec, {"at": pts, "radius": 0.001})["c"]
                nrm = np.asarray(sc.get("normal", [0, -1, 0]), float)
                seg = np.linalg.norm(np.diff(C, axis=0), axis=1)
                s = np.concatenate([[0], np.cumsum(seg)])
                dots = []
                for d in np.arange(0.004, s[-1] - 0.002, 0.006):
                    j = min(int(np.searchsorted(s, d) - 1), len(seg) - 1)
                    q = C[j] + (C[j + 1] - C[j]) * (d - s[j]) / max(seg[j], 1e-9)
                    side = np.cross(C[j + 1] - C[j], nrm)
                    side /= max(np.linalg.norm(side), 1e-9)
                    dots += [(q + 2.6 * w * side).round(5).tolist(), (q - 2.6 * w * side).round(5).tolist()]
                if dots:
                    layer(n + "_stitches", m_extra, color=col, opacity=0.7 * amt, height=-0.00012,
                          mask=[{"spot": {"at": dots, "radius": round(0.45 * w, 6), "soft": 0.6}}])
        elif kind == "keloid":
            layer(n, m_extra, color=T(melanin=1.25 - 0.3 * old, blood=4.2 - 1.6 * old, oxygenation=0.5), opacity=0.9 * amt,
                  roughness=max(base_r - 0.2, 0.18), height=round(0.0009 * amt, 6), mask=area)
        elif kind == "burn":
            ragged = area + [{"breakup": {"amount": 0.35, "scale": 0.008, "sharpness": 0.6, "seed": sd}}]
            layer(n, m_extra, pre=True, color=T(melanin=0.45, blood=2.4 - 1.2 * old), opacity=0.85 * amt, roughness=max(base_r - 0.17, 0.2), mask=ragged)
            layer(n + "_red", m_extra, pre=True, color=T(melanin=1.5, blood=4.0 - 1.5 * old, oxygenation=0.6), opacity=0.6 * amt,
                  mask=[{"noise": {"scale": 0.007, "range": [0.5, 0.62], "seed": sd + 1, "warp": 0.9}}, {"mask": ragged}])
            layer(n + "_webs", m_extra, height=round(-0.0006 * amt, 6),  # a net of taut furrows in contracted tissue
                  mask=[{"tile": {"swatch": "coarse", "size": 0.05, "vary": False}}, {"mask": area}])
        elif kind == "pockmarks":
            w = float(sc.get("width", 0.002))
            dots = [{"tile": {"swatch": "stubble", "size": round(0.012 * w / 0.00018, 4), "range": [0.2, 0.8], "vary": False}}, {"mask": area}]
            layer(n, m_extra, color=T(melanin=0.8, blood=1.3 - 0.4 * old), opacity=0.4, height=round(-0.00038 * amt, 6), mask=dots)
            continue  # the skin between the pits keeps its pores
        ctx["smooth"].append(area if not m_extra else area + [{"mask": m_extra}])


def tattoo_image(img: dict, age: float, ink) -> tuple[dict, bool]:
    """The tattoo's image as it has aged: (a paint image dict pointing at the processed file, has its own colours).
    Lines spread (a blur growing with the years, in the picture's own millimetres), black turns blue-green and thins,
    colours lose saturation (yellows and reds first)."""
    from PIL import Image, ImageFilter
    from . import images
    src = images.source_path(img)
    text = "text" in img
    sz = img.get("size") or [None, None]
    key = hashlib.sha1(json.dumps([str(src), round(age, 2), ink, sz, 3], default=str).encode()).hexdigest()[:16]
    out = images.store_dir() / f"tt_{key}.png"
    if not out.exists():
        im = Image.open(src).convert("RGBA")
        W, H = im.size
        width_m = float(sz[0]) if sz and sz[0] else (float(sz[1]) * W / H if sz and sz[1] else 0.08)
        a = np.asarray(im, np.float32) / 255.0
        rgb, al = a[..., :3].copy(), a[..., 3].copy()
        if text or (np.ptp(rgb.reshape(-1, 3), axis=0).max() < 0.02 and al.min() < 0.5):  # ink given by coverage alone
            rgb[...] = np.asarray(ink, np.float32)
            own = False
        else:
            own = True
            if al.min() > 0.98:  # an opaque picture on white paper: the paper isn't ink
                al = np.clip((1.0 - rgb.min(-1)) * 4.0, 0, 1) if rgb.reshape(-1, 3).mean() > 0.6 else al
        yrs = float(np.clip(age, 0, 60))
        fade = float(np.exp(-yrs / 45.0))
        # colours fade toward grey; darks drift blue-green
        grey = rgb.mean(-1, keepdims=True)
        rgb = grey + (rgb - grey) * (0.35 + 0.65 * fade)
        darkness = np.clip(1.0 - grey * 1.6, 0, 1)
        rgb = rgb + darkness * (1 - fade) * (np.array([0.10, 0.2, 0.22], np.float32) - rgb) * 0.9
        rgb = rgb + (1 - fade) * 0.25 * (1 - rgb) * 0.6  # thinner ink: lighter
        px_per_mm = W / (width_m * 1000.0)
        blur = (0.12 + 0.03 * yrs) * px_per_mm  # mm of spread
        vis = al > 0.05  # where there's no ink, carry the ink's mean colour (a blur would pull in the paper)
        if vis.any() and not vis.all():
            rgb[~vis] = rgb[vis].mean(0)
        rgba = np.dstack([rgb, al])
        im2 = Image.fromarray(np.round(np.clip(rgba, 0, 1) * 255).astype(np.uint8), "RGBA")
        if blur > 0.3:
            r, g, b, al_ = im2.split()
            al_ = al_.filter(ImageFilter.GaussianBlur(blur))
            rgbb = Image.merge("RGB", (r, g, b)).filter(ImageFilter.GaussianBlur(blur * 0.6))
            im2 = Image.merge("RGBA", (*rgbb.split(), al_))
        out.parent.mkdir(parents=True, exist_ok=True)
        tmp = out.with_suffix(".tmp.png")
        im2.save(tmp)
        tmp.replace(out)
        (out.with_suffix(".own")).write_text("1" if own else "0")
    own = out.with_suffix(".own").read_text() == "1" if out.with_suffix(".own").exists() else not text
    new = {k: v for k, v in img.items() if k not in ("file", "id", "text", "name", "channel")}
    new["id"] = images.ingest(out)
    return new, own


def _tattoos(spec, p, layer, ctx) -> None:
    for i, tt in enumerate(p["tattoos"]):
        what = f"skin tattoos[{i}]"
        if not (isinstance(tt, dict) and isinstance(tt.get("image"), dict)):
            raise SpecError(f"{what}: {{\"image\": {{a paint image: \"file\" | \"text\", \"at\", \"size\", ...}}, \"age\", \"opacity\", \"ink\"}}")
        bad = set(tt) - {"image", "age", "opacity", "ink", "mask"}
        if bad:
            raise SpecError(f"{what}: unknown keys {sorted(bad)} (have image, age, opacity, ink, mask)")
        age = float(tt.get("age", 2.0))
        ink = _hex(tt.get("ink", "#1c2026"))
        img, own = tattoo_image(tt["image"], age, ink)
        op = float(tt.get("opacity", 0.9)) * (0.6 + 0.4 * float(np.exp(-age / 30.0)))
        # ink lies in the dermis: it multiplies into the skin's own colour; melanin above it mutes it on dark skin
        op *= 1.0 - 0.35 * p["tone"]["melanin"]
        layer(f"tattoo{i}", tt.get("mask"), color="image", image=img, mix="multiply", opacity=op)


def reference() -> str:
    return __doc__.split("\n\n", 1)[1].strip()
