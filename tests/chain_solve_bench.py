"""A garment-sized network for chain_solve's speed (N1b): a torso of two sewn panels and two sleeves of two sewn panels
each, round a body of three cylinders (torso and two arms), seeded loose (each panel flat a little off the body). Scale
sets the point count: scale 1 is ~24k points, 0.5 ~6k, 0.25 ~1.5k.

    uv run python tests/chain_solve_bench.py [scale] [--profile]
"""
import cProfile
import pstats
import sys
import time

import numpy as np

sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))
from test_chain_solve import cylinder, grid, pattern  # noqa: E402

from hifipushie import chain_solve as cs  # noqa: E402
from hifipushie.chain_net import Contact, Network  # noqa: E402

RT, HT = 0.15, 0.6  # torso radius, height
RA, HA, XA = 0.05, 0.5, 0.32  # arm radius, height, offset


def body():
    parts = [cylinder(RT, -0.05, HT + 0.05, seg=96, rings=24)]
    for sx in (-1, 1):
        c = cylinder(RA, -0.05, HA + 0.05, seg=48, rings=20)
        parts.append(Contact(c.V + [sx * XA, 0, 0.05], c.T))
    V, T, n = [], [], 0
    for p in parts:
        V.append(p.V)
        T.append(p.T + n)
        n += len(p.V)
    return Contact(np.concatenate(V), np.concatenate(T))


def garment(scale=1.0):
    """(net, X0, body): two tubes' worth of panels per limb; the sides sewn."""
    pieces, sew, seeds = [], [], []
    n = 0

    def tube(name, r, h, cx, z0, nx, ny):
        nonlocal n
        W = 1.15 * np.pi * r
        uv, F = grid(nx, ny, W, h)
        col0, col1 = np.arange(ny), (nx - 1) * ny + np.arange(ny)
        k = len(uv)
        pieces.extend([(name + " front", uv, F), (name + " back", uv.copy(), F)])
        sew.extend([np.c_[col0 + n, col0 + n + k], np.c_[col1 + n, col1 + n + k]])
        for sy in (-1, 1):
            seeds.append(np.c_[cx + uv[:, 0] - W / 2, np.full(k, sy * (r + 0.01)), z0 + uv[:, 1]])
        n += 2 * k

    s = np.sqrt(scale)
    tube("torso", RT, HT, 0.0, 0.0, int(round(81 * s)), int(round(100 * s)))
    for sx in (-1, 1):
        tube(f"arm{sx}", RA, HA, sx * XA, 0.05, int(round(25 * s)), int(round(80 * s)))
    M, _ = pattern(pieces, sew=np.concatenate(sew))
    return Network(M), np.concatenate(seeds), body()


def run(scale=1.0, profile=False, log=None, **kw):
    net, X0, b = garment(scale)
    pr = cProfile.Profile() if profile else None
    t0 = time.time()
    if pr:
        pr.enable()
    X, rep = cs.solve(net, X0, body=b, log=log, **kw)
    if pr:
        pr.disable()
    wall = time.time() - t0
    if pr:
        pstats.Stats(pr).sort_stats("cumulative").print_stats(25)
        pstats.Stats(pr).sort_stats("tottime").print_stats(15)
    return net, X, rep, wall


if __name__ == "__main__":
    sc = float(sys.argv[1]) if len(sys.argv) > 1 and not sys.argv[1].startswith("-") else 1.0
    net, X, rep, wall = run(sc, "--profile" in sys.argv, log=print if "--log" in sys.argv else None)
    print(f"points {net.n} wall {wall:.1f} s")
    for k in ("links", "edges", "contact", "hard_ok", "lm_passes", "projection_passes", "pd_passes", "timing"):
        print(k, rep.get(k))
