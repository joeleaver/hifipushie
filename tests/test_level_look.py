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
    grass = W1[:, M.layers.index("grass")] > 0.9
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
    assert (C[:, 2] > -0.3).all()  # (nothing under the sea)


if __name__ == "__main__":
    T = _pebble()
    test_arch_and_roofs(T)
    test_ground_pointwise(T)
    test_grass_swatch_tiles()
    test_clutter(T)
    print("ok")
