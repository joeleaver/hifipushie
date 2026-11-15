"""F4 (trial s4-28): step 2's panel shares each from a source (reference or convention, never typed), the seams placed
round the body for the step-2 look, and the a>b short-way hint on a converter refusal."""
import numpy as np
import pytest

from hifipushie import panel_shares as ps, panel_shares_look as psl

PIECES = {"front.L": {}, "side.L": {}, "back.L": {}}
READ = {"views": [{"view": "front", "image": "x.png"}],
        "fit_read": {"view": 0, "widths": [{"at": "chest", "garment": [[450, 560], [806, 560]],
                                             "body": [[473, 560], [783, 560]]}]}}


def _loop(a=0.17, b=0.12, n=400):
    th = np.linspace(0, 2 * np.pi, n, endpoint=False)
    return np.c_[a * np.sin(th), -b * np.cos(th), np.full(n, 1.3)]


def _check(panels, loop=True):
    bad = []
    out = ps.check(panels, PIECES, READ, (lambda g: _loop()) if loop else None, bad)
    return out, bad


def test_inferred_or_typed_shares_refused_by_name():
    out, bad = _check([{"girth": "chest", "shares": {"front": {"source": "convention"}, "side": {"source": "inferred"},
                                                     "back": .38}}])
    assert any("side.source 'inferred'" in b and "never draft / block / inferred" in b for b in bad)
    assert any("shares.back" in b and "never a typed share" in b for b in bad)
    out, bad = _check([{"girth": "chest", "shares": {k: {"source": "convention", "share": .3} for k in
                                                     ("front", "side", "back")}}])
    assert any("front.share 0.3: not typed" in b for b in bad)


def test_convention_takes_the_rule():
    out, bad = _check([{"girth": "chest", "shares": {k: {"source": "convention"} for k in ("front", "side", "back")}}])
    assert not bad
    sh = {k: v["share"] for k, v in out[0]["shares"].items()}
    assert sh == {"front": .40, "side": .22, "back": .38}
    out2, bad2 = _check(out)  # (a saved entry re-checked: the tool's own shares pass; garment_carry)
    assert not bad2 and out2[0]["shares"] == out[0]["shares"]


def test_reference_share_walked_round_the_body_and_convention_fills_the_rest():
    R = ps.ring(_loop())
    out, bad = _check([{"girth": "chest", "shares": {
        "front": {"source": "reference", "view": 0, "at": [[806, 562]], "what": "front / side seam at the silhouette"},
        "side": {"source": "convention"}, "back": {"source": "convention"}}}])
    assert not bad
    sh = {k: v["share"] for k, v in out[0]["shares"].items()}
    assert sh["front"] == pytest.approx(2 * R["s_side"] / R["round_mm"], abs=0.01) and sh["front"] == pytest.approx(.5, abs=.01)
    assert sh["side"] == pytest.approx(.22 * .5 / .6, abs=.01) and sh["back"] == pytest.approx(.38 * .5 / .6, abs=.01)
    # a point off the girth's level, one outside the garment, and the wrong number of points are refused
    _, bad = _check([{"girth": "chest", "shares": {
        "front": {"source": "reference", "view": 0, "at": [[700, 760]], "what": "x"},
        "side": {"source": "reference", "view": 0, "at": [[900, 560], [700, 560]], "what": "y"},
        "back": {"source": "convention"}}}])
    assert any("off the chest level" in b for b in bad) and any("outside the garment" in b for b in bad)
    _, bad = _check([{"girth": "chest", "shares": {
        "front": {"source": "reference", "view": 0, "at": [[806, 560]], "what": "x"},
        "side": {"source": "convention"}, "back": {"source": "convention"}}}], loop=False)
    assert any("no body" in b for b in bad)


def test_look_puts_each_seam_at_its_share():
    out, _ = _check([{"girth": "chest", "shares": {k: {"source": "convention"} for k in ("front", "side", "back")}}])
    e = out[0]
    R = ps.ring(_loop())
    half = R["round_mm"] / 2
    sm = e["placed"]["seams"]
    assert [s["between"] for s in sm] == [["front", "side"], ["side", "back"]]
    assert sm[0]["s_mm"] == pytest.approx(.40 * half, abs=1) and sm[1]["s_mm"] == pytest.approx(.62 * half, abs=1)
    assert sm[0]["seen_from"] == "front" and sm[1]["seen_from"] == "back"  # (0.40 of the half ring: in front of the side; 0.62 behind it)
    tk = psl.ticks(e, READ, 0, "front")
    assert len(tk) == 2 and all(abs(abs(u - 628) - abs(sm[0]["t"]) * 178) < 1 for u, _, _ in tk)
    e2 = dict(e, placed=ps.place(R, [("front", .46), ("side", .08), ("back", .46)]))
    tk = psl.ticks(e2, READ, 0, "front")
    t0 = e2["placed"]["seams"][0]["t"]
    assert [round(u) for u, _, _ in tk] == [round(628 - abs(t0) * 178), round(628 + abs(t0) * 178)]
    side = next(p for p in e2["placed"]["pieces"] if p["piece"] == "side")
    assert side["share"] == .08
    lines = "\n".join(ps.text_lines({"panels": [e]}))
    assert "front / side at" in lines and "side 0.22 (convention: body_panels)" in lines


def test_short_way_round_named_on_a_refusal():
    from hifipushie import draft_own_block as dob
    # a collar: its outer edge tip1 > cbo > tip2 is the long way round from tip1 to tip2
    pts = [("tip1", (0, 0)), ("n1", (.05, -.01)), ("tip2", (.1, 0)), ("o2", (.12, .06)), ("cbo", (.05, .09)),
           ("o1", (-.02, .06))]
    pc = {"name": "collar.L", "P": np.array([p for _, p in pts], float), "names": {n: i for i, (n, _) in enumerate(pts)}}
    sw = []
    dob._short_way(pc, "collar.L", "outer", "tip1>tip2", sw)
    dob._short_way(pc, "collar.L", "neck", "tip1>n1>tip2", sw)  # (a via point decides: not noted)
    assert [x["edge"] for x in sw] == ["collar.L:outer"] and sw[0]["short_mm"] == 102 and sw[0]["long_mm"] > 250
    h = dob.short_way_hint({"short_ways": sw}, "two sewn edges overlap: collar.L:tip1>tip2 (seam 3) and collar.L:...")
    assert "collar.L:tip1>tip2 (collar.L:outer) was walked the short way round (102 mm" in h
    assert "add a via point (tip1>v>tip2" in h
    assert dob.short_way_hint({"short_ways": []}, "x") == ""
