"""What the gate rules require next, generated from a stage tool's actual result (docs/notes/gates.md, codified.md
"MCP-enforced"). The MCP tools append these lines to their text so ANY model using the server follows the rules
without a human-written brief (Joe 2026-10-19: "we don't want to make it work just for this session, but anyone who
uses the mcp"). Each function returns a short "next: ..." block, specific to the result, never boilerplate.

The order for a garment: pattern -> pattern_check (flat) -> fit_garment (on the form) -> judge (clay + diag beside the
reference, one view per review) -> optional sim, only as a wrinkle source -> game mesh. Post-sim closing and hand
finishing are NOT steps: measured 2026-10-19 (dress-garrett), they pushed face strain p99 from 4.7 % to 66-74 %.
"""
from __future__ import annotations

STRAIN_P99_MAX = 6.0  # % face strain p99 on the form, body pieces (cloth_check form_strain row: KES EMT for suiting)


def _ids(rows, status) -> list:
    return [r["id"] for r in rows if r.get("status") == status]


def after_pattern_check(rec: dict, model: str, garment: str) -> str:
    """pattern_check's next step from its gate record."""
    w = rec.get("waived") or {}
    rows = [r for r in rec.get("rows") or [] if not w.get(r["id"])]
    fails, unm = _ids(rows, "FAIL"), _ids(rows, "UNMEASURED")
    ok = rec.get("status") in ("PASS", "PASS_WAIVED")
    out = []
    if not ok and (fails or unm):
        out.append(f"next: the pattern gate is {rec.get('status')}: DON'T simulate (dress refuses).")
        if fails:
            out.append(f"  fix these rows on the flat pattern first (alter_pattern / design_garment): {', '.join(fails)}")
        if unm:
            out.append(f"  unmeasured (no reading = no pass): {', '.join(unm)}: give a reference reading "
                       f"(garment_from_reference) or waive each BY NAME with a reason (waive={{id: why}})")
        out.append(f"  then pattern_check(\"{model}\", \"{garment}\") again")
    elif not ok:
        out.append(f"next: the pattern gate is {rec.get('status')}: DON'T simulate; re-run pattern_check")
    else:
        info = _ids(rows, "INFO")
        out.append(f"next: call_tool(\"fit_garment\", {{\"name\": \"{model}\", \"garment\": \"{garment}\"}}): assemble it on the form (no sim) and judge clay + "
                   "diag beside the reference, one view at a time (review_view)")
        if info:
            out.append(f"  INFO rows (not gating, read them on the form): {', '.join(info[:8])}")
    for w in rec.get("warnings") or []:
        out.append(f"  warning: {w}")
    return "\n".join(out)


def after_fit(model: str, garment: str, strain_p99: float | None, pierce: int | None, validated: bool,
              backfaces: int | None = None, worn_open: bool = False) -> str:
    """fit_garment's next step from what it measured on the form. worn_open: the design says the closure is worn
    open: the form judges it CLOSED and one release sim opens it (Joe 2026-10-20)."""
    out = []
    if worn_open:
        out.append(f"worn open: judge the CLOSED fit here (top button fastened), then release_garment(\"{model}\", "
                   f"\"{garment}\"): ONE short sim from this fit that undoes the closure and lets the fronts hang under "
                   "gravity (no holds on the form: five rounds of them failed)")
    bad = []
    if strain_p99 is not None and strain_p99 > STRAIN_P99_MAX:
        bad.append(f"strain p99 {strain_p99:.1f} % > {STRAIN_P99_MAX:g} %: the pattern is too small / mis-shaped "
                   "where the strain map is red: fix the PATTERN there (not the solver, not a hand pass)")
    if pierce:
        # NOT a composing fault (Joe 2026-10-22, C153): the under garment's covered triangles are culled later, so its
        # show-through is reported, never a fix; judge the outer garment's own shape (the under one hidden)
        out.append(f"layer pierce {pierce} faces of the under garment (magenta): INFO only, the covered under-layer is "
                   "culled later (C153); judge this garment's own shape with the under one hidden")
    if backfaces:
        bad.append(f"{backfaces} faces seen from behind (red in the backfaces view): a piece inside out or a flap "
                   "turned the wrong way")
    if bad:
        out.append("next: fix on the pattern, then pattern_check and fit_garment again:")
        out += [f"  {b}" for b in bad]
    else:
        out.append("next: judge the clay AND the diag views beside the reference, ONE view per review_view call "
                   "(no contact sheets, no captions); a clean form is not a right garment")
    if not validated:
        out.append("  the dress form is not validated yet: its readings are INFO, the flat gate decides")
    out.append("  a sim is optional and only a wrinkle source; never close or hand-finish after it (strain p99 went "
               "4.7 % -> 66-74 % that way)")
    return "\n".join(out)


def after_alter(rows: list, model: str, garment: str) -> str:
    """alter_pattern's next step from the walked seams."""
    bad = [r for r in rows if not r.get("ok", True)]
    if bad:
        return ("next: these seams don't walk (lengths differ past their declared ease): "
                + "; ".join(f"{r.get('a', '?')} | {r.get('b', '?')}" for r in bad[:6])
                + f" -- match them (op \"match\") before pattern_check(\"{model}\", \"{garment}\")")
    return f"next: call_tool(\"pattern_check\", {{\"name\": \"{model}\", \"garment\": \"{garment}\"}}) (the flat gate: the record is per pattern, so re-run it)"


def after_look(kind: str, has_reference: bool) -> str:
    """look / look_cloth / look_skin: what a look must be before it is forwarded."""
    if not has_reference:
        return (f"next: no reference beside this {kind}: set one (set_reference / the stage's reference reading) and "
                "judge against it; a look with nothing to compare to proves nothing")
    return (f"next: judge this {kind} yourself BESIDE its reference before forwarding it, then an independent "
            "review_view per region (one view per call)")


def after_dress_refused(blocked: dict, model: str) -> str:
    """dress refused for want of a PASS: what to run."""
    lines = []
    for g, why in blocked.items():
        lines.append(f"{g}: NOT simulated: {why}")
        lines.append(f"  next: call_tool(\"pattern_check\", {{\"name\": \"{model}\", \"garment\": \"{g}\"}}), fix its FAIL / UNMEASURED rows, fit_garment, "
                     "judge; a sim comes after (optional: a wrinkle source)")
    return "\n".join(lines)


def after_review(verdict: str | None, dry: bool) -> str:
    if dry:
        return ("next: give this ONE pair image and the prompt to an independent reviewer (a fresh agent with no "
                "context), not your own reading; then one call per remaining view / region")
    if verdict == "PASS":
        return "next: the next view / region (every checklist region needs its own review_view call)"
    if verdict == "FAIL":
        return ("next: fix every independent MAJOR (group them by cause first), then review this view again; answer "
                "each point in the notes, never override a MAJOR by opinion")
    return "next: the review did NOT run (no verdict): this is not 0 MAJORs; retry or use dry=True"
