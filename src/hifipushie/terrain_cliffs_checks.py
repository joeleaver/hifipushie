"""Checks on the ground against the cliffs: buried over ground, exposed buried, floating, lifted, lakes. Part of the terrain cliffs (terrain_cliffs.py has the overview)."""
from __future__ import annotations

from pathlib import Path

import numpy as np
from scipy import ndimage

from . import terrain_cliffs
from . import terrain_gltf
from .terrain_cliffs import CliffField, Region

def buried_over_ground(out: Path, M: dict, lod: int = 0) -> dict:
    """The guarantee "the shell's back sinks under the heightmap" measured as a consumer does (pushieworld note 123,
    their tools/dev/buried_exposed.py): LOD `lod` "buried" faces whose centre stands more than OVER_GROUND m over
    the highest corner of the ground tile's heightmap cell under it. Most of it lies inside the rock (between the
    shell's surface and the pushed ground) and is never seen; `buried_in_the_open` is the visible kind. Info, not a
    failure: {area_m2, tiles: [[i, j, m2]] worst first, worst: [[x, y, z, m over]]}."""
    hm = {(e["i"], e["j"]): e for e in M.get("ground", []) if e.get("heightmap")}
    T = float(M["tile_size"])
    total, per, worst = 0.0, [], []
    for e in M["tiles"]:
        L = e["lods"][lod] if len(e["lods"]) > lod else None
        g = hm.get((e["i"], e["j"]))
        if not L or g is None:
            continue
        H = np.load(out / g["heightmap"])[::-1]  # (row 0 south)
        n = H.shape[0] - 1
        d = T / n
        x0, y0 = g["min"][0], g["min"][1]
        tr, prims = terrain_gltf.read_glb(out / L["file"])
        o = terrain_gltf._from_gltf(tr[None])[0]
        for p in prims:
            if p["extras"].get("role") != "buried":
                continue
            P = terrain_gltf._from_gltf(p["POSITION"].astype(np.float64)) + o
            F = p["indices"]
            c = P[F].mean(1)
            a = np.linalg.norm(np.cross(P[F[:, 1]] - P[F[:, 0]], P[F[:, 2]] - P[F[:, 0]]), axis=1) / 2
            xi = np.clip(((c[:, 0] - x0) / d).astype(int), 0, n - 1)
            yi = np.clip(((c[:, 1] - y0) / d).astype(int), 0, n - 1)
            top = np.maximum(np.maximum(H[yi, xi], H[yi + 1, xi]), np.maximum(H[yi, xi + 1], H[yi + 1, xi + 1]))
            up = c[:, 2] - top
            m = up > terrain_cliffs.OVER_GROUND
            if m.any():
                ar = float(a[m].sum())
                total += ar
                per.append([e["i"], e["j"], round(ar, 1)])
                k = np.flatnonzero(m)[np.argsort(-up[m])[:2]]
                worst += [[*c[i].round(1).tolist(), round(float(up[i]), 2)] for i in k]
    per.sort(key=lambda r: -r[2])
    worst.sort(key=lambda r: -r[3])
    return {"area_m2": round(total, 1), "tiles": per[:10], "worst": worst[:6]}


def exposed_buried(out: Path, M: dict, R: Region, tiles=None) -> list[dict]:
    """Faces of the "buried" primitive (a cliff shell's back: drawn plain, meant to lie under the heightmap or inside the
    rock) that stand in the open: the point EXPOSED_OFF m out from the face (along its normal) is air in the true rock
    field and above the pushed heightmap. Seen in the engine as flat pale triangles through a cliff (the island's Kaze
    stacks at LOD 1-2, 10-20 m across). Per tile LOD: [{tile, lod, faces, area_m2, at}], worst first."""
    rows = []
    for e in M["tiles"]:
        if tiles is not None and (e["i"], e["j"]) not in tiles:
            continue
        for k, L in enumerate(e["lods"]):
            if not L:
                continue
            tr, prims = terrain_gltf.read_glb(out / L["file"])
            o = terrain_gltf._from_gltf(tr[None])[0]
            for p in prims:
                if p["extras"].get("role") != "buried":
                    continue
                P = terrain_gltf._from_gltf(p["POSITION"].astype(np.float64)) + o
                F = p["indices"]
                n = np.cross(P[F[:, 1]] - P[F[:, 0]], P[F[:, 2]] - P[F[:, 0]])
                a = np.linalg.norm(n, axis=1) / 2
                c = P[F].mean(1)
                q = c + terrain_cliffs.EXPOSED_OFF * n / np.maximum(2 * a, 1e-12)[:, None]
                above = q[:, 2] > R.height(q[:, 0], q[:, 1]) + 0.05
                bad = np.zeros(len(F), bool)
                if above.any():
                    bad[above] = R.base.value(q[above]) > 0.05
                if bad.any():
                    w = np.flatnonzero(bad)
                    rows.append({"tile": [e["i"], e["j"]], "lod": k, "faces": int(len(w)),
                                 "area_m2": round(float(a[w].sum()), 2),
                                 "at": c[w[np.argmax(a[w])]].round(1).tolist()})
    rows.sort(key=lambda r: -r["area_m2"])
    return rows


def floating(out: Path, M: dict, R: Region, lod: int = 0, tol: float = 0.15, memo=None, tile_keys=None) -> dict:
    """Connected pieces of the cliff meshes (LOD `lod`, every tile welded by position) that never reach down to the
    ground: a piece is grounded if some vertex lies at or under the pushed heightmap (+ tol) or under the sea floor
    it stands on; one that doesn't floats in the air (a stack's head cut off by the rock relief, a shell fragment).
    Each tile's clearances (pointwise) can come from `memo` by its GLB's bytes and `tile_keys[i, j]` (what the pushed
    heightmap reads there: the incremental export's field key)."""
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components
    from . import terrain_incremental as inc
    Ps, Fs, Cs, off = [], [], [], 0
    for e in M["tiles"]:
        L = e["lods"][lod]
        if not L:
            continue
        tr, prims = terrain_gltf.read_glb(out / L["file"])
        o = terrain_gltf._from_gltf(tr[None])[0]
        tp = []
        for p in prims:
            if p["extras"].get("role") == "skirt":
                continue
            P = terrain_gltf._from_gltf(p["POSITION"].astype(np.float64)) + o
            Ps.append(P)
            tp.append(P)
            Fs.append(p["indices"] + off)
            off += len(P)
        if tp:
            Q = np.vstack(tp)
            key = None
            if memo is not None and tile_keys is not None and (e["i"], e["j"]) in tile_keys:
                key = inc._h("clearance", inc.file_hash(out / L["file"]), tile_keys[e["i"], e["j"]])
            c = memo.get(key) if key is not None else None
            if c is None:
                c = Q[:, 2] - R.height(Q[:, 0], Q[:, 1])
                if key is not None:
                    memo.put(key, c)
            Cs.append(c)
    if not Ps:
        return {"components": 0, "floating": []}
    P, F = np.vstack(Ps), np.vstack(Fs)
    _, uid, inv = np.unique(np.round(P, 4), axis=0, return_index=True, return_inverse=True)
    F = inv.ravel()[F]
    P = P[uid]
    n = len(P)
    e = np.concatenate([F[:, [0, 1]], F[:, [1, 2]]])
    ncomp, lab = connected_components(coo_matrix((np.ones(len(e)), (e[:, 0], e[:, 1])), shape=(n, n)), directed=False)
    clear = np.concatenate(Cs)[uid]  # (pointwise: each tile's own, the same as over all points at once)
    # a piece that runs off the exported block (an `only` export: the tile beyond wasn't made, but the world goes on)
    # continues there: on a wall steep all the way across the block the shell never came down to the ground inside it
    have = {(g["i"], g["j"]) for g in M.get("ground", [])} or {(e["i"], e["j"]) for e in M["tiles"]}
    G = R.G
    off = np.zeros(len(P), bool)
    for ax in (0, 1):
        t = (P[:, ax] - G.origin[ax]) / G.tile
        on = np.abs(t - np.round(t)) < 1e-6
        inner = (P[:, ax] > G.lo[ax] + 1e-6) & (P[:, ax] < G.hi[ax] - 1e-6)
        k = np.flatnonzero(on & inner)
        if not len(k):
            continue
        line = np.round(t[k]).astype(int)
        other = np.floor((P[k, 1 - ax] - G.origin[1 - ax]) / G.tile).astype(int)
        for side in (line - 1, line):  # the tiles either side of the plane
            ij = [(s_, o) if ax == 0 else (o, s_) for s_, o in zip(side, other)]
            off[k] |= np.array([q not in have for q in ij])
    clear = np.where(off, -np.inf, clear)
    low = np.full(ncomp, np.inf)
    np.minimum.at(low, lab, clear)
    tri = np.bincount(lab[F[:, 0]], minlength=ncomp)
    out_ = []
    for c in np.flatnonzero(low > tol):
        at = P[lab == c].mean(0)
        out_.append({"triangles": int(tri[c]), "clearance_m": float(low[c]), "at": at.round(1).tolist()})
    out_.sort(key=lambda f: -f["triangles"])
    return {"components": int(ncomp), "floating": out_}


def lifted(cf: CliffField, P, N):
    """Vertices of a cliff shell's front moved up onto the true ground where the front is the sunk construction
    (CliffField.lift), their normals eased to the ground's: where its AO is measured (see UNSUNK_BAND)."""
    P = np.asarray(P, float)
    w, q = cf.lift(P)
    k = np.flatnonzero(w > 0)
    if not len(k):
        return P, N
    P, N = P.copy(), np.asarray(N, float).copy()
    g = cf.base.value_gradient(q[k], 0.25)[1]
    g /= np.maximum(np.linalg.norm(g, axis=1, keepdims=True), 1e-12)
    P[k] += w[k, None] * (q[k] - P[k])
    n = N[k] * (1 - w[k, None]) + g * w[k, None]
    N[k] = n / np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-12)
    return P, N


def lake_check(out: Path, M: dict) -> dict:
    """Each lake of the manifest flooded on the written tile heightmaps to its level, from its outline: the water's
    area against the designed lake. A dam the heightmaps lost (taken for a cliff and pushed away) floods the valley
    below (pushieworld note 106: 134,000 m2 for 3,300)."""
    from skimage.draw import polygon as _poly
    failures, summary = [], {}
    lakes = M.get("lakes") or {}
    tiles = {(e["i"], e["j"]): e for e in M.get("ground", []) if e.get("heightmap")}
    if not lakes or not tiles:
        return {"summary": summary, "failures": failures}
    T = float(M["tile_size"])
    e0 = next(iter(tiles.values()))
    n = int(np.load(out / e0["heightmap"], mmap_mode="r").shape[0])
    d = T / (n - 1)
    ox, oy = e0["min"][0] - e0["i"] * T, e0["min"][1] - e0["j"] * T
    for name, lk in lakes.items():
        rings = lk.get("outline") or []
        if not rings:
            continue
        pts = np.array(rings[0])
        pad = max(3.0 * float(np.ptp(pts, axis=0).max()), 60.0)
        lo, hi = pts.min(0) - pad, pts.max(0) + pad
        i0, i1 = int(np.floor((lo[0] - ox) / T)), int(np.floor((hi[0] - ox) / T))
        j0, j1 = int(np.floor((lo[1] - oy) / T)), int(np.floor((hi[1] - oy) / T))
        ni, nj = i1 - i0 + 1, j1 - j0 + 1
        Hm = np.full((nj * (n - 1) + 1, ni * (n - 1) + 1), np.nan)  # rows south -> north
        for i in range(i0, i1 + 1):
            for j in range(j0, j1 + 1):
                if (i, j) in tiles:
                    h = np.load(out / tiles[i, j]["heightmap"])[::-1]  # (files are north row first)
                    Hm[(j - j0) * (n - 1):(j - j0) * (n - 1) + n, (i - i0) * (n - 1):(i - i0) * (n - 1) + n] = h
        x0, y0 = ox + i0 * T, oy + j0 * T
        rr, cc = _poly((pts[:, 1] - y0) / d, (pts[:, 0] - x0) / d, Hm.shape)
        inside = np.zeros(Hm.shape, bool)
        inside[rr, cc] = True
        if np.isnan(Hm[inside]).any() or not inside.any():
            summary[name] = {"skipped": "its tiles are not all in this export"}
            continue
        level = float(lk["level"])
        below = Hm < level
        lab, _ = ndimage.label(below)
        ids = np.unique(lab[inside & below])
        wet = np.isin(lab, ids[ids > 0])
        area = float(wet.sum()) * d * d
        # (water reaching tiles the export doesn't hold, or the window's edge: at least this much, and leaking)
        gap = ndimage.binary_dilation(np.isnan(Hm))
        leaks = bool((wet & gap).any() or wet[[0, -1], :].any() or wet[:, [0, -1]].any())
        want = float(lk["area_m2"])
        ratio = area / max(want, 1e-6)
        summary[name] = {"level": level, "designed_m2": round(want), "flooded_m2": round(area), "ratio": round(ratio, 2),
                         "leaks": leaks}
        if ratio > terrain_cliffs.LAKE_AREA or leaks:
            failures.append(f"lake {name}: flooded to its level {level:.2f} m on the tile heightmaps the water covers "
                            f"{area:,.0f} m2{' and runs on out of the area checked' if leaks else ''} where the lake is "
                            f"{want:,.0f} m2 (limit x{terrain_cliffs.LAKE_AREA}): the heightmaps don't hold it (its dam or bank is "
                            f"missing from them)")
        elif ratio < 1.0 / terrain_cliffs.LAKE_AREA:
            failures.append(f"lake {name}: the tile heightmaps hold only {area:,.0f} m2 of water under its level "
                            f"{level:.2f} m where the lake is {want:,.0f} m2: its bed stands too high in them")
    return {"summary": summary, "failures": failures}
