"""Step 2's check (garment_plan "style"): the form is garment_plan's docstring (STEP 2); refused BY NAME, every refusal
ending with the full form and the row and trace kinds (C351)."""
from __future__ import annotations

import json

from . import structure_rows as sr
from .garment_plan import PlanRefused, _src, _target, _uv_list, form, pixel_errors


def check_style(p: dict, read: dict, parts: dict) -> dict:
    bad, p = [], json.loads(json.dumps(p))
    nv = len(read.get("views") or [])
    pieces, details, closures = (parts.get(k) or {} for k in ("pieces", "details", "closures"))
    from . import closure_ties as ct
    ct.check(p, closures, bad, _src)  # (R1 C391: which fastenings are done up, never a named state)
    names = set(pieces) | set(details) | set(closures)
    kinds = {r.get("id"): r.get("what") for r in p.get("rows") or [] if isinstance(r, dict)}
    for i, b in enumerate(p.get("bends") or []):
        w = f"bends[{i}] {b.get('id', '')}".strip()
        if str(b.get("on", "")).split(":")[0] not in names:
            bad.append(f"{w}.on {b.get('on')!r}: not a piece, detail or closure of the inventory")
        _target(b.get("target"), w, bad)
        _src(b, w, bad)
        if b.get("what") is not None or "value" in (b.get("target") or {}):  # (C286: a numeric bend is judged too)
            sr.check_row(b, w, bad, kinds)
    from .garment_appearance import check_plan  # (T14: the appearance block: amounts from the story, step 9a reads it)
    bad += check_plan(p.get("appearance"), list((read.get("cloth") or {})), list((parts.get("details") or {})))
    lay = p.get("layers")  # (T12: how a garment worn over another layers it: chain_press.py)
    if lay is not None and not (isinstance(lay, dict) and lay.get("mode") in ("visible", "full")
                                and (lay["mode"] == "visible" or str(lay.get("why") or "").strip())):
        bad.append("layers: {mode: visible (default: the garment under kept where seen) | full (the whole garment under "
                   "fitted inside and hung with this one), why (needed for full: it comes off at runtime, a close-up)}")
    pose = p.get("pose")
    if not isinstance(pose, dict) or not pose.get("name"):
        bad.append("pose: {name (e.g. 'arms down, relaxed'), source}")
    else:
        _src(pose, "pose", bad)
    rows = p.get("rows")
    if not isinstance(rows, list) or not rows:
        bad.append("rows: [{id, what, target, source}] what the reference photo judges (the structure gate's targets)")
        rows = []
    ids = [r.get("id") for r in rows]
    for i, r in enumerate(rows):
        w = f"rows[{i}] {r.get('id', '')}".strip()
        if not r.get("id") or ids.count(r.get("id")) > 1 or not r.get("what"):
            bad.append(f"{w}: a unique id and what it judges")
        _row_target(r, w, read, bad)
        _src(r, w, bad)
        sr.check_row(r, w, bad, kinds)  # (C286: what = a structure_rows kind)
        if r.get("at") is not None and not (_uv_list(r["at"]) and isinstance(r.get("view", 0), int)
                                            and 0 <= r.get("view", 0) < nv):
            bad.append(f"{w}.at: [[u, v], ...] on view (a step-0 view index)")
    from . import chain_drape as cd, structure_marks as sm, structure_outline as so
    m0, own = sm.from_read(read, parts.get("centre")), p.get("body_marks") or []
    own = [m for m in own if not (isinstance(m, dict) and m.get("from_step0"))] if isinstance(own, list) else own
    if m0 and isinstance(own, list):  # (C351: the fit view is placed by step 0's own landmarks, never marked again)
        if any(isinstance(m, dict) and m.get("view", 0) == m0["view"] for m in own):
            bad.append(f"body_marks: view {m0['view']} is placed by step 0's fit landmarks (approved: "
                       f"{', '.join(sorted(m0['at']))}); leave them out (body_marks only for a view step 0 didn't fit)")
        p["body_marks"] = [m0] + [m for m in own if isinstance(m, dict) and m.get("view", 0) != m0["view"]]
    so.check_plan(p, read, bad)  # (T15: traced edges, required: C351; the body marks that place the view)
    if not any(b.startswith("traces") for b in bad):  # (C353: each trace on the picture's own edges)
        from . import structure_trace_edges as te
        te.check(p.get("traces"), read.get("views") or [], bad)
    if p.get("blockin") is not None:  # (F9: the garment as worn, an SDF block-in: garment_blockin's docstring)
        from .garment_blockin import validate as _bv
        bad += _bv(p["blockin"])
    cd.check_style(p, pieces, bad)  # (T13: drape falls; a hang row needs a draped piece falling that way)
    falls = {x["falls"] for x in cd.plan_drape({"parts": parts, "style": p}).values()}
    for i, r in enumerate(rows):
        k = sr.KINDS.get(r.get("what")) or {}
        if k.get("needs_drape") and k["needs_drape"] not in falls:
            bad.append(f"rows[{i}] {r.get('id', '')}: {r['what']} is judged on the hang of a draped piece falling "
                       f"{k['needs_drape']}; step 1 / 2 have none ({sr.stage_kinds()})")
    bad += pixel_errors(p, read.get("views"))
    if bad:
        raise PlanRefused("step 2 (style) refused:\n  " + "\n  ".join(bad) + "\n" + form("2") + "\n  row kinds (what): "
                          + sr.vocabulary() + "\n  trace kinds (what): " + so.vocabulary())  # (t s2-1: C351)
    return p


def _row_target(r: dict, w: str, read: dict, bad: list):
    """A row's target: none for not_judged (C353); a step-0 height BY NAME for a kind step 0 already measured
    (structure_rows step0_on: t s2-3 gave a jacket's length as 45 px below the hips, beside step 0's hem height);
    else {value, unit} | {is}."""
    k, t = sr.KINDS.get(r.get("what")) or {}, r.get("target")
    if r.get("what") == "not_judged" and t is None:
        return
    on = k.get("step0_on")
    hs = {n: h for n, h in (read.get("heights") or {}).items() if isinstance(h, dict) and h.get("on", "torso") == on}
    if on and isinstance(t, dict) and "height" in t:
        if t["height"] not in hs:
            bad.append(f"{w}.target.height {t['height']!r}: a step-0 height on the {on} (have {', '.join(hs) or 'none'})")
        else:
            t["z_mm"] = round(float(hs[t["height"]]["z_mm"]), 1)
        return
    if on and hs:
        bad.append(f"{w}: {r.get('what')} was measured at step 0 on the model: target {{height: one of {', '.join(hs)}}}, "
                   "never a second number")
        return
    _target(t, w, bad)
