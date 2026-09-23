"""On-disk models: spec.json is the source of truth; every change is checkpointed in history/."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import time
from pathlib import Path

import numpy as np

from . import sdf, spec as specmod

HOME = Path(os.environ.get("HIFIPUSHIE_HOME") or Path.cwd() / "workspace")
BUILD_VERSION = 8  # bump when meshing changes, so cached builds are redone


def _dir(name: str) -> Path:
    if not re.fullmatch(r"[A-Za-z0-9_\-]+", name):
        raise ValueError("model names may only contain letters, digits, _ and -")
    return HOME / name


def list_models() -> list[str]:
    return sorted(p.parent.name for p in HOME.glob("*/spec.json"))


def load(name: str) -> dict:
    p = _dir(name) / "spec.json"
    if not p.exists():
        raise ValueError(f"no model {name!r}; existing: {list_models()}")
    return json.loads(p.read_text())


def save(name: str, spec: dict, note: str = "") -> int:
    specmod.compile_prims(spec)  # validate before writing
    d = _dir(name)
    (d / "history").mkdir(parents=True, exist_ok=True)
    version = len(list((d / "history").glob("*.json"))) + 1
    entry = {"version": version, "time": time.strftime("%Y-%m-%d %H:%M:%S"), "note": note, "spec": spec}
    (d / "history" / f"{version:04d}.json").write_text(json.dumps(entry, indent=1))
    (d / "spec.json").write_text(json.dumps(spec, indent=1))
    return version


def history(name: str) -> list[dict]:
    d = _dir(name) / "history"
    out = []
    for p in sorted(d.glob("*.json")):
        e = json.loads(p.read_text())
        out.append({k: e[k] for k in ("version", "time", "note")})
    return out


def version_spec(name: str, version: int) -> dict:
    p = _dir(name) / "history" / f"{version:04d}.json"
    if not p.exists():
        raise ValueError(f"{name} has no version {version}")
    return json.loads(p.read_text())["spec"]


def apply_ops(spec: dict, ops: list[dict]) -> dict:
    """Edit ops:
      {"op": "set", "kind": "joints|bones|blobs", "name": n, "value": {...}}   merge fields (creates if new)
      {"op": "delete", "kind": ..., "name": n}
      {"op": "rename", "kind": ..., "name": n, "to": m}   (joint renames update references)
      {"op": "move", "joints": [names], "delta": [dx, dy, dz]}
      {"op": "scale_r", "joints": [names], "factor": f}
      {"op": "global", "value": {"blend": 0.04, "symmetry": true}}
    """
    s = copy.deepcopy(spec)
    for o in ops:
        kind = o.get("kind")
        if kind is not None and kind not in specmod.KINDS:
            raise ValueError(f"bad kind {kind!r}")
        match o.get("op"):
            case "set":
                cur = s.setdefault(kind, {}).setdefault(o["name"], {})
                for k, v in o["value"].items():
                    if v is None:
                        cur.pop(k, None)
                    else:
                        cur[k] = v
            case "delete":
                if s.get(kind, {}).pop(o["name"], None) is None:
                    raise ValueError(f"no {kind[:-1]} {o['name']!r}")
            case "rename":
                s[kind][o["to"]] = s[kind].pop(o["name"])
                if kind == "joints":
                    for b in s["bones"].values():
                        for e in ("a", "b"):
                            if b[e] == o["name"]:
                                b[e] = o["to"]
                    for bl in s["blobs"].values():
                        if bl.get("at") == o["name"]:
                            bl["at"] = o["to"]
                    for kit in s.get("kits", {}).values():
                        for key in ("wrist", "head"):
                            if kit.get(key) == o["name"]:
                                kit[key] = o["to"]
                if kind == "bones":
                    for bl in s["blobs"].values():
                        if isinstance(bl.get("at"), dict) and bl["at"].get("bone") == o["name"]:
                            bl["at"]["bone"] = o["to"]
            case "move":
                for n in o["joints"]:
                    s["joints"][n]["pos"] = [a + b for a, b in zip(s["joints"][n]["pos"], o["delta"])]
            case "scale_r":
                for n in o["joints"]:
                    s["joints"][n]["r"] = s["joints"][n].get("r", 0.05) * o["factor"]
            case "global":
                s.update(o["value"])
            case other:
                raise ValueError(f"unknown op {other!r}")
    return s


def build(name: str, resolution: int = 160, box=None) -> dict:
    """Mesh the current spec (cached by expanded spec + resolution). Returns paths and stats.
    With box=(lo, hi), only that region is meshed, at `resolution` voxels across the box (close-ups);
    that goes to its own cache files and has no silhouettes."""
    spec = load(name)
    tag = "" if box is None else json.dumps([np.round(b, 4).tolist() for b in box])
    # keyed on the kit-expanded spec, so changes to kit code (or what a face is seated on) rebuild
    key = hashlib.sha1((json.dumps(specmod.expand_mirror(spec), sort_keys=True, default=float)
                        + f"@{resolution}/{BUILD_VERSION}{tag}").encode()).hexdigest()[:12]
    bd = _dir(name) / "build"
    bd.mkdir(exist_ok=True)
    mesh_p, sil_p, meta_p = ((bd / "mesh.npz", bd / "sil.npz", bd / "meta.json") if box is None else
                             (bd / "closeup.npz", None, bd / "closeup_meta.json"))
    if meta_p.exists() and json.loads(meta_p.read_text()).get("key") == key and mesh_p.exists():
        return json.loads(meta_p.read_text())
    t = time.time()
    prims = specmod.compile_prims(spec)
    lo, voxel, shape = sdf.frame(prims, resolution, box=box)
    defs = spec.get("parts") or {}
    V, F, N, P, C, fields, names, empty = [], [], [], [], [], [], [], []
    for i, ps in enumerate(sdf.streams(prims)):  # each part meshed on its own, on one shared grid
        name = ps[0].part
        f = sdf.evaluate(ps, at=(lo, voxel, shape)).field
        fields.append(f)
        try:
            v, fc = sdf.mesh(sdf.Grid(f, lo, voxel))
        except ValueError:
            empty.append(name)  # nothing of it inside this grid (or its region misses the base)
            continue
        v, n = sdf.project(ps, v, fc, voxel)
        F.append(fc + sum(len(x) for x in V))
        V.append(v)
        N.append(n)
        P.append(np.full(len(v), len(names), np.int16))
        C.append(np.tile(part_colour(name, defs, len(names)), (len(v), 1)))
        names.append(name)
    if not V:
        raise ValueError("field has no interior: the shape is empty")
    verts, faces, normals = np.concatenate(V), np.concatenate(F), np.concatenate(N)
    np.savez(mesh_p, verts=verts, faces=faces, normals=normals, part=np.concatenate(P),
             part_names=np.array(names), part_colors=np.concatenate(C))
    grid = sdf.Grid(np.minimum.reduce(fields), lo, voxel)
    if box is None:
        sil = sdf.silhouettes(grid)
        np.savez_compressed(sil_p, **{f"{k}_mask": v["mask"] for k, v in sil.items()},
                            **{f"{k}_uv": np.array([*v["u"], *v["v"]]) for k, v in sil.items()})
    lo, hi = verts.min(0), verts.max(0)
    meta = {"key": key, "mesh": str(mesh_p), "verts": len(verts), "faces": len(faces),
            "voxel": grid.voxel, "bounds": [lo.tolist(), hi.tolist()], "seconds": round(time.time() - t, 2),
            "parts": names, "empty_parts": empty}
    meta_p.write_text(json.dumps(meta))
    return meta


PALETTE = [(0.9, 0.9, 0.9), (0.62, 0.72, 0.9), (0.9, 0.68, 0.55), (0.66, 0.85, 0.66), (0.88, 0.8, 0.55),
           (0.8, 0.65, 0.88)]


def part_colour(name: str, defs: dict, index: int) -> np.ndarray:
    """RGBA for a part's clay: its "color" from spec["parts"], else a palette entry (the body stays neutral)."""
    rgb = (defs.get(name) or {}).get("color") or PALETTE[index % len(PALETTE)]
    return np.array([*rgb[:3], 1.0], np.float32)


def extent(name: str) -> np.ndarray:
    """The model's bounding box from its primitives, without building: [lo, hi]."""
    adds = [p for p in specmod.compile_prims(load(name)) if p.op == "add"]
    return np.array([np.min([p.lo for p in adds], axis=0), np.max([p.hi for p in adds], axis=0)])


def silhouette(name: str, view: str) -> dict:
    z = np.load(_dir(name) / "build" / "sil.npz")
    uv = z[f"{view}_uv"]
    return {"mask": z[f"{view}_mask"], "u": (uv[0], uv[1]), "v": (uv[2], uv[3])}


def export_obj(name: str, path: Path) -> Path:
    z = np.load(_dir(name) / "build" / "mesh.npz")
    faces = z["faces"]
    part = z["part"][faces[:, 0]] if "part" in z else np.zeros(len(faces), int)
    names = [str(n) for n in z["part_names"]] if "part_names" in z else [name]
    with open(path, "w") as f:
        f.write(f"# hifipushie {name}: one object per part ({', '.join(names)})\n")
        np.savetxt(f, z["verts"], fmt="v %.5f %.5f %.5f")
        np.savetxt(f, z["normals"], fmt="vn %.4f %.4f %.4f")
        for i, pn in enumerate(names):
            f.write(f"o {name}_{pn}\n")
            np.savetxt(f, np.repeat(faces[part == i] + 1, 2, axis=1), fmt="f %d//%d %d//%d %d//%d")
    return path


def refs_dir(name: str) -> Path:
    p = _dir(name) / "refs"
    p.mkdir(parents=True, exist_ok=True)
    return p
