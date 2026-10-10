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


def view_dirs(n_ring: int = 12, elevations=(-50.0, -25.0, 0.0, 25.0, 50.0)) -> np.ndarray:
    """Unit view directions (from the eye toward the model) round the figure: rings at the given elevations (deg;
    negative = from below, looking up) + straight down; what a game camera can see of a character."""
    out = []
    for el in elevations:
        e = np.radians(el)
        for k in range(n_ring):
            a = 2 * np.pi * k / n_ring
            out.append([np.cos(e) * np.sin(a), np.cos(e) * np.cos(a), -np.sin(e)])
    out.append([0.0, 0.0, -1.0])
    return np.array(out)


def occluded(P: np.ndarray, Vo: np.ndarray, Fo: np.ndarray, dirs: np.ndarray, px: float = 0.002,
             tol: float = 0.0015, gaps: bool = False, front_only: bool = False) -> np.ndarray:
    """Per point of P, per view direction: True where the mesh (Vo, Fo) lies in FRONT of the point along that
    direction (orthographic: a z-buffer of the mesh at `px` m per pixel; the point is behind it by more than `tol`).
    -> bool [len(dirs), len(P)]. Points outside the mesh's footprint in a view are not occluded there.
    gaps: instead the depth of the mesh behind minus the point's ([len(dirs), len(P)], inf off the footprint;
    > 0 = the mesh lies BEHIND the point by that much). front_only: only faces turned toward the eye (Fo wound outward)
    are drawn: the outer side of a garment, not its inside seen through an opening."""
    P, Vo, Fo = np.asarray(P, float), np.asarray(Vo, float), np.asarray(Fo)
    out = np.zeros((len(dirs), len(P)), float if gaps else bool)
    for k, d in enumerate(np.asarray(dirs, float)):
        d = d / np.linalg.norm(d)
        a = np.cross(d, [0.0, 0.0, 1.0]) if abs(d[2]) < 0.95 else np.cross(d, [1.0, 0.0, 0.0])
        a /= np.linalg.norm(a)
        b = np.cross(d, a)
        uv_o = np.c_[Vo @ a, Vo @ b] / px
        dep_o = Vo @ d  # (larger = further from the eye)
        lo = np.floor(uv_o.min(0)).astype(int) - 1
        W, H = (np.ceil(uv_o.max(0)).astype(int) - lo + 2)
        Z = np.full((W, H), np.inf)
        T = uv_o[Fo] - lo  # [nf, 3, 2]
        Dz = dep_o[Fo]
        if front_only:
            fn_ = np.cross(Vo[Fo[:, 1]] - Vo[Fo[:, 0]], Vo[Fo[:, 2]] - Vo[Fo[:, 0]])
            facing = fn_ @ d < 0
        else:
            facing = np.ones(len(Fo), bool)
        bx0 = np.floor(T[..., 0].min(1)).astype(int)
        bx1 = np.ceil(T[..., 0].max(1)).astype(int)
        by0 = np.floor(T[..., 1].min(1)).astype(int)
        by1 = np.ceil(T[..., 1].max(1)).astype(int)
        for f in np.where(facing)[0]:
            xs, ys = np.arange(bx0[f], bx1[f] + 1), np.arange(by0[f], by1[f] + 1)
            if not len(xs) or not len(ys):
                continue
            gx, gy = np.meshgrid(xs + 0.5, ys + 0.5, indexing="ij")
            (x0, y0), (x1, y1), (x2, y2) = T[f]
            den = (y1 - y2) * (x0 - x2) + (x2 - x1) * (y0 - y2)
            if abs(den) < 1e-12:
                continue
            l0 = ((y1 - y2) * (gx - x2) + (x2 - x1) * (gy - y2)) / den
            l1 = ((y2 - y0) * (gx - x2) + (x0 - x2) * (gy - y2)) / den
            l2 = 1 - l0 - l1
            inside = (l0 >= -0.02) & (l1 >= -0.02) & (l2 >= -0.02)
            if not inside.any():
                continue
            z = l0 * Dz[f, 0] + l1 * Dz[f, 1] + l2 * Dz[f, 2]
            sub = Z[bx0[f]:bx1[f] + 1, by0[f]:by1[f] + 1]
            np.minimum(sub, np.where(inside, z, np.inf), out=sub)
        q = (np.c_[P @ a, P @ b] / px - lo).astype(int)
        ok = (q[:, 0] >= 0) & (q[:, 0] < W) & (q[:, 1] >= 0) & (q[:, 1] < H)
        zq = np.full(len(P), np.inf)
        zq[ok] = Z[q[ok, 0], q[ok, 1]]
        out[k] = (zq - (P @ d)) if gaps else (zq < (P @ d) - tol)
    return out


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
TUCK_FEATHER = 5  # rings of uncovered cloth that follow the covered cloth beside them
TUCK_FALL = 0.6  # the share of its neighbours' mean move an uncovered vertex beside covered cloth takes, ring by ring
TUCK_EVEN = 0.7  # a covered vertex moves no less than this share of its neighbours' mean move


def tucked(under: dict, outer: dict, gap: float = TUCK_GAP, rigid: np.ndarray | None = None,
           keep_shown: bool = True) -> tuple:
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
    Vo, Mo = np.asarray(outer["V"], float), outer["mesh"]
    Fo = np.asarray(Mo["F"])
    body = outer["body"]
    oriented = False
    if Mo.get("sew") is not None and len(np.asarray(Mo["sew"])) and "piece" in Mo and "names" in Mo:
        # the outer garment WELDED (its seams one surface: unwelded, beside a seam the nearest point lay on a piece's
        # edge and cloth standing out through the seam was not "over" it) and each piece wound to face out
        # (cloth10: shirt through the jacket at the armholes and side seams, 17-29 mm out)
        from . import cloth as _cloth
        try:
            Fo = np.asarray(_cloth.welded_faces(Mo, Vo, body=body))
            oriented = True
        except Exception:  # (a mesh the welder can't take: as before)
            Fo = np.asarray(Mo["F"])
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
            dot = (N * out).sum(1) / np.maximum(np.linalg.norm(out, axis=1), 1e-9)
            # wound pieces: their own normal, unless the body says clearly otherwise (a turned lapel); in an armpit the
            # nearest body vertex lies every way and flipped the jacket's side panel inside out
            N = np.where(((dot < -0.5) if oriented else (dot < 0))[:, None], -N, N)
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
        # (covered is decided per vertex by a nearest point: at an opening's edge single vertices flip, and each
        # pushed 4 mm by itself was a dent catching the light: the pale flecks on the shirt beside a lapel. A vertex
        # goes with the majority of its neighbours)
        deg = np.bincount(E.ravel(), minlength=len(V)).astype(float)
        for _m in range(2):
            nbc = np.bincount(E[:, 0], weights=cov[E[:, 1]].astype(float), minlength=len(V)) + \
                np.bincount(E[:, 1], weights=cov[E[:, 0]].astype(float), minlength=len(V))
            share = nbc / np.maximum(deg, 1)
            cov = np.where(cov, share >= 0.34, share > 0.67)
        need = np.where(cov, np.maximum(s + gap, 0.0), 0.0)
        covered |= cov
        if need.max() < 2e-4:
            break
        D = -N * need[:, None]
        # the cloth beside covered cloth follows a little (no step at the outer garment's edge): the move falls off
        # smoothly over TUCK_FEATHER rings, and a covered vertex moves no less than its neighbours' mean x TUCK_EVEN
        # (one vertex needing 0 among ones needing 4 mm was a bump)
        fixed = need > 0
        for _r in range(TUCK_FEATHER):
            acc, wt = np.zeros_like(D), np.zeros(len(V))
            np.add.at(acc, E[:, 0], D[E[:, 1]])
            np.add.at(wt, E[:, 0], 1.0)
            np.add.at(acc, E[:, 1], D[E[:, 0]])
            np.add.at(wt, E[:, 1], 1.0)
            avg = acc / np.maximum(wt, 1)[:, None]
            low = fixed & (np.linalg.norm(D, axis=1) < TUCK_EVEN * np.linalg.norm(avg, axis=1))
            D = np.where(fixed[:, None] & ~low[:, None], D, np.where(low[:, None], TUCK_EVEN * avg, TUCK_FALL * avg))
        if rigid is not None:
            for gid in np.unique(rigid[rigid >= 0]):
                m = rigid == gid
                if fixed[m].any():
                    D[m] = D[m][fixed[m]].mean(0) if fixed[m].mean() > 0.5 else 0.0
        V = V + D
    if keep_shown:
        # what SHOWS stays bit-identical to the finished under garment: only covered vertices take the move (the
        # feather onto uncovered cloth beside the outer garment's edge nudged the visible shirt up to 9 mm; a garment
        # shipped merged-and-cut never shows the step it smoothed, cloth10). keep_shown=False: the feathered move
        keep_m = covered.copy()
        if rigid is not None:  # (a rigid group that moved moves whole: its shape is kept)
            for gid in np.unique(rigid[rigid >= 0]):
                m_ = rigid == gid
                if np.abs(V[m_] - Vu[m_]).max() > 0:
                    keep_m[m_] = True
        V = np.where(keep_m[:, None], V, Vu)
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
