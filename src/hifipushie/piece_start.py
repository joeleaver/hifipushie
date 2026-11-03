"""PIECE START (F4, C312-C313): every piece starts where its OWN measurements were taken.

Joe (2026-11-02): "I don't know why we need leg tubes, shouldn't they just build like any other garment pattern?"
Before the build solves lengths each piece needs a start near where it is worn. It was a list of body parts by role
(torso panels round the torso, sleeves round the arm's axis); nothing else could start anywhere. Now the start comes
from the measurements the piece was drafted from:

- STEP 4 keeps each piece's measurement list (`piece_measurements`): the body names on step 1's seams its edges are
  on, plus its draft part's own `measurements` (FreeSewing's part config, pattern_parts). A pair's two pieces share it.
- STEP 3 keeps where each was taken (tape_geom: a girth's loop, a length's path).
- TUBE: soft pieces of one side sewn to each other (or one sewn to itself) whose girth loops lie on that side of the
  body (a loop that doesn't hold the centre line): the tube starts round those loops, along the line through their
  centres, run on to the ends of the length paths it names (`MeasuredAxis`, the same interface as the old axis).
  Pieces of the other side take the loops mirrored. Nothing names a limb.
- PANEL: an open piece starts over the region between its tapes: its top at the highest top of the length paths it
  names (a waist-to-knee panel at the waist, an hps-to-waist one at the hps); `panel_dz`.
- FALLBACK: a piece that names no measurement with geometry starts as before (the torso's rings, the limb's joint
  axis), said in the build's reads (`reads["starts"]`) and so in its answer.

`attach(M, step1, step3, step4)`: M["starts"] = {"pieces": {piece: [names]}, "tapes": {name: {kind, pts}}}.
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
    out = {}
    for p in pieces:
        base = p[:-2] if p.endswith((".L", ".R")) else p
        out[p] = sorted(own.get(p, own.get(base, set())))
    return out


def attach(M: dict, step3: dict, step4: dict) -> dict:
    """M["starts"] from the record (lists, so the pickled build keeps them); {} pieces when step 4 has no list."""
    from . import tape_geom
    T = tape_geom.tapes(step3)
    M["starts"] = {"pieces": dict((step4 or {}).get("piece_measurements") or {}),
                   "tapes": {k: {"kind": v["kind"], "pts": v[v["kind"]].tolist()} for k, v in T.items()}}
    return M["starts"]


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


def tube_groups(net, soft: list, sewn: dict, self_sewn: set) -> dict:
    """{piece: [its tube's pieces]} for pieces whose girth loops lie on their own side: connected through seams with
    pieces of the same side that do too (a front + back leg, a top + under sleeve) or one sewn to itself."""
    from .chain_garment import hand_of
    ok = []
    for p in soft:
        s = hand_of(p)
        loops, _ = _tapes_of(net, p)
        if s != 0 and loops and any(sided(P, s) for _, P in loops):
            ok.append(p)
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
            todo += [r for r in sewn[q] if r in ok and r not in seen and hand_of(r) == hand_of(p)]
        if len(grp) > 1 or grp[0] in self_sewn:
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
