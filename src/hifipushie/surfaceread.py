"""THE SURFACE A PICTURE SHOWS, read by a learned model: which way the surface faces at every pixel of a reference
picture of anything (a creature, a prop), and the relief those slopes add up to inside one part.

  normals(images)        unit normals per picture, (h, w, 3) float32: x right, y UP, z TOWARDS the viewer
  height(n, mask, px)    the relief the slopes add up to inside a region, metres towards the viewer (least squares;
                         each connected piece of the region floats on its own: nothing ties two pieces' depths)
  clay(n, mask)          the read lit as plain grey clay, to look at beside the picture

The reader: MoGe-2 ViT-L normal (Microsoft, MIT; weights Ruicheng/moge-2-vitl-normal, 1.3 GB) on the CPU in its own
venv (HIFIPUSHIE_SURFACE, default /mnt/data/hifipushie/measuremodels/surface: venv/ with torch CPU + moge, hf/ = its
weights), one subprocess for all the pictures asked for (~10 s to load, ~16 s a picture, ~5 GB), cached by each
picture's bytes. Only the SLOPES are used, added up inside one continuous region at a time: a single picture's depth
warps over a whole figure (docs/notes/measuremodels.md: monocular depth as evidence is a dead end). One picture read as
one surface is a clean, real relief; several pictures' reads do not join into one solid, and a read pressed in part
by part tears at every part border (docs/state/feature_map.md: tried, closed 2026-11-14; that code is at the tag
archive/feature-map-closed-route). Use it to SEE: a grey-clay target beside a sculpt.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
from pathlib import Path

import numpy as np

ROOT = os.environ.get("HIFIPUSHIE_SURFACE", "/mnt/data/hifipushie/measuremodels/surface")
THREADS = 12
LIGHT = (-0.5, 0.55, 0.67)

_SRC = r'''
import sys, json, numpy as np, torch
from PIL import Image
jobs, T = json.load(open(sys.argv[1])), int(sys.argv[2])
torch.set_num_threads(T)
from moge.model.v2 import MoGeModel
model = MoGeModel.from_pretrained("Ruicheng/moge-2-vitl-normal").eval()
for src, dst in jobs:
    x = torch.tensor(np.asarray(Image.open(src).convert("RGB")) / 255.0, dtype=torch.float32).permute(2, 0, 1)
    with torch.no_grad():
        out = model.infer(x, use_fp16=False, apply_mask=False)
    n = np.nan_to_num(out["normal"].cpu().numpy().astype(np.float32)) * np.array([1, -1, -1], np.float32)
    n /= np.maximum(np.linalg.norm(n, axis=-1, keepdims=True), 1e-6)   # MoGe: x right, y down, z away
    np.save(dst, n.astype(np.float16))
'''


def available() -> bool:
    return (Path(ROOT) / "venv" / "bin" / "python").exists()


def _cache_dir() -> Path:
    from . import store
    d = store.HOME / "_cache" / "surfaceread"
    d.mkdir(parents=True, exist_ok=True)
    return d


def normals(images: list) -> list[np.ndarray]:
    """Unit normals of each picture (PIL images, RGB), (h, w, 3): x right, y up, z towards the viewer."""
    from . import resources
    keys, todo = [], {}
    for im in images:
        a = np.asarray(im.convert("RGB"))
        k = hashlib.sha1(a.tobytes() + str(a.shape).encode()).hexdigest()[:20]
        keys.append(k)
        if not (_cache_dir() / f"moge2_{k}.npy").exists():
            todo[k] = im
    if todo:
        py = Path(ROOT) / "venv" / "bin" / "python"
        if not py.exists():
            raise FileNotFoundError(f"surfaceread: no reader at {ROOT} (a venv with torch (CPU) and moge, and hf/ with "
                                    "Ruicheng/moge-2-vitl-normal; or set HIFIPUSHIE_SURFACE)")
        with tempfile.TemporaryDirectory(dir=str(_cache_dir())) as td:
            jobs = []
            for k, im in todo.items():
                src = os.path.join(td, f"{k}.png")
                im.convert("RGB").save(src)
                jobs.append([src, os.path.join(td, f"{k}.npy")])
            Path(td, "jobs.json").write_text(json.dumps(jobs))
            Path(td, "read.py").write_text(_SRC)
            env = dict(os.environ, HF_HOME=str(Path(ROOT) / "hf"), HF_HUB_OFFLINE="1")
            env.pop("PYTHONPATH", None)
            with resources.heavy(f"surfaceread (MoGe-2, CPU, {len(jobs)} pictures)", gb=6, kind="surfaceread_cpu"):
                r = subprocess.run([str(py), os.path.join(td, "read.py"), os.path.join(td, "jobs.json"), str(THREADS)],
                                   capture_output=True, text=True, timeout=3600, env=env)
            for (_, dst), k in zip(jobs, todo):
                if not os.path.exists(dst):
                    raise RuntimeError(f"surfaceread failed: {r.stderr[-800:]}")
                os.replace(dst, _cache_dir() / f"moge2_{k}.npy")
    return [np.load(_cache_dir() / f"moge2_{k}.npy").astype(np.float32) for k in keys]


MEMBRANE = 0.05     # the weight of "no slope" where the read doesn't count, against one read slope


def height(n: np.ndarray, mask: np.ndarray, px: float, steep: float = 0.2, pin: np.ndarray | None = None,
           pin_w: float = 1.0, data: np.ndarray | None = None, gain: tuple | None = None, parts: bool = False):
    """The relief inside `mask` whose slopes are the read ones: metres towards the viewer per pixel (0 outside).
    `px` = metres per pixel; a normal facing less than `steep` towards the viewer counts as that steep (a grazing
    normal's slope is unbounded).
    pin    metres, NaN where free: holds the relief to known heights there, softly (weight `pin_w` against one
           slope). A piece with pins takes its depth from them, a piece without is zero-mean.
    data   where the read counts (default: all of `mask`); the rest of the mask is carried through smoothly (a
           membrane): the surface under a part that stands in front.
    gain   (lowest, highest): a read mutes or exaggerates depth as a whole. With pins in two places that differ in
           depth, the one scale of the slopes that agrees best with them is solved too; returns (relief, gain).
    parts  returns (what the pins alone make, what the slopes alone make): the relief is the first plus any gain
           times the second, for a caller who has its own measure of the gain.
    The pins' weights are per pixel: on a finer grid the same hold needs them smaller, as the pixel's area."""
    import scipy.sparse as sp
    import scipy.sparse.linalg as spl
    from scipy import ndimage
    mask = np.asarray(mask, bool)
    data = mask if data is None else (np.asarray(data, bool) & mask)
    nz = np.clip(n[..., 2], steep, None)
    p, q = -n[..., 0] / nz, n[..., 1] / nz          # dz/dx (to the right), dz/drow (downwards: y up = -row)
    idx = -np.ones(mask.shape, int)
    idx[mask] = np.arange(int(mask.sum()))
    rows, cols, vals, rhs, k = [], [], [], [], 0
    H, W = mask.shape
    for dy, dx, g in ((0, 1, p), (1, 0, q)):
        a = mask[: H - dy, : W - dx] & mask[dy:, dx:]
        ia, ib = idx[: H - dy, : W - dx][a], idx[dy:, dx:][a]
        both = (data[: H - dy, : W - dx] & data[dy:, dx:])[a]
        wt = np.where(both, 1.0, np.sqrt(MEMBRANE))
        m = len(ia)
        rows += [np.arange(k, k + m)] * 2
        cols += [ib, ia]
        vals += [wt, -wt]
        rhs.append(np.where(both, 0.5 * (g[: H - dy, : W - dx][a] + g[dy:, dx:][a]), 0.0))
        k += m
    out = np.zeros(mask.shape, np.float32)
    if not k:
        return (out, 1.0) if gain else out
    bg = np.concatenate(rhs)
    pinned = np.zeros(mask.shape, bool) if pin is None else (mask & np.isfinite(pin))
    bp = np.zeros(0)
    if pinned.any():
        ip = idx[pinned]
        rows.append(np.arange(k, k + len(ip)))
        cols.append(ip)
        pw = np.sqrt(np.broadcast_to(np.asarray(pin_w, float), mask.shape)[pinned])   # one weight, or one per pixel
        vals.append(pw)
        bp = pw * pin[pinned] / px
        k += len(ip)
    A = sp.csr_matrix((np.concatenate(vals), (np.concatenate(rows), np.concatenate(cols))), shape=(k, int(mask.sum())))
    solve = spl.factorized((A.T @ A + 1e-6 * sp.identity(A.shape[1])).tocsc())
    b_g, b_p = np.r_[bg, np.zeros(len(bp))], np.r_[np.zeros(len(bg)), bp]
    zg = solve(A.T @ b_g)                            # the slopes alone (pins at zero)
    zp = solve(A.T @ b_p) if len(bp) else np.zeros_like(zg)   # the pins alone (no slopes)
    if parts:
        a, b = np.zeros(mask.shape, np.float32), np.zeros(mask.shape, np.float32)
        a[mask], b[mask] = zp * px, zg * px
        return a, b
    g1 = 1.0
    if gain and len(bp):                             # the energy is quadratic in the gain: its best value in one step
        r0, r1 = A @ zp - b_p, A @ zg - b_g
        g1 = float(np.clip(-(r0 @ r1) / max(r1 @ r1, 1e-12), *gain))
    out[mask] = (zp + g1 * zg) * px
    lab, m = ndimage.label(mask)
    for i in range(1, m + 1):
        if not pinned[lab == i].any():
            out[lab == i] -= out[lab == i].mean()
    return (out, g1) if gain else out


def clay(n: np.ndarray, mask: np.ndarray | None = None, light=LIGHT, bg=(236, 236, 232)):
    """The read lit as plain grey clay (a PIL image): what the surface would look like with no paint on it."""
    from PIL import Image
    lv = np.asarray(light, np.float32)
    lv /= np.linalg.norm(lv)
    sh = 0.14 + 0.86 * np.clip((n.astype(np.float32) * lv).sum(-1), 0, 1)
    col = np.array([208, 203, 196], np.float32)[None, None] * sh[..., None]
    if mask is not None:
        col = np.where(np.asarray(mask, bool)[..., None], col, np.array(bg, np.float32)[None, None])
    return Image.fromarray(col.clip(0, 255).astype(np.uint8))
