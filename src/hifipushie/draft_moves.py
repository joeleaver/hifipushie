"""Declaration `moves` (F5): a seam line moved between the two pieces it joins, by mm at points along it; the converter
re-cuts both pieces so they still sew.

Why (trial s4-29, the suit jacket, 2026-11-15): step 2's panel shares asked for a real side body, the FreeSewing block
(jaeger) gives a 34 mm one, and the agent spent most of its budget re-cutting it by hand in design.mjs (a strip off the
front, one off the back, each level by hand). Taking width in at the top of the front / side seam then made one side's
slant from the shared armhole point longer than the other's and the seams row failed (477 vs 467 mm). A pattern maker
moves the seam LINE: what one piece gives up, its neighbour gains, and the seam stays one length on both sides. FreeSewing
blocks expose a seam's placement only where their author made it an option (jaeger: sideFrontPlacement, the front seam at
the waist, 80-90 %), so it can't be the general route; this declaration works on any block's pieces. Nothing here knows
a garment.

FORM: moves [{"seam": ["pieceA:edge", "pieceB:edge"] (two declared edges sewn to each other), "at": [[mm along A's edge
  from its start, mm the seam moves toward B], ...], "why"?}]. A grows, B shrinks (a negative mm: the other way). Between
  the listed points the move is linear; past the first / last it holds (list [0, 0] and [A's length, 0] to taper it out).
  A ".L" move brings its ".R" twin unless that is declared too.
HOW (`apply`): each point of both edges moves along its piece's normal by the move at its share of the edge (A outward,
  B inward). An end that moves slides along the edge beyond it (the armhole, the hem: trimmed on one piece, extended on
  the other), the points of that edge eased over max(3 x the slide, SPREAD) so none crosses another. Then B's end that
  changes the seam's length most per mm slides until the two edges differ by what they differed before (the declared
  ease kept): the seam still sews. The re-cut is recorded in the block's `moves` (what moved, both lengths after).
`hint` gives the declaration the panels row's FAIL names, so the agent's next call is the fix.
"""
from __future__ import annotations

import numpy as np

SPREAD = 0.03  # m: the least run of the edge beyond a moved end that eases the slide
FORM = ('moves [{"seam": ["pieceA:edge", "pieceB:edge"], "at": [[mm along A\'s edge from its start, mm toward B], ...]}] '
        '(A grows, B shrinks; held past the listed points: add [0, 0] / [A\'s length, 0] to taper)')


class Refused(ValueError):
    pass


def _swap(n: str) -> str:
    return n[:-2] + (".R" if n.endswith(".L") else ".L") if n.endswith((".L", ".R")) else n


def expand(moves: list, pieces: set) -> list:
    """The moves with each ".L" move's ".R" twin added (unless declared)."""
    out = [dict(m) for m in moves or []]
    have = {tuple(m.get("seam") or ()) for m in out}
    for m in list(out):
        s = list(m.get("seam") or ())
        if len(s) == 2 and all(isinstance(e, str) and ":" in e for e in s):
            tw = tuple(f"{_swap(e.split(':', 1)[0])}:{e.split(':', 1)[1]}" for e in s)
            if tw != tuple(s) and tw not in have and all(e.split(":", 1)[0] in pieces for e in tw):
                out.append(dict(m, seam=list(tw)))
                have.add(tw)
    return out


def _len(P: np.ndarray) -> float:
    return float(np.sum(np.linalg.norm(np.diff(P, axis=0), axis=1)))


def _normals(P: np.ndarray) -> np.ndarray:
    """Outward unit normals at every outline point of closed polygon P."""
    t = np.roll(P, -1, axis=0) - np.roll(P, 1, axis=0)
    area = 0.5 * float(np.sum(P[:, 0] * np.roll(P[:, 1], -1) - np.roll(P[:, 0], -1) * P[:, 1]))
    n = np.stack([t[:, 1], -t[:, 0]], axis=1) * (1.0 if area > 0 else -1.0)
    return n / np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-12)


def _frame(P: np.ndarray, ix: list, end: int) -> tuple:
    """(step round the outline beyond the end, u: unit along the edge beyond it, nrm: the seam's outward normal there,
    tng: the seam's tangent there pointing out of the edge)."""
    n = len(P)
    i0 = ix[end]
    d = (ix[1] - ix[0]) % n == 1
    step = (-1 if d else 1) if end == 0 else (1 if d else -1)
    u = P[(i0 + step) % n] - P[i0]
    u = u / max(np.linalg.norm(u), 1e-12)
    tng = P[i0] - P[ix[1] if end == 0 else ix[-2]]
    tng = tng / max(np.linalg.norm(tng), 1e-12)
    nrm = np.array([-tng[1], tng[0]])
    nrm = nrm if float(nrm @ _normals(P)[i0]) >= 0 else -nrm
    return step, u, nrm, tng


def _slide(P: np.ndarray, ix: list, end: int, D: np.ndarray) -> None:
    """Move the edge's end (0: first, -1: last) by D, easing the outline beyond it over max(3 |D|, SPREAD)."""
    n = len(P)
    i0 = ix[end]
    step = _frame(P, ix, end)[0]
    A = max(3 * float(np.linalg.norm(D)), SPREAD)
    own = set(ix)
    a, k, prev = 0.0, i0, P[i0].copy()
    P[i0] = P[i0] + D
    for _ in range(n):
        k = (k + step) % n
        if k in own:
            break
        a += float(np.linalg.norm(P[k] - prev))
        prev = P[k].copy()
        if a >= A:
            break
        P[k] = P[k] + D * (1 - a / A)


def _run(P: np.ndarray, ix: list, end: int, A: float | None) -> list:
    """Outline indices beyond the edge's end, from it out to the first point A m along (None: to the outline's next
    point of the edge); the last one stays where it is."""
    n, own = len(P), set(ix)
    step, k, a, out = _frame(P, ix, end)[0], ix[end], 0.0, []
    for _ in range(n):
        j = (k + step) % n
        if j in own:
            break
        a += float(np.linalg.norm(P[j] - P[k]))
        out.append(j)
        k = j
        if A is not None and a >= A:
            break
    return out


def _resample(Q: np.ndarray, m: int) -> np.ndarray:
    L = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(Q, axis=0), axis=1))])
    t = np.linspace(0, L[-1], m)
    return np.stack([np.interp(t, L, Q[:, k]) for k in range(2)], axis=1)


def _ends(PA, ia, PB, ib, v: float, end: int) -> None:
    """A move of v m toward B at that end: the piece that gives up width there is trimmed along the edge beyond its end
    (the armhole, the hem) to where it lies |v| inside the seam; the one that gains it takes that strip of the edge, set
    on beyond its own end in its own frame, so the edge beyond runs on as one line and both seam sides stay one length.
    The points of the edge beyond are respaced over max(3 x the strip, SPREAD); none is added, none taken away."""
    (Ps, is_), (Pg, ig) = ((PB, ib), (PA, ia)) if v > 0 else ((PA, ia), (PB, ib))
    _, _, ns, ts = _frame(Ps, is_, end)
    _, _, ng, tg = _frame(Pg, ig, end)
    Cs, Cg = Ps[is_[end]].copy(), Pg[ig[end]].copy()
    beyond = _run(Ps, is_, end, None)
    Q = np.vstack([Cs, Ps[beyond]])
    dep = -(Q - Cs) @ ns
    k = next((i for i in range(1, len(Q)) if dep[i] >= abs(v)), None)
    if k is None:
        raise Refused("doesn't reach that far inside the seam, so the end can't be trimmed along it")
    f = (abs(v) - dep[k - 1]) / max(dep[k] - dep[k - 1], 1e-12)
    X = Q[k - 1] + f * (Q[k] - Q[k - 1])
    strip = np.vstack([Q[:k], X])
    sl = _len(strip)
    rs = _run(Ps, is_, end, max(3 * sl, SPREAD))
    seg = np.vstack([Cs, Ps[rs]])
    Ls = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(seg, axis=0), axis=1))])
    keep = seg[Ls > _len(strip[: k + 1]) - 1e-12] if len(seg) > 1 else seg[-1:]
    new = _resample(np.vstack([X, keep]), len(rs) + 1)
    Ps[is_[end]] = new[0]
    Ps[rs] = new[1:]
    rel = strip - Cs  # (the strip in the gaining piece's frame: along its seam, out past it)
    mapped = Cg + np.outer(rel @ ts, tg) + np.outer(-(rel @ ns), ng)
    rg = _run(Pg, ig, end, max(3 * sl, SPREAD))
    new = _resample(np.vstack([mapped[::-1], Pg[rg]]), len(rg) + 1)
    Pg[ig[end]] = new[0]
    Pg[rg] = new[1:]


def _recut(pa: dict, ia: list, pb: dict, ib: list, prof: np.ndarray, LA0: float) -> None:
    PA, PB = np.asarray(pa["P"], float).copy(), np.asarray(pb["P"], float).copy()

    def s_of(P, ix):
        E = P[ix]
        L = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(E, axis=0), axis=1))])
        return np.interp(L / (L[-1] or 1.0) * LA0, prof[:, 0], prof[:, 1])
    sA, sB = s_of(PA, ia), s_of(PB, ib)
    nA, nB = _normals(PA), _normals(PB)
    for e in (0, -1):
        if abs(sA[e]) > 1e-6:
            _ends(PA, ia, PB, ib, float(sA[e]), e)
    for i, k in enumerate(ia[1:-1], 1):
        PA[k] = PA[k] + sA[i] * nA[k]
    for i, k in enumerate(ib[1:-1], 1):
        PB[k] = PB[k] - sB[i] * nB[k]
    pa["P"], pb["P"] = PA, PB


def _true(pc: dict, ix: list, target: float) -> float:
    """The edge made target m long as a pattern maker trues a seam: its end where the edge beyond crosses it squarest
    (the hem, not the armhole: the cap's ease stays) lengthened or shortened along the seam, the edge beyond eased.
    Needed because two sewn edges are rarely one curve (each piece's shaping): moved together, one gains what the
    other loses only where their curves mirror. Returns the error left."""
    P0 = np.asarray(pc["P"], float)
    e = max((0, -1), key=lambda k: abs(float(_frame(P0, ix, k)[1] @ _frame(P0, ix, k)[2])))
    for _ in range(4):
        P = np.asarray(pc["P"], float).copy()
        r = _len(P[ix]) - target
        if abs(r) < 1e-5:
            break
        _slide(P, ix, e, -r * _frame(P, ix, e)[3])
        pc["P"] = P
    return _len(np.asarray(pc["P"])[ix]) - target


def apply(pieces: dict, ix_of, seams: list, moves: list) -> list:
    """Every move re-cut on `pieces` (module docstring). ix_of("piece:edge") -> outline indices; seams = the declared
    seams (to check the two edges are sewn to each other). Returns the record of what moved."""
    sewn = set()
    for s in seams or []:
        a, b = s.get("a"), s.get("b")
        if isinstance(a, str) and isinstance(b, str):
            sewn |= {(a, b), (b, a)}
    out = []
    for m in expand(moves, set(pieces)):
        sm = m.get("seam")
        tag = f"moves {sm}"
        if not (isinstance(sm, list) and len(sm) == 2 and all(isinstance(e, str) and ":" in e for e in sm)):
            raise Refused(f"{tag}: \"seam\" is two declared edges sewn to each other, [\"pieceA:edge\", \"pieceB:edge\"]")
        if tuple(sm) not in sewn:
            raise Refused(f"{tag}: {sm[0]} and {sm[1]} aren't one declared seam (a seam [\"a\", \"b\"] of single edges)")
        try:
            prof = np.asarray(m.get("at"), float).reshape(-1, 2) / 1000.0
        except (TypeError, ValueError):
            raise Refused(f"{tag}: \"at\" is [[mm along {sm[0]} from its start, mm toward {sm[1].split(':')[0]}], ...]")
        if not len(prof):
            raise Refused(f"{tag}: \"at\" is empty")
        prof = prof[np.argsort(prof[:, 0])]
        (pa, _), (pb, _) = (e.split(":", 1) for e in sm)
        ia, ib = ix_of(sm[0]), ix_of(sm[1])
        LA0, LB0 = _len(np.asarray(pieces[pa]["P"])[ia]), _len(np.asarray(pieces[pb]["P"])[ib])
        try:
            _recut(pieces[pa], ia, pieces[pb], ib, prof, LA0)
        except Refused as e:
            raise Refused(f"{tag}: the edge beyond an end of {sm[0]} or {sm[1]} {e}: taper the move to 0 there") from None
        LA = _len(np.asarray(pieces[pa]["P"])[ia])
        err = _true(pieces[pb], ib, LA + (LB0 - LA0))
        LB = _len(np.asarray(pieces[pb]["P"])[ib])
        out.append({"seam": sm, "at": m.get("at"), "lengths_mm": [round(1000 * LA, 1), round(1000 * LB, 1)],
                    "was_mm": [round(1000 * LA0, 1), round(1000 * LB0, 1)], "off_mm": round(1000 * err, 2)})
    return out


def hint(B: dict, p: str, q: str, line: tuple, mm: float) -> str:
    """The `moves` entry that moves the seam between p (grows) and q by mm at the level line (q0, u) on p; "" when
    the seam isn't one declared edge a side."""
    from . import pattern
    from .draft_girths import _cross, _seam_pairs
    names = {v: k for k, v in (B.get("edge_arcs") or {}).get(p, {}).items()}
    namesq = {v: k for k, v in (B.get("edge_arcs") or {}).get(q, {}).items()}
    for pa, ea, pb, eb in _seam_pairs(B):
        if pa == p and pb == q and len(ea) == len(eb) == 1 and ea[0] in names and eb[0] in namesq:
            E = np.asarray(B["pieces"][p]["P"], float)[pattern.arc_indices(B["pieces"][p], ea[0])]
            hit = _cross(E, np.asarray(line[0], float), np.asarray(line[1], float), closed=False)
            if not hit:
                return ""
            _, i, t = hit[0]
            L = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(E, axis=0), axis=1))])
            at = L[i] + t * (L[i + 1] - L[i])
            return (f'{{"seam": ["{p}:{names[ea[0]]}", "{q}:{namesq[eb[0]]}"], "at": [[{1000 * at:.0f}, '
                    f'{mm:.0f}]]}}')
    return ""
