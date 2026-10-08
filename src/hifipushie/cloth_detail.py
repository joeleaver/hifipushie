"""Fine folds authored on a draped garment, not simulated: what an artist sculpts or paints in after the drape.

A cloth sim's mesh sets the smallest fold it can make (1 cm triangles: no crest under ~7 mm, creases 6-11 mm wide where
real shirting's are 2.5-4.5 mm, cloth_audit.md), so cotton reads thick. Where real cloth would have buckled into
folds finer than the mesh, the sim's cloth is left COMPRESSED instead (shorter than its pattern across the fold that
didn't form: the inside of an elbow, the armpit, a waist gathered by a belt, a sleeve blousing onto its cuff). That
compression is the map of where the fine folds belong, which way they run (across the compression) and how deep they
are: a fold of wavelength L that takes up a compression c has amplitude ~ (L / pi) sqrt(c) (an inextensible buckle).

`compression(M, V)` reads it per vertex; `wrinkle_height` lays folds from it into a height map on the flat-pattern
atlas (anisotropic Gabor-like dabs: a few ridges across, long along the fold, wavelengths spread over the fabric's
range, sharp creases), which `cloth.detail_maps(extra=...)` adds to the sewing details before the normal map is
taken. Nothing here is specific to a garment: the folds come from the drape.
"""
from __future__ import annotations

import numpy as np

# per fabric: the spacing of its fine folds (m), from photos (cloth_audit.md: shirting 8.6-16 mm, wool coating
# 38-44 mm) and how sharp its creases are (the profile's exponent: 1 = a sine)
# fine_gain / density: how deep and how many the fine (normal map) folds are. Shirting is worn ironed: against a worn
# shirt photo (cloth_refs/shirt_worn_front.png, chest: band-passed luminance 1-4 mm / 4-15 mm = 0.33-0.44) the full
# set read as a net of creases (0.60-0.83); 0.45 x 0.6 brings it to the photo's
FOLDS = {"shirting": {"wavelength": (0.008, 0.017), "sharp": 0.75, "length": (0.03, 0.09), "fine_gain": 0.45,
                      "density": 0.6},
         "linen": {"wavelength": (0.008, 0.02), "sharp": 0.65, "length": (0.03, 0.10)},
         "jersey": {"wavelength": (0.012, 0.03), "sharp": 1.0, "length": (0.04, 0.12)},
         "denim": {"wavelength": (0.02, 0.045), "sharp": 0.8, "length": (0.05, 0.14)},
         "wool_coating": {"wavelength": (0.03, 0.06), "sharp": 1.0, "length": (0.08, 0.2)}}
FLOOR = 0.006  # compression under this is the sim's noise
C_MAX = 0.12  # (a triangle squashed further is crumpled, not folded)


def strain_field(M: dict, V: np.ndarray) -> tuple:
    """Per triangle: (smallest principal stretch, largest, the smallest's direction in pattern coordinates (m, 2),
    area in the pattern)."""
    uv, F = M["uv"], M["F"]
    a, b, c = uv[F[:, 0]], uv[F[:, 1]], uv[F[:, 2]]
    Dm = np.stack([b - a, c - a], -1)
    det = Dm[:, 0, 0] * Dm[:, 1, 1] - Dm[:, 0, 1] * Dm[:, 1, 0]
    ok = np.abs(det) > 1e-14
    inv = np.zeros_like(Dm)
    inv[ok, 0, 0], inv[ok, 0, 1] = Dm[ok, 1, 1] / det[ok], -Dm[ok, 0, 1] / det[ok]
    inv[ok, 1, 0], inv[ok, 1, 1] = -Dm[ok, 1, 0] / det[ok], Dm[ok, 0, 0] / det[ok]
    Ds = np.stack([V[F[:, 1]] - V[F[:, 0]], V[F[:, 2]] - V[F[:, 0]]], -1)
    G = Ds @ inv
    C = np.einsum("fki,fkj->fij", G, G)
    w, vec = np.linalg.eigh(C)
    return np.sqrt(np.maximum(w[:, 0], 0)), np.sqrt(np.maximum(w[:, 1], 0)), vec[:, :, 0], 0.5 * np.abs(det)


def compression(M: dict, V: np.ndarray, smooth: int = 3) -> tuple:
    """Per vertex: (compression 0..C_MAX: how much shorter than its pattern the cloth is across its most compressed
    direction, past the sim's noise; that direction in pattern coordinates (n, 2), unit). Averaged over the triangles
    round each vertex and smoothed `smooth` times over each piece."""
    lo, _, d, ar = strain_field(M, V)
    c = np.clip(1.0 - lo - FLOOR, 0.0, C_MAX)
    F = M["F"]
    n = len(M["uv"])
    ang = np.arctan2(d[:, 1], d[:, 0])
    acc = np.zeros((n, 3))  # c, c cos 2a, c sin 2a (a direction has no sign)
    wsum = np.zeros(n)
    for k in range(3):
        np.add.at(acc, F[:, k], (ar * c)[:, None] * np.c_[np.ones(len(F)), np.cos(2 * ang), np.sin(2 * ang)])
        np.add.at(wsum, F[:, k], ar)
    acc /= np.maximum(wsum, 1e-18)[:, None]
    E = np.unique(np.sort(np.r_[F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]], 1), axis=0)
    deg = np.bincount(E.ravel(), minlength=n).astype(float)
    for _ in range(smooth):
        nb = np.zeros_like(acc)
        np.add.at(nb, E[:, 0], acc[E[:, 1]])
        np.add.at(nb, E[:, 1], acc[E[:, 0]])
        acc = 0.5 * acc + 0.5 * nb / np.maximum(deg, 1)[:, None]
    a2 = 0.5 * np.arctan2(acc[:, 2], acc[:, 1])
    coh = np.hypot(acc[:, 1], acc[:, 2]) / np.maximum(acc[:, 0], 1e-12)  # 1 where the triangles agree on the direction
    return acc[:, 0] * np.clip(coh, 0, 1), np.c_[np.cos(a2), np.sin(a2)]


def fold_dabs(M: dict, V: np.ndarray, fabric: str = "shirting", stiff: np.ndarray | None = None, gain: float = 1.0,
              seed: int = 7, opts: dict | None = None) -> tuple:
    """The folds the drape V implies, as dabs in pattern coordinates: each one fold (a crest or a crease with its
    shoulders: a narrow envelope, so no ripple trains), long along the fold and a little curved, lying across the local
    compression (its direction jittered), its wavelength, length and depth drawn from the fabric's ranges. Two sizes:
    fine ones (the fabric's `wavelength`; they only fit a normal map) and big ones (`big` x that, sparse: a mesh of
    5-10 mm can carry them, so they go into the geometry and the silhouette). Fewer where the compression is even (a
    smooth band of compression makes a few folds, not a comb). Returns ({"p", "k" piece, "d", "lam", "len", "amp",
    "ph", "kap", "big"}, info)."""
    o = dict(FOLDS.get(fabric, FOLDS["shirting"]), **(opts or {}))
    c, d = compression(M, V)
    if stiff is not None:
        c = c * np.clip(1.0 - 1.5 * np.asarray(stiff), 0, 1)
    rng = np.random.default_rng(seed)
    F, uv = M["F"], M["uv"]
    a_, b_, c_ = uv[F[:, 0]], uv[F[:, 1]], uv[F[:, 2]]
    area = 0.5 * np.abs((b_ - a_)[:, 0] * (c_ - a_)[:, 1] - (b_ - a_)[:, 1] * (c_ - a_)[:, 0])
    cf = c[F].mean(1)
    # how uneven the compression is round each triangle (its corners' spread over their mean)
    un = np.clip((c[F].max(1) - c[F].min(1)) / np.maximum(cf, 1e-4) / 0.5, 0, 1)
    want = area * np.clip(cf / 0.02, 0, 1) * (0.45 + 0.55 * un)
    info = {"folded_area_m2": round(float((area * np.clip(cf / 0.02, 0, 1)).sum()), 4),
            "compression_p50_p95": [round(float(v), 4) for v in np.percentile(c, [50, 95])]}
    out = {k: [] for k in ("p", "k", "d", "lam", "len", "amp", "ph", "kap", "big")}
    if want.sum() <= 0:
        info["dabs"] = [0, 0]
        return {k: np.zeros((0, 2)) if k in ("p", "d") else np.zeros(0) for k in out}, info
    big = float(o.get("big", 2.8))
    counts = []
    for is_big, wl, ln_, dens in ((False, o["wavelength"], o["length"], float(o.get("density", 1.6))),
                                  (True, tuple(big * v for v in o["wavelength"]), tuple(1.8 * v for v in o["length"]),
                                   float(o.get("density_big", 0.7)))):
        lam_m, len_m = 0.5 * (wl[0] + wl[1]), 0.5 * (ln_[0] + ln_[1])
        n = int(min(float(o.get("max_dabs", 6000)), dens * want.sum() / (len_m * lam_m)))
        counts.append(n)
        if n <= 0:
            continue
        ti = rng.choice(len(F), n, p=want / want.sum())
        w = rng.dirichlet([1, 1, 1], n)
        cc = np.einsum("nk,nk->n", w, c[F[ti]])
        dd = d[F[ti][:, 0]]
        jit = rng.normal(0, np.radians(10.0), n)  # (a comb is every fold exactly parallel)
        dd = np.c_[dd[:, 0] * np.cos(jit) - dd[:, 1] * np.sin(jit), dd[:, 0] * np.sin(jit) + dd[:, 1] * np.cos(jit)]
        lam = np.exp(rng.uniform(np.log(wl[0]), np.log(wl[1]), n))
        ln = np.exp(rng.uniform(np.log(ln_[0]), np.log(ln_[1]), n)) * (0.6 + 0.8 * np.clip(cc / 0.04, 0, 1))
        amp = np.minimum(lam / np.pi * np.sqrt(np.maximum(cc, 0)) * gain, 0.22 * lam) * rng.uniform(0.5, 1.2, n)
        out["p"].append(np.einsum("nk,nkd->nd", w, uv[F[ti]]))
        out["k"].append(M["piece"][F[ti][:, 0]])
        out["d"].append(dd)
        out["lam"].append(lam)
        out["len"].append(ln)
        out["amp"].append(amp * (0.7 if is_big else float(o.get("fine_gain", 1.0))))
        out["ph"].append(rng.choice([0.0, np.pi], n) + rng.normal(0, 0.5, n))
        out["kap"].append(rng.normal(0, 0.35, n) / ln)  # a bow of ~ a third of a wavelength over its length
        out["big"].append(np.full(n, is_big))
    info["dabs"] = counts
    return {k: np.concatenate(v) if v else np.zeros(0) for k, v in out.items()}, info


def _dab(D: dict, i: int, du, dv, sharp: float):
    """Dab i's height at offsets (du, dv) (m, pattern axes) from its centre."""
    ex, ey = D["d"][i]
    l = -du * ey + dv * ex
    a = du * ex + dv * ey + D["kap"][i] * l * l  # across the fold (along the compression), bowed along it
    sa, sl = 0.5 * D["lam"][i], D["len"][i] / 2.4
    env = np.exp(-0.5 * (a / sa) ** 2 - 0.5 * (l / sl) ** 2)
    wave = np.cos(2 * np.pi * a / D["lam"][i] + D["ph"][i])
    return D["amp"][i] * env * np.sign(wave) * np.abs(wave) ** sharp


def height_at(D: dict, M: dict, big: bool | None = None, fabric: str = "shirting", opts: dict | None = None) -> np.ndarray:
    """The dabs' summed height at every vertex of M (pattern coordinates, each piece its own dabs). big: only the big
    folds (True), only the fine ones (False), or all."""
    sharp = float(dict(FOLDS.get(fabric, FOLDS["shirting"]), **(opts or {}))["sharp"])
    H = np.zeros(len(M["uv"]))
    for i in range(len(D["lam"])):
        if big is not None and bool(D["big"][i]) != big:
            continue
        sel = np.where(M["piece"] == D["k"][i])[0]
        q = M["uv"][sel] - D["p"][i]
        near = np.abs(q).max(1) < 3 * max(0.5 * D["lam"][i], D["len"][i] / 2.4)
        if near.any():
            H[sel[near]] += _dab(D, i, q[near, 0], q[near, 1], sharp)
    return H


def displace(M: dict, V: np.ndarray, D: dict, fabric: str = "shirting", opts: dict | None = None,
             stiff: np.ndarray | None = None, edge: float = 0.02, body=None) -> tuple:
    """V with the big folds in its geometry: each vertex out along its normal by the big dabs' height (outward only: a
    fold lifts off the body), fading to nothing within `edge` of a piece's outline (seams stay shut) and on interfaced
    cloth. "Out" is the garment's outside (cloth.oriented_faces): the pattern mesh winds each piece as its pattern
    lies, and on su_garrett's trousers the folds of the inward-wound back.L went INTO the thigh (111 faces inside the
    body after a clean sim). Returns (V, rms mm)."""
    from scipy.spatial import cKDTree
    h = height_at(D, M, True, fabric, opts)
    h = np.maximum(h, 0.0) + 0.35 * np.minimum(h, 0.0)
    bd = np.where(M["border"])[0]
    dist = cKDTree(M["uv"][bd]).query(M["uv"])[0] if len(bd) else np.full(len(V), 1.0)
    same = M["piece"][bd[cKDTree(M["uv"][bd]).query(M["uv"])[1]]] == M["piece"] if len(bd) else np.ones(len(V), bool)
    f = np.clip(dist / edge, 0, 1)
    h = h * np.where(same, f * f * (3 - 2 * f), 1.0)
    if stiff is not None:
        h = h * np.clip(1.0 - 1.5 * np.asarray(stiff), 0, 1)
    from .cloth import oriented_faces
    F = oriented_faces(M, V, body=body)
    fn = np.cross(V[F[:, 1]] - V[F[:, 0]], V[F[:, 2]] - V[F[:, 0]])
    N = np.zeros_like(V)
    for c_ in range(3):
        np.add.at(N, F[:, c_], fn)
    N /= np.maximum(np.linalg.norm(N, axis=1, keepdims=True), 1e-12)
    return V + N * h[:, None], float(np.sqrt(np.mean(h ** 2)) * 1000)


def wrinkle_height(M: dict, V: np.ndarray, uv: np.ndarray, side: float, T: int, fabric: str = "shirting",
                   stiff: np.ndarray | None = None, gain: float = 1.0, seed: int = 7, opts: dict | None = None,
                   dabs: dict | None = None, big: bool | None = None, out_sign: float = 1.0) -> tuple:
    """A height map (T, T; m; image rows run down, as cloth.detail_maps) of the folds the drape V implies (fold_dabs,
    or the `dabs` given), on the atlas `uv` (0..1; `side` m across). big False: the fine folds only (the big ones are
    in the geometry: displace). Interfaced cloth (stiff 0..1) takes none. Returns (height, info)."""
    from PIL import Image, ImageDraw
    o = dict(FOLDS.get(fabric, FOLDS["shirting"]), **(opts or {}))
    info = {}
    if dabs is None:
        dabs, info = fold_dabs(M, V, fabric, stiff, gain, seed, opts)
    mpt = side / T
    pid_img = Image.new("I", (T, T), 0)
    dr = ImageDraw.Draw(pid_img)
    off = {}
    for k in range(len(M["names"])):
        ring = np.where((M["piece"] == k) & M["border"])[0]
        if len(ring) >= 3:
            dr.polygon([(uv[i, 0] * T, (1 - uv[i, 1]) * T) for i in ring], fill=k + 1)
            off[k] = uv[ring[0]] * side - M["uv"][ring[0]]  # the atlas is each piece's pattern moved, at one scale
    PID = np.asarray(pid_img)
    H = np.zeros((T, T), np.float32)
    sharp = float(o["sharp"])
    for i in range(len(dabs["lam"])):
        if (big is not None and bool(dabs["big"][i]) != big) or int(dabs["k"][i]) not in off:
            continue
        c = (dabs["p"][i] + off[int(dabs["k"][i])]) / side
        r = int(np.ceil(3 * max(0.5 * dabs["lam"][i], dabs["len"][i] / 2.4) / mpt))
        cx, cy = c[0] * T, (1 - c[1]) * T
        x0, x1, y0, y1 = max(int(cx) - r, 0), min(int(cx) + r + 1, T), max(int(cy) - r, 0), min(int(cy) + r + 1, T)
        if x1 <= x0 or y1 <= y0:
            continue
        du = (np.arange(x0, x1) + 0.5 - cx)[None, :] * mpt
        dv = -(np.arange(y0, y1) + 0.5 - cy)[:, None] * mpt
        H[y0:y1, x0:x1] += np.where(PID[y0:y1, x0:x1] == int(dabs["k"][i]) + 1, _dab(dabs, i, du, dv, sharp), 0).astype(np.float32)
    if (PID > 0).any():
        info["height_mm_rms_p99"] = [round(float(np.sqrt(np.mean(H[PID > 0] ** 2)) * 1000), 3),
                                     round(float(np.percentile(np.abs(H[PID > 0]), 99)) * 1000, 2)]
    return H, info
