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
    allv = np.arange(len(T))
    sym &= mirror_v[np.maximum(mirror_v, 0)] == allv            # a true pair (or its own mirror image: the mid-line)
    own = mirror_v == allv
    half = np.where(ok & sym & (own | (T[:, 0] > 0)))[0]
    # the 68 standard landmarks' vertices are in from the start (their heaviest vertex)
    WL = np.asarray(g["lm68"], float)
    lm_v = []
    for r in WL:
        ids, w = r[0::2].astype(int), r[1::2]          # (vertex, weight) pairs
        lm_v.append(int(ids[int(np.argmax(w))]))
    seed = []
    for v in lm_v:
        v2 = v if (own[v] or T[v, 0] > 0) else int(mirror_v[v])
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
    mid = own[left]
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
    # (a standard landmark whose own vertex is not exterior skin, an inner lip point: the set's nearest landmark)
    lm68 = np.array([where[v] if v in where else int(np.argmin(np.linalg.norm(T[vs] - T[v], axis=1))) for v in lm_v])
    return {"gnm": vs, "region": np.array(region + ["eyeball"] * len(extra)), "mirror": np.r_[mirror, np.array(em)],
            "names": names + extra, "extra": extra, "n_skin": Ls, "n": Ls + len(extra), "lm68": lm68, "version": VERSION}


def _sym_fps(T, cand, n_half: int, seed=()):
    """Farthest-point picks on the vertex subset `cand` (ids) of the template T, as mirror pairs about x = 0:
    (ids (n,), mirror (n,) = each pick's partner's position in ids). Vertices without a mirror partner in the subset
    (within 0.8 mm) are left out."""
    from scipy.spatial import cKDTree
    cand = np.asarray(cand, int)
    dm, jm = cKDTree(T[cand]).query(T[cand] * np.array([-1.0, 1.0, 1.0]))
    part = cand[jm]
    back = dict(zip(cand.tolist(), part.tolist()))
    ok = (dm < 0.0008) & np.array([back.get(int(q), -1) == int(v) for v, q in zip(cand, part)])
    own = part == cand
    half = np.where(ok & (own | (T[cand, 0] > 0)))[0]
    P = T[cand[half]]
    picks, dmin = [], np.full(len(half), np.inf)
    for v in seed:
        k = np.where(cand[half] == v)[0]
        if len(k):
            picks.append(int(k[0]))
            dmin = np.minimum(dmin, np.linalg.norm(P - P[k[0]], axis=1))
    if not picks:
        picks.append(int(np.argmax(P[:, 2] - np.abs(P[:, 0]))))          # the most forward point nearest the mid-line
        dmin = np.linalg.norm(P - P[picks[0]], axis=1)
    while len(picks) < min(n_half, len(half)):
        i = int(np.argmax(dmin))
        picks.append(i)
        dmin = np.minimum(dmin, np.linalg.norm(P - P[i], axis=1))
    left = cand[half[picks]]
    mid = own[half[picks]]
    ids = np.r_[left, part[half[picks]][~mid]]
    mirror = np.arange(len(ids))
    nm = np.where(~mid)[0]
    mirror[nm] = len(left) + np.arange(len(nm))
    mirror[len(left):] = nm
    return ids, mirror


TEETH_HALF = 7              # landmarks per half tooth row (the front arc: what a smile or an open jaw shows)
TONGUE_HALF = 5
TEETH_ARC = 0.016           # m: a tooth vertex this far behind its row's most forward one is still "the front arc"


@functools.lru_cache(maxsize=1)
def landmarks_v2() -> dict:
    """VERSION 2 (stage 1, after gnmnative): version 1's skin landmarks, UNCHANGED and first (so regions, the 68 and
    every reader of the skin part stay valid), then GNM's OWN loose pieces, all as GNM vertex ids ("gnm_all"): per eye
    the pupil's centre vertex and 8 vertices round the iris disc's rim (GNM's recessed iris: its limbus ring), the
    front arc of the upper and of the lower teeth, the tongue's upper front. Regions "eyeball", "teeth_upper",
    "teeth_lower", "tongue". Mirror pairs throughout."""
    L1 = landmarks()
    T, gr, present, g = _groups()
    ns = L1["n_skin"]
    ids, mirror, region, names = [L1["gnm"]], [L1["mirror"][:ns]], list(L1["region"][:ns]), list(L1["names"][:ns])
    off = ns
    Q = np.asarray(g["quads"], int)

    def add(v, m, reg, tag):
        nonlocal off
        ids.append(np.asarray(v, int))
        mirror.append(off + np.asarray(m, int))
        region.extend([reg] * len(v))
        names.extend([f"{tag}_{int(x)}" for x in v])
        off += len(v)
    # eyes: the left eye's picks, the right eye's by mirror image
    iris = gr["irises"]
    q_iris = Q[iris[Q].any(1)]
    rim = np.zeros(len(T), bool)
    rim[q_iris[~iris[q_iris].all(1)].ravel()] = True
    rim &= iris                                             # iris vertices sharing a quad with the sclera
    from scipy.spatial import cKDTree
    eye_ids = []
    for side in ("left_eye", "right_eye"):
        m = gr[side] & gr["eye_interiors"] if "eye_interiors" in gr else gr[side]
        pv = np.where(m & gr["pupils"])[0]
        rv = np.where(m & rim)[0]
        eye_ids.append((pv, rv))
    pv, rv = eye_ids[0]
    c = T[np.where(gr["left_eye"] & iris)[0]].mean(0)
    pc = pv[int(np.argmin(np.linalg.norm(T[pv] - T[pv].mean(0), axis=1)))]
    ang = np.arctan2(T[rv, 1] - c[1], T[rv, 0] - c[0])
    ring = [int(rv[int(np.argmin(np.abs(np.angle(np.exp(1j * (ang - 2 * np.pi * k / LIMBUS_N))))))]) for k in range(LIMBUS_N)]
    left = np.array([pc] + ring)
    pv2, rv2 = eye_ids[1]
    cand = np.r_[pv2, rv2]
    _, j = cKDTree(T[cand]).query(T[left] * np.array([-1.0, 1.0, 1.0]))
    right = cand[j]
    n1 = len(left)
    add(np.r_[left, right], np.r_[n1 + np.arange(n1), np.arange(n1)], "eyeball", "eye")
    # teeth: each row's front arc
    for row, reg in (("upper_teeth_and_gums", "teeth_upper"), ("lower_teeth_and_gums", "teeth_lower")):
        tv = np.where(gr[row] & gr["teeth"])[0]
        tv = tv[T[tv, 2] > T[tv, 2].max() - TEETH_ARC]
        v, m = _sym_fps(T, tv, TEETH_HALF)
        add(v, m, reg, "tooth")
    # tongue: its upper surface, front half
    tv = np.where(gr["tongue"])[0]
    tv = tv[(T[tv, 2] > np.median(T[tv, 2])) & (T[tv, 1] > np.median(T[tv, 1]))]
    v, m = _sym_fps(T, tv, TONGUE_HALF)
    add(v, m, "tongue", "tongue")
    ids = np.concatenate(ids)
    return {"gnm": L1["gnm"], "gnm_all": ids, "region": np.array(region), "mirror": np.concatenate(mirror), "names": names,
            "extra": names[ns:], "n_skin": ns, "n": len(ids), "lm68": L1["lm68"], "version": 2,
            "eye": (ns, ns + 2 * n1), "left_eye": np.arange(ns, ns + n1), "right_eye": np.arange(ns + n1, ns + 2 * n1)}


BORDER_HALF = 9             # per half vermilion border / lip seam line (17 a line with the mid-line point)
NOSE_BASE_HALF = 26         # extra picks per half on the nose's lower third (alar rims and grooves, nostrils, columella, subnasale)
PHILTRUM_HALF = 8


@functools.lru_cache(maxsize=1)
def landmarks_v3() -> dict:
    """VERSION 3 (stage 1; after the pilot's lips and nose base sat off the features on real phone portraits while
    MediaPipe's sat on them): version 2 UNCHANGED and first, then the places where identity is fine-grained, as GNM
    vertices: the UPPER and LOWER VERMILION BORDER (the lip groups' edge against the skin: cupid's bow, mid-line dip,
    commissures: regions "lip_border_upper" / "lip_border_lower"), the LIP SEAM (the contact ring's two halves:
    "lip_seam"), the NOSE'S LOWER THIRD densely ("nose_base": alar rims, alar-facial grooves, nostril openings,
    columella, subnasale: farthest-point picks over every exterior nose vertex below the tip's level that set 2 does
    not hold) and the PHILTRUM ("philtrum": the upper-lip region between the nose and the border). Mirror pairs."""
    L2 = landmarks_v2()
    T, gr, present, g = _groups()
    from . import base as basemod, faceslide
    ext, skin = gr["skin_exterior"], np.asarray(g["skin"], bool)
    Q = np.asarray(g["quads"], int)
    e = np.r_[Q[:, [0, 1]], Q[:, [1, 2]], Q[:, [2, 3]], Q[:, [3, 0]]]
    e = np.r_[e, e[:, ::-1]]
    ids, mirror, region, names = [L2["gnm_all"]], [L2["mirror"]], list(L2["region"]), list(L2["names"])
    have = set(L2["gnm_all"].tolist())
    off = L2["n"]

    def add(cand, n_half, reg, tag):
        nonlocal off
        cand = np.array([v for v in np.unique(cand) if int(v) not in have and present[v]], int)
        if len(cand) < 2:
            return
        v, m = _sym_fps(T, cand, n_half)
        ids.append(v)
        mirror.append(off + m)
        region.extend([reg] * len(v))
        names.extend([f"{tag}_{int(x)}" for x in v])
        have.update(int(x) for x in v)
        off += len(v)
    for grp, reg in (("upper_lip", "lip_border_upper"), ("lower_lip", "lip_border_lower")):
        m = gr[grp] & ext
        add(e[m[e[:, 0]] & ~m[e[:, 1]] & ext[e[:, 1]] & skin[e[:, 1]], 0], BORDER_HALF, reg, "border")
    R = faceslide._lip_rings()
    C = np.asarray(R["rings"][R["contact"]], int)
    up = np.asarray(R["upper"], bool)[C]
    add(C[up], BORDER_HALF, "lip_seam", "seam")
    add(C[~up], BORDER_HALF, "lip_seam", "seam")
    nose = np.where(gr["nose_region"] & ext)[0]
    tip = nose[int(np.argmax(T[nose, 2]))]
    add(nose[T[nose, 1] < T[tip, 1] + 0.004], NOSE_BASE_HALF, "nose_base", "nose")
    ul = np.where(gr["upper_lip_region"] & ext & ~gr["upper_lip"])[0]
    add(ul[np.abs(T[ul, 0]) < 0.014], PHILTRUM_HALF, "philtrum", "philtrum")
    ids = np.concatenate(ids)
    out = dict(L2)
    out.update({"gnm_all": ids, "region": np.array(region), "mirror": np.concatenate(mirror), "names": names,
                "extra": names[L2["n_skin"]:], "n": len(ids), "version": 3, "n_v2": L2["n"]})
    return out


def current() -> dict:
    """the set new data is labelled with and new networks are trained on."""
    return landmarks_v3()


def by_count(n: int) -> dict:
    """the landmark set a network with n landmark outputs was trained on."""
    for L in (landmarks(), landmarks_v2(), landmarks_v3()):
        if L["n"] == n:
            return L
    raise ValueError(f"denselm: no landmark set of {n} landmarks (versions 1, 2, 3: {landmarks()['n']}, {landmarks_v2()['n']}, {landmarks_v3()['n']})")


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


DIST_UNIT = 1.2            # a stage-1 network's distance row: log(metres) / DIST_UNIT (spikes/denselm/train.py)


def _merge(o) -> tuple:
    """the crop's prediction and its mirror image's, joined by their own certainties: (xy in [-1, 1], log sigma, the
    landmark set, distance (m, its log's sigma) | None). The network's row count says which set it was trained on:
    588 = version 1 (the pilot); 623 + 1 = version 2 + the camera's distance (stage 1)."""
    rows = o.shape[1]
    dist = None
    if rows == landmarks()["n"]:
        L = landmarks()
    else:
        L = by_count(rows - 1)
        d = o[:, -1]
        w = np.exp(-2 * d[:, 2])
        dist = (float(np.exp(DIST_UNIT * (d[:, 0] * w).sum() / w.sum())), float(DIST_UNIT * np.sqrt(1.0 / w.mean())))
        o = o[:, :-1]
    xy, ls = o[0, :, :2], o[0, :, 2]
    xy2, ls2 = o[1][L["mirror"], :2] * np.array([-1.0, 1.0]), o[1][L["mirror"], 2]
    w1, w2 = np.exp(-2 * ls), np.exp(-2 * ls2)
    return (xy * w1[:, None] + xy2 * w2[:, None]) / (w1 + w2)[:, None], -0.5 * np.log((w1 + w2) / 2), L, dist


def predict(img, box, weights: str | None = None, passes: int = 2) -> dict:
    """The detector on a PIL picture. box: a rough square (x0, y0, x1, y1) round the face in picture pixels, or the 68
    standard landmarks' pixels from anything ((68, 2)); with passes=2 the crop is laid again on the network's own 68
    and read once more (no other detector's idea of the face stays in the result).
    -> {"xy": (L, 2) picture px, "sigma": (L,) picture px (large = unsure / hidden), "box": the crop used, "set": the
    landmark set (landmarks() or landmarks_v2(): the first n_skin rows are the same skin vertices in both),
    "distance": (metres from the camera to the head, the sigma of its log) from a stage-1 network, else None}."""
    w = weights or (str(weights_path()) if weights_path() else None)
    if not w:
        raise RuntimeError(f"denselm: no trained network (set ${WEIGHTS_ENV} to its model.pt)")
    box = np.asarray(box, float)
    box = box_of(box) if box.ndim == 2 else tuple(map(float, box))
    for k in range(max(1, passes)):
        xy, ls, L, dist = _merge(_run([take_crop(img, box)], w)[0])
        x0, y0, x1, y1 = box
        s = (x1 - x0) / 2.0
        P = np.stack([x0 + (xy[:, 0] + 1) * s, y0 + (xy[:, 1] + 1) * s], 1)
        res = {"xy": P, "sigma": np.exp(ls) * s, "box": box, "set": L, "distance": dist}
        if k + 1 < passes:
            box = box_of(P[L["lm68"]])
    return res
