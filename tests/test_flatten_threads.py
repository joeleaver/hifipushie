"""Flattening by the threads (flatten_threads.py, R3g C512): woven cloth keeps its warp and weft and shears freely to
the weave's jam; the measures split thread stretch from shear."""
import numpy as np

from hifipushie.flatten import flatten, strain
from hifipushie.flatten_threads import thread_strain, threads
from hifipushie.mark_split import areas


def _grid(nr, nc, f):
    V = np.array([f(i / (nr - 1), j / (nc - 1)) for i in range(nr) for j in range(nc)])
    F = []
    for i in range(nr - 1):
        for j in range(nc - 1):
            a = i * nc + j
            F += [[a, a + 1, a + nc + 1], [a, a + nc + 1, a + nc]]
    return V, np.array(F)


def _sphere_patch(half=0.6, n=30):
    """A patch of a 10 cm sphere (lat / lon +-half rad): doubly curved, no flat piece covers it unstretched."""
    R = 0.1
    return _grid(n, n, lambda u, v: R * np.array([np.cos(2 * half * u - half) * np.cos(2 * half * v),
                                                   np.cos(2 * half * u - half) * np.sin(2 * half * v),
                                                   np.sin(2 * half * u - half)]))


def _mean(x, V, F):
    ar = areas(V, F)
    return float((x * ar).sum() / ar.sum())


def test_bias_piece_takes_a_dome_by_shear_alone():
    V, F = _sphere_patch()
    U, S, Fk = flatten(V, F, grain=45.0)
    w, f, sh = threads(V, Fk, U, 45.0)
    assert _mean(thread_strain(w, f, sh), V, Fk) < 0.005  # threads ~unstretched
    assert np.abs(sh).max() > 5  # ... because the grid sheared
    Ui, Si, Fi = flatten(V, F, grain=None)  # the isotropic sheet counts that shear as strain
    assert _mean(strain(Si), V, Fi) > 0.02


def test_shear_past_the_jam_counts():
    V, F = _sphere_patch()
    U, S, Fk = flatten(V, F, grain=45.0)
    w, f, sh = threads(V, Fk, U, 45.0)
    free = _mean(thread_strain(w, f, sh, lim_deg=35.0), V, Fk)
    tight = _mean(thread_strain(w, f, sh, lim_deg=2.0), V, Fk)
    assert tight > free + 0.01


def test_measures_split_stretch_from_shear():
    V, F = _grid(6, 6, lambda u, v: np.array([0.1 * v, 0.1 * u, 0.0]))
    U = V[:, :2].copy()
    for M, (ew, ef, s) in ((np.diag([1.1, 1.0]), (0.10, 0.0, 0.0)),  # (grain 0: the warp along the flat's x)
                           (np.array([[1.0, np.sin(0.3)], [0.0, np.cos(0.3)]]), (0.0, 0.0, np.degrees(0.3)))):
        V3 = np.c_[U @ M.T, np.zeros(len(U))]
        w, f, sh = threads(V3, F, U, 0.0)
        assert np.allclose(w, ew, atol=1e-9) and np.allclose(f, ef, atol=1e-9) and np.allclose(np.abs(sh), s, atol=1e-6)


def test_a_stretch_along_a_thread_is_caught():
    V, F = _grid(10, 10, lambda u, v: np.array([0.1 * v, 0.1 * u, 0.0]))
    U = V[:, :2].copy()
    U[:, 0] = np.where(V[:, 0] > 0.05, 0.05 + (V[:, 0] - 0.05) / 1.08, V[:, 0])  # the flat 8 % short along x there
    w, f, sh = threads(V, F, U, 0.0)
    t = thread_strain(w, f, sh)
    assert t.max() > 0.07 and np.abs(sh).max() < 1e-6
