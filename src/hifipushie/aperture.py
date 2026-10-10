"""The eye aperture by part ID (eyedetail, 2026-10-09): the visible eyeball pixels of a render, so paint can't bias the
measure. The 478-point detector's lid points moved ~1 mm with lid tints and wrinkles while the opening's pixels stayed
the same (Garrett, dressed vs eyes-only paint: docs/notes/eyes.md). Use this for the model's own opening (a lid-pose
refit, dressed vs clay); keep the detector for likeness against a photo, where tints are on both sides.

measure(blend, frame, eyes, ...) renders the scene through one camera frame (render.camera_frame / stage.fitted_frame
shape) with every part black but the eyes part (lashes hidden: they stand in front of the opening, not in it), and per
eye (subject's right, left = picture left, right in a front view) returns the opening's height (its tallest column),
width, and the inner / outer corner angles (between lines fitted to the upper and lower rim within `corner_mm` of
each corner), in mm at the eyes' distance."""
from __future__ import annotations

import tempfile
from pathlib import Path

import numpy as np


def mask(blend: str, frame: dict, size: int = 1024, eyes_part: str = "eyes", hide=("lashes",)) -> np.ndarray:
    """(size, size) bool: where the eyes part is the nearest surface."""
    from PIL import Image

    from . import scene
    with tempfile.TemporaryDirectory() as tmp:
        fr = {**frame, "out": str(Path(tmp) / "id.png")}
        job = {"mode": "render", "blend": str(blend), "views": [fr], "size": size, "samples": 8, "hide": list(hide),
               "flat": True, "id_parts": {eyes_part: [1.0, 0.0, 0.0]}}
        scene._blender(job, 1200)
        im = np.asarray(Image.open(fr["out"]).convert("RGB"), float)
    return (im[..., 0] > 128) & (im[..., 1] < 100) & (im[..., 2] < 100)


def _corner_angle(B, corner, toward, r_px):
    """The angle at a corner between the upper and lower rim: lines fitted to the boundary pixels within r_px of it."""
    d = B - corner
    near = (np.linalg.norm(d, axis=1) < r_px) & ((d @ toward) > 0.15 * r_px)
    if near.sum() < 6:
        return float("nan")
    P = B[near]
    up = P[:, 1] < corner[1]  # (image y down)
    angs = []
    for sel in (up, ~up):
        if sel.sum() < 3:
            return float("nan")
        q = P[sel] - corner
        dvec = q.mean(0)
        angs.append(np.arctan2(dvec[1], dvec[0]))
    a = abs(np.degrees(angs[0] - angs[1]))
    return float(min(a, 360 - a))


def from_mask(m: np.ndarray, mm_per_px: float, corner_mm: float = 3.0) -> list:
    """Per eye, picture left to right: {"open", "width" (mm), "inner_angle", "outer_angle" (deg)}."""
    from scipy import ndimage
    lab, n = ndimage.label(m)
    if n < 1:
        return []
    sizes = ndimage.sum(m, lab, range(1, n + 1))
    keep = 1 + np.argsort(sizes)[::-1][:2]
    comps = sorted(keep, key=lambda k: np.nonzero(lab == k)[1].mean())
    out = []
    for i, k in enumerate(comps):
        c = lab == k
        ys, xs = np.nonzero(c)
        cols = np.bincount(xs - xs.min())
        er = c ^ ndimage.binary_erosion(c)
        by, bx = np.nonzero(er)
        B = np.c_[bx, by].astype(float)
        left = B[np.argmin(B[:, 0])]
        right = B[np.argmax(B[:, 0])]
        # the inner corner is toward the nose: picture left eye's right end, picture right eye's left end
        inner, outer = (right, left) if i == 0 else (left, right)
        r = corner_mm / mm_per_px
        out.append({"open": round(float(cols.max() * mm_per_px), 2), "width": round(float((np.ptp(xs) + 1) * mm_per_px), 2),
                    "inner_angle": round(_corner_angle(B, inner, (outer - inner) / np.linalg.norm(outer - inner), r), 1),
                    "outer_angle": round(_corner_angle(B, outer, (inner - outer) / np.linalg.norm(inner - outer), r), 1)})
    return out


def measure(blend: str, frame: dict, eyes: list, size: int = 1024, eyes_part: str = "eyes", corner_mm: float = 3.0) -> list:
    """The aperture per eye (picture left to right) through `frame` (needs "eye", "fov"), scaled at the eyes' mean
    distance (eyes: their centres, world)."""
    m = mask(blend, frame, size, eyes_part)
    dist = float(np.linalg.norm(np.mean(np.asarray(eyes, float), 0) - np.asarray(frame["eye"], float)))
    mmpx = 2 * dist * np.tan(np.radians(frame["fov"]) / 2) * 1000 / size
    return from_mask(m, mmpx, corner_mm)
