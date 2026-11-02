"""CHAIN STRUCTURE: the pre-sim gate. A chain_garment BUILD is measured against the reference reading before any hang.

Why (Joe 2026-11-02, C279): "you're running zozo sims and then saying 'everything looked bunched' but that's what's
_supposed_ to happen. We need a pre-sim judge of the structure." The hang adds folds by design, so a verdict on hung cloth
blames the sim for, or hides, faults already in the build (cf_shirt closed: the collar a straight tube up to the jaw, the
points never spread, all visible in built.pkl). So the job stops at "built", reads the build here, and hangs only on PASS
(or PASS_WAIVED: every failing row waived by name with a reason, cloth_check.verdict's rule).

READS (`reads`, numbers off the built vertices; heights from the body's landmarks):
- collar: garment_reads.collar_reads (points apart / below the HPS, collar_state, fall_above_stand) plus the collar's
  clearance under the jaw, the top line's tilt in the side view (back high, front low), the points' drop below the
  collar's back top, the leaves' stand-off from the cloth under them (lying, not standing).
- front: garment_reads.front_reads (state, met share, V bottom, V half widths) plus the over front edge's straightness.
- hem: CF / CB / left / right hem heights. Sleeves: the cuff's end past the wrist along the arm; the cuff's ease.

ROWS (`items` -> garment_reads.checklist_rows on stage "build"): each item has its target, its SOURCE (the reference
reading when it answers, else a named kind default: the measured reference notes beside the photos or a stated INFERRED
convention, never a number fitted to a build) and its CHANGE: what to alter when it fails (an alter_pattern op, a design
option, or the build stage that owns it) so a blind agent can act. Items whose pieces the garment lacks are left out.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from . import garment_reads as gr

STAGE = "build"
REF_NOTES = "folds_ab/refs README (Joe 2026-10-29, the default shirt's collar references)"
LAYER_REST_MM = 5.0  # chain_garment: the fall rests on the soft cloth under it at LAYER + 2 mm


def _neck_w(at) -> float:
    return 2.0 * abs(float(np.asarray(at["neck_side.L"])[0])) * 1000


def _pieces(M, roles) -> np.ndarray:
    return gr._mask(M, roles)


def collar_extra(X, M, bV, bT, at) -> dict:
    """Clearance under the jaw, top-line tilt, the points' drop below the back top, the leaves' stand-off."""
    col = np.where(_pieces(M, ("collar_fall", "collar_stand")))[0]
    fall = np.where(_pieces(M, ("collar_fall",)))[0]
    if not len(col) or not len(fall):
        return {}
    cf, cb = np.asarray(at["cf_neck"], float), np.asarray(at["cb_neck"], float)
    bV = np.asarray(bV, float)
    out = {}
    jaw = bV[(bV[:, 2] > cf[2] + 0.01) & (bV[:, 1] < cf[1] - 0.02) & (np.abs(bV[:, 0]) < abs(at["neck_side.L"][0]) + 0.03)]
    if len(jaw):
        from scipy.spatial import cKDTree
        d, _ = cKDTree(jaw).query(X[col])
        out["collar_jaw_clear_mm"] = round(float(d.min()) * 1000, 1)
    P = X[col]
    back = P[(np.abs(P[:, 0]) < 0.015) & (P[:, 1] > cb[1] - 0.03)]
    front = P[P[:, 1] < cf[1] + 0.03]  # the collar's front: forward of the throat less 30 mm
    if len(back) and len(front):
        zb, yb = back[:, 2].max(), back[np.argmax(back[:, 2]), 1]
        ft = front[np.argmax(front[:, 2])]
        out["collar_top_tilt_deg"] = round(float(np.degrees(np.arctan2(zb - ft[2], yb - ft[1]))), 1)
        out["collar_front_top_above_cf_mm"] = round(float(ft[2] - cf[2]) * 1000, 1)
        pts = [X[c[np.argmin(X[c, 2])]] for c in (fall[X[fall, 0] > 0.005], fall[X[fall, 0] < -0.005]) if len(c)]
        if len(pts) == 2:
            out["collar_points_below_back_top_mm"] = round(float(zb - np.mean([p[2] for p in pts])) * 1000, 1)
    pnl = _pieces(M, ("front", "back", "yoke"))
    Fm = np.asarray(M["F"])
    Fp = Fm[pnl[Fm[:, 0]]]
    low = fall[X[fall, 2] < cf[2]]  # the leaves in front, below the neckline: they lie on the shirt (or in an open V,
    if len(Fp) and len(low):        # on the body: read less the cloth's own GAP off the body)
        from .chain_net import Contact
        from .chain_garment import GAP
        d = np.abs(Contact(X, Fp).query(X[low])[0])
        db = np.abs(Contact(bV, np.asarray(bT, np.int64)).query(X[low])[0]) - GAP
        out["collar_leaf_standoff_p90_mm"] = round(float(np.percentile(np.minimum(d, db), 90)) * 1000, 1)
    out["neck_width_mm"] = round(_neck_w(at), 1)
    if "collar_points_apart_mm" in (ca := gr.collar_reads(X, M, float(np.asarray(at["hps.L"])[2]))):
        out["collar_points_apart_nw"] = round(ca["collar_points_apart_mm"] / out["neck_width_mm"], 2)
    return out


def front_extra(X, M, fr: dict, hps_z: float) -> dict:
    """The over front's edge straightness from the first fastened button down, and the V's taper (open)."""
    out = {}
    prof = fr.get("front_gap_profile") or []
    first = fr.get("first_done_below_hps_mm")
    if prof and first is not None:
        X = np.asarray(X, float)
        pid = np.asarray(M["piece"])
        fronts = [k for k, r in enumerate(gr._roles(M)) if r == "front"]
        L = X[np.isin(pid, [k for k in fronts if X[pid == k, 0].mean() > 0])]
        hem = L[:, 2].min()
        xs = []
        z = hps_z - first / 1000
        while z > hem + 0.04:  # the button stand to above the hem's curve
            s = L[np.abs(L[:, 2] - z) < 0.004]
            if len(s):
                xs.append(s[:, 0].min())
            z -= gr.SCAN_STEP_MM / 1000
        if xs:
            out["front_edge_wander_mm"] = round(float(np.ptp(xs)) * 1000, 1)
    vb = fr.get("v_bottom_below_hps_mm")
    if vb and prof:
        top = prof[0][2] + prof[0][3]
        mid = [p for p in prof if abs(p[0] - vb / 2) <= 2 * gr.SCAN_STEP_MM]
        if mid and top > 0:
            out["v_taper"] = round(float((mid[0][2] + mid[0][3]) / top), 2)
    return out


def hem_sleeve(X, M, bV, at) -> dict:
    X = np.asarray(X, float)
    out = {}
    pnl = np.where(_pieces(M, ("front", "back")))[0]
    if len(pnl):
        P = X[pnl]
        cf_y, cb_y = float(at["cf_neck"][1]), float(at["cb_neck"][1])
        mid_y = 0.5 * (cf_y + cb_y)

        def low(m):
            return float(P[m, 2].min()) if m.any() else None
        hz = {"cf": low((np.abs(P[:, 0]) < 0.03) & (P[:, 1] < mid_y)), "cb": low((np.abs(P[:, 0]) < 0.03) & (P[:, 1] > mid_y)),
              "L": low(P[:, 0] > 0.6 * P[:, 0].max()), "R": low(P[:, 0] < 0.6 * P[:, 0].min())}
        if None not in hz.values():
            out["hem_cf_cb_mm"] = round((hz["cb"] - hz["cf"]) * 1000, 1)  # + = the back hangs higher
            out["hem_left_right_mm"] = round(abs(hz["L"] - hz["R"]) * 1000, 1)
    cuff = np.where(_pieces(M, ("cuff",)))[0]
    slv = np.where(_pieces(M, ("cuff", "sleeve")))[0]
    if len(cuff) and "elbow.L" in at and "wrist.L" in at:
        e, w = np.asarray(at["elbow.L"], float), np.asarray(at["wrist.L"], float)
        ax = (w - e) / np.linalg.norm(w - e)
        S = X[slv[X[slv, 0] > 0]]
        t = (S - w) @ ax
        out["sleeve_past_wrist_mm"] = round(float(np.percentile(t, 99)) * 1000, 1)
        C = X[cuff[X[cuff, 0] > 0]]
        bV = np.asarray(bV, float)
        tb = (bV - w) @ ax
        ring = bV[(np.abs(tb) < 0.006) & (np.linalg.norm(bV - w - np.outer(tb, ax), axis=1) < 0.06)]
        if len(ring) > 8:
            from scipy.spatial import ConvexHull
            Q = ring - w
            u = np.cross(ax, [0, 0, 1.0])
            u /= np.linalg.norm(u)
            v = np.cross(ax, u)
            h = ConvexHull(np.c_[Q @ u, Q @ v])
            wrist_g = h.area  # (2D hull: .area is the perimeter)
            tc = (C - w) @ ax
            Qc = C - w - np.outer(tc, ax)
            r = np.linalg.norm(Qc, axis=1)
            out["wrist_girth_mm"] = round(wrist_g * 1000, 1)
            out["cuff_ease_mm"] = round(float(2 * np.pi * np.median(r) - wrist_g) * 1000, 1)
    return out


def reads(X, M, bV, bT, at: dict) -> dict:
    hz = float(np.asarray(at["hps.L"])[2])
    r = {}
    r.update(gr.collar_reads(X, M, hz))
    fr = gr.front_reads(X, M, hz)
    r.update({k: v for k, v in fr.items() if k != "buttons"})
    r.update(collar_extra(X, M, bV, bT, at))
    r.update(front_extra(X, M, fr, hz))
    r.update(hem_sleeve(X, M, bV, at))
    if r.get("v_bottom_below_hps_mm") is not None and r.get("collar_points_below_hps_mean_mm") is not None:
        r["v_below_points_nw"] = round((r["v_bottom_below_hps_mm"] - r["collar_points_below_hps_mean_mm"]) /
                                       max(r.get("neck_width_mm") or _neck_w(at), 1.0), 2)
    return {k: (float(v) if isinstance(v, np.floating) else v) for k, v in r.items()}


def _ref_value(refs: dict | None, garment: str, key: str):
    t = (((refs or {}).get("targets") or {}).get(garment) or {}).get(key) or {}
    return t.get("value") if t.get("visible") else None


def items(M, wear: dict, refs: dict | None = None, garment: str = "shirt") -> list:
    """The structure items this garment has pieces for, with targets for this wear."""
    roles = set(gr._roles(M))
    state = wear.get("state", "closed")
    spread = float(wear.get("spread") or 1.7)
    I = []

    def add(i, read, src, change, stage=1, **tgt):
        I.append(dict(id=i, read=read, on=STAGE, stage=stage, source=src, change=change, **tgt))
    if {"collar_fall", "collar_stand"} <= roles:
        ref_cs = _ref_value(refs, garment, "collar_state")
        if ref_cs is not None:
            add("collar_wear", "wear_collar", f"reference reading collar_state {ref_cs!r}",
                f"wear the collar as the reference shows: chain_garment wear=\"{'open' if ref_cs == 'open' else 'closed'}\"",
                equals="open" if ref_cs == "open" else "closed")
        add("collar_under_jaw", "collar_jaw_clear_mm", "kind default (shirt collar): sits on the neck base, clear of the jaw "
            "with the head level; " + REF_NOTES + ": ~28 mm of neck between the collar's top and the jaw at the side (front "
            "view, 0.46 mm/px), INFERRED >= 20 mm",
            "the collar rides up the neck: lower the CF neckline (alter_pattern move the front neck point down on front.L and "
            "front.R) or a lower stand (design option collar stand height); if the pattern is right, the BAND stage "
            "(chain_garment band_closed / band_open) stands the band upright instead of leaning it on the neck: a build "
            "fault, report it", range=[20.0, None])
        add("collar_tilt", "collar_top_tilt_deg", REF_NOTES + ": the collar's top line tilts ~31 deg in the side view "
            "(back high, front low); +-10 deg",
            "the collar is a level tube: its front must sit lower than its back: drop the CF neckline (alter_pattern move the "
            "front neck point down) and curve the stand's front end up (alter_pattern slash_spread on the stand's top edge); "
            "if the pattern has it, the BAND stage holds the band level: a build fault", range=[21.0, 41.0])
        add("collar_points_drop", "collar_points_below_back_top_mm", REF_NOTES + ": the points ~107 mm below the collar's "
            "back top (side view, 0.55 mm/px); +-20 %",
            "the fall is too shallow / deep at its points: alter_pattern move the collar's point corner (fall) down / up",
            range=[86.0, 128.0])
        if state == "open":
            src = (f"wear open, opening {spread} neck widths (chain_garment.OPEN_SPREAD 1.7 from " + REF_NOTES +
                   ": points ~442 px apart at a ~265 px neck); +-20 %")
            lo, hi = 0.8 * spread, 1.2 * spread
        else:
            src = ("kind default (shirt collar, buttoned): the points spread over the collarbones, a point collar's tips "
                   "~75-130 mm apart (menswear convention 3-5 in, INFERRED) = 0.6-1.1 neck widths")
            lo, hi = 0.6, 1.1
        add("collar_points_spread", "collar_points_apart_nw", src,
            "the points don't spread: the FALL stage keeps the leaves turned in round the neck: check the fall's outer edge "
            "length against the neckline (alter_pattern move the fall's point corner outward = a wider spread); if the cut "
            "reaches, the FALL stage (chain_garment fall_build) doesn't let the leaf turn out: a build fault",
            range=[round(lo, 2), round(hi, 2)])
        add("collar_leaves_lie", "collar_leaf_standoff_p90_mm", f"the fall rests on the cloth under it (chain_garment: "
            f"LAYER + 2 mm = {LAYER_REST_MM:.0f} mm); a coarse panel mesh (20 mm) reads up to ~5 mm more: <= 10 mm",
            "the leaves stand off the shirt (a cone round the neck): the fall's outer edge is too short to lie on the "
            "shoulders (alter_pattern slash_spread the fall's outer edge) or the FALL stage holds it up: a build fault",
            range=[None, 10.0])
        add("collar_turned", "fall_above_stand_mm", "garment_reads.collar_reads: the fall turned down over the stand at CB "
            "(fall above the stand's top < 0)", "the fall stands above the stand: the roll line / fall depth "
            "(alter_pattern on the collar's roll fold) or the FALL stage: a build fault", range=[None, 0.0])
    if "front" in roles:
        add("front_meets", "front_met_share", "wear: the buttoned front meets from the V bottom to the hem (garment_reads "
            "front_state closed: met share >= 0.9, MEET_MM 2 mm)",
            "the fronts gape between buttons: the PLACKETS / soft network leave the CF edges apart: check the closure's "
            "button marks on the pattern (alter_pattern move), else a build fault (chain_garment plackets)", range=[0.9, None])
        add("front_edge_straight", "front_edge_wander_mm", "kind default: a buttoned front edge hangs plumb from the first "
            "fastened button to the hem curve; INFERRED <= 10 mm (under half a 25 mm box placket)",
            "the front edge wanders: the fronts are not the same length either side of CF or the buttons are not evenly "
            "spaced (alter_pattern match the front edges; move button marks); else a build fault (soft network)",
            range=[None, 10.0], stage=2)
        if state == "open":
            add("v_depth", "v_below_points_nw", REF_NOTES + ": the V bottom ~85 px below the higher point at a ~265 px neck "
                "(0.32 neck widths); +-50 %", "the V is too shallow / deep: the first fastened button "
                "(alter_pattern move the front's button marks) or the collar's opening", range=[0.16, 0.48])
            add("v_straight", "v_taper", "kind default: an open shirt front is a straight V: its width at half depth is "
                "half its top width, INFERRED 0.3-0.7", "the V bows: the PLACKETS stage folds the over placket out along a "
                "curve; the fold line must run from the band end to the first fastened button: a build fault",
                range=[0.3, 0.7], stage=2)
    if {"front", "back"} <= roles:
        add("hem_level_lr", "hem_left_right_mm", "kind default: worn straight the hem is level left to right (the pattern "
            "is mirrored); <= 10 mm", "the hem hangs lower one side: front.L / front.R lengths differ (alter_pattern match) "
            "or the soft network starts askew: a build fault", range=[None, 10.0], stage=2)
        add("hem_level_fb", "hem_cf_cb_mm", "kind default (shirt): the back hem no higher than the front, a shirttail back "
            "at most 40 mm lower (INFERRED, dress shirt convention)", "the hem tips front / back: the front and back "
            "lengths at CF / CB (alter_pattern move the hem points), or the soft network rides up: a build fault",
            range=[-40.0, 0.0], stage=2)
    if "cuff" in roles:
        add("sleeve_length", "sleeve_past_wrist_mm", "kind default (shirt): the cuff covers the wrist bone, ending 0-40 mm "
            "past the wrist joint along the arm (INFERRED, dress shirt convention)", "the sleeve is short / long: "
            "alter_pattern move the sleeve's hem points (or the cuff depth); else the RINGS stage placed the cuff off its "
            "length: a build fault", range=[0.0, 40.0], stage=2)
        add("cuff_fit", "cuff_ease_mm", "kind default (shirt cuff, buttoned): the wrist girth + 20-50 mm, a cuff that slides "
            "but doesn't flare (INFERRED, dress shirt convention)", "the cuff is too wide (flares) / tight: alter_pattern "
            "scale the cuff's length (or move its button mark)", range=[20.0, 50.0], stage=2)
    return I


def check(X, M, bV, bT, at: dict, wear: dict, refs: dict | None = None, garment: str = "shirt", waive: dict | None = None) -> dict:
    """{"verdict", "rows", "reads"}: the build measured against its items (rows: garment_reads.checklist_rows)."""
    from . import cloth_check as cc
    r = reads(X, M, bV, bT, at)
    r["wear_collar"] = wear.get("state", "closed")
    its = items(M, wear, refs, garment)
    rows = gr.checklist_rows(its, r, STAGE)
    change = {f"checklist:{it['id']}": it["change"] for it in its}
    for row in rows:
        cid = row["id"]
        row["id"] = cid.split(":", 1)[1]
        row.pop("checklist", None)
        row["measure"] = "chain_structure (the build)"
        if row["status"] in ("FAIL", "UNMEASURED"):
            row["change"] = change[cid]
            if (waive or {}).get(row["id"]):
                row["waived"] = waive[row["id"]]
    rows.sort(key=lambda x: (x["status"] not in ("FAIL", "UNMEASURED"), x["stage"]))
    return {"verdict": cc.verdict(rows, waive), "rows": rows, "reads": r}


def passed(st: dict | None) -> bool:
    return bool(st) and st.get("verdict") in ("PASS", "PASS_WAIVED")


def load_refs(model: str) -> dict | None:
    """The model's saved reference reading (garment_from_reference: <model>/cloth_refs.json), or None."""
    from . import store
    p = Path(store.HOME) / model / "cloth_refs.json"
    try:
        return json.loads(p.read_text()) if p.exists() else None
    except ValueError:
        return None


def row_line(r: dict) -> str:
    vals = ", ".join(f"{v}" for v in r.get("ours", {}).values())
    s = f"  {r['status']} {r['id']}: {vals} (target {r.get('ref')}; {r.get('source', '')[:90]})"
    if r.get("change"):
        s += f"\n      change: {r['change']}"
    if r.get("waived"):
        s += f"\n      waived: {r['waived']}"
    return s
