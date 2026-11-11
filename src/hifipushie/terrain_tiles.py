"""export_tiles: the terrain exported as tiles with LODs, maps and collision, and its summary. Part of the terrain
mesh (terrain_mesh.py has the overview)."""
from __future__ import annotations

import json
import os
import math
import time
from pathlib import Path

import numpy as np

from . import profiling
from .terrain_field import _lattice_values, project
from .terrain_materials import Materials
from .terrain_mesh import DEFAULTS, DENSITY_FILL, LAYERS, _CTX
from .terrain_relief import facet
from .terrain_seam_check import lake_outlines, seam_check
from .terrain_tile_border import WELD, _needs, _polylines, _simplify, _weld_rows
from .terrain_tile_finish import BAKE_PIECE, _job_bake, _job_finish, _planes, _thickness
from .terrain_tile_job import _job_tile
from .terrain_tile_jobs import (
    OVER_BUDGET, TilesCheckFailed, _fingerprint, _job_collapse, _job_dense_full, _job_ground, _job_maps, _job_mc,
    _job_prep_tile, _pool, _swatch, _work, budget_check, build_field,
)
from .terrain_tile_mesh import Grid, _key_geometry
from .terrain_volumes import FLOAT_PIECE, _sea

def export_tiles(T, out_dir, cfg: dict | None = None, log=print) -> dict:
    """See `_export_tiles`; holds the machine's heavy-job slot (`resources.heavy`) so exports don't stack up."""
    from . import resources
    # (PSS every 2 s: reading every worker's smaps_rollup each 0.5 s kept a parent thread ~40% busy)
    name = (cfg or {}).get("name") or Path(str(out_dir)).name
    with resources.heavy(f"terrain tiles {name}", log=log, kind="terrain_tiles", model=name,
                         gb=(cfg or {}).get("heavy_gb")), resources.peak_memory(every=2.0) as peak:
        return _export_tiles(T, out_dir, cfg, log, peak)


def _export_tiles(T, out_dir, cfg: dict | None = None, log=print, peak=None) -> dict:
    """Mesh the terrain's field (heightfield + volumes) into seamless tiles; write GLBs per tile per LOD, collision
    GLBs, heightmap and splat tiles, trees.csv and manifest.json; run the seam check (raises if it fails)."""
    from PIL import Image
    import copy
    t_all = time.time()
    cfg = {**DEFAULTS, **((T.spec.get("export") or {}).get("tiles") or {}), **(cfg or {})}
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    import shutil
    workdir = out / "_work"  # per-tile dense meshes, streamed through disk; removed at the end
    shutil.rmtree(workdir, ignore_errors=True)
    workdir.mkdir()
    _CTX.clear()
    _CTX["work"] = workdir
    timing = {}
    prof = profiling.Report(progress=log)  # per stage: wall, workers' busy share, stragglers; spans, field counts (manifest "profile")
    tile_key = lambda ij: f"{ij[0]},{ij[1]}"
    t0 = time.time()
    _st = prof.stage("setup (parent)")
    _st.__enter__()
    field, vols, notes, caves = build_field(T, cfg)
    base = field  # the whole rock (materials, trees, caves' walk, splats); `field` is what's meshed
    mats = Materials(T, base)
    G = Grid(T, cfg)
    if cfg.get("detail") and base.rock is not None:  # (the tiling detail's projection, read by the workers)
        from . import terrain_swatch
        _CTX["detail"] = terrain_swatch.DetailProjection(base, base.rock)
        de = _swatch(out, base.rock, cfg["texel_density"][0], cfg["detail_source"])  # (cached by seed + code)
        de.update(texcoord=1 + bool(int(cfg["splat"])), bins=_CTX["detail"].BINS, line_d=terrain_swatch.LINE_D,
                  layers=[nm for nm in ("rock", "wet_rock") if nm in mats.layers], recipe=terrain_swatch.RECIPE,
                  gltf=("each cliff tile LOD's baked material carries extras.hifipushie_detail: texture indices of "
                        "the embedded lines map and of the swatch images (files in materials/, by uri), and the UV "
                        "set; glTF viewers ignore it and show the macro maps"))
        _CTX["detail_entry"] = de
        # (the drawn lines go to the lines map, crisp, instead of blurring into the macro colour)
        mats.lines_in_maps = bool(cfg.get("lines", True))
    region = None
    if cfg["mode"] == "cliffs":
        from . import terrain_cliffs
        region = terrain_cliffs.Region(T, base, G, cfg)
        field = terrain_cliffs.CliffField(base, region)
    elif cfg["mode"] != "full":
        raise ValueError(f"export.tiles mode {cfg['mode']!r}: use cliffs or full")
    _st.__exit__(None, None, None)
    timing["setup"] = time.time() - t0
    tiles = [(i, j) for j in range(G.nj) for i in range(G.ni)]
    if cfg.get("only"):  # a block of tiles [[i0, j0], [i1, j1]] (inclusive), for trying things
        (i0, j0), (i1, j1) = cfg["only"]
        tiles = [(i, j) for (i, j) in tiles if i0 <= i <= i1 and j0 <= j <= j1]
    log(f"{len(tiles)} tiles ({G.ni} x {G.nj}) of {G.tile:g} m, voxel {G.voxel:g} m, LOD errors "
        f"{cfg['error'][:G.lods]} m, {len(vols)} volume pieces")

    # ---- 0. incremental: each tile's inputs keyed (terrain_incremental); the previous export's state if it applies
    from . import terrain_incremental as inc
    t0 = time.time()
    with prof.stage("incremental keys (parent)"):
        hrange = [float(np.nanmin(T.H)), float(np.nanmax(T.H))]
        fp = _fingerprint(T, cfg, base, field, mats, region, G, hrange)
        fkey = {ij: fp.tile(*G.bounds(*ij)) for ij in tiles}
        prev_state, why_cold = None, "incremental off (export.tiles incremental false or HIFIPUSHIE_TILES_COLD)"
        if fp.unknown:
            why_cold = f"inputs it can't fingerprint: {fp.unknown[:3]}"
            (out / inc.STATE).unlink(missing_ok=True)
        elif cfg.get("incremental", True) and not os.environ.get("HIFIPUSHIE_TILES_COLD"):
            prev_state, why_cold = inc.load(out, fp.parts["code"], fp.global_key, fp.parts)
        else:
            (out / inc.STATE).unlink(missing_ok=True)
    old = prev_state["tiles"] if prev_state else {}
    ns = {ij: {"field": fkey[ij][0], "parts": fkey[ij][1]} for ij in tiles}  # (the state this export leaves)
    redone = {}
    if prev_state is None:
        log(f"cold export: {why_cold}")
        for f in out.glob("*.glb"):
            f.unlink()
    timing["incremental keys"] = time.time() - t0

    # ---- 1. marching cubes per tile, and the canonical border vertices (decided once)
    t0 = time.time()
    v0 = G.voxel
    mc = {}
    reg = {}
    _CTX.update(field=field, G=G, vols=vols, base=base)
    redo = [ij for ij in tiles if not (ij in old and old[ij]["field"] == fkey[ij][0] and "mc" in old[ij])]
    if prev_state is not None:
        changed = [ij for ij in redo if ij in old]
        log(f"incremental: {len(redo)} of {len(tiles)} tiles' inputs changed" +
            "".join(f"; {ij[0]},{ij[1]}: {inc.why(old[ij]['parts'], fkey[ij][1])}" for ij in changed[:4]))
    redone["marching cubes"] = len(redo)
    if redo:
        with _pool() as ex:  # (in parallel: serial it was a third of the export)
            for ij, r in zip(redo, prof.pool_map(ex, _job_mc, redo, "marching cubes", tile_key)):
                mc[ij] = r
    mc = {ij: mc[ij] if ij in mc else old[ij]["mc"] for ij in tiles}  # (tile order: the chains' order follows it)
    for ij in tiles:
        ns[ij]["mc"] = mc[ij]
    for (i, j) in tiles:  # canonical border keys numbered in tile order (deterministic)
        if mc[i, j] is not None:
            for key in mc[i, j][1].values():
                reg.setdefault(key, len(reg))
    keys = sorted(reg, key=reg.get) or [(0, 0, 0, 0)]  # (a placeholder when no tile has a mesh)
    with prof.stage("border vertices (parent)"):
        a, b, fixed = _key_geometry(keys, G, 0)
        Fa, Fb = _lattice_values(field, a, v0), _lattice_values(field, b, v0)
        with np.errstate(divide="ignore", invalid="ignore"):  # (the placeholder key of a block with no borders: Fa == Fb)
            tt = np.where(Fa != Fb, Fa / np.where(Fa != Fb, Fa - Fb, 1.0), 0.0)
        CP, CN = project(field, a + tt[:, None] * (b - a), v0, fixed=fixed)
        CW, CC = mats.weights(CP, CN)
    pos = {tuple(p): r for r, p in enumerate(CP)}
    timing["marching cubes + border vertices"] = time.time() - t0

    # ---- 2. border chains per shared plane, simplified once per LOD (nested: each LOD keeps a subset of the last)
    t0 = time.time()
    plane_edges = {}
    for (i, j), r in mc.items():
        if r is None:
            continue
        rng, kk, bed = r
        for (p, q) in bed:
            if True:
                for plane in _planes(kk[p], kk[q], G, 0):
                    plane_edges.setdefault(plane, set()).add(tuple(sorted((reg[kk[p]], reg[kk[q]]))))
    _st = prof.stage("border chains (parent)")
    _st.__enter__()
    corner = fixed[:, 0] & fixed[:, 1]
    alias = _weld_rows(plane_edges, CP, corner, WELD * v0)
    if alias:  # (the chains run through each weld's kept row; every tile's dense mesh merges its vertices the same way)
        plane_edges = {pl: {tuple(sorted((alias.get(a, a), alias.get(b, b)))) for a, b in e
                            if alias.get(a, a) != alias.get(b, b)} for pl, e in plane_edges.items()}
        log(f"{len(alias)} border vertices welded to a neighbour closer than {WELD * v0:.2g} m")
    _CTX["alias"] = alias
    lines = {pl: _polylines(e) for pl, e in plane_edges.items()}
    keep = []
    prev = {pl: [(ln, closed) for ln, closed in L] for pl, L in lines.items()}
    for k in range(G.lods):
        ks = set(np.flatnonzero(corner).tolist())
        cur = {}
        for pl, L in prev.items():
            simp = []
            for ln, closed in L:
                kept = _simplify(CP, ln, closed, cfg["error"][k], ks)
                simp.append((kept, closed))
                ks.update(kept)
            cur[pl] = simp
        keep.append(ks)
        prev = cur
    _st.__exit__(None, None, None)
    timing["border chains"] = time.time() - t0

    # ---- 3. per tile: LOD0 projected; each LOD = border chains collapsed to its kept vertices, then decimated
    t0 = time.time()
    _CTX.update(field=field, G=G, v0=v0, mc=mc, reg=reg, CP=CP, CN=CN, cfg=cfg)
    work = [ij for ij, r in mc.items() if r is not None]
    # each tile's border rows as its dense mesh takes them (welds merged), and what its dense mesh depends on: its
    # field, its canonical border vertices, and their order (a weld keeps the lowest row)
    rows_of, dkey = {}, {}
    for ij in work:
        kk = mc[ij][1]
        orig = np.array([reg[kk[q]] for q in sorted(kk)], np.int64)
        rows = np.array([alias.get(int(r), int(r)) for r in orig], np.int64)
        rows_of[ij] = rows
        dkey[ij] = inc._h(fkey[ij][0], "dense", inc.rank(rows), rows != orig, CP[rows], CN[rows])
    redo = [ij for ij in work if not (ij in old and old[ij].get("dense", {}).get("key") == dkey[ij])]
    redone["dense LOD0"] = len(redo)
    areas = {}
    if redo:
        with _pool() as ex:
            res = prof.pool_map(ex, _job_dense_full, redo, "dense LOD0 (project, sharp)", tile_key)
        areas = {ij: r[1] for ij, r in zip(redo, res)}
        drops = {ij: r[2] for ij, r in zip(redo, res)}
    else:
        drops = {}
    for ij in work:
        ns[ij]["dense"] = {"key": dkey[ij], "area": areas[ij] if ij in areas else old[ij]["dense"]["area"],
                           "dropped": drops[ij] if ij in drops else old[ij]["dense"].get("dropped", [])}
    # (small cliff pieces standing clear of everything, dropped from the dense meshes: logged, not failed)
    dropped_pieces = [{"tile": list(ij), **d} for ij in sorted(work) for d in ns[ij]["dense"]["dropped"]]
    if dropped_pieces:
        log(f"dropped {len(dropped_pieces)} small cliff piece(s) standing clear of the ground (under "
            f"{float(cfg.get('float_piece_m2', FLOAT_PIECE)):g} m2 each; manifest dropped_pieces): "
            + ", ".join(f"{d['m2']:g} m2 at {d['at']} ({d['clearance_m']:g} m up)" for d in dropped_pieces[:6]))
    dense = set(work)
    _CTX["dense"] = dense
    timing["dense LOD0"] = time.time() - t0
    t0 = time.time()
    # one texel density per LOD for every tile: the asked one, or what the tile with the most rock can fit in
    # texture_max (each tile used to lower its own: on the alps' walls tiles came out 11-16 texels/m side by side,
    # sharp rock beside soft in squares of tiles)
    area = max([ns[ij]["dense"]["area"] for ij in work] + [1.0])
    tmax = int(cfg["texture_max"])
    cfg["_density"] = [min(float(d), math.sqrt(DENSITY_FILL * tmax * tmax / area)) for d in cfg["texel_density"]]
    if cfg["_density"][0] < cfg["texel_density"][0]:
        log(f"texel density {cfg['_density'][0]:.1f}/m at LOD 0 (asked {cfg['texel_density'][0]:g}): the largest "
            f"tile's rock ({area:.0f} m2) in a {tmax} atlas")
    # skirts go into the rock, in the border plane, against the surface normal; never out through the other side
    # (a skirt under a cave roof would hang into the cave)
    dirn = -CN.copy()
    dirn[fixed] = 0.0
    ln_ = np.linalg.norm(dirn, axis=1, keepdims=True)
    dirn = np.where(ln_ > 0.2, dirn / np.maximum(ln_, 1e-9), np.array([0, 0, -1.0]))
    with prof.stage("skirt thickness (parent)"):
        thick = _thickness(field, CP, dirn, np.full(len(CP), 3.0), v0)
    pbr = {"baseColorFactor": [1, 1, 1, 1], "metallicFactor": 0.0, "roughnessFactor": 0.92}
    mat = [{"name": "terrain_reference", "pbrMetallicRoughness": pbr},
           {"name": "terrain_skirt", "doubleSided": True, "pbrMetallicRoughness": pbr}]
    rounds = 0
    # border collapses: (tile, LOD) keyed by the tile's dense key and which of its border rows the LOD keeps; the
    # vertices it couldn't drop are stored as positions in the tile's rows (row numbers shift between exports)
    tile_state = {ij: old[ij]["tile"] for ij in tiles if "tile" in old.get(ij, {})}  # (each tile's LODs as on disk)
    rpos_of, tile_wanted = {}, {}
    col_known = {(ij, ck): pos_ for ij in work for ck, pos_ in old.get(ij, {}).get("col", {}).items()}
    col_used, col_file, col_all = {}, {}, set()  # (ij, k) -> the key this export's chains need; the file in _work's
    first = lambda rows: {int(r): p for p, r in reversed(list(enumerate(rows.tolist())))}
    redone["border collapses"] = 0
    while True:
        collapsed = {}
        for rnd in range(8):
            # where the rock is too thin for the skirt a gap needs, every LOD keeps that vertex (the gap closes)
            need = _needs(lines, keep, CP, G.lods)
            thin = set()
            for k in range(G.lods):
                d = np.maximum(need[k] * 1.25 + 0.05, cfg["skirt"])
                thin |= set(np.flatnonzero((need[k] > 1e-6) & (d > thick + 1e-6)).tolist())
            if thin:
                for kk in keep:
                    kk |= thin
                continue
            # a vertex a tile can't drop without folding is kept by both its tiles (at every LOD: chains nested)
            failed = set()
            todo = {}
            for k in range(G.lods):
                kr = np.array(sorted(keep[k]), np.int64)
                for ij in work:
                    ck = inc._h(dkey[ij], "col", k, np.isin(rows_of[ij], kr))
                    col_used[ij, k] = ck
                    col_all.add((ij, ck))  # (every round's: the next export walks the same rounds)
                    if (ij, ck) in col_known:
                        failed |= {int(rows_of[ij][p]) for p in col_known[ij, ck]}
                    else:
                        todo.setdefault(k, []).append((ij, kr, k))
            if todo:
                with _pool() as ex:
                    need_dense = sorted({a[0] for t in todo.values() for a in t if not _work(_CTX, "dense", *a[0]).exists()})
                    if need_dense:  # (tiles whose dense mesh the last export made: made again, one job a tile)
                        prof.pool_map(ex, _job_dense_full, need_dense, "dense LOD0 again (for collapses)", tile_key)
                    for k, jobs in sorted(todo.items()):
                        redone["border collapses"] += len(jobs)
                        for a, bad in zip(jobs, prof.pool_map(ex, _job_collapse, jobs, f"border collapse lod{k}",
                                                              lambda a: f"{a[0][0]},{a[0][1]}")):
                            failed |= bad
                            ij = a[0]
                            f_ = first(rows_of[ij])
                            col_known[ij, col_used[ij, k]] = tuple(sorted(f_[r] for r in bad))
                            col_file[ij, k] = col_used[ij, k]
            if not failed:
                break
            for kk in keep:
                kk |= failed
        else:
            raise RuntimeError("border chains didn't settle (vertices that can't be collapsed, or rock too "
                               "thin for a skirt)")
        for ij in work:
            ns[ij]["col"] = {ck: col_known[ij, ck] for (t, ck) in sorted(col_all) if t == ij}
        depth = [np.minimum(np.maximum(need[k] * 1.25 + 0.05, cfg["skirt"]), thick) for k in range(G.lods)]
        # (summed over the settle rounds: each round is collapses, then tiles; the labels used to take the last
        # round's span, from the previous round's tiles on, so the island's tiles read as 4,621 s of collapses)
        timing["border collapse + skirts"] = timing.get("border collapse + skirts", 0.0) + time.time() - t0

        t0 = time.time()
        manifest_tiles = []
        _CTX.update(mats=mats, cfg=cfg, out=out, vols=vols, collapsed=collapsed, pos=pos, depth=depth, dirn=dirn,
                    CN=CN, CW=CW, CC=CC, mat=mat, keep=[np.array(sorted(kk), np.int64) for kk in keep])
        if cfg.get("maps"):  # the field the maps are baked from: the rock with its bake-only fine relief
            import copy
            from . import terrain_bake
            bfs = []
            for k in range(G.lods):  # (per LOD: the fine relief band-limited to its texel)
                bf = copy.copy(base)
                if base.rock is not None and base.rock.get("joints"):  # (the far LODs' maps: big structure only)
                    rk = dict(base.rock)
                    rk["joints"] = {**rk["joints"], "depth": rk["joints"]["depth"] * [1.0, 0.5, 0.0][min(k, 2)]}
                    bf.rock = rk
                dens = cfg["_density"][min(k, len(cfg["_density"]) - 1)]
                if getattr(base, "edits", None) is not None:  # (the turf's step crisper in the maps than the mesh)
                    bf.edit_riser = max(base.edits.lip_cfg["maps"], 2.5 / dens)
                    bf.edit_wmin = 2.5 / dens
                if base.rock is not None and float(cfg["micro"]) > 0:
                    bf.micro = terrain_bake.micro_relief(base.rock, float(cfg["micro"]), 1.0 / dens,
                                                         fine="detail" not in _CTX)
                if region is not None:  # (a cliff's visible face: the rock, its ground sunk toward the region's edge)
                    bf = terrain_cliffs.CliffField(bf, region).front_field()
                bfs.append(bf)
            # (the normal over ~0.4 m that picks layer weights and colour: from the rock WITHOUT the per-LOD fine relief,
            # so every LOD picks the same layers at a border; with it, the LOD's own band-limited rock structure moved
            # weights p95 0.26 between LOD 0 and LOD 2)
            # (and from the rock UNSUNK: the cliff front's sink toward the region's edge, metres within a metre, tipped
            # the 0.4 m normal of texels on the true ground beside it to the horizontal, and their weights to rock:
            # a dark line on the grass along every overlay edge, pushieworld note 104)
            gf = base
            _CTX.update(bakefield=bfs, weightfield=gf,
                        layer_rough=np.array([LAYERS[nm]["roughness"] for nm in mats.layers]))
        # every tile's LODs (decimation, atlases), and as each tile is done its atlases' texels baked in pieces across
        # the pool, and each atlas's maps assembled and its GLB written once its pieces are in: a 3 x 3 block's
        # stragglers (one tile decimating for minutes) no longer hold the bake back
        stats, t_dec, wanted, got, left = [], 0.0, set(), {}, {}

        def on_done(fn, arg, r):
            nonlocal t_dec
            if fn is _job_tile:
                entry, st, td, wt = r
                manifest_tiles.append(entry)
                stats.extend(st)
                t_dec += td
                wanted.update(wt)
                tile_wanted[entry["i"], entry["j"]] = set(wt)
                jobs = []
                for q in entry.pop("_bakes", []):
                    # (at most BAKE_PIECE texels a piece, and a small atlas still spread over ~16 jobs: a preview's one
                    # tile. Never by the pool's size: that follows free memory, and where a piece starts changes a few
                    # texels' facet lookups (the walk chains from the last point): exports differed run to run)
                    step = int(np.clip(q["n"] / 16, BAKE_PIECE / 6, BAKE_PIECE))
                    cuts = list(range(0, q["n"], step))
                    left[q["stem"]] = len(cuts)
                    jobs += [(_job_bake, (q["stem"], q["k"], a, min(a + step, q["n"])), f"{q['stem']}@{a}")
                             for a in cuts]
                return jobs
            if fn is _job_bake:
                left[arg[0]] -= 1
                return [(_job_finish, arg[0], arg[0])] if not left[arg[0]] else []
            got[arg] = r
            return []
        # each tile's LODs keyed by its dense mesh and everything _job_tile reads of its border vertices (rows as `pos`
        # finds them): which each LOD keeps, normals, weights, colours, skirt depths and directions; and the density
        kp = _CTX["keep"]
        tkey = {}
        for ij in tiles:
            if ij in dense:
                rows = rows_of[ij]
                rp = np.array([pos[tuple(CP[r])] for r in rows.tolist()], np.int64)
                rpos_of[ij] = rp
                tp = {"dense": dkey[ij], "keep": inc._h(*[np.isin(rows, kp[k]) for k in range(G.lods)]),
                      "keep at pos": inc._h(*[np.isin(rp, kp[k]) for k in range(G.lods)]),
                      "skirt depth": inc._h(*[depth[k][rp] for k in range(G.lods)]), "skirt dir": inc._h(dirn[rp]),
                      "normals": inc._h(CN[rp]), "weights": inc._h(CW[rp], CC[rp]),
                      "density": inc._h(cfg["_density"], mat)}
                ns[ij]["tile parts"] = tp
                tkey[ij] = inc._h("tile", *sorted(tp.items()))
            else:
                tkey[ij] = inc._h(fkey[ij][0], "tile without a mesh")
        redo = [ij for ij in tiles if not (tile_state.get(ij) and tile_state[ij]["key"] == tkey[ij]
                                            and inc.files_ok(out, tile_state[ij]["files"]))]
        redone[f"tiles round {rounds}"] = len(redo)
        stale = [ij for ij in redo if ij in dense and any(col_file.get((ij, k)) != col_used[ij, k]
                                                          for k in range(G.lods))]
        if redo:
            with _pool() as ex:
                if stale:  # (their dense meshes and collapses came from the last export: made again here)
                    prof.pool_map(ex, _job_prep_tile, stale, "dense + collapses again (for tiles)", tile_key)
                    for ij in stale:
                        for k in range(G.lods):
                            col_file[ij, k] = col_used[ij, k]
                prof.run_jobs(ex, [(_job_tile, ij, tile_key(ij)) for ij in redo], on_done,
                              f"tiles (decimate, atlases; maps baked in pieces) round {rounds}")
        for ij in tiles:
            if ij not in redo:  # (unchanged: its entry, stats and files as the last export left them)
                c_ = tile_state[ij]
                manifest_tiles.append(copy.deepcopy(c_["entry"]))
                stats.extend(c_["stats"])
                wanted.update(int(rpos_of[ij][p]) for p in c_["wanted"])
        order = {ij: n for n, ij in enumerate(tiles)}
        manifest_tiles.sort(key=lambda e: order[e["i"], e["j"]])
        stats.sort(key=lambda st: (order[st[0], st[1]], st[2]))
        _maps_done(manifest_tiles, stats, got)
        for e in manifest_tiles:
            ij = (e["i"], e["j"])
            if ij in redo:
                f_ = first(rpos_of[ij]) if ij in rpos_of else {}
                tile_state[ij] = {"key": tkey[ij], "entry": copy.deepcopy(e), "stats": [st for st in stats if st[:2] == ij],
                           "wanted": tuple(sorted(f_[r] for r in tile_wanted.get(ij, ()))),
                           "files": inc.sizes(out, inc.entry_files(e))}
        # a vertex a coarse LOD couldn't lose without folding (the dense mesh folded at every count, and an
        # earlier LOD's mesh couldn't drop it either): every LOD keeps it and the tiles are written again
        timing["tiles (decimate, project, write)"] = timing.get("tiles (decimate, project, write)", 0.0) + \
            time.time() - t0
        t0 = time.time()
        if not wanted or rounds >= 2:
            break
        rounds += 1
        for kk in keep:
            kk |= wanted
        log(f"{len(wanted)} border vertices kept for coarse LODs that folded; tiles written again")
    shutil.rmtree(workdir, ignore_errors=True)
    for ij in tiles:
        ns[ij]["tile"] = tile_state[ij]
    timing["of which decimation"] = t_dec

    # ---- 4. heightmap and splat tiles on the same grid (in parallel)
    t0 = time.time()
    hrange = [float(np.nanmin(T.H)), float(np.nanmax(T.H))]
    hm, sp = int(cfg["heightmap"]), int(cfg["splat"])
    for sub in ("heightmaps", "splats"):
        (out / sub).mkdir(exist_ok=True)
    _CTX.update(hrange=hrange)
    ground = []
    if region is not None:
        # the ground: pushed heightmaps, holes, grid meshes; splats as before (on the heightmap's own tiles)
        pbr = {"baseColorFactor": [1, 1, 1, 1], "metallicFactor": 0.0, "roughnessFactor": 0.92}
        cfg["_hrange"] = hrange
        cfg["_layer_rough"] = np.array([LAYERS[nm]["roughness"] for nm in mats.layers])
        cfg["_ground_mat"] = [{"name": "terrain_reference", "pbrMetallicRoughness": pbr},
                              {"name": "terrain_skirt", "doubleSided": True, "pbrMetallicRoughness": pbr}]
        _CTX.update(region=region, mats=mats, cfg=cfg, out=out)
        gkey = {ij: inc._h(fkey[ij][0], "ground") for ij in tiles}
        og = {ij: old[ij]["ground"] for ij in tiles if "ground" in old.get(ij, {})}
        redo = [ij for ij in tiles if not (ij in og and og[ij]["key"] == gkey[ij] and inc.files_ok(out, og[ij]["files"]))]
        redone["ground tiles"] = len(redo)
        got_g = {}
        if redo:
            with _pool() as ex:
                got_g = dict(zip(redo, prof.pool_map(ex, _job_ground, redo, "ground tiles", tile_key)))
        ground = [got_g[ij] if ij in got_g else copy.deepcopy(og[ij]["entry"]) for ij in tiles]
        for ij, e in zip(tiles, ground):
            ns[ij]["ground"] = og[ij] if ij not in got_g else \
                {"key": gkey[ij], "entry": copy.deepcopy(e), "files": inc.sizes(out, inc.entry_files(e))}
        cfg.pop("_hrange"), cfg.pop("_ground_mat"), cfg.pop("_layer_rough")
        manifest_tiles = [e for e in manifest_tiles if any(e["lods"])]
        timing["ground tiles"] = time.time() - t0
        t0 = time.time()
    ents = ground or manifest_tiles
    mkey = {(e["i"], e["j"]): inc._h(fkey[e["i"], e["j"]][0], "maps", e["min"]) for e in ents}
    om = {ij: old[ij]["maps"] for ij in mkey if "maps" in old.get(ij, {})}
    redo = [e for e in ents if not ((e["i"], e["j"]) in om and om[e["i"], e["j"]]["key"] == mkey[e["i"], e["j"]]
                                    and inc.files_ok(out, om[e["i"], e["j"]]["files"]))]
    redone["heightmaps + splats"] = len(redo)
    got_m = {}
    if redo:
        with _pool() as ex:
            got_m = {(e["i"], e["j"]): x for e, x in zip(redo, prof.pool_map(
                ex, _job_maps, [(e["i"], e["j"], e["min"]) for e in redo], "heightmaps + splats",
                lambda a: f"{a[0]},{a[1]}"))}
    for e in ents:
        ij = (e["i"], e["j"])
        extra = got_m[ij] if ij in got_m else copy.deepcopy(om[ij]["extra"])
        ns[ij]["maps"] = om[ij] if ij not in got_m else \
            {"key": mkey[ij], "extra": copy.deepcopy(extra), "files": inc.sizes(out, inc.entry_files(extra))}
        e.update(extra)
    timing["heightmaps + splats"] = time.time() - t0

    clutter_sec = None
    # ---- 4b. ground clutter (bushes on the scrub, boulders on the shore): placements an engine's detail scatter can use
    if T.spec.get("ground_character", True) is not False and mats.ground is not None:
        from . import terrain_ground
        with prof.stage("clutter (parent)"):
            ks = ("bush", "boulder")
            cb = None
            if cfg.get("only"):  # (a block of tiles: only its ground)
                (i0, j0), (i1, j1) = cfg["only"]
                cb = [G.bounds(i0, j0)[0][:2].tolist(), G.bounds(i1, j1)[1][:2].tolist()]
            C = terrain_ground.clutter(T, mats, base, ks, box=cb)
            # (a stream's rocks, cobbles, driftwood, reeds, a lake's margin, a beach's pebbles and wrack:
            # terrain_stream.all_clutter)
            from . import terrain_stream
            SC = terrain_stream.all_clutter(T, mats, base, box=cb) if terrain_stream.config(T) is not None else None
            if SC is not None and not len(SC) and mats.streams is None:
                SC = None
            with open(out / "clutter.csv", "w") as f:
                # (csv_version 3: + water, sink (empty on dry ground), + a capsule's x0..z1, diameter (snags, limbs))
                f.write(terrain_stream.CSV_COLUMNS + "\n")
                for r in C:
                    f.write(f"{r[0]:.2f},{r[1]:.2f},{r[2]:.2f},{ks[int(r[3])]},{r[4]:.2f},{r[5]:.0f},{r[6]:.2f},,,"
                            f",,,,,,,\n")
                if SC is not None:
                    sk = list(terrain_stream.KINDS)
                    for r in SC:
                        cap = "" if np.isnan(r[11]) else ",".join(f"{v:.2f}" for v in r[11:17]) + f",{r[17]:.3f}"
                        f.write(f"{r[0]:.2f},{r[1]:.2f},{r[2]:.2f},{sk[int(r[3])]},{r[4]:.2f},{r[5]:.0f},{r[6]:.2f},"
                                f"{terrain_stream.PLACES[int(r[7])]},{r[9]:.2f},{r[10]:.2f},"
                                f"{cap if cap else ',,,,,,'}\n")
            notes.append(f"clutter.csv: {int((C[:, 3] == 0).sum())} bushes, {int((C[:, 3] == 1).sum())} boulders")
            clutter_sec = {"kinds": {"bush": {"scale_m": [0.6, 1.9], "squash": [0.45, 1.0], "z": "surface",
                                              "what": "a scrub / heath bush (squash < 1: wind-shorn by a cliff lip)"},
                                     "boulder": {"scale_m": [0.36, 1.96], "squash": [1.0, 1.0],
                                                 "z": "sunk 0.12 x scale", "what": "an angular rock (shore, rock "
                                                 "breaking through near cliff lips)"}},
                           "columns": terrain_stream.CSV_COLUMNS, "csv_version": terrain_stream.CSV_VERSION}
            if SC is not None:
                sm = terrain_stream.manifest(mats.streams, SC)
                clutter_sec = {**sm, "kinds": {**clutter_sec["kinds"], **sm["kinds"]}, "columns": clutter_sec["columns"],
                               "csv_version": clutter_sec["csv_version"]}
                if mats.streams is not None:
                    notes.extend(mats.streams.report())
                notes.extend(terrain_stream.summary(mats.streams, SC, cb))

    # ---- 5. trees and the manifest
    _st = prof.stage("trees + layer textures (parent)")
    _st.__enter__()
    from . import terrain_design as design
    inst = design.trees(T)
    with open(out / "trees.csv", "w") as f:
        f.write("x,y,z,kind,layer\n")
        layers = getattr(T, "tree_layers", {})
        zs = np.zeros(0) if not len(inst) else region.height(inst[:, 0], inst[:, 1]) if region is not None \
            else base.column(inst[:, 0], inst[:, 1])[0]
        # a tree stands only where the solid ground is under it: not over an arch's mouth or a notch the volumes cut
        # away (a cypress stood in the water at the arch), nor on a face the rock relief moved
        if len(inst):
            below = base.value(np.c_[inst[:, :2], zs - 0.3])
            ok = below < 0
            n_drop = int((~ok).sum())
            # nor in the splash zone (a cypress stood on the wave-cut platform at pebble's point), nor on a cliff face
            # (more than 45 deg: the trees' masks are cut on the heightfield, the solid rock is steeper)
            sea = _sea(T)
            wet = (zs < sea + 2.5) if sea is not None else np.zeros(len(zs), bool)
            _, gq = base.value_gradient(np.c_[inst[:, :2], zs], 0.25)
            steep = gq[:, 2] / np.maximum(np.linalg.norm(gq, axis=1), 1e-9) < 0.7
            n_wet, n_steep = int((ok & wet).sum()), int((ok & ~wet & steep).sum())
            ok &= ~wet & ~steep
            # nor perched on a cliff's lip: a tree's roots want soil, so none within its crown of the turf's edge
            # (terrain_ground.TREE_LIP m in from it; wind-shorn cypress may stand closer)
            n_lip = 0
            if getattr(base, "edits", None) is not None and len(inst):
                from . import terrain_ground
                Pq = np.c_[inst[:, :2], zs]
                bare_, d_, edge_, top_ = base.edits.bare(Pq)
                kinds_ = [layers.get(int(li), ("", ""))[1] for li in inst[:, 3]]
                need = np.array([terrain_ground.TREE_LIP.get(k_, terrain_ground.TREE_LIP["default"]) for k_ in kinds_])
                lip = (top_ > 0.3) & (d_ - edge_ < need)
                n_lip = int((ok & lip).sum())
                ok &= ~lip
            inst, zs = inst[ok], zs[ok]
            if n_drop:
                notes.append(f"{n_drop} trees dropped: no solid ground under them")
            if n_wet or n_steep or n_lip:
                notes.append(f"{n_wet} trees dropped in the splash zone (under 2.5 m over the sea), {n_steep} on "
                             f"faces steeper than 45 deg, {n_lip} on cliff lips (closer to the turf's edge than "
                             "terrain_ground.TREE_LIP)")
        for (x, y, _, li), z in zip(inst, zs):
            nm, kind = layers.get(int(li), ("", ""))
            f.write(f"{x:.2f},{y:.2f},{z:.2f},{kind},{nm}\n")
    groups = [mats.layers[g:g + 4] for g in range(0, len(mats.layers), 4)]
    layer_tex = {}
    if cfg.get("maps"):
        from . import terrain_bake
        layer_tex = terrain_bake.layer_textures(out, {nm: mats.layer_ref(nm) for nm in mats.layers})
    style_sec = None
    if T.spec.get("styles"):  # (per-style tileable layer textures + zone maps for the engine's shader: terrain_style)
        from . import terrain_style
        style_sec = terrain_style.write(out, T, {nm: mats.layer_ref(nm) for nm in mats.layers},
                                        tiles=[(i, j, tuple(float(x) for x in np.concatenate(G.bounds(i, j))))
                                               for j in range(G.nj) for i in range(G.ni)], layers=mats.layers)
    detail = _CTX.get("detail_entry")
    _st.__exit__(None, None, None)
    manifest = {
        "format": "hifipushie terrain tiles 1",
        "units": "m",
        "axes": {"world": "x east, y north, z up", "gltf": "glTF x = east, y = up, z = -north (node translation = "
                                                          "the tile's south-west corner; vertices local to it)"},
        "origin": G.origin.tolist(), "tile_size": G.tile, "grid": [G.ni, G.nj],
        "world_min": G.lo.tolist(), "world_max": G.hi.tolist(),
        "trimmed": "the extent was trimmed to whole coarsest voxels" if G.trimmed else "",
        "voxel": G.voxel,
        "lods": [{"lod": k, "error_m": cfg["error"][k], "budget_triangles": cfg["budget"][k],
                  "made": "LOD0's mesh with the border chains simplified (Douglas-Peucker at error_m, each LOD's chain "
                          "a subset of the one before) and decimated to error_m"} for k in range(G.lods)],
        "skirts": "primitive 1 of each tile (extras.role = skirt, double-sided material): each shared border's chain "
                  "extruded into the rock by how far the neighbours' LOD chains differ there (chains are nested "
                  "subsets, so that's at most their tolerances)",
        "collision": f"collision_<i>_<j>.glb: LOD {cfg['collision']} surface, no skirts, positions only (in cliffs "
                     "mode: the cliff shells, their buried backs included; load it WITH ground_collision_<i>_<j>.glb, "
                     "the heightmap's grid with the hole cells left out). A tile's collision is decimated further "
                     "when its LOD came out over collision_budget (tiles[].collision_triangles)",
        "sea_level": _sea(T),
        "lakes": lake_outlines(T),
        "materials": {
            "layers": [{"name": nm, **mats.layer_ref(nm), "weights": f"_WEIGHTS{g}", "channel": c,
                        **({"textures": layer_tex[nm]} if nm in layer_tex else {}),
                        "triplanar": nm in ("rock", "wet_rock")}
                       for g, grp in enumerate(groups) for c, nm in enumerate(grp)],
            "engine_recipe": "per pixel: weights w_i from the weights texture (cliff tiles: maps/<tile>_weights<g>.png "
                             "on TEXCOORD_0) or the splat (ground: TEXCOORD_1) or _WEIGHTS<g> per vertex. Rock on cliff "
                             "tiles: the tiling rock detail instead (manifest detail.recipe) when the export has "
                             "it. Each layer's "
                             "tiling textures (materials/<layer>_albedo/_normal/_height.png) at world position / "
                             "scale: planar (x, -y) on the ground, triplanar (blend by |n|^4 on the world axes) where "
                             "`triplanar` is true or the face is steeper than ~35 deg and in caves. Albedo = baked base "
                             "colour x (sum w_i albedo_i / colour_i) (the layers modulate the tile's macro colour); "
                             "normal = the baked normal with sum w_i detail normal_i blended on top (RNM or whiteout); "
                             "occlusion (ORM R) on indirect light only; roughness ORM G. Height blending (w_i x "
                             "height_i, sharpened) gives crisper layer edges than linear weights.",
            "blend": "layer weights per vertex (_WEIGHTS0, _WEIGHTS1 ... vec4, sum 1) and per tile splat PNGs "
                     "(RGBA = the same layers in the same groups of 4); layers are world-space/triplanar tiling "
                     "textures at `scale` metres",
            "reference": ("the baked material (terrain_baked: base colour, ORM = occlusion/roughness/metallic, "
                          "tangent-space normal, all from the exact field at TEXCOORD_0) shows each tile as authored "
                          "in any glTF viewer; skirts and buried faces use a plain matte material with COLOR_0")
                         if cfg.get("maps") else
                         "COLOR_0 is a display colour (linear) with a plain matte material, so tiles look right in "
                         "any glTF viewer",
            "splat_uv": f"splats cover the tile plus {cfg['splat_margin']} texels into the neighbours each side, "
                        f"row 0 north; texel centre (c, r) at x = min.x + (c - {cfg['splat_margin']} + 0.5) * "
                        f"tile / {sp}, y = max.y - (r - {cfg['splat_margin']} + 0.5) * tile / {sp}" if sp else "",
        },
        "heightmaps": {"samples": hm, "spacing": G.tile / max(hm - 1, 1), "format": "float32 .npy absolute metres, "
                       "north-up; .png 16-bit over the range", "range": hrange,
                       "note": "the 2.5D ground only (volumes aren't in heightmaps); edges shared with neighbours"}
        if hm else None,
        "trees": "trees.csv (x, y, z, kind, layer), world metres",
        "volumes": notes,
        "mode": cfg["mode"],
        "config": {k: v for k, v in cfg.items() if not k.startswith("_") and k not in ("only", "incremental")},
        "texel_density_used": [round(d, 3) for d in cfg.get("_density", [])],
        "maps": {
            "per tile LOD": "each tile's GLB embeds base colour (JPEG, sRGB), ORM (PNG: R occlusion, G roughness, "
                            "B metallic 0) and normal (PNG, tangent space, OpenGL/glTF: +Y up the texture, against "
                            "the TANGENT attribute) on TEXCOORD_0, its own atlas; lods[].maps gives the size, "
                            "texels/m, fill and how many texels fell back to the low poly",
            "beside": "maps/<tile>_height.png (16-bit, 0.5 = on the low poly, +-height_range_m along its normal: "
                      "for parallax/tessellation) and maps/<tile>_weights<g>.png (the layer weights, RGBA per "
                      "group of 4 in the manifest's layer order, on the same atlas)",
            "detail": "normals come from the exact rock plus bake-only fine relief (facets 0.45-1.2 m, cracks, the "
                      "bedding notch): detail below the meshing voxel lives in the maps, not in triangles",
            "seams": "gutters are baked from the surface past each chart's edge (across tile borders too), so "
                     "filtering and mips read the real neighbour; the seam check compares decoded normals along "
                     "shared borders",
        } if cfg.get("maps") else None,
        "tiles": manifest_tiles,
    }
    if detail is not None:
        manifest["detail"] = detail
    if style_sec is not None:
        manifest["styles"] = style_sec
    if clutter_sec is not None:
        manifest["clutter"] = clutter_sec
    if mats.streams is not None:  # (the rivers as the bed rules read them: for an engine's water, wet shading, audio)
        manifest["streams"] = {
            "rivers": {r["name"]: [[round(float(a), 2) for a in row] for row in
                                   np.c_[r["xy"], r["level"], r["width"], r["energy"]][r["live"]]]
                       for r in mats.streams.reaches},
            "columns": "x, y, water level (m), water width (m, across), energy 0..1 (0 slow and silty .. 1 a boulder "
                       "torrent)",
            "layers": {"gravel": "cobbles and gravel under the water and on bars", "silt": "fine sediment in pools and "
                       "slack margins", "bank": "the bank's damp foot above the water", "wet_rock": "bedrock in the "
                       "bed (steep reaches) and rock faces by the water"},
            "bed": "the heightmaps and cliff meshes carry the bed's shape (pools, riffles, bars); the water's level is "
                   "the rivers' own (never raised)"}
    if cfg.get("corridors"):  # (0.25 m heightmaps along the water for a nested water solve: pushieworld note 118)
        from . import terrain_corridors
        cbox = None
        if cfg.get("only"):
            (i0, j0), (i1, j1) = cfg["only"]
            cbox = [G.bounds(i0, j0)[0][:2], G.bounds(i1, j1)[1][:2]]
        with prof.stage("corridors (parent)"):
            cm = terrain_corridors.write(T, field, region, out, cfg, box=cbox, log=log, grid=G)
        if cm:
            manifest["corridors"] = cm
    if getattr(T, "falls", None):  # (waterfalls: for the engine's falling sheet and spray; terrain_falls)
        from . import terrain_falls
        from . import terrain_stream
        wr = terrain_stream.wet_design(T)["pools"] or [None] * len(T.falls)
        manifest["falls"] = {"falls": [{**f, "pool": {**f["pool"], "wet_radius": r}} if f.get("pool") and r is not None
                                       else f for f, r in zip(T.falls, wr)], "note": terrain_falls.META_NOTE}
    if cfg.get("maps") and cfg.get("grass_detail", True) and any(nm in mats.layers for nm in ("grass", "scrub",
                                                                                                "turf", "sand")):
        from . import terrain_ground  # (the turf's tiling detail: terrain_ground.grass_swatch, one per kind)
        ge = terrain_ground.write_grass(out, mats.layers)
        wl = lambda lay: [[f"_WEIGHTS{mats.layers.index(nm) // 4}", mats.layers.index(nm) % 4] for nm in lay
                          if nm in mats.layers]
        for sw in ge["swatches"]:
            sw["weights"] = wl(sw["layers"])
        ge["weights"] = wl(ge["layers"])
        manifest["ground_detail"] = ge
    if region is not None:
        manifest["cliffs"] = {
            "what": "the ground is the heightmap (ground tiles); `tiles` are 3D cliff meshes laid over it wherever the "
                    f"ground is steeper than {cfg['cliff_slope']:g} deg or a volume opens (cave mouths, arches, "
                    "notches, shafts). Each cliff mesh is a closed shell of rock that pinches out buried under the "
                    "heightmap at its edges: nothing to stitch.",
            "heightmap": f"pushed {region.push:.2f} m into the rock under the cliffs (eroded in plan), so the cliff "
                         "face covers it; holes only where a void opens through it (hole PNG per ground tile: 255 = "
                         "hole, one per heightmap cell, row 0 north)",
            "shell": {"sink_m": round(region.sink, 2), "thick_m": round(region.thick, 2),
                      "cave_wall_m": region.wall, "margin_m": cfg["cliff_margin"]},
            "hole_cells": int(region.holes.sum()),
        }
        manifest["ground"] = ground
        manifest["heightmaps"] = {"samples": int(cfg["heightmap"]), "spacing": region.d,
                                  "format": "float32 .npy absolute metres, C order, row 0 = the tile's north edge, "
                                            "column 0 = its west; .png 16-bit over the range",
                                  "holes": "heightmaps/holes_<i>_<j>.png only for tiles with holes (ground[].holes)",
                                  "range": hrange, "note": "pushed under the cliff meshes; edges shared with "
                                  "neighbours; ground_<i>_<j>_lod<k>.glb are the same samples as grid meshes (stride "
                                  "2^k, hole cells left out, vertical skirts on shared borders)"}
    if caves:  # a person walked through every passage
        t0 = time.time()
        from . import terrain_caves
        with prof.stage("cave walk (parent)"):
            manifest["cave_paths"] = []
            manifest["caves"] = terrain_caves.check(caves, base, sea=_sea(T), paths=manifest["cave_paths"])
            # the same walk's floor on what an engine collides with (the collision meshes): its steps can be taller
            # than the field's (decimation at the collision LOD's error, a pile of blocks simplified to a riser)
            try:
                for ln in terrain_caves.collision_steps(manifest["cave_paths"], out, manifest_tiles,
                                                        int(cfg["collision"])):
                    manifest["caves"].append(ln)
            except Exception as ex_:  # (a measure, never the export's failure)
                log(f"cave steps on the collision meshes not measured: {ex_}")
        timing["cave walk"] = time.time() - t0
    over = budget_check(manifest_tiles, cfg, G.lods, [cv.name for cv in caves] if caves else [])
    manifest["budget_check"] = {"limit": f"{OVER_BUDGET:g} x the LOD's budget", "over": over}
    manifest["dropped_pieces"] = {"limit_m2": float(cfg.get("float_piece_m2", FLOAT_PIECE)), "pieces": dropped_pieces}
    for o in over[:12]:
        log(f"OVER BUDGET: tile {o['tile'][0]},{o['tile'][1]} LOD {o['lod']}: {o['triangles']} triangles against "
            f"{o['budget']}: {o['why']}")
    (out / "manifest.json").write_text(json.dumps(manifest, indent=1))
    # files no tile names any more (a tile that lost its cliff, a LOD without maps now) go; then the state the next
    # export builds on
    keep_files = {f for e in manifest_tiles + ground for f in inc.entry_files(e)}
    for f in list(out.glob("*.glb")) + [p for d in inc.OUT_DIRS for p in (out / d).glob("*") if p.is_file()]:
        if str(f.relative_to(out)) not in keep_files:
            f.unlink()
    inc.save(out, {"format": inc.FORMAT, "code": fp.parts["code"], "global": fp.global_key, "global_parts": fp.parts,
                   "tiles": ns})
    timing["total before check"] = time.time() - t_all
    t0 = time.time()
    if cfg.get("checks", True):
        # (what the checks compute from each tile's files, kept by those files' bytes: an incremental export decodes
        # only the maps of the tiles it rewrote)
        memo = inc.Memo(out, "checks", fp.parts["code"])
        with prof.stage("check: seams (parent)"):
            check = seam_check(out, memo=memo) if manifest_tiles else {"summary": {"failures": 0}, "failures": []}
        if region is not None:
            from . import terrain_cliffs
            with prof.stage("check: ground (parent)"):
                gc = terrain_cliffs.ground_check(out, manifest, region, memo=memo,
                                                 tile_keys={ij: fkey[ij][0] for ij in tiles})
            check["summary"]["ground"] = gc["summary"]
            check["failures"] += gc["failures"]
            with prof.stage("check: lakes (parent)"):
                lc = terrain_cliffs.lake_check(out, manifest)
            check["summary"]["lakes"] = lc["summary"]
            check["failures"] += lc["failures"]
        # what the eye sees that the per-channel border comparison can't: squares locked to the terrain's grid in the
        # colour, and texel density jumping between neighbouring tiles (sharp rock beside soft)
        from . import terrain_seams
        with prof.stage("check: grid squares (parent)"):
            gs = terrain_seams.grid_squares(T, mats)
        if base.rock is not None:  # how regular the facets look (a lattice shows repeated diamonds from afar)
            from . import terrain_facets
            rk = base.rock
            with prof.stage("check: facet periodicity (parent)"):
                per = terrain_facets.periodicity(lambda P, fd: facet(P, 1.5 * rk["size"], rk["seed"], fd)
                                                 + 0.3 * facet(P, 0.6 * rk["size"], rk["seed"] + 5, fd))
            check["summary"]["facet_periodicity"] = per
            if max(per) > terrain_facets.PERIODIC:
                check["failures"].append(f"rock facets look regular (autocorrelation peaks {per}, limit "
                                         f"{terrain_facets.PERIODIC}): a quilt of repeated diamonds from afar")
        with prof.stage("check: texel density (parent)"):
            td = terrain_seams.texel_density(manifest) if cfg.get("maps") else {"summary": {}, "failures": []}
        check["summary"]["grid_squares"], check["summary"]["texel_density"] = gs, td["summary"]
        if not gs["ok"]:
            check["failures"].append(f"the colour bends on every terrain cell line (x{gs['ratio']} the kinks between "
                                     f"them): cell-sized squares on the rock")
        check["failures"] += td["failures"]
        if detail is not None:  # the swatch must tile: its wrap seam's jump against the steps beside it
            check["summary"]["swatch_wrap_seam"] = detail["wrap_seam"]
            if not detail["tileable"]:
                from . import terrain_swatch
                check["failures"].append(f"the detail swatch's wrap seam shows (jump excess {detail['wrap_seam']}, "
                                         f"limit {terrain_swatch.TILE_LIMIT})")
        for o in over:
            check["failures"].append(f"tile {o['tile'][0]},{o['tile'][1]} LOD {o['lod']}: {o['triangles']} triangles "
                                     f"against a budget of {o['budget']}: {o['why']}")
        check["summary"]["over_budget"] = len(over)
        check["summary"]["failures"] = len(check["failures"])
        check["summary"]["failed"] = check["failures"][:40]
        memo.save()
        redone["check samples"] = {"reused": memo.hits, "computed": memo.misses}
    else:  # (a preview: `preview_tiles`)
        check = {"summary": {"failures": 0, "skipped": "checks off (a preview)"}, "failures": []}
    timing["seam check"] = time.time() - t0
    manifest["seam_check"] = check["summary"]
    manifest["timing_s"] = {k: round(v, 2) for k, v in timing.items()}
    manifest["profile"] = prof.as_dict()
    # (in the profile: like the timings, it says how this export ran, not what it made)
    manifest["profile"]["incremental"] = {"previous export used": prev_state is not None,
                                          "why not": why_cold if prev_state is None else "", "tiles": len(tiles),
                                          "redone": redone}
    log(f"incremental: {json.dumps(manifest['profile']['incremental'])}")
    (out / "profile.txt").write_text(profiling.table(manifest["profile"]))
    log(profiling.table(manifest["profile"], top=25))
    if peak is not None:  # (what the job used, sampled every 0.5 s: PSS of the parent and its workers)
        manifest["memory_gb"] = {k: round(v, 2) for k, v in peak.items()}
    (out / "manifest.json").write_text(json.dumps(manifest, indent=1))
    result = {"out": str(out), "manifest": manifest, "stats": stats, "timing": timing, "check": check}
    if check["failures"]:
        # (everything is written and the manifest is complete: the caller can still report it, see `summary`)
        raise TilesCheckFailed(f"seam check FAILED (the tiles and manifest.json were written to {out}):\n"
                               + "\n".join(check["failures"][:30]), result)
    return result


def preview_tiles(T, out_dir, at, radius=40.0, density=6.0, cfg=None, log=print) -> dict:
    """A fast look at the rock round `at` (an address or [x, y]): only the tiles within `radius` m, one LOD, maps at
    `density` texels/m, ground maps at half their density, no checks. The same code path as the export (so what it
    shows is what an export bakes), sized for rock design rounds: a tile or four in about a minute instead of a block
    export's 15+. Render it with `render_tiles(T, out_dir, views)`."""
    base = {**DEFAULTS, **((T.spec.get("export") or {}).get("tiles") or {}), **(cfg or {})}
    G = Grid(T, base)
    xy = np.asarray(at, float)[:2] if isinstance(at, (list, tuple)) else np.asarray(T.address(at)[0], float)
    lo = np.floor((xy - radius - G.origin) / G.tile).astype(int).clip(0, [G.ni - 1, G.nj - 1])
    hi = np.floor((xy + radius - G.origin) / G.tile).astype(int).clip(0, [G.ni - 1, G.nj - 1])
    c = {"only": [lo.tolist(), hi.tolist()], "lods": 1, "texel_density": [float(density)], "checks": False,
         "ground_density": 0.5 * float(base["ground_density"])}
    return export_tiles(T, out_dir, {**c, **(cfg or {})}, log)


def summary(r) -> str:
    """A short text report of an export_tiles result."""
    M = r["manifest"]
    what = "cliff mesh tiles" if M.get("mode") == "cliffs" else "3D tiles"
    lines = []
    fails = (r.get("check") or {}).get("failures") or []
    if fails:
        lines += [f"CHECKS FAILED ({len(fails)}). The export is COMPLETE on disk (every tile and manifest.json, whose "
                  "seam_check.failed repeats this list) and loads in an engine. Each failure names its tiles. Open "
                  "edges or shards in a \"buried\" primitive are under the heightmap (not seen); in \"surface\" they "
                  "show (black slivers, holes). A tile over its budget is a valid mesh, only heavy."]
        lines += [f"  FAILED: {f}" for f in fails[:30]]
        if len(fails) > 30:
            lines.append(f"  ... and {len(fails) - 30} more")
    lines += [f"{what} in {r['out']}: {M['grid'][0]} x {M['grid'][1]} tiles of {M['tile_size']:g} m"
              + (f", {len(M['tiles'])} with cliffs" if M.get("mode") == "cliffs" else "")]
    for k, L in enumerate(M["lods"]):
        tris = [t["lods"][k]["triangles"] for t in M["tiles"] if t["lods"][k]]
        size = sum(t["lods"][k]["bytes"] for t in M["tiles"] if t["lods"][k])
        if tris:
            lines.append(f"LOD {k} (error {L['error_m']:g} m): {sum(tris)} triangles, per tile {min(tris)}-{max(tris)} "
                         f"(median {int(np.median(tris))}), {size / 1e6:.1f} MB")
    if M.get("ground"):
        for k in range(len(M["ground"][0]["lods"])):
            tris = [g["lods"][k]["triangles"] for g in M["ground"]]
            size = sum(g["lods"][k]["bytes"] for g in M["ground"])
            lines.append(f"ground LOD {k}: {sum(tris)} triangles ({min(tris)}-{max(tris)} a tile), {size / 1e6:.1f} MB")
        c = M["cliffs"]
        lines.append(f"heightmap pushed {c['heightmap'].split(' m ')[0].split()[-1]} m under the cliffs; "
                     f"{c['hole_cells']} hole cells")
    lines += [f"volume {n}" for n in M["volumes"]]
    lines += [f"walk: {n}" for n in M.get("caves", [])]
    sc = M["seam_check"]
    if "shared_edges" in sc:
        lines.append(f"seam check: {sc['failures']} failures; shared edges {sc['shared_edges']}, border normals within "
                     f"{sc['border_normal_max_deg']} deg, LOD gaps up to {sc['lod_pairs_max_gap_m']} m all under "
                     f"skirts")
    else:
        lines.append(f"seam check: {sc['failures']} failures")
    if "ground" in sc:
        lines.append("ground check: " + ", ".join(f"{k} {v}" for k, v in sc["ground"].items()))
    if "grid_squares" in sc:
        if "facet_periodicity" in sc:
            lines.append(f"facet periodicity (autocorrelation peak per plane orientation): {sc['facet_periodicity']}")
        lines.append(f"grid squares (colour kinks on cell lines vs between): x{sc['grid_squares']['ratio']}; texel "
                     "density " + ", ".join(f"{k} {v['min']:g}-{v['max']:g}/m (neighbours x{v['worst_neighbour_ratio']})"
                                            for k, v in sc.get("texel_density", {}).items()))
    sh = [f"LOD {k} {sc[f'lod{k}_shards']['area_pct']}%" for k in range(len(M["lods"])) if f"lod{k}_shards" in sc]
    if sh:
        lines.append("shards (corner normals against their face, share of the area): " + ", ".join(sh))
    inc_ = (M.get("profile") or {}).get("incremental")
    if inc_:  # (always said: cold and why, or what was redone)
        rd = inc_.get("redone") or {}
        lines.append(("incremental: reused the previous export; redone " + ", ".join(f"{k} {v}" for k, v in rd.items())
                      + f" of {inc_.get('tiles')} tiles") if inc_.get("previous export used") else
                     f"incremental: cold export ({inc_.get('why not') or 'no previous export'})")
    lines.append("timing (s): " + ", ".join(f"{k} {v}" for k, v in M["timing_s"].items()))
    if M.get("memory_gb"):
        m = M["memory_gb"]
        lines.append(f"memory peak: {m['job_gb']} GB for the job (largest worker {m['worker_gb']} GB, parent "
                     f"{m['parent_gb']} GB); the machine's free memory never below {m['min_available_gb']} GB")
    return "\n".join(lines)


def _maps_done(manifest_tiles, stats, got):
    """Each textured tile LOD's GLB size and maps report (from _job_finish) into its manifest entry and stats."""
    for e in manifest_tiles:
        for k, L in enumerate(e["lods"]):
            if L and L["bytes"] is None:
                L["bytes"], extra = got[f"tile_{e['i']}_{e['j']}_lod{k}"]
                L["maps"] = {**extra, **L.get("maps", {})}
    for n_, st in enumerate(stats):
        if st[6] is None:
            stats[n_] = st[:6] + (got[f"tile_{st[0]}_{st[1]}_lod{st[2]}"][0],)
