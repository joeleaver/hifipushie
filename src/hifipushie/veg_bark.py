"""Bark as tiling maps per species: height, normal, albedo (a grey multiplier of the bark's colour) and roughness on
a torus (every term periodic: FFT-filtered noise, Voronoi with wrapped distances), laid on branches by UV (u round
the branch in whole repeats, v along it in metres / `tile[1]`).

Kinds: furrowed (oak, willow: long interlacing ridges with deep furrows), plates (pine: big flaky plates between
cracks), scales (spruce: small round scales), lenticel (birch: smooth pale bark with dark dashes round it and peeling
bands).
"""

from __future__ import annotations

import numpy as np
from scipy import ndimage
from scipy.spatial import cKDTree

KINDS = {  # tile = [m round the branch, m along it]
    "furrowed": {"tile": [0.5, 1.0], "depth": 0.022},
    "plates": {"tile": [0.6, 1.2], "depth": 0.018},
    "scales": {"tile": [0.3, 0.6], "depth": 0.006},
    "lenticel": {"tile": [0.4, 0.8], "depth": 0.0025},
}


def _noise(shape, lo, hi, seed, stretch=(1.0, 1.0)):
    """Periodic noise with wavelengths between hi and lo cycles per tile (after `stretch` of the axes), 0..1."""
    rng = np.random.default_rng(seed)
    h, w = shape
    fy = np.fft.fftfreq(h)[:, None] * h * stretch[1]
    fx = np.fft.fftfreq(w)[None, :] * w * stretch[0]  # (a stretched axis reads its waves longer)
    f = np.hypot(fx, fy)
    amp = np.where((f >= lo) & (f <= hi), 1.0 / np.maximum(f, 1e-6), 0.0)
    spec = amp * np.exp(2j * np.pi * rng.random((h, w)))
    n = np.real(np.fft.ifft2(spec))
    n -= n.min()
    return n / max(n.max(), 1e-12)


def _cells(shape, count, seed, aspect=1.0, warp=None):
    """Voronoi on the torus: F1, F2 (tile units, across-the-cell distances with cells `aspect` x taller) and ids."""
    rng = np.random.default_rng(seed)
    h, w = shape
    nx = max(2, int(round(np.sqrt(count * aspect))))
    ny = max(2, int(round(count / nx)))
    gx, gy = np.meshgrid(np.arange(nx), np.arange(ny))
    pts = np.c_[(gx.ravel() + 0.15 + 0.7 * rng.random(nx * ny)) / nx, (gy.ravel() + 0.5 * (gx.ravel() % 2) + 0.1 + 0.8 * rng.random(nx * ny)) / ny % 1.0]
    sc = np.array([1.0, 1.0 / aspect])  # compress y: cells come out `aspect` x taller
    yy, xx = np.mgrid[:h, :w]
    q = np.c_[(xx.ravel() + 0.5) / w, (yy.ravel() + 0.5) / h]
    if warp is not None:
        q = (q + warp.reshape(-1, 2)) % 1.0
    tree = cKDTree((pts % 1.0) * sc, boxsize=sc)
    d, i = tree.query((q % 1.0) * sc, k=2)
    return d[:, 0].reshape(h, w), d[:, 1].reshape(h, w), i[:, 0].reshape(h, w), len(pts)


def _smooth(x, a, b):
    t = np.clip((x - a) / (b - a), 0, 1)
    return t * t * (3 - 2 * t)


def bark_maps(kind: str = "furrowed", size: int = 256, seed: int = 0) -> dict:
    """{"height" 0..1, "normal" (h, w, 3) 0..1, "albedo" grey multiplier (mean ~1), "rough", "tile" [m, m],
    "depth" m}: `size` px round the branch, in proportion along it."""
    if kind not in KINDS:
        raise ValueError(f"bark kind {kind!r}: {sorted(KINDS)}")
    K = KINDS[kind]
    w = size
    h = int(round(size * K["tile"][1] / K["tile"][0]))
    shape = (h, w)
    fine = _noise(shape, 12, 80, seed + 1)
    mid = _noise(shape, 3, 12, seed + 2)
    warp = np.stack([(_noise(shape, 1, 4, seed + 3) - 0.5) * 0.12, (_noise(shape, 1, 4, seed + 4) - 0.5) * 0.12], -1)
    if kind == "furrowed":  # long ridges that fork and rejoin: tall cells, the furrow where two meet
        f1, f2, ids, n = _cells(shape, 26, seed, aspect=5.0, warp=warp)
        edge = (f2 - f1)
        ridge = _smooth(edge, 0.0, 0.045)
        tone = np.random.default_rng(seed + 9).random(n)[ids]
        height = ridge * (0.72 + 0.2 * mid + 0.08 * tone) + 0.1 * fine * ridge
        # cross checks on the ridges (old oak bark breaks into blocks)
        g1, g2, _, _ = _cells(shape, 60, seed + 20, aspect=0.6, warp=warp)
        height *= 0.8 + 0.2 * _smooth(g2 - g1, 0.0, 0.02)
        albedo = 0.55 + 0.65 * _smooth(height, 0.15, 0.85) + 0.25 * (tone - 0.5) + 0.2 * (fine - 0.5)
        rough = 0.95 - 0.1 * ridge
    elif kind == "plates":  # big plates, flaky in steps, between dark cracks
        f1, f2, ids, n = _cells(shape, 34, seed, aspect=2.2, warp=warp)
        edge = f2 - f1
        plate = _smooth(edge, 0.0, 0.018)
        rng = np.random.default_rng(seed + 9)
        tone = rng.random(n)[ids]
        flakes = np.floor((mid + 0.5 * _noise(shape, 2, 6, seed + 5)) * 4) / 4  # stepped layers
        height = plate * (0.55 + 0.3 * flakes + 0.1 * tone) + 0.06 * fine * plate
        albedo = 0.5 + 0.55 * plate + 0.35 * (tone - 0.5) + 0.3 * (flakes - 0.4) + 0.15 * (fine - 0.5)
        rough = 0.92 - 0.12 * plate
    elif kind == "scales":
        f1, f2, ids, n = _cells(shape, 90, seed, aspect=1.2, warp=warp * 0.5)
        edge = f2 - f1
        sc = _smooth(edge, 0.0, 0.02)
        tone = np.random.default_rng(seed + 9).random(n)[ids]
        height = sc * (0.6 + 0.3 * (1 - np.clip(f1 / 0.05, 0, 1)) + 0.1 * tone) + 0.08 * fine
        albedo = 0.6 + 0.45 * sc + 0.3 * (tone - 0.5) + 0.15 * (fine - 0.5)
        rough = 0.9 * np.ones(shape)
    else:  # lenticel: smooth, with dark lens dashes round the stem, peeling bands and a few black scars
        f1, f2, ids, n = _cells(shape, 110, seed, aspect=0.14)
        rng = np.random.default_rng(seed + 9)
        on = (rng.random(n) < 0.7)[ids]
        lens = (1 - _smooth(f1, 0.0, 0.03)) * on
        bands = _noise(shape, 2, 10, seed + 6, stretch=(6.0, 1.0))  # stretched round the stem
        peel = _smooth(bands, 0.62, 0.7)
        s1, s2, sid, sn = _cells(shape, 12, seed + 30, aspect=0.4, warp=warp)
        scar = (1 - _smooth(s1, 0.0, 0.085)) * (rng.random(sn) < 0.6)[sid]  # (the black marks that read from 20 m)
        ring = _smooth(_noise(shape, 1, 5, seed + 44, stretch=(8.0, 1.0)), 0.6, 0.75)  # darker bands round the stem
        scar = np.maximum(scar, 0.45 * ring * (0.5 + 0.5 * fine))
        height = 0.6 + 0.25 * peel - 0.5 * lens - 0.45 * scar + 0.06 * fine
        albedo = 1.0 + 0.1 * (bands - 0.5) + 0.06 * peel - 0.75 * lens - 0.8 * scar + 0.06 * (fine - 0.5)
        rough = 0.55 + 0.3 * lens + 0.3 * scar + 0.1 * fine
    height = np.clip(height, 0, 1)
    height = ndimage.gaussian_filter(height, 0.7, mode="wrap")
    albedo = np.clip(albedo, 0.08, 1.8)
    albedo = albedo / albedo.mean()
    # the normal from the height's slope (tangent space: x round the branch, y along it, +y up the image)
    px = K["tile"][0] / w
    dzdx = (np.roll(height, -1, 1) - np.roll(height, 1, 1)) * K["depth"] / (2 * px)
    dzdy = (np.roll(height, 1, 0) - np.roll(height, -1, 0)) * K["depth"] / (2 * px)
    nrm = np.stack([-dzdx, -dzdy, np.ones(shape)], -1)
    nrm /= np.linalg.norm(nrm, axis=2, keepdims=True)
    return {"height": height, "normal": nrm * 0.5 + 0.5, "albedo": albedo, "rough": np.clip(rough, 0.2, 1.0),
            "tile": list(K["tile"]), "depth": K["depth"]}


def tileability(a: np.ndarray) -> float:
    """The step across the wrap seam over the steps beside it (1 = seamless); the worse of both axes."""
    a = np.asarray(a, float)
    if a.ndim == 3:
        a = a.mean(2)
    out = 0.0
    for ax in (0, 1):
        d = np.abs(np.diff(np.concatenate([a, np.take(a, [0], axis=ax)], axis=ax), axis=ax))
        seam = np.take(d, [-1], axis=ax).mean()
        out = max(out, float(seam / max(np.delete(d, -1, axis=ax).mean(), 1e-12)))
    return out


def write(maps: dict, stem: str) -> dict:
    """<stem>_albedo.png (grey), _normal.png, _rough.png, _height.png; returns the paths."""
    from PIL import Image
    out = {}
    g = lambda x: Image.fromarray(np.clip(x * 255, 0, 255).astype(np.uint8))
    for k, im in (("albedo", g(maps["albedo"] * 0.5)), ("normal", g(maps["normal"])), ("rough", g(maps["rough"])),
                  ("height", g(maps["height"]))):
        out[k] = f"{stem}_{k}.png"
        im.save(out[k])
    return out
