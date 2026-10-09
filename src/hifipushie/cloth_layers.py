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
- `tucked(under, outer)`: the under garment's finished surface with only its covered cloth laid under the outer
  one's inner face: what every look, the scene and the export draw (cloth.worn_together).
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
    collar_hug_mm   the outer collar and stand off the under collar's surface, behind the neck's axis (median);
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
        # (the outer collar where it goes ROUND the neck: behind the neck's axis. A notched collar's ends lie on the
        # chest with the lapels, 5-10 cm from an under collar: with them in the median Garrett's jacket read 27 mm
        # whatever its back did)
        hb = co[Vo[co, 1] > yc]
        d, _ = cKDTree(_samples(Vu, Mu["F"][np.isin(Mu["piece"][Mu["F"][:, 0]], np.unique(Mu["piece"][cu]))])).query(Vo[hb if len(hb) else co])
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


TUCK_GAP = 0.004  # m under the outer garment's inner face a covered vertex of the under garment is laid
TUCK_SIDE = 0.010  # m: outer cloth whose nearest point lies further than this to the SIDE of a vertex doesn't cover it
TUCK_REACH = 0.08  # m: outer cloth further than this from a vertex doesn't cover it
TUCK_FEATHER = 3  # rings of uncovered cloth that follow the covered cloth beside them (halving a ring)


def tucked(under: dict, outer: dict, gap: float = TUCK_GAP, rigid: np.ndarray | None = None) -> tuple:
    """The under garment's FINISHED surface as it is worn with the outer one over it: (V, covered per vertex).
    What shows of it (collar, the front in the jacket's V, cuffs) stays exactly as finished (relief, bands, made
    pieces: the surface the buttons and maps were made for); only vertices the outer garment lies over, and that
    stand closer than `gap` under its inner face or outside it (a shirt simulated alone blouses through a jacket's
    sleeves), are laid `gap` under that face, straight along the outer cloth's normal at the nearest point: under
    the outer garment the under one takes ITS shape, so nothing crumples. Covered = the nearest point of the outer
    garment lies along the way out of the body from the vertex (or back in, where it pokes through), within
    TUCK_SIDE to the side: beside an opening the nearest outer cloth is off to the side and that cloth shows.
    (Tried: "projects inside a triangle": outside a convex sleeve the nearest point is always on an edge, shards
    stayed at sleeves and armholes; "not on an open edge": the chest in the V was pulled under the lapels, crumpled.)
    Drawn pressed everywhere instead (the collider the outer garment was simulated over: cloth.pressed), the shirt
    front in a jacket's V was a crumpled surface with no band and no buttons (the user: "where the placket?").
    `rigid` (per vertex group id, -1 none: made pieces, closure bands): a group moves by ONE vector (the mean of its
    members' moves), so a collar or a placket keeps its shape."""
    from .closures import _closest_on
    Vu, Mu = np.asarray(under["V"], float), under["mesh"]
    Vo, Fo = np.asarray(outer["V"], float), np.asarray(outer["mesh"]["F"])
    body = outer["body"]
    V = Vu.copy()
    covered = np.zeros(len(V), bool)
    Fu = np.asarray(Mu["F"])
    E = np.unique(np.sort(np.r_[Fu[:, [0, 1]], Fu[:, [1, 2]], Fu[:, [2, 0]]], 1), axis=0)
    tree = cKDTree(body.V) if len(getattr(body, "V", [])) else None
    bn = None
    if tree is not None:
        vn_, _t = body.normals()
        bn = vn_[tree.query(Vu)[1]]  # out of the body at each vertex
    for _ in range(3):
        Q, N, ins = _closest_on(V, Vo, Fo, k=16)
        if tree is not None:  # out = away from the body (a turned lapel's own normal faces in)
            out = Q - body.V[tree.query(Q)[1]]
            N = np.where(((N * out).sum(1) < 0)[:, None], -N, N)
        d = V - Q
        s = (d * N).sum(1)  # > 0: outside the outer garment
        near = np.linalg.norm(d, axis=1) < TUCK_REACH
        # over it: the nearest outer cloth lies along the way out of the body from the vertex (or back in, where the
        # vertex pokes through), not off to its side (beside an opening the nearest outer cloth is the lapel's edge)
        if bn is not None:
            side = np.linalg.norm(d - (d * bn).sum(1)[:, None] * bn, axis=1)
            # (or it stands OUTSIDE the outer cloth's face, within 3 cm: in an armpit the body's normals point every
            # way and bunched shirt came through the jacket's armhole as shards)
            cov = near & ((side < TUCK_SIDE) | (ins & (s > 0) & (np.linalg.norm(d, axis=1) < 0.03)))
        else:
            cov = near & ins
        need = np.where(cov, np.maximum(s + gap, 0.0), 0.0)
        covered |= cov
        if need.max() < 2e-4:
            break
        D = -N * need[:, None]
        # the cloth beside covered cloth follows a little (no step at the outer garment's edge)
        fixed = need > 0
        for _r in range(TUCK_FEATHER):
            acc, wt = np.zeros_like(D), np.zeros(len(V))
            np.add.at(acc, E[:, 0], D[E[:, 1]])
            np.add.at(wt, E[:, 0], 1.0)
            np.add.at(acc, E[:, 1], D[E[:, 0]])
            np.add.at(wt, E[:, 1], 1.0)
            D = np.where(fixed[:, None], D, 0.5 * acc / np.maximum(wt, 1)[:, None])
        if rigid is not None:
            for gid in np.unique(rigid[rigid >= 0]):
                m = rigid == gid
                if fixed[m].any():
                    D[m] = D[m][fixed[m]].mean(0) if fixed[m].mean() > 0.5 else 0.0
        V = V + D
    return V, covered


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
