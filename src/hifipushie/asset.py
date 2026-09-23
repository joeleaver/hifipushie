"""Game-ready export: a low-poly mesh with one UV atlas and PBR textures baked from the exact model.

Nothing is baked from a high-poly mesh. Each texel's point on the low-poly surface is projected onto the exact
field, and every map is read there:
  normal        tangent-space (MikkTSpace, OpenGL / glTF convention: green = +V), from the field's gradient
  height        signed distance from the low-poly surface to the exact one along the low-poly normal (m);
                low poly + height reproduces the sculpt. 16-bit PNG, 0.5 = 0, +-`height_range` m at 0 / 1.
  basecolor, roughness, metallic, specular   from paint (paint.apply_channels) at the exact point, so paint
                detail is limited by the texture, not by the build voxel
  ao            ambient occlusion from the field of all parts (cheap SDF cone samples along the normal)
  orm           glTF packing: R = ao, G = roughness, B = metallic
Plus asset.glb (glTF 2.0, Y up, the creature facing +Z, one mesh per part, one material with base colour,
ORM, normal and KHR_materials_specular) and asset.json describing all of it.
"""

from __future__ import annotations

import json
import struct
import subprocess
import tempfile
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from . import paint, render, sdf, store, surface
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


def lowpoly(high: Path, out: Path, triangles: int, texture: int) -> dict:
    """Decimate + unwrap in Blender; returns {part: {verts, corner_vert, uv, normal, tangent, sign}}."""
    _blender({"mode": "lowpoly", "mesh": str(high), "out": str(out), "triangles": int(triangles),
              "min_part": 300, "margin": 6.0 / texture})
    z = np.load(out)
    names = [str(n) for n in z["part_names"]]
    return {pn: {k: z[f"{i}_{k}"] for k in ("verts", "corner_vert", "uv", "normal", "tangent", "sign")}
            for i, pn in enumerate(names)}


def prune_hidden(spec: dict, mesh: Path, out: Path, voxel: float, log: list) -> Path:
    """Drop faces buried inside another part (skin under solid clothing shells, the back of an eyeball in its
    socket, tooth roots): nobody sees them, and they'd take triangles and atlas space."""
    z = dict(np.load(mesh))
    names = [str(n) for n in z["part_names"]]
    streams = {ps[0].part: ps for ps in sdf.streams(compile_prims(spec))}
    hidden = surface.hidden(streams, z["verts"].astype(np.float64), z["part"], names, voxel) > 0.5
    faces = z["faces"]
    keep = ~hidden[faces].all(1)
    dropped = {pn: int((~keep & (z["part"][faces[:, 0]] == i)).sum()) for i, pn in enumerate(names)}
    log.append("hidden faces dropped: " + ", ".join(f"{k} {v}" for k, v in dropped.items() if v) if any(
        dropped.values()) else "no hidden faces")
    z["faces"] = faces[keep]
    np.savez(out, **z)
    return out


def rasterize(parts: dict, size: int):
    """Which triangle covers each texel and where: (tri id per texel or -1, barycentrics, per-triangle part
    index and corner offset). Texel (x, y) of the PNG (row 0 at the top) is uv ((x + .5) / size, 1 - (y + .5) / size)."""
    img = Image.new("I", (size, size), -1)
    d = ImageDraw.Draw(img)
    uvs, tpart = [], []
    for pi, p in enumerate(parts.values()):
        uvs.append(p["uv"].reshape(-1, 3, 2))
        tpart.append(np.full(len(uvs[-1]), pi))
    uv = np.concatenate(uvs).astype(np.float64)
    px = np.stack([uv[..., 0] * size, (1 - uv[..., 1]) * size], -1)
    for t, tri in enumerate(px):
        d.polygon([tuple(q) for q in tri], fill=t)
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
    bary = np.clip(np.stack([1 - w1 - w2, w1, w2], -1), 0, 1)
    bary /= bary.sum(1, keepdims=True)
    return (ys, xs), t, bary, np.concatenate(tpart)


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


def bake(spec: dict, parts: dict, size: int, voxel: float, log: list) -> dict:
    """Every map as float arrays (size, size, k), plus the height range."""
    t0 = time.time()
    names = list(parts)
    (ys, xs), tri, bary, tpart = rasterize(parts, size)
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
    streams = {ps[0].part: ps for ps in sdf.streams(compile_prims(spec))}
    X, G = P.copy(), Nl.copy()
    h = 0.1 * voxel
    t1 = time.time()
    for pi, pn in enumerate(names):
        sel = np.flatnonzero(part == pi)
        x, g = surface.newton(streams[pn], X[sel], h, voxel)
        # a texel that wandered off (onto another sheet, or out of a thin gap) keeps the low-poly surface
        bad = (np.linalg.norm(x - P[sel], axis=1) > 6 * voxel) | ((_unit(g) * Nl[sel]).sum(1) < 0.2)
        x[bad], g[bad] = P[sel][bad], Nl[sel][bad]
        X[sel], G[sel] = x, _unit(g)
        if bad.any():
            log.append(f"  {pn}: {bad.mean():.2%} of texels kept the low-poly surface (projection went astray)")
    log.append(f"projected onto the exact surface in {time.time() - t1:.1f}s")
    t3 = time.time()
    ao_map = _ao_map(spec, parts, streams, size, voxel)
    log.append(f"ambient occlusion (at {size // 2 if size >= 1024 else size}^2) in {time.time() - t3:.1f}s")

    t2 = time.time()
    base = paint.part_defaults(spec, names, part)
    pts = surface.Points(spec, X, G, part, names, voxel, cache={"ao": ao_map[ys, xs, 0]}, streams=streams)
    masks: dict = {}
    ch = paint.apply_channels(spec, pts, base, masks=masks)
    log.append(f"painted in {time.time() - t2:.1f}s")
    # painted height: into the height map, and its slope tilts the normals (texel-sized differences)
    c = _corners(parts, "pos")
    texel = np.sqrt(np.linalg.norm(np.cross(c[:, 1] - c[:, 0], c[:, 2] - c[:, 0]), axis=1).sum() / 2 / max(len(tri), 1))
    t4 = time.time()
    b = paint.bump(spec, pts, 0.5 * texel, masks)
    if b is not None:
        X = X + b[0][:, None] * G  # the height map measures to the painted surface
        G = b[1]
        log.append(f"painted height (texel {texel * 1000:.2f} mm) in {time.time() - t4:.1f}s")

    height = ((X - P) * Nl).sum(1)
    tn = np.stack([(G * T).sum(1), (G * B).sum(1), (G * Nl).sum(1)], -1)
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
    maps["ao"] = ao_map
    put("normal", tn * 0.5 + 0.5, 0.5)
    put("height", (height / hr * 0.5 + 0.5)[:, None], 0.5)
    maps["orm"] = np.concatenate([maps["ao"], maps["roughness"], maps["metallic"]], -1)
    return {"maps": maps, "height_range": hr, "coverage": len(tri) / size ** 2}


def _ao_map(spec: dict, parts: dict, streams: dict, size: int, voxel: float) -> np.ndarray:
    """The AO map: occlusion is soft, so above 1024 it's computed at half the texture's resolution and scaled up
    (a quarter of the cost; it's the slowest map). Points are projected onto the exact surface as for the rest."""
    small = size // 2 if size >= 1024 else size
    (ys, xs), tri, bary, tpart = rasterize(parts, small)
    names = list(parts)
    P = np.einsum("nk,nkc->nc", bary, _corners(parts, "pos")[tri])
    N = _unit(np.einsum("nk,nkc->nc", bary, _corners(parts, "normal")[tri]))
    part = tpart[tri]
    for pi, pn in enumerate(names):
        sel = np.flatnonzero(part == pi)
        P[sel] = surface.newton(streams[pn], P[sel], 0.1 * voxel, voxel, iterations=2)[0]
    ao = surface.ao(list(streams.values()), P, N, voxel)
    img = np.ones((small, small))
    img[ys, xs] = ao
    filled = np.zeros((small, small), bool)
    filled[ys, xs] = True
    img = _dilate(img, filled)
    if small != size:
        img = np.asarray(Image.fromarray(img.astype(np.float32), "F").resize((size, size), Image.BILINEAR))
    return img[..., None].astype(np.float64)


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
            uv.astype(np.float32), inv.ravel().astype(np.uint32))


def _safe_unit(v: np.ndarray, fallback) -> np.ndarray:
    """Unit vectors; any zero-length one (glTF requires unit normals and tangents) becomes `fallback`."""
    n = np.linalg.norm(v, axis=1, keepdims=True)
    return np.where(n > 1e-9, v / np.maximum(n, 1e-12), np.asarray(fallback, float))


def write_glb(path: Path, name: str, parts: dict, images: dict[str, Path]):
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

    img_idx = {}
    for key, p in images.items():
        while len(bin_) % 4:
            bin_.append(0)
        raw = Path(p).read_bytes()
        views.append({"buffer": 0, "byteOffset": len(bin_), "byteLength": len(raw)})
        bin_.extend(raw)
        img_idx[key] = len(img_idx)
    meshes, nodes = [], []
    for pn, p in parts.items():
        pos, nrm, tan, uv, idx = _gltf_vertices(p)
        prim = {"attributes": {"POSITION": add(pos, 34962, 5126, "VEC3", True), "NORMAL": add(nrm, 34962, 5126, "VEC3"),
                               "TANGENT": add(tan, 34962, 5126, "VEC4"), "TEXCOORD_0": add(uv, 34962, 5126, "VEC2")},
                "indices": add(idx, 34963, 5125, "SCALAR"), "material": 0}
        meshes.append({"name": pn, "primitives": [prim]})
        nodes.append({"name": f"{name}_{pn}", "mesh": len(meshes) - 1})
    tex = {k: {"source": i, "sampler": 0} for k, i in img_idx.items()}
    textures = [tex[k] for k in images]
    ti = {k: i for i, k in enumerate(images)}
    material = {
        "name": f"{name}_material",
        "pbrMetallicRoughness": {"baseColorTexture": {"index": ti["basecolor"]},
                                 "metallicRoughnessTexture": {"index": ti["orm"]},
                                 "metallicFactor": 1.0, "roughnessFactor": 1.0},
        "normalTexture": {"index": ti["normal"]},
        "occlusionTexture": {"index": ti["orm"]},
        # specular 0..1 in the texture's alpha; 0.5 = F0 0.04 (dielectric default), as Blender's IOR level
        "extensions": {"KHR_materials_specular": {"specularTexture": {"index": ti["specular"]},
                                                  "specularFactor": 1.0, "specularColorFactor": [2.0, 2.0, 2.0]}},
    }
    doc = {"asset": {"version": "2.0", "generator": "hifipushie"}, "scene": 0,
           "scenes": [{"nodes": list(range(len(nodes)))}], "nodes": nodes, "meshes": meshes,
           "materials": [material], "textures": textures, "samplers": [{"magFilter": 9729, "minFilter": 9987}],
           # the images went into the buffer first: they are views 0..len(images)-1
           "images": [{"bufferView": i, "mimeType": "image/png"} for i in range(len(images))],
           "accessors": accessors, "bufferViews": views, "buffers": [{"byteLength": 0}],
           "extensionsUsed": ["KHR_materials_specular"]}
    while len(bin_) % 4:
        bin_.append(0)
    doc["buffers"][0]["byteLength"] = len(bin_)
    js = json.dumps(doc, separators=(",", ":")).encode()
    js += b" " * ((4 - len(js) % 4) % 4)
    with open(path, "wb") as f:
        f.write(struct.pack("<III", 0x46546C67, 2, 12 + 8 + len(js) + 8 + len(bin_)))
        f.write(struct.pack("<II", len(js), 0x4E4F534A) + js)
        f.write(struct.pack("<II", len(bin_), 0x004E4942) + bytes(bin_))


def export(name: str, out_dir: Path, triangles: int = 15000, texture: int = 2048, resolution: int = 256) -> dict:
    """Build, decimate + unwrap, bake every map, write PNGs, asset.glb and asset.json into out_dir."""
    log = []
    t = time.time()
    meta = store.build(name, resolution)
    spec = store.load(name)
    out_dir.mkdir(parents=True, exist_ok=True)
    high = prune_hidden(spec, Path(meta["mesh"]), out_dir / "high.npz", meta["voxel"], log)
    parts = lowpoly(high, out_dir / "lowpoly.npz", triangles, texture)
    high.unlink()
    ntri = sum(len(p["corner_vert"]) // 3 for p in parts.values())
    log.append(f"low poly: {ntri} triangles ({', '.join(f'{k} {len(p['corner_vert']) // 3}' for k, p in parts.items())}) "
               f"in {time.time() - t:.1f}s")
    res = bake(spec, parts, texture, meta["voxel"], log)
    maps = res["maps"]
    files = {}
    for key in ("basecolor", "normal", "orm", "roughness", "metallic", "specular", "ao"):
        files[key] = out_dir / f"{name}_{key}.png"
        _png(files[key], maps[key])
    files["height"] = out_dir / f"{name}_height.png"
    _png(files["height"], maps["height"], bits=16)
    # glTF reads specular from the alpha channel of its texture
    spec_rgba = out_dir / f"{name}_specular_gltf.png"
    a = (np.clip(maps["specular"][..., 0], 0, 1) * 255 + 0.5).astype(np.uint8)
    Image.fromarray(np.stack([np.full_like(a, 255)] * 3 + [a], -1), "RGBA").save(spec_rgba)
    glb = out_dir / f"{name}.glb"
    write_glb(glb, name, parts, {"basecolor": files["basecolor"], "orm": files["orm"], "normal": files["normal"],
                                 "specular": spec_rgba})
    spec_rgba.unlink()
    (out_dir / "lowpoly.npz").unlink()
    allv = np.concatenate([p["verts"] for p in parts.values()])
    info = {"glb": str(glb), "triangles": ntri, "bounds_blender": [allv.min(0).tolist(), allv.max(0).tolist()], "texture": texture, "height_range_m": res["height_range"],
            "maps": {k: str(v) for k, v in files.items()},
            "conventions": {"up": "+Y (glTF)", "front": "+Z", "units": "metres", "normal_map": "OpenGL (+Y), MikkTSpace",
                            "height": "0.5 = low-poly surface, 0/1 = -/+ height_range_m along the normal",
                            "orm": "R ambient occlusion, G roughness, B metallic",
                            "specular": "0.5 = F0 0.04 (Blender's IOR level)"},
            "seconds": round(time.time() - t, 1), "log": log}
    (out_dir / f"{name}.json").write_text(json.dumps(info, indent=1))
    return info


def preview(glb: Path, views: list[str], size: int = 512, samples: int = 24, focus=None, zoom: float = 1.0) -> Image.Image:
    """Render the exported GLB (as an engine would load it) with Cycles: checks the textures, not the model.
    Views as in look; the GLB is Y up, so the cameras are turned to match."""
    bounds = np.array(json.loads(glb.with_suffix(".json").read_text())["bounds_blender"])
    with tempfile.TemporaryDirectory(prefix="hifipushie-prev-") as tmp:
        frames = render.view_frames(bounds, views, focus, zoom)
        for f in frames:  # Blender's glTF importer converts back to Z up, so the look cameras apply as they are
            f["out"] = str(Path(tmp) / f"{f['name']}.png")
        _blender({"mode": "preview", "glb": str(glb), "views": frames, "size": size, "samples": samples})
        imgs = [Image.open(f["out"]).convert("RGB") for f in frames]
    return render.contact_sheet(imgs, frames)
