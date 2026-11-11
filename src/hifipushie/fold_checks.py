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
PLEAT = ("Bp['pleats']: [{'piece', 'a': fold line, 'b': fold line (pattern.fold_line forms), 'depth': m, "
         "'press': 'left' | 'right' | 'box'}]: a pleat folds on a and lies back on b; its layers are 3 deep over 'depth'")


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

