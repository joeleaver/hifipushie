"""CHAIN DRAPE (garment_steps T13, C297): garments that hang free below where they are held (a cloak, a cape, a hood, a
skirt's free hem). Their shape is how they FALL, so the chain build builds only what holds them and the sim makes the rest.

Why (Joe 2026-11-02, the ranger's hooded cloak): "judge the build, not the hang" (C279). A fitted garment's build fixes its
shape; a draped one's build fixes only the neckline / shoulder line / hood opening edge and its closures (a clasp at the
throat). Judging a cloak's hem or a hood's depth on the build judges the start we chose, not the garment.

THE PLAN carries it (nothing here knows a garment):
- step 1 piece `hang: "draped"` (default "fitted") and `held: [edge, ...]`: the edges built exactly on the body (the
  draft's declared edge names: a cloak's neck). A draped piece with no held edge of its own is held where it is sewn to a
  held edge (a hood on the cloak's neckline); one with neither is refused by name.
- step 2 `drape: {piece: {falls: down|up, source}}`: which way its free cloth starts (a hood worn UP rises over the head
  and falls onto it in the sim); default down.
- step 2 rows of a HANG kind (structure_rows.KINDS[..]["on"] == "hang": the hem's height, spread and front / back fall, the
  hood's opening and depth) wait for step 8; the build's rows are judged at the build as before (structure_rows).

THE BUILD (build_drape, from GarmentBuild.run when the plan has draped pieces):
1. HELD LINE: the declared held edges as ONE line of their pattern length, resting on the body round the neck base
   (held_ring: the neck-base ellipse through cf_neck / neck_side / cb_neck, widened until its 3D length is the pattern's,
   each point dropped from above until it rests GAP off the body: the high points). An open line's two ends meet at CF
   (its closure: a clasp) CLASP_GAP apart. Held in every later stage and in the hang (the plan's state).
2. FREE CLOTH: each free vertex starts on the path of its nearest held vertex (flat distance d along it): out and down
   (or up) at the smallest angle that keeps the whole path CLEAR off the body, turning straight down (up) once clear (over
   a shoulder, past an arm). An open held line's ends fan apart (FAN_DEG) so two edges never start on one path. Radial
   lengths are exact by construction; lines across may only be shorter (gathered); the soft network (soft_net) then
   projects every chain and line with the body as a floor: the start is legal by construction, never shaped by hand.
3. THE HANG (step 8, ZOZO): the fall. hang_reads reads the draped rows on the hung cloth; hang_check judges them.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np

DRAPED, FITTED = "draped", "fitted"
HANGS = (FITTED, DRAPED)
FALLS = ("down", "up")
CLEAR = 0.012  # m: a start path keeps this far off the body (GAP + a coarse panel edge's sag)
GAP_START = 0.0045  # m: chain_garment.GAP: where the held line rests
CLASP_GAP = 0.004  # m: an open held line's ends at CF, closed (structure: <= chain_structure.BAND_SHUT_MM)
FAN_DEG = 10.0  # an open held line's ends fan apart by this angle each side (two edges never on one path)
FAN_ARC = 0.06  # m: the fan fades over this much of the held line from each end
HEM_SHARE = 0.85  # the hem: free border at >= this share of the piece's largest distance from its held line


class DrapeRefused(ValueError):
    pass


# ---------------------------------------------------------------- the plan
def plan_drape(plan: dict | None) -> dict:
    """{piece: {held: [edges], falls}} for the step-1 pieces with hang "draped" (step 2's drape gives falls)."""
    pcs = ((plan or {}).get("parts") or {}).get("pieces") or {}
    falls = ((plan or {}).get("style") or {}).get("drape") or {}
    return {n: {"held": list(p.get("held") or []), "falls": (falls.get(n) or {}).get("falls", "down")}
            for n, p in pcs.items() if isinstance(p, dict) and p.get("hang") == DRAPED and p.get("build") != "omit"}


def check_parts(pieces: dict, bad: list):
    """garment_plan step 1: hang / held."""
    for n, x in pieces.items():
        if not isinstance(x, dict):
            continue
        h = x.get("hang", FITTED)
        if h not in HANGS:
            bad.append(f"pieces.{n}.hang {h!r}: one of {', '.join(HANGS)} (draped: hangs free below where it is held)")
        if x.get("held") is not None and (h != DRAPED or not isinstance(x["held"], list)
                                          or not all(isinstance(e, str) for e in x["held"])):
            bad.append(f"pieces.{n}.held: a list of the piece's edge names, only on a hang \"draped\" piece")


def check_style(style: dict, pieces: dict, bad: list):
    """garment_plan step 2: drape {piece: {falls, source}} only on draped pieces; rows' stage fits the pieces."""
    dr = style.get("drape") or {}
    if not isinstance(dr, dict):
        bad.append("drape: {piece: {falls: down|up, source}}")
        return
    for n, x in dr.items():
        p = pieces.get(n)
        if not isinstance(p, dict) or p.get("hang") != DRAPED:
            bad.append(f"drape.{n}: not a step-1 piece with hang \"draped\"")
        elif not isinstance(x, dict) or x.get("falls") not in FALLS or not str(x.get("source") or "").strip():
            bad.append(f"drape.{n}: {{falls: {'|'.join(FALLS)}, source}}")


def draped_pieces(parts: dict | None) -> set:
    return set(plan_drape({"parts": parts}))


# ---------------------------------------------------------------- the pattern
def _edge_verts(net, piece: str, how) -> np.ndarray:
    if not isinstance(how, str):
        raise DrapeRefused(f"held edge of {piece}: a path edge ({how!r}) is not read yet; declare it as 'a>b' or "
                           "'a>via>b' (draft_pattern edges)")
    pts = net.M.get("points") or {}
    vs = []
    for k in how.split(">"):
        v = pts.get(f"{piece}:{k}")
        if v is None:
            raise DrapeRefused(f"held edge of {piece}: point {k!r} not on the pattern (draft_pattern edges.{piece})")
        vs.append(int(v))
    arc = net.arc(piece, vs)
    if arc[0] != vs[0]:
        arc = arc[::-1]
    return arc


def info(model: str, garment: str, net, spec: dict | None = None, plan: dict | None = None) -> dict | None:
    """The draped pieces of a garment's build: {pieces: {name: {falls, held (ordered vertices of its own held edges)}}}."""
    from . import chain_structure as cs, store
    plan = cs.load_plan(model, garment) if plan is None else plan
    dp = plan_drape(plan)
    if not dp:
        return None
    spec = spec or store.load(model)
    pdir = ((spec.get("cloth") or {}).get(garment) or {}).get("pattern", {}).get("dir")
    decl = json.loads((Path(pdir) / "declarations.json").read_text()) if pdir else {}
    out = {}
    for n, x in dp.items():
        if n not in net.names:
            raise DrapeRefused(f"{n}: a draped step-1 piece not in the pattern (draft_pattern)")
        hv = []
        for e in x["held"]:
            how = ((decl.get("edges") or {}).get(n) or {}).get(e)
            if how is None:
                raise DrapeRefused(f"{n}.held {e!r}: no such edge in the draft's declarations (edges.{n})")
            hv.append(_edge_verts(net, n, how))
        out[n] = {"falls": x["falls"], "held": np.concatenate(hv) if hv else np.zeros(0, np.int64)}
    return {"pieces": out}


# ---------------------------------------------------------------- 1. the held line
RING_LIFT = 0.01  # m: the widened neck-base ring starts this far above the landmarks, then rests


def held_ring(body, length: float, gap: float, n: int = 720) -> np.ndarray:
    """A closed ring (n points, from CF going round +X, CB, -X back to CF) of 3D length `length`, resting on the body
    round the neck base: the neck-base ellipse through cf_neck / neck_side / cb_neck widened to the length, lifted clear,
    then rested as a rigid ring on the high points (chain_rest.rest_ring, the band's rest: C280)."""
    from .chain_rest import rest_ring
    cf, cb, ns = (np.asarray(body.at[k], float) for k in ("cf_neck", "cb_neck", "neck_side.L"))
    cy, ay, ax = (cf[1] + cb[1]) / 2, (cb[1] - cf[1]) / 2, abs(ns[0])
    th = np.linspace(0, 2 * math.pi, n, endpoint=False)
    c = np.cos(th)
    z0 = ns[2] + np.where(c > 0, c * (cf[2] - ns[2]), -c * (cb[2] - ns[2])) + RING_LIFT
    for h in np.arange(0.0, 0.15, 0.005):  # (the lowest height round the neck where a ring of this length fits)
        k = 1.0
        for _ in range(12):
            P = np.c_[np.sin(th) * ax * k, cy - c * ay * k, z0 + h]
            for _ in range(6):  # (each point put out of the body to the gap: a ring through the body is never rested)
                d, nrm = body.contact.query(P)
                low = d < gap * 1.05
                if not low.any():
                    break
                P[low] += nrm[low] * (gap * 1.1 - d[low])[:, None]
            per = float(np.linalg.norm(np.diff(np.r_[P, P[:1]], axis=0), axis=1).sum())
            if abs(per / length - 1) < 5e-4:
                break
            k *= (length / per) ** 1.2
        if abs(per / length - 1) < 2e-3 and float(body.contact.query(P)[0].min()) >= gap * 0.95:
            break
    else:
        raise DrapeRefused(f"no ring of the held line's {length * 1000:.0f} mm rests round the neck (last {per * 1000:.0f} mm): "
                           "the held edge is shorter than the neck where it could sit; next: lengthen it (draft_pattern)")
    R, info = rest_ring(P, body.contact, gap, np.r_[0.0, cy, float(ns[2]) + RING_LIFT + h])
    return R


def _along(P: np.ndarray, s: np.ndarray) -> np.ndarray:
    seg = np.linalg.norm(np.diff(np.r_[P, P[:1]], axis=0), axis=1)
    cum = np.r_[0, np.cumsum(seg)]
    Pc = np.r_[P, P[:1]]
    return np.c_[[np.interp(s, cum, Pc[:, i]) for i in range(3)]].T


# ---------------------------------------------------------------- 2. the free cloth
def _paths(X0, out, vert, tang, dmax, contact):
    """The clear path from X0: (angle off vertical, turn distance), the smallest horizontal reach that keeps CLEAR.
    Every candidate (angle 0..85 deg by 5, turn every 40 mm) is tested in ONE body query (straight down first, the
    rest only if none is clear); the first clear candidate with the least reach, in (angle, turn) order, wins."""
    t = np.arange(0.01, dmax + 0.02, 0.02)
    need = np.minimum(t / 0.05, 1.0) * CLEAR  # (the held line rests at GAP: the path clears the body as it leaves)
    sbs = np.r_[np.arange(0.04, min(dmax, 0.9), 0.04), dmax]
    for angs in (np.zeros(1), np.radians(np.arange(5, 86, 5))):
        A, S = (g.ravel() for g in np.meshgrid(angs, sbs, indexing="ij"))
        d1 = out[None] * np.sin(A)[:, None] + vert[None] * np.cos(A)[:, None]  # (c, 3)
        tc = np.minimum(t[None], S[:, None])  # (c, nt)
        P = X0 + tc[..., None] * d1[:, None] + (t[None] - tc)[..., None] * vert
        ok = (contact.query(P.reshape(-1, 3))[0].reshape(len(A), len(t)) >= need).all(axis=1)
        if ok.any():
            reach = np.where(ok, S * np.sin(A), np.inf)
            i = int(np.argmin(reach))
            return float(A[i]), float(S[i])
    raise DrapeRefused(f"no clear path from the held line at {np.round(X0, 3).tolist()} ({1000 * float(contact.query(X0[None])[0][0]):.1f} mm off the body, "
                       f"falls {'up' if vert[2] > 0 else 'down'}): the body is in the way "
                       "within 85 deg (a draped piece held inside the body?)")


def _path_pts(X0, out, vert, tang, a, sb, t, fan):
    d1 = out * math.sin(a) + vert * math.cos(a)
    t = np.asarray(t, float)
    P = X0 + np.minimum(t, sb)[:, None] * d1 + np.maximum(t - sb, 0)[:, None] * vert
    return P + (t * math.tan(math.radians(FAN_DEG)) * fan)[:, None] * tang


def check_held_sewn(net, hp: str, hv) -> None:
    """Refused by name: two points of the held line sewn into one (a seam pairs its ends the wrong way round: the held
    ring would be pinched shut there; the flat gate's lengths can't see it)."""
    from .chain_garment import ChainRefused
    rs, uv = net.root, net.uv
    _, first, cnt = np.unique(rs[hv], return_index=True, return_counts=True)
    if (cnt > 1).any():  # (two points of the held line sewn into one: a seam pairs its ends the wrong way round)
        k = int(first[np.argmax(cnt > 1)])
        two = np.where(rs[hv] == rs[hv[k]])[0]
        by = sorted({net.names[int(net.piece[v])] for v in np.where(rs == rs[hv[k]])[0]} - {hp})
        raise ChainRefused(f"{hp}'s held line is sewn to itself: its points {two.tolist()} of {len(hv)} (flat "
                           f"{np.round(uv[hv[two]], 3).tolist()}) are one point through {', '.join(by) or 'its own seams'}: "
                           "a seam pairs its edges' ends the wrong way round (a:start meets b:start). next: turn one edge "
                           "of that seam (draft_pattern edges \"p>q\" as \"q>p\")")


def build_drape(b, t0: float) -> None:
    """Stages for a garment whose pieces are all draped (module doc). Fitted + draped pieces in one garment: refused."""
    import time
    from .chain_garment import GAP, ChainRefused
    net, D = b.net, b.drape["pieces"]
    if b.roles.band or b.roles.fall or b.roles.rings or b.roles.front:
        raise ChainRefused("a garment with fitted stiff parts / a front AND draped pieces: not built yet (T13 builds "
                           "wholly draped garments). next: plan the fitted parts as their own garment, or report it")
    fitted = [p for p in net.names if p not in D]
    if fitted:
        raise ChainRefused(f"{', '.join(fitted)}: not draped in step 1, in a garment with draped pieces: T13 builds wholly "
                           "draped garments. next: hang: \"draped\" on them (garment_plan parts) or report it")
    rs, uv = net.root, net.uv
    own = [p for p in D if len(D[p]["held"])]
    if len(own) != 1:
        raise ChainRefused(f"held edges on {own or 'no piece'}: T13 builds ONE held line (a cloak's neck). next: "
                           "garment_plan parts held on the one piece that is held, the others sewn to it")
    hp = own[0]
    hv = D[hp]["held"]
    check_held_sewn(net, hp, hv)
    seg = np.linalg.norm(np.diff(uv[hv], axis=0), axis=1)
    L = float(seg.sum())
    if uv[hv[0], 0] < uv[hv[-1], 0]:  # (the end with the larger flat x goes to the wearer's left, +X)
        hv, seg = hv[::-1], seg[::-1]
    ring = held_ring(b.body, L + CLASP_GAP, GAP)
    s = CLASP_GAP / 2 + np.r_[0, np.cumsum(seg)]
    X = np.zeros((net.n, 3))
    X[hv] = _along(ring, s)
    held = np.isin(rs, rs[hv])
    for v in np.where(held)[0]:
        X[v] = X[hv[np.where(rs[hv] == rs[v])[0][0]]]
    centre = np.array([0.0, float(ring[:, 1].mean())])
    b.X = X.copy()
    b.extra_held = held
    X0 = X.copy()
    reads = {"held_piece": hp, "held_cut_mm": round(L * 1000, 1), "paths": {}}
    for p, x in D.items():
        v = net.verts(p)
        hv_p = v[held[v]]
        if not len(hv_p):
            raise ChainRefused(f"{p}: a draped piece neither held nor sewn to the held line. next: garment_plan parts held "
                               f"on {p}, or sew it to the held piece (draft_pattern seams)")
        vert = np.array([0, 0, 1.0 if x["falls"] == "up" else -1.0])
        line = hv_p[np.argsort(_order_on(hv, rs, hv_p))]
        cl = np.r_[0, np.cumsum(np.linalg.norm(np.diff(uv[line], axis=0), axis=1))]
        free = v[~held[v]]
        dd = np.linalg.norm(uv[free][:, None] - uv[line][None], axis=2)
        near = np.argmin(dd, axis=1)
        dist = dd[np.arange(len(free)), near]
        for k in np.unique(near):
            h = line[k]
            Xh = X[h]
            o = np.r_[Xh[:2] - centre, 0.0]
            o = o / max(np.linalg.norm(o), 1e-9)
            nb = line[min(k + 1, len(line) - 1)] if k < len(line) - 1 else line[k - 1]
            tg = X[nb] - Xh if k < len(line) - 1 else Xh - X[nb]
            tg = tg - o * (tg @ o)
            tg[2] = 0.0
            tg = tg / max(np.linalg.norm(tg), 1e-9)
            fan = 0.0
            if cl[-1] > 0:  # (the ends of this piece's held line fan apart: into the piece)
                e0, e1 = cl[k], cl[-1] - cl[k]
                fan = max(0.0, 1 - e0 / FAN_ARC) - max(0.0, 1 - e1 / FAN_ARC)  # (start end along +tg)
            fan *= float(_is_open_end(net, rs, h, held, line, k))
            m = near == k
            a, sb = _paths(Xh, o, vert, tg, float(dist[m].max()), b.body.contact)
            X0[free[m]] = _path_pts(Xh, o, vert, tg, a, sb, dist[m], fan)[np.arange(m.sum())] if m.sum() else X0[free[m]]
            reads["paths"].setdefault(p, []).append(round(math.degrees(a)))
        reads["paths"][p] = {"deg_min": min(reads["paths"][p]), "deg_max": max(reads["paths"][p])}
    b.reads["drape"] = reads
    b.reads["stiff_closed_s"] = round(time.time() - t0, 1)
    b.soft_net(start=X0)
    b.reads["drape"].update(start_reads(b.X, net, b.body, b.drape, held))


def _order_on(hv, rs, verts) -> np.ndarray:
    """Each vertex's position along the held line (by root)."""
    pos = {int(r): i for i, r in enumerate(rs[hv])}
    return np.array([pos.get(int(rs[v]), 0) for v in verts])


def _is_open_end(net, rs, h, held, line, k) -> bool:
    """An end of a piece's held line that is a free corner (not where two pieces' held lines meet at a seam)."""
    if 0 < k < len(line) - 1:
        return True  # (the fan is 0 in the middle anyway)
    cnt = np.bincount(rs, minlength=net.n)
    return cnt[rs[h]] <= 2  # (sewn to the held piece only: a front corner; a CB meeting has three or more)


# ---------------------------------------------------------------- reads
def _free_border(net, M, pieces, held) -> np.ndarray:
    border = np.asarray(M.get("border"), bool) if M.get("border") is not None else np.ones(net.n, bool)
    cnt = np.bincount(net.root, minlength=net.n)
    v = np.where(np.isin(net.piece, [net.pid(p) for p in pieces]) & border & ~held & (cnt[net.root] == 1))[0]
    return v


def start_reads(X, net, body, drape, held) -> dict:
    """At the build: the draped cloth's clearance off the body, the held line's length vs its cut, the clasp shut."""
    D = drape["pieces"]
    v = np.where(np.isin(net.piece, [net.pid(p) for p in D]))[0]
    clear = float(body.contact.query(X[v])[0].min()) * 1000
    hp = next(p for p in D if len(D[p]["held"]))
    hv = D[hp]["held"]
    cut = np.linalg.norm(np.diff(net.uv[hv], axis=0), axis=1)
    now = np.linalg.norm(np.diff(X[hv], axis=0), axis=1)
    worst = float(np.abs(now / np.maximum(cut, 1e-9) - 1).max()) * 100
    ends = float(np.linalg.norm(X[hv[0]] - X[hv[-1]])) * 1000
    return {"clear_min_mm": round(clear, 1), "held_worst_pct": round(worst, 2), "clasp_ends_mm": round(ends, 1)}


def hang_reads(X, M, body, drape: dict | None) -> dict:
    """Readings of the draped rows (structure_rows hang kinds) on the hung cloth (or any X)."""
    from .chain_net import Network
    if not drape:
        return {}
    net = Network(M)
    X = np.asarray(X, float)
    D = drape["pieces"]
    at = body.at
    held = np.zeros(net.n, bool)
    hp = [p for p in D if len(D[p]["held"])]
    for p in hp:
        held[D[p]["held"]] = True
    held = np.isin(net.root, net.root[held])
    r = {"stature_mm": round(float(np.ptp(body.V[:, 2])) * 1000, 1)}
    cy = (float(at["cf_neck"][1]) + float(at["cb_neck"][1])) / 2
    down = [p for p in D if D[p]["falls"] == "down"]
    up = [p for p in D if D[p]["falls"] == "up"]
    if down:
        fb = _free_border(net, M, down, held)
        hv = np.concatenate([D[p]["held"] for p in hp]) if hp else np.zeros(0, int)
        dd = np.linalg.norm(net.uv[fb][:, None] - net.uv[hv][None], axis=2).min(1) if len(hv) else np.zeros(len(fb))
        hem = fb[dd >= HEM_SHARE * dd.max()] if len(fb) else fb
        if len(hem):
            z0 = float(body.V[:, 2].min())
            r["drape_hem_height_mm"] = round((float(np.median(X[hem, 2])) - z0) * 1000, 1)
            r["drape_hem_spread_mm"] = round(float(np.ptp(X[hem, 0])) * 1000, 1)
            fr, bk = X[hem][X[hem, 1] < cy], X[hem][X[hem, 1] >= cy]
            if len(fr) and len(bk):
                r["drape_back_below_front_mm"] = round((float(np.median(fr[:, 2])) - float(np.median(bk[:, 2]))) * 1000, 1)
    if up:
        op = _free_border(net, M, up, held)
        uvv = np.where(np.isin(net.piece, [net.pid(p) for p in up]))[0]
        if len(op):
            r["hood_opening_mm"] = round(float(np.ptp(X[op, 0])) * 1000, 1)
            r["hood_depth_mm"] = round((float(X[uvv, 1].max()) - float(np.median(X[op, 1]))) * 1000, 1)
            r["hood_over_head_mm"] = round((float(X[uvv, 2].max()) - float(body.V[:, 2].max())) * 1000, 1)
    return r


def hang_check(X, M, body, plan: dict | None, drape: dict | None, waive: dict | None = None) -> dict:
    """Step 8's gate gains the draped rows: the plan's hang rows (and the hood rule) judged on the hung cloth."""
    from . import cloth_check as cc, garment_reads as gr, chain_structure as cs
    its, notes = cs.items(M, plan)
    its = [it for it in its if it.get("on") == "hang"]
    r = hang_reads(X, M, body, drape)
    for it in its:
        k = it["read"] if isinstance(it["read"], str) else ""
        if "/" in k and ":" not in k:
            a, b_ = (r.get(x) for x in k.split("/"))
            r[k] = round(a / b_, 3) if a is not None and b_ else None
    rows = gr.checklist_rows(its, r, "hang")
    for row, it in zip(rows, its):
        row["id"] = row["id"].split(":", 1)[1]
        row["measure"] = "chain_drape (the hang)"
        if it.get("missing"):
            row.update(status="UNMEASURED", why=it["missing"])
        if row["status"] in ("FAIL", "UNMEASURED"):
            row["change"] = it.get("change", "")
            if (waive or {}).get(row["id"]):
                row["waived"] = waive[row["id"]]
    return {"verdict": cc.verdict(rows, waive) if rows else "PASS", "rows": rows, "reads": r, "notes": notes}


def rule_items(plan: dict | None) -> list:
    """Build rows every draped garment gets (source: the rule): the start clear of the body, the held line at its cut,
    the clasp shut; and on the hang: a hood worn up covers the head."""
    dp = plan_drape(plan)
    if not dp:
        return []
    I = [dict(id="drape_start_clear", read="drape_clear_min_mm", range=[CLEAR * 1000 * 0.5, None], stage=1, on="build",
              source=f"rule: a draped piece starts clear of the body (chain_drape CLEAR {CLEAR * 1000:.0f} mm paths; "
                     "the soft network may settle it to half that)", change="the held line rests inside the body: "
                     "chain_drape held_ring / the start paths: a build fault, report it"),
         dict(id="drape_held_exact", read="drape_held_worst_pct", range=[None, 2.0], stage=1, on="build",
              source="rule: the held line is built exactly from the pattern (chain_garment MAX_FREE_PCT 2 %)",
              change="the held line can't rest at its cut length round the neck base: the neck edge (alter_pattern) "
                     "or chain_drape held_ring")]
    if any(x["falls"] == "up" for x in dp.values()):
        I.append(dict(id="hood_on_head", read="hood_over_head_mm", range=[0.0, None], stage=2, on="hang",
                      source="rule: a hood worn up (step 2 drape falls up) rests ON the head: its top above the head's",
                      change="the hood is too short to reach over the head (alter_pattern its height) or it fell off"))
    return I


def build_reads(b) -> dict:
    """The build's draped readings for chain_structure (start_reads, and the clasp state from its ends)."""
    d = (getattr(b, "reads", None) or {}).get("drape") or {}
    if not d:
        return {}
    from .chain_structure import BAND_SHUT_MM
    return {"drape_clear_min_mm": d.get("clear_min_mm"), "drape_held_worst_pct": d.get("held_worst_pct"),
            "drape_clasp_state": "closed" if (d.get("clasp_ends_mm") or 1e9) <= BAND_SHUT_MM else "open"}
