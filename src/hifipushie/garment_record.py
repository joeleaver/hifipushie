"""The garment record (docs/state/garment_steps.md, tooling run T1): ONE file per garment holding every step's output.

workspace/<model>/garments/<garment>.json; looks and the sheet in workspace/<model>/garments/<garment>/.
Every later tool reads and writes here. Nothing in it is specific to one garment: a shirt and a hussar jacket share it.

Per step (STEPS, the one list of steps; add or rename a step here and nowhere else):
  output     what the step made, or a pointer to the file that holds it (a dict)
  status     todo / done / failed (stored); "approved" is never stored: it is READ from workspace/approved.json
  gate       {"verdict", "rows": [...]} when the step has a gate
  reference  what the step was judged against (default: step 0's reference picture)
  look       image paths of the step's own look
  back_to    on a FAIL: the step to return to (the step's default, or the writer's)
  digest     hash of output + status + gate; inputs: the digest of the step before it when it was written
A step is READY when its status is done (approved where approval is required) and it isn't stale. A step is STALE when
the step before it changed since it was written (its digest differs from the recorded inputs) or is stale itself, or
when garment_carry marked it (`stale_why`: its saved content no longer validates against a rewritten earlier step).
Carry forward (F2, garment_carry.py): when garment_plan rewrites step 0 / 1, later steps that still validate are
re-stamped (`inputs` = the new digest, `carried`) instead of left stale; their digests (and approvals) don't change.
write(N) refuses by name unless step N-1 is ready: a step consumes only the ready output of the step before it.

Approvals: Joe or the coordinator only, with the existing /mnt/data/hifipushie/bin/approve into workspace/approved.json:
  approve add garment <model>.<garment>.<step> <record path>#<digest> <sheet> joe|coordinator
An approval counts only while its digest is the step's current one (a changed step loses it). This module never
writes approved.json; write() refuses status "approved".
Step 7a (look and approve before the sim) needs approval when PRESIM_APPROVAL is "required" (the default, every
development run); env HIFIPUSHIE_PRESIM_APPROVAL=optional is the shipped agents' setting (7a then passes through).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
from pathlib import Path

from . import store

# (id, key, what the step outputs, the call that makes it or None, approval: none / required / setting, default back_to)
STEPS = [
    ("0", "read", "the reading: kind, cloth, fit; the reference picture", "garment_plan", "none", "0"),
    ("1", "parts", "every piece and detail: seen / occluded / inferred, how far built, layer order; the seams", "garment_plan", "none", "0"),
    ("2", "style", "the ONE worn state, as bends and targets; the pose", "garment_plan", "none", "1"),
    ("3", "measure", "every measurement steps 1-2 call for, by name", None, "none", "2"),
    ("4", "draft", "flat pattern + seam pairs, stiff pieces, folds, closures; the flat gate", "draft_pattern", "none", "4"),
    ("5", "chains", "the pattern's edges as exact-length chains in the planned state", "chain_garment", "none", "4"),
    ("6", "surfaces", "the garment surface; the structure gate", "chain_garment", "none", "4"),
    ("7", "details", "buttons, braid, frogging on the surface, at the pattern's marks", "garment_details", "none", "6"),
    ("7a", "presim", "the built, detailed garment beside the reference, approved before the sim", None, "setting", "6"),
    ("8", "sim", "folds only: soft cloth under gravity, stiff parts and the state held", "chain_garment", "none", "4"),
    ("9", "look", "the garment beside the reference, blind review, approval", "look_chain", "required", "4"),
    ("9a", "appearance", "materials on the pattern UVs: colour, print on the grain, stitching, wear, fray; textures", "garment_appearance", "none", "2"),
    ("10", "export", "game mesh, retopology, skinned to the rig", None, "none", "10"),
]
IDS = [s[0] for s in STEPS]
# the earlier steps a step reads beyond the one before it (T4: the draft needs step 1's seams AND step 3's measurements)
READS = {"3": ("1", "2"), "4": ("1", "3")}
STEP = {s[0]: dict(zip(("id", "key", "what", "tool", "approval", "back_to"), s)) for s in STEPS}
for _s in STEPS:
    STEP[_s[1]] = STEP[_s[0]]  # (a step by its key too: "draft" == "4")
STORED = ("todo", "done", "failed")
APPROVE = "/mnt/data/hifipushie/bin/approve"


class OrderRefused(ValueError):
    """A write to a step whose previous step isn't ready."""


def presim_approval() -> str:
    v = os.environ.get("HIFIPUSHIE_PRESIM_APPROVAL", "required")
    if v not in ("required", "optional"):
        raise ValueError(f"HIFIPUSHIE_PRESIM_APPROVAL {v!r}: \"required\" or \"optional\"")
    return v


def _sid(step) -> str:
    s = STEP.get(str(step))
    if s is None:
        raise ValueError(f"step {step!r}: one of {', '.join(IDS)} (or a key: {', '.join(x[1] for x in STEPS)})")
    return s["id"]


def _needs_approval(sid: str) -> bool:
    a = STEP[sid]["approval"]
    return a == "required" or (a == "setting" and presim_approval() == "required")


def path(model: str, garment: str) -> Path:
    if not re.fullmatch(r"[A-Za-z0-9_\-.]+", garment):
        raise ValueError("garment names may only contain letters, digits, _ - and .")
    return store._dir(model) / "garments" / f"{garment}.json"


def look_dir(model: str, garment: str) -> Path:
    d = path(model, garment).with_suffix("")
    d.mkdir(parents=True, exist_ok=True)
    return d


def load(model: str, garment: str) -> dict:
    p = path(model, garment)
    rec = json.loads(p.read_text()) if p.exists() else {"model": model, "garment": garment, "steps": {}}
    for sid in IDS:
        rec["steps"].setdefault(sid, {"status": "todo"})
    return rec


def _save(rec: dict) -> Path:
    p = path(rec["model"], rec["garment"])
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(f".tmp{os.getpid()}")
    tmp.write_text(json.dumps(rec, indent=1, default=str))
    tmp.replace(p)
    return p


def _digest(st: dict) -> str:
    keep = {k: st.get(k) for k in ("status", "output", "gate")}
    return hashlib.sha1(json.dumps(keep, sort_keys=True, default=str).encode()).hexdigest()[:12]


def _approvals() -> dict:
    p = Path(os.environ.get("HIFIPUSHIE_APPROVED") or store.HOME / "approved.json")
    try:
        return json.loads(p.read_text()).get("approved") or {}
    except (OSError, ValueError):
        return {}


def piece(model: str, garment: str, sid: str) -> str:
    return f"{model}.{garment}.{sid}"


def approval(rec: dict, sid: str, approved: dict | None = None) -> dict | None:
    """The approval of this step's CURRENT output (approved.json's garment/<model>.<garment>.<step>), or None."""
    a = (approved if approved is not None else _approvals()).get(f"garment/{piece(rec['model'], rec['garment'], sid)}")
    st = rec["steps"][sid]
    if not a or st.get("status") != "done" or not str(a.get("model", "")).endswith("#" + str(st.get("digest"))):
        return None
    return a


def states(rec: dict, approved: dict | None = None) -> dict:
    """{step: {"status": todo/done/failed/approved, "stale": bool, "ready": bool, "why": ...}} in step order."""
    approved = _approvals() if approved is None else approved
    out, prev = {}, None
    for sid in IDS:
        st = rec["steps"][sid]
        status = st.get("status", "todo") if st.get("status") in STORED else "todo"  # (a stored "approved" is ignored)
        ok = approval(rec, sid, approved)
        if ok:
            status = "approved"
        stale = bool(prev and status != "todo" and (out[prev]["stale"] or bool(st.get("stale_why")) or
                     st.get("inputs") != rec["steps"][prev].get("digest")))
        if sid == "7a" and not _needs_approval(sid) and status == "todo":  # (optional pre-sim approval: passes through)
            ready, why = bool(prev and out[prev]["ready"]), "optional (HIFIPUSHIE_PRESIM_APPROVAL=optional)"
        else:
            ready = (status == "approved" or (status == "done" and not _needs_approval(sid))) and not stale
            why = (f"stale: {st['stale_why']}" if stale and st.get("stale_why") else
                   "stale: the step before it changed" if stale else
                   "done; waits for approval (Joe or the coordinator)" if status == "done" and not ready else "")
        out[sid] = {"status": status, "stale": stale, "ready": ready, "why": why}
        prev = sid
    return out


def write(model: str, garment: str, step, status: str, output: dict | None = None, gate: dict | None = None,
          reference: str | None = None, look: list | None = None, back_to: str | None = None, by: str = "") -> dict:
    """Write one step's result. Refused (OrderRefused, naming the step) unless the step before it is ready."""
    sid = _sid(step)
    if status == "approved":
        raise PermissionError("approvals are Joe's or the coordinator's: " + approve_cmd(load(model, garment), sid))
    if status not in STORED:
        raise ValueError(f"status {status!r}: one of {', '.join(STORED)}")
    rec = load(model, garment)
    i = IDS.index(sid)
    if i:
        prev = IDS[i - 1]
        s = states(rec)[prev]
        if not s["ready"]:
            raise OrderRefused(f"{model}:{garment}: step {sid} ({STEP[sid]['key']}) refused: step {prev} "
                               f"({STEP[prev]['key']}) is not ready ({s['status']}{'; ' + s['why'] if s['why'] else ''})")
    st = {"status": status, "output": output or {}, "t": time.strftime("%Y-%m-%d %H:%M"), "by": by}
    if gate:
        st["gate"] = {"verdict": gate.get("verdict"), "rows": [_row(r) for r in gate.get("rows") or []]}
    ref = reference or (rec["steps"]["0"].get("reference") if sid != "0" else None)
    if ref:
        st["reference"] = str(ref)
    if look:
        st["look"] = [str(p) for p in look]
    if status == "failed":
        st["back_to"] = _sid(back_to or STEP[sid]["back_to"])
    if i:
        st["inputs"] = rec["steps"][IDS[i - 1]].get("digest")
    st["digest"] = _digest(st)
    was = rec["steps"][sid]
    if _digest(was) == was.get("digest") == st["digest"] and was.get("inputs") == st.get("inputs"):  # (the same result again: kept, its
        st = dict(was, **{k: st[k] for k in ("look", "reference") if k in st})  # approval with it; a new look attached)
    rec["steps"][sid] = st
    _save(rec)
    return st


def attach_look(model: str, garment: str, step, paths: list) -> None:
    """A look of a step that is already written (no change to its output, so its approval holds)."""
    sid = _sid(step)
    rec = load(model, garment)
    if rec["steps"][sid].get("status", "todo") == "todo":
        return
    rec["steps"][sid]["look"] = [str(p) for p in paths]
    _save(rec)


def _row(r: dict) -> dict:
    return {k: r[k] for k in ("id", "status", "value", "target", "why", "fix", "back_to", "waived") if k in r}


def approve_cmd(rec: dict, sid: str, sheet: str = "<sheet>") -> str:
    st = rec["steps"][sid]
    return (f"{APPROVE} add garment {piece(rec['model'], rec['garment'], sid)} "
            f"{path(rec['model'], rec['garment'])}#{st.get('digest')} {sheet} joe|coordinator")


def next_step(rec: dict, approved: dict | None = None) -> dict:
    """{"step", "why", "uses", "call"}: the first step that isn't ready, what it may use, and the call that makes it."""
    s = states(rec, approved)
    for i, sid in enumerate(IDS):
        if s[sid]["ready"]:
            continue
        st = rec["steps"][sid]
        if s[sid]["status"] == "failed" and not s[sid]["stale"]:
            b = st.get("back_to") or STEP[sid]["back_to"]
            return {"step": b, "why": f"step {sid} ({STEP[sid]['key']}) FAILED: back to step {b} ({STEP[b]['key']})",
                    "uses": _uses(rec, b), "call": _call(rec, b)}
        if s[sid]["status"] == "done" and not s[sid]["stale"]:
            return {"step": sid, "why": f"step {sid} ({STEP[sid]['key']}) waits for approval", "uses": _uses(rec, sid),
                    "call": "Joe or the coordinator, after the look: " + approve_cmd(rec, sid)}
        return {"step": sid, "why": f"step {sid} ({STEP[sid]['key']}): {s[sid]['why'] or s[sid]['status']}",
                "uses": _uses(rec, sid), "call": _call(rec, sid)}
    return {"step": None, "why": "every step is ready", "uses": None, "call": None}


def _uses(rec: dict, sid: str) -> dict | None:
    i = IDS.index(sid)
    u = {"step": IDS[i - 1], **rec["steps"][IDS[i - 1]].get("output", {})} if i else None
    if u is not None and READS.get(sid):
        u["reads"] = {s: rec["steps"][s].get("output", {}) for s in READS[sid] if s != IDS[i - 1]}
    return u


def reads(model: str, garment: str, step) -> dict:
    """{step: output} of every earlier step this one reads (READS, else the step before it). Refused by name (OrderRefused)
    when one isn't ready: a step consumes only ready outputs."""
    sid = _sid(step)
    rec = load(model, garment)
    i = IDS.index(sid)
    want = READS.get(sid) or ((IDS[i - 1],) if i else ())
    s = states(rec)
    for w in want:
        if not s[w]["ready"]:
            raise OrderRefused(f"{model}:{garment}: step {sid} ({STEP[sid]['key']}) reads step {w} ({STEP[w]['key']}), "
                               f"which is not ready ({s[w]['status']}{'; ' + s[w]['why'] if s[w]['why'] else ''})")
    return {w: rec["steps"][w].get("output", {}) for w in want}


def _call(rec: dict, sid: str) -> str:
    t = STEP[sid]["tool"]
    if sid == "7a":
        return ("chain_garment writes it after a structure PASS (stage awaiting_approval); then the build's look beside the "
                "reference and approval by Joe or the coordinator: " + approve_cmd(rec, sid))
    if not t:
        return f"no tool writes step {sid} ({STEP[sid]['key']}) yet: see docs/state/garment_steps.md"
    a = {"name": rec["model"], "garment": rec["garment"]}
    if t == "garment_plan":
        a.update(step=STEP[sid]["key"], plan="{...}")  # (the plan's form: guide(topic="garment_plan"))
    return f"call_tool(\"{t}\", {json.dumps(a)})"


def answer(model: str, garment: str) -> str:
    """The text of the garment_record tool: every step's status, what's stale, what's next and its call."""
    rec = load(model, garment)
    s = states(rec)
    lines = [f"{model}:{garment} garment record ({path(model, garment)})"]
    for sid in IDS:
        st, x = rec["steps"][sid], s[sid]
        g = st.get("gate") or {}
        bad = [r["id"] for r in g.get("rows") or [] if r.get("status") in ("FAIL", "UNMEASURED") and not r.get("waived")]
        lines.append(f"  {sid:>3} {STEP[sid]['key']:<9} {x['status']:<9}" + (" STALE" if x["stale"] else "") +
                     (f" gate {g.get('verdict')}" if g else "") + (f" failing: {', '.join(bad[:6])}" if bad else "") +
                     (f" back_to {st['back_to']}" if x["status"] == "failed" else "") +
                     (f" ({x['why']})" if x["why"] and (not x["stale"] or st.get("stale_why")) else "") +
                     (f" (carried forward after step {st['carried']['from']} changed)" if st.get("carried") and not x["stale"] else ""))
    stale = [sid for sid in IDS if s[sid]["stale"]]
    if stale:
        lines.append(f"  stale (an earlier step changed; write them again): {', '.join(stale)}")
    lines.append(f"  pre-sim approval (7a): {presim_approval()}")
    n = next_step(rec)
    if n["step"] is None:
        return "\n".join(lines + ["next: nothing: every step is ready"])
    lines.append(f"  {n['why']}; it uses: {json.dumps(n['uses'], default=str)[:300] if n['uses'] else 'nothing before it'}")
    return "\n".join(lines + [f"next: {n['call']}"])


def sheet(model: str, garment: str, size: int = 360) -> Path:
    """One sheet per garment: the step-0 reference beside every look the record holds; a tile of every step's status."""
    from PIL import Image, ImageDraw
    from .render import contact_sheet
    rec = load(model, garment)
    s = states(rec)
    ims, frames = [], []

    def tile(p):
        im = Image.open(p).convert("RGB")
        im.thumbnail((size, size))
        bg = Image.new("RGB", (size, size), (30, 31, 35))
        bg.paste(im, ((size - im.size[0]) // 2, (size - im.size[1]) // 2))
        return bg
    ref = rec["steps"]["0"].get("reference")
    if ref and Path(ref).exists():
        ims.append(tile(ref)), frames.append({"name": "reference (step 0)", "axes": None})
    for sid in IDS:
        for p in (rec["steps"][sid].get("look") or [])[:1]:
            if Path(p).exists():
                ims.append(tile(p)), frames.append({"name": f"step {sid} {STEP[sid]['key']}: {s[sid]['status']}",
                                                    "axes": None})
    txt = Image.new("RGB", (size, size), (30, 31, 35))
    d = ImageDraw.Draw(txt)
    from .pattern_sheet import _font  # (large: a glance tile; every status is also in answer's text, C288)
    fs = _font(max(12, min(22, (size - 16) // len(IDS) - 4)))
    for k, sid in enumerate(IDS):
        x = s[sid]
        d.text((8, 8 + (size - 16) // len(IDS) * k), f"{sid} {STEP[sid]['key']} {x['status']}" + (" STALE" if x["stale"] else ""),
               fill=(235, 235, 235) if x["ready"] else (230, 150, 120), font=fs)
    ims.append(txt), frames.append({"name": "steps", "axes": None})
    out = look_dir(model, garment) / "sheet.png"
    contact_sheet(ims, frames).save(out)
    return out


# --- the existing tools write here (each catches a refusal: the tool still works, its answer names the refusal) ---

def _try(fn, *a, **k) -> str:
    try:
        fn(*a, **k)
        return ""
    except OrderRefused as e:
        return f"record: {e}"


def from_pattern_check(model: str, garment: str, rec: dict, gate_path: str = "", flat=None) -> str:
    """pattern_check (step 4's gate): its verdict and rows; the flat sheet as the step's look."""
    look = []
    if flat is not None:
        look = [str(look_dir(model, garment) / "step4_flat.png")]
        flat.save(look[0])
    ok = rec.get("status") in ("PASS", "PASS_WAIVED")
    return _try(write, model, garment, "4", "done" if ok else "failed", by="pattern_check", look=look,
                output={"gate_record": str(gate_path), "kind": rec.get("kind"), "pattern": rec.get("pattern")},
                gate={"verdict": rec.get("status"), "rows": rec.get("rows")})


def from_chain(model: str, garment: str, wear: str, d: Path, st: dict) -> str:
    """chain_garment's worker at its end: step 5 (the chains), 6 (structure rows), 8 (the hang)."""
    stage, sc = st.get("stage"), st.get("structure") or {}
    out = {"job": str(d), "wear": wear, "build": st.get("build_id")}
    msgs = []
    if stage == "refused" and not (d / "final.pkl").exists():
        return _try(write, model, garment, "5", "failed", output=dict(out, refused=st.get("refused")), by="chain_garment")
    if stage not in ("structure_failed", "presim", "awaiting_approval", "done", "refused"):
        return ""
    msgs.append(_try(write, model, garment, "5", "done", output=dict(out, built=str(d / "built.pkl")), by="chain_garment"))
    from .chain_structure import passed
    msgs.append(_try(write, model, garment, "6", "done" if passed(sc) else "failed", by="chain_garment",
                     output=dict(out, built=str(d / "built.pkl")), gate={"verdict": sc.get("verdict"), "rows": sc.get("rows")}))
    if stage in ("done", "refused") and (d / "final.pkl").exists():  # (step 8: its gate is the threads reading, T2)
        from .chain_presim import threads_gate
        g = threads_gate(st) or {}
        ok = stage == "done" and g.get("verdict") != "FAIL"
        msgs.append(_try(write, model, garment, "8", "done" if ok else "failed", by="chain_garment", gate=g or None,
                         back_to=g.get("back_to") if g.get("verdict") == "FAIL" else None,
                         output=dict(out, hung=str(d / "final.pkl"), refused=st.get("refused"), reads=st.get("reads"))))
    return "; ".join(m for m in msgs if m)


def from_look_chain(model: str, garment: str, wear: str, hung: bool, paths: list) -> str:
    """look_chain: the build's look goes on step 6; the hung garment's look is step 9's output (then approval)."""
    if not hung:
        attach_look(model, garment, "6", paths)
        attach_look(model, garment, "7a", paths)  # (the build is what 7a approves)
        return ""
    return _try(write, model, garment, "9", "done", output={"wear": wear, "views": [str(p) for p in paths]},
                look=paths, by="look_chain")


if __name__ == "__main__":
    import sys
    print(answer(sys.argv[1], sys.argv[2]))
    if "--sheet" in sys.argv:
        print(sheet(sys.argv[1], sys.argv[2]))
