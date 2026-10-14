"""Skin from PROJECTION (the `skin_project` tool): a model's fitted reference pictures laid into the head's own
texture space (the one human mesh's UV atlas, GNM's layout on the head), DE-LIT into albedo, the unseen filled, and
kept as two images the skin lays like any other paint: spec["skin"]["projection"] = {"albedo", "detail", "box", ...}
-> layers "skin:projection" (colour) and "skin:projection_detail" (fine relief), image wrap "uv" (images.py).

What each step does, and what it cannot know (the report says the same per model):
  PROJECT   per texel of the head's atlas and per picture: the picture's colour where its camera sees that skin (the
            view's own fitted camera and expression), the facing angle, and a confidence.
  EXCLUDE   what is not this skin: the picture's hair, clothing and backdrop (the picture's own parse: MediaPipe's
            multiclass segmenter, Apache 2.0; without it a colour rule), the lid margins (lashes, a misregistered eye),
            ears whose picture does not land on the model's ear (measured: the report says so), skin seen at a
            grazing angle.
  DE-LIGHT  picture = albedo x shading. The shading is what THIS head's geometry does under a low-frequency light:
            order-2 spherical harmonics through each texel's own visibility (so ambient occlusion and soft
            self-shadow are in it), plus one soft key light with its cast shadow, per picture and per colour channel,
            fitted on the face's plain skin with the albedo held smooth, then re-fitted against the views' agreed
            albedo (the same skin seen by two pictures has one albedo). What the fit explains is light and goes;
            everything else stays in the albedo: pigment (lips, brows, stubble shadow, freckles, redness), fine lines,
            AND the shading of forms the head does not have (a bag's shadow, a fold's dark side): that part is
            AMBIGUOUS, reported per region as "dark the light does not explain" (neutral = shadow-like, coloured =
            pigment-like), never silently called pigment.
  BLEND     the views' albedos by confidence in two bands (broad colour with wide weights, fine detail from the best
            view), so no seam and no double image.
  FILL      what no picture saw: the mirror image where the other side was seen (INFERRED, lower confidence), then
            OUR procedural skin (the model's own paint layers, evaluated at the texels) retoned to the projected skin
            around it and given fine texture of the projected skin's own statistics, so there is no patch edge.
  DETAIL    a relief map from the albedo's fine dark LINES where the picture is trusted (crow's feet, forehead and
            under-eye lines; coherent line bundles only: specks, hairs and freckles are pigment, not grooves).

  atlas(base)                  the head's texture space (texel -> triangle, barycentric)
  make(name, ...)              the whole pipeline -> {"albedo", "raw", "detail", "conf", "source", "report", ...}
  apply(name, out=None, ...)   make + files + spec["skin"]["projection"] saved
  lookup(spec, pos)            (u, v, weight) of surface points in the atlas (image wrap "uv")
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np

VERSION = 1
SIZE = 2048              # texels across the head's box of the atlas (~0.21 mm a texel)
PAD = 0.004              # atlas units round the head's faces
DEPTH_TOL = 0.002        # m: a texel is seen when it lies this near the camera's own depth buffer
FACE = (0.22, 0.7)       # cos(skin normal, way to the camera): no trust .. full
N_DIRS = 128             # directions of the visibility / light basis (a Fibonacci set over the sphere)
VIS_MM = 0.5             # mm per pixel of the visibility depth maps
KEY_DISC = 7.0           # deg: the key light's half-angle (soft shadow edges)
KEY_SHARE = 0.1          # ... and give this share of the plain skin's light (a "key" that lights nothing is noise)
KEY_GAIN = 0.03          # a key light must cut the fit's residual by this share to be kept
MU = 0.6                 # how far the lights' re-fit follows the views' agreed low-frequency albedo (0: flat skin)
LOW_MM = 6.0             # mm: "low frequency" of the albedo for the re-fit
BAND_MM = 1.2            # mm: the split between the broad band (wide weights) and the fine band (best view)
SHADE_FLOOR = 0.4        # shading under this share of a view's median is not divided out further (noise), and counts less
CAVITY_AO = 0.65         # a texel whose ambient occlusion is under this is one of the model's cavities (nostril, lip line)
CAVITY_MM = 2.5          # mm: "near" such a cavity (a Gaussian's sigma)
CAVITY_DARK = 0.62       # skin there under this x its surroundings (5 mm, same region) is a misplaced cavity's dark
DIP_MM = 3.0             # mm: "its surroundings" for the rule below
DIP = (0.75, 0.92)       # the fitted shading against its 3 mm surroundings: a crease of the MODEL from the second, fully one at the first
DIP_OVER = 1.05          # ... there the de-lit albedo may not exceed this x its own surroundings outside the crease
SHINE = (1.25, 0.3)      # a highlight: luminance over this x the local (1 cm) mean is compressed to this share
MIRROR_CONF = 0.45       # the mirrored side's confidence against a direct view's
EAR_BESIDE = 0.25        # an ear is left out when this share of the band beside the model's ear is skin in the picture
EAR_INSIDE = 0.75        # ... or under this share of the model's ear is
LID_BAND = 0.0013        # m: no picture this near the eyeball's surface (lashes, the margin; grows with the lids' misfit)
LID_OPEN = (0.0003, 0.0006)   # m from the eyeball: the image is transparent within the first, opaque from first + second (the
                         # wet line and caruncle are the live skin's; wider, our eyelid tint showed as a pink ring)
HAIR_GROW = 0.003        # m: the picture's hair grown by this (wisps, its shadow line)
SKIN_DE = 20.0           # (no parser) Lab distance from the picture's skin past which a texel above the brows is hair
OFF_SKIN = 42.0          # (no parser) ... past which a texel anywhere off the features is not skin
DETAIL_MM = (0.35, 0.9)  # mm: the line detector's scales (Gaussian sigmas)
DETAIL_DEPTH = 0.00012   # m: the relief of a full-strength line
INPAINT_MM = (1.5, 3.0, 6.0, 12.0)   # mm: holes are filled from the projected skin within these reaches, nearest first (a lid band, a
                         # nostril, a wisp, the hairline's first centimetre); beyond the last: our skin, retoned
LINE = (0.02, 0.06)      # a line's contrast (log luminance at its own scale): none .. full strength
DETAIL_LID = 0.006       # m: no detail this near the eyeball's surface (the lids)
COHERENT_MM = 2.5        # mm: lines count as grooves where their directions agree over this distance
Y = np.array([0.2126, 0.7152, 0.0722])


def _lin(c):
    c = np.asarray(c, float)
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def _srgb(lin):
    lin = np.clip(np.asarray(lin, float), 0, 1)
    return np.where(lin <= 0.0031308, lin * 12.92, 1.055 * lin ** (1 / 2.4) - 0.055)


def lab(lin):
    M = np.array([[0.4124564, 0.3575761, 0.1804375], [0.2126729, 0.7151522, 0.0721750], [0.0193339, 0.1191920, 0.9503041]])
    xyz = np.asarray(lin, float) @ M.T / np.array([0.95047, 1.0, 1.08883])
    f = np.where(xyz > 0.008856, np.cbrt(np.maximum(xyz, 1e-9)), 7.787 * xyz + 16 / 116)
    return np.stack([116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]), 200 * (f[..., 1] - f[..., 2])], -1)


def _sstep(x):
    x = np.clip(x, 0.0, 1.0)
    return x * x * (3 - 2 * x)


# ---------------------------------------------------------------- the atlas

_ATLAS: dict = {}


def _faces(tpl: dict) -> list:
    L, S = np.asarray(tpl["L"]), np.asarray(tpl["S"]) if "S" in tpl else None
    if S is None:
        return [L[i:i + 4] for i in range(0, len(L), 4)]
    out, o = [], 0
    for n in S:
        out.append(L[o:o + int(n)])
        o += int(n)
    return out


def vertex_uv(tpl: dict) -> tuple:
    """(candidates per template vertex: list of (k, 2) arrays, asset vertex index per template vertex or -1): the one
    mesh's atlas coordinates of a built template's vertices. A vertex on the atlas' cut has more than one."""
    from . import onemesh
    a = onemesh.asset()
    nraw = int(a["n_raw_v"])
    fid = np.asarray(tpl["fid"], int)
    skin = np.asarray(a["part"]) == 0
    cand: dict = {}
    for f, q in zip(np.asarray(a["faces"])[skin], np.asarray(a["uv"], float)[skin]):
        for v, t in zip(f, q):
            c = cand.setdefault(int(v), [])
            if not any(abs(t[0] - x[0]) + abs(t[1] - x[1]) < 1e-6 for x in c):
                c.append(t)
    out = [np.asarray(cand[int(i)], float) if int(i) in cand else None for i in fid]
    new = np.flatnonzero(fid >= nraw)
    if len(new):  # the lids' extra edge loops (onemesh._with_loops): each new vertex is the mean of its parents
        from . import gnmloops
        par = np.asarray(gnmloops.plan()["parents"], int)
        gid = np.asarray(a["gnm_id"], int)
        row = np.full(gnmloops.N_RAW + len(par), -1)
        old = np.flatnonzero((fid < nraw) & (fid >= 0))
        g = gid[fid[old]]
        row[g[g >= 0]] = old[g >= 0]
        row[gnmloops.N_RAW + (fid[new] - nraw)] = new
        for k in np.argsort(fid[new]):
            i = new[k]
            p = row[par[fid[i] - nraw]]
            if (p >= 0).all() and all(out[j] is not None for j in p):
                out[i] = np.mean([out[j][0] for j in p], 0)[None]
    return out, fid


def mesh_uv(base: dict) -> dict:
    """The head's mesh in the atlas, no raster: {"V" (template vertices at rest), "T" (the head's triangles), "uvT"
    (their atlas coordinates), "other" (the template's remaining triangles: body, mouth sock), "gid", "fid", "fade",
    "head", "is_new", "state"}."""
    from . import humanfit, onemesh
    key = hashlib.sha1(json.dumps([base, VERSION], sort_keys=True, default=str).encode()).hexdigest()
    if _MESH.get("key") == key:
        return _MESH["m"]
    st = humanfit.state(base)
    tpl = st["tpl"]
    a = onemesh.asset()
    V = np.asarray(tpl["P"], float)
    cand, fid = vertex_uv(tpl)
    nraw = int(a["n_raw_v"])
    gid = np.where((fid >= 0) & (fid < nraw), np.asarray(a["gnm_id"], int)[np.clip(fid, 0, nraw - 1)], -1)
    fade = np.where((fid >= 0) & (fid < nraw), np.asarray(a["fade"], float)[np.clip(fid, 0, nraw - 1)], 1.0)
    is_new = fid >= nraw
    headv = (gid >= 0) | is_new
    T, uvT, other = [], [], []
    for f in _faces(tpl):
        f = np.asarray(f, int)
        tri = [(f[0], f[j], f[j + 1]) for j in range(1, len(f) - 1)]
        if not headv[f].all() or any(cand[i] is None for i in f):
            other += tri
            continue
        one = [cand[i][0] for i in f if len(cand[i]) == 1]
        ref = np.mean(one, 0) if one else np.mean([c.mean(0) for c in (cand[i] for i in f)], 0)
        uv = np.array([cand[i][np.argmin(np.abs(cand[i] - ref).sum(1))] for i in f])
        if np.ptp(uv, 0).max() > 0.05:   # a face across the cut with no single-valued corner: not drawn
            other += tri
            continue
        for j in range(1, len(f) - 1):
            T.append((f[0], f[j], f[j + 1]))
            uvT.append((uv[0], uv[j], uv[j + 1]))
    m = {"V": V, "T": np.asarray(T, int), "uvT": np.asarray(uvT, float), "other": np.asarray(other, int).reshape(-1, 3), "gid": gid, "fid": fid,
         "fade": fade, "head": headv, "is_new": is_new, "state": st, "nraw": nraw}
    _MESH.clear()
    _MESH.update(key=key, m=m)
    return m


_MESH: dict = {}


def atlas(base: dict, size: int = SIZE) -> dict:
    """The head's texture space: the one mesh's atlas over the head's faces (GNM's skin layout), `size` texels across.
    {"shape": (H, W), "box": [u0, v0, u1, v1] (atlas units the image covers), "ii", "jj" (the valid texels' rows /
    columns), "tri" (their triangle), "bary", "T" (triangles: template vertex indices), "uvT" (triangles' atlas
    coordinates), "V" (template vertices at rest), "head" (vertex is the head's), "gid" (GNM vertex or -1), "fade",
    "mm" (mm per texel, median), per-vertex "groups" {name: weight}}. Image row 0 is the top (v = v1)."""
    from . import base as basemod, likeness as lk, onemesh
    key = hashlib.sha1(json.dumps([base, size, VERSION], sort_keys=True, default=str).encode()).hexdigest()
    if _ATLAS.get("key") == key:
        return _ATLAS["at"]
    mu = mesh_uv(base)
    a = onemesh.asset()
    st, V, T, uvT, gid, fid, fade, headv, is_new, nraw = (mu[k] for k in ("state", "V", "T", "uvT", "gid", "fid", "fade", "head", "is_new", "nraw"))
    fade = fade.copy()
    lo, hi = uvT.reshape(-1, 2).min(0) - PAD, uvT.reshape(-1, 2).max(0) + PAD
    W = int(size)
    H = int(round(size * (hi[1] - lo[1]) / (hi[0] - lo[0])))
    sx = ((uvT[..., 0] - lo[0]) / (hi[0] - lo[0]) * W).ravel()
    sy = ((hi[1] - uvT[..., 1]) / (hi[1] - lo[1]) * H).ravel()
    if not lk._RUN:
        lk._RUN.append(lk._raster())
    F = np.arange(3 * len(T)).reshape(-1, 3)
    bary = np.zeros((H, W, 3))
    zb = np.full((H, W), np.inf)
    lk._RUN[0](sx, sy, np.zeros(len(sx)), np.ascontiguousarray(F), np.tile(np.eye(3), (len(T), 1)), W, H, bary, zb)
    tid = np.zeros((H, W, 3))
    zb2 = np.full((H, W), np.inf)
    lk._RUN[0](sx, sy, np.zeros(len(sx)), np.ascontiguousarray(F), np.repeat(np.arange(len(T), dtype=float), 3)[:, None] * np.ones(3), W, H, tid, zb2)
    ii, jj = np.nonzero(np.isfinite(zb))
    b = bary[ii, jj]
    b /= b.sum(1, keepdims=True)
    tri = np.round(tid[ii, jj, 0]).astype(int)
    G = basemod._gnm_data()["groups"]
    groups = {}
    for k, g in G.items():
        g = np.asarray(g, float)
        groups[k] = np.where(gid >= 0, g[np.clip(gid, 0, len(g) - 1)], 0.0)
    for k in list(groups):   # the lids' new loop vertices take their neighbours' groups
        if is_new.any():
            pass
    e3 = np.linalg.norm(V[T[:, 1]] - V[T[:, 0]], axis=1)
    e2 = np.linalg.norm((uvT[:, 1] - uvT[:, 0]) / (hi - lo) * [W, H], axis=1)
    at = {"shape": (H, W), "box": [float(lo[0]), float(lo[1]), float(hi[0]), float(hi[1])], "ii": ii, "jj": jj, "tri": tri,
          "bary": b, "T": T, "uvT": uvT, "V": V, "head": headv, "gid": gid, "fid": fid, "fade": fade, "groups": groups,
          "mm": float(np.median(1000 * e3 / np.maximum(e2, 1e-9))), "state": st, "key": key[:12],
          "neutral": np.asarray(a["neutral"], float)[np.clip(fid, 0, nraw - 1)] if True else None, "is_new": is_new}
    if is_new.any():   # new loop vertices: neutral position and groups from the nearest old head vertex at rest
        from scipy.spatial import cKDTree
        old = np.flatnonzero(headv & ~is_new)
        nn = old[cKDTree(V[old]).query(V[is_new])[1]]
        at["neutral"][is_new] = at["neutral"][nn] + (V[is_new] - V[nn])
        for k in groups:
            groups[k][is_new] = groups[k][nn]
        at["fade"][is_new] = fade[nn]
    _ATLAS.clear()
    _ATLAS.update(key=key, at=at)
    return at


def interp(at: dict, A: np.ndarray) -> np.ndarray:
    """A per-vertex array at the valid texels."""
    A = np.asarray(A, float)
    t, b = at["T"][at["tri"]], at["bary"]
    if A.ndim == 1:
        return (A[t] * b).sum(1)
    return (A[t] * b[:, :, None]).sum(1)


def image(at: dict, vals: np.ndarray, fill=0.0) -> np.ndarray:
    """Valid-texel values as an (H, W[, c]) image."""
    vals = np.asarray(vals)
    out = np.full(at["shape"] + vals.shape[1:], fill, vals.dtype if vals.dtype != bool else bool)
    out[at["ii"], at["jj"]] = vals
    return out


def _blur(at: dict, vals: np.ndarray, w: np.ndarray | None, mm: float) -> np.ndarray:
    """A masked Gaussian of valid-texel values across the atlas (sigma in mm; weights w, default 1): the weighted
    local mean, at the valid texels. Where no weight is within reach the value stays."""
    from scipy import ndimage
    sg = mm / at["mm"]
    w = np.ones(len(vals)) if w is None else np.asarray(w, float)
    Wm = image(at, w.astype(np.float32))
    den = ndimage.gaussian_filter(Wm, sg)[at["ii"], at["jj"]]
    if vals.ndim == 1:
        num = ndimage.gaussian_filter(image(at, (vals * w).astype(np.float32)), sg)[at["ii"], at["jj"]]
        return np.where(den > 1e-4, num / np.maximum(den, 1e-4), vals)
    out = np.empty_like(vals, dtype=float)
    for c in range(vals.shape[1]):
        num = ndimage.gaussian_filter(image(at, (vals[:, c] * w).astype(np.float32)), sg)[at["ii"], at["jj"]]
        out[:, c] = np.where(den > 1e-4, num / np.maximum(den, 1e-4), vals[:, c])
    return out


def _normals(at: dict, V: np.ndarray) -> np.ndarray:
    from . import likeness as lk
    return lk._vertex_normals(V, at["_Fall"]) if "_Fall" in at else lk._vertex_normals(V, at["T"])


# ---------------------------------------------------------------- one picture onto the atlas

def sample_view(at: dict, mesh: dict, cam: dict, photo: np.ndarray, maps: dict | None = None) -> dict:
    """One picture at the atlas' texels through its fitted camera. mesh: likeness.model_mesh of the view's own base
    (its expression). photo: (h, w, 3) sRGB 0..255. maps: {name: (h, w) picture-pixel maps} sampled the same way.
    Returns {"rgb" (n, 3) linear, "vis" (seen by the camera), "facing" (cos), "X", "N" (world), "uv" (picture px),
    "mm" (the picture's mm per pixel at the head), "maps": {name: (n,)}, "clip" (a channel clipped)}."""
    from . import humanfit, likeness as lk
    from .likeness_read import PROJECT_TOL
    V = np.asarray(mesh["V"], float)
    X = interp(at, V)
    N = interp(at, lk._vertex_normals(V, np.asarray(mesh["F"])))
    N /= np.maximum(np.linalg.norm(N, axis=1, keepdims=True), 1e-12)
    w, h = cam["size"]
    R = humanfit._cam_rot(cam)
    Xc = (X - np.asarray(cam["centre"], float)) @ R.T + np.asarray(cam["t"], float)
    us, vs = cam["f"] * Xc[:, 0] / Xc[:, 2] + w / 2, cam["f"] * Xc[:, 1] / Xc[:, 2] + h / 2
    spx = int(min(max(w, h), 2000))
    _, ks, sp = lk.render(mesh, cam, (0.0, 0.0, float(w), float(h)), px=spx, brows=False, passes=True)
    zs = sp["zb"]
    a, b = np.round(vs * ks - 0.5).astype(int), np.round(us * ks - 0.5).astype(int)
    inside = (a >= 0) & (a < zs.shape[0]) & (b >= 0) & (b < zs.shape[1]) & (us >= 0.5) & (us < w - 1.5) & (vs >= 0.5) & (vs < h - 1.5) & (Xc[:, 2] > 0.01)
    vis = np.zeros(len(X), bool)
    vis[inside] = Xc[inside, 2] < zs[a[inside], b[inside]] + min(PROJECT_TOL, DEPTH_TOL)
    to_cam = -(Xc / np.linalg.norm(Xc, axis=1, keepdims=True)) @ R
    facing = (N * to_cam).sum(1)
    vis &= facing > 0.02

    def bil(img):
        img = np.asarray(img)
        u_, v_ = np.clip(us, 0, w - 1.001), np.clip(vs, 0, h - 1.001)
        x0, y0 = np.floor(u_).astype(int), np.floor(v_).astype(int)
        fx, fy = u_ - x0, v_ - y0
        if img.ndim == 3:
            fx, fy = fx[:, None], fy[:, None]
        return (img[y0, x0] * (1 - fx) * (1 - fy) + img[y0, x0 + 1] * fx * (1 - fy) + img[y0 + 1, x0] * (1 - fx) * fy
                + img[y0 + 1, x0 + 1] * fx * fy)
    ph = np.asarray(photo, float)
    col = bil(ph)
    zc = float(np.median(Xc[vis, 2])) if vis.any() else float(cam["t"][2])
    return {"rgb": _lin(col / 255.0).astype(np.float32), "vis": vis, "facing": facing.astype(np.float32), "X": X.astype(np.float32),
            "N": N.astype(np.float32), "uv": np.c_[us, vs].astype(np.float32),
            "mm": 1000.0 * zc / cam["f"], "maps": {k: bil(m).astype(np.float32) for k, m in (maps or {}).items()},
            "clip": (col.max(1) > 250) | (col.max(1) < 6), "zb": zs, "ks": ks}


# ---------------------------------------------------------------- what is not this skin

def _picture_maps(img, cam, mesh, parse: str | None) -> dict:
    """The picture's own parse as picture-pixel probability maps {"skin", "hair", "cloth", "figure"} ({} without a
    parser). parse: "mediapipe" (Apache 2.0: the default, its masks decide what ships) | "bisenet" (trained on
    CelebAMask-HQ, non-commercial data: a MEASURING tool, for comparison only) | None (the colour rule)."""
    if not parse:
        return {}
    from . import faceparse
    try:
        if not faceparse.available():
            return {}
        g = faceparse.masks(img, cam, mesh, model=parse)[2]
    except Exception:  # noqa: BLE001
        return {}
    return {k: np.asarray(g[k], np.float32) for k in ("skin", "hair", "cloth", "figure", "ears") if k in g}


WISP_NEAR = 0.03         # m: loose hairs are looked for this near the parser's hair
WISP_MM = 0.45           # mm: a hair's half-width as the line detector sees it
WISP_DARK = 0.07         # a line this much darker (log luminance, at its own scale) than its sides is a hair


VEIL_NEAR = 0.012        # m: a veil of hair / its shadow is looked for this near the parser's hair
VEIL_DARK = 0.35         # ... where the skin is this much darker (log luminance, 1.5 mm mean) than the skin away from the hair


def _wisps(photo: np.ndarray, hair: np.ndarray, mpp: float, skin: np.ndarray | None = None) -> np.ndarray:
    """Loose hairs over skin in a picture ((h, w) 0..1): thin dark lines within WISP_NEAR of the parser's hair, grown
    by a millimetre. (The parser's hair mask ends where the hair is solid: Tess's temple and nape wisps went on as skin.)"""
    from scipy import ndimage
    lum = np.log(np.maximum(_lin(np.asarray(photo, float) / 255.0) @ Y, 1e-3)).astype(np.float32)
    s = max(WISP_MM / 1000.0 / mpp, 0.8)
    hxx = ndimage.gaussian_filter(lum, s, order=(0, 2)) * s * s
    hyy = ndimage.gaussian_filter(lum, s, order=(2, 0)) * s * s
    hxy = ndimage.gaussian_filter(lum, s, order=(1, 1)) * s * s
    tr, df = hxx + hyy, np.sqrt((hxx - hyy) ** 2 + 4 * hxy ** 2)
    line = np.clip(0.5 * (tr + df) - np.abs(0.5 * (tr - df)), 0, None)
    near = ndimage.maximum_filter(hair, 2 * max(int(WISP_NEAR / mpp / 4), 1) + 1)
    near = ndimage.zoom(ndimage.maximum_filter(near[::4, ::4], 9), 4, order=1)[:hair.shape[0], :hair.shape[1]] if min(hair.shape) > 64 else near
    if near.shape != hair.shape:
        near = np.pad(near, ((0, hair.shape[0] - near.shape[0]), (0, hair.shape[1] - near.shape[1])), mode="edge")
    w = _sstep((line - 0.5 * WISP_DARK) / WISP_DARK) * (near > 0.3)
    k = max(int(round(0.001 / mpp)), 1)
    w = ndimage.gaussian_filter(ndimage.maximum_filter(w, 2 * k + 1), k * 0.5)
    # a veil of hair or its shadow: skin within VEIL_NEAR of the hair much darker than the picture's skin away from it
    kv = max(int(round(VEIL_NEAR / mpp / 4)), 1)
    nv = ndimage.maximum_filter(hair[::4, ::4], 2 * kv + 1)
    nv = np.kron(nv, np.ones((4, 4), np.float32))[:hair.shape[0], :hair.shape[1]]
    if nv.shape != hair.shape:
        nv = np.pad(nv, ((0, hair.shape[0] - nv.shape[0]), (0, hair.shape[1] - nv.shape[1])), mode="edge")
    if skin is not None and ((skin > 0.7) & (nv < 0.1)).sum() > 500:
        ref = float(np.median(lum[(skin > 0.7) & (nv < 0.1)]))
        lo = ndimage.gaussian_filter(lum, 0.0015 / mpp)
        w = np.maximum(w, _sstep((ref - lo - 0.6 * VEIL_DARK) / (0.8 * VEIL_DARK)) * (nv > 0.3))
    return w.astype(np.float32)


STRAND_MM = 8.0          # mm: a dark thin line this long, connected to the parser's hair, is a strand of hair wherever it runs


def _strands(photo: np.ndarray, hair: np.ndarray, mpp: float) -> np.ndarray:
    """Long strands of hair lying across the face ((h, w) 0..1): connected thin dark lines that TOUCH the parser's hair
    (grown 3 mm) and run on at least STRAND_MM, followed however far they run, grown by a millimetre. Unlike _wisps, no
    region keeps them (a strand down a test head's cheek beside her nose crossed the orbital and nose regions, where wisps
    are kept for the lids' and nostrils' own lines, and went on as a dark streak in her skin)."""
    from scipy import ndimage
    lum = np.log(np.maximum(_lin(np.asarray(photo, float) / 255.0) @ Y, 1e-3)).astype(np.float32)
    s = max(WISP_MM / 1000.0 / mpp, 0.8)
    hxx = ndimage.gaussian_filter(lum, s, order=(0, 2)) * s * s
    hyy = ndimage.gaussian_filter(lum, s, order=(2, 0)) * s * s
    hxy = ndimage.gaussian_filter(lum, s, order=(1, 1)) * s * s
    tr, df = hxx + hyy, np.sqrt((hxx - hyy) ** 2 + 4 * hxy ** 2)
    line = np.clip(0.5 * (tr + df) - np.abs(0.5 * (tr - df)), 0, None) > WISP_DARK
    lab, nl = ndimage.label(line, structure=np.ones((3, 3)))
    if nl == 0:
        return np.zeros(hair.shape, np.float32)
    g3 = max(int(round(0.003 / mpp)), 1)
    near = ndimage.maximum_filter((hair > 0.5).astype(np.uint8), 2 * g3 + 1) > 0
    touch = np.zeros(nl + 1, bool)
    touch[np.unique(lab[near & line])] = True
    sl = ndimage.find_objects(lab)
    keep = np.zeros(nl + 1, bool)
    for i, b in enumerate(sl, start=1):
        if b is None or not touch[i]:
            continue
        ext = float(np.hypot(b[0].stop - b[0].start, b[1].stop - b[1].start)) * mpp * 1000.0
        keep[i] = ext >= STRAND_MM
    keep[0] = False
    m = keep[lab] & ~(hair > 0.5)
    k = max(int(round(0.001 / mpp)), 1)
    return ndimage.gaussian_filter(ndimage.maximum_filter(m.astype(np.float32), 2 * k + 1), k * 0.5).astype(np.float32)


def exclude(at: dict, s: dict, mesh: dict, cam: dict, img, view: dict, parse: str | None = "mediapipe", ears: bool = False) -> tuple:
    """(ok (n,) 0..1: this texel's picture pixel IS this skin, notes). s: sample_view's (with the parse maps)."""
    from scipy import ndimage
    from scipy.spatial import cKDTree
    from . import humanfit
    n = len(s["vis"])
    seen = s["vis"] & (s["facing"] > FACE[0])
    ok = np.ones(n)
    notes: dict = {"parser": parse if s["maps"] else None}
    L = np.asarray(mesh["L"], float)
    if s["maps"]:
        mp = s["maps"]
        not_skin = 1 - _sstep((mp["skin"] - 0.35) / 0.3)
        hair = _sstep((mp.get("hair_grown", mp["hair"]) - 0.25) / 0.4)
        if "wisp" in mp:   # loose hairs the parser calls skin: dark thin lines near its hair; never on brows, lids, lips
            g = at["groups"]
            keep = np.max([interp(at, g[k]) for k in ("left_brow_region", "right_brow_region", "middle_brow_region", "upper_lip", "lower_lip",
                                                    "left_orbital_region", "right_orbital_region", "nose_region")], 0) > 0.2
            hair = np.maximum(hair, np.where(keep, 0.0, _sstep((mp["wisp"] - 0.3) / 0.4)))
        if "strand" in mp:   # long strands connected to the hair: excluded wherever they run (but the brows: bangs
            g = at["groups"]   # touching a brow would take the brow's hairs with them)
            kb = np.max([interp(at, g[k]) for k in ("left_brow_region", "right_brow_region", "middle_brow_region")], 0) > 0.2
            hair = np.maximum(hair, np.where(kb, 0.0, _sstep((mp["strand"] - 0.3) / 0.4)))
        cloth = _sstep((mp["cloth"] - 0.3) / 0.4) if "cloth" in mp else np.zeros(n)
        bg = _sstep((0.6 - mp["figure"]) / 0.3)
        ok *= (1 - not_skin) * (1 - hair) * (1 - cloth) * (1 - bg)
        tot = max(int(seen.sum()), 1)
        notes["rejected"] = {"hair": round(float((seen & (hair > 0.5)).sum() / tot), 3),
                             "clothing": round(float((seen & (cloth > 0.5) & (hair <= 0.5)).sum() / tot), 3),
                             "backdrop": round(float((seen & (bg > 0.5) & (hair <= 0.5) & (cloth <= 0.5)).sum() / tot), 3),
                             "other": round(float((seen & (not_skin > 0.5) & (hair <= 0.5) & (cloth <= 0.5) & (bg <= 0.5)).sum() / tot), 3)}
    else:  # no parser: the picture's own skin colour (likeness_texture's rule)
        lb = lab(s["rgb"])
        core = seen & (s["facing"] > 0.8) & (interp(at, at["groups"]["hockey_mask"]) > 0.5)
        skin_lab = np.median(lb[core], 0) if core.sum() > 50 else np.array([65.0, 12.0, 18.0])
        de = np.linalg.norm((lb - skin_lab) * np.array([0.7, 1.0, 1.0]), axis=1)
        brow_z = float(L[17:27, 2].mean())
        hairy = (s["X"][:, 2] > brow_z + 0.012) & (de > SKIN_DE)
        dfeat = cKDTree(L[17:68]).query(s["X"])[0]
        ok *= ~hairy & ~((dfeat > 0.02) & (de > OFF_SKIN))
        notes["rejected"] = {"by colour": round(float((seen & (ok < 0.5)).sum() / max(int(seen.sum()), 1)), 3)}
    # the lid margins: nothing within a band of the eyeball (the picture's lashes, wet line, a lid that sits elsewhere)
    band = LID_BAND
    try:
        from . import blockin as bi
        P = bi.detect_view(img, view)
        if P is not None:
            Pm = humanfit.project(cam, L[:68])
            from . import likeness as lk
            P = np.asarray(P, float)
            P = P[np.asarray(lk.MP68)] if len(P) > 68 else P
            res = np.linalg.norm(P[36:48, :2] - Pm[36:48], axis=1)
            mis = float(np.sqrt(np.mean(res ** 2))) * s["mm"] / 1000.0
            notes["lid_misfit_mm"] = round(1000 * mis, 2)
            band = float(np.clip(1.2 * mis, LID_BAND, 0.004))
    except Exception:  # noqa: BLE001
        pass
    notes["lid_band_mm"] = round(1000 * band, 2)
    for Ve, _, _ in mesh["eyes"]:
        c = Ve.mean(0)
        r = float(np.linalg.norm(Ve - c, axis=1).max())
        d = np.linalg.norm(s["X"] - c, axis=1) - r
        ok *= _sstep((d - band) / band)
    # the ears: only when asked for, and only when the picture's ear lands on the model's
    ear = interp(at, at["groups"]["ears"]) > 0.35
    ev = np.flatnonzero((at["groups"]["ears"] > 0.5) & at["head"])
    near_ear = cKDTree(np.asarray(mesh["V"])[ev]).query(s["X"])[0] if len(ev) else np.full(n, 1.0)
    keep_ear = False
    if ears and (seen & ear).sum() > 200 and s["maps"]:
        inside = float((s["maps"]["skin"][seen & ear] > 0.5).mean())
        zb, ks = s["zb"], s["ks"]
        m = np.zeros(zb.shape, bool)
        q = seen & ear
        a_, b_ = np.round(s["uv"][q, 1] * ks - 0.5).astype(int), np.round(s["uv"][q, 0] * ks - 0.5).astype(int)
        m[np.clip(a_, 0, zb.shape[0] - 1), np.clip(b_, 0, zb.shape[1] - 1)] = True
        ring = ndimage.binary_dilation(m, iterations=max(int(0.010 / (s["mm"] / 1000.0) * ks), 2)) & ~np.isfinite(zb)
        from PIL import Image
        sk = np.asarray(Image.fromarray((np.clip(s["_skin_map"], 0, 1) * 255).astype(np.uint8)).resize((zb.shape[1], zb.shape[0]), Image.BILINEAR)) > 127
        beside = float(sk[ring].mean()) if ring.sum() > 50 else 0.0
        keep_ear = inside >= EAR_INSIDE and beside <= EAR_BESIDE
        notes["ear"] = {"inside": round(inside, 2), "beside": round(beside, 2), "projected": bool(keep_ear)}
    elif (seen & ear).sum() > 200:
        notes["ear"] = {"projected": False, "why": "ears are left to the procedural skin unless asked for (ears=True)"}
    if not keep_ear:
        ok *= _sstep((near_ear - 0.002) / 0.006)
    return ok, notes


# ---------------------------------------------------------------- light

def _dirs(n: int = N_DIRS) -> np.ndarray:
    k = np.arange(n) + 0.5
    th = np.arccos(1 - 2 * k / n)
    ph = np.pi * (1 + 5 ** 0.5) * k
    return np.c_[np.sin(th) * np.cos(ph), np.sin(th) * np.sin(ph), np.cos(th)]


def transfer(mesh: dict, X: np.ndarray, N: np.ndarray, sub: np.ndarray | None = None, n_dirs: int = N_DIRS) -> dict:
    """The head's light transport at points: {"T" (n, 9): irradiance per unit of each order-2 SH coefficient of the
    light, through each point's own visibility (self-shadow and occlusion in it), "ao" (n,), "D" (directions),
    "sub_vis" (D, m) the visibility of the points `sub` per direction (the key light's search)}."""
    from . import likeness as lk
    Vo, Fo = lk._occluders(mesh)
    D = _dirs(n_dirs)
    Yk = lk.sh9(D)
    T = np.zeros((len(X), 9), np.float32)
    num, den = np.zeros(len(X), np.float32), np.zeros(len(X), np.float32)
    sv = np.zeros((n_dirs, len(sub)), bool) if sub is not None else None
    pos = np.full(len(X), -1)
    if sub is not None:
        pos[sub] = np.arange(len(sub))
    for k, d in enumerate(D):
        c = N @ d
        up = np.flatnonzero(c > 0)
        if not len(up):
            continue
        dm = lk._DepthMap(Vo, Fo, d, VIS_MM)
        vis = dm.lit(X[up], N[up])
        cv = (c[up] * vis).astype(np.float32)
        T[up] += cv[:, None] * Yk[k].astype(np.float32)
        num[up] += cv
        den[up] += c[up].astype(np.float32)
        if sv is not None:
            q = pos[up]
            sv[k, q[q >= 0]] = vis[q >= 0]
    T *= 4.0 / n_dirs
    return {"T": T, "ao": num / np.maximum(den, 1e-6), "D": D, "sub_vis": sv}


def key_basis(mesh: dict, X: np.ndarray, N: np.ndarray, d, disc: float = KEY_DISC) -> np.ndarray:
    """A soft key light's irradiance at points (cos x the share of its disc that sees the point)."""
    from . import likeness as lk
    Vo, Fo = lk._occluders(mesh)
    d = np.asarray(d, float) / np.linalg.norm(d)
    a = np.cross(d, [1.0, 0, 0] if abs(d[0]) < 0.9 else [0, 1.0, 0])
    a /= np.linalg.norm(a)
    b = np.cross(d, a)
    r = np.tan(np.radians(disc)) * 0.75
    ds = [d] + [d + r * (np.cos(t) * a + np.sin(t) * b) for t in np.arange(8) * np.pi / 4]
    c = np.clip(N @ d, 0, None)
    up = np.flatnonzero(c > 0)
    v = np.zeros(len(up))
    for q in ds:
        v += lk._DepthMap(Vo, Fo, q / np.linalg.norm(q), VIS_MM).lit(X[up], N[up])
    out = np.zeros(len(X), np.float32)
    out[up] = c[up] * v / len(ds)
    return out


def _irls(A: np.ndarray, r: np.ndarray, w: np.ndarray, rounds: int = 6, k: float = 0.12, ridge: float = 1e-4) -> tuple:
    """Robust weighted least squares r ~ A x (Huber on the residual relative to the prediction). (x, rms)."""
    ww = w.copy()
    x = np.zeros(A.shape[1])
    for _ in range(rounds):
        Aw = A * ww[:, None]
        x = np.linalg.solve(A.T @ Aw + ridge * np.eye(A.shape[1]) * float(ww.sum()), Aw.T @ r)
        p = A @ x
        e = (r - p) / np.maximum(np.abs(p), 0.05 * float(np.median(np.abs(r))))
        ww = w * np.where(np.abs(e) <= k, 1.0, k / np.maximum(np.abs(e), 1e-9))
    p = A @ x
    e = (r - p) / np.maximum(np.abs(p), 0.05 * float(np.median(np.abs(r))))
    return x, float(np.sqrt(np.sum(ww * e ** 2) / max(float(ww.sum()), 1e-9)))


def fit_light(view: dict, target: np.ndarray, fit: np.ndarray, key: bool = True, key_dir=None, mesh=None, colour_w: np.ndarray | None = None) -> dict:
    """One picture's light against a target albedo: view = {"rgb", "T", "sub", "sub_vis", "D", "X", "N"}; target
    (n, 3) linear albedo; fit: indices of the texels fitted (trusted plain skin). Returns {"sh" (3, 9), "key":
    {"dir", "rgb"} | None, "S" (n, 3) the shading at every texel, "rms": relative residual on luminance, "rms0":
    without the key, "ambient" / "directional": shares}."""
    T = view["T"]
    r = view["rgb"][fit] / np.maximum(target[fit], 1e-4)
    rY = r @ Y
    w = np.ones(len(fit))
    A = T[fit].astype(float)
    x0, rms0 = _irls(A, rY, w)
    kd, kb_fit, best = None, None, rms0
    if key_dir is not None:
        kd = np.asarray(key_dir, float)
    elif key and view.get("sub_vis") is not None:
        # the search: each direction of the set as a soft key (its neighbours' visibility averaged), on the fit texels
        pos = np.full(len(T), -1)
        pos[view["sub"]] = np.arange(len(view["sub"]))
        q = pos[fit]
        has = q >= 0
        if has.sum() > 500:
            D = view["D"]
            sv = view["sub_vis"][:, q[has]]
            Nf = view["N"][fit][has]
            Af, rf = A[has], rY[has]
            G = Af.T @ Af + 1e-4 * np.eye(9) * has.sum()
            base = float(np.sum((rf - Af @ np.linalg.solve(G, Af.T @ rf)) ** 2))
            cosn = np.cos(np.radians(2.2 * KEY_DISC))
            res = []
            for k, d in enumerate(D):
                nb = np.flatnonzero(D @ d > cosn)
                b = sv[nb].mean(0) * np.clip(Nf @ d, 0, None)
                if b.sum() < 0.02 * len(b):
                    res.append(np.inf)
                    continue
                A2 = np.c_[Af, b]
                x = np.linalg.solve(A2.T @ A2 + 1e-4 * np.eye(10) * has.sum(), A2.T @ rf)
                res.append(float(np.sum((rf - A2 @ x) ** 2)) if x[9] > 0 else np.inf)
            k = int(np.argmin(res))
            if res[k] < (1 - KEY_GAIN) ** 2 * base:
                # refine between the set's directions: the residual-weighted mean of the best few neighbours
                nb = np.flatnonzero(D @ D[k] > np.cos(np.radians(16)))
                wq = np.array([max(base - res[j], 0.0) if np.isfinite(res[j]) else 0.0 for j in nb]) ** 2
                kd = (D[nb] * wq[:, None]).sum(0)
                kd /= np.linalg.norm(kd)
    kb = None
    if kd is not None:
        kb = view["key_b"] if view.get("key_b") is not None and view.get("key_dir") is not None and np.allclose(view["key_dir"], kd) else key_basis(mesh, view["X"], view["N"], kd)
        view["key_b"], view["key_dir"] = kb, kd
        kb_fit = kb[fit].astype(float)
        A2 = np.c_[A, kb_fit]
        x1, rms1 = _irls(A2, rY, w)
        share = float(np.median(kb_fit) * x1[9]) / max(float(np.median(A2 @ x1)), 1e-9)
        if x1[9] <= 0 or (key_dir is None and (rms1 > (1 - KEY_GAIN) * rms0 or share < KEY_SHARE)):
            kd, kb = None, None
            view["key_dir"] = None
        else:
            best = rms1
    sh, krgb = np.zeros((3, 9)), np.zeros(3)
    Af = A if kd is None else np.c_[A, kb_fit]
    # the light's COLOUR is fitted only where the skin is the tone it is taken to be: colour_w (per fit texel) is 0 on
    # the beard zones (a beard's shadow is greyer and bluer than the tone: with it in the fit a front view's light came
    # out cyan and the head, rendered under that light, green beside a neutral photograph)
    wc = w if colour_w is None or float(np.sum(colour_w)) < 1500 else w * colour_w
    for c in range(3):
        x, _ = _irls(Af, r[:, c], wc)
        sh[c] = x[:9]
        if kd is not None:
            krgb[c] = max(x[9], 0.0)
    S = T.astype(float) @ sh.T
    amb = float(np.median((T[fit].astype(float) @ sh.T) @ Y))
    if kd is not None:
        S = S + kb[:, None].astype(float) * krgb
    direct = float(np.median(kb_fit) * (krgb @ Y)) if kd is not None else 0.0
    return {"sh": sh, "key": {"dir": [round(float(v), 4) for v in kd], "rgb": [round(float(v), 4) for v in krgb]} if kd is not None else None,
            "S": S, "rms": best, "rms0": rms0, "ambient_share": round(amb / max(amb + direct, 1e-9), 3)}


# ---------------------------------------------------------------- ours

def ours_albedo(at: dict, spec: dict, stride: int = 4, log=print) -> np.ndarray:
    """OUR skin's albedo (the model's own paint layers, no projection) at the atlas' texels: evaluated on every
    `stride`-th texel (skin_read.Albedo, in Python) and interpolated: (n, 3) linear."""
    import copy
    from scipy import ndimage
    from . import likeness as lk, skin_read
    sp = copy.deepcopy(spec)
    (sp.get("skin") or {}).pop("projection", None)
    # nor the measured STACK (made from an earlier atlas): taken as "ours", each new atlas was retoned to the last stack's
    # colour, and a head re-projected after a form change drifted greyer every pass (an older head's g / b 1.13 -> 1.10 -> 1.08;
    # the photo's 1.17)
    (sp.get("skin") or {}).pop("stack", None)
    (sp.get("skin") or {}).pop("only", None)
    st = skin_read.stage_spec(sp)
    H, W = at["shape"]
    sel = np.flatnonzero((at["ii"] % stride == stride // 2) & (at["jj"] % stride == stride // 2))
    V = at["V"]
    X = interp(at, V)[sel]
    Nv = lk._vertex_normals(V, at["T"])
    N = interp(at, Nv)[sel]
    N /= np.maximum(np.linalg.norm(N, axis=1, keepdims=True), 1e-12)
    A = skin_read.Albedo(st, X, N, log=log)()
    h, w = (H + stride - 1) // stride, (W + stride - 1) // stride
    C = np.zeros((h, w, 3))
    M = np.zeros((h, w), bool)
    ci, cj = at["ii"][sel] // stride, at["jj"][sel] // stride
    C[ci, cj] = A
    M[ci, cj] = True
    idx = ndimage.distance_transform_edt(~M, return_distances=False, return_indices=True)
    C = C[idx[0], idx[1]]
    yy = (at["ii"] - stride // 2) / stride
    xx = (at["jj"] - stride // 2) / stride
    return np.stack([ndimage.map_coordinates(C[..., c], [yy, xx], order=1, mode="nearest") for c in range(3)], 1)


# ---------------------------------------------------------------- the eyes

IRIS_YAW = 35.0          # deg: irises are read in views turned no further than this
IRIS_PX = 12.0           # the limbus' radius in pixels under which an eye is not read
EYE_RING = ((33, 246, 161, 160, 159, 158, 157, 173, 133, 155, 154, 153, 145, 144, 163, 7),          # MediaPipe: the lid margins'
            (263, 466, 388, 387, 386, 385, 384, 398, 362, 382, 381, 380, 374, 373, 390, 249))       # closed contour, subject's right, left
IRIS_BINS = np.linspace(0.0, 1.2, 25)
IRIS_ZONES = {"inner": (0.0, 0.55), "outer": (0.6, 0.86), "limbal": (0.9, 1.0)}   # shares of the limbus radius (inner starts at the pupil's edge)


def iris_profile(img, view: dict) -> dict | None:
    """The irises of one picture as a radial read at the picture's OWN limbus (blockin_eyes.limbus: MediaPipe's ring
    under-reads it), over the pixels INSIDE the lid margins' contour (the detector's own lid points, drawn in by a
    pixel: no lid skin, whatever the hooding; a fixed sector took lid skin on a hooded eye), both eyes pooled, the
    brightest 15 % of each ring (catch lights) and the darkest 10 % (lash shadow, the lid's edge) left out:
    {"r": bin centres (share of the limbus radius), "rgb": (bins, 3) linear medians, "n", "radius_px", "pupil": the
    pupil's edge (the steepest dark -> light step inside 0.15-0.6), "open": the share of the iris disc the lids leave};
    None without a detection or under IRIS_PX."""
    from PIL import Image, ImageDraw
    from . import blockin as bi, blockin_eyes as be
    P = bi.detect_view(img, view)
    if P is None or len(P) < 478:
        return None
    P = np.asarray(P, float)[:, :2]
    try:
        lb = be.limbus(img, P)
    except Exception:  # noqa: BLE001
        return None
    a = _lin(np.asarray(img.convert("RGB"), float) / 255.0)
    H, W = a.shape[:2]
    px = [[] for _ in range(len(IRIS_BINS) - 1)]
    rad, opens = [], []
    for s_, e in enumerate(lb):
        r, c = float(e["r_px"]), np.asarray(e["centre"], float)
        if r < IRIS_PX:
            continue
        m = Image.new("L", (W, H), 0)
        ring = P[list(EYE_RING[s_])]
        cen = ring.mean(0)
        ring = cen + (ring - cen) * (1 - 1.0 / max(np.linalg.norm(ring - cen, axis=1).mean(), 1.0))     # in by ~1 px
        ImageDraw.Draw(m).polygon([tuple(q) for q in ring], fill=255)
        inside = np.asarray(m) > 0
        y0, y1, x0, x1 = int(c[1] - 1.25 * r), int(c[1] + 1.25 * r) + 1, int(c[0] - 1.25 * r), int(c[0] + 1.25 * r) + 1
        if y0 < 0 or x0 < 0 or y1 >= H or x1 >= W:
            continue
        yy, xx = np.mgrid[y0:y1, x0:x1]
        d = np.hypot(xx - c[0], yy - c[1]) / r
        ok = inside[yy, xx]
        opens.append(float(ok[d < 1.0].mean()))
        rad.append(r)
        for k in range(len(px)):
            q = ok & (d >= IRIS_BINS[k]) & (d < IRIS_BINS[k + 1])
            px[k].append(a[yy[q], xx[q]])
    if not rad:
        return None
    rgb, n = [], []
    for q in px:
        q = np.concatenate(q) if q else np.zeros((0, 3))
        if len(q) >= 8:
            lum = q @ Y
            q = q[(lum <= np.percentile(lum, 85)) & (lum >= np.percentile(lum, 10))]
        rgb.append(np.median(q, 0) if len(q) else np.full(3, np.nan))
        n.append(len(q))
    rgb = np.asarray(rgb)
    rc = 0.5 * (IRIS_BINS[:-1] + IRIS_BINS[1:])
    lum = rgb @ Y
    g = np.gradient(np.where(np.isfinite(lum), lum, 0.0))
    sel = (rc > 0.15) & (rc < 0.6)
    pupil = float(rc[sel][int(np.argmax(g[sel]))]) if sel.any() else 0.36
    return {"r": rc, "rgb": rgb, "n": n, "radius_px": float(np.mean(rad)), "pupil": pupil, "open": float(np.mean(opens))}


def _zones(prof: dict) -> dict:
    """{zone: linear rgb median} of a radial profile: inner (pupil's edge + 0.08 .. 0.55), outer, limbal."""
    out = {}
    for k, (lo, hi) in IRIS_ZONES.items():
        lo = max(lo, prof["pupil"] + 0.08) if k == "inner" else lo
        v = prof["rgb"][(prof["r"] >= lo) & (prof["r"] < hi)]
        v = v[np.isfinite(v).all(1)]
        out[k] = np.median(v, 0) if len(v) else None
    return out


def _swatch_zones(eyes: dict, radius_px: float, pupil: float) -> dict:
    """The same zones read off OUR eye picture (skin_swatch.eye_image with these skin.eyes values), blurred to the
    photograph's resolution: what a parameter value gives through the same read (the calibration)."""
    from PIL import Image
    from scipy import ndimage
    from . import skin_swatch
    hx = lambda h: [int(h[i:i + 2], 16) / 255.0 for i in (1, 3, 5)]  # noqa: E731
    span = 2.1
    path = skin_swatch.eye_image(hx(eyes["iris"]), pupil, 0.0, (0.92, 0.89, 0.85), 0, span, limbal=float(eyes.get("limbal", 0.72)),
                                 contrast=float(eyes.get("iris_contrast", 1.0)), limbal_width=float(eyes.get("limbal_width", 0.2)),
                                 inner=hx(eyes["iris_inner"]) if eyes.get("iris_inner") else None, inner_to=float(eyes.get("iris_inner_to", 0.55)))
    a = _lin(np.asarray(Image.open(path).convert("RGB"), float) / 255.0)
    S = a.shape[0]
    R = S / (2 * span)
    a = np.stack([ndimage.gaussian_filter(a[..., c], 0.6 * R / max(radius_px, 1.0)) for c in range(3)], -1)
    yy, xx = np.mgrid[0:S, 0:S]
    d = np.hypot(xx - (S - 1) / 2, yy - (S - 1) / 2) / R
    rgb = np.array([np.median(a[(d >= IRIS_BINS[k]) & (d < IRIS_BINS[k + 1])], 0) for k in range(len(IRIS_BINS) - 1)])
    return _zones({"r": 0.5 * (IRIS_BINS[:-1] + IRIS_BINS[1:]), "rgb": rgb, "pupil": pupil})


def iris_read(profiles: list, gains: list, eyes0: dict | None = None) -> dict | None:
    """skin.eyes values from the views' iris profiles: {"iris" (#hex: toward the rim), "iris_inner" (#hex: round the
    pupil), "limbal" (0..1), "pupil" (the pupil's edge, share of the radius: reported), "px", "zones" (the picture's
    albedo per zone, sRGB), "text"}. Each zone's colour is the picture's (lightness x the gain of the skin under the
    eye: INFERRED, the eye taken to be lit as that skin; the picture's own hue), and the PARAMETERS are solved so that
    OUR eye picture, read the same way at the picture's resolution, gives those zones (a few fixed-point steps: the
    fibres, crypts and ring darken a colour by 20-65 %, so a parameter is not the colour it gives)."""
    rows = [(p, float(np.asarray(g, float) @ Y)) for p, g in zip(profiles, gains) if p is not None]
    if not rows:
        return None
    want = {}
    for k in IRIS_ZONES:
        v = [z * g for p, g in rows for z in [_zones(p)[k]] if z is not None]
        want[k] = np.median(v, 0) if v else None
    if want["outer"] is None:
        return None
    if want["inner"] is None:
        want["inner"] = want["outer"]
    px = float(np.mean([p["radius_px"] for p, _ in rows]))
    pupil = float(np.median([p["pupil"] for p, _ in rows]))
    hexs = lambda c: "#" + "".join(f"{int(round(255 * float(x))):02x}" for x in np.clip(_srgb(np.clip(c, 0, 1)), 0, 1))  # noqa: E731
    e = {**{k: v for k, v in (eyes0 or {}).items() if k in ("iris_contrast", "limbal_width")}, "iris": hexs(want["outer"]), "iris_inner": hexs(want["inner"]),
         "limbal": float((eyes0 or {}).get("limbal", 0.72))}
    par = {"iris": np.asarray(want["outer"], float).copy(), "iris_inner": np.asarray(want["inner"], float).copy()}
    for _ in range(5):
        got = _swatch_zones(e, px, pupil)
        if got["outer"] is None or got["inner"] is None:
            break
        par["iris"] = np.clip(par["iris"] * np.clip(want["outer"] / np.maximum(got["outer"], 1e-4), 0.5, 2.0), 0, 1)
        par["iris_inner"] = np.clip(par["iris_inner"] * np.clip(want["inner"] / np.maximum(got["inner"], 1e-4), 0.5, 2.0), 0, 1)
        if want["limbal"] is not None and got["limbal"] is not None:
            rw = float(want["limbal"] @ Y) / max(float(want["outer"] @ Y), 1e-5)
            rg = float(got["limbal"] @ Y) / max(float(got["outer"] @ Y), 1e-5)
            e["limbal"] = float(np.clip(e["limbal"] + 0.8 * (rg - rw), 0.0, 0.95))
        e["iris"], e["iris_inner"] = hexs(par["iris"]), hexs(par["iris_inner"])
    got = _swatch_zones(e, px, pupil)
    de = {k: (round(float(np.linalg.norm(lab(want[k]) - lab(got[k]))), 1) if want[k] is not None and got.get(k) is not None else None) for k in IRIS_ZONES}
    out = {"iris": e["iris"], "iris_inner": e["iris_inner"], "limbal": round(e["limbal"], 2), "pupil": round(pupil, 2), "px": round(px, 1),
           "zones": {k: (hexs(v) if v is not None else None) for k, v in want.items()}, "left_dE": de,
           "open": round(float(np.mean([p["open"] for p, _ in rows])), 2)}
    out["text"] = (f"the picture's iris (albedo; lightness through the skin under the eye: INFERRED; the picture's own hue): round the pupil {out['zones']['inner']}, "
                   f"toward the rim {out['zones']['outer']}, the limbal ring {out['zones']['limbal']}; pupil's edge at {out['pupil']} of the radius; limbus {out['px']} px, "
                   f"{int(100 * out['open'])} % of the disc inside the lids. Parameters that give them through our eye picture: iris {out['iris']}, iris_inner {out['iris_inner']}, "
                   f"limbal {out['limbal']} (left over, Lab dE by zone: {de})")
    return out


# ---------------------------------------------------------------- the pipeline

PLAIN = ("forehead_region", "left_temple_region", "right_temple_region", "left_zygomatic_region", "right_zygomatic_region",
         "left_infraorbital_region", "right_infraorbital_region", "left_cheek_region", "right_cheek_region", "nose_region",
         "chin_region", "left_parotid_region", "right_parotid_region", "upper_lip_region")
NOT_PLAIN = ("upper_lip", "lower_lip", "left_brow_region", "right_brow_region", "middle_brow_region", "left_orbital_region",
             "right_orbital_region", "ears")
REGIONS = {"forehead": ("forehead_region",), "temple": ("left_temple_region", "right_temple_region"),
           "brow": ("left_brow_region", "right_brow_region", "middle_brow_region"),
           "orbit": ("left_orbital_region", "right_orbital_region"),
           "under_eye": ("left_infraorbital_region", "right_infraorbital_region"),
           "cheekbone": ("left_zygomatic_region", "right_zygomatic_region"), "cheek": ("left_cheek_region", "right_cheek_region"),
           "nose": ("nose_region",), "upper_lip_skin": ("upper_lip_region",), "lips": ("upper_lip", "lower_lip"),
           "lower_lip_skin": ("lower_lip_region",), "chin": ("chin_region",), "jaw_side": ("left_parotid_region", "right_parotid_region")}


BEARD_ZONES = ("upper_lip_skin", "lower_lip_skin", "chin", "jaw_side")   # where a beard's shadow may lie: out of the light's COLOUR fit


def region_masks(at: dict) -> dict:
    """{region: (n,) bool} at the valid texels, from GNM's own vertex groups (a texel is in the first region that
    claims it; the vermilion wins over the lip skin regions)."""
    g = at["groups"]
    out = {}
    lips = np.maximum(interp(at, g["upper_lip"]), interp(at, g["lower_lip"])) > 0.5
    for k, names in REGIONS.items():
        m = np.max([interp(at, g[n]) for n in names if n in g], 0) > 0.5
        out[k] = m & (~lips if k != "lips" else True)
    return out


def _plain(at: dict) -> np.ndarray:
    g = at["groups"]
    a = np.max([interp(at, g[n]) for n in PLAIN if n in g], 0) > 0.5
    b = np.max([interp(at, g[n]) for n in NOT_PLAIN if n in g], 0) > 0.3
    return a & ~b


def _two_band(at: dict, cols: list, ws: list) -> tuple:
    """Albedos (n, 3) with weights (n,) blended in two bands (log colour): the broad band with the weights as they
    are, the fine band from the strongest. Returns (colour, total weight, strongest index)."""
    Wt = np.sum(ws, 0)
    low_num, hi_num, hi_den = np.zeros((len(Wt), 3)), np.zeros((len(Wt), 3)), np.zeros(len(Wt))
    for c, w in zip(cols, ws):
        lg = np.log(np.maximum(c, 1e-4))
        lo = _blur(at, lg, (w > 0.02).astype(float), BAND_MM)
        low_num += w[:, None] * lo
        w4 = w ** 4
        hi_num += w4[:, None] * (lg - lo)
        hi_den += w4
    out = low_num / np.maximum(Wt, 1e-6)[:, None] + hi_num / np.maximum(hi_den, 1e-12)[:, None]
    return np.exp(out), Wt, np.argmax(ws, 0)


def _shine(at: dict, col: np.ndarray, w: np.ndarray) -> np.ndarray:
    yy = col @ Y
    loc = _blur(at, yy, (w > 0.3).astype(float), 10.0)
    top = SHINE[0] * np.maximum(loc, 1e-4)
    over = np.maximum(yy - top, 0.0)
    return col * ((np.minimum(yy, top) + SHINE[1] * over) / np.maximum(yy, 1e-5))[:, None]


def _pull_push(at: dict, vals: np.ndarray, w: np.ndarray, fallback, reaches=(4.0, 10.0, 25.0, 60.0)) -> np.ndarray:
    """Values known where w > 0 spread over the whole atlas: the nearest known neighbourhood's weighted mean
    (Gaussians of growing reach), `fallback` where nothing is within reach."""
    out = np.tile(np.asarray(fallback, float), (len(vals), 1)) if vals.ndim == 2 else np.full(len(vals), float(fallback))
    done = np.zeros(len(vals), bool)
    from scipy import ndimage
    Wm = image(at, w.astype(np.float32))
    for mm in reaches:
        sg = mm / at["mm"]
        den = ndimage.gaussian_filter(Wm, sg, truncate=3.0)[at["ii"], at["jj"]]
        got = (den > 0.02) & ~done
        if not got.any():
            continue
        if vals.ndim == 1:
            num = ndimage.gaussian_filter(image(at, (vals * w).astype(np.float32)), sg, truncate=3.0)[at["ii"], at["jj"]]
            out[got] = num[got] / den[got]
        else:
            for c in range(vals.shape[1]):
                num = ndimage.gaussian_filter(image(at, (vals[:, c] * w).astype(np.float32)), sg, truncate=3.0)[at["ii"], at["jj"]]
                out[got, c] = num[got] / den[got]
        done |= got
    return out


def _texture_noise(at: dict, logc: np.ndarray, trust: np.ndarray, seed: int = 7) -> tuple:
    """Fine texture with the projected skin's own statistics: Gaussian noise in three octave bands under BAND_MM,
    each with the band's measured strength on the trusted plain skin, coloured as the measured fine band is.
    Returns ((n, 3) log-colour noise, {"bands_mm", "std"})."""
    from scipy import ndimage
    rng = np.random.default_rng(seed)
    H, W = at["shape"]
    sig = [BAND_MM / at["mm"] / k for k in (1.0, 2.0, 4.0)]      # texels
    lum = logc @ Y
    Lm = image(at, np.where(trust, lum, 0.0).astype(np.float32))
    Tm = image(at, trust.astype(np.float32))

    def low(img, s):
        return ndimage.gaussian_filter(img, s) / np.maximum(ndimage.gaussian_filter(Tm, s), 1e-3) if img is Lm else ndimage.gaussian_filter(img, s)
    ok = ndimage.gaussian_filter(Tm, sig[0]) > 0.95
    prev = low(Lm, sig[0])
    bands, stds = [], []
    white = rng.standard_normal((H, W)).astype(np.float32)
    nprev = ndimage.gaussian_filter(white, sig[0])
    for s in sig[1:] + [0.0]:
        cur = low(Lm, s) if s > 0 else np.where(Tm > 0, Lm, 0.0)
        ncur = ndimage.gaussian_filter(white, s) if s > 0 else white
        b = (cur - prev)[ok & (Tm > 0.5)]
        sd = float(np.median(np.abs(b - np.median(b))) * 1.4826) if len(b) > 500 else 0.0
        nb = ncur - nprev
        bands.append(nb * (sd / max(float(nb.std()), 1e-9)))
        stds.append(sd)
        prev, nprev = cur, ncur
    noise = np.sum(bands, 0)[at["ii"], at["jj"]]
    # the fine band's colour: per-channel strength against the luminance's
    hp = logc - _blur(at, logc, trust.astype(float), BAND_MM)
    q = trust & np.isfinite(hp).all(1)
    k = np.array([float(np.median(np.abs(hp[q, c]))) for c in range(3)]) / max(float(np.median(np.abs(hp[q] @ Y))), 1e-9) if q.sum() > 500 else np.ones(3)
    return noise[:, None] * np.clip(k, 0.5, 1.6), {"bands_mm": [round(s * at["mm"], 2) for s in sig], "std": [round(s, 4) for s in stds]}


def _detail(at: dict, col: np.ndarray, trust: np.ndarray) -> tuple:
    """The fine relief map: dark LINES of the albedo (a ridge detector on log luminance at DETAIL_MM), kept where
    their directions agree over COHERENT_MM (a wrinkle bundle; hairs, specks and freckles do not). Returns ((n,)
    0..1 groove strength, notes)."""
    from scipy import ndimage
    lum = np.log(np.maximum(col @ Y, 1e-4))
    Lm = image(at, lum.astype(np.float32))
    M = image(at, np.ones(len(lum), np.float32))
    Lm = np.where(M > 0, Lm, float(np.median(lum)))
    best = np.zeros(at["shape"], np.float32)
    Jxx, Jxy, Jyy = (np.zeros(at["shape"], np.float32) for _ in range(3))
    for mm in DETAIL_MM:
        s = max(mm / at["mm"], 0.8)
        hxx = ndimage.gaussian_filter(Lm, s, order=(0, 2)) * s * s
        hyy = ndimage.gaussian_filter(Lm, s, order=(2, 0)) * s * s
        hxy = ndimage.gaussian_filter(Lm, s, order=(1, 1)) * s * s
        tr, df = hxx + hyy, np.sqrt((hxx - hyy) ** 2 + 4 * hxy ** 2)
        l1, l2 = 0.5 * (tr + df), 0.5 * (tr - df)        # l1: across a dark line (positive: a valley of lightness)
        line = np.clip(l1 - np.abs(l2), 0, None) * (l1 > 0)
        th = 0.5 * np.arctan2(2 * hxy, hxx - hyy)
        take = line > best
        best = np.where(take, line, best)
        Jxx += line * np.cos(2 * th)
        Jxy += line * np.sin(2 * th)
        Jyy += line
    sc = COHERENT_MM / at["mm"]
    coh = np.hypot(ndimage.gaussian_filter(Jxx, sc), ndimage.gaussian_filter(Jxy, sc)) / np.maximum(ndimage.gaussian_filter(Jyy, sc), 1e-6)
    v = best[at["ii"], at["jj"]]
    ref = float(np.percentile(v[trust], 99)) if trust.sum() > 1000 else 0.0
    g = _sstep((v - LINE[0]) / LINE[1]) * _sstep((coh[at["ii"], at["jj"]] - 0.25) / 0.3)
    return g, {"line_p99": round(ref, 4), "coherent_share": round(float((coh[at["ii"], at["jj"]][trust] > 0.4).mean()), 3) if trust.any() else 0.0}


def _bleed(img: np.ndarray, valid: np.ndarray) -> np.ndarray:
    from scipy import ndimage
    idx = ndimage.distance_transform_edt(~valid, return_distances=False, return_indices=True)
    return img[idx[0], idx[1]]


HARMONISE_MM = 12.0      # mm: the scale of a view's colour cast against the others (a wall's bounce, the fitted light's tint)


def _harmonise(at: dict, cols: dict, VI, ws, rep: dict) -> None:
    """Each view's de-lit colour brought to the views' consensus in CHROMA only (lightness untouched): the smooth
    log-ratio against the weighted mean of the others where both see the skin, carried over the rest of that view's
    texels, divided out. (A cast one light colour per picture cannot hold: a test head's profile picture beside an orange
    wall left a yellow-green patch at her temple; views 0-1 disagreed by dE 5.6 after de-lighting.) In place."""
    lc = {vi: np.log(np.maximum(cols[vi], 1e-4)) for vi in VI}
    wd = {vi: np.asarray(w, float) for vi, w in zip(VI, ws)}
    corr = {}
    for vi in VI:
        others = [o for o in VI if o != vi]
        wo = np.sum([wd[o] for o in others], 0)
        mo = np.sum([wd[o][:, None] * lc[o] for o in others], 0) / np.maximum(wo, 1e-6)[:, None]
        ov = np.clip(np.minimum(wd[vi], wo), 0, 1) * (wd[vi] > 0.3) * (wo > 0.3)
        if ov.sum() < 2000:
            continue
        d = lc[vi] - mo
        d = d - (d @ Y)[:, None]                                  # chroma only
        sm = _blur(at, d, ov, HARMONISE_MM)
        has = _blur(at, ov, None, HARMONISE_MM) > 0.05
        fill = _pull_push(at, sm, has.astype(float), np.median(sm[has], 0) if has.any() else np.zeros(3), reaches=(10.0, 25.0, 60.0))
        corr[vi] = np.where(has[:, None], sm, fill)
    for vi, c in corr.items():
        cols[vi] = cols[vi] * np.exp(-0.5 * c)                    # each view half way: the pair meet in the middle
    rep["harmonised"] = {str(vi): round(float(np.median(np.linalg.norm(c, axis=1))), 4) for vi, c in corr.items()}


def make(name: str, spec: dict | None = None, views=None, size: int = SIZE, delight: bool = True, parse: str | None = "mediapipe",
         ears: bool = False, mirror: bool = True, tone: str = "model", key: bool = True, log=print, photos: dict | None = None,
         lights: dict | None = None) -> dict:
    """The projected skin of a model with fitted references (human_refs.json: views + cameras). Returns {"albedo"
    (H, W, 4) uint8 sRGB (alpha: the head's fade into the body), "raw" (the same blend and fill with NO de-lighting),
    "detail" (H, W) uint8 groove strength, "conf" (H, W, 3) uint8 (direct view, mirrored, ours), "source" (H, W) int8
    (the strongest view per texel, -1 mirrored, -2 ours), "box", "report": {...}, "text"}.
    views: indices (default: every view with an image and a camera). tone: "model" (the projected plain skin's median
    takes the model's own skin tone: exposure and white balance are the model's, set by skin_from_reference or by
    hand) | "picture" (the picture's colour under an assumed white light; only the lightness is the model's).
    photos: {view index: (h, w, 3) uint8} instead of the references' files (tests). lights: {view: {"sh", "key"}} to
    hold the lights (tests)."""
    import time
    from PIL import Image
    from scipy import ndimage
    from scipy.spatial import cKDTree
    from . import blockin as bi, likeness as lk, store
    t0 = time.time()
    spec = spec or store.load(name)
    rj = bi._refs(name)
    at = atlas(spec["base"], size)
    n = len(at["ii"])
    VI = [i for i in (range(len(rj["views"])) if views is None else views) if rj["views"][i].get("image") and rj["cameras"][i] is not None]
    if not VI:
        raise ValueError(f"skin_project: {name} has no fitted reference views (human_reference / block_in first)")
    meshes = bi._per_view(spec["base"], rj, VI, lambda b: lk.model_mesh(b))
    plain = _plain(at)
    regs = region_masks(at)
    beard = np.zeros(n, bool)
    for k_ in BEARD_ZONES:
        if k_ in regs:
            beard |= regs[k_]
    rep: dict = {"model": name, "views": {}, "atlas": {"size": list(at["shape"][::-1]), "mm_per_texel": round(at["mm"], 3), "box": at["box"]}}
    S: dict = {}
    tr_cache: dict = {}
    for vi in VI:
        v, cam = rj["views"][vi], rj["cameras"][vi]
        img = Image.fromarray(np.asarray(photos[vi])) if photos and vi in photos else Image.open(v["image"]).convert("RGB")
        mesh = meshes[vi]
        maps = _picture_maps(img, cam, mesh, parse)
        if "hair" in maps:
            mpp = max(cam["t"][2] / cam["f"], 1e-9)          # m per picture pixel at the head
            px = max(int(round(HAIR_GROW / mpp)), 1)
            maps["hair_grown"] = ndimage.maximum_filter(maps["hair"], 2 * px + 1)
            maps["wisp"] = _wisps(np.asarray(img), maps["hair"], mpp, maps.get("skin"))
            maps["strand"] = _strands(np.asarray(img), maps["hair"], mpp)
        s = sample_view(at, mesh, cam, np.asarray(img), maps)
        s["_skin_map"] = maps.get("skin")
        from . import face_ruler as _fr
        s["iris"] = iris_profile(img, v) if abs(_fr.view_yaw(cam)) <= IRIS_YAW else None
        ok, notes = exclude(at, s, mesh, cam, img, v, parse, ears)
        face = _sstep((s["facing"] - FACE[0]) / (FACE[1] - FACE[0]))
        s["conf"] = (s["vis"] * face * ok * ~s["clip"]).astype(np.float32)
        s.pop("maps", None)
        S[vi] = s
        rep["views"][vi] = {"image": Path(v["image"]).name, "mm_per_px": round(s["mm"], 3), **notes,
                            "seen": round(float(s["vis"].mean()), 3), "trusted": round(float((s["conf"] > 0.5).mean()), 3)}
        log(f"skin_project: view {vi} sampled ({time.time() - t0:.0f} s): seen {s['vis'].mean():.2f} trusted {(s['conf'] > 0.5).mean():.2f} {notes}")
    # ours (the fill, and the tone)
    O = ours_albedo(at, spec, log=log)
    anyc = np.max([S[vi]["conf"] for vi in VI], 0)
    core = plain & (anyc > 0.6)
    c_tone = np.median(O[core], 0) if core.sum() > 500 else np.median(O, 0)
    rep["tone"] = {"mode": tone, "ours_plain_srgb": [round(float(x), 3) for x in _srgb(c_tone)]}
    log(f"skin_project: ours evaluated ({time.time() - t0:.0f} s)")
    # RAW: no de-lighting, each view's exposure matched on the plain skin
    def blend(cols):
        return _two_band(at, [cols[vi] for vi in VI], [S[vi]["conf"] for vi in VI])
    raw_cols = {}
    for vi in VI:
        q = plain & (S[vi]["conf"] > 0.6)
        g = float((c_tone @ Y) / max(float(np.median(S[vi]["rgb"][q] @ Y)), 1e-4)) if q.sum() > 200 else 1.0
        raw_cols[vi] = S[vi]["rgb"] * g
    raw, Wt, src = blend(raw_cols)
    alb_cols = raw_cols
    if delight:
        target = np.tile(c_tone, (n, 1))
        for rnd in range(3):
            for vi in VI:
                s = S[vi]
                fit = np.flatnonzero(plain & (s["conf"] > 0.5))
                if len(fit) < 2000:
                    fit = np.flatnonzero(s["conf"] > 0.5)
                if len(fit) > 60000:
                    fit = fit[np.random.default_rng(vi).choice(len(fit), 60000, replace=False)]
                if "T" not in s:
                    mk = id(meshes[vi])
                    if mk not in tr_cache:
                        sub = np.flatnonzero(plain & (anyc > 0.3))
                        if len(sub) > 40000:
                            sub = sub[np.random.default_rng(1).choice(len(sub), 40000, replace=False)]
                        tr = transfer(meshes[vi], s["X"], s["N"], sub)
                        tr_cache[mk] = (tr, sub)
                        log(f"skin_project: light transport of view {vi}'s head ({time.time() - t0:.0f} s)")
                    tr, sub = tr_cache[mk]
                    s.update(T=tr["T"], D=tr["D"], sub=sub, sub_vis=tr["sub_vis"], ao=tr["ao"])
                held = (lights or {}).get(vi)
                lt = fit_light(s, target, fit, key=key, key_dir=(s.get("key_dir") if rnd else None) if not held else (held.get("key") or {}).get("dir"), mesh=meshes[vi],
                               colour_w=(~beard[fit]).astype(float))
                s["light"] = lt
            cols = {}
            for vi in VI:
                s = S[vi]
                Sv = s["light"]["S"]
                if tone == "picture":   # the light taken WHITE: its shading comes out, not its colour (else the hue the fit
                    Sv = np.repeat((Sv @ Y)[:, None], 3, 1)   # gave the light, fitted against the model's tone, is divided out again)
                sy = Sv @ Y
                ok_ = s["conf"] > 0.5
                med = float(np.median(sy[ok_])) if ok_.any() else 1.0
                medc = np.median(Sv[ok_], 0) if ok_.any() else np.ones(3)
                cols[vi] = s["rgb"] / np.maximum(Sv, SHADE_FLOOR * medc)        # no division by near-darkness
                # a crease the model has and the picture has elsewhere (the alar groove, a nostril's rim, the lip line):
                # dividing by the model's dip paints a bright line. Where the shading dips against its surroundings the
                # albedo may not rise above its own surroundings
                wv = (s["conf"] > 0.3).astype(float)
                dip = sy / np.maximum(_blur(at, sy, wv, DIP_MM), 1e-6)
                cy = cols[vi] @ Y
                cap = DIP_OVER * _blur(at, cy, wv * (dip > DIP[1]), DIP_MM)
                k = np.where((dip < DIP[1]) & (cy > cap), cap / np.maximum(cy, 1e-6), 1.0)
                k = 1 + (k - 1) * _sstep((DIP[1] - dip) / (DIP[1] - DIP[0]))
                cols[vi] = cols[vi] * k[:, None]
                s["lit"] = _sstep((sy / med - 0.5 * SHADE_FLOOR) / SHADE_FLOOR).astype(np.float32)   # deep occlusion: the picture's dark there is ours to make
            ws = [S[vi]["conf"] * S[vi]["lit"] for vi in VI]
            if rnd == 2 and len(VI) > 1:
                _harmonise(at, cols, VI, ws, rep)
            alb, Wt, src = _two_band(at, [cols[vi] for vi in VI], ws)
            if rnd < 2:
                lo = _blur(at, np.log(np.maximum(alb, 1e-4)), (Wt > 0.2).astype(float), LOW_MM)
                target = np.exp((1 - MU) * np.log(c_tone) + MU * lo)
        alb = _shine(at, alb, Wt)
        alb_cols = cols
        # a cavity's dark that the picture has BESIDE the model's cavity (a nostril, the lip line: the head's nostril
        # sits a millimetre or two from the photographed one): near the model's own cavities, on the nose and round the
        # mouth, skin much darker than its surroundings is the picture's occlusion, not pigment: left out (the fill
        # takes the skin round it; the model's own cavity makes the dark where it belongs)
        ao_all = np.min([S[vi]["ao"] for vi in VI], 0)
        cav = _blur(at, (ao_all < CAVITY_AO).astype(float), None, CAVITY_MM) > 0.03
        ay = np.log(np.maximum(alb @ Y, 1e-4))
        bad = np.zeros(n, bool)
        for grp in (regs["lips"], regs["nose"] | regs["upper_lip_skin"] | regs["lower_lip_skin"]):
            wq = (grp & (Wt > 0.3)).astype(float)
            if wq.sum() < 200:
                continue
            loc = _blur(at, ay, wq, 5.0)
            bad |= grp & cav & (ay < loc + np.log(CAVITY_DARK)) & (Wt > 0.05)
        if bad.any():
            soft = np.clip(_blur(at, bad.astype(float), None, 0.5) * 2.5, 0, 1)
            Wt = Wt * (1 - soft)
            rep["cavity_dark_left_out"] = round(float(bad.sum() / max(int((Wt > 0.3).sum()), 1)), 4)
        for vi in VI:
            lt = S[vi]["light"]
            q_ = S[vi]["conf"] > 0.5
            mc = np.median(lt["S"][q_], 0) if q_.any() else np.ones(3)
            rep["views"][vi]["light_colour"] = [round(float(x), 4) for x in mc / max(float(mc @ Y), 1e-9)]   # the light's colour IF the skin has the tone it was fitted with
            rep["views"][vi]["light"] = {"colour": rep["views"][vi]["light_colour"], "fit_rms": round(lt["rms"], 4), "fit_rms_no_key": round(lt["rms0"], 4), "key": lt["key"],
                                         "ambient_share": lt["ambient_share"], "sh": np.round(lt["sh"], 4).tolist()}
        log(f"skin_project: de-lit ({time.time() - t0:.0f} s): " + "; ".join(f"view {vi} rms {S[vi]['light']['rms']:.3f} key {S[vi]['light']['key']}" for vi in VI))
    else:
        alb = raw
    # tone: the plain skin's median
    def retone(col):
        q = plain & (Wt > 0.6)
        if q.sum() < 500:
            return col, [1.0, 1.0, 1.0]
        med = np.median(col[q], 0)
        g = c_tone / np.maximum(med, 1e-5) if tone == "model" else np.full(3, float((c_tone @ Y) / max(med @ Y, 1e-5)))
        return col * g, [round(float(x), 3) for x in g]
    alb, g_alb = retone(alb)
    raw, _ = retone(raw)
    rep["tone"]["gain"] = g_alb
    # FILL 1: the mirror image
    direct = np.clip(Wt, 0, 1)
    conf_m = np.zeros(n)
    outs = {}
    Xn = interp(at, at["neutral"])
    have = np.flatnonzero(direct > 0.3)
    need = np.flatnonzero(direct < 0.6)
    msrc = None
    if mirror and len(have) > 1000 and len(need):
        d, j = cKDTree(Xn[have]).query(Xn[need] * [-1.0, 1.0, 1.0], distance_upper_bound=0.0008)
        good = np.isfinite(d)
        msrc = (need[good], have[j[good]])
        conf_m[msrc[0]] = MIRROR_CONF * direct[msrc[1]]
    for kname, col in (("albedo", alb), ("raw", raw)):
        if msrc is not None:
            cm = col.copy()
            cm[msrc[0]] = col[msrc[1]]
            col2, W2, _ = _two_band(at, [col, cm], [direct, conf_m])
        else:
            col2, W2 = col, direct
        outs[kname] = (col2, W2)
    Wp = np.clip(outs["albedo"][1], 0, 1)
    # FILL 2: ours, retoned to the projected skin round it, with its fine texture
    al = _sstep((_blur(at, Wp, None, 1.5) - 0.2) / 0.5) * (Wp > 0.02)
    fin = {}
    for kname, (col, _) in outs.items():
        lc = np.log(np.maximum(col, 1e-4))
        lo_p = _blur(at, lc, (Wp > 0.4).astype(float), LOW_MM)
        lo_o = _blur(at, np.log(np.maximum(O, 1e-4)), None, LOW_MM)
        known = (Wp > 0.5).astype(float)
        g0 = np.median((lo_p - lo_o)[Wp > 0.5], 0) if (Wp > 0.5).sum() > 500 else np.zeros(3)
        rho = _pull_push(at, lo_p - lo_o, known, g0)
        noise, tn = _texture_noise(at, lc, plain & (Wp > 0.8))
        lo_fill = lo_o + rho
        # a small hole inside the projected skin (a nostril's rim, a lid, a wisp) takes the skin round it, not our
        # zone paint: the projected broad colour carried in, handed over to ours beyond INPAINT_MM
        inp = _pull_push(at, lc, known, np.zeros(3), reaches=INPAINT_MM)
        from scipy import ndimage as _nd
        near = _nd.gaussian_filter(image(at, known.astype(np.float32)), INPAINT_MM[-1] / at["mm"], truncate=3.0)[at["ii"], at["jj"]]
        kin = _sstep((near - 0.08) / 0.2)
        lo_fill = kin[:, None] * inp + (1 - kin)[:, None] * lo_fill
        fill = lo_fill + (1 - kin)[:, None] * (np.log(np.maximum(O, 1e-4)) - lo_o) + noise
        fin[kname] = np.exp(al[:, None] * lc + (1 - al)[:, None] * fill)
        if kname == "albedo":
            rep["fill"] = {"texture": tn, "ours_to_projected_gain": [round(float(x), 3) for x in np.exp(g0)]}
    # DETAIL
    trust = (direct > 0.6)
    det, dn = _detail(at, fin["albedo"], trust & plain)
    brow = np.max([interp(at, at["groups"][k]) for k in ("left_brow_region", "right_brow_region", "middle_brow_region")], 0)
    lipsm = regs["lips"]
    inner = _blur(at, (direct > 0.6).astype(float), None, 1.5)          # not at the picture's own edges (a border is no line)
    facem = np.max([m for k, m in regs.items() if k not in ("lips", "brow")], 0)
    det = det * _sstep((inner - 0.8) / 0.15) * (1 - _sstep((brow - 0.2) / 0.4)) * facem
    for Ve, _, _ in lk.model_mesh(spec["base"])["eyes"]:      # not on the lids (the lid's fold and lash line are FORM, not a groove)
        c_ = Ve.mean(0)
        det = det * _sstep((np.linalg.norm(interp(at, at["V"]) - c_, axis=1) - float(np.linalg.norm(Ve - c_, axis=1).max()) - DETAIL_LID) / 0.003)
    ao = np.min([S[vi]["ao"] for vi in VI if "ao" in S[vi]], 0) if any("ao" in S[vi] for vi in VI) else None
    if ao is not None:                                         # nor where the model has a crease of its own (alar groove, lip corner)
        det = det * _sstep((ao - 0.72) / 0.15)
    rep["detail"] = dn
    # the report: coverage, what the light did not explain
    seen_share = {"direct": round(float((direct > 0.5).mean()), 3), "mirrored": round(float(((direct <= 0.5) & (conf_m > 0.2)).mean()), 3)}
    seen_share["ours"] = round(1 - seen_share["direct"] - seen_share["mirrored"], 3)
    rep["coverage"] = seen_share
    rep["coverage_by_region"] = {k: {"direct": round(float((direct[m] > 0.5).mean()), 2), "mirrored": round(float(((direct[m] <= 0.5) & (conf_m[m] > 0.2)).mean()), 2)}
                                 for k, m in regs.items() if m.sum() > 100}
    rep["views_used"] = {int(vi): round(float(((src == i) & (direct > 0.5)).sum() / max(int((direct > 0.5).sum()), 1)), 3) for i, vi in enumerate(VI)}
    if delight:
        # what the light did not explain: the albedo's mid-band dark against its surroundings, neutral vs coloured
        lc = np.log(np.maximum(alb, 1e-4))
        mid = _blur(at, lc, (direct > 0.4).astype(float), 1.5) - _blur(at, lc, (direct > 0.4).astype(float), 12.0)
        dark = np.clip(-(mid @ Y), 0, None)
        chroma = mid - (mid @ Y)[:, None]
        amb = {}
        for k, m in regs.items():
            q = m & (direct > 0.6)
            if q.sum() < 300:
                continue
            d = dark[q]
            strong = d > 0.06
            amb[k] = {"dark_share": round(float(strong.mean()), 3), "mean_dark": round(float(d.mean()), 3),
                      "coloured": round(float(np.median(np.linalg.norm(chroma[q][strong], axis=1) / np.maximum(d[strong], 1e-6))) if strong.sum() > 50 else 0.0, 2)}
        rep["unexplained_dark"] = amb
        # the views' agreement after de-lighting: the same skin in two pictures
        agree = {}
        for i, a_ in enumerate(VI):
            for b_ in VI[i + 1:]:
                q = (S[a_]["conf"] * S[a_]["lit"] > 0.6) & (S[b_]["conf"] * S[b_]["lit"] > 0.6)
                if q.sum() < 500:
                    continue
                def de(ca, cb):
                    la = lab(_blur(at, ca, q.astype(float), 2.0)[q])
                    lb_ = lab(_blur(at, cb, q.astype(float), 2.0)[q])
                    la -= np.median(la, 0)
                    lb_ -= np.median(lb_, 0)
                    return float(np.sqrt(np.mean(np.sum((la - lb_) ** 2, 1))))
                agree[f"{a_}-{b_}"] = {"texels": int(q.sum()), "dE_raw": round(de(raw_cols[a_], raw_cols[b_]), 2), "dE_delit": round(de(alb_cols[a_], alb_cols[b_]), 2)}
        rep["agreement"] = agree
    # the eyes: the irises' colour and limbal ring, as albedo through the gain of the skin under the eye
    gains = []
    for vi in VI:
        q = regs["under_eye"] & (S[vi]["conf"] > 0.6)
        gains.append(np.median(alb[q] / np.maximum(S[vi]["rgb"][q], 1e-4), 0) if q.sum() > 200 else np.ones(3) * float("nan"))
    ok_v = [i for i, vi in enumerate(VI) if S[vi].get("iris") is not None and np.isfinite(gains[i]).all()]
    e0 = spec["skin"].get("eyes") if isinstance((spec.get("skin") or {}).get("eyes"), dict) else {}
    ir = iris_read([S[VI[i]]["iris"] for i in ok_v], [gains[i] for i in ok_v], e0) if ok_v else None
    rep["eyes"] = ir or {"text": "irises not read (no view within 35 deg of the front with a detection)"}
    # images
    H, W = at["shape"]
    valid = image(at, np.ones(n, bool), False)
    fade = np.clip(interp(at, at["fade"]), 0, 1)
    X0 = interp(at, at["V"])
    for Ve, _, _ in lk.model_mesh(spec["base"])["eyes"]:      # the lid margins stay the live procedural skin's (wet line,
        c = Ve.mean(0)                                          # caruncle, lash roots): the image is transparent there
        r = float(np.linalg.norm(Ve - c, axis=1).max())
        fade = fade * _sstep((np.linalg.norm(X0 - c, axis=1) - r - LID_OPEN[0]) / LID_OPEN[1])
    def rgba(col):
        a = np.zeros((H, W, 4), np.uint8)
        a[..., :3] = _bleed(image(at, (np.clip(_srgb(col), 0, 1) * 255 + 0.5).astype(np.uint8)), valid)
        a[..., 3] = _bleed(image(at, (fade * 255).astype(np.uint8)), valid)
        return a
    conf = image(at, (np.c_[direct, np.where(direct > 0.5, 0, conf_m / MIRROR_CONF), 1 - al] * 255).astype(np.uint8))
    srcm = np.where(direct > 0.5, np.asarray(VI)[src], np.where(conf_m > 0.2, -1, -2)).astype(np.int8)
    rep["seconds"] = round(time.time() - t0, 1)
    out = {"albedo": rgba(fin["albedo"]), "raw": rgba(fin["raw"]), "detail": image(at, (np.clip(det, 0, 1) * 255).astype(np.uint8)),
           "conf": conf, "source": image(at, srcm, -3), "box": at["box"], "report": rep, "atlas_key": at["key"],
           "lights": {vi: S[vi].get("light") and {"sh": S[vi]["light"]["sh"], "key": S[vi]["light"]["key"]} for vi in VI}}
    out["text"] = report_text(rep)
    return out


def report_text(rep: dict) -> str:
    L = [f"skin_project {rep['model']}: atlas {rep['atlas']['size'][0]} x {rep['atlas']['size'][1]}, {rep['atlas']['mm_per_texel']} mm a texel"]
    for vi, v in rep["views"].items():
        s = f"  view {vi} ({v['image']}, {v['mm_per_px']} mm a pixel): trusted on {int(100 * v['trusted'])}% of the head's texels"
        rj = v.get("rejected") or {}
        if rj:
            s += "; left out of what it sees: " + ", ".join(f"{k} {int(round(100 * x))}%" for k, x in rj.items() if x > 0.004)
        s += f"; lid margin band {v.get('lid_band_mm')} mm" + (f" (the lids' landmarks sit {v['lid_misfit_mm']} mm off the picture's)" if "lid_misfit_mm" in v else "")
        e = v.get("ear")
        if e:
            s += "; ear " + ("projected" if e.get("projected") else "NOT projected") + (f" (picture skin on {int(100 * e['inside'])}% of the model's ear, {int(100 * e['beside'])}% of the band beside it)" if "inside" in e else "")
        L.append(s)
        lt = v.get("light")
        if lt:
            L.append(f"    light: fit residual {lt['fit_rms']:.3f} of the shading (no key {lt['fit_rms_no_key']:.3f}); " +
                     (f"key from {lt['key']['dir']} colour {lt['key']['rgb']}, " if lt["key"] else "no key light found (soft light), ") + f"ambient share {lt['ambient_share']}")
    c = rep["coverage"]
    L.append(f"  coverage of the head's atlas: pictures {int(100 * c['direct'])}%, mirrored (INFERRED) {int(100 * c['mirrored'])}%, our procedural skin retoned {int(100 * c['ours'])}%")
    L.append("  by region (picture / mirrored): " + ", ".join(f"{k} {int(100 * v['direct'])}/{int(100 * v['mirrored'])}" for k, v in rep["coverage_by_region"].items()))
    t = rep["tone"]
    L.append(f"  tone ({t['mode']}): the projected plain skin x {t.get('gain')} -> our skin's {t['ours_plain_srgb']} (sRGB)")
    if rep.get("agreement"):
        L.append("  the same skin in two pictures, Lab difference of the broad colour (raw -> de-lit): " +
                 ", ".join(f"views {k}: {v['dE_raw']} -> {v['dE_delit']} ({v['texels']} texels)" for k, v in rep["agreement"].items()))
    if rep.get("unexplained_dark"):
        L.append("  AMBIGUOUS: dark the fitted light does not explain, kept in the albedo (share of the region over 6% darker than its "
                 "surroundings; coloured 0 = neutral like a shadow, higher = pigment-like):")
        L.append("    " + ", ".join(f"{k} {int(100 * v['dark_share'])}% (coloured {v['coloured']})" for k, v in rep["unexplained_dark"].items()))
    f = rep.get("fill") or {}
    if f:
        L.append(f"  fill: our skin x {f['ours_to_projected_gain']} at the border; fine texture bands {f['texture']['bands_mm']} mm with std {f['texture']['std']}")
    L.append("  eyes: " + (rep.get("eyes") or {}).get("text", "-"))
    d = rep.get("detail") or {}
    L.append(f"  detail: line strength p99 {d.get('line_p99')}, coherent share of the trusted plain skin {d.get('coherent_share')}")
    return "\n".join(L)


# ---------------------------------------------------------------- the atlas at surface points (image wrap "uv")

_LOOK: dict = {}
SEAM = (0.0015, 0.003)   # m: no picture within the first of the atlas' cut, full from the first + the second
REACH = (0.003, 0.004)   # m: full weight within the first of the head's own mesh, none past first + second


def _closest(P, A, B, C):
    """Closest points of triangles (A, B, C) to points P, all (n, 3): barycentric (n, 3)."""
    ab, ac, ap = B - A, C - A, P - A
    d1, d2 = (ab * ap).sum(1), (ac * ap).sum(1)
    bp = P - B
    d3, d4 = (ab * bp).sum(1), (ac * bp).sum(1)
    cp = P - C
    d5, d6 = (ab * cp).sum(1), (ac * cp).sum(1)
    va, vb, vc = d3 * d6 - d5 * d4, d5 * d2 - d1 * d6, d1 * d4 - d3 * d2
    den = np.maximum(va + vb + vc, 1e-30)
    v, w = vb / den, vc / den
    out = np.stack([1 - v - w, v, w], 1)
    def setw(m, val):
        out[m] = val[m]
    e = np.zeros_like(out)
    t = np.clip(d1 / np.maximum(d1 - d3, 1e-30), 0, 1)
    m = (vc <= 0) & (d1 >= 0) & (d3 <= 0)
    e[:] = np.stack([1 - t, t, np.zeros_like(t)], 1)
    setw(m, e)
    t = np.clip(d2 / np.maximum(d2 - d6, 1e-30), 0, 1)
    m = (vb <= 0) & (d2 >= 0) & (d6 <= 0)
    e[:] = np.stack([1 - t, np.zeros_like(t), t], 1)
    setw(m, e)
    t = np.clip((d4 - d3) / np.maximum((d4 - d3) + (d5 - d6), 1e-30), 0, 1)
    m = (va <= 0) & ((d4 - d3) >= 0) & ((d5 - d6) >= 0)
    e[:] = np.stack([np.zeros_like(t), 1 - t, t], 1)
    setw(m, e)
    out[(d1 <= 0) & (d2 <= 0)] = [1, 0, 0]
    out[(d3 >= 0) & (d4 <= d3)] = [0, 1, 0]
    out[(d6 >= 0) & (d5 <= d6)] = [0, 0, 1]
    return out


def lookup(base: dict, pos: np.ndarray, k: int = 8) -> tuple:
    """(u, v, weight) of surface points in the head's atlas (atlas units): the closest point of the head's own mesh
    (the template at rest), its triangle's atlas coordinates. weight: 0 off the head (REACH) and along the atlas' cut
    (SEAM: per-vertex coordinates cannot cross it; the layer under shows there)."""
    from scipy.spatial import cKDTree
    key = hashlib.sha1(json.dumps([base, VERSION], sort_keys=True, default=str).encode()).hexdigest()
    if _LOOK.get("key") != key:
        at = mesh_uv(base)
        V, T, uvT = at["V"], at["T"], at["uvT"]
        nT = len(T)
        Tall = np.r_[T, at["other"]] if len(at["other"]) else T
        cen = V[Tall].mean(1)
        # the cut: edges whose two triangles disagree on a shared vertex's coordinates
        ed: dict = {}
        seam = []
        for t in range(len(T)):
            for a, b in ((0, 1), (1, 2), (2, 0)):
                e = (min(T[t, a], T[t, b]), max(T[t, a], T[t, b]))
                ua, ub = (uvT[t, a], uvT[t, b]) if T[t, a] < T[t, b] else (uvT[t, b], uvT[t, a])
                if e in ed:
                    if np.abs(ed[e][0] - ua).sum() + np.abs(ed[e][1] - ub).sum() > 1e-5:
                        seam.append(e)
                else:
                    ed[e] = (ua, ub)
        sp = np.concatenate([V[[a for a, _ in seam]] * (1 - f) + V[[b for _, b in seam]] * f for f in (0.0, 0.25, 0.5, 0.75, 1.0)]) if seam else np.zeros((0, 3))
        _LOOK.clear()
        _LOOK.update(key=key, V=V, T=Tall, nT=nT, uvT=uvT, tree=cKDTree(cen), seam=cKDTree(sp) if len(sp) else None)
    L = _LOOK
    P = np.asarray(pos, float)
    u, v, w = np.full(len(P), -1.0), np.full(len(P), -1.0), np.zeros(len(P))
    d0, _ = L["tree"].query(P)
    near = np.flatnonzero(d0 < 0.03)
    if not len(near):
        return u, v, w
    Pn = P[near]
    _, cand = L["tree"].query(Pn, k=k)
    best = np.full(len(Pn), np.inf)
    bu = np.zeros((len(Pn), 2))
    own = np.zeros(len(Pn), bool)
    for j in range(k):
        t = cand[:, j]
        A, B, C = (L["V"][L["T"][t, i]] for i in range(3))
        b = _closest(Pn, A, B, C)
        Q = b[:, :1] * A + b[:, 1:2] * B + b[:, 2:] * C
        d = np.linalg.norm(Q - Pn, axis=1)
        m = d < best
        best[m] = d[m]
        inat = t < L["nT"]
        own[m] = inat[m]
        mm_ = m & inat
        bu[mm_] = (b[mm_, :, None] * L["uvT"][t[mm_]]).sum(1)
    wt = (1 - _sstep((best - REACH[0]) / REACH[1])) * own      # (the body, the mouth's sock: not the head's atlas)
    if L["seam"] is not None:
        ds = L["seam"].query(Pn)[0]
        wt *= _sstep((ds - SEAM[0]) / SEAM[1])
    u[near], v[near], w[near] = bu[:, 0], bu[:, 1], wt
    return u, v, w


# ---------------------------------------------------------------- the model

def layers(spec: dict, pj: dict, out: dict, part: str) -> None:
    """spec["skin"]["projection"] as paint layers (skin_features.build calls it after the skin's own colour and hair
    paint, before scars, tattoos and make-up): the albedo over everything painted so far, and the fine relief."""
    if not pj or not pj.get("albedo"):
        return
    box = [float(x) for x in pj["box"]]
    op = float(pj.get("opacity", 1.0))
    if op > 0:
        out["skin:projection"] = {"part": part, "color": "image", "opacity": round(op, 4),
                                  "image": {"id": pj["albedo"], "wrap": "uv", "box": box, "channel": "alpha"}}
    d = float(pj.get("detail_depth", DETAIL_DEPTH))
    if pj.get("detail") and d > 0:
        out["skin:projection_detail"] = {"part": part, "height": -round(d, 7),
                                         "mask": [{"image": {"id": pj["detail"], "wrap": "uv", "box": box, "channel": "luma"}}]}


def check(pj) -> dict | None:
    """Validate spec["skin"]["projection"]."""
    from .spec import SpecError
    if pj in (None, False, {}):
        return None
    if not isinstance(pj, dict) or set(pj) - {"albedo", "detail", "box", "opacity", "detail_depth", "head", "views", "delight", "version", "confidence", "light_colour", "tone_gain"}:
        raise SpecError("skin projection: {albedo: image id, detail: image id, box: [u0, v0, u1, v1], opacity, detail_depth} (made by skin_project)")
    if not (isinstance(pj.get("box"), list) and len(pj["box"]) == 4):
        raise SpecError("skin projection: box is [u0, v0, u1, v1] (made by skin_project)")
    return pj


def stale(spec: dict) -> bool:
    """The projection was made on another head shape than the spec's (re-run skin_project after the head changes)."""
    from . import likeness_texture as lt
    pj = (spec.get("skin") or {}).get("projection") or {}
    return bool(pj.get("head")) and pj["head"] != lt.head_key(spec.get("base") or {})


def apply(name: str, out: str | None = None, remove: bool = False, opacity: float = 0.0, detail_depth: float = DETAIL_DEPTH,
          note: str = "", save_dir: str | None = None, raw: bool = False, made: dict | None = None, eyes: bool = False, stubble: str = "picture", **kw) -> dict:
    """make() + the images into the content store + spec["skin"]["projection"] saved (on `out`, a copy with the
    references, or on `name`). remove=True takes it out. raw=True lays the UN-de-lit blend instead (the comparison).
    opacity: 0 (default) = the atlas is a MEASUREMENT only: the skin that ships is the procedural layers, which
    skin_from_reference fits to it; 1 = "photo skin": the de-lit picture itself as the colour (the ceiling, a judging
    overlay, an explicit opt-in).
    The files (albedo, raw, detail, confidence, report) are also written to <model>/skin_projection/ (or save_dir)."""
    import copy
    from PIL import Image
    from . import blockin as bi, images, likeness_texture as lt, store
    spec = copy.deepcopy(store.load(name))
    dst = out or name
    if remove:
        (spec.get("skin") or {}).pop("projection", None)
        store.save(dst, spec, note or "skin projection removed")
        return {"text": f"{dst}: skin projection removed"}
    if not spec.get("skin"):
        raise ValueError(f"skin_project: {name} has no skin (the projection lies over the procedural skin: `skin` first)")
    r = dict(made) if made is not None else make(name, spec=spec, **kw)     # (made: a make() result to lay again, e.g. raw)
    d = Path(save_dir) if save_dir else store._dir(dst) / "skin_projection"
    d.mkdir(parents=True, exist_ok=True)
    Image.fromarray(r["albedo"], "RGBA").save(d / "albedo.png")
    Image.fromarray(r["raw"], "RGBA").save(d / "raw.png")
    det = np.zeros(r["detail"].shape + (4,), np.uint8)
    det[..., :3] = r["detail"][..., None]
    det[..., 3] = 255
    Image.fromarray(det, "RGBA").save(d / "detail.png")
    Image.fromarray(r["conf"]).save(d / "confidence.png")
    (d / "report.json").write_text(json.dumps(r["report"], indent=1, default=str))
    (d / "report.txt").write_text(r["text"])
    pj = {"albedo": images.ingest(d / ("raw.png" if raw else "albedo.png")), "detail": images.ingest(d / "detail.png"), "box": [round(float(x), 6) for x in r["box"]],
          "opacity": float(opacity), "detail_depth": float(detail_depth), "head": lt.head_key(spec["base"]), "delight": not raw, "version": VERSION,
          # the MEASUREMENT skin_from_reference fits the procedural skin to (skin_read.atlas_source): the de-lit albedo, where a
          # picture vouches for it, and each view's fitted light colour (against a backdrop it gives the tone's hue)
          "confidence": images.ingest(d / "confidence.png"),
          "light_colour": {str(k): v["light_colour"] for k, v in r["report"]["views"].items() if v.get("light_colour")},
          "tone_gain": r["report"]["tone"].get("gain")}
    spec["skin"] = {**spec["skin"], "projection": pj}
    notes = []
    ir = r["report"].get("eyes") or {}
    if not eyes and ir.get("iris"):
        notes.append("  skin.eyes left as they are (eyes=True sets iris / iris_inner / limbal from the read above)")
    if eyes and ir.get("iris") and spec["skin"].get("eyes") is not False:
        e0 = dict(spec["skin"].get("eyes") or {})
        e1 = {**e0, "iris": ir["iris"], "iris_inner": ir["iris_inner"], "limbal": ir["limbal"]}
        spec["skin"]["eyes"] = e1
        notes.append(f"  skin.eyes: iris {e0.get('iris')} -> {e1['iris']}, iris_inner {e0.get('iris_inner')} -> {e1['iris_inner']}, limbal {e0.get('limbal')} -> {e1['limbal']} "
                     "(GNM's own eyeball and pupil are kept: only its painted iris changes)")
    h = spec["skin"].get("hair") or {}
    if h.get("stubble"):
        if stubble == "picture":   # one or the other: the picture's own beard shadow, not ours on top of it
            spec["skin"]["hair"] = {k: v for k, v in h.items() if k != "stubble"}
            notes.append(f"  skin.hair.stubble {json.dumps(h['stubble'])} REMOVED: the picture carries its own beard shadow (stubble=\"keep\" keeps "
                         "ours: its strands / relief then stand on the picture's shadow)")
        else:
            notes.append("  NOTE: skin.hair.stubble kept AND the picture carries its own beard shadow: the projection covers our painted shadow; "
                         "our stubble's relief / strands stand on the picture's")
    if dst != name:
        rj = copy.deepcopy(bi._refs(name))
        if rj.get("blockin"):
            rj["blockin"] = {**rj["blockin"], "root": dst}
        bi._save(dst, spec, note or f"skin projection of {name}'s references", rj)
    else:
        store.save(dst, spec, note or "skin projection: the references projected, de-lit, filled")
    r["text"] += "\n" + "\n".join([f"  saved: {dst} skin.projection (files in {d})"] + notes)
    r["dir"] = str(d)
    return r


# ---------------------------------------------------------------- the fitted light as a scene light

def stage_light(light: dict, n: int = 24, angle: float = 55.0) -> dict:
    """A view's FITTED light ({"sh": (3, 9), "key": {"dir", "rgb"} | None}: make()'s report, views.<i>.light) as a
    scene lighting dict (suns + a uniform world; Standard view, 0 EV: the picture's own exposure): the order-2 light as
    the fewest non-negative soft suns of a fixed direction set + ambient whose order-2 projection it is (NNLS per
    channel), the key as its own sun. For renders set beside the picture: what the tool believes lit it."""
    from scipy.optimize import nnls
    from . import likeness as lk
    sh = np.asarray(light["sh"], float)
    Dq = _dirs(4000)
    Yq = lk.sh9(Dq)
    G = 4 * np.pi / len(Dq) * Yq.T @ Yq
    D = _dirs(n)
    A = np.linalg.solve(G, np.pi * lk.sh9(D).T)              # (9, n): a unit sun's order-2 coefficients
    amb = np.zeros((9, 1))
    amb[0, 0] = 1.0
    M = np.c_[A, amb]
    # ONE set of suns from the light's LUMINANCE, all of the light's own mean colour (solving each channel by itself put
    # differently coloured suns in different directions: colour fringes under the chin and round the nose)
    x = nnls(M, Y @ sh)[0]
    # the light's colour: skin_project's own measure (the fitted shading's median colour on the trusted skin) when the
    # report has it, else the order-0 coefficients' ratio; neutral when that is degenerate (a fit with a negative mean)
    dc = np.asarray(light.get("colour") or sh[:, 0], float)
    dc = dc / max(float(dc @ Y), 1e-9) if (dc > 0.05 * abs(dc).max()).all() and dc.min() > 0 else np.ones(3)
    cm = float(dc.max())
    lights = []
    for i in range(n):
        if x[i] > 0.01 * float(x[:n].max() + 1e-9):
            lights.append({"dir": [round(float(v), 4) for v in D[i]], "energy": round(float(np.pi * x[i] * cm), 4),
                           "color": [round(float(v), 4) for v in dc / cm], "angle": angle, "specular": 0.3})
    X = np.zeros((n + 1, 3))
    X[n] = x[n] * dc
    k = light.get("key")
    if k:
        m = float(max(k["rgb"]))
        if m > 0:
            lights.insert(0, {"dir": list(k["dir"]), "energy": round(float(np.pi * m), 4), "color": [round(float(v) / m, 4) for v in k["rgb"]],
                              "angle": 2 * KEY_DISC})
    a = X[n]
    am = float(max(a.max(), 1e-4))
    return {"lights": lights or [{"dir": [0, -1, 0.3], "energy": 0.0, "angle": angle}],
            "world": {"color": [round(float(v) / am, 4) for v in a], "strength": round(am, 4)}, "view": "Standard", "exposure": 0.0}


# ---------------------------------------------------------------- the residual: procedural skin against the atlas

BANDS_MM = (6.0, 1.2)    # low: broader than the first; mid: between; fine: under the second


def residual(name: str, spec: dict | None = None, stride: int = 2, save: str | None = None, log=print) -> dict:
    """The model's PROCEDURAL skin (its own layers, no projection) against its de-lit atlas, where a picture vouches
    for the atlas: {"regions": {region: {"dE" (Lab, broad colour), "dL", "da", "db" (ours - atlas), "mid" (rms of the
    1.2-6 mm band's log-luminance difference), "fine" (ours' fine-band strength / the atlas': texture statistics, not
    a pointwise match), "texels"}}, "all": {...}, "map" (H, W, 3) uint8 (the broad + mid residual: red = ours darker,
    blue = ours lighter, grey = no picture), "text"}. The quality measure of a fitted skin, and its to-do list."""
    from PIL import Image
    from . import images, store
    spec = spec or store.load(name)
    pj = (spec.get("skin") or {}).get("projection") or {}
    if not pj.get("albedo") or not pj.get("confidence"):
        raise ValueError(f"residual: {name} has no skin projection with its confidence (skin_project first)")
    at = atlas(spec["base"])
    A = _lin(np.asarray(Image.open(images.id_path(pj["albedo"])).convert("RGB"), float) / 255.0)[at["ii"], at["jj"]]
    cf = np.asarray(Image.open(images.id_path(pj["confidence"])).convert("RGB"), float)[..., 0][at["ii"], at["jj"]] / 255.0
    O = ours_albedo(at, spec, stride=stride, log=log)
    ok = cf > 0.6
    w = ok.astype(float)
    la, lo = np.log(np.maximum(A, 1e-4)), np.log(np.maximum(O, 1e-4))
    A_low, O_low = np.exp(_blur(at, la, w, BANDS_MM[0])), np.exp(_blur(at, lo, w, BANDS_MM[0]))
    a_mid = _blur(at, la @ Y, w, BANDS_MM[1]) - _blur(at, la @ Y, w, BANDS_MM[0])
    o_mid = _blur(at, lo @ Y, w, BANDS_MM[1]) - _blur(at, lo @ Y, w, BANDS_MM[0])
    a_fine = la @ Y - _blur(at, la @ Y, w, BANDS_MM[1])
    o_fine = lo @ Y - _blur(at, lo @ Y, w, BANDS_MM[1])
    dlab = lab(O_low) - lab(A_low)
    regs = {"ALL": np.ones(len(ok), bool), **region_masks(at)}
    out = {"regions": {}}
    for k, m in regs.items():
        q = m & ok
        if q.sum() < 300:
            continue
        d = dlab[q]
        out["regions"][k] = {"dE": round(float(np.linalg.norm(d, axis=1).mean()), 2), "dL": round(float(d[:, 0].mean()), 2),
                             "da": round(float(d[:, 1].mean()), 2), "db": round(float(d[:, 2].mean()), 2),
                             "mid": round(float(np.sqrt(np.mean((o_mid[q] - a_mid[q]) ** 2))), 4),
                             "mid_atlas": round(float(a_mid[q].std()), 4), "mid_ours": round(float(o_mid[q].std()), 4),
                             "fine": round(float(o_fine[q].std() / max(a_fine[q].std(), 1e-6)), 2), "texels": int(q.sum())}
    out["all"] = out["regions"].get("ALL")
    dl = (lo @ Y - la @ Y) - (o_fine - a_fine)                # broad + mid, signed
    img = np.full(at["shape"] + (3,), 90, np.uint8)
    v = np.clip(dl / 0.3, -1, 1)
    col = np.stack([np.where(v < 0, 255, 255 * (1 - v)), 255 * (1 - np.abs(v)), np.where(v > 0, 255, 255 * (1 + v))], 1)
    col = np.where(ok[:, None], col, 120)
    img[at["ii"], at["jj"]] = col.astype(np.uint8)
    out["map"] = img
    if save:
        Image.fromarray(img).save(save)
    L = [f"residual {name}: procedural skin against the de-lit atlas ({int(ok.sum())} texels a picture vouches for); broad colour Lab (ours - atlas), "
         "mid band (1.2-6 mm) rms of the log-luminance difference [the atlas' own / ours' strength there], fine band strength ours / atlas:"]
    for k, r in out["regions"].items():
        L.append(f"  {k:16s} dE {r['dE']:5.2f}  dL {r['dL']:+5.1f} da {r['da']:+5.1f} db {r['db']:+5.1f}   mid {r['mid']:.3f} [{r['mid_atlas']:.3f} / {r['mid_ours']:.3f}]   fine x {r['fine']:.2f}")
    out["text"] = "\n".join(L)
    return out


# ---------------------------------------------------------------- placed marks (moles), read in the atlas

MARK_MM = (0.5, 0.9, 1.5)   # mm: the blob detector's scales (a mark's radius is ~1.4 x the scale it answers at)
MARK_DARK = 0.10            # a mark is at least this much darker (log luminance, at its own scale) than its surroundings
MARK_ROUND = 0.45           # ... and round: the Hessian's smaller curvature over the larger (a line has ~0)
MARK_MAX = 16               # at most this many, the darkest first


def marks(name: str, spec: dict | None = None) -> dict:
    """Prominent dark MARKS (moles, large freckles) of the de-lit atlas, each placed where it is: {"marks": [{"at"
    [x, y, z] (the head at rest, world), "radius" m, "dark" (log luminance under its surroundings), "lab" (its
    colour against the skin round it), "region"}], "text"}. Only where a picture vouches for the texel directly; never
    on brows, lips, the lids, at the picture's own edges or where the model has a cavity. A mole is a placed mark, not
    noise: skin.features.moles.at takes the list."""
    from PIL import Image
    from scipy import ndimage
    from . import images, likeness as lk, store
    spec = spec or store.load(name)
    pj = (spec.get("skin") or {}).get("projection") or {}
    if not pj.get("albedo") or not pj.get("confidence"):
        raise ValueError(f"marks: {name} has no skin projection (skin_project first)")
    at = atlas(spec["base"])
    img = _lin(np.asarray(Image.open(images.id_path(pj["albedo"])).convert("RGB"), float) / 255.0)
    cf = np.asarray(Image.open(images.id_path(pj["confidence"])).convert("RGB"), float)[..., 0] / 255.0
    lum = np.log(np.maximum(img @ Y, 1e-4)).astype(np.float32)
    valid = image(at, np.ones(len(at["ii"]), bool), False)
    lum = np.where(valid, lum, float(np.median(lum[valid])))
    regs = region_masks(at)
    allow = np.zeros(len(at["ii"]), bool)
    for k, m in regs.items():
        if k not in ("lips", "brow"):
            allow |= m
    X = interp(at, at["V"])
    for Ve, _, _ in lk.model_mesh(spec["base"])["eyes"]:
        c_ = Ve.mean(0)
        allow &= np.linalg.norm(X - c_, axis=1) - float(np.linalg.norm(Ve - c_, axis=1).max()) > DETAIL_LID
    A = image(at, allow, False) & (ndimage.gaussian_filter((cf > 0.6).astype(np.float32), 2.0 / at["mm"]) > 0.9)
    best, scale = np.zeros(lum.shape, np.float32), np.zeros(lum.shape, np.float32)
    for mm in MARK_MM:
        s = mm / at["mm"]
        hxx = ndimage.gaussian_filter(lum, s, order=(0, 2)) * s * s
        hyy = ndimage.gaussian_filter(lum, s, order=(2, 0)) * s * s
        hxy = ndimage.gaussian_filter(lum, s, order=(1, 1)) * s * s
        tr, df = hxx + hyy, np.sqrt((hxx - hyy) ** 2 + 4 * hxy ** 2)
        l1, l2 = 0.5 * (tr + df), 0.5 * (tr - df)                 # both positive at a dark blob
        blob = np.where((l2 > 0) & (l2 > MARK_ROUND * l1), 0.5 * tr, 0.0)   # ~ the centre's depth under its surroundings
        take = blob > best
        best, scale = np.where(take, blob, best), np.where(take, mm, scale)
    peak = (best == ndimage.maximum_filter(best, int(2 * 2.0 / at["mm"]) | 1)) & (best > MARK_DARK) & A
    ys, xs = np.nonzero(peak)
    order = np.argsort(-best[ys, xs])[:MARK_MAX]
    idx = np.full(at["shape"], -1)
    idx[at["ii"], at["jj"]] = np.arange(len(at["ii"]))
    out = []
    for y, x in zip(ys[order], xs[order]):
        t = idx[y, x]
        if t < 0:
            continue
        r_px = 1.4 * scale[y, x] / at["mm"]
        yy, xx = np.mgrid[max(y - int(4 * r_px), 0):y + int(4 * r_px) + 1, max(x - int(4 * r_px), 0):x + int(4 * r_px) + 1]
        d = np.hypot(yy - y, xx - x)
        inn, ring = img[yy[d < 0.7 * r_px], xx[d < 0.7 * r_px]], img[yy[(d > 2 * r_px) & (d < 3.5 * r_px)], xx[(d > 2 * r_px) & (d < 3.5 * r_px)]]
        dl = lab(np.median(inn, 0)) - lab(np.median(ring, 0)) if len(inn) and len(ring) else np.zeros(3)
        out.append({"at": [round(float(v), 5) for v in X[t]], "radius": round(float(1.4 * scale[y, x] / 1000.0), 5), "dark": round(float(best[y, x]), 3),
                    "lab": [round(float(v), 1) for v in dl], "region": next((k for k, m in regs.items() if m[t]), "?")})
    L = [f"marks {name}: {len(out)} placed dark mark(s) read in the de-lit atlas (darkest first; radius mm, darkness, Lab against the skin round it):"]
    L += [f"  {m_['region']:14s} at {m_['at']}  r {1000 * m_['radius']:.1f}  dark {m_['dark']:.2f}  dLab {m_['lab']}" for m_ in out]
    return {"marks": out, "text": "\n".join(L)}
