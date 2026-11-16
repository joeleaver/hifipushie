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
    lv = [a for a in mv["at"] if 15 < a[0] < 440]
    assert len(lv) == 1 and -25 < lv[0][1] < -15 and abs(lv[0][0] - 300) < 15, mv  # (the chest crosses ~300 mm up)
    assert [mv["at"][0], mv["at"][-1][1]] == [[0, 0], 0], mv  # (F6: both ends stated, each farther than 3 x the move
    # from the level: the move tapers out before them)
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
    dg = np.abs(girth() - g0)
    assert dg[levels < 0.415].max() < 1e-6 and dg.max() < 2e-3, np.round(1000 * (girth() - g0), 1)  # (what the back
    # gains at a level the front loses there: moved along each piece's normal, the bent top moved up as much as across,
    # s4-29 chest +49; the last 2 cm under the end: the run on to where the end slid along the armhole)
    assert abs(L("front.L:arm") + L("back.L:arm") - arm0) < 5e-4, 1000 * (L("front.L:arm") + L("back.L:arm") - arm0)
    assert abs(L("back.L:centre") / L("c.L:edge") - other0) < 1e-4  # (the moved piece's other seam keeps its ease)
    assert np.abs(np.asarray(pcs["c.L"]["P"]) - P0["c.L"]).max() < 1e-9  # (a neighbour drafted in the front's frame
    # isn't a follower: s4-29's back was dragged, its side seam off by 14 mm and its sleeve link by 6)
    C, Fr = np.asarray(pcs["canvas.L"]["P"]), np.asarray(pcs["front.L"]["P"])
    assert rec[0]["followers"] == ["canvas.L"], rec  # (moved with the front: its corner on the front's new armhole
    # end, its own cut line still inside the front; s4-29: 23 mm outside)
    i = pcs["front.L"]["names"]["armpit"]  # (F6: the front's new corner, slid up its armhole)
    assert np.linalg.norm(C[0] - Fr[i]) < 1e-9 and _inside(C[16:], Fr).all(), (C[0], Fr[i], C[16:])


def test_the_chest_at_the_underarm_is_read_at_one_underarm_after_a_move():
    from hifipushie import draft_girths as dg, draft_moves, pattern
    pcs, ix, stops, seams = _three()
    B = {"pieces": pcs, "seams": [["front.L:sideHem>armpit", "back.L:sideHem>armpit"]]}
    holes = {p: [("armpit>shoulder", {"sleeve.L"})] for p in ("front.L", "back.L")}

    def chest():  # (as place reads it: levels above the armholes: taken at one underarm)
        lines = {p: (np.array([0.0, 0.5]), np.array([1.0, 0.0])) for p in (*holes, "sleeve.L")}
        dg.at_underarm(B, lines, holes)
        return sum(dg.width(np.asarray(pcs[p]["P"], float), *lines[p])[0] for p in holes), lines
    g0, _ = chest()
    LA = 1000 * pattern.length(np.asarray(pcs["front.L"]["P"])[ix("front.L:side")])
    draft_moves.apply(pcs, ix, seams, [{"seam": ["front.L:side", "back.L:side"], "at": [[200, 0], [LA, -20]]}], stops)
    g1, lines = chest()
    top = float(np.asarray(pcs["front.L"]["P"])[pcs["front.L"]["names"]["armpit"], 1])  # (the front's new corner: its armhole's lowest point now)
    assert lines["front.L"][0][1] < top - 0.005, (top, lines)  # (read per piece, the front at its raised corner:
    # s4-29 chest +19 mm)
    assert abs(g1 - g0) < 4e-3, (g0, g1, lines)  # (within the corner's own few mm: the run turns with the seam, F6: slid along the armhole)


def _torso3():
    """Front, side body, back (F5c, s4-29's jacket): the front's and back's armholes end at corners 30 mm above the side
    body's, which dips in a U between them (its lowest point the underarm); a sleeve sewn into all three."""
    from hifipushie import pattern
    U = [(0.25 + 0.12 * t, 0.45 - 0.03 * np.sin(np.pi * t)) for t in np.linspace(0, 1, 13)]
    pcs = {"front.L": [(0.0, 0.0), (0.25, 0.0), (0.25, 0.225), (0.25, 0.45), (0.21, 0.52), (0.17, 0.56), (0.0, 0.60)],
           "side.L": [(0.25, 0.0), (0.37, 0.0), (0.37, 0.225), (0.37, 0.45)] + U[::-1][1:-1] + [(0.25, 0.45),
                                                                                                    (0.25, 0.225)],
           "back.L": [(0.37, 0.0), (0.62, 0.0), (0.62, 0.62), (0.45, 0.58), (0.41, 0.52), (0.37, 0.45), (0.37, 0.225)],
           "sleeve.L": [(0.0, 0.0), (0.3, 0.0), (0.3, -0.5), (0.0, -0.5)]}
    nm = {"front.L": {"hem": 0, "side": 1, "armpit": 3, "shoulder": 5, "cf": 6},
          "side.L": {"fhem": 0, "bhem": 1, "barm": 3, "farm": 15},
          "back.L": {"bhem": 0, "cb": 1, "cbTop": 2, "shoulder": 3, "armpit": 5},
          "sleeve.L": {"a": 0, "b": 1, "c": 2, "d": 3}}
    for k in pcs:
        pcs[k] = {"name": k, "P": np.asarray(pcs[k], float), "names": nm[k],
                  "wrap": {"to": "arm.L" if k == "sleeve.L" else "torso"}}
    arcs = {"front.L:side": "side>armpit", "side.L:front": "fhem>farm", "side.L:back": "bhem>barm",
            "back.L:side": "bhem>armpit", "front.L:arm": "armpit>shoulder", "side.L:arm": "barm>farm",
            "back.L:arm": "shoulder>armpit"}
    ix = lambda e: pattern.arc_indices(pcs[e.split(":")[0]], arcs[e])
    B = {"pieces": pcs, "seams": [["front.L:side>armpit", "side.L:fhem>farm"], ["side.L:bhem>barm", "back.L:bhem>armpit"],
                                  ["front.L:armpit>shoulder", "sleeve.L:a>b"], ["side.L:barm>farm", "sleeve.L:b>c"],
                                  ["back.L:shoulder>armpit", "sleeve.L:c>d"]]}
    return B, ix


def _chest3(B, own):
    """{piece: level} as place reads it from each piece's own length-tape level `own`, and the chest round them."""
    from hifipushie import draft_girths as dg
    lines = {p: (np.array([0.0, y]), np.array([1.0, 0.0])) for p, y in own.items()}
    dg.at_underarm(B, lines, dg.holes(B))
    pcs = B["pieces"]
    return ({p: float(lines[p][0][1]) for p in own},
            sum(dg.width(np.asarray(pcs[p]["P"], float), *lines[p])[0] for p in ("front.L", "side.L", "back.L")))


def test_a_spiked_armhole_corner_is_read_at_the_loops_underarm_not_its_corner():
    B, _ = _torso3()
    # the front's tape level cuts its armhole; the side body's and back's own levels sit below their armholes (as in
    # s4-29's unmoved draft, where F5b read the front at its corner, 34 mm loose)
    lv, _ = _chest3(B, {"front.L": 0.47, "side.L": 0.41, "back.L": 0.43, "sleeve.L": -0.1})
    for p in ("front.L", "side.L", "back.L"):
        assert abs(lv[p] - 0.42) < 1e-3, lv  # (all three at the side body's underarm, 30 mm below the corners)
    lv, _ = _chest3(B, {"front.L": 0.30, "side.L": 0.30, "back.L": 0.30, "sleeve.L": -0.1})
    assert all(abs(lv[p] - 0.30) < 1e-9 for p in ("front.L", "side.L", "back.L")), lv  # (a girth below every armhole
    # (a waist) keeps each piece's own level)


def test_the_same_draft_reads_the_same_chest_before_and_after_a_zero_length_move():
    from hifipushie import draft_moves
    B, ix = _torso3()
    own = {"front.L": 0.47, "side.L": 0.41, "back.L": 0.43, "sleeve.L": -0.1}
    _, g0 = _chest3(B, own)
    stops = {p: {i for i in B["pieces"][p]["names"].values()} for p in ("front.L", "side.L", "back.L")}
    draft_moves.apply(B["pieces"], ix, [{"a": "front.L:side", "b": "side.L:front"}],
                      [{"seam": ["front.L:side", "side.L:front"], "at": [[0, 0], [450, 0]]}], stops)
    _, g1 = _chest3(B, own)
    _, g2 = _chest3(B, dict(own, **{"side.L": 0.425}))  # (a move that raised the side body's top raises its own
    # level above its armhole (s4-29's moved draft): the side lowered too, the chest the same)
    assert abs(g1 - g0) < 1e-6 and abs(g2 - g0) < 1e-6, (g0, g1, g2)


def _u_body():
    """Front, a 50 mm side body, back in one frame (F6, s4-30's jaeger): one smooth armhole, a circle round the
    underarm, the side body taking only its bottom (seam tops 32 mm above the chest at y 0.40)."""
    from hifipushie import pattern
    cx, cy, r = 0.275, 0.56, 0.13
    arc = lambda a, b, n: [(cx + r * np.sin(t), cy - r * np.cos(t)) for t in np.linspace(a, b, n)]
    tf, tb = np.arcsin(-0.025 / r), np.arcsin(0.025 / r)
    up = lambda x: [(x, y) for y in np.linspace(0.0, cy - r * np.cos(tf), 30)]
    F = [(0.0, 0.0)] + up(0.25) + arc(tf, -1.2, 40)[1:] + [(0.10, 0.60), (0.0, 0.60)]
    S = up(0.25)[::-1] + up(0.30) + arc(tf, tb, 9)[1:-1][::-1]
    Bk = up(0.30)[::-1] + [(0.55, 0.0), (0.55, 0.62), (0.45, 0.62)] + arc(1.2, tb, 40)[:-1]
    pcs = {"front.L": (F, {"cf": 0, "hem": 1, "pit": 30, "sh": 69, "top": 71}),
           "side.L": (S, {"ftop": 0, "fhem": 29, "bhem": 30, "btop": 59}),
           "back.L": (Bk, {"btop": 0, "bhem": 29, "cb": 30, "cbTop": 31, "sh": 32, "pit": 71})}
    pcs = {k: {"name": k, "P": np.asarray(P, float), "names": n, "wrap": {"to": "torso"}} for k, (P, n) in pcs.items()}
    arcs = {"front.L": {"side": "hem>pit", "arm": "pit>sh"}, "side.L": {"front": "fhem>ftop", "back": "bhem>btop",
                                                                      "arm": "ftop>btop"},
            "back.L": {"side": "bhem>btop", "arm": "sh>pit"}}
    ix = lambda e: pattern.arc_indices(pcs[e.split(":")[0]], arcs[e.split(":")[0]][e.split(":", 1)[1]])
    stops = {p: {pattern.index_of(pcs[p], n) for s in a.values() for n in (s.split(">")[0], s.split(">")[-1])}
             for p, a in arcs.items()}
    seams = [{"a": "front.L:side", "b": "side.L:front"}, {"a": "side.L:back", "b": "back.L:side"}]
    return pcs, ix, stops, seams


def _turn(E):
    d = np.diff(E, axis=0)
    a = np.arctan2(d[:, 1], d[:, 0])
    return np.degrees(np.abs((np.diff(a) + np.pi) % (2 * np.pi) - np.pi))


def test_a_side_body_widened_70mm_at_the_underarm_re_splits_the_armhole(monkeypatch):
    from hifipushie import draft_girths as dg, draft_moves, draft_panels, pattern, tape_geom
    pcs, ix, stops, seams = _u_body()
    L = lambda e: pattern.length(np.asarray(pcs[e.split(":")[0]]["P"])[ix(e)])
    arms = ("front.L:arm", "side.L:arm", "back.L:arm")
    arm0, turn0 = sum(L(e) for e in arms), _turn(np.asarray(pcs["front.L"]["P"])[ix("front.L:arm")]).max()
    ys = {"chest": 0.40, "waist": 0.25, "hips": 0.05}
    girth = lambda y: sum(dg.width(np.asarray(pcs[p]["P"], float), np.array([0.0, y]), np.array([1.0, 0.0]))[0]
                          for p in ("front.L", "side.L", "back.L"))
    g0 = {k: girth(y) for k, y in ys.items()}
    top = 1000 * L("front.L:side")
    rec = draft_moves.apply(pcs, ix, seams, [  # (the side body grows 35 mm a side at the underarm, tapering to the hips)
        {"seam": ["front.L:side", "side.L:front"], "at": [[50, 0], [top - 32, -35], [top, -35]]},
        {"seam": ["side.L:back", "back.L:side"], "at": [[50, 0], [top - 32, 35], [top, 35]]}], stops)
    assert all(abs(r["off_mm"]) < 0.1 for r in rec), rec  # (both seams still sew)
    assert abs(sum(L(e) for e in arms) - arm0) < 5e-4, 1000 * (sum(L(e) for e in arms) - arm0)  # (the curve the
    # sleeve is set into: what the front and back gave, the side body took)
    assert L("side.L:arm") - 0.05 > 0.069, L("side.L:arm")  # (it took 35 mm of each)
    for k, y in ys.items():
        assert abs(girth(y) - g0[k]) < 1e-3, (k, girth(y), g0[k])
    S = np.asarray(pcs["side.L"]["P"])
    assert _turn(S[ix("side.L:arm")]).max() < 1.5 * turn0, (_turn(S[ix("side.L:arm")]).max(), turn0)  # (its top one
    # smooth part of the armhole: no hook where it was set on)
    for e in ("side.L:front", "side.L:back"):  # (each seam's top runs on into its new corner without folding back)
        E = S[ix(e)][::-1] if ix(e)[0] in (S.shape[0] - 1,) else S[ix(e)]
        E = E if E[-1, 1] > E[0, 1] else E[::-1]
        assert _turn(E[-12:]).max() < 30, (e, _turn(E[-12:]))
    w = dg.width(S, np.array([0.0, 0.40]), np.array([1.0, 0.0]))[0]
    assert abs(w - 0.12) < 0.003, w  # (the side body 120 mm at the chest)
    line = (np.array([0.0, 0.40]), np.array([1.0, 0.0]))
    ring = {"front.L", "side.L", "back.L"}
    monkeypatch.setattr(tape_geom, "tapes", lambda s3: {"chest": {"kind": "loop"}})
    monkeypatch.setattr(draft_panels, "_widths", lambda B_, d, T, g: [
        (ring, {p: dg.width(np.asarray(B_["pieces"][p]["P"]), *line)[0] for p in ring}, {}, {p: line for p in ring})])
    plan = {"panels": [{"girth": "chest", "shares": {b: {"source": "convention", "share": v} for b, v in
                                                     (("front", 0.215 / 0.55), ("side", 0.12 / 0.55),
                                                      ("back", 0.215 / 0.55))}}]}
    r = draft_panels.rows({"pieces": pcs, "seams": []}, plan, {}, {})[0]
    assert r["status"] == "PASS", r
