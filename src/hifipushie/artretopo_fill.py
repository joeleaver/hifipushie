"""Artist retopo, step 3b: repair each bake (numpy / scipy / PIL; the spike used OpenCV).

Per tag ("low", "lod1", every prop):
  thin parts     -> the short-offset bake, where low_thin.png says the part is thin (both maps and the coverage)
  small misses   -> (coverage black inside an island: the rays found nothing) filled from the nearest covered texels,
                    then smoothed over the hole (the spike's TELEA inpaint, approximated)
  invented skin  -> (pinned surfaces; skin touching a prop) colour: the SURFACE-diffused colour (low_diffused.png;
                    else a pull-push of the trusted colour, for props); normals FLAT (no sculpted detail there)
  mouth inside   -> dark (RGB 70, 22, 38), flat normals
  margins        -> every island's colours pushed out over the gutter (no seams at mip levels)
Writes the maps in place (color.png, normal.png / <tag>_color.png, <tag>_normal.png)."""
from __future__ import annotations

import os

import numpy as np
from PIL import Image
from scipy import ndimage as nd

FLAT = np.array([128, 128, 255], np.float32)          # a flat tangent-space normal (RGB)
MOUTH = np.array([70, 22, 38], np.float32)


def _read(p):
    return np.asarray(Image.open(p)) if os.path.exists(p) else None


def _grey(a):
    return a if a is None or a.ndim == 2 else a[..., 0]


def pull_push(img, known):
    """unknown texels from a smooth multi-scale average of the known ones"""
    img = img.astype(np.float32); w = known.astype(np.float32)
    levels = [(img * w[..., None], w)]
    while min(levels[-1][1].shape) > 2:
        a, ww = levels[-1]
        h, wd = (ww.shape[0] // 2) * 2, (ww.shape[1] // 2) * 2
        a2 = a[:h, :wd].reshape(h // 2, 2, wd // 2, 2, -1).sum((1, 3)); w2 = ww[:h, :wd].reshape(h // 2, 2, wd // 2, 2).sum((1, 3))
        levels.append((a2, w2))
    a, ww = levels[-1]; filled = a / np.maximum(ww, 1e-6)[..., None]
    for a, ww in reversed(levels[:-1]):
        up = nd.zoom(filled, (ww.shape[0] / filled.shape[0], ww.shape[1] / filled.shape[1], 1), order=1)
        mine = a / np.maximum(ww, 1e-6)[..., None]; k = np.clip(ww * 4, 0, 1)[..., None]
        filled = mine * k + up * (1 - k)
    return filled


def inpaint(rgb, mask, passes=6):
    """fill masked texels: copy the nearest unmasked texel, then average inside the hole a few times"""
    if not mask.any():
        return rgb
    _, (iy, ix) = nd.distance_transform_edt(mask, return_indices=True)
    out = rgb[iy, ix].astype(np.float32)
    for _ in range(passes):
        sm = nd.uniform_filter(out, size=(3, 3, 1))
        out[mask] = sm[mask]
    return np.clip(out, 0, 255).astype(np.uint8)


def repair(D: str, tag: str) -> dict:
    j = lambda f: os.path.join(D, f)
    cpath = j("color.png") if tag == "low" else j(f"{tag}_color.png")
    npath = j("normal.png") if tag == "low" else j(f"{tag}_normal.png")
    col, nor = _read(cpath), _read(npath)
    cov = _grey(_read(j(f"{tag}_cover.png")))
    island = _grey(_read(j(f"{tag}_island.png"))) > 128
    thin = _grey(_read(j(f"{tag}_thin.png")))
    if thin is not None and os.path.exists(cpath.replace(".png", "_thinbake.png")):
        m = (thin.astype(np.float32) / 255)[..., None]
        col = (col * (1 - m) + _read(cpath.replace(".png", "_thinbake.png")) * m).astype(np.uint8)
        nor = (nor * (1 - m) + _read(npath.replace(".png", "_thinbake.png")) * m).astype(np.uint8)
        c1 = _grey(_read(j(f"{tag}_cover_thinbake.png")))
        if c1 is not None:
            cov = (cov * (1 - m[..., 0]) + c1 * m[..., 0]).astype(np.uint8)
    inv = _grey(_read(j(f"{tag}_invented.png")))
    invented = (inv > 64) & island if inv is not None else np.zeros_like(island)
    miss = (cov < 128) & island & ~invented
    rgb_c, rgb_n = col[..., :3].copy(), nor[..., :3].copy()
    mk = nd.binary_dilation(miss, np.ones((3, 3), bool))
    rgb_c = inpaint(rgb_c, mk); rgb_n = inpaint(rgb_n, mk)
    if invented.any():
        grow = nd.binary_dilation(invented, np.ones((5, 5), bool))
        dif = _read(j(f"{tag}_diffused.png"))
        pp = dif[..., :3].astype(np.float32) if dif is not None else pull_push(rgb_c, island & ~grow)
        soft = nd.gaussian_filter(grow.astype(np.float32), 3)[..., None]
        rgb_c = (rgb_c * (1 - soft) + pp * soft).astype(np.uint8)
        rgb_n = (rgb_n * (1 - soft) + FLAT * soft).astype(np.uint8)
    mouth = _grey(_read(j(f"{tag}_mouth.png")))
    if mouth is not None:
        mm = (mouth.astype(np.float32) / 255)[..., None]
        rgb_c = (rgb_c * (1 - mm) + MOUTH * mm).astype(np.uint8)
        rgb_n = (rgb_n * (1 - mm) + FLAT * mm).astype(np.uint8)
    for arr in (rgb_c, rgb_n):                      # push island colours out over the margin
        g = nd.grey_dilation(arr, size=(5, 5, 1)); arr[~island] = g[~island]
    for arr, pth, orig in ((rgb_c, cpath, col), (rgb_n, npath, nor)):
        out = np.dstack([arr, orig[..., 3]]) if orig.ndim == 3 and orig.shape[2] == 4 else arr
        Image.fromarray(out).save(pth)
    return {"tag": tag, "misses": int(miss.sum()), "invented": int(invented.sum())}


def repair_all(D: str) -> list[dict]:
    """every baked tag in the folder"""
    tags = ["low"] + (["lod1"] if os.path.exists(os.path.join(D, "lod1_cover.png")) else [])
    tags += sorted(f[:-10] for f in os.listdir(D) if f.endswith("_cover.png") and f[:-10] not in ("low", "lod1")
                   and not f.endswith("_thick_cover.png"))
    return [repair(D, t) for t in tags]
