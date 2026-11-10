"""The garment record (T1): order refusal, stale marking, approvals read-only, the tool's answer, the existing tools
writing it. Cheap: no builds, no hangs; one sheet."""
import contextlib
import json
import pickle

import pytest
from PIL import Image

from hifipushie import garment_record as gr, store


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "HOME", tmp_path)
    monkeypatch.setenv("HIFIPUSHIE_APPROVED", str(tmp_path / "approved.json"))
    monkeypatch.delenv("HIFIPUSHIE_PRESIM_APPROVAL", raising=False)
    ref = tmp_path / "ref.png"
    Image.new("RGB", (40, 60), (200, 40, 40)).save(ref)
    return tmp_path


def _approve(home, model, garment, sid):
    """What bin/approve add writes (the coordinator's act, done here by hand for the test)."""
    rec = gr.load(model, garment)
    p = home / "approved.json"
    d = json.loads(p.read_text()) if p.exists() else {"approved": {}, "log": []}
    d["approved"][f"garment/{gr.piece(model, garment, sid)}"] = {
        "model": f"{gr.path(model, garment)}#{rec['steps'][sid]['digest']}", "sheet": "s", "by": "joe", "date": "", "note": ""}
    p.write_text(json.dumps(d))


def _upto(home, model, garment, last):
    for sid in gr.IDS[:gr.IDS.index(last) + 1]:
        if sid == "0":
            gr.write(model, garment, "0", "done", output={"kind": "jacket"}, reference=str(home / "ref.png"))
        else:
            gr.write(model, garment, sid, "done", output={"n": sid})
        if gr._needs_approval(sid):
            _approve(home, model, garment, sid)


def test_order_refused_by_name(home):
    with pytest.raises(gr.OrderRefused, match=r"step 4 \(draft\) refused: step 3 \(measure\) is not ready"):
        gr.write("m", "hussar", "4", "done")
    _upto(home, "m", "hussar", "3")
    gr.write("m", "hussar", "draft", "done", output={"pattern": "p1"})
    assert gr.states(gr.load("m", "hussar"))["4"]["ready"]


def test_stale_and_back_to(home):
    _upto(home, "m", "shirt", "6")
    gr.write("m", "shirt", "4", "done", output={"pattern": "altered"})
    s = gr.states(gr.load("m", "shirt"))
    assert not s["4"]["stale"] and s["5"]["stale"] and s["6"]["stale"] and not s["6"]["ready"]
    assert gr.next_step(gr.load("m", "shirt"))["step"] == "5"
    gr.write("m", "shirt", "5", "done", output={"n": "5b"})
    gr.write("m", "shirt", "6", "failed", gate={"verdict": "FAIL", "rows": [{"id": "collar_tilt", "status": "FAIL"}]})
    n = gr.next_step(gr.load("m", "shirt"))
    assert n["step"] == "4" and "FAILED" in n["why"] and n["call"].startswith('call_tool("draft_pattern"')  # (step 4's tool, T5)


def test_approval_read_only(home):
    _upto(home, "m", "shirt", "7")
    with pytest.raises(PermissionError, match="bin/approve add garment m.shirt.7a"):
        gr.write("m", "shirt", "7a", "approved")
    gr.write("m", "shirt", "7a", "done")
    rec = json.loads(gr.path("m", "shirt").read_text())
    rec["steps"]["7a"]["status"] = "approved"  # (a hand-edited record is not an approval)
    gr.path("m", "shirt").write_text(json.dumps(rec))
    assert gr.states(gr.load("m", "shirt"))["7a"]["status"] == "todo"
    gr.write("m", "shirt", "7a", "done")
    with pytest.raises(gr.OrderRefused, match="7a"):
        gr.write("m", "shirt", "8", "done")
    assert "waits for approval" in gr.next_step(gr.load("m", "shirt"))["why"]
    _approve(home, "m", "shirt", "7a")
    gr.write("m", "shirt", "8", "done")  # (approved: the sim may use it)
    gr.write("m", "shirt", "7a", "done", output={"changed": 1})  # a changed 7a loses its approval
    assert gr.states(gr.load("m", "shirt"))["7a"]["status"] == "done"


def test_presim_setting(home, monkeypatch):
    _upto(home, "m", "jacket", "7")
    monkeypatch.setenv("HIFIPUSHIE_PRESIM_APPROVAL", "optional")
    gr.write("m", "jacket", "8", "done")
    monkeypatch.setenv("HIFIPUSHIE_PRESIM_APPROVAL", "required")
    assert not gr.states(gr.load("m", "jacket"))["7a"]["ready"]


def test_tool_answer_and_sheet(home):
    from hifipushie import server
    _upto(home, "m", "shirt", "4")
    txt = server.garment_record("m", "shirt")
    assert "  4 draft     done" in txt and "step 5 (chains)" in txt and 'next: call_tool("chain_garment"' in txt
    look = home / "look.png"
    Image.new("RGB", (50, 50), (40, 200, 40)).save(look)
    gr.attach_look("m", "shirt", "4", [look])
    ims = server.garment_record("m", "shirt", sheet=True)
    p = gr.look_dir("m", "shirt") / "sheet.png"
    assert p.exists() and "sheet:" in ims[-1] and Image.open(p).size[0] > 360


def test_pattern_check_writes_step4(home, monkeypatch):
    from hifipushie import cloth_check as cc, next_steps, pattern_sheet, server
    rec = {"status": "FAIL", "kind": "shirt", "pattern": "ph", "body": "bh", "rows": [{"id": "seam_pairs", "status": "FAIL"}]}

    def gate(name, garment, refs=None, waive=None, log=None, keep=None):
        keep["res"] = {"pieces_full": {}}
        return rec
    monkeypatch.setattr(cc, "pattern_gate", gate)
    monkeypatch.setattr(cc, "seams", lambda *a: [])
    monkeypatch.setattr(pattern_sheet, "render", lambda *a, **k: Image.new("RGB", (30, 30)))
    monkeypatch.setattr(next_steps, "after_pattern_check", lambda *a: "next: x")
    out = server.pattern_check("m", "shirt", diag=False)
    assert "record: m:shirt: step 4 (draft) refused" in out[-1]
    _upto(home, "m", "shirt", "3")
    server.pattern_check("m", "shirt", diag=False)
    st = gr.load("m", "shirt")["steps"]["4"]
    assert st["status"] == "failed" and st["back_to"] == "4" and st["gate"]["rows"][0]["id"] == "seam_pairs"
    assert st["look"][0].endswith("step4_flat.png")


def test_chain_worker_writes_steps_5_6_8(home, monkeypatch):
    from hifipushie import chain_garment as cg, resources
    _upto(home, "m", "shirt", "4")
    monkeypatch.setattr(resources, "heavy", lambda *a, **k: contextlib.nullcontext())

    def refuse(*a):
        raise cg.ChainRefused("front.L 3 % off its cut")
    monkeypatch.setattr(cg, "load_garment", refuse)
    cg.worker("m", "shirt", {"state": "closed"})
    st = gr.load("m", "shirt")["steps"]["5"]
    assert st["status"] == "failed" and "3 %" in st["output"]["refused"]
    d = cg.job_dir("m", "shirt", "closed")
    (d / "final.pkl").write_bytes(b"x")
    gr.from_chain("m", "shirt", "closed", d, {"stage": "done", "structure": {"verdict": "PASS", "rows": [{"id": "a", "status": "PASS"}]}})
    s = gr.states(gr.load("m", "shirt"))
    assert s["5"]["ready"] and s["6"]["ready"] and s["8"]["status"] == "todo"  # (8 refused: steps 7, 7a not ready)
    msg = gr.from_chain("m", "shirt", "closed", d, {"stage": "done", "structure": {"verdict": "PASS", "rows": []}})
    assert "step 8 (sim) refused: step 7a (presim)" in msg


def test_look_chain_writes_step9(home, monkeypatch):
    from hifipushie import chain_garment as cg, server
    _upto(home, "m", "shirt", "8")
    d = cg.job_dir("m", "shirt", "closed")
    cg.write_status(d, stage="done", structure={"verdict": "PASS", "rows": []})
    pickle.dump({"X": None, "M": {"names": ["front.L"]}, "bV": None, "bT": None}, open(d / "final.pkl", "wb"))

    def views(X, M, bV, bT, out, focus=None, size=640):
        p = f"{out}_front.png"
        Image.new("RGB", (20, 20)).save(p)
        return [("front", p)]
    monkeypatch.setattr(cg, "render_views", views)
    server.look_chain("m", "shirt")
    rec = gr.load("m", "shirt")
    assert rec["steps"]["9"]["status"] == "done" and rec["steps"]["9"]["look"][0].endswith("_front.png")
    assert "waits for approval" in gr.next_step(rec)["why"]


def test_a_steps_saved_output_is_shown_and_step_3_carries_after_a_step_2_rewrite(home, monkeypatch):  # (t s2-5; C390)
    from hifipushie import garment_carry as gc, server
    _upto(home, "tm", "g", "3")
    assert '"n": "2"' in server.garment_record("tm", "g", step="2")
    gr.write("tm", "g", "2", "done", output={"n": "2", "fixed": True})
    assert gr.states(gr.load("tm", "g"))["3"]["stale"]
    monkeypatch.setattr(gc, "_check", lambda sid, out, rec: "")  # (step 3's saved content still validates)
    gc.carry("tm", "g", "2")
    assert not gr.states(gr.load("tm", "g"))["3"]["stale"]
