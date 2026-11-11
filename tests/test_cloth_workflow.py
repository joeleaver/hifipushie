"""The staged clothing workflow: design sheet, knowledge base, evidence, blocks, fold lines, the pattern sheet.
No body, no draft pack, no sim needed. Run: uv run python tests/test_cloth_workflow.py"""
import numpy as np

from hifipushie import cloth, cloth_check, garment_blocks, garment_design as gd, pattern_sheet

MEAS = {"waist": 776.0, "seat": 972.0, "hips": 920.0, "waistToSeat": 245.0, "waistToKnee": 585.0, "wrist": 150.0}


def test_kb_is_consistent():
    K = gd.kb()
    for kind, kd in K["kinds"].items():
        if kind.startswith("_"):
            continue
        for d, c in kd.get("details", {}).items():
            assert c in K["details"][d], (kind, d, c)
        for d in kd.get("required", []):
            assert d in K["details"], (kind, d)
    for d, choices in K["details"].items():
        if d.startswith("_"):
            continue
        for c, e in choices.items():
            if c.startswith("_"):
                continue
            for need in e.get("needs", []):
                assert need in K["details"], (d, c, need)
            for ev in e.get("evidence", []):
                assert set(ev) & {"piece", "no_piece", "seam", "fold", "not_made", "interfaced", "closed", "stitches",
                                  "lap", "darts", "dim", "closure", "trim"}, (d, c, ev)
                if "dim" in ev:
                    assert ev["dim"] in e.get("dims", {}), (d, c, ev)
    for src, rec in K["designs"].items():
        if src.startswith("_"):
            continue
        for d, can in rec["can"].items():
            for c in can:
                assert c in K["details"][d], (src, d, c)
        for key in rec.get("cannot", {}):
            d, c = key.split(".")
            assert c in K["details"][d], (src, key)
    for f, e in K["fabrics"].items():
        if not f.startswith("_"):
            assert e["preset"] in cloth.FABRICS, f


def test_sheet_defaults_and_failures():
    r = gd.resolve({"kind": "shirt", "from": "simon"})
    assert r["details"]["collar"]["choice"] == "shirt_collar" and r["details"]["collar"]["source"] == "kind default"
    assert not r["problems"], r["problems"]  # (C240: every kind default drafts; the shirt's placket is the slit)
    r = gd.resolve({"kind": "shirt", "from": "simon", "details": {"sleeve_placket": "tower"}})
    assert any("sleeve_placket" in p and "can't make" in p for p in r["problems"]), r["problems"]  # simon has no tower
    r = gd.resolve({"kind": "shirt", "from": "simon", "details": {"sleeve_placket": "none"}})
    assert any("needs a sleeve_placket" in p for p in r["problems"]), r["problems"]  # a barrel cuff needs one
    r = gd.resolve({"kind": "skirt", "from": "skirt_block", "fit": "a_line"})
    assert not r["problems"], r["problems"]
    try:
        gd.validate({"kind": "shirt", "details": {"collar": "ruff"}})
    except cloth.ClothError as e:
        assert "ruff" in str(e)
    else:
        raise AssertionError("an unknown choice must be refused")


def test_compile_and_expand():
    g = cloth.expanded({"design": {"kind": "skirt", "from": "skirt_block", "fit": "a_line", "fabric": "cotton_twill"},
                        "color": "#445566"})
    assert g["pattern"]["from"] == "skirt_block" and g["pattern"]["flare"] == 0.07
    assert g["fabric"]["preset"] == "denim" and g["detail"]["hem"] == 0.04 and g["color"] == "#445566"
    s = cloth.expanded({"design": {"kind": "shirt", "from": "simon", "details": {"collar": "band"}}})
    assert s["drop"] == ["collar"] and "folds" not in s
    s = cloth.expanded({"design": {"kind": "shirt", "from": "simon"}})
    assert s["folds"][0]["piece"] == "collar" and s["folds"][0]["kind"] == "roll"
    cloth.validate({"base": {"body": {}}, "cloth": {"skirt": {"design": {"kind": "skirt", "from": "skirt_block"}}}})


def _skirt(**sheet):
    g = cloth.expanded({"design": dict({"kind": "skirt", "from": "skirt_block", "fit": "a_line"}, **sheet)})
    return g, cloth.pieces(g, MEAS)


def test_fold_lines():
    own = {"pieces": {"band": {"rect": [0.4, 0.06], "role": "cuff"}}, "seams": [],
           "folds": [{"piece": "band", "line": {"mid": "x"}, "angle": 0, "kind": "press"},
                     {"piece": "band", "line": {"edge": "band:sw>s>se", "offset": 0.01}, "angle": 15, "kind": "roll"}]}
    B = cloth.pieces(own, {})
    assert len(B["folds"]) == 2
    a = gd.fold_polyline(B["pieces"], B["folds"][0])
    b = gd.fold_polyline(B["pieces"], B["folds"][1])
    assert np.allclose(a[:, 1], 0.0, atol=1e-9) and abs(np.ptp(a[:, 0]) - 0.4) < 0.01
    assert np.allclose(b[:, 1], -0.03 + 0.01, atol=1e-6), b[:3]


def test_pattern_sheet_renders():
    g, Bp = _skirt()
    im = pattern_sheet.render(Bp, "skirt", seam_rows=cloth_check.seams(Bp, "skirt"))
    assert im.size[0] > 800 and im.size[1] > 400
    assert len(set(im.resize((64, 64)).getdata())) > 20  # not blank


def test_pattern_sheet_numbers_are_in_text_not_the_image():
    """C288: the sheet is shape only (no seam table under the pieces); every piece and seam pair, with its numbers,
    is in text_lines; a piece name that can't fit inside its piece is reported, not squeezed."""
    g, Bp = _skirt()
    rows = cloth_check.seams(Bp, "skirt")
    im = pattern_sheet.render(Bp, "skirt", seam_rows=rows)
    assert isinstance(im.info.get("names_off"), list)
    txt = "\n".join(pattern_sheet.text_lines(Bp, rows))
    for nm in Bp["pieces"]:
        assert f"  {nm}: " in txt and " mm, cut " in txt
    assert txt.count("\n  S") == len(Bp["seams"]) and " ease " in txt and ("PASS" in txt or "FAIL" in txt)
    tiny = {"pieces": {"tab": dict(Bp["pieces"][next(iter(Bp["pieces"]))])}, "seams": [], "interfaced": []}
    tiny["pieces"]["tab"]["P"] = tiny["pieces"]["tab"]["P"] * 0.02  # (a 1 cm piece: no name fits inside it)
    assert pattern_sheet.render(tiny, "tiny").info["names_off"] == ["tab"]


def test_sewn_pairs_crossing_at_the_start_are_said_not_failed():
    # ZOZO starts with existing intersections allowed: pieces crossing where they are sewn / stitched (a collar on its
    # stand, a sleeve in its armhole, a cuff's lap) are a warning in stage 4; pieces with nothing joining them fail
    from hifipushie import cloth_workflow
    M = {"names": ["back", "sleeve", "cuff", "pocket"], "piece": np.array([0, 0, 1, 1, 2, 2, 3]),
         "sew": np.array([[0, 2]]), "stitch": np.array([[4, 5]])}
    cr = [("back", "sleeve"), ("cuff", "cuff"), ("back", "pocket")]
    assert cloth_workflow.sewn_crossings(cr, M) == [("back", "sleeve"), ("cuff", "cuff")]


def test_a_rib_band_may_start_stretched():
    """A band declared stretched on (its seam note's ease e < 0) is allowed 1 / (1 + e) - 1 of start stretch on its
    own triangles; other pieces get none (Tess's jumper: a rib hem band at 0.88 failed the 5% start check)."""
    import json as _j
    import numpy as np
    from hifipushie import cloth
    M = {"names": ["front", "hem_band"], "piece": np.array([0, 0, 0, 1, 1, 1]), "F": np.array([[0, 1, 2], [3, 4, 5]])}
    seam = ["hem_band:sw>s>se", ["front:hem.m>cfHem>hem"]]
    Bp = {"seam_notes": {_j.dumps(seam): {"ease": [-0.14, -0.10], "why": "rib"}}}
    a = cloth.declared_stretch(Bp, M)
    assert a[0] == 0.0 and abs(a[1] - (1 / 0.88 - 1)) < 1e-9
    assert cloth.declared_stretch({"seam_notes": {}}, M).tolist() == [0.0, 0.0]


def test_a_rib_band_is_simulated_with_room_to_stretch_on():
    """The sims get a band's declared stretch (job "declared"), and the runner raises that piece's strain limit above it:
    under the garment's 5% Tess's cuffs (cut 0.85 of the sleeve's wrist) stayed at their cut length, their closing seams
    20-47 mm open and the neckband 62 mm off the back (tess_b2); carried onto the fine mesh, 5x at the cuff."""
    import json as _j
    import numpy as np
    from hifipushie import cloth, cloth_zozo
    seam = ["cuff.L:a>b", ["sleeve.L:wrist"]]
    Bp = {"seam_notes": {_j.dumps(seam): {"ease": [-0.15, -0.15], "why": "rib"}}}
    dec = cloth.declared_pieces(Bp, ["sleeve.L", "cuff.L"])
    assert set(dec) == {"cuff.L"} and abs(dec["cuff.L"] - (1 / 0.85 - 1)) < 1e-9
    assert cloth.declared_pieces(Bp, ["front"]) == {}
    lim = 0.05
    assert cloth_zozo.declared_limit(dec["cuff.L"], lim) > lim + dec["cuff.L"] + 0.05  # the ring at the offset too
    assert cloth_zozo.declared_limit(0.0, lim) == lim and cloth_zozo.declared_limit(5.0, lim) == 1.0
    pid = np.array([0, 0, 1, 1, 2])
    pieces = ["sleeve.L", "cuff.L", "collar"]
    lifted = np.array([False, False, False, False, True])
    zone = np.array([True, False, False, False, False])
    lv = cloth_zozo.vertex_limits(pid, pieces, lim, lifted, 0.4, zone, 0.15, dec)
    assert lv[1] == lim and lv[0] == 0.15 and lv[4] == 0.4
    assert np.allclose(lv[2:4], cloth_zozo.declared_limit(dec["cuff.L"], lim))
    # (nothing declared, nothing lifted: the garment's limit everywhere, as before)
    assert (cloth_zozo.vertex_limits(pid, pieces, lim, lifted, None, np.zeros(5, bool), lim, None) == lim).all()


def test_relaxing_a_start_leaves_a_declared_band_stretched():
    """The fine start's relaxations (_relax_stretch, _relax_strain) draw a band declared stretched on (M "declared_v")
    back only to its declared stretch + their limit, not to its cut length (Tess's neckband 1.26 -> 2.99x)."""
    import numpy as np
    from hifipushie import cloth
    uv = np.array([[0, 0], [0.1, 0], [0, 0.1], [0.1, 0.1]], float)
    M = {"uv": uv, "F": np.array([[0, 1, 2], [1, 3, 2]])}
    V = np.c_[uv * [1.15, 1.0], np.zeros(4)]  # 15% stretched along x
    free = np.array([False, True, False, True])
    for fn in (cloth._relax_stretch, cloth._relax_strain):
        assert np.abs(fn(V, M, free, 0.02) - V).max() > 1e-3  # a plain piece is drawn in
        Md = dict(M, declared_v=np.full(4, 1 / 0.85 - 1))
        assert np.abs(fn(V, Md, free, 0.02) - V).max() < 1e-9  # a declared band is left as it is


def test_a_start_inside_the_contact_standoff_is_named():
    """A piece starting closer to the body than ZOZO's contact standoff (offset 2 mm + gap 1 mm) is named with where:
    Tess's neckband's folded end started 0.84 mm off the neck and the sim stopped at its first step."""
    import types
    import numpy as np
    from hifipushie import cloth_workflow
    body = types.SimpleNamespace(V=np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0.0]]), T=np.array([[0, 1, 2]]))
    M = {"names": ["front", "band"], "piece": np.array([0, 0, 1, 1]), "uv": np.zeros((4, 2))}
    X = np.array([[0.3, 0.3, 0.02], [0.2, 0.2, 0.02], [0.3, 0.3, 0.001], [0.2, 0.2, 0.01]])
    near = cloth_workflow.start_in_standoff(X, M, body)
    assert set(near) == {"band"} and abs(near["band"][0] - 1.0) < 0.05


def test_a_drafted_sweater_makes_its_rib_bands():
    """dress-tess: a crew-neck sweater from the knit block (kind hoodie, rib_neckband / rib / rib_band) failed 'a
    neckband piece (none in the pattern)': the band details now generate their bands (details.<d>.<c>.draft.generate);
    the garment's own band of a name replaces the design's."""
    from hifipushie import garment_design as gd
    sheet = {"kind": "hoodie", "block": "knit", "fit": "regular",
             "details": {"collar": "rib_neckband", "cuff": "rib", "hem": "rib_band", "pockets": "none"},
             "ops": [{"op": "sleeve"}]}
    bands = {e["band"] for e in gd.compile_sheet(sheet)["generate"]}
    assert bands == {"neckband", "cuff.L", "cuff.R", "hem_band"}, bands
    own = {"band": "hem_band", "role": "hem_band", "along": ["back:cbWaist>waist.m"], "ratio": 0.9, "height": 0.05}
    g = gd.expand({"design": sheet, "generate": [own]})
    hb = [e for e in g["generate"] if e["band"] == "hem_band"]
    assert hb == [own], hb


def test_a_piece_through_itself_is_only_excused_where_it_is_sewn_to_itself():
    """dress-tess: a jeans leg whose start folded through itself was only warned about (the sim crawled to its
    limit); a cuff closed on itself (a self seam / stitch) still is."""
    from hifipushie import cloth_workflow as wf
    M = {"names": ["front.L", "cuff.L"], "piece": np.array([0, 0, 1, 1]),
         "sew": np.array([[2, 3]]), "stitch": np.zeros((0, 2), np.int64)}
    assert wf.sewn_crossings([("front.L", "front.L"), ("cuff.L", "cuff.L")], M) == [("cuff.L", "cuff.L")]
    M["folds"] = [{"piece": "front.L", "name": "lapel roll"}]  # (a lapel pressed onto its own forepart is construction)
    assert wf.sewn_crossings([("front.L", "front.L")], M) == [("front.L", "front.L")]


if __name__ == "__main__":  # (at the END: tests defined after it never ran as a script, until dress-tess)
    for k, f in list(globals().items()):
        if k.startswith("test_"):
            f()
            print("ok", k)
