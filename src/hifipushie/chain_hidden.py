"""HIDDEN FIRST (T12b, C296): layering "visible" (the default) decides what of the under garment is hidden BEFORE any of it
can push the over garment, and omits it for real (T12 worked it out after the over build, as advice only: the hidden
shirt collar pushed the jacket's stand out, 34.9 % at the back neck).

THE ORDER (build_over, the worker's build of a garment worn over others in mode "visible"):
  (a) the over garment built on the body + each under garment's cloth THICKNESS where it covers (every under face read as
      cover: nothing of it stands off yet);
  (b) what that build hides (decide): an under point is hidden where the over garment covers it (its nearest place on the
      over garment not on an open edge: past a hem, between open fronts, above a stand it is seen), on the body's side or
      poking through (pressed in, it is hidden);
  (c) the hidden part omitted: a piece hidden >= HIDDEN_OMIT is dropped whole; the others keep their seen part + MARGIN
      into the hidden cloth; the record names each omitted piece and why, with the step 1 change (`build: omit`);
  (d) only the KEPT stiff parts (a collar showing above a stand) and the SEEN solid details (buttons in an open V) push:
      the collider gets them, and the over build is RE-SOLVED from (a)'s build (resolve: its last solve on the new
      collider, held points it now sits inside moved out), only when one of them reaches it;
  (e) the kept parts fitted inside the over garment and held (chain_press.fit_one with the decision).
CUT EDGES (trim): a trimmed piece is cut along the level line MARGIN into the hidden cloth of a smoothed distance-to-seen
field (never the mesh's jagged face boundary): the cut points moved onto that line, smoothed and evened along it (the mesh's
own spacing), then held between the body and the over garment's inner side; the read says how many of them it covers.
Mode "full" keeps T12's order (everything pushes, everything pressed).
"""
from __future__ import annotations

import numpy as np
from scipy.spatial import cKDTree

from . import chain_net as cn
from .chain_garment import GAP

MARGIN = 0.03  # m: a seen part is kept this far into the hidden cloth; its cut runs there (chain_press.MARGIN)
HIDDEN_OMIT = 0.98  # share of a piece hidden: omitted whole (chain_press.HIDDEN_OMIT)
SMOOTH = 4  # Laplace passes over the distance-to-seen field (the cut follows its level line, not the faces)
CUT_SMOOTH = 12  # passes along the cut line (positions and spacing)
REACH_TOL = 0.0005  # m: an over point this far inside the new collider is reached by a pusher (re-solve)


def _nbrs(F, n):
    e = cn.edges_of(F)
    nb = [[] for _ in range(n)]
    for a, b in e.tolist():
        nb[a].append(b)
        nb[b].append(a)
    return [np.array(x, np.int64) for x in nb]


def field(X, covered, Fw, rounds: int = SMOOTH) -> np.ndarray:
    """m per vertex: how far into the hidden cloth (0 where seen), smoothed over the welded mesh."""
    seen = ~covered
    if not seen.any():
        return np.full(len(X), np.inf)
    f = cKDTree(X[seen]).query(X)[0]
    nb = _nbrs(Fw, len(X))
    for _ in range(rounds):
        m = np.array([f[n].mean() if len(n) else f[i] for i, n in enumerate(nb)])
        f = np.where(seen, 0.0, 0.5 * f + 0.5 * m)
    return f


def decide(ub, lim, under: str, over: str, details: dict | None = None) -> dict:
    """(b) + (c): the under build `ub` against the over garment's inner side `lim` (chain_press.OuterLimit). Returns keep_v
    (vertices kept), f (the field), covered, omitted {piece: why}, pieces {piece: hidden / kept %}, push_F (kept stiff
    faces, welded), details {name: seen?}, record (the step 1 change)."""
    from .chain_layers import welded
    net = ub.net
    X = np.asarray(ub.X, float)
    covered = lim.query(X)[0] < 0.5
    Fw = welded(net.F, net.root)
    f = field(X, covered, Fw)
    h = float(np.median(np.linalg.norm(X[Fw[:, 1]] - X[Fw[:, 0]], axis=1))) if len(Fw) else 0.0
    near = (f <= MARGIN + h)[np.asarray(net.root)]  # (faces straddle the cut line; trim moves their far points onto it)
    keep_v = near.copy()
    pieces, omitted = {}, {}
    for p in net.names:
        v = net.verts(p)
        if not len(v):
            continue
        hp = float(covered[v].mean())
        pieces[p] = {"hidden_pct": round(hp * 100, 1)}
        if hp >= HIDDEN_OMIT:
            omitted[p] = f"hidden under {over} ({round(hp * 100, 1)} % of it, by visibility in the planned state)"
            keep_v[v] = False
        pieces[p]["kept_pct"] = round(float(keep_v[v].mean() * 100), 1)
    keep_v[np.asarray(net.root)[keep_v]] = True  # (a sewn point is kept, at its root, when any side of it is: one point)
    stiff = np.isin(net.root, net.root[ub._stiff_mask()])
    push_F = Fw[(stiff[Fw].all(1)) & keep_v[Fw].all(1)]
    dseen = {}
    for n_, m in (details or {}).items():
        if not m or not len(m.get("F", [])):
            continue
        c = np.asarray(m["V"], float).mean(0)[None]
        near = int(cKDTree(X).query(c)[1][0])
        dseen[n_] = bool(lim.query(c)[0][0] >= 0.5 and keep_v[near])
    rec = ""
    if omitted:
        ch = ", ".join(f'"{p}": {{"build": "omit", "why": "hidden under {over} (C296)"}}' for p in omitted)
        rec = (f"{under}'s step 1 builds {', '.join(omitted)} though {over} hides them: call_tool(\"garment_plan\", "
               f"{{\"name\": <model>, \"garment\": \"{under}\", \"step\": \"parts\", \"plan\": <its step 1 with pieces "
               f"{{{ch}}}>}})")
    return {"keep_v": keep_v, "f": f, "covered": covered, "omitted": omitted, "pieces": pieces, "push_F": push_F,
            "details": dseen, "record": rec, "edge_mm": round(h * 1e3, 2)}


def trim(X, F, root, dec: dict, lim, body_contact, gap_out: float) -> tuple:
    """(keep faces of F, cut vertices, X, read): the kept faces of F (unwelded, as net.F), their cut edge (a boundary of the
    kept welded faces that is not one of the garment's own edges) moved onto the field's MARGIN level line, smoothed and
    evened along it, then held inside the over garment (gap_out off its inner side) and off the body (GAP)."""
    from .chain_layers import welded
    X = np.asarray(X, float).copy()
    kv, f = dec["keep_v"], dec["f"]
    F = np.asarray(F, np.int64)
    keep = kv[F].all(1)
    Fw_all, Fw = welded(F, root), welded(F[keep], root)
    own = {tuple(e) for e in cn.boundary_edges(Fw_all).tolist()} if len(Fw_all) else set()
    cut_e = np.array([e for e in cn.boundary_edges(Fw).tolist() if tuple(e) not in own], np.int64).reshape(-1, 2) \
        if len(Fw) else np.zeros((0, 2), np.int64)
    cut = np.zeros(len(X), bool)
    cut[cut_e.ravel()] = True
    nb = _nbrs(Fw, len(X)) if len(Fw) else [np.zeros(0, np.int64)] * len(X)
    for v in np.where(cut & (f > MARGIN))[0]:  # (onto the level line: along the edge to its lowest neighbour)
        n = nb[v][f[nb[v]] < f[v]] if len(nb[v]) else nb[v]
        if not len(n):
            continue
        w = n[np.argmin(f[n])]
        t = float(np.clip((f[v] - MARGIN) / max(f[v] - f[w], 1e-9), 0.0, 1.0))
        X[v] = X[v] + t * (X[w] - X[v])
    ln = [[] for _ in range(len(X))]
    for a, b in cut_e.tolist():
        ln[a].append(b)
        ln[b].append(a)
    two = np.array([v for v in np.where(cut)[0] if len(ln[v]) == 2], np.int64)
    rough0 = _rough(X, two, ln)
    for _ in range(CUT_SMOOTH):  # (smoothed and evened along the line: each cut point towards its neighbours' middle)
        mid = np.array([X[ln[v]].mean(0) for v in two]).reshape(-1, 3)
        if len(two):
            X[two] = 0.5 * X[two] + 0.5 * mid
    c = np.where(cut)[0]
    if len(c):  # (held: inside the over garment where it covers, off the body)
        d, n = lim.query(X[c])
        ins = d < 0.5
        mv = ins & (d < gap_out)
        X[c[mv]] += n[mv] * (gap_out - d[mv])[:, None]
        db, nbn = body_contact.query(X[c])
        lo = db < GAP
        X[c[lo]] += nbn[lo] * (GAP - db[lo])[:, None]
    X = X[np.asarray(root)] if root is not None else X
    cov = lim.query(X[c])[0] < 0.5 if len(c) else np.zeros(0, bool)
    seg = np.linalg.norm(X[cut_e[:, 1]] - X[cut_e[:, 0]], axis=1) if len(cut_e) else np.zeros(0)
    read = {"cut_points": int(len(c)), "cut_inside_pct": round(float(cov.mean() * 100), 1) if len(c) else 100.0,
            "cut_seg_mm": [round(float(np.percentile(seg, q)) * 1e3, 1) for q in (5, 50, 95)] if len(seg) else [],
            "cut_rough_mm": [round(rough0, 2), round(_rough(X, two, ln), 2)], "edge_mm": dec.get("edge_mm")}
    return keep, cut, X, read


def _rough(X, two, ln) -> float:
    """mm, p95: how far a cut point stands off its two neighbours' middle (a jagged cut reads ~ half an edge)."""
    if not len(two):
        return 0.0
    mid = np.array([X[ln[v]].mean(0) for v in two])
    return float(np.percentile(np.linalg.norm(X[two] - mid, axis=1), 95) * 1e3)


def resolve(b, LB, log=None) -> dict:
    """(d): the over build `b` re-solved on the collider LB from where it is (its last solve, chain_garment final_links):
    held points LB now holds inside are moved out along its normal, the mesh then the chains solved again."""
    I2, J2, L2, E2, held, fl2, th = b.final_links
    X = np.asarray(b.X, float).copy()
    d, n = LB.contact.query(X)
    bad = np.asarray(held, bool) & (d < GAP)
    X[bad] += n[bad] * (GAP - d[bad])[:, None]
    fl = [(LB.contact,) + tuple(fl2[0][1:])] + list(fl2[1:])
    E2 = np.asarray(E2, bool)
    rd = {}
    for rnd in range(3):
        X, rd = cn.project(X, I2, J2, L2, E2, held, fl, threads=th, iters=30, step=0.006)
        X, rd = cn.project(X, I2[E2], J2[E2], L2[E2], E2[E2], held, fl, iters=30, step=0.006)
        if log:
            log(f"re-solve {rnd}: {rd}")
    b.X, b.body = X[b.net.root], LB
    b.final_links = (I2, J2, L2, E2, held, fl, th)
    b.reads["chains"] = b.chain_read(b.X)
    return {"held_moved": int(bad.sum()), "last": rd}


def build_over(model: str, garment: str, body, under: dict, make, log=print) -> tuple:
    """(build, collider) of `garment` worn over `under` (chain_layers.under_for) in mode visible: (a)-(d) above; `make`
    (collider -> a GarmentBuild, not run). The collider carries .hidden {under: decision} for the fit (e)."""
    from pathlib import Path
    from . import chain_layers as cl, chain_presim as cp, chain_press as cpr, garment_details as gd
    LA = cl.layered_body(model, garment, body, under, log=log, push={})
    b = make(LA)
    b.run()
    oX, oF = np.asarray(b.X, float), cl.welded(b.net.F, b.net.root)
    lim = cpr.OuterLimit(oX, oF, body.contact)
    hid, push, summ = {}, {}, {}
    for u, x in under.items():
        ub, _ = cp.load_build(Path(x["job"]))
        dp = Path(x["job"]) / "details.pkl"
        dets = (gd.load_result(dp).get("built") or {}) if x.get("details") and dp.exists() else {}
        dec = decide(ub, lim, u, garment, dets)
        hid[u] = dec
        seen_d = [k for k, v in dec["details"].items() if v]
        if len(dec["push_F"]) or seen_d:
            push[u] = {"stiff_F": dec["push_F"], "details": seen_d}
        summ[u] = {"omitted": dec["omitted"], "pieces": dec["pieces"], "pushing": {"stiff_faces": int(len(dec["push_F"])),
                   "details": seen_d}, "details_hidden": [k for k, v in dec["details"].items() if not v],
                   "record": dec["record"]}
    LB, rs = LA, None
    if push:
        LD = cl.layered_body(model, garment, body, under, log=log, push=push)
        reach = LD.contact.query(b.X)[0] < GAP - REACH_TOL
        if reach.any():
            rs = resolve(b, LD, log=log)
            rs["reached"] = int(reach.sum())
        LB = LD
    LB.hidden = hid
    b.body = LB
    b.reads["hidden"] = {"under": summ, "resolved": rs or "nothing kept of the under garment reaches it"}
    if log:
        log(f"hidden first: omitted {[(u, list(s['omitted'])) for u, s in summ.items()]}; re-solve {bool(rs)}")
    return b, LB
