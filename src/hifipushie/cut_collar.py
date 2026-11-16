"""garment_cut's COLLAR, the tailor's way (R2 / R2b's lofted collars were saddles whose fall edge was no longer than their
roll line: C490-C491): drafted FLAT first, as a pattern maker drafts it, then fitted round the toile's neck by the
stiff-piece chain route (chain_net.project: every link of the flat at its exact length, only bends free).

THE DRAFT (one piece symmetric about CB, s along the neck edge from CB): its neck edge = the garment's neck line, the
declared neck edges' flat lengths (the front's from the gorge / notch, the back's to CB): N per half; its width w(s) =
stand + fall at CB and behind the shoulder, tapering in front to the collar end's length; its roll line at the stand's
height h(s) (stand behind the shoulder, tapering in front to H_MIN: the collar turns with the lapel there). Its OUTER
(fall) edge is longer than its neck edge by what the fall needs to lie out over the shoulders: draft_fall's rule (the
neck line walked at depth d = fall - stand into each back piece's flat, a front's neck edge at its own length, plus the
cloth's lift), so shape_fall_landing measures what was drafted. The neck edge is a circular arc of the curvature that
gives that outer length (a crescent: never a band, never a saddle); the outer edge its offset by w(s).
THE PIECES: each declared collar piece (an undercollar, a top collar) gets this outline; its neck-side edges are named by
step 1: the edge sewn to the garment's neck edge, or to a layer cut from it (a facing's gorge), or caught in that seam
(a top collar's stand in the back neck seam); ".L" names serve the ".R" half.
THE FIT: the neck row held on the toile's neckline (the garment's neck edges in 3D, from the notch round to CB), the
stand rising square to it, the fall turned down outward over it; then project() until every length holds (the neck row's
own links at most their flat length), the fall kept off the toile (chain_net.Contact). Rows: lengths (worst %), where the
outer edge lands below the neck seam at CB against d, the fall's clearance off the toile, the flat's span and bow.

THE DECLARATION (garment_cut's `collar`): {"pieces": [collar pieces], "neck": [garment neck edges of the left half from
the front end to CB], "stand_mm", "fall_mm" (at CB), "end_mm" (the collar end), "outer": edge name, "end": edge name
(".L"), "fold": step 2's roll fold name, "fold_on": the piece step 2 turns it on}. Nothing here knows a garment."""
from __future__ import annotations

import re

import numpy as np

H_MIN = 0.010    # m: the stand at the collar end (the roll line meets the end ~1 cm above the gorge corner)
NS, KS, KF = 40, 3, 5  # columns per half, stand rows, fall rows
GAP = 0.003      # m: the fall turns over the stand this far out (the cloth's thickness)
NECK_R = 0.006   # m: a neck point may sit this far from its place on the toile's neck line (the flatten's own mismatch)
SPREAD_ROUNDS = 4  # drafts at most: the outer edge lengthened by what the fit stretched it, until it lies
SPREAD_TOL = 0.002  # the fitted outer edge within this of its flat length: it lies as drafted
CONTACT = True   # the fall kept GAP off the toile while it is fitted
ITERS = 400      # project() passes (each moves the worst point at most 2 cm)


class CollarRefused(ValueError):
    """A collar declaration the garment can't answer (named)."""


def mirror(e: str) -> str:
    return re.sub(r"\.L$", ".R", e) if e.endswith(".L") else re.sub(r"\.L:", ".R:", e)


def neck_edge(c: str, g: str, s1: dict, layers: dict) -> str | None:
    """The edge of collar piece c sewn to garment edge g (or to a layer cut from g's piece, or caught in g's seam)."""
    gp, ge = g.split(":", 1)
    via = {f"{lay}:{(d.get('edges') or {}).get(ge, ge)}" for lay, d in layers.items() if d.get("host") == gp}
    for s in s1.get("seams") or []:
        for mine, other in ((s["a"], s["b"]), (s["b"], s["a"])):
            if mine.split(":")[0] == c and (other == g or other in via):
                return mine.split(":", 1)[1]
    for s in s1.get("seams") or []:
        if g in (s["a"], s["b"]):
            for x in s.get("caught") or []:
                if x.split(":")[0] == c:
                    return x.split(":", 1)[1]
    return None


def outer_target(necks: list, d: float, decl: dict, s1: dict) -> float:
    """Half the outer edge's length by draft_fall's rule: [(piece, flat outline P, edge points E)] of one half."""
    from . import draft_fall, draft_shape, pattern
    line = 0.0
    for p, P, E in necks:
        front = draft_shape._role(p, decl, s1) in draft_shape.LAPEL_ROLES
        line += pattern.length(E) if front else draft_fall.offset_length(E, P, d)
    return line + np.pi * draft_fall.LIFT


def _pt(s, w, k):
    if abs(k) < 1e-9:
        return np.c_[s, w]
    R = 1 / k
    return np.c_[(R + w) * np.sin(s / R), (R + w) * np.cos(s / R) - R]


def draft(Lb: float, Lf: float, W: float, stand: float, end: float, O_half: float):
    """(U (rows x cols, 2) flat grid, s per column, h, w, curvature): the crescent whose outer edge is O_half per half."""
    N = Lb + Lf
    s = np.r_[np.linspace(-N, -Lb, NS // 2, endpoint=False), np.linspace(-Lb, Lb, NS, endpoint=False),
              np.linspace(Lb, N, NS // 2 + 1)]
    a = np.abs(s)
    tf = np.clip((a - Lb) / max(Lf, 1e-9), 0, 1)
    w = W + (end - W) * tf
    h = stand + (H_MIN - stand) * tf
    half = s >= 0

    def outer_len(k):
        Q = _pt(s[half], w[half], k)
        return float(np.linalg.norm(np.diff(Q, axis=0), axis=1).sum())
    lo, hi = 0.0, 2.6 / N
    if outer_len(lo) >= O_half:
        k = 0.0
    else:
        for _ in range(60):
            k = 0.5 * (lo + hi)
            lo, hi = (k, hi) if outer_len(k) < O_half else (lo, k)
    rows = []
    for r in range(KS + KF + 1):
        fr = (r / KS) * h if r <= KS else h + (r - KS) / KF * (w - h)
        rows.append(_pt(s, fr, k))
    return np.stack(rows), s, h, w, k


def grid_faces(nr, nc):
    F = []
    for r in range(nr - 1):
        for c in range(nc - 1):
            a, b, cc, d = r * nc + c, r * nc + c + 1, (r + 1) * nc + c + 1, (r + 1) * nc + c
            F += [[a, b, cc], [a, cc, d]]
    return np.array(F)


def grid_loop(nr, nc):
    return ([c for c in range(nc)] + [r * nc + nc - 1 for r in range(1, nr)] +
            [(nr - 1) * nc + c for c in range(nc - 2, -1, -1)] + [r * nc for r in range(nr - 2, 0, -1)])


def curve3d(polys):
    """The neck line from the front end to CB: [(n, 3) polylines], each oriented to follow the one before."""
    out = [np.asarray(polys[0], float)]
    for P in polys[1:]:
        P = np.asarray(P, float)
        if len(out) == 1:
            ends = [(np.linalg.norm(out[0][i] - P[j]), i, j) for i in (0, -1) for j in (0, -1)]
            _, i, j = min(ends)
            if i == 0:
                out[0] = out[0][::-1]
            out.append(P if j == 0 else P[::-1])
        else:
            out.append(P if np.linalg.norm(out[-1][-1] - P[0]) < np.linalg.norm(out[-1][-1] - P[-1]) else P[::-1])
    return out


def at_len(P, frac):
    s = np.r_[0, np.cumsum(np.linalg.norm(np.diff(P, axis=0), axis=1))]
    t = np.clip(frac, 0, 1) * s[-1]
    return np.c_[[np.interp(t, s, P[:, k]) for k in range(3)]].T


def place(U, s, h, w, front3, back3, Lb, Lf, toile):
    """3D start: the neck row on the toile's neck line, the stand up, the fall down outward; then project()."""
    from .chain_net import Contact, project
    nr, nc = U.shape[:2]
    half = {}
    for sg, (fr, bk) in ((1, (front3[0], back3[0])), (-1, (front3[1], back3[1]))):
        f_, b_ = curve3d([fr, bk])  # front end -> shoulder, shoulder -> CB
        half[sg] = (f_, b_)
    Q = np.zeros((nc, 3))
    for c in range(nc):
        f_, b_ = half[1 if s[c] >= 0 else -1]
        a = abs(s[c])
        Q[c] = at_len(b_[::-1], a / Lb)[0] if a <= Lb else at_len(f_[::-1], (a - Lb) / Lf)[0]
    cen = Q.mean(0)
    T = np.gradient(Q, axis=0)
    T /= np.linalg.norm(T, axis=1, keepdims=True) + 1e-12
    up = np.array([0, 0, 1.0]) - (T @ [0, 0, 1.0])[:, None] * T
    up /= np.linalg.norm(up, axis=1, keepdims=True)
    out = np.cross(T, up)
    hz = Q - cen
    hz[:, 2] = 0
    out *= np.sign((out * hz).sum(1))[:, None]
    down = -up + 0.3 * out
    down /= np.linalg.norm(down, axis=1, keepdims=True)
    X = np.zeros((nr, nc, 3))
    for r in range(nr):
        if r <= KS:
            X[r] = Q + ((r / KS) * h)[:, None] * up
        else:
            X[r] = Q + h[:, None] * up + GAP * out + (((r - KS) / KF) * (w - h))[:, None] * down
    X = X.reshape(-1, 3)
    Uf = U.reshape(-1, 2)
    F = grid_faces(nr, nc)
    E = np.unique(np.sort(np.r_[F[:, [0, 1]], F[:, [1, 2]], F[:, [0, 2]]], axis=1), axis=0)
    L = np.linalg.norm(Uf[E[:, 0]] - Uf[E[:, 1]], axis=1)
    cb = int(np.argmin(np.abs(s)))
    exact = np.ones(len(E), bool)
    held = np.zeros(len(X), bool)
    held[cb] = True  # (CB on the toile's neck; every other neck point within NECK_R of its place on the neck line)
    lim = [(c, Q[c], NECK_R) for c in range(nc) if c != cb]
    ct = Contact(*toile)
    far = toile[0].mean(0) + np.array([0, -1.0, 0])
    if ct.query(far[None])[0][0] < 0:
        ct = Contact(*toile, side=-1.0)
    fall = np.arange((KS + 1) * nc, nr * nc)
    X, read = project(X, E[:, 0], E[:, 1], L, exact, held=held, contacts=[(ct, fall, GAP)] if CONTACT else (), iters=ITERS,
                      limit=lim)
    off = np.abs(np.linalg.norm(X[E[:, 0]] - X[E[:, 1]], axis=1) - L)[exact]
    nk = lambda Z: float(np.linalg.norm(np.diff(Z, axis=0), axis=1).sum()) * 500  # (mm per half)
    wk = int(np.argmax(np.where(exact, np.abs(np.linalg.norm(X[E[:, 0]] - X[E[:, 1]], axis=1) - L), 0)))
    read = dict(read, worst_at=np.round(0.5 * (X[E[wk, 0]] + X[E[wk, 1]]), 3).tolist(), neck_3d_half_mm=round(nk(Q), 1), neck_fit_half_mm=round(nk(X[:nc]), 1), worst_mm=round(float(off.max()) * 1000, 2),
                worst_pct_5mm=round(float((off / L[exact])[L[exact] > 0.005].max()) * 100, 3))
    return X, F, E, L, exact, read, ct, Q


def build(pcs: dict, edges: dict, d: dict, s1: dict, layers: dict, toile):
    """({piece: f}, {piece: edges}, folds, report, bad): the collar pieces drafted, named and fitted (module doc)."""
    for k in ("pieces", "neck", "stand_mm", "fall_mm", "end_mm", "outer", "end"):
        if k not in d:
            raise CollarRefused(f"collar: needs {k!r} (module doc)")
    necks, polys3 = [], {}
    for g in d["neck"]:
        p, e = g.split(":", 1)
        for gg in (g, mirror(g)):
            pp, ee = gg.split(":", 1)
            if pp not in pcs or ee not in edges.get(pp, {}):
                raise CollarRefused(f"collar: neck edge {gg!r} is not a cut edge")
            f = pcs[pp]
            idx = edges[pp][ee]
            pos = list(idx) + [(idx[-1] + 1) % len(f["lp"])]
            lp = np.asarray(f["lp"])[pos]
            polys3[gg] = f["V"][lp]
            if gg == g:
                necks.append((p, f["U"][np.asarray(f["lp"])], f["U"][lp]))
    from . import pattern
    lens = [pattern.length(E) for _, _, E in necks]
    Lf, Lb = sum(lens[:-1]), lens[-1]
    stand, fall, end = (float(d[k]) / 1000 for k in ("stand_mm", "fall_mm", "end_mm"))
    if fall <= stand:
        raise CollarRefused(f"collar: fall {fall * 1000:.0f} mm is no deeper than the stand {stand * 1000:.0f} mm")
    O_rule = O_half = outer_target(necks, fall - stand, {"pieces": {}}, s1)
    front3 = (np.concatenate([polys3[g] for g in d["neck"][:-1]]), np.concatenate([polys3[mirror(g)] for g in d["neck"][:-1]]))
    back3 = (polys3[d["neck"][-1]], polys3[mirror(d["neck"][-1])])
    spread = []
    for _ in range(SPREAD_ROUNDS):  # (the pattern maker's second look: lay it on, spread the fall where it pulls)
        U, s, h, w, k = draft(Lb, Lf, stand + fall, stand, end, O_half)
        nr, nc = U.shape[:2]
        X, F, E, L, exact, read, ct, Q = place(U, s, h, w, front3, back3, Lb, Lf, toile)
        o_fit = float(np.linalg.norm(np.diff(X.reshape(nr, nc, 3)[-1], axis=0), axis=1).sum())
        o_flat = float(np.linalg.norm(np.diff(U[-1], axis=0), axis=1).sum())
        spread.append(round(o_fit / o_flat, 4))
        if o_fit <= o_flat * (1 + SPREAD_TOL):
            break
        O_half *= o_fit / o_flat
    loop = np.asarray(grid_loop(nr, nc))
    Uf = U.reshape(-1, 2)
    out_pcs, out_edges, bad = {}, {}, []
    for c in d["pieces"]:
        names = [neck_edge(c, g, s1, layers) for g in d["neck"]]
        if None in names:
            bad.append(f"collar: {c} has no edge sewn to (or caught in) {d['neck'][names.index(None)]} in step 1")
            continue
        keys = []
        for i in range(len(loop)):
            a, b = loop[i], loop[(i + 1) % len(loop)]
            ra, ca, rb, cb = a // nc, a % nc, b // nc, b % nc
            if ra == 0 and rb == 0:
                sm = 0.5 * (abs(s[ca]) + abs(s[cb]))
                e = names[-1] if sm <= Lb else names[0]
                keys.append(e if s[ca] + s[cb] > 0 else mirror(e))
            elif ra == nr - 1 and rb == nr - 1:
                keys.append(d["outer"])
            else:
                keys.append(d["end"] if ca == nc - 1 else mirror(d["end"]))
        from .cut import _group
        out_edges[c] = {key: idx for key, idx in _group(keys)}
        out_pcs[c] = {"name": c, "U": Uf, "F": F, "V": X, "bad": np.zeros(len(F)), "lp": loop, "loop": list(loop),
                      "rep": {"faces": int(len(F)), "strain_mean_pct": 0.0, "area_over_2pct": 0.0, "drafted": True}}
    roll = U[KS]
    folds = [{"name": d["fold"], "piece": d.get("fold_on") or d["pieces"][-1], "line": roll.tolist(), "kind": "roll"}] \
        if d.get("fold") else []
    o3 = X.reshape(nr, nc, 3)[-1]
    cb = int(np.argmin(np.abs(s)))
    sd = ct.query(X[(KS + 1) * nc:])[0]
    chord = U[0, -1] - U[0, 0]
    cu, dv = chord / np.linalg.norm(chord), U[0] - U[0, 0]
    bow = float(np.abs(cu[0] * dv[:, 1] - cu[1] * dv[:, 0]).max())
    rep = {"neck_mm": {"front": round(Lf * 1000, 1), "back": round(Lb * 1000, 1), "half": round((Lf + Lb) * 1000, 1)},
           "outer_half_mm": round(O_half * 1000, 1), "outer_rule_half_mm": round(O_rule * 1000, 1),
           "spread_rounds": spread, "outer_over_neck": round(O_half / (Lf + Lb), 3),
           "curvature_per_m": round(k, 3),
           "flat_span_mm": [round(float(np.ptp(Uf[:, 0])) * 1000, 1), round(float(np.ptp(Uf[:, 1])) * 1000, 1)],
           "neck_bow_mm": round(bow * 1000, 1),
           "lengths": read,
           "outer_3d_mm": round(float(np.linalg.norm(np.diff(o3, axis=0), axis=1).sum()) * 1000, 1),
           "outer_flat_mm": round(float(np.linalg.norm(np.diff(U[-1], axis=0), axis=1).sum()) * 1000, 1),
           "lands_below_neck_cb_mm": round(float(Q[cb, 2] - o3[cb, 2]) * 1000, 1), "d_mm": round((fall - stand) * 1000, 1),
           "fall_clear_min_mm": round(float(sd.min()) * 1000, 1)}
    return out_pcs, out_edges, folds, rep, bad
