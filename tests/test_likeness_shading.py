"""The fast renderer's shading passes (likeness._DepthMap shadows, ambient_occlusion): a floor with a square tile
floating 20 mm over it. Shadows must fall where the geometry says; AO must darken under the tile."""
import numpy as np

from hifipushie import likeness as lk


def _grid(n, half, z):
    xs = np.linspace(-half, half, n)
    X, Y = np.meshgrid(xs, xs, indexing="ij")
    V = np.c_[X.ravel(), Y.ravel(), np.full(n * n, z)]
    F = []
    for i in range(n - 1):
        for j in range(n - 1):
            a, b, c, d = i * n + j, (i + 1) * n + j, (i + 1) * n + j + 1, i * n + j + 1
            F += [[a, b, c], [a, c, d]]
    return V, np.array(F)


def _scene():
    Vf, Ff = _grid(81, 0.06, 0.0)      # floor, 1.5 mm cells
    Vt, Ft = _grid(9, 0.01, 0.02)      # tile 20 x 20 mm, 20 mm up
    return np.r_[Vf, Vt], np.r_[Ff, Ft + len(Vf)], len(Vf)


def test_shadow_falls_where_the_geometry_says():
    V, F, nf = _scene()
    floor = V[:nf]
    n = np.tile([0, 0, 1.0], (nf, 1))
    for ang in (0.0, 30.0):
        d = np.array([np.sin(np.radians(ang)), 0, np.cos(np.radians(ang))])
        lit = lk._DepthMap(V, F, d).lit(floor, n)
        # exact: the ray from p toward the light meets the tile's plane at p + 0.02 * d / d_z
        hit = floor[:, :2] + 0.02 * d[:2] / d[2]
        shadowed = (np.abs(hit) < 0.01).all(1)
        margin = (np.abs(np.abs(hit) - 0.01) > 0.0015).all(1)   # (the edges: a map pixel + the bias either way)
        assert (lit[margin] != shadowed[margin]).all(), ang
        assert shadowed.sum() > 50


def test_soft_light_disc_directions():
    d = np.array([0.2, -0.5, 0.8])
    ds = lk._light_disc(d, 10.0)
    assert len(ds) == lk.SOFT_N
    cos = np.array(ds) @ (d / np.linalg.norm(d))
    assert (cos > np.cos(np.radians(10.5))).all() and cos.min() < np.cos(np.radians(5))
    assert len(lk._light_disc(d, 0.0)) == 1


def test_ambient_occlusion_matches_the_open_sky():
    # a 60 x 60 mm tile 10 mm over a wide floor: under its centre the open sky is the cone outside the tile's
    # solid angle; cosine-weighted, a disc of half-angle a hides sin(a)^2 (the square hides a little more)
    Vf, Ff = _grid(81, 0.3, 0.0)
    Vt, Ft = _grid(13, 0.03, 0.01)
    V, F, nf = np.r_[Vf, Vt], np.r_[Ff, Ft + len(Vf)], len(Vf)
    mesh = {"V": V, "F": F, "eyes": []}
    ao = lk.ambient_occlusion(mesh, n_dirs=96)
    floor = V[:nf]
    under = (np.abs(floor[:, :2]) < 0.004).all(1)
    open_ = (np.abs(floor[:, :2]) > 0.2).any(1)
    hidden = np.sin(np.arctan(3.0)) ** 2   # the inscribed disc: 0.9
    assert 0.02 < ao[:nf][under].mean() < 1 - hidden + 0.03
    assert ao[:nf][open_].mean() > 0.97
    assert "_ao" in mesh
