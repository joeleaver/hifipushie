"""Dense landmarks on GNM's topology: the landmark SET our own detector is trained to find (docs/notes/
fitter_whitepaper.md "## denselm"; after Wood et al. 2022: hundreds of points, each with its own uncertainty, trained
on synthetic renders only, where every vertex's pixel is known exactly), and the detector's inference (`predict`).

The set (`landmarks()`): GNM skin vertices picked for COVERAGE by farthest-point sampling with a density per region
(lids / lips x ~3, nose and chin x 2, the face x 1.2, scalp and neck sparse), on the left half and mirrored, always
with the 68 standard landmarks' vertices; plus per eye the iris centre and 8 limbus points (today from the model's
own eyeballs; GNM's eyeball, teeth, tongue and gums join when GNM's own components are evaluated: "after gnmnative").
Every landmark is predicted whether visible or not: a hidden one comes back with a large sigma (no visibility flag).
"""
from __future__ import annotations

import functools
from pathlib import Path

import numpy as np

VERSION = 1
N_HALF = 300                # farthest-point picks on the left half (+ the mid-line); the set is these + their mirrors
LIMBUS_N = 8                # limbus points per eye
# a region's density: distances inside it are divided by this before the farthest-point rule (2 = twice as dense
# along a line, ~4x per area)
DENSITY = (("upper_lip", 3.0), ("lower_lip", 3.0), ("lids", 3.2), ("left_orbital_region", 2.0), ("right_orbital_region", 2.0),
           ("upper_lip_region", 1.9), ("lower_lip_region", 1.9), ("nose_region", 2.0), ("chin_region", 1.8),
           ("left_brow_region", 1.6), ("right_brow_region", 1.6), ("middle_brow_region", 1.5), ("hockey_mask", 1.25),
           ("ears", 1.0))
REST = 0.55                 # scalp, neck, the back of the head
# evaluation groups, first match wins
REGIONS = (("lids", ("lids",)), ("lips", ("upper_lip", "lower_lip")),
           ("eyes", ("left_orbital_region", "right_orbital_region")),
           ("brows", ("left_brow_region", "right_brow_region", "middle_brow_region")), ("nose", ("nose_region",)),
           ("mouth", ("upper_lip_region", "lower_lip_region")), ("chin", ("chin_region",)),
           ("cheeks", ("left_cheek_region", "right_cheek_region", "left_infraorbital_region", "right_infraorbital_region",
                       "left_zygomatic_region", "right_zygomatic_region", "left_parotid_region", "right_parotid_region")),
           ("forehead", ("forehead_region", "left_temple_region", "right_temple_region")), ("ears", ("ears",)),
           ("face_other", ("hockey_mask",)))


def _groups() -> tuple:
    from . import base as basemod, onemesh
    g = basemod._gnm_data()
    gr = {k: np.asarray(v) > 0.5 for k, v in g["groups"].items()}
    T = np.asarray(g["template_vertex_positions"], float)
    a = onemesh.asset()
    present = np.zeros(len(T), bool)        # GNM vertices the one human mesh carries (its skin above the neck ring)
    gid = np.asarray(a["gnm_id"], int)
    present[gid[gid >= 0]] = True
    # the lid margins: skin vertices on the border of the eye openings (edges with one skin face, near an eyeball)
    Q = np.asarray(g["quads"], int)
    sk = gr["skin_exterior"]
    q = Q[sk[Q].all(1)]
    e = np.sort(np.concatenate([q[:, [0, 1]], q[:, [1, 2]], q[:, [2, 3]], q[:, [3, 0]]]), 1)
    u, n = np.unique(e, axis=0, return_counts=True)
    bnd = np.zeros(len(T), bool)
    bnd[u[n == 1].ravel()] = True
    orb = gr["left_orbital_region"] | gr["right_orbital_region"]
    lids = bnd & orb
    # ... and the two rings of skin behind them (the lid's edge and platform)
    for _ in range(2):
        m = lids[q].any(1)
        grow = np.zeros(len(T), bool)
        grow[q[m].ravel()] = True
        lids = lids | (grow & orb)
    gr["lids"] = lids
    return T, gr, present, g


@functools.lru_cache(maxsize=1)
def landmarks() -> dict:
    """{"gnm": (Ls,) GNM vertex ids, "region": (L,) names, "mirror": (L,) the landmark on the other side, "names",
    "n_skin", "n": L, "extra": the non-skin names, "lm68": (68,) positions in the set of the 68 standard landmarks}."""
    T, gr, present, g = _groups()
    ok = gr["skin_exterior"] & present
    dens = np.full(len(T), REST)
    for name, d in reversed(DENSITY):
        dens[gr[name]] = d
    for name, d in DENSITY:                    # the densest group a vertex is in
        dens[gr[name]] = np.maximum(dens[gr[name]], d)
    # mirror map on the template (x -> -x)
    from scipy.spatial import cKDTree
    idx_ok = np.where(ok)[0]
    tree = cKDTree(T[idx_ok])
    dm, jm = tree.query(T[idx_ok] * np.array([-1.0, 1.0, 1.0]))
    mirror_v = np.full(len(T), -1)
    mirror_v[idx_ok] = idx_ok[jm]
    sym = np.zeros(len(T), bool)
    sym[idx_ok] = dm < 0.0008
    half = np.where(ok & sym & (T[:, 0] >= -1e-5))[0]
    # the 68 standard landmarks' vertices are in from the start (their heaviest vertex)
    WL = np.asarray(g["lm68"], float)
    lm_v = []
    for r in WL:
        ids, w = r[0::2].astype(int), r[1::2]          # (vertex, weight) pairs
        lm_v.append(int(ids[int(np.argmax(w))]))
    seed = []
    for v in lm_v:
        v2 = v if T[v, 0] >= -1e-5 else int(mirror_v[v])
        if v2 >= 0 and ok[v2] and sym[v2] and v2 not in seed:
            seed.append(v2)
    P = T[half]
    pos = {int(v): i for i, v in enumerate(half)}
    seed = [v for v in seed if v in pos]
    dmin = np.full(len(half), np.inf)
    picks = []
    for v in seed:
        i = pos[v]
        picks.append(i)
        dmin = np.minimum(dmin, np.linalg.norm(P - P[i], axis=1))
    while len(picks) < N_HALF:
        i = int(np.argmax(dmin * dens[half]))
        picks.append(i)
        dmin = np.minimum(dmin, np.linalg.norm(P - P[i], axis=1))
    left = half[picks]
    mid = np.abs(T[left, 0]) < 1e-5
    vs = list(map(int, left)) + [int(mirror_v[v]) for v in left[~mid]]
    vs = np.array(vs)
    Ls = len(vs)
    where = {int(v): i for i, v in enumerate(vs)}
    mirror = np.arange(Ls)
    nm = np.where(~mid)[0]
    mirror[nm] = len(left) + np.arange(len(nm))
    mirror[len(left):] = nm
    region = []
    for v in vs:
        r = "scalp_neck"
        for name, groups_ in REGIONS:
            if any(gr[k][v] for k in groups_):
                r = name
                break
        region.append(r)
    names = [f"skin_{int(v)}" for v in vs]
    extra = []
    for s in ("L", "R"):
        extra += [f"iris.{s}"] + [f"limbus.{s}.{k}" for k in range(LIMBUS_N)]
    # the eye points' mirrors: L <-> R, the ring's points swapped left-right (k -> the point at pi - angle)
    em = []
    for si, s in enumerate(("L", "R")):
        o = Ls + (1 - si) * (1 + LIMBUS_N)
        em.append(o)
        em += [o + 1 + ((LIMBUS_N // 2 - k) % LIMBUS_N) for k in range(LIMBUS_N)]
    lm68 = np.array([where[v] if v in where else -1 for v in lm_v])
    return {"gnm": vs, "region": np.array(region + ["eyeball"] * len(extra)), "mirror": np.r_[mirror, np.array(em)],
            "names": names + extra, "extra": extra, "n_skin": Ls, "n": Ls + len(extra), "lm68": lm68, "version": VERSION}


def limbus_points(centre, axis, eye_r: float, iris_r: float, up=(0.0, 0.0, 1.0)) -> np.ndarray:
    """(1 + LIMBUS_N, 3): the iris centre (on the limbus plane) and LIMBUS_N points round the limbus of an eyeball
    (centre, gaze axis, radius; iris radius). Point k is at angle 2 pi k / n from the eye's +x (the subject's left)
    toward up, so k and n/2 - k mirror each other."""
    c, a = np.asarray(centre, float), np.asarray(axis, float)
    a = a / np.linalg.norm(a)
    x = np.cross(np.asarray(up, float), -a)           # the subject faces -Y: its left is +X
    x /= np.linalg.norm(x)
    y = np.cross(-a, x)
    y /= np.linalg.norm(y)
    if y @ np.asarray(up, float) < 0:
        y = -y
    if x[0] < 0:
        x = -x
    h = np.sqrt(max(eye_r ** 2 - iris_r ** 2, 0.0))
    o = c + a * h
    t = 2 * np.pi * np.arange(LIMBUS_N) / LIMBUS_N
    return np.concatenate([o[None], o[None] + iris_r * (np.cos(t)[:, None] * x[None] + np.sin(t)[:, None] * y[None])])


def model_vertices(tpl_fid) -> np.ndarray:
    """(Ls,) for each skin landmark, its vertex in a one-mesh model's template (humanfit.state(base)["tpl"]["P"])."""
    from . import onemesh
    gid = np.asarray(onemesh.asset()["gnm_id"], int)[np.asarray(tpl_fid)]
    at = np.full(int(gid.max()) + 1, -1)
    at[gid[gid >= 0]] = np.where(gid >= 0)[0]
    v = at[landmarks()["gnm"]]
    if (v < 0).any():
        raise ValueError("denselm: the model's mesh lacks GNM vertices of the landmark set")
    return v


# ---- inference --------------------------------------------------------------------------------------------------------

WEIGHTS_ENV = "HIFIPUSHIE_DENSELM"          # a .onnx / .pt of the trained network (an optional asset: not in git)


def crop_box(box, margin: float = 0.0) -> tuple:
    """a square pixel box (x0, y0, x1, y1) round a face box, grown by margin x its side."""
    x0, y0, x1, y1 = map(float, box)
    s = max(x1 - x0, y1 - y0) * (1 + margin)
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    return cx - s / 2, cy - s / 2, cx + s / 2, cy + s / 2


def take_crop(img, box, size: int = 256):
    """the square box of a PIL image resampled to size x size (outside the picture: edge colour's mean)."""
    from PIL import Image
    x0, y0, x1, y1 = box
    im = img.convert("RGB")
    fill = tuple(int(v) for v in np.asarray(im.resize((1, 1), Image.BOX)).ravel())
    return im.transform((size, size), Image.EXTENT, (x0, y0, x1, y1), Image.BICUBIC, fillcolor=fill)


def weights_path() -> Path | None:
    import os
    p = os.environ.get(WEIGHTS_ENV)
    return Path(p) if p and Path(p).exists() else None


@functools.lru_cache(maxsize=2)
def _net(path: str):
    import onnxruntime as ort
    so = ort.SessionOptions()
    so.intra_op_num_threads = 2
    return ort.InferenceSession(path, so, providers=["CPUExecutionProvider"])


def predict(img, box, weights: str | None = None, flip: bool = True) -> dict:
    """The detector on a square crop (box in picture pixels: see crop_box) of a PIL image -> {"xy": (L, 2) picture
    pixels, "sigma": (L,) picture pixels (the network's own: large = unsure / hidden)}. flip: average with the mirrored
    crop's prediction (test-time augmentation)."""
    w = weights or (str(weights_path()) if weights_path() else None)
    if not w:
        raise RuntimeError(f"denselm: no trained network (set ${WEIGHTS_ENV} to its .onnx)")
    net = _net(w)
    size = int(net.get_inputs()[0].shape[-1])
    im = np.asarray(take_crop(img, box, size), np.float32) / 255.0
    L = landmarks()

    def run(a):
        x = ((a - np.array([0.485, 0.456, 0.406], np.float32)) / np.array([0.229, 0.224, 0.225], np.float32)).transpose(2, 0, 1)[None]
        o = net.run(None, {net.get_inputs()[0].name: x.astype(np.float32)})[0][0].reshape(-1, 3)
        return o[:, :2], o[:, 2]
    xy, ls = run(im)
    if flip:
        xy2, ls2 = run(im[:, ::-1].copy())
        xy2 = xy2[L["mirror"]] * np.array([-1.0, 1.0])
        ls2 = ls2[L["mirror"]]
        w1, w2 = np.exp(-2 * ls), np.exp(-2 * ls2)
        xy = (xy * w1[:, None] + xy2 * w2[:, None]) / (w1 + w2)[:, None]
        ls = -0.5 * np.log((w1 + w2) / 2)
    x0, y0, x1, y1 = box
    s = (x1 - x0) / 2.0
    return {"xy": np.stack([x0 + (xy[:, 0] + 1) * s, y0 + (xy[:, 1] + 1) * s], 1), "sigma": np.exp(ls) * s}
