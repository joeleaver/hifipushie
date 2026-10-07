"""flipfit (2026-10-07, Garrett's 20k export: a 14 mm edge from the left upper lid's fold up to the brow, its two
triangles 68 deg apart: a dark crease up the lid in every blink): an edge lying ACROSS a smooth bend is turned to
lie along it; a modelled crease (both triangles already on the surface) is left alone."""
import numpy as np

from hifipushie import flipfit


def _ridge(n=41, w=0.02):
    """A dense reference: a ridge along x, z = -30 y^2 (a lid's fold seen as a cylinder)."""
    s = np.linspace(-w, w, n)
    V = np.array([[x, y, -30.0 * y * y] for y in s for x in s])
    T = []
    for j in range(n - 1):
        for i in range(n - 1):
            a, b, c, d = j * n + i, j * n + i + 1, (j + 1) * n + i, (j + 1) * n + i + 1
            T += [[a, b, d], [a, d, c]]
    return V, np.array(T)


def test_edge_across_a_ridge_is_turned_along_it():
    RV, RT = _ridge()
    near = flipfit.mesh_nearest(RV, RT)
    y = 0.015
    # four low-poly vertices on the surface: two on the ridge's top (along it), two down its sides
    V = np.array([[-0.005, 0, 0], [0.005, 0, 0], [0, -y, -30 * y * y], [0, y, -30 * y * y]])
    across = np.array([[2, 3, 0], [3, 2, 1]])  # diagonal 2-3 runs over the ridge: two tents tilted sideways
    across = np.array([t if np.cross(V[t[1]] - V[t[0]], V[t[2]] - V[t[0]])[2] > 0 else t[[0, 2, 1]] for t in across])
    assert len(flipfit.sharp_misfits(V, across, near, sharp=0.99)) == 1
    T2, k = flipfit.flip_to_fit(V, across, near, sharp=0.99)
    assert k == 1
    assert sorted(set(T2[0]) & set(T2[1])) == [0, 1]  # the shared edge is now the ridge's top
    assert len(flipfit.sharp_misfits(V, T2, near, sharp=0.99)) == 0
    # every new triangle faces up like the old ones
    n = np.cross(V[T2[:, 1]] - V[T2[:, 0]], V[T2[:, 2]] - V[T2[:, 0]])
    assert (n[:, 2] > 0).all()


def test_modelled_crease_is_left_alone():
    # two faces of a box meeting at 90 deg, the reference the same box: nothing disagrees, nothing turns
    V = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0], [1, 1, 0], [0, 1, -1], [1, 1, -1]], float)
    T = np.array([[0, 1, 3], [0, 3, 2], [2, 3, 5], [2, 5, 4]])
    T2, k = flipfit.flip_to_fit(V, T, flipfit.mesh_nearest(V, T))
    assert k == 0 and (T2 == T).all()
