"""Planar rock facets from an irregular point set, and a measure of how regular a facet pattern looks.

`facets(p, size, seed, fd)`: a continuous, piecewise-planar field (-1..1) whose creases form irregular triangles: random
heights at Poisson-disk seeds, interpolated linearly over their 2D Delaunay triangles, laid on the face triplanar-style
(projected along x, y and z onto the other two axes, weighted by the face normal's components^4, the independent
patterns' blend renormalised so it keeps its contrast). The face normal comes from the ground's smoothed downhill
gradient `fd` (Field.face_dir): normal ~ (fd, 1). Vertical projections are stretched `stretch` up the face (the rock's
grain: joints run vertical).

Why not 3D: a random-height field on a cubic lattice (the Freudenthal split, terrain_mesh._pl_facets) put every crease
on one lattice's planes and diagonals: a face showed a few fixed crease directions at one spacing, a quilt of diamonds
from 40-150 m (the user's "squares in the rocks"); warping that lattice helped little (autocorrelation peak 0.46 vs
0.55). A 3D Delaunay of Poisson-disk seeds has slivers (near-flat tetrahedra: random heights over them made needles
with 4x the lattice's steepest slope, black shards in a mesh). 2D Delaunay triangles of well-spaced seeds have no
slivers: slopes stay under the lattice's.

Seeds are decided per point set, deterministically and locally (hashed candidates, a few candidates per cell of a
grid, accepted in rounds by priority within the disk radius), so any two queries agree on every seed they share: tiles
evaluate the same field at a shared border. Triangulations are cached per process per fixed block (GROUP facet
sizes square + PAD): boxes fitted to each query missed the cache whenever a later query reached a little further.

`periodicity(fn)`: the strongest peak of the shaded field's autocorrelation above its radial mean, over planes of a few
orientations: a lattice shows off-centre peaks (0.4-0.55), irregular facets don't (~0.25-0.3)."""
from __future__ import annotations

import os

import numpy as np
from scipy import ndimage
from scipy.spatial import Delaunay, cKDTree

from . import fieldjit, noise

R_DISK = 0.8                          # Poisson-disk radius, in facet sizes
CELL = R_DISK / np.sqrt(2) * 0.999    # candidate grid: at most one seed per cell
PER = 3                               # candidates per cell
ROUNDS = 3                            # acceptance rounds (each depends on candidates R_DISK further out)
PAD = 3.0                             # facet sizes of seeds round the queried points (their triangles are global)
GAIN = 1.4                            # slope to match the lattice facets' (see facets)
GROUP = 32.0                          # points are triangulated per block this many facet sizes square (+ PAD round)
CACHE_POINTS = int(os.environ.get("HIFIPUSHIE_FACET_CACHE", 600_000))  # seeds kept in triangulations per process (~200 B
# each with the lazily built transform)
PERIODIC = 0.4                        # periodicity() above this: the facets read as a lattice
_CACHE: dict = {}                     # (seed, block i, block j) -> (triangulation, heights), least recently used first


def _seeds(lo, hi, seed, period=None):
    """Poisson-disk seeds in the box [lo, hi] (2D, facet units) and their ids (cell i, j, candidate k). period: (ni, nj)
    cells: the candidates' hashes repeat every ni x nj cells, so the seeds (and anything built on them) tile a torus
    ni x nj x CELL across (the tiling rock swatches, terrain_swatch); ids come back wrapped into the period."""
    m = int(np.ceil((ROUNDS + 1) * R_DISK / CELL)) + 1
    lo_c = np.floor(np.asarray(lo) / CELL).astype(np.int64) - m
    hi_c = np.floor(np.asarray(hi) / CELL).astype(np.int64) + m
    if fieldjit.ON and period is None:  # (the same candidates and rounds, compiled: 10x+, a cache miss was ~90% this)
        return fieldjit.seeds(lo_c, hi_c, lo, hi, seed, CELL, PER, R_DISK, ROUNDS)
    I, J = np.meshgrid(np.arange(lo_c[0], hi_c[0] + 1), np.arange(lo_c[1], hi_c[1] + 1), indexing="ij")
    I, J = np.repeat(I.ravel(), PER), np.repeat(J.ravel(), PER)
    K = np.tile(np.arange(PER, dtype=np.int64), len(I) // PER)
    Ih, Jh = (I, J) if period is None else (np.mod(I, period[0]), np.mod(J, period[1]))
    pts = (np.stack([I, J], 1) + np.stack([noise._hash(Ih, Jh, K, seed + 1), noise._hash(Ih, Jh, K, seed + 2)], 1)) \
        * CELL
    pr = noise._hash(Ih, Jh, K, seed + 3)
    pairs = cKDTree(pts).query_pairs(R_DISK, output_type="ndarray")
    a, b = pairs[:, 0], pairs[:, 1]
    state = np.zeros(len(pts), np.int8)  # 0 undecided, 1 a seed, -1 not
    for _ in range(ROUNDS):
        und = state == 0
        lose = np.zeros(len(pts), bool)  # an undecided neighbour has the higher priority
        both = und[a] & und[b]
        lose[np.where(pr[a] < pr[b], a, b)[both]] = True
        blocked = np.zeros(len(pts), bool)  # a neighbour is a seed already
        blocked[a[state[b] == 1]] = True
        blocked[b[state[a] == 1]] = True
        win = und & ~lose & ~blocked
        state[win] = 1
        near = np.zeros(len(pts), bool)
        near[a[win[b]]] = True
        near[b[win[a]]] = True
        state[und & near & ~win] = -1
    keep = (state == 1) & np.all((pts >= lo) & (pts <= hi), axis=1)
    return pts[keep], np.stack([Ih, Jh, K], 1)[keep]


def _triangulation(seed, gi, gj):
    """The Delaunay triangulation of the seeds in block (gi, gj) plus PAD round it, and the seeds' heights. One per
    block, cached by block (boxes fitted to each query's points missed the cache whenever a later query reached a
    little further: a cold bake piece spent 3/4 of its field time triangulating)."""
    key = (seed, gi, gj)
    hit = _CACHE.pop(key, None)
    if hit is None:
        from . import profiling
        lo = np.array([gi * GROUP - PAD, gj * GROUP - PAD])
        hi = lo + GROUP + 2 * PAD
        with profiling.span("facets.triangulate (cache miss)", leaf=True):
            pts, ids = _seeds(lo, hi, seed)
            val = 2 * noise._hash(ids[:, 0], ids[:, 1], ids[:, 2], seed + 9) - 1
            tri = Delaunay(pts)
        profiling.count("facets.seeds triangulated", len(pts))
        hit = (tri, val)
        total = sum(len(v[1]) for v in _CACHE.values()) + len(val)
        for k in list(_CACHE):
            if total <= CACHE_POINTS:
                break
            total -= len(_CACHE.pop(k)[1])
    _CACHE[key] = hit
    return hit


def pl2d(q, seed, gi, gj):
    """The piecewise-linear field at 2D points q (facet units) in block (gi, gj)."""
    tri, val = _triangulation(seed, gi, gj)
    if fieldjit.ON:
        return fieldjit.pl2d_tri(q, tri, val)
    s = tri.find_simplex(q)
    T = tri.transform[s]
    bc = np.einsum("nij,nj->ni", T[:, :2], q - T[:, 2])
    return (np.c_[bc, 1 - bc.sum(1)] * val[tri.simplices[s]]).sum(1)


def facets(p, size, seed, fd, stretch=1.4):
    """Irregular planar facets about `size` m across on the face whose ground gradient is fd (n, 2). -1..1."""
    p = np.asarray(p, float)
    w = np.abs(np.c_[fd, np.ones(len(p))]) ** 4
    if fieldjit.ON:  # (the same arithmetic from here on, compiled: fieldjit.facets)
        got = fieldjit.facets(p, size, seed, w, stretch, GROUP, _triangulation, GAIN, normalise=0.03)
        if got is not None:
            return got
    w /= w.sum(1, keepdims=True)
    # (a projection under 3% is dropped, continuously: on a steep face one or two patterns, not three)
    w = np.maximum(w - 0.03, 0.0)
    w /= w.sum(1, keepdims=True)
    out = np.zeros(len(p))
    for ax, (u, v, st) in enumerate(((1, 2, stretch), (0, 2, stretch), (0, 1, 1.0))):
        k = np.flatnonzero(w[:, ax] > 0)
        if len(k):
            q = np.c_[p[k, u], p[k, v] / st] / size
            # one triangulation per GROUP x GROUP piece of the plane the points fall in (a sparse sample spread over a
            # whole map in one box asked for tens of millions of seeds: the export's parent grew to 7 GB)
            g = np.floor(q / GROUP).astype(np.int64)
            key = g[:, 0] * 1_000_003 + g[:, 1]
            o = np.argsort(key, kind="stable")
            ks = key[o]
            cut = np.r_[0, np.flatnonzero(ks[1:] != ks[:-1]) + 1, len(ks)]
            vals = np.empty(len(k))
            for a_, b_ in zip(cut[:-1], cut[1:]):
                sel = o[a_:b_]
                vals[sel] = pl2d(q[sel], seed + 500 * ax, int(g[sel[0], 0]), int(g[sel[0], 1]))
            out[k] += w[k, ax] * vals
    # (triangles of well-spaced seeds tilt less than the lattice's six tetrahedra a cube: median slope 0.11 vs 0.18 a
    # facet size, and the rock read soft and plastered from 5 m. Steeper by GAIN (1.4: median slope 0.15, ~8%
    # clipped), clipped to the lattice's range: the clipped places are flat planes, still facets)
    return np.clip(GAIN * out / np.sqrt((w * w).sum(1)), -1.0, 1.0)


def periodicity(fn, extent=80.0, n=400, orients=((0, 1, 0), (1, 1, 0.3), (0.2, -0.5, 1), (1, -0.3, 0.4))):
    """How regular a relief function looks: fn(P (m, 3), fd (m, 2)) -> offsets. Per plane orientation, the largest
    value of the shaded relief's autocorrelation above its radial mean, 4-30 m out. Lattice facets 0.4-0.55,
    irregular ones 0.25-0.3."""
    s = np.linspace(0, extent, n)
    U, V = np.meshgrid(s, s)
    out = []
    for nrm in orients:
        nrm = np.array(nrm, float)
        nrm /= np.linalg.norm(nrm)
        a = np.cross(nrm, [0, 0, 1.0])
        a /= np.linalg.norm(a)
        b = np.cross(nrm, a)
        P = U.ravel()[:, None] * a + V.ravel()[:, None] * b + 1000.0
        fd = np.tile(nrm[:2] / max(nrm[2], 1e-3), (len(P), 1))
        F = fn(P, fd).reshape(n, n)
        gy, gx = np.gradient(F, s[1] - s[0])
        sh = 0.6 * (gx - gy)
        sh = sh - ndimage.gaussian_filter(sh, 20)
        A = np.fft.rfft2(sh, s=(2 * n, 2 * n))
        ac = np.fft.fftshift(np.fft.irfft2(np.abs(A) ** 2))
        ac /= max(ac[n, n], 1e-12)
        yy, xx = np.mgrid[:2 * n, :2 * n]
        rb = np.rint(np.hypot(yy - n, xx - n)).astype(int)
        mean = np.bincount(rb.ravel(), ac.ravel()) / np.maximum(np.bincount(rb.ravel()), 1)
        r = rb * (s[1] - s[0])
        out.append(float((ac - mean[rb])[(r > 4.0) & (r < 30.0)].max()))
    return [round(x, 3) for x in out]
