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


def _cells(shape, count, seed, aspect=1.0, warp=None, loose=0.0, local=False):
    """Voronoi on the torus: F1, F2 (tile units, across-the-cell distances with cells `aspect` x taller) and ids.
    `loose` 0..1: that share of the seeds lie anywhere instead of near their grid place (cells of every size: a
    jittered grid of tall cells read as a woven basket). `local`: also each pixel's offset from its cell's seed."""
    rng = np.random.default_rng(seed)
    h, w = shape
    nx = max(2, int(round(np.sqrt(count * aspect))))
    ny = max(2, int(round(count / nx)))
    gx, gy = np.meshgrid(np.arange(nx), np.arange(ny))
    pts = np.c_[(gx.ravel() + 0.15 + 0.7 * rng.random(nx * ny)) / nx, (gy.ravel() + 0.5 * (gx.ravel() % 2) + 0.1 + 0.8 * rng.random(nx * ny)) / ny % 1.0]
    if loose > 0:
        free = rng.random(len(pts)) < loose
        pts = np.where(free[:, None], rng.random((len(pts), 2)), pts)
    sc = np.array([1.0, 1.0 / aspect])  # compress y: cells come out `aspect` x taller
    yy, xx = np.mgrid[:h, :w]
    q = np.c_[(xx.ravel() + 0.5) / w, (yy.ravel() + 0.5) / h]
    if warp is not None:
        q = (q + warp.reshape(-1, 2)) % 1.0
    tree = cKDTree((pts % 1.0) * sc, boxsize=sc)
    d, i = tree.query((q % 1.0) * sc, k=2)
    if local:
        off = ((q % 1.0) - (pts % 1.0)[i[:, 0]] + 0.5) % 1.0 - 0.5
        return d[:, 0].reshape(h, w), d[:, 1].reshape(h, w), i[:, 0].reshape(h, w), len(pts), off.reshape(h, w, 2)
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
    elif kind == "plates":  # pine: long irregular plates of flaky layers between deep fissures of uneven width
        # (the first version, one even Voronoi with a thin black outline, read as tidy lozenges drawn in ink)
        grit = _noise(shape, 20, 110, seed + 11)
        rag = np.stack([_noise(shape, 6, 30, seed + 15) - 0.5, _noise(shape, 6, 30, seed + 16) - 0.5], -1) * 0.03
        warp2 = warp * 1.1 + rag
        f1, f2, ids, n = _cells(shape, 22, seed, aspect=2.4, warp=warp2, loose=0.7)  # the plates (of every size)
        wide = 0.012 + 0.04 * _noise(shape, 1, 5, seed + 7) ** 1.5  # a fissure opens and pinches along its run
        plate = np.clip((f2 - f1) / (0.35 * wide), 0, 1) ** 0.7  # thin cracks between neighbouring plates...
        b1, b2, bid, bn = _cells(shape, 9, seed + 31, aspect=2.6, warp=warp * 1.6 + rag, loose=0.8)  # ...and the deep wide fissures between blocks of them
        deep = np.clip((b2 - b1) / (2.6 * wide), 0, 1)
        plate = plate * (0.25 + 0.75 * deep ** 0.8)
        tone_b = np.random.default_rng(seed + 12).random(bn)[bid]
        g1, g2, gid, gn = _cells(shape, 70, seed + 21, aspect=2.0, warp=warp2)  # cracks across a plate: shallow, broken
        crack = 1 - (1 - np.clip((g2 - g1) / 0.012, 0, 1)) * _smooth(_noise(shape, 2, 9, seed + 8), 0.45, 0.6)
        rng = np.random.default_rng(seed + 9)
        tone = rng.random(n)[ids]
        lay = mid + 0.5 * _noise(shape, 2, 6, seed + 5) + 0.35 * rng.random(gn)[gid]
        flakes = np.floor(lay * 4.5) / 4.5  # stepped papery layers on the plate
        height = plate * (0.42 + 0.38 * flakes + 0.1 * tone) * (0.8 + 0.2 * crack) + 0.12 * (0.5 * fine + 0.5 * grit) * plate
        # Two colours (the photos, veg_refs/bark/pine_bark_*): the weathered top of each plate is grey-mauve
        # (`color`), the layers under it orange-red (`color2`): plate rims, the lower flake steps, fissure walls and
        # freshly shed plates; only the fissure floor is dark. One brown x a grey multiplier read as brown worms.
        fresh = (np.random.default_rng(seed + 13).random(n) < 0.2)[ids]
        top = _smooth(flakes + 0.25 * (tone - 0.5), 0.3, 0.75)
        tint = _smooth(plate, 0.2, 0.65) * (0.2 + 0.8 * top) * (1 - 0.5 * fresh * (1 - top)) + 0.25 * (grit - 0.5) * plate
        albedo = (0.42 + 0.58 * _smooth(plate, 0.0, 0.35)) * (0.6 + 0.4 * deep ** 0.6) + 0.25 * (tone - 0.5) + 0.12 * (tone_b - 0.5) + 0.14 * (flakes - 0.5) - 0.2 * (1 - crack) + 0.22 * (fine - 0.5) + 0.3 * (grit - 0.5)
        rough = 0.92 - 0.1 * plate
    elif kind == "scales":  # spruce: thin irregular flakes lying over one another, low contrast, fine at arm's length
        # (the first version, round Voronoi cells with dark grout, read as cobblestones / giraffe skin in the engine)
        # (the second, steps of a noise with their rims drawn, read as worms / camouflage: isolines close into loops)
        # Now shingles: cells of every size, each a flake fixed at its top whose lower edge stands proud of the one
        # under it; no grout, only the thin shadow under each free edge; pale patches a hand wide (lichen, wear).
        rag = np.stack([_noise(shape, 8, 40, seed + 15) - 0.5, _noise(shape, 8, 40, seed + 16) - 0.5], -1) * 0.02  # ragged flake edges
        f1, f2, ids, n, off = _cells(shape, 520, seed, aspect=1.3, warp=warp * 0.5 + rag, loose=0.75, local=True)
        rng = np.random.default_rng(seed + 9)
        tone = rng.random(n)[ids]
        lift = rng.random(n)[ids]
        ramp = np.clip(0.5 + off[..., 1] * 17.0, 0, 1)  # (image y runs down the trunk: the flake rises toward its lower edge)
        height = 0.3 + 0.38 * ramp * (0.5 + 0.5 * lift) + 0.16 * tone + 0.1 * fine + 0.08 * mid
        drop = np.clip(ndimage.maximum_filter(height, 3, mode="wrap") - height - 0.06, 0, 1)  # under a proud edge
        drop = ndimage.gaussian_filter(drop, 0.6, mode="wrap")
        patch = _noise(shape, 1, 4, seed + 14)
        albedo = 0.97 + 0.16 * (tone - 0.5) + 0.07 * (ramp - 0.5) - 1.5 * drop + 0.14 * (fine - 0.5) + 0.16 * (_smooth(patch, 0.4, 0.8) - 0.4)
        rough = 0.9 * np.ones(shape)
    else:  # lenticel: smooth, with dark lens dashes round the stem, peeling bands and a few black scars
        f1, f2, ids, n = _cells(shape, 110, seed, aspect=0.14)
        rng = np.random.default_rng(seed + 9)
        on = (rng.random(n) < 0.7)[ids]
        lens = (1 - _smooth(f1, 0.0, 0.03)) * on
        bands = _noise(shape, 2, 10, seed + 6, stretch=(6.0, 1.0))  # stretched round the stem
        peel = _smooth(bands, 0.62, 0.7)
        s1, s2, sid, sn = _cells(shape, 12, seed + 30, aspect=0.4, warp=warp)
        scar = (1 - _smooth(s1, 0.0, 0.13)) * (rng.random(sn) < 0.65)[sid]  # (the black marks that read from 20 m)
        ring = _smooth(_noise(shape, 1, 5, seed + 44, stretch=(8.0, 1.0)), 0.6, 0.75)  # darker bands round the stem
        scar = np.maximum(scar, 0.8 * ring * (0.4 + 0.6 * fine))
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
    out = {"height": height, "normal": nrm * 0.5 + 0.5, "albedo": albedo, "rough": np.clip(rough, 0.2, 1.0),
           "tile": list(K["tile"]), "depth": K["depth"]}
    if kind == "plates":
        out["tint"] = np.clip(ndimage.gaussian_filter(tint, 0.6, mode="wrap"), 0, 1)
    return out


def rgb(maps: dict, bark: dict) -> np.ndarray:
    """The bark's colour picture (h, w, 3) 0..1 in sRGB: albedo x `color`, or, for kinds with two colours (a `tint`
    map: 1 = `color`, 0 = `color2`), albedo x their mix."""
    c1 = np.asarray(bark.get("color", [0.5, 0.45, 0.4]), float)
    if "tint" in maps and bark.get("color2") is not None:
        t = maps["tint"][..., None]
        col = c1[None, None] * t + np.asarray(bark["color2"], float)[None, None] * (1 - t)
    else:
        col = c1[None, None]
    return np.clip(maps["albedo"][..., None] * col, 0, 1)


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
