"""Inputs to the scene's materials: calibration, world and placed points, the raytraced inputs, paint inputs. Part of the live Blender scene (scene.py has the overview)."""
from __future__ import annotations

import hashlib
import json
import tempfile
import time
from pathlib import Path

import numpy as np

from . import sdf
from . import scene

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
    c = scene.CALIBRATION.get(key)
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
    job = {"mode": "bake_inputs", "ao_distance": scene.RT["ao_distance"] * size, "sky_distance": scene.RT["sky_distance"] * size,
           "samples": scene.RT["samples"], "device": device}
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
            out = scene._blender(job, 3600)
            bt = next((line[8:] for line in out.splitlines() if line.startswith("@@times")), "")
            for o, sub in zip(objs, todo):
                f = Path(tmp) / (o["key"].replace("/", "__") + ".npz")
                if not f.exists():
                    continue
                with np.load(f) as z, np.load(o["mesh"]) as m:
                    if sub is None:
                        raw = {n: z[n] for n in scene.RAYTRACED}
                    else:
                        with np.load(raw_of[o["key"]]) as r0:
                            raw = {n: r0[n].copy() for n in scene.RAYTRACED}
                        for n in scene.RAYTRACED:
                            raw[n][z["idx"]] = z[n]
                    sm = {n: _smooth(raw[n].astype(np.float64), m["faces"], scene.RT["smooth"]) for n in scene.RAYTRACED}
                    final = {n: calibrate(n, sm[n]).astype(np.float32) for n in scene.RAYTRACED}
                    final["ao_raw"] = sm["ao"].astype(np.float32)  # the export's AO map: Cycles' own, uncalibrated
                np.savez(raw_of[o["key"]], **raw, **{f"final_{n}": v for n, v in final.items()})
                stamps[o["key"]] = hashlib.sha1(b"".join(np.round(final[n], 4).tobytes() for n in scene.RAYTRACED)).hexdigest()[:10]
        log.append(f"Cycles AO and sky: {n_bake} vertices baked"
                   f"{'' if all(s is None for s in todo) else f' ({len(boxes)} building primitives changed)'}, "
                   f"{time.time() - t:.1f}s (blender {bt})")
    sf.write_text(json.dumps({"params": pkey, "prims": fps, "stamps": stamps,
                              "objects": {o["key"]: _placed(o, ctx) for o in objs}}))
    out = {}
    for o in objs:
        with np.load(raw_of[o["key"]]) as z:
            out[o["key"]] = {n: z[f"final_{n}"] for n in (*scene.RAYTRACED, "ao_raw")}
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
    ours = [k for k in prog["inputs"] if k not in scene.RAYTRACED]
    building = hashlib.sha1(json.dumps(sorted(_placed(o, ctx) for o in objs if not o["prefab"])).encode()).hexdigest()
    prog_id = hashlib.sha1(json.dumps([prog["fallbacks"], prog["packing"], ours, INPUTS_VERSION, scene.RT, scene.CALIBRATION,
                                       scene.LAYOUT],
                                      sort_keys=True, default=str).encode()).hexdigest()[:12]
    from .paint_masks import hand_painted, painted_values
    hand = hand_painted(spec)  # layers painted by hand: each object on their parts carries an attribute to paint
    last = cache / "inputs_state.json"
    st = json.loads(last.read_text()) if last.exists() else {}
    run = hashlib.sha1(json.dumps([building, prog_id, sorted(_placed(o, ctx) for o in objs), hand]).encode()).hexdigest()[:12]
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
                for k in scene.RAYTRACED:
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
        vals = {k: rt[o["key"]][k] for k in scene.RAYTRACED if k in rt.get(o["key"], {})}
        for f in (ffile[o["key"]], mfile[o["key"]]):
            with np.load(f) as z:
                vals.update({k: z[k] for k in z.files})
        packs = {}  # an EEVEE material reads at most paintnodes.MAX_ATTRS vertex attributes: scalars go four to one
        for attr, (pk, ch) in prog["packing"].get(o["part"], {}).items():
            packs.setdefault(pk, np.zeros((len(v), paintnodes.PACK), np.float32))[:, ch] = vals[attr]
        vec = {k: vals[k].astype(np.float32) for k in scene.VECTOR_INPUTS if k in vals}  # their own vector attributes
        arrays = {"wpos": v.astype(np.float32), "wnrm": n.astype(np.float32), **packs, **vec}
        if "ao_raw" in rt.get(o["key"], {}):  # a plain attribute: baked into the export's AO map
            arrays["ao_raw"] = rt[o["key"]]["ao_raw"]
        for ly, (pid, parts) in hand.items():  # a colour attribute to paint, showing the mask as it stands
            if "*" in parts or o["part"] in parts:
                arrays[f"hp_paint:{ly}"] = painted_values(pid, v, n).astype(np.float32)
        h = hashlib.sha1()
        for k in sorted(arrays):
            h.update(k.encode() + np.round(arrays[k], 4).tobytes())
        f = cache / f"{o['hash']}_in_{h.hexdigest()[:12]}.npz"
        if not f.exists():
            np.savez(f, **arrays)
        o["inputs"] = str(f)
        o["hash"] = f"{o['hash']}:{h.hexdigest()[:12]}"
        made[o["key"]] = str(f)
    last.write_text(json.dumps({"run": run, "objects": made,
                                "files": sorted(str(f) for fs in (ffile, mfile) for f in fs.values())}))
    return prog
