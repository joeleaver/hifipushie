"""OUTLINE vs REFERENCE (tooling run T15, C299): the garment's edges as the reference draws them, compared in mm.

Why (Joe 2026-11-02, on the hussar): "It still doesn't have any of these curves right": the stand collar and the stepped
cutaway notch. The structure rows measure lengths and ratios (cutaway_drop, collar_height), and a ratio can't tell an
arc from a square step: any shape that hits the numbers passed. Here the reference's key edges are TRACED (step 2) and
the build's matching outline, seen from the same view, is compared with them point by point.

STEP 2 (garment_plan "style"): `traces` + `body_marks`.
  traces     [{id, what (a KINDS key), view (step-0 view index), points [[u,v],..] (image pixels, u right, v down; >=
              MIN_POINTS, inside the image, in order along the edge), corners [indices of points where the edge turns
              sharply: they must stay corners], source}]
  body_marks [{view, at: {landmark: [u,v]}, source}]  landmarks = MARKS (the body's own, .R mirrors .L; a "_z" height
              takes v only). They place the photo's figure on the body: u = u0 + a/s, v = v0 + b/s (a, b mm in the
              view plane). The scale s (mm per px) is fit from the marks (least squares; two marks > 50 mm apart): the
              BODY is the ruler, since the build is compared on it; step 0's view `scale` (a guess at the real garment's
              size) only places a view with one mark, and is reported beside the fit when it disagrees by > SCALE_AGREE.
              Which was used is said in every row, with the marks' own residual.
STEP 6 (chain_structure.check, rows "outline:<id>"): the build projected orthographically along the view (front: from
  -Y, a = x; back: from +Y, a = -x; side: from +X, a = y; b = -z). The matching edge is found from the trace's `what`:
  KINDS names the pieces (by role) whose BORDER (the mesh's free edges: hem, front edges, a collar's top...) can make it,
  only those facing the camera where the kind says so; of those border loops the points whose nearest place on the trace
  is a perpendicular foot inside a segment (not past an end or a corner's wedge: a side seam or CF edge rising from the
  hem is another edge), running within TANGENT_DEG of the trace there and within CAP_X tolerances are the built outline. Compared both ways (trace -> built, built ->
  trace): p95 and max in mm, placed by the body, and its SHAPE after the best shift (the shift reported: a garment set
  too long / short is a pattern length, not a shape); the worst place (the trace point, in px and along the trace, the
  build's piece and the pattern edge there: step 4's declarations); each traced corner: the build turns >= CORNER_KEEP of
  the traced turn within one tolerance of it (both turns over the same window).
TARGETS (named, never tuned): tol = TRACE_PX * mm_per_px (how well a traced line sits on a photo's edge) + the build's
  border edge length (the outline can't be finer than its mesh): shape p95 <= tol, max <= 2 tol; |shift| <= SHIFT_X tol
  + the marks' own residual. A FAIL backs to step 4 (the pattern edge that makes that outline is redrawn).
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

KINDS = {  # the ONE vocabulary of traced edges (garment_plan validates against it); roles: garment_kb roles
    "hem": dict(roles=("front", "back", "panel", "side", "skirt", "drape", "cape", "cloak"), facing=True,
                desc="the bottom edge of the body pieces facing the view (a cutaway, a notch, tails included)"),
    "front_edge": dict(roles=("front",), facing=True, desc="the fronts' closure edges (CF, a lapel's edge)"),
    "collar_top": dict(roles=("collar_stand", "collar_fall", "collar", "neckband"), facing=False,
                       desc="a collar's free (top / outer) edge as seen, its front ends included"),
    "collar_front": dict(roles=("collar_stand", "collar_fall", "collar", "neckband"), facing=False,
                         desc="a collar's front ends (the edge from its top corner down to the neckline)"),
    "neckline": dict(roles=("front", "back", "yoke"), facing=True, desc="the body pieces' neck edge where no collar hides it"),
    "sleeve_end": dict(roles=("sleeve", "cuff"), facing=True, desc="a sleeve's or cuff's end edge"),
    "outline": dict(roles=None, facing=False, desc="any free edge of the garment as seen (every piece)"),
    "roll_line": dict(roles=("front", "facing", "collar", "collar_fall"), facing=True,
                      unmeasured="a fold line: the build's folds aren't compared with traces yet (C351)",
                      desc="a fold where cloth turns back on itself as worn (a lapel's roll line, a turned-back cuff's "
                           "fold): its course, from its top to where it ends (the break) as the trace's first and last "
                           "points (corners are only turns between them); not a free edge, so step 6 reports it "
                           "UNMEASURED until fold lines are compared (C351, C352)"),
    "trim": dict(roles=None, facing=True,
                 unmeasured="a trim's course: compared once the details are built (step 7), not on the bare build",
                 desc="a trim's course as seen (braid, piping, a cuff's chevron, a shoulder strap's outline): name the "
                      "detail in source; step 6 reports it UNMEASURED, the details' step judges it (C353)"),
}
MARKS = ("hps", "shoulder", "neck_side", "bust", "elbow", "wrist", "cf_neck", "cb_neck", "armpit_z", "chest_z", "waist_z",
         "high_hip_z", "hips_z", "seat_z", "crotch_z")
MIN_POINTS = 4
TRACE_PX = 3.0      # px: a traced line sits within ~3 px of a photo's edge (its anti-aliased blur + the tracer's hand)
TANGENT_DEG = 60.0  # a built edge crossing the trace steeper than this is another edge meeting it (a CF edge off a hem)
CAP_X = 3.0         # built points farther than max(trace->built max, CAP_X tol) from the trace are another edge
SHIFT_X = 2.0       # the outline placed by the body within SHIFT_X tol + the marks' residual (else: lengths / placing)
CORNER_KEEP = 0.5   # a traced corner is kept when the build turns >= half the traced turn within one tol of it
EDGE_NEAR_M = 0.015  # a place farther than this from every declared edge on the flat is named by the draft's points
SCALE_AGREE = 0.05  # the step-0 scale and the body marks' own fit disagreeing by more: said in the row (placing unsure)
CORNER_MIN_DEG = 30.0  # a listed corner turning less than this in the trace is not a corner (said, not judged)
VIEW_AXES = {"front": ((0, 1.0), None), "back": ((0, -1.0), None), "side": ((1, 1.0), None)}  # (a = sign * X[axis])


def _num(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and np.isfinite(x)


def _image_size(path) -> tuple | None:
    try:
        from PIL import Image
        with Image.open(path) as im:
            return im.size
    except Exception:  # noqa: BLE001
        return None


def vocabulary() -> str:
    return "; ".join(f"{k}: {v['desc']}" for k, v in KINDS.items())


def mark_names() -> list:
    return [m for m in MARKS if m.endswith("_z") or m in ("cf_neck", "cb_neck")] + \
        [f"{m}.{s}" for m in MARKS if not m.endswith("_z") and m not in ("cf_neck", "cb_neck") for s in "LR"]


# ---------------------------------------------------------------- step 2: validation
def check_plan(p: dict, read: dict, bad: list) -> None:
    """Refuse bad traces / body marks BY NAME into `bad` (garment_plan.check_style)."""
    views = read.get("views") or []
    tr, bm = p.get("traces"), p.get("body_marks")
    if not tr:  # (C351: t s2-1 wrote a plan with no traces; they are how step 6 judges the curves)
        bad.append("traces: required: the reference's key edges traced on a view, [{id, what, view, points [[u,v],..], "
                   f"corners [indices], source}}]; what: {', '.join(KINDS)}")
        return
    if not isinstance(tr, list):
        bad.append("traces: [{id, what, view, points [[u,v],..], corners [indices], source}]")
        return
    ids, need = [t.get("id") for t in tr if isinstance(t, dict)], set()
    for i, t in enumerate(tr):
        w = f"traces[{i}] {t.get('id', '') if isinstance(t, dict) else ''}".strip()
        if not isinstance(t, dict):
            bad.append(f"{w}: an object {{id, what, view, points, corners, source}}")
            continue
        if not t.get("id") or ids.count(t["id"]) > 1:
            bad.append(f"{w}: a unique id")
        if t.get("what") not in KINDS:
            bad.append(f"{w}.what {t.get('what')!r}: one of {', '.join(KINDS)} ({'; '.join(f'{k}: {v['desc']}' for k, v in KINDS.items())})")
        vi = t.get("view", 0)
        if not isinstance(vi, int) or not 0 <= vi < len(views):
            bad.append(f"{w}.view {vi!r}: a step-0 view index (0..{len(views) - 1})")
            continue
        if views[vi].get("view") not in VIEW_AXES:
            bad.append(f"{w}.view {vi}: a {views[vi].get('view')!r} view; traces are compared on {', '.join(VIEW_AXES)} views")
        need.add(vi)
        pts = t.get("points")
        if not (isinstance(pts, list) and len(pts) >= MIN_POINTS and all(
                isinstance(q, (list, tuple)) and len(q) == 2 and all(map(_num, q)) for q in pts)):
            bad.append(f"{w}.points: at least {MIN_POINTS} [u, v] pixel points in order along the edge")
            continue
        size = _image_size(views[vi].get("image"))
        if size and any(not (0 <= u < size[0] and 0 <= v < size[1]) for u, v in pts):
            bad.append(f"{w}.points: outside the image ({size[0]} x {size[1]} px)")
        c = t.get("corners", [])
        if not isinstance(c, list) or any(not isinstance(k, int) or not 0 < k < len(pts) - 1 for k in c):
            bad.append(f"{w}.corners: indices of interior points (1..{len(pts) - 2}) where the edge turns sharply")
        if not str(t.get("source") or "").strip():
            bad.append(f"{w}: no source (the view and what edge was traced there)")
    have = {}
    for i, m in enumerate(bm or []):
        w = f"body_marks[{i}]"
        if not isinstance(m, dict) or not isinstance(m.get("view", 0), int) or not isinstance(m.get("at"), dict):
            bad.append(f"{w}: {{view, at: {{landmark: [u, v]}}, source}}")
            continue
        unk = [k for k in m["at"] if k not in mark_names()]
        if unk:
            bad.append(f"{w}.at: unknown landmark(s) {', '.join(unk)} (have {', '.join(mark_names())})")
        if any(not (isinstance(q, (list, tuple)) and len(q) == 2 and _num(q[0]) and (_num(q[1]) or q[1] is None)) for q in m["at"].values()):
            bad.append(f"{w}.at: each landmark at [u, v] pixels (a point landmark's v may be null: its u only)")
        if not str(m.get("source") or "").strip():
            bad.append(f"{w}: no source")
        have.setdefault(m.get("view", 0), {}).update(m["at"])
    for vi in sorted(need):
        n, scaled = len(have.get(vi, {})), bool((views[vi].get("scale") or {}).get("mm_per_px"))
        if n < (1 if scaled else 2):
            bad.append(f"body_marks: view {vi} needs {'one landmark (its scale is given)' if scaled else 'two landmarks apart (no scale given)'} "
                       f"to place the photo's figure on the body ({', '.join(mark_names())})")


# ---------------------------------------------------------------- placing the photo on the body
def _mark_mm(at: dict, name: str, view: str):
    """(a, b) mm of a landmark in the view plane; a height (_z) gives (None, b)."""
    if name.endswith("_z"):
        return None, -float(np.asarray(at[name]).ravel()[-1]) * 1000
    base, side = (name.rsplit(".", 1) + [""])[:2] if "." in name else (name, "")
    p = np.asarray(at[f"{base}.L"] if side else at[name], float).copy()
    if side == "R":
        p[0] = -p[0]
    return project(p[None], view)[0]


def project(X, view: str) -> np.ndarray:
    (ax, sg), _ = VIEW_AXES[view]
    X = np.asarray(X, float)
    return np.c_[sg * X[:, ax] * 1000, -X[:, 2] * 1000]


def placement(view: dict, marks: dict, at: dict) -> dict:
    """{s (mm/px), u0, v0, how, residual_mm}: the photo's figure placed on the body by the marks."""
    rows = []  # (pixel, index 0 u / 1 v, mm)
    for k, (u, v) in marks.items():  # (F9: a point mark's v may be null: its u only, a figure whose heights differ)
        a, b = _mark_mm(at, k, view["view"])
        if a is not None and u is not None:
            rows.append((u, 0, a))
        if v is not None:
            rows.append((v, 1, b))
    given = (view.get("scale") or {}).get("mm_per_px")
    A = np.array([[1.0 if i == 0 else 0.0, 1.0 if i == 1 else 0.0, mm] for _, i, mm in rows])
    y = np.array([px for px, _, _ in rows])
    spread = any(np.ptp([mm for _, i, mm in rows if i == ax] or [0]) > 50 for ax in (0, 1))
    fit = np.linalg.lstsq(A, y, rcond=None)[0] if spread and len(rows) >= 3 else None
    if fit is not None and fit[2] > 0:  # (the BODY is the ruler: the build is compared on it)
        u0, v0, k = fit
        how = f"scale fit from the body marks {', '.join(marks)}"
    elif given:
        k = 1.0 / float(given)
        u0, v0 = np.linalg.lstsq(A[:, :2], y - k * A[:, 2], rcond=None)[0]
        how = (f"scale {given} mm/px from step 0 ({(view.get('scale') or {}).get('from', '')}); placed by "
               f"{', '.join(marks)} (too few marks apart to fit a scale)")
    else:
        raise ValueError("the body marks don't fit a scale (two landmarks > 50 mm apart, or step 0's view scale)")
    if k <= 0:
        raise ValueError("body marks give a negative scale: marks on the wrong sides")
    res = (A[:, :2] @ [u0, v0] + k * A[:, 2] - y) / k
    out = dict(s=1.0 / k, u0=float(u0), v0=float(v0), how=how, residual_mm=round(float(np.sqrt(np.mean(res ** 2))), 1))
    if given and fit is not None:
        out["step0_mm_per_px"] = float(given)
    return out


def to_mm(pts_px, pl: dict) -> np.ndarray:
    P = np.asarray(pts_px, float)
    return np.c_[(P[:, 0] - pl["u0"]) * pl["s"], (P[:, 1] - pl["v0"]) * pl["s"]]


def to_px(P_mm, pl: dict) -> np.ndarray:
    P = np.asarray(P_mm, float)
    return np.c_[pl["u0"] + P[:, 0] / pl["s"], pl["v0"] + P[:, 1] / pl["s"]]


# ---------------------------------------------------------------- the build's outline
def border_loops(M, pieces: list) -> list:
    """[(piece index, [vertex ids in order])]: each piece's free-edge loops (edges used by one face)."""
    F = np.asarray(M["F"])
    pid = np.asarray(M["piece"])
    if F.shape[1] == 4:  # (quads: as two triangles' outer edges)
        E = np.r_[F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 3]], F[:, [3, 0]]]
    else:
        E = np.r_[F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]]
    key = np.sort(E, 1)
    u, inv, cnt = np.unique(key, axis=0, return_inverse=True, return_counts=True)
    B = u[cnt == 1]
    out = []
    for k in pieces:
        Bk = B[pid[B[:, 0]] == k]
        nb = {}
        for a, b in Bk:
            nb.setdefault(int(a), []).append(int(b))
            nb.setdefault(int(b), []).append(int(a))
        seen = set()
        for s in nb:
            if s in seen:
                continue
            loop, prev, cur = [s], None, s
            seen.add(s)
            while True:
                nxt = [n for n in nb[cur] if n != prev and n not in seen]
                if not nxt:
                    break
                prev, cur = cur, nxt[0]
                seen.add(cur)
                loop.append(cur)
            if len(loop) > 2:
                out.append((k, loop))
    return out


def matching_pieces(M, what: str, view: str, X) -> list:
    from .garment_reads import _roles
    rr = _roles(M)
    k = KINDS[what]
    ks = [i for i, r in enumerate(rr) if k["roles"] is None or r in k["roles"]]
    if k["facing"]:
        pid, Xa = np.asarray(M["piece"]), np.asarray(X, float)
        sgn, ax = {"front": (-1, 1), "back": (1, 1), "side": (1, 0)}[view]  # (the camera's side of the garment)
        mid = float(np.median(Xa[:, ax])) if view != "side" else 0.0
        ks = [i for i in ks if sgn * (Xa[pid == i, ax].mean() - mid) > 0]
    return ks


def _foot(P, T):
    """For each point P: (distance to the polyline T, segment index, t in [0,1], interior: a perpendicular foot)."""
    A, B = T[:-1], T[1:]
    D = B - A
    L2 = np.maximum((D ** 2).sum(1), 1e-12)
    t = ((P[:, None, :] - A[None]) * D[None]).sum(2) / L2[None]
    tc = np.clip(t, 0, 1)
    Q = A[None] + tc[..., None] * D[None]
    d = np.linalg.norm(P[:, None, :] - Q, axis=2)
    j = d.argmin(1)
    tt = t[np.arange(len(P)), j]
    return d[np.arange(len(P)), j], j, np.clip(tt, 0, 1), (tt > 0) & (tt < 1)


def _resample(T, step):
    T = np.asarray(T, float)
    s = np.r_[0, np.cumsum(np.linalg.norm(np.diff(T, axis=0), axis=1))]
    n = max(int(s[-1] / step), 2)
    q = np.linspace(0, s[-1], n + 1)
    return np.c_[np.interp(q, s, T[:, 0]), np.interp(q, s, T[:, 1])], q


def turning_deg(P, i, w) -> float:
    """The turn of polyline P at point i over a window of w mm either side (0 = straight)."""
    s = np.r_[0, np.cumsum(np.linalg.norm(np.diff(P, axis=0), axis=1))]
    a = np.interp(s[i] - w, s, np.arange(len(P)))
    b = np.interp(s[i] + w, s, np.arange(len(P)))
    if s[i] - w < 0 or s[i] + w > s[-1]:
        return 0.0
    pa = np.array([np.interp(a, np.arange(len(P)), P[:, 0]), np.interp(a, np.arange(len(P)), P[:, 1])])
    pb = np.array([np.interp(b, np.arange(len(P)), P[:, 0]), np.interp(b, np.arange(len(P)), P[:, 1])])
    u, v = P[i] - pa, pb - P[i]
    c = float(np.dot(u, v) / max(np.linalg.norm(u) * np.linalg.norm(v), 1e-9))
    return float(np.degrees(np.arccos(np.clip(c, -1, 1))))


def compare(trace_mm, arcs: list, edge_mm: float, mm_per_px: float, corners=(), residual_mm: float = 0.0) -> dict:
    """trace (mm, view plane) vs the build's border arcs ([ (N,2) mm, ordered ]): the numbers of one outline row."""
    tol = TRACE_PX * mm_per_px + edge_mm
    T, sT = _resample(trace_mm, max(min(edge_mm, tol) / 2, 0.5))
    C = np.concatenate(arcs) if arcs else np.zeros((0, 2))
    tan = np.concatenate([np.gradient(np.asarray(a, float), axis=0) for a in arcs]) if arcs else np.zeros((0, 2))
    tan /= np.maximum(np.linalg.norm(tan, axis=1, keepdims=True), 1e-9)
    seg = np.diff(T, axis=0)
    seg /= np.maximum(np.linalg.norm(seg, axis=1, keepdims=True), 1e-9)
    out = dict(tol_mm=round(tol, 1), edge_mm=round(edge_mm, 1), trace_mm=round(float(sT[-1]), 1))
    if not len(C):
        return dict(out, status="UNMEASURED", why="no border of the matching pieces near the trace")

    def both(shift):
        Cs = C + shift
        d1 = np.min(np.linalg.norm(T[:, None] - Cs[None], axis=2), 1)
        cap = max(float(d1.max()), CAP_X * tol)
        d2, j, _, inner = _foot(Cs, T)
        along = np.abs((tan * seg[j]).sum(1)) >= np.cos(np.radians(TANGENT_DEG))
        keep = inner & (d2 <= cap) & along
        return d1, d2[keep], keep, None
    shift = np.zeros(2)
    for _ in range(8):  # (the best shift: built points pulled onto their trace feet, then the trace's onto them)
        d1, d2, keep, _ = both(shift)
        Cs = C + shift
        n1 = np.argmin(np.linalg.norm(T[:, None] - Cs[None], axis=2), 1)
        shift = shift + np.mean(T - Cs[n1], 0)
    d1p, d2p, keepp, _ = both(np.zeros(2))
    d1, d2, keep, _ = both(shift)
    allp, alls = np.r_[d1p, d2p], np.r_[d1, d2]
    w = int(np.argmax(d1))
    out.update(placed_p95_mm=round(float(np.percentile(allp, 95)), 1), placed_max_mm=round(float(allp.max()), 1),
               p95_mm=round(float(np.percentile(alls, 95)), 1), max_mm=round(float(alls.max()), 1),
               shift_mm=[round(float(x), 1) for x in shift], worst_mm=T[w].round(1).tolist(),
               worst_along=round(float(sT[w] / sT[-1]), 2), built_kept=int(keep.sum()),
               kept_masks=np.split(keep, np.cumsum([len(a) for a in arcs])[:-1]),
               built_near_worst=(C + shift)[int(np.argmin(np.linalg.norm(C + shift - T[w], axis=1)))].round(1).tolist())
    shift_lim = SHIFT_X * tol + residual_mm
    cs, Tm = [], np.asarray(trace_mm, float)
    win = tol
    for ci in corners:
        tturn = turning_deg(Tm, ci, win)
        if tturn < CORNER_MIN_DEG:
            cs.append(dict(index=ci, traced_deg=round(tturn, 0), kept=None, why=f"turns < {CORNER_MIN_DEG:.0f} deg in the trace"))
            continue
        best, gap = None, min(float(np.min(np.linalg.norm(a + shift - Tm[ci], axis=1))) for a in arcs)
        for a in arcs:
            A = a + shift
            for i in np.where(np.linalg.norm(A - Tm[ci], axis=1) <= tol)[0]:
                t_ = turning_deg(A, int(i), win)
                best = t_ if best is None or t_ > best else best
        cs.append(dict(index=ci, traced_deg=round(tturn, 0), built_deg=None if best is None else round(best, 0),
                       nearest_mm=round(gap, 1), kept=bool(best is not None and best >= CORNER_KEEP * tturn),
                       at_mm=Tm[ci].round(1).tolist()))
    out["corners"] = cs
    fails = []
    if out["p95_mm"] > tol:
        fails.append(f"shape p95 {out['p95_mm']} > {tol:.1f} mm")
    if out["max_mm"] > 2 * tol:
        fails.append(f"shape max {out['max_mm']} > {2 * tol:.1f} mm")
    if float(np.linalg.norm(shift)) > shift_lim:
        fails.append(f"placed {np.linalg.norm(shift):.0f} mm off (> {shift_lim:.0f} mm)")
    lost = [c for c in cs if c["kept"] is False]
    if lost:
        fails.append(f"{len(lost)} of {sum(c['kept'] is not None for c in cs)} corners lost")
    out.update(status="FAIL" if fails else "PASS", fails=fails, shift_limit_mm=round(shift_lim, 1))
    return out


# ---------------------------------------------------------------- the pattern edge behind a place
def pattern_edge(M, vid: int, draft_dir) -> str | None:
    """The step-4 declared edge (piece:edge) nearest this vertex on the flat pattern (uv = draft points / 1000, v down
    negated, mirrored pieces u negated), or None (no declarations)."""
    try:
        d = Path(draft_dir)
        dec = json.loads((d / "declarations.json").read_text())
        parts = json.loads((d / "draft.json").read_text())["parts"]
        from .draft_pairs import expand
        dec = expand(dec, parts)  # (pairs: NAME.L / NAME.R as the build names them)
    except (OSError, ValueError, KeyError, TypeError):
        return None
    name = M["names"][int(np.asarray(M["piece"])[vid])]
    pc, edges = (dec.get("pieces") or {}).get(name) or {}, (dec.get("edges") or {}).get(name) or {}
    pts = (parts.get(pc.get("part")) or {}).get("points") or {}
    uv = np.asarray(M["uv"], float)[vid]
    best = (np.inf, None)
    for en, chain in edges.items():
        P = [pts.get(k) for k in str(chain).split(">")]
        if len(P) < 2 or any(p is None for p in P):
            continue
        P = np.array([[(-1 if pc.get("mirror") else 1) * x / 1000, -y / 1000] for x, y in P])
        dd = _foot(uv[None], P)[0][0]
        if dd < best[0]:
            best = (dd, f"{name}:{en}")
    if best[0] > EDGE_NEAR_M and pts:  # (no declared edge there: name the draft's two points the place lies between)
        Q = {k: np.array([(-1 if pc.get("mirror") else 1) * x / 1000, -y / 1000]) for k, (x, y) in pts.items()
             if isinstance(x, (int, float)) and isinstance(y, (int, float))}
        near = sorted(Q, key=lambda k: float(np.linalg.norm(Q[k] - uv)))[:2]
        return f"{name}: the undeclared edge between its points {' and '.join(near)}"
    return best[1]


# ---------------------------------------------------------------- the rows (chain_structure.check adds them)
def _view_of(plan: dict, vi: int) -> dict:
    return ((plan.get("read") or {}).get("views") or [{}])[vi]


def _marks(style: dict, vi: int) -> dict:
    out = {}
    for m in style.get("body_marks") or []:
        if m.get("view", 0) == vi:
            out.update(m.get("at") or {})
    return out


def measure(X, M, at: dict, plan: dict | None) -> list:
    """[{trace, view, placement, arcs (mm), result}] for every step-2 trace (the rows' numbers and the look's lines)."""
    style = (plan or {}).get("style") or {}
    out = []
    X = np.asarray(X, float)
    for t in style.get("traces") or []:
        vi = t.get("view", 0)
        v = _view_of(plan, vi)
        try:
            pl = placement(v, _marks(style, vi), at)
        except (ValueError, KeyError, np.linalg.LinAlgError) as e:
            out.append(dict(trace=t, view=v, result=dict(status="UNMEASURED", why=f"the body marks don't place the view: {e}")))
            continue
        if KINDS.get(t.get("what"), {}).get("unmeasured"):
            out.append(dict(trace=t, view=v, result=dict(status="UNMEASURED", why=KINDS[t["what"]]["unmeasured"])))
            continue
        ks = matching_pieces(M, t["what"], v["view"], X)
        P2 = project(X, v["view"])
        loops = border_loops(M, ks)
        arcs = [P2[lp] for _, lp in loops]
        Tm = to_mm(t["points"], pl)
        lens = [np.linalg.norm(np.diff(a, axis=0), axis=1) for a in arcs]
        edge = float(np.median(np.concatenate(lens))) if lens else 0.0
        # (only loops that come near the trace: a far loop can't be its edge)
        near = [i for i, a in enumerate(arcs) if np.min(np.linalg.norm(a[:, None] - Tm[None], axis=2)) < 0.5 * np.ptp(Tm, 0).max() + 50]
        res = compare(Tm, [arcs[i] for i in near], edge, pl["s"], t.get("corners") or [], pl["residual_mm"])
        if res.get("built_near_worst") is not None:
            C = np.concatenate([arcs[i] for i in near])
            V = np.concatenate([np.asarray(loops[i][1]) for i in near])
            vid = int(V[np.argmin(np.linalg.norm(C + res["shift_mm"] - res["built_near_worst"], axis=1))])
            res["worst_piece"] = M["names"][int(np.asarray(M["piece"])[vid])]
            res["worst_edge"] = pattern_edge(M, vid, ((plan or {}).get("draft") or {}).get("dir") or "")
            res["worst_px"] = to_px([res["worst_mm"]], pl)[0].round(0).tolist()
        out.append(dict(trace=t, view=v, placement=pl, arcs=[arcs[i] for i in near], pieces=[M["names"][k] for k in ks],
                        result=res))
    return out


def rows(X, M, at: dict, plan: dict | None, measured: list | None = None) -> list:
    """The outline rows ("outline:<trace id>") in chain_structure's row form."""
    out = []
    for m in measured if measured is not None else measure(X, M, at, plan):
        t, r = m["trace"], m["result"]
        rid = f"outline:{t['id']}"
        pl = m.get("placement") or {}
        src = (f"step 2 trace {t['id']} ({t['what']}, {t.get('source', '')}); placed: {pl.get('how', '-')}; tol = "
               f"{TRACE_PX:.0f} px x {pl.get('s', 0):.2f} mm/px + the border edge {r.get('edge_mm', '?')} mm (C299)")
        if pl.get("step0_mm_per_px") and abs(pl["step0_mm_per_px"] / pl["s"] - 1) > SCALE_AGREE:
            src += (f"; NOTE: step 0's scale {pl['step0_mm_per_px']} mm/px is {pl['step0_mm_per_px'] / pl['s'] - 1:+.0%} off "
                    f"the body marks' {pl['s']:.3f}: the photo's figure is not this body's size (step 0's scale is unused)")
        row = dict(id=rid, stage=6, status=r["status"], source=src, measure="structure_outline (the build, projected)",
                   ref=f"shape p95 <= {r.get('tol_mm')} mm, max <= {2 * (r.get('tol_mm') or 0):.1f}, placed within "
                       f"{r.get('shift_limit_mm')} mm, corners kept (>= {CORNER_KEEP:.0%} of the traced turn)",
                   ours={k: r.get(k) for k in ("p95_mm", "max_mm", "placed_p95_mm", "shift_mm") if k in r})
        if r["status"] == "UNMEASURED":
            row.update(why=r["why"], change="mark the view's body landmarks / check the trace's what (back to step 2)",
                       back_to="2")
        elif r["status"] == "FAIL":
            cs = [c for c in r["corners"] if c["kept"] is False]
            row.update(why="; ".join(r["fails"]), back_to="4",
                       change=f"redraw the pattern edge {r.get('worst_edge') or r.get('worst_piece')} so its outline "
                              f"follows the trace: worst {r['max_mm']} mm at trace px {r.get('worst_px')} "
                              f"({r['worst_along']:.0%} along {t['id']})"
                              + (f"; corners lost at trace points {[c['index'] for c in cs]} (traced "
                                 f"{[c['traced_deg'] for c in cs]} deg; built turn {[c['built_deg'] for c in cs]} deg, "
                                 f"None = no built outline within {r['tol_mm']} mm: nearest {[c['nearest_mm'] for c in cs]} mm)"
                                 if cs else "")
                              + (f"; the whole edge sits {np.linalg.norm(r['shift_mm']):.0f} mm off where the body puts it "
                                 f"(shift {r['shift_mm']} mm: the pattern's length / width to this edge)"
                                 if any(f.startswith("placed") for f in r["fails"]) else "")
                              + " (back to step 4: draft_pattern)")
        out.append(row)
    return out
