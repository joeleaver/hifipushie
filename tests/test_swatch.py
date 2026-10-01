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


if __name__ == "__main__":
    for f in (test_periodic_facets, test_swatch_tiles, test_projection):
        f()
        print("ok", f.__name__)
