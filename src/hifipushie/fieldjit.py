"""Compiled (numba) kernels for the terrain field's hot leaves, bit-identical to the numpy code they stand in for.

The numpy functions stay the reference and the fallback: each keeps its signature and calls the kernel here when `ON`.
HIFIPUSHIE_JIT=0 turns the kernels off (numpy everywhere); without numba installed they're off too.

Kernels reproduce the numpy/scipy arithmetic operation by operation (same order, no fastmath, no FMA contraction), so
values match bit for bit; `tests/test_fieldjit.py` checks that on real terrains.
- `hash01`, `value_noise`: noise._hash / noise._value_noise.
- `cubic2d`, `column`: scipy.ndimage.map_coordinates(order=3, prefilter=False, mode="nearest") on a 2D grid (the
  weights and the 4x4 accumulation order of ni_splines.c / ni_interpolation.c), and Field.column's 5-tap stencil.
- `pl2d`: Delaunay.find_simplex (the lifted walk, the directed walk and the brute-force fallback of scipy's _qhull.pyx,
  with its start chaining) + the barycentric interpolation of terrain_facets.pl2d.
- `blocks_*`: terrain_blocks' jointed, bedded rock (bed coordinate, bed slots, minor joints per bed, master joints, ids)
  per point. Its numpy-only pieces come in precomputed: the super-beds' cuts (h ** 1.2: SVML pow) and joint frames
  (sin/cos) as tables over the K range, the master joints' plan projections (BLAS), and the carve stays numpy.
A noise corner whose weight is exactly 0 is skipped (it adds +0.0 to a sum that is never -0.0): coordinates on a lattice
plane (a bed or family index used as a coordinate) halve their hashes.
`cache=True` writes the compiled code next to this file (__pycache__), so forked pool workers and later runs load it
instead of compiling (~1-2 s cold, once)."""
from __future__ import annotations

import os

import numpy as np

ON = False
if os.environ.get("HIFIPUSHIE_JIT", "1") not in ("0", "", "off", "false"):
    try:
        import numba  # noqa: F401
        from numba import njit
        ON = True
    except ImportError:  # pragma: no cover
        ON = False

if ON:
    _U13 = np.uint64(13)
    _U15 = np.uint64(15)
    _MUL = np.uint64(0x5bd1e995)
    _MASK = np.uint64(0xFFFFFF)

    @njit(cache=True, inline="always")
    def hash01(ix, iy, iz, seed):
        """noise._hash for one lattice point (int64 inputs)."""
        h = (ix * 73856093) ^ (iy * 19349663) ^ (iz * 83492791) ^ (seed * 2654435761)
        u = np.uint64(h)
        u ^= u >> _U13
        u *= _MUL
        u ^= u >> _U15
        return np.float64(u & _MASK) / 16777215.0

    @njit(cache=True, inline="always")
    def _vn(x, y, z, seed):
        fx, fy, fz = np.floor(x), np.floor(y), np.floor(z)
        ix, iy, iz = np.int64(fx), np.int64(fy), np.int64(fz)
        fx = x - np.float64(ix)
        fy = y - np.float64(iy)
        fz = z - np.float64(iz)
        ux = fx * fx * fx * (fx * (fx * 6 - 15) + 10)
        uy = fy * fy * fy * (fy * (fy * 6 - 15) + 10)
        uz = fz * fz * fz * (fz * (fz * 6 - 15) + 10)
        out = 0.0
        for dx in range(2):
            wx = ux if dx else 1 - ux
            for dy in range(2):
                wy = uy if dy else 1 - uy
                for dz in range(2):
                    wz = uz if dz else 1 - uz
                    w = wx * wy * wz
                    # (a zero weight adds +0.0: skipped, exactly. Coordinates on lattice planes (a bed or family index
                    # as a coordinate) have half their corners at zero weight)
                    if w != 0.0:
                        out += w * hash01(ix + dx, iy + dy, iz + dz, seed)
        return out

    @njit(cache=True)
    def value_noise(p, seed):
        n = p.shape[0]
        out = np.empty(n)
        for k in range(n):
            out[k] = _vn(p[k, 0], p[k, 1], p[k, 2], seed)
        return out

    # ------------------------------------------------------------ cubic B-spline lookups

    @njit(cache=True, inline="always")
    def _weights(cc):
        x = cc - np.floor(cc)
        y = x
        z = 1.0 - x
        w1 = (y * y * (y - 2.0) * 3.0 + 4.0) / 6.0
        w2 = (z * z * (z - 2.0) * 3.0 + 4.0) / 6.0
        w0 = z * z * z / 6.0
        w3 = 1.0
        w3 -= w0
        w3 -= w1
        w3 -= w2
        return w0, w1, w2, w3

    @njit(cache=True, inline="always")
    def _cubic(a, r, q):
        """One map_coordinates(order=3, prefilter=False, mode="nearest") sample of the 2D array a at (r, q)."""
        n0, n1 = a.shape
        s0 = np.int64(np.floor(r)) - 1
        s1 = np.int64(np.floor(q)) - 1
        a0, a1, a2, a3 = _weights(r)
        b0, b1, b2, b3 = _weights(q)
        wr = (a0, a1, a2, a3)
        wq = (b0, b1, b2, b3)
        t = 0.0
        for i in range(4):
            ii = s0 + i
            if ii < 0:
                ii = 0
            elif ii > n0 - 1:
                ii = n0 - 1
            for j in range(4):
                jj = s1 + j
                if jj < 0:
                    jj = 0
                elif jj > n1 - 1:
                    jj = n1 - 1
                coeff = a[ii, jj]
                coeff *= wr[i]
                coeff *= wq[j]
                t += coeff
        return t

    @njit(cache=True)
    def cubic2d(a, r, q):
        """map_coordinates(a, [r, q], order=3, prefilter=False, mode="nearest") for a 2D float64 array."""
        n = r.shape[0]
        out = np.empty(n)
        for k in range(n):
            out[k] = _cubic(a, r[k], q[k])
        return out

    @njit(cache=True)
    def grid_at(a, x, y, x0, y0, c):
        """A grid lookup at world columns (Field.steep_at / grain_at): r = (y - y0) / c, q = (x - x0) / c."""
        n = x.shape[0]
        out = np.empty(n)
        for k in range(n):
            out[k] = _cubic(a, (y[k] - y0) / c, (x[k] - x0) / c)
        return out

    @njit(cache=True)
    def column(H, x, y, x0, y0, c):
        """Field.column: the height and 1 / sqrt(1 + |grad h|^2) from a 5-tap stencil half a cell wide."""
        n = x.shape[0]
        h = np.empty(n)
        s = np.empty(n)
        e = 0.5
        d = 2 * e * c
        for k in range(n):
            r = (y[k] - y0) / c
            q = (x[k] - x0) / c
            v0 = _cubic(H, r, q)
            v1 = _cubic(H, r, q + e)
            v2 = _cubic(H, r, q - e)
            v3 = _cubic(H, r + e, q)
            v4 = _cubic(H, r - e, q)
            gx = (v1 - v2) / d
            gy = (v3 - v4) / d
            h[k] = v0
            s[k] = 1.0 / np.sqrt(1.0 + gx * gx + gy * gy)
        return h, s

    # ------------------------------------------------------------ 2D Delaunay point location + interpolation

    @njit(cache=True, inline="always")
    def _bary(T, s, x0, x1):
        c0 = 0.0
        c0 += T[s, 0, 0] * (x0 - T[s, 2, 0])
        c0 += T[s, 0, 1] * (x1 - T[s, 2, 1])
        c1 = 0.0
        c1 += T[s, 1, 0] * (x0 - T[s, 2, 0])
        c1 += T[s, 1, 1] * (x1 - T[s, 2, 1])
        c2 = 1.0
        c2 -= c0
        c2 -= c1
        return c0, c1, c2

    @njit(cache=True)
    def _brute(T, nb, x0, x1, eps, eps_broad, lo, hi):
        if x0 < lo[0] - eps or x0 > hi[0] + eps or x1 < lo[1] - eps or x1 > hi[1] + eps:
            return -1
        ns = T.shape[0]
        for s in range(ns):
            if T[s, 0, 0] == T[s, 0, 0]:
                c0, c1, c2 = _bary(T, s, x0, x1)
                if (-eps <= c0 <= 1 + eps) and (-eps <= c1 <= 1 + eps) and (-eps <= c2 <= 1 + eps):
                    return s
            else:
                for k in range(3):
                    m_ = nb[s, k]
                    if m_ == -1:
                        continue
                    if T[m_, 0, 0] != T[m_, 0, 0]:
                        continue
                    c = _bary(T, m_, x0, x1)
                    inside = True
                    for m in range(3):
                        if nb[m_, m] == s:
                            if not (-eps_broad <= c[m] <= 1 + eps):
                                inside = False
                                break
                        else:
                            if not (-eps <= c[m] <= 1 + eps):
                                inside = False
                                break
                    if inside:
                        return m_
        return -1

    @njit(cache=True)
    def _find(T, nb, eq, scale, shift, lo, hi, x0, x1, start, eps, eps_broad):
        """scipy's _find_simplex for one 2D point: (simplex or -1, the start for the next point)."""
        if x0 < lo[0] - eps or x0 > hi[0] + eps or x1 < lo[1] - eps or x1 > hi[1] + eps:
            return -1, start
        ns = T.shape[0]
        if ns <= 0:
            return -1, start
        s = start
        if s < 0 or s >= ns:
            s = 0
        z2 = 0.0
        z2 += x0 * x0
        z2 += x1 * x1
        z2 *= scale
        z2 += shift
        best = eq[s, 3]
        best += eq[s, 0] * x0
        best += eq[s, 1] * x1
        best += eq[s, 2] * z2
        changed = True
        while changed:
            if best > 0:
                break
            changed = False
            for k in range(3):
                g = nb[s, k]
                if g == -1:
                    continue
                d = eq[g, 3]
                d += eq[g, 0] * x0
                d += eq[g, 1] * x1
                d += eq[g, 2] * z2
                if d > best + eps * (1 + abs(best)):
                    s = g
                    best = d
                    changed = True
        # the directed walk
        for _ in range(1 + ns // 4):
            if s == -1:
                break
            inside = 1
            c0 = 0.0
            c1 = 0.0
            for k in range(3):
                if k < 2:
                    v = 0.0
                    v += T[s, k, 0] * (x0 - T[s, 2, 0])
                    v += T[s, k, 1] * (x1 - T[s, 2, 1])
                    if k == 0:
                        c0 = v
                    else:
                        c1 = v
                else:
                    v = 1.0
                    v -= c0
                    v -= c1
                if v < -eps:
                    m = nb[s, k]
                    if m == -1:
                        return -1, s
                    s = m
                    inside = -1
                    break
                elif v <= 1 + eps:
                    pass
                else:
                    inside = 0
            if inside == -1:
                continue
            elif inside == 1:
                return s, s
            else:
                s = _brute(T, nb, x0, x1, eps, eps_broad, lo, hi)
                return s, s
        s = _brute(T, nb, x0, x1, eps, eps_broad, lo, hi)
        return s, s

    @njit(cache=True)
    def pl2d(q, T, nb, simp, eq, scale, shift, lo, hi, val, eps, eps_broad):
        """terrain_facets.pl2d: find_simplex per point (chained starts, as scipy does), then the barycentric
        interpolation of val (a point outside the triangulation uses the last simplex, like T[-1] in numpy)."""
        n = q.shape[0]
        out = np.empty(n)
        start = 0
        ns = T.shape[0]
        for k in range(n):
            x0, x1 = q[k, 0], q[k, 1]
            s, start = _find(T, nb, eq, scale, shift, lo, hi, x0, x1, start, eps, eps_broad)
            if s < 0:
                s = ns + s
            d0 = x0 - T[s, 2, 0]
            d1 = x1 - T[s, 2, 1]
            b0 = T[s, 0, 0] * d0 + T[s, 0, 1] * d1
            b1 = T[s, 1, 0] * d0 + T[s, 1, 1] * d1
            b2 = 1 - (b0 + b1)
            out[k] = b0 * val[simp[s, 0]] + b1 * val[simp[s, 1]] + b2 * val[simp[s, 2]]
        return out


def pl2d_tri(q, tri, val):
    """terrain_facets.pl2d through the kernel, from a scipy Delaunay object."""
    eps = 100 * np.finfo(np.double).eps
    return pl2d(np.ascontiguousarray(q, dtype=np.float64), tri.transform, tri.neighbors, tri.simplices, tri.equations,
                float(tri.paraboloid_scale), float(tri.paraboloid_shift), tri.min_bound, tri.max_bound, val, eps,
                float(np.sqrt(eps)))


if ON:
    @njit(cache=True)
    def _hash_flat(ix, iy, iz, seed):
        n = ix.shape[0]
        out = np.empty(n)
        for k in range(n):
            out[k] = hash01(ix[k], iy[k], iz[k], seed)
        return out


def _hash_np(ix, iy, iz, seed):
    h = (ix * 73856093) ^ (iy * 19349663) ^ (iz * 83492791) ^ (seed * 2654435761)
    h = h.astype(np.uint64)
    h ^= h >> np.uint64(13)
    h *= np.uint64(0x5bd1e995)
    h ^= h >> np.uint64(15)
    return (h & np.uint64(0xFFFFFF)).astype(np.float64) / float(0xFFFFFF)


def hash_arrays(ix, iy, iz, seed):
    """noise._hash: the kernel for int64 arrays (any shapes that broadcast), numpy for anything else (other integer
    widths wrap differently)."""
    if not (isinstance(ix, np.ndarray) and isinstance(iy, np.ndarray) and isinstance(iz, np.ndarray)
            and ix.dtype == np.int64 and iy.dtype == np.int64 and iz.dtype == np.int64 and abs(int(seed)) < 2 ** 31):
        return _hash_np(ix, iy, iz, seed)
    a, b, c = np.broadcast_arrays(ix, iy, iz)
    shape = a.shape
    out = _hash_flat(np.ascontiguousarray(a).ravel(), np.ascontiguousarray(b).ravel(),
                     np.ascontiguousarray(c).ravel(), int(seed))
    return out.reshape(shape)


# ---------------------------------------------------------------- terrain_facets.facets, fused

AMBIG = 1e-9  # a point whose barycentric coordinates all exceed this lies in exactly one triangle (find_simplex's
# tolerance is 100 eps ~ 2e-14): any walk finds it. Closer to an edge, scipy's own walk decides (its chained start).
BUCKET = 1.0  # facet units per cell of a triangulation's bucket grid (a triangle under each cell's centre)

if ON:

    @njit(cache=True)
    def _blocks(p, w, size, stretch, group, maxb):
        """The (axis, gi, gj) blocks the points' projections fall in, in order of first appearance (at most maxb)."""
        out = np.empty((maxb, 3), np.int64)
        nb = 0
        n = p.shape[0]
        for k in range(n):
            for ax in range(3):
                if not w[k, ax] > 0:
                    continue
                if ax == 0:
                    a, b, st = p[k, 1], p[k, 2], stretch
                elif ax == 1:
                    a, b, st = p[k, 0], p[k, 2], stretch
                else:
                    a, b, st = p[k, 0], p[k, 1], 1.0
                q0 = a / size
                q1 = b / st / size
                gi = np.int64(np.floor(q0 / group))
                gj = np.int64(np.floor(q1 / group))
                found = False
                for t in range(nb - 1, -1, -1):
                    if out[t, 0] == ax and out[t, 1] == gi and out[t, 2] == gj:
                        found = True
                        break
                if not found:
                    if nb == maxb:
                        return out[:0]
                    out[nb, 0] = ax
                    out[nb, 1] = gi
                    out[nb, 2] = gj
                    nb += 1
        return out[:nb]

    @njit(cache=True)
    def _locate_fast(T, nb, grid, g0, g1, gnx, gny, x0, x1):
        """The triangle containing (x0, x1) when the point is unambiguous (every barycentric > AMBIG), else -1: from
        the bucket grid's triangle (cells BUCKET = 1 unit), walking toward the most negative coordinate."""
        # (clamped, not tested: an early return here made the loop 3-4x slower; a far start only walks longer)
        i = min(max(np.int64(np.floor(x0 - g0)), 0), gnx - 1)
        j = min(max(np.int64(np.floor(x1 - g1)), 0), gny - 1)
        s = grid[i * gny + j]
        for _ in range(64):
            c0 = T[s, 0, 0] * (x0 - T[s, 2, 0]) + T[s, 0, 1] * (x1 - T[s, 2, 1])
            c1 = T[s, 1, 0] * (x0 - T[s, 2, 0]) + T[s, 1, 1] * (x1 - T[s, 2, 1])
            c2 = 1.0 - c0 - c1
            if c0 > AMBIG and c1 > AMBIG and c2 > AMBIG:
                return s
            if c0 < c1 and c0 < c2:
                s = nb[s, 0]
            elif c1 < c2:
                s = nb[s, 1]
            else:
                s = nb[s, 2]
            if s < 0:
                return -1
        return -1  # (near an edge, inside: ambiguous; or a cycle)

    @njit(cache=True)
    def _facets_block(p, w, size, stretch, ax, x0s, x1s, sel, m, T, nb, simp, eq, val, grid, fpar, ipar, vout):
        """One block's points (sel[:m], in order): located and interpolated into vout[k, ax]."""
        eps = 100 * np.finfo(np.float64).eps
        eps_broad = np.sqrt(eps)
        start = 0
        lo = fpar[0:2]
        hi = fpar[2:4]
        for t in range(m):
            k = sel[t]
            x0 = x0s[k]
            x1 = x1s[k]
            s = _locate_fast(T, nb, grid, fpar[4], fpar[5], ipar[0], ipar[1], x0, x1)
            if s < 0:
                s, start = _find(T, nb, eq, fpar[7], fpar[8], lo, hi, x0, x1, start, eps, eps_broad)
                if s < 0:
                    s = T.shape[0] + s
            else:
                start = s
            d0 = x0 - T[s, 2, 0]
            d1 = x1 - T[s, 2, 1]
            b0 = T[s, 0, 0] * d0 + T[s, 0, 1] * d1
            b1 = T[s, 1, 0] * d0 + T[s, 1, 1] * d1
            b2 = 1 - (b0 + b1)
            vout[k, ax] = b0 * val[simp[s, 0]] + b1 * val[simp[s, 1]] + b2 * val[simp[s, 2]]

    @njit(cache=True)
    def _facets_coords(p, w, size, stretch, group, blocks, x0s, x1s, bidx):
        """Each point's projected coordinates per axis and the index of its block in `blocks` (-1: no weight)."""
        n = p.shape[0]
        nblk = blocks.shape[0]
        last = 0
        for k in range(n):
            for ax in range(3):
                bidx[k, ax] = -1
                if not w[k, ax] > 0:
                    continue
                if ax == 0:
                    a, b, st = p[k, 1], p[k, 2], stretch
                elif ax == 1:
                    a, b, st = p[k, 0], p[k, 2], stretch
                else:
                    a, b, st = p[k, 0], p[k, 1], 1.0
                x0 = a / size
                x1 = b / st / size
                x0s[ax, k] = x0
                x1s[ax, k] = x1
                gi = np.int64(np.floor(x0 / group))
                gj = np.int64(np.floor(x1 / group))
                if not (blocks[last, 0] == ax and blocks[last, 1] == gi and blocks[last, 2] == gj):
                    for t in range(nblk):
                        if blocks[t, 0] == ax and blocks[t, 1] == gi and blocks[t, 2] == gj:
                            last = t
                            break
                bidx[k, ax] = last

    @njit(cache=True)
    def _by_block(bidx, nblk):
        """Every (point, axis) grouped by block, points in their own order within a block (a counting sort):
        (order of point indices, start of each block's run)."""
        n = bidx.shape[0]
        cnt = np.zeros(nblk + 1, np.int64)
        for k in range(n):
            for ax in range(3):
                b = bidx[k, ax]
                if b >= 0:
                    cnt[b + 1] += 1
        for t in range(nblk):
            cnt[t + 1] += cnt[t]
        pos = cnt[:nblk].copy()
        order = np.empty(cnt[nblk], np.int64)
        for k in range(n):
            for ax in range(3):
                b = bidx[k, ax]
                if b >= 0:
                    order[pos[b]] = k
                    pos[b] += 1
        return order, cnt

    @njit(cache=True)
    def _norm_weights(w, cut):
        for k in range(w.shape[0]):
            t = w[k, 0] + w[k, 1] + w[k, 2]
            a, b, c = w[k, 0] / t, w[k, 1] / t, w[k, 2] / t
            a = max(a - cut, 0.0)
            b = max(b - cut, 0.0)
            c = max(c - cut, 0.0)
            t = a + b + c
            w[k, 0] = a / t
            w[k, 1] = b / t
            w[k, 2] = c / t

    @njit(cache=True)
    def _facets_sum(w, vout, gain):
        n = w.shape[0]
        out = np.empty(n)
        for k in range(n):
            acc = 0.0
            for ax in range(3):
                if w[k, ax] > 0:
                    acc += w[k, ax] * vout[k, ax]
            nrm = np.sqrt(w[k, 0] * w[k, 0] + w[k, 1] * w[k, 1] + w[k, 2] * w[k, 2])
            r = gain * acc / nrm
            out[k] = min(max(r, -1.0), 1.0)
        return out


def _grid_of(tri):
    """A bucket grid over a triangulation: per BUCKET cell, the triangle under its centre (-1 outside)."""
    g = getattr(tri, "_hp_grid", None)
    if g is None:
        lo, hi = tri.min_bound, tri.max_bound
        nx = int(np.ceil((hi[0] - lo[0]) / BUCKET)) + 1
        ny = int(np.ceil((hi[1] - lo[1]) / BUCKET)) + 1
        I, J = np.meshgrid(np.arange(nx), np.arange(ny), indexing="ij")
        c = np.c_[lo[0] + (I.ravel() + 0.5) * BUCKET, lo[1] + (J.ravel() + 0.5) * BUCKET]
        g = (tri.find_simplex(c).astype(np.int64), float(lo[0]), float(lo[1]), nx, ny)
        tri._hp_grid = g
        _ = tri.transform  # (computed once, kept by scipy)
    return g


def facets(p, size, seed, w, stretch, group, triangulation, gain, normalise=None):
    """terrain_facets.facets from its weights w (n, 3) on: every projection's block found and triangulated (through
    `triangulation(seed, gi, gj)`, the module's cache), its points located and interpolated block by block (each
    block's points in their own order: find_simplex's chained start), summed by weight. None when the points touch
    too many blocks (the caller then takes the numpy path)."""
    p = np.ascontiguousarray(p, dtype=np.float64)
    w = np.ascontiguousarray(w, dtype=np.float64)
    if normalise is not None:  # (w = |(fd, 1)|^4, normalised, `normalise` taken off, normalised again: in place)
        w = w.copy()  # (the caller's array stays as it was: it falls back to numpy when there are too many blocks)
        _norm_weights(w, float(normalise))
    n = len(p)
    blocks = _blocks(p, w, float(size), float(stretch), float(group), 1 << 16)
    if len(blocks) == 0:
        return None
    x0s, x1s = np.empty((3, n)), np.empty((3, n))
    bidx = np.empty((n, 3), np.int64)
    _facets_coords(p, w, float(size), float(stretch), float(group), blocks, x0s, x1s, bidx)
    vout = np.zeros((n, 3))
    order, starts = _by_block(bidx, len(blocks))
    for t, (ax, gi, gj) in enumerate(blocks):
        tri, val = triangulation(seed + 500 * int(ax), int(gi), int(gj))
        grid, g0, g1, nx, ny = _grid_of(tri)
        fpar = np.array([tri.min_bound[0], tri.min_bound[1], tri.max_bound[0], tri.max_bound[1], g0, g1, BUCKET,
                         float(tri.paraboloid_scale), float(tri.paraboloid_shift)])
        sel = order[starts[t]:starts[t + 1]]
        _facets_block(p, w, float(size), float(stretch), int(ax), x0s[ax], x1s[ax], sel, len(sel), tri.transform,
                      tri.neighbors, tri.simplices, tri.equations, val, grid, fpar, np.array([nx, ny], np.int64), vout)
    return _facets_sum(w, vout, float(gain))


# ---------------------------------------------------------------- terrain_mesh._pl_walk (the warped facet lattice)

if ON:
    _U16 = np.uint64(16)
    _U29 = np.uint64(29)
    _U31 = np.uint64(31)
    _M1 = np.uint64(0xBF58476D1CE4E5B9)
    _M2 = np.uint64(0x94D049BB133111EB)
    _FFFF = np.uint64(0xFFFF)

    @njit(cache=True, inline="always")
    def _hash3_one(ix, iy, iz, seed):
        h = np.uint64((ix * 73856093) ^ (iy * 19349663) ^ (iz * 83492791) ^ (seed * 2654435761))
        h ^= h >> _U31
        h *= _M1
        h ^= h >> _U31
        h *= _M2
        h ^= h >> _U29
        a = np.float64(h & _FFFF) / 32767.5 - 1.0
        b = np.float64((h >> _U16) & _FFFF) / 32767.5 - 1.0
        c = np.float64((h >> np.uint64(32)) & _FFFF) / 32767.5 - 1.0
        return a, b, c

    @njit(cache=True)
    def pl_walk(q, seed, vec):
        """terrain_mesh._pl_walk: corner values of the unit lattice interpolated over the Freudenthal tetrahedra.
        Axes walked from the largest fraction down (ties in index order; a tie's middle corner has weight 0, so the
        order between tied axes doesn't change the value). (n,) or (n, 3) with vec (the first column filled when
        not vec)."""
        n = q.shape[0]
        out = np.zeros((n, 3 if vec else 1))
        for k in range(n):
            b0 = np.int64(np.floor(q[k, 0]))
            b1 = np.int64(np.floor(q[k, 1]))
            b2 = np.int64(np.floor(q[k, 2]))
            f0 = q[k, 0] - np.float64(b0)
            f1 = q[k, 1] - np.float64(b1)
            f2 = q[k, 2] - np.float64(b2)
            # argsort(-f), stable: o0 has the largest fraction
            o0, o1, o2 = 0, 1, 2
            fa, fb, fc = f0, f1, f2
            if -fb < -fa:
                o0, o1 = o1, o0
                fa, fb = fb, fa
            if -fc < -fb:
                o1, o2 = o2, o1
                fb, fc = fc, fb
                if -fb < -fa:
                    o0, o1 = o1, o0
                    fa, fb = fb, fa
            w0 = 1 - fa
            w1 = fa - fb
            w2 = fb - fc
            w3 = fc
            v0, v1, v2 = b0, b1, b2
            for step in range(4):
                if step == 0:
                    ww = w0
                else:
                    o = o0 if step == 1 else (o1 if step == 2 else o2)
                    if o == 0:
                        v0 += 1
                    elif o == 1:
                        v1 += 1
                    else:
                        v2 += 1
                    ww = w1 if step == 1 else (w2 if step == 2 else w3)
                if vec:
                    a, b_, c = _hash3_one(v0, v1, v2, seed)
                    if step == 0:
                        out[k, 0] = ww * a
                        out[k, 1] = ww * b_
                        out[k, 2] = ww * c
                    else:
                        out[k, 0] = out[k, 0] + ww * a
                        out[k, 1] = out[k, 1] + ww * b_
                        out[k, 2] = out[k, 2] + ww * c
                else:
                    hv = 2 * hash01(v0, v1, v2, seed) - 1
                    if step == 0:
                        out[k, 0] = ww * hv
                    else:
                        out[k, 0] = out[k, 0] + ww * hv
        return out


_WARM = False


def warm():
    """Compile (or load from the on-disk cache) every kernel in this process, once: call it before forking a pool, so
    the workers inherit compiled code instead of each compiling it (~10 s apiece when the cache is cold)."""
    global _WARM
    if not ON or _WARM:
        return
    import time
    from scipy.spatial import Delaunay
    t = time.perf_counter()
    p = np.array([[0.3, 0.4, 0.5], [1.7, 2.2, -0.4]])
    value_noise(p, 1)
    hash_arrays(np.zeros(2, np.int64), np.zeros(2, np.int64), np.zeros(2, np.int64), 1)
    a = np.zeros((4, 4))
    cubic2d(a, p[:, 0], p[:, 1])
    grid_at(a, p[:, 0], p[:, 1], 0.0, 0.0, 1.0)
    column(a, p[:, 0], p[:, 1], 0.0, 0.0, 1.0)
    pl_walk(p, 1, True)
    pl_walk(p, 1, False)
    pts = np.array([[0.0, 0.0], [3.0, 0.0], [0.0, 3.0], [3.0, 3.0], [1.4, 1.6]])
    tri = Delaunay(pts)
    val = np.linspace(-1, 1, len(pts))
    pl2d_tri(np.array([[1.0, 1.0]]), tri, val)
    facets(p, 1.0, 1, np.abs(np.c_[p[:, :2], np.ones(2)]) ** 4, 1.4, 32.0, lambda s, i, j: (tri, val), 1.4,
           normalise=0.03)
    linear_at(a, p[:, 0], p[:, 1], 0.0, 0.0, 1.0)
    seeds(np.array([0, 0]), np.array([3, 3]), np.array([0.0, 0.0]), np.array([1.0, 1.0]), 1, 0.565, 3, 0.8, 3)
    from . import terrain_blocks as tb  # (jointed rock: offsets with and without the maps' sharp window, ids)
    B = tb.config(6.0, 0.5)
    fd = np.array([[0.8, 1.9], [-2.0, 0.4]])
    tb.structure(p, B, fd, 0.0, want_ids=True, sharp=0.3)
    tb.offsets(p, B, fd, np.zeros(2))
    _WARM = True
    return time.perf_counter() - t


# ---------------------------------------------------------------- terrain_facets._seeds (Poisson-disk seeds)

if ON:
    @njit(cache=True)
    def _seeds_kernel(i0, j0, nI, nJ, per, seed, cell, r, rounds, lo0, lo1, hi0, hi1):
        """terrain_facets._seeds after its cell range: candidates (cell i, j, k) at hashed spots, accepted in rounds by
        priority within r (the same pairs cKDTree.query_pairs finds: neighbours up to 2 cells off; on equal
        priorities the later candidate loses, as np.where(pr[a] < pr[b], a, b) does)."""
        N = nI * nJ * per
        px = np.empty(N)
        py = np.empty(N)
        pr = np.empty(N)
        for a in range(nI):
            I = i0 + a
            for b in range(nJ):
                J = j0 + b
                for k in range(per):
                    c = (a * nJ + b) * per + k
                    px[c] = (I + hash01(I, J, np.int64(k), seed + 1)) * cell
                    py[c] = (J + hash01(I, J, np.int64(k), seed + 2)) * cell
                    pr[c] = hash01(I, J, np.int64(k), seed + 3)
        rr = r * r
        reach = np.int64(np.ceil(r / cell))
        # neighbours within r, once (CSR): the rounds then only walk these. Counted, then filled, in separate loops:
        # one loop appending to a growable array (or branching on the pass) ran 5-10x slower than the tests alone
        start = np.zeros(N + 1, np.int64)
        for a in range(nI):
            for b in range(nJ):
                for k in range(per):
                    c = (a * nJ + b) * per + k
                    cnt = 0
                    for aa in range(max(a - reach, 0), min(a + reach + 1, nI)):
                        for bb in range(max(b - reach, 0), min(b + reach + 1, nJ)):
                            for kk in range(per):
                                o = (aa * nJ + bb) * per + kk
                                dx = px[c] - px[o]
                                dy = py[c] - py[o]
                                cnt += dx * dx + dy * dy <= rr
                    start[c + 1] = cnt - 1  # (itself)
        for c in range(N):
            start[c + 1] += start[c]
        nbr = np.empty(start[N], np.int64)
        for a in range(nI):
            for b in range(nJ):
                for k in range(per):
                    c = (a * nJ + b) * per + k
                    f = start[c]
                    for aa in range(max(a - reach, 0), min(a + reach + 1, nI)):
                        for bb in range(max(b - reach, 0), min(b + reach + 1, nJ)):
                            for kk in range(per):
                                o = (aa * nJ + bb) * per + kk
                                dx = px[c] - px[o]
                                dy = py[c] - py[o]
                                if dx * dx + dy * dy <= rr and o != c:
                                    nbr[f] = o
                                    f += 1
        state = np.zeros(N, np.int8)
        win = np.zeros(N, np.bool_)
        for _ in range(rounds):
            for c in range(N):
                w_ = False
                if state[c] == 0:
                    w_ = True
                    for u in range(start[c], start[c + 1]):
                        o = nbr[u]
                        so = state[o]
                        if so == 1:  # (a neighbour is a seed already)
                            w_ = False
                            break
                        if so == 0:  # (an undecided neighbour with the higher priority)
                            lo_, hi_ = (c, o) if c < o else (o, c)
                            if (lo_ if pr[lo_] < pr[hi_] else hi_) == c:
                                w_ = False
                                break
                win[c] = w_
            for c in range(N):
                if win[c]:
                    state[c] = 1
            for c in range(N):  # (undecided neighbours of this round's winners are out)
                if win[c]:
                    for u in range(start[c], start[c + 1]):
                        o = nbr[u]
                        if state[o] == 0:
                            state[o] = -1
        m = 0
        for c in range(N):
            if state[c] == 1 and px[c] >= lo0 and px[c] <= hi0 and py[c] >= lo1 and py[c] <= hi1:
                m += 1
        pts = np.empty((m, 2))
        ids = np.empty((m, 3), np.int64)
        t = 0
        for a in range(nI):
            for b in range(nJ):
                for k in range(per):
                    c = (a * nJ + b) * per + k
                    if state[c] == 1 and px[c] >= lo0 and px[c] <= hi0 and py[c] >= lo1 and py[c] <= hi1:
                        pts[t, 0] = px[c]
                        pts[t, 1] = py[c]
                        ids[t, 0] = i0 + a
                        ids[t, 1] = j0 + b
                        ids[t, 2] = k
                        t += 1
        return pts, ids


def seeds(lo_c, hi_c, lo, hi, seed, cell, per, r, rounds):
    """terrain_facets._seeds through the kernel (cells lo_c..hi_c inclusive)."""
    return _seeds_kernel(int(lo_c[0]), int(lo_c[1]), int(hi_c[0] - lo_c[0] + 1), int(hi_c[1] - lo_c[1] + 1), int(per),
                         int(seed), float(cell), float(r), int(rounds), float(lo[0]), float(lo[1]), float(hi[0]),
                         float(hi[1]))



# ---------------------------------------------------------------- linear grid lookups (terrain_cliffs.Region.s)

if ON:
    @njit(cache=True)
    def linear_at(a, x, y, x0, y0, d):
        """map_coordinates(a, [(x - x0) / d, (y - y0) / d], order=1, mode="nearest") (ni_splines' order-1 weights:
        w0 = 1 - frac, w1 = 1 - w0)."""
        n0, n1 = a.shape
        n = x.shape[0]
        out = np.empty(n)
        for k in range(n):
            r = (x[k] - x0) / d
            q = (y[k] - y0) / d
            fr = np.floor(r)
            fq = np.floor(q)
            s0 = np.int64(fr)
            s1 = np.int64(fq)
            u0 = 1.0 - (r - fr)
            u1 = 1.0 - u0
            v0 = 1.0 - (q - fq)
            v1 = 1.0 - v0
            t = 0.0
            for i in range(2):
                ii = min(max(s0 + i, 0), n0 - 1)
                wi = u0 if i == 0 else u1
                for j in range(2):
                    jj = min(max(s1 + j, 0), n1 - 1)
                    coeff = a[ii, jj]
                    coeff *= wi
                    coeff *= v0 if j == 0 else v1
                    t += coeff
            out[k] = t
        return out


# ---------------------------------------------------------------- terrain_blocks (jointed, bedded rock)
# The structure's per-point work (bed coordinate, bed slots, minor joints per bed, master joints, ids) compiled. What
# numpy computes through SVML or BLAS stays numpy and comes in as tables or arrays: each super-bed's cuts (h ** 1.2),
# each bed's joint frames (sin/cos), the master joints' plan projections (q[:, :2] @ n2); the carve (logaddexp) is
# applied by the caller.

if ON:
    _BP_NCUT = 6
    _BP_SLOTS = 3
    _BP_SOFT = 0.1
    _BP_LEVER = 3.0
    _BP_ABSENT = 0.35

    @njit(cache=True, inline="always")
    def _clip(x, lo, hi):
        """np.clip for floats (numpy's _NPY_MIN(_NPY_MAX(x, lo), hi))."""
        a = x if x > lo else lo
        return a if a < hi else hi

    @njit(cache=True, inline="always")
    def _hb(i, j, s):
        return hash01(i, j, np.int64(0), s)

    @njit(cache=True, inline="always")
    def _bvn(q, a, b, seed):
        """terrain_blocks._vn for one point: value noise and its derivative along q."""
        i0 = np.int64(np.floor(q))
        i1 = np.int64(np.floor(a))
        i2 = np.int64(np.floor(b))
        x0 = q - np.float64(i0)
        x1 = a - np.float64(i1)
        x2 = b - np.float64(i2)
        u0 = x0 * x0 * x0 * (x0 * (x0 * 6 - 15) + 10)
        u1 = x1 * x1 * x1 * (x1 * (x1 * 6 - 15) + 10)
        u2 = x2 * x2 * x2 * (x2 * (x2 * 6 - 15) + 10)
        du = 30 * (x0 * x0) * ((x0 - 1) * (x0 - 1))
        out = 0.0
        d = 0.0
        for dy in range(2):
            wy = u1 if dy else 1 - u1
            for dz in range(2):
                wz = u2 if dz else 1 - u2
                w = wy * wz
                if w == 0.0:  # (both terms +-0.0 added to a sum that is never -0.0: skipped, exactly)
                    continue
                h0 = hash01(i0, i1 + dy, i2 + dz, seed)
                h1 = hash01(i0 + 1, i1 + dy, i2 + dz, seed)
                out += w * (h0 + u0 * (h1 - h0))
                d += w * du * (h1 - h0)
        return out, d

    @njit(cache=True, inline="always")
    def _bwarp(x, sp, a, b, seed):
        """terrain_blocks._warp (big 0.25, jit 0.1) for one point: (phi, dphi)."""
        big = 0.25
        jit = 0.1
        L = 4 * sp
        v1, d1 = _bvn(x / L, a, b + 0.5, seed + 1)
        v2, d2 = _bvn(0.8 * x / sp, a, b, seed)
        phi = (x + L * big * (2 * v1 - 1)) / sp + jit * v2
        dphi = (1 + 2 * big * d1) / sp + jit * 0.8 * d2 / sp
        lo = 0.08 / sp
        return phi, (dphi if dphi >= lo else lo)

    @njit(cache=True, inline="always")
    def _bR(x, e):
        if x < -e:
            return 0.0
        if x > e:
            return x
        return (x + e) * (x + e) / (4 * e)

    @njit(cache=True, inline="always")
    def _bwin(lo, hi, c, a, e):
        """terrain_blocks._win for one interval."""
        t = hi - c
        if t + a < -e:  # (the interval wholly under the window: both G are (0 - 0) / 2a, exactly 0)
            return 0.0
        g1 = (_bR(t + a, e) - _bR(t - a, e)) / (2 * a)
        t = lo - c
        g0 = (_bR(t + a, e) - _bR(t - a, e)) / (2 * a)
        return g1 - g0

    @njit(cache=True, inline="always")
    def _babsent(i, j, s):
        return (_hb(i, j, s) < _BP_ABSENT) and not (_hb(i - 1, j, s) < _BP_ABSENT)

    @njit(cache=True, inline="always")
    def _bface(n0, n1, fd0, fd1):
        """terrain_blocks.face_weight for one point."""
        t = 0.0
        t += fd0 * n0
        t += fd1 * n1
        q = 0.0
        q += fd0 * fd0
        q += fd1 * fd1
        cs = abs(t) / np.sqrt(q + 0.04)
        x = _clip((cs - 0.93) / (0.7 - 0.93), 0.0, 1.0)
        return x * x * (3 - 2 * x)

    @njit(cache=True)
    def _blocks_bed_coord(p, zoff, S, seed):
        """terrain_blocks._bed_coord: (Phi, dPhi)."""
        n = p.shape[0]
        Phi = np.empty(n)
        dPhi = np.empty(n)
        for k in range(n):
            x, y, z = p[k, 0], p[k, 1], p[k, 2]
            und = 0.3 * S * (_vn(x / 10.0, y / 10.0, 3.5, seed + 2) - 0.5) + \
                0.5 * S * (_vn(x / 28.0, y / 28.0, 7.5, seed + 3) - 0.5)
            und = und + 0.3 * (_vn(x / 3.0, y / 3.0, z / 3.0, seed + 5) - 0.5)
            Phi[k], dPhi[k] = _bwarp(z + zoff[k] + und, S, x / 40.0, y / 40.0, seed)
        return Phi, dPhi

    @njit(cache=True, inline="always")
    def _bjoint_coord(x, y, z, rough, K, j, m, thick, nrm, fpar, seed):
        """terrain_blocks._joint_coord for one point in bed (K, j), family m: (phi, dphi). rough: the point's
        0.4 * (value noise(p / 3) - 0.5) for this family (the same in every bed)."""
        sp = _clip(fpar[2] * thick, fpar[3], fpar[4]) * (1.0 if m == 0 else (1.3 if m == 1 else 1.7))
        s = seed + 60 + m
        bid = np.float64(K * 16 + j)
        wav = 0.25 * sp * (_vn(z / (1.5 * sp), bid, m + 0.5, s + 7) - 0.5)
        d = 0.0
        d += x * nrm[0]
        d += y * nrm[1]
        d += z * nrm[2]
        return _bwarp(d + wav + rough, sp, bid, np.float64(m), s)

    @njit(cache=True, inline="always")
    def _bjoint_value_g(g, jj, t_m, half, z_m, zh, fpar, seed):
        """terrain_blocks._joint_value for the merged block g = i - absent(i) (with the chipped corners when fpar's
        chip > 0)."""
        s = seed + 80
        h1 = _hb(g, jj, s)
        h2 = _hb(g, jj, s + 1)
        h3 = _hb(g, jj, s + 2)
        v = fpar[8] * (2 * h1 - 1)
        if h2 < fpar[11]:
            v = fpar[10] * (0.6 + 0.8 * h1)
        if h2 > 1 - fpar[13]:
            v = -fpar[12] * (0.6 + 0.8 * h1)
        v = v + fpar[9] * (2 * h3 - 1) * _clip(t_m, -_BP_LEVER, _BP_LEVER)
        chip = fpar[19]
        if chip > 0:
            a = t_m / (half if half >= 0.2 else 0.2)
            b = z_m / (zh if zh >= 0.2 else 0.2)
            for c in range(2):
                hc = _hb(g, jj, s + 3 + c)
                st = 1.0 if _hb(g, jj, s + 5 + 2 * c) < 0.5 else -1.0
                sz = 1.0 if _hb(g, jj, s + 6 + 2 * c) < 0.5 else -1.0
                u = st * a + sz * b
                on = 1.0 if hc < (0.6 if c == 0 else 0.3) else 0.0
                x = _clip((u - 0.6) / 1.0, 0.0, 1.0)
                v = v + on * chip * (0.5 + 0.5 * hc) * x * x * (3 - 2 * x)
        return v

    @njit(cache=True)
    def _blocks_offsets(p, fd, Phi, dPhi, Kmin, cuts, nrms, n2s, fpar, seed, sharp, out, out2):
        """terrain_blocks.offsets before the carve: per point the bincount of ol * (v + J) over its bed slots (out),
        and with sharp > 0 the same over the +-sharp window (out2)."""
        n = p.shape[0]
        ramp = fpar[18]
        sup = fpar[0]
        thin = fpar[1]
        has_sharp = sharp > 0
        aw_f = sharp if (has_sharp and sharp > ramp) else ramp  # (max(ramp, sharp or 0.0))
        sj = seed + 80 + 9
        rough = np.empty(3)
        have = np.zeros(3, np.bool_)
        ols = np.empty(2 * _BP_SLOTS + 1)
        ols2 = np.empty(2 * _BP_SLOTS + 1)
        lows = np.zeros(2 * _BP_SLOTS + 3, np.bool_)
        for k in range(n):
            x, y, z = p[k, 0], p[k, 1], p[k, 2]
            fd0, fd1 = fd[k, 0], fd[k, 1]
            ph = Phi[k]
            dp = dPhi[k]
            have[0] = have[1] = have[2] = False  # (each family's rough edge noise, once per point when needed)
            K0 = np.int64(np.floor(ph))
            aw = aw_f * dp
            e_ = _BP_SOFT * dp
            if not e_ >= 1e-9:
                e_ = 1e-9
            ew = 0.9 * aw
            ew = e_ if e_ <= ew else ew
            a = ramp * dp
            ea = _BP_SOFT * dp
            ea9 = 0.9 * a
            ea = ea if ea <= ea9 else ea9
            a2 = 0.0
            e2 = 0.0
            if has_sharp:
                a2 = sharp * dp
                e2 = (_BP_SOFT if _BP_SOFT <= 0.5 * sharp else 0.5 * sharp) * dp
                e29 = 0.9 * a2
                e2 = e2 if e2 <= e29 else e29
            acc = 0.0
            acc2 = 0.0
            for dk in range(-1, 2):
                K = K0 + dk
                row = K - Kmin
                for jb in range(_BP_NCUT):
                    lo = np.float64(K) + cuts[row, jb]
                    hi = np.float64(K) + cuts[row, jb + 1]
                    if not hi > lo:
                        continue
                    ol = _bwin(lo, hi, ph, aw, ew)
                    if not ol > 0:
                        continue
                    phw = ph + aw
                    pmw = ph - aw
                    oc = 0.5 * ((hi if hi <= phw else phw) + (lo if lo >= pmw else pmw))
                    th = (hi - lo) * sup
                    if has_sharp and sharp > ramp:
                        ol = _bwin(lo, hi, ph, a, ea)
                        pha = ph + a
                        pma = ph - a
                        oc = 0.5 * ((hi if hi <= pha else pha) + (lo if lo >= pma else pma))
                    mid = 0.5 * (lo + hi)
                    t_m = (oc - mid) / dp
                    zh = 0.5 * (hi - lo) / dp
                    # the bed's own offset (terrain_blocks._bed_value)
                    s = seed + 30
                    jb64 = np.int64(jb)
                    h1 = _hb(K, jb64, s)
                    h2 = _hb(K, jb64, s + 1)
                    along = _clip(1.4 * _vn(x / 9.0, y / 9.0, np.float64(K * 16 + jb64), s + 2) - 0.25, 0.0, 1.0)
                    if th < thin:
                        v = along * fpar[14]
                    else:
                        v = along * (-fpar[15] * _clip((th - 1.2) / 2.5, 0.0, 1.0))
                    v = v + fpar[16] * (2 * h1 - 1) + fpar[17] * (2 * h2 - 1) * _clip(t_m, -_BP_LEVER, _BP_LEVER)
                    # the minor joints inside it (terrain_blocks._joints_in_bed)
                    J = 0.0
                    J2 = 0.0
                    for m in range(3):
                        fw = _bface(n2s[row, jb, m, 0], n2s[row, jb, m, 1], fd0, fd1)
                        w = fpar[5 + m] * fw * (1.0 if th >= thin else 0.0)
                        if not w > 0:
                            continue
                        if not have[m]:
                            rough[m] = 0.4 * (_vn(x / 3.0, y / 3.0, z / 3.0, seed + 60 + m + 9) - 0.5)
                            have[m] = True
                        phj, dpj = _bjoint_coord(x, y, z, rough[m], K, jb64, m, th, nrms[row, jb, m], fpar, seed)
                        aj = ramp * dpj
                        jj = (K * 16 + jb64) * 5 + m
                        i0 = np.int64(np.floor(phj))
                        ej = _BP_SOFT * dpj
                        ej9 = 0.9 * aj
                        ej = ej if ej <= ej9 else ej9
                        aj2 = 0.0
                        ej2 = 0.0
                        if has_sharp:
                            aj2 = sharp * dpj
                            ej2 = (_BP_SOFT if _BP_SOFT <= 0.5 * sharp else 0.5 * sharp) * dpj
                            ej29 = 0.9 * aj2
                            ej2 = ej2 if ej2 <= ej29 else ej29
                        jacc = 0.0
                        jacc2 = 0.0
                        # the slots either window reaches, then each boundary's "absent" hash once (a boundary
                        # i is absent when h(i) < P and h(i - 1) isn't: lows[t] = h(i0 - SLOTS - 1 + t) < P)
                        first = -1
                        last = -2
                        for di in range(-_BP_SLOTS, _BP_SLOTS + 1):
                            fi = np.float64(i0 + di)
                            olj = _bwin(fi, fi + 1.0, phj, aj, ej)
                            olj2 = _bwin(fi, fi + 1.0, phj, aj2, ej2) if has_sharp else 0.0
                            t = di + _BP_SLOTS
                            ols[t] = olj
                            ols2[t] = olj2
                            if olj > 0 or (has_sharp and olj2 > 0):
                                if first < 0:
                                    first = t
                                last = t
                        if first < 0:
                            continue
                        for t in range(first, last + 3):  # (boundaries first .. last + 1 and the one under first)
                            lows[t] = _hb(i0 - _BP_SLOTS - 1 + t, jj, sj) < _BP_ABSENT
                        for t in range(first, last + 1):
                            olj = ols[t]
                            olj2 = ols2[t]
                            if not (olj > 0 or (has_sharp and olj2 > 0)):
                                continue
                            i = i0 + t - _BP_SLOTS
                            fi = np.float64(i)
                            fi1 = np.float64(i + 1)
                            ab0 = lows[t + 1] and not lows[t]  # (boundary i)
                            ab1 = lows[t + 2] and not lows[t + 1]  # (boundary i + 1)
                            pa = phj + aj
                            pm = phj - aj
                            ocj = 0.5 * ((fi1 if fi1 <= pa else pa) + (fi if fi >= pm else pm))
                            mid_ = i + 0.5 + 0.5 * (1.0 if ab1 else 0.0) - 0.5 * (1.0 if ab0 else 0.0)
                            tj = (ocj - mid_) / dpj
                            ext = 1 + (1 if ab0 else 0) + (1 if ab1 else 0)
                            vj = _bjoint_value_g(i - (1 if ab0 else 0), jj, tj, 0.5 * ext / dpj, t_m, zh, fpar, seed)
                            jacc += olj * vj
                            if has_sharp:
                                jacc2 += olj2 * vj
                        J += w * jacc
                        if has_sharp:
                            J2 += w * jacc2
                    acc += ol * (v + J)
                    if has_sharp:
                        acc2 += _bwin(lo, hi, ph, a2, e2) * (v + J2)
            out[k] = acc
            if has_sharp:
                out2[k] = acc2

    @njit(cache=True)
    def _blocks_face3(fd, n2):
        """terrain_blocks.face_weight per family of plan normals n2 (3, 2): (3, n)."""
        n = fd.shape[0]
        out = np.empty((3, n))
        for m in range(3):
            for k in range(n):
                out[m, k] = _bface(n2[m, 0], n2[m, 1], fd[k, 0], fd[k, 1])
        return out

    @njit(cache=True)
    def _blocks_masters(p, mw, mxb, mu, mpar, seed, depth, near):
        """terrain_blocks._masters from each family's face weight mw, plan projection mxb = q[:, :2] @ n2 and
        mu = q[:, :2] @ t2 (numpy's, per point; points where the family's weight is 0 skipped)."""
        n = p.shape[0]
        spacing, pm, seg, p_seg, half_m, taper, lean_c = mpar[0], mpar[1], mpar[2], mpar[3], mpar[4], mpar[5], mpar[6]
        for k in range(n):
            depth[k] = 0.0
            near[k] = np.inf
        s0 = seed + 200
        for m in range(3):
            s = s0 + 11 * m
            sp = spacing * (1.0 if m == 0 else (1.3 if m == 1 else 1.7))
            mm = np.int64(m)
            for k in range(n):
                w = mw[m, k]
                if not w > 0:
                    continue
                zq = p[k, 2]
                u = mu[m, k]
                wav = 2.4 * (_vn(zq / 14.0, u / 14.0, m + 0.5, s + 6) - 0.5) + \
                    0.6 * (_vn(zq / 4.0, u / 4.0, m + 7.5, s + 8) - 0.5)
                x = mxb[m, k] + wav
                i0 = np.int64(np.floor(x / sp))
                zs = np.int64(np.floor(zq / seg))
                best = 0.0
                dmin = np.inf
                for di in range(-1, 2):
                    i = i0 + di
                    if not _hb(i, mm, s) < pm:
                        continue
                    x0 = (i + 0.5 + 0.35 * (2 * _hb(i, mm, s + 5) - 1)) * sp
                    lean = lean_c * (2 * _hb(i, mm, s + 4) - 1)
                    op = 0.4 + 0.6 * _hb(i, mm, s + 7)
                    g = 0.0
                    for dz in range(-1, 2):
                        zk = zs + dz
                        on = 1.0 if _hb(i, zk, s + 1) < p_seg else 0.0
                        zc = (zk + 0.5 + 0.3 * (2 * _hb(i, zk, s + 2) - 1)) * seg
                        half = 0.5 * seg * (0.5 + 0.6 * _hb(i, zk, s + 3))
                        ends = on * _clip((half - abs(zq - zc)) / taper, 0.0, 1.0)
                        d = abs(x - (x0 + 1.5 * (2 * _hb(i, zk, s + 9) - 1) + lean * (zq - zc)))
                        v = _clip(1 - d / half_m, 0.0, 1.0)
                        gg = op * ends * v * v * (3 - 2 * v)
                        g = g if g >= gg else gg
                        if ends > 0:
                            dmin = dmin if dmin <= d else d
                    best = best if best >= g else g
                wb = w * best
                depth[k] = depth[k] if depth[k] >= wb else wb
                nd = dmin if w > 0.3 else np.inf
                near[k] = near[k] if near[k] <= nd else nd

    @njit(cache=True)
    def _blocks_ids(p, fd, Phi, dPhi, Kmin, cuts, nrms, n2s, fpar, seed, iK, ij, fo, blocks, fam):
        """terrain_blocks.ids: per point iK, ij (the bed), fo columns (thick, bed_edge, below_top, bed_crack, thin),
        per family blocks[m] and fam[m] columns (weights, edges, open)."""
        n = p.shape[0]
        sup = fpar[0]
        thin = fpar[1]
        s = seed + 80 + 9
        for k in range(n):
            x, y, z = p[k, 0], p[k, 1], p[k, 2]
            ph = Phi[k]
            dp = dPhi[k]
            K0 = np.int64(np.floor(ph))
            # the own bed: the first slot holding Phi (np.argmax over the slots: slot 0 when none does)
            oK = K0 - 1
            oj = np.int64(0)
            olo = np.float64(oK) + cuts[oK - Kmin, 0]
            ohi = np.float64(oK) + cuts[oK - Kmin, 1]
            found = False
            for dk in range(-1, 2):
                K = K0 + dk
                row = K - Kmin
                for jb in range(_BP_NCUT):
                    lo = np.float64(K) + cuts[row, jb]
                    hi = np.float64(K) + cuts[row, jb + 1]
                    if lo <= ph and ph < hi and hi > lo:
                        oK = K
                        oj = np.int64(jb)
                        olo = lo
                        ohi = hi
                        found = True
                        break
                if found:
                    break
            K = oK
            j = oj
            th = (ohi - olo) * sup
            d_lo = (ph - olo) / dp
            d_hi = (ohi - ph) / dp
            plane_hi = d_hi < d_lo
            top = ohi >= K + 1 - 1e-9
            Kp = K + 1 if (plane_hi and top) else K
            jp = (np.int64(0) if top else j + 1) if plane_hi else j
            pc = _hb(Kp, jp, seed + 90)
            crack = _clip((pc - 0.75) / 0.25, 0.0, 1.0) * _clip(
                (_vn(x / 15.0, y / 15.0, np.float64(jp + 16 * Kp), seed + 92) - 0.4) / 0.25, 0.0, 1.0)
            iK[k] = K
            ij[k] = j
            fo[k, 0] = th
            fo[k, 1] = d_lo if d_lo <= d_hi else d_hi
            fo[k, 2] = (np.float64(K + 1) - ph) / dp
            fo[k, 3] = crack
            fo[k, 4] = 1.0 if th < thin else 0.0
            row = K - Kmin
            for m in range(3):
                rough = 0.4 * (_vn(x / 3.0, y / 3.0, z / 3.0, seed + 60 + m + 9) - 0.5)
                phj, dpj = _bjoint_coord(x, y, z, rough, K, j, m, th, nrms[row, j, m], fpar, seed)
                jj = (K * 16 + j) * 5 + m
                i = np.int64(np.floor(phj))
                lo_b = i - (1 if _babsent(i, jj, s) else 0)
                hi_b = i + 1 + (1 if _babsent(i + 1, jj, s) else 0)
                blocks[m, k] = lo_b
                fam[m, k, 0] = fpar[5 + m] * _bface(n2s[row, j, m, 0], n2s[row, j, m, 1], fd[k, 0], fd[k, 1]) * \
                    (1.0 if th >= thin else 0.0)
                dl = (phj - lo_b) / dpj
                dh = (hi_b - phj) / dpj
                e = dl if dl <= dh else dh
                fam[m, k, 1] = e
                b = lo_b if dl < dh else hi_b
                fam[m, k, 2] = e if _hb(b, jj, seed + 91) < fpar[20] else np.inf


def _blocks_fpar(B):
    return np.array([B["super"], B["thin"], B["joint"], B["joint_min"], B["joint_max"], B["family"][0],
                     B["family"][1], B["family"][2], B["amp"], B["tip"], B["recess"], B["p_recess"], B["proud"],
                     B["p_proud"], B["package"], B["thick_proud"], B["bed_amp"], B["bed_tilt"], B["ramp"],
                     float(B.get("chip", 0) or 0.0), B["open"]], np.float64)


def blocks_pre(p, B, fd, zoff, AZ):
    """terrain_blocks' (Phi, dPhi, (master groove depth, master distance)) at points p."""
    import math
    p = np.ascontiguousarray(p, dtype=np.float64)
    n = len(p)
    zo = np.ascontiguousarray(np.broadcast_to(np.asarray(zoff, np.float64), (n,)))
    Phi, dPhi = _blocks_bed_coord(p, zo, float(B["super"]), int(B["seed"]))
    M = B["master"]
    mw, mxb, mu = np.zeros((3, n)), np.zeros((3, n)), np.zeros((3, n))
    n2s = np.array([[math.cos(math.radians(a)), math.sin(math.radians(a))] for a in AZ[:3]])
    W = _blocks_face3(np.ascontiguousarray(fd, dtype=np.float64), n2s)
    for m in range(3):  # (numpy's: the plan projections exactly as terrain_blocks._masters makes them)
        n2 = n2s[m]
        w = W[m]
        k = np.flatnonzero(w > 0)
        if not len(k):
            continue
        q = p[k]
        t2 = np.c_[-n2[1], n2[0]]
        mw[m, k] = w[k]
        mu[m, k] = q[:, :2] @ t2[0]
        mxb[m, k] = q[:, :2] @ n2
    mpar = np.array([M["spacing"], M["p"], M["seg"], M["p_seg"], M["half"], M["taper"],
                     math.tan(math.radians(15.0))])
    depth, near = np.empty(n), np.empty(n)
    _blocks_masters(p, mw, mxb, mu, mpar, int(B["seed"]), depth, near)
    return Phi, dPhi, (depth, near)


_TABLES = {}


def _blocks_tables(Phi, B, cuts_fn, frame_fn, ncut):
    """The super-beds' cuts and every bed's joint frames over the K range the points reach (numpy's own functions,
    cached per super-bed range)."""
    K0 = np.floor(Phi).astype(np.int64)
    Kmin, Kmax = int(K0.min()) - 1, int(K0.max()) + 1
    key = (id(B), B["seed"], B["super"], Kmin, Kmax)
    hit = _TABLES.get(key)
    if hit is not None and hit[0] is B:
        return hit[1]
    Ks = np.arange(Kmin, Kmax + 1, dtype=np.int64)
    cuts = np.ascontiguousarray(cuts_fn(Ks, B))
    nk = len(Ks)
    KK = np.repeat(Ks, ncut)
    JJ = np.tile(np.arange(ncut, dtype=np.int64), nk)
    nrms = np.empty((nk, ncut, 3, 3))
    n2s = np.empty((nk, ncut, 3, 2))
    for m in range(3):
        nrm, n2 = frame_fn(KK, JJ, m, B)
        nrms[:, :, m] = nrm.reshape(nk, ncut, 3)
        n2s[:, :, m] = n2.reshape(nk, ncut, 2)
    out = (Kmin, cuts, nrms, n2s)
    if len(_TABLES) > 64:
        _TABLES.clear()
    _TABLES[key] = (B, out)
    return out


def blocks_offsets(p, B, fd, Phi, dPhi, sharp, cuts_fn, frame_fn, ncut):
    """terrain_blocks.offsets' per-point sums before the carve: (o, o2), o2 None without sharp."""
    p = np.ascontiguousarray(p, dtype=np.float64)
    fd = np.ascontiguousarray(fd, dtype=np.float64)
    n = len(p)
    Kmin, cuts, nrms, n2s = _blocks_tables(Phi, B, cuts_fn, frame_fn, ncut)
    out = np.empty(n)
    out2 = np.empty(n) if sharp is not None else out
    _blocks_offsets(p, fd, np.ascontiguousarray(Phi, dtype=np.float64), np.ascontiguousarray(dPhi, dtype=np.float64),
                    Kmin, cuts, nrms, n2s, _blocks_fpar(B), int(B["seed"]),
                    float(sharp) if sharp is not None else -1.0, out, out2)
    return out, (out2 if sharp is not None else None)


def blocks_ids(p, B, fd, Phi, dPhi, cuts_fn, frame_fn, ncut):
    """terrain_blocks.ids' arrays: (K, j, fo (n, 5): thick, bed_edge, below_top, bed_crack, thin; blocks (3, n);
    fam (3, n, 3): weights, edges, open)."""
    p = np.ascontiguousarray(p, dtype=np.float64)
    fd = np.ascontiguousarray(fd, dtype=np.float64)
    n = len(p)
    Kmin, cuts, nrms, n2s = _blocks_tables(Phi, B, cuts_fn, frame_fn, ncut)
    iK, ij = np.empty(n, np.int64), np.empty(n, np.int64)
    fo = np.empty((n, 5))
    blocks = np.empty((3, n), np.int64)
    fam = np.empty((3, n, 3))
    _blocks_ids(p, fd, np.ascontiguousarray(Phi, dtype=np.float64), np.ascontiguousarray(dPhi, dtype=np.float64),
                Kmin, cuts, nrms, n2s, _blocks_fpar(B), int(B["seed"]), iK, ij, fo, blocks, fam)
    return iK, ij, fo, blocks, fam
