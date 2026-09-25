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


def kind_of(name):
    if not name:
        return None
    n = str(name).lower().replace("_", " ").strip()
    if n.replace(" ", "_") in KINDS:
        return n.replace(" ", "_")
    for k, v in KINDS.items():
        if n in v["words"]:
            return k
    for k, v in KINDS.items():  # a word inside a longer phrase ("a small alpine valley")
        if any(w in n for w in v["words"]):
            return k
    raise ValueError(f"unknown terrain kind {name!r}: one of {sorted(KINDS)} (or words like "
                     + ", ".join(repr(w) for w in ("glen", "gorge", "farmstead", "mesa", "caldera")) + ")")


def game_across(spec) -> float | None:
    """The frame size for "units": "none" when the spec names a kind: its typical game footprint."""
    k = kind_of((spec.get("world") or {}).get("kind"))
    return KINDS[k]["game"] if k else None


def resolve(T) -> dict:
    """The world in use: kind, compression (horizontal, vertical), relief and face slope for the level, player-scale
    detail. Without a kind: no compression reasoning, generic detail (what the compiler did before)."""
    w = T.spec.get("world") or {}
    k = kind_of(w.get("kind"))
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
            "floor": K["floor"]}


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
    out = [f"world: {W['kind'].replace('_', ' ')} (real ones ~{W['real_across'] / 1000:.1f} km across, "
           f"~{W['real_relief']:.0f} m relief); this level is at {W['c']:.2f} horizontal, {W['cv']:.2f} vertical scale: "
           f"~{W['relief']:.0f} m relief, faces averaging {W['face']:.0f} deg"
           + (f" (compression would ask {W['face_wanted']:.0f}: the rest goes into cliff bands)"
              if W["face_wanted"] > W["face"] + 1 else "")]
    if T.filled:
        out.append("world: heights chosen for you: " + ", ".join(T.filled))
    return out
