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
from .spec import SpecError, euler_matrix

SCRIPT = Path(__file__).with_name("blender_scene.py")


def blend_path(name: str) -> Path:
    return store._dir(name) / "scene.blend"


LIVE_PORT = int(__import__("os").environ.get("BLENDER_MCP_PORT", "9876"))


def _live_call(code: str, timeout: float = 600.0, port: int | None = None) -> dict | None:
    """Run Python in a person's running Blender over the Blender MCP add-on's socket (JSON + NUL). None when
    no Blender is listening."""
    import socket
    try:
        with socket.create_connection(("localhost", port or LIVE_PORT), timeout=1.0) as sock:
            sock.settimeout(timeout)
            sock.sendall(json.dumps({"type": "execute", "code": code, "strict_json": False}).encode() + b"\0")
            buf = bytearray()
            while b"\0" not in buf:
                chunk = sock.recv(65536)
                if not chunk:
                    break
                buf.extend(chunk)
    except OSError:
        return None
    if not buf:
        return None
    return json.loads(bytes(buf).partition(b"\0")[0].decode())


def live_session(name: str) -> bool:
    """Is the model's scene.blend open in a person's running Blender (the Blender MCP add-on listening)? Then
    syncs and pulls happen in that session, so edits show as they're made and theirs come back unsaved."""
    r = _live_call("import bpy\nresult = {'file': bpy.data.filepath}", timeout=5.0)
    if not r or r.get("status") != "ok":
        return False
    f = (r.get("result") or {}).get("file") or ""
    return bool(f) and Path(f).resolve() == blend_path(name).resolve()


def _blender_live(job: dict) -> str:
    """blender_scene's job, run inside the live session (it imports the module; nothing is opened or reloaded
    from disk, and a sync saves the session to scene.blend so headless renders see it)."""
    code = ("import sys, importlib, json\n"
            f"sys.path.insert(0, {str(SCRIPT.parent)!r})\n"
            "import blender_scene as B\n"
            "importlib.reload(B)\n"
            f"B.MODES[{job['mode']!r}](json.loads({json.dumps({**job, 'live': True})!r}))\n"
            "result = {}")
    r = _live_call(code, timeout=3600.0)
    if r is None:
        raise RuntimeError("the live Blender session went away")
    if r.get("status") != "ok":
        raise RuntimeError(f"live Blender failed: {r.get('message')}\n{r.get('stderr', '')[-2000:]}")
    return str(r.get("stdout") or "")


def _blender(job: dict, timeout: float = 900, progress=None) -> str:
    """Run blender_scene.py on a job. progress(line) gets each "@@progress" line as Blender prints it."""
    with tempfile.TemporaryDirectory(prefix="hifipushie-scene-") as tmp:
        p = Path(tmp) / "job.json"
        p.write_text(json.dumps(job))
        cmd = [render.BLENDER, "-b", "--factory-startup", "--python-exit-code", "1", "--python", str(SCRIPT), "--", str(p)]
        if progress is None:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
            out, err, code = r.stdout, r.stderr, r.returncode
        else:
            import threading
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            errs = []
            t = threading.Thread(target=lambda: errs.append(proc.stderr.read()), daemon=True)
            t.start()
            lines = []
            timer = threading.Timer(timeout, proc.kill)
            timer.start()
            try:
                for line in proc.stdout:
                    lines.append(line)
                    if line.startswith("@@progress"):
                        progress(line[11:].rstrip())
                code = proc.wait()
            finally:
                timer.cancel()
            t.join(5)
            out, err = "".join(lines), "".join(errs)
        if code:
            raise RuntimeError(f"blender failed:\n{out[-3000:]}\n{err[-3000:]}")
        return out


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


# Per model, per scene part: its block grid and projected mesh from the last sync (like store._LIVE), so an edit
# to a big part (a window cut into the logs) re-meshes only the blocks the change can reach. Grids of fine-voxel
# parts are big: a model keeps at most LIVE_CELLS of them (the most recently used), the rest mesh cold.
_LIVE: dict[str, dict] = {}
LIVE_CELLS = 750_000_000  # ~3 GB of float32 per model


def _live_grid(name: str, key: str, fr) -> dict:
    parts = _LIVE.setdefault(name, {})
    st = parts.pop(key, None) or {"grid": sdf.PartGrid()}
    parts[key] = st  # most recently used last
    st["cells"] = int(np.prod(np.asarray(fr[2], np.int64) + sdf.BLOCK))
    while sum(p.get("cells", 0) for p in parts.values()) > LIVE_CELLS and len(parts) > 1:
        parts.pop(next(iter(parts)))
    return st


def objects(name: str, resolution: int = 256, log: list | None = None) -> tuple[list, list]:
    """The scene's objects (meshed or from the cache) and instances, from the current spec."""
    log = [] if log is None else log
    spec = store.load(name)
    ctx = asset.split(spec, resolution, True, log, min_share=1)  # every instance its own movable object
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
            if pf is None:  # a scene part: keep its grid, so an edit re-meshes only the blocks it can reach
                st = _live_grid(name, key, fr)
                try:
                    field, boxes = st["grid"].update(ps, fr)
                    m = store._mesh_part(ps, field, lo, v, boxes, st)
                except BaseException:
                    _LIVE.get(name, {}).pop(key, None)  # possibly half updated: start that part cold next time
                    raise
            else:
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


LAYOUT = 2  # what an object's packed inputs file holds (2: ao_raw for the export's AO map): bump on change
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


def _world(o: dict, ctx: dict):
    """An object's vertices and normals in the world, where it stands (a prefab: at its bake instance)."""
    z = np.load(o["mesh"])
    v, n = z["verts"].astype(np.float64), z["normals"].astype(np.float64)
    if o["prefab"]:
        d = ctx["prefabs"][o["prefab"]]
        M0 = d["instances"][d["bake"]]
        v = v @ M0[:3, :3].T + M0[:3, 3]
        n = n @ M0[:3, :3].T
        n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-12)
    return v, n


def _placed(o: dict, ctx: dict) -> str:
    """An object's identity including where it stands (a prefab's mesh key is its definition alone)."""
    if not o["prefab"]:
        return o["hash"]
    d = ctx["prefabs"][o["prefab"]]
    return o["hash"] + hashlib.sha1(np.round(d["instances"][d["bake"]], 6).tobytes()).hexdigest()[:8]


def _near_change(v: np.ndarray, boxes: list, reach: float) -> np.ndarray:
    """Vertices whose AO or sky a change in these boxes can reach: within `reach` of a box (AO), or under it
    within a 45 degree cone plus `reach` (what's overhead shades the sky). The cone starts at the box's bottom:
    sky openness is weighted around straight up, so a change beside a point, at its own height (a door moved
    along a wall), barely moves it; what's above it does (a roof, a beam). Measured from the top, a door cut's
    2 m of height re-baked everything within 2 m of it: 1.9M vertices for a 15 cm move."""
    hit = np.zeros(len(v), bool)
    for lo, hi in boxes:
        hit |= np.all((v >= lo - reach) & (v <= hi + reach), 1)
        m = reach + np.clip(lo[2] - v[:, 2], 0, 2.0)
        hit |= (v[:, 2] <= hi[2] + reach) & np.all((v[:, :2] >= lo[:2] - m[:, None]) & (v[:, :2] <= hi[:2] + m[:, None]), 1)
    return hit


def raytraced(objs: list, insts: list, ctx: dict, cache: Path, log: list, device: str = "CPU") -> dict:
    """AO and sky openness per vertex of every object by Cycles (`blender_scene.bake_inputs`), smoothed and
    calibrated: {key: {"ao", "sky"}}. Only the building (primitives that aren't prefab instances) occludes other
    things; a prop shades only itself, so moving one changes nothing else. Incremental: the building's
    primitives are diffed against the last bake (rt_state.json) and only its vertices a change can reach are
    baked again (`_near_change`); a prop bakes again when its bake instance moves or the building changes over it.
    Each object's values carry a stamp (its entry in the state) that changes whenever they do."""
    from .surface import model_size
    size = model_size(list(ctx["full"].values()))
    job = {"mode": "bake_inputs", "ao_distance": RT["ao_distance"] * size, "sky_distance": RT["sky_distance"] * size,
           "samples": RT["samples"], "device": device}
    pkey = hashlib.sha1(json.dumps([job, 6], sort_keys=True).encode()).hexdigest()[:12]
    raw_dir = cache / "rt"
    raw_dir.mkdir(exist_ok=True)
    sf = cache / "rt_state.json"
    state = json.loads(sf.read_text()) if sf.exists() else {}
    # the building: per primitive its box, name, its fingerprint without cuts and its cuts' boxes, so a board
    # whose only change is a door cut moving along it counts as changed where the cut was and is, not all over
    fps = {sdf.fingerprint(p): [p.lo.tolist(), p.hi.tolist(), p.name, sdf.fingerprint(p, cuts=False),
                                {c[0]: [c[1].tolist(), c[2].tolist()] for c in p.cut_boxes}]
           for ps in ctx["full"].values() for p in ps if p.instance is None}
    same = state.get("params") == pkey
    old = state.get("prims", {}) if same else {}
    gone, new_ = set(old) - set(fps), set(fps) - set(old)
    by_name = {old[f][2]: f for f in gone if len(old[f]) == 5}
    boxes = []
    for f in new_:
        e = fps[f]
        g = by_name.pop(e[2], None)
        if g is not None and old[g][3] == e[3]:  # the same shape, cut differently: where the cuts differ
            oc, nc = old[g][4], e[4]
            boxes += [np.asarray(oc[c], float) for c in set(oc) - set(nc)] + \
                     [np.asarray(nc[c], float) for c in set(nc) - set(oc)]
            gone.discard(g)
        else:
            boxes.append(np.asarray(e[:2], float))
    boxes += [np.asarray(old[f][:2], float) for f in gone]
    raw_of = {o["key"]: raw_dir / (o["key"].replace("/", "__") + ".npz") for o in objs}
    stamps = dict(state.get("stamps", {})) if same else {}
    reach = 1.5 * job["ao_distance"]
    todo, n_bake = [], 0
    for o in objs:
        whole = not same or state.get("objects", {}).get(o["key"]) != _placed(o, ctx) or not raw_of[o["key"]].exists()
        if not whole and boxes:
            near = _near_change(_world(o, ctx)[0], boxes, reach)
            whole = bool(o["prefab"]) and near.any()  # a prop is small: again whole
            sub = None if whole else np.flatnonzero(near)
        else:
            sub = None if whole else np.zeros(0, np.int64)
        n_bake += len(np.load(o["mesh"])["verts"]) if sub is None else len(sub)
        todo.append(sub)
    if any(sub is None or len(sub) for sub in todo):
        t = time.time()
        with tempfile.TemporaryDirectory() as tmp:
            jobs = []
            for o, sub in zip(objs, todo):
                j = {"key": o["key"], "mesh": o["mesh"], "prefab": o["prefab"],
                     "bake": ctx["prefabs"][o["prefab"]]["bake"] if o["prefab"] else None}
                if sub is not None:
                    j["subset"] = str(Path(tmp) / (o["key"].replace("/", "__") + "_subset.npy"))
                    np.save(j["subset"], sub)
                jobs.append(j)
            job.update(out=tmp, instances=insts, objects=jobs)
            out = _blender(job, 3600)
            bt = next((line[8:] for line in out.splitlines() if line.startswith("@@times")), "")
            for o, sub in zip(objs, todo):
                f = Path(tmp) / (o["key"].replace("/", "__") + ".npz")
                if not f.exists():
                    continue
                with np.load(f) as z, np.load(o["mesh"]) as m:
                    if sub is None:
                        raw = {n: z[n] for n in RAYTRACED}
                    else:
                        with np.load(raw_of[o["key"]]) as r0:
                            raw = {n: r0[n].copy() for n in RAYTRACED}
                        for n in RAYTRACED:
                            raw[n][z["idx"]] = z[n]
                    sm = {n: _smooth(raw[n].astype(np.float64), m["faces"], RT["smooth"]) for n in RAYTRACED}
                    final = {n: calibrate(n, sm[n]).astype(np.float32) for n in RAYTRACED}
                    final["ao_raw"] = sm["ao"].astype(np.float32)  # the export's AO map: Cycles' own, uncalibrated
                np.savez(raw_of[o["key"]], **raw, **{f"final_{n}": v for n, v in final.items()})
                stamps[o["key"]] = hashlib.sha1(b"".join(np.round(final[n], 4).tobytes() for n in RAYTRACED)).hexdigest()[:10]
        log.append(f"Cycles AO and sky: {n_bake} vertices baked"
                   f"{'' if all(s is None for s in todo) else f' ({len(boxes)} building primitives changed)'}, "
                   f"{time.time() - t:.1f}s (blender {bt})")
    sf.write_text(json.dumps({"params": pkey, "prims": fps, "stamps": stamps,
                              "objects": {o["key"]: _placed(o, ctx) for o in objs}}))
    out = {}
    for o in objs:
        with np.load(raw_of[o["key"]]) as z:
            out[o["key"]] = {n: z[f"final_{n}"] for n in (*RAYTRACED, "ao_raw")}
        out[o["key"]]["stamp"] = stamps.get(o["key"], "")
    return out


def _paint_inputs(spec: dict, ctx: dict, objs: list, insts: list, cache: Path, log: list) -> dict | None:
    """The paint program, and each object's per-vertex inputs, from three caches: our field inputs (curvature,
    thickness, grain: the object's own geometry where it stands), Cycles' AO and sky (`raytraced`: the building
    shades, props only themselves) and the measured masks (the object, the building and their definitions). An
    object's packed file is named by its content, so the scene replaces only objects whose inputs changed, and
    moving a prop re-measures at most that prop."""
    from . import paintnodes
    from .surface import INPUTS_VERSION
    t = time.time()
    prog = paintnodes.compile(spec)
    ours = [k for k in prog["inputs"] if k not in RAYTRACED]
    building = hashlib.sha1(json.dumps(sorted(_placed(o, ctx) for o in objs if not o["prefab"])).encode()).hexdigest()
    prog_id = hashlib.sha1(json.dumps([prog["fallbacks"], prog["packing"], ours, INPUTS_VERSION, RT, CALIBRATION,
                                       LAYOUT],
                                      sort_keys=True, default=str).encode()).hexdigest()[:12]
    last = cache / "inputs_state.json"
    st = json.loads(last.read_text()) if last.exists() else {}
    run = hashlib.sha1(json.dumps([building, prog_id, sorted(_placed(o, ctx) for o in objs)]).encode()).hexdigest()[:12]
    if st.get("run") == run and all(Path((st.get("objects") or {}).get(o["key"], "")).exists() for o in objs):
        for o in objs:  # nothing that inputs depend on changed since the last sync
            o["inputs"] = st["objects"][o["key"]]
            o["hash"] = f"{o['hash']}:{Path(o['inputs']).stem.split('_in_')[-1]}"
        return prog
    rt = raytraced(objs, insts, ctx, cache, log)  # always: the export's AO map comes from it, paint or not
    names = list(ctx["full"])

    def key(*parts):
        return hashlib.sha1(json.dumps(parts, default=str).encode()).hexdigest()[:12]
    ffile = {o["key"]: cache / f"{o['hash']}_field_{key(_placed(o, ctx), ours, INPUTS_VERSION)}.npz" for o in objs}
    # masks (near distances, paths, blurred and mirrored entries) read the building and the object's own inputs
    mfile = {o["key"]: cache / f"{o['hash']}_masks_{key(_placed(o, ctx), building, prog_id, rt.get(o['key'], {}).get('stamp'))}.npz"
             for o in objs}
    for what, files in (("field", ffile), ("masks", mfile)):
        groups: dict = {}  # measured at each object's own voxel: curvature and AO steps scale with it
        for o in objs:
            if not files[o["key"]].exists():
                groups.setdefault(o["voxel"], []).append(o)
        for voxel, group in groups.items():
            P, N, part, sl, given = [], [], [], [], {}
            for o in group:
                v, n = _world(o, ctx)
                sl.append((sum(len(x) for x in P), len(v)))
                for k in RAYTRACED:
                    if k in rt.get(o["key"], {}):
                        given.setdefault(k, []).append(rt[o["key"]][k])
                P.append(v)
                N.append(n)
                part.append(np.full(len(v), names.index(o["part"])))
            P, N, part = np.concatenate(P), np.concatenate(N), np.concatenate(part)
            given = {k: np.concatenate(v).astype(np.float64) for k, v in given.items()}
            got = paintnodes.measure(spec, prog, P, N, part, names, voxel, ctx["full"], what, given)
            for o, (a, n) in zip(group, sl):
                np.savez(files[o["key"]], **{name: v[a:a + n] for name, v in got.items()})
            log.append(f"measured {what} for {len(group)} objects at {voxel * 1000:.1f} mm ({len(P)} vertices), "
                       f"{time.time() - t:.1f}s so far")
    made = {}
    for o in objs:
        v, n = _world(o, ctx)
        vals = {k: rt[o["key"]][k] for k in RAYTRACED if k in rt.get(o["key"], {})}
        for f in (ffile[o["key"]], mfile[o["key"]]):
            with np.load(f) as z:
                vals.update({k: z[k] for k in z.files})
        packs = {}  # a GPU shader reads ~16 vertex attributes: scalars go three to a vector
        for attr, (pk, ch) in prog["packing"].get(o["part"], {}).items():
            packs.setdefault(pk, np.zeros((len(v), 3), np.float32))[:, ch] = vals[attr]
        vec = {k: vals[k].astype(np.float32) for k in VECTOR_INPUTS if k in vals}  # their own vector attributes
        arrays = {"wpos": v.astype(np.float32), "wnrm": n.astype(np.float32), **packs, **vec}
        if "ao_raw" in rt.get(o["key"], {}):  # a plain attribute: baked into the export's AO map
            arrays["ao_raw"] = rt[o["key"]]["ao_raw"]
        h = hashlib.sha1()
        for k in sorted(arrays):
            h.update(k.encode() + np.round(arrays[k], 4).tobytes())
        f = cache / f"{o['hash']}_in_{h.hexdigest()[:12]}.npz"
        if not f.exists():
            np.savez(f, **arrays)
        o["inputs"] = str(f)
        o["hash"] = f"{o['hash']}:{h.hexdigest()[:12]}"
        made[o["key"]] = str(f)
    last.write_text(json.dumps({"run": run, "objects": made}))
    return prog


def pull(name: str, log: list | None = None) -> dict:
    """Instance edits a person made in the scene, applied to the spec: from their running Blender when it has the
    scene open (`live_session`), else from the saved file. Returns {instance: new placement}."""
    log = [] if log is None else log
    bp = blend_path(name)
    if not bp.exists():
        return {}
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "pull.json"
        job = {"mode": "pull", "blend": str(bp), "out": str(out)}
        if live_session(name):  # the person's running Blender: their unsaved moves and tweaks, as they are
            _blender_live(job)
            log.append("pulled from the live Blender session")
        else:
            _blender(job)
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
        fw = (pls.get(inst) or {}).get("from_wall")
        if d is None and fw:  # a wall's door: its swing goes back into the opening's "open"; the rest is the wall's
            wn, k, kind = fw[:3]
            M = np.asarray(m)
            if kind == "door":
                rz = float(np.degrees(np.arctan2(M[1, 0], M[0, 0])))
                a = ((rz - fw[3]) * fw[4] + 180.0) % 360.0 - 180.0
                spec["walls"][wn]["openings"][k]["open"] = round(max(a, 0.0), 1)
                changes[inst] = {"open": round(max(a, 0.0), 1)}
                log.append(f"{inst}: wall {wn!r} opening {k} now open {max(a, 0.0):.0f} deg (from the scene)")
            else:
                log.append(f"{inst}: moved in the scene, but it's placed by wall {wn!r}: move the opening in the spec")
            continue
        if d is None:
            log.append(f"{inst}: moved in the scene, but it's the mirror of a '.L' instance: move that one")
            continue
        M = np.asarray(m)
        L = M[:3, :3]
        sc = float(np.cbrt(np.linalg.det(L)))
        rot_user = np.asarray(assemble._euler_of(L / sc))
        # the weather moved it from the spec's placement by these offsets; take them back out
        at0 = list(d.get("at", [0, 0, 0]))
        at0 = at0 + [0.0] * (3 - len(at0))  # "on" instances may give [x, y]
        d_at = np.asarray(pls[inst]["at"], float) - np.asarray(at0, float)
        d_rot = np.asarray(pls[inst]["rot"], float) - np.asarray(d.get("rot", [0, 0, 0]), float)
        new = {"at": assemble._r(M[:3, 3] - d_at), "rot": [round(float(v), 3) for v in rot_user - d_rot]}
        if abs(sc - float(d.get("scale", 1.0))) > 1e-4:
            new["scale"] = round(sc, 4)
        spec["instances"][inst] = {**d, **new}
        if "on" in d:  # slid along its support: it stays "on" it; lifted, lowered or moved off it: where it was put
            off = abs(float(M[2, 3]) - float(pls[inst]["at"][2])) > 0.01
            if not off:
                try:
                    assemble.expand(spec)
                except SpecError:
                    off = True
            if off:
                new["at"] = assemble._r(M[:3, 3] - np.append(d_at[:2], 0.0))
                spec["instances"][inst] = {k: v for k, v in {**d, **new}.items() if k not in ("on", "lift")}
                log.append(f"{inst}: no longer set down \"on\" {d['on']} (moved off it in the scene)")
            else:  # still on it: only x, y are the person's; z stays found
                new["at"] = new["at"][:2]
                spec["instances"][inst] = {**d, **new}
        changes[inst] = new
        log.append(f"{inst}: {json.dumps(new)} (from the scene)")
    store.save(name, spec, "from the Blender scene: " + ", ".join(changes))
    for inst in moved:  # a person's move can land an instance inside something: say so
        hit = clashes(spec, inst)
        if hit:
            log.append(f"{inst} now cuts into " + ", ".join(f"{n} ({d * 1000:.0f} mm)" for d, n in hit[:4])
                       + ": move it in the scene, or `scene.clear_of(name, instance)` slides it out")
    return changes


def _clash_setup(spec: dict, inst: str, voxel: float, tol: float):
    """The instance's inside (grid points over its box, and how deep each is) and everything else's prims."""
    from .spec import compile_prims, geometry
    prims = compile_prims(geometry(spec))
    own = [p for p in prims if p.instance == inst]
    if not own:
        return None
    adds = [p for p in own if p.op == "add"]
    lo, hi = np.min([p.lo for p in adds], 0), np.max([p.hi for p in adds], 0)
    ax = [np.arange(a, b + voxel, voxel) for a, b in zip(lo, hi)]
    P = np.stack(np.meshgrid(*ax, indexing="ij"), -1).reshape(-1, 3)
    fo = sdf.field_at(own, P)
    inside = fo < -tol
    return P[inside], -fo[inside], [p for p in prims if p.instance != inst]


def _clash_at(P, depth_own, rest, tol: float, shift=np.zeros(3), names: bool = True) -> list:
    """Clashes of the instance's inside points moved by `shift` with the rest: [(depth, element)], deepest first
    (names=False: just [(depth, None)] if it clashes, for searches)."""
    Q = P + shift
    if not len(Q):
        return []
    near = [p for p in rest if p.op == "add" and np.all(p.hi >= Q.min(0)) and np.all(p.lo <= Q.max(0))]
    if not near:
        return []
    depth = np.minimum(depth_own, -sdf.field_at(near, Q))
    deep = np.flatnonzero(depth > tol)
    if not names:
        return [(float(depth.max()), None)] if len(deep) else []
    out = {}
    for i in deep[np.argsort(depth[deep])[-300:]]:  # name each clash by the other element nearest the point
        el = min(near, key=lambda p: float(sdf.SDF[p.kind](Q[i:i + 1], p.params)[0]))
        out[el.name] = max(out.get(el.name, 0.0), float(depth[i]))
    return sorted(((d, n) for n, d in out.items()), reverse=True)


def clashes(spec: dict, inst: str, voxel: float = 0.005, tol: float = 0.003) -> list:
    """Where an instance cuts into anything else: on a grid over its box, points inside both its own field and
    the rest's; depth = how far inside both. Returns [(depth m, the other element)], deepest first, over tol."""
    st = _clash_setup(spec, inst, voxel, tol)
    return [] if st is None else _clash_at(*st, tol)


def clear_of(name: str, inst: str, step: float = 0.005, reach: float = 0.25, log: list | None = None) -> dict | None:
    """Slide an instance the least distance sideways (8 directions in the ground plane, `step` apart) until it cuts
    into nothing, keeping its rotation. Its inside is sampled once and tested shifted. Saves and returns the new
    instance, or None if it was clear already or nothing within reach works."""
    log = [] if log is None else log
    spec = store.load(name)
    tol = 0.003
    st = _clash_setup(spec, inst, 0.01, tol)  # searched on a 1 cm grid, the answer checked at 5 mm
    fine = _clash_setup(spec, inst, 0.005, tol)
    if st is None or not _clash_at(*fine, tol, names=False):
        return None
    d0 = spec["instances"][inst]
    for r in np.arange(step, reach + 1e-9, step):
        for a in np.radians(np.arange(0, 360, 45)):
            t = r * np.array([np.cos(a), np.sin(a), 0.0])
            if not _clash_at(*st, tol, t, names=False) and not _clash_at(*fine, tol, t, names=False):
                at = np.asarray(d0.get("at", [0, 0, 0]), float) + t
                spec["instances"][inst] = {**d0, "at": [round(float(x), 3) for x in at]}
                store.save(name, spec, f"{inst} slid {r * 1000:.0f} mm clear of what it cut into")
                log.append(f"{inst}: at {spec['instances'][inst]['at']} ({r * 1000:.0f} mm)")
                return spec["instances"][inst]
    return None


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
    """Pull a person's edits, then bring scene.blend in line with the spec. Returns timings and the log.
    Moving a prop re-measures at most that prop (nothing depends on where props stand)."""
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
        from .paint import style_rgb
        rgb = style_rgb(o["color"][:3], (spec.get("style") or {}).get("paint") or {})
        bases[o["part"]] = {"color": [float(x) for x in rgb], "roughness": float(d.get("roughness", 0.6)),
                            "metallic": float(d.get("metallic", 0.0)), "specular": float(d.get("specular", 0.5)),
                            **{k: float(d[k]) for k in ("transmission", "alpha", "ior") if k in d}}
    ph = part_hashes(prog, bases)
    job = {"mode": "sync", "blend": str(blend_path(name)), "objects": objs, "instances": insts,
           "program": prog, "bases": bases, "prog_hash": ph}
    live = live_session(name)
    out = _blender_live(job) if live else _blender(job)
    if live:
        log.append("synced into the live Blender session (and saved it to scene.blend)")
    made = next((json.loads(line[7:]) for line in out.splitlines() if line.startswith("@@made")), [])
    rebuilt = next((json.loads(line[10:]) for line in out.splitlines() if line.startswith("@@rebuilt")), [])
    log.append(f"scene: {len(made)} objects replaced ({', '.join(made[:8])}{'...' if len(made) > 8 else ''})"
               + (f"; materials rebuilt: {', '.join(rebuilt)}" if rebuilt else ""))
    return {"blend": str(blend_path(name)), "pulled": pulled, "log": log,
            "seconds": {"pull": round(t1 - t, 1), "mesh": round(t2 - t1, 1), "blender": round(time.time() - t2, 1)}}


def part_hashes(prog: dict | None, bases: dict) -> dict:
    """Per part, what its material is built from: the layers on it, its packed inputs, its base channels, the
    noise quantiles and the node-building code. A part's material is rebuilt only when its own hash changes (one
    hash for all rebuilt every part on any paint edit: ~30-60 s on the cabin, plus shader compiles)."""
    code = hashlib.sha1(SCRIPT.read_bytes()).hexdigest()
    out = {}
    for part, base in bases.items():
        layers = [ly for ly in (prog or {}).get("layers", []) if part in ly["parts"] or "*" in ly["parts"]]
        out[part] = hashlib.sha1(json.dumps([layers, (prog or {}).get("packing", {}).get(part, {}),
                                             (prog or {}).get("quantiles"), base, code], sort_keys=True,
                                            default=str).encode()).hexdigest()[:12]
    return out


def look(name: str, views: list[str] | None = None, cameras: list[dict] | None = None, size: int = 640,
         save: str | None = None, show_layer: str | None = None, hide_parts: list[str] | None = None,
         only_parts: list[str] | None = None, flat: bool = False):
    """Render the saved scene with EEVEE: named views (as look) and/or perspective cameras {"eye": [x,y,z],
    "target", "fov"}. show_layer: one paint layer's mask, orange on grey clay. hide_parts / only_parts: leave
    parts out (prefab parts too, in every instance); with only_parts the views frame what's shown. flat: unlit
    base colour."""
    from PIL import Image
    from .spec import compile_prims, geometry
    bp = blend_path(name)
    spec = store.load(name)
    prims = [p for p in compile_prims(geometry(spec)) if p.op == "add"]
    allp = sorted({p.part for p in prims})
    bad = [p for p in (hide_parts or []) + (only_parts or []) if p not in allp]
    if bad:
        raise ValueError(f"no part(s) {bad}; parts: {allp}")
    hide = [p for p in allp if (only_parts and p not in only_parts) or p in (hide_parts or [])]
    frames = []
    if views:
        shown = [p for p in prims if p.part not in hide] or prims  # bounds for the ortho views
        lo, hi = np.min([p.lo for p in shown], 0), np.max([p.hi for p in shown], 0)
        lo, hi = lo - 0.06 * (hi - lo), hi + 0.06 * (hi - lo)
        frames += render.view_frames(np.array([[(lo, hi)[(i >> k) & 1][k] for k in range(3)] for i in range(8)]), views)
    for i, c in enumerate(cameras or []):
        frames.append(render.camera_frame(c, i))
    with tempfile.TemporaryDirectory() as tmp:
        for f in frames:
            f["out"] = str(Path(tmp) / f"{f['name']}.png")
        t = time.time()
        # 16 EEVEE samples look the same as the default 64 (mean 0.3/255 apart on cabin5) in half the time; glass
        # refracting the room behind it wants more
        glass = any((d or {}).get("transmission") or (d or {}).get("alpha", 1) < 1 for d in (spec.get("parts") or {}).values())
        job = {"mode": "render", "blend": str(bp), "views": frames, "size": size, "hide": hide, "flat": flat,
               "samples": 32 if glass else 16}
        if show_layer:  # that layer's mask alone (needs the program: compile it again)
            from . import paint, paintnodes
            names = list(paint.layers(spec))
            if not any(n == show_layer or n.startswith(show_layer + ":") for n in names):
                raise ValueError(f"no paint layer {show_layer!r}; layers: {', '.join(names)}")
            defs = spec.get("parts") or {}
            job.update(show_layer=show_layer, program=paintnodes.compile(spec),
                       bases={p: {"color": [0.5] * 3, "roughness": 0.6, "metallic": 0.0, "specular": 0.5}
                              for p in list(defs) + ["body"]})
        _blender(job)
        imgs = [Image.open(f["out"]) for f in frames]
    cover = None
    if show_layer:  # the mask glows orange: the share of the surface in view where it's on (alpha: surface)
        lit = seen = 0
        bg = Image.new("RGBA", imgs[0].size, (140, 150, 165, 255))
        for i, im in enumerate(imgs):
            a = np.asarray(im.convert("RGBA"), np.float64)
            surf = a[..., 3] > 127
            seen += surf.sum()
            lit += (surf & (a[..., 0] - a[..., 2] > 30)).sum()  # AgX desaturates the orange: r - b peaks ~85
            imgs[i] = Image.alpha_composite(bg, im.convert("RGBA"))
        cover = lit / max(seen, 1)
    imgs = [im.convert("RGB") for im in imgs]
    sheet = render.contact_sheet(imgs, frames)
    if save:
        sheet.save(save)
    look.coverage = cover
    return sheet, round(time.time() - t, 1)
