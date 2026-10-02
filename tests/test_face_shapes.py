"""Face shapes (faceshapes.py, kits.face.mouth.interior, export_asset(face_shapes=...)): the mouth interior the kit
builds, the shapes on a meshed goblin (which parts move, where, the closed neutral) and the GLB round trip (target
names and counts per part, vertex counts equal to the neutral, deltas zero where nothing moves, sparse accessors
decoded back to what was written). Meshes with our own mesher only: no Blender.

Run: uv run python tests/test_face_shapes.py   (or pytest)."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

_TMP = tempfile.mkdtemp(prefix="hp-faceshapes-")
os.environ["HIFIPUSHIE_HOME"] = _TMP  # before hifipushie.store reads it

import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402

from hifipushie import asset, faceshapes, sdf, store  # noqa: E402
from hifipushie.spec import SpecError, compile_prims  # noqa: E402

store.HOME = Path(_TMP)
EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "goblin_talk.json"
_PARTS: dict = {}


def _spec() -> dict:
    return json.loads(EXAMPLE.read_text())


def _parts() -> dict:
    """The goblin's export parts as the low poly would carry them, but straight from our mesher (the slit's part at
    the face shapes' voxel): verts, corner_vert, per-corner normal/tangent/uv/sign, atlas 0."""
    if _PARTS:
        return _PARTS
    spec = _spec()
    fine = faceshapes.Face(spec).voxels()
    ctx = asset.split(spec, 96, True, [], min_share=1, voxels=fine)
    path = asset.mesh_parts(ctx, Path(_TMP) / "high.npz")
    with np.load(path) as z:
        V, F, P, names = z["verts"], z["faces"], z["part"], [str(n) for n in z["part_names"]]
    for i, pn in enumerate(names):
        keep = np.flatnonzero(P == i)
        remap = np.full(len(V), -1)
        remap[keep] = np.arange(len(keep))
        tri = remap[F[np.all(P[F] == i, axis=1)]]
        v = V[keep].astype(np.float64)
        n = faceshapes.vertex_normals(v, tri)
        cv = tri.ravel()
        t = np.cross(n[cv], [0.0, 0.0, 1.0])
        t[np.linalg.norm(t, axis=1) < 1e-6] = [1.0, 0.0, 0.0]
        _PARTS[pn] = {"verts": v, "corner_vert": cv, "normal": n[cv].astype(np.float32),
                      "tangent": (t / np.linalg.norm(t, axis=1, keepdims=True)).astype(np.float32),
                      "uv": np.zeros((len(cv), 2), np.float32), "sign": np.ones(len(cv), np.float32), "atlas": 0}
    return _PARTS


def test_kit_interior():
    """The slit opens the lips into the bag; teeth and tongue are parts of their own inside it."""
    spec = _spec()
    face = faceshapes.Face(spec)
    prims = compile_prims(spec)
    body = [p for p in prims if p.part == "body"]
    inside = face.M - face.out * (face.thick + face.bag[1])  # the bag's middle
    lips = face.M - face.out * 0.5 * face.thick              # between the lips, half way to the bag
    cheek = face.M - face.out * face.thick + face.up * 3 * face.lip  # the upper lip's flesh
    f = sdf.field_at(body, np.array([inside, lips, cheek]))
    assert f[0] > 0 and f[1] > 0 and f[2] < 0, f
    assert face.parts_teeth == {"teeth"} and face.parts_tongue == {"tongue"}
    assert {p.part for p in prims} >= {"body", "eyes", "teeth", "tongue"}
    assert face.voxels()["body"] < face.slit / 2


def test_needs_interior():
    spec = _spec()
    del spec["kits"]["face"]["mouth"]["interior"]
    try:
        faceshapes.Face(spec)
    except SpecError as e:
        assert "interior" in str(e)
    else:
        raise AssertionError("a face without a mouth interior can't take face shapes")
    try:
        faceshapes.names_of(["jawOpen", "visemeAA"])
    except SpecError as e:
        assert "visemeAA" in str(e)
    else:
        raise AssertionError("unknown names are refused")


def test_shapes_on_the_goblin():
    parts = {pn: dict(p) for pn, p in _parts().items()}
    before = {pn: p["verts"].copy() for pn, p in parts.items()}
    log = []
    got = faceshapes.apply(_spec(), parts, True, log)
    names = list(faceshapes.ALL)
    assert set(got) == {"body", "teeth", "tongue"}, got  # the eyeballs don't move
    assert all(got[pn] == names for pn in got)
    face = faceshapes.Face(_spec())
    body = parts["body"]
    S = body["shapes"]
    assert list(S) == names
    # nothing moves away from the face: hands, feet, the back of the head
    far = np.linalg.norm(before["body"] - face.M, axis=1) > 3 * face.width + 2 * face.R
    for nm, (d, n0, n1) in S.items():
        assert d.shape == before["body"].shape and n0.shape == n1.shape == d.shape
        assert np.abs(d[far]).max() == 0.0, nm
        assert np.abs(d).max() > 1e-4, f"{nm} moves nothing"
    # the neutral closed the slit: lip vertices moved toward the parting line, nothing else
    moved = np.linalg.norm(body["verts"] - before["body"], axis=1)
    assert 0.3 * face.slit < moved.max() <= 0.51 * face.slit + 1e-6, moved.max()
    assert moved[far].max() == 0.0
    L = face.local(before["body"])
    up_lip = (moved > 0.2 * face.slit) & (L["h0"] > 0)
    lo_lip = (moved > 0.2 * face.slit) & (L["h0"] < 0)
    assert up_lip.sum() > 10 and lo_lip.sum() > 10
    assert ((body["verts"][up_lip] - before["body"][up_lip]) @ face.up < 0).all()
    assert ((body["verts"][lo_lip] - before["body"][lo_lip]) @ face.up > 0).all()
    # jawOpen: the chin goes down, the forehead stays
    d = S["jawOpen"][0]
    chin = (L["u"] < 0.3) & (L["h0"] < -2 * face.lip) & (L["back"] < face.thick)
    brow = (L["u"] < 0.3) & (L["h0"] > 0.5 * face.R)
    assert (d[chin] @ face.up).mean() < -0.3 * face.width * np.sin(face.open), (d[chin] @ face.up).mean()
    assert np.abs(d[brow]).max() < 1e-9
    # left is the creature's left (+X here)
    sl = S["mouthSmileLeft"][0]
    xs = (before["body"] - face.M) @ face.side
    assert np.abs(sl[xs < -0.3 * face.W2]).max() < 1e-9 and np.abs(sl[xs > 0.5 * face.W2]).max() > 1e-3
    # teeth: the lower row rides the jaw, the upper row never moves
    t = parts["teeth"]
    dj = t["shapes"]["jawOpen"][0]
    up_row = face.local(before["teeth"])["h0"] > 0.5 * face.bag[2]
    assert np.abs(dj[up_row]).max() == 0.0 and np.abs(dj).max() > 1e-3
    assert np.abs(t["shapes"]["mouthSmileLeft"][0]).max() == 0.0
    # the tongue comes out past the lips
    to = parts["tongue"]["shapes"]["tongueOut"][0]
    tip = (parts["tongue"]["verts"] + to) @ face.out
    assert tip.max() > face.M @ face.out, (tip.max(), face.M @ face.out)


def test_glb_round_trip():
    parts = {pn: dict(p) for pn, p in _parts().items()}
    faceshapes.apply(_spec(), parts, ["jawOpen", "mouthSmileLeft", "eyeBlinkLeft", "tongueOut"], [])
    png = Path(_TMP) / "flat.png"
    Image.new("RGBA", (4, 4), (128, 128, 255, 255)).save(png)
    glb = Path(_TMP) / "goblin.glb"
    asset.write_glb(glb, "goblin", parts, [("0", {"basecolor": png, "orm": png, "normal": png, "specular": png})])
    got = faceshapes.read_glb(glb)
    assert set(got) == set(parts)
    for pn, p in parts.items():
        g = got[pn]
        if not p.get("shapes"):  # parts that don't move carry no targets at all
            assert g["names"] == [] and g["targets"] == [], pn
            continue
        assert g["names"] == list(p["shapes"]) and g["weights"] == [0.0] * len(g["names"])
        assert len(g["targets"]) == len(g["names"])
        pos, nrm, tan, uv, idx, src = asset._gltf_vertices(p)
        assert g["count"] == len(pos)
        for name, t in zip(g["names"], g["targets"]):
            assert t["POSITION"].shape == (len(pos), 3) and t["NORMAL"].shape == (len(pos), 3)
            want = p["shapes"][name][0][src] @ asset._Z_TO_Y.T
            assert np.abs(t["POSITION"] - want).max() < 1e-6, (pn, name)
            # where nothing round a vertex moves, neither does its normal
            tri = p["corner_vert"].reshape(-1, 3)
            mv = np.abs(p["shapes"][name][0]).max(1) > 0
            loud = np.zeros(len(mv), bool)
            loud[tri[mv[tri].any(1)].ravel()] = True
            quiet = ~loud[src]
            assert not quiet.any() or np.abs(t["NORMAL"][quiet]).max() < 1e-6, (pn, name)
            assert not mv.any() or np.abs(t["NORMAL"][~quiet]).max() > 0, (pn, name)
    assert np.abs(got["teeth"]["targets"][1]["POSITION"]).max() == 0.0  # mouthSmileLeft: teeth stay


if __name__ == "__main__":
    for k, f in list(globals().items()):
        if k.startswith("test_"):
            f()
            print("ok", k)
