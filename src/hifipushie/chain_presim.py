"""PRE-SIM APPROVAL and THE THREADS GATE of a chain_garment job (docs/state/garment_steps.md steps 7a and 8; tooling run T2).

Step 7a: nothing is hung that wasn't approved built. After a structure PASS (or PASS_WAIVED) the worker writes the garment
record's steps 5, 6, 7 (a pass-through until a details step exists) and 7a (the build, its look), then:
  - HIFIPUSHIE_PRESIM_APPROVAL=optional (shipped agents): hangs straight away;
  - "required" (the default, every development run): unless 7a is already approved (the same build, digest and all), the
    job ends at stage "awaiting_approval" with the build saved (built.pkl holds the whole build). Joe or the coordinator
    approves 7a (garment_record.approve_cmd); agents can't. The SAME chain_garment call then RESUMES: the worker loads the
    build from built.pkl, re-reads the structure (cheap) and hangs. It never rebuilds.
A structure waiver resumes the same way: the waiver is not in the job key, so waiving re-reads the saved build.

Step 8: the hang's threads reading (faces past the thread cap, p99 / max strain) is its gate. Any face past the cap FAILS
(nothing may stretch past the cloth's cap; the cap is the cloth's, never a setting). back_to: step 5 when the build itself
was already past the cap (the chains start stretched); otherwise the cause can't be told from the numbers: step 5 too,
said as unknown. Nothing here is specific to one garment."""
from __future__ import annotations

import hashlib
import pickle
from pathlib import Path

import numpy as np

from . import garment_record as gr

AWAIT = "awaiting_approval"


# ---- the saved build (built.pkl): what look_chain shows, plus the whole build for the resume

def save_build(d: Path, b, pat, body, fabric) -> str:
    """built.pkl: the arrays look_chain reads + the build itself (the resume's input). Returns the build's id (a hash of
    its positions: the same build keeps its approval, a changed one loses it)."""
    log, b.log = b.log if hasattr(b, "log") else None, None  # (a log callable doesn't pickle)
    r = {"X": b.X, "M": pat.M, "bV": body.V, "bT": body.T, "reads": b.reads, "fabric": fabric, "build": b,
         "at": {k: np.asarray(v).tolist() for k, v in body.at.items()}}
    try:
        try:
            pickle.dump(r, open(Path(d) / "built.pkl", "wb"))
        except (pickle.PicklingError, TypeError, AttributeError) as e:  # (the look survives; a resume then says why not)
            r["build"], r["build_error"] = None, f"{type(e).__name__}: {e}"
            pickle.dump(r, open(Path(d) / "built.pkl", "wb"))
    finally:
        b.log = log
    return hashlib.sha1(np.ascontiguousarray(np.asarray(b.X, float)).tobytes()).hexdigest()[:12]


def load_build(d: Path, log=None) -> tuple:
    """(build, M, body arrays, fabric) from built.pkl. Refused by name when it isn't there or holds no build."""
    p = Path(d) / "built.pkl"
    if not p.exists():
        raise FileNotFoundError(f"no saved build in {d}: start over with rebuild=True")
    r = pickle.load(open(p, "rb"))
    if r.get("build") is None:
        raise ValueError(f"{p} holds no build to resume ({r.get('build_error') or 'written before T2'}): a tool fault; "
                         "report it; rebuild=True starts over")
    b = r["build"]
    b.log = log or (lambda *_: None)
    return b, r


# ---- step 7a

def write_presim(model: str, garment: str, wear: str, d: Path, st: dict) -> str:
    """Steps 7 (pass-through: no details step yet) and 7a (the build beside the reference) after a structure pass.
    Returns the record's refusal text, or ""."""
    out = {"job": str(d), "wear": wear, "build": st.get("build_id"), "built": str(Path(d) / "built.pkl")}
    msgs = [gr._try(gr.write, model, garment, "7", "done", by="chain_garment",
                    output=dict(out, details=[], note="no details step yet (T10): passed through"))]
    look = gr.load(model, garment)["steps"]["6"].get("look") or []
    sc = st.get("structure") or {}
    msgs.append(gr._try(gr.write, model, garment, "7a", "done", by="chain_garment", look=look,
                        output=dict(out, structure=sc.get("verdict"),
                                    waived=[r["id"] for r in sc.get("rows") or [] if r.get("waived")])))
    return "; ".join(m for m in msgs if m)


def presim_ready(model: str, garment: str) -> tuple:
    """(may the hang run, why). Optional setting: always. Required: only when the record's 7a is ready (approved)."""
    if gr.presim_approval() == "optional":
        return True, "pre-sim approval optional (HIFIPUSHIE_PRESIM_APPROVAL=optional)"
    s = gr.states(gr.load(model, garment))["7a"]
    if s["ready"]:
        return True, "step 7a approved"
    return False, f"step 7a (presim) {s['status']}" + (f": {s['why']}" if s["why"] else "")


def gate_presim(model: str, garment: str, wear: str, d: Path, st: dict) -> tuple:
    """The worker after a structure pass: write 7 + 7a, then (hang?, why, record message)."""
    msg = write_presim(model, garment, wear, d, st)
    ok, why = presim_ready(model, garment)
    return ok, why, msg


def resume_wanted(model: str, garment: str, d: Path, st: dict, w: dict) -> str:
    """Why the same call resumes a finished job from its saved build, or "" (it just answers)."""
    if not (Path(d) / "built.pkl").exists():
        return ""
    stage = st.get("stage")
    new_waive = (w.get("waive") or {}) != ((st.get("wear") or {}).get("waive") or {})
    if stage == "structure_failed" and new_waive:
        return "a waiver: the structure re-read on the saved build"
    if stage == AWAIT and (new_waive or presim_ready(model, garment)[0]):
        return "approved: the hang from the saved build" if not new_waive else "a waiver: the structure re-read on the saved build"
    return ""


def awaiting_text(model: str, garment: str, wear: str, st: dict, head: str, again: str, look: str) -> str:
    """The answer at awaiting_approval: the look, the sheet, the exact approve command; agents can't approve."""
    rec = gr.load(model, garment)
    s = gr.states(rec)["7a"]
    lines = [head, f"  STOPPED BEFORE THE HANG: step 7a (look and approve before the sim) is {s['status']}"
             f"{' (STALE)' if s['stale'] else ''}; the build is saved: the hang resumes from it, never rebuilds"]
    sheet = st.get("sheet")
    if sheet:
        lines.append(f"  sheet (the reference beside the build): {sheet}")
    if rec["steps"]["7a"].get("status") == "done" and not s["stale"]:
        lines.append(f"  approval (Joe or the coordinator ONLY; an agent never approves): "
                     f"{gr.approve_cmd(rec, '7a', sheet or '<sheet>')}")
    else:
        lines.append("  approval can't be given yet: the record doesn't hold this build's steps up to 7a "
                     f"({st.get('record') or s['why'] or 'see garment_record'}); next for the record: "
                     f"{gr.next_step(rec)['call']}")
    return ("\n".join(lines) + f"\nnext: {look} to see the build beside your reference; then hand the build's look and the "
            f"sheet to Joe or the coordinator for approval (you can't approve it: don't run the approve command). Once "
            f"approved, {again} resumes the hang from the saved build")


# ---- step 8: threads past the cap

def threads_gate(st: dict) -> dict | None:
    """Step 8's gate from the hang's threads reading: {verdict, rows, back_to, change, line}; None before a hang."""
    t = (st.get("reads") or {}).get("threads") if st.get("stage") in ("done", "refused") else None
    if not t:
        return None
    over, faces = int(t.get("over_cap") or 0), int(t.get("faces") or 0)
    built = int((st.get("build_threads") or {}).get("over_cap") or 0)
    value = f"{over} of {faces} faces past the thread cap; p99 {t.get('p99_pct')} %, max {t.get('max_pct')} %"
    if over == 0:
        return {"verdict": "PASS", "rows": [{"id": "threads_past_cap", "status": "PASS", "value": value, "target": "0 faces"}],
                "back_to": None, "change": "", "line": f"  step 8 threads: PASS: {value}"}
    if built:
        why = f"the build was already past the cap ({built} faces) before any hang: the chains start stretched"
        change = ("find the stretched piece (look_chain focus=<piece> on the build), then fix it in the chains (step 5) or "
                  "its pattern; never raise the cap: it is the cloth's")
    else:
        why = "the hang stretched them (the build had none past the cap); which step causes it can't be told from the numbers"
        change = ("look_chain on the hung garment, find where the cloth is pulled tight (a piece too small for the body, "
                  "or held too far), fix it in the chains (step 5) or the pattern (step 4); never raise the cap: it is the cloth's")
    row = {"id": "threads_past_cap", "status": "FAIL", "value": value, "target": "0 faces", "why": why, "fix": change,
           "back_to": "5"}
    return {"verdict": "FAIL", "rows": [row], "back_to": "5", "change": change,
            "line": f"  STEP 8 FAIL threads: {value}; {why}; back to step 5\n  change: {change}"}
