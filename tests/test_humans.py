"""Whole humans by age (anthro.py, makehuman's measured growth, humans.py): uv run python tests/test_humans.py
(the body checks need the makehuman pack, the head check the gnm pack too)"""
import numpy as np

from hifipushie import anthro


def have(gnm=False):
    try:
        from hifipushie import assets, makehuman
        makehuman.body({"age": 25})
        makehuman.body({"age": 7, "sex": 0.0})
        if gnm:
            assets.path("gnm", "gnm/shape/data/versions/v3_0/gnm_head.npz")
        return True
    except Exception as err:  # the packs aren't in the repo
        print("skipped:", str(err)[:80])
        return False


def test_references():
    """The compiled tables: statures grow, heads-in-height runs from ~4.6 at one year to ~8 adult, girls pass boys at
    11-12 and stop earlier."""
    for sex in (0.0, 1.0):
        H = [anthro.stature(a, sex) for a in (0, 1, 3, 7, 11, 16, 19, 40)]
        assert all(b >= a for a, b in zip(H, H[1:])), H
        assert 0.47 < H[0] < 0.52 and 0.72 < H[1] < 0.78 and 0.93 < H[2] < 0.98 and 1.18 < H[3] < 1.24, H
        assert H[-1] == H[-2]
        hd = [anthro.heads(a, sex) for a in (1, 3, 7, 11, 19)]
        assert 4.4 < hd[0] < 4.8 and 5.2 < hd[1] < 5.6 and 6.3 < hd[2] < 6.6 and 7.0 < hd[3] < 7.4 and 7.8 < hd[4] < 8.2, hd
    assert anthro.stature(12, 0.0) > anthro.stature(12, 1.0) and anthro.stature(17, 0.0) < anthro.stature(17, 1.0) - 0.1
    r = anthro.reference(3, 0.0)
    assert 0.55 < r["sitting_height"] / r["stature"] < 0.60 and 0.10 < r["hand_length"] / r["stature"] < 0.12, r
    assert 0.62 < anthro.reference(1, 0.5)["sitting_height"] / anthro.stature(1, 0.5) < 0.67


def _measured(age, sex, **kw):
    from hifipushie import headfit, makehuman
    b = makehuman.body({"age": age, "sex": sex, **kw})
    P = np.asarray(b["P"], float)
    return anthro.measure(P, b["J"], float(P[headfit.table()["lm68"][8], 2])), b


def test_children_have_their_age():
    """A body under 25 has the measured proportions and (MakeHuman's adult over WHO's: 2-3% under) stature of its age."""
    for sex in (0.0, 1.0):
        adult = _measured(25, sex)[0]["stature"] / anthro.stature(19, sex)
        assert 0.96 < adult < 1.0, adult
        for age in (1, 2, 3, 5, 7, 9, 11, 13, 16, 19, 22):
            m, _ = _measured(age, sex)
            r = anthro.reference(age, sex)
            assert abs(m["stature"] / (r["stature"] * adult) - 1) < 0.005, (age, sex, m["stature"], r["stature"])
            assert abs(m["heads"] / r["heads"] - 1) < 0.03, (age, sex, m["heads"], r["heads"])
            assert abs(m["head_height"] / r["head_height"] - 1) < 0.05, (age, sex, m["head_height"], r["head_height"])
            assert abs(m["sitting_height"] / r["sitting_height"] - 1) < 0.05, (age, sex, m["sitting_height"], r["sitting_height"])
            assert abs(m["hand_length"] / r["hand_length"] - 1) < (0.15 if age <= 2 else 0.08), (age, sex, m["hand_length"], r["hand_length"])
            if age >= 2:
                assert abs(m["trochanter_height"] / r["trochanter_height"] - 1) < 0.06, (age, sex)
    # a girl's waist comes with puberty: waist girth over hip girth falls from a toddler's to a woman's
    wh = lambda a: (lambda m: m["waist_circ"] / m["hip_circ"])(_measured(a, 0.0)[0])  # noqa: E731
    assert wh(3) > wh(11) > wh(25) - 0.02 and wh(3) > wh(25) + 0.08, (wh(3), wh(11), wh(25))


def test_adults_and_opt_out_unchanged():
    """From 25 years MakeHuman's bodies are what they were; "growth": false gives the old straight-line child."""
    from hifipushie import makehuman
    assert not makehuman.grows({"age": 25}) and not makehuman.grows({"age": 40}) and makehuman.grows({"age": 24.9})
    assert not makehuman.grows({"age": 7, "growth": False})
    old = makehuman.body({"age": 7, "sex": 1.0, "growth": False})
    new = makehuman.body({"age": 7, "sex": 1.0})
    assert abs(float(old["P"][:, 2].max()) - 1.055) < 0.01 and float(new["P"][:, 2].max()) > 1.17
    tall = makehuman.body({"age": 7, "sex": 1.0, "height": 1.3})
    assert abs(float(tall["P"][:, 2].max()) - 1.3) < 1e-6  # a given height wins; the shape is still a 7-year-old's
    m = anthro.measure(tall["P"], tall["J"], float(tall["P"][__import__("hifipushie").headfit.table()["lm68"][8], 2]))
    assert abs(m["heads"] / anthro.heads(7, 1.0) - 1) < 0.03


def test_nipples_smoothed():
    from hifipushie import makehuman
    a = makehuman.body({"age": 3, "sex": 0.0})["P"]
    b = makehuman.body({"age": 3, "sex": 0.0, "nipples": 0.0})["P"]
    d = np.linalg.norm(a - b, axis=1)
    moved = d > 1e-5
    H = a[:, 2].max()
    assert 20 < moved.sum() < 600 and 0.001 < d.max() < 0.012, (moved.sum(), d.max())
    assert (a[moved, 1] < 0).all() and (a[moved, 2] > 0.6 * H).all() and (a[moved, 2] < 0.8 * H).all()
    assert abs(a[moved, 0]).min() > 0.02 * H  # two patches, off the centre line


def test_dressed_by_default():
    """humans.spec: a dressed figure whose clothes cover from the neck's base past the crotch at every age."""
    from hifipushie import humans
    for age, sex in ((1, 0.5), (3, 0.0), (7, 1.0), (11, 0.0), (30, 0.0), (75, 1.0)):
        sp = humans.spec(age, sex, skin=False)
        m = humans.measures(sp)
        shells = {k for k, p in sp["parts"].items() if p.get("shell") == "body"}
        assert shells, sp["parts"]
        lo = min(b["at"][2] - b["size"][2] for b in sp["blobs"].values() if b.get("shape") == "box")
        hi = max(b["at"][2] + b["size"][2] for b in sp["blobs"].values() if b.get("shape") == "box")
        assert lo < m["crotch_height"] - 0.02 * m["stature"], (age, lo, m["crotch_height"])
        assert hi > m["stature"] - m["head_height"] - 0.12 * m["stature"], (age, hi)
        assert sp["base"]["head"]["follow_body"] is True
        assert sp["base"]["body"]["nipples"] == 0.0
    assert "nipples" not in humans.spec(30, 1.0, skin=False, outfit_kind="underwear")["base"]["body"]
    assert humans.spec(1, 0.5, skin=False)["parts"].get("onesie") and humans.spec(4, 0.5, skin=False)["parts"].get("tee")
    assert humans.spec(30, "woman", skin=False)["base"]["body"]["sex"] == 0.0
    assert "skin" in humans.spec(5, "boy") and humans.spec(5, "boy")["skin"]["age"] == 5
    try:
        humans.spec(5, "x")
        raise AssertionError("an unknown sex word was taken")
    except ValueError:
        pass


def test_child_head_keeps_the_bodys_neck():
    """A head that follows its body is that body's own head, so the body keeps its neck and arms (the old neck tube,
    cut at a loop under the graft plane, took a toddler's shoulders and arms off with the head)."""
    from hifipushie import base as basemod
    from hifipushie import humans
    from hifipushie.spec import expand_mirror
    sp = humans.spec(3, 0.0, skin=False, outfit_kind="none")
    s = expand_mirror(sp)
    sf = basemod.surface(s, s["base"])
    assert sf["graft"]["own_neck"]
    V = sf["verts"]
    wrist = np.array(s["joints"]["wrist.L"]["pos"])
    assert np.abs(V[:, 0]).max() > abs(wrist[0]), (np.abs(V[:, 0]).max(), wrist)
    assert (sf["src"] >= 0).all()  # no tube vertices: the template's own skin weights reach every vertex
    # an adult's followed head too; a head set apart from its body (`like`) keeps the tube
    b = {"body": {"source": "makehuman", "age": 30, "sex": 0.0}, "head": {"source": "gnm", "follow_body": True, "seed": 3, "like": {"age": 60}}}
    s2 = expand_mirror({"symmetry": True, "base": b, "joints": {}, "bones": {}, "blobs": {}})
    assert not basemod.surface(s2, s2["base"])["graft"].get("own_neck")


if __name__ == "__main__":
    test_references()
    if have():
        for fn in (test_children_have_their_age, test_adults_and_opt_out_unchanged, test_nipples_smoothed, test_dressed_by_default):
            fn()
    if have(gnm=True):
        test_child_head_keeps_the_bodys_neck()
    print("ok")
