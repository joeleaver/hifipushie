"""What the joint solve read and what moved without a read (solvereads, 2026-10-12): solve_report (the measures' rows,
the model's posterior, the DIRECT read, the report, the hold), the solve's continuous down-weighting, the expression
columns, the views' sanity, and blockin.solve_step carrying them across calls. The model tests need the workspace
block-in tn_T00 and are skipped without it.  uv run python -m pytest -q tests/test_solvereads.py"""
import shutil

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


def _obs(J, o, typ="outline", view="front", sig=0.3):
    return [{"type": typ, "view": view, "o": float(o[i]), "J": J[i], "sig": sig} for i in range(len(o))]


# ---- the measures and the model's own read -----------------------------------------------------------------------------

def test_rows_cover_the_chin_and_are_consistent():
    rw = sr.rows()
    i = rw["names"].index
    for n in ("pogonion_forward", "lower_face_height", "chin_point", "mentolabial_depth", "gonial_width", "chin_width",
              "jaw_angle", "cheek_fullness", "eyes_forward"):
        assert n in rw["names"] and rw["sd"][i(n)] > 0.05
    # the profile's chain: the chin's front against the nasion = nose base + upper lip + lower lip + chin, link by link
    chain = sum(rw["R"][i(n)] for n in ("subnasale_forward", "upper_lip_forward", "lower_lip_forward", "chin_forward"))
    assert np.allclose(rw["R"][i("pogonion_forward")], chain, atol=1e-6)
    assert set(rw["unit"]) == {"mm", "sd"}
    for reg, names in sr.REGIONS.items():
        assert all(n in rw["names"] for n in names), reg


def test_support_says_which_measure_the_reads_pin():
    rw = sr.rows()
    head = fr.gnm_head(np.zeros(170))
    i, j = rw["names"].index("chin_forward"), rw["names"].index("skull_width")
    r = rw["R"][i] / np.linalg.norm(rw["R"][i])
    q = rw["R"][j] - (rw["R"][j] @ r) * r                  # skull width with the chin's direction taken out
    rng = np.random.default_rng(0)
    J = np.outer(rng.standard_normal(60), r)               # 60 reads of ONE direction: the chin's
    c = 2.0 * r
    out = fr.solve(_obs(J, J @ c), head)
    sup = sr.support(out["post"], _obs(J, J @ c))
    assert sup["read"][i] > 0.95
    assert 1 - (q @ np.linalg.inv((J.T * out["post"]["w"]) @ J + np.eye(170)) @ q) / (q @ q) < 0.01
    assert sup["by"]["chin_forward"][0][0] == ("outline", "front")
    rep = sr.report(sup, c, np.zeros(170))
    row = {x["measure"]: x for x in rep["rows"]}
    assert not row["chin_forward"]["unread"] and abs(row["chin_forward"]["moved"] - rw["R"][i] @ c) < 1e-9


def test_report_names_what_moved_with_no_read():
    rw = sr.rows()
    n = len(rw["names"])
    k = rw["names"].index("eyes_forward")
    sup = {"names": rw["names"], "unit": rw["unit"], "prior": rw["sd"], "post": rw["sd"], "read": np.ones(n), "by": {}}
    sup["read"][k] = 0.05
    c = 2.0 * rw["R"][k] / (rw["R"][k] @ rw["R"][k]) * rw["sd"][k]          # eye depth moved 2 population sd
    rep = sr.report(sup, c, np.zeros(170))
    assert [r["measure"] for r in rep["moved_unread"]] == ["eyes_forward"]
    assert "MOVED WITH NO READ" in rep["text"] and "eyes_forward" in rep["text"]
    assert not sr.report(sup, np.zeros(170), np.zeros(170))["moved_unread"]
    assert "eyes_forward" in sr.report(sup, np.zeros(170), np.zeros(170))["text"]      # listed as unread instead


def test_hold_keeps_an_unread_measure_at_the_start():
    rw = sr.rows()
    head = fr.gnm_head(np.zeros(170))
    k = rw["names"].index("eyes_forward")
    rng = np.random.default_rng(1)
    J = rng.standard_normal((40, 170)) * 0.3               # 40 reads: 170 comps are not pinned, the prior fills the rest
    c = rng.standard_normal(170)
    c *= 6.0 / np.linalg.norm(c)
    obs = _obs(J, J @ c)
    free = fr.solve(obs, head)
    read = np.ones(len(rw["names"]))
    read[k] = 0.0
    held = fr.solve(obs + sr.hold_rows(read), head)
    assert abs(rw["R"][k] @ free["dc"]) > 0.5              # the correlations moved eye depth
    assert abs(rw["R"][k] @ held["dc"]) < 0.2 * abs(rw["R"][k] @ free["dc"])
    resid = lambda d: np.sqrt(np.mean((J @ (c - d)) ** 2))  # noqa: E731
    assert resid(held["dc"]) < resid(free["dc"]) + 0.15    # ... and holding it costs the reads next to nothing
    # across calls: the hold is on the WHOLE move since the start (done), not on this call's step
    done = 1.5 * rw["R"][k] / (rw["R"][k] @ rw["R"][k])
    h = sr.hold_rows(read, done=done)
    assert len(h) == 1 and abs(h[0]["o"] + 1.5) < 1e-9


# ---- the solve: continuous down-weighting, the expression columns --------------------------------------------------------

def _forced(n=300):
    rng = np.random.default_rng(1)
    J = rng.standard_normal((n, 170)) * 0.5
    c = np.zeros(170)
    c[40] = 6.0
    return _obs(J, J @ c + 0.3 * rng.standard_normal(n))


def test_cmax_is_a_bound_not_a_factor():
    """(solvecams, 2026-10-13) a component the reads push past cmax is HELD AT it, the others solved again; no sigma
    is raised and nothing is carried (the factor went x15 for a component at 3.11 sd and stuck)."""
    head = fr.gnm_head(np.zeros(170))
    obs = _forced()
    a = fr.solve(obs, head, cmax=3.0)
    assert a["relax"] == 1.0 and a["bound"] == [40]
    assert abs(np.abs(a["dc"]).max() - 3.0) < 1e-3
    b = fr.solve(obs, head, cmax=3.0, relax0=5.0)          # an old carried factor changes nothing
    assert np.allclose(a["dc"], b["dc"])
    free = fr.solve(_obs(*(lambda J: (J, J @ np.r_[2.0, np.zeros(169)]))(np.random.default_rng(2).standard_normal((200, 170)))), head, cmax=3.0)
    assert free["bound"] == []


def test_expression_columns_take_a_pictures_expression_out_of_the_identity():
    rng = np.random.default_rng(4)
    head = dict(fr.gnm_head(np.zeros(170)), expr={"names": ("squint", "happy")})
    c = rng.standard_normal(170)
    c *= 4.0 / np.linalg.norm(c)
    obs, plain = [], []
    for view, e in (("front", np.array([0.8, 0.0])), ("3q", np.array([0.6, -0.3]))):
        Jid = rng.standard_normal((250, 170)) * 0.5
        X = rng.standard_normal((250, 2)) * 2.0                                   # mm per unit of expression
        X[:, 0] += 3.0 * Jid[:, 7]                                                # ... which looks like identity comp 7
        o = Jid @ c + X @ e + 0.3 * rng.standard_normal(250)
        obs += _obs(np.c_[Jid, X], o, typ="landmark", view=view)
        plain += _obs(Jid, o, typ="landmark", view=view)
    with_x, without = fr.solve(obs, head), fr.solve(plain, head)
    assert np.linalg.norm(with_x["dc"] - c) < 0.6 * np.linalg.norm(without["dc"] - c)
    assert abs(with_x["expr"]["front"]["squint"][0] - 0.8) < 0.1 and abs(with_x["expr"]["3q"]["happy"][0] + 0.3) < 0.1
    shared = fr.solve(obs, head, expr_mode="shared")
    assert list(shared["expr"]) == ["all"] and 0.55 < shared["expr"]["all"]["squint"][0] < 0.85
    # the NULL: neutral pictures return no expression and the identity a solve without the term returns
    obs0, plain0 = [], []
    for view in ("front", "3q"):
        Jid = rng.standard_normal((250, 170)) * 0.5
        X = rng.standard_normal((250, 2)) * 2.0
        o = Jid @ c + 0.3 * rng.standard_normal(250)
        obs0 += _obs(np.c_[Jid, X], o, typ="landmark", view=view)
        plain0 += _obs(Jid, o, typ="landmark", view=view)
    a, b = fr.solve(obs0, head), fr.solve(plain0, head)
    assert max(abs(v[0]) for d in a["expr"].values() for v in d.values()) < 0.05
    assert np.linalg.norm(a["dc"] - b["dc"]) < 0.1


# ---- the views' sanity ------------------------------------------------------------------------------------------------

def test_view_yaw_is_the_fitted_cameras_turn():
    assert abs(fr.view_yaw(fr.camera("front"))) < 1e-6
    assert abs(abs(fr.view_yaw(fr.camera("3q"))) - 35.0) < 1e-6
    assert abs(abs(fr.view_yaw(fr.camera(-72.0))) - 72.0) < 1e-6
    assert abs(abs(fr.view_yaw(fr.cam_moved(fr.camera("profile"), yaw=-10.0))) - 100.0) < 1e-6
    views = [{"image": "a/front.png", "yaw": 0}, {"image": "a/tq.png", "yaw": 45}, {"image": "a/profile.png", "yaw": -90}]
    s = fr.view_sanity(views, [fr.camera("front"), fr.camera(-23.0), fr.camera(-72.0)])
    assert not s[0]["warn"]
    assert "three-quarter" in s[1]["warn"] and "23" in s[1]["warn"]
    assert "NO TRUE SIDE VIEW" in s[2]["warn"] and s[2]["kind"] == "profile" and s[1]["kind"] == "3q"
    assert not any(x["warn"] for x in fr.view_sanity(views, [fr.camera("front"), fr.camera(-40.0), fr.camera(-88.0)]))


def test_check_references_words():
    from hifipushie import likeness_brief as lb
    assert lb._kind_word(23) == "a three-quarter view" and lb._kind_word(-72) == "a profile" and lb._kind_word(5) == "a front view"


# ---- on a block-in model -----------------------------------------------------------------------------------------------

@need_ref
def test_direct_read_knows_what_the_pictures_show():
    c = fr.compare(REF, rounds=1, lids=True, lips=True, parse=False, adapt=True)
    assert c["post"] is not None
    sup = sr.support(c["post"], c["obs"], groups=False)
    drc = sr.direct(c["post"], c["obs"], c["views"], c["head"])
    rd = dict(zip(sr.rows()["names"], drc["read"]))
    md = dict(zip(sr.rows()["names"], sup["read"]))
    assert rd["pupils_apart"] > 0.8 and rd["tip_forward"] > 0.6          # both irises in the front; the profile's nose
    assert rd["skull_width"] < 0.25 and rd["neck_width"] < 0.25          # under her hair; the body's
    assert md["skull_width"] > rd["skull_width"] + 0.2                   # the model's own posterior calls it read: correlations
    rep = sr.report(sup, c["head"]["c"], c["head"]["c"], drc=drc)
    assert "skull_width" in rep["text"] and not rep["moved_unread"]      # nothing moved: unread, not "moved with no read"


@need_ref
def test_expression_basis_matches_the_models_own_expression():
    import copy
    from hifipushie import humanfit
    spec = store.load(REF)
    head = fr.model_head(spec, expr={"names": fr.EXPR_SET})
    x = head["expr"]
    assert head["B"].shape[0] == 170 + len(fr.EXPR_SET) and head["LB"].shape[0] == 170 + len(fr.EXPR_SET)
    assert 0.6 < x["kx"] < 1.2 and x["kx_res"] < 0.5
    sp2 = copy.deepcopy(spec)
    sp2["base"]["head"]["expression"] = fr.expression_coeffs({"squint": 0.6, "mouth_left": 0.4})
    L0, L1 = (np.asarray(humanfit.state(s_["base"])["L"], float)[:68] for s_ in (spec, sp2))
    i, j = fr.EXPR_SET.index("squint"), fr.EXPR_SET.index("mouth_left")
    pred = 0.6 * head["LB"][170 + i] + 0.4 * head["LB"][170 + j]
    d = L1 - L0
    assert np.corrcoef(d.ravel(), pred.ravel())[0, 1] > 0.85
    assert np.sqrt(((d - pred) ** 2).sum(1).mean()) < 0.5 * np.sqrt((d ** 2).sum(1).mean())


@need_ref
def test_solve_step_reports_and_carries_its_state():
    from hifipushie import blockin as bi
    root, a, b = "_t_solvereads_r", "_t_solvereads_a", "_t_solvereads_b"
    try:
        for n in (root, a, b):
            shutil.rmtree(store.HOME / n, ignore_errors=True)
        bi.fork(REF, root)
        r1 = bi.solve_step(root, out=a, cameras="refit", rounds=2, hold="auto", expression="view")
        so = r1["solve"]
        assert so["report"]["rows"] and isinstance(so["report"]["text"], str)
        assert so["held"] and "skull_width" in so["held"]
        assert set(so["expression"]) and all(len(d) == len(fr.EXPR_SET) for d in so["expression"].values())
        assert so["kinds"] == ["front", "3q", "profile"] and all(x in ("plain", "parser", "points") for x in so["readers"])
        b1 = bi._refs(a)["blockin"]
        assert b1["relax"] >= 1.0 and b1["kinds"] == so["kinds"] and b1["readers"] == so["readers"]
        rw = sr.rows()
        k = rw["names"].index("skull_width")
        moved = rw["R"][k] @ (bi.identity(store.load(a)) - bi.identity(store.load(root)))
        assert abs(moved) < 0.5 * rw["sd"][k]                    # held: under her hair nothing reads the skull's width
        r2 = bi.solve_step(a, out=b, cameras="free", rounds=2, hold="auto", expression="view")
        assert r2["solve"]["readers"] == so["readers"]           # ONE outline reader per view for the whole block-in
        assert r2["solve"]["relax"] >= 1.0 + bi.RELAX_KEEP * (so["relax"] - 1.0) - 1e-6
        assert r2["solve"]["dc"] < so["dc"]
    finally:
        for n in (root, a, b):
            shutil.rmtree(store.HOME / n, ignore_errors=True)
