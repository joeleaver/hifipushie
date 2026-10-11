"""GNM's control atlas (gnm_controls), its sampler decoders (gnm_sampler) and the block-in's sculpt move."""
import numpy as np
import pytest

from hifipushie import gnm_controls as gcm

pytestmark = pytest.mark.skipif(not gcm.DATA.exists(), reason="gnm_controls.npz not built")


def test_zones_named_and_symmetric():
    Z = gcm.zones()
    assert set(Z) == set(gcm.ZONES)
    T = gcm.gnm()["T"]
    for k in ("alar_crease", "bridge_walls", "jowls", "nasolabial", "lid_fold", "vermilion_border_upper"):
        idx = Z[k]
        assert len(idx) >= 6, k
        x = T[idx, 0]
        assert (x > 0.002).sum() > 0 and (x < -0.002).sum() > 0, f"{k} has both sides"


def test_identity_field_is_the_basis():
    g = gcm.gnm()
    D = gcm.field("head_005")
    assert np.allclose(D, g["IB"][g["id_names"].index("head_005")], atol=1e-6)
    c, e, rot = gcm.coefficients("both_eye_region_003", 2.0)
    assert e[g["ex_names"].index("left_eye_region_003")] == 2.0 and e[g["ex_names"].index("right_eye_region_003")] == 2.0


def test_query_finds_the_feature():
    assert gcm.match_zones("alar crease") == ["alar_crease"]
    assert set(gcm.match_zones("lip border")) == {"vermilion_border_upper", "vermilion_border_lower"}
    r = gcm.query("jowl", top=5)
    assert r["zones"] == ["jowls"] and len(r["rows"]) == 5
    assert all(row["family"] in gcm.SHAPE_FAMILIES for row in r["rows"])
    d = gcm.describe("bridge_height")
    assert d["macros"]["bridge_height"] == pytest.approx(1.0, abs=0.05)   # a block-in macro moves its own measure 1 sd
    assert "sheet" in d and d["sheet"].startswith("gnm_atlas/")


def test_sampler_decoders():
    from hifipushie import gnm_sampler as S
    D = S.identity()
    lab = S.id_label("female", "white")
    z = np.random.default_rng(0).standard_normal(64)
    J = D.jac(z, lab)
    k, h = 11, 1e-4
    e = np.zeros(64)
    e[k] = h
    fd = (D(z + e, lab)[0] - D(z - e, lab)[0]) / (2 * h)
    assert np.allclose(fd, J[:, k], atol=1e-6)
    assert D(np.zeros(64), lab).shape == (1, 253)
    assert S.prototype("happy").shape == (383,)


def test_sculpt_holds_the_macros_and_moves_the_zone():
    sc = gcm.sculpt("bridge_walls", hold_zones=("dorsum",))
    dc = sc["dc"]
    assert gcm.zone_row("bridge_walls") @ dc == pytest.approx(1.0, abs=1e-6)
    assert gcm.zone_row("dorsum") @ dc == pytest.approx(0.0, abs=1e-6)
    MJ = gcm._macro_jac()
    assert np.abs(MJ @ dc).max() < 1e-6          # every macro held
    assert 1.0 < sc["cost"] < 6.0
    from hifipushie import blockin as bi
    assert np.allclose(bi.direction("sculpt:bridge_walls|hold=dorsum"), dc)
    assert np.allclose(bi.direction("gnm:head_007")[7], 1.0)
