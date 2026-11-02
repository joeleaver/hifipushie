"""Step 10, EXPORT: a skinned garment that BENDS cleanly (T11b, C293): its weights and the check that it bends.

Weights (`skin`): every garment vertex reads the body's weights at its PROJECTED body surface point (the closest point
of the base body's surface, barycentric in that triangle: rig_template.from_surface with no facing rule: a garment
vertex's own normal says nothing about which skin it lies on), then those weights are SMOOTHED OVER THE GARMENT'S OWN
SURFACE by a geodesic kernel of radius `geo_radius` (a rigger's smooth after a weight transfer). Why: cloth stands
off the skin at the shoulder and armpit; two neighbouring garment vertices there project onto different body regions
(the deltoid -> the arm, the chest's side -> the spine) and part when the arm moves: a step / a pinched notch
(Joe, T11's shirt at 45 deg). rig.skin_parts did the same projection but with WORN_SMOOTH = 0 (no smoothing over the
cloth). The radius (GEO_R_*): at least two grid cells (one edge can't carry a weight jump: the step spreads over two
rows of quads) and at least twice the garment's p95 stand-off from the skin (cloth that far off has no single skin
under it: neighbours within that distance may read skins that far apart), within [2, 6] cm (6 cm: past it a sleeve's
cuff reads the elbow). Details keep taking their garment vertex's weights (garment_export_tool).

The check (`deformation`): the GARMENT's own shape between rest and each pose of `poses(rb)` (arm raised 45 deg, arm
forward 60 deg, elbow bent 90 deg, both arms down by the sides; axes from the rig's own bones, not per garment),
per edge of the welded outer mesh:
  * strain = posed length / rest length - 1, minus the body's own strain under it (the skin stretches at a raised
    shoulder; a skinned garment can't be better than the skin's field). Limit: the cloth's thread cap
    (pattern_form.FIT_THREAD_CAP): p99 of the excess within it (the top 1 %: linear-blend skinning's corner noise).
  * crease = the change of the dihedral angle at an edge, minus the body's own change under it. Limit: CREASE_FLOOR or
    the sharpest fold the soft cloth already has at rest (p99 of the rest dihedrals), whichever is larger: a pose may
    not make a crease sharper than any fold the garment had. The body's own crease is reported as the body's.
Rows per pose: strain p99 / max, crease max (excess over the body) with the region (the dominant rig bone there), and
the body's own crease max. A kink is a crease past the limit; a tear / a step is strain past the cap.
"""
from __future__ import annotations

import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import dijkstra
from scipy.spatial import cKDTree

GEO_R_MIN, GEO_R_MAX = 0.02, 0.06  # m: the smoothing radius' range (see the docstring)
GEO_CELLS = 2.0  # x the grid edge: the radius is at least this many cells
GEO_STANDOFF = 2.0  # x the p95 stand-off from the skin
CREASE_FLOOR = 25.0  # deg: never a crease limit below this (a 25 deg fold between two quads reads as a soft bend)
STRAIN_Q = 99.0  # the strain row's percentile
SKIN_REACH = 0.01  # m: the skin under a garment vertex: body vertices within its stand-off + this
THROUGH = 0.003  # m: a garment vertex this far inside the posed body (outside at rest): skin through (reported)
POSE_ARM = "LeftArm"
POSE_FOREARM = "LeftForeArm"


# ---------------------------------------------------------------- the body's field

_FIELD: dict = {}


def body_field(spec: dict, rb: list[dict]):
    """(Wq, Tq, dense weights, spread) of the base body's surface: the template's hand-made weights (MakeHuman) or
    ours by distance (rig.skin_parts' reference); spread: the template knows no twist bones (rig._spread_twist)."""
    import json
    from . import base as basemod, rig, rig_template
    from .spec import expand_mirror
    key = json.dumps([spec.get("base"), [b["name"] for b in rb]], sort_keys=True, default=str)
    if key in _FIELD:
        return _FIELD[key]
    surf = basemod.surface(basemod.inject(expand_mirror(spec)), spec["base"])
    Wq, fq = surf["quads"]
    Wq = np.asarray(Wq, float)
    Tq = np.array([(f[0], f[j], f[j + 1]) for f in fq for j in range(1, len(f) - 1)])
    ref = rig_template.template_weights(spec, rb, surf)
    spread = ref is not None
    if ref is None:
        Jr, Wr = rig.rig_weights(spec, rb, Wq, Tq, smooth=rig.SMOOTH)
        ref = np.zeros((len(Wq), len(rb)))
        np.add.at(ref, (np.repeat(np.arange(len(Wq)), Jr.shape[1]), Jr.ravel()), Wr.ravel())
    _FIELD.clear()
    _FIELD[key] = (Wq, Tq, ref, spread)
    return _FIELD[key]


def weld(V: np.ndarray, tol: float = 1e-5):
    """(index of each vertex's welded copy, welded count): seam-split vertices are one vertex (or they'd crack)."""
    _, inv = np.unique(np.round(np.asarray(V, float) / tol).astype(np.int64), axis=0, return_inverse=True)
    inv = inv.ravel()
    return inv, int(inv.max()) + 1 if len(inv) else 0


def edges_of(T: np.ndarray) -> np.ndarray:
    T = np.asarray(T, np.int64)
    E = np.sort(np.concatenate([T[:, [0, 1]], T[:, [1, 2]], T[:, [2, 0]]]), 1)
    return np.unique(E, axis=0)


def geo_radius(h: float, standoff_p95: float) -> float:
    return float(np.clip(max(GEO_CELLS * h, GEO_STANDOFF * standoff_p95), GEO_R_MIN, GEO_R_MAX))


def geodesic_smooth(V: np.ndarray, T: np.ndarray, D: np.ndarray, radius: float) -> np.ndarray:
    """D (per vertex rows) averaged over the mesh's own surface: weight (1 - (g / radius)^2)^2 at geodesic (edge
    path) distance g < radius. Welded first (seams don't part)."""
    inv, n = weld(V)
    Vw = np.zeros((n, 3))
    Vw[inv] = V
    cnt = np.bincount(inv, minlength=n).astype(float)[:, None]
    Dw = np.zeros((n, D.shape[1]))
    np.add.at(Dw, inv, D)
    Dw /= np.maximum(cnt, 1)
    E = edges_of(inv[np.asarray(T, np.int64)])
    E = E[E[:, 0] != E[:, 1]]
    L = np.linalg.norm(Vw[E[:, 0]] - Vw[E[:, 1]], axis=1)
    G = coo_matrix((np.r_[L, L], (np.r_[E[:, 0], E[:, 1]], np.r_[E[:, 1], E[:, 0]])), shape=(n, n)).tocsr()
    out = np.zeros_like(Dw)
    step = max(1, 4_000_000 // max(n, 1))
    for s in range(0, n, step):
        idx = np.arange(s, min(n, s + step))
        g = dijkstra(G, indices=idx, limit=radius)
        w = np.where(np.isfinite(g), (1 - np.clip(g / radius, 0, 1) ** 2) ** 2, 0.0)
        out[idx] = (w @ Dw) / np.maximum(w.sum(1, keepdims=True), 1e-12)
    return out[inv]


def dense(J, W, nb: int) -> np.ndarray:
    D = np.zeros((len(J), nb))
    np.add.at(D, (np.repeat(np.arange(len(J)), J.shape[1]), np.asarray(J).ravel()), np.asarray(W).ravel())
    return D


def skin(spec: dict, rb: list[dict], V: np.ndarray, T: np.ndarray, h: float, smooth: bool = True):
    """(J, W, info) for a garment mesh: projected body weights, smoothed over the garment by the geodesic radius.
    smooth=False: the projection alone (the body's own mesh)."""
    from . import rig, rig_template
    Wq, Tq, ref, spread = body_field(spec, rb)
    D, info = transfer(Wq, Tq, ref, V, T, h, smooth)
    J, W = rig_template.top_k(D)
    if spread:
        J, W = rig._spread_twist(rb, V, J, W)
    return np.asarray(J), np.asarray(W, float), info


def transfer(Wq, Tq, ref, V, T, h: float, smooth: bool = True):
    """(dense weights, info): the body's (Wq, Tq, ref) at each vertex's projected point, smoothed over (V, T)."""
    from . import rig_template
    V = np.asarray(V, float)
    D = rig_template.from_surface(Wq, Tq, ref, V, None)
    off = cKDTree(Wq).query(V)[0]
    sp = float(np.percentile(off, 95)) if len(off) else 0.0
    info = {"standoff_p95_m": round(sp, 4)}
    if smooth and len(T):
        r = geo_radius(h, sp)
        D = geodesic_smooth(V, T, D, r)
        info["geo_radius_m"] = round(r, 4)
    return D, info


# ---------------------------------------------------------------- the poses

def _bone(rb, short):
    for i, b in enumerate(rb):
        if b["name"] == short or b["name"].split(":")[-1] == short:
            return i
    raise ValueError(f"no rig bone {short!r}")


def _unit(v):
    v = np.asarray(v, float)
    return v / max(np.linalg.norm(v), 1e-12)


def _dir(rb, i):
    """A bone's direction: head -> its first child's head (rig bones have heads only)."""
    kids = [j for j, b in enumerate(rb) if b["parent"] == i and "Twist" not in b["name"] and "Bend" not in b["name"]]
    tail = rb[kids[0]]["head"] if kids else rb[i].get("tail", rb[i]["head"])
    return _unit(np.asarray(tail, float) - np.asarray(rb[i]["head"], float))


def poses(rb: list[dict]) -> dict:
    """{pose: {bone name: (axis, deg)}} from the rig's own bones (world axes, Z up, the body faces -Y):
    arm_raised_45 (the upper arm toward +Z), arm_forward_60 (toward -Y), elbow_bent_90 (the forearm toward -Y),
    arms_down (both upper arms turned until they hang straight down: -Z)."""
    Z, F = np.array([0, 0, 1.0]), np.array([0, -1.0, 0])
    a, f = _bone(rb, POSE_ARM), _bone(rb, POSE_FOREARM)
    da, df = _dir(rb, a), _dir(rb, f)
    out = {"arm_raised_45": {rb[a]["name"]: (_unit(np.cross(da, Z)).tolist(), 45.0)},
           "arm_forward_60": {rb[a]["name"]: (_unit(np.cross(da, F)).tolist(), 60.0)},
           "elbow_bent_90": {rb[f]["name"]: (_unit(np.cross(df, F)).tolist(), 90.0)}}
    down = {}
    for side in ("Left", "Right"):
        i = _bone(rb, side + POSE_ARM[4:])
        d = _dir(rb, i)
        ang = float(np.degrees(np.arccos(np.clip(d @ -Z, -1, 1))))
        if ang > 1.0:
            down[rb[i]["name"]] = (_unit(np.cross(d, -Z)).tolist(), ang)
    out["arms_down"] = down
    return out


def posed(rb, V, J, W, turns):
    from . import rig
    return rig.pose(rb, V, J, W, rig.drive_twist(rb, rig.resolve_turns(rb, turns)))


# ---------------------------------------------------------------- the check

def _dihedral(V, T, E2, F2):
    """Angle (deg) between the normals of the two faces at each interior edge."""
    n = np.cross(V[T[:, 1]] - V[T[:, 0]], V[T[:, 2]] - V[T[:, 0]])
    n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-15)
    c = np.clip((n[F2[:, 0]] * n[F2[:, 1]]).sum(1), -1, 1)
    return np.degrees(np.arccos(c))


def interior(T):
    """(edges [m, 2], their two faces [m, 2]) of a welded triangle mesh's manifold interior edges."""
    T = np.asarray(T, np.int64)
    E = np.sort(np.concatenate([T[:, [0, 1]], T[:, [1, 2]], T[:, [2, 0]]]), 1)
    fid = np.tile(np.arange(len(T)), 3)
    key = E[:, 0] * (int(T.max()) + 1) + E[:, 1]
    o = np.argsort(key, kind="stable")
    k, f = key[o], fid[o]
    starts = np.flatnonzero(np.r_[True, k[1:] != k[:-1]])  # runs of one key: an edge with exactly two faces
    cnt = np.diff(np.r_[starts, len(k)])
    two = starts[cnt == 2]
    return E[o][two], np.stack([f[two], f[two + 1]], 1)


def _field(V, T, P):
    """Per vertex: max edge strain and max dihedral change over its incident edges (rest V -> posed P)."""
    E = edges_of(T)
    s = np.linalg.norm(P[E[:, 0]] - P[E[:, 1]], axis=1) / np.maximum(np.linalg.norm(V[E[:, 0]] - V[E[:, 1]], axis=1), 1e-12) - 1
    vs = np.zeros(len(V))
    np.maximum.at(vs, E[:, 0], s)
    np.maximum.at(vs, E[:, 1], s)
    E2, F2 = interior(T)
    dc = np.abs(_dihedral(P, T, E2, F2) - _dihedral(V, T, E2, F2))
    vc = np.zeros(len(V))
    np.maximum.at(vc, E2[:, 0], dc)
    np.maximum.at(vc, E2[:, 1], dc)
    return vs, vc


def _vnormals(V, T):
    from .garment_game import normals
    return normals(np.asarray(V, float), np.asarray(T, np.int64))


def crease_limit(V, T, soft: np.ndarray | None = None) -> float:
    """The sharpest fold the soft cloth has at rest (p99 of its interior dihedrals), at least CREASE_FLOOR."""
    E2, F2 = interior(T)
    d = _dihedral(V, T, E2, F2)
    if soft is not None:
        d = d[soft[F2].all(1)]
    return float(max(CREASE_FLOOR, np.percentile(d, 99) if len(d) else 0.0))


def deformation(rb, gV, gT, gJ, gW, bV, bT, bJ, bW, pose_set: dict | None = None, soft_faces=None,
                cap: float | None = None) -> dict:
    """The garment's own bend per pose vs the body's under it (module docstring). gV/gT: the OUTER garment mesh (welded
    here). Returns {"limits", "poses": {pose: row}, "ok", "posed": {pose: (garment, body)}}."""
    from . import pattern_form
    cap = pattern_form.FIT_THREAD_CAP if cap is None else cap
    pose_set = pose_set or poses(rb)
    inv, n = weld(gV)
    Vw = np.zeros((n, 3))
    Vw[inv] = gV
    first = np.zeros(n, int)
    first[inv[::-1]] = np.arange(len(inv))[::-1]
    Tw = inv[np.asarray(gT, np.int64)]
    keep = (Tw[:, 0] != Tw[:, 1]) & (Tw[:, 1] != Tw[:, 2]) & (Tw[:, 2] != Tw[:, 0])
    Tw = Tw[keep]
    soft = None if soft_faces is None else np.asarray(soft_faces, bool)[keep]
    Jw, Ww = np.asarray(gJ)[first], np.asarray(gW)[first]
    climit = crease_limit(Vw, Tw, soft)
    E = edges_of(Tw)
    E2, F2 = interior(Tw)
    th0 = _dihedral(Vw, Tw, E2, F2)
    dist, near = cKDTree(bV).query(Vw)
    # the skin a garment vertex may lie over: the body vertices within its stand-off + SKIN_REACH (cloth bridging the
    # armpit lies over the armpit's skin, not only the one body vertex nearest it)
    over = cKDTree(bV).query_ball_point(Vw, dist + SKIN_REACH)
    bN = _vnormals(bV, bT)
    side0 = ((Vw - bV[near]) * bN[near]).sum(1)
    names = [b["name"] for b in rb]
    names = [x.split(":")[-1] for x in names]
    region = np.array([names[j] for j in Jw[np.arange(n), np.argmax(Ww, 1)]])
    rows, posed_out = {}, {}
    for pn, turns in pose_set.items():
        P = posed(rb, Vw, Jw, Ww, turns)
        bP = posed(rb, bV, bJ, bW, turns)
        bs, bc = _field(bV, bT, bP)
        gs = np.array([bs[o].max() if len(o) else 0.0 for o in over])
        gc = np.array([bc[o].max() if len(o) else 0.0 for o in over])
        s = np.linalg.norm(P[E[:, 0]] - P[E[:, 1]], axis=1) / np.maximum(np.linalg.norm(Vw[E[:, 0]] - Vw[E[:, 1]], axis=1), 1e-12) - 1
        xs = s - np.maximum(np.maximum(gs[E[:, 0]], gs[E[:, 1]]), 0)
        th1 = _dihedral(P, Tw, E2, F2)
        dc = np.abs(th1 - th0)
        xc = dc - np.maximum(gc[E2[:, 0]], gc[E2[:, 1]])
        new = (th0 <= climit) & (th1 > climit) & (xc > 0)  # a NEW crease past every rest fold, more than the skin's
        moved = np.linalg.norm(P - Vw, axis=1) > 0.005
        me, me2 = moved[E].any(1), moved[Tw[F2].reshape(len(F2), -1)].any(1)  # (a hinge edge itself stays put)
        xs_m, xc_m = xs[me], xc[me2]
        sp = float(np.percentile(xs_m, STRAIN_Q)) if len(xs_m) else 0.0
        smax = float(xs_m.max()) if len(xs_m) else 0.0
        cmax = float(xc_m.max()) if len(xc_m) else 0.0
        nw = new & me2
        worst = E2[nw][np.argmax(th1[nw])] if nw.any() else (E2[me2][np.argmax(xc_m)] if len(xc_m) else None)
        regs, sreg = {}, {}
        for e, v in zip(E2[nw], th1[nw]):
            regs[region[e[0]]] = max(regs.get(region[e[0]], 0.0), round(float(v), 1))
        for e in E[me][xs_m > cap]:
            sreg[region[e[0]]] = sreg.get(region[e[0]], 0) + 1
        bNp = _vnormals(bP, bT)
        side1 = ((P - bP[near]) * bNp[near]).sum(1)
        through = (side0 >= 0) & (side1 < -THROUGH)
        rows[pn] = {"strain_p99": round(sp, 4), "strain_max": round(smax, 4), "crease_excess_max_deg": round(cmax, 1),
                    "new_creases": int(nw.sum()), "crease_where": (region[worst[0]] if worst is not None else None),
                    "crease_at": (np.round(Vw[worst].mean(0), 3).tolist() if worst is not None else None),
                    "crease_regions": regs, "strain_regions": sreg,
                    "body_crease_max_deg": round(float(bc[near[np.unique(E2[me2])]].max()) if me2.any() else 0.0, 1),
                    "body_strain_p99": round(float(np.percentile(bs[near[moved]], STRAIN_Q)) if moved.any() else 0.0, 4),
                    "skin_through": int(through.sum()), "vertices_moved": int(moved.sum()),
                    "ok": bool(sp <= cap and not nw.any())}
        posed_out[pn] = (P, bP)
    return {"limits": {"strain_p99": cap, "crease_deg": round(climit, 1)}, "poses": rows,
            "ok": all(r["ok"] for r in rows.values()), "posed": posed_out, "welded": (Vw, Tw, Jw, Ww)}


def rows_text(d: dict) -> list[str]:
    L = d["limits"]
    out = [f"  bend check (garment vs the body under it; limits: strain p99 <= {L['strain_p99']} (thread cap), "
           f"no new crease past {L['crease_deg']} deg (the soft cloth's sharpest rest fold, p99; floor {CREASE_FLOOR:.0f}))"]
    for pn, r in d["poses"].items():
        out.append(f"    {pn}: {'PASS' if r['ok'] else 'FAIL'} strain over the skin's p99 {r['strain_p99']:+.3f} max "
                   f"{r['strain_max']:+.3f}; new creases {r['new_creases']} (worst at {r['crease_where']} {r['crease_at']}; "
                   f"crease change over the skin's max {r['crease_excess_max_deg']} deg); skin through {r['skin_through']} / "
                   f"{r['vertices_moved']} moved; the body's own: crease change max {r['body_crease_max_deg']} deg, "
                   f"strain p99 {r['body_strain_p99']:+.3f}")
    return out
