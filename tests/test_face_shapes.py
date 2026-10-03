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
    names = faceshapes.names_of(True)
    assert len(names) == 53 and names[-1] == "jawOpen_mouthClose"  # all 52 ARKit names + the corrective
    assert set(got) == {"body", "teeth", "tongue", "eyes"}, got  # the eyeballs: only eyeLook*
    assert all(got[pn] == names for pn in got)
    E = parts["eyes"]["shapes"]
    assert all(np.abs(E[nm][0]).max() == 0 for nm in names if not nm.startswith("eyeLook"))
    assert all(np.abs(E[nm][0]).max() > 1e-3 for nm in names if nm.startswith("eyeLook"))
    face = faceshapes.Face(_spec())
    body = parts["body"]
    S = body["shapes"]
    assert list(S) == names
    # nothing moves away from the face: hands, feet, the back of the head
    far = np.linalg.norm(before["body"] - face.M, axis=1) > 3 * face.width + 2 * face.R
    for nm, (d, n0, n1) in S.items():
        assert d.shape == before["body"].shape and n0.shape == n1.shape == d.shape
        assert np.abs(d[far]).max() == 0.0, nm
        assert nm.startswith("eyeLook") or np.abs(d).max() > 1e-4, f"{nm} moves nothing"
    _no_shared_offset(S)
    # mouthClose alone barely moves (A2F drives it with the jaw shut); the corrective does the closing
    assert np.linalg.norm(S["mouthClose"][0], axis=1).max() < 0.2 * np.linalg.norm(S["jawOpen_mouthClose"][0], axis=1).max()
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


def _no_shared_offset(S: dict):
    """No vertex moves by one identical offset in every mouth shape (a baked-in neutral mismatch: round 2's GNM
    lower lids took the eyeball push in all 23)."""
    mouth = [k for k in S if k.startswith("mouth")]
    stack = np.stack([S[k][0] for k in mouth])
    spread = np.linalg.norm(stack - stack[0], axis=2).max(0)
    mag = np.linalg.norm(stack[0], axis=1)
    shared = (mag > 1e-3) & (spread < 1e-4)
    assert shared.sum() == 0, f"{shared.sum()} vertices move identically in all {len(mouth)} mouth shapes"


def test_focus_warp():
    """The decimation's focus warp (focuswarp.py) is undone exactly, magnifies near a sphere and leaves far points."""
    from hifipushie import focuswarp
    S = [[0.0, 0.0, 0.0, 0.02, 2.0], [0.03, 0.0, 0.0, 0.02, 2.0], [0.0, 0.05, 0.0, 0.06, 1.5]]
    P = np.random.default_rng(0).uniform(-0.1, 0.1, (5000, 3))
    Q = focuswarp.warp(P, S)
    assert np.abs(focuswarp.unwarp(Q, S) - P).max() < 1e-9
    a = focuswarp.warp(np.array([[0.001, 0, 0], [0.002, 0, 0]]), S[:1])
    assert abs(np.linalg.norm(a[1] - a[0]) - 0.002) < 1e-4  # 2x at the centre
    far = np.array([[1.0, 1.0, 1.0]])
    assert np.abs(focuswarp.warp(far, S) - far).max() < 1e-12


GNM_EXAMPLE = EXAMPLE.with_name("gnm_talk.json")


def _gnm():
    """The gnm_talk head (MakeHuman body, GNM head) and its anatomy; None without the GNM asset pack."""
    from hifipushie import assets, base
    try:
        assets.path("gnm", base.GNM)
    except Exception:
        return None
    spec = json.loads(GNM_EXAMPLE.read_text())
    return spec, faceshapes.face_of(spec)


def test_gnm_head_shapes():
    """On a GNM head the shapes are GNM's expression basis carried onto the mesh: tried on the head mesh itself
    (as the low poly), its jaw's interior by the jaw's rigid motion. Slow (~3 min: the MakeHuman body and the GNM
    head are built); skipped without the GNM pack."""
    got = _gnm()
    if got is None:
        print("skip: no GNM asset pack ($HIFIPUSHIE_ASSETS)")
        return
    spec, face = got
    assert isinstance(face, faceshapes.GnmFace)
    h = face.head
    V = np.asarray(h["verts"], float)
    T = np.array([(f[0], f[j], f[j + 1]) for f in h["faces"] for j in range(1, len(f) - 1)])
    # the neutral closes the parted lips: inner lip landmarks meet
    lm = h["lm68"]
    face.neutral(V, "skin")
    close, _ = face._onto(lm, face._gnm["close"])
    gap0 = np.linalg.norm(lm[62] - lm[66])
    gap1 = np.linalg.norm(lm[62] + close[62] - lm[66] - close[66])
    assert gap0 > 0.002 and gap1 < 0.35 * gap0, (gap0, gap1)
    n0 = faceshapes.vertex_normals(V, T)
    names = faceshapes.names_of(True)
    D = face.displacements(V, V, n0, "skin", names)
    assert list(D) == names
    _no_shared_offset({k: (d,) for k, d in D.items()})
    # mouth shapes stay below the lower lids, lid/brow shapes above the nose's base (the basis's regions reach
    # further: jawOpen moved the forehead, mouth shapes the under-eye skin)
    h = (V - face.M) @ face.up
    hl = np.mean([(lm[i] - face.M) @ face.up for i in (40, 41, 46, 47)])
    hn = (lm[33] - face.M) @ face.up
    for nm, d in D.items():
        m = np.linalg.norm(d, axis=1)
        if faceshapes.family(nm) == "mouth":
            assert m[h > hl].max() < 1e-4, (nm, m[h > hl].max())
        elif faceshapes.family(nm) == "eye":
            assert m[h < hn].max() < 1e-4, (nm, m[h < hn].max())
    # A2F's stress combos keep the lips apart and the chin in (rig report 2026-10-02: 29 mm crossing, 17 mm bulge)
    lips_up = [51, 61, 62, 63]
    lips_lo = [57, 65, 66, 67]
    chin = [7, 8, 9]
    for combo in ("CL alone", "warm f31", "PK+CL+JO", "RL+SL", "PK+RL", "JO+RL"):
        w = faceshapes.playback(faceshapes.COMBOS[combo])
        dl = sum(v * face._onto(lm, face._gnm["dW"][k])[0] for k, v in w.items() if k in face._gnm["dW"])
        P = lm + dl
        cross = max(float((P[lo] - P[u]) @ face.up) for u, lo in zip(lips_up, lips_lo))
        assert cross < 0.0015, (combo, cross)
        no_jaw = dl - w.get("jawOpen", 0) * face._onto(lm, face._gnm["dW"]["jawOpen"])[0]
        assert max(float(no_jaw[i] @ face.out) for i in chin) < 0.004, (combo, no_jaw[chin])
    on, _ = face._onto(lm, face._gnm["dW"]["jawOpen"])
    assert on[8] @ face.up < -0.02 and abs(on[27] @ face.up) < 0.002  # the chin drops, the nose bridge stays
    # left is the head's own left (+X), and the right shape mirrors it
    sl, _ = face._onto(lm, face._gnm["dW"]["mouthSmileLeft"])
    sr, _ = face._onto(lm, face._gnm["dW"]["mouthSmileRight"])
    assert sl[54] @ face.up > 0.003 and sl[54] @ face.up > 2 * (sl[48] @ face.up)
    assert np.allclose(sl[54] * [-1, 1, 1], sr[48], atol=5e-4), (sl[54], sr[48])
    # a blink never sinks the skin into the eyeball: no deeper than its clearance, or than the neutral already sits
    # (the neutral lower lids are a hair inside it; pushing them out to the clearance was round 2's under-eye leak)
    for s in ("Left", "Right"):
        ev = face.eyes[s]
        X = V + D[f"eyeBlink{s}"]
        r0 = np.linalg.norm(V - ev["c"], axis=1)
        near = r0 < 1.6 * ev["r"]
        floor = np.minimum(ev["r"] + 0.0005, r0[near]) - 1e-6
        assert (np.linalg.norm(X[near] - ev["c"], axis=1) >= floor).all()
    # far from the face (the back of the head, the neck) nothing moves (brows do pull the forehead a little)
    eyes = 0.5 * (face.eyes["Left"]["c"] + face.eyes["Right"]["c"])
    far = (np.linalg.norm(V - face.M, axis=1) > 0.16) & (np.linalg.norm(V - eyes, axis=1) > 0.12)
    assert far.sum() > 100 and max(np.abs(d[far]).max() for d in D.values()) < 2e-4
    # the tongue rides the jaw and comes out past the lips
    tp = [p for p in compile_prims(spec) if p.name == "face_tongue"][0]
    tv = tp.params["c"] + np.array([[0, 0, 0], [0, -tp.params["size"][1], 0]])
    Dt = face.displacements(tv, tv, np.zeros_like(tv), "tongue", ["jawOpen", "tongueOut"])
    assert Dt["jawOpen"][0] @ face.up < -0.005
    assert (tv[1] + Dt["tongueOut"][1]) @ face.out > face.M @ face.out


if __name__ == "__main__":
    for k, f in list(globals().items()):
        if k.startswith("test_"):
            f()
            print("ok", k)
