"""Layered garments: one garment worn over another (garment key `over: "<garment>"`; a jacket over a shirt, a coat
over a jacket, an apron over a dress).

How it is built (cloth.build): the under garment is finished first and frozen: its result joins the body as a
collider. The outer garment's pieces are placed on the body padded out to cover it (`cloth.padded_body`, + `layer_gap`
of air) and the sim collides with the real body and the under garment's own mesh (`cloth._collider`: it rides the
body's poses). Here: what is read off the two results afterwards.

- `tells(outer, under)`: the tailoring tells as numbers against garment_kb.json's targets (how much shirt collar
  shows above the jacket's at centre back, how much cuff past the sleeve, lapels lying on the chest, the outer collar
  hugging the under one, crossings between the layers).
- `hidden(under, outer)`: the under garment's faces nobody can see (covered by the outer one, further than `margin`
  from its openings): the export drops them (a shirt under a jacket becomes collar + front V + cuffs).
- `between_crossings(A, B)`: edges of one mesh through triangles of the other.
"""
from __future__ import annotations

import numpy as np
from scipy.spatial import cKDTree

TARGETS = {"collar_show_mm": (10.0, 20.0), "cuff_show_mm": (10.0, 15.0), "lapel_gap_mm": (0.0, 6.0),
           "collar_hug_mm": (0.0, 6.0), "crossings": (0, 0)}


def _samples(V: np.ndarray, F: np.ndarray) -> np.ndarray:
    w = np.array([[1, 0, 0], [0, 1, 0], [0, 0, 1], [1 / 3, 1 / 3, 1 / 3], [.5, .5, 0], [0, .5, .5], [.5, 0, .5]])
    return np.einsum("kw,fwd->fkd", w, V[F]).reshape(-1, 3)


def between_crossings(VA: np.ndarray, FA: np.ndarray, VB: np.ndarray, FB: np.ndarray) -> int:
    """Edges of mesh A through triangles of mesh B, plus B's through A's."""
    from .cloth import _seg_tri
    n = 0
    for (V1, F1), (V2, F2) in (((VA, FA), (VB, FB)), ((VB, FB), (VA, FA))):
        E = np.unique(np.sort(np.r_[F1[:, [0, 1]], F1[:, [1, 2]], F1[:, [2, 0]]], 1), axis=0)
        cen = V2[F2].mean(1)
        rad = np.max(np.linalg.norm(V2[F2] - cen[:, None], axis=2), axis=1)
        mid = 0.5 * (V1[E[:, 0]] + V1[E[:, 1]])
        half = 0.5 * np.linalg.norm(V1[E[:, 0]] - V1[E[:, 1]], axis=1)
        cand = cKDTree(cen).query_ball_point(mid, r=half + float(np.percentile(rad, 99)), return_sorted=False)
        ei = np.repeat(np.arange(len(E)), [len(c) for c in cand])
        ti = np.fromiter((t for c in cand for t in c), dtype=np.int64, count=len(ei))
        if not len(ei):
            continue
        T = F2[ti]
        n += int(_seg_tri(V1[E[ei, 0]], V1[E[ei, 1]], V2[T[:, 0]], V2[T[:, 1]], V2[T[:, 2]]).sum())
    return n


def _pieces_of(res: dict, roles: tuple, wrap: str | None = None) -> np.ndarray:
    """Vertices of the result's pieces whose name starts with one of `roles` (or that are wrapped on `wrap`)."""
    M, pcs = res["mesh"], res["pieces"]["pieces"]
    ks = [k for k, nm in enumerate(M["names"]) if (nm.split(".")[0] in roles) or
          (wrap is not None and pcs[nm]["wrap"].get("to") == wrap)]
    return np.where(np.isin(M["piece"], ks))[0]


def tells(outer: dict, under: dict) -> dict:
    """The tailoring tells of an outer garment over an under one, each {"value", "target", "ok"} (None where the
    garments don't have the pieces):
    collar_show_mm  the under collar's top above the outer collar's at centre back (a shirt collar shows 10-20 mm);
    cuff_show_mm    the under cuff past the outer sleeve's hem, along the forearm, per arm (10-15 mm);
    lapel_gap_mm    the lapels' flaps off the fronts they lie on (median; folds named lapel*);
    collar_hug_mm   the outer collar and stand off the under collar's surface (median);
    crossings       edges of either garment through the other's triangles."""
    Vo, Vu = outer["V"], under["V"]
    Mo, Mu = outer["mesh"], under["mesh"]
    body = outer["body"]
    out = {}

    def put(k, v, digits=1):
        lo, hi = TARGETS[k]
        if v is None:
            out[k] = None
            return
        vals = v if isinstance(v, (list, tuple)) else [v]
        out[k] = {"value": [round(float(x), digits) for x in vals] if isinstance(v, (list, tuple)) else round(float(v), digits),
                  "target": [lo, hi], "ok": bool(all(lo - 1e-9 <= x <= hi + 1e-9 for x in vals))}
    co, cu = _pieces_of(outer, ("collar", "stand")), _pieces_of(under, ("collar", "stand"))
    if len(co) and len(cu):
        # at centre back: within 2.5 cm of the middle, behind the neck's axis
        yc = float(body.J["neck"][1]) if "neck" in body.J else 0.0
        bo = co[(np.abs(Vo[co, 0]) < 0.025) & (Vo[co, 1] > yc)]
        bu = cu[(np.abs(Vu[cu, 0]) < 0.025) & (Vu[cu, 1] > yc)]
        put("collar_show_mm", (Vu[bu, 2].max() - Vo[bo, 2].max()) * 1000 if len(bo) and len(bu) else None)
        d, _ = cKDTree(_samples(Vu, Mu["F"][np.isin(Mu["piece"][Mu["F"][:, 0]], np.unique(Mu["piece"][cu]))])).query(Vo[co])
        put("collar_hug_mm", float(np.median(d)) * 1000)
    else:
        out["collar_show_mm"] = out["collar_hug_mm"] = None
    shows = []
    for side in ("L", "R"):
        if f"elbow.{side}" not in body.J:
            continue
        el, wr = body.J[f"elbow.{side}"], body.J[f"wrist.{side}"]
        ax = (wr - el) / np.linalg.norm(wr - el)
        so = _pieces_of(outer, (), wrap=f"arm.{side}")
        su = _pieces_of(under, (), wrap=f"arm.{side}")
        if len(so) and len(su):
            shows.append(float((np.percentile((Vu[su] - el) @ ax, 99) - np.percentile((Vo[so] - el) @ ax, 99)) * 1000))
    put("cuff_show_mm", shows if shows else None)
    from . import folds as foldmod
    faces = outer["pieces"].get("faces") or {}
    gaps = [foldmod.measure(Vo, Mo, fd, faces.get(fd["piece"], 1.0)).get("gap_mm", [None])[0]
            for fd in Mo.get("folds") or [] if fd["name"].startswith("lapel")]
    gaps = [g for g in gaps if g is not None]
    put("lapel_gap_mm", gaps if gaps else None)
    lo, hi = TARGETS["crossings"]
    n = between_crossings(Vo, Mo["F"], Vu, Mu["F"])
    out["crossings"] = {"value": n, "target": [lo, hi], "ok": n == 0}
    return out


def tells_text(t: dict) -> str:
    L = []
    for k, v in t.items():
        if v is None:
            L.append(f"  {k}: not measured (the garments don't have the pieces)")
        else:
            L.append(f"  {'ok ' if v['ok'] else '!! '}{k}: {v['value']} (target {v['target'][0]}-{v['target'][1]})")
    return "\n".join(L)


def hidden(under: dict, outer: dict, margin: float = 0.03, reach: float = 0.06) -> np.ndarray:
    """Per triangle of the under garment: True where it can't be seen for the outer one. A vertex is covered when
    the outer garment lies over it (an outer surface point within `reach`, further from the body than the vertex) and
    it is more than `margin` inside the outer garment's openings (its free edges: neckline, front edges, hems, sleeve
    ends: what shows there stays, with a margin for movement). A triangle is hidden when all three corners are."""
    Vu, Fu = under["V"], under["mesh"]["F"]
    Vo, Mo = outer["V"], outer["mesh"]
    body = outer["body"]
    P = _samples(Vo, Mo["F"])
    d, i = cKDTree(P).query(Vu)
    cu, co = body.clearance(Vu), body.clearance(P[i])
    # over it: the nearest outer point lies outward of the vertex, not beside it (past an opening's edge the nearest
    # outer cloth is off to the side)
    vn, tree = body.normals()
    n = vn[tree.query(Vu)[1]]
    off = P[i] - Vu
    along = (off * n).sum(1)
    side = np.linalg.norm(off - along[:, None] * n, axis=1)
    over = (d < reach) & (co > cu - 0.002) & (side < 0.012)
    # the outer garment's openings: outline vertices no seam closes
    sewn = np.zeros(len(Vo), bool)
    if len(Mo["sew"]):
        sewn[Mo["sew"].ravel()] = True
    free = np.where(Mo["border"] & ~sewn)[0]
    if len(free):
        dopen, _ = cKDTree(Vo[free]).query(Vu)
        over &= dopen > margin
    return over[Fu].all(1)
