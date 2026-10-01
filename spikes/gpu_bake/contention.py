"""The APU shares power, clocks and memory bandwidth between the CPU cores and the GPU: does the GPU's rate hold up while
the CPU pool is busy (as it would be: decimation, unwrap, the rest of the bake), and what does the pool lose?

    uv run python spikes/gpu_bake/contention.py [seconds] [workers]

Blocks kernel (the field's heaviest leaf): GPU fp32 / fp64 in a loop, the numba fork pool in a loop, alone and together."""
from __future__ import annotations

import multiprocessing as mp
import sys
import threading
import time

import numpy as np

import bench as b
from bench import H
from hifipushie import fieldjit, resources

G = {}


def _job(args):
    lo, hi = args
    W, P, fd, zoff = G["W"], G["P"], G["fd"], G["zoff"]
    b.numba_blocks(W, P[lo:hi], fd[lo:hi], zoff[lo:hi])
    return hi - lo


def gpu_loop(rn, W, P, fd, zoff, secs, out):
    n = 0
    t = time.perf_counter()
    while time.perf_counter() - t < secs:
        b.k_blocks(rn, W, P, fd, zoff)
        n += len(P)
    out.append(n / (time.perf_counter() - t))


def pool_loop(pool, n, secs, out):
    jobs = [(i, min(i + 25_000, n)) for i in range(0, n, 25_000)]
    done = 0
    t = time.perf_counter()
    while time.perf_counter() - t < secs:
        done += sum(pool.map(_job, jobs))
    out.append(done / (time.perf_counter() - t))


def main(secs=12.0, workers=12):
    W = b.Work("alps")
    P, fd, zoff = W.P, np.ascontiguousarray(W.d["fd"]), np.ascontiguousarray(W.d["zoff"])
    G.update(W=W, P=P, fd=fd, zoff=zoff)
    fieldjit.warm()
    hip = H.Hip()
    with resources.heavy("gpu_bake contention"):
        nw = resources.workers(0.6, cap=workers)
        with mp.get_context("fork").Pool(nw, initializer=resources._worker_init) as pool:
            pool.map(_job, [(0, 25_000)] * nw)
            for real in ("float", "double"):
                rn = b.Runner(real, "gpu", hip)
                g = []
                gpu_loop(rn, W, P, fd, zoff, secs, g)
                c = []
                pool_loop(pool, len(P), secs, c)
                gb, cb = [], []
                th = threading.Thread(target=gpu_loop, args=(rn, W, P, fd, zoff, secs, gb))
                th.start()
                pool_loop(pool, len(P), secs, cb)
                th.join()
                print(f"blocks, GPU {real}: GPU alone {g[0] / 1e6:.1f} M/s, pool ({nw}) alone {c[0] / 1e6:.1f} M/s; "
                      f"together GPU {gb[0] / 1e6:.1f} + pool {cb[0] / 1e6:.1f} = {(gb[0] + cb[0]) / 1e6:.1f} M/s",
                      flush=True)


if __name__ == "__main__":
    a = sys.argv[1:]
    main(float(a[0]) if a else 12.0, int(a[1]) if len(a) > 1 else 12)
