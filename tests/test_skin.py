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
    def ita(rgb):  # Chardon's individual typology angle: very light > 55, light 41-55, intermediate 28-41 ...
        c = np.where(np.array(rgb) <= 0.04045, np.array(rgb) / 12.92, ((np.array(rgb) + 0.055) / 1.055) ** 2.4)
        y = c @ [0.2126, 0.7152, 0.0722]
        z = c @ [0.0193, 0.1192, 0.9505] / 1.08883
        f = lambda v: np.cbrt(v) if v > 0.008856 else 7.787 * v + 16 / 116  # noqa: E731
        return np.degrees(np.arctan2(116 * f(y) - 16 - 50, 200 * (f(y) - f(z))))
    assert ita(skin.tone_rgb({"fitzpatrick": 1})) > 55, "Fitzpatrick 1 reaches 'very light' (it stopped at ITA 52: tan)"
    assert 41 < ita(skin.tone_rgb({"fitzpatrick": 2})) < 55 and 28 < ita(skin.tone_rgb({"fitzpatrick": 3})) < 41
    assert skin.tone_rgb({"melanin": 0.3}) == [0.7576, 0.5871, 0.4815], "F2 and darker unchanged by the fair end"
    v = lambda t, **k: colorsys.rgb_to_hsv(*skin.tone_rgb(t, **k))[2]  # noqa: E731
    assert v({"fitzpatrick": 1}) - v({"fitzpatrick": 1}, melanin=2.5) > 0.03, "freckles still show on very fair skin"
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


def test_only_some_groups():
    """2026-10-07 (s0urc3's Garrett): the description was all or nothing on the skin part; to take only its eye
    pictures on a hand-painted character they pointed it at the tongue. skin.only lays the groups asked for and
    nothing else, and without "shading" leaves the part's own shading alone."""
    full = head_spec(tone={"fitzpatrick": 2}, age=52, eyes={"iris": "#56666e"})
    spec = head_spec(tone={"fitzpatrick": 2}, age=52, only=["eyes"], eyes={"iris": "#56666e"})
    spec["blobs"]["eye.L"]["part"] = "eyes"
    full["blobs"]["eye.L"]["part"] = "eyes"
    L = paint.layers(spec)
    assert L and all(skin.group_of(k) == "eyes" for k in L), list(L)
    assert {"skin:eye_L", "skin:eye_R"} <= set(L) and all(v["part"] == "eyes" for v in L.values())
    assert skin.part_base(spec) is None and not skin.shaded(spec) and skin.shaded(full)
    assert L["skin:eye_L"] == paint.layers(full)["skin:eye_L"]  # the same picture as the whole description's
    paint.validate(spec)
    # the rims are on the skin: ordinary layers (nothing is composited into a base that isn't the description's)
    rims = paint.layers(head_spec(only=["eyes", "eye_rims"]))
    assert "skin:caruncle" in rims and not any(v.get("_pre") for v in rims.values())
    assert paint.layers(full)["skin:caruncle"].get("_pre")
    # (garrettnative) the lateral canthus: off unless asked; then a multiply shadow on each eyeball's outer end (the
    # eyes group) and the corner's red on the skin (a rim), each on its own side of the eye
    assert not any("canthus" in k for k in paint.layers(full))
    cs = head_spec(tone={"fitzpatrick": 2}, age=52, eyes={"iris": "#56666e", "canthus": 0.8})
    cs["blobs"]["eye.L"]["part"] = "eyes"
    CL = paint.layers(cs)
    assert CL["skin:eye_canthus_L"]["part"] == "eyes" and CL["skin:eye_canthus_L"]["mix"] == "multiply"
    assert CL["skin:eye_canthus_L"]["mask"][0]["spot"]["at"][0][0] > 0 > CL["skin:eye_canthus_R"]["mask"][0]["spot"]["at"][0][0]
    assert skin.group_of("skin:eye_canthus_L") == "eyes" and skin.group_of("skin:canthus") == "eye_rims"
    assert CL["skin:canthus"].get("_pre")
    paint.validate(cs)
    # every layer of a full description belongs to a group, and the groups add up to it
    names = set(paint.layers(full))
    got = set()
    for g in skin.GROUPS:
        if g != "shading":
            got |= set(paint.layers(head_spec(tone={"fitzpatrick": 2}, age=52, only=[g])))
    assert got == names, (names - got, got - names)
    both = head_spec(only=["shading", "lips"])
    assert skin.part_base(both) is not None and all(skin.group_of(k) == "lips" for k in paint.layers(both))
    for bad in (["iris"], [], "skin"):
        try:
            paint.layers(head_spec(only=bad))
            assert False, bad
        except SpecError as e:
            assert "eye_rims" in str(e)


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
            for want in ("skin:freckles", "skin:stubble_shadow", "skin:brow_hairs", "skin:stubble", "skin:wrinkle_forehead", "skin:scar0_cut",
                         "skin:scar1_surgical_stitches", "skin:makeup_eyeliner", "skin:micro_pores"):
                assert want in fine, want
            for want in ("skin:midface_red", "skin:lips_lower", "skin:makeup_foundation", "skin:makeup_lipstick",
                         "skin:flush", "skin:tan"):
                assert want in pre, want
            # what a renderer's shader must hold stays small, and none of it is procedural noise: swatches, images, spots
            assert sum(1 for v in fine.values() if v.get("part", "body") == "body") <= 44, len(fine)   # (44: lips.under_shade on by default, the commissures drawn in it; 37: skin3 moved the stubble shadow per pixel; 41: skin4's face base map, 4 layers; 43: projskin's face microrelief cells + cells_fine. Cycles rendered the projskin heads (a stack + these) once the blemishes under a stack lost their height; the full spec here not rendered)
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


def test_beard_area_and_stubble_options():
    """The beard is an area (jowls and under the jaw, not only beads along the jaw's edge), and stubble takes size /
    shadow / grey; brows take drop / arch / soft. Defaults make no new layer."""
    spec = head_spec(hair={"stubble": {"amount": 0.8, "engine": "tile"}})
    names = list(paint.layers(spec))
    assert "skin:stubble" in names and "skin:stubble_grey" not in names
    assert "jowl.L" in skin.UNIONS["beard.L"] and "beard_neck" in skin.UNIONS["beard.L"]
    spec = head_spec(hair={"stubble": {"amount": 1.0, "size": 2.0, "shadow": 1.5, "shadow_color": "#83705f", "grey": 0.5, "engine": "tile"},
                           "brows": {"drop": 0.003, "arch": 0.5, "soft": 0.4}})
    ly = paint.layers(spec)
    assert "skin:stubble_grey" in ly
    assert abs(ly["skin:stubble_shadow"]["opacity"] - 0.63) < 1e-6
    assert ly["skin:brow_hairs"]["opacity"] < 0.95


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


def test_lash_line_is_a_line():
    """The upper lash line stays on the lid's margin: the pretarsal lid lies on the eyeball too, so "near the eyeball"
    alone painted the whole open lid up to the fold, a dark grey band over the iris (Tess, 2026-10-09)."""
    from hifipushie.surface import Points
    c, R = np.array(LM["eye.L"]), 0.0125
    on = lambda deg: c + R * np.array([0.0, -np.cos(np.radians(deg)), np.sin(np.radians(deg))])  # noqa: E731
    pts = np.array([on(22), on(48)])  # the margin (lashes) | the lid 9 mm up, still on the ball (no lashes)
    for with_margin, want in ((False, [1, 1]), (True, [1, 0])):
        spec = head_spec(age=25)
        spec["blobs"]["eye.L"]["size"] = [R] * 3
        if with_margin:
            for k, x in (("lm_lid_upper_in.L", -0.007), ("lm_lid_upper_out.L", 0.007)):
                spec["joints"][k] = {"pos": (on(21) + [x, 0.001, 0]).tolist(), "r": 0.003}
            spec["joints"]["lm_eye_inner.L"]["pos"] = (on(5) + [-0.012, 0.002, 0]).tolist()
            spec["joints"]["lm_eye_outer.L"]["pos"] = (on(5) + [0.013, 0.004, 0]).tolist()
        P = Points(spec, pts, np.tile([0, -1.0, 0], (2, 1)), np.zeros(2, int), ["body"], 0.002)
        ly = skin.expand_zones(spec, {"color": [0, 0, 0], "zone": "lash_upper.L"})
        m = paint.layer_mask(spec, "t", ly, paint._View(P, np.arange(2)))
        assert (m > 0.5).astype(int).tolist() == want, (with_margin, m)


def test_brow_tilt_and_fall():
    """A brow's own shape beside its landmarks (Tess, 2026-10-09: hers rises outward with a short tail, ours sat as a
    level bar hooked down at the end; `arch` only scales the landmarks' slope, which was ~0): `tilt` turns the whole
    brow (tail up), `fall` scales the tail's drop (a new picture), and the defaults leave the brow as it was."""
    import tempfile
    from hifipushie import store
    with tempfile.TemporaryDirectory() as d:
        home, store.HOME = store.HOME, __import__("pathlib").Path(d)
        try:
            def img(**b):
                ly = paint.layers(head_spec(hair={"brows": {"density": 0.8, **b}}))["skin:brow_hairs"]
                return next(e["image"] for e in [ly] + list(ly.get("mask") or []) if isinstance(e, dict) and "image" in e)
            a, b, c = img(), img(tilt=6), img(fall=0.3)
            assert abs(b["rotate"] - a["rotate"] - 6) < 1e-6
            assert b["file"] == a["file"] and c["file"] != a["file"]
            assert img(fall=1.0)["file"] == a["file"]
            # each end on its own: the inner head down 3 mm, the tail level: the centre down 1.5 mm, turned tail-up
            e = img(lift=[-0.003, 0.0])
            assert abs(e["at"][2] - a["at"][2] + 0.0015) < 1e-6 and e["rotate"] > a["rotate"]
            f = img(apart=0.002)
            assert abs(f["at"][0] - a["at"][0] - 0.002) < 1e-6
            # the shadow follows a moved brow (its own picture), and stays the landmark zone for one that isn't
            def shadow(**b):
                return paint.layers(head_spec(hair={"brows": {"density": 0.8, **b}}))["skin:brow_shadow"]
            assert "image" in str(shadow(drop=0.003)) and "image" not in str(shadow())
        finally:
            store.HOME = home


def test_makeup_looks():
    """skin.makeup.look presets expand into items (overrides merge key by key); the liner follows the lash line's own
    zone (lines through the eye-corner landmarks left dots past the lids' corners) and a wing is a tapering chain from
    the outer lash line, one per side; each product keeps its finish."""
    import json
    import tempfile
    from hifipushie import skin_makeup, store
    r = skin_makeup.resolve({"look": "evening", "lipstick": {"color": "#552233"}, "blush": 0.2})
    assert r["lipstick"]["color"] == "#552233" and r["lipstick"]["finish"] == "matte" and r["blush"] == 0.2
    try:
        skin_makeup.resolve({"look": "party"})
        raise AssertionError("an unknown look must fail")
    except SpecError:
        pass
    with tempfile.TemporaryDirectory() as d:
        home, store.HOME = store.HOME, __import__("pathlib").Path(d)
        try:
            nat = paint.layers(head_spec(makeup={"look": "natural"}))
            eve = paint.layers(head_spec(makeup={"look": "evening"}))
        finally:
            store.HOME = home
    assert "skin:makeup_eyeliner" not in nat and "skin:makeup_lipstick" in nat
    assert nat["skin:makeup_lipstick"]["opacity"] < 0.5 and nat["skin:makeup_lipstick"]["roughness"] < 0.2   # a sheer balm
    for k in ("makeup_eyeshadow", "makeup_eyeshadow_crease", "makeup_eyeshadow_outer", "makeup_eyeliner", "makeup_contour",
              "makeup_lip_liner", "makeup_highlight"):
        assert "skin:" + k in eve, k
    liner = json.dumps(eve["skin:makeup_eyeliner"]["mask"])
    assert '"near": ["eye.L"' in liner and liner.count('"spot"') >= 2   # the lash zone (near the eyeballs) + a wing per side


def test_lip_rim_lower():
    """skin.lips.rim_lower (mouth_eye_bias): the pale vermilion rim drawn under the LOWER lip at this share. Photos show a
    lower lip as a lit pad over its own shadow; a pale ring there made our lower lips read darker than the skin under
    them on every head (docs/notes/mouth_eye_bias.md)."""
    from hifipushie.surface import Points
    J = {k: np.asarray(v, float) for k, v in LM.items()}
    above = J["lm_lip_upper"] + [0, 0, 0.0006]
    below = J["lm_lip_lower"] - [0, 0, 0.0006]
    inside = 0.5 * (J["lm_lip_upper"] + J["lm_lip_seam"])
    got = {}
    for rl in (0.0, 0.5, 1.0):
        spec = head_spec(tone={"fitzpatrick": 2}, age=30, lips={"rim_lower": rl})
        L = paint.layers(spec)
        P = Points(spec, np.array([above, below, inside]), np.tile([0, -1.0, 0], (3, 1)), np.zeros(3, int), ["body"], 0.002)
        got[rl] = paint.layer_mask(spec, "skin:lip_border", L["skin:lip_border"], paint._View(P, np.arange(3)))
    for rl, m in got.items():
        assert m[0] > 0.2 and m[2] < 0.05, (rl, m)     # the rim over the upper lip stays; nothing inside the red
    assert got[0.0][1] < 0.05 < got[0.5][1] < got[1.0][1], {k: v.round(3).tolist() for k, v in got.items()}
    try:
        paint.layers(head_spec(lips={"rim_low": 0}))
        raise AssertionError("an unknown lips key must fail")
    except SpecError:
        pass


def test_lip_under_shade():
    """skin.lips.under_shade (mouth_eye_bias): a warm multiply band on the skin just under the lower lip, deepest under
    the middle, never on the red; off at 0."""
    from hifipushie.surface import Points
    J = {k: np.asarray(v, float) for k, v in LM.items()}
    mid = J["lm_lip_lower"] - [0, 0, 0.0018]
    side = J["lm_lip_lower_side.L"] - [0, 0, 0.0012]
    red = 0.5 * (J["lm_lip_lower"] + J["lm_lip_seam"])
    spec = head_spec(tone={"fitzpatrick": 2}, age=30, lips={"under_shade": 1.0})
    L = paint.layers(spec)
    ly = L["skin:lip_under_shade"]
    assert ly["mix"] == "multiply" and 0 < ly["opacity"] <= 1
    P = Points(spec, np.array([mid, side, red]), np.tile([0, -1.0, 0], (3, 1)), np.zeros(3, int), ["body"], 0.002)
    m = paint.layer_mask(spec, "skin:lip_under_shade", ly, paint._View(P, np.arange(3)))
    assert m[0] > 0.1 and m[0] > 2 * m[1] and m[2] < 0.05, m
    assert "skin:lip_under_shade" not in paint.layers(head_spec(tone={"fitzpatrick": 2}, age=30, lips={"under_shade": 0}))

def test_lid_shade_zone():
    """skin.zones.lid_shade: off by default; asked for, a neutral-cool multiply on the eyelid zone (the photographed lid is
    darker AND a little less red / yellow than the cheek: melanin or the blood-red eyelids zone would warm it)"""
    spec = head_spec(tone={"fitzpatrick": 2}, age=45)
    assert "skin:lid_shade" not in paint.layers(spec)
    spec["skin"]["zones"] = {"lid_shade": 1.0}
    ly = paint.layers(spec)["skin:lid_shade"]
    col = np.asarray(ly["color"], float)
    assert ly.get("mix") == "multiply" and col.max() < 0.8 and col[2] >= col[0] - 1e-9, "darker, neutral to cool"
    assert "eyelid" in str(ly["mask"]) or "spot" in str(ly["mask"])
    spec["skin"]["zones"] = {"lid_shade": 1.6}
    assert paint.layers(spec)["skin:lid_shade"]["opacity"] > ly["opacity"]




def test_zone_colors_override():
    """skin.zone_colors.<layer>: the zone's own colour replaced (the cool lid_shade turned Garrett's and B's sockets grey-lilac,
    r7 2026-10-16: eye sock - cheek b* -5.6 vs photo -0.1); unknown layers and bad colours refuse."""
    spec = head_spec(tone={"fitzpatrick": 2}, age=45, zones={"lid_shade": 1.0}, zone_colors={"lid_shade": [0.8, 0.71, 0.64]})
    ly = paint.layers(spec)["skin:lid_shade"]
    assert ly["color"] == [0.8, 0.71, 0.64] and ly["mix"] == "multiply"
    for bad in ({"nope": [0.5, 0.5, 0.5]}, {"lid_shade": [0.5, 0.5]}, {"lid_shade": [1.5, 0.5, 0.5]}):
        try:
            paint.layers(head_spec(tone={"fitzpatrick": 2}, zone_colors=bad))
        except Exception as e:
            assert "zone_colors" in str(e)
        else:
            raise AssertionError(bad)


def test_lips_over_stack():
    """lips.over_stack: the lips' own colour laid after a stack, not "_pre" (under a stack, stack_base covered it: Tess's
    lips.melanin 12 moved nothing, 2026-10-16); off by default"""
    st = {"box": [0.56, 0.65, 1.0, 0.99], "base": [0.86, 0.76, 0.66], "coverage": "c" * 16,
          "layers": [{"name": "pigment", "image": "a" * 16, "opacity": 0.8}]}
    L = skin.layers(head_spec(tone={"fitzpatrick": 2}, stack=st))
    assert L["skin:lips_upper"].get("_pre")
    L = skin.layers(head_spec(tone={"fitzpatrick": 2}, stack=st, lips={"over_stack": True}))
    ks = list(L); top = max(i for i, k in enumerate(ks) if k.startswith("skin:stack_"))
    for nm in ("skin:lips_upper", "skin:lips_lower"):
        assert not L[nm].get("_pre") and ks.index(nm) > top, nm


def test_lid_shade_survives_a_stack():
    """A measured stack drops our colour zones (they painted over its base), but lid_shade (off unless asked, the lid's
    measured lever) stays: dropping it made every stacked head's lid_shade a silent no-op (r5, 2026-10-16)."""
    st = {"box": [0.56, 0.65, 1.0, 0.99], "base": [0.86, 0.76, 0.66], "coverage": "c" * 16,
          "layers": [{"name": "pigment", "image": "a" * 16, "opacity": 0.8}]}
    L = skin.layers(head_spec(tone={"fitzpatrick": 2}, stack=st, zones={"lid_shade": 0.6, "under_eye": 1.2}))
    assert "skin:lid_shade" in L and "skin:stack_pigment" in L
    assert "skin:under_eye" not in L and "skin:midface_red" not in L
    ks = list(L)   # ... and lies OVER the stack (laid first, stack_base's normal mix at opacity 1 covered it: r6 moved nothing)
    assert ks.index("skin:lid_shade") > max(i for i, k in enumerate(ks) if k.startswith("skin:stack_"))


def test_under_eye_shade_survives_a_stack():
    """skin.zones.under_eye_shade: off by default; asked for, a multiply on the under-eye zone that a stack keeps and lays
    after itself (the "under_eye" zone is dropped under a stack: nothing moved the under-eye row in r6, 2026-10-16)."""
    st = {"box": [0.56, 0.65, 1.0, 0.99], "base": [0.86, 0.76, 0.66], "coverage": "c" * 16,
          "layers": [{"name": "pigment", "image": "a" * 16, "opacity": 0.8}]}
    assert "skin:under_eye_shade" not in skin.layers(head_spec(tone={"fitzpatrick": 2}, stack=st))
    L = skin.layers(head_spec(tone={"fitzpatrick": 2}, stack=st, zones={"lid_shade": 0.6, "under_eye_shade": 1.0}))
    L2 = skin.layers(head_spec(tone={"fitzpatrick": 2}, stack=st, zones={"lid_shade": 0.6, "under_eye_shade": 1.5}))
    ks = list(L); top = max(i for i, k in enumerate(ks) if k.startswith("skin:stack_"))
    assert ks.index("skin:under_eye_shade") > top and ks.index("skin:lid_shade") > top
    assert L["skin:under_eye_shade"]["mix"] == "multiply" and L2["skin:under_eye_shade"]["opacity"] > L["skin:under_eye_shade"]["opacity"]
    # not "_pre": pre layers are composited into the base under the shader's stack_base, which covers them (2026-10-16)
    assert not L["skin:under_eye_shade"].get("_pre") and not L["skin:lid_shade"].get("_pre")
    sp_ = head_spec(tone={"fitzpatrick": 2}, stack=st)
    sp_["skin"].setdefault("hair", {})["brows"] = {"density": 1.0}
    assert not skin.layers(sp_)["skin:brow_shadow"].get("_pre")
    sp_ = head_spec(tone={"fitzpatrick": 2})
    sp_["skin"].setdefault("hair", {})["brows"] = {"density": 1.0}
    assert skin.layers(sp_)["skin:brow_shadow"].get("_pre")   # (no stack: unchanged)


def test_rough_layers_follow_shading_roughness():
    """The rough_* layers are offsets from skin.shading.roughness when it is set (they used the oil-derived value and
    covered the part's own: r6's shading.roughness moved no sheen row, 2026-10-16)."""
    def tz(**sh):
        sp_ = head_spec(tone={"fitzpatrick": 2})
        if sh:
            sp_["skin"]["shading"] = sh
        return skin.layers(sp_)["skin:rough_tzone"]["roughness"]
    assert abs((tz(roughness=0.6) - tz(roughness=0.4)) - 0.2) < 2e-3, (tz(roughness=0.6), tz(roughness=0.4))


def test_brows_shadow_scales_the_skin_shadow():
    """hair.brows.shadow multiplies the skin-level shadow under the hairs (a strong one filled the gaps: "solid sticker")."""
    def op(sh):
        sp_ = head_spec(tone={"fitzpatrick": 2})
        sp_["skin"].setdefault("hair", {})["brows"] = {"density": 1.0, **({"shadow": sh} if sh is not None else {})}
        return skin.layers(sp_)["skin:brow_shadow"]["opacity"]
    assert abs(op(0.5) - 0.5 * op(None)) < 2e-3, (op(0.5), op(None))


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
