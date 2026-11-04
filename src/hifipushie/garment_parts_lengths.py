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
CHECKED (lengths, C335/C350): every length that resolves on the model (body names: the tape; a ratio: of the tape, of a
span between step-0 heights / landmarks on the model, along the limb when both ends are on one, or of another edge as
drawn; fixed mm as given) is compared with its edge as drawn on the step-0 fit view at the step-0 scale: past LENGTH_X
either way it is refused unless the seam says why (a front view foreshortens an edge running round the body: the
bounds are wide; it catches the wrong measurement, not a few cm) (t s1-9: no ratio was checked at all).
"""
from __future__ import annotations

import math

LENGTH_X = (0.4, 2.5)  # (the length on the model / its edge as drawn: outside this, the wrong measurement)


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


def _drawn(e, edges: dict, fit_view, scale):
    """mm of 'piece:edge' as drawn on the fit view (None: not drawn there, or hidden)."""
    pc, _, ed = str(e).partition(":")
    g = (edges.get(pc) or {}).get(ed)
    if not g or g[0] != fit_view or g[2]:
        return None
    d = sum(math.dist(p, q) for p, q in zip(g[1], g[1][1:])) * scale
    return d if d >= 1 else None


def _end(name: str, heights: dict, body):
    """(part, z_mm, s_mm along its limb | None) of a step-0 height or a landmark on the model; None if unknown."""
    from .garment_fit_heights import PARTS
    h = heights.get(name)
    if isinstance(h, dict) and isinstance(h.get("z_mm"), (int, float)):
        al = h.get("along") or {}
        return h.get("on", "torso"), float(h["z_mm"]), al.get("s_mm")
    if body is None:
        return None
    try:
        z = float(body.at(name)["z_mm"])
        limb = next((p for p in ("arm", "leg") if name in PARTS[p] and name not in PARTS["torso"]), None)
        return limb or "torso", z, (body.along(limb, name) if limb else None)
    except Exception:  # (a landmark the model can't place: no check, not a refusal)
        return None


def _span(of: list, heights: dict, body):
    a, b = (_end(n, heights, body) for n in of)
    if not a or not b:
        return None
    if a[0] == b[0] and a[0] != "torso" and a[2] is not None and b[2] is not None:
        return abs(a[2] - b[2])  # (both on one limb: along it)
    return abs(a[1] - b[1])


def model_mm(ln, mm: dict, heights: dict, body, edges: dict, fit_view, scale):
    """(mm on the model, what it is) of a seam's length, or None when it can't be resolved here."""
    if not isinstance(ln, dict):
        return None
    if isinstance(ln.get("body"), list) and ln["body"]:
        return (sum(float(mm[m]) for m in ln["body"]), " + ".join(ln["body"])) if all(m in mm for m in ln["body"]) else None
    st = ln.get("style") if isinstance(ln.get("style"), dict) else {}
    r, of = st.get("ratio"), st.get("of")
    if _num(r):
        if isinstance(of, str) and of in mm:
            base = float(mm[of])
        elif isinstance(of, str) and ":" in of:
            base = _drawn(of, edges, fit_view, scale)
        elif isinstance(of, list) and len(of) == 2:
            base = _span(of, heights, body)
        else:
            base = None
        return (r * base, f"{r} x {of if isinstance(of, str) else ' to '.join(of)}") if base else None
    if _num(st.get("value_mm")):
        return float(st["value_mm"]), "fixed"
    return None


def lengths(seams: list, edges: dict, fit_view, scale, mm: dict, heights: dict, body, bad: list) -> list:
    """Each seam's length on the model against its edge as drawn on the fit view; [(seam, model mm, drawn mm)]."""
    done = []
    if not scale:
        return done
    for i, s in enumerate(seams):
        if not isinstance(s, dict) or str(s.get("why") or "").strip():
            continue  # (a seam with why: kept)
        got = model_mm(s.get("length"), mm or {}, heights or {}, body, edges, fit_view, scale)
        if not got or got[0] < 1:
            continue
        for end in (s.get("a"), s.get("b")):
            drawn = _drawn(end, edges, fit_view, scale)
            if drawn is None:
                continue
            x = got[0] / drawn
            done.append((i, round(got[0], 1), round(drawn, 1)))
            if not LENGTH_X[0] <= x <= LENGTH_X[1]:
                bad.append(f"seams[{i}] {s.get('a')} = {s.get('b')}: {got[1]} is {got[0]:.0f} mm on the model, but "
                           f"{end} as drawn is about {drawn:.0f} mm ({x:.1f}x; {LENGTH_X[0]}-{LENGTH_X[1]}x allowed: a "
                           "front view foreshortens): the wrong measurement or ratio (a whole girth for part of it, both "
                           "shoulders for one, a span between the wrong heights), or an edge joined to several pieces "
                           "given the whole length in each seam (each takes its share); fix it, or keep it with why")
            break
    return done
