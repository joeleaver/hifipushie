"""The hair READER (hair_read.py; the hair_from_reference tool): its measures on synthetic pictures, and the START it
sets from a read. No Blender, no face-parsing nets. `uv run pytest tests/test_hair_read.py`.

What these hold: the stand-off is the hair's edge minus the skull's along rays from the head centre, in mm, and can be
negative (a skull poking through the hair is the head and picture disagreeing, never clipped); halo density rises with
fine hairs past the solid edge and is ~0 for a cut-out; the hairline's softness is the 20-80 % width of the mean
profile across it; baby hairs are thin specks (pores and round blobs are not); a part is found where the strand
direction flips with a scalp line, and not where the strands only lean one way; the colour split finds the grey
strands' share; the start is a valid groom (every key known to hair.validate) and says where each value came from."""

import numpy as np
import pytest

from hifipushie import hair, hair_read as hr


def _disk(n, c, r):
    y, x = np.mgrid[:n, :n]
    return (x - c[0]) ** 2 + (y - c[1]) ** 2 <= r * r


def test_standoff_from_skull_and_hair_disks():
    n, mm = 600, 0.25
    c = (300.0, 300.0)
    skull, hairm = _disk(n, c, 160), _disk(n, c, 200)  # 40 px = 10 mm of hair over the skull
    bg = (~hairm).astype(float)
    o = hr.outline_rays(skull, hairm, hairm.astype(float), bg, np.array(c), mm)
    st = o["standoff_mm"][np.isfinite(o["standoff_mm"])]
    assert len(st) > 100
    assert abs(np.median(st) - 10.0) < 0.6
    assert np.nanmax(o["halo"]) < 0.05  # a cut-out: nothing past the edge


def test_standoff_is_negative_where_the_skull_pokes_out():
    n, mm = 600, 0.25
    c = (300.0, 300.0)
    skull, hairm = _disk(n, c, 200), _disk(n, c, 180)
    o = hr.outline_rays(skull, hairm, hairm.astype(float), (~hairm).astype(float), np.array(c), mm)
    assert np.nanmedian(o["standoff_mm"]) < -4.0


def test_halo_density_rises_with_fine_hairs_past_the_edge():
    n, mm = 600, 0.25
    c = (300.0, 300.0)
    skull, hairm = _disk(n, c, 160), _disk(n, c, 200)
    rng = np.random.default_rng(0)
    a = hairm.astype(float)
    ring = _disk(n, c, 212) & ~hairm
    a[ring & (rng.random((n, n)) < 0.3)] = 1.0  # sparse fine hairs within 3 mm
    bg = (~hairm).astype(float)
    o0 = hr.outline_rays(skull, hairm, hairm.astype(float), bg, np.array(c), mm)
    o1 = hr.outline_rays(skull, hairm, a, bg, np.array(c), mm)
    assert np.nanmean(o1["halo"]) > np.nanmean(o0["halo"]) + 0.08


def test_edge_softness_is_the_20_80_width():
    n, mm = 400, 0.2
    x = np.arange(n) * mm
    w = 5.0  # mm: a linear ramp from skin (0) to hair (1)
    a = np.clip((x - 40.0) / w, 0, 1)[None, :].repeat(n, 0)
    pts = np.stack([np.full(50, 40.0 / mm + 0.5 * w / mm), np.linspace(50, 350, 50)], 1)
    nrm = np.tile([1.0, 0.0], (50, 1))
    r = hr.edge_softness(None, a, pts, nrm, mm, reach=6.0)
    assert abs(r["width_mm"] - 0.6 * w) < 0.6


def test_baby_hairs_count_thin_specks_not_round_ones():
    n, mm = 400, 0.1
    hairp = np.zeros((n, n))
    hairp[:150] = 1.0
    skin = 1.0 - hairp
    a = np.zeros((n, n))
    for x in (60, 120, 180, 240):  # thin hairs 2.5 mm long, 0.2 mm wide, 1-3.5 mm under the hairline
        a[160:185, x:x + 2] = 1.0
    for x in (300, 350):  # round specks 1.2 mm across (pores, freckles)
        a[165:177, x:x + 12] = 1.0
    assert hr.baby_hairs(a, hairp, skin, mm) == 4


def test_parting_found_where_strands_flip_and_scalp_shows():
    from PIL import Image
    n, mm = 500, 0.2
    y, x = np.mgrid[:n, :n].astype(float)
    xc = 250.0
    left = np.sin((x + y) * 0.9)    # strands along "/" ... (stripes run along x + y = const)
    right = np.sin((x - y) * 0.9)   # ... and "\"
    L = np.where(x < xc, left, right) * 40 + 90
    solid = np.ones((n, n), bool)
    a_skin = np.ones((n, n))
    a_skin[:, int(xc) - 3:int(xc) + 3] = 0.0  # a thin line of scalp along the part
    L[:, int(xc) - 3:int(xc) + 3] = 180
    img = Image.fromarray(np.stack([L] * 3, -1).clip(0, 255).astype(np.uint8))
    p = hr.parting(img, solid, a_skin, mm, top_px=0, hairline_px=n - 1, c=np.array([xc, 450.0]))
    assert p["seen"], p
    assert abs(p["x_px"] - xc) < 25
    # strands leaning one way everywhere, no scalp line: no part
    img2 = Image.fromarray(np.stack([left * 40 + 90] * 3, -1).clip(0, 255).astype(np.uint8))
    p2 = hr.parting(img2, solid, np.ones((n, n)), mm, top_px=0, hairline_px=n - 1, c=np.array([xc, 450.0]))
    assert not p2["seen"], p2


def test_colour_split_finds_the_grey_share():
    from PIL import Image
    rng = np.random.default_rng(1)
    n = 200
    dark = np.array([80.0, 70, 62])
    grey = np.array([170.0, 168, 165])
    pick = rng.random((n, n)) < 0.3
    img = np.where(pick[..., None], grey, dark) + rng.normal(0, 3, (n, n, 3))
    r = hr.colour_split(Image.fromarray(img.clip(0, 255).astype(np.uint8)), np.ones((n, n), bool), 0.2)
    assert abs(r["light_share"] - 0.3) < 0.03
    assert r["grey"] is not None and r["seen"] is not None
    gr = [int(r["grey"][i:i + 2], 16) for i in (1, 3, 5)]
    assert min(gr) > 150


def test_region_names():
    assert list(hr.region_name([0, 90, 180, 180, 10, 170], [20, 10, 10, -40, 70, 60])) == \
        ["front", "sides", "back", "nape", "top", "crown"]


def _fake_read():
    s = {"standoff": {"front": 13.0, "top": 12.0, "crown": 11.0, "sides": 10.0, "back": 12.0, "nape": 3.0},
         "halo": {}, "halo_all": 0.07, "rough_mm": 0.5, "wisps_per_10cm": 1.7,
         "hairline": [[2.5, 1.741, 34.0, 50], [27.5, 1.748, 42.0, 40], [42.5, 1.744, 39.0, 30], [57.5, 1.71, 13.0, 30]],
         "hairline_softness_mm": {"front": 3.5}, "baby_per_cm": 2.0,
         "parting": {"seen": False, "sweep": 0.2, "x_m": 0.005},
         "colour": {"bands": {"variation": {"strand_sd": 6.8}}, "light_share": 0.45, "seen": "#635b55", "grey": "#7d7773",
                    "dark_L": 35.0},
         "colour_view": 0, "light_share_by_region": {"front": 0.23, "top": 0.2, "sides": 0.59, "back": 0.43, "crown": 0.56}}
    return {"summary": s, "views": [], "authority": 0}


def test_start_is_a_valid_short_cut_groom():
    st = hr.start(_fake_read(), {})
    h = st["hair"]
    assert st["short"]
    spec = {"hair": {"style": h["style"], "groom": h["groom"], "strands": h["strands"], "look": h["look"]}}
    hair.validate(spec)  # every key known
    g = h["groom"]
    assert g["parting"] == {"side": "none"}  # not seen: no part invented
    assert g["hairline"]["front_points"][0][0] == 2.5
    assert abs(g["volume"]["top"] - 0.6 * 0.012) < 1e-6
    assert h["look"]["grey_amount"] == 0.2 and g["grey"]["sides"] > 0.4
    assert "crown" not in g["grey"]
    keys = [k for k, _, _ in st["rows"]]
    assert "groom.loose.length" in keys
    why = dict((k, w) for k, _, w in st["rows"])
    assert "INFERRED" in why["groom.loose.length"] and "MEASURED" in why["look.seen"] and "view 0" in why["look.seen"]


def test_start_sets_a_seen_part():
    r = _fake_read()
    r["summary"]["parting"] = {"seen": True, "x_m": -0.031, "strength": 0.5, "scalp": 0.2, "sweep": 0.3}
    g = hr.start(r, {})["hair"]["groom"]
    assert g["parting"] == {"side": "right", "offset": 0.031}


def test_long_hair_is_not_given_a_crop():
    r = _fake_read()
    r["summary"]["standoff"] = {k: 60.0 for k in r["summary"]["standoff"]}
    st = hr.start(r, {})
    assert not st["short"] and "loose" not in st["hair"]["groom"]


def test_render_as_picture_undoes_the_square():
    from PIL import Image
    sq = Image.new("RGB", (1536, 1536), (0, 0, 0))
    sq.paste(Image.new("RGB", (1152, 1536), (255, 255, 255)), (192, 0))
    p = np.asarray(hr.render_as_picture(sq, (1152, 1536)))
    assert p.shape == (1536, 1152, 3) and p.min() > 250
