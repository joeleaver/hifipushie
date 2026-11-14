"""Feature crops: detection, boxes, the crops of a run and of the head's photos. Part of the judge (judge.py has the overview)."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from . import judge
from .judge_render import _photo_index, state_sig

# ------------------------------------------------------------------ crops
def _detect(img):
    from . import likeness_detect
    P = likeness_detect.detect([img.convert("RGB")])[0]
    if P is None:  # a small face in a big frame: once more on the alpha / centre box
        return None
    return np.asarray(P, float)


def feature_boxes(P: np.ndarray) -> dict:
    iod = float(np.linalg.norm(P[33] - P[263]))
    out = {}
    for name, spec in judge.FEATURES.items():
        idx, hw, hh = spec[:3]
        c = P[idx].mean(0) + np.array([0.0, (spec[3] if len(spec) > 3 else 0.0) * iod])
        out[name] = [c[0] - hw * iod, c[1] - hh * iod, c[0] + hw * iod, c[1] + hh * iod]
    return out


def _crop(im, box, size=None):
    from PIL import Image
    x0, y0, x1, y1 = (int(round(v)) for v in box)
    c = im.crop((x0, y0, x1, y1))
    if size is not None:
        c = c.resize(size, Image.LANCZOS)
    return c


def _fit(w, h, m=judge.FEATURE_PX):
    s = m / max(w, h)
    return (max(1, int(round(w * s))), max(1, int(round(h * s))))


def crops(out: Path, boxes_from: Path | None = None) -> dict:
    """Cut the crops of a run: out/crops/<shot>__<view>[__<feature>].png + crops.json {name: {file, state, box}}.
    boxes_from: another run whose face boxes are reused (the same camera: the same pixels compared)."""
    from PIL import Image
    out = Path(out)
    au = json.loads((out / "audit.json").read_text())
    states = {Path(r["file"]).name: state_sig(r) for r in au["renders"]}
    prev = json.loads((Path(boxes_from) / "crops.json").read_text()) if boxes_from else {}
    (out / "crops").mkdir(exist_ok=True)
    table = {}
    for f in sorted((out / "renders").glob("r_*.png")):
        shot, view = f.stem[2:].split("_", 1)  # r_<shot>_<view>: shot names carry no "_"
        base = shot.split("-")[0]
        spec = next(s for s in judge.SHOTS if s["name"] == base)
        im = Image.open(f)
        if spec.get("features"):
            boxes = {}
            for feat in judge.FEATURES:
                k = f"{shot}__{view}__{feat}"
                if "box" in prev.get(k, {}):
                    boxes[feat] = prev[k]["box"]
            if len(boxes) < len(judge.FEATURES):
                P = _detect(_flat(im))
                if P is None:
                    table[f"{shot}__{view}"] = {"error": "no face found"}
                    continue
                boxes = feature_boxes(P)
            for feat, b in boxes.items():
                k = f"{shot}__{view}__{feat}"
                out_by = max(-b[0], -b[1], b[2] - im.width, b[3] - im.height) / max(b[2] - b[0], b[3] - b[1])
                if out_by > 0.15:  # (beyond the frame = transparent, outside the mask) the feature leaves the frame: the shot's framing is wrong, not the model
                    table[k] = {"error": f"crop leaves the frame by {out_by:.0%} of its size"}
                    continue
                c = _crop(im, b, _fit(b[2] - b[0], b[3] - b[1]))
                c.save(out / "crops" / f"{k}.png")
                table[k] = {"file": str(out / "crops" / f"{k}.png"), "state": states[f.name], "box": b,
                            "feature": feat, "view": view, "shot": shot}
        else:
            cw, ch = spec.get("crop", [min(im.width, judge.CROP_MAX), min(im.height, judge.CROP_MAX)])
            b = [(im.width - cw) / 2, (im.height - ch) / 2, (im.width + cw) / 2, (im.height + ch) / 2]
            k = f"{shot}__{view}"
            _crop(im, b).save(out / "crops" / f"{k}.png")
            table[k] = {"file": str(out / "crops" / f"{k}.png"), "state": states[f.name], "box": b, "view": view,
                        "shot": shot}
    (out / "crops.json").write_text(json.dumps(table, indent=1))
    return table


def _flat(im, bg=(0.5, 0.5, 0.5)):
    from PIL import Image
    if im.mode != "RGBA":
        return im.convert("RGB")
    b = Image.new("RGBA", im.size, tuple(int(255 * c) for c in bg) + (255,))
    return Image.alpha_composite(b, im).convert("RGB")


def photo_crops(head: str, out: Path) -> dict:
    """The head's reference photos (human_refs.json) cut to the same face features by their OWN landmarks, at the
    render crops' size. out/photo/<view>__<feature>.png. The photo's state is "photo" (compared with renders under
    that view's photo_light only)."""
    from PIL import Image
    from . import store
    from . import likeness_detect
    refs = json.loads((store.HOME / head / "human_refs.json").read_text())
    out = Path(out) / "photo"
    out.mkdir(parents=True, exist_ok=True)
    table = {}
    for view, yaw in judge.PHOTO_VIEWS.items():
        vi = _photo_index(head, yaw)
        img = Image.open(refs["views"][vi]["image"]).convert("RGB")
        P = _detect(img)
        if P is None:
            P0 = likeness_detect.detect_region(img, (0, 0, img.width, img.height))
            P = None if P0 is None else np.asarray(P0, float)
        if P is None:
            continue
        for feat, b in feature_boxes(P).items():
            c = _crop(img, b, _fit(b[2] - b[0], b[3] - b[1]))
            p = out / f"{view}__{feat}.png"
            c.save(p)
            table[f"{view}__{feat}"] = {"file": str(p), "state": "photo", "box": b, "image": refs["views"][vi]["image"]}
    (out / "photo.json").write_text(json.dumps(table, indent=1))
    return table
