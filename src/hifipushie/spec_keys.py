"""The keys a joint, a bone and a blob take: anything else is refused before the spec is saved (C442).

Why: paint, style, walls and scatter refuse an unknown key with the list of the known ones; joints, bones and blobs,
the first things an agent writes, took any key in silence: "sizee", "radius", "offest" saved, compiled and built a
default-sized ellipsoid at the origin of its joint, and nothing said why the edit changed nothing. The lists are every
key the code reads off these elements (spec.py's compile and its shapes, softforms.py, sheet.py, assemble_*.py); on
2026-11-12 all 21,751 saved specs (models and their histories) used only keys from them, so the refusal breaks none.

check(spec): SpecError naming the element, the key, the nearest known key and the list. Run by store.validate on the
spec as written (before kits, strokes and anatomy expand it: what they generate is theirs).
"""
from __future__ import annotations

import difflib

JOINT_KEYS = ("pos", "r", "on", "lift", "shift")
BONE_KEYS = ("a", "b", "r_a", "r_b", "flat", "bow", "up", "blend", "op", "layer", "group", "join", "part", "ends",
             "lumpy", "tags", "array", "between", "inset", "targets")
BLOB_KEYS = (
    "at", "offset", "size", "rot", "shape", "blend", "op", "layer", "group", "join", "part", "tags", "array", "targets",
    "between", "inset",
    "round", "hollow", "ends", "chips", "lumpy",                                  # box, cylinder, blade
    "squareness", "exponents",                                                    # super
    "sections", "bottom", "top", "cup", "taper",                                  # loft
    "spine", "curve", "stations", "root", "tip", "width_axis", "fold", "bend", "thickness", "hand",  # sheet
    "upper", "lower", "r", "width",                                               # lids
    "lean", "fall", "points", "spread", "spread_back", "gap", "stand_gap",        # collar
    "path", "profile", "values", "lip", "mirror", "open_start",                   # sweep
    "pts", "nrm", "depth", "height", "soft",                                      # displace, flatten
    "instance", "local")                                                          # an element of a prefab's instance
KEYS = {"joints": ("joint", JOINT_KEYS), "bones": ("bone", BONE_KEYS), "blobs": ("blob", BLOB_KEYS)}


def unknown(spec: dict) -> list[tuple[str, str, str]]:
    """[(kind, element name, key)] for every key of a joint, bone or blob that is not in its list."""
    out = []
    for kind, (_, known) in KEYS.items():
        for name, el in (spec.get(kind) or {}).items():
            if isinstance(el, dict):
                out += [(kind, name, k) for k in el if k not in known]
    return out


def check(spec: dict) -> None:
    from .spec import SpecError
    bad = unknown(spec)
    if not bad:
        return
    kind, name, key = bad[0]
    what, known = KEYS[kind]
    near = difflib.get_close_matches(str(key), known, n=1, cutoff=0.6)
    more = f" ({len(bad) - 1} more unknown key(s): " + ", ".join(f"{n}.{k}" for _, n, k in bad[1:4]) + ")" if len(bad) > 1 else ""
    raise SpecError(f"{what} {name!r}: unknown key {key!r}" + (f" (did you mean {near[0]!r}?)" if near else "") + more +
                    f". A {what} takes: {', '.join(known)}. Nothing was saved; kit_reference describes each shape's own keys")
