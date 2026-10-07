"""The export rig's twist chains and rigid head (rig.py; s0urc3's Garrett: a turned hand wrung at the wrist, a jaw
that lagged a head turn).

Twist bones are extra leaves after the Mixamo set: the base joints must not change, an animation of the base joints
alone must move the skin as it did without them, and driven by their documented shares they must spread a roll joint
to joint. The head must be rigid down to the jaw. Uses examples/goblin_talk.json (face kit, teeth, tongue, eyes; no
asset packs); the GNM floor is checked when the packs are there.
Run: uv run python tests/test_rig_twist.py"""
import copy
import json
import os
import tempfile
from pathlib import Path

os.environ.setdefault("HIFIPUSHIE_HOME", tempfile.mkdtemp(prefix="hp_rigtwist_"))

import numpy as np  # noqa: E402

from hifipushie import rig, store  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
P = rig.PREFIX
_CACHE = {}


def _model():
    if not _CACHE:
        spec = json.loads((ROOT / "examples" / "goblin_talk.json").read_text())
        store.save("rigtwist_goblin", spec, "test")
        z = np.load(store.build("rigtwist_goblin", 112)["mesh"])
        _CACHE.update(spec=spec, V=z["verts"].astype(np.float64), F=z["faces"], part=z["part"],
                      names=[str(n) for n in z["part_names"]])
    return _CACHE


def _skin(**opts):
    m = _model()
    key = json.dumps(opts, sort_keys=True)
    if key not in _CACHE:
        spec = copy.deepcopy(m["spec"])
        spec.setdefault("rig", {}).update(opts)
        bones = rig.rig_bones(spec)
        J, W = rig.skin_mesh(spec, bones, m["V"], m["F"], m["part"], m["names"])
        _CACHE[key] = (spec, bones, J, W)
    return _CACHE[key]


def test_base_set_unchanged():
    """The Mixamo joints are the same joints, in the same order, with twist bones on or off; the twist bones come
    after them, hang from their segment's joint and carry nothing."""
    _, off, _, _ = _skin(twist=False)
    _, on, _, _ = _skin()
    assert not any(b.get("twist") for b in off)
    assert len(on) == len(off) + 14, (len(on), len(off))
    for a, b in zip(off, on):
        assert a["name"] == b["name"] and a["parent"] == b["parent"] and a["end"] == b["end"]
        assert np.allclose(a["head"], b["head"], atol=0)
        assert not b.get("twist")
    parents = {b["parent"] for b in on}
    names = [b["name"] for b in on]
    for i, b in enumerate(on[len(off):], len(off)):
        tw = b["twist"]
        assert i not in parents, f"{b['name']} has children"
        assert on[b["parent"]]["name"] == tw["of"] and tw["driver"] in names
        seg = b["name"][len(P):].split("Twist")[0]
        assert seg.endswith(("ForeArm", "Arm", "UpLeg", "Leg")) and b["name"].startswith(P)
        assert abs(np.linalg.norm(tw["axis"]) - 1) < 1e-9
        if tw["mode"] == "follow":
            assert 0 < tw["share"] <= 1 and abs(tw["share"] - tw["station"]) < 1e-6
        else:
            assert -1 <= tw["share"] < 0 and abs(tw["share"] + 1 - tw["station"]) < 1e-6
    fa = [b["twist"] for b in on if b["name"].startswith(P + "LeftForeArmTwist")]
    assert [t["share"] for t in fa] == [0.3333, 0.6667, 1.0]
    ua = [b["twist"] for b in on if b["name"].startswith(P + "LeftArmTwist")]
    assert [t["share"] for t in ua] == [-1.0, -0.5] and [t["station"] for t in ua] == [0.0, 0.5]


def test_options():
    m = _model()
    for tw, n in ((False, 0), (0, 0), (1, 8), (3, 24), ({"forearm": 2, "leg": 0}, 2 * (2 + 2 + 1))):
        spec = {**m["spec"], "rig": {"twist": tw}}
        assert sum(1 for b in rig.rig_bones(spec) if b.get("twist")) == n, tw
    for bad in ({"wrist": 2}, {"arm": 9}):
        try:
            rig.rig_bones({**m["spec"], "rig": {"twist": bad}})
        except ValueError:
            continue
        raise AssertionError(f"rig.twist {bad} accepted")


def test_undriven_is_the_old_skin():
    """An animation that knows only the Mixamo joints (the twist bones left at rest on their parents) moves the skin
    as it did before twist bones existed: the weights are the segment's own, shared out."""
    m = _model()
    _, off, J0, W0 = _skin(twist=False)
    _, on, J1, W1 = _skin()
    for bones, J, W in ((off, J0, W0), (on, J1, W1)):
        assert np.allclose(W.sum(1), 1, atol=1e-9) and (W >= 0).all()
    turns = {P + "LeftForeArm": ([1, 0, 0], -75), P + "RightArm": ([0, 1, 0], 45), P + "LeftUpLeg": ([1, 0, 0], -35),
             P + "RightLeg": ([1, 0, 0], 60), P + "RightHand": ([0.3, 0.2, 1], 50), P + "Neck": ([0, 0, 1], 25)}
    A = rig.pose(off, m["V"], J0, W0, turns)
    B = rig.pose(on, m["V"], J1, W1, turns)
    d = np.linalg.norm(A - B, axis=1)
    # (not exactly 0 everywhere: a vertex with four bones before the split can have five after, and its smallest
    # weight is dropped; the goblin's arms are fused to its belly, the worst case: a web of four-bone vertices)
    assert d.max() < 8e-3 and np.percentile(d, 95) < 5e-4 and (d > 1e-3).mean() < 0.03, \
        (d.max(), np.percentile(d, 95), (d > 1e-3).mean())
    # a vertex's twist weights add up to what its segment's bone had
    names = [b["name"] for b in on]
    for seg in ("LeftForeArm", "RightArm", "LeftUpLeg", "RightLeg"):
        own = [i for i, n in enumerate(names) if n == P + seg or n.startswith(P + seg + "Twist")]
        w1 = (W1 * np.isin(J1, own)).sum(1)
        w0 = (W0 * (J0 == names.index(P + seg))).sum(1)
        assert np.percentile(np.abs(w1 - w0), 99) < 0.05, seg


def test_roll_decomposition():
    """roll_about is the twist of a swing-twist decomposition: a roll comes back whole, a swing across the axis
    has none, and the two composed give the roll."""
    a = np.array([0.6, 0.0, -0.8])
    assert abs(rig.roll_about(a, (a, 75.0)) - 75.0) < 1e-9
    assert abs(rig.roll_about(a, ([0.0, 1.0, 0.0], 40.0))) < 1e-9
    assert abs(rig.roll_about(a, (-a, 30.0)) + 30.0) < 1e-9


def test_forearm_twist_spreads():
    """The hand rolled 75 and 105 degrees: undriven the wrist takes it; driven, the roll runs elbow to wrist, the
    wrist keeps almost none and no section collapses."""
    m = _model()
    _, on, J, W = _skin()
    _, off, J0, W0 = _skin(twist=False)
    for side in ("Left", "Right"):
        for deg, area in ((75.0, 0.9), (105.0, 0.82)):
            old = rig.twist_check(off, m["V"], m["F"], J0, W0, P + side + "Hand", deg, False)
            new = rig.twist_check(on, m["V"], m["F"], J, W, P + side + "Hand", deg, True)
            assert old["at_end"] > 0.7 * deg and old["area_min"] < new["area_min"], (old, new)
            assert new["at_end"] < 8 and new["at_start"] < 10, new
            assert new["step"] < 0.2 * deg and new["area_min"] > area, new
            assert all(b >= a - 1.0 for a, b in zip(new["twist"], new["twist"][1:])), new["twist"]  # monotone
            assert new["tri_p1"] > old["tri_p1"], (old["tri_p1"], new["tri_p1"])
    # three twist bones (the default) against two: smaller steps, less loss
    _, b2, J2, W2 = _skin(twist={"forearm": 2})
    r3 = rig.twist_check(on, m["V"], m["F"], J, W, P + "RightHand", 105.0, True)
    r2 = rig.twist_check(b2, m["V"], m["F"], J2, W2, P + "RightHand", 105.0, True)
    assert r3["area_min"] > r2["area_min"] + 0.04, (r2["area_min"], r3["area_min"])


def test_upper_arm_and_legs():
    """Counter chains: the arm (thigh) rolled about its own length leaves the shoulder's (hip's) skin where it was
    and reaches the full roll at the elbow (knee); the shin follows the foot."""
    m = _model()
    _, on, J, W = _skin()
    for drv, deg in (("RightArm", 60.0), ("LeftArm", 60.0), ("RightUpLeg", 40.0)):
        r = rig.twist_check(on, m["V"], m["F"], J, W, P + drv, deg, True)
        assert abs(r["at_start"]) < 8 and r["twist"][-1] > 0.9 * deg and r["area_min"] > 0.85, (drv, r)
    r = rig.twist_check(on, m["V"], m["F"], J, W, P + "RightFoot", 40.0, True)
    assert r["at_end"] < 5 and r["area_min"] > 0.85, r
    # and a swing has no roll for them to take: the arm raised sideways drives nothing
    turns = rig.drive_twist(on, {P + "RightArm": ([0, 1, 0], 45.0)})
    ax = next(b["twist"]["axis"] for b in on if b["name"] == P + "RightArmTwist1")
    want = rig.roll_about(ax, ([0, 1, 0], 45.0))
    got = turns.get(P + "RightArmTwist1", (ax, 0.0))[1]
    assert abs(got + want) < 1e-9


def test_head_is_rigid():
    """Face, jaw, teeth, tongue and eyes are Head 1.0 and follow a head turn exactly; clavicles and arms have no say
    on the face; below the falloff nothing changed."""
    m = _model()
    spec, on, J, W = _skin()
    _, off, J0, W0 = _skin(rigid_head=False)
    hc = rig.head_check(on, m["V"], J, W)
    old = rig.head_check(off, m["V"], J0, W0)
    face = [r for r in hc["rows"] if r["rel"] >= 0.1]
    assert len(face) >= 4 and all(r["head"] >= 0.995 and r["lag_mm"] < 0.3 and r["arms"] == 0 for r in face), face
    assert max(r["lag_mm"] for r in old["rows"] if r["rel"] >= 0.1) > 5, old["rows"]  # it wasn't before
    wh = hc["head_weight"]
    for pn in ("teeth", "tongue", "eyes"):
        sel = m["part"] == m["names"].index(pn)
        assert sel.any() and wh[sel].min() > 0.999, (pn, wh[sel].min())
    hf = rig.head_field(spec, on)
    h = hf["h"](m["V"])
    body = m["part"] == m["names"].index("body") if "body" in m["names"] else np.ones(len(h), bool)
    same = (h < 1e-9) & body
    assert same.sum() > 1000
    A = rig.pose(on, m["V"][same], J[same], W[same], rig.test_pose(on))
    B = rig.pose(off, m["V"][same], J0[same], W0[same], rig.test_pose(off))
    assert np.abs(A - B).max() < 1e-9  # unrelated regions keep their weights
    assert np.allclose(W.sum(1), 1, atol=1e-9)
    # the falloff is continuous: no vertex's Head weight steps against its neighbours'
    e = np.r_[m["F"][:, [0, 1]], m["F"][:, [1, 2]], m["F"][:, [2, 0]]]
    step = np.abs(wh[e[:, 0]] - wh[e[:, 1]])
    assert step.max() < 0.5, step.max()


def test_rigid_near_and_export_frames():
    """What a face shape moves becomes Head 1.0 with a falloff round it; a twist joint's GLB frame has +Y along its
    segment and binds back to identity."""
    from hifipushie import asset
    m = _model()
    _, on, J, W = _skin(rigid_head=False)
    names = [b["name"] for b in on]
    hi = names.index(P + "Head")
    hj = on[hi]["head"]
    c = m["V"][np.argmin(np.linalg.norm(m["V"] - (hj + [0, -0.1, -0.02]), axis=1))]  # a patch under the chin
    moved = np.linalg.norm(m["V"] - c, axis=1) < 0.03
    assert moved.sum() > 20
    out = rig.rigid_near(on, {"all": (J, W)}, {"all": m["V"]}, {"all": moved * 0.01})
    J2, W2 = out["all"]
    wh = (W2 * (J2 == hi)).sum(1)
    assert wh[moved].min() > 0.999
    far = np.linalg.norm(m["V"] - c, axis=1) > 0.03 + 0.05
    assert np.array_equal(J2[far], J[far]) and np.allclose(W2[far], W[far])
    # a part no shape moves (a collar beside the throat) keeps its weights, however near the moved skin it lies
    out = rig.rigid_near(on, {"all": (J, W), "collar": (J, W)}, {"all": m["V"], "collar": m["V"]}, {"all": moved * 0.01})
    assert np.array_equal(out["collar"][0], J) and np.array_equal(out["collar"][1], W)
    for b in on:
        if b.get("twist"):
            a = asset._Z_TO_Y @ b["twist"]["axis"]
            R = asset._quat_matrix(asset._arc_quat(np.array([0.0, 1.0, 0.0]), a))
            assert np.allclose(R @ [0, 1, 0], a, atol=1e-9) and np.allclose(R @ R.T, np.eye(3), atol=1e-9)
    assert np.allclose(asset._quat_matrix(asset._arc_quat(np.array([0.0, 1, 0]), np.array([0.0, -1, 0]))) @ [0, 1, 0],
                       [0, -1, 0], atol=1e-9)


def test_gnm_floor():
    """A GNM head's floor comes from its jaw landmarks: chin, lips and the jaw's angle are rigid, the throat fades to the
    neck's over the neck's length. Skipped without the asset packs."""
    try:
        spec = json.loads((ROOT / "examples" / "gnm_talk.json").read_text())
        from hifipushie.spec import expand_mirror, resolve_point
        s = expand_mirror(spec)
        bones = rig.rig_bones(spec)
    except Exception as e:  # the packs aren't here
        print("  (skipped: %s)" % str(e).splitlines()[0][:80])
        return
    hf = rig.head_field(spec, bones)
    assert "landmarks" in hf["how"], hf["how"]
    pts = {k: resolve_point(s, k) for k in ("lm_chin", "lm_lip_lower", "lm_nose_tip", "lm_jaw_4.L", "lm_jaw_7.R",
                                            "lm_jaw_0.L", "head")}
    h = hf["h"](np.array(list(pts.values())))
    assert (h > 0.999).all(), dict(zip(pts, h))
    chin = pts["lm_chin"]
    # the head's weight fades down the whole neck (HEAD_FALL ~11 cm), not over a narrow band under the jaw
    under = hf["h"](np.array([chin + [0, 0.02, -0.005], chin + [0, 0.08, -0.05], chin + [0, 0.1, -0.1],
                              chin + [0, 0.1, -0.14]]))
    assert under[0] > 0.9 and 0.3 < under[1] < 0.7 and under[2] < 0.02 and under[3] == 0, under
    names = [b["name"] for b in bones]
    assert hf["bone"] == names.index(P + "Head")


if __name__ == "__main__":
    for k, f in list(globals().items()):
        if k.startswith("test_"):
            f()
            print("ok", k)


def _tube(r, z0, z1, n=48, m=24):
    a = np.linspace(0, 2 * np.pi, n, endpoint=False)
    zs = np.linspace(z0, z1, m)
    V = np.array([[r * np.cos(t), r * np.sin(t), z] for z in zs for t in a])
    F = []
    for j in range(m - 1):
        for i in range(n):
            p, q = j * n + i, j * n + (i + 1) % n
            F += [[p, q, q + n], [p, q + n, p + n]]
    return V, np.array(F)


def test_skin_under_a_collar_follows_the_collar():
    """2026-10-07 (s0urc3's Garrett): the head's long falloff down the neck (HEAD_FALL inside HEAD_COLUMN) left the
    neck skin under his collar Head 0.70 while the collar, worn, takes no head rule: 52 skin vertices came through
    the jacket's collar in the game's idle, 73 at a 33 deg head turn. `skin_cover`: skin a worn part covers (a ray
    out along its normal meets it within COVER_REACH) gets none of the head rule, handing over on the visible side
    within COVER_EASE. A neck as a tube, a collar as a wider tube round its lower half."""
    neck = _tube(0.05, 0.0, 0.12)
    collar = _tube(0.058, -0.01, 0.06)
    meshes = {"body": neck, "collar": collar}
    hf = {"h": lambda V: np.ones(len(V)), "part": lambda V: np.where(np.asarray(V)[:, 2] > 0.1, 1.0, 0.0), "bone": 0}
    cov = rig.skin_cover({"parts": {}}, [], meshes, hf)
    assert set(cov) == {"body"}
    z, c = neck[0][:, 2], cov["body"]
    assert (c[z < 0.055] == 1.0).all()  # under the collar: all of it follows the collar
    assert (c[z > 0.06 + rig.COVER_EASE + 0.006] == 0.0).all()  # visible skin above the hand-over: the head rule
    mid = (z > 0.062) & (z < 0.06 + rig.COVER_EASE)
    assert ((c[mid] > 0) & (c[mid] < 1)).any()  # eased between
    off = rig.skin_cover({"parts": {}, "rig": {"rigid_head": {"cover": False}}}, [], meshes, hf)
    assert off == {}
