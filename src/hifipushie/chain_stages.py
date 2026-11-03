"""BUILD STAGE GATES (F5, C314-C316): the chain build gates each of its stages and stops at the first failure, cheapest first.

Joe (2026-11-03, the F4 trousers: every soft piece crumpled, the right leg's front never wrapped): "I think maybe we're
simulating too early, I don't think we're doing enough checks earlier in the process." The build's gates (lengths,
structure, outline) all ran after every stage had finished, so a start wrong in its first second cost the whole solve and
came back as "front.L 90 % off at the front crotch". Now each stage of the SOFT build (GarmentBuild.soft_net) is gated
where it ends, before the next stage runs:

1. START (seconds, before any soft solve) on the soft start (piece_start): every tube closed round each girth loop it was
   measured at (`round:<tube>@<loop>`), .L / .R starts mirror each other (`mirror:<piece>`), no start sunk into the body
   (`inside:<piece>`). Back to step 5's start (piece_start) or step 3 / 4 (a tape or a piece's measurement list).
2. CHAINS (after the chain solve, before surfaces): every free chain at its length (MAX_FREE_PCT, the existing 2 % rule:
   `length`, `held_length`), each tube still round its loops and each pair still mirrored where its start put it.
3. SURFACES (after the fill between the chains, BEFORE the slow thread solve): coverage (`holes:<piece>`: no face torn
   open past the weave's own limit) and `soft_cloth_smooth` (structure_rows' roughness, C286) read HERE, so crumpling made
   by the surface lay is told apart from crumpling made by the solve.

A FAIL raises StageFailed(stage, gate); the worker ends the job `stage_failed` with its rows, its look (stage_look: the
start / the chains alone / the surface, on the body, the tapes drawn), the step to go back to and what to change.
Every limit is an existing number, named in its row's source. Nothing names a garment or a limb.
"""
from __future__ import annotations

import pickle
from pathlib import Path

import numpy as np

STAGES = ("start", "chains", "surfaces")
OPEN_DEG = 90.0  # a tube with a gap wider than a quarter turn round its loop is not closed round (a two-piece tube missing
#                 one piece leaves ~180 deg)
SLICE = 0.015  # m: half the slice read round a loop: 1.5x the 0.01 m flat row bins _tube_points lays rows at (or
# 0.6x the mesh's own row spacing when coarser: a slice always holds a row)
BACK = {"start": ("5", "the START (piece_start): the piece's measurement list (step 4 piece_measurements) or where its "
                       "tapes were taken (step 3 body_tape), then chain_garment again"),
        "chains": ("5", "the CHAIN stage: a length off its cut is the pattern's (alter_pattern at the named line); a tube "
                        "or pair pulled off its start is the start or the seams joining it (pattern_check)"),
        "surfaces": ("6", "the SURFACES lay (chain_garment soft fill between the chains): torn or crumpled before any "
                          "solve is the lay, not the cloth")}


class StageFailed(Exception):
    def __init__(self, stage: str, gate: dict):
        super().__init__(f"{stage}: " + "; ".join(r["id"] for r in gate["rows"] if r["status"] == "FAIL"))
        self.stage, self.gate = stage, gate


def _row(id_, value, limit, ok, source, change, unit="") -> dict:
    return {"id": id_, "status": "PASS" if ok else "FAIL", "ours": {"value": f"{value}{unit}"}, "ref": f"{limit}{unit}",
            "source": source, "change": "" if ok else change}


# Rows whose limits aren't calibrated yet (no build that passes the end gates has been read against them; the hussar fails
# them too): reported as "INFO (would FAIL)", never stopping a build, until a passing build sets them (coordinator,
# 2026-11-03). The other rows rest on existing rules (2 % lengths, the stand-off gap, piece_start's tube rule, roughness).
PROVISIONAL = ("inside:", "holes:", "sewn:")


def verdict(stage: str, rows: list, reads: dict | None = None) -> dict:
    for r in rows:
        if r["status"] == "FAIL" and r["id"].startswith(PROVISIONAL):
            r["status"] = "INFO (would FAIL)"
    bad = [r for r in rows if r["status"] == "FAIL"]
    back, change = BACK[stage]
    return {"stage": stage, "verdict": "FAIL" if bad else "PASS", "rows": rows, "back_to": back if bad else None,
            "change": change if bad else "", "reads": reads or {}}


# ---------------------------------------------------------------- readings
def _soft(b) -> list:
    R = b.roles
    return list(R.panels) + list(R.tubes)


def _groups(b) -> list:
    """Each tube group once: (its pieces, side)."""
    from .chain_garment import hand_of
    seen, out = set(), []
    for t in b.roles.tubes:
        g = tuple(sorted((b.roles.tube_groups or {}).get(t) or [t]))
        if g not in seen:
            seen.add(g)
            out.append((list(g), hand_of(t)))
    return out


def _loop_frame(P):
    P = np.asarray(P, float)
    c = P.mean(0)
    n = np.linalg.svd(P - c)[2][2]
    r = float(np.linalg.norm((P - c) - np.outer((P - c) @ n, n), axis=1).mean())
    return c, n, r


def round_reads(b, X, use=None) -> dict:
    """{(group name, loop name): the widest gap in degrees round the loop's centre in the group's cloth} in a slice at
    each sided girth loop the group was measured at (piece_start._tapes_of / sided): a closed tube has no wide gap."""
    from .piece_start import _tapes_of, sided
    out = {}
    for grp, side in _groups(b):
        loops = {}
        for p in grp:
            for n, P in _tapes_of(b.net, p)[0]:
                if sided(P, side):
                    loops[n] = P
        if not loops:
            continue
        gv = np.concatenate([b.net.verts(p) for p in grp])
        E = b.net.edges[np.all(np.isin(b.net.edges, gv), axis=1)]
        sl = max(SLICE, 0.6 * float(np.median(np.abs(b.net.uv[E[:, 0], 1] - b.net.uv[E[:, 1], 1])[
            np.abs(b.net.uv[E[:, 0], 1] - b.net.uv[E[:, 1], 1]) > 1e-6]))) if len(E) else SLICE  # (wider than a row)
        V = X[gv[use[gv]]] if use is not None else X[gv]
        for n, P in loops.items():
            c, nrm, r = _loop_frame(P)
            d = V - c
            ax = d @ nrm
            pl = d - np.outer(ax, nrm)
            k = np.abs(ax) < sl  # (the group's own cloth only: a loose hem stands well off its loop)
            if not k.any():
                out[(",".join(grp), n)] = 360.0
                continue
            u = np.cross(nrm, [0.0, 0.0, 1.0] if abs(nrm[2]) < 0.9 else [1.0, 0.0, 0.0])
            u /= np.linalg.norm(u)
            w = np.cross(nrm, u)
            th = np.arctan2(pl[k] @ w, pl[k] @ u)
            th = np.sort(th)
            out[(",".join(grp), n)] = round(float(np.degrees(np.diff(np.r_[th, th[0] + 2 * np.pi]).max())), 1)
    return out


def mirror_reads(b, X, use=None) -> dict:
    """{piece.L: (p50 mm, p90 mm)}: each .R piece's points against its .L partner's mirrored (x -> -x), matched by their
    flat position (the .R cut is the .L cut mirrored: spec convention)."""
    from scipy.spatial import cKDTree
    net, out = b.net, {}
    soft = _soft(b)
    for p in soft:
        if not p.endswith(".L") or p[:-2] + ".R" not in soft:
            continue
        vl, vr = net.verts(p), net.verts(p[:-2] + ".R")
        best = None
        for fx in (1.0, -1.0):
            dd, j = cKDTree(net.uv[vl] * [fx, 1.0]).query(net.uv[vr])
            if best is None or dd.mean() < best[0].mean():
                best = (dd, j)
        dd, j = best
        k = dd < 0.003  # (matched flat points only: 3 mm on the cut)
        if use is not None:
            k &= use[vr] & use[vl[j]]
        if k.sum() < 3:
            continue
        e = np.linalg.norm(X[vr[k]] - X[vl[j[k]]] * [-1.0, 1.0, 1.0], axis=1) * 1e3
        out[p] = (round(float(np.percentile(e, 50)), 1), round(float(np.percentile(e, 90)), 1))
    return out


def _pairs(b) -> list:
    soft = _soft(b)
    return [(p, p[:-2] + ".R") for p in soft if p.endswith(".L") and p[:-2] + ".R" in soft]


def mirror_starts(b, X):
    """The soft start with every .R piece laid as its .L partner's mirror (x -> -x), point by point through the flat:
    each .R flat point at its place in the .L's mirrored flat (linear inside its triangles, nearest outside). The spec
    convention (.L mirrors to .R) made exact at the start. (F5: the trousers' .R tube was started by its own phase
    rule, which a mirrored flat runs the other way: its front piece at the back, never wrapped round its leg.)"""
    from scipy.interpolate import LinearNDInterpolator, NearestNDInterpolator
    net, X = b.net, np.array(X, float)
    for pl, pr in _pairs(b):
        vl, vr = net.verts(pl), net.verts(pr)
        best = None
        for fx in (-1.0, 1.0):  # (which way the .R flat was cut: mirrored, or the same)
            from scipy.spatial import cKDTree
            dd = cKDTree(net.uv[vl] * [fx, 1.0]).query(net.uv[vr])[0]
            if best is None or dd.mean() < best[0]:
                best = (dd.mean(), fx)
        Q = net.uv[vl] * [best[1], 1.0]
        Y = X[vl] * [-1.0, 1.0, 1.0]
        P = LinearNDInterpolator(Q, Y)(net.uv[vr])
        bad = ~np.isfinite(P).all(1)
        if bad.any():
            P[bad] = NearestNDInterpolator(Q, Y)(net.uv[vr][bad])
        X[vr] = P
    b.reads.setdefault("starts", {})["mirrored"] = [f"{pr} from {pl}" for pl, pr in _pairs(b)]
    return X


def inside_reads(b, X) -> dict:
    """{piece: share of its points deeper in the body than GAP}: a start through the body, not on it."""
    from .chain_garment import GAP
    out = {}
    for p in _soft(b):
        v = b.net.verts(p)
        d = b.body.contact.query(X[v])[0]
        out[p] = round(float((d < -GAP).mean()), 3)
    return out


# ---------------------------------------------------------------- the gates
def chain_vertices(net) -> np.ndarray:
    """Per vertex: on a chain or line (what the chain stage solves; the rest still lies at its start)."""
    li, lj, _, _ = net.lines()
    k = np.zeros(net.n, bool)
    k[np.r_[net.link_i, net.link_j, li, lj].astype(int)] = True
    return k[net.root]


def _placement_rows(b, X, stage: str) -> tuple[list, dict]:
    from .chain_garment import GAP, LAYER
    rows, reads = [], {}
    use = chain_vertices(b.net) if stage == "chains" else None
    rr = round_reads(b, X) if stage == "start" else {}  # (the chain stage solves outlines only: read as moved:, below)
    reads["round"] = {f"{g}@{n}": v for (g, n), v in rr.items()}
    for (g, n), v in rr.items():
        rows.append(_row(f"round:{g}@{n}", v, OPEN_DEG, v <= OPEN_DEG, f"piece_start TUBE rule: its seams close it round; "
                         f"the widest gap (deg) in its cloth round the girth loop {n} it was measured at; limit a quarter turn",
                         f"{g} is not round its {n} loop at the {stage}: " + ("its start (piece_start: the loops it names; "
                         "a piece of the tube placed elsewhere)" if stage == "start" else "the chains pulled it off: the seam "
                         "joining the tube's pieces, or the start it left")))
    mr = mirror_reads(b, X, use)
    reads["mirror_mm"] = {p: list(v) for p, v in mr.items()}
    lim = round(GAP * 1e3, 1) if stage == "start" else round((GAP + LAYER) * 1e3 * 2, 1)
    for p, (p50, p90) in mr.items():
        val = p90 if stage == "start" else p50
        rows.append(_row(f"mirror:{p[:-2]}", val, lim, val <= lim,
                         (f"spec: .L mirrors to .R; {'p90' if stage == 'start' else 'p50 (a lap may break it locally)'} "
                          f"mm of {p[:-2]}.R from {p} mirrored; limit " + ("GAP (the build's stand-off)" if stage == "start"
                          else "2x (GAP + LAYER): the stand-off plus one lap, on both sides")),
                         f"{p[:-2]}.R does not mirror {p} at the {stage}: " + ("the .R start (piece_start: mirrored loops, "
                         "_tube_points phase)" if stage == "start" else "the chains broke the pair: the seams of the .R side "
                         "(a sewn root shared across the centre) or its start")))
    return rows, reads


def sewn_reads(b, X) -> dict:
    """{piece: (p90 mm its points sewn to an already built stiff part start from where they are sewn, a quarter of
    that sewn edge's flat length in mm)}: a seam to a band starting a quarter way round from its place is on the wrong side."""
    net = b.net
    stiff = b._stiff_mask()
    held = np.zeros(net.n, bool)
    held[net.root[stiff]] = True
    out = {}
    for p in _soft(b):
        v = net.verts(p)
        v = v[held[net.root[v]] & ~stiff[v]]
        if len(v) < 2:
            continue
        e = np.linalg.norm(X[v] - b.X[net.root[v]], axis=1) * 1e3
        L = float(np.linalg.norm(np.ptp(net.uv[v], axis=0))) * 1e3
        out[p] = (round(float(np.percentile(e, 90)), 1), round(L / 4, 1))
    return out


def gate_start(b, X) -> dict:
    from .chain_garment import GAP
    rows, reads = _placement_rows(b, X, "start")
    sw = sewn_reads(b, X)
    reads["sewn_mm"] = {p: list(v) for p, v in sw.items()}
    for p, (m, lim) in sw.items():
        rows.append(_row(f"sewn:{p}", m, lim, m <= lim, f"a piece starts at the stiff part it is sewn to (built first): "
                         f"p90 mm from its seam's place; limit a quarter of that sewn edge's flat length",
                         f"{p} starts away from the band it is sewn to: the band's placement (which way round it runs, "
                         "its height) or the piece's start", "mm"))
    ins = inside_reads(b, X)
    reads["inside"] = ins
    lim = 0.1  # (the share: one point in ten through the body is a misplaced piece, not ease: a reading of the start)
    for p, v in ins.items():
        rows.append(_row(f"inside:{p}", v, lim, v <= lim, f"a start lies on the body: share of {p}'s points deeper "
                         f"than GAP ({GAP * 1e3:.1f} mm) inside it; limit 1 in 10",
                         f"{p} starts through the body: its start (piece_start: its tapes or measurement list)"))
    return verdict("start", rows, reads)


def moved_reads(b, X, X0) -> dict:
    """{tube piece: (p90 mm its outline moved from its start, the smallest girth radius it was started round in mm)}."""
    from .piece_start import _tapes_of, sided
    use = chain_vertices(b.net)
    out = {}
    for grp, side in _groups(b):
        rs = [_loop_frame(P)[2] for p in grp for _, P in _tapes_of(b.net, p)[0] if sided(P, side)]
        if not rs:
            continue
        for p in grp:
            v = b.net.verts(p)
            v = v[use[v]]
            e = np.linalg.norm(X[v] - X0[v], axis=1) * 1e3
            out[p] = (round(float(np.percentile(e, 90)), 1), round(min(rs) * 1e3, 1))
    return out


def gate_chains(b, X) -> dict:
    from .chain_garment import MAX_FREE_PCT
    c = b.chain_read(X)
    rows = [_row("length", c["free_worst_pct"], MAX_FREE_PCT, c["free_worst_pct"] <= MAX_FREE_PCT,
                 "MAX_FREE_PCT (chain_garment): a free chain link off its cut, worst, read at the chain stage",
                 f"{c['free_worst_line']}: the pattern can't make this line here (alter_pattern at it) or the start "
                 "put it where it can't reach")]
    if "held_worst_pct" in c:
        rows.append(_row("held_length", c["held_worst_pct"], MAX_FREE_PCT, c["held_worst_pct"] <= MAX_FREE_PCT,
                         "MAX_FREE_PCT: a link held at both ends (F1)", f"{c.get('held_worst_line')}: the stiff piece's cut"))
    pr, reads = _placement_rows(b, X, "chains")
    X0 = getattr(b, "stage_start", None)
    if X0 is not None:
        mv = moved_reads(b, X, X0)
        reads["moved_mm"] = {p: list(v) for p, v in mv.items()}
        for p, (m, r) in mv.items():
            pr.append(_row(f"wrapped:{p}", m, r, m <= r, f"the outline stays where its start put it: p90 mm its chains "
                           f"moved from the start; limit the smallest girth radius it was started round (piece_start loops)",
                           f"{p} left its start in the chain solve (moved past its own girth's radius): the seams "
                           "joining it pull it off (pattern_check the seam pairs), or a length it can't reach", "mm"))
    reads.update(free_worst_pct=c["free_worst_pct"], free_worst_line=c["free_worst_line"])
    return verdict("chains", rows + pr, reads)


def hole_reads(b, X) -> dict:
    """{piece: share of its faces whose area is past the weave's limit squared (SHEAR_LIMIT on each edge) of its flat
    area, or not finite}: the surface torn open between its chains."""
    from .chain_garment import SHEAR_LIMIT
    net, out = b.net, {}
    F = np.asarray(net.F)
    for p in _soft(b):
        Fp = F[net.piece[F[:, 0]] == net.pid(p)]
        if not len(Fp):
            out[p] = 1.0
            continue
        a3 = 0.5 * np.linalg.norm(np.cross(X[Fp[:, 1]] - X[Fp[:, 0]], X[Fp[:, 2]] - X[Fp[:, 0]]), axis=1)
        u = net.uv
        e1, e2 = u[Fp[:, 1]] - u[Fp[:, 0]], u[Fp[:, 2]] - u[Fp[:, 0]]
        a2 = 0.5 * np.abs(e1[:, 0] * e2[:, 1] - e1[:, 1] * e2[:, 0])
        bad = ~np.isfinite(a3) | (a3 > a2 * (1 + SHEAR_LIMIT) ** 2)
        out[p] = round(float(bad.mean()), 4)
    return out


HOLE_SHARE = 0.01  # (the share of a piece's faces torn: the threads gate's own 1 in 100 faces (zozo cap p99))


def gate_surfaces(b, X) -> dict:
    from . import structure_rows as sr
    from .chain_garment import SHEAR_LIMIT
    hr = hole_reads(b, X)
    rows = [_row(f"holes:{p}", v, HOLE_SHARE, v <= HOLE_SHARE, f"coverage: share of {p}'s faces past (1 + SHEAR_LIMIT "
                 f"{SHEAR_LIMIT})^2 of their flat area (torn open); limit 1 in 100 (the threads p99)",
                 f"{p}'s surface is torn between its chains: the SURFACES fill or the chains it spans") for p, v in hr.items()]
    rough = sr.roughness(X, b.net.M, _soft(b))
    worst = max(rough.items(), key=lambda kv: kv[1]["bump_p90_mm"] / kv[1]["limit_mm"]) if rough else None
    ratio = round(worst[1]["bump_p90_mm"] / worst[1]["limit_mm"], 2) if worst else 0.0
    rows.append(_row("soft_cloth_smooth", ratio, 1.0, ratio <= 1.0,
                     f"structure_rows soft_cloth_smooth (C286): bump p90 <= {sr.ROUGH_LIMIT_X:g}x a smooth "
                     f"R{sr.ROUGH_SMOOTH_R_MM:.0f} mm tube's, worst piece ({worst[0] if worst else '-'}), read on the "
                     "surface lay BEFORE the solve", f"{worst[0] if worst else ''} crumpled by the surface lay itself "
                     "(the fill between the chains), not by the solve"))
    return verdict("surfaces", rows, {"holes": hr, "rough": {k: round(v["bump_p90_mm"] / v["limit_mm"], 2)
                                                              for k, v in rough.items()}})


GATES = {"start": gate_start, "chains": gate_chains, "surfaces": gate_surfaces}


def check(b, stage: str, X):
    """Run the stage's gate on X (per vertex); keep it in b.reads["stages"]; FAIL: raise StageFailed (the stage's X kept
    on the build for its look). b.stage_gates False: read only (a resume or a caller that gates itself)."""
    if not getattr(b, "stage_gates", True):
        return None
    done = b.reads.setdefault("stages", {})
    if stage in done:  # (each stage gated once per build: a second soft solve (the fall's rest) is not a new stage)
        return done[stage]
    if stage == "start":
        b.stage_start = np.asarray(X, float).copy()
    g = GATES[stage](b, np.asarray(X, float))
    done[stage] = {k: v for k, v in g.items() if k != "reads"} | {"reads": g["reads"]}
    if g["verdict"] == "FAIL" and getattr(b, "stage_gates", True) != "report":  # ("report": read every stage, stop none)
        b.stage_X = (stage, np.asarray(X, float).copy())
        e = StageFailed(stage, g)
        e.build = b
        raise e
    return g


# ---------------------------------------------------------------- the look
def save(d, b, stage: str, X):
    pickle.dump({"stage": stage, "X": X, "M": b.net.M, "bV": b.body.V, "bT": b.body.T,
                 "links": (np.asarray(b.net.link_i), np.asarray(b.net.link_j))}, open(Path(d) / "stage.pkl", "wb"))


def on_fail(d, e, put, log=print):
    """The worker's end of a StageFailed: stage.pkl (the stage's X for its look), status stage_failed with the gate,
    then the look rendered (a look's failure never loses the result)."""
    b = e.build
    stage, X = b.stage_X
    save(d, b, stage, X)
    put(stage="stage_failed", stage_failed=stage, stage_gate=e.gate, reads=b.reads)
    try:
        put(stage_look=look(d, log=log))
    except Exception as ex:  # (the look is a picture of the result, not the result)
        put(stage_look_error=f"{type(ex).__name__}: {ex}"[:200])


def _tubes(segs, r=0.0025, k=5):
    """Thin k-sided tubes round segments [(a, b)]: chains and tapes drawn as lines."""
    V, F = [], []
    for a, b in segs:
        t = b - a
        L = np.linalg.norm(t)
        if L < 1e-6:
            continue
        t = t / L
        u = np.cross(t, [0, 0, 1.0] if abs(t[2]) < 0.9 else [1.0, 0, 0])
        u /= np.linalg.norm(u)
        w = np.cross(t, u)
        th = np.linspace(0, 2 * np.pi, k, endpoint=False)
        ring = (np.cos(th)[:, None] * u + np.sin(th)[:, None] * w) * r
        o = sum(len(x) for x in V)
        V.append(np.r_[a + ring, b + ring])
        F += [[o + i, o + (i + 1) % k, o + k + (i + 1) % k] for i in range(k)]
        F += [[o + i, o + k + (i + 1) % k, o + k + i] for i in range(k)]
    return (np.concatenate(V), np.array(F)) if V else (np.zeros((0, 3)), np.zeros((0, 3), int))


def tape_segments(M) -> list:
    out = []
    for t in ((M.get("starts") or {}).get("tapes") or {}).values():
        P = np.asarray(t["pts"], float)
        for s in (1.0, -1.0):
            Q = P * [s, 1, 1]
            out += list(zip(Q[:-1], Q[1:]))
    return out


def look(d, size: int = 520, log=print) -> list:
    """The failing stage's look, shape only (C288): start / surfaces = the cloth at that stage on the body; chains = the
    chains ALONE on the body; the tapes drawn (red) beside start and chains. [(view, path)]."""
    from . import cloth, resources
    from .chain_garment import joined_faces
    r = pickle.load(open(Path(d) / "stage.pkl", "rb"))
    X, M, stage = r["X"], r["M"], r["stage"]
    parts = [{"name": "body", "V": r["bV"], "F": r["bT"], "color": "#c4bcb4"}]
    if stage == "chains":
        i, j = r["links"]
        V, F = _tubes(list(zip(X[i], X[j])), r=0.002)
        parts.append({"name": "chains", "V": V, "F": F, "color": "#3a6fb0"})
    else:
        parts.append({"name": "cloth", "V": X, "F": joined_faces(X, M, r["bV"], r["bT"]), "color": "#a9c4e6"})
    if stage != "surfaces":
        V, F = _tubes(tape_segments(M), r=0.003)
        if len(F):
            parts.append({"name": "tapes", "V": V, "F": F, "color": "#d03030"})
    lo, hi = X.min(0), X.max(0)
    box = [[lo[0] - 0.05, lo[1] - 0.05, lo[2] - 0.03], [hi[0] + 0.05, hi[1] + 0.05, hi[2] + 0.05]]
    res = []
    with resources.heavy(f"stage look {stage}", gb=3.0, gpu=True, log=log):
        for nm, dv in (("front", [0, -1, 0.05]), ("side", [-1, 0, 0.05]), ("back", [0, 1, 0.05])):
            p = cloth.render(parts, str(Path(d) / f"stage_{stage}_{nm}"), views=[{"name": nm, "dir": dv}], resolution=size,
                             box=box)[0]
            res.append((nm, str(p)))
    return res


def answer(name: str, garment: str, wear: str, st: dict, again: str, look_call: str) -> str:
    g = st.get("stage_gate") or {}
    from .chain_structure import row_line
    bad = [r for r in g.get("rows") or [] if r["status"] == "FAIL"]
    ok = [r["id"] for r in g.get("rows") or [] if r["status"] == "PASS"]
    passed = [s for s in STAGES[:STAGES.index(g.get("stage", "start"))]]
    return (f"{name}:{garment} ({wear}): stage_failed: {g.get('stage')} ({len(bad)} rows fail; passed stages: "
            f"{', '.join(passed) or 'none'}; pass here: {', '.join(ok[:12]) or 'none'}); nothing after it ran\n"
            + "\n".join(row_line(r) for r in bad[:12]) + (f"\n  ... {len(bad) - 12} more" if len(bad) > 12 else "")
            + f"\n  back to step {g.get('back_to')}: {g.get('change')}"
            + (f"\n  look: {', '.join(p for _, p in st.get('stage_look') or [])}" if st.get("stage_look") else "")
            + f"\nnext: {look_call} shows the {g.get('stage')} stage; fix it there, then {again}")
