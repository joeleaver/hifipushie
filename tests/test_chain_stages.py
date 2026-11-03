"""F5 (chain_stages.py): the chain build gates each stage where it ends, cheapest first, and stops at the first FAIL.
On F4's synthetic two-legged body: a clean start passes START (each tube round its loops, .R the .L's mirror, nothing
through the body); a misplaced .R start fails it; a chain past its cut fails CHAINS; a torn or crumpled surface fails
SURFACES; the job ends `stage_failed` at that stage with its rows, and the record shows the stage."""
import numpy as np
import pytest

from hifipushie import chain_garment as cg, chain_stages as cst
from test_piece_start import LEG, _build, _cyl

PIECES = {"front.L": LEG, "back.L": LEG, "front.R": LEG, "back.R": LEG}
SEWS = [("front.L", 0, "back.L", 0), ("front.L", 5, "back.L", 5), ("front.R", 0, "back.R", 0), ("front.R", 5, "back.R", 5)]


def _legs():
    """F4's two tubes on two legs alone (no torso: a tube run up into a torso is a start through the body, its own row)."""
    b = _build(PIECES, {p: ["thigh", "knee", "outseam"] for p in PIECES}, SEWS)
    Vs, Fs, k = [], [], 0
    for cx in (0.10, -0.10):
        V, F = _cyl(cx, 0.07, 0.02, 1.15)
        Vs.append(V), Fs.append(F + k)
        k += len(V)
    b.body = cg.Body(np.concatenate(Vs), np.concatenate(Fs), b.body.at)
    return b


def test_a_tube_run_up_into_the_torso_starts_through_the_body():
    b = _build(PIECES, {p: ["thigh", "knee", "outseam"] for p in PIECES}, SEWS)  # (F4's body: legs + torso)
    g = cst.gate_start(b, b.soft_start())
    assert _flagged(g) == {"inside"} and "GAP" in next(r for r in g["rows"] if r["id"].startswith("inside"))["source"]


def _fails(g):
    return {r["id"].split(":")[0] for r in g["rows"] if r["status"] == "FAIL"}


def _flagged(g):  # (FAIL, or a provisional row's "INFO (would FAIL)": chain_stages.PROVISIONAL, not yet calibrated)
    return {r["id"].split(":")[0] for r in g["rows"] if r["status"] in ("FAIL", "INFO (would FAIL)")}


def test_a_clean_start_passes_and_the_right_side_is_the_lefts_mirror():
    b = _legs()
    X = b.soft_start()
    g = cst.gate_start(b, X)
    assert g["verdict"] == "PASS", [r for r in g["rows"] if r["status"] == "FAIL"]
    ids = {r["id"] for r in g["rows"]}
    assert {"round:back.L,front.L@thigh", "round:back.R,front.R@knee", "mirror:front", "inside:front.R"} <= ids
    assert b.reads["starts"]["mirrored"] == ["front.R from front.L", "back.R from back.L"]
    v = b.net.verts("front.R")
    assert np.allclose(X[v, 0].mean(), -X[b.net.verts("front.L"), 0].mean(), atol=1e-6)


def test_a_misplaced_start_fails_start_by_row():
    b = _legs()
    X = b.soft_start()
    v = b.net.verts("front.R")
    X[v] += [0.20, 0.0, 0.0]  # (the right leg's front panel started over the left leg)
    g = cst.gate_start(b, X)
    assert g["verdict"] == "FAIL" and g["back_to"] == "5"
    assert {"mirror", "round"} <= _fails(g)
    X2 = b.soft_start()
    v = b.net.verts("back.L")
    X2[v, 0] = 0.10 + (X2[v, 0] - 0.10) * 0.3  # (pulled in round its leg's axis: inside the leg)
    X2[v, 1] *= 0.3
    assert "inside" in _flagged(cst.gate_start(b, X2))


def test_the_build_stops_at_the_first_failing_stage():
    b = _legs()
    b.soft_start = (lambda f: (lambda: f() + np.where(np.isin(np.arange(b.net.n), b.net.verts("front.R"))[:, None],
                                                       [0.2, 0.0, 0.0], 0.0)))(b.soft_start)
    with pytest.raises(cst.StageFailed) as e:
        b.soft_net()
    assert e.value.stage == "start" and list(b.reads["stages"]) == ["start"]
    assert e.value.build is b and b.stage_X[0] == "start"


def _solved():
    """A clean build in report mode: every stage read, none stopping it; the stages' X kept."""
    b = _legs()
    b.stage_gates = "report"
    seen = {}
    real = cst.GATES.copy()
    for s in cst.STAGES:
        cst.GATES[s] = (lambda s: lambda bb, X: (seen.__setitem__(s, X.copy()), real[s](bb, X))[1])(s)
    try:
        b.soft_net()
    finally:
        cst.GATES.update(real)
    return b, seen


def test_chains_gate_reads_lengths_and_fails_a_chain_past_its_cut():
    b, seen = _solved()
    assert list(b.reads["stages"]) == list(cst.STAGES)
    g = cst.gate_chains(b, seen["chains"])
    row = next(r for r in g["rows"] if r["id"] == "length")
    assert row["status"] == "PASS" and "MAX_FREE_PCT" in row["source"]
    X = seen["chains"].copy()
    k = int(b.net.link_i[0])
    X[b.net.root == b.net.root[k]] += [0.0, -0.08, 0.0]  # (one chain node pulled 8 cm: its links past their cut)
    g = cst.gate_chains(b, X)
    assert g["verdict"] == "FAIL" and "length" in _fails(g)


def test_surfaces_gate_fails_a_hole_and_a_crumple():
    b, seen = _solved()
    Z = seen["surfaces"]
    g = cst.gate_surfaces(b, Z)
    assert g["verdict"] == "PASS", [r for r in g["rows"] if r["status"] == "FAIL"]
    v = b.net.verts("back.L")
    inner = v[~cst.chain_vertices(b.net)[v]]
    X = Z.copy()
    X[inner[len(inner) // 2]] += [0.0, 0.0, 0.3]  # (one point torn away: its faces open)
    assert "holes" in _flagged(cst.gate_surfaces(b, X))
    rng = np.random.default_rng(0)
    X = Z.copy()
    X[inner] += rng.normal(0, 0.01, (len(inner), 3))  # (the lay crumpled)
    g = cst.gate_surfaces(b, X)
    assert "soft_cloth_smooth" in _fails(g) and g["back_to"] == "6"


def test_the_job_ends_stage_failed_and_the_record_shows_the_stage(monkeypatch, tmp_path):
    from test_chain_garment import _Build, _stub_worker
    seen = _stub_worker(monkeypatch, tmp_path, "PASS")

    class _Net:
        link_i, link_j, M = np.array([0]), np.array([1]), {"names": ["front.L"], "piece": [0, 0, 0], "F": [[0, 1, 2]]}

    class _Failing(_Build):
        def run(self):
            self.net, self.stage_X = _Net(), ("start", np.zeros((3, 3)))
            g = cst.verdict("start", [cst._row("mirror:front", 120.0, 4.5, False, "spec", "the .R start")])
            e = cst.StageFailed("start", g)
            e.build = self
            raise e

    monkeypatch.setattr(cg, "GarmentBuild", _Failing)
    monkeypatch.setattr(cst, "look", lambda d, **k: [("front", str(tmp_path / "front.png"))])
    rec = {}
    from hifipushie import garment_record as gr
    monkeypatch.setattr(gr, "write", lambda *a, **k: rec.update(step=a[2], status=a[3], **k) or {})
    cg.worker("m", "trousers", {"state": "closed"})
    d = cg.job_dir("m", "trousers", "closed")
    st = cg.status(d)
    assert st["stage"] == "stage_failed" and st["stage_failed"] == "start" and seen["check"] == 0 and seen["hang"] == 0
    assert (d / "stage.pkl").exists() and not (d / "built.pkl").exists()
    assert rec["step"] == "5" and rec["status"] == "failed" and rec["gate"]["stage"] == "start" and rec["back_to"] == "5"
    txt = cst.answer("m", "trousers", "closed", st, "AGAIN", "LOOK")
    assert "stage_failed: start" in txt and "FAIL mirror:front" in txt and "back to step 5" in txt and "LOOK" in txt
