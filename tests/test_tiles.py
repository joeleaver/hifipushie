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


def _box(c, h):
    """A closed box mesh (12 triangles) centred at c, half size h."""
    import itertools
    V = np.array([[c[0] + sx * h, c[1] + sy * h, c[2] + sz * h] for sx, sy, sz in itertools.product((-1, 1), repeat=3)])
    F = np.array([[0, 1, 3], [0, 3, 2], [4, 6, 7], [4, 7, 5], [0, 4, 5], [0, 5, 1], [2, 3, 7], [2, 7, 6],
                  [0, 2, 6], [0, 6, 4], [1, 5, 7], [1, 7, 3]])
    return V, F


def test_floating_pieces_dropped():
    """Closed cliff pieces off the tile border that never come down to the ground: dropped and listed under the size
    limit (a slab of style relief cut off over a lip), kept above it (a stack's head: the check fails it); pieces
    on the ground and pieces on the border always kept."""
    parts = [((0, 0, 0.5), 1.0), ((10, 0, 8), 1.0), ((20, 0, 30), 6.0), ((30, 0, 20), 1.0)]
    Ps, Fs, off = [], [], 0
    for c, h in parts:
        V, F = _box(c, h)
        Ps.append(V)
        Fs.append(F + off)
        off += len(V)
    P, F = np.vstack(Ps), np.vstack(Fs)
    border = np.zeros(len(P), bool)
    border[24:32] = True  # (the fourth box runs off the tile)
    clear = P[:, 2] - 0.0  # (flat ground at z 0)
    F2, dropped = tm._drop_specks(P, F, border, 4.0, clear, 50.0)
    kept = {int(v) // 8 for v in np.unique(F2)}
    assert kept == {0, 2, 3}, kept
    assert len(dropped) == 1 and dropped[0]["triangles"] == 12 and dropped[0]["clearance_m"] == 7.0, dropped
    F3, d3 = tm._drop_specks(P, F, border, 4.0)  # (no clearance: only specks under min_area)
    assert len(F3) == len(F) and d3 == []


def test_region_edge_is_smooth():
    """The cliff region's weight S fades to 0 without a step (cut at the grown mask, it fell from ~0.6 to 0 in one
    lattice step: the front's sunk edge and the shell's back stood in the open round kaze_cave's doline)."""
    from hifipushie import terrain_cliffs as tc

    class R_:
        d = 1.0
    a = np.zeros((80, 80))
    a[38:42, 38:42] = 1.0
    S = tc.Region._grow(R_(), a, 6.0)
    assert np.abs(np.diff(S, axis=0)).max() < 0.25 and np.abs(np.diff(S, axis=1)).max() < 0.25, \
        np.abs(np.diff(S, axis=0)).max()
    assert S[0, 0] == 0.0 and S[40, 40] > 0.99, (S[0, 0], S[40, 40])


def test_relief_fades_in_at_its_cut(base, G):
    """The rock relief is evaluated only where its weight is over RELIEF_CUT; it must ease in from there. Taken at
    once it stepped in at 1% of its size: a 2-3 cm step in the field along the weight's 0.01 contour, metres out on
    the grass round every rock face, drawn by the maps' normals as thin dark dashed cracks (pushieworld note 104)."""
    lo, hi = np.min([G.bounds(i, j)[0] for i in range(4) for j in range(4)], 0), \
        np.max([G.bounds(i, j)[1] for i in range(4) for j in range(4)], 0)
    xs, ys = np.arange(lo[0] + 1, hi[0] - 1, 0.5), np.arange(lo[1] + 1, hi[1] - 1, 0.5)
    X, Y = np.meshgrid(xs, ys)
    w = base.relief_at(X.ravel(), Y.ravel()).reshape(X.shape)
    cut = tm.RELIEF_CUT
    a = np.argwhere((w[:, :-1] - cut) * (w[:, 1:] - cut) < 0)  # (grid pairs straddling the cut, along x)
    assert len(a) > 20, len(a)
    a = a[np.linspace(0, len(a) - 1, 60).astype(int)]
    y = Y[a[:, 0], a[:, 1]]
    x0, x1 = X[a[:, 0], a[:, 1]], X[a[:, 0], a[:, 1] + 1]
    for _ in range(30):  # (bisect onto the cut)
        xm = 0.5 * (x0 + x1)
        up = (base.relief_at(xm, y) > cut) == (base.relief_at(x0, y) > cut)
        x0, x1 = np.where(up, xm, x0), np.where(up, x1, xm)
    jumps = []
    for e in (-0.001, 0.001):
        x = 0.5 * (x0 + x1) + e
        h, _ = base.column(x, y)
        jumps.append(base.value(np.c_[x, y, h]))
    j = np.abs(jumps[1] - jumps[0])
    assert j.max() < 2e-3, f"the field steps by up to {1000 * j.max():.1f} mm where the rock relief's weight is cut"
    return float(j.max())


def test_sunk_edge_reads_as_ground(cf, G):
    """Where the cliff front sinks toward the region's edge it dives under the heightmap; the few cm of the dive that
    show were baked as a steep dark crease (rock weights from a tipped 0.4 m normal, AO from metres down): a thin dark
    dashed line along every overlay edge (pushieworld note 104). Its maps read the true ground over it: the normal the
    bake uses (terrain_bake._unsunk) is the ground's on both sides of SINK_EDGE."""
    from hifipushie import terrain_bake as tb
    R = cf.region
    lo, hi = G.bounds(0, 0)[0], G.bounds(3, 3)[1]
    xs, ys = np.arange(lo[0] + 1, hi[0] - 1, 0.5), np.arange(lo[1] + 1, hi[1] - 1, 0.5)
    X, Y = np.meshgrid(xs, ys)
    S = R.s(X.ravel(), Y.ravel()).reshape(X.shape)
    e = terrain_cliffs.SINK_EDGE
    a = np.argwhere((S[:, :-1] - e) * (S[:, 1:] - e) < 0)
    assert len(a) > 20, len(a)
    a = a[np.linspace(0, len(a) - 1, 40).astype(int)]
    y = Y[a[:, 0], a[:, 1]]
    ff = cf.front_field()
    worst_raw, worst = 0.0, 0.0
    for t in np.linspace(-0.6, 0.6, 13):  # (across the edge, along x)
        x = 0.5 * (X[a[:, 0], a[:, 1]] + X[a[:, 0], a[:, 1] + 1]) + t
        h, _ = cf.base.column(x, y)
        P = np.c_[x, y, h]
        for _ in range(8):  # (onto the front)
            f, g = ff.value_gradient(P, 0.03)
            P = P - (f / np.maximum((g * g).sum(1), 1e-9))[:, None] * g
        # (the normal map's normal: the front's at 3 cm, eased to the ground's; the true ground's over the same column)
        g0 = tb._unit(ff.value_gradient(P, 0.03)[1])
        gu = tb._unsunk(ff, P, g0, 0.03)
        hq, _ = cf.base.column(P[:, 0], P[:, 1])
        gt = tb._unit(cf.base.value_gradient(np.c_[P[:, :2], hq], 0.03)[1])
        soft = gt[:, 2] > 0.85  # (gentle ground: where the line showed)
        ang = lambda u, v: np.degrees(np.arccos(np.clip((u * v).sum(1), -1, 1)))
        if soft.any():
            worst_raw = max(worst_raw, float(ang(g0, gt)[soft].max()))
            worst = max(worst, float(ang(gu, gt)[soft].max()))
    assert worst_raw > 20, f"the transects never crossed the dive ({worst_raw:.1f} deg)"
    assert worst < 8, f"the sunk edge's normal is {worst:.1f} deg off the true ground's"
    return worst_raw, worst


def test_dam_stays_in_the_heightmap():
    """A dammed lake on a slope: its embankment is ground, so the tile heightmap (the pushed ground) holds the lake.
    Taken for a cliff, the heightmap was pushed down the dam's face and its crest eroded away: flooded to the lake's
    level the heightmaps held 134,000 m2 for a 3,300 m2 pond (pushieworld note 106)."""
    from scipy import ndimage
    spec = json.loads(json.dumps(SPEC))
    spec["landforms"] = {"pond": {"type": "lake", "at": [64, 96], "radius": 10, "depth": 2, "dam": True}}
    d = Path(tempfile.mkdtemp())
    (d / "spec.json").write_text(json.dumps(spec))
    T = terrain.load(d / "spec.json")
    lk = T.lakes["pond"]
    assert lk["area"] > 100 and T.dams["pond"].any(), (lk, T.dams["pond"].sum())
    rep = "\n".join(T.report()) if isinstance(T.report(), list) else str(T.report())
    assert "dammed:" in rep, "the report says nothing of the dam"
    lakes = tm.lake_outlines(T)
    assert len(lakes["pond"]["outline"][0]) >= 8 and abs(lakes["pond"]["level"] - lk["level"]) < 1e-3
    cfg, G, region, cf, vols = _shell(T)
    # the pushed heightmap on its lattice, flooded to the level from the lake's centre
    xs = G.origin[0] + np.arange(region.nx) * region.d
    ys = G.origin[1] + np.arange(region.ny) * region.d
    X, Y = np.meshgrid(xs, ys)
    Hm = region.height(X.ravel(), Y.ravel()).reshape(X.shape)
    lab, _ = ndimage.label(Hm < lk["level"])
    k = lab[int(round((96 - ys[0]) / region.d)), int(round((64 - xs[0]) / region.d))]
    assert k > 0, "the heightmap is dry at the lake's centre"
    area = float((lab == k).sum()) * region.d ** 2
    assert area < terrain_cliffs.LAKE_AREA * lk["area"], f"the heightmap holds {area:.0f} m2 for a {lk['area']:.0f} m2 lake"
    on = T.dams["pond"]
    S = region.s(T.X[on], T.Y[on])
    assert S.max() < 0.05, f"the dam is in the cliff region (S up to {S.max():.2f})"
    return area, lk["area"]


def test_projected_normals_never_zero():
    """A field flat at the normal's stencil (a capped constant) still gives unit normals (zero ones are invalid glTF,
    and read as "normals differ by 90 deg" across a tile border)."""
    class Flat:
        def value_gradient(self, P, h):
            g = np.zeros((len(P), 3))
            g[P[:, 0] > 0, 2] = 1.0 if h > 0.6 else 0.0  # (flat at the fine stencil, sloped at the wide one)
            return np.zeros(len(P)), g
    P = np.array([[1.0, 0, 0], [-1.0, 0, 0]])
    _, N = tm._project(Flat(), P, 1.0, iterations=0)
    assert np.allclose(np.linalg.norm(N, axis=1), 1.0), N


def test_unflip_corners():
    """A corner whose normal points against its face gets its own vertex with the face's normal; the shared vertex
    keeps its normal for the other face (and stays first: a border chain reads it)."""
    P = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0], [1, 1, 0.0]])
    F = np.array([[0, 1, 2], [1, 3, 2]])
    N = np.array([[0, 0, 1], [0, 0, -1], [0, 0, 1], [0, 0, 1.0]])
    src = np.arange(4)
    P2, F2, N2, s2 = tm._unflip_corners(P, F, N, src, np.array([True, False]))
    assert len(P2) == 5 and F2[0, 1] == 4 and F2[1, 0] == 1, F2
    assert np.allclose(N2[4], [0, 0, 1]) and np.allclose(N2[1], [0, 0, -1]) and s2[4] == 1
    fn = np.cross(P2[F2[:, 1]] - P2[F2[:, 0]], P2[F2[:, 2]] - P2[F2[:, 0]])
    assert (np.einsum("fcj,fj->fc", N2[F2], fn)[0] >= 0).all()


def test_long_tube_by_runs():
    """A long tube evaluates its segments in runs at the points within their reach: the same values (and floor /
    size details) as every segment at every point, wherever the tube can matter."""
    rng = np.random.default_rng(3)
    t_ = np.linspace(0, 1, 120)
    nodes = np.c_[300 * t_, 40 * np.sin(9 * t_), 50 - 40 * t_]
    tb = tm.Tube("t", nodes, 3.5, 2.5, nodes[:, 2], rough=0.2, seed=4)
    P = np.c_[rng.uniform(-10, 310, 20000), rng.uniform(-50, 50, 20000), rng.uniform(0, 60, 20000)]
    got = tb.sd(P, detail=True)
    run, tm.TUBE_RUN = tm.TUBE_RUN, 10 ** 6
    try:
        ref = tb.sd(P, detail=True)
    finally:
        tm.TUBE_RUN = run
    near = ref[0] < tb.reach - 1.0
    assert near.sum() > 1000
    for g, r in zip(got, ref):
        assert np.array_equal(g[near], r[near])
    assert (got[0][~near] >= tb.reach - 1.0 - 1e-9).all()


if __name__ == "__main__":
    t0 = time.time()
    test_plane_chain()
    test_long_tube_by_runs()
    test_unflip_corners()
    test_floating_pieces_dropped()
    test_region_edge_is_smooth()
    test_projected_normals_never_zero()
    print("dam stays in the heightmap (flooded %.0f m2, lake %.0f m2)" % test_dam_stays_in_the_heightmap())
    T = _coast()
    print(f"terrain {time.time() - t0:.1f} s")
    test_cover_named_by_type(T)
    test_budget_check()
    t0 = time.time()
    cfg, G, region, cf, vols = _shell(T)
    print(f"field {time.time() - t0:.1f} s")
    test_shell_keeps_add_volumes_whole(cf, region)
    print(f"relief fades in at its cut (largest step {1000 * test_relief_fades_in_at_its_cut(cf.base, G):.2f} mm)")
    print("sunk edge reads as ground (raw / baked normal off the ground's: %.1f / %.1f deg)"
          % test_sunk_edge_reads_as_ground(cf, G))
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
