"""The upper lid's fold in GNM's parameters (gnm_fold): what can be formed, at what cost, and what cannot."""
import numpy as np
import pytest

from hifipushie import gnm_controls as gcm, gnm_fold as gf

pytestmark = pytest.mark.skipif(not gcm.DATA.exists(), reason="gnm_controls.npz not built")


def test_rings_and_template_read():
    ch = gf.chains(7.0)
    assert ch.shape[1] == gf.NR + 1 and len(ch) >= 6
    t = gf.topo()
    assert (t["ring"][ch] == np.arange(gf.NR + 1)).all()
    q = gf.read(gf.vertices())
    assert q["hang_max"] == 0.0                     # GNM's template has no overhang
    assert 10 < q["turn_mean"] < 25


def test_overhang_direction_is_the_brow_coming_down():
    d = gf.hood_direction(5)
    assert 0.4 < d["per_unit"] < 0.8                # mm of overhang per unit |c|
    assert 2.0 < d["sd_to_overhang"] < 3.5          # the template's spacing is that many sd from reversing
    assert d["corr_brow"] < -0.85 and d["brow"] < -1.5
    V = gf.vertices(4.5 * d["dc"])
    assert gf.read(V)["hang_mean"] > 0.3


def test_the_basis_spans_a_designed_fold_only_with_nothing_held():
    r = gf.fold(np.zeros(170), free=True)
    assert r["residual"] < 0.2 and r["after"]["hang_mean"] > 0.8     # spanned ...
    assert r["dc"] > 100                                              # ... by enormous coefficients


def test_crisp_fold_at_a_chosen_height():
    r = gf.fold(np.zeros(170), crease=4.7)
    a = r["after"]
    assert a["turn_mean"] > 40 and 3.3 < a["h_mean"] < 5.2            # the population's largest at >= 4 mm is ~36 deg
    assert a["hang_max"] < 0.1                                        # no overhang survives the hold
    assert r["dc"] < 18 and r["held_rms"] < 0.7


def test_overhang_costs_the_brow():
    r = gf.fold(np.zeros(170), crease=4.7, overhang=0.5)
    assert r["after"]["hang_mean"] > 0.4
    assert r["brow_drop"] > 2.5                                       # the brow comes down: hooding
    tight = gf.fold(np.zeros(170), crease=4.7, overhang=0.5, brow=0.3)
    assert tight["dc"] > 1.3 * r["dc"]                                # holding the brow makes it far dearer
    assert "overhang" in gf.fold_text(r)
