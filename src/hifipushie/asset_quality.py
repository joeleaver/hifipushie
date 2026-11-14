"""Checks on the result: seam steps, designed interiors, mesh quality, defect regions. Part of the game-ready export (asset.py has the overview)."""
from __future__ import annotations

import numpy as np

from . import asset
from . import sdf
from .asset_raster import _bilinear

def seam_steps(p: dict, img: np.ndarray, per_texel: int = 2) -> dict | None:
    """How a map steps across a part's UV seams (edges whose two triangles have the same vertices but different
    uvs), as an engine shows it: along every seam edge, the step across it (half a texel into each chart, sampled
    bilinearly) against the steps beside it (half a texel to 1.5 texels in, on each side). excess = their ratio
    summed over the seams (~1 = invisible: the map runs on across the seam as it does inside a chart; a texel's
    misregistration of a sharp edge is ~2+), p95 = the 95th percentile of it per sample where the map changes
    (beside > 2% of its range). None if the part has no seams."""
    S = img.shape[0]
    cv = p["corner_vert"].reshape(-1, 3).astype(np.int64)
    uv = p["uv"].reshape(-1, 3, 2).astype(np.float64)
    a, b = cv, np.roll(cv, -1, 1)  # edge k runs from corner k to k + 1
    ea, eb = np.minimum(a, b).T.ravel(), np.maximum(a, b).T.ravel()
    et, ek = np.tile(np.arange(len(cv)), 3), np.repeat(np.arange(3), len(cv))
    order = np.lexsort((eb, ea))
    ea, eb, et, ek = ea[order], eb[order], et[order], ek[order]
    pair = np.flatnonzero((ea[1:] == ea[:-1]) & (eb[1:] == eb[:-1]))
    if not len(pair):
        return None
    tA, kA, tB, kB = et[pair], ek[pair], et[pair + 1], ek[pair + 1]

    def ends(t, k, v0):  # the edge's uv at vertex v0 then the other end, and the opposite corner's uv
        i0, i1 = k, (k + 1) % 3
        swap = cv[t, i0] != v0
        u0 = np.where(swap[:, None], uv[t, i1], uv[t, i0])
        u1 = np.where(swap[:, None], uv[t, i0], uv[t, i1])
        return u0, u1, uv[t, (k + 2) % 3]
    v0 = ea[pair]
    a0, a1, a2 = ends(tA, kA, v0)
    b0, b1, b2 = ends(tB, kB, v0)
    seam = (np.abs(a0 - b0).max(1) > 0.5 / S) | (np.abs(a1 - b1).max(1) > 0.5 / S)
    if not seam.any():
        return None
    a0, a1, a2, b0, b1, b2 = (x[seam] for x in (a0, a1, a2, b0, b1, b2))

    def inward(u0, u1, u2):
        d = u1 - u0
        n = np.stack([-d[:, 1], d[:, 0]], 1)
        n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-12)
        return n * np.sign(((u2 - u0) * n).sum(1))[:, None]
    nA, nB = inward(a0, a1, a2), inward(b0, b1, b2)
    m = np.maximum(np.ceil(np.linalg.norm(a1 - a0, axis=1) * S * per_texel).astype(np.int64), 1)
    e = np.repeat(np.arange(len(m)), m)
    t = (np.arange(len(e)) - np.repeat(np.cumsum(m) - m, m) + 0.5) / m[e]
    t = t[:, None]
    pa, pb = a0[e] + t * (a1[e] - a0[e]), b0[e] + t * (b1[e] - b0[e])
    A0, A1 = (_bilinear(img, pa + nA[e] * s / S) for s in (0.5, 1.5))
    B0, B1 = (_bilinear(img, pb + nB[e] * s / S) for s in (0.5, 1.5))
    across = np.linalg.norm(A0 - B0, axis=1)
    beside = 0.5 * (np.linalg.norm(A1 - A0, axis=1) + np.linalg.norm(B1 - B0, axis=1))
    rng = float(np.ptp(img.reshape(-1, img.shape[-1]), axis=0).max()) or 1.0
    busy = beside > 0.02 * rng
    eps = 0.002 * rng * len(e)  # steps under 0.2% of the map's range are noise, not edges (a flat map reads ~1)
    return {"edges": int(seam.sum()), "samples": len(e),
            "excess": round(float((across.sum() + eps) / (beside.sum() + eps)), 2),
            "p95": round(float(np.percentile(across[busy] / beside[busy], 95)), 2) if busy.sum() > 20 else None}


def _slit_mask(lid_fold, n: int) -> np.ndarray:
    """(n,) bool over GNM's vertices: the lid fold's slit and crease tail (gnm_fold_mesh.slit_ids). The fold re-sections the
    upper lid's rings into platform, slit and roll: the roll's lower edge undercuts the slit by design (the hood), so its
    edges fold against their neighbours (Garrett ~50 / Tess ~37 exterior folded edges after the wrap clamp WRAP_MAX,
    2026-10-18 r12, all on rings ring+1 / ring+2). Those are the crease, not a tear."""
    m = np.zeros(n, bool)
    if lid_fold:
        from . import gnm_fold_mesh
        ids = np.array([v for v in gnm_fold_mesh.slit_ids(lid_fold) if 0 <= v < n], int)   # (every key: the tapered ends
        # carry weight 0 for the cavity paint but are the same rings, and fold the same)
        m[ids] = True
    return m


def _designed_interior(topo, verts, creases: bool = True, lid_fold=None) -> np.ndarray | None:
    """(one mesh, own quads) per low-poly vertex: GNM's own interior surfaces (the lids' insides, the inner lip
    rolls, nostrils' depths, the mouth sock): modelled to roll back under the skin, so they fold against the field
    and stand off it by design. None when the part isn't that topology. lid_fold (the head's base.head.lid_fold):
    with creases, the fold's slit too (_slit_mask)."""
    if not topo:
        return None
    z = np.load(topo[0])
    if "gnm" not in z.files or len(z["verts"]) != len(verts) or not np.allclose(np.asarray(verts, float), z["verts"],
                                                                                   atol=1e-5):
        return None
    from . import base_identity
    g = base_identity._gnm_data()
    from . import gnmloops
    gid = gnmloops.raw_id(np.asarray(z["gnm"], int))  # (the lids' new vertices: as their first parent)
    gr = {k: np.asarray(v) > 0.5 for k, v in g["groups"].items()}
    # (+ the lips and the lid margins: closed in the neutral, their seams are creases by design; measured on the
    # adult's export they were the rest of the TORN clusters at both eyes and the mouth)
    ins = ~gr["skin_exterior"] | gr["mouth_sock"]
    if creases:
        ins = ins | gr["upper_lip"] | gr["lower_lip"] | gr["eye_sockets"] | gr["ears"]  # (ears: kept as GNM made them)
        ins = ins | _slit_mask(lid_fold, len(ins))
    return (gid >= 0) & ins[np.maximum(gid, 0)]


def mesh_quality(verts: np.ndarray, tris: np.ndarray, prims=None, designed: np.ndarray | None = None) -> dict:
    """A triangle mesh's own quality report: distance to the exact field (mm; p50/p99/max over face centres and
    edge midpoints, where a low poly strays between its vertices) when `prims` are given, and counts of
    non-manifold edges (3+ faces), open edges, folds (neighbouring faces turned > 120 deg) and slivers (smallest
    angle < 2 deg). designed: per vertex, surfaces modelled to fold back (a one-mesh head's lid insides, lip rolls
    and mouth sock): triangles touching them are left out of the distance, folds and turned faces."""
    if designed is not None and designed.any():
        keep = ~np.asarray(designed, bool)[np.asarray(tris)].any(1)  # (and their rims: a lid's margin folds back)
        q = mesh_quality(verts, np.asarray(tris)[keep], prims)
        q["designed_triangles"] = int((~keep).sum())
        return q
    P = np.asarray(verts, np.float64)
    key = np.round(P / 1e-6).astype(np.int64)  # weld split vertices (uv seams) by position
    _, weld = np.unique(key, axis=0, return_inverse=True)
    T = weld.reshape(-1)[np.asarray(tris)]
    c = P[np.asarray(tris)]
    n = np.cross(c[:, 1] - c[:, 0], c[:, 2] - c[:, 0])
    area2 = np.linalg.norm(n, axis=1)
    n = n / np.maximum(area2, 1e-30)[:, None]
    E = np.sort(np.stack([T[:, [0, 1]], T[:, [1, 2]], T[:, [2, 0]]], 1).reshape(-1, 2), axis=1)
    fid = np.repeat(np.arange(len(T)), 3)
    uniq, inv, cnt = np.unique(E, axis=0, return_inverse=True, return_counts=True)
    inv = inv.reshape(-1)
    out = {"triangles": int(len(T)), "non_manifold_edges": int((cnt > 2).sum()), "open_edges": int((cnt == 1).sum())}
    two = np.flatnonzero(cnt == 2)
    order = np.argsort(inv, kind="stable")
    first = np.searchsorted(inv[order], two)
    fa, fb = fid[order[first]], fid[order[first + 1]]
    fold = (n[fa] * n[fb]).sum(1) < -0.5
    out["folds"] = int(fold.sum())
    spots = [P[uniq[two[fold]]].mean(1)] if fold.any() else []
    ang = []
    for i in range(3):
        a, b = c[:, (i + 1) % 3] - c[:, i], c[:, (i + 2) % 3] - c[:, i]
        cosv = (a * b).sum(1) / np.maximum(np.linalg.norm(a, axis=1) * np.linalg.norm(b, axis=1), 1e-30)
        ang.append(np.degrees(np.arccos(np.clip(cosv, -1, 1))))
    out["slivers"] = int((np.min(ang, axis=0) < 2.0).sum())
    if prims is not None:
        probe = np.concatenate([c.mean(1), ((c + np.roll(c, 1, 1)) / 2).reshape(-1, 3)])
        d = np.abs(sdf.field_at(prims, probe, clip=False)) * 1000
        out.update(err_mm_p50=round(float(np.percentile(d, 50)), 2), err_mm_p99=round(float(np.percentile(d, 99)), 2),
                   err_mm_max=round(float(d.max()), 2))
        # faces turned against the surface they lie on (their normal against the field's gradient): the inside of
        # a tangle or a tear, drawn dark or culled by an engine. Only faces near the surface count (a face
        # bridging a gap has no surface to disagree with).
        fc = c.mean(1)
        ok = (d[:len(fc)] < 2.0) & (area2 > 1e-12)
        if ok.any():
            h = 2e-4
            g = np.stack([sdf.field_at(prims, fc[ok] + h * e, clip=False) - sdf.field_at(prims, fc[ok] - h * e, clip=False)
                          for e in np.eye(3)], 1)
            g /= np.maximum(np.linalg.norm(g, axis=1, keepdims=True), 1e-12)
            bad = (g * n[ok]).sum(1) < -0.3
            out["turned"] = int(bad.sum())
            if bad.any():
                spots.append(fc[ok][bad])
        else:
            out["turned"] = 0
    out["spots"] = np.concatenate(spots) if spots else np.zeros((0, 3))
    return out


def defect_regions(spots: np.ndarray, spec: dict) -> list[tuple[str, int]]:
    """Where a mesh's folded edges and turned faces are, by the model's nearest joint: [(joint, count)] for every
    joint with DEFECT_CLUSTER or more, most first (a model without joints: one entry per 10 cm cell, named by its
    position)."""
    if not len(spots):
        return []
    try:
        from .spec import expand_mirror, resolve_point
        s = expand_mirror(spec)
        names = [k for k in s.get("joints", {}) if not k.startswith("lm_")]
        J = np.array([resolve_point(s, k) for k in names], float)
        lms = [k for k in s.get("joints", {}) if k.startswith("lm_")]
        L = np.array([resolve_point(s, k) for k in lms], float).reshape(-1, 3)
    except Exception:  # noqa: BLE001
        names, J, lms, L = [], np.zeros((0, 3)), [], np.zeros((0, 3))
    if len(names):
        from scipy.spatial import cKDTree
        near = cKDTree(J).query(spots)[1]
        lab = [names[i] for i in near]
        if len(lms):  # clusters are counted by modelling joint (landmarks are many and close: they'd split one tear
            # into several small counts), but NAMED by a face landmark where one is nearer their middle: a GNM head
            # has no mouth joint, and the mouth's cluster read "TORN at eye_front.L", 8 cm away
            for nm in set(lab):
                mid = spots[[x == nm for x in lab]].mean(0)
                d, i = cKDTree(L).query(mid)
                if d < np.linalg.norm(mid - J[names.index(nm)]):
                    lab = [f"{lms[i]} (by {nm})" if x == nm else x for x in lab]
    else:
        lab = ["[%.1f, %.1f, %.1f]" % tuple(np.round(q / 0.1) * 0.1) for q in spots]
    u, cnt = np.unique(lab, return_counts=True)
    return [(str(a), int(b)) for b, a in sorted(zip(cnt, u), reverse=True) if b >= asset.DEFECT_CLUSTER]
