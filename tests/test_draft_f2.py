"""F2 (blind trial s4-26, the suit jacket's step 4): vents declared, a girth compared like with like, places read off
the tapes, grain words."""
import numpy as np


def _s3(z_girth=0.8, mm=800.0, extra=None):
    r = mm / (2000 * np.pi)
    th = np.linspace(0, 2 * np.pi, 65)[:-1]
    ms = [{"name": "waist", "mm": mm, "loop": [[r * np.cos(t), r * np.sin(t), z_girth] for t in th]},
          {"name": "len", "mm": 900.0, "path": [[0.05, -r, 1.5], [0.05, -r, 0.6]]}]
    return {"measurements": ms + (extra or [])}


def _vented(w=0.44, ext=0.04, top=-0.5, vent=True):
    """A two-panel tube: a's right side and b's left are sewn from the top down to the vent top, then open, each with
    an extension `ext` past the seam line down to the hem (0.9 m)."""
    A = [[0, 0], [w, 0], [w, top], [w + ext, top], [w + ext, -0.9], [0, -0.9]]
    Bp = [[0, 0], [w, 0], [w, -0.9], [-ext, -0.9], [-ext, top], [0, top]]
    nA = {"tl": 0, "tr": 1, "vt": 2, "xt": 3, "xb": 4, "bl": 5}
    nB = {"tl": 0, "tr": 1, "br": 2, "xb": 3, "xt": 4, "vt": 5}
    pcs = {p: {"name": p, "P": np.array(P, float), "names": n, "marks": {}, "wrap": {"to": "torso"}}
           for p, P, n in (("a", A, nA), ("b", Bp, nB))}
    decl = {"tapes": {"a": ["len", "waist"], "b": ["len", "waist"]},
            "vents": [{"name": "vent", "over": "a:vent", "under": "b:vent"}] if vent else []}
    return {"pieces": pcs, "seams": [["a:tr>vt", "b:tl>vt"], ["b:tr>br", "a:tl>bl"]], "closures": [],
            "edge_arcs": {"a": {"vent": "xb>xt>vt"}, "b": {"vent": "xb>xt>vt"}}, "decl": decl}


def test_a_vents_overlap_is_counted_once_round_a_girth():
    from hifipushie import draft_girths as dg
    B = _vented()  # (cloth 2 x 480 = 960 at the level, below the vent top; each side's 40 mm extension laps)
    r = dg.rows(B, _s3(), {"waist": {"ease_mm": 80.0}})[0]
    assert r["status"] == "PASS" and "pattern 880 mm" in r["value"] and "vents' overlap -80" in r["value"], r
    assert "OPEN" not in r["value"], r
    r = dg.rows(_vented(vent=False), _s3(), {"waist": {"ease_mm": 80.0}})[0]  # (undeclared: both laps read as cloth)
    assert r["status"] == "FAIL" and "pattern 960 mm" in r["value"] and "too loose" in r["why"], r
    # above the vent top the seam closes the ring and nothing comes off
    r = dg.rows(_vented(top=-0.8), _s3(), {"waist": {"ease_mm": 80.0}})[0]
    assert "pattern 880 mm" in r["value"] and "overlap" not in r["value"], r


def test_a_vents_sides_are_unsewn_below_its_top():
    from hifipushie import draft_vents as dv
    decl = {"pieces": {"a": {"part": "x"}, "b": {"part": "x"}},
            "edges": {"a": {"side": "tr>vt", "vent": "xb>xt>vt", "other": "tl>bl"},
                      "b": {"side": "tl>vt", "vent": "xb>xt>vt", "other": "tr>br"}},
            "seams": [{"a": "a:side", "b": "b:side"}, {"a": "b:other", "b": "a:other"}],
            "vents": [{"name": "vent", "over": "a:vent", "under": "b:vent"}]}
    assert dv.faults(decl) == []
    sewn = dict(decl, seams=[{"a": ["a:side", "a:vent"], "b": ["b:side", "b:vent"]}, decl["seams"][1]])
    assert any("is in a seam" in f for f in dv.faults(sewn)), dv.faults(sewn)
    off = dict(decl, edges=dict(decl["edges"], a=dict(decl["edges"]["a"], vent="xb>xt")))
    assert any("vent top" in f for f in dv.faults(off)), dv.faults(off)
    # a pair declared once: one vent per side
    from hifipushie import draft_vents
    D = draft_vents.expand({"vents": [{"name": "v", "over": "a:vent", "under": "b:vent"}]}, {"a", "b"})
    assert [(v["name"], v["over"], v["under"]) for v in D["vents"]] == [("v.L", "a.L:vent", "b.L:vent"),
                                                                         ("v.R", "a.R:vent", "b.R:vent")]


def test_a_girths_target_uses_the_definition_its_ease_was_read_on():
    """s4-26: step 3's hips (FreeSewing's, 901 mm) + step 0's ease read on the tape's hips (942.8 mm, lower)."""
    from hifipushie import draft_girths as dg
    from test_draft_own import _tube
    tp = {"a": ["len", "waist"], "b": ["len", "waist"]}
    B, s3 = _tube({"a": 0.5, "b": 0.5}, tp)  # (1000 round at every level: rectangles)
    fe = {"ease_mm": 160.0, "body_girth_mm": 840.0, "level_z_m": 0.9}  # (step 0's own: 840 + 160 = 1000)
    r = dg.rows(B, s3, {"waist": fe})[0]
    assert r["status"] == "PASS" and "body 840 (step 0's waist definition" in r["value"], r
    r = dg.rows(B, s3, {"waist": {"ease_mm": 160.0, "body_girth_mm": 800.0}})[0]  # (the same definition: as before)
    assert r["status"] == "FAIL" and "40 mm too loose" in r["why"], r
    r = dg.rows(B, s3, {"waist": {"ease_mm": 160.0, "body_girth_mm": 840.0}})[0]  # (another one, no level recorded)
    assert r["status"] == "FAIL" and "two definitions" in r["why"], r


def test_a_pieces_place_is_read_off_its_own_tapes():
    from hifipushie import draft_place as dp
    r = 800 / (2000 * np.pi)
    s3 = _s3(1.0, extra=[{"name": "down_back", "mm": 500.0, "path": [[0.05, r, 1.5], [0.05, r, 1.0]]},
                         {"name": "arm", "mm": 550.0, "path": [[0.3, 0.0, 1.45], [0.5, 0.0, 1.2]]}])

    def B(**places):
        return {"pieces": {p: {"P": np.zeros((3, 2)), "wrap": w} for p, w in places.items()}}
    decl = {"tapes": {"f": ["len", "waist"], "k": ["down_back"], "s.L": ["arm"]}}
    ok = dp.row(B(f={"to": "torso", "side": "front"}, k={"to": "torso", "side": "back"}, **{"s.L": {"to": "arm.L"}}),
                decl, s3)
    assert ok["status"] == "PASS" and "k: torso/back (tapes down_back: back)" in ok["value"], ok
    bad = dp.row(B(f={"to": "torso", "side": "back"}, k={"to": "torso"}, **{"s.L": {"to": "torso"}}), decl, s3)
    assert bad["status"] == "FAIL", bad
    assert "f: place.side back, its tapes (len) run down the front" in bad["why"], bad
    assert "k: place.side missing (read as front)" in bad["why"], bad
    assert 's.L: placed torso, its tapes (arm) run along the arm: declare place {"to": "arm.L"}' in bad["why"], bad
    assert "one of front, back, side" in dp.row(B(f={"to": "torso", "side": "frnt"}), decl, s3)["why"]


def test_grain_takes_words():
    from hifipushie import draft_own as do
    assert (do.grain("lengthwise"), do.grain("Bias"), do.grain("crosswise"), do.grain(30)) == (90.0, 45.0, 0.0, 30.0)
    assert do.grain("diagonal") is None and do.grain(True) is None
