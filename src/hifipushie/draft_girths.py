"""The flat pattern's girths at the body's levels (C383, t s4-13: no row measured the draft round the body, so a jacket
drafted ~2.5 cm under its plan's waist passed; the agent read 840 mm off the sheet by eye against step 0's 870).

A pattern maker walks a level line across the pieces: on a front and a back it lies the body's own surface drop below
the side neck point (hps), down the front / back at the hps; across a piece with no neck (a side panel) it joins the
points where that line meets its seams, carried over each seam at the same share of the seam's length (seams are
sewn end to end: draft_seam_ends). The widths along the line, summed over every torso piece, are the garment's girth
there; each step-3 girth of the torso (its loop round the centre line, below the neck) is checked against it:
  FAIL: under the body (it can't close), or under the body + step 0's fit ease by more than GIRTH_TOL;
  said: the ease each level has. Only the ring of pieces round the body is summed (a facing or canvas lying on
  another is pruned), an open dart's gap is taken off, and a lapped closure's overlap (edge to its paired marks).
Flat y is taken as the body's vertical on a torso piece (grain lengthwise). Nothing here knows a garment."""
from __future__ import annotations

import numpy as np

GIRTH_TOL = 0.03  # x the girth: the plan's ease met within this (the level is placed to ~1 cm on each piece, and
# the round changes ~4 mm per cm of level on a shaped front; C384: 1.5 % read s4-14's chest, 2.6 % under, as a fault)
NECK_GAP = 0.05  # m: a girth this close below the hps (the neck) is the collar's, not the body's


def section(V: np.ndarray, T: np.ndarray, x: float) -> np.ndarray:
    """The body's surface cut by the plane X = x: the points where its triangles' edges cross it."""
    out = []
    for a, b in ((0, 1), (1, 2), (2, 0)):
        A, B = V[T[:, a]], V[T[:, b]]
        da, db = A[:, 0] - x, B[:, 0] - x
        m = (da * db) < 0
        t = (da[m] / (da[m] - db[m]))[:, None]
        out.append(A[m] + t * (B[m] - A[m]))
    return np.concatenate(out) if out else np.zeros((0, 3))


def drops(V: np.ndarray, hps: np.ndarray, zs: list, T: np.ndarray | None = None) -> dict:
    """{"front" | "back": {z: m}}: the body's surface length from the hps straight down the front / back (the
    vertical plane x = hps.x, cut through its triangles T) to each level z."""
    hx, hz = float(hps[0]), float(hps[2])
    S = section(V, np.asarray(T), hx) if T is not None else V[np.abs(V[:, 0] - hx) < 0.012]
    out = {"front": {}, "back": {}}
    if len(S) < 10:
        return out
    hy = float(hps[1])
    for side, pick, half in (("front", np.min, S[:, 1] < hy), ("back", np.max, S[:, 1] > hy)):
        H = S[half]  # (the section's own side of the hps: a level with only the other side's points is skipped)
        for z in zs:
            bins = np.arange(hz, z - 1e-9, -0.01)
            pts = [(hy, hz)]
            for b in bins[1:]:
                sel = H[np.abs(H[:, 2] - b) < 0.006]
                if len(sel):
                    pts.append((float(pick(sel[:, 1])), float(b)))
            sel = H[np.abs(H[:, 2] - z) < 0.01]
            if len(sel):
                pts.append((float(pick(sel[:, 1])), float(z)))
            P = np.asarray(pts)
            out[side][z] = float(np.sum(np.linalg.norm(np.diff(P, axis=0), axis=1))) if len(P) > 1 else hz - z
    return out


def _cross(P: np.ndarray, q: np.ndarray, u: np.ndarray, closed: bool) -> list:
    """[(point, segment index, t)] where the line q + s u crosses polyline P."""
    n = np.array([-u[1], u[0]])
    d = (P - q) @ n
    out = []
    m = len(P) if closed else len(P) - 1
    for i in range(m):
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


def level(B: dict, D: dict) -> tuple[dict, list, list]:
    """({torso piece: width m}, [pieces the line didn't reach], [pieces whose line was lowered out of the armhole to
    the underarm]) for one level: D {"front" | "back": surface drop m}."""
    from . import draft_shape as ds, pattern
    pcs = B["pieces"]
    torso = [p for p, pc in pcs.items() if str((pc.get("wrap") or {}).get("to", "")).startswith("torso")]
    arcs = B.get("edge_arcs") or {}

    def edge(p, arc):
        pc = pcs[p]
        return np.asarray(pc["P"], float)[pattern.arc_indices(pc, arc)]
    limb = {p for p, pc in pcs.items() if p not in torso}
    holes = {}  # torso piece -> its edges sewn to a limb piece (a sleeve's armhole)
    for s in B.get("seams") or []:
        A, Bs = ds._sides(s[0]), ds._sides(s[1])
        for X, Y in ((A, Bs), (Bs, A)):
            if any(e.split(":", 1)[0] in limb for e in Y):
                for e in X:
                    if e.split(":", 1)[0] in torso:
                        holes.setdefault(e.split(":", 1)[0], []).append(e.split(":", 1)[1])
    lines, under = {}, []
    necks = {p: [edge(p, a) for k, a in (arcs.get(p) or {}).items() if ds.is_neck(k) and isinstance(a, str)]
             for p in torso}
    anyneck = any(necks.values())
    for p in torso:
        side = str((pcs[p].get("wrap") or {}).get("side", ""))
        # (the level hangs from the hps: only a piece with a neck edge reaches it; a panel placed on the back with no
        # neck gets its line over its seams (C384, t s4-14: its own top, the armpit, was read as the hps and its waist
        # line fell 280 mm low, below the panel, so the waist "didn't go round" and went unchecked))
        if side not in D or (anyneck and not necks[p]):
            continue
        P = np.asarray(pcs[p]["P"], float)
        neck = necks[p]
        top = max(float(N[:, 1].max()) for N in neck) if neck else float(P[:, 1].max())
        y = top - D[side]
        low = [float(edge(p, a)[:, 1].min()) for a in holes.get(p, [])]
        if low and y > min(low):  # (a level in the armhole: a tailor's chest line runs through the underarm point)
            y = min(low) - 1e-4
            under.append(p)
        lines[p] = (np.array([0.0, y]), np.array([1.0, 0.0]))
    pairs = []  # (piece, arc, other piece, other arc): single-edge seams between torso pieces
    for s in B.get("seams") or []:
        A, Bs = ds._sides(s[0]), ds._sides(s[1])
        if len(A) == len(Bs) == 1:
            (pa, ea), (pb, eb) = A[0].split(":", 1), Bs[0].split(":", 1)
            if pa in torso and pb in torso and pa != pb:
                pairs += [(pa, ea, pb, eb), (pb, eb, pa, ea)]
    for _ in range(len(torso)):  # carry the line over seams to pieces not yet reached
        got = {}
        for pa, ea, pb, eb in pairs:
            if pa in lines and pb not in lines:
                E = edge(pa, ea)
                c = _cross(E, *lines[pa], closed=False)
                if c:
                    got.setdefault(pb, []).append(_at_share(edge(pb, eb), _share(E, c[0][1], c[0][2])))
        if not got:
            break
        for p, pts in got.items():
            if len(pts) >= 2:
                a, b = pts[0], pts[-1]
                u = (b - a) / (np.linalg.norm(b - a) or 1.0)
                lines[p] = (a, u)
            else:
                lines[p] = (pts[0], np.array([1.0, 0.0]))
    widths = {}
    for p, (q, u) in lines.items():
        c = _cross(np.asarray(pcs[p]["P"], float), q, u, closed=True)
        if len(c) >= 2:
            s = [float((x[0] - q) @ u) for x in c]
            widths[p] = max(s) - min(s)
    for dt in B.get("darts") or []:  # (an open dart's gap is sewn shut: its intake isn't the garment's)
        p = dt.get("piece")
        if p in widths:
            q, u = lines[p]
            xs = [_cross(edge(*e.split(":", 1)) if ":" in e else edge(p, e), q, u, closed=False) for e in dt["legs"]]
            if all(xs):
                widths[p] -= abs(float((xs[0][0][0] - xs[1][0][0]) @ u))
    ring, lap = _ring(B, lines, widths, edge, pairs)
    for p in [p for p in widths if p not in ring]:
        widths.pop(p)
    placed = sorted(lines)
    return widths, [p for p in torso if p not in widths and p not in lines], under, lap, placed


def _ring(B: dict, lines: dict, widths: dict, edge, pairs: list) -> tuple[set, float]:
    """(the pieces the level goes ROUND, the lap to take off): torso pieces linked where the line crosses both sides
    of a seam or a closure; a piece with fewer than two links (a facing, a canvas, an interlining: it lies on another,
    its other side free) is pruned, so only the ring round the body is summed (s4-6's jacket read 1914 mm with its
    facings and canvases). Lapped closures' paired marks (buttons) give the lap: each edge to its marks' line."""
    def crosses(p, arc):
        q, u = lines[p]
        return bool(_cross(edge(p, arc), q, u, closed=False))
    link = {p: set() for p in widths}
    for pa, ea, pb, eb in pairs:
        if pa in widths and pb in widths and crosses(pa, ea) and crosses(pb, eb):
            link[pa].add(pb)
    lap = 0.0
    for c in B.get("closures") or []:
        o, un, E = c.get("over"), c.get("under"), c.get("edge") or {}
        if o in widths and un in widths and isinstance(E, dict):
            link[o].add(un)
            link[un].add(o)
            for p, arc in ((o, E.get("over")), (un, E.get("under"))):
                pc = B["pieces"][p]
                nm = [a if p == o else b for a, b in c.get("pairs") or []]
                marks = [pc["marks"][n] for n in nm if n in (pc.get("marks") or {})] + \
                    [pc["P"][pc["names"][n]] for n in nm if n not in (pc.get("marks") or {}) and n in pc.get("names", {})]
                if marks and isinstance(arc, str):
                    q, u = lines[p]
                    x = _cross(edge(p, arc), q, u, closed=False)
                    if x:
                        lap += float(np.min([abs((np.asarray(m, float) - x[0][0]) @ u) for m in marks]))
    alive = set(link)
    while True:
        drop = {p for p in alive if len(link[p] & alive) < 2}
        if not drop:
            return alive, lap
        alive -= drop


def rows(B: dict, step3: dict | None, fit: dict | None, body: dict | None) -> list:
    """Row `girths` (module docstring); INFO when there is no body or no torso girth to check."""
    from .draft_body_lengths import _ease
    rid = {"id": "girths", "back_to": "4", "target": "at each step-3 torso girth's level: the pattern round >= the body "
           f"+ step 0's fit ease (within {GIRTH_TOL:.1%}); never under the body"}
    if not body or "hps.L" not in (body.get("at") or {}):
        return [dict(rid, status="INFO", value="n/a", why="no body landmarks (hps) to place the levels")]
    hps = np.asarray(body["at"]["hps.L"], float).ravel()
    lv = []
    for m in (step3 or {}).get("measurements") or []:
        L = np.asarray(m.get("loop") or [], float)
        if L.ndim == 2 and L.shape[1] == 3 and "mm" in m and abs(L[:, 0].mean()) < 0.03 and \
                L[:, 2].mean() < hps[2] - NECK_GAP:
            lv.append((m["name"], float(m["mm"]), float(L[:, 2].mean())))
    if not lv:
        return [dict(rid, status="INFO", value="no step-3 torso girth below the neck")]
    dr = drops(np.asarray(body["V"], float), hps, [z for _, _, z in lv], body.get("T"))
    vals, fails, infos = [], [], []
    for nm, mm, z in sorted(lv, key=lambda x: -x[2]):
        D = {k: dr[k].get(z) for k in ("front", "back") if dr[k].get(z) is not None}
        if not D:
            continue
        w, miss, under, lap, lv_pieces = level(B, D)
        if not w or any(p for p in miss if str((B["pieces"][p].get("wrap") or {}).get("side", "")) in D):
            infos.append(f"{nm}: the pattern doesn't reach its level ({', '.join(miss)})" if miss else
                         f"{nm}: the level doesn't go round the body (a hem, vent or opening breaks it there; the line "
                         f"was placed on {', '.join(lv_pieces) or 'no piece'}): not checked")
            continue
        g = 1000 * (sum(w.values()) - lap)
        ease, reg = _ease(nm, fit)
        tgt = mm + ease
        txt = (f"{nm}: pattern {g:.0f} mm round = body {mm:.0f} {g - mm:+.0f}" + (f" (step 0's {reg} ease wants "
               f"{ease:+.0f}: {g - tgt:+.0f})" if reg else " (no fit ease in step 0)")
               + f" [{', '.join(f'{p} {1000 * v:.0f}' for p, v in w.items())}]" + (f"; not reached: {', '.join(miss)}" if miss else "")
               + ("; its level falls in the armhole: taken at the underarm" if under else "")
               + (f"; less the fronts' lap {1000 * lap:.0f}" if lap else ""))
        vals.append(txt)
        if g < mm:
            fails.append(f"{nm}: {g:.0f} mm round is under the body's {mm:.0f}: it can't close. change: let the "
                         f"pieces out by {tgt - g:.0f} mm in all at that level (spread over its seams)")
        elif reg and g < tgt * (1 - GIRTH_TOL):
            fails.append(f"{nm}: {g:.0f} mm round against the body {mm:.0f} + step 0's {reg} ease {ease:.0f} = "
                         f"{tgt:.0f}: {tgt - g:.0f} mm tight. change: let the pieces out by {tgt - g:.0f} mm in all at "
                         "that level (spread over its seams), or the block's ease option")
    return [dict(rid, status="FAIL" if fails else ("PASS" if vals else "INFO"), value="; ".join(vals) or "n/a",
                 why="; ".join(fails), info="; ".join(infos),
                 fix="let out or take in where the row says; a girth comes from the block's ease options or its "
                     "seams' widths at that level" if fails else "")]
