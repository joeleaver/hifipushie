"""The bake's scene: whether it needs OSL, the cage and its clearance, scene maps, FBX. Part of the game-ready export (asset.py has the overview)."""
from __future__ import annotations

import time
from pathlib import Path

import numpy as np

from . import asset
from . import render, sdf

def bake_needs_osl(job: dict, log) -> bool:
    """(2026-10-18, Garrett's export) Compile every bake pass of the parts' scene materials first (blender_scene.bake_maps
    check_only: seconds): a material too deep for Cycles' SVM stack (it would bake BLACK; a stacked skin of 61 layers, 20
    with height) makes the bake run with OSL instead (no stack limit; CPU, slower). True when OSL is needed."""
    from . import scene
    try:
        scene._blender({**job, "check_only": True}, 1800)
        return False
    except RuntimeError as e:
        if "shader stack" not in str(e):
            raise
        which = str(e).split("material(s) ", 1)[-1].split("]", 1)[0] + "]"
        log.append(f"WARNING bake: {which} too deep for Cycles' SVM shader stack: baking every map with OSL (CPU) instead")
        return True


def cage_verts(p: dict, d: np.ndarray, vx: float) -> np.ndarray:
    """The bake cage: each low-poly vertex pushed out along its (averaged) normal by its OWN faces' stray from the exact
    surface (d: field at the face centres, then the 3 edge midpoints of every face, as scene_maps probes) x1.5 + 2 voxels.
    One extrusion per part (the part's WORST stray) reached ~6 mm on Tess's body (GNM head + wrapped body in one part):
    inside a 5-8 mm nostril a texel's ray started past the opposite wall and baked dark pinwheel fans and a ragged rim
    (skin r14). The head is GNM's own mesh (stray ~0): its cage is ~2 voxels."""
    V = np.asarray(p["verts"], np.float64)
    C = np.asarray(p["corner_vert"], np.int64)
    nt = len(C) // 3
    dd = np.asarray(d, np.float64)
    stray = np.maximum(-dd[:nt], 0.0)
    stray = np.maximum(stray, np.maximum(-dd[nt:], 0.0).reshape(nt, 3).max(1))
    out = np.zeros(len(V))
    np.maximum.at(out, C, np.repeat(stray, 3))
    out = out * 1.5 + 2 * vx
    n = np.zeros_like(V)
    np.add.at(n, C, np.asarray(p["normal"], np.float64))
    n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-12)
    # (r64) never past the part's own opposite wall: the 2-voxel floor is up to ~14 mm on "body" (model voxel 7.1 mm),
    # where the head's low poly IS the high poly; at the alar groove and the nostril rims a texel's ray then started
    # past the other wall and baked it (Tess rc2p: a dark blocky patch on her left ala, pink-dark nostril rims)
    clear = _clearance(V, n, C.reshape(-1, 3), out)
    out = np.minimum(out, np.maximum(asset.CAGE_CLEAR * clear, asset.CAGE_MIN))
    return V + n * out[:, None]


def _clearance(V: np.ndarray, n: np.ndarray, T: np.ndarray, reach: np.ndarray, chunk: int = 1000) -> np.ndarray:
    """Per vertex, the distance along n to the first triangle of T (not one of its own) within reach (inf: none)."""
    from scipy.spatial import cKDTree
    A, B, Cc = V[T[:, 0]], V[T[:, 1]], V[T[:, 2]]
    cen = (A + B + Cc) / 3
    rad = np.max(np.linalg.norm(np.stack([A, B, Cc], 1) - cen[:, None], axis=2), axis=1)
    tree = cKDTree(cen)
    res = np.full(len(V), np.inf)
    rmax = float(rad.max(initial=0.0))
    for a in range(0, len(V), chunk):
        idx = np.arange(a, min(a + chunk, len(V)))
        near = tree.query_ball_point(V[idx], reach[idx] + rmax)
        vi = np.repeat(idx, [len(x) for x in near])
        if not len(vi):
            continue
        ti = np.concatenate([np.asarray(x, np.int64) for x in near])
        own = (T[ti] == vi[:, None]).any(1)
        vi, ti = vi[~own], ti[~own]
        e1, e2 = B[ti] - A[ti], Cc[ti] - A[ti]
        d = n[vi]
        pv = np.cross(d, e2)
        det = (e1 * pv).sum(1)
        ok = np.abs(det) > 1e-14
        inv = np.where(ok, 1.0 / np.where(ok, det, 1.0), 0.0)
        tv = V[vi] - A[ti]
        u = (tv * pv).sum(1) * inv
        qv = np.cross(tv, e1)
        w = (d * qv).sum(1) * inv
        t = (e2 * qv).sum(1) * inv
        hit = ok & (u >= 0) & (w >= 0) & (u + w <= 1) & (t > 1e-7)
        np.minimum.at(res, vi[hit], t[hit])
    return res


def scene_maps(name: str, parts: dict, sizes: dict, ctx: dict, resolution: int, log: list) -> dict:
    """The paint and AO maps of every atlas, baked by Cycles from the model's Blender scene (synced first) onto
    the low poly: {atlas: {"color" (linear), "rms", "ao"}}. Each part's rays reach as far as its low poly strays
    from the exact surface."""
    import tempfile
    from . import scene
    from . import scene_sync
    t = time.time()
    scene_sync.sync(name, resolution)
    log.append(f"scene synced in {time.time() - t:.1f}s")
    with tempfile.TemporaryDirectory(prefix="hifipushie-maps-") as tmp:
        jobs = []
        for pn, p in parts.items():
            vx = ctx["frames"][pn][1]
            c = p["verts"][p["corner_vert"]].reshape(-1, 3, 3).astype(np.float64)  # vertices sit on the surface:
            probe = np.concatenate([c.mean(1), (c + np.roll(c, 1, 1)).reshape(-1, 3) / 2])  # faces stray between
            d = sdf.field_at(ctx["streams"][pn], probe, clip=False)
            out_ = max(float(-np.min(d)), 0.0) * 1.5 + 2 * vx  # the exact surface outside the low poly
            in_ = max(float(np.max(d)), 0.0) * 1.5 + 2 * vx  # and inside it
            f = Path(tmp) / f"low{len(jobs)}.npz"
            extra = {}
            if asset.BAKE_CAGE:
                extra["cage"] = cage_verts(p, d, vx)
                out_ = float(np.max(np.linalg.norm(extra["cage"] - np.asarray(p["verts"], np.float64), axis=1), initial=0.0))
            np.savez(f, verts=p["verts"], corner_vert=p["corner_vert"], uv=p["uv"], normal=p["normal"], **extra)
            pf = next((q for q, dd in ctx["prefabs"].items() if pn in dd["parts"]), None)
            M = ctx["prefabs"][pf]["instances"][ctx["prefabs"][pf]["bake"]].tolist() if pf else None
            jobs.append({"key": pn, "scene_key": ctx.get("split", {}).get(pn, pn), "low": str(f), "atlas": p["atlas"],
                         "extrusion": out_, "ray": out_ + in_, "matrix": M})
        t = time.time()
        bj = {"mode": "bake_maps", "blend": str(scene.blend_path(name)), "parts": jobs,
              "atlases": {str(ai): sz for ai, sz in sizes.items()}, "out": tmp, "samples": asset.BAKE_SAMPLES,
              "supersample": asset.BAKE_SS, "max_px": asset.BAKE_SS_PX, "detail": ctx.get("bake_detail", True),
              "texel_m": ctx.get("texel_m", 0.0) if asset.BAKE_PREFILTER else 0.0}
        bj["osl"] = bake_needs_osl(bj, log)
        out = scene._blender(bj, 3 * 3600, progress=getattr(log, "note", None))
        bt = next((line[8:] for line in out.splitlines() if line.startswith("@@times")), "")
        log.append(f"paint and AO maps baked by Cycles from the scene in {time.time() - t:.1f}s ({bt})")
        res = {}
        for ai in sizes:
            with np.load(Path(tmp) / f"atlas{ai}.npz") as z:
                res[ai] = {k: z[k] for k in z.files}
    return res


def write_fbx(glb: Path, fbx: Path) -> None:
    """The GLB as FBX for Unity and Unreal (skeleton, skin, textures embedded): `blender_fbx.py`."""
    from . import resources
    r = resources.run([render.BLENDER, "-b", "--factory-startup", "--python-exit-code", "1",
                       "--python", str(Path(__file__).with_name("blender_fbx.py")), "--", str(glb), str(fbx)],
                       capture_output=True, text=True, timeout=900)
    if r.returncode or not fbx.exists():
        raise RuntimeError(f"fbx export failed:\n{r.stdout[-2000:]}\n{r.stderr[-2000:]}")
