"""Reference-modelling study: the fast lane. Heads in GNM's own frame (no body, no MakeHuman build), a numba
renderer, the detector with depth kept, ground-truth scoring by region. Everything here is study scaffolding; the
prototype that came out of it is src/hifipushie/humanmacro.py.

World frame as the rest of the repo: Z up, the head faces -Y, its left is +X. GNM's frame is y up, facing +z."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
from pathlib import Path

import numpy as np

from hifipushie import base, headfit, humanfit, likeness

D = Path(os.environ.get("D", "/mnt/data/hifipushie/refstudy"))
CACHE = D / "cache"
K_TRUE = 170   # head components a synthetic truth head uses (all of GNM's)
K_FIT = 120    # what the fits may use (headfit.N: the repo's solvers)
_C = {}


def gnm():
    if "g" in _C:
        return _C["g"]
    g = base._gnm_data()
    names = [str(n) for n in g["identity_names"]]
    comps = [i for i, n in enumerate(names) if n.startswith("head")]
    V0 = to_world(g["template_vertex_positions"].astype(float))
    IB = to_world(np.asarray(g["vertex_identity_basis"])[comps].astype(np.float32))
    q = np.asarray(g["quads"])
    T = np.r_[q[:, [0, 1, 2]], q[:, [0, 2, 3]]].astype(np.int64)
    gr = {k: np.asarray(v, float) > 0.5 for k, v in g["groups"].items()}
    nv = len(V0)
    W = np.zeros((70, nv))
    for i, r in enumerate(g["lm68"]):
        for v, w in zip(r[0::2], r[1::2]):
            W[i, int(v)] += float(w)
    le, re = gr["left_eye"], gr["right_eye"]
    if V0[le, 0].mean() < V0[re, 0].mean():
        le, re = re, le
    W[68, le] = 1.0 / le.sum()   # the subject's left (+x), as humanfit's EYE_L
    W[69, re] = 1.0 / re.sum()
    ext = gr["skin_exterior"]
    out = {"V0": V0, "IB": IB, "T": T, "gr": gr, "W": W, "ext": ext, "names": names, "comps": comps, "raw": g,
           "L0": W @ V0, "LB": np.einsum("ln,cnd->cld", W, IB)}
    out["albedo"] = _albedo(out)
    out["regions"] = _regions(out)
    _C["g"] = out
    return out


def to_world(X):
    X = np.asarray(X)
    return np.stack([X[..., 0], -X[..., 2], X[..., 1]], -1)


def _albedo(g):
    gr, V0 = g["gr"], g["V0"]
    A = np.tile(likeness.SKIN, (len(V0), 1))
    A[gr["scleras"]] = [235, 230, 225]
    A[gr["irises"]] = [80, 62, 48]
    A[gr["pupils"]] = [25, 18, 15]
    A[gr["teeth"]] = [225, 220, 205]
    A[gr["mouth_sock"] | gr["tongue"] | gr["gums"]] = [120, 60, 60]
    L = g["L0"]
    brow = np.zeros(len(V0), bool)   # brows painted on the skin: within 3.5 mm of the brow landmarks' polylines
    for a, b in ((17, 22), (22, 27)):
        for i in range(a, b - 1):
            p, q = L[i], L[i + 1]
            t = np.clip(((V0 - p) @ (q - p)) / ((q - p) @ (q - p)), 0, 1)
            brow |= np.linalg.norm(V0 - (p + t[:, None] * (q - p)), axis=1) < 0.0035
    A[brow & g["ext"]] = [70, 52, 40]
    g["brow"] = brow & g["ext"]
    return A


def _regions(g):
    """Named sets of exterior skin vertices to score by."""
    gr, V0, L, ext = g["gr"], g["V0"], g["L0"], g["ext"]
    two = lambda n: gr[f"left_{n}_region"] | gr[f"right_{n}_region"]  # noqa: E731
    named = {"chin": gr["chin_region"], "nose": gr["nose_region"], "eyes": two("orbital"), "under_eye": two("infraorbital"),
             "brow": two("brow") | gr["middle_brow_region"], "cheeks": two("cheek") | two("zygomatic"),
             "jaw": two("parotid"), "lips": gr["upper_lip_region"] | gr["lower_lip_region"],
             "forehead": gr["forehead_region"] | two("temple"), "ears": gr["ears"]}
    used = np.zeros(len(V0), bool)
    out = {}
    for k, m in named.items():
        out[k] = np.flatnonzero(m & ext)
        used |= m
    rest = ext & ~used
    zc = L[8, 2]   # chin level
    out["cranium"] = np.flatnonzero(rest & (V0[:, 2] > L[27, 2] - 0.01))
    out["neck"] = np.flatnonzero(rest & (V0[:, 2] < zc + 0.005))
    out["face"] = np.flatnonzero(gr["hockey_mask"] & ext)
    out["head"] = np.flatnonzero(ext & (V0[:, 2] > zc - 0.02))
    # the mid-line profile from the hairline to under the chin (what a true profile view draws)
    front = V0[:, 1] < L[[0, 16], 1].mean()
    out["profile"] = np.flatnonzero(ext & front & (np.abs(V0[:, 0]) < 0.0015) & (V0[:, 2] > zc - 0.015) & (V0[:, 2] < L[27, 2] + 0.06))
    return out


REGIONS = ("face", "profile", "jaw", "chin", "nose", "eyes", "brow", "cheeks", "lips", "forehead", "cranium", "ears", "neck", "head")


# ---- heads --------------------------------------------------------------------------------------------------------

def head(c=None, e=None, extra=None):
    """World vertices of GNM's head with identity c (head components, sigma), expression offsets e (V, 3 world) and
    any extra displacement."""
    g = gnm()
    V = g["V0"].copy()
    if c is not None:
        c = np.asarray(c, float)
        V += np.tensordot(c, g["IB"][:len(c)], 1)
    if e is not None:
        V += e
    if extra is not None:
        V += extra
    return V


def expression(pose: dict, V=None):
    """World vertex offsets of a pose in base.POSE's words (m): smile, lid_upper (+ closes), brow_inner (- frowns)..."""
    g = gnm()
    Vg = np.asarray(g["raw"]["template_vertex_positions"], float)
    return to_world(base.pose_expression(pose, Vg, 1.0))


def mh_field(age, sex, weight=0.5, amount=1.0):
    """World offsets taking GNM's mean head to MakeHuman's head of this age / sex / weight: out of GNM's basis."""
    g = gnm()
    io = float(abs(g["L0"][68, 0] - g["L0"][69, 0]))
    d = headfit.field_vertices({"age": age, "sex": sex, "weight": weight, "toward": 1.0, "amount": amount, "dimorphism": 0.8})
    return to_world(d) * io


def landmarks(V):
    return gnm()["W"] @ V


def similarity(X, Y, w=None):
    """s, R, t with Y ~ s X R^T + t (least squares)."""
    w = np.ones(len(X)) if w is None else w
    w = w / w.sum()
    mx, my = w @ X, w @ Y
    A, B = X - mx, Y - my
    U, S, Vt = np.linalg.svd((B * w[:, None]).T @ A)
    d = np.sign(np.linalg.det(U @ Vt))
    Dm = np.diag([1, 1, d])
    R = U @ Dm @ Vt
    s = (S * [1, 1, d]).sum() / (w @ (A ** 2).sum(1))
    return s, R, my - s * mx @ R.T


def score(V, Vt, scale=True) -> dict:
    """mm by region: mean vertex distance of V from the truth Vt after aligning V onto Vt on the face (similarity:
    pictures don't give a head's absolute size). "profile" is the fore-aft miss (rms) of the mid-line."""
    g = gnm()
    f = g["regions"]["face"]
    s, R, t = similarity(V[f], Vt[f])
    if not scale:
        s = 1.0
        _, R, t = similarity(V[f], Vt[f])
        t = Vt[f].mean(0) - V[f].mean(0) @ R.T
    A = s * V @ R.T + t
    d = np.linalg.norm(A - Vt, axis=1) * 1000
    out = {k: float(d[i].mean()) for k, i in g["regions"].items()}
    p = g["regions"]["profile"]
    out["profile"] = float(np.sqrt(((A[p, 1] - Vt[p, 1]) ** 2).mean()) * 1000)
    out["scale"] = float(s)
    return out


def row(sc: dict) -> str:
    return " ".join(f"{sc[k]:5.2f}" for k in REGIONS)


HEADER = " ".join(f"{k[:5]:>5}" for k in REGIONS)


# ---- cameras and pictures ------------------------------------------------------------------------------------------

def make_cam(V, yaw=0.0, pitch=0.0, roll=0.0, lens=50.0, size=(768, 768), fill=0.62, off=(0.0, 0.0)):
    """A pinhole camera in humanfit's convention looking at the head: yaw deg (+ = the picture shows the subject's
    left side), lens = 35 mm-equivalent focal, the head's height `fill` of the frame."""
    g = gnm()
    ctr = landmarks(V)[:68].mean(0)
    w, h = size
    f = lens / 36.0 * w
    hh = float(np.ptp(V[g["regions"]["head"], 2]))
    dist = f * hh / (fill * h)
    r = _rv(humanfit._rotvec([np.radians(pitch), 0, 0]) @ humanfit._rotvec([0, 0, np.radians(roll)]))
    return {"r": r.tolist(), "t": [off[0] * dist, off[1] * dist, dist], "f": float(f), "size": [w, h], "centre": ctr.tolist(),
            "yaw": float(yaw), "lens": float(lens)}


def _rv(R):
    from scipy.spatial.transform import Rotation
    return Rotation.from_matrix(R).as_rotvec()


def cam_xform(cam, X):
    return (np.asarray(X, float) - np.asarray(cam["centre"], float)) @ humanfit._cam_rot(cam).T + np.asarray(cam["t"], float)


def render(V, cam, light=None, albedo=None, bg=238.0, flat=False):
    """(image uint8 HxWx3, depth (inf off the head), vertex-id of the nearest vertex is not kept: use depth)."""
    g = gnm()
    if "run" not in _C:
        _C["run"] = likeness._raster()
    w, h = cam["size"]
    Xc = cam_xform(cam, V)
    P = humanfit.project(cam, V)
    F = g["T"]
    fn = np.cross(Xc[F[:, 1]] - Xc[F[:, 0]], Xc[F[:, 2]] - Xc[F[:, 0]])
    keep = (fn * Xc[F].mean(1)).sum(1) < 0
    vn = np.zeros_like(Xc)
    for c in range(3):
        np.add.at(vn, F[:, c], fn)
    vn /= np.maximum(np.linalg.norm(vn, axis=1, keepdims=True), 1e-15)
    key = likeness.KEY if light is None else np.asarray(light, float) / np.linalg.norm(light)
    sh = 0.24 + 0.76 * np.clip(vn @ key, 0, 1) ** 1.3 + 0.06 * np.clip(-vn[:, 2], 0, 1)
    A = g["albedo"] if albedo is None else albedo
    C = np.clip(A * (1.0 if flat else sh[:, None]), 0, 255)
    img = np.full((h, w, 3), float(bg))
    zb = np.full((h, w), np.inf)
    _C["run"](P[:, 0].copy(), P[:, 1].copy(), Xc[:, 2].copy(), np.ascontiguousarray(F[keep]), np.ascontiguousarray(C), w, h, img, zb)
    return img.astype(np.uint8), zb


def skinned_albedo(seed=0):
    """A second look of the same head: lips tinted, stubble shadow on the lower face, a little mottling."""
    g = gnm()
    rng = np.random.default_rng(seed)
    A = g["albedo"].copy()
    gr = g["gr"]
    A[gr["upper_lip"] | gr["lower_lip"]] = [176, 110, 104]
    low = (gr["chin_region"] | gr["left_parotid_region"] | gr["right_parotid_region"] | gr["upper_lip_region"]) & g["ext"] & ~(gr["upper_lip"] | gr["lower_lip"])
    A[low] = A[low] * [0.78, 0.8, 0.84]
    A[g["ext"]] *= rng.normal(1.0, 0.02, (int(g["ext"].sum()), 1))
    A[g["brow"]] = [70, 52, 40]
    return A


def visible(V, cam, idx=None, zb=None, tol=0.004):
    """Which vertices (all, or idx) the camera sees (depth test against the render's z-buffer)."""
    if zb is None:
        _, zb = render(V, cam)
    X = V if idx is None else V[idx]
    P = humanfit.project(cam, X)
    z = cam_xform(cam, X)[:, 2]
    w, h = cam["size"]
    u, v = np.clip(P[:, 0].astype(int), 0, w - 1), np.clip(P[:, 1].astype(int), 0, h - 1)
    return z < zb[v, u] + tol


def unproject(cam, uv, zb):
    """World points under pixels (nan where the picture shows no head)."""
    w, h = cam["size"]
    u, v = np.clip(np.round(uv[:, 0] - 0.5).astype(int), 0, w - 1), np.clip(np.round(uv[:, 1] - 0.5).astype(int), 0, h - 1)
    z = zb[v, u]
    Xc = np.stack([(uv[:, 0] - w / 2) / cam["f"] * z, (uv[:, 1] - h / 2) / cam["f"] * z, z], 1)
    X = (Xc - np.asarray(cam["t"])) @ humanfit._cam_rot(cam) + np.asarray(cam["centre"])
    X[~np.isfinite(z)] = np.nan
    return X


# ---- the detector, depth kept ----------------------------------------------------------------------------------------

_DET = r'''
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
    d = {"P": [[q.x * im.size[0], q.y * im.size[1], q.z * im.size[0]] for q in res.face_landmarks[0]]}
    if res.face_blendshapes:
        d["bs"] = {b.category_name: round(float(b.score), 4) for b in res.face_blendshapes[0]}
    if res.facial_transformation_matrixes:
        d["M"] = np.asarray(res.facial_transformation_matrixes[0], float).tolist()
    out.append(d)
json.dump(out, open(sys.argv[1], "w"))
'''


def detect(images: list) -> list:
    """uint8 images -> [{"P": (478, 3) pixels (x, y, z in pixel units, z relative), "bs", "M"} | None], cached."""
    from PIL import Image
    CACHE.mkdir(parents=True, exist_ok=True)
    out, todo, keys = [None] * len(images), [], []
    for i, im in enumerate(images):
        im = np.asarray(im)
        k = hashlib.sha1(im.tobytes() + str(im.shape).encode()).hexdigest()[:20]
        keys.append(k)
        f = CACHE / f"mp3_{k}.json"
        if f.exists():
            out[i] = json.loads(f.read_text())
        else:
            todo.append(i)
    for a in range(0, len(todo), 40):
        part = todo[a:a + 40]
        with tempfile.TemporaryDirectory(dir=str(D)) as td:
            paths = []
            for i in part:
                p = os.path.join(td, f"{i}.png")
                Image.fromarray(np.asarray(images[i])).save(p)
                paths.append(p)
            res, src = os.path.join(td, "out.json"), os.path.join(td, "det.py")
            Path(src).write_text(_DET)
            subprocess.run([str(Path(likeness.VENV) / "bin" / "python"), src, res, str(Path(likeness.VENV) / "face_landmarker.task"), *paths],
                           check=True, capture_output=True, timeout=600)
            got = json.loads(Path(res).read_text())
        for i, v in zip(part, got):
            (CACHE / f"mp3_{keys[i]}.json").write_text(json.dumps(v))
            out[i] = v
    for v in out:
        if v is not None:
            v["P"] = np.asarray(v["P"], float)
    return out


LM_FROM_MP = np.array(likeness.MP68 + [likeness.MP_EYES[1], likeness.MP_EYES[0]])   # 70: the 68 + eye.L, eye.R (iris centres)


def outline(zb, cam, V, levels=None):
    """The head's occluding outline in a picture, as pixels: the mask's boundary between the brows' top and the chin
    (hair hides what is above, the neck what is below)."""
    from scipy import ndimage
    m = np.isfinite(zb)
    edge = m & ~ndimage.binary_erosion(m)
    ys, xs = np.nonzero(edge)
    L = humanfit.project(cam, landmarks(V))
    top = L[17:27, 1].min() - 0.15 * (L[8, 1] - L[27, 1])
    bot = L[8, 1]
    k = (ys > top) & (ys < bot)
    return np.c_[xs[k] + 0.5, ys[k] + 0.5]
