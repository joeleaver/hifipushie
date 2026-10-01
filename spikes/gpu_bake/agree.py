"""Agreement of the C kernels (GPU fp64, CPU fp64, GPU fp32) with numba on the dumped workload.

    uv run python spikes/gpu_bake/agree.py [alps] [n]"""
from __future__ import annotations

import sys

import numpy as np

import bench as b
from bench import H


def main(name="alps", n=None):
    W = b.Work(name)
    P = W.P if n is None else W.P[:n]
    d = W.d
    fd = np.ascontiguousarray(d["fd"][:len(P)])
    zoff = np.ascontiguousarray(d["zoff"][:len(P)])
    hip = H.Hip()
    print("device memory free/total GB", [round(x / 2**30, 1) for x in hip.mem_info()])
    runners = {"gpu64": b.Runner("double", "gpu", hip), "cpu64": b.Runner("double", "cpu"),
               "gpu32": b.Runner("float", "gpu", hip)}
    ref_col, _ = b.numba_column(W, P, None)
    ref_fbm, _ = b.numba_fbm(P)
    ref_blk, _ = b.numba_blocks(W, P, fd, zoff)
    w = b.facet_weights(fd)
    r = W.rock
    sizes = [1.5 * r["size"], 0.45 * r["size"], 1.2]
    ref_fac = {}
    pools = {}
    for s in sizes:
        b.numba_facets(P, s, int(r["seed"]), fd)  # (warm the triangulations)
        ref_fac[s], _ = b.numba_facets(P, s, int(r["seed"]), fd)
        pools[s] = b.FacetPool(P, w, s, int(r["seed"]))
        print(f"facets {s:.2f} m: {len(pools[s].keys)} triangulations, {pools[s].nbytes / 2**20:.1f} MB")
    for k, rn in runners.items():
        col, _ = b.k_column(rn, W, P)
        print(f"{k} column+grids", b.diff(col, ref_col))
        fb, _ = b.k_fbm(rn, W, P)
        print(f"{k} fbm         ", b.diff(fb, ref_fbm))
        blk, _ = b.k_blocks(rn, W, P, fd, zoff)
        print(f"{k} blocks      ", b.diff(blk, ref_blk), " (Phi, dPhi, o, o2) max per column",
              [f"{x:.2g}" for x in np.abs(blk - ref_blk).max(0)])
        for s in sizes:
            (v, amb), _ = b.k_facets(rn, W, P, w, pools[s], s, int(r["seed"]))
            ok = amb == 0
            print(f"{k} facets {s:4.2f}  ambiguous {int((~ok).sum())} of {len(P)};", b.diff(v[ok], ref_fac[s][ok]))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "alps", int(sys.argv[2]) if len(sys.argv) > 2 else None)
