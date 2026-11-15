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
    assert r["status"] == "FAIL" and '"seam": ["back.L:side", "front.L:side"]' in r["fix"], r["fix"]
    mv = json.loads(r["fix"].split("moves [", 1)[1].split("]. Form", 1)[0])
    assert -25 < mv["at"][0][1] < -15 and abs(mv["at"][0][0] - 300) < 15, mv  # (the chest crosses ~300 mm up)
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


def _three():
    """The tube with what s4-29's jacket had round its moved seam (F5b): the front's side seam bending in toward its
    armhole over its top (as jaeger's does), a canvas drawn on the front (its armhole points the front's own, its own
    cut line inside the side seam), and a third piece drafted in the front's frame beside it, sewn to the back's centre
    edge, two of its points 0.3 mm off the front's outline (jaeger's back beside its front)."""
    from hifipushie import pattern
    up = np.linspace(0, 1, 13)[1:-1]
    side = [(0.30 + 0.015 * np.sin(np.pi * t) - 0.03 * max(0.0, t - 0.8) / 0.2, 0.45 * t - 0.02 * max(0.0, t - 0.8) / 0.2)
            for t in up]  # (its last 2 points bend in toward the corner: the seam meets the armhole at ~35 degrees)
    arm = [(0.30 - 0.08 * t, 0.45 + 0.11 * t) for t in np.linspace(0, 1, 15)[1:-1]]
    F = [(0.0, 0.0), (0.30, 0.0)] + side + [(0.30, 0.45)] + arm + [(0.22, 0.56), (0.0, 0.60)]
    Bk = [(-x, y) for x, y in F]
    nF = {"cfHem": 0, "sideHem": 1, "armpit": 13, "shoulder": 27, "cfTop": 28}
    cv = F[13:29] + [(0.0, 0.25), (0.27, 0.25), (0.285, 0.40)]  # (armpit..shoulder, cfTop: the front's own points)
    c = [(0.3003, 0.0), (0.45, 0.0), (0.45, 0.60), (0.3003, 0.60), (0.3003, 0.45)]  # (sewn edge: 0 > 3 via 4)
    pcs = {"front.L": {"P": F, "names": dict(nF)}, "back.L": {"P": Bk, "names": dict(nF)},
           "canvas.L": {"P": cv, "names": {"armpit": 0, "shoulder": 14}},
           "c.L": {"P": c, "names": {"lo": 0, "hi": 3, "via": 4}}}
    for k, v in pcs.items():
        v.update(name=k, P=np.asarray(v["P"], float), wrap={"to": "torso"})
    tube = {"side": "sideHem>armpit", "arm": "armpit>shoulder", "hem": "cfHem>sideHem", "centre": "cfHem>cfTop"}
    arcs = {"front.L": dict(tube), "back.L": dict(tube), "c.L": {"edge": "lo>via>hi"}}
    ix = lambda e: pattern.arc_indices(pcs[e.split(":")[0]], arcs[e.split(":")[0]][e.split(":", 1)[1]])
    stops = {p: {pattern.index_of(pcs[p], n) for s in a.values() for n in (s.split(">")[0], s.split(">")[-1])}
             for p, a in arcs.items()}
    seams = [{"a": "front.L:side", "b": "back.L:side"}, {"a": "back.L:centre", "b": "c.L:edge"}]
    return pcs, ix, stops, seams


def test_a_move_keeps_every_girth_the_armhole_the_other_seams_and_takes_the_canvas_along():
    from hifipushie import draft_moves, pattern
    from hifipushie.draft_caught import _inside
    from hifipushie.draft_girths import width
    pcs, ix, stops, seams = _three()
    P0 = {k: np.asarray(v["P"], float).copy() for k, v in pcs.items()}
    L = lambda e: pattern.length(np.asarray(pcs[e.split(":")[0]]["P"])[ix(e)])
    arm0, other0 = L("front.L:arm") + L("back.L:arm"), L("back.L:centre") / L("c.L:edge")
    levels = np.linspace(0.02, 0.44, 22)
    girth = lambda: np.array([sum(width(np.asarray(pcs[p]["P"], float), np.array([0.0, y]), np.array([1.0, 0.0]))[0]
                                  for p in ("front.L", "back.L")) for y in levels])
    g0, LA = girth(), 1000 * L("front.L:side")
    rec = draft_moves.apply(pcs, ix, seams, [{"seam": ["front.L:side", "back.L:side"], "at": [[200, 0], [LA, -20]]}],
                            stops)
    assert abs(L("front.L:side") - L("back.L:side")) < 1e-4, rec  # (the moved seam sews)
    assert np.abs(girth() - g0).max() < 1e-3, np.round(1000 * (girth() - g0), 1)  # (what the back gains at a level
    # the front loses there: moved along each piece's normal, the bent top moved up as much as across, s4-29 chest +49)
    assert abs(L("front.L:arm") + L("back.L:arm") - arm0) < 5e-4, 1000 * (L("front.L:arm") + L("back.L:arm") - arm0)
    assert abs(L("back.L:centre") / L("c.L:edge") - other0) < 1e-4  # (the moved piece's other seam keeps its ease)
    assert np.abs(np.asarray(pcs["c.L"]["P"]) - P0["c.L"]).max() < 1e-9  # (a neighbour drafted in the front's frame
    # isn't a follower: s4-29's back was dragged, its side seam off by 14 mm and its sleeve link by 6)
    C, Fr = np.asarray(pcs["canvas.L"]["P"]), np.asarray(pcs["front.L"]["P"])
    assert rec[0]["followers"] == ["canvas.L"], rec  # (moved with the front: its corner on the front's new armhole
    # end, its own cut line still inside the front; s4-29: 23 mm outside)
    assert np.linalg.norm(C[0] - Fr[13]) < 1e-9 and _inside(C[16:], Fr).all(), (C[0], Fr[13], C[16:])


def test_the_chest_at_the_underarm_is_read_at_one_underarm_after_a_move():
    from hifipushie import draft_girths as dg, draft_moves, pattern
    pcs, ix, stops, seams = _three()
    B = {"pieces": pcs, "seams": [["front.L:sideHem>armpit", "back.L:sideHem>armpit"]]}
    holes = {p: ["armpit>shoulder"] for p in ("front.L", "back.L")}

    def chest():  # (as place reads it: each piece lowered to its armhole's lowest point, then one underarm)
        lines = {p: (np.array([0.0, float(np.asarray(pcs[p]["P"])[ix(p + ":arm"), 1].min()) - 1e-4]),
                     np.array([1.0, 0.0])) for p in holes}
        dg.one_underarm(B, lines, list(holes), holes)
        return sum(dg.width(np.asarray(pcs[p]["P"], float), *lines[p])[0] for p in holes), lines
    g0, _ = chest()
    LA = 1000 * pattern.length(np.asarray(pcs["front.L"]["P"])[ix("front.L:side")])
    draft_moves.apply(pcs, ix, seams, [{"seam": ["front.L:side", "back.L:side"], "at": [[200, 0], [LA, -20]]}], stops)
    g1, lines = chest()
    top = float(np.asarray(pcs["front.L"]["P"])[13, 1])  # (the front's new corner: its armhole's lowest point now)
    assert lines["front.L"][0][1] < top - 0.005, (top, lines)  # (read per piece, the front at its raised corner:
    # s4-29 chest +19 mm)
    assert abs(g1 - g0) < 3e-3, (g0, g1, lines)  # (within the corner's own few mm: the strip turns with the seam)
