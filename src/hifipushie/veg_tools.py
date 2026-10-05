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
    if not re.fullmatch(r"[A-Za-z0-9_\-]+", name):
        raise ValueError("plant names may only contain letters, digits, _ and -")
    return home() / name


def list_plants() -> list[str]:
    return sorted(p.parent.name for p in home().glob("*/plant.json"))


def load(name: str) -> dict:
    p = _dir(name) / "plant.json"
    if not p.exists():
        raise ValueError(f"no plant {name!r}; existing: {list_plants()}")
    return json.loads(p.read_text())


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
    vegetation.resolve(spec)
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
    """After a save: what changed in the spec (old -> new, resolved values for what was unset) and in the tree."""
    after = load(name)
    lines = []
    if before_spec is not None:
        res_old = vegetation.resolve(before_spec)
        for d_ in diff(before_spec, after):
            key = d_.split(":")[0]
            if "(unset)" in d_:  # show what the preset had been giving
                cur = res_old
                try:
                    for part in key.split("."):
                        cur = cur[part]
                    d_ = d_.replace("(unset)", f"{json.dumps(cur)} (from the preset/defaults)")
                except (KeyError, TypeError):
                    pass
            lines.append("  " + d_)
    st = grown(name)["stats"]
    if before_stats:
        lines.append(f"  tree: {before_stats['nodes']} -> {st['nodes']} nodes, {before_stats['height_m']} -> {st['height_m']} m tall, "
                     f"trunk diameter {before_stats['trunk_diameter_m']} -> {st['trunk_diameter_m']} m")
    return "changed:\n" + "\n".join(lines) if lines else ""


def grown(name: str) -> dict:
    spec = load(name)
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


def report(name: str) -> str:
    """The grown plant in numbers: size, form (measured on its own silhouettes), limbs, foliage, guides, and its
    reference match when it has one. WARNINGS last."""
    from . import veg_leaf
    T = grown(name)
    s = T["spec"]
    st = T["stats"]
    warn = []
    out = [f"plant {name}: {s.get('species') or 'no preset'}, age {s['age']} ({st['steps']} growth steps), "
           f"{st['nodes']} nodes, grown in {st['grow_s']} s",
           f"size: {st['height_m']} m tall, trunk DIAMETER {st['trunk_diameter_m']} m at the foot (with its flare), "
           f"branch orders to {st['max_order']}" + (f", {st['pruned_nodes']} nodes cut by prunes" if st.get("pruned_nodes") else "")]
    ms = [vegetation.shape_measures(vegetation.silhouette(T, az, 12, leaves=True)[0]) for az in (0, 90)]
    f = lambda k: round(float(np.mean([m[k] for m in ms])), 2)
    H = T["height"]
    ends = T["pos"][T["ends"]]
    cen = ends[:, :2].mean(0) if len(ends) else np.zeros(2)
    rad_ = float(np.percentile(np.linalg.norm(ends[:, :2] - cen, axis=1), 90)) if len(ends) else 0.0
    zlow = float(np.percentile(ends[:, 2], 3)) if len(ends) else 0.0
    cover = 1 - float(np.mean([m["porosity"] for m in ms]))
    out.append(f"form (in leaf, two side views): width/height {f('width_over_height')}; widest at {f('widest_at')} of the "
               f"height; crown starts at {f('bole') * H:.1f} m (bole {f('bole')}: the lowest height a quarter as wide as the "
               f"widest; the lowest shoot ends hang at {zlow:.1f} m)")
    out.append(f"crown: its middle sits [{cen[0]:+.1f}, {cen[1]:+.1f}] m from the trunk's foot ({np.linalg.norm(cen) / max(rad_, 1e-6):.2f} "
               f"of its radius {rad_:.1f} m: 0 = centred, 0.5+ = plainly swept to one side); cover {cover:.2f} (1 = solid from the side)")
    ang = vegetation.branch_angles(T, 1)
    if ang["n"]:
        drawn = sum(1 for ai in T["guides"].values() if T["axes"][ai]["order"] == 1)
        out.append(f"limbs: {ang['n']} first-order branches ({drawn} drawn; medians of so few jump about), leaving the trunk at {ang['insertion_p10_50_90'][1]} deg "
                   f"(p10-p90 {ang['insertion_p10_50_90'][0]}-{ang['insertion_p10_50_90'][2]}), their far halves "
                   f"{ang['elevation_p10_50_90'][1]} deg above level ({ang['elevation_p10_50_90'][0]} to {ang['elevation_p10_50_90'][2]})")
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
        out.append(f"guide {g}: order {T['axes'][ai]['order']}, {len(nodes)} nodes on its path, "
                   f"{'drawn to its end' if end < 0.3 else f'{end:.1f} m short of its end'}, {kids} branches from it")
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
    if st["nodes"] < 12 * st["steps"]:
        warn.append(f"only {st['nodes']} nodes after {st['steps']} steps: the tree starved (raise habit.vigour, lower habit.shed, "
                    f"or it is shaded by its environment: neighbours/stand)")
    if st["nodes"] > 90000:
        warn.append("over 90k nodes: slow to look at and heavy to export (lower habit.vigour, bud_break or max_order)")
    if s.get("height") and abs(T["height"] - s["height"]) > 0.15 * s["height"]:
        warn.append(f"asked height {s['height']} m, grew {T['height']:.1f} m (edits changed it: a pruned top is shorter)")
    dr = vegetation.droop(T, max(f("bole"), 0.1))
    if dr > 0.1:
        warn.append(f"{dr:.0%} of the shoot ends hang under the crown's base away from the trunk (habit.sag, tropism)")
    d_end = vegetation._norm(T["pos"] - T["pos"][T["parent"]])[T["ends"]]
    down = float((d_end[:, 2] < -0.5).mean()) if len(d_end) else 0.0
    out.append(f"shoot ends: {down:.0%} point steeply down (weeping), {float((d_end[:, 2] > 0.5).mean()) if len(d_end) else 0:.0%} steeply up")
    if down > 0.35 and min(vegetation._per(s["habit"]["tropism"], np.arange(6))) > -0.3:
        warn.append(f"{down:.0%} of the shoot ends hang though the habit isn't a weeping one: lower habit.sag ({s['habit']['sag']}) "
                    f"or raise tropism on the high orders")
    return "\n".join(out + [f"WARNING: {w}" for w in warn])


VIEWS = ("clay", "bare", "leaf", "far", "near", "close")


def _view_jobs(T: dict, views, azimuth: float, size: int, stem) -> tuple[list, list]:
    """Blender view jobs for named views or camera dicts; (jobs, [(name, path)])."""
    from . import veg_look
    import math
    has_leaves = T["spec"].get("season") not in ("winter", "bare", "dead") and not T["spec"].get("decay")
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
            j.update(azimuth=azimuth, leaves=False, clay=True)
        elif x == "bare":
            j.update(azimuth=azimuth, elevation=4, leaves=False)
        elif x == "leaf":
            j.update(azimuth=azimuth, elevation=4, leaves=has_leaves)
        elif x == "far":  # from far enough that the tree is about half the picture's height
            j.update(eye=(toward * max(12.0, 4.5 * H) + [0, 0, 1.7]).tolist(), look=[0, 0, 0.45 * H], fov=24, leaves=has_leaves)
        elif x == "near":  # standing by it: a small tree from close, a big one from 5 m, looking at the trunk and up
            dist = float(np.clip(0.45 * H, 2.0, 5.0))
            j.update(eye=(toward * dist + [0, 0, min(1.7, 0.6 * H)]).tolist(), look=[0, 0, min(0.5 * H, 5.0)], fov=62, leaves=has_leaves)
        elif x == "close":
            j.update(azimuth=azimuth, elevation=8, focus=veg_look.closeup_focus(T, azimuth), span=min(2.4, 0.6 * H), leaves=has_leaves)
        jobs.append(j)
        got.append((x, j["out"]))
    return jobs, got


def look(name: str, views=("clay", "leaf", "far"), azimuth: float = 0.0, size: int = 640, foliage: str | None = None,
         sheet: bool = False) -> list:
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
    jobs, got = _view_jobs(T, views, azimuth, size, lambda x: str(d / f"{x}_v{v}.png"))
    veg_look.render(T, jobs, foliage=foliage)
    return got


def look_group(names: list[str], at: list | None = None, spacing: float | None = None, views=("far",),
               azimuth: float = 0.0, size: int = 640, foliage: str | None = None) -> list:
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
    at = [np.asarray(a, float)[:2] - np.asarray(at[0], float)[:2] for a in at]  # (the first plant stands at the origin)
    d = home() / "_groups"
    d.mkdir(parents=True, exist_ok=True)
    tag = "+".join(names)[:80]
    span = max(float(np.linalg.norm(a)) for a in at) + 0.4 * H
    c_, s_ = math.cos(math.radians(azimuth)), math.sin(math.radians(azimuth))
    toward = np.array([-s_, -c_, 0.0])
    cen = np.r_[np.mean(at, axis=0), 0.0]
    jobs, got = [], []
    for k, x in enumerate(views):
        nm = x if isinstance(x, str) else x.get("name", f"camera{k + 1}")
        o = str(d / f"{tag}_{nm}.png")
        j = {"out": o, "size": [int(size * 1.3), size], "sun": [azimuth + 235, 40]}
        if isinstance(x, dict):
            j.update(eye=x["eye"], look=x["look"], fov=x.get("fov", 40))
        elif x == "far":
            j.update(eye=(cen + toward * max(15.0, 3.2 * (H + span)) + [0, 0, 1.7]).tolist(), look=(cen + [0, 0, 0.45 * H]).tolist(), fov=28)
        elif x == "near":
            j.update(eye=(cen + toward * (span + 3.0) + [0, 0, 1.7]).tolist(), look=(cen + [0, 0, 0.45 * H]).tolist(), fov=60)
        elif x == "clay":
            j.update(eye=(cen + toward * max(15.0, 3.2 * (H + span)) + [0, 0, 1.7]).tolist(), look=(cen + [0, 0, 0.45 * H]).tolist(),
                     fov=28, clay=True, leaves=False)
        elif x == "top":
            j.update(eye=(cen + [0, -0.01, 3.0 * (H + span)]).tolist(), look=cen.tolist(), fov=30)
        else:
            raise ValueError(f"group views: far, near, clay, top or a camera {{'eye', 'look', 'fov'}} (got {x!r})")
        jobs.append(j)
        got.append((nm, o))
    others = [(t, a.tolist(), (i * 137.5) % 360) for i, (t, a) in enumerate(zip(trees[1:], at[1:]), start=1)]
    veg_look.render(trees[0], jobs, foliage=foliage, others=others)
    return got


def export(name: str, out_dir: str | None = None, triangles: int | None = None) -> dict:
    from . import veg_export
    T = grown(name)
    out = Path(out_dir) if out_dir else _dir(name) / "export"
    return veg_export.write_glb(T, str(out / f"{name}.glb"), name, triangles=triangles)


def edit(name: str, ops: list[dict], note: str = "") -> int:
    """Apply edit ops to the stored spec and save: {"op": "guide", "name", "path", "from_year", "until_year",
    "vigour"} (add or redraw), {"op": "remove_guide", "name"}, {"op": "prune", ...a volume...}, {"op": "clear_prunes"},
    {"op": "envelope", ...} (or "envelope": null to remove), {"op": "force", "dir", "strength", "orders"},
    {"op": "clear_forces"}, {"op": "set", "path": "habit.apical.0", "value": 0.6}."""
    spec = load(name)
    for i, o in enumerate(ops):
        o = dict(o)
        k = o.pop("op", None)
        if k == "guide":
            g = o.pop("name", None)
            if not g or "path" not in o or len(o["path"]) < 2:
                raise ValueError(f"op {i}: a guide needs a name and a path of at least two [x, y, z] points (m)")
            spec.setdefault("guides", {})[g] = o
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
            raise ValueError(f"op {i}: unknown op {k!r} (guide, remove_guide, prune, clear_prunes, envelope, force, "
                             f"clear_forces, set)")
    return save(name, spec, note=note or "edit")


def _seed_habit(spec: dict, key: str) -> dict:
    """Copy one resolved habit key into the plant's own habit, so a per-order element can be set on it."""
    full = vegetation.resolve(spec)["habit"]
    if key not in full:
        raise ValueError(f"unknown habit key {key!r}: {sorted(full)}")
    spec.setdefault("habit", {})[key] = full[key]
    return spec["habit"]
