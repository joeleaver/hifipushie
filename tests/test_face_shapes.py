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
    assert len(names) == 54 and names[-2:] == ["jawOpen_mouthClose", "jawOpen_mouthSmile"]  # all 52 ARKit names + the correctives
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
        assert nm.startswith("eyeLook") or nm == "jawOpen_mouthSmile" or np.abs(d).max() > 1e-4, f"{nm} moves nothing"  # (jawOpen_mouthSmile: the GNM path only)
    _no_shared_offset(S)
    # mouthClose alone barely moves (A2F drives it with the jaw shut); the corrective does the closing
    assert np.linalg.norm(S["mouthClose"][0], axis=1).max() < 0.2 * np.linalg.norm(S["jawOpen_mouthClose"][0], axis=1).max()
    # the neutral closed the slit: lip vertices moved toward the parting line (half the slit, then the seal: what
    # was left open, at most a lip radius each), nothing else
    moved = np.linalg.norm(body["verts"] - before["body"], axis=1)
    assert 0.3 * face.slit < moved.max() <= 0.51 * face.slit + face.lip + 1e-6, moved.max()
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


# ---- seeing the mouth from the front (numpy rays: the closed neutral, teeth, combos) ----------------------------

def _front_hits(geo: dict, face, xs, zs, yaw: float = 0.0):
    """Rays into the face from in front of the mouth (screen x across, z up; yaw deg turns the view about the up
    axis): per (z, x) the first hit's part ('' = none) and its triangle index in that part."""
    a = np.radians(yaw)
    d = np.cos(a) * -face.out + np.sin(a) * face.side
    sx = np.cross(d, face.up)
    P, names, tid = [], [], []
    for pn, (V, T) in geo.items():
        keep = np.flatnonzero(np.linalg.norm(V[T].mean(1) - face.M, axis=1) < 2 * face.width)
        P.append(V[T[keep]] - face.M)
        names += [pn] * len(keep)
        tid.append(keep)
    P = np.concatenate(P)
    P = np.stack([P @ sx, P @ face.up, P @ d], -1)
    names, tid = np.array(names), np.concatenate(tid)
    # only triangles over the ray grid (the goblin's body has ~240k near the mouth: rays x all of them ran out of memory)
    lo, hi = P[..., :2].min(1), P[..., :2].max(1)
    over = (hi[:, 0] >= xs.min()) & (lo[:, 0] <= xs.max()) & (hi[:, 1] >= zs.min()) & (lo[:, 1] <= zs.max())
    P, names, tid = P[over], np.r_[names[over], [""]], np.r_[tid[over], [-1]]
    best = np.full((len(zs), len(xs)), len(P))
    order = np.argsort(lo[over][:, 1])  # one row of rays at a time, against the triangles spanning its height
    los, his = lo[over][order, 1], hi[over][order, 1]
    px = xs[:, None]
    for r, z in enumerate(zs):
        cand = order[:np.searchsorted(los, z, "right")]
        cand = cand[his[:np.searchsorted(los, z, "right")] >= z]
        if not len(cand):
            continue
        Q = P[cand]

        def cr(p, q, z=z):
            return (q[None, :, 0] - p[None, :, 0]) * (z - p[None, :, 1]) - (q[None, :, 1] - p[None, :, 1]) * (px - p[None, :, 0])
        w0, w1, w2 = cr(Q[:, 1], Q[:, 2]), cr(Q[:, 2], Q[:, 0]), cr(Q[:, 0], Q[:, 1])
        inside = ((w0 >= 0) & (w1 >= 0) & (w2 >= 0)) | ((w0 <= 0) & (w1 <= 0) & (w2 <= 0))
        area = w0 + w1 + w2
        area = np.where(np.abs(area) < 1e-18, 1e-18, area)
        dep = np.where(inside, (w0 * Q[None, :, 0, 2] + w1 * Q[None, :, 1, 2] + w2 * Q[None, :, 2, 2]) / area, np.inf)
        j = dep.argmin(1)
        best[r] = np.where(np.isfinite(dep[np.arange(len(j)), j]), cand[j], len(P))
    return names[best], tid[best]


def _posed(parts: dict, weights: dict) -> dict:
    out = {}
    w = faceshapes.playback(weights)
    for pn, p in parts.items():
        V = np.asarray(p["verts"], float).copy()
        for k, a in w.items():
            if a and k in (p.get("shapes") or {}):
                V = V + a * p["shapes"][k][0]
        out[pn] = (V, p["corner_vert"].reshape(-1, 3))
    return out


def _interior_shown(geo: dict, face, inner, yaw: float = 0.0, dz: float = 5e-5) -> np.ndarray:
    """Per column across the mouth (to its corners), how much of the mouth's inside shows from the front (m): rays
    near the parting line that hit the teeth, tongue, nothing, or skin that was inside the mouth as meshed (`inner`:
    per body triangle, the slit's walls and the bag)."""
    # (turned, the mouth spans less of the screen: past it the rays miss the head's edge)
    xs = np.linspace(-face.W2, face.W2, 121) * (1.0 if not yaw else 0.92 * np.cos(np.radians(yaw)))
    zs = np.arange(-2 * face.lip, 2 * face.lip, dz)
    zl = np.interp(np.abs(xs) / face.W2, face.su, face.sz)
    who, tri = _front_hits(geo, face, xs, zs + 0.0, yaw)
    near = np.abs(zs[:, None] - zl[None]) < 2 * face.lip
    bad = (who != "body") | inner[np.where(who == "body", tri, 0)]
    return (bad & near).sum(0) * dz


def _inner(face, Xm, T) -> np.ndarray:
    L = face.local(Xm)
    return (L["back"][T].mean(1) > 0.5 * face.thick) & (L["u"][T].max(1) < 1.0)  # (past the corners: the cheek)


def test_neutral_sealed():
    """The neutral's lips meet along the whole line, corners too: from the front and from either side no inside of
    the mouth shows (<= 0.3 mm per column; Garrett's neutral showed a ~1 mm slit and 5-7 mm open corners), and the
    seal measured again on the result finds nothing left to close."""
    parts = {pn: dict(p) for pn, p in _parts().items()}
    Xm, T = parts["body"]["verts"].copy(), parts["body"]["corner_vert"].reshape(-1, 3)
    faceshapes.apply(_spec(), parts, ["jawOpen", "mouthClose"], [])
    face = faceshapes.Face(_spec())
    inner = _inner(face, Xm, T)
    for yaw in (0.0, -30.0, 30.0):
        shown = _interior_shown(_posed(parts, {}), face, inner, yaw)
        assert shown.max() <= 0.0003, (yaw, shown.max(), np.flatnonzero(shown > 0.0003))
    # the open mouth still opens onto the inside
    assert _interior_shown(_posed(parts, {"jawOpen": 0.5}), face, inner).max() > 0.5 * face.lip
    # along the slit (to its end, 0.92 of the half width; past it the lips are one surface)
    face.seal(Xm, parts["body"]["verts"], T)
    mids, r = face.sealed
    assert r[np.abs(mids) <= 0.92].max() <= 0.0003, r.max()


def test_closed_combos_stay_closed():
    """A2F's sealed-lip stress combos (and mouthClose alone) keep the sealed neutral sealed and don't push one lip
    through the other: the upper lip's skin is never seen below the lower lip's from the front."""
    parts = {pn: dict(p) for pn, p in _parts().items()}
    Xm, T = parts["body"]["verts"].copy(), parts["body"]["corner_vert"].reshape(-1, 3)
    faceshapes.apply(_spec(), parts, True, [])
    face = faceshapes.Face(_spec())
    inner = _inner(face, Xm, T)
    up = face.local(Xm)["h0"][T].mean(1) >= 0
    xs = np.linspace(-0.9 * face.W2, 0.9 * face.W2, 61)
    zs = np.arange(-2 * face.lip, 2 * face.lip, 5e-5)
    for combo in ("CL alone", "MBP", "PK+RL", "RL+SL", "PK+CL+JO", "warm f31", "open+close"):
        geo = _posed(parts, faceshapes.COMBOS[combo])
        shown = _interior_shown(geo, face, inner)
        # (warm f31, A2F's worst frame on the GNM human, is a full pucker and roll with mouthClose 1.0 over jawOpen
        # 0.58: its pursed middle may part a hair; open+close, the jaw at 1.0 (past A2F's ~0.6) closed by the
        # corrective, a column 2.1 mm)
        assert shown.max() <= (0.0025 if combo in ("warm f31", "open+close") else 0.001), (combo, shown.max())
        who, tri = _front_hits(geo, face, xs, zs)
        skin = (who == "body") & ~inner[np.where(who == "body", tri, 0)]  # (the lips' outsides: not the bag seen through)
        su, sl = skin & up[np.where(skin, tri, 0)], skin & ~up[np.where(skin, tri, 0)]
        z = zs[:, None] * np.ones((1, len(xs)))
        flip = np.max(np.where(sl, z, -1), 0) - np.min(np.where(su, z, 1), 0)
        # the closing combos: none. The rolls/shrugs/puckers press the lower lip up against the upper and with the
        # lips sealed it shows in front of it by a few mm (goblin 2026-10-03: PK+RL 2.7, RL+SL 3.9, PK+CL+JO 5.0, and
        # warm f31, mouthClose 1.0 + pucker 1.0 + roll 1.0 over jawOpen 0.58, 13.1; the slit-open neutral 0-10.5)
        bound = 0.0005 if combo in ("CL alone", "MBP", "open+close") else 2 * face.lip if combo == "warm f31" else face.lip
        assert flip.max() <= bound, (combo, flip.max())


def test_upper_teeth_show():
    """An open mouth (jawOpen 0.3-0.6, as far as A2F's curves go) shows the upper teeth below the upper lip, not
    just the lower row (the upper row's edge was level with the lip: buried)."""
    parts = {pn: dict(p) for pn, p in _parts().items()}
    faceshapes.apply(_spec(), parts, ["jawOpen"], [])
    face = faceshapes.Face(_spec())
    Tt = parts["teeth"]["corner_vert"].reshape(-1, 3)
    upper = (np.abs(parts["teeth"]["shapes"]["jawOpen"][0]).max(1) == 0)[Tt].all(1)  # (the row the jaw leaves)
    xs = np.linspace(-0.5 * face.W2, 0.5 * face.W2, 41)
    zs = np.arange(-4 * face.lip, 2 * face.lip, 1e-4)
    for w in (0.3, 0.5):
        who, tri = _front_hits(_posed(parts, {"jawOpen": w}), face, xs, zs)
        rows = (who == "teeth") & upper[np.where(who == "teeth", tri, 0)]
        shown = rows.sum(0) * 1e-4  # per column, how much upper tooth shows
        print("upper teeth shown at jawOpen", w, np.median(shown))
        assert np.median(shown) > 0.3 * face.ru, (w, np.median(shown))
    who, _ = _front_hits(_posed(parts, {}), face, xs, zs)
    assert not (who == "teeth").any()  # closed: none


def test_clothes_take_no_shapes():
    """Only the face's own skin (and parts listed in face_shapes.parts) takes the skin's shapes: a collar under the
    chin stays still (transferred by distance, Garrett's collar followed his jaw 31 mm)."""
    base = _parts()
    body = base["body"]
    face = faceshapes.Face(_spec())
    L = face.local(body["verts"])
    T = body["corner_vert"].reshape(-1, 3)
    chin = (L["h0"][T].mean(1) < -2 * face.lip) & (L["h0"][T].mean(1) > -0.8 * face.R) & (L["u"][T].mean(1) < 1.0)
    used = np.unique(T[chin])
    remap = np.full(len(body["verts"]), -1)
    remap[used] = np.arange(len(used))
    V = body["verts"][used] - face.out * 0.004  # a collar 4 mm in front of the chin
    cv = remap[T[chin]].ravel()
    n = faceshapes.vertex_normals(V, cv.reshape(-1, 3))[cv].astype(np.float32)
    collar = {"verts": V, "corner_vert": cv, "normal": n, "tangent": n.copy(), "uv": np.zeros((len(cv), 2), np.float32),
              "sign": np.ones(len(cv), np.float32), "atlas": 0}
    for opt_in in (False, True):
        spec = _spec()
        if opt_in:
            spec["face_shapes"] = {"parts": ["collar"]}
        parts = {pn: dict(p) for pn, p in base.items()} | {"collar": dict(collar)}
        got = faceshapes.apply(spec, parts, ["jawOpen", "mouthSmileLeft", "tongueOut"], [])
        if not opt_in:
            assert "collar" not in got and not parts["collar"].get("shapes")
            assert np.array_equal(parts["collar"]["verts"], V)
            assert "body" in got
        else:
            assert "collar" in got and np.abs(parts["collar"]["shapes"]["jawOpen"][0]).max() > 1e-3


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



def _lid_line(face, V, d, s, nb=10):
    """A blink's lid line on a mesh: (gap per bin across the middle 84% of the eye, m: the upper margin's lowest
    vertex minus the lower margin's highest, + = an open slit; the lower margin's roughness against a parabola)."""
    lm = np.asarray(face.head["lm68"], float)
    ev = face.eyes[s]
    c, r = np.asarray(ev["c"], float), float(ev["r"])
    ci, co = faceshapes._mirror_ids([42, 45], s)
    pairs = list(zip(faceshapes._mirror_ids([43, 44], s), faceshapes._mirror_ids([47, 46], s)))
    side = lm[co] - lm[ci]
    width = float(np.linalg.norm(side))
    side = side / width
    up = face.up - side * (face.up @ side)
    up /= np.linalg.norm(up)
    out = np.cross(side, up)
    out = out if out @ face.out > 0 else -out
    mid = 0.5 * (lm[ci] + lm[co])
    u, h0, f0 = (V - mid) @ side, (V - mid) @ up, (V - c) @ out
    ku = [-0.5 * width] + [float((0.5 * (lm[a] + lm[b]) - mid) @ side) for a, b in pairs] + [0.5 * width]
    kh = [0.0] + [float((0.5 * (lm[a] + lm[b]) - mid) @ up) for a, b in pairs] + [0.0]
    o = np.argsort(ku)
    upper = h0 > np.interp(u, np.array(ku)[o], np.array(kh)[o])
    rad = np.linalg.norm(V - c, axis=1)
    zone = (np.abs(u) < 0.42 * width) & (rad < 1.9 * r) & (f0 > 0.3 * r) & (rad > r + 2e-4)
    hp = h0 + d @ up
    edges = np.linspace(-0.42 * width, 0.42 * width, nb + 1)
    bi = np.clip(np.searchsorted(edges, u) - 1, 0, nb - 1)
    lo_u, hi_l = np.full(nb, np.nan), np.full(nb, np.nan)
    for k in range(nb):
        a, b = zone & upper & (bi == k), zone & ~upper & (bi == k)
        if a.any() and b.any():
            lo_u[k], hi_l[k] = hp[a].min(), hp[b].max()
    ok = np.isfinite(lo_u)
    bc = 0.5 * (edges[1:] + edges[:-1])
    rough = float(np.std(hi_l[ok] - np.polyval(np.polyfit(bc[ok], hi_l[ok], 2), bc[ok])))
    return (lo_u - hi_l)[ok], rough


def test_blink_lids_meet():
    """2026-10-05: a blink's lids must meet on one smooth line on a LOW POLY (GnmFace._lid_seal). Unsealed, each
    margin vertex lands at its own height (the lids overlap by up to 5 mm in one place and gape in the next: a ragged
    line with dark slots). The first seal then parked the margins ~0.5 mm either side of the line it had drawn: a
    1.2 mm slit along the whole eye (gap +0.4 .. +1.5 mm), which is what still showed. Measured on the head mesh and
    on it decimated to a third, the density of a 40k export's face. Slow (the head is built); skipped without GNM."""
    got = _gnm()
    if got is None:
        print("skip: no GNM asset pack ($HIFIPUSHIE_ASSETS)")
        return
    import pyfqmr
    spec, face = got
    h = face.head
    V = np.asarray(h["verts"], float)
    T = np.array([(f[0], f[j], f[j + 1]) for f in h["faces"] for j in range(1, len(f) - 1)])
    sp = pyfqmr.Simplify()
    sp.setMesh(V, T)
    sp.simplify_mesh(target_count=int(len(T) * 0.3), aggressiveness=5, preserve_border=True, verbose=False)
    v2, f2, _ = sp.getMesh()
    names = ["eyeBlinkLeft", "eyeBlinkRight"]
    keep = faceshapes.LID_SEAL
    try:
        for X, F in ((V, T), (np.asarray(v2, float), np.asarray(f2))):
            n0 = faceshapes.vertex_normals(X, F)
            faceshapes.LID_SEAL = False
            raw = face.displacements(X, X, n0, "skin", names)
            faceshapes.LID_SEAL = True
            D = face.displacements(X, X, n0, "skin", names)
            for s in ("Left", "Right"):
                g0, r0 = _lid_line(face, X, raw[f"eyeBlink{s}"], s)
                g1, r1 = _lid_line(face, X, D[f"eyeBlink{s}"], s)
                assert len(g1) >= 8, (s, len(g1))
                assert g1.max() < 0.0006, (s, "an open slit between the lids", g1.max())
                # the upper lid is MEANT to pass the lower lid's line by LID_OVER (a seal, no slit), and by LID_SAG
                # more mid-eye (the closed lid's line dips over the globe): more than half a millimetre past that is
                # a fault
                assert g1.min() > -(faceshapes.LID_OVER + faceshapes.LID_SAG + 0.0005), (s, "the lids cross", g1.min())
                assert np.ptp(g1) < 0.4 * np.ptp(g0), (s, "no tidier than unsealed", np.ptp(g1), np.ptp(g0))
                assert r1 < 0.00025 and r1 < r0, (s, "the lid line is ragged", r1, r0)
                # the seal only moves the lids: nothing past the eye's own neighbourhood
                far = np.linalg.norm(X - face.eyes[s]["c"], axis=1) > 2.2 * face.eyes[s]["r"]
                assert np.abs(D[f"eyeBlink{s}"][far] - raw[f"eyeBlink{s}"][far]).max() < 1e-9
    finally:
        faceshapes.LID_SEAL = keep


def test_blink_seal_leaves_the_cheek():
    """2026-10-07 (s0urc3's Garrett, 20k export): the lid seal sheared the skin UNDER each eye into a sawtooth:
    neighbouring cheek vertices 7-22 mm below the eye rose 0.25, -0.13, 2.40, 0.43, ... 5.24 mm. On a coarse low
    poly most of the seal's bins across the eye hold no margin vertex, so a bin's "highest lower-lid vertex" was a
    cheek vertex, lifted to the lid line; and every vertex's share was its blink travel over its margin's (~1 mm
    on a lower lid: noise). Now margins are found by their lid's edge and the share falls off with distance from
    the margin. On the head mesh decimated to a game face's density: nothing under the lower lid's reach moves,
    and the sealed blink is no more uneven (`faceshapes.unevenness`) than the unsealed one. Also the spec switch."""
    got = _gnm()
    if got is None:
        print("skip: no GNM asset pack ($HIFIPUSHIE_ASSETS)")
        return
    import pyfqmr
    spec, face = got
    h = face.head
    V = np.asarray(h["verts"], float)
    T = np.array([(f[0], f[j], f[j + 1]) for f in h["faces"] for j in range(1, len(f) - 1)])
    names = ["eyeBlinkLeft", "eyeBlinkRight"]
    keep, opts = faceshapes.LID_SEAL, face.lid_seal
    try:
        for share in (0.3, 0.1, 0.05):
            sp = pyfqmr.Simplify()
            sp.setMesh(V, T)
            sp.simplify_mesh(target_count=int(len(T) * share), aggressiveness=5, preserve_border=True, verbose=False)
            v2, f2, _ = sp.getMesh()
            X, F = np.asarray(v2, float), np.asarray(f2)
            n0 = faceshapes.vertex_normals(X, F)
            faceshapes.LID_SEAL = False
            raw = face.displacements(X, X, n0, "skin", names)
            faceshapes.LID_SEAL = True
            D = face.displacements(X, X, n0, "skin", names)
            first, Fw, _ = faceshapes.weld(X, F)
            for s in ("Left", "Right"):
                nm = f"eyeBlink{s}"
                ev = face.eyes[s]
                # (12 mm under the eye's centre on the 24.4 mm ball this stylised head had; with GNM's own ball, 4 %
                # larger and not seated back, the lower lid's margin lies that much lower: half a radius)
                below = (X - ev["c"]) @ face.up < -max(0.012, 0.5 * ev["r"])
                ch = np.linalg.norm(D[nm] - raw[nm], axis=1)
                assert ch.max() > 2e-4, (share, s, "the seal did nothing")
                assert ch[below].max() < 1e-4, (share, s, "the seal moved the cheek", ch[below].max())
                # (at the margins themselves the seal is steep on purpose: the band drawn onto the line; s0urc3's
                # region is the skin from 6.5 mm under the eye's centre)
                under = (((X - ev["c"]) @ face.up < -0.0065) & (np.linalg.norm(X - ev["c"], axis=1) < 0.045))[first]
                u0 = faceshapes.unevenness(X[first], Fw, raw[nm][first], under)
                u1 = faceshapes.unevenness(X[first], Fw, D[nm][first], under)
                assert u1[0] < max(u0[0] + 0.06, 0.12), (share, s, "the sealed blink is jagged under the eye", u1, u0)
                if share < 0.3:  # (a game face's density: the whole shape under the export log's limit)
                    off = face.off_margins(nm, X[first])
                    assert faceshapes.unevenness(X[first], Fw, D[nm][first], off)[0] < 0.75 * faceshapes.UNEVEN_LIMIT, (share, s)
        # a spike reads as one: one vertex moved 3 mm alone
        d = np.zeros_like(X)
        d[np.argmin(np.linalg.norm(X - face.eyes["Left"]["c"] + 0.02 * face.up, axis=1))] = 0.003 * face.up
        assert faceshapes.unevenness(X[first], Fw, d[first])[0] > faceshapes.UNEVEN_LIMIT
        # spec.face_shapes.lid_seal: false = the basis's own blink; a wrong key is refused
        face.lid_seal = faceshapes.lid_seal_options(False)
        off = face.displacements(X, X, n0, "skin", names)
        assert np.abs(off["eyeBlinkLeft"] - raw["eyeBlinkLeft"]).max() < 1e-12
        face.lid_seal = faceshapes.lid_seal_options(0.5)
        half = face.displacements(X, X, n0, "skin", names)
        a = np.linalg.norm(half["eyeBlinkLeft"] - raw["eyeBlinkLeft"], axis=1).max()
        assert 0 < a < np.linalg.norm(D["eyeBlinkLeft"] - raw["eyeBlinkLeft"], axis=1).max()
        try:
            faceshapes.lid_seal_options({"amont": 1})
            raise AssertionError("a misspelt lid_seal key passed")
        except SpecError:
            pass
    finally:
        faceshapes.LID_SEAL, face.lid_seal = keep, opts


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
    # (relative: the smile is GNM's expression prototype split per side on the head's own, slightly asymmetric
    # identity: the corners move ~25 mm and differ by ~5%, which an absolute 0.5 mm can't hold)
    assert np.allclose(sl[54] * [-1, 1, 1], sr[48], rtol=0.08, atol=5e-4), (sl[54], sr[48])
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
    worst = max(((float(np.abs(d[far]).max()), k) for k, d in D.items()))
    assert far.sum() > 100 and worst[0] < 2e-4, worst
    # the tongue rides the jaw and comes out past the lips
    tp = [p for p in compile_prims(spec) if p.name == "face_tongue"][0]
    tv = tp.params["c"] + np.array([[0, 0, 0], [0, -tp.params["size"][1], 0]])
    Dt = face.displacements(tv, tv, np.zeros_like(tv), "tongue", ["jawOpen", "tongueOut"])
    assert Dt["jawOpen"][0] @ face.up < -0.005
    assert (tv[1] + Dt["tongueOut"][1]) @ face.out > face.M @ face.out


def test_jaw_leaves_the_body_under_the_neck():
    """2026-10-12 (headbody; a regression of GNM's own mouth, 75a6a10): away from the face the jaw's rigid move was
    laid on x 1.0 instead of x the jaw weight. Meant for GNM's teeth and tongue, it ran on the SKIN too: every body
    vertex under the neck moved 25.9 mm with jawOpen, and the export's rigid_near (whatever a face shape moves is
    head) then weighted the whole trunk 1.0 to the Head bone: a head turn carried the chest, a neck bend tore it away.
    On a GNM-mouth head: no skin vertex under the neck moves with jawOpen (by index on the one mesh's own quads, and
    by projection as a decimated low poly gets them), and the trunk's Head weight after rigid_near is 0."""
    try:
        from hifipushie import assets
        assets.path("gnm", "gnm/shape/data/versions/v3_0/gnm_head.npz")
    except Exception as err:
        print("skipped:", str(err)[:80])
        return
    from hifipushie import humans, retopo
    from hifipushie import rig as rigmod
    sp = humans.spec(age=40, sex=1.0, seed=3, skin=False, source="human")  # (no interior key: GNM's own mouth)
    sp.setdefault("parts", {}).setdefault("body", {})["topology"] = "wrap"
    r = retopo.wrap(sp, log=[])
    V, L, S, gnm = r["verts"], r["loops"], r["sizes"], np.asarray(r["gnm"])
    st = np.r_[0, np.cumsum(S)[:-1]]
    T = np.array([(L[a], L[a + j], L[a + j + 1]) for a, k in zip(st, S) for j in range(1, k - 1)])
    face = faceshapes.face_of(sp)
    assert face.gnm_mouth
    chin_z = float(face.head["lm68"][8][2])
    trunk = V[:, 2] < chin_z - 0.15
    assert trunk.sum() > 3000 and (gnm[trunk] < 0).all()
    moved = {}
    for how, idx in (("by index", gnm), ("projected", None)):
        Xn = V + face.neutral(V, "skin", idx)
        D = face.displacements(V, Xn, faceshapes.vertex_normals(Xn, T), "skin", ["jawOpen", "tongueOut", "eyeBlinkLeft"],
                               None, idx)
        if idx is not None:  # (2026-10-16, expr_r8..r12: the closed lips showed a flap of inner roll / a dark gap)
            # the lips' seam is closed at neutral and at eyeBlink: nothing inside the contact ring seen from the front
            for nm, X in (("neutral", Xn), ("eyeBlinkLeft", Xn + D["eyeBlinkLeft"])):
                a = face.seam_showing(X, T, idx)
                assert a is not None and a <= faceshapes.SEAM_SHOWING, (nm, a)
        D.pop("eyeBlinkLeft")
        mv = np.max([np.linalg.norm(d, axis=1) for d in D.values()], 0)
        assert mv[~trunk].max() > 0.015, how  # (the jaw does open)
        assert mv[trunk].max() < rigmod.MOVED[0], (how, float(mv[trunk].max()))
        moved[how] = mv
    assert moved["by index"][gnm < 0].max() == 0.0  # (the one mesh: nothing under the seam ring moves at all)
    bones = rigmod.rig_bones(sp)
    names = [b["name"] for b in bones]
    hi, sp2 = names.index(rigmod.PREFIX + "Head"), names.index(rigmod.PREFIX + "Spine2")
    J = np.full((len(V), 4), sp2)
    W = np.tile([1.0, 0.0, 0.0, 0.0], (len(V), 1))
    for how, mv in moved.items():
        Jr, Wr = rigmod.rigid_near(bones, {"body": (J, W)}, {"body": V}, {"body": mv}, band=0.08)["body"]
        head = np.where(np.asarray(Jr) == hi, np.asarray(Wr), 0.0).sum(1)
        assert head[~trunk].max() > 0.99 and head[trunk].max() == 0.0, (how, float(head[trunk].max()))


def _lid_edges(V: dict, centre, half: float):
    """Per eye: the eyeball's visible top / bottom (m, z) seen from the front in its centre columns (+-15% of its
    half width), rays along +Y (the face looks down -Y): the lids' margins as a render sees them."""
    from types import SimpleNamespace
    f = SimpleNamespace(M=np.asarray(centre, float), out=np.array([0.0, -1.0, 0.0]), up=np.array([0.0, 0.0, 1.0]),
                        side=np.array([1.0, 0.0, 0.0]), width=0.03)
    xs = np.linspace(-0.15 * half, 0.15 * half, 7)
    zs = np.arange(-0.010, 0.010, 0.00005)
    hit, _ = _front_hits(V, f, xs, zs)
    top, bot = [], []
    for k in range(len(xs)):
        r = np.flatnonzero(hit[:, k] == "eyes")
        if len(r):
            top.append(zs[r.max()]), bot.append(zs[r.min()])
    return np.mean(top), np.mean(bot)


def test_exported_squint_matches_fit():
    """(r40) The fitted smile's squint survives the export: in the exported GLB (HP_SQUINT_GLB), mouthSmile + cheekSquint
    at 1 move each lid's visible margin (front rays at the eye's centre columns, against the GLB's own eyeballs) as far
    as the FITTED GNM head (HP_SQUINT_SPEC: the head model's spec.json, e.g. tp_k19's, posed read-only with the fit's coefficients, the eye
    components x SMILE_FIT_EYE_GAIN) moves it, within 0.25 mm. Skipped without HP_SQUINT_GLB / HP_SQUINT_SPEC / HP_SMILE_FIT."""
    glb = os.environ.get("HP_SQUINT_GLB")
    if not glb or not faceshapes.SMILE_FIT or not os.environ.get("HP_SQUINT_SPEC"):
        print("skip: HP_SQUINT_GLB / HP_SQUINT_SPEC / HP_SMILE_FIT not set")
        return
    import copy
    from hifipushie import base, humanfit, likeness, rig_audit
    g = rig_audit.read_glb(glb)["meshes"]
    W = {"mouthSmileLeft": 1.0, "mouthSmileRight": 1.0, "cheekSquintLeft": 1.0, "cheekSquintRight": 1.0}

    def posed(m, w):
        V = np.asarray(m["V"], float).copy()
        for k, a in w.items():
            if k in m.get("targets", {}):
                V = V + a * np.asarray(m["targets"][k], float)
        return V
    names = [str(n) for n in base._gnm_data()["expression_names"]]
    e = np.asarray(np.load(faceshapes.SMILE_FIT), float).copy()
    for i, n in enumerate(names[:len(e)]):
        if n.startswith(("left_eye", "right_eye")):
            e[i] *= faceshapes.SMILE_FIT_EYE_GAIN
    spec = json.loads(Path(os.environ["HP_SQUINT_SPEC"]).read_text())  # (this module points HIFIPUSHIE_HOME at a temp dir)

    def gnm(ev):
        s = copy.deepcopy(spec)
        if ev is not None:
            s["base"]["head"]["expression"] = {n: float(x) for n, x in zip(names, ev) if abs(x) > 1e-5}
        m = likeness.model_mesh_from_state(humanfit.state(s["base"]))
        F = np.asarray(m["F"])
        if F.shape[1] == 4:
            F = np.concatenate([F[:, [0, 1, 2]], F[:, [0, 2, 3]]])
        return np.asarray(m["V"], float), F
    G0, GF = gnm(None)
    G1, _ = gnm(e)
    E0 = posed(g["eyes"], {})
    for side, sel in (("L", E0[:, 0] > 0), ("R", E0[:, 0] < 0)):
        c = E0[sel].mean(0)
        half = 0.5 * np.ptp(E0[sel][:, 0])
        Eg = (np.asarray(g["eyes"]["V"], float), np.asarray(g["eyes"]["F"]))
        moved = {}
        for lab, n, s_ in (("export", {"head": (posed(g["head"], {}), np.asarray(g["head"]["F"])), "eyes": Eg},
                                       {"head": (posed(g["head"], W), np.asarray(g["head"]["F"])),
                                        "eyes": (posed(g["eyes"], W), Eg[1])}),
                           ("fit", {"head": (G0, GF), "eyes": Eg}, {"head": (G1, GF), "eyes": Eg})):
            t0, b0 = _lid_edges(n, c, half)
            t1, b1 = _lid_edges(s_, c, half)
            moved[lab] = (t1 - t0, b1 - b0, t0 - b0)
        ex, fi = moved["export"], moved["fit"]
        print(f"eye{side}: upper {1e3 * ex[0]:+.2f} (fit {1e3 * fi[0]:+.2f}) lower {1e3 * ex[1]:+.2f} (fit {1e3 * fi[1]:+.2f}) mm,"
              f" neutral opening {1e3 * ex[2]:.2f} (fit head {1e3 * fi[2]:.2f}) mm")
        # (r43) the export's lower lid travels SMILE_LOWLID_GAIN x the fit's at the lid's centre (a hand pass on the solve)
        lo = fi[1] * float(os.environ.get("HP_SMILE_LOWLID_GAIN", faceshapes.SMILE_LOWLID_GAIN))
        assert abs(ex[0] - fi[0]) < 0.00025 and abs(ex[1] - lo) < 0.00025, (side, ex, fi, lo)



def _lid_profile(V: dict, centre, half: float, n: int = 9):
    """The eyeball's visible top / bottom (m, z) seen from the front at n columns across the eye (15% .. 85% of its
    width): the lids' margins along the whole eye, as a render sees them (nan where no eye shows)."""
    from types import SimpleNamespace
    f = SimpleNamespace(M=np.asarray(centre, float), out=np.array([0.0, -1.0, 0.0]), up=np.array([0.0, 0.0, 1.0]),
                        side=np.array([1.0, 0.0, 0.0]), width=0.03)
    xs = np.linspace(-0.7 * half, 0.7 * half, n)
    zs = np.arange(-0.010, 0.010, 0.00005)
    hit, _ = _front_hits(V, f, xs, zs)
    top, bot = np.full(n, np.nan), np.full(n, np.nan)
    for k in range(n):
        r = np.flatnonzero(hit[:, k] == "eyes")
        if len(r):
            top[k], bot[k] = zs[r.max()], zs[r.min()]
    return top, bot


def test_exported_neutral_eye_opening_matches_source():
    """(r41) The exported head's NEUTRAL lid margins are the approved source head's: in the GLB (HP_SQUINT_GLB), each lid's
    visible margin at 9 columns across each eye (front rays against the GLB's own eyeballs) lies within 0.2 mm of the
    source GNM head's (HP_SQUINT_SPEC, e.g. tp_k19's spec.json, read-only), and the opening at the centre within 0.2 mm.
    Before retopo.LID_KEEP the drop onto the smoothed field moved the lids' skin up to 1 mm: 9.9 against 8.6 mm."""
    glb = os.environ.get("HP_SQUINT_GLB")
    if not glb or not os.environ.get("HP_SQUINT_SPEC"):
        print("skip: HP_SQUINT_GLB / HP_SQUINT_SPEC not set")
        return
    from hifipushie import humanfit, likeness, rig_audit
    g = rig_audit.read_glb(glb)["meshes"]
    spec = json.loads(Path(os.environ["HP_SQUINT_SPEC"]).read_text())
    m = likeness.model_mesh_from_state(humanfit.state(spec["base"]))
    F = np.asarray(m["F"])
    if F.shape[1] == 4:
        F = np.concatenate([F[:, [0, 1, 2]], F[:, [0, 2, 3]]])
    E = np.asarray(g["eyes"]["V"], float)
    Eg = (E, np.asarray(g["eyes"]["F"]))
    for side, sel in (("L", E[:, 0] > 0), ("R", E[:, 0] < 0)):
        c = E[sel].mean(0)
        half = 0.5 * np.ptp(E[sel][:, 0])
        ex = _lid_profile({"head": (np.asarray(g["head"]["V"], float), np.asarray(g["head"]["F"])), "eyes": Eg}, c, half)
        so = _lid_profile({"head": (np.asarray(m["V"], float), F), "eyes": Eg}, c, half)
        dt, db = 1e3 * (ex[0] - so[0]), 1e3 * (ex[1] - so[1])
        mid = len(dt) // 2
        op_e, op_s = 1e3 * (ex[0][mid] - ex[1][mid]), 1e3 * (so[0][mid] - so[1][mid])
        print(f"eye{side}: neutral opening export {op_e:.2f} source {op_s:.2f} mm; upper margin export - source "
              f"{np.round(dt, 2)}, lower {np.round(db, 2)} mm")
        ok = ~np.isnan(dt) & ~np.isnan(db)
        assert ok.sum() >= len(dt) - 2, (side, dt, db)
        assert np.abs(dt[ok]).max() < 0.2 and np.abs(db[ok]).max() < 0.2 and abs(op_e - op_s) < 0.2, (side, dt, db)


_FACE_REGIONS = ("upper_lip", "lower_lip", "upper_lip_region", "lower_lip_region", "nose_region", "chin_region",
                 "middle_brow_region", "left_brow_region", "left_orbital_region", "right_orbital_region")


def _face_items(X, grp):
    """Feature items on GNM-indexed vertices (mm): mouth width / corners, vermilion height and front per column,
    nose tip / width, philtrum depth, brow front (grp(name): the cage's exterior vertices of that GNM group)."""
    o = {}
    U, L = grp("upper_lip"), grp("lower_lip")
    lips = U | L
    xs = X[lips, 0]
    w, cx = np.ptp(xs), 0.5 * (xs.max() + xs.min())
    o["mouth width"] = w
    o["corner L z"] = X[lips & (X[:, 0] > cx + 0.45 * w), 2].mean()
    o["corner R z"] = X[lips & (X[:, 0] < cx - 0.45 * w), 2].mean()
    for c in (-0.3, -0.15, 0.0, 0.15, 0.3):
        band = np.abs(X[:, 0] - (cx + c * w)) < 0.0025
        for nm, sel in (("upper", U & band), ("lower", L & band)):
            o[f"{nm} vermilion height @{c:+.2f}"] = np.ptp(X[sel, 2])
            o[f"{nm} lip front @{c:+.2f}"] = X[sel, 1].min()
    nz = grp("nose_region")
    tip = np.argmin(np.where(nz, X[:, 1], 9))
    o["nose tip y"], o["nose tip z"] = X[tip, 1], X[tip, 2]
    o["nose width"] = np.ptp(X[nz & (np.abs(X[:, 2] - (X[tip, 2] - 0.008)) < 0.004), 0])
    ph = grp("upper_lip_region") & ~U
    mid = ph & (np.abs(X[:, 0] - cx) < 0.0015)
    zc = X[mid, 2].mean()
    mid &= np.abs(X[:, 2] - zc) < 0.004
    rid = ph & (np.abs(np.abs(X[:, 0] - cx) - 0.0045) < 0.0015) & (np.abs(X[:, 2] - zc) < 0.004)
    o["philtrum depth"] = X[mid, 1].mean() - X[rid, 1].mean()
    for r in ("middle_brow_region", "left_brow_region", "right_brow_region"):
        o[f"{r} front"] = X[grp(r), 1].mean()
    return {k: 1e3 * v for k, v in o.items()}


def test_face_keep_regions_match_source():
    """(r42) The export's head surface IS the approved GNM head on the whole face, not just at the lids: retopo.base_quads
    dropped the cage onto the SMOOTHED body field, which moved the lips' skin 1.2 mm on average (max 6.6), the lower
    vermilion 3.5 mm shorter, the nose tip 0.34 mm back ("neutral lips thin"). With retopo.FACE_KEEP every feature item
    (lips per column, corners, nose, philtrum, brows) and every region's vertices stay within 0.1 mm of the cage.
    Model: HP_FACE_KEEP_SPEC (a one-mesh GNM model's spec.json, e.g. ga_tess_v54's; read-only)."""
    m = os.environ.get("HP_FACE_KEEP_SPEC")
    if not m:
        print("skip: HP_FACE_KEEP_SPEC not set")
        return
    from hifipushie import base as basemod, onemesh, gnmloops, retopo
    from hifipushie.spec import expand_mirror
    spec = json.loads(Path(m).read_text())
    log = []
    r = retopo.base_quads(spec, log)
    sf = basemod.surface(expand_mirror(spec), spec["base"])
    Vq = np.asarray(sf["quads"][0], float)
    tpl = basemod.source(spec["base"])
    gnm = np.asarray(onemesh.asset()["gnm_exact"], int)[np.asarray(tpl["fid"])]
    rid = np.maximum(gnmloops.raw_id(gnm), 0)
    g = basemod._gnm_data()
    ext = (gnm >= 0) & (np.asarray(g["groups"]["skin_exterior"]) > 0.5)[rid]
    V = np.asarray(r["verts"], float)[:len(Vq)]

    def grp(k):
        return ext & (np.asarray(g["groups"][k]) > 0.5)[rid]
    for k in _FACE_REGIONS:
        d = 1e3 * np.linalg.norm(V[grp(k)] - Vq[grp(k)], axis=1)
        print(f"{k:22s} |d| mean {d.mean():.3f} max {d.max():.3f} mm")
        assert d.max() < 0.1, (k, d.max())
    a, b = _face_items(Vq, grp), _face_items(V, grp)
    for k in a:
        print(f"{k:32s} source {a[k]:9.2f} export {b[k] - a[k]:+.3f} mm")
        assert abs(b[k] - a[k]) < 0.1, (k, a[k], b[k])


if __name__ == "__main__":
    for k, f in list(globals().items()):
        if k.startswith("test_"):
            f()
            print("ok", k)
