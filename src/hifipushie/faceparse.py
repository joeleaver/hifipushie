"""FACE PARSING (refread, 2026-10-11): a per-pixel read of a picture of a head: skin / hair / ears / neck / clothes /
brows / nose / lips / background, on ANY background and on paintings. face_ruler.photo_masks assumes a plain backdrop
and warm skin: on Garrett's two paintings it found 31-56 outline samples (Tess's studio photos: ~195).

Two nets, both run on CPU in the detector venv (likeness.VENV: OpenCV dnn + MediaPipe) as a subprocess, ~1 s a
picture, cached by the crop's bytes (asset pack "faceparse"):
  "bisenet"    BiSeNet (ResNet-34) trained on CelebAMask-HQ, 19 classes (yakhyo/face-parsing, MIT code). The DATA
               (CelebAMask-HQ) is for non-commercial research only, so the weights are a MEASURING TOOL here, never
               shipped in an asset or the package (as faceid's ArcFace).
  "mediapipe"  MediaPipe's selfie_multiclass_256x256 (Apache 2.0): background / hair / body skin / face skin /
               clothes / others. No ears, nose or lips of their own.
Validated on dressed renders over a dark painted background (spikes/refread/pval.py; the notes' "## refread").

  parse(img, box, model)            class probabilities on a square crop of the picture -> {"p": (C, n, n) float32,
                                    "names", "box"}
  groups(res)                       {"figure", "skin" (bare skin incl. neck, ears, features), "face" (no neck), "hair",
                                    "nose", "ears", "neck", "cloth"}: probability maps of the crop
  head_box(cam, L, origin, scale)   the crop a head wants (the nets were trained on framed faces)
  masks(img, cam, head, ...)        -> (figure mask, bare-skin mask, {group: probability map}) in the picture's pixels
"""
from __future__ import annotations

import hashlib
import os
import subprocess
import tempfile
from pathlib import Path

import numpy as np

MODEL = "bisenet"
SIZE = {"bisenet": 512, "mediapipe": 256}
NAMES = {"bisenet": ("background", "skin", "l_brow", "r_brow", "l_eye", "r_eye", "eye_g", "l_ear", "r_ear", "ear_r", "nose",
                     "mouth", "u_lip", "l_lip", "neck", "neck_l", "cloth", "hair", "hat"),
         "mediapipe": ("background", "hair", "body_skin", "face_skin", "cloth", "others")}
GROUPS = {"bisenet": {"skin": (1, 2, 3, 4, 5, 7, 8, 10, 11, 12, 13, 14), "face": (1, 2, 3, 4, 5, 7, 8, 10, 11, 12, 13),
                      "hair": (17, 18), "nose": (10,), "ears": (7, 8), "neck": (14,), "cloth": (15, 16), "lips": (12, 13),
                      "brows": (2, 3)},
          "mediapipe": {"skin": (2, 3), "face": (3,), "hair": (1,), "neck": (2,), "cloth": (4, 5)}}

_SRC = r'''
import sys, numpy as np, cv2
kind, d = sys.argv[1], sys.argv[2]
paths = sys.argv[3:]
if kind == "bisenet":
    net = cv2.dnn.readNet(d + "/bisenet_resnet34.onnx")
    for p in paths:
        im = cv2.imread(p)
        x = cv2.resize(im, (512, 512), interpolation=cv2.INTER_AREA if im.shape[0] > 512 else cv2.INTER_CUBIC)[:, :, ::-1].astype(np.float32) / 255.0
        x = (x - [0.485, 0.456, 0.406]) / [0.229, 0.224, 0.225]
        net.setInput(x.transpose(2, 0, 1)[None].astype(np.float32))
        y = net.forward()[0].astype(np.float64)
        y = np.exp(y - y.max(0, keepdims=True))
        y /= y.sum(0, keepdims=True)
        np.savez_compressed(p + ".npz", p=np.round(y * 255).astype(np.uint8))
else:
    import mediapipe as mp
    from mediapipe.tasks import python as mpt
    from mediapipe.tasks.python import vision
    seg = vision.ImageSegmenter.create_from_options(vision.ImageSegmenterOptions(
        base_options=mpt.BaseOptions(model_asset_path=d + "/selfie_multiclass_256x256.tflite"),
        output_category_mask=False, output_confidence_masks=True))
    for p in paths:
        im = cv2.imread(p)[:, :, ::-1]
        r = seg.segment(mp.Image(image_format=mp.ImageFormat.SRGB, data=np.ascontiguousarray(im)))
        y = np.stack([cv2.resize(np.asarray(m.numpy_view(), np.float32), (256, 256)) for m in r.confidence_masks])
        np.savez_compressed(p + ".npz", p=np.round(np.clip(y, 0, 1) * 255).astype(np.uint8))
    seg.close()
'''


def available() -> bool:
    from . import assets, likeness
    try:
        assets.pack("faceparse")
    except (FileNotFoundError, ValueError):
        return False
    return (Path(likeness.VENV) / "bin" / "python").exists()


def _cache_dir() -> Path:
    from . import store
    d = store.HOME / "_cache" / "faceparse"
    d.mkdir(parents=True, exist_ok=True)
    return d


def parse(img, box=None, model: str | None = None) -> dict:
    """Class probabilities of a picture's square crop box (x0, y0, x1, y1; default the whole picture): {"p": (C, n, n)
    float32 0..1, "names", "box", "model"}. The crop is what the net sees: frame the head (head_box)."""
    from . import assets, likeness
    model = model or MODEL
    if model not in SIZE:
        raise ValueError(f"faceparse: model = one of {sorted(SIZE)}")
    box = (0, 0, *img.size) if box is None else tuple(int(round(float(v))) for v in box)
    crop = img.convert("RGB").crop(box)
    a = np.asarray(crop)
    key = hashlib.sha1(a.tobytes() + str(a.shape).encode() + model.encode()).hexdigest()[:20]
    f = _cache_dir() / f"{model}_{key}.npz"
    if not f.exists():
        d = assets.pack("faceparse")
        with tempfile.TemporaryDirectory(dir=str(_cache_dir())) as td:
            p = os.path.join(td, "in.png")
            crop.save(p)
            src = os.path.join(td, "parse.py")
            Path(src).write_text(_SRC)
            r = subprocess.run([str(Path(likeness.VENV) / "bin" / "python"), src, model, str(d), p], capture_output=True,
                               text=True, timeout=600)
            if not os.path.exists(p + ".npz"):
                raise RuntimeError(f"faceparse ({model}) failed: {r.stderr[-600:]}")
            os.replace(p + ".npz", f)
    return {"p": np.load(f)["p"].astype(np.float32) / 255.0, "names": NAMES[model], "box": box, "model": model}


def groups(res: dict) -> dict:
    """The classes summed into what the readers use: probability maps (crop resolution)."""
    p = res["p"]
    out = {"figure": 1.0 - p[0]}
    for k, ids in GROUPS[res["model"]].items():
        out[k] = p[list(ids)].sum(0)
    return out


def head_box(P, size, pad: float = 2.1) -> tuple:
    """The square crop for a head whose 68 landmarks project to P (picture px): pad x the landmarks' height, the face a
    little under the middle (hair above), as the nets' training pictures frame it. Clipped to nothing: PIL pads."""
    P = np.asarray(P, float)
    c = 0.5 * (P.min(0) + P.max(0))
    s = pad * float(max(np.ptp(P[:, 1]), 0.8 * np.ptp(P[:, 0])))
    return (c[0] - s / 2, c[1] - 0.55 * s, c[0] + s / 2, c[1] + 0.45 * s)


def to_picture(prob, box, size) -> np.ndarray:
    """A crop's probability map laid back on the picture (w, h = size), bilinear; 0 outside the crop."""
    from PIL import Image
    x0, y0, x1, y1 = (int(round(v)) for v in box)
    m = Image.fromarray(np.round(np.clip(prob, 0, 1) * 255).astype(np.uint8)).resize((x1 - x0, y1 - y0), Image.BILINEAR)
    full = Image.new("L", tuple(size), 0)
    full.paste(m, (x0, y0))
    return np.asarray(full, np.float32) / 255.0


def masks(img, cam, head, origin=(0.0, 0.0), scale: float = 1.0, model: str | None = None) -> tuple:
    """A picture of the model's head through cam (img = the camera's picture, or its crop at origin / scale): (the
    figure's mask, where it is BARE SKIN (face, ears, neck; not hair, cloth, glasses), {group: probability map}), all in
    img's pixels. Same meaning as face_ruler.photo_masks, for any background."""
    from . import humanfit
    P = (humanfit.project(cam, np.asarray(head["L"], float)[:68]) - np.asarray(origin, float)) * float(scale)
    box = head_box(P, img.size)
    g = groups(parse(img, box, model))
    full = {k: to_picture(v, box, img.size) for k, v in g.items()}
    return full["figure"] > 0.5, full["skin"] > 0.5, full
