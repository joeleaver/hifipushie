"""Texture repaint: the SURFACE a painter works on. A repaint never edits pixels as pixels; it works on texels as points
on the model: every texel of a map knows its 3D position, normal, part and UV island, so masks are smoothed ON THE
SURFACE (across UV seams, never across empty UV space) and concept views are projected onto it with a depth test.

  dump(glb, folder)          Blender: triangles (world corners, normals, UVs, image, object) + the GLB's maps
  Surface.load(folder)       the dumped triangles
  surface.texels(image, res) rasterise one map's triangles at res: Texels (index, pos, nrm, tri, obj)
  Grid / smooth3d            fields splatted into a 3D grid, blurred, read back at each texel (the surface blur)
  surface.view(axis, res)    an orthographic depth render of the model (visibility for projections)
Rasterising is plain numpy (no Blender) so tests run in milliseconds on a synthetic sphere."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from scipy import ndimage

HERE = Path(__file__).parent


def folder(name: str) -> Path:
    if "/" in name:
        return Path(name)
    from . import store
    return store.HOME / "texrepaint" / name


def blender(job: dict, gb: float, gpu: bool = False, timeout: float = 1800) -> str:
    import tempfile
    from . import render, resources
    with tempfile.TemporaryDirectory(prefix="hifipushie-texrepaint-") as tmp:
        p = Path(tmp) / "job.json"; p.write_text(json.dumps(job))
        with resources.heavy(f"texrepaint {job['mode']}", gb=gb, gpu=gpu):
            r = resources.run([render.BLENDER, "-b", *render._threads(), "--factory-startup", "--python-exit-code", "1",
                               "--python", str(HERE / "blender_texrepaint.py"), "--", str(p)],
                              capture_output=True, text=True, timeout=timeout)
    if r.returncode:
        raise RuntimeError(f"blender texrepaint {job['mode']} failed:\n{r.stdout[-3000:]}\n{r.stderr[-2000:]}")
    return r.stdout


def dump(glb: str | Path, d: Path) -> dict:
    d.mkdir(parents=True, exist_ok=True)
    blender({"mode": "dump", "glb": str(glb), "out": str(d / "surface.npz"), "maps": str(d / "maps")}, gb=3)
    return json.loads((d / "surface.json").read_text())


@dataclass
class Texels:
    res: int
    idx: np.ndarray        # (n,) flat index into the res x res map (row 0 = TOP of the image, v = 1)
    pos: np.ndarray        # (n,3)
    nrm: np.ndarray        # (n,3)
    tri: np.ndarray        # (n,) triangle index
    obj: np.ndarray        # (n,) object index

    def image(self, values, fill=0, dtype=None):
        """scatter per-texel values back into a res x res (x C) image"""
        values = np.asarray(values)
        shp = (self.res * self.res,) + values.shape[1:]
        out = np.full(shp, fill, dtype or values.dtype); out[self.idx] = values
        return out.reshape((self.res, self.res) + values.shape[1:])

    def sample(self, img):
        """per-texel values of a map of ANY resolution (bilinear at the texel centre)"""
        img = np.asarray(img); H, W = img.shape[:2]
        r, c = np.divmod(self.idx, self.res)
        y = (r + 0.5) * H / self.res - 0.5; x = (c + 0.5) * W / self.res - 0.5
        if img.ndim == 2:
            return ndimage.map_coordinates(img.astype(np.float32), [y, x], order=1, mode="nearest")
        return np.stack([ndimage.map_coordinates(img[..., k].astype(np.float32), [y, x], order=1, mode="nearest")
                         for k in range(img.shape[2])], 1)

    def mask(self):
        m = np.zeros(self.res * self.res, bool); m[self.idx] = True
        return m.reshape(self.res, self.res)


def raster(tri2d: np.ndarray, W: int, H: int, depth: np.ndarray | None = None):
    """rasterise triangles given in pixel coordinates (T,3,2) (x right, y down) into a W x H buffer: per pixel the
    triangle id (-1 none) and barycentrics; with depth (T,3) keeps the NEAREST (smallest depth) triangle"""
    tid = np.full(H * W, -1, np.int32); bc = np.zeros((H * W, 2), np.float32)
    zb = np.full(H * W, np.inf, np.float32) if depth is not None else None
    lo = np.floor(tri2d.min(1)).astype(int); hi = np.ceil(tri2d.max(1)).astype(int)
    lo = np.maximum(lo, 0); hi[:, 0] = np.minimum(hi[:, 0], W - 1); hi[:, 1] = np.minimum(hi[:, 1], H - 1)
    for t in np.nonzero((hi >= lo).all(1))[0]:
        (x0, y0), (x1, y1) = lo[t], hi[t]
        xs, ys = np.meshgrid(np.arange(x0, x1 + 1) + 0.5, np.arange(y0, y1 + 1) + 0.5)
        a, b, c = tri2d[t]
        den = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1])
        if abs(den) < 1e-12:
            continue
        l0 = ((b[1] - c[1]) * (xs - c[0]) + (c[0] - b[0]) * (ys - c[1])) / den
        l1 = ((c[1] - a[1]) * (xs - c[0]) + (a[0] - c[0]) * (ys - c[1])) / den
        l2 = 1 - l0 - l1
        e = -1e-4
        ins = (l0 >= e) & (l1 >= e) & (l2 >= e)
        if not ins.any():
            continue
        pix = ((ys[ins] - 0.5).astype(int) * W + (xs[ins] - 0.5).astype(int))
        if depth is None:
            tid[pix] = t; bc[pix, 0] = l0[ins]; bc[pix, 1] = l1[ins]
        else:
            z = l0[ins] * depth[t, 0] + l1[ins] * depth[t, 1] + l2[ins] * depth[t, 2]
            near = z < zb[pix]
            pix, z = pix[near], z[near]
            zb[pix] = z; tid[pix] = t; bc[pix, 0] = l0[ins][near]; bc[pix, 1] = l1[ins][near]
    return tid, bc, zb


class Surface:
    def __init__(self, P, N, UV, img, obj, meta):
        self.P, self.N, self.UV, self.img, self.obj, self.meta = P, N, UV, img, obj, meta

    @classmethod
    def load(cls, d: Path):
        z = np.load(d / "surface.npz"); meta = json.loads((d / "surface.json").read_text())
        return cls(z["P"], z["N"], z["UV"], z["img"], z["obj"], meta)

    def image_index(self, image: str | None) -> int:
        ims = self.meta["images"]
        if image is None:  # the map most triangles use
            return int(np.bincount(self.img[self.img >= 0]).argmax())
        for k, n in enumerate(ims):
            if n == image or Path(n).stem == Path(image).stem:
                return k
        raise ValueError(f"image {image!r} not in the model; its maps: {ims}")

    def texels(self, image: str | None, res: int) -> Texels:
        k = self.image_index(image)
        names = self.meta["objects"]
        lod = np.array(["lod" in n.lower() and "lod0" not in n.lower() for n in names])
        T = np.nonzero((self.img == k) & ~lod[self.obj])[0]   # LOD copies share the UVs: the texel is LOD0's
        if not len(T):
            T = np.nonzero(self.img == k)[0]
        uv = self.UV[T]; px = np.stack([uv[..., 0] * res, (1 - uv[..., 1]) * res], -1)
        tid, bc, _ = raster(px, res, res)
        idx = np.nonzero(tid >= 0)[0]; t = tid[idx]; b = bc[idx]
        w = np.stack([b[:, 0], b[:, 1], 1 - b[:, 0] - b[:, 1]], 1)[..., None]
        gt = T[t]
        pos = (self.P[gt] * w).sum(1); nrm = (self.N[gt] * w).sum(1)
        nrm /= np.maximum(np.linalg.norm(nrm, axis=1, keepdims=True), 1e-9)
        return Texels(res, idx, pos.astype(np.float32), nrm.astype(np.float32), gt, self.obj[gt])

    def bounds(self):
        p = self.P.reshape(-1, 3); return p.min(0), p.max(0)

    def view(self, axis: str, px_per_m: float, lo=None, hi=None):
        """orthographic depth render along a view: 'front' (from -y), 'back' (+y), 'side' (+x, faces left),
        'side_r' (-x). Returns View with the image <-> world mapping and the depth buffer."""
        lo = self.bounds()[0] if lo is None else lo; hi = self.bounds()[1] if hi is None else hi
        return View(axis, self, px_per_m, lo, hi)


AXES = {"front": (np.array([1, 0, 0]), np.array([0, -1, 0])), "back": (np.array([-1, 0, 0]), np.array([0, 1, 0])),
        "side": (np.array([0, 1, 0]), np.array([1, 0, 0])), "side_r": (np.array([0, -1, 0]), np.array([-1, 0, 0]))}


class View:
    """image x = right axis, image y = down (-z); depth = distance from the camera (toward -toward)"""

    def __init__(self, axis, surf: Surface, ppm, lo, hi):
        self.axis = axis; self.right, self.toward = AXES[axis]; self.ppm = ppm
        corners = np.array([[x, y, z] for x in (lo[0], hi[0]) for y in (lo[1], hi[1]) for z in (lo[2], hi[2])])
        r = corners @ self.right
        self.r0, self.z1 = r.min(), hi[2]
        self.W = int(np.ceil((r.max() - r.min()) * ppm)) + 2; self.H = int(np.ceil((hi[2] - lo[2]) * ppm)) + 2
        px = self.project(surf.P.reshape(-1, 3))[0].reshape(-1, 3, 2)
        dep = -(surf.P @ self.toward)
        self.tid, self.bc, zb = raster(px, self.W, self.H, depth=dep)
        self.depth = zb.reshape(self.H, self.W); self.surf = surf

    def textured(self, image_index: int, tex: np.ndarray, step: int = 2):
        """the model as this view sees it, coloured by its own texture: (rows, cols, rgb) of the pixels (every
        `step`-th) whose triangle uses that map"""
        pix = np.nonzero(self.tid >= 0)[0][::step]; t = self.tid[pix]
        ok = self.surf.img[t] == image_index; pix, t = pix[ok], t[ok]
        b = self.bc[pix]; w = np.stack([b[:, 0], b[:, 1], 1 - b[:, 0] - b[:, 1]], 1)[..., None]
        uv = (self.surf.UV[t] * w).sum(1); H, W = tex.shape[:2]
        x = np.clip((uv[:, 0] * W).astype(int), 0, W - 1); y = np.clip(((1 - uv[:, 1]) * H).astype(int), 0, H - 1)
        r, c = np.divmod(pix, self.W)
        return r, c, tex[y, x]

    def project(self, pts):
        x = (pts @ self.right - self.r0) * self.ppm; y = (self.z1 - pts[:, 2]) * self.ppm
        return np.stack([x, y], -1), -(pts @ self.toward)

    def silhouette(self):
        return np.isfinite(self.depth)

    def visible(self, pts, nrm, tol=0.004, min_cos=0.25):
        """which points this view sees (depth test + facing), and the facing cosine"""
        xy, d = self.project(pts)
        xi = np.clip(xy[:, 0].astype(int), 0, self.W - 1); yi = np.clip(xy[:, 1].astype(int), 0, self.H - 1)
        cos = nrm @ self.toward
        return (d <= self.depth[yi, xi] + tol) & (cos > min_cos), cos, xy


class Grid:
    """a 3D grid over the texel cloud: splat per-texel values, blur, read back = smoothing ON THE SURFACE"""

    def __init__(self, pos: np.ndarray, voxel: float):
        self.lo = pos.min(0) - 4 * voxel; self.h = voxel
        self.shape = tuple(np.ceil((pos.max(0) + 4 * voxel - self.lo) / voxel).astype(int) + 1)
        self.ijk = (pos - self.lo) / voxel

    def splat(self, values, weights=None):
        g = np.zeros(self.shape, np.float32); n = np.zeros(self.shape, np.float32)
        i = np.round(self.ijk).astype(int).T
        w = np.ones(len(self.ijk), np.float32) if weights is None else weights.astype(np.float32)
        np.add.at(g, tuple(i), values * w); np.add.at(n, tuple(i), w)
        return g, n

    def smooth(self, values, sigma: float, weights=None):
        """weighted Gaussian average (sigma in metres) of per-texel values, read back at every texel"""
        g, n = self.splat(values, weights)
        s = sigma / self.h
        g = ndimage.gaussian_filter(g, s, truncate=2.5); n = ndimage.gaussian_filter(n, s, truncate=2.5)
        gv = ndimage.map_coordinates(g, self.ijk.T, order=1); nv = ndimage.map_coordinates(n, self.ijk.T, order=1)
        return gv / np.maximum(nv, 1e-6), nv

    def components(self, flags):
        """connected clusters (in 3D, across seams) of the flagged texels: label per texel (0 = not flagged)"""
        g = np.zeros(self.shape, bool); i = np.round(self.ijk).astype(int).T
        g[tuple(i[:, flags])] = True
        g = ndimage.binary_closing(g, iterations=1)
        lab, n = ndimage.label(g, structure=np.ones((3, 3, 3)))
        out = lab[tuple(i)]; out[~flags] = 0
        return out, n


def pad(img: np.ndarray, mask: np.ndarray, px: int = 12) -> np.ndarray:
    """edge padding: grow the islands' colours outward px texels (no bleeding of black into mips)"""
    out = img.copy().astype(np.float32); m = mask.copy()
    sz = (3, 3, 1) if out.ndim == 3 else (3, 3)
    for _ in range(px):
        grown = ndimage.binary_dilation(m) & ~m
        if not grown.any():
            break
        mm = m[..., None] if out.ndim == 3 else m
        acc = ndimage.uniform_filter(out * mm, sz); cnt = ndimage.uniform_filter(m.astype(np.float32), 3)
        val = acc / (np.maximum(cnt, 1e-6)[..., None] if out.ndim == 3 else np.maximum(cnt, 1e-6))
        out[grown] = val[grown]; m = m | grown
    out[~m] = out[m].mean(0) if m.any() else 0
    return out
