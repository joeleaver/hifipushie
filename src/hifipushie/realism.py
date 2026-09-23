"""Imperfection: the model's story, and an audit that flags what looks too perfect to be real.

Nothing real is pristine: things are old, used, weathered, repaired, set down carelessly. Every model gets a
spec["story"], and every imperfection should follow from it, so detail is coherent instead of random noise:

  "story": {"summary": "a trapper's cabin, built 30 years ago, lived in every winter since",
            "age": 30 (years),
            "climate": "wet mountain forest, heavy snow",
            "use": "one man and a dog; cooks and dries furs indoors",
            "directions": {"weather": [0.3, 1, 0.2], "sun": [0, -1, 0.8]},   (named world directions)
            "events": ["the roof leaked over the stove corner", "the dog sleeps on the rug by the stove",
                       "the north wall takes the weather", "the porch step was replaced last year"]}

Directions named here can be used by paint wherever a direction is taken: {"facing": "weather"} wets and
darkens the weather side, {"facing": "sun"} bleaches the sunny side. Everything else is for you: turn each event
into geometry (weather ops, lumpy, chips, bow, a moved chair) and paint (grime, wear paths, soot, drips).

Restraint: weathering should be noticed second, after the form. Real sag is centimetres over metres, a
lean a degree or so, furniture a few degrees off square, grime and bleaching a shift of tone rather than a new
colour (layer opacities ~0.15-0.3). Push it until it reads, then back off by a third.

check(name) runs audit(): it warns about a missing story, arrays of identical copies at even spacing, things
lined up with the world axes, identical repeated parts, big flat surfaces with no deviation, and paint without
wear or dirt. Warnings are prompts, not rules: a machined part should be perfect; a log wall shouldn't.
"""

from __future__ import annotations

import numpy as np

from .spec import SpecError

STORY_KEYS = ("summary", "age", "climate", "use", "directions", "events")


def validate(spec: dict) -> None:
    st = spec.get("story")
    if st is None:
        return
    if not isinstance(st, dict):
        raise SpecError("story is an object: {\"summary\", \"age\", \"climate\", \"use\", \"directions\", \"events\"}")
    unknown = set(st) - set(STORY_KEYS)
    if unknown:
        raise SpecError(f"story: unknown keys {sorted(unknown)} (have {', '.join(STORY_KEYS)})")
    for k, v in (st.get("directions") or {}).items():
        if not (isinstance(v, list) and len(v) == 3 and np.linalg.norm(np.asarray(v, float)) > 0):
            raise SpecError(f"story.directions.{k}: a direction is [x, y, z]")


def direction(spec: dict, d, what: str) -> np.ndarray:
    """A direction given as [x, y, z] or as the name of one of the story's directions, as a unit vector."""
    if isinstance(d, str):
        dirs = (spec.get("story") or {}).get("directions") or {}
        if d not in dirs:
            raise SpecError(f"{what}: no story direction {d!r} (story.directions has {sorted(dirs)})")
        d = dirs[d]
    v = np.asarray(d, float)
    return v / np.linalg.norm(v)


def summary(spec: dict) -> str:
    st = spec.get("story")
    if not st:
        return "story: NONE (see check: every model needs one)"
    bits = [st.get("summary", "")]
    for k in ("age", "climate", "use"):
        if k in st:
            bits.append(f"{k}: {st[k]}")
    if st.get("events"):
        bits.append(f"{len(st['events'])} events")
    return "story: " + "; ".join(b for b in bits if b)


def audit(spec: dict) -> list[str]:
    """Warnings about perfection, most important first."""
    from .assemble import expand as assemble
    out = []
    st = spec.get("story")
    if not st:
        out.append("NO STORY: write spec['story'] (age, climate, use, directions, events) and let every "
                   "imperfection follow from it (realism docs in kit_reference)")
    elif not st.get("events"):
        out.append("the story has no events: what happened to this thing? (leaks, repairs, favourite spots, "
                   "damage, what faces the weather)")

    arrays = [(k, n, el) for k in ("bones", "blobs") for n, el in (spec.get(k) or {}).items() if "array" in el]
    for k, n, el in arrays:
        steps = el["array"] if isinstance(el["array"], list) else [el["array"]]
        count = int(np.prod([int(s.get("count", 1)) for s in steps]))
        varied = any(s.get("jitter") or s.get("vary") or s.get("flip") for s in steps) or el.get("lumpy")
        if count >= 3 and not varied:
            out.append(f"array {n!r}: {count} identical copies at exactly even spacing (add vary / jitter / "
                       f"flip, or lumpy): nothing made or grown is that regular")

    by_prefab: dict[str, list] = {}
    turned = set()  # tags that weather ops turn or tilt
    for w in spec.get("weather") or []:
        if (w.get("jitter") or {}).get("rot") or w.get("lean"):
            turned |= set(w.get("tags") or [])
    for inst, d in (spec.get("instances") or {}).items():
        if not ({inst, d.get("use"), *d.get("tags", [])} & turned):
            by_prefab.setdefault(d.get("use"), []).append((inst, d))
    for pf, insts in by_prefab.items():
        rots = [np.asarray(d.get("rot", [0, 0, 0]), float) for _, d in insts]
        aligned = [inst for (inst, _), r in zip(insts, rots) if np.all(np.abs(((r + 45) % 90) - 45) < 0.5)]
        if len(aligned) >= 2 and len(aligned) == len(insts):
            out.append(f"instances of {pf!r} ({', '.join(a for a, _ in insts)}) are all square to the world axes: "
                       f"things in use get pushed, pulled out and knocked askew (turn them a few degrees)")

    try:
        s = assemble(spec)
    except SpecError:
        s = spec
    sizes: dict[tuple, list] = {}
    for n, bl in (s.get("blobs") or {}).items():
        if bl.get("op", "add") != "add" or bl.get("lumpy") or bl.get("chips") or "/" in n:
            continue  # (prefab copies are the same by design: the prefab's own arrays are checked above)
        key = (bl.get("shape", "ellipsoid"), tuple(round(float(x), 4) for x in bl.get("size", [0.05] * 3)),
               bl.get("part", "body"))
        sizes.setdefault(key, []).append(n)
    for (shape, size, part), names in sizes.items():
        if len(names) >= 4 and shape != "lids":
            out.append(f"{len(names)} {shape}s in part {part!r} are exactly the same size {list(size)} "
                       f"({', '.join(names[:4])}{', ...' if len(names) > 4 else ''})")
    for n, bl in (s.get("blobs") or {}).items():
        if bl.get("shape") == "box" and bl.get("op", "add") == "add" and not (bl.get("lumpy") or bl.get("chips")):
            sz = np.asarray(bl.get("size", [0.05] * 3), float)
            if np.sort(sz)[-2] > 0.4:
                out.append(f"box {n!r} has a flat face {2 * np.sort(sz)[-1]:.1f} x {2 * np.sort(sz)[-2]:.1f} m with no "
                           f"deviation: floors sag, walls bow, stone is uneven (lumpy, chips, or strokes)")

    paint = spec.get("paint") or {}
    if s.get("bones") or s.get("blobs"):
        if not paint:
            out.append("no paint: even a clay study reads better with dirt in the creases and wear on the edges")
        else:
            def weathered(ly):
                keys = set(ly) | {g for e in (ly.get("mask") or []) if isinstance(e, dict) for g in e}
                return bool(keys & {"ao", "cavity", "breakup"}) or ("material" in ly and
                                                                    (ly.get("wear", 0.5) or ly.get("dirt", 0.5)))
            if not any(weathered(ly) for ly in paint.values()):
                out.append("paint has no wear or dirt (no ao / cavity / breakup layers, no material with wear): "
                           "grime in the corners, worn edges, traffic paths, soot")
    return out
