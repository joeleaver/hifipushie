"""The flat gate: `gate` (its rows) and `verdict`. Part of garment step 4's own draft (draft_own.py has the overview)."""
from __future__ import annotations

import json

from . import draft_own
from .draft_own_validate import _edge_of, _folded, _sides


def _at_cut(na: str, tags: set) -> bool:
    q = na.lstrip("|").split(">")[-1].split(":")[-1]
    return q.endswith((".cut_a", ".cut_b")) and q.rsplit(".", 1)[0] in tags


# ---------------------------------------------------------------- the flat gate
def gate(B: dict, decl: dict, step1: dict, stand_ref: dict | None = None, step3: dict | None = None,
         fit: dict | None = None, step2: dict | None = None, look: dict | None = None) -> list:
    """General flat rows: seams (each pair within its declared ease, else PLAIN_TOL), seam_ends (each seam's edges run
    the same way: draft_seam_ends.py), cut (every built inventory piece
    cut), sewn (every step-1 seam), closures (every step-1 closure declared; lapped edges line up), truing (INFO), and
    the SHAPE rows per role (draft_shape.py: stand / band rise and lean, fall spread, sleeve cap, curved-to-straight seams),
    panels (draft_panels.py: each piece's share of a girth as step 2 states it), caught (draft_caught.py: every edge step 1
    catches in a seam reaches it), turned_width (draft_turned.py: a traced fold's turned part as wide as the reference;
    look = {plan, at}: step 2's plan and the body's landmarks that place its traces)."""
    from . import cloth_check as cc, pattern
    rows = []
    sm = cc.seams(B)
    bad = []
    cut_tags = {dt.get("inside") for dt in decl.get("darts") or [] if isinstance(dt, dict) and dt.get("inside")}
    for r in sm:
        n = (B.get("seam_notes") or {}).get(json.dumps([r["a"], r["b"]]))
        lo, hi = n["ease"] if n else (-draft_own.PLAIN_TOL, draft_own.PLAIN_TOL)
        e = r["len_a_mm"] / r["len_b_mm"] - 1 if r["len_b_mm"] else 0.0
        ok = lo - 1e-6 <= e <= hi + 1e-6
        r.update(ease=e, band=(lo, hi), ok=ok, kind="declared" if n else "plain")
        if not ok:
            from .draft_runs import hint  # (F3, t s4-27: a cap counted past its corners, +49.8 %)
            bad.append(f"{r['a']} || {r['b']}: {r['len_a_mm']:.1f} vs {r['len_b_mm']:.1f} mm, ease {100 * e:+.1f}% "
                       f"outside [{100 * lo:+.1f}, {100 * hi:+.1f}]%" + hint(B, r))
        seen_n = set()
        if r.get("notches_off"):  # (C416: a chain joined at a dart's cut-through is one seam: the cut is sewn shut)
            r["notches_off"] = [x for x in r["notches_off"] if not _at_cut(x[0], cut_tags)]
        for na, nb, d in r.get("notches_off") or []:  # (C387, t s4-16 / s4-17: listed "FAIL" under a PASS row)
            na = na.lstrip("|").split(">")[-1].split(":")[-1].removesuffix("-notch")  # (a notch, or a chain's joint)
            if (na, nb) in seen_n:
                continue
            seen_n.add((na, nb))
            first = lambda x: (x if isinstance(x, str) else x[0]).split(">")[0] + ("..." if not isinstance(x, str) else "")
            bad.append(f"{first(r['a'])} || {first(r['b'])}: {na} sits {float(d):.1f} mm from {nb} along the seam "
                       f"(> {cc.NOTCH_MM:.0f} mm): they meet when sewn")
    rows.append({"id": "seams", "status": "FAIL" if bad else "PASS", "value": f"{len(sm)} seams, {len(bad)} off",
                 "target": f"each pair within its declared ease, else +-1 %; its notches within {cc.NOTCH_MM:.0f} mm",
                 "why": "; ".join(bad[:8]),
                 "fix": "redraft the shorter side, or declare the ease with why; a notch off: move it (or the chain's "
                        "start) so the two meet, e.g. a sleeve's top notch onto the shoulder seam", "back_to": "4",
                 "detail": sm})
    from . import draft_dart_cut
    if B.get("darts"):
        rows.append(draft_dart_cut.row(B))  # (C361: legs meet at their tip; C416: no hand-cut slits)
    from . import draft_notches
    rows.append(draft_notches.row(B))  # (C412: a notch outside its piece, copied from the part it was drawn from)
    from . import draft_darts_inv
    dr = draft_darts_inv.row(step1, decl)  # (C410: a dart step 1 builds is drafted, never only a mark)
    if dr:
        rows.append(dr)
    from . import draft_seam_ends
    rows += draft_seam_ends.rows(B)  # (F6: a seam sewn the wrong way round passes every length row)
    if step3 is not None:  # (F6: the pattern against the body it was measured on, before any build)
        from . import draft_body_lengths
        rows += draft_body_lengths.rows(B, step1, step3, fit)
        rows += draft_body_lengths.style_rows(B, step1, step3)
        from . import draft_girths  # (G1: the pattern round every girth its tapes name vs body + the plan's ease)
        rows += draft_girths.rows(B, step3, fit, B.get("decl") or decl)
        from . import draft_tapes  # (P1: every piece placed where the body was measured for it)
        rows.append(draft_tapes.row(B, B.get("decl") or decl, step3))
        from . import draft_place  # (F2: each piece's place read off its own tapes, never a silent guess)
        rows.append(draft_place.row(B, B.get("decl") or decl, step3))
    inv =step1.get("pieces") or {}
    from .draft_pairs import base_name
    dx = B.get("decl") or decl  # (pairs expanded: draft_pairs)
    # (a cut copy counts under its own name or its pair's base, whichever step 1 uses: C366, t s4-5's "not cut: front.L
    # ... not in step 1: front.L" read the expanded copies against the unexpanded declaration)
    from .draft_pairs import halves, canon
    H = halves(dx, step1)
    own = lambda n: n if n in inv else (n[:-2] if n.endswith((".L", ".R")) and n[:-2] in inv else base_name(n, decl))
    cut = {own(n) for n in B["pieces"]} | set(decl.get("omit") or {}) | {f"{n}.{s}" for n in H for s in "LR"}
    miss = [n for n, it in inv.items() if it.get("build") in draft_own.BUILT and n not in cut]
    extra = [n for n in B["pieces"] if own(n) not in inv and n not in H]
    rows.append({"id": "cut", "status": "FAIL" if miss or extra else "PASS",
                 "value": f"{len(B['pieces'])} cut, {len(decl.get('omit') or {})} omitted",
                 "target": "every built step-1 piece cut, nothing else", "why": "; ".join(
                     [f"not cut: {n}" for n in miss] + [f"not in step 1: {n}" for n in extra]), "back_to": "4"})
    sewn = [({canon(e, H) for e in _sides(s.get("a"))}, {canon(e, H) for e in _sides(s.get("b"))})
            for s in decl.get("seams") or []]
    omit = set(decl.get("omit") or {})
    uns = [f"{r['a']} <-> {r['b']}" for r in step1.get("seams") or []
           if not any(_edge_of(x)[0] in omit for x in (r["a"], r["b"])) and not (_folded(r, dx, H) or _folded(r, decl, H))
           and not any((canon(r["a"], H) in A and canon(r["b"], H) in Bs) or (canon(r["b"], H) in A and
                       canon(r["a"], H) in Bs) for A, Bs in sewn)]
    rows.append({"id": "sewn", "status": "FAIL" if uns else "PASS", "value": f"{len(step1.get('seams') or []) - len(uns)} of "
                 f"{len(step1.get('seams') or [])} step-1 seams sewn", "target": "every step-1 seam", "why": "; ".join(uns[:8]),
                 "back_to": "4"})
    cl, why = dx.get("closures") or [], []
    for nm, c1 in (step1.get("closures") or {}).items():
        want = set(c1.get("pieces") or []) & set(B["pieces"])
        if want and not any(want <= {c.get("over"), c.get("under")} or nm == c.get("name") for c in cl):
            why.append(f"step 1 closure {nm!r} ({', '.join(sorted(want))}) has no declared closure")
    arcs = B.get("edge_arcs") or {}
    for c in cl:
        e = {k: arcs.get(c.get(k), {}).get(v, v) for k, v in (c.get("edge") or {}).items()}  # (edge names -> arcs)
        if c.get("over") and c.get("under") and c["over"] != c["under"] and e.get("over") and e.get("under"):
            try:
                lo = pattern.length(B["pieces"][c["over"]]["P"][pattern.arc_indices(B["pieces"][c["over"]], e["over"])])
                lu = pattern.length(B["pieces"][c["under"]]["P"][pattern.arc_indices(B["pieces"][c["under"]], e["under"])])
            except (KeyError, ValueError) as x:
                why.append(f"closure {c.get('name')!r}: {x}")
                continue
            if abs(lo / lu - 1) > draft_own.CLOSURE_TOL:
                why.append(f"closure {c.get('name')!r}: over {1000 * lo:.0f} mm vs under {1000 * lu:.0f} mm (the holes "
                           f"won't meet their buttons)")
    rows.append({"id": "closures", "status": "FAIL" if why else "PASS", "value": f"{len(cl)} declared",
                 "target": "every step-1 closure declared; lapped edges within 1 %", "why": "; ".join(why[:6]), "back_to": "4"})
    try:
        jn = cc.junctions(B)
        off = [j for j in jn if not j.get("ok", True)]
        rows.append({"id": "truing", "status": "INFO", "value": f"{len(off)} of {len(jn)} seam ends not trued",
                     "target": "info: seam ends not meeting square (what the build refuses is the seam_links row, C395)", "why": "; ".join(str(j.get("at", j))[:60] for j in off[:4])})
    except (KeyError, ValueError, TypeError) as x:
        rows.append({"id": "truing", "status": "INFO", "value": "n/a", "why": str(x)[:120]})
    from . import draft_shape
    from . import fold_bends
    fr = fold_bends.draft_row(decl, step2)  # (R2 C392: every planned fold drafted, every roll planned)
    if fr:
        rows.append(fr)
    from . import draft_caught, draft_panels, draft_turned  # (F3: s4-27's sliver side body, short canvas, narrow lapel)
    if step3 is not None:
        rows += draft_panels.rows(B, step2, step3, dx)
    for r in (draft_caught.row(B, step1), draft_turned.row(B, dx, step2, look)):
        if r:
            rows.append(r)
    return rows + draft_shape.rows(B, dx, step1, stand_ref)


def verdict(rows: list) -> str:
    return "FAIL" if any(r["status"] == "FAIL" for r in rows) else "PASS"
