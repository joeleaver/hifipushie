"""Clothes, the one path: garment_plan -> body_tape -> draft_pattern (pattern_parts, pattern_check) -> chain_garment
-> garment_details -> look_chain -> garment_appearance -> export_garment; garment_record shows every step."""
from __future__ import annotations

import json
import os
from pathlib import Path

from PIL import Image as PILImage

from . import store
from .mcp_app import mcp
from .tool_common import _out, _spec_arg

def _save_suffix(save: str | None, tag: str) -> str | None:
    if not save:
        return None
    p = Path(save)
    return str(p.with_name(f"{p.stem}_{tag}{p.suffix or '.png'}"))


@mcp.tool(structured_output=False)
def pattern_check(name: str, garment: str):
    """STEP 4's FLAT GATE AGAIN, on a garment drafted with draft_pattern: the general flat gate re-read from the saved
    draft and step 4 rewritten (chain_garment refuses without its PASS). Returns the per-row table and the next step.
    Details: guide(topic="pattern_check")."""
    if not _own_draft(name, garment):
        raise ValueError(f"{garment} on {name} has no draft of its own to check: step 4 is draft_pattern (your own "
                         "FreeSewing design and its declarations), which runs this gate itself")
    from . import draft_own_tool as dot  # (drafted with draft_pattern: the general flat gate, re-read: T5)
    return dot.check_text(name, garment)


def _chain_gate(name: str, garment: str, spec: dict) -> str | None:
    """None when the garment may be built; else the refusal, naming the next step."""
    if garment not in (spec.get("cloth") or {}):
        return (f"no garment {garment!r} on {name} (have {', '.join(spec.get('cloth') or {}) or 'none'}).\nnext: a garment "
                f"starts at its reading: call_tool(\"garment_plan\", {{\"name\": \"{name}\", \"garment\": \"{garment}\", "
                "\"step\": \"read\", ...})")
    if (spec["cloth"][garment].get("pattern") or {}).get("from") != "own":
        return (f"{garment}: it has no draft of its own (step 4), and a garment is built only from one.\nnext: "
                f"call_tool(\"draft_pattern\", {{\"name\": \"{name}\", \"garment\": \"{garment}\", ...}})")
    from . import garment_record as gr  # (draft_pattern: step 4's flat gate, T5)
    v = ((gr.load(name, garment)["steps"]["4"].get("gate") or {}).get("verdict"))
    return None if v == "PASS" else (f"{garment}: step 4's flat gate is {v or 'not run'}.\nnext: call_tool("
                                     f"\"pattern_check\", {{\"name\": \"{name}\", \"garment\": \"{garment}\"}})")


def _chain_text(st: dict) -> str:
    r = st.get("reads") or {}
    c = r.get("chains") or {}
    t = r.get("threads") or {}
    lines = []
    if c:
        lines.append(f"  chains: {c.get('links')} links; free worst {c.get('free_worst_pct')} % ({c.get('free_worst_line')}), p99 "
                     f"{c.get('free_p99_pct')} %; {c.get('gathered_links')} gathered into stiff parts (held longest over "
                     f"{c.get('held_longest_over_pct')} %)")
    if t:
        lines.append(f"  threads (warp / weft): p99 {t.get('p99_pct')} %, max {t.get('max_pct')} %, {t.get('over_cap')} of {t.get('faces')} faces past the cap")
    for p_, how_ in (r.get("starts") or {}).items():  # (F4: where each piece started, from its own measurements)
        lines.append(f"  start {p_}: {how_}")
    if "seam_gap_mm" in r:
        lines.append(f"  seams: largest gap {r['seam_gap_mm']} mm; pattern truing {r.get('seam_truing')}")
    if r.get("band"):
        lines.append(f"  band: {r['band']}")
    if r.get("band_open"):
        lines.append(f"  band open: {r['band_open']}")
    if r.get("plackets"):
        lines.append(f"  plackets: {r['plackets']}")
    if r.get("rings"):
        lines.append(f"  rings: {r['rings']}")
    if r.get("hang_moved_mm"):
        lines.append(f"  hang: moved {r['hang_moved_mm']}; before the last lengths {r.get('after_hang_before_lengths')}")
    return "\n".join(lines)


def _tag(wear: str | None) -> str:
    """The wear in an answer's head: none when the style plan decides it (C418, t s5-2: an open jacket read "(closed)")."""
    return f" ({wear})" if wear else ""


def _chain_call(name: str, garment: str, wear: str | None, opening: float | None = None, **more) -> str:
    args = {"name": name, "garment": garment, **({"wear": wear} if wear else {})}
    if opening is not None:
        args["opening"] = opening
    return f"call_tool(\"chain_garment\", {json.dumps(dict(args, **more))})"


def _chain_spawn(d, name: str, garment: str, w: dict) -> int:
    """The worker, its own process under bin/capped: a hang never blocks the server. Returns its pid."""
    import subprocess
    import sys
    cmd = [sys.executable, "-m", "hifipushie.chain_garment", name, garment, json.dumps(w)]
    capped = "/mnt/data/hifipushie/bin/capped"
    cmd = ([capped] if os.path.exists(capped) else []) + cmd
    return subprocess.Popen(cmd, stdout=open(d / "worker.log", "w"), stderr=subprocess.STDOUT, start_new_session=True,
                            env=dict(os.environ, HIFIPUSHIE_HOME=str(store.HOME))).pid


@mcp.tool(structured_output=False)
def chain_garment(name: str, garment: str, wear: str | None = None, opening: float | None = None, wait: float = 50.0,
                  rebuild: bool = False, waive: dict | None = None):
    """START A GARMENT: the only way to dress a character, fit or drape clothes on a body. Built from the pattern as chains of its lengths, straight
    into the record's style plan (each closure's state, the collar spread); without a plan, wear "closed" | "open" and
    opening (points apart, neck widths); a contradicting wear is refused. Needs pattern_check's PASS. A JOB: build, a
    STRUCTURE check beside the reference, pre-sim approval (Joe's), then the hang. Call again with the same arguments to
    poll or resume; rebuild=True starts over; waive={row: why} accepts failing rows. Answers end in next:.
    guide(topic="chain_garment")."""
    import time as _t
    from . import chain_garment as cg
    from . import chain_plan, chain_structure as _cs
    if wear not in (None, "closed", "open"):
        raise ValueError(f"wear {wear!r}: \"closed\" or \"open\" (or none: the style plan's)")
    if opening is not None and wear == "closed":
        raise ValueError("opening is how far an open collar opens: only with wear=\"open\"")
    if opening is not None and not 1.0 <= float(opening) <= 2.6:
        raise ValueError(f"opening {opening}: collar points apart in neck widths, 1.0 .. 2.6 (default 1.7)")
    if not 0 <= float(wait) <= 280:
        raise ValueError(f"wait {wait}: seconds, 0 .. 280; call again for the stage")
    spec = store.load(name)
    if garment not in (spec.get("cloth") or {}):
        return _chain_gate(name, garment, spec)
    w = chain_plan.planned_wear(_cs.load_plan(name, garment), wear, opening)  # (T7: the plan wins; raises on a contradiction)
    job = w["state"]  # (the job's folder; the answers name a wear only when no style plan decides it: C418)
    wear = None if "plan" in w else job
    from . import chain_layers as _cl
    try:  # (worn over another garment: its approved build is the collider, part of the job key; T9)
        under = _cl.under_for(name, garment)
    except _cl.LayerRefused as e:
        return f"{name}:{garment}: refused (layering): {e}"
    if under:
        w["under"] = under
    if waive:
        if not isinstance(waive, dict) or not all(isinstance(v, str) and v.strip() for v in waive.values()):
            raise ValueError("waive: {structure row id: the reason it is accepted}, each reason a sentence")
        w["waive"] = {str(k): str(v) for k, v in waive.items()}
    key = cg.job_key(spec, garment, w, ((_cs.load_plan(name, garment) or {}).get("style") or {}).get("blockin"))  # (F10)
    d = cg.job_dir(name, garment, job)
    st = cg.live_status(d)
    if st.get("stage") in cg.RUNNING:
        if st.get("key") != key or rebuild:  # (two workers in one folder would write over each other)
            return (f"{name}:{garment}{_tag(wear)}: a job of a different pattern or opening is at stage {st['stage']}; it ends first.\n"
                    f"next: {_chain_call(name, garment, wear, opening)} when this one has ended")
    elif st.get("key") != key or rebuild:
        refused = _chain_gate(name, garment, spec)
        if refused:
            return refused
        for f in ("status.json", "built.pkl", "final.pkl"):
            (d / f).unlink(missing_ok=True)
        cg.write_status(d, stage="queued", key=key, wear=w, t0=_t.time())
        cg.write_status(d, pid=_chain_spawn(d, name, garment, w))
    else:  # (step 7a approved, or a new waiver: the same call resumes from the saved build, never rebuilds; T2)
        from . import chain_presim as cp
        why = cp.resume_wanted(name, garment, d, st, w)
        if why:
            cg.write_status(d, stage="queued", wear=w, t0=_t.time(), resumed=why, note="")
            cg.write_status(d, pid=_chain_spawn(d, name, garment, dict(w, resume="waiver" if "waiver" in why else "approved")))
    t0 = _t.time()
    st = cg.live_status(d)
    while st.get("stage") in cg.RUNNING and _t.time() - t0 < float(wait):
        _t.sleep(min(2.0, float(wait)))
        st = cg.live_status(d)
    return _cl.with_answer(_chain_answer(name, garment, wear, st, opening, job=job), st)


def _chain_answer(name: str, garment: str, wear: str | None, st: dict, opening: float | None = None,
                  job: str | None = None) -> str:
    """Every answer of the job names the next call."""
    from . import chain_garment as cg
    look = f"call_tool(\"look_chain\", {{\"name\": \"{name}\", \"garment\": \"{garment}\", \"wear\": \"{job or wear}\"}})"
    stage = st.get("stage", "queued")
    again = _chain_call(name, garment, wear, opening)
    if stage == "refused":
        sc = st.get("structure") or {}
        bad = [r["id"] for r in sc.get("rows") or [] if r["status"] in ("FAIL", "UNMEASURED") and not r.get("waived")]
        more = f"\n  structure (the build, read before the refusal): {sc.get('verdict')}; failing: {', '.join(bad)}" if sc else ""
        return (f"{name}:{garment}{_tag(wear)}: refused: {st.get('refused')}{more}\nnext: fix it in your draft (draft_pattern runs the flat gate), "
                f"then {again}")
    if stage == "stage_failed":  # (F5: the build stopped at a stage's gate: start, chains or surfaces)
        from . import chain_stages as cst
        return cst.answer(name, garment, wear, st, again, look)
    if stage == "structure_failed":
        from . import chain_structure as cs
        sc = st.get("structure") or {}
        bad = [r for r in sc.get("rows") or [] if r["status"] in ("FAIL", "UNMEASURED") and not r.get("waived")]
        ok = [r["id"] for r in sc.get("rows") or [] if r["status"] == "PASS"]
        return (f"{name}:{garment}{_tag(wear)}: built; STRUCTURE {sc.get('verdict')}: the hang does not run ({len(bad)} rows "
                f"fail; pass: {', '.join(ok) or 'none'})\n" + "\n".join(cs.row_line(r) for r in bad) +
                f"\nnext: {look} to see the build beside your reference; then each row's change (in your draft: draft_pattern, "
                f"then {again}); a row the reference can't decide: {again[:-2]}, \"waive\": {{\"<row id>\": "
                f"\"<why>\"}}}})")
    if stage == "awaiting_approval":
        from . import chain_presim as cp
        return cp.awaiting_text(name, garment, wear, st, f"{name}:{garment}{_tag(wear)}: built; STRUCTURE "
                                f"{(st.get('structure') or {}).get('verdict')}\n{_chain_text(st)}", again, look)
    if stage == "failed":
        return (f"{name}:{garment}{_tag(wear)}: the build failed: {st.get('error')}\nnext: report this to the coordinator as a tool "
                f"fault, with the text above; don't work round it. {_chain_call(name, garment, wear, opening, rebuild=True)} starts over")
    head = {"queued": "starting", "building": "building", "resuming": "resuming from the saved build (no rebuild)", "built": "built; the structure check is reading the build", "hanging": "built; the hang is running",
            "hung": "hung; the last lengths are being read", "done": "built and hung"}.get(stage, stage)
    head += f" ({cg.elapsed(st)} s)" if stage != "done" else ""
    if st.get("note"):
        head += f"; {st['note']}"
    body = _chain_text(st)
    sc = st.get("structure")
    if sc:
        body = (f"  structure: {sc.get('verdict')} ({len(sc.get('rows') or [])} rows" +
                (f"; waived: {', '.join(r['id'] for r in sc['rows'] if r.get('waived'))}" if any(r.get("waived") for r in sc.get("rows") or []) else "")
                + ")" + (f"\n{body}" if body else ""))
    txt = f"{name}:{garment}{_tag(wear)}: {head}" + (f"\n{body}" if body else "") + (f"\n  {st['record']}" if st.get("record") else "")
    if stage == "done":
        from . import chain_presim as cp
        g = cp.threads_gate(st)
        if g and g["verdict"] == "FAIL":
            return (f"{txt}\n{g['line']}\nnext: {look} to find where the cloth is pulled; then back to step {g['back_to']} "
                    f"as the change: line says (the cap is the cloth's, never a setting)")
        return f"{txt}" + (f"\n{g['line']}" if g else "") + f"\nnext: {look} beside your reference; review_view one view per call"
    if stage in ("queued", "building"):
        return f"{txt}\nnext: {again} for the stage; nothing to look at yet"
    return f"{txt}\nnext: {again} for the stage; {look} shows the build until the hang ends"


@mcp.tool(structured_output=False)
def look_chain(name: str, garment: str, wear: str = "closed", focus: str | None = None, size: int = 640,
               reference: str | None = None, save: str | None = None):
    """Look at a chain_garment result: the build until its structure check passed and the hang ended, then the hung garment
    (said in the text). focus:
    none = the whole figure on the body (front, three, side, back); "neck" = the collar close, on the body; a piece's name
    (collar, stand, cuff.L, ...) = that piece ALONE, large, four sides. reference: a picture's path, shown beside each view.
    Returns the views + numbers. Details: guide(topic="look_chain")."""
    import pickle
    from . import chain_garment as cg
    if wear not in ("closed", "open"):
        raise ValueError(f"wear {wear!r}: \"closed\" or \"open\"")
    d = cg.job_dir(name, garment, wear)
    st = cg.status(d)
    if not st:
        return f"no chain build of {garment} ({wear}).\nnext: call_tool(\"chain_garment\", {{\"name\": \"{name}\", \"garment\": \"{garment}\", \"wear\": \"{wear}\"}})"
    if st.get("stage") == "stage_failed" and (d / "stage.pkl").exists():  # (F5: the failing stage's own look)
        from . import chain_stages as cst
        paths = [tuple(p) for p in st.get("stage_look") or []] or cst.look(d, size=size)
        return [_out(PILImage.open(p).convert("RGB"), _save_suffix(save, nm) if save else None) for nm, p in paths] + [
            _chain_answer(name, garment, wear, st).split("\nnext:")[0] + f"\n  shown: the {st.get('stage_failed')} STAGE "
            "(the build stopped there; red: the tapes it was measured on)\nnext: fix it where its rows say; chain_garment again"]
    from . import chain_structure as cs
    hung_ok = (d / "final.pkl").exists() and cs.passed(st.get("structure"))  # (C279: the build until its structure passed)
    src = d / "final.pkl" if hung_ok else (d / "built.pkl" if (d / "built.pkl").exists() else None)
    if src is None:
        return _chain_answer(name, garment, wear, st)
    r = pickle.load(open(src, "rb"))
    names = list(r["M"]["names"])
    if focus is not None and focus != "neck" and focus not in names:
        raise ValueError(f"focus {focus!r}: \"neck\" or a piece: {', '.join(names)}")
    tag = f"{garment}_{wear}" + (f"_{focus}" if focus else "")
    paths = cg.render_views(r["X"], r["M"], r["bV"], r["bT"], str(d / tag), focus=focus, size=size)
    ims = []
    refim = PILImage.open(reference).convert("RGB") if reference else None
    for nm, p in paths:
        im = PILImage.open(p).convert("RGB")
        if refim is not None:
            h = im.size[1]
            rr = refim.resize((int(refim.size[0] * h / refim.size[1]), h))
            sh = PILImage.new("RGB", (rr.size[0] + im.size[0] + 6, h), "white")
            sh.paste(rr, (0, 0))
            sh.paste(im, (rr.size[0] + 6, 0))
            im = sh
        ims.append(_out(im, _save_suffix(save, nm) if save else None))
    plan = cs.load_plan(name, garment) if focus is None else None
    if ((plan or {}).get("style") or {}).get("traces") and r.get("at"):  # (T15, C299: the step-2 traces vs this outline, on the reference)
        from . import structure_outline as so, structure_outline_look as sol
        ms = so.measure(r["X"], r["M"], r["at"], plan)
        for vi in sorted({m["trace"].get("view", 0) for m in ms}):
            p = sol.sheet([m for m in ms if m["trace"].get("view", 0) == vi], plan["read"]["views"][vi]["image"],
                          str(d / f"{tag}_outline_v{vi}.png"))
            ims.append(_out(PILImage.open(p).convert("RGB"), None))
            paths.append((f"outline_v{vi}", p))
    txt = _chain_answer(name, garment, wear, st).split("\nnext:")[0]
    txt += f"\n  shown: {'the hung garment' if src.name == 'final.pkl' else 'the BUILD (before any hang)'}"
    if focus is None:  # (the garment record: the build's look on step 6, the hung garment's as step 9)
        from . import garment_record as gr
        refused = gr.from_look_chain(name, garment, wear, src.name == "final.pkl", [p for _, p in paths])
        txt += f"\n  {refused}" if refused else ""
    return ims + [txt + f"\n  views: {', '.join(p for _, p in paths)}\nnext: judge beside your reference (review_view, one view per "
                  "call); a fault: fix it in your draft (draft_pattern), then chain_garment again; close views: focus=\"neck\" or a "
                  "piece's name"]


@mcp.tool(structured_output=False)
def garment_record(name: str = "", garment: str = "", sheet: bool = False, step: str = ""):
    """THE GARMENT RECORD: one file per garment holding every step's output, status (todo / done / failed / approved),
    gate rows, reference and look (docs/state/garment_steps.md, steps 0-10 + 7a). Answers each step's status, what is
    stale (an earlier step changed), the next step, what it may use (the step before it, ready only) and the call that
    makes it. A step is written only when the step before it is ready; approvals are Joe's or the coordinator's
    (bin/approve), read here, never written. sheet=True: the step-0 reference beside every look, and the statuses.
    step="2": that step's saved output in full (JSON), to retake it changing only what's refused. Details: guide(topic="garment_record")."""
    from . import garment_record as gr
    for given in (name, garment):  # ("garrett:jacket" in either: t s1-2 was refused for it)
        if ":" in given and not (name and garment and ":" not in name + garment):
            name, _, garment = given.partition(":")
            break
    if not name or not garment:
        return "garment_record: name (the model) and garment, or one 'model:garment' (e.g. 'garrett:jacket')"
    if step:  # (C390, t s2-5: a retake had to read the record's file to resend the old plan unchanged)
        rec = gr.load(name, garment)
        sid = gr._sid(step)
        st = rec["steps"].get(sid) or {}
        return (f"{name}:{garment} step {sid} ({gr.STEP[sid]['key']}), status {st.get('status', 'todo')}; its saved output "
                f"(resend it with only the refused part changed):\n" + json.dumps(st.get("output") or {}, indent=1, default=str))
    txt = gr.answer(name, garment)
    if not sheet:
        return txt
    p = gr.sheet(name, garment)
    return [_out(PILImage.open(p).convert("RGB"), None), txt + f"\n  sheet: {p}"]


@mcp.tool(structured_output=False)
def body_tape(name: str, measurements: list | None = None, garment: str = "", landmarks: bool = False, add: bool = False):
    """MEASURE A BODY BY NAME (garment step 3): each measurement your garment's seams call for, named and defined by
    you: girth (at a level, square to the body or a limb), arc (over the surface between landmarks), length (surface or
    straight, via landmarks; down to a level), height, or a FreeSewing name as a string. Answers each in mm with how it
    was taken, and the tape lines drawn on the body. No measurements, or landmarks=True: the landmarks and levels you can
    name. garment: writes step 3 of its record; add=True (with garment): keep step 3's measurements and add only these.
    Details: guide(topic="body_tape")."""
    from . import body_tape as bt
    look, txt = bt.run(name, _spec_arg(measurements) if measurements else None, garment, landmarks, add)
    return txt if look is None else [_out(PILImage.open(look).convert("RGB"), None), txt]


@mcp.tool(structured_output=False)
def garment_plan(name: str, garment: str, step: str, plan: dict | str, look: bool = True):
    """STEPS 0-2 OF A GARMENT (the record's start, any garment): step="read" (kind: a short name; cloth as numbers; fit as RATIOS marked on the picture, applied to the model's body),
    "parts" (every piece and detail: seen / occluded / inferred, how far built, stiff, layer; the seams, each with the
    body measurements or style proportion its length needs; over: the garments it is worn over) or "style" (the ONE worn state per closure, bends, pose,
    the rows the photo judges). plan: that step's dict; every at / outline is PIXELS of its view. Refused by name;
    else written with a look over the reference; later steps that still validate are carried. guide(topic="garment_plan")"""
    from . import garment_plan as gp
    r = gp.write(name, garment, step, _spec_arg(plan) if isinstance(plan, str) else plan, look=look)
    txt = gp.text(name, garment, r)
    return [_out(PILImage.open(p_).convert("RGB"), None) for p_ in r["look"][:2]] + [txt] if r["look"] else txt


def _own_draft(name: str, garment: str) -> bool:
    try:
        return ((store.load(name).get("cloth") or {}).get(garment, {}).get("pattern") or {}).get("from") == "own"
    except ValueError:  # (no model: pattern_gate says so in its own words)
        return False


@mcp.tool(structured_output=False)
def draft_pattern(name: str, garment: str, design: str, declarations: dict | str, options: dict | None = None,
                  sa: float = 10.0):
    """STEP 4: YOUR OWN PATTERN. design: a FreeSewing design you write (JS module on @freesewing/core, usually parts
    `from:` brian / bent / jaeger; ends `export default new Design({...})`), drafted in Node (sandboxed, timeout) with
    step 3's measurements by name. declarations: what it can't draw, in step 1's names: pieces, edges, seams (+ ease,
    why), stiff, folds, closures, omit. Refused by name when they don't match step 1; else the flat gate (seams, cut,
    sewn, closures), the flat sheet with seam pairs and step 4 written. guide(topic="draft_pattern")."""
    from . import draft_own_tool as dot
    sheet, txt = dot.run(name, garment, design, _spec_arg(declarations) if isinstance(declarations, str) else declarations,
                         options, sa)
    return [_out(PILImage.open(sheet).convert("RGB"), None), txt] if sheet else txt


@mcp.tool(structured_output=False)
def garment_toile(name: str, garment: str, declarations: dict | str):
    """STEP 4: THE TOILE, the garment's 3D surface on the body (drape first): the body + step 0's ease per fit level
    (calibrated to the planned girths), shaped by the parts you declare: parts [sleeves, opening, lapel, pad],
    hang_from (a step-0 level or "none"), armhole {length_mm}, sleeves {ease_mm [top, wrist], crown_mm, hem},
    opening {lap_mm, edge (a step-2 trace), buttons}, lapel {roll, top (traces), width_mm}, pad {thickness_mm}.
    Refused by name when one is missing. Gate rows (girths, clearance, closed, outline vs step 2's traces), the look
    (4 views beside the reference), step 4 written. guide(topic="garment_toile")."""
    from . import toile_tool
    sheet, txt = toile_tool.run(name, garment, _spec_arg(declarations) if isinstance(declarations, str) else declarations)
    return [_out(PILImage.open(sheet).convert("RGB"), None), txt] if sheet else txt


@mcp.tool(structured_output=False)
def pattern_parts(design: str, name: str = "", garment: str = "", part: str = "", options: dict | None = None,
                  look: bool = False):
    """SEE A FREESEWING DESIGN before you declare its edges. design: a pack design name (brian, bent, jaeger, carlton,
    simon, teagan) or your own design's source. Lists every part it drafts (HIDDEN bases, from / after), the
    measurements it needs, its options (default, range) and each part's seam outline as point names in order; part=:
    that part's points (x, y mm) and every path in order (look=True: its outline, names large). name + garment: drafted
    with step 3's measurements. guide(topic="pattern_parts")"""
    from . import pattern_parts as pp
    p_, txt = pp.run(design, name, garment, part, options, look)
    return [_out(PILImage.open(p_).convert("RGB"), None), txt] if p_ else txt


@mcp.tool(structured_output=False)
def garment_details(name: str, garment: str, details: dict | str, wear: str = "open", look: bool = True):
    """STEP 7: DETAILS AND TRIMS at the pattern's MARKS (positions are marked at step 4: draft_pattern declarations.marks;
    a closure's buttons are its own). details: {step-1 detail: {kind point|line|motif, size_mm | width_mm, thickness_mm,
    shape, colour}}: geometry only. Made on the latest chain build (wear), carried onto the hung garment (never
    simulated); writes step 7 (+ 7a). Refused by name: a detail not inventoried, omitted, cloth-made (a piece) or
    unmarked. Returns the look (shape) + every detail's count, marks, sizes. guide(topic="garment_details")"""
    from . import garment_details_tool as gdt
    looks, txt = gdt.run(name, garment, _spec_arg(details) if isinstance(details, str) else details, wear, look)
    return [_out(PILImage.open(p_).convert("RGB"), None) for p_ in looks] + [txt] if looks else txt


@mcp.tool(structured_output=False)
def export_garment(name: str, garment: str, wear: str = "open", role: str = "main_npc", look: bool = True):
    """STEP 10: a chain garment as a GAME ASSET: the hung garment (else the build) re-gridded on its FLAT PATTERN (UVs =
    the pattern) at the density that fits the role's clothing budget (budgets.json), step 7's details as their own
    meshes, skinned to the rig with weights read off the body; one GLB. Refused by name: step 9 not approved; over
    budget at the coarsest grid (says what to change). Also writes <garment>_LOD1..3.glb (the same re-grid, coarser:
    export_asset takes them). Writes step 10. Returns the look (EEVEE, rest + the bend poses beside the reference,
    then the LODs) + triangles vs budget, UV stretch, the bend check, each LOD's count. guide(topic="export_garment")"""
    from . import garment_export_tool as get
    looks, txt = get.run(name, garment, wear, role, look)
    return [_out(PILImage.open(p_).convert("RGB"), None) for p_ in looks] + [txt] if looks else txt


@mcp.tool(structured_output=False)
def garment_appearance(name: str, garment: str, appearance: dict | None = None, wear: str = "open",
                       role: str = "main_npc", look: bool = True):
    """STEP 9a: the garment's MATERIAL painted on its flat pattern (the export's UVs): base colour per cloth (step 0),
    the print at its repeat on each piece's grain, stitching along seams and hems, wear at the body's high points and
    free edges, frayed hems, colour variation; amounts from step 2's appearance block (or `appearance`), restrained by
    default. Bakes base / roughness / normal at the role's texture size; export_garment uses them. Writes step 9a.
    Returns the EEVEE look beside the reference + every layer's numbers. guide(topic="garment_appearance")"""
    from . import garment_appearance_tool as gat
    looks, txt = gat.run(name, garment, _spec_arg(appearance) if isinstance(appearance, str) else appearance, wear, role, look)
    return [_out(PILImage.open(p_).convert("RGB"), None) for p_ in looks] + [txt] if looks else txt
