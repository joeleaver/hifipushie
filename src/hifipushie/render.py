"""Contact sheets: several consistent clay views in one image, with world-unit rulers."""

from __future__ import annotations

import json
import math
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

BLENDER = os.environ.get("HIFIPUSHIE_BLENDER") or shutil.which("blender") or "blender"
SCRIPT = Path(__file__).with_name("blender_render.py")


def _dir(az: float, el: float) -> list[float]:
    """Camera direction from azimuth (0 = front/-Y, +90 = creature's left/+X) and elevation, degrees."""
    a, e = math.radians(az), math.radians(el)
    return [math.sin(a) * math.cos(e), -math.cos(a) * math.cos(e), math.sin(e)]


# name -> (dir, up, ruler axes (u, v) as world axis indices, or None for oblique views)
VIEWS = {
    "front": ([0, -1, 0], [0, 0, 1], (0, 2)),
    "side": ([1, 0, 0], [0, 0, 1], (1, 2)),
    "top": ([0, 0, 1], [0, 1, 0], (0, 1)),
    "back": ([0, 1, 0], [0, 0, 1], None),
    "left": ([-1, 0, 0], [0, 0, 1], None),
    "three_quarter": (_dir(-35, 20), [0, 0, 1], None),
    "three_quarter_back": (_dir(-145, 25), [0, 0, 1], None),
    "below": ([0, 0, -1], [0, 1, 0], None),
}
DEFAULT_VIEWS = ["front", "side", "top", "three_quarter"]

try:
    FONT = ImageFont.truetype("DejaVuSans.ttf", 13)
except OSError:
    FONT = ImageFont.load_default()


def view_frames(verts: np.ndarray, views: list[str], focus=None, zoom: float = 1.0) -> list[dict]:
    """Shared ortho scale across views so proportions compare directly between panels."""
    lo, hi = verts.min(0), verts.max(0)
    center = (lo + hi) / 2 if focus is None else np.asarray(focus, float)
    scale = float((hi - lo).max() * 1.12 / zoom)
    out = []
    for name in views:
        if name not in VIEWS:
            raise ValueError(f"unknown view {name!r}; choose from {sorted(VIEWS)}")
        d, up, axes = VIEWS[name]
        out.append({"name": name, "dir": d, "up": up, "center": center.tolist(), "scale": scale, "axes": axes})
    return out


def render_views(mesh_npz: Path, frames: list[dict], size: int, matcap: str, cavity: bool = True) -> list[Image.Image]:
    with tempfile.TemporaryDirectory(prefix="hifipushie-") as tmp:
        for f in frames:
            f["out"] = str(Path(tmp) / f"{f['name']}.png")
        job = Path(tmp) / "job.json"
        job.write_text(json.dumps({"mesh": str(mesh_npz), "size": size, "matcap": matcap, "cavity": cavity,
                                   "views": frames}))
        r = subprocess.run([BLENDER, "-b", "--factory-startup", "--python", str(SCRIPT), "--", str(job)],
                           capture_output=True, text=True, timeout=300)
        missing = [f["out"] for f in frames if not Path(f["out"]).exists()]
        if r.returncode or missing:
            raise RuntimeError(f"blender render failed:\n{r.stdout[-3000:]}\n{r.stderr[-3000:]}")
        return [Image.open(f["out"]).convert("RGB") for f in frames]


def _nice_step(span: float) -> float:
    raw = span / 8
    mag = 10 ** math.floor(math.log10(raw))
    return next(m * mag for m in (1, 2, 5, 10) if m * mag >= raw)


def _panel(img: Image.Image, frame: dict, grid: bool) -> Image.Image:
    """Add a title and, for axis-aligned views, rulers + faint grid in world units."""
    m = 36
    W, H = img.size
    out = Image.new("RGB", (W + m, H + m + 20), (30, 31, 35))
    out.paste(img, (m, 20))
    d = ImageDraw.Draw(out)
    d.text((m + 4, 3), frame["name"], fill=(235, 235, 235), font=FONT)
    axes = frame["axes"]
    if axes is None:
        return out
    s, c = frame["scale"], frame["center"]
    u0, v0 = c[axes[0]] - s / 2, c[axes[1]] - s / 2
    step = _nice_step(s)
    names = "XYZ"
    d.text((W + m - 60, 3), f"{names[axes[0]]}→  {names[axes[1]]}↑", fill=(160, 160, 170), font=FONT)
    t = math.ceil(u0 / step) * step
    while t <= u0 + s:
        px = m + (t - u0) / s * W
        if grid:
            d.line([(px, 20), (px, 20 + H)], fill=(80, 85, 95), width=1)
        d.text((px - 12, H + 22), f"{t:.2f}".rstrip("0").rstrip(".") or "0", fill=(190, 190, 200), font=FONT)
        t += step
    t = math.ceil(v0 / step) * step
    while t <= v0 + s:
        py = 20 + H - (t - v0) / s * H
        if grid:
            d.line([(m, py), (m + W, py)], fill=(80, 85, 95), width=1)
        d.text((2, py - 7), f"{t:.2f}".rstrip("0").rstrip(".") or "0", fill=(190, 190, 200), font=FONT)
        t += step
    return out


def contact_sheet(images: list[Image.Image], frames: list[dict], grid: bool = False) -> Image.Image:
    panels = [_panel(im, f, grid) for im, f in zip(images, frames)]
    cols = 2 if len(panels) > 1 else 1
    rows = math.ceil(len(panels) / cols)
    pw, ph = panels[0].size
    sheet = Image.new("RGB", (pw * cols, ph * rows), (30, 31, 35))
    for i, p in enumerate(panels):
        sheet.paste(p, ((i % cols) * pw, (i // cols) * ph))
    return sheet
