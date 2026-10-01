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
                    out += wx * wy * wz * hash01(ix + dx, iy + dy, iz + dz, seed)
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
    def _select(bidx, ax, bi, sel):
        m = 0
        for k in range(bidx.shape[0]):
            if bidx[k, ax] == bi:
                sel[m] = k
                m += 1
        return m

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


def facets(p, size, seed, w, stretch, group, triangulation, gain):
    """terrain_facets.facets from its weights w (n, 3) on: every projection's block found and triangulated (through
    `triangulation(seed, gi, gj)`, the module's cache), its points located and interpolated block by block (each
    block's points in their own order: find_simplex's chained start), summed by weight. None when the points touch
    too many blocks (the caller then takes the numpy path)."""
    p = np.ascontiguousarray(p, dtype=np.float64)
    w = np.ascontiguousarray(w, dtype=np.float64)
    n = len(p)
    blocks = _blocks(p, w, float(size), float(stretch), float(group), 512)
    if len(blocks) == 0:
        return None
    x0s, x1s = np.empty((3, n)), np.empty((3, n))
    bidx = np.empty((n, 3), np.int64)
    _facets_coords(p, w, float(size), float(stretch), float(group), blocks, x0s, x1s, bidx)
    vout = np.zeros((n, 3))
    sel = np.empty(n, np.int64)
    for t, (ax, gi, gj) in enumerate(blocks):
        tri, val = triangulation(seed + 500 * int(ax), int(gi), int(gj))
        grid, g0, g1, nx, ny = _grid_of(tri)
        fpar = np.array([tri.min_bound[0], tri.min_bound[1], tri.max_bound[0], tri.max_bound[1], g0, g1, BUCKET,
                         float(tri.paraboloid_scale), float(tri.paraboloid_shift)])
        m = _select(bidx, int(ax), t, sel)
        _facets_block(p, w, float(size), float(stretch), int(ax), x0s[ax], x1s[ax], sel, m, tri.transform,
                      tri.neighbors, tri.simplices, tri.equations, val, grid, fpar, np.array([nx, ny], np.int64), vout)
    return _facets_sum(w, vout, float(gain))
