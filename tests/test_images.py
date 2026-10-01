"""Images as paint (images.py, the `image` paint generator): the content store, text pages, the projection, image
masks in a stack, the node program and save-time validation.

Run: uv run python tests/test_images.py   (or pytest)."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

_TMP = tempfile.mkdtemp(prefix="hp-images-")
os.environ["HIFIPUSHIE_HOME"] = _TMP  # before hifipushie.store reads it

import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402

from hifipushie import images, paint, paintnodes, store  # noqa: E402
from hifipushie.spec import SpecError  # noqa: E402

store.HOME = Path(_TMP)


def _png(name: str, rgba) -> Path:
    """A 4 x 2 test image: left half colour a, right half colour b (rows top first)."""
    p = Path(_TMP) / name
    Image.fromarray(np.asarray(rgba, np.uint8)).save(p)
    return p


LR = [[[255, 0, 0, 255]] * 2 + [[0, 0, 255, 255]] * 2] * 2  # red left, blue right


def _board(img: dict, **ly) -> dict:
    """A thin board facing -Y (its front) with one image layer on it."""
    return {"symmetry": False, "blend": 0.0, "joints": {"c": {"pos": [0, 0, 0], "r": 0.01}},
            "parts": {"board": {"color": "#808080"}},
            "blobs": {"board": {"shape": "box", "at": [0, 0, 0], "size": [0.2, 0.01, 0.1], "part": "board"}},
            "paint": {"pic": {"part": "board", "color": "image", "image": img, **ly}}}


def test_content_store():
    p = _png("a.png", LR)
    i1, i2 = images.ingest(p), images.ingest(str(p))
    assert i1 == i2 and len(i1) == 16 and images.id_path(i1).exists()
    q = _png("b.png", [[[0, 255, 0, 255]] * 4] * 2)
    assert images.ingest(q) != i1
    try:
        images.id_path("../etc/passwd")
        raise AssertionError("a path was taken as an id")
    except SpecError:
        pass
    spec = _board({"file": str(p), "at": "board", "size": [0.2, None]})
    out = images.ingest_spec(spec)
    img = out["paint"]["pic"]["image"]
    assert "file" not in img and img["id"] == i1 and img["name"] == "a.png"
    assert "file" in spec["paint"]["pic"]["image"]  # the caller's spec is left alone


def test_text_page():
    t = {"string": "Hello world. " * 20, "size": 0.005, "margin": 0.01}
    im = images.render_text(t, 0.1, None)  # height fitted to the text
    a = np.asarray(im)
    assert im.size[0] == 600 and a[..., 3].max() == 255 and (a[..., 3] > 0).mean() < 0.5
    assert (a[..., :3] == [17, 17, 17]).all()  # ink everywhere, coverage in alpha (no dark fringe)
    p1, p2 = images.text_path(t, 0.1, None), images.text_path(t, 0.1, None)
    assert p1 == p2 and p1.exists()
    assert images.text_path({**t, "string": "other"}, 0.1, None) != p1
    bg = np.asarray(images.render_text({**t, "background": "#ffffff"}, 0.1, 0.05))
    assert (bg[..., 3] == 255).all() and bg.shape[:2] == (300, 600)


def test_projection():
    p = _png("lr.png", LR)
    spec = _board({"file": str(p), "at": "board", "size": [0.2, None]})
    fr = images.frame(spec, spec["paint"]["pic"]["image"])
    assert np.allclose(fr["c"], [0, -0.01, 0]) and np.allclose(fr["dir"], [0, -1, 0])  # on the board's front face
    assert np.isclose(fr["h"], 0.1)  # from the image's aspect (4 x 2)
    assert np.allclose(fr["right"], [1, 0, 0]) and np.allclose(fr["up"], [0, 0, 1])  # reads left to right from the front
    pos = np.array([[-0.05, -0.01, 0.0], [0.05, -0.01, 0.0], [0.05, 0.01, 0.0], [0.3, -0.01, 0.0]])
    nrm = np.array([[0, -1, 0], [0, -1, 0], [0, 1, 0], [0, -1, 0.0]])
    m, col = images.evaluate(fr, pos, nrm)
    assert np.allclose(m, [1, 1, 0, 0])  # the back face and outside the rectangle don't take it
    assert col[0, 0] > 0.9 and col[0, 2] < 0.1 and col[1, 2] > 0.9  # red on the left, blue on the right
    # mirrored: the mirror placement still reads red-left, blue-right as seen from its own front
    mf = images.mirrored({**fr, "c": [0.5, -0.01, 0], "mirror": True})
    m2, col2 = images.evaluate(mf, np.array([[-0.55, -0.01, 0.0], [-0.45, -0.01, 0.0]]), nrm[:2])
    assert np.allclose(m2, 1) and col2[0, 0] > 0.9 and col2[1, 2] > 0.9


def test_mask_and_channels():
    p = _png("lr2.png", LR)
    img = {"file": str(p), "at": "board", "size": [0.2, None], "channel": "r"}
    spec = _board({"file": str(p), "at": "board", "size": [0.2, None]})
    spec["paint"]["stencil"] = {"part": "board", "color": "#000000",
                                "mask": [{"image": img}, {"facing": [0, -1, 0], "range": [0, 0.5]}]}

    class _Pts:  # the bits of surface.Points a mask stack reads
        def __init__(self, pos, nrm):
            self.pos, self.normal = pos, nrm
            self.part = np.zeros(len(pos), int)
            self.part_names = ["board"]
    pos = np.array([[-0.05, -0.01, 0.0], [0.05, -0.01, 0.0]])
    view = paint._View(_Pts(pos, np.array([[0, -1.0, 0]] * 2)), np.arange(2))
    m = paint.layer_mask(spec, "stencil", spec["paint"]["stencil"], view)
    assert m[0] > 0.9 and m[1] < 0.1  # the red channel as a stencil: on over the red half only


def test_nodes_and_validation():
    p = _png("lr3.png", LR)
    spec = _board({"file": str(p), "at": "board", "size": [0.2, None]})
    spec["paint"]["relief"] = {"part": "board", "height": 0.001, "image": {"file": str(p), "at": "board",
                                                                         "size": [0.2, None], "channel": "luma"}}
    prog = paintnodes.compile(spec)
    ly = prog["layers"][0]
    e = ly["entries"][0]
    assert e["gen"] == "image" and ly["color_from"] == e["key"] and ly["channels"]["color"] == "image"
    assert not prog["fallbacks"]  # drawn per pixel, nothing measured per vertex
    # a ".L" layer of decals stays native, with the mirrored placement
    spec["paint"]["sign.L"] = {"part": "board", "color": "#ffffff", "image": {"file": str(p), "at": [0.1, -0.01, 0],
                                                                             "dir": [0, -1, 0], "size": [0.05, None]}}
    e = next(ly for ly in paintnodes.compile(spec)["layers"] if ly["name"] == "sign.L")["entries"][0]
    assert e["gen"] == "image" and e["mirror"] and np.allclose(e["mirrored"]["c"], [-0.1, -0.01, 0])
    (Path(_TMP) / "board").mkdir(exist_ok=True)
    store.save("board", spec)
    saved = store.load("board")
    assert "id" in saved["paint"]["pic"]["image"] and "file" not in saved["paint"]["pic"]["image"]
    bad = _board({"file": str(p), "at": [0, -0.5, 0], "dir": [0, -1, 0], "size": [0.1, 0.05], "depth": 0.02})
    try:
        store.save("board", bad)
        raise AssertionError("a decal hitting nothing was saved")
    except SpecError as ex:
        assert "hits nothing" in str(ex)
    for wrong, why in (({"file": str(p), "at": "board", "size": [0, 0.1]}, "size"),
                       ({"file": str(p), "at": "board", "size": [0.1, None], "channel": "x"}, "channel"),
                       ({"at": "board", "size": [0.1, None]}, "one of")):
        try:
            store.save("board", _board(wrong))
            raise AssertionError(f"saved a bad image ({why})")
        except SpecError as ex:
            assert why in str(ex), ex


if __name__ == "__main__":
    for k, f in list(globals().items()):
        if k.startswith("test_"):
            f()
            print("ok", k)
