"""Terrain styles (terrain_style.py): sheets, tileable layer textures, the zone partition and weights, the files and
manifest section an engine reads. Script-style: `uv run python tests/test_terrain_style.py` (~30 s, no heavy slot)."""

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from hifipushie import terrain_style as ts  # noqa: E402
from hifipushie import terrain_mesh as tm  # noqa: E402

REFS = {k: dict(v) for k, v in tm.LAYERS.items()}


class Stub:
    """Just what terrain_design.region and the style maps read off a Terrain."""

    def __init__(self, n=129, size=256.0, zones=None, styles=None):
        self.cell = size / (n - 1)
        self.xs = np.linspace(0, size, n)
        self.ys = np.linspace(0, size, n)
        self.X, self.Y = np.meshgrid(self.xs, self.ys)
        self.zones = zones or {}
        self.lakes, self.sites, self.masks = {}, {}, {}
        self.spec = {"extent": [[0, 0], [size, size]], "zones": self.zones, "styles": styles or {}}


def test_sheets():
    for nm in ("realistic", "blobby", "anime"):
        st = ts.sheet(nm)
        assert st["name"] == nm and "layers" in st and "seasons" in st
        for lay in ts.STYLE_LAYERS:
            L = ts.layer_sheet(st, lay)
            assert L.get("ops"), (nm, lay)
    try:
        ts.sheet("nope")
    except ValueError as e:
        assert "no terrain style" in str(e)
    else:
        raise AssertionError("an unknown style must fail")
    st = ts.sheet("blobby", {"layers": {"grass": {"scale_m": 9.0}}})
    assert ts.layer_sheet(st, "grass")["scale_m"] == 9.0
    assert ts.layer_sheet(st, "scrub")["scale_m"] == 9.0  # (scrub is `like` grass)


def test_textures_tile_and_keep_their_colour():
    for nm in ("blobby", "anime", "realistic", "cartoon", "pixar"):
        st = ts.sheet(nm)
        for lay in ("grass", "rock", "sand", "earth"):
            # (contract 2: soft layers are laid from the top only; rock is triplanar)
            assert ts.layer_sheet(st, lay).get("projection", "top") == ("triplanar" if lay == "rock" else "top"), (nm, lay)
            col = ts.layer_colour(st, lay, REFS)
            S = ts.texture(st, lay, col, 256)
            mean = S["albedo_linear"].reshape(-1, 3).mean(0)
            assert np.allclose(mean, ts._srgb_lin(col), atol=0.01), (nm, lay, mean)
            seam = ts.tileable(S["albedo"])
            assert seam < 1.5, (nm, lay, seam)  # (the manifest's 'shows' limit)
            assert np.isfinite(S["normal"]).all() and (S["normal"][..., 2] > 0).all()


def test_blobby_matches_plants_colour_turn():
    st = ts.sheet("blobby")
    c = ts.layer_colour(st, "grass", REFS)
    import colorsys
    h0, s0, v0 = colorsys.rgb_to_hsv(*REFS["grass"]["color"])
    h1, s1, v1 = colorsys.rgb_to_hsv(*c)
    assert abs(s1 - min(1, s0 * 1.3)) < 1e-6 and abs(v1 - min(1, v0 * 1.15)) < 1e-6


def test_partition_and_weights():
    T = Stub(zones={"downs": "west", "paint": "east", "hill": {"polygon": [[170, 170], [230, 170], [230, 230], [170, 230]]}},
             styles={"blobby": "downs", "anime": "paint", "cartoon": "hill"})
    T.spec["styles"] = {"blobby": "downs", "anime": "paint"}
    styles = ts.resolve(T.spec)
    F = ts.style_fields(T, styles)
    assert F["order"] == ["blobby", "anime", "realistic"]
    W = sum(F["w"].values())
    assert np.allclose(W, 1.0)
    # the two zones meet: no realistic between them, half and half on the line
    assert F["w"]["realistic"].max() < 1e-6
    mid = np.argmin(np.abs(T.xs - 128))
    row = 64
    assert abs(F["w"]["blobby"][row, mid] - 0.5) < 0.2
    assert F["w"]["blobby"][row, 0] > 0.999 and F["w"]["anime"][row, -1] > 0.999
    assert F["sd"]["blobby"][row, 0] > 0 > F["sd"]["blobby"][row, -1]
    # an island zone: realistic around it, a later style wins where zones overlap
    T.spec["styles"] = {"anime": "paint", "blobby": "hill"}
    F = ts.style_fields(T, ts.resolve(T.spec))
    j, i = np.argmin(np.abs(T.ys - 200)), np.argmin(np.abs(T.xs - 200))
    assert F["w"]["blobby"][j, i] > 0.99  # (inside the hill, which is also in the east zone)
    assert F["w"]["realistic"][j, 0] > 0.99


def test_write_files_manifest_and_cache():
    d = Path(tempfile.mkdtemp(prefix="ts_test_"))
    cache = Path(tempfile.mkdtemp(prefix="ts_cache_"))
    os.environ["HIFIPUSHIE_STYLE_CACHE"] = str(cache)
    try:
        T = Stub(zones={"downs": "west"}, styles={"blobby": "downs"})
        layers = ["grass", "rock", "sand"]
        refs = {k: REFS[k] for k in layers}
        tiles = [(i, j, (i * 128.0, j * 128.0, (i + 1) * 128.0, (j + 1) * 128.0)) for j in range(2) for i in range(2)]
        sec = ts.write(d / "a", T, refs, tiles=tiles, layers=layers, px=128)
        assert sec["order"] == ["blobby", "realistic"]
        names = [s["name"] for s in sec["styles"]]
        assert names == ["blobby", "realistic"]
        for s in sec["styles"]:
            for lay in layers:
                L = s["layers"][lay]
                for k in ("albedo", "normal", "height"):
                    assert (d / "a" / L[k]).exists(), L[k]
                assert set(L["seasons"]) == set(ts.SEASONS)
                assert L["seasons"]["summer"]["tint_linear"] == [1.0, 1.0, 1.0]
            assert s["snow"]["by_normal"]["from"] < s["snow"]["by_normal"]["to"]
        assert (d / "a" / "styles" / "blobby_sd.png").exists() and (d / "a" / "styles" / "weights0.png").exists()
        reach = {(t["i"], t["j"]): t["styles"] for t in sec["tiles"]}
        assert reach[(0, 0)] == ["blobby", "realistic"] or "blobby" in reach[(0, 0)]
        assert reach[(1, 1)] == ["blobby", "realistic"]  # (the band crosses x = 128: both tiles see both)
        json.dumps(sec)  # (the section is plain json)
        # a second write from the cache gives the same bytes
        sec2 = ts.write(d / "b", T, refs, tiles=tiles, layers=layers, px=128)
        for p in (d / "a").rglob("*.png"):
            q = d / "b" / p.relative_to(d / "a")
            assert p.read_bytes() == q.read_bytes(), p
        assert sec2 == sec
    finally:
        shutil.rmtree(d, ignore_errors=True)
        shutil.rmtree(cache, ignore_errors=True)
        os.environ.pop("HIFIPUSHIE_STYLE_CACHE", None)


def test_resolve_errors():
    for bad in ({"blobby": {"in": "west", "wat": 1}}, {"blobby": {"band": 3}}, {"nostyle": "west"}):
        try:
            ts.resolve({"styles": bad})
        except ValueError:
            pass
        else:
            raise AssertionError(bad)


COAST = {"world": {"kind": "coast", "base": 10}, "extent": [[0, 0], [128, 128]], "cell": 0.64,
         "tilt": {"down": "south", "grade": 0.25},
         "sea": {"level": 0, "shore": "cliffs", "cliffs": {"height": [14, 20]}},
         "cover": [{"type": "meadow", "in": "everywhere"}, {"type": "rock", "in": "cliffs"}],
         "export": {"tiles": {"tile": 32}}}


def _field(styles=None):
    import copy
    from hifipushie import terrain
    d = Path(tempfile.mkdtemp())
    sp = copy.deepcopy(COAST)
    (d / "spec.json").write_text(json.dumps(sp))
    T = terrain.load(d / "spec.json")
    if styles:
        T.spec["zones"] = {"downs": "west", "paint": "east"}
        T.zones = dict(T.spec["zones"])
        T.spec["styles"] = styles
    cfg = {**tm.DEFAULTS, **T.spec["export"]["tiles"]}
    return T, tm.build_field(T, cfg)[0]


def test_rock_shape_by_zone():
    """A style's rock shape is in the field only in its zone (+ its band): the realistic zone's field is unchanged
    bit for bit; blobby's cliffs lose the facets / bedding / blocks and get pillow grooves; the field is continuous
    across the band."""
    T0, f0 = _field()
    T1, f1 = _field({"blobby": "downs"})  # (blobby in the west; east realistic)
    assert f1.styles and not f0.styles
    # cliff points (sheer, south) on a few columns each side
    xs = np.linspace(4, 124, 61)
    ys = np.linspace(0, 40, 81)
    X, Y = np.meshgrid(xs, ys)
    h, s = f0.column(X.ravel(), Y.ravel())
    P = np.c_[X.ravel(), Y.ravel(), h - 0.2]
    a, b = f0.value(P), f1.value(P)
    east = P[:, 0] > 64 + 20  # (past the 10 m rock band, the smoothing and the grid filters)
    assert np.array_equal(a[east], b[east]), np.abs(a[east] - b[east]).max()
    west = P[:, 0] < 50
    assert np.abs(a[west] - b[west]).max() > 0.05  # (the blobby side changed)
    # continuity across the band: neighbouring points 0.1 m apart along x differ by little
    xl = np.arange(40, 90, 0.1)
    yl = np.full_like(xl, float(ys[np.argmin(np.abs(s.reshape(X.shape).min(1) - s.min()))]))
    hl, _ = f1.column(xl, yl)
    Fl = f1.value(np.c_[xl, yl, hl])
    h0l, _ = f0.column(xl, yl)
    F0l = f0.value(np.c_[xl, yl, h0l])
    step, step0 = np.abs(np.diff(Fl)).max(), np.abs(np.diff(F0l)).max()
    print("  steps along the band (styled, realistic):", round(float(step), 3), round(float(step0), 3))
    assert step < max(2.0 * step0, 0.15), (step, step0)  # (no jump where the styles hand over)


def test_pillow_is_smooth_and_bounded():
    rng = np.random.default_rng(1)
    p = rng.random((20000, 3)) * 20
    c = ts.pillow_carve(p, 3.0, 0.8, 0.4, 5)
    assert c.min() >= 0 and c.max() <= 0.8 + 1e-9 and c.mean() > 0.02
    assert np.array_equal(c, ts.pillow_carve(p, 3.0, 0.8, 0.4, 5))
    q = p + np.array([0.01, 0, 0])
    assert np.abs(ts.pillow_carve(q, 3.0, 0.8, 0.4, 5) - c).max() < 0.05


if __name__ == "__main__":
    for k, f in list(globals().items()):
        if k.startswith("test_") and callable(f):
            f()
            print("ok", k)
