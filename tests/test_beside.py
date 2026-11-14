"""look_beside (beside.py): the model beside its reference view, the worst places and the grab that fixes each."""
import copy

import numpy as np
import pytest
from PIL import Image

from hifipushie import beside, refread, store
from hifipushie.featurerays import depth_image
from hifipushie.spec import empty_spec

K = 0.002  # metres per pixel of the made-up reference


def _figure():
    s = empty_spec()
    # (the torso stands on z = 0: a reference view's lowest row is the ground)
    s["joints"] = {"pelvis": {"pos": [0, 0, 0.2]}, "head": {"pos": [0, 0, 0.53]}, "ear.L": {"pos": [0.13, 0, 0.69]}}
    s["blobs"] = {"torso": {"at": "pelvis", "size": [0.2, 0.18, 0.2]},
                  "head": {"at": "head", "size": [0.2, 0.17, 0.16]},
                  "ear.L": {"at": "ear.L", "size": [0.045, 0.025, 0.07], "blend": 0.02}}
    return s


@pytest.fixture()
def home(tmp_path, monkeypatch):
    """A model `fig` whose reference is its own front view, as a cut-out picture read by read_reference."""
    monkeypatch.setattr(store, "HOME", tmp_path)
    store.save("ref", _figure(), "the reference's own shape")
    _, whole = beside._model("ref", 144)
    W, H = 320, 460
    cam = refread.ortho_camera("front", (W, H), K, W / 2, H - 20)
    hit = np.isfinite(depth_image(whole, cam))
    rgba = np.zeros((H, W, 4), np.uint8)
    rgba[hit] = (200, 150, 140, 255)
    Image.fromarray(rgba, "RGBA").save(tmp_path / "sheet.png")
    top = np.nonzero(hit.any(1))[0]
    height = (top[-1] + 1 - top[0]) * K
    store.save("fig", _figure(), "start")
    from hifipushie import server
    server.read_reference("fig", image=str(tmp_path / "sheet.png"), views=["front"], height=float(height))
    return tmp_path


def test_a_model_that_is_its_reference_has_nothing_to_list(home):
    r = beside.compare("fig", resolution=144)["views"]["front"]
    assert r["iou"] > 0.97 and r["places"] == []


def test_a_short_ear_is_the_first_place_and_its_grab_mends_it(home):
    from hifipushie import server
    s = store.load("fig")
    s["blobs"]["ear.L"]["size"] = [0.045, 0.025, 0.045]  # the ears end 2.5 cm lower than the reference's
    store.save("fig", s, "short ears")
    before = beside.compare("fig", resolution=144)["views"]["front"]
    p = before["places"][0]
    assert p["kind"] == "short" and p["mass"] == "ear.L" and p["at"][0] > 0  # said once, for the stored side
    assert not any(q["twin"] for q in before["places"])  # the right ear's same faults are not listed again
    assert 0.015 < p["off"] < 0.035 and f'of=["ear.L"]' in p["grab"]
    server.grab("fig", of=[p["mass"]], view="front", at=p["at"], to=p["to"], radius=p["radius"])
    after = beside.compare("fig", resolution=144)["views"]["front"]
    assert after["iou"] > before["iou"] + 0.005
    short = [q for q in after["places"] if q["mass"] == "ear.L" and q["kind"] == "short"]
    assert not short or short[0]["area"] < 0.5 * p["area"]


def test_an_ignored_mass_is_left_out_and_a_view_that_is_not_there_is_named(home):
    r = beside.compare("fig", ignore=["ear.L"], resolution=144)
    assert r["ignored"] == ["ear.L", "ear.R"]
    assert any(p["kind"] == "short" for p in r["views"]["front"]["places"])  # the reference's ears, with no model ear
    with pytest.raises(ValueError, match="no flat reference view"):
        beside.compare("fig", views=["side"])
    with pytest.raises(ValueError, match="no mass called"):
        beside.compare("fig", ignore=["nose"])


def test_the_tool_gives_a_picture_a_view_and_the_text(home):
    from hifipushie import server
    out = server.look_beside("fig", save=str(home / "pics"))
    assert len(out) == 2 and "front: outline overlap" in out[-1] and "next:" in out[-1]
    im = Image.open(home / "pics" / "beside_front.png")
    assert im.width > 1.4 * im.height  # three panels of an upright figure, side by side
