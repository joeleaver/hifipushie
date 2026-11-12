"""The pipeline's steps: region masks, plain skin, the two bands, shine, pull-push, texture noise, detail, harmonise. Part of the skin projection (skin_project.py has the overview)."""
from __future__ import annotations

import numpy as np

from . import skin_project
from .skin_project import _sstep
from .skin_project_atlas import _blur, image, interp

def region_masks(at: dict) -> dict:
    """{region: (n,) bool} at the valid texels, from GNM's own vertex groups (a texel is in the first region that
    claims it; the vermilion wins over the lip skin regions)."""
    g = at["groups"]
    out = {}
    lips = np.maximum(interp(at, g["upper_lip"]), interp(at, g["lower_lip"])) > 0.5
    for k, names in skin_project.REGIONS.items():
        m = np.max([interp(at, g[n]) for n in names if n in g], 0) > 0.5
        out[k] = m & (~lips if k != "lips" else True)
    return out


def _plain(at: dict) -> np.ndarray:
    g = at["groups"]
    a = np.max([interp(at, g[n]) for n in skin_project.PLAIN if n in g], 0) > 0.5
    b = np.max([interp(at, g[n]) for n in skin_project.NOT_PLAIN if n in g], 0) > 0.3
    return a & ~b


def _two_band(at: dict, cols: list, ws: list) -> tuple:
    """Albedos (n, 3) with weights (n,) blended in two bands (log colour): the broad band with the weights as they
    are, the fine band from the strongest. Returns (colour, total weight, strongest index)."""
    Wt = np.sum(ws, 0)
    low_num, hi_num, hi_den = np.zeros((len(Wt), 3)), np.zeros((len(Wt), 3)), np.zeros(len(Wt))
    for c, w in zip(cols, ws):
        lg = np.log(np.maximum(c, 1e-4))
        lo = _blur(at, lg, (w > 0.02).astype(float), skin_project.BAND_MM)
        low_num += w[:, None] * lo
        w4 = w ** 4
        hi_num += w4[:, None] * (lg - lo)
        hi_den += w4
    out = low_num / np.maximum(Wt, 1e-6)[:, None] + hi_num / np.maximum(hi_den, 1e-12)[:, None]
    return np.exp(out), Wt, np.argmax(ws, 0)


def _shine(at: dict, col: np.ndarray, w: np.ndarray) -> np.ndarray:
    yy = col @ skin_project.Y
    loc = _blur(at, yy, (w > 0.3).astype(float), 10.0)
    top = skin_project.SHINE[0] * np.maximum(loc, 1e-4)
    over = np.maximum(yy - top, 0.0)
    return col * ((np.minimum(yy, top) + skin_project.SHINE[1] * over) / np.maximum(yy, 1e-5))[:, None]


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
    sig = [skin_project.BAND_MM / at["mm"] / k for k in (1.0, 2.0, 4.0)]      # texels
    lum = logc @ skin_project.Y
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
    hp = logc - _blur(at, logc, trust.astype(float), skin_project.BAND_MM)
    q = trust & np.isfinite(hp).all(1)
    k = np.array([float(np.median(np.abs(hp[q, c]))) for c in range(3)]) / max(float(np.median(np.abs(hp[q] @ skin_project.Y))), 1e-9) if q.sum() > 500 else np.ones(3)
    return noise[:, None] * np.clip(k, 0.5, 1.6), {"bands_mm": [round(s * at["mm"], 2) for s in sig], "std": [round(s, 4) for s in stds]}


def _detail(at: dict, col: np.ndarray, trust: np.ndarray) -> tuple:
    """The fine relief map: dark LINES of the albedo (a ridge detector on log luminance at DETAIL_MM), kept where
    their directions agree over COHERENT_MM (a wrinkle bundle; hairs, specks and freckles do not). Returns ((n,)
    0..1 groove strength, notes)."""
    from scipy import ndimage
    lum = np.log(np.maximum(col @ skin_project.Y, 1e-4))
    Lm = image(at, lum.astype(np.float32))
    M = image(at, np.ones(len(lum), np.float32))
    Lm = np.where(M > 0, Lm, float(np.median(lum)))
    best = np.zeros(at["shape"], np.float32)
    Jxx, Jxy, Jyy = (np.zeros(at["shape"], np.float32) for _ in range(3))
    for mm in skin_project.DETAIL_MM:
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
    sc = skin_project.COHERENT_MM / at["mm"]
    coh = np.hypot(ndimage.gaussian_filter(Jxx, sc), ndimage.gaussian_filter(Jxy, sc)) / np.maximum(ndimage.gaussian_filter(Jyy, sc), 1e-6)
    v = best[at["ii"], at["jj"]]
    ref = float(np.percentile(v[trust], 99)) if trust.sum() > 1000 else 0.0
    g = _sstep((v - skin_project.LINE[0]) / skin_project.LINE[1]) * _sstep((coh[at["ii"], at["jj"]] - 0.25) / 0.3)
    return g, {"line_p99": round(ref, 4), "coherent_share": round(float((coh[at["ii"], at["jj"]][trust] > 0.4).mean()), 3) if trust.any() else 0.0}


def _bleed(img: np.ndarray, valid: np.ndarray) -> np.ndarray:
    from scipy import ndimage
    idx = ndimage.distance_transform_edt(~valid, return_distances=False, return_indices=True)
    return img[idx[0], idx[1]]


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
        d = d - (d @ skin_project.Y)[:, None]                                  # chroma only
        sm = _blur(at, d, ov, skin_project.HARMONISE_MM)
        has = _blur(at, ov, None, skin_project.HARMONISE_MM) > 0.05
        fill = _pull_push(at, sm, has.astype(float), np.median(sm[has], 0) if has.any() else np.zeros(3), reaches=(10.0, 25.0, 60.0))
        corr[vi] = np.where(has[:, None], sm, fill)
    for vi, c in corr.items():
        cols[vi] = cols[vi] * np.exp(-0.5 * c)                    # each view half way: the pair meet in the middle
    rep["harmonised"] = {str(vi): round(float(np.median(np.linalg.norm(c, axis=1))), 4) for vi, c in corr.items()}
