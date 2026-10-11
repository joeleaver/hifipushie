"""The dressed brows from the picture (blockin_brows) and the iris by its limbus (blockin_eyes.limbus): gnmbrow,
2026-10-11. Incident: Tess's dressed brows sat 4-7 mm under hers, on the lid's fold (hand offsets carried over from an
older head), and her drawn iris was 18 % too big (lids matched in iris radii opened the eye 18 % too tall).
uv run python -m pytest -q tests/test_blockin_brows.py"""
import numpy as np
import pytest
from PIL import Image, ImageDraw

from hifipushie import blockin_brows as bb, blockin_eyes as be, lidfold, store

REF = "fs_ge3"
need_ref = pytest.mark.skipif(not (store.HOME / REF / "human_refs.json").exists(), reason=f"workspace model {REF} not present")


def _points(w=600, h=500):
    """Detector points of an upright face: nasion 168 over the chin 152, the irises, their rims, the brows' contours."""
    P = np.zeros((478, 2))
    P[168], P[152] = (w / 2, 200), (w / 2, 460)
    P[13] = P[14] = (w / 2, 400)
    for s, cx in enumerate((200.0, 400.0)):
        c = np.array([cx, 250.0])
        P[lidfold.IRIS_C[s]] = c
        for i, d in zip(lidfold.IRIS_RIM[s], ((1, 0), (0, -1), (-1, 0), (0, 1))):
            P[i] = c + 16.0 * np.array(d)                      # the detector's ring: 16 px (it under-reads)
        up, lo = bb.BROWS[s]
        xs = np.linspace(cx - 50, cx + 50, 5) if s else np.linspace(cx + 50, cx - 50, 5)
        for k, (iu, il) in enumerate(zip(up, lo)):
            P[iu], P[il] = (xs[k], 172.0), (xs[k], 188.0)
    return P


def test_limbus_reads_the_edge_not_the_detectors_ring():
    P = _points()
    im = Image.new("RGB", (600, 500), (205, 170, 150))
    d = ImageDraw.Draw(im)
    for s in (0, 1):
        c = P[lidfold.IRIS_C[s]]
        d.ellipse([c[0] - 45, c[1] - 22, c[0] + 45, c[1] + 22], fill=(235, 230, 225))      # the white
        d.ellipse([c[0] - 20, c[1] - 20, c[0] + 20, c[1] + 20], fill=(70, 62, 48))          # a 20 px iris
        d.ellipse([c[0] - 6, c[1] - 6, c[0] + 6, c[1] + 6], fill=(5, 5, 5))
    lb = be.limbus(im, P)
    for e in lb:
        assert abs(e["r_px"] - 20.0) < 1.0, e
        assert np.allclose(np.array(e["rgb"]) * 255, (70, 62, 48), atol=6), e["rgb"]
    assert abs(be.iris_scale(im, P) - 0.8) < 0.05
    # a picture with no readable limbus (one flat colour): the detector's own radius is kept
    assert be.iris_scale(Image.new("RGB", (600, 500), (128, 128, 128)), P) == 1.0


def test_band_reads_a_drawn_brow():
    """A dark band 12 px thick whose lower edge is 6 px UNDER the detector's (the detector's band is a guess): the
    reader returns the drawn edges, at 0.25 mm / px."""
    P = _points()
    im = Image.new("RGB", (600, 500), (205, 170, 150))
    d = ImageDraw.Draw(im)
    for cx in (200, 400):
        d.rectangle([cx - 70, 182, cx + 70, 194], fill=(60, 45, 35))
    im = im.resize((600, 500))
    for side in bb.band(im, P, mmpx=0.25):
        ok = side["contrast"] > 0.3
        assert ok.sum() >= 8
        assert np.allclose(side["low"][ok], 194.5, atol=1.2), side["low"]
        assert np.allclose(side["top"][ok], 181.5, atol=1.2), side["top"]
    # the same picture enlarged x2 and cropped is read at the same columns (how a render is read at the photo's)
    big = im.resize((1200, 1000), Image.LANCZOS).crop((100, 100, 1200, 1000))
    for side in bb.band(big, P, mmpx=0.25, scale=2.0, origin=(50, 50)):
        ok = side["contrast"] > 0.3
        assert np.allclose(side["low"][ok], 194.5, atol=1.2), side["low"]


def test_decal_is_the_skins_own_placement():
    """decal() must lay the brow where skin_features lays its picture (drop, lift, tilt, apart included), both sides."""
    import tempfile
    from pathlib import Path
    from test_skin import head_spec
    from hifipushie import images, paint, skin_look
    with tempfile.TemporaryDirectory() as tmp:
        home, store.HOME = store.HOME, Path(tmp)
        try:
            for o in ({}, {"drop": 0.004, "tilt": 2, "lift": [0.0, 0.0018], "apart": 0.0015, "arch": 0.8}):
                spec = head_spec(hair={"brows": o or 1.0})
                ly = paint.layers(spec)["skin:brow_hairs"]
                img = next(e["image"] for e in [ly] + list(ly.get("mask") or []) if isinstance(e, dict) and "image" in e)
                fr = images.frame(spec, img)
                J = skin_look._J(spec)
                for side, f in ((1, fr), (-1, images.mirrored(fr))):
                    c, right, up, w, h = bb.decal(J, o, side)
                    assert np.allclose(c, f["c"], atol=1e-4), (o, side, c, f["c"])
                    assert np.allclose(right, f["right"], atol=2e-3) and np.allclose(up, f["up"], atol=2e-3), (o, side)
                    assert abs(w - f["w"]) < 1e-4 and abs(h - f["h"]) < 1e-4
        finally:
            store.HOME = home


def test_model_band_follows_the_decal():
    """On a flat wall seen square on at 1 px / mm, the band's middle is the spine's height and drop moves it 1:1."""
    J = {"lm_brow_inner.L": np.array([0.012, -0.1, 1.60]), "lm_brow_mid.L": np.array([0.032, -0.1, 1.607]),
         "lm_brow_outer.L": np.array([0.052, -0.1, 1.603]), "eye.L": np.array([0.031, -0.09, 1.58]),
         "eye.R": np.array([-0.031, -0.09, 1.58])}
    g = np.arange(-0.08, 0.0801, 0.002)
    X, Z = np.meshgrid(g, 1.6 + g)
    V = np.c_[X.ravel(), np.full(X.size, -0.1), Z.ravel()]
    cam = {"r": [0, 0, 0], "t": [0, 0, 1.0], "f": 1000.0, "size": [1000, 1000], "centre": [0, -0.1, 1.6], "yaw": 0.0}
    ex, ey = np.array([1.0, 0]), np.array([0, 1.0])
    xs = [np.array([500 - 32.0]), np.array([500 + 32.0])]
    a = bb.model_band(J, V, cam, {}, 1.0, xs, ex, ey)
    b = bb.model_band(J, V, cam, {"drop": 0.003}, 1.0, xs, ex, ey)
    for s in (0, 1):
        assert np.isfinite(a[s]["mid"][0]) and a[s]["low"][0] > a[s]["mid"][0] > a[s]["top"][0]     # y runs down
        assert abs((b[s]["mid"][0] - a[s]["mid"][0]) - 3.0) < 0.15                                  # 3 mm lower
        assert abs(a[s]["mid"][0] - a[1 - s]["mid"][0]) < 0.2                                       # mirrored
    thick = bb.model_band(J, V, cam, {}, 1.5, xs, ex, ey)
    assert (thick[1]["low"][0] - thick[1]["top"][0]) > 1.3 * (a[1]["low"][0] - a[1]["top"][0])


@need_ref
def test_fit_brings_the_brows_to_the_picture():
    r = bb.fit(REF)
    assert r["after"]["n"] >= 6
    assert r["after"]["mid_rms"] <= min(r["before"]["mid_rms"], 1.5), (r["before"]["mid_rms"], r["after"]["mid_rms"])
    assert "lift" not in r["brows"] and set(bb.BOUNDS) <= set(r["brows"])
    for k, (lo, hi) in bb.BOUNDS.items():
        assert lo <= r["brows"][k] <= hi, k


def test_small_iris_is_not_read():
    """A full-figure picture (Garrett's concept: a 5 px iris) has no readable limbus: the detector's radius is kept."""
    P = _points()
    for s in (0, 1):
        c = P[lidfold.IRIS_C[s]]
        for i, d in zip(lidfold.IRIS_RIM[s], ((1, 0), (0, -1), (-1, 0), (0, 1))):
            P[i] = c + 5.0 * np.array(d)
    im = Image.new("RGB", (600, 500), (205, 170, 150))
    d = ImageDraw.Draw(im)
    for s in (0, 1):
        c = P[lidfold.IRIS_C[s]]
        d.ellipse([c[0] - 4, c[1] - 4, c[0] + 4, c[1] + 4], fill=(40, 30, 25))
    assert be.iris_scale(im, P) == 1.0


@need_ref
def test_iris_check_reports_or_declines():
    r = be.iris_check(REF)       # fs_ge3's front picture is the full-figure concept: declined, with the reason
    assert "IRIS" in r["text"] and 9.0 < r["model_mm"] < 16.0
    if r["photo_mm"] is None:
        assert r["eye_radius"] is None and "not readable" in r["text"]
    else:
        assert 7.0 < r["photo_mm"] < 16.0 and r["iris_hex"].startswith("#")
