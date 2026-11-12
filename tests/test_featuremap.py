"""The feature map (refread.py, featuremap.py, featuresee.py) on a known answer: a small figure draws its own
turnaround (each element in its own colour, shaded), the turnaround is read and marked, and the report must call
the true model right and find every planted fault: a feature not made, moved, shrunk, buried.

Run: pytest tests/test_featuremap.py"""
from __future__ import annotations

import numpy as np
import pytest
from PIL import Image

from hifipushie import featuremap, featuresee, masses, matched, refread, sdf, store
from hifipushie.spec import compile_prims

K, W, H, GROUND = 0.0025, 200, 350, 340
COLS = {"body": (120, 125, 150), "head": (200, 170, 120), "snout": (235, 160, 150), "eye.L": (240, 200, 40),
        "eye.R": (240, 200, 40), "ear.L": (110, 80, 70), "ear.R": (110, 80, 70)}
ORDER = ("body", "head", "snout", "ear.L", "ear.R", "eye.L", "eye.R")


def _spec(eye=(0.06, -0.125, 0.67), snout=0.06, move=(0.0, 0.0, 0.0)) -> dict:
    def at(x, y, z):
        return [x + move[0], y + move[1], z + move[2]]
    return {"symmetry": True, "blend": 0.02, "joints": {}, "bones": {}, "blobs": {
        "body": {"at": at(0, 0, 0.25), "size": [0.16, 0.13, 0.25]},
        "head": {"at": at(0, -0.02, 0.62), "size": [0.14, 0.13, 0.13]},
        "snout": {"at": at(0, -0.15, 0.58), "size": [snout, 0.06, snout * 5 / 6]},
        "eye.L": {"at": at(*eye), "size": [0.03, 0.02, 0.03], "blend": 0.003},
        "ear.L": {"at": at(0.12, 0.0, 0.76), "size": [0.05, 0.02, 0.06], "blend": 0.01}}}


def _truth(name: str, kind: str):
    cam = refread.ortho_camera(kind, (W, H), K, W / 2, GROUND)
    fm = {"features": {n: {"marks": {kind: {}}} for n in ORDER}}
    return cam, featuresee.footprints(store.load(name), fm, {n: [n] for n in ORDER}, [kind], {kind: cam}, 128)


def _sheet(name: str, path) -> None:
    """front | side of the figure, each element's footprint in its colour, shaded: a stand-in turnaround."""
    sheet = Image.new("RGBA", (2 * W + 60, H + 20), (0, 0, 0, 0))
    for i, kind in enumerate(("front", "side")):
        _, fp = _truth(name, kind)
        d = fp["depth"][kind]
        rgb = np.zeros((H, W, 3)) + COLS["body"]
        for n in ORDER:
            rgb[fp["masks"][(n, kind)]] = COLS[n]
        rgb *= 0.5 + 0.5 * featuresee.relief(d, K)[..., None] / 255
        a = np.where(np.isfinite(d), 255, 0)
        sheet.paste(Image.fromarray(np.dstack([rgb, a]).astype(np.uint8), "RGBA"), (20 + i * (W + 20), 10))
    sheet.save(path)


def _to_crop(truth: np.ndarray, view: str, box) -> np.ndarray:
    """A mask in a view's own tile (W x H), as the view's crop of the sheet has it."""
    sheet = np.zeros((H + 20, 2 * W + 60), bool)
    x = 20 if view == "front" else 40 + W
    sheet[10:10 + H, x:x + W] = truth
    return sheet[box[1]:box[3], box[0]:box[2]]


def _pick(name: str, view: str, truth: np.ndarray, box) -> list[int]:
    """The patches a sculptor would point at for a feature: those lying mostly inside it."""
    lab = refread.patches(name, view)
    t = _to_crop(truth, view, box)
    ids = []
    for i in range(1, int(lab.max()) + 1):
        m = lab == i
        if m.any() and (m & t).sum() > 0.6 * m.sum():
            ids.append(i)
    return ids


@pytest.fixture(scope="module")
def fig(tmp_path_factory):
    with pytest.MonkeyPatch.context() as mp:
        home = tmp_path_factory.mktemp("featuremap")
        mp.setattr(store, "HOME", home)
        store.save("fig", _spec(), "test")
        sheet = home / "sheet.png"
        _sheet("fig", sheet)
        top = max(float(p.hi[2]) for p in compile_prims(store.load("fig")))
        recs = refread.read("fig", str(sheet), ["front", "side"], height=top)
        fm = featuremap.add_views("fig", recs)
        marks = {}
        for kind in ("front", "side"):
            _, fp = _truth("fig", kind)
            for n in ORDER:
                if fp["masks"][(n, kind)].any():
                    ids = _pick("fig", kind, fp["masks"][(n, kind)], fm["views"][kind]["box"])
                    if ids:
                        marks.setdefault(n, {})[kind] = {"patches": ids}
        yield {"home": home, "marks": marks, "top": top}


def _features(marks, skip=()):
    on = {"head": "body", "snout": "head", "eye.L": "head", "eye.R": "head", "ear.L": "head", "ear.R": "head"}
    return {n: {"kind": "mass", **({"on": on[n]} if n in on else {}), "marks": m} for n, m in marks.items() if n not in skip}


def test_views_get_cameras_at_the_sheets_scale(fig):
    fm = featuremap.load("fig")
    assert set(fm["views"]) == {"front", "side"}
    for v in ("front", "side"):
        rec, cam = fm["views"][v], matched.load_camera("fig", v)
        assert abs(rec["m_per_px"] - K) < 0.02 * K and cam["kind"] == "ortho"
        truth = refread.ortho_camera(v, (W, H), K, W / 2, GROUND)
        P = np.array([[0.06, -0.14, 0.67], [0.0, 0.0, 0.0], [0.12, 0.0, 0.8]])
        a, _ = matched.project(P, cam)
        b, _ = matched.project(P, truth)
        shift = np.array(rec["box"][:2]) - (np.array([20, 10]) if v == "front" else np.array([40 + W, 10]))
        assert np.abs(a + shift - b).max() < 2.5, (v, a + shift, b)
    assert abs(fm["views"]["front"]["centre_px"] + fm["views"]["front"]["box"][0] - 20 - W / 2) < 1.5


def test_a_footprint_sits_where_the_element_is(fig):
    cam, fp = _truth("fig", "front")
    ys, xs = np.where(fp["masks"][("eye.L", "front")])
    want, _ = matched.project(np.array([[0.06, -0.125, 0.67]]), cam)
    assert abs(xs.mean() - want[0, 0]) < 2 and abs(ys.mean() - want[0, 1]) < 2
    assert xs.mean() > W / 2  # the creature's left is at a front view's right
    _, side = _truth("fig", "side")
    assert not side["masks"][("eye.R", "side")].any()  # the far eye is behind the head from its left side
    assert side["masks"][("eye.L", "side")].any()


def test_patches_keep_to_one_feature(fig):
    for n in ("head", "snout", "eye.L", "ear.L"):
        assert "front" in fig["marks"][n], f"no patch lies mostly inside {n}"
    _, fp = _truth("fig", "front")
    fm = featuremap.mark("fig", _features(fig["marks"]))
    for n in ("snout", "eye.L", "ear.L"):
        t = fp["masks"][(n, "front")]
        got = featuremap.mask("fig", n, "front")
        tt = _to_crop(t, "front", fm["views"]["front"]["box"])
        assert (got & tt).sum() / (got | tt).sum() > 0.7, n


def test_the_map_says_what_it_owes(fig):
    fm = featuremap.mark("fig", _features(fig["marks"], skip=("ear.L", "ear.R")), remove=[f for f in ("ear.L", "ear.R")
                                                                                         if f in featuremap.load("fig")["features"]])
    owes = featuremap.checks("fig", fm)
    assert any(o.startswith("UNMARKED front") for o in owes), owes
    fm = featuremap.mark("fig", _features(fig["marks"]))
    assert not [o for o in featuremap.checks("fig", fm) if o.startswith(("UNMARKED", "SIDE", "DISAGREE"))]
    # the right eye's patches named as the left eye: the picture's left is the creature's right
    fm = featuremap.mark("fig", {"eye.L": {"marks": {"front": fig["marks"]["eye.R"]["front"]}}})
    assert any(o.startswith("SIDE eye.L") for o in featuremap.checks("fig", fm))
    # a mark 40 px too low in one view: the two views no longer agree on its height
    box = fm["features"]["snout"]["marks"]["side"]["box"]
    fm = featuremap.mark("fig", {"eye.L": {"marks": {"front": fig["marks"]["eye.L"]["front"]}},
                                 "snout": {"marks": {"side": {"box": [box[0], box[1] + 40, box[2], box[3] + 40]}}}})
    assert any(o.startswith("DISAGREE snout") for o in featuremap.checks("fig", fm))
    # null clears one view's mark; a malformed mark is refused with how it is written
    fm = featuremap.mark("fig", {"snout": {"marks": {"side": None}}})
    assert "side" not in fm["features"]["snout"]["marks"] and "front" in fm["features"]["snout"]["marks"]
    with pytest.raises(ValueError, match="four numbers"):
        featuremap.mark("fig", {"snout": {"marks": {"side": {"box": [[1, 2], [3, 4]]}}}})
    with pytest.raises(ValueError, match="kind is one of"):
        featuremap.mark("fig", {"thing": {"marks": {"front": {"box": [10, 10, 30, 30]}}}})
    with pytest.raises(ValueError, match="no patch"):
        featuremap.mark("fig", {"thing": {"kind": "form", "marks": {"front": {"patches": [9999]}}}})
    featuremap.mark("fig", _features(fig["marks"]), remove=["thing"] if "thing" in featuremap.load("fig")["features"] else None)


def _status(rep):
    return {(r["feature"], r["view"]): r for r in rep["rows"]}


def test_the_true_model_is_right_and_planted_faults_are_found(fig):
    featuremap.mark("fig", _features(fig["marks"]))
    els = {n: [n] for n in fig["marks"]}
    rep = featuresee.report("fig", els, resolution=128)
    assert {r["status"] for r in rep["rows"]} == {"right"}, [r for r in rep["rows"] if r["status"] != "right"]
    # not made: no element is named for the snout
    rep = featuresee.report("fig", {"snout": []}, resolution=128)
    assert rep["by_feature"]["snout"] == "NOT MADE" and rep["by_feature"]["eye.L"] == "right"
    featuresee.report("fig", {"snout": ["snout"]}, resolution=128)
    # moved: the eyes 3 cm higher
    store.save("fig", _spec(eye=(0.06, -0.125, 0.70)), "eye up")
    r = _status(featuresee.report("fig", resolution=128))[("eye.L", "front")]
    assert r["status"] == "OFF" and "above the mark" in r["why"] and 20 < r["dy_mm"] < 40, r
    # shrunk: a snout half the size
    store.save("fig", _spec(snout=0.03), "small snout")
    r = _status(featuresee.report("fig", resolution=128))[("snout", "front")]
    assert r["status"] == "OFF" and "as wide as the mark" in r["why"] and r["wide"] < 0.7, r
    # buried: the eyes sunk inside the head
    store.save("fig", _spec(eye=(0.06, -0.06, 0.67)), "eye buried")
    assert _status(featuresee.report("fig", resolution=128))[("eye.L", "front")]["status"] == "HIDDEN"
    # built 4 cm back and 2 cm into the ground: nothing a picture can know, so the views follow the model and say so
    store.save("fig", _spec(move=(0.0, 0.04, -0.02)), "moved")
    rep = featuresee.report("fig", resolution=128)
    assert {r["status"] for r in rep["rows"]} == {"right"}, [r for r in rep["rows"] if r["status"] != "right"]
    said = " ".join(rep["moved_views"])
    assert "below its own zero" in said and "centre line" in said, rep["moved_views"]
    store.save("fig", _spec(), "back")
    assert featuresee.report("fig", resolution=128)["moved_views"]  # (and back again)
    # a line mark has no size: right where the model has form along it, off where it has none
    box = featuremap.load("fig")["features"]["snout"]["marks"]["front"]["box"]
    y = (box[1] + box[3]) // 2
    featuremap.mark("fig", {"snout_line": {"kind": "form", "on": "head", "marks": {"front": {"line": [[box[0], y], [box[2], y]]}}},
                            "no_line": {"kind": "form", "on": "body", "marks": {"front": {"line": [[60, 250], [100, 250]]}}},
                            "bulge": {"kind": "form", "on": "head", "marks": {"front": {"box": [box[0], box[1], box[2], y]}}}})
    rep = featuresee.report("fig", {"snout_line": ["snout"], "no_line": ["snout"], "bulge": ["="]}, resolution=128)
    assert rep["by_feature"]["snout_line"] == "right" and rep["by_feature"]["no_line"] == "OFF"
    assert rep["by_feature"]["bulge"] == "IN ITS MASS"
    featuremap.mark("fig", {}, remove=["snout_line", "no_line", "bulge"])
    with pytest.raises(ValueError, match="no model element matches"):
        featuresee.report("fig", {"snout": ["snoot"]}, resolution=128)
    featuresee.report("fig", {"snout": ["sn*"]}, resolution=128)  # a pattern picks it


def test_the_tools_return_a_picture_and_the_table(fig):
    from hifipushie import server
    featuremap.mark("fig", _features(fig["marks"]))
    im, text = server.read_reference("fig", view="front", focus=[40, 20, 160, 140])
    assert "patches" in text and len(im.data) > 1000
    im, text = server.mark_features("fig")
    assert "7 features" in text and "masses" in text
    im, text = server.mark_features("fig", view="side")
    from hifipushie import tools_model
    assert "feature map: 7 masses and forms" in tools_model._feature_line("fig") and tools_model._feature_line("none") == ""
    im, text = server.feature_report("fig", {n: [n] for n in fig["marks"]}, view="front", resolution=128)
    assert "0 NOT MADE" in text and "right" in text


def test_a_flat_views_camera_and_the_small_helpers():
    """Fast: no model, no picture read."""
    cam = refread.ortho_camera("front", (200, 300), 0.002, 90.0, 280)
    xy, _ = matched.project(np.array([[0.0, 0.0, 0.0], [0.05, 0.3, 0.1], [-0.05, -0.3, 0.1]]), cam)
    assert np.allclose(xy[0], [90, 280], atol=0.05)                       # the origin: centre line, ground row
    assert np.allclose(xy[1], [115, 230], atol=0.4) and np.allclose(xy[2], [65, 230], atol=0.4)  # depth barely moves it
    side, _ = matched.project(np.array([[0.0, -0.1, 0.1]]), refread.ortho_camera("side", (200, 300), 0.002, 90.0, 280))
    assert side[0, 0] < 90                                                 # in "side" the front (-y) is at the left
    back, _ = matched.project(np.array([[0.05, 0.0, 0.1]]), refread.ortho_camera("back", (200, 300), 0.002, 90.0, 280))
    assert back[0, 0] < 90                                                 # from behind, its left is at the left
    m = np.zeros((40, 60), bool)
    m[5:35, 20:41] = True
    assert abs(refread.mirror_line(m) - 30) <= 0.5
    assert refread.colour_word((240, 200, 40)) == "yellow" and refread.colour_word((30, 30, 30)) == "black"
    assert refread.nice_step(300) == 50 and refread.nice_step(60) == 10
    assert featuremap.twin("ear.L") == "ear.R" and featuremap.twin("nose") is None


def test_masses_are_built_from_their_marks(fig):
    """The figure's masses rebuilt from the marks alone land on the picture: no number typed."""
    featuremap.mark("fig", _features(fig["marks"]))
    true = store.load("fig")
    try:
        store.save("fig", {**true, "blobs": {"body": true["blobs"]["body"]}}, "only a body left: the rest is built")
        res = masses.build("fig", {"body": {"as": "trunk"}, "head": {"as": "trunk", "sections": 5}, "snout": {"as": "ball"},
                                   "eye.L": {"as": "ball"}, "eye.R": {"as": "ball"}, "ear.L": {"as": "tube"},
                                   "ear.R": {"as": "tube"}})
        spec = res["spec"]
        eye = spec["blobs"]["eye.L"]
        assert np.allclose(eye["at"], [0.06, -0.125, 0.67], atol=0.012), eye["at"]   # where the true eye is
        assert "eye.R" not in spec["blobs"]                                           # (mirrored, not built twice)
        widest = max(s["half_width"] for s in spec["blobs"]["body"]["sections"])
        assert abs(widest - 0.16) < 0.02, widest                                      # the true body is 0.16 half wide
        assert res["made"]["ear.R"] == [featuremap.twin(n) for n in res["made"]["ear.L"]]
        rep = featuresee.report("fig", resolution=128)
        assert min(rep["outline"].values()) > 0.9, rep["outline"]
        assert not rep["moved_views"]                                                 # built in the map's own frame
        bad = [r for r in rep["rows"] if r["status"] != "right"]
        assert len(bad) <= 1, bad
        with pytest.raises(ValueError, match="as is one of"):
            masses.build("fig", {"snout": {"as": "blob"}})
        flap = masses.build("fig", {"ear.L": {"as": "flap"}})
        ear = flap["spec"]["blobs"]["ear.L"]
        assert ear["shape"] == "sheet" and len(ear["spine"]) >= 3 and all(s_["half_thickness"] < s_["half_width"] for s_ in ear["stations"])
        rows = [r for r in featuresee.report("fig", resolution=128)["rows"] if r["feature"] == "ear.L"]
        assert rows and all(r["status"] == "right" for r in rows), rows
        sock = masses.build("fig", {"eye.L": {"as": "ball", "socket": True}})["spec"]["blobs"]
        assert sock["eye_socket.L"]["op"] == "subtract" and sock["eye_socket.L"]["targets"] == ["head"]
        assert featuremap.load("fig")["features"]["eye.L"]["elements"] == ["eye.L"]   # (the socket is the head's)
        rows = [r for r in featuresee.report("fig", resolution=128)["rows"] if r["feature"] in ("eye.L", "eye.R", "head")]
        assert all(r["status"] == "right" for r in rows), rows
        drum = masses.build("fig", {"snout": {"as": "drum", "along": "y"}})["spec"]["blobs"]["snout"]
        assert drum["shape"] == "cylinder" and drum["rot"] == [90, 0, 0] and abs(drum["size"][2] - 0.06) < 0.012, drum
    finally:
        store.save("fig", true, "the true figure again")
        fm = featuremap.load("fig")
        fm.pop("frame", None)
        for n in fig["marks"]:
            fm["features"][n].update(elements=[n], built=[])
        featuremap.save("fig", fm)
