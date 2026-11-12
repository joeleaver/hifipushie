"""`edit`, and the Blender scene: guides and limbs as curves, pull, sync, the seeded habit. Part of the plant tools (veg_tools.py has the overview)."""
from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np

from . import vegetation
from . import vegetation_fit, vegetation_tree
from .veg_tools import _dir, _tree_of, grown, load, save

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
            lb = {L["name"]: L for L in vegetation_tree.limbs(T)}
            L = next((q for q in lb.values() if o.get("key") and q["key"] == o["key"]), None) or lb.get(o.get("limb")) \
                or next((q for q in vegetation_tree.limbs(T, 99, 0.0) if q["id"] == o.get("limb")), None)
            if L is None:
                raise ValueError(f"op {i}: no limb {o.get('limb')!r}; this tree's limbs: {sorted(lb)} (the report lists them)")
            if L["guide"]:
                raise ValueError(f"op {i}: {L['name']} is already a guide: redraw it with op guide")
            g = o.get("name") or f"limb_{o.get('limb') or L['name']}"
            path = o.get("path") or vegetation_tree.limb_path(T, L, int(o.get("points", 6)))
            path = [[round(float(x), 3) for x in q] for q in path]
            nodes = vegetation_tree.stout_path(T, T["axes"][L["axis"]]["node"])
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
                vegetation_fit._set_path(spec.setdefault("habit", {}) if rest.partition(".")[0] in spec.get("habit", {}) else
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


# ---------------------------------------------------------------- the Blender scene: guides and limbs as curves
def blend_path(name: str) -> Path:
    return _dir(name) / "plant.blend"


def _curves(T: dict) -> list:
    s = T["spec"]
    out = [{"name": g, "kind": "guides", "points": gd["path"], "radius": 0.035} for g, gd in (s.get("guides") or {}).items()]
    for L in vegetation_tree.limbs(T):
        if not L["guide"]:
            out.append({"name": L["name"], "kind": "limbs", "points": vegetation_tree.limb_path(T, L, 6), "radius": 0.02, "key": L["key"]})
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
            "limbs": sum(1 for L in vegetation_tree.limbs(T) if not L["guide"]), **info}


def _seed_habit(spec: dict, key: str) -> dict:
    """Copy one resolved habit key into the plant's own habit, so a per-order element can be set on it."""
    full = vegetation.resolve(spec)["habit"]
    if key not in full:
        raise ValueError(f"unknown habit key {key!r}: {sorted(full)}")
    spec.setdefault("habit", {})[key] = full[key]
    return spec["habit"]
