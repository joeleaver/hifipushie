"""ONE family of checks for every DECLARED fold of a pattern (Joe 2026-10-20 via the coordinator: "we need generic checks
for any folded / pressed / pleated clothing part. That happens a lot in clothes"). Keyed on the pattern's fold
declarations (Bp["folds"] flat; the mesh's fold records M["folds"] on the form), never on the garment type: a collar's
roll, a lapel, a placket / front band, a hem or cuff turn-back, a waistband fold, a pocket flap, a dart pressed to one
side, a pleat (Bp["pleats"]: a fold pair, see PLEAT) all run through the same rows.

FLAT (the draft, per fold entry; `flat_rows(Bp, g)`):
- fold_turn_allowance  the cloth past the fold line (the flap's depth) covers the turn of cloth of the stack it wraps
  (C43: pi/2 x the flap's stack + the stack under it, from the fabrics) + FLAP_MIN_MM to lie on.
- fold_run_off         a fold line that stops short of the outline must declare a run-off (C79: the turn fades to 0),
  and a declared run-off must end inside the line (off < the line's length).
- fold_outer_longer    the turned (outer) layer's free edge is at least the length of the base line it lands on plus the
  turn (pi x the stack it wraps, for a roll that wraps a stack: the undercollar / facing rule, generalised; R18).
- pleat_depth          a pleat's two lines lie 2 x its depth apart (+-2 mm) and it declares its press side.

FORM (assembled vertices X on the form, per fold record; `form_rows(M, X, body)`):
- fold_turn            the turn achieved vs the declared turn (C46), +-35 deg. The declared TURN is |180 - angle| (folds.py:
                       angle is the outside dihedral, 180 flat, 0 folded right over: a collar's fall over its stand is a
                       180 deg turn; shirt round 9: the row compared the turn to the angle and read angle 0 as "unset",
                       so the full-fold collar roll was never judged). Read in SECTION by pattern_form.fold_turned (the
                       validated read; mean normals cancel round a wrapped fold: jacket collar 13 vs 175 in section),
                       its base across a seam where the fold's own base is narrow (< BASE_NARROW: a two-piece collar's
                       fall, roll 4-6 mm above its seam, lies on the STAND).
- fold_on_base         the flap lies on its own base, outside it (no flap vertex through the base: the lapel_on_base
                       row is this row on a lapel; pattern_form.flap_through_base) = the layer order kept (C82).
- fold_twist           the turn along the fold line changes by at most TWIST_DEG_CM per cm (gorge_lie's twist measure
                       generalised to any fold edge).
- fold_crisp           a pressed fold turns within PRESS_WIDTH_MM across its line; a soft roll spreads over at least
                       its declared radius (the dihedral profile across the fold).
Rows carry "family": "fold" and "fold": "<piece>:<name>"; status PASS / FAIL, or INFO with "why" where the
declaration gives nothing to judge (no angle declared).
"""
from __future__ import annotations

import math

import numpy as np

FLAP_MIN_MM = 3.0  # the flap lies on at least this past the turn
RUN_OFF_GAP_MM = 2.0  # a fold line ending further than this inside the outline "stops short"
TURN_TOL_DEG = 35.0
TWIST_DEG_CM = 15.0  # (gorge_lie: 10 deg / cm across a pressed seam; a fold's own line may bend with the body: 15)
PRESS_WIDTH_MM = 8.0  # a pressed edge / crease turns 80 % of its angle within this across the line
PLEAT = ("Bp['pleats']: [{'piece', 'a': fold line, 'b': fold line (pattern.fold_line forms), 'depth': m, "
         "'press': 'left' | 'right' | 'box'}]: a pleat folds on a and lies back on b; its layers are 3 deep over 'depth'")
SOURCE = ("folds by their declaration (Joe 2026-10-20): turn of cloth C43, run-off C79, outer longer than inner R18, "
          "turn achieved C46, flap on its base (fit round 11 lapel_on_base), twist (fit round 17 gorge_lie), layer order C82")


def _thick_mm(g: dict | None) -> float:
    from . import pattern_jacket
    fab = (g or {}).get("fabric") if isinstance((g or {}).get("fabric"), str) else None
    return pattern_jacket._thick_mm(fab or "", 0.25 if fab is None else 0.5)


def _line(Bp, f):
    from . import pattern
    return np.asarray(pattern.fold_line(Bp["pieces"], f), float)


def _flap_depth(P: np.ndarray, L: np.ndarray, flap_side: float) -> float:
    """m: how far the piece's outline reaches past fold line L on its flap side (sign of the line's left normal)."""
    # (signed distance to the LINE itself, folds.side_dist: across its chord a curved line, a sprung collar's roll,
    # read 4.0 mm on a 6 mm strip: shirt round 9)
    from . import folds as fm
    s = fm.side_dist(L, P)[0] * flap_side
    return float(max(s.max(), 0.0))


def _flap_side(pc, L, f) -> float:
    """+1 / -1: which side of L the flap is (the fold entry's "flap" point or the side holding less area)."""
    t = L[-1] - L[0]
    n = np.array([-t[1], t[0]]) / (np.linalg.norm(t) + 1e-12)
    P = np.asarray(pc["P"], float)
    fl = f.get("flap")
    if isinstance(fl, str) and fl in pc.get("names", {}):
        return float(np.sign((P[pc["names"][fl]] - L[0]) @ n) or 1.0)
    from . import folds as fm
    s = fm.side_dist(L, P)[0]
    return 1.0 if s.clip(0).sum() <= (-s).clip(0).sum() else -1.0


def _dist_to_outline(P: np.ndarray, q: np.ndarray) -> float:
    C = np.r_[P, P[:1]]
    a, b = C[:-1], C[1:]
    ab = b - a
    t = np.clip(((q - a) * ab).sum(1) / np.maximum((ab * ab).sum(1), 1e-18), 0, 1)
    return float(np.linalg.norm(a + t[:, None] * ab - q, axis=1).min())


def flat_rows(Bp: dict, g: dict | None = None) -> list:
    from . import pattern
    rows = []
    tm = _thick_mm(g)
    for f in Bp.get("folds") or []:
        pc = (Bp.get("pieces") or {}).get(f.get("piece"))
        if pc is None:
            continue
        tag = f"{f['piece']}:{f.get('name', '')}"
        try:
            L = _line(Bp, f)
        except Exception as e:  # noqa: BLE001
            rows.append({"id": "fold_line", "family": "fold", "fold": tag, "stage": 3, "status": "UNMEASURED",
                         "why": f"{type(e).__name__}: {e}"})
            continue
        P = np.asarray(pc["P"], float)
        side = _flap_side(pc, L, f)
        depth = _flap_depth(P, L, side) * 1000
        under_layers = 1 if f.get("band") or f.get("kind") == "press" else 2  # (a band folds on itself; a roll wraps a stand)
        turn = math.pi / 2 * 2 * tm + under_layers * tm
        need = turn + FLAP_MIN_MM
        rows.append({"id": "fold_turn_allowance", "family": "fold", "fold": tag, "stage": 3,
                     "status": "PASS" if depth >= need else "FAIL", "ours": {"flap_depth_mm": round(depth, 1)},
                     "ref": f">= {need:.1f} mm (turn {turn:.1f} + {FLAP_MIN_MM:g})", "why": "C43"})
        ends = [_dist_to_outline(P, L[0]) * 1000, _dist_to_outline(P, L[-1]) * 1000]
        ro = f.get("run_off")
        short = max(ends) > RUN_OFF_GAP_MM
        ok = (not short or bool(ro)) and (not ro or float(ro.get("off", 0.0)) < pattern.length(L))
        rows.append({"id": "fold_run_off", "family": "fold", "fold": tag, "stage": 3, "status": "PASS" if ok else "FAIL",
                     "ours": {"ends_inside_mm": [round(e, 1) for e in ends], "run_off": ro},
                     "ref": "stops short only with a run-off; the run-off ends inside the line", "why": "C79"})
        # the outer (turned) layer: its far edge = the piece's outline beyond the line, read as the chord of the
        # outline points within 2 mm of the flap depth, vs the fold line's length
        if depth > 1.0 and f.get("kind") == "roll" and f.get("wraps"):
            t = L[-1] - L[0]
            n = np.array([-t[1], t[0]]) / (np.linalg.norm(t) + 1e-12) * side
            far = P[(P - L[0]) @ n * 1000 > depth - 2.0]
            outer = float(np.ptp(far @ (t / np.linalg.norm(t)))) * 1000 if len(far) > 1 else 0.0
            inner = pattern.length(L) * 1000
            extra = math.pi * float(f["wraps"]) * 1000 if isinstance(f["wraps"], (int, float)) else math.pi * 2 * tm
            rows.append({"id": "fold_outer_longer", "family": "fold", "fold": tag, "stage": 3,
                         "status": "PASS" if outer >= inner + extra - 3.0 else "FAIL",
                         "ours": {"outer_mm": round(outer, 1), "inner_mm": round(inner, 1)},
                         "ref": f">= inner + {extra:.1f} mm - 3", "why": "R18 (undercollar / facing rule)"})
    for p in Bp.get("pleats") or []:
        tag = f"{p.get('piece')}:pleat"
        try:
            A, B = (_line(Bp, {"piece": p["piece"], "line": p[k]}) for k in ("a", "b"))
            dd = float(np.mean([_dist_to_outline(np.r_[B, B[::-1]], q) for q in A])) * 1000
            ok = abs(dd - 2000 * float(p["depth"])) <= 2.0 and p.get("press") in ("left", "right", "box")
            rows.append({"id": "pleat_depth", "family": "fold", "fold": tag, "stage": 3, "status": "PASS" if ok else "FAIL",
                         "ours": {"lines_apart_mm": round(dd, 1), "press": p.get("press")},
                         "ref": f"2 x depth {2000 * float(p['depth']):.0f} mm +-2, press declared", "why": PLEAT})
        except Exception as e:  # noqa: BLE001
            rows.append({"id": "pleat_depth", "family": "fold", "fold": tag, "stage": 3, "status": "UNMEASURED",
                         "why": f"{type(e).__name__}: {e}"})
    return rows


# --------------------------------------------------------------------------------------------------------- form
def _fnormals(X, F):
    n = np.cross(X[F[:, 1]] - X[F[:, 0]], X[F[:, 2]] - X[F[:, 0]])
    return n / (np.linalg.norm(n, axis=1, keepdims=True) + 1e-15)


def fold_sides(M: dict, fd: dict):
    """(row vertices, flap vertex mask, base vertex mask) of one fold record on the mesh (folds._geom)."""
    from . import folds as fm
    n = len(M["uv"])
    row = np.asarray(fd["rows"][0], np.int64) if len(fd["rows"]) else np.zeros(0, np.int64)
    g = fm._geom(M, fd)
    fl = np.zeros(n, bool)
    fl[np.asarray(g["rows"][-1]["v"], np.int64)] = True
    k = list(M["names"]).index(fd["piece"])
    base = (np.asarray(M["piece"]) == k) & ~fl
    for r in fd["rows"]:
        base[np.asarray(r, np.int64)] = False
    return row, fl, base


def _profile(M, X, fd, reach=0.03, step=0.002):
    """The turn across the fold: (distances across in mm, cumulative turn deg from the base side) on the pattern."""
    from scipy.spatial import cKDTree
    uv = np.asarray(M["uv"], float)
    F = np.asarray(M["F"])
    row, fl, base = fold_sides(M, fd)
    if not len(row):
        return None
    mine = fl | base
    for r in fd["rows"]:
        mine[np.asarray(r, np.int64)] = True
    Fm = F[mine[F].all(1)]
    if not len(Fm):
        return None
    d = cKDTree(uv[row]).query(uv[Fm].mean(1))[0]
    sgn = np.where(fl[Fm].any(1), 1.0, -1.0)
    s = d * sgn
    N = _fnormals(X, Fm)
    b = N[(s < -0.004) & (s > -reach)]
    if not len(b):
        return None
    nb = b.mean(0)
    nb /= np.linalg.norm(nb) + 1e-12
    xs = np.arange(-reach, reach + 1e-9, step)
    ang = []
    for x in xs:
        m = np.abs(s - x) < step
        if m.any():
            v = N[m].mean(0)
            ang.append(math.degrees(math.acos(np.clip(v @ nb / (np.linalg.norm(v) + 1e-12), -1, 1))))
        else:
            ang.append(np.nan)
    return xs * 1000, np.asarray(ang), (Fm, s, N, nb)


def _turn(prof) -> float:
    xs, ang, _ = prof
    fl = ang[(xs > 6) & np.isfinite(ang)]
    return float(np.median(fl)) if len(fl) else float("nan")


def _twist(M, X, fd, prof) -> float:
    """deg / cm: how fast the flap's turn changes ALONG the fold line (row vertices in order)."""
    uv = np.asarray(M["uv"], float)
    row = np.asarray(fd["rows"][0], np.int64)
    if len(row) < 4 or prof is None:
        return float("nan")
    Fm, s, N, nb = prof[2]
    F = np.asarray(M["F"])
    c = uv[Fm].mean(1)
    flap = (s > 0.006) & (s < 0.03)
    if flap.sum() < 4:
        return float("nan")
    o = np.argsort(uv[row] @ (uv[row[-1]] - uv[row[0]]))
    R = uv[row[o]]
    seg = np.r_[0, np.cumsum(np.linalg.norm(np.diff(R, axis=0), axis=1))]
    t = np.array([np.argmin(np.linalg.norm(R - q, axis=1)) for q in c[flap]])
    ang = np.degrees(np.arccos(np.clip(N[flap] @ nb, -1, 1)))
    bins = np.arange(0, seg[-1] + 0.01, 0.01)
    if len(bins) < 3:
        return float("nan")
    pos = seg[t]
    prof_a = [np.median(ang[(pos >= a) & (pos < a + 0.01)]) for a in bins[:-1] if ((pos >= a) & (pos < a + 0.01)).any()]
    if len(prof_a) < 2:
        return float("nan")
    return float(np.percentile(np.abs(np.diff(prof_a)), 90))


def _width(prof) -> float:
    """mm across the line holding 10..90 % of the turn."""
    xs, ang, _ = prof
    m = np.isfinite(ang)
    xs, ang = xs[m], np.maximum.accumulate(np.nan_to_num(ang[m]))
    if not len(ang) or ang[-1] < 5:
        return float("nan")
    lo, hi = np.interp([0.1 * ang[-1], 0.9 * ang[-1]], ang, xs)
    return float(hi - lo)


def declared_turn(fd: dict):
    """The turn a fold record declares (deg: 0 flat .. 180 folded right over or right under), None without an angle."""
    a = fd.get("angle")
    return None if a is None else abs(180.0 - float(a))


def narrow_base(M: dict, fd: dict) -> bool:
    """The fold's own base side is narrower than pattern_form.BASE_NARROW (C46): it lies on the piece sewn there."""
    from . import folds as fm, pattern_form as pf
    g = fm._geom(M, fd)
    bv = np.setdiff1d(np.asarray(g["sel"]), np.where(np.asarray(g["flap0"]))[0])
    return bool(len(bv)) and float(np.asarray(g["d0"])[bv].max()) < pf.BASE_NARROW


def turn_achieved(M: dict, X, fd: dict, prof=None) -> float:
    """deg turned on the form: pattern_form.fold_turned (the dihedral IN SECTION along the row, base across a seam: the
    validated read, C46), the base vs flap mean normals beside the row (_turn) only where it reads nothing. Mean
    normals sum round a curved / wrapped fold and cancel (shirt round 9: the jacket r26g collar roll read 13 deg by
    normals, 175 in section; Garrett's shirt collar 123 vs 162)."""
    from . import folds as fm, pattern_form as pf
    t = float(pf.fold_turned(M, np.asarray(X, float), fm._geom(M, fd)))
    if np.isfinite(t):
        return t
    prof = _profile(M, X, fd) if prof is None else prof
    return _turn(prof) if prof is not None else float("nan")


def form_rows(M: dict, X, body=None) -> list:
    from . import pattern_form as pf
    X = np.asarray(X, float)
    rows = []
    ftb = pf.flap_through_base(M, X, body) if M.get("folds") else {}
    for fd in M.get("folds") or []:
        tag = f"{fd['piece']}:{fd.get('name', '')}"
        prof = _profile(M, X, fd)
        want = declared_turn(fd)  # (deg turned, from the declared dihedral; the record's "turn" is the mesher's radians)
        nb = narrow_base(M, fd)
        if prof is None and not nb:
            rows.append({"id": "fold_turn", "family": "fold", "fold": tag, "stage": 3, "status": "UNMEASURED",
                         "why": "no base / flap faces beside the fold's row"})
            continue
        got = turn_achieved(M, X, fd, prof)
        if want is None or not np.isfinite(got):
            rows.append({"id": "fold_turn", "family": "fold", "fold": tag, "stage": 3,
                         "status": "INFO" if want is None else "UNMEASURED",
                         "ours": {"turn_deg": round(got, 1)} if np.isfinite(got) else {},
                         "why": "no declared turn to judge (no angle)" if want is None else "turn unread"})
        else:
            rows.append({"id": "fold_turn", "family": "fold", "fold": tag, "stage": 3,
                         "status": "PASS" if abs(got - float(want)) <= TURN_TOL_DEG else "FAIL",
                         "ours": {"turn_deg": round(got, 1), "read": "in section" + (", base across the seam" if nb
                                                                                      else "")},
                         "ref": f"{float(want):g} +- {TURN_TOL_DEG:g} deg (angle {float(fd['angle']):g})", "why": "C46"})
        if prof is None:
            continue
        fb = ftb.get(fd["piece"])
        if fb is not None:
            rows.append({"id": "fold_on_base", "family": "fold", "fold": tag, "stage": 3,
                         "status": "PASS" if fb["ok"] else "FAIL", "ours": fb,
                         "ref": f"share through <= {pf.FLAP_THROUGH_MAX}", "why": pf.FLAP_THROUGH_SOURCE})
        tw = _twist(M, X, fd, prof)
        if np.isfinite(tw):
            rows.append({"id": "fold_twist", "family": "fold", "fold": tag, "stage": 3,
                         "status": "PASS" if tw <= TWIST_DEG_CM else "FAIL", "ours": {"twist_deg_cm_p90": round(tw, 1)},
                         "ref": f"<= {TWIST_DEG_CM:g} deg / cm", "why": "gorge_lie's twist, any fold edge"})
        w = _width(prof)
        if np.isfinite(w) and want:
            press = fd.get("kind") == "press" or float(fd.get("radius", 0) or 0) < 0.003
            r_mm = float(fd.get("radius", 0) or 0) * 1000
            ok = w <= PRESS_WIDTH_MM if press else w >= max(r_mm, 2.0)
            rows.append({"id": "fold_crisp", "family": "fold", "fold": tag, "stage": 3, "status": "PASS" if ok else "FAIL",
                         "ours": {"turn_width_mm": round(w, 1), "pressed": press},
                         "ref": f"<= {PRESS_WIDTH_MM:g} mm (pressed)" if press else f">= {max(r_mm, 2.0):g} mm (soft roll)",
                         "why": "a pressed edge is a line; a roll is round"})
    return rows
