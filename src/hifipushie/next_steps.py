"""What the gate rules require next, generated from a stage tool's actual result (docs/notes/gates.md, codified.md
"MCP-enforced"). The MCP tools append these lines to their text so ANY model using the server follows the rules
without a human-written brief (Joe 2026-10-19: "we don't want to make it work just for this session, but anyone who
uses the mcp"). Each function returns a short "next: ..." block, specific to the result, never boilerplate.

The older clothing routes these lines served (the fit on the form, the sim, the game garment) were deleted on
2026-11-10 (C409); what is left serves pattern_check, the looks and the reviews.
"""
from __future__ import annotations


def after_look(kind: str, has_reference: bool, how: str = "") -> str:
    """look / look_cloth / look_skin: what a look must be before it is forwarded. how: the call that does it."""
    if not has_reference:
        return (f"next: no reference beside this {kind}: set one (set_reference / the stage's reference reading) and "
                "judge against it; a look with nothing to compare to proves nothing")
    return (f"next: judge this {kind} yourself BESIDE its reference before forwarding it, then an independent "
            "review_view per region (one view per call)" + (f": {how}" if how else ""))


def after_save(name: str, spec: dict) -> str:
    """put_model / edit_model on a creature or a prop. (A character's own tools say their own next step: a save of a
    model with a base, clothes, skin or hair adds nothing here.)"""
    if spec.get("base") or spec.get("cloth") or spec.get("skin") or spec.get("hair"):
        return ""
    plan = "" if spec.get("plan") else " No plan yet: set_plan (the blockout that check measures against) before detail."
    return f'next: look("{name}") from front, side and three_quarter before the next change.{plan}'


def after_model_look(name: str, has_reference: bool) -> str:
    """look on a creature or a prop: what the look is compared with."""
    if not has_reference:
        return ("next: nothing to compare this model with yet: set_plan (your blockout) or set_reference (front / side / "
                "top outlines); from ONE concept picture: fit_concept_camera, then look_matched. A look with nothing to "
                "compare to proves nothing")
    return (f'next: check("{name}") measures it against its plan; judge it yourself beside the reference, then an '
            "independent review_view of one view")


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

