"""Detection: MediaPipe in its own venv, cached; a region's detection, the head's yaw. Part of likeness (likeness.py has the overview)."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
from pathlib import Path

import numpy as np

from . import likeness

def detector_available() -> bool:
    return (Path(likeness.VENV) / "bin" / "python").exists() and (Path(likeness.VENV) / "face_landmarker.task").exists()


def _cache_dir() -> Path:
    from . import store
    d = store.HOME / "_cache" / "likeness"
    d.mkdir(parents=True, exist_ok=True)
    return d


def detect_info(images: list) -> list:
    """PIL images -> [{"P": (478, 2) pixels, "bs": blendshape scores, "M": head pose 4x4} | None] (MediaPipe Face
    Landmarker), cached by the image's bytes."""
    if not detector_available():
        return [None] * len(images)
    out, todo, keys = [None] * len(images), [], []
    for i, im in enumerate(images):
        k = hashlib.sha1(np.asarray(im.convert("RGB")).tobytes() + str(im.size).encode()).hexdigest()[:20]
        keys.append(k)
        f = _cache_dir() / f"mp2_{k}.json"
        if f.exists():
            out[i] = json.loads(f.read_text())
        else:
            todo.append(i)
    if todo:
        with tempfile.TemporaryDirectory() as td:
            paths = []
            for i in todo:
                p = os.path.join(td, f"{i}.png")
                images[i].convert("RGB").save(p)
                paths.append(p)
            res = os.path.join(td, "out.json")
            src = os.path.join(td, "det.py")
            Path(src).write_text(likeness._DETECT_SRC)
            subprocess.run([str(Path(likeness.VENV) / "bin" / "python"), src, res, str(Path(likeness.VENV) / "face_landmarker.task"), *paths],
                           check=True, capture_output=True, timeout=300)
            got = json.loads(Path(res).read_text())
        for i, v in zip(todo, got):
            (_cache_dir() / f"mp2_{keys[i]}.json").write_text(json.dumps(v))
            out[i] = v
    for v in out:
        if v is not None:
            v["P"] = np.asarray(v["P"], float)
    return out


def detect(images: list) -> list:
    """PIL images -> [(478, 2) pixel array | None]."""
    return [None if v is None else v["P"] for v in detect_info(images)]


def detect_region(img, box, info: bool = False):
    """Detect on a crop of a big picture (a full figure: MediaPipe wants the face to fill the frame), scaled to
    DETECT_PX; points back in the picture's pixels (info=True: the detector's dict with "P" in picture pixels)."""
    from PIL import Image
    x0, y0, x1, y1 = (float(v) for v in box)
    c = img.crop((int(round(x0)), int(round(y0)), int(round(x1)), int(round(y1))))
    s = likeness.DETECT_PX / max(c.size)
    c = c.resize((max(1, int(round(c.size[0] * s))), max(1, int(round(c.size[1] * s)))), Image.LANCZOS)
    d = detect_info([c])[0]
    if d is None:
        return None
    d = dict(d)
    d["P"] = d["P"] / s + [int(round(x0)), int(round(y0))]
    return d if info else d["P"]


def head_yaw(M) -> float | None:
    """Degrees the head is turned from the camera (MediaPipe's pose matrix; + = toward the picture's left)."""
    if M is None:
        return None
    R = np.asarray(M, float)[:3, :3]
    return float(np.degrees(np.arctan2(R[0, 2], R[2, 2])))
