"""Step-4 row `girths`: the flat pattern round every girth it hangs on, against the body + the plan's ease (G1).

Why (2026-11-14): ten step-5 runs failed to fit the suit jacket with every link at its cut; D1 proved the pattern
consistent with itself, D2 measured it round the body: chest 1035 against a planned 1108, waist 894 against 988, hips
1007 against 1103 (70-130 mm less ease than planned), seat 25 mm and the biceps 7 mm under the body + the cloth's gap.
Its step 4 had been approved: this row was INFO "n/a" (it needed body landmarks the model lacked, then the open front
broke its ring). Joe: "the flat gate (step 4) must check every pattern length against the body measurement step 1
names for it + the plan's ease ... before any build". So the row reads ONLY declared data (step 3's tapes, step 4's
`tapes` declarations, step 0's fit, the flat) and FAILs where a declaration it needs is missing; it never says n/a.

THE GIRTHS: every step-3 girth tape (a loop) some piece's `tapes` names (draft_tapes); each is checked round every
ring of pieces it crosses (a left and a right sleeve: two rings).
THE LEVEL on a piece: from the declared LENGTH tape of that piece that crosses the girth's plane (the step-3 path; of
several, the one whose top is highest, as piece_start's panel start): its surface length from its top end (the end
highest and nearest the centre line: an hps, a shoulder point, an armpit) to the plane is the drop from the piece's top
(its highest flat point; flat y runs up the grain). A level above the lowest point of the piece's edges sewn to a piece
of another body part (an armhole, a sleeve cap) is taken there: a tailor's chest line runs through the underarm, one
underarm round the ring (one_underarm). A piece with no such tape gets the level over its seams at the same share of the
seam's length (sewn end to end).
THE RING: pieces linked where the level crosses both sides of a seam (a closure links its over and under pieces);
pieces with fewer than two links are pruned (a facing or canvas lying on another is not round the body). A piece in
the ring whose `tapes` don't name the girth FAILs as a missing declaration (its numbers still shown).
THE PATTERN'S GIRTH: each piece's width along its level, inside its outline only (even-odd: an open dart's gap and a
cut-through dart are out), summed; a closure's lap taken off: each side's front edge to the centre line through its
own fastening marks (`pairs` / `at`). Where a side's edge stands SHORT of that line (a cut-away below the button) the
level is OPEN: the girth is the cloth only (nothing lapped), the gap is said, and the cloth's-minimum FAIL doesn't
apply (it can't be too tight to close where it doesn't close). The plan's girth is the garment's girth closed (step 0
reads a garment worn open as its closed girth, C388), so the plan check applies to closed and open levels alike: a
cut-away level the plan states is held to it. A garment with no closure: the ring left after pruning, or the open chain.
THE CHECK: target = body (step 3) + the plan's ease for that girth (step 0's fit, by name); with no stated ease only
the minimum applies. FAIL: a closed level under body + 2 pi GAP (it can't be worn: the cloth stands GAP off the skin);
FAIL: off the target by more than max(TOL_MM, TOL_FRAC x the planned ease) either way. Nothing here knows a garment."""
from __future__ import annotations

import math

import numpy as np

TOL_MM = 15.0  # mm: the level is placed to ~1 cm on a shaped piece where the round changes ~4 mm per cm (C383), and
# step 0's girth is read off a picture to ~5 mm: 15 mm is what placement + reading can't promise better than
REACH = 0.02  # m: a length tape ending this close short of a girth's plane still places it (run on straight)
CENTRE = 0.01  # m: a tape's top end this close to the centre line starts at the piece's centre-line top (a cbNeck)
TOL_FRAC = 0.15  # x the planned ease: a loose plan (200 mm of ease) is read off a picture less exactly than a close one
DEF_TOL = 0.01  # x the girth: step 0's body girth this far from step 3's same-named one is another definition (s4-26:
# step 3's hips 901 mm, FreeSewing's at the iliac crest; step 0 read its ease on the tape's hips, 942.8 at the hip joints)


def _gap_round() -> float:
    from .chain_core import GAP
    return 2 * math.pi * GAP * 1000.0


def _cross(P: np.ndarray, q: np.ndarray, u: np.ndarray, closed: bool) -> list:
    """[(point, segment index, t)] where the line q + s u crosses polyline P."""
    n = np.array([-u[1], u[0]])
    d = (P - q) @ n
    out = []
    for i in range(len(P) if closed else len(P) - 1):
        j = (i + 1) % len(P)
        if (d[i] <= 0 < d[j]) or (d[j] <= 0 < d[i]):
            t = d[i] / (d[i] - d[j])
            out.append((P[i] + t * (P[j] - P[i]), i, float(t)))
    return out


def _share(E: np.ndarray, i: int, t: float) -> float:
    L = np.r_[0, np.cumsum(np.linalg.norm(np.diff(E, axis=0), axis=1))]
    return float((L[i] + t * (L[i + 1] - L[i])) / (L[-1] or 1.0))


def _at_share(E: np.ndarray, f: float) -> np.ndarray:
    L = np.r_[0, np.cumsum(np.linalg.norm(np.diff(E, axis=0), axis=1))]
    return np.array([np.interp(f * L[-1], L, E[:, k]) for k in range(2)])


def one_underarm(B: dict, lines: dict, under: list, holes: dict) -> None:
    """Pieces lowered to the underarm, sewn to each other by a seam running down from their armholes' ends, are read
    at ONE underarm: the deeper of the two, measured along the seam from its top (as sewn: points that far down meet;
    flat drops differ where the two pieces' grains meet at an angle), on both (F5b). Read per piece, each at its own
    armhole's lowest point, s4-29's front was read at its spiked corner 19.5 mm above the side body's underarm, and a
    seam moved toward the front raised the front's corner and its reading (8 mm), so a move that kept every level's
    width read the chest 19 mm looser."""
    pcs = B["pieces"]
    lv = {p: float(lines[p][0][1]) for p in under if p in lines}
    ends = {p: [x for a in holes.get(p, []) for x in _edge(pcs, p, a)[[0, -1]]] for p in lv}

    def down(E):  # (the seam from its top end down, with its arc lengths)
        E = E if E[-1, 1] >= E[0, 1] else E[::-1]
        E = E[::-1]
        return E, np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(E, axis=0), axis=1))])
    pairs = []
    for pa, ea, pb, eb in _seam_pairs(B):
        if pa in lv and pb in lv and pa < pb:
            (E, LE), (F, LF) = down(_edge(pcs, pa, ea)), down(_edge(pcs, pb, eb))
            if (any(np.linalg.norm(E[0] - x) < 1e-6 for x in ends[pa]) and any(np.linalg.norm(F[0] - x) < 1e-6
                                                                               for x in ends[pb])):
                pairs.append(((pa, E, LE), (pb, F, LF)))

    def arc_at(E, LE, y):  # (arc from the top where the level y first crosses the seam; None: it doesn't)
        c = _cross(E, np.array([0.0, y]), np.array([1.0, 0.0]), closed=False)
        return None if not c else LE[c[0][1]] + c[0][2] * (LE[c[0][1] + 1] - LE[c[0][1]])
    for _ in range(len(lv)):
        moved = False
        for sides in pairs:
            arcs = [arc_at(E, LE, lv[p]) for p, E, LE in sides]
            if None in arcs:
                continue
            for (p, E, LE), a in zip(sides, arcs):
                if max(arcs) > a + 1e-7:
                    lv[p], moved = float(np.interp(max(arcs), LE, E[:, 1])), True
        if not moved:
            break
    for p, y in lv.items():
        lines[p] = (np.array([0.0, y]), lines[p][1])


def width(P: np.ndarray, q: np.ndarray, u: np.ndarray) -> tuple[float, float, float]:
    """(inside length, lowest s, highest s) of outline P along the line q + s u (even-odd: gaps out)."""
    s = sorted(float((x[0] - q) @ u) for x in _cross(P, q, u, closed=True))
    if len(s) < 2:
        return 0.0, 0.0, 0.0
    return float(sum(b - a for a, b in zip(s[0::2], s[1::2]))), s[0], s[-1]


def drop(path: np.ndarray, loop: np.ndarray) -> float | None:
    """Surface length along path from its top end to the loop's plane (None: the path doesn't reach it)."""
    c = loop.mean(0)
    n = np.linalg.svd(loop - c)[2][-1]
    P = path if (path[0, 2] - abs(path[0, 0])) >= (path[-1, 2] - abs(path[-1, 0])) else path[::-1]
    d = (P - c) @ n
    s = 0.0
    for i in range(len(P) - 1):
        seg = float(np.linalg.norm(P[i + 1] - P[i]))
        if d[i] == 0:
            return s
        if d[i] * d[i + 1] < 0:
            return s + seg * d[i] / (d[i] - d[i + 1])
        s += seg
    if d[-1] == 0:
        return s
    seg = P[-1] - P[-2]  # (a path meant to END at the girth (an hps-to-waist) stops a few mm short of its loop)
    k = float(seg @ n)
    t = -d[-1] / k if abs(k) > 1e-9 else np.inf
    return s + t * float(np.linalg.norm(seg)) if 0 < t * float(np.linalg.norm(seg)) <= REACH else None


def _seam_pairs(B: dict) -> list:
    """[(piece, arcs, other piece, other arcs)] of every seam whose each side lies on one piece (a chain of edges, in
    order, read as one line: a side seam drafted as hem>waist + waist>armpit), both ways (a piece sewn to itself too)."""
    from .draft_shape import _sides
    out = []
    for s in B.get("seams") or []:
        A, Bs = [[e.split(":", 1) for e in _sides(x)] for x in s[:2]]
        pa, pb = {e[0] for e in A}, {e[0] for e in Bs}
        if len(pa) == len(pb) == 1 and pa <= set(B["pieces"]) and pb <= set(B["pieces"]):
            ea, eb = tuple(e[1] for e in A), tuple(e[1] for e in Bs)
            out += [(A[0][0], ea, Bs[0][0], eb), (Bs[0][0], eb, A[0][0], ea)]
    return out


def _edge(pcs: dict, p: str, arcs) -> np.ndarray:
    """The outline points of piece p along arc "a>b", or along a chain of arcs joined end to end."""
    from . import pattern
    P = np.asarray(pcs[p]["P"], float)
    out = []
    for a in ([arcs] if isinstance(arcs, str) else arcs):
        Q = P[pattern.arc_indices(pcs[p], a)]
        if out and np.linalg.norm(out[-1][-1] - Q[0]) > np.linalg.norm(out[-1][-1] - Q[-1]):
            Q = Q[::-1]
        out.append(Q)
    return np.concatenate(out)


def _part(pc: dict) -> str:
    return str((pc.get("wrap") or {}).get("to", ""))


def place(B: dict, loop: np.ndarray, T: dict, decl: dict) -> tuple[dict, list, list]:
    """({piece: (q, u)} level lines, [pieces lowered to the underarm], [pieces with an own length tape there])."""
    from . import draft_tapes, pattern
    pcs = B["pieces"]
    edge = lambda p, a: _edge(pcs, p, a)
    holes = {}
    for pa, ea, pb, eb in _seam_pairs(B):
        if _part(pcs[pa]) != _part(pcs[pb]):
            holes.setdefault(pa, []).append(ea)
    for s in B.get("seams") or []:  # (a cap sewn to an armhole chain: several edges on the other side)
        from .draft_shape import _sides
        A, Bs = _sides(s[0]), _sides(s[1])
        for X, Y in ((A, Bs), (Bs, A)):
            for e in X:
                p, a = e.split(":", 1)
                if p in pcs and any(y.split(":", 1)[0] in pcs and _part(pcs[y.split(":", 1)[0]]) != _part(pcs[p])
                                    for y in Y):
                    holes.setdefault(p, []).append(a)
    lines, under, own = {}, [], []
    for p, pc in pcs.items():
        best = None
        for n in draft_tapes.names_of(decl, p):
            if (T.get(n) or {}).get("kind") != "path":
                continue
            path = np.asarray(T[n]["path"], float)
            d = drop(path, loop)
            hi = path[0] if (path[0, 2] - abs(path[0, 0])) >= (path[-1, 2] - abs(path[-1, 0])) else path[-1]
            score = (abs(hi[0]) >= CENTRE, hi[2] - abs(hi[0]))  # (a side-neck top first: the flat's own top)
            if d is not None and (best is None or score > best[0]):
                best = (score, d)
        if best is None:
            continue
        P = np.asarray(pc["P"], float)
        if best[0][0]:
            y = float(P[:, 1].max()) - best[1]
        else:  # (a centre-line tape: from the top of the piece's edge nearest the centre line)
            x0 = P[np.argmin(np.abs(P[:, 0])), 0]
            y = float(P[np.abs(P[:, 0] - x0) < CENTRE, 1].max()) - best[1]
        low = [float(edge(p, a)[:, 1].min()) for a in holes.get(p, [])]
        if low and y > min(low):
            y = min(low) - 1e-4
            under.append(p)
        lines[p] = (np.array([0.0, y]), np.array([1.0, 0.0]))
        own.append(p)
    one_underarm(B, lines, under, holes)
    pairs = _seam_pairs(B)
    for _ in range(len(pcs)):  # carry the level over seams to pieces with no length tape of their own there
        got = {}
        for pa, ea, pb, eb in pairs:
            if pa in lines and pb not in lines:
                E = edge(pa, ea)
                c = _cross(E, *lines[pa], closed=False)
                if c:
                    F, f = edge(pb, eb), _share(E, c[0][1], c[0][2])
                    if (E[-1, 1] - E[0, 1]) * (F[-1, 1] - F[0, 1]) < 0:
                        f = 1.0 - f  # (a seam declared one edge up, one down: C385)
                    got.setdefault(pb, []).append(_at_share(F, f))
        if not got:
            break
        for p, pts in got.items():
            a, b = pts[0], pts[-1]
            u = (b - a) / np.linalg.norm(b - a) if len(pts) > 1 and np.linalg.norm(b - a) > 1e-6 else np.array([1.0, 0])
            lines[p] = (a, u)
    return lines, under, own


def rings(B: dict, lines: dict, named: set | None = None) -> tuple[list, bool]:
    """([sets of pieces round the body], open): the level's links pruned to rings; with none, the open chain."""
    from . import pattern
    pcs = B["pieces"]
    edge = lambda p, a: _edge(pcs, p, a)
    crosses = lambda p, a: p in lines and bool(_cross(edge(p, a), *lines[p], closed=False))
    links, elinks = [], []
    for pa, ea, pb, eb in _seam_pairs(B):
        if crosses(pa, ea) and crosses(pb, eb):
            links.append((pa, pb))
            elinks.append((pa, pb, eb))  # (eb: the edge of pb it is sewn along)
    cedge = {}
    for c in B.get("closures") or []:
        for k in ("over", "under"):
            e = (c.get("edge") or {}).get(k)
            if c.get(k) and isinstance(e, str):
                cedge.setdefault(c[k], set()).add((e,))
    for c in B.get("closures") or []:
        o, un = c.get("over"), c.get("under")
        if o in lines and un in lines and o != un:
            links += [(o, un), (un, o)]
    from . import draft_vents  # (a vent's two sides lapped across its opening, as a closure's: draft_vents)
    links += draft_vents.links(B, crosses)
    deg =lambda alive: {p: sum(1 for a, b in links if a == p and b in alive) for p in alive}
    alive = {a for a, _ in links}
    while True:
        dg = deg(alive)
        drop_ = {p for p, k in dg.items() if k < 2}
        if not drop_:
            break
        alive -= drop_
    is_open = False
    if not alive:  # (no ring: open at a vent or an open front: the cloth across the level is one or more lines of
        # pieces; a dead end LYING ON a piece is pruned: one sewn along that piece's closure edge (a facing), or one
        # whose tapes don't name the girth, on a piece of 3+ links; a dead end that names it (a side panel at a vent) stays)
        on_edge = {(p, q) for p, q, ea in elinks if ea in cedge.get(q, set())}
        alive = {a for a, _ in links}
        while True:
            dg = deg(alive)
            lay = {p for p, k in dg.items() if k == 1 and any(a == p and b in alive and dg.get(b, 0) >= 3 and
                   ((p, b) in on_edge or p not in (named or {p})) for a, b in links)}
            if not lay:
                break
            alive -= lay
        is_open = bool(alive)
    comps, left = [], set(alive)
    while left:
        st, comp = [left.pop()], set()
        while st:
            p = st.pop()
            comp.add(p)
            for a, b in links:
                if a == p and b in left:
                    left.discard(b)
                    st.append(b)
        comps.append(comp)
    return comps, is_open


def laps(B: dict, ring: set, lines: dict) -> tuple[float, float, list]:
    """(lap m taken off, opening m: edges short of the centre line, [missing declarations]) of the closures in ring."""
    from . import pattern
    lap, gap, miss = 0.0, 0.0, []
    for c in B.get("closures") or []:
        o, un, E = c.get("over"), c.get("under"), c.get("edge") or {}
        if o not in ring or un not in ring or o == un:
            continue
        prs = c.get("pairs") or c.get("at") or []
        for p, k, arc in ((o, 0, E.get("over")), (un, 1, E.get("under"))):
            pc = B["pieces"][p]
            nm = [pr[k] for pr in prs if len(pr) > k]
            M = [np.asarray(pc["marks"][n], float)[:2] for n in nm if n in (pc.get("marks") or {})] + \
                [np.asarray(pc["P"][pc["names"][n]], float) for n in nm
                 if n not in (pc.get("marks") or {}) and n in (pc.get("names") or {})]
            if not M or not isinstance(arc, str):
                miss.append(f"closure {c.get('name', '?')!r} on {p}: " + ("no fastening marks (pairs / at) on it"
                            if not M else "no edge") + ": the centre line (and the lap) can't be found")
                continue
            q, u = lines[p]
            P = np.asarray(pc["P"], float)
            x = _cross(P[pattern.arc_indices(pc, arc)], q, u, closed=False)
            if not x:
                continue  # (the front edge doesn't reach this level: the piece's width already ends at its outline)
            M = np.asarray(M)
            if len(M) > 1:
                a, b = M[np.argmax(M[:, 1])], M[np.argmin(M[:, 1])]
                cl = _cross(np.array([a + 10 * (a - b), b - 10 * (a - b)]), q, u, closed=False)
                s_cf = float((cl[0][0] - q) @ u) if cl else float((M[0] - q) @ u)
            else:
                s_cf = float((M[0] - q) @ u)
            s_e = float((x[0][0] - q) @ u)
            _, lo, hi = width(P, q, u)
            ov = (s_e - s_cf) if abs(s_e - hi) < abs(s_e - lo) else (s_cf - s_e)
            lap += max(ov, 0.0)
            gap += max(-ov, 0.0)
    return lap, gap, miss


def like_with_like(g: str, reg: str, fe: dict | None, loop: np.ndarray, body: float, fails: list) -> tuple:
    """(loop, body mm, said) of girth g compared like with like: step 0's ease for it was read on ITS body girth at ITS
    level; where step 3's same-named girth is another definition (another body girth), the level is moved to step 0's
    (fe["level_z_m"]) and the body is step 0's, so the target is that definition's body + its ease. (None, ...) with a
    FAIL when step 0 doesn't record its level."""
    if not fe or fe.get("body_girth_mm") is None or abs(float(fe["body_girth_mm"]) - body) <= DEF_TOL * body:
        return loop, body, ""
    b0 = float(fe["body_girth_mm"])
    if fe.get("level_z_m") is None:
        fails.append(f"{g}: step 0 read its {reg} ease on a body girth of {b0:.0f} mm, step 3's {g} is {body:.0f}: two "
                     "definitions, and step 0's fit doesn't record its level: re-read step 0's fit (garment_plan read: "
                     "back to step 0) so the girth is checked where its ease was read")
        return None, body, ""
    z = float(fe["level_z_m"])
    said = (f" (step 0's {reg} definition, where its ease was read: {b0:.0f} mm at z {z:.3f}; step 3's {g} is "
            f"{body:.0f} at z {float(loop[:, 2].mean()):.3f}, another definition)")
    return loop + np.array([0.0, 0.0, z - float(loop[:, 2].mean())]), b0, said


def rows(B: dict, step3: dict | None, fit: dict | None, decl: dict | None = None) -> list:
    """Row `girths` (module docstring)."""
    from . import draft_tapes, draft_vents, tape_geom
    from .draft_body_lengths import _ease
    decl = decl or B.get("decl") or {}
    rid = {"id": "girths", "back_to": "4", "target": "every girth the pieces' tapes name: the pattern round = the body + "
           f"the plan's ease (within {TOL_MM:.0f} mm or {TOL_FRAC:.0%} of that ease); a closed level never under the "
           f"body + the cloth's gap ({_gap_round():.0f} mm round)"}
    T = tape_geom.tapes(step3)
    named = {}
    for p in B["pieces"]:
        for n in draft_tapes.names_of(decl, p):
            if (T.get(n) or {}).get("kind") == "loop":
                named.setdefault(n, set()).add(p)
    if not named:
        return [dict(rid, status="FAIL", value="no girth checked", why="no piece's tapes name a step-3 girth (a loop): "
                     "declare tapes.<piece> with the girths it was drafted on (chest, waist, biceps ...)",
                     fix="declarations tapes", back_to="4")]
    vals, fails, gmin = [], [], _gap_round()
    for g, decl_by in sorted(named.items(), key=lambda kv: -float(np.asarray(T[kv[0]]["loop"])[:, 2].mean())):
        loop = np.asarray(T[g]["loop"], float)
        body = float(T[g].get("mm") or 1000 * np.linalg.norm(np.diff(np.r_[loop, loop[:1]], axis=0), axis=1).sum())
        ease, reg = _ease(g, fit)
        loop, body, defn = like_with_like(g, reg, (fit or {}).get(reg) if reg else None, loop, body, fails)
        if loop is None:
            continue
        lines, under, own = place(B, loop, T, decl)
        comps, is_open = rings(B, lines, decl_by)
        if is_open and any(c & decl_by for c in comps):  # (open at a vent or the front: all the cloth across it)
            parts = {_part(B["pieces"][p]) for p in decl_by}  # (a sleeve crossing a torso girth's plane isn't in it)
            comps = [set().union(*[c for c in comps if {_part(B["pieces"][p]) for p in c} <= parts])]
        comps = [c for c in comps if c & decl_by]
        if not comps:
            fails.append(f"{g}: its level doesn't go round the body (placed on {', '.join(sorted(lines)) or 'no piece'}"
                         + ("" if own else f"; no length tape declared on {', '.join(sorted(decl_by))} reaches the "
                            f"{g} level: declare one running from the piece's top past it") + "): sew the ring's seams "
                         "across that level, or declare the front closure (over / under, edges, marks)")
            continue
        tgt, tol = body + ease, max(TOL_MM, TOL_FRAC * ease)
        seen = []
        for ring in sorted(comps, key=lambda c: sorted(c)):
            if not any(p in own for p in ring):
                fails.append(f"{g}: no length tape declared on {', '.join(sorted(ring))} reaches its level: declare "
                             f"tapes.<piece> with a length from its top past the {g}")
                continue
            w = {p: width(np.asarray(B["pieces"][p]["P"], float), *lines[p])[0] for p in sorted(ring)}
            lap, gap, miss = laps(B, ring, lines)
            for m in miss:
                fails.append(f"{g}: {m}")
            vlap = draft_vents.laps(B, ring, lines)
            pat = 1000 * (sum(w.values()) - lap - vlap)
            key = round(pat)
            if key in seen:
                continue  # (the other side's ring, alike)
            seen.append(key)
            opening = gap > 1e-3 or is_open
            spare = pat - tgt
            vals.append(f"{g}: pattern {pat:.0f} mm, body {body:.0f}{defn}, planned ease "
                        + (f"{ease:.0f} ({reg})" if reg else f"none stated (the cloth's minimum {gmin:.0f})")
                        + (f", spare {spare:+.0f} vs plan" if reg else f", spare {pat - body - gmin:+.0f} vs minimum")
                        + f" [{', '.join(f'{p} {1000 * v:.0f}' for p, v in w.items())}"
                        + (f"; lap -{1000 * lap:.0f}" if lap else "")
                        + (f"; vents' overlap -{1000 * vlap:.0f}" if vlap else "") + "]"
                        + (f"; OPEN at the front (edges {1000 * gap:.0f} mm short of the centre line)" if gap > 1e-3 else
                           "; OPEN: no closure or seam closes it there (a vent, an open front)" if is_open else "")
                        + ("; taken at the underarm" if under and any(p in ring for p in under) else ""))
            undecl = sorted(p for p in ring if p not in decl_by)
            if undecl:
                fails.append(f"{g}: {', '.join(undecl)} lie(s) in the {g} ring but its tapes don't name {g!r}: add "
                             f"{g!r} to tapes.<piece> (a pair by its base name)")
            half = ", ".join(sorted({p.removesuffix('.L').removesuffix('.R') for p in ring}))
            if not opening and pat < body + gmin:
                fails.append(f"{g}: {pat:.0f} mm round is under the body {body:.0f} + the cloth's gap {gmin:.0f}: it "
                             f"can't be worn: widen {half} at the {g} line by {max(tgt, body + gmin) - pat:.0f} mm in "
                             "total (back to step 4)")
            elif reg and abs(spare) > tol:
                fails.append(f"{g}: {pat:.0f} mm round against body {body:.0f} + the plan's {reg} ease {ease:.0f} = "
                             f"{tgt:.0f}: {abs(spare):.0f} mm too {'tight' if spare < 0 else 'loose'} (tolerance "
                             f"{tol:.0f}): {'widen' if spare < 0 else 'take in'} {half} at the {g} line by "
                             f"{abs(spare):.0f} mm in total (back to step 4; to step 0 if the plan's ease is what's wrong)")
    return [dict(rid, status="FAIL" if fails else "PASS", value="; ".join(vals) or "no girth measured",
                 why="; ".join(fails), fix="widen or take in the pieces at the named line by the named total (spread "
                 "over its seams), or declare what the row says is missing" if fails else "")]
