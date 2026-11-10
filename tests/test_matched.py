"""Matched views (matched.py) and join reports (joins.py): the concept mask, the camera's frame, a fitted camera
recovering a known one, the mirror flag, same-box tiles the review gate accepts, a planted stalk found.

Run: uv run python tests/test_matched.py   (or pytest)."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

_TMP = tempfile.mkdtemp(prefix="hp-matched-")
os.environ["HIFIPUSHIE_HOME"] = _TMP  # before hifipushie.store reads it

import numpy as np  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402

from hifipushie import joins, matched, reviewgate, store  # noqa: E402

store.HOME = Path(_TMP)


def _figure(name: str, arm: bool = True) -> None:
    """A little figure: body, head, a snout in front and (arm=True) one arm on its left only: not mirror-symmetric."""
    blobs = {"body": {"shape": "ellipsoid", "at": [0, 0, 0.25], "size": [0.12, 0.1, 0.18], "part": "body"},
             "head": {"shape": "ellipsoid", "at": [0, -0.02, 0.5], "size": [0.1, 0.09, 0.09], "part": "body"},
             "snout": {"shape": "ellipsoid", "at": [0, -0.11, 0.49], "size": [0.04, 0.04, 0.03], "part": "body"}}
    if arm:
        blobs["arm"] = {"shape": "ellipsoid", "at": [0.16, -0.03, 0.27], "size": [0.04, 0.04, 0.11], "part": "body"}
    store.save(name, {"symmetry": False, "blend": 0.01, "joints": {}, "bones": {}, "blobs": blobs}, "test")


def _cam(**kw) -> dict:
    return {"az": -25.0, "el": 8.0, "roll": 1.0, "f_px": 1400.0, "aim": [0.0, 0.0, 0.32], "dist": 2.0,
            "size": [400, 400], **kw}


def _concept(name: str, cam: dict) -> Path:
    """The figure's silhouette from `cam`, pink on a grey sweep with a soft floor shadow: a stand-in concept."""
    from scipy import ndimage
    meta = store.build(name, 96)
    m = matched._splat(matched.project(matched._samples(Path(meta["mesh"])), cam)[0], cam["size"])
    W, H = cam["size"]
    yy, xx = np.mgrid[:H, :W]
    img = np.dstack([215 + 15 * yy / H] * 3)  # a grey gradient sweep
    sh = ndimage.gaussian_filter((((xx - W / 2 + 40) / 120.0) ** 2 + ((yy - 0.93 * H) / 14.0) ** 2 < 1).astype(float), 6)
    img -= 45 * sh[..., None]  # a soft cast shadow, on the floor beside the figure
    img[m] = (230, 150, 130)
    p = Path(_TMP) / f"{name}_concept.png"
    Image.fromarray(img.clip(0, 255).astype(np.uint8)).save(p)
    return p


def test_mask_skips_a_soft_shadow_keeps_grey_inside():
    W = H = 200
    im = Image.new("RGB", (W, H), (222, 222, 222))
    d = ImageDraw.Draw(im)
    for r in range(30, 0, -1):  # a soft grey shadow, darkening to its centre
        g = 222 - (30 - r)
        d.ellipse([60 - 2 * r, 175 - r // 3, 140 + 2 * r, 185 + r // 3], fill=(g, g, g))
    d.ellipse([60, 40, 140, 170], fill=(230, 150, 130))  # the figure
    d.rectangle([85, 150, 115, 168], fill=(90, 85, 85))  # a grey hoof inside the figure's outline
    m = matched.mask_of(_save(im, "mask"))
    ref = Image.new("L", (W, H), 0)
    ImageDraw.Draw(ref).ellipse([60, 40, 140, 170], fill=255)
    ImageDraw.Draw(ref).rectangle([85, 150, 115, 168], fill=255)
    want = np.asarray(ref) > 0
    iou = (m & want).sum() / (m | want).sum()
    assert iou > 0.95, iou
    assert m[160, 100], "the grey hoof inside the figure is figure, not background"
    assert not m[190, 30:170].any(), "the soft shadow is background"


def _save(im, stem) -> Path:
    p = Path(_TMP) / f"{stem}.png"
    im.save(p)
    return p


def test_frame_and_look_camera_agree():
    cam = _cam()
    xy, z = matched.project(np.array([cam["aim"]]), cam)
    assert np.allclose(xy[0], [200, 200]) and abs(z[0] - 2.0) < 1e-9  # the aim is the image centre, dist away
    D, Fw, R, U = matched.axes(-25, 8, 0)
    assert D[0] < 0 and D[1] < 0, "az < 0: the camera is round toward the creature's right (-X), in front"
    assert abs(R @ U) < 1e-9 and abs(R @ Fw) < 1e-9
    lc = matched.look_camera(cam)
    assert np.allclose(lc["eye"], np.array(cam["aim"]) + 2.0 * matched.axes(-25, 8, 1)[0])
    assert abs(lc["fov"] - np.degrees(2 * np.arctan(200 / 1400))) < 1e-9
    # +X (the creature's left) shows on the picture's right from the front
    front = _cam(az=0.0, el=0.0, roll=0.0)
    assert matched.project(np.array([[0.1, 0, 0.32]]), front)[0][0, 0] > 200


def test_fit_recovers_a_known_camera():
    _figure("fig")
    true = _cam()
    img = _concept("fig", true)
    cam = matched.fit_camera("fig", str(img), dist=2.0)  # (focal length trades with distance: fix one)
    assert cam["iou"] > 0.93, cam
    assert abs(cam["az"] - true["az"]) < 4 and abs(cam["el"] - true["el"]) < 4, cam
    assert abs(cam["f_px"] / true["f_px"] - 1) < 0.08, cam
    saved = json.loads(matched.cam_path("fig", "concept").read_text())
    assert saved["image"] == str(img.resolve()) and saved["size"] == [400, 400]
    assert matched.load_camera("fig")["az"] == cam["az"]


def test_symmetric_silhouette_is_flagged_mirror():
    _figure("sym", arm=False)
    img = _concept("sym", _cam(roll=0.0))
    cam = matched.fit_camera("sym", str(img))
    assert cam["mirror"] is not None, cam  # az and -az fit about as well: said, not guessed silently
    assert np.sign(cam["mirror"]["az"]) != np.sign(cam["az"]), cam


def test_tiles_share_boxes_and_pass_the_review_gate():
    _figure("fig")
    img = _concept("fig", _cam())
    matched.fit_camera("fig", str(img))
    # a stand-in for the matched render (Blender isn't run here): the concept itself, same size
    Image.open(img).save(matched.cam_path("fig", "concept").with_name("concept_render.png"))
    r = matched.tiles("fig", {"arm": ["arm"], "face": ["snout", "head"], "corner": [0, 0, 50, 40]}, min_px=300)
    assert set(r["tiles"]) == {"arm", "face", "corner"}
    for region, (a, b, box) in r["tiles"].items():
        A, B = Image.open(a), Image.open(b)
        assert A.size == B.size and A.size[0] == A.size[1] >= 300
        assert box[2] - box[0] == box[3] - box[1]
        assert np.array_equal(np.asarray(A), np.asarray(B)), region  # same box from both images
    ax0, ay0, ax1, ay1 = r["tiles"]["arm"][2]
    cx = matched.project(np.array([[0.16, -0.03, 0.27]]), matched.load_camera("fig"))[0][0]
    assert ax0 < cx[0] < ax1 and ay0 < cx[1] < ay1 and ax1 - ax0 < 240, "the arm's box is round the arm, and tight"
    paths = [p for a, b, _ in r["tiles"].values() for p in (a, b)]
    reviewgate.refuse_inputs(paths, list(r["tiles"]), "a test figure")  # no caption, no sheet: accepted
    assert "bin/review" in r["review"] and '"arm=' in r["review"]


def _eared(name: str, stalk: bool) -> None:
    """A body with an ear: laid along the body (stalk=False) or held off it on a thin neck (stalk=True)."""
    blobs = {"body": {"shape": "ellipsoid", "at": [0, 0, 0], "size": [0.15, 0.15, 0.15], "part": "body"}}
    if stalk:
        blobs["ear"] = {"shape": "ellipsoid", "at": [0, 0, 0.18], "size": [0.07, 0.02, 0.012], "part": "body"}
        blobs["neck"] = {"shape": "ellipsoid", "at": [0, 0, 0.155], "size": [0.018, 0.012, 0.02], "part": "body"}
    else:
        blobs["ear"] = {"shape": "ellipsoid", "at": [0, 0, 0.155], "size": [0.07, 0.02, 0.02], "part": "body"}
    store.save(name, {"symmetry": False, "blend": 0.004, "joints": {}, "bones": {}, "blobs": blobs}, "test")


def test_join_finds_a_planted_stalk():
    _eared("based", stalk=False)
    _eared("stalked", stalk=True)
    good = joins.measure("based", "ear")
    bad = joins.measure("stalked", "ear,neck", sections=True)
    assert good["joined"] and good["ratio"] >= joins.WARN, good
    assert bad["joined"] and bad["ratio"] < 0.6, {k: v for k, v in bad.items() if k != "image"}
    assert bad["image"].size[0] > bad["image"].size[1]  # two sections side by side
    assert "WARNING" in joins.line(bad) and "WARNING" not in joins.line(good)
    assert "no element or part" in joins.report("based", ["tail"])


def test_put_and_edit_model_report_joins():
    from hifipushie import server
    _eared("stalked", stalk=True)
    spec = store.load("stalked")
    out = server.put_model("stalked2", spec, joins=["ear,neck"])
    assert "WARNING: join ear,neck" in out
    out = server.edit_model("stalked2", [{"op": "set", "kind": "blobs", "name": "neck",
                                          "value": {"size": [0.06, 0.02, 0.03]}}], joins=["ear,neck"])
    assert "join ear,neck" in out and "WARNING: join" not in out, out  # a broad neck: joined along its base


def test_look_resolves_a_fitted_camera():
    from hifipushie import server
    _figure("fig")
    matched.fit_camera("fig", str(_concept("fig", _cam())))
    c = server._resolve_camera("fig", {"fitted": "concept"})
    assert len(c["eye"]) == 3 and 5 <= c["fov"] <= 150 and len(c["up"]) == 3
    try:
        server._resolve_camera("fig", {"fitted": "nope"})
    except ValueError as e:
        assert "fit_concept_camera" in str(e)
    else:
        raise AssertionError("an unknown fitted camera is refused")


if __name__ == "__main__":
    for k, f in list(globals().items()):
        if k.startswith("test_"):
            f()
            print("ok", k)
