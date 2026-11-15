"""export_asset(recolour_masks=...) (asset_recolour): a small four-part prop exported with and without masks.

The masked parts bake a neutral grey base; the mask channels are on exactly the texels the unmasked export paints in
that part's colour; texels of the unmasked part are the same in both exports; each channel's default (the part's own
colour) is in the json and the shading notes; the oxidegen runner's schema keeps the parameter."""
import json
import os
import tempfile
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

_TMP = tempfile.mkdtemp(prefix="hp-recolour-")
os.environ.setdefault("HIFIPUSHIE_HOME", _TMP)

from hifipushie import asset, store  # noqa: E402
from hifipushie.spec import SpecError  # noqa: E402

COLORS = {"wall": "#b03020", "trim": "#30a040", "roof": "#2040b0", "base": "#c0a060"}
MASKS = [{"R": ["wall"], "G": ["trim"]}, {"B": ["roof"]}]


def _spec() -> dict:
    boxes = {"wall": [-0.15, 0.08], "trim": [0.0, 0.08], "roof": [0.15, 0.08], "base": [0.0, -0.04]}
    return {"symmetry": False, "blend": 0.0, "joints": {"c": {"pos": [0, 0, 0], "r": 0.01}},
            "parts": {p: {"color": c} for p, c in COLORS.items()},
            "blobs": {p: {"shape": "box", "at": [x, 0, z], "size": [0.06, 0.06, 0.06] if p != "base" else [0.24, 0.06, 0.03],
                          "part": p} for p, (x, z) in boxes.items()}}


def _srgb(h: str) -> np.ndarray:
    return np.array([int(h[i:i + 2], 16) for i in (1, 3, 5)], float)


@pytest.fixture(scope="module")
def exports():
    store.HOME = Path(_TMP)
    store.save("crate", _spec())
    out = {}
    for tag, masks in (("plain", None), ("masked", MASKS)):
        d = Path(_TMP) / tag
        d.mkdir()
        info = asset.export("crate", d, triangles=600, texture=256, resolution=96, recolour_masks=masks)
        out[tag] = (d, info)
    return out


def _img(d: Path, name: str) -> np.ndarray:
    return np.asarray(Image.open(d / name), float)


def test_masked_base_is_neutral_and_masks_cover_the_parts(exports):
    (dp, ip), (dm, im) = exports["plain"], exports["masked"]
    assert "recolour" not in ip and not any("mask" in k for k in ip["maps"])  # no masks: no new output
    plain, masked = _img(dp, "crate_basecolor.png")[..., :3], _img(dm, "crate_basecolor.png")[..., :3]
    m0, m1 = _img(dm, "crate_mask0.png"), _img(dm, "crate_mask1.png")
    assert m0.shape[-1] == 4 and m1.shape[-1] == 4
    on = {"wall": m0[..., 0] > 127, "trim": m0[..., 1] > 127, "roof": m1[..., 2] > 127}
    assert not (m0[..., 2:] > 0).any() and not (m1[..., [0, 1, 3]] > 0).any()  # unused channels stay empty
    anym = on["wall"] | on["trim"] | on["roof"]
    assert sum(o.astype(int) for o in on.values()).max() == 1  # exclusive
    # neutral where masked: no hue left (painted shading stays as light / dark)
    sat = masked.max(-1) - masked.min(-1)
    assert sat[anym].max() <= 3, sat[anym].max()
    assert masked[anym].mean() > 170  # near white at the default
    # the masks lie where the plain export paints each part's colour (the same low poly and atlas)
    for p, o in on.items():
        near = np.abs(plain - _srgb(COLORS[p])).max(-1) < 30
        assert o.sum() > 200, (p, o.sum())
        assert (near & o).sum() / near.sum() > 0.97, (p, (near & o).sum(), near.sum())
        assert (near & o).sum() / o.sum() > 0.9, (p, (near & o).sum(), o.sum())
    # the unmasked part is baked as before
    base = np.abs(plain - _srgb(COLORS["base"])).max(-1) < 30
    # (only texels in the gaps between islands can differ: the plain export fills them from the nearest baked texel,
    # the masks from the nearest drawn one)
    assert base.sum() > 200 and (base & anym).sum() / base.sum() < 0.02, (base & anym).sum() / base.sum()
    assert np.abs(masked[~anym] - plain[~anym]).max() <= 1


def test_defaults_recorded(exports):
    d, info = exports["masked"]
    rc = info["recolour"]
    assert rc["masks"] == ["crate_mask0.png", "crate_mask1.png"] and rc["base_white"] == asset.RECOLOUR_BASE_WHITE
    got = {(c["mask"], c["channel"]): c for c in rc["channels"]}
    assert set(got) == {(0, "R"), (0, "G"), (1, "B")}
    for (k, ch), p in {(0, "R"): "wall", (0, "G"): "trim", (1, "B"): "roof"}.items():
        assert got[(k, ch)]["parts"] == [p]
        assert np.abs(_srgb(got[(k, ch)]["default"]) - _srgb(COLORS[p])).max() < 12, (p, got[(k, ch)]["default"])
    sh = json.loads(Path(info["shading"]["json"]).read_text())
    mats = [m for m in sh["materials"] if (m.get("params") or {}).get("recolour")]
    assert len(mats) == 1 and {"mask0", "mask1"} <= set(mats[0]["maps"])
    assert mats[0]["formulas"][0].startswith("albedo = basecolor * (1 - sum(m)")
    assert "Recolour channels" in Path(info["shading"]["md"]).read_text()


def test_bad_masks_refused():
    store.HOME = Path(_TMP)
    store.save("crate2", _spec())
    with pytest.raises(SpecError, match="no part"):
        asset.export("crate2", Path(_TMP), triangles=600, texture=256, resolution=96, recolour_masks=[{"R": ["door"]}])
    from hifipushie import asset_recolour
    parts = {"a": {"atlas": 0}, "b": {"atlas": 0}}
    with pytest.raises(SpecError, match="one channel per part"):
        asset_recolour.resolve([{"R": ["a"]}, {"G": ["a"]}], parts, {})
    with pytest.raises(SpecError, match="channel"):
        asset_recolour.resolve([{"X": ["a"]}], parts, {})
    with pytest.raises(SpecError, match="atlases"):
        asset_recolour.resolve([{"R": ["a"], "G": ["b"]}], {"a": {"atlas": 0}, "b": {"atlas": 1}}, {})


def test_oxidegen_runner_keeps_the_parameter():
    from hifipushie import artist
    caps, _ = artist.capabilities()
    c = next(x for x in caps if x["tool"] == "export_asset")
    assert "recolour_masks" in c["input_schema"]["properties"]
