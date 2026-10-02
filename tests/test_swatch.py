"""The tiling rock detail (terrain_swatch): the swatch tiles, the projection is a function of position.
uv run python tests/test_swatch.py"""
import numpy as np

from hifipushie import terrain_swatch as ts


def test_periodic_facets():
    # facets on the torus: no step at the wrap seam
    a = ts.periodic_facets(128, 2.0, 0.3, 11, stretch=1.4)
    b = ts.periodic_facets(256, 4.0, 0.3, 11, stretch=1.4)
    assert a.shape == (128, 128) and np.isfinite(a).all()
    assert max(ts.tileability(a)) < ts.TILE_LIMIT, ts.tileability(a)
    assert np.isfinite(b).all()


def test_swatch_tiles():
    S = ts.swatch(None, size=1.0, res=128)
    for k in ("height", "normal", "albedo", "rough"):
        t = ts.tileability(S[k])
        assert max(t) < ts.TILE_LIMIT, (k, t)
    assert abs(S["albedo"].reshape(-1, 3).mean(0) - 1).max() < 1e-6


class _Plane:
    """A vertical wall facing -y (x east), as a field: value = -y."""
    rock = None

    def value_gradient(self, p, h):
        return -p[:, 1], np.tile([0.0, -1.0, 0.0], (len(p), 1))


def test_projection():
    D = ts.DetailProjection(_Plane())
    P = np.array([[10.0, 0.0, 5.0], [11.0, 0.0, 7.0]])
    det = D.attrs(P)
    # facing -y: the strike (to the right as one faces the wall from the south) is +x, all side, v = z
    assert np.allclose(det[:, :2], [[1, 0], [1, 0]]) and np.allclose(det[:, 2], 1) and np.allclose(det[:, 3], P[:, 2])
    b = D.face_bins(P, np.array([[0, 1, 1]]))
    uv = D.uv(P, np.repeat(b, 2))
    assert b[0] == 0 and np.allclose(uv, [[10, -5], [11, -7]])


def test_cells_and_pits_tile():
    # the polygonal facets (soft-min over the K nearest seeds) and the pits are continuous on the torus
    h, ids, e = ts.periodic_cells(256, 1.0, 0.2, 5, stretch=1.3)
    assert max(ts.tileability(h)) < ts.TILE_LIMIT and (e >= 0).all()
    d, inside = ts.periodic_pits(256, 1.0, 6)
    assert max(ts.tileability(d)) < ts.TILE_LIMIT and d.min() >= 0


def test_stats_and_repetition():
    S = ts.swatch(None, size=1.0, res=128)
    st = ts.swatch_stats(S)
    assert st["slope_octaves"] and st["albedo"]["lum_std"] > 0
    prof = ts.repetition_profile(S, ps=[0.01, 0.05])
    assert len(prof) == 2 and all(0 <= c and -1 <= p <= 1 for _, c, p in prof)


def test_scan_swatch():
    # (only where the optional rock_scans pack is present)
    try:
        S = ts.scan_swatch("rock_face_03", n=128)
    except FileNotFoundError:
        print("  (rock_scans not fetched: skipped)")
        return
    assert S["albedo"].shape == (128, 128, 3) and abs(S["albedo"].reshape(-1, 3).mean(0) - 1).max() < 1e-6
    assert S["height_scale_m"] > 0


def test_structure_lines_follow_the_rock():
    """The lines map's signed distances are clean ramps across each drawn line and its strength is continuous (the
    distance to the nearest plane of the point's own bed was noise inside thin packages, and a strength gated to a texel
    round it stepped row by row: sawteeth and thorns along the 0.5 m mesh). Columns of points up a face on pebble."""
    from pathlib import Path
    from hifipushie import terrain, terrain_mesh as tm
    spec = Path(__file__).resolve().parents[1] / "examples" / "pebble_disc.json"
    T = terrain.load(spec)
    field = tm.build_field(T)[0]
    texel = 1 / 8.0
    z = np.arange(-2.0, 40.0, 0.01)
    drawn = 0
    for x, y in ((176.0, 224.0), (150.0, 210.0), (205.0, 238.0)):
        X = np.c_[np.full(len(z), x), np.full(len(z), y), z]
        fd = field.face_dir(X[:, 0], X[:, 1])
        n = np.c_[fd[:, :2], np.zeros(len(z))]
        n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-9)
        sb, ab, sj, aj = ts.structure_lines(field, X, texel, N=n)
        assert np.abs(np.diff(ab)).max() < 0.05 and np.abs(np.diff(aj)).max() < 0.05
        on = (ab[1:] > 0.2) & (ab[:-1] > 0.2)
        drawn += on.sum()
        if on.any():  # (up a vertical face the distance to a level plane grows at ~1 m per m)
            slope = np.diff(sb)[on] / 0.01
            assert np.percentile(np.abs(slope - np.median(slope)), 95) < 0.15, slope
    assert drawn > 0


if __name__ == "__main__":
    for f in (test_periodic_facets, test_swatch_tiles, test_projection, test_cells_and_pits_tile,
              test_stats_and_repetition, test_scan_swatch, test_structure_lines_follow_the_rock):
        f()
        print("ok", f.__name__)
