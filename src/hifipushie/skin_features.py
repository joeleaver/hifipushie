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
             brow lower, onto the orbital rim), "arch": 1 (x the landmarks' slope: 0 = level), "tilt": deg (the whole
             brow turned, tail up +), "fall": 1 (x how far the tail drops past the arch: 0.3 = a straight, rising
             brow), "lift": [inner, tail] m (each end up + / down -), "apart": m (both brows off the mid-line), "soft": 0..1 (a soft mass rather than hairs one by one), "feather": m (the band's lower edge fades over it: photos ~.0012-.0016), "shadow": x the skin-level shadow under the hairs (1; lower = gaps and a fading head show), "taper":
             0..1 (0.82: how much the band thins toward the tail; 0.95 = a clean thin tail on a thick brow), "tail":
             0..1 (1: how far along the hairs reach), "head": 0..0.6 (0: the share of the length over which the inner end fades
             in, sparse single hairs; 0.65 matches the photos' ramp), "head_density": 0..1 (0.05: the share of hairs kept at the inner end)}: hairs as strokes, growing up at the inner end and out along the brow.
  lashes     {"color", "amount": 0..1 (0.7), "width": 1 (x the lash line's width, with lash geometry)}: the lash lines
             darkened (upper more).
  stubble    {"amount", "color", "where", "size": 1 (the dots' size), "count": 1 (hairs per area x, .25-4: density saturates at 1), "shadow": 1 (the under-skin shadow's strength; "shadow_color",
             "shadow_breakup": its noise, 0 = an even field: a dense stubble shadow reads as one grey-brown field),
             "grey": 0..1 (+ "grey_color": a share of white hairs: salt and pepper), "zones": {moustache, chin, soul_patch, jaw,
             cheeks, neck: weight 0..1.5 (1)} (where it grows: a goatee, bare cheeks)}: the beard area: a shadow under the
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
    ctx = {**ctx, "torso": "chest" in J, "spec": spec}
    ctx["smooth"] = []
    if p.get("stack") and ctx["face"]:   # (skin_layers) the colour as a stack of layer maps from the reference: over the
        from . import skin_layers       # broad colour layers laid so far, under every fine generator below
        skin_layers.layers(spec, p["stack"], out, part)
    from . import paint as _paint
    ctx["eyes"] = all(e in (_paint._expanded(spec).get("blobs") or {}) for e in ("eye.L", "eye.R"))  # eyeballs: lid margins
    from . import lashes as _lashes
    ctx["lash_geometry"] = ctx["eyes"] and bool(_lashes.wanted(spec))  # lash ribbons (lashes.py) over the painted lines
    if ctx["lash_geometry"]:
        lm_ = _lashes.for_spec(spec)
        ctx["lash_curves"] = None if lm_ is None else {k: [np.round(c, 5).tolist() for c in v] for k, v in lm_["curves"].items()}
    from .skin_makeup import resolve as _mk_resolve
    f0 = _mk_resolve(p["makeup"]).get("foundation")
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
    o = _opt(f.get("freckles"), "features.freckles", ("size", "clump", "dark", "zones", "engine"))
    if o and o.get("engine", "map") == "map" and ctx["face"] and "lm_jaw_1.L" in J:
        _freckle_map(ctx["spec"], p, J, o, layer, T, ctx)
        o = None
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
        scattered = not o.get("at") or (isinstance(f.get("moles"), dict) and "amount" in f["moles"])
        if scattered and ctx["face"] and "lm_jaw_1.L" in J and not o.get("where"):
            # a few on the face from the mark map (the swatch's "strongest marks" were nearly invisible): ~12 at amount 1
            from . import skin_marks
            q = {**freckle_options({"amount": 1e-4}), "moles": int(round(12 * float(o["amount"]))), "seed": int(o.get("seed", 0))}
            path, place, _ = skin_marks.freckle_map(ctx["spec"], p["part"], J, q)
            stacks.append([{"image": {"file": path, **place, "channel": "b"}}])
        elif scattered:
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
        # (under a measured stack: colour only, no height: a stacked head's material is near Cycles' shader stack limit,
        # and the blemishes' bump tipped Tess's and a test head's over: "would render black")
        hk = {} if p.get("stack") else {"height": 0.0004}
        layer("blemish_bump", o.get("mask"), color=T(blood=6.5, melanin=1.15), opacity=0.6 * (0.5 + 0.5 * show), roughness=max(base_r - 0.14, 0.2),
              mask=[{"tile": {**tile, "range": [round(lo + 0.3, 3), round(lo + 0.5, 3)]}}] + w, **hk)

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
    # the eye corners' wet red (caruncle, canthus) fades as the lid closes: on a closed eye it showed as red lines at the
    # seam's ends (a blind review read the closed lid as a cut)
    wb_ = float(np.clip(float((((spec.get("base") or {}).get("head") or {}).get("pose") or {}).get("lid_upper", 0.0) or 0.0) / 0.0095, 0.0, 1.0))
    if wb_ > 0:
        for k_ in [k for k in out if any(t in k for t in ("caruncle", "canthus", "eye_shade"))]:
            if out[k_].get("opacity") is not None:
                out[k_]["opacity"] = round(float(out[k_]["opacity"]) * (1 - wb_), 4)
    _gnm_mouth(spec, out, part)
    _wrinkles(p, J, layer, T, ctx)
    from . import skin_folds
    skin_folds.build(spec, p, J, layer, ctx)
    _hair(p, J, layer, T, ctx)
    if p.get("projection") and ctx["face"]:   # the references as albedo (skin_project): over our colours and painted hair
        from . import skin_project
        skin_project.layers(spec, p["projection"], out, part)
    _scars(spec, p, J, layer, T, ctx)
    _tattoos(spec, p, layer, ctx)
    from . import skin_makeup
    skin_makeup.build(spec, p, J, layer, T, ctx)
    return ctx["smooth"]


INNER_LIP_COLOR = [0.38, 0.148, 0.11]  # (r29: [0.38, 0.11, 0.11] rendered the band over the smile's upper teeth (175, 101, 103) sRGB, G/R 0.58, magenta beside our vermilion (G/R 0.62); the reference's wet inner lip (jaw open) is the vermilion's own hue, G/R 0.66 vs 0.65, a little lighter: G linear 0.39 x R) linear: the wet inner lip (mucosa): redder and darker than the vermilion, lighter than the bag


def inner_lip_values(head) -> np.ndarray | None:
    """Per GNM vertex, how much of the wet inner lip (mucosa) colour it takes: GNM's skin rings from the open mouth
    loop (where the sock joins) to the contact ring (base.LIP_RING) 1, the next ring INNER_LIP_FADE, else 0. With the
    lips closed the scene's surface has no rolls, so the bake filled them from the skin beside them and every shape
    that parts the lips (jawOpen, smiles) showed a ragged brown fringe round the opening (review expr_r1). The export
    paints these values onto the low poly's own triangles (asset.bake, "inner_paint")."""
    import collections
    from . import base as _base
    if head is None or head.get("gnm_world") is None:
        return None
    g = _base._gnm_data()
    mp = _base.gnm_mouth(head)
    n = len(np.asarray(head["gnm_world"]))
    skin = np.asarray(g["skin"], bool)
    sock = np.asarray(g["groups"]["mouth_sock"]) > 0.5
    Q = np.asarray(g["quads"])
    Q = Q[skin[Q].all(1)]
    adj = collections.defaultdict(set)
    for q in Q:
        for k in range(4):
            a, b = int(q[k]), int(q[(k + 1) % 4])
            adj[a].add(b), adj[b].add(a)
    own = sock[mp["sock"]["ids"]]
    rim = [int(v) for v in mp["sock"]["ids"][~own]]
    if not rim:
        return None
    lev = {v: 0 for v in rim}
    front = list(rim)
    ring = _base.LIP_RING
    while front and min(lev[v] for v in front) <= ring:
        nxt = []
        for v in front:
            for u in adj[v]:
                if u not in lev and not sock[u]:
                    lev[u] = lev[v] + 1
                    nxt.append(u)
        front = nxt
    val = np.zeros(n)
    for v, lv in lev.items():
        # (v25 faded the contact ring itself, nothing past it, against "a jagged pink band with a notch" (expr_r8..r10):
        # the notch was the upper roll folded forward through the seam (faceshapes._rolls_behind), and without the
        # wet colour on the contact ring the closed seam showed the projected skin's dark lip line as a jagged
        # dark gap (expr_r11 / r12): back to the ring at 1, the next at INNER_LIP_FADE)
        val[v] = 1.0 if lv <= ring else INNER_LIP_FADE if lv == ring + 1 else 0.0
    return val


INNER_LIP_FADE = 0.3  # the ring outside the contact ring: the wet line fading into the vermilion
MOUTH_DEEP_COLOR = [0.035, 0.008, 0.008]  # linear: the mouth's interior (GNM's sock) a few rings in: dark, a throat
MOUTH_DARK_SIDE = (0.55, 0.8, 0.003, 0.006)  # (r32) the sock also darkens past this share of the mouth's half width (ramp a..b), from this depth behind the lips' front (ramp, m): the side walls in shadow; None = off
MOUTH_DARK_DEPTH = (0.008, 0.012)  # (4-8 mm: dark sock shards at the closed seam, expr_r11) m behind the lips' front: the sock darkens fully over this (by depth, beside the rings)
TONGUE_BACK = (0.04, 0.06)  # (r28: back with JAW_TONGUE off, expr_r23 jaw row worse than r22) (r26: with JAW_TONGUE's bowed dorsum the front sees rest depths 41-62 mm (p5-p95), so 40-60 turned 74% of the visible tongue dark) (r23: 28-50 mm: jawOpen sees the dorsum 36-42 mm back, so it read (122, 58, 58) sRGB with a black band, "tongue missing", expr_r19) (r17: 12-30 mm blacked out the whole visible dorsum, v32) m behind the tongue's tip: its colour darkens to MOUTH_DEEP_COLOR over this (None: off)
TEETH_BACK = (0.009, 0.022, 0.8, [0.1, 0.075, 0.06])  # m behind each row's front (along the mouth's `out`), strength,
# linear colour: the teeth darkened toward the molars (expr_r16 smile: "the teeth run all the way into the mouth corners";
# a real smile's outer teeth fall into the buccal corridor's shadow; flat-coloured teeth stayed lit to the corners)
MOUTH_DEEP_RINGS = 2  # (3 left the sock walls at the corners lit pink in jawOpen: "raw red fleshy shapes", expr_r7) rings of the sock from the lips' rim over which the inner lip red darkens to MOUTH_DEEP_COLOR


def mouth_interior_values(head) -> np.ndarray | None:
    """Per GNM vertex 0..1: how deep in the mouth's sock it is (0 off the sock, rising ring by ring from the rim to 1 at
    MOUTH_DEEP_RINGS). The sock is in the low poly but hidden in the closed scene, so the bake painted it grey: grey
    shards inside every parted mouth and a grey dot at the upper lip's centre in the neutral (review expr_r2)."""
    import collections
    from . import base as _base
    if head is None or head.get("gnm_world") is None:
        return None
    g = _base._gnm_data()
    mp = _base.gnm_mouth(head)
    n = len(np.asarray(head["gnm_world"]))
    sock = np.asarray(g["groups"]["mouth_sock"]) > 0.5
    Q = np.asarray(g["quads"])
    adj = collections.defaultdict(set)
    for q in Q:
        for k in range(4):
            a, b = int(q[k]), int(q[(k + 1) % 4])
            adj[a].add(b), adj[b].add(a)
    own = sock[mp["sock"]["ids"]]
    rim = [int(v) for v in mp["sock"]["ids"][~own]]
    if not rim:
        return None
    lev = {v: 0 for v in rim}
    front = list(rim)
    while front:
        nxt = []
        for v in front:
            for u in adj[v]:
                if u not in lev and u < len(sock) and sock[u]:
                    lev[u] = lev[v] + 1
                    nxt.append(u)
        front = nxt
    val = np.zeros(n)
    for v, lv in lev.items():
        if v < len(sock) and sock[v]:
            val[v] = min(1.0, lv / MOUTH_DEEP_RINGS)
    val[:len(sock)][sock & (val[:len(sock)] == 0)] = 1.0  # sock vertices out of reach of the rim: deep
    # and by depth behind the lips' front: the corners' walls are near the rim in rings but 5-10 mm in, beside the
    # teeth; lit pink they read as torn lining in every jawOpen (expr_r7..r9). A cavity in shadow is dark.
    ml = _base.mouth_lips(head)
    W = np.asarray(head["gnm_world"], float)
    lm = np.asarray(head["lm68"], float)
    front = float(np.max((lm[[48, 54, 51, 57]] - ml["M"]) @ ml["out"]))
    depth = front - (W - ml["M"]) @ np.asarray(ml["out"], float)
    by_depth = np.clip((depth - MOUTH_DARK_DEPTH[0]) / (MOUTH_DARK_DEPTH[1] - MOUTH_DARK_DEPTH[0]), 0, 1)
    if MOUTH_DARK_SIDE:  # (r32) the side walls past the dental arch, a little in: the cheeks' inner walls in shadow
        # (jaw: lit pink walls beside the tongue with a black edge-on line between, "black vertical side lines")
        a, b, d0, d1 = MOUTH_DARK_SIDE
        u = np.abs((W - ml["M"]) @ np.asarray(ml["side"], float)) / max(0.5 * ml["width"], 1e-6)
        by_depth = np.maximum(by_depth, np.clip((u - a) / (b - a), 0, 1) * np.clip((depth - d0) / (d1 - d0), 0, 1))
    on = np.zeros(n, bool)
    on[:len(sock)] = sock
    val[on] = np.maximum(val[on], by_depth[on])
    return val


def _gnm_mouth(spec, out, part) -> None:
    """GNM's OWN MOUTH, dressed (minimal, 2026-10-12; Joe: "we'll figure out the dressing as we go along"): the mouth
    bag dark wet red on the skin's part, the gums on the teeth's part. Both masks are point clouds made from GNM's own
    vertices (its `mouth_sock` and `gums` groups, as the head places them), read like a hand-painted mask
    (paint.painted_values): the gum line is GNM's scalloped one, not a height. Teeth and tongue keep their parts'
    flat colours (base.MOUTH_PARTS): no enamel translucency, no tongue texture, no wet film yet."""
    from . import base as _base
    from . import paint as _paint
    from . import spec as _specmod
    b = spec.get("base") or {}
    if _base.mouth_mode(b) != "gnm":
        return
    head = _base.head_of({"joints": _specmod.expand_mirror(spec)["joints"]}, b)
    if head is None or _base.mouth_mode(b, head) != "gnm":
        return
    mp = _base.gnm_mouth(head)
    g = _base._gnm_data()
    sk = mp["sock"].get("points") or _base._piece_points(mp["sock"]["verts"], mp["sock"]["faces"], rounds=1)
    # (the joining quads' lip-loop vertices are skin: the bag's colour starts a ring behind them)
    own = np.asarray(g["groups"]["mouth_sock"])[mp["sock"]["ids"]] > 0.5
    from scipy.spatial import cKDTree
    d_own = cKDTree(mp["sock"]["verts"][own]).query(sk["verts"])[0]
    d_rim = cKDTree(mp["sock"]["verts"][~own]).query(sk["verts"])[0] if (~own).any() else np.full(len(sk["verts"]), 1.0)
    # (the cloud's own spacing, and only points clearly inside the sock: at a 3 mm spacing the mask reached ~6 mm and
    # printed the bag's near-black red onto the outer skin at the mouth corners: two black "curls" on every GNM head)
    sp_ = float(np.median(cKDTree(sk["verts"]).query(sk["verts"], k=2)[0][:, 1]))
    pid = _paint.save_painted(sk["verts"], sk["normals"], (d_own < d_rim - 0.0008).astype(float), float(np.clip(sp_, 0.0005, 0.0015)))
    # (the inner rolls are NOT a scene layer: with the lips closed the scene's surface has no rolls (the fill behind the
    # seam), so a painted cloud there found the outer lips instead (v8: lipstick red). The export paints them on the
    # low poly's own triangles by GNM index: asset.bake's "inner_paint", values from inner_lip_values)
    out["skin:mouth_bag"] = {"part": part, "color": list(_base.BAG_COLOR), "roughness": 0.4, "specular": 0.5,
                             "mask": [{"painted": pid}]}
    for k, tpart in (("teeth_upper", _base.TEETH_PARTS[0]), ("teeth_lower", _base.TEETH_PARTS[1])):
        V, F = mp[k]["verts"], [list(map(int, f)) for f in mp[k]["faces"]]
        gum = mp[k]["gum"].astype(float)[:, None].repeat(3, 1)
        for _ in range(_base.MOUTH_SUBDIVIDE):
            V2, F2 = _base._catmull_clark(V, F)
            gum = _base._catmull_clark(gum, F)[0]  # (the group's weight subdivided like the positions)
            V, F = V2, F2
        N, h = _base._normals_and_h(V, F)
        pid = _paint.save_painted(V, N, np.clip((gum[:, 0] - 0.35) / 0.3, 0, 1), 0.0012)
        out["skin:gums" + ("" if tpart == "teeth" else "_lower")] = {
            "part": tpart, "color": list(_base.GUM_COLOR), "roughness": 0.4, "specular": 0.5, "mask": [{"painted": pid}]}
    if TEETH_BACK:
        out_ = np.asarray(mp["frame"][1], float)
        for k, tpart in (("teeth_upper", _base.TEETH_PARTS[0]), ("teeth_lower", _base.TEETH_PARTS[1])):
            V, F = mp[k]["verts"], [list(map(int, f)) for f in mp[k]["faces"]]
            for _ in range(_base.MOUTH_SUBDIVIDE):
                V, F = _base._catmull_clark(V, F)
            N, _h = _base._normals_and_h(V, F)
            dep = float((V @ out_).max()) - V @ out_
            u = np.clip((dep - TEETH_BACK[0]) / (TEETH_BACK[1] - TEETH_BACK[0]), 0, 1)
            pid = _paint.save_painted(V, N, TEETH_BACK[2] * u * u * (3 - 2 * u), 0.0012)
            out["skin:teeth_back" + ("" if tpart == "teeth" else "_lower")] = {
                "part": tpart, "color": list(TEETH_BACK[3]), "roughness": 0.4, "specular": 0.5, "mask": [{"painted": pid}]}
    if TONGUE_BACK and "tongue" in mp and len(mp["tongue"]["verts"]):
        # the tongue's back darkened into the throat (expr_r15: the flat-coloured dorsum read as "a flat red back wall"
        # in jawOpen; a real tongue's back falls into the mouth's shadow): by depth behind its tip, along the mouth's `out`
        V, F = mp["tongue"]["verts"], [list(map(int, f)) for f in mp["tongue"]["faces"]]
        for _ in range(_base.MOUTH_SUBDIVIDE):
            V, F = _base._catmull_clark(V, F)
        N, _h = _base._normals_and_h(V, F)
        out_ = np.asarray(mp["frame"][1], float)
        dep = float((V @ out_).max()) - V @ out_
        u = np.clip((dep - TONGUE_BACK[0]) / (TONGUE_BACK[1] - TONGUE_BACK[0]), 0, 1)
        pid = _paint.save_painted(V, N, u * u * (3 - 2 * u), 0.0012)
        out["skin:tongue_back"] = {"part": "tongue", "color": list(MOUTH_DEEP_COLOR), "roughness": 0.45,
                                   "specular": 0.5, "mask": [{"painted": pid}]}


FRAME_PAST = 0.0022   # m: the upper lash line's dark frame past the outer canthus (the visible eye's outer end)
CANTHUS_TIP = 0.0012  # m: the inner corner's dark point, on past the caruncle's pocket toward the nose
LOWER_FRAME = 0.8     # the lower lash line's weight against the upper's (was 0.55: weak, the eye read short)
EYE_OCCLUSION = 0.5   # skin.eyes.occlusion default (the lids' shadow on the ball). mouth_eye_bias: at 1 it takes 0.6-0.8 mm of the
#                       detector's eye opening and ~0.5 mm of the fissure against photos; proposed 0.5 (docs/notes/mouth_eye_bias.md)
EYE_KEYS = ("iris", "iris_size", "pupil", "veins", "sclera", "tear", "waterline", "limbal", "limbal_width",
            "iris_contrast", "gloss", "occlusion", "caruncle", "crease", "canthus", "iris_inner", "iris_inner_to")


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
    {"iris": colour (the iris toward its rim), "iris_inner": colour (the zone round the pupil, when it differs: hazel,
    central heterochromia; "iris_inner_to": where it hands over, share of the radius, 0.55), "iris_size": m (the visible iris' diameter: adults 11-12.5 mm, 11.7 on average; unset on a GNM
    head with GNM's own eyeball: its limbus for the identity, base.head.identity.eyes_000), "pupil": 0..1
    of the iris' radius (0.36; bright daylight 0.2-0.3; unset on GNM's eyeball: its own pupil, 0.5 at rest, moved by
    base.head.expression.pupils_000: +1 = 0.67, -1 = 0.33), "veins": 0..1, "sclera": colour, "limbal": 0..1 (0.72: the
    dark ring at the iris' edge, darker and wider in the young), "limbal_width": share of the radius (0.2),
    "iris_contrast": the fibres' contrast (1), "gloss": 0..1 (1: the tear film, a clear coat over a matte iris and
    sclera: the sharp catchlight on the cornea), "occlusion": 0..1 (1: the lids' shadow on the ball, all round the
    lid contact and deepest under the upper lid; MetaHuman's eye-occlusion shell as paint), "tear": 0..1 (the
    meniscus: the bright wet line where the lower lid meets the ball), "waterline": 0..1, "caruncle": 0..1.2 (unset:
    a soft pink spot; a number: the inner corner's pocket filled wet dark red from GNM's inner-corner landmark to the
    eyeball, the way a photographed canthus reads: the eye then reaches its anatomical inner corner), "canthus": 0..1.2
    (unset / 0: off; the LATERAL corner: a soft warm shadow on the eyeball's outer end and the lid junction's wet
    red, against the white wedge running to a point that GNM's sharp outer corner shows; ~0.8), "crease":
    {"amount": 0..1 (0.6), "path": [[u, v], ...] (mm from the iris centre in the eye's frame, u toward the outer
    corner, v up: eye_ruler.crease_path reads it off the picture), "width": mm (0.5), "color", "shade": 0..1 (0.4:
    a soft band over the line, the fold's underside)}: the fold LINE as a thin shadow in the skin (multiply), where
    the lid's soft valley gives no line of its own}."""
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
    from . import base as _base
    eg = _base.eye_native(spec)  # (gnmnative) GNM's own eye: the iris at its limbus, the pupil as its geometry has it
    # (the identity's eyes_* components and the expression's pupils_000: dilation is a pose value)
    path = skin_swatch.eye_image(iris, float(e.get("pupil", eg["pupil"] if eg else 0.36)), veins, tuple(scl), p["seed"], span,
                                 limbal=float(e.get("limbal", 0.72)), contrast=float(e.get("iris_contrast", 1.0)),
                                 limbal_width=float(e.get("limbal_width", 0.2)),
                                 inner=_hex(e["iris_inner"]) if e.get("iris_inner") else None, inner_to=float(e.get("iris_inner_to", 0.55)))
    gloss = float(e.get("gloss", 1.0))
    occ = float(e.get("occlusion", EYE_OCCLUSION))
    for sd in (".L", ".R"):
        c, f = J[f"eye{sd}"], J[f"eye_front{sd}"]
        r = float(np.linalg.norm(f - c))
        d = (f - c) / max(r, 1e-9)
        size = float(e.get("iris_size", 2 * eg["limbus"] if eg else 0.0118 * r / 0.0123)) * span
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
            # (one layer: each layer costs shader; the band all round is the max over the upper lid's shadow)
            # (r27: opacity 0.6 -> 0.25 and a greyer shadow (was [0.6, 0.43, 0.41]): with the picture's own warm edge the
            # true visible sclera baked (0.85, 0.79, 0.79) of the paint, both eyes alike; the L/R "asymmetry" was the
            # measure taking iris texels. Fast path (assembly/eyevar.py): mid sclera -> (0.94, 0.90, 0.90) L, (0.95, 0.92, 0.92) R)
            out[f"skin:eye_shade{nm}"] = {"part": part, "color": [0.7, 0.64, 0.62], "mix": "multiply",
                                          "opacity": round(min(0.25 * occ, 1.0), 3),
                                          # (r26: both terms keyed to the distance from the lids, unsigned: the ball lies
                                          # INSIDE the head's field, so "near base" was 1 over the whole visible sclera,
                                          # baked x(0.76, 0.66, 0.65), and the height-keyed upper shadow darkened the eye
                                          # whose lids sit higher: L 49 vs R 68 against the paint's ~90)
                                          "mask": [{"mask": [{"axis": {"dir": [0, 0, 1], "at": f"eye{sd}", "from": round(0.1 * r, 5),
                                                                       "to": round(0.55 * r, 5)}},
                                                             {"spot": {"at": f"eye{sd}", "radius": round(1.6 * r, 5), "soft": 0.2}},
                                                             {"near": ["base"], "side": "both", "within": round(0.04 * r, 5),
                                                              "soft": round(0.16 * r, 5)}],
                                                    "weight": 0.85},
                                                   {"near": ["base"], "side": "both", "within": round(0.02 * r, 5),
                                                    "soft": round(0.09 * r, 5), "blend": "max"}]}
        # the tear line: the strip of tear film standing where the lower lid meets the ball, a thin bright wet line
        if float(e.get("tear", 1.0)) > 0:
            out[f"skin:eye_tear{nm}"] = {"part": part, "color": [0.97, 0.86, 0.84], "opacity": round(0.4 * float(e.get("tear", 1.0)), 3),
                                         "roughness": 0.02, "specular": 1.0,
                                         "mask": [{"near": ["base"], "side": "both", "within": round(0.015 * r, 5), "soft": round(0.035 * r, 5)},
                                                  {"axis": {"dir": [0, 0, -1], "at": f"eye{sd}", "from": round(0.05 * r, 5), "to": round(0.2 * r, 5)}}]}
    # on the skin: the caruncle (the pink, wet corner by the nose) and the lower lid's waterline
    car = e.get("caruncle")
    if car is None:   # (the old soft pink spot)
        pts = [{"at": f"lm_eye_inner{sd}", "offset": [round(sx * 0.012 * io, 5), round(-0.02 * io, 5), 0.0]} for sd, sx in ((".L", 1), (".R", -1))]
        layer("caruncle", pre=True, color=T(blood=5.0, melanin=0.7), opacity=0.7, roughness=0.18,
              mask=[{"spot": {"at": pts, "radius": round(0.036 * io, 5), "soft": 0.6}}])
    elif float(car) > 0:
        # (eyeruler) GNM's lids end in a pocket between the opening's medial end and the lm68 inner corner (1.9 mm): the
        # caruncle and the corner's wet red. Painted as skin, the eye read ~2 mm short at the inner corner against a
        # photo (a detector puts the canthus at the pocket's tip, as GNM's landmark does). So the pocket is filled with
        # a darker wet red, from the landmark out to the eyeball: a capsule along the corner -> eye line.
        a = float(car)
        segs = []
        for sd in (".L", ".R"):
            i_ = np.asarray(J[f"lm_eye_inner{sd}"], float)
            sx = 1.0 if sd == ".L" else -1.0   # (the pocket runs sideways from the landmark, a little back into the head)
            segs.append([[round(float(x), 5) for x in i_ + np.array([sx * t, 0.25 * t, 0.0])] for t in (0.0003, 0.0013, 0.0023)])
        from .skin import _sp
        m = [dict(_sp(sg, [0.0007, 0.0011, 0.0010], soft=0.35, line=True), **({"blend": "max"} if k else {})) for k, sg in enumerate(segs)]
        layer("caruncle", pre=True, color=T(blood=6.0, melanin=0.8), opacity=round(min(0.85 * a, 1.0), 3), roughness=0.15, mask=m)
        # THE INNER CANTHUS' TIP (mouth_eye_bias -> skin): in a photo the inner corner ends in a dark POINT (the pocket's
        # shadow where the lids meet past the caruncle), not a rounded white / pink end: a thin dark wedge from the
        # pocket's medial end on toward the nose, tapering to nothing over ~CANTHUS_TIP; drawn in the caruncle's wet
        # multiply (one layer: the shader budget), darker there
        tips = []
        for sd in (".L", ".R"):
            i_ = np.asarray(J[f"lm_eye_inner{sd}"], float)
            sx = 1.0 if sd == ".L" else -1.0
            tips.append(dict(_sp([i_ + np.array([sx * 0.0008, 0.0, 0.0]), i_, i_ + np.array([-sx * CANTHUS_TIP, 0.0, -0.0002])],
                                 [0.00045, 0.0003, 0.00006], soft=0.5, line=True), blend="max"))
        layer("caruncle_wet", pre=True, color=[0.64, 0.49, 0.47], mix="multiply", opacity=round(min(0.75 * a, 1.0), 3), mask=m + tips)
        # ... and on the eyeball's nose-side end: the caruncle's flesh and the plica stand in FRONT of the sclera there
        # (a photographed inner corner is 3-4 mm of pink before any white); GNM's pocket alone is a slit
        for sd, sx in ((".L", 1.0), (".R", -1.0)):
            i_ = np.asarray(J[f"lm_eye_inner{sd}"], float)
            c_, f_ = np.asarray(J[f"eye{sd}"], float), np.asarray(J[f"eye_front{sd}"], float)
            r_ = float(np.linalg.norm(f_ - c_))
            q_ = i_ + np.array([sx * 0.0016, 0.0, 0.0002]) - c_       # (the spot sits ON the ball: its nose-side end lies
            q_ = c_ + r_ * q_ / max(float(np.linalg.norm(q_)), 1e-9)   # 2-3 mm behind the lids' corner)
            out[f"skin:eye_caruncle{sd.replace('.', '_')}"] = {
                "part": part, "color": [0.63, 0.43, 0.39], "opacity": round(min(0.75 * a, 1.0), 3), "roughness": 0.2,
                "mask": [_sp([q_], [0.003], soft=0.8)]}
    cn = float(e.get("canthus") or 0.0)
    if cn > 0:
        # (garrettnative, 2026-10-12) THE LATERAL CANTHUS: GNM's lids meet in a sharp V over a 14.6 mm sphere and the
        # sclera is plain white to the corner, so every GNM head shows a white wedge running to a point at the outer
        # corner (gnmnative's ladder: on GNM's raw mesh too; shading, not shape). In a face that corner is in the
        # lids' shadow and the conjunctiva there is pink, not white. So: on the eyeball's outer end a soft warm
        # shadow (multiply; strongest at the corner, gone by the limbus), and on the skin the corner's own wet red
        # at the lid margins' junction (as "caruncle" does at the nose side, much smaller).
        from .skin import _sp
        for sd, sx in ((".L", 1.0), (".R", -1.0)):
            o_ = np.asarray(J[f"lm_eye_outer{sd}"], float)
            c_, f_ = np.asarray(J[f"eye{sd}"], float), np.asarray(J[f"eye_front{sd}"], float)
            r_ = float(np.linalg.norm(f_ - c_))
            q_ = o_ - c_
            q_ = c_ + r_ * q_ / max(float(np.linalg.norm(q_)), 1e-9)    # the corner's place ON the ball
            out[f"skin:eye_canthus{sd.replace('.', '_')}"] = {
                "part": part, "color": [0.58, 0.40, 0.36], "mix": "multiply", "opacity": round(min(0.8 * cn, 1.0), 3),
                "mask": [_sp([q_], [0.0048], soft=0.85)]}
        pts = [np.asarray(J[f"lm_eye_outer{sd}"], float) + np.array([-sx * 0.0006, 0.0, 0.0]) for sd, sx in ((".L", 1.0), (".R", -1.0))]
        layer("canthus", pre=True, color=T(blood=4.5, melanin=1.6), opacity=round(min(0.6 * cn, 1.0), 3), roughness=0.2,
              mask=[_sp(pts, [0.0016] * len(pts), soft=0.7)])
    cr = e.get("crease")
    if isinstance(cr, dict) and float(cr.get("amount", 0.6)) > 0 and cr.get("path"):
        # the fold LINE as the skin's own shadow (eyeruler; Joe: darkness the fold's shape does not give comes from the
        # skin's cosmetics, never a geometry layer): a thin multiply line along a path given in the eye's frame (mm
        # from the iris centre: eye_ruler reads it off the picture), laid from the front like the brows' picture
        f_, c_ = np.asarray(J["eye_front.L"], float), np.asarray(J["eye.L"], float)
        d_ = (f_ - c_) / max(float(np.linalg.norm(f_ - c_)), 1e-9)
        cpath = skin_swatch.crease_image(cr["path"], float(cr.get("width", 0.5)),
                                         colour=tuple(_hex(cr["color"])) if "color" in cr else (0.5, 0.36, 0.32),
                                         shade=float(cr.get("shade", 0.4)))
        img = {"file": str(cpath), "at": [round(float(x), 5) for x in f_ + np.array([0.0, 0.0, 0.003])],
               "dir": [round(float(x), 4) for x in d_], "size": [0.04, 0.03], "depth": 0.02, "facing": -0.3, "mirror": True,
               "mirror_image": True}
        # (the picture itself as the colour, multiplied in: a mask is sampled per vertex and loses a 0.5 mm line)
        layer("lid_crease_line", color="image", image=img, mix="multiply", opacity=round(min(float(cr.get("amount", 0.6)), 1.0), 3))
    if float(e.get("waterline", 1.0)) > 0:   # 0..1 (1): the pink wet rim; on a lid whose rim faces the camera it reads as lid
        layer("waterline", pre=True, color=T(blood=3.5, melanin=0.6), opacity=round(0.5 * float(e.get("waterline", 1.0)), 3),
              roughness=0.15, mask=_zones(["lash_lower"], 0.7))
    from . import lidfold
    fc = lidfold.config(spec)
    if fc:  # the lid's fold (lidfold.py): its crease's own tone, along the fold's own invagination (paint's `near` on
        # a fold prim: the distance across its crease line, scaled by its depth). Skin deep in a tight fold catches
        # no light and its blood shows: a photographed crease is a soft brown-red line. (The field's cavity can't do
        # it: curvature is measured with a 0.75-voxel stencil, which steps over a 0.8 mm groove.)
        w = float(fc["crease_width"]) * 0.001
        # A SHADOW, not a hue: neutral multiplies (the skin's own colour darker, its saturation kept), darkest in a thin
        # line, then a soft gradient up the fold's underside and none below (a red-brown tone read as a painted scar)
        fold = ["lid_fold.L", "lid_fold.R"]
        layer("lid_crease", pre=True, color=[0.76, 0.82, 0.86], mix="multiply",  # (a hair cool: the groove's own
              # subsurface glow reddens it ~3 deg against the photo's crease)
              opacity=round(float(np.clip(0.35 + 0.3 * fc["crease_depth"], 0, 0.9)), 3),
              mask=[{"near": fold, "within": round(0.2 * w, 6), "soft": round(0.8 * w, 6)}])
        layer("lid_fold_shadow", pre=True, color=[0.9, 0.91, 0.92], mix="multiply", opacity=0.85,
              mask=[{"near": fold, "side": "up", "within": 0.0, "soft": round(1.8 * float(fc["fold_width"]) * 0.001, 6)}])


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
    # multiplied in: a crease is a little darker and redder (thin skin); its shadow is the geometry's. (It was [0.7, 0.58,
    # 0.55] at 0.75: over a stubble shadow on facesliders' joint Garrett, where the landmark line lay beside his own
    # deep fold, it painted a dark red-brown streak beside the mouth.)
    crease = [0.84, 0.77, 0.75]

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
        # the folds lie where the surface itself folds: the landmark line finds the region, the surface's concavity the
        # fold (a head with its own deep fold beside the line keeps only a trace of the line)
        ("nasolabial", 1.0, [{"mask": _zones(["nasolabial"], 1.8)}, {"cavity": "concave", "radius": [0.06, 0.012], "weight": 0.7}]),
        ("marionette", 0.9, [{"mask": _zones(["marionette"], 1.7)}, {"cavity": "concave", "radius": [0.06, 0.012], "weight": 0.7}])]
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
        o = _opt(h.get("brows", 1.0), "hair.brows", ("color", "density", "thickness", "length", "grey", "drop", "soft", "arch",
                                                     "tilt", "fall", "lift", "apart", "taper", "tail", "shadow", "head",
                                                     "head_density", "clump", "opacity", "feather"))
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
            path, (wmm, hmm) = skin_swatch.brow_image(dens, thick, float(o.get("length", 0.006)) * 1000, width * 1000, seed,
                                                       fall=float(o.get("fall", 1.0)), taper=float(o.get("taper", 0.82)),
                                                       tail=float(o.get("tail", 1.0)), head=float(o.get("head", 0.0)),
                                                       head_density=float(o.get("head_density", 0.05)),
                                                       clump=float(o.get("clump", 0.0)),
                                                       feather=float(o.get("feather", 0.0)) * 1000)   # m -> mm: the lower edge's fade
            c = 0.5 * (a_ + b_)
            c[2] = (a_[2] + 2 * m_[2] + b_[2]) / 4 - 0.02 * io
            c[1] = m_[1]
            c[2] -= float(o.get("drop", 0.0))   # a heavy brow sits on the orbital rim, its lower edge at the lid's fold
            li, lo_ = (float(x) for x in (o.get("lift") or (0.0, 0.0)))  # m: the inner head / the tail up (+) or down
            c[2] += 0.5 * (li + lo_)
            c[0] += float(o.get("apart", 0.0))  # m: both brows away from the mid-line (+: the heads less pinched)
            d = np.array([0.42, -1.0, 0.12])
            d /= np.linalg.norm(d)
            slope = float(np.degrees(np.arctan2(b_[2] - a_[2], np.linalg.norm((b_ - a_)[:2])))) * float(o.get("arch", 1.0))
            slope += float(o.get("tilt", 0.0))  # deg: the whole brow turned, its tail up (+) or down (-)
            slope += float(np.degrees(np.arctan2(lo_ - li, width)))  # (lift: the two ends placed on their own)
            soft = float(o.get("soft", 0.0))    # 0..1: hairs read less one by one (fine, greying brows: a soft mass)
            img = {"file": str(path), "at": [round(float(x), 5) for x in c], "dir": [round(float(x), 4) for x in d],
                   "size": [round(width, 5), round(width * hmm / wmm, 5)], "rotate": round(slope, 2), "depth": 0.03,
                   "mirror": True, "mirror_image": True, "channel": "alpha"}  # (unmirrored, the other brow's hairs ran
            # toward the nose: "the left eyebrow is backwards")
            # the shadow under the hairs sits where the hairs are: a brow moved off its landmarks (drop, lift, tilt,
            # apart) left the landmark zone's shadow behind as a grey band over the new brow (Tess, 2026-10-09)
            moved = any(o.get(k) for k in ("drop", "lift", "tilt", "apart"))
            ctx["brow_area"] = [{"image": img}] if moved else None   # (makeup under the brows follows the hairs too)
            layer("brow_shadow", pre=True, color=_shade(col, 1.6) if sum(col) < 0.6 else col,
                  # shadow: x the skin-level shadow under the hairs. It is uniform over the landmark zone: a strong one fills the
                  # gaps between hairs (flat inside) and the sparse head (a blunt front): r5 / r6 brows read as a "solid
                  # sticker", skincheck brow inside spread ~half the photo's, front / middle ~.9 vs ~.45 (2026-10-16)
                  opacity=min((0.3 * min(dens, 1) + 0.06 + 0.45 * soft) * float(o.get("shadow", 1.0)), 0.9),
                  # with a fading head (brows.head) the landmark zone's even shadow drew a blunt grey stencil under the sparse
                  # inner hairs (Garrett r10): the shadow then follows the hairs' own density, blurred ~1.5 mm
                  mask=[{"image": dict(img, file=str(skin_swatch.blurred(path, 1.5 * 1024 / (width * 1000))))}]
                  if float(o.get("head", 0.0)) > 0 else [{"image": img}] if moved else _zones(["brow"], 0.9 * thick))
            # matte: a drawn picture of hairs shinier than the skin read as a grey, glossy bar with a hot highlight under a
            # studio catchlight (Tess s14: brow L 58-62 vs the photo's 34-36 although its colour was #2a1c12)
            # opacity: the hairs' cover (.95 default); lower = see-through, the skin between and under the hairs reads (r10: "near-black block")
            layer("brow_hairs", color=col, opacity=round(float(o.get("opacity", 0.95)) * (1 - 0.45 * soft), 3), roughness=0.68, specular=0.22, height=0.00012, image=img)
        o = _opt(h.get("lashes", 0.7 if ctx["eyes"] else None), "hair.lashes", ("color", "width"))
        if o:
            col = _hex(o["color"]) if "color" in o else _shade(dflt, 0.45)
            op = 0.9 * min(o["amount"] * (1 + 0.45 * ctx.get("fem", 0.0)) + 0.2, 1)
            cu = ctx.get("lash_curves")
            if cu:  # with lash geometry (lashes.py): only the roots' tone, a tight line along the lash line itself (the
                # margin zone's broad band painted the waterline and the lid's edge dark: the detector read the opening
                # 1.4 mm smaller than the clay's on Garrett)
                from .skin import _sp
                tubes = []
                # THE VISIBLE EYE (mouth_eye_bias -> skin, 2026-10-15): a photographed eye's width is its white plus the
                # lash line's dark frame, and that frame runs ON past the outer canthus (the lashes' roots, the lid
                # margins meeting, their shadow): ours stopped at the last lash and the eye read ~25 % short. So the
                # upper line is fullest over its outer third and goes on ~FRAME_PAST mm past the outer end along its own
                # tangent, tapering to a point; the lower line is darker than before (0.55 -> LOWER_FRAME)
                # width: x the line's radius (r4 measure: the RIM 0..1 mm outside the opening reads 3..27 L lighter than the
                # photo's on every head; the waterline alone moved it ~1.5 L: the dark frame has to reach that band)
                wd = float(o.get("width", 1.0))
                for lid, rad, wgt in (("upper", 0.0008 * wd, 1.0), ("lower", 0.0005 * wd, LOWER_FRAME)):
                    for c in cu[lid]:
                        c = np.asarray(c, float)
                        n = len(c)
                        if n < 3:
                            continue
                        out_end = abs(c[-1][0]) > abs(c[0][0])   # (the outer end: farther from the mid-line)
                        if not out_end:
                            c = c[::-1]
                        t = np.linspace(0.0, 1.0, n)
                        taper = 0.35 + 0.65 * np.sin(np.linspace(0.15, np.pi - 0.35, n)) ** 0.5
                        if lid == "upper":
                            taper = np.maximum(taper, np.clip((t - 0.55) / 0.3, 0, 1) * 1.15)   # fullest over the outer third
                            tan = c[-1] - c[-3]
                            tan /= max(float(np.linalg.norm(tan)), 1e-9)
                            ext = [c[-1] + tan * FRAME_PAST * k / 3 for k in (1, 2, 3)]
                            c = np.vstack([c, ext])
                            taper = np.concatenate([taper, [0.8, 0.5, 0.15]])
                        tubes.append({"mask": [_sp(c, rad * taper, soft=0.6, line=True)], "vertex": True,  # (per vertex: shader stack)
                                      **({"blend": "max"} if tubes else {}),
                                      **({"weight": wgt} if wgt < 1 else {})})
                layer("lashes", color=col, opacity=op, roughness=0.42, mask=tubes)
            else:
                layer("lashes", color=col, opacity=op, roughness=0.4,
                      mask=_zones(["lash_upper"]) + [{"zone": "lash_lower", "blend": "max", "weight": 0.5}])
        o = _opt(h.get("stubble"), "hair.stubble", ("color", "length", "size", "shadow", "shadow_color", "shadow_breakup", "grey", "grey_color",
                                                     "style", "density", "patchy", "trim", "cheeks", "cheek_line", "neckline", "engine", "zones", "count",
                                                     "contrast"))
        if o and o.get("engine", "map") == "map" and "lm_jaw_1.L" in J:
            _stubble_map(ctx["spec"], p, J, o, layer, T, ctx)
            o = None
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


SHADOW_GAIN = 1.6   # (0.85 before the shadow map carried the under-skin shafts' grain: its mean fell ~1/2)
CAST_DEPTH = 0.6   # the shafts seen through the skin are darker than the old even wash (gate: ref_30 / 29 / 28 beard - cheek)
CAST_SAT = 0.15   # its chroma kept (the rest goes to a neutral grey of the same luminance)


def stubble_options(o: dict, age: float = 35) -> dict:
    """hair.stubble's options resolved against its style (skin_marks.STUBBLE_STYLES)."""
    from . import skin_marks
    st = o.get("style", "short")
    if st not in skin_marks.STUBBLE_STYLES:
        raise SpecError(f"skin hair.stubble: style is one of {', '.join(skin_marks.STUBBLE_STYLES)}")
    base = dict(skin_marks.STUBBLE_STYLES[st])
    a = float(o["amount"])
    zw = o.get("zones") or {}
    if not isinstance(zw, dict) or set(zw) - set(skin_marks.BEARD_ZONES):
        raise SpecError(f"skin hair.stubble: zones is {{zone: weight}} over {', '.join(skin_marks.BEARD_ZONES)}")
    zw = {k: round(float(np.clip(v, 0, 1.5)), 3) for k, v in zw.items() if abs(float(v) - 1.0) > 1e-6}
    # count: hairs per area x (1 = ~80 / cm2 where full). density is a 0..1 share of that and saturates at 1 where the beard
    # is full, so it can't make a dense beard denser: Garrett's photo stubble covers ~.5 of the chin / jaw pixels, ours .2-.25
    # at density 1 (2026-10-16). Left out of the options at 1 so existing maps keep their cache keys.
    cnt = float(np.clip(o.get("count", 1.0), 0.25, 4.0))
    return {**({"zones": zw} if zw else {}), **({"count": round(cnt, 3)} if abs(cnt - 1.0) > 1e-6 else {}),
            "length": float(o.get("length", base["length"])), "density": float(np.clip(o.get("density", base["density"]) * min(a, 1.0), 0.02, 1.0)),
            "grey": float(np.clip(o.get("grey", 0.0), 0, 1)), "patchy": float(np.clip(o.get("patchy", base["patchy"]), 0, 1)),
            "trim": float(np.clip(o.get("trim", base["trim"]), 0, 1)), "cheeks": float(np.clip(o.get("cheeks", base["cheeks"]), 0, 1)),
            "cheek_line": float(o.get("cheek_line", 0.0)), "neckline": float(o.get("neckline", 0.0)),
            "size": float(o.get("size", 1.0)), "seed": int(o.get("seed", 0)), "shadow": float(o.get("shadow", base["shadow"]))}


def _stubble_map(spec, p, J, o, layer, T, ctx) -> None:
    """Stubble as a unique map on the head (skin_marks.stubble_map): the shadow of hair in the skin (per vertex,
    from the dark roots' count) + dark and white hairs as cut strokes along the growth direction, with relief."""
    from . import skin_marks
    t = p["tone"]
    a = float(o["amount"])
    q = stubble_options(o, p["age"])
    path, place, _ = skin_marks.stubble_map(spec, p["part"], J, q)
    col = _hex(o["color"]) if "color" in o else hair_default(t, p["age"])
    im = lambda ch: {"image": {"file": path, **place, "channel": ch}}  # noqa: E731
    lips = {"zone": {"name": "lips", "grow": 0.6}, "blend": "subtract"}   # (a crisp border: no bald halo round the lips)
    # hair seen through the skin: on light skin a cool blue-grey cast (the dark shaft under a scattering layer), on dark
    # skin just darker; the hair's own colour mixed in as it grows out
    # (a freshly shaved jaw: the cool cast; a few days' growth: the cut hairs at the surface warm it to a grey-brown, the
    # colour measured on Garrett's photo under the matched light: Lab ~45/4/13 at ~0.8 coverage)
    grow = float(np.clip(q["length"] / 0.001, 0, 1))
    # a fresh shave: dark hair under a scattering layer reads blue-grey, never olive (a greyed skin colour read as a
    # "dirty grey-green wash" to the blind reader): the skin darkened and pushed toward a cool blue-violet grey
    cool = np.array(T(grey=0.6, melanin=1.1)) * (0.58 + 0.22 * t["melanin"]) + np.array([0.08, 0.105, 0.125]) * (1 - t["melanin"])   # (neutral blue-grey: more blue read lilac)
    warm = np.array(T(grey=0.25, melanin=2.3, blood=1.05)) * (0.62 + 0.25 * t["melanin"])   # (warm grey: less read as green)
    cast = (1 - 0.35 * grow) * cool + 0.35 * grow * warm + 0.06 * grow * (np.array(col) - 0.3)   # the sub-skin shadow stays cool: the hairs carry the warmth
    lum = float(cast @ np.array([0.2126, 0.7152, 0.0722]))
    cast = lum + CAST_SAT * (cast - lum)   # (beard minus cheek: a and b fall 3-14 on the refs, ~1 on ours before)
    cast = [round(float(c), 4) for c in np.clip(CAST_DEPTH * cast, 0, 1)]
    cast = _hex(o["shadow_color"]) if "shadow_color" in o else cast
    # (per pixel, not pre-composited per vertex: the shadow map carries the under-skin shafts, ~0.2 mm across)
    layer("stubble_shadow", o.get("mask"), color=cast, opacity=round(min(SHADOW_GAIN * min(a, 1.3) * q["shadow"], 0.95), 3),
          mask=[im("b"), lips])
    hgt = round(float(np.clip(0.00003 + 0.012 * q["length"], 0.00003, 0.00012)), 7)   # a hair stands ~0.1 mm proud
    r = min(ctx["base_r"] + 0.1, 0.9)
    # contrast: x the hairs' cover (1). A few days' grey stubble seen from a metre is a fine grey-brown HAZE: single hairs are
    # sub-texel, so each pixel is a low-contrast mix of skin and hair; opaque hairs read as white specks (grey) or black
    # pepper (dark) (Garrett r12). The haze's tone is then the shadow (shadow_color, shadow) under many faint hairs (count)
    k_ = float(np.clip(o.get("contrast", 1.0), 0.05, 1.0))
    layer("stubble", o.get("mask"), color=col, opacity=round(0.97 * k_, 3), roughness=r, specular=0.35, height=hgt, mask=[im("r"), lips])
    if q["grey"] > 0:
        # (white hairs near-white and opaque: #aaa39a at 0.85 was ~+14 L over the skin, "salt & pepper has no white in
        # it" (5th blind read; ref_28's white hairs are the brightest thing on the jaw). The shadow under the dark ones
        # now carries the darkening (shafts under the skin), so near-white no longer reads as ash, skin3)
        # (then "uniform bright chalk scratches", skin3's 6th read: real grey hair is translucent and a little yellow,
        # #d9d4cb at .95 -> #c8c0b2 at .8)
        layer("stubble_grey", o.get("mask"), color=_hex(o.get("grey_color", "#c8c0b2")), opacity=round(0.8 * k_, 3), roughness=r, specular=0.4,
              height=hgt, mask=[im("g"), lips])


def freckle_options(o: dict) -> dict:
    from . import skin_marks
    z = dict(skin_marks.FRECKLE_ZONES)
    zo = o.get("zones") or {}
    if not isinstance(zo, dict) or set(zo) - set(z):
        raise SpecError(f"skin features.freckles: zones is {{zone: weight}} over {', '.join(z)}")
    z.update({k: float(v) for k, v in zo.items()})
    return {"amount": float(np.clip(o["amount"], 0, 3)), "size": float(o.get("size", 0.0004)), "clump": float(np.clip(o.get("clump", 0.6), 0, 1)),
            "dark": float(np.clip(o.get("dark", 0.2), 0, 1)), "moles": 0, "zones": z, "seed": int(o.get("seed", 0))}


def _freckle_map(spec, p, J, o, layer, T, ctx) -> None:
    """Freckles on the face as a unique map (skin_marks.freckle_map: irregular macules, clustered, where the sun falls),
    on the body (shoulders, forearms, the chest's V) from the freckle swatch at two sizes mixed (vary: no repeat)."""
    from . import skin_marks
    t = p["tone"]
    dark = t["melanin"]
    show = ctx["show"]
    a = float(o["amount"])
    q = freckle_options(o)
    path, place, _ = skin_marks.freckle_map(spec, p["part"], J, q)
    im = lambda ch: {"image": {"file": path, **place, "channel": ch}}  # noqa: E731
    # ephelides: more melanin in the same skin (light tan to brown on fair skin; on dark skin hardly a change)
    # (one layer: each freckle's darkness is its value in the map, faint tan to brown)
    layer("freckles", o.get("mask"), color=T(melanin=3.2 + 2.0 * (1 - dark), blood=1.7, oxygenation=0.8), opacity=round(min(0.75 + 0.12 * a, 0.95) * show, 3), mask=[im("r")])
    body = [z for z in ("shoulder", "forearm", "chest") if _has(z, ctx)] + (["collarbone"] if ctx["torso"] else [])
    if body:
        lo = float(np.clip(0.42 - 0.3 * min(a, 1.2), 0.04, 0.6))
        k = q["size"] / 0.0016
        layer("freckles_body", o.get("mask"), color=T(melanin=2.6 + 1.6 * (1 - dark), blood=1.3), opacity=min(0.4 + 0.3 * a, 0.75) * show,
              mask=[{"tile": {"swatch": "freckles", "size": round(0.042 * k, 5), "range": [round(lo, 3), round(lo + 0.55, 3)], "vary": True, "rotate": True}},
                    {"vertex": True, "mask": _zones(body)}])


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
