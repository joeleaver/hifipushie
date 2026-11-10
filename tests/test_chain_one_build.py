"""R3c (C399): ONE BUILD. GarmentBuild.run is one sequence driven by what holds what; it branches on no worn state and no
role. The ties step 2 plans are the only ties: a front with none tied gets no tie, a front tied at its top pair ties only
that pair, plackets fold only through a tied pair."""
import ast
import inspect
import textwrap
import types

import numpy as np

from hifipushie import chain_garment as cg, chain_plan as cp
from hifipushie.chain_band import BandStages
from hifipushie.chain_stiff import StiffStages

WORDS = ("state", "stand", "band", "fall", "open", "closed")


def test_run_branches_on_no_worn_state_and_no_role():
    """Every if / ternary / match test in run() is read: none may name the worn state or a role."""
    tree = ast.parse(textwrap.dedent(inspect.getsource(cg.GarmentBuild.run)))
    tests = [n.test for n in ast.walk(tree) if isinstance(n, (ast.If, ast.IfExp, ast.While))]
    tests += [n.subject for n in ast.walk(tree) if isinstance(n, ast.Match)]
    tests += [c for n in ast.walk(tree) if isinstance(n, ast.comprehension) for c in n.ifs]
    bad = []
    for t in tests:
        names = {x.id for x in ast.walk(t) if isinstance(x, ast.Name)} | \
                {x.attr for x in ast.walk(t) if isinstance(x, ast.Attribute)} | \
                {str(x.value) for x in ast.walk(t) if isinstance(x, ast.Constant) and isinstance(x.value, str)}
        hit = [n for n in names if any(w in n.lower() for w in WORDS) or n == "wear"]
        if hit:
            bad.append((ast.unparse(t), hit))
    assert not bad, f"run() branches on a worn state or a role: {bad}"
    src = inspect.getsource(cg.GarmentBuild.run)
    assert "build_open" not in src and "build_stand" not in src and "stiff_stage" not in src
    assert not hasattr(cp, "build_open") and not hasattr(cp, "button_start")


UV = {1: (0.0, 0.30), 2: (0.0, 0.30), 3: (0.0, 0.20), 4: (0.0, 0.20), 5: (0.0, 0.10), 6: (0.0, 0.10)}
FRONT = {"name": "front", "kind": "buttons", "over": "front.L", "under": "front.R", "v": [(1, 2), (3, 4), (5, 6)],
         "closed": [True] * 3}


def _ties_of(tie):
    b = types.SimpleNamespace(net=types.SimpleNamespace(root=np.arange(8)),
                              roles=types.SimpleNamespace(front=cp.apply_tie(dict(FRONT), tie, UV)))
    return StiffStages._closure_ties(b), b.roles.front


def test_a_front_with_no_tie_gets_no_tie_constraint():
    t, fr = _ties_of({"fastened": [], "of": 3})
    assert len(t) == 0 and fr["closed"] == [False] * 3 and len(fr["v"]) == 3  # (every pair kept, none tied: free)
    assert cp.first_tied(fr, UV) is None and not cp.top_tied(fr, UV)
    t, _ = _ties_of({"fastened": [], "legacy": "open"})  # (an old record's open front: the same)
    assert len(t) == 0


def test_a_front_tied_at_its_top_pair_ties_only_that_pair():
    t, fr = _ties_of({"fastened": [1], "of": 3})
    assert t[:, :2].astype(int).tolist() == [[1, 2]] and fr["closed"] == [True, False, False]
    assert cp.first_tied(fr, UV) == (1, 2) and cp.top_tied(fr, UV)
    t, fr = _ties_of({"fastened": [2, 3], "of": 3})  # (the top undone: tied from the second down)
    assert t[:, :2].astype(int).tolist() == [[3, 4], [5, 6]] and cp.first_tied(fr, UV) == (3, 4)


def _untied_band(tie):
    """An untied band: band_untied holds the sewn fronts to the topmost tied pair, or to nothing."""
    seen = {}
    b = types.SimpleNamespace(net=types.SimpleNamespace(uv=UV, root=np.arange(8), n=8), X=np.zeros((8, 3)), reads={},
                              roles=types.SimpleNamespace(front=cp.apply_tie(dict(FRONT), tie, UV)))
    b.hold_start = lambda hold: np.array([0.0, -0.1, 1.4])
    b.band_open = lambda hold=None: seen.setdefault("band_open", hold)
    BandStages.band_untied(b)
    b.plackets = lambda Xs, hold: seen.setdefault("plackets", hold) and Xs
    b.soft_net = lambda start=None, far_z=None: seen.setdefault("soft_net", far_z)
    b.roles.panels = []
    b.net.piece = np.zeros(8, int)
    b.net.pid = lambda p: 0
    far = StiffStages.fold_plackets(b)
    return b, seen, far


def test_plackets_fold_only_through_tied_pairs():
    b, seen, far = _untied_band({"fastened": [], "of": 3})
    assert b.band_hold is None and seen["band_open"] is None  # (nothing tied: nothing holds the fronts' neck)
    assert far is None and "plackets" not in seen and "soft_net" not in seen  # (no placket fold)
    b, seen, far = _untied_band({"fastened": [2, 3], "of": 3})
    assert b.band_hold == (3, 4) and seen["band_open"] == (3, 4) and seen["plackets"] == (3, 4)  # (through pair 2)
    assert far is not None and "button_start_mm" in b.reads
    b = types.SimpleNamespace(band_hold=None)  # (a band done up: band_untied never ran, no fold)
    assert StiffStages.fold_plackets(b) is None


def test_no_record_wear_is_read_as_ties():
    """No step 2: wear "open" is the band's own closure left undone (the front's pairs as the pattern has them)."""
    assert cp.ties_of_wear({"state": "open"})["band_tie"]["fastened"] == []
    assert "band_tie" not in cp.ties_of_wear({"state": "closed"})
    w = {"state": "open", "ties": {"band": {"fastened": [1], "of": 1}}, "band_tie": {"fastened": [1], "of": 1}}
    assert cp.ties_of_wear(w) is w  # (a plan's ties win)


def test_a_stiff_part_is_placed_by_what_rests_on_it_never_its_name(monkeypatch):
    """The neckline part with only soft cloth hanging from it stands (the suit jacket's collar: it was read as a band
    and refused, "no closure on the band"); with a stiff part sewn on top it is a band; other stiff parts are rings."""
    from hifipushie import chain_roles as cr
    from hifipushie.chain_holds import Part
    calls = []
    monkeypatch.setattr(cr, "stand_ring", lambda b: calls.append("stand"))
    neck = Part("undercollar", ["undercollar", "collar"], "undercollar", True, rests_on=["body"])
    front = Part("front.L", ["front.L"], "front.L", False, rests_on=["undercollar"])
    cuff = Part("cuff.L", ["cuff.L"], "cuff.L", True, rests_on=["body"])
    b = types.SimpleNamespace(neck="undercollar", band_tied=False, holds=types.SimpleNamespace(parts=[neck, front, cuff]))
    for m in ("band_closed", "band_untied", "fill_band", "stiff_last", "fall_build", "fall_surface"):
        setattr(b, m, lambda m=m: calls.append(m))
    b.rings = lambda only=None: calls.append(("rings", only))
    for p in (neck, cuff):
        StiffStages.rest_part(b, p)
    assert calls == ["stand", "fill_band", "stiff_last", ("rings", ["cuff.L"])]
    calls.clear()
    fall = Part("collar", ["collar"], "collar", True, rests_on=["undercollar"])
    b.holds.parts.append(fall)
    StiffStages.rest_part(b, neck)
    StiffStages.rest_part(b, fall)
    assert calls == ["band_closed", "band_untied", "fall_build", "fill_band", "fall_surface", "stiff_last"]
