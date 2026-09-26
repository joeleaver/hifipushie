"""Game-ready export: a low-poly mesh with UV atlases and PBR textures baked from the exact model.

Triangles per part follow geometric error (one joint decimation), scaled by parts.<p>.triangle_weight; texels
per metre follow parts.<p>.texel_density and texel_focus regions; a texel density (texels/m) opens atlases as
needed (or parts.<p>.atlas / atlases=n split the parts by hand), each with its own maps and GLB material.
Prefabs with 2+ instances are meshed and baked once (at their first instance) and placed by a node per instance.

Geometry is never baked from a high-poly mesh: each texel's point on the low-poly surface is projected onto the
exact field, and read there:
  normal        tangent-space (MikkTSpace, OpenGL / glTF convention: green = +V), from the field's gradient,
                tilted by the painted relief's slope
  height        signed distance from the low-poly surface to the exact one along the low-poly normal (m), plus
                the painted relief; low poly + height reproduces the sculpt. 16-bit PNG, 0.5 = 0,
                +-`height_range` m at 0 / 1.
Paint and AO come from the model's Blender scene (`scene_maps`), baked by Cycles onto the low poly per pixel:
  basecolor, roughness, metallic, specular   the scene's shader nodes (paint layers compiled by paintnodes)
  ao            the scene's Cycles AO: each asset's own (a prop never shadows the building or another prop)
  orm           glTF packing: R = ao, G = roughness, B = metallic
Plus asset.glb (glTF 2.0, Y up, the creature facing +Z, one mesh per part, one material per atlas with base
colour, ORM, normal and KHR_materials_specular) and asset.json describing all of it (mm/texel per part).
"""

from __future__ import annotations

import json
import os
import struct
import subprocess
import tempfile
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from . import assemble, render, sdf, store, surface
from .spec import compile_prims

SCRIPT = Path(__file__).with_name("blender_asset.py")


def _blender(job: dict, timeout: float = 600):
    with tempfile.TemporaryDirectory(prefix="hifipushie-asset-") as tmp:
        p = Path(tmp) / "job.json"
        p.write_text(json.dumps(job))
        r = subprocess.run([render.BLENDER, "-b", "--factory-startup", "--python-exit-code", "1",
                            "--python", str(SCRIPT), "--", str(p)], capture_output=True, text=True, timeout=timeout)
        if r.returncode:
            raise RuntimeError(f"blender failed:\n{r.stdout[-3000:]}\n{r.stderr[-3000:]}")


def margin_px(texture: int) -> int:
    """Gap between UV islands in texels: enough for bilinear filtering and the first mips (dilation fills it)."""
    return max(2, texture // 512)


def min_part(triangles: int) -> int:
    """No part gets fewer triangles than this (or all it has): eyes, teeth, pots stay round."""
    return max(300, triangles // 100)


def lowpoly(high: Path, out: Path, cfg: dict, triangles: int, sizes: dict, voxel: float = 0.0) -> tuple[dict, dict]:
    """Decimate + unwrap in Blender. cfg: {part: {"weight": triangle weight, "density": texel density,
    "atlas": index}}, sizes: {atlas index: texels}, voxel: the scene voxel (flat regions within a quarter of it
    are dissolved before the collapse). Returns ({part: {verts, corner_vert, uv, normal, tangent, sign,
    atlas}}, info from Blender: per part the joint decimation's count, the budget and whether it came out mirrored;
    timings)."""
    import hashlib
    st = high.stat()
    # what the decimation depends on (not the atlases): a regroup for other atlas sizes re-unwraps only
    key = hashlib.sha1(json.dumps([str(high), st.st_size, st.st_mtime_ns, int(triangles), float(voxel),
                                   {pn: {k: v for k, v in c.items() if k != "atlas"} for pn, c in cfg.items()}],
                                  sort_keys=True, default=str).encode()).hexdigest()
    flat = flatten_parts(high, out.with_name(out.stem + "_flat.npz"), list(cfg), 0.25 * float(voxel))
    _blender({"mode": "lowpoly", "mesh": str(high), "out": str(out), "parts": cfg, "triangles": int(triangles), "flat": flat,
              "min_part": min_part(triangles), "voxel": float(voxel), "textures": {str(a): int(t) for a, t in sizes.items()},
              "margins": {str(a): margin_px(int(t)) for a, t in sizes.items()},
              "decimated": {"path": str(out.with_name(out.stem + "_decimated.npz")), "key": key}}, timeout=3600)
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
    with ProcessPoolExecutor(max_workers=max(1, min(len(jobs), (os.cpu_count() or 4) - 1))) as ex:
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


BAKE_SAMPLES = 1  # emission bakes: one sample per texel (4 cost 4x and changed nothing measurable)
FILL = 0.6  # the fraction of an atlas the packed islands fill: a first guess, corrected from the first unwrap


def _pow2(x: float, lo: int = 256) -> int:
    return int(max(lo, 2 ** int(np.ceil(np.log2(max(x, 1.0))))))


def density_groups(units: dict, loads: dict, fixed: dict, max_texture: int, fill: float) -> dict:
    """Atlas name per part, from a texel density: units ({unit: [parts]}, a prefab's parts stay together) go
    largest first into the first atlas with room (max_texture^2 x fill texels), opening atlases as needed.
    fixed: parts with their own "atlas" name, which they keep."""
    cap = max_texture ** 2 * fill
    out = dict(fixed)
    bins: list[float] = []
    for u in sorted(units, key=lambda u: -sum(loads[p] for p in units[u])):
        ps = [p for p in units[u] if p not in fixed]
        need = sum(loads[p] for p in ps)
        if not ps:
            continue
        i = next((k for k, b in enumerate(bins) if b + need <= cap), None)
        if i is None:
            bins.append(0.0)
            i = len(bins) - 1
        bins[i] += need
        for p in ps:
            out[p] = str(i)
    return out


def split(spec: dict, resolution: int, instancing: bool, log: list, min_share: int = 2) -> dict:
    """What gets meshed and baked: the model's parts, minus the instances of shared prefabs, plus one copy of each
    shared prefab's parts (named "<prefab>/<part>") taken from its bake instance (the first unmirrored one).
    A prefab is shared when it has `min_share`+ instances (the scene uses 1: every instance is a movable object),
    unless prefabs.<p>.export is "unique" (then its instances are
    baked into the scene like any element). Returns {"streams": {export part: prims}, "origin": {export part:
    model part}, "frames": {export part: (lo, voxel, shape)}, "voxel": scene voxel, "full": {model part: prims}
    (the whole model: AO, sky and paint context), "prefabs": {prefab: {"bake": instance, "instances": {instance:
    local -> world 4x4}, "parts": [export parts]}}}."""
    prims = compile_prims(spec)
    full = {ps[0].part: ps for ps in sdf.streams(prims)}
    lo, voxel, shape = sdf.frame(prims, resolution)
    pls = assemble.placements(spec) if instancing else {}
    by_pf: dict[str, list] = {}
    for inst, pl in pls.items():
        by_pf.setdefault(pl["use"], []).append(inst)
    shared = {}
    for pf, insts in by_pf.items():
        mode = ((spec.get("prefabs") or {}).get(pf) or {}).get("export", "share")
        if mode not in ("share", "unique"):
            raise ValueError(f"prefabs.{pf}.export is \"share\" or \"unique\"")
        if mode == "unique" or len(insts) < min_share:
            log.append(f"prefab {pf}: {len(insts)} instance(s) baked into the scene"
                       + (" (export: unique)" if mode == "unique" else ""))
            continue
        bake = next((i for i in insts if not pls[i]["mirror"]), insts[0])
        shared[pf] = {"bake": bake, "instances": {i: assemble.world_of(pls[i]) for i in insts}, "parts": []}
    owner = {inst: pf for pf, d in shared.items() for inst in d["instances"]}
    xs, origin = {}, {}
    for pn, ps in full.items():
        groups: dict[str, list] = {}
        shells = [p for p in ps if p.kind == "shell"]
        for p in ps:
            if p.kind == "shell":
                continue
            pf = owner.get(p.instance)
            if pf is not None and p.instance != shared[pf]["bake"]:
                continue
            groups.setdefault(pn if pf is None else f"{pf}/{pn}", []).append(p)
        for key, g in groups.items():
            if not any(q.op in ("add", "intersect") for q in g):
                continue  # only cuts (or a shell's region is all on instances)
            xs[key], origin[key] = shells + g, pn
            if key != pn:
                shared[key.split("/")[0]]["parts"].append(key)
    frames = {}
    for key, ps in xs.items():
        if key == origin[key]:
            frames[key] = (lo, voxel, shape)
            continue
        # a prefab is meshed in a box of its own, finer if it's small (`resolution` voxels across it)
        pf = key.split("/")[0]
        own = [q for k in shared[pf]["parts"] for q in xs[k] if q.kind != "shell" and q.op in ("add", "intersect")]
        a, b = np.min([q.lo for q in own], 0) - 0.02, np.max([q.hi for q in own], 0) + 0.02
        v = min(voxel, float((b - a).max()) / resolution)
        frames[key] = (a, v, np.ceil((b - a) / v).astype(int) + 1)
    for pf, d in shared.items():
        v = frames[d["parts"][0]][1] if d["parts"] else voxel
        log.append(f"prefab {pf}: {len(d['instances'])} instances share one mesh and one set of texels, baked at "
                   f"{d['bake']} (its paint, AO and sky as it stands there; voxel {v * 1000:.1f} mm)")
    return {"streams": xs, "origin": origin, "frames": frames, "voxel": float(voxel), "full": full,
            "prefabs": {pf: d for pf, d in shared.items() if d["parts"]}}


def mesh_parts(ctx: dict, out: Path) -> Path:
    """Mesh every export part on its frame and project it onto its exact surface (as store.build does)."""
    V, F, N, P, names = [], [], [], [], []
    for key, ps in ctx["streams"].items():
        lo, vx, shape = ctx["frames"][key]
        f, _ = sdf.PartGrid().update(ps, (lo, vx, shape))
        m = store._mesh_part(ps, f, lo, vx, [], {})
        if m is False:
            continue
        v, fc, n, _ = m
        F.append(fc + sum(len(x) for x in V))
        V.append(v)
        N.append(n)
        P.append(np.full(len(v), len(names), np.int16))
        names.append(key)
    np.savez(out, verts=np.concatenate(V), faces=np.concatenate(F), normals=np.concatenate(N),
             part=np.concatenate(P), part_names=np.array(names))
    return out


def split_big(mesh: Path, ctx: dict, rel: dict, texture: int, log: list) -> None:
    """A part (not a prefab's) that wants more texels than one `texture` atlas holds at its density is cut into
    slabs of equal load along its longest side ("roof~0", "roof~1", ...), each an export part of its own on the
    same exact surface (ctx streams, frames and origin copied), so each can take an atlas. The slabs keep the
    vertices they share on the high mesh, so the joint decimation keeps them joined (lowpoly never re-decimates
    them alone: `split` in their cfg)."""
    z = dict(np.load(mesh))
    V, F, part = z["verts"].astype(np.float64), z["faces"], z["part"].copy()
    names = [str(n) for n in z["part_names"]]
    fpart = part[F[:, 0]]
    c = V[F]
    area = np.linalg.norm(np.cross(c[:, 1] - c[:, 0], c[:, 2] - c[:, 0]), axis=1) / 2
    cap = texture ** 2 * FILL
    pf_parts = {pn for d in ctx["prefabs"].values() for pn in d["parts"]}
    changed = False
    for i, pn in enumerate(list(names)):
        sel = fpart == i
        load = float(area[sel].sum()) * rel.get(pn, 1.0) ** 2
        if pn in pf_parts or not sel.any() or load <= cap:
            continue
        k = int(np.ceil(load / cap))
        cen = c[sel].mean(1)
        ax = int(np.argmax(np.ptp(cen, 0)))
        order = np.argsort(cen[:, ax])
        cum = np.cumsum(area[sel][order]) / area[sel].sum()
        cuts = [float(cen[order[np.searchsorted(cum, j / k)], ax]) for j in range(1, k)]
        vids = np.unique(F[sel])
        grp = np.searchsorted(cuts, V[vids, ax])
        new = [f"{pn}~{j}" for j in range(k)]
        idx = [i] + [len(names) + j for j in range(k - 1)]
        names[i] = new[0]
        names += new[1:]
        part[vids] = np.asarray(idx, part.dtype)[grp]
        for n in new:
            for key in ("streams", "frames", "origin"):
                ctx[key][n] = ctx[key][pn]
        for key in ("streams", "frames", "origin"):
            ctx[key].pop(pn)
        ctx.setdefault("split", {}).update({n: pn for n in new})
        log.append(f"{pn}: {load / cap:.1f} atlases' worth of texels at its density ({FILL:.0%} packed): split into "
                   f"{k} along {'xyz'[ax]} ({', '.join(new)})")
        changed = True
    if changed:
        z["part"], z["part_names"] = part, np.array(names)
        np.savez(mesh, **z)


def prune_hidden(ctx: dict, mesh: Path, log: list) -> Path:
    """Drop faces buried inside another part (skin under solid clothing shells, the back of an eyeball in its
    socket, tooth roots, a chair's feet in the floor): nobody sees them, and they'd take triangles and atlas space."""
    z = dict(np.load(mesh))
    names = [str(n) for n in z["part_names"]]
    hidden = surface.hidden(ctx["streams"], z["verts"].astype(np.float64), z["part"], names, ctx["voxel"]) > 0.5
    faces = z["faces"]
    keep = ~hidden[faces].all(1)
    dropped = {pn: int((~keep & (z["part"][faces[:, 0]] == i)).sum()) for i, pn in enumerate(names)}
    log.append("hidden faces dropped: " + ", ".join(f"{k} {v}" for k, v in dropped.items() if v) if any(
        dropped.values()) else "no hidden faces")
    z["faces"] = faces[keep]
    np.savez(mesh, **z)
    return mesh


def rasterize(parts: dict, size: int, atlas: int | None = None):
    """Which triangle covers each texel and where: (texel rows and columns, triangle id, barycentrics, part index
    of every triangle). Triangle ids and part indices count over all parts in order; only the parts on `atlas`
    (None: all) are drawn. Texel (x, y) of the PNG (row 0 at the top) is uv ((x + .5) / size, 1 - (y + .5) / size)."""
    img = Image.new("I", (size, size), -1)
    d = ImageDraw.Draw(img)
    uvs, tpart, draw = [], [], []
    for pi, p in enumerate(parts.values()):
        uvs.append(p["uv"].reshape(-1, 3, 2))
        tpart.append(np.full(len(uvs[-1]), pi))
        draw.append(np.full(len(uvs[-1]), atlas is None or p.get("atlas", 0) == atlas))
    uv = np.concatenate(uvs).astype(np.float64)
    px = np.stack([uv[..., 0] * size, (1 - uv[..., 1]) * size], -1)
    for t in np.flatnonzero(np.concatenate(draw)):
        d.polygon([tuple(q) for q in px[t]], fill=int(t))
    tid = np.asarray(img, np.int64)
    ys, xs = np.nonzero(tid >= 0)
    t = tid[ys, xs]
    a, b, c = px[t, 0], px[t, 1], px[t, 2]
    q = np.stack([xs + 0.5, ys + 0.5], -1)
    v0, v1, v2 = b - a, c - a, q - a
    den = v0[:, 0] * v1[:, 1] - v1[:, 0] * v0[:, 1]
    den = np.where(np.abs(den) < 1e-12, 1e-12, den)
    w1 = (v2[:, 0] * v1[:, 1] - v1[:, 0] * v2[:, 1]) / den
    w2 = (v0[:, 0] * v2[:, 1] - v2[:, 0] * v0[:, 1]) / den
    raw = np.stack([1 - w1 - w2, w1, w2], -1)
    inside = (raw >= -1e-6).all(1)  # the texel's centre lies in its triangle (edge texels PIL adds don't)
    bary = np.clip(raw, 0, 1)
    bary /= bary.sum(1, keepdims=True)
    return (ys, xs), t, bary, np.concatenate(tpart), inside


def uv_islands(parts: dict) -> np.ndarray:
    """UV island id per triangle (over all parts, in order): triangles joined across edges whose two corners have
    the same vertices and uvs on both sides."""
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components
    keys, tris = [], []
    t0 = 0
    for pi, p in enumerate(parts.values()):
        cv = p["corner_vert"].reshape(-1, 3).astype(np.int64)
        uv = np.round(p["uv"].reshape(-1, 3, 2) * 2 ** 20).astype(np.int64)
        for a, b in ((0, 1), (1, 2), (2, 0)):
            swap = cv[:, a] > cv[:, b]
            va, vb = np.where(swap, cv[:, b], cv[:, a]), np.where(swap, cv[:, a], cv[:, b])
            ua, ub = np.where(swap[:, None], uv[:, b], uv[:, a]), np.where(swap[:, None], uv[:, a], uv[:, b])
            keys.append(np.column_stack([np.full(len(cv), pi), va, vb, ua, ub]))
            tris.append(t0 + np.arange(len(cv)))
        t0 += len(cv)
    keys, tris = np.concatenate(keys), np.concatenate(tris)
    _, inv = np.unique(keys, axis=0, return_inverse=True)
    inv = inv.ravel()
    order = np.argsort(inv, kind="stable")
    same = inv[order][1:] == inv[order][:-1]  # consecutive triangles sharing an edge key
    a, b = tris[order][:-1][same], tris[order][1:][same]
    g = coo_matrix((np.ones(len(a)), (a, b)), shape=(t0, t0))
    return connected_components(g, directed=False)[1]


def _project(prims, P: np.ndarray, ys: np.ndarray, xs: np.ndarray, island: np.ndarray, vx: float, step: int = 4):
    """surface.newton for texels, cheaper: every `step`-th texel (both ways) is projected from the low poly; the
    rest start from their low-poly point moved by the offset interpolated from the anchors around them (on their
    own uv island), a step or two from converged. Where the low poly lies near the surface that is the point a
    start from the low poly finds; where it strays (bridged gaps, rounded-off corners) the nearest surface is
    ambiguous and the two may differ, equally on the surface (cabin5 at 6 mm texels: residuals the same or
    lower, 1.6-2x faster)."""
    anc = (ys % step == 0) & (xs % step == 0)
    X, G = P.copy(), np.zeros_like(P)
    if anc.sum() < 16 or anc.mean() > 0.5:
        return surface.newton(prims, P, 0.1 * vx, vx)
    X[anc], G[anc] = surface.newton(prims, P[anc], 0.1 * vx, vx)
    # the anchors' offsets on a grid, with their islands
    gy, gx = ys[anc] // step, xs[anc] // step
    H, W = gy.max() + 2, gx.max() + 2
    k = np.full((H, W), -1, np.int64)
    k[gy, gx] = np.flatnonzero(anc)
    rest = np.flatnonzero(~anc)
    cy, cx = ys[rest] // step, xs[rest] // step
    u, v = (xs[rest] % step) / step, (ys[rest] % step) / step
    off, wsum = np.zeros((len(rest), 3)), np.zeros(len(rest))
    for dy, dx, w in ((0, 0, (1 - u) * (1 - v)), (0, 1, u * (1 - v)), (1, 0, (1 - u) * v), (1, 1, u * v)):
        yy, xx = np.minimum(cy + dy, H - 1), np.minimum(cx + dx, W - 1)
        a = k[yy, xx]
        ok = (a >= 0) & (island[np.maximum(a, 0)] == island[rest])
        w = np.where(ok, w, 0.0)
        off += w[:, None] * (X[np.maximum(a, 0)] - P[np.maximum(a, 0)])
        wsum += w
    has = wsum > 1e-9
    start = P[rest].copy()
    start[has] += off[has] / wsum[has, None]
    X[rest], G[rest] = surface.newton(prims, start, 0.1 * vx, vx)
    return X, G


def _corners(parts: dict, key: str) -> np.ndarray:
    out = []
    for p in parts.values():
        v = p["verts"][p["corner_vert"]] if key == "pos" else p[key]
        out.append(v.reshape(len(p["corner_vert"]) // 3, 3, -1))
    return np.concatenate(out).astype(np.float64)


def _dilate(img: np.ndarray, filled: np.ndarray) -> np.ndarray:
    """Fill empty texels from the nearest filled one, so filtering and mips don't pull in background at seams."""
    from scipy import ndimage
    _, (iy, ix) = ndimage.distance_transform_edt(~filled, return_indices=True)
    return img[iy, ix]


def _unit(v):
    return v / np.maximum(np.linalg.norm(v, axis=-1, keepdims=True), 1e-12)


def bake(parts: dict, size: int, ctx: dict, log: list, atlas: int | None, given: dict) -> dict:
    """Every map of one atlas (None: all parts) as float arrays (size, size, k), plus the height range. Each
    texel is projected onto its export part's own field (normal, height); given: the maps Cycles baked from the
    scene (`scene_maps`: color linear, rms, ao, height; rows top first) for paint, AO and painted relief."""
    t0 = time.time()
    names = list(parts)
    (ys, xs), tri, bary, tpart, inside = rasterize(parts, size, atlas)
    log.append(f"rasterized {len(tri)} texels ({len(tri) / size ** 2:.0%} of the atlas) in {time.time() - t0:.1f}s")

    def interp(key):
        return np.einsum("nk,nkc->nc", bary, _corners(parts, key)[tri])

    P, Nl, T = interp("pos"), _unit(interp("normal")), interp("tangent")
    sgn = np.sign(interp("sign")[:, 0])
    sgn[sgn == 0] = 1
    T = _unit(T - Nl * (T * Nl).sum(1, keepdims=True))
    B = sgn[:, None] * np.cross(Nl, T)
    part = tpart[tri]

    # project onto the exact surface of the texel's own part
    X, G = P.copy(), Nl.copy()
    t1 = time.time()
    island = uv_islands(parts)[tri]
    for pi, pn in enumerate(names):
        sel = np.flatnonzero(part == pi)
        if not len(sel):
            continue
        vx = ctx["frames"][pn][1]
        x, g = _project(ctx["streams"][pn], X[sel], ys[sel], xs[sel], island[sel], vx)
        # a texel that wandered off (onto the far side of a thin sheet, or out of a thin gap) keeps the low-poly
        # surface. Steep but outward normals (a shingle's butt end, a board's edge) are real detail: keep those.
        bad = (np.linalg.norm(x - P[sel], axis=1) > 6 * vx) | ((_unit(g) * Nl[sel]).sum(1) < -0.2)
        x[bad], g[bad] = P[sel][bad], Nl[sel][bad]
        X[sel], G[sel] = x, _unit(g)
        if bad.any():
            log.append(f"  {pn}: {bad.mean():.2%} of texels kept the low-poly surface (projection went astray)")
    log.append(f"projected onto the exact surface in {time.time() - t1:.1f}s")
    # texels whose ray found no scene mesh (alpha 0) take their nearest baked neighbour
    baked = given["color"][..., 3] > 0.5
    miss = ~baked[ys, xs]
    if miss.any():
        log.append(f"  {miss.mean():.2%} of texels found no scene mesh along their ray: filled from neighbours")
        log.append(f"    {(miss & ~inside).sum() / miss.sum():.0%} of them are edge texels (centre outside its triangle)")
        for pi, pn in enumerate(names):
            m = (miss & inside)[part == pi]
            if m.size and m.mean() > 0.005:
                log.append(f"    {pn}: {m.mean():.1%} of its texels missed inside their triangle")
        given = {k: _dilate(v, baked) for k, v in given.items()}

    c = _corners(parts, "pos")[np.unique(tri)]  # the atlas's triangles: surface per texel
    texel = np.sqrt(np.linalg.norm(np.cross(c[:, 1] - c[:, 0], c[:, 2] - c[:, 0]), axis=1).sum() / 2 / max(len(tri), 1))
    lin = given["color"][ys, xs, :3].astype(np.float64)
    srgb = np.where(lin <= 0.0031308, 12.92 * lin, 1.055 * np.clip(lin, 0, None) ** (1 / 2.4) - 0.055)
    rms = given["rms"][ys, xs].astype(np.float64)
    ch = {"color": srgb, "roughness": rms[:, :1], "metallic": rms[:, 1:2], "specular": rms[:, 2:3]}
    if "height" in given:
        # painted height baked by Cycles (0.5 + h x 25); its slope across the texture tilts the normal: u runs
        # along the tangent, v (up the texture, rows down) along the bitangent, a texel is `texel` metres
        hi = (given["height"][..., 0].astype(np.float64) - 0.5) / 25.0
        if np.abs(hi[ys, xs]).max() > 1e-6:
            hp = np.pad(hi, 1, mode="edge")
            du = (hp[1:-1, 2:] - hp[1:-1, :-2]) / (2 * texel)
            dv = -(hp[2:, 1:-1] - hp[:-2, 1:-1]) / (2 * texel)
            h0 = hi[ys, xs]
            X = X + h0[:, None] * G  # the height map measures to the painted surface
            G = _unit(G - du[ys, xs][:, None] * T - dv[ys, xs][:, None] * B)  # B is signed: +v
            log.append(f"painted height from the scene's bake (texel {texel * 1000:.2f} mm)")

    height = ((X - P) * Nl).sum(1)
    tn = np.stack([(G * T).sum(1), (G * B).sum(1), (G * Nl).sum(1)], -1)
    # a normal map can't point below its surface: detail steeper than 90 deg is bent to the horizon
    tn[:, 2] = np.maximum(tn[:, 2], 0.02)
    tn = _unit(tn)
    filled = np.zeros((size, size), bool)
    filled[ys, xs] = True
    hr = float(max(np.abs(height).max(), 1e-4))
    maps = {}

    def put(name, vals, fill):
        img = np.full((size, size, vals.shape[1]), fill, np.float64)
        img[ys, xs] = vals
        maps[name] = _dilate(img, filled)
    put("basecolor", ch["color"], 0.5)
    put("roughness", ch["roughness"], 0.6)
    put("metallic", ch["metallic"], 0.0)
    put("specular", ch["specular"], 0.5)
    maps["ao"] = _dilate(given["ao"][..., :1].astype(np.float64), filled)
    put("normal", tn * 0.5 + 0.5, 0.5)
    put("height", (height / hr * 0.5 + 0.5)[:, None], 0.5)
    maps["orm"] = np.concatenate([maps["ao"], maps["roughness"], maps["metallic"]], -1)
    return {"maps": maps, "height_range": hr, "coverage": len(tri) / size ** 2}


def scene_maps(name: str, parts: dict, sizes: dict, ctx: dict, resolution: int, log: list) -> dict:
    """The paint and AO maps of every atlas, baked by Cycles from the model's Blender scene (synced first) onto
    the low poly: {atlas: {"color" (linear), "rms", "ao"}}. Each part's rays reach as far as its low poly strays
    from the exact surface."""
    import tempfile
    from . import scene
    t = time.time()
    scene.sync(name, resolution)
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
            np.savez(f, verts=p["verts"], corner_vert=p["corner_vert"], uv=p["uv"], normal=p["normal"])
            pf = next((q for q, dd in ctx["prefabs"].items() if pn in dd["parts"]), None)
            M = ctx["prefabs"][pf]["instances"][ctx["prefabs"][pf]["bake"]].tolist() if pf else None
            jobs.append({"key": pn, "scene_key": ctx.get("split", {}).get(pn, pn), "low": str(f), "atlas": p["atlas"],
                         "extrusion": out_, "ray": out_ + in_, "matrix": M})
        t = time.time()
        out = scene._blender({"mode": "bake_maps", "blend": str(scene.blend_path(name)), "parts": jobs,
                              "atlases": {str(ai): sz for ai, sz in sizes.items()}, "out": tmp, "samples": BAKE_SAMPLES},
                             3 * 3600, progress=getattr(log, "note", None))
        bt = next((line[8:] for line in out.splitlines() if line.startswith("@@times")), "")
        log.append(f"paint and AO maps baked by Cycles from the scene in {time.time() - t:.1f}s ({bt})")
        res = {}
        for ai in sizes:
            with np.load(Path(tmp) / f"atlas{ai}.npz") as z:
                res[ai] = {k: z[k] for k in z.files}
    return res


def write_fbx(glb: Path, fbx: Path) -> None:
    """The GLB as FBX for Unity and Unreal (skeleton, skin, textures embedded): `blender_fbx.py`."""
    r = subprocess.run([render.BLENDER, "-b", "--factory-startup", "--python-exit-code", "1",
                        "--python", str(Path(__file__).with_name("blender_fbx.py")), "--", str(glb), str(fbx)],
                       capture_output=True, text=True, timeout=900)
    if r.returncode or not fbx.exists():
        raise RuntimeError(f"fbx export failed:\n{r.stdout[-2000:]}\n{r.stderr[-2000:]}")


def _png(path: Path, img: np.ndarray, srgb_input: bool = True, bits: int = 8):
    a = np.clip(img, 0, 1)
    if bits == 16:
        Image.fromarray((a[..., 0] * 65535 + 0.5).astype(np.uint16)).save(path)
        return
    a = (a * 255 + 0.5).astype(np.uint8)
    Image.fromarray(a[..., 0] if a.shape[-1] == 1 else a).save(path)


# ---- GLB -------------------------------------------------------------------------------------------------------

_Z_TO_Y = np.array([[1, 0, 0], [0, 0, 1], [0, -1, 0]], np.float64)  # Blender (Z up, faces -Y) -> glTF (Y up, faces +Z)


def _gltf_vertices(p: dict):
    """Split corners into glTF vertices (one per distinct position/uv/normal/tangent) and index them."""
    c = p["corner_vert"]
    rows = np.concatenate([c[:, None].astype(np.float64), p["uv"], p["normal"], p["tangent"], p["sign"][:, None]], 1)
    key = np.round(rows * 1e5).astype(np.int64)
    _, first, inv = np.unique(key, axis=0, return_index=True, return_inverse=True)
    pos = p["verts"][c[first]] @ _Z_TO_Y.T
    nrm = _safe_unit(p["normal"][first].astype(np.float64), [0.0, 0.0, 1.0]) @ _Z_TO_Y.T
    tan = _safe_unit(p["tangent"][first].astype(np.float64), [1.0, 0.0, 0.0]) @ _Z_TO_Y.T
    uv = np.stack([p["uv"][first, 0], 1 - p["uv"][first, 1]], -1)  # glTF uv origin is the top left
    t4 = np.concatenate([tan, p["sign"][first, None]], 1)
    return (pos.astype(np.float32), nrm.astype(np.float32), np.ascontiguousarray(t4, np.float32),
            uv.astype(np.float32), inv.ravel().astype(np.uint32), c[first])


def _safe_unit(v: np.ndarray, fallback) -> np.ndarray:
    """Unit vectors; any zero-length one (glTF requires unit normals and tangents) becomes `fallback`."""
    n = np.linalg.norm(v, axis=1, keepdims=True)
    return np.where(n > 1e-9, v / np.maximum(n, 1e-12), np.asarray(fallback, float))


def _local(p: dict, M: np.ndarray) -> dict:
    """A part baked at its prefab's bake instance (local -> world M, no mirror) in the prefab's own frame."""
    A = np.linalg.inv(M[:3, :3])
    q = dict(p)
    q["verts"] = (p["verts"].astype(np.float64) - M[:3, 3]) @ A.T
    q["normal"], q["tangent"] = p["normal"] @ A.T, p["tangent"] @ A.T  # rotation x uniform scale: renormalised
    return q


def _trs(M: np.ndarray) -> dict:
    """glTF node transform (translation, rotation, scale) of a local -> world matrix in Blender axes."""
    from scipy.spatial.transform import Rotation
    G = _Z_TO_Y @ M[:3, :3] @ _Z_TO_Y.T
    det = float(np.linalg.det(G))
    sc = abs(det) ** (1 / 3)
    D = np.diag([-1.0, 1, 1]) if det < 0 else np.eye(3)  # a mirrored instance: negative x scale
    q = Rotation.from_matrix(G @ D / sc).as_quat()  # x, y, z, w as glTF wants
    return {"translation": (_Z_TO_Y @ M[:3, 3]).tolist(), "rotation": q.tolist(), "scale": (np.diag(D) * sc).tolist()}


def write_glb(path: Path, name: str, parts: dict, atlases: list[tuple[str, dict[str, Path]]],
              prefabs: dict | None = None, looks: dict | None = None, rig: dict | None = None):
    """One mesh per part, one material per atlas: atlases is [(atlas name, {basecolor, orm, normal, specular: png})]
    in atlas index order; each part uses the material of its "atlas" index. A shared prefab (prefabs: {prefab:
    {"bake", "instances": {instance: local -> world}, "parts"}}) is one mesh, a primitive per part in its own
    frame, and a node per instance (extras.prefab names it). looks: {part: {"transmission", "ior", "alpha"}}: such a
    part gets a variant of its atlas's material (same textures) with KHR_materials_transmission + KHR_materials_ior
    (glass) or alpha blending. rig: {"bones": [{"name", "head" (Blender axes), "parent"}], "weights": {part: (bone
    indices (verts, 4), weights (verts, 4))}}: a joint node per bone under a "rig" node (at its head, parents first),
    one skin, and the parts with weights skinned to it (`rig.py`)."""
    bin_ = bytearray()
    views, accessors = [], []

    def add(data: np.ndarray, target, ctype, typ, minmax=False):
        while len(bin_) % 4:
            bin_.append(0)
        views.append({"buffer": 0, "byteOffset": len(bin_), "byteLength": data.nbytes,
                      **({"target": target} if target else {})})
        bin_.extend(data.tobytes())
        acc = {"bufferView": len(views) - 1, "componentType": ctype, "count": len(data), "type": typ}
        if minmax:
            acc["min"], acc["max"] = data.min(0).tolist(), data.max(0).tolist()
        accessors.append(acc)
        return len(accessors) - 1

    # the images go into the buffer first: they are views 0..n-1, and texture i shows image i
    images = [p for _, imgs in atlases for p in imgs.values()]
    for p in images:
        while len(bin_) % 4:
            bin_.append(0)
        raw = Path(p).read_bytes()
        views.append({"buffer": 0, "byteOffset": len(bin_), "byteLength": len(raw)})
        bin_.extend(raw)
    materials, k = [], 0
    for an, imgs in atlases:
        ti = {key: k + i for i, key in enumerate(imgs)}
        k += len(imgs)
        materials.append({
            "name": f"{name}_material" if len(atlases) == 1 else f"{name}_{an}_material",
            "pbrMetallicRoughness": {"baseColorTexture": {"index": ti["basecolor"]},
                                     "metallicRoughnessTexture": {"index": ti["orm"]},
                                     "metallicFactor": 1.0, "roughnessFactor": 1.0},
            "normalTexture": {"index": ti["normal"]},
            "occlusionTexture": {"index": ti["orm"]},
            # specular 0..1 in the texture's alpha; 0.5 = F0 0.04 (dielectric default), as Blender's IOR level
            "extensions": {"KHR_materials_specular": {"specularTexture": {"index": ti["specular"]},
                                                      "specularFactor": 1.0, "specularColorFactor": [2.0, 2.0, 2.0]}},
        })
    used = ["KHR_materials_specular"]
    variants = {}

    def material_of(pn, p):
        ai = int(p.get("atlas", 0))
        lk = (looks or {}).get(pn)
        if not lk:
            return ai
        key = (ai, json.dumps(lk, sort_keys=True))
        if key not in variants:
            m = json.loads(json.dumps(materials[ai]))
            m["name"] = f"{m['name']}_{pn.split('/')[-1].split('~')[0]}"
            if lk.get("transmission"):
                m["extensions"]["KHR_materials_transmission"] = {"transmissionFactor": float(lk["transmission"])}
                m["extensions"]["KHR_materials_ior"] = {"ior": float(lk.get("ior", 1.45))}
                for e in ("KHR_materials_transmission", "KHR_materials_ior"):
                    if e not in used:
                        used.append(e)
            if lk.get("alpha", 1.0) < 1.0:
                m["alphaMode"] = "BLEND"
                m["pbrMetallicRoughness"]["baseColorFactor"] = [1.0, 1.0, 1.0, float(lk["alpha"])]
            m["doubleSided"] = True
            materials.append(m)
            variants[key] = len(materials) - 1
        return variants[key]
    meshes, nodes = [], []

    skinned = (rig or {}).get("weights") or {}
    nb = len((rig or {}).get("bones") or [])

    def primitive(p, pn=None):
        pos, nrm, tan, uv, idx, src = _gltf_vertices(p)
        attrs = {"POSITION": add(pos, 34962, 5126, "VEC3", True), "NORMAL": add(nrm, 34962, 5126, "VEC3"),
                 "TANGENT": add(tan, 34962, 5126, "VEC4"), "TEXCOORD_0": add(uv, 34962, 5126, "VEC2")}
        if pn in skinned:
            J, W = skinned[pn]
            J, W = np.asarray(J)[src], np.asarray(W, np.float32)[src]
            W = W / W.sum(1, keepdims=True)
            J = np.where(W > 0, J, 0)  # unused slots: joint 0 at weight 0
            attrs["JOINTS_0"] = add(np.ascontiguousarray(J, np.uint8 if nb <= 256 else np.uint16), 34962,
                                    5121 if nb <= 256 else 5123, "VEC4")
            attrs["WEIGHTS_0"] = add(np.ascontiguousarray(W, np.float32), 34962, 5126, "VEC4")
        return {"attributes": attrs, "indices": add(idx, 34963, 5125, "SCALAR"), "material": material_of(pn, p)}
    prefabs = prefabs or {}
    in_prefab = {pn for d in prefabs.values() for pn in d["parts"]}
    skins, top = [], []
    if nb:  # the armature: a node per bone at its head, relative to its parent's head; the skin's joints
        bones = rig["bones"]
        base = len(nodes)
        head = np.array([_Z_TO_Y @ np.asarray(b["head"], float) for b in bones])
        for i, b in enumerate(bones):
            ref = head[b["parent"]] if b["parent"] >= 0 else np.zeros(3)
            nodes.append({"name": b["name"], "translation": (head[i] - ref).tolist()})
        for i, b in enumerate(bones):
            if b["parent"] >= 0:
                nodes[base + b["parent"]].setdefault("children", []).append(base + i)
        nodes.append({"name": "rig", "children": [base + i for i, b in enumerate(bones) if b["parent"] < 0]})
        top.append(len(nodes) - 1)
        ibm = np.tile(np.eye(4, dtype=np.float32), (nb, 1, 1))
        ibm[:, :3, 3] = -head  # bind pose: every joint unrotated at its head
        skins.append({"name": f"{name}_rig", "joints": list(range(base, base + nb)), "skeleton": len(nodes) - 1,
                      "inverseBindMatrices": add(np.ascontiguousarray(ibm.transpose(0, 2, 1)).reshape(nb, 16),
                                                 None, 5126, "MAT4")})
    for pn, p in parts.items():
        if pn in in_prefab:
            continue
        meshes.append({"name": pn, "primitives": [primitive(p, pn)]})
        nodes.append({"name": f"{name}_{pn}", "mesh": len(meshes) - 1, **({"skin": 0} if pn in skinned else {})})
        top.append(len(nodes) - 1)
    for pf, d in prefabs.items():
        M0 = d["instances"][d["bake"]]
        meshes.append({"name": pf, "primitives": [primitive(_local(parts[pn], M0), pn) for pn in d["parts"] if pn in parts]})
        for inst, M in d["instances"].items():
            nodes.append({"name": inst, "mesh": len(meshes) - 1, **_trs(M), "extras": {"prefab": pf}})
            top.append(len(nodes) - 1)
    doc = {"asset": {"version": "2.0", "generator": "hifipushie"}, "scene": 0,
           "scenes": [{"nodes": top}], "nodes": nodes, "meshes": meshes, **({"skins": skins} if skins else {}),
           "materials": materials, "textures": [{"source": i, "sampler": 0} for i in range(len(images))],
           "samplers": [{"magFilter": 9729, "minFilter": 9987}],
           "images": [{"bufferView": i, "mimeType": "image/png"} for i in range(len(images))],
           "accessors": accessors, "bufferViews": views, "buffers": [{"byteLength": 0}],
           "extensionsUsed": used}
    while len(bin_) % 4:
        bin_.append(0)
    doc["buffers"][0]["byteLength"] = len(bin_)
    js = json.dumps(doc, separators=(",", ":")).encode()
    js += b" " * ((4 - len(js) % 4) % 4)
    with open(path, "wb") as f:
        f.write(struct.pack("<III", 0x46546C67, 2, 12 + 8 + len(js) + 8 + len(bin_)))
        f.write(struct.pack("<II", len(js), 0x4E4F534A) + js)
        f.write(struct.pack("<II", len(bin_), 0x004E4942) + bytes(bin_))


def texel_sizes(parts: dict, sizes: dict, focus: dict | None = None) -> dict:
    """Per part: surface area, uv area (fraction of its atlas) and the texel size it got (mm per texel) with its
    atlas at sizes[atlas index] texels, plus the texel size inside each of its focus regions ({part: [[x, y, z, r,
    w]]})."""
    out = {}
    for pn, p in parts.items():
        texture = sizes[p["atlas"]]
        c = p["verts"][p["corner_vert"]].reshape(-1, 3, 3).astype(np.float64)
        a3 = np.linalg.norm(np.cross(c[:, 1] - c[:, 0], c[:, 2] - c[:, 0]), axis=1) / 2
        u = p["uv"].reshape(-1, 3, 2).astype(np.float64)
        e1, e2 = u[:, 1] - u[:, 0], u[:, 2] - u[:, 0]
        auv = np.abs(e1[:, 0] * e2[:, 1] - e1[:, 1] * e2[:, 0]) / 2

        def mm(sel):
            return float(1000 * np.sqrt(a3[sel].sum() / max(auv[sel].sum(), 1e-20)) / texture)
        out[pn] = {"area_m2": float(a3.sum()), "uv_fill": float(auv.sum()), "mm_per_texel": mm(slice(None))}
        regions = (focus or {}).get(pn) or []
        if regions:
            cen = c.mean(1)
            out[pn]["focus_mm_per_texel"] = [round(mm(np.linalg.norm(cen - f[:3], axis=1) <= f[3]), 2)
                                             for f in regions]
    return out


def export(name: str, out_dir: Path, triangles: int = 15000, texture: int = 2048, resolution: int = 256,
           atlases: int = 1, texel_density: float | None = None, instancing: bool = True, rig: bool = False,
           fbx: bool = False) -> dict:
    """Build, decimate + unwrap, bake every map, write PNGs, <name>.glb and <name>.json into out_dir.
    Per part (spec["parts"][p]): "triangle_weight" and "texel_density" (relative, default 1) scale its share of
    the triangles and its texels per metre; "atlas" (any name) puts it on an atlas of its own.
    texel_density (texels per metre): atlases are opened as needed to give every part that (x its own weight) at
    most `texture`^2 each, each atlas the smallest power of two that holds its parts. Without it, `atlases` (n)
    atlases of `texture`^2 split the parts by load.
    instancing: prefabs with 2+ instances are one mesh and one set of texels, placed by a node per instance
    (prefabs.<p>.export = "unique" bakes a prefab's instances into the scene instead). `triangles` counts the
    triangles drawn (a prefab's once per instance); the file holds fewer. With instancing every instance is a
    movable asset (a prefab of one instance too), as in the Blender scene. The paint and AO maps are baked by
    Cycles from the model's Blender scene (`scene_maps`; AO is each asset's own, as an engine expects)."""
    log = _Log(name)
    t = time.time()
    spec = store.load(name)
    defs = spec.get("parts") or {}
    out_dir.mkdir(parents=True, exist_ok=True)
    ctx = split(spec, resolution, instancing, log, min_share=1)
    origin = ctx["origin"]
    tm = time.time()
    high = mesh_parts(ctx, out_dir / "high.npz")
    log.append(f"meshed {len(ctx['streams'])} parts in {time.time() - tm:.1f}s (scene voxel {ctx['voxel'] * 1000:.1f} mm)")
    prune_hidden(ctx, high, log)
    if texel_density:
        split_big(high, ctx, {pn: _weight(defs, origin[pn], "texel_density") * texel_density for pn in ctx["streams"]},
                  texture, log)
    areas = part_areas(high)

    def w(pn, key):
        return _weight(defs, origin[pn], key)
    focus = {pn: focus_regions(spec, origin[pn]) for pn in areas}
    rel = {pn: w(pn, "texel_density") * (texel_density or 1.0) for pn in areas}
    loads = texture_loads(high, rel, focus)
    fixed = {pn: str(defs[origin[pn]]["atlas"]) for pn in areas if (defs.get(origin[pn]) or {}).get("atlas") is not None}
    pf_of = {pn: pf for pf, d in ctx["prefabs"].items() for pn in d["parts"]}
    units: dict[str, list] = {}
    for pn in areas:  # a prefab's parts go on one atlas together (one material per instance where possible)
        units.setdefault(pf_of.get(pn, pn), []).append(pn)
    if texel_density:  # say now, not after the bake, which parts can't get the density asked for (a prefab too
        # big for an atlas: scene parts were split above)
        for u, pns in units.items():
            need = sum(loads[pn] for pn in pns)
            cap = texture ** 2 * FILL
            if need > cap:
                got = texel_density * np.sqrt(cap / need)
                area = sum(loads[pn] / rel[pn] ** 2 for pn in pns)
                log.append(f"{u}: {area:.0f} m^2 of surface wants {np.sqrt(need / FILL):.0f}^2 texels at "
                           f"{texel_density:g}/m, more than one {texture}^2 atlas holds: expect ~{got:.0f}/m "
                           f"(split it into parts, raise texture, or give it a lower texel_density)")
    fill = FILL
    for attempt in range(2):
        group = density_groups(units, loads, fixed, texture, fill) if texel_density else atlas_groups(
            loads, fixed, atlases)
        names = sorted(set(group.values()), key=lambda g: (not g.isdigit(), int(g) if g.isdigit() else 0, g))
        sizes = {ai: min(texture, _pow2(np.sqrt(sum(loads[pn] for pn in areas if group[pn] == an) / fill)))
                 if texel_density else texture for ai, an in enumerate(names)}
        cfg = {pn: {"weight": w(pn, "triangle_weight"), "density": w(pn, "texel_density"),
                    "atlas": names.index(group[pn]), "focus": focus[pn], "split": pn in ctx.get("split", {}),
                    "copies": len(ctx["prefabs"][pf_of[pn]]["instances"]) if pn in pf_of else 1} for pn in areas}
        t1 = time.time()
        parts, binfo = lowpoly(high, out_dir / "lowpoly.npz", cfg, triangles, sizes, ctx["voxel"])
        if not texel_density:
            break
        # the size each atlas needs for every part to get its density, now that it's packed
        ts = texel_sizes(parts, sizes)
        need = {ai: max(sizes[ai] * ts[pn]["mm_per_texel"] * rel[pn] / 1000 for pn, p in parts.items()
                        if p["atlas"] == ai) for ai in range(len(names))}
        over = [ai for ai in need if need[ai] > 1.05 * texture and len({pf_of.get(pn, pn) for pn, p in parts.items()
                                                                         if p["atlas"] == ai}) > 1]
        if over and attempt == 0:
            fill = 0.95 * min(sum(ts[pn]["uv_fill"] for pn, p in parts.items() if p["atlas"] == ai) for ai in over)
            log.append(f"atlases {[names[ai] for ai in over]} came out too full for {texel_density:g} texels/m at "
                       f"{texture}: regrouping for a pack fill of {fill:.0%}")
            continue
        sizes = {ai: min(texture, _pow2(0.97 * need[ai])) for ai in need}
        break
    ntri = sum(len(p["corner_vert"]) // 3 for p in parts.values())
    log.append(f"low poly: {ntri} triangles in the file in {time.time() - t1:.1f}s (joint decimation {binfo['joint_s']:.1f}s, "
               f"per-part {binfo['decimate_s'] - binfo['joint_s']:.1f}s, unwrap + pack {binfo['unwrap_s']:.1f}s)")
    tsz = texel_sizes(parts, sizes, {pn: focus[pn] for pn in parts})
    report = {}
    for pn, p in parts.items():
        b = binfo["parts"][pn]
        report[pn] = {"triangles": len(p["corner_vert"]) // 3, "atlas": names[p["atlas"]],
                      "mm_per_texel": round(tsz[pn]["mm_per_texel"], 2), "area_m2": round(tsz[pn]["area_m2"], 3),
                      "islands": b.get("islands"), "joint_decimation_share": b["joint_count"],
                      "mirrored": b["symmetric"], "texel_density": cfg[pn]["density"],
                      "triangle_weight": cfg[pn]["weight"]}
        if pn in pf_of:
            report[pn]["prefab"] = pf_of[pn]
        if "focus_mm_per_texel" in tsz[pn]:
            report[pn]["focus_mm_per_texel"] = tsz[pn]["focus_mm_per_texel"]
    for ai, an in enumerate(names):
        fill_a = sum(tsz[pn]["uv_fill"] for pn, p in parts.items() if p["atlas"] == ai)
        short = ""
        if texel_density:
            got = min(1000 / r["mm_per_texel"] / (rel[pn] / texel_density) for pn, r in report.items()
                      if r["atlas"] == an)
            short = f" (below the {texel_density:g}/m asked: {got:.0f}/m)" if got < 0.9 * texel_density else ""
        log.append(f"atlas {an}: {sizes[ai]}^2, {fill_a:.0%} filled{short}; " + ", ".join(
            f"{pn} {r['triangles']} tris {r['mm_per_texel']:.1f} mm/texel"
            + (f" (focus {', '.join(f'{v:.1f}' for v in r['focus_mm_per_texel'])})" if "focus_mm_per_texel" in r else "")
            for pn, r in report.items() if r["atlas"] == an))
    atlas_files, maps_info, heights, cover = [], {}, {}, {}
    given = scene_maps(name, parts, sizes, ctx, resolution, log)
    for ai, an in enumerate(names):
        stem = name if len(names) == 1 else f"{name}_{an}"
        if len(names) > 1:
            log.append(f"atlas {an}:")
        res = bake(parts, sizes[ai], ctx, log, ai, given[ai])
        maps = res["maps"]
        files = {}
        for key in ("basecolor", "normal", "orm", "roughness", "metallic", "specular", "ao"):
            files[key] = out_dir / f"{stem}_{key}.png"
            _png(files[key], maps[key])
        files["height"] = out_dir / f"{stem}_height.png"
        _png(files["height"], maps["height"], bits=16)
        # glTF reads specular from the alpha channel of its texture
        spec_rgba = out_dir / f"{stem}_specular_gltf.png"
        a = (np.clip(maps["specular"][..., 0], 0, 1) * 255 + 0.5).astype(np.uint8)
        Image.fromarray(np.stack([np.full_like(a, 255)] * 3 + [a], -1), "RGBA").save(spec_rgba)
        atlas_files.append((an, {"basecolor": files["basecolor"], "orm": files["orm"], "normal": files["normal"],
                                 "specular": spec_rgba}))
        maps_info[an] = {k: str(v) for k, v in files.items()}
        heights[an] = res["height_range"]
        cover[an] = res["coverage"]
    glb = out_dir / f"{name}.glb"
    looks = {pn: {k: float(d[k]) for k in ("transmission", "alpha", "ior") if k in d}
             for pn in parts for d in [defs.get(origin[pn]) or {}] if any(k in d for k in ("transmission", "alpha"))}
    rigged = None
    if rig:  # an armature from the skeleton, the parts (not prefabs) skinned to it
        from . import rig as rigmod
        tr = time.time()
        bones = rigmod.rig_bones(spec)
        rigged = {"bones": bones, "weights": {
            pn: rigmod.rig_weights(spec, bones, p["verts"], p["corner_vert"].reshape(-1, 3), smooth=3)
            for pn, p in parts.items() if pn not in pf_of}}
        log.append(f"rig: {len(bones)} bones ({(spec.get('rig') or {}).get('type', 'humanoid')}, root "
                   f"{bones[0]['name']!r}), {len(rigged['weights'])} parts skinned, {time.time() - tr:.1f}s")
    write_glb(glb, name, parts, atlas_files, ctx["prefabs"], looks, rigged)
    if fbx:  # the same asset as FBX, for engines' skinned-mesh import
        tf = time.time()
        write_fbx(glb, glb.with_suffix(".fbx"))
        log.append(f"wrote {glb.with_suffix('.fbx').name} in {time.time() - tf:.1f}s")
    for _, f in atlas_files:
        f["specular"].unlink()
    (out_dir / "lowpoly.npz").unlink()
    high.unlink()
    # where everything ends up: scene parts as they are, a prefab at each of its instances
    placed = [p["verts"] for pn, p in parts.items() if pn not in pf_of]
    prefabs = {}
    for pf, d in ctx["prefabs"].items():
        M0inv = np.linalg.inv(d["instances"][d["bake"]])
        tri = sum(report[pn]["triangles"] for pn in d["parts"] if pn in report)
        texels = sum(tsz[pn]["uv_fill"] * sizes[parts[pn]["atlas"]] ** 2 for pn in d["parts"] if pn in parts)
        for M in d["instances"].values():
            A = M @ M0inv
            placed += [p["verts"] @ A[:3, :3].T + A[:3, 3] for pn, p in parts.items() if pf_of.get(pn) == pf]
        n = len(d["instances"])
        prefabs[pf] = {"instances": {i: _trs(M) for i, M in d["instances"].items()}, "bake_instance": d["bake"],
                       "parts": d["parts"], "triangles": tri, "texels": int(texels)}
        log.append(f"prefab {pf}: {tri} triangles and {texels / 1e6:.2f} Mtexels shown {n} times "
                   f"(unique copies would add {tri * (n - 1)} triangles, {texels * (n - 1) / 1e6:.2f} Mtexels)")
    allv = np.concatenate(placed)
    shown = ntri + sum(d["triangles"] * (len(d["instances"]) - 1) for d in prefabs.values())
    info = {"glb": str(glb), "triangles": ntri, "triangles_placed": shown,
            "bounds_blender": [allv.min(0).tolist(), allv.max(0).tolist()],
            "texture": texture, "texel_density": texel_density, "height_range_m": max(heights.values()),
            "maps": maps_info[names[0]],
            "atlases": {an: {"size": sizes[ai], "maps": maps_info[an], "height_range_m": heights[an],
                             "coverage": round(cover[an], 3),
                             "parts": [pn for pn, r in report.items() if r["atlas"] == an]} for ai, an in enumerate(names)},
            "parts": report, "prefabs": prefabs,
            "conventions": {"up": "+Y (glTF)", "front": "+Z", "units": "metres", "normal_map": "OpenGL (+Y), MikkTSpace",
                            "height": "0.5 = low-poly surface, 0/1 = -/+ height_range_m (per atlas) along the normal",
                            "orm": "R ambient occlusion, G roughness, B metallic",
                            "specular": "0.5 = F0 0.04 (Blender's IOR level)",
                            "materials": "one per atlas, in the order of 'atlases'",
                            "prefabs": "one mesh per prefab (a primitive per part, in the prefab's frame), a node "
                                       "per instance with extras.prefab"},
            "seconds": round(time.time() - t, 1), "log": log}
    (out_dir / f"{name}.json").write_text(json.dumps(info, indent=1))
    return info


def preview(glb: Path, views: list[str], size: int = 512, samples: int = 24, focus=None, zoom: float = 1.0,
            hide: list[str] | None = None) -> Image.Image:
    """Render the exported GLB (as an engine would load it) with Cycles: checks the textures, not the model.
    Views as in look; the GLB is Y up, so the cameras are turned to match. hide: parts left out (the roof and
    walls, to see an interior)."""
    bounds = np.array(json.loads(glb.with_suffix(".json").read_text())["bounds_blender"])
    with tempfile.TemporaryDirectory(prefix="hifipushie-prev-") as tmp:
        frames = render.view_frames(bounds, views, focus, zoom)
        for f in frames:  # Blender's glTF importer converts back to Z up, so the look cameras apply as they are
            f["out"] = str(Path(tmp) / f"{f['name']}.png")
        _blender({"mode": "preview", "glb": str(glb), "views": frames, "size": size, "samples": samples,
                  "hide": list(hide or [])})
        imgs = [Image.open(f["out"]).convert("RGB") for f in frames]
    return render.contact_sheet(imgs, frames)
