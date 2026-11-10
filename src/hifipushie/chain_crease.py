"""CHAIN CREASE (R3d of docs/proposals/step5_one_build.md): every fold step 2 plans is TURNED to its turn_deg and lies on
its lies_on, lengths exact. A lapel rolled back to its break, a turned-back cuff and a rolled sleeve are one thing: a
crease along the draft's own fold row on a piece, the part beyond it turned over by an angle, lying on something.

Before R3d the build read wear["folds"] (chain_plan.planned_wear, R2 C392) and turned nothing; only a stiff collar's
fall was turned, by its own stage (chain_fall). Called in THE ORDER after the soft cloth is laid (soft_net, then the
plackets and the fall's rest), for each planned fold {on, fold, turn_deg, lies_on} (fold_bends.wear):

THE FOLD LINE is the draft's fold row on that piece (net.fold_rows: cloth.mesh puts a row of vertices on it, its ends on
the outline; a roll has rows over its arc). Nothing is drawn here: a planned fold the draft has no row for is refused
(back to step 4, the draft's folds).

THE TWO SIDES are the piece's faces split along its rows (face neighbours never cross a row edge). The HELD side is the
component with the most SEWN length on its outline (links whose two ends are sewn nodes: the seams to the body cloth, to
stiff parts, to a facing); ties go to the larger flat area. Every other component is TURNED (a roll's arc band between
its rows included). The HINGE is the row touching the held side. Why sewn length: a piece hangs from its seams; the part
beyond a crease with the fewest seams is the flap (folds.py's own default, "the side with less sewn edge").

WHERE THE TURNED REGION ENDS: a row from outline to outline (the mesh's rule) cuts off exactly its component: a lapel's
roll from the break on the front edge to the neckline turns the lapel and nothing below the break; along the front edge
the break point is a hinge vertex, so the edge bends there, it never tears. A row that stops inside the piece (no split):
the far side of the line within its span turns fully, and past each end of the line the turn fades to nothing over FADE
(folds.py's run-off length), so the cloth past the end bends, never tears; farther out nothing is turned, and the
projection bends what the turned cloth's exact edges pull (a crease dying inside a piece is a cone: cloth.mesh refuses
such a line in a draft, so this is only the rule for a planned turn shorter than its row).

THE TURN is a crease about the hinge, per station along it (the nearest point of the row in the flat): a point at flat
distance d from the line rolls round an arc of radius r for its first r * turn, then runs straight on, its laid shape
(curvature off the straight) rotated with it. 0 deg = flat on, 180 = right back onto the held side. A "roll" fold turns
softly, r = the draft's fold radius (Pattern.fold_radius) or else LAYER (one cloth thickness), so at 180 its plies lie
2 r apart at the crease; a "press" fold turns sharp, r = 0, about its row (a row is a mesh vertex line: the bend is AT it,
and an arc a link spans is no shape the links can hold), its plies kept LAYER apart by its lies_on. Pieces sewn to the turned region that are not held (a facing
sewn along a lapel's edge) are carried by the same turn, each point by the turned vertex nearest it (within CARRY).

LIES ON (after the turn): no turned point past 2 LAYER from the line may come nearer its lies_on surface than its gap
(the projection's floor), and past the measuring band (MEAS, where the turn is read) a turned point the turn brings
within ON_REACH of it is laid on it at its gap: LAYER outside the held side ("lies_on" its own piece) or another piece's surface, GAP
on the body; free: the angle alone. Then the NET'S PROJECTION (chain_net.project) has the last word, as every stage
ends: the soft solve's own links (chains, lines, mesh edges at most, threads, ties, the body floor) plus the lies_on
surface as a floor for the turned points. No length is chosen; only the bend is free. Pieces neither turned nor carried
are held in it, so a piece with no planned fold is untouched, bit for bit. Plies follow their host after it
(chain_holds.place_plies).

THE FALL: a roll fold on a STIFF part (chain_holds' `fall`: a collar's roll over its band) is turned by the FALL stage
(chain_fall.fall_build) as before and NOT here; its planned turn is read as `turned_by: fall`. R3e: fold the FALL's turn
into this one once the shirt control reads no worse (the shirt plans no fold bends today, so the choice is unproven).
A held node (a stiff part's, e.g. a lapel's gorge sewn to a collar built before it) is never moved by the turn.

READS (b.reads["crease"][bend id]): the measured turn (180 - the dihedral between the held and turned sides AT the line:
each side's tangent there from a quadratic fit of its points MEAS from the line, so neither a ply's offset nor the
laid curvature tilts it; median over the stations), the turned side's distance off its lies_on (median and least, mm), lengths after.
GATE (chain_stages stage "crease", one row per fold `fold:<bend id>`): FAIL when the measured turn is more than TURN_TOL
off turn_deg, or the turned side sinks inside its lies_on (least distance below -SINK_TOL); back to step 2's bend
(turn_deg, lies_on) or step 4's fold line. Nothing here names a garment, a piece or a limb.
"""
from __future__ import annotations

import numpy as np
import scipy.sparse as sp
from scipy.sparse.csgraph import connected_components
from scipy.spatial import cKDTree

from . import chain_net as cn
from .chain_core import GAP, LAYER, ChainRefused, cn_vnormals

FADE = 0.03  # m: past a line's end inside a piece the turn fades to 0 over this (folds.py run_off "over" default)
MEAS = (0.005, 0.04)  # m: flat distance band from the line (past a roll's arc) where the turn is measured
ON_REACH = 0.015  # m: a turned point brought this near its lies_on (past MEAS[0]) is laid on it at its gap
CARRY = 0.02  # m: a sewn neighbour's point is carried by the turned vertex nearest it within this
TURN_TOL = 15.0  # deg: the measured turn may be this far off the plan (the gate's limit)
SINK_TOL = 0.0005  # m: the turned side may not be deeper than this inside its lies_on


# ---- the plan: which rows turn
def jobs(b) -> list:
    """[(bend id, plan, fold entry, [rows])] for every planned fold this stage turns; the FALL's are noted, not turned."""
    net = b.net
    plan = (getattr(b, "wear", None) or {}).get("folds") or {}
    if not plan:
        return []
    H = getattr(b, "holds", None)
    falls = {(h["piece"], h["name"]) for h in (H.folds if H is not None else []) if h.get("fall")}
    rows: dict = {}
    for f, r in net.fold_rows():
        rows.setdefault((f.get("piece"), f.get("name")), (f, []))[1].append(r)
    out = []
    for bid, w in plan.items():
        on, name = str(w.get("on") or ""), w.get("fold")
        keys = [k for k in rows if k[1] == name and (k[0] == on or (k[0] or "")[:-2] == on and on not in net.names)]
        if not keys:
            raise ChainRefused(f"fold {bid}: step 2 turns {name!r} on {on}, and the draft has no fold row of that name on it. "
                               "next: declare the fold at step 4 (draft folds: {name, piece, line, kind}) or change step 2's bend")
        for k in keys:
            if k in falls:
                b.reads.setdefault("crease", {})[bid if len(keys) == 1 else f"{bid}@{k[0]}"] = {
                    "turned_by": "fall", "planned_deg": w.get("turn_deg")}
                continue
            out.append((bid if len(keys) == 1 else f"{bid}@{k[0]}", dict(w, on=k[0]), rows[k][0], rows[k][1]))
    return out


def _faces(net, piece):
    return net.F[np.all(net.piece[net.F] == net.pid(piece), axis=1)]


def sides(b, piece: str, rows: list) -> dict:
    """The held and turned sides of `piece` along its rows (see the module doc): turned (vertex ids), weight (1, or the
    fade past an inner end), hinge (the row on the held side), split (the rows cut the piece)."""
    net = b.net
    Fp = _faces(net, piece)
    row_e = {tuple(sorted(e)) for r in rows for e in zip(r[:-1].tolist(), r[1:].tolist())}
    # face neighbours across edges that are not row edges
    ek = {}
    for fi, f in enumerate(Fp):
        for a, c in ((f[0], f[1]), (f[1], f[2]), (f[2], f[0])):
            ek.setdefault(tuple(sorted((int(a), int(c)))), []).append(fi)
    A, B = [], []
    for e, fs in ek.items():
        if len(fs) == 2 and e not in row_e:
            A.append(fs[0])
            B.append(fs[1])
    G = sp.coo_matrix((np.ones(len(A)), (A, B)), shape=(len(Fp), len(Fp)))
    nc, lab = connected_components(G, directed=False)
    sewn = np.bincount(net.root, minlength=net.n)[net.root] > 1
    bnd = [e for e, fs in ek.items() if len(fs) == 1]
    if nc > 1:
        score = []
        for c in range(nc):
            Fc = Fp[lab == c]
            vs = set(Fc.ravel().tolist())
            L = sum(float(np.linalg.norm(net.uv[a] - net.uv[q])) for a, q in bnd
                    if a in vs and q in vs and sewn[a] and sewn[q] and lab[ek[(a, q)][0]] == c)
            p_, q_ = net.uv[Fc[:, 1]] - net.uv[Fc[:, 0]], net.uv[Fc[:, 2]] - net.uv[Fc[:, 0]]
            ar = float(np.abs(p_[:, 0] * q_[:, 1] - p_[:, 1] * q_[:, 0]).sum() / 2)
            score.append((round(L, 6), ar))
        base = max(range(nc), key=lambda c: score[c])
        bv = np.unique(Fp[lab == base])
        tv = np.setdiff1d(np.unique(Fp[lab != base]), bv)
        hinge = max(rows, key=lambda r: int(np.isin(r, bv).sum()))
        return {"turned": tv, "weight": np.ones(len(tv)), "hinge": hinge, "split": True, "held_v": bv,
                "sewn_m": {"held": score[base][0], "turned": round(sum(score[c][0] for c in range(nc) if c != base), 4)}}
    # a line that stops inside the piece: the far side within its span, the turn fading past its ends
    hinge = rows[0]
    v = np.unique(Fp)
    d, s_par, side = _station_flat(net.uv, hinge, net.uv[v])
    span = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(net.uv[hinge], axis=0), axis=1))]
    past = np.maximum(np.maximum(-s_par, s_par - span[-1]), 0.0)
    halves = []
    for sg in (1, -1):
        m = (side == sg) & ~np.isin(v, hinge)
        vs = set(v[m].tolist())
        halves.append(sum(float(np.linalg.norm(net.uv[a] - net.uv[q])) for a, q in bnd if a in vs and q in vs
                          and sewn[a] and sewn[q]))
    cnt = [int(((side == sg) & ~np.isin(v, hinge)).sum()) for sg in (1, -1)]
    far = -1 if (round(halves[0], 6), cnt[0]) >= (round(halves[1], 6), cnt[1]) else 1  # (less sewn, then smaller, turns)
    w = np.clip(1.0 - past / FADE, 0.0, 1.0)
    m = (side == far) & (w > 0) & ~np.isin(v, hinge)
    return {"turned": v[m], "weight": w[m], "hinge": hinge, "split": False, "held_v": v[~m],
            "sewn_m": {"held": round(max(halves), 4), "turned": round(min(halves), 4)}}


def _station_flat(uv, row, Q):
    """Nearest point of the flat polyline `row` to each Q: (distance, arc parameter (may run past the ends), side +-1)."""
    P = uv[row]
    a, c = P[:-1], P[1:]
    ab = c - a
    ln = np.maximum(np.linalg.norm(ab, axis=1), 1e-12)
    cum = np.r_[0.0, np.cumsum(ln)]
    t = ((Q[:, None, :] - a[None]) * ab[None]).sum(2) / ln[None] ** 2
    tc = np.clip(t, 0, 1)
    D = np.linalg.norm(Q[:, None, :] - (a[None] + tc[..., None] * ab[None]), axis=2)
    k = np.argmin(D, axis=1)
    r = np.arange(len(Q))
    tk = t[r, k]
    s = cum[k] + np.where((k == 0) & (tk < 0) | (k == len(ab) - 1) & (tk > 1), tk, tc[r, k]) * ln[k]
    cr = ab[k, 0] * (Q[:, 1] - a[k, 1]) - ab[k, 1] * (Q[:, 0] - a[k, 0])
    return D[r, k], s, np.where(cr >= 0, 1, -1)


def _frames(b, piece, hinge, vids):
    """Per vertex: the station on the hinge (3D point X0, tangent t, outward normal n, into-flap e1) and flat distance d."""
    net, X = b.net, b.X
    uv = net.uv
    P = uv[hinge]
    a, ab = P[:-1], P[1:] - P[:-1]
    ln2 = np.maximum((ab ** 2).sum(1), 1e-24)
    Q = uv[vids]
    t_ = np.clip(((Q[:, None, :] - a[None]) * ab[None]).sum(2) / ln2[None], 0, 1)
    D = np.linalg.norm(Q[:, None, :] - (a[None] + t_[..., None] * ab[None]), axis=2)
    k = np.argmin(D, axis=1)
    lam = t_[np.arange(len(Q)), k]
    d = D[np.arange(len(Q)), k]
    i0, i1 = hinge[k], hinge[k + 1]
    X0 = X[i0] + lam[:, None] * (X[i1] - X[i0])
    t = cn.unit(X[i1] - X[i0])
    N = cn_vnormals(X, _faces(net, piece))
    out = b.body.contact.query(X[hinge])[1]
    N[hinge] = np.where(((N[hinge] * out).sum(1) < 0)[:, None], -N[hinge], N[hinge])
    n = N[i0] + lam[:, None] * (N[i1] - N[i0])
    n = cn.unit(n - (n * t).sum(1, keepdims=True) * t)
    e1 = np.cross(n, t)
    sg = np.where(((X[vids] - X0) * e1).sum(1) < 0, -1.0, 1.0)
    return X0, t, n, e1 * sg[:, None], d, k


def _rot(v, ax, ph):
    c, s = np.cos(ph)[:, None], np.sin(ph)[:, None]
    return v * c + np.cross(ax, v) * s + ax * (ax * v).sum(1, keepdims=True) * (1 - c)


def crease_map(P, X0, n, e1, d, theta, r):
    """The crease: a point at flat distance d rolls round radius r for its first r * theta, then runs straight on; its
    laid shape off the straight line (P - X0 - d e1) rotates with it. theta per point (rad)."""
    ph = np.minimum(d / r, theta) if r > 0 else np.asarray(theta, float) * np.ones(len(d))
    s = np.maximum(d - r * ph, 0.0)
    ax = np.cross(e1, n)  # (e1 -> n under a positive turn)
    arc = r * np.sin(ph)[:, None] * e1 + r * (1 - np.cos(ph))[:, None] * n
    return X0 + arc + _rot(P - X0 - d[:, None] * e1, ax, ph) + s[:, None] * _rot(e1, ax, ph)


def _oriented(b, F):
    X = b.X
    fn = np.cross(X[F[:, 1]] - X[F[:, 0]], X[F[:, 2]] - X[F[:, 0]])
    out = b.body.contact.query(X[F].mean(1))[1]
    F = F.copy()
    flip = (fn * out).sum(1) < 0
    F[flip] = F[flip][:, [0, 2, 1]]
    return F


def lies_on(b, plan, sd_: dict):
    """(Contact, gap) of the surface the turned side lies on, or None (free)."""
    lo = plan.get("lies_on")
    if lo in (None, "free"):
        return None
    if lo == "body":
        return b.body.contact, GAP
    if lo == plan["on"]:
        F = _faces(b.net, plan["on"])
        F = F[np.isin(F, sd_["held_v"]).all(1)]
    elif lo in b.net.names:
        F = _faces(b.net, lo)
    else:
        raise ChainRefused(f"fold on {plan['on']}: lies_on {lo!r} is no piece of the draft. next: step 2's bend")
    if not len(F):
        return None
    return cn.Contact(b.X.copy(), _oriented(b, F)), LAYER


# ---- the turn
def _radius(b, f, plan) -> float:
    if f.get("kind") != "roll":
        return 0.0
    fr = getattr(getattr(b, "pat", None), "fold_radius", None) or {}
    r = fr.get(f.get("name")) or fr.get(plan["on"]) or f.get("radius")
    return float(r) if r else LAYER


def _held(b) -> np.ndarray:
    net = b.net
    fl = getattr(b, "final_links", None)
    held = np.array(fl[4], bool) if fl is not None else np.zeros(net.n, bool)
    if hasattr(b, "_stiff_mask"):
        held[net.root[b._stiff_mask()]] = True
    return held


def _set(b, v, P):
    r = b.net.root[np.asarray(v, np.int64)]
    b.X[r] = P
    b.X = b.X[b.net.root]


def turn(b, bid: str, plan: dict, f: dict, rows: list) -> dict:
    """Turn one planned fold (module doc); returns its state for the reads."""
    net = b.net
    rs = net.root
    piece = plan["on"]
    S = sides(b, piece, rows)
    tv = S["turned"]
    held = _held(b)
    r = _radius(b, f, plan)
    th_full = np.radians(float(plan["turn_deg"]))
    theta = th_full * S["weight"]
    X0, t, n, e1, d, _ = _frames(b, piece, S["hinge"], tv)
    Xb = b.X.copy()
    P = crease_map(Xb[tv], X0, n, e1, d, theta, r)
    mov = ~held[rs[tv]]
    # sewn neighbours that aren't held follow the turn, each point by its nearest turned vertex
    pv = net.verts(piece)
    other = np.isin(rs, rs[tv[mov]]) & (net.piece != net.pid(piece))
    carried = sorted({net.names[q] for q in np.unique(net.piece[other])})
    cv = np.zeros(0, np.int64)
    if carried:
        cand = np.where(np.isin(net.piece, [net.pid(c) for c in carried]) & ~held[rs] & ~np.isin(rs, rs[pv]))[0]
        dd, j = cKDTree(Xb[pv]).query(Xb[cand])
        pos = -np.ones(net.n, np.int64)
        pos[tv] = np.arange(len(tv))
        k = pos[pv[j]]
        ok = (dd < CARRY) & (k >= 0)
        cv, k = cand[ok], k[ok]
        Pc = crease_map(Xb[cv], X0[k], n[k], e1[k], d[k], theta[k], r)
    # lies on: past the measuring band, a turned point brought near its surface is laid on it at its gap
    ct = lies_on(b, plan, S)
    far = (d > r * theta + MEAS[1]) & (S["weight"] >= 1.0)
    if ct is not None and far.any():
        sdv, nv = ct[0].query(P[far])
        lay = sdv < ON_REACH
        Q = P[far]
        Q[lay] += (ct[1] - sdv[lay])[:, None] * nv[lay]
        P[far] = Q
    _set(b, tv[mov], P[mov])
    if len(cv):
        b.X[cv] = Pc
    # the net's projection has the last word; everything not turned or carried is held
    inv = [net.pid(piece)] + [net.pid(c) for c in carried]
    hold = held.copy()
    hold[rs[~np.isin(net.piece, inv)]] = True
    fl = getattr(b, "final_links", None)
    if fl is not None:
        I, J, L, E, _, floor, th = fl
    else:
        li, lj, lL, lE = net.lines()
        I, J = np.r_[net.link_i, li], np.r_[net.link_j, lj]
        L, E = np.r_[net.link_L, lL], np.r_[np.ones(len(net.link_L), bool), lE]
        floor, th = [(b.body.contact, np.unique(np.r_[I, J]), GAP)], None
    floor = list(floor)
    near = (d > r * theta + 2 * LAYER) & mov
    if ct is not None and near.any():
        floor.append((ct[0], np.unique(rs[tv[near]]), ct[1]))
    Z = b.X.copy()
    if th is not None:
        Z, _ = cn.project(Z, I, J, L, E, hold, floor, threads=th, iters=40, step=0.008)
    for _ in range(4):  # (lengths last; a turn moves points by its own width, a pass at most `step`)
        Z, rd = cn.project(Z, I, J, L, E, hold, floor, iters=40, step=0.008)
        if rd["worst_exact_pct"] <= 100 * cn.EXACT_TOL and rd["deepest_mm"] <= 0.02:
            break
    b.X = Z[rs]
    H = getattr(b, "holds", None)
    if H is not None and H.plies:
        from .chain_holds import place_plies
        place_plies(b, hosts={piece, *carried})
    return {"sides": S, "r": r, "theta": th_full, "ct": ct, "carried": carried, "project": rd, "pieces": inv,
            "moved": int(mov.sum()), "pinned": int((~mov).sum()), "carried_v": int(len(cv))}


def measure(b, plan: dict, st: dict) -> dict:
    """The turn as built: measured angle, how far the turned side lies off its lies_on, lengths of the pieces turned."""
    net, X = b.net, b.X
    S, r, th = st["sides"], st["r"], st["theta"]
    piece = plan["on"]
    hv = np.setdiff1d(S["held_v"], S["hinge"])
    tv = S["turned"][S["weight"] >= 1.0]
    out = {"planned_deg": float(plan["turn_deg"]), "lies_on": plan.get("lies_on"), "piece": piece,
           "turned_v": int(len(S["turned"])), "held_side_sewn_m": S["sewn_m"], "split": S["split"], "radius_mm": r * 1e3,
           "pinned_v": st["pinned"], "carried": st["carried"], "carried_v": st["carried_v"]}
    ang = []
    if len(hv) and len(tv):
        Xb0, tb, _, _, db, kb = _frames(b, piece, S["hinge"], hv)
        Xt0, tt, _, _, dt, kt = _frames(b, piece, S["hinge"], tv)
        mb = (db > MEAS[0]) & (db < MEAS[1])
        mt = (dt - r * th > MEAS[0]) & (dt - r * th < MEAS[1])

        mid = 0.5 * (MEAS[0] + MEAS[1])

        def way(P, X0, t, d, m, kk, k):
            """The side's tangent at the line, station k: u(d) = P - X0 off the line fitted as a + b d (+ c d^2 with 3
            or more distances); its direction b."""
            s_ = m & (kk == k)
            u, dd = P[s_] - X0[s_], d[s_]
            if len(np.unique(np.round(dd, 4))) < 2:
                return None
            A = np.c_[np.ones(len(dd)), dd] if len(np.unique(np.round(dd, 4))) < 3 else np.c_[np.ones(len(dd)), dd, dd ** 2]
            w = np.linalg.lstsq(A, u, rcond=None)[0][1]
            tk = t[s_].mean(0)
            return cn.unit(w - (w @ tk) * tk)
        for k in np.intersect1d(kb[mb], kt[mt]):
            a = way(X[hv], Xb0, tb, db, mb, kb, k)
            c = way(X[tv], Xt0, tt, dt - r * th, mt, kt, k)
            if a is not None and c is not None:
                ang.append(180.0 - float(np.degrees(np.arccos(np.clip(a @ c, -1, 1)))))
    out["measured_deg"] = round(float(np.median(ang)), 1) if ang else None
    out["stations"] = len(ang)
    ct = st["ct"]
    if ct is not None and len(tv):
        _, _, _, _, dt, _ = _frames(b, piece, S["hinge"], tv)
        far = dt - r * th > MEAS[1]
        sd = ct[0].query(X[tv[far]])[0] if far.any() else np.zeros(0)
        if len(sd):
            out.update(off_median_mm=round(float(np.median(sd)) * 1e3, 2), off_least_mm=round(float(sd.min()) * 1e3, 2),
                       gap_mm=round(ct[1] * 1e3, 2))
    m = np.isin(net.piece[net.link_i], st["pieces"]) | np.isin(net.piece[net.link_j], st["pieces"])
    l = np.linalg.norm(X[net.link_j[m]] - X[net.link_i[m]], axis=1)
    out["worst_link_pct"] = round(float(np.abs(l / np.maximum(net.link_L[m], 1e-9) - 1).max() * 100), 3) if m.any() else 0.0
    return out


def turn_all(b) -> dict:
    """Every planned fold no other stage turns, turned (module doc), read, then gated (chain_stages "crease")."""
    js = jobs(b)
    if not js:
        return b.reads.get("crease") or {}
    reads = b.reads.setdefault("crease", {})
    for bid, plan, f, rows in js:
        st = turn(b, bid, plan, f, rows)
        reads[bid] = dict(measure(b, plan, st), fold=f.get("name"), kind=f.get("kind"))
    from . import chain_stages as cst
    cst.check(b, "crease", b.X)
    return reads


def gate(b, X) -> dict:
    """chain_stages' "crease" stage: one row per turned fold, `fold:<bend id>`."""
    from .chain_stages import _row, verdict
    rows = []
    for bid, rd in (b.reads.get("crease") or {}).items():
        if rd.get("turned_by"):
            continue
        m, p, least = rd.get("measured_deg"), rd["planned_deg"], rd.get("off_least_mm")
        off_ok = m is not None and abs(m - p) <= TURN_TOL
        sink_ok = least is None or least >= -SINK_TOL * 1e3
        val = (f"turn {m} deg (planned {p}), " + (f"lies {rd.get('off_median_mm')} mm off {rd['lies_on']} (least {least}, "
               f"gap {rd.get('gap_mm')})" if least is not None else f"lies_on {rd['lies_on']}") +
               f", links {rd['worst_link_pct']} %")
        why = ("its turned side sinks inside " + str(rd["lies_on"]) if not sink_ok else
               f"it turned {m} deg against {p} planned" if m is not None else "no station measured on both sides")
        rows.append(_row(f"fold:{bid}", val, f"{p} +- {TURN_TOL} deg, least >= {-SINK_TOL * 1e3} mm", off_ok and sink_ok,
                         f"step 2's bend {bid} (turn_deg {p}, lies_on {rd['lies_on']}) on step 4's fold {rd.get('fold')} "
                         f"of {rd['piece']} (chain_crease: TURN_TOL, SINK_TOL)",
                         f"{why}: back to step 2's bend {bid} if the reference's crease isn't that turn or doesn't lie on "
                         f"{rd['lies_on']}, else step 4's fold line {rd.get('fold')} on {rd['piece']} (where it runs)"))
    return verdict("crease", rows, {"crease": b.reads.get("crease") or {}})
