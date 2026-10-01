"""Points/s per kernel: numba (1 process, and a fork pool), the same C on 1 CPU thread, GPU fp64, GPU fp32.

    uv run python spikes/gpu_bake/throughput.py [alps] [reps] [workers]

reps: the dumped points repeated (250k x reps per call). Runs under resources.heavy (it saturates the CPU)."""
from __future__ import annotations

import multiprocessing as mp
import sys
import time

import numpy as np

import bench as b
from bench import H
from hifipushie import fieldjit, resources

G = {}


def _numba_job(args):
    name, lo, hi = args
    W, P, fd, zoff, w = G["W"], G["P"], G["fd"], G["zoff"], G["w"]
    sl = slice(lo, hi)
    t = time.perf_counter()
    if name == "column":
        b.numba_column(W, P[sl], None)
    elif name == "fbm":
        b.numba_fbm(P[sl])
    elif name == "blocks":
        b.numba_blocks(W, P[sl], fd[sl], zoff[sl])
    else:
        b.numba_facets(P[sl], float(name), int(W.rock["seed"]), fd[sl])
    return time.perf_counter() - t


def main(name="alps", reps=4, workers=12):
    W = b.Work(name)
    P = np.ascontiguousarray(np.tile(W.P, (reps, 1)))
    fd = np.ascontiguousarray(np.tile(W.d["fd"], (reps, 1)))
    zoff = np.ascontiguousarray(np.tile(W.d["zoff"], reps))
    n = len(P)
    w = b.facet_weights(fd)
    r = W.rock
    sizes = [1.5 * r["size"], 0.45 * r["size"], 1.2]
    G.update(W=W, P=P, fd=fd, zoff=zoff, w=w)
    fieldjit.warm()
    pools = {s: b.FacetPool(W.P, w[:W.n], s, int(r["seed"])) for s in sizes}
    for s in sizes:  # (warm every worker's triangulation cache through the fork)
        b.numba_facets(W.P, s, int(r["seed"]), W.d["fd"])
    hip = H.Hip()
    rows = []
    kernels = ["column", "fbm", "blocks"] + [f"{s:g}" for s in sizes]
    with resources.heavy("gpu_bake throughput"):
        for kname in kernels:
            row = {"kernel": kname, "n": n}
            # numba, 1 process
            row["numba1"] = n / _numba_job((kname, 0, n))
            # the C source on 1 CPU thread
            rc = b.Runner("double", "cpu")
            row["c_cpu1"] = n / run(rc, kname, W, P, fd, zoff, w, pools)
            # GPU, twice (the first warms the code object), best of 2
            for real in ("double", "float"):
                rn = b.Runner(real, "gpu", hip)
                run(rn, kname, W, P[:1000], fd[:1000], zoff[:1000], w[:1000], pools)
                ts = [run(rn, kname, W, P, fd, zoff, w, pools) for _ in range(2)]
                row["gpu64" if real == "double" else "gpu32"] = n / min(ts)
            rows.append(row)
            print({k: (f"{v / 1e6:.2f}M" if isinstance(v, float) else v) for k, v in row.items()}, flush=True)
        # numba fork pool (the export's model: forked workers, one BLAS thread each)
        nw = resources.workers(0.6, cap=workers)
        ctx = mp.get_context("fork")
        with ctx.Pool(nw, initializer=resources._worker_init) as pool:
            for row in rows:
                chunk = 25_000
                jobs = [(row["kernel"], i, min(i + chunk, n)) for i in range(0, n, chunk)]
                pool.map(_numba_job, jobs[:nw])  # (warm)
                t = time.perf_counter()
                pool.map(_numba_job, jobs)
                row["numba_pool"] = n / (time.perf_counter() - t)
                row["pool_workers"] = nw
        print("\npoints/s (M):  kernel        numba x1  numba pool   C x1   GPU fp64  GPU fp32   GPU64/pool")
        for row in rows:
            print(f"  {row['kernel']:14s} {row['numba1'] / 1e6:9.2f} {row['numba_pool'] / 1e6:10.2f} "
                  f"{row['c_cpu1'] / 1e6:7.2f} {row['gpu64'] / 1e6:9.2f} {row['gpu32'] / 1e6:9.2f} "
                  f"{row['gpu64'] / row['numba_pool']:10.2f}")
        print(f"(pool: {rows[0]['pool_workers']} workers)")


def run(rn, kname, W, P, fd, zoff, w, pools):
    """Kernel time only (uploads/downloads excluded: timed separately in transfer())."""
    if kname == "column":
        return b.k_column(rn, W, P)[1]
    if kname == "fbm":
        return b.k_fbm(rn, W, P)[1]
    if kname == "blocks":
        return b.k_blocks(rn, W, P, fd, zoff)[1]
    s = [k for k in pools if f"{k:g}" == kname][0]
    return b.k_facets(rn, W, P, w, pools[s], s, int(W.rock["seed"]))[1]


if __name__ == "__main__":
    a = sys.argv[1:]
    main(a[0] if a else "alps", int(a[1]) if len(a) > 1 else 4, int(a[2]) if len(a) > 2 else 12)
