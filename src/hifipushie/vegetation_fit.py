"""Fitting a habit to a reference silhouette, and form across ages and settings. Part of vegetation (vegetation.py has the overview)."""
from __future__ import annotations

import copy
import json
import math

import numpy as np

from . import vegetation
from .vegetation import _merge, resolve
from .vegetation_grow import grow
from .vegetation_measures import branch_angles, outline_iou, shape_measures, silhouette, tree_branch_directions

# ---------------------------------------------------------------- fitting a habit to a reference silhouette
def _set_path(d: dict, path: str, value):
    """habit key 'apical.0' = element 0 of the list (a scalar becomes a list)."""
    k, _, i = path.partition(".")
    if not i:
        d[k] = value
        return
    lst = list(d[k]) if isinstance(d.get(k), (list, tuple)) else [d.get(k)]
    while len(lst) <= int(i):
        lst.append(lst[-1])
    lst[int(i)] = value
    d[k] = lst


def match(tree: dict, ref_mask: np.ndarray, bare: bool = False, azimuths=(0, 90), px_per_m: float = 12.0) -> dict:
    """How a grown tree compares with a reference silhouette: outline IoU (best azimuth) and both sets of measures."""
    mr = shape_measures(ref_mask)
    best = None
    for az in azimuths:
        m, _ = silhouette(tree, az, px_per_m, leaves=not bare)
        iou = outline_iou(ref_mask, m)
        if best is None or iou > best[0]:
            best = (iou, az, m)
    mo = shape_measures(best[2])
    keys = ("width_over_height", "bole", "widest_at", "crown_aspect", "lopsided", "porosity")
    return {"iou": best[0], "azimuth": best[1], "ours": {k: mo[k] for k in keys}, "ref": {k: mr[k] for k in keys},
            "mask": best[2]}


def droop(tree: dict, bole: float) -> float:
    """Share of the shoot ends hanging under the crown's base (bole x height), more than 1.5 m out from the trunk:
    limbs drooped to the ground, which an outline fit would otherwise reward."""
    e = tree["pos"][tree["ends"]]
    if not len(e):
        return 0.0
    low = (e[:, 2] < bole * tree["height"] * 0.85) & (np.linalg.norm(e[:, :2], axis=1) > 1.5)
    return float(low.mean())


def fit_habit(spec: dict, ref_mask: np.ndarray, params: dict, bare: bool = False, iters: int = 60, seeds=(1, 2),
              nodes=(3000, 30000), rng_seed: int = 0, log=None, directions: dict | None = None,
              elevation: tuple | None = None, droop_max: float | None = None) -> dict:
    """Search habit numbers so the grown tree's outline matches a reference: `params` = {habit path: [lo, hi]}
    ("apical.0" = the list's element 0; integer bounds stay integers). Random search, then shrinking steps round
    the best; scored on outline IoU over `seeds` minus misses in width/height and bole, and node counts outside
    `nodes`. Returns {"habit": the fitted overrides, "score", "iou", "log"}. A fit's numbers go into a preset or a
    spec; nothing is kept hidden."""
    rng = np.random.default_rng(rng_seed)
    names = list(params)
    lo = np.array([params[k][0] for k in names], float)
    hi = np.array([params[k][1] for k in names], float)
    isint = [all(isinstance(v, int) for v in params[k]) for k in names]
    base = resolve(spec)["habit"]

    def vec0():
        out = []
        for k in names:
            a, _, i = k.partition(".")
            v = base[a]
            v = (v[min(int(i), len(v) - 1)] if isinstance(v, list) else v) if i else v
            out.append(float(v if v is not None else 0.5 * (params[k][0] + params[k][1])))
        return np.clip(np.array(out), lo, hi)

    def score(x):
        hb = {}
        full = copy.deepcopy(base)
        for k, v, ii in zip(names, x, isint):
            _set_path(full, k, int(round(v)) if ii else round(float(v), 4))
        for k in {n.partition(".")[0] for n in names}:
            hb[k] = full[k]
        tot, ious = 0.0, []
        for sd in seeds:
            sp = _merge(spec, {"seed": sd, "habit": hb})
            sp.pop("height", None)
            T = grow(sp)
            m = match(T, ref_mask, bare=bare)
            n = T["stats"]["nodes"]
            pen = abs(m["ours"]["width_over_height"] - m["ref"]["width_over_height"]) * 0.3 \
                + abs(m["ours"]["bole"] - m["ref"]["bole"]) * 0.8 \
                + 1.5 * max(0.0, droop(T, m["ref"]["bole"]) - (0.02 if droop_max is None else droop_max)) \
                + 0.15 * max(0.0, math.log(nodes[0] / max(n, 1))) + 0.15 * max(0.0, math.log(n / nodes[1]))
            if directions:  # branch directions against the winter photo's (deg from vertical)
                dv = tree_branch_directions(T, m["azimuth"], directions["height_px"])
                pen += 0.006 * abs(dv["p50"] - directions["p50"]) + 0.3 * abs(dv["level"] - directions["level"])
            if elevation:  # the first-order limbs' far halves, inside a stated band (deg above level)
                el = branch_angles(T, 1)["elevation_p10_50_90"]
                if el:
                    pen += 0.006 * (max(0.0, elevation[0] - el[1]) + max(0.0, el[1] - elevation[1]))
            tot += m["iou"] - pen
            ious.append(m["iou"])
        return tot / len(seeds), float(np.mean(ious)), hb

    x = vec0()
    best = (*score(x), x)
    hist = [(round(best[0], 3), round(best[1], 3))]
    for it in range(iters):
        if it < iters // 2:
            c = lo + rng.random(len(names)) * (hi - lo) if it % 3 == 0 else np.clip(best[3] + rng.normal(0, 0.25, len(names)) * (hi - lo), lo, hi)
        else:
            w = 0.12 * (1 - (it - iters // 2) / max(iters - iters // 2, 1)) + 0.03
            c = np.clip(best[3] + rng.normal(0, w, len(names)) * (hi - lo) * (rng.random(len(names)) < 0.5), lo, hi)
        r = score(c)
        if r[0] > best[0]:
            best = (*r, c)
            if log:
                log(f"{it}: score {r[0]:.3f} iou {r[1]:.3f} {json.dumps(r[2])}")
        hist.append((round(r[0], 3), round(r[1], 3)))
    return {"habit": best[2], "score": round(best[0], 3), "iou": round(best[1], 3), "log": hist}


# ---------------------------------------------------------------- form across ages and settings
def crown_measures(tree: dict) -> dict:
    """The tree's form read off its own live foliage (not a silhouette): height (m), crown width / height (mean of four
    azimuths, 1st-99th percentile of leafy wood), live crown depth / height (above the 3rd percentile of leafy wood),
    the height of the widest level / height, girth at 1.3 m (cm), how far the top stands off the foot (m), and the
    living first-order limbs. What a forester's crown ratio and crown width are, so targets can come from tables."""
    P, o = tree["pos"], tree["order"]
    live = tree["leafy"] & ~tree["dead"]
    H = float(tree["height"])
    L = P[live] if live.sum() > 3 else P
    base = float(np.percentile(L[:, 2], 3))
    w = []
    for az in (0, 45, 90, 135):
        x = L[:, 0] * math.cos(math.radians(az)) + L[:, 1] * math.sin(math.radians(az))
        w.append(np.percentile(x, 99) - np.percentile(x, 1))
    W = float(np.mean(w))
    zs = np.linspace(base, H, 11)
    reach = []
    for a, b in zip(zs[:-1], zs[1:]):
        m = (L[:, 2] >= a) & (L[:, 2] < b)
        reach.append(float(np.percentile(np.linalg.norm(L[m, :2], axis=1), 95)) if m.sum() > 5 else 0.0)
    k = int(np.argmax(reach))
    tr = (o == 0) & ~tree["dead"]
    dbh = 200 * float(np.interp(1.3, P[tr][:, 2], tree["radius"][tr])) if tr.sum() > 2 and H > 1.3 else 0.0
    limbs_ = int(((o == 1) & (o[tree["parent"]] == 0) & ~tree["dead"]).sum())
    return {"height": round(H, 2), "width_over_height": round(W / max(H, 1e-6), 3), "crown_ratio": round(1 - base / max(H, 1e-6), 3),
            "widest_at": round(0.5 * (zs[k] + zs[k + 1]) / max(H, 1e-6), 3), "dbh_cm": round(dbh, 1),
            "top_off": round(float(np.linalg.norm(P[int(np.argmax(P[:, 2])), :2])), 2), "limbs": limbs_,
            "nodes": int(len(P))}


def form_cases(spec: dict, cases: list, seeds=(1,)) -> list:
    """Grow the spec once per case ({"age", "environment"?, "name"?, + target bands}) and seed; returns each case with
    its mean `measures`. The same habit at several ages and settings: a preset tuned at one age is a single point."""
    out = []
    for c in cases:
        ms = []
        for sd in seeds:
            sp = _merge(spec, {"seed": sd, "age": c["age"], "environment": c.get("environment") or {"setting": "open"}})
            sp.pop("height", None)
            ms.append(crown_measures(grow(sp)))
        out.append({**c, "measures": {k: round(float(np.mean([m[k] for m in ms])), 3) for k in ms[0]},
                    "spread": {k: round(float(np.ptp([m[k] for m in ms])), 3) for k in ("width_over_height", "crown_ratio")}})
    return out


def form_miss(cases: list) -> float:
    """How far measured cases lie outside their target bands ({key: [lo, hi]}), each miss as a share of the band's
    middle; 0 = every measure inside its band."""
    tot = 0.0
    for c in cases:
        for k in vegetation.FORM_KEYS:
            if k in c:
                lo, hi = c[k]
                v = c["measures"][k]
                tot += float(c.get("weight", 1.0)) * (max(0.0, lo - v) + max(0.0, v - hi)) / max(0.5 * (abs(lo) + abs(hi)), 1e-6)
    return tot


def fit_form(spec: dict, cases: list, params: dict, iters: int = 60, seeds=(1, 2), rng_seed: int = 0, log=None) -> dict:
    """Search habit numbers so ONE habit meets crown targets at several ages and settings (`cases`: {"age",
    "environment", and bands like "width_over_height": [0.4, 0.55], "crown_ratio", "widest_at", "height", "dbh_cm",
    "nodes"}). `params` as fit_habit's. The outline fit (fit_habit) matches one photo; this keeps a species right
    from a sapling to a veteran, in the open and in a stand, against numbers that can be sourced (yield tables,
    crown-ratio studies, measured photos). Returns {"habit", "miss", "cases"}."""
    rng = np.random.default_rng(rng_seed)
    names = list(params)
    lo = np.array([params[k][0] for k in names], float)
    hi = np.array([params[k][1] for k in names], float)
    isint = [all(isinstance(v, int) for v in params[k]) for k in names]
    base = resolve(spec)["habit"]

    def vec0():
        out = []
        for k in names:
            a, _, i = k.partition(".")
            v = base[a]
            v = (v[min(int(i), len(v) - 1)] if isinstance(v, list) else v) if i else v
            out.append(float(v if v is not None else 0.5 * (params[k][0] + params[k][1])))
        return np.clip(np.array(out), lo, hi)

    def score(x):
        full = copy.deepcopy(base)
        for k, v, ii in zip(names, x, isint):
            a, _, i = k.partition(".")
            if i and isinstance(full[a], list) and len(full[a]) <= int(i):
                full[a] = full[a] + [full[a][-1]] * (int(i) + 1 - len(full[a]))
            _set_path(full, k, int(round(v)) if ii else round(float(v), 4))
        hb = {k: full[k] for k in {n.partition(".")[0] for n in names}}
        cs = form_cases(_merge(spec, {"habit": hb}), cases, seeds)
        return form_miss(cs), hb, cs

    x = vec0()
    best = (*score(x), x)
    if log:
        log(f"start: miss {best[0]:.3f}")
    for it in range(iters):
        if it < iters // 2:
            c = lo + rng.random(len(names)) * (hi - lo) if it % 4 == 0 else np.clip(best[3] + rng.normal(0, 0.2, len(names)) * (hi - lo) * (rng.random(len(names)) < 0.6), lo, hi)
        else:
            w = 0.1 * (1 - (it - iters // 2) / max(iters - iters // 2, 1)) + 0.03
            c = np.clip(best[3] + rng.normal(0, w, len(names)) * (hi - lo) * (rng.random(len(names)) < 0.4), lo, hi)
        r = score(c)
        if r[0] < best[0]:
            best = (*r, c)
            if log:
                log(f"{it}: miss {r[0]:.3f} {json.dumps(r[1])}")
        if best[0] <= 0:
            break
    return {"habit": best[1], "miss": round(best[0], 3), "cases": best[2]}
