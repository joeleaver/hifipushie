"""The flesh a rig weights against: cone pieces and the flesh tree. Part of rig (rig.py has the overview)."""
from __future__ import annotations

import numpy as np

from . import rig
from .rig import _segments
from .rig_model import _chain_pieces, _seg_dist, skeleton

def _cone_piece(p, a: np.ndarray, b: np.ndarray, t0: float, t1: float):
    """The part of a bone's cone between t0 and t1 along it (a -> b, radii interpolated): a rig bone's own flesh where
    it lies along the modelling bone. The skeleton walk can reach a bone from its far end (the goblin's arms, from
    the hand), so a -> b may run against the cone's own axis: the piece is laid along the cone's axis either way."""
    import copy
    q = copy.copy(p)
    pr = dict(p.params)
    L = pr["len"]
    ra, rb = pr["ra"], pr["rb"]
    if np.linalg.norm(a - pr["a"]) > np.linalg.norm(b - pr["a"]):  # reached from the cone's far end
        t0, t1 = 1.0 - t1, 1.0 - t0
    ax = pr["frame"][1]
    s, e = pr["a"] + t0 * L * ax, pr["a"] + t1 * L * ax
    pr["a"] = s
    pr["len"] = max((t1 - t0) * L, 1e-4)
    pr["ra"], pr["rb"] = ra + t0 * (rb - ra), ra + t1 * (rb - ra)
    pr["cut"] = 0.0
    q.params = pr
    q.lo, q.hi = np.minimum(s, e) - max(ra, rb) * 2, np.maximum(s, e) + max(ra, rb) * 2
    return q


def _flesh_tree(spec: dict, rb: list[dict]):
    """(rig bone indices, [{"name", "parent", "prims", "prim", "cuts"}]): the weight-carrying rig bones with their
    flesh, as `weights` takes them."""
    seg = _segments(rb)
    ids = list(seg)
    A = np.array([seg[i][0] for i in ids])
    B = np.array([seg[i][1] for i in ids])
    flesh = {i: [] for i in ids}
    base_r = None
    if spec.get("base"):  # a base body has no modelling bones (its bones are clothes, straps): each rig bone's
        # flesh is a cone along its own segment as thick as the base body there (the median distance of the base's
        # vertices that lie nearest it), measured once, so every part (skin, shirt, shoes) gets the same weights
        from . import base_implied, base_surface
        from .spec import expand_mirror as _em
        s = base_implied.inject(_em(spec))
        W = np.asarray(base_surface.surface(s, spec["base"])["quads"][0], float)
        D = np.stack([_seg_dist(W, A[q], B[q]) for q in range(len(ids))], 1)
        near = D.argmin(1)
        base_r = np.array([float(np.median(D[near == q, q])) if (near == q).sum() > 3 else np.nan
                           for q in range(len(ids))])
        mb = []
    else:
        mb = skeleton(spec)
    for b in mb:
        p, h, t = b["prim"], b["head"], b["tail"]
        ax = t - h
        L = max(float(np.linalg.norm(ax)), 1e-9)
        tol = max(0.002, 0.02 * L)
        on_m = [(_seg_dist(A[q], h, t) < tol) and (_seg_dist(B[q], h, t) < tol) for q in range(len(ids))]
        pieces = []
        for q, on in enumerate(on_m):  # rig segments lying along this bone: their piece of its cone
            if on and np.linalg.norm(B[q] - A[q]) > tol:
                t0, t1 = sorted(float(((x - h) @ ax) / L ** 2) for x in (A[q], B[q]))
                t0, t1 = max(t0, 0.0), min(t1, 1.0)
                if t1 - t0 > 0.02:
                    pieces.append((ids[q], t0, t1))
        for bl in b["prims"][1:]:  # blobs: the rig bone nearest their middle (a palm the hand, not a finger)
            pieces_ = _chain_pieces(bl, A, B) if bl.kind in rig.SOFT else None  # a torso loft: shared along the spine
            if pieces_:
                for q, pc in pieces_:
                    flesh[ids[q]].append(pc)
                continue
            flesh[ids[int(np.argmin(_seg_dist(0.5 * (bl.lo + bl.hi), A, B)))]].append(bl)
        if pieces:
            for i, t0, t1 in pieces:
                flesh[i].append(_cone_piece(p, h, t, t0, t1))
            continue
        inside = [q for q in range(len(ids)) if _seg_dist(h, A[q], B[q]) < tol and _seg_dist(t, A[q], B[q]) < tol]
        if inside:  # a curled finger's pieces find their phalanx
            flesh[ids[inside[0]]].append(p)
            continue
        # else each quarter of it goes to the rig bone nearest that quarter's middle: a tusk is all the head's, but a
        # sheet from the ribs to the arm (a lat) blends from the chest to the arm instead of dragging the ribs along
        near = [int(np.argmin(_seg_dist(h + (k + 0.5) / 4 * (t - h), A, B))) for k in range(4)]
        if len(set(near)) == 1:
            flesh[ids[near[0]]].append(p)
        else:
            for k, q in enumerate(near):
                flesh[ids[q]].append(_cone_piece(p, h, t, k / 4, (k + 1) / 4))
    for q, i in enumerate(ids):  # nothing of its own: a cone along its segment, as thick as its neighbours
        if not flesh[i]:
            have = [n for n, j in enumerate(ids) if any(x.kind == "cone" and "rb" in x.params for x in flesh[j])]
            nq = min(have, key=lambda n: float(_seg_dist(A[q], A[n], B[n]))) if have else None
            ref = next(x for x in flesh[ids[nq]] if x.kind == "cone" and "rb" in x.params) if nq is not None else None
            r = 0.4 * (min(ref.params["ra"], ref.params["rb"]) if ref is not None else 0.03)
            if base_r is not None and np.isfinite(base_r[q]):
                r = 0.8 * float(base_r[q])
            from .spec import Prim, bone_frame
            a, bb = A[q], B[q] if np.linalg.norm(B[q] - A[q]) > 1e-3 else A[q] + np.array([0, 0, 1e-3])
            flesh[i].append(Prim(rb[i]["name"], "cone", "add", 0.0, 0, np.minimum(a, bb) - r, np.maximum(a, bb) + r,
                                 {"a": a, "frame": bone_frame(a, bb), "len": float(np.linalg.norm(bb - a)), "ra": r,
                                  "rb": r, "flat": [1.0, 1.0], "bow": (0.0, 0.0), "cut": 0.0}))
    carry = [{"name": rb[i]["name"], "parent": -1, "prims": flesh[i],
              "prim": next((x for x in flesh[i] if x.kind == "cone"), flesh[i][0])} for i in ids]
    pos = {i: n for n, i in enumerate(ids)}
    for n, i in enumerate(ids):  # the rig tree among the weight-carrying bones (end joints skipped)
        par = rb[i]["parent"]
        while par >= 0 and par not in pos:
            par = rb[par]["parent"]
        carry[n]["parent"] = pos.get(par, -1)
    for n, i in enumerate(ids):  # where a chain continues through a joint, parent and child flesh meet at the plane
        pn = carry[n]["parent"]  # bisecting the two bones (the elbow's crease), so a collar's round end doesn't
        if pn < 0:  # reach over the top of the upper arm
            continue
        (a0, a1), (b0, b1) = seg[ids[pn]], seg[i]
        la, lb = np.linalg.norm(a1 - a0), np.linalg.norm(b1 - b0)
        if la < 1e-3 or lb < 1e-3 or np.linalg.norm(a1 - b0) > 1e-6:
            continue
        if carry[pn]["prim"].name == carry[n]["prim"].name:  # pieces of one cone (the spine) keep blending softly
            continue
        nrm = (a1 - a0) / la + (b1 - b0) / lb
        if np.linalg.norm(nrm) < 1e-6:
            continue
        nrm /= np.linalg.norm(nrm)
        carry[pn].setdefault("cuts", []).append((b0, nrm))
        carry[n].setdefault("cuts", []).append((b0, -nrm))
    for c in carry:
        if "ra" not in c["prim"].params:  # a blob-only bone: its falloff from the blob's size
            sz = float(np.min(c["prim"].hi - c["prim"].lo)) / 2
            c["falloff_r"] = sz
    return ids, carry
