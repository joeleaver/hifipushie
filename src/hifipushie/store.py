"""On-disk models: spec.json is the source of truth; every change is checkpointed in history/."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import threading
import time
from pathlib import Path

import numpy as np

from . import sdf, spec as specmod

HOME = Path(os.environ.get("HIFIPUSHIE_HOME") or Path.cwd() / "workspace")
BUILD_VERSION = 15  # bump when meshing changes, so cached builds are redone


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
    from . import paint, realism, strokes
    realism.validate(spec)
    strokes.check(spec)  # cheap static checks first: seating errors would only show up at build time
    prims = specmod.compile_prims(spec)  # validate before writing
    paint.validate(spec)
    paint.check_refs(spec, prims)  # names paint points at: here, not minutes into a sync
    for pn, d in (spec.get("parts") or {}).items():
        part_colour(pn, spec["parts"], 0)
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
      {"op": "delete", "kind": ..., "name": n}   or {"op": "delete", "tag": t} (every bone/blob tagged t)
      {"op": "rename", "kind": ..., "name": n, "to": m}   (joint renames update references)
      {"op": "move", "joints": [names], "delta": [dx, dy, dz]}
      {"op": "scale_r", "joints": [names], "factor": f}
      {"op": "global", "value": {"blend": 0.04, "symmetry": true}}
    """
    s = copy.deepcopy(spec)
    for o in ops:
        kind = o.get("kind")
        if kind is not None and kind not in (*specmod.KINDS, "paint", "parts", "prefabs", "instances"):
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
                if "tag" in o:  # every stored bone/blob carrying that tag
                    gone = [(k, n) for k in (kind,) if k for n, el in list(s.get(k, {}).items())
                            if o["tag"] in (el.get("tags") or [])] if kind else \
                        [(k, n) for k in ("bones", "blobs") for n, el in list(s.get(k, {}).items())
                         if o["tag"] in (el.get("tags") or [])]
                    if not gone:
                        raise ValueError(f"nothing tagged {o['tag']!r}")
                    for k, n in gone:
                        del s[k][n]
                elif s.get(kind, {}).pop(o["name"], None) is None:
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
    lkey = (name, "full" if box is None else "closeup")
    with _LOCKS_GUARD:
        lock = _LOCKS.setdefault(lkey, threading.Lock())
    with lock:  # MCP tools run on worker threads: two builds of one model must not share its live grids at once
        if meta_p.exists() and json.loads(meta_p.read_text()).get("key") == key and mesh_p.exists():
            return json.loads(meta_p.read_text())
        try:
            return _build(spec, key, resolution, box, lkey, mesh_p, sil_p, meta_p)
        except BaseException:
            _LIVE.pop(lkey, None)  # grids or meshes may be half updated: the next build starts cold
            raise


def _build(spec, key, resolution, box, lkey, mesh_p, sil_p, meta_p) -> dict:
    t = time.time()
    prims = specmod.compile_prims(spec)
    lo, voxel, shape = sdf.frame(prims, resolution, box=box)
    defs = spec.get("parts") or {}
    live = _LIVE.setdefault(lkey, {})
    V, F, N, P, C, sils, names, empty, redone = [], [], [], [], [], [], [], [], []
    changed: dict[str, list] = {}
    for ps in sdf.streams(prims):  # each part meshed on its own, on one shared grid
        pname = ps[0].part
        st = live.setdefault(pname, {"grid": sdf.PartGrid(), "mesh": None})
        base = (defs.get(pname) or {}).get("shell")
        grow = float((defs.get(pname) or {}).get("offset", 0.006)) + 2 * voxel
        extra = [(a - grow, b + grow) for a, b in changed.get(base, [])]  # where its base part changed
        f, boxes = st["grid"].update(ps, (lo, voxel, shape), extra)
        changed[pname] = boxes
        if boxes or st["mesh"] is None:
            st["mesh"] = _mesh_part(ps, f, lo, voxel, boxes, st)
            redone.append(pname)
        if st["mesh"] is False:
            empty.append(pname)  # nothing of it inside this grid (or its region misses the base)
            continue
        v, fc, n, sil = st["mesh"]
        sils.append(sil)
        F.append(fc + sum(len(x) for x in V))
        V.append(v)
        N.append(n)
        P.append(np.full(len(v), len(names), np.int16))
        C.append(np.tile(part_colour(pname, defs, len(names)), (len(v), 1)))
        names.append(pname)
    for gone in set(live) - {ps[0].part for ps in sdf.streams(prims)}:
        live.pop(gone)
    if not V:
        raise ValueError("field has no interior: the shape is empty")
    verts, faces, normals = np.concatenate(V), np.concatenate(F), np.concatenate(N)
    np.savez(mesh_p, verts=verts, faces=faces, normals=normals, part=np.concatenate(P),
             part_names=np.array(names), part_colors=np.concatenate(C))
    if box is None:
        sil = {k: {**sils[0][k], "mask": np.logical_or.reduce([x[k]["mask"] for x in sils])} for k in sils[0]}
        np.savez_compressed(sil_p, **{f"{k}_mask": v["mask"] for k, v in sil.items()},
                            **{f"{k}_uv": np.array([*v["u"], *v["v"]]) for k, v in sil.items()})
    lo, hi = verts.min(0), verts.max(0)
    meta = {"key": key, "mesh": str(mesh_p), "verts": len(verts), "faces": len(faces),
            "voxel": float(voxel), "bounds": [lo.tolist(), hi.tolist()], "seconds": round(time.time() - t, 2),
            "parts": names, "empty_parts": empty, "rebuilt_parts": redone}
    meta_p.write_text(json.dumps(meta))
    return meta


PALETTE = [(0.9, 0.9, 0.9), (0.62, 0.72, 0.9), (0.9, 0.68, 0.55), (0.66, 0.85, 0.66), (0.88, 0.8, 0.55),
           (0.8, 0.65, 0.88)]


def part_colour(name: str, defs: dict, index: int) -> np.ndarray:
    """RGBA for a part's clay: its "color" from spec["parts"], else a palette entry (the body stays neutral)."""
    from .paint import colour
    c = (defs.get(name) or {}).get("color")
    rgb = colour(c, f"parts.{name}.color") if c is not None else PALETTE[index % len(PALETTE)]
    return np.array([*rgb[:3], 1.0], np.float32)


# Per model: each part's grid and mesh from the last build, so the next build redoes only what changed.
# Lives as long as the process (the MCP server); a fresh process just builds everything once.
_LIVE: dict[tuple, dict] = {}
_LOCKS: dict[tuple, threading.Lock] = {}
_LOCKS_GUARD = threading.Lock()


def _mesh_part(prims, field, lo, voxel, boxes, st):
    """Mesh one part and project it onto the exact surface, reusing the projection of every vertex that sits
    where it sat last build (same smoothed position) outside the regions that changed."""
    try:
        v, fc = sdf.mesh(sdf.Grid(field, lo, voxel))
    except ValueError:
        st["proj"] = None
        return False
    keys = np.round(v.astype(np.float64) / (voxel * 1e-4)).astype(np.int64)
    reuse = None
    old = st.get("proj")
    if old is not None:
        okeys, ov, og = old
        kv = keys.view([("x", np.int64), ("y", np.int64), ("z", np.int64)]).ravel()
        ok_ = okeys.view([("x", np.int64), ("y", np.int64), ("z", np.int64)]).ravel()
        order = np.argsort(ok_)
        pos = np.clip(np.searchsorted(ok_[order], kv), 0, len(ok_) - 1)
        match = ok_[order][pos] == kv
        near = np.zeros(len(v), bool)
        for a, b in boxes:
            near |= np.all((v >= a - voxel) & (v <= b + voxel), axis=1)
        mask = match & ~near
        src = order[pos[mask]]
        reuse = (mask, ov[src], og[src])
    vp, n, (rv, rg) = sdf.project(prims, v, fc, voxel, reuse=reuse, keep=True)
    st["proj"] = (keys, rv, rg)
    return vp, fc, n, sdf.silhouettes(sdf.Grid(field, lo, voxel))


def clip_planes(clip) -> list[tuple[np.ndarray, np.ndarray]]:
    """Section planes as (point, unit normal); everything on the side the normal points into is cut away.
    clip: {"z": h} (drop above z = h; also "x", "y"), {"-y": c} (drop below y = c, i.e. the front of a model
    facing -Y; also "-x", "-z"), {"point": [x,y,z], "normal": [x,y,z]}, or a list of these (all applied)."""
    if not clip:
        return []
    out = []
    for c in (clip if isinstance(clip, list) else [clip]):
        if not isinstance(c, dict):
            raise ValueError(f"bad clip {c!r}: use {{'z': 2.2}}, {{'-y': 0}} or {{'point': [...], 'normal': [...]}}")
        if "normal" in c:
            n = np.asarray(c["normal"], float)
            if n.shape != (3,) or np.linalg.norm(n) < 1e-9:
                raise ValueError("clip normal must be a non-zero [x, y, z]")
            out.append((np.asarray(c.get("point", [0, 0, 0]), float), n / np.linalg.norm(n)))
            continue
        for k, v in c.items():
            ax = k.lstrip("+-").lower()
            if ax not in ("x", "y", "z"):
                raise ValueError(f"bad clip key {k!r}: x, y, z, -x, -y, -z, or point + normal")
            n = np.eye(3)["xyz".index(ax)] * (-1.0 if k.startswith("-") else 1.0)
            out.append((np.abs(n) * float(v), n))
    return out


def view_mesh(mesh: Path, keep_parts: list[str] | None, planes, frusta: list[dict] | None = None) -> Path:
    """The mesh with only some parts and/or cut by section planes (`clip_planes`), as <stem>_view.npz, cached
    by mesh + filter. Faces wholly beyond a plane go; vertices beyond it on the faces that stay are pulled onto
    it, so the cut edge is straight. frusta: perspective camera frames (render.camera_frame); faces outside
    all of them go too (nothing else would see them, so there's nothing to paint there). Keeps every
    per-vertex array (paint, curvature colours) and records the base mesh and each vertex's index in it
    ("src", so painting can reuse the base mesh's paint or inputs), and the bounds of the kept parts before
    cutting ("frame_bounds", to frame the views)."""
    out = mesh.with_name(mesh.stem + "_view.npz")
    stamp = json.dumps([mesh.stat().st_mtime_ns, str(mesh), keep_parts,
                        [[p.tolist(), n.tolist()] for p, n in planes],
                        [[f["eye"], f["dir"], f["up"], f["fov"]] for f in frusta or []]])
    if out.exists():
        with np.load(out) as z:
            if "stamp" in z and str(z["stamp"]) == stamp:
                return out
    z = dict(np.load(mesh))
    nv = len(z["verts"])
    names = [str(n) for n in z["part_names"]]
    verts, faces = z["verts"].astype(np.float64), z["faces"]
    keep_v = (np.ones(nv, bool) if keep_parts is None else
              np.isin(z["part"], [names.index(p) for p in keep_parts if p in names]))
    if not keep_v.any():
        raise ValueError("none of the parts to show are in this build")
    fb = np.array([verts[keep_v].min(0), verts[keep_v].max(0)])
    keep_f = keep_v[faces[:, 0]]
    for p, n in planes:
        s = (verts - p) @ n
        far = s > 0
        keep_f &= ~far[faces].all(1)
        used = np.zeros(nv, bool)
        used[faces[keep_f]] = True
        mv = far & used
        verts[mv] -= s[mv, None] * n
    if frusta:
        seen = np.zeros(nv, bool)
        for fr in frusta:
            d, up = np.asarray(fr["dir"], float), np.asarray(fr["up"], float)
            right = np.cross(up, d)
            right /= np.linalg.norm(right)
            up = np.cross(d, right)
            q = verts - np.asarray(fr["eye"], float)
            depth = -(q @ d)
            lim = depth * np.tan(np.radians(fr["fov"]) / 2) * 1.05 + 0.05  # a little slack at the edges
            seen |= (depth > -0.05) & (np.abs(q @ right) <= lim) & (np.abs(q @ up) <= lim)
        keep_f &= seen[faces].any(1)
    if not keep_f.any():
        raise ValueError("the clip removes everything shown")
    used = np.zeros(nv, bool)
    used[faces[keep_f]] = True
    src = np.flatnonzero(used)
    remap = np.full(nv, -1, np.int64)
    remap[src] = np.arange(len(src))
    res = {k: (a[src] if k not in ("part_names", "faces") and a.ndim and len(a) == nv else a)
           for k, a in z.items() if k not in ("stamp", "coverage")}
    res["verts"] = verts[src].astype(z["verts"].dtype)
    res["faces"] = remap[faces[keep_f]].astype(faces.dtype)
    np.savez(out, **res, src=src, base=np.array(str(mesh)), frame_bounds=fb, stamp=np.array(stamp))
    return out


def section_caps(name: str, view: Path, planes, keep_parts: list[str] | None, voxel: float) -> Path | None:
    """Flat caps where the section planes cut solid parts, so cut walls read as solid (and the insides of the
    kept parts don't show through): cells of a grid on each plane (half a voxel, at most 1200 across the shown
    parts' extent) whose centre is inside a shown part's exact field, coloured by that part's clay darkened.
    Cached next to the view mesh. None when nothing solid is cut."""
    out = view.with_name(view.stem + "_caps.npz")
    with np.load(view) as z:
        stamp = str(z["stamp"])
        fb = z["frame_bounds"]
        names = [str(n) for n in z["part_names"]]
        pc = z["part_colors"][:, :3]
        part = z["part"]
    if out.exists():
        with np.load(out) as zc:
            if str(zc["stamp"]) == stamp:
                return out if len(zc["faces"]) else None
    spec = load(name)
    streams = {ps[0].part: ps for ps in sdf.streams(specmod.compile_prims(spec))}
    shown = [p for p in names if (keep_parts is None or p in keep_parts) and p in streams]
    defs = spec.get("parts") or {}
    colour = {}
    for i, pn in enumerate(names):
        sel = np.flatnonzero(part == i)
        colour[pn] = (pc[sel[0]] if len(sel) else part_colour(pn, spec.get("parts") or {}, i)[:3]) * 0.55
    V, F, C, N = cap_arrays(streams, shown, defs, colour, planes, fb, voxel)
    if not V:
        np.savez(out, verts=np.zeros((0, 3), np.float32), faces=np.zeros((0, 3), np.int32), stamp=np.array(stamp))
        return None
    np.savez(out, verts=np.concatenate(V).astype(np.float32), faces=np.concatenate(F).astype(np.int32),
             normals=np.concatenate(N).astype(np.float32), part_colors=np.concatenate(C).astype(np.float32),
             stamp=np.array(stamp))
    return out


def cap_arrays(streams: dict, shown: list, defs: dict, colour: dict, planes, fb, voxel: float):
    """Cap quads where the planes cut the shown parts' solids (see section_caps): lists of (verts, faces, colours,
    normals) arrays, empty if nothing is cut. colour: {part: rgb}."""
    box = np.array([[x, y, w] for x in (fb[0][0], fb[1][0]) for y in (fb[0][1], fb[1][1])
                    for w in (fb[0][2], fb[1][2])])
    V, F, C, N = [], [], [], []
    for k, (p, n) in enumerate(planes):
        u = np.cross(n, np.eye(3)[int(np.argmin(np.abs(n)))])
        u /= np.linalg.norm(u)
        v = np.cross(n, u)  # u x v = n: quads wound counter-clockwise seen from the removed side
        cu, cv = (box - p) @ u, (box - p) @ v
        h = max(voxel / 2, (cu.max() - cu.min()) / 1200, (cv.max() - cv.min()) / 1200)
        iu = np.arange(np.floor(cu.min() / h), np.ceil(cu.max() / h))
        iv = np.arange(np.floor(cv.min() / h), np.ceil(cv.max() / h))
        gu, gv = np.meshgrid(iu, iv, indexing="ij")
        ctr = p + ((gu + 0.5) * h)[..., None] * u + ((gv + 0.5) * h)[..., None] * v
        ok = np.all((ctr >= fb[0] - voxel) & (ctr <= fb[1] + voxel), axis=-1)
        for j, (q, m) in enumerate(planes):
            if j != k:
                ok &= (ctr - q) @ m <= 0
        idx = np.flatnonzero(ok.ravel())
        pts = ctr.reshape(-1, 3)[idx]
        best, who = np.zeros(len(pts)), np.full(len(pts), -1)
        shells = {p for p in shown if (defs.get(p) or {}).get("shell")}
        for i, pn in sorted(enumerate(shown), key=lambda t: t[1] in shells):  # solid parts first
            f = sdf.field_at(streams[pn], pts)
            hit = (f < best) if pn not in shells else ((f < 0) & (who < 0))  # a shell is solid: only its rim
            best[hit], who[hit] = f[hit], i
        for i, pn in enumerate(shown):
            cell = idx[who == i]
            if not len(cell):
                continue
            ci, cj = np.unravel_index(cell, gu.shape)
            q0 = sum(len(x) for x in V) + 4 * np.arange(len(cell))
            V.append(np.stack([p + ((iu[ci] + du) * h)[:, None] * u + ((iv[cj] + dv) * h)[:, None] * v
                               for du, dv in ((0, 0), (1, 0), (1, 1), (0, 1))], 1).reshape(-1, 3))
            F.append(np.concatenate([np.stack([q0, q0 + 1, q0 + 2], 1), np.stack([q0, q0 + 2, q0 + 3], 1)]))
            C.append(np.tile([*colour[pn], 1.0], (4 * len(cell), 1)))
            N.append(np.tile(n, (4 * len(cell), 1)))
    return V, F, C, N


def extent(name: str) -> np.ndarray:
    """The model's bounding box from its primitives, without building: [lo, hi]."""
    adds = [p for p in specmod.compile_prims(load(name)) if p.op == "add"]
    return np.array([np.min([p.lo for p in adds], axis=0), np.max([p.hi for p in adds], axis=0)])


def silhouette(name: str, view: str) -> dict:
    z = np.load(_dir(name) / "build" / "sil.npz")
    uv = z[f"{view}_uv"]
    return {"mask": z[f"{view}_mask"], "u": (uv[0], uv[1]), "v": (uv[2], uv[3])}


def export_obj(name: str, path: Path) -> Path:
    """OBJ with one object per part and each part's clay colour per vertex as "v x y z r g b", which Blender's
    importer reads into a colour attribute. Paint lives in the Blender scene (sync) and the GLB (export_asset)."""
    z = np.load(_dir(name) / "build" / "mesh.npz")
    faces = z["faces"]
    vpart = z["part"] if "part" in z else np.zeros(len(z["verts"]), int)
    part = vpart[faces[:, 0]]
    names = [str(n) for n in z["part_names"]] if "part_names" in z else [name]
    cols = z["part_colors"][vpart, :3] if "part_colors" in z else np.full((len(z["verts"]), 3), 0.7)
    with open(path, "w") as f:
        f.write(f"# hifipushie {name}: one object per part ({', '.join(names)})\n")
        np.savetxt(f, np.concatenate([z["verts"], cols], 1), fmt="v %.5f %.5f %.5f %.4f %.4f %.4f")
        np.savetxt(f, z["normals"], fmt="vn %.4f %.4f %.4f")
        for i, pn in enumerate(names):
            f.write(f"o {name}_{pn}\n")
            np.savetxt(f, np.repeat(faces[part == i] + 1, 2, axis=1), fmt="f %d//%d %d//%d %d//%d")
    return path


def refs_dir(name: str) -> Path:
    p = _dir(name) / "refs"
    p.mkdir(parents=True, exist_ok=True)
    return p
