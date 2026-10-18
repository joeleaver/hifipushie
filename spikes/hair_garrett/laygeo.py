"""laygeo.py <model> [patch.json] [patch2.json ...]: the loose groom's LAY measured on the lock geometry, before any
render (the texture items lay_top / stand-off of the checklist, on the curves).

Each patch is {"groom": {...}} deep-merged into the model's groom (in memory: nothing is saved); with none, the model
as it is. Per variant, over lock points of the top-front (|az| < 45 deg, el from the hairline to 70 deg):
  rise    : the lock's climb off the scalp, deg (atan of d height / d arc), length-weighted median and p75: a lying lock
            is under ~15, a standing root 40+
  img3q / imgpro : the visible segments' angle to the image horizontal in an orthographic yaw 45 / yaw -90 view (axial
            0-90, as texmeas's `lay`), length-weighted mean over the top's silhouette band (|n.view| < .5, n_z > .4)
  standoff: p90 height of the lock points over the scalp above the front hairline (|az| < 15, hairline + 2..20 deg), mm
  dip5 / dipmax: locks whose points reach > 5 deg below the front hairline (|az| < 40), the deepest (deg)
  tipdrop : median (height at the lock's highest point - height at its tip), mm: > 0 = it lies down toward the tip
Calibration (2026-10-16): G56r / G58r rendered lay_top 59 / 48 (3q), stand-off 14.6 / 11.2 mm."""
import copy
import json
import sys

import numpy as np

from hifipushie import hair, hair_loose as hl, store


def merge(a, b):
    for k, v in b.items():
        if isinstance(v, dict) and isinstance(a.get(k), dict):
            merge(a[k], v)
        else:
            a[k] = copy.deepcopy(v)
    return a


def measure(sc, g, col):
    line = hair.hairline(sc, g)
    locks = hl.grow(sc, g, line, np.random.default_rng(int(g.get("seed", 0))), col)
    rise_w, rise_v, segs, sel_pts, drops, dips = [], [], [], [], [], []
    for lk in locks.values():
        P = np.asarray(lk["pts"], float) + sc.C
        a, e, h = sc.coords(P)
        a = ((a + 180) % 360) - 180
        if not (abs(a[0]) < 45 and e[0] < 70):
            continue
        ds = np.linalg.norm(np.diff(P, axis=0), axis=1)
        dh = np.diff(h)
        rise_v.append(np.degrees(np.arctan2(dh, np.maximum(ds, 1e-9))))
        rise_w.append(ds)
        segs.append((P[:-1], np.diff(P, axis=0)))
        drops.append(float(h.max() - h[-1]))
    for lk in locks.values():
        P = np.asarray(lk["pts"], float) + sc.C
        a, e, h = sc.coords(P)
        a = ((a + 180) % 360) - 180
        ln = hair._line_at(line, a)
        k = (np.abs(a) < 15) & (e > ln + 2) & (e < ln + 20)
        sel_pts.append(h[k])
        if abs(a[0]) < 60 and ((np.abs(a[3:]) < 40) & (e[3:] < ln[3:] - 5)).any():
            dips.append(float((ln[3:] - e[3:])[np.abs(a[3:]) < 40].max()))
    rv, rw = np.concatenate(rise_v), np.concatenate(rise_w)
    o = np.argsort(rv)
    cw = np.cumsum(rw[o]) / rw.sum()
    out = {"locks": len(rise_v), "rise": float(rv[o][np.searchsorted(cw, 0.5)]),
           "rise75": float(rv[o][np.searchsorted(cw, 0.75)])}
    X = np.concatenate([s[0] for s in segs]); D = np.concatenate([s[1] for s in segs])
    for name, yaw in (("img3q", 45.0), ("imgpro", -90.0)):
        t = np.radians(yaw)
        view = np.array([-np.sin(t), np.cos(t), 0.0])  # camera looks along +y at yaw 0 (the face is at -y)
        right = np.cross(view, [0, 0, 1.0])
        nrm = hair._unit(X - sc.C) if hasattr(hair, "_unit") else (X - sc.C) / np.linalg.norm(X - sc.C, axis=1)[:, None]
        vis = (np.abs(nrm @ view) < 0.5) & (nrm[:, 2] > 0.4)  # the top silhouette band (texmeas's top_front crops)
        dx, dz = np.abs(D @ right), np.abs(D[:, 2])
        ang = np.degrees(np.arctan2(dz, np.maximum(dx, 1e-12)))
        w = np.hypot(dx, dz) * vis
        out[name] = float((ang * w).sum() / max(w.sum(), 1e-12))
    hp = np.concatenate(sel_pts) if sel_pts else np.zeros(1)
    out["standoff"] = float(np.percentile(hp, 90) * 1000) if len(hp) else float("nan")
    out["tipdrop"] = float(np.median(drops) * 1000)
    out["dip5"] = len(dips)  # locks reaching > 5 deg below the front hairline (|az| < 40): the front-reach limit
    out["dipmax"] = float(max(dips, default=0.0))
    return out


if __name__ == "__main__":
    m = sys.argv[1]
    spec = store.load(m)
    sc = hair.scalp(m, spec)
    col = hl.collider(m, spec, sc)
    base = hair.groom_params(spec)
    for pf in [None] + sys.argv[2:]:
        g = copy.deepcopy(base)
        if pf:
            merge(g, json.load(open(pf)).get("groom", {}))
        r = measure(sc, hair.fit_to_head(g, sc), col)
        print(f"{pf or m:<40} " + " ".join(f"{k} {v:.1f}" if isinstance(v, float) else f"{k} {v}" for k, v in r.items()),
              flush=True)
