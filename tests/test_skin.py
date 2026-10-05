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
      "eye_front.L": [0.043, -0.148, 1.64], "eye.L": [0.043, -0.136, 1.64], "head": [0, -0.045, 1.654], "neck": [0, -0.011, 1.5],
      **{f"lm_jaw_{k}.L": [0.106 - 0.012 * k, -0.05 - 0.014 * k, 1.615 - 0.018 * k] for k in range(8)}}


def head_spec(**sk) -> dict:
    return {"symmetry": True, "joints": {k: {"pos": v, "r": 0.06 if k in ("head", "neck") else 0.005} for k, v in LM.items()},
            "bones": {}, "blobs": {"skull": {"at": "head", "size": [0.09, 0.115, 0.125]},
                               "eye.L": {"at": "eye.L", "size": [0.012, 0.012, 0.012]}}, "skin": sk}


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


FULL = dict(tone={"fitzpatrick": 3}, age=60, sun=0.6,
            features={"freckles": 0.6, "moles": {"amount": 0.5, "at": ["lm_chin"]}, "blemishes": 0.4, "flush": 0.3, "sunburn": 0.2,
                      "tan": {"amount": 0.3, "mask": [{"zone": "forehead"}]}},
            hair={"stubble": 0.7, "brows": {"density": 0.9}},
            scars=[{"kind": "cut", "path": [{"at": "lm_brow_outer.L", "offset": [0, -0.005, 0.01]}, "lm_eye_outer.L"]},
                   {"kind": "surgical", "path": ["lm_jaw_3.L", "lm_jaw_5.L"], "age": 0.4}, {"kind": "keloid", "at": "lm_chin", "radius": 0.006},
                   {"kind": "burn", "zone": "cheek_side.R"}, {"kind": "pockmarks", "zone": "cheek.R"}],
            makeup={"foundation": {"amount": 0.5, "finish": "matte"}, "blush": 0.5, "contour": 0.4, "highlight": 0.5, "concealer": 0.4,
                    "eyeshadow": {"color": "#553322", "finish": "metallic"}, "eyeliner": {"wing": 0.005}, "mascara": 1, "brows": 0.4,
                    "lipstick": {"color": "#a01030", "finish": "gloss"}})


def _gens(e, found):
    for k, v in e.items():
        if k in ("noise", "cells"):
            found.add(k)
        if k == "mask":
            for sub in v:
                _gens(sub, found)


def test_features_and_shader_budget(tmp=None):
    import os
    import tempfile
    from hifipushie import store
    with tempfile.TemporaryDirectory() as d:  # the brow picture and swatches go to the image store
        home, store.HOME = store.HOME, __import__("pathlib").Path(d)
        try:
            spec = head_spec(**FULL)
            L = paint.layers(spec)
            paint.validate(spec)
            pre = {k for k, v in L.items() if v.get("_pre")}
            fine = {k: v for k, v in L.items() if not v.get("_pre")}
            for want in ("skin:freckles", "skin:brow_hairs", "skin:stubble", "skin:wrinkle_forehead", "skin:scar0_cut",
                         "skin:scar1_surgical_stitches", "skin:makeup_eyeliner", "skin:micro_pores"):
                assert want in fine, want
            for want in ("skin:midface_red", "skin:lips_lower", "skin:stubble_shadow", "skin:makeup_foundation", "skin:makeup_lipstick",
                         "skin:flush", "skin:tan"):
                assert want in pre, want
            # what a renderer's shader must hold stays small, and none of it is procedural noise: swatches, images, spots
            assert sum(1 for v in fine.values() if v.get("part", "body") == "body") <= 36, len(fine)
            for k, v in fine.items():
                found = set()
                _gens({kk: vv for kk, vv in v.items() if kk == "mask"}, found)
                per_pixel = set()
                for e in v.get("mask") or []:
                    if not e.get("vertex"):
                        _gens(e, per_pixel)
                assert not per_pixel, (k, per_pixel)
            assert all("height" not in L[k] for k in pre), "a per-vertex layer can't carry relief"
            assert L["skin:makeup_lipstick"]["roughness"] < 0.2 and L["skin:makeup_eyeshadow"]["metallic"] > 0.5
            assert L["skin:freckles"]["opacity"] < paint.layers(head_spec(**{**FULL, "makeup": {}}))["skin:freckles"]["opacity"], \
                "foundation hides the marks under it"
            young = paint.layers(head_spec(tone={"fitzpatrick": 3}, age=18))
            assert "skin:wrinkle_forehead" not in young and "skin:wrinkle_crepe" not in young and "skin:age_spots" not in young
            # the pre layers composite to a base: the cheek ends up redder than the forehead, lipstick on the lips
            from hifipushie.surface import Points
            J = skin._joints(spec)
            io = skin.interocular(J)
            pts = np.array([J["lm_lid_lower.L"] + io * np.array([0.12, 0.1, -0.6]), J["lm_nose_bridge"] + io * np.array([0, 0.2, 0.9]),
                            J["lm_lip_lower"] + [0, 0, 0.004]])
            P = Points(spec, pts, np.tile([0, -1.0, 0], (3, 1)), np.zeros(3, int), ["body"], 0.002)
            plain = head_spec(tone={"fitzpatrick": 3}, age=60)
            base = skin.part_base(plain)[1]
            c = paint.precomposite(plain, paint._View(P, np.arange(3)), base, paint.pre_layers(plain))
            assert c.shape == (3, 5) and c[0, 0] / c[0, 1] > c[1, 0] / c[1, 1], c  # r/g: cheek vs forehead
            c2 = paint.precomposite(spec, paint._View(P, np.arange(3)), base, paint.pre_layers(spec))
            assert c2[2, 3] < 0.25 < c[2, 3], (c2[2], c[2])  # glossy lipstick's roughness on the lower lip
            from hifipushie import paintnodes
            prog = paintnodes.compile(spec)
            assert len(prog["pre"]["body"]) == 5 and all(not ly["name"] in pre for ly in prog["layers"])
            rec = skin.export_recipe(spec, d, "t")
            assert rec["detail"] and all((store.HOME / x["normal"]).exists() or os.path.exists(os.path.join(d, x["normal"])) for x in rec["detail"])
        finally:
            store.HOME = home


def test_brows_mirror():
    """Both brows' hairs run from the nose outward: the right brow is the left one's mirror image (it was laid
    unmirrored: "the left eyebrow is backwards")."""
    import tempfile
    from hifipushie import images, store
    with tempfile.TemporaryDirectory() as d:
        home, store.HOME = store.HOME, __import__("pathlib").Path(d)
        try:
            spec = head_spec(hair={"brows": 1.0})
            ly = paint.layers(spec)["skin:brow_hairs"]
            img = next(e["image"] for e in [ly] + list(ly.get("mask") or []) if isinstance(e, dict) and "image" in e)
            assert img["mirror"] and img["mirror_image"]
            fr = images.frame(spec, img)
            mr = images.mirrored(fr)
            M = np.array([-1.0, 1, 1])
            for k in ("c", "right", "up", "dir"):  # a pure reflection of the left brow's frame
                assert np.allclose(np.array(mr[k]), np.array(fr[k]) * M), k
            rng = np.random.default_rng(1)
            P = np.array(fr["c"]) + rng.uniform(-1, 1, (400, 1)) * 0.5 * fr["w"] * np.array(fr["right"]) \
                + rng.uniform(-1, 1, (400, 1)) * 0.5 * fr["h"] * np.array(fr["up"])
            N = np.tile(fr["dir"], (400, 1))
            a, _ = images.evaluate(fr, P, N)
            b, _ = images.evaluate(fr, P * M, N * M)
            assert a.max() > 0.5 and np.allclose(a, b, atol=1e-6)  # the hair picture at mirrored points is the same
        finally:
            store.HOME = home


def test_makehuman_sex():
    from hifipushie import assets, makehuman
    try:
        assets.pack("makehuman")
    except Exception:
        print("  (no MakeHuman pack: skipped)")
        return
    a = makehuman.body({"age": 30, "height": 1.7})
    b = makehuman.body({"age": 30, "height": 1.7, "sex": 1.0})
    assert np.array_equal(a["P"], b["P"]), "male stays the default, bit for bit"
    f = makehuman.body({"age": 30, "height": 1.7, "sex": 0.0})
    m = makehuman.body({"age": 30, "height": 1.7, "sex": 0.5})
    assert np.abs(f["P"] - a["P"]).max() > 0.01 and np.abs(m["P"] - 0.5 * (f["P"] + a["P"])).max() < 0.02


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
