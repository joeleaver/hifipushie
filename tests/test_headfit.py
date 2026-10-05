"""Heads with an age, a sex and a weight (headfit.py): uv run python tests/test_headfit.py   (needs the gnm pack; the
MakeHuman pack only for the checks against it)"""
import json
from pathlib import Path

import numpy as np

from hifipushie import assets, headfit

ROOT = Path(__file__).resolve().parents[1]


def have(mh=False):
    try:
        assets.path("gnm", "gnm/shape/data/versions/v3_0/gnm_head.npz")
        if mh:
            from hifipushie import makehuman
            makehuman.body({"age": 25})
        return True
    except Exception as err:  # the packs aren't in the repo
        print("skipped:", str(err)[:80])
        return False


def base(body=None, **head):
    h = {"source": "gnm", "seed": 5, "spread": 0.7, **head}
    b = {"head": {k: v for k, v in h.items() if v is not None}}
    if body is not None:
        b["body"] = {"source": "makehuman", **body}
    return b


def test_tables():
    t = headfit.table()
    assert len(t["lm68"]) == 68 and set(t["extra"]) == set(t["gnm_extra"]) == set(headfit.CRANIUM)
    assert len(t["dense_gnm"]) == len(t["dense_mh"]) > 200
    a = headfit.axes()
    n = 68 + 4 + len(t["dense_gnm"])
    assert a["age_sex"].shape == (len(a["ages"]), 2, n, 3) and a["weight"].shape == (2, 2, n, 3)
    d, io = headfit.shape_delta(25, 0.5, 0.5)
    assert np.abs(d).max() < 1e-6 and 0.05 < io < 0.07  # the reference is no move
    child, _ = headfit.shape_delta(6, 0.5)
    man, _ = headfit.shape_delta(35, 1.0)
    woman, _ = headfit.shape_delta(35, 0.0)
    assert child[8][1] > 0.1 and child[68][1] > 0  # a child's chin is nearer the eyes, the cranium higher over them
    assert man[8][1] < woman[8][1]  # a man's longer lower face
    assert (man[12][0] - man[4][0]) > (woman[12][0] - woman[4][0])  # and wider jaw
    for a_, b_ in ((0, 16), (36, 45), (48, 54)):  # moves mirror
        assert np.allclose(man[a_] * [-1, 1, 1], man[b_], atol=3e-3), (a_, b_)


def test_when_it_applies():
    assert not headfit.applies(base({"age": 8}))  # off unless asked: existing characters keep their heads
    assert headfit.applies(base({"age": 8}, follow_body=True)) and headfit.applies(base({"age": 8}, follow_body=0.5))
    assert not headfit.applies(base({"age": 8}, follow_body=False)) and not headfit.applies(base({"age": 8}, follow_body=0))
    assert not headfit.applies(base(None, follow_body=True))  # the template body has no age of its own to follow
    assert headfit.applies(base(None, like={"sex": 0.0})) and headfit.applies(base(None, features={"jaw": -1}))
    w = headfit.wanted(base({"age": 70, "sex": 0.0}, follow_body=True, like={"age": 30}))
    assert (w["age"], w["sex"], w["weight"]) == (30.0, 0.0, 0.5)  # like sets one control apart from the body
    w = headfit.wanted(base(None, like={"sex": 0.0}))
    assert (w["age"], w["sex"]) == (25.0, 0.0) and not w["follow"]
    for bad in ({"like": {"gender": 1}}, {"features": {"ears": 1}}):
        try:
            headfit.wanted(base(None, **bad))
            raise AssertionError("accepted " + str(bad))
        except ValueError:
            pass
    for f in ("examples/disc_golfer_mh.json", "examples/disc_golfer_style.json", "examples/gnm_talk.json"):
        assert not headfit.applies(json.loads((ROOT / f).read_text())["base"]), f  # the golfer keeps his face


def _shape(b):
    """(chin drop, cranium height, jaw width, brow height, the head dict, cheek width) of the head as solved (identity + warp), interoculars."""
    h = headfit.follow(b, b["head"])
    X = headfit.solved_points(h)
    return -X[8][1], X[68][1], abs(X[12][0] - X[4][0]), X[19][1], h, abs(X[13][0] - X[3][0])


def test_age_and_sex_reach_the_head():
    child, man, woman, old = (_shape(base(None, like=p)) for p in ({"age": 7}, {"age": 35, "sex": 1.0},
                                                                   {"age": 35, "sex": 0.0}, {"age": 82, "sex": 1.0}))
    assert child[0] < woman[0] < man[0], (child[0], woman[0], man[0])  # a child's short lower face, a man's long one
    assert child[1] / child[0] > 1.08 * man[1] / man[0]  # more cranium over less face
    assert woman[2] < man[2]  # a narrower jaw
    for s in (child, man, woman, old):
        assert max(abs(v) for v in s[4]["identity"].values()) <= headfit.CLIP + 1e-6 and s[4]["plane_follows_chin"]
        assert "scale" not in s[4]  # only following a body sets the head's size
    for p in ({"age": 7}, {"age": 35, "sex": 0.0}, {"age": 82, "sex": 1.0}):
        r = headfit.report(base(None, like=p))
        assert r["field_io"] > 0.08 and r["stretch_max"] < 0.35, r  # the shape itself is MakeHuman's head, as a field
    # the seed's own sex doesn't decide: every seed's woman has a narrower jaw than the same seed's man
    for seed in (1, 5, 8, 11):
        w_, m_ = (_shape({"head": {"source": "gnm", "seed": seed, "spread": 0.7, "like": {"sex": s}}}) for s in (0.0, 1.0))
        assert w_[2] < m_[2] - 0.03 and w_[0] < m_[0], seed
    # the same people across seeds differ (the seed keeps what is its own)
    a, b = (_shape({"head": {"source": "gnm", "seed": s, "spread": 0.7, "like": {"sex": 0.0}}})[4]["identity"] for s in (5, 8))
    assert np.abs(np.array(list(a.values())) - np.array(list(b.values()))).max() > 0.5
    # dimorphism: a woman's jaw is narrower still with it, a man's wider; 0 = MakeHuman's own sexes
    j = lambda sex, dm: _shape(base(None, like={"sex": sex}, dimorphism=dm))[2]  # noqa: E731
    assert j(0.0, 1.0) < j(0.0, 0.0) < j(1.0, 0.0) < j(1.0, 1.0) and j(1.0, 1.0) - j(1.0, 0.0) < j(0.0, 0.0) - j(0.0, 1.0)
    assert abs(j(0.5, 1.0) - j(0.5, 0.0)) < 1e-9
    F = headfit.fields()
    assert F["ref"].shape[1] == 3 and F["age_sex"].shape[:2] == (len(F["ages"]), 2) and F["valid"].sum() > 9000
    own = headfit.follow(base(None, like={"age": 7}, identity={"head_000": 1.5}),
                         {"source": "gnm", "seed": 5, "like": {"age": 7}, "identity": {"head_000": 1.5}})
    assert own["identity"]["head_000"] == 1.5  # the head's own identity entries win


def test_features():
    n = _shape(base(None, features={"jaw": 1e-6}))  # (a `like` head is MakeHuman-shaped: another baseline)
    jaw = _shape(base(None, features={"jaw": 1.0}))
    brow = _shape(base(None, features={"brow_ridge": 1.0}))
    assert jaw[2] > n[2] + 0.02 and abs(jaw[1] - n[1]) < 0.02  # a wider jaw, the cranium where it was
    assert brow[3] < n[3] - 0.01 and abs(brow[2] - n[2]) < 0.02  # a lower, heavier brow; the jaw where it was
    cheeks = _shape(base(None, features={"cheeks": 1.0}))
    assert cheeks[5] > n[5] + 0.02 and abs(cheeks[1] - n[1]) < 0.02  # fuller cheeks
    M = headfit.feature_masks()
    assert all(0 <= m.min() and m.max() > 0.9 for m in M.values())


def test_follows_its_body():
    """Needs MakeHuman: the head takes the body's age and sex and the body's own head's size."""
    b = base({"age": 7, "sex": 0.5, "height": 1.22}, follow_body=True)
    adult = base({"age": 35, "sex": 1.0, "height": 1.8}, follow_body=True)
    h, ha = headfit.follow(b, b["head"]), headfit.follow(adult, adult["head"])
    assert h["scale"] < 0.95 * ha["scale"] and 0.8 < ha["scale"] < 1.05, (h["scale"], ha["scale"])
    w = headfit.wanted(b)
    assert (w["age"], w["sex"]) == (7.0, 0.5)
    half = headfit.wanted(base({"age": 7}, follow_body=0.5))
    assert half["amount"] == 0.5
    # the sampled table against MakeHuman itself, between its samples
    ref, _ = headfit.mh_points({**headfit.table()["reference"]})
    for p in ({"age": 11, "sex": 0.3, "weight": 0.6}, {"age": 58, "sex": 0.8, "weight": 0.3}):
        d0 = headfit.mh_points({**p, "muscle": 0.5})[0] - ref
        d1, _ = headfit.shape_delta(p["age"], p["sex"], p["weight"])
        assert np.sqrt(((d0 - d1) ** 2).sum(1).mean()) < 0.12 * np.sqrt((d0 ** 2).sum(1).mean()), p


def test_without_the_keys_nothing_changes():
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
        for fn in (test_tables, test_when_it_applies, test_age_and_sex_reach_the_head, test_features):
            fn()
            print("ok", fn.__name__)
    if have(mh=True):
        for fn in (test_follows_its_body, test_without_the_keys_nothing_changes):
            fn()
            print("ok", fn.__name__)
