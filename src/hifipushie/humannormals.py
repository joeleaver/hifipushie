"""Surface normals measured from a picture as evidence for the head's identity (the measurement-model study,
CLAUDE.md "Measurement models").

Microsoft's DAViD (MIT code and weights, trained on synthetic humans only; ONNX, CPU) estimates a normal map of the
person in a picture. Used raw it is worth nothing to a fit; CALIBRATED on renders of heads whose shape is known it is
worth about one character read: per view class and per GNM vertex,
    truth's normal - mean head's normal  ~  gain x (DAViD's normal - mean head's normal)   +- sigma
(gain ~0.5: the model exaggerates relief; sigma = what it leaves open on other heads; vertices where it leaves more
than CUT of the population's own spread are not used). `rows` turns one picture's normal map into linear evidence
rows on the identity components, to add to a least-squares fit (humanfit_map's H, b) about the current head.

On the truth set (skinned EEVEE renders, front + three-quarter): face 2.45 -> 2.21 mm in-model / 2.39 -> 2.13 out,
profile 2.33 -> 2.07 / 3.07 -> 2.74, chin 3.7 -> 2.7, jaw 4.1 -> 3.7; with a read on top 2.06 / 2.03.
CAVEATS: calibrated on RENDERS only (20 heads, 8 skin tones, plain backgrounds), not on photographs; a painting's
brush strokes come out as relief; hair must be masked (pass `hide`); it says nothing on cranium, ears, neck.

Camera frame: x right, y down, z into the picture. World: z up, the head faces -y, its left is +x.
"""
from __future__ import annotations

import hashlib
import os
import subprocess
from pathlib import Path

import numpy as np

CAL = Path(__file__).with_name("david_normals_gnm.npz")
CLASSES = ("front", "left", "profile", "right")      # as humanfit_map's table
HOME = Path(os.environ.get("HIFIPUSHIE_DAVID", "/mnt/data/hifipushie/measuremodels/david"))   # venv/, DAViD/, the .onnx
MODEL = "multi-task-model-vitl16_384.onnx"
URL = "https://facesyntheticspubwedata.z6.web.core.windows.net/iccv-2025/models/" + MODEL
INFLATE = 4.0     # neighbouring vertices' errors are not independent: sigma x this (stable from x3 to x6)
CUT = 0.9         # a vertex is used where the model leaves < CUT of the population's own spread
STEP = 4          # every STEP-th usable vertex
_C = {}

_RUN = r'''
import sys, os
import cv2, numpy as np
sys.path.insert(0, os.path.join(sys.argv[1], "DAViD", "runtime"))
from multi_task_estimator import MultiTaskEstimator
est = MultiTaskEstimator(os.path.join(sys.argv[1], sys.argv[2]), providers=["CPUExecutionProvider"], is_inverse_depth=False)
o = est.estimate_all_tasks(cv2.imread(sys.argv[3]))
np.savez_compressed(sys.argv[4], normal=o["normal"].astype(np.float16), mask=(np.clip(o["foreground"], 0, 1) * 255).astype(np.uint8),
                    depth=o["depth"].astype(np.float32))
'''


def available() -> str | None:
    """None when DAViD can run here, else what is missing and how to get it."""
    if not (HOME / "venv" / "bin" / "python").exists() or not (HOME / "DAViD" / "runtime").exists():
        return (f"DAViD's runtime is not at {HOME}: git clone https://github.com/microsoft/DAViD there, and "
                f"`uv venv venv && uv pip install --python venv/bin/python onnxruntime opencv-python-headless numpy`")
    if not (HOME / MODEL).exists() or (HOME / MODEL).stat().st_size < 1.3e9:
        return f"DAViD's model is missing: fetch {URL} (1.4 GB, MIT) into {HOME}"
    return None


def predict(image: str | Path) -> dict:
    """{"normal": (H, W, 3) unit normals in the CAMERA frame of this module, "mask": (H, W) 0..1 person, "depth":
    relative depth} for a picture file. ~15-40 s on CPU; cached by the file's content beside the model."""
    miss = available()
    if miss:
        raise RuntimeError(miss)
    key = hashlib.sha1(Path(image).read_bytes()).hexdigest()[:20]
    out = HOME / "cache" / f"{key}.npz"
    if not out.exists():
        out.parent.mkdir(exist_ok=True)
        src = HOME / "cache" / "_run.py"
        src.write_text(_RUN)
        subprocess.run([str(HOME / "venv" / "bin" / "python"), str(src), str(HOME), MODEL, str(image), str(out)], check=True, capture_output=True,
                       timeout=1800, env={**os.environ, "OMP_NUM_THREADS": "6"})
    z = np.load(out)
    n = z["normal"].astype(float) * calibration()["flip"]
    n /= np.maximum(np.linalg.norm(n, axis=-1, keepdims=True), 1e-9)
    return {"normal": n, "mask": z["mask"].astype(float) / 255.0, "depth": z["depth"]}


def calibration() -> dict:
    if "cal" not in _C:
        z = np.load(CAL)
        _C["cal"] = {"g": z["g"].astype(float), "s": z["s"].astype(float), "p": z["p"].astype(float), "flip": z["flip"].astype(float)}
    return _C["cal"]


def gnm() -> dict:
    """GNM's mean head in the world frame, triangles, the exterior-skin and face masks."""
    if "g" not in _C:
        from . import base
        g = base._gnm_data()
        X = np.asarray(g["template_vertex_positions"], float)
        V0 = np.stack([X[:, 0], -X[:, 2], X[:, 1]], 1)
        q = np.asarray(g["quads"])
        T = np.r_[q[:, [0, 1, 2]], q[:, [0, 2, 3]]].astype(np.int64)
        gr = {k: np.asarray(v, float) > 0.5 for k, v in g["groups"].items()}
        _C["g"] = {"V0": V0, "T": T, "ext": gr["skin_exterior"], "face": gr["hockey_mask"] & gr["skin_exterior"]}
    return _C["g"]


def vnormals(V, T):
    fn = np.cross(V[T[:, 1]] - V[T[:, 0]], V[T[:, 2]] - V[T[:, 0]])
    vn = np.zeros_like(V)
    for c in range(3):
        np.add.at(vn, T[:, c], fn)
    return vn / np.maximum(np.linalg.norm(vn, axis=1, keepdims=True), 1e-15)


def _similarity(X, Y):
    mx, my = X.mean(0), Y.mean(0)
    A, B = X - mx, Y - my
    U, S, Vt = np.linalg.svd(B.T @ A / len(X))
    d = np.sign(np.linalg.det(U @ Vt))
    R = U @ np.diag([1, 1, d]) @ Vt
    s = (S * [1, 1, d]).sum() / (A ** 2).sum(1).mean()
    return s, R, my - s * mx @ R.T


def _sample(M, pix):
    from scipy import ndimage
    co = np.stack([pix[:, 1] - 0.5, pix[:, 0] - 0.5])
    return np.stack([ndimage.map_coordinates(M[..., c], co, order=1, mode="nearest") for c in range(M.shape[2])], 1)


def visible(V, cam, hide=None):
    """Indices of exterior-skin vertices a camera (humanfit's) sees front-on, away from depth edges and from `hide`
    (a boolean picture mask: hair, a hat, a hand), with their pixels and camera-frame normals."""
    from scipy import ndimage

    from . import humanfit, likeness
    g = gnm()
    if "run" not in _C:
        _C["run"] = likeness._raster()
    w, h = cam["size"]
    Rc = humanfit._cam_rot(cam)
    Xc = (V - np.asarray(cam["centre"], float)) @ Rc.T + np.asarray(cam["t"], float)
    P = humanfit.project(cam, V)
    F = g["T"]
    fn = np.cross(Xc[F[:, 1]] - Xc[F[:, 0]], Xc[F[:, 2]] - Xc[F[:, 0]])
    keep = (fn * Xc[F].mean(1)).sum(1) < 0
    img = np.zeros((h, w, 3))
    zb = np.full((h, w), np.inf)
    _C["run"](P[:, 0].copy(), P[:, 1].copy(), Xc[:, 2].copy(), np.ascontiguousarray(F[keep]), np.zeros((len(V), 3)), w, h, img, zb)
    ok = g["ext"] & (P[:, 0] > 2) & (P[:, 0] < w - 2) & (P[:, 1] > 2) & (P[:, 1] < h - 2)
    u, v = np.clip(P[:, 0].astype(int), 0, w - 1), np.clip(P[:, 1].astype(int), 0, h - 1)
    ok &= Xc[:, 2] < zb[v, u] + 0.003
    m = np.isfinite(zb)
    edge = (ndimage.maximum_filter(np.where(m, zb, -1e9), 7) - ndimage.minimum_filter(np.where(m, zb, 1e9), 7) > 0.012) | ~ndimage.binary_erosion(m, iterations=4)
    ok &= ~edge[v, u]
    if hide is not None:
        ok &= ~np.asarray(hide, bool)[v, u]
    n = vnormals(V, F) @ Rc.T
    ok &= n[:, 2] < -0.15
    idx = np.flatnonzero(ok)
    return idx, P[idx], n[idx], Rc


def rows(normal: np.ndarray, V: np.ndarray, IB: np.ndarray, c: np.ndarray, cam: dict, cls: int, hide=None, only=None,
         inflate: float = INFLATE, cut: float = CUT, step: int = STEP) -> tuple:
    """Evidence rows (A (m, K), y (m,), info) on the identity from one picture's normal map, about the current head.

    normal: (H, W, 3) from `predict` (this module's camera frame); V: the current head's GNM vertices (world, m);
    IB: (K, V, 3) how they move per identity component (world); c: the current components (the rows are linear
    about it: A c' ~ y); cam: the picture's fitted camera (humanfit's dict); cls: the view class (CLASSES);
    hide: a boolean picture mask of what covers the head (hair!); only: a boolean vertex mask to restrict to.
    Add to a normal-equations fit as H += A.T @ A, b += A.T @ y."""
    cal = calibration()
    g = gnm()
    K = len(c)
    idx, pix, n_head, Rc = visible(V, cam, hide)
    f = np.flatnonzero(g["face"])
    s, R, t = _similarity(g["V0"][f], V[f])
    n_mean = (vnormals(s * g["V0"] @ R.T + t, g["T"]) @ Rc.T)[idx]
    gq, sq, pq = cal["g"][cls][idx], cal["s"][cls][idx], cal["p"][cls][idx]
    ok = np.isfinite(sq) & (sq < cut * pq) & (gq > 0.05)
    if only is not None:
        ok &= np.asarray(only, bool)[idx]
    j = np.flatnonzero(ok)[::step]
    if len(j) < 20:
        return np.zeros((0, K)), np.zeros(0), {"vertices": 0}
    nm = _sample(np.asarray(normal, float), pix[j])
    nm /= np.maximum(np.linalg.norm(nm, axis=1, keepdims=True), 1e-9)
    target = n_mean[j] + gq[j, None] * (nm - n_mean[j])
    target /= np.maximum(np.linalg.norm(target, axis=1, keepdims=True), 1e-9)
    res = target - n_head[j]
    # d(normal)/d(component) at the used vertices, by finite differences of the whole head's normals
    n0 = vnormals(V, g["T"])
    J = np.zeros((K, len(j), 3))
    for k in range(K):
        J[k] = (vnormals(V + 0.5 * IB[k], g["T"])[idx[j]] - n0[idx[j]]) / 0.5
    Jc = np.einsum("knd,ed->kne", J, Rc)
    sg = sq[j] * inflate
    A, y = [], []
    for e in (0, 1):
        An = Jc[:, :, e].T
        r = res[:, e] / sg
        w = np.where(np.abs(r) > 2.5, np.sqrt(2.5 / np.maximum(np.abs(r), 1e-9)), 1.0)
        A.append(An / sg[:, None] * w[:, None])
        y.append((res[:, e] + An @ c) / sg * w)
    ang = np.degrees(np.arccos(np.clip((target * n_head[j]).sum(1), -1, 1)))
    return np.vstack(A), np.concatenate(y), {"vertices": int(len(j)), "mean_angle_deg": float(ang.mean())}
