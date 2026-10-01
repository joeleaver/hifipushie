"""What float32 does to the baked maps: a rock field composed from the ported leaves, evaluated in fp64 (bit-identical to
numba) and fp32 on the GPU, then the value error (mm) and the normal error (deg) from the bake's own stencils (the
tetrahedral gradient at h = v/16 = 0.031 m for the Newton/normal pass, 0.4 m for the layer/colour normal).

    uv run python spikes/gpu_bake/normals.py [alps] [n]

F = ((z - h) s) + steep * (A (1.1 f(1.5 size) + 0.4 f(0.45 size)) + 0.06 f(1.2) + blocks_sharp): the shape of
Field._solid's rock (rock_relief + micro_relief + the maps' sharp structure), not its exact weights.
fp32 variants: "world" (z - h in float32 at ~1.5 km) and "local" (z and H shifted by a tile origin z0 in double first)."""
from __future__ import annotations

import sys

import numpy as np

import bench as b
from bench import H

TET = np.array([[1, 1, 1], [1, -1, -1], [-1, 1, -1], [-1, -1, 1]], float)


def compose(rn, W, P, w_of, pools, sizes, z0=0.0):
    dt = np.float64 if rn.real == "double" else np.float32
    col, _ = b.k_column(rn, W, P, z0)
    h, s, st, gr = col[:, 0], col[:, 1], col[:, 2], col[:, 3]
    fd = np.ascontiguousarray(col[:, 4:6], dtype=float)  # (the face direction as this precision computed it)
    zoff = np.ascontiguousarray(W.d["zoff_fn"](P))
    blk, _ = b.k_blocks(rn, W, P, fd, zoff)
    w = w_of(fd)
    fac = [b.k_facets(rn, W, P, w, pools[s_], s_, int(W.rock["seed"]), fixup_fd=fd)[0][0] for s_ in sizes]
    A = dt(W.rock["facets"])
    z = P[:, 2].astype(dt) - dt(z0)
    hh = h.astype(dt)  # (already relative to z0)
    F = (z - hh) * s.astype(dt) + st.astype(dt) * (A * (dt(1.1) * fac[0] + dt(0.4) * fac[1]) + dt(0.06) * fac[2]
                                                   + blk[:, 3].astype(dt))
    return F.astype(float)


def grad(rn, W, X, hstep, w_of, pools, sizes, z0=0.0):
    Q = (X[:, None, :] + hstep * TET[None]).reshape(-1, 3)
    f = compose(rn, W, Q, w_of, pools, sizes, z0).reshape(-1, 4)
    return f.mean(1), (f @ TET) / (4 * hstep)


def ang(a, b_):
    a = a / np.linalg.norm(a, axis=1, keepdims=True)
    b_ = b_ / np.linalg.norm(b_, axis=1, keepdims=True)
    return np.degrees(np.arccos(np.clip((a * b_).sum(1), -1, 1)))


def main(name="alps", n=60_000):
    W = b.Work(name)
    X = W.P[:n]
    # zoff (the big beds' wander, smooth over tens of metres): its mean (the dump has it at the points only)
    zm = float(W.d["zoff"].mean())
    W.d["zoff_fn"] = lambda P: np.full(len(P), zm)
    r = W.rock
    sizes = [1.5 * r["size"], 0.45 * r["size"], 1.2]
    span = np.r_[X - 0.45, X + 0.45]
    fd_all = np.r_[W.d["fd"][:n], W.d["fd"][:n]]
    pools = {s: b.FacetPool(span, b.facet_weights(fd_all) * 0 + 1, s, int(r["seed"])) for s in sizes}  # (all 3 axes)
    hip = H.Hip()
    g64 = b.Runner("double", "gpu", hip)
    g32 = b.Runner("float", "gpu", hip)
    z0 = float(np.floor(X[:, 2].mean()))
    print(f"{n} points, tile origin z0 = {z0} m")
    ref_v = compose(g64, W, X, b.facet_weights, pools, sizes)
    for label, rn, zz in (("fp32 world", g32, 0.0), ("fp32 local", g32, z0)):
        v = compose(rn, W, X, b.facet_weights, pools, sizes, zz)
        e = np.abs(v - ref_v) * 1000
        print(f"{label}: value error mm p50 {np.percentile(e, 50):.3f} p99 {np.percentile(e, 99):.3f} max {e.max():.3f}")
        for hstep in (0.5 / 16, 0.4):
            _, ga = grad(g64, W, X, hstep, b.facet_weights, pools, sizes)
            _, gb = grad(rn, W, X, hstep, b.facet_weights, pools, sizes, zz)
            d = ang(ga, gb)
            # the normal map's bytes (world normal as a stand-in for the tangent-space one: same quantisation)
            q = lambda g: np.round((g / np.linalg.norm(g, axis=1, keepdims=True) * 0.5 + 0.5) * 255)
            bytes_ = (q(ga) != q(gb)).any(1).mean() * 100
            print(f"   normal (h = {hstep:.3f} m): deg p50 {np.percentile(d, 50):.4f} p99 {np.percentile(d, 99):.4f} "
                  f"max {d.max():.3f}; 8-bit normal texels differing {bytes_:.2f}%")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "alps", int(sys.argv[2]) if len(sys.argv) > 2 else 60_000)
