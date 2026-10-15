"""The hairline finds the EAR on the head (hair.ear), and the measures look_hair reports against a reference picture
(hair.outline_measure, hair.colour_bands). No Blender. `uv run pytest tests/test_hair_ear.py`.

What these hold (tesshair6, 2026-10-12): hairline() guessed the ear's top at the outer brow + 4 mm; on ten heads of
three bases the real ear was 0.7 - 3.2 cm lower, so the line ran that far above the ear (the "shaved temple" of tied
hair, sideburns that ended over the ear's top) and round five patched Tess's model by hand. Now:
- the ear is the bump on the scalp's rays, wherever it sits; a head without one keeps the old rule;
- the line passes `ear` m over the found ear's top, never onto the ear (a negative `ear`, the old patch, is raised);
- the sideburn hangs `sideburns` m below the ear's top in front of the ear;
- ear_from "brow" keeps a groom's old line exactly; explicit `points` are untouched."""

import numpy as np

from hifipushie import hair

LM = {"lm_brow_mid.L": [0.03, -0.09, 1.6], "lm_nose_base": [0.0, -0.1, 1.55], "lm_jaw_0.L": [0.075, -0.01, 1.57],
      "lm_brow_outer.L": [0.05, -0.08, 1.6], "lm_nose_bridge": [0.0, -0.095, 1.6]}


def _head(ear_top=-0.03, ear_h=0.055, lm=True):
    """A 9 cm ball with an ear 1.2 cm proud of each side: az 88..108, its top `ear_top` m from the centre's height."""
    C = np.array([0.0, 0.0, 1.6])
    sc = hair.Scalp(C, None, dict(LM) if lm else {})
    sc.R = np.full((len(sc.A), len(sc.E)), 0.09)
    if ear_top is not None:
        AA, EE = np.meshgrid(sc.A, sc.E, indexing="ij")
        z = 0.09 * np.sin(np.radians(EE))
        fa = np.abs(((AA + 180) % 360) - 180)
        sc.R = sc.R + 0.012 * ((fa >= 88) & (fa <= 108) & (z <= ear_top) & (z >= ear_top - ear_h))
    return sc


def _z(sc, line, az):
    return float(sc.point(float(az), float(hair._line_at(line, az)), 0.0)[2] - sc.C[2])


def test_the_ear_is_found_where_it_is():
    for top in (-0.012, -0.03, -0.045):
        sc = _head(top)
        e = hair.ear(sc)
        assert e is not None
        assert abs(e["top"] - sc.C[2] - top) < 0.004, (top, e["top"] - sc.C[2])
        assert 85 <= e["front"] <= 89 and 107 <= e["back"] <= 111, (e["front"], e["back"])
        assert e["top"] - e["lobe"] > 0.04
    assert hair.ear(_head(None)) is None  # a ball: no ear, the old rule


def test_the_hairline_passes_just_over_the_found_ear():
    g = hair._merge(hair.GROOM, {})
    for top in (-0.012, -0.03, -0.045):
        sc = _head(top)
        line = hair.hairline(sc, g)
        over = [_z(sc, line, a) - top for a in (92, 98, 104)]
        assert all(0.002 < o < 0.012 for o in over), (top, over)  # default: EAR_OVER above the top, whatever its height
        assert _z(sc, hair.hairline(sc, g), 262) - top < 0.012  # the right ear alike
    # the old guess stood wherever the brow was: 3 cm over a low ear
    sc = _head(-0.045)
    old = hair.hairline(sc, hair._merge(hair.GROOM, {"hairline": {"ear_from": "brow"}}))
    assert _z(sc, old, 98) - (-0.045) > 0.03
    sc0 = _head(None)  # no ear found: the line is the old one, whatever ear_from says
    assert np.allclose(hair.hairline(sc0, g), hair.hairline(sc0, hair._merge(hair.GROOM, {"hairline": {"ear_from": "brow"}})))


def test_overrides_still_work_and_never_root_on_the_ear():
    sc = _head(-0.03)
    z = lambda hl: _z(sc, hair.hairline(sc, hair._merge(hair.GROOM, {"hairline": hl})), 98) + 0.03  # noqa: E731
    assert z({"ear": 0.02}) > z({}) + 0.008  # more clearance
    assert 0.0 < z({"ear": -0.03}) < 0.006  # an old negative patch: raised to EAR_CLEAR, not into the ear
    # sideburns: m below the ear's top, in front of the ear
    sb = lambda hl: min(_z(sc, hair.hairline(sc, hair._merge(hair.GROOM, {"hairline": hl})), a) for a in np.arange(70, 88, 0.5)) + 0.03  # noqa: E731
    assert -0.02 < sb({}) < -0.008  # default SIDEBURNS
    assert sb({"sideburns": 0.03}) < sb({}) - 0.01
    assert sb({"sideburns": 0.0}) > sb({}) + 0.008
    # explicit points are the line
    pts = [[0, 1.66], [60, 1.64], [100, 1.61], [180, 1.56]]
    line = hair.hairline(sc, hair._merge(hair.GROOM, {"hairline": {"points": pts}}))
    assert abs(_z(sc, line, 100) - 0.01) < 0.004


def test_nape_v_brings_the_nape_centre_down_to_a_point():
    """hairline.nape_v: the nape line's centre comes down below its sides (a rounded point); 0 keeps the old line."""
    sc = _head(-0.03)
    z = lambda hl, a: _z(sc, hair.hairline(sc, hair._merge(hair.GROOM, {"hairline": hl})), a)  # noqa: E731
    assert abs(z({"nape_v": 0.0}, 180) - z({}, 180)) < 1e-9
    v = 0.02
    # (on the test ball the nape sits near the scalp grid's bottom row, which caps how far the centre can go down)
    assert z({"nape_v": v}, 180) < z({}, 180) - 0.002  # the centre lower
    assert z({"nape_v": v}, 150) > z({}, 150) + 0.004  # the sides higher
    assert z({"nape_v": v}, 180) < z({"nape_v": v}, 165) < z({"nape_v": v}, 150)


def test_a_head_without_landmarks_uses_its_ear_only_on_a_human_base():
    sc = _head(-0.02, lm=False)
    g = hair._merge(hair.GROOM, {})
    creature = hair.hairline(sc, g)
    sc.human = True
    human = hair.hairline(sc, g)
    assert abs(_z(sc, human, 98) - (-0.02) - 0.01) < 0.006  # over the found ear
    assert _z(sc, creature, 98) > _z(sc, human, 98) + 0.01  # the elevations' 18 deg: far above it
    explicit = hair.hairline(sc, hair._merge(hair.GROOM, {"hairline": {"ear_el": 30}}))
    assert _z(sc, explicit, 98) > _z(sc, human, 98) + 0.02  # explicit elevations win


def test_outline_measure_reads_a_tail():
    n = 200
    ref = np.zeros((n, n), bool)
    ref[40:100, 60:140] = True  # the head's hair
    ref[100:180, 110:150] = True  # a tail 80 px long, 40 wide, under a tie at (130, 100)
    ours = ref.copy()
    m = hair.outline_measure(ours, ref, 1.0, tie=[130, 100])
    assert m["iou"] > 0.97 and abs(m["below"]) < 0.03
    assert abs(m["hers"]["length_mm"] - 79) < 3 and abs(m["hers"]["width_mm"] - 40) < 2
    big = ref.copy()
    big[100:200, 100:160] = True  # longer and wider
    m = hair.outline_measure(big, ref, 2.0, tie=[130, 100])
    assert m["below"] > 0.6 and m["ours"]["length_mm"] > m["hers"]["length_mm"] + 30
    assert m["ours"]["width_mm"] > m["hers"]["width_mm"] + 30 and m["iou"] < 0.85 and m["chamfer_mm"] > 1
    assert "below" not in hair.outline_measure(ours, ref, 1.0)


def test_colour_bands_tell_dark_from_light_and_grey_from_brown():
    rng = np.random.default_rng(0)
    m = np.ones((40, 40), bool)
    brown = np.clip(np.array([90, 60, 40])[None, None] * rng.uniform(0.5, 1.5, (40, 40, 1)), 0, 255)
    grey = np.clip(np.array([60, 60, 60])[None, None] * rng.uniform(0.5, 1.5, (40, 40, 1)), 0, 255)
    b, g = hair.colour_bands(brown, m), hair.colour_bands(grey, m)
    assert b["mean"]["chroma"] > 10 > 2 > g["mean"]["chroma"]
    assert 40 < b["mean"]["hue"] < 80
    assert b["shadow"]["L"] < b["mid"]["L"] < b["highlight"]["L"]
    assert hair.colour_bands(brown, np.zeros((40, 40), bool)) == {}


def test_colour_variation_tells_flat_from_streaked():
    """tesshair7 (Joe: "one flat brown"): colour_variation puts numbers on strand / ribbon contrast and on the share
    of light ribbons, so a look is matched to a picture by measure."""
    rng = np.random.default_rng(1)
    n = 240
    m = np.ones((n, n), bool)
    flat = np.tile(np.array([70.0, 50.0, 38.0]), (n, n, 1)) * rng.uniform(0.97, 1.03, (n, n, 1))
    streak = flat.copy()
    for x in range(10, n, 30):  # light warm ribbons 6 px (3 mm at 0.5 mm / px) wide
        streak[:, x:x + 6] *= [1.9, 1.8, 1.6]
    vf, vs = hair.colour_variation(flat, m, 0.5), hair.colour_variation(np.clip(streak, 0, 255), m, 0.5)
    assert vs["ribbon_sd"] > vf["ribbon_sd"] + 3 and vs["L_sd"] > vf["L_sd"] + 3
    assert vf["ribbons"]["share"] < 0.01 and 0.1 < vs["ribbons"]["share"] < 0.35 and vs["ribbons"]["contrast"] > 5
    assert vs["hue_sd"] >= vf["hue_sd"]
    b = hair.colour_bands(np.clip(streak, 0, 255), m, 0.5)
    assert "variation" in b and "mean" in b and "variation" not in hair.colour_bands(streak, m)
    assert hair.colour_variation(flat, np.zeros((n, n), bool), 0.5) == {}
