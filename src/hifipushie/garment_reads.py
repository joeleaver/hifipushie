"""A garment's BIG READS, measured where the path judges them, for ANY garment (shirt, jacket, Tess's clothes).

Why (shirt round 1, 2026-10-20; ledger C97 / C98 / C100 / C101): Garrett's shirt passed its flat gate with every one of
its biggest reads unread. The front's state, the collar's spread, the buttons done, the tuck were "SIM: judged after the
sim" on a path that never runs a sim (form path, M1); the piece checklist (workspace/checklists/<piece>.json) held ten
measured items with tolerances that no gate read; the collar draft rules lived in the jacket's tailor rows only; the
colour row compared a design hex with a lit read. Each lesson is general code here:

READINGS (numbers, read off the geometry, never off a design key):
- `front_reads(X, M, hps_z)`   (C97) the fronts' state from the assembled vertices: the gap between the two fronts'
  inner (CF) edges per height below the HPS; the V bottom (the first height, from the top, where they meet within
  MEET_MM and stay met); front_state closed / open / part (share of heights met from the V bottom to the hem); the
  front closure's buttons done (pair vertices within BUTTON_DONE_MM) and the first fastened button's drop.
- `collar_reads(X, M, hps_z)`  (C97) the collar's state: its points (each side's lowest fall vertex) apart, off CF and
  below the HPS (front view), whether the fall is turned down over the stand at CB (fall_above_stand_mm < 0), and the
  label collar_state standing / closed / part / spread.
- `tuck_reads(X, body, line_z)` (C97, design key "tucked") the cloth below the tuck line: its p90 stand-off off the body
  and how far the hem runs below the line (hidden by the garment over it).
- `collar_draft_reads(Bp, g)`  (C101) ANY collar with a stand (role collar_stand) and a fall (role collar_fall) sewn to
  the stand's top: the stand's height at CB and at its ends, the fall's at CB, the roll line (the fall's roll fold
  offset), the turn of cloth from the fabric stack (C43: pattern_jacket.turn_stack with this garment's fabrics), the
  worn fall's cover over the stand seam (fall below the roll - the turn - the stand above it), and whether the fold's
  run-off agrees with the stand (C79 / R28: a stand that runs off to nothing at its ends needs a fold that runs off; a
  stand standing at its ends needs a fold that runs the whole edge, or the points flip).
- `flat_closure_reads(Bp)`     the front band's (placket's) width and the front buttons' spacing, read on the draft.
- `colour_patch(png, box)`     (C100) a lit / shadow patch read (60-90th / 5-15th luminance percentile, sRGB) on a
  render of the garment's OWN colour under the game light, compared like with like with the same read on the reference.

CHECKLIST ROWS (C98): `checklist_rows(items, readings, stage)`: every checklist item with a machine target becomes a gate
row automatically: {"read": <reading key>, "range": [lo, hi]} or {"read": ..., "equals": <label>}, "on": "flat" | "fit"
| "colour" | "dressed" (where it is read; default "fit"), "stage" (C52: 1 big reads, 2 fit, 3+ details). An item read at
another stage is a LATER row (shown with its reading when one exists, never blocking here); a reading missing where the
item is read is UNMEASURED (blocks). Rows are ordered big to small by cloth_check.big_first.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np

MEET_MM = 2.0  # the two fronts' inner edges within this (or lapped past each other) = they meet (shirt f1b: -1..+2 mm closed)
BUTTON_DONE_MM = 8.0  # a button pair's two vertices within this = fastened (f1b: done 0 mm, the undone collar 70 mm)
SCAN_STEP_MM = 5.0
COLLAR_CLOSED_MM = 70.0  # collar points closer than this = a closed / standing collar; wider than COLLAR_SPREAD_MM = spread
COLLAR_SPREAD_MM = 110.0
FALL_COVER_MM = (5.0, 25.0)  # the worn fall covers the stand seam by >= 5 mm (checklist collar_band; Aldrich, Metric
# Pattern Cutting for Menswear, shirt collars: the fall 10-15 mm deeper than the stand), <= 25 (a fall that deep reads
# as a cape on a shirt collar)
STAND_RUNS_OFF_MM = 6.0  # a stand under this at its ends "runs off" (the jacket's two-piece stand: R28 ~3 mm)
TUCK_STANDOFF_MM = 10.0  # tucked cloth below the line lies within this of the body (= cloth_check.UNDER_STANDOFF)
COLLAR_FABRIC_SOURCE = ("a shirt collar: two layers of the shell + a fused interlining (~0.3 mm, INFERRED: typical shirt "
                        "collar fusibles 0.25-0.35 mm); its stand the same stack (C43: turn of cloth from the fabrics)")


def _roles(M) -> list:
    from . import garment_design
    return [garment_design.role_of(n) for n in M["names"]]


def _mask(M, roles) -> np.ndarray:
    rr = _roles(M)
    return np.isin(np.asarray(M["piece"]), [k for k, r in enumerate(rr) if r in roles])


def front_reads(X, M, hps_z: float, closure: str = "front") -> dict:
    """The fronts' state on assembled vertices X (mesh M: names, piece, closures with "v" pairs). Heights in mm below
    hps_z. No front pieces on both sides: {} (a garment with no opening)."""
    X = np.asarray(X, float)
    pid = np.asarray(M["piece"])
    rr = _roles(M)
    fr = [k for k, r in enumerate(rr) if r == "front"]
    side = {}
    for k in fr:
        m = pid == k
        if m.sum():
            side.setdefault("L" if X[m, 0].mean() > 0 else "R", []).append(k)
    out: dict = {}
    if "L" in side and "R" in side:
        mL, mR = np.isin(pid, side["L"]), np.isin(pid, side["R"])
        XL, XR = X[mL], X[mR]
        top = min(XL[:, 2].max(), XR[:, 2].max())
        bot = max(XL[:, 2].min(), XR[:, 2].min()) + 0.03
        prof = []
        z = top - 0.004
        while z > bot:
            a, b = XL[np.abs(XL[:, 2] - z) < 0.004], XR[np.abs(XR[:, 2] - z) < 0.004]
            if len(a) and len(b):
                gap = (a[:, 0].min() - b[:, 0].max()) * 1000
                prof.append((round((hps_z - z) * 1000, 1), round(float(gap), 1), round(float(a[:, 0].min()) * 1000, 1),
                             round(float(-b[:, 0].max()) * 1000, 1)))
            z -= SCAN_STEP_MM / 1000
        met = [p[1] <= MEET_MM for p in prof]
        vb = None
        for i in range(len(prof)):
            if all(met[i:i + 3]) and len(met[i:i + 3]) == 3:
                vb = i
                break
        out["front_gap_profile"] = prof[::4]
        if vb is None:
            out.update(front_state="open", v_bottom_below_hps_mm=None, front_met_share=0.0)
        else:
            share = float(np.mean(met[vb:])) if met[vb:] else 0.0
            out.update(v_bottom_below_hps_mm=prof[vb][0], front_met_share=round(share, 3),
                       front_state="closed" if share >= 0.9 else ("open" if share < 0.5 else "part"),
                       v_top_half_width_mm=[prof[0][2], prof[0][3]])
        # the V's half width at fixed drops (front view): the inner edges off CF
        for d in (40, 60, 80):
            near = [p for p in prof if abs(p[0] - d) <= SCAN_STEP_MM / 2 + 0.1]
            if near:
                out[f"v_half_width_{d}_mm"] = [near[0][2], near[0][3]]
    btn = []
    for c in M.get("closures") or []:
        if c.get("name") != closure:
            continue
        for v in c.get("v") or []:
            a, b = X[int(v[0])], X[int(v[1])]
            btn.append({"below_hps_mm": round(float(hps_z - 0.5 * (a[2] + b[2])) * 1000, 1),
                        "gap_mm": round(float(np.linalg.norm(a - b)) * 1000, 1)})
    if btn:
        btn.sort(key=lambda r: r["below_hps_mm"])
        done = [r for r in btn if r["gap_mm"] <= BUTTON_DONE_MM]
        out.update(buttons=btn, buttons_done=len(done), buttons_total=len(btn),
                   first_done_below_hps_mm=done[0]["below_hps_mm"] if done else None,
                   button_spacing_worn_mm=round(float(np.median(np.diff([r["below_hps_mm"] for r in btn]))), 1)
                   if len(btn) > 1 else None)
    for c in M.get("closures") or []:  # the collar's own closure (a shirt's top button): done or not
        if c.get("name") == "collar" and c.get("v"):
            a, b = X[int(c["v"][0][0])], X[int(c["v"][0][1])]
            out["collar_button_done"] = bool(np.linalg.norm(a - b) * 1000 <= BUTTON_DONE_MM)
    return out


def collar_reads(X, M, hps_z: float) -> dict:
    """The collar's worn state (front view: x across, z up): the fall's points, its turn over the stand at CB."""
    X = np.asarray(X, float)
    fall = np.where(_mask(M, ("collar_fall",)))[0]
    if not len(fall):
        return {}
    out = {}
    pts = {}
    for sd, sg in (("L", 1), ("R", -1)):
        c = fall[sg * X[fall, 0] > 0.005]
        if len(c):
            pts[sd] = X[c[np.argmin(X[c, 2])]]
    if len(pts) == 2:
        pl, pr = pts["L"], pts["R"]
        apart = float(np.linalg.norm((pl - pr)[[0, 2]]) * 1000)
        out.update(collar_points_apart_mm=round(apart, 1), collar_points_off_cf_mm=[round(pl[0] * 1000, 1),
                   round(-pr[0] * 1000, 1)], collar_points_below_hps_mm=[round((hps_z - pl[2]) * 1000, 1),
                                                                         round((hps_z - pr[2]) * 1000, 1)])
        out["collar_points_below_hps_mean_mm"] = round(float(np.mean(out["collar_points_below_hps_mm"])), 1)
    st = np.where(_mask(M, ("collar_stand",)))[0]
    if len(st):
        cbs = st[(np.abs(X[st, 0]) < 0.02) & (X[st, 1] > np.median(X[st, 1]))]
        cbf = fall[(np.abs(X[fall, 0]) < 0.02) & (X[fall, 1] > np.median(X[fall, 1]))]
        if len(cbs) and len(cbf):
            out["fall_above_stand_mm"] = round(float(np.median(X[cbf, 2]) - X[cbs, 2].max()) * 1000, 1)
    a = out.get("collar_points_apart_mm")
    if a is not None:
        turned = out.get("fall_above_stand_mm", -1.0) < 0
        out["collar_state"] = ("standing" if not turned else "closed" if a < COLLAR_CLOSED_MM else
                               "spread" if a > COLLAR_SPREAD_MM else "part")
    return out


def tuck_reads(X, body, line_z: float, keep=None) -> dict:
    """Cloth below the tuck line (line_z, m; the garment over it covers it): its p90 signed stand-off off the body in
    the band from the line to 150 mm below (|x| < 0.22: the torso, not the arms) and the hem's depth below the line."""
    from . import pattern_form
    X = np.asarray(X, float)
    sel = (X[:, 2] < line_z) & (X[:, 2] > line_z - 0.15) & (np.abs(X[:, 0]) < 0.22)
    if keep is not None:
        sel &= np.asarray(keep, bool)
    if not sel.any():
        return {"tuck_standoff_p90_mm": None, "hem_below_line_mm": round(float(line_z - X[:, 2].min()) * 1000, 1)}
    d = pattern_form._body_surface(body).signed(X[sel])[0]
    return {"tuck_standoff_p90_mm": round(float(np.percentile(d, 90)) * 1000, 1),
            "tuck_standoff_p50_mm": round(float(np.median(d)) * 1000, 1),
            "hem_below_line_mm": round(float(line_z - X[:, 2].min()) * 1000, 1)}


def tuck_line_z(body, g: dict) -> float | None:
    """The tuck line for a garment with the design key "tucked" (true, or {"line": landmark z name | z (m), "drop":
    m added}): default the body's waist_z (a trousers waistband sits there). None: not tucked."""
    t = g.get("tucked")
    if not t:
        return None
    t = t if isinstance(t, dict) else {}
    at = getattr(body, "at", {}) or {}
    ln = t.get("line", "waist_z")
    z = float(ln) if isinstance(ln, (int, float)) else at.get(ln)
    if z is None:
        return None
    return float(np.asarray(z).reshape(-1)[-1]) + float(t.get("drop", 0.0))


def big_reads(res: dict, X=None, g: dict | None = None) -> dict:
    """Every big read of a garment assembled on the form (res: pattern_form.on_form / cloth.build; X its vertices)."""
    X = np.asarray(res["A"] if X is None else X, float)
    M, body = res["mesh"], res["body"]
    at = getattr(body, "at", {}) or {}
    hps = at.get("hps.L")
    if hps is None:
        return {}
    hz = float(np.asarray(hps, float).reshape(-1)[2])
    out = {**front_reads(X, M, hz), **collar_reads(X, M, hz)}
    lz = tuck_line_z(body, g or {})
    if lz is not None:
        torso = ~_mask(M, ("sleeve", "cuff", "collar_stand", "collar_fall"))
        out.update(tuck_reads(X, body, lz, keep=torso), tuck_line_below_hps_mm=round((hz - lz) * 1000, 1))
    return out


# ---------------------------------------------------------------------------------------------------------- flat
def _edge(pc, arc) -> np.ndarray:
    from . import pattern
    return np.asarray(pc["P"], float)[pattern.arc_indices(pc, arc)]


def _height_at(P_out: np.ndarray, E: np.ndarray, q: np.ndarray, n: np.ndarray) -> float:
    """The piece's depth from point q on edge E along the in-piece normal n: the far outline crossing (outline points
    within 3 mm of the normal line), m."""
    C = np.r_[P_out, P_out[:1]]  # (the outline densified to ~0.5 mm: a short end edge has no vertex near the line)
    seg = np.linalg.norm(np.diff(C, axis=0), axis=1)
    P_out = np.concatenate([C[i] + np.linspace(0, 1, max(int(seg[i] / 0.0005), 1), endpoint=False)[:, None] *
                            (C[i + 1] - C[i]) for i in range(len(seg))])
    rel = P_out - q
    along = rel @ n
    across = np.abs(rel @ np.array([-n[1], n[0]]))
    m = (across < 0.0008) & (along > 0.0005)
    return float(along[m].max()) if m.any() else float("nan")


def _depths(pc, arc) -> tuple:
    """(depth at the edge's middle, at its first end, at its last end) of piece pc measured from its edge `arc`."""
    E = _edge(pc, arc)
    P = np.asarray(pc["P"], float)
    c = P.mean(0)
    s = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(E, axis=0), axis=1))]
    res = []
    for f in (0.5, 0.0, 1.0):
        t = f * s[-1]
        i = int(np.clip(np.searchsorted(s, t) - 1, 0, len(E) - 2))
        u = (t - s[i]) / max(s[i + 1] - s[i], 1e-12)
        q = E[i] + u * (E[i + 1] - E[i])
        tg = E[i + 1] - E[i]
        tg = tg / (np.linalg.norm(tg) + 1e-12)
        n = np.array([-tg[1], tg[0]])
        # (into the piece: the side a step off the edge lands inside the outline; the centroid decided before, and a
        # sprung fall bent round its centre has its centroid behind its own sewn edge's middle: shirt round 9)
        from . import pattern as _pt
        inn = _pt._poly_inside(P, np.array([q + 0.0015 * n, q - 0.0015 * n]))
        if inn[1] and not inn[0] or (inn[0] == inn[1] and (c - q) @ n < 0):
            n = -n
        if f != 0.5:  # (the ends: step in 2 mm so the normal line does not run along the piece's end)
            q = q + tg * (0.002 if f == 0.0 else -0.002)
        res.append(_height_at(P, E, q, n))
    return tuple(res)


def collar_draft_reads(Bp: dict, g: dict | None = None) -> dict:
    """C101: ANY collar with a stand and a fall (shirt point collar, the jacket's two-piece collar). {} without both.
    Readings mm. The stand's neck edge and top edge come from the seam table (the stand edge sewn to the neckline; the
    stand edge the fall is sewn to)."""
    from . import garment_design, pattern_jacket
    g = g or {}
    pcs = Bp.get("pieces") or {}
    stn = [n for n, p in pcs.items() if garment_design.role_of(n, p) == "collar_stand" and not n.endswith(".m")]
    fan = [n for n, p in pcs.items() if garment_design.role_of(n, p) == "collar_fall" and not n.endswith(".m")]
    if not stn or not fan:
        return {}
    sn, fn = stn[0], fan[0]
    neck_e = top_e = fall_e = None
    for a, b in Bp.get("seams") or []:
        for x, y in ((a, b), (b, a)):
            if isinstance(x, str) and x.startswith(sn + ":"):
                ys = [y] if isinstance(y, str) else list(y)
                if any(s.startswith(fn + ":") for s in ys):
                    top_e, fall_e = x.split(":", 1)[1], next(s for s in ys if s.startswith(fn + ":")).split(":", 1)[1]
                elif all(not s.startswith(fn + ":") for s in ys):
                    neck_e = x.split(":", 1)[1]
    if neck_e is None or fall_e is None:
        return {}
    st_cb, _, _ = _depths(pcs[sn], neck_e)
    # the stand's height at its ends: the neck edge's end points to the top edge (the seam the fall is sewn to)
    En, Et = _edge(pcs[sn], neck_e), _edge(pcs[sn], top_e)
    Etd = np.concatenate([Et[i] + np.linspace(0, 1, 40, endpoint=False)[:, None] * (Et[i + 1] - Et[i])
                          for i in range(len(Et) - 1)] + [Et[-1:]])
    st_a, st_b = (float(np.linalg.norm(Etd - q, axis=1).min()) for q in (En[0], En[-1]))
    fa_cb, _, _ = _depths(pcs[fn], fall_e)
    roll = next((f for f in Bp.get("folds") or [] if f.get("piece") == fn and f.get("kind") == "roll"), None)
    fat = float(((roll or {}).get("line") or {}).get("offset", 0.0)) if isinstance((roll or {}).get("line"), dict) else 0.0
    if roll is None:
        fat = float((((pcs[fn].get("wrap") or {}).get("turn")) or {}).get("at", 0.0))
    two = (((Bp.get("draft") or {}).get("meta") or {}).get("collar_two_piece") or {}).get("turn")
    if two:
        ts, src = two, "the draft's own turn record (pattern_jacket.turn_stack)"
    else:
        fab = g.get("fabric") if isinstance(g.get("fabric"), str) else None
        canvas = g.get("collar_canvas", "fusible")
        ts = pattern_jacket.turn_stack(fab, canvas=canvas, under=fab, under_layers=0) if fab else \
            pattern_jacket.turn_stack(canvas=canvas, under_layers=0)
        if canvas == "fusible":  # (the KB has no fusible: its INFERRED 0.3 mm, see COLLAR_FABRIC_SOURCE)
            t = pattern_jacket._thick_mm(fab or "", 0.25) if fab else 0.25
            tf = 2 * t + 0.3
            ts = dict(ts, t_fall_mm=round(tf, 3), t_under_mm=round(tf, 3), depth_mm=round(math.pi / 2 * tf + tf, 2))
        src = COLLAR_FABRIC_SOURCE
    stand_w = st_cb * 1000 + fat * 1000
    fall_w = fa_cb * 1000 - fat * 1000 - float(ts["depth_mm"])
    ends = [st_a * 1000, st_b * 1000]
    runs_off = max(ends) < STAND_RUNS_OFF_MM
    fold_runs_off = bool((roll or {}).get("run_off"))
    return {"collar_stand_cb_mm": round(st_cb * 1000, 1), "collar_stand_ends_mm": [round(e, 1) for e in ends],
            "collar_fall_cb_mm": round(fa_cb * 1000, 1), "collar_roll_above_seam_mm": round(fat * 1000, 1),
            "collar_turn_mm": float(ts["depth_mm"]), "collar_turn_source": src,
            "collar_stand_worn_mm": round(stand_w, 1), "collar_fall_worn_mm": round(fall_w, 1),
            "collar_fall_cover_mm": round(fall_w - stand_w, 1),
            "collar_stand_runs_off": bool(runs_off), "collar_fold_runs_off": fold_runs_off,
            "collar_fold_agrees": bool(runs_off == fold_runs_off), "collar_pieces": [sn, fn]}


FALL_PATH_TAPER = False  # (C125) True = round 9's path: the drop tapers u^2 from the CB cover to the points' height
FALL_PATH_SOURCE = ("shirt round 11 (C125): a shirt collar's fall lands close round the neck, its outer edge parallel to "
                    "the stand seam at the CB cover (10-15 mm, Aldrich) all the way to the front; the points are the "
                    "fall's own corners lying on the fronts, not a deeper landing line. Round 9's path tapered the drop "
                    "u^2 to the points' height (42.7 mm at the ends: the front necklines offset 27 mm, +42 / +48 mm "
                    "each) and sprang the fall 127 mm past its sewn edge: on the form it spread over the shoulders as "
                    "a cape. Shirt drafting: the fall's outer edge ~ the neckline + a few cm of spring (Aldrich, "
                    "Metric Pattern Cutting for Menswear, two-piece shirt collar: the collar drafted on a near-rectangle "
                    "with a small front lift)")
SPRING_TOL_MM = (-6.0, 30.0)  # the fall's whole outer edge vs its landing path (R18's -3 / +15 per half, both halves)
SPRING_SOURCE = ("R18 / C43 generalised to any stand + fall collar (shirt round 9): turned down over its stand, the "
                 "fall's outer edge lies on the body where it lands (the neckline offset by the edge's drop below the "
                 "seam, + pi x its stand-off); cut as long as the stand (a straight band) it can only stand round the "
                 "neck as a tube: the funnel (Garrett r8: edge 5 mm out from the seam 10-21 mm below it, 59 mm/half "
                 "short). Pattern makers spring it: slash the fall from the outer edge and spread (Aldrich, Metric "
                 "Pattern Cutting for Menswear, shirt collars; Cabrera & Flaherty, collar spring)")


def _corners(P: np.ndarray, idx: list, deg: float = 45.0) -> list:
    """Positions in `idx` (an outline run) where the outline turns by more than `deg` (its ends excluded)."""
    out = []
    for j in range(1, len(idx) - 1):
        a, b, c = P[idx[j - 1]], P[idx[j]], P[idx[j + 1]]
        u, v = b - a, c - b
        if np.linalg.norm(u) < 1e-9 or np.linalg.norm(v) < 1e-9:
            continue
        t = math.degrees(math.acos(float(np.clip(u @ v / (np.linalg.norm(u) * np.linalg.norm(v)), -1, 1))))
        if t > deg:
            out.append(j)
    return out


def collar_pieces(Bp: dict) -> dict | None:
    """A stand + fall collar's pieces and edges from the seam table: {stand, fall, neck_e (the stand's edge sewn to the
    neckline), body (that seam's body arcs), top_e (the stand edge the fall is sewn to), fall_e (the fall's sewn edge),
    outer (outline indices of the fall's free outer edge: between the free outline's first and last corners)}."""
    from . import garment_design, pattern
    pcs = Bp.get("pieces") or {}
    stn = [n for n, p in pcs.items() if garment_design.role_of(n, p) == "collar_stand" and not n.endswith(".m")]
    fan = [n for n, p in pcs.items() if garment_design.role_of(n, p) == "collar_fall" and not n.endswith(".m")]
    if not stn or not fan:
        return None
    sn, fn = stn[0], fan[0]
    r = {"stand": sn, "fall": fn}
    for a, b in Bp.get("seams") or []:
        for x, y in ((a, b), (b, a)):
            if isinstance(x, str) and x.startswith(sn + ":"):
                ys = [y] if isinstance(y, str) else list(y)
                if any(s.startswith(fn + ":") for s in ys):
                    r["top_e"] = x.split(":", 1)[1]
                    r["fall_e"] = next(s for s in ys if s.startswith(fn + ":")).split(":", 1)[1]
                elif all(not s.startswith(fn + ":") for s in ys):
                    r["neck_e"], r["body"] = x.split(":", 1)[1], ys
    if "fall_e" not in r or "neck_e" not in r:
        return None
    pc = pcs[fn]
    n = len(pc["P"])
    se = pattern.arc_indices(pc, r["fall_e"])
    a, b = se[-1], se[0]  # (the free outline: from the sewn edge's end round to its start, the other way)
    fwd = [(a + k) % n for k in range((b - a) % n + 1)]
    bwd = [(a - k) % n for k in range((a - b) % n + 1)]
    free = fwd if not (set(fwd[1:-1]) & set(se)) else bwd
    P = np.asarray(pc["P"], float)
    cj = _corners(P, free)
    r["outer"] = free[cj[0]:cj[-1] + 1] if len(cj) >= 2 else free
    r["sewn"] = se
    return r


def fall_spring_reads(Bp: dict, g: dict | None = None) -> dict:
    """SPRING_SOURCE: a stand + fall collar's whole outer edge (mm) vs the path it lies on turned fully down over the
    stand: the neckline (the stand seam's body arcs) offset into the body pieces by the edge's drop below the seam
    (the worn fall's cover of the stand seam at CB, collar_draft_reads, held along the whole neckline: FALL_PATH_SOURCE;
    FALL_PATH_TAPER = True tapers it u^2 to the fall's end height less the roll, turn and stand end, as
    pattern_jacket.fall_need), + pi x its stand-off on each half (turn_stack). {} without such a collar."""
    from . import pattern, pattern_jacket
    cp = collar_pieces(Bp)
    rd = collar_draft_reads(Bp, g)
    if not cp or not rd or any(e.split(":")[0] not in Bp["pieces"] for e in cp["body"]):
        return {}  # (no collar, or the neckline's pieces aren't in this pattern: no path to read)
    pcs = Bp["pieces"]
    fc_ = pcs[cp["fall"]]
    P = np.asarray(fc_["P"], float)
    outer = pattern.length(P[cp["outer"]])
    E = P[cp["sewn"]]
    Ed = np.concatenate([E[i] + np.linspace(0, 1, 20, endpoint=False)[:, None] * (E[i + 1] - E[i]) for i in range(len(E) - 1)])
    he_f = float(np.mean([np.linalg.norm(Ed - P[cp["outer"][j]], axis=1).min() for j in (0, -1)]))
    fat = rd["collar_roll_above_seam_mm"] / 1000
    dep = rd["collar_turn_mm"] / 1000
    he_s = float(np.mean(rd["collar_stand_ends_mm"])) / 1000
    drop_cb = rd["collar_fall_cover_mm"] / 1000
    drop_e = (he_f - fat - dep) - (he_s + fat)
    Ls = []
    for e in cp["body"]:
        nm = e.split(":")[0]
        Ls.append(pattern.length(np.asarray(pcs[nm]["P"], float)[pattern.arc_indices(pcs[nm], e.split(":", 1)[1])]))
    c = np.r_[0.0, np.cumsum(Ls)] / max(sum(Ls), 1e-9)
    path, parts = 0.0, {}
    for i, e in enumerate(cp["body"]):
        u = np.abs(np.linspace(c[i], c[i + 1], 41) - 0.5) * 2  # (0 at CB, the chain's middle; 1 at its ends)
        de_ = drop_e if FALL_PATH_TAPER else drop_cb  # (C125: the edge runs parallel to the seam at the CB cover)
        dr = float(np.mean(np.maximum(drop_cb + (de_ - drop_cb) * u * u, 0.0)))
        L = pattern_jacket.fall_path(pcs, [e], dr)
        path += L
        parts[e] = {"arc_mm": round(Ls[i] * 1000, 1), "drop_mm": round(dr * 1000, 1), "path_mm": round(L * 1000, 1)}
    ts = pattern_jacket.turn_stack(g.get("fabric") if isinstance((g or {}).get("fabric"), str) else None)
    need = path * 1000 + 2 * float(ts["length_mm"])
    sewn = pattern.length(E) * 1000
    return {"fall_outer_mm": round(outer * 1000, 1), "fall_need_mm": round(need, 1),
            "fall_short_mm": round(need - outer * 1000, 1), "fall_sewn_mm": round(sewn, 1),
            "spring_mm": round(outer * 1000 - sewn, 1), "drop_cb_mm": round(drop_cb * 1000, 1),
            "drop_end_mm": round(drop_e * 1000, 1), "parts": parts, "ring_mm": ts["length_mm"],
            "pieces": [cp["stand"], cp["fall"]]}


CORNER_STRAIN_MAX = 10.0  # % at a collar / band corner (the made pieces start within 7 % p99 on the form; shirting
# yields ~3-5 % before it puckers: above 10 % the corner reads torn)
CORNER_FOLDED_MAX = 2
CORNER_SOURCE = ("Joe on shirt round 8's collar crop: 'the front corners of the collar are torn': at the right band end "
                 "strain 31 % (stand) / 22 % (the fall's sewn end) after the arrangement's single-vertex pins pulled the "
                 "band ends 35 mm; a shirting corner pulled past ~10 % reads frayed. Crumpled = a cell whose normal "
                 "opposes its 6 mm neighbours' mean, outside the fold's hinge band (the roll's own turn is not a crumple)")


def collar_corner_reads(M: dict, X, Bp: dict, reach: float = 0.02) -> dict:
    """The corners of a stand + fall collar (the fall's free-outline corners: its points; its sewn edge's ends; the
    stand's ends): per corner, the faces within `reach` (pattern) of it: strain max / p99 (%), crumpled cells (normal
    against its neighbours' mean, outside every fold's hinge band: the roll's rows + 4 mm), the cells' pattern edge
    (mm), the corner's pattern angle. -> {"<piece>:<index>": {..., "ok"}} ({} without such a collar)."""
    from scipy.spatial import cKDTree
    from . import diag_render, folds as fm
    cp = collar_pieces(Bp) if Bp else None
    if not cp or M is None:
        return {}
    X = np.asarray(X, float)
    F = np.asarray(M["F"]); uv = np.asarray(M["uv"], float); pid = np.asarray(M["piece"]); names = list(M["names"])
    s = diag_render.face_strain(X, F, uv) * 100
    N = np.cross(X[F[:, 1]] - X[F[:, 0]], X[F[:, 2]] - X[F[:, 0]])
    N /= np.linalg.norm(N, axis=1, keepdims=True) + 1e-15
    C = X[F].mean(1)
    hinge = np.zeros(len(F), bool)
    for fd in M.get("folds") or []:
        if fd["piece"] in (cp["stand"], cp["fall"]) and len(fd["rows"]):
            g = fm._geom(M, fd)
            rv = np.concatenate([np.asarray(r["row"]) for r in g["rows"]])
            kf = names.index(fd["piece"])
            d = cKDTree(uv[rv]).query(uv[F].mean(1))[0]
            hinge |= (pid[F[:, 0]] == kf) & (d < 0.004)
    pcs = Bp["pieces"]
    corners = []
    fP = np.asarray(pcs[cp["fall"]]["P"], float)
    for i in (cp["outer"][0], cp["outer"][-1], cp["sewn"][0], cp["sewn"][-1]):
        corners.append((cp["fall"], i, fP))
    sP = np.asarray(pcs[cp["stand"]]["P"], float)
    from . import pattern
    ne = pattern.arc_indices(pcs[cp["stand"]], cp["neck_e"])
    te = pattern.arc_indices(pcs[cp["stand"]], cp["top_e"])
    for i in (ne[0], ne[-1], te[0], te[-1]):
        corners.append((cp["stand"], i, sP))
    Cu = uv[F].mean(1)  # (neighbours in the PATTERN: in 3D a turned flap lies 1-2 mm over its base, opposite)
    tr = cKDTree(Cu)
    out = {}
    for pn, i, P in corners:
        k = names.index(pn)
        q = P[i]
        a, b = P[i - 1] - q, P[(i + 1) % len(P)] - q
        ang = math.degrees(math.acos(float(np.clip(a @ b / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-15), -1, 1))))
        idx = np.where((pid[F[:, 0]] == k) & (np.linalg.norm(uv[F].mean(1) - q, axis=1) < reach))[0]
        if not len(idx):
            continue
        crum = 0
        for f in idx[~hinge[idx]]:
            nb = [j for j in tr.query_ball_point(Cu[f], 0.006) if pid[F[j, 0]] == k and j != f and not hinge[j]]
            if nb and N[f] @ N[nb].mean(0) < 0:
                crum += 1
        el = np.linalg.norm(uv[F[idx]] - uv[F[idx]][:, [1, 2, 0]], axis=2)
        smax = float(np.abs(s[idx]).max())
        out[f"{pn}:{i}"] = {"strain_max": round(smax, 1), "strain_p99": round(float(np.percentile(np.abs(s[idx]), 99)), 1),
                            "crumpled": crum, "faces": int(len(idx)), "edge_mm": round(float(np.median(el)) * 1000, 1),
                            "corner_deg": round(ang, 1),
                            "ok": bool(smax <= CORNER_STRAIN_MAX and crum <= CORNER_FOLDED_MAX)}
    return out


def flat_closure_reads(Bp: dict, closure: str = "front") -> dict:
    """The front band's width (each front's band / placket fold offset) and the front closure's button spacing on the
    flat pattern (the over piece's marks named by its pairs), mm."""
    out = {}
    bands = [abs(float(f["line"]["offset"])) * 1000 for f in Bp.get("folds") or []
             if f.get("band") and isinstance(f.get("line"), dict) and "offset" in f["line"]]
    if bands:
        out["placket_width_mm"] = round(max(bands), 1)
        out["placket_widths_mm"] = [round(b, 1) for b in bands]
    for c in Bp.get("closures") or []:
        if c.get("name") != closure:
            continue
        pc = (Bp.get("pieces") or {}).get(c.get("over"))
        if pc is None:
            continue
        ys = []
        for pr in c.get("pairs") or []:
            for nm in pr:
                v = (pc.get("marks") or {}).get(nm)
                if v is None and nm in pc.get("names", {}):
                    v = pc["P"][pc["names"][nm]]
                if v is not None and len(np.asarray(v).reshape(-1)) == 2:
                    ys.append(float(np.asarray(v, float).reshape(-1)[1]))
                    break
        if len(ys) > 1:
            ys = sorted(ys)
            out["button_spacing_mm"] = round(float(np.median(np.diff(ys))) * 1000, 1)
            out["buttons_marked"] = len(ys)
    return out


def flat_reads(Bp: dict, g: dict | None = None) -> dict:
    return {**collar_draft_reads(Bp, g), **flat_closure_reads(Bp)}


# ---------------------------------------------------------------------------------------------------------- colour
def colour_patch(png, box) -> dict:
    """Lit (60-90th luminance percentile) and shadow (5-15th) mean sRGB of a box (fractions x0, y0, x1, y1) of a PNG:
    the same read on the reference and on ours (C100: lit vs lit)."""
    from PIL import Image
    im = np.asarray(Image.open(png).convert("RGB")).astype(float)
    h, w = im.shape[:2]
    x0, y0, x1, y1 = int(box[0] * w), int(box[1] * h), int(box[2] * w), int(box[3] * h)
    P = im[y0:y1, x0:x1].reshape(-1, 3)
    o = np.argsort(P @ np.array([0.2126, 0.7152, 0.0722]))
    n = len(o)
    lit = P[o[int(.6 * n):int(.9 * n)]].mean(0)
    sh = P[o[int(.05 * n):int(.15 * n)]].mean(0)
    return {"lit": [round(float(v), 1) for v in lit], "shadow": [round(float(v), 1) for v in sh],
            "r_minus_b": round(float(lit[0] - lit[2]), 1)}


def colour_row(item: dict, ours: dict, ref: dict | None = None) -> dict:
    """A colour item's row: ours["lit"] vs the reference lit read (item "ref_rgb", or `ref` colour_patch of the
    reference crop), each channel within item "tol_rgb" (default 8), hue R-B within item "hue_rb" [lo, hi] when given."""
    tgt = (ref or {}).get("lit") or item.get("ref_rgb")
    if tgt is None or ours is None:
        return {"id": item["id"], "stage": item.get("stage", 1), "status": "UNMEASURED", "why": "no lit read"}
    tol = float(item.get("tol_rgb", 8))
    d = [round(float(a) - float(b), 1) for a, b in zip(ours["lit"], tgt)]
    ok = all(abs(x) <= tol for x in d)
    hr = item.get("hue_rb")
    if hr:
        ok = ok and float(hr[0]) <= ours["r_minus_b"] <= float(hr[1])
    return {"id": item["id"], "stage": item.get("stage", 1), "status": "PASS" if ok else "FAIL", "ours": ours,
            "ref": {"lit": tgt, "tol_rgb": tol, "hue_rb": hr}, "miss": d, "read_on": "own-colour render (game light)"}


# ---------------------------------------------------------------------------------------------------------- checklist
def checklist_path(piece: str) -> Path:
    from . import store
    return store.HOME / "checklists" / f"{piece}.json"


def checklist_items(g: dict | None, model: str = "", garment: str = "") -> tuple:
    """(piece name, items) of the garment's piece checklist: garment key "checklist" (a piece name under
    workspace/checklists/), else <model>_<garment>. (None, []) when there is none."""
    g = g or {}
    for nm in [g.get("checklist"), f"{model}_{garment}" if model and garment else None]:
        if nm and checklist_path(nm).exists():
            try:
                return nm, list(json.loads(checklist_path(nm).read_text()).get("items") or [])
            except Exception:  # noqa: BLE001 (a broken checklist is no checklist: the gate says so)
                return nm, []
    return None, []


def _get(readings: dict, key: str):
    """readings[key]; "key[i]" picks an element; "key.max" / "key.min" / "key.mean" reduce a list."""
    k, sub = key, None
    if "[" in key:
        k, sub = key.split("[", 1)
        sub = int(sub.rstrip("]"))
    elif key.rsplit(".", 1)[-1] in ("max", "min", "mean"):
        k, sub = key.rsplit(".", 1)
    v = readings.get(k)
    if v is None or sub is None:
        return v
    if isinstance(sub, int):
        return v[sub] if isinstance(v, (list, tuple)) and len(v) > sub else None
    vals = [x for x in v if x is not None] if isinstance(v, (list, tuple)) else [v]
    return None if not vals else {"max": max, "min": min, "mean": lambda a: float(np.mean(a))}[sub](vals)


def gated(it: dict) -> bool:
    return bool(it.get("read")) and ("range" in it or "equals" in it or "ref_rgb" in it)


def checklist_rows(items: list, readings: dict, stage: str) -> list:
    """Rows for the checklist items with a machine target (C98), read at `stage` ("flat" | "fit" | "colour" |
    "dressed"). Each "read" may be a list of keys (every one must pass). An item read elsewhere: LATER."""
    rows = []
    for it in items:
        if not gated(it):
            continue
        on = it.get("on", "fit")
        keys = it["read"] if isinstance(it["read"], list) else [it["read"]]
        vals = {k: _get(readings, k) for k in keys}
        row = {"id": f"checklist:{it['id']}", "stage": int(it.get("stage", 3)), "measure": f"garment_reads ({on})",
               "read": keys, "ours": vals, "ref": it.get("range", it.get("equals")), "source": it.get("source", ""),
               "checklist": True}
        if on != stage:
            row.update(status="LATER", why=f"read on the {on} stage (garment_reads); shown, not judged here")
        elif "ref_rgb" in it:  # (C100: a colour item: lit vs lit, colour_row on a colour_patch reading)
            c = colour_row(it, vals[keys[0]])
            row.update({k: v for k, v in c.items() if k not in ("id", "stage")})
        elif any(v is None for v in vals.values()):
            row.update(status="UNMEASURED", why=f"no reading for {[k for k, v in vals.items() if v is None]} at {stage}")
        else:
            bad = []
            for k, v in vals.items():
                if "equals" in it:
                    if v != it["equals"]:
                        bad.append(f"{k} {v} != {it['equals']}")
                else:
                    lo, hi = it["range"]
                    if not ((lo is None or float(v) >= float(lo)) and (hi is None or float(v) <= float(hi))):
                        bad.append(f"{k} {v} outside [{lo}, {hi}]")
            row.update(status="FAIL" if bad else "PASS", **({"miss": "; ".join(bad)} if bad else {}))
        rows.append(row)
    return rows


# the cloth_reference measures that are big reads of the WORN state: read on the form fit, never deferred to a sim
FORM_READ = {"front_state": ("front_state", "v_bottom_below_hps_mm"), "buttons_done": ("buttons_done",
             "first_done_below_hps_mm"), "collar_state": ("collar_state", "collar_points_apart_mm"),
             "tucked": ("tuck_standoff_p90_mm",), "placket_finish": ("placket_width_mm",)}


def uncovered_form_reads(kind_items: list, items: list) -> list:
    """FORM_READ measures the garment kind's reference items ask for that no checklist item reads (C97: each one needs
    a checklist item with a target, or it is never judged)."""
    want = {it.get("measure") for it in kind_items if it.get("measure") in FORM_READ}
    have = set()
    for it in items:
        if gated(it):
            ks = it["read"] if isinstance(it["read"], list) else [it["read"]]
            have |= {k.split("[")[0].rsplit(".", 1)[0] if k.rsplit(".", 1)[-1] in ("max", "min", "mean") else
                     k.split("[")[0] for k in ks}
    return sorted(m for m in want if not (set(FORM_READ[m]) & have))
