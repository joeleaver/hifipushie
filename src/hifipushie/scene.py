"""A model's live Blender scene (workspace/<model>/scene.blend): the spec stays the source of truth, the scene is
derived from it, and what a person changes in it comes back as spec edits.

Objects: every part (minus the instances of shared prefabs) and every shared prefab's parts are meshed on their
own and cached by content (a hash of their primitives and voxel), so an edit re-meshes only what it touched.
Scene parts are meshed at the scene voxel on a lattice fixed in space (unrelated edits don't move it); a prefab's
parts in its own frame, at up to `resolution` voxels across the prefab. Instances are collection instances.

Round trip: `pull` reads the saved .blend and turns moved, turned or scaled instances into instance edits (the
weather's offsets taken back out, so the spec + weather lands where the person put it). `sync` pulls first, so
nothing a person did is overwritten, then writes the spec's state.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import tempfile
import time
from pathlib import Path

import numpy as np

from . import asset, assemble, render, sdf, store
from .spec import euler_matrix

SCRIPT = Path(__file__).with_name("blender_scene.py")


def blend_path(name: str) -> Path:
    return store._dir(name) / "scene.blend"


def _blender(job: dict, timeout: float = 900) -> str:
    with tempfile.TemporaryDirectory(prefix="hifipushie-scene-") as tmp:
        p = Path(tmp) / "job.json"
        p.write_text(json.dumps(job))
        r = subprocess.run([render.BLENDER, "-b", "--factory-startup", "--python-exit-code", "1",
                            "--python", str(SCRIPT), "--", str(p)], capture_output=True, text=True, timeout=timeout)
        if r.returncode:
            raise RuntimeError(f"blender failed:\n{r.stdout[-3000:]}\n{r.stderr[-3000:]}")
        return r.stdout


def _hash(ps: list, frame, extra: str = "") -> str:
    h = hashlib.sha1(extra.encode())
    for p in ps:
        h.update(sdf.fingerprint(p).encode())
        if p.kind == "shell":  # a shell follows its base part
            for q in p.params["prims"]:
                h.update(sdf.fingerprint(q).encode())
    lo, vx, shape = frame
    h.update(np.round(np.asarray(lo), 6).tobytes() + np.float64(vx).tobytes() + np.asarray(shape, np.int64).tobytes())
    return h.hexdigest()[:16]


def thinnest(ps: list) -> float:
    """The thinnest feature among additive primitives (m): a box's or cylinder's least extent, a bone's
    diameter, an ellipsoid's least axis, a hollow wall. About 2.5 voxels across it meshes cleanly."""
    t = np.inf
    for p in ps:
        if p.op != "add":
            continue
        pr = p.params["p"] if p.kind == "csg" else p.params
        kind = p.params["kind"] if p.kind == "csg" else p.kind
        if kind in ("box", "cylinder", "ellipsoid"):
            t = min(t, 2 * float(np.min(pr["size"])))
        elif kind == "cone":
            t = min(t, 2 * min(pr["ra"], pr["rb"]) * min(1.0, *pr["flat"]))
        if p.kind == "csg" and p.params.get("hollow"):
            t = min(t, float(p.params["hollow"]))
    return float(t) if np.isfinite(t) else 0.05


def part_voxel(ps: list, voxel: float) -> tuple[float, str]:
    """A scene part's voxel: fine enough for its thinnest element (2.5 voxels across its thinnest feature, 8
    along its whole length: a lantern's glass, a basin's wall), never coarser than the scene voxel nor finer than
    a quarter of it (one thin element makes the whole part fine). Returns (voxel, why)."""
    need, why = voxel, ""
    for p in ps:
        if p.op != "add" or p.kind in ("shell", "displace", "flatten"):
            continue
        t, ext = thinnest([p]), float(np.max(p.hi - p.lo))
        v = min(t / 2.5, ext / 8)
        if v < need:
            need, why = v, f"{p.name}: {t * 1000:.0f} mm thin, {ext * 1000:.0f} mm long"
    floor = voxel / 4
    if need < floor:
        why += f"; capped at {floor * 1000:.1f} mm"
    return float(np.round(max(need, floor), 4)), why


def _frame(ps: list, voxel: float, pad: float = 0.03):
    """A grid around a stream's primitives, snapped to a lattice of `voxel` fixed in space."""
    own = [q for q in ps if q.kind != "shell" and q.op in ("add", "intersect")]
    a = np.min([q.lo for q in own], 0) - pad
    b = np.max([q.hi for q in own], 0) + pad
    a = np.floor(a / voxel) * voxel
    return a, voxel, np.ceil((b - a) / voxel).astype(int) + 1


def objects(name: str, resolution: int = 256, log: list | None = None) -> tuple[list, list]:
    """The scene's objects (meshed or from the cache) and instances, from the current spec."""
    log = [] if log is None else log
    spec = store.load(name)
    ctx = asset.split(spec, resolution, True, log)
    vx = float(np.round(ctx["voxel"], 3))  # a round voxel: resolution edits that don't change it keep the cache
    cache = store._dir(name) / "scene_cache"
    cache.mkdir(exist_ok=True)
    defs = spec.get("parts") or {}
    pf_of = {pn: pf for pf, d in ctx["prefabs"].items() for pn in d["parts"]}
    objs, meshed = [], 0
    for key, ps in ctx["streams"].items():
        pf = pf_of.get(key)
        if pf is None:  # a scene part: its own voxel, from its thinnest element
            pv, why = part_voxel(ps, vx)
            if why:
                log.append(f"{key}: {pv * 1000:.1f} mm voxel ({why})")
            fr = _frame(ps, pv)
        else:  # a prefab: one voxel for all its parts, from its thinnest feature (a cup's wall, a chair's slat)
            own = [q for k in ctx["prefabs"][pf]["parts"] for q in ctx["streams"][k]]
            ext = float((np.max([q.hi for q in own if q.op == "add"], 0) -
                         np.min([q.lo for q in own if q.op == "add"], 0)).max())
            fr = _frame(ps, min(vx, float(np.round(max(thinnest(own) / 2.5, ext / 400), 4))))
        M0 = ctx["prefabs"][pf]["instances"][ctx["prefabs"][pf]["bake"]] if pf else None
        if pf is None:
            h = _hash(ps, fr)
        else:  # the same shape in its own frame wherever its first instance stands: keyed on the definition
            h = hashlib.sha1(json.dumps([spec["prefabs"][pf], key, fr[1], round(float(np.cbrt(np.linalg.det(M0[:3, :3]))), 6)],
                                        sort_keys=True).encode()).hexdigest()[:16]
        f = cache / f"{h}.npz"
        if not f.exists():
            lo, v, shape = fr
            field, _ = sdf.PartGrid().update(ps, fr)
            m = store._mesh_part(ps, field, lo, v, [], {})
            if m is False:
                continue
            verts, faces, normals, _ = m
            if M0 is not None:  # into the prefab's own frame
                A = np.linalg.inv(M0[:3, :3])
                verts = (verts.astype(np.float64) - M0[:3, 3]) @ A.T
                normals = normals @ A.T
                normals /= np.maximum(np.linalg.norm(normals, axis=1, keepdims=True), 1e-12)
            np.savez(f, verts=verts.astype(np.float32), faces=faces, normals=normals.astype(np.float32))
            meshed += 1
        objs.append({"key": key, "mesh": str(f), "hash": h, "part": ctx["origin"][key], "prefab": pf, "voxel": fr[1],
                     "color": store.part_colour(ctx["origin"][key], defs, len(objs)).tolist()})
    insts = [{"name": inst, "prefab": pf, "matrix": M.tolist()}
             for pf, d in ctx["prefabs"].items() for inst, M in d["instances"].items()]
    log.append(f"{len(objs)} objects ({meshed} meshed, {len(objs) - meshed} from the cache), {len(insts)} instances")
    prog = _paint_inputs(spec, ctx, objs, insts, cache, log)
    return objs, insts, prog


VECTOR_INPUTS = ("grain",)  # per-vertex vectors: an attribute each, not packed
RAYTRACED = ("ao", "sky")  # inputs Cycles measures (the rest are ours: curvature is exact from the field)
# AO as ours (cones out to 3 steps of 0.008 x the model size). Sky reaches past the whole model: a roof shelters
# however high it is (ours stopped at 0.3 x, so interior walls read as open to the sky). x model size.
RT = {"ao_distance": 0.024, "sky_distance": 2.0, "samples": 32, "smooth": 2}
CALIBRATION = json.loads(Path(__file__).with_name("input_quantiles.json").read_text()) \
    if Path(__file__).with_name("input_quantiles.json").exists() else {}


def _smooth(v: np.ndarray, faces: np.ndarray, rounds: int = 2) -> np.ndarray:
    """Each vertex halfway to its neighbours' mean, a few rounds: Cycles' per-vertex estimate (32 rays) is
    noisier than neighbouring vertices differ, and paint ramps turn that into speckle."""
    import scipy.sparse as sp
    i = np.concatenate([faces[:, 0], faces[:, 1], faces[:, 2]])
    j = np.concatenate([faces[:, 1], faces[:, 2], faces[:, 0]])
    A = sp.coo_matrix((np.ones(2 * len(i)), (np.r_[i, j], np.r_[j, i])), (len(v), len(v))).tocsr()
    A.data[:] = 1.0
    deg = np.maximum(np.asarray(A.sum(1)).ravel(), 1)
    for _ in range(rounds):
        v = 0.5 * v + 0.5 * (A @ v) / deg
    return v


def calibrate(key: str, v: np.ndarray) -> np.ndarray:
    """Cycles' openness mapped onto the distribution of ours (a quantile curve, like noise), so the ranges in
    specs keep their meaning."""
    c = CALIBRATION.get(key)
    return v if c is None else np.interp(v, c[0], c[1])


def raytraced(objs: list, insts: list, ctx: dict, cache: Path, geo: str, log: list, device: str = "CPU") -> dict:
    """AO and sky openness per vertex of every object by Cycles (`blender_scene.bake_inputs`), smoothed and
    calibrated: {key: {"ao", "sky"}}. Cached per object on the whole geometry (every object occludes)."""
    from .surface import model_size
    size = model_size(list(ctx["full"].values()))
    job = {"mode": "bake_inputs", "ao_distance": RT["ao_distance"] * size, "sky_distance": RT["sky_distance"] * size,
           "samples": RT["samples"], "device": device}
    k = hashlib.sha1((geo + json.dumps([job, CALIBRATION, 1], sort_keys=True)).encode()).hexdigest()[:12]
    files = {o["key"]: cache / f"{o['hash']}_rt_{k}.npz" for o in objs}
    if not all(f.exists() for f in files.values()):
        t = time.time()
        with tempfile.TemporaryDirectory() as tmp:
            job.update(out=tmp, instances=insts, objects=[
                {"key": o["key"], "mesh": o["mesh"], "prefab": o["prefab"],
                 "bake": ctx["prefabs"][o["prefab"]]["bake"] if o["prefab"] else None} for o in objs])
            _blender(job, 3600)
            for o in objs:
                with np.load(Path(tmp) / (o["key"].replace("/", "__") + ".npz")) as z, np.load(o["mesh"]) as m:
                    np.savez(files[o["key"]], **{n: calibrate(n, _smooth(z[n].astype(np.float64), m["faces"], RT["smooth"]))
                                                .astype(np.float32) for n in RAYTRACED})
        log.append(f"Cycles AO and sky for {len(objs)} objects: {time.time() - t:.1f}s")
    out = {}
    for key, f in files.items():
        with np.load(f) as z:
            out[key] = {n: z[n] for n in z.files}
    return out


def _paint_inputs(spec: dict, ctx: dict, objs: list, insts: list, cache: Path, log: list) -> dict | None:
    """The paint program, and each object's per-vertex inputs (cached: AO and sky depend on every object, so
    the key is the whole geometry plus what the program measures)."""
    from . import paintnodes
    if not spec.get("paint"):
        return None
    t = time.time()
    prog = paintnodes.compile(spec)
    geo = hashlib.sha1(json.dumps(sorted(o["hash"] for o in objs)).encode())
    for pf, d in ctx["prefabs"].items():  # where a prefab is baked matters for its AO and sky
        geo.update(np.round(d["instances"][d["bake"]], 6).tobytes())
    from .surface import INPUTS_VERSION
    # two caches: the field inputs (AO, sky: slow) change only with the geometry; the measured masks with it and
    # their own definitions. The packed attribute file per object is assembled from both (cheap).
    ours = [k for k in prog["inputs"] if k not in RAYTRACED]
    fkey = hashlib.sha1((geo.hexdigest() + json.dumps([ours, INPUTS_VERSION])).encode()).hexdigest()[:12]
    # the ray traced inputs join in the masks key (masks can read them), so the packed file follows them too
    mkey = hashlib.sha1((geo.hexdigest() + json.dumps(prog["fallbacks"], sort_keys=True, default=str)
                         + str(INPUTS_VERSION) + json.dumps([RT, CALIBRATION])).encode()).hexdigest()[:12]
    key = hashlib.sha1((fkey + mkey + json.dumps(prog["packing"], sort_keys=True)).encode()).hexdigest()[:12]
    todo = [o for o in objs if not (cache / f"{o['hash']}_in_{key}.npz").exists()]
    # ray traced inputs: needed by the program itself, or by a mask we measure (a blurred or mirrored entry)
    rt = raytraced(objs, insts, ctx, cache, geo.hexdigest(), log) if todo and (
        set(prog["inputs"]) & set(RAYTRACED) or any(k in json.dumps(prog["fallbacks"], default=str)
                                                    for k in RAYTRACED)) else {}
    names = list(ctx["full"])
    groups: dict = {}  # measured at each object's own voxel: curvature and AO steps scale with it
    for o in todo:
        groups.setdefault(o["voxel"], []).append(o)
    for voxel, todo in groups.items():
        P, N, part, sl, given = [], [], [], [], {}
        for o in todo:
            z = np.load(o["mesh"])
            v, n = z["verts"].astype(np.float64), z["normals"].astype(np.float64)
            if o["prefab"]:  # measured where the bake instance stands, as the export bakes it
                d = ctx["prefabs"][o["prefab"]]
                M0 = d["instances"][d["bake"]]
                v = v @ M0[:3, :3].T + M0[:3, 3]
                n = n @ M0[:3, :3].T
                n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-12)
            sl.append((sum(len(x) for x in P), len(v)))
            for k in rt.get(o["key"], {}):
                given.setdefault(k, []).append(rt[o["key"]][k])
            P.append(v)
            N.append(n)
            part.append(np.full(len(v), names.index(o["part"])))
        P, N, part = np.concatenate(P), np.concatenate(N), np.concatenate(part)
        given = {k: np.concatenate(v).astype(np.float64) for k, v in given.items()}
        vals = {k: v.astype(np.float32) for k, v in given.items()}
        for what, k in (("field", fkey), ("masks", mkey)):
            files = [cache / f"{o['hash']}_{what}_{k}.npz" for o in todo]
            if all(f.exists() for f in files):
                for f, (a, n) in zip(files, sl):
                    with np.load(f) as zz:
                        for name in zz.files:
                            vals.setdefault(name, np.zeros((len(P),) + zz[name].shape[1:], np.float32))[a:a + n] = zz[name]
                continue
            got = paintnodes.measure(spec, prog, P, N, part, names, voxel, ctx["full"], what, given)
            for f, (a, n) in zip(files, sl):
                np.savez(f, **{name: v[a:a + n] for name, v in got.items()})
            vals.update(got)
            log.append(f"measured {what} for {len(todo)} objects at {voxel * 1000:.1f} mm ({len(P)} vertices), "
                       f"{time.time() - t:.1f}s so far")
        for o, (a, n) in zip(todo, sl):
            packs = {}  # a GPU shader reads ~16 vertex attributes: scalars go three to a vector
            for attr, (pk, ch) in prog["packing"].get(o["part"], {}).items():
                packs.setdefault(pk, np.zeros((n, 3), np.float32))[:, ch] = vals[attr][a:a + n]
            vec = {k: vals[k][a:a + n] for k in VECTOR_INPUTS if k in vals}  # their own vector attributes
            np.savez(cache / f"{o['hash']}_in_{key}.npz", wpos=P[a:a + n].astype(np.float32),
                     wnrm=N[a:a + n].astype(np.float32), **packs, **vec)
    for o in objs:
        o["inputs"] = str(cache / f"{o['hash']}_in_{key}.npz")
        o["hash"] = f"{o['hash']}:{key}"
    return prog


def pull(name: str, log: list | None = None) -> dict:
    """Instance edits a person made in the saved scene, applied to the spec. Returns {instance: new placement}."""
    log = [] if log is None else log
    bp = blend_path(name)
    if not bp.exists():
        return {}
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "pull.json"
        _blender({"mode": "pull", "blend": str(bp), "out": str(out)})
        got = json.loads(out.read_text())
    moved = got["moved"]
    spec = store.load(name)
    changes = _pull_params(spec, got["params"], log)
    if not moved:
        if changes:
            store.save(name, spec, "paint from the Blender scene: " + ", ".join(changes))
        return changes
    pls = assemble.placements(spec)
    for inst, m in moved.items():
        d = (spec.get("instances") or {}).get(inst)
        if d is None:
            log.append(f"{inst}: moved in the scene, but it's the mirror of a '.L' instance: move that one")
            continue
        M = np.asarray(m)
        L = M[:3, :3]
        sc = float(np.cbrt(np.linalg.det(L)))
        rot_user = np.asarray(assemble._euler_of(L / sc))
        # the weather moved it from the spec's placement by these offsets; take them back out
        d_at = np.asarray(pls[inst]["at"], float) - np.asarray(d.get("at", [0, 0, 0]), float)
        d_rot = np.asarray(pls[inst]["rot"], float) - np.asarray(d.get("rot", [0, 0, 0]), float)
        new = {"at": assemble._r(M[:3, 3] - d_at), "rot": [round(float(v), 3) for v in rot_user - d_rot]}
        if abs(sc - float(d.get("scale", 1.0))) > 1e-4:
            new["scale"] = round(sc, 4)
        spec["instances"][inst] = {**d, **new}
        changes[inst] = new
        log.append(f"{inst}: {json.dumps(new)} (from the scene)")
    store.save(name, spec, "from the Blender scene: " + ", ".join(changes))
    return changes


def _at(spec, path):
    x = spec
    for k in path:
        x = x[k]
    return x


def _pull_params(spec: dict, params: dict, log: list) -> dict:
    """Paint numbers changed in the scene's materials, written into the spec (by their json path)."""
    from . import paint
    changes = {}
    for key, vals in params.items():
        path = json.loads(key)
        try:
            cur = _at(spec, path)
        except (KeyError, IndexError, TypeError):
            if path[-1] == "opacity":
                cur = 1.0
            else:
                continue
        if isinstance(cur, (str, list)) and path[-1] == "color":
            cur_rgb = paint.colour(cur)
            new = next((v for v in vals if np.abs(np.asarray(v) - cur_rgb).max() > 2e-3), None)
            if new is None:
                continue
            val = "#" + "".join(f"{int(round(min(max(c, 0), 1) * 255)):02x}" for c in new)
        else:
            new = next((v for v in vals if abs(float(v) - float(cur)) > 1e-4), None)
            if new is None:
                continue
            val = round(float(new), 4)
        x = spec
        for k in path[:-1]:
            x = x[k]
        x[path[-1]] = val
        changes[".".join(str(k) for k in path[1:])] = val
        log.append(f"paint {'.'.join(str(k) for k in path[1:])}: {cur} -> {val} (from the scene)")
    return changes


def sync(name: str, resolution: int = 256) -> dict:
    """Pull a person's edits, then bring scene.blend in line with the spec. Returns timings and the log."""
    t = time.time()
    log: list = []
    pulled = pull(name, log)
    t1 = time.time()
    objs, insts, prog = objects(name, resolution, log)
    t2 = time.time()
    spec = store.load(name)
    defs = spec.get("parts") or {}
    bases = {}
    for o in objs:
        d = defs.get(o["part"]) or {}
        bases[o["part"]] = {"color": list(o["color"][:3]), "roughness": float(d.get("roughness", 0.6)),
                            "metallic": float(d.get("metallic", 0.0)), "specular": float(d.get("specular", 0.5))}
    # materials are rebuilt when the program, the bases or the code that builds their nodes change
    ph = hashlib.sha1(json.dumps([prog, bases, hashlib.sha1(SCRIPT.read_bytes()).hexdigest()], sort_keys=True,
                                 default=str).encode()).hexdigest()[:12]
    out = _blender({"mode": "sync", "blend": str(blend_path(name)), "objects": objs, "instances": insts,
                    "program": prog, "bases": bases, "prog_hash": ph})
    made = next((json.loads(line[7:]) for line in out.splitlines() if line.startswith("@@made")), [])
    log.append(f"scene: {len(made)} objects replaced ({', '.join(made[:8])}{'...' if len(made) > 8 else ''})")
    return {"blend": str(blend_path(name)), "pulled": pulled, "log": log,
            "seconds": {"pull": round(t1 - t, 1), "mesh": round(t2 - t1, 1), "blender": round(time.time() - t2, 1)}}


def look(name: str, views: list[str] | None = None, cameras: list[dict] | None = None, size: int = 640,
         save: str | None = None, show_layer: str | None = None):
    """Render the saved scene with EEVEE: named views (as look) and/or perspective cameras {"eye": [x,y,z],
    "target", "fov"}."""
    from PIL import Image
    bp = blend_path(name)
    frames = []
    if views:
        from .spec import compile_prims, geometry
        adds = [p for p in compile_prims(geometry(store.load(name))) if p.op == "add"]  # bounds for the ortho views
        lo, hi = np.min([p.lo for p in adds], 0), np.max([p.hi for p in adds], 0)
        lo, hi = lo - 0.06 * (hi - lo), hi + 0.06 * (hi - lo)
        frames += render.view_frames(np.array([[(lo, hi)[(i >> k) & 1][k] for k in range(3)] for i in range(8)]), views)
    for i, c in enumerate(cameras or []):
        frames.append(render.camera_frame(c, i))
    with tempfile.TemporaryDirectory() as tmp:
        for f in frames:
            f["out"] = str(Path(tmp) / f"{f['name']}.png")
        t = time.time()
        job = {"mode": "render", "blend": str(bp), "views": frames, "size": size}
        if show_layer:  # that layer's mask alone, grey (needs the program: compile it again)
            from . import paintnodes
            spec = store.load(name)
            defs = spec.get("parts") or {}
            job.update(show_layer=show_layer, program=paintnodes.compile(spec),
                       bases={p: {"color": [0.5] * 3, "roughness": 0.6, "metallic": 0.0, "specular": 0.5}
                              for p in list(defs) + ["body"]})
        _blender(job)
        imgs = [Image.open(f["out"]).convert("RGB") for f in frames]
    sheet = render.contact_sheet(imgs, frames)
    if save:
        sheet.save(save)
    return sheet, round(time.time() - t, 1)
