"""The head follows the body (headfit.py): uv run python tests/test_headfit.py   (needs the gnm + makehuman packs)"""
import json
from pathlib import Path

import numpy as np

from hifipushie import assets, headfit

ROOT = Path(__file__).resolve().parents[1]


def have():
    try:
        assets.path("gnm", "gnm/shape/data/versions/v3_0/gnm_head.npz")
        from hifipushie import makehuman
        makehuman.body({"age": 25})
        return True
    except Exception as err:  # the packs aren't in the repo
        print("skipped:", str(err)[:80])
        return False


def base(body, **head):
    h = {"source": "gnm", "seed": 5, "spread": 0.7, "follow_body": True, **head}
    return {"body": {"source": "makehuman", **body}, "head": {k: v for k, v in h.items() if v is not None}}


def test_table():
    t = headfit.table()
    assert len(t["lm68"]) == 68 and set(t["extra"]) == set(t["gnm_extra"]) == set(headfit.CRANIUM)
    X, io = headfit.body_points(t["reference"])
    assert 0.05 < io < 0.07
    assert np.abs(X[8][0]) < 1e-3 and X[8][1] < -1.4, X[8]  # the chin: on the centre line, under the eyes
    assert X[68][1] > 1.5  # the top of the head
    for a, b in ((0, 16), (36, 45), (48, 54), (31, 35)):  # pairs mirror
        assert np.allclose(X[a] * [-1, 1, 1], X[b], atol=2e-3), (a, b)
    assert X[30][2] > X[27][2] > X[36][2]  # the nose tip in front of the bridge, in front of an eye corner


def test_when_it_applies():
    assert not headfit.applies(base({"age": 8}, follow_body=None))  # off unless asked: existing characters keep their heads
    assert headfit.applies(base({"age": 8}))
    assert headfit.applies(base({"age": 8}, fit={"jaw_width": 1.6}))
    assert headfit.applies(base({"age": 8}, follow_body=0.5))
    assert not headfit.applies(base({"age": 8}, follow_body=False)) and not headfit.applies(base({"age": 8}, follow_body=0))
    assert not headfit.applies({"head": {"source": "gnm", "follow_body": True}})  # the template body has no head of its age
    for f in ("examples/disc_golfer_mh.json", "examples/disc_golfer_style.json", "examples/gnm_talk.json"):
        assert not headfit.applies(json.loads((ROOT / f).read_text())["base"]), f  # the golfer keeps his face


def test_reference_is_no_move():
    b = base(headfit.table()["reference"])
    h = headfit.follow(b, b["head"])
    r = headfit.report(b)
    assert r["asked_io"] == 0 and r["left_io"] == 0, r
    assert 0.85 < h["scale"] < 1.0, h["scale"]  # the head is the body's head's size (the old default 1.4 was a doll's)


def _shape(b):
    """(chin drop, cranium height, jaw width) of the followed GNM head, interocular units."""
    from hifipushie import base as basemod
    g = headfit._gnm()
    h = headfit.follow(b, b["head"])
    c = np.array([h["identity"][g["names"][i]] for i in g["comps"]])
    L = g["L0"] + np.tensordot(c, g["LB"], 1)
    J = g["J0"] + np.tensordot(c, g["JB"], 1)
    io = abs(J[0][0] - J[1][0])
    X = (L - J.mean(0)) / io
    return -X[8][1], X[68][1], abs(X[12][0] - X[4][0]), h


def test_age_and_sex_reach_the_head():
    child, man, woman, old = (_shape(base(p)) for p in ({"age": 7, "sex": 0.5}, {"age": 35, "sex": 1.0},
                                                        {"age": 35, "sex": 0.0}, {"age": 82, "sex": 1.0}))
    assert child[0] < woman[0] < man[0], (child[0], woman[0], man[0])  # a child's short lower face, a man's long one
    assert child[1] / child[0] > 1.08 * man[1] / man[0]  # more cranium over less face
    assert woman[2] < man[2]  # a narrower jaw
    assert child[3]["scale"] < 0.85 * man[3]["scale"]  # and a smaller head
    for s in (child, man, woman, old):
        assert max(abs(v) for v in s[3]["identity"].values()) <= headfit.CLIP + 1e-6
        assert s[3]["plane_follows_chin"]
    for p in ({"age": 7, "sex": 0.5}, {"age": 82, "sex": 1.0}):  # most of the move is made
        r = headfit.report(base(p))
        assert r["left_io"] < 0.55 * r["asked_io"], r
    half = _shape(base({"age": 7, "sex": 0.5}, follow_body=0.5))
    assert child[0] < half[0] < man[0]  # "follow" scales it
    own = headfit.follow(base({"age": 7}, identity={"head_000": 1.5}),
                         {"source": "gnm", "seed": 5, "follow_body": True, "identity": {"head_000": 1.5}})
    assert own["identity"]["head_000"] == 1.5  # the head's own identity entries win


def test_without_the_key_nothing_changes():
    """A seed-only head on a MakeHuman body, as existing characters have: the head built is gnm_head of the head dict
    as given (no identity added, the default scale, the fixed graft plane), bit for bit."""
    from hifipushie import base as basemod
    b = {"body": {"source": "makehuman", "age": 60, "sex": 1.0, "weight": 0.6}, "eyes": "eyes",
         "head": {"source": "gnm", "seed": 5, "spread": 0.7, "mouth_gap": 0.0}}
    s = basemod.inject({"base": b, "joints": {}})
    h = basemod.head_of({"joints": s["joints"]}, b)
    assert not h.get("room")
    tpl, tj, J = basemod.source(b), basemod.template_joints(b), s["joints"]
    eb = np.array(tpl["face"]["landmarks"]["eye.L"]) * [0, 1, 1]
    mid = np.array(J["head"]["pos"], float) + eb - np.array(tj["head"]["pos"])
    ref = basemod.gnm_head(b["head"], mid, np.array([0, 0, 1.0]))
    assert h["verts"].shape == ref["verts"].shape and np.array_equal(h["verts"], ref["verts"])
    assert np.array_equal(h["plane"][0], ref["plane"][0])
    on = basemod.head_of({"joints": s["joints"]}, {**b, "head": {**b["head"], "follow_body": True}})
    assert on.get("room") and not np.array_equal(on["verts"][:100], ref["verts"][:100])


if __name__ == "__main__":
    if have():
        for k, fn in list(globals().items()):
            if k.startswith("test_"):
                fn()
                print("ok", k)
