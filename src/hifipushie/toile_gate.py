"""The TOILE's gate (step 4 of drape first) and its look. Rows (garment_record's gate form: id, status, value, target,
why, back_to):
  girth:<level>   the toile's tape at each step-0 fit level (the convex hull of the MESH's section, the arms and the
                  turned flaps left out) vs the planned garment girth: within GIRTH_TOL_MM (by construction; measured).
  clearance       nothing inside the body: the least distance of the toile's vertices to the body >= 0; the share
                  closer than CLOSE_MM is reported (cloth touching the body there).
  closed          the toile is ONE surface, every edge used by at most two faces, its free edges in the loops its
                  parts make: neck + hem (one loop with the opening), a sleeve hem or an armhole per side.
  neck            no stand at the back: no toile point behind the side neck points above them + NECK_RISE_MM.
  outline:<id>    step 2's traced edge vs the toile's outline seen from the reference's view, LIKE WITH LIKE (the
                  picture's body and pose are not the model's): a side outline as its PROFILE (distance off the toile's
                  torso edge less its median; the width is the girth rows'; the arm zone above the underarm left out),
                  a hem as its HEIGHT (median), a sleeve end as its LENGTH past the wrist (each read from its own
                  wrist along the arm, signed, within SLEEVE_MM);
                  p95 within SILHOUETTE_MM for KINDS_GATED, the rest (an edge the closed toile can't show open, a
                  collar not built here) INFO.
The look: the toile with its parts beside the reference, four views, shape only (every number in the text answer)."""
from __future__ import annotations

import numpy as np
from scipy.spatial import ConvexHull, cKDTree

from .toile_geom import boundary_loops, edge_counts, render, sheet, slice_points, zbuffer

GIRTH_TOL_MM = 6.0    # a tape read on a 6 mm grid's surface
CLOSE_MM = 2.0        # cloth closer than this to the body is touching it
NECK_RISE_MM = 3.0    # the back neck may rise this far over the side neck points (no stand)
SLEEVE_MM = 10.0      # the sleeve's length past the wrist, toile vs trace (signed)
SILHOUETTE_MM = 20.0  # a toile is the shape before the hang: its outline within 2 cm of the traced edge
KINDS_GATED = ("hem", "outline", "sleeve_end")
ARM_ZONE_M = 0.03     # the side outline above the underarm less this is the picture's arm pose, not the toile
DEPTH_STEP_M = 0.03   # an outline inside the silhouette: the depth jumps this much between neighbouring pixels
LOOK_BOX = None


def girth_rows(t) -> list:
    V, F = t.meshes["toile"]
    rows = []
    for n, (z, plan) in sorted(t.inp.levels.items(), key=lambda kv: -kv[1][0]):
        zz = max(z, t.hem + 0.004)
        P = slice_points(V, F, zz)
        P = P[t.armness(P) < 0.5] if len(P) else P
        g = ConvexHull(P[:, :2]).area if len(P) > 3 else 0.0
        d = (g - plan) * 1000
        rows.append({"id": f"girth:{n}", "status": "PASS" if abs(d) <= GIRTH_TOL_MM else "FAIL",
                     "value": round(g * 1000, 1), "target": f"{plan * 1000:.1f} mm (step 0's plan) +-{GIRTH_TOL_MM:g}",
                     "why": f"{d:+.1f} mm at z {zz:.3f}", "back_to": "4" if abs(d) > GIRTH_TOL_MM else None})
    return rows


def clearance_row(t) -> dict:
    V = np.concatenate([t.meshes[k][0] for k in t.meshes if not k.startswith("pad")])
    s = t.CT.query(V)[0]
    mn = float(s.min()) * 1000
    close = float(np.mean(s < CLOSE_MM / 1000) * 100)
    return {"id": "clearance", "status": "PASS" if mn >= 0 else "FAIL", "value": round(mn, 1),
            "target": "least distance to the body >= 0 mm", "why": f"{close:.1f} % of the toile within {CLOSE_MM:g} mm "
            f"of the body; {int((s < 0).sum())} vertices inside" + (f", the deepest at {np.round(V[np.argmin(s)], 3).tolist()}"
            if mn < 0 else ""), "back_to": "4" if mn < 0 else None}


def closed_row(t) -> dict:
    from .toile_geom import components
    V, F = t.meshes["toile"]
    ncomp = int(components(F, len(V)).max() + 1)
    _, c = edge_counts(F)
    nonman = int((c > 2).sum())
    loops = boundary_loops(F)
    want = (1 if "opening" in t.parts else 2) + 2  # neck + hem (one loop when open) + two sleeve hems / armholes
    ok = ncomp == 1 and nonman == 0 and len(loops) == want
    return {"id": "closed", "status": "PASS" if ok else "FAIL", "value": len(loops),
            "target": f"one surface, no edge on 3+ faces, {want} free loops", "back_to": None if ok else "4",
            "why": f"{ncomp} component(s), {nonman} non-manifold edges, free loops of {sorted(len(l) for l in loops)} edges"}


def neck_row(t) -> dict:
    """No stand at the back neck: no toile point behind the side neck points higher than them + NECK_RISE_MM (a cut at
    the neck tape's back, where the neck turns vertical, climbs the back of the neck)."""
    nl = t.info.get("neckline")
    if not nl:
        return {"id": "neck", "status": "INFO", "value": None, "target": "read", "why": "no neckline read", "back_to": None}
    V = t.meshes["toile"][0]
    B = V[V[:, 1] > nl["hps_y"]]
    rise = (float(B[:, 2].max()) - nl["hps_z"]) * 1000 if len(B) else -np.inf
    ok = rise <= NECK_RISE_MM
    return {"id": "neck", "status": "PASS" if ok else "FAIL", "value": round(rise, 1),
            "target": f"the back no higher than the side neck points + {NECK_RISE_MM:g} mm", "back_to": None if ok else "4",
            "why": f"the back's top {rise:+.1f} mm off the side neck points (z {nl['hps_z']:.3f}); centre back cut at z "
                   f"{nl.get('cb_z', float('nan')):.3f} (the neck tape crosses it at {nl.get('cb_z_tape', float('nan')):.3f})"}


def _outline_px(t, view, box, mpp):
    """The toile's outline in the view, as (u, v) pixels: the silhouette's border + the parts' front-facing free edges."""
    meshes = [(V, F, np.full((len(F), 3), 200)) for k, (V, F) in t.meshes.items() if not k.startswith("pad")]
    _, zb = zbuffer(meshes, view, box, mpp)
    m = np.isfinite(zb)
    edge = m & ~(np.roll(m, 1, 0) & np.roll(m, -1, 0) & np.roll(m, 1, 1) & np.roll(m, -1, 1))
    zf = np.where(m, zb, 1e3)  # (and where one part passes in front of another: a sleeve over the side seam's edge)
    edge |= m & ((np.abs(zf - np.roll(zf, 1, 0)) > DEPTH_STEP_M) | (np.abs(zf - np.roll(zf, 1, 1)) > DEPTH_STEP_M))
    vv, uu = np.nonzero(edge)
    pts = [np.c_[uu, vv].astype(float)]
    (u0, _), (_, z1) = box
    sg = 1.0 if view == "front" else -1.0
    for k, (V, F) in t.meshes.items():
        if k.startswith("pad"):
            continue
        for lp in boundary_loops(F):
            P = V[lp]
            u, v = (sg * P[:, 0] - u0) / mpp, (z1 - P[:, 2]) / mpp
            d = sg * P[:, 1]
            ui, vi = np.clip(u.astype(int), 0, zb.shape[1] - 1), np.clip(v.astype(int), 0, zb.shape[0] - 1)
            seen = d <= zb[vi, ui] + 0.012
            pts.append(np.c_[u[seen], v[seen]])
    return np.concatenate(pts)


def _torso_edges(mask, uc):
    """Per pixel row, the torso's outline columns (left, right): walked out from the centre column uc until the
    silhouette ends (a hanging hand beside the hip is not the torso's edge); -1 where the row is empty at the centre."""
    H, W = mask.shape
    lo, hi = np.full(H, -1), np.full(H, -1)
    for r in range(H):
        row = mask[r]
        if not row[uc]:
            continue
        gl = np.nonzero(~row[:uc])[0]
        gr_ = np.nonzero(~row[uc:])[0]
        lo[r] = (gl[-1] + 1) if len(gl) else 0
        hi[r] = (uc + gr_[0] - 1) if len(gr_) else W - 1
    return lo, hi


def _like_rows(t, tid, tr, mask, box, mpp, sg):
    """A side outline or a hem compared like with like (the picture's body is not the model's): a SIDE as its profile
    (the traced edge's distance off the toile's torso edge, less its median: the width itself is the girth rows'),
    skipping the arm zone above the toile's underarm less ARM_ZONE_M (there the picture's outline is its arm pose);
    a HEM as its height (the toile's lowest point in each traced column; columns past the toile's width left out)."""
    (u0, _), (_, z1) = box
    xz = np.asarray(tr["xz"], float)
    u = np.clip(((sg * xz[:, 0] - u0) / mpp).astype(int), 0, mask.shape[1] - 1)
    v = np.clip(((z1 - xz[:, 1]) / mpp).astype(int), 0, mask.shape[0] - 1)
    uc = int(round(-u0 / mpp))  # (the centre line x = 0 in either view)
    lo, hi = _torso_edges(mask, uc)
    if tr.get("what") == "hem":
        cols = [np.nonzero(mask[:, c])[0] for c in u]
        rh = max(int(np.nonzero(lo >= 0)[0].max()) - 2, 0)  # (the torso's width just above its hem)
        keep = np.array([len(c) > 0 for c in cols]) & (u >= lo[rh]) & (u <= hi[rh])
        if not keep.any():
            return None
        dz = np.array([(c.max() - vv) * mpp * 1000 for c, vv, k in zip(cols, v, keep) if k])
        off, n = float(np.median(dz)), int(keep.sum())
        d = np.array([abs(off)])  # (the hem's HEIGHT is one number; its curve up to the front edge is the opening's)
        how = (f"the hem's height: the toile's hem {abs(off):.1f} mm {'below' if off > 0 else 'above'} the traced one "
               f"(median over {n} columns inside the toile's width; the range {dz.min():+.1f} .. {dz.max():+.1f} mm)")
    else:
        ua = float(t.info.get("armhole", {}).get("underarm_z", np.inf)) - ARM_ZONE_M
        keep = (xz[:, 1] < ua) & (lo[v] >= 0)
        if keep.sum() < 3:
            return None
        edge = np.where(u > uc, hi[v], lo[v])
        dx = (np.abs(u - uc) - np.abs(edge - uc))[keep] * mpp * 1000
        off = float(np.median(dx))
        d, n = np.abs(dx - off), int(keep.sum())
        how = (f"the side's profile below z {ua:.3f} (the arm zone left out): the traced edge {off:+.1f} mm (median) "
               f"outside the toile's: that offset read, not gated (the picture's body is not the model's: the girth rows gate the width)")
    return d, how, xz[keep]


def _sleeve_end(t, tr):
    """A sleeve end compared as the sleeve's LENGTH past the WRIST, each read from its own wrist along the arm (the
    picture's arm is not the model's: across leaks into along when both are read on one axis): the traced end past the
    picture's wrist mark less the toile's hem past the model's wrist, signed (+ = the toile's sleeve is short); FAIL
    past SLEEVE_MM either way. Without step 2's wrist marks: INFO."""
    from .toile_style import along_from_wrist, arm_dir
    s = t.info.get("sleeve", {})
    if "sleeves" not in t.parts or "hem_at" not in s:
        return None
    w = t.inp.wrists or {}
    if "photo" not in w or "model" not in w:
        return {"status": "INFO", "value": None, "why": "step 2 has no wrist body marks: the sleeve's length not compared"}
    st = along_from_wrist(t, np.asarray(tr["xz"], float), w["photo"])
    sh = float((np.asarray(s["hem_at"], float) - np.asarray(w["model"], float)) @ arm_dir(t))
    d = (st - sh) * 1000
    ok = abs(d) <= SLEEVE_MM
    from_trace = t.d["sleeves"]["hem"] in t.inp.traces
    why = (f"the sleeve's length past the wrist: traced {st * 1000:+.1f} mm past the picture's wrist, the toile's hem "
           f"{sh * 1000:+.1f} mm past the model's: the toile {abs(d):.1f} mm {'short' if d > 0 else 'long'} "
           f"(hem from {s.get('hem_from', '?')})")
    back = None
    if not ok:
        back = "4" if from_trace else "0"
        why += "" if from_trace else ": step 0's height and step 2's trace disagree: declare sleeves.hem as the trace"
    return {"status": "PASS" if ok else "FAIL", "value": round(d, 1), "why": why, "back_to": back,
            "target": f"signed, within +-{SLEEVE_MM:g} mm (+ = short)"}


def outline_rows(t, view="front") -> list:
    if not t.inp.traces:
        return []
    box, mpp = ((t.xs[0], t.xs[-1]), (t.zs[0] - 0.05, t.zs[-1])), 0.002
    if view not in ("front", "back"):
        return [{"id": "outline", "status": "INFO", "why": f"the reference's view {view!r}: only front / back compared"}]
    O = _outline_px(t, view, box, mpp) * mpp * 1000
    kd = cKDTree(O)
    torso = [(V, F, np.full((len(F), 3), 200)) for k, (V, F) in t.meshes.items() if k == "toile"]
    mask = np.isfinite(zbuffer(torso, view, box, mpp)[1])
    (u0, _), (_, z1) = box
    sg = 1.0 if view == "front" else -1.0
    rows = []
    for tid, tr in sorted(t.inp.traces.items()):
        what = tr.get("what")
        xz = np.asarray(tr["xz"], float)
        if what == "sleeve_end":
            r = _sleeve_end(t, tr)
            if r is not None:
                rows.append(dict({"id": f"outline:{tid}", "target": "read", "back_to": None}, **r))
                continue
        like = _like_rows(t, tid, tr, mask, box, mpp, sg) if what in ("hem", "outline") else None
        if like is not None:
            d, how, xz = like
        else:
            P = np.c_[(sg * xz[:, 0] - u0) / mpp, (z1 - xz[:, 1]) / mpp] * mpp * 1000
            d = kd.query(P)[0]
            how = ""
        p95, mx = float(np.percentile(d, 95)), float(d.max())
        worst = xz[int(np.argmax(d))] if len(d) == len(xz) else xz[int(np.argmin(np.abs(xz[:, 1] - np.median(xz[:, 1]))))]
        gated = what in KINDS_GATED
        st = ("PASS" if p95 <= SILHOUETTE_MM else "FAIL") if gated else "INFO"
        back = None
        if st == "FAIL":
            back = "4"
        why = (f"p95 {p95:.1f} / max {mx:.1f} mm; worst at x {worst[0]:.3f} z {worst[1]:.3f}" + (f"; {how}" if how else "") +
               ("" if gated else f" (a {what} edge: the toile is built closed / without it; read, not gated)"
                if what != "outline" else ""))
        rows.append({"id": f"outline:{tid}", "status": st, "value": round(p95, 1),
                     "target": f"p95 <= {SILHOUETTE_MM:g} mm" if gated else "read", "why": why, "back_to": back})
    return rows


def rows(t, view="front") -> list:
    return girth_rows(t) + [clearance_row(t), closed_row(t), neck_row(t)] + outline_rows(t, view)


def verdict(rs: list) -> str:
    return "FAIL" if any(r["status"] == "FAIL" for r in rs) else "PASS"


COLOURS = {"toile": (150, 160, 185), "lapel": (120, 135, 170), "pad": (230, 200, 90)}


def look(t, body_V, body_T, ref, path, traces3d=()):
    """The toile beside the reference: four views, the traced edges drawn on the front (red)."""
    skin = (body_V, body_T, np.tile([[200, 170, 150]], (len(body_T), 1)))
    M = [skin] + [(V, F, np.tile([COLOURS[k.split(".")[0]]], (len(F), 1))) for k, (V, F) in t.meshes.items()
                  if not k.startswith("pad")]
    box = ((t.xs[0] - 0.02, t.xs[-1] + 0.02), (t.zs[0] - 0.08, t.zs[-1] + 0.04))
    sbox = ((t.ys[0] - 0.15, t.ys[-1] + 0.15), box[1])
    tiles = [render(M, lines=[(P, (220, 30, 30), 2) for P in traces3d] if v == "front" else (), view=v,
                    box=box if v in ("front", "back") else sbox) for v in ("front", "left", "back", "right")]
    sheet(tiles, ref, labels=["reference", "front (traces red)", "left", "back", "right"]).save(path)
    return path
