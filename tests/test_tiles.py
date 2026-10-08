"""Tile export faults found by the first consumer export (pushieworld slice_a, 2026-10-07), on a small synthetic
coast (128 m, sheer sea cliffs, 32 m tiles): the cliff shell's depth under sheer faces, triangle budgets that hold or
are reported, failed checks as a report. uv run python tests/test_tiles.py"""
import json
import tempfile
import time
from pathlib import Path

import numpy as np

from hifipushie import terrain, terrain_cliffs, terrain_mesh as tm

SPEC = {"world": {"kind": "coast", "base": 10}, "extent": [[0, 0], [128, 128]], "cell": 0.64,
        "tilt": {"down": "south", "grade": 0.25},
        "sea": {"level": 0, "shore": "cliffs", "cliffs": {"height": [14, 20]}},
        "cover": [{"type": "meadow", "in": "everywhere"}, {"type": "rock", "in": "cliffs"}],
        "export": {"tiles": {"tile": 32}}}
TILE = (2, 0)  # (the tile with the most sheer columns)


def _coast():
    d = Path(tempfile.mkdtemp())
    (d / "spec.json").write_text(json.dumps(SPEC))
    return terrain.load(d / "spec.json")


def _shell(T):
    cfg = {**tm.DEFAULTS, **T.spec["export"]["tiles"]}
    base, vols, notes, caves = tm.build_field(T, cfg)
    G = tm.Grid(T, cfg)
    region = terrain_cliffs.Region(T, base, G, cfg)
    return cfg, G, region, terrain_cliffs.CliffField(base, region), vols


def _mc(G, cf, vols, ij):
    idx, F, _ = tm._tile_mc(cf, G, ij[0], ij[1], 0, vols)
    v = G.voxel
    return np.c_[G.origin[0] + idx[:, 0] * v, G.origin[1] + idx[:, 1] * v, (idx[:, 2] + tm.ZOFF) * v], F


def test_cover_named_by_type(T):
    assert list(T.cover)[:2] == ["meadow", "rock"], list(T.cover)  # (not cover_1, cover_2)


def test_shell_stops_under_the_cliff_foot(G, region, cf, vols):
    """Under a sheer face's columns the shell's back, `thick` behind the column's own plane, was thick / cos(slope)
    down: a buried sheet 50-100 m deep, cut open by the lattice's bottom (slice_a: z -95 m under a sea floor at -7,
    44 open edges, 262k of a tile's 439k triangles more than 10 m under their ground)."""
    lo, hi = G.bounds(*TILE)
    xs = np.arange(lo[0], hi[0], 0.5)
    X, Y = np.meshgrid(xs, np.arange(lo[1], hi[1], 0.5))
    h, s = cf.column(X.ravel(), Y.ravel())
    assert (s < 0.15).sum() > 50, "the test terrain lost its sheer cliffs"
    P, F = _mc(G, cf, vols, TILE)
    assert P[:, 2].min() > h.min() - (region.thick + 2.0), (P[:, 2].min(), h.min(), region.thick)
    c = P[F].mean(1)
    assert np.all(c[:, 2] > region.back_at(c[:, 0], c[:, 1])[0] - 1.0)
    # closed: no open edge except on the tile's border planes
    be = tm._boundary_edges(F)
    on = lambda q: (np.abs(q[:, 0] - lo[0]) < 1e-6) | (np.abs(q[:, 0] - hi[0]) < 1e-6) | \
        (np.abs(q[:, 1] - lo[1]) < 1e-6) | (np.abs(q[:, 1] - hi[1]) < 1e-6)
    assert np.all(on(P[be[:, 0]]) & on(P[be[:, 1]])), "the shell is open inside the tile"
    # the tile's lattice reaches the shell's back (it used to stop at ground - zpad / 0.15 whatever the shell did)
    assert float(np.min(cf.zlow(X.ravel(), Y.ravel()))) <= float(P[:, 2].min()) + 1e-6
    # on even ground the back is where it was: `thick` under it
    flat = s > 0.98
    hb, _ = region.back_at(X.ravel()[flat], Y.ravel()[flat])
    assert np.percentile(np.abs(h[flat] - hb - region.thick), 50) < 0.3
    return P, F


def test_budget_holds(cf, G, P, F):
    """The cliff tile decimates to its budget: not the dense mesh handed back (495k triangles at every LOD on
    slice_a's cave tile: thin buried sheets folded at every collapse), and not far under it either (the buried back's
    own error counted as the tolerance: 1,132 triangles for LOD 0 of a 64 m cliff tile)."""
    P2, _ = tm.project(cf, P, G.voxel)
    for budget, err in ((4000, 0.04), (1500, 0.15)):  # (the dense border alone is ~800 edges)
        t = time.time()
        Pd, Fd = tm._decimate(P2, F, err, budget, cf)
        print(f"  budget {budget}: {len(F)} -> {len(Fd)} triangles, {time.time() - t:.1f} s")
        assert len(Fd) <= 1.15 * budget + 64, (budget, len(Fd))
        if err < 0.1:
            assert len(Fd) >= 0.5 * budget, (budget, len(Fd))
    Pc, Fc = tm._collision_mesh(P2, F, 2000)
    assert len(Fc) <= 2200 and len(Fc) < len(F)


def test_budget_check():
    cfg = {"budget": [12000, 3000, 800], "error": [0.04, 0.15, 0.5]}
    L = lambda n, mc: {"triangles": n, "visible_triangles": n // 3, "marching_cubes_triangles": mc}
    tiles = [{"i": 4, "j": 1, "volumes": ["smugglers"], "lods": [L(495898, 497134), L(495622, 497134), L(700, 497134)]},
             {"i": 0, "j": 0, "lods": [L(12000, 136208), L(5999, 136208), None]}]
    over = tm.budget_check(tiles, cfg, 3)
    assert [(o["tile"], o["lod"]) for o in over] == [([4, 1], 0), ([4, 1], 1)], over
    assert "removed nothing" in over[0]["why"] and over[0]["budget"] == 12000


def test_failed_checks_are_a_report(T):
    """An export whose checks fail is still complete on disk, raises TilesCheckFailed with the result, and its
    summary leads with what failed (the MCP tool returns that, not a traceback)."""
    out = Path(tempfile.mkdtemp()) / "tiles"
    cfg = {"only": [list(TILE), list(TILE)], "lods": 2, "maps": False, "detail": False, "budget": [40, 20, 10],
           "collision_budget": 500, "incremental": False}
    try:
        tm._export_tiles(T, out, cfg, log=lambda *a: None)
        raise AssertionError("a 40-triangle budget passed")
    except tm.TilesCheckFailed as e:
        r = e.result
    M = json.loads((out / "manifest.json").read_text())
    assert M["budget_check"]["over"] and M["seam_check"]["over_budget"] >= 1
    assert all((out / L["file"]).exists() for t in M["tiles"] for L in t["lods"] if L)
    s = tm.summary(r)
    assert s.startswith("CHECKS FAILED") and "against a budget of 40" in s and "COMPLETE on disk" in s, s[:400]
    t = M["tiles"][0]
    assert t["collision_triangles"] <= 550, t["collision_triangles"]
    # heightmaps are C order on disk (a plain reader got a column-major file transposed)
    g = M["ground"][0]
    with open(out / g["heightmap"], "rb") as f:
        head = f.read(128)
    assert b"'fortran_order': False" in head, head
    H = np.load(out / g["heightmap"])
    lo = np.array(g["min"])
    assert H[0, 0] > H[-1, 0] + 3.0  # (row 0 is north: the land; the last row the sea's edge of this tile)


def test_plane_chain():
    """The seam check compares border CHAINS: a sliver lying in the border plane (its third vertex on the plane, on no
    chain: the island's 11,8 / 12,8 'border vertices differ') and an edge along a tile corner's vertical line (its far
    face in the diagonal tile: 21,6 / 22,6 at LOD 2) are not border differences."""
    x = 64.0
    P = np.array([[x, 0, 0], [x, 10, 0], [x - 5, 5, 0],          # a face with an edge on the plane (the chain)
                  [x, 10, 0.0004], [x, 10.0004, 0.0002],           # a 0.4 mm sliver in the plane, off the chain
                  [x, 20, 0], [x, 20, 5], [x - 5, 20, 2]], float)  # an edge on the corner line y = 20
    N = np.tile([1.0, 0, 0], (len(P), 1))
    F = np.array([[0, 1, 2], [1, 3, 4], [5, 6, 7]])
    V, _, E = tm._plane_chain((P, N, F), 0, x, (0.0, 20.0))
    keys = {tuple(p) for p in V}
    assert (x, 0.0, 0.0) in keys and (x, 10.0, 0.0) in keys
    assert not any(abs(p[1] - 20.0) < 1e-9 for p in keys), keys  # (the corner line's edge left out)
    assert frozenset(((x, 0.0, 0.0), (x, 10.0, 0.0))) in E


class _Block:  # (a solid add volume standing deep in the rock, like a sea stack over the heightfield's slim core)
    op, blend, relief = "add", 0.3, 0.0

    def __init__(self, lo, hi):
        self.lo, self.hi = np.asarray(lo, float) - 2.0, np.asarray(hi, float) + 2.0
        self.c, self.h = (np.asarray(lo, float) + hi) / 2, (np.asarray(hi, float) - lo) / 2

    def sd(self, p, detail=False):
        q = np.abs(p - self.c) - self.h
        d = np.linalg.norm(np.maximum(q, 0), axis=1) + np.minimum(q.max(1), 0)
        return (d, np.full(len(p), np.inf), np.full(len(p), 1.0)) if detail else d

    def touches(self, lo, hi):
        return bool(np.all(self.hi >= lo) and np.all(self.lo <= hi))


def test_shell_keeps_add_volumes_whole(cf, region):
    """Inside a solid add volume the shell is all rock: its back follows the heightfield's ground moved in, and under a
    stack that ground is the slim core: the island's Kaze stacks were hollow from the sea floor to 16 m up, and their
    decimated hollow walls (buried faces) came out through the stack as white triangles."""
    b = cf.base
    xy = np.array([[20.0, 100.0]])
    h, _ = b.column(xy[:, 0], xy[:, 1])
    hb, _ = region.back_at(xy[:, 0], xy[:, 1])
    z = float(hb[0]) - 3.0  # under the shell's back
    blk = _Block([xy[0, 0] - 3, xy[0, 1] - 3, z - 4], [xy[0, 0] + 3, xy[0, 1] + 3, float(h[0]) + 6])
    p = np.array([[xy[0, 0], xy[0, 1], z]])
    vols = b.vols
    whole = terrain_cliffs.WHOLE_ADDS
    try:
        terrain_cliffs.WHOLE_ADDS = True  # (off by default until sea stacks mesh cleanly solid)
        b.vols = list(vols) + [blk]
        cf.__dict__.pop("_add_vols", None)
        assert cf.value(p)[0] < 0, cf.value(p)  # (inside the block: rock)
        assert b.value(p)[0] < 0
    finally:
        terrain_cliffs.WHOLE_ADDS = whole
        b.vols = vols
        cf.__dict__.pop("_add_vols", None)


if __name__ == "__main__":
    t0 = time.time()
    test_plane_chain()
    T = _coast()
    print(f"terrain {time.time() - t0:.1f} s")
    test_cover_named_by_type(T)
    test_budget_check()
    t0 = time.time()
    cfg, G, region, cf, vols = _shell(T)
    print(f"field {time.time() - t0:.1f} s")
    test_shell_keeps_add_volumes_whole(cf, region)
    t0 = time.time()
    P, F = test_shell_stops_under_the_cliff_foot(G, region, cf, vols)
    print(f"shell depth ok ({len(F)} triangles, {time.time() - t0:.1f} s)")
    t0 = time.time()
    test_budget_holds(cf, G, P, F)
    print(f"budget ok ({time.time() - t0:.1f} s)")
    t0 = time.time()
    test_failed_checks_are_a_report(T)
    print(f"failed checks report ok ({time.time() - t0:.1f} s)")
    print("ok")
