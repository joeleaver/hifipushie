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
        assert "Clothes: design_garment" in t and "chain_garment" in t, (q, t)
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

def _stub_worker(monkeypatch, tmp_path, verdict: str):
    """cg.worker on stubs: no build, no ZOZO; the structure check answers `verdict`. Returns what the hang saw."""
    import contextlib
    from hifipushie import chain_structure as cs, resources, store, zozo_hang as zh
    monkeypatch.setattr(store, "HOME", tmp_path)
    monkeypatch.setattr(resources, "heavy", lambda *a, **k: contextlib.nullcontext())
    seen = {"hang": 0, "check": 0}

    class Pat:
        M = {"names": ["front.L"], "piece": [0, 0, 0], "F": [[0, 1, 2]]}

    class Body:
        V, T, at = np.zeros((3, 3)), np.array([[0, 1, 2]]), {"hps.L": [0.06, 0.0, 1.5]}

    class Build:
        def __init__(self, pat, body, wear, log=None):
            self.X, self.reads, self.wear = np.zeros((3, 3)), {}, wear

        def run(self):
            pass

        def gate_lengths(self):
            pass

        def write_job(self, jd, fabric, name=""):
            return jd

        def finish_hang(self, V):
            return np.ones((3, 3))

    def check(X, M, bV, bT, at, wear, refs, garment, waive):
        seen["check"] += 1
        seen["waive"] = waive
        rows = [{"id": "collar_under_jaw", "status": "PASS" if verdict == "PASS" else "FAIL", "stage": 1, "ours": {}}]
        return {"verdict": verdict, "rows": rows, "reads": {}}

    def run(jd, log=None, timeout=0):
        seen["hang"] += 1
        return {"V": np.ones((3, 3))}, None

    monkeypatch.setattr(cg, "load_garment", lambda m, g: (Pat(), Body(), {}))
    monkeypatch.setattr(cg, "GarmentBuild", Build)
    monkeypatch.setattr(cs, "check", check)
    monkeypatch.setattr(cs, "load_refs", lambda m: None)
    monkeypatch.setattr(zh, "run", run)
    return seen


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
    cg.worker("m", "shirt", {"state": "open", "waive": {"collar_tilt": "the reference is a turned head"}})
    st = cg.status(cg.job_dir("m", "shirt", "open"))
    assert st["stage"] == "done" and seen["hang"] == 1
    assert seen["waive"] == {"collar_tilt": "the reference is a turned head"}


def test_structure_rows_and_waiver():
    """Real items and rows on stub readings: a failing row names its source and what to change; a waiver by name passes."""
    from hifipushie import chain_structure as cs
    M = {"names": ["front.L", "front.R", "back", "stand", "collar", "cuff.L"]}
    good = {"collar_jaw_clear_mm": 40.0, "collar_top_tilt_deg": 30.0, "collar_points_below_back_top_mm": 107.0,
            "collar_points_apart_nw": 0.8, "collar_leaf_standoff_p90_mm": 6.0, "fall_above_stand_mm": -10.0,
            "front_met_share": 1.0, "front_edge_wander_mm": 3.0, "hem_left_right_mm": 2.0, "hem_cf_cb_mm": -10.0,
            "sleeve_past_wrist_mm": 15.0, "cuff_ease_mm": 30.0, "wear_collar": "closed"}
    its = cs.items(M, {"state": "closed"})
    assert {"collar_under_jaw", "collar_tilt", "collar_points_spread", "collar_leaves_lie", "front_meets",
            "front_edge_straight", "hem_level_lr", "sleeve_length", "cuff_fit"} <= {i["id"] for i in its}
    assert all(i["source"] and i["change"] for i in its)
    from hifipushie import cloth_check as cc, garment_reads as gr

    def run(readings, waive=None):
        rows = gr.checklist_rows(its, readings, cs.STAGE)
        for r in rows:
            r["id"] = r["id"].split(":", 1)[1]
        return cc.verdict(rows, waive), rows
    assert run(good)[0] == "PASS"
    v, rows = run(dict(good, collar_jaw_clear_mm=12.9, collar_points_apart_nw=0.34))
    assert v == "FAIL" and {r["id"] for r in rows if r["status"] == "FAIL"} == {"collar_under_jaw", "collar_points_spread"}
    assert run(dict(good, collar_jaw_clear_mm=12.9), {"collar_under_jaw": "a turned head"})[0] == "PASS_WAIVED"
    assert "v_depth" in {i["id"] for i in cs.items(M, {"state": "open"})}  # the V only when worn open


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
