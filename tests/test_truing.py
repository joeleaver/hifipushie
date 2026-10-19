"""Known answers for pattern truing (dress-garrett 2026-10-19: Garrett's jacket and shirt necklines met the shoulder seam
at 125 / 118 deg, the sewn neckline turned 44 / 31 deg at the side neck and both collars kinked there; Joe saw it).
cloth_check.junctions measures every seam end's joined turn; pattern.true_corner (alteration op "true") trues one.
Run: uv run python tests/test_truing.py"""
import math
import sys

import numpy as np

from hifipushie import cloth_check as cc, pattern


def _pc(P, names):
    return {"name": "x", "P": np.asarray(P, float), "names": names, "marks": {}, "wrap": {}, "lines": {}}


def _shoulder_pair(front_deg=125.0):
    """A back and a front sewn along a shoulder seam on y = 0 (hps at x = 0, shoulder at x = 0.12); the back's neckline
    leaves the hps at 90 deg (straight down -y, then curving), the front's at `front_deg` (interior), both 0.15 m long."""
    a = math.radians(front_deg)
    # front above the seam: hps (0,0) -> shoulder (0.12,0) -> (0.12,0.2) -> neckline back to hps, leaving hps at angle a
    # the neckline from its far end (0.15 m out) back to the hps, sampled every 10 mm; the outline closes over it
    neck = [[0.15 * (1 - t) * math.cos(a), 0.15 * (1 - t) * math.sin(a)] for t in np.linspace(0, 1, 16)[:-1]]
    F = np.r_[[[0.0, 0.0], [0.12, 0.0], [0.12, 0.2], [0.15 * math.cos(a), 0.2]], neck]
    Bk = np.asarray([[0.0, 0.0], [0.0, -0.15], [0.12, -0.2], [0.12, 0.0]], float)
    return {"pieces": {"front": _pc(F, {"hps": 0, "shoulder": 1}), "back": _pc(Bk, {"hps": 0, "shoulder": 3})},
            "seams": [["front:hps>shoulder", "back:hps>shoulder"]]}


def test_junctions_selftest():
    cc._selftest_junctions()


def test_true_corner_known_answer():
    """A front neckline leaving the shoulder seam at 125 deg, the back at 90: the joined neckline turns 35 deg at the
    HPS. True the front ("true", at hps, keep shoulder, 90 deg, blend 40 mm): it meets at 90 +- 1, the joined turn is
    < 2 deg, the shoulder seam does not move, and the neckline past the blend is untouched."""
    B = _shoulder_pair(125.0)
    h0 = next(r for r in cc.junctions(B) if "hps" in r["at"])
    print(f"before: front {h0['deg_a']} back {h0['deg_b']} turn {h0['turn_deg']}")
    assert abs(h0["turn_deg"] - 35.0) < 2.0, h0
    P0 = B["pieces"]["front"]["P"].copy()
    B2 = {"pieces": pattern.apply(B["pieces"], [{"op": "true", "piece": "front", "at": "hps", "keep": "shoulder",
                                                 "deg": 90, "blend": 0.04}]), "seams": B["seams"]}
    P1 = B2["pieces"]["front"]["P"]
    h1 = next(r for r in cc.junctions(B2) if "hps" in r["at"])
    print(f"after: front {h1['deg_a']} back {h1['deg_b']} turn {h1['turn_deg']}")
    assert abs(h1["deg_a"] - 90.0) < 1.0 and h1["turn_deg"] < 2.0, h1
    assert np.allclose(P1[:3], P0[:3])  # (hps, shoulder, the far corner)
    far = np.linalg.norm(P0 - P0[0], axis=1) > 0.045
    assert np.allclose(P1[far], P0[far]), "past the blend the neckline moved"


def test_true_then_match_walks_the_seam():
    """WALK THE SEAM (dress-garrett 2026-10-19 order + seam lengths): truing bends a neckline, which changes its length
    (with the curve past the blend fixed it can't keep it: a straight edge bent at one end only gets longer). The
    shirt's trued neckline grew 9.3 mm and its stand read 2.4% short (cloth_check.seams band row FAIL, the gate's
    "seams" row). Known answer: a band sewn to the 125 deg front's neckline reads 0 ease before, short after "true",
    and 0 +- 0.1 mm after "match" (the band spread parallel at its middle by what it lacks)."""
    B = _shoulder_pair(125.0)
    fr = B["pieces"]["front"]
    neck = np.r_[fr["P"][4:], fr["P"][:1]]  # (the neckline, far end -> hps)
    L = float(np.linalg.norm(np.diff(neck, axis=0), axis=1).sum())
    fr["names"].update({"neckEnd": 4})
    band = _pc([[0, 0], [L, 0], [L, 0.03], [0, 0.03]], {"bl": 0, "br": 1, "tr": 2, "tl": 3})
    band["marks"] = {"midB": np.array([L / 2, 0.0]), "midT": np.array([L / 2, 0.03])}
    B["pieces"]["band"] = band
    B["seams"].append(["band:bl>br", "front:neckEnd>hps"])
    row = lambda Bp: next(r for r in cc.seams(Bp) if r["a"] == "band:bl>br")
    r0 = row(B)
    tr = {"op": "true", "piece": "front", "at": "hps", "keep": "shoulder", "deg": 90, "blend": 0.04}
    B1 = {"pieces": pattern.apply(B["pieces"], [tr]), "seams": B["seams"]}
    r1 = row(B1)
    mt = {"op": "match", "piece": "band", "edge": "band:bl>br", "to": ["front:neckEnd>hps"], "line": ["midB", "midT"]}
    B2 = {"pieces": pattern.apply(B["pieces"], [tr, mt]), "seams": B["seams"]}
    r2 = row(B2)
    print(f"band vs neckline: before true {r0['len_a_mm']} / {r0['len_b_mm']}, after true {r1['len_a_mm']} / "
          f"{r1['len_b_mm']}, after match {r2['len_a_mm']} / {r2['len_b_mm']} mm")
    assert abs(r0["len_a_mm"] - r0["len_b_mm"]) < 0.1
    assert r1["len_b_mm"] - r1["len_a_mm"] > 1.0, r1  # (the fault: truing lengthened the neckline)
    assert abs(r2["len_a_mm"] - r2["len_b_mm"]) < 0.1, r2


def test_junctions_chained_and_crossings():
    """(coordinator 2026-10-19, round 4) The truing row failed non-faults: Garrett's jacket underarm read 112 deg (a
    set-in cap is a CLOSED loop of chained seams, 'under:underarm>usF + top:tsF>tsB + under:usB>underarm': it has no
    ends) and seam crossings (a shirt cap's end at the underarm, where the sleeve seam and side seam cross). Known
    answers: (1) a sleeve cap chained of two edges all round an armhole chained of two pieces gives no truing rows;
    (2) two panels sewn side by side under one top band: the side seam's top end is read (both necklines in the band
    seam, 0 deg); its bottom end, where only one panel has a hem band and the other's corner is skewed 30 deg, is a
    CROSSING, reported and not failed."""
    a = _pc([[0, 0], [1, 0], [1, 1], [0, 1]], {"bl": 0, "br": 1, "tr": 2, "tl": 3})
    b = _pc([[1, 0], [2, -0.6], [2, 1], [1, 1]], {"bl": 0, "br": 1, "tr": 2, "tl": 3})  # (bottom edge skewed)
    top = _pc([[0, 1], [2, 1], [2, 1.1], [0, 1.1]], {"bl": 0, "br": 1, "tr": 2, "tl": 3})
    hem = _pc([[0, -0.1], [1, -0.1], [1, 0], [0, 0]], {"bl": 0, "br": 1, "tr": 2, "tl": 3})
    # a sleeve loop: its own two edges all round the two panels' outer sides (chained, closed on the sleeve)
    sl = _pc([[0, 0], [1, 0], [1, 1], [0, 1]], {"u": 0, "f": 1, "t": 2, "bk": 3})
    Bp = {"pieces": {"a": a, "b": b, "top": top, "hem": hem, "sleeve": sl},
          "seams": [["a:br>tr", "b:bl>tl"], ["top:bl>br", ["a:tl>tr", "b:tl>tr"]], ["hem:tl>tr", "a:bl>br"],
                    [["sleeve:u>f>t", "sleeve:t>bk>u"], ["a:tl>bl", "b:br>tr"]]]}
    r = cc.junctions(Bp)
    for x in r:
        print(f"  {x['at']}: {x['deg_a']} + {x['deg_b']} -> {x['turn_deg']} crossing {x['crossing']} ok {x['ok']}")
    assert not any("sleeve" in x["at"] for x in r), "a closed loop has no ends"
    topend = next(x for x in r if x["at"] == "a:tr | b:tl")
    assert topend["turn_deg"] < 1.0 and not topend["crossing"], topend
    bot = next(x for x in r if x["at"] == "a:br | b:bl")
    assert bot["crossing"] and bot["ok"] and bot["turn_deg"] > 10.0, bot


if __name__ == "__main__":
    fails = 0
    for k, f in list(globals().items()):
        if k.startswith("test_") and callable(f):
            try:
                f()
                print("PASS", k)
            except Exception as ex:  # noqa: BLE001
                fails += 1
                import traceback
                traceback.print_exc()
                print("FAIL", k, ex)
    sys.exit(1 if fails else 0)
