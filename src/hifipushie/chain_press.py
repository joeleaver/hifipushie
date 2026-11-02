"""THE UNDER GARMENT FITTED INSIDE THE OVER ONE (T12, C294). Layering where the outer garment rules: the over garment is built
on the body + the under garment's thickness + its stiff / solid parts (chain_layers.LayeredBody); then each under garment is
fitted INSIDE it here, its chains keeping their exact lengths, between two limits: the body (inside, GAP) and the over
garment's inner surface less both half thicknesses + ZOZO's reach (outside, OuterLimit). The outer limit acts only where the
over garment covers a point (its nearest place on the over garment not on an open edge: past a hem, between open fronts,
above a stand the under garment is free). Its stiff parts stay as built (they pushed the over garment out); its soft cloth
is pressed in, its spare length folding into the room it has (the soft stage's last solve, chain_garment final_links, with
the outer limit added).

TWO MODES (the over garment's step 2 `layers`: {"mode": "visible"|"full", "why"}; default visible):
  visible (the default, as game artists layer): the under garment is kept only where it is SEEN: a point is hidden when the
    over garment covers it on the body's side; faces within MARGIN of a seen point are kept (the collar inside the stand,
    cuffs, tails below the hem, the placket in an open V), the rest dropped, the kept part's hidden edge HELD (to the body /
    the over garment: fastened inside, as a game shirt collar is). No two-garment sim: the kept parts ride with what holds
    them. VISIBILITY CHECK: each under piece the plan builds "full" that is hidden here is named (omit / visible + margin:
    the change is the under garment's step 1 `build`).
  full (asked for with a reason: the over garment comes off at runtime, a close-up): the whole under garment pressed inside
    (room for FOLDS layers of it), both hung together in ZOZO with contact between them. The joint hang is NOT wired yet
    (T12: what's left is in docs/state/collar_outline.md); the press is.

THE ORDER (garment_record): the over garment's build needs the under's steps 1 + 4 and a build of it (not approved: its fit
comes after the over garment's build); the fit is written here (<over job>/under_<name>.pkl) and both are approved together
at the over garment's 7a.
"""
from __future__ import annotations

import pickle
from pathlib import Path

import numpy as np
from scipy.spatial import cKDTree

from . import chain_net as cn
from .chain_garment import GAP, MAX_FREE_PCT, zozo_legal

MODES = ("visible", "full")
FOLDS = 3  # layers "full": room for the under cloth this many times (a fold is the cloth three times)
MARGIN = 0.03  # m: a seen part is kept this far into the hidden cloth (its hidden edge, held there)
HIDDEN_OMIT = 0.98  # share of a piece hidden: "omit" it (step 1 build)
SEEN_FULL = 0.9  # share of a piece kept below which a "full" piece is "simplified: visible + margin"
AT_LIMIT = 0.0005  # m: a point this near its outer limit is pressed


def mode(model: str, garment: str) -> tuple:
    """(mode, why) from the over garment's step 2 `layers` (default visible)."""
    from . import garment_record as gr
    try:
        lay = (gr.load(model, garment)["steps"]["2"].get("output") or {}).get("layers") or {}
    except Exception:  # (no record: the default)
        lay = {}
    m = lay.get("mode", "visible") if isinstance(lay, dict) else "visible"
    return (m if m in MODES else "visible"), (lay.get("why", "") if isinstance(lay, dict) else "")


def room(t_u: float, t_o: float, mode_: str = "visible") -> tuple:
    """(push, gap_out) m: how far the over garment's collider stands off the body where the under cloth covers it (beyond
    GAP), and how far the under cloth stays inside the over garment's midsurface: both half thicknesses + ZOZO's reach;
    push leaves the under cloth itself room once (visible: pressed flat) or FOLDS times (full)."""
    gap_out = (t_u + t_o) / 2 + zozo_legal()
    return gap_out + (FOLDS if mode_ == "full" else 1) * t_u, gap_out


class OuterLimit:
    """The over garment's inner side as a limit (a chain_net Contact for project): signed distance positive on the body's
    side; points it doesn't cover read far (no limit)."""

    def __init__(self, X, F, body_contact):
        from .chain_layers import Layer, outward
        self.L = Layer("over", "cloth", X, outward(X, F, body_contact)[:, [0, 2, 1]], 0.0)

    def query(self, P):
        d, n, cov = self.L.query(P)
        return np.where(cov, d, 1.0), np.where(cov[:, None], n, 0.0)


def press(ub, lim: OuterLimit, gap_out: float, rounds: int = 3, log=None, keep_v=None) -> tuple:
    """(X, read) the under build `ub` (a GarmentBuild with final_links) pressed inside `lim`, as its soft stage builds:
    the chains first (exact, between the body and the outer limit), the cloth between them carried by their moves
    (chain_net.fill), the whole mesh (its edges at most their weave limit, threads at their cap), the chains last. Its held
    (stiff) points stay. A rough start (a build its own solve can't settle) is not stalled by its rough mesh this way."""
    I2, J2, L2, E2, _, fl2, th = ub.final_links
    rs = np.asarray(ub.net.root)
    held = np.zeros(len(ub.X), bool)  # (only its STIFF parts stay: the build's last solve holds its far cloth too, C296)
    held[rs[np.asarray(ub._stiff_mask(), bool)]] = True
    nodes = np.unique(rs[np.asarray(ub.net.F, np.int64)])
    c0, ids, g0 = fl2[0][0], nodes[~held[nodes]], GAP
    if keep_v is not None:  # (hidden first, C296: only the kept part is pressed; the omitted cloth plays no part)
        kv = np.asarray(keep_v, bool)
        m = kv[I2] & kv[J2]
        I2, J2, L2, E2 = I2[m], J2[m], L2[m], np.asarray(E2, bool)[m]
        held = np.asarray(held, bool) | ~kv
        ki = kv[ids]
        ids, g0 = ids[ki], (g0[ki] if np.ndim(g0) else g0)
    fl = [(c0, ids, g0), (lim, ids, gap_out)]
    Z0 = np.asarray(ub.X, float).copy()
    E2 = np.asarray(E2, bool)
    Ic, Jc, Lc, Ec = I2[E2], J2[E2], L2[E2], E2[E2]
    Y, rd = Z0, {}
    for rnd in range(rounds):
        Y, rd = cn.project(Y, Ic, Jc, Lc, Ec, held, fl, iters=30, step=0.004)
        if log:
            log(f"press chains {rnd}: {rd}")
    known = np.asarray(held, bool).copy()
    known[np.unique(np.r_[Ic, Jc])] = True
    Z = cn.fill(Z0, Y, known, ub.net.uv, ub.net.F, root=rs)
    for rnd in range(rounds):
        Z, rd = cn.project(Z, I2, J2, L2, E2, held, fl, threads=th, iters=20, step=0.004)
        Z, rd = cn.project(Z, Ic, Jc, Lc, Ec, held, fl, iters=20, step=0.004)  # (the chains last)
        if log:
            log(f"press mesh {rnd}: {rd}")
    return Z[rs], rd


def _level(at, z):
    from .chain_layers import _level as lv
    return lv(at, z)


def fit_one(ub, oX, oF, body, mode_: str, gap_out: float, log=None, decided=None) -> dict:
    """The under build fitted inside the over garment (oX, oF welded): {X, keep (faces of M["F"]), held (vertices),
    hidden, read}. read: moved / pressed by piece, the lengths, the visibility per piece. decided (chain_hidden.decide,
    mode visible, C296): what is kept was decided before the over build's last solve: only that is pressed, its cut
    edge trimmed onto a smooth line inside the cover and held there (read["cut"])."""
    net = ub.net
    X0 = np.asarray(ub.X, float)
    lim = OuterLimit(oX, oF, body.body_contact)
    if decided is not None and mode_ == "visible":
        from . import chain_hidden as ch
        X, rd = press(ub, lim, gap_out, log=log, keep_v=decided["keep_v"])
        keep, held, X, cut = ch.trim(X, net.F, net.root, decided, lim, body.body_contact, gap_out)
        return _fit_read(ub, X0, X, lim, body, mode_, gap_out, rd, keep, held, decided["covered"], cut, decided)
    X, rd = press(ub, lim, gap_out, log=log)
    sd, _ = lim.query(X)
    covered = sd < 0.5
    hidden = covered & (sd > -AT_LIMIT)  # (covered, on the body's side: the over garment hides it)
    F = np.asarray(net.F, np.int64)
    if mode_ == "visible" and (~hidden).any():
        near = cKDTree(X[~hidden]).query(X)[0] <= MARGIN
        keep = near[F].any(1)
    else:
        keep = np.ones(len(F), bool)
    dv = np.zeros(len(X), bool)
    dv[F[~keep].ravel()] = True
    kv = np.zeros(len(X), bool)
    kv[F[keep].ravel()] = True
    held = kv & dv  # (the kept part's hidden edge: fastened there)
    return _fit_read(ub, X0, X, lim, body, mode_, gap_out, rd, keep, held, hidden, None, None)


def _fit_read(ub, X0, X, lim, body, mode_, gap_out, rd, keep, held, hidden, cut, decided) -> dict:
    net = ub.net
    F = np.asarray(net.F, np.int64)
    sd, _ = lim.query(X)
    covered = sd < 0.5
    soft = ~np.isin(net.root, net.root[ub._stiff_mask()])
    moved = np.linalg.norm(X - X0, axis=1)
    d_in = body.body_contact.query(X0)[0] - body.body_contact.query(X)[0]  # (how far it came in towards the body)
    kv = np.zeros(len(X), bool)
    kv[F[keep].ravel()] = True
    chains = ub.chain_read(X)
    li, lj = net.link_i, net.link_j
    lk = kv[li] & kv[lj] & ~((held[li] | held[lj]) if cut is not None else (held[li] & held[lj]))  # (a trimmed cut is new cloth)
    e = np.abs(np.linalg.norm(X[lj] - X[li], axis=1) / np.maximum(net.link_L, 1e-9) - 1) * 100
    e0 = np.abs(np.linalg.norm(X0[lj] - X0[li], axis=1) / np.maximum(net.link_L, 1e-9) - 1) * 100
    ok0 = e0 <= MAX_FREE_PCT  # (the press answers for the lengths the build held; a build's own fault stays its own)
    lk_ok = lk & ok0
    by = {}
    for p in net.names:
        v = net.verts(p)
        if not len(v):
            continue
        s = soft[v]
        row = {"hidden_pct": round(float(hidden[v].mean() * 100), 1), "kept_pct": round(float(kv[v].mean() * 100), 1),
               "stiff": bool(not s.any())}
        if s.any():
            pr = s & covered[v] & (sd[v] < gap_out + AT_LIMIT)
            row.update(moved_mm_p50=round(float(np.median(moved[v][s]) * 1e3), 1),
                       moved_mm_max=round(float(moved[v][s].max() * 1e3), 1),
                       in_mm_p95=round(float(np.percentile(d_in[v][s], 95) * 1e3), 1),
                       pressed_pct=round(float(pr.mean() * 100), 1))
            if pr.any():
                row["pressed_at"] = _level(body.at, float(np.median(X[v][pr][:, 2])))
        by[p] = row
    out_lim = covered & (sd < gap_out - 0.001) & soft & kv
    read = {"mode": mode_, "pieces": by, "press": rd, "chains_free_worst_pct": chains["free_worst_pct"],
            "kept_free_worst_pct": round(float(e[lk_ok].max()), 3) if lk_ok.any() else 0.0,
            "build_free_worst_pct": round(float(e0.max()), 3), "press_broken_links": int((lk_ok & (e > MAX_FREE_PCT)).sum()),
            "outside_limit": int(out_lim.sum()), "kept_faces": int(keep.sum()), "faces": len(F), "held_edge": int(held.sum())}
    if out_lim.any():
        z = X[out_lim][:, 2]
        read["outside_at"] = _level(body.at, float(np.median(z)))
    if cut is not None:  # (the build's own chain read spans the omitted cloth: the kept links are what is answered for)
        read.pop("chains_free_worst_pct")
        read["cut"], read["omitted"] = cut, decided["omitted"]
        seen = kv & ~covered
        read["seen_points"] = int(seen.sum())
    return {"X": X, "keep": keep, "held": held, "hidden": hidden, "read": read}


def visibility_advice(model: str, under: str, read: dict, over: str) -> list:
    """Under pieces the plan builds "full" that the over garment hides: the change to its step 1 `build`."""
    from . import garment_record as gr
    try:
        pieces = (gr.load(model, under)["steps"]["1"].get("output") or {}).get("pieces") or {}
    except Exception:
        pieces = {}
    out = []
    for p, r in read["pieces"].items():
        b = (pieces.get(p) or {}).get("build", "full")
        if b != "full":
            continue
        if r["hidden_pct"] >= HIDDEN_OMIT * 100:
            out.append(f"{under} {p}: hidden under {over} ({r['hidden_pct']} %): step 1 build omit (why: under {over})")
        elif r["kept_pct"] < SEEN_FULL * 100:
            out.append(f"{under} {p}: {r['kept_pct']} % seen + margin: step 1 build simplified (why: the rest under {over})")
    return out


def fit_unders(model: str, garment: str, b, body, d=None, log=None) -> tuple:
    """Each under garment of `body` (a LayeredBody) fitted inside the over build `b`: body.fits gets each fit as a Layer
    (what the gate reads), <d>/under_<name>.pkl the fit. Returns (reads, refusal text or "")."""
    from . import chain_presim as cp
    from .chain_layers import Layer, outward, welded
    oX = np.asarray(b.X, float)
    oF = welded(b.net.F, b.net.root)
    reads, why = {}, []
    for u, x in body.info.items():
        try:
            ub, r = cp.load_build(Path(x["job"]))
        except (FileNotFoundError, ValueError) as e:
            reads[u] = {"fit": f"not fitted: {e}"}
            continue
        m = x.get("mode", "visible")
        dec = (getattr(body, "hidden", None) or {}).get(u)
        f = fit_one(ub, oX, oF, body, m, x["gap_mm"] * 1e-3, log=log, decided=dec)
        rd = f["read"]
        rd["advice"] = [dec["record"]] if dec and dec["record"] else ([] if dec else visibility_advice(model, u, rd, garment))
        reads[u] = rd
        Fw = welded(np.asarray(ub.net.F)[f["keep"]] if m == "visible" else ub.net.F, ub.net.root)
        body.fits[u] = Layer(u, "cloth", f["X"], outward(f["X"], welded(ub.net.F, ub.net.root), body.body_contact),
                             0.0, body.body_contact)
        worst = rd["kept_free_worst_pct"]
        if worst > MAX_FREE_PCT:
            why.append(f"{u} can't keep its lengths inside {garment}: {worst} % off its cut where it is kept ({m}, "
                       f"{rd['press_broken_links']} links its build held); "
                       f"the room {garment} leaves is too small: ease {garment} there in the draft (step 4)")
        if d is not None:
            pickle.dump({"X": f["X"], "M": r["M"], "F_kept": Fw, "keep": f["keep"], "held": f["held"],
                         "hidden": f["hidden"], "bV": body.body_V, "bT": body.body_T, "read": rd, "over": garment},
                        open(Path(d) / f"under_{u}.pkl", "wb"))
    return reads, "; ".join(why)
