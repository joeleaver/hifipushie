"""Plant specs on disk: workspace/plants/<name>/plant.json (the source of truth) + history/ (every version), and
the grown tree cached in memory by the spec's content. The MCP tools (stage 6) sit on these."""

from __future__ import annotations

import hashlib
import json
import re
import time
from pathlib import Path

import numpy as np

from . import store, vegetation

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
    by = {L["name"]: L["id"] for L in vegetation.limbs(T)}
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
        key = vegetation._child(vegetation._mix(np.uint64(int(spec.get("seed", 1)) + 7919)), k)
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
            v.setdefault("habit", {})["vigour"] = round(float(hb * (1 + st["vigour"] * (2 * float(vegetation._u(key, 3)) - 1))), 3)
        if st["lean"]:
            a = 2 * np.pi * float(vegetation._u(key, 4))
            m = np.tan(np.radians(st["lean"] * (0.4 + 0.6 * float(vegetation._u(key, 5)))))
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
           "leaf_twig_ranges": TWIG_INFO, "growth": {"steps": vegetation.steps_of(full),
                                                     "note": "steps = age / habit.years_per_step, 2-80"}}
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
        _GROWN[name] = (key, vegetation.grow(spec))
    return _GROWN[name][1]


# ---------------------------------------------------------------- what the tools say and show

def reference(name: str) -> dict | None:
    p = _dir(name) / "reference.json"
    return json.loads(p.read_text()) if p.exists() else None


def set_reference(name: str, image: str, mask: dict, bare: bool = False, credit: str = "") -> dict:
    """Keep a reference photo for the plant: copied beside it, with how its silhouette is taken (`mask` =
    vegetation.reference_mask arguments: crop + foot, or a traced polygon) and whether the photo is of a bare tree."""
    import shutil
    d = _dir(name)
    d.mkdir(parents=True, exist_ok=True)
    src = Path(image)
    if not src.exists():
        raise ValueError(f"no image at {image}")
    dst = d / ("reference" + src.suffix.lower())
    if src.resolve() != dst.resolve():
        shutil.copyfile(src, dst)
    m = vegetation.reference_mask(str(dst), **mask)  # (fails here if the mask's arguments are wrong)
    if m.sum() < 50:
        raise ValueError("the mask is empty: check crop/foot/tol, or trace a polygon")
    ref = {"image": str(dst), "mask": mask, "bare": bool(bare), "credit": credit}
    (d / "reference.json").write_text(json.dumps(ref, indent=1))
    return ref


def _report_clump(name: str, T: dict) -> str:
    """An assembled plant in numbers: size, cards per layer, how they stand, cover from above, triangles."""
    from . import veg_leaf, veg_small
    s, m = T["spec"], veg_small.measures(T)
    at = veg_leaf.atlas(s["leaves"], (s.get("bark") or {}).get("twig_color") or [0.45, 0.4, 0.35])
    pc = veg_leaf.part_cards(s["leaves"])
    tw = T["twigs"]
    out = [f"plant {name}: {s.get('species') or 'no preset'}, assembled from cards (plant: clump), seed {s.get('seed', 1)}",
           f"size: {m['height_m']} m tall, {m['spread_m']} m across; {m['cards']} cards on {m.get('stalks', 0)} stalks; "
           f"{sum(len(at['cards'][c]['F']) for c in tw['card'])} foliage triangles at full detail",
           f"cards stand at {m['card_elevation_p10_50_90'][1]:.0f} deg above level (p10-p90 {m['card_elevation_p10_50_90'][0]:.0f} to "
           f"{m['card_elevation_p10_50_90'][2]:.0f}: 90 = upright blades, 0 = lying flat); cover seen from above {m['cover_from_above']} of its footprint"]
    for i, L in enumerate(s["clump"]["layers"]):
        n_ = int(np.isin(tw["card"], pc.get(L.get("part") or "", [])).sum()) if L.get("part", "main") else 0
        out.append(f"  layer {i}" + (f" '{L['name']}'" if L.get("name") else "") + f": part {L.get('part', 'main')}, count {L.get('count', 12)}"
                   + (f", on stalks {L['stem']} m" if L.get("stem") else "") + (f", standing on layer {L['on']}" if L.get("on") is not None else "")
                   + (f" ({n_} cards of this part in all)" if n_ else ""))
    out.append(f"pictures (parts of the atlas): {', '.join(f'{k} x{len(v)}' for k, v in pc.items())}; atlas {at['color'].shape[0]} px, card fill {at['fill']:.2f}")
    warn = []
    if m["cards"] * at["triangles"] > 3000:
        warn.append(f"WARNING: {m['cards'] * at['triangles']} foliage triangles for one small plant; a scattered plant wants 50-600 (fewer, larger cards)")
    if at["fill"] < 0.15:
        warn.append(f"WARNING: card fill {at['fill']:.2f}: the cards are mostly empty (overdraw); `card.strips` for long thin pictures, or fuller pictures")
    if m["height_m"] > 0 and tw["pos"][:, 2].min() < -0.06:
        warn.append("WARNING: cards start more than 6 cm under the ground")
    return "\n".join(out + warn)


def report(name: str) -> str:
    """The grown plant in numbers: size, form (measured on its own silhouettes), limbs, foliage, guides, and its
    reference match when it has one. WARNINGS last."""
    from . import veg_leaf
    T = grown(name)
    s = T["spec"]
    st = T["stats"]
    warn = []
    if T.get("clump"):
        return _report_clump(name, T)
    out = [f"plant {name}: {s.get('species') or 'no preset'}, age {s['age']} ({st['steps']} growth steps), "
           f"{st['nodes']} nodes, grown in {st['grow_s']} s",
           f"size: {st['height_m']} m tall, trunk DIAMETER {st['trunk_diameter_m']} m at the foot (with its flare), "
           f"branch orders to {st['max_order']}" + (f", {st['pruned_nodes']} nodes cut by prunes" if st.get("pruned_nodes") else "")]
    ms = [vegetation.shape_measures(vegetation.silhouette(T, az, 12, leaves=True)[0]) for az in (0, 90)]
    f = lambda k: round(float(np.mean([m[k] for m in ms])), 2)
    H = T["height"]
    ends = T["pos"][T["ends"] & (T["order"] > 0)]
    if not len(ends):
        ends = T["pos"][T["ends"]]
    cen = ends[:, :2].mean(0) if len(ends) else np.zeros(2)
    rad_ = float(np.percentile(np.linalg.norm(ends[:, :2] - cen, axis=1), 90)) if len(ends) else 0.0
    zlow = float(np.percentile(ends[:, 2], 3)) if len(ends) else 0.0
    covs = []
    for az in (0, 90):  # cover of the CROWN: the side view above the crown's base, trunk rows left out
        m_, fr = vegetation.silhouette(T, az, 12, leaves=True)
        top = int(max((fr["z1"] - zlow) * fr["px_per_m"], 1))
        covs.append(1 - vegetation.shape_measures(m_[:top])["porosity"] if m_[:top].any() else 0.0)
    cover = float(np.mean(covs))
    tr = T["pos"][T["order"] == 0]
    tip = tr[np.argmax(tr[:, 2])]
    lean = float(np.degrees(np.arctan2(np.linalg.norm(tip[:2]), max(tip[2], 1e-6))))
    out.append(f"form (in leaf, two side views): width/height {f('width_over_height')}; widest at {f('widest_at')} of the "
               f"height; crown base (the lowest branch ends) at {zlow:.1f} m = {zlow / max(H, 1e-6):.2f} of the height")
    out.append(f"trunk: {tip[2]:.1f} m to its top, leaning {lean:.0f} deg from upright"
               + (f" toward [{tip[0] / max(np.linalg.norm(tip[:2]), 1e-6):+.1f}, {tip[1] / max(np.linalg.norm(tip[:2]), 1e-6):+.1f}]" if lean > 3 else "")
               + f" (its top stands [{tip[0]:+.1f}, {tip[1]:+.1f}] m from its foot)")
    out.append(f"crown: its middle sits [{cen[0]:+.1f}, {cen[1]:+.1f}] m from the trunk's foot ({np.linalg.norm(cen) / max(rad_, 0.5):.2f} "
               f"of its radius {rad_:.1f} m: 0 = centred, 0.5+ = plainly swept to one side); cover {cover:.2f} (1 = solid from the side)")
    ang = vegetation.branch_angles(T, 1)
    if ang["n"]:
        drawn = sum(1 for ai in T["guides"].values() if T["axes"][ai]["order"] == 1)
        out.append(f"limbs: {ang['n']} first-order branches ({drawn} drawn; medians of so few jump about), leaving the trunk at {ang['insertion_p10_50_90'][1]} deg "
                   f"(p10-p90 {ang['insertion_p10_50_90'][0]}-{ang['insertion_p10_50_90'][2]}), their far halves "
                   f"{ang['elevation_p10_50_90'][1]} deg above level ({ang['elevation_p10_50_90'][0]} to {ang['elevation_p10_50_90'][2]})")
    lb = vegetation.limbs(T)
    if lb:
        out.append("main limbs (name: leaves the trunk at height, base diameter, its length along its stoutest wood and where that "
                   "ends, the span of everything it carries. The compass name is by where its farthest wood lies and "
                   "is THIS tree's; the id lasts through edits. edit_plant take_limb makes one a guide you can redraw):")
        for L in lb:
            out.append(f"  {L['name']}{' (drawn)' if L['guide'] else ' (id ' + L['id'] + ')'}: at {L['height']} m, {L['diameter'] * 100:.0f} cm, "
                       f"{L['length']} m long to [{L['end'][0]:+.1f}, {L['end'][1]:+.1f}, {L['end'][2]:.1f}], "
                       f"carries {L['low']}-{L['high']} m high, {L['reach']} m out, since year {L['born_year']}")
    tw = veg_leaf.place(T)
    if len(tw["pos"]):
        out.append(f"foliage: {len(tw['pos'])} twigs ({s['leaves'].get('shape', 'ovate')} leaves, "
                   f"{s['leaves'].get('length', 0.07)} m)")
    else:
        out.append("foliage: none (winter, dead, or decayed)")
    for g, ai in T["guides"].items():
        nodes = np.flatnonzero((T["axis"] == ai) & T["pin"])
        path = np.asarray(s["guides"][g]["path"], float)
        if not len(nodes):
            out.append(f"guide {g}: not grown")
            fy = s["guides"][g].get("from_year", 0)
            warn.append(f"guide {g} has no nodes: " + (f"its from_year {fy} is at or past the tree's age {s['age']}" if fy >= s["age"]
                        else "a prune volume covers it, or the wood it started from was cut"))
            continue
        end = float(np.linalg.norm(T["pos"][nodes[-1]] - path[-1]))
        kids = int(np.isin(T["parent"], nodes).sum() - len(nodes) + 1)
        sub = np.zeros(len(T["parent"]), bool)
        sub[nodes] = True
        for i_ in range(int(nodes[0]), len(sub)):
            sub[i_] |= sub[T["parent"][i_]]
        reach = float(np.linalg.norm(T["pos"][sub][:, :2], axis=1).max())
        out.append(f"guide {g}: order {T['axes'][ai]['order']}, {len(nodes)} nodes on its path, "
                   f"{'drawn to its end' if end < 0.3 else f'{end:.1f} m short of its end'}, {kids} branches from it; "
                   f"with what grew from it, it reaches {reach:.1f} m out from the foot, {T['pos'][sub][:, 2].min():.1f}-{T['pos'][sub][:, 2].max():.1f} m high")
        if end >= 0.3:
            warn.append(f"guide {g} stops {end:.1f} m short: give it more years (until_year) or more vigour")
    for g in (s.get("guides") or {}):
        if g not in T["guides"]:
            warn.append(f"guide {g} never started (from_year past the tree's age?)")
    ref = reference(name)
    if ref:
        R = vegetation.reference_mask(ref["image"], **ref["mask"])
        m = vegetation.match(T, R, bare=ref["bare"], azimuths=(0, 45, 90, 135))
        o, r = m["ours"], m["ref"]
        out.append(f"reference: outline IoU {m['iou']:.2f} (best from azimuth {m['azimuth']}); width/height "
                   f"{o['width_over_height']:.2f} vs {r['width_over_height']:.2f}, bole {o['bole']:.2f} vs {r['bole']:.2f}, "
                   f"widest at {o['widest_at']:.2f} vs {r['widest_at']:.2f}")
    for dd in st.get("dead") or []:
        if dd.get("missing"):
            warn.append(f"dead: {dd['what']} is not on this tree any more (an edit regrew it without that limb): nothing died there")
        else:
            out.append(f"dead wood ({dd['what']}): {dd['nodes']} nodes died, {dd['broken_off']} of them (the thin ends) broken off; "
                       f"what stands is bare and grey, {dd['low']}-{dd['high']} m high")
            if dd["nodes"] and dd["broken_off"] >= dd["nodes"] - 1:
                warn.append(f"dead {dd['what']}: all of it broke off (min_radius is thicker than the wood there): nothing shows")
            if not dd["nodes"]:
                warn.append(f"dead {dd['what']}: no wood there (a limb shorter than its `from`, or an empty volume)")
    side = T["order"] > 0
    if side.any():  # clearance over the ground as it lies (a hillside rises under the uphill limbs)
        from . import veg_look
        Pn = T["pos"][side]
        gz = np.array([veg_look.ground_z(s, q) for q in Pn[:, :2]]) if (s.get("environment") or {}).get("ground", {}).get("slope") else np.zeros(len(Pn))
        cl = Pn[:, 2] - gz
        i_ = int(np.argmin(cl))
        out.append(f"lowest wood: {cl[i_]:.1f} m above the ground at [{Pn[i_][0]:+.1f}, {Pn[i_][1]:+.1f}]"
                   + (f" (the ground there is {gz[i_]:+.1f} m against the foot)" if abs(gz[i_]) > 0.05 else ""))
        if cl[i_] < -0.05:
            warn.append(f"{int((cl < 0).sum())} nodes are under the ground (down to {cl[i_]:.1f} m) round [{Pn[i_][0]:+.1f}, {Pn[i_][1]:+.1f}]: "
                        f"raise that limb's path, prune {{\"under\": z}}, or lower habit.sag")
    longest = max((L["length"] for L in lb), default=0.0)
    if rad_ > 0.9 * H or longest > 1.4 * H:
        warn.append(f"the crown is {2 * rad_:.0f} m across on a {H:.0f} m tree (longest limb {longest:.0f} m): limbs ran away. "
                    f"With fewer branch orders (max_order) or less shedding the same vigour goes into fewer, longer shoots: "
                    f"lower habit.vigour / shoot_max, or set tip_life for the limbs")
    for c in st.get("cuts") or []:
        if not c["nodes"]:
            warn.append(f"the cut at year {c['year']} cut nothing: the tree had no wood in that volume yet (a pollard's "
                        f"first cut must come after the trunk has grown past the cut height)")
            continue
        out.append(f"cut at year {c['year']}: {c['nodes']} nodes of wood removed, {c['stubs']} stubs left to sprout")
    lost = st.get("pruned_nodes", 0)
    if lost > 0.5 * (st["nodes"] + lost):
        warn.append(f"the prunes cut {lost} of {st['nodes'] + lost} nodes ({lost / (st['nodes'] + lost):.0%}): what is left is mostly "
                    f"stubs; shrink the prune volumes (get_plant lists them) or use a timed `cuts` entry so the tree regrows")
    elif st["nodes"] < 12 * st["steps"] and not s.get("cuts"):
        warn.append(f"only {st['nodes']} nodes after {st['steps']} steps: the tree starved (raise habit.vigour, lower habit.shed, "
                    f"or it is shaded by its environment: neighbours/stand)")
    if st["nodes"] > 90000:
        warn.append("over 90k nodes: slow to look at and heavy to export (lower habit.vigour, bud_break or max_order)")
    if s.get("height") and abs(T["height"] - s["height"]) > 0.15 * s["height"] and not s.get("cuts"):
        warn.append(f"asked height {s['height']} m, grew {T['height']:.1f} m. `height` sizes the UNEDITED tree of this "
                    f"description (it sets the segment length); guides, prunes, cuts and envelopes then change what grows. "
                    + ("With a drawn trunk the trunk's own path decides: make the path as tall as you want it, and drop `height`."
                       if any(T["axes"][a]["order"] == 0 for a in T["guides"].values()) else "Change age or habit.unit, or the edits."))
    try:
        p_age = vegetation.preset(s["species"]).get("age") if s.get("species") else None
    except ValueError:
        p_age = None
    if p_age and s["age"] > 1.4 * p_age and not s.get("height"):
        warn.append(f"age {s['age']} is well past the age the {s['species']} preset was tuned at ({p_age}): size keeps growing with "
                    f"age here ({T['height']:.0f} m); for an older-looking tree of normal size set `height`, or lower habit.vigour")
    if s["habit"]["clear"] > 0.9 * tip[2]:
        warn.append(f"habit.clear {s['habit']['clear']} m is nearly the whole trunk ({tip[2]:.1f} m): no limbs can leave it")
    dr = vegetation.droop(T, max(f("bole"), 0.1))
    if dr > 0.1:
        warn.append(f"{dr:.0%} of the shoot ends hang under the crown's base away from the trunk (habit.sag, tropism)")
    d_end = vegetation._norm(T["pos"] - T["pos"][T["parent"]])[T["ends"]]
    down = float((d_end[:, 2] < -0.5).mean()) if len(d_end) else 0.0
    out.append(f"shoot ends: {down:.0%} point steeply down (weeping), {float((d_end[:, 2] > 0.5).mean()) if len(d_end) else 0:.0%} steeply up")
    if down > 0.35 and min(vegetation._per(s["habit"]["tropism"], np.arange(6))) > -0.3:
        warn.append(f"{down:.0%} of the shoot ends hang though the habit isn't a weeping one: lower habit.sag ({s['habit']['sag']}) "
                    f"or raise tropism on the high orders")
    if load(name.partition("#")[0]).get("set") and "#" not in name:
        out.append(set_report(name))
    return "\n".join(out + [f"WARNING: {w}" for w in warn])


VIEWS = ("clay", "bare", "leaf", "far", "near", "close", "under")


def _view_jobs(T: dict, views, azimuth: float, size: int, stem) -> tuple[list, list]:
    """Blender view jobs for named views or camera dicts; (jobs, [(name, path)])."""
    from . import veg_look
    import math
    has_leaves = len(veg_look.veg_leaf_place(T)) > 0
    H = T["height"]
    c_, s_ = math.cos(math.radians(azimuth)), math.sin(math.radians(azimuth))
    toward = np.array([-s_, -c_, 0.0])
    sz = [int(size * 0.95), size]
    jobs, got = [], []
    for k, x in enumerate(views):
        if isinstance(x, dict):  # a camera of your own: {"eye": [x, y, z], "look": [x, y, z], "fov": deg, "name"}
            nm = x.get("name", f"camera{k + 1}")
            if "eye" not in x or "look" not in x:
                raise ValueError('a camera view needs "eye" [x, y, z] and "look" [x, y, z] (m), optional "fov" deg, "name"')
            j = {"out": stem(nm), "size": sz, "eye": x["eye"], "look": x["look"], "fov": x.get("fov", 40),
                 "leaves": has_leaves and x.get("leaves", True), "clay": bool(x.get("clay")),
                 "sun": x.get("sun") or [math.degrees(math.atan2(x["eye"][0] - x["look"][0], x["eye"][1] - x["look"][1])) + 55, 40]}
            jobs.append(j)
            got.append((nm, j["out"]))
            continue
        if x not in VIEWS:
            raise ValueError(f"unknown view {x!r}: {list(VIEWS)} or a camera {{'eye', 'look', 'fov'}}")
        j = {"out": stem(x), "size": sz, "sun": [azimuth + 235, 40]}
        if x == "clay":
            j.update(azimuth=azimuth, leaves=False, clay=True, ruler=True)
        elif x == "bare":
            j.update(azimuth=azimuth, elevation=4, leaves=False, ruler=True)
        elif x == "leaf":
            j.update(azimuth=azimuth, elevation=4, leaves=has_leaves)
        elif x == "far":  # from far enough that the tree is about half the picture's height
            j.update(eye=(toward * max(12.0, 4.5 * H) + [0, 0, 1.7]).tolist(), look=[0, 0, 0.45 * H], fov=24, leaves=has_leaves)
        elif x == "near":  # standing by it: a small tree from close, a big one from 5 m, looking at the trunk and up
            dist = veg_look.near_distance(T, toward, float(np.clip(0.45 * H, 2.0, 5.0)))
            j.update(eye=(toward * dist + [0, 0, min(1.7, 0.6 * H)]).tolist(), look=[0, 0, min(0.5 * H, 5.0)], fov=62, leaves=has_leaves)
        elif x == "under":  # standing under the crown, looking up along a limb: is there foliage under and round the wood?
            ends_ = T["pos"][T["ends"]]
            q = ends_[np.argmax(ends_[:, :2] @ toward[:2])] if len(ends_) else np.array([0, 0, H])
            j.update(eye=(toward * 0.25 * float(np.linalg.norm(q[:2])) + [0, 0, 1.6]).tolist(),
                     look=[float(0.8 * q[0]), float(0.8 * q[1]), float(q[2])], fov=58, leaves=has_leaves)
        elif x == "close":
            j.update(azimuth=azimuth, elevation=8, focus=veg_look.closeup_focus(T, azimuth), span=min(2.4, 0.6 * H), leaves=has_leaves)
        if "eye" in j:  # the eye stands on the hillside, not on the level of the plant's foot
            j["eye"] = [j["eye"][0], j["eye"][1], j["eye"][2] + veg_look.ground_z(T["spec"], j["eye"])]
        jobs.append(j)
        got.append((x, j["out"]))
    return jobs, got


def look(name: str, views=("clay", "leaf", "far"), azimuth: float = 0.0, size: int = 640, foliage: str | None = None,
         sheet: bool = False, triangles: int | None = None) -> list:
    """Render views of the plant; returns [(view name, png path)]. See look_plant (the tool) for the views."""
    from . import veg_look
    T = grown(name)
    d = _dir(name)
    v = len(history(name))
    if sheet:
        ref = reference(name)
        if not ref:
            raise ValueError("no reference yet: plant_reference(name, image_path, ...) first")
        out = str(d / f"sheet_v{v}.png")
        veg_look.reference_sheet(load(name), ref, out, bare=ref["bare"], title=name, foliage=foliage)
        return [("sheet", out)]
    suffix = (f"_{name.partition('#')[2]}" if "#" in name else "") + (f"_az{int(round(azimuth))}" if azimuth else "") + (f"_{triangles}tris" if triangles else "")
    if T.get("clump"):  # a small plant is seen from the side, from standing height and from above; and its pictures
        import math
        from PIL import Image
        from . import veg_leaf, veg_small
        s = T["spec"]
        at = veg_leaf.atlas(s["leaves"], (s.get("bark") or {}).get("twig_color") or [0.45, 0.4, 0.35])
        c = at["color"]
        img = np.clip(c[..., :3] * c[..., 3:] + np.array([0.75, 0.78, 0.82]) * (1 - c[..., 3:]), 0, 1)
        pa = str(d / f"atlas{suffix}_v{v}.png")
        Image.fromarray((img * 255).astype(np.uint8)).resize((size, size)).save(pa)
        H, R = T["height"], max(veg_small.measures(T)["spread_m"] / 2, 0.1)
        D = 2.2 * max(H, 2 * R)
        ca, sa = math.cos(math.radians(azimuth)), math.sin(math.radians(azimuth))
        e = lambda dist, z: [-sa * dist, -ca * dist, z]
        jobs = [{"name": "side", "eye": e(D, 0.45 * H), "look": [0, 0, 0.45 * H], "fov": 40},
                {"name": "stand", "eye": e(max(1.5, 1.5 * D), 1.6), "look": [0, 0, 0.45 * H], "fov": 28 if H < 1 else 46},
                {"name": "above", "eye": e(0.3 * D, 1.6 * D), "look": [0, 0, 0.3 * H], "fov": 40}]
        got = [("atlas", pa)]
        for j in jobs:
            j.update(out=str(d / f"{j['name']}{suffix}_v{v}.png"), size=[size, size], sun=[azimuth + 235, 40])
            got.append((j["name"], j["out"]))
        veg_look.render(T, jobs, foliage=foliage, triangles=triangles)
        return got
    jobs, got = _view_jobs(T, views, azimuth, size, lambda x: str(d / f"{x}{suffix}_v{v}.png"))
    veg_look.render(T, jobs, foliage=foliage, triangles=triangles)
    return got


def look_group(names: list[str], at: list | None = None, spacing: float | None = None, views=("far",),
               azimuth: float = 0.0, size: int = 640, foliage: str | None = None, triangles: int | None = None) -> list:
    """Several plants standing together in one picture. `at` = [[x, y], ...] per plant (m), or `spacing` m apart on a
    loose ring (default: 0.35 x the tallest's height). The first plant's environment (ground slope, look) sets the
    scene; "far"/"near" frame the whole group. Returns [(view, path)]."""
    from . import veg_look
    import math
    trees = [grown(n) for n in names]
    H = max(t["height"] for t in trees)
    if at is None:
        sp = spacing or 0.35 * H
        r = sp / (2 * math.sin(math.pi / max(len(names), 2))) if len(names) > 1 else 0.0
        at = [[r * math.cos(2.4 * i + 0.5) * (0.8 + 0.2 * ((i * 7) % 3)), r * math.sin(2.4 * i + 0.5)] for i in range(len(names))]
    if len(at) != len(names):
        raise ValueError(f"{len(names)} plants but {len(at)} positions")
    at = [np.asarray(a, float)[:2] for a in at]
    d = home() / "_groups"
    d.mkdir(parents=True, exist_ok=True)
    tag = "+".join(names).replace("#", "-")
    if len(tag) > 60:  # (a cut-off name read as another plant's)
        tag = f"{names[0].replace('#', '-')}+{len(names) - 1}more_{hashlib.sha1(tag.encode()).hexdigest()[:6]}"
    tag += (f"_az{int(round(azimuth))}" if azimuth else "") + (f"_{triangles}tris" if triangles else "")
    c_, s_ = math.cos(math.radians(azimuth)), math.sin(math.radians(azimuth))
    toward = np.array([-s_, -c_, 0.0])
    right = np.array([c_, -s_, 0.0])
    cen = np.r_[np.mean(at, axis=0), 0.0]
    # the group's width as this view sees it (crowns included), and the eye's distance to fill ~80% of the frame
    rads = [float(np.percentile(np.linalg.norm(t["pos"][:, :2], axis=1), 98)) for t in trees]
    xs = [float(np.r_[a, 0] @ right) for a in at]
    width = max(x + r for x, r in zip(xs, rads)) - min(x - r for x, r in zip(xs, rads))
    depth = max(float(np.r_[a, 0] @ -toward) + r for a, r in zip(at, rads))
    aspect = 1.3

    def frame(fov):  # vertical fov deg -> eye distance from the group's middle
        tv = math.tan(math.radians(fov) / 2)
        return max(H / (2 * tv), width / (2 * tv * aspect)) * 1.2 + max(depth, 0.0)

    jobs, got = [], []
    for k, x in enumerate(views):
        nm = x if isinstance(x, str) else x.get("name", f"camera{k + 1}")
        o = str(d / f"{tag}_{nm}.png")
        j = {"out": o, "size": [int(size * aspect), size], "sun": [azimuth + 235, 40]}
        if isinstance(x, dict):  # (world metres, the same frame as `at`)
            j.update(eye=x["eye"], look=x["look"], fov=x.get("fov", 40), clay=bool(x.get("clay")))
        elif x in ("far", "clay"):
            j.update(eye=(cen + toward * frame(30) + [0, 0, 1.7]).tolist(), look=(cen + [0, 0, 0.47 * H]).tolist(), fov=30)
            if x == "clay":
                j.update(clay=True, leaves=False)
        elif x == "near":
            j.update(eye=(cen + toward * (0.5 * frame(62) + 2.0) + [0, 0, 1.7]).tolist(), look=(cen + [0, 0, 0.4 * H]).tolist(), fov=62)
        elif x == "top":
            j.update(eye=(cen + [0, -0.01, 2.4 * max(width, H)]).tolist(), look=cen.tolist(), fov=30)
        else:
            raise ValueError(f"group views: far, near, clay, top or a camera {{'eye', 'look', 'fov'}} (got {x!r})")
        if isinstance(x, str):  # (the eye stands on the hillside)
            j["eye"] = [j["eye"][0], j["eye"][1], j["eye"][2] + veg_look.ground_z(trees[0]["spec"], j["eye"])]
        jobs.append(j)
        got.append((nm, o))
    others = [(t, a.tolist(), (i * 137.5) % 360 if names[i] in names[:i] else 0.0)
              for i, (t, a) in enumerate(zip(trees[1:], at[1:]), start=1)]  # (a repeated plant is turned; others stand as made)
    veg_look.render(trees[0], jobs, foliage=foliage, others=others, at=at[0].tolist(), triangles=triangles)
    return got


def impostor(name: str, px: int = 512) -> dict:
    """The plant from two sides (along +y and along -x) as one RGBA picture, for the last LOD's crossed quads:
    {"image" (h, 2w, 4) 0..1, "size": the square each view covers (m), "height": its middle's height (m)}."""
    from PIL import Image
    import tempfile
    from . import veg_look
    T = grown(name)
    H = T["height"]
    R = float(np.percentile(np.linalg.norm(T["pos"][:, :2], axis=1), 99.5))
    S = float(max(H, 2 * R) * 1.06)
    with tempfile.TemporaryDirectory(prefix="hifipushie-vegimp-") as tmp:
        jobs = [{"out": f"{tmp}/v{i}.png", "size": [px, px], "azimuth": az, "elevation": 0, "focus": [0, 0, 0.5 * H], "span": S,
                 "leaves": True, "transparent": True, "no_ground": True, "sun": [az + 235, 50]} for i, az in enumerate((0, 90))]
        veg_look.render(T, jobs)
        im = np.concatenate([np.asarray(Image.open(j["out"]).convert("RGBA"), np.float32) / 255 for j in jobs], axis=1)
    return {"image": im, "size": S, "height": 0.5 * H}


def export(name: str, out_dir: str | None = None, triangles: int | None = None, lods: int = 1, seasons=("summer",),
           wet: bool = False, impostor_lod: bool = False, lod_files: bool = False) -> dict:
    """The plant's GLB (see veg_export.write_glb). lods 1-3 mesh LODs (+ impostor_lod: crossed quads with its picture
    as the last); lod_files also writes each LOD as <name>_LOD<k>.glb for engines without MSFT_lod."""
    from . import veg_export
    T = grown(name)
    out = Path(out_dir) if out_dir else _dir(name) / "export"
    imp = impostor(name) if impostor_lod else None
    stem = name.replace("#", "_")
    c = veg_export.write_glb(T, str(out / f"{stem}.glb"), stem, triangles=triangles, lods=lods, seasons=seasons, wet=wet, impostor=imp)
    c["total"] = c["wood_triangles"] + c["foliage_triangles"]
    c["over"] = max(0, c["total"] - triangles) if triangles else 0
    c["files"] = [c["path"]]
    if lod_files and len(c["lods"]) > 1:
        base = triangles or c["lods"][0]["triangles"]
        for li, L in enumerate(c["lods"]):
            if L.get("impostor"):
                f = veg_export.write_impostor(T, str(out / f"{stem}_LOD{li}.glb"), stem, imp)
            else:
                f = veg_export.write_glb(T, str(out / f"{stem}_LOD{li}.glb"), stem, triangles=int(base * veg_export.LODS[li][0]),
                                         seasons=seasons, wet=wet, cap=veg_export.LODS[li][1])["path"]
            c["files"].append(f)
    return c


def blender_import(glb: str, frames: int = 0, out: str | None = None, **job) -> dict:
    """Open a GLB with Blender's own glTF importer and report what arrived (objects, uv sets, attributes, variants);
    with frames, also render it swaying from its wind channels into `out`."""
    import subprocess
    import tempfile
    from . import render as _render
    script = Path(__file__).with_name("blender_veg_wind.py")
    with tempfile.TemporaryDirectory(prefix="hifipushie-vegwind-") as tmp:
        rp = Path(tmp) / "report.json"
        jp = Path(tmp) / "job.json"
        jp.write_text(json.dumps({"glb": str(glb), "frames": frames, "out": out, "report": str(rp), **job}))
        r = subprocess.run([_render.BLENDER, "-b", "--factory-startup", "--python-exit-code", "1", "--python", str(script),
                            "--", str(jp)], capture_output=True, text=True, timeout=1800)
        if r.returncode:
            raise RuntimeError(f"blender failed:\n{r.stdout[-1500:]}\n{r.stderr[-1500:]}")
        return json.loads(rp.read_text())


def wind(name: str, triangles: int | None = 20000, seconds: float = 4.0, fps: int = 12, strength: float = 1.0,
         wind_from: float = 270.0, azimuth: float = 0.0, size: int = 480) -> dict:
    """The exported plant swaying: its GLB (at `triangles`) imported by Blender's glTF importer and moved from the
    file's own wind channels by the recipe an engine shader would use. Writes wind_v<n>.mp4 (when ffmpeg is there),
    the frames, and wind_v<n>_strip.png (six frames side by side + their difference from frame 0); returns paths, the
    importer's report and how far the plant moved."""
    import shutil
    import subprocess
    from PIL import Image
    from . import veg_export
    T = grown(name)
    d = _dir(name)
    v = len(history(name))
    stem = name.replace("#", "_")
    glb = veg_export.write_glb(T, str(d / "export" / f"{stem}_wind.glb"), stem, triangles=triangles)["path"]
    fr = d / f"wind_v{v}"
    if fr.exists():
        shutil.rmtree(fr)
    fr.mkdir(parents=True)
    n = int(round(seconds * fps))
    rep = blender_import(glb, frames=n, out=str(fr), fps=fps, strength=strength, height=T["height"], azimuth=azimuth,
                         size=[size, int(size * 1.12)], **{"from": wind_from})
    files = sorted(fr.glob("f_*.png"))
    ims = [np.asarray(Image.open(f).convert("RGB"), np.float32) for f in files]
    pick = [int(round(i * (len(ims) - 1) / 5)) for i in range(6)]
    top = np.concatenate([ims[i] for i in pick], axis=1)
    diff = np.concatenate([np.clip(np.abs(ims[i] - ims[0]) * 4, 0, 255) for i in pick], axis=1)
    strip = str(d / f"wind_v{v}_strip.png")
    Image.fromarray(np.concatenate([top, diff], axis=0).astype(np.uint8)).save(strip)
    moved = float(np.mean([(np.abs(i_ - ims[0]).max(-1) > 24).mean() for i_ in ims[1:]])) if len(ims) > 1 else 0.0
    out = {"frames": str(fr), "strip": strip, "glb": glb, "import": rep, "moved_share": round(moved, 3), "n": len(files),
           "height": float(T["height"]), "displacement": rep.get("displacement") or {}}
    if shutil.which("ffmpeg"):
        mp4 = str(d / f"wind_v{v}.mp4")
        q = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(fps), "-i", str(fr / "f_%03d.png"),
                            "-pix_fmt", "yuv420p", "-vf", "pad=ceil(iw/2)*2:ceil(ih/2)*2", mp4], capture_output=True, text=True)
        if q.returncode == 0:
            out["mp4"] = mp4
    return out


def edit(name: str, ops: list[dict], note: str = "") -> int:
    """Apply edit ops to the stored spec and save: {"op": "guide", "name", "path", "from_year", "until_year",
    "vigour"} (add or redraw), {"op": "remove_guide", "name"}, {"op": "prune", ...a volume...}, {"op": "clear_prunes"},
    {"op": "envelope", ...} (or "envelope": null to remove), {"op": "force", "dir", "strength", "orders"},
    {"op": "clear_forces"}, {"op": "set", "path": "habit.apical.0", "value": 0.6}."""
    spec = load(name)
    spec0, T0 = json.loads(json.dumps(spec)), None
    for i, o in enumerate(ops):
        o = dict(o)
        k = o.pop("op", None)
        if k == "guide":
            g = o.pop("name", None)
            if not g or "path" not in o or len(o["path"]) < 2:
                raise ValueError(f"op {i}: a guide needs a name and a path of at least two [x, y, z] points (m)")
            spec.setdefault("guides", {})[g] = o
        elif k == "take_limb":  # a grown limb becomes a guide: same place and shape, now yours to redraw
            T = T0 = T0 or _tree_of(spec0)  # (the tree as it stood before this batch: the names the caller saw)
            lb = {L["name"]: L for L in vegetation.limbs(T)}
            L = next((q for q in lb.values() if o.get("key") and q["key"] == o["key"]), None) or lb.get(o.get("limb")) \
                or next((q for q in vegetation.limbs(T, 99, 0.0) if q["id"] == o.get("limb")), None)
            if L is None:
                raise ValueError(f"op {i}: no limb {o.get('limb')!r}; this tree's limbs: {sorted(lb)} (the report lists them)")
            if L["guide"]:
                raise ValueError(f"op {i}: {L['name']} is already a guide: redraw it with op guide")
            g = o.get("name") or f"limb_{o.get('limb') or L['name']}"
            path = o.get("path") or vegetation.limb_path(T, L, int(o.get("points", 6)))
            path = [[round(float(x), 3) for x in q] for q in path]
            nodes = vegetation.stout_path(T, T["axes"][L["axis"]]["node"])
            yps = T["spec"]["habit"]["years_per_step"]
            spec.setdefault("guides", {})[g] = {
                "path": path, "on": "trunk", "from_year": L["born_year"],
                "until_year": round(float(min((T["born"][nodes[-1]] + 1) * yps, T["spec"]["age"])), 1), "replaces": [L["key"]]}
        elif k == "dead":  # {"op": "dead", "limb": "SW2" | a volume, "min_radius"}; a compass name is stored as the limb's id
            spec.setdefault("dead", []).append(o)
        elif k == "clear_dead":
            spec["dead"] = []
        elif k == "remove_guide":
            if o.get("name") not in (spec.get("guides") or {}):
                raise ValueError(f"op {i}: no guide {o.get('name')!r}; guides: {sorted(spec.get('guides') or {})}")
            del spec["guides"][o["name"]]
        elif k == "prune":
            if not any(x in o for x in ("box", "sphere", "above", "below", "under")):
                raise ValueError(f"op {i}: a prune needs box [[lo], [hi]], sphere [[c], r], above z, below z or under z")
            spec.setdefault("prune", []).append(o)
        elif k == "remove_prune":  # by its place in the list (get_plant shows it)
            i_ = int(o.get("index", -1))
            if not 0 <= i_ < len(spec.get("prune") or []):
                raise ValueError(f"op {i}: no prune {i_}; there are {len(spec.get('prune') or [])}")
            spec["prune"].pop(i_)
        elif k == "clear_prunes":
            spec["prune"] = []
        elif k == "cut":
            spec.setdefault("cuts", []).append(o)
        elif k == "clear_cuts":
            spec["cuts"] = []
        elif k == "envelope":
            spec["envelope"] = o or None
        elif k == "force":
            spec.setdefault("forces", []).append(o)
        elif k == "clear_forces":
            spec["forces"] = []
        elif k == "set":
            head, _, rest = o["path"].partition(".")
            if head == "habit" and rest:
                vegetation._set_path(spec.setdefault("habit", {}) if rest.partition(".")[0] in spec.get("habit", {}) else
                                     _seed_habit(spec, rest.partition(".")[0]), rest, o["value"])
            else:
                cur = spec
                parts = o["path"].split(".")
                for p_ in parts[:-1]:
                    cur = cur.setdefault(p_, {})
                cur[parts[-1]] = o["value"]
        else:
            raise ValueError(f"op {i}: unknown op {k!r} (guide, take_limb, dead, clear_dead, remove_guide, prune, remove_prune, clear_prunes, cut, "
                             f"clear_cuts, envelope, force, clear_forces, set)")
    return save(name, spec, note=note or "edit")


def _tree_of(spec: dict) -> dict:
    spec = {k: v for k, v in spec.items() if k != "set"}
    key = hashlib.sha1(json.dumps([spec, vegetation.VERSION], sort_keys=True).encode()).hexdigest()
    for k_, t in _GROWN.values():
        if k_ == key:
            return t
    return vegetation.grow(spec)


def set_names(name: str) -> list[str]:
    return [f"{name}#{k + 1}" for k in range(len(variants(load(name))))]


def set_report(name: str) -> str:
    """The set's plants in a line each: seed, age, height, crown width, trunk, nodes."""
    out = []
    for n_ in set_names(name):
        T = grown(n_)
        st = T["stats"]
        w = 2 * float(np.percentile(np.linalg.norm(T["pos"][:, :2], axis=1), 98))
        out.append(f"  {n_}: seed {T['spec']['seed']}, age {T['spec']['age']}, {st['height_m']} m tall, crown {w:.1f} m wide, "
                   f"trunk {st['trunk_diameter_m']} m, {st['nodes']} nodes" + (" STARVED" if st["nodes"] < 12 * st["steps"] else ""))
    hs = [grown(n_)["height"] for n_ in set_names(name)]
    return f"set of {len(hs)} from {name} (heights {min(hs):.1f}-{max(hs):.1f} m):\n" + "\n".join(out)


def export_set(name: str, out_dir: str | None = None, triangles: int | None = None, lods: int = 1,
               seasons=("summer",), wet: bool = False) -> dict:
    """The set as ONE GLB (<name>_set.glb): a node per plant, one bark and one foliage material shared."""
    from . import veg_export
    names = set_names(name)
    if not names:
        raise ValueError(f"{name} has no set: grow_plant(name, patch={{\"set\": {{\"count\": 5}}}})")
    out = Path(out_dir) if out_dir else _dir(name) / "export"
    c = veg_export.write_glb([grown(n_) for n_ in names], str(out / f"{name}_set.glb"),
                             [n_.replace("#", "_") for n_ in names], triangles=triangles, lods=lods, seasons=seasons, wet=wet)
    c["total"] = c["wood_triangles"] + c["foliage_triangles"]
    return c


# ---------------------------------------------------------------- the Blender scene: guides and limbs as curves

def blend_path(name: str) -> Path:
    return _dir(name) / "plant.blend"


def _curves(T: dict) -> list:
    s = T["spec"]
    out = [{"name": g, "kind": "guides", "points": gd["path"], "radius": 0.035} for g, gd in (s.get("guides") or {}).items()]
    for L in vegetation.limbs(T):
        if not L["guide"]:
            out.append({"name": L["name"], "kind": "limbs", "points": vegetation.limb_path(T, L, 6), "radius": 0.02, "key": L["key"]})
    return out


def _read_scene(name: str) -> dict | None:
    """The scene's curves: from the person's running Blender when it has plant.blend open, else from the file."""
    import subprocess
    import tempfile
    from . import render as _render, scene as _scene, veg_look
    bp = blend_path(name)
    code = ("import sys, importlib\n" f"sys.path.insert(0, {str(veg_look.SCRIPT.parent)!r})\n"
            "import blender_vegetation as B\nimportlib.reload(B)\nresult = B.read_curves()")
    r = _scene._live_call(code, timeout=60.0)
    if r and r.get("status") == "ok" and (r.get("result") or {}).get("file") and \
            Path(r["result"]["file"]).resolve() == bp.resolve():
        return {**r["result"], "live": True}
    if not bp.exists():
        return None
    with tempfile.TemporaryDirectory(prefix="hifipushie-veg-") as tmp:
        out = Path(tmp) / "curves.json"
        q = subprocess.run([_render.BLENDER, "-b", str(bp), "--python-exit-code", "1", "--python", str(veg_look.SCRIPT),
                            "--", "pull", str(out)], capture_output=True, text=True, timeout=300)
        if q.returncode:
            raise RuntimeError(f"blender failed:\n{q.stdout[-1500:]}\n{q.stderr[-1500:]}")
        return {**json.loads(out.read_text()), "live": False}


def _moved(a, b, tol=2e-3) -> bool:
    a, b = np.asarray(a, float), np.asarray(b, float)
    return a.shape != b.shape or float(np.abs(a - b).max()) > tol


def pull(name: str) -> list[str]:
    """Bring a person's edits of plant.blend back into the spec: a guide curve they moved (or gave more points) is
    that guide's new path; a LIMB curve they moved becomes a guide (take_limb with their path); a curve they added
    to "guides" is a new guide (it attaches to the nearest wood); a guide curve they deleted is removed. Only what
    moved from what the sync wrote counts, so pulling twice changes nothing. Returns what changed."""
    sc = _read_scene(name)
    if sc is None:
        return []
    spec = load(name)
    guides = spec.get("guides") or {}
    ops, said = [], []
    seen = set()
    for c in sc["guides"]:
        seen.add(c["name"])
        if len(c["points"]) < 2:
            continue
        if c["name"] in guides:
            if c["set"] is not None and _moved(c["points"], c["set"]) and _moved(c["points"], guides[c["name"]]["path"]):
                ops.append({"op": "guide", "name": c["name"], **{**guides[c["name"]], "path": c["points"]}})
                said.append(f"guide {c['name']}: redrawn ({len(c['points'])} points)")
        elif c["name"] not in sc["made"].get("guides", []) or c["set"] is None:
            nm = re.sub(r"[^A-Za-z0-9_]+", "_", c["name"])
            if nm in guides and not _moved(c["points"], guides[nm]["path"]):
                continue  # (pulled before, the scene not written since)
            ops.append({"op": "guide", "name": nm, "path": c["points"]})
            said.append(f"guide {nm}: new, from a curve added in Blender")
    for g in sc["made"].get("guides", []):
        if g not in seen and g in guides:
            ops.append({"op": "remove_guide", "name": g})
            said.append(f"guide {g}: deleted in Blender")
    for c in sc["limbs"]:
        if c["set"] is not None and len(c["points"]) >= 2 and _moved(c["points"], c["set"]):
            if any(c.get("key") in (gd.get("replaces") or []) for gd in guides.values()):
                continue  # (taken on an earlier pull)
            ops.append({"op": "take_limb", "limb": c["name"], "key": c.get("key"), "path": c["points"]})
            said.append(f"limb {c['name']}: moved in Blender, now guide limb_{c['name']}")
    if ops:
        edit(name, ops, note="pulled from Blender: " + "; ".join(said))
    return said


def sync(name: str) -> dict:
    """Pull, then write workspace/plants/<name>/plant.blend from the spec: the plant (bark, foliage instances, ground,
    sun) with its guides (orange) and named limbs (blue) as Bezier curves. Open it in Blender, move curve points
    (or a whole limb), save, and sync again (or pull). A running Blender with the file open is read live and told
    to reload the rewritten file."""
    from . import scene as _scene, veg_look
    came = pull(name)
    T = grown(name)
    bp = blend_path(name)
    info = veg_look.render(T, [], save=str(bp), curves=_curves(T), keep=str(_dir(name) / "scene_maps"))
    live = False
    r = _scene._live_call("import bpy\nresult = {'file': bpy.data.filepath}", timeout=5.0)
    if r and r.get("status") == "ok" and (r.get("result") or {}).get("file") and Path(r["result"]["file"]).resolve() == bp.resolve():
        _scene._live_call("import bpy\nbpy.ops.wm.revert_mainfile()\nresult = {}", timeout=120.0)
        live = True
    return {"blend": str(bp), "pulled": came, "live": live, "guides": len(T["spec"].get("guides") or {}),
            "limbs": sum(1 for L in vegetation.limbs(T) if not L["guide"]), **info}


def _seed_habit(spec: dict, key: str) -> dict:
    """Copy one resolved habit key into the plant's own habit, so a per-order element can be set on it."""
    full = vegetation.resolve(spec)["habit"]
    if key not in full:
        raise ValueError(f"unknown habit key {key!r}: {sorted(full)}")
    spec.setdefault("habit", {})[key] = full[key]
    return spec["habit"]
