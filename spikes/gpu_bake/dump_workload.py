"""Build the alps bake field once, profile the CPU (numba) field on bake-like points, and dump what the GPU prototype
needs: the grids, the points, the rock settings, and CPU reference values of each leaf.

Run (under the heavy lock): uv run python spikes/gpu_bake/dump_workload.py [alps|pebble] [n]
Writes spikes/gpu_bake/work_<name>.npz + .pkl (rock config)."""
from __future__ import annotations

import pickle
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "tests"))

from hifipushie import fieldjit, profiling, resources, terrain_blocks as tb, terrain_facets as tf  # noqa: E402
import test_fieldjit as tfj  # noqa: E402


def texel_points(base, n, density=8.0, seed=0):
    """Bake-like points: a square patch of the steepest ground at `density` texels/m in plan (n of them), each near
    the surface (z = the column's height + N(0, 0.15 m): Newton iterates), Morton ordered like a bake piece."""
    from scipy import ndimage
    from hifipushie import terrain_mesh as tm
    rng = np.random.default_rng(seed)
    k = np.unravel_index(np.argmax(ndimage.uniform_filter(base.steep, 9)), base.steep.shape)
    cx, cy = base.x0 + k[1] * base.c, base.y0 + k[0] * base.c
    side = np.sqrt(n) / density
    g = (np.arange(int(np.sqrt(n))) + 0.5) / density - side / 2
    X, Y = np.meshgrid(cx + g, cy + g)
    xy = np.c_[X.ravel(), Y.ravel()] + rng.normal(0, 0.02, (X.size, 2))
    h, _ = base.column(xy[:, 0], xy[:, 1])
    P = np.c_[xy, h + rng.normal(0, 0.15, len(xy))]
    return P[tm._morton(P, 0.5)]


def main(name="alps", n=60_000):
    with resources.heavy(f"gpu_bake dump {name}"):
        t = time.perf_counter()
        T, base, front, mats = tfj._fields(name)
        print(f"fields built {time.perf_counter() - t:.1f} s")
        P = texel_points(base, n)
        print("points", len(P))
        fieldjit.warm()
        front.value(P[:2000])  # (warm the triangulation cache a little, as a worker would be mid-bake)
        profiling.reset()
        t = time.perf_counter()
        for i in range(0, len(P), 25_000):
            front.value(P[i:i + 25_000])
        dt = time.perf_counter() - t
        print(f"front.value: {len(P)} pts in {dt:.2f} s = {dt / len(P) * 1e6:.2f} us/pt (1 process, numba)")
        snap = profiling.snapshot()
        for k, (s, c) in sorted(snap["spans"].items(), key=lambda kv: -kv[1][0]):
            print(f"  {k:40s} {s:8.2f} s {c:6d} calls  {s / dt * 100:5.1f}%")
        for k, c in sorted(snap["counts"].items(), key=lambda kv: -kv[1])[:12]:
            print(f"  {k:50s} {c:12,d}")
        # leaves at the points, for the GPU kernels to match
        x, y = P[:, 0].copy(), P[:, 1].copy()
        h, s = base.column(x, y)
        st = base.steep_at(x, y)
        gr = base.grain_at(x, y)
        fd = base.face_dir(x, y)
        r = base.rock
        B = r["blocks"]
        zoff = r["bed_offset"](P[:, :2]) if r.get("bed_offset") else np.zeros(len(P))
        zoff = np.broadcast_to(np.asarray(zoff, float), (len(P),)).copy()
        Phi, dPhi, mast = tb._pre(P, B, fd, zoff)
        sharp = 0.25
        o, o2 = fieldjit.blocks_offsets(P, B, fd, Phi, dPhi, sharp, tb._cuts, tb._joint_frame, tb.NCUT)
        fac = {}
        for size in (1.5 * r["size"], 0.45 * r["size"], 1.2):
            fac[size] = tf.facets(P, size, int(r["seed"]), fd)
        from hifipushie import noise
        fb = noise.fbm(P, 1.3, 3, seed=91)
        np.savez(HERE / f"work_{name}.npz", P=P, H=base.H, steep=base.steep, grain=base.grain, fdx=base._fdx,
                 fdy=base._fdy, x0=base.x0, y0=base.y0, c=base.c, h=h, s=s, st=st, gr=gr, fd=fd, zoff=zoff, Phi=Phi,
                 dPhi=dPhi, o=o, o2=o2, fbm=fb, fac_sizes=np.array(list(fac)), fac=np.stack(list(fac.values())),
                 front=np.concatenate([front.value(P[i:i + 25_000]) for i in range(0, len(P), 25_000)]),
                 us_per_pt=dt / len(P) * 1e6)
        keep = {k: v for k, v in r.items() if not callable(v)}
        with open(HERE / f"work_{name}.pkl", "wb") as f:
            pickle.dump({"rock": keep, "B": B}, f)
        print("dumped")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "alps", int(sys.argv[2]) if len(sys.argv) > 2 else 60_000)
