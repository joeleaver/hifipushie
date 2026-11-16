"""The TOILE's gate (step 4 of drape first) and its look. Rows (garment_record's gate form: id, status, value, target,
why, back_to):
  girth:<level>   the toile's tape at each step-0 fit level (the convex hull of the MESH's section, the arms and the
                  turned flaps left out) vs the planned garment girth: within GIRTH_TOL_MM (by construction; measured).
  clearance       nothing inside the body: the least distance of the toile's vertices to the body >= 0; the share
                  closer than CLOSE_MM is reported (cloth touching the body there).
  closed          the toile is ONE surface, every edge used by at most two faces, its free edges in the loops its
                  parts make: neck + hem (one loop with the opening), a sleeve hem or an armhole per side.
  outline:<id>    step 2's traced edge vs the toile's outline seen from the reference's view (its silhouette and
                  its parts' free edges, front-facing, and where one part passes in front of another), mm off per trace point: p95 within SILHOUETTE_MM for the
                  edges the toile builds in the reference's own state (KINDS_GATED); the rest (an edge the closed toile
                  can't show open, a collar not built here) INFO.
The look: the toile with its parts beside the reference, four views, shape only (every number in the text answer)."""
from __future__ import annotations

import numpy as np
from scipy.spatial import ConvexHull, cKDTree

from .toile_geom import boundary_loops, edge_counts, render, sheet, slice_points, zbuffer

GIRTH_TOL_MM = 6.0    # a tape read on a 6 mm grid's surface
CLOSE_MM = 2.0        # cloth closer than this to the body is touching it
SILHOUETTE_MM = 20.0  # a toile is the shape before the hang: its outline within 2 cm of the traced edge
KINDS_GATED = ("hem", "outline", "sleeve_end")
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


def outline_rows(t, view="front") -> list:
    if not t.inp.traces:
        return []
    box, mpp = ((t.xs[0], t.xs[-1]), (t.zs[0] - 0.05, t.zs[-1])), 0.002
    if view not in ("front", "back"):
        return [{"id": "outline", "status": "INFO", "why": f"the reference's view {view!r}: only front / back compared"}]
    O = _outline_px(t, view, box, mpp) * mpp * 1000
    kd = cKDTree(O)
    (u0, _), (_, z1) = box
    sg = 1.0 if view == "front" else -1.0
    rows = []
    for tid, tr in sorted(t.inp.traces.items()):
        xz = np.asarray(tr["xz"], float)
        P = np.c_[(sg * xz[:, 0] - u0) / mpp, (z1 - xz[:, 1]) / mpp] * mpp * 1000
        d = kd.query(P)[0]
        p95, mx = float(np.percentile(d, 95)), float(d.max())
        gated = tr.get("what") in KINDS_GATED
        st = ("PASS" if p95 <= SILHOUETTE_MM else "FAIL") if gated else "INFO"
        worst = xz[int(np.argmax(d))]
        why = (f"p95 {p95:.1f} / max {mx:.1f} mm; worst at x {worst[0]:.3f} z {worst[1]:.3f}" +
               ("" if gated else f" (a {tr.get('what')} edge: the toile is built closed / without it; read, not gated)"))
        rows.append({"id": f"outline:{tid}", "status": st, "value": round(p95, 1),
                     "target": f"p95 <= {SILHOUETTE_MM:g} mm" if gated else "read", "why": why,
                     "back_to": "4" if st == "FAIL" else None})
    return rows


def rows(t, view="front") -> list:
    return girth_rows(t) + [clearance_row(t), closed_row(t)] + outline_rows(t, view)


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
