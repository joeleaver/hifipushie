"""R3e (C496): the cap's ease flattened at its rest length (flatten.flatten(rest=...), cut_ease.py); the closure's
fastening marks where the closed fronts cross the centre line (cut_tapes.closure_marks)."""
import numpy as np

from hifipushie import cut_tapes
from hifipushie.flatten import flatten


def _grid(nx=21, nz=11, w=0.2, h=0.1, x0=0.0):
    x, z = np.meshgrid(np.linspace(x0, x0 + w, nx), np.linspace(0, h, nz), indexing="ij")
    V = np.c_[x.ravel(), np.zeros(x.size), z.ravel()]
    idx = np.arange(x.size).reshape(nx, nz)
    F = np.r_[np.c_[idx[:-1, :-1].ravel(), idx[1:, :-1].ravel(), idx[1:, 1:].ravel()],
              np.c_[idx[:-1, :-1].ravel(), idx[1:, 1:].ravel(), idx[:-1, 1:].ravel()]]
    return V, F


def test_eased_band_flattens_longer_by_its_ease():
    V, F = _grid()
    U0 = flatten(V, F)[0]
    e = 0.075
    U, S, _ = flatten(V, F, rest=lambda Vc, Fc: (np.tile([1.0, 0, 0], (len(Fc), 1)), np.full(len(Fc), e)))
    w0, w1 = np.ptp(U0[:, 0]) if np.ptp(U0[:, 0]) > np.ptp(U0[:, 1]) else np.ptp(U0[:, 1]), max(np.ptp(U, axis=0))
    assert abs(w1 / w0 - (1 + e)) < 0.005  # (the cloth's rest length along the seam: the toile's x (1 + ease))
    assert np.abs(S - 1).max() < 1e-3  # (against its rest shape the flat is unstrained)


def test_closure_marks_on_both_fronts_at_the_centre_line():
    Vo, Fo = _grid(x0=-0.03)          # the over front runs 3 cm past the centre line
    Vu, Fu = _grid(x0=-0.17)          # the under front's mirror side
    pcs = {}
    for p, (V, F) in (("front.L", (Vo, Fo)), ("front.R", (Vu, Fu))):
        pcs[p] = {"V": V, "U": V[:, [0, 2]] + 1.0, "F": F}
    B = {"pieces": {p: {"marks": {}} for p in pcs},
         "closures": [{"name": "front_closure", "over": "front.L", "under": "front.R", "edge": {}}]}
    why = cut_tapes.closure_marks(B, pcs, {"wear": "closed", "buttons_z": [0.04, 0.07]}, {})
    assert not why
    assert B["closures"][0]["pairs"] == [["button1", "buttonhole1"], ["button2", "buttonhole2"]]
    assert np.allclose(B["pieces"]["front.L"]["marks"]["button1"], [1.0, 1.07], atol=1e-6)
    assert np.allclose(B["pieces"]["front.R"]["marks"]["buttonhole2"], [1.0, 1.04], atol=1e-6)
