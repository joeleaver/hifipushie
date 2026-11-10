"""chain_net / chain_garment: lengths exact, seams one node, no fit input, refusals name a line, mirror two-way (the collapse),
and the MCP layer offers no other way to start a garment."""
import asyncio
import re

import numpy as np
import pytest

from hifipushie import chain_garment as cg, chain_net as cn, server


def _strip(n=9, w=0.1, h=0.02, x0=0.0, piece=0):
    """A flat strip of n x 2 vertices."""
    xs = np.linspace(x0, x0 + w, n)
    uv = np.r_[np.c_[xs, np.zeros(n)], np.c_[xs, np.full(n, h)]]
    F = []
    for i in range(n - 1):
        F += [[i, i + 1, n + i], [i + 1, n + i + 1, n + i]]
    return uv, np.array(F), np.full(2 * n, piece)


def _mesh(pieces=2):
    uvs, Fs, ps, off = [], [], [], 0
    for p in range(pieces):
        uv, F, pc = _strip(piece=p, x0=0.2 * p)
        uvs.append(uv), Fs.append(F + off), ps.append(pc)
        off += len(uv)
    names = [f"p{k}" for k in range(pieces)]
    return {"uv": np.concatenate(uvs), "F": np.concatenate(Fs), "piece": np.concatenate(ps), "names": names,
            "sew": np.zeros((0, 2), np.int64), "folds": [], "closures": []}


def test_project_makes_chains_exact():
    """From a rough start every exact link reaches its cut length; an at-most line may stay shorter, never longer."""
    M = _mesh(1)
    net = cn.Network(M)
    rng = np.random.default_rng(1)
    X = np.c_[net.uv, np.zeros(net.n)] * [1.1, 1.0, 1.0] + rng.normal(0, 0.002, (net.n, 3))
    li, lj, lL, lE = net.lines(step=1)
    I, J = np.r_[net.link_i, li], np.r_[net.link_j, lj]
    L, E = np.r_[net.link_L, lL], np.r_[np.ones(len(net.link_L), bool), lE]
    Y, rd = cn.project(X, I, J, L, E, iters=60, step=0.01)
    assert rd["worst_exact_pct"] <= cn.EXACT_TOL * 100 * 1.01, rd
    assert net.chain_report(Y)["worst_pct"] < 0.02
    d = np.linalg.norm(Y[J] - Y[I], axis=1)
    assert (d[~E] <= L[~E] * (1 + cn.ATMOST_TOL) + 1e-9).all()


def test_seam_merge_is_one_node_and_keeps_closures_apart():
    """Sewn points are one node; closures are wear and never merge; a seam's two sides average, the difference is read."""
    M = _mesh(2)
    n = 9
    M["sew"] = np.array([[n + i, 18 + i] for i in range(n)])  # p0's top edge to p1's bottom edge
    M["uv"][18:27, 0] -= 0.2  # same x
    M["closures"] = [{"name": "c", "over": "p0", "under": "p1", "v": [[0, 18]], "closed": [True]}]
    net = cn.Network(M)
    assert net.root[n] == net.root[18]
    assert net.root[0] != net.root[18 + 9]
    assert net.root[0] != net.root[18 + 0] or (0, 18) in [tuple(p) for p in M["sew"]]
    # a link whose two ends are sewn together closes a cut: no length
    assert (net.link_i != net.link_j).all()
    assert net.seam_mismatch()["max_mm"] < 1e-6


def test_mirror_map_is_two_way():
    """The first all-pieces build mapped left -> right only: every right node mirrored onto itself and the net collapsed."""
    M = _mesh(2)
    M["names"] = ["a.L", "a.R"]
    net = cn.Network(M)
    mir = cn.mirror_map(net, [("a.L", "a.R", 1.0)])
    both = np.r_[net.verts("a.L"), net.verts("a.R")]
    assert (mir[both] >= 0).all()
    assert (net.piece[mir[net.verts("a.R")]] == net.pid("a.L")).all()


def test_no_fit_input():
    """Positions can't get in: Pattern keeps pattern keys only, and a Network given positions refuses."""
    M = _mesh(1)
    M2 = dict(M, A=np.zeros((len(M["uv"]), 3)))
    p = cg.pattern_from_mesh(M2)
    assert "A" not in p.M and "A" not in cg.PATTERN_KEYS
    with pytest.raises(ValueError, match="never a fit"):
        cn.Network(M2)


def test_refusal_names_the_line():
    """A length past the limit is refused with the piece, the line and the next step."""
    M = _mesh(1)
    n = len(M["uv"])
    b = object.__new__(cg.GarmentBuild)
    b.net = cn.Network(M)
    b.roles = cg.Roles(None, None, [], [], ["p0"], None, None, None)
    b.reads = {}
    b.X = np.c_[M["uv"] * [1.5, 1.0], np.zeros(n)]
    with pytest.raises(cg.ChainRefused) as e:
        b.gate_lengths()
    t = str(e.value)
    assert "p0 edge" in t and "next:" in t and "alter_pattern" in t


def test_contact_side_and_floor():
    """A point under a floor comes up to its gap in project; the signed distance reads the side."""
    V = np.array([[-1, -1, 0], [1, -1, 0], [1, 1, 0], [-1, 1, 0.0]])
    T = np.array([[0, 1, 2], [0, 2, 3]])
    ct = cn.Contact(V, T)
    sd, n = ct.query(np.array([[0.1, 0.1, 0.05], [0.1, 0.1, -0.02]]))
    assert sd[0] == pytest.approx(0.05) and sd[1] == pytest.approx(-0.02)
    X = np.array([[0.0, 0.0, -0.01], [0.1, 0.0, -0.01]])
    Y, rd = cn.project(X, [0], [1], [0.1], [True], contacts=[(ct, np.array([0, 1]), 0.005)], iters=20)
    assert ct.query(Y)[0].min() >= 0.005 - 1e-4
    assert abs(np.linalg.norm(Y[1] - Y[0]) - 0.1) < 1e-4


def test_threads_read_warp_and_weft_not_the_bias():
    """A pure shear of the flat cloth stretches the bias, not the threads' first-order reading (and a stretch reads)."""
    uv = np.array([[0, 0], [0.1, 0], [0, 0.1.__float__()]], float)
    th = cn.Threads(uv, np.array([[0, 1, 2]]), 0.02)
    X = np.c_[uv, np.zeros(3)]
    assert abs(th.report(X)["max_pct"]) < 1e-6
    X2 = X.copy()
    X2[:, 0] *= 1.1
    assert th.report(X2)["max_pct"] == pytest.approx(10.0, abs=0.01)


GATED = ("fit_garment", "style_garment", "release_garment", "arrange_garment", "dress", "look_cloth", "check_garment",
         "check_garment_reference", "game_garment")


@pytest.mark.skipif(server.LEGACY_CLOTH, reason="legacy cloth on")
def test_only_path_for_clothes():
    """A blind agent asking how to make clothes lands on the chain path and nothing else."""
    for q in ("make a shirt", "fit a garment", "dress the character", "drape a jacket on the body", "clothes", "simulate cloth"):
        t = server.find_tool(q, limit=8)
        assert "Clothes: garment_plan" in t and "chain_garment" in t, (q, t)  # (T4: a garment starts at its reading)
        names = re.findall(r"^\d+\. (\w+) ", t, re.M)
        assert not set(names) & set(GATED), (q, names)
    full = server.find_tool("")
    for g in GATED:
        assert not re.search(r"\b" + g + r"\b", full)
    assert "chain_garment" in full
    ins = server.mcp.instructions
    assert "chain_garment" in ins and not any(g in ins for g in GATED)
    for g in GATED:
        with pytest.raises(ValueError, match="chain_garment"):
            asyncio.run(server.call_tool(g, {}))
        assert "chain_garment" in server.guide(g)
    for topic in ("cloth", "cloth_tools", "cloth_construction", "spec", "tools", ""):
        t = server.guide(topic)
        assert not any(re.search(r"\b" + g + r"\b", t) for g in GATED), topic
    assert "chain_garment" in server.guide("cloth")
    for t in ("look_pattern", "pattern_check", "garment_from_reference", "review_view", "alter_pattern"):
        s = server.guide(t)
        assert not any(re.search(r"\b" + g + r"\b", s) for g in GATED if g != "dress") and "dress`" not in s, t


def test_chain_tool_strict_arguments():
    with pytest.raises(ValueError, match="closed"):
        server.chain_garment("x", "y", wear="half")
    with pytest.raises(ValueError, match="only with"):
        server.chain_garment("x", "y", wear="closed", opening=1.5)
    with pytest.raises(ValueError, match="1.0"):
        server.chain_garment("x", "y", wear="open", opening=9)


def _job_model(monkeypatch, tmp_path, script: str):
    """The job path on a stub worker: the real tool, spawn and status files; no build, no gate."""
    import json
    import subprocess
    import sys
    from hifipushie import store
    monkeypatch.setattr(store, "HOME", tmp_path)
    monkeypatch.setattr(store, "load", lambda n: {"bones": {}, "cloth": {"shirt": {"design": {"kind": "shirt"}}}})
    calls = []

    def spawn(d, name, garment, w):
        calls.append(w)
        code = ("import json,sys,time,pathlib\nd=pathlib.Path(sys.argv[1])\ndef put(**k):\n st=json.loads((d/'status.json').read_text())\n"
                " st.update(k)\n (d/'status.json').write_text(json.dumps(st))\n" + script)
        return subprocess.Popen([sys.executable, "-c", code, str(d)]).pid

    monkeypatch.setattr(server, "_chain_spawn", spawn)
    return calls, json


def test_job_answers_at_once_and_a_poll_never_starts_a_second(monkeypatch, tmp_path):
    calls, _ = _job_model(monkeypatch, tmp_path, "put(stage='building')\ntime.sleep(4)\nput(stage='done', reads={})\n")
    monkeypatch.setattr(server, "_chain_gate", lambda *a: None)
    t = server.chain_garment("m", "shirt", wait=0)
    assert 'next: call_tool("chain_garment"' in t and '"wear": "closed"' in t
    t = server.chain_garment("m", "shirt", wait=0)
    assert len(calls) == 1 and "next: call_tool" in t
    t = server.chain_garment("m", "shirt", wait=20)
    assert "built and hung" in t and "look_chain" in t and len(calls) == 1
    t = server.chain_garment("m", "shirt", wait=0)  # a finished job answers with its result
    assert "built and hung" in t and len(calls) == 1
    server.chain_garment("m", "shirt", wait=0, rebuild=True)
    assert len(calls) == 2


def _plan(band="open", front="closed", **front_kw):
    """A step-0..2 record's outputs (garment_plan shapes): a band closure, a front closure, a cuff."""
    parts = {"pieces": {"front.L": {}, "front.R": {}, "collar_band": {}, "collar": {}, "cuff.L": {}},
             "closures": {"front": {"pieces": ["front.L", "front.R"]}, "band": {"pieces": ["collar_band"]},
                          "cuff.L": {"pieces": ["cuff.L"]}}}
    style = {"state": {"front": dict(state=front, source="photo", **front_kw), "band": {"state": band, "source": "photo"},
                       "cuff.L": {"state": "closed", "source": "convention"}},
             "bends": [{"id": "collar_spread", "on": "collar", "what": "collar_points_apart", "source": "photo",
                        "target": {"value": 1.6, "unit": "ratio", "of": "neck_width"}}]}
    return {"read": {}, "parts": parts, "style": style}


def test_the_plan_decides_the_worn_state():
    """T7 (C287): the band closure's planned state is the wear; the plan's collar spread is the FALL's target; a
    contradicting wear / opening is refused by name; no record = the arguments, as before."""
    from hifipushie import chain_plan as cp
    w = cp.planned_wear(_plan())
    assert w["state"] == "open" and w["spread"] == 1.6 and "ties.band open" in w["state_from"]
    assert cp.planned_wear(_plan(band="closed"))["state"] == "closed" and "spread" not in cp.planned_wear(_plan(band="closed"))
    with pytest.raises(cp.PlanContradiction, match="contradicts the style plan: ties.band open"):
        cp.planned_wear(_plan(), wear="closed")
    with pytest.raises(cp.PlanContradiction, match="opening 2.0 contradicts"):
        cp.planned_wear(_plan(), opening=2.0)
    assert cp.planned_wear(_plan(), wear="open", opening=1.6)["spread"] == 1.6  # (agreeing arguments are fine)
    # (C396: a front with nothing tied, or partly tied under a band done up, is built, never refused)
    assert cp.planned_wear(_plan(front="open"))["front_tie"]["fastened"] == []
    with pytest.raises(cp.PlanContradiction, match="fastened_from"):  # (an old partly naming no button: which is unknown)
        cp.planned_wear(_plan(front="partly"))
    assert cp.planned_wear(_plan(band="closed", front="partly", fastened_from=2))["state"] == "closed"
    assert cp.planned_wear(_plan(front="partly", fastened_from=2))["front_tie"]["fastened_from"] == 2
    assert cp.planned_wear(None) == {"state": "closed"}
    assert cp.planned_wear(None, "open", 1.5) == {"state": "open", "spread": 1.5}
    assert cp.planned_wear({"read": {}, "parts": {}, "style": None}, "open") == {"state": "open"}  # (a record, no step 2)
    uv = {1: (0, 0.3), 3: (0, 0.2), 5: (0, 0.1)}  # (pairs' over points, top first by uv y)
    fr = cp.apply_tie({"over": "front.L", "under": "front.R", "v": [(1, 2), (3, 4), (5, 6)], "closed": [True] * 3},
                      {"fastened_from": 2, "legacy": "partly"}, uv)
    assert fr["v"] == [(1, 2), (3, 4), (5, 6)] and fr["closed"] == [False, True, True]  # (C396: every pair kept, marked)


def _tplan(band, front):
    p = _plan()
    p["style"].pop("state")
    p["style"]["ties"] = {"front": dict(front, source="photo"), "band": dict(band, source="photo"),
                          "cuff.L": {"fastened": [1], "of": 1, "source": "convention"}}
    return p


def test_ties_are_which_fastenings_are_done_up():
    """R1 (C391): step 2 names the fastenings done up; open / closed / partly are only their summary; the build ties
    exactly those pairs (any set, not only 'from button k down')."""
    from hifipushie import chain_plan as cp, closure_ties as ct
    w = cp.planned_wear(_tplan({"fastened": [], "of": 1}, {"fastened": [2, 3], "of": 3}))
    assert w["state"] == "open" and w["front_tie"]["fastened"] == [2, 3] and w["plan"]["front"] == "partly"
    assert cp.planned_wear(_tplan({"fastened": [1], "of": 1}, {"fastened": [1, 2, 3], "of": 3}))["state"] == "closed"
    w = cp.planned_wear(_tplan({"fastened": [], "of": 1}, {"fastened": [], "of": 3}))  # (C396: none tied is built)
    assert w["front_tie"]["fastened"] == [] and w["plan"]["front"] == "open"
    uv = {1: (0, 0.3), 3: (0, 0.2), 5: (0, 0.1)}
    fr = {"name": "front", "over": "front.L", "under": "front.R", "v": [(1, 2), (3, 4), (5, 6)], "closed": [True] * 3}
    t = cp.apply_tie(fr, {"fastened": [1, 3], "of": 3}, uv)  # (top and bottom done up, the middle undone)
    assert t["v"] == [(1, 2), (3, 4), (5, 6)] and t["closed"] == [True, False, True]
    assert cp.apply_tie(fr, {"span": [0.4, 1.0]}, uv)["closed"] == [False, True, True]  # (a zip done up from 0.4 down;
    # C396: the pair above is kept, untied)
    with pytest.raises(Exception, match="counts 2 fastenings"):
        cp.apply_tie(fr, {"fastened": [1], "of": 2}, uv)
    assert cp.apply_tie(fr, {"all": True, "legacy": "closed"}, uv) is fr  # (an old closed record: the pattern as it was)
    assert ct.summary({"fastened": [1], "of": 2}) == "partly" and ct.summary({"span": [0, 1]}) == "closed"
    assert ct.said({"fastened": [], "of": 2}) == "none of 2 done up (open)"
    assert ct.of_style({"state": {"f": {"state": "partly", "fastened_from": 2}}})["f"]["fastened_from"] == 2


def test_the_tool_builds_the_planned_state(monkeypatch, tmp_path):
    from hifipushie import chain_structure as cs
    calls, _ = _job_model(monkeypatch, tmp_path, "put(stage='building')\ntime.sleep(2)\n")
    monkeypatch.setattr(server, "_chain_gate", lambda *a: None)
    server.chain_garment("m", "shirt", wait=0)  # no record: closed, as before
    assert calls[-1]["state"] == "closed" and "plan" not in calls[-1]
    monkeypatch.setattr(cs, "load_plan", lambda m, g: _plan())
    t = server.chain_garment("m", "shirt", wait=0)
    assert calls[-1]["state"] == "open" and calls[-1]["spread"] == 1.6 and "(open)" in t
    with pytest.raises(ValueError, match="contradicts the style plan"):
        server.chain_garment("m", "shirt", wear="closed", wait=0)


def test_job_open_poll_keeps_the_opening(monkeypatch, tmp_path):
    _job_model(monkeypatch, tmp_path, "put(stage='building')\ntime.sleep(2)\n")
    monkeypatch.setattr(server, "_chain_gate", lambda *a: None)
    t = server.chain_garment("m", "shirt", wear="open", opening=1.5, wait=0)
    assert '"opening": 1.5' in t.split("next:")[1]


def test_job_dead_worker_reads_failed(monkeypatch, tmp_path):
    _job_model(monkeypatch, tmp_path, "put(stage='building')\nimport os\nos._exit(9)\n")
    monkeypatch.setattr(server, "_chain_gate", lambda *a: None)
    t = server.chain_garment("m", "shirt", wait=15)
    assert "the worker died" in t and "rebuild" in t


def test_job_refusal_is_immediate_and_starts_nothing(monkeypatch, tmp_path):
    calls, _ = _job_model(monkeypatch, tmp_path, "")
    monkeypatch.setattr(server, "_chain_gate", lambda *a: "shirt: not built: FAIL\nnext: call_tool(\"pattern_check\")")
    assert "not built" in server.chain_garment("m", "shirt")
    assert not calls


def test_a_design_defaults_to_the_fit_it_drafts():
    from hifipushie import garment_design as gd
    assert gd.resolve({"kind": "shirt", "from": "simon"})["fit"] == "regular"
    assert gd.resolve({"kind": "shirt", "from": "simon", "fit": "slim"})["fit"] == "slim"


# ---- the pre-sim STRUCTURE gate (C279): judge the build, never the hang

class _Pat:  # (module level: the saved build pickles them, as it pickles the real ones)
    M = {"names": ["front.L"], "piece": [0, 0, 0], "F": [[0, 1, 2]]}


class _Body:
    V, T, at = np.zeros((3, 3)), np.array([[0, 1, 2]]), {"hps.L": [0.06, 0.0, 1.5]}


_SEEN: dict = {}


class _Build:
    def __init__(self, pat, body, wear, log=None):
        _SEEN["build"] += 1
        self.pat, self.body, self.log = pat, body, log
        self.X, self.reads, self.wear = np.zeros((3, 3)), {"threads": dict(_SEEN["build_threads"])}, wear

    def run(self):
        pass

    def gate_lengths(self):
        pass

    def write_job(self, jd, fabric, name=""):
        return jd

    def finish_hang(self, V):
        self.reads["threads"] = dict(_SEEN["hang_threads"])
        return np.ones((3, 3))


def _stub_worker(monkeypatch, tmp_path, verdict: str, hang_over: int = 0, build_over: int = 0):
    """cg.worker on stubs: no build, no ZOZO; the structure check answers `verdict` (a waived row passes). Returns counts."""
    import contextlib
    from hifipushie import chain_structure as cs, resources, store, zozo_hang as zh
    monkeypatch.setattr(store, "HOME", tmp_path)
    monkeypatch.setenv("HIFIPUSHIE_APPROVED", str(tmp_path / "approved.json"))
    monkeypatch.delenv("HIFIPUSHIE_PRESIM_APPROVAL", raising=False)
    monkeypatch.setattr(resources, "heavy", lambda *a, **k: contextlib.nullcontext())
    _SEEN.clear()
    _SEEN.update(hang=0, check=0, build=0, build_threads={"p99_pct": 0.5, "max_pct": 1.0, "over_cap": build_over, "faces": 100},
                 hang_threads={"p99_pct": 1.9, "max_pct": 6.1 if hang_over else 1.9, "over_cap": hang_over, "faces": 100})

    def check(X, M, bV, bT, at, wear, plan, waive):
        _SEEN["check"] += 1
        _SEEN["waive"] = waive
        ok = verdict == "PASS" or "collar_under_jaw" in (waive or {})
        rows = [{"id": "collar_under_jaw", "status": "PASS" if verdict == "PASS" else "FAIL", "stage": 1, "ours": {},
                 **({"waived": waive["collar_under_jaw"]} if verdict != "PASS" and ok else {})}]
        return {"verdict": "PASS" if verdict == "PASS" else "PASS_WAIVED" if ok else "FAIL", "rows": rows, "reads": {}}

    def run(jd, log=None, timeout=0):
        _SEEN["hang"] += 1
        return {"V": np.ones((3, 3))}, None

    monkeypatch.setattr(cg, "load_garment", lambda m, g: (_Pat(), _Body(), {}))
    monkeypatch.setattr(cg, "GarmentBuild", _Build)
    monkeypatch.setattr(cs, "check", check)
    monkeypatch.setattr(cs, "load_plan", lambda m, g: None)
    monkeypatch.setattr(zh, "run", run)
    return _SEEN


def test_structure_fail_stops_before_the_hang(monkeypatch, tmp_path):
    seen = _stub_worker(monkeypatch, tmp_path, "FAIL")
    cg.worker("m", "shirt", {"state": "closed"})
    d = cg.job_dir("m", "shirt", "closed")
    st = cg.status(d)
    assert st["stage"] == "structure_failed" and st["structure"]["verdict"] == "FAIL"
    assert seen["check"] == 1 and seen["hang"] == 0
    assert (d / "built.pkl").exists() and not (d / "final.pkl").exists()


def test_structure_pass_hangs_and_a_waiver_reaches_the_check(monkeypatch, tmp_path):
    seen = _stub_worker(monkeypatch, tmp_path, "PASS")
    monkeypatch.setenv("HIFIPUSHIE_PRESIM_APPROVAL", "optional")  # (the shipped agents' setting: no pre-sim stop)
    cg.worker("m", "shirt", {"state": "open", "waive": {"collar_tilt": "the reference is a turned head"}})
    st = cg.status(cg.job_dir("m", "shirt", "open"))
    assert st["stage"] == "done" and seen["hang"] == 1 and seen["build"] == 1
    assert seen["waive"] == {"collar_tilt": "the reference is a turned head"}


def test_structure_rows_and_waiver():
    """Rows from a style plan on stub readings: a failing row names its source and what to change; a waiver by name passes;
    no plan: one UNMEASURED row naming step 2 (C286)."""
    from hifipushie import chain_structure as cs, cloth_check as cc, garment_reads as gr
    M = {"names": ["front.L", "front.R", "back", "stand", "collar", "cuff.L"]}
    plan = {"read": {"views": [{"view": "front"}]},
            "parts": {"pieces": {"front.L": {}, "front.R": {}, "back": {}, "stand": {"stiff": True}, "collar": {"stiff": True}},
                      "closures": {"front": {"pieces": ["front.L", "front.R"]}}},
            "style": {"state": {"front": {"state": "closed", "source": "front view"}},
                      "rows": [{"id": "spread", "what": "collar_points_apart", "target": {"value": 1.0, "unit": "ratio",
                                "tol": 0.2, "of": "neck_width"}, "source": "front view"},
                               {"id": "tilt", "what": "collar_tilt", "target": {"value": 30, "unit": "deg", "tol": 5},
                                "source": "side view"}]}}
    its, _ = cs.items(M, plan)
    assert {"spread", "tilt", "collar_leaves_lie", "collar_turned", "closure_front", "closure_front_meets", "hem_level_lr",
            "soft_cloth_smooth"} <= {i["id"] for i in its}
    assert all(i["source"] and i["change"] for i in its)
    good = {"collar_points_apart_mm": 120.0, "neck_width_mm": 120.0, "collar_top_tilt_deg": 30.0,
            "collar_leaf_standoff_p90_mm": 6.0, "fall_above_stand_mm": -10.0, "closure_state:front": "closed",
            "front_met_share": 1.0, "hem_left_right_mm": 2.0, "soft_rough_over_limit": 0.5}

    def run(readings, waive=None):
        r = dict(readings)
        r["collar_points_apart_mm/neck_width_mm"] = r["collar_points_apart_mm"] / r["neck_width_mm"]
        rows = gr.checklist_rows(its, r, cs.STAGE)
        for x in rows:
            x["id"] = x["id"].split(":", 1)[1]
        return cc.verdict(rows, waive), rows
    assert run(good)[0] == "PASS"
    v, rows = run(dict(good, collar_points_apart_mm=40.0, soft_rough_over_limit=2.8))
    assert v == "FAIL" and {r["id"] for r in rows if r["status"] == "FAIL"} == {"spread", "soft_cloth_smooth"}
    assert run(dict(good, collar_top_tilt_deg=9.6), {"tilt": "the reference is a turned head"})[0] == "PASS_WAIVED"
    its0, _ = cs.items(M, None)
    assert any(i["id"] == "style_plan" and i.get("missing") for i in its0)


def test_structure_fail_answer_lists_rows_and_look_shows_the_build(monkeypatch, tmp_path):
    import pickle
    sc = {"verdict": "FAIL", "rows": [{"id": "collar_under_jaw", "status": "FAIL", "stage": 1, "ours": {"k": 12.9},
                                       "ref": [20.0, None], "source": "kind default", "change": "lower the CF neckline"},
                                      {"id": "cuff_fit", "status": "PASS", "stage": 2, "ours": {"k": 30}}]}
    _job_model(monkeypatch, tmp_path, f"put(stage='structure_failed', structure={sc!r})\n")
    monkeypatch.setattr(server, "_chain_gate", lambda *a: None)
    t = server.chain_garment("m", "shirt", wait=20)
    assert "STRUCTURE FAIL" in t and "the hang does not run" in t and "collar_under_jaw" in t
    assert "change: lower the CF neckline" in t and 'next: call_tool("look_chain"' in t and '"waive"' in t
    d = cg.job_dir("m", "shirt", "closed")
    M = {"names": ["front.L"], "piece": [0, 0, 0], "F": [[0, 1, 2]]}
    for f, x in (("built.pkl", 0.0), ("final.pkl", 1.0)):  # (a stale hung result must not be shown)
        pickle.dump({"X": np.full((3, 3), x), "M": M, "bV": np.zeros((3, 3)), "bT": np.array([[0, 1, 2]])}, open(d / f, "wb"))
    shown = []

    def views(X, M, bV, bT, out, focus=None, size=640):
        from PIL import Image
        shown.append(float(np.asarray(X).max()))
        Image.new("RGB", (8, 8)).save(out + "_front.png")
        return [("front", out + "_front.png")]
    monkeypatch.setattr(cg, "render_views", views)
    res = server.look_chain("m", "shirt")
    assert shown == [0.0] and "the BUILD (before any hang)" in res[-1]
    with pytest.raises(ValueError, match="waive"):
        server.chain_garment("m", "shirt", waive={"collar_tilt": ""})


# ---- step 7a (pre-sim approval) and step 8 (threads past the cap): T2

def _presim_model(monkeypatch, tmp_path, verdict="PASS", **kw):
    """The real tool and the real worker, in-process on the stub build; the record ready up to step 4."""
    import os
    from hifipushie import garment_record as gr, store
    seen = _stub_worker(monkeypatch, tmp_path, verdict, **kw)
    monkeypatch.setattr(store, "load", lambda n: {"bones": {}, "cloth": {"shirt": {"design": {"kind": "shirt"}}}})
    monkeypatch.setattr(server, "_chain_gate", lambda *a: None)
    for sid in ("0", "1", "2", "3", "4"):
        gr.write("m", "shirt", sid, "done", output={"n": sid})
    calls = []

    def spawn(d, name, garment, w):
        calls.append(w)
        cg.worker(name, garment, w)
        return os.getpid()
    monkeypatch.setattr(server, "_chain_spawn", spawn)
    return seen, calls


def _approve_7a(tmp_path):
    import json
    from hifipushie import garment_record as gr
    rec = gr.load("m", "shirt")
    (tmp_path / "approved.json").write_text(json.dumps({"approved": {"garment/m.shirt.7a": {
        "model": f"{gr.path('m', 'shirt')}#{rec['steps']['7a']['digest']}", "by": "joe"}}, "log": []}))


def test_presim_awaits_approval_then_resumes_from_the_saved_build(monkeypatch, tmp_path):
    from hifipushie import garment_record as gr
    seen, calls = _presim_model(monkeypatch, tmp_path)
    t = server.chain_garment("m", "shirt", wait=5)
    d = cg.job_dir("m", "shirt", "closed")
    assert cg.status(d)["stage"] == "awaiting_approval" and seen["hang"] == 0 and not (d / "final.pkl").exists()
    assert "STOPPED BEFORE THE HANG" in t and "bin/approve add garment m.shirt.7a" in t and "never approves" in t
    assert "sheet.png" in t and gr.load("m", "shirt")["steps"]["7a"]["status"] == "done"
    t = server.chain_garment("m", "shirt", wait=5)  # (not approved: the same answer, nothing started)
    assert len(calls) == 1 and "STOPPED BEFORE THE HANG" in t
    _approve_7a(tmp_path)
    t = server.chain_garment("m", "shirt", wait=5)
    assert calls[-1].get("resume") == "approved" and cg.status(d)["stage"] == "done", t
    assert seen["build"] == 1 and seen["check"] == 1 and seen["hang"] == 1  # (resumed: never rebuilt, never re-read)
    s = gr.states(gr.load("m", "shirt"))
    assert s["7a"]["status"] == "approved" and s["8"]["status"] == "done" and "built and hung" in t


def test_presim_optional_hangs_straight_away(monkeypatch, tmp_path):
    seen, calls = _presim_model(monkeypatch, tmp_path)
    monkeypatch.setenv("HIFIPUSHIE_PRESIM_APPROVAL", "optional")
    t = server.chain_garment("m", "shirt", wait=5)
    assert seen["hang"] == 1 and len(calls) == 1 and "built and hung" in t and "step 8 threads: PASS" in t


def test_a_waiver_resumes_from_the_saved_build(monkeypatch, tmp_path):
    seen, calls = _presim_model(monkeypatch, tmp_path, verdict="FAIL")
    t = server.chain_garment("m", "shirt", wait=5)
    assert "STRUCTURE FAIL" in t and seen["build"] == 1
    t = server.chain_garment("m", "shirt", wait=5, waive={"collar_under_jaw": "a turned head in the reference"})
    assert calls[-1].get("resume") == "waiver" and seen["build"] == 1 and seen["check"] == 2
    assert cg.status(cg.job_dir("m", "shirt", "closed"))["stage"] == "awaiting_approval" and "STRUCTURE PASS_WAIVED" in t
    assert seen["hang"] == 0


def test_step8_fails_on_faces_past_the_cap(monkeypatch, tmp_path):
    from hifipushie import garment_record as gr
    seen, calls = _presim_model(monkeypatch, tmp_path, hang_over=20)
    monkeypatch.setenv("HIFIPUSHIE_PRESIM_APPROVAL", "optional")
    t = server.chain_garment("m", "shirt", wait=5)
    assert "STEP 8 FAIL threads: 20 of 100 faces past the thread cap" in t and "back to step 5" in t
    assert "\n  change: " in t and "never raise the cap" in t and "next:" in t
    st = gr.load("m", "shirt")["steps"]["8"]
    assert st["status"] == "failed" and st["back_to"] == "5" and st["gate"]["rows"][0]["status"] == "FAIL"
    assert gr.next_step(gr.load("m", "shirt"))["step"] == "5"
    from hifipushie import chain_presim as cp
    g = cp.threads_gate({"stage": "done", "reads": {"threads": {"over_cap": 3, "faces": 9}}, "build_threads": {"over_cap": 2}})
    assert g["back_to"] == "5" and "already past the cap" in g["line"]


def test_the_tied_pair_an_untied_band_was_held_to_stays_through_the_soft_cloth():
    """T7: the open band is tied to the topmost tied front pair where hold_start put it; the first soft solve must hold
    it there (free, the soft cloth carried it 10 mm down and 14 mm out: the fronts' neck-to-button reach ran past cut).
    C396: that pair comes from the ties (chain_plan.first_tied); none tied, nothing more is held."""
    import types
    from hifipushie import chain_plan as cp
    b = types.SimpleNamespace(net=types.SimpleNamespace(n=6), band_hold=(1, 2))
    cg.GarmentBuild._hold_tied(b)
    assert np.where(b.extra_held)[0].tolist() == [1, 2]
    b = types.SimpleNamespace(net=types.SimpleNamespace(n=6), band_hold=None)
    cg.GarmentBuild._hold_tied(b)
    assert getattr(b, "extra_held", None) is None
    uv = {1: (0, 0.3), 3: (0, 0.2), 5: (0, 0.1)}
    fr = {"v": [(5, 6), (3, 4), (1, 2)], "closed": [True, True, False]}
    assert cp.first_tied(fr, uv) == (3, 4) and not cp.top_tied(fr, uv)
    assert cp.first_tied(dict(fr, closed=[False] * 3), uv) is None
