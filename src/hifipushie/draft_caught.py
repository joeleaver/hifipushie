"""Step-4 row `caught`: every piece step 1 says is caught in a seam reaches that seam, and lies on its host.

Why (trial s4-27, the suit jacket, 2026-11-15): step 1 says the chest canvas is caught in the front-edge seam and
carries the lapel; the draft's canvas stopped at the roll line, 65 mm short of the front edge, and no row checked the
claim ("canvas doesn't reach into the lapel", the trial's own fault 2). The sewn row checks the seams step 1 names
between a and b; nothing checked step 1's `caught` edges (a canvas, an interfacing sewn into a seam line with a and b).

THE CHECK, per follower piece (one with an edge caught in a step-1 seam): its HOST is the piece of those seams' sides it
shares most seams with (a canvas caught in the forepart's shoulder, armhole, neck and front seams: the forepart). The
follower is laid on its host flat by one rigid move (mirror allowed): by the outline points both pieces name alike when
they agree (a canvas drafted from the forepart's own points: their positions coincide within NAME_MM), else fitted to
its caught edges (each point to its host edge, from several starting turns). Then:
  FAIL: a caught edge lying more than TOL_MM off the host's edge it is caught in (its worst point, in mm), or not
    declared on the follower at all;
  FAIL: the follower reaching more than TOL_MM outside its host's outline (it lies on it: it can't hang past it).
Each FAIL names the edge, the seam step 1 catches it in, and how far off: redraw the follower's edge along the host's.
Lying on a host with no edge caught (a pocket bag) isn't a claim this row can measure. Nothing here knows a garment."""
from __future__ import annotations

import numpy as np

TOL_MM = 6.0  # mm: a caught edge is cut on the seam line; a drafted chest piece is often trimmed ~3-5 mm short of it
NAME_MM = 3.0  # mm: shared point names place the follower when their distances agree this well


def _seg_dist(X: np.ndarray, P: np.ndarray) -> np.ndarray:
    """Distance of each point in X to the polyline P."""
    A, Bv = P[:-1], P[1:]
    d = Bv - A
    L2 = np.maximum((d * d).sum(1), 1e-18)
    t = np.clip(((X[:, None, :] - A[None]) * d[None]).sum(2) / L2[None], 0, 1)
    Q = A[None] + t[..., None] * d[None]
    return np.linalg.norm(X[:, None, :] - Q, axis=2).min(1)


def _closest(X: np.ndarray, P: np.ndarray) -> np.ndarray:
    A, Bv = P[:-1], P[1:]
    d = Bv - A
    L2 = np.maximum((d * d).sum(1), 1e-18)
    t = np.clip(((X[:, None, :] - A[None]) * d[None]).sum(2) / L2[None], 0, 1)
    Q = A[None] + t[..., None] * d[None]
    k = np.linalg.norm(X[:, None, :] - Q, axis=2).argmin(1)
    return Q[np.arange(len(X)), k]


def rigid(X: np.ndarray, Y: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """(R, t) of the rigid move (mirror allowed) taking points X nearest to Y: Y ~ X @ R.T + t."""
    cx, cy = X.mean(0), Y.mean(0)
    U, _, Vt = np.linalg.svd((X - cx).T @ (Y - cy))
    best = None
    for D in (np.eye(2), np.diag([1.0, -1.0])):
        R = (U @ D @ Vt).T
        e = np.linalg.norm((X - cx) @ R.T + cy - Y)
        if best is None or e < best[0]:
            best = (e, R)
    R = best[1]
    return R, cy - cx @ R.T


def _icp(Xs: list, Hs: list, R: np.ndarray, t: np.ndarray, n: int = 30) -> tuple[np.ndarray, np.ndarray, float]:
    X = np.concatenate(Xs)
    for _ in range(n):
        Y = np.concatenate([_closest(x @ R.T + t, h) for x, h in zip(Xs, Hs)])
        R, t = rigid(X, Y)
    err = float(np.concatenate([_seg_dist(x @ R.T + t, h) for x, h in zip(Xs, Hs)]).mean())
    return R, t, err


def place(fol: dict, host: dict, Xs: list, Hs: list) -> tuple[np.ndarray, np.ndarray, str]:
    """(R, t, how) laying follower piece fol on host piece host (module docstring)."""
    nf, nh = fol.get("names") or {}, host.get("names") or {}
    common = sorted(set(nf) & set(nh))
    if len(common) >= 2:
        X = np.array([fol["P"][nf[k]] for k in common], float)
        Y = np.array([host["P"][nh[k]] for k in common], float)
        R, t = rigid(X, Y)
        if np.abs(np.linalg.norm(X @ R.T + t - Y, axis=1)).max() * 1000 <= NAME_MM:
            return R, t, f"by the points both name ({', '.join(common[:6])})"
    best = None
    X = np.concatenate(Xs)
    Y = np.concatenate(Hs)
    for a in np.radians(np.arange(0, 360, 45)):
        for m in (1.0, -1.0):
            R0 = np.array([[np.cos(a), -np.sin(a)], [np.sin(a), np.cos(a)]]) @ np.diag([1.0, m])
            t0 = Y.mean(0) - X.mean(0) @ R0.T
            R, t, e = _icp(Xs, Hs, R0, t0)
            if best is None or e < best[2]:
                best = (R, t, e)
    return best[0], best[1], "fitted to its caught edges (no points named alike)"


def _edge_pts(B: dict, p: str, e: str) -> np.ndarray | None:
    """The outline points of piece p's declared edge e (a split edge e.1, e.2 ... joined), or None."""
    from .draft_girths import _edge
    arcs = (B.get("edge_arcs") or {}).get(p) or {}
    if e in arcs:
        v = arcs[e]
    else:
        v = [arcs[k] for k in sorted(arcs) if k.startswith(e + ".") and k[len(e) + 1:].isdigit()]
        if not v:
            return None
    try:
        return _edge(B["pieces"], p, v)
    except (KeyError, ValueError, IndexError):
        return None


def _inside(X: np.ndarray, P: np.ndarray) -> np.ndarray:
    x, y = X[:, 0][:, None], X[:, 1][:, None]
    a, b = P, np.roll(P, -1, axis=0)
    c = ((a[:, 1] > y) != (b[:, 1] > y)) & (x < (b[:, 0] - a[:, 0]) * (y - a[:, 1]) / (b[:, 1] - a[:, 1] + 1e-18) + a[:, 0])
    return c.sum(1) % 2 == 1


def row(B: dict, step1: dict) -> dict | None:
    """Row `caught` (module docstring); None when step 1 catches nothing in a drafted seam."""
    pcs = B["pieces"]
    claims = {}  # follower -> [(its edge, seam text, (side piece, side edge) ...)]
    for s in step1.get("seams") or []:
        sides = [str(s.get(k, "")).split(":", 1) for k in ("a", "b")]
        for c in s.get("caught") or []:
            fp, fe = str(c).split(":", 1) if ":" in str(c) else (str(c), "")
            if fp in pcs:
                claims.setdefault(fp, []).append((fe, f"{s.get('a')} = {s.get('b')}", [x for x in sides if len(x) == 2]))
    if not claims:
        return None
    why, vals = [], []
    for fp, cl in sorted(claims.items()):
        count = {}
        for _, _, sides in cl:
            for hp, _ in sides:
                count[hp] = count.get(hp, 0) + 1
        hosts = [h for h in sorted(count, key=lambda h: -count[h]) if h in pcs]
        if not hosts:
            continue
        hp = hosts[0]
        use = []
        for fe, txt, sides in cl:
            X = _edge_pts(B, fp, fe)
            he = next((e for p, e in sides if p == hp), None)
            H = _edge_pts(B, hp, he) if he else None
            if X is None:
                why.append(f"{fp}:{fe} (step 1: caught in {txt}) is not a declared edge of {fp}: declare it on the "
                           "follower, along the seam it is caught in")
            elif H is not None:
                use.append((fe, txt, X, H, he))
        if not use:
            continue
        R, t, how = place(pcs[fp], pcs[hp], [u[2] for u in use], [u[3] for u in use])
        offs = []
        for fe, txt, X, H, he in use:
            d = 1000 * float(_seg_dist(X @ R.T + t, H).max())
            offs.append(f"{fe} {d:.0f}")
            if d > TOL_MM:
                why.append(f"{fp}:{fe} lies up to {d:.0f} mm off {hp}:{he}, the edge step 1 catches it in ({txt}): "
                           f"redraw {fp}'s {fe} along {hp}'s {he} (from its points), so it reaches that seam")
        P = np.asarray(pcs[fp]["P"], float) @ R.T + t
        Hp = np.asarray(pcs[hp]["P"], float)
        out = ~_inside(P, Hp)
        far = 1000 * float(_seg_dist(P[out], np.r_[Hp, Hp[:1]]).max()) if out.any() else 0.0
        if far > TOL_MM:
            why.append(f"{fp} reaches {far:.0f} mm outside {hp}, the piece it lies on: trim it to {hp}'s outline")
        vals.append(f"{fp} on {hp} ({how}): caught edges off by " + ", ".join(offs) + f" mm; outside {far:.0f} mm")
    return {"id": "caught", "status": "FAIL" if why else "PASS", "value": "; ".join(vals) or "no follower drafted",
            "target": f"every edge step 1 catches in a seam lies on that seam's edge (within {TOL_MM:.0f} mm), the "
                      "follower inside the piece it lies on", "why": "; ".join(why[:8]), "back_to": "4",
            "fix": "redraw the follower (canvas, interfacing) from its host's own points out to each seam step 1 "
                   "catches it in" if why else ""}
