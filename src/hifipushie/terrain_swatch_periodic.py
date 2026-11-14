"""Periodic pieces a swatch is made of: facets, spectral noise, cells, pits, veins, all wrapping at the tile's edge. Part of the terrain's material swatches (terrain_swatch.py has the overview)."""
from __future__ import annotations

import numpy as np
from scipy import ndimage

from . import noise
from . import terrain_facets as tf
from .terrain_swatch import smoothstep

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
    """Periodic noise (as terrain_bake_layers._spectral: random phases, 1/f^beta), zero mean, about -1..1, with nothing
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
