"""What the gate rules require next, generated from a stage tool's actual result (docs/notes/gates.md, codified.md
"MCP-enforced"). The MCP tools append these lines to their text so ANY model using the server follows the rules
without a human-written brief (Joe 2026-10-19: "we don't want to make it work just for this session, but anyone who
uses the mcp"). Each function returns a short "next: ..." block, specific to the result, never boilerplate.

The older clothing routes these lines served (the fit on the form, the sim, the game garment) were deleted on
2026-11-10 (C409); what is left serves pattern_check, the looks and the reviews.
"""
from __future__ import annotations


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
        out.append(f"next: the pattern gate is {rec.get('status')}: chain_garment refuses until it passes.")
        if fails:
            out.append(f"  fix these rows on the flat pattern first (alter_pattern / design_garment): {', '.join(fails)}")
        if unm:
            out.append(f"  unmeasured (no reading = no pass): {', '.join(unm)}: give a reference reading "
                       f"(garment_from_reference) or waive each BY NAME with a reason (waive={{id: why}})")
        out.append(f"  then pattern_check(\"{model}\", \"{garment}\") again")
    elif not ok:
        out.append(f"next: the pattern gate is {rec.get('status')}: chain_garment refuses until it passes; re-run pattern_check")
    else:
        info = _ids(rows, "INFO")
        out.append(f"next: call_tool(\"chain_garment\", {{\"name\": \"{model}\", \"garment\": \"{garment}\", \"wear\": \"closed\"}}): the only way "
                   "a garment is started; then look_chain beside the reference, one view at a time (review_view)")
        if info:
            out.append(f"  INFO rows (not gating): {', '.join(info[:8])}")
    for w in rec.get("warnings") or []:
        out.append(f"  warning: {w}")
    return "\n".join(out)


def after_alter(rows: list, model: str, garment: str) -> str:
    """alter_pattern's next step from the walked seams."""
    bad = [r for r in rows if not r.get("ok", True)]
    if bad:
        return ("next: these seams don't walk (lengths differ past their declared ease): "
                + "; ".join(f"{r.get('a', '?')} | {r.get('b', '?')}" for r in bad[:6])
                + f" -- match them (op \"match\") before pattern_check(\"{model}\", \"{garment}\")")
    return f"next: call_tool(\"pattern_check\", {{\"name\": \"{model}\", \"garment\": \"{garment}\"}}) (the flat gate: the record is per pattern, so re-run it)"


def after_look(kind: str, has_reference: bool, how: str = "") -> str:
    """look / look_cloth / look_skin: what a look must be before it is forwarded. how: the call that does it."""
    if not has_reference:
        return (f"next: no reference beside this {kind}: set one (set_reference / the stage's reference reading) and "
                "judge against it; a look with nothing to compare to proves nothing")
    return (f"next: judge this {kind} yourself BESIDE its reference before forwarding it, then an independent "
            "review_view per region (one view per call)" + (f": {how}" if how else ""))


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

