"""Step 4 says which step-3 tape each piece was drafted on (P1, docs/proposals/place_where_measured.md).

Why: Joe (2026-11-11): "It feels like we should place where we measure." The suit jacket's approved step 4 had EMPTY
`piece_measurements` for all 16 pieces (its own parts extend jaeger without re-listing measurements), nothing refused
it, and step 5 fell back to rules: the undercollar was laid as a ring round the neck, tearing the gorge off the lapel.

Declarations key `tapes` {piece: [step-3 tape names] | {edge: tape name}}: the tapes a piece was drafted on; an edge map
says which tape each edge LAID ON THE BODY lies along (a collar's neck edge on the neckline tape). A pair's base name
(pieces.X {pair}) covers X.L and X.R; X.L / X.R name one side; a fold-cut piece's step-1 halves (P.L / P.R) name P.
- `validate(decl)`: refusals by name (an unknown piece, an edge not declared on it, a value of the wrong form).
- `names_of(decl, piece)`: the tape names piece (as cut) declares (an edge map's tapes too): merged into step 4's
  `piece_measurements` (piece_start).
- `edge_tapes(decl, pieces, arcs)`: {piece: {edge: {"tape", "arc"}}} for the record (step 5 lays the edge on its tape).
- `row(B, decl, step3)`: flat gate row `piece_tapes`: FAIL when a cut piece declares no step-3 tape with geometry, when
  a named tape isn't in step 3 (back to step 3: measure that line), when a STIFF piece sewn to a soft one names no edge
  tape for that sewn edge.
"""
from __future__ import annotations

FORM = ('tapes {piece: [step-3 tape names] | {edge: tape name}}: the tapes each piece was drafted on (an edge map: the '
        'tape each edge laid on the body lies along, e.g. a collar\'s neck edge on the neckline tape)')


def _side(n: str) -> bool:
    return n.endswith((".L", ".R"))


def _keys_for(decl: dict, piece: str) -> list:
    """The `tapes` keys that apply to piece as cut: its own name, its pair's base, a fold-cut piece's step-1 halves."""
    ks = [piece]
    if _side(piece):
        ks.append(piece[:-2])
    else:
        ks += [f"{piece}.L", f"{piece}.R"]
    return [k for k in ks if k in (decl.get("tapes") or {})]


def _entries(v) -> list:
    """[(edge or None, tape)] of one `tapes` value."""
    if isinstance(v, dict):
        return [(e, t) for e, t in v.items()]
    if isinstance(v, (list, tuple)):
        return [(None, t) for t in v]
    return []


def validate(decl: dict) -> list:
    tp = decl.get("tapes")
    if tp is None:
        return []
    if not isinstance(tp, dict):
        return [f"tapes: {FORM}"]
    pcs, edges = decl.get("pieces") or {}, decl.get("edges") or {}
    bad = []
    for k, v in tp.items():
        own = k if k in pcs else (k[:-2] if _side(k) and k[:-2] in pcs else None)
        if own is None and f"{k}.L" in pcs and f"{k}.R" in pcs:
            own = k  # (expanded pair: its base name)
        if own is None:
            bad.append(f"tapes.{k}: not a drafted piece (have {', '.join(pcs) or 'none'})")
            continue
        if not isinstance(v, (dict, list)) or not v or not all(isinstance(t, str) and t for _, t in _entries(v)):
            bad.append(f"tapes.{k}: {v!r}: a list of step-3 tape names, or {{edge: tape name}}; {FORM}")
            continue
        if isinstance(v, dict):
            have = set(edges.get(k) or {}) | set(edges.get(own) or {}) | set(edges.get(f"{k}.L") or {})
            for e in v:
                if e not in have and e.removesuffix(".m") not in have:
                    bad.append(f"tapes.{k}.{e}: no edge {e!r} declared on {own!r} (edges.{own}: "
                               f"{', '.join(sorted(have)) or 'none'})")
    return bad


def names_of(decl: dict, piece: str) -> list:
    return sorted({t for k in _keys_for(decl, piece) for _, t in _entries(decl["tapes"][k])})


def _edge_map(decl: dict, piece: str) -> dict:
    out = {}
    for k in _keys_for(decl, piece):
        v = decl["tapes"][k]
        if isinstance(v, dict):
            out.update(v)
    return out


def edge_tapes(decl: dict, pieces, arcs: dict | None = None) -> dict:
    out = {}
    for p in pieces:
        m = _edge_map(decl, p)
        if m:
            out[p] = {e: {"tape": t, "arc": (arcs or {}).get(p, {}).get(e)} for e, t in m.items()}
    return out


def _sewn_edges(decl: dict, stiff: set) -> dict:
    """{stiff piece: {edge: soft piece}}: each stiff piece's edges on a seam whose other side is soft cloth."""
    sides = lambda s: [s] if isinstance(s, str) else list(s or [])
    pe = lambda e: str(e).split(":", 1) if ":" in str(e) else (str(e), "")
    out: dict = {}
    for s in decl.get("seams") or []:
        A, B = [pe(e) for e in sides(s.get("a"))], [pe(e) for e in sides(s.get("b"))]
        for X, Y in ((A, B), (B, A)):
            soft = [p for p, _ in Y if p not in stiff]
            for p, e in X:
                if p in stiff and soft:
                    out.setdefault(p, {}).setdefault(e, soft[0])
    return out


def row(B: dict, decl: dict, step3: dict) -> dict:
    from . import tape_geom
    T = tape_geom.tapes(step3)
    taken = {r.get("name") for r in (step3 or {}).get("measurements") or []}
    bad, none, unknown, nogeo = [], [], set(), set()
    pieces = list(B.get("pieces") or {})
    for p in pieces:
        names = names_of(decl, p)
        for n in names:
            if n not in taken:
                unknown.add(n)
            elif n not in T:
                nogeo.add(n)
        if not any(n in T for n in names):
            none.append(f"{p} ({', '.join(names) or 'no tapes'})")
    if none:
        bad.append(f"no step-3 tape with geometry: {', '.join(none)}: declare tapes.<piece> [the step-3 tapes it was "
                   "drafted on] (a pair once, by its base name, and an edge laid on the body as {edge: tape}): step 5 starts "
                   "each piece on its tapes, never from a rule")
    for n in sorted(unknown):
        bad.append(f"tape {n!r} is not in step 3 (have {', '.join(sorted(taken)) or 'none'}): measure that line in step 3 "
                   f"(body_tape {n!r} as a length from / via / to over the surface, or a girth, add=true keeping the rest), "
                   "or name a tape step 3 took")
    for n in sorted(nogeo):
        bad.append(f"tape {n!r} has no line in step 3 (only a number): retake it with body_tape so it records where "
                   "it was taken")
    stiff = set(decl.get("stiff") or [])
    for p, es in sorted(_sewn_edges(decl, stiff).items()):
        if p not in (B.get("pieces") or {p: 1}):
            continue
        em = _edge_map(decl, p)
        for e, soft in sorted(es.items()):
            if e not in em and e.removesuffix(".m") not in em:
                bad.append(f"stiff {p}:{e} is sewn to soft {soft} but names no tape: declare tapes.{p}.{e} = the step-3 "
                           "tape that edge lies on (a collar's neck edge: the neckline tape, measured in step 3 "
                           "if it isn't there): a stiff piece is laid on it, never on a ring")
    back = "3" if unknown or nogeo else "4"
    return {"id": "piece_tapes", "status": "FAIL" if bad else "PASS",
            "value": f"{sum(1 for p in pieces if any(n in T for n in names_of(decl, p)))} of {len(pieces)} pieces on "
                     "step-3 tapes",
            "target": "every cut piece names the step-3 tapes it was drafted on (with geometry); a stiff piece's edge "
                      "sewn to soft cloth names the tape it lies on",
            "why": "; ".join(bad[:12]), "fix": f"declarations {FORM}", "back_to": back}
