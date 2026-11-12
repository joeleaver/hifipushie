"""Parts on the way to the atlas: planar UVs, the low poly, flattened parts, part weights and triangle limits,
focus regions and decals, atlas groups, texture loads, the log. Part of the game-ready export (asset.py has the overview)."""
from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np

from . import asset
from . import store
from .asset_budget import _blender, margin_px, min_part

def planar_uvs(part: dict) -> dict:
    """0..1 UVs projected along the part's thinnest axis (PCA of its vertices), upright (image up = world up),
    aspect kept and centred; tangents
    and signs to match (MikkTSpace-consistent for a flat surface: the U axis on the tangent plane). For a flat,
    swappable surface (parts.<p>.uv = "planar"): its front fills the texture as a 2D image would. Its back and rim
    land on the same texels (only the front's look matters: an engine replaces the texture)."""
    V = np.asarray(part["verts"], np.float64)
    cv = np.asarray(part["corner_vert"])
    c = V.mean(0)
    _, _, vt = np.linalg.svd(V - c, full_matrices=False)
    na = vt[2]  # the thinnest axis: the projection direction
    nrm = np.asarray(part["normal"], np.float64)
    if (nrm @ na).mean() < 0:  # look at the side most corners face (the front)
        na = -na
    # image up = world up (+Z) on the surface; a lying surface (a table top): up = toward its back (+Y; creatures and
    # props face -Y). (u, v, n) right-handed, so the front reads as an image: upright, not mirrored
    up = np.array([0.0, 0.0, 1.0])
    va = up - (up @ na) * na
    if np.linalg.norm(va) < 0.3:
        up = np.array([0.0, 1.0, 0.0])
        va = up - (up @ na) * na
    va /= np.linalg.norm(va)
    ua = np.cross(va, na)
    P = V[cv] - c
    u, v = P @ ua, P @ va
    span = max(np.ptp(u), np.ptp(v), 1e-9)
    uv = np.stack([(u - u.min()) / span + (1 - np.ptp(u) / span) / 2,
                   (v - v.min()) / span + (1 - np.ptp(v) / span) / 2], -1)
    t = ua[None, :] - nrm * (nrm @ ua)[:, None]
    t /= np.maximum(np.linalg.norm(t, axis=1, keepdims=True), 1e-12)
    sign = np.where(np.einsum("ij,ij->i", np.cross(nrm, t), np.broadcast_to(va, t.shape)) >= 0, 1.0, -1.0)
    return {"uv": uv.astype(np.asarray(part["uv"]).dtype), "tangent": t.astype(np.asarray(part["tangent"]).dtype),
            "sign": sign.astype(np.asarray(part["sign"]).dtype)}


def lowpoly(high: Path, out: Path, cfg: dict, triangles: int, sizes: dict, voxel: float = 0.0,
            tri_focus: list | None = None) -> tuple[dict, dict]:
    """Decimate + unwrap in Blender. cfg: {part: {"weight": triangle weight, "density": texel density,
    "atlas": index}}, sizes: {atlas index: texels}, voxel: the scene voxel (flat regions within a quarter of it
    are dissolved before the collapse). Returns ({part: {verts, corner_vert, uv, normal, tangent, sign,
    atlas}}, info from Blender: per part the joint decimation's count, the budget and whether it came out mirrored;
    timings). tri_focus: [[x, y, z, radius, k]]: the mesh is decimated magnified k x round those spheres and put
    back (focuswarp.py): more triangles where face shapes deform (lids, lips)."""
    import hashlib
    st = high.stat()
    # what the decimation depends on (not the atlases): a regroup for other atlas sizes re-unwraps only
    key = hashlib.sha1(json.dumps([str(high), st.st_size, st.st_mtime_ns, int(triangles), float(voxel),
                                   {pn: {k: v for k, v in c.items() if k != "atlas"} for pn, c in cfg.items()},
                                  tri_focus or [], "flipfit 1"],
                                  sort_keys=True, default=str).encode()).hexdigest()
    if tri_focus:  # decimate a magnified copy (its own file: flatten and the decimation cache key on the path)
        from . import focuswarp
        with np.load(high) as z:
            arrs = {k: z[k] for k in z.files}
        arrs["verts"] = focuswarp.warp(arrs["verts"], tri_focus).astype(arrs["verts"].dtype)
        high = out.with_name("high_focus.npz")
        np.savez(high, **arrs)
    flat = flatten_parts(high, out.with_name(out.stem + "_flat.npz"), list(cfg), 0.25 * float(voxel))
    _blender({"mode": "lowpoly", "mesh": str(high), "out": str(out), "parts": cfg, "triangles": int(triangles), "flat": flat,
              "min_part": min_part(triangles), "voxel": float(voxel), "textures": {str(a): int(t) for a, t in sizes.items()},
              "margins": {str(a): margin_px(int(t)) for a, t in sizes.items()},
              "decimated": {"path": str(out.with_name(out.stem + "_decimated.npz")), "key": key},
              "focus_warp": tri_focus or []}, timeout=3600)
    z = np.load(out)
    names = [str(n) for n in z["part_names"]]
    parts = {pn: {k: z[f"{i}_{k}"] for k in ("verts", "corner_vert", "uv", "normal", "tangent", "sign")}
             for i, pn in enumerate(names)}
    for pn, a in zip(names, z["atlas"]):
        parts[pn]["atlas"] = int(a)
    return parts, json.loads(str(z["info"]))


def flatten_parts(high: Path, path: Path, names: list, plane_tol: float) -> str:
    """Every part's flat regions dissolved to ngons (`planar.flatten`), in parallel processes, saved for the
    Blender job (per part i: {i}_V, {i}_L loop vertices, {i}_S loop sizes, {i}_gone). Kept while the mesh and
    tolerance are the same."""
    import hashlib
    from concurrent.futures import ProcessPoolExecutor
    from . import planar
    st = high.stat()
    key = hashlib.sha1(json.dumps([str(high), st.st_size, st.st_mtime_ns, plane_tol, sorted(names)]).encode()).hexdigest()
    if path.exists():
        with np.load(path) as z:
            if str(z["key"]) == key:
                return str(path)
    z = np.load(high)
    V, F, part = z["verts"], z["faces"], z["part"]
    all_names = [str(n) for n in z["part_names"]]
    fpart = part[F[:, 0]]
    todo, jobs = [], []
    for pn in names:
        sel = fpart == all_names.index(pn) if pn in all_names else np.zeros(len(F), bool)
        if not sel.any():
            continue
        used = np.unique(F[sel])
        remap = np.full(len(V), -1, np.int64)
        remap[used] = np.arange(len(used))
        todo.append(pn)
        jobs.append((V[used], remap[F[sel]], plane_tol))
    order = sorted(range(len(jobs)), key=lambda i: -len(jobs[i][1]))  # biggest first: they set the wall time
    from . import resources
    ex = ProcessPoolExecutor(max_workers=resources.workers(1.5, jobs=len(jobs)), initializer=resources._worker_init)
    with resources.guarded(ex, "flatten parts") as ex:
        got = dict(zip(order, ex.map(planar._flatten_job, [jobs[i] for i in order])))
    arrays = {"key": np.array(key), "names": np.array(todo)}
    for i in range(len(todo)):
        Vn, L, S, gone = got[i]
        arrays.update({f"{i}_V": Vn.astype(np.float32), f"{i}_L": L.astype(np.int32), f"{i}_S": S.astype(np.int32),
                       f"{i}_gone": gone})
    np.savez(path, **arrays)
    return str(path)


def part_areas(mesh: Path) -> dict:
    """Surface area (m^2) of each part of a built mesh that has any faces."""
    z = np.load(mesh)
    V, F = z["verts"].astype(np.float64), z["faces"]
    fpart = z["part"][F[:, 0]]
    area = np.linalg.norm(np.cross(V[F[:, 1]] - V[F[:, 0]], V[F[:, 2]] - V[F[:, 0]]), axis=1) / 2
    return {pn: float(area[fpart == i].sum()) for i, pn in enumerate(str(n) for n in z["part_names"])
            if (fpart == i).any()}


def _weight(defs: dict, pn: str, key: str) -> float:
    w = float((defs.get(pn) or {}).get(key, 1.0))
    if w <= 0:
        raise ValueError(f"parts.{pn}.{key} must be > 0")
    return w


def _min_triangles(defs: dict, pn: str) -> int | None:
    """parts.<p>.min_triangles: this part's floor per copy, in place of min_part (which pins every copy of a
    many-instance prefab, chain links say, at 300 whatever its triangle_weight)."""
    v = (defs.get(pn) or {}).get("min_triangles")
    if v is None:
        return None
    if int(v) < 0:
        raise ValueError(f"parts.{pn}.min_triangles must be >= 0")
    return int(v)


def _max_triangles(defs: dict, pn: str) -> int | None:
    """parts.<p>.max_triangles: this part's ceiling per copy (a LOD0 split inside a budget group: GNM's tooth rows
    and tongue came in whole at 2828 / 1824 and put eyes_mouth_lashes at 2.6x the hero's 5000)."""
    v = (defs.get(pn) or {}).get("max_triangles")
    if v is None:
        return None
    if int(v) < 1:
        raise ValueError(f"parts.{pn}.max_triangles must be >= 1")
    return int(v)


def focus_regions(spec: dict, pn: str) -> list:
    """parts.<p>.texel_focus: [{"at": point | joint | blob | {"bone", "t"}, "radius": m, "density": w}] as
    [[x, y, z, radius, density]]: islands inside get `density` times the part's own (the face of a character)."""
    items = (spec.get("parts", {}).get(pn) or {}).get("texel_focus") or []
    if isinstance(items, dict):
        items = [items]
    if not items:
        return []
    from .spec import expand_mirror, resolve_point
    full = expand_mirror(spec)
    out = []
    for it in items:
        c = resolve_point(full, it["at"])
        r, w = float(it.get("radius", 0.1)), float(it.get("density", 2.0))
        if r <= 0 or w <= 0:
            raise ValueError(f"parts.{pn}.texel_focus: radius and density must be > 0")
        out.append([float(c[0]), float(c[1]), float(c[2]), r, w])
    return out


def _cover(pts: np.ndarray, w: float, h: float) -> list:
    """Spheres [x, y, z, r] covering a decal's footprint points: one round them all when that fits about as tight
    as the decal's own half diagonal (planar decals, stickers), else greedy spheres of the decal's smaller side (a
    label wrapped round a can: one sphere round it all would take the whole can)."""
    half = 0.5 * float(np.hypot(w, h))
    c = pts.mean(0)
    r = float(np.linalg.norm(pts - c, axis=1).max())
    if r <= 1.15 * half:
        return [[*c.tolist(), r * 1.05]]
    rs = 0.6 * min(w, h)
    left = np.ones(len(pts), bool)
    out = []
    while left.any():
        c = pts[np.flatnonzero(left)[0]]
        near = left & (np.linalg.norm(pts - c, axis=1) <= 1.6 * rs)
        c = pts[near].mean(0)  # centred on what it takes
        inside = np.linalg.norm(pts - c, axis=1) <= rs
        if not (inside & left).any():
            inside = np.linalg.norm(pts - c, axis=1) <= np.linalg.norm(pts[near] - c, axis=1).max()
        left &= ~inside
        out.append([*c.tolist(), rs * 1.05])
    return out


def decal_focus(spec: dict, pn: str, base: float, box=None) -> list:
    """Focus regions over the part's image decals (paint `image`, images.py), so a picture or a page of text keeps
    about its own resolution in the atlas: spheres over each decal's footprint as it lies on the surface (wraps
    included), density = the image's pixels per metre (capped at DECAL_MAX) / the part's own density `base`
    (texels/m), at most DECAL_GAIN, never below 1. pn is the model part; box (lo, hi): only decals reaching it (a
    prefab's part is exported from its bake instance: a decal on another instance isn't on its texels)."""
    from . import images, paint
    out = []
    exp = None
    for name, ly in paint.layers(spec).items():
        lp = ly.get("part", "body")
        if lp != "*" and pn not in ([lp] if isinstance(lp, str) else lp):
            continue
        for img in images.layer_images(ly):
            if exp is None:
                exp = paint._expanded(spec)
            fr = images.frame(spec, img, exp, what=f"paint {name!r} image", parts=lp)
            if fr["wrap"] == "uv":  # no placement of its own (the whole head): the part's own density stands
                continue
            want = min(asset.DECAL_MAX, fr["px"][0] / fr["w"], fr["px"][1] / fr["h"])
            k = float(np.clip(want / max(base, 1e-9), 1.0, asset.DECAL_GAIN))
            if k <= 1.0:
                continue
            places = [fr] + ([images.mirrored(fr)] if fr["mirror"] or name.endswith(".L") else [])
            for f in places:
                pts = images.footprint(f)
                if box is not None:
                    pts = pts[((pts >= box[0]) & (pts <= box[1])).all(1)]
                if not len(pts):
                    continue
                for s in _cover(pts, f["w"], f["h"]):
                    if not any(np.allclose(o[:4], s) for o in out):
                        out.append([*(float(x) for x in s), k])
    return out


def atlas_groups(loads: dict, fixed: dict, atlases: int) -> dict:
    """Atlas name per part, by count. Parts with their own "atlas" (fixed) keep it; the others share atlas "0", or
    with atlases > 1 are split into that many ("0", "1", ...) by texture load, largest first into the lightest."""
    out = dict(fixed)
    load = [0.0] * max(1, int(atlases))
    for pn in sorted((pn for pn in loads if pn not in out), key=lambda pn: -loads[pn]):
        i = int(np.argmin(load))
        out[pn] = str(i)
        load[i] += loads[pn]
    return out


def texture_loads(mesh: Path, density: dict, focus: dict) -> dict:
    """Texels each part wants: area x density^2 (density in texels per metre, or relative), with its focus
    regions' faces at their density."""
    z = np.load(mesh)
    V, F = z["verts"].astype(np.float64), z["faces"]
    fpart = z["part"][F[:, 0]]
    c = V[F]
    area = np.linalg.norm(np.cross(c[:, 1] - c[:, 0], c[:, 2] - c[:, 0]), axis=1) / 2
    cen = c.mean(1)
    out = {}
    for i, pn in enumerate(str(n) for n in z["part_names"]):
        sel = fpart == i
        if pn not in density or not sel.any():
            continue
        w = np.ones(int(sel.sum()))
        for x, y, zz, r, k in focus.get(pn) or []:
            inside = np.linalg.norm(cen[sel] - [x, y, zz], axis=1) <= r
            w[inside & (w == 1)] = k
        out[pn] = float((area[sel] * (w * density[pn]) ** 2).sum())
    return out


class _Log(list):
    """The export log, echoed as it grows (stderr and workspace/<model>/progress.log, with the elapsed time) so a
    long export isn't silent until it returns."""

    def __init__(self, name: str):
        super().__init__()
        self.t0 = time.time()
        self.path = store.HOME / name / "progress.log"
        self.path.write_text("")

    def note(self, line: str):
        import sys
        msg = f"[{time.time() - self.t0:6.0f}s] {line}"
        print(msg, file=sys.stderr, flush=True)
        with open(self.path, "a") as f:
            f.write(msg + "\n")

    def append(self, line):
        super().append(line)
        self.note(str(line))
