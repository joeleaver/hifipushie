"""Tiling layers: a layer's height and textures, PNG / JPEG, the material. Part of the terrain's bake (terrain_bake.py has the overview)."""
from __future__ import annotations

import io

import numpy as np

from . import terrain_bake
from .terrain_bake import _unit

def _spectral(n, beta, seed, stretch=(1.0, 1.0)):
    """Tileable noise (n x n): random phases with a 1 / f^beta spectrum, zero mean, unit range."""
    rng = np.random.default_rng(seed)
    fx = np.fft.fftfreq(n)[None, :] * stretch[0]
    fy = np.fft.fftfreq(n)[:, None] * stretch[1]
    f = np.sqrt(fx * fx + fy * fy)
    f[0, 0] = 1.0
    amp = f ** -beta
    amp[0, 0] = 0.0
    z = np.real(np.fft.ifft2(amp * np.exp(2j * np.pi * rng.random((n, n)))))
    z -= z.min()
    return z / max(z.max(), 1e-12)


def layer_height(name, n=512):
    kind, _ = terrain_bake.LAYER_DETAIL.get(name, ("grain", 0.3))
    s = zlib_seed(name)
    if kind == "grit":
        # grit and lumps only: any Voronoi crack net, even broken up, tiled into honeycomb paving across a cliff (the
        # cracks are the rock's own, in the baked maps)
        h = 0.35 * _spectral(n, 1.6, s + 1) + 0.35 * _spectral(n, 1.0, s + 2) + 0.3 * _spectral(n, 0.6, s + 4)
    elif kind == "ripples":
        h = 0.6 * _spectral(n, 2.2, s, stretch=(0.15, 1.0)) + 0.4 * _spectral(n, 0.8, s + 1)
    elif kind == "blades":
        h = 0.5 * _spectral(n, 0.6, s, stretch=(1.0, 0.25)) + 0.5 * _spectral(n, 1.4, s + 1)
    elif kind == "litter":
        h = 0.6 * (_spectral(n, 2.0, s) > 0.55) + 0.4 * _spectral(n, 1.0, s + 1)
    elif kind == "clods":
        h = 0.7 * _spectral(n, 1.8, s) + 0.3 * _spectral(n, 0.9, s + 1)
    elif kind == "soft":
        h = _spectral(n, 2.4, s)
    else:
        h = _spectral(n, 1.0, s)
    lo, hi = np.percentile(h, [1, 99])  # (full contrast: a few extremes had squeezed the rest into a grey)
    return np.clip((h - lo) / max(hi - lo, 1e-12), 0, 1)


def zlib_seed(name):
    import zlib
    return zlib.crc32(name.encode()) % 100000


def layer_textures(out_dir, layers: dict) -> dict:
    """Tileable textures per layer in out_dir/materials: <layer>_albedo.png (the layer's reference colour varied by
    its pattern, mean = the colour), <layer>_normal.png (glTF convention) and <layer>_height.png. {layer: files}."""
    from PIL import Image
    d = out_dir / "materials"
    d.mkdir(exist_ok=True)
    res = {}
    for name, ref in layers.items():
        h = layer_height(name)
        _, strength = terrain_bake.LAYER_DETAIL.get(name, ("grain", 0.3))
        col = np.array(ref["color"], float)
        mod = 1.0 + 0.8 * strength * (h - h.mean())
        alb = np.clip(col[None, None, :] * mod[..., None], 0, 1)
        n = h.shape[0]
        texel = float(ref.get("scale", 3.0)) / n
        depth = 0.02 * strength * float(ref.get("scale", 3.0))  # (pattern relief: a few cm per metre of tile)
        gx = (np.roll(h, -1, 1) - np.roll(h, 1, 1)) * depth / (2 * texel)
        gy = (np.roll(h, 1, 0) - np.roll(h, -1, 0)) * depth / (2 * texel)  # (+y = up the image)
        nm = _unit(np.stack([-gx, -gy, np.ones_like(gx)], -1))
        files = {}
        for key, img in (("albedo", (alb * 255).round().astype(np.uint8)),
                         ("normal", ((nm * 0.5 + 0.5) * 255).round().astype(np.uint8)),
                         ("height", (h * 255).round().astype(np.uint8))):
            fn = f"materials/{name}_{key}.png"
            Image.fromarray(img).save(out_dir / fn)
            files[key] = fn
        res[name] = {**files, "detail_strength": strength}
    return res


def png(a, mode=None):
    from PIL import Image
    b = io.BytesIO()
    if a.dtype == np.uint16:
        Image.fromarray(a, "I;16").save(b, format="PNG")
    else:
        Image.fromarray(a, mode).save(b, format="PNG", optimize=False, compress_level=6)
    return b.getvalue()


def jpeg(a, q=90):
    from PIL import Image
    b = io.BytesIO()
    Image.fromarray(a, "RGB").save(b, format="JPEG", quality=q)
    return b.getvalue()


def material(name, rough=1.0):
    """The reference glTF material over the baked maps: base colour (texture 0), ORM (texture 1: occlusion R,
    roughness G, metallic B = 0), normal (texture 2). Shows the terrain as authored in any glTF viewer."""
    return {"name": name, "pbrMetallicRoughness": {"baseColorTexture": {"index": 0}, "metallicFactor": 0.0,
                                                   "roughnessFactor": rough,
                                                   "metallicRoughnessTexture": {"index": 1}},
            "normalTexture": {"index": 2}, "occlusionTexture": {"index": 1}}
