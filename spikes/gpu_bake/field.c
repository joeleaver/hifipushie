/* The terrain field's hot leaves as ONE C source, compiled twice by the same clang:
 *   - for the GPU: clang --target=amdgcn-amd-amdhsa -mcpu=gfx1150 -nogpulib -O3 -ffp-contract=off  (HIP code object,
 *     loaded through libamdhip64 with ctypes: no ROCm SDK, no hiprtc, nothing installed)
 *   - for the CPU: clang -O3 -ffp-contract=off -shared -fPIC  (a plain .so, called through ctypes)
 * Each function is a transcription of a numba kernel in src/hifipushie/fieldjit.py, operation by operation (same
 * order, no FMA contraction, no fast math), so in double precision it should match numba bit for bit; with
 * -DREAL=float -DREAL_IS_FLOAT it is the float32 variant (world coordinates in float32; grid lookups relative to the
 * grid's origin, which the host subtracts in double).
 *
 * Kernels (one thread per point; on the CPU a loop over the same body):
 *   k_column   Field.column + steep_at + grain_at + face_dir (cubic B-spline lookups, mode="nearest")
 *   k_fbm      noise.fbm (value noise on rotated lattices)
 *   k_facets   terrain_facets.facets: triplanar, a triangulation per (axis, block) looked up in a hash table, the
 *              bucket grid + walk (fieldjit._locate_fast); ambiguous points (within 1e-9 of an edge) are flagged for the
 *              host (scipy's chained walk decides those)
 *   k_blocks   terrain_blocks bed coordinate + offsets (with the maps' sharp window): fieldjit._blocks_bed_coord +
 *              _blocks_offsets
 */
#ifdef DEBUG
#include <stdio.h>
#endif
typedef long i64;
typedef unsigned long u64;
typedef int i32;

#ifndef REAL
#define REAL double
#endif
typedef REAL real;

#ifdef __AMDGCN__
#define KERNEL __attribute__((amdgpu_kernel, amdgpu_flat_work_group_size(1, 256)))
#define DEV static inline __attribute__((always_inline))
#define GID ((i64)__builtin_amdgcn_workgroup_id_x() * 256 + (i64)__builtin_amdgcn_workitem_id_x())
#define LOOP(n) i64 k = GID; if (k >= (n)) return; {
#define ENDLOOP }
#else
#define KERNEL
#define DEV static inline
#define LOOP(n) for (i64 k = 0; k < (n); k++) {
#define ENDLOOP }
#endif

#define FLOOR(x) __builtin_floor((double)(x))
#define SQRT(x) ((real)__builtin_sqrt((double)(x)))
#define FABS(x) ((x) < 0 ? -(x) : (x))
#if defined(REAL_IS_FLOAT)
#undef SQRT
#undef FLOOR
#define SQRT(x) __builtin_sqrtf(x)
#define FLOOR(x) __builtin_floorf(x)
#endif

/* ------------------------------------------------------------------ hash + value noise */

DEV real hash01(i64 ix, i64 iy, i64 iz, i64 seed) {
    u64 h = ((u64)ix * 73856093UL) ^ ((u64)iy * 19349663UL) ^ ((u64)iz * 83492791UL) ^ ((u64)seed * 2654435761UL);
    h ^= h >> 13;
    h *= 0x5bd1e995UL;
    h ^= h >> 15;
    return (real)(h & 0xFFFFFFUL) / (real)16777215.0;
}

DEV real vn(real x, real y, real z, i64 seed) {
    real fx = FLOOR(x), fy = FLOOR(y), fz = FLOOR(z);
    i64 ix = (i64)fx, iy = (i64)fy, iz = (i64)fz;
    fx = x - (real)ix; fy = y - (real)iy; fz = z - (real)iz;
    real ux = fx * fx * fx * (fx * (fx * 6 - 15) + 10);
    real uy = fy * fy * fy * (fy * (fy * 6 - 15) + 10);
    real uz = fz * fz * fz * (fz * (fz * 6 - 15) + 10);
    real out = 0;
    for (int dx = 0; dx < 2; dx++) {
        real wx = dx ? ux : 1 - ux;
        for (int dy = 0; dy < 2; dy++) {
            real wy = dy ? uy : 1 - uy;
            for (int dz = 0; dz < 2; dz++) {
                real wz = dz ? uz : 1 - uz;
                real w = wx * wy * wz;
                if (w != 0) out += w * hash01(ix + dx, iy + dy, iz + dz, seed);
            }
        }
    }
    return out;
}

/* ------------------------------------------------------------------ cubic B-spline lookups */

DEV void bw(real cc, real *w) {
    real x = cc - FLOOR(cc);
    real y = x, z = 1 - x;
    w[1] = (y * y * (y - 2) * 3 + 4) / 6;
    w[2] = (z * z * (z - 2) * 3 + 4) / 6;
    w[0] = z * z * z / 6;
    real w3 = 1;
    w3 -= w[0]; w3 -= w[1]; w3 -= w[2];
    w[3] = w3;
}

DEV real cubic(const real *a, i64 n0, i64 n1, real r, real q) {
    i64 s0 = (i64)FLOOR(r) - 1, s1 = (i64)FLOOR(q) - 1;
    real wr[4], wq[4];
    bw(r, wr); bw(q, wq);
    real t = 0;
    for (int i = 0; i < 4; i++) {
        i64 ii = s0 + i;
        ii = ii < 0 ? 0 : (ii > n0 - 1 ? n0 - 1 : ii);
        for (int j = 0; j < 4; j++) {
            i64 jj = s1 + j;
            jj = jj < 0 ? 0 : (jj > n1 - 1 ? n1 - 1 : jj);
            real coeff = a[ii * n1 + jj];
            coeff *= wr[i];
            coeff *= wq[j];
            t += coeff;
        }
    }
    return t;
}

/* grids: H, steep, grain, fdx, fdy, each n0 x n1, origin x0, y0, cell c (float32: the host passes x - x0 and 0).
 * out: (n, 6) h, s, steep, grain, fdx, fdy */
KERNEL void k_column(const real *H, const real *ST, const real *GR, const real *FX, const real *FY, i64 n0, i64 n1,
                     real x0, real y0, real c, const real *x, const real *y, i64 n, real *out) {
    LOOP(n)
        real r = (y[k] - y0) / c, q = (x[k] - x0) / c;
        real e = 0.5, d = 2 * e * c;
        real v0 = cubic(H, n0, n1, r, q);
        real v1 = cubic(H, n0, n1, r, q + e);
        real v2 = cubic(H, n0, n1, r, q - e);
        real v3 = cubic(H, n0, n1, r + e, q);
        real v4 = cubic(H, n0, n1, r - e, q);
        real gx = (v1 - v2) / d, gy = (v3 - v4) / d;
        out[k * 6 + 0] = v0;
        out[k * 6 + 1] = 1 / SQRT(1 + gx * gx + gy * gy);
        out[k * 6 + 2] = cubic(ST, n0, n1, r, q);
        out[k * 6 + 3] = cubic(GR, n0, n1, r, q);
        out[k * 6 + 4] = cubic(FX, n0, n1, r, q);
        out[k * 6 + 5] = cubic(FY, n0, n1, r, q);
    ENDLOOP
}

/* ------------------------------------------------------------------ fbm (noise.fbm): rot = 8 rotations (8 x 3 x 3) */

KERNEL void k_fbm(const real *p, i64 n, real scale, i64 octaves, i64 seed, const real *rot, real *out) {
    LOOP(n)
        real q0 = p[3 * k] / scale, q1 = p[3 * k + 1] / scale, q2 = p[3 * k + 2] / scale;
        real acc = 0, amp = 1, total = 0;
        for (i64 o = 0; o < octaves; o++) {
            const real *R = rot + 9 * (o % 8);
            real f = (real)(1L << o);
            real a = (q0 * R[0] + q1 * R[3] + q2 * R[6]) * f;
            real b = (q0 * R[1] + q1 * R[4] + q2 * R[7]) * f;
            real cc = (q0 * R[2] + q1 * R[5] + q2 * R[8]) * f;
            acc += amp * vn(a, b, cc, seed + 101 * o);
            total += amp;
            amp *= 0.5;
        }
        real v = 0.5 + (acc / total - 0.5) * (1 + (real)0.6 * (octaves - 1));
        out[k] = v < 0 ? 0 : (v > 1 ? 1 : v);
    ENDLOOP
}

/* ------------------------------------------------------------------ facets
 * A pool of triangulations (all blocks the points touch, every size/axis): per block b
 *   tri_off[b]  first triangle in TR (ns x 6: the scipy transform T[s, 0..2, 0..1]), NB (ns x 3), SI (ns x 3)
 *   val_off[b]  first seed in VAL
 *   grd_off[b]  first cell in GRD (nx x ny: a triangle per BUCKET cell, local index), bpar[b] = g0, g1, nx, ny
 * Blocks are found by an open-addressing table keyed on (seedax, gi, gj) (HT: 4 i64 per slot: key fields + block).
 * Coordinates in facet units (world / size), as scipy's triangulation has them. */

DEV i64 ht_find(const i64 *HT, i64 mask, i64 sa, i64 gi, i64 gj) {
    u64 h = ((u64)sa * 0x9E3779B97F4A7C15UL) ^ ((u64)gi * 0xC2B2AE3D27D4EB4FUL) ^ ((u64)gj * 0x165667B19E3779F9UL);
    h ^= h >> 29;
    i64 s = (i64)(h & (u64)mask);
    for (int t = 0; t < 64; t++) {
        const i64 *e = HT + 4 * s;
        if (e[3] < 0) return -1;
        if (e[0] == sa && e[1] == gi && e[2] == gj) return e[3];
        s = (s + 1) & mask;
    }
    return -1;
}

#define AMBIG 1e-9

/* returns the triangle (local) or -1 (ambiguous / outside). x0, x1 in the block's frame. */
DEV i64 locate(const real *TR, const i32 *NB, const i32 *GRD, const real *bp, real x0, real x1) {
    i64 gnx = (i64)bp[2], gny = (i64)bp[3];
    i64 i = (i64)FLOOR(x0 - bp[0]);
    i64 j = (i64)FLOOR(x1 - bp[1]);
    i = i < 0 ? 0 : (i > gnx - 1 ? gnx - 1 : i);
    j = j < 0 ? 0 : (j > gny - 1 ? gny - 1 : j);
    i64 s = GRD[i * gny + j];
    if (s < 0) return -1;
    for (int it = 0; it < 64; it++) {
        const real *T = TR + 6 * s;
        real c0 = T[0] * (x0 - T[4]) + T[1] * (x1 - T[5]);
        real c1 = T[2] * (x0 - T[4]) + T[3] * (x1 - T[5]);
        real c2 = 1 - c0 - c1;
        if (c0 > AMBIG && c1 > AMBIG && c2 > AMBIG) return s;
        if (c0 < c1 && c0 < c2) s = NB[3 * s];
        else if (c1 < c2) s = NB[3 * s + 1];
        else s = NB[3 * s + 2];
        if (s < 0) return -1;
    }
    return -1;
}

/* p (n x 3) world, w (n x 3) the normalised projection weights (computed by the host as numpy does: |(fd, 1)|^4 is
 * SVML pow), size, stretch, group, seed. out[k] = the facets value; amb[k] = bitmask of axes the GPU couldn't decide
 * (the host redoes those with scipy's chained walk); simp_out: the triangle per axis (the host's chained start). */
KERNEL void k_facets(const real *p, const real *w, i64 n, real size, real stretch, real group, i64 seed,
                     const i64 *HT, i64 mask, const i64 *tri_off, const i64 *val_off, const i64 *grd_off,
                     const real *bpar, const real *TR, const i32 *NB, const i32 *SI, const real *VAL, const i32 *GRD,
                     real gain, real *out, i32 *amb, i32 *simp_out) {
    LOOP(n)
        real acc = 0;
        int bad = 0;
        for (int ax = 0; ax < 3; ax++) {
            simp_out[3 * k + ax] = -1;
            real wk = w[3 * k + ax];
            if (!(wk > 0)) continue;
            real a, b, st;
            if (ax == 0) { a = p[3 * k + 1]; b = p[3 * k + 2]; st = stretch; }
            else if (ax == 1) { a = p[3 * k + 0]; b = p[3 * k + 2]; st = stretch; }
            else { a = p[3 * k + 0]; b = p[3 * k + 1]; st = 1; }
            real l0 = a / size;
            real l1 = b / st / size;
            i64 bi = (i64)FLOOR(l0 / group);
            i64 bj = (i64)FLOOR(l1 / group);
            i64 blk = ht_find(HT, mask, seed + 500 * ax, bi, bj);
            if (blk < 0) { bad |= 1 << ax; continue; }
            const real *bp = bpar + 4 * blk;
            const real *TR_ = TR + 6 * tri_off[blk];
            const i32 *NB_ = NB + 3 * tri_off[blk];
            i64 s = locate(TR_, NB_, GRD + grd_off[blk], bp, l0, l1);
            if (s < 0) { bad |= 1 << ax; continue; }
            simp_out[3 * k + ax] = (i32)s;
            const real *T = TR_ + 6 * s;
            real d0 = l0 - T[4], d1 = l1 - T[5];
            real b0 = T[0] * d0 + T[1] * d1;
            real b1 = T[2] * d0 + T[3] * d1;
            real b2 = 1 - (b0 + b1);
            const i32 *S = SI + 3 * tri_off[blk] + 3 * s;
            const real *V = VAL + val_off[blk];
            acc += wk * (b0 * V[S[0]] + b1 * V[S[1]] + b2 * V[S[2]]);
        }
        real nrm = SQRT(w[3 * k] * w[3 * k] + w[3 * k + 1] * w[3 * k + 1] + w[3 * k + 2] * w[3 * k + 2]);
        real r = gain * acc / nrm;
        out[k] = r < -1 ? -1 : (r > 1 ? 1 : r);
        amb[k] = bad;
    ENDLOOP
}

/* ------------------------------------------------------------------ terrain_blocks (fieldjit._blocks_*) */

#define NCUT 6
#define SLOTS 3
#define BSOFT 0.1
#define LEVER 3.0
#define ABSENT 0.35

DEV real clip(real x, real lo, real hi) { real a = x > lo ? x : lo; return a < hi ? a : hi; }
DEV real hb(i64 i, i64 j, i64 s) { return hash01(i, j, 0, s); }

DEV void bvn(real q, real a, real b, i64 seed, real *out_, real *d_) {
    i64 i0 = (i64)FLOOR(q), i1 = (i64)FLOOR(a), i2 = (i64)FLOOR(b);
    real x0 = q - (real)i0, x1 = a - (real)i1, x2 = b - (real)i2;
    real u0 = x0 * x0 * x0 * (x0 * (x0 * 6 - 15) + 10);
    real u1 = x1 * x1 * x1 * (x1 * (x1 * 6 - 15) + 10);
    real u2 = x2 * x2 * x2 * (x2 * (x2 * 6 - 15) + 10);
    real du = 30 * (x0 * x0) * ((x0 - 1) * (x0 - 1));
    real out = 0, d = 0;
    for (int dy = 0; dy < 2; dy++) {
        real wy = dy ? u1 : 1 - u1;
        for (int dz = 0; dz < 2; dz++) {
            real wz = dz ? u2 : 1 - u2;
            real w = wy * wz;
            if (w == 0) continue;
            real h0 = hash01(i0, i1 + dy, i2 + dz, seed);
            real h1 = hash01(i0 + 1, i1 + dy, i2 + dz, seed);
            out += w * (h0 + u0 * (h1 - h0));
            d += w * du * (h1 - h0);
        }
    }
    *out_ = out; *d_ = d;
}

DEV void bwarp(real x, real sp, real a, real b, i64 seed, real *phi, real *dphi) {
    real big = 0.25, jit = 0.1;
    real L = 4 * sp;
    real v1, d1, v2, d2;
    bvn(x / L, a, b + 0.5, seed + 1, &v1, &d1);
    bvn(0.8 * x / sp, a, b, seed, &v2, &d2);
    *phi = (x + L * big * (2 * v1 - 1)) / sp + jit * v2;
    real dp = (1 + 2 * big * d1) / sp + jit * 0.8 * d2 / sp;
    real lo = 0.08 / sp;
    *dphi = dp >= lo ? dp : lo;
}

DEV real bR(real x, real e) {
    if (x < -e) return 0;
    if (x > e) return x;
    return (x + e) * (x + e) / (4 * e);
}

DEV real bwin(real lo, real hi, real c, real a, real e) {
    real t = hi - c;
    if (t + a < -e) return 0;
    real g1 = (bR(t + a, e) - bR(t - a, e)) / (2 * a);
    t = lo - c;
    real g0 = (bR(t + a, e) - bR(t - a, e)) / (2 * a);
    return g1 - g0;
}

DEV real bface(real n0, real n1, real fd0, real fd1) {
    real t = 0; t += fd0 * n0; t += fd1 * n1;
    real q = 0; q += fd0 * fd0; q += fd1 * fd1;
    real cs = FABS(t) / SQRT(q + (real)0.04);
    real x = clip((cs - (real)0.93) / ((real)0.7 - (real)0.93), 0, 1);
    return x * x * (3 - 2 * x);
}

DEV void bjoint_coord(real x, real y, real z, real rough, i64 K, i64 j, int m, real thick, const real *nrm,
                      const real *fpar, i64 seed, real *phi, real *dphi) {
    real sp = clip(fpar[2] * thick, fpar[3], fpar[4]) * (m == 0 ? (real)1.0 : (m == 1 ? (real)1.3 : (real)1.7));
    i64 s = seed + 60 + m;
    real bid = (real)(K * 16 + j);
    real wav = (real)0.25 * sp * (vn(z / ((real)1.5 * sp), bid, (real)m + (real)0.5, s + 7) - (real)0.5);
    real d = 0; d += x * nrm[0]; d += y * nrm[1]; d += z * nrm[2];
    bwarp(d + wav + rough, sp, bid, (real)m, s, phi, dphi);
}

DEV real bjoint_value_g(i64 g, i64 jj, real t_m, real half, real z_m, real zh, const real *fpar, i64 seed) {
    i64 s = seed + 80;
    real h1 = hb(g, jj, s), h2 = hb(g, jj, s + 1), h3 = hb(g, jj, s + 2);
    real v = fpar[8] * (2 * h1 - 1);
    if (h2 < fpar[11]) v = fpar[10] * ((real)0.6 + (real)0.8 * h1);
    if (h2 > 1 - fpar[13]) v = -fpar[12] * ((real)0.6 + (real)0.8 * h1);
    v = v + fpar[9] * (2 * h3 - 1) * clip(t_m, -LEVER, LEVER);
    real chip = fpar[19];
    if (chip > 0) {
        real a = t_m / (half >= (real)0.2 ? half : (real)0.2);
        real b = z_m / (zh >= (real)0.2 ? zh : (real)0.2);
        for (int c = 0; c < 2; c++) {
            real hc = hb(g, jj, s + 3 + c);
            real st = hb(g, jj, s + 5 + 2 * c) < (real)0.5 ? 1 : -1;
            real sz = hb(g, jj, s + 6 + 2 * c) < (real)0.5 ? 1 : -1;
            real u = st * a + sz * b;
            real on = hc < (c == 0 ? (real)0.6 : (real)0.3) ? 1 : 0;
            real xx = clip((u - (real)0.6) / (real)1.0, 0, 1);
            v = v + on * chip * ((real)0.5 + (real)0.5 * hc) * xx * xx * (3 - 2 * xx);
        }
    }
    return v;
}

/* p world. zoff per point; cuts (nk x 7), nrms (nk x 6 x 3 x 3),
 * n2s (nk x 6 x 3 x 2) for K = Kmin..; out (n x 4): Phi, dPhi, o (before carve), o2 (sharp window) */
KERNEL void k_blocks(const real *p, const real *fd, const real *zoff, i64 n, real S, i64 seed, i64 Kmin, i64 nk,
                     const real *cuts, const real *nrms, const real *n2s, const real *fpar, real sharp, real *out) {
    LOOP(n)
        real x = p[3 * k], y = p[3 * k + 1], z = p[3 * k + 2];
        /* _blocks_bed_coord */
        real und = (real)0.3 * S * (vn(x / (real)10.0, y / (real)10.0, (real)3.5, seed + 2) - (real)0.5) +
                   (real)0.5 * S * (vn(x / (real)28.0, y / (real)28.0, (real)7.5, seed + 3) - (real)0.5);
        und = und + (real)0.3 * (vn(x / (real)3.0, y / (real)3.0, z / (real)3.0, seed + 5) - (real)0.5);
        real ph, dp;
        bwarp(z + zoff[k] + und, S, x / (real)40.0, y / (real)40.0, seed, &ph, &dp);
        /* _blocks_offsets */
        real ramp = fpar[18], sup = fpar[0], thin = fpar[1];
        int has_sharp = sharp > 0;
        real aw_f = (has_sharp && sharp > ramp) ? sharp : ramp;
        i64 sj = seed + 80 + 9;
        real rough[3];
        int have[3] = {0, 0, 0};
        real fd0 = fd[2 * k], fd1 = fd[2 * k + 1];
        i64 K0 = (i64)FLOOR(ph);
        real aw = aw_f * dp;
        real e_ = (real)BSOFT * dp;
        if (!(e_ >= (real)1e-9)) e_ = (real)1e-9;
        real ew = (real)0.9 * aw;
        ew = e_ <= ew ? e_ : ew;
        real a = ramp * dp;
        real ea = (real)BSOFT * dp;
        real ea9 = (real)0.9 * a;
        ea = ea <= ea9 ? ea : ea9;
        real a2 = 0, e2 = 0;
        if (has_sharp) {
            a2 = sharp * dp;
            e2 = ((real)BSOFT <= (real)0.5 * sharp ? (real)BSOFT : (real)0.5 * sharp) * dp;
            real e29 = (real)0.9 * a2;
            e2 = e2 <= e29 ? e2 : e29;
        }
        real acc = 0, acc2 = 0;
        for (int dk = -1; dk < 2; dk++) {
            i64 K = K0 + dk;
            i64 row = K - Kmin;
            if (row < 0 || row >= nk) continue; /* (the host's table covers every K; a guard only) */
            for (int jb = 0; jb < NCUT; jb++) {
                real lo = (real)K + cuts[row * 7 + jb];
                real hi = (real)K + cuts[row * 7 + jb + 1];
                if (!(hi > lo)) continue;
                real ol = bwin(lo, hi, ph, aw, ew);
                if (!(ol > 0)) continue;
                real phw = ph + aw, pmw = ph - aw;
                real oc = (real)0.5 * ((hi <= phw ? hi : phw) + (lo >= pmw ? lo : pmw));
#ifdef REAL_IS_FLOAT
                /* (float32: (K + c1) - (K + c0) cancels ~3e-5 at K ~ 300; the joint spacing comes from th and the joint
                 * coordinate counts spacings from the world origin (~1000 of them), so that moved joints 5 cm) */
                real th = (cuts[row * 7 + jb + 1] - cuts[row * 7 + jb]) * sup;
#else
                real th = (hi - lo) * sup;
#endif
                if (has_sharp && sharp > ramp) {
                    ol = bwin(lo, hi, ph, a, ea);
                    real pha = ph + a, pma = ph - a;
                    oc = (real)0.5 * ((hi <= pha ? hi : pha) + (lo >= pma ? lo : pma));
                }
                real mid = (real)0.5 * (lo + hi);
                real t_m = (oc - mid) / dp;
                real zh = (real)0.5 * (hi - lo) / dp;
                i64 s = seed + 30;
                i64 jb64 = jb;
                real h1 = hb(K, jb64, s), h2 = hb(K, jb64, s + 1);
                real along = clip((real)1.4 * vn(x / (real)9.0, y / (real)9.0, (real)(K * 16 + jb64), s + 2) - (real)0.25,
                                  0, 1);
                real v;
                if (th < thin) v = along * fpar[14];
                else v = along * (-fpar[15] * clip((th - (real)1.2) / (real)2.5, 0, 1));
                v = v + fpar[16] * (2 * h1 - 1) + fpar[17] * (2 * h2 - 1) * clip(t_m, -LEVER, LEVER);
                real J = 0, J2 = 0;
                for (int m = 0; m < 3; m++) {
                    const real *n2 = n2s + ((row * NCUT + jb) * 3 + m) * 2;
                    real fw = bface(n2[0], n2[1], fd0, fd1);
                    real w = fpar[5 + m] * fw * (th >= thin ? (real)1.0 : (real)0.0);
                    if (!(w > 0)) continue;
                    if (!have[m]) {
                        rough[m] = (real)0.4 * (vn(x / (real)3.0, y / (real)3.0, z / (real)3.0, seed + 60 + m + 9) - (real)0.5);
                        have[m] = 1;
                    }
                    real phj, dpj;
                    bjoint_coord(x, y, z, rough[m], K, jb64, m, th, nrms + ((row * NCUT + jb) * 3 + m) * 3, fpar, seed,
                                 &phj, &dpj);
                    real aj = ramp * dpj;
                    i64 jj = (K * 16 + jb64) * 5 + m;
                    i64 i0 = (i64)FLOOR(phj);
                    real ej = (real)BSOFT * dpj;
                    real ej9 = (real)0.9 * aj;
                    ej = ej <= ej9 ? ej : ej9;
                    real aj2 = 0, ej2 = 0;
                    if (has_sharp) {
                        aj2 = sharp * dpj;
                        ej2 = ((real)BSOFT <= (real)0.5 * sharp ? (real)BSOFT : (real)0.5 * sharp) * dpj;
                        real ej29 = (real)0.9 * aj2;
                        ej2 = ej2 <= ej29 ? ej2 : ej29;
                    }
                    real jacc = 0, jacc2 = 0;
                    /* (no per-thread arrays: on the GPU they lived in scratch memory. The windows are recomputed in
                     * the second pass and the boundaries' "absent" hashes roll through three registers; same values,
                     * same order of accumulation) */
                    int first = -1, last = -2;
                    for (int di = -SLOTS; di < SLOTS + 1; di++) {
                        real fi = (real)(i0 + di);
                        real olj = bwin(fi, fi + 1, phj, aj, ej);
                        real olj2 = has_sharp ? bwin(fi, fi + 1, phj, aj2, ej2) : 0;
                        int t = di + SLOTS;
                        if (olj > 0 || (has_sharp && olj2 > 0)) {
                            if (first < 0) first = t;
                            last = t;
                        }
                    }
                    if (first < 0) continue;
                    int lw0 = hb(i0 - SLOTS - 1 + first, jj, sj) < (real)ABSENT;
                    int lw1 = hb(i0 - SLOTS + first, jj, sj) < (real)ABSENT;
                    for (int t = first; t < last + 1; t++) {
                        int lw2 = hb(i0 - SLOTS + 1 + t, jj, sj) < (real)ABSENT;
                        i64 i = i0 + t - SLOTS;
                        real fi = (real)i, fi1 = (real)(i + 1);
                        real olj = bwin(fi, fi1, phj, aj, ej);
                        real olj2 = has_sharp ? bwin(fi, fi1, phj, aj2, ej2) : 0;
                        if (olj > 0 || (has_sharp && olj2 > 0)) {
                            int ab0 = lw1 && !lw0;
                            int ab1 = lw2 && !lw1;
                            real pa = phj + aj, pm = phj - aj;
                            real ocj = (real)0.5 * ((fi1 <= pa ? fi1 : pa) + (fi >= pm ? fi : pm));
                            real mid_ = (real)i + (real)0.5 + (real)0.5 * (ab1 ? (real)1.0 : (real)0.0) -
                                        (real)0.5 * (ab0 ? (real)1.0 : (real)0.0);
                            real tj = (ocj - mid_) / dpj;
                            i64 ext = 1 + ab0 + ab1;
                            real vj = bjoint_value_g(i - ab0, jj, tj, (real)0.5 * (real)ext / dpj, t_m, zh, fpar, seed);
                            jacc += olj * vj;
                            if (has_sharp) jacc2 += olj2 * vj;
                        }
                        lw0 = lw1;
                        lw1 = lw2;
                    }
#ifdef DEBUG
                    if (k == DEBUG) printf("  m %d w %.9g phj %.9g dpj %.9g rough %.9g jacc %.9g first %d last %d\n", m,
                                           (double)w, (double)phj, (double)dpj, (double)rough[m], (double)jacc, first, last);
#endif
                    J += w * jacc;
                    if (has_sharp) J2 += w * jacc2;
                }
#ifdef DEBUG
                if (k == DEBUG) printf("dk %d jb %d lo %.9g hi %.9g ol %.9g v %.9g J %.9g J2 %.9g ph %.9g\n", dk, jb,
                                       (double)lo, (double)hi, (double)ol, (double)v, (double)J, (double)J2, (double)ph);
#endif
                acc += ol * (v + J);
                if (has_sharp) acc2 += bwin(lo, hi, ph, a2, e2) * (v + J2);
            }
        }
        out[4 * k] = ph;
        out[4 * k + 1] = dp;
        out[4 * k + 2] = acc;
        out[4 * k + 3] = has_sharp ? acc2 : 0;
    ENDLOOP
}
