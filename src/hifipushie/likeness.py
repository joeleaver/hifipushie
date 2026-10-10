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
        elif it["id"] in LEVERS:
            it["control"] = f"lever {LEVERS[it['id']][0]}"
        elif not any(w in c for w in ("fit_outline", "fit_hood")) and it["measure"]["kind"] != "judge":
            it["control"] = ("" if c.startswith("GAP") else "GAP: ") + c.replace("fit_views", "points by hand (fit_views / nudge)")
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
opts = vision.FaceLandmarkerOptions(base_options=mpt.BaseOptions(model_asset_path=sys.argv[2]), num_faces=1,
                                    output_face_blendshapes=True, output_facial_transformation_matrixes=True)
det = vision.FaceLandmarker.create_from_options(opts)
out = []
for p in sys.argv[3:]:
    im = Image.open(p).convert("RGB")
    res = det.detect(mp.Image(image_format=mp.ImageFormat.SRGB, data=np.asarray(im)))
    if not res.face_landmarks:
        out.append(None)
        continue
    d = {"P": [[q.x * im.size[0], q.y * im.size[1]] for q in res.face_landmarks[0]]}
    if res.face_blendshapes:
        d["bs"] = {b.category_name: round(float(b.score), 4) for b in res.face_blendshapes[0]}
    if res.facial_transformation_matrixes:
        d["M"] = np.asarray(res.facial_transformation_matrixes[0], float).tolist()
    out.append(d)
json.dump(out, open(sys.argv[1], "w"))
'''


def detector_available() -> bool:
    return (Path(VENV) / "bin" / "python").exists() and (Path(VENV) / "face_landmarker.task").exists()


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
            Path(src).write_text(_DETECT_SRC)
            subprocess.run([str(Path(VENV) / "bin" / "python"), src, res, str(Path(VENV) / "face_landmarker.task"), *paths],
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
    s = DETECT_PX / max(c.size)
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
    return model_mesh_from_state(humanfit.state(base))


def model_mesh_from_state(st: dict) -> dict:
    """model_mesh of a humanfit.state."""
    tpl, ht = st["tpl"], st["head"]
    Lf = np.asarray(tpl["L"]).reshape(-1, 4)
    F = np.r_[Lf[:, [0, 1, 2]], Lf[:, [0, 2, 3]]].astype(np.int64)
    V = np.asarray(tpl["P"], float)
    fwd = np.asarray(ht.get("forward", [0, -1, 0]), float)
    eyes = []
    r = float(ht.get("eye_r", 0.012))
    for c in ht["eyes"]:
        eyes.append(_sphere(c, r * 0.985, fwd))
    from . import likeness_shape as ls
    ears = None
    try:
        from . import base as basemod, onemesh
        gid = np.asarray(onemesh.asset()["gnm_id"], int)[np.asarray(tpl["fid"])]
        eg = np.asarray(basemod._gnm_data()["groups"]["ears"], float) > 0.5
        ears = np.where((gid >= 0) & eg[np.maximum(gid, 0)])[0]
    except Exception:  # noqa: BLE001  (not a one-mesh template: no ear vertices known)
        ears = None
    return {"V": V, "F": F, "eyes": eyes, "L": st["L"], "state": st, "ears": ears, "shape3d": ls.measures3d(st)}


SHADOW_MM = 0.25     # shadow / AO depth maps: mm per map pixel
AO_DIRS = 96         # AO: directions over the sphere (a Fibonacci set), each one orthographic depth map


OCCLUDE_R = 0.2      # m: occluders are the mesh within this of the eyes' midpoint (a one-mesh body is 1.7 m tall:
                     # its depth maps at SHADOW_MM were 27 Mpx; nothing below the neck shadows the face in these views)


def _occluders(mesh: dict):
    """(V, F) of everything near the face that casts shadow: the skin within OCCLUDE_R of the eyes and the eyeballs."""
    if "_occ" in mesh:
        return mesh["_occ"]
    V, F = mesh["V"], mesh["F"]
    if mesh["eyes"]:
        c = np.mean([e[0].mean(0) for e in mesh["eyes"]], 0)
        near = np.linalg.norm(V - c, axis=1) < OCCLUDE_R
        F = F[near[F].all(1)]
    Vs, Fs, n = [V], [F], len(V)
    for Ve, Fe, _ in mesh["eyes"]:
        Vs.append(Ve)
        Fs.append(Fe + n)
        n += len(Ve)
    Vo, Fo = np.concatenate(Vs), np.concatenate(Fs).astype(np.int64)
    used = np.unique(Fo)
    remap = np.full(len(Vo), -1)
    remap[used] = np.arange(len(used))
    mesh["_occ"] = (Vo[used], remap[Fo])
    return mesh["_occ"]


def _vertex_normals(V, F):
    fn = np.cross(V[F[:, 1]] - V[F[:, 0]], V[F[:, 2]] - V[F[:, 0]])
    vn = np.zeros_like(V)
    for c in range(3):
        np.add.at(vn, F[:, c], fn)
    return vn / np.maximum(np.linalg.norm(vn, axis=1, keepdims=True), 1e-15)


class _DepthMap:
    """An orthographic depth map of (V, F) seen from far along direction d (unit, world, pointing TO the source):
    depth = -X . d (smaller = nearer the source); `lit(X, n)` says which points the source sees (no occluder nearer
    than the point, with a slope-scaled bias)."""

    def __init__(self, V, F, d, mm=SHADOW_MM):
        if not _RUN:
            _RUN.append(_raster())
        d = np.asarray(d, float) / np.linalg.norm(d)
        a = np.array([1.0, 0, 0]) if abs(d[0]) < 0.9 else np.array([0, 1.0, 0])
        u = np.cross(d, a)
        u /= np.linalg.norm(u)
        v = np.cross(d, u)
        self.d, self.B, self.s = d, np.stack([u, v]), 1000.0 / mm   # px per m
        uv = V @ self.B.T
        self.o = uv.min(0) - 2 / self.s
        q = (uv - self.o) * self.s
        W, H = int(np.ceil(q[:, 0].max())) + 3, int(np.ceil(q[:, 1].max())) + 3
        self.zb = np.full((H, W), np.inf)
        dummy = np.zeros((H, W, 3))
        _RUN[0](q[:, 0], q[:, 1], -(V @ d), np.ascontiguousarray(F), np.zeros((len(V), 3)), W, H, dummy, self.zb)
        # 3 x 3 max filter of the occluder depth: a point is tested against its own surface's farthest neighbour, so the
        # rasterised surface never shadows itself (map aliasing), while a real occluder (mm in front) still does
        from scipy.ndimage import maximum_filter
        z = np.where(np.isfinite(self.zb), self.zb, -np.inf)
        self.zmax = maximum_filter(z, 3)

    def lit(self, X, n=None, bias_mm=0.35):
        q = (X @ self.B.T - self.o) * self.s
        j = np.clip(np.floor(q[:, 0]).astype(int), 0, self.zb.shape[1] - 1)
        i = np.clip(np.floor(q[:, 1]).astype(int), 0, self.zb.shape[0] - 1)
        z = -(X @ self.d)
        bias = bias_mm * 1e-3
        if n is not None:
            c = np.clip(n @ self.d, 0.05, 1.0)
            bias = bias + 1.5 / self.s * np.sqrt(1 - c ** 2) / c
            bias = np.minimum(bias, 8.0 / self.s + bias_mm * 1e-3)
        return z <= self.zmax[i, j] + bias


def ambient_occlusion(mesh: dict, n_dirs: int = AO_DIRS, mm: float = 0.5) -> np.ndarray:
    """Per-vertex ambient occlusion of the skin (cosine-weighted visibility of the sky over each vertex's hemisphere,
    1 = open), the eyeballs occluding too; cached on the mesh dict. What makes the nostrils, the stomion, the lid
    crease's fold and the alar groove dark in a photo's soft light, which smooth-normal clay can't."""
    if "_ao" in mesh:
        return mesh["_ao"]
    V, F = mesh["V"], mesh["F"]
    Vo, Fo = _occluders(mesh)
    vn = _vertex_normals(V, F)
    k = np.arange(n_dirs) + 0.5
    th = np.arccos(1 - 2 * k / n_dirs)
    ph = np.pi * (1 + 5 ** 0.5) * k
    D = np.c_[np.sin(th) * np.cos(ph), np.sin(th) * np.sin(ph), np.cos(th)]
    num, den = np.zeros(len(V)), np.zeros(len(V))
    near = np.ones(len(V), bool)
    if mesh["eyes"]:
        near = np.linalg.norm(V - np.mean([e[0].mean(0) for e in mesh["eyes"]], 0), axis=1) < OCCLUDE_R
    for d in D:
        c = vn @ d
        up = (c > 0) & near
        if not up.any():
            continue
        dm = _DepthMap(Vo, Fo, d, mm)
        vis = dm.lit(V[up], vn[up])
        num[up] += c[up] * vis
        den[up] += c[up]
    mesh["_ao"] = np.where(near, num / np.maximum(den, 1e-9), 1.0)
    return mesh["_ao"]


def render(mesh: dict, cam: dict, box, px: int = RENDER_PX, brows: bool = True, passes: bool = False, light=None,
           ao: bool = False, shadow: bool = False):
    """(PIL image, scale px per picture pixel): the model through the reference's camera, cropped to box (picture
    pixels), lit by a key from the upper left (smooth normals), eyes with irises, brows drawn. passes=True also
    returns {"zb": camera depth (m; inf off the model), "nrm": camera-frame normals, "part": 0 skin / 1 eyes / -1 none}.
    light = (c0, w) (likeness_shape.fit_light: luminance = c0 + w . n) lights the skin like the photo instead.
    ao=True darkens the ambient term by ambient_occlusion (nostrils, stomion, folds); shadow=True casts the key's (or
    the photo light's w) shadows per pixel from a depth map (shadow=<degrees>: a disc light that wide, soft edges) (the upper lip's shadow on the lower, the nose's on the
    lip, the brow's on the lid): the cues a photo shows and the readers compare (passes then also has "lit": the
    direct light's visibility per pixel, "ao" per pixel)."""
    from PIL import Image, ImageDraw
    from . import humanfit
    if not _RUN:
        _RUN.append(_raster())
    if ao or shadow:
        return _render_shaded(mesh, cam, box, px, brows, passes, light, ao, shadow)
    x0, y0, x1, y1 = box
    k = px / max(x1 - x0, y1 - y0)
    W, H = int(round((x1 - x0) * k)), int(round((y1 - y0) * k))
    img = np.full((H, W, 3), 238.0)
    zb = np.full((H, W), np.inf)
    nimg = np.zeros((H, W, 3))
    pimg = np.full((H, W, 3), -1.0)
    zn, zq = np.full((H, W), np.inf), np.full((H, W), np.inf)
    Rc = humanfit._cam_rot(cam)
    parts = [(mesh["V"], mesh["F"], None)] + list(mesh["eyes"])
    for pi, (V, F, col) in enumerate(parts):
        if passes or light is not None:
            Xc = (V - np.asarray(cam["centre"])) @ Rc.T + np.asarray(cam["t"])
            P = humanfit.project(cam, V)
            fn = np.cross(Xc[F[:, 1]] - Xc[F[:, 0]], Xc[F[:, 2]] - Xc[F[:, 0]])
            keep = (fn * Xc[F].mean(1)).sum(1) < 0
            vn = np.zeros_like(Xc)
            for c in range(3):
                np.add.at(vn, F[:, c], fn)
            vn /= np.maximum(np.linalg.norm(vn, axis=1, keepdims=True), 1e-15)
            args = ((P[:, 0] - x0) * k, (P[:, 1] - y0) * k, Xc[:, 2].copy(), np.ascontiguousarray(F[keep]))
            _RUN[0](*args, np.ascontiguousarray(vn), W, H, nimg, zn)
            _RUN[0](*args, np.ascontiguousarray(np.full_like(vn, float(min(pi, 1)))), W, H, pimg, zq)
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
        if light is not None and col is None:  # the photo's light (linear luminance -> sRGB grey, skin-tinted)
            lum = np.clip((light[0] + vn @ np.asarray(light[1])) / max(light[2] if len(light) > 2 else 0.2, 1e-6), 0.0, 3.0)
            sh = 0.8 * lum ** (1 / 2.2)   # the face's median at 0.8 of the skin colour
        base_c = (np.asarray(mesh["C"], float) if mesh.get("C") is not None else np.broadcast_to(SKIN, Xc.shape)) if col is None else col
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
    if passes:
        return im, k, {"zb": zn, "nrm": nimg, "part": np.where(np.isfinite(zq), pimg[..., 0], -1).round().astype(int)}
    return im, k


SOFT_N = 16   # soft shadows: samples over the light's disc


def _light_disc(d, deg: float) -> list:
    """Directions over a disc light of angular radius deg about d (a Fibonacci spiral; [d] for a point light)."""
    d = np.asarray(d, float) / np.linalg.norm(d)
    if deg <= 0:
        return [d]
    a = np.array([1.0, 0, 0]) if abs(d[0]) < 0.9 else np.array([0, 1.0, 0])
    u = np.cross(d, a)
    u /= np.linalg.norm(u)
    v = np.cross(d, u)
    out = []
    for i in range(SOFT_N):
        r = np.tan(np.radians(deg)) * np.sqrt((i + 0.5) / SOFT_N)
        t = i * np.pi * (3 - 5 ** 0.5)
        e = d + r * (np.cos(t) * u + np.sin(t) * v)
        out.append(e / np.linalg.norm(e))
    return out


def _render_shaded(mesh, cam, box, px, brows, passes, light, ao, shadow):
    """render() with ambient occlusion and / or cast shadows: the ambient and the direct terms are rasterised
    separately (per-vertex, interpolated) and the direct one is multiplied per pixel by the key's visibility."""
    from PIL import Image, ImageDraw
    from . import humanfit
    x0, y0, x1, y1 = box
    k = px / max(x1 - x0, y1 - y0)
    W, H = int(round((x1 - x0) * k)), int(round((y1 - y0) * k))
    Rc = humanfit._cam_rot(cam)
    aov = ambient_occlusion(mesh) if ao else np.ones(len(mesh["V"]))
    key_c = np.asarray(light[1], float) if light is not None else KEY
    key_w = Rc.T @ (key_c / max(np.linalg.norm(key_c), 1e-12))   # world direction to the light
    parts = [(mesh["V"], mesh["F"], None, aov)] + [(V, F, col, None) for V, F, col in mesh["eyes"]]
    img_a, img_d = np.full((H, W, 3), 238.0), np.zeros((H, W, 3))
    za, zd = np.full((H, W), np.inf), np.full((H, W), np.inf)
    nimg, pimg, aimg = np.zeros((H, W, 3)), np.full((H, W, 3), -1.0), np.ones((H, W, 3))
    zn, zq, zo = (np.full((H, W), np.inf) for _ in range(3))
    for pi, (V, F, col, av) in enumerate(parts):
        Xc = (V - np.asarray(cam["centre"])) @ Rc.T + np.asarray(cam["t"])
        P = humanfit.project(cam, V)
        fn = np.cross(Xc[F[:, 1]] - Xc[F[:, 0]], Xc[F[:, 2]] - Xc[F[:, 0]])
        keep = (fn * Xc[F].mean(1)).sum(1) < 0
        vn = np.zeros_like(Xc)
        for c in range(3):
            np.add.at(vn, F[:, c], fn)
        vn /= np.maximum(np.linalg.norm(vn, axis=1, keepdims=True), 1e-15)
        args = ((P[:, 0] - x0) * k, (P[:, 1] - y0) * k, Xc[:, 2].copy(), np.ascontiguousarray(F[keep]))
        base_c = (np.asarray(mesh["C"], float) if mesh.get("C") is not None else np.broadcast_to(SKIN, Xc.shape)) if col is None else col
        avv = np.ones(len(V)) if av is None else av
        if light is not None and col is None:
            sc = max(light[2] if len(light) > 2 else 0.2, 1e-6)
            # light[3] (optional, 0..1): how much of the ambient term AO darkens (fitted to the photo: soft studio
            # light fills cavities more than an open sky does)
            aw = float(light[3]) if len(light) > 3 else 1.0
            amb = float(light[0]) / sc * (1.0 - aw + aw * avv)
            dirc = (vn @ np.asarray(light[1], float)) / sc
            # (the photo's linear model: the negative part of w . n stays ambient-like, unshadowed)
            amb = amb + np.minimum(dirc, 0)
            dirc = np.maximum(dirc, 0)
            Ca = 0.8 * np.clip(amb, 0, 3)[:, None] * base_c
            Cd = 0.8 * np.clip(dirc, 0, 3)[:, None] * base_c
        else:
            Ca = base_c * ((0.24 + 0.06 * np.clip(-vn[:, 2], 0, 1)) * avv)[:, None]
            Cd = base_c * (0.76 * np.clip(vn @ KEY, 0, 1) ** 1.3)[:, None]
        _RUN[0](*args, np.ascontiguousarray(Ca), W, H, img_a, za)
        _RUN[0](*args, np.ascontiguousarray(Cd), W, H, img_d, zd)
        _RUN[0](*args, np.ascontiguousarray(vn), W, H, nimg, zn)
        _RUN[0](*args, np.ascontiguousarray(np.full_like(vn, float(min(pi, 1)))), W, H, pimg, zq)
        _RUN[0](*args, np.ascontiguousarray(np.repeat(avv[:, None], 3, 1)), W, H, aimg, zo)
    lit = np.ones((H, W))
    on = np.isfinite(zn)
    if shadow and on.any():
        from .likeness_shape import unproject
        Vo, Fo = _occluders(mesh)
        ii, jj = np.nonzero(on)
        uv = np.c_[x0 + (jj + 0.5) / k, y0 + (ii + 0.5) / k]
        Xw = unproject(cam, uv, zn[ii, jj])
        nw = nimg[ii, jj] @ Rc   # camera-frame normals back to world
        acc = np.zeros(len(ii))
        dirs = _light_disc(key_w, 0.0 if shadow is True else float(shadow))
        for d in dirs:
            acc += _DepthMap(Vo, Fo, d).lit(Xw, nw)
        lit[ii, jj] = acc / len(dirs)
        from scipy.ndimage import gaussian_filter
        lit = np.where(on, np.clip(gaussian_filter(lit, 0.6), 0, 1), 1.0)   # (a pixel's worth of penumbra)
    img = np.clip(img_a + img_d * lit[..., None], 0, 255)
    img[~on] = 238.0
    im =Image.fromarray(img.astype(np.uint8))
    if brows:
        L = humanfit.project(cam, mesh["L"])
        d = ImageDraw.Draw(im)
        wpx = max(2, int(round(_mm_per_px(cam, mesh["L"]) ** -1 * 4.0 * k)))
        for a, b in ((17, 22), (22, 27)):
            pts = [((L[i, 0] - x0) * k, (L[i, 1] - y0) * k) for i in range(a, b)]
            d.line(pts, fill=(70, 52, 40), width=wpx, joint="curve")
    if passes:
        return im, k, {"zb": zn, "nrm": nimg, "part": np.where(np.isfinite(zq), pimg[..., 0], -1).round().astype(int),
                       "lit": lit, "ao": np.where(on, aimg[..., 0], 1.0)}
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
    if m.get("kind") == "shape":
        return sorted({int(r[k]) for r in (m["region"], m["ref"]) for k in ("at", "from", "to") if k in r})
    if m.get("kind") == "jaw":
        return []
    for k, v in m.items():
        if k in ("a", "b", "vertex", "level", "from", "to", "pts", "line", "region"):
            out += list(np.ravel(v))
        elif k == "pairs":
            out += list(np.ravel([i for p in v for x in p for i in np.ravel(x)]))
        elif k in ("num", "den"):
            out += points_of(v)
        elif k in ("outer", "inner"):
            out += list(np.ravel(v))
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


def _facing(side: Side, ex) -> float:
    """+1 when the face points along +ex in the picture (its nose tip ahead of its wings), else -1."""
    return 1.0 if (side.pt(1) - side.pt([129, 358])) @ ex >= 0 else -1.0


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
        if m.get("forward"):  # signed toward where the face points (+ = b ahead of a): turned views only
            vals = [v * _facing(side, ex) for v in vals]
        return float(np.mean(vals)) * mmpx
    if k == "eline":  # signed distance of points from the line a -> b, + = ahead of it (toward where the face points)
        a, b, q = side.pt(m["a"]), side.pt(m["b"]), side.pt(m["pts"])
        ex, ey = side.frame()
        t = (b - a) / max(np.linalg.norm(b - a), 1e-9)
        n = np.array([-t[1], t[0]])
        if (n @ ex) * _facing(side, ex) < 0:
            n = -n
        return float((q - a) @ n) * mmpx
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
    if k in ("cushion", "lip_area"):
        # the lower vermilion between its outer (skin) border and its inner (contact) line, corner to corner:
        # "cushion" = its visible width (where it is thicker than `frac` of its middle) over the mouth's width (a
        # short central cushion vs a lip out to the corners); "lip_area" = its area over the mouth's width squared
        # (fullness: a pouting lower lip shows more red)
        ex, ey = side.frame()
        O = np.array([side.pt(i) for i in m["outer"]])
        I_ = np.array([side.pt(i) for i in m["inner"]])
        wm = float((O[-1] - O[0]) @ ex)
        if abs(wm) < 1e-9:
            return float("nan")
        if k == "lip_area":
            P = np.r_[O, I_[::-1]]
            area = 0.5 * abs(float(np.dot(P[:, 0], np.roll(P[:, 1], -1)) - np.dot(P[:, 1], np.roll(P[:, 0], -1))))
            return area / wm ** 2
        t = np.abs((O - I_) @ ey)
        u = ((0.5 * (O + I_)) - O[0]) @ ex / wm
        mid = len(t) // 2
        lim = float(m.get("frac", 0.5)) * t[mid]
        ends = []
        for rng in (range(mid, 0, -1), range(mid, len(t) - 1)):
            e = None
            for i in rng:
                j = i - 1 if rng.step < 0 else i + 1
                if t[j] < lim <= t[i]:
                    e = u[i] + (u[j] - u[i]) * (t[i] - lim) / max(t[i] - t[j], 1e-12)
                    break
            ends.append(u[0] if (e is None and rng.step < 0) else (u[-1] if e is None else e))
        return float(abs(ends[1] - ends[0]))
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
    # (below the chin: the jaw's lower border and the neck under it are checklist items)
    return (max(lo[0] - pad, 0.0), max(lo[1] - pad * 1.2, 0.0), min(hi[0] + pad, size[0]), min(hi[1] + pad * 1.1, size[1]))


def photo_sides(refs: dict) -> list:
    """Each reference picture as a Side (the detector on a crop round its face; its stored points as the fallback)."""
    from PIL import Image
    out = []
    for v, cam in zip(refs["views"], refs["cameras"]):
        img = Image.open(v["image"]).convert("RGB")
        box = _box(v["points"], img.size)
        info = detect_region(img, box, info=True)
        P = None if info is None else info["P"]
        out.append({"view": v, "cam": cam, "kind": view_kind(cam.get("yaw", v.get("yaw", 0))), "img": img, "box": box,
                    "side": Side(P, _lm_from_points(v["points"]), "detector" if P is not None else "landmarks"),
                    "mmpx": float(cam["t"][2] / cam["f"] * 1000.0), "info": info or {}})
    return out


REFIT = ("three_quarter", "profile")  # views whose camera is refitted on the detector's points (a loose painting)
REFIT_ROUNDS = 2
INFER_TOL = 1.5     # a profile item read from a three-quarter view ("inferred"): its tolerance x this
SPECIAL = ("shape", "jaw", "contour")   # measured in compare (they need the model's render or a trace), not from points alone


def _refit(mesh, ph, cam):
    """The camera refitted for this picture: the detector's 478 on the photo against the model's surface under the same
    detector points on its render (unprojected through the render's depth), pose and focal, REFIT_ROUNDS rounds."""
    from . import likeness_shape as ls
    if ph["side"].P is None:
        return cam, None
    keep = np.setdiff1d(np.arange(468), OVAL)
    res = None
    for _ in range(REFIT_ROUNDS):
        im, k, ps = render(mesh, cam, ph["box"], passes=True)
        Pm = detect([im])[0]
        if Pm is None:
            break
        ij = np.clip(Pm[keep].astype(int), 0, [ps["zb"].shape[1] - 1, ps["zb"].shape[0] - 1])
        z = ps["zb"][ij[:, 1], ij[:, 0]]
        ok = np.isfinite(z) & (ps["part"][ij[:, 1], ij[:, 0]] == 0)
        uvm = Pm[keep][ok] / k + [ph["box"][0], ph["box"][1]]
        X = ls.unproject(cam, uvm, z[ok])
        cam, r = ls.refit_camera(cam, ph["side"].P[keep][ok], X)
        res = np.full(478, np.nan)
        res[keep[ok]] = r
    return cam, res


def model_sides(base: dict, photos: list, mesh=None, cameras=None, refit: bool = True) -> list:
    """The model through each reference's camera (refitted for REFIT views): the clay render, the detector on it, its
    own landmarks projected, its passes (depth, normals), the light fitted to the photo on its normals and the
    residual shading, and a render lit like the photo for the panels."""
    from . import humanfit
    from . import likeness_shape as ls
    mesh = mesh or model_mesh(base)
    out = []
    for i, ph in enumerate(photos):
        cam, box = (cameras[i] if cameras else ph["cam"]), ph["box"]
        cres = None
        if refit and ph["kind"] in REFIT and not cameras:
            cam, cres = _refit(mesh, ph, cam)
        im, k, ps = render(mesh, cam, box, passes=True)
        P = detect([im])[0]
        P = None if P is None else P / k + [box[0], box[1]]
        mmpx = _mm_per_px(cam, mesh["L"])
        md = {"img": im, "k": k, "cam": cam, "passes": ps, "cam_res": cres, "mmpx": mmpx, "mesh": mesh,
              "side": Side(P, humanfit.project(cam, mesh["L"]), "detector" if P is not None else "landmarks")}
        md["shade"] = _shade(ph, md)
        if md["shade"]:
            md["img_lit"] = render(mesh, cam, box, light=(md["shade"]["c0"], md["shade"]["w"], md["shade"]["med"]))[0]
        out.append(md)
    return out


def _shade(ph, md) -> dict | None:
    """The photo's light fitted on the model's normals over the face's skin, and the residual (photo / model lit so - 1)."""
    from PIL import Image
    from . import likeness_shape as ls
    if ph["side"].P is None:
        return None
    k, box, ps = md["k"], ph["box"], md["passes"]
    H, W = ps["zb"].shape
    crop = ph["img"].crop(tuple(int(round(v)) for v in box)).resize((W, H), Image.LANCZOS)
    Y = ls._lin(crop)
    to_px = lambda P: (np.asarray(P, float) - [box[0], box[1]]) * k  # noqa: E731
    ppm = k / md["mmpx"]
    mask = ls.skin_mask(ph["side"], (H, W), to_px, ppm) & (ps["part"] == 0)
    if mask.sum() < 500:
        return None
    c0, w, rms = ls.fit_light(Y, ps["nrm"], mask)
    R = ls.residual(Y, ps["nrm"], c0, w, mask, 1.5 * ppm)
    ex, ey = ph["side"].frame()
    hard = float(np.linalg.norm(w) / max(c0 + np.linalg.norm(w), 1e-6))
    return {"c0": c0, "w": w, "rms": rms, "R": R, "med": float(np.median(Y[mask])), "mask": mask, "to_px": to_px, "ppm": ppm, "ex": ex, "ey": ey,
            "hard": hard, "fit_share": float(rms / max(np.nanmean(Y[mask]), 1e-6))}


def _allowed(it: dict, vk: str, kinds: list) -> tuple:
    """(measured in this view, inferred): a profile item falls back to a three-quarter view when there's no profile."""
    if vk in it["views"]:
        return True, False
    if "profile" in it["views"] and vk == "three_quarter" and "profile" not in kinds:
        return True, True
    return False, False


def measure_sides(sides: list, kinds: list, mmpxs: list) -> dict:
    """{item id: {view index: value | "unmeasurable: why"}}; "-" when no picture has a view the item needs. Shape and
    jaw items are left to compare (`SPECIAL`)."""
    out = {}
    for it in checklist():
        if it["measure"]["kind"] in SPECIAL:
            continue
        row = {}
        for vi, (s, vk, mp) in enumerate(zip(sides, kinds, mmpxs)):
            ok, _ = _allowed(it, vk, kinds)
            if not ok:
                continue
            try:
                row[vi] = value(s, it["measure"], mp)
            except Unmeasurable as e:
                row[vi] = f"unmeasurable: {e}"
        if not row:
            row["-"] = "unmeasurable: " + " or ".join(it["views"]) + " view needed"
        out[it["id"]] = row
    return out


def _near_sign(side: Side) -> list:
    """Sides to read in a picture: both in a front view, only the nearer (wider eye) in a turned one: [-1] = the
    subject's right, [1] its left."""
    try:
        wr = np.linalg.norm(side.pt(33) - side.pt(133))
        wl = np.linalg.norm(side.pt(263) - side.pt(362))
    except Unmeasurable:
        return [-1, 1]
    if max(wr, wl) / max(min(wr, wl), 1e-6) < 1.25:
        return [-1, 1]
    return [-1] if wr > wl else [1]


MIRROR = {61: 291, 234: 454, 33: 263, 133: 362, 145: 374, 159: 386, 129: 358, 98: 327, 172: 397, 105: 334, 70: 300,
          107: 336, 52: 282, 58: 288, 136: 365, 116: 345, 123: 352, 50: 280, 205: 425, 147: 376, 187: 411, 93: 323}


def _shape_rows(it, photos, models, kinds) -> list:
    from . import likeness_shape as ls
    rows = []
    m = it["measure"]
    for vi, (ph, md) in enumerate(zip(photos, models)):
        ok, inferred = _allowed(it, kinds[vi], kinds)
        if not ok:
            continue
        sh = md.get("shade")
        r = {"vi": vi, "inferred": inferred, "model3d": md.get("shape3d", {}).get(m.get("model3d"))}
        if sh is None:
            r["why"] = "no shading (no detector on the photo)"
            rows.append(r)
            continue
        vals = []
        for sgn in _near_sign(ph["side"]):
            pidx = (lambda i, s=sgn: MIRROR.get(i, i) if s > 0 else i)
            exs = sh["ex"]
            reg = ls.region_centre(ph["side"], m["region"], sgn, exs, sh["ey"], sh["ppm"], sh["to_px"], pidx)
            ref = ls.region_centre(ph["side"], m["ref"], sgn, exs, sh["ey"], sh["ppm"], sh["to_px"], pidx)
            H, W = sh["R"].shape
            a = sh["R"][ls._disk(H, W, reg, m["region"].get("r_mm", 4) * sh["ppm"])]
            b = sh["R"][ls._disk(H, W, ref, m["ref"].get("r_mm", 5) * sh["ppm"])]
            a, b = a[np.isfinite(a)], b[np.isfinite(b)]
            if len(a) < 10 or len(b) < 10:
                continue
            vals.append(100 * (a.mean() - b.mean()))
            r.setdefault("regions", []).append((reg, ref, m["region"].get("r_mm", 4) * sh["ppm"], m["ref"].get("r_mm", 5) * sh["ppm"]))
        if vals:
            r["photo"] = float(np.mean(vals))
        else:
            r["why"] = "region off the face's skin in this picture"
        rows.append(r)
    return rows


def _jaw_rows(it, photos, models, kinds, traces) -> list:
    from . import likeness_shape as ls
    rows = []
    key = it["measure"]["key"]
    for vi, (ph, md) in enumerate(zip(photos, models)):
        ok, inferred = _allowed(it, kinds[vi], kinds)
        if not ok:
            continue
        tr = traces.get(ph["view"]["image"], {})
        r = {"vi": vi, "inferred": inferred}
        got = False
        for sd in ("R", "L"):
            Q = tr.get("lines", {}).get(f"jaw.{sd}")
            if not Q or len(Q) < 6:
                continue
            pv, mv = _jaw_pair(ph, md, tr, sd)
            if key in pv and key in mv:
                r.setdefault("pairs", []).append((pv[key], mv[key]))
                r.setdefault("traces", []).append((np.asarray(Q, float), mv.get("_line"), pv.get("_gonion"), mv.get("_gonion")))
                got = True
        if got:
            r["photo"] = float(np.mean([a for a, b in r["pairs"]]))
            r["model"] = float(np.mean([b for a, b in r["pairs"]]))
        else:
            r["why"] = ("needs a trace on this picture: likeness_points 'jaw.R' / 'jaw.L' (down the ramus, round the angle, "
                        "forward along the lower border)" + ("; 'ear_lobe.R' for the lobe" if "lobe" in key else "")
                        + ("; 'neck.R' for the neck" if "neck" in key else ""))
        rows.append(r)
    return rows


def profile_read(ph, md, traces):
    """likeness_profile.read for one picture, kept on the model's entry (None: no "profile" line on that picture)."""
    from . import likeness_profile as lp
    if "profile" not in md:
        lines = traces.get(ph["view"]["image"], {}).get("lines", {})
        try:
            md["profile"] = (lp.read(ph["img"], lines, md, ph["box"], ph["side"].P,
                                     traces.get(ph["view"]["image"], {}).get("points", {})) if lines.get("profile") else None)
        except Exception as e:  # noqa: BLE001
            md["profile"] = None
            md["profile_error"] = str(e)
    return md["profile"]


CONTOUR_WHY = {"upper_lip": "the lips don't break this contour (no notch between them at this angle)",
               "lower_lip": "the lips don't break this contour (no notch between them at this angle)",
               "forehead_slope": "the trace doesn't run 4 cm up the forehead"}


def _contour_rows(it, photos, models, kinds, traces) -> list:
    rows = []
    key = it["measure"]["key"]
    nose = key.startswith(("nose", "bridge", "tip_", "columella"))
    for vi, (ph, md) in enumerate(zip(photos, models)):
        ok, inferred = _allowed(it, kinds[vi], kinds)
        if not ok or kinds[vi] == "front":
            continue
        rd = profile_read(ph, md, traces)
        r = {"vi": vi, "inferred": False}
        if rd is None:
            r["why"] = ("needs a trace on this picture: likeness_points line 'profile' (the far side of the face against "
                        "the background, forehead to under the chin)" + ("; 'nose' (the nose's own edge)" if nose else ""))
        elif key in rd["photo"]["m"] and key in rd["model"]["m"]:
            r["photo"], r["model"] = float(rd["photo"]["m"][key]), float(rd["model"]["m"][key])
            r["traces"] = [(rd["photo"]["line"], rd["model"]["line"], None, None)]
            if "nose" in rd["photo"]:
                r["traces"].append((rd["photo"]["nose"]["line"], rd["model"]["nose"]["line"], None, None))
            o, ex, ey = rd["frame"]
            names = {"chin_projection": ("chin", "brow"), "cheek_line": ("mouth", "brow"), "chin_height": ("chin", "mouth"),
                     "brow_ridge": ("brow", "orbit"), "mentolabial": ("sulcus",), "forehead_slope": ("fh1", "fh2"),
                     "upper_lip": ("ul", "sto"), "lower_lip": ("ll_notch", "sto")}.get(key, ())
            marks = []
            for sd_ in ("photo", "model"):
                kk = {**rd[sd_]["kp"], **rd[sd_]["kn"]} if nose else rd[sd_]["kp"]
                nm = ("tip", "under", "base", "nasion", "alar") if nose else names
                marks.append([o + ex * kk[n][1] / rd["mmpx"] + ey * kk[n][0] / rd["mmpx"] for n in nm if n in kk])
            r["marks"] = marks
        else:
            r["why"] = CONTOUR_WHY.get(key, "the line 'nose' is not traced on this picture" if nose and "nose" not in rd["photo"]
                                       else "needs the hand-placed point 'alar_base.R' / '.L' (the near wing's base) on this picture"
                                       if nose and "alar" not in rd["photo"]["kn"] and key in ("nose_base_incl", "tip_height", "columella_show")
                                       else "not found on this contour")
        rows.append(r)
    return rows


def _jaw_pair(ph, md, tr, sd):
    """The jaw measures on the photo's trace and on the model's contour found along it (picture pixels)."""
    from . import likeness_shape as ls
    from . import humanfit
    ex, ey = ph["side"].frame()
    mmpx = md["mmpx"]
    Q = np.asarray(tr["lines"][f"jaw.{sd}"], float)
    pts = tr.get("points", {})
    try:
        mouth_p = ph["side"].pt([13, 14])
        mouth_m = md["side"].pt([13, 14])
    except Unmeasurable:
        mouth_p = mouth_m = None
    neck_p = tr.get("lines", {}).get(f"neck.{sd}")
    pv = ls.jaw_measures(Q, ex, ey, mmpx, pts.get(f"ear_lobe.{sd}"), mouth_p, neck_p)
    # the model's jaw line by GEOMETRY, not an image search (the contour found in the render read a neck step of
    # 7-27 mm on one head between runs): its own jaw-contour landmarks on that side (lm 2..8: the line onemesh2's
    # shape.jawline moves, the skin following), densified in 3D and projected; the neck under it = the outermost skin
    # 12-30 mm below the border two thirds of the way to the chin.
    L3, V3 = md["mesh"]["L"], md["mesh"]["V"]
    mx = 0.5 * (L3[68, 0] + L3[69, 0])
    sx = -1.0 if sd == "R" else 1.0
    ids = [2, 3, 4, 5, 6, 7, 8] if np.sign(L3[3, 0] - mx) == sx else [14, 13, 12, 11, 10, 9, 8]
    O = L3[ids]
    seg = np.linalg.norm(np.diff(O, axis=0), axis=1)
    u = np.r_[0, np.cumsum(seg)] / seg.sum()
    J3 = np.c_[[np.interp(np.linspace(0, 1, 40), u, O[:, c]) for c in range(3)]].T
    Qm = humanfit.project(md["cam"], J3)
    i3 = ls._split_corner(Qm)
    B = J3[i3 + (2 * (len(J3) - i3)) // 3] if i3 is not None else J3[26]
    neck_m = None
    ears_i = md["mesh"].get("ears")
    skin = np.ones(len(V3), bool)
    if ears_i is not None:
        skin[ears_i] = False
    side_v = skin & (np.sign(V3[:, 0] - mx) == sx) & (np.abs(V3[:, 1] - B[1]) < 0.012)
    npts = []
    for z0, z1 in ((0.012, 0.02), (0.02, 0.03)):
        kk = side_v & (V3[:, 2] < B[2] - z0) & (V3[:, 2] > B[2] - z1)
        if kk.any():
            npts.append(V3[kk][np.argmax(np.abs(V3[kk][:, 0] - mx))])
    if len(npts) == 2 and neck_p and len(neck_p) >= 2:
        neck_m = humanfit.project(md["cam"], np.array(npts))
    lobe_m = None
    ears = md["mesh"].get("ears")
    if ears is not None and len(ears):
        V = md["mesh"]["V"][ears]
        s = V[V[:, 0] < 0] if sd == "R" else V[V[:, 0] > 0]
        if len(s):
            lobe_m = humanfit.project(md["cam"], s[np.argmin(s[:, 2])][None])[0]
    mex, mey = md["side"].frame() if md["side"].P is not None else (ex, ey)
    mv = ls.jaw_measures(Qm, mex, mey, mmpx, lobe_m, mouth_m, neck_m)
    mv["_line"] = Qm
    return pv, mv


def measure_reference(name: str, save: bool = True, photos=None) -> dict:
    """The target sheet: every checklist item measured on the model's reference pictures (human_refs.json), with its
    view, tolerance, confidence and source, or why it can't be measured. Saved as <model>/likeness_targets.json.
    Values are mm at the face's depth through each picture's fitted camera (its own scale), degrees or ratios."""
    from . import store
    refs = _refs(name)
    photos = photos or photo_sides(refs)
    vals = measure_sides([p["side"] for p in photos], [p["kind"] for p in photos], [p["mmpx"] for p in photos])
    items = {}
    from . import likeness_shape as ls
    traces = ls.load_points(name)
    kinds = [p["kind"] for p in photos]
    for it in checklist():
        rows = {}
        if it["measure"]["kind"] == "shape":
            vals[it["id"]] = {"-": "unmeasurable: shading is read against a model lit like the photo (compare / likeness)"}
        if it["measure"]["kind"] == "contour":
            vals[it["id"]] = {"-": "unmeasurable: a contour is read in the model's frame through its camera (compare / likeness); "
                                   "trace likeness_points 'profile' / 'nose' on a turned view"}
        if it["measure"]["kind"] == "jaw":
            vals[it["id"]] = {}
            for vi, ph in enumerate(photos):
                if not _allowed(it, ph["kind"], kinds)[0]:
                    continue
                tr = traces.get(ph["view"]["image"], {})
                got = []
                for sd in ("R", "L"):
                    Q = tr.get("lines", {}).get(f"jaw.{sd}")
                    if Q and len(Q) >= 6:
                        ex, ey = ph["side"].frame()
                        try:
                            mouth = ph["side"].pt([13, 14])
                        except Unmeasurable:
                            mouth = None
                        v = ls.jaw_measures(Q, ex, ey, ph["mmpx"], tr.get("points", {}).get(f"ear_lobe.{sd}"), mouth,
                                            tr.get("lines", {}).get(f"neck.{sd}")).get(it["measure"]["key"])
                        if v is not None:
                            got.append(v)
                vals[it["id"]][vi] = float(np.mean(got)) if got else "unmeasurable: needs a trace (likeness_points jaw.R / jaw.L)"
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


def compare(name: str, base: dict | None = None, photos=None, cameras=None, mesh=None, points_from: str | None = None) -> dict:
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
    from . import likeness_shape as ls
    for md in models:
        md["shape3d"] = md["mesh"].get("shape3d") or {}
    traces = ls.load_points(points_from or name)
    rows = []
    order = [s["name"] for s in stage_names()]
    for it in checklist():
        kind = it["measure"]["kind"]
        if kind in SPECIAL:
            got = (_shape_rows(it, photos, models, kinds) if kind == "shape" else _jaw_rows(it, photos, models, kinds, traces)
                   if kind == "jaw" else _contour_rows(it, photos, models, kinds, traces))
            if not got:
                got = [{"vi": "-", "why": " or ".join(it["views"]) + " view needed"}]
            for g in got:
                vi = g["vi"]
                tol = it["tol"] * (INFER_TOL if g.get("inferred") else 1.0)
                a = g.get("photo")
                b = 0.0 if kind == "shape" and a is not None else g.get("model")
                r = {"id": it["id"], "name": it["name"], "stage": it["stage"], "tier": order.index(it["stage"]) + 1,
                     "view": kinds[vi] if vi != "-" else "-", "vi": vi, "unit": it["unit"], "tol": tol,
                     "control": it["control"], "reliability": it.get("reliability", ""), "photo": a, "model": b,
                     "points": points_of(it["measure"]), "inferred": g.get("inferred", False), "kind": kind,
                     "model3d": g.get("model3d"), "regions": g.get("regions"), "traces": g.get("traces"),
                     "marks": g.get("marks"), "rank": float(it.get("rank", 1.0))}
                if kind == "shape" and r["view"] != "front" and isinstance(a, float):
                    r["score"] = -1.0
                    r["why"] = (f"shading contrast {a:+.1f}% shown in the panel, not scored: a turned / painted view's light "
                                "is not one light")
                elif isinstance(a, float) and isinstance(b, float) and np.isfinite(a) and np.isfinite(b):
                    r["miss"] = b - a
                    r["score"] = abs(b - a) / tol
                    r["source"] = "shading" if kind == "shape" else "trace/render contour"
                    if kind == "contour":
                        r["source"] = "contour"
                else:
                    r["score"] = -1.0
                    r["why"] = g.get("why", "")
                rows.append(r)
            continue
        for vi in pv[it["id"]]:
            a, b = pv[it["id"]][vi], mv[it["id"]].get(vi)
            inferred = vi != "-" and _allowed(it, kinds[vi], kinds)[1]
            tol = (it["tol"] or 0) * (INFER_TOL if inferred else 1.0) or it["tol"]
            r = {"id": it["id"], "name": it["name"], "stage": it["stage"], "tier": order.index(it["stage"]) + 1,
                 "view": kinds[vi] if vi != "-" else "-", "vi": vi, "unit": it["unit"], "tol": tol,
                 "control": it["control"], "reliability": it.get("reliability", ""), "photo": a, "model": b,
                 "points": points_of(it["measure"]), "inferred": inferred, "kind": it["measure"]["kind"]}
            cres = models[vi]["cam_res"] if vi != "-" else None
            if cres is not None:
                pr = [cres[i] for i in r["points"] if i < len(cres) and np.isfinite(cres[i])]
                if pr:
                    r["cam_mm"] = float(np.sqrt(np.mean(np.square(pr)))) * models[vi]["mmpx"]
            if isinstance(a, float) and isinstance(b, float) and it["tol"] and np.isfinite(a) and np.isfinite(b):
                r["miss"] = b - a
                r["score"] = abs(b - a) / tol
                if r.get("cam_mm") is not None and it["unit"] == "mm":  # a loose camera: its residual widens the tolerance
                    r["score"] = abs(b - a) / float(np.hypot(tol, 0.5 * r["cam_mm"]))
                r["source"] = f"{photos[vi]['side'].source}/{models[vi]['side'].source}"
                c, d = pl[it["id"]].get(vi), ml[it["id"]].get(vi)
                if isinstance(c, float) and isinstance(d, float) and np.isfinite(c) and np.isfinite(d):
                    r["miss_lm"] = d - c
                    r["agree"] = abs((d - c) - (b - a)) <= it["tol"]
            else:
                r["score"] = -1.0
                r["why"] = (a if isinstance(a, str) else b if isinstance(b, str) else "").split(": ", 1)[-1]
            rows.append(r)
    # a contour reading replaces the "inferred" detector reading of the same thing on that picture
    gone = {(i, r["vi"]) for r in rows if r.get("kind") == "contour" and r["score"] >= 0
            for i in _item(r["id"]).get("replaces", [])}
    rows = [r for r in rows if not ((r["id"], r["vi"]) in gone and r.get("kind") != "contour")]
    # "rank": identity features people read at once (the nose's base line) sort above their bare miss / tolerance
    rows.sort(key=lambda r: (-(r["score"] > 1.0), -r["score"] * r.get("rank", 1.0) if r["score"] > 1.0 else r["tier"], -r["score"]))
    cmp = {"rows": rows, "photos": photos, "models": models, "name": name, "points_from": points_from}
    cmp["pictures"] = [picture_notes(p, m) for p, m in zip(photos, models)]
    for r in rows:   # a turned picture whose yaw is in doubt: its depth items are judged wider
        if r.get("kind") == "contour" and r["score"] >= 0 and _item(r["id"])["measure"]["key"] in YAW_ITEMS:
            d = cmp["pictures"][r["vi"]].get("yaw_doubt")
            if d:
                r["tol"] = r["tol"] + YAW_MM * d
                r["score"] = abs(r["miss"]) / r["tol"]
                r["reliability"] = f"yaw in doubt by {d:.0f} deg (tolerance widened); " + r.get("reliability", "")
    rows.sort(key=lambda r: (-(r["score"] > 1.0), -r["score"] * r.get("rank", 1.0) if r["score"] > 1.0 else r["tier"], -r["score"]))
    for r in rows:   # items an expression on that picture biases
        if r["vi"] != "-":
            for nm, v in (cmp["pictures"][r["vi"]].get("expressions") or {}).items():
                if r["id"] in EXPR_BIAS.get(nm, []):
                    r["expression"] = f"{nm} {v:.2f}"
    return cmp


# ---- what a set of pictures can support -----------------------------------------------------------------------------

YAW_DOUBT = 6.0        # deg between the detector's head yaw and the fitted camera's: past it the picture isn't one projection
YAW_MM = 0.5           # mm of tolerance added per degree of that doubt on a turned view's depth items (1 deg ~ 1 mm of gap)
YAW_ITEMS = ("nose_gap", "nose_tip", "cheek_line", "chin_projection", "brow_ridge")
EXPR = {"smile": (("mouthSmileLeft", "mouthSmileRight"), 0.3), "mouth open": (("jawOpen",), 0.15),
        "squint": (("eyeBlinkLeft", "eyeBlinkRight", "eyeSquintLeft", "eyeSquintRight"), 0.45),
        "brows raised": (("browInnerUp", "browOuterUpLeft", "browOuterUpRight"), 0.4),
        "frown": (("browDownLeft", "browDownRight"), 0.45)}
# THE RULE: an expression read on a reference is not the person's shape. The items it moves are fitted through the
# model's POSE (base.head.pose: an expression), not its identity; the neutral head keeps typical values.
EXPR_BIAS = {"squint": ["eye_opening", "eye_aspect", "upper_lid_show", "brow_eye"],
             "frown": ["brow_eye", "brow_tilt", "brow_arch"],
             "brows raised": ["brow_eye", "brow_arch", "brow_tilt", "eye_opening", "upper_third"],
             "smile": ["mouth_corner_tilt", "mouth_width", "nasolabial_fold", "upper_lip", "eye_opening", "width_mouth"],
             "mouth open": ["lower_third", "lower_over_middle", "face_height", "chin_height", "upper_lip", "lower_lip",
                            "lip_ratio", "mouth_line"]}
# item -> the pose lever that takes it when an expression biases it (path, step, range, default)
EXPR_LEVERS = {"eye_opening": ("pose.lid_upper", 0.001, (-0.003, 0.004), 0.0),
               "brow_eye": ("pose.brow_inner", -0.001, (-0.004, 0.003), 0.0),
               "mouth_corner_tilt": ("pose.smile", 0.001, (-0.004, 0.004), 0.0)}


def expression_bias(pictures: list, view: str | None = "front") -> dict:
    """{item id: "squint 0.70"}: the items an expression read on the references biases (in pictures of that view)."""
    out = {}
    for pn in pictures:
        if view and pn.get("view") != view:
            continue
        for nm, v in (pn.get("expressions") or {}).items():
            for iid in EXPR_BIAS.get(nm, []):
                out.setdefault(iid, f"{nm} {v:.2f}")
    return out


def lens_mm(cam: dict) -> float:
    """35 mm-equivalent focal length of a fitted camera (full-frame diagonal over the picture's)."""
    w, h = cam["size"]
    return float(cam["f"] * 43.27 / np.hypot(w, h))


def _skinlike(img, box_px, ref_rgb) -> float:
    """Share of a picture region whose colour is close to the face's skin (chroma and brightness)."""
    a = np.asarray(img.crop(tuple(int(round(v)) for v in box_px)).convert("RGB"), float).reshape(-1, 3)
    if len(a) == 0:
        return float("nan")
    ch = a / np.maximum(a.sum(1, keepdims=True), 1)
    cr = np.asarray(ref_rgb, float) / max(sum(ref_rgb), 1)
    lum = a.mean(1) / max(np.mean(ref_rgb), 1)
    return float(((np.linalg.norm(ch - cr, axis=1) < 0.035) & (lum > 0.45) & (lum < 1.7)).mean())


def picture_notes(ph: dict, md: dict | None = None) -> dict:
    """What a reference picture is good and bad for: view (and the detector's head yaw), lens, expression, light,
    ears and hairline showing. Each a short phrase; "problems" lists the ones that cost checklist items."""
    out = {"image": Path(ph["view"]["image"]).name, "view": ph["kind"], "problems": []}
    info = ph.get("info") or {}
    out["head_yaw"] = head_yaw(info.get("M"))
    cam = md["cam"] if md else ph["cam"]
    cy = abs(float(cam.get("yaw", 0.0)))
    if out["head_yaw"] is not None and ph["kind"] != "front" and abs(abs(out["head_yaw"]) - cy) > YAW_DOUBT:
        out["yaw_doubt"] = abs(abs(out["head_yaw"]) - cy)
        out["problems"].append(f"NOT ONE PROJECTION: the detector reads the head turned {abs(out['head_yaw']):.0f} deg, the fitted camera "
                               f"{cy:.0f} (a painting / generated picture): distances and widths are the FRONT picture's; this one gives "
                               "character (the contour's shape: bridge, tip, chin, jaw corner), its depth items' tolerances are widened")
    f = lens_mm(cam)
    out["lens_mm"] = round(f, 0)
    if f < 60:
        out["problems"].append(f"short lens (~{f:.0f} mm equivalent): perspective swells the nose, shrinks the ears")
    bs = info.get("bs") or {}
    for nm, (keys, lim) in EXPR.items():
        v = max((bs.get(k, 0.0) for k in keys), default=0.0)
        if v > lim:
            out.setdefault("expressions", {})[nm] = float(v)
            out["problems"].append(f"{nm} ({v:.2f}): an expression, not shape; it biases "
                                   + ", ".join(EXPR_BIAS[nm]) + " (fit those through the pose)")
    sh = md.get("shade") if md else None
    if sh:
        out["light_hard"] = round(sh["hard"], 2)
        out["light_fit"] = round(sh["fit_share"], 3)
        if sh["hard"] > 0.75:
            out["problems"].append(f"hard light ({sh['hard']:.2f}): shading reads shape and shadow edges together")
        if sh["fit_share"] > 0.15:
            out["problems"].append(f"one light explains the shading badly ({100 * sh['fit_share']:.0f}% rms): painted or "
                                   "mixed light, shape items unreliable")
    s = ph["side"]
    if s.P is not None and ph.get("mmpx"):
        mmpx = ph["mmpx"]
        try:
            ref = np.asarray(ph["img"].crop(tuple(int(v) for v in np.r_[s.pt(50) - 3, s.pt(50) + 3])).convert("RGB"),
                             float).reshape(-1, 3).mean(0)
            ex, ey = s.frame()
            ears = []
            for i, sgn in ((234, -1), (454, 1)):
                c = s.pt(i) + sgn * ex * 14 / mmpx
                r = 7 / mmpx
                ears.append(_skinlike(ph["img"], (c[0] - r, c[1] - r, c[0] + r, c[1] + r), ref))
            near = _near_sign(s)
            seen = [e for e, sg in zip(ears, (-1, 1)) if sg in near]
            out["ears_skin"] = [round(e, 2) for e in ears]
            if seen and min(seen) < 0.25:
                out["problems"].append("ears hidden (hair, collar or out of frame): ear items judge-only")
            top = s.pt([105, 334]) - ey * 12 / mmpx
            hb = (top[0] - 25 / mmpx, top[1] - 22 / mmpx, top[0] + 25 / mmpx, top[1])
            out["forehead_skin"] = round(_skinlike(ph["img"], hb, ref), 2)
            if out["forehead_skin"] < 0.5:
                out["problems"].append("hair over the forehead / hairline: forehead height unreadable")
        except (Unmeasurable, ValueError):
            pass
    elif s.P is None:
        out["problems"].append("no face found by the detector: only the stored landmarks are read")
    return out


def coverage_text(cmp: dict) -> str:
    """One glance: which checklist items these pictures support, which only by eye or inferred, which not, and why."""
    by = {}
    for r in cmp["rows"]:
        by.setdefault(r["id"], []).append(r)
    meas, inf, judge, none = [], [], [], {}
    for iid, rs in by.items():
        ok = [r for r in rs if r["score"] >= 0]
        if ok:
            (inf if all(r.get("inferred") for r in ok) else meas).append(iid)
        elif any(r.get("kind") == "judge" and r["vi"] != "-" for r in rs):
            judge.append(rs[0]["name"])
        else:
            why = (rs[0].get("why") or "").split(":")[0].split(";")[0][:60]
            none.setdefault(why or "?", []).append(rs[0]["name"])
    lines = [f"coverage: {len(meas)} items measured, {len(inf)} inferred from a weaker view, {len(judge)} judge by eye, "
             f"{sum(len(v) for v in none.values())} not supported by these pictures"]
    if inf:
        lines.append("  inferred (three-quarter for profile, tolerance x1.5): " + ", ".join(by[i][0]["name"] for i in inf))
    for why, names in none.items():
        lines.append(f"  not supported ({why}): " + ", ".join(names))
    if judge:
        lines.append("  judge by eye (panels): " + ", ".join(judge))
    kinds = [p["kind"] for p in cmp["photos"]]
    if "profile" not in kinds:
        need = sorted({r["name"] for r in cmp["rows"] if "profile" in _item(r["id"])["views"]})
        lines.append("  a true profile would measure (now inferred or judged): " + ", ".join(need))
    for pn in cmp.get("pictures", []):
        lines.append(f"  picture {pn['image']} ({pn['view']}, head yaw {pn['head_yaw'] if pn['head_yaw'] is None else round(pn['head_yaw'])}, "
                     f"lens ~{pn['lens_mm']:.0f} mm" + (f", light hardness {pn['light_hard']}" if "light_hard" in pn else "") + "): "
                     + ("; ".join(pn["problems"]) or "no problems found"))
    return "\n".join(lines)


def _fmt(v, unit):
    if not isinstance(v, float):
        return "-"
    return f"{v:.3f}" if unit == "" else f"{v:.1f}"


def table_text(cmp: dict, top: int | None = None) -> str:
    rows = cmp["rows"]
    meas = [r for r in rows if r["score"] >= 0]
    over = [r for r in meas if r["score"] > 1.0]
    res = ", ".join(f"{p['kind']} {m['mmpx']:.2f} mm/px ({p['side'].source} / {m['side'].source}"
                    + (", camera refitted" if m.get("cam_res") is not None else "") + ")"
                    for p, m in zip(cmp["photos"], cmp["models"]))
    lines = [coverage_text(cmp), "",
             f"likeness: {len(meas)} item-views measured, {len(over)} beyond tolerance (photo vs model through the same "
             f"camera; miss = model - photo). Pictures: {res}.",
             "  lm miss = the same measure on the landmarks alone; '!' = the readings differ by more than the tolerance (the "
             "miss depends on the definition: look at the panel). '~' = inferred from a weaker view (tolerance x1.5). cam = "
             "the refitted camera's residual at the item's points (mm; includes shape misses; widens the tolerance by half). "
             "Shape rows (%): the photo's shading against the model lit like the photo, region vs reference region; + miss "
             "= the photo is darker there than the model's shape predicts (deeper hollow, sharper turn); 3D = the model's "
             "own number in mm.",
             f"{'#':>2} {'item':40} {'view':14} {'photo':>8} {'model':>8} {'miss':>8} {'tol':>6} {'xtol':>5} {'lm miss':>8} {'cam':>5} {'3D':>6}  stage: control"]
    for i, r in enumerate(meas[:top] if top else meas, 1):
        dp = 3 if r["unit"] == "" else 1
        view = r["view"] + ("~" if r.get("inferred") else "")
        lines.append(f"{i:>2} {r['name'][:40]:40} {view:14} {_fmt(r['photo'], r['unit']):>8} {_fmt(r['model'], r['unit']):>8} "
                     f"{r['miss']:+8.{dp}f} {r['tol']:>6.3g} {r['score']:5.1f} "
                     + (f"{r['miss_lm']:+7.{dp}f}{' ' if r['agree'] else '!'}" if "miss_lm" in r else f"{'-':>8}")
                     + (f" {r['cam_mm']:5.1f}" if r.get("cam_mm") is not None else f" {'-':>5}")
                     + (f" {r['model3d']:6.1f}" if isinstance(r.get("model3d"), float) else f" {'-':>6}")
                     + f"  {r['stage']}: {r['control']}"
                     + ("" if r.get("source") == "detector/detector" else f"  [{r.get('source')}]")
                     + (f"  EXPRESSION ({r['expression']}): fit through the pose, not the identity" if r.get("expression") else "")
                     + (f"  CAUTION {r['reliability']}" if r["reliability"] and r["score"] > 1 else ""))
    rest = [r for r in rows if r["score"] < 0]
    if rest:
        lines.append("not measured (judge in the focus panels, or what is missing):")
        for r in rest:
            lines.append(f"   {r['name']} [{r['view']}{'~' if r.get('inferred') else ''}]: {r.get('why') or 'judge by eye'}"
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
    b0 = ph["box"]
    k = md["k"]
    circles, polys = [], []   # (centre px, r px, colour), (points, colour) in picture pixels
    if row.get("kind") == "shape":
        pp, mp_ = {}, {}
        for reg, ref, rr, rf in row.get("regions") or []:
            circles += [(reg / k + b0[:2], rr / k, (255, 220, 60)), (ref / k + b0[:2], rf / k, (120, 230, 120))]
    if row.get("kind") == "contour":
        for pts_, col in zip(row.get("marks") or [], (PHOTO_COL, MODEL_COL)):
            for g in pts_:
                circles.append((np.asarray(g), 2.0 / max(md["mmpx"], 1e-6), col))
    if row.get("kind") in ("jaw", "contour"):
        pp, mp_ = {}, {}
        for Q, Qm, gp, gm in row.get("traces") or []:
            polys.append((Q, PHOTO_COL))
            if Qm is not None:
                polys.append((Qm, MODEL_COL))
            for g, col in ((gp, PHOTO_COL), (gm, MODEL_COL)):
                if g is not None:
                    circles.append((np.asarray(g), 4.0 / max(md["mmpx"], 1e-6), col))
        from . import likeness_shape as ls
        tr = ls.load_points(cmp.get("points_from") or cmp.get("name", "")).get(ph["view"]["image"], {}) if row.get("kind") == "jaw" else {}
        for nm_, uv in tr.get("points", {}).items():
            circles.append((np.asarray(uv, float), 2.5 / max(md["mmpx"], 1e-6), (255, 140, 255)))
        for nm_, ln in tr.get("lines", {}).items():
            if not nm_.startswith("jaw"):
                polys.append((np.asarray(ln, float), (255, 140, 255)))
    allp = list(pp.values()) + list(mp_.values()) + [p for s, _ in segs for p in s]
    allp += [c_ + d_ for c_, r_, _ in circles for d_ in ([r_, r_], [-r_, -r_])] + [q for Q, _ in polys for q in np.asarray(Q)]
    allp = np.array(allp) if allp else np.array([[(ph["box"][0] + ph["box"][2]) / 2, (ph["box"][1] + ph["box"][3]) / 2]])
    lo, hi = allp.min(0), allp.max(0)
    side = max((hi - lo).max() * 1.4, 30.0 / max(md["mmpx"], 1e-6))   # at least 30 mm across
    side = min(side, b0[2] - b0[0], b0[3] - b0[1])
    c = (lo + hi) / 2
    c = np.clip(c, [b0[0] + side / 2, b0[1] + side / 2], [b0[2] - side / 2, b0[3] - side / 2])   # inside the render
    box = (c[0] - side / 2, c[1] - side / 2, c[0] + side / 2, c[1] + side / 2)
    s = px / side

    def crop(img, origin, scale):
        return img.crop(tuple(int(round(v)) for v in ((box[0] - origin[0]) * scale, (box[1] - origin[1]) * scale,
                                                       (box[2] - origin[0]) * scale, (box[3] - origin[1]) * scale))).resize((px, px), Image.LANCZOS)
    a = crop(ph["img"], (0, 0), 1.0)
    lit = row.get("kind") in ("shape", "jaw", "judge", "contour") and md.get("img_lit") is not None
    b = crop(md["img_lit"] if lit else md["img"], (b0[0], b0[1]), k)
    for im in (a, b):
        d = ImageDraw.Draw(im)
        for cc, rr, col in circles:
            q = (cc - box[:2]) * s
            d.ellipse((q[0] - rr * s, q[1] - rr * s, q[0] + rr * s, q[1] + rr * s), outline=col, width=2)
        for Q, col in polys:
            d.line([tuple((q - box[:2]) * s) for q in np.asarray(Q, float)], fill=col, width=2)
        for (p, q), col in segs:
            d.line([tuple((p - box[:2]) * s), tuple((q - box[:2]) * s)], fill=col, width=2)
        _draw_feature(d, {i: (p - box[:2]) * s for i, p in pp.items()}, pp, PHOTO_COL)
        _draw_feature(d, {i: (p - box[:2]) * s for i, p in mp_.items()}, mp_, MODEL_COL, r=2)
    out = Image.new("RGB", (2 * px + 6, px + 34), (24, 24, 28))
    out.paste(a, (0, 34))
    out.paste(b, (px + 6, 34))
    d = ImageDraw.Draw(out)
    miss = f"{row['miss']:+.{3 if row['unit'] == '' else 1}f}{row['unit']} (tol {row['tol']:g})" if row["score"] >= 0 else "judge"
    tag = (" INFERRED" if row.get("inferred") else "") + (" | model lit like the photo" if lit else "")
    d.text((4, 2), f"{row['name'][:46]} [{row['view']}{tag}]", fill=(240, 240, 240))
    extra = f"  3D {row['model3d']:.1f} mm" if isinstance(row.get("model3d"), float) else ""
    if row.get("kind") == "shape":
        txt = f"shading contrast photo {_fmt(row['photo'], 'x')}% vs model 0  (yellow region - green ref){extra}"
    else:
        txt = f"photo {_fmt(row['photo'], row['unit'])} | model {_fmt(row['model'], row['unit'])}  miss {miss}{extra}"
    d.text((4, 17), txt, fill=(255, 210, 120))
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
    # stage 0, the character read: its diff (reference vs the model's blind reads) and what the read implies lead the
    # report, above the millimetres
    from . import likeness_read as lr
    lead = []
    try:   # the six-view sheet: what a person judges too (reference cameras + the views no reference shows)
        views = str(Path(out).with_name(Path(out).stem.replace("_focus", "") + "_views.png"))
        lr.render_views(name, views, base=base)
        lead.append(f"six-view sheet (judge this first, and last): {views}")
    except Exception as e:  # noqa: BLE001
        lead.append(f"(six-view sheet not rendered: {e})")
    reads = lr.load(name)["reads"]
    if reads.get("reference"):
        for tag in reads:
            if tag != "reference":
                lead.append(lr.diff(name, tag))
        pr = lr.apply_prior(cmp, reads["reference"])
        if pr:
            lead.append("the read as a prior:\n" + "\n".join(pr))
    else:
        lead.append("no character read stored (character_read): the report is millimetres only")
    return "\n\n".join(lead + [table_text(cmp)]), out, cmp


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


def stage_wants(cmp: dict, stage: str, skip=()) -> tuple:
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
        if r["score"] <= 1.0 or r["id"] in skip:
            continue
        if it.get("solve"):
            want[it["solve"]] = want.get(it["solve"], 0.0) - r["miss"]
        elif r["score"] > 0:
            gaps.append(f"{it['name']} ({r['miss']:+.2f} {it['unit']}): {it['control']}")
    want = {m: f"{d:+.2f}" for m, d in want.items() if abs(d) > humanfit.TOL_MM}
    pins = {m: "+0" for m in pins if m not in want}
    return want, pins, gaps


LEVERS = {
    # item id: (path in base.head, step, (lo, hi), default) -- 1-D secant fits on the item's own signed miss
    "cheek_hollow": ("shape.hollow", 0.002, (0.0, 0.008), 0.0),
    "corner_temple": ("shape.planes", 0.3, (2.0, 3.2), 2.0),
    "corner_cheekbone": ("shape.planes", 0.3, (2.0, 3.2), 2.0),
    "corner_jaw": ("shape.jaw_angle", 0.0015, (0.0, 0.005), 0.0),
    "brow_ridge": ("features.brow_ridge", 0.5, (-1.5, 1.5), 0.0),
    "under_eye": ("shape.under_eye", 0.3, (0.0, 1.0), 0.0),
    # onemesh2's jaw control (base.head.shape.jawline: the mandible as an L), driven by the traced jaw
    "jaw_gonion_lobe": ("shape.jawline.below_lobe", 0.008, (0.02, 0.07), 0.045),
    "jaw_gonion_mouth": ("shape.jawline.below_lobe", 0.008, (0.02, 0.07), 0.045),
    "jaw_ramus": ("shape.jawline.forward", 0.006, (-0.01, 0.02), 0.004),
    "jaw_neck_step": ("shape.jawline.tuck", 0.003, (0.0, 0.008), 0.0),
    "canthal_tilt": ("nudge:eye_outer.L:z", 0.001, (-0.004, 0.004), 0.0),
    "nose_length": ("nudge:nose_tip:z", 0.002, (-0.006, 0.006), 0.0),
    "nose_projection": ("nudge:nose_tip:y", -0.002, (-0.006, 0.006), 0.0),
    "mouth_corner_tilt": ("pose.smile", 0.001, (-0.004, 0.004), 0.0),
}
LEVERS["prof_brow_ridge"] = ("features.brow_ridge", 0.4, (-1.5, 1.5), 0.0)
LEVERS["prof_nose_base"] = ("shape.nose_tip.up", 5.0, (-10.0, 25.0), 0.0)   # the tip turned up / down (deg)
LEVERS["prof_tip_height"] = ("shape.nose_tip.up", 5.0, (-10.0, 25.0), 0.0)
# onemesh2's controls (581dc3e): the tip blunted, the chin's own form
LEVERS["prof_tip_radius"] = ("shape.nose_tip.round", 0.4, (0.0, 1.5), 0.0)
LEVERS["prof_chin"] = ("shape.chin.project", 0.002, (-0.004, 0.010), 0.0)
LEVERS["width_chin"] = ("shape.chin.width", 0.002, (-0.006, 0.010), 0.0)
LEVERS["prof_cheek_line"] = ("shape.hollow", 0.002, (0.0, 0.008), 0.0)
# (facesliders, 2026-10-09) the eye items on the one mesh's face sliders (faceslide.py: morph targets in [-1, 1]):
# the corner tilt turns the fissure on the ball (it was a landmark nudge), the platform's show is the fold's edge,
# the under-eye's depth the tear trough, the brow ridge the skin over the supraorbital rim (features.brow_ridge moved
# the forehead's slope instead: likeloop). Crease height / depth are read by faceslide.read_eyes (the detector has no
# crease point) and solved by faceslide.fit.
LEVERS["canthal_tilt"] = ("sliders.canthal_tilt", 0.25, (-1.0, 1.0), 0.0)
LEVERS["upper_lid_show"] = ("sliders.eye_platform", 0.25, (-1.0, 1.0), 0.0)
LEVERS["under_eye"] = ("sliders.eye_tear_trough", 0.25, (-1.0, 1.0), 0.0)
LEVERS["brow_ridge"] = ("sliders.brow_ridge", 0.25, (-1.0, 1.0), 0.0)
LEVERS["prof_brow_ridge"] = ("sliders.brow_ridge", 0.25, (-1.0, 1.0), 0.0)
# the mouth's: the bow's depth, the lips' eversion (volume forward: what the profile and the E-line see)
LEVERS["cupid_bow"] = ("sliders.lip_bow", 0.25, (-1.0, 1.0), 0.0)
LEVERS["lip_projection"] = ("sliders.lip_upper_roll", 0.25, (-1.0, 1.0), 0.0)
LEVERS["prof_upper_lip"] = ("sliders.lip_upper_roll", 0.25, (-1.0, 1.0), 0.0)
LEVERS["prof_lower_lip"] = ("sliders.lip_lower_roll", 0.25, (-1.0, 1.0), 0.0)
# the nose's dorsal widths (shading items: the side wall off the dorsal line against the dorsum)
LEVERS["radix_width"] = ("sliders.nose_radix_width", 0.25, (-1.0, 1.0), 0.0)
LEVERS["dorsum_width"] = ("sliders.nose_dorsum_width", 0.25, (-1.0, 1.0), 0.0)
LEVER_VIEWS = {"shape": ("front",)}   # shading is scored on the front photo only (a painting's light isn't one light)


BARE = {"nose_tip": "up"}   # controls that may be a bare number: which key of their dict form it is


def lever_value(base: dict, path: str, default: float) -> float:
    if path.startswith("nudge:"):
        return 0.0
    d = base.get("head", {})
    keys = path.split(".")
    for k in keys[:-1]:
        d = d.get(k) or {}
        if isinstance(d, (int, float)) and k in BARE:   # shape.nose_tip = 12 means {"up": 12}
            d = {BARE[k]: d}
        if not isinstance(d, dict):   # (a control given as a bare number: shape.hollow = 0.005)
            return default
    v = d.get(keys[-1], default) if isinstance(d, dict) else default
    return float(v) if isinstance(v, (int, float)) else default


def with_lever(base: dict, path: str, x: float, force: bool = False) -> tuple:
    """(base, refused?) with the lever set to x (a nudge: the landmark moved x m along its axis from `base`)."""
    import copy as _copy
    from . import humanfit
    if path.startswith("nudge:"):
        _, lm, ax = path.split(":")
        mv = [0.0, 0.0, 0.0]
        mv["xyz".index(ax)] = float(x)
        if abs(x) < 1e-6:
            return base, False
        nb, rep = humanfit.nudge(base, lm, move=mv, force=force)
        return nb, bool(rep.get("refused"))
    out = _copy.deepcopy(base)
    d = out.setdefault("head", {})
    keys = path.split(".")
    for k in keys[:-1]:
        if not isinstance(d.get(k), dict):
            d[k] = {BARE[k]: d[k]} if isinstance(d.get(k), (int, float)) and k in BARE else {}
        d = d[k]
    d[keys[-1]] = round(float(x), 5)
    return out, False


def _signed(cmp: dict, ids, views=None) -> float | None:
    v = [r["miss"] for r in cmp["rows"] if r["id"] in ids and r["score"] >= 0 and (views is None or r["view"] in views)]
    return float(np.mean(v)) if v else None


def _undone(start: dict, cur: dict, k: int) -> list:
    """Earlier stages' checklist items (re-measured) that got worse: > 0.5 x tol and past the tolerance."""
    order = [s["name"] for s in stage_names()]
    bmap = {(r["id"], r["vi"]): r for r in start["rows"]}
    out = []
    for r in cur["rows"]:
        b = bmap.get((r["id"], r["vi"]))
        if b is None or order.index(r["stage"]) >= k:
            continue
        # pins are the items read steadily: detector distances / angles in a front view. The shading and traced-jaw
        # readers move by more than a tolerance when anything nearby changes, and a turned view's camera is refitted
        # per model: holding those vetoed every later stage (first run: eyes, mouth and chin all refused).
        if r.get("kind") in SPECIAL or r["view"] != "front":
            continue
        if r["score"] >= 0 and b["score"] >= 0 and r["score"] > max(b["score"], 1.0) + 0.5:
            out.append((b, r))
    return out


def _lever_fit(name, base, photos, start, cmp0, k, ids, lever, force, log) -> tuple:
    """1-D secant on the lever for the items' signed miss, from `base` (measured: cmp0); every candidate
    integrity-guarded and checked against the earlier stages' items (re-measured against `start`). (base, compare,
    note)."""
    from . import humanfit
    path, step, (lo, hi), dflt = lever
    kind = _item(ids[0])["measure"]["kind"]
    views = LEVER_VIEWS.get(kind)
    x0 = lever_value(base, path, dflt)
    st0 = humanfit.state(base)
    f0 = _signed(cmp0, ids, views)
    if f0 is None:
        return base, cmp0, f"{path}: not measured"
    tol = _item(ids[0])["tol"]
    if abs(f0) <= tol:
        return base, cmp0, f"{path}: already within tolerance ({f0:+.2f})"
    tried = [(abs(f0), x0, base, cmp0, f0)]
    fresh = path.startswith("shape.jawline") and not isinstance((base.get("head", {}).get("shape") or {}).get("jawline"), dict)

    def ev(x):
        x = float(np.clip(x, lo, hi))
        nb, refused = with_lever(base, path, x, force)
        if refused:
            return None
        it = humanfit.integrity(nb, None, st0)
        if not it["ok"] and not force and humanfit._newly_broken(base, it):
            log.append(f"    {path} = {x:.4g}: BROKEN ({'; '.join(it['broken'])[:120]})")
            return None
        c = compare(name, nb, photos=photos)
        f = _signed(c, ids, views)
        und = _undone(start, c, k)
        log.append(f"    {path} = {x:.4g}: miss {f if f is None else round(f, 2)}" + (f", undoes {[u[1]['id'] for u in und]}" if und else ""))
        if f is None:
            return None
        if not und:
            tried.append((abs(f), x, nb, c, f))
        return f       # (a vetoed try still tells the secant which way the lever moves the item)
    if fresh:   # the control at its default first: that is the lever's real starting point
        fd = ev(x0)
        if fd is None:
            return base, cmp0, f"{path}: its default was refused"
        f0 = fd
    x1 = x0 + step if x0 + step <= hi else x0 - step
    f1 = ev(x1)
    if f1 is not None and abs(f1 - f0) > 0.02 * max(abs(f0), 1e-9):
        xs = float(np.clip(x1 - f1 * (x1 - x0) / (f1 - f0), lo, hi))
        if abs(xs - x1) > 1e-9 and abs(xs - x0) > 1e-9:
            f2 = ev(xs)
            if f2 is not None and abs(f2) > tol and len(tried) < 2:   # still vetoed or off: one try half way
                ev(x0 + 0.5 * (xs - x0))
    elif f1 is not None:
        log.append(f"    {path}: no effect on the item (lever doesn't reach it)")
    best = min(tried, key=lambda t: t[0])
    return best[2], best[3], f"{path}: {x0:.4g} -> {best[1]:.4g}, miss {f0:+.2f} -> {best[4]:+.2f} (tol {tol:g})"


def fit_stage(name: str, stage: str, base: dict | None = None, force: bool = False, save: bool = False,
              panels: str | None = None) -> dict:
    """One stage of the likeness fit: the stage's controls run on the model, the checklist measured before and after.
    Controls: humanfit.solve on the stage's solver measures (front view), fit_outline (widths), fit_hood (eyes), and
    1-D lever fits (LEVERS: shape.hollow / planes / jaw_angle / under_eye, features.brow_ridge, pose.smile, nudges of
    eye corners and nose tip) on the items' own misses. Every result is integrity-guarded (refused if it breaks the
    mesh) and PINNED to the earlier stages' checklist items, re-measured: a step that makes one worse (> 0.5 x tol, past
    tol) is not taken (a solve is retried with half its asks first). save=True stores the result (and the cameras)."""
    from . import humanfit, store
    sp = store.load(name)
    base = base or sp["base"]
    refs = _refs(name)
    st = _stage(stage)
    photos = _photos(refs)
    start = compare(name, base, photos=photos)
    start["_base"] = base
    order = [s["name"] for s in stage_names()]
    k = order.index(stage)
    rep = {"stage": stage, "control": st["control"], "steps": [], "log": []}
    cur, cur_cmp = base, start
    biased = expression_bias(start["pictures"])
    rep["expression"] = {i: v for i, v in biased.items() if _item(i)["stage"] == stage}
    want, pins, gaps = stage_wants(start, stage, skip=biased)
    rep["want"], rep["pins"] = want, pins
    if stage == "widths":
        nb, r = humanfit.fit_outline(cur, refs["views"], [m["cam"] for m in start["models"]], force=force)
        c = compare(name, nb, photos=photos)
        und = _undone(start, c, k)
        rep["steps"].append(("fit_outline", r))
        if und and not force:
            rep["log"].append(f"  fit_outline not taken: undoes {[u[1]['id'] for u in und]}")
        elif not r.get("refused"):
            cur, cur_cmp = nb, c
    if want:
        for frac in (1.0, 0.5):
            ask = {m: f"{float(v) * frac:+.2f}" for m, v in want.items()}
            nb, r = humanfit.solve(cur, {**pins, **ask}, force=force)
            if r.get("refused"):
                rep["steps"].append((f"solve {ask}", r))
                break
            c = compare(name, nb, photos=photos)
            und = _undone(start, c, k)
            rep["steps"].append((f"solve {ask}" + (f" (pinned {sorted(pins)})" if pins else ""), r))
            if not und or force:
                cur, cur_cmp = nb, c
                break
            rep["log"].append(f"  solve x{frac}: undoes {[u[1]['id'] for u in und]}" + ("; retry at half" if frac == 1.0 else "; not taken"))
    if stage == "eyes" and "eye_opening" not in biased:
        nb, r = humanfit.fit_hood(cur, _views_with(refs, list(humanfit.HOOD_LIDS)), [m["cam"] for m in cur_cmp["models"]], force=force)
        c = compare(name, nb, photos=photos)
        if not _undone(start, c, k) and not r.get("refused"):
            cur, cur_cmp = nb, c
        rep["steps"].append(("fit_hood", r))
    part = {"nose": "nose", "chin_jaw": "chin", "structure": "cheek"}.get(stage)
    if part and _profile_score(cur_cmp, part) is not None:
        cur, cur_cmp, plog = fit_profile(name, cur, parts=(part,), force=force, start=start, k=k, photos=photos)
        rep["log"] += plog
        rep["steps"].append((f"profile contour ({part})", {}))
    done = set()
    for it in checklist():
        lv_of = lambda i: EXPR_LEVERS[i] if (i in biased and i in EXPR_LEVERS) else LEVERS.get(i)  # noqa: E731
        if it["stage"] != stage or lv_of(it["id"]) is None or it["id"] in done:
            continue
        lever = lv_of(it["id"])
        ids = [i for i in list(LEVERS) + list(EXPR_LEVERS) if lv_of(i) and lv_of(i)[0] == lever[0] and _item(i)["stage"] == stage]
        ids = list(dict.fromkeys(ids))
        # a contour reading (mm, geometry) drives the lever alone where there is one: mixed with the shading's % the
        # mean miss means nothing
        cids = [i for i in ids if _item(i)["measure"]["kind"] == "contour"
                and any(r["id"] == i and r["score"] >= 0 for r in cur_cmp["rows"])]
        ids = cids or [i for i in ids if _item(i)["measure"]["kind"] != "contour"]
        if not ids:
            continue
        done.update(ids)
        rep["log"].append(f"  lever {lever[0]} for {ids}:")
        cur_cmp["_base"] = cur
        cur, cur_cmp, note = _lever_fit(name, cur, photos, start, cur_cmp, k, ids, lever, force, rep["log"])
        rep["steps"].append((f"lever {note}", {}))
    gaps = []
    for r in cur_cmp["rows"]:
        it = _item(r["id"])
        if it["stage"] == stage and r["score"] > 1.0 and not it.get("solve") and r["id"] not in LEVERS \
                and not any(w in it["control"] for w in ("fit_outline", "fit_hood")):
            gaps.append(f"{it['name']} [{r['view']}] ({r['miss']:+.2f} {it['unit']}): {it['control']}")
    rep["gaps"] = gaps
    if not rep["steps"]:
        rep["gap"] = f"nothing wired for {stage}" + (": judge the panels" if gaps else "")
    after = cur_cmp
    rep["refused"] = [f"{n}: {r['refused']}" for n, r in rep["steps"] if isinstance(r, dict) and r.get("refused")]
    rep["integrity"] = humanfit.verdict(humanfit.integrity(cur, None, humanfit.state(base))) if cur is not base else "unchanged"
    bmap = {(r["id"], r["vi"]): r for r in start["rows"]}
    rep["rows"] = [(bmap[(r["id"], r["vi"])], r) for r in after["rows"]
                   if (r["id"], r["vi"]) in bmap and order.index(r["stage"]) == k]
    rep["undone"] = _undone(start, after, k)
    rep["text"] = stage_text(rep)
    rep["base"], rep["after"] = cur, after
    if panels:
        focus_sheet(after, panels, top=14, rows=[r for _, r in rep["rows"]])
        rep["panels"] = panels
    if save and cur is not base:
        v = store.save(name, {**sp, "base": cur}, f"likeness stage {stage}")
        refs2 = {**refs, "cameras": [m["cam"] for m in after["models"]]}
        (store.HOME / name / "human_refs.json").write_text(json.dumps(refs2, indent=1))
        rep["saved"] = v
        rep["text"] += f"\nsaved {name} v{v}"
    return rep


PROFILE_PARTS = {   # part -> (region group(s), contour, heights it reads (levels, mm either side), landmarks held)
    "nose": ("nose_region", "nose", None, None),
    "chin": (["chin_region", "lower_lip_region"], "outer", ("sto", 6.0, "chin", 9.0),
             [i for i in range(17, 68) if i not in (55, 56, 57, 58, 59, 65, 66, 67)]),
    # the cheek's fullness at the mouth's height (the far cheek's line in a turned view), the front outline held
    "cheek": (["left_cheek_region", "right_cheek_region"], "outer", ("sn", 2.0, "sto", 10.0), list(range(17, 68))),
}
PROFILE_ITEMS = {"cheek": ["prof_cheek_line"], "nose": ["prof_nose_tip", "prof_nose_gap", "prof_nose_length", "prof_bridge_bow"],
                 "chin": ["prof_chin", "prof_chin_height", "prof_mentolabial"]}
PROFILE_ROUNDS = 5
PROFILE_DONE = 1.5    # mm rms of the contour's miss at its vertices: done


PROFILE_FRONT = {"nose": list(range(27, 36)), "chin": [7, 8, 9, 56, 57, 58]}


PROFILE_HOLD_N = 60     # region vertices held in the front picture's plane
PROFILE_HOLD_W = 3      # ... each counted this many times against a contour vertex
PROFILE_GAIN = 0.7      # share of the contour's miss asked a round (to the contour, not past it)
PROFILE_SIGMA = 1.6     # a round that takes the region's components past this is not taken (plausibility)


def _front_holds(cmp, part) -> list:
    """The part's skin held where a FRONT picture has it (fit_region targets at their own projection): a turned view's
    contour says how far things stand along the front camera's line of sight; heights and widths are the front
    picture's. Landmarks alone (round 1) left the subnasale free to slide 3 mm down (philtrum, lower third): now
    PROFILE_HOLD_N vertices spread over the region, so what is left to the solve is depth."""
    from . import humanfit
    from . import likeness_profile as lp
    out = []
    for vi, (ph, md) in enumerate(zip(cmp["photos"], cmp["models"])):
        if ph["kind"] != "front":
            continue
        V, L = md["mesh"]["V"], md["mesh"]["L"]
        if part == "nose":
            ids = lp.nose_ids(V, L)
        elif part == "cheek":   # both cheeks, between the mouth's corner and the jaw's side
            cs = [0.5 * (L[48] + L[4]), 0.5 * (L[54] + L[12])]
            ids = np.nonzero(np.min([np.linalg.norm(V - c, axis=1) for c in cs], axis=0) < 0.03)[0]
        else:
            c = 0.5 * (L[8] + L[57])
            ids = np.nonzero(np.linalg.norm(V - c, axis=1) < 0.032)[0]
        if len(ids) > PROFILE_HOLD_N:
            ids = ids[np.linspace(0, len(ids) - 1, PROFILE_HOLD_N).astype(int)]
        uv = humanfit.project(md["cam"], V[ids])
        out += [{"view": vi, "tpl": [int(a)] * 3, "bary": [1.0, 0.0, 0.0], "uv": [float(u[0]), float(u[1])], "hold": True}
                for a, u in zip(ids, uv)] * PROFILE_HOLD_W
    return out


def _rms(tg) -> float:
    return float(np.sqrt(np.mean([t["raw_mm"] ** 2 for t in tg]))) if tg else 1e9


def _profile_targets(cmp, traces, part) -> list:
    from . import likeness_profile as lp
    group, contour, rng, hold = PROFILE_PARTS[part]
    tg = []
    for vi, (ph, md) in enumerate(zip(cmp["photos"], cmp["models"])):
        rd = profile_read(ph, md, traces)
        if rd is None:
            continue
        vr = None
        if rng:
            lv = rd["model_levels"]
            vr = (lv[rng[0]] + rng[1], lv[rng[2]] + rng[3])
        tg += lp.targets(rd, md["mesh"], md["cam"], vi, contour, v_range=vr, gain=PROFILE_GAIN)
    return tg


def _profile_score(cmp, part):
    v = [r["score"] for r in cmp["rows"] if r["id"] in PROFILE_ITEMS[part] and r["score"] >= 0]
    return float(np.sum(np.square(v))) if v else None


def fit_profile(name: str, base: dict | None = None, parts=("nose", "chin"), force: bool = False, save: bool = False,
                start: dict | None = None, k: int | None = None, photos=None) -> tuple:
    """(base, cmp, log): the nose and the chin fitted to a turned view's contours. Each round: the contour's miss at
    the model vertices that MAKE its contour (likeness_profile.targets, the camera's offset on the bony upper face
    taken out) -> humanfit.fit_region (GNM identity components inside the nose / chin + lower lip region, the other
    landmarks held, integrity-guarded). A round is kept only if the part's contour items score better and (in a staged
    fit: start, k) no earlier stage's pinned item is undone."""
    from . import humanfit, store
    from . import likeness_profile as lp
    from . import likeness_shape as ls
    sp = store.load(name)
    base = base or sp["base"]
    photos = photos or _photos(_refs(name))
    cur = base
    cmp = compare(name, cur, photos=photos)
    cmp_first = cmp
    cams0 = [m["cam"] for m in cmp["models"]]   # ONE camera per picture through the whole fit: refitted per candidate
    # (as compare does for turned views) the camera follows the nose it is meant to judge
    traces = ls.load_points(name)
    log = []
    for part in parts:
        group, contour, rng, hold = PROFILE_PARTS[part]
        for rnd in range(PROFILE_ROUNDS):
            s0 = _profile_score(cmp, part)
            if s0 is None:
                log.append(f"  {part}: no contour on the references (likeness_points 'profile'" + (" / 'nose'" if part == "nose" else "") + ")")
                break
            tg = _profile_targets(cmp, traces, part)
            if len(tg) < 4:
                log.append(f"  {part}: {len(tg)} contour vertices: too few")
                break
            miss = _rms(tg)
            if miss < PROFILE_DONE:
                log.append(f"  {part}: contour within {miss:.1f} mm rms")
                break
            nb, r = humanfit.fit_region(cur, cams0, tg + _front_holds(cmp, part), group, hold=hold, force=force,
                                        name=f"likeness_{part}")
            if r.get("refused"):
                log.append(f"  {part} round {rnd + 1}: REFUSED ({r['refused'][:90]})")
                break
            c = compare(name, nb, photos=photos, cameras=cams0)
            s1 = _profile_score(c, part)
            tg1 = _profile_targets(c, traces, part)
            miss1 = _rms(tg1)
            # pins: every FRONT-view item (any stage) when run alone; the earlier stages' in a staged fit
            und = _undone(start, c, k) if start is not None else _undone(cmp_first, c, 99)
            if float(r.get("largest_sigma") or 0) > PROFILE_SIGMA and not force:
                log.append(f"  {part} round {rnd + 1}: not taken (components at {r.get('largest_sigma')} sigma, limit {PROFILE_SIGMA})")
                break
            note = (f"{len(tg)} contour vertices, contour rms {miss:.1f} -> {miss1:.1f} mm, share {r.get('share')}, largest "
                    f"{r.get('largest_sigma')} sigma; items' score {s0:.1f} -> {s1 if s1 is None else round(s1, 1)}")
            # judged on the contour itself (the items are a few numbers read off it: one of them worse while the line
            # as a whole comes closer stopped the first runs after one round, the bridge left scooped)
            if (miss1 > 0.97 * miss or und) and not force:
                log.append(f"  {part} round {rnd + 1}: not taken ({note}" + (f"; undoes {[u[1]['id'] for u in und]}" if und else "") + ")")
                break
            log.append(f"  {part} round {rnd + 1}: fit_region {group} ({note})")
            cur, cmp = nb, c
    if save and cur is not base:
        v = store.save(name, {**sp, "base": cur}, "likeness profile contour fit")
        log.append(f"saved {name} v{v}")
    return cur, cmp, log


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
        lines.append(f"  {n}: {extra}".rstrip(": "))
    for i, v in (rep.get("expression") or {}).items():
        lines.append(f"  EXPRESSION on the reference ({v}): {_item(i)['name']} is fitted through the pose, not the identity")
    lines += rep.get("log") or []
    if rep.get("gap"):
        lines.append("  GAP: " + rep["gap"])
    for g in rep.get("gaps") or []:
        lines.append("  GAP (no control): " + g)
    lines.append(f"  {'item':40} {'view':14} {'photo':>8} {'before':>8} {'after':>8} {'tol':>6}  x tol before -> after")
    for b, a in rep["rows"]:
        if a["score"] < 0:
            lines.append(f"  {a['name'][:40]:40} {a['view']:14}  (not measured: {(a.get('why') or 'judge by eye')[:80]})")
            continue
        sb = f"{b['score']:.1f}" if b["score"] >= 0 else "-"
        bm = b["model"] if b.get("kind") != "shape" else (-(b.get("miss") or 0.0) if b["score"] >= 0 else None)
        am = a["model"] if a.get("kind") != "shape" else -a["miss"]
        lines.append(f"  {a['name'][:40]:40} {a['view'] + ('~' if a.get('inferred') else ''):14} {_fmt(a['photo'], a['unit']):>8} "
                     f"{_fmt(bm, a['unit']):>8} {_fmt(am, a['unit']):>8} {a['tol']:>6.3g}  {sb} -> {a['score']:.1f}"
                     + ("  ok" if a["score"] <= 1 else "")
                     + (f"  3D {b.get('model3d')} -> {a.get('model3d')} mm" if a.get("kind") == "shape" else ""))
    if rep["undone"]:
        lines.append("  EARLIER STAGES MADE WORSE (review before going on):")
        for b, a in rep["undone"]:
            lines.append(f"    {a['name']} [{a['view']}] ({a['stage']}): {b['score']:.1f} -> {a['score']:.1f} x tol")
    return "\n".join(lines)


def fit_likeness(name: str, stages: list | None = None, force: bool = False, save: bool = True, panels_dir: str | None = None) -> list:
    """Run stages in order (all of them by default), each saved before the next. For a person or an LLM approving
    stage by stage, call with one stage at a time and look at its panels."""
    from . import store
    out = []
    names = stages or [s["name"] for s in stage_names()]
    for s in names:
        pn = str(Path(panels_dir or (store.HOME / "human_renders")) / f"lk_{name}_stage_{s}.png")
        out.append(fit_stage(name, s, force=force, save=save, panels=pn))
    return out

