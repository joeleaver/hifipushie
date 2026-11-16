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
  B inward). At an end that moves, the piece giving up width is trimmed along the edge beyond (the armhole, the hem)
  and the piece gaining it takes that strip of the edge on beyond its own end (the armhole runs on as one line; what one
  loses the other gains), that edge's points respaced over max(3 x the strip, SPREAD), none added. Then B's end that
  crosses it squarest (the hem, not the armhole: the cap's ease stays) is lengthened or shortened along the seam until
  the two edges are one length (with the seam's declared ease: its range's middle), so the seam sews, and a seam drafted
  off its length is trued by the same entry. A piece drawn on a re-cut piece's points (canvas, facing) moves with it. The re-cut is recorded in the block's `moves` (what moved, both lengths after).
`crossing` / `entry` give the declaration the panels row's FAIL names, so the agent's next call is the fix.
"""
from __future__ import annotations

import numpy as np

SPREAD = 0.03  # m: the least run of the edge beyond a moved end that eases the slide
LEAN = 3.0  # a seam under an end its curve can't take as far across leans at most 1 in this (_lean)
EXACT = 1e-5  # m: a point of another piece this near a host's point is drawn from it (FreeSewing copies points exactly;
# t s4-29: the back, drafted in the front's frame, lay 0.2-0.5 mm off three of its points and was dragged as a follower)
REACH = 0.03  # m: a follower's points this near its host's outline take the host's move in full, tapering to none at 2x
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
    E = P[ix] if end == 0 else P[ix][::-1]  # (the seam's run over its last SPREAD: its last few mm may turn into the
    # curve beyond: t s4-30, jaeger's back seam 48 degrees in its last 2 mm, and the run set on the side body went out)
    La = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(E, axis=0), axis=1))])
    tng = P[i0] - E[min(int(np.searchsorted(La, SPREAD)), len(E) - 1)]
    tng = tng / max(np.linalg.norm(tng), 1e-12)
    nrm = np.array([-tng[1], tng[0]])
    from .draft_caught import _inside  # (outward by a point just off the seam: a corner's own normal, between two
    # points FreeSewing joined at one place, pointed in on jaeger's side body and the run set on went the wrong way, F6)
    a = min(1e-3, 0.25 * float(np.linalg.norm(P[i0] - P[ix[1] if end == 0 else ix[-2]])))
    nrm = -nrm if _inside((P[i0] - a * tng + a * nrm)[None], P)[0] else nrm
    return step, u, nrm, tng


def _axis(P: np.ndarray, ix: list) -> np.ndarray:
    """The direction the seam moves in: along the levels a girth is read on (across the grain for a seam running up
    it, flat y being the grain; up the grain for one running across), signed out of the piece across the seam. Moved
    along each piece's own normal instead, a seam whose top bends toward its armhole (t s4-29: the jacket front's last
    10 mm at 24 degrees) moved up as much as across, and the girth at the underarm grew 16 mm."""
    d = P[ix[-1]] - P[ix[0]]
    ax = np.array([1.0, 0.0]) if abs(d[1]) >= abs(d[0]) else np.array([0.0, 1.0])
    return ax if float(_normals(P)[ix].sum(0) @ ax) >= 0 else -ax


def _slide(P: np.ndarray, ix: list, end: int, D: np.ndarray, stops: set) -> None:
    """Move the edge's end (0: first, -1: last) by D, easing the outline beyond it over max(3 |D|, SPREAD), never past
    another edge's end."""
    n = len(P)
    i0 = ix[end]
    step = _frame(P, ix, end)[0]
    A = max(3 * float(np.linalg.norm(D)), SPREAD)
    own = set(ix) | stops
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


def _run(P: np.ndarray, ix: list, end: int, A: float | None, stops: set) -> list:
    """Outline indices beyond the edge's end, from it out to the first point A m along (None: to the next end of an
    edge); never past another edge's end (t s4-29: the side body's short armhole respaced on down its back seam)."""
    n, own = len(P), set(ix) | stops
    step, k, a, out = _frame(P, ix, end)[0], ix[end], 0.0, []
    for _ in range(n):
        j = (k + step) % n
        out.append(j)
        if j in own:
            out.pop()
            break
        a += float(np.linalg.norm(P[j] - P[k]))
        k = j
        if A is not None and a >= A:
            break
    return out


def _resample(Q: np.ndarray, m: int) -> np.ndarray:
    L = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(Q, axis=0), axis=1))])
    t = np.linspace(0, L[-1], m)
    return np.stack([np.interp(t, L, Q[:, k]) for k in range(2)], axis=1)


def _resample2(Q1: np.ndarray, Q2: np.ndarray, m: int) -> np.ndarray:
    """m points over Q1 then Q2 (Q1 ends where Q2 starts), that joint kept as a point: the old corner the strip is set
    on at (respaced through, its corner cut and the armhole ran 1 mm short)."""
    l1, l2 = _len(Q1), _len(Q2)
    if m < 3 or l1 + l2 <= 0:
        return _resample(np.vstack([Q1, Q2[1:]]), m)
    k1 = int(np.clip(round((m - 1) * l1 / (l1 + l2)), 1, m - 2))
    return np.vstack([_resample(Q1, k1 + 1), _resample(Q2, m - k1)[1:]])


def _reach(Q: np.ndarray, inward: np.ndarray, need: float) -> tuple:
    """(m along polyline Q (from Q[0], the end) the end slides, m across that gives): the end slides `need` m ALONG the
    curve (what the gaining piece takes of it), giving as much across as the curve does there (a hem: all of it; an
    armhole rising from its corner: less, t s4-30: jaeger's back armhole reaches 18 mm across in all). Slid instead to
    where the curve reaches `need` across, or its farthest, the end went 109-135 mm up the armholes and met them
    parallel to the seam: a spike on the side body's top (F6)."""
    s = min(float(need), _len(Q))
    return s, float(max((_at(Q, s)[1] - Q[0]) @ inward, 0.0))


def _profile(prof: np.ndarray, t) -> np.ndarray:
    """The move at mm-along t: smooth through the listed points (no kink at a level: a pattern maker's curve, not a
    polyline; it never overshoots them), held past the first / last."""
    from scipy.interpolate import PchipInterpolator
    x, i = np.unique(prof[:, 0], return_index=True)
    t = np.clip(np.asarray(t, float), x[0], x[-1])
    return np.interp(t, x, prof[i, 1]) if len(x) < 3 else PchipInterpolator(x, prof[i, 1])(t)


def _lean(prof: np.ndarray, LA0: float, end: int, e: float, s: float) -> np.ndarray:
    """The profile near an end that can give only e m across (_reach): each point's move at most e + (its distance
    from the end + the slide s) / LEAN, so the seam leans from its new end down to the levels at most 1 in LEAN, never
    hooks (t s4-30: a seam moved 33 mm a level 13 mm under an end that kept its place hooked the side body's top)."""
    t = np.union1d(np.linspace(0.0, LA0, max(int(LA0 / 0.002), 2) + 1), prof[:, 0][(prof[:, 0] >= 0) & (prof[:, 0] <= LA0)])
    v = _profile(prof, t)
    cap = e + (np.abs(t - (0.0 if end == 0 else LA0)) + s) / LEAN
    return np.stack([t, np.sign(v) * np.minimum(np.abs(v), cap)], axis=1)


def _at(Q: np.ndarray, s: float) -> tuple:
    """(index k, the point) s m along polyline Q: the point lies on segment k..k+1."""
    L = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(Q, axis=0), axis=1))])
    k = int(np.clip(np.searchsorted(L, s, side="right") - 1, 0, len(Q) - 2))
    f = (s - L[k]) / max(L[k + 1] - L[k], 1e-12)
    return k, Q[k] + f * (Q[k + 1] - Q[k])


def _between(Pt: np.ndarray, Q: np.ndarray, m: int) -> np.ndarray:
    """m points evenly on the line from Pt to Q, both left out."""
    return Pt + np.outer(np.arange(1, m + 1) / (m + 1), Q - Pt) if m > 0 else np.zeros((0, 2))


def _insert(pc: dict, a: int, b: int, pts: np.ndarray, idmap: np.ndarray) -> None:
    """pts set into the outline between adjacent points a and b (in order from a to b); names and idmap (each old
    point's index now) shifted past them."""
    P, k = np.asarray(pc["P"], float), len(pts)
    if not k:
        return
    n = len(P)
    at, pts = (a + 1, pts) if b == (a + 1) % n else (a, pts[::-1])
    pc["P"] = np.vstack([P[:at], pts, P[at:]])
    pc["names"] = {nm: (i + k if i >= at else i) for nm, i in pc["names"].items()}
    idmap[idmap >= at] += k


def _giver(v: float, A: tuple, B: tuple) -> tuple:
    """(the side giving up width, the side gaining it) for a move of v toward B."""
    return (B, A) if v > 0 else (A, B)


def _slide_of(O: np.ndarray, ix: list, end: int, need: float, stops: set) -> tuple:
    """(the curve beyond the giving piece's end, the slide along it, m across that gives) for `need` m across."""
    beyond = _run(O, ix, end, None, stops)
    if not beyond:
        raise Refused("has no edge beyond it to slide along")
    Q = np.vstack([O[ix[end]], O[beyond]])
    return (Q, *_reach(Q, -_axis(O, ix), need))  # (into the giving piece: its seam moves in)


def _ends(sA: tuple, sB: tuple, v: float, end: int, adds: list) -> None:
    """A move of v m toward B at that end, after both edges moved across the levels (s*: (P, O: the outline before,
    ix, stops, piece)). The end lies on another edge of both pieces (the armhole, a neckline, the hem): it SLIDES ALONG
    that edge, as a pattern maker re-splits an armhole, never across it. The piece giving up width loses the run of
    the edge beyond its end that gives |v| across (_reach, measured along the curve): its end set where that run ends,
    the rest of the edge respaced over max(3 x the run, SPREAD), never past another edge's end. The piece gaining
    width takes exactly that run (same arc, same points), set on beyond its own end in its own frame (along its seam,
    out past it), so the edge runs on as one line and its total over both pieces stays (the sleeve cap's ease with
    it). Each seam runs on in a line from where the levels put its end to its new end, every other point where the
    levels put it (so every level keeps its girth). New points go into `adds` (set in once both ends are done)."""
    (Ps, Os, is_, ss, ps), (Pg, Og, ig, _, pg) = _giver(v, sA, sB)
    _, _, ns, ts = _frame(Os, is_, end)
    _, _, ng, tg = _frame(Og, ig, end)
    Cs, Cg = Os[is_[end]].copy(), Og[ig[end]].copy()
    Q, s, _ = _slide_of(Os, is_, end, abs(v), ss)
    if s <= 1e-6:
        return
    k, X = _at(Q, s)
    strip = np.vstack([Q[: k + 1], X])
    rs = _run(Os, is_, end, max(3 * s, SPREAD), ss)
    seg = np.vstack([Cs, Os[rs]])
    Ls = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(seg, axis=0), axis=1))])
    keep = seg[Ls > s - 1e-12]
    if not len(keep):
        raise Refused("is shorter than the run the end slides along it")
    new = _resample(np.vstack([X, keep]), len(rs) + 1)
    E = Os[is_]
    gap = float(np.median(np.linalg.norm(np.diff(E, axis=0), axis=1))) or SPREAD
    nb = is_[1] if end == 0 else is_[-2]  # (the seam's point next to its end)
    m = int(np.linalg.norm(new[0] - Ps[nb]) / gap)
    Ps[is_[end]] = new[0]
    Ps[rs] = new[1:]
    adds.append((ps, is_[end], nb, _between(new[0], Ps[nb], m)))
    rel = strip - Cs  # (the run in the gaining piece's frame: along its seam, out past it)
    mapped = Cg + np.outer(rel @ ts, tg) + np.outer(-(rel @ ns), ng)
    step = _frame(Og, ig, end)[0]
    nb = ig[1] if end == 0 else ig[-2]
    Pg[ig[end]] = mapped[-1]
    adds.append((pg, ig[end], (ig[end] + step) % len(Og), mapped[::-1][1:]))
    adds.append((pg, ig[end], nb, _between(mapped[-1], Pg[nb], int(np.linalg.norm(mapped[-1] - Pg[nb]) / gap))))


def _recut(pa: dict, ia: list, pb: dict, ib: list, prof: np.ndarray, LA0: float, stops: tuple) -> dict:
    """Both edges moved across the levels by the profile at each point's share of its edge (so what A gains at a level
    B loses at that level: the girth holds there), leaned under an end its curve can't take that far (_lean), then
    each moved end slid along its curve (_ends). Returns {"a" / "b": each old point's index now}."""
    OA, OB = np.asarray(pa["P"], float), np.asarray(pb["P"], float)
    PA, PB = OA.copy(), OB.copy()
    A, B = (PA, OA, ia, stops[0], "a"), (PB, OB, ib, stops[1], "b")
    ends = [float(_profile(prof, 0.0 if e == 0 else LA0)) for e in (0, -1)]  # (each end's slide along its curve)
    for e, v in zip((0, -1), ends):  # (an end its curve can't take as far across as asked: the seam leans down from it)
        if abs(v) > 1e-6:
            (_, Os, is_, ss, _), _ = _giver(v, A, B)
            _, sl, got = _slide_of(Os, is_, e, abs(v), ss)
            if got < abs(v) - 1e-6:
                prof = _lean(prof, LA0, e, got, sl)

    def s_of(P, ix):
        E = P[ix]
        L = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(E, axis=0), axis=1))])
        return _profile(prof, L / (L[-1] or 1.0) * LA0)
    sA, sB = s_of(OA, ia), s_of(OB, ib)
    PA[ia] = OA[ia] + np.outer(sA, _axis(OA, ia))
    PB[ib] = OB[ib] - np.outer(sB, _axis(OB, ib))
    adds: list = []
    for e, v in zip((0, -1), ends):
        if abs(v) > 1e-6:
            _ends(A, B, v, e, adds)
    pa["P"], pb["P"] = PA, PB
    pcs = {"a": pa, "b": pb}
    idmap = {"a": np.arange(len(OA)), "b": np.arange(len(OB))}
    for who, i, j, pts in adds:  # (each between a point and its neighbour, by their indices now)
        _insert(pcs[who], int(idmap[who][i]), int(idmap[who][j]), pts, idmap[who])
    return idmap


def _true(pc: dict, ix: list, target: float, stops: set) -> float:
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
        _slide(P, ix, e, -r * _frame(P, ix, e)[3], stops)
        pc["P"] = P
    return _len(np.asarray(pc["P"])[ix]) - target


def _followers(pieces: dict, hosts: tuple) -> dict:
    """{piece: its host}: pieces drawn on a host's own points (a canvas, a facing: FreeSewing parts made `from` it, one
    frame): at least 3 of its points exactly on the host's, and most of them on or inside the host. Read before the re-cut. A
    neighbour drafted in the same frame (jaeger's back beside its front) lies outside it and is no follower."""
    from .draft_caught import _inside
    out = {}
    for nm, pc in pieces.items():
        if nm in hosts:
            continue
        Q = np.asarray(pc["P"], float)
        for h in hosts:
            H = np.asarray(pieces[h]["P"], float)
            on = np.linalg.norm(Q[:, None] - H[None], axis=2).min(1) < EXACT
            if on.sum() >= 3 and (on | _inside(Q, H)).mean() > 0.5:
                out[nm] = h
                break
    return out


def _follow(pc: dict, H0: np.ndarray, H1: np.ndarray) -> None:
    """The follower takes its host's move: each of its points the move of the host's outline nearest it, in full within
    REACH, tapering to none at 2 x REACH (its own cut lines near the moved seam move with it: t s4-29, the canvas's edge
    beside the front's side seam was left 23 mm outside it)."""
    D = H1 - H0
    if not np.any(np.linalg.norm(D, axis=1) > 1e-7):
        return
    a, ab = H0, np.roll(H0, -1, axis=0) - H0
    Q = np.asarray(pc["P"], float)
    t = np.clip(np.einsum("qkd,kd->qk", Q[:, None] - a[None], ab) / np.maximum((ab * ab).sum(1), 1e-18), 0, 1)
    dist = np.linalg.norm(Q[:, None] - (a[None] + t[..., None] * ab[None]), axis=2)
    k = dist.argmin(1)
    r = np.arange(len(Q))
    tk = t[r, k][:, None]
    w = np.clip(2.0 - dist[r, k] / REACH, 0.0, 1.0)[:, None]
    pc["P"] = Q + w * ((1 - tk) * D[k] + tk * np.roll(D, -1, axis=0)[k])


def apply(pieces: dict, ix_of, seams: list, moves: list, stops: dict | None = None) -> list:
    """Every move re-cut on `pieces` (module docstring). ix_of("piece:edge") -> outline indices; seams = the declared
    seams (to check the two edges are sewn to each other, and to true the moved pieces' other seams); stops = {piece:
    outline indices of its declared edges' ends}. Returns the record of what moved."""
    names = {p: {n for n, i in pieces[p]["names"].items() if i in ix} for p, ix in (stops or {}).items() if p in pieces}
    stop = lambda p: {pieces[p]["names"][n] for n in names.get(p, ())}  # (by name: a re-cut adds points)
    sewn, plain = {}, []  # (A, B) -> the ease B is trued to: A / B - 1, the mean of the seam's declared range (none: 0)
    for s in seams or []:
        a, b = s.get("a"), s.get("b")
        if isinstance(a, str) and isinstance(b, str):
            mid = float(np.mean(s["ease"])) if s.get("ease") is not None else 0.0
            sewn[(a, b)], sewn[(b, a)] = mid, 1.0 / (1.0 + mid) - 1.0
            plain.append((a, b))
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
        L = lambda e: _len(np.asarray(pieces[e.split(":", 1)[0]]["P"])[ix_of(e)])
        others = [(x, y) for x, y in plain if {x, y} != set(sm) and x.split(":", 1)[0] in (pa, pb)
                  and y.split(":", 1)[0] not in (pa, pb)]
        was = {(x, y): L(x) / max(L(y), 1e-12) for x, y in others}
        LA0, LB0 = L(sm[0]), L(sm[1])
        old = {h: np.asarray(pieces[h]["P"], float).copy() for h in (pa, pb)}
        fol = _followers(pieces, (pa, pb))
        try:
            idm = _recut(pieces[pa], ia, pieces[pb], ib, prof, LA0, (stop(pa), stop(pb)))
        except Refused as e:
            raise Refused(f"{tag}: the edge beyond an end of {sm[0]} or {sm[1]} {e}: taper the move to 0 there") from None
        LA = L(sm[0])
        err = _true(pieces[pb], ix_of(sm[1]), LA / (1.0 + sewn[tuple(sm)]), stop(pb))
        for (x, y), r in was.items():  # (the moved pieces' other seams kept at their ease: the side body's back seam)
            p = x.split(":", 1)[0]
            _true(pieces[p], ix_of(x), r * L(y), stop(p))
        for f, h in fol.items():  # (the host's points it had before, where they are now)
            _follow(pieces[f], old[h], np.asarray(pieces[h]["P"], float)[idm["a" if h == pa else "b"]])
        LB = L(sm[1])
        out.append({"seam": sm, "at": m.get("at"), "lengths_mm": [round(1000 * LA, 1), round(1000 * LB, 1)],
                    "was_mm": [round(1000 * LA0, 1), round(1000 * LB0, 1)], "off_mm": round(1000 * err, 2),
                    "followers": sorted(fol)})
    return out


def _edge_name(B: dict, p: str, arcs) -> str | None:
    """The declared edge a seam side's arcs are: one edge, or the halves a dart's release split it into (<edge>.1, .2)."""
    import re
    names = {v: k for k, v in (B.get("edge_arcs") or {}).get(p, {}).items()}
    got = [names.get(a) for a in arcs]
    if None in got:
        return None
    base = {re.sub(r"\.\d+$", "", g) if len(got) > 1 else g for g in got}
    return base.pop() if len(base) == 1 else None


def crossing(B: dict, p: str, q: str, line: tuple) -> tuple | None:
    """([p's edge, q's edge], mm along p's edge from its start where the level line (q0, u) on p crosses their seam,
    p's edge's length mm);
    None when they share no seam of one declared edge a side, or the line misses it."""
    from .draft_girths import _cross, _edge, _seam_pairs
    for pa, ea, pb, eb in _seam_pairs(B):
        if pa != p or pb != q:
            continue
        na, nb = _edge_name(B, p, ea), _edge_name(B, q, eb)
        if not (na and nb):
            continue
        E = _edge(B["pieces"], p, ea)
        hit = _cross(E, np.asarray(line[0], float), np.asarray(line[1], float), closed=False)
        if not hit:
            return None
        _, i, t = hit[0]
        L = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(E, axis=0), axis=1))])
        return [f"{p}:{na}", f"{q}:{nb}"], 1000 * (L[i] + t * (L[i + 1] - L[i])), 1000 * L[-1]
    return None


def ends(at: dict, length: float) -> dict:
    """`at` with both ends of the seam stated: an end within LEAN x its nearest level's move of that level slides
    along its curve by that move (the armhole re-split, so the seam can't hook under it); a farther end stays (0: the
    move tapers out before it, t s4-30: the back seam's foot on the vent, whose edge runs down the seam, can't slide)."""
    if not at:
        return at
    out = dict(at)
    for e in (0.0, float(length)):
        k = min(at, key=lambda x: abs(x - e))
        if round(e) not in out:
            out[round(e)] = at[k] if abs(k - e) <= LEAN * abs(at[k]) else 0.0
    return out


def entry(seam: list, at: dict) -> str:
    """A `moves` entry as the agent declares it: at {mm along: mm toward the second piece}."""
    pts = ", ".join(f"[{k:.0f}, {v:.0f}]" for k, v in sorted(at.items()))
    return f'{{"seam": ["{seam[0]}", "{seam[1]}"], "at": [{pts}]}}'
