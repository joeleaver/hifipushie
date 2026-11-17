"""R3f-5 / R3f-7 (C502, C504): a synthetic torso worn OPEN. Its WORN state (t.worn: the look): the fronts don't lap
(no cloth across centre front), each front's edge where the front-edge trace puts it, the lapel turned about the roll
as traced (near vertical, not moved to centre front). Its CUT state (t.meshes, what steps 5 / 6 read) is the closed
one: the fronts lap past centre front, as worn closed (test_toile). A missing wear state refused by name (validate and
the build); lap_mm required whatever the wear."""
import numpy as np
import pytest

from hifipushie import toile_gate, toile_style, toile_tool
from hifipushie.toile import Toile
from test_toile import DECL, _inputs

OPEN = dict(DECL, parts=["sleeves", "opening", "lapel"], opening={"closure": "front_closure", "edge": "front_edge.L", "lap_mm": 20},
            lapel={"roll": "roll.L", "top": "collar_top.L"})
EDGE = np.array([[0.115, 1.44], [0.10, 1.36], [0.07, 1.26], [0.065, 1.10], [0.07, 1.00], [0.10, 0.93]])
ROLL = np.array([[0.055, 1.47], [0.06, 1.36], [0.07, 1.26]])


def _open_inputs(wear):
    inp = _inputs(OPEN, wear=wear)
    inp.wear = dict(wear)
    inp.traces.update({"front_edge.L": {"xz": EDGE, "corners": [2], "what": "front_edge"},
                       "roll.L": {"xz": ROLL, "corners": [], "what": "roll_line"},
                       "collar_top.L": {"xz": np.array([[0.075, 1.47], [0.115, 1.44]]), "corners": [1],
                                        "what": "collar_top"}})
    return inp


@pytest.mark.timeout(600)
def test_worn_open_the_fronts_part_on_their_traced_edges_and_are_cut_closed():
    t = Toile(_open_inputs({"front_closure": "open"}), log=lambda *_: None).build()
    assert t.info["opening"]["wear"] == "open" and t.info["opening"]["cut"] == "closed"
    assert t.info["opening"]["lap_mm"] == 20 and t.info["worn"]["opening"]["lap_mm"] == 0
    assert t.worn is not t.meshes and set(t.worn) == set(t.meshes)
    V, F = t.worn["toile"]
    front = V[:, 1] < t.yc - 0.06
    for z in (1.05, 1.15, 1.22):
        band = front & (np.abs(V[:, 2] - z) < 0.01)
        xl, xr = V[band & (V[:, 0] > 0), 0].min(), V[band & (V[:, 0] < 0), 0].max()
        want = np.interp(z, EDGE[2:, 1][::-1], EDGE[2:, 0][::-1])
        assert abs(xl - want) < 0.008 and abs(-xr - want) < 0.008, (z, xl, xr, want)  # (each edge where traced)
    assert not (front & (np.abs(V[:, 0]) < 0.05) & (V[:, 2] > 0.95) & (V[:, 2] < 1.4)).any()  # (no lap: the V shows)
    rl = t.worn_arrays["roll_line"]  # worn: the lapel turns about the roll as traced, its break at the traced place
    assert abs(rl[0, 0] - 0.07) < 0.006 and abs(rl[-1, 0] - 0.055) < 0.006, (rl[0], rl[-1])
    assert {"lapel.L", "lapel.R"} <= set(t.meshes)
    # CUT closed: the over front laps 20 mm past centre front at the buttons' height, the under front its mirror
    Vc, _ = t.meshes["toile"]
    band = (Vc[:, 1] < t.yc - 0.06) & (np.abs(Vc[:, 2] - 1.15) < 0.01)
    assert Vc[band, 0].min() < -0.015 and Vc[band, 0].max() > 0.015, (Vc[band, 0].min(), Vc[band, 0].max())
    assert t.roll_line[0, 0] < -0.01, (t.roll_line[0], t.roll_line[-1])  # (the break moved to CF + lap)
    rows = {r["id"]: r for r in toile_gate.rows(t)}
    assert rows["closed"]["status"] == "PASS" and rows["clearance"]["status"] == "PASS", (rows["closed"], rows["clearance"])
    for lv in ("chest", "waist", "hips"):  # (the girths read the closed garment: the hull bridges the opening)
        assert rows[f"girth:{lv}"]["status"] == "PASS", rows[f"girth:{lv}"]


def test_a_missing_wear_state_is_refused_by_name():
    with pytest.raises(toile_style.WearRefused, match="opening.closure 'front_closure'"):
        Toile(_open_inputs({}), log=lambda *_: None).build()
    s0 = {"fit": {"hips": {"level_z_m": 0.98}}, "heights": {"hem": {"z_mm": 920}, "sleeve_hem": {"z_mm": 980}}}
    s2 = {"traces": [{"id": k} for k in ("front_edge.L", "roll.L", "collar_top.L")], "rows": []}
    bad = toile_tool.validate(OPEN, s0, s2)
    assert any(b.startswith("opening.closure: 'front_closure' has no wear state") for b in bad), bad
    s2["ties"] = {"front_closure": {"fastened": [1], "of": 2, "source": "seen"}}
    assert any("is worn partly" in b for b in toile_tool.validate(OPEN, s0, s2))
    no_lap = dict(OPEN, opening={"closure": "front_closure", "edge": "front_edge.L"})
    for f in ([1, 2], []):  # (cut closed whatever the wear: the lap is always needed)
        s2["ties"] = {"front_closure": {"fastened": f, "of": 2, "source": "seen"}}
        assert any(b.startswith("opening.lap_mm: missing") for b in toile_tool.validate(no_lap, s0, s2))
    assert toile_tool.validate(OPEN, s0, s2) == []
    bad = toile_tool.validate(dict(OPEN, opening={"edge": "front_edge.L"}), s0, s2)
    assert "opening.closure: missing" in bad
