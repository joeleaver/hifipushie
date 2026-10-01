"""The compiled field kernels (fieldjit) against the numpy path they stand in for: bit-identical values.

Unit tests on synthetic inputs (fast; terrain_blocks included), then the whole 3D terrain field on real terrains (jointed
rock on, the default): the bake's field (CliffField
front + micro relief) and the meshing field (Field.value), value_gradient and Materials.weights at points near the
rock surface, numpy (fieldjit.ON = False) vs compiled. Terrains: examples/pebble_disc.json, examples/lava_field.json,
and workspace/terrain/t3_alps (skipped when missing; it takes ~1-2 min to build).

Run: uv run python tests/test_fieldjit.py [name filter]   (or pytest). HIFIPUSHIE_FIELDJIT_TERRAINS=pebble,lava,alps
picks the terrains (default all present)."""

from __future__ import annotations

import copy
import os
import sys
from pathlib import Path

import numpy as np
from scipy import ndimage

from hifipushie import fieldjit, noise, terrain_facets as tf, terrain_mesh as tm

ROOT = Path(__file__).resolve().parents[1]
TERRAINS = {"pebble": ROOT / "examples" / "pebble_disc.json", "lava": ROOT / "examples" / "lava_field.json",
            "alps": ROOT / "workspace" / "terrain" / "t3_alps" / "spec.json"}
if not TERRAINS["alps"].exists():  # (a worktree has no workspace: the main checkout's)
    TERRAINS["alps"] = ROOT.parents[2] / "workspace" / "terrain" / "t3_alps" / "spec.json"


def both(fn):
    """fn() with the kernels off, then on: (numpy result, compiled result)."""
    was = fieldjit.ON
    try:
        fieldjit.ON = False
        a = fn()
        fieldjit.ON = was
        b = fn()
    finally:
        fieldjit.ON = was
    return a, b


def same(a, b, what):
    a = a if isinstance(a, tuple) else (a,)
    b = b if isinstance(b, tuple) else (b,)
    for x, y in zip(a, b):
        x, y = np.asarray(x), np.asarray(y)
        assert x.shape == y.shape, (what, x.shape, y.shape)
        if not np.array_equal(x, y):
            d = np.abs(x.astype(float) - y.astype(float))
            raise AssertionError(f"{what}: {int((x != y).sum())} of {x.size} differ, max {float(d.max()):.3g}")


def need_jit():
    if not fieldjit.ON:
        print("  (kernels off: HIFIPUSHIE_JIT=0 or no numba)")
        return False
    return True


def test_noise():
    if not need_jit():
        return
    rng = np.random.default_rng(0)
    p = rng.normal(size=(50_000, 3)) * 40
    same(*both(lambda: noise._value_noise(p, 7)), "value noise")
    same(*both(lambda: noise.fbm(p, 6.0, 3, seed=11)), "fbm")
    i = np.floor(p).astype(np.int64)
    same(*both(lambda: noise._hash(i[:, 0], i[:, 1], i[:, 2], 5)), "hash")
    same(*both(lambda: noise._hash(i[:, 0], i[:, 0] * 0 + 3, i[:, 0] * 0, 5)), "hash (broadcast)")
    j = i.astype(np.float64)  # (anything but int64 arrays stays on numpy)
    same(*both(lambda: noise._hash(i[:, 0], j[:, 1].astype(np.int64), 7, 5)), "hash (scalar)")


def test_cubic():
    if not need_jit():
        return
    rng = np.random.default_rng(1)
    A = rng.normal(size=(120, 90))
    r, q = rng.uniform(-4, 124, 40_000), rng.uniform(-4, 94, 40_000)
    a = ndimage.map_coordinates(A, [r, q], order=3, prefilter=False, mode="nearest")
    same(a, fieldjit.cubic2d(A, r, q), "cubic")
    x, y = rng.uniform(-30, 500, 40_000), rng.uniform(-30, 500, 40_000)
    a = ndimage.map_coordinates(A, [(x - 2.0) / 5.0, (y + 3.0) / 5.0], order=1, mode="nearest")
    same(a, fieldjit.linear_at(A, x, y, 2.0, -3.0, 5.0), "linear")


def test_pl_walk():
    if not need_jit():
        return
    rng = np.random.default_rng(2)
    q = rng.normal(size=(40_000, 3)) * 9
    q[:500] = np.round(q[:500] * 4) / 4  # (ties and lattice points)
    same(*both(lambda: tm._pl_walk(q, 13)), "pl_walk")
    same(*both(lambda: tm._pl_walk(q, 13, vec=True)), "pl_walk vec")


def test_facets():
    if not need_jit():
        return
    rng = np.random.default_rng(3)
    p = np.cumsum(rng.normal(0, 0.3, (30_000, 3)), 0) + [500.0, -200.0, 40.0]  # (a coherent walk, like texels)
    fd = rng.normal(0, 1.5, (len(p), 2))
    fd[:3000] = 0.0  # (flat: one projection)
    for size in (8.0, 1.2, 0.45):
        same(*both(lambda: tf.facets(p, size, 4242, fd)), f"facets {size}")
    sparse = rng.uniform([0, 0, 0], [3000, 3000, 400], (300, 3))  # (a block per point, the caller's w untouched)
    same(*both(lambda: tf.facets(sparse, 1.2, 4242, fd[:300])), "facets, sparse")
    for b in range(4):  # (Poisson-disk seeds: candidates, rounds, priority ties)
        lo = np.array([b * tf.GROUP * 1.7 - 500, -3 * tf.GROUP]) - tf.PAD
        same(*both(lambda: tf._seeds(lo, lo + tf.GROUP + 2 * tf.PAD, 77 + b)), "seeds")
    tri, val = tf._triangulation(4242, 3, -2)
    q = rng.uniform([3 * tf.GROUP, -2 * tf.GROUP], [4 * tf.GROUP, -tf.GROUP], (20_000, 2))
    q[:200] = tri.points[tri.simplices[:200, 0]]  # (on seeds: on edges of several triangles)
    q[200:400] = 0.5 * (tri.points[tri.simplices[:200, 0]] + tri.points[tri.simplices[:200, 1]])  # (mid-edge)
    same(*both(lambda: tf.pl2d(q, 4242, 3, -2)), "pl2d")


def test_blocks():
    """terrain_blocks (jointed, bedded rock): the bed coordinate, master joints, offsets (with and without the maps'
    sharp window, narrower and wider than the ramp), ids and structure, at two voxels."""
    if not need_jit():
        return
    from hifipushie import terrain_blocks as tb
    rng = np.random.default_rng(5)
    n = 30_000
    p = np.cumsum(rng.normal(0, 0.3, (n, 3)), 0) + [500.0, -200.0, 40.0]
    fd = rng.normal(0, 1.5, (n, 2))
    fd[:2000] = 0.0  # (flat: every family's weight from the 0.04 floor)
    zoff = rng.normal(0, 1, n)
    for vox in (0.5, 1.0):
        B = tb.config(6.0, vox)
        same(*both(lambda: tb._pre(p, B, fd, zoff)[:2]), "blocks: bed coordinate")
        same(*both(lambda: tb._pre(p, B, fd, zoff)[2]), "blocks: master joints")
        same(*both(lambda: tb.offsets(p, B, fd, zoff)), "blocks: offsets")
        for sh in (0.25, B["ramp"], 0.8):
            same(*both(lambda: tb.offsets(p, B, fd, 0.0, None, sh)), f"blocks: offsets sharp {sh}")

        def ids():
            I = tb.ids(p, B, fd, zoff)
            return tuple([I[k] for k in ("K", "j", "thick", "thin", "bed_edge", "below_top", "bed_crack", "master",
                                         "master_d")] + I["blocks"] + I["weights"] + I["edges"] + I["open"])
        same(*both(ids), "blocks: ids")

        def st():
            o, I = tb.structure(p, B, fd, zoff, want_ids=True, sharp=0.3)
            return (o, I["sharp"], I["bed_edge"], I["bed_crack"], *I["open"], *I["blocks"])
        same(*both(st), "blocks: structure")


def _fields(name):
    from hifipushie import terrain, terrain_bake, terrain_cliffs
    T = terrain.load(TERRAINS[name])
    cfg = {**tm.DEFAULTS, **((T.spec.get("export") or {}).get("tiles") or {})}
    base, vols, notes, caves = tm.build_field(T, cfg)
    G = tm.Grid(T, cfg)
    region = terrain_cliffs.Region(T, base, G, cfg)
    bf = copy.copy(base)
    if base.rock is not None:
        bf.micro = terrain_bake.micro_relief(base.rock, float(cfg["micro"]), 1.0 / 16.0)
    front = terrain_cliffs.CliffField(bf, region).front_field()
    return T, base, front, tm.Materials(T, base)


def _points(T, base, n=60_000, seed=0):
    """Points within a couple of metres of the ground, most on steep ground (where the rock relief is), Morton
    ordered like texels, plus some round each volume (caves, arches)."""
    rng = np.random.default_rng(seed)
    (x0, y0), (x1, y1) = T.spec["extent"]
    # (a 256 m window round the steepest ground, as a few export tiles see it: points spread over a whole 3 x 4 km
    # map triangulate a facet block per point and take tens of minutes)
    if base.rock is not None:
        k = np.unravel_index(np.argmax(ndimage.uniform_filter(base.steep, 9)), base.steep.shape)
        cx, cy = base.x0 + k[1] * base.c, base.y0 + k[0] * base.c
        x0, y0, x1, y1 = max(x0, cx - 128), max(y0, cy - 128), min(x1, cx + 128), min(y1, cy + 128)
    xy = rng.uniform([x0, y0], [x1, y1], (30 * n, 2))
    st = base.steep_at(xy[:, 0], xy[:, 1]) if base.rock is not None else np.ones(len(xy))
    xy = np.r_[xy[st > 0.2][: n // 2 * 3 // 2], xy[: n // 4]]
    h, _ = base.column(xy[:, 0], xy[:, 1])
    P = np.c_[xy, h + rng.normal(0, 1.0, len(xy))]
    for v in base.vols[:20]:  # (volumes anywhere on the map)
        c = v.nodes if hasattr(v, "nodes") else np.array([0.5 * (v.lo + v.hi)])
        c = c[rng.integers(0, len(c), 300)] + rng.normal(0, 2.0, (300, 3))
        P = np.r_[P, c]
    return P[tm._morton(P, 0.5)]


def check_terrain(name):
    if not need_jit():
        return
    if not TERRAINS[name].exists():
        print(f"  ({name}: {TERRAINS[name]} missing, skipped)")
        return
    T, base, front, mats = _fields(name)
    P = _points(T, base)
    chunks = lambda f: np.concatenate([f(P[i:i + 25_000]) for i in range(0, len(P), 25_000)])
    same(*both(lambda: chunks(base.value)), f"{name}: Field.value")
    same(*both(lambda: chunks(front.value)), f"{name}: bake field (front + micro)")
    g = lambda: front.value_gradient(P[:20_000], 0.03)
    same(*both(g), f"{name}: value_gradient")
    N = np.c_[np.zeros((len(P), 2)), np.ones(len(P))]
    N[::2] = np.c_[np.ones(len(P[::2])) * 0.8, np.zeros(len(P[::2])), np.ones(len(P[::2])) * 0.6]
    same(*both(lambda: mats.weights(P[:20_000], N[:20_000])), f"{name}: Materials.weights")
    print(f"  {name}: {len(P)} points identical")


def test_pebble():
    check_terrain("pebble")


def test_lava():
    check_terrain("lava")


def test_alps():
    check_terrain("alps")


if __name__ == "__main__":
    pick = os.environ.get("HIFIPUSHIE_FIELDJIT_TERRAINS")
    fails = 0
    for name, fn in list(globals().items()):
        if not (name.startswith("test_") and callable(fn)):
            continue
        if len(sys.argv) > 1 and not any(a in name for a in sys.argv[1:]):
            continue
        if pick and name[5:] in TERRAINS and name[5:] not in pick.split(","):
            continue
        try:
            fn()
            print("ok  ", name)
        except Exception as e:  # noqa: BLE001
            fails += 1
            import traceback
            traceback.print_exc()
            print("FAIL", name, e)
    sys.exit(1 if fails else 0)
