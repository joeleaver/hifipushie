"""Plant specs on disk: workspace/plants/<name>/plant.json (the source of truth) + history/ (every version), and
the grown tree cached in memory by the spec's content. The MCP tools (stage 6) sit on these.

Where the code is (split by responsibility, as C424): this module is the family's base and holds EVERY constant (set
and read at veg_tools.NAME: C422). veg_tools_report: what the tools say: the reference, a plant's report, ground
lines, a set's names and report. veg_tools_look: what the tools show and write: looks, the impostor, export, the
Blender import, wind, a set's export. veg_tools_scene: `edit`, and the Blender scene: guides and limbs as curves,
pull, sync, the seeded habit.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
from pathlib import Path

import numpy as np

from . import store, vegetation
from . import vegetation_grow, vegetation_kernels, vegetation_tree
from . import moved

_GROWN: dict[str, tuple[str, dict]] = {}


def home() -> Path:
    return store.HOME / "plants"


def _dir(name: str) -> Path:
    name = name.partition("#")[0]  # ("oak#3" = the third plant of oak's set: it lives in oak's folder)
    if not re.fullmatch(r"[A-Za-z0-9_\-]+", name):
        raise ValueError("plant names may only contain letters, digits, _ and -")
    return home() / name


def list_plants() -> list[str]:
    return sorted(p.parent.name for p in home().glob("*/plant.json"))


def load(name: str) -> dict:
    base, _, k = name.partition("#")
    p = _dir(base) / "plant.json"
    if not p.exists():
        raise ValueError(f"no plant {base!r}; existing: {list_plants()}")
    spec = json.loads(p.read_text())
    if k:
        vs = variants(spec)
        if not k.isdigit() or not 1 <= int(k) <= len(vs):
            raise ValueError(f"{base} has a set of {len(vs)} (\"{base}#1\" .. \"{base}#{len(vs)}\"); set one with "
                             f"grow_plant(patch={{\"set\": {{\"count\": 5}}}})")
        return vs[int(k) - 1]
    return spec


SET = {"count": 5, "age": [0.55, 1.0], "height": None, "vigour": 0.12, "keep_guides": False, "lean": 0.0}


def _lasting_limbs(spec: dict) -> None:
    """`dead` entries naming a limb by its compass name ("SW2": a name of one grown tree) are stored by the limb's id,
    read off the tree as it grows without them: a later edit can't make them point at another limb."""
    todo = [d for d in spec.get("dead") or [] if isinstance(d.get("limb"), str) and d["limb"] not in (spec.get("guides") or {})
            and not (len(d["limb"]) == 5 and d["limb"][0] == "L")]
    if not todo:
        return
    T = _tree_of({k: v for k, v in spec.items() if k != "dead"})
    by = {L["name"]: L["id"] for L in vegetation_tree.limbs(T)}
    for d in todo:
        if d["limb"] not in by:
            raise ValueError(f"dead: no limb {d['limb']!r} on this tree; its limbs: {sorted(by)} (or a guide's name, or a limb id)")
        d["limb"] = by[d["limb"]]


def variants(spec: dict) -> list[dict]:
    """The plants of a spec's `set`: the same description grown from other seeds at a spread of ages (shares of the
    spec's age, youngest first; or `ages` in years), vigour varied +-`vigour`, an optional `height` range [lo, hi] m
    over the set (the unit follows), `lean` deg of trunk lean in a different direction each. Hero edits (guides, cuts
    without `every`, prunes) are dropped unless keep_guides: a set is the species, not copies of one tree.
    Deterministic: variant k of a spec is always the same plant."""
    st = spec.get("set")
    if not st:
        return []
    bad = set(st) - set(SET) - {"ages", "seeds", "patch"}
    if bad:
        raise ValueError(f"set: unknown keys {sorted(bad)}; it takes {sorted(set(SET) | {'ages', 'seeds', 'patch'})}")
    st = {**SET, **st}
    n = int(st["count"])
    if not 1 <= n <= 24:
        raise ValueError("set.count: 1-24 plants")
    age0 = vegetation.resolve({k: v for k, v in spec.items() if k != "set"})["age"]
    out = []
    for k in range(n):
        u = (k + 0.5) / n if n > 1 else 1.0
        t = k / (n - 1) if n > 1 else 1.0
        key = vegetation_kernels._child(vegetation_kernels._mix(np.uint64(int(spec.get("seed", 1)) + 7919)), k)
        v = {kk: json.loads(json.dumps(vv)) for kk, vv in spec.items() if kk != "set"}
        if not st["keep_guides"]:
            for kk in ("guides", "prune", "envelope", "forces"):
                v.pop(kk, None)
            if v.get("cuts"):
                v["cuts"] = [c for c in v["cuts"] if c.get("every")]  # (management stays: every tree of a pollard row is a pollard)
        v["seed"] = int((st.get("seeds") or [])[k]) if k < len(st.get("seeds") or []) else int(spec.get("seed", 1)) * 1000 + k + 1
        v["age"] = float(st["ages"][k]) if st.get("ages") else round(age0 * (st["age"][0] + (st["age"][1] - st["age"][0]) * t), 1)
        if st.get("height"):
            v["height"] = round(float(st["height"][0] + (st["height"][1] - st["height"][0]) * t), 2)
        else:
            v.pop("height", None) if not st.get("ages") and st["age"] != [1.0, 1.0] else None
        if st["vigour"]:
            hb = vegetation.resolve(v)["habit"]["vigour"]
            v.setdefault("habit", {})["vigour"] = round(float(hb * (1 + st["vigour"] * (2 * float(vegetation_kernels._u(key, 3)) - 1))), 3)
        if st["lean"]:
            a = 2 * np.pi * float(vegetation_kernels._u(key, 4))
            m = np.tan(np.radians(st["lean"] * (0.4 + 0.6 * float(vegetation_kernels._u(key, 5)))))
            v.setdefault("forces", []).append({"dir": [round(float(np.cos(a) * m), 3), round(float(np.sin(a) * m), 3), 0], "orders": [0]})
        if st.get("patch"):
            v = merge(v, st["patch"][k] if isinstance(st["patch"], list) else st["patch"])
        out.append(v)
    return out


def merge(base: dict, patch: dict) -> dict:
    """JSON merge patch: objects merge key by key, null deletes, anything else replaces."""
    out = json.loads(json.dumps(base))
    for k, v in patch.items():
        if v is None:
            out.pop(k, None)
        elif isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = merge(out[k], v)
        else:
            out[k] = v
    return out


def save(name: str, spec: dict | None = None, patch: dict | None = None, note: str = "") -> int:
    """Store a spec (or a merge patch onto the stored one) after checking it resolves; returns its version."""
    if spec is None:
        spec = merge(load(name), patch or {})
    elif patch:
        spec = merge(spec, patch)
    if "#" in name:
        raise ValueError(f"{name} is a plant of a set: change the set through its plant ({name.partition('#')[0]}), or copy "
                         f"it out with grow_plant(new_name, copy_from=\"{name}\")")
    vegetation.resolve(spec)
    _lasting_limbs(spec)
    for v_ in variants(spec):
        vegetation.resolve(v_)
    d = _dir(name)
    (d / "history").mkdir(parents=True, exist_ok=True)
    v = len(list((d / "history").glob("*.json"))) + 1
    text = json.dumps(spec, indent=1)
    (d / "plant.json").write_text(text)
    (d / "history" / f"{v:04d}.json").write_text(json.dumps({"version": v, "note": note, "time": time.time(), "spec": spec}))
    return v


def history(name: str) -> list[dict]:
    out = []
    for p in sorted((_dir(name) / "history").glob("*.json")):
        h = json.loads(p.read_text())
        out.append({"version": h["version"], "note": h["note"]})
    return out


def revert(name: str, version: int) -> int:
    h = json.loads((_dir(name) / "history" / f"{version:04d}.json").read_text())
    return save(name, h["spec"], note=f"revert to {version}")


def describe(name: str | None = None, species: str | None = None) -> dict:
    """A plant's own spec, what it resolves to with its preset and the defaults, and what each habit number usually
    is. With `species` alone: that preset resolved."""
    from . import veg_leaf
    own = load(name) if name else {"species": species}
    full = vegetation.resolve(own)
    full["leaves"] = {**veg_leaf.LEAF, **full["leaves"], "twig": {**veg_leaf.TWIG, **(full["leaves"].get("twig") or {})}}
    if full.get("plant") == "clump":
        from . import veg_small
        return {"own": own, "resolved": {k: v for k, v in full.items() if k != "habit"}, "layer_keys": veg_small.LAYER_INFO,
                "leaf_twig_ranges": TWIG_INFO, "note": "an assembled plant (plant: clump): `habit`, guides, prunes and cuts do not apply; "
                "its form is `clump.layers`, its pictures are `leaves` + `leaves.parts`"}
    out = {"own": own, "resolved": full, "habit_ranges": vegetation.HABIT_INFO,
           "leaf_twig_ranges": TWIG_INFO, "growth": {"steps": vegetation_tree.steps_of(full),
                                                     "note": "steps = age / habit.years_per_step, 2-80"}}
    from . import veg_style
    out["style"] = {"resolved": veg_style.sheet(full) or "realistic", "styles": veg_style.names(),
                    "note": 'spec "style": a sheet\'s name, or {"sheet": name, "wood": {...}, "crown": {...}} to override its numbers'}
    if name:
        out["version"] = len(history(name))
    return out


TWIG_INFO = {
    "leaves.length": "m: a leaf's blade (birch 0.05, oak 0.11, willow 0.09; needles: pine 0.07, spruce 0.02)",
    "leaves.width": "x length (ovate 0.55, willow 0.16)", "leaves.hang": "0-1: leaves hang down from the twig",
    "twig.length": "0.2-0.8 m: the twig (the unit of foliage)", "twig.leaves": "leaves (or needles) on one twig: 8-30 (needles 90-220)",
    "twig.per_m": "3-12 twigs per metre of young shoot", "twig.steps": "2-6: shoots up to this many growth steps old carry twigs (deeper foliage)",
    "twig.spread": "25-55 deg a twig leans off its shoot", "twig.up": "-0.9..0.6: twigs turn up to the light (+) or hang (-)",
    "twig.droop": "-0.1..1.2: the twig's own sag along its length", "twig.min_order": "1-2: lowest branch order that carries twigs",
    "twig.where": '"shoots" or "ends" (only shoot ends)', "twig.angle": "40-60 deg a leaf leaves the twig at",
    "leaves.needle_width": "0.08-0.45: a mesh needle's width / length (wider than life on purpose)",
    "twig.side_shoots": "0-6 pairs of side shoots on a needle spray", "card.cross": "1 or 2 crossed cards (2 for tufts)",
    "card.strips": "0, or 3-5 quads along a long hanging twig", "card.scale": "0.8-1.5 x the card's size",
    "card.twig / card.leaf": "overrides used only for the card's picture (e.g. leaves 400, needle_width 0.03-0.1)",
    "bark.scale": "0.3-1.5 x the bark pattern's size (finer for a small trunk)", "bark.upper_blend": "m the upper colour takes to come in",
    "leaves.shape (small plants)": '"linear" a grass blade, "strap" iris / a palm leaflet, "round" clover / lily pad, "petal" spoon-shaped, widest near the tip',
    "leaves.bend": "0-0.4: a blade arcs sideways (grass)", "twig.arrangement (small plants)": '"basal": every leaf from the foot, fanned by `angle` (a tuft, a rosette); "pinnate": pairs along the stalk, sized by `taper` (a frond)',
    "twig.taper": "0-0.9: leaflets shrink toward the tip by this share", "twig.flower": '{"form": "ray" (daisy, seen from its face) | "cup" (tulip, from the side) | "spike" (lupin, a seed head), "petals", "radius" m, "color", "center", "center_size"}',
    "leaves.parts": "{name: overrides of leaves / twig / card}: more pictures in the same atlas (a flower head, a seed stalk); layers name them",
    "bark.twig_radius": "[m, m]: wood thinner than [0] is all `twig_color`, thicker than [1] none (pine [0.015, 0.05]: only stout wood is orange)",
    "twig.fascicle": "needles per bundle on a pine's shoot: 2 (Scots), 3, 5 (white pines)",
    "twig.needle_angle": "[deg, deg] a needle stands off the shoot at the foliage's base and at its tip ([75, 30] = a bottlebrush)",
    "twig.bud": "m: the resting bud at a shoot's end (pine 0.012-0.02)",
    "card.end": "true: one more card ACROSS the shoot with the tuft seen from its tip, so a tuft is round from every side (pine tufts)",
}


def diff(a, b, path="") -> list[str]:
    """What changed between two specs: 'habit.vigour: 4 -> 7'."""
    out = []
    if isinstance(a, dict) and isinstance(b, dict):
        for k in list(a) + [k for k in b if k not in a]:
            if k not in b:
                out.append(f"{path}{k}: {json.dumps(a[k])} -> (removed)")
            elif k not in a:
                out.append(f"{path}{k}: (unset) -> {json.dumps(b[k])}")
            else:
                out += diff(a[k], b[k], f"{path}{k}.")
    elif a != b:
        out.append(f"{path[:-1]}: {json.dumps(a)} -> {json.dumps(b)}")
    return out


def change_note(name: str, before_spec: dict | None, before_stats: dict | None) -> str:
    """After a save: every value that changed in force, old -> new (the old ones from the preset or the defaults
    when the plant hadn't set them), and what the tree did."""
    after = load(name)
    lines = []
    if before_spec is not None:
        try:
            lines = ["  " + d_ for d_ in diff(vegetation.resolve(before_spec), vegetation.resolve(after))]
        except ValueError:
            lines = ["  " + d_ for d_ in diff(before_spec, after)]
    st = grown(name)["stats"]
    if before_stats:
        lines.append(f"  tree: {before_stats['nodes']} -> {st['nodes']} nodes, {before_stats['height_m']} -> {st['height_m']} m tall, "
                     f"trunk diameter {before_stats['trunk_diameter_m']} -> {st['trunk_diameter_m']} m")
    return "changed:\n" + "\n".join(lines) if lines else ""


def grown(name: str) -> dict:
    spec = load(name)
    spec = {k: v for k, v in spec.items() if k != "set"}
    key = hashlib.sha1(json.dumps([spec, vegetation.VERSION], sort_keys=True).encode()).hexdigest()
    if _GROWN.get(name, ("",))[0] != key:
        _GROWN[name] = (key, vegetation_grow.grow(spec))
    return _GROWN[name][1]


VIEWS = ("clay", "bare", "leaf", "far", "near", "close", "under", "ground")


def _tree_of(spec: dict) -> dict:
    spec = {k: v for k, v in spec.items() if k != "set"}
    key = hashlib.sha1(json.dumps([spec, vegetation.VERSION], sort_keys=True).encode()).hexdigest()
    for k_, t in _GROWN.values():
        if k_ == key:
            return t
    return vegetation_grow.grow(spec)


# The modules this one was split into (as C424). Its constants stay HERE (C422): tests/test_constants_address.py.
MODULES = ("veg_tools_report", "veg_tools_look", "veg_tools_scene")
__getattr__ = moved.refuse(__name__, MODULES)  # a name that moved says where it is now (C426)
