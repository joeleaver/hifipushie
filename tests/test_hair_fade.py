"""hair_fade: the short hair's edge fade painted into the head's skin (sh7 / sh8)."""
import numpy as np

from hifipushie import hair_fade as hf
from hifipushie.hair import Scalp

C = np.array([0.0, 0.01, 1.62])
FADE = {"edge": [[0, -20.0], [180, -20.0]], "fade_mm": [[0, 20.0], [180, 20.0]], "fa_min": 55, "seed": 3}


def _scalp(az_term=0.0):
    A = np.arange(0.0, 360.0, Scalp.STEP)
    E = np.arange(Scalp.EL[0], Scalp.EL[1] + 1e-6, Scalp.STEP)
    R = 0.09 + 0.0002 * E[None, :] + az_term * np.cos(np.radians(A))[:, None] + 0 * A[:, None]
    return Scalp(C, R, {})


def _pt(az, el, r):
    a, e = np.radians(az), np.radians(el)
    return C + r * np.array([np.sin(a) * np.cos(e), -np.cos(a) * np.cos(e), np.sin(e)])


def test_skull_map_is_indexed_azimuth_then_elevation():
    """Known answer (sh7a blanked the nape: map_coordinates got the axes reversed): a skull whose radius grows with
    elevation only must read, on every column, the radius at that row's elevation; one that varies with azimuth only,
    the radius at that column's azimuth."""
    fm = hf.build(_scalp(), FADE)
    H, W = fm["skull"].shape
    el = hf.EL1 - (np.arange(H) + 0.5) * hf.RES
    want = 0.09 + 0.0002 * np.clip(el, Scalp.EL[0], Scalp.EL[1])
    for j in (0, W // 4, W // 2, W - 1):
        assert np.allclose(fm["skull"][:, j], want, atol=2e-6), j
    sc = _scalp(az_term=0.004)
    fm = hf.build(sc, FADE)
    Rs = hf.skull_radius(sc)
    az = (np.arange(W) + 0.5) * hf.RES
    i0 = int(np.argmin(np.abs(el - 10.0)))
    ie = (el[i0] - Scalp.EL[0]) / Scalp.STEP
    col = np.interp(ie, np.arange(Rs.shape[1]), np.arange(Rs.shape[1]))  # (row of the scalp grid)
    k0 = int(np.floor(col))
    ring = Rs[:, k0] + (col - k0) * (Rs[:, k0 + 1] - Rs[:, k0])
    want_az = np.interp(az, np.r_[sc.A, 360.0], np.r_[ring, ring[:1]])
    assert np.allclose(fm["skull"][i0], want_az, atol=2e-6)
    assert np.ptp(fm["skull"][i0]) > 0.004  # the azimuth term survived (not read along elevation)


def test_chart_coords_front_is_azimuth_zero_and_left_is_ninety():
    fm = {"rgba": np.zeros((1200, 3600, 4), np.float32), "skull": np.full((1200, 3600), 0.1), "el": [hf.EL0, hf.EL1],
          "C": list(C)}
    row, col, r = hf.chart_coords(fm, np.stack([_pt(0, 0, 0.09), _pt(90, 0, 0.09), _pt(180, -30, 0.08)]))
    assert np.allclose(col, [-0.5, 900 - 0.5, 1800 - 0.5], atol=1e-6)
    assert np.allclose(row, [450 - 0.5, 450 - 0.5, 750 - 0.5], atol=1e-6)
    assert np.allclose(r, [0.09, 0.09, 0.08])


def test_sample_reads_the_texel_under_the_point_and_never_the_ear():
    rgba = np.zeros((1200, 3600, 4), np.float32)
    rgba[700:760, 1750:1850] = [0.2, 0.4, 0.6, 1.0]  # el -25..-31, az 175..185 (the nape)
    fm = {"rgba": rgba, "skull": np.full((1200, 3600), 0.09), "el": [hf.EL0, hf.EL1], "C": list(C)}
    s = hf.sample(fm, np.stack([_pt(180, -28, 0.089), _pt(180, -28, 0.09 + hf.EAR_CLEAR + 0.001), _pt(90, -28, 0.089),
                                _pt(180, -80, 0.089)]))
    assert np.allclose(s[0], [0.2, 0.4, 0.6, 1.0], atol=1e-5)
    assert s[1, 3] == 0 and s[2, 3] == 0 and s[3, 3] == 0  # off the skull (ear), elsewhere, off the map's span


def test_sample_wraps_round_the_front():
    rgba = np.zeros((1200, 3600, 4), np.float32)
    rgba[:, 0] = rgba[:, -1] = [1, 1, 1, 1]
    fm = {"rgba": rgba, "skull": np.full((1200, 3600), 0.09), "el": [hf.EL0, hf.EL1], "C": list(C)}
    s = hf.sample(fm, np.stack([_pt(0.0, 0, 0.08), _pt(359.99, 0, 0.08)]))
    assert np.allclose(s[:, 3], 1.0, atol=1e-3)


def test_bake_into_mixes_in_linear_light():
    rgba = np.zeros((1200, 3600, 4), np.float32)
    rgba[700:760, 1750:1850] = [0.5, 0.5, 0.5, 1.0]
    fm = {"rgba": rgba, "skull": np.full((1200, 3600), 0.09), "el": [hf.EL0, hf.EL1], "C": list(C)}
    lin = np.array([[0.6, 0.4, 0.3], [0.6, 0.4, 0.3]])
    new, a = hf.bake_into(lin, np.stack([_pt(180, -28, 0.089), _pt(90, 0, 0.089)]), fm)
    assert np.allclose(new[0], 0.21404, atol=1e-4) and a[0] == 1.0  # sRGB 0.5 decoded
    assert np.allclose(new[1], lin[1]) and a[1] == 0.0


def test_density_is_half_at_the_edge_and_none_at_the_face():
    fm = hf.build(_scalp(), FADE)
    W = fm["density"].shape[1]
    row = int(round((hf.EL1 - (-20.0)) / hf.RES - 0.5))
    assert abs(float(fm["density"][row, W // 2]) - 0.5) < 0.03
    assert float(fm["density"][:, :int(40 / hf.RES)].max()) == 0.0  # 0..40 deg from the front: never painted
    assert float(fm["density"][int(10 / hf.RES), W // 2]) > 0.99  # well above the edge: full (under the cap)
    assert fm["hairs"] > 1000


def test_surface_mm_measures_the_fade_on_the_skin_not_a_sphere():
    """(sh8) down the neck the radius grows as elevation falls: a fade of N mm measured on the skin ends nearer the edge
    (in elevation) than one measured on the median sphere (sh8a's nape ran ~6 cm down the neck as streaks)."""
    A = np.arange(0.0, 360.0, Scalp.STEP)
    E = np.arange(Scalp.EL[0], Scalp.EL[1] + 1e-6, Scalp.STEP)
    R = 0.09 + 0.002 * np.clip(-20.0 - E, 0, None)[None, :] + 0 * A[:, None]  # the neck flares below el -20
    sc = Scalp(C, R, {})
    o = {**FADE, "edge": [[0, -30.0], [180, -30.0]], "fade_mm": [[0, 30.0], [180, 30.0]]}
    a = hf.build(sc, o)["density"][:, 1800]
    b = hf.build(sc, {**o, "surface_mm": True})["density"][:, 1800]
    el = hf.EL1 - (np.arange(len(a)) + 0.5) * hf.RES
    assert el[a > 0.01].min() < el[b > 0.01].min() - 3.0
    row = int(round((hf.EL1 + 30.0) / hf.RES - 0.5))
    assert abs(float(b[row]) - 0.5) < 0.03  # still half at the edge


def test_trim_mask_cuts_below_the_line_and_breakup_keeps_far_rows():
    o = {"trim": [[0, -30.0], [180, -30.0]], "trim_soft_mm": 4.0}
    el = 90.0 - (np.arange(400) + 0.5) * 0.4
    m = hf.trim_mask(o, 0.09, el, 360)
    assert m.shape == (400, 360)
    assert m[el > -25].min() == 1.0 and m[el < -31].max() == 0.0
    mb = hf.trim_mask({**o, "trim_breakup_mm": 3.0, "seed": 1}, 0.09, el, 360)
    assert mb[el > 0].min() == 1.0 and mb[el < -50].max() == 0.0
    near = (el > -34) & (el < -26)
    assert np.abs(mb[near] - m[near]).max() > 0.2  # the edge moved: ragged, not ruled
    assert hf.trim_mask({}, 0.09, el, 360) is None
