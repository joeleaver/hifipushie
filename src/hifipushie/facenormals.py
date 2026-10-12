"""LEARNED SURFACE NORMALS of a picture of a head (refread, 2026-10-11): what no outline sees, the surface INSIDE the
silhouette (cheek fullness, the planes of the face). The hand-built lambertian shading read failed its validation
(face_ruler._shade_obs: its own error is as large as a 2 mm cheek change's signal); this is the same idea with a
learned monocular normal estimator in the photometric model's place.

The estimator: Meta's Sapiens normal model, 0.3b (asset pack "facenormals"; CC BY-NC 4.0: a MEASURING TOOL, never
shipped), TorchScript on CPU in its own venv (HIFIPUSHIE_NORMALS_VENV, default /mnt/data/hifipushie/normals_venv:
torch CPU wheel + numpy + pillow), one subprocess per picture (~20-60 s, ~5 GB), cached by the crop's bytes.

  estimate(img, box)            unit normals of a 3:4 crop of the picture: {"n": (h, w, 3) float32 in the CAMERA frame
                                of face_ruler / likeness.render (x right, y down, z away from the camera), "box"}
  head_box(P, size)             the 3:4 crop a head wants
  at(res, px)                   normals at picture pixels (bilinear, renormalised)
Validation (spikes/refread/nrmval.py) and its verdict: the notes' "## refread".
"""
from __future__ import annotations

import hashlib
import os
import subprocess
import tempfile
from pathlib import Path

import numpy as np

VENV = os.environ.get("HIFIPUSHIE_NORMALS_VENV", "/mnt/data/hifipushie/normals_venv")
H, W = 1024, 768
THREADS = 8
# Sapiens' output axes -> the camera frame used here (x right, y down, z away from the camera): found on renders of
# known heads (spikes/refread/nrmaxes.py), the signs that make the estimate agree with the mesh's normals
AXES = np.diag([1.0, -1.0, -1.0])

_SRC = r'''
import sys, numpy as np, torch
from PIL import Image
model, src, dst, H, W, T = sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4]), int(sys.argv[5]), int(sys.argv[6])
torch.set_num_threads(T)
net = torch.jit.load(model, map_location="cpu").eval()
im = Image.open(src).convert("RGB").resize((W, H), Image.LANCZOS)
x = (np.asarray(im, np.float32) - [123.5, 116.5, 103.5]) / [58.5, 57.0, 57.5]
with torch.inference_mode():
    y = net(torch.from_numpy(x.transpose(2, 0, 1)[None].astype(np.float32)))
y = y[0].float().numpy().transpose(1, 2, 0)
y /= np.maximum(np.linalg.norm(y, axis=-1, keepdims=True), 1e-6)
np.savez_compressed(dst, n=y.astype(np.float16))
'''


def available() -> bool:
    from . import assets
    try:
        assets.pack("facenormals")
    except (FileNotFoundError, ValueError):
        return False
    return (Path(VENV) / "bin" / "python").exists()


def _cache_dir() -> Path:
    from . import store
    d = store.HOME / "_cache" / "facenormals"
    d.mkdir(parents=True, exist_ok=True)
    return d


def head_box(P, size, pad: float = 2.0) -> tuple:
    """The 3:4 crop for a head whose 68 landmarks project to P (picture px): pad x the landmarks' height tall."""
    P = np.asarray(P, float)
    c = 0.5 * (P.min(0) + P.max(0))
    h = pad * float(max(np.ptp(P[:, 1]), 0.8 * np.ptp(P[:, 0])))
    w = h * W / H
    return (c[0] - w / 2, c[1] - 0.55 * h, c[0] + w / 2, c[1] + 0.45 * h)


def estimate(img, box=None) -> dict:
    """The picture's surface normals on its crop box (x0, y0, x1, y1; 3:4; default the whole picture): {"n": (1024,
    768, 3) unit normals in the camera frame (x right, y down, z away from the camera), "box"}."""
    from . import assets, resources
    box = (0, 0, *img.size) if box is None else tuple(int(round(float(v))) for v in box)
    crop = img.convert("RGB").crop(box)
    a = np.asarray(crop)
    key = hashlib.sha1(a.tobytes() + str(a.shape).encode()).hexdigest()[:20]
    f = _cache_dir() / f"sapiens03_{key}.npz"
    if not f.exists():
        d = assets.pack("facenormals")
        if not (Path(VENV) / "bin" / "python").exists():
            raise FileNotFoundError(f"facenormals: no PyTorch venv at {VENV} (uv venv it and install torch (CPU), numpy, pillow; "
                                    "or set HIFIPUSHIE_NORMALS_VENV)")
        with tempfile.TemporaryDirectory(dir=str(_cache_dir())) as td:
            p = os.path.join(td, "in.png")
            crop.save(p)
            src = os.path.join(td, "nrm.py")
            Path(src).write_text(_SRC)
            with resources.heavy("facenormals (Sapiens 0.3b, CPU)", gb=6):
                r = subprocess.run([str(Path(VENV) / "bin" / "python"), src, str(d / "sapiens_0.3b_normal.pt2"), p,
                                    os.path.join(td, "out.npz"), str(H), str(W), str(THREADS)], capture_output=True, text=True,
                                   timeout=1800)
            if not os.path.exists(os.path.join(td, "out.npz")):
                raise RuntimeError(f"facenormals failed: {r.stderr[-600:]}")
            os.replace(os.path.join(td, "out.npz"), f)
    n = np.load(f)["n"].astype(np.float32) @ AXES.T
    return {"n": n, "box": box}


def at(res: dict, px) -> np.ndarray:
    """Unit normals at picture pixels px (n, 2); NaN outside the crop."""
    px = np.asarray(px, float)
    x0, y0, x1, y1 = res["box"]
    n = res["n"]
    h, w = n.shape[:2]
    u = (px[:, 0] - x0) / (x1 - x0) * w - 0.5
    v = (px[:, 1] - y0) / (y1 - y0) * h - 0.5
    ok = (u >= 0) & (v >= 0) & (u <= w - 1.001) & (v <= h - 1.001)
    uu, vv = np.clip(u, 0, w - 1.001), np.clip(v, 0, h - 1.001)
    i, j = np.floor(vv).astype(int), np.floor(uu).astype(int)
    fy, fx = (vv - i)[:, None], (uu - j)[:, None]
    out = n[i, j] * (1 - fx) * (1 - fy) + n[i, j + 1] * fx * (1 - fy) + n[i + 1, j] * (1 - fx) * fy + n[i + 1, j + 1] * fx * fy
    out /= np.maximum(np.linalg.norm(out, axis=1, keepdims=True), 1e-9)
    out[~ok] = np.nan
    return out
