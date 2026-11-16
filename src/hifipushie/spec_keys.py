"""The keys a joint, a bone and a blob take: anything else is refused before the spec is saved (C442).

Why: paint, style, walls and scatter refuse an unknown key with the list of the known ones; joints, bones and blobs,
the first things an agent writes, took any key in silence: "sizee", "radius", "offest" saved, compiled and built a
default-sized ellipsoid at the origin of its joint, and nothing said why the edit changed nothing. The lists are every
key the code reads off these elements (spec.py's compile and its shapes, softforms.py, sheet.py, assemble_*.py); on
2026-11-12 all 21,751 saved specs (models and their histories) used only keys from them, so the refusal breaks none.

check(spec): SpecError naming the element, the key, the nearest known key and the list. Run by store.validate on the
spec as written (before kits, strokes and anatomy expand it: what they generate is theirs). The elements inside
prefabs are checked the same way (spec["prefabs"][name]: joints, bones, blobs), named with their prefab.

GENERIC: the keys every bone and blob takes (spec_hands._csg and the assemble modules read them off any element). C442's
bone list missed two of them, "hollow" and "chips": no saved top-level spec had a hollow bone, 110 bones inside saved
prefabs did, and a list read off the saved specs alone would have refused the next one. A test now holds every key
spec.py reads off an element to both lists.
"""
from __future__ import annotations

import difflib

JOINT_KEYS = ("pos", "r", "on", "lift", "shift")
GENERIC = ("blend", "op", "layer", "group", "join", "fuse", "fill", "fill_sides", "part", "tags", "array", "between", "inset", "targets",
           "lumpy", "chips", "hollow",  # element-level solids (spec_hands._csg): on bones and shaped blobs
           "instance", "local")         # an element of a prefab's instance (written by the expansion)
BONE_KEYS = ("a", "b", "r_a", "r_b", "flat", "bow", "up", "ends", "flap", *GENERIC)
BLOB_KEYS = (
    "at", "offset", "size", "rot", "aim", "shape", *GENERIC,
    "round", "ends",                                                              # box, cylinder, blade
    "squareness", "exponents",                                                    # super
    "sections", "bottom", "top", "cup", "taper",                                  # loft
    "spine", "curve", "stations", "root", "tip", "width_axis", "fold", "bend", "thickness", "hand",  # sheet
    "upper", "lower", "r", "width",                                               # lids
    "lean", "fall", "points", "spread", "spread_back", "gap", "stand_gap",        # collar
    "path", "profile", "values", "lip", "mirror", "open_start",                   # sweep
    "pts", "nrm", "depth", "height", "soft", "only")                              # displace, flatten
KEYS = {"joints": ("joint", JOINT_KEYS), "bones": ("bone", BONE_KEYS), "blobs": ("blob", BLOB_KEYS)}


def unknown(spec: dict) -> list[tuple[str, str, str, str | None]]:
    """[(kind, element name, key, prefab name | None)] for every key of a joint, bone or blob that is not in its
    list: the spec's own elements, then each prefab's."""
    out = []
    pfs = spec.get("prefabs")
    homes = [(None, spec)] + [(pn, pf) for pn, pf in (pfs.items() if isinstance(pfs, dict) else ()) if isinstance(pf, dict)]
    for pn, home in homes:
        for kind, (_, known) in KEYS.items():
            els = home.get(kind)
            for name, el in (els.items() if isinstance(els, dict) else ()):  # (a section of the wrong type is the compile's to refuse)
                if isinstance(el, dict):
                    out += [(kind, name, k, pn) for k in el if k not in known]
    return out


def check(spec: dict) -> None:
    from .spec import SpecError
    bad = unknown(spec)
    if not bad:
        return
    kind, name, key, prefab = bad[0]
    what, known = KEYS[kind]
    near = difflib.get_close_matches(str(key), known, n=1, cutoff=0.6)
    more = f" ({len(bad) - 1} more unknown key(s): " + ", ".join(f"{n}.{k}" for _, n, k, _ in bad[1:4]) + ")" if len(bad) > 1 else ""
    raise SpecError((f"prefab {prefab!r}: " if prefab else "") + f"{what} {name!r}: unknown key {key!r}" +
                    (f" (did you mean {near[0]!r}?)" if near else "") + more +
                    f". A {what} takes: {', '.join(known)}. Nothing was saved; kit_reference describes each shape's own keys")
