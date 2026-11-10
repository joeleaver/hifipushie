"""Carry later steps forward when an earlier plan step is rewritten (fix run F2, t8 finding 7).

Why: every change to step 1 (parts) marked steps 2 (style) and 3 (measure) stale, so the agent re-sent unchanged steps
by hand (3 extra calls per parts change, x3 garments). garment_record's rule (T1) stays: a step is STALE when the step
before it changed since it was written. What's new: right after garment_plan writes step N (0, 1 or 2: C390, t s2-5's
step-2 retake left step 3 stale with nothing to redo), each later done step
whose SAVED content still validates against the new steps is carried forward: re-stamped (its `inputs` set to the step
before it's current digest, `carried` = {from, t}); its digest (status + output + gate) is unchanged, so an approval and
the steps after it stay as they were. The first step that no longer validates stops the carry: it stays (or is marked)
stale with `stale_why`, the reason garment_record shows.

Validators (CHECKS): step 1 = garment_plan.check_parts on step 0; step 2 = check_style on steps 0 + 1; step 3 = every
measurement step 1 names (its `measurements`) is among step 3's taken rows; step 4 = draft_own.validate (the saved
declarations against step 1, and the drafted parts); later steps are never carried past a changed step 1 (they're builds:
rebuild). A step whose own inputs already match (step 3 after a carried step 2) is still checked: when it fails it is
marked stale (`stale_why`) though its inputs match.
"""
from __future__ import annotations

import json
import time

from . import garment_record as gr


def _check(sid: str, out: dict, rec: dict) -> str:
    """'' when step sid's saved output validates against the current earlier steps; else the reason."""
    from . import garment_plan as gp
    o = {k: rec["steps"][k].get("output") or {} for k in ("0", "1", "2", "3")}
    try:
        if sid == "1":
            gp.check_parts(out, o["0"])
        elif sid == "2":
            gp.check_style(out, o["0"], o["1"])
        elif sid == "3":
            took = {r.get("name") for r in out.get("measurements") or []}
            miss = [m for m in o["1"].get("measurements") or [] if m not in took]
            if miss:
                return f"step 1 now needs measurements step 3 hasn't taken: {', '.join(miss)} (body_tape them by name)"
        elif sid == "4":
            from . import draft_own as do
            from pathlib import Path
            dd = Path(out.get("dir") or "")
            if not (dd / "declarations.json").exists():
                return "step 4's declarations aren't on disk: draft_pattern again"
            decl = json.loads((dd / "declarations.json").read_text())
            parts = json.loads((dd / "draft.json").read_text()).get("parts") if (dd / "draft.json").exists() else None
            bad = do.validate(decl, o["1"], parts)
            if bad:
                return "the draft's declarations don't match step 1 now: " + "; ".join(bad[:3])
        else:
            return f"step {sid} is a build: run it again"
    except gp.PlanRefused as e:
        return str(e).replace("\n  ", "; ")
    return ""


def carry(model: str, garment: str, changed: str) -> list:
    """After step `changed` was rewritten: carry each later done step forward while it validates. Lines for the answer."""
    rec = gr.load(model, garment)
    ids = gr.IDS
    i = ids.index(gr._sid(changed))
    lines, moved = [], False
    for sid in ids[i + 1:]:
        st = rec["steps"][sid]
        if st.get("status") not in ("done", "failed") or not st.get("output"):
            break
        prev = ids[ids.index(sid) - 1]
        why = _check(sid, st["output"], rec)
        if why:
            st["stale_why"] = why
            lines.append(f"  step {sid} ({gr.STEP[sid]['key']}) STALE: {why}")
            moved = True
            break
        if st.get("inputs") != rec["steps"][prev].get("digest") or st.get("stale_why"):
            st["inputs"] = rec["steps"][prev].get("digest")
            st.pop("stale_why", None)
            st["carried"] = {"from": changed, "t": time.strftime("%Y-%m-%d %H:%M")}
            lines.append(f"  step {sid} ({gr.STEP[sid]['key']}) carried forward: its saved content still validates "
                         f"against the new step {changed} (not re-sent)")
            moved = True
        else:
            lines.append(f"  step {sid} ({gr.STEP[sid]['key']}) still valid")
    if moved:
        gr._save(rec)
    return lines
