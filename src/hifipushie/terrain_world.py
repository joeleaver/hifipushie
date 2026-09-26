"""The world a level pretends to be, and how much it's compressed.

A level has three scales: the *implied world* (the kind of terrain the brief names, at its real size), the *level's
footprint* (a compressed version of it: game levels shrink distances), and the *player* (exact: a 1.8 m person, 15 m
trees, 3 m tracks). Proportions come from the kind, compressed; detail (erosion depth, bumps, crags) and gameplay stay
at player scale and are never compressed. Mixing them made 25 m erosion trenches and 58 deg "mountainsides".

"world": {"kind": "alpine valley", "compression": "auto" | number, "base": m}
  compression "auto": footprint / the kind's real width (1 if the frame is at least that big). Heights compress less
  (by the square root), so mountains still feel tall; the steepness that costs goes into cliff bands.

The reference ranges are rough, from general geomorphology (typical, not extremes), and meant to be refined.
"""

from __future__ import annotations

import math
import zlib

PLAYER = {"eye": 1.7, "walk_grade": 0.15, "tree": 15.0, "track": 3.0}

# across: real width range and typical (m); relief: real range and typical (m); face: typical slope of the main
# slopes (deg) and its plausible range; steep: share of ground over 45 deg in the real thing; floor: share of the
# frame that's floor/low ground; game: typical level footprint (m) when the size isn't given.
# Detail at player scale (m, never compressed): bumps = surface roughness amplitude, gully = erosion depth,
# crag = size of rock features.
KINDS = {
    "alpine_valley": dict(across=(4000, 12000, 7000), relief=(800, 2000, 1200), face=(32, 25, 40), steep=0.12,
                          floor=0.25, game=4000, bumps=3.0, gully=8.0, crag=40.0,
                          words=("alpine valley", "mountain valley", "valley", "alpine", "mountains", "glen")),
    "cirque": dict(across=(800, 3000, 1500), relief=(300, 800, 500), face=(38, 30, 50), steep=0.25, floor=0.25,
                   game=1200, bumps=3.0, gully=6.0, crag=30.0,
                   words=("cirque", "corrie", "tarn", "mountain lake", "bowl")),
    "canyon": dict(across=(500, 4000, 1500), relief=(150, 1200, 400), face=(60, 45, 85), steep=0.35, floor=0.12,
                   game=1500, bumps=3.0, gully=10.0, crag=30.0, words=("canyon", "gorge", "ravine", "slot canyon")),
    "hills": dict(across=(1000, 6000, 2500), relief=(40, 250, 100), face=(10, 4, 20), steep=0.0, floor=0.3,
                  game=1500, bumps=1.0, gully=2.0, crag=25.0, words=("hills", "rolling hills", "downs", "hill country")),
    "farmland": dict(across=(200, 1500, 600), relief=(8, 60, 25), face=(6, 2, 12), steep=0.0, floor=0.5,
                     game=500, crop=True, bumps=0.4, gully=0.8, crag=12.0,
                     words=("farm", "farmstead", "farmland", "meadow", "pasture", "field", "orchard", "tile")),
    "plateau": dict(across=(1000, 8000, 3000), relief=(50, 400, 150), face=(55, 40, 80), steep=0.12, floor=0.5,
                    game=2500, bumps=2.0, gully=5.0, crag=30.0, words=("plateau", "mesa", "butte", "tableland")),
    "crater": dict(across=(500, 8000, 2000), relief=(100, 800, 300), face=(30, 22, 40), steep=0.08, floor=0.3,
                   game=1500, bumps=2.0, gully=5.0, crag=30.0, words=("crater", "caldera", "volcano")),
    "coast": dict(across=(500, 5000, 2000), relief=(10, 150, 50), face=(10, 3, 45), steep=0.05, floor=0.5,
                  game=1500, bumps=1.0, gully=2.0, crag=20.0, words=("coast", "beach", "shore", "sea cliffs", "bay")),
    "dunes": dict(across=(300, 5000, 1500), relief=(5, 80, 25), face=(15, 5, 32), steep=0.0, floor=0.3,
                  game=1000, bumps=0.3, gully=0.5, crag=10.0, words=("dunes", "desert", "erg", "sand")),
    "moor": dict(across=(2000, 10000, 5000), relief=(100, 500, 250), face=(12, 5, 25), steep=0.01, floor=0.3,
                 game=3000, bumps=1.0, gully=3.0, crag=30.0, words=("moor", "moorland", "highland", "fell", "upland")),
}


DESCRIBE = {
    "alpine_valley": "a valley between high mountains, forested lower slopes, rocky tops",
    "cirque": "a steep mountain bowl, often with a small lake",
    "canyon": "a deep cut into flat high ground, with cliffs",
    "hills": "rolling hills you'd walk over",
    "farmland": "gentle farmland, fields and a farmstead",
    "plateau": "flat high ground ending in cliffs (mesas, buttes)",
    "crater": "a round crater or caldera",
    "coast": "a shoreline: beach, bay or sea cliffs (a \"sea\" with its shore)",
    "dunes": "sand dunes",
    "moor": "open upland: broad, bare, rolling",
}

# the designer decides what they want in their own terms; each answer means numbers behind the scenes
QUESTIONS = [
    {"id": "size", "question": "How big should it feel to cross on foot?", "options": {
        "a minute or two": dict(across=250), "a few minutes": dict(across=600),
        "ten minutes": dict(across=1500), "a long trek": dict(across=5000)}},
    {"id": "height", "question": "How dramatic is the height?", "options": {
        "gentle rises": dict(relief=0.03, face=(6, 2, 12), steep=0.0),
        "hills you'd climb": dict(relief=0.08, face=(15, 8, 25), steep=0.01),
        "mountains": dict(relief=0.25, face=(32, 25, 40), steep=0.12),
        "sheer walls": dict(relief=0.3, face=(60, 45, 85), steep=0.35)}},
    {"id": "underfoot", "question": "What's it like underfoot?", "options": {
        "soft and smooth": dict(bumps=0.3, gully=0.5, crag=10.0),
        "grassy and bumpy": dict(bumps=1.0, gully=2.0, crag=20.0),
        "rocky and broken": dict(bumps=3.0, gully=8.0, crag=30.0)}},
    {"id": "bottom", "question": "What's at the lowest point?", "options": {
        "dry ground": dict(floor=0.3, water="none"), "a river": dict(floor=0.2, water="river"),
        "a lake": dict(floor=0.3, water="lake"), "the sea": dict(floor=0.4, water="sea")}},
    {"id": "enclosed", "question": "Can the player walk out, or is it closed in?", "options": {
        "open": dict(enclosed="open"), "partly closed in": dict(enclosed="partly"),
        "closed in (you can't climb out)": dict(enclosed="closed")}},
    {"id": "shape", "question": "What's its overall shape, seen from above?", "options": {
        "a long valley between ridges": dict(shape="valley"), "a bowl or ring": dict(shape="bowl"),
        "one big mountain or cone": dict(shape="cone"), "high flat ground cut by gorges": dict(shape="cut"),
        "open rolling ground": dict(shape="rolling"), "a strip along water": dict(shape="shore")}},
]

# how each shape is built from the vocabulary (said in the report, so the spec's author reaches for the right nouns)
SHAPES = {
    "valley": "rivers down the middle with ridges either side (or a basin inside a closed ridge, open at one end by a pass)",
    "bowl": "a basin inside a closed ridge (its walls are the mountainsides), a lake as its falls_to",
    "cone": "a lone peak with a big radius and gentle flanks; a crater is a basin inside a small closed ridge on top",
    "cut": "a plateau at world.base with canyons cut along rivers, mesas standing on it",
    "rolling": "lone hills (peaks with no ridge) and a tilt, with rugged patches",
    "shore": "a \"sea\" with a land zone (a coast: \"north\"; an island: near a point) and its shore forms",
}

# what the vocabulary can't build yet: said up front, before anyone spends a round on it
LIMITS = [
    (("tide", "tides", "surf", "reef", "lagoon", "atoll"),
     "the sea is a still surface at one level: no tides, surf or waves, and no reefs or lagoons of their own (a reef "
     "would be a shallow rim of land; a lagoon a lake inside it)"),
    (("volcano", "volcanic", "lava", "cone", "caldera"),
     "no volcano forms yet: no cone profile, lava flows or crater rims of their own; a lone peak with a basin inside a "
     "small closed ridge is the nearest, and a lava flow is a rounded ridge with rock cover"),
    (("cave", "arch", "overhang", "tunnel"),
     "the ground is a height field: no caves, arches, overhangs or natural bridges"),
    (("glacier", "ice", "icefall", "crevasse"), "no glaciers: snow and ice are cover layers only"),
    (("dune", "erg"), "no dune forms: sand is a cover, dunes would be hand-placed hills"),
    (("waterfall", "cascade"), "no falling water: a hanging river makes the step, the water doesn't fall"),
    (("swamp", "marsh", "bog", "wetland", "delta"), "no wetland forms: mud cover and shallow lakes (fans for deltas)"),
    (("city", "town", "castle", "building", "ruin", "ruins"), "no buildings: sites are the flat pads they stand on"),
]


def limits(*texts) -> list[str]:
    """What can't be built, for the words in these texts (a kind's name, the designer's answers, the story)."""
    import re
    words = set(re.findall(r"[a-z]+", " ".join(_norm(t) for t in texts if t)))
    out = []
    for keys, why in LIMITS:
        hit = [k for k in keys if k in words]
        if hit and why not in out:
            out.append(f"{why} (you said \"{hit[0]}\")")
    return out


class Questions(Exception):
    """The spec needs the designer to decide something. `questions` is for relaying to them, not for answering here;
    `cant` says what the tool can't build of what they asked for."""

    def __init__(self, why, questions, cant=()):
        super().__init__(why)
        self.why = why
        self.questions = questions
        self.cant = list(cant)

    def data(self):
        return {"why": self.why, "cant_build": self.cant,
                "questions": [{"id": q["id"], "question": q["question"], "options": list(q["options"]),
                               "optional": bool(q.get("optional"))} for q in self.questions],
                "answer_in": "world.answers: {id: option or the designer's own words}"}

    def text(self):
        out = [f"QUESTIONS FOR THE DESIGNER ({self.why}). Ask them in their own terms; don't answer for them. Put their "
               f"answers in \"world\": {{\"answers\": {{...}}}}:"]
        if self.cant:
            out.insert(0, "TELL THE DESIGNER FIRST, what can't be built yet:\n" + "\n".join(f"  - {c}" for c in self.cant))
        for q in self.questions:
            out.append(f"  {q['id']}: {q['question']}" + (" (optional)" if q.get("optional") else ""))
            for o, means in q["options"].items():
                out.append(f"      - \"{o}\"" + (f"  ({means})" if isinstance(means, str) and means else ""))
        return "\n".join(out)


def _user_kinds():
    import json
    import os
    from pathlib import Path
    from .store import HOME
    p = Path(os.environ.get("HIFI_TERRAIN_KINDS") or HOME / "terrain" / "kinds.json")
    return (json.loads(p.read_text()) if p.exists() else {}), p


def _norm(n):
    return " ".join(str(n).lower().replace("_", " ").split())


def kind_of(name, spec_kinds=None):
    """A kind by its exact name or alias: built in, defined in the spec ("kinds"), or saved from earlier answers.
    Anything else is a question for the designer, never a guess ("river valley" used to become an alpine valley)."""
    if not name:
        return None
    n = _norm(name)
    parts = _mixture(n)
    if parts:
        keys = [kind_of(p_, spec_kinds) for p_ in parts]
        return mix(keys) if all(keys) else None
    user, _ = _user_kinds()
    for table in (KINDS, spec_kinds or {}, user):
        for k, v in table.items():
            if n == _norm(k) or n in [_norm(w) for w in v.get("words", ())]:
                if table is not KINDS:
                    KINDS.setdefault(k, {**v, "words": tuple(v.get("words", ()))})
                return k
    return None


def _mixture(n):
    """"crater + coast", "canyon and mesas", "hills with a lake"? The parts, or None for a single name."""
    import re
    parts = [x.strip() for x in re.split(r"\s*(?:\+|&|/|,|\band\b|\bwith\b|\bplus\b)\s*", n) if x.strip()]
    return parts if len(parts) > 1 else None


def mix(keys):
    """A kind made of several (the first is the main one: its size and floor). Heights and roughness take the most
    dramatic of them; slopes span them all."""
    keys = list(dict.fromkeys(keys))
    if len(keys) == 1:
        return keys[0]
    key = "+".join(keys)
    if key in KINDS:
        return key
    Ks = [KINDS[k] for k in keys]
    main = Ks[0]
    face = (max(K["face"][0] for K in Ks), min(K["face"][1] for K in Ks), max(K["face"][2] for K in Ks))
    KINDS[key] = {**main, "face": face, "relief": max((K["relief"] for K in Ks), key=lambda r: r[2]),
                  "steep": max(K["steep"] for K in Ks), "bumps": max(K["bumps"] for K in Ks),
                  "gully": max(K["gully"] for K in Ks), "crag": max(K["crag"] for K in Ks),
                  "crop": all(K.get("crop") for K in Ks), "mix": keys,
                  "words": (" + ".join(k.replace("_", " ") for k in keys),)}
    return key


def ask_about(name):
    """Questions to define an unknown kind: is it one of the known ones (partial matches first), and if not, what the
    designer wants it to be like."""
    n = _norm(name)
    near = [k for k, v in KINDS.items() if any(w in n or n in w for w in (_norm(k), *map(_norm, v.get("words", ()))))]
    order = near + [k for k in KINDS if k not in near]
    is_q = {"id": "is", "optional": True,
            "question": f"Is \"{name}\" like one of these, or a mix of them (\"crater + coast\")? If not, skip this and "
                        f"answer the rest in your own words",
            "options": {k.replace("_", " "): DESCRIBE.get(k, "") + (" (closest by name)" if k in near else "")
                        for k in order}}
    return [is_q] + [{"id": q["id"], "question": q["question"], "options": {o: "" for o in q["options"]}} for q in QUESTIONS]


STOP = {"a", "an", "the", "of", "it", "is", "and", "or", "to", "in", "on", "you", "i", "its", "like", "very", "quite",
        "bit", "more", "less", "with", "that", "be", "should", "feel", "some", "kind"}


def match(answer, options):
    """The option an answer means: the same words, a prefix, or failing that the most words in common (the designer
    answers in their own words: "rocky" -> "rocky and broken", "a big old volcano" -> "one big mountain or cone")."""
    a = _norm(answer)
    for o in options:
        if _norm(o) == a or _norm(o).startswith(a) or a in _norm(o):
            return o
    aw = {w.rstrip("s") for w in a.split() if w not in STOP}
    best = max(options, key=lambda o: len(aw & {w.rstrip("s") for w in _norm(o).split() if w not in STOP}))
    return best if aw & {w.rstrip("s") for w in _norm(best).split() if w not in STOP} else None


def from_answers(name, answers):
    """A kind from the designer's answers. Returns (kind key, missing question ids)."""
    if answers.get("is") and _norm(answers["is"]) not in ("something new", "none", "no", "skip"):
        k = kind_of(answers["is"])
        if k:
            return k, []
    kind = {"words": (_norm(name),), "answers": dict(answers)}
    missing = []
    for q in QUESTIONS:
        a = answers.get(q["id"])
        opt = None
        if a is not None:
            opt = match(a, q["options"])
        if opt is None:
            missing.append(q["id"])
            continue
        kind.update(q["options"][opt])
    if missing:
        return None, missing
    across = kind.pop("across")
    rel = kind.pop("relief") * across
    kind.update(across=(across * 0.5, across * 2, across), relief=(rel * 0.5, rel * 2, rel), game=across)
    key = _norm(name).replace(" ", "_")
    KINDS[key] = kind
    return key, []


def save_kind(key):
    import json
    user, path = _user_kinds()
    if key in user:
        return None
    k = dict(KINDS[key])
    k["words"] = list(k.get("words", ()))
    user[key] = k
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(user, indent=1))
    return path


def game_across(spec) -> float | None:
    """The frame size for "units": "none" when the spec names a kind: its typical game footprint."""
    w = spec.get("world") or {}
    try:
        k = resolve_kind(w, spec.get("kinds"))
    except Questions:
        return None
    return KINDS[k]["game"] if k else None


def resolve_kind(w, spec_kinds=None):
    """The kind key for a "world" block, from its name, the spec's own kinds, saved kinds, or the designer's answers;
    raises Questions when the designer has to decide."""
    name = w.get("kind")
    if not name:
        return None
    k = kind_of(name, spec_kinds)
    if k:
        return k
    answers = w.get("answers") or {}
    if answers:
        k, missing = from_answers(name, answers)
        if k:
            return k
        qs = [q for q in ask_about(name) if q["id"] in missing]
        raise Questions(f"\"{name}\" still needs: {', '.join(missing)}", qs,
                        limits(name, *map(str, answers.values())))
    raise Questions(f"\"{name}\" isn't a kind the tool knows", ask_about(name), limits(name))


def resolve(T) -> dict:
    """The world in use: kind, compression (horizontal, vertical), relief and face slope for the level, player-scale
    detail. Without a kind: no compression reasoning, generic detail (what the compiler did before)."""
    w = T.spec.get("world") or {}
    k = resolve_kind(w, T.spec.get("kinds"))
    T.new_kind = k if (k and "answers" in KINDS[k]) else None
    if not k:
        return {"kind": None, "c": 1.0, "cv": 1.0, "relief": 0.25 * T.size, "face": 32.0, "face_max": 40.0,
                "steep": 0.12, "bumps": 2.0 * T.k ** 0.5, "gully": 6.0, "crag": 80 * T.k, "base": float(w.get("base", 0)),
                "floor": 0.35}
        # (the generic detail keeps the old frame-relative behaviour for specs that don't name a kind)
    K = KINDS[k]
    c = w.get("compression", "auto")
    if c == "auto":
        # a frame much smaller than the kind (or a kind that's small anyway) is a piece of it, not a squeezed whole
        c = 1.0 if K.get("crop") or T.size < 0.3 * K["across"][2] else min(1.0, T.size / K["across"][2])
    c = float(c)
    cv = math.sqrt(c)
    face, flo, fhi = K["face"]
    # a compressed world is steeper (heights shrink less than distances): what that asks beyond the kind's
    # plausible range goes into cliff bands, not into the whole face
    wanted = math.degrees(math.atan(math.tan(math.radians(face)) * cv / c))
    return {"kind": k, "c": c, "cv": cv, "relief": K["relief"][2] * cv, "face": min(wanted, fhi), "face_wanted": wanted,
            "face_max": fhi, "steep": K["steep"], "bumps": K["bumps"], "gully": K["gully"], "crag": K["crag"],
            "base": float(w.get("base", 0)), "real_across": K["across"][2], "real_relief": K["relief"][2],
            "floor": K.get("floor", 0.3)}


def fill_heights(T):
    """Heights the designer left out, from the kind and its compression: peaks, cols, basin floors. Listed in the
    report so they can be read and overridden."""
    W = T.world
    R, base = W["relief"], W["base"]
    filled = []
    for group, lo, hi in (("peaks", 0.75, 1.0), ("cols", 0.45, 0.6)):
        for n, p in (T.spec.get(group) or {}).items():
            if p.get("h") is None:
                f = lo + (hi - lo) * (zlib.crc32(n.encode()) % 1000) / 999  # stable per name
                p["h"] = base + f * R
                filled.append(f"{n} h {p['h']:.0f} m")
    for n, b in (T.spec.get("basins") or {}).items():
        if b.get("floor") is None:
            b["floor"] = [base + 0.05 * R, base + 0.22 * R]
            filled.append(f"basin {n} floor {b['floor'][0]:.0f}-{b['floor'][1]:.0f} m")
        b.setdefault("walls", {}).setdefault("average", W["face"])
    T.filled = filled


def report(T) -> list[str]:
    W = T.world
    if not W["kind"]:
        return ["world: no kind given, so no real-world yardstick (\"world\": {\"kind\": \"alpine valley\"} etc.)"]
    src = " (from the designer's answers: " + ", ".join(f"{a}={v}" for a, v in KINDS[W["kind"]]["answers"].items()) + ")" \
        if "answers" in KINDS[W["kind"]] else ""
    out = [f"world: {W['kind'].replace('_', ' ')}{src} (real ones ~{W['real_across'] / 1000:.1f} km across, "
           f"~{W['real_relief']:.0f} m relief); this level is at {W['c']:.2f} horizontal, {W['cv']:.2f} vertical scale: "
           f"~{W['relief']:.0f} m relief, faces averaging {W['face']:.0f} deg"
           + (f" (compression would ask {W['face_wanted']:.0f}: the rest goes into cliff bands)"
              if W["face_wanted"] > W["face"] + 1 else "")]
    if T.filled:
        out.append("world: heights chosen for you: " + ", ".join(T.filled))
    K = KINDS[W["kind"]]
    if K.get("mix"):
        out.append("world: a mix of " + " + ".join(k.replace("_", " ") for k in K["mix"]) + f" ({K['mix'][0].replace('_', ' ')}"
                   " sets the size; heights and roughness from the most dramatic)")
    if K.get("shape") in SHAPES:
        out.append(f"world: the designer's shape, {K['shape']}, is built as {SHAPES[K['shape']]}")
    cant = limits(W["kind"], *map(str, (K.get("answers") or {}).values()), T.spec.get("story", ""))
    for c in cant:
        out.append(f"world: CAN'T BUILD YET: {c}")
        w = f"can't build yet (tell the designer): {c}"
        if w not in T.warnings:
            T.warnings.append(w)
    hints = {"river": "use rivers", "lake": "use a lake landform (a basin's falls_to)", "none": "",
             "sea": "use \"sea\" (a level, the land zone, and its shore: cliffs, beaches, coves)"}
    if K.get("water") and hints.get(K["water"]):
        out.append(f"world: the designer said the lowest point is {K['water']}: {hints[K['water']]}")
    if K.get("enclosed") == "closed":
        out.append("world: the designer said it's closed in: a basin inside a closed ridge (its walls are unclimbable), "
                   "with a pass if the player enters")
    return out
