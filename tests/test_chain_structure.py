"""C286: the pre-sim structure rows come from the garment record (step 2), judged by one vocabulary of kinds."""
import numpy as np
import pytest

from hifipushie import chain_structure as cs, garment_plan as gp, garment_reads as gr, structure_rows as sr

READ = {"views": [{"image": "f.png", "view": "front", "scale": {"mm_per_px": 0.5, "from": "neck"}},
                  {"image": "s.png", "view": "side"}]}
PARTS = {"pieces": {"front.L": {"stiff": False}, "front.R": {"stiff": False}, "back": {"stiff": False},
                    "collar_band": {"stiff": True}, "collar": {"stiff": True}},
         "closures": {"front": {"pieces": ["front.L", "front.R"]}, "band": {"pieces": ["collar_band"]},
                      "cuff": {"pieces": ["cuff.L"]}}}
M = {"names": ["front.L", "front.R", "back", "stand", "collar"]}


def _style(**kw):
    s = {"state": {"front": {"state": "closed", "source": "f"}, "band": {"state": "open", "source": "f"},
                   "cuff": {"state": "closed", "source": "convention"}},
         "bends": [{"id": "spread", "on": "collar", "what": "collar_points_apart",
                    "target": {"value": 1.7, "unit": "ratio", "of": "neck_width"}, "source": "front view"},
                   {"id": "tilt_b", "on": "collar", "what": "collar_tilt", "target": {"value": 31, "unit": "deg"},
                    "source": "side view"}],
         "rows": [{"id": "nw", "what": "neck_width", "target": {"value": 200, "unit": "px"}, "source": "f", "view": 0},
                  {"id": "v", "what": "v_depth", "target": {"value": 60, "unit": "px", "tol": 10}, "source": "f", "view": 0},
                  {"id": "fall", "what": "fall_back_width", "target": {"value": 80, "unit": "px", "tol": 10}, "source": "s",
                   "view": 1},
                  {"id": "tilt", "what": "collar_tilt", "target": {"value": 30, "unit": "deg", "tol": 5}, "source": "s"},
                  {"id": "drop", "what": "collar_points_drop", "target": {"value": 9, "unit": "cm"}, "source": "s"},
                  {"id": "frogs", "what": "trim_row_count", "target": {"value": 7, "unit": "count"}, "source": "f"},
                  {"id": "len", "what": "garment_length", "target": {"is": "the high hip"}, "source": "f"},
                  {"id": "back", "what": "not_judged", "target": {"is": "no view"}, "source": "front only"}]}
    s.update(kw)
    return s


def _plan(**kw):
    return {"read": READ, "parts": PARTS, "style": _style(**kw)}


def test_rows_from_the_record():
    its, notes = cs.items(M, _plan())
    by = {i["id"]: i for i in its}
    assert by["spread"]["read"] == "collar_points_apart_mm/neck_width_mm" and by["spread"]["range"] == [1.53, 1.87]
    assert "tilt_b" not in by and by["tilt"]["range"] == [25.0, 35.0]       # a row of the bend's kind judges it
    assert by["v"]["read"] == "v_below_points_mm/neck_width_mm" and by["v"]["range"] == [0.25, 0.35]  # px / the base row
    assert "px" in by["fall"]["missing"]  # no base row on the side view and no scale there: UNMEASURED
    assert by["drop"]["range"] == [81.0, 99.0] and "+-10%" in by["drop"]["source"]  # cm -> mm, default tolerance
    assert "T10" in by["frogs"]["missing"] and "give a number" in by["len"]["missing"]
    assert any(n.startswith("back: not judged") for n in notes) and any(n.startswith("nw: a base") for n in notes)
    assert all(i["source"] and i["change"] for i in its)
    assert by["closure_band"]["equals"] == "open" and "no build reading" in by["closure_cuff"]["missing"]


def test_fall_px_by_scale():
    st = _style()
    st["rows"][2]["view"] = 0  # on the front view: neck_width is a base of fall_back_width -> a ratio
    its, _ = cs.items(M, {"read": READ, "parts": PARTS, "style": st})
    f = next(i for i in its if i["id"] == "fall")
    assert f["read"] == "collar_fall_cb_width_mm/neck_width_mm" and f["range"] == [0.35, 0.45]
    READ2 = {"views": [READ["views"][0], dict(READ["views"][1], scale={"mm_per_px": 0.55, "from": "ear"})]}
    its, _ = cs.items(M, {"read": READ2, "parts": PARTS, "style": _style()})
    f = next(i for i in its if i["id"] == "fall")
    assert f["read"] == "collar_fall_cb_width_mm" and f["range"] == [38.5, 49.5]


def test_unknown_what_refused_with_the_list():
    p = gp.check_style  # step-2 validation, against the one vocabulary
    read = {"views": READ["views"]}
    parts = {"pieces": {"collar": {}}, "details": {}, "closures": {"front": {"pieces": ["collar"]}}}
    base = {"state": {"front": {"state": "closed", "source": "f"}}, "pose": {"name": "arms down", "source": "f"},
            "bends": [], "rows": [{"id": "x", "what": "points spread nicely", "target": {"value": 1, "unit": "mm"},
                                   "source": "f"}]}
    with pytest.raises(gp.PlanRefused) as e:
        p(base, read, parts)
    assert "not a row kind" in str(e.value) and "collar_points_apart" in str(e.value) and "trim_row_pitch" in str(e.value)
    base["rows"][0].update(what="collar_tilt", target={"value": 3, "unit": "mm"})
    with pytest.raises(gp.PlanRefused, match="unit 'mm' for collar_tilt"):
        p(base, read, parts)
    base["rows"][0].update(what="v_depth", target={"value": 0.3, "unit": "ratio", "of": "shoulder_width"})
    with pytest.raises(gp.PlanRefused, match="is of 'neck_width'"):
        p(base, read, parts)
    base["bends"] = [{"id": "b", "on": "collar", "target": {"value": 31, "unit": "deg"}, "source": "s"}]
    base["rows"][0]["target"]["of"] = "neck_width"
    with pytest.raises(gp.PlanRefused, match="bends.0. b.what None"):  # a numeric bend names its kind
        p(base, read, parts)
    base["bends"][0]["what"] = "collar_tilt"
    p(base, read, parts)


def test_unmeasured_is_named_and_blocks(monkeypatch):
    monkeypatch.setattr(cs, "reads", lambda *a: {"collar_top_tilt_deg": 30.0})
    parts = dict(PARTS, pieces={k: dict(v, stiff=True) for k, v in PARTS["pieces"].items()})
    res = cs.check(None, M, None, None, {}, {}, {"read": READ, "parts": parts, "style": _style()})
    by = {r["id"]: r for r in res["rows"]}
    assert by["tilt"]["status"] == "PASS"
    assert by["frogs"]["status"] == "UNMEASURED" and "T10" in by["frogs"]["why"] and by["frogs"]["change"]
    assert by["len"]["status"] == "UNMEASURED" and res["verdict"] == "FAIL"
    none = cs.check(None, M, None, None, {}, {}, None)
    assert none["verdict"] == "FAIL" and any(r["id"] == "style_plan" and r["status"] == "UNMEASURED" for r in none["rows"])


def test_roughness_smooth_vs_crumpled():
    for r in (0.04, 0.15):
        X, F = sr.tube(r, 0.008)
        Mt = {"names": ["sleeve.L"], "F": F, "piece": np.zeros(len(X), int)}
        ok = sr.roughness(X, Mt, ["sleeve.L"])["sleeve.L"]
        assert ok["bump_p90_mm"] <= ok["limit_mm"], ok
        Xn, _ = sr.tube(r, 0.008, noise=0.0015)
        bad = sr.roughness(Xn, Mt, ["sleeve.L"])["sleeve.L"]
        assert bad["bump_p90_mm"] > 1.5 * bad["limit_mm"], bad
    assert sr.soft_pieces(M, PARTS) == ["front.L", "front.R", "back"]  # collar_band (stiff) matches the build's "stand"
