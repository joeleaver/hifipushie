"""Measurement-model study: ground truth per picture of the skinned set and the scores a dense model is judged by.

Camera frame everywhere: x right, y down, z into the picture (OpenCV; humanfit's cameras; MoGe's points).
A prediction is MM/pred/<model>/<id>.npz with any of: depth (H, W), points (H, W, 3), normal (H, W, 3), mask.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import numpy as np
from scipy import ndimage

import rs

MM = Path(os.environ.get("MM", "/mnt/data/hifipushie/measuremodels"))
SET = MM / "set"
PRED = MM / "pred"
REG = ("face", "nose", "chin", "lips", "eyes", "brow", "cheeks", "forehead", "jaw", "ears", "cranium", "neck")
_C = {}


def ids(kind=None, view=None):
    out = json.loads((SET / "jobs.json").read_text())
    if kind == "truth":
        out = [i for i in out if not i.startswith("C")]
    if kind == "cal":
        out = [i for i in out if i.startswith("C")]
    if view:
        out = [i for i in out if i.rsplit("_", 1)[1] in ([view] if isinstance(view, str) else view)]
    return out


def vnormals(V):
    T = rs.gnm()["T"]
    fn = np.cross(V[T[:, 1]] - V[T[:, 0]], V[T[:, 2]] - V[T[:, 0]])
    vn = np.zeros_like(V)
    for c in range(3):
        np.add.at(vn, T[:, c], fn)
    return vn / np.maximum(np.linalg.norm(vn, axis=1, keepdims=True), 1e-15)


def region_of():
    """A region name per vertex (the scoring regions; '' elsewhere)."""
    if "reg" not in _C:
        g = rs.gnm()
        lab = np.full(len(g["V0"]), "", dtype=object)
        for k in ("cranium", "neck", "forehead", "cheeks", "jaw", "brow", "eyes", "lips", "chin", "nose", "ears"):
            lab[g["regions"][k]] = k
        _C["reg"] = lab
        f = np.zeros(len(lab), bool)
        f[g["regions"]["face"]] = True
        _C["face"] = f
    return _C["reg"], _C["face"]


def item(iid):
    """Everything known about a picture: V (as pictured), cam, and per VISIBLE skin vertex (not under the hair
    stand-in, not at a depth edge): idx, pix (u, v), Xc (camera frame, m), n (camera-frame normal), region."""
    if iid in _C:
        return _C[iid]
    meta = json.loads((SET / f"{iid}.json").read_text())
    z = np.load(SET / f"{iid}.npz")
    V = z["V"].astype(float)
    cam = meta["cam"]
    g = rs.gnm()
    f = MM / "gt" / f"{iid}_zb.npy"
    if f.exists():
        zb = np.load(f).astype(float)
    else:
        f.parent.mkdir(exist_ok=True)
        _, zb = rs.render(V, cam)
        np.save(f, zb.astype(np.float32))
    w, h = cam["size"]
    P = rs.humanfit.project(cam, V)
    Xc = rs.cam_xform(cam, V)
    ok = g["ext"] & (P[:, 0] > 2) & (P[:, 0] < w - 2) & (P[:, 1] > 2) & (P[:, 1] < h - 2)
    u, v = np.clip(P[:, 0].astype(int), 0, w - 1), np.clip(P[:, 1].astype(int), 0, h - 1)
    ok &= Xc[:, 2] < zb[v, u] + 0.003
    m = np.isfinite(zb)
    zf = np.where(m, zb, 0.0)
    edge = (ndimage.maximum_filter(np.where(m, zb, -1e9), 7) - ndimage.minimum_filter(np.where(m, zb, 1e9), 7) > 0.012) | ~ndimage.binary_erosion(m, iterations=4)
    ok &= ~edge[v, u]
    hair = np.zeros((h, w), bool)
    if len(z["hairV"]):
        Ph = rs.humanfit.project(cam, z["hairV"].astype(float))
        hu, hv = np.clip(Ph[:, 0].astype(int), 0, w - 1), np.clip(Ph[:, 1].astype(int), 0, h - 1)
        hair[hv, hu] = True
        hair = ndimage.binary_dilation(ndimage.binary_closing(hair, iterations=3), iterations=5)
        ok &= ~hair[v, u]
    n = vnormals(V) @ rs.humanfit._cam_rot(cam).T
    ok &= n[:, 2] < -0.15            # facing the camera (grazing surfaces say little)
    idx = np.flatnonzero(ok)
    reg, face = region_of()
    out = {"id": iid, "subject": meta["subject"], "view": meta["view"], "V": V, "cam": cam, "zb": zb, "hair": hair, "idx": idx,
           "pix": P[idx], "Xc": Xc[idx], "n": n[idx], "reg": reg[idx], "face": face[idx], "look": meta["look"], "zf": zf}
    _C[iid] = out
    return out


def image(iid):
    from PIL import Image
    return np.asarray(Image.open(SET / f"{iid}.png").convert("RGB"))


def pred(model, iid):
    f = PRED / model / f"{iid}.npz"
    return dict(np.load(f)) if f.exists() else None


def sample(M, pix):
    """A map (H, W[, c]) read at pixel positions (u, v) (pixel centres at +0.5), bilinear."""
    co = np.stack([pix[:, 1] - 0.5, pix[:, 0] - 0.5])
    if M.ndim == 2:
        return ndimage.map_coordinates(M, co, order=1, mode="nearest")
    return np.stack([ndimage.map_coordinates(M[..., c], co, order=1, mode="nearest") for c in range(M.shape[2])], 1)


def mean_head(it):
    """GNM's mean head laid on this picture's head by a similarity on the visible face: (Xc, n) at it's vertices."""
    g = rs.gnm()
    V0 = g.get("V0_gnm", g["V0"])
    f = it["idx"][it["face"]]
    s, R, t = rs.similarity(V0[f], it["V"][f])
    A = s * V0 @ R.T + t
    n = vnormals(A) @ rs.humanfit._cam_rot(it["cam"]).T
    return rs.cam_xform(it["cam"], A)[it["idx"]], n[it["idx"]]


def fit_z(d, zt, w, inverse=False, iters=4):
    """Scale + shift taking a model's depth to true z on weighted points (robust). inverse: the model gives
    disparity. Returns the aligned z at every point."""
    y = 1.0 / zt if inverse else zt
    ww = w.astype(float).copy()
    for _ in range(iters):
        A = np.c_[d, np.ones(len(d))] * ww[:, None]
        a, b = np.linalg.lstsq(A, y * ww, rcond=None)[0]
        r = a * d + b - y
        sc = 1.4826 * np.median(np.abs(r[w > 0])) + 1e-12
        ww = w * np.where(np.abs(r) > 3 * sc, 3 * sc / np.maximum(np.abs(r), 1e-12), 1.0)
    q = a * d + b
    return 1.0 / np.maximum(q, 1e-6) if inverse else q
