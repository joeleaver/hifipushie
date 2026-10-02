"""Tiling rock detail: the rock's grain below ~0.5 m as a small seamless material, laid along the bedding.

Detail by scale (agreed 2026-10-01): geometry carries >= ~1 m (landform, cliffs, beds, blocks); each tile's unique maps
carry the macro (colour, staining, AO, layer weights, the normal of the >= 0.5 m structure) at a few texels/m; what
is finer (grain, small facets, hairline fractures, laminae, crustose lichen) is the same everywhere on one kind of
rock, so it is authored once per rock type as a tileable swatch, and the engine draws it sharp at any distance.

`swatch(rock)`: a SIZE x SIZE m patch of rock face at RES texels/m (s along the strike, t up the beds): polygonal
fracture facets at three sizes (`periodic_cells`: Voronoi planes on a torus, sizes varying place to place), FFT spectra
(periodic by construction), cracks on facet nets' zero lines, clustered pits, veins, per-facet tones. Every term is
periodic in both directions, so the swatch tiles exactly (never cropped and cross-faded); `tileability` measures the
wrap seam like the tile border checks. Its settings (TUNE) are tuned toward CC0 photoscans by `swatch_stats` (slope and
albedo per octave, edges, fractures; 2026-10-01: the scans had 3x our slope and 5-10x our albedo variation in every
octave). `scan_swatch(set)` takes a scan (asset pack rock_scans) as the swatch instead (export cfg detail_source).

`DetailProjection`: where the swatch lies. Strike-binned planar projection: BINS vertical planes round the compass
(u = p . d_k, to the right as one faces the rock) plus the top plane, v = the bed coordinate (z + the beds' offset:
terrain_rock.bed_offset + the wander, the same coordinate the solid rock's beds use), so the swatch's grain and laminae
run along the beds and are never stretched by more than 1 / cos(22.5 deg) = 1.08. Which planes apply follows the
rock's normal averaged over RADIUS (a pure function of position: tiles agree at their borders, LODs agree). Exported
per cliff-tile vertex as `_DETAIL` (strike x, y, side share, bed coordinate) for shaders that blend the two nearest planes
and the top (seamless, like triplanar), and as a UV set (each triangle on its nearest plane: stock engine detail maps
on a UV channel; seams where the plane changes). A single global UV can't follow the strike: round every peak the
faces close into a ring, and a function's gradient can't circulate (a least-squares strike coordinate came out at
0.37 m per metre on the alps wall: the swatch stretched 2.7x).
"""
from __future__ import annotations

import math

import numpy as np
from scipy import ndimage

from . import noise
from . import terrain_facets as tf

SIZE = 4.0        # m: the swatch's side
RES = 256         # texels per metre (1024 x 1024)


def smoothstep(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3 - 2 * t)


# ---------------------------------------------------------------- periodic pieces

def periodic_facets(n, L, size, seed, stretch=1.0):
    """terrain_facets' irregular planar facets (~`size` m, stretched `stretch` up the face) on an n x n grid over an
    L x L torus (rows = t up, columns = s along). The facet size is rounded so the seed grid's cells fit the period
    exactly (within a few %). -1..1."""
    nx = max(3, int(round(L / (size * tf.CELL))))
    ny = max(3, int(round(L / (size * stretch * tf.CELL))))
    Px, Py = nx * tf.CELL, ny * tf.CELL  # the period in facet units
    pts, ids = tf._seeds(np.array([-tf.PAD, -tf.PAD]), np.array([Px + tf.PAD, Py + tf.PAD]), seed, period=(nx, ny))
    val = 2 * noise._hash(ids[:, 0], ids[:, 1], ids[:, 2], seed + 9) - 1
    from scipy.spatial import Delaunay
    tri = Delaunay(pts)
    g = (np.arange(n) + 0.5) / n
    S, Tt = np.meshgrid(g * Px, g * Py)
    q = np.c_[S.ravel(), Tt.ravel()]
    s = tri.find_simplex(q)
    Tr = tri.transform[s]
    bc = np.einsum("nij,nj->ni", Tr[:, :2], q - Tr[:, 2])
    out = (np.c_[bc, 1 - bc.sum(1)] * val[tri.simplices[s]]).sum(1)
    return np.clip(tf.GAIN * out, -1, 1).reshape(n, n)


def spectral(n, beta, seed, stretch=(1.0, 1.0), lo=4.0):
    """Periodic noise (as terrain_bake._spectral: random phases, 1/f^beta), zero mean, about -1..1, with nothing
    longer than a `lo`-th of the swatch: a feature as big as the swatch repeats visibly (one lichen patch a tile)."""
    rng = np.random.default_rng(seed)
    fx = np.fft.fftfreq(n)[None, :] * n * stretch[0]  # cycles per swatch
    fy = np.fft.fftfreq(n)[:, None] * n * stretch[1]
    f = np.sqrt(fx * fx + fy * fy)
    amp = np.where(f > 0, np.maximum(f, 1e-9) ** -beta, 0.0) * smoothstep(0.5 * lo, lo, f)
    z = np.real(np.fft.ifft2(amp * np.exp(2j * np.pi * rng.random((n, n)))))
    return 2 * (z - z.mean()) / max(np.ptp(z), 1e-9)


def _wrap_edt(mask):
    """Distance (texels) from each True texel to the nearest False one, on the torus (computed on a 3x3 tiling)."""
    n0, n1 = mask.shape
    big = np.tile(mask, (3, 3))
    d = ndimage.distance_transform_edt(big)
    return d[n0:2 * n0, n1:2 * n1]


def _torus_grid(n, L):
    """Texel centres (n*n, 2) on the L x L torus: columns s along, rows t up."""
    g = (np.arange(n) + 0.5) * (L / n)
    S, Tt = np.meshgrid(g, g)
    return np.c_[S.ravel(), Tt.ravel()]


def _wrapd(d, L):
    return d - L * np.round(d / L)


def periodic_cells(n, L, size, seed, stretch=1.0, vary=1.5, warp=0.12, slope=0.08, step=0.004, cup=0.004, soft=0.12,
                   blend=2.0):
    """Polygonal facets on the L x L torus: Voronoi cells of seeds whose density changes place to place (`vary`: cells
    from ~0.5x to ~2.5x `size` m; one size everywhere read as a regular quilt), stretched `stretch` up the face, edges
    bent a little (`warp` x size: straight polygon sides read as cut). Each cell is its own fracture plane: tilted
    (`slope`), set up or down (`step` m) and cupped (`cup` m over its size: conchoidal); neighbouring planes meet in a
    step softened over `blend` texels, so the field is continuous (the Delaunay facets met in creases only, as
    triangles: the "faceted plaster" at 10 m). Returns (height m, cell id, distance to the cell's edge m) as n x n."""
    from scipy.spatial import cKDTree
    rng = np.random.default_rng(seed)
    m = max(4, int(round(2.0 * L / size)))  # (candidates on a jittered grid at half the size; a quarter kept)
    sp = L / m
    I, J = np.meshgrid(np.arange(m), np.arange(m))
    pts = (np.c_[I.ravel(), J.ravel()] + rng.random((m * m, 2))) * sp
    dens = spectral(64, 1.6, seed + 1, lo=2)
    di = np.floor(pts / L * 64).astype(np.int64) % 64
    keep = rng.random(len(pts)) < np.clip(0.25 * np.exp(vary * dens[di[:, 1], di[:, 0]]), 0.02, 1.0)
    pts = pts[keep]
    k = len(pts)
    g = rng.normal(0.0, slope, (k, 2))
    a = rng.uniform(-1.0, 1.0, k) * step
    c = rng.uniform(0.2, 1.0, k) * cup
    q = _torus_grid(n, L)
    w = np.c_[spectral(n, 3.0, seed + 2, lo=6).ravel(), spectral(n, 3.0, seed + 3, lo=6).ravel()]
    q = np.mod(q + warp * size * w, L)
    sc = np.array([1.0, 1.0 / stretch])
    K = 6
    d, i = cKDTree(pts * sc, boxsize=[L, L / stretch]).query(q * sc, k=K)
    # the planes blended by a soft-min of the distances (a partition of unity over the K nearest: continuous
    # everywhere; blending only the two nearest jumped wherever the second-nearest changed, a thin line from every
    # corner). How soft changes place to place: crisp steps in some patches, soft swells in others (every edge crisp
    # read as crazed paint or dried mud). The softness is a share of the LOCAL seed spacing (from the density field):
    # a share of `size` let the 7th-nearest seed carry weight where the cells were small, and its coming and going
    # speckled those patches
    qi = (q / L * 64) % 64
    p_loc = np.clip(0.25 * np.exp(vary * ndimage.map_coordinates(dens, [qi[:, 1] - 0.5, qi[:, 0] - 0.5], order=1,
                                                                  mode="grid-wrap")), 0.02, 1.0)
    spacing = sp / np.sqrt(p_loc)
    cr = smoothstep(-0.55, -0.15, spectral(n, 3.0, seed + 4, lo=4).ravel())  # (1 = soft; smooth: noise in the
    # softness shook the far planes' small weights and speckled the crisp patches)
    sig = np.minimum(blend * L / n * (1 - cr) + soft * size * cr, 0.12 * spacing)
    w = np.exp(-(d - d[:, :1]) / sig[:, None])
    w /= w.sum(1, keepdims=True)
    h = np.zeros(len(q))
    for col in range(K):
        j = i[:, col]
        dx = _wrapd(q - pts[j], L)
        h += w[:, col] * (a[j] + (g[j] * dx).sum(1) + c[j] * (dx * dx).sum(1) / size ** 2)
    e = 0.5 * (d[:, 1] - d[:, 0])
    return h.reshape(n, n), i[:, 0].reshape(n, n).astype(np.int64), e.reshape(n, n)


def periodic_pits(n, L, seed, clusters=22, per=12, lone=60, r_med=0.0045, spread=0.12, elong=1.3):
    """Solution pits on the torus: clustered (they gather where water sits) plus a few alone, radii log-normal about
    `r_med` m (3-25 mm), a little longer along the beds, each a crisp-rimmed cup (depth ~0.7 radius; soft blobs from a
    thresholded noise read as cauliflower at 10 m). Returns (depth m >= 0, inside 0..1)."""
    from scipy.spatial import cKDTree
    rng = np.random.default_rng(seed)
    cen = rng.random((clusters, 2)) * L
    cnt = rng.poisson(per, clusters)
    P = np.concatenate([np.repeat(cen, cnt, 0) + rng.normal(0.0, spread, (cnt.sum(), 2)) * np.array([1.6, 0.8]),
                        rng.random((lone, 2)) * L])
    P = np.mod(P, L)
    R = np.clip(r_med * np.exp(rng.normal(0.0, 0.55, len(P))), 0.003, 0.025)
    el = rng.uniform(1.0, elong + 0.3, len(P))      # (each its own shape: longer along the beds, turned +-35 deg)
    ang = rng.uniform(-0.6, 0.6, len(P))
    q = _torus_grid(n, L)
    d, i = cKDTree(P, boxsize=[L, L]).query(q, k=4, distance_upper_bound=0.035)
    depth = np.zeros(len(q))
    inside = np.zeros(len(q))
    tex = L / n
    for col in range(4):
        ok = np.isfinite(d[:, col])
        j = i[ok, col]
        dx = _wrapd(q[ok] - P[j], L)
        ca, sa = np.cos(ang[j]), np.sin(ang[j])
        rn = np.hypot((ca * dx[:, 0] + sa * dx[:, 1]) / (R[j] * el[j]), (ca * dx[:, 1] - sa * dx[:, 0]) * el[j] / R[j])
        edge = smoothstep(1.0 + 0.6 * tex / R[j], 1.0 - 0.6 * tex / R[j], rn)  # (the rim over ~1 texel)
        dep = (0.4 * np.sqrt(np.clip(1 - rn * rn, 0, 1)) + 0.1) * R[j] * edge
        depth[ok] = np.maximum(depth[ok], dep)
        inside[ok] = np.maximum(inside[ok], edge)
    return depth.reshape(n, n), inside.reshape(n, n)


def _veins(n, L, seed, texel):
    """Calcite veins: thin pale lines (1.5-4 mm half-width) on the zero lines of two periodic fields stretched across
    each other (two sets that cross), only in patches. 0..1."""
    out = np.zeros((n, n))
    for k, st in enumerate(((1.0, 2.5), (2.2, 1.0))):
        V = spectral(n, 2.4, seed + 10 * k, stretch=st, lo=5)
        gx = (np.roll(V, -1, 1) - np.roll(V, 1, 1)) / (2 * texel)  # (wrapped: np.gradient's edges broke the tiling)
        gy = (np.roll(V, -1, 0) - np.roll(V, 1, 0)) / (2 * texel)
        dist = np.abs(V) / np.maximum(np.hypot(gx, gy), 1e-6)
        hw = 1.5 * texel + 0.0025 * (0.5 + 0.5 * spectral(n, 1.5, seed + 10 * k + 1, lo=8))
        on = smoothstep(0.3, 0.55, spectral(n, 1.6, seed + 10 * k + 2, lo=5))
        out = np.maximum(out, on * smoothstep(hw + texel, hw, dist))
    return out


# The procedural swatch's settings, tuned toward measured CC0 rock scans (swatch_stats; examples/scan_compare.py):
# cells = facet sizes (m) and their tilt (rms slope), step and cup (m); fractures = facet nets whose zero lines crack,
# their coverage (`on` thresholds), half-width and depth (m); albedo: per-octave tone noise, per-facet tones (each
# softened over `cell_soft` x its size), proud places lighter, weathering patches, grime round and under fractures.
# 2026-10-01 (rock5): albedo rms per octave 0.05-0.07 -> 0.13 at 0.25-1 m falling to 0.06-0.09 below 6 cm
# (rock_face_03: 0.10-0.12 flat; flat at that level read as speckled dirty granite on pebble's dark rock at 15 m, so
# the energy sits in the larger octaves), luminance std 0.195 -> 0.28 (0.32), percentiles 1/5/50/95/99 of the
# multiplier 0.49/0.60/0.96/1.54/1.84 (the scan's 0.50/0.60/0.96/1.54/1.85: a long pale tail, `skew`), correlation with
# high-passed height 0.12 -> 0.25 (0.23); hard per-facet tones that strong read as terrazzo, so they are softened
TUNE = {
    "cells": [{"size": 0.32, "stretch": 1.3, "vary": 1.6, "slope": 0.10, "step": 0.006, "cup": 0.005, "soft": 0.12},
              {"size": 0.09, "stretch": 1.1, "vary": 1.2, "slope": 0.12, "step": 0.002, "cup": 0.0015, "soft": 0.12},
              {"size": 0.03, "stretch": 1.0, "vary": 1.0, "slope": 0.14, "step": 0.0006, "cup": 0.0004, "soft": 0.2}],
    "rough": 0.0025, "rough_beta": 0.9,
    "fractures": [{"net": 0.7, "on": [0.0, 0.3], "width": 0.006, "depth": 0.025},
                  {"net": 0.3, "on": [0.1, 0.35], "width": 0.004, "depth": 0.012}],
    "scars": 0.035,
    "speck": 0.55, "speck_beta": 0.3, "cell_tone": [0.17, 0.2, 0.13], "cell_soft": 0.15, "proud": 0.07,
    "rough_var": 0.15, "patch": 0.22, "halo_m": 0.03, "streak_m": 0.15, "grime": 0.35, "skew": 1.0,
}


def swatch(rock=None, size=SIZE, res=RES, seed=None):
    """The detail swatch of one rock type: {"height" (m, outward), "normal" (unit, tangent space: x along s, y up t,
    z out), "albedo" (a multiplier on the macro colour, mean 1 per channel), "rough" (a multiplier, mean 1), "cavity"
    (0..1)}; arrays rows = t up. Rock character at several scales, each periodic on the swatch:
    - planes: irregular facets 0.45 / 0.16 / 0.07 m (terrain_facets' seeds on a torus), the bigger ones stretched up
      the face like the rock's own;
    - fractures: few, on a facet net's zero lines, broken into lengths, each its own width (2-12 mm) and depth (to ~3
      cm), a V with a dark floor (uniform thin creases read as crumpled paper);
    - spall scars: polygons where a coarser facet field stands high, a crisp rim and a conchoidal bowl 1-3 cm deep
      that is paler (fresh rock) and smoother;
    - pits: sparse round pits 3-10 mm, dark inside;
    - grain: mineral speckle in albedo (pale and dark grains, a few mm) and roughness (glassy grains smoother), a
      sub-millimetre-to-cm roughness in the relief;
    - weathering patches 0.3-1 m and sparse crustose lichen.
    Nothing longer than a quarter of the swatch (a swatch-sized feature repeats visibly)."""
    seed = int((rock or {}).get("seed", 4242) if seed is None else seed) + 900
    n = int(round(size * res))
    L = float(size)
    texel = L / n
    T = TUNE
    # planes: polygonal fracture facets at three sizes, each size varying place to place; most of the relief is here
    # (a rock face is rough everywhere: the scans' surface slope is 0.1-0.2 rms in every octave from 0.5 m to 1 cm)
    cells = [periodic_cells(n, L, c["size"], seed + 1 + 5 * k, stretch=c["stretch"], vary=c["vary"], slope=c["slope"],
                            step=c["step"], cup=c["cup"], soft=c["soft"]) for k, c in enumerate(T["cells"])]
    big_id, big_e = cells[0][1], cells[0][2]
    rough_rel = spectral(n, T["rough_beta"], seed + 3, lo=24)
    # fractures: on the zero lines of facet nets at two sizes, in lengths (`on`), each its own width and depth
    frac = np.zeros((n, n))
    frac_d = np.zeros((n, n))
    for k, fr in enumerate(T["fractures"]):
        net = periodic_facets(n, L, fr["net"], seed + 4 + 30 * k, stretch=1.6)
        wob = spectral(n, 1.8, seed + 5 + 30 * k, lo=8)
        on = smoothstep(fr["on"][0], fr["on"][1], spectral(n, 2.2, seed + 7 + 30 * k, lo=4))  # (lengths ~1 m:
        # shorter lengths read as dashes)
        wvar = np.clip(0.5 + 0.5 * spectral(n, 1.4, seed + 14 + 30 * k, lo=10), 0, 1)  # (each length its own width)
        # (half-width never under ~1.5 texels: thinner, the V was sampled on and off along its length and read as a
        # dashed line; a fracture fades out by depth and darkness (`on`), not by narrowing to nothing)
        width = 1.5 * texel + fr["width"] * wvar ** 2                            # half-width, m
        gnet = np.hypot((np.roll(net, -1, 1) - np.roll(net, 1, 1)) / (2 * texel),  # (the net's slope; wrapped)
                        (np.roll(net, -1, 0) - np.roll(net, 1, 0)) / (2 * texel))
        dist = np.abs(net + 0.04 * wob) / np.maximum(ndimage.gaussian_filter(gnet, 3, mode="wrap"), 0.5)
        v = np.clip(1 - dist / width, 0, 1) * on
        frac = np.maximum(frac, v)
        frac_d = np.maximum(frac_d, (0.006 + fr["depth"] * wvar) * v ** 0.7)  # V depth
    # spall scars: a few big facets spalled off: a polygonal rim, a shallow conchoidal bowl
    hc = noise._hash(big_id, np.zeros_like(big_id), np.zeros_like(big_id), seed + 15)
    region = hc < T["scars"]
    sdepth = 0.004 + 0.008 * noise._hash(big_id, np.ones_like(big_id), np.zeros_like(big_id), seed + 17)
    bowl = np.where(region, sdepth * (1 - np.exp(-big_e / 0.03)), 0.0)
    scar = smoothstep(0.0, 0.003, bowl)
    # pits: crisp cups, clustered
    pit_d, pit = periodic_pits(n, L, seed + 18)
    vein = _veins(n, L, seed + 40, texel)
    h = (sum(c[0] for c in cells) * (1 - 0.5 * scar) + T["rough"] * rough_rel - frac_d - bowl - pit_d
         + 0.0006 * vein)
    gx = (np.roll(h, -1, 1) - np.roll(h, 1, 1)) / (2 * texel)
    gy = (np.roll(h, -1, 0) - np.roll(h, 1, 0)) / (2 * texel)  # (rows = t up)
    nrm = np.stack([-gx, -gy, np.ones_like(h)], -1)
    nrm /= np.linalg.norm(nrm, axis=-1, keepdims=True)
    # cavity: concave places (the height's Laplacian over ~1 cm)
    lap = ndimage.laplace(ndimage.gaussian_filter(h, 1.5, mode="wrap"), mode="wrap") / (texel * texel)
    cav = np.clip(lap / max(np.percentile(np.abs(lap), 98), 1e-9), -1, 1)
    # albedo: variation in every octave (the scans' luminance varies 0.1-0.2 rms per octave, flat across them; ours had
    # 0.01-0.04 and read as stucco): each facet of each size its own tone, mineral grain, proud places lighter
    # (the scans: +0.2 correlation with high-passed height; concave places not darker on their own)
    g1 = spectral(n, 0.0, seed + 10, lo=64)                                  # (grain-sized white-ish noise)
    g2 = spectral(n, 0.0, seed + 20, lo=64)
    pale = smoothstep(0.3, 0.45, g1) * 0.3                                   # pale grains (quartz, calcite)
    dark = smoothstep(0.32, 0.47, g2) * 0.4                                  # dark grains
    dens = np.clip(0.55 + 0.6 * spectral(n, 1.4, seed + 23, lo=8), 0.1, 1.2)  # (grains cluster: no even salt and pepper)
    pale, dark = pale * dens, dark * dens
    tone = 1 + T["speck"] * spectral(n, T["speck_beta"], seed + 21, lo=8) + pale - dark
    for k, c in enumerate(cells):
        fh = noise._hash(c[1], np.full_like(c[1], 2), np.zeros_like(c[1]), seed + 16 + k)
        ct = (2 * fh - 1).astype(float)
        if T["cell_soft"] > 0:  # (each facet's tone fading into its neighbours': hard polygon tones read as terrazzo)
            ct = ndimage.gaussian_filter(ct, T["cell_soft"] * T["cells"][k]["size"] / texel, mode="wrap")
            ct = ct / max(ct.std(), 1e-9) * 0.577  # (the std a hard +-1 uniform tone has)
        tone = tone + T["cell_tone"][k] * ct
    hp = h - ndimage.gaussian_filter(h, 0.05 / texel, mode="wrap")
    tone = tone + T["proud"] * hp / max(hp.std(), 1e-9)
    # weathering: patches of rind darker or paler (0.2-1 m, irregular, soft-edged), grime soaked into the rock round
    # each fracture and washed down from it (the scans' darkest tones sit in and under their cracks, not on concave
    # facets)
    wz = spectral(n, 1.7, seed + 60, lo=6)
    tone = tone + T["patch"] * (smoothstep(-0.25, 0.35, wz) - 0.5) * 2
    halo = ndimage.gaussian_filter(frac, T["halo_m"] / texel, mode="wrap")
    halo = halo / max(halo.max(), 1e-9)
    kz = max(1, int(round(T["streak_m"] / texel)))
    ker = np.exp(-np.arange(4 * kz) / kz)
    # (rows = t up: grime runs down, so a row takes what the rows above it hold)
    streak = sum(ker[i] * np.roll(halo, -i, 0) for i in range(0, len(ker), max(1, kz // 8))) * max(1, kz // 8) / ker.sum()
    streak = streak / max(streak.max(), 1e-9)
    tone = tone * (1 - T["grime"] * np.clip(0.6 * halo + 0.7 * streak, 0, 1))
    # (skewed like the scans': a long pale tail, a short dark one (their 1st percentile 0.3-0.5 x the median, ours was
    # 0.3 with a symmetric spread: dark mottle on dark rock read as dirty granite)
    tone = np.exp(T["skew"] * (tone - 1.0))
    tone = (tone + 0.05 * scar) * (1 - 0.55 * frac) * (1 - 0.15 * pit)
    lic = smoothstep(0.66, 0.74, 0.5 + 0.5 * spectral(n, 1.8, seed + 11, lo=24)) * \
        smoothstep(0.0, 0.4, spectral(n, 1.6, seed + 12, lo=8)) * (1 - scar)
    # mineral variety: calcite veins (pale, cool), iron staining (warm, in patches, stronger in pits where water sits)
    iron = smoothstep(0.15, 0.6, spectral(n, 1.6, seed + 50, lo=8)) * (0.6 + 0.4 * pit)
    hue = 1 + iron[..., None] * np.array([0.10, 0.0, -0.13]) + vein[..., None] * np.array([0.14, 0.15, 0.17])
    alb = (tone[..., None] * hue) * (1 - 0.6 * lic[..., None]) + 0.6 * lic[..., None] * np.array([1.30, 1.34, 1.18])
    alb = np.clip(alb, 0.05, None)
    alb = alb / alb.reshape(-1, 3).mean(0)
    rough = 1 + T["rough_var"] * spectral(n, 1.0, seed + 13, lo=8) - 0.4 * pale + 0.08 * frac - 0.1 * scar \
        - 0.05 * lic - 0.15 * vein + 0.06 * pit
    rough = rough / rough.mean()
    return {"height": h, "normal": nrm, "albedo": alb, "rough": rough, "cavity": np.clip(-cav, 0, 1),
            "size_m": L, "texels_per_m": n / L, "n": n}


SCAN_PX = 1024  # a scan's swatch is resampled to this many pixels across


def scan_swatch(name, n=SCAN_PX):
    """A photoscanned rock texture set (asset pack "rock_scans", CC0, e.g. "rock_face_03") as a detail swatch, the same
    dict as `swatch` (rows = t up). Albedo: the scan's diffuse made linear and divided by its mean per channel (a
    multiplier on the macro colour: the scan's own hue goes, its variation stays); roughness the same; normal the
    tangent-space map as it is (OpenGL, +y up the image); height the displacement map in metres, its scale fitted so
    its slopes match the normal map's (the scan says 0..1, not metres)."""
    import json
    from PIL import Image
    from . import assets
    d = assets.pack("rock_scans")
    size = float(json.loads((d / "sets.json").read_text())[name]["size_m"])
    load = lambda k, ext: Image.open(d / name / f"{name}_{k}_2k.{ext}")
    rs = lambda im, mode: np.asarray(im.resize((n, n), mode), float)[::-1]  # (rows up)
    diff = rs(load("diff", "jpg").convert("RGB"), Image.LANCZOS) / 255
    lin = np.where(diff <= 0.04045, diff / 12.92, ((diff + 0.055) / 1.055) ** 2.4)
    alb = lin / lin.reshape(-1, 3).mean(0)
    rough = rs(load("rough", "jpg").convert("L"), Image.LANCZOS) / 255
    rough = rough / max(rough.mean(), 1e-6)
    nrm = rs(load("nor_gl", "png").convert("RGB"), Image.LANCZOS) / 255 * 2 - 1
    nrm /= np.maximum(np.linalg.norm(nrm, axis=-1, keepdims=True), 1e-9)
    disp = np.asarray(load("disp", "png"), float)
    disp = disp[..., 0] if disp.ndim == 3 else disp  # (some sets store it as RGBA)
    disp = np.asarray(Image.fromarray(disp.astype(np.float32), "F").resize((n, n), Image.LANCZOS), float)[::-1]
    disp = (disp - disp.mean()) / 65535.0
    texel = size / n
    gx = (np.roll(disp, -1, 1) - np.roll(disp, 1, 1)) / (2 * texel)
    gy = (np.roll(disp, -1, 0) - np.roll(disp, 1, 0)) / (2 * texel)
    tx, ty = -nrm[..., 0] / np.maximum(nrm[..., 2], 0.1), -nrm[..., 1] / np.maximum(nrm[..., 2], 0.1)
    k = float(((gx * tx).sum() + (gy * ty).sum()) / max((gx * gx).sum() + (gy * gy).sum(), 1e-12))
    h = disp * k
    lap = ndimage.laplace(ndimage.gaussian_filter(h, 1.5, mode="wrap"), mode="wrap") / (texel * texel)
    cav = np.clip(lap / max(np.percentile(np.abs(lap), 98), 1e-9), -1, 1)
    return {"height": h, "normal": nrm, "albedo": alb, "rough": rough, "cavity": np.clip(-cav, 0, 1), "size_m": size,
            "texels_per_m": n / size, "n": n, "source": f"scan:{name}", "height_scale_m": round(k, 4)}


def swatch_stats(S):
    """What a swatch is made of, comparable across procedural and scanned ones (the targets for tuning ours):
    - slope_octaves: rms surface slope (from the normal map) per octave of wavelength, 1 m down to 2 texels;
    - albedo: luminance std (of the multiplier), and its correlation with cavity (concave places darker: negative)
      and with high-passed height (proud places lighter: positive);
    - rough: std and p5/p95 of the roughness multiplier;
    - edges: the slope magnitude's p50/p90/p99 and its kurtosis (sharp-edged facets: flat faces + steep edges =
      a heavy tail);
    - fractures: valleys deeper than 2 mm (a 1.5 cm black top-hat of the height), as skeleton length per m2 and
      their widths (2 x the distance to the valley's edge along its skeleton) p50/p90 in mm."""
    from skimage.morphology import skeletonize
    n, L = S["n"], S["size_m"]
    tex = L / n
    nrm = S["normal"]
    sx, sy = -nrm[..., 0] / np.maximum(nrm[..., 2], 0.1), -nrm[..., 1] / np.maximum(nrm[..., 2], 0.1)
    fx = np.fft.fftfreq(n, tex)
    F = np.hypot(*np.meshgrid(fx, fx))
    P = np.abs(np.fft.fft2(sx)) ** 2 + np.abs(np.fft.fft2(sy)) ** 2
    lum = S["albedo"].mean(-1)
    PA = np.abs(np.fft.fft2(lum - lum.mean())) ** 2
    oct_ = []
    lam = 1.0
    while lam / 2 >= 2 * tex:
        band = (F >= 1 / lam) & (F < 2 / lam)
        oct_.append({"wavelength_m": [round(lam / 2, 4), lam], "slope_rms": round(float(np.sqrt(P[band].sum()) / n ** 2), 4),
                     "albedo_rms": round(float(np.sqrt(PA[band].sum()) / n ** 2), 4)})
        lam /= 2
    hp = S["height"] - ndimage.gaussian_filter(S["height"], 0.05 / tex, mode="wrap")
    cc = lambda a, b: float(np.corrcoef(a.ravel(), b.ravel())[0, 1])
    smag = np.hypot(sx, sy)
    k = ((smag - smag.mean()) ** 4).mean() / max(smag.var() ** 2, 1e-12)
    r = max(1, int(round(0.015 / tex)))
    th = ndimage.black_tophat(S["height"], size=2 * r + 1, mode="wrap")
    val = th > 0.002
    sk = skeletonize(val)
    wd = 2 * ndimage.distance_transform_edt(val)[sk] * tex * 1000
    return {"source": S.get("source", "procedural"), "size_m": L, "texels_per_m": round(n / L, 1),
            "slope_octaves": oct_,
            "albedo": {"lum_std": round(float(lum.std()), 3), "corr_cavity": round(cc(lum, S["cavity"]), 3),
                       "corr_height_hp": round(cc(lum, hp), 3)},
            "rough": {"std": round(float(S["rough"].std()), 3),
                      "p5_p95": [round(float(x), 3) for x in np.percentile(S["rough"], [5, 95])]},
            "edges": {"slope_p50_p90_p99": [round(float(x), 3) for x in np.percentile(smag, [50, 90, 99])],
                      "kurtosis": round(float(k), 2)},
            "fractures": {"length_m_per_m2": round(float(sk.sum() * tex / (L * L)), 2),
                          "width_mm_p50_p90": [round(float(x), 1) for x in np.percentile(wd, [50, 90])] if len(wd)
                          else None}}


def detail_swatch(rock=None, source="procedural"):
    """The swatch a detail layer uses: `swatch(rock)` or, for source "scan:<set>", `scan_swatch(<set>)`."""
    if source and str(source).startswith("scan:"):
        return scan_swatch(str(source)[5:])
    return swatch(rock)


def tileability(img):
    """How much the wrap seam stands out, per axis: the mean jump across it (last column -> first, top row -> bottom)
    over the mean jump between neighbours elsewhere. ~1.0 = invisible (the same measure as the tile border checks'
    jump excess)."""
    a = np.asarray(img, float)
    a = a.reshape(a.shape[0], a.shape[1], -1)
    dx = np.abs(np.diff(a, axis=1)).mean()
    dy = np.abs(np.diff(a, axis=0)).mean()
    wx = np.abs(a[:, 0] - a[:, -1]).mean()
    wy = np.abs(a[0] - a[-1]).mean()
    return [round(float(wx / max(dx, 1e-12)), 3), round(float(wy / max(dy, 1e-12)), 3)]


VARIATION_M = 24.0          # m: the anti-tiling mask's period on the detail UV
VARIATION_SCALE = 1.618     # the second sampling's size: the swatch at SIZE x this
VARIATION_OFFSET = [0.37, 0.71]  # its offset (in swatches)
TILE_LIMIT = 1.5  # a wrap seam jumping more than this x its neighbours' steps shows as a line every swatch


REF_VIEW = (1920, 60.0)     # px, deg: the camera the manifest quotes fade distances for


REPEAT = {"periodicity": 0.3, "contrast": 0.02, "px": 768, "span": 2.0}
# repetition shows where the detail's image has a periodicity above `periodicity` while its contrast is above
# `contrast` (2% luminance, about a just-noticeable step), measured on a `px`-pixel frontal view; the fade runs over
# `span` x the footprint where it starts. Calibrated on the alps wall at 40 m (n02/n03): every scan (1.5-2.7 m) showed a
# grid there and measures 0.37-0.61 at 37-53 m in local windows; ours (4 m) never does and stays 0.16-0.26


def detail_image(S, p, px=768, light=(-0.5, 0.45, 0.74)):
    """What the detail draws on a flat face seen square-on at footprint p m/px (px x px pixels): the swatch's albedo
    luminance x Lambert shading of its normal under a raking light (the detail's own contribution, the macro flat),
    laid as the shader lays it (the swatch at 1x and at VARIATION_SCALE x, mixed by the variation mask) and read from
    the mip level a GPU would pick for that footprint (2x2 box pyramid, bilinear)."""
    n, L = S["n"], S["size_m"]
    Lv = np.asarray(light, float) / np.linalg.norm(light)
    img0 = S["albedo"].mean(-1) * np.clip((S["normal"] * Lv).sum(-1), 0, 1)
    img0 = img0 / img0.mean()
    lvl = max(0, int(np.floor(np.log2(max(p * n / L, 1.0)))))
    mip = img0
    for _ in range(lvl):
        if mip.shape[0] < 2:
            break
        mip = 0.25 * (mip[0::2, 0::2] + mip[1::2, 0::2] + mip[0::2, 1::2] + mip[1::2, 1::2])
    m = mip.shape[0]
    g = (np.arange(px) + 0.5) * p
    U, V = np.meshgrid(g, g)
    samp = lambda u, v: ndimage.map_coordinates(mip, [(v / L * m - 0.5) % m, (u / L * m - 0.5) % m], order=1,
                                                mode="grid-wrap")
    a = samp(U, V)
    sc = VARIATION_SCALE
    b = samp(U / sc + VARIATION_OFFSET[0] * L, V / sc + VARIATION_OFFSET[1] * L)
    var = smoothstep(-0.25, 0.25, spectral(256, 2.0, 4242 + 990, lo=2))
    w = ndimage.map_coordinates(var, [(V / VARIATION_M * 256 - 0.5) % 256, (U / VARIATION_M * 256 - 0.5) % 256],
                                order=1, mode="grid-wrap")
    return a * (1 - w) + b * w


def repetition_profile(S, ps=None):
    """How visible the swatch's repetition is with the pixel footprint p: per p, the detail image's (`detail_image`)
    contrast (std of luminance) and periodicity (the largest autocorrelation above its radial mean, from 2 px out
    to a third of the view: the measure terrain_facets.periodicity uses for lattice patterns). A repeat shows where
    both are above REPEAT's limits. Returns [(p, contrast, periodicity)]."""
    ps = ps if ps is not None else np.geomspace(0.004, 0.25, 13)
    out = []
    px = REPEAT["px"]
    wn = px // 3  # (local windows: the anti-tiling mask mixes the two samplings over ~24 m, so a whole-view
    # autocorrelation averaged the repeat away, but within one patch of the mask the repeat is exact: rock_face_03 read
    # as a grid at 40 m (n03) while the whole-view measure gave 0.28)
    yy, xx = np.mgrid[:2 * wn, :2 * wn]
    rb = np.rint(np.hypot(yy - wn, xx - wn)).astype(int)
    cnt = np.maximum(np.bincount(rb.ravel()), 1)
    for p in ps:
        im = detail_image(S, float(p), px)
        c = float(im.std())
        sh = im - ndimage.gaussian_filter(im, wn / 4, mode="reflect")
        per = 0.0
        for i in range(3):
            for j in range(3):
                w = sh[i * wn:(i + 1) * wn, j * wn:(j + 1) * wn]
                A = np.fft.rfft2(w - w.mean(), s=(2 * wn, 2 * wn))
                ac = np.fft.fftshift(np.fft.irfft2(np.abs(A) ** 2))
                ac /= max(ac[wn, wn], 1e-12)
                mean = np.bincount(rb.ravel(), ac.ravel()) / cnt
                per = max(per, float((ac - mean[rb])[(rb > 2) & (rb < wn // 2)].max()))
        out.append((round(float(p), 5), round(c, 4), round(per, 3)))
    return out


def repetition_fade(S):
    """The detail's fade by repetition (the way engines fade a tiling detail: mipmaps take care of aliasing; what
    the fade is for is the repeat that shows once many copies are on screen): full until the first footprint where
    the repeat is visible (REPEAT), gone `span` x further. ([p_full, p_gone] m/px or None if it never shows, the
    profile)."""
    prof = repetition_profile(S)
    vis = [p for p, c, per in prof if per > REPEAT["periodicity"] and c > REPEAT["contrast"]]
    if not vis:
        return None, prof
    return [vis[0], round(vis[0] * REPEAT["span"], 5)], prof


def write(out_dir, rock=None, name="rock", size=SIZE, res=RES, macro_density=8.0, source="procedural", S=None):
    """The swatch's images in out_dir/materials (rows top = up the face): <name>_detail_albedo.png (linear RGB,
    value x 2 = the multiplier on the macro colour: 0.5 = unchanged), _normal.png (tangent space, glTF/OpenGL: +x along
    the strike u, +y up the beds v), _height.png (16-bit, 0.5 = 0, +-height_m), _rough.png (value x 2 = the multiplier
    on roughness). Returns the manifest entry, with the wrap seam's measure per image."""
    from PIL import Image
    d = out_dir / "materials"
    d.mkdir(exist_ok=True)
    if S is None:
        S = swatch(rock, size, res) if not str(source).startswith("scan:") else detail_swatch(rock, source)
    size = float(S["size_m"])
    up = lambda a: np.ascontiguousarray(a[::-1])  # (image rows run down; ours run up the face)
    q8 = lambda a: np.round(np.clip(a, 0, 1) * 255).astype(np.uint8)
    hr = float(max(np.abs(S["height"]).max(), 1e-4))
    imgs = {"albedo": q8(0.5 * S["albedo"]), "normal": q8(S["normal"] * 0.5 + 0.5),
            "height": np.round((S["height"] / hr * 0.5 + 0.5) * 65535).astype(np.uint16),
            "rough": q8(0.5 * S["rough"])}
    # the anti-tiling mask: a smooth periodic noise sampled at the detail UV / VARIATION_M, choosing between the swatch
    # at 1x and at VARIATION_SCALE x (offset) place by place, so the 4 m repeat doesn't line up across a wall
    var = spectral(256, 2.0, int((rock or {}).get("seed", 4242)) + 990, lo=2)
    imgs["variation"] = q8(smoothstep(-0.25, 0.25, var))
    files, seams = {}, {}
    for k, a in imgs.items():
        fn = f"materials/{name}_detail_{k}.png"
        im = Image.fromarray(up(a), "I;16" if a.dtype == np.uint16 else None)
        im.save(out_dir / fn)
        files[k] = fn
        seams[k] = tileability(a)
    fade, prof = repetition_fade(S)
    pa = 2 * math.tan(math.radians(REF_VIEW[1] / 2)) / REF_VIEW[0]  # (rad per pixel)
    return {"layer": name, **files, "source": S.get("source", "procedural"), "size_m": float(size),
            "texels_per_m": float(S["texels_per_m"]),
            "variation_m": VARIATION_M, "variation_scale": VARIATION_SCALE, "variation_offset": VARIATION_OFFSET,
            "pixels": int(S["n"]), "height_m": round(hr, 5), "wrap_seam": seams,
            "tileable": all(max(v) <= TILE_LIMIT for v in seams.values()),
            "fade": {"footprint_m": fade, "limits": dict(REPEAT),
                     "distance_m": [round(p / pa, 1) for p in fade] if fade else None,
                     "distance_view": {"width_px": REF_VIEW[0], "fov_deg": REF_VIEW[1]},
                     "repetition": [{"footprint_m": p, "contrast": c, "periodicity": r} for p, c, r in prof]}}


RECIPE = (
    "The tile maps are macro only (a few texels/m: colour, AO, roughness, layer weights, the normal of the >= 0.5 m "
    "structure); the rock below ~0.5 m is a tiling swatch per rock type, drawn on top in the shader. glTF viewers that "
    "ignore it show the macro maps alone (the reference material): correct, softer up close. Per pixel, on cliff tiles, "
    "where the rock layers weigh w = sum of the `layers`' weights (_WEIGHTS / the weights map):\n"
    "1. Projection (seamless, custom shader): s = normalize(_DETAIL.xy) (the strike, u runs to the right as one faces "
    "the rock), v = _DETAIL.w (the bed coordinate, m). theta = atan2(s.y, s.x) / (2 pi / bins); k0 = floor(theta), f = "
    "theta - k0; for k in (k0, k0 + 1): d_k = (cos, sin)(k 2 pi / bins), uv_k = (dot(worldpos.xy, d_k), v), tangent "
    "T_k = (d_k, 0), bitangent B = +z (both projected onto the surface and normalised). Blend the two by f^4 / (f^4 + "
    "(1 - f)^4). Top plane: uv = worldpos.xy, T = +x, B = +y. Blend sides vs top by _DETAIL.z (the side share). "
    "Simpler (stock detail maps): TEXCOORD_<texcoord> holds each triangle's nearest plane (metres; seams where the "
    "plane changes); its tangents are MikkTSpace on that UV set, or the analytic T/B above.\n"
    "2. Anti-tiling: sample the swatch at uv / size_m and at uv / (size_m x variation_scale) + variation_offset; mix by "
    "the variation texture (R) sampled at uv / variation_m.\n"
    "3. Albedo: macro base colour x (1 + w (2 x albedo_detail - 1)) (the albedo texture is linear, 0.5 = unchanged). "
    "Roughness: ORM.g x (1 + w (2 x rough_detail - 1)).\n"
    "4. Normal: the detail normal (tangent space on the plane's T/B, glTF convention) in world space, combined with "
    "the macro normal by RNM about the vertex normal Nv: t = Nm + Nv; u = 2 (Nd.Nv) Nv - Nd; n = normalize(t (t.u) / "
    "(t.Nv) - u); then mix(Nm, n, w).\n"
    "5. Lines (the lines map, TEXCOORD_0, linear filtering, never sRGB): per set (R/B bed planes, G/A joints) s = (c - "
    "0.5) x 2 x line_d metres, a = strength; half-width = (1.2 + 3.3 n) cm x (0.5 + 0.5 a) with n 0..1 wandering "
    "along the line over ~1.5 m, its edge wandering +-40% of it over ~10 cm (never to zero: a width that reached 0 "
    "under a fixed jitter drew dashes); crack = a (1 - smoothstep(0, 0.02, |s| - edge)); shadow = a (1 - "
    "smoothstep(0.015, 0.06, |s|)); albedo x (1 - (0.45 crack + 0.3 shadow) w); a groove: height -(crack + 0.5 shadow) "
    "x 4 cm (bump or derivatives of s). The signed distances interpolate linearly across a line, so it stays crisp at "
    "any distance. The lines never fade.\n"
    "6. Distance fade (fade): mipmaps (trilinear/anisotropic) handle the detail's aliasing; the fade only hides its "
    "repetition, measured from the swatch (repetition: contrast and periodicity of the mipped, anti-tiled detail per "
    "footprint). With p = the pixel's footprint in metres (length(fwidth(worldpos)), or view distance x the pixel's "
    "angle), w_detail = w x (1 - smoothstep(ln footprint_m[0], ln footprint_m[1], ln p)) for the albedo and normal "
    "terms (distance_m quotes the same for a 1920 px, 60 deg view); footprint_m null = no fade needed.")


# ---------------------------------------------------------------- the structure's lines (a macro map)

LINE_D = 0.5  # m: the lines map's signed distances run -LINE_D..LINE_D (8 bits: 4 mm a step)


JOINT_OPEN = {"across": 2.2, "along": 7.0, "up": 6.0, "lo": 0.72, "hi": 0.88, "thick": (1.4, 2.4)}
# m: the openness field's scales (across a family's joints, along their strike, up the face) and its 0..1 ramp


def joint_openness(X, m, B):
    """How open family m's joints are at points X (0..1): smooth value noise elongated along the family's strike and
    up the face, so a fracture corridor opens a few neighbouring joints together, the crack runs on through the beds
    above and below (stepping where each bed's set turns) and its strength wanders and tapers along it."""
    from .terrain_blocks import AZ
    a = math.radians(AZ[m])
    d = np.array([math.cos(a), math.sin(a)])
    J = JOINT_OPEN
    q = np.c_[X[:, :2] @ d / J["across"], X[:, :2] @ np.array([-d[1], d[0]]) / J["along"], X[:, 2] / J["up"]]
    v = noise._value_noise(np.ascontiguousarray(q), int(B["seed"]) + 700 + 11 * m)
    return smoothstep(J["lo"], J["hi"], v)


LINE_GATE_TX = (1.5, 2.5)  # texels: a line's strength fades out between these distances from it


def _drawn_beds(p, Phi, dPhi, B, texel):
    """The nearest DRAWN bed plane at points: (signed distance m, + above it; its crack strength; the distance to the
    next drawn plane). Drawn planes are the open ones (terrain_blocks.ids' bed_crack: the same hash and stretches)
    beside a bed thicker than ~3 texels. Measured to the nearest plane of the point's own bed, the distance was noise
    inside a thin package (a plane every few cm), and the line's strength, gated to a texel round it so that noise
    stayed dark, stepped from texel row to texel row along it: the sawteeth."""
    from .terrain_blocks import _cuts, _h, NCUT
    n = len(Phi)
    S = B["super"]
    K0 = np.floor(Phi).astype(np.int64)
    Cs = {dk: _cuts(K0 + dk, B) for dk in (-2, -1, 0, 1)}
    best = np.full(n, np.inf)
    s_best = np.full(n, LINE_D)
    a_best = np.zeros(n)
    second = np.full(n, np.inf)
    for dk in (-1, 0, 1):
        K = K0 + dk
        C, Cb = Cs[dk], Cs[dk - 1]
        last_lo = np.max(np.where(Cb[:, :NCUT] < 1.0, Cb[:, :NCUT], 0.0), 1)  # (the top bed of the super-bed below)
        for i in range(NCUT):
            lo = K + C[:, i]
            valid = (C[:, i + 1] > C[:, i]) & ((i == 0) | (C[:, i] < 1.0))
            above = (C[:, i + 1] - C[:, i]) * S
            below = ((C[:, i] - C[:, i - 1]) if i else (1.0 - last_lo)) * S
            d = (Phi - lo) / dPhi
            pc = _h(K, np.full(n, i, np.int64), B["seed"] + 90)
            cand = valid & (pc > 0.75) & (np.abs(d) < LINE_D) & (np.maximum(above, below) > 2.8 * texel)
            if not cand.any():
                continue
            k = np.flatnonzero(cand)
            vn = noise._value_noise(np.c_[p[k, :2] / 8.0, (i + 16 * K[k]).astype(float)], B["seed"] + 92)
            cr = np.clip((pc[k] - 0.75) / 0.25, 0, 1) * np.clip((vn - 0.52) / 0.18, 0, 1)
            k, cr = k[cr > 0], cr[cr > 0]
            # (how open the crack is wanders along it over a metre or two, now and then closing: one strength over a
            # whole 8 m stretch drew a ruled ink line across the 10 m view once the line was clean)
            key = (i + 16 * K[k]).astype(float) + 0.5
            ow = noise._value_noise(np.c_[p[k, :2] / 1.7, key], B["seed"] + 93)
            gap = noise._value_noise(np.c_[p[k, :2] / 4.5, key], B["seed"] + 94)
            cr = cr * (0.3 + 0.7 * smoothstep(0.2, 0.7, ow)) * smoothstep(0.25, 0.4, gap)
            ad = np.abs(d[k])
            nearer = ad < best[k]
            second[k] = np.where(nearer, best[k], np.minimum(second[k], ad))
            kk = k[nearer]
            best[kk], s_best[kk], a_best[kk] = ad[nearer], d[kk], cr[nearer]
    return s_best, a_best, second


def _drawn_joints(p, I, B, fd, texel, n):
    """Per joint family the nearest present boundary of the point's own bed's set (terrain_blocks: absent boundaries
    merge blocks): (signed distance m along the joint's normal, the family's weight x joint_openness there, the
    distance to the next boundary, the joint's 3D normal)."""
    from .terrain_blocks import _joint_coord, _joint_frame, _absent, face_weight
    K, j, th = I["K"][:n], I["j"][:n], I["thick"][:n]
    out = []
    for m in range(len(I["edges"])):
        phi, dphi, n2 = _joint_coord(p, K, j, m, th, B)
        nrm, _ = _joint_frame(K, j, m, B)
        jj = (K * 16 + j) * 5 + m
        i0 = np.floor(phi).astype(np.int64)
        best = np.full(n, np.inf)
        sd = np.full(n, LINE_D)
        second = np.full(n, np.inf)
        for db in (-1, 0, 1, 2):
            b = i0 + db
            ok = ~_absent(b, jj, B["seed"] + 80 + 9)  # (every present boundary: which are drawn is joint_openness's)
            d = (phi - b) / dphi
            ad = np.where(ok, np.abs(d), np.inf)
            nearer = ad < best
            second = np.where(nearer, best, np.minimum(second, ad))
            sd = np.where(nearer, d, sd)
            best = np.where(nearer, ad, best)
        w = B["family"][m] * face_weight(n2, fd) * (th >= B["thin"])
        out.append((np.where(np.isfinite(best), sd, LINE_D), w * joint_openness(p, m, B), second, nrm))
    return out


def structure_lines(field, X, texel=0.25, N=None):
    """The rock structure's drawn lines at texels, as SIGNED distances (m, across the surface) and strengths, for the
    lines map: (s_bed, a_bed, s_joint, a_joint). At a few texels per metre a crack 3-5 cm wide can't be baked into
    colour (it blurs into a 0.5 m smudge), but a signed distance interpolates linearly across the line, so the shader
    cuts it crisp at any width (as a font's distance field does).
    X: the texels' points on the low poly (measured at the point projected onto the exact rock, every texel of a
    triangle bridging a ledge landed on its crease, on the bed plane: filled triangles); N: the low poly's smooth
    (interpolated) normal there. Every value is a smooth function of position within a line's reach (2026-10-01: the
    lines followed the 0.5 m mesh's zigzag as thorns at 40 m and sawteeth on bed lines at 10 m; the cause was the
    distance and the gating, not where it was measured: moving the points level onto the exact rock first changed
    nothing measurable):
    - the distance is to the nearest DRAWN plane (`_drawn_beds`) or joint (`_drawn_joints`), so it is a clean
      ramp across the line, and the strength is wide (LINE_GATE_TX texels) and constant across it: the shader's crisp
      cut follows the distance's zero, not the texel grid. Half-way to the next drawn line the distance flips sign (a
      false zero after interpolation): the strength is 0 there (it fades within 2 texels of that point);
    - distances are taken across the surface, not through space (/ the sine between the surface and the plane, from
      the low poly's smooth normal): on a tread lying near a bed plane the vertical distance stayed under the line's
      width over whole triangles. Where the surface runs within ~20 deg of a plane (a tread, a block's side) the line
      fades out on the same smooth normal (the old gate on the triangle's own normal switched it triangle by triangle:
      thorns; ungated, the mesh's wobble about the plane drew wavy false lines beside a crack)."""
    from . import terrain_blocks
    r = field.rock
    n = len(X)
    z = np.zeros(n)
    if not r or not r.get("blocks") or not n:
        return z, z, z, z
    B = r["blocks"]
    fd = field.face_dir(X[:, 0], X[:, 1])
    zoff = r["bed_offset"](X[:, :2]) if r.get("bed_offset") else 0.0
    pre = terrain_blocks._pre(X, B, fd, zoff)
    I = terrain_blocks.ids(X, B, fd, zoff, pre=pre)
    Phi, dPhi = pre[0], pre[1]
    g0, g1 = LINE_GATE_TX[0] * texel, LINE_GATE_TX[1] * texel
    gate = lambda s: 1.0 - smoothstep(g0, g1, np.abs(s))
    guard = lambda s, d2: smoothstep(0.0, 2.0 * texel, d2 - np.abs(s))
    s_b, a_b, d2b = _drawn_beds(X, Phi, dPhi, B, texel)
    if N is not None:
        sin_b = np.sqrt(np.maximum(1.0 - N[:, 2] ** 2, 0.02))
        s_b, d2b = s_b / sin_b, d2b / sin_b
        a_b = a_b * smoothstep(0.2, 0.4, sin_b)
    a_b = a_b * gate(s_b) * guard(s_b, d2b)
    fam = _drawn_joints(X, I, B, fd, texel, n)
    # (a bed crack breaks where a joint crosses it: the joint's block corners are knocked off there, not cut through)
    cross = np.zeros(n)
    for sd, w, d2, nrm in fam:
        cross = np.maximum(cross, np.clip(w, 0, 1) * (1 - smoothstep(0.08, 0.3, np.abs(sd))))
    a_b = a_b * (1 - 0.85 * cross)
    best = np.full(n, -1.0)
    runner = np.zeros(n)
    s_j, a_j = np.full(n, LINE_D), np.zeros(n)
    for sd, w, d2, nrm in fam:
        if N is not None:
            sn = np.sqrt(np.maximum(1.0 - ((N * nrm).sum(1)) ** 2, 0.02))
            sd, d2 = sd / sn, d2 / sn
            w = w * smoothstep(0.2, 0.4, sn)
        a = np.clip(w, 0, 1) * gate(sd) * guard(sd, d2)
        # (the family drawn at a point is the one whose line there is strongest: the family with the NEAREST boundary,
        # however faint, broke a strong crack into pieces wherever its own boundary came closer)
        take = a > best
        runner = np.where(take, np.maximum(best, 0.0), np.maximum(runner, a))
        best = np.where(take, a, best)
        s_j, a_j = np.where(take, sd, s_j), np.where(take, a, a_j)
    # (a joint stops at its bed's planes: faded out within ~1.5 texels of them; and only in beds thick enough for a
    # crack with some length (in a 0.7-1.4 m bed every open joint was a short dash of one width, the "pen ticks" of m02)
    # (where two families are nearly as strong, the drawn one can switch between neighbouring texels, and two distances
    # of either sign interpolate to a false zero: faded where the runner-up is close)
    a_j = a_j * smoothstep(0.0, 0.35, (best - runner) / np.maximum(best, 1e-9))
    th = JOINT_OPEN["thick"]
    a_j = a_j * smoothstep(0.6 * texel, 1.6 * texel, I["bed_edge"]) * smoothstep(th[0], th[1], I["thick"])
    return np.clip(s_b, -LINE_D, LINE_D), a_b, np.clip(s_j, -LINE_D, LINE_D), a_j


# ---------------------------------------------------------------- the bed-aligned projection

class DetailProjection:
    """Where and how the swatch lies on the rock (see the module docstring): per point the smoothed face normal's
    strike, the bed coordinate and the side share; per triangle the nearest strike-binned plane (the UV set). Built
    once per terrain in the parent; pointwise afterwards (forked workers read it)."""

    BINS = 8          # strike planes, every 45 deg round the compass (u to the right as one faces the rock)
    RADIUS = 1.5      # m: the normal is averaged over a ball this size (a rough face's facets don't flip bins)

    def __init__(self, field, rock=None):
        self.field = field
        self.off = rock.get("bed_offset") if rock else None

    def smooth_normal(self, P):
        """The field's normal averaged over RADIUS (gradients at the point and six around it): a pure function of
        position, so both tiles at a border and every LOD agree."""
        P = np.asarray(P, float)
        r = self.RADIUS
        offs = np.array([[0, 0, 0], [r, 0, 0], [-r, 0, 0], [0, r, 0], [0, -r, 0], [0, 0, r], [0, 0, -r]], float)
        Q = (P[:, None, :] + offs[None]).reshape(-1, 3)
        g = np.zeros((len(Q), 3))
        for a in range(0, len(Q), 200_000):
            g[a:a + 200_000] = self.field.value_gradient(Q[a:a + 200_000], 0.5)[1]
        g = g.reshape(len(P), len(offs), 3)
        g /= np.maximum(np.linalg.norm(g, axis=2, keepdims=True), 1e-9)
        n = g.mean(1)
        return n / np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-9)

    def bed_v(self, P):
        P = np.asarray(P, float)
        return P[:, 2] + (self.off(P[:, :2]) if self.off is not None else 0.0)

    @staticmethod
    def side_share(n):
        return smoothstep(0.45, 0.75, np.hypot(n[:, 0], n[:, 1]))

    @staticmethod
    def strike(n):
        """Unit horizontal vector along the face, to the right as one faces it (u x v = outward normal)."""
        s = np.c_[-n[:, 1], n[:, 0]]
        return s / np.maximum(np.linalg.norm(s, axis=1, keepdims=True), 1e-9)

    def attrs(self, P):
        """Per vertex _DETAIL = (strike x, strike y, side share, the bed coordinate in m). (One VEC4: Blender's glTF
        importer mixes up custom attributes of different widths.)"""
        n = self.smooth_normal(P)
        return np.c_[self.strike(n), self.side_share(n), self.bed_v(P)]

    def face_bins(self, P, F):
        """Per triangle the plane its UV set uses: 0..BINS-1 = the strike bin nearest its corners' mean smoothed
        normal, BINS = the top plane (flat rock: ledges, cave floors and roofs)."""
        n = self.smooth_normal(np.asarray(P, float)[F].mean(1))
        s = self.strike(n)
        k = np.round(np.arctan2(s[:, 1], s[:, 0]) / (2 * np.pi / self.BINS)).astype(np.int64) % self.BINS
        return np.where(self.side_share(n) < 0.5, self.BINS, k)

    def uv(self, P, b):
        """The UV set (metres; glTF v runs down) of points P on planes b: side planes u = p . d_b, v = bed coordinate;
        the top plane u = x, v = y (north up the image)."""
        P = np.asarray(P, float)
        a = np.asarray(b) * (2 * np.pi / self.BINS)
        u = P[:, 0] * np.cos(a) + P[:, 1] * np.sin(a)
        v = self.bed_v(P)
        top = np.asarray(b) == self.BINS
        u = np.where(top, P[:, 0], u)
        v = np.where(top, P[:, 1], v)
        return np.c_[u, -v]
