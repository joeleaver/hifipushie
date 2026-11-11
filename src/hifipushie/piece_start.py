"""PIECE START (F4, C312-C313): every piece starts where its OWN measurements were taken.

Joe (2026-11-02): "I don't know why we need leg tubes, shouldn't they just build like any other garment pattern?"
Before the build solves lengths each piece needs a start near where it is worn. It was a list of body parts by role
(torso panels round the torso, sleeves round the arm's axis); nothing else could start anywhere. Now the start comes
from the measurements the piece was drafted from:

- STEP 4 keeps each piece's measurement list (`piece_measurements`): the body names on step 1's seams its edges are
  on, plus its draft part's own `measurements` (FreeSewing's part config, pattern_parts), plus the tapes its
  declarations name (`tapes`, draft_tapes.py: P1; the flat gate refuses a piece with none). A pair's two pieces share it.
- STEP 3 keeps where each was taken (tape_geom: a girth's loop, a length's path).
- TUBE: soft pieces of one side whose seams close them round (one sewn to itself, or two joined by two separate
  seams) whose girth loops lie on that side of the body (a loop that doesn't hold the centre line) and one of whose
  length paths runs along those loops (an armhole's girth named by a body panel is not its tube): it starts round them, along the line through their
  centres, run on to the ends of the length paths it names (`MeasuredAxis`, the same interface as the old axis).
  Pieces of the other side take the loops mirrored. Nothing names a limb.
- PANEL: an open piece starts over the region between its tapes: its top at the highest top of the length paths it
  names (a waist-to-knee panel at the waist, an hps-to-waist one at the hps); `panel_dz`.
- NO TAPE (P2, docs/proposals/place_where_measured.md): a built piece (every piece but plies and floating layers, which
  follow their host) naming no step-3 tape with geometry is REFUSED by name before anything is placed (`untaped`, called
  first in GarmentBuild.run): "step 4 names no tape for <piece>". Nothing is guessed. A piece WITH tapes but none of the
  kind its start reads (a tube with no girth on its side, a panel with no length spanning it) still starts on the torso's
  rings / the limb's joint axis, said by name in reads["starts"] (P3 retires those with the shirt and hussar controls).
- A STIFF PIECE'S EDGE ON ITS TAPE (P2, `lay_on_tape`): an edge step 4 names on a tape (edge_tapes) is laid along that
  tape's line by arc length from the end they share: a centre piece (a collar) from its middle (CB) outward, the half on
  the worn +X side along the tape, the other half along it mirrored (x -> -x); a sided piece from its edge's end nearest
  the centre line in its flat (flats run from the centre line), a .R piece on the mirrored tape. A tape shorter than the
  edge is refused (back to step 3: measure it on). The tape lies on the skin: the laid line is lifted to GAP off it.

`attach(M, step3, step4)`: M["starts"] = {"pieces": {piece: [names]}, "tapes": {name: {kind, pts}},
"edges": {piece: {edge: {"tape", "arc"}}}}.
"""
from __future__ import annotations

import numpy as np

SIDED_TOL = 0.01  # m: a loop lies on one side when its nearest point is this far off the centre line (x = 0)
EXTEND = 0.15  # m: the axis runs on past its ends so a piece's far rows never clamp


def _unit(v):
    v = np.asarray(v, float)
    n = np.linalg.norm(v, axis=-1, keepdims=True)
    return v / np.where(n > 1e-12, n, 1.0)


# ---------------------------------------------------------------- step 4: the measurement list of every piece
def piece_measurements(step1: dict, decl: dict, parts_cfg: dict, pieces: list) -> dict:
    """{piece (as cut: n, n.L, n.R): sorted body measurement names} from step 1's seams and the draft parts' own lists."""
    own: dict = {}
    for s in (step1 or {}).get("seams") or []:
        names = ((s.get("length") or {}).get("body") or []) if isinstance(s.get("length"), dict) else []
        for e in (s.get("a"), s.get("b")):
            if isinstance(e, str) and ":" in e:
                own.setdefault(e.split(":")[0], set()).update(names)
    for n, d in ((decl or {}).get("pieces") or {}).items():
        part = (d or {}).get("part")
        pc = (parts_cfg or {}).get(part) or {}
        own.setdefault(n, set()).update(pc.get("measurements") or [])
    from . import draft_tapes  # (P1: the tapes step 4 declares each piece / edge drafted on)
    out = {}
    for p in pieces:
        base = p[:-2] if p.endswith((".L", ".R")) else p
        out[p] = sorted(own.get(p, own.get(base, set())) | set(draft_tapes.names_of(decl or {}, p)))
    return out


def attach(M: dict, step3: dict, step4: dict) -> dict:
    """M["starts"] from the record (lists, so the pickled build keeps them); {} pieces when step 4 has no list."""
    from . import tape_geom
    T = tape_geom.tapes(step3)
    M["starts"] = {"pieces": dict((step4 or {}).get("piece_measurements") or {}),
                   "tapes": {k: {"kind": v["kind"], "pts": v[v["kind"]].tolist()} for k, v in T.items()},
                   "edges": dict((step4 or {}).get("edge_tapes") or {})}
    return M["starts"]


# ---------------------------------------------------------------- P2: no tape, refused; a stiff edge on its tape
def untaped(b) -> list:
    """Built pieces (not plies / floating layers: they follow their host) that name no step-3 tape with geometry."""
    st = b.net.M.get("starts") or {}
    names, T = st.get("pieces") or {}, st.get("tapes") or {}
    carried = set(b.roles.carried)
    return [p for p in b.net.names if p not in carried and not any(n in T for n in names.get(p) or [])]


def refuse_untaped(b):
    from .chain_core import ChainRefused
    bad = untaped(b)
    if bad:
        raise ChainRefused(f"step 4 names no tape for {', '.join(bad)}: back to step 4, declare tapes (draft_pattern "
                           "declarations tapes {piece: [the step-3 tapes it was drafted on] | {edge: tape}}, a stiff piece's "
                           "edge sewn to the body cloth on the tape it lies along); step 5 places every piece where the body "
                           "was measured for it, never from a rule")


CENTRE_TOL = 0.005  # m: a tape's end this near x = 0 is on the centre line


def _resample(P, step=0.002):
    s = np.r_[0, np.cumsum(np.linalg.norm(np.diff(P, axis=0), axis=1))]
    q = np.arange(0, s[-1] + 1e-12, step)
    return np.column_stack([np.interp(q, s, P[:, k]) for k in range(3)])


def from_centre(kind: str, P) -> np.ndarray:
    """The tape as a line from its end on the centre line, running to the worn +X side: a path from the end nearer
    x = 0 (both on it: the back one; mirrored when it lies on -X); a loop from where it crosses x = 0 at the back, the way it goes to +X."""
    P = np.asarray(P, float)
    if kind == "loop":
        Q = _resample(np.r_[P, P[:1]] if np.linalg.norm(P[0] - P[-1]) > 1e-9 else P)[:-1]
        near = np.abs(Q[:, 0]) <= max(np.abs(Q[:, 0]).min() * 1.5, 0.003)
        k = int(np.flatnonzero(near)[np.argmax(Q[near, 1])])  # (the back's crossing: largest y)
        Q = np.roll(Q, -k, axis=0)
        if Q[1:len(Q) // 4, 0].mean() < 0:
            Q = np.r_[Q[:1], Q[1:][::-1]]
        return np.r_[Q, Q[:1]]
    ends_c = np.abs(P[[0, -1], 0]) < CENTRE_TOL
    if (ends_c.all() and P[-1, 1] > P[0, 1]) or (not ends_c.all() and abs(P[-1, 0]) < abs(P[0, 0])):
        P = P[::-1]  # (from the end on the centre line; both on it, CB to CF round the neck: from the back one)
    if P[:, 0].mean() < 0:
        P = P * [-1, 1, 1]
    return P


def _lift(contact, P, gap, passes=4):
    """P moved out along the body's normal until every point is gap off it (a few passes: the surface curves)."""
    for _ in range(passes):
        sd, nrm = contact.query(P)
        if (sd >= gap - 1e-5).all():
            break
        P = P + nrm * np.maximum(gap - sd, 0.0)[:, None]
    return P


def _at(Q, d):
    s = np.r_[0, np.cumsum(np.linalg.norm(np.diff(Q, axis=0), axis=1))]
    return np.column_stack([np.interp(d, s, Q[:, k]) for k in range(3)]), float(s[-1])


def lay_on_tape(b, piece: str, chain, mid: int | None = None, su: float = 1.0):
    """(P2) The positions of `chain` (a stiff piece's ordered edge vertices sewn to the body cloth) laid on the tape step 4
    names for that edge (module doc), GAP off the body, and what it read. mid: the chain index at the centre line (a
    centre piece); su: +1 when the chain's later indices from mid run to worn +X. Raises ChainRefused by name."""
    from .chain_core import GAP, ChainRefused, hand_of
    net = b.net
    st = net.M.get("starts") or {}
    em = (st.get("edges") or {}).get(piece) or {}
    if not em and hand_of(piece):
        em = (st.get("edges") or {}).get(piece[:-2]) or {}
    names = sorted({e.get("tape") for e in em.values() if isinstance(e, dict) and e.get("tape")})
    T = st.get("tapes") or {}
    if not names:
        raise ChainRefused(f"step 4 names no tape for {piece}'s edge sewn to the body cloth: back to step 4, declare "
                           f"tapes.{piece} {{edge: tape}} (the step-3 tape that edge lies along); a stiff piece is laid "
                           "on its tape, never on a ring")
    if len(names) > 1:
        raise ChainRefused(f"{piece}: its edge sewn to the body cloth names {len(names)} tapes ({', '.join(names)}); it is "
                           "laid along one line: back to step 3, take one tape along the whole seam line (body_tape "
                           "length from / via / to over the surface), and name it for each of those edges in step 4")
    n = names[0]
    if n not in T:
        raise ChainRefused(f"{piece}: tape {n!r} has no line in step 3: back to step 3, retake it with body_tape")
    Q = from_centre(T[n]["kind"], T[n]["pts"])
    chain = np.asarray(chain, np.int64)
    s = np.r_[0, np.cumsum(np.linalg.norm(np.diff(net.uv[chain], axis=0), axis=1))]
    if mid is not None:  # (a centre piece: from its middle outward, the -X half on the mirrored tape)
        d = (s - s[mid]) * su
    else:  # (a sided piece from its centre-line end; a .R piece laid as its .L, then mirrored)
        d = s if abs(net.uv[chain[0], 0]) <= abs(net.uv[chain[-1], 0]) else s[-1] - s
        d = d * (-1.0 if hand_of(piece) < 0 else 1.0)
    P, L = _at(Q, np.abs(d))
    if np.abs(d).max() > L + 0.002:  # (d < 0: the -X side, laid on +X then mirrored)
        raise ChainRefused(f"{piece}: tape {n!r} runs {L * 1e3:.0f} mm from the centre line, the edge laid on it needs "
                           f"{np.abs(d).max() * 1e3:.0f} mm: back to step 3, measure {n!r} on to where that edge ends")
    P = _lift(b.body.contact, P, GAP)  # (the tape lies on the skin; the cloth GAP off it: on the +X side, then mirrored)
    neg = d < 0
    P[neg] = P[neg] * [-1, 1, 1]
    P = _lift(b.body.contact, P, GAP, 1)  # (a body's mesh is never exactly mirror symmetric: what that leaves under GAP)
    rd = {"tape": n, "kind": T[n]["kind"], "edge_mm": round(float(s[-1] * 1e3), 1), "tape_mm": round(L * 1e3, 1),
          "laid_from": "the centre line, both ways (the -X half mirrored)" if mid is not None else "its centre-line end"}
    b.reads.setdefault("starts", {})[piece] = f"edge laid on its tape {n} ({rd['edge_mm']} mm of {rd['tape_mm']} mm)"
    return P, rd


def _tapes_of(net, piece: str) -> tuple[list, list]:
    """(girth loops, length paths) the piece names, as arrays, mirrored to its side when it is a .R piece."""
    st = net.M.get("starts") or {}
    names = (st.get("pieces") or {}).get(piece) or []
    T = st.get("tapes") or {}
    side = -1.0 if piece.endswith(".R") else 1.0
    loops, paths = [], []
    for n in names:
        t = T.get(n)
        if not t:
            continue
        P = np.asarray(t["pts"], float)
        if side < 0:
            P = P * [-1, 1, 1]
        (loops if t["kind"] == "loop" else paths).append((n, P))
    return loops, paths


def sided(P: np.ndarray, side: float) -> bool:
    """A loop round a part of the body on one side: all of it off the centre line on that side."""
    return bool(side != 0 and (np.asarray(P)[:, 0] * side).min() > SIDED_TOL)


ALONG = 1.5  # a length path runs along a tube when its median distance to the loops' line is under this x their radius


def _seams_between(net, a: str, b: str) -> int:
    """How many separate seams join piece a to piece b: runs of a's sewn vertices joined by a's own mesh edges."""
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components
    pa, pb = net.pid(a), net.pid(b)
    va = np.unique([int(x) if net.piece[x] == pa else int(y) for x, y in net.sew
                    if {int(net.piece[x]), int(net.piece[y])} == {pa, pb}])
    if not len(va):
        return 0
    idx = {v: k for k, v in enumerate(va.tolist())}
    E = np.r_[net.F[:, [0, 1]], net.F[:, [1, 2]], net.F[:, [2, 0]]]
    E = E[np.isin(E[:, 0], va) & np.isin(E[:, 1], va)]
    i_ = [idx[int(x)] for x in E[:, 0]]
    j_ = [idx[int(x)] for x in E[:, 1]]
    G = coo_matrix((np.ones(len(i_)), (i_, j_)), shape=(len(va), len(va)))
    return int(connected_components(G, directed=False)[0])


def _along(loops: list, paths: list) -> bool:
    """Some length path runs along the line through the loops (a tube's own length), not off across the body."""
    if not paths:
        return True
    C, k_ = np.unique(np.round([P.mean(0) for P in loops], 4), axis=0, return_index=True)  # (a loop two pieces name: once)
    loops = [loops[k] for k in sorted(k_)]
    C = np.array([P.mean(0) for P in loops])
    r = max(float(np.linalg.norm(P - P.mean(0), axis=1).mean()) for P in loops)
    u = _unit(C[-1] - C[0]) if len(C) > 1 else _unit(np.linalg.svd(loops[0] - C[0])[2][2])  # (one loop: its normal)
    tc = (C - C[0]) @ u
    for _, P in paths:  # (over the loops' own span: a path that only meets their line inside the body runs elsewhere)
        sp = np.r_[0, np.cumsum(np.linalg.norm(np.diff(P, axis=0), axis=1))]
        q = np.arange(0, sp[-1] + 1e-9, 0.01)
        P = np.column_stack([np.interp(q, sp, P[:, k]) for k in range(3)])  # (every cm along it)
        t = (P - C[0]) @ u
        m = (t >= tc.min() - r) & (t <= tc.max() + r)
        d = np.linalg.norm(np.cross(P - C[0], u), axis=1)
        if m.sum() >= 2 and float(np.median(d[m])) < ALONG * r:
            return True
    return False


def tube_groups(net, soft: list, sewn: dict, self_sewn: set) -> dict:
    """{piece: [its tube's pieces]}: soft pieces of one side whose seams close them round (one sewn to itself, or two
    joined by two separate seams: a front + back leg's side and inseam, a top + under sleeve) and whose girth loops lie
    on their side with a length path of theirs running along them."""
    from .chain_garment import hand_of
    tp = {p: _tapes_of(net, p) for p in soft}
    ok = [p for p in soft if hand_of(p) != 0 and any(sided(P, hand_of(p)) for _, P in tp[p][0])]
    out, seen = {}, set()
    for p in ok:
        if p in seen:
            continue
        grp, todo = [], [p]
        while todo:
            q = todo.pop()
            if q in seen:
                continue
            seen.add(q)
            grp.append(q)
            todo += [r for r in sewn[q] if r in ok and r not in seen and hand_of(r) == hand_of(p)
                     and _seams_between(net, q, r) >= 2]
        if not (len(grp) > 1 or grp[0] in self_sewn):
            continue
        s = hand_of(p)
        loops = [P for q in grp for _, P in tp[q][0] if sided(P, s)]
        if not _along(loops, [x for q in grp for x in tp[q][1]]):
            continue
        grp = sorted(grp, key=lambda q: -float(np.ptp(net.uv[net.verts(q), 1])))
        for q in grp:
            out[q] = grp
    return out


# ---------------------------------------------------------------- the build: a tube's axis from its loops
class MeasuredAxis:
    """The line through a tube's girth loops' centres (the end nearest the body's centre line first), run on along the
    tube's length paths to their far ends. at(s) -> (point, outer side, front side, direction) like the joint axis."""

    def __init__(self, loops: list, paths: list, side: float):
        from scipy.ndimage import gaussian_filter1d
        C = np.array([P[:-1].mean(0) if np.allclose(P[0], P[-1]) else P.mean(0) for P in loops])
        if len(C) == 1:  # (one loop: the line along its section's normal, the way its paths run)
            n = _unit(np.cross(loops[0][1] - loops[0][0], loops[0][len(loops[0]) // 3] - loops[0][0]))
            C = np.array([C[0] + n * 0.05, C[0] - n * 0.05])
        c0 = C.mean(0)
        u = _unit(np.linalg.svd(C - c0)[2][0])
        t = (C - c0) @ u
        C = C[np.argsort(t)]
        if abs(C[-1, 0]) < abs(C[0, 0]):  # (the end nearest the centre line first: where the tube joins the body)
            C = C[::-1]
        d0, d1 = _unit(C[0] - C[1]), _unit(C[-1] - C[-2])
        top = bot = 0.0
        for _, P in paths:  # (the length paths: how far past the loops the tube runs, each way)
            top = max(top, float(((P - C[0]) @ d0).max()))
            bot = max(bot, float(((P - C[-1]) @ d1).max()))
        Q = np.r_[[C[0] + d0 * (top + EXTEND)], [C[0] + d0 * top] if top > 0.01 else np.zeros((0, 3)), C,
                  [C[-1] + d1 * bot] if bot > 0.01 else np.zeros((0, 3)), [C[-1] + d1 * (bot + EXTEND)]]
        s0 = np.r_[0, np.cumsum(np.linalg.norm(np.diff(Q, axis=0), axis=1))]
        q = np.arange(0, s0[-1], 0.002)
        A = np.column_stack([np.interp(q, s0, Q[:, k]) for k in range(3)])
        A = gaussian_filter1d(A, 10, axis=0, mode="nearest")
        s = np.r_[0, np.cumsum(np.linalg.norm(np.diff(A, axis=0), axis=1))]
        self.s = s - s[int(np.argmin(np.linalg.norm(A - (C[0] + d0 * top), axis=1)))]  # (0 at the tube's top end)
        self.C = A
        self.d = _unit(np.gradient(A, axis=0))
        self.o = side * _unit(np.cross(self.d, [0, 1.0, 0]))
        f = _unit(np.cross(self.o, self.d))
        self.f = f * np.sign(-(f[:, 1]).mean())
        self.top = C[0] + d0 * top

    def at(self, s):
        s = np.asarray(s, float)
        g = lambda A: np.column_stack([np.interp(s, self.s, A[:, k]) for k in range(3)])
        return g(self.C), _unit(g(self.o)), _unit(g(self.f)), _unit(g(self.d))


def axis_for(b, t: str):
    """The axis a tube starts round: its measured loops (MeasuredAxis), else the joint axis as the named FALLBACK."""
    from .chain_garment import LimbAxis, hand_of
    side = hand_of(t)
    grp = (b.roles.tube_groups or {}).get(t) or [t]
    key = (side, tuple(sorted(grp)))
    axes = b.__dict__.setdefault("axes", {})
    if key in axes:
        return axes[key]
    loops, paths = [], []
    for p in grp:
        lp, pp = _tapes_of(b.net, p)
        loops += [x for x in lp if sided(x[1], side)]
        paths += pp
    seen = set()
    loops = [x for x in loops if not (x[0] in seen or seen.add(x[0]))]
    pseen = set()
    paths = [x for x in paths if not (x[0] in pseen or pseen.add(x[0]))]
    rd = b.reads.setdefault("starts", {})
    if loops:
        ax = MeasuredAxis([P for _, P in loops], paths, side)
        rd[",".join(grp)] = (f"tube round its own measurements: loops {', '.join(n for n, _ in loops)}"
                             + (f", along {', '.join(n for n, _ in paths)}" if paths else ""))
    else:
        ax = LimbAxis(b.body, side)
        rd[",".join(grp)] = "FALLBACK: names no girth measured on its side; started round the joint axis"
    axes[key] = ax
    return ax


PANEL_MATCH = 0.2  # a length path spans the panel when its height is within this fraction of the panel's flat height


def panel_dz(b, p: str) -> float:
    """How far a panel's flat (hung from the hps) moves so its top sits at the top of the length path that spans it
    (its height within PANEL_MATCH of the panel's: a waist-to-knee skirt panel at the waist); none: hung from the hps."""
    _, paths = _tapes_of(b.net, p)
    rd = b.reads.setdefault("starts", {})
    yv = b.net.uv[b.net.verts(p), 1]
    H = float(np.ptp(yv))
    span = [(n, P) for n, P in paths if abs(float(np.ptp(P[:, 2])) - H) <= PANEL_MATCH * H]
    if not span:
        rd.setdefault(p, "FALLBACK: names no length path spanning it" + (f" (has {', '.join(n for n, _ in paths)})"
                      if paths else "") + "; hung from the hps round the torso")
        return 0.0
    n, P = max(span, key=lambda x: float(np.ptp(x[1][:, 2])))
    hz = float(b.body.p("hps.L")[2])
    top = float(P[:, 2].max())
    dz = top - (hz + float(yv.max()))
    rd[p] = f"panel between its tapes: top at {top:.3f} m (the top of {n}), {dz * 1e3:+.0f} mm from hung at the hps"
    return dz


TURN_STEPS = 72  # (5 deg: a tube's turn read to well under a seam's own spacing at a thigh's radius)


def turn_to_seams(b, X):
    """(F5 C316) A tube sewn to a stiff part built before it (a waistband, a cuff) turns about its loops' line until its
    seam faces where it is sewn: the turn of least median distance from each sewn point to its place. The phase rule
    (_tube_points / tube_group_points: the longest piece's middle on the outer side) is a sleeve's; this reads the
    garment's own seam instead. Groups with nothing sewn to a built part keep their phase. Said in reads["starts"]."""
    from .chain_garment import hand_of
    net = b.net
    stiff = b._stiff_mask()
    held = np.zeros(net.n, bool)
    held[net.root[stiff]] = True
    X = np.array(X, float)
    done = set()
    for t in b.roles.tubes:
        grp = tuple(sorted((b.roles.tube_groups or {}).get(t) or [t]))
        if grp in done:
            continue
        done.add(grp)
        side = hand_of(t)
        loops = [P for p in grp for _, P in _tapes_of(net, p)[0] if sided(P, side)]
        gv = np.concatenate([net.verts(p) for p in grp])
        sv = gv[held[net.root[gv]] & ~stiff[gv]]
        if len(loops) < 2 or len(sv) < 3:
            continue
        C = np.array([np.asarray(P).mean(0) for P in loops])
        c0 = C.mean(0)
        ax = _unit(np.linalg.svd(C - c0)[2][0])
        tgt = b.X[net.root[sv]]

        def turned(P, a):
            d = P - c0
            return c0 + d * np.cos(a) + np.cross(ax, d) * np.sin(a) + np.outer(d @ ax, ax) * (1 - np.cos(a))

        cost = [float(np.median(np.linalg.norm(turned(X[sv], a) - tgt, axis=1)))
                for a in np.linspace(0, 2 * np.pi, TURN_STEPS, endpoint=False)]
        k = int(np.argmin(cost))
        a = 2 * np.pi * k / TURN_STEPS
        if k:
            X[gv] = turned(X[gv], a)
        # then the cloth between the seam and the nearest loop it was measured at eases onto the built part: each point
        # moved by its nearest sewn point's offset (on its own piece's flat), all of it at the seam, none at that loop
        from scipy.spatial import cKDTree
        ts = float(((tgt - c0) @ ax).mean())
        tl = (C - c0) @ ax
        t_loop = float(tl[np.argmin(np.abs(tl - ts))])
        span = ts - t_loop
        if abs(span) > 1e-3:
            for p in grp:
                v = net.verts(p)
                sp = v[np.isin(v, sv)]
                if not len(sp):
                    continue
                off = b.X[net.root[sp]] - X[sp]
                j = cKDTree(net.uv[sp]).query(net.uv[v])[1]
                w = np.clip(((X[v] - c0) @ ax - t_loop) / span, 0, 1)
                w = w * w * (3 - 2 * w)
                X[v] = X[v] + off[j] * w[:, None]
        b.reads.setdefault("starts", {})[f"{','.join(grp)} turn"] = (
            f"turned {np.degrees(a):.0f} deg to face its seam to the built part (median {cost[0] * 1e3:.0f} -> "
            f"{cost[k] * 1e3:.0f} mm), eased onto it down to its nearest loop")
    return X
