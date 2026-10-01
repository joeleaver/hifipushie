"""Two things a tiled bake needs from the GPU besides speed.

1. Determinism per point: the same point gives the same bits whatever batch it is in (order, batch size, neighbours),
   fp64 and fp32: tile borders are baked by different jobs.
2. Memory accounting on the shared-RAM iGPU: does a hipMalloc show up where resources.py looks (process PSS, MemAvailable)?

    uv run python spikes/gpu_bake/determinism.py"""
from __future__ import annotations

import os
import time

import numpy as np

import bench as b
from bench import H
from hifipushie import resources


def main():
    W = b.Work("alps")
    n = 50_000
    P, fd, zoff = W.P[:n], np.ascontiguousarray(W.d["fd"][:n]), np.ascontiguousarray(W.d["zoff"][:n])
    hip = H.Hip()
    rng = np.random.default_rng(1)
    for real in ("double", "float"):
        rn = b.Runner(real, "gpu", hip)
        a, _ = b.k_blocks(rn, W, P, fd, zoff)
        o = rng.permutation(n)
        c, _ = b.k_blocks(rn, W, P[o], fd[o], zoff[o])
        parts = [b.k_blocks(rn, W, P[i:i + 777], fd[i:i + 777], zoff[i:i + 777])[0] for i in range(0, 7770, 777)]
        same_perm = np.array_equal(a[o], c)
        same_small = np.array_equal(a[:7770], np.concatenate(parts))
        print(f"{real}: shuffled batch identical {same_perm}, 777-point batches identical {same_small}")
    # memory: 2 GB on the device
    def drm(k):
        try:
            return int(open(f"/sys/class/drm/card1/device/mem_info_{k}_used").read()) / 2**30
        except OSError:
            return float("nan")
    g0, v0 = drm("gtt"), drm("vram")
    pid = os.getpid()
    m0, p0 = resources.meminfo()["available"], resources._pss_gb(pid)
    f0 = hip.mem_info()[0]
    buf = hip.empty(2 << 30)
    big = np.ones((2 << 30) // 8)
    hip.ck(hip.h.hipMemcpy(buf.ptr, big.ctypes.data, big.nbytes, 1), "H2D")
    del big
    time.sleep(1.0)
    m1, p1 = resources.meminfo()["available"], resources._pss_gb(pid)
    f1 = hip.mem_info()[0]
    print(f"amdgpu counters: GTT used {g0:.2f} -> {drm('gtt'):.2f} GB, VRAM (2 GB carve-out) used {v0:.2f} -> "
          f"{drm('vram'):.2f} GB")
    print(f"after a 2 GB hipMalloc (filled): MemAvailable {m0:.2f} -> {m1:.2f} GB, process PSS {p0:.2f} -> {p1:.2f} GB, "
          f"HIP free {f0 / 2**30:.1f} -> {f1 / 2**30:.1f} GB")
    buf.free()
    time.sleep(0.5)
    print(f"freed: MemAvailable {resources.meminfo()['available']:.2f} GB, PSS {resources._pss_gb(pid):.2f} GB")


if __name__ == "__main__":
    main()
