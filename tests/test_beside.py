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


def test_a_short_ear_is_the_first_place_said_once_and_the_mass_s_own_size_mends_it(home):
    s = store.load("fig")
    tall = list(s["blobs"]["ear.L"]["size"])
    s["blobs"]["ear.L"]["size"] = [0.045, 0.025, 0.045]  # the ears end 2.5 cm lower than the reference's
    store.save("fig", s, "short ears")
    before = beside.compare("fig", resolution=144)["views"]["front"]
    p = before["places"][0]
    assert p["kind"] == "short" and p["mass"] == "ear.L" and p["at"][0] > 0  # said once, for the stored side
    assert not any(q["twin"] for q in before["places"])  # the right ear's same faults are not listed again
    assert 0.015 < p["off"] < 0.035 and "grab" not in p  # where and how far: no fix handed over
    s["blobs"]["ear.L"]["size"] = tall
    store.save("fig", s, "the ear its own size again")
    after = beside.compare("fig", resolution=144)["views"]["front"]
    assert after["iou"] > before["iou"] + 0.005 and not [q for q in after["places"] if q["mass"] == "ear.L"]


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


def test_a_difference_kept_on_purpose_is_shown_apart_and_not_counted(home):
    s = store.load("fig")
    tall = list(s["blobs"]["ear.L"]["size"])
    s["blobs"]["ear.L"]["size"] = [0.045, 0.025, 0.045]
    store.save("fig", s, "short ears")
    before = beside.compare("fig", resolution=144)["views"]["front"]
    p = before["places"][0]
    with pytest.raises(ValueError, match="say why"):
        beside.set_on_purpose("fig", [{"view": "front", "at": p["at"], "why": "ok"}])
    beside.set_on_purpose("fig", [{"view": "front", "at": p["at"], "why": "short ears, on purpose for this test"}])
    res = beside.compare("fig", resolution=144)
    after = res["views"]["front"]
    assert not any(q["mass"] == "ear.L" and np.hypot(q["at"][0] - p["at"][0], q["at"][1] - p["at"][1]) < 0.03
                   for q in after["places"])
    assert after["on_purpose"][0]["why"].startswith("short ears") and after["iou"] > before["iou"]
    assert after["on_purpose"][0]["area"] > 1.6 * p["area"]  # the one record holds for the right ear too
    said = beside.text("fig", res)
    assert "not listed and not counted: short ears" in said and "kept on record" in said
    s["blobs"]["ear.L"]["size"] = tall  # mended: the record says it has nothing to stand for
    store.save("fig", s, "ears as the reference")
    res = beside.compare("fig", resolution=144)
    assert res["stale"] and "nothing differs there now" in beside.text("fig", res)
    beside.set_on_purpose("fig", [{"view": "front", "at": p["at"], "remove": True}])
    assert beside.on_purpose("fig") == []


def test_a_piece_that_touches_nothing_is_said_to_float(home):
    s = store.load("fig")
    s["joints"]["tail"] = {"pos": [0, 0.26, 0.2]}
    s["blobs"]["tail"] = {"at": "tail", "size": [0.02, 0.03, 0.02]}  # 5 cm clear of the torso's back
    store.save("fig", s, "a tail in the air")
    res = beside.compare("fig", resolution=144)
    assert [f["mass"] for f in res["floating"]] == ["tail"] and 0.03 < res["floating"][0]["gap"] < 0.07
    assert "FLOATS: tail touches nothing" in beside.text("fig", res)
    s["joints"]["tail"]["pos"] = [0, 0.2, 0.2]  # sunk into the back
    store.save("fig", s, "a tail on the body")
    assert beside.compare("fig", resolution=144)["floating"] == []


@pytest.fixture()
def painted(home):
    """`fig` with a concept picture of its own shape from the front right, and that picture's camera."""
    import json

    from hifipushie import matched
    _, whole = beside._model("ref", 144)
    cam = {"az": -30.0, "el": 7.0, "roll": 0.0, "f_px": 900.0, "aim": [0.0, 0.0, 0.4], "dist": 3.0, "size": [400, 480],
           "iou": 0.99, "label": "concept"}
    hit = np.isfinite(depth_image(whole, cam))
    rgba = np.zeros((480, 400, 4), np.uint8)
    rgba[hit] = (220, 150, 140, 255)
    Image.fromarray(rgba, "RGBA").save(home / "painting.png")
    cam["image"] = str(home / "painting.png")
    p = matched.cam_path("fig", "concept")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(cam))
    return home


def test_the_painting_is_a_view_of_its_own_and_says_which_side_the_camera_is_on(painted):
    res = beside.compare("fig", resolution=144)
    assert list(res["views"]) == ["front", "painting"]
    r = res["views"]["painting"]
    assert r["iou"] > 0.96 and r["places"] == [] and "front right" in r["side"] and '".R" ones' in r["side"]
    assert r["picture"].width > 2.2 * r["picture"].height  # three panels
    assert "painting (the concept's own angle): outline overlap" in beside.text("fig", res)


def test_a_short_ear_shows_in_the_painting_on_the_ear_and_can_be_kept_on_purpose(painted):
    s = store.load("fig")
    s["blobs"]["ear.L"]["size"] = [0.045, 0.025, 0.04]
    store.save("fig", s, "short ears")
    r = beside.compare("fig", views=["painting"], resolution=144)["views"]["painting"]
    ears = [p for p in r["places"] if p["mass"] == "ear.L" and p["kind"] == "short"]
    assert ears and "up" in ears[0]["way"] and len(ears[0]["at"]) == 2
    beside.set_on_purpose("fig", [{"view": "painting", "at": ears[0]["at"], "why": "short ears, on purpose for this test"}])
    res = beside.compare("fig", views=["painting"], resolution=144)
    after = res["views"]["painting"]
    assert len([p for p in after["places"] if p["mass"] == "ear.L"]) < len(ears) + len([p for p in r["places"] if p["mass"] == "ear.L" and p["kind"] != "short"])
    assert after["on_purpose"] and after["iou"] > r["iou"] and "round pixel" in beside.text("fig", res)


def test_the_painting_without_a_camera_is_asked_for_by_name(home):
    with pytest.raises(ValueError, match="fit_concept_camera"):
        beside.compare("fig", views=["painting"])
    assert "fit_concept_camera" in beside.text("fig", beside.compare("fig", resolution=144))


def test_a_place_names_its_mass_and_no_grab_and_the_proportions_are_read(home):
    s = store.load("fig")
    s["blobs"]["head"]["size"] = [0.17, 0.15, 0.14]  # a head 6 cm narrower than the reference's
    store.save("fig", s, "a small head")
    res = beside.compare("fig", resolution=144)
    said = beside.text("fig", res)
    assert "grab(" not in said and "a grab from" not in said and "on head" in said
    pr = res["views"]["front"]["proportions"]
    wide = [m for m in pr["landmarks"] if m["kind"] == "widest"]
    assert len(wide) >= 2  # the head and the body, found on the reference itself
    head = min(wide, key=lambda m: abs(m["z"] - 0.53))
    assert abs(head["reference"] - 0.40) < 0.015 and abs(head["model"] - 0.34) < 0.015
    assert pr["ratios"] and pr["ratios"][0]["model"] < pr["ratios"][0]["reference"] - 0.08
    assert "proportions:" in said and "the model's upper mass is small against its lower" in said


def test_paired_masses_are_left_out_of_the_model_s_own_width(home):
    s = store.load("fig")
    s["joints"]["arm.L"] = {"pos": [0.19, 0, 0.2]}  # (the reference picture is cut 2 cm outside the figure)
    s["blobs"]["arm.L"] = {"at": "arm.L", "size": [0.03, 0.04, 0.04]}  # a stub of an arm at the body's widest
    store.save("fig", s, "arms out")
    pr = beside.compare("fig", resolution=144)["views"]["front"]["proportions"]
    body = min((m for m in pr["landmarks"] if m["kind"] == "widest"), key=lambda m: abs(m["z"] - 0.2))
    assert abs(body["model"] - body["reference"]) < 0.015 and body["whole"] > body["model"] + 0.03
    assert pr["ratios"] == []  # a width with limbs in it is not set against another
