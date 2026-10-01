"""GPU (HIP on the 890M) vs the compiled CPU field (numba) on a bake-like workload dumped by dump_workload.py.

    uv run python spikes/gpu_bake/bench.py [alps] [--reps N] [--big M]

Per kernel (column+grids, fbm, facets x3 sizes, blocks): agreement with numba (fp64: bit-identical?; fp32: error), and
throughput: numba 1 thread, the C kernels on 1 CPU thread (same source as the GPU), GPU fp64, GPU fp32. Points are the
dump's texel-like points, tiled to --big points (shifted copies along the face) for the throughput runs."""
from __future__ import annotations

import ctypes
import math
import pickle
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import hip as H  # noqa: E402
from hifipushie import fieldjit, noise, terrain_blocks as tb, terrain_facets as tf  # noqa: E402

c_i64, c_f64, c_f32 = ctypes.c_long, ctypes.c_double, ctypes.c_float


def R(real):
    return (np.float64, c_f64) if real == "double" else (np.float32, c_f32)


# ------------------------------------------------------------------ inputs per kernel

class Work:
    def __init__(self, name="alps"):
        self.d = dict(np.load(HERE / f"work_{name}.npz"))
        with open(HERE / f"work_{name}.pkl", "rb") as f:
            m = pickle.load(f)
        self.rock, self.B = m["rock"], m["B"]
        self.P = self.d["P"]
        self.n = len(self.P)


def facet_weights(fd):
    """As terrain_facets.facets -> fieldjit.facets does it: |(fd, 1)|^4 (numpy's power), normalised, 3% off."""
    w = np.abs(np.c_[fd, np.ones(len(fd))]) ** 4
    w = np.ascontiguousarray(w)
    fieldjit._norm_weights(w, 0.03)
    return w


class FacetPool:
    """Every triangulation the points need for one facet size (all three projections), packed for the GPU."""

    def __init__(self, P, w, size, seed, stretch=1.4, group=tf.GROUP):
        t = time.perf_counter()
        keys = []
        for ax, (u, v, st) in enumerate(((1, 2, stretch), (0, 2, stretch), (0, 1, 1.0))):
            k = w[:, ax] > 0
            g = np.floor(np.c_[P[k, u] / size, P[k, v] / st / size] / group).astype(np.int64)
            for gi, gj in np.unique(g, axis=0):
                keys.append((seed + 500 * ax, int(gi), int(gj)))
        self.keys = keys
        tris = []
        for sa, gi, gj in keys:
            tri, val = tf._triangulation(sa, gi, gj)
            grid, g0, g1, nx, ny = fieldjit._grid_of(tri)
            tris.append((tri, val, grid, g0, g1, nx, ny))
        self.t_triangulate = time.perf_counter() - t
        nt = [len(x[0].simplices) for x in tris]
        self.tri_off = np.r_[0, np.cumsum(nt)[:-1]].astype(np.int64)
        self.val_off = np.r_[0, np.cumsum([len(x[1]) for x in tris])[:-1]].astype(np.int64)
        self.grd_off = np.r_[0, np.cumsum([len(x[2]) for x in tris])[:-1]].astype(np.int64)
        self.TR = np.concatenate([x[0].transform.reshape(-1, 6) for x in tris])
        self.NB = np.concatenate([x[0].neighbors for x in tris]).astype(np.int32)
        self.SI = np.concatenate([x[0].simplices for x in tris]).astype(np.int32)
        self.VAL = np.concatenate([x[1] for x in tris])
        self.GRD = np.concatenate([x[2] for x in tris]).astype(np.int32)
        self.bpar = np.array([[x[3], x[4], x[5], x[6]] for x in tris], float)
        size_ht = 1 << max(4, int(math.ceil(math.log2(4 * len(keys)))))
        HT = np.full((size_ht, 4), -1, np.int64)
        mask = size_ht - 1
        for b, (sa, gi, gj) in enumerate(keys):
            h = (np.uint64(sa) * np.uint64(0x9E3779B97F4A7C15)) ^ (np.uint64(gi & (2**64 - 1)) *
                                                                   np.uint64(0xC2B2AE3D27D4EB4F)) ^ \
                (np.uint64(gj & (2**64 - 1)) * np.uint64(0x165667B19E3779F9))
            h ^= h >> np.uint64(29)
            s = int(h & np.uint64(mask))
            while HT[s, 3] >= 0:
                s = (s + 1) & mask
            HT[s] = (sa, gi, gj, b)
        self.HT, self.mask = HT, mask
        self.nbytes = sum(a.nbytes for a in (self.TR, self.NB, self.SI, self.VAL, self.GRD, self.HT))


# ------------------------------------------------------------------ runners

class Runner:
    """Runs a kernel on the GPU (Hip) or the CPU build of the same source, with uploads kept apart from the timing."""

    def __init__(self, real, target, hip=None):
        self.real, self.target = real, target
        self.dt, self.ct = R(real)
        self.path = H.build(real, target)
        self.hip = hip
        self.cpu = H.Cpu(self.path) if target == "cpu" else None

    def arr(self, a, dtype=None):
        a = np.ascontiguousarray(a, dtype or self.dt)
        return self.hip.to_device(a) if self.target == "gpu" else a

    def out(self, shape, dtype=None):
        dtype = dtype or self.dt
        if self.target == "gpu":
            return (self.hip.empty(int(np.prod(shape)) * np.dtype(dtype).itemsize), dtype, shape)
        return np.empty(shape, dtype)

    def get(self, o):
        if self.target == "gpu":
            b, dtype, shape = o
            return self.hip.from_device(b, dtype, shape)
        return o

    def run(self, name, n, args):
        a = [x[0] if isinstance(x, tuple) else x for x in args]
        t = time.perf_counter()
        if self.target == "gpu":
            self.hip.launch(self.hip.function(self.path, name), n, a)
            self.hip.sync()
        else:
            self.cpu.call(name, a)
        return time.perf_counter() - t

    def free(self, *bufs):
        if self.target == "gpu":
            for b in bufs:
                (b[0] if isinstance(b, tuple) else b).free()


def k_column(rn: Runner, W: Work, P, z0=0.0):
    """z0: heights come back relative to z0 (the grid shifted in double before a float32 upload)."""
    d = W.d
    n0, n1 = d["H"].shape
    if rn.real == "float":
        x, y, x0, y0 = P[:, 0] - d["x0"], P[:, 1] - d["y0"], 0.0, 0.0
    else:
        x, y, x0, y0 = P[:, 0], P[:, 1], float(d["x0"]), float(d["y0"])
    grids = [rn.arr(d[k] - z0 if k == "H" else d[k]) for k in ("H", "steep", "grain", "fdx", "fdy")]
    X, Y = rn.arr(x), rn.arr(y)
    out = rn.out((len(P), 6))
    dt = rn.run("k_column", len(P), [*grids, c_i64(n0), c_i64(n1), rn.ct(x0), rn.ct(y0), rn.ct(float(d["c"])), X, Y,
                                     c_i64(len(P)), out])
    res = rn.get(out)
    rn.free(*grids, X, Y, out)
    return res, dt


def k_fbm(rn: Runner, W: Work, P):
    rot = rn.arr(np.stack(noise._ROT))
    p = rn.arr(P)
    out = rn.out((len(P),))
    dt = rn.run("k_fbm", len(P), [p, c_i64(len(P)), rn.ct(1.3), c_i64(3), c_i64(91), rot, out])
    res = rn.get(out)
    rn.free(rot, p, out)
    return res, dt


def k_facets(rn: Runner, W: Work, P, w, pool: FacetPool, size, seed, fixup_fd=None):
    args = [rn.arr(P), rn.arr(w), c_i64(len(P)), rn.ct(size), rn.ct(1.4), rn.ct(tf.GROUP), c_i64(seed),
            rn.arr(pool.HT, np.int64), c_i64(pool.mask), rn.arr(pool.tri_off, np.int64),
            rn.arr(pool.val_off, np.int64), rn.arr(pool.grd_off, np.int64), rn.arr(pool.bpar), rn.arr(pool.TR),
            rn.arr(pool.NB, np.int32), rn.arr(pool.SI, np.int32), rn.arr(pool.VAL), rn.arr(pool.GRD, np.int32),
            rn.ct(tf.GAIN)]
    out, amb, simp = rn.out((len(P),)), rn.out((len(P),), np.int32), rn.out((len(P), 3), np.int32)
    dt = rn.run("k_facets", len(P), args + [out, amb, simp])
    res = (rn.get(out), rn.get(amb))
    if fixup_fd is not None and (res[1] != 0).any():  # (within 1e-9 of an edge: scipy's walk, on the CPU)
        k = np.flatnonzero(res[1] != 0)
        res[0][k] = tf.facets(P[k], size, seed, fixup_fd[k])
    rn.free(*[a for a in args if not isinstance(a, (ctypes.c_long, ctypes.c_double, ctypes.c_float))], out, amb, simp)
    return res, dt


def block_tables(W: Work, P, zoff):
    """Kmin + the cuts/frames tables over every super-bed the points can reach (bounded from z: the warp moves Phi at
    most ~1.1 beds, the undulation +-0.4 S + 0.15 m)."""
    B = W.B
    S = B["super"]
    lo = (P[:, 2] + zoff).min() - 0.4 * S - 0.15
    hi = (P[:, 2] + zoff).max() + 0.4 * S + 0.15
    Phi = np.array([lo / S - 2.0, hi / S + 2.0])
    return fieldjit._blocks_tables(Phi, B, tb._cuts, tb._joint_frame, tb.NCUT)


def k_blocks(rn: Runner, W: Work, P, fd, zoff, sharp=0.25):
    B = W.B
    Kmin, cuts, nrms, n2s = block_tables(W, P, zoff)
    args = [rn.arr(P), rn.arr(fd), rn.arr(zoff), c_i64(len(P)), rn.ct(B["super"]), c_i64(int(B["seed"])), c_i64(Kmin),
            c_i64(len(cuts)), rn.arr(cuts), rn.arr(nrms), rn.arr(n2s), rn.arr(fieldjit._blocks_fpar(B)), rn.ct(sharp)]
    out = rn.out((len(P), 4))
    dt = rn.run("k_blocks", len(P), args + [out])
    res = rn.get(out)
    rn.free(*[a for a in args if not isinstance(a, (ctypes.c_long, ctypes.c_double, ctypes.c_float))], out)
    return res, dt


# ------------------------------------------------------------------ numba references (timed, 1 thread)

def numba_column(W, P, base_like):
    x, y = np.ascontiguousarray(P[:, 0]), np.ascontiguousarray(P[:, 1])
    d = W.d
    t = time.perf_counter()
    h, s = fieldjit.column(d["H"], x, y, float(d["x0"]), float(d["y0"]), float(d["c"]))
    st = fieldjit.grid_at(d["steep"], x, y, float(d["x0"]), float(d["y0"]), float(d["c"]))
    gr = fieldjit.grid_at(d["grain"], x, y, float(d["x0"]), float(d["y0"]), float(d["c"]))
    fx = fieldjit.grid_at(d["fdx"], x, y, float(d["x0"]), float(d["y0"]), float(d["c"]))
    fy = fieldjit.grid_at(d["fdy"], x, y, float(d["x0"]), float(d["y0"]), float(d["c"]))
    return np.c_[h, s, st, gr, fx, fy], time.perf_counter() - t


def numba_fbm(P):
    t = time.perf_counter()
    v = noise.fbm(P, 1.3, 3, seed=91)
    return v, time.perf_counter() - t


def numba_facets(P, size, seed, fd):
    t = time.perf_counter()
    v = tf.facets(P, size, seed, fd)
    return v, time.perf_counter() - t


def numba_blocks(W, P, fd, zoff, sharp=0.25):
    B = W.B
    t = time.perf_counter()
    Phi, dPhi = fieldjit._blocks_bed_coord(np.ascontiguousarray(P), np.ascontiguousarray(zoff), float(B["super"]),
                                           int(B["seed"]))
    o, o2 = fieldjit.blocks_offsets(P, B, fd, Phi, dPhi, sharp, tb._cuts, tb._joint_frame, tb.NCUT)
    return np.c_[Phi, dPhi, o, o2], time.perf_counter() - t


def diff(a, b):
    a, b = np.asarray(a, float), np.asarray(b, float)
    ok = np.isfinite(a) & np.isfinite(b)
    d = np.abs(a - b)[ok]
    return {"differ": int((a != b).sum()), "of": int(a.size), "max": float(d.max()) if len(d) else 0.0,
            "p99": float(np.percentile(d, 99)) if len(d) else 0.0}
