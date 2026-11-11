"""The job that makes one tile at one LOD, and its collision mesh. Part of the terrain mesh (terrain_mesh.py has
the overview)."""
from __future__ import annotations

import os
import time
from pathlib import Path

import numpy as np

from . import profiling
from .profiling import span as _span
from .terrain_field import project
from .terrain_gltf import _to_gltf, write_glb
from .terrain_materials import _linear
from .terrain_mesh import _CTX
from .terrain_tile_border import _collapse_border
from .terrain_tile_finish import (
    _compact, _on_border, _prim, _shared, _textured_prep, _unflip_corners, _vertex_normals, split_normals,
)
from .terrain_tile_jobs import OVER_BUDGET, _dense, _work
from .terrain_tile_mesh import PRE, _boundary_edges, _decimate
from .terrain_volumes import BURIED_DEEP, BURIED_SHADE, EXPOSED_OFF, NORMAL_H

def _job_tile(ij):
    """Write one tile's LODs and collision (runs in a worker: everything it reads is in _CTX)."""
    i, j = ij
    c = _CTX
    G, v0, field, mats, cfg, out, vols = c["G"], c["v0"], c["field"], c["mats"], c["cfg"], c["out"], c["vols"]
    dense, collapsed, pos, depth, dirn = c["dense"], c["collapsed"], c["pos"], c["depth"], c["dirn"]
    CN, CW, CC, mat = c["CN"], c["CW"], c["CC"], c["mat"]
    stats, t_dec, wanted, wanted_bakes = [], 0.0, set(), []
    t_tile = time.time()
    lo, hi = G.bounds(i, j)
    trans = _to_gltf(np.array([[lo[0], lo[1], 0.0]]))[0]
    entry = {"i": i, "j": j, "min": [float(lo[0]), float(lo[1])], "max": [float(hi[0]), float(hi[1])], "lods": []}
    zmin, zmax = np.inf, -np.inf
    prevs = []
    # (a decimated mesh may only have canonical vertices on the tile's border planes)
    border_ok = lambda v: all(tuple(q) in pos for q in v[_on_border(v, lo, hi)])
    for k in range(G.lods):
        if (i, j) not in dense:
            entry["lods"].append(None)
            continue
        mark = profiling.snapshot()
        P, faces0, _ = _dense(c, (i, j))
        Fk = np.load(_work(c, "col", i, j, k))
        used = np.unique(Fk)
        remap = np.full(len(P), -1, np.int64)
        remap[used] = np.arange(len(used))
        Pk, Fk = P[used], remap[Fk]
        n_mc = len(faces0)
        td = time.time()
        _sp = _span(f"tile/lod{k}/decimate")
        _sp.__enter__()
        Pd = Fd = None
        if k > 0 and prevs:
            # from the last LOD's mesh (a fifth of the dense one's faces: the count search was most of the export's
            # time), its border collapsed to this LOD's chain; the dense mesh only if that can't be done
            Pp, Fp = prevs[-1]
            rp = np.array([pos.get(tuple(q), -1) for q in Pp])
            Fc, bad = _collapse_border(Pp, Fp, np.flatnonzero((rp >= 0) & ~np.isin(rp, c["keep"][k])), min_dot=0.0)
            if not bad:
                used = np.unique(Fc)
                remap = np.full(len(Pp), -1, np.int64)
                remap[used] = np.arange(len(used))
                Pd, Fd = _decimate(Pp[used], remap[Fc], cfg["error"][k], cfg["budget"][k], field, border_ok)
                if len(Fd) > 1.15 * cfg["budget"][k] + 64:
                    Pd = Fd = None
        if Pd is None:
            if k > 0:
                profiling.count(f"decimate: lod{k} from the dense mesh (the last LOD's didn't reach its budget)")
                if os.environ.get("HIFIPUSHIE_DECIMATE_DUMP"):  # (the inputs, to replay a straggler offline)
                    Pp, Fp = prevs[-1]
                    np.savez(Path(os.environ["HIFIPUSHIE_DECIMATE_DUMP"]) / f"dec_{i}_{j}_{k}.npz", Pk=Pk, Fk=Fk,
                             Pp=Pp, Fp=Fp, keep=np.asarray(c["keep"][k]), lo=np.asarray(lo), hi=np.asarray(hi),
                             pos=np.array(list(pos.keys()), float), posv=np.array(list(pos.values())),
                             err=cfg["error"][k], budget=cfg["budget"][k])
            with _span(f"tile/lod{k}/decimate from dense"):
                # (a coarse LOD from the dense mesh: one pass to PRE x its budget first, LOD 0 as it always was)
                Pd, Fd = _decimate(Pk, Fk, cfg["error"][k], cfg["budget"][k], field, border_ok,
                                   pre=PRE * cfg["budget"][k] if k > 0 else None)
        if k > 0 and prevs and len(Fd) > max(cfg["budget"][k], len(prevs[-1][1])):
            # this LOD from the dense mesh folded at every count: from an earlier LOD's mesh instead (the last one
            # first), its border collapsed to this LOD's chain (the same chain either way: neighbours still agree)
            profiling.count(f"decimate: lod{k} retried from earlier LODs (the dense mesh folded at every count)")
            for Pp, Fp in reversed(prevs):
                rp = np.array([pos.get(tuple(q), -1) for q in Pp])
                drop = np.flatnonzero((rp >= 0) & ~np.isin(rp, c["keep"][k]))
                Fc, bad = _collapse_border(Pp, Fp, drop, min_dot=0.0)
                if bad:
                    if len(Fd) > 1.2 * cfg["budget"][k]:
                        wanted |= {int(rp[u]) for u in bad}
                    continue
                used = np.unique(Fc)
                remap = np.full(len(Pp), -1, np.int64)
                remap[used] = np.arange(len(used))
                P2, F2 = _decimate(Pp[used], remap[Fc], cfg["error"][k], cfg["budget"][k], field, border_ok)
                if len(F2) < len(Fd):
                    Pd, Fd = P2, F2
                    break
        _sp.__exit__(None, None, None)
        t_dec += time.time() - td
        # border vertices must have come through untouched, and be this LOD's chain
        rowd = np.array([pos.get(tuple(p), -1) for p in Pd])
        on = _on_border(Pd, lo, hi)
        if np.any(on & (rowd < 0)):
            q = Pd[on & (rowd < 0)]
            inP = [bool(np.any(np.all(Pk == x, axis=1))) for x in q[:5]]
            be = np.unique(_boundary_edges(Fk)) if len(Fk) else np.zeros(0, np.int64)
            onb = [bool(np.any(np.all(Pk[be] == x, axis=1))) for x in q[:5]]
            raise RuntimeError(f"tile {i},{j} LOD {k}: {int(np.sum(on & (rowd < 0)))} border vertices moved in "
                               f"decimation, e.g. {q[:5].tolist()} (in the undecimated mesh: {inP}, on its open "
                               f"boundary: {onb})")
        bd = rowd >= 0
        N = np.zeros_like(Pd)
        before = Pd.copy()
        with _span(f"tile/lod{k}/project"):
            Pd[~bd], N[~bd] = project(field, Pd[~bd], v0)
        hn = NORMAL_H * v0
        # where projecting a coarse vertex folds its faces, it stays where decimation put it
        fold = ~bd & ((_vertex_normals(Pd, Fd) * N).sum(1) < 0.3)
        if fold.any():
            Pd[fold] = before[fold]
            N[fold] = _vertex_normals(Pd, Fd)[fold]
        N[bd] = CN[rowd[bd]]
        prevs.append((Pd.copy(), Fd.copy()))
        W = np.zeros((len(Pd), len(mats.layers)), np.float32)
        C = np.zeros((len(Pd), 3))
        W[bd], C[bd] = CW[rowd[bd]], CC[rowd[bd]]
        with _span(f"tile/lod{k}/vertex weights"):
            W[~bd], C[~bd] = mats.weights(Pd[~bd], N[~bd])
        # skirts along shared borders (not the world's edge)
        be = _boundary_edges(Fd)
        shared = np.array([_shared(Pd[a_], Pd[b_], lo, hi, G) for a_, b_ in be], bool) if len(be) else np.zeros(0, bool)
        be = be[shared] if len(be) else be
        sv = np.unique(be.ravel()) if len(be) else np.zeros(0, np.int64)
        top = Pd[sv]
        bot = top + dirn[rowd[sv]] * depth[k][rowd[sv]][:, None]
        m = {int(x): r_ for r_, x in enumerate(sv)}
        SP = np.empty((2 * len(sv), 3))
        SP[0::2], SP[1::2] = top, bot
        SN = np.repeat(N[sv], 2, 0)
        SC = np.repeat(C[sv], 2, 0)
        SW = np.repeat(W[sv], 2, 0)
        sf = []
        for a_, b_ in be:  # the face has a -> b; the skirt hangs below it, facing the same way
            ta, tb = 2 * m[int(a_)], 2 * m[int(b_)]
            sf += [(tb, ta, ta + 1), (tb, ta + 1, tb + 1)]
        sf = np.array(sf, np.int64).reshape(-1, 3)
        origin = np.array([lo[0], lo[1], 0.0])
        with _span(f"tile/lod{k}/split normals + buried"):
            Ps, Fs, Ns, src = split_normals(Pd, Fd, N, field, bd, hn)
            bur = np.zeros(len(Fs), bool)
            if hasattr(field, "front"):
                # a cliff shell: faces off the visible rock (its back, buried under the heightmap) go in their own
                # primitive, so an engine or a bake can skip them
                # (off it at the centre, unless all three corners are on it: a big face across the turf's step or a
                # lip's crease has its centre 0.3 m+ off the rock with every corner on it; taken for buried, it was
                # drawn with the plain matte material: the pale flat triangles at cliff lips. A face with one corner
                # on the front is the back's edge where it meets it: still buried)
                # (and its centre INSIDE the rock: a face whose centre stands out in the open is seen whatever its
                # corners say; called buried, it was drawn plain: white triangles through the island's cliffs)
                thr = max(0.3, 2 * cfg["error"][k])
                # (deep for its size: a big flat face over rounded rock has its centre a little inside it: a 570 m2
                # face of a near-empty tile, centre 0.36 m in, was called buried at LOD 0)
                fa = np.linalg.norm(np.cross(Ps[Fs[:, 1]] - Ps[Fs[:, 0]], Ps[Fs[:, 2]] - Ps[Fs[:, 0]]), axis=1) / 2
                bur = (field.front(Ps[Fs].mean(1)) < -np.maximum(thr, BURIED_DEEP * np.sqrt(fa))) & \
                    (np.abs(field.front(Ps))[Fs].max(1) > thr)
                # (and still in rock half a metre out along the face's own normal: what faces open air from just under
                # the surface is seen, as `terrain_cliffs.exposed_buried` judges it)
                kb = np.flatnonzero(bur)
                if len(kb):
                    fn = np.cross(Ps[Fs[kb, 1]] - Ps[Fs[kb, 0]], Ps[Fs[kb, 2]] - Ps[Fs[kb, 0]])
                    fn /= np.maximum(np.linalg.norm(fn, axis=1, keepdims=True), 1e-12)
                    bur[kb] = field.front(Ps[Fs[kb]].mean(1) + EXPOSED_OFF * fn) < 0
                    if hasattr(field, "region"):  # (under the pushed heightmap counts as hidden)
                        q = Ps[Fs[kb]].mean(1) + EXPOSED_OFF * fn
                        bur[kb] |= q[:, 2] <= field.region.height(q[:, 0], q[:, 1]) + 0.05
            Ps, Fs, Ns, src = _unflip_corners(Ps, Fs, Ns, src, ~bur, bd[src])
        stem = f"tile_{i}_{j}_lod{k}"
        from .terrain_bake import material as terrain_bake_material
        images, binfo, deferred = None, None, None
        if cfg.get("maps") and (~bur).any():
            Pv, Nv, Cv, Wv, Fv = _compact(Ps, Ns, C[src], W[src], Fs[~bur])
            with _span(f"tile/lod{k}/maps prep"):
                prim, binfo, deferred = _textured_prep(Pv, Nv, Wv, Fv, k, origin, stem)
            prims = [prim]
        else:
            prims = [_prim(*_compact(Ps - origin, Ns, C[src], W[src], Fs[~bur]), 0, {"role": "surface"}, mats, lo, cfg)]
        tile_mats = mat + ([terrain_bake_material("terrain_baked")] if (cfg.get("maps") and (~bur).any()) else [])
        if bur.any():
            # (its own material name: an importer that drops extras, Godot's, saw the back as a second skirt surface)
            # (and its own colour: the rock's mean colour there, in shade. White, it showed as pale plates wherever an
            # engine drew a piece of the back in the open (it ignores COLOR_0 without a vertex-colour material))
            cb = _linear(np.asarray(C[src][np.unique(Fs[bur])], float)[:, :3].mean(0)) * BURIED_SHADE
            tile_mats = tile_mats + [{**mat[0], "name": "terrain_buried",
                                      "pbrMetallicRoughness": {**mat[0]["pbrMetallicRoughness"],
                                                               "baseColorFactor": [*map(float, cb), 1.0]}}]
            prims.append(_prim(*_compact(Ps - origin, Ns, C[src], W[src], Fs[bur]), len(tile_mats) - 1,
                               {"role": "buried"}, mats, lo, cfg))
        if len(sf):
            prims.append(_prim(SP - origin, SN, SC, SW, sf, 1, {"role": "skirt"}, mats, lo, cfg))
        for pr in prims[1:]:  # (custom attributes on every primitive: Blender's importer can't merge them otherwise)
            for key in ("_DETAIL",):
                if key in prims[0]["attrs"] and key not in pr["attrs"]:
                    pr["attrs"][key] = np.zeros((len(pr["attrs"]["POSITION"]), prims[0]["attrs"][key].shape[1]))
        fn = f"{stem}.glb"
        glb = dict(path=out / fn, name=stem, prims=prims, trans=trans, mats=tile_mats,
                   extras={"tile": [i, j], "lod": k, "error_m": cfg["error"][k]})
        if deferred:  # (written by _job_finish once its texels are baked)
            import pickle
            with open(c["work"] / f"glb_{stem}.pkl", "wb") as fh:
                pickle.dump(glb, fh, protocol=pickle.HIGHEST_PROTOCOL)
            wanted_bakes.append(deferred)
        else:
            with _span(f"tile/lod{k}/write glb"):
                write_glb(glb["path"], stem, prims, trans, glb["mats"], extras=glb["extras"], images=images)
        if k == int(cfg["collision"]):
            cf = f"collision_{i}_{j}.glb"
            Pc, Fc = _collision_mesh(Pd, Fd, int(cfg.get("collision_budget") or OVER_BUDGET * cfg["budget"][k]))
            write_glb(out / cf, f"collision_{i}_{j}", [{"attrs": {"POSITION": _to_gltf(Pc - origin)},
                                                        "indices": Fc}], trans, None,
                      extras={"tile": [i, j], "collision": True, "from_lod": k})
            entry["collision"] = cf
            entry["collision_triangles"] = int(len(Fc))
        zmin, zmax = min(zmin, float(Pd[:, 2].min())), max(zmax, float(Pd[:, 2].max()))
        size_ = None if deferred else (out / fn).stat().st_size
        entry["lods"].append({"file": fn, "triangles": int(len(Fd)), "skirt_triangles": int(len(sf)),
                              "visible_triangles": int((~bur).sum()),
                              "marching_cubes_triangles": int(n_mc), "bytes": size_})
        if binfo:
            entry["lods"][-1]["maps"] = binfo
        entry["lods"][-1]["timing_s"] = _since(mark)
        stats.append((i, j, k, len(Fd), len(sf), n_mc, size_))
    entry["zmin"], entry["zmax"] = zmin, zmax
    entry["seconds"] = round(time.time() - t_tile, 1)
    entry["volumes"] = sorted({vol.name.split(":")[0] for vol in vols
                               if vol.touches(np.array([lo[0], lo[1], -1e9]), np.array([hi[0], hi[1], 1e9]))})
    entry["_bakes"] = wanted_bakes
    return entry, stats, t_dec, wanted


def _collision_mesh(P, F, budget):
    """A LOD's mesh for collision: as it is when within `budget` triangles, else decimated to it (pyfqmr, open borders
    kept; no fold or seam checks: physics doesn't shade, and a half-million-face trimesh for one 64 m tile is what an
    engine got when a LOD missed its budget)."""
    if len(F) <= budget:
        return P, F
    import pyfqmr
    s = pyfqmr.Simplify()
    s.setMesh(np.ascontiguousarray(P, float), np.ascontiguousarray(F, np.int64))
    s.simplify_mesh(target_count=int(budget), aggressiveness=7, max_iterations=300, preserve_border=True,
                    verbose=False)
    v, f, _ = s.getMesh()
    v, f = np.asarray(v, float), np.asarray(f, np.int64)
    return (v, f) if 0 < len(f) < len(F) else (P, F)


def _since(mark, min_s=0.05):
    """The spans (seconds, rounded) and field-point counts run since `mark` (a profiling.snapshot)."""
    now = profiling.snapshot()
    out = {}
    for k, (t, _) in now["spans"].items():
        d = t - mark["spans"].get(k, [0.0, 0])[0]
        if d >= min_s:
            out[k.split("/")[-1] if k.startswith("tile/") else k] = round(d, 2)
    n = now["counts"].get("field.solid pts", 0) - mark["counts"].get("field.solid pts", 0)
    if n:
        out["field points"] = int(n)
    return out
