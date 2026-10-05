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
FOLDS = {"shirting": {"wavelength": (0.008, 0.017), "sharp": 0.75, "length": (0.03, 0.09)},
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


def wrinkle_height(M: dict, V: np.ndarray, uv: np.ndarray, side: float, T: int, fabric: str = "shirting",
                   stiff: np.ndarray | None = None, gain: float = 1.0, seed: int = 7, opts: dict | None = None) -> tuple:
    """A height map (T, T; m; image rows run down, as cloth.detail_maps) of the fine folds the drape V implies, on
    the atlas `uv` (0..1; `side` m across). Interfaced cloth (stiff 0..1) takes none. Returns (height, info)."""
    from PIL import Image, ImageDraw
    o = dict(FOLDS.get(fabric, FOLDS["shirting"]), **(opts or {}))
    c, d = compression(M, V)
    if stiff is not None:
        c = c * np.clip(1.0 - 1.5 * np.asarray(stiff), 0, 1)
    rng = np.random.default_rng(seed)
    F = M["F"]
    mpt = side / T
    pid_img = Image.new("I", (T, T), 0)
    dr = ImageDraw.Draw(pid_img)
    for k in range(len(M["names"])):
        ring = np.where((M["piece"] == k) & M["border"])[0]
        if len(ring) >= 3:
            dr.polygon([(uv[i, 0] * T, (1 - uv[i, 1]) * T) for i in ring], fill=k + 1)
    PID = np.asarray(pid_img)
    H = np.zeros((T, T), np.float32)
    # dabs: centres drawn over the triangles by area x compression; each covers ~ length x 2 wavelengths
    a_, b_, c_ = M["uv"][F[:, 0]], M["uv"][F[:, 1]], M["uv"][F[:, 2]]
    area = 0.5 * np.abs((b_ - a_)[:, 0] * (c_ - a_)[:, 1] - (b_ - a_)[:, 1] * (c_ - a_)[:, 0])
    cf = c[F].mean(1)
    lam_m = 0.5 * (o["wavelength"][0] + o["wavelength"][1])
    len_m = 0.5 * (o["length"][0] + o["length"][1])
    want = area * np.clip(cf / 0.02, 0, 1)  # the area that folds (full where the cloth is 2% short)
    n_dabs = int(min(float(o.get("max_dabs", 6000)), float(o.get("density", 2.2)) * want.sum() / (len_m * 2 * lam_m)))
    info = {"dabs": n_dabs, "folded_area_m2": round(float(want.sum()), 4),
            "compression_p50_p95": [round(float(v), 4) for v in np.percentile(c, [50, 95])]}
    if n_dabs <= 0:
        return H, info
    ti = rng.choice(len(F), n_dabs, p=want / want.sum())
    w = rng.dirichlet([1, 1, 1], n_dabs)
    cu = np.einsum("nk,nkd->nd", w, uv[F[ti]])  # atlas position
    cc = np.einsum("nk,nk->n", w, c[F[ti]])
    dd = d[F[ti][:, 0]]  # (a direction: no sign to blend across the corners)
    pk = M["piece"][F[ti][:, 0]] + 1
    lam = rng.uniform(*o["wavelength"], n_dabs)
    ln = rng.uniform(*o["length"], n_dabs)
    amp = np.minimum(lam / np.pi * np.sqrt(np.maximum(cc, 0)) * gain, 0.22 * lam)
    ph = rng.uniform(0, 2 * np.pi, n_dabs)
    sharp = float(o["sharp"])
    for i in range(n_dabs):
        sa, sl = 0.75 * lam[i], ln[i] / 2.4
        r = int(np.ceil(3 * max(sa, sl) / mpt))
        cx, cy = cu[i, 0] * T, (1 - cu[i, 1]) * T
        x0, x1, y0, y1 = max(int(cx) - r, 0), min(int(cx) + r + 1, T), max(int(cy) - r, 0), min(int(cy) + r + 1, T)
        if x1 <= x0 or y1 <= y0:
            continue
        du = (np.arange(x0, x1) + 0.5 - cx)[None, :] * mpt
        dv = -(np.arange(y0, y1) + 0.5 - cy)[:, None] * mpt
        ex, ey = dd[i]
        a = du * ex + dv * ey  # across the fold (along the compression)
        l = -du * ey + dv * ex
        env = np.exp(-0.5 * (a / sa) ** 2 - 0.5 * (l / sl) ** 2)
        wave = np.cos(2 * np.pi * a / lam[i] + ph[i])
        wave = np.sign(wave) * np.abs(wave) ** sharp
        H[y0:y1, x0:x1] += np.where(PID[y0:y1, x0:x1] == pk[i], amp[i] * env * wave, 0).astype(np.float32)
    info["height_mm_rms_p99"] = [round(float(np.sqrt(np.mean(H[PID > 0] ** 2)) * 1000), 3),
                                 round(float(np.percentile(np.abs(H[PID > 0]), 99)) * 1000, 2)]
    return H, info
