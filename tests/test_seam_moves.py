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


def _tube():
    """Two panels a side of a tube: front.L (0.30 wide) and back.L (0.30), each in its own frame, sewn at the side
    (a curved seam, its top on a slanted armhole) and at a centre seam; a chest level at y 0.30."""
    from hifipushie import pattern
    up = np.linspace(0, 1, 13)[1:-1]
    side = [(0.30 + 0.015 * np.sin(np.pi * t), 0.45 * t) for t in up]  # (bulging out at the waist)
    arm = [(0.30 - 0.08 * t, 0.45 + 0.11 * t) for t in np.linspace(0, 1, 15)[1:-1]]  # (dense, as a drafted curve)
    F = [(0.0, 0.0), (0.30, 0.0)] + side + [(0.30, 0.45)] + arm + [(0.22, 0.56), (0.0, 0.60)]
    Bk = [(-x, y) for x, y in F]  # (the back: the front mirrored, its own frame)
    nF = {"cfHem": 0, "sideHem": 1, "armpit": 13, "shoulder": 27, "cfTop": 28}
    front = {"name": "front.L", "P": np.asarray(F, float), "names": dict(nF), "wrap": {"to": "torso"}}
    back = {"name": "back.L", "P": np.asarray(Bk, float), "names": dict(nF), "wrap": {"to": "torso"}}
    arcs = {"side": "sideHem>armpit", "centre": "cfHem>cfTop", "arm": "armpit>shoulder"}
    B = {"pieces": {"front.L": front, "back.L": back},
         "seams": [["front.L:sideHem>armpit", "back.L:sideHem>armpit"], ["front.L:cfHem>cfTop", "back.L:cfHem>cfTop"]],
         "edge_arcs": {"front.L": dict(arcs), "back.L": dict(arcs)}}
    ix = lambda e: pattern.arc_indices(B["pieces"][e.split(":")[0]], arcs[e.split(":", 1)[1]])
    return B, ix


def _panels(B, monkeypatch, front_share):
    from hifipushie import draft_girths as dg, draft_panels, tape_geom
    line = (np.array([0.0, 0.30]), np.array([1.0, 0.0]))
    ring = set(B["pieces"])
    monkeypatch.setattr(tape_geom, "tapes", lambda s3: {"chest": {"kind": "loop"}})
    monkeypatch.setattr(draft_panels, "_widths", lambda B_, d, T, g: [
        (ring, {p: dg.width(np.asarray(B_["pieces"][p]["P"]), *line)[0] for p in ring}, {}, {p: line for p in ring})])
    plan = {"panels": [{"girth": "chest", "shares": {"front": {"source": "convention", "share": front_share},
                                                     "back": {"source": "convention", "share": 1 - front_share}}}]}
    return draft_panels.rows(B, plan, {}, {})[0]


def test_a_seam_moved_20mm_at_the_chest_still_sews_and_the_panels_row_passes(monkeypatch):
    import json
    from hifipushie import draft_moves, pattern
    B, ix = _tube()
    seams = [{"a": "front.L:side", "b": "back.L:side"}, {"a": "front.L:centre", "b": "back.L:centre"}]
    L = lambda e: pattern.length(np.asarray(B["pieces"][e.split(":")[0]]["P"])[ix(e)])
    arm0 = L("front.L:arm") + L("back.L:arm")
    r = _panels(B, monkeypatch, 0.32 / 0.60)  # (front 300 mm where the plan wants 320: 20 mm a piece too narrow)
    assert r["status"] == "FAIL" and '"seam": ["front.L:side", "back.L:side"]' in r["fix"], r["fix"]
    mv = json.loads(r["fix"].split("moves [", 1)[1].split("]. Form", 1)[0])
    assert 15 < mv["at"][0][1] < 25 and abs(mv["at"][0][0] - 300) < 15, mv  # (the chest crosses ~300 mm up)
    rec = draft_moves.apply(B["pieces"], ix, seams, [{"seam": mv["seam"], "at": mv["at"]}])
    assert abs(L("front.L:side") - L("back.L:side")) < 1e-4, rec  # (the seam still sews: one length both sides)
    assert abs(L("front.L:arm") + L("back.L:arm") - arm0) < 0.02 * arm0  # (the armhole: what one loses the other
    # gains, but for the corner the respaced points cut: within the cap ease tolerance)
    r = _panels(B, monkeypatch, 0.32 / 0.60)
    assert r["status"] == "PASS", r


def test_a_move_names_one_declared_seam():
    import pytest
    from hifipushie import draft_moves
    B, ix = _tube()
    with pytest.raises(draft_moves.Refused, match="aren't one declared seam"):
        draft_moves.apply(B["pieces"], ix, [], [{"seam": ["front.L:side", "back.L:side"], "at": [[0, 10]]}])
