"""judge.py's measures and readers on synthetic data (no Blender): uv reader orientation on a hand-made GLB, explicit
back faces counted, measures zero against themselves, a planted blot found where it was put, the signed sharpness,
the A/B controls. Run: uv run python tests/test_judge.py"""
from __future__ import annotations

import json
import struct
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from hifipushie import judge as J  # noqa: E402


def _glb(path, X, U, F, img: Image.Image, double=False):
    """A one-mesh GLB with an embedded PNG base colour."""
    import io
    png = io.BytesIO()
    img.save(png, "PNG")
    blobs = [X.astype(np.float32).tobytes(), U.astype(np.float32).tobytes(), F.astype(np.uint32).tobytes(), png.getvalue()]
    views, off = [], 0
    for b in blobs:
        views.append({"buffer": 0, "byteOffset": off, "byteLength": len(b)})
        off += (len(b) + 3) // 4 * 4
    binc = b"".join(b + b"\0" * ((4 - len(b) % 4) % 4) for b in blobs)
    js = {"asset": {"version": "2.0"}, "buffers": [{"byteLength": len(binc)}], "bufferViews": views,
          "accessors": [{"bufferView": 0, "componentType": 5126, "count": len(X), "type": "VEC3"},
                        {"bufferView": 1, "componentType": 5126, "count": len(U), "type": "VEC2"},
                        {"bufferView": 2, "componentType": 5125, "count": F.size, "type": "SCALAR"}],
          "images": [{"bufferView": 3, "mimeType": "image/png"}], "textures": [{"source": 0}],
          "materials": [{"pbrMetallicRoughness": {"baseColorTexture": {"index": 0}}, "doubleSided": double}],
          "meshes": [{"name": "card", "primitives": [{"attributes": {"POSITION": 0, "TEXCOORD_0": 1}, "indices": 2,
                                                       "material": 0}]}],
          "nodes": [{"mesh": 0}], "scenes": [{"nodes": [0]}], "scene": 0}
    j = json.dumps(js).encode()
    j += b" " * ((4 - len(j) % 4) % 4)
    out = struct.pack("<III", 0x46546C67, 2, 12 + 8 + len(j) + 8 + len(binc))
    out += struct.pack("<II", len(j), 0x4E4F534A) + j + struct.pack("<II", len(binc), 0x004E4942) + binc
    Path(path).write_bytes(out)


def test_uv_reader_top_left():
    """glTF uv (0, 0) = the image's TOP-left: a red top half must read red at v = 0.25 (the r70 mis-read was a flip)."""
    a = np.zeros((64, 64, 3), np.float32)
    a[:32, :, 0] = 1.0  # top rows red
    a[32:, :, 2] = 1.0  # bottom rows blue
    assert J.texel_at(a, np.array([[0.5, 0.25]]))[0, 0] > 0.99
    assert J.texel_at(a, np.array([[0.5, 0.75]]))[0, 2] > 0.99


def test_glb_back_faces_and_probes():
    X = np.array([[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0]], float)
    U = np.array([[0, 0], [1, 0], [1, 1], [0, 1]], float)
    F = np.array([[0, 1, 2], [0, 2, 3], [2, 1, 0], [0, 0, 1]])  # a front pair, one explicit back face, a degenerate
    rng = np.random.default_rng(1)
    img = Image.fromarray((rng.random((32, 32, 3)) * 255).astype(np.uint8))
    with tempfile.TemporaryDirectory() as td:
        g = Path(td) / "t.glb"
        _glb(g, X, U, F, img)
        js, binc = J.read_glb(g)
        assert J.glb_triangles(js) == {"card": 4}
        assert J.glb_merged_faces(js, binc) == {"card": {"back": 1, "degenerate": 1}}
        assert J._engine_sides(g) == {"card": [True]}  # explicit back faces: drawn two-sided
        probes, ours = J.uv_probes(g, n=2, min_tris=1)
        assert len(probes) == 2 and len(ours["ours"]) == 2


def _face(w=160, seed=0):
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:w, 0:w]
    base = 150 + 30 * np.sin(xx / 9.0) * np.cos(yy / 13.0) + rng.normal(0, 3, (w, w))
    rgb = np.dstack([base, base * 0.8, base * 0.7]).clip(0, 255)
    a = (((xx - w / 2) ** 2 + (yy - w / 2) ** 2) < (0.45 * w) ** 2) * 255
    return Image.fromarray(np.dstack([rgb, a]).astype(np.uint8), "RGBA")


def test_measures_self_checks():
    ref = _face()
    for name, ok, detail in J.self_check_measures(ref):
        assert ok, (name, detail)


def test_blot_found_where_planted():
    ref = _face(seed=3)
    bad, at = J.plant_blot(ref, at=(60, 95))
    c = J.compare(bad, ref)
    assert np.hypot(c["worst"][0] - 60, c["worst"][1] - 95) < 0.08 * 160, c["worst"]
    assert c["spot"] > 1.0 and c["L50"] <= 0


def test_sharp_is_signed():
    from PIL import ImageFilter
    a = np.asarray(_face(seed=4)).copy()
    a[60:90, 50:110, :3] = (a[60:90, 50:110, :3] * 0.6).astype(np.uint8)  # a hard-edged decal (a lip sticker)
    ref = Image.fromarray(a, "RGBA")
    soft = ref.filter(ImageFilter.GaussianBlur(2))
    assert J.compare(soft, ref)["sharp"] < -0.1
    assert J.compare(ref, soft)["sharp"] > 0.1


def test_review_controls():
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "review.md"
        p.write_text("...\nKEY APPLIED:\nmouth: NEW\nbrows: OLD\nmouth_b: OLD\nmouth_c: NEW\nVERDICT: TIE\n")
        r = J.score_review(Path(td))
        assert r["controls_ok"] and r["votes"]["new"] == 1
        p.write_text("KEY APPLIED:\nmouth: NEW\nmouth_b: NEW\nmouth_c: NEW\nVERDICT: NEW\n")
        assert J.score_review(Path(td))["verdict"].startswith("REFUSED")


if __name__ == "__main__":
    for k, f in list(globals().items()):
        if k.startswith("test_"):
            f()
            print("ok", k)
