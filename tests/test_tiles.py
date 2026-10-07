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


if __name__ == "__main__":
    t0 = time.time()
    T = _coast()
    print(f"terrain {time.time() - t0:.1f} s")
    test_cover_named_by_type(T)
    test_budget_check()
    t0 = time.time()
    cfg, G, region, cf, vols = _shell(T)
    print(f"field {time.time() - t0:.1f} s")
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
