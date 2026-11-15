"""F5 (t s4-29): the armhole depth read along the whole armhole chain; a seam moved between two sewn pieces."""
import numpy as np

from hifipushie import draft_shape as ds


def _pc(name, P, names, to="torso"):
    return {"name": name, "P": np.asarray(P, float), "names": names, "wrap": {"to": to}}


def _sleeve():
    sq = [[0, 0], [0.1, 0], [0.1, -0.12], [0, -0.12]]  # cap 120 mm high, edge a>b>c
    return _pc("top", sq, {"a": 0, "b": 1, "c": 2, "d": 3}, "arm.L")


def test_a_side_body_taking_the_underarm_reads_the_two_piece_bodys_depth():
    # two-piece: front and back armholes from the shoulder (y 0) down to the underarm (y -0.20)
    front = _pc("front", [[0, 0], [0.04, -0.12], [0.10, -0.20], [0.10, -0.60], [-0.2, -0.6], [-0.2, 0]],
                {"sh": 0, "pitch": 1, "ua": 2})
    back = _pc("back", [[0, 0], [-0.04, -0.12], [-0.10, -0.20], [-0.10, -0.60], [0.2, -0.6], [0.2, 0]],
               {"sh": 0, "pitch": 1, "ua": 2})
    two = {"pieces": {"top": _sleeve(), "front": front, "back": back},
           "seams": [["top:a>b>c", ["front:sh>pitch>ua", "back:ua>pitch>sh"]]]}
    d2 = ds.armhole_depth(two, ["front:sh>pitch>ua", "back:ua>pitch>sh"])
    # three-piece: the side body takes the underarm; front and back armholes stop 60 mm above it; the side body is in
    # its OWN frame (shifted 0.5 m), as a FreeSewing part is
    f3 = _pc("front", [[0, 0], [0.04, -0.12], [0.06, -0.14], [0.06, -0.60], [-0.2, -0.6], [-0.2, 0]],
             {"sh": 0, "pitch": 1, "cut": 2})
    b3 = _pc("back", [[0, 0], [-0.04, -0.12], [-0.06, -0.14], [-0.06, -0.6], [0.2, -0.6], [0.2, 0]],
             {"sh": 0, "pitch": 1, "cut": 2})
    side = _pc("side", np.array([[0, -0.14], [0.04, -0.20], [0.08, -0.14], [0.08, -0.6], [0, -0.6]]) + [0, 0.5],
               {"f": 0, "ua": 1, "b": 2})
    chain = ["front:sh>pitch>cut", "side:f>ua>b", "back:cut>pitch>sh"]
    three = {"pieces": {"top": _sleeve(), "front": f3, "back": b3, "side": side}, "seams": [["top:a>b>c", chain]]}
    d3 = ds.armhole_depth(three, chain)
    assert abs(d2 - 0.20) < 1e-9 and abs(d3 - d2) < 1e-9, (d2, d3)
    r2, r3 = ds.cap_rows(two, {}, {}), ds.cap_rows(three, {}, {})
    assert "armhole depth 200 mm" in r2["value"] and "armhole depth 200 mm" in r3["value"], (r2["value"], r3["value"])
    assert r3["status"] == r2["status"] == "PASS"  # (read per piece, the three-piece body read the front's 140 mm)
