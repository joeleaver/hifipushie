"""THE SURFACE A PICTURE SHOWS, read by a learned model: which way the surface faces at every pixel of a reference
picture of anything (a creature, a prop), and the relief those slopes add up to inside one part.

  normals(images)        unit normals per picture, (h, w, 3) float32: x right, y UP, z TOWARDS the viewer
  height(n, mask, px)    the relief the slopes add up to inside a region, metres towards the viewer (least squares;
                         each connected piece of the region floats on its own: nothing ties two pieces' depths)
  clay(n, mask)          the read lit as plain grey clay, to look at beside the picture

The reader: MoGe-2 ViT-L normal (Microsoft, MIT; weights Ruicheng/moge-2-vitl-normal, 1.3 GB) on the CPU in its own
venv (HIFIPUSHIE_SURFACE, default /mnt/data/hifipushie/measuremodels/surface: venv/ with torch CPU + moge, hf/ = its
weights), one subprocess for all the pictures asked for (~10 s to load, ~16 s a picture, ~5 GB), cached by each
picture's bytes. Only the SLOPES are used, added up inside one part at a time: a single picture's depth warps over a
whole figure (docs/notes/measuremodels.md: monocular depth as evidence is a dead end), and a part's depth and tilt
are set by its marks in the other views (relief_press.py).
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


def height(n: np.ndarray, mask: np.ndarray, px: float, steep: float = 0.2, pin: np.ndarray | None = None,
           pin_w: float = 1.0) -> np.ndarray:
    """The relief inside `mask` whose slopes are the read ones: metres towards the viewer per pixel (0 outside).
    `px` = metres per pixel; a normal facing less than `steep` towards the viewer counts as that steep (a grazing
    normal's slope is unbounded). `pin` (metres, NaN where free) holds the relief to known heights there, softly
    (weight `pin_w` against one slope): a piece with pins takes its depth from them, a piece without is zero-mean."""
    import scipy.sparse as sp
    import scipy.sparse.linalg as spl
    mask = np.asarray(mask, bool)
    nz = np.clip(n[..., 2], steep, None)
    p, q = -n[..., 0] / nz, n[..., 1] / nz          # dz/dx (to the right), dz/drow (downwards: y up = -row)
    idx = -np.ones(mask.shape, int)
    idx[mask] = np.arange(int(mask.sum()))
    rows, cols, vals, rhs, k = [], [], [], [], 0
    for dy, dx, g in ((0, 1, p), (1, 0, q)):
        a = mask[: mask.shape[0] - dy, : mask.shape[1] - dx] & mask[dy:, dx:]
        ia, ib = idx[: mask.shape[0] - dy, : mask.shape[1] - dx][a], idx[dy:, dx:][a]
        m = len(ia)
        rows += [np.arange(k, k + m)] * 2
        cols += [ib, ia]
        vals += [np.ones(m), -np.ones(m)]
        rhs.append(0.5 * (g[: mask.shape[0] - dy, : mask.shape[1] - dx][a] + g[dy:, dx:][a]))
        k += m
    out = np.zeros(mask.shape, np.float32)
    if not k:
        return out
    pinned = np.zeros(mask.shape, bool) if pin is None else (mask & np.isfinite(pin))
    if pinned.any():
        ip = idx[pinned]
        rows.append(np.arange(k, k + len(ip)))
        cols.append(ip)
        vals.append(np.full(len(ip), np.sqrt(pin_w)))
        rhs.append(np.sqrt(pin_w) * pin[pinned] / px)
        k += len(ip)
    A = sp.csr_matrix((np.concatenate(vals), (np.concatenate(rows), np.concatenate(cols))), shape=(k, int(mask.sum())))
    z = spl.spsolve((A.T @ A + 1e-6 * sp.identity(A.shape[1])).tocsc(), A.T @ np.concatenate(rhs))
    out[mask] = z * px
    from scipy import ndimage
    lab, m = ndimage.label(mask)
    for i in range(1, m + 1):
        if not pinned[lab == i].any():
            out[lab == i] -= out[lab == i].mean()
    return out


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
