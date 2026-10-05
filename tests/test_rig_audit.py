"""The skin weights' audit (rig_audit.py) and the template weights (rig_template.py).

The user on a posed export: "the fingers are getting mangled and so is the jaw. We might have serious issues with how
our skin weights are getting made." The audit must say so in numbers (and not cry wolf at a web between two fingers);
a base body made from MakeHuman must take MakeHuman's own hand-made weights, read off its surface, so one finger's
bones hold nothing of the next finger; and the Head joint must pivot at the skull's base, not the neck's.
The MakeHuman / GNM parts run when the asset packs are present ($HIFIPUSHIE_ASSETS).
Run: uv run python tests/test_rig_audit.py"""
import copy
import json
import os
import tempfile
from pathlib import Path

os.environ.setdefault("HIFIPUSHIE_HOME", tempfile.mkdtemp(prefix="hp_rigaudit_"))

import numpy as np  # noqa: E402

from hifipushie import rig, rig_audit, rig_template, store  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
P = rig.PREFIX
_C = {}


def _goblin():
    if "goblin" not in _C:
        spec = json.loads((ROOT / "examples" / "goblin_talk.json").read_text())
        store.save("rigaudit_goblin", spec, "test")
        z = np.load(store.build("rigaudit_goblin", 128)["mesh"])
        V, F = z["verts"].astype(np.float64), z["faces"]
        bones = rig.rig_bones(spec)
        J, W = rig.skin_mesh(spec, bones, V, F, z["part"], [str(n) for n in z["part_names"]])
        _C["goblin"] = (spec, bones, V, F, J, W)
    return _C["goblin"]


def _human():
    """(spec, bones, base quad vertices, triangles, surface) or None without the packs."""
    if "human" not in _C:
        try:
            from hifipushie import base as basemod
            from hifipushie.spec import expand_mirror
            spec = json.loads((ROOT / "examples" / "gnm_talk.json").read_text())
            bones = rig.rig_bones(spec)
            surf = basemod.surface(basemod.inject(expand_mirror(spec)), spec["base"])
        except Exception as e:  # the packs aren't here
            print("  (skipped: %s)" % str(e).splitlines()[0][:80])
            _C["human"] = None
            return None
        Wq, fq = surf["quads"]
        Tq = np.array([(f[0], f[j], f[j + 1]) for f in fq for j in range(1, len(f) - 1)])
        _C["human"] = (spec, bones, np.asarray(Wq, float), Tq, surf)
    return _C["human"]


def test_audit_reads_a_skin():
    """Sums, influence counts, a row per turned joint, lines to read."""
    _, bones, V, F, J, W = _goblin()
    a = rig_audit.audit(bones, V, F, J, W)
    s = a["static"]
    assert s["sum_error"] < 1e-9 and s["negative"] == 0 and s["influences_max"] <= 4
    assert len(a["bones"]) > 30 and all(r["deg"] > 0 for r in a["bones"])
    names = {r["bone"] for r in a["bones"]}
    assert P + "LeftForeArm" in names and P + "Head" in names
    assert not any("Twist" in n or n.endswith("_End") for n in names)  # twist and end joints aren't turned
    txt = rig_audit.audit_text(a)
    assert txt[0].startswith("weights audit") and any("each joint turned alone" in t for t in txt)
    # a rigid thing reads rigid: the head's own skin follows a head turn
    head = next(r for r in a["bones"] if r["bone"] == P + "Head")
    assert head["rigid_p95"] < 0.5, head


def test_audit_catches_a_planted_fault():
    """One finger's skin given to its neighbour's bones: bleed and leak say so, and say whose skin moved."""
    _, bones, V, F, J, W = _goblin()
    names = [b["name"] for b in bones]
    a0 = rig_audit.audit(bones, V, F, J, W, only=["LeftHand"])
    src = [i for i, n in enumerate(names) if n.startswith(P + "LeftHandMiddle")]
    dst = [i for i, n in enumerate(names) if n.startswith(P + "LeftHandIndex")]
    J2 = J.copy()
    for a, b in zip(src, dst):  # the middle finger's skin now follows the index finger's bones
        J2[J == a] = b
    a1 = rig_audit.audit(bones, V, F, J2, W, only=["LeftHand"])
    b0 = max((r["max"] for r in a0["static"]["digit_bleed"] if r["holder"] == "LeftIndex"), default=0.0)
    b1 = max((r["max"] for r in a1["static"]["digit_bleed"] if r["holder"] == "LeftIndex" and r["on"] == "LeftMiddle"),
             default=0.0)
    assert b1 > 0.8 and b1 > b0 + 0.5, (b0, b1)
    row = next(r for r in a1["bones"] if r["bone"] == P + "LeftHandIndex1")
    assert rig_audit.is_bad(row) and row["leak_max"] > 3 and "Middle" in row.get("leak_on", ""), row
    mid = next(r for r in a1["bones"] if r["bone"] == P + "LeftHandMiddle1")
    assert mid["rigid_p95"] > 3, mid  # and the middle finger no longer follows its own bone
    assert any("<- BAD" in t for t in rig_audit.audit_text(a1))


def test_surface_transfer_keeps_sides_apart():
    """Two sheets 2 mm apart facing opposite ways (two fingers' sides): a point takes the weights of the sheet that
    faces its way, though the other sheet's vertices are as near."""
    g = np.stack(np.meshgrid(np.linspace(0, 0.02, 9), np.linspace(0, 0.02, 9), indexing="ij"), -1).reshape(-1, 2)
    quad = [(i * 9 + j, (i + 1) * 9 + j, (i + 1) * 9 + j + 1, i * 9 + j + 1) for i in range(8) for j in range(8)]
    T = np.array([(q[0], q[1], q[2]) for q in quad] + [(q[0], q[2], q[3]) for q in quad])
    A = np.c_[g, np.zeros(len(g))]                      # faces +z
    B = np.c_[g + 0.0011, np.full(len(g), 0.002)]       # 2 mm above, faces -z (wound the other way)
    Vq = np.r_[A, B]
    Tq = np.r_[T, T[:, ::-1] + len(A)]
    D = np.zeros((len(Vq), 2))
    D[:len(A), 0] = 1
    D[len(A):, 1] = 1
    rng = np.random.default_rng(0)
    pts = np.c_[rng.uniform(0.004, 0.016, (200, 2)), np.full(200, 0.0009)]  # nearer sheet A (0.9 vs 1.1 mm)
    up = np.tile([0, 0, 1.0], (200, 1))
    wa = rig_template.from_surface(Vq, Tq, D, pts, up)
    wb = rig_template.from_surface(Vq, Tq, D, pts + [0, 0, 0.0003], -up)  # nearer A still, but facing B's way
    assert wa[:, 0].min() > 0.999, wa[:, 0].min()
    assert wb[:, 1].min() > 0.999, wb[:, 1].min()
    J, W = rig_template.top_k(np.c_[wa, np.zeros((200, 3))])
    assert J.shape == (200, 4) and np.allclose(W.sum(1), 1)


def test_makehuman_names_fold_onto_mixamo():
    f = rig_template._mixamo
    assert f("finger1-1.L") == "LeftHandThumb1" and f("finger5-3.R") == "RightHandPinky3"
    assert f("metacarpal2.L") == "LeftHand" and f("wrist.R") == "RightHand"
    assert f("upperarm02.L") == "LeftArm" and f("lowerarm01.R") == "RightForeArm" and f("clavicle.L") == "LeftShoulder"
    assert f("upperleg01.R") == "RightUpLeg" and f("lowerleg02.L") == "LeftLeg" and f("toe3-2.L") == "LeftToeBase"
    assert f("jaw") == "Head" and f("oris03.L") == "Head" and f("tongue02") == "Head" and f("eye.R") == "Head"
    assert f("spine03") is None and f("neck02") is None and f("root") is None  # by where they lie
    assert f("pelvis.L") == "Hips" and f("breast.R") == "Spine2"


def test_template_weights_on_a_makehuman_body():
    """The base body's own vertices take MakeHuman's hand-made weights: symmetric, four bones at most after the
    cut, no finger holding another's skin, every finger joint clean; and the Head joint sits at the skull's base."""
    h = _human()
    if h is None:
        return
    spec, bones, Wq, Tq, surf = h
    names = [b["name"] for b in bones]
    D = rig_template.template_weights(spec, bones, surf)
    assert D is not None and D.shape == (len(Wq), len(bones))
    assert np.allclose(D.sum(1), 1, atol=1e-9) and (D >= 0).all()
    assert not D[:, [i for i, b in enumerate(bones) if b.get("twist") or b["end"]]].any()
    J, W = rig_template.top_k(D)
    a = rig_audit.audit(bones, Wq, Tq, J, W)
    s = a["static"]
    # the grafted neck fades to the Neck joint by distance from the template's loop: as symmetric as the graft (0.5 mm)
    assert s["asymmetry"]["p99"] < 1e-3 and s["asymmetry"]["max"] < 0.03, s["asymmetry"]
    assert not [r for r in s["digit_bleed"] if r["max"] > rig_audit.BAD["bleed"]], s["digit_bleed"][:3]
    digits = [r for r in a["bones"] if "Hand" in r["bone"] and r["bone"][-1].isdigit()]
    assert len(digits) == 30 and not [r for r in digits if rig_audit.is_bad(r)], [r for r in digits if rig_audit.is_bad(r)]
    # ours by distance, on the same vertices: the fault the audit was written for
    Jd, Wd = rig.rig_weights(spec, bones, Wq, Tq)
    ad = rig_audit.audit(bones, Wq, Tq, Jd, Wd, only=["Hand"])
    assert sum(rig_audit.is_bad(r) for r in ad["bones"]) > sum(rig_audit.is_bad(r) for r in digits)
    # the pivots: Neck at the neck's base, Head two thirds up it (MakeHuman's own head bone), clavicles unmoved
    from hifipushie.spec import expand_mirror, resolve_point
    e = expand_mirror(spec)
    nk, hd = resolve_point(e, "neck"), resolve_point(e, "head")
    assert np.allclose(bones[names.index(P + "Neck")]["head"], nk)
    head = bones[names.index(P + "Head")]["head"]
    assert 0.05 < head[2] - nk[2] < hd[2] - nk[2], (head, nk, hd)
    assert head[2] > resolve_point(e, "lm_chin")[2] + 0.03  # above the chin, not level with it
    off = copy.deepcopy(spec)
    off["rig"] = {"weights": "distance"}
    assert rig_template.template_weights(off, bones, surf) is None


def test_parts_read_the_base_surface():
    """skin_parts on a base body: a hand's vertices pushed 1 mm off the surface (a glove, the export's low poly) take
    the finger under them, not the neighbour; twist bones get their share after the transfer."""
    h = _human()
    if h is None:
        return
    spec, bones, Wq, Tq, surf = h
    names = [b["name"] for b in bones]
    N = np.zeros_like(Wq)
    fn = np.cross(Wq[Tq[:, 1]] - Wq[Tq[:, 0]], Wq[Tq[:, 2]] - Wq[Tq[:, 0]])
    for c in range(3):
        np.add.at(N, Tq[:, c], fn)
    N /= np.maximum(np.linalg.norm(N, axis=1, keepdims=True), 1e-30)
    sk = rig.skin_parts(spec, bones, {"glove": (Wq + 0.001 * N, Tq)})
    J, W = sk["glove"]
    assert np.allclose(W.sum(1), 1, atol=1e-9) and J.shape[1] == 4
    a = rig_audit.audit(bones, Wq + 0.001 * N, Tq, J, W, only=["Hand"])
    assert not [r for r in a["static"]["digit_bleed"] if r["max"] > rig_audit.BAD["bleed"]], a["static"]["digit_bleed"][:3]
    assert not [r for r in a["bones"] if r["bone"][-1].isdigit() and rig_audit.is_bad(r)]
    tw = [i for i, b in enumerate(bones) if b.get("twist")]
    assert (W * np.isin(J, tw)).sum() > 100  # the forearm and upper arm are shared out along their twist bones
    r = rig.twist_check(bones, Wq + 0.001 * N, Tq, J, W, P + "RightHand", 105.0, True)
    assert r["at_end"] < 8 and r["area_min"] > 0.82, r


def test_grafted_neck_and_worn_parts():
    """The grafted neck is the Neck joint's a few cm above the template's own loop (copied all the way up, the
    loop's shoulder and upper-arm shares pulled the neck with a raised arm), and a part worn on the body (a collar
    reaching above the jaw's floor) keeps the neck's weights where the skin itself becomes head."""
    h = _human()
    if h is None:
        return
    spec, bones, Wq, Tq, surf = h
    names = [b["name"] for b in bones]
    D = rig_template.template_weights(spec, bones, surf)
    src = np.asarray(surf["src"])
    from scipy.spatial import cKDTree
    d, _ = cKDTree(Wq[src >= 0]).query(Wq)
    far = (src < 0) & (d > rig_template.GRAFT_REACH)
    assert far.sum() > 500
    arms = [i for i, n in enumerate(names) if "Arm" in n or "Shoulder" in n]
    assert D[far][:, arms].max() < 1e-9 and D[far, names.index(P + "Neck")].min() > 1 - 1e-9
    hf = rig.head_field(spec, bones)
    hv = hf["h"](Wq)
    ring = (hv > 0.3) & (hv < 1.0) & (Wq[:, 1] > bones[names.index(P + "Head")]["head"][1])  # the nape's band
    assert ring.sum() > 20
    N = np.zeros_like(Wq)
    fn = np.cross(Wq[Tq[:, 1]] - Wq[Tq[:, 0]], Wq[Tq[:, 2]] - Wq[Tq[:, 0]])
    for c in range(3):
        np.add.at(N, Tq[:, c], fn)
    N /= np.maximum(np.linalg.norm(N, axis=1, keepdims=True), 1e-30)
    low = hv < 1.0  # a "collar": everything under the head, 4 mm off the skin; a "cap": the head, 4 mm off
    use = np.flatnonzero(low | (hv >= 1.0))
    sk = rig.skin_parts(spec, bones, {"body": (Wq, Tq), "collar": (Wq[low] + 0.004 * N[low], np.zeros((0, 3), int)),
                                     "cap": (Wq[~low] + 0.004 * N[~low], np.zeros((0, 3), int))})
    hi = names.index(P + "Head")

    def head_w(J, W):
        return (W * (J == hi)).sum(1)
    assert head_w(*sk["body"])[ring].min() > 0.25          # the skin's nape blends toward the head
    assert head_w(*sk["collar"])[ring[low]].max() < 0.02   # the collar round it doesn't
    assert head_w(*sk["cap"]).min() > 0.999                # and what sits on the head is all head
    spec2 = copy.deepcopy(spec)
    spec2.setdefault("parts", {}).setdefault("collar", {})["rig_head"] = True
    sk2 = rig.skin_parts(spec2, bones, {"collar": (Wq[low] + 0.004 * N[low], np.zeros((0, 3), int))})
    assert head_w(*sk2["collar"])[ring[low]].min() > 0.2
    # a strap attached to a bag bound to Hips: beside the bag it is the bag's joint's, far from it the body's
    knee = bones[names.index(P + "LeftLeg")]["head"]
    thigh = np.linalg.norm(Wq - (knee + [0, 0, 0.12]), axis=1) < 0.12
    bag = knee + [0.08, 0, 0.12] + 0.01 * np.random.default_rng(0).normal(size=(50, 3))
    spec3 = copy.deepcopy(spec)
    spec3.setdefault("parts", {}).update({"bag": {"rig_bone": "Hips"}, "strap": {"rig_attach": "bag"}})
    none = np.zeros((0, 3), int)
    sk3 = rig.skin_parts(spec3, bones, {"bag": (bag, none), "strap": (Wq[thigh], none)})
    hips = (sk3["strap"][1] * (sk3["strap"][0] == names.index(P + "Hips"))).sum(1)
    d = np.linalg.norm(Wq[thigh][:, None] - bag[None], axis=2).min(1)
    assert hips[d < 0.02].min() > 0.8 and hips[d > rig.ATTACH].max() < 0.05, (hips[d < 0.02].min(), hips[d > rig.ATTACH].max())
    # shorts ending at the knee, with the shin pruned (rig_drop): the hem is the thigh's, sums stay 1, and a name
    # without a side takes both sides and the twist joints of the segment
    hem = np.linalg.norm(Wq - knee, axis=1) < 0.07
    spec4 = copy.deepcopy(spec)
    spec4.setdefault("parts", {})["shorts"] = {}
    mesh = {"shorts": (Wq[hem] + 0.004 * N[hem], none)}
    leg = rig.drop_joints(bones, ["Leg"])
    assert {names[i][len(P):] for i in np.flatnonzero(leg)} >= {"LeftLeg", "RightLeg", "LeftLegTwist1"}
    assert not leg[names.index(P + "LeftUpLeg")] and not rig.drop_joints(bones, ["LeftLeg"])[names.index(P + "RightLeg")]
    J0, W0 = rig.skin_parts(spec4, bones, mesh)["shorts"]
    spec4["parts"]["shorts"]["rig_drop"] = ["Leg"]
    J1, W1 = rig.skin_parts(spec4, bones, mesh)["shorts"]
    up = names.index(P + "LeftUpLeg")
    upt = [i for i, n in enumerate(names) if n.startswith(P + "LeftUpLeg")]
    assert (W0 * leg[J0]).sum(1).max() > 0.3                      # the transfer gave the hem to the shin
    assert (W1 * leg[J1]).sum(1).max() == 0.0                      # pruned
    assert np.allclose(W1.sum(1), 1.0) and (W1 * np.isin(J1, upt)).sum(1).min() > 0.95
    assert np.allclose((W1 * (J1 == up)).sum(1), (W0 * (J0 == up)).sum(1) + (W0 * leg[J0]).sum(1), atol=1e-9)
    try:
        rig.drop_joints(bones, ["Shin"])
        raise AssertionError("an unknown joint passed")
    except ValueError as e:
        assert "UpLeg" in str(e)


def test_bound_parts_do_not_bury_their_neighbours():
    """A rigged export drops faces buried in another part, but not across parts that move apart: the golfer's
    shorts had a hole where the hip bag (rig_bone Hips) sat at rest, shown as soon as the thigh lifted."""
    from hifipushie import surface
    from hifipushie.spec import compile_prims
    spec = {"joints": {"a": {"pos": [0, 0, 1], "r": 0.1}, "b": {"pos": [0.12, 0, 1], "r": 0.1}},
            "blobs": {"leg": {"at": "a", "size": [0.1, 0.1, 0.1]},
                      "bag": {"at": "b", "size": [0.1, 0.1, 0.1], "part": "bag"},
                      "cuff": {"at": "a", "size": [0.12, 0.12, 0.03], "part": "cuff"}},
            "parts": {"bag": {"rig_bone": "Hips"}, "cuff": {}}}
    st = {}
    for q in compile_prims(spec):
        st.setdefault(q.part, []).append(q)
    names = list(st)
    X = np.array([[0.09, 0, 1.0], [0.0, 0.09, 1.0], [0, 0, 1.09]])  # on the leg: in the bag, in the cuff, free
    part = np.full(3, names.index("body"))
    assert surface.hidden(st, X, part, names, 0.005).tolist() == [1, 1, 0], (names, surface.hidden(st, X, part, names, 0.005))
    apart = {pn: (spec["parts"].get(pn) or {}).get("rig_bone") for pn in names}
    assert surface.hidden(st, X, part, names, 0.005, apart).tolist() == [0, 1, 0]


if __name__ == "__main__":
    for k, f in list(globals().items()):
        if k.startswith("test_"):
            f()
            print("ok", k)
