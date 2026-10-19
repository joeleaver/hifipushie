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

from . import assemble, render, sdf, store, surface, validated
from .spec import compile_prims

SCRIPT = Path(__file__).with_name("blender_asset.py")


def _blender(job: dict, timeout: float = 600):
    with tempfile.TemporaryDirectory(prefix="hifipushie-asset-") as tmp:
        p = Path(tmp) / "job.json"
        p.write_text(json.dumps(job))
        from . import resources  # killed with the job if its tool call is cancelled
        r = resources.run([render.BLENDER, "-b", "--factory-startup", "--python-exit-code", "1",
                           "--python", str(SCRIPT), "--", str(p)], capture_output=True, text=True, timeout=timeout)
        if r.returncode:
            raise RuntimeError(f"blender failed:\n{r.stdout[-3000:]}\n{r.stderr[-3000:]}")


GAME_SCRIPT = Path(__file__).with_name("blender_game.py")


EML_PARTS = ("eyes", "teeth", "teeth_lower", "tongue", "brows")


def lash_cap(rb: dict, report: dict) -> int | None:
    """Triangles the lashes may take under the role's eyes_mouth_lashes budget: the budget less what the eyes, teeth,
    tongue and brows already take (report). None without that budget."""
    b = (rb.get("parts") or {}).get("eyes_mouth_lashes")
    if not b:
        return None
    return max(0, int(b["default"]) - sum(int(report[pn].get("triangles", 0)) for pn in EML_PARTS if pn in report))


_ROLE_T = {"parts": {"hair_cards": {"default": 25000, "range": [15000, 50000]}, "head": {"default": 10000}},
           "lod0_triangles": {"default": 100000}}


def _selftest_hair_budget():
    """Known answers: 26040 drawn with back faces = 13020 card faces + the cap; over the range max is a FAIL."""
    rep = {"hair": {"triangles": 26040, "cards": True, "back_faces": True, "vertices": 16115,
                    "layers": {"cap": [0, 1040], "layer0": [1040, 25000]}}}
    h = hair_budget(_ROLE_T, rep)
    assert h == {"drawn": 26040, "card_faces": 13540, "vertices": 16115, "default": 25000, "max": 50000}, h
    one = {"hair": {**rep["hair"], "back_faces": False}}
    assert hair_budget(_ROLE_T, one)["card_faces"] == 26040
    assert hair_budget(_ROLE_T, {"body": {"triangles": 5}}) is None


def _selftest_budget_check():
    rep = {"hair": {"triangles": 52000, "cards": True, "back_faces": True, "vertices": 30000,
                    "layers": {"cap": [0, 2000], "layer0": [2000, 50000]}}, "hat": {"triangles": 900}}
    g = budget_check(_ROLE_T, rep, {})
    assert g["parts"]["hair_cards"] == [27000, 25000] and g["fail"] and g["parts"]["accessories"] == [900, None], g
    assert g["total"] == [27900, 100000]
    ok = budget_check(_ROLE_T, {"hair": {**rep["hair"], "triangles": 40000}}, {})
    assert not ok["fail"] and any(ln.startswith("budget: hair_cards drawn 40000") for ln in ok["lines"]), ok


def export_gb(spec: dict, name: str | None = None) -> float:
    """The memory an export declares to resources.heavy: the measured estimate for export_asset, and for a human
    character (a spec with base, skin or hair) at least resources.EXPORT_HUMAN_GB (24 GB: v7e was OOM-killed at less)."""
    from . import resources
    gb = resources.estimate("export_asset", name)
    if any(k in spec for k in ("base", "skin", "hair")):
        gb = max(gb, resources.EXPORT_HUMAN_GB)
    return float(gb)


@validated.known_answer(_selftest_budget_check)
def budget_check(rb: dict, report: dict, spec: dict) -> dict:
    """LOD0 triangles by budget part (budgets.json's parts: head, body, clothing, hair_cards, eyes_mouth_lashes,
    accessories) against the role's defaults: {"parts": {part: [count, budget]}, "total": [count, budget], "lines"}."""
    skin_pn = (spec.get("skin") or {}).get("part", "body")
    have: dict = {}
    for pn, r in report.items():
        n = int(r.get("triangles", 0))
        if pn == skin_pn and r.get("meshes"):
            have["head"] = have.get("head", 0) + int(r["meshes"].get("head", {}).get("triangles", 0))
            have["body"] = have.get("body", 0) + int(r["meshes"].get("body", {}).get("triangles", 0))
            continue
        k = ("body" if pn == skin_pn else "clothing" if r.get("cloth") else "hair_cards" if (r.get("curves") or r.get("cards"))
             else "eyes_mouth_lashes" if (r.get("lashes") or pn in EML_PARTS) else "accessories")
        have[k] = have.get(k, 0) + n
    bp = rb["parts"]
    hair = hair_budget(rb, report)
    if hair:  # the role default counts card FACES (one side): engine-proof back faces reuse the same vertices
        have["hair_cards"] = hair["card_faces"]
    parts = {k: [have.get(k, 0), int(bp[k]["default"]) if k in bp else None] for k in sorted(set(have) | set(bp))}
    tot = [sum(have.values()), int(rb["lod0_triangles"]["default"])]
    lines, fail = [], []
    for k, (n, b) in parts.items():
        over = b is not None and n > b
        lines.append(("WARNING budget: " if over else "budget: ") + f"{k} {n} of {b}" + (" (OVER)" if over else ""))
    if hair:
        ln = (f"hair_cards drawn {hair['drawn']} triangles (back faces included) of the role's range max {hair['max']}; "
              f"card faces {hair['card_faces']} of {hair['default']}; vertices {hair['vertices']}")
        if hair["max"] is not None and hair["drawn"] > hair["max"]:
            fail.append(ln)
            lines.append("FAIL budget: " + ln)
        else:
            lines.append("budget: " + ln)
    lines.append(("WARNING budget: " if tot[0] > tot[1] else "budget: ") + f"total {tot[0]} of {tot[1]} (LOD0)")
    return {"parts": parts, "total": tot, "lines": lines, "hair": hair, "fail": fail}


@validated.known_answer(_selftest_hair_budget)
def hair_budget(rb: dict, report: dict) -> dict | None:
    """(hair-budget rule, coordinator 2026-10-19; codified) LOD0 hair cards against the role: card FACES (one side)
    against budgets.json's hair_cards default; DRAWN triangles (the index count, engine-proof back faces included)
    against the role's range MAX (hero 50k, main_npc 20k, secondary_npc 8k, crowd 1.5k), a hard limit; vertices
    reported. Counting back faces against the default halved Tess's cards and lowered her crown (round 39). None
    without card hair in the report."""
    rows = [r for r in report.values() if r.get("cards")]
    if not rows:
        return None
    drawn = sum(int(r.get("triangles", 0)) for r in rows)
    back = sum(sum(int(v[1]) for k, v in (r.get("layers") or {}).items() if k != "cap") // 2
               for r in rows if r.get("back_faces"))
    b = (rb.get("parts") or {}).get("hair_cards") or {}
    rng = b.get("range") or [None, None]
    return {"drawn": drawn, "card_faces": drawn - back, "vertices": sum(int(r.get("vertices", 0)) for r in rows),
            "default": int(b["default"]) if "default" in b else None, "max": int(rng[1]) if rng[1] is not None else None}


def game(glb: Path, timeout: float = 900, **job) -> str:
    """The game-like EEVEE render of an exported GLB (blender_game.py): job keys frames / poses / size / hide
    (asset.preview) or shots / anim / out (the engine-stage checks). Returns Blender's log."""
    with tempfile.TemporaryDirectory(prefix="hifipushie-game-") as tmp:
        p = Path(tmp) / "job.json"
        p.write_text(json.dumps({"glb": str(glb), **{k: v for k, v in job.items() if v is not None}}))
        from . import resources
        r = resources.run([render.BLENDER, "-b", *render._threads(), "--factory-startup", "--python-exit-code", "1",
                           "--python", str(GAME_SCRIPT), "--", str(p)], capture_output=True, text=True, timeout=timeout)
        if r.returncode:
            raise RuntimeError(f"blender failed:\n{r.stdout[-3000:]}\n{r.stderr[-3000:]}")
        return r.stdout


def margin_px(texture: int) -> int:
    """Gap between UV islands in texels: enough for bilinear filtering and the first mips (dilation fills it)."""
    return max(2, texture // 512)


def min_part(triangles: int) -> int:
    """No part gets fewer triangles than this (or all it has): eyes, teeth, pots stay round."""
    return max(300, triangles // 100)


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


EYES_AO_OFF = True  # (r23: the export's sclera AO read mean 0.38, CoV 0.77, p5 0.02 in the rest pose's lid shadow: the
# "blotchy sclera" in engine renders, absent from the scene's gate render; real-time eyes take their occlusion from
# the lids as they stand, not a baked map) the base's eyes part gets AO 1
DECAL_MAX = 2000.0  # texels per metre a decal asks for at most (0.5 mm: small print stays readable)
DECAL_GAIN = 16.0  # and at most this many times its part's own density


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
            want = min(DECAL_MAX, fr["px"][0] / fr["w"], fr["px"][1] / fr["h"])
            k = float(np.clip(want / max(base, 1e-9), 1.0, DECAL_GAIN))
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


SEAM_LIMIT = 1.5  # seam_steps excess over which the export warns (texture space; ~1 = invisible)
BAKE_SS = 2  # Cycles bakes BAKE_SS^2 points per texel, box-filtered (one point per texel aliased sharp paint)
BAKE_PREFILTER = True  # (s14) paint images finer than the bake's sample spacing are box-downsampled first (a mip level):
# Cycles point-samples image textures, so Garrett's 0.06 mm stubble hairs under 0.2 mm bake samples came out as sparse
# texel-sized black / white specks (the stage's EEVEE mipmaps them into a soft shadow). False = the old point sampling.
BAKE_SS_PX = 8192  # ... while the supersampled image's side stays within this
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


def split(spec: dict, resolution: int, instancing: bool, log: list, min_share: int = 2,
          voxels: dict | None = None) -> dict:
    """What gets meshed and baked: the model's parts, minus the instances of shared prefabs, plus one copy of each
    shared prefab's parts (named "<prefab>/<part>") taken from its bake instance (the first unmirrored one).
    A prefab is shared when it has `min_share`+ instances (the scene uses 1: every instance is a movable object),
    unless prefabs.<p>.export is "unique" (then its instances are
    baked into the scene like any element). Returns {"streams": {export part: prims}, "origin": {export part:
    model part}, "frames": {export part: (lo, voxel, shape)}, "voxel": scene voxel, "full": {model part: prims}
    (the whole model: AO, sky and paint context), "prefabs": {prefab: {"bake": instance, "instances": {instance:
    local -> world 4x4}, "parts": [export parts]}}}. voxels: {part: voxel} at most (face shapes: the lips' slit)."""
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
            from . import scene as scenemod
            pv, _ = scenemod.part_voxel(ps, voxel)
            if (voxels or {}).get(key):
                pv = min(pv, float(voxels[key]))
            # a part finer than the model's voxel (a shirt collar's 6 mm sheet, a strap) on its own grid, as the
            # scene meshes it: at the model's 7.8 mm the collar came out as shreds
            frames[key] = (lo, voxel, shape) if pv >= voxel else scenemod._frame(ps, pv)
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
            "prefabs": {pf: d for pf, d in shared.items() if d["parts"]}, "defs": spec.get("parts") or {}}


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


def topology_parts(spec: dict, ctx: dict, out_dir: Path, log: list) -> dict:
    """Parts with a modelled topology instead of a decimation: parts.<p>.topology = "wrap" (the body of a humanoid:
    retopo.wrap, the template's quads carried onto it; a base's grafted head keeps its own), its faces buried in
    other parts (skin under clothes, where animation would only poke it through) dropped. {part: npz path}."""
    import hashlib
    defs = spec.get("parts") or {}
    out = {}
    for pn in ctx["streams"]:
        if (defs.get(ctx["origin"][pn]) or {}).get("topology") not in ("wrap", "template"):
            continue
        if ctx["origin"][pn] != "body":
            raise ValueError(f"parts.{pn}.topology = \"wrap\": only the body (a humanoid's) can be wrapped")
        from . import retopo
        tl = []
        r = retopo.wrap(spec, log=tl)
        V, L, S = r["verts"], r["loops"], r["sizes"]
        names = list(ctx["streams"])
        hid = surface.hidden(ctx["streams"], V, np.full(len(V), names.index(pn)), names, ctx["voxel"],
                             ctx.get("apart")) > 0.5
        hid = _deep_hidden(np.asarray(V, np.float64), hid, np.zeros(len(V), int))
        if r.get("gnm") is not None:  # (one mesh) GNM's head is all kept: its lids' insides lie in the eyeballs and
            # its mouth round the teeth, and a blink or a jaw drags them out (dropped, the left lid's margin was a row
            # of spikes with the eyeball showing through: the eyes look a little apart, so one side lost more)
            hid &= np.asarray(r["gnm"]) < 0
        st = np.r_[0, np.cumsum(S)[:-1]]
        faces = [L[a:a + k] for a, k in zip(st, S)]
        kept = [f for f in faces if not hid[f].all()]
        used = np.unique(np.concatenate(kept))
        rm = np.full(len(V), -1)
        rm[used] = np.arange(len(used))
        Vk, Lk, Sk = V[used], rm[np.concatenate(kept)], np.array([len(f) for f in kept])
        gk = np.asarray(r["gnm"])[used] if r.get("gnm") is not None else None
        if (defs.get(ctx["origin"][pn]) or {}).get("joint_density", True) and spec.get("rig", {}) is not False:
            # the same triangles spent where it bends: hinge zones split, shafts thinned (topodensity.py)
            from . import rig as _rig
            from . import topodensity
            try:
                Vk, Lk, Sk, gk = topodensity.rebalance(_rig.rig_bones(spec), Vk, Lk, Sk, gk, ctx["streams"][pn],
                                                       ctx["voxel"], log)
            except Exception as e:  # (the plain wrap is still a body)
                log.append(f"WARNING body density: not rebalanced ({type(e).__name__}: {e})")
        path = out_dir / f"topology_{pn}.npz"
        extra = {"gnm": gk} if gk is not None else {}  # (one mesh: GNM vertex ids,
        # face shapes go by index)
        np.savez(path, verts=Vk, loops=Lk, sizes=Sk, **extra)
        out[pn] = (str(path), hashlib.sha1(Vk.tobytes() + Lk.tobytes()).hexdigest()[:12])
        log.append(f"{pn}: wrapped topology, {len(Sk)} faces ({(Sk == 4).mean():.0%} quads, "
                   f"{int((Sk - 2).sum())} triangles), {len(faces) - len(kept)} faces under other parts dropped; "
                   + "; ".join(x for x in tl if x.startswith(("wrapped", "head"))))
    return out


HIDDEN_RIM = 0.012  # m: buried skin and cloth is kept this far in from what shows
OWN_SURFACE = 0.0012  # m: a GNM mouth part's meshed vertex this near GNM's own (subdivided) vertices is its surface


UNDER_CLOTH_REACH = 0.06  # m: skin with a garment this close along its normal is covered
UNDER_CLOTH_TUBE = 0.012  # m: ... within this radius of the normal's line (the sim mesh is ~1 cm)
UNDER_CLOTH_RIM = 0.04  # m: covered skin this close to uncovered skin stays (a sleeve's cuff, a collar, a hem
# lifting in a pose: what the opening shows)


LOD_PUSH_WORN = True  # (r54) ... and the parts worn under them (socks, the body), where they were under at LOD0
LOD_PUSH_WORN_MIN = 20  # LOD0 vertices under a garment for a part to count as worn under it
LOD_PUSH_WORN_NOT_OVER = True  # (r55) see the mask in export
LOD_PUSH_WORN_SHARE = 0.85  # (r55) ... and at least this share of its vertices with a garment in reach UNDER it (the
# rest have the garment poking through them): worn under, not over. rc2d LOD0: socks 0.99, body 0.89, shoes 1.00 (the
# collar under the jeans' hem: 46 vertices, those move); worn over: badge 0.49, lanyard 0.48, clip 0.58, laces 0.67,
# badge_card 0.83 (the margin is thin there: a flat card's back faces see the coat)
LOD_PUSH_WORN_SKIP = ("head", "eyes", "teeth", "teeth_lower", "tongue")  # (the head's meshes: its neck seam ring meets
# the body's; the body's side of it is under the collar at most)
LOD0_PUSH_UNDER = True  # (r57) the garments' under layers are put under their covers at LOD0 too
LOD0_UNDER_GAP = 0.0015  # m: ... this far under (cloth.PUSH_UNDER_GAP); the LODs use lods.LOD_UNDER_GAP
LOD_PUSH_UNDER = True  # (r53) each LOD puts the under garments back under their decimated covers (lods.push_under_layers)


def under_cloth_keep(p: dict, cloth: list[dict]) -> np.ndarray:
    """Per triangle of an export part (the skin): False where all three corners are covered by a garment (one of
    `cloth`'s export parts lies within UNDER_CLOTH_REACH along the vertex normal, inside a UNDER_CLOTH_TUBE line) and
    no uncovered vertex is within UNDER_CLOTH_RIM: the skin under clothes, which games leave out (never seen; in a pose
    it pokes through the cloth)."""
    from scipy.spatial import cKDTree
    V = np.asarray(p["verts"], np.float64)
    cv = np.asarray(p["corner_vert"], np.int64)
    N = np.zeros_like(V)
    np.add.at(N, cv, np.asarray(p["normal"], np.float64))
    N /= np.maximum(np.linalg.norm(N, axis=1, keepdims=True), 1e-12)
    tris = []
    for c in cloth:
        Vc = np.asarray(c["verts"], np.float64)
        tris.append(Vc[np.asarray(c["corner_vert"], np.int64).reshape(-1, 3)])
    T = np.concatenate(tris)  # (m, 3, 3)
    A, E1, E2 = T[:, 0], T[:, 1] - T[:, 0], T[:, 2] - T[:, 0]
    cen = T.mean(1)
    rad = np.linalg.norm(T - cen[:, None], axis=2).max()
    tree = cKDTree(cen)
    used = np.unique(cv)
    covered = np.zeros(len(V), bool)
    for s in range(0, len(used), 20000):
        ids = used[s:s + 20000]
        for i, nb in zip(ids, tree.query_ball_point(V[ids], UNDER_CLOTH_REACH + rad)):
            if not nb:
                continue
            nb = np.asarray(nb)
            d = N[i]  # Moller-Trumbore: the ray from the vertex along its normal against the nearby cloth triangles
            pv = np.cross(d, E2[nb])
            det = (E1[nb] * pv).sum(1)
            ok = np.abs(det) > 1e-12
            inv = np.where(ok, 1.0 / np.where(ok, det, 1.0), 0.0)
            tv = V[i] - A[nb]
            u = (tv * pv).sum(1) * inv
            qv = np.cross(tv, E1[nb])
            v = (qv @ d) * inv
            t = (E2[nb] * qv).sum(1) * inv
            eps = 1e-4  # (a ray through a shared edge or vertex hits)
            hit = ok & (u >= -eps) & (v >= -eps) & (u + v <= 1 + eps) & (t > -0.002) & (t < UNDER_CLOTH_REACH)
            covered[i] = bool(hit.any())
    open_ = used[~covered[used]]
    if len(open_):
        near = cKDTree(V[open_]).query(V[used], distance_upper_bound=UNDER_CLOTH_RIM)[0] < UNDER_CLOTH_RIM
        covered[used[near]] = False
    return ~covered[cv.reshape(-1, 3)].all(1)


LOD_SKIN_CULL_FROM = 1  # (Garrett s14) from this LOD on the skin too drops its faces deep under the garments at LOD0
# (lods.cull_covered), keeping every face a clip frame of cull_poses uncovers; None = the skin is never culled per LOD


def skin_pose_exposed(p: dict, P0: np.ndarray, covers: list[dict], name: str, cover_names: list[str], poses) -> np.ndarray:
    """(Garrett s14) per LOD0 point P0 (lods.under_at_lod0's, vertices of p): True where a triangle using that vertex is
    uncovered (under_cloth_keep, its rim included) in any frame of the `poses` dumps; all False without poses."""
    from scipy.spatial import cKDTree
    out = np.zeros(len(P0), bool)
    if not poses or not len(P0):
        return out
    nt = len(p["corner_vert"]) // 3
    k, _ = cull_exposed_keep(p, covers, name, cover_names, poses, np.zeros(nt, bool))
    if not k.any():
        return out
    vid = np.unique(np.asarray(p["corner_vert"], np.int64).reshape(-1, 3)[k])
    d, nn = cKDTree(np.asarray(p["verts"], np.float64)[vid]).query(np.asarray(P0, np.float64))
    return d < 1e-6


CLOTH_UNDER_CULL = True  # (r53) asset.export's cull_under_cloth also drops an under garment's faces its covers hide


def _over_chain(over: dict, g: str) -> list:
    """The garments under `g` by its chain of "over" (coat -> sweater -> jeans)."""
    out, x = [], over.get(g)
    while x is not None and x not in out and x != g:
        out.append(x)
        x = over.get(x)
    return out


def cloth_under_keep(p: dict, covers: list[dict]) -> np.ndarray:
    """under_cloth_keep for a garment part under other garments. A two-sided garment (p["shell"]: outer triangles, then
    their inner twins, then made pieces / buttons) is tested on its OUTER shell only (the inner shell's vertices face in:
    as "uncovered" vertices they would have kept every rim); each inner triangle goes with its outer twin, the rest stay."""
    nt = len(p["corner_vert"]) // 3
    if not p.get("shell"):
        return under_cloth_keep(p, covers)
    n = int(p["shell"]["outer"])
    po = {"verts": p["verts"], "corner_vert": np.asarray(p["corner_vert"])[:3 * n],
          "normal": np.asarray(p["normal"])[:3 * n]}
    ko = under_cloth_keep(po, covers)
    return np.r_[ko, ko, np.ones(nt - 2 * n, bool)]


def _posed(p: dict, rest: np.ndarray, posed: np.ndarray) -> dict:
    """p with its vertices moved as a dump's mesh moved (each vertex takes its nearest rest vertex's posed position) and
    per-corner normals from the posed triangles' winding."""
    from scipy.spatial import cKDTree
    V = np.asarray(p["verts"], np.float64)
    d, nn = cKDTree(rest).query(V)
    P = np.where((d < 0.002)[:, None], posed[nn], 1e3)  # (a vertex the dump lacks goes far away: never "covered")
    cv = np.asarray(p["corner_vert"], np.int64)
    T = cv.reshape(-1, 3)
    fn = np.cross(P[T[:, 1]] - P[T[:, 0]], P[T[:, 2]] - P[T[:, 0]])
    fn /= np.maximum(np.linalg.norm(fn, axis=1, keepdims=True), 1e-12)
    q = {**p, "verts": P, "normal": np.repeat(fn, 3, axis=0)}
    if p.get("shell"):  # (two-sided: the inner shell's corners keep the winding's own normal, unused by the test)
        q["shell"] = p["shell"]
    return q


def cull_exposed_keep(p: dict, covers: list[dict], name: str, cover_names: list[str], poses, keep: np.ndarray):
    """(r54) The garment-under-garment cull (cloth_under_keep at rest) checked over posed frames: `poses` = npz dumps
    (blender_game shot "dump": "<mesh>:rest" / "<mesh>:posed" per mesh, the clip's frame with skinning, twist, shapes;
    or a glob / list of them) of an export WITHOUT the garment cull. In every frame the under garment and its covers
    are posed (nearest rest vertex) and tested again; a triangle uncovered in any frame is kept. Returns (keep, report)."""
    import glob as glob_
    files = sorted(glob_.glob(poses)) if isinstance(poses, str) else list(poses)
    k = np.asarray(keep, bool).copy()
    rep = {"frames": 0, "restored": 0, "worst": None}
    worst = 0
    for f in files:
        z = np.load(f) if isinstance(f, (str, Path)) else f
        if f"{name}:rest" not in z or not all(f"{c}:rest" in z for c in cover_names):
            continue
        pp = _posed(p, z[f"{name}:rest"], z[f"{name}:posed"])
        cp = [_posed(c, z[f"{cn}:rest"], z[f"{cn}:posed"]) for c, cn in zip(covers, cover_names)]
        kf = cloth_under_keep(pp, cp)
        new = kf & ~k
        rep["frames"] += 1
        if new.sum() > worst:
            worst, rep["worst"] = int(new.sum()), Path(str(f)).stem if isinstance(f, (str, Path)) else str(rep["frames"])
        k |= kf
    rep["restored"] = int(k.sum() - np.asarray(keep, bool).sum())
    return k, rep


def cull_tris(p: dict, keep: np.ndarray) -> dict:
    """p without the triangles `keep` is False for (per-corner arrays cut; vertices, weights, shapes kept), its shell
    layout (outer, inner twins) recounted."""
    cm = np.repeat(keep, 3)
    q = dict(p)
    for k_ in ("corner_vert", "uv", "normal", "tangent", "sign"):
        if q.get(k_) is not None:
            q[k_] = np.asarray(q[k_])[cm]
    if p.get("shell"):
        n = int(p["shell"]["outer"])
        q["shell"] = dict(p["shell"], outer=int(keep[:n].sum()))
    return q


def garment_cull_masks(parts: dict, layer_stack: dict, garments: list) -> dict:
    """(Garrett s10) {under garment: (its LOD0 outward points, whether each is under its covers there, the covers)} for
    cull_under_garments (lods.under_at_lod0 against the garments over it in layer_stack)."""
    from . import lods as lodmod
    out = {}
    if not lodmod.LOD_UNDER_CULL_GARMENTS_FROM:
        return out
    for un_, ovs_ in (layer_stack or {}).items():
        cov_ = [parts[o] for o in ovs_ if o in parts]
        if un_ in garments and un_ in parts and cov_:
            P0_, un0_ = lodmod.under_at_lod0(parts[un_], cov_)
            if un0_.any():
                out[un_] = (P0_, un0_, [o for o in ovs_ if o in parts])
    return out


def cull_under_garments(lp: dict, masks: dict, k: int, log: list, rep_l: dict) -> None:
    """(Garrett s10) at LOD k >= lods.LOD_UNDER_CULL_GARMENTS_FROM, each under garment in `lp` (this LOD's parts) drops
    the faces that were deep under its covers at LOD0 (lods.cull_covered: beyond LOD_UNDER_CULL_RIM from what showed).
    v7's LOD1 right forearm: the decimated sleeve dips more than the push-under cap under the shirt, a white shard."""
    from . import lods as lodmod
    if not lodmod.LOD_UNDER_CULL_GARMENTS_FROM or k < lodmod.LOD_UNDER_CULL_GARMENTS_FROM:
        return
    for pn, (P0_, un0_, ovs_) in masks.items():
        if pn not in lp:
            continue
        kc_ = lodmod.cull_covered(lp[pn], P0_, un0_)
        if not kc_.all():  # only faces that touch the cover at this LOD (a corner less than LOD_UNDER_GAP under it, or
            # through): the rest still sit under it, and a seated pose that lifts a cover (the jacket's skirt off the
            # trousers) must not open a hole the LOD0 cull (posed) kept closed
            covs_ = [lp[o] for o in ovs_ if o in lp]  # this LOD's (decimated) covers
            vid_, _, _, t_ = lodmod.under_depth(lp[pn], covs_)
            near_ = np.zeros(len(lp[pn]["verts"]), bool)
            near_[vid_] = np.isfinite(t_) & (t_ < lodmod.LOD_UNDER_GAP)
            T_ = np.asarray(lp[pn]["corner_vert"], np.int64).reshape(-1, 3)
            kc_ |= ~near_[T_].any(1)
        if not kc_.all():
            lp[pn] = cull_tris(lp[pn], kc_)
            rep_l.setdefault(pn, {})["covered_culled"] = int((~kc_).sum())
            rep_l[pn]["triangles"] = len(lp[pn]["corner_vert"]) // 3
            log.append(f"LOD{k}: {pn}: {int((~kc_).sum())} of {len(kc_)} triangles deep under its covers at LOD0 dropped "
                       f"(lods.cull_covered, {lodmod.LOD_UNDER_CULL_RIM * 1000:.0f} mm rim)")


def _deep_hidden(V: np.ndarray, hidden: np.ndarray, part: np.ndarray, rim: float = HIDDEN_RIM) -> np.ndarray:
    """Hidden vertices with no visible vertex of their own part within `rim`. Faces were dropped right where a part
    goes under another, so the cut ran along every hem, cuff and neckline as a ragged edge one triangle deep (the
    golfer's shirt hem: a solid shell whose inside was cut away exactly at its rounded rim, wavy at rest and
    shedding shards over a lifted thigh). The cut now lies `rim` inside, where nothing looks."""
    from scipy.spatial import cKDTree
    deep = np.asarray(hidden, bool).copy()
    for pi in np.unique(part):
        m = part == pi
        vis = m & ~deep
        hid = np.flatnonzero(m & deep)
        if vis.any() and len(hid):
            d, _ = cKDTree(V[vis]).query(V[hid], distance_upper_bound=rim)
            deep[hid[np.isfinite(d)]] = False
    return deep


def own_mouth_meshes(mesh: Path, mp: dict, log: list) -> None:
    """GNM's tooth rows and tongue as their OWN quads (triangulated) in place of the parts' field meshes in the high mesh: the
    field (IMLS shell, 0.4 mm) decimated to 1200 triangles a row read "jagged, separate pegs with gaps, fang tips"
    (expr_r4 / r5) where GNM's 1414 quads are clean teeth. The parts' min_triangles (base.MOUTH_PARTS) keep them whole.
    Normals: area-weighted from the quads, turned so the front of the row faces forward."""
    from . import base as basemod
    z = dict(np.load(mesh))
    names = [str(n) for n in z["part_names"]]
    V, F, N, P = z["verts"].astype(np.float64), z["faces"], z["normals"].astype(np.float64), z["part"]
    for gn, pn in (("teeth_upper", basemod.TEETH_PARTS[0]), ("teeth_lower", basemod.TEETH_PARTS[1]), ("tongue", "tongue")):
        if pn not in names:
            continue
        i = names.index(pn)
        Vg = np.asarray(mp[gn]["verts"], np.float64)
        Q = np.asarray(mp[gn]["faces"])
        T = np.concatenate([Q[:, [0, 1, 2]], Q[:, [0, 2, 3]]])
        c = Vg[T]
        fn = np.cross(c[:, 1] - c[:, 0], c[:, 2] - c[:, 0])
        Ng = np.zeros_like(Vg)
        for k in range(3):
            np.add.at(Ng, T[:, k], fn)
        Ng /= np.maximum(np.linalg.norm(Ng, axis=1, keepdims=True), 1e-12)
        front = Vg[:, 1] < np.percentile(Vg[:, 1], 15)  # (Blender axes: the face looks toward -y; the tongue's tip)
        if (Ng[front, 1] > 0).mean() > 0.5:
            T, Ng = T[:, [0, 2, 1]], -Ng
        keepv = P != i
        remap = np.cumsum(keepv) - 1
        keepf = keepv[F].all(1)
        F = remap[F[keepf]]
        V, N, P = V[keepv], N[keepv], P[keepv]
        F = np.concatenate([F, T + len(V)])
        V, N = np.concatenate([V, Vg]), np.concatenate([N, Ng])
        P = np.concatenate([P, np.full(len(Vg), i, P.dtype)])
        log.append(f"{pn}: GNM's own {gn} quads as its mesh ({len(T)} triangles), not the field's")
    z.update(verts=V.astype(z["verts"].dtype), faces=F.astype(z["faces"].dtype), normals=N.astype(z["normals"].dtype), part=P)
    np.savez(mesh, **z)


def _hide_covered(ctx: dict, z: dict, names: list, hidden: np.ndarray, log: list) -> None:
    """spec parts.<p>.hides (hides.py) on the high mesh, in place on `hidden`: the hidden part's faces its covers
    enclose go (poke-through islands too), and a cover's faces buried only in the hidden part come back where that
    part is now gone (a shoe's inside under toes it hides would leave a see-through hole)."""
    from scipy.spatial import cKDTree
    from . import hides as hidesmod
    rules = hidesmod.rules(ctx.get("defs") or {})
    if not rules:
        return
    origin = ctx["origin"]
    by_part = {k: ps for k, ps in ctx["streams"].items() if origin.get(k, k) == k}
    V = z["verts"].astype(np.float64)
    for i, nm in enumerate(names):
        rule = rules.get(origin.get(nm, nm))
        cov = hidesmod.covers(rule, by_part) if rule else []
        if not cov:
            continue
        sel = np.flatnonzero(z["part"] == i)
        fsel = z["faces"][z["part"][z["faces"][:, 0]] == i]
        loc = np.full(len(V), -1, np.int64)
        loc[sel] = np.arange(len(sel))
        hid = hidesmod.covered(V[sel], loc[fsel], cov, rule["margin"], rule["reach"], rule["rim"])
        hidden[sel] |= hid
        log.append(f"{nm}: {int(hid.sum())} vertices hidden under {', '.join(rule['covers'])}")
        if not hid.any():
            continue
        tree = cKDTree(V[sel])
        for c in rule["covers"]:
            if c not in names:
                continue
            cs = np.flatnonzero((z["part"] == names.index(c)) & hidden)
            if not len(cs):
                continue
            inB = sdf.field_at(ctx["streams"][nm], V[cs]) < -0.5 * ctx["voxel"]
            gone = hid[tree.query(V[cs])[1]]
            others = {k: q for k, q in ctx["streams"].items() if k != nm}
            still = surface.hidden(others, V[cs], np.zeros(len(cs), int), [c], ctx["voxel"]) > 0.5
            back = inB & gone & ~still
            hidden[cs[back]] = False
            if back.any():
                log.append(f"{c}: {int(back.sum())} vertices inside {nm} kept (that part is hidden there)")


def hide_export_part(ctx: dict, pn: str, p: dict, log: list) -> int:
    """spec parts.<p>.hides on a finished export part (its corner arrays, after decimation or a template wrap):
    triangles whose corners the covers enclose are culled. Returns how many were dropped."""
    from . import hides as hidesmod
    rule = hidesmod.rules(ctx.get("defs") or {}).get(ctx["origin"].get(pn, pn))
    by_part = {k: ps for k, ps in ctx["streams"].items() if ctx["origin"].get(k, k) == k}
    cov = hidesmod.covers(rule, by_part) if rule else []
    if not cov:
        return 0
    cv = np.asarray(p["corner_vert"], np.int64)
    keep = hidesmod.keep_faces(np.asarray(p["verts"], np.float64), cv.reshape(-1, 3), cov, rule)
    if keep.all():
        return 0
    cm = np.repeat(keep, 3)
    for k_ in ("corner_vert", "uv", "normal", "tangent", "sign"):
        if k_ in p:
            p[k_] = np.asarray(p[k_])[cm]
    n = int((~keep).sum())
    log.append(f"{pn}: {n} of {len(keep)} triangles under {', '.join(rule['covers'])} culled (parts hides)")
    return n


def prune_hidden(ctx: dict, mesh: Path, log: list, own_surface: dict | None = None) -> Path:
    """Drop faces buried inside another part (skin under solid clothing shells, the back of an eyeball in its
    socket, tooth roots, a chair's feet in the floor): nobody sees them, and they'd take triangles and atlas space.
    own_surface {part: (n, 3) points}: parts that are hidden only in the neutral (GNM's own teeth and tongue behind
    closed lips: a jaw shape brings them out): of those, the faces ON these points (the piece's own outer surface)
    are kept and the rest (the inside of its shell) dropped, whatever covers them."""
    z = dict(np.load(mesh))
    names = [str(n) for n in z["part_names"]]
    hidden = surface.hidden(ctx["streams"], z["verts"].astype(np.float64), z["part"], names, ctx["voxel"],
                            ctx.get("apart")) > 0.5
    hidden = _deep_hidden(z["verts"].astype(np.float64), hidden, z["part"])
    _hide_covered(ctx, z, names, hidden, log)
    for pn, pts in (own_surface or {}).items():
        from scipy.spatial import cKDTree
        for i, nm in enumerate(names):
            if ctx["origin"].get(nm, nm) == pn or nm == pn:
                m = z["part"] == i
                hidden[m] = cKDTree(pts).query(z["verts"][m].astype(np.float64))[0] > OWN_SURFACE
    faces = z["faces"]
    keep = ~hidden[faces].all(1)
    dropped = {pn: int((~keep & (z["part"][faces[:, 0]] == i)).sum()) for i, pn in enumerate(names)}
    log.append("hidden faces dropped: " + ", ".join(f"{k} {v}" for k, v in dropped.items() if v) if any(
        dropped.values()) else "no hidden faces")
    z["faces"] = faces[keep]
    np.savez(mesh, **z)
    return mesh


def rasterize(parts: dict, size: int, atlas: int | None = None, ring: int = 0):
    """Which triangle covers each texel and where: (texel rows and columns, triangle id, barycentrics, part index
    of every triangle, inside, drawn). Triangle ids and part indices count over all parts in order; only the parts on
    `atlas` (None: all) are drawn. Texel (x, y) of the PNG (row 0 at the top) is uv ((x + .5) / size, 1 - (y + .5)
    / size). inside: the texel's centre lies in its triangle. ring > 0: texels whose centre lies outside (PIL's edge
    texels, plus every texel up to `ring` (+ the diagonal) texels past an island's edge, appended after the drawn ones, with their
    nearest drawn texel's triangle) get the triangle's barycentrics extrapolated: the surface carried on past the
    chart's edge, as the chart across the seam has it (a texel copied from its nearest neighbour put a sharp edge
    a fraction of a texel off on each side of a seam). Without ring they are clamped onto the triangle."""
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
    if ring > 0:
        from scipy import ndimage
        dist, (iy, ix) = ndimage.distance_transform_edt(tid < 0, return_indices=True)
        ry, rx = np.nonzero((tid < 0) & (dist <= ring + 0.5))
        t = np.concatenate([t, tid[iy[ry, rx], ix[ry, rx]]])
        ys, xs = np.concatenate([ys, ry]), np.concatenate([xs, rx])
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
    if ring > 0:  # extrapolated, unless the uv triangle is too thin for its plane to say where (a sliver)
        span = np.maximum.reduce([np.linalg.norm(v0, axis=1), np.linalg.norm(v1, axis=1),
                                  np.linalg.norm(c - b, axis=1)])
        height = np.abs(den) / np.maximum(span, 1e-12)  # texels across the triangle
        ok = ~inside & (height > 0.5)
        bary[ok] = raw[ok]
    drawn = np.arange(len(t)) < int((tid >= 0).sum())  # (the ring texels come after the drawn ones)
    return (ys, xs), t, bary, np.concatenate(tpart), inside, drawn


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


MISS_FILL_3D = 8  # (r66) texels whose Cycles ray found no scene mesh INSIDE their triangle take the inverse-distance mean
# of this many nearest baked texels of the same part ON THE SURFACE (3D), not the nearest texel in the atlas: filled in
# the atlas, a run of missed texels (rc2p/q: 1.9% of the head's, at the nostril rims and the ala's groove) copied its
# border in a texel staircase, from whatever lay next to it in the atlas (a tiny island beside it: blocky dark / pink
# patches, game_ready.md r64-r66). 0 = the atlas fill only.


def _fill_missed_3d(given: dict, baked: np.ndarray, miss: np.ndarray, ys, xs, P, part, log: list) -> dict:
    """bake(): each missed texel (rows of ys/xs/P/part, mask `miss`) from its MISS_FILL_3D nearest baked texels of the
    same part by surface position, inverse-distance weighted."""
    from scipy.spatial import cKDTree
    ok = baked[ys, xs]
    out = {k: v.copy() for k, v in given.items()}
    n = 0
    for pi in np.unique(part[miss]):
        src = np.flatnonzero(ok & (part == pi))
        dst = np.flatnonzero(miss & (part == pi))
        if len(src) < MISS_FILL_3D or not len(dst):
            continue
        d, j = cKDTree(P[src]).query(P[dst], k=MISS_FILL_3D)
        w = 1.0 / np.maximum(d, 1e-5) ** 2
        w /= w.sum(1, keepdims=True)
        sy, sx = ys[src][j], xs[src][j]
        for k, v in given.items():
            out[k][ys[dst], xs[dst]] = np.einsum("nk,nkc->nc", w, v[sy, sx].astype(np.float64)).astype(v.dtype)
        n += len(dst)
    if n:
        log.append(f"    {n} texels missed inside their triangle: filled from their {MISS_FILL_3D} nearest baked texels on "
                   f"the surface")
    return out


def _unit(v):
    return v / np.maximum(np.linalg.norm(v, axis=-1, keepdims=True), 1e-12)


def _across_seams(parts, given, baked, share, ys, xs, tri, P, fill, tpart, texel):
    """The texels past each island's edge (rasterize's ring: their point P is their triangle's plane carried on
    past the edge) take what the chart across the seam baked at that surface point: the low-poly triangle of the
    same part, on another island, that P lies on (within half a texel), its uv, Cycles' maps sampled there
    bilinearly. Then bilinear filtering at a chart's edge reads the surface beyond it, as the chart across reads
    it. Returns (given, baked, texels filled)."""
    from .decalmap import _closest_bary
    r = np.flatnonzero(fill)
    if not len(r):
        return given, baked, 0
    C, UV = _corners(parts, "pos"), _corners(parts, "uv")
    isl = uv_islands(parts)
    # global vertex ids per triangle, and each vertex's triangles (padded): the faces across an edge are found by
    # topology, not by distance (a decimated cylinder's strips are hundreds of texels long: their centres are far
    # from a point just past their side)
    tv, base = [], 0
    for p in parts.values():
        tv.append(p["corner_vert"].reshape(-1, 3).astype(np.int64) + base)
        base += len(p["verts"])
    tv = np.concatenate(tv)
    vs, fs = tv.ravel(), np.repeat(np.arange(len(tv)), 3)
    o = np.argsort(vs, kind="stable")
    vs, fs = vs[o], fs[o]
    start = np.searchsorted(vs, np.arange(base))
    rank = np.arange(len(vs)) - start[vs]
    cap = int(min(rank.max() + 1, 16))
    vf = np.full((base, cap), -1, np.int64)
    keep = rank < cap
    vf[vs[keep], rank[keep]] = fs[keep]
    A = tri[r]
    # the edge of its own triangle the texel lies past (its most negative barycentric), and the faces round that
    # edge's two vertices: the triangle across the seam and its neighbours
    e0, e1 = C[A, 1] - C[A, 0], C[A, 2] - C[A, 0]
    nrm = np.cross(e0, e1)
    q = P[r] - C[A, 0]
    n2 = np.maximum((nrm * nrm).sum(1), 1e-30)
    w1 = (np.cross(q, e1) * nrm).sum(1) / n2
    w2 = (np.cross(e0, q) * nrm).sum(1) / n2
    k_out = np.argmin(np.stack([1 - w1 - w2, w1, w2], 1), 1)
    va = tv[A, (k_out + 1) % 3]
    vb = tv[A, (k_out + 2) % 3]
    cand = np.concatenate([vf[va], vf[vb]], 1)
    best, bt, bw = np.full(len(r), np.inf), np.full(len(r), -1), np.zeros((len(r), 3))
    own_isl, own_part = isl[A], tpart[A]
    for j in range(cand.shape[1]):
        t = cand[:, j]
        okj = t >= 0
        t = np.where(okj, t, 0)
        w = _closest_bary(P[r], C[t, 0], C[t, 1], C[t, 2])
        d = np.linalg.norm(np.einsum("nk,nkc->nc", w, C[t]) - P[r], axis=1)
        better = okj & (isl[t] != own_isl) & (tpart[t] == own_part) & (d < best)
        best[better], bt[better], bw[better] = d[better], t[better], w[better]
    ok = (bt >= 0) & (best < texel)
    if not ok.any():
        return given, baked, 0
    uv = np.einsum("nk,nkc->nc", bw[ok], UV[bt[ok]])
    yy, xx = ys[r[ok]], xs[r[ok]]
    a = share[yy, xx][:, None]  # an edge texel part-baked keeps its own points' share: the rest from across
    from scipy import ndimage
    done = baked.copy()
    done[yy, xx] = True
    # (one pass: a second, reading the chart across with its edge texels already filled, measured worse: 1.08 -> 1.14)
    _, (iy, ix) = ndimage.distance_transform_edt(~baked, return_indices=True)
    out = {}
    for name, img in given.items():
        v = _bilinear(img[iy, ix], uv)  # (past its own edge, the chart across reads its nearest texel)
        o = img.copy()
        o[yy, xx] = a * img[yy, xx] + (1 - a) * v
        o[yy, xx, -1] = 1.0  # baked now
        out[name] = o
    return out, done, int(ok.sum())


INNER_PAINT_ROUGHNESS = 0.4  # the inner lip: moist, a soft sheen (0.25 read as wet plastic streaks in every
# smile and the jaw open: coordinator on m18, 2026-10-15)


def inner_paint(parts: dict, topo: dict, head: dict, log: list) -> None:
    """A GNM head's inner lip rolls (skin_features.inner_lip_values by GNM vertex) as each low-poly corner's
    "inner_paint" weight, which bake() lays over the scene's colour: the scene's surface has no rolls with the lips
    closed (the fill behind the seam), so what the bake found there was the skin beside the seam."""
    from . import skin_features as sfe
    val = sfe.inner_lip_values(head)
    if val is None:
        return
    deep = sfe.mouth_interior_values(head)
    if deep is None:
        deep = np.zeros(len(val))
    on_sock = deep > 0
    val = np.where(on_sock, 1.0, val)  # the sock is wet mucosa too: red at the rim, darkening inward
    for pn, (tp, _) in topo.items():
        z = np.load(tp)
        if pn not in parts or "gnm" not in z.files or len(z["verts"]) != len(parts[pn]["verts"]):
            continue
        gi = np.asarray(z["gnm"], int)
        v = np.where((gi >= 0) & (gi < len(val)), val[np.clip(gi, 0, len(val) - 1)], 0.0)
        dv = np.where((gi >= 0) & (gi < len(deep)), deep[np.clip(gi, 0, len(deep) - 1)], 0.0)
        parts[pn]["inner_paint"] = np.stack([v, dv], 1)[parts[pn]["corner_vert"]].astype(np.float32)
        log.append(f"{pn}: the lips' inner rolls painted on {int((v > 0.99).sum())} vertices (GNM's rings to the "
                   f"contact ring)")


# (r65) the skin's tiling micro detail is baked into the part's own normal / roughness / colour maps (False = the
# old split: tiling maps only, which the GLB can't carry)
BAKE_SKIN_DETAIL = True


def face_keep_paint(parts: dict, topo: dict, log: list) -> None:
    """(one mesh, retopo.FACE_KEEP) each low-poly corner's "keep" weight: 1 where the head's surface IS the approved GNM
    head (retopo.face_keep: eyes, mouth, nose), fading over its rings. bake() doesn't project those texels onto the field:
    the field is the smoothed copy of that head (the lips up to 6.6 mm off, game_ready.md r42), so projected, the lips'
    texels went astray (r41's lip gate 2.69 -> 4.27% with the lids kept) and their normals were the smoothed lips'."""
    from . import retopo
    if not retopo.FACE_KEEP:
        return
    for pn, (tp, _) in topo.items():
        z = np.load(tp)
        if pn not in parts or "gnm" not in z.files or len(z["verts"]) != len(parts[pn]["verts"]):
            continue
        L, S = np.asarray(z["loops"], int), np.asarray(z["sizes"], int)
        faces = np.split(L, np.cumsum(S)[:-1])
        w = retopo.face_keep(np.asarray(z["gnm"], int), faces)
        parts[pn]["keep"] = w[parts[pn]["corner_vert"]].astype(np.float32)[:, None]
        log.append(f"{pn}: {int((w > 0.999).sum())} vertices of the approved face kept, not projected in the bake")


LIP_FLOOR_ROUGHNESS = 0.38  # (r66) bake(): the export's lower lip is never glossier than this. The stage's lip sheen pad
# (skin:lip_sheen, 0.24 at 0.8) was tuned with the lip lines breaking its highlight; baked, those lines are sub-texel
# (0.24 mm deep, ~1 mm period at 0.77 mm texels: a faint ripple, r65), so the GLB's lower lip was one unbroken, wet-plastic
# highlight at ~0.31 (game_ready.md r64 / r65). The floor is laid by the skin's own lower-lip zone, per texel.
LIP_FLOOR_ZONE = {"zone": {"name": "lip_lower", "grow": 0.6}}  # (lip_sheen's own zone: the pad never reaches past it)


def lip_floor_mask(spec: dict, X: np.ndarray, n: np.ndarray) -> np.ndarray:
    """0..1 per surface point (Blender coords, normals): the skin's lower-lip zone, where bake() floors the roughness at
    LIP_FLOOR_ROUGHNESS. Zeros without a skin or its lip landmarks."""
    from . import paint
    from .surface import Points
    sk = spec.get("skin") or {}
    if not sk or not len(X):
        return np.zeros(len(X))
    try:
        pts = Points(spec, X, n, np.zeros(len(X), int), [sk.get("part", "body")], 0.001)
        pts.footprint = 0.0005
        from . import skin
        ly = skin.expand_zones(spec, {"mask": [LIP_FLOOR_ZONE]}, "lip floor")
        return paint.layer_mask(spec, "lip_floor", ly, paint._View(pts, np.arange(len(X))))
    except (KeyError, ValueError):  # (no lip landmarks on this model: no floor)
        return np.zeros(len(X))


def lip_front_share(P: np.ndarray, bad: np.ndarray, lipw: np.ndarray) -> tuple[float | None, int]:
    """The share of the lips' FRONT band texels whose projection went astray (bake), and their count (None under
    50 texels). The band: in front of the inner rolls (lipw > 0.5: hidden in the closed seam, ~28% astray even when
    clean, so left out), within 1.2 half-widths across and 0.6 up / down of the rolls' centre (Blender axes, faces
    -y). Clean (retopo.SOCK_FALLOFF 0, v31/v37) 2.5%, x32's torn streaks (6) 6.5% (tests/test_lip_astray.py)."""
    rolls = lipw > 0.5
    if rolls.sum() < 50:
        return None, 0
    r = P[rolls]
    c = r.mean(0)
    hw = np.abs(r[:, 0] - c[0]).max()
    Q = P - c
    lips = (np.abs(Q[:, 0]) < 1.2 * hw) & (np.abs(Q[:, 2]) < 0.6 * hw) & (Q[:, 1] < 0) & ~rolls
    if lips.sum() < 50:
        return None, 0
    return float(bad[lips].mean()), int(lips.sum())


LIP_ASTRAY_WARN = 0.045  # bake(): the share of the lips' front-band texels whose projection went astray, over which
# the log warns (clean v31/v37 2.5%, v32's torn streaks 6.5%: tests/test_lip_astray.py; a narrow margin, 2.6x)


def bake(parts: dict, size: int, ctx: dict, log: list, atlas: int | None, given: dict) -> dict:
    """Every map of one atlas (None: all parts) as float arrays (size, size, k), plus the height range. Each
    texel is projected onto its export part's own field (normal, height); given: the maps Cycles baked from the
    scene (`scene_maps`: color linear, rms, ao, height; rows top first) for paint, AO and painted relief."""
    t0 = time.time()
    names = list(parts)
    # the islands' own texels plus a ring past their edges (half the gap between islands): extrapolated, so
    # bilinear filtering at a chart's edge reads the surface beyond it on both sides of a seam
    (ys, xs), tri, bary, tpart, inside, drawn = rasterize(parts, size, atlas, ring=max(1, margin_px(size) // 2))
    log.append(f"rasterized {drawn.sum()} texels ({drawn.sum() / size ** 2:.0%} of the atlas) + {(~drawn).sum()} "
               f"past the islands' edges in {time.time() - t0:.1f}s")

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
    lip_astray = {}
    t1 = time.time()
    island = uv_islands(parts)[tri]
    # the lips' texels (inner_paint's roll weight > 0: GNM's rings from the sock to past the contact ring), so a
    # projection that goes astray there is named on its own: a whole-part share hid x32's torn lip streaks
    # (3.75 -> 4.89% of the head, ~all of the rise in the lips' band; game_ready.md r20/r21)
    lipw = None
    if any("inner_paint" in p for p in parts.values()):
        # (column 1 = the mouth sock's depth: the sock takes column 0 = 1 too, but lies hidden behind the closed
        # lips, where a projection astray is expected; only the lips' own rolls count)
        lc = np.concatenate([(np.where(p["inner_paint"][:, 1] > 0, 0.0, p["inner_paint"][:, 0]) if "inner_paint" in p
                              else np.zeros(len(p["corner_vert"]))).reshape(-1, 3) for p in parts.values()]).astype(np.float64)
        lipw = (bary * lc[tri]).sum(1)
    kw = None
    if any("keep" in p for p in parts.values()):  # (face_keep_paint: the approved face is the low poly itself)
        for p_ in parts.values():
            p_.setdefault("keep", np.zeros((len(p_["corner_vert"]), 1), np.float32))
        kw = np.clip(interp("keep")[:, 0], 0, 1)
    for pi, pn in enumerate(names):
        sel = np.flatnonzero(part == pi)
        if not len(sel):
            continue
        vx = ctx["frames"][pn][1]
        x, g = _project(ctx["streams"][pn], X[sel], ys[sel], xs[sel], island[sel], vx)
        if kw is not None:  # kept: the low poly's own position / normal (fading out over the keep's rings)
            k_ = kw[sel][:, None]
            x = P[sel] + (1 - k_) * (x - P[sel])
            g = _unit(k_ * Nl[sel] + (1 - k_) * _unit(g))
        # a texel that wandered off (onto the far side of a thin sheet, or out of a thin gap) keeps the low-poly
        # surface. Steep but outward normals (a shingle's butt end, a board's edge) are real detail: keep those.
        bad = (np.linalg.norm(x - P[sel], axis=1) > 6 * vx) | ((_unit(g) * Nl[sel]).sum(1) < -0.2)
        x[bad], g[bad] = P[sel][bad], Nl[sel][bad]
        X[sel], G[sel] = x, _unit(g)
        if bad.any():
            log.append(f"  {pn}: {bad.mean():.2%} of texels kept the low-poly surface (projection went astray)"
                       + (": WARNING, the low poly is too far from thin geometry: raise its triangle_weight "
                          "(or min_triangles)" if bad.mean() > 0.2 else ""))
        if os.environ.get("HP_ASTRAY_DUMP"):  # (debug: where the astray texels are, to compare two exports)
            np.savez(Path(os.environ["HP_ASTRAY_DUMP"]) / f"astray_{pn}_{atlas}.npz", P=P[sel], bad=bad,
                     lipw=lipw[sel] if lipw is not None else np.zeros(len(sel)))
        share, nl = lip_front_share(P[sel], bad, lipw[sel]) if lipw is not None else (None, 0)
        if share is not None:
            lip_astray[pn] = share
            log.append(f"  {pn}: {share:.2%} of the lips' {nl} front texels kept the low-poly surface"
                       + (f": WARNING, the lips' texels projected astray (over {LIP_ASTRAY_WARN:.1%}): torn streaks "
                          f"bake into the lips (the mouth sock moved onto their exact surface? retopo.SOCK_FALLOFF)"
                          if share > LIP_ASTRAY_WARN else ""))
    log.append(f"projected onto the exact surface in {time.time() - t1:.1f}s")
    # texels whose ray found no scene mesh (alpha 0) take their nearest baked neighbour
    share = given["color"][..., 3].astype(np.float64)  # (supersampled: the share of the texel's points baked)
    baked = share > 0
    miss = ~baked[ys, xs] & drawn
    if miss.any():
        log.append(f"  {miss.sum() / drawn.sum():.2%} of texels found no scene mesh along their ray: filled from neighbours")
        log.append(f"    {(miss & ~inside).sum() / miss.sum():.0%} of them are edge texels (centre outside its triangle)")
        for pi, pn in enumerate(names):
            m = (miss & inside)[(part == pi) & drawn]
            if m.size and m.mean() > 0.005:
                log.append(f"    {pn}: {m.mean():.1%} of its texels missed inside their triangle")
        given = {k: _dilate(v, baked) for k, v in given.items()}
        if MISS_FILL_3D:
            given = _fill_missed_3d(given, baked, miss & inside, ys, xs, P, part, log)
        if os.environ.get("HP_BAKE_DUMP"):  # (debug, r66: where the missed texels are, to mark them on a crop)
            np.savez(Path(os.environ["HP_BAKE_DUMP"]) / f"miss_{atlas}.npz", P=P[miss], inside=inside[miss],
                     part=part[miss], names=np.array(names), ys=ys[miss], xs=xs[miss], size=size)

    c = _corners(parts, "pos")[np.unique(tri)]  # the atlas's triangles: surface per texel
    area = np.linalg.norm(np.cross(c[:, 1] - c[:, 0], c[:, 2] - c[:, 0]), axis=1).sum() / 2
    texel = np.sqrt(area / max(int(drawn.sum()), 1))
    fill = share[ys, xs] < 0.999  # past the islands' edges, edge texels part-baked or missed
    given, baked, n_across = _across_seams(parts, given, baked, share, ys, xs, tri, P, fill, tpart, texel)
    if fill.any():
        log.append(f"  {n_across / fill.sum():.0%} of the texels past the islands' edges (or missed at them) filled "
                   f"across their seam; the rest (open edges) from the nearest texel")
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

    if any(parts[pn].get("designed") is not None for pn in names):  # (one mesh, own quads) GNM's interior
        # surfaces (sock, lip rolls, lid insides) are its own, not the field's: projected, the sock's texels read
        # heights of 25 mm and set the whole atlas's height range
        td = np.concatenate([np.asarray(parts[pn]["designed"], bool)[parts[pn]["corner_vert"].reshape(-1, 3)].all(1)
                             if parts[pn].get("designed") is not None else
                             np.zeros(len(parts[pn]["corner_vert"]) // 3, bool) for pn in names])
        dm = td[tri]
        X[dm], G[dm] = P[dm], Nl[dm]
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
    # Cycles' channels keep their own texels past the islands' edges too (the bake's margin, filled across each
    # seam from the adjacent faces): only what lies beyond them is filled from the nearest texel
    own = baked.copy()
    own[ys[drawn], xs[drawn]] = True

    def put_given(name, img):
        maps[name] = _dilate(img.astype(np.float64), own)
    lin = given["color"][..., :3].astype(np.float64)
    if any("inner_paint" in p for p in parts.values()):  # (inner_paint: the lips' rolls, hidden in the scene)
        from . import skin_features as sfe
        for pn_, p_ in parts.items():
            p_.setdefault("inner_paint", np.zeros((len(p_["corner_vert"]), 2), np.float32))
        ip_ = interp("inner_paint")
        w_ = np.zeros(lin.shape[:2] + (2,))
        w_[ys, xs] = np.clip(ip_[:, :2], 0, 1)
        w_ = _dilate(w_, own)
        d_ = w_[..., 1:2]
        w_ = w_[..., 0]
        inner_c = (1 - d_) * np.asarray(sfe.INNER_LIP_COLOR, float) + d_ * np.asarray(sfe.MOUTH_DEEP_COLOR, float)
        lin = lin * (1 - w_[..., None]) + inner_c * w_[..., None]
        if os.environ.get("HP_BAKE_DUMP"):  # (debug, r70: Tess's ala patch is this overlay at w = 1, deep = 1 exactly,
            # on texels whose GLB triangles carry no paint: which bake-time triangle / uv put it there)
            np.savez(Path(os.environ["HP_BAKE_DUMP"]) / f"inner_{atlas}.npz", ys=ys, xs=xs, tri=tri, part=part,
                     drawn=drawn, ip=ip_[:, :2].astype(np.float32), P=P.astype(np.float32), names=np.array(names),
                     raw=given["color"].astype(np.float16), own=own, w=w_.astype(np.float16), d=d_[..., 0].astype(np.float16),
                     **{f"uv_{pn_}": p_["uv"] for pn_, p_ in parts.items()},
                     **{f"cv_{pn_}": p_["corner_vert"] for pn_, p_ in parts.items()},
                     **{f"v_{pn_}": p_["verts"] for pn_, p_ in parts.items()})
        rms = given["rms"].astype(np.float64).copy()
        rms[..., 0] = rms[..., 0] * (1 - w_) + INNER_PAINT_ROUGHNESS * w_
        given = {**given, "rms": rms}
    lf = ctx.get("lip_floor")  # (r66) the lower lip never glossier than LIP_FLOOR_ROUGHNESS (skin's lower-lip zone)
    if lf is not None and lf[1] in names and LIP_FLOOR_ROUGHNESS > 0:
        sel = np.flatnonzero(part == names.index(lf[1]))
        mk = lip_floor_mask(lf[0], P[sel], Nl[sel]) if len(sel) else np.zeros(0)
        if (mk > 0).any():
            rms = given["rms"].astype(np.float64).copy()
            r_ = rms[ys[sel], xs[sel], 0]
            rms[ys[sel], xs[sel], 0] = r_ + mk * np.maximum(LIP_FLOOR_ROUGHNESS - r_, 0)
            given = {**given, "rms": rms}
            on = mk > 0.5
            log.append(f"lip floor: {int(on.sum())} lower-lip texels, roughness mean {r_[on].mean():.3f} -> "
                       f"{rms[ys[sel][on], xs[sel][on], 0].mean():.3f} (floor {LIP_FLOOR_ROUGHNESS})" if on.any() else
                       "lip floor: no texel over half in the lower-lip zone")
    put_given("basecolor", _srgb(lin))
    put_given("roughness", given["rms"][..., :1])
    put_given("metallic", given["rms"][..., 1:2])
    put_given("specular", given["rms"][..., 2:3])
    ao_ = given["ao"][..., :1].astype(np.float64)
    off_ = [names.index(pn_) for pn_ in (ctx.get("ao_off") or ()) if pn_ in names]
    if off_ and EYES_AO_OFF:  # (the eyeball: its baked AO is the lids' shadow in the rest pose, wrong once a lid moves)
        m_ = np.isin(tpart[tri], off_)  # (tpart is per triangle)
        ao_ = ao_.copy()
        ao_[ys[m_], xs[m_]] = 1.0
        log.append(f"ao: {', '.join(names[i] for i in off_)} left unoccluded ({int(m_.sum())} texels): the lids move")
    put_given("ao", ao_)
    if "blink" in given:   # (skin) the crease line and the lid's occlusion as their own multiplier map, out of basecolor
        # (sRGB-encoded like basecolor: the notes declare it sRGB, as engines sample colour maps. Written as the raw
        # linear ratio it was decoded to ~ratio^2.2: the lids' crease and occlusion twice as dark and orange, expr_r15)
        put_given("blink", _srgb(given["blink"][..., :3]))
    put("normal", tn * 0.5 + 0.5, 0.5)
    put("height", (height / hr * 0.5 + 0.5)[:, None], 0.5)
    maps["orm"] = np.concatenate([maps["ao"], maps["roughness"], maps["metallic"]], -1)
    return {"maps": maps, "height_range": hr, "coverage": float(drawn.sum()) / size ** 2, "lip_astray": lip_astray}


def _bilinear(img: np.ndarray, uv: np.ndarray) -> np.ndarray:
    """img (rows top first) at uvs as an engine samples it (bilinear, texel centres at (i + .5) / size, clamped)."""
    S = img.shape[0]
    x, y = uv[:, 0] * S - 0.5, (1 - uv[:, 1]) * S - 0.5
    x0, y0 = np.floor(x).astype(np.int64), np.floor(y).astype(np.int64)
    fx, fy = (x - x0)[:, None], (y - y0)[:, None]
    c = lambda a: np.clip(a, 0, S - 1)  # noqa: E731
    return (img[c(y0), c(x0)] * (1 - fx) * (1 - fy) + img[c(y0), c(x0 + 1)] * fx * (1 - fy)
            + img[c(y0 + 1), c(x0)] * (1 - fx) * fy + img[c(y0 + 1), c(x0 + 1)] * fx * fy)


def seam_steps(p: dict, img: np.ndarray, per_texel: int = 2) -> dict | None:
    """How a map steps across a part's UV seams (edges whose two triangles have the same vertices but different
    uvs), as an engine shows it: along every seam edge, the step across it (half a texel into each chart, sampled
    bilinearly) against the steps beside it (half a texel to 1.5 texels in, on each side). excess = their ratio
    summed over the seams (~1 = invisible: the map runs on across the seam as it does inside a chart; a texel's
    misregistration of a sharp edge is ~2+), p95 = the 95th percentile of it per sample where the map changes
    (beside > 2% of its range). None if the part has no seams."""
    S = img.shape[0]
    cv = p["corner_vert"].reshape(-1, 3).astype(np.int64)
    uv = p["uv"].reshape(-1, 3, 2).astype(np.float64)
    a, b = cv, np.roll(cv, -1, 1)  # edge k runs from corner k to k + 1
    ea, eb = np.minimum(a, b).T.ravel(), np.maximum(a, b).T.ravel()
    et, ek = np.tile(np.arange(len(cv)), 3), np.repeat(np.arange(3), len(cv))
    order = np.lexsort((eb, ea))
    ea, eb, et, ek = ea[order], eb[order], et[order], ek[order]
    pair = np.flatnonzero((ea[1:] == ea[:-1]) & (eb[1:] == eb[:-1]))
    if not len(pair):
        return None
    tA, kA, tB, kB = et[pair], ek[pair], et[pair + 1], ek[pair + 1]

    def ends(t, k, v0):  # the edge's uv at vertex v0 then the other end, and the opposite corner's uv
        i0, i1 = k, (k + 1) % 3
        swap = cv[t, i0] != v0
        u0 = np.where(swap[:, None], uv[t, i1], uv[t, i0])
        u1 = np.where(swap[:, None], uv[t, i0], uv[t, i1])
        return u0, u1, uv[t, (k + 2) % 3]
    v0 = ea[pair]
    a0, a1, a2 = ends(tA, kA, v0)
    b0, b1, b2 = ends(tB, kB, v0)
    seam = (np.abs(a0 - b0).max(1) > 0.5 / S) | (np.abs(a1 - b1).max(1) > 0.5 / S)
    if not seam.any():
        return None
    a0, a1, a2, b0, b1, b2 = (x[seam] for x in (a0, a1, a2, b0, b1, b2))

    def inward(u0, u1, u2):
        d = u1 - u0
        n = np.stack([-d[:, 1], d[:, 0]], 1)
        n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-12)
        return n * np.sign(((u2 - u0) * n).sum(1))[:, None]
    nA, nB = inward(a0, a1, a2), inward(b0, b1, b2)
    m = np.maximum(np.ceil(np.linalg.norm(a1 - a0, axis=1) * S * per_texel).astype(np.int64), 1)
    e = np.repeat(np.arange(len(m)), m)
    t = (np.arange(len(e)) - np.repeat(np.cumsum(m) - m, m) + 0.5) / m[e]
    t = t[:, None]
    pa, pb = a0[e] + t * (a1[e] - a0[e]), b0[e] + t * (b1[e] - b0[e])
    A0, A1 = (_bilinear(img, pa + nA[e] * s / S) for s in (0.5, 1.5))
    B0, B1 = (_bilinear(img, pb + nB[e] * s / S) for s in (0.5, 1.5))
    across = np.linalg.norm(A0 - B0, axis=1)
    beside = 0.5 * (np.linalg.norm(A1 - A0, axis=1) + np.linalg.norm(B1 - B0, axis=1))
    rng = float(np.ptp(img.reshape(-1, img.shape[-1]), axis=0).max()) or 1.0
    busy = beside > 0.02 * rng
    eps = 0.002 * rng * len(e)  # steps under 0.2% of the map's range are noise, not edges (a flat map reads ~1)
    return {"edges": int(seam.sum()), "samples": len(e),
            "excess": round(float((across.sum() + eps) / (beside.sum() + eps)), 2),
            "p95": round(float(np.percentile(across[busy] / beside[busy], 95)), 2) if busy.sum() > 20 else None}


def _slit_mask(lid_fold, n: int) -> np.ndarray:
    """(n,) bool over GNM's vertices: the lid fold's slit and crease tail (gnm_fold.slit_ids). The fold re-sections the
    upper lid's rings into platform, slit and roll: the roll's lower edge undercuts the slit by design (the hood), so its
    edges fold against their neighbours (Garrett ~50 / Tess ~37 exterior folded edges after the wrap clamp WRAP_MAX,
    2026-10-18 r12, all on rings ring+1 / ring+2). Those are the crease, not a tear."""
    m = np.zeros(n, bool)
    if lid_fold:
        from . import gnm_fold
        ids = np.array([v for v in gnm_fold.slit_ids(lid_fold) if 0 <= v < n], int)   # (every key: the tapered ends
        # carry weight 0 for the cavity paint but are the same rings, and fold the same)
        m[ids] = True
    return m


def _designed_interior(topo, verts, creases: bool = True, lid_fold=None) -> np.ndarray | None:
    """(one mesh, own quads) per low-poly vertex: GNM's own interior surfaces (the lids' insides, the inner lip
    rolls, nostrils' depths, the mouth sock): modelled to roll back under the skin, so they fold against the field
    and stand off it by design. None when the part isn't that topology. lid_fold (the head's base.head.lid_fold):
    with creases, the fold's slit too (_slit_mask)."""
    if not topo:
        return None
    z = np.load(topo[0])
    if "gnm" not in z.files or len(z["verts"]) != len(verts) or not np.allclose(np.asarray(verts, float), z["verts"],
                                                                                   atol=1e-5):
        return None
    from . import base as basemod
    g = basemod._gnm_data()
    from . import gnmloops
    gid = gnmloops.raw_id(np.asarray(z["gnm"], int))  # (the lids' new vertices: as their first parent)
    gr = {k: np.asarray(v) > 0.5 for k, v in g["groups"].items()}
    # (+ the lips and the lid margins: closed in the neutral, their seams are creases by design; measured on the
    # adult's export they were the rest of the TORN clusters at both eyes and the mouth)
    ins = ~gr["skin_exterior"] | gr["mouth_sock"]
    if creases:
        ins = ins | gr["upper_lip"] | gr["lower_lip"] | gr["eye_sockets"] | gr["ears"]  # (ears: kept as GNM made them)
        ins = ins | _slit_mask(lid_fold, len(ins))
    return (gid >= 0) & ins[np.maximum(gid, 0)]


def mesh_quality(verts: np.ndarray, tris: np.ndarray, prims=None, designed: np.ndarray | None = None) -> dict:
    """A triangle mesh's own quality report: distance to the exact field (mm; p50/p99/max over face centres and
    edge midpoints, where a low poly strays between its vertices) when `prims` are given, and counts of
    non-manifold edges (3+ faces), open edges, folds (neighbouring faces turned > 120 deg) and slivers (smallest
    angle < 2 deg). designed: per vertex, surfaces modelled to fold back (a one-mesh head's lid insides, lip rolls
    and mouth sock): triangles touching them are left out of the distance, folds and turned faces."""
    if designed is not None and designed.any():
        keep = ~np.asarray(designed, bool)[np.asarray(tris)].any(1)  # (and their rims: a lid's margin folds back)
        q = mesh_quality(verts, np.asarray(tris)[keep], prims)
        q["designed_triangles"] = int((~keep).sum())
        return q
    P = np.asarray(verts, np.float64)
    key = np.round(P / 1e-6).astype(np.int64)  # weld split vertices (uv seams) by position
    _, weld = np.unique(key, axis=0, return_inverse=True)
    T = weld.reshape(-1)[np.asarray(tris)]
    c = P[np.asarray(tris)]
    n = np.cross(c[:, 1] - c[:, 0], c[:, 2] - c[:, 0])
    area2 = np.linalg.norm(n, axis=1)
    n = n / np.maximum(area2, 1e-30)[:, None]
    E = np.sort(np.stack([T[:, [0, 1]], T[:, [1, 2]], T[:, [2, 0]]], 1).reshape(-1, 2), axis=1)
    fid = np.repeat(np.arange(len(T)), 3)
    uniq, inv, cnt = np.unique(E, axis=0, return_inverse=True, return_counts=True)
    inv = inv.reshape(-1)
    out = {"triangles": int(len(T)), "non_manifold_edges": int((cnt > 2).sum()), "open_edges": int((cnt == 1).sum())}
    two = np.flatnonzero(cnt == 2)
    order = np.argsort(inv, kind="stable")
    first = np.searchsorted(inv[order], two)
    fa, fb = fid[order[first]], fid[order[first + 1]]
    fold = (n[fa] * n[fb]).sum(1) < -0.5
    out["folds"] = int(fold.sum())
    spots = [P[uniq[two[fold]]].mean(1)] if fold.any() else []
    ang = []
    for i in range(3):
        a, b = c[:, (i + 1) % 3] - c[:, i], c[:, (i + 2) % 3] - c[:, i]
        cosv = (a * b).sum(1) / np.maximum(np.linalg.norm(a, axis=1) * np.linalg.norm(b, axis=1), 1e-30)
        ang.append(np.degrees(np.arccos(np.clip(cosv, -1, 1))))
    out["slivers"] = int((np.min(ang, axis=0) < 2.0).sum())
    if prims is not None:
        probe = np.concatenate([c.mean(1), ((c + np.roll(c, 1, 1)) / 2).reshape(-1, 3)])
        d = np.abs(sdf.field_at(prims, probe, clip=False)) * 1000
        out.update(err_mm_p50=round(float(np.percentile(d, 50)), 2), err_mm_p99=round(float(np.percentile(d, 99)), 2),
                   err_mm_max=round(float(d.max()), 2))
        # faces turned against the surface they lie on (their normal against the field's gradient): the inside of
        # a tangle or a tear, drawn dark or culled by an engine. Only faces near the surface count (a face
        # bridging a gap has no surface to disagree with).
        fc = c.mean(1)
        ok = (d[:len(fc)] < 2.0) & (area2 > 1e-12)
        if ok.any():
            h = 2e-4
            g = np.stack([sdf.field_at(prims, fc[ok] + h * e, clip=False) - sdf.field_at(prims, fc[ok] - h * e, clip=False)
                          for e in np.eye(3)], 1)
            g /= np.maximum(np.linalg.norm(g, axis=1, keepdims=True), 1e-12)
            bad = (g * n[ok]).sum(1) < -0.3
            out["turned"] = int(bad.sum())
            if bad.any():
                spots.append(fc[ok][bad])
        else:
            out["turned"] = 0
    out["spots"] = np.concatenate(spots) if spots else np.zeros((0, 3))
    return out


DEFECT_CLUSTER = 12  # this many folded edges / turned faces by one joint is a tear or a tangle someone will see


def defect_regions(spots: np.ndarray, spec: dict) -> list[tuple[str, int]]:
    """Where a mesh's folded edges and turned faces are, by the model's nearest joint: [(joint, count)] for every
    joint with DEFECT_CLUSTER or more, most first (a model without joints: one entry per 10 cm cell, named by its
    position)."""
    if not len(spots):
        return []
    try:
        from .spec import expand_mirror, resolve_point
        s = expand_mirror(spec)
        names = [k for k in s.get("joints", {}) if not k.startswith("lm_")]
        J = np.array([resolve_point(s, k) for k in names], float)
        lms = [k for k in s.get("joints", {}) if k.startswith("lm_")]
        L = np.array([resolve_point(s, k) for k in lms], float).reshape(-1, 3)
    except Exception:  # noqa: BLE001
        names, J, lms, L = [], np.zeros((0, 3)), [], np.zeros((0, 3))
    if len(names):
        from scipy.spatial import cKDTree
        near = cKDTree(J).query(spots)[1]
        lab = [names[i] for i in near]
        if len(lms):  # clusters are counted by modelling joint (landmarks are many and close: they'd split one tear
            # into several small counts), but NAMED by a face landmark where one is nearer their middle: a GNM head
            # has no mouth joint, and the mouth's cluster read "TORN at eye_front.L", 8 cm away
            for nm in set(lab):
                mid = spots[[x == nm for x in lab]].mean(0)
                d, i = cKDTree(L).query(mid)
                if d < np.linalg.norm(mid - J[names.index(nm)]):
                    lab = [f"{lms[i]} (by {nm})" if x == nm else x for x in lab]
    else:
        lab = ["[%.1f, %.1f, %.1f]" % tuple(np.round(q / 0.1) * 0.1) for q in spots]
    u, cnt = np.unique(lab, return_counts=True)
    return [(str(a), int(b)) for b, a in sorted(zip(cnt, u), reverse=True) if b >= DEFECT_CLUSTER]


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


BAKE_CAGE = True  # (r51) bake through a per-vertex cage (cage_verts) instead of one extrusion per part


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
    out = np.minimum(out, np.maximum(CAGE_CLEAR * clear, CAGE_MIN))
    return V + n * out[:, None]


CAGE_CLEAR = 0.45  # cage_verts: a vertex's cage at most this share of its clearance (first hit of the part's own surface
CAGE_MIN = 0.0002  # along its cage normal), never under CAGE_MIN metres (a ray starting on the surface misses it)


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
            extra = {}
            if BAKE_CAGE:
                extra["cage"] = cage_verts(p, d, vx)
                out_ = float(np.max(np.linalg.norm(extra["cage"] - np.asarray(p["verts"], np.float64), axis=1), initial=0.0))
            np.savez(f, verts=p["verts"], corner_vert=p["corner_vert"], uv=p["uv"], normal=p["normal"], **extra)
            pf = next((q for q, dd in ctx["prefabs"].items() if pn in dd["parts"]), None)
            M = ctx["prefabs"][pf]["instances"][ctx["prefabs"][pf]["bake"]].tolist() if pf else None
            jobs.append({"key": pn, "scene_key": ctx.get("split", {}).get(pn, pn), "low": str(f), "atlas": p["atlas"],
                         "extrusion": out_, "ray": out_ + in_, "matrix": M})
        t = time.time()
        bj = {"mode": "bake_maps", "blend": str(scene.blend_path(name)), "parts": jobs,
              "atlases": {str(ai): sz for ai, sz in sizes.items()}, "out": tmp, "samples": BAKE_SAMPLES,
              "supersample": BAKE_SS, "max_px": BAKE_SS_PX, "detail": ctx.get("bake_detail", True),
              "texel_m": ctx.get("texel_m", 0.0) if BAKE_PREFILTER else 0.0}
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


def _srgb(lin: np.ndarray) -> np.ndarray:
    """linear [0, 1] -> sRGB-encoded"""
    return np.where(lin <= 0.0031308, 12.92 * lin, 1.055 * np.clip(lin, 0, None) ** (1 / 2.4) - 0.055)


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


def _arc_quat(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """The shortest turn from unit a to unit b as a glTF quaternion (x, y, z, w)."""
    c = float(a @ b)
    if c < -1 + 1e-9:  # opposite: half a turn about any axis across a
        ax = np.cross(a, [1.0, 0, 0]) if abs(a[0]) < 0.9 else np.cross(a, [0, 0, 1.0])
        return np.r_[ax / np.linalg.norm(ax), 0.0]
    q = np.r_[np.cross(a, b), 1.0 + c]
    return q / np.linalg.norm(q)


def _quat_matrix(q: np.ndarray) -> np.ndarray:
    x, y, z, w = q
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                     [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                     [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])


def _head_share(rigged: dict, pn: str, bone: int) -> np.ndarray:
    J, W = rigged["weights"][pn]
    return (np.asarray(W) * (np.asarray(J) == bone)).sum(1)


BEND_RECIPE = ("Bend helpers (<joint>Bend: ForeArmBend at the elbow, LegBend at the knee, ArmBend at the shoulder, "
               "UpLegBend at the hip) are leaf joints after the Mixamo set, children of the joint's PARENT, standing at the "
               "joint. Drive each every frame after the animation: local rotation = slerp(identity, the driver joint's "
               "local rotation from its rest, share) (share 0.5: half the elbow's bend). The blend zone of the hinge's "
               "skin rides them, so a bent elbow / knee keeps its volume instead of collapsing to the chord. Undriven they "
               "stay on the parent and the hinge's skin lags: they MUST be driven (Unreal: a Control Rig / AnimBP "
               "'Copy Bone' with weight 0.5 or a pose driver; Unity: a Multi-Rotation Constraint at 0.5; Godot: copy "
               "the slerped rotation in _process).")


CORRECTIVE_RECIPE = (
    "Pose correctives are morph targets named corr_<Side><Joint>_<motion><deg> (on the skin and the parts worn over the "
    "joint; every LOD keeps them). Each is faded in by its joint's angle, every frame after the animation and the "
    "helper / twist drivers: take the joint's local rotation from its rest, split it into swing (about an axis across "
    "the bone) and twist (about the bone); deg = swing angle x dot(swing axis, axis_rest) (axis_rest in the parent's "
    "frame at rest = the json's Blender axes; glTF: (x, z, -y)); weight = 0 below from_deg, rising linearly to 1 at "
    "key_deg, then (when to_deg is set) falling to 0 at to_deg while the next key of the motion rises. Unreal: a Pose "
    "Driver node (swing, the joint, these targets as curves) or a Control Rig writing the curves; Unity: a script or "
    "Animation Rigging job setting SkinnedMeshRenderer.SetBlendShapeWeight (x100) in LateUpdate; Godot: a script "
    "setting MeshInstance3D.set_blend_shape_value in _process after the AnimationPlayer. Left at 0 the mesh bends "
    "by its weights alone (the arc weights, still sound).")
TWIST_RECIPE = {
    "what": "Twist bones are extra leaf joints after the Mixamo set (children of the Arm / ForeArm / UpLeg / Leg "
            "joints, named <segment>Twist<k>, k counted away from the body). Nothing animates them: left alone they "
            "ride their parent and the skin is what it would be without them. Drive them every frame, after the "
            "animation, to spread a segment's roll along it.",
    "driver": "roll = the twist of the DRIVER joint's local rotation (its pose relative to its rest; every Mixamo "
              "joint here rests unrotated) about the segment's axis (extras.axis_parent, in the driver's parent's "
              "rest frame = model space at rest): with q = (w, v) the local rotation and a the axis, "
              "roll = 2 atan2(v . a, w) (swing-twist decomposition). Then set each twist joint's local rotation to "
              "rest x turn(axis_local +Y, share x roll). After an import that re-orients bones (FBX), use "
              "q = inverse(rest local rotation) x pose local rotation, and for a the direction from the segment's "
              "joint to its child joint in that joint's rest frame; the twist joint still turns about its own "
              "length.",
    "modes": "follow: the driver is the segment's child (Hand for ForeArmTwist, Foot for LegTwist); shares rise to "
             "1.0 at the wrist/ankle, so the joint itself keeps no twist. counter: the driver is the segment's own "
             "joint (Arm for ArmTwist, UpLeg for UpLegTwist); shares are negative, -1.0 at the shoulder/hip (that "
             "skin stays with the clavicle/pelvis) rising to 0 at the elbow/knee.",
    "godot": "Godot 4: a SkeletonModifier3D after the AnimationMixer (in _process_modification read "
             "get_bone_pose_rotation(driver), compute roll as above, set_bone_pose_rotation(twist, rest_rotation * "
             "Quaternion(Vector3.UP, share * roll))); newer versions also have BoneTwistDisperser3D, which spreads "
             "a child's twist over a chain. Bone names lose the colon on import (mixamorig_LeftForeArmTwist1).",
    "unity": "Unity: Humanoid avatars ignore the extra joints (keep them as extra transforms: untick 'Strip bones' "
             "/ leave Optimize Game Objects off, or expose them), so Mixamo clips play unchanged; drive them in "
             "LateUpdate, or with the Animation Rigging package's Twist Correction constraint (source = the driver "
             "joint, twist axis = the segment's, twist nodes with weights = the shares; its weights run -1..1, so "
             "counter chains work too). The avatar's own 'Upper/Lower Arm Twist' muscle settings only move roll "
             "between the two Mixamo joints of a limb (they know no extra bones): set them so the roll stays on the "
             "hand / upper-arm joint, and let the twist joints spread it.",
    "unreal": "Unreal: in a Post Process Anim Blueprint or Control Rig on the skeletal mesh (where the Mannequin "
              "drives its lowerarm_twist_01/02 and upperarm_twist_01/02), per twist bone: read the driver's roll "
              "about the segment axis and set the bone's local rotation to rest x (share x roll about its Y); "
              "Control Rig's 'Twist Bones' node does a follow chain in one node. Keep the twist bones out of the IK "
              "Rig's retarget chains so retargeted animation leaves them to the post process.",
}


_FROZEN_OVER: dict = {}  # {(path, mtime, size): the frozen garment's own "over"} (the pickles are big: read once)


def garment_over(spec: dict, log=None) -> dict:
    """{garment: the garment it is worn over} for the spec's garments. The spec's own "over" wins; a frozen garment
    without one ({"frozen", "color"}: cloth.FROZEN_KEYS carry no "over") falls back to the "over" frozen with it, the
    chain cloth's own layered cut uses (thaw). Garrett v6: his frozen garments wrote none, so _garment_stack was empty
    and no garment push-under or under-garment cull ran at any LOD (white shirt shards through the jacket at LOD1-3),
    silently. A fallback is logged; a cloth set with no chain at all is a WARNING."""
    import pickle
    from . import cloth as clothmod_
    out, fell = {}, []
    for gn, g_ in (spec.get("cloth") or {}).items():
        g_ = clothmod_.expanded(g_ or {})
        o_ = g_.get("over")
        if o_ is None and g_.get("frozen"):
            path = Path(g_["frozen"]).expanduser()
            if path.exists():
                st = path.stat()
                k0 = (str(path), st.st_mtime, st.st_size)
                if k0 not in _FROZEN_OVER:
                    th_ = clothmod_._THAWED.get(k0)
                    if th_ is None:
                        with open(path, "rb") as f:
                            th_ = pickle.load(f)
                    _FROZEN_OVER[k0] = (th_.get("g") or {}).get("over")
                o_ = _FROZEN_OVER[k0]
                if o_ is not None:
                    fell.append(f"{gn} over {o_}")
        out[gn] = o_
    if log is not None:
        if fell:
            log(f"garment layers: the spec gives no \"over\"; using the frozen garments' own chain: {', '.join(fell)}")
        if len(out) > 1 and all(v is None for v in out.values()):
            log(f"WARNING garment layers: {len(out)} garments and no \"over\" chain (spec or frozen): no garment "
                "push-under or under-garment cull runs at any LOD")
    return out


def _garment_stack(spec: dict, parts: dict, log=None) -> dict:
    """{under garment part: the garment parts over it, transitively} (cloth "over" chains, garment_over)."""
    stack = {}
    over_ = garment_over(spec, log)
    for on_ in over_:  # every garment down on_'s chain of "over" lies under on_
        x_, seen_ = over_.get(on_), {on_}
        while x_ is not None and x_ not in seen_:
            seen_.add(x_)
            if f"cloth_{x_}" in parts and f"cloth_{on_}" in parts:
                stack.setdefault(f"cloth_{x_}", []).append(f"cloth_{on_}")
            x_ = over_.get(x_)
    return stack


def write_glb(path: Path, name: str, parts: dict, atlases: list[tuple[str, dict[str, Path]]],
              prefabs: dict | None = None, looks: dict | None = None, rig: dict | None = None,
              extra_ext: dict | None = None, external: bool = False):
    """external: the images are referenced by file name (they lie beside the GLB) instead of embedded: several GLBs
    (LOD tiers) share one set of maps. One mesh per part, one material per atlas: atlases is [(atlas name, {basecolor, orm, normal, specular: png})]
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
    for p in ([] if external else images):
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
            # specular 0..1 in the texture's alpha; 0.5 = F0 0.04 (dielectric default), as Blender's IOR level: the
            # colour factor 2 maps that back (F0 = 0.04 x 2 x 0.5); KHR_materials_specular allows factors > 1
            "extensions": {"KHR_materials_specular": {"specularTexture": {"index": ti["specular"]},
                                                      "specularFactor": 1.0, "specularColorFactor": [2.0, 2.0, 2.0]},
                           **((extra_ext or {}).get(len(materials)) or {})},
        })
    used = ["KHR_materials_specular"] + sorted({e for x in (extra_ext or {}).values() for e in x} - {"KHR_materials_specular"})
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
            if lk.get("transmission") or lk.get("alpha", 1.0) < 1.0 or lk.get("double_sided"):
                m["doubleSided"] = True
            if lk.get("alpha_cutoff") is not None:  # alpha-tested, both sides drawn (hair cards)
                m["alphaMode"], m["alphaCutoff"] = "MASK", float(lk["alpha_cutoff"])
                m["doubleSided"] = bool(lk.get("double_sided", True))  # (hair cards with their own back faces: False)
                hx_ = (lk.get("extras") or {}).get("hifipushie_hair")
                if not m["doubleSided"] and hx_ is not None and not hx_.get("back_faces"):
                    raise ValueError(f"{pn}: single-sided hair-card material on cards WITHOUT their own back faces: every "
                                     "viewer culls half the cards (the half-sided hair misdiagnosis); double_sided=True, or "
                                     "export the cards with hair.BACK_FACES")
            for e, v in (lk.get("ext") or {}).items():  # further ratified extensions for this part's material
                m["extensions"][e] = v
                if e not in used:
                    used.append(e)
            if lk.get("extras"):
                m["extras"] = lk["extras"]
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
        if p.get("vcolor") is not None:  # a colour per vertex (hair cards: root-to-tip ramp, a value per lock)
            attrs["COLOR_0"] = add(np.ascontiguousarray(np.asarray(p["vcolor"], np.float32)[src]), 34962, 5126, "VEC3")
        if pn in skinned:
            J, W = skinned[pn]
            J, W = np.asarray(J)[src], np.asarray(W, np.float32)[src]
            W = W / W.sum(1, keepdims=True)
            J = np.where(W > 0, J, 0)  # unused slots: joint 0 at weight 0
            attrs["JOINTS_0"] = add(np.ascontiguousarray(J, np.uint8 if nb <= 256 else np.uint16), 34962,
                                    5121 if nb <= 256 else 5123, "VEC4")
            attrs["WEIGHTS_0"] = add(np.ascontiguousarray(W, np.float32), 34962, 5126, "VEC4")
        prim = {"attributes": attrs, "indices": add(idx, 34963, 5125, "SCALAR"), "material": material_of(pn, p)}
        if p.get("shapes"):  # face shapes (faceshapes.py): a morph target per shape, POSITION and NORMAL deltas
            prim["targets"] = [morph(d, n0, n1, src, nrm) for d, n0, n1 in p["shapes"].values()]
        return prim

    def morph(d, n0, n1, src, nrm):
        """One morph target: per glTF vertex the move (Blender -> glTF axes) and the turn of its own normal (the
        vertex normal's turn from the neutral to the target). Sparse accessors: a face shape moves a few percent of
        a body's vertices."""
        dp = (np.asarray(d, np.float64)[src] @ _Z_TO_Y.T).astype(np.float32)
        nn = _safe_unit(nrm.astype(np.float64) @ _Z_TO_Y, [0.0, 0.0, 1.0])  # back to Blender axes, as n0/n1
        from .faceshapes import turn
        dn = ((turn(nn, n0[src], n1[src]) - nn) @ _Z_TO_Y.T).astype(np.float32)
        return {"POSITION": sparse(dp, True), "NORMAL": sparse(dn)}

    def sparse(data, minmax=False):
        rows = np.flatnonzero(np.abs(data).max(1) > 1e-7).astype(np.uint32)
        acc = {"componentType": 5126, "count": len(data), "type": "VEC3"}
        if minmax:
            acc["min"], acc["max"] = data.min(0).tolist(), data.max(0).tolist()
        if len(rows):  # (none: an accessor without a buffer view is all zeros)
            vi = add(rows, None, 5125, "SCALAR")
            vv = add(np.ascontiguousarray(data[rows]), None, 5126, "VEC3")
            accessors.pop()
            accessors.pop()
            acc["sparse"] = {"count": len(rows), "indices": {"bufferView": len(views) - 2, "componentType": 5125},
                             "values": {"bufferView": len(views) - 1}}
        accessors.append(acc)
        return len(accessors) - 1
    prefabs = prefabs or {}
    in_prefab = {pn for d in prefabs.values() for pn in d["parts"]}
    skins, top = [], []
    if nb:  # the armature: a node per bone at its head, relative to its parent's head; the skin's joints
        bones = rig["bones"]
        base = len(nodes)
        head = np.array([_Z_TO_Y @ np.asarray(b["head"], float) for b in bones])
        ibm = np.tile(np.eye(4, dtype=np.float32), (nb, 1, 1))
        ibm[:, :3, 3] = -head  # bind pose: every joint unrotated at its head
        for i, b in enumerate(bones):
            ref = head[b["parent"]] if b["parent"] >= 0 else np.zeros(3)
            nodes.append({"name": b["name"], "translation": (head[i] - ref).tolist()})
            tw = b.get("twist")
            if tw:  # a twist bone (rig.py): a leaf whose local +Y is its segment's axis, so a driver sets "turn
                # about Y by share x the driver's roll"; what to drive it from is in its extras
                a = _Z_TO_Y @ np.asarray(tw["axis"], float)
                q = _arc_quat(np.array([0.0, 1.0, 0.0]), a)
                R = _quat_matrix(q)
                nodes[-1]["rotation"] = [float(x) for x in q]
                nodes[-1]["extras"] = {"hifipushie_twist": {
                    "driver": tw["driver"], "mode": tw["mode"], "share": tw["share"], "station": tw["station"],
                    "axis_local": [0.0, 1.0, 0.0], "axis_parent": [round(float(x), 6) for x in a]}}
                ibm[i, :3, :3] = R.T
                ibm[i, :3, 3] = -R.T @ head[i]
            bd = b.get("bend")
            if bd:  # a bend helper (rig.py): rests unrotated like the joint it follows; driven by BEND_RECIPE
                nodes[-1]["extras"] = {"hifipushie_bend": {"driver": bd["driver"], "share": bd["share"]}}
        for i, b in enumerate(bones):
            if b["parent"] >= 0:
                nodes[base + b["parent"]].setdefault("children", []).append(base + i)
        nodes.append({"name": "rig", "children": [base + i for i, b in enumerate(bones) if b["parent"] < 0]})
        top.append(len(nodes) - 1)
        skins.append({"name": f"{name}_rig", "joints": list(range(base, base + nb)), "skeleton": len(nodes) - 1,
                      "inverseBindMatrices": add(np.ascontiguousarray(ibm.transpose(0, 2, 1)).reshape(nb, 16),
                                                 None, 5126, "MAT4")})
    for pn, p in parts.items():
        if pn in in_prefab:
            continue
        # (headbody) a part written as SEVERAL meshes on the one skeleton (a native head and its body): p["meshes"] =
        # {mesh name: triangle mask}. Each takes its triangles' corners of the SAME arrays, so the vertices of a shared
        # edge loop (the neck's seam ring) are written twice with identical position, normal, tangent, uv and weights:
        # no crack in any pose, no shading step. Morph targets go to the meshes named in p["shape_meshes"] only.
        subs = [(pn, p)]
        if p.get("meshes"):
            subs = []
            for mn, tm in p["meshes"].items():
                cm = np.repeat(np.asarray(tm, bool), 3)
                q = {**p, "corner_vert": p["corner_vert"][cm], "uv": p["uv"][cm], "normal": p["normal"][cm],
                     "tangent": p["tangent"][cm], "sign": p["sign"][cm]}
                if mn not in (p.get("shape_meshes") or [mn]):  # (pose correctives go on every mesh of the part)
                    q["shapes"] = {k: v for k, v in (q.get("shapes") or {}).items() if k.startswith("corr_")}
                    if not q["shapes"]:
                        q.pop("shapes")
                subs.append((mn, q))
        for mn, q in subs:
            meshes.append({"name": mn, "primitives": [primitive(q, pn)]})
            if q.get("shapes"):  # names in extras.targetNames (the glTF convention engines and Blender read)
                meshes[-1]["weights"] = [0.0] * len(q["shapes"])
                meshes[-1]["extras"] = {"targetNames": list(q["shapes"])}
            nodes.append({"name": f"{name}_{mn}", "mesh": len(meshes) - 1, **({"skin": 0} if pn in skinned else {})})
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
           "images": ([{"uri": Path(p).name} for p in images] if external else
                      [{"bufferView": i, "mimeType": "image/png"} for i in range(len(images))]),
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


def head_body_meshes(spec: dict, parts: dict, topo: dict, log: list) -> dict | None:
    """(headbody) A native head (base.head.attach "native") and its body as TWO meshes sharing the neck's seam ring:
    sets parts[body]["meshes"] = {"head": triangles of GNM's vertices, "body": the rest} for write_glb when the body's
    low poly is its own quads (parts.body.topology "wrap": every vertex knows its GNM vertex). base.head.mesh
    "welded" keeps one mesh. -> {"part", "report": {mesh: {"triangles", "vertices"}, "seam": {"vertices", "gap",
    "normal_deg"}}} or None."""
    from . import onemesh
    b = spec.get("base") or {}
    if not onemesh.native(b):
        return None
    mode = (b.get("head") or {}).get("mesh", "separate")
    if mode not in ("separate", "welded"):
        raise ValueError('base.head.mesh: "separate" (head and body meshes sharing the seam ring; default) or "welded"')
    if mode == "welded":
        return None
    for pn, (tp, _) in topo.items():
        p = parts.get(pn)
        z = np.load(tp)
        if p is None or "gnm" not in z.files:
            continue
        gi = p.get("gnm_index")  # (face shapes checked it against the low poly before they moved anything)
        if gi is None and len(z["verts"]) == len(p["verts"]) and np.allclose(np.asarray(p["verts"], float), z["verts"], atol=1e-5):
            gi = z["gnm"]
        if gi is None or len(gi) != len(p["verts"]):
            log.append(f"WARNING head / body meshes: {pn}'s low poly isn't its topology's vertices "
                       f"({len(p['verts'])} against {len(z['verts'])}): written as one mesh")
            return None
        gi = np.asarray(gi, int)
        tri = np.asarray(p["corner_vert"]).reshape(-1, 3)
        head = (gi[tri] >= 0).all(1)
        p["meshes"] = {"head": head, "body": ~head}
        p["shape_meshes"] = ["head"]
        vh, vb = np.unique(tri[head]), np.unique(tri[~head])
        ring = np.intersect1d(vh, vb)
        # the ring's corners: the same vertex must carry the same normal on both sides (it does when the low poly's
        # normals are smooth there: both meshes read one array). Reported, so a hard edge at the seam is seen.
        cv = np.asarray(p["corner_vert"])
        N = np.asarray(p["normal"], float)
        hm = np.repeat(head, 3)
        worst = 0.0
        for v in ring:
            a_, b_ = N[(cv == v) & hm], N[(cv == v) & ~hm]
            if len(a_) and len(b_):
                worst = max(worst, float(np.degrees(np.arccos(np.clip((a_[:, None] * b_[None]).sum(-1) /
                            (np.linalg.norm(a_, axis=1)[:, None] * np.linalg.norm(b_, axis=1)[None] + 1e-12), -1, 1)).max())))
        rep = {"head": {"triangles": int(head.sum()), "vertices": int(len(vh))},
               "body": {"triangles": int((~head).sum()), "vertices": int(len(vb))},
               "seam": {"vertices": int(len(ring)), "gap": 0.0, "normal_deg": round(worst, 3)}}
        log.append(f"{pn}: written as two meshes on the one skeleton: head {rep['head']['triangles']} triangles (GNM's "
                   f"topology, face shapes), body {rep['body']['triangles']}; they share the seam ring's {len(ring)} "
                   f"vertices (same position, normal, uv, weights: largest normal difference across it {worst:.2f} deg)")
        return {"part": pn, "report": rep}
    log.append("WARNING head / body meshes: the body is decimated (no seam ring in it): one mesh. Set "
               "parts.body.topology \"wrap\" for the two-mesh export")
    return None


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


def export(name: str, out_dir: Path, *args, **kw) -> dict:
    """See `_export`; holds the machine's heavy-job slot (`resources.heavy`) so exports don't stack up."""
    from . import resources
    prog = store.HOME / name / "progress.log"

    def waiting(msg: str):  # the wait shows where the export's progress does (an oxidegen artist's task progress)
        print(msg, flush=True)
        try:
            with open(prog, "a") as f:
                f.write(msg + "\n")
        except OSError:
            pass
    with resources.heavy(f"export {name}", kind="export_asset", model=name, log=waiting,
                         gb=export_gb(store.load(name), name)):
        from . import faceshapes
        notes = []
        with faceshapes.character_fits(store.load(name), notes, store._dir(name)):  # per-character fits from the spec, not the env
            for m in notes:
                waiting(m)
            res = _export(name, out_dir, *args, **kw)
        if isinstance(res, dict) and isinstance(res.get("log"), list):
            res["log"][:0] = notes
        return res


CLOTH_BUDGET_ROUNDS = 4  # decimation rounds to bring the garments under cloth_triangles


def decimate_cloth(cparts: list, cloth_triangles: int, log: list) -> list:
    """The garments [(name, part, files)] decimated together to at most `cloth_triangles` (one ratio for all)."""
    from . import lods as lodmod
    n_c = sum(len(cp["corner_vert"]) // 3 for _, cp, _ in cparts)
    ratio_c = cloth_triangles / n_c
    got = n_c
    msgs, dec = [], list(cparts)
    for round_c in range(CLOTH_BUDGET_ROUNDS):  # parts' floors (made pieces, held borders) keep more than the
        # ratio asks (Garrett v5: 27,032 of 25,000): the ratio is scaled by the overshoot until the sum fits
        dec, msgs = [], []
        for pn_c, cpart, cfiles in cparts:
            q, _, r_ = lodmod.lod_part(cpart, None, ratio_c)
            msgs.append(f"cloth {pn_c}: {r_['triangles0']} -> {r_['triangles']} triangles (cloth_triangles "
                        f"{cloth_triangles} over {n_c}, ratio {ratio_c:.3f})")
            dec.append((pn_c, q, cfiles))
        got = sum(len(q["corner_vert"]) // 3 for _, q, _ in dec)
        if got <= cloth_triangles:
            break
        ratio_c *= cloth_triangles / got * 0.99
    log.extend(msgs)
    if got > cloth_triangles:
        log.append(f"WARNING cloth: {got} triangles after {CLOTH_BUDGET_ROUNDS} rounds, over cloth_triangles "
                   f"{cloth_triangles}")
    return dec


ROLE_HAIR_TIER = {"hero": "hero", "main_npc": "main", "secondary_npc": "npc", "crowd": "far"}  # LOD0 card tier by role


HEAD_KEEP_FROM_BUILD = ("attach",)  # base.head keys the build keeps over the approved head's (how it joins the body)


def approved_head(spec: dict, log: list, approved_path: Path | None = None) -> dict:
    """(Garrett s7, coordinator's rule) spec base.head_approved = an approval key in workspace/approved.json (e.g.
    "head/garrett" -> gp_h6c): the export's head GEOMETRY is that approved model's base.head (the build keeps only
    HEAD_KEEP_FROM_BUILD); skin TEXTURES still come from the build's skin. Garrett v6 carried s21's lid_fold and shape
    (eye_bag, cheek_flat), which Joe never approved: the face drifted. Every key dropped or changed is logged; an
    unknown key / missing model raises (never a silent fallback to the unapproved head)."""
    key = (spec.get("base") or {}).get("head_approved")
    if not key:
        return spec
    from . import store
    ap = approved_path or (store.HOME / "approved.json")
    ent = (json.loads(Path(ap).read_text()).get("approved") or {}).get(key)
    if not ent or not ent.get("model"):
        raise ValueError(f"base.head_approved {key!r}: no such approval in {ap}")
    sp_ = Path(ap).parent / ent["model"] / "spec.json"
    head0 = (json.loads(sp_.read_text()).get("base") or {}).get("head")
    if not head0:
        raise ValueError(f"base.head_approved {key!r}: {sp_} has no base.head")
    build = spec["base"].get("head") or {}
    head = {**head0, **{k: build[k] for k in HEAD_KEEP_FROM_BUILD if k in build}}
    diff = sorted(k for k in set(build) | set(head) if build.get(k) != head.get(k))
    log.append(f"head: the APPROVED head {key} = {ent['model']}'s base.head; the build's "
               + (f"{', '.join(diff)} replaced / dropped" if diff else "head was already it"))
    out = dict(spec)
    out["base"] = {**spec["base"], "head": head}
    approved_folds = (json.loads(sp_.read_text()).get("skin") or {}).get("folds") or {}
    out = fold_form_gate(out, log, approved_folds)
    from . import skin_layers   # (s9) the stack's lid shading / blink map re-baked on the head that ships
    return skin_layers.stack_on_head(out, log)


# The GAME rig as blender_game.light_rig(None) builds it, in blender_scene's "lighting" format (world colour sRGB): a stage
# render meant to be compared with the shipped GLB's game render must use THIS, view transform included. (Garrett s12:
# the stage's "game" frames used AgX while blender_game renders Khronos PBR Neutral (since 2026-10-16): the GLB read
# lighter and ~2x yellower (cheek b* 8.6 -> 15.0, forehead L* 68 -> 79) and its lid band ~10 L* darker, all of it the
# view transform; with the same view the GLB matched the stage within ~1 L* / 1 b* (photo light: 80.7 vs 80.8).)
GAME_LIGHT = {"lights": [{"dir": [-1.0, -1.2, 1.4], "energy": 3.0, "angle": 2.0, "color": [1.0, 1.0, 1.0]},
                         {"dir": [1.4, -0.6, 0.6], "energy": 1.0, "angle": 10.0, "color": [1.0, 1.0, 1.0]},
                         {"dir": [0.3, 1.5, 1.0], "energy": 1.5, "angle": 3.0, "color": [1.0, 1.0, 1.0]}],
              "world": {"color": [0.584, 0.600, 0.631], "strength": 0.8}, "view": "Khronos PBR Neutral", "exposure": 0.0}
FACE_LIGHT_TOL = {"lid-cheek": 5.0, "under-cheek": 3.0}  # L* (CIE) the shipped head may differ from the approved stage render
FACE_LIGHT_TEX_RATIO = 1.4  # forehead fine-texture (high-pass L* std) the shipped head may have over the approved render


def _lstar(a: np.ndarray) -> np.ndarray:
    c = np.asarray(a, float)[..., :3] / 255.0
    c = np.where(c > 0.04045, ((c + 0.055) / 1.055) ** 2.4, c / 12.92)
    Y = c @ np.array([0.2126, 0.7152, 0.0722])
    return np.where(Y > 0.008856, 116 * np.cbrt(Y) - 16, 903.3 * Y)


def face_light(img, eyes=None) -> dict:
    """(Garrett s10, coordinator) lightness of a FRONT eyes render (the eyes in the middle band, brows and cheeks in
    frame): the upper-lid band and the under-eye band against the cheek (L* differences, both eyes averaged) and the
    forehead's fine texture (std of L* minus its blur at 1/25 of the eye distance: grooves / wrinkles). Eyes are the
    darkest blurred point in each half between 40 and 75% of the height (the pupils), or given (px). Regions are boxes
    in eye-distance units d: lid -0.15..-0.07 d above the pupil, under +0.08..+0.2 d, cheek +0.3..+0.42 d (each
    +-0.15 d wide), forehead -0.85..-0.6 d, +-0.4 d about the midpoint."""
    from scipy import ndimage as nd
    L = _lstar(np.asarray(Image.open(img).convert("RGB")) if isinstance(img, (str, Path)) else np.asarray(img))
    h, w = L.shape
    if eyes is None:
        b = nd.gaussian_filter(L, w / 150)
        eyes = []
        for x0, x1 in ((0, w // 2), (w // 2, w)):
            s_ = b[int(.4 * h):int(.75 * h), x0:x1]
            y, x = np.unravel_index(np.argmin(s_), s_.shape)
            eyes.append((x + x0, y + int(.4 * h)))
    (x1, y1), (x2, y2) = eyes
    d = float(np.hypot(x2 - x1, y2 - y1))

    def box(A, cx, cy, a, b, c, e):
        return A[max(0, int(cy + c * d)):int(cy + e * d), max(0, int(cx + a * d)):int(cx + b * d)]
    m = {k: float(np.mean([box(L, x, y, a, b, c, e).mean() for x, y in eyes]))
         for k, (a, b, c, e) in {"lid": (-.15, .15, -.15, -.07), "under": (-.15, .15, .08, .2),
                                 "cheek": (-.15, .15, .3, .42)}.items()}
    hp = L - nd.gaussian_filter(L, d / 25)
    tex = float(box(hp, (x1 + x2) / 2, (y1 + y2) / 2, -.4, .4, -.85, -.6).std())
    return {"lid-cheek": m["lid"] - m["cheek"], "under-cheek": m["under"] - m["cheek"], "forehead_tex": tex,
            "eyes": [list(map(int, e)) for e in eyes]}


def face_light_check(stage, shipped, label: str = "") -> list[str]:
    """The shipped head's render against the APPROVED head's stage render through the same camera and light (e.g.
    eyes_v0 photo / game): lid band and under-eye vs cheek within FACE_LIGHT_TOL L*, forehead texture within
    FACE_LIGHT_TEX_RATIO. Lines to log; WARNING lines name the numbers. (Garrett v6 / v7: lid-cheek -33 vs the approved
    -16 under the photo light: the blink map's lid_fold crease + occlusion; forehead 2.1 vs 1.2 in the game rig: s21's
    wrinkles in the normal map.) Eyes are found on the stage render and used for both (same camera). The two renders
    must share the light rig AND the view transform (game: GAME_LIGHT): a different view transform alone moved the
    lid band ~8 L* and the cheek's b* x2 (Garrett s12)."""
    a = face_light(stage)
    b = face_light(shipped, eyes=a["eyes"])
    out = []
    for k, tol in FACE_LIGHT_TOL.items():
        bad = abs(b[k] - a[k]) > tol
        out.append(("WARNING " if bad else "") + f"face light{(' ' + label) if label else ''}: {k} {b[k]:.1f} L* vs the "
                   f"approved render's {a[k]:.1f} (tolerance {tol})" + (": the shipped maps darken / lighten it" if bad else ""))
    bad = b["forehead_tex"] > FACE_LIGHT_TEX_RATIO * max(a["forehead_tex"], 0.5)
    out.append(("WARNING " if bad else "") + f"face light{(' ' + label) if label else ''}: forehead texture "
               f"{b['forehead_tex']:.2f} vs the approved render's {a['forehead_tex']:.2f} (at most x{FACE_LIGHT_TEX_RATIO})"
               + (": grooves / wrinkles the approved head doesn't have (normal map)" if bad else ""))
    return out


FOLD_FORM_MAX_MM = 1.0  # (coordinator, Garrett s8) skin.folds up to this much relief are SKIN detail (grooves, creases);
# more (a roll / bag / cheek mass, a lid's overhang) changes the head's FORM: head geometry, Joe's approval


def fold_form(name: str, v) -> float:
    """The most a skin fold moves the surface, in mm: its groove, its roll (the swell beside it), its platform, at its
    largest amount (a side's amount x the fold's)."""
    from . import skin_folds
    q = skin_folds.options({name: v}).get(name)
    if not q:
        return 0.0
    rl = skin_folds.RELIEF[name]
    a = q["amount"] * max([sd["amount"] for sd in q["sides"].values()] or [1.0])
    return a * max(rl["depth"] * q["depth"], (rl["roll"][2] * q["roll"]) if rl.get("roll") else 0.0,
                   rl["plat"][0] if rl.get("plat") else 0.0)


def fold_form_gate(spec: dict, log: list, approved: dict | None = None) -> dict:
    """(coordinator, Garrett s8) the approved-geometry rule for skin.folds: a fold whose relief is at most
    FOLD_FORM_MAX_MM ships (skin detail); a larger one, unless the approved head carries the same fold, is clamped to
    it (its roll and groove scaled: the crease line stays, the form change goes) with a WARNING naming it."""
    from . import skin_folds
    folds = (spec.get("skin") or {}).get("folds") or {}
    if not folds:
        return spec
    out_f, msgs = {}, []
    for name, v in folds.items():
        mm = fold_form(name, v)
        if mm <= FOLD_FORM_MAX_MM + 1e-9 or (approved or {}).get(name) == v:
            out_f[name] = v
            msgs.append(f"{name} {mm:.2f} mm ok")
            continue
        q = {"amount": float(v)} if isinstance(v, (int, float)) else dict(v)
        rl = skin_folds.RELIEF[name]
        k = FOLD_FORM_MAX_MM / mm
        if rl.get("roll"):
            q["roll"] = float(q.get("roll", 1.0)) * k
        q["depth"] = float(q.get("depth", 1.0)) * min(1.0, k * mm / max(fold_form(name, {**q, "roll": 0.0}), 1e-9))
        out_f[name] = q
        log.append(f"WARNING head: skin.folds.{name} changes the head's FORM ({mm:.2f} mm > {FOLD_FORM_MAX_MM} mm: a roll / "
                   f"bag / overhang is head geometry, not approved): clamped to {fold_form(name, q):.2f} mm for the export "
                   "(Joe approves it into the head, or the skin thread lowers it)")
    if msgs:
        log.append("head: skin.folds within the skin-detail depth: " + ", ".join(msgs))
    return {**spec, "skin": {**spec["skin"], "folds": out_f}}


def hair_tier_default(spec: dict, role: str | None, log: list) -> dict:
    """LOD0's card tier: the groom's hair.export.tier, else the role's (ROLE_HAIR_TIER). Unset, hair.EXPORT_CARDS cut
    the cards to its 12000-triangle budget per lock (Garrett v3 / v4: 96 cards + cap, a helmet, while LOD1-3 got the
    tiers). Only card / strand grooms have tiers; no role keeps the old cut and says so."""
    h = spec.get("hair") or {}
    if h.get("style") not in ("cards", "strands") or (h.get("export") or {}).get("tier"):
        return spec
    tier = ROLE_HAIR_TIER.get(role or "")
    if tier is None:
        log.append("WARNING hair: no hair.export.tier and no role: LOD0 cards cut to hair.EXPORT_CARDS' budget, not a "
                   "card tier (pass role= or set hair.export.tier)")
        return spec
    log.append(f"hair: LOD0 card tier {tier!r} from role {role!r} (hair.export.tier unset)")
    return {**spec, "hair": {**h, "export": {**(h.get("export") or {}), "tier": tier}}}


def _export(name: str, out_dir: Path, triangles: int | None = None, texture: int = 2048, resolution: int = 256,
            atlases: int = 1, texel_density: float | None = None, instancing: bool = True, rig: bool | dict = False,
            fbx: bool = False, face_shapes: bool | list | None = None, asset_name: str | None = None,
            lods: bool | list | None = None, cloth_triangles: int | None = None,
            cull_under_cloth: bool = True, role: str | None = None, correctives: bool = True,
            cull_poses: list | str | None = None) -> dict:
    """Build, decimate + unwrap, bake every map, write PNGs, <name>.glb and <name>.json into out_dir.
    asset_name: what the files, nodes, meshes and materials are called (default: the model's name): an engine's
    importer and tools key on them (s0urc3's Garrett is model rg_garrett, asset "garrett": garrett_body, ...).
    Per part (spec["parts"][p]): "triangle_weight" and "texel_density" (relative, default 1) scale its share of
    the triangles and its texels per metre; "atlas" (any name) puts it on an atlas of its own; "uv": "planar" gives
    a swappable flat surface (a dial, a sign, a screen) its own material and upright 0..1 planar UVs.
    texel_density (texels per metre): atlases are opened as needed to give every part that (x its own weight) at
    most `texture`^2 each, each atlas the smallest power of two that holds its parts. Without it, `atlases` (n)
    atlases of `texture`^2 split the parts by load.
    instancing: prefabs with 2+ instances are one mesh and one set of texels, placed by a node per instance
    (prefabs.<p>.export = "unique" bakes a prefab's instances into the scene instead). `triangles` counts the
    triangles drawn (a prefab's once per instance); the file holds fewer. With instancing every instance is a
    movable asset (a prefab of one instance too), as in the Blender scene. The paint and AO maps are baked by
    Cycles from the model's Blender scene (`scene_maps`; AO is each asset's own, as an engine expects).
    face_shapes: True (every ARKit shape faceshapes.py makes) or a list of names: morph targets on the parts that
    move with the face (faceshapes.apply), the neutral's mouth closed; listed per part in the json.
    lods: True (lods.LOD_RATIOS) or a list of shares of LOD0's triangles: <asset>_LOD<k>.glb beside the GLB, the same
    skeleton, weights, face shapes and atlas (they reference LOD0's maps by file name); hair cards by whole layers.
    cloth_triangles: the simulated garments together decimated to this many triangles (their sim mesh, two-sided, is
    10-40k each: Tess's jeans 38k, sweater 28k); None keeps the sim mesh. cull_under_cloth: the skin (and shells on
    it without a garment fit, socks) the garments cover is left out (under_cloth_keep), a rim kept at the openings."""
    log = _Log(name)
    t = time.time()
    rb = None
    if role:  # the budgets profile (budgets.json, docs/notes/budgets.md): what this role may cost; explicit arguments win
        from . import budgets as budgetmod
        rb = budgetmod.role(role)
        bp_ = rb["parts"]
        if triangles is None:  # what the joint decimation spends: the body (head + body meshes) and the small parts
            triangles = sum(int(bp_[k]["default"]) for k in ("head", "body", "eyes_mouth_lashes", "accessories") if k in bp_)
        if cloth_triangles is None and "clothing" in bp_:
            cloth_triangles = int(bp_["clothing"]["default"])
        texture = min(texture, int((rb.get("textures") or {}).get("max_map", texture)))
        if texel_density is None:  # atlases sized by the role's texel density (the face's higher density is the
            # model's parts.<skin>.texel_focus; separate head / body texture SETS need the native head unwrapped as its
            # own part: not built, the two meshes share one atlas)
            texel_density = float(((rb.get("textures") or {}).get("texel_density_px_per_m") or {}).get("body", 1024))
        if lods is None:
            lods = True
        log.append(f"budgets: role {role!r}: triangles {triangles} (head + body + eyes/mouth/lashes + accessories), "
                   f"clothing {cloth_triangles}, maps <= {texture}, LOD0 total {rb['lod0_triangles']['default']}")
    if triangles is None:
        triangles = 15000
        log.append("WARNING budgets: no role given and no triangles: 15000 (not a stated budget; pass role=)")
    spec = store.load(name)
    if (spec.get("base") or {}).get("head_approved"):  # (Garrett s7) the head geometry must BE the approved head's: a
        # gate, not a swap (geometry is built from the stored model); compose the spec with approved_head first
        lg_ = []
        ah_ = approved_head(spec, lg_)
        h_ = ah_["base"]["head"]
        if h_ != spec["base"].get("head"):
            raise ValueError(f"{name}: base.head is not the approved head ({lg_[0]}): write approved_head(spec)'s "
                             "head into the model first")
        if (ah_.get("skin") or {}).get("folds") != (spec.get("skin") or {}).get("folds"):  # (s8: folds that change form)
            raise ValueError(f"{name}: skin.folds change the head's form ({'; '.join(m for m in lg_ if 'WARNING' in m)}): "
                             "write approved_head(spec)'s skin.folds into the model first")
        if (ah_.get("skin") or {}).get("stack") != (spec.get("skin") or {}).get("stack"):  # (r63) this gate's result
            # is not what ships (textures come from the stored model): the lid layers re-baked by stack_on_head must be
            # IN the model, or the blink map / lid shading of the lid_fold head ships (Tess rc2o did exactly that)
            raise ValueError(f"{name}: skin.stack was measured on another head "
                             f"({'; '.join(m for m in lg_ if m.startswith('skin stack'))}): write approved_head(spec)'s "
                             "skin.stack into the model first")
        log.append(f"head: = the approved head {spec['base']['head_approved']} (checked)")
        for m_ in lg_:  # (append: the export log prints on append, not extend)
            if "skin.folds" in m_:
                log.append(m_)
    aname = asset_name or name
    from .base import part_defs
    defs = part_defs(spec)  # (the base's implied parts too: a clear cornea's lens)
    fine, tri_focus = {}, []
    if face_shapes:  # say now, not after the bake, that the face can't take them; mesh the slit open; keep
        # triangles at the lids and lips
        from . import faceshapes
        faceshapes.names_of(face_shapes)
        fface = faceshapes.face_of(spec)
        fine, tri_focus = fface.voxels(), fface.tri_focus()
    out_dir.mkdir(parents=True, exist_ok=True)
    ctx = split(spec, resolution, instancing, log, min_share=1, voxels=fine)
    if rig:  # parts bound to a joint of their own (parts.<p>.rig_bone) move apart from the rest: what they cover
        # at rest is seen in a pose (the golfer's shorts had a hole where the hip bag sat, shown by a lifted thigh)
        ctx["apart"] = {pn: (defs.get(ctx["origin"][pn]) or {}).get("rig_bone") for pn in ctx["streams"]}
    for pn, v in fine.items():
        if ctx["frames"].get(pn) and ctx["frames"][pn][1] <= v:
            log.append(f"{pn}: meshed at {ctx['frames'][pn][1] * 1000:.2f} mm for the face shapes (the lips' slit, teeth)")
    origin = ctx["origin"]
    tm = time.time()
    high = mesh_parts(ctx, out_dir / "high.npz")
    log.append(f"meshed {len(ctx['streams'])} parts in {time.time() - tm:.1f}s (scene voxel {ctx['voxel'] * 1000:.1f} mm)")
    own_surface = None
    if face_shapes and getattr(fface, "gnm_mouth", False):  # GNM's own teeth and tongue lie behind the closed lips
        from . import base as basemod
        mp = basemod.gnm_mouth(fface.head)
        pts = {k: basemod._piece_points(mp[k]["verts"], mp[k]["faces"])["verts"] for k in ("teeth_upper", "teeth_lower", "tongue")}
        own_surface = {basemod.TEETH_PARTS[0]: pts["teeth_upper"], basemod.TEETH_PARTS[1]: pts["teeth_lower"],
                       "tongue": pts["tongue"]}
        own_mouth_meshes(high, mp, log)
        # (their own vertices ARE the surface: every face kept, whatever covers the rows in the neutral)
        own_surface.update({basemod.TEETH_PARTS[0]: np.asarray(mp["teeth_upper"]["verts"], float),
                            basemod.TEETH_PARTS[1]: np.asarray(mp["teeth_lower"]["verts"], float),
                            "tongue": np.asarray(mp["tongue"]["verts"], float)})
    prune_hidden(ctx, high, log, own_surface)
    if texel_density:
        split_big(high, ctx, {pn: _weight(defs, origin[pn], "texel_density") * texel_density for pn in ctx["streams"]},
                  texture, log)
    areas = part_areas(high)

    def w(pn, key):
        return _weight(defs, origin[pn], key)
    focus = {pn: focus_regions(spec, origin[pn]) for pn in areas}
    # image decals keep their own resolution: their density relative to the part's (asked, or what an atlas of
    # `texture` holds over every part). A prefab's part (or a split slab) takes the decals reaching its own mesh: it
    # is unwrapped where its bake instance stands, as the scene paints it
    guess = texture * np.sqrt(FILL / max(sum(areas.values()), 1e-9))
    with np.load(high) as z:
        hv, hp, hnames = z["verts"], z["part"], [str(n) for n in z["part_names"]]
    for pn in areas:
        box = None
        if pn != origin[pn] and pn in hnames:
            pv = hv[hp == hnames.index(pn)]
            box = (pv.min(0) - 0.01, pv.max(0) + 0.01) if len(pv) else None
        if pn == origin[pn] or box is not None:
            dec = decal_focus(spec, origin[pn], w(pn, "texel_density") * (texel_density or guess), box)
            if dec:
                focus[pn] = focus[pn] + dec
                log.append(f"{pn}: texel focus over {len(dec)} image decal(s), x{', x'.join(f'{d[4]:.1f}' for d in dec)}")
    rel ={pn: w(pn, "texel_density") * (texel_density or 1.0) for pn in areas}
    loads = texture_loads(high, rel, focus)
    fixed = {pn: str(defs[origin[pn]]["atlas"]) for pn in areas if (defs.get(origin[pn]) or {}).get("atlas") is not None}
    # parts.<p>.uv = "planar": a swappable surface (a clock's dial, a sign, a screen) gets its own material and 0..1
    # planar UVs, so an engine swaps its texture by one property (s0urc3: the dial needed a custom UV shader)
    planar = {pn for pn in areas if (defs.get(origin[pn]) or {}).get("uv") == "planar"}
    for pn in planar:
        fixed.setdefault(pn, f"planar_{pn}")
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
    topo = topology_parts(spec, ctx, out_dir, log)
    fill = FILL
    for attempt in range(2):
        group = density_groups(units, loads, fixed, texture, fill) if texel_density else atlas_groups(
            loads, fixed, atlases)
        names = sorted(set(group.values()), key=lambda g: (not g.isdigit(), int(g) if g.isdigit() else 0, g))
        sizes = {ai: min(texture, _pow2(np.sqrt(sum(loads[pn] for pn in areas if group[pn] == an) / fill)))
                 if texel_density else texture for ai, an in enumerate(names)}
        cfg = {pn: {"weight": w(pn, "triangle_weight"), "density": w(pn, "texel_density"),
                    "atlas": names.index(group[pn]), "focus": focus[pn], "split": pn in ctx.get("split", {}),
                    "copies": len(ctx["prefabs"][pf_of[pn]]["instances"]) if pn in pf_of else 1,
                    **({} if _min_triangles(defs, origin[pn]) is None else  # (absent: cached decimations stay valid)
                       {"min": _min_triangles(defs, origin[pn])}),
                    **({} if _max_triangles(defs, origin[pn]) is None else {"max": _max_triangles(defs, origin[pn])}),
                    **({"fixed": topo[pn][0], "fixed_sum": topo[pn][1]} if pn in topo else {})} for pn in areas}
        t1 = time.time()
        from . import lashes as _lashes  # the lash ribbons come out of the same budget (their own count, fixed)
        lash_tris = _lashes.triangles(spec)
        if lash_tris:
            log.append(f"lashes: {lash_tris} triangles of the {triangles} budget")
        parts, binfo = lowpoly(high, out_dir / "lowpoly.npz", cfg, max(triangles - lash_tris, triangles // 2), sizes,
                               ctx["voxel"], tri_focus)
        for pn in planar & set(parts):
            parts[pn].update(planar_uvs(parts[pn]))
            log.append(f"{pn}: own material, planar 0..1 UVs (uv: planar)")
        if not texel_density:
            break
        # the size each atlas needs for every part to get its density, now that it's packed
        ts = texel_sizes(parts, sizes, {pn: focus.get(pn) or [] for pn in parts})

        def needs(pn, ai):  # the part's own density, and each focus region's (a decal covering a whole mug: the
            # part's average is the focus's, and sizing the atlas by it alone dropped the focus)
            yield sizes[ai] * ts[pn]["mm_per_texel"] * rel[pn] / 1000
            for f, mm in zip(focus.get(pn) or [], ts[pn].get("focus_mm_per_texel") or []):
                if mm > 0:  # (0: no face of this part in the region)
                    yield sizes[ai] * mm * rel[pn] * f[4] / 1000
        need = {ai: max(x for pn, p in parts.items() if p["atlas"] == ai for x in needs(pn, ai))
                for ai in range(len(names))}
        over = [ai for ai in need if need[ai] > 1.05 * texture and len({pf_of.get(pn, pn) for pn, p in parts.items()
                                                                         if p["atlas"] == ai}) > 1]
        if over and attempt == 0:
            fill = 0.95 * min(sum(ts[pn]["uv_fill"] for pn, p in parts.items() if p["atlas"] == ai) for ai in over)
            log.append(f"atlases {[names[ai] for ai in over]} came out too full for {texel_density:g} texels/m at "
                       f"{texture}: regrouping for a pack fill of {fill:.0%}")
            continue
        sizes = {ai: min(texture, _pow2(0.97 * need[ai])) for ai in need}
        break
    hid_tris = {pn: hide_export_part(ctx, pn, parts[pn], log) for pn in parts}  # (parts.<p>.hides: also after a
    # template wrap or a decimation, which bring back what the high mesh had already lost)
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
                      "triangle_weight": cfg[pn]["weight"],
                      **({"uv": "planar", "material": f"{aname}_{names[p['atlas']]}_material"} if pn in planar else {})}
        if pn in pf_of:
            report[pn]["prefab"] = pf_of[pn]
        if hid_tris.get(pn):
            report[pn]["hidden_dropped"] = hid_tris[pn]
        if "focus_mm_per_texel" in tsz[pn]:
            report[pn]["focus_mm_per_texel"] = tsz[pn]["focus_mm_per_texel"]
        des = _designed_interior(topo.get(pn), p["verts"], lid_fold=((spec.get("base") or {}).get("head") or {}).get("lid_fold"))
        if des is not None:  # (bake: the interior's texels keep the low poly's own surface)
            p["designed"] = _designed_interior(topo.get(pn), p["verts"], creases=False)
        q = mesh_quality(p["verts"], p["corner_vert"].reshape(-1, 3), ctx["streams"][pn], designed=des)
        spots = q.pop("spots")
        for other, st in ctx["streams"].items():  # what lies inside another part is never seen (the skin running
            if other != pn and len(spots):       # on into the socket behind an eyeball, a tooth's root)
                spots = spots[sdf.field_at(st, spots, clip=False) > 0]
        if face_shapes and len(spots) and ctx["origin"][pn] == fface.slit_part:
            # the mouth's interior (slit walls, the bag's corners) folds at a game budget and is behind the lips:
            # counted, not part of the tear alarm (Garrett's bag read "TORN OR TANGLED at eye_front.L (12)")
            inm = fface.inside_mouth(spots, ctx["streams"][pn])
            if inm.any():
                q["inside_mouth"] = int(inm.sum())
                spots = spots[~inm]
        where = defect_regions(spots, spec)
        if (defs.get(ctx["origin"][pn]) or {}).get("folds"):  # parts.<p>.folds = true: folded by design (a turned
            where = []                                         # collar, a cuff, pleats): counts stay, no alarm
        if where:
            q["defects_by_joint"] = dict(where)
        report[pn]["quality"] = q
        vx_mm = ctx["frames"][pn][1] * 1000
        warn = [w for w, bad in ((f"p99 {q['err_mm_p99']:.1f} mm from the surface (> 4 voxels: bridged gaps or "
                                  f"cut corners; raise its triangle_weight)", q["err_mm_p99"] > 4 * vx_mm),
                                 (f"{q['folds']} folded edges", q["folds"] > 0),
                                 (f"{q.get('turned', 0)} faces turned against the surface", q.get("turned", 0) > 0),
                                 ("TORN OR TANGLED at " + ", ".join(f"{j} ({k})" for j, k in where[:4])
                                  + ": folded edges / turned faces in a cluster; look at it in clay "
                                    "(rig(glb=..., focus=...)) before shipping", bool(where)),
                                 (f"{q['non_manifold_edges']} non-manifold edges", q["non_manifold_edges"] > 0))
                if bad]
        log.append(f"  {pn} quality: error p50/p99/max {q['err_mm_p50']}/{q['err_mm_p99']}/{q['err_mm_max']} mm, "
                   f"{q['slivers']} slivers, {q['open_edges']} open edges"
                   + (f" ({q['inside_mouth']} of the folds / turned faces are inside the mouth)" if q.get("inside_mouth") else "")
                   + (f": WARNING {'; '.join(warn)}" if warn else ""))
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
    skin_recipe = None
    if spec.get("skin"):
        # (r65, coordinator) the skin's micro detail (pores, cells, lines, the lip lines) is BAKED into the part's own
        # maps: as tiling maps in the shading json alone, neither plain glTF viewers nor blender_game apply them, and
        # the lower lip shipped as one smooth, unbroken highlight (game_ready.md r64). The tiling maps still ship, as
        # an optional close-up extra (normal only: their tint / roughness are in the maps already).
        from . import skin as skinmod
        skin_recipe = skinmod.export_recipe(spec, out_dir, name, baked=BAKE_SKIN_DETAIL)
        ctx["bake_detail"] = BAKE_SKIN_DETAIL or not (skin_recipe and skin_recipe["detail"])
        if skin_recipe and skin_recipe["detail"]:
            log.append("skin: micro detail " + ("baked into the part's maps; also written as tiling normal maps (close-up "
                       "extra, normal only) (" if BAKE_SKIN_DETAIL else "left out of the baked maps and written as "
                       "tiling normal maps (") + ", ".join(d["normal"] for d in skin_recipe["detail"]) + "): the recipe "
                       "is in the json and the skin material's extras")
    if face_shapes and getattr(fface, "gnm_mouth", False):  # the lips' inner rolls: hidden in the closed scene,
        inner_paint(parts, topo, fface.head, log)            # painted on the low poly's own triangles
    face_keep_paint(parts, topo, log)
    if spec.get("skin"):
        ctx["lip_floor"] = (spec, (spec.get("skin") or {}).get("part", "body"))
    # (s14) the finest texel any part bakes at: the bake prefilters paint images finer than its sample spacing
    ctx["texel_m"] = min((min([r["mm_per_texel"]] + list(r.get("focus_mm_per_texel") or [])) for r in report.values()
                          if r.get("mm_per_texel")), default=0.0) / 1000.0
    given = scene_maps(name, parts, sizes, ctx, resolution, log)
    ek_ = (spec.get("base") or {}).get("eyes")
    ctx["ao_off"] = [ek_] if isinstance(ek_, str) else []
    for ai, an in enumerate(names):
        stem = aname if len(names) == 1 else f"{aname}_{an}"
        if len(names) > 1:
            log.append(f"atlas {an}:")
        res = bake(parts, sizes[ai], ctx, log, ai, given[ai])
        maps = res["maps"]
        for pn, sh in res.get("lip_astray", {}).items():
            report[pn]["lip_astray"] = {"share": round(sh, 4), "warn": sh > LIP_ASTRAY_WARN}
        for pn, p in parts.items():  # seams: does the baked colour run on across each chart border? (~1 = yes)
            if p["atlas"] == ai:
                st = {k: seam_steps(p, maps[k]) for k in ("basecolor", "orm")}
                report[pn]["seams"] = st
                if st["basecolor"]:
                    b = st["basecolor"]
                    log.append(f"  {pn} seams: {b['edges']} edges, colour step across / beside {b['excess']} (p95 "
                               f"{b['p95']}), orm {st['orm']['excess']}"
                               + (": WARNING, the maps step at chart borders" if b["excess"] > SEAM_LIMIT else ""))
        files = {}
        for key in ("basecolor", "normal", "orm", "roughness", "metallic", "specular", "ao"):
            files[key] = out_dir / f"{stem}_{key}.png"
            _png(files[key], maps[key])
        files["height"] = out_dir / f"{stem}_height.png"
        _png(files["height"], maps["height"], bits=16)
        if "blink" in maps:   # the minimal wrinkle map: basecolor x lerp(1, blink, 1 - eyeBlink)
            files["blink"] = out_dir / f"{stem}_blink_multiply.png"
            _png(files["blink"], maps["blink"])
            log.append(f"  {stem}_blink_multiply.png: the crease line + lid occlusion, NOT in basecolor; engine: "
                       "basecolor x lerp(1, map, 1 - eyeBlink) (eyeBlink = the ARKit morph weight; open eye = full)")
        # glTF reads specular from the alpha channel of its texture
        spec_rgba = out_dir / f"{stem}_specular_gltf.png"
        a = (np.clip(maps["specular"][..., 0], 0, 1) * 255 + 0.5).astype(np.uint8)
        Image.fromarray(np.stack([np.full_like(a, 255)] * 3 + [a], -1), "RGBA").save(spec_rgba)
        atlas_files.append((an, {"basecolor": files["basecolor"], "orm": files["orm"], "normal": files["normal"],
                                 "specular": spec_rgba}))
        maps_info[an] = {k: str(v) for k, v in files.items()}
        heights[an] = res["height_range"]
        cover[an] = res["coverage"]
    extra_ext = {}
    if (spec.get("hair") or {}).get("locks"):  # curve locks (hair.py): meshed and baked in Blender, their own atlas
        from . import hair as hairmod
        spec = hair_tier_default(spec, role, log)
        hp = hairmod.export_part(name, out_dir, spec, texture=min(texture, 2048), log=log)
        if hp is not None:
            hpart, hfiles = hp
            pn_h = (spec["hair"].get("part") or "hair")
            hpart["atlas"] = len(atlas_files)
            parts[pn_h] = hpart
            origin[pn_h] = pn_h
            atlas_files.append((pn_h, hfiles))
            maps_info[pn_h] = {k: str(v) for k, v in hfiles.items()}
            heights[pn_h], cover[pn_h] = 0.0, 1.0
            report[pn_h] = {"triangles": len(hpart["corner_vert"]) // 3, "atlas": pn_h, "curves": True}
            hair_cards = hpart.pop("hair", None)
            if hair_cards:
                k0 = sum(len(i_) for _, i_ in atlas_files[:-1])
                hair_cards["aux_texture"] = k0 + list(hfiles).index("aux")
                report[pn_h].update(cards=True, layers=hair_cards["layers"], budget=hair_cards["budget"],
                                    back_faces=bool(hair_cards.get("back_faces")), vertices=len(hpart["verts"]))
            names.append(pn_h)
            sizes[len(names) - 1] = min(texture, 2048)
            ntri += report[pn_h]["triangles"]
            # a lock's sheen runs along it (the uv's v): anisotropy turned 90 degrees from the tangent (u, round the
            # lens), and a soft warm sheen
            lk = hairmod.full_look(spec["hair"].get("look"))
            sheen = [round(float(c), 3) for c in hairmod.srgb_to_linear(lk["sheen"])]
            extra_ext[len(atlas_files) - 1] = {
                # (r59) half the specular, in the sheen's colour (hair.card_specular_tint): the default white x 2 mirrored
                # the key light off the crown's cards as a white plate (Tess rc2i, Garrett v5)
                # (no specular texture: the hair's is a flat 0.5; F0 = 0.04 x factor x colour = 0.02 x tint)
                "KHR_materials_specular": {"specularFactor": hairmod.CARD_SPECULAR,
                                           "specularColorFactor": hairmod.card_specular_tint(sheen)},
                "KHR_materials_anisotropy": {"anisotropyStrength": float(lk.get("anisotropic", 0.7)),
                                             "anisotropyRotation": 1.5708},
                "KHR_materials_sheen": {"sheenColorFactor": sheen, "sheenRoughnessFactor": 0.35}}
    if spec.get("cloth"):  # simulated garments (cloth.py): their settled meshes, the flat pattern as the uv
        from . import cloth as clothmod
        cparts = clothmod.export_part(name, spec, out_dir, texture=min(texture, 2048), log=log.append)
        n_c = sum(len(cp["corner_vert"]) // 3 for _, cp, _ in cparts)
        cover_by = [cp for _, cp, _ in cparts]  # (the sim's own mesh: what covers the skin, before any decimation)
        if cloth_triangles and n_c > cloth_triangles:  # the sim's 1 cm mesh (two-sided) is far over a game budget:
            # decimated like a LOD (patches with their borders held: seams, hems, the pattern's uv)
            from . import lods as lodmod
            cparts = decimate_cloth(cparts, cloth_triangles, log)
        for pn_c, cpart, cfiles in cparts:
            cpart["atlas"] = len(atlas_files)
            parts[pn_c] = cpart
            origin[pn_c] = pn_c
            atlas_files.append((pn_c, cfiles))
            maps_info[pn_c] = {k: str(v) for k, v in cfiles.items()}
            heights[pn_c], cover[pn_c] = 0.0, 1.0
            report[pn_c] = {"triangles": len(cpart["corner_vert"]) // 3, "atlas": pn_c, "cloth": True}
            names.append(pn_c)
            sizes[len(names) - 1] = min(texture, 2048)
            ntri += report[pn_c]["triangles"]
        if cull_under_cloth and cparts:  # skin the garments cover: never seen, and a bent limb pokes it through
            cl = cover_by
            skin_pn = (spec.get("skin") or {}).get("part", "body")
            under = {skin_pn} | {p_ for p_, d_ in defs.items() if (d_ or {}).get("shell") == skin_pn
                                 and not (d_ or {}).get("garment")}  # (the skin and paint-like shells: socks)
            for pn in list(parts):
                if report.get(pn, {}).get("cloth") or report.get(pn, {}).get("curves") or pn in pf_of:
                    continue
                if origin.get(pn) not in under:
                    continue
                n0 = len(parts[pn]["corner_vert"]) // 3
                keep = under_cloth_keep(parts[pn], cl)
                if keep.all():
                    continue
                cm = np.repeat(keep, 3)
                for k_ in ("corner_vert", "uv", "normal", "tangent", "sign"):
                    parts[pn][k_] = parts[pn][k_][cm]
                report[pn]["triangles"] = int(keep.sum())
                report[pn]["under_cloth_dropped"] = int(n0 - keep.sum())
                ntri -= int(n0 - keep.sum())
                log.append(f"{pn}: {n0 - int(keep.sum())} of {n0} triangles under the garments dropped (covered "
                           f"within {UNDER_CLOTH_REACH * 1000:.0f} mm along the normal, {UNDER_CLOTH_RIM * 1000:.0f} mm "
                           "rim kept at every opening)")
            # (r53, coordinator) garment under garment: the faces of an under garment its covers hide (the same test,
            # reach and rim) are dropped at LOD0, so every LOD inherits it: rc2's jeans / sweater kept every triangle under
            # the coat, which cost budget and poked through at LOD1+
            cnames = [pn_c for pn_c, _, _ in cparts]
            over_ = garment_over(spec, log.append)
            for gn in over_:
                un = f"cloth_{gn}"
                ups = [f"cloth_{o_}" for o_ in over_ if gn in _over_chain(over_, o_)]
                cov = [cover_by[cnames.index(u_)] for u_ in ups if u_ in cnames]
                if un not in parts or not cov or not CLOTH_UNDER_CULL:
                    continue
                n0 = len(parts[un]["corner_vert"]) // 3
                keep = cloth_under_keep(parts[un], cov)
                if keep.all():
                    continue
                if cull_poses:  # (r54) a face uncovered in ANY dumped clip frame is kept (cull_exposed_keep)
                    ups_ = [u_ for u_ in ups if u_ in parts]
                    keep, ex_ = cull_exposed_keep(parts[un], [parts[u_] for u_ in ups_], un, ups_, cull_poses, keep)
                    log.append(f"{un}: {ex_['restored']} culled triangles restored, exposed in a clip frame "
                               f"({ex_['frames']} frames; worst {ex_['worst']})")
                    report[un]["cull_exposed"] = ex_
                parts[un] = cull_tris(parts[un], keep)
                report[un]["triangles"] = int(keep.sum())
                report[un]["under_cloth_dropped"] = int(n0 - keep.sum())
                ntri -= int(n0 - keep.sum())
                log.append(f"{un}: {n0 - int(keep.sum())} of {n0} triangles under {', '.join(ups)} dropped (garment "
                           f"under garment, {UNDER_CLOTH_RIM * 1000:.0f} mm rim kept at every opening)")
    from . import lashes as lashmod
    lash = lashmod.export_part(spec, out_dir, log=log.append)
    if lash:  # eyelash ribbons (lashes.py): their own mesh and tiny maps, two-sided; face shapes turn them with the lids
        pn_l, lpart, lfiles = lash
        cap_ = lash_cap(rb, report) if rb else None
        if cap_ is not None:  # the eyes / mouth / lashes budget: the lashes fit what eyes, teeth, tongue and brows leave
            from .lods import ribbon_fit
            lpart, linfo_ = ribbon_fit(lpart, cap_)
            if linfo_["triangles"] < linfo_["triangles0"]:
                log.append(f"lashes: {linfo_['triangles0']} -> {linfo_['triangles']} triangles ({linfo_['ribbons_kept']} of "
                           f"{linfo_['ribbons']} lashes, widened x{linfo_['widen']:.2f}) to fit eyes_mouth_lashes "
                           f"{int(rb['parts']['eyes_mouth_lashes']['default'])}")
        lpart["atlas"] = len(atlas_files)
        parts[pn_l] = lpart
        origin[pn_l] = pn_l
        atlas_files.append((pn_l, lfiles))
        maps_info[pn_l] = {k: str(v) for k, v in lfiles.items()}
        heights[pn_l], cover[pn_l] = 0.0, 1.0
        report[pn_l] = {"triangles": len(lpart["corner_vert"]) // 3, "atlas": pn_l, "lashes": True}
        names.append(pn_l)
        sizes[len(names) - 1] = 16
        ntri += report[pn_l]["triangles"]
    glb = out_dir / f"{aname}.glb"
    looks = {pn: {k: float(d[k]) for k in ("transmission", "alpha", "ior") if k in d}
             for pn in parts for d in [defs.get(origin[pn]) or {}] if any(k in d for k in ("transmission", "alpha"))}
    if (spec.get("hair") or {}).get("locks") and locals().get("hair_cards"):
        looks.setdefault(pn_h, {}).update(alpha_cutoff=hair_cards["alpha_cutoff"],
                                          double_sided=not hair_cards.get("back_faces"),  # (c6: own back faces)
                                          extras={"hifipushie_hair": hair_cards})
    if skin_recipe:  # the skin part's own material: the film's second lobe and the sheen as ratified extensions, the
        sp = (spec.get("skin") or {}).get("part", "body")  # rest (scattering, tiling detail) in its extras
        for pn in parts:
            if origin[pn] == sp:
                looks.setdefault(pn, {}).update(
                    ext={"KHR_materials_clearcoat": {"clearcoatFactor": float(skin_recipe["specular"]["coat"]),
                                                     "clearcoatRoughnessFactor": float(skin_recipe["specular"]["coat_roughness"])},
                         "KHR_materials_sheen": {"sheenColorFactor": [float(skin_recipe["sheen"])] * 3, "sheenRoughnessFactor": 0.5}},
                    extras={"hifipushie_skin": skin_recipe})
    if lash:
        looks.setdefault(lash[0], {})["double_sided"] = True
    from .skin_features import eye_base
    ek = eye_base(spec)
    if ek:  # the eyes' tear film: a clear coat over the matte iris and sclera (the catchlight)
        for pn in parts:
            if origin.get(pn) == ek[0]:
                looks.setdefault(pn, {}).setdefault("ext", {})["KHR_materials_clearcoat"] = {
                    "clearcoatFactor": float(ek[1]["coat"]), "clearcoatRoughnessFactor": float(ek[1]["coat_roughness"])}
    rigged = None
    if rig:  # an armature from the skeleton, the parts (not prefabs) skinned to it
        from . import rig as rigmod
        tr = time.time()
        rspec = spec
        if isinstance(rig, dict):  # export options over spec["rig"]: {"twist": ..., "rigid_head": ...}
            rspec = {**spec, "rig": {**(spec.get("rig") or {}), **rig}}
        bones = rigmod.rig_bones(rspec)
        skin_at = {pn: np.array(p["verts"], np.float64) for pn, p in parts.items() if pn not in pf_of}
        rigged = {"bones": bones, "weights": rigmod.skin_parts(
            rspec, bones, {pn: (skin_at[pn], parts[pn]["corner_vert"].reshape(-1, 3)) for pn in skin_at}, smooth=3)}
        hf = rigmod.head_field(rspec, bones)
        ntw = sum(1 for b in bones if b.get("twist"))
        log.append(f"rig: {len(bones)} bones ({(spec.get('rig') or {}).get('type', 'humanoid')}, root "
                   f"{bones[0]['name']!r}; {ntw} twist bones after the base set), {len(rigged['weights'])} parts "
                   f"skinned, head rigid by {hf['how'] if hf else 'nothing (off, or no Head bone)'}, "
                   f"{time.time() - tr:.1f}s")
        from . import rig_template as _rt
        if _rt.weights_note(rspec):
            log.append(_rt.weights_note(rspec))
        from . import rig_audit as _ra
        sit = _ra.seated(bones)
        if sit and len(skin_at) > 1:  # do the layers stay in order when the character sits (rig_audit.layers)
            pn_s = list(skin_at)
            Vs = np.concatenate([skin_at[pn] for pn in pn_s])
            off = np.cumsum([0] + [len(skin_at[pn]) for pn in pn_s])
            Fs_ = np.concatenate([parts[pn]["corner_vert"].reshape(-1, 3) + off[i] for i, pn in enumerate(pn_s)])
            Js = np.concatenate([np.asarray(rigged["weights"][pn][0]) for pn in pn_s])
            Ws = np.concatenate([np.asarray(rigged["weights"][pn][1], np.float64) for pn in pn_s])
            rows = _ra.layers(Vs, Fs_, np.repeat(np.arange(len(pn_s)), np.diff(off)), pn_s,
                              rigmod.pose(bones, Vs, Js, Ws, rigmod.drive_twist(bones, sit)),
                              skip=[pn for pn in pn_s if (defs.get(origin[pn]) or {}).get("rig_bone")])
            bad = [r for r in rows if r["through"] > _ra.LAYER_BAD]
            log += [("WARNING rig: " if bad else "rig: ") + ln.strip() if i == 0 else ln
                    for i, ln in enumerate(_ra.layers_text(rows, top=4))]
            rigged["layers_seated"] = rows[:8]
    shapes = {}
    if face_shapes:  # after the bake and the skin: both use the meshed (open-mouthed) low poly
        from . import faceshapes
        tf = time.time()
        for pn, (tp, _) in topo.items():  # (one mesh, own quads) each low-poly vertex's GNM vertex: face shapes
            # by index. Only when the low poly is still the topology's vertices as they were written
            z = np.load(tp)
            if pn in parts and "gnm" in z.files and len(z["verts"]) == len(parts[pn]["verts"]) and \
                    np.allclose(np.asarray(parts[pn]["verts"], float), z["verts"], atol=1e-5):
                parts[pn]["gnm_index"] = z["gnm"]
            elif pn in parts and "gnm" in z.files:
                log.append(f"WARNING face shapes: {pn}'s low poly isn't its topology's vertices: shapes by projection")
        moving = {pn: p for pn, p in parts.items() if pn not in pf_of and not report[pn].get("curves")}
        if os.environ.get("HP_SHAPES_DUMP"):  # (debug / fast tuning: the parts as faceshapes.apply gets them, so a
            # shape constant can be retried on them in seconds; spikes/game_ready/shapesfast.py)
            import copy
            import pickle
            with open(os.environ["HP_SHAPES_DUMP"], "wb") as fh:
                pickle.dump({"spec": spec, "parts": copy.deepcopy(moving), "face_shapes": face_shapes}, fh)
        shapes = faceshapes.apply(spec, moving, face_shapes, log)
        from . import skin_folds
        fx = skin_folds.expression(spec, {pn: parts[pn] for pn in shapes}, log)   # the folds' own change with each shape
        for pn, nms in shapes.items():
            report[pn]["face_shapes"] = nms
            if fx and parts[pn].get("shapes") and pn.split("/")[-1].split("~")[0] == (spec.get("skin") or {}).get("part", "body"):
                report[pn]["fold_expressions"] = fx
            if parts[pn].get("shape_unevenness"):  # (faceshapes.unevenness: shapes over UNEVEN_COUNT, worst vertex)
                report[pn]["face_shape_unevenness"] = parts[pn].pop("shape_unevenness")
        log.append(f"face shapes: {len(faceshapes.names_of(face_shapes))} on {len(shapes)} parts in "
                   f"{time.time() - tf:.1f}s")
        if rigged and hf is not None:  # whatever a face shape moves is head: it must not also bend with the neck
            moved = {}
            for pn in shapes:
                d = [np.linalg.norm(np.asarray(x[0]), axis=1) for x in (parts[pn].get("shapes") or {}).values()]
                if d and pn in skin_at and len(d[0]) == len(skin_at[pn]):
                    moved[pn] = np.max(d, 0)
            before = {pn: _head_share(rigged, pn, hf["bone"]) for pn in moved}
            skin_cov = rigmod.skin_cover(rspec, bones, {pn: (skin_at[pn], parts[pn]["corner_vert"].reshape(-1, 3))
                                                     for pn in skin_at}, hf)
            rigged["weights"] = rigmod.rigid_near(bones, rigged["weights"], skin_at, moved, hf["band"], skin_cov,
                                                     hf["h"] if rspec.get("base") else None)
            for pn, mv in moved.items():
                m = mv >= rigmod.MOVED[1]
                if m.any():
                    b0, b1 = before[pn][m], _head_share(rigged, pn, hf["bone"])[m]
                    log.append(f"rig: {pn}: {int(m.sum())} vertices the face shapes move "
                               f"{rigmod.MOVED[1] * 1e3:g} mm or more are Head {b1.min():.2f}+ "
                               f"({int((b0 < 0.99).sum())} weren't: least {b0.min():.2f})")
    for p in parts.values():  # (the lashes' roots: only face shapes needed them)
        p.pop("lash_root", None)
        p.pop("lash_centre", None)
    corr_keys = []
    if rigged and correctives:  # pose correctives (correctives.py): morph targets faded in by the joint's angle
        from . import correctives as cormod
        tc = time.time()
        corr_keys = cormod.keys(rigged["bones"])
        nc_ = 0
        for pn in list(rigged["weights"]):
            if pn not in skin_at or report[pn].get("curves") or report[pn].get("lashes") or \
                    (defs.get(origin.get(pn, pn)) or {}).get("rig_bone"):
                continue
            Jp, Wp = rigged["weights"][pn]
            Fp = parts[pn]["corner_vert"].reshape(-1, 3)
            D = cormod.solve(rigged["bones"], skin_at[pn], Fp, Jp, Wp, corr_keys, log if pn == "body" else [])
            D = {k: v for k, v in D.items() if np.abs(v).max() > cormod.EPS}
            if not D:
                continue
            n0 = cormod.vertex_normals(skin_at[pn], Fp)
            sh = parts[pn].setdefault("shapes", {})
            for k in corr_keys:
                if k["name"] in D:
                    sh[k["name"]] = (D[k["name"]], n0, cormod.vertex_normals(skin_at[pn] + D[k["name"]], Fp))
            report[pn]["pose_correctives"] = [k["name"] for k in corr_keys if k["name"] in D]
            nc_ += len(D)
        log.append(f"pose correctives: {len(corr_keys)} ({', '.join(sorted({k['motion'] for k in corr_keys}))}), "
                   f"{nc_} targets over the parts, {time.time() - tc:.1f}s")
    seam = head_body_meshes(spec, parts, topo, log)
    if seam:
        report[seam["part"]]["meshes"] = seam["report"]
    if spec.get("cloth") and LOD0_PUSH_UNDER:  # (r57) LOD0 too: rc2f's sweater poked 0.4-1 mm through both coat shells
        # beside her left chest pocket in the rest pose (an orange speck at 1 m); LOD1-3 start from this
        from . import lods as lodmod0_
        st0_ = _garment_stack(spec, parts, log.append)
        if st0_:
            pu0_ = lodmod0_.push_under_layers(parts, st0_, gap=LOD0_UNDER_GAP)
            log.append("LOD0: under garments put back under their covers (lods.push_under_layers): " + ", ".join(
                f"{pn} poking {v['poking0']} vertices / {v['faces_poking0']} faces -> {v['poking']} ({v['moved']} moved"
                f"{', %d capped' % v['capped'] if v.get('capped') else ''}"
                f"{', ' + str(v['flaps']) + ' in a flap through the cover' if v.get('flaps') else ''})"
                for pn, v in pu0_.items()))
            for pn, v in pu0_.items():
                report.setdefault(pn, {})["under0"] = v
    write_glb(glb, aname, parts, atlas_files, ctx["prefabs"], looks, rigged, extra_ext)
    lod_info = []
    if lods:
        from . import lods as lodmod
        ratios = list(lodmod.LOD_RATIOS) if lods is True else [float(r) for r in lods]
        ratio_of, mesh_r, shape_lods = None, None, None
        if rb is not None and lods is True:
            from . import budgets as budgetmod
            above, below = budgetmod.lod_ratios("head"), budgetmod.lod_ratios("body")
            ratios = budgetmod.lod_ratios(None)[1:]
            shape_lods = set((rb.get("face_shapes") or {}).get("lods") or [0])

            ratio_of = True
        cards = [pn for pn in parts if report[pn].get("curves") or report[pn].get("lashes")]
        tier_parts = {}
        if locals().get("hair_cards"):  # hair LODs are the groom's own card TIERS (one atlas for all:
            # hair.export_hair), cut for their budget; thinning LOD0's cards dropped the tail first. (Unrigged too,
            # round 25: whole layers dropped once, 11996 -> 5324 at LOD1 and flat at LOD2 / LOD3.)
            from . import hair as hairmod
            hb_ = next((i for i, b in enumerate(rigged["bones"]) if b["name"].endswith("Head")), 0) if rigged else 0
            for k, r in enumerate(ratios, 1):
                tier_ = lodmod.HAIR_TIERS[min(k, len(lodmod.HAIR_TIERS)) - 1]
                sp_ = {**spec, "hair": {**spec["hair"], "export": {**(spec["hair"].get("export") or {}), "tier": tier_}}}
                try:
                    tp_, _tf = hairmod.export_cards(name, out_dir / f"_lod{k}", sp_, log)
                except Exception as e:  # (LOD0 hair kept)
                    log.append(f"WARNING LOD{k}: hair tier {tier_} failed ({type(e).__name__}: {e}); LOD0's cards kept")
                    continue
                tp_.pop("hair", None)
                own_ = None
                if hairmod.share_atlas(tp_, _tf, dict(atlas_files[parts[pn_h]["atlas"]][1])):
                    tp_["atlas"] = parts[pn_h]["atlas"]  # (its uv on LOD0's atlas: a tier's atlas lacks the baked rows)
                else:  # its own maps beside the GLBs (a tier whose pictures differ from LOD0's)
                    import shutil
                    own_ = {}
                    for mk_, f_ in _tf.items():
                        own_[mk_] = out_dir / f"{pn_h}_lod{k}_{mk_}.png"
                        shutil.copyfile(f_, own_[mk_])
                    log.append(f"LOD{k}: hair tier {tier_}'s atlas differs from LOD0's: it carries its own maps")
                nv_ = len(tp_["verts"])
                Jh = np.zeros((nv_, 4), np.int64)
                Jh[:, 0] = hb_
                Wh = np.zeros((nv_, 4), np.float32)
                Wh[:, 0] = 1.0
                tier_parts[k] = (tp_, (Jh, Wh), tier_, own_)
        layer_stack = {}  # (r53) {under garment part: the garment parts over it, transitively}: each LOD puts the under
        # garments back under their decimated covers (lods.push_under_layers)
        if spec.get("cloth") and LOD_PUSH_UNDER:
            layer_stack = _garment_stack(spec, parts)
        under_masks = {}  # (r54) parts worn under garments that are not garments (socks, the body): put back under the
        # garments too, but only where they were under one at LOD0 (lods.under_at_lod0). rc2c's LOD2 showed the socks
        # (kept whole) through the decimated jeans' calves (101 vertices poking, 1 at LOD0) and the body through the sweater.
        garm_ = [pn for pn in parts if pn.startswith("cloth_") and pn not in pf_of]
        if garm_ and LOD_PUSH_UNDER and LOD_PUSH_WORN:
            for pn, p in parts.items():
                if (pn in garm_ or pn in pf_of or pn in cards or pn in LOD_PUSH_WORN_SKIP or report.get(pn, {}).get("lashes")
                        or p.get("shell")):
                    continue
                P0_, un0_, sh_, ov0_, N0_ = lodmod.under_at_lod0(p, [parts[g] for g in garm_], share=True)
                if int(un0_.sum()) >= LOD_PUSH_WORN_MIN and sh_ >= LOD_PUSH_WORN_SHARE:
                    layer_stack[pn] = list(garm_)
                    under_masks[pn] = (P0_, ~ov0_ if LOD_PUSH_WORN_NOT_OVER else un0_, sh_, N0_, un0_)  # (r55) every vertex NOT over a
                    # garment at LOD0 may move: rc2d's LOD2 left calf showed 22 sock vertices through the jeans whose LOD0
                    # vertices had no jeans within reach (a loose leg), so the 'under at LOD0' mask kept them still
            sk_ = (spec.get("skin") or {}).get("part", "body")
            if sk_ in under_masks and LOD_SKIN_CULL_FROM is not None:  # (Garrett s14) the skin's deep-covered faces drop at
                # LOD >= LOD_SKIN_CULL_FROM too (its residue under the jacket's armhole poked through the decimated sleeve:
                # the underarm notch), except where a dumped clip frame (cull_poses: the seated poses) uncovers it
                P0_, a_, b_, c_, un0_ = under_masks[sk_]
                exp_ = skin_pose_exposed(parts[sk_], P0_, [parts[g] for g in garm_], sk_, garm_, cull_poses)
                under_masks[sk_] = (P0_, a_, b_, c_, un0_, un0_ & ~exp_)  # [5]: what the per-LOD cull may drop
                log.append(f"LODs: {sk_}: {int(un0_.sum())} LOD0 points under the garments, {int((un0_ & exp_).sum())} of them "
                           f"uncovered in a clip frame (kept at every LOD)")
            if under_masks:
                log.append("LODs: parts worn under garments also put back under them: " + ", ".join(
                    f"{pn} ({int(m_[1].sum())} vertices free to move, {m_[2]:.0%} of those in reach under)" for pn, m_ in under_masks.items()))
        garment_cull = garment_cull_masks(parts, layer_stack, garm_)  # (Garrett s10) under garments' LOD0 cover masks
        if os.environ.get("HP_LOD_DUMP"):  # (r60, debug: the LOD inputs, to probe a part's LOD steps offline)
            import pickle
            with open(os.environ["HP_LOD_DUMP"], "wb") as fh:
                pickle.dump({"parts": {pn: p for pn, p in parts.items() if pn not in pf_of and pn not in cards},
                             "rigged": rigged, "layer_stack": layer_stack, "under_masks": under_masks,
                             "ratios": ratios, "above": locals().get("above"), "below": locals().get("below")}, fh)
        for k, r in enumerate(ratios, 1):
            tl = time.time()
            if ratio_of is not None:  # above the neck holds detail longer than below it (budgets.lod_ratios)
                kk_ = min(k, len(above) - 1)
                skin_pn_ = (spec.get("skin") or {}).get("part", "body")

                def r_part(pn, kk_=kk_):  # head parts (the skin's head mesh by mesh_ratios) above, the rest below
                    if pn == skin_pn_ or pn in ("eyes", "teeth", "teeth_lower", "tongue") or report.get(pn, {}).get("lashes"):
                        return above[kk_]
                    return below[min(kk_, len(below) - 1)]
                rr_, mesh_r = r_part, {"head": above[kk_], "body": below[min(kk_, len(below) - 1)]}
            else:
                rr_ = r
            lp, lr, rep_l = lodmod.lod_parts({pn: p for pn, p in parts.items() if pn not in pf_of}, rigged, rr_, skip=cards,
                                             cards={pn_h: hair_cards["layers"]} if locals().get("hair_cards") and k not in tier_parts else None,
                                             mesh_ratios=mesh_r, shapes=(shape_lods is None or k in shape_lods),
                                             ribbons=[pn for pn in cards if report[pn].get("lashes")])
            if layer_stack:
                rb_ = below[min(kk_, len(below) - 1)] if ratio_of is not None else r
                pu_ = lodmod.push_under_layers(lp, layer_stack, masks=under_masks, face_deep=(
                    lodmod.LOD_UNDER_FACE_DEEP_FAR if rb_ < lodmod.LOD_SMALL_FAR_RATIO else None))
                log.append(f"LOD{k}: under garments put back under their covers (lods.push_under_layers): " + ", ".join(
                    f"{pn} poking {v['poking0']} -> {v['poking']} ({v['moved']} moved{', %d capped' % v['capped'] if v.get('capped') else ''})" for pn, v in pu_.items()))
                for pn, v in pu_.items():
                    rep_l.setdefault(pn, {})["under"] = v
            skin_pn0_ = (spec.get("skin") or {}).get("part", "body")
            for pn, m_ in under_masks.items():  # (r60) the worn parts' covered rims (socks); (s14) the skin's from its own LOD
                    from_ = LOD_SKIN_CULL_FROM if pn == skin_pn0_ else lodmod.LOD_UNDER_CULL_FROM
                    if not from_ or k < from_ or pn not in lp or len(m_) < 5:
                        continue
                    kc_ = lodmod.cull_covered(lp[pn], m_[0], m_[5] if len(m_) > 5 else m_[4])
                    if not kc_.all():
                        lp[pn] = cull_tris(lp[pn], kc_)
                        rep_l.setdefault(pn, {})["covered_culled"] = int((~kc_).sum())
                        rep_l[pn]["triangles"] = len(lp[pn]["corner_vert"]) // 3
                        log.append(f"LOD{k}: {pn}: {int((~kc_).sum())} of {len(kc_)} triangles deep under the garments at LOD0 "
                                   f"dropped (lods.cull_covered, {lodmod.LOD_UNDER_CULL_RIM * 1000:.0f} mm rim)")
            cull_under_garments(lp, garment_cull, k, log, rep_l)
            atl_k, ext_k = atlas_files, extra_ext
            if k in tier_parts:
                tp_, w_, tier_, own_ = tier_parts[k]
                if own_ is not None:  # (an atlas of its own, wearing the hair material's extensions)
                    hi_ = parts[pn_h]["atlas"]
                    tp_ = {**tp_, "atlas": len(atlas_files)}
                    atl_k = atlas_files + [(f"{pn_h}_lod{k}", own_)]
                    ext_k = {**extra_ext, **({len(atlas_files): extra_ext[hi_]} if hi_ in extra_ext else {})}
                lp[pn_h] = tp_
                if lr is not None:
                    lr["weights"][pn_h] = w_
                rep_l[pn_h] = {"triangles0": len(parts[pn_h]["corner_vert"]) // 3,
                               "triangles": len(tp_["corner_vert"]) // 3, "tier": tier_,
                               "atlas": "own" if own_ is not None else "LOD0's"}
            lg = out_dir / f"{aname}_LOD{k}.glb"
            write_glb(lg, aname, lp, atl_k, {}, looks, lr, ext_k, external=True)
            tri_k = sum(v["triangles"] for v in rep_l.values())
            lod_info.append({"lod": k, "ratio": r, "glb": str(lg), "triangles": tri_k,
                             "parts": {pn: v["triangles"] for pn, v in rep_l.items()}})
            log.append(f"LOD{k} ({r:g} of LOD0): {tri_k} triangles in {time.time() - tl:.1f}s -> {lg.name} (maps "
                       f"by file name beside it); " + ", ".join(f"{pn} {v['triangles']}" for pn, v in rep_l.items()))
        import shutil
        for k in tier_parts:  # (the tiers' own copies of the shared hair atlas)
            shutil.rmtree(out_dir / f"_lod{k}", ignore_errors=True)
    budget_gate = None
    if rb is not None:  # each part's count against the role's budget (a gate line; over = WARNING)
        budget_gate = budget_check(rb, report, spec)
        for ln in budget_gate["lines"]:
            log.append(ln)
        if budget_gate["fail"]:  # (hair-budget rule) over the role's range max is refused, not a WARNING
            raise ValueError(f"{name}: over the {role} budget's hard limit: " + "; ".join(budget_gate["fail"]))
    if fbx:  # the same asset as FBX, for engines' skinned-mesh import
        tf = time.time()
        write_fbx(glb, glb.with_suffix(".fbx"))
        log.append(f"wrote {glb.with_suffix('.fbx').name} in {time.time() - tf:.1f}s")
    for _, f in atlas_files:
        if not lods:  # (the LODs' GLBs read it by name)
            f["specular"].unlink()
    (out_dir / "lowpoly.npz").unlink()
    high.unlink()
    out_dir.joinpath("high_focus.npz").unlink(missing_ok=True)
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
            "parts": report, "prefabs": prefabs, **({"lods": lod_info} if lod_info else {}),
            **({"role": role, "budget": budget_gate} if rb is not None else {}), **({"skin": skin_recipe} if skin_recipe else {}),
            **({"rig": {"bones": [b["name"] for b in rigged["bones"]],
                        "base_bones": sum(1 for b in rigged["bones"] if not b.get("twist") and not b.get("bend")),
                        "layers_seated": rigged.get("layers_seated", []),
                        "rest": "every base joint unrotated at its head, pose as modelled; twist joints rotated so "
                                "local +Y runs along their segment",
                        "twist": rigmod.twist_table(rigged["bones"]),
                        "twist_axes": "Blender axes here (Z up, faces -Y); the GLB's node extras.hifipushie_twist "
                                      "carry the same per joint in glTF axes (axis_parent) and local (+Y)",
                        "twist_recipe": TWIST_RECIPE,
                        "bend": rigmod.bend_table(rigged["bones"]), "bend_recipe": BEND_RECIPE,
                        **({"correctives": __import__("hifipushie.correctives", fromlist=["table"]).table(corr_keys),
                            "corrective_recipe": CORRECTIVE_RECIPE} if corr_keys else {}),
                        "head": (f"rigid: {hf['how']}; falloff to the neck over {hf['band'] * 1e3:.0f} mm below; "
                                 "face-shape vertices, teeth, tongue and eyes Head 1.0") if hf else "not rigid"}}
               if rigged else {}),
            **({"face_shapes": {"names": faceshapes.names_of(face_shapes), "parts": shapes,
                                "correctives": {c: f"{op}({a}, {b})" for c, (op, a, b) in faceshapes.CORRECTIVES.items()
                                                if c in faceshapes.names_of(face_shapes)},
                                "convention": "ARKit blendshape names; glTF morph targets (names in mesh.extras."
                                              "targetNames, default weights 0), FBX blend shapes of the same names; "
                                              "neutral = mouth closed, each shape its full extent at 1.0, additive; "
                                              "correctives are not ARKit channels: set each to its formula of the "
                                              "ARKit weights every frame (jawOpen_mouthClose = min(jawOpen, "
                                              "mouthClose) seals the lips over an open jaw); left at 0 the lips "
                                              "just stay parted"}}
               if face_shapes else {}),
            "conventions": {"up": "+Y (glTF)", "front": "+Z", "units": "metres", "normal_map": "OpenGL (+Y), MikkTSpace",
                            "height": "0.5 = low-poly surface, 0/1 = -/+ height_range_m (per atlas) along the normal",
                            "orm": "R ambient occlusion, G roughness, B metallic",
                            "specular": "0.5 = F0 0.04 (Blender's IOR level)",
                            "materials": "one per atlas, in the order of 'atlases'",
                            "prefabs": "one mesh per prefab (a primitive per part, in the prefab's frame), a node "
                                       "per instance with extras.prefab"},
            "seconds": round(time.time() - t, 1), "log": log}
    try:  # the engine-agnostic shading notes beside the GLB (shading.py): what each material is meant to do
        from . import shading
        from .hair import look_of as _hlook
        sj, sm = shading.write(info, out_dir, aname, looks=looks,
                               hair_look=_hlook(spec) if spec.get("hair") else None, eyes_part=ek[0] if ek else None)
        info["shading"] = {"json": str(sj), "md": str(sm)}
    except Exception as e:  # (notes never fail an export; said in the log)
        log.append(f"WARNING shading notes not written: {type(e).__name__}: {e}")
    try:  # the rig's drivers (twist, bend helpers, pose correctives) per engine (rignotes.py)
        from . import rignotes
        rn = rignotes.write(info, out_dir, aname)
        if rn:
            info["rig_notes"] = {"json": str(rn[0]), "md": str(rn[1])}
    except Exception as e:
        log.append(f"WARNING rig notes not written: {type(e).__name__}: {e}")
    (out_dir / f"{aname}.json").write_text(json.dumps(info, indent=1))
    return info


def preview(glb: Path, views: list[str], size: int = 512, samples: int = 24, focus=None, zoom: float = 1.0,
            hide: list[str] | None = None, lighting: dict | None = None, cameras: list | None = None,
            denoise: bool = True, poses: list[dict] | None = None, engine: str = "game"):
    """Render the exported GLB as a game draws it: re-imported by Blender's glTF importer and rendered in EEVEE set up
    like a game (no ray tracing, alpha-tested cards, shadow maps), its materials built from the export's shading notes
    (<asset>_shading.json: blender_game.py, the engine stage of docs/notes/gates.md), face shapes and the blink map
    driven as an engine drives them. engine="cycles": the old path-traced look of the importer's materials (lighting,
    samples, denoise apply to it only).
    Views as in look; the GLB is Y up, so the cameras are turned to match. hide: parts left out (the roof and
    walls, to see an interior). lighting: a style look ({"lights", "world", "look", "exposure", "view"}, as scene.look
    takes), so the preview compares with the painted look; default a neutral studio under Standard. cameras:
    perspective panels as look takes them (model coordinates, Z up), for close-ups of the textures.
    poses: [{shape name: weight}] (face shapes, the GLB's morph targets): one Blender run renders the views once per
    pose and a list of contact sheets comes back, one per pose."""
    bounds = np.array(json.loads(glb.with_suffix(".json").read_text())["bounds_blender"])
    with tempfile.TemporaryDirectory(prefix="hifipushie-prev-") as tmp:
        frames = (render.view_frames(bounds, views, focus, zoom) if views else []) + [
            render.camera_frame(c, i) for i, c in enumerate(cameras or [])]  # perspective: {"eye", "target", "fov"}
        for f in frames:  # Blender's glTF importer converts back to Z up, so the look cameras apply as they are
            f["out"] = str(Path(tmp) / f"{f['name']}.png")
        if engine == "game":
            game(glb, frames=frames, size=size, hide=hide, poses=poses, timeout=600 + 60 * len(poses or []))
        else:
            _blender({"mode": "preview", "glb": str(glb), "views": frames, "size": size, "samples": samples,
                      "hide": list(hide or []), "lighting": lighting, "denoise": denoise, "poses": poses},
                     timeout=600 + 60 * len(poses or []))
        if poses is None:
            return render.contact_sheet([Image.open(f["out"]).convert("RGB") for f in frames], frames)
        return [render.contact_sheet([Image.open(f"{f['out'][:-4]}_p{i}.png").convert("RGB") for f in frames], frames)
                for i in range(len(poses))]
