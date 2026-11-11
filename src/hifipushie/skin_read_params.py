"""What the fit may set: bounds, groups, sigmas, and getting / setting a parameter by its path. Part of the skin read (skin_read.py has the overview)."""
from __future__ import annotations

# ---------------------------------------------------------------- the fit
BOUNDS = {"tone.melanin": (0.0, 1.0), "tone.blood": (0.0, 1.0), "tone.undertone": (-1.0, 1.0),
          "zones.forehead_yellow": (0.0, 3.0), "zones.midface_red": (0.0, 3.0), "zones.nose_red": (0.0, 3.0),
          "zones.perioral_red": (0.0, 3.0), "zones.lower_cool": (0.0, 2.0), "zones.under_eye": (0.0, 2.5),
          "zones.eyelids": (0.0, 2.5), "zones.periorbital": (0.0, 1.5), "features.flush": (0.0, 1.5),
          # (lips.melanin is x the TONE's melanin: on a very fair tone a dark lip needs 10-20. At 9, and lower.melanin no
          # lower than 0.4, Garrett's upper lip stayed 11 L lighter than the painting's: the "stuck" lips. skinfolds)
          "lips.blood": (0.15, 3.0), "lips.melanin": (0.2, 30.0), "lips.lower.blood": (0.3, 2.5), "lips.lower.melanin": (0.1, 2.5), "lips.strength": (0.4, 1.6),
          }
GROUPS = {"tone": ("tone.melanin", "tone.blood", "tone.undertone"),
          "zones": ("zones.forehead_yellow", "zones.midface_red", "zones.nose_red", "zones.perioral_red", "zones.lower_cool",
                    "features.flush"),
          "eyes": ("zones.under_eye", "zones.eyelids", "zones.periorbital"),
          "lips": ("lips.blood", "lips.melanin", "lips.strength", "lips.lower.blood", "lips.lower.melanin"),
          "stubble": (), "brows": (), "freckles": (), "eyeballs": (), "folds": ()}
# ("eyeballs", the iris colour, was not a default until 2026-10-13: on Tess's photographs it turned grey-green irises
# orange-brown: the picture's sclera sits in lid shadow, and the change was clipped per channel. Now read against the
# sclera's bright part with the hue kept (iris_colour): in the default set, so a head no longer keeps the default brown)
DEFAULT_GROUPS = ("tone", "zones", "eyes", "lips", "stubble", "brows", "freckles", "folds", "eyeballs")
SIGMA = (6.0, 0.8, 0.8)     # Lab: what a region's read is worth (lightness carries the shading we do not model)
EXPOSURE = 0.08           # log units: how closely the picture's unknown exposure is held to our skin's lightness. At 0.5
                          # (free) the tone ran DARK: the pigment model reaches a picture's chroma most cheaply by adding
                          # melanin (validation: melanin 0.48 for a truth of 0.30; Garrett came out a tanned
                          # orange-brown). Held, it still runs dark when the picture's skin is far more saturated than the
                          # start (validation: 0.54), stays within ~3 L on the two subjects. The tone's lightness is NOT
                          # a read: check it by eye.
# (also tried: holding the base tone's own L to 1.5. On the far synthetic truth the solve then bent the zones to find the
# chroma: perioral 2.8, flush 1.26, no beard. Taken out.)
BEARD_EVEN = 0.6          # the beard's zone scales are held to their mean this loosely (side zones read lightness, the least
                          # trusted number; free, a jaw at 1 beside cheeks at 0 drew a band with an edge)

LIP_SIGMA_L = 2.5         # the lips' lightness is theirs (a small region, read whole): trusted more than the skin's
IRIS_MM = 0.5             # mm a picture pixel: coarser, an iris is a handful of pixels of lid shadow (Garrett's read x 2)
BROW_COLOUR_MM = 0.8      # coarser, a brow's darkest third is half skin: its colour is not read (its density is)
FIT_POINTS = 50000         # the solve's points (region means do not need every pixel)
PRIOR = 0.04                # the pull back to the start, per share of a parameter's range (least change)
STUBBLE_PROTO = {"amount": 1.0, "style": "short"}
BEARD_MIN = 0.08            # a fitted beard weaker than this share of the prototype is no beard


def _get(sk: dict, path: str):
    from . import skin as skinmod
    a, _, b = path.partition(".")
    if a == "tone":
        return skinmod.tone_params(sk.get("tone"))[b]
    if a == "zones":
        return float((sk.get("zones") or {}).get(b, skinmod.ZONE_LAYERS[b]))
    if path == "features.flush":
        v = (sk.get("features") or {}).get("flush")
        return float(v if isinstance(v, (int, float)) else (v or {}).get("amount", 1.0 if v else 0.0)) if v else 0.0
    if path == "hair.lashes":
        v = (sk.get("hair") or {}).get("lashes", 0.7)
        return float(v if isinstance(v, (int, float)) else (v or {}).get("amount", 1.0)) if v else 0.0
    if a == "lips":
        lp = sk.get("lips") or {}
        return float((lp.get("lower") or {}).get(b[6:], 1.0)) if b.startswith("lower.") else float(lp.get(b, 1.0))
    raise KeyError(path)


def _set(sk: dict, path: str, x: float) -> None:
    from . import skin as skinmod
    a, _, b = path.partition(".")
    x = round(float(x), 4)
    if a == "tone":
        t = skinmod.tone_params(sk.get("tone"))
        t[b] = x
        sk["tone"] = {k: round(float(v), 4) for k, v in t.items()}
    elif a == "zones":
        sk.setdefault("zones", {})[b] = x
    elif path == "features.flush":
        f = sk.setdefault("features", {})
        if isinstance(f.get("flush"), dict):
            f["flush"] = {**f["flush"], "amount": x}
        else:
            f["flush"] = x
        if x <= 0.005:
            f.pop("flush", None)
    elif path == "hair.lashes":
        h = sk.setdefault("hair", {})
        h["lashes"] = {**h["lashes"], "amount": x} if isinstance(h.get("lashes"), dict) else x
    elif a == "lips":
        lp = sk.setdefault("lips", {})
        if b.startswith("lower."):
            lp.setdefault("lower", {})[b[6:]] = x
        else:
            lp[b] = x


def _stubble_opts(sk: dict):
    v = (sk.get("hair") or {}).get("stubble")
    if not v:
        return None
    return {"amount": float(v)} if isinstance(v, (int, float)) else dict(v)


def _path_set(sk: dict, path: str) -> bool:
    a, _, b = path.partition(".")
    d = sk.get(a) or {}
    if a == "tone":
        return True
    if b.startswith("lower."):
        return b[6:] in (d.get("lower") or {})
    return b in d


def _unset(sk1: dict, sk0: dict, path: str) -> None:
    """A parameter the fit left where it was and the description never named: take it out again."""
    a, _, b = path.partition(".")
    d = sk1.get(a)
    if not isinstance(d, dict):
        return
    if b.startswith("lower."):
        (d.get("lower") or {}).pop(b[6:], None)
        if "lower" in d and not d["lower"]:
            d.pop("lower")
    else:
        d.pop(b, None)
    if not d and a not in sk0:
        sk1.pop(a, None)
