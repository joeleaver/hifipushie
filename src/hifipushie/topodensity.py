"""Joint-aware density for a wrapped body (asset.topology_parts): the same triangle count, spent where it bends.

Why (2026-10-14, rig_r4..r6): with arc weights and pose correctives the knee and elbow bend round, but the review
still read their fronts as "faceted, a mitred pipe": the template's quads are ~1.5 cm, six edges round a bent knee's
front, and the silhouette of a bend is all corners. A rigger puts extra loops at the joints and fewer along the
shafts. Here, within the body's budget: every face of a hinge zone (knee, elbow, shoulder, hip: `rig.arc_frames`, the
outer zone x HINGE_ZONE along the limb) is split in four (its new vertices projected onto the model's exact surface),
the faces round it are fanned from their centre (no T-junctions), and the rest of the body (away from the joints, hands, feet
and neck) are decimated, border held, by as many triangles as the joints took. GNM's head and the
seam ring are never touched (face shapes go by its vertex ids).
"""
from __future__ import annotations

import numpy as np

HINGE_ZONE = 1.6    # x the joint's outer zone half width (rig.BEND_ARC): the refined band along the limb


def _faces(L, S):
    st = np.r_[0, np.cumsum(S)[:-1]]
    return [list(L[a:a + k]) for a, k in zip(st, S)]


PAY_MARGIN = 1.4  # the hinge zones grown by this when choosing what pays (the loops' neighbours stay as they are)


def hinge_mask(bones: list[dict], V: np.ndarray, axes: bool = False, margin: float = 1.0):
    """Vertices in a hinge zone (and with axes=True each one's limb axis there)."""
    from . import rig
    m = np.zeros(len(V), bool)
    U = np.zeros((len(V), 3))
    for f in rig.arc_frames(bones):
        d = V - f["pivot"]
        s = d @ f["u"]
        rho = np.linalg.norm(d - s[:, None] * f["u"], axis=1)
        side = np.ones(len(V), bool) if f["mid"] is None else (V[:, 0] - f["mid"]) * f["side"] > 0.0
        k = (np.abs(s) < margin * HINGE_ZONE * f["outer"]) & (rho < margin * f["reach"]) & side
        m |= k
        U[k] = f["u"]
    return (m, U) if axes else m


def shaft_mask(bones: list[dict], V: np.ndarray) -> np.ndarray:
    """What pays for the joints: the body away from the hinge zones, the hands and feet (their digits keep every
    loop) and the neck (the seam ring). The limbs' shafts alone had ~1k triangles on the MakeHuman wrap."""
    names = [b["name"] for b in bones]
    P = "mixamorig:"
    m = np.ones(len(V), bool)
    for side in ("Left", "Right"):
        for b, r in (("Hand", 0.11), ("Foot", 0.13)):
            if P + side + b in names:
                m &= np.linalg.norm(V - np.asarray(bones[names.index(P + side + b)]["head"], float), axis=1) > r
    if P + "Neck" in names:
        m &= V[:, 2] < float(np.asarray(bones[names.index(P + "Neck")]["head"], float)[2]) - NECK_CLEAR
    return m


NECK_CLEAR = 0.03  # m below the Neck joint


def rebalance(bones: list[dict], V: np.ndarray, L: np.ndarray, S: np.ndarray, gnm: np.ndarray | None,
              prims=None, voxel: float = 0.003, log: list | None = None):
    """(V, L, S, gnm) with the hinge zones refined and the shafts thinned to the same triangle total."""
    log = log if log is not None else []
    V = np.asarray(V, float)
    faces = _faces(np.asarray(L), np.asarray(S))
    ntri0 = int((np.asarray(S) - 2).sum())
    head = np.zeros(len(V), bool) if gnm is None else np.asarray(gnm) >= 0
    # faces touching the head (the seam ring) stay as they are
    touch_head = np.array([head[f].any() for f in faces])
    hz, U = hinge_mask(bones, V, axes=True)
    hz &= ~head
    ref = np.array([len(f) == 4 and hz[f].all() for f in faces]) & ~touch_head
    # 1) a loop inserted across the limb in every hinge quad: its two edges running ALONG the limb split at their
    # midpoints, the quad into two (a rigger's extra loops at a joint)
    newV = [V]
    nV = len(V)
    mid = {}

    def midpoint(a, b):
        nonlocal nV
        k = (min(a, b), max(a, b))
        if k not in mid:
            mid[k] = nV
            newV.append(((V[a] + V[b]) / 2)[None])
            nV += 1
        return mid[k]

    def centre(f):
        nonlocal nV
        newV.append(V[f].mean(0)[None])
        nV += 1
        return nV - 1
    out = []
    for f, r in zip(faces, ref):
        if not r:
            continue
        a, b, c, d = f
        u = U[f].mean(0)
        u /= max(np.linalg.norm(u), 1e-12)

        def along(p, q):
            e = V[q] - V[p]
            return abs(e @ u) / max(np.linalg.norm(e), 1e-12)
        if along(a, b) + along(c, d) >= along(b, c) + along(d, a):
            m1, m2 = midpoint(a, b), midpoint(c, d)
            out += [[a, m1, m2, d], [m1, b, c, m2]]
        else:
            m1, m2 = midpoint(b, c), midpoint(d, a)
            out += [[a, b, m1, m2], [m2, m1, c, d]]
    # 2) every other face: a split edge gets its midpoint; such a face is fanned from its centre
    for f, r in zip(faces, ref):
        if r:
            continue
        n = len(f)
        ring = []
        for i in range(n):
            ring.append(f[i])
            k = (min(f[i], f[(i + 1) % n]), max(f[i], f[(i + 1) % n]))
            if k in mid:
                ring.append(mid[k])
        if len(ring) == n:
            out.append(list(f))
            continue
        c = centre(f)
        for i in range(len(ring)):
            out.append([c, ring[i], ring[(i + 1) % len(ring)]])
    V2 = np.concatenate(newV)
    newv = np.arange(len(V), len(V2))
    if prims is not None and len(newv):  # the new vertices onto the exact surface (Newton steps on the field)
        from . import sdf
        tri = np.array([t for p in out for t in ([p] if len(p) == 3 else [[p[0], p[1], p[2]], [p[0], p[2], p[3]]])])
        Pp, _ = sdf.project(prims, V2, tri, voxel)
        V2[newv] = np.asarray(Pp)[newv]
    gnm2 = None if gnm is None else np.r_[np.asarray(gnm), -np.ones(len(V2) - len(V), int)]
    ntri1 = sum(len(p) - 2 for p in out)
    extra = ntri1 - ntri0
    # 3) the shafts pay: their faces triangulated and decimated with their border held, by `extra` triangles
    sh = shaft_mask(bones, V2) & ~hinge_mask(bones, V2, margin=PAY_MARGIN)
    if gnm2 is not None:
        sh &= gnm2 < 0
    shaft_f = np.array([sh[p].all() for p in out])
    if extra > 0 and shaft_f.any():
        from . import lods
        keep = [p for p, s in zip(out, shaft_f) if not s]
        T = np.array([t for p, s in zip(out, shaft_f) if s
                      for t in ([p] if len(p) == 3 else [[p[0], p[1], p[2]], [p[0], p[2], p[3]]])])
        used = np.unique(T)
        loc = np.full(len(V2), -1)
        loc[used] = np.arange(len(used))
        target = max(len(T) - extra, len(T) // 3)
        Vd, Fd = lods._decimate(V2[used], loc[T], target)
        # border vertices come back at their own positions: match them, the rest are new
        from scipy.spatial import cKDTree
        dist, near = cKDTree(V2[used]).query(Vd)
        idx = np.where(dist < 1e-9, used[near], -1)
        fresh = np.flatnonzero(idx < 0)
        idx[fresh] = len(V2) + np.arange(len(fresh))
        V2 = np.concatenate([V2, Vd[fresh]])
        if gnm2 is not None:
            gnm2 = np.r_[gnm2, -np.ones(len(fresh), int)]
        out = keep + [list(idx[t]) for t in Fd]
        log.append(f"body density: hinge zones {int(ref.sum())} faces split, +{extra} triangles; shafts "
                   f"{len(T)} -> {len(Fd)} triangles")
    # drop unused vertices
    Lf = np.concatenate([np.asarray(p) for p in out])
    used = np.unique(Lf)
    rm = np.full(len(V2), -1)
    rm[used] = np.arange(len(used))
    S2 = np.array([len(p) for p in out])
    log.append(f"body density: {ntri0} -> {int((S2 - 2).sum())} triangles")
    return V2[used], rm[Lf], S2, (None if gnm2 is None else gnm2[used])
