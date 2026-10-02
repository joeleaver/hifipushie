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

from hifipushie import images, paint, paintnodes, sdf, store  # noqa: E402
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




# ---- wraps ---------------------------------------------------------------------------------------------------------

def _can(**img) -> dict:
    """A can (cylinder blob, radius 0.033, axis Z) and a cone-ish taper (a bone 0.03 -> 0.015) with one image layer."""
    return {"symmetry": False, "blend": 0.0,
            "joints": {"t0": {"pos": [0.3, 0, 0.0], "r": 0.03}, "t1": {"pos": [0.3, 0, 0.1], "r": 0.015}},
            "parts": {"can": {"color": "#808080"}},
            "bones": {"taper": {"a": "t0", "b": "t1", "r_a": 0.03, "r_b": 0.015, "part": "can"}},
            "blobs": {"can": {"shape": "cylinder", "at": [0, 0, 0.06], "size": [0.033, 0.033, 0.06], "part": "can"}},
            "paint": {"pic": {"part": "can", "color": "image", "image": img}}}


def _ring(fr, a, t, r):
    """Points (and outward normals) at angle a round a wrap's axis from its centre direction, height t, radius r."""
    e1, e2, k = (np.array(fr[x]) for x in ("dir", "right", "k"))
    n = np.cos(a)[:, None] * e1 + np.sin(a)[:, None] * e2
    return np.array(fr["o"]) + r * n + np.asarray(t)[:, None] * k, n


def test_cylinder_wrap():
    p = _png("lr4.png", LR)
    spec = _can(file=str(p), wrap="cylinder", at="can", size=[0.17, 0.08])
    fr = images.frame(spec, spec["paint"]["pic"]["image"], parts=["can"])
    assert np.isclose(fr["r0"], 0.033, atol=1e-6) and np.allclose(fr["k"], [0, 0, 1])
    assert np.allclose(fr["dir"], [0, -1, 0]) and np.allclose(fr["right"], [1, 0, 0])  # reads left to right from the front
    a = np.radians([-140.0, -60, 0, 60, 140])
    pos, n = _ring(fr, a, [0, 0.02, -0.02, 0.03, 0], 0.033)
    u, v, w = images.project(fr, pos, n)
    assert np.allclose(u, 0.033 * a / 0.17 + 0.5) and np.allclose(v, [0.5, 0.75, 0.25, 0.875, 0.5])  # arc length
    assert np.allclose(w, 1)
    assert np.allclose(images.project(fr, pos * [0.9, 0.9, 1], -n)[2], 0)  # an inside wall (facing in) stays clean
    m, col = images.evaluate(fr, pos[[1, 3]], n[[1, 3]])
    assert col[0, 0] > 0.9 and col[1, 2] > 0.9  # red on the left of the front, blue on the right
    # 360 degrees: the two ends meet at the seam (behind), continuously
    f2 = images.frame(spec, {**spec["paint"]["pic"]["image"], "size": [None, 0.08], "span": 360, "seam": 180},
                      parts=["can"])
    pos, n = _ring(f2, np.radians([179.9, -179.9]), [0, 0], 0.033)
    u, _, _ = images.project(f2, pos, n)
    assert u[0] > 0.999 and u[1] < 0.001
    # the seam is where the wrap is cut: the centre stays at dir, a picture reaching past the seam is clipped there
    f3 = images.frame(spec, {**spec["paint"]["pic"]["image"], "size": [None, 0.08], "span": 360, "seam": 90},
                      parts=["can"])
    pos, n = _ring(f3, np.radians([0.0, 89.9, 90.1]), [0, 0, 0], 0.033)
    u, _, _ = images.project(f3, pos, n)
    assert np.isclose(u[0], 0.5) and np.isclose(u[1], 0.75, atol=1e-3) and u[2] < 0
    # mirrored: the mirrored can's label still reads left to right from its own front
    mf = images.mirrored({**fr, "o": [0.2, 0, 0.06], "c": [0.2, -0.033, 0.06]})
    assert np.allclose(mf["right"], [1, 0, 0]) and np.allclose(mf["o"], [-0.2, 0, 0.06])


def test_taper_arc_length():
    """unroll "arc" on a taper: the label keeps its width round the surface (u = arc length at the point's own
    radius, v = height along the axis)."""
    p = _png("lr5.png", LR)
    spec = _can(file=str(p), wrap="cylinder", axis="taper", at=[0.3, 0, 0.05], size=[0.05, 0.02], unroll="arc")
    fr = images.frame(spec, spec["paint"]["pic"]["image"], parts=["can"])
    assert np.allclose(fr["k"], [0, 0, 1]) and np.allclose(fr["o"], [0.3, 0, 0.05])
    for t in (-0.008, 0.0, 0.008):  # the surface's radius at each height, measured
        r = images._hit(images.prims_on(spec, ["can"]), np.array([0.3, 0, 0.05 + t]), np.array([0, -1.0, 0]), "t")
        pos, n = _ring(fr, np.array([0.5]), [t], r)
        u, v, w = images.project(fr, pos, n)
        assert np.isclose((u[0] - 0.5) * 0.05, 0.5 * r, rtol=1e-6) and w[0] > 0.9  # metres round the surface
    # with span the picture is angular instead: the same angle everywhere
    f2 = images.frame(spec, {**spec["paint"]["pic"]["image"], "size": [None, 0.02], "span": 90}, parts=["can"])
    pos, n = _ring(f2, np.radians([45.0, 45.0]), [-0.008, 0.008], 0.02)
    assert np.allclose(images.project(f2, pos, n)[0], 1.0)


def test_taper_cone():
    """unroll "cone" (auto on a taper): the label fan-cut onto the local cone, like a paper neck label. Columns run
    along the cone's generators (the same u at every height), rows round it (the same v all round a height), v is
    the slant distance, and the frame's cone matches the bone's (radius 0.03 -> 0.015 over 0.1 m)."""
    p = _png("lr10.png", LR)
    spec = _can(file=str(p), wrap="cylinder", axis="taper", at=[0.3, 0, 0.05], size=[0.05, 0.02])
    fr = images.frame(spec, spec["paint"]["pic"]["image"], parts=["can"])
    assert fr["unroll"] == "cone" and np.isclose(fr["m"], -0.15, atol=0.01) and fr["sg"] == 1.0
    prims = images.prims_on(spec, ["can"])
    rs = {t: images._hit(prims, np.array([0.3, 0, 0.05 + t]), np.array([0, -1.0, 0]), "t") for t in (-0.008, 0.008)}
    for a in np.radians([-60.0, 0, 45]):
        pts = [_ring(fr, np.array([a]), [t], rs[t]) for t in (-0.008, 0.008)]
        (u0, v0, w0), (u1, v1, w1) = (images.project(fr, q, n) for q, n in pts)
        assert np.isclose(u0[0], u1[0]) and np.isclose(u0[0], fr["r0"] * a / 0.05 + 0.5)  # along a generator
        slant = np.linalg.norm(pts[1][0][0] - pts[0][0][0])
        assert np.isclose((v1[0] - v0[0]) * 0.02, slant, rtol=0.02) and w0[0] > 0.9 and w1[0] > 0.9
    pos, n = _ring(fr, np.radians([-80.0, 10, 80]), [0.004] * 3, 0.0294)
    assert np.ptp(images.project(fr, pos, n)[1]) < 1e-9  # a row runs round the cone at one height
    fp = images.footprint(fr, 8)  # the footprint lies on the surface
    assert np.abs(sdf.field_at(prims, fp, clip=False)).max() < 1e-3


def test_sphere_wrap():
    p = _png("lr6.png", LR)
    spec = _board({"file": str(p), "wrap": "sphere", "at": "ball", "span": [360, 180]})
    spec["parts"]["ball"] = {}
    spec["blobs"]["ball"] = {"shape": "ellipsoid", "at": [0, 0.5, 0], "size": [0.1, 0.1, 0.1], "part": "ball"}
    spec["paint"]["pic"]["part"] = "ball"
    fr = images.frame(spec, spec["paint"]["pic"]["image"], parts=["ball"])
    assert np.isclose(fr["r0"], 0.1, atol=1e-6)
    lat, lon = np.radians([0.0, 30, -45, 60]), np.radians([0.0, 90, -120, 170])
    d = (np.cos(lat)[:, None] * (np.cos(lon)[:, None] * np.array(fr["dir"]) + np.sin(lon)[:, None] * np.array(fr["right"]))
         + np.sin(lat)[:, None] * np.array(fr["k"]))
    u, v, w = images.project(fr, np.array([0, 0.5, 0]) + 0.1 * d, d)
    assert np.allclose(u, lon / (2 * np.pi) + 0.5) and np.allclose(v, lat / np.pi + 0.5) and np.allclose(w, 1)


def test_surface_map_on_sphere():
    """The surface decal's coordinates against the sphere's exact log map (geodesic polar coordinates)."""
    from hifipushie import decalmap
    p = _png("lr7.png", LR)
    spec = _board({"file": str(p), "wrap": "surface", "at": [0, 0.3, 0.0], "size": [0.12, 0.12]})
    spec["parts"]["ball"] = {}
    spec["blobs"]["ball"] = {"shape": "ellipsoid", "at": [0, 0.5, 0], "size": [0.1, 0.1, 0.1], "part": "ball"}
    spec["paint"]["pic"]["part"] = "ball"
    fr = images.frame(spec, spec["paint"]["pic"]["image"], parts=["ball"])
    assert np.allclose(fr["c"], [0, 0.4, 0], atol=1e-5) and np.allclose(fr["dir"], [0, -1, 0], atol=1e-4)
    m = images.surface_map(fr)
    c0, R = np.array([0, 0.5, 0]), 0.1
    err = []
    for beta in np.linspace(0, 2 * np.pi, 16, endpoint=False):
        for al in (0.2, 0.4, 0.6):
            t = np.cos(beta) * np.array(fr["right"]) + np.sin(beta) * np.array(fr["up"])
            q = c0 + R * (np.cos(al) * np.array([0, -1.0, 0]) + np.sin(al) * t)
            U, dist, _ = decalmap.lookup(m, q[None])
            assert dist[0] < 1e-3
            err.append(np.linalg.norm(U[0] - R * al * np.array([np.cos(beta), np.sin(beta)])))
    err = np.array(err)
    assert err.mean() < 0.012 * 0.12 and err.max() < 0.04 * 0.12, (err.mean(), err.max())  # of the decal's size
    # every point on the decal is reached and weighted; the far side of the ball isn't
    rng = np.random.default_rng(1)
    d = rng.normal(size=(20000, 3))
    d /= np.linalg.norm(d, axis=1, keepdims=True)
    u, v, w = images.project(fr, c0 + R * d, d)
    inside = (u > 0.02) & (u < 0.98) & (v > 0.02) & (v < 0.98)
    assert inside.any() and (w[inside] > 0.99).all() and (w[d[:, 1] > 0] == 0).all()


def _logmap_errors(m, fr, c0, R, alphas):
    """(max |angle error| deg, max |radius error| share) per geodesic angle alpha against the sphere's exact log map."""
    from hifipushie import decalmap
    n0, r, u = (np.array(fr[k]) for k in ("dir", "right", "up"))
    out = []
    for al in alphas:
        beta = np.linspace(0, 2 * np.pi, 32, endpoint=False)
        q = c0 + R * (np.cos(al) * n0 + np.sin(al) * (np.cos(beta)[:, None] * r + np.sin(beta)[:, None] * u))
        U, _, _ = decalmap.lookup(m, q)
        ang = np.degrees(np.angle(np.exp(1j * (np.arctan2(U[:, 1], U[:, 0]) - beta))))
        out.append((np.abs(ang).max(), np.abs(np.linalg.norm(U, axis=1) / (R * al) - 1).max()))
    return out


def test_logmap_heat_vs_dem():
    """The vector heat log map (potpourri3d) against the sphere's exact one, off-axis with a turned up, and the
    discrete exponential map it replaced (still the fallback)."""
    from hifipushie import decalmap
    p = _png("lr10.png", LR)
    spec = {"symmetry": False, "blend": 0.0, "parts": {"ball": {}},
            "blobs": {"ball": {"shape": "ellipsoid", "at": [0, 0.5, 0], "size": [0.1, 0.1, 0.1], "part": "ball"}},
            "paint": {"pic": {"part": "ball", "color": "image",
                              "image": {"file": str(p), "wrap": "surface", "at": [0.013, 0.3, 0.021],
                                        "size": [0.16, 0.16], "up": [0.3, 0, 1]}}}}
    fr = images.frame(spec, spec["paint"]["pic"]["image"], parts=["ball"])
    prims = images._PRIMS[fr["geo"]]
    c0, R = np.array([0, 0.5, 0]), 0.1
    assert decalmap.method() == "heat"
    heat = _logmap_errors(decalmap.build(prims, fr, "heat"), fr, c0, R, (0.2, 0.4, 0.6, 0.8))
    dem = _logmap_errors(decalmap.build(prims, fr, "dem"), fr, c0, R, (0.2, 0.4, 0.6, 0.8))
    assert all(a < 0.3 and r < 0.004 for a, r in heat), heat  # measured <= 0.12 deg, 0.25%
    assert all(a < 2.5 and r < 0.006 for a, r in dem), dem  # measured 1.85 deg at 0.8 rad
    assert heat[-1][0] < 0.25 * dem[-1][0]  # the drift at the decal's corners is gone
    # the fallback is what runs without the library
    old = decalmap.METHOD
    try:
        decalmap.METHOD = "dem"
        assert decalmap.method() == "dem"
    finally:
        decalmap.METHOD = old


def _moved(fr_g, T=np.zeros(3), R=np.eye(3), S=np.ones(3)):
    """A gizmo matrix moved by T, turned by R (about its origin) and its scale multiplied by S."""
    M = np.asarray(fr_g["matrix"], float)
    out = np.eye(4)
    out[:3, :3] = R @ M[:3, :3] * S
    out[:3, 3] = M[:3, 3] + T
    return M, out


def _rz(deg):
    a = np.radians(deg)
    return np.array([[np.cos(a), -np.sin(a), 0], [np.sin(a), np.cos(a), 0], [0, 0, 1]])


def test_decal_gizmo_round_trip():
    """A decal's gizmo moved, turned or scaled comes back into the spec (images.from_gizmo): near its blob as an
    offset, far off as a world point; a spin as rotate, a tilt as dir/up; a scale as size; a wrap's height, turn
    round its axis and scale as offset, dir, span. Absolute: pulled twice, the spec is the same."""
    p = _png("lr11.png", LR)
    spec = _board({"file": str(p), "at": "board", "size": [0.1, None]})
    img = spec["paint"]["pic"]["image"]
    fr = images.frame(spec, img, parts="board")
    g = images.gizmo(fr)
    assert np.allclose(np.asarray(g["matrix"])[:3, 3], fr["c"])
    assert images.from_gizmo(spec, img, "board", *_moved(g)) == (None, [])  # nothing moved
    # slid along the board's face by 2 cm: an offset from the blob (it keeps riding the board)
    new, notes = images.from_gizmo(spec, img, "board", *_moved(g, T=[0.02, 0, 0.01]))
    assert new["at"] == "board" and np.allclose(new["offset"], [0.02, 0, 0.01]) and not notes
    f2 = images.frame(spec, new, parts="board")
    assert np.allclose(f2["c"], np.asarray(fr["c"]) + [0.02, 0, 0.01])
    again, _ = images.from_gizmo({**spec, "paint": {"pic": {**spec["paint"]["pic"], "image": new}}}, new, "board",
                                 *_moved(g, T=[0.02, 0, 0.01]))
    assert again is None or again == new  # absolute: a second pull of the same gizmo changes nothing
    # moved 30 cm away: a world point, dir/up written out
    new, notes = images.from_gizmo(spec, img, "board", *_moved(g, T=[0.3, 0, 0]))
    assert np.allclose(new["at"], np.asarray(fr["c"]) + [0.3, 0, 0], atol=1e-4) and "offset" not in new and notes
    assert np.allclose(new["dir"], fr["dir"]) and np.allclose(new["up"], fr["up"])
    assert np.allclose(images.frame(spec, new, parts="board")["c"], np.asarray(fr["c"]) + [0.3, 0, 0], atol=1e-4)
    # spun 30 degrees about its normal: rotate
    Rspin = np.array(fr["dir"])  # rotation about dir (here -Y)
    K = np.array([[0, -Rspin[2], Rspin[1]], [Rspin[2], 0, -Rspin[0]], [-Rspin[1], Rspin[0], 0]])
    a = np.radians(30)
    Rd = np.eye(3) + np.sin(a) * K + (1 - np.cos(a)) * K @ K
    new, _ = images.from_gizmo(spec, img, "board", *_moved(g, R=Rd))
    assert np.isclose(new["rotate"], 30, atol=0.05) and new.get("offset") is None, new
    f3 = images.frame(spec, new, parts="board")
    assert np.allclose(f3["up"], Rd @ np.array(fr["up"]), atol=1e-4)
    # scaled 1.5 x uniformly: the width given, the height still from the image's aspect
    new, _ = images.from_gizmo(spec, img, "board", *_moved(g, S=[1.5, 1.5, 1.5]))
    assert new["size"] == [0.15, None]
    # a cylinder wrap: raised 1 cm along the can's axis, turned 40 degrees round it, scaled 1.2 x
    spec = _can(file=str(p), wrap="cylinder", at="can", span=120, size=[None, 0.04])
    img = spec["paint"]["pic"]["image"]
    fr = images.frame(spec, img, parts=["can"])
    g = images.gizmo(fr)
    new, _ = images.from_gizmo(spec, img, ["can"], *_moved(g, T=[0, 0, 0.01], R=_rz(40), S=[1.2] * 3))
    assert np.allclose(new["offset"], [0, 0, 0.01]) and np.isclose(new["span"], 144) and new["size"] == [None, 0.048]
    f4 = images.frame(spec, new, parts=["can"])
    assert np.isclose(f4["o"][2], fr["o"][2] + 0.01, atol=1e-6)
    assert np.allclose(f4["dir"], _rz(40) @ np.array(fr["dir"]), atol=1e-4) and np.allclose(f4["k"], fr["k"])


def test_decal_pull_through_blender():
    """The whole round trip in a headless Blender: sync makes the gizmo, a person's move (here a script that moves
    it and saves the file) comes back into the spec on pull, a re-sync re-stamps it, and a second pull is empty."""
    import shutil
    import subprocess
    from hifipushie import scene
    if not shutil.which("blender"):
        print("  (no blender: skipped)")
        return
    p = _png("lr12.png", LR)
    spec = _board({"file": str(p), "at": "board", "size": [0.1, None]})
    (Path(_TMP) / "decal_rt").mkdir(exist_ok=True)
    store.save("decal_rt", spec)
    scene.sync("decal_rt", 96)
    move = ("import bpy\n"
            "ob = next(o for o in bpy.data.objects if o.get('hp_decal') is not None)\n"
            "ob.location.x += 0.03\n"
            "bpy.ops.wm.save_mainfile()\n")
    subprocess.run(["blender", "-b", str(scene.blend_path("decal_rt")), "--factory-startup", "--python-expr", move],
                   check=True, capture_output=True, timeout=300)
    log: list = []
    got = scene.pull("decal_rt", log)
    assert np.allclose(got["pic.image"]["offset"], [0.03, 0, 0]), (got, log)
    assert np.allclose(store.load("decal_rt")["paint"]["pic"]["image"]["offset"], [0.03, 0, 0])
    scene.sync("decal_rt", 96)
    assert scene.pull("decal_rt", []) == {}  # re-stamped: nothing moved since


def test_chart_border_steps():
    """asset.seam_steps on a square cut into two charts along x = 0 (packed apart, at different sub-texel phases):
    a map that is the surface's own function on both sides (texels past each chart's edge extrapolated, as
    `rasterize(ring=)` gives them) reads ~1 (measured 1.0); one chart a texel off reads over twice that (2.3)."""
    from hifipushie import asset
    S = 64
    # 3D: two triangles sharing the edge (0, 0)-(0, 1) in the z = 0 plane, 4 cm across
    V = np.array([[0, 0, 0], [0, 0.04, 0], [-0.04, 0.02, 0], [0.04, 0.02, 0]], float)
    cv = np.array([0, 1, 2, 0, 3, 1])
    k = 20 / S / 0.04  # 20 texels across 4 cm
    uvA = np.array([[0.40, 0.2], [0.40, 0.2 + 0.04 * k], [0.40 - 0.04 * k, 0.2 + 0.02 * k]])
    uvB = np.array([[0.55 + 0.3 / S, 0.25 + 0.37 / S]] * 3) + np.array([[0, 0], [0, 0.04 * k], [0.04 * k, 0.02 * k]])
    part = {"verts": V, "corner_vert": cv, "uv": np.concatenate([uvA, uvB]), "atlas": 0}

    def bake(ring, shift_b=0.0):
        (ys, xs), tri, bary, _, _, _ = asset.rasterize({"p": part}, S, ring=ring)
        P = np.einsum("nk,nkc->nc", bary, V[cv.reshape(-1, 3)][tri])
        y = P[:, 1] + 0.7 * P[:, 0] + np.where(tri == 1, shift_b, 0.0)  # an edge crossing the seam at a slant
        val = 1 / (1 + np.exp(-(y - 0.0213) / 0.0015))  # an edge across the seam, about a texel wide
        img = np.zeros((S, S, 3))
        img[ys, xs] = val[:, None]
        filled = np.zeros((S, S), bool)
        filled[ys, xs] = True
        return asset._dilate(img, filled)
    good = asset.seam_steps(part, bake(2))["excess"]
    off = asset.seam_steps(part, bake(2, shift_b=0.04 / 20))["excess"]  # chart B a texel off
    assert 0.7 < good < 1.3, good
    assert off > 2.0 * good, (good, off)


def test_wrap_mask_and_nodes():
    p = _png("lr8.png", LR)
    spec = _can(file=str(p), wrap="cylinder", at="can", size=[0.17, 0.08])
    spec["paint"]["stencil"] = {"part": "can", "color": "#000000",
                                "mask": [{"image": {"file": str(p), "wrap": "cylinder", "at": "can",
                                                    "size": [0.17, 0.08], "channel": "r"}}]}
    fr = images.frame(spec, spec["paint"]["pic"]["image"], parts=["can"])
    pos, n = _ring(fr, np.radians([-30.0, 30]), [0, 0], 0.033)

    class _Pts:
        def __init__(self, pos, nrm):
            self.pos, self.normal = pos, nrm
            self.part = np.zeros(len(pos), int)
            self.part_names = ["can"]
    view = paint._View(_Pts(pos, n), np.arange(2))
    m = paint.layer_mask(spec, "stencil", spec["paint"]["stencil"], view)
    assert m[0] > 0.9 and m[1] < 0.1  # a wrapped stencil: on over the label's red half only
    prog = paintnodes.compile(spec)
    e = prog["layers"][0]["entries"][0]
    assert e["wrap"] == "cylinder" and np.isclose(e["r0"], 0.033) and not prog["fallbacks"]  # per pixel
    # a surface decal: its u, v, weight are measured per vertex (three attributes), and the picture sampled per pixel
    spec["paint"]["pic"]["image"] = {"file": str(p), "wrap": "surface", "at": "can", "size": [0.05, 0.03]}
    del spec["paint"]["stencil"]
    prog = paintnodes.compile(spec)
    e = prog["layers"][0]["entries"][0]
    assert len(e["uv"]) == 3 and all(prog["fallbacks"][a][0] == "decal" for a in e["uv"])
    got = paintnodes.measure(spec, prog, pos, n, np.zeros(2, int), ["can"], 0.002, {}, "masks")
    uu = got[e["uv"][0]]
    assert uu[0] < 0.5 < uu[1] and (got[e["uv"][2]] > 0.9).all()


def test_style_on_images():
    p = _png("lr9.png", LR)
    spec = _board({"file": str(p), "at": "board", "size": [0.2, None], "style": True})
    spec["style"] = {"paint": {"saturation": 0.5, "value": 0.8}}
    fr = images.frame(spec, spec["paint"]["pic"]["image"])
    assert Path(fr["path"]).name.startswith("s_")
    px = images.pixels(Path(fr["path"]))
    r = px[0, 0, :3]  # red, half saturated and 0.8 bright: (0.8, 0.4, 0.4)
    assert np.allclose(r, [0.8, 0.4, 0.4], atol=0.01), r
    off = images.frame(spec, {**spec["paint"]["pic"]["image"], "style": False})
    assert Path(off["path"]) == images.id_path(images.ingest(p))
if __name__ == "__main__":
    for k, f in list(globals().items()):
        if k.startswith("test_"):
            f()
            print("ok", k)
