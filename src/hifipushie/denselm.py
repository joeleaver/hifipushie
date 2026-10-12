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

WEIGHTS_ENV = "HIFIPUSHIE_DENSELM"          # the trained network's TorchScript file (model.pt; an optional asset: not in git)
VENV = __import__("os").environ.get("HIFIPUSHIE_NORMALS_VENV", "/mnt/data/hifipushie/normals_venv")   # torch (CPU) + numpy + pillow
SIZE = 256
BOX_SCALE = 1.5 * 1.1                       # the crop: this x the 68 standard landmarks' extent (training's centre)

_RUN_SRC = '''
import sys, json, numpy as np, torch
from PIL import Image
torch.set_num_threads(2)
m = torch.jit.load(sys.argv[1]).eval()
out = []
for f in sys.argv[3:]:
    a = np.asarray(Image.open(f).convert("RGB"), np.float32) / 255.0
    x = torch.from_numpy(np.stack([a, a[:, ::-1].copy()]).transpose(0, 3, 1, 2))
    with torch.no_grad():
        o = m(x).numpy()
    out.append(o.tolist())
json.dump(out, open(sys.argv[2], "w"))
'''


def weights_path() -> Path | None:
    import os
    p = os.environ.get(WEIGHTS_ENV)
    return Path(p) if p and Path(p).exists() else None


def available() -> bool:
    return weights_path() is not None and (Path(VENV) / "bin" / "python").exists()


def box_of(xy68) -> tuple:
    """the network's crop (x0, y0, x1, y1; square) from the 68 standard landmarks' pixels (any source)."""
    xy68 = np.asarray(xy68, float)
    lo, hi = xy68.min(0), xy68.max(0)
    c, s = (lo + hi) / 2, BOX_SCALE * float(max(hi - lo))
    return float(c[0] - s / 2), float(c[1] - s / 2), float(c[0] + s / 2), float(c[1] + s / 2)


def take_crop(img, box, size: int = SIZE):
    """the square box of a PIL image resampled to size x size (outside the picture: its mean colour)."""
    from PIL import Image
    im = img.convert("RGB")
    fill = tuple(int(v) for v in np.asarray(im.resize((1, 1), Image.BOX)).ravel())
    x0, y0, x1, y1 = box
    big = (x1 - x0) / size > 1.5          # shrinking a lot: average first (EXTENT + BICUBIC alone aliases)
    if big:
        k = (x1 - x0) / size
        w, h = max(1, int(round(im.size[0] / k))), max(1, int(round(im.size[1] / k)))
        sx, sy = w / im.size[0], h / im.size[1]
        im = im.resize((w, h), Image.LANCZOS)
        x0, y0, x1, y1 = x0 * sx, y0 * sy, x1 * sx, y1 * sy
    return im.transform((size, size), Image.EXTENT, (x0, y0, x1, y1), Image.BICUBIC, fillcolor=fill)


def _run(crops: list, weights: str) -> list:
    """[(2, L, 3)]: the network on each 256 px crop and on its mirror image."""
    import hashlib
    import json
    import subprocess
    import tempfile
    from . import store
    cdir = store.HOME / "_cache" / "denselm"
    cdir.mkdir(parents=True, exist_ok=True)
    wk = hashlib.sha1((str(Path(weights).stat().st_size) + str(Path(weights).stat().st_mtime_ns)).encode()).hexdigest()[:8]
    keys = [hashlib.sha1(np.asarray(c).tobytes()).hexdigest()[:20] + "_" + wk for c in crops]
    out, todo = [None] * len(crops), []
    for i, k in enumerate(keys):
        f = cdir / f"{k}.npy"
        if f.exists():
            out[i] = np.load(f)
        else:
            todo.append(i)
    if todo:
        with tempfile.TemporaryDirectory() as td:
            ps = []
            for i in todo:
                crops[i].save(f"{td}/{i}.png")
                ps.append(f"{td}/{i}.png")
            Path(f"{td}/run.py").write_text(_RUN_SRC)
            subprocess.run([str(Path(VENV) / "bin" / "python"), f"{td}/run.py", str(weights), f"{td}/out.json", *ps], check=True,
                           capture_output=True, timeout=600)
            got = json.loads(Path(f"{td}/out.json").read_text())
        for i, o in zip(todo, got):
            out[i] = np.asarray(o, np.float32)
            np.save(cdir / f"{keys[i]}.npy", out[i])
    return out


def _merge(o) -> tuple:
    """the crop's prediction and its mirror image's, joined by their own certainties: (xy in [-1, 1], log sigma)."""
    L = landmarks()
    xy, ls = o[0, :, :2], o[0, :, 2]
    xy2, ls2 = o[1][L["mirror"], :2] * np.array([-1.0, 1.0]), o[1][L["mirror"], 2]
    w1, w2 = np.exp(-2 * ls), np.exp(-2 * ls2)
    return (xy * w1[:, None] + xy2 * w2[:, None]) / (w1 + w2)[:, None], -0.5 * np.log((w1 + w2) / 2)


def predict(img, box, weights: str | None = None, passes: int = 2) -> dict:
    """The detector on a PIL picture. box: a rough square (x0, y0, x1, y1) round the face in picture pixels, or the 68
    standard landmarks' pixels from anything ((68, 2)); with passes=2 the crop is laid again on the network's own 68
    and read once more (no other detector's idea of the face stays in the result).
    -> {"xy": (L, 2) picture px, "sigma": (L,) picture px (large = unsure / hidden), "box": the crop used}."""
    w = weights or (str(weights_path()) if weights_path() else None)
    if not w:
        raise RuntimeError(f"denselm: no trained network (set ${WEIGHTS_ENV} to its model.pt)")
    box = np.asarray(box, float)
    box = box_of(box) if box.ndim == 2 else tuple(map(float, box))
    L = landmarks()
    for k in range(max(1, passes)):
        xy, ls = _merge(_run([take_crop(img, box)], w)[0])
        x0, y0, x1, y1 = box
        s = (x1 - x0) / 2.0
        P = np.stack([x0 + (xy[:, 0] + 1) * s, y0 + (xy[:, 1] + 1) * s], 1)
        res = {"xy": P, "sigma": np.exp(ls) * s, "box": box}
        if k + 1 < passes:
            box = box_of(P[L["lm68"]])
    return res
