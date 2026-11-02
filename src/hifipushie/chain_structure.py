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

ROWS (C288, `items`): from the garment record, never a garment's conventions in code. Step 2's rows (and its numeric
bends) are judged by their kind (structure_rows.KINDS: the one vocabulary garment_plan validates against) with the plan's
target and source; general rules (structure_rows.rule_items: a fall lies down, the hem level left to right, each closure in
its planned state, soft cloth not crumpled) are added with the rule as their source. No style plan, or a row with no build
reading yet: UNMEASURED, named (the gate never passes it silently; waive by name with a reason).
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from . import garment_reads as gr, structure_rows as sr

STAGE = "build"
BAND_SHUT_MM = 5.0  # a band's ends this close are shut (its button's overlap holds them together)
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
    fr_c = P[P[:, 1] < cf[1] + 0.03]
    if len(fr_c):  # the collar's height at its front: the 20 mm band nearest CF
        ax = np.abs(fr_c[:, 0])
        out["collar_front_height_mm"] = round(float(np.ptp(fr_c[ax <= ax.min() + 0.02, 2])) * 1000, 1)
    fb = X[fall][(np.abs(X[fall, 0]) < 0.015) & (X[fall, 1] > cb[1] - 0.03)]
    if len(fb):
        out["collar_fall_cb_width_mm"] = round(float(np.ptp(fb[:, 2])) * 1000, 1)
    stn = X[np.where(_pieces(M, ("collar_stand",)))[0]]
    sf = stn[stn[:, 1] < cf[1] + 0.03]
    sl, sr_ = sf[sf[:, 0] > 0], sf[sf[:, 0] <= 0]
    if len(sl) and len(sr_):  # a band closing on itself: its two front ends touch (<= BAND_SHUT_MM) or stand apart
        from scipy.spatial import cKDTree
        g = float(cKDTree(sl).query(sr_)[0].min()) * 1000
        out["band_ends_gap_mm"] = round(g, 1)
        out["band_state"] = "closed" if g <= BAND_SHUT_MM else "open"
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
            k = max(int(round(40 / gr.SCAN_STEP_MM)), 1)  # the edge off vertical over each 40 mm: a kink shows
            if len(xs) > k:
                dx = np.abs(np.asarray(xs[k:]) - np.asarray(xs[:-k]))
                out["front_edge_kink_deg"] = round(float(np.degrees(np.arctan2(dx.max(), k * gr.SCAN_STEP_MM / 1000))), 1)
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
    X = np.asarray(X, float)
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
    pts = r.get("collar_points_below_hps_mm")
    if r.get("v_bottom_below_hps_mm") is not None and pts:
        r["v_below_points_mm"] = round(r["v_bottom_below_hps_mm"] - min(pts), 1)  # below the HIGHER point
    if "shoulder.L" in at:
        r["shoulder_width_mm"] = round(2 * abs(float(np.asarray(at["shoulder.L"])[0])) * 1000, 1)
    fz = X[np.where(_pieces(M, ("front",)))[0]]
    fz = fz[np.abs(fz[:, 0]) < 0.03] if len(fz) else fz
    if len(fz):
        r["closure_length_mm"] = round(float(np.ptp(fz[:, 2])) * 1000, 1)
    return {k: (float(v) if isinstance(v, np.floating) else v) for k, v in r.items()}


def items(M, plan: dict | None) -> tuple[list, list]:
    """(items, notes): the style plan's rows (structure_rows.plan_items) + the general rules for this build's pieces."""
    roles = set(gr._roles(M))
    if not (plan or {}).get("style"):
        its = [dict(id="style_plan", read="unmeasured:style_plan", range=[None, None], stage=1,
                    source="garment record step 2", missing="no style plan in the garment record",
                    change="garment_plan(step=\"style\") writes the targets this gate judges (back to step 2)")]
        notes = []
    else:
        its, notes = sr.plan_items(plan, roles)
    cl = sr.closure_reads(plan.get("parts") if plan else None, ((plan or {}).get("style") or {}).get("state") or {})
    its = its + sr.rule_items(roles, sr.soft_pieces(M, (plan or {}).get("parts")), cl)
    for it in its:
        it["on"] = STAGE
    return its, notes


def _plan_reads(X, M, r: dict, its: list, plan: dict | None) -> None:
    """Readings the items name beyond reads(): closure states, roughness, ratios ("a/b")."""
    st = ((plan or {}).get("style") or {}).get("state") or {}
    for c, x in sr.closure_reads((plan or {}).get("parts"), st).items():
        v = r.get(x["read"]) if x["read"] else None
        r[f"closure_state:{c}"] = None if v is None else next(
            (k for k, w in sr.STATE_OF[x["read"]].items() if w == v and k == x["state"]), v)
    soft = sr.soft_pieces(M, (plan or {}).get("parts"))
    if soft:
        rough = sr.roughness(X, M, soft)
        r["soft_rough"] = rough
        if rough:
            r["soft_rough_over_limit"] = round(max(v["bump_p90_mm"] / v["limit_mm"] for v in rough.values()), 2)
    for it in its:
        k = it["read"] if isinstance(it["read"], str) else ""
        if "/" in k and ":" not in k:
            a, b = (r.get(x) for x in k.split("/"))
            r[k] = round(a / b, 3) if a is not None and b else None


def check(X, M, bV, bT, at: dict, wear: dict, plan: dict | None = None, waive: dict | None = None) -> dict:
    """{"verdict", "rows", "reads", "notes"}: the build measured against the record's rows (garment_reads.checklist_rows)."""
    from . import cloth_check as cc
    r = reads(X, M, bV, bT, at)
    its, notes = items(M, plan)
    _plan_reads(X, M, r, its, plan)
    rows = gr.checklist_rows(its, r, STAGE)
    by = {f"checklist:{it['id']}": it for it in its}
    for row in rows:
        cid = row["id"]
        it = by[cid]
        row["id"] = cid.split(":", 1)[1]
        row.pop("checklist", None)
        row["measure"] = "chain_structure (the build)"
        if it.get("missing"):
            row.update(status="UNMEASURED", why=it["missing"], ours={}, read=[])
        if row["status"] in ("FAIL", "UNMEASURED"):
            row["change"] = it["change"]
            if (waive or {}).get(row["id"]):
                row["waived"] = waive[row["id"]]
    rows.sort(key=lambda x: (x["status"] not in ("FAIL", "UNMEASURED"), x["stage"]))
    return {"verdict": cc.verdict(rows, waive), "rows": rows, "reads": r, "notes": notes}


def passed(st: dict | None) -> bool:
    return bool(st) and st.get("verdict") in ("PASS", "PASS_WAIVED")


def load_plan(model: str, garment: str) -> dict | None:
    """The garment record's steps 0-2 outputs ({read, parts, style}), or None (no record)."""
    from . import garment_record as grec
    p = grec.path(model, garment)
    try:
        st = json.loads(p.read_text()).get("steps") or {} if p.exists() else None
    except ValueError:
        return None
    if st is None:
        return None
    return {k: (st.get(n) or {}).get("output") for k, n in (("read", "0"), ("parts", "1"), ("style", "2"))}


def row_line(r: dict) -> str:
    vals = ", ".join(f"{v}" for v in r.get("ours", {}).values())
    s = f"  {r['status']} {r['id']}: {vals} (target {r.get('ref')}; {r.get('source', '')[:90]})"
    if r.get("change"):
        s += f"\n      change: {r['change']}"
    if r.get("waived"):
        s += f"\n      waived: {r['waived']}"
    return s
