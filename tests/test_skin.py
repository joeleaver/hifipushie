"""Skin: the tone model, zones, the layers a description expands into, the new paint generators (spot, tile) and
the measurements. `uv run python tests/test_skin.py` (no Blender, no asset packs: a hand-made skeleton stands in for
a base body's joints and landmarks)."""
import colorsys

import numpy as np

from hifipushie import paint, skin, skin_measure, skin_swatch
from hifipushie.spec import SpecError

LM = {"lm_nose_bridge": [0, -0.156, 1.644], "lm_nose_tip": [0, -0.185, 1.591], "lm_nose_base": [0, -0.172, 1.572],
      "lm_chin": [0, -0.158, 1.493], "lm_lip_upper": [0, -0.178, 1.553], "lm_lip_lower": [0, -0.176, 1.533],
      "lm_lip_seam": [0, -0.175, 1.543], "lm_lip_inner_upper": [0, -0.175, 1.543], "lm_lip_inner_lower": [0, -0.175, 1.543],
      "lm_brow_inner.L": [0.014, -0.158, 1.659], "lm_brow_mid.L": [0.046, -0.154, 1.67], "lm_brow_outer.L": [0.08, -0.128, 1.655],
      "lm_eye_inner.L": [0.026, -0.145, 1.633], "lm_eye_outer.L": [0.062, -0.136, 1.636], "lm_lid_upper.L": [0.045, -0.148, 1.644],
      "lm_lid_lower.L": [0.045, -0.146, 1.632], "lm_nostril.L": [0.024, -0.16, 1.572], "lm_mouth_corner.L": [0.036, -0.155, 1.539],
      "lm_lip_peak.L": [0.014, -0.175, 1.553], "lm_lip_upper_side.L": [0.026, -0.167, 1.545],
      "lm_lip_lower_side.L": [0.026, -0.162, 1.535], "lm_lip_lower_mid.L": [0.016, -0.171, 1.533],
      "lm_lip_inner_upper.L": [0.018, -0.169, 1.542], "lm_lip_inner_lower.L": [0.018, -0.169, 1.543],
      "eye_front.L": [0.043, -0.148, 1.64], "head": [0, -0.045, 1.654], "neck": [0, -0.011, 1.5],
      **{f"lm_jaw_{k}.L": [0.106 - 0.012 * k, -0.05 - 0.014 * k, 1.615 - 0.018 * k] for k in range(8)}}


def head_spec(**sk) -> dict:
    return {"symmetry": True, "joints": {k: {"pos": v, "r": 0.06 if k in ("head", "neck") else 0.005} for k, v in LM.items()},
            "bones": {}, "blobs": {"skull": {"at": "head", "size": [0.09, 0.115, 0.125]}}, "skin": sk}


def test_tone():
    hsv = [colorsys.rgb_to_hsv(*skin.tone_rgb({"fitzpatrick": f})) for f in range(1, 7)]
    assert all(a[2] > b[2] for a, b in zip(hsv, hsv[1:])), "more melanin is darker"
    assert 0.75 < hsv[0][2] < 0.9 and 0.25 < hsv[5][2] < 0.45, [h[2] for h in hsv]  # inside the PBR albedo range
    assert all(10 < h[0] * 360 < 35 for h in hsv), "skin hues stay orange-red"
    for f in (1, 3, 6):  # more blood is redder (lower hue, more a*) on every tone; lips redder than cheeks
        t = {"fitzpatrick": f}
        a = [-colorsys.rgb_to_hsv(*skin.tone_rgb(t, blood=b))[0] for b in (0.5, 1, 2, 4)]
        assert all(x < y for x, y in zip(a, a[1:])), a
        palm = colorsys.rgb_to_hsv(*skin.tone_rgb(t, melanin=0.25))[2]
        assert palm >= colorsys.rgb_to_hsv(*skin.tone_rgb(t))[2]
    warm, cool = skin.tone_rgb({"melanin": 0.3, "undertone": 1}), skin.tone_rgb({"melanin": 0.3, "undertone": -1})
    assert colorsys.rgb_to_hsv(*warm)[0] > colorsys.rgb_to_hsv(*cool)[0], "warm undertone is yellower"
    try:
        skin.tone_params({"fitzpatrick": 9})
        assert False
    except SpecError:
        pass


def test_zones_and_layers():
    spec = head_spec(tone={"fitzpatrick": 5}, age=30)
    names = skin.zone_names()
    assert {"cheek", "cheek.L", "cheek.R", "forehead", "nose", "lips", "beard", "under_eye.L"} <= set(names)
    L = paint.layers(spec)
    assert all(k.startswith("skin:") for k in L) and "skin:midface_red" in L and "skin:micro_pores" in L
    assert '"zone"' not in str(L).replace("'", '"'), "zones expand to spots before anything else sees them"
    paint.validate(spec)
    # a zone is where it says: the left cheek spot holds the point under the left eye, not the right one
    from hifipushie.surface import Points
    J = skin._joints(spec)
    io = skin.interocular(J)
    pts = np.array([J["lm_lid_lower.L"] + io * np.array([0.12, 0.1, -0.6]), J["lm_lid_lower.R"] + io * np.array([-0.12, 0.1, -0.6]),
                    J["lm_nose_bridge"] + io * np.array([0, 0.2, 0.9])])
    P = Points(spec, pts, np.tile([0, -1.0, 0], (3, 1)), np.zeros(3, int), ["body"], 0.002)
    view = paint._View(P, np.arange(3))
    for z, want in (("cheek.L", [1, 0, 0]), ("cheek.R", [0, 1, 0]), ("cheek", [1, 1, 0]), ("forehead", [0, 0, 1])):
        ly = skin.expand_zones(spec, {"color": [1, 0, 0], "zone": z})
        m = paint.layer_mask(spec, "t", ly, view)
        assert (m > 0.5).astype(int).tolist() == want, (z, m)
    # the model's own paint can address zones, and sits over the skin's layers
    spec["paint"] = {"blush": {"color": "#d06060", "opacity": 0.4, "zone": "cheekbone"}}
    L = paint.layers(spec)
    assert list(L)[-1] == "blush" and "spot" in str(L["blush"])
    try:
        skin.expand_zones(spec, {"color": [1, 0, 0], "zone": "elbow.L"})
        assert False, "no arm joints here"
    except SpecError as e:
        assert "elbow" in str(e)
    try:
        paint.layers(head_spec(tone={"melanin": 0.2}, freckle=1))
        assert False
    except SpecError as e:
        assert "unknown keys" in str(e)
    # no skin: nothing changes for models without it
    plain = head_spec()
    del plain["skin"]
    assert paint.layers(plain) == {}


def test_description_drives_layers():
    def col(spec, name):
        return np.array(paint.layers(spec)[name]["color"])
    light, dark = head_spec(tone={"fitzpatrick": 1}), head_spec(tone={"fitzpatrick": 6})
    assert col(light, "skin:lips_lower").sum() > col(dark, "skin:lips_lower").sum()
    for s in (light, dark):  # lips and cheeks are redder than the base on any tone
        base = skin_measure.lab(np.array([[skin.part_base(s)[1]["color"]]]))[0, 0]
        for n in ("skin:lips_lower", "skin:midface_red"):
            assert skin_measure.lab(np.array([[col(s, n)]]))[0, 0, 1] > base[1], n
    flat = paint.layers(head_spec(tone={"fitzpatrick": 2}, variation=0, detail=0))
    assert "skin:midface_red" not in flat and "skin:micro_pores" not in flat and "skin:lips_lower" in flat
    b = skin.part_base(head_spec(tone={"fitzpatrick": 2}, oil=1.0))[1]
    assert b["subsurface"] > 0 and b["coat"] > skin.part_base(head_spec(tone={"fitzpatrick": 2}, oil=0.0))[1]["coat"]
    assert skin.part_base(head_spec(age=80))[1]["roughness"] > skin.part_base(head_spec(age=25))[1]["roughness"]


def test_spot_and_tile():
    s = {"c": np.array([[0, 0, 0.0], [0.1, 0, 0]]), "r": np.full((2, 3), 0.01), "soft": 0.5, "line": True}
    v = np.array([[0.05, 0, 0], [0.05, 0.004, 0], [0.05, 0.0075, 0], [0.05, 0.02, 0], [-0.02, 0, 0]])
    m = paint.spot_mask(s, v)
    assert m[0] == 1 and m[1] == 1 and 0 < m[2] < 1 and m[3] == 0 and m[4] == 0, m
    for kind in skin_swatch.KINDS:
        d = skin_swatch.depth(kind)
        assert d.shape == (skin_swatch.SIZE,) * 2 and 0 <= d.min() and d.max() == 1
        # periodic: the wrap seam is no rougher than the inside
        seam = np.abs(d[:, 0] - d[:, -1]).mean()
        inside = np.abs(d[:, 1:] - d[:, :-1]).mean()
        assert seam < 2.5 * inside, (kind, seam, inside)
    n = np.tile([0.0, -1.0, 0.0], (4, 1))
    p = np.array([[0.001, 0, 0.002], [0.001 + skin_swatch.PERIOD["pores"], 0, 0.002], [0.004, 0, 0.007], [0.0, 0, 0.0]])
    t = paint.tile_mask({"swatch": "pores", "vary": False}, p, n)
    assert abs(t[0] - t[1]) < 1e-6 and 0 <= t.min() and t.max() <= 1, t


def test_measure():
    rng = np.random.default_rng(0)
    flat = np.full((200, 200, 3), 180, np.uint8)
    flat[..., 1] = 140
    flat[..., 2] = 120
    noisy = np.clip(flat + rng.normal(0, 6, flat.shape), 0, 255).astype(np.uint8)
    a, b = skin_measure.bands(flat, 0.1), skin_measure.bands(noisy, 0.1)
    assert all((x or 0) < 1e-6 for x in a["L"]) and b["L"][0] > 0.1
    assert skin_measure.micro(noisy, 0.1) > 10 * (skin_measure.micro(flat, 0.1) + 1e-6)
    lit = np.tile(np.linspace(60, 220, 200)[None, :, None], (200, 1, 3)).astype(np.uint8)
    s = skin_measure.shadow_colour(lit.reshape(-1, 3))
    assert abs(s["chroma_over_L_lit"]) < 0.02 and s["L_lit"] > s["L_shadow"]


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
