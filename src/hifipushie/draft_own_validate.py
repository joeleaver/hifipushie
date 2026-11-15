"""The declarations checked against step 1: `validate` and `validate_marks` refuse by name. Part of garment step 4's own draft (draft_own.py has the overview)."""
from __future__ import annotations

import json

from . import draft_own
from .draft_own import DraftRefused, _roles, grain


# ---------------------------------------------------------------- declarations
def _edge_of(e: str) -> tuple[str, str]:
    if not isinstance(e, str) or ":" not in e:
        raise DraftRefused(f"{e!r}: an edge is \"piece:edge\" (step 1's names)")
    return tuple(e.split(":", 1))


def _sides(s) -> list:
    return [s] if isinstance(s, str) else list(s or [])


def _fold_line_seams(decl: dict) -> list:
    """A seam joining a fold-cut piece's edge to its own mirror (P:e = P:e.m, step 1's P.L:cb = P.R:cb): that edge is
    the fold line, which joins the halves itself (C382, t s4-12)."""
    out, pcs = [], draft_own.FOLDED(decl.get("pieces") or {})
    for i, s in enumerate(decl.get("seams") or []):
        A, B = _sides(s.get("a")), _sides(s.get("b"))
        if len(A) == len(B) == 1 and ":" in str(A[0]) and ":" in str(B[0]):
            (pa, ea), (pb, eb) = A[0].split(":", 1), B[0].split(":", 1)
            if pa == pb and pa in pcs and {ea, eb} == {ea.removesuffix(".m"), ea.removesuffix(".m") + ".m"}:
                out.append(f"seam {i} ({s.get('a')} | {s.get('b')}): that edge is the fold line of {pa} (cut on the "
                           "fold): the fold joins the halves, no seam; drop it (step 1's fold there is made by the "
                           "fold: C382)")
    return out


def _folded(r: dict, decl: dict, H: set = frozenset()) -> bool:
    """A step-1 seam of kind "fold" (a piece folded on itself: a collar's fall edge) is made by a declared fold of
    that name on that piece, not by a seam. One between two pieces (P.L:cb <-> P.R:cb: the halves of one piece cut on
    the fold) is made by cutting P on the fold (pieces.P.fold: H) or by a seam, never by a fold on one half (C381)."""
    if r.get("kind") != "fold":
        return False
    from .draft_pairs import canon
    ca, cb = canon(r["a"], H), canon(r["b"], H)
    if isinstance(r.get("b"), str) and _edge_of(ca)[0] != _edge_of(cb)[0]:
        return False
    if _edge_of(ca)[0] in H and ca == cb:
        return True
    p, ed = _edge_of(r["a"])
    return any(f.get("piece") == p and ed in (f.get("name"), f.get("line")) for f in decl.get("folds") or [])


def validate(decl: dict, step1: dict, parts: dict | None = None) -> list:
    """Refusals (one line each, by name); [] = usable. A declared pair (pieces.X {pair: true}) is expanded to X.L + X.R
    first and the expansion validated (C364, t s4-3: "pair never produced the right-hand pieces": the inventory check ran
    on the unexpanded name and refused it)."""
    from . import draft_pairs as dp
    if parts is not None:
        decl = dp.fold_halves(decl, parts)
        on_fold = _fold_line_seams(decl)
        if on_fold:
            return on_fold
    inv_ = step1.get("pieces") or {}
    sided = [nm for nm, pd in (decl.get("pieces") or {}).items() if isinstance(pd, dict) and pd.get("pair")
             and nm not in inv_ and f"{nm}.L" in inv_ and f"{nm}.R" in inv_]  # (step 1 names the two sides)
    if parts is not None and sided:
        bad0 = [f"declarations: unknown key {k!r} (have {', '.join(sorted(draft_own.DECL_KEYS))})" for k in decl if k not in draft_own.DECL_KEYS]
        bad0 += dp.faults(decl, parts, step1)
        if bad0:
            return bad0
        try:
            ex = dp.expand(json.loads(json.dumps(decl)), parts)
        except DraftRefused as e:
            return [str(e)]
        return validate(ex, step1, parts)
    bad = [f"declarations: unknown key {k!r} (have {', '.join(sorted(draft_own.DECL_KEYS))})" for k in decl if k not in draft_own.DECL_KEYS]
    pcs, edges, omit = decl.get("pieces") or {}, decl.get("edges") or {}, decl.get("omit") or {}
    inv = step1.get("pieces") or {}
    H = dp.halves(decl, step1)
    cn = lambda e: dp.canon(e, H)
    for nm, pd in pcs.items():
        if nm not in inv and nm not in H:
            bad.append(f"piece {nm!r} is drafted but not in step 1's inventory (have {', '.join(inv)})")
        for k in set(pd) - draft_own.PIECE_KEYS:
            bad.append(f"piece {nm!r}: unknown key {k!r} (have {', '.join(sorted(draft_own.PIECE_KEYS))})")
        if pd.get("role") is not None and pd["role"] not in _roles():  # (t s4-7: "stand" was taken silently)
            bad.append(f"piece {nm!r}: role {pd['role']!r} is not a role (have {', '.join(_roles())}); a layer sewn "
                       "edge to edge onto a piece (canvas, facing, lining of it) needs none: it takes that piece's (C377)")
        if pd.get("grain") is not None and grain(pd["grain"]) is None:
            bad.append(f"piece {nm!r}: grain {pd['grain']!r}: degrees from the part's x axis (90 = lengthwise, the usual "
                       "straight grain; 0 = crosswise; 45 = bias), or one of those words (C363)")
        if parts is not None and pd.get("part") not in parts:
            bad.append(f"piece {nm!r}: the draft has no part {pd.get('part')!r} (has {', '.join(parts)})")
    for nm, it in inv.items():
        if it.get("build") in draft_own.BUILT and nm not in pcs and nm[:-2] not in H and not str(omit.get(nm, "")).strip():
            bad.append(f"step 1 piece {nm!r} (build {it.get('build')}) is not drafted: draft it, or omit {{\"{nm}\": why}}")
    sewn = []
    for i, s in enumerate(decl.get("seams") or []):
        for side in ("a", "b"):
            for e in _sides(s.get(side)):
                p, ed = _edge_of(e)
                p = dp.base_name(p, decl)
                if p not in pcs:
                    bad.append(f"seam {i} {e!r}: no drafted piece {p!r}")
                elif ed not in (edges.get(p) or {}):
                    bad.append(f"seam {i} {e!r}: no edge {ed!r} declared on {p!r} (edges.{p}: {', '.join(edges.get(p) or {}) or 'none'})")
        if s.get("ease") is not None and not str(s.get("why", "")).strip():
            bad.append(f"seam {i} ({s.get('a')} | {s.get('b')}): an eased seam says why")
        sewn.append(({cn(e) for e in _sides(s.get("a"))}, {cn(e) for e in _sides(s.get("b"))}))
    for r in step1.get("seams") or []:
        a, b = r.get("a"), r.get("b")
        if any(_edge_of(x)[0] in omit for x in (a, b)):
            continue
        if _folded(r, decl, H):
            continue
        two = r.get("kind") == "fold" and isinstance(b, str) and _edge_of(cn(a))[0] != _edge_of(cn(b))[0]
        if r.get("kind") == "fold" and not two:
            bad.append(f"step 1 fold {a}: declare folds [{{\"name\": \"{_edge_of(a)[1]}\", \"piece\": \"{_edge_of(a)[0]}\", \"line\": ...}}]")
            continue
        a_, b_ = cn(a), cn(b)
        if two and not any((a_ in A and b_ in B) or (b_ in A and a_ in B) for A, B in sewn):
            base = _edge_of(a)[0][:-2] if _edge_of(a)[0].endswith((".L", ".R")) else _edge_of(a)[0]
            bad.append(f"step 1 fold {a} <-> {b} joins two halves: cut them as ONE piece on the fold (pieces.{base} "
                       f"{{part, fold: \"x0\"}}, no pair: it stands for both halves, its edges named once) or sew them "
                       f"(a seam {a} = {b}); a fold declared on one half doesn't join them (C381)")
            continue
        for x in (a_, b_):
            p, ed = _edge_of(x)
            if p in pcs and ed not in (edges.get(p) or {}):
                tw = p[:-2] + (".L" if p.endswith(".R") else ".R") if p.endswith((".L", ".R")) else None
                hint = (f"; or declare the pair ONCE: pieces.{p[:-2]} {{part, pair: true}} with edges.{p[:-2]} "
                        "(copied to both sides, C362)") if tw and not edges.get(p) and edges.get(tw) else ""
                bad.append(f"step 1 seam {a} <-> {b}: no drafted edge {x!r} (declare edges.{p}.{ed}{hint})")
        if not any((a_ in A and b_ in B) or (b_ in A and a_ in B) for A, B in sewn):
            bad.append(f"step 1 seam {a} <-> {b} is not sewn: a declared seam with {a} on one side and {b} on the other "
                       "(either may be one edge of a chain: a two-piece sleeve's cap set into the whole armhole as ONE seam, "
                       "[cap edges] = [armhole edges], sews every cap / armhole pair of step 1: C365; each edge of a chain starts "
                       "where the one before it ended, both chains the same way round: C403)")
    from . import draft_dart_cut as dcut
    for i, dt in enumerate(decl.get("darts") or []):
        p, legs = dp.base_name(str((dt or {}).get("piece")), decl), (dt or {}).get("legs")
        if p not in pcs:
            bad.append(f"darts[{i}]: no drafted piece {dt.get('piece')!r}")
        elif dcut.is_inside(dt):  # (C416: a dart drawn inside the piece; the tool cuts it through along release)
            bad += dcut.check(i, dt, (parts or {}).get((pcs.get(p) or {}).get("part")) if parts is not None else None)
        elif not (isinstance(legs, list) and len(legs) == 2 and legs[0] != legs[1]):
            bad.append(f"darts[{i}] on {p}: legs = [two edges of the piece] (the dart's sides, sewn to each other)")
        else:
            miss = [e for e in legs if e not in (edges.get(p) or {})]
            if miss:
                bad.append(f"darts[{i}] on {p}: no edge {', '.join(miss)} declared (edges.{p}: "
                           f"{', '.join(edges.get(p) or {}) or 'none'})")
    for c in decl.get("closures") or []:
        for k in ("over", "under"):
            if c.get(k) and dp.base_name(c[k], decl) not in pcs:
                bad.append(f"closure {c.get('name')!r}: {k} {c[k]!r} is not a drafted piece")
    if parts is not None and not bad:
        bad += dp.faults(decl, parts, step1)  # (F3: half a garment / a limb with no side, by name, with the pair)
        if not bad:
            try:
                dp.expand(decl, parts)
            except DraftRefused as e:
                bad.append(str(e))
    from . import draft_tapes, draft_vents  # (P1: the step-3 tapes each piece / edge was drafted on, by name)
    return bad + draft_tapes.validate(decl) + validate_marks(decl, step1) + draft_vents.faults(decl)


def validate_marks(decl: dict, step1: dict) -> list:
    """The details' marks (T10, C290): every built step-1 detail is marked on the pattern (or is a closure's own button
    / a cloth piece); every mark names a step-1 detail, on drafted pieces, with position keys only."""
    from . import garment_details as gd
    bad, mk, pcs = [], decl.get("marks") or {}, decl.get("pieces") or {}
    det = step1.get("details") or {}
    if not isinstance(mk, dict):
        return [f"marks: {{detail: mark | [marks]}}; {draft_own.MARK_FORM}"]
    kinds = {x.get("name"): x.get("kind") for x in decl.get("closures") or []}
    byclosure = {d for nm, c in (step1.get("closures") or {}).items() for d in c.get("details") or []
                 if kinds.get(nm) == "buttons" or (kinds.get(nm) == "zip" and (det.get(d) or {}).get("cloth"))}
    for n, m in mk.items():
        if n not in det:
            bad.append(f"marks.{n}: not a step-1 detail ({', '.join(det) or 'none'})")
            continue
        bad += gd.check_mark(n, m)
        for x in m if isinstance(m, list) else [m]:
            p = x.get("piece") if isinstance(x, dict) else None
            if p and p not in pcs:
                bad.append(f"marks.{n}: piece {p!r} is not drafted")
    mirrored = {gd.mirror_name(n) for n, m in mk.items()
                for x in (m if isinstance(m, list) else [m]) if isinstance(x, dict) and x.get("mirror")}
    for n, x in det.items():  # (a .L mark with mirror: true places the .R detail too, any kind: C366, t s4-5)
        if x.get("build") in draft_own.BUILT and n not in mk and n not in byclosure and n not in mirrored \
                and not gd.cloth_made(x.get("what")):
            bad.append(f"step 1 detail {n!r} (build {x.get('build')}) has no mark: declare marks.{n}; {draft_own.MARK_FORM}")
    return bad
