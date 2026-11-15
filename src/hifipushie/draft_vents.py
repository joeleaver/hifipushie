"""Vents at the draft (F2, blind trial s4-26): an opening at the bottom of a seam whose two sides overlap.

Why: s4-26 drafted a jacket's side vents with their extensions (one side's cloth runs on past the seam line under the
other's) and the girths row counted both extensions as cloth round the hips: "128 too loose ... the double-vent
extensions counted as girth"; with "no way to declare a vent's lap" it dropped the extensions and kept the vents as marks.
A pattern maker cuts the extensions; the pattern declares what they are.

`vents` [{"name", "over": "piece:edge", "under": "piece:edge", "why"?}]: each side's vent edge, a declared edge of its
piece running from the hem up the extension to the VENT TOP, the point where the seam between the two pieces starts
(an end of that piece's edge sewn to the other piece). Below its top the vent is open: its edges are sewn to nothing
(a vent edge in a seam is refused); `over` lies on `under` (the side seen from outside), lapped by their extensions.
A pair (pieces.P {pair: true}) is declared once by its base name: one vent per side (draft_pairs.expand).
THE GIRTH: the two sides are linked across the opening like a closure's lap, and each side's cloth beyond its seam line
(the sewn edge run on straight past the vent top) is taken off once: the vent's overlap is counted once round a girth.
Nothing here knows a garment."""
from __future__ import annotations

import copy

import numpy as np

KEYS = {"name", "over", "under", "why"}
FORM = ('vents [{"name", "over": "piece:edge", "under": "piece:edge"}]: each side\'s vent edge from the hem up its '
        'extension to the vent top, where the seam between the two pieces starts')
RUN_ON = 0.05  # m: the seam line past the vent top is the sewn edge's chord over this length from the top


def _pe(e) -> tuple[str, str]:
    p, _, ed = str(e).partition(":")
    return p, ed


def _ends(arc) -> tuple[str, str] | None:
    if not isinstance(arc, str) or ">" not in arc:
        return None
    pts = arc.split(">")
    return pts[0], pts[-1]


def faults(decl: dict) -> list:
    """Refusals by name (step 4), on the declarations as written (a pair by its base name)."""
    from .draft_own import _sides
    from .draft_pairs import base_name
    pcs, edges, bad = decl.get("pieces") or {}, decl.get("edges") or {}, []
    sewn = [(_sides(s.get("a")), _sides(s.get("b"))) for s in decl.get("seams") or []]
    in_seam = {e for A, B in sewn for e in A + B}
    for i, v in enumerate(decl.get("vents") or []):
        nm = (v or {}).get("name", f"vents[{i}]")
        if not isinstance(v, dict) or not all(isinstance(v.get(k), str) and ":" in v[k] for k in ("over", "under")):
            bad.append(f"vent {nm!r}: " + FORM)
            continue
        bad += [f"vent {nm!r}: unknown key {k!r} (have {', '.join(sorted(KEYS))})" for k in v if k not in KEYS]
        (po, eo), (pu, eu) = _pe(v["over"]), _pe(v["under"])
        for k, (p, ed) in (("over", (po, eo)), ("under", (pu, eu))):
            b = base_name(p, decl)
            if b not in pcs:
                bad.append(f"vent {nm!r}: {k} {p!r} is not a drafted piece")
            elif ed not in (edges.get(b) or {}):
                bad.append(f"vent {nm!r}: no edge {ed!r} declared on {b!r} (edges.{b}: {', '.join(edges.get(b) or {}) or 'none'})")
            elif v[k] in in_seam:
                bad.append(f"vent {nm!r}: {v[k]} is in a seam: a vent's edges are open below its top; sew only the seam "
                           "above it (its edges from the vent top up)")
        if bad:
            continue
        top = _top(decl, po, eo, pu) if po != pu or eo != eu else None
        if top is None:
            bad.append(f"vent {nm!r}: {v['over']} must end where an edge of {po} sewn to {pu} starts (the vent top): "
                       "declare the vent edge from the hem to that point and the seam from it up")
        elif _top(decl, pu, eu, po) is None:
            bad.append(f"vent {nm!r}: {v['under']} must end where an edge of {pu} sewn to {po} starts (the vent top)")
    return bad


def _top(decl: dict, p: str, ed: str, other: str) -> str | None:
    """The vent edge's end that is an end of an edge of p sewn to `other` (names only), or None."""
    from .draft_own import _sides
    from .draft_pairs import base_name
    edges = decl.get("edges") or {}
    en = _ends((edges.get(base_name(p, decl)) or {}).get(ed))
    if en is None:
        return "?"  # (a path edge: its points are checked on the flat, not by name)
    for s in decl.get("seams") or []:
        A, B = _sides(s.get("a")), _sides(s.get("b"))
        for X, Y in ((A, B), (B, A)):
            if any(base_name(_pe(y)[0], decl) == base_name(other, decl) for y in Y):
                for x in X:
                    q, e2 = _pe(x)
                    if base_name(q, decl) == base_name(p, decl):
                        se = _ends((edges.get(base_name(q, decl)) or {}).get(e2))
                        hit = set(en) & set(se or ())
                        if hit:
                            return hit.pop()
    return None


def expand(D: dict, pr: set) -> dict:
    """Vents naming a pair's base name: one per side (P.L with Q.L, P.R with Q.R)."""
    if not D.get("vents"):
        return D
    out = []
    for v in D["vents"]:
        ps = [_pe(v.get(k))[0] for k in ("over", "under")]
        if not any(p in pr for p in ps):
            out.append(v)
            continue
        for sd in ("L", "R"):
            w = copy.deepcopy(v)
            for k in ("over", "under"):
                p, ed = _pe(v[k])
                if p in pr:
                    w[k] = f"{p}.{sd}:{ed}"
            w["name"] = f"{v.get('name', 'vent')}.{sd}"
            out.append(w)
    D["vents"] = out
    return D


def resolved(B: dict) -> list:
    """[{name, over, under: (piece, vent arc, seam arc ending at the top, top point)}] of the block's vents."""
    decl, arcs = B.get("decl") or {}, B.get("edge_arcs") or {}
    out = []
    for v in decl.get("vents") or []:
        sides = {}
        for k, o in (("over", "under"), ("under", "over")):
            p, ed = _pe(v[k])
            q = _pe(v[o])[0]
            va = (arcs.get(p) or {}).get(ed)
            en = _ends(va)
            if p not in B["pieces"] or en is None:
                break
            for S in B.get("seams") or []:
                A, Bs = ([s] if isinstance(s, str) else list(s) for s in S[:2])
                for X, Y in ((A, Bs), (Bs, A)):
                    if any(y.split(":", 1)[0] == q for y in Y):
                        for x in X:
                            px, ax = x.split(":", 1)
                            hit = set(en) & set(_ends(ax) or ())
                            if px == p and hit and k not in sides:
                                sides[k] = (p, va, ax, hit.pop())
        if len(sides) == 2:
            out.append(dict(name=v.get("name", "vent"), **sides))
    return out


def _seam_line(pc: dict, arc: str, top: str) -> tuple[np.ndarray, np.ndarray]:
    """(the vent top, the direction the seam runs on past it): the sewn edge's chord over RUN_ON from the top."""
    from . import pattern
    E = np.asarray(pc["P"], float)[pattern.arc_indices(pc, arc)]
    if arc.split(">")[-1] == top:
        E = E[::-1]
    L = np.r_[0, np.cumsum(np.linalg.norm(np.diff(E, axis=0), axis=1))]
    far = np.array([np.interp(min(RUN_ON, L[-1]), L, E[:, k]) for k in range(2)])
    d = E[0] - far
    return E[0], d / (np.linalg.norm(d) or 1.0)


def links(B: dict, crosses) -> list:
    """[(piece, piece)] both ways: the vents whose two edges the level crosses (open there, lapped)."""
    out = []
    for v in resolved(B):
        (po, ao, _, _), (pu, au, _, _) = v["over"], v["under"]
        if po != pu and crosses(po, ao) and crosses(pu, au):
            out += [(po, pu), (pu, po)]
    return out


def laps(B: dict, ring: set, lines: dict) -> float:
    """m taken off the ring's girth: each vent side's cloth past its seam line where the level crosses its vent edge."""
    from . import pattern
    from .draft_girths import _cross
    lap = 0.0
    for v in resolved(B):
        for p, va, sa, top in (v["over"], v["under"]):
            if p not in ring or p not in lines:
                continue
            pc = B["pieces"][p]
            q, u = lines[p]
            x = _cross(np.asarray(pc["P"], float)[pattern.arc_indices(pc, va)], q, u, closed=False)
            if not x:
                continue
            t0, d = _seam_line(pc, sa, top)
            den = d[0] * u[1] - d[1] * u[0]
            if abs(den) < 1e-9:
                continue
            w = t0 - q  # (q + s u = t0 + t d: solve for s)
            s = (w[0] * d[1] - w[1] * d[0]) / (u[0] * d[1] - u[1] * d[0])
            lap += abs(float((x[0][0] - q) @ u) - s)
    return lap
