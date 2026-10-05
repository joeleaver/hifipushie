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
           f"size: {st['height_m']} m tall, trunk {st['trunk_diameter_m']} m at the foot, orders to {st['max_order']}"]
    ms = [vegetation.shape_measures(vegetation.silhouette(T, az, 12, leaves=True)[0]) for az in (0, 90)]
    f = lambda k: round(float(np.mean([m[k] for m in ms])), 2)
    out.append(f"form (in leaf, two side views): width/height {f('width_over_height')}, bole {f('bole')} of the height, "
               f"widest at {f('widest_at')}, lopsided {round(float(ms[0]['lopsided']), 2)} / {round(float(ms[1]['lopsided']), 2)} "
               f"(+ = toward +x / +y)")
    ang = vegetation.branch_angles(T, 1)
    if ang["n"]:
        out.append(f"limbs: {ang['n']} first-order branches, leaving the trunk at {ang['insertion_p10_50_90'][1]} deg "
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
            warn.append(f"guide {g} has no nodes (its from_year {s['guides'][g].get('from_year', 0)} is past the tree's age, "
                        f"or it was pruned)")
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
    if st["nodes"] < 300:
        warn.append("very few nodes: the tree starved (raise habit.vigour or lower habit.shed) or is very young")
    if st["nodes"] > 90000:
        warn.append("over 90k nodes: slow to look at and heavy to export (lower habit.vigour, bud_break or max_order)")
    if s.get("height") and abs(T["height"] - s["height"]) > 0.15 * s["height"]:
        warn.append(f"asked height {s['height']} m, grew {T['height']:.1f} m (edits changed it: a pruned top is shorter)")
    dr = vegetation.droop(T, max(f("bole"), 0.1))
    if dr > 0.1:
        warn.append(f"{dr:.0%} of the shoot ends hang under the crown's base away from the trunk (habit.sag, tropism)")
    return "\n".join(out + [f"WARNING: {w}" for w in warn])


VIEWS = ("clay", "bare", "leaf", "far", "near", "close")


def look(name: str, views=("clay", "leaf", "far"), azimuth: float = 0.0, size: int = 640, foliage: str | None = None,
         sheet: bool = False) -> list:
    """Render views of the plant; returns [(view name, png path)]. clay = the bare skeleton lit as clay, bare = in
    colour without leaves, leaf = in leaf (both orthographic side views from `azimuth`), far = from 70 m at eye
    height, near = from 5 m looking up, close = 2.4 m of foliage. sheet=True makes the reference sheet instead (the
    photo, outlines over each other, every view, numbers): it needs a reference."""
    from . import veg_look
    import math
    T = grown(name)
    d = _dir(name)
    v = len(history(name))
    if sheet:
        ref = reference(name)
        if not ref:
            raise ValueError("no reference yet: plant_reference(name, image_path, mask) first")
        out = str(d / f"sheet_v{v}.png")
        veg_look.reference_sheet(load(name), ref, out, bare=ref["bare"], title=name, foliage=foliage)
        return [("sheet", out)]
    bad = [x for x in views if x not in VIEWS]
    if bad:
        raise ValueError(f"unknown views {bad}: {list(VIEWS)}")
    has_leaves = T["spec"].get("season") not in ("winter", "bare", "dead") and not T["spec"].get("decay")
    H = T["height"]
    c_, s_ = math.cos(math.radians(azimuth)), math.sin(math.radians(azimuth))
    toward = np.array([-s_, -c_, 0.0])
    sz = [int(size * 0.95), size]
    jobs, got = [], []
    for x in views:
        o = str(d / f"{x}_v{v}.png")
        j = {"out": o, "size": sz, "sun": [azimuth + 235, 40]}
        if x == "clay":
            j.update(azimuth=azimuth, leaves=False, clay=True)
        elif x == "bare":
            j.update(azimuth=azimuth, elevation=4, leaves=False)
        elif x == "leaf":
            j.update(azimuth=azimuth, elevation=4, leaves=has_leaves)
        elif x == "far":
            j.update(eye=(toward * max(70.0, 3.5 * H) + [0, 0, 1.7]).tolist(), look=[0, 0, 0.42 * H], fov=22, leaves=has_leaves)
        elif x == "near":
            j.update(eye=(toward * 5.0 + [0, 0, 1.7]).tolist(), look=[0, 0, min(0.5 * H, 6.0)], fov=62, leaves=has_leaves)
        elif x == "close":
            j.update(azimuth=azimuth, elevation=8, focus=veg_look.closeup_focus(T, azimuth), span=2.4, leaves=has_leaves)
        jobs.append(j)
        got.append((x, o))
    veg_look.render(T, jobs, foliage=foliage)
    return got


def export(name: str, out_dir: str | None = None) -> dict:
    from . import veg_export
    T = grown(name)
    out = Path(out_dir) if out_dir else _dir(name) / "export"
    return veg_export.write_glb(T, str(out / f"{name}.glb"), name)


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
            if not any(x in o for x in ("box", "sphere", "above", "below")):
                raise ValueError(f"op {i}: a prune needs box [[lo], [hi]], sphere [[c], r], above z or below z")
            spec.setdefault("prune", []).append(o)
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
