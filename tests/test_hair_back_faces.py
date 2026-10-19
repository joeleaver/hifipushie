"""Hair cards export each card's back face as its own triangles (c6): reversed winding, the same outward normal, the
cap single; layers stay contiguous ranges; the material is single-sided."""
import numpy as np

from hifipushie import hair


def test_back_faces():
    P = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0], [1, 1, 0]], float)
    T = np.array([[0, 1, 2], [1, 3, 2], [0, 1, 3]])
    lay = np.array([-1, 0, 1])
    N = np.tile([0.0, 0.0, 1.0], (9, 1))
    UV = np.arange(18, dtype=float).reshape(9, 2)
    T2, (N2, UV2) = hair.back_faces(T, lay, (N, UV))
    assert len(T2) == 5 and (T2[0] == T[0]).all()  # cap: one face
    assert (T2[1] == T[1]).all() and (T2[2] == T[1][::-1]).all()  # card: front, then its back
    assert (T2[3] == T[2]).all() and (T2[4] == T[2][::-1]).all()
    g = np.cross(P[T2[:, 1]] - P[T2[:, 0]], P[T2[:, 2]] - P[T2[:, 0]])[:, 2]
    assert (np.sign(g[1:]) == [1, -1, 1, -1]).all()  # the back is wound the other way ...
    assert (N2 == [0, 0, 1]).all()  # ... with the same (outward) normal
    assert (UV2.reshape(-1, 3, 2)[2] == UV.reshape(-1, 3, 2)[1][::-1]).all()  # its corners' attributes follow
    lay2 = lay[[0, 1, 1, 2, 2]]
    assert [int(np.nonzero(lay2 == k)[0][0]) for k in (-1, 0, 1)] == [0, 1, 3]


def test_single_sided_material():
    assert hair.BACK_FACES == 1
    assert "not doubleSided" in hair.CARD_RECIPE_FACES and hair.CARD_RECIPE_FACES != hair.CARD_RECIPE


if __name__ == "__main__":
    test_back_faces()
    test_single_sided_material()
    print("ok")
