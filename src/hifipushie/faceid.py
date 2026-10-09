"""Face-recognition similarity: "does this render look like the person in the photo?" as one number.

Two open face-recognition embeddings (asset pack "faceid"): SFace (opencv_zoo, Apache 2.0) and ArcFace w600k_r50
(InsightFace buffalo_l, non-commercial research only: a measuring tool here, never shipped). Faces are found and
aligned to the standard 112 px five-point template by YuNet (`cv2.FaceRecognizerSF.alignCrop`); the score is the
cosine similarity of the two embeddings. Runs in the detector venv (likeness.VENV: OpenCV with dnn), as a subprocess;
embeddings are cached by the image's bytes.

What a score means depends on the pictures (a clay render against a painted photo never reaches photo-vs-photo
numbers): calibrate on the same kind of pair (`calibrate` in spikes/likeloop) before reading one.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
from pathlib import Path

import numpy as np

MODELS = ("sface", "arcface")

_SRC = r'''
import sys, json
import cv2, numpy as np
out, d = sys.argv[1], sys.argv[2]
imgs = sys.argv[3:]
det = cv2.FaceDetectorYN.create(d + "/yunet.onnx", "", (320, 320), 0.3, 0.3, 5000)
rec = cv2.FaceRecognizerSF.create(d + "/sface.onnx", "")
af = cv2.dnn.readNet(d + "/w600k_r50.onnx")
res = []
for p in imgs:
    im = cv2.imread(p)
    lm = None
    if p.endswith(".lm.png"):
        lm = json.load(open(p[:-7] + ".json"))
    h, w = im.shape[:2]
    if lm is None:
        det.setInputSize((w, h))
        n, faces = det.detect(im)
        if faces is None or len(faces) == 0:
            res.append(None)
            continue
        f = max(faces, key=lambda r: r[2] * r[3])
    else:  # five points given (eyes, nose tip, mouth corners): the box is only bookkeeping
        f = np.r_[[0, 0, w, h], np.asarray(lm, np.float32).ravel(), [1.0]].astype(np.float32)
    al = rec.alignCrop(im, f)
    d1 = {"box": [float(v) for v in f[:4]], "lm5": [float(v) for v in f[4:14]], "det": float(f[14]),
          "sface": rec.feature(al).ravel().tolist()}
    af.setInput(cv2.dnn.blobFromImage(al, 1.0 / 127.5, (112, 112), (127.5, 127.5, 127.5), swapRB=True))
    d1["arcface"] = af.forward().ravel().tolist()
    res.append(d1)
json.dump(res, open(out, "w"))
'''


def _venv() -> Path:
    from . import likeness
    return Path(likeness.VENV)


def available() -> bool:
    from . import assets
    try:
        assets.pack("faceid")
    except (FileNotFoundError, ValueError):
        return False
    return (_venv() / "bin" / "python").exists()


def _cache() -> Path:
    from . import store
    d = store.HOME / "_cache" / "faceid"
    d.mkdir(parents=True, exist_ok=True)
    return d


def embed(images: list, lm5: list | None = None) -> list:
    """PIL images -> [{"sface": (128,), "arcface": (512,), "box", "lm5", "det"} | None (no face found)].
    lm5[i]: optional five points (x, y) in that image's pixels, YuNet's order (the eye on the picture's left, the
    other eye, nose tip, mouth corners left then right), instead of YuNet's detection."""
    from . import assets
    d = assets.pack("faceid")
    lm5 = lm5 or [None] * len(images)
    out, todo, keys = [None] * len(images), [], []
    for i, im in enumerate(images):
        h = hashlib.sha1(np.asarray(im.convert("RGB")).tobytes() + str(im.size).encode()
                         + json.dumps(None if lm5[i] is None else np.round(np.asarray(lm5[i], float), 2).tolist()).encode())
        k = h.hexdigest()[:20]
        keys.append(k)
        f = _cache() / f"fid_{k}.json"
        if f.exists():
            out[i] = json.loads(f.read_text())
        else:
            todo.append(i)
    if todo:
        with tempfile.TemporaryDirectory() as td:
            paths = []
            for i in todo:
                if lm5[i] is None:
                    p = os.path.join(td, f"{i}.png")
                else:
                    p = os.path.join(td, f"{i}.lm.png")
                    Path(os.path.join(td, f"{i}.json")).write_text(json.dumps(np.asarray(lm5[i], float).tolist()))
                images[i].convert("RGB").save(p)
                paths.append(p)
            res, src = os.path.join(td, "out.json"), os.path.join(td, "fid.py")
            Path(src).write_text(_SRC)
            subprocess.run([str(_venv() / "bin" / "python"), "-I", src, res, str(d), *paths],
                           check=True, capture_output=True, timeout=600)
            got = json.loads(Path(res).read_text())
        for i, v in zip(todo, got):
            (_cache() / f"fid_{keys[i]}.json").write_text(json.dumps(v))
            out[i] = v
    for v in out:
        if v is not None:
            for m in MODELS:
                v[m] = np.asarray(v[m], float)
    return out


def cosine(a, b) -> float:
    a, b = np.asarray(a, float), np.asarray(b, float)
    return float(a @ b / max(np.linalg.norm(a) * np.linalg.norm(b), 1e-12))


def lm5_from_mediapipe(P) -> list:
    """YuNet's five points from MediaPipe's 478 (pixels): the picture's left eye (iris 468), the right (473), nose
    tip (1), mouth corners (61, 291). For renders YuNet misses."""
    P = np.asarray(P, float)
    return [P[468].tolist(), P[473].tolist(), P[1].tolist(), P[61].tolist(), P[291].tolist()]


def similarity(a, b, lm5_a=None, lm5_b=None) -> dict:
    """{"sface": cos, "arcface": cos} between two PIL face pictures (None where a face isn't found)."""
    ea, eb = embed([a, b], [lm5_a, lm5_b])
    if ea is None or eb is None:
        return {m: None for m in MODELS}
    return {m: round(cosine(ea[m], eb[m]), 4) for m in MODELS}


def scores(ref, others: list, lm5_ref=None, lm5s: list | None = None) -> list:
    """Similarity of each picture in `others` to `ref` (one embedding call)."""
    lm5s = lm5s or [None] * len(others)
    E = embed([ref] + list(others), [lm5_ref] + list(lm5s))
    out = []
    for e in E[1:]:
        out.append({m: None if (e is None or E[0] is None) else round(cosine(E[0][m], e[m]), 4) for m in MODELS})
    return out
