"""A reference picture projected onto the head (likeness_texture.project; likeness_read.project_reference shares its
visibility rule), on a synthetic head with a synthetic "photo": the model's own lit render with coloured marks at
known landmarks. uv run python tests/test_likeness_texture.py"""
import json
import sys

import numpy as np

from hifipushie import assets, humanfit as hf, likeness as lk, likeness_texture as lt


def _have():
    try:
        assets.pack("gnm")
        assets.pack("makehuman")
        return True
    except Exception as err:
        print("skipped:", str(err)[:80])
        return False


_C = {}


def setup():
    if _C:
        return _C
    b = {"body": {"source": "human", "age": 40, "sex": 1.0}, "head": {"seed": 3, "spread": 0.5}}
    mesh = lk.model_mesh(b)
    L = np.asarray(mesh["L"], float)
    w, h = 640, 800
    cam = {"r": [0.0, 0.0, 0.0], "yaw": 0.0, "centre": L[:68].mean(0).tolist(), "t": [0.0, 0.0, 1.6], "f": 2400.0, "size": [w, h]}
    im, k = lk.render(mesh, cam, (0.0, 0.0, float(w), float(h)), px=max(w, h), brows=False)[:2]
    photo = np.asarray(im.convert("RGB").resize((w, h)), float)
    marks = {30: (255, 0, 0), 54: (0, 255, 0), 27: (0, 0, 255)}         # nose tip, the left mouth corner, nasion
    yy, xx = np.mgrid[0:h, 0:w]
    for i, c in marks.items():
        u, v = hf.project(cam, L[i][None])[0]
        photo[(xx - u) ** 2 + (yy - v) ** 2 < 5 ** 2] = c
    _C.update(b=b, mesh=mesh, L=L, cam=cam, photo=photo, marks=marks)
    return _C


def _texel(r, cam_o, X):
    u, v = hf.project(cam_o, np.asarray(X, float)[None])[0]
    return r["rgba"][int(round(v - 0.5)), int(round(u - 0.5))]


def test_projection_lands_where_the_camera_saw_it():
    """The marks painted on the picture at three landmarks come out at those landmarks' own texels of the
    orthographic image; the decal's frame is the camera's; the picture is not laid on ears, under the jaw, or on
    skin turned away from the camera."""
    c = setup()
    r = lt.project(c["mesh"], c["cam"], c["photo"], delight=False, match=None)
    n = r["rgba"].shape[0]
    io = float(np.linalg.norm(c["L"][36:42].mean(0) - c["L"][42:48].mean(0)))
    cam_o = lt.ortho_camera(c["cam"], c["L"][:68].mean(0), 2.1 * io, r["px_per_m"])
    assert cam_o["size"][0] == n
    for i, col in c["marks"].items():
        px = _texel(r, cam_o, c["L"][i]).astype(int)
        want = np.array(col)
        assert np.abs(px[:3] - want).max() < 90, (i, px, want)
    assert _texel(r, cam_o, c["L"][30])[3] > 200                       # the nose tip faces the camera: trusted
    assert np.allclose(r["dir"], [0, -1, 0], atol=1e-6) and np.allclose(r["up"], [0, 0, 1], atol=1e-6)
    assert abs(r["size"][0] - 4.2 * io) < 1e-4
    assert 0.15 < r["coverage"] < 0.9, r["coverage"]
    V = np.asarray(c["mesh"]["V"])
    ears = V[c["mesh"]["ears"]]
    a_ear = [int(_texel(r, cam_o, p)[3]) for p in ears[:: max(len(ears) // 60, 1)]]
    assert max(a_ear) < 40, max(a_ear)
    under = c["L"][8] + np.array([0.0, 0.02, -0.03])                    # under the chin, on the neck
    assert _texel(r, cam_o, under)[3] < 10
    side = c["L"][2]                                                    # the jaw's side by the ear: turned away
    assert _texel(r, cam_o, side)[3] < 128


def test_delight_flattens_the_shading_and_tone_matches():
    """The synthetic picture is one grey skin under one light: de-lit, the confident texels' lightness varies much
    less; matched to a tone, their median is that tone."""
    c = setup()
    raw = lt.project(c["mesh"], c["cam"], c["photo"], delight=False, match=None)
    dl = lt.project(c["mesh"], c["cam"], c["photo"], delight=True, match=None)
    conf = raw["rgba"][..., 3] > 230
    sd = lambda r: float(np.std(r["rgba"][..., :3][conf].mean(1)))      # noqa: E731
    assert dl["light"] is not None and sd(dl) < 0.6 * sd(raw), (sd(dl), sd(raw))
    tone = [0.8, 0.62, 0.52]
    tm = lt.project(c["mesh"], c["cam"], c["photo"], delight=True, match="tone", skin_tone=tone)
    med = np.median(tm["rgba"][..., :3][conf], 0) / 255.0
    assert np.abs(med - tone).max() < 0.08, med


def test_layers_and_stale(tmp_path=None):
    """make() writes one decal layer per picture (colour = the image, the camera's own axis); a layer made on another
    head shape is reported stale."""
    import tempfile
    from pathlib import Path
    from PIL import Image
    from hifipushie import store
    c = setup()
    tmp = Path(tmp_path or tempfile.mkdtemp())
    home = store.HOME
    store.HOME = tmp
    try:
        (tmp / "m").mkdir(exist_ok=True)
        Image.fromarray(c["photo"].astype(np.uint8)).save(tmp / "photo.png")
        (tmp / "m" / "human_refs.json").write_text(json.dumps({"views": [{"image": str(tmp / "photo.png"), "size": c["cam"]["size"],
                                                                            "yaw": 0.0, "points": {}}], "cameras": [c["cam"]]}))
        spec = {"base": c["b"], "paint": {}}
        r = lt.make("m", base=c["b"], out_dir=str(tmp / "m"), spec=spec)
        ly = r["layers"]["ref_texture_0"]
        assert ly["color"] == "image" and ly["image"]["channel"] == "alpha" and Path(ly["image"]["file"]).exists()
        assert "the PICTURE" in r["text"] and "OURS" in r["text"]
        spec["paint"].update(r["layers"])
        assert lt.stale(spec) == []
        other = {**spec, "base": {**c["b"], "head": {**c["b"]["head"], "shape": {"lean": 0.004}}}}
        assert lt.stale(other) == ["ref_texture_0"]
    finally:
        store.HOME = home


def test_harmonise_hands_the_edge_over_to_our_skin():
    """The picture against "our" unlit skin through the decal's camera: its confident skin takes our median colour,
    at its outer edge its low frequencies become ours (no colour step when the head turns) while its fine detail and
    its middle stay the picture's; the eyes' holes are not edges."""
    from scipy import ndimage
    n, ppm = 400, 2000.0
    yy, xx = np.mgrid[0:n, 0:n]
    r = np.hypot(xx - n / 2, yy - n / 2)
    A = np.clip((150 - r) / 8.0, 0, 1)
    A[(np.hypot(xx - 160, yy - 170) < 14)] = 0.0                      # an eye hole
    pic = np.zeros((n, n, 4), np.uint8)
    base = np.array([150.0, 110.0, 90.0])                             # the picture: darker and redder than ours ...
    pic[..., :3] = np.clip(base + 25 * (np.sin(xx / 3.0) > 0)[..., None] - 30 * (xx > n / 2)[..., None], 0, 255)  # fine stripes, a darker half
    pic[..., 3] = (A * 255).astype(np.uint8)
    ours = np.zeros((n, n, 3), np.uint8)
    ours[:] = (200, 160, 140)
    out = lt.harmonise({"rgba": pic, "px_per_m": ppm}, ours, np.ones((n, n), bool))
    o = out["rgba"].astype(float)
    lin = lambda c: lt._to_lin(c)                                     # noqa: E731
    # the confident skin's median is ours
    conf = A > 0.9
    assert np.allclose(np.median(lin(o[..., :3])[conf], 0), np.median(lin(ours.astype(float))[conf], 0), rtol=0.12), out["gain_to_ours"]
    # at the outer edge the low frequencies are ours (both halves), the fine stripes stay
    ring = (r > 135) & (r < 146)
    low = ndimage.gaussian_filter(lin(o[..., :3]), (12, 12, 0))
    assert np.abs(np.log(low[ring] / lin(ours.astype(float))[ring])).max() < 0.12
    mid = (r < 60)
    left, right = lin(o[..., :3])[mid & (xx < n / 2 - 10)].mean(0), lin(o[..., :3])[mid & (xx > n / 2 + 10)].mean(0)
    assert left[0] / right[0] > 1.25                                   # the middle keeps the picture's own darker half
    row = lin(o[n // 2, 60:120, :3])[:, 0]
    assert row.std() / row.mean() > 0.05                               # stripes survive near the edge
    # alpha fades to the edge, and the eye's hole made no fade round itself
    assert o[..., 3][ring].max() < 255 * 0.9 and o[..., 3][(r < 100) & (np.hypot(xx - 160, yy - 170) > 30)].min() > 250
    assert o[170, 160 + 20, 3] > 250


if __name__ == "__main__":
    if _have():
        for k in sys.argv[1:] or [k for k in dict(globals()) if k.startswith("test_")]:
            globals()[k]()
            print("ok", k)
