"""Face shapes in a look and the rest expression (facepose.py): weights with correctives filled in by formula (a
hand-set one kept and said), the posed mesh equal to the export's own shapes (faceshapes.apply on the same fine mesh),
the neutral's cache reused, face_shapes.rest written as the GLB meshes' default weights, and the evidence that a baked
rest can't reach a closed mouth. Our own mesher only: no Blender.

Run: uv run python tests/test_facepose.py   (or pytest)."""

from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path

_TMP = tempfile.mkdtemp(prefix="hp-facepose-")
os.environ["HIFIPUSHIE_HOME"] = _TMP  # before hifipushie.store reads it

import numpy as np  # noqa: E402
import pytest  # noqa: E402
from PIL import Image  # noqa: E402

from hifipushie import asset, facepose, faceshapes, store  # noqa: E402
from hifipushie.spec import SpecError  # noqa: E402

store.HOME = Path(_TMP)
EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "goblin_talk.json"
RES = 96
GRIN = {"jawOpen": 0.5, "mouthSmileLeft": 0.4, "mouthSmileRight": 0.4}


def _model(rest: dict | None = None) -> str:
    spec = json.loads(EXAMPLE.read_text())
    if rest is not None:
        spec["face_shapes"] = {**(spec.get("face_shapes") or {}), "rest": rest}
    store.save("gob", spec, "test")
    return "gob"


def test_weights():
    w = facepose.weights(GRIN)
    assert w["jawOpen_mouthSmile"] == pytest.approx(0.4)  # min(jawOpen, mouthSmile), as the export's notes say
    assert "jawOpen_mouthClose" not in w  # (mouthClose not in the pose: no such target to set)
    w = facepose.weights({**GRIN, "jawOpen_mouthSmile": 0.2})
    assert w["jawOpen_mouthSmile"] == 0.2 and "kept as given" in facepose.NOTES[0]
    with pytest.raises(SpecError):
        facepose.weights({"jawOpne": 0.5})
    with pytest.raises(SpecError):
        facepose.weights({"jawOpen": 1.5})
    with pytest.raises(SpecError):
        facepose.rest_of({"face_shapes": {"rest": "grin"}})
    assert facepose.rest_of({}) == {}


def test_pose_is_the_exports_shapes():
    name = _model()
    spec = store.load(name)
    path, info = facepose.pose(name, GRIN, RES)
    with np.load(path) as z:
        X, pnames = z["verts"].astype(np.float64), [str(n) for n in z["part_names"]]
    assert "body" in info["moved"]
    # the export's path on the same fine mesh, whole parts, no shortcuts
    with np.load(Path(path).with_name("face_fine.npz")) as z:
        V, F, P = z["verts"].astype(np.float64), z["faces"], z["part"]
    w = facepose.weights(GRIN)
    for i, pn in enumerate(pnames):
        if pn not in info["moved"]:
            continue
        keep = np.flatnonzero(P == i)
        remap = np.full(len(V), -1)
        remap[keep] = np.arange(len(keep))
        tri = remap[F[np.all(P[F] == i, axis=1)]]
        n = faceshapes.vertex_normals(V[keep], tri)[tri.ravel()]
        parts = {pn: {"verts": V[keep], "corner_vert": tri.ravel(), "normal": n.astype(np.float32),
                      "tangent": np.tile([1.0, 0, 0], (len(n), 1)).astype(np.float32)}}
        faceshapes.apply(spec, parts, [k for k in GRIN], [])
        p = parts[pn]
        want = p["verts"] + sum(w.get(nm, 0.0) * sh[0] for nm, sh in p["shapes"].items())
        err = np.linalg.norm(X[keep] - want, axis=1).max()
        assert err < 2e-4, (pn, err)  # float32 storage; the seal measured on the face's region, not the whole part


def test_neutral_cached_and_reused():
    name = _model()
    facepose.pose(name, GRIN, RES)
    p1, i1 = facepose.pose(name, {"jawOpen": 0.2}, RES)
    log: list = []
    t = time.time()
    p2, i2 = facepose.pose(name, {"jawOpen": 0.2}, RES, log)
    assert "face mesh: cached" in log and time.time() - t < 30
    with np.load(p2) as z:
        a = z["verts"].copy()
    _, i3 = facepose.pose(name, {}, RES)  # no shape: the closed neutral
    with np.load(p2) as z:
        b = z["verts"]
    assert np.abs(a - b).max() > 1e-4  # (the neutral differs from jawOpen 0.2)
    assert all(np.abs(d).max() > 0 for _, d in i3["moved"].values()) and "body" in i3["moved"]  # the slit closed


def test_rest_in_the_glb():
    name = _model(rest=GRIN)
    rest = facepose.rest_of(store.load(name))
    assert rest["jawOpen_mouthSmile"] == pytest.approx(0.4)
    spec = store.load(name)
    fine = faceshapes.Face(spec).voxels()
    ctx = asset.split(spec, RES, True, [], min_share=1, voxels=fine)
    path = asset.mesh_parts(ctx, Path(_TMP) / "high.npz")
    with np.load(path) as z:
        V, F, P, names = z["verts"], z["faces"], z["part"], [str(n) for n in z["part_names"]]
    parts = {}
    for i, pn in enumerate(names):
        keep = np.flatnonzero(P == i)
        remap = np.full(len(V), -1)
        remap[keep] = np.arange(len(keep))
        tri = remap[F[np.all(P[F] == i, axis=1)]]
        v = V[keep].astype(np.float64)
        cv = tri.ravel()
        parts[pn] = {"verts": v, "corner_vert": cv, "normal": faceshapes.vertex_normals(v, tri)[cv].astype(np.float32),
                     "tangent": np.tile([1.0, 0, 0], (len(cv), 1)).astype(np.float32),
                     "uv": np.zeros((len(cv), 2), np.float32), "sign": np.ones(len(cv), np.float32), "atlas": 0}
    faceshapes.apply(spec, parts, ["jawOpen", "mouthSmileLeft", "mouthSmileRight", "eyeBlinkLeft"], [])
    for p in parts.values():
        if p.get("shapes"):
            p["shape_rest"] = rest
    png = Path(_TMP) / "flat.png"
    Image.new("RGBA", (4, 4), (128, 128, 255, 255)).save(png)
    glb = Path(_TMP) / "gob.glb"
    asset.write_glb(glb, "gob", parts, [("0", {"basecolor": png, "orm": png, "normal": png, "specular": png})])
    got = faceshapes.read_glb(glb)
    body = got["body"]
    ws = dict(zip(body["names"], body["weights"]))
    assert ws["jawOpen"] == pytest.approx(0.5) and ws["eyeBlinkLeft"] == 0.0
    assert ws["jawOpen_mouthSmile"] == pytest.approx(0.4)
    raw = glb.read_bytes()
    js = json.loads(raw[20:20 + int.from_bytes(raw[12:16], "little")])
    m = next(m for m in js["meshes"] if m["name"] == "body")
    assert m["extras"]["restExpression"]["mouthSmileLeft"] == pytest.approx(0.4)


def test_baked_rest_cannot_close_the_mouth():
    name = _model()
    r = facepose.compare_rest(name, GRIN, {"neutral": {}, "rest": GRIN}, RES)
    assert r["rest"] < 1e-3 and r["neutral"] > 2.0  # mm: engines clamp the negative jawOpen a baked grin would need


if __name__ == "__main__":
    for k, f in list(globals().items()):
        if k.startswith("test_"):
            f()
            print("ok", k)
