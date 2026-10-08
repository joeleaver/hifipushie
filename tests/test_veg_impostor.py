"""Hemi-octahedral impostors (veg_impostor): the mapping, the reference view, the export. uv run python tests/test_veg_impostor.py"""
import json
import struct
import tempfile
from pathlib import Path

import numpy as np

from hifipushie import veg_export, veg_impostor as vi, vegetation as v


def test_mapping():
    """Directions <-> hemi-oct coordinates both ways; the grid's border is the horizon; each frame's basis is
    orthonormal and right-handed (right x up = toward the camera)."""
    rng = np.random.default_rng(1)
    d = rng.normal(size=(500, 3))
    d[:, 1] = np.abs(d[:, 1])
    d /= np.linalg.norm(d, axis=1, keepdims=True)
    assert np.allclose(vi.decode(vi.encode(d)), d, atol=1e-9)
    F = vi.frame_dirs(8)
    edge = np.r_[F[0].reshape(-1, 3), F[-1].reshape(-1, 3), F[:, 0].reshape(-1, 3), F[:, -1].reshape(-1, 3)]
    assert np.allclose(edge[:, 1], 0, atol=1e-9) and (F[1:-1, 1:-1, 1] > 0).all()
    R, U = vi.basis(F.reshape(-1, 3))
    assert np.allclose(np.cross(R, U), F.reshape(-1, 3), atol=1e-9) and np.allclose(np.linalg.norm(R, axis=1), 1)
    r0, u0 = vi.basis(np.array([[0, 0, 1.0]]))
    assert np.allclose(r0, [1, 0, 0]) and np.allclose(u0, [0, 1, 0])  # a camera on +z: image right = +x, up = +y


def _ball_atlas(n=8, px=64, size=10.0, ball=(2.5, 1.0, 0.0), r=1.2):
    """An atlas made the way the bake makes it, of one ball off the centre (analytic: alpha, colour by height, depth)."""
    C = np.array([0.0, 5.0, 0.0])
    b = C + np.array(ball)
    img = np.zeros((n * px, n * px, 4), np.float32)
    nrm = np.zeros((n * px, n * px, 4), np.float32)
    t = (np.arange(px) + 0.5) / px - 0.5
    X, Y = np.meshgrid(t, -t)
    F = vi.frame_dirs(n)
    for i in range(n):
        for j in range(n):
            d = F[i, j]
            R, U = vi.basis(d[None])
            P = C + size * (X[..., None] * R[0] + Y[..., None] * U[0])  # points on the frame's middle plane
            q = P - b
            along = q @ d
            perp = q - along[..., None] * d
            hit = np.linalg.norm(perp, axis=-1) < r
            front = b + perp + d * np.sqrt(np.maximum(r * r - (perp ** 2).sum(-1), 0))[..., None]
            dep = -((front - C) @ d)  # behind the middle plane
            sl = (slice(j * px, (j + 1) * px), slice(i * px, (i + 1) * px))
            img[sl] = np.dstack([np.repeat(((front[..., 1] - 3) / 5)[..., None], 3, -1), hit])
            nrm[sl] = np.dstack([np.full(X.shape + (3,), 0.5), np.clip(dep / size + 0.5, 0, 1)])
    return {"image": img, "normal": nrm, "frames": n, "size": size, "centre": C.tolist()}


def test_view_lands_where_the_plant_is():
    """Between frames the reference view draws the ball where it is seen from there (frames blended, parallax by
    depth): IoU against the true disc, better with the depth step."""
    A = _ball_atlas()
    C = np.array(A["centre"])
    b, r, size, px = C + [2.5, 1.0, 0.0], 1.2, A["size"], 128
    for el, az in ((0, 25), (20, 140), (45, 300), (80, 10)):
        e, a = np.radians(el), np.radians(az)
        d = np.array([np.sin(a) * np.cos(e), np.sin(e), np.cos(a) * np.cos(e)])
        R, U = vi.basis(d[None])
        t = (np.arange(px) + 0.5) / px - 0.5
        X, Y = np.meshgrid(t, -t)
        P = C + size * (X[..., None] * R[0] + Y[..., None] * U[0])
        q = P - b
        true = np.linalg.norm(q - (q @ d)[..., None] * d, axis=-1) < r
        ious = []
        for par in (0, 1):
            m = vi.view(A, d, px, parallax=par)[..., 3] > 0.5
            ious.append((m & true).sum() / max((m | true).sum(), 1))
        assert ious[1] > 0.85 and ious[1] >= ious[0] - 0.01, (el, az, ious)


def test_export_one_quad_with_its_recipe():
    T = v.grow({"species": "birch", "age": 12, "style": "blobby"})
    A = _ball_atlas(n=4, px=16)
    imp = {**A, "kind": vi.KIND, "normal": A["normal"],
           "seasons": {"winter": {"image": np.zeros_like(A["image"]), "normal": A["normal"]}}}
    with tempfile.TemporaryDirectory() as tmp:
        p = veg_export.write_impostor(T, str(Path(tmp) / "i.glb"), "b", imp, ("summer", "winter"))
        raw = open(p, "rb").read()
        G = json.loads(raw[20:20 + struct.unpack("<I", raw[12:16])[0]])
        pr = G["meshes"][0]["primitives"][0]
        m = G["materials"][pr["material"]]
        assert G["accessors"][pr["indices"]]["count"] == 6 and "normalTexture" not in m
        hi = m["extras"]["hifipushie_impostor"]
        assert hi["kind"] == vi.KIND and hi["frames"] == 4 and abs(hi["size"] - A["size"]) < 1e-6 and m["extras"]["receive_shadows"] is False
        assert G["meshes"][0]["extras"]["cull_margin_m"] > 0 and "OBJECT" in hi["normal"].upper()
        sj = veg_export.seasons_json(p)
        assert sj["contract"]["version"] >= 6 and sj["impostor"]["kind"] == vi.KIND
        for se in ("summer", "winter"):
            sl = sj["seasons"][se]["impostor"]
            assert Path(tmp, sl["baseColorTexture"]["file"]).exists() and Path(tmp, sl["impostorNormalTexture"]["file"]).exists()
        assert sj["seasons"]["winter"]["impostor"]["baseColorTexture"]["file"] != sj["seasons"]["summer"]["impostor"]["baseColorTexture"]["file"]
        # the quad is cropped to what the frames draw (a ball well inside its frames), and the stored quad matches
        c = hi["crop"]
        assert sj["impostor"]["crop"] == c and 0 < c[0] < c[1] < 1 and 0 < c[2] < c[3] < 1 and (c[1] - c[0]) * (c[3] - c[2]) < 0.8


def test_crop_covers_every_drawn_pixel():
    """`crop` holds every pixel any frame of any picture draws, plus a margin, and never leaves 0..1."""
    n, px = 2, 20
    a = np.zeros((n * px, n * px, 4), np.float32)
    a[3:12, 25:31, 3] = 1  # frame (1, 0): u 5..10 px, v 3..11 px of 20
    b = np.zeros_like(a)
    b[30:39, 2:18, 3] = 1  # frame (0, 1): u 2..17, v 10..18
    c = vi.crop([a, b], n, margin=0.0)
    assert c == [0.1, 0.9, 0.15, 0.95], c
    assert vi.crop([np.zeros_like(a)], n) == [0.0, 1.0, 0.0, 1.0]
    cr = vi.crops([a, b], n, margin=0.0)  # (per frame: k = column * n + row)
    assert cr[1 * n + 0] == [0.25, 0.55, 0.15, 0.6] and cr[0 * n + 1] == [0.1, 0.9, 0.5, 0.95] and cr[0] == [0.5, 0.5, 0.5, 0.5], cr
    assert vi.drawn_share(cr, n) < 0.5


if __name__ == "__main__":
    for k, f in list(globals().items()):
        if k.startswith("test_"):
            f()
            print("ok", k)
