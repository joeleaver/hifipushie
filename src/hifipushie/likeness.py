"""Likeness: a checklist of facial features, measured the same way on a reference picture and on the model.

The user (2026-10-08): "a checklist of facial features to specifically look for and match from references. Your image
comprehension is good, but it works better if it knows where to focus." So:

- `likeness.json` is the checklist (FISWG's component list + likeness artists' order + Farkas' landmarks: see
  likeness_guide.md). Each item: what to look at, which views show it, a MEASURE, a tolerance, the control that fixes
  it, and the fitting stage it belongs to (big to small, as artists work).
- Every measure is a 2D quantity in the reference picture, read on BOTH sides through the same fitted camera
  (human_refs.json): the photo's points and the model's points, in mm at the face's depth. Where it can, both sides
  use the SAME detector (MediaPipe Face Landmarker, 478 points) on the photo and on a clay render of the model through
  that camera, so a definition the detector gets wrong (a jaw contour, iris vs eyeball centre) is wrong the same way
  on both. Where it can't (no detector, a point the clay can't show: brows are paint), the model's own landmarks are
  used and the item says so.
- `measure_reference(name)`: the target sheet (every item measured on the references once, with its view, confidence
  or "unmeasurable"), saved as <model>/likeness_targets.json.
- `report(name)`: the table ranked by miss beyond tolerance, and FOCUS PANELS (photo | model at the same crop and
  camera, the feature drawn on both) for the top misses.
- `stages(name)` / `fit_stage(...)`: the staged fit from the sheet in artists' order (see STAGES), each through an
  existing humanfit control with its integrity gate, earlier stages' points kept as targets in later ones.

This module measures and focuses; it changes a model only through humanfit's guarded fits (fit_stage).
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
from pathlib import Path

import numpy as np

CHECKLIST = Path(__file__).with_name("likeness.json")
VENV = os.environ.get("HIFIPUSHIE_MEDIAPIPE", "/mnt/data/hifipushie/facerefs_venv")
DETECT_PX = 768       # the face crop is scaled to this before detection (MediaPipe works on ~200-800 px faces)
RENDER_PX = 900       # the model's render of the face box, across its longer side
TARGETS = "likeness_targets.json"

# dlib's 68 from MediaPipe's 478 (the table onemesh2's detect.py used for human_refs.json)
MP68 = [162, 234, 93, 58, 172, 136, 149, 148, 152, 377, 378, 365, 397, 288, 323, 454, 389,
        71, 63, 105, 66, 107, 336, 296, 334, 293, 301,
        168, 197, 5, 4, 75, 97, 2, 326, 305,
        33, 160, 158, 133, 153, 144, 362, 385, 387, 263, 373, 380,
        61, 39, 37, 0, 267, 269, 291, 405, 314, 17, 84, 181,
        78, 82, 13, 312, 308, 317, 14, 87]
MP_EYES = (468, 473)   # iris centres: the subject's right (image left), left
OVAL = [10, 338, 297, 332, 284, 251, 389, 356, 454, 323, 361, 288, 397, 365, 379, 378, 400, 377, 152, 148, 176, 149, 150,
        136, 172, 58, 132, 93, 234, 127, 162, 21, 54, 103, 67, 109]
_MP_TO_LM = {m: i for i, m in enumerate(MP68)}
_MP_TO_LM[MP_EYES[0]] = 69   # humanfit: 68 = eye.L (subject's left), 69 = eye.R
_MP_TO_LM[MP_EYES[1]] = 68


def checklist() -> list:
    """The items; `control` says what the staged fit uses: "solve <measure>" (humanfit.solve, wired), the stage's own
    control (fit_outline, fit_hood), or GAP + what a person would use by hand."""
    out = json.loads(CHECKLIST.read_text())["items"]
    for it in out:
        c = it["control"]
        if it.get("solve"):
            it["control"] = f"solve {it['solve']}"
        elif not any(w in c for w in ("fit_outline", "fit_hood")) and it["measure"]["kind"] != "judge":
            it["control"] = "GAP: " + c.replace("fit_views", "points by hand (fit_views / nudge)")
    return out


def stage_names() -> list:
    return json.loads(CHECKLIST.read_text())["stages"]


# ---- detection (MediaPipe in its own venv: Apache-2.0, not a dependency of the package) ----------------------------

_DETECT_SRC = r'''
import json, sys
import numpy as np
import mediapipe as mp
from mediapipe.tasks import python as mpt
from mediapipe.tasks.python import vision
from PIL import Image
opts = vision.FaceLandmarkerOptions(base_options=mpt.BaseOptions(model_asset_path=sys.argv[2]), num_faces=1)
det = vision.FaceLandmarker.create_from_options(opts)
out = []
for p in sys.argv[3:]:
    im = Image.open(p).convert("RGB")
    res = det.detect(mp.Image(image_format=mp.ImageFormat.SRGB, data=np.asarray(im)))
    out.append(None if not res.face_landmarks else [[q.x * im.size[0], q.y * im.size[1]] for q in res.face_landmarks[0]])
json.dump(out, open(sys.argv[1], "w"))
'''


def detector_available() -> bool:
    return (Path(VENV) / "bin" / "python").exists() and (Path(VENV) / "face_landmarker.task").exists()


def _cache_dir() -> Path:
    from . import store
    d = store.HOME / "_cache" / "likeness"
    d.mkdir(parents=True, exist_ok=True)
    return d


def detect(images: list) -> list:
    """PIL images -> [(478, 2) pixel array | None] (MediaPipe Face Landmarker), cached by the image's bytes."""
    if not detector_available():
        return [None] * len(images)
    out, todo = [None] * len(images), []
    keys = []
    for i, im in enumerate(images):
        k = hashlib.sha1(np.asarray(im.convert("RGB")).tobytes() + str(im.size).encode()).hexdigest()[:20]
        keys.append(k)
        f = _cache_dir() / f"mp_{k}.json"
        if f.exists():
            v = json.loads(f.read_text())
            out[i] = None if v is None else np.asarray(v, float)
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
            Path(src).write_text(_DETECT_SRC)
            subprocess.run([str(Path(VENV) / "bin" / "python"), src, res, str(Path(VENV) / "face_landmarker.task"), *paths],
                           check=True, capture_output=True, timeout=300)
            got = json.loads(Path(res).read_text())
        for i, v in zip(todo, got):
            (_cache_dir() / f"mp_{keys[i]}.json").write_text(json.dumps(v))
            out[i] = None if v is None else np.asarray(v, float)
    return out


def detect_region(img, box) -> np.ndarray | None:
    """Detect on a crop of a big picture (a full figure: MediaPipe wants the face to fill the frame), scaled to
    DETECT_PX; points back in the picture's pixels."""
    from PIL import Image
    x0, y0, x1, y1 = (float(v) for v in box)
    c = img.crop((int(round(x0)), int(round(y0)), int(round(x1)), int(round(y1))))
    s = DETECT_PX / max(c.size)
    c = c.resize((max(1, int(round(c.size[0] * s))), max(1, int(round(c.size[1] * s)))), Image.LANCZOS)
    P = detect([c])[0]
    if P is None:
        return None
    return P / s + [int(round(x0)), int(round(y0))]


# ---- the model through a reference's camera: a clay render -----------------------------------------------------------

def _raster():
    from numba import njit

    @njit(cache=True)
    def run(sx, sy, z, F, C, W, H, img, zb):
        for t in range(F.shape[0]):
            i0, i1, i2 = F[t, 0], F[t, 1], F[t, 2]
            x0, x1, x2 = sx[i0], sx[i1], sx[i2]
            y0, y1, y2 = sy[i0], sy[i1], sy[i2]
            a0 = max(int(np.floor(min(x0, min(x1, x2)))), 0)
            a1 = min(int(np.ceil(max(x0, max(x1, x2)))), W - 1)
            b0 = max(int(np.floor(min(y0, min(y1, y2)))), 0)
            b1 = min(int(np.ceil(max(y0, max(y1, y2)))), H - 1)
            if a0 > a1 or b0 > b1:
                continue
            d = (y1 - y2) * (x0 - x2) + (x2 - x1) * (y0 - y2)
            if abs(d) < 1e-12:
                continue
            for py in range(b0, b1 + 1):
                gy = py + 0.5
                for px in range(a0, a1 + 1):
                    gx = px + 0.5
                    w0 = ((y1 - y2) * (gx - x2) + (x2 - x1) * (gy - y2)) / d
                    w1 = ((y2 - y0) * (gx - x2) + (x0 - x2) * (gy - y2)) / d
                    w2 = 1.0 - w0 - w1
                    if w0 < 0 or w1 < 0 or w2 < 0:
                        continue
                    zz = w0 * z[i0] + w1 * z[i1] + w2 * z[i2]
                    if zz < zb[py, px]:
                        zb[py, px] = zz
                        for c in range(3):
                            img[py, px, c] = w0 * C[i0, c] + w1 * C[i1, c] + w2 * C[i2, c]
    return run


_RUN = []
KEY = np.array([-0.35, -0.45, -0.82])  # camera frame (x right, y down, z into the picture): a soft key from the upper left
KEY /= np.linalg.norm(KEY)
SKIN = np.array([222.0, 196.0, 176.0])


def _sphere(c, r, fwd, n=28):
    """A UV sphere (eyeball) with a dark iris and pupil where `fwd` leaves it: (V, F, colour per vertex)."""
    th, ph = np.meshgrid(np.linspace(0, np.pi, n), np.linspace(0, 2 * np.pi, 2 * n, endpoint=False), indexing="ij")
    d = np.stack([np.sin(th) * np.cos(ph), np.sin(th) * np.sin(ph), np.cos(th)], -1).reshape(-1, 3)
    V = np.asarray(c, float) + r * d
    F = []
    m = 2 * n
    for i in range(n - 1):
        for j in range(m):
            a, b, cc, dd = i * m + j, i * m + (j + 1) % m, (i + 1) * m + (j + 1) % m, (i + 1) * m + j
            F += [[a, cc, b], [a, dd, cc]]
    cs = d @ (np.asarray(fwd, float) / np.linalg.norm(fwd))
    col = np.where(cs[:, None] > 0.97, [25, 18, 15], np.where(cs[:, None] > 0.86, [80, 62, 48], [235, 230, 225])).astype(float)
    return V, np.asarray(F, np.int64), col


def model_mesh(base: dict) -> dict:
    """The model's head as the clay render draws it: skin (template quads), eyeballs with irises, and the brows (paint
    on the real model: drawn as strokes through the model's brow landmarks)."""
    from . import humanfit
    st = humanfit.state(base)
    tpl, ht = st["tpl"], st["head"]
    Lf = np.asarray(tpl["L"]).reshape(-1, 4)
    F = np.r_[Lf[:, [0, 1, 2]], Lf[:, [0, 2, 3]]].astype(np.int64)
    V = np.asarray(tpl["P"], float)
    fwd = np.asarray(ht.get("forward", [0, -1, 0]), float)
    eyes = []
    r = float(ht.get("eye_r", 0.012))
    for c in ht["eyes"]:
        eyes.append(_sphere(c, r * 0.985, fwd))
    return {"V": V, "F": F, "eyes": eyes, "L": st["L"], "state": st}


def render(mesh: dict, cam: dict, box, px: int = RENDER_PX, brows: bool = True):
    """(PIL image, scale px per picture pixel): the model through the reference's camera, cropped to box (picture
    pixels), lit by a key from the upper left (smooth normals), eyes with irises, brows drawn."""
    from PIL import Image, ImageDraw
    from . import humanfit
    if not _RUN:
        _RUN.append(_raster())
    x0, y0, x1, y1 = box
    k = px / max(x1 - x0, y1 - y0)
    W, H = int(round((x1 - x0) * k)), int(round((y1 - y0) * k))
    img = np.full((H, W, 3), 238.0)
    zb = np.full((H, W), np.inf)
    Rc = humanfit._cam_rot(cam)
    parts = [(mesh["V"], mesh["F"], None)] + list(mesh["eyes"])
    for V, F, col in parts:
        Xc = (V - np.asarray(cam["centre"])) @ Rc.T + np.asarray(cam["t"])
        P = humanfit.project(cam, V)
        fn = np.cross(Xc[F[:, 1]] - Xc[F[:, 0]], Xc[F[:, 2]] - Xc[F[:, 0]])
        keep = (fn * Xc[F].mean(1)).sum(1) < 0   # facing the camera
        vn = np.zeros_like(Xc)
        for c in range(3):
            np.add.at(vn, F[:, c], fn)
        vn /= np.maximum(np.linalg.norm(vn, axis=1, keepdims=True), 1e-15)
        sh = 0.24 + 0.76 * np.clip(vn @ KEY, 0, 1) ** 1.3 + 0.06 * np.clip(-vn[:, 2], 0, 1)
        base_c = np.broadcast_to(SKIN, Xc.shape) if col is None else col
        C = np.clip(base_c * sh[:, None], 0, 255)
        _RUN[0]((P[:, 0] - x0) * k, (P[:, 1] - y0) * k, Xc[:, 2].copy(), np.ascontiguousarray(F[keep]),
                np.ascontiguousarray(C), W, H, img, zb)
    im = Image.fromarray(img.astype(np.uint8))
    if brows:
        L = humanfit.project(cam, mesh["L"])
        d = ImageDraw.Draw(im)
        wpx = max(2, int(round(_mm_per_px(cam, mesh["L"]) ** -1 * 4.0 * k)))  # ~4 mm thick
        for a, b in ((17, 22), (22, 27)):
            pts = [((L[i, 0] - x0) * k, (L[i, 1] - y0) * k) for i in range(a, b)]
            d.line(pts, fill=(70, 52, 40), width=wpx, joint="curve")
    return im, k


def _mm_per_px(cam: dict, X) -> float:
    """mm per picture pixel at the depth of these points (the mean)."""
    from . import humanfit
    Xc = (np.asarray(X, float).mean(0) - np.asarray(cam["centre"])) @ humanfit._cam_rot(cam).T + np.asarray(cam["t"])
    return float(Xc[2] / cam["f"] * 1000.0)


# ---- measuring: the same 2D quantity on the photo and on the model, through one camera ------------------------------

class Unmeasurable(Exception):
    pass


def view_kind(yaw: float) -> str:
    a = abs(float(yaw or 0.0))
    return "front" if a < 20 else ("three_quarter" if a < 70 else "profile")


class Side:
    """One picture's face: MediaPipe's 478 (P) and/or the 68 + 2 eye centres (lm), pixels of the reference picture."""

    def __init__(self, P=None, lm=None, source=""):
        self.P = None if P is None else np.asarray(P, float)
        self.lm = None if lm is None else np.asarray(lm, float)
        self.source = source or ("detector" if P is not None else "landmarks")

    def pt(self, idx) -> np.ndarray:
        idx = [idx] if isinstance(idx, (int, np.integer)) else list(idx)
        out = []
        for i in idx:
            if self.P is not None:
                out.append(self.P[i])
            elif self.lm is not None and i in _MP_TO_LM and np.isfinite(self.lm[_MP_TO_LM[i]]).all():
                out.append(self.lm[_MP_TO_LM[i]])
            else:
                raise Unmeasurable(f"point {i} needs the detector (not in the 68)")
        return np.mean(out, 0)

    def frame(self):
        a = self.pt(168)
        try:
            b = self.pt(152)
        except Unmeasurable:      # (stored reference points often leave the jaw contour out: its definition differs)
            b = self.pt([13, 14])
        ey = (b - a) / max(np.linalg.norm(b - a), 1e-9)
        return np.array([ey[1], -ey[0]]), ey


def points_of(m: dict) -> list:
    """Every point a measure (or a judge item's region) reads."""
    out = []
    for k, v in m.items():
        if k in ("a", "b", "vertex", "level", "from", "to", "pts", "line", "region"):
            out += list(np.ravel(v))
        elif k == "pairs":
            out += list(np.ravel([i for p in v for x in p for i in np.ravel(x)]))
        elif k in ("num", "den"):
            out += points_of(v)
        elif k == "kind" and v == "width":
            out += OVAL
    return sorted({int(i) for i in out})


def _width_ends(side: Side, level) -> tuple:
    """The face oval's two crossings of the face-horizontal line through the level's points (picture pixels)."""
    if side.P is None:
        raise Unmeasurable("face widths need the detector's face oval")
    ex, ey = side.frame()
    c = side.pt(level)
    o = side.P[OVAL]
    s = (o - c) @ ey
    xs = []
    for p in range(len(o)):
        q = (p + 1) % len(o)
        if s[p] * s[q] <= 0 and s[p] != s[q]:
            t = s[p] / (s[p] - s[q])
            xs.append(((o[p] + t * (o[q] - o[p])) - c) @ ex)
    if len(xs) < 2:
        raise Unmeasurable("the level misses the face oval")
    return c + min(xs) * ex, c + max(xs) * ex


def _width(side: Side, level) -> float:
    a, b = _width_ends(side, level)
    return float(np.linalg.norm(b - a))


def _width_lines(m: dict) -> list:
    if m.get("kind") == "width":
        return [m["level"]]
    return [x for k in ("num", "den") if k in m for x in _width_lines(m[k])]


def _item(iid: str) -> dict:
    return next(it for it in checklist() if it["id"] == iid)


def value(side: Side, m: dict, mmpx: float):
    """One measure on one side: mm (distances), degrees (tilts, angles) or a ratio."""
    k = m["kind"]
    if k == "judge":
        raise Unmeasurable("judge by eye (focus panel)")
    if k == "dist":
        ex, ey = side.frame()
        ax = {"x": ex, "y": ey}.get(m.get("axis"))
        vals = []
        for a, b in (m.get("pairs") or [[m["a"], m["b"]]]):
            d = side.pt(b) - side.pt(a)
            v = float(np.linalg.norm(d)) if ax is None else float(d @ ax)
            vals.append(abs(v) if m.get("abs") else v)
        return float(np.mean(vals)) * mmpx
    if k == "width":
        return _width(side, m["level"]) * mmpx
    if k == "ratio":
        d = value(side, m["den"], mmpx)
        return value(side, m["num"], mmpx) / d if abs(d) > 1e-9 else float("nan")
    if k == "tilt":
        ex, ey = side.frame()
        vals = []
        for a, b in m["pairs"]:
            d = side.pt(b) - side.pt(a)
            vals.append(np.degrees(np.arctan2(-(d @ ey), abs(d @ ex))))
        return float(np.mean(vals))
    if k == "level":
        ex, ey = side.frame()
        a, b = side.pt(m["from"]), side.pt(m["to"])
        return float(((side.pt(m["pts"]) - a) @ ey) / max((b - a) @ ey, 1e-9))
    if k == "arch":
        ex, ey = side.frame()
        vals = []
        for line in m["pairs"]:
            Q = np.array([side.pt(i) for i in line])
            n = Q[-1] - Q[0]
            n = np.array([-n[1], n[0]]) / max(np.linalg.norm(n), 1e-9)
            if n @ ey > 0:
                n = -n                     # up the face
            vals.append(float(((Q - Q[0]) @ n).max()))
        return float(np.mean(vals)) * mmpx
    if k == "angle":
        a, v, b = side.pt(m["a"]), side.pt(m["vertex"]), side.pt(m["b"])
        u, w = a - v, b - v
        return float(np.degrees(np.arccos(np.clip(u @ w / max(np.linalg.norm(u) * np.linalg.norm(w), 1e-12), -1, 1))))
    if k == "bow":
        ex, ey = side.frame()
        Q = np.array([side.pt(i) for i in m["line"]])
        n = Q[-1] - Q[0]
        n = np.array([-n[1], n[0]]) / max(np.linalg.norm(n), 1e-9)
        out = side.pt(m["line"][-1]) - side.pt([129, 358])
        if n @ out < 0:
            n = -n                         # + = toward where the nose points: a hump
        dev = (Q - Q[0]) @ n
        return float(dev[np.argmax(np.abs(dev))]) * mmpx
    raise ValueError(f"likeness: unknown measure kind {k!r}")


def _confidence(item: dict, vk: str, mmpx: float, src: str) -> str:
    if item["measure"]["kind"] == "judge":
        return "judge"
    pref = item["views"][0] if item["views"] else vk
    if item.get("tol") and item["unit"] == "mm" and item["tol"] < 1.2 * mmpx:
        return "low"            # the tolerance is about a pixel of the reference
    if item.get("reliability") or vk != pref or src != "detector":
        return "medium"
    return "high"


# ---- the references and the model seen through them -----------------------------------------------------------------

def _refs(name: str) -> dict:
    from . import store
    p = store.HOME / name / "human_refs.json"
    if not p.exists():
        raise ValueError(f"likeness: {name} has no human_refs.json (fit its reference pictures first: human_reference)")
    return json.loads(p.read_text())


def _lm_from_points(points: dict) -> np.ndarray:
    from . import humanfit
    lm = np.full((70, 2), np.nan)
    for k, uv in points.items():
        try:
            lm[humanfit.point_index(k)] = uv
        except ValueError:
            pass
    return lm


def _box(points: dict, size) -> tuple:
    U = np.array(list(points.values()), float)
    lo, hi = U.min(0), U.max(0)
    pad = 0.5 * (hi - lo).max()
    return (max(lo[0] - pad, 0.0), max(lo[1] - pad * 1.2, 0.0), min(hi[0] + pad, size[0]), min(hi[1] + pad * 0.6, size[1]))


def photo_sides(refs: dict) -> list:
    """Each reference picture as a Side (the detector on a crop round its face; its stored points as the fallback)."""
    from PIL import Image
    out = []
    for v, cam in zip(refs["views"], refs["cameras"]):
        img = Image.open(v["image"]).convert("RGB")
        box = _box(v["points"], img.size)
        P = detect_region(img, box)
        out.append({"view": v, "cam": cam, "kind": view_kind(cam.get("yaw", v.get("yaw", 0))), "img": img, "box": box,
                    "side": Side(P, _lm_from_points(v["points"]), "detector" if P is not None else "landmarks"),
                    "mmpx": float(cam["t"][2] / cam["f"] * 1000.0)})
    return out


def model_sides(base: dict, photos: list, mesh=None, cameras=None) -> list:
    """The model through each reference's camera: the clay render, the detector on it, its own landmarks projected."""
    from . import humanfit
    mesh = mesh or model_mesh(base)
    out = []
    for i, ph in enumerate(photos):
        cam, box = (cameras[i] if cameras else ph["cam"]), ph["box"]
        im, k = render(mesh, cam, box)
        P = detect([im])[0]
        P = None if P is None else P / k + [box[0], box[1]]
        out.append({"img": im, "k": k, "cam": cam, "side": Side(P, humanfit.project(cam, mesh["L"]),
                                                                  "detector" if P is not None else "landmarks"),
                    "mmpx": _mm_per_px(cam, mesh["L"])})
    return out


def measure_sides(sides: list, kinds: list, mmpxs: list) -> dict:
    """{item id: {view index: value | "unmeasurable: why"}}; "-" when no picture has a view the item needs."""
    out = {}
    for it in checklist():
        row = {}
        for vi, (s, vk, mp) in enumerate(zip(sides, kinds, mmpxs)):
            if vk not in it["views"]:
                continue
            try:
                row[vi] = value(s, it["measure"], mp)
            except Unmeasurable as e:
                row[vi] = f"unmeasurable: {e}"
        if not row:
            row["-"] = "unmeasurable: " + " or ".join(it["views"]) + " view needed"
        out[it["id"]] = row
    return out


def measure_reference(name: str, save: bool = True, photos=None) -> dict:
    """The target sheet: every checklist item measured on the model's reference pictures (human_refs.json), with its
    view, tolerance, confidence and source, or why it can't be measured. Saved as <model>/likeness_targets.json.
    Values are mm at the face's depth through each picture's fitted camera (its own scale), degrees or ratios."""
    from . import store
    refs = _refs(name)
    photos = photos or photo_sides(refs)
    vals = measure_sides([p["side"] for p in photos], [p["kind"] for p in photos], [p["mmpx"] for p in photos])
    items = {}
    for it in checklist():
        rows = {}
        for vi, v in vals[it["id"]].items():
            if vi == "-":
                rows["-"] = {"value": None, "confidence": "unmeasurable", "why": v.split(": ", 1)[1]}
                continue
            ph = photos[vi]
            if isinstance(v, str):
                rows[str(vi)] = {"view": ph["kind"], "value": None,
                                 "confidence": "judge" if "judge" in v else "unmeasurable", "why": v.split(": ", 1)[1]}
            else:
                rows[str(vi)] = {"view": ph["kind"], "value": round(float(v), 3),
                                 "confidence": _confidence(it, ph["kind"], ph["mmpx"], ph["side"].source),
                                 "source": ph["side"].source, "mm_per_px": round(ph["mmpx"], 3)}
        items[it["id"]] = {"name": it["name"], "stage": it["stage"], "unit": it["unit"], "tol": it["tol"],
                           "control": it["control"], "reliability": it.get("reliability", ""), "views": rows}
    sheet = {"model": name, "references": [{"image": p["view"]["image"], "view": p["kind"], "mm_per_px": round(p["mmpx"], 3),
                                            "detector": p["side"].source == "detector"} for p in photos],
             "stages": [s["name"] for s in stage_names()], "items": items}
    if save:
        (store.HOME / name / TARGETS).write_text(json.dumps(sheet, indent=1))
    return sheet


def sheet_text(sheet: dict) -> str:
    lines = ["target sheet (" + ", ".join(f"{r['view']} {r['mm_per_px']} mm/px{'' if r['detector'] else ' NO DETECTOR'}"
                                          for r in sheet["references"]) + ")"]
    for st in sheet["stages"]:
        lines.append(f"[{st}]")
        for iid, it in sheet["items"].items():
            if it["stage"] != st:
                continue
            for vi, r in it["views"].items():
                v = "-" if r["value"] is None else (f"{r['value']:.3f}" if it["unit"] == "" else f"{r['value']:.1f} {it['unit']}")
                lines.append(f"  {it['name'][:44]:44} {r.get('view', '-'):13} {v:>10}  {r['confidence']}"
                             + (f" ({r['why']})" if r.get("why") else ""))
    return "\n".join(lines)


def compare(name: str, base: dict | None = None, photos=None, cameras=None, mesh=None) -> dict:
    """Photo vs model for every item and view: rows sorted by miss / tolerance (beyond tolerance first, then big items
    before small), plus the pictures the focus panels need."""
    from . import store
    base = base or store.load(name)["base"]
    photos = photos or photo_sides(_refs(name))
    models = model_sides(base, photos, mesh=mesh, cameras=cameras)
    kinds = [p["kind"] for p in photos]
    mm = [m["mmpx"] for m in models]
    pv = measure_sides([p["side"] for p in photos], kinds, mm)
    mv = measure_sides([m["side"] for m in models], kinds, mm)
    # the same measures on the landmarks alone (the photo's stored 68 + eye centres, the model's own GNM landmarks):
    # where the two readings disagree, the miss depends on the definition, not only on the face
    pl = measure_sides([Side(None, p["side"].lm, "landmarks") for p in photos], kinds, mm)
    ml = measure_sides([Side(None, m["side"].lm, "landmarks") for m in models], kinds, mm)
    rows = []
    order = [s["name"] for s in stage_names()]
    for it in checklist():
        for vi in pv[it["id"]]:
            a, b = pv[it["id"]][vi], mv[it["id"]].get(vi)
            r = {"id": it["id"], "name": it["name"], "stage": it["stage"], "tier": order.index(it["stage"]) + 1,
                 "view": kinds[vi] if vi != "-" else "-", "vi": vi, "unit": it["unit"], "tol": it["tol"],
                 "control": it["control"], "reliability": it.get("reliability", ""), "photo": a, "model": b,
                 "points": points_of(it["measure"])}
            if isinstance(a, float) and isinstance(b, float) and it["tol"] and np.isfinite(a) and np.isfinite(b):
                r["miss"] = b - a
                r["score"] = abs(b - a) / it["tol"]
                r["source"] = f"{photos[vi]['side'].source}/{models[vi]['side'].source}"
                c, d = pl[it["id"]].get(vi), ml[it["id"]].get(vi)
                if isinstance(c, float) and isinstance(d, float) and np.isfinite(c) and np.isfinite(d):
                    r["miss_lm"] = d - c
                    r["agree"] = abs((d - c) - (b - a)) <= it["tol"]
            else:
                r["score"] = -1.0
                r["why"] = (a if isinstance(a, str) else b if isinstance(b, str) else "").split(": ", 1)[-1]
            rows.append(r)
    rows.sort(key=lambda r: (-(r["score"] > 1.0), -r["score"] if r["score"] > 1.0 else r["tier"], -r["score"]))
    return {"rows": rows, "photos": photos, "models": models}


def _fmt(v, unit):
    if not isinstance(v, float):
        return "-"
    return f"{v:.3f}" if unit == "" else f"{v:.1f}"


def table_text(cmp: dict, top: int | None = None) -> str:
    rows = cmp["rows"]
    meas = [r for r in rows if r["score"] >= 0]
    over = [r for r in meas if r["score"] > 1.0]
    res = ", ".join(f"{p['kind']} {m['mmpx']:.2f} mm/px ({p['side'].source} / {m['side'].source})"
                    for p, m in zip(cmp["photos"], cmp["models"]))
    lines = [f"likeness: {len(meas)} item-views measured, {len(over)} beyond tolerance (photo vs model through the same "
             f"camera; miss = model - photo). Pictures: {res}. lm miss = the same measure on the landmarks alone (the photo's "
             "stored 68, the model's own); '!' = the two readings differ by more than the tolerance: the miss depends on the "
             "definition there, look at the panel before trusting it",
             f"{'#':>2} {'item':40} {'view':13} {'photo':>8} {'model':>8} {'miss':>8} {'tol':>6} {'xtol':>5} {'lm miss':>8}  stage: control"]
    for i, r in enumerate(meas[:top] if top else meas, 1):
        dp = 3 if r["unit"] == "" else 1
        lines.append(f"{i:>2} {r['name'][:40]:40} {r['view']:13} {_fmt(r['photo'], r['unit']):>8} {_fmt(r['model'], r['unit']):>8} "
                     f"{r['miss']:+8.{dp}f} {r['tol']:>6g} {r['score']:5.1f} "
                     + (f"{r['miss_lm']:+7.{dp}f}{' ' if r['agree'] else '!'}" if "miss_lm" in r else f"{'-':>8}")
                     + f"  {r['stage']}: {r['control']}"
                     + ("" if r["source"] == "detector/detector" else f"  [{r['source']}]")
                     + (f"  CAUTION {r['reliability']}" if r["reliability"] and r["score"] > 1 else ""))
    rest = [r for r in rows if r["score"] < 0]
    if rest:
        lines.append("not measured (judge in the focus panels, or the view is missing):")
        for r in rest:
            lines.append(f"   {r['name']} [{r['view']}]: {r.get('why') or 'judge by eye'}"
                         + (f"; {r['reliability']}" if r["reliability"] and r["reliability"] not in (r.get("why") or "") else ""))
    return "\n".join(lines)


# ---- focus panels: photo | model at the same crop and camera, the feature drawn on both -----------------------------

PANEL_PX = 300
PHOTO_COL, MODEL_COL = (255, 60, 40), (40, 210, 255)


def _draw_feature(d, Q, idx, col, r=3):
    for i in idx:
        x, y = Q[i]
        d.ellipse((x - r, y - r, x + r, y + r), outline=col, width=2)


def _region_pts(side: Side, idx):
    out = {}
    for i in idx:
        try:
            out[i] = side.pt(i)
        except Unmeasurable:
            pass
    return out


def panel(cmp: dict, row: dict, px: int = PANEL_PX):
    """One focus panel for a row: [photo | model], both cropped round the feature in the reference picture's pixels;
    the photo's points red, the model's blue on both halves (the gap between them is the miss)."""
    from PIL import Image, ImageDraw
    vi = row["vi"] if row["vi"] != "-" else 0
    ph, md = cmp["photos"][vi], cmp["models"][vi]
    m = _item(row["id"])["measure"]
    widths = _width_lines(m)
    idx = [i for i in row["points"] if i not in OVAL] if widths else row["points"]
    pp, mp_ = _region_pts(ph["side"], idx), _region_pts(md["side"], idx)
    segs = []
    for lv in widths:
        for sd, col in ((ph["side"], PHOTO_COL), (md["side"], MODEL_COL)):
            try:
                segs.append((_width_ends(sd, lv), col))
            except Unmeasurable:
                pass
    allp = list(pp.values()) + list(mp_.values()) + [p for s, _ in segs for p in s]
    allp = np.array(allp) if allp else np.array([[(ph["box"][0] + ph["box"][2]) / 2, (ph["box"][1] + ph["box"][3]) / 2]])
    lo, hi = allp.min(0), allp.max(0)
    side = max((hi - lo).max() * 1.4, 30.0 / max(md["mmpx"], 1e-6))   # at least 30 mm across
    b0 = ph["box"]
    side = min(side, b0[2] - b0[0], b0[3] - b0[1])
    c = (lo + hi) / 2
    c = np.clip(c, [b0[0] + side / 2, b0[1] + side / 2], [b0[2] - side / 2, b0[3] - side / 2])   # inside the render
    box = (c[0] - side / 2, c[1] - side / 2, c[0] + side / 2, c[1] + side / 2)
    k = md["k"]
    s = px / side

    def crop(img, origin, scale):
        return img.crop(tuple(int(round(v)) for v in ((box[0] - origin[0]) * scale, (box[1] - origin[1]) * scale,
                                                       (box[2] - origin[0]) * scale, (box[3] - origin[1]) * scale))).resize((px, px), Image.LANCZOS)
    a = crop(ph["img"], (0, 0), 1.0)
    b = crop(md["img"], (b0[0], b0[1]), k)
    for im in (a, b):
        d = ImageDraw.Draw(im)
        for (p, q), col in segs:
            d.line([tuple((p - box[:2]) * s), tuple((q - box[:2]) * s)], fill=col, width=2)
        _draw_feature(d, {i: (p - box[:2]) * s for i, p in pp.items()}, pp, PHOTO_COL)
        _draw_feature(d, {i: (p - box[:2]) * s for i, p in mp_.items()}, mp_, MODEL_COL, r=2)
    out = Image.new("RGB", (2 * px + 6, px + 34), (24, 24, 28))
    out.paste(a, (0, 34))
    out.paste(b, (px + 6, 34))
    d = ImageDraw.Draw(out)
    miss = f"{row['miss']:+.{3 if row['unit'] == '' else 1}f}{row['unit']} (tol {row['tol']:g})" if row["score"] >= 0 else "judge"
    d.text((4, 2), f"{row['name'][:46]} [{row['view']}]", fill=(240, 240, 240))
    d.text((4, 17), f"photo {_fmt(row['photo'], row['unit'])} | model {_fmt(row['model'], row['unit'])}  miss {miss}",
           fill=(255, 210, 120))
    return out


def focus_sheet(cmp: dict, out: str, top: int = 8, judge: bool = True, cols: int = 2, rows: list | None = None) -> str:
    """The top misses' panels (and, with judge, the judge-by-eye items) on one sheet; or the given rows."""
    from PIL import Image, ImageDraw
    if rows is not None:
        rows = [r for r in rows if r["vi"] != "-"][:top]
        judge = False
    else:
        rows = [r for r in cmp["rows"] if r["score"] > 1.0][:top]
    if judge:
        seen = set()
        for r in cmp["rows"]:
            if r["score"] < 0 and r["vi"] != "-" and r["id"] not in seen and r["points"]:
                seen.add(r["id"])
                rows.append(r)
    tiles = [panel(cmp, r) for r in rows]
    if not tiles:
        tiles = [Image.new("RGB", (2 * PANEL_PX + 6, PANEL_PX + 34), (24, 24, 28))]
    w, h = tiles[0].size
    n = len(tiles)
    sheet = Image.new("RGB", (cols * w + (cols - 1) * 8, ((n + cols - 1) // cols) * (h + 8) + 22), (14, 14, 16))
    ImageDraw.Draw(sheet).text((6, 4), "photo (left) | model (right), same camera and crop; red = photo's points, "
                                        "blue = model's", fill=(230, 230, 230))
    for i, t in enumerate(tiles):
        sheet.paste(t, ((i % cols) * (w + 8), 22 + (i // cols) * (h + 8)))
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out)
    return out


def report(name: str, base: dict | None = None, top: int = 8, save: str | None = None) -> tuple:
    """(table text, focus sheet path): every checklist item measured on the references and on the model."""
    from . import store
    cmp = compare(name, base)
    out = save or str(store.HOME / "human_renders" / f"lk_{name}_focus.png")
    focus_sheet(cmp, out, top=top)
    return table_text(cmp), out, cmp


# ---- staged fitting from the sheet: big to small, each stage through an existing control, guarded ------------------

JAW_CONTOUR = set(range(0, 7)) | set(range(10, 17))  # the 68's jaw contour: GNM's and the detector's differ (onemesh2):
#                                                     widths come from the outline fit instead; the chin (7-9) stays


def _stage(name: str) -> dict:
    for s in stage_names():
        if s["name"] == name:
            return s
    raise ValueError(f"likeness: no stage {name!r} (have {', '.join(s['name'] for s in stage_names())})")


def stage_points(stage: str) -> list:
    """The 68-point indices a stage fits: its own and every earlier stage's (so a later stage can't undo them)."""
    pts = []
    for s in stage_names():
        pts += s["points"]
        if s["name"] == stage:
            break
    return sorted(set(pts) - JAW_CONTOUR)


def stage_plan(name: str | None = None) -> str:
    """The stages in order with their items, controls and gaps (items with no control wired, or not measurable)."""
    sheet = None
    if name:
        from . import store
        p = store.HOME / name / TARGETS
        sheet = json.loads(p.read_text()) if p.exists() else None
    lines = []
    for i, s in enumerate(stage_names(), 1):
        lines.append(f"{i}. {s['name']}: {s['what']} -> {s['control']}")
        for it in checklist():
            if it["stage"] != s["name"]:
                continue
            c = it["control"]
            if it["measure"]["kind"] == "judge":
                gap = "  -> judge by eye; " + c
            elif c.startswith("GAP"):
                gap = "  -> " + c
            else:
                gap = "  -> " + c
            conf = ""
            if sheet and it["id"] in sheet["items"]:
                conf = " [" + ", ".join(f"{r.get('view', '-')}: {r['confidence']}" for r in sheet["items"][it["id"]]["views"].values()) + "]"
            lines.append(f"     {it['name']}{conf}{gap}")
    return "\n".join(lines)


def _views_with(refs: dict, pts: list) -> list:
    out = []
    for v in refs["views"]:
        p = {f"lm{i}": v["points"][f"lm{i}"] for i in pts if f"lm{i}" in v["points"]}
        out.append({**{k: v[k] for k in v if k != "points"}, "points": p})
    return out


_PHOTOS = {}


def _photos(refs: dict) -> list:
    k = hashlib.sha1(json.dumps(refs["views"], sort_keys=True).encode()).hexdigest()
    if k not in _PHOTOS:
        _PHOTOS.clear()
        _PHOTOS[k] = photo_sides(refs)
    return _PHOTOS[k]


def stage_wants(cmp: dict, stage: str) -> tuple:
    """(want, pins, gaps) for humanfit.solve from a comparison: each of the stage's items with a `solve` measure and a
    miss beyond its tolerance in the FRONT view asks that measure to move by the miss (front views are near
    orthographic: a 2D miss in mm is the 3D measure's, x across and z up); items sharing a measure add up. Earlier
    stages' measures are pinned where they are. gaps = the stage's items that miss with no solver measure."""
    from . import humanfit
    order = [s["name"] for s in stage_names()]
    k = order.index(stage)
    items = {it["id"]: it for it in checklist()}
    want, pins, gaps = {}, {}, []
    for r in cmp["rows"]:
        it = items[r["id"]]
        s = order.index(it["stage"])
        if r["view"] != "front" or s > k:
            continue
        if s < k:
            if it.get("solve"):
                pins[it["solve"]] = None
            continue
        if r["score"] <= 1.0:
            continue
        if it.get("solve"):
            want[it["solve"]] = want.get(it["solve"], 0.0) - r["miss"]
        elif r["score"] > 0:
            gaps.append(f"{it['name']} ({r['miss']:+.2f} {it['unit']}): {it['control']}")
    want = {m: f"{d:+.2f}" for m, d in want.items() if abs(d) > humanfit.TOL_MM}
    pins = {m: "+0" for m in pins if m not in want}
    return want, pins, gaps


def fit_stage(name: str, stage: str, base: dict | None = None, force: bool = False, save: bool = False,
              panels: str | None = None) -> dict:
    """One stage of the likeness fit: the stage's control run on the model (humanfit's guarded fits: a result that
    breaks the mesh is refused), the checklist measured before and after, the stage's items and any EARLIER stage's
    item that got worse beyond its tolerance listed, focus panels of the stage's items. save=True stores the result
    as a new version (and the refitted cameras in human_refs.json) unless it was refused."""
    from . import humanfit, store
    sp = store.load(name)
    base = base or sp["base"]
    refs = _refs(name)
    st = _stage(stage)
    photos = _photos(refs)
    cams0 = refs["cameras"]
    before = compare(name, base, photos=photos, cameras=cams0)
    order = [s["name"] for s in stage_names()]
    k = order.index(stage)
    rep = {"stage": stage, "control": st["control"], "steps": []}
    cur, cams = base, cams0
    want, pins, gaps = stage_wants(before, stage)
    rep["want"], rep["pins"], rep["gaps"] = want, pins, gaps
    if stage == "widths":
        cur, r = humanfit.fit_outline(cur, refs["views"], cams, force=force)
        rep["steps"].append(("fit_outline", r))
    if want:
        cur, r = humanfit.solve(cur, {**pins, **want}, force=force)
        rep["steps"].append((f"solve {want}" + (f", earlier stages pinned {sorted(pins)}" if pins else ""), r))
    if stage == "eyes":
        cur, r = humanfit.fit_hood(cur, _views_with(refs, list(humanfit.HOOD_LIDS)), cams, force=force)
        rep["steps"].append(("fit_hood", r))
    if not rep["steps"]:
        rep["gap"] = f"nothing to do with the wired controls for {stage}" + (": judge the panels" if gaps else "")
    after = compare(name, cur, photos=photos, cameras=cams)
    rep["refused"] = [f"{n}: {r['refused']}" for n, r in rep["steps"] if isinstance(r, dict) and r.get("refused")]
    rep["integrity"] = humanfit.verdict(humanfit.integrity(cur, None, humanfit.state(base))) if cur is not base else "unchanged"
    bmap = {(r["id"], r["vi"]): r for r in before["rows"]}
    mine, undone = [], []
    for r in after["rows"]:
        b = bmap.get((r["id"], r["vi"]))
        if b is None:
            continue
        s = order.index(r["stage"])
        if s == k:
            mine.append((b, r))
        elif s < k and r["score"] >= 0 and b["score"] >= 0 and r["score"] > max(b["score"], 1.0) + 0.5:
            undone.append((b, r))
    rep["rows"], rep["undone"] = mine, undone
    rep["text"] = stage_text(rep)
    rep["base"], rep["cameras"] = cur, cams
    rep["after"] = after
    if panels:
        focus_sheet(after, panels, top=12, rows=[r for _, r in mine])
        rep["panels"] = panels
    if save and cur is not base and not rep["refused"]:
        v = store.save(name, {**sp, "base": cur}, f"likeness stage {stage}: {st['control']}")
        refs2 = {**refs, "cameras": cams}
        (store.HOME / name / "human_refs.json").write_text(json.dumps(refs2, indent=1))
        rep["saved"] = v
        rep["text"] += f"\nsaved {name} v{v}"
    return rep


def stage_text(rep: dict) -> str:
    lines = [f"stage {rep['stage']} ({rep['control']}): {rep['integrity']}"]
    for n, r in rep["steps"]:
        extra = ""
        if isinstance(r, dict):
            if r.get("views"):
                extra = "; ".join(f"rms {v.get('rms_mm')} mm" for v in r["views"])
            if "amount" in r or "asked_mm" in r:
                extra = f"hood {r.get('amount_before')} -> {r.get('amount', r.get('asked_mm'))} mm"
            if r.get("refused"):
                extra += "  REFUSED: " + r["refused"]
        lines.append(f"  {n}: {extra}")
    if rep.get("gap"):
        lines.append("  GAP: " + rep["gap"])
    for g in rep.get("gaps") or []:
        lines.append("  no solver measure for: " + g)
    lines.append(f"  {'item':40} {'view':13} {'photo':>8} {'before':>8} {'after':>8} {'tol':>6}  x tol before -> after")
    for b, a in rep["rows"]:
        if a["score"] < 0:
            lines.append(f"  {a['name'][:40]:40} {a['view']:13}  (not measured: {a.get('why') or 'judge by eye'})")
            continue
        lines.append(f"  {a['name'][:40]:40} {a['view']:13} {_fmt(a['photo'], a['unit']):>8} {_fmt(b['model'], a['unit']):>8} "
                     f"{_fmt(a['model'], a['unit']):>8} {a['tol']:>6g}  {b['score']:.1f} -> {a['score']:.1f}"
                     + ("  ok" if a["score"] <= 1 else ""))
    if rep["undone"]:
        lines.append("  EARLIER STAGES MADE WORSE (review before going on):")
        for b, a in rep["undone"]:
            lines.append(f"    {a['name']} [{a['view']}] ({a['stage']}): {b['score']:.1f} -> {a['score']:.1f} x tol")
    return "\n".join(lines)


def fit_likeness(name: str, stages: list | None = None, force: bool = False, save: bool = True, panels_dir: str | None = None) -> list:
    """Run stages in order (all of them by default), each saved before the next. Stops at a refused stage. For a
    person or an LLM approving stage by stage, call with one stage at a time and look at its panels."""
    from . import store
    out = []
    names = stages or [s["name"] for s in stage_names()]
    for s in names:
        pn = str(Path(panels_dir or (store.HOME / "human_renders")) / f"lk_{name}_stage_{s}.png")
        rep = fit_stage(name, s, force=force, save=save, panels=pn)
        out.append(rep)
        if rep["refused"]:
            break
    return out
