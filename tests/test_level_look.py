"""The whole-level look round (2026-10-02): arches through a fin, roofs scaled to the span, the ground's character
(pointwise: tiles agree), the turf swatch tiles, clutter placement. uv run python tests/test_level_look.py"""
from pathlib import Path

import numpy as np

from hifipushie import terrain, terrain_ground, terrain_mesh, terrain_swatch

ROOT = Path(__file__).resolve().parents[1]


def _pebble():
    import json
    import tempfile
    d = Path(tempfile.mkdtemp())
    (d / "spec.json").write_text((ROOT / "examples" / "pebble_disc.json").read_text())
    return terrain.load(d / "spec.json")


def test_arch_and_roofs(T):
    vols, notes = terrain_mesh.volumes(T)
    arch = [v for v in vols if getattr(v, "kind", None) == "arch"][0]
    A = arch.arch
    # taller than wide, a roof of at least half the span over it
    assert A["w"] <= 0.8 * A["height"] + 1e-6, A
    top = float(T.height(np.asarray(A["c"])))
    assert top - A["floor"] - A["height"] >= max(2.0, 0.5 * A["w"]) - 1e-6
    # a fin: where the land along it is long, the neck is cut down to the floor beside the arch, not at it
    if getattr(arch, "cut", None) is not None:
        H = terrain_mesh.cut_neck(T, T.H.copy(), arch.cut)
        c, t = np.asarray(A["c"]), np.asarray(A["t"])
        mid = float(H[int(round(c[1] - T.ys[0])), int(round(c[0] - T.xs[0]))])
        assert abs(mid - top) < 0.5, (mid, top)  # (the fin over the arch is kept)
        side = c + t * (0.5 * A["through"] + 3.0)
        h_side = float(H[int(round(side[1] - T.ys[0])), int(round(side[0] - T.xs[0]))])
        assert h_side < top - 0.5 * A["height"], (h_side, top)
    field, vols, notes, _ = terrain_mesh.build_field(T)
    assert any("see-through" in n for n in notes)
    arch = [v for v in vols if getattr(v, "kind", None) == "arch"][0]
    assert arch.view["clear"] > 0.5, arch.view
    for n in notes:  # every cave keeps a roof: no "breaks through"
        assert "breaks through" not in n, n


def test_ground_pointwise(T):
    field, *_ = terrain_mesh.build_field(T)
    M = terrain_mesh.Materials(T, field)
    rng = np.random.default_rng(1)
    xy = np.c_[rng.uniform(150, 300, 3000), rng.uniform(60, 260, 3000)]
    h, _ = field.column(xy[:, 0], xy[:, 1])
    P = np.c_[xy, h]
    _, g = field.value_gradient(P, 0.125)
    N = g / np.linalg.norm(g, axis=1, keepdims=True)
    W1, C1 = M.weights(P, N)
    W2, C2 = np.concatenate([M.weights(P[:1000], N[:1000])[0], M.weights(P[1000:], N[1000:])[0]]), \
        np.concatenate([M.weights(P[:1000], N[:1000])[1], M.weights(P[1000:], N[1000:])[1]])
    assert np.array_equal(W1, W2) and np.array_equal(C1, C2)  # (a point's colour is its own: tiles agree)
    # varied ground: the grass's colour spreads (the old flat cover colour had none)
    gl = [M.layers.index(nm) for nm in ("grass", "turf") if nm in M.layers]
    grass = W1[:, gl].sum(1) > 0.75
    L = C1[grass] @ np.array([0.3, 0.59, 0.11])
    assert L.std() / L.mean() > 0.04, L.std() / L.mean()
    # no grass in the splash zone
    low = (P[:, 2] < 0.6) & (P[:, 2] > 0.1)
    if low.any():
        assert W1[low, M.layers.index("grass")].max() < 0.5


def test_grass_swatch_tiles():
    S = terrain_ground.grass_swatch()
    for k in ("albedo", "height"):
        a = S[k] if S[k].ndim == 2 else S[k][..., 1]
        assert max(terrain_swatch.tileability(a)) <= terrain_swatch.TILE_LIMIT, k
    assert abs(S["albedo"].reshape(-1, 3).mean(0) - 1).max() < 1e-6


def test_clutter(T):
    field, *_ = terrain_mesh.build_field(T)
    M = terrain_mesh.Materials(T, field)
    C = terrain_ground.clutter(T, M, field, ("bush", "tussock", "boulder"), box=[[150, 60], [300, 260]])
    kinds = C[:, 3].astype(int)
    assert (kinds == 0).sum() > 10 and (kinds == 1).sum() > 100, np.bincount(kinds)
    ground = C[:, 2] + np.where(kinds == 2, 0.12 * C[:, 4], 0.0)  # (boulders are sunk 0.12 x their scale)
    assert (ground > -0.3).all()  # (nothing under the sea)


def test_ground_edits(T):
    """The turf's step at a cliff lip and the bunkers are real geometry, finer than the grid, and continuous."""
    field, *_ = terrain_mesh.build_field(T)
    E = field.edits
    assert E is not None and E.any
    # a bunker: ~depth down inside, untouched a metre outside, the cut face within ~0.6 m
    sd = E.bunker_sd(np.c_[np.linspace(194, 210, 33), np.full(33, 114.3)])
    assert sd.min() < -1.0, sd
    xs = np.linspace(190, 214, 241)
    ys = np.full_like(xs, 114.3)
    h, s = field.column(xs, ys)
    h0, _ = field._column(xs, ys)
    dz = h - h0
    assert dz.min() < -0.5 and np.abs(dz[:20]).max() < 1e-9
    assert np.abs(np.diff(dz)).max() < 0.2  # (continuous at 0.1 m steps)
    # the turf lip: some lip points are stepped down by the turf's thickness, the step continuous
    rng = np.random.default_rng(3)
    P = np.c_[rng.uniform(150, 300, 20000), rng.uniform(60, 260, 20000), np.zeros(20000)]
    b, d, edge, top = E.bare(P)
    assert (b > 0.9).sum() > 50
    k = np.flatnonzero(b > 0.9)[:200]
    hz, _ = field.column(P[k, 0], P[k, 1])
    hr, _ = field._column(P[k, 0], P[k, 1])
    assert np.allclose(hz - hr, -E.lip_cfg["turf"] * b[k], atol=1e-9)  # (the step: the turf's thickness x bare)
    assert (hz - hr).min() < -0.9 * E.lip_cfg["turf"]
    # outside the zone the column is the grid's own
    far = np.c_[np.full(50, 600.0), np.linspace(380, 420, 50)]
    assert np.array_equal(field.column(far[:, 0], far[:, 1])[0], field._column(far[:, 0], far[:, 1])[0])


def test_kinds_and_swatches(T):
    field, *_ = terrain_mesh.build_field(T)
    M = terrain_mesh.Materials(T, field)
    assert "turf" in M.layers
    rng = np.random.default_rng(2)
    xy = np.c_[rng.uniform(150, 600, 20000), rng.uniform(60, 500, 20000)]
    P = np.c_[xy, field.column(xy[:, 0], xy[:, 1])[0]]
    k = M.kinds(P)
    assert (k["cut"] > 0.5).sum() > 50  # (a first cut round the fairways)
    assert (np.minimum(k["cut"], k["mown"]) > 0.5).sum() == 0
    for kind in ("turf", "grass"):
        Sw = terrain_ground.SWATCHES[kind]
        S = terrain_ground.grass_swatch(seed=Sw["seed"], blades=Sw["blades"] // 4, length=Sw["length"])
        assert max(terrain_swatch.tileability(S["height"])) <= terrain_swatch.TILE_LIMIT
    S = terrain_ground.sand_swatch()
    for a in (S["albedo"][..., 1], S["height"]):
        assert max(terrain_swatch.tileability(a)) <= terrain_swatch.TILE_LIMIT


def test_clutter_lips(T):
    field, *_ = terrain_mesh.build_field(T)
    M = terrain_mesh.Materials(T, field)
    C = terrain_ground.clutter(T, M, field, ("bush", "boulder"), box=[[100, 40], [320, 280]])
    bush = C[C[:, 3] == 0]
    b, d, edge, top = field.edits.bare(bush[:, :3])
    into = np.where(top > 0.3, d - edge, 1e3)
    assert (into > terrain_ground.CLUTTER_LIP["keep"] - 0.3).all(), into.min()
    near = into < 3.0
    if near.any():
        assert bush[near, 6].max() < 0.8  # (hugging the ground near the lip)


def test_thin_rock(T):
    """Thin rock (the arch's fin) keeps its relief, bounded by its local half-thickness, and shows strata."""
    field, vols, *_ = terrain_mesh.build_field(T)
    assert field.thin_parts, "no thin rock measured on pebble"
    A = [v for v in vols if getattr(v, "kind", None) == "arch"][0].arch
    rng = np.random.default_rng(3)
    P = np.c_[np.asarray(A["c"]) + rng.uniform(-14, 14, (30000, 2)), rng.uniform(0.5, 9.0, 30000)]
    h, s = field.column(P[:, 0], P[:, 1])
    F0 = (P[:, 2] - h) * s
    k = np.abs(F0) < 0.25
    P, F0, s = P[k], F0[k], s[k]
    hw, t = field.thin_at(P)
    assert (t > 0.5).mean() > 0.2, (t > 0.5).mean()
    R = field.solid(P, F0.copy(), s) - F0
    # the relief's own weight is back on the fin (it was a tenth), within THIN_RELIEF x hw where fully thin
    assert np.sqrt((R * R).mean()) > 0.3, np.sqrt((R * R).mean())
    full = (t > 0.999) & np.isfinite(hw)
    if full.any():
        assert (np.abs(R[full]) <= terrain_mesh.THIN_RELIEF * hw[full] + 1e-6).all()
    st = terrain_mesh.strata(P, 0.0, 4242)
    assert 0.05 < (st > 0.1).mean() < 0.9 and st.max() <= terrain_mesh.THIN_STRATA["depth"] + 1e-9
    # continuous along z: no jumps between beds (a jump meshes as shards)
    z = np.arange(0, 20, 0.01)
    col = terrain_mesh.strata(np.c_[np.full(len(z), 200.0), np.full(len(z), 80.0), z], 0.0, 4242)
    assert np.abs(np.diff(col)).max() < 0.05, np.abs(np.diff(col)).max()


def test_route_off_turf(T):
    """A route is worn ground only off mown turf."""
    field, *_ = terrain_mesh.build_field(T)
    M = terrain_mesh.Materials(T, field)
    if M.routes is None or M.ground is None:
        return
    iy, ix = np.nonzero(np.asarray(M.routes, float) > 0.5)
    xy = np.c_[T.xs[ix], T.ys[iy]]
    kinds = M.kinds(np.c_[xy, field.column(xy[:, 0], xy[:, 1])[0]])
    r = M._route(xy, kinds)
    turf = np.clip(np.asarray(kinds.get("mown", 0.0) + kinds.get("cut", 0.0)) + np.zeros(len(xy)), 0, 1)
    assert (r[turf > 0.7] < 0.05).all()
    if (turf < 0.05).any():
        assert r[turf < 0.05].max() > 0.5


if __name__ == "__main__":
    T = _pebble()
    test_arch_and_roofs(T)
    test_ground_pointwise(T)
    test_grass_swatch_tiles()
    test_clutter(T)
    test_ground_edits(T)
    test_kinds_and_swatches(T)
    test_clutter_lips(T)
    test_thin_rock(T)
    test_route_off_turf(T)
    print("ok")
