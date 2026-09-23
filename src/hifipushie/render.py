"""Contact sheets: several consistent clay views in one image, with world-unit rulers."""

from __future__ import annotations

import json
import math
import os
import queue
import shutil
import subprocess
import tempfile
import threading
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


def camera_frame(cam: dict, index: int = 0) -> dict:
    """A perspective panel from {"eye": [x,y,z], "target": [x,y,z], "fov"?: degrees across (default 70),
    "up"?, "name"?} (eye and target already resolved to 3D). No rulers: sizes vary with depth."""
    eye, target = np.asarray(cam["eye"], float), np.asarray(cam["target"], float)
    d = eye - target
    if np.linalg.norm(d) < 1e-9:
        raise ValueError("camera eye and target are the same point")
    d /= np.linalg.norm(d)
    up = np.asarray(cam.get("up", [0, 0, 1]), float)
    if np.linalg.norm(np.cross(up, d)) < 1e-6:  # looking straight up or down: screen up is +Y
        up = np.array([0.0, 1.0, 0.0])
    fov = float(cam.get("fov", 70))
    if not 5 <= fov <= 150:
        raise ValueError("camera fov must be between 5 and 150 degrees")
    return {"name": cam.get("name") or (f"camera {index + 1}" if index else "camera"), "dir": d.tolist(),
            "up": up.tolist(), "eye": eye.tolist(), "center": target.tolist(), "fov": fov,
            "near": float(cam.get("near", 0.01)), "scale": None, "axes": None}


class _Blender:
    """One headless Blender kept running between looks (render jobs go in on stdin), so a look doesn't pay
    for Blender's startup. Restarted if it dies; one job at a time."""

    def __init__(self):
        self.proc = None
        self.lines: queue.Queue = queue.Queue()
        self.lock = threading.Lock()

    def _start(self):
        self.proc = subprocess.Popen([BLENDER, "-b", "--factory-startup", "--python", str(SCRIPT), "--", "--serve"],
                                     stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                     text=True, bufsize=1)
        self.lines = queue.Queue()
        out, q = self.proc.stdout, self.lines

        def pump():
            for line in out:
                q.put(line)
            q.put(None)
        threading.Thread(target=pump, daemon=True).start()

    def render(self, job: Path, timeout: float = 300):
        with self.lock:
            if self.proc is None or self.proc.poll() is not None:
                self._start()
            self.proc.stdin.write(f"{job}\n")
            self.proc.stdin.flush()
            log = []
            while True:
                try:
                    line = self.lines.get(timeout=timeout)
                except queue.Empty:
                    self.proc.kill()
                    raise RuntimeError("blender render timed out")
                if line is None:
                    raise RuntimeError("blender exited:\n" + "".join(log[-60:]))
                if line.startswith("@@done"):
                    return
                if line.startswith("@@error"):
                    raise RuntimeError("blender render failed: " + line[8:] + "".join(log[-60:]))
                log.append(line)


_BLENDER = _Blender()


def render_views(mesh_npz: Path, frames: list[dict], size: int, matcap: str, cavity: bool = True,
                 flat: bool = False, extra: list[Path] = ()) -> list[Image.Image]:
    """One image per frame. extra: further meshes drawn with the model (section caps)."""
    with tempfile.TemporaryDirectory(prefix="hifipushie-") as tmp:
        for f in frames:
            f["out"] = str(Path(tmp) / f"{f['name']}.png")
        job = Path(tmp) / "job.json"
        job.write_text(json.dumps({"mesh": str(mesh_npz), "size": size, "matcap": matcap, "cavity": cavity,
                                   "flat": flat, "views": frames,
                                   "extra": [str(e) for e in extra]}))
        try:
            _BLENDER.render(job)
        except (RuntimeError, OSError):  # fall back to a one-off Blender, which reports its own errors
            r = subprocess.run([BLENDER, "-b", "--factory-startup", "--python", str(SCRIPT), "--", str(job)],
                               capture_output=True, text=True, timeout=300)
            if r.returncode:
                raise RuntimeError(f"blender render failed:\n{r.stdout[-3000:]}\n{r.stderr[-3000:]}")
        missing = [f["out"] for f in frames if not Path(f["out"]).exists()]
        if missing:
            raise RuntimeError(f"blender wrote no image for {missing}")
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
    if "eye" in frame:
        e = ", ".join(f"{x:.2f}" for x in frame["eye"])
        d.text((m + 4 + d.textlength(frame["name"], font=FONT) + 10, 3),
               f"perspective {frame['fov']:.0f}° from ({e}), no rulers", fill=(160, 160, 170), font=FONT)
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


def raking_matcap(path: Path, size: int = 256) -> Path:
    """A matcap lit by one low light from the viewer's left and a little above, so the light grazes
    surfaces facing the camera: shallow bumps, planes and dents show up that a soft studio matcap hides."""
    u = (np.arange(size) + 0.5) / size * 2 - 1
    x, y = np.meshgrid(u, -u)
    z = np.sqrt(np.clip(1 - x * x - y * y, 0, 1))

    def lam(L):
        L = np.asarray(L, float) / np.linalg.norm(L)
        return np.clip(x * L[0] + y * L[1] + z * L[2], 0, 1)
    # key low from the left, a weak fill from the right so the shadow side keeps its shape
    v = 0.1 + 0.85 * lam([-0.85, 0.35, 0.4]) + 0.18 * lam([0.7, 0.1, 0.7])
    img = (np.clip(np.stack([v * 1.0, v * 0.97, v * 0.93], -1), 0, 1) * 255).astype(np.uint8)
    img[x * x + y * y > 1] = 0
    Image.fromarray(img).save(path)
    return path


def curvature_colours(lap: np.ndarray, size: float, voxel: float) -> np.ndarray:
    """Colour vertices by mean curvature (lap = Laplacian of the field, = 2/r on a sphere of radius r).
    Warm = convex, cool = concave, grey = flatter than a quarter of the model; saturation grows on a log
    scale down to radius ~2 voxels, so a crisp crease and a broad swell both read."""
    r = 2.0 / np.maximum(np.abs(lap), 1e-9)
    r_ref, r_min = 0.25 * size, 2.0 * voxel
    t = np.clip(np.log(r_ref / r) / np.log(r_ref / r_min), 0.0, 1.0)[:, None]
    grey = np.array([0.62, 0.62, 0.62])
    warm, cool = np.array([0.95, 0.35, 0.12]), np.array([0.12, 0.4, 0.95])
    tip = np.where((lap > 0)[:, None], warm, cool)
    rgb = grey + t * (tip - grey)
    return np.concatenate([rgb, np.ones((len(rgb), 1))], 1)


_VIRIDIS = np.array([[0.267, 0.005, 0.329], [0.229, 0.322, 0.546], [0.128, 0.567, 0.551], [0.369, 0.789, 0.383],
                     [0.993, 0.906, 0.144]])


def mask_colours(m: np.ndarray) -> np.ndarray:
    """A paint mask 0..1 per vertex in false colour (viridis: purple 0, teal 0.5, yellow 1), sRGB (n, 3)."""
    t = np.clip(m, 0, 1) * (len(_VIRIDIS) - 1)
    i = np.minimum(t.astype(int), len(_VIRIDIS) - 2)
    f = (t - i)[:, None]
    return _VIRIDIS[i] * (1 - f) + _VIRIDIS[i + 1] * f


STROKE_COLOURS = {"clay": (255, 150, 40), "crease": (40, 200, 255), "flatten": (90, 230, 120)}


def project(frame: dict, pts: np.ndarray, size: int) -> np.ndarray:
    """World points -> pixel (x, y) in an orthographic view's image (same camera as blender_render.py)."""
    d, up = np.asarray(frame["dir"], float), np.asarray(frame["up"], float)
    d /= np.linalg.norm(d)
    right = np.cross(up, d)
    right /= np.linalg.norm(right)
    up = np.cross(d, right)
    q = np.asarray(pts, float) - np.asarray(frame["center"], float)
    s = frame["scale"]
    return np.stack([(q @ right / s + 0.5) * size, (0.5 - q @ up / s) * size], -1)


def draw_strokes(img: Image.Image, frame: dict, strokes: list[dict]) -> Image.Image:
    """Draw stroke paths on a rendered view: colour by op, name at the start, hidden parts left out.
    strokes: [{"label": str | None, "op": "clay"|"crease"|"flatten", "pts": (K, 3), "vis": {view: (K,) bool}}]"""
    img = img.copy()
    d = ImageDraw.Draw(img)
    W = img.width
    placed: list[tuple] = []  # label boxes so far: nudge new ones down until they don't overlap
    for st in strokes:
        xy = project(frame, st["pts"], W)
        vis = st["vis"][frame["name"]]
        col = STROKE_COLOURS[st["op"]]
        if len(xy) == 1 or st["op"] == "flatten":
            for (x, y), v in zip(xy, vis):
                if v:
                    d.ellipse([x - 4, y - 4, x + 4, y + 4], outline=col, width=2)
        for k in range(len(xy) - 1):
            if vis[k] and vis[k + 1]:
                d.line([tuple(xy[k]), tuple(xy[k + 1])], fill=col, width=2)
        if st["label"] and vis.any():
            x, y = xy[np.flatnonzero(vis)[0]]
            x0, y0, x1, y1 = d.textbbox((x + 5, y - 14), st["label"], font=FONT, stroke_width=2)
            while any(x0 < b[2] and b[0] < x1 and y0 < b[3] and b[1] < y1 for b in placed):
                y0, y1 = y0 + 8, y1 + 8
            placed.append((x0, y0, x1, y1))
            if y0 > y - 14 + 4:
                d.line([(x, y), (x0, y0 + 7)], fill=col, width=1)
            d.text((x0, y0), st["label"], fill=col, font=FONT, stroke_width=2, stroke_fill=(20, 20, 20))
    return img
