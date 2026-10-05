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
                                  "lap", "darts", "dim"}, (d, c, ev)
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
    assert any("sleeve_placket" in p and "can't make" in p for p in r["problems"]), r["problems"]  # simon has no placket
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


def test_skirt_block_and_evidence():
    g, Bp = _skirt()
    assert set(Bp["pieces"]) == {"front", "back.L", "back.R", "waistband"}
    assert gd.roles(Bp) == {"skirt_front": ["front"], "skirt_back": ["back.L", "back.R"], "waistband": ["waistband"]}
    rows = cloth_check.seams(Bp, "skirt")
    assert all(r["ok"] for r in rows), [r for r in rows if not r["ok"]]
    D = gd.dims(Bp, MEAS)
    assert 28 <= D["waistband_height"] <= 42 and 0 <= D["waistband_over_waist"] <= 30, D
    assert abs(D["waistband_overlap"] - 35) < 0.5, D
    ev = gd.evidence(gd.resolve(g["_design"]), Bp, MEAS)
    assert ev and all(ok for ok, *_ in ev), [e for e in ev if not e[0]]
    M = cloth.mesh(Bp, 0.02)  # it meshes: darts and the waist chain sew
    assert len(M["sew"]) > 50 and len(M["stitch"]) == 1
    # no darts: the evidence for "darts: waist" fails, said plainly
    g2, Bp2 = _skirt(pattern={"darts": False})
    bad = [t for ok, d, c, t in gd.evidence(gd.resolve(g2["_design"]), Bp2, MEAS) if not ok]
    assert any("0 darts" in t for t in bad), bad


def test_made_or_draped_and_frozen_fronts():
    g, Bp = _skirt()
    md = gd.made_or_draped(Bp, gd.resolve(g["_design"]), g["_design"])
    assert md["waistband"][0] == "made" and md["front"][0] == "draped"
    # a notched lapel's fronts must roll: wholly interfaced fronts are refused
    own = {"pieces": {"front.L": {"rect": [0.3, 0.6], "role": "front"}, "front.R": {"rect": [0.3, 0.6], "role": "front"}},
           "seams": [], "interfaced": ["front.L", "front.R"]}
    B = cloth.pieces(own, {})
    res = gd.resolve({"kind": "coat", "details": {"collar": "notched_lapel", "lining": "none", "shoulder": "none",
                                                  "back_vent": "none"}})
    bad = [t for ok, d, c, t in gd.evidence(res, B, {}) if not ok]
    assert any("can't" in t and "roll" in t for t in bad) and any("facing" in t for t in bad), bad


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


def test_generate_band_ring():
    own = {"pieces": {"body": {"rect": [0.5, 0.4], "wrap": {"to": "torso"}}}, "seams": [],
           "generate": [{"band": "neckband", "role": "neckband", "along": ["body:nw>n>ne"], "ratio": 0.85, "height": 0.02,
                         "ring": True, "fold": True, "wrap": {"to": "neck"}}]}
    B = cloth.pieces(own, {})
    P = B["pieces"]["neckband"]["P"]
    assert abs(np.ptp(P[:, 0]) - 0.5 * 0.85) < 1e-6 and "fold" in B["pieces"]["neckband"]["lines"]
    assert abs(gd.dims(B, {})["neckband_ratio"] - 0.85) < 1e-6
    assert len(B["seams"]) == 2  # to the body, and its own ring seam


def test_pattern_sheet_renders():
    g, Bp = _skirt()
    im = pattern_sheet.render(Bp, "skirt", seam_rows=cloth_check.seams(Bp, "skirt"))
    assert im.size[0] > 800 and im.size[1] > 400
    assert len(set(im.resize((64, 64)).getdata())) > 20  # not blank


if __name__ == "__main__":
    for k, f in list(globals().items()):
        if k.startswith("test_"):
            f()
            print("ok", k)
