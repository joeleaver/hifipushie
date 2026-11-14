"""The seam check: exported tiles read back and judged where they meet (gaps, shards, creases, skirts, lakes).
Part of the terrain mesh (terrain_mesh.py has the overview)."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from scipy.spatial import cKDTree

from . import terrain_mesh
from .terrain_gltf import _from_gltf, read_glb
from .terrain_map_seams import map_seams
from .terrain_tile_border import _chain_dist
from .terrain_tile_mesh import _boundary_edges, _face_normals

# ---------------------------------------------------------------- the seam check
def seam_check(out_dir, normal_deg=1.0, memo=None) -> dict:
    """Read the written tiles back and check: (1) border vertices identical across every shared edge, per LOD;
    (2) each LOD's tiles joined are watertight and consistently oriented except at the world's edge; (3) matched
    border vertices carry the same normal (under `normal_deg`), and the crease across seams is no worse than inside
    tiles; (4) every neighbouring LOD pair: chains' gaps covered by the skirts; (5) heightmap edges identical."""
    out = Path(out_dir)
    M = json.loads((out / "manifest.json").read_text())
    T = M["tile_size"]
    lods = len(M["lods"])
    # the edge of what was exported (the world's edge, or a block's when only some tiles were written)
    wlo = np.min([e["min"] for e in M["tiles"]], 0)
    whi = np.max([e["max"] for e in M["tiles"]], 0)
    failures, summary = [], {}
    tiles = {(e["i"], e["j"]): e for e in M["tiles"]}
    data = {}
    for (i, j), e in tiles.items():
        for k, L in enumerate(e["lods"]):
            if L is None:
                continue
            tr, prims = read_glb(out / L["file"])
            origin = _from_gltf(tr[None])[0]
            d = {}
            for p in prims:
                P = _from_gltf(p["POSITION"].astype(np.float64)) + origin
                d[p["extras"].get("role", "surface")] = (P, _from_gltf(p["NORMAL"].astype(np.float64)), p["indices"])
            d["_roles"] = np.zeros(len(d["surface"][2]) if "surface" in d else 0, np.int8)
            if "buried" in d:  # (a cliff shell's back: part of the mesh's structure, not of what is seen)
                empty = (np.zeros((0, 3)), np.zeros((0, 3)), np.zeros((0, 3), np.int64))
                d["visible"] = d.get("surface", empty)
                (P1, N1, F1), (P2, N2, F2) = d["visible"], d.pop("buried")
                d["surface"] = (np.vstack([P1, P2]), np.vstack([N1, N2]), np.vstack([F1, F2 + len(P1)]))
                d["_roles"] = np.r_[np.zeros(len(F1), np.int8), np.ones(len(F2), np.int8)]
            data[i, j, k] = d
    # (2) watertight per LOD
    for k in range(lods):
        allP, allF, off, ftile, frole = [], [], 0, [], []
        for (i, j) in tiles:
            if (i, j, k) not in data:
                continue
            P, _, F = data[i, j, k]["surface"]
            allP.append(P)
            allF.append(F + off)
            ftile.append(np.tile([i, j], (len(F), 1)))
            frole.append(data[i, j, k]["_roles"])
            off += len(P)
        P = np.vstack(allP)
        F = np.vstack(allF)
        ftile, frole = np.vstack(ftile), np.concatenate(frole)
        _, uid = np.unique(P, axis=0, return_inverse=True)
        F = uid.ravel()[F]
        ok3 = (F[:, 0] != F[:, 1]) & (F[:, 1] != F[:, 2]) & (F[:, 0] != F[:, 2])
        F, ftile, frole = F[ok3], ftile[ok3], frole[ok3]
        e = np.concatenate([F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]])
        nmax = int(F.max()) + 1
        fwd = e[:, 0] * nmax + e[:, 1]
        rev = e[:, 1] * nmax + e[:, 0]
        und = np.minimum(fwd, rev)
        u, cnt = np.unique(und, return_counts=True)
        fu, fcnt = np.unique(fwd, return_counts=True)
        dup_dir = int(np.sum(fcnt > 1))  # the same directed edge twice: flipped or overlapping faces
        Pu = np.zeros((nmax, 3))
        Pu[uid.ravel()] = np.vstack(allP)
        single = u[cnt == 1]
        a, b = single // nmax, single % nmax
        at_edge = (_at_world_edge(Pu[a], wlo, whi) & _at_world_edge(Pu[b], wlo, whi))
        open_inside = int(np.sum(~at_edge))
        nonman = int(np.sum(cnt > 2))
        summary[f"lod{k}_watertight"] = {"vertices": int(nmax), "triangles": int(len(F)), "open_edges_inside": open_inside,
                                          "open_edges_world_edge": int(np.sum(at_edge)), "non_manifold_edges": nonman,
                                          "same_direction_edges": dup_dir}
        # shading: a face whose corner normals point away from it renders as a black shard (a jump in the field
        # under it, or a fold decimation left)
        sh = _shards([data[i, j, k].get("visible", data[i, j, k]["surface"]) for (i, j) in tiles if (i, j, k) in data])
        if sh["faces"]:  # (which tiles: a designer can't tell a feature from a world point)
            per = [((i, j), _shards([data[i, j, k].get("visible", data[i, j, k]["surface"])]))
                   for (i, j) in tiles if (i, j, k) in data]
            per = sorted(((q["area_m2"], q["faces"], ij) for ij, q in per if q["faces"]), reverse=True)[:6]
            sh["tiles"] = [{"tile": list(ij), "faces": n_, "area_m2": a_} for a_, n_, ij in per]
        summary[f"lod{k}_shards"] = sh
        if sh["area_pct"] > terrain_mesh.SHARD_LIMIT[min(k, len(terrain_mesh.SHARD_LIMIT) - 1)]:
            failures.append(f"LOD {k}: {sh['faces']} faces ({sh['area_pct']}% of the visible area, limit "
                            f"{terrain_mesh.SHARD_LIMIT[min(k, len(terrain_mesh.SHARD_LIMIT) - 1)]}%) with corner normals "
                            f"against the face: black shards (e.g. at {sh['at'][:3]}; most in tiles "
                            + ", ".join(f"{q['tile'][0]},{q['tile'][1]} ({q['faces']})" for q in sh["tiles"][:4]) + ")")
        if open_inside or nonman or dup_dir:
            bad = np.r_[a[~at_edge], u[cnt > 2] // nmax, fu[fcnt > 1] // nmax]
            ex = Pu[bad[:3]].round(2).tolist()
            # (which tiles and primitives the bad edges' faces are in: an edge's faces, by its undirected key)
            bad_keys = np.r_[single[~at_edge], u[cnt > 2], np.minimum(fu[fcnt > 1], (fu[fcnt > 1] % nmax) * nmax
                                                                       + fu[fcnt > 1] // nmax)]
            fe = np.tile(np.arange(len(F)), 3)
            hit = fe[np.isin(und, bad_keys[:20])]
            where = sorted({(int(ftile[f][0]), int(ftile[f][1]), ("surface", "buried")[int(frole[f])]) for f in hit})
            failures.append(f"LOD {k}: {open_inside} open edges inside the world, {nonman} non-manifold, "
                            f"{dup_dir} doubled directed edges (e.g. at {ex}; tiles/primitives {where[:6]})")
    # (1, 3, 4) shared edges
    worst_n, worst_gap, n_edges, uncovered = 0.0, 0.0, 0, 0
    crease_seam, crease_in = [], []
    for (i, j) in tiles:
        for (di, dj, ax) in ((1, 0, 0), (0, 1, 1)):
            if (i + di, j + dj) not in tiles:
                continue
            lim = np.array(tiles[i, j]["max"])[ax]
            n_edges += 1
            for k in range(lods):
                A, B = data.get((i, j, k)), data.get((i + di, j + dj, k))
                if A is None or B is None:
                    if (A is None) != (B is None):
                        failures.append(f"tiles {i},{j} / {i + di},{j + dj} LOD {k}: one side has no mesh")
                    continue
                # (the chains along the plane, by position, without edges ON a tile corner's vertical line: such an
                # edge's other face may be in the third or fourth tile at that corner (the island's 21,6 / 22,6 at
                # LOD 2: its partner was 21,7), and the watertight check above covers them. Vertices: only those on a
                # chain: marching cubes at a lattice node within a hair of the surface left a 0.4 mm sliver face lying
                # IN the plane (11,8 / 12,8), its third vertex on the plane but on no chain, a vertex of one side)
                oth = 1 - ax
                cl = (np.array(tiles[i, j]["min"])[oth], np.array(tiles[i, j]["max"])[oth])
                ca, na, ea = _plane_chain(A["surface"], ax, lim, cl)
                cb, nb, eb = _plane_chain(B["surface"], ax, lim, cl)
                sa = {tuple(p): r for r, p in enumerate(ca)}
                sb = {tuple(p): r for r, p in enumerate(cb)}
                if set(sa) != set(sb):
                    failures.append(f"tiles {i},{j} / {i + di},{j + dj} LOD {k}: border vertices differ "
                                    f"({len(set(sa) - set(sb))} / {len(set(sb) - set(sa))} unmatched)")
                    continue
                if ea != eb:
                    failures.append(f"tiles {i},{j} / {i + di},{j + dj} LOD {k}: border edges differ")
                common = list(sa)
                if common:
                    va = na[[sa[p] for p in common]]
                    vb = nb[[sb[p] for p in common]]
                    # (a zero normal is its own fault, not a mismatch: both tiles' zero normals read as 90 deg)
                    z0 = (np.linalg.norm(va, axis=1) < 0.5) | (np.linalg.norm(vb, axis=1) < 0.5)
                    if z0.any():
                        failures.append(f"tiles {i},{j} / {i + di},{j + dj} LOD {k}: {int(z0.sum())} border vertices "
                                        f"with a zero normal (e.g. at "
                                        f"{np.round(np.array(common)[z0][:2], 2).tolist()})")
                    ang = np.degrees(np.arccos(np.clip((va * vb).sum(1)[~z0], -1, 1))).max() if (~z0).any() else 0.0
                    worst_n = max(worst_n, float(ang))
                    if ang > normal_deg:
                        failures.append(f"tiles {i},{j} / {i + di},{j + dj} LOD {k}: normals differ by {ang:.2f} deg")
                    if k == 0:
                        crease_seam.append(_crease(A["surface"], B["surface"], ax, lim))
            # (4) LOD pairs: the gap between chains must be covered by a skirt
            for ka in range(lods):
                for kb in range(lods):
                    if ka == kb:
                        continue
                    A, B = data.get((i, j, ka)), data.get((i + di, j + dj, kb))
                    if A is None or B is None:
                        continue
                    segA, segB = _plane_segs(A["surface"], ax, lim), _plane_segs(B["surface"], ax, lim)
                    if not len(segA) or not len(segB):
                        if len(segA) != len(segB):
                            failures.append(f"tiles {i},{j} LOD {ka} / {i + di},{j + dj} LOD {kb}: a chain on one "
                                            f"side only")
                        continue
                    ptsA = np.unique(segA.reshape(-1, 3), axis=0)
                    gap = _chain_dist(ptsA, segB)
                    depA = _skirt_depth(A, ptsA)
                    ptsB = np.unique(segB.reshape(-1, 3), axis=0)
                    depB = _skirt_depth(B, ptsB)
                    _, near = cKDTree(ptsB).query(ptsA)
                    cover = np.maximum(depA, depB[near])
                    bad = gap > cover + 1e-3
                    worst_gap = max(worst_gap, float(gap.max()))
                    if bad.any():
                        uncovered += int(bad.sum())
                        failures.append(f"tiles {i},{j} LOD {ka} / {i + di},{j + dj} LOD {kb}: {int(bad.sum())} chain "
                                        f"points with a gap ({gap[bad].max():.2f} m) deeper than the skirts "
                                        f"({cover[bad].min():.2f} m)")
    for (i, j) in tiles:
        if (i, j, 0) in data:
            crease_in.append(_crease_inside(data[i, j, 0]["surface"]))
    summary["shared_edges"] = n_edges
    summary["border_normal_max_deg"] = round(worst_n, 4)
    cs = np.concatenate([c for c in crease_seam if len(c)]) if crease_seam else np.zeros(0)
    ci = np.concatenate([c for c in crease_in if len(c)]) if crease_in else np.zeros(0)
    summary["lod0_face_crease_deg"] = {"across_seams_p50_p99": [round(float(np.percentile(cs, q)), 2) for q in (50, 99)]
                                       if len(cs) else None,
                                       "inside_tiles_p50_p99": [round(float(np.percentile(ci, q)), 2) for q in (50, 99)]
                                       if len(ci) else None}
    summary["lod_pairs_max_gap_m"] = round(worst_gap, 3)
    summary["lod_pairs_uncovered_points"] = uncovered
    # (5) heightmaps
    hm_bad = 0
    for (i, j), e in tiles.items():
        if not e.get("heightmap"):
            continue
        h = np.load(out / e["heightmap"])
        if (i + 1, j) in tiles:
            h2 = np.load(out / tiles[i + 1, j]["heightmap"])
            hm_bad += int(np.any(h[:, -1] != h2[:, 0]))
        if (i, j + 1) in tiles:
            h2 = np.load(out / tiles[i, j + 1]["heightmap"])
            hm_bad += int(np.any(h[0, :] != h2[-1, :]))  # rows north-up: this tile's north row = the next's south
    summary["heightmap_edges_differing"] = hm_bad
    if hm_bad:
        failures.append(f"{hm_bad} heightmap tile edges differ from their neighbours'")
    if M.get("maps"):  # (6) baked maps agree across borders
        ms = map_seams(out, M["tiles"], lods, memo=memo)
        summary["map_seams"] = ms
        for key, r in ms.items():
            if not r["ok"]:
                lim_ = terrain_mesh.MAP_SEAM[min(int(key[-1]), len(terrain_mesh.MAP_SEAM) - 1)]
                failures.append(f"{key}: baked maps differ across tile borders in {r['bad']}: "
                                + ", ".join(f"{c} p50/p95 {r[c]} (limit "
                                            f"{lim_[c] if c in lim_ else lim_['weights']}); worst borders "
                                            + ", ".join(f"{a[0]},{a[1]}|{b[0]},{b[1]} {p}"
                                                        for p, a, b in r.get("worst", {}).get(c, [])[:3])
                                            for c in r["bad"])
                                + " (a visible seam in shading / ground layers along those borders at that LOD)")
    # (7) steps in the baked surface on soft ground (terrain_bake_maps.bake_texels' jumps): a sub-texel step in the field's
    # value, which the normal map draws as a thin dark line across the grass (pushieworld note 104: no other check saw it)
    jl = []
    for (i, j), e in tiles.items():
        for k, L in enumerate(e["lods"]):
            n = int(((L or {}).get("maps") or {}).get("jumps", 0) or 0)
            if n:
                jl.append((n, i, j, k, (L["maps"].get("jump_at") or [None])[0]))
    summary["soft_ground_jumps"] = {"total": sum(a[0] for a in jl), "tile_lods": len(jl),
                                    "worst": [[a[1], a[2], a[3], a[0], a[4]] for a in sorted(jl, key=lambda a: -a[0])[:5]]}
    over = [a for a in jl if a[0] > terrain_mesh.JUMP_LIMIT]
    if over:
        over.sort(key=lambda a: -a[0])
        failures.append(f"steps in the baked surface on soft ground in {len(over)} tile LODs (over {terrain_mesh.JUMP_LIMIT} sampled "
                        "texels each): " + ", ".join(f"{i},{j} LOD {k} {n} at {at[:3] if at else '?'}"
                                                     for n, i, j, k, at in over[:4])
                        + " (thin dark lines in the normal map: a step in the field's value, e.g. a weight cut off)")
    summary["failures"] = len(failures)
    (out / "seam_check.json").write_text(json.dumps({"summary": summary, "failures": failures}, indent=1))
    return {"summary": summary, "failures": failures}


def lake_outlines(T) -> dict:
    """Per lake (not the sea): its level, centre, area and the water's outline as closed rings of [x, y] (m), for an
    engine's water system. The tile heightmaps hold each lake under its level (the export's lake check floods them)."""
    from skimage import measure
    out = {}
    lid = getattr(T, "lake_id", None)
    for name, lk in (getattr(T, "lakes", None) or {}).items():
        if lk.get("sea") or lid is None or not lk.get("area"):
            continue
        m = np.pad((lid == lk["id"]).astype(float), 1)
        rings = []
        for c in measure.find_contours(m, 0.5):
            if len(c) < 8:
                continue
            step = max(1, len(c) // 400)
            xy = np.c_[T.xs[0] + (c[::step, 1] - 1) * T.cell, T.ys[0] + (c[::step, 0] - 1) * T.cell]
            rings.append(np.round(xy, 2).tolist())
        rings.sort(key=len, reverse=True)
        out[name] = {"level": round(float(lk["level"]), 3), "at": [round(float(v), 2) for v in lk["xy"]],
                     "area_m2": round(float(lk["area"]), 1), "depth_m": round(float(lk.get("depth", 0)), 2),
                     "outline": rings}
    return out


def _shards(surfs):
    """Faces with a corner normal against the face (dot < 0): count, area share, worst places."""
    n = a_bad = a_all = 0
    at = []
    for P, N, F in surfs:
        fn = np.cross(P[F[:, 1]] - P[F[:, 0]], P[F[:, 2]] - P[F[:, 0]])
        A = np.linalg.norm(fn, axis=1) / 2
        fn /= np.maximum(2 * A, 1e-20)[:, None]
        m = np.einsum("fcj,fj->fc", N[F], fn).min(1)
        b = m < 0
        n += int(b.sum())
        a_bad += float(A[b].sum())
        a_all += float(A.sum())
        at += [(float(A[f]), P[F[f]].mean(0).round(1).tolist()) for f in np.flatnonzero(b)]
    at = [p for _, p in sorted(at, reverse=True)[:5]]
    return {"faces": n, "area_m2": round(a_bad, 2), "area_pct": round(100 * a_bad / max(a_all, 1e-9), 4), "at": at}


def _at_world_edge(P, lo, hi):
    return (P[:, 0] == lo[0]) | (P[:, 0] == hi[0]) | (P[:, 1] == lo[1]) | (P[:, 1] == hi[1])


def _on_plane(surf, ax, lim):
    P, N, _ = surf
    k = P[:, ax] == lim
    return P[k], N[k]


def _plane_chain(surf, ax, lim, corners):
    """A tile's border chain on one plane, by position: (vertices, their normals, edges as sets of two positions).
    Boundary edges of the mesh welded by position (split normals duplicate vertices) lying in the plane, except edges
    along a tile corner's vertical line (`corners`: the plane's two ends on the other axis); vertices = their ends."""
    P, N, F = surf
    if not len(F):
        return np.zeros((0, 3)), np.zeros((0, 3)), set()
    Pu, first, uid = np.unique(P, axis=0, return_index=True, return_inverse=True)
    Fw = uid.ravel()[F]
    Fw = Fw[(Fw[:, 0] != Fw[:, 1]) & (Fw[:, 1] != Fw[:, 2]) & (Fw[:, 0] != Fw[:, 2])]
    be = _boundary_edges(Fw)
    on = (Pu[be[:, 0], ax] == lim) & (Pu[be[:, 1], ax] == lim)
    oth = 1 - ax
    cor = lambda v: np.isin(Pu[v, oth], corners)
    on &= ~(cor(be[:, 0]) & cor(be[:, 1]))
    be = be[on]
    vs = np.unique(be.ravel())
    return Pu[vs], N[first[vs]], {frozenset((tuple(Pu[a]), tuple(Pu[b]))) for a, b in be}


def _plane_edges(surf, ax, lim):
    P, _, F = surf
    be = _boundary_edges(F)
    on = (P[be[:, 0], ax] == lim) & (P[be[:, 1], ax] == lim)
    return {frozenset((tuple(P[a]), tuple(P[b]))) for a, b in be[on]}


def _plane_segs(surf, ax, lim):
    P, _, F = surf
    be = _boundary_edges(F)
    on = (P[be[:, 0], ax] == lim) & (P[be[:, 1], ax] == lim)
    return np.stack([P[be[on, 0]], P[be[on, 1]]], 1) if on.any() else np.zeros((0, 2, 3))


def _skirt_depth(tile, pts):
    if "skirt" not in tile:
        return np.zeros(len(pts))
    SP = tile["skirt"][0]
    top, bot = SP[0::2], SP[1::2]
    dep = np.linalg.norm(bot - top, axis=1)
    d, k = cKDTree(top).query(pts)
    return np.where(d < 1e-6, dep[k], 0.0)


def _crease(A, B, ax, lim):
    """Angle between the faces either side of each seam edge (LOD0)."""
    out = []
    PA, _, FA = A
    PB, _, FB = B
    nA, nB = _face_normals(PA, FA), _face_normals(PB, FB)

    def edge_faces(P, F, n):
        m = {}
        near = np.flatnonzero((P[F, ax] == lim).sum(1) >= 2)
        for f in near:
            tri = F[f]
            for a, b in ((0, 1), (1, 2), (2, 0)):
                pa, pb = P[tri[a]], P[tri[b]]
                if pa[ax] == lim and pb[ax] == lim:
                    m[frozenset((tuple(pa), tuple(pb)))] = n[f]
        return m

    ma, mb = edge_faces(PA, FA, nA), edge_faces(PB, FB, nB)
    for e, na in ma.items():
        if e in mb:
            out.append(np.degrees(np.arccos(np.clip(na @ mb[e], -1, 1))))
    return np.array(out)


def _crease_inside(surf):
    P, _, F = surf
    n = _face_normals(P, F)
    e = np.concatenate([F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]])
    fid = np.tile(np.arange(len(F)), 3)
    key = np.minimum(e[:, 0], e[:, 1]) * (len(P) + 1) + np.maximum(e[:, 0], e[:, 1])
    o = np.argsort(key, kind="stable")
    ks, fs = key[o], fid[o]
    same = ks[1:] == ks[:-1]
    a, b = fs[:-1][same], fs[1:][same]
    return np.degrees(np.arccos(np.clip((n[a] * n[b]).sum(1), -1, 1)))
