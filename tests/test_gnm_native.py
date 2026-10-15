"""GNM-native heads (gnmnative, 2026-10-12): GNM's OWN eyeball (its two-sphere eye at its joint; limbus / cornea
from the identity's eyes_* components, the pupil from the expression's pupils_000) and GNM's OWN mouth (teeth and
gums, tongue, mouth bag; one evaluation of GNM's bases for every component), the override that keeps old models
(base.head.eye_radius, base.head.interior), the fallback (a style that pushed the lips), and the face shapes on it.

Run: uv run pytest tests/test_gnm_native.py   (needs the GNM asset pack; ~2 min: one MakeHuman body is built)."""
from __future__ import annotations

import copy
import os
import tempfile
from pathlib import Path

import numpy as np
import pytest

_TMP = tempfile.mkdtemp(prefix="hp-gnmnative-")
os.environ.setdefault("HIFIPUSHIE_HOME", _TMP)

from hifipushie import assets, base, faceshapes, humans, lidrings, onemesh, sdf  # noqa: E402
from hifipushie import spec as specmod  # noqa: E402
from hifipushie.spec import empty_spec  # noqa: E402


def _have_gnm() -> bool:
    try:
        assets.path("gnm", base.GNM)
        return True
    except Exception:  # noqa: BLE001
        return False


pytestmark = pytest.mark.skipif(not _have_gnm(), reason="no GNM asset pack ($HIFIPUSHIE_ASSETS)")
_C: dict = {}


def _spec(**head) -> dict:
    """A one-mesh man of 30 (clay: no skin), GNM's mean identity unless the head says otherwise."""
    key = repr(sorted(head.items()))
    if key not in _C:
        sp = {**empty_spec(), **humans.spec(age=30, sex=1.0, source="human", skin=False, outfit_kind="none")}
        sp["base"]["head"].update(head)
        sp["base"]["head"].pop("lip_seal", None)
        sp["base"]["head"].setdefault("lip_close", True)
        _C[key] = sp
    return copy.deepcopy(_C[key])


def _head(sp):
    return onemesh.head_rest(sp["base"])


# ---- GNM's eye as data -------------------------------------------------------------------------------------------

def test_gnm_eye_is_two_spheres_and_the_components_move_it():
    g = base._gnm_data()
    T = g["template_vertex_positions"].astype(float)
    J = g["template_joint_positions"].astype(float)
    inm = [str(n) for n in g["identity_names"]]
    enm = [str(n) for n in g["expression_names"]]
    e = base.gnm_eyes(T, g)
    for q, j in zip(e, (2, 3)):
        assert np.linalg.norm(q["c"] - J[j]) < 2e-5                 # the scleral sphere sits on GNM's eye joint
        assert 0.01450 < q["r"] < 0.01465                           # the paper's ~14.6 mm, held
        assert 0.0058 < q["limbus"] < 0.0063                        # N(6.0, 0.44) mm
        assert 0.0070 < q["cornea_r"] < 0.0090 and q["apex"] > q["r"] + 0.0012
        assert abs(q["pupil"] - 0.5) < 0.02 and q["axis"][2] > 0.999
    # eyes_000 = the limbus; the ball's radius stays (eyelid compatibility)
    B = g["vertex_identity_basis"][inm.index("eyes_000")]
    lo, hi = base.gnm_eyes(T - 2 * B, g)[0], base.gnm_eyes(T + 2 * B, g)[0]
    assert hi["limbus"] - lo["limbus"] > 0.0012 and abs(hi["r"] - lo["r"]) < 0.00015
    # pupils_000 = dilation, nothing else
    P = g["expression_basis"][enm.index("pupils_000")]
    small, big = base.gnm_eyes(T - P, g)[0], base.gnm_eyes(T + P, g)[0]
    assert small["pupil"] < 0.36 < 0.62 < big["pupil"] and abs(big["limbus"] - small["limbus"]) < 2e-5
    # a head component only carries the ball (with its joint): same radius, same limbus
    c = np.zeros(len(inm))
    c[:170] = np.random.default_rng(3).normal(size=170)
    V = T + np.tensordot(c, g["vertex_identity_basis"], 1)
    Jc = J + np.tensordot(c, g["joint_identity_basis"], 1)
    q = base.gnm_eyes(V, g)[0]
    assert np.linalg.norm(q["c"] - Jc[2]) < 3e-5 and abs(q["r"] - e[0]["r"]) < 2e-5 and abs(q["limbus"] - e[0]["limbus"]) < 3e-5


def test_loose_pieces_are_gnms_own_shapes():
    g = base._gnm_data()
    T = g["template_vertex_positions"].astype(float)
    assert np.abs(base._gnm_pieces(T, T, g) - T).max() < 1e-12      # nothing of ours on the head: exactly GNM's
    # the skin warped by a field of ours (a stretch across + a shear): the pieces stay similar to GNM's own
    W = T * [1.08, 1.0, 0.97] + 0.02 * T[:, [1]] * [0, 0, 1.0]
    P = base._gnm_pieces(W, T, g)
    for ids, anc in base._gnm_piece_sets(g):
        A, Bq = T[ids] - T[ids].mean(0), P[ids] - P[ids].mean(0)
        k = np.sqrt((Bq ** 2).sum() / (A ** 2).sum())
        assert np.abs(Bq - k * A).max() < 1e-9 and 0.95 < k < 1.1   # a translation and one scale: no squash, no turn
    q = base.gnm_eyes(P, g)[0]
    assert abs(q["limbus"] / q["r"] - 0.00604 / 0.01458) < 0.004    # still GNM's eye, proportions kept


# ---- the built head ----------------------------------------------------------------------------------------------

def test_default_eyeball_is_gnms_and_the_lids_lie_on_it():
    sp = _spec()
    assert "eye_radius" not in sp["base"]["head"]                   # the human tool no longer writes our 12 mm ball
    ht = _head(sp)
    eg = ht["eye_gnm"]
    assert eg is not None and base.eye_native(sp) is not None
    s = float(ht["carry"]["s"])
    assert 0.9 * 0.01458 * s < ht["eye_r"] < 1.1 * 0.01458 * s      # GNM's sphere x the head's scale (x the lids' own)
    assert 0.38 < eg["limbus"] / ht["eye_r"] < 0.45 and abs(eg["pupil"] - 0.5) < 0.02
    assert abs(base.drawn_iris(sp) - eg["limbus"]) < 1e-9
    # the lids: GNM's contact rings (the socket lining just behind the margin) lie ON the ball, its margin a lid's
    # thickness off it; with the 12 mm override the same rings stand off
    t, mir = lidrings.topo(), lidrings.mirror()
    W = np.asarray(ht["gnm_world"], float)

    def off(h, k):
        ids = t["loops"][k]
        return float(np.mean([(np.linalg.norm(W[i] - c, axis=1) - h["eye_r"]).mean() for c, i in ((h["eyes"][0], ids), (h["eyes"][1], mir[ids]))]))
    assert abs(off(ht, -2)) < 0.0006 and 0.0002 < off(ht, 0) < 0.0016
    old = _spec(eye_radius=0.012)
    ho = _head(old)
    assert ho["eye_gnm"] is None and base.eye_native(old) is None and abs(ho["eye_r"] - 0.012) < 1e-9
    assert off(ho, -2) > off(ht, -2) + 0.0002                        # our smaller ball left the lids off it
    assert abs(base.drawn_iris(old, ho["eye_r"]) - 0.51 * 0.985 * 0.012) < 1e-9
    # the eye joints, the cornea and the gaze: the injected blobs
    inj = base.inject(sp)
    c, f = np.array(inj["joints"]["eye.L"]["pos"]), np.array(inj["joints"]["eye_front.L"]["pos"])
    assert np.linalg.norm(c - ht["eyes"][0]) < 1e-4 and abs(np.linalg.norm(f - c) - ht["eye_r"]) < 1e-4
    co = inj["blobs"]["cornea.L"]
    assert abs(co["size"][0] - eg["cornea_r"]) < 2e-5               # GNM's corneal sphere, on by default
    apex = np.linalg.norm(np.array(co["at"]) - c) + co["size"][0]
    assert abs(apex - eg["apex"]) < 5e-5
    assert "cornea.L" not in base.inject({**sp, "base": {**sp["base"], "cornea": False}})["blobs"]
    # a look-at turns the gaze about GNM's centre
    look = base.inject({**sp, "base": {**sp["base"], "look_at": [0.5, -1.0, 1.6]}})
    f2 = np.array(look["joints"]["eye_front.L"]["pos"])
    assert np.linalg.norm(f2 - f) > 0.002 and abs(np.linalg.norm(f2 - c) - ht["eye_r"]) < 1e-4


def test_limbus_and_pupil_are_identity_and_expression():
    sp = _spec()
    eg = base.eye_native(sp)
    want = 2000 * eg["limbus"] - 0.8                                 # an iris 0.8 mm smaller
    li = base.limbus_identity(sp, want)
    assert -3 < li["eyes_000"] < -0.5
    sp2 = _spec(identity={"eyes_000": li["eyes_000"]})
    e2 = base.eye_native(sp2)
    assert abs(2000 * e2["limbus"] - want) < 0.06                    # mm
    assert abs(_head(sp2)["eye_r"] - _head(sp)["eye_r"]) < 2e-5      # the ball did not change
    with pytest.raises(ValueError):
        base.limbus_identity(sp, 2000 * eg["limbus"] + 4.0)          # no eye in GNM's population
    sp3 = _spec(expression={"pupils_000": -1.0})
    assert base.eye_native(sp3)["pupil"] < 0.36 and abs(base.eye_native(sp3)["limbus"] - eg["limbus"]) < 2e-5


# ---- the mouth ---------------------------------------------------------------------------------------------------

def test_mouth_mode_and_fallback():
    sp = _spec()
    b = sp["base"]
    ht = _head(sp)
    assert base.mouth_mode(b) == "gnm" and base.mouth_mode(b, ht) == "gnm" and ht["mouth_off"] < 1e-6
    assert set(base.implied_parts(sp)) >= {"teeth", "teeth_lower", "tongue"}
    kit = {**b, "head": {**b["head"], "interior": {"teeth": True, "tongue": True}}}
    assert base.mouth_mode(kit) == "kit"                             # an old spec's interior keeps its meaning
    assert base.mouth_mode({**b, "head": {**kit["head"], "mouth": "gnm"}}) == "gnm"
    assert base.mouth_mode({**b, "head": {**b["head"], "mouth": "none"}}) == "none"
    with pytest.raises(ValueError):
        base.mouth_mode({**b, "head": {**b["head"], "mouth": "ours"}})
    # a style that pushes the lips off GNM's surface: GNM's teeth no longer fit; said, and the kit / nothing instead
    pushed = _spec(shape={"push": [{"lm": [51, 57], "radius": 0.026, "amount": 0.006, "dir": [0, 1, 0]}]})
    hp = _head(pushed)
    assert hp["mouth_off"] > 0.003 and base.mouth_mode(pushed["base"], hp) == "none"
    note = base.mouth_note(pushed["base"], hp)
    assert note and "moved the lips" in note
    assert not [p for p in specmod.compile_prims(pushed) if p.name.startswith("gnm_")]
    pk = copy.deepcopy(pushed)
    pk["base"]["head"]["interior"] = {"teeth": True, "tongue": True}
    pk["base"]["head"]["mouth"] = "gnm"
    assert base.mouth_mode(pk["base"], _head(pk)) == "kit" and "kit" in base.mouth_note(pk["base"], _head(pk))


def test_gnm_mouth_pieces_in_the_field():
    sp = _spec()
    prims = {p.name: p for p in specmod.compile_prims(sp)}
    assert {"gnm_teeth_upper", "gnm_teeth_lower", "gnm_tongue"} <= set(prims)
    assert prims["gnm_teeth_upper"].part == "teeth" and prims["gnm_tongue"].part == "tongue"
    assert prims["gnm_teeth_lower"].part == "teeth_lower"  # (one part: the rows met at the bite and jawOpen tore them)
    assert "mouth_fill" in specmod.expand_mirror(sp)["blobs"]        # closed lips: the fill behind them, as before
    ht = base.head_of({"joints": specmod.expand_mirror(sp)["joints"]}, sp["base"])
    mp = base.gnm_mouth(ht)
    for k in ("teeth_upper", "teeth_lower", "tongue"):
        p = prims[f"gnm_{k}"]
        V = mp[k]["verts"]
        d = sdf.SDF[p.kind](V, p.params)
        assert np.abs(d).max() < 0.0015                              # the solid's surface is GNM's own
        # a closed solid: a few cm away in every direction it is outside (the plain IMLS of these open shells was not)
        far = V.mean(0) + 0.06 * np.array([[1, 0, 0], [-1, 0, 0], [0, 1, 0], [0, -1, 0], [0, 0, 1], [0, 0, -1.0]])
        assert (sdf.SDF[p.kind](far, p.params) > 0.005).all()
    # the teeth sit behind the lips: none outside the head's skin
    body = [p for p in prims.values() if p.part == "body"]
    T_ = np.r_[mp["teeth_upper"]["verts"], mp["teeth_lower"]["verts"]]
    assert (sdf.field_at(body, T_, clip=False) < 0).all()


def test_jaw_open_moves_gnms_own_pieces_and_opens_the_bag():
    sp0 = _spec()
    face = faceshapes.face_of(sp0)
    assert isinstance(face, faceshapes.GnmFace) and face.gnm_mouth
    cf = face.shape_coeffs("jawOpen")
    assert cf and all(k.startswith("lower_face_region") for k in cf)
    sp1 = _spec(expression=cf)
    e0, e1 = specmod.expand_mirror(sp0), specmod.expand_mirror(sp1)
    h0 = base.head_of({"joints": e0["joints"]}, sp0["base"])
    h1 = base.head_of({"joints": e1["joints"]}, sp1["base"])
    m0, m1 = base.gnm_mouth(h0), base.gnm_mouth(h1)
    up = np.asarray(m0["frame"][2])
    lo = (m1["teeth_lower"]["verts"] - m0["teeth_lower"]["verts"]) @ up
    assert lo.min() < -0.006                                         # the lower row drops with GNM's jaw ...
    # ... the upper row stays (to the error of telling the neutral from the posed skin: 0.6 mm at this 14 deg jaw)
    assert np.abs(m1["teeth_upper"]["verts"] - m0["teeth_upper"]["verts"]).max() < 0.001
    assert ((m1["tongue"]["verts"] - m0["tongue"]["verts"]) @ up).mean() < -0.003          # the tongue rides the jaw
    assert m1["gap"] > 0.008 and "mouth_fill" not in e1["blobs"]
    # the cavity: outside the head's field behind the parted lips (GNM's sock closes it), flesh beyond the sock
    prims = specmod.compile_prims(sp1)
    body = [p for p in prims if p.part == "body"]
    M, out = np.asarray(m1["frame"][0]), np.asarray(m1["frame"][1])
    assert sdf.field_at(body, (M - 0.012 * out)[None], clip=False)[0] > 0.001
    own = np.asarray(base._gnm_data()["groups"]["mouth_sock"])[m1["sock"]["ids"]] > 0.5
    c = m1["sock"]["verts"][own].mean(0)
    assert sdf.field_at(body, (c - 0.06 * out)[None], clip=False)[0] < 0        # behind the bag: the head again


def test_face_shapes_on_gnms_own_mouth():
    sp = _spec()
    face = faceshapes.face_of(sp)
    mp = base.gnm_mouth(face.head)
    names = ["jawOpen", "mouthSmileLeft", "tongueOut", "eyeBlinkLeft", "mouthClose"]
    lowv, upv, tgv = mp["teeth_lower"]["verts"], mp["teeth_upper"]["verts"], mp["tongue"]["verts"]
    Dl = face.displacements(lowv, lowv, np.zeros_like(lowv), "teeth", names)
    Du = face.displacements(upv, upv, np.zeros_like(upv), "teeth", names)
    Dt = face.displacements(tgv, tgv, np.zeros_like(tgv), "tongue", names)
    assert (Dl["jawOpen"] @ face.up).min() < -0.006 and np.abs(Du["jawOpen"]).max() < 0.0006
    # near-rigid: GNM's jaw turns the lower row ~22 deg (GNM_OPEN), through a LINEAR basis: off a true rotation by
    # r (1 - cos) ~ 2.6 mm (1.6 at the old 14 deg)
    X0, X1 = lowv, lowv + Dl["jawOpen"]
    a, b = X0.mean(0), X1.mean(0)
    U, _, Vt = np.linalg.svd((X0 - a).T @ (X1 - b))
    Rr = (U @ Vt).T
    assert np.abs((X0 - a) @ Rr.T + b - X1).max() < 0.0032
    assert np.abs(Dl["eyeBlinkLeft"]).max() < 1e-6 and np.abs(Dt["eyeBlinkLeft"]).max() < 1e-6
    assert np.abs(Du["mouthSmileLeft"]).max() < 0.0006               # a smile does not move the upper teeth
    # the tongue: out past the lips' front with GNM's own tongue components (not a stretched blob)
    # (its most forward vertex at rest is the floor's attachment under the blade, which no tongue component moves)
    lips = max(float(face.head["lm68"][i] @ face.out) for i in (51, 57))
    assert float(((tgv + Dt["tongueOut"]) @ face.out).max()) > lips + 0.003
    assert float(((tgv + Dt["jawOpen"]) @ face.out).max()) < lips
    cf = face.shape_coeffs("tongueOut")
    assert any(k.startswith("tongue_") for k in cf) and max(abs(v) for k, v in cf.items() if k.startswith("tongue_")) < 4.5
    assert face.shape_coeffs("eyeLookUpLeft") == {} and face.shape_coeffs("cheekPuff") == {}
    # the parts the export will find, and how fine it meshes the teeth
    assert face.parts_teeth == {"teeth", "teeth_lower"} and face.parts_tongue == {"tongue"}
    assert face.voxels()["teeth"] <= 0.0005 and face.voxels()["teeth_lower"] <= 0.0005
    # a row's part says which row it is: the lower row's vertices nearest the UPPER row's (at the bite) still ride
    # the jaw, the upper row's nearest the lower row stay
    D2 = face.displacements(upv, upv, np.zeros_like(upv), "teeth", ["jawOpen"], np.ones(len(upv), bool))
    assert (D2["jawOpen"] @ face.up).min() < -0.006
    D3 = face.displacements(lowv, lowv, np.zeros_like(lowv), "teeth", ["jawOpen"], np.zeros(len(lowv), bool))
    assert np.abs(D3["jawOpen"]).max() < 0.0006
    # a blink's lid clears GNM's corneal bulge too
    assert face.eyes["Left"].get("cornea") is not None


def test_block_in_keeps_the_whole_identity():
    from hifipushie import blockin as bi
    sp = _spec(identity={"eyes_000": -1.2, "teeth_003": 0.7, "head_000": 0.5})
    c = bi.identity(sp)
    assert c[0] == 0.5 and len(c) == 170
    bi.set_identity(sp, c + 0.1)
    idn = sp["base"]["head"]["identity"]
    assert idn["eyes_000"] == -1.2 and idn["teeth_003"] == 0.7 and abs(idn["head_000"] - 0.6) < 1e-9
    assert bi.identity_extra(sp) == {"eyes_000": -1.2, "teeth_003": 0.7}
    # every GNM identity name is a valid key of the spec's identity (one vector: 170 + 3 + 80)
    g = base._gnm_data()
    assert len(base._gnm_coeffs(g["identity_names"], idn)) == 253


def test_size_is_held_and_the_iris_is_its_weak_ruler():
    """No picture reads the head's overall size (every camera's scale is free), so the joint solve holds it at the
    start head's by default (Joe, 2026-10-12: "I'd trust the model more"); the iris may pull it, weakly."""
    from hifipushie import face_ruler as fr, solve_report as sr
    assert fr.SIZE_HOLD is True
    g = sr.size_gain()
    psd = sr.size_prior_sd()
    assert g.shape == (170,) and 0.015 < psd < 0.08                 # GNM's own spread of head size: a few per cent
    d = np.zeros(170)
    d[0] = 1.0
    r0, r1 = sr.size_row(done=d), sr.size_row(done=d, target=0.04)
    assert abs(r0["o"] + g[0]) < 1e-12 and abs(r1["o"] - (0.04 - g[0])) < 1e-12 and r0["sig"] == sr.SIZE_SIG
    # the iris' say at +- 7 % against the prior's spread: a weak pull, and a combined sigma under either
    w = psd ** 2 / (psd ** 2 + sr.SIZE_IRIS_SIG ** 2)
    comb = 1 / np.sqrt(1 / psd ** 2 + 1 / sr.SIZE_IRIS_SIG ** 2)
    assert 0.03 < w < 0.6 and comb < min(psd, sr.SIZE_IRIS_SIG)


def test_inner_lip_paint_covers_the_rolls_not_the_outer_lips():
    """The inner rolls (GNM's rings from the mouth loop to the contact ring) get the wet inner-lip colour: hidden in
    the closed neutral, the bake filled them with skin and every parting shape showed a brown fringe."""
    from scipy.spatial import cKDTree
    from hifipushie import skin_features as sf
    sp = _spec()
    head = base.head_of({"joints": specmod.expand_mirror(sp)["joints"]}, sp["base"])
    V, N, val, s = sf._inner_lip_cloud(head, base.gnm_mouth(head), base._gnm_data())
    on = cKDTree(V[val > 0.99])
    lm = head["lm68"]
    assert max(on.query(lm[i])[0] for i in (61, 62, 63, 65, 66, 67)) < 0.002   # the contact ring: inner lip
    assert min(on.query(lm[i])[0] for i in (50, 51, 52, 56, 57, 58)) > 0.003   # the outer vermilion: not
