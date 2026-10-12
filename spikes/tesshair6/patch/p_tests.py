"""p_tests.py: (applied once) tests/test_hair_flow.py for round six: the soft tousle, the front word."""
from pathlib import Path

p = Path(__file__).resolve().parents[3] / "tests/test_hair_flow.py"
s = p.read_text()


def rep(a, b):
    global s
    assert s.count(a) == 1, (s.count(a), a[:70])
    s = s.replace(a, b)


rep('''    assert 0.6 < min(L) / max(L) < 0.92  # an uneven end, no lock half the length''',
    '''    assert 0.52 < min(L) / max(L) < 0.92  # an uneven end, no lock half the length''')
rep('''    for lk in Y1:
        assert 1 <= lk["hairs"] <= 4 and lk["width"] <= 0.004 and lk["free"] == 1.0
''', '''    for lk in Y1:
        # (single hairs and, tesshair6, a few THIN soft locks of 7-15 hairs)
        assert (1 <= lk["hairs"] <= 4 and lk["width"] <= 0.004 or 7 <= lk["hairs"] <= 15 and lk["width"] <= 0.009) and lk["free"] == 1.0
    assert sum(lk["hairs"] <= 4 for lk in Y1) > 0.6 * len(Y1) and any(lk["hairs"] >= 7 for lk in Y1)
    for lk in Y1:
''')
rep('''    assert tl1["in_step"] > 0.5
''', '''    assert tl0["in_step"] > 0.5 and tl1["in_step"] >= 0.35
''')
rep('''def test_sideburn_grows_no_lock_to_the_tie():''', '''def test_tousle_is_soft_not_straw():
    """tesshair6 (th_T56's tail: "shorter, stiff straw kicking out backwards"; round four's th_T48 hung, full and
    wavy): the tousle no longer points the locks, flicks them out or clumps their strands. It is `soft`: locks
    loosened out of the bundle, open ends, fine strands at a higher count, longer strays; the hang is the brushed
    tail's."""
    st = lambda to: hf.style({"tail": {"length": 0.22, "fullness": 0.5, "wave": 0.6, "tousle": to}})  # noqa: E731
    a, b = st(0.0), st(0.8)
    ta, tb = a["tie"]["tail"], b["tie"]["tail"]
    assert ta["flick"] == tb["flick"]  # no kick of its own
    assert tb["soft"] > 0.9 > 0.2 > ta["soft"]
    assert tb["strands"]["clump"] <= ta["strands"]["clump"] and tb["strands"]["tip_spread"] >= 0.6  # open, soft ends
    assert tb["strands"]["fine"] > ta["strands"]["fine"] and tb["strands"]["density"] > ta["strands"]["density"] + 0.5
    assert tb["stray_length"][1] >= 0.14 and tb["strays"] > 2 * ta["strays"]
    assert b["strands"]["free"]["clump_shape"] == a["strands"]["free"]["clump_shape"]  # not pointed wisps
    # the locks: no pointed taper, some loosened out of the bundle (the outline is irregular), none stiffly straight up
    def grow(to):
        sc, g, line, locks = _grow({"tail": {"length": 0.22, "fullness": 0.5, "wave": 0.6, "tousle": to}})
        return sc, [lk for k, lk in locks.items() if k.startswith("tt")], [lk for k, lk in locks.items() if k.startswith("ty")]
    sc, T0, _ = grow(0.0)
    _, T1, Y1 = grow(0.8)
    assert max(lk["taper"] for lk in T1) <= 0.4
    ends = lambda T: np.array([_world(sc, lk)[-1] for lk in T])  # noqa: E731
    spread = lambda T: float(np.linalg.norm(ends(T)[:, :2] - ends(T)[:, :2].mean(0), axis=1).std())  # noqa: E731
    assert spread(T1) > spread(T0)  # an irregular outline at the end
    for lk in T1:  # it hangs: every lock ends below where it starts
        P = _world(sc, lk)
        assert P[-1, 2] < P[0, 2] - 0.05
    L = [float(np.linalg.norm(np.diff(_world(sc, lk), axis=0), axis=1).sum()) for lk in Y1]
    assert max(L) > 0.1  # strays long enough to leave the outline
    assert ht.TIE["tail"]["soft"] == 0.0  # a raw tie is unchanged


def test_front_is_looser_than_the_rest():
    """tesshair6 (Tess: "hers drapes loosely over the forehead corners and temples with visible loosened locks from
    the FRONT view; ours is a neat held-back arc"): the style word `front` loosens the hair in front of the ears
    only, lets it hang over the forehead's corners, and adds thick locks that swoop from beside the part across the
    corner and tuck back. The back of the head and a style without the word are unchanged."""
    base = {"tie": "low", "tightness": 0.85, "neatness": 0.95, "wisps": 0.6}
    s0, s1 = hf.style(base), hf.style({**base, "front": {"looseness": 0.6, "drape": 0.6}})
    assert "front" not in s0["tie"]["gather"] and "swoop" not in s0["tie"]["wisps"]
    assert s1["tie"]["gather"]["front"]["loose"] > 0.4 and s1["tie"]["gather"]["front"]["drape"] == 0.6
    assert s1["tie"]["gather"]["sag"] == s0["tie"]["gather"]["sag"]  # the head's own tightness is kept
    assert s1["tie"]["wisps"]["swoop"] == 2 and s1["tie"]["wisps"]["count"] > s0["tie"]["wisps"]["count"]
    assert s1["strands"]["wisp"]["thickness"] > s0["strands"]["wisp"]["thickness"]
    assert hf.style({**base, "front": 0.5})["tie"]["gather"]["front"]["drape"] == 0.5
    assert hf.style({**base, "tie": "high", "front": 0.8})["tie"]["wisps"].get("swoop") is None  # none toward a high tie
    try:
        hf.style({**base, "front": {"loosness": 1}})
        raise AssertionError("accepted a wrong key")
    except ValueError as e:
        assert "looseness" in str(e)
    sc, g, line, L0 = _grow(base)
    _, _, _, L1 = _grow({**base, "front": {"looseness": 0.7, "drape": 0.7}})

    def low(locks, front):
        """Mean depth (deg) the gather's ways dip below ... no: their lowest elevation over the first half, by side."""
        out = []
        for k, lk in locks.items():
            if not k.startswith("tg"):
                continue
            P = np.asarray(lk["pts"], float)
            fa = abs(((P[0, 0] + 180) % 360) - 180)
            if (fa < 50) == front and (front or fa > 120):
                out.append(P[:6, 1].min() - P[0, 1])
        return float(np.mean(out))
    assert low(L1, True) < low(L0, True) - 1.0  # the front's ways hang lower after their roots
    assert abs(low(L1, False) - low(L0, False)) < 0.7  # the back's do not
    sw = {k: lk for k, lk in L1.items() if k.startswith("tws")}
    assert len(sw) == 4 and not any(k.startswith("tws") for k in L0)
    for k, lk in sw.items():
        P = _world(sc, lk) - sc.C
        az0 = abs(np.degrees(np.arctan2(P[0, 0], -P[0, 1])))
        az1 = abs(np.degrees(np.arctan2(P[-1, 0], -P[-1, 1])))
        assert az0 < 35 and az1 > az0 + 25, (k, az0, az1)  # from beside the part out to the temple and back
        assert P[:, 2].min() < P[0, 2] - 0.015 and lk["hairs"] >= 30 and lk["width"] >= 0.009
        assert np.sign(P[-1, 0]) == np.sign(P[0, 0])  # on its own side


def test_sideburn_grows_no_lock_to_the_tie():''')
p.write_text(s)
print("ok")
