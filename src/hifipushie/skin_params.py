"""The description's parameters: groups, the age curve, `params`, shading, a part's base colour, roughness. Part of skin (skin.py has the spec)."""
from __future__ import annotations

import numpy as np

from . import skin
from .spec import SpecError
from .skin import tone_params, tone_rgb

def group_of(layer: str) -> str:
    """Which group of the description (skin.only) a layer "skin:<name>" belongs to."""
    n = layer[5:] if layer.startswith("skin:") else layer
    if n.startswith(("eye_L", "eye_R", "eye_shade", "eye_tear", "eye_canthus")):
        return "eyes"
    if n in ("caruncle", "waterline", "canthus"):
        return "eye_rims"
    if n.startswith(("lips_", "lip_")) or n == "micro_lip_lines":
        return "lips"
    if n.startswith("rough_"):
        return "roughness"
    if n.startswith("micro_"):
        return "micro"
    if n in skin.ZONE_LAYERS or n.startswith("mottle_"):
        return "zones"
    return "features"


def _age_curve(age: float, a0: float, a1: float) -> float:
    """0 before a0, 1 from a1 on (smooth)."""
    t = float(np.clip((age - a0) / max(a1 - a0, 1e-9), 0, 1))
    return t * t * (3 - 2 * t)


def params(spec: dict) -> dict:
    """spec["skin"] with every default filled in (validated)."""
    sk = spec.get("skin") or {}
    if not isinstance(sk, dict):
        raise SpecError("skin is an object: {\"tone\": {...}, \"age\": ...}")
    bad = set(sk) - skin.KEYS
    if bad:
        raise SpecError(f"skin: unknown keys {sorted(bad)} (have {', '.join(sorted(skin.KEYS))})")
    age = float(sk.get("age", 30))
    if not 0 <= age <= 120:
        raise SpecError("skin age is in years")
    p = {"part": sk.get("part", "body"), "tone": tone_params(sk.get("tone")), "age": age, "seed": int(sk.get("seed", 0))}
    sx = sk.get("sex")
    if sx is not None and not 0 <= float(sx) <= 1:
        raise SpecError("skin sex is 0 (female) .. 1 (male)")
    p["fem"] = 0.0 if sx is None else float(np.clip(1 - 2 * float(sx), 0, 1))
    p["masc"] = 0.0 if sx is None else float(np.clip(2 * float(sx) - 1, 0, 1))
    for k, d in (("variation", 1.0), ("detail", 1.0), ("oil", 0.5), ("thin", 0.5), ("sun", 0.3)):
        p[k] = float(sk.get(k, d))
        if not 0 <= p[k] <= 3:
            raise SpecError(f"skin {k} is a number 0..1 (up to 3 to exaggerate)")
    z = sk.get("zones") or {}
    bad = set(z) - set(skin.ZONE_LAYERS)
    if bad:
        raise SpecError(f"skin zones: unknown {sorted(bad)} (have {', '.join(skin.ZONE_LAYERS)})")
    p["zones"] = {**skin.ZONE_LAYERS, **{k: float(v) for k, v in z.items()}}
    zc = sk.get("zone_colors") or {}
    bad = set(zc) - set(skin.ZONE_LAYERS)
    if bad:
        raise SpecError(f"skin zone_colors: unknown {sorted(bad)} (have {', '.join(skin.ZONE_LAYERS)})")
    for k, v in zc.items():
        if not (isinstance(v, (list, tuple)) and len(v) == 3 and all(0 <= float(c) <= 1 for c in v)):
            raise SpecError(f"skin zone_colors.{k} is [r, g, b], each 0..1")
    p["zone_colors"] = {k: [float(c) for c in v] for k, v in zc.items()}
    lips = sk.get("lips") or {}
    bad = set(lips) - {"blood", "melanin", "roughness", "dry", "lower", "gradient", "border", "strength", "rim_lower", "under_shade", "over_stack", "sheen", "specular"}
    low = lips.get("lower") or {}
    if bad or not isinstance(low, dict) or set(low) - {"blood", "melanin"}:
        raise SpecError(f"skin lips: unknown keys {sorted(bad)} (have blood, melanin, roughness, dry, gradient, border, strength, lower: {{blood, melanin}})")
    p["lips"] = {"blood": float(lips.get("blood", 1.0)), "melanin": float(lips.get("melanin", 1.0)),
                 "roughness": float(lips.get("roughness", 0.36)), "dry": float(lips.get("dry", 0.0)),
                 # sheen: the lower lip's pad roughness (default lips.roughness - .1, never below .24: the pad paints over the
                 # lower lip's own roughness, so lips.roughness under .34 never reached the highlight; r10 2026-10-18);
                 # specular: the pad's and the lower lip's specular level (None: the skin's)
                 "sheen": (float(lips["sheen"]) if lips.get("sheen") is not None else None),
                 "specular": (float(lips["specular"]) if lips.get("specular") is not None else None),
                 "strength": float(np.clip(lips.get("strength", 1.0), 0.2, 2.0)),
                 "gradient": float(np.clip(lips.get("gradient", 1.0), 0, 2.5)), "border": float(np.clip(lips.get("border", 1.5), 0.3, 4.0)),
                 "rim_lower": float(np.clip(lips.get("rim_lower", skin.RIM_LOWER), 0.0, 1.0)),
                 "under_shade": float(np.clip(lips.get("under_shade", skin.UNDER_SHADE), 0.0, 2.0)),
                 "lower": {"blood": float(low.get("blood", 1.0)), "melanin": float(low.get("melanin", 1.0))}}
    sh = sk.get("shading") or {}
    bad = set(sh) - {"subsurface", "radius", "scale", "specular", "roughness", "coat", "coat_roughness", "sheen", "thickness", "rough_breakup"}
    if bad:
        raise SpecError(f"skin shading: unknown keys {sorted(bad)} (have subsurface, radius, scale, specular, roughness)")
    p["shading"] = sh
    for k in ("features", "wrinkles", "hair", "makeup", "nails", "eyes", "folds"):
        p[k] = sk.get(k) or {}
        if not isinstance(p[k], dict):
            raise SpecError(f"skin {k} is an object")
    for k in ("scars", "tattoos"):
        p[k] = sk.get(k) or []
        if not isinstance(p[k], list):
            raise SpecError(f"skin {k} is a list")
    from . import skin_project_model
    p["projection"] = skin_project_model.check(sk.get("projection"))
    from . import skin_layers
    p["stack"] = skin_layers.check(sk.get("stack"))
    only = sk.get("only")
    if only is not None:
        only = [only] if isinstance(only, str) else list(only)
        bad = [g for g in only if g not in skin.GROUPS]
        if bad or not only:
            raise SpecError(f"skin only: a list of groups to lay, of {', '.join(skin.GROUPS)} (got {sk.get('only')!r})")
    p["only"] = only
    return p


def shaded(spec: dict) -> bool:
    """Whether the description sets the skin part's shading (not with skin.only lacking "shading")."""
    only = (spec.get("skin") or {}).get("only")
    return bool(spec.get("skin")) and (only is None or "shading" in ([only] if isinstance(only, str) else only))


def part_base(spec: dict) -> tuple[str, dict] | None:
    """(the skin part, its base channels): the tone's colour, roughness, specular and subsurface. Values the part's
    own definition gives win."""
    if not spec.get("skin") or not shaded(spec):
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
                       "coat": float(sh.get("coat", 0.01 + 0.03 * p["oil"])),   # (0.015 + 0.07 x oil: a wet, plastic cheek under raking light)
                       "coat_roughness": float(sh.get("coat_roughness", 0.34)),
                       "sheen": float(sh.get("sheen", 0.12)), "sheen_roughness": 0.5,
                       "thickness": float(sh.get("thickness", 0.007)),  # light comes through what is thinner (ears, nostrils)
                       "_old": old}


def _roughness(p: dict) -> float:
    child = 1 - _age_curve(p["age"], 6, 18)
    return float(np.clip(0.49 - 0.05 * (p["oil"] - 0.5) + 0.06 * _age_curve(p["age"], 45, 85) - 0.03 * child, 0.2, 0.9))


def _z(*names, grow=1.0) -> list:
    """A mask stack: the union of zones."""
    return [{"zone": {"name": n, "grow": grow}, **({"blend": "max"} if i else {})} for i, n in enumerate(names)]
