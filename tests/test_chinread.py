"""The chin and jaw in the joint solve (chinread, 2026-10-12): the detector's chin points are left out of the differential
anchors when the set has a side view (kept when it has none); the tie of unread widths to their expectation and the hold
of the head's size (options, off by default); the two reads that did not validate stay off. The model tests need the
workspace block-in tn_T00 and are skipped without it.  uv run python -m pytest -q tests/test_chinread.py"""
import copy

import numpy as np
import pytest

from hifipushie import assets, face_ruler as fr, solve_report as sr, store

try:
    assets.pack("gnm")
    HAVE = True
except Exception:  # noqa: BLE001
    HAVE = False
pytestmark = pytest.mark.skipif(not HAVE, reason="GNM asset pack not installed")
REF = "tn_T00"
need_ref = pytest.mark.skipif(not (store.HOME / REF / "human_refs.json").exists(), reason=f"workspace model {REF} not present")


def test_defaults_what_validated_is_on_what_did_not_is_off():
    assert fr.CHIN_LM_AXES == "auto" and fr.SIDE_MIN == 60.0
    assert fr.RAMP is False and fr.CLOTH_EDGE is False and fr.CHIN_TIE is False and fr.SIZE_HOLD is True   # (size: held since 2026-10-12, Joe's decision: no picture reads it; tests/test_gnm_native.py)
    assert fr.LM_STRETCH is False and fr.LM_SIG_SCALE == 1.0


def test_tie_row_is_the_part_of_a_measure_the_read_ones_do_not_explain():
    rw = sr.rows()
    i = rw["names"].index
    given = sr.TIE_GIVEN + sr.TIE_GIVEN_SIDE
    rows = sr.tie_rows(done=np.zeros(170), given=given)
    assert [r["name"] for r in rows] == [f"tie_{n}" for n in sr.TIE]
    r = rows[0]
    G = np.array([rw["R"][i(g)] for g in given])
    assert np.abs(G @ r["J"]).max() < 1e-6 * np.linalg.norm(r["J"]) * np.linalg.norm(G, axis=1).max() + 1e-9     # independent of every given measure
    full = float(np.linalg.norm(rw["R"][i("chin_width")]))
    assert 0.3 * full < r["cond_sd"] < 0.8 * full                 # the read measures explain a good part of the chin's width, not all
    assert abs(r["sig"] - sr.TIE_SIG * r["cond_sd"]) < 1e-9 and r["type"] == "hold"
    # the whole move since the start is what is held: a head that already moved the row by x is asked back by x
    d = 0.7 * r["J"] / (r["J"] @ r["J"])
    assert abs(sr.tie_rows(done=d, given=given)[0]["o"] + 0.7) < 1e-9
    # no given measure: the plain hold at the start's value
    assert np.allclose(sr.tie_rows(given=())[0]["J"], rw["R"][i("chin_width")])


def test_tie_keeps_a_width_from_drifting_with_biased_reads_but_lets_it_follow_the_face():
    rw = sr.rows()
    i = rw["names"].index
    head = fr.gnm_head(np.zeros(170))
    cw, mw = rw["R"][i("chin_width")], rw["R"][i("mouth_width")]
    # one biased read that pushes the chin's width alone by 5 mm
    obs = [{"type": "outline", "view": "front", "o": 5.0, "J": cw, "sig": 0.3}]
    free = fr.solve(obs, head)["dc"]
    tied = fr.solve(obs + sr.tie_rows(done=np.zeros(170), names=("chin_width",), given=("mouth_width",)), head)["dc"]
    assert cw @ free > 4.0
    r = sr.tie_rows(names=("chin_width",), given=("mouth_width",))[0]["J"]
    assert abs(r @ tied) < 0.35 * abs(r @ free)                   # the independent part is held ...
    # ... while a read of the given measure still carries the width along, as the population does
    obs = [{"type": "lip", "view": "front", "o": 4.0, "J": mw, "sig": 0.2}]
    tied = fr.solve(obs + sr.tie_rows(done=np.zeros(170), names=("chin_width",), given=("mouth_width",)), head)["dc"]
    k = float(cw @ mw / (mw @ mw))
    assert abs(cw @ tied - k * (mw @ tied)) < 0.3 and cw @ tied > 0.5


def test_size_row_is_the_faces_scale():
    from hifipushie import gnm_mm
    r = sr.size_row()
    sp = gnm_mm._space()
    m = sp["gr"]["hockey_mask"]
    # a uniform 2 % growth of the face expressed in the comps (least squares) reads as +0.02
    X = (sp["T"][m] - sp["T"][m].mean(0)).ravel()
    D = (sp["IB"][:, m] - sp["IB"][:, m].mean(1, keepdims=True)).reshape(170, -1)
    c = np.linalg.lstsq(D.T, 0.02 * X, rcond=None)[0]
    got = float(r["J"] @ c)
    assert 0.5 * 0.02 < got <= 0.02 + 1e-6                       # (GNM's comps cannot make a pure scaling: what they make of it)
    assert r["type"] == "hold" and abs(sr.size_row(done=c)["o"] + got) < 1e-12
    head = fr.gnm_head(np.zeros(170))
    obs = [{"type": "outline", "view": "front", "o": 3.0, "J": 150.0 * r["J"], "sig": 1.5}]      # a read that only asks for size (2 %, +-1 %)
    assert abs(r["J"] @ fr.solve(obs + [sr.size_row()], head)["dc"]) < 0.25 * abs(r["J"] @ fr.solve(obs, head)["dc"])


@need_ref
def test_chin_points_are_left_out_when_the_set_has_a_side_view():
    from hifipushie import blockin as bi
    rj = bi._refs(REF)
    assert any(abs(fr.view_yaw(c)) >= fr.SIDE_MIN for c in rj["cameras"])          # Tess's set has one (67 deg)
    head, views, notes = fr.reference_views(REF, lids=False, lips=False, parse=False)
    assert all(v["chin"]["chin_lm"] == "none" for v in views) and any(n.startswith("CHIN:") for n in notes)
    v = views[0]
    names = {ob["name"].split(".")[0] for ob in v["extra"](head, v) if ob["type"] == "landmark"}
    assert names and not names & {"lm7", "lm8", "lm9"}
    # asked for, they are back (a set without a side view keeps them: nothing else reads the chin there)
    head, views, notes = fr.reference_views(REF, lids=False, lips=False, parse=False, chin={"chin_lm": "xy"})
    v = views[0]
    names = {ob["name"] for ob in v["extra"](head, v) if ob["type"] == "landmark"}
    assert {"lm7.x", "lm8.y", "lm9.x"} <= names and not any(n.startswith("CHIN:") for n in notes)
    head, views, _ = fr.reference_views(REF, lids=False, lips=False, parse=False, chin={"chin_lm": "y"})
    names = {ob["name"] for ob in views[0]["extra"](head, views[0]) if ob["type"] == "landmark"}
    assert "lm8.y" in names and "lm8.x" not in names and "lm30.x" in names


@need_ref
def test_a_set_without_a_side_view_keeps_the_chin_points(monkeypatch):
    from hifipushie import blockin as bi
    rj = copy.deepcopy(bi._refs(REF))
    keep = [i for i, c in enumerate(rj["cameras"]) if abs(fr.view_yaw(c)) < fr.SIDE_MIN]
    rj["views"], rj["cameras"] = [rj["views"][i] for i in keep], [rj["cameras"][i] for i in keep]
    monkeypatch.setattr(bi, "_refs", lambda name: rj)
    head, views, notes = fr.reference_views(REF, lids=False, lips=False, parse=False)
    assert all(v["chin"]["chin_lm"] == "xy" for v in views) and not any(n.startswith("CHIN:") for n in notes)
    names = {ob["name"] for ob in views[0]["extra"](head, views[0]) if ob["type"] == "landmark"}
    assert {"lm7.x", "lm8.y", "lm9.y"} <= names


@need_ref
def test_the_unvalidated_reads_run_only_when_asked():
    head, views, _ = fr.reference_views(REF, lids=False, lips=False, parse=False)
    v = [dict(views[1], limbus=False)]
    obs = fr.observe(head, v, colour=False)
    assert not any(ob["type"] in ("ramp", "cloth") for ob in obs)
    for ob in fr._ramp_obs(head, dict(views[1])):                # asked: reads carry a shift in mm and the model's own Jacobian
        assert abs(ob["o"]) <= fr.RAMP_REACH + 0.26 and len(ob["J"]) == 170 and ob["ncc"] >= fr.RAMP_NCC
