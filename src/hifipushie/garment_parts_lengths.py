"""Step 1's SEAM LENGTH FORM (garment_plan.check_parts), for any garment: a seam's length is what the MODEL will
measure, never millimetres read off the picture (t s1-8: 38 of 42 seams of a suit jacket were value_mm read at the
picture's ~1.08 mm/px: the picture's person is not the model, so those lengths don't transfer; ratios do: C335, C349).

FORM: length = {body: [measurement names]}             step 3 measures them on the model
             | {style: {ratio, of, source}}             a proportion read off the picture, OF a base the model has:
                 of = a body measurement name (body_tape takes it, or define names it)
                    | "piece:edge" (another edge of this garment)
                    | [a, b]: the span between two step-0 heights or fit landmarks, measured on the model (a side seam:
                      ["armpit", "hem"]; a front edge: ["lapel_gorge", "hem"])
             | {style: {value_mm, fixed, source}}       a length that is the same on every wearer (a zip, a standard
                 vent depth): fixed says why it doesn't scale with the body
"""
from __future__ import annotations


def _num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0


def check(ln, w: str, pieces: dict, define: dict, spans: set, takes, bad: list, needs: set):
    """One seam's length form; needs gets the body names step 3 must measure. spans = the step-0 heights and fit
    landmark names a span may run between."""
    if isinstance(ln, dict) and isinstance(ln.get("body"), list) and ln["body"] and all(
            isinstance(m, str) and m for m in ln["body"]):
        needs.update(ln["body"])
        return
    st = ln.get("style") if isinstance(ln, dict) else None
    if not isinstance(st, dict) or not (_num(st.get("ratio")) or _num(st.get("value_mm"))):
        bad.append(f"{w}.length: {{body: [measurement names]}} (step 3 measures them) or {{style: {{ratio, of, source}}}} "
                   "(a proportion read off the reference, of a base the model has)")
        return
    if not str(st.get("source") or "").strip():
        bad.append(f"{w}.length.style: no source (name what it comes from: a view and what was read there, a convention)")
    if _num(st.get("value_mm")) and not _num(st.get("ratio")):
        if not str(st.get("fixed") or "").strip():
            bad.append(f"{w}.length.style.value_mm: millimetres read off the picture don't transfer (the picture's "
                       "person is not the model): give {ratio, of} instead, of a body measurement, a 'piece:edge', or "
                       "[a, b] a span between step-0 heights / landmarks (e.g. ['armpit', 'hem']); keep value_mm only "
                       "for a length the same on every wearer, with fixed: why")
        return
    of = st.get("of")
    if isinstance(of, str) and (of in takes or of in define):
        needs.add(of)  # (step 3 measures the base: t s1-3's "of biceps" was missed)
    elif isinstance(of, str) and ":" in of and of.split(":")[0] in pieces:
        pass
    elif isinstance(of, list) and len(of) == 2 and all(isinstance(a, str) for a in of) and of[0] != of[1]:
        off = [a for a in of if a not in spans]
        if off:
            bad.append(f"{w}.length.style.of {of!r}: {', '.join(off)} not a step-0 height or landmark (have "
                       f"{', '.join(sorted(spans))})")
    else:
        bad.append(f"{w}.length.style.of {of!r}: a ratio's base: a body measurement name (step 3 measures it; one "
                   "body_tape takes, or one you define), a 'piece:edge', or [a, b] a span between two step-0 heights / "
                   "landmarks")
