"""skin_marks: the unique stubble / freckle maps on a head (`uv run python tests/test_skin_marks.py`; no Blender). The
hand-made head of test_skin (an ellipsoid skull + landmarks) stands in for a base body."""
import hashlib
import pathlib
import tempfile

import numpy as np

from hifipushie import images, paint, skin, skin_marks as mk, store
from hifipushie.skin_features import freckle_options, stubble_options
from test_skin import head_spec


def _tmp(fn):
    def run():
        with tempfile.TemporaryDirectory() as d:
            home, store.HOME = store.HOME, pathlib.Path(d)
            mk._MESH.clear()
            try:
                fn()
            finally:
                store.HOME = home
    run.__name__ = fn.__name__
    return run


def _near(V, p):
    return int(np.argmin(np.linalg.norm(V - np.asarray(p, float), axis=1)))


@_tmp
def test_beard_zones_from_landmarks():
    """Where the beard grows follows the landmarks: chin and jaw yes, forehead / nose / lips no, the cheeks thinner than
    the chin, and moving the chin landmark moves the beard."""
    spec = head_spec(hair={"stubble": {"style": "short"}})
    J = skin._joints(spec)
    V, N, _ = mk.head_mesh(spec, "body", J)
    V, N = V.astype(float), N.astype(float)
    d = mk.beard_density(J, stubble_options({"amount": 1.0, "style": "short"}))(V, N)
    io = skin.interocular(J)
    at = lambda name, off=(0, 0, 0): d[_near(V, J[name] + io * np.asarray(off))]  # noqa: E731
    assert at("lm_chin", (0, 0, 0.15)) > 0.6
    assert at("lm_jaw_5.L") > 0.4
    assert at("lm_nose_bridge") == 0 and at("lm_brow_mid.L") == 0
    assert at("lm_lid_lower.L", (0.1, 0, -0.4)) < at("lm_chin", (0, 0, 0.15))   # upper cheek < chin
    assert at("lm_lip_upper", (0, 0, -0.03)) < 0.05                              # the vermilion
    # trimmed: the cheek line is sharper than grown-out
    o_t = stubble_options({"amount": 1.0, "style": "designer"})
    o_n = stubble_options({"amount": 1.0, "style": "heavy", "trim": 0.0})
    dt, dn = mk.beard_density(J, o_t)(V, N), mk.beard_density(J, o_n)(V, N)
    mid = lambda x: np.mean((x > 0.05) & (x < 0.5 * x.max()))  # noqa: E731  share of the half-tone edge
    assert mid(dt) < mid(dn)
    # untrimmed: no edge but a taper, and a few stragglers out past it (density < 0.1 where trimmed has none)
    strag = (dn > 0) & (dn < 0.1) & (dt == 0)
    assert strag.sum() > 0.02 * (dn > 0.5).sum()


@_tmp
def test_stubble_map_deterministic_and_styles():
    """Same inputs, same map (content-cached, byte-identical when rebuilt); clean shaven shows almost no hair, a
    longer style more; grey puts hairs in the white channel only when asked; the shadow follows the dark roots."""
    spec = head_spec()
    J = skin._joints(spec)

    def mapped(**kw):
        o = stubble_options({"amount": 1.0, **kw})
        path, place, st = mk.stubble_map(spec, "body", J, o)
        return path, images.pixels(pathlib.Path(path)), st, place
    p1, a1, s1, place = mapped(style="short")
    h1 = hashlib.sha1(pathlib.Path(p1).read_bytes()).hexdigest()
    pathlib.Path(p1).unlink()
    pathlib.Path(p1).with_suffix(".json").unlink()
    p2, a2, _, _ = mapped(style="short")
    assert p1 == p2 and hashlib.sha1(pathlib.Path(p2).read_bytes()).hexdigest() == h1
    assert place["wrap"] == "sphere" and s1["hairs"] > 500
    _, clean, _, _ = mapped(style="clean")
    _, heavy, _, _ = mapped(style="heavy")
    assert clean[..., 0].mean() < 0.25 * a1[..., 0].mean() < heavy[..., 0].mean()
    assert a1[..., 1].mean() < 0.15 * a1[..., 0].mean()   # (dark hairs carry a little of their tone there)
    _, grey, sg, _ = mapped(style="short", grey=0.5)
    assert grey[..., 1].mean() > 0.3 * grey[..., 0].mean() and grey[..., 2].mean() < a1[..., 2].mean()
    assert 0.4 < sg["white"] < 0.6
    # the skin layers: shadow and hairs per pixel, all reading this map
    L = paint.layers(head_spec(hair={"stubble": {"style": "short", "grey": 0.3}}))
    # (the shadow per pixel: its map carries the under-skin shafts, ~0.2 mm dashes a per-vertex layer would lose)
    assert not L["skin:stubble_shadow"].get("_pre") and "skin:stubble_grey" in L
    assert L["skin:stubble"]["mask"][0]["image"]["wrap"] == "sphere"


@_tmp
def test_fade_band_never_darker_than_full():
    """Where the beard thins out (its fade band), nothing is darker or more saturated than where it is full: the
    shadow channel and the hairs' darkness there stay below the full beard's, and the fold lines that cross the band
    (nasolabial, marionette) are a pale, nearly grey multiply confined to the surface's own concavity (on facesliders'
    joint Garrett a saturated red-brown fold line beside his own fold read as streaks beside the mouth)."""
    import colorsys
    spec = head_spec(hair={"stubble": {"style": "short"}})
    J = skin._joints(spec)
    o = stubble_options({"amount": 1.0, "style": "short"})
    path, place, _ = mk.stubble_map(spec, "body", J, o)
    V, N, _ = mk.head_mesh(spec, "body", J)
    V, N = V.astype(float), N.astype(float)
    d = mk.beard_density(J, o, mk.curvature_at(spec, "body", J))(V, N)
    fr = images.frame(spec, {"file": path, **place, "channel": "b"}, parts=["body"])
    u, v, w = images.project(fr, V, N)
    # (the shadow channel carries the under-skin shafts' grain: compared as the eye takes it from a step back, ~1.5 mm)
    from scipy.ndimage import gaussian_filter
    pix = np.array(images.pixels(pathlib.Path(path)), dtype=np.float32)
    pix[..., 2] = gaussian_filter(pix[..., 2], 0.0015 / 0.00006)
    px = images.sample(pix, u, v)
    inside = (w > 0.9) & (u > 0.02) & (u < 0.98) & (v > 0.05) & (v < 0.98)
    full, band = (d > 0.85) & inside, (d > 0.03) & (d < 0.4) & inside
    assert full.sum() > 50 and band.sum() > 50
    assert np.percentile(px[band, 2], 99) <= np.percentile(px[full, 2], 50) + 0.02
    L = paint.layers(head_spec(age=60, hair={"stubble": {"style": "short"}}))
    folds = L["skin:wrinkle_folds"]
    h, s, val = colorsys.rgb_to_hsv(*folds["color"])
    assert s < 0.15 and val > 0.8, folds["color"]
    assert '"cavity": "concave"' in __import__("json").dumps(folds["mask"])


@_tmp
def test_freckles_no_repeat_and_sun():
    """Freckles are unique: two windows of the map 6 cm apart (the old swatch's period) don't match; they gather on
    the nose and cheeks, not under the chin."""
    spec = head_spec(features={"freckles": 1.0})
    J = skin._joints(spec)
    o = freckle_options({"amount": 1.0})
    path, place, st = mk.freckle_map(spec, "body", J, o)
    a = images.pixels(pathlib.Path(path))[..., 0]
    assert st["freckles"] > 50
    H, W = a.shape
    px = 0.00012
    s = int(0.06 / px)
    w = a[H // 2 - 150:H // 2 + 150, W // 2 - s // 2 - 150:W // 2 - s // 2 + 150]
    v = a[H // 2 - 150:H // 2 + 150, W // 2 + s // 2 - 150:W // 2 + s // 2 + 150]
    if w.std() > 0 and v.std() > 0:
        assert abs(np.corrcoef(w.ravel(), v.ravel())[0, 1]) < 0.3
    V, N, _ = mk.head_mesh(spec, "body", J)
    d = mk.freckle_density(J, {**o, "clump": 0.0})(V.astype(float), N.astype(float))
    io = skin.interocular(J)
    nose = d[_near(V, J["lm_nose_bridge"] + io * np.array([0, 0, -0.3]))]
    under = d[_near(V, J["lm_chin"] + io * np.array([0, 0.5, -0.2]))]
    assert nose > 0.3 and under < 0.05, (nose, under)


@_tmp
def test_patchy_is_missing_hair_and_freckles_fade_out():
    """A patchy beard keeps the moustache and the chin's underside and leaves the cheeks bare (noise blobs on the
    cheek read as stains in four blind reads); freckles peak on the nose bridge and upper cheek and fade outward
    without stopping dead at the cheek's side (skin3 measured 0.01 of the peak there, refs 0.1-0.9)."""
    spec = head_spec(hair={"stubble": {"style": "patchy"}})
    J = skin._joints(spec)
    io = skin.interocular(J)
    V, N, _ = mk.head_mesh(spec, "body", J)
    V, N = V.astype(float), N.astype(float)
    o = stubble_options({"amount": 1.0, "style": "patchy"})
    d = mk.beard_density(J, o, mk.curvature_at(spec, "body", J))(V, N)
    def front(field, p, r=0.003, ny=-0.3):   # the most a field reaches on skin facing forward within r of p, seen from the front
        p = np.asarray(p, float)
        m = (np.linalg.norm(V[:, [0, 2]] - p[[0, 2]], axis=1) < r) & (N[:, 1] < ny)
        return float(field[m].max()) if m.any() else 0.0
    mous = front(d, np.asarray(J["lm_lip_upper"]) + [0.006, 0, 0.004])
    cheek = front(d, np.asarray(J["lm_mouth_corner.L"]) + io * np.array([0.3, 0.0, 0.2]))
    assert mous > 0.3 and cheek < 0.25 * mous, (mous, cheek)
    fd = mk.freckle_density(J, {**freckle_options({"amount": 1.0}), "clump": 0.0})(V, N)
    up = front(fd, np.asarray(J["lm_lid_lower.L"]) + io * np.array([0.0, 0.0, -0.35]))
    out = front(fd, np.asarray(J["lm_lid_lower.L"]) + io * np.array([0.3, 0.0, -0.35]), ny=0.0)   # (this test head is narrow)
    assert up > 0.3 and 0.05 * up < out < up, (up, out)


if __name__ == "__main__":
    for t in (test_beard_zones_from_landmarks, test_stubble_map_deterministic_and_styles, test_fade_band_never_darker_than_full,
              test_freckles_no_repeat_and_sun, test_patchy_is_missing_hair_and_freckles_fade_out):
        t()
        print("ok", t.__name__)
