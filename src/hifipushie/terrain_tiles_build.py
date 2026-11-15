"""The tiles' meshes: marching cubes and the canonical border vertices, border chains per LOD, each tile's dense mesh,
the tile jobs (LODs, atlases, bakes).
Stages of the tile export (terrain_tiles._export_tiles calls them in order; terrain_mesh.py has the overview)."""
from __future__ import annotations

import math
import time

import numpy as np

from . import terrain_mesh
from .terrain_field import _lattice_values, project
from .terrain_tile_border import _needs, _polylines, _simplify, _weld_rows
from .terrain_tile_finish import _job_bake, _job_finish, _planes, _thickness
from .terrain_tile_job import _job_tile
from .terrain_tile_jobs import _job_collapse, _job_dense_full, _job_mc, _job_prep_tile, _pool, _work
from .terrain_tile_mesh import _key_geometry

def _cubes(tx):
    """Marching cubes per tile whose field changed; the canonical border vertices, decided once."""

    # ---- 1. marching cubes per tile, and the canonical border vertices (decided once)
    tx.t0 = time.time()
    tx.v0 = tx.G.voxel
    tx.mc = {}
    tx.reg = {}
    terrain_mesh._CTX.update(field=tx.field, G=tx.G, vols=tx.vols, base=tx.base)
    redo = [ij for ij in tx.tiles if not (ij in tx.old and tx.old[ij]["field"] == tx.fkey[ij][0] and "mc" in tx.old[ij])]
    if tx.prev_state is not None:
        changed = [ij for ij in redo if ij in tx.old]
        tx.log(f"incremental: {len(redo)} of {len(tx.tiles)} tiles' inputs changed" +
            "".join(f"; {ij[0]},{ij[1]}: {tx.inc.why(tx.old[ij]['parts'], tx.fkey[ij][1])}" for ij in changed[:4]))
    tx.redone["marching cubes"] = len(redo)
    if redo:
        with _pool() as ex:  # (in parallel: serial it was a third of the export)
            for ij, r in zip(redo, tx.prof.pool_map(ex, _job_mc, redo, "marching cubes", tx.tile_key)):
                tx.mc[ij] = r
    tx.mc = {ij: tx.mc[ij] if ij in tx.mc else tx.old[ij]["mc"] for ij in tx.tiles}  # (tile order: the chains' order follows it)
    for ij in tx.tiles:
        tx.ns[ij]["mc"] = tx.mc[ij]
    for (i, j) in tx.tiles:  # canonical border keys numbered in tile order (deterministic)
        if tx.mc[i, j] is not None:
            for key in tx.mc[i, j][1].values():
                tx.reg.setdefault(key, len(tx.reg))
    keys = sorted(tx.reg, key=tx.reg.get) or [(0, 0, 0, 0)]  # (a placeholder when no tile has a mesh)
    with tx.prof.stage("border vertices (parent)"):
        a, b, tx.fixed = _key_geometry(keys, tx.G, 0)
        Fa, Fb = _lattice_values(tx.field, a, tx.v0), _lattice_values(tx.field, b, tx.v0)
        with np.errstate(divide="ignore", invalid="ignore"):  # (the placeholder key of a block with no borders: Fa == Fb)
            tt = np.where(Fa != Fb, Fa / np.where(Fa != Fb, Fa - Fb, 1.0), 0.0)
        tx.CP, tx.CN = project(tx.field, a + tt[:, None] * (b - a), tx.v0, fixed=tx.fixed)
        tx.CW, tx.CC = tx.mats.weights(tx.CP, tx.CN)
    tx.pos = {tuple(p): r for r, p in enumerate(tx.CP)}
    tx.timing["marching cubes + border vertices"] = time.time() - tx.t0


def _border_chains(tx):
    """Border chains per shared plane, simplified once per LOD: each LOD keeps a subset of the last."""

    # ---- 2. border chains per shared plane, simplified once per LOD (nested: each LOD keeps a subset of the last)
    tx.t0 = time.time()
    plane_edges = {}
    for (i, j), r in tx.mc.items():
        if r is None:
            continue
        rng, kk, bed = r
        for (p, q) in bed:
            if True:
                for plane in _planes(kk[p], kk[q], tx.G, 0):
                    plane_edges.setdefault(plane, set()).add(tuple(sorted((tx.reg[kk[p]], tx.reg[kk[q]]))))
    _st = tx.prof.stage("border chains (parent)")
    _st.__enter__()
    corner = tx.fixed[:, 0] & tx.fixed[:, 1]
    tx.alias = _weld_rows(plane_edges, tx.CP, corner, terrain_mesh.WELD * tx.v0)
    if tx.alias:  # (the chains run through each weld's kept row; every tile's dense mesh merges its vertices the same way)
        plane_edges = {pl: {tuple(sorted((tx.alias.get(a, a), tx.alias.get(b, b)))) for a, b in e
                            if tx.alias.get(a, a) != tx.alias.get(b, b)} for pl, e in plane_edges.items()}
        tx.log(f"{len(tx.alias)} border vertices welded to a neighbour closer than {terrain_mesh.WELD * tx.v0:.2g} m")
    terrain_mesh._CTX["alias"] = tx.alias
    tx.lines = {pl: _polylines(e) for pl, e in plane_edges.items()}
    tx.keep = []
    prev = {pl: [(ln, closed) for ln, closed in L] for pl, L in tx.lines.items()}
    for k in range(tx.G.lods):
        ks = set(np.flatnonzero(corner).tolist())
        cur = {}
        for pl, L in prev.items():
            simp = []
            for ln, closed in L:
                kept = _simplify(tx.CP, ln, closed, tx.cfg["error"][k], ks)
                simp.append((kept, closed))
                ks.update(kept)
            cur[pl] = simp
        tx.keep.append(ks)
        prev = cur
    _st.__exit__(None, None, None)
    tx.timing["border chains"] = time.time() - tx.t0


def _dense_meshes(tx):
    """Each tile's dense mesh (LOD0, projected), one texel density per LOD, the skirts; what the LOD jobs start from."""

    # ---- 3. per tile: LOD0 projected; each LOD = border chains collapsed to its kept vertices, then decimated
    tx.t0 = time.time()
    terrain_mesh._CTX.update(field=tx.field, G=tx.G, v0=tx.v0, mc=tx.mc, reg=tx.reg, CP=tx.CP, CN=tx.CN, cfg=tx.cfg)
    tx.work = [ij for ij, r in tx.mc.items() if r is not None]
    # each tile's border rows as its dense mesh takes them (welds merged), and what its dense mesh depends on: its
    # field, its canonical border vertices, and their order (a weld keeps the lowest row)
    tx.rows_of, tx.dkey = {}, {}
    for ij in tx.work:
        kk = tx.mc[ij][1]
        orig = np.array([tx.reg[kk[q]] for q in sorted(kk)], np.int64)
        rows = np.array([tx.alias.get(int(r), int(r)) for r in orig], np.int64)
        tx.rows_of[ij] = rows
        tx.dkey[ij] = tx.inc._h(tx.fkey[ij][0], "dense", tx.inc.rank(rows), rows != orig, tx.CP[rows], tx.CN[rows])
    redo = [ij for ij in tx.work if not (ij in tx.old and tx.old[ij].get("dense", {}).get("key") == tx.dkey[ij])]
    tx.redone["dense LOD0"] = len(redo)
    areas = {}
    if redo:
        with _pool() as ex:
            res = tx.prof.pool_map(ex, _job_dense_full, redo, "dense LOD0 (project, sharp)", tx.tile_key)
        areas = {ij: r[1] for ij, r in zip(redo, res)}
        drops = {ij: r[2] for ij, r in zip(redo, res)}
    else:
        drops = {}
    for ij in tx.work:
        tx.ns[ij]["dense"] = {"key": tx.dkey[ij], "area": areas[ij] if ij in areas else tx.old[ij]["dense"]["area"],
                           "dropped": drops[ij] if ij in drops else tx.old[ij]["dense"].get("dropped", [])}
    # (small cliff pieces standing clear of everything, dropped from the dense meshes: logged, not failed)
    tx.dropped_pieces = [{"tile": list(ij), **d} for ij in sorted(tx.work) for d in tx.ns[ij]["dense"]["dropped"]]
    if tx.dropped_pieces:
        tx.log(f"dropped {len(tx.dropped_pieces)} small cliff piece(s) standing clear of the ground (under "
            f"{float(tx.cfg.get('float_piece_m2', terrain_mesh.FLOAT_PIECE)):g} m2 each; manifest dropped_pieces): "
            + ", ".join(f"{d['m2']:g} m2 at {d['at']} ({d['clearance_m']:g} m up)" for d in tx.dropped_pieces[:6]))
    tx.dense = set(tx.work)
    terrain_mesh._CTX["dense"] = tx.dense
    tx.timing["dense LOD0"] = time.time() - tx.t0
    tx.t0 = time.time()
    # one texel density per LOD for every tile: the asked one, or what the tile with the most rock can fit in
    # texture_max (each tile used to lower its own: on the alps' walls tiles came out 11-16 texels/m side by side,
    # sharp rock beside soft in squares of tiles)
    area = max([tx.ns[ij]["dense"]["area"] for ij in tx.work] + [1.0])
    tmax = int(tx.cfg["texture_max"])
    tx.cfg["_density"] = [min(float(d), math.sqrt(terrain_mesh.DENSITY_FILL * tmax * tmax / area)) for d in tx.cfg["texel_density"]]
    if tx.cfg["_density"][0] < tx.cfg["texel_density"][0]:
        tx.log(f"texel density {tx.cfg['_density'][0]:.1f}/m at LOD 0 (asked {tx.cfg['texel_density'][0]:g}): the largest "
            f"tile's rock ({area:.0f} m2) in a {tmax} atlas")
    # skirts go into the rock, in the border plane, against the surface normal; never out through the other side
    # (a skirt under a cave roof would hang into the cave)
    tx.dirn = -tx.CN.copy()
    tx.dirn[tx.fixed] = 0.0
    ln_ = np.linalg.norm(tx.dirn, axis=1, keepdims=True)
    tx.dirn = np.where(ln_ > 0.2, tx.dirn / np.maximum(ln_, 1e-9), np.array([0, 0, -1.0]))
    with tx.prof.stage("skirt thickness (parent)"):
        tx.thick = _thickness(tx.field, tx.CP, tx.dirn, np.full(len(tx.CP), 3.0), tx.v0)
    pbr = {"baseColorFactor": [1, 1, 1, 1], "metallicFactor": 0.0, "roughnessFactor": 0.92}
    tx.mat = [{"name": "terrain_reference", "pbrMetallicRoughness": pbr},
           {"name": "terrain_skirt", "doubleSided": True, "pbrMetallicRoughness": pbr}]
    tx.rounds = 0
    # border collapses: (tile, LOD) keyed by the tile's dense key and which of its border rows the LOD keeps; the
    # vertices it couldn't drop are stored as positions in the tile's rows (row numbers shift between exports)
    tx.tile_state = {ij: tx.old[ij]["tile"] for ij in tx.tiles if "tile" in tx.old.get(ij, {})}  # (each tile's LODs as on disk)
    tx.rpos_of, tx.tile_wanted = {}, {}
    tx.col_known = {(ij, ck): pos_ for ij in tx.work for ck, pos_ in tx.old.get(ij, {}).get("col", {}).items()}
    tx.col_used, tx.col_file, tx.col_all = {}, {}, set()  # (ij, k) -> the key this export's chains need; the file in _work's
    tx.first = lambda rows: {int(r): p for p, r in reversed(list(enumerate(rows.tolist())))}
    tx.redone["border collapses"] = 0


def _tile_lods(tx):
    """The tile jobs, in at most three rounds: borders collapsed, LODs decimated, atlases baked in pieces and written."""
    while True:
        collapsed = {}
        for rnd in range(8):
            # where the rock is too thin for the skirt a gap needs, every LOD keeps that vertex (the gap closes)
            tx.need = _needs(tx.lines, tx.keep, tx.CP, tx.G.lods)
            thin = set()
            for k in range(tx.G.lods):
                d = np.maximum(tx.need[k] * 1.25 + 0.05, tx.cfg["skirt"])
                thin |= set(np.flatnonzero((tx.need[k] > 1e-6) & (d > tx.thick + 1e-6)).tolist())
            if thin:
                for kk in tx.keep:
                    kk |= thin
                continue
            # a vertex a tile can't drop without folding is kept by both its tiles (at every LOD: chains nested)
            failed = set()
            todo = {}
            for k in range(tx.G.lods):
                kr = np.array(sorted(tx.keep[k]), np.int64)
                for ij in tx.work:
                    ck = tx.inc._h(tx.dkey[ij], "col", k, np.isin(tx.rows_of[ij], kr))
                    tx.col_used[ij, k] = ck
                    tx.col_all.add((ij, ck))  # (every round's: the next export walks the same rounds)
                    if (ij, ck) in tx.col_known:
                        failed |= {int(tx.rows_of[ij][p]) for p in tx.col_known[ij, ck]}
                    else:
                        todo.setdefault(k, []).append((ij, kr, k))
            if todo:
                with _pool() as ex:
                    need_dense = sorted({a[0] for t in todo.values() for a in t if not _work(terrain_mesh._CTX, "dense", *a[0]).exists()})
                    if need_dense:  # (tiles whose dense mesh the last export made: made again, one job a tile)
                        tx.prof.pool_map(ex, _job_dense_full, need_dense, "dense LOD0 again (for collapses)", tx.tile_key)
                    for k, jobs in sorted(todo.items()):
                        tx.redone["border collapses"] += len(jobs)
                        for a, bad in zip(jobs, tx.prof.pool_map(ex, _job_collapse, jobs, f"border collapse lod{k}",
                                                              lambda a: f"{a[0][0]},{a[0][1]}")):
                            failed |= bad
                            ij = a[0]
                            f_ = tx.first(tx.rows_of[ij])
                            tx.col_known[ij, tx.col_used[ij, k]] = tuple(sorted(f_[r] for r in bad))
                            tx.col_file[ij, k] = tx.col_used[ij, k]
            if not failed:
                break
            for kk in tx.keep:
                kk |= failed
        else:
            raise RuntimeError("border chains didn't settle (vertices that can't be collapsed, or rock too "
                               "thin for a skirt)")
        for ij in tx.work:
            tx.ns[ij]["col"] = {ck: tx.col_known[ij, ck] for (t, ck) in sorted(tx.col_all) if t == ij}
        depth = [np.minimum(np.maximum(tx.need[k] * 1.25 + 0.05, tx.cfg["skirt"]), tx.thick) for k in range(tx.G.lods)]
        # (summed over the settle rounds: each round is collapses, then tiles; the labels used to take the last
        # round's span, from the previous round's tiles on, so the island's tiles read as 4,621 s of collapses)
        tx.timing["border collapse + skirts"] = tx.timing.get("border collapse + skirts", 0.0) + time.time() - tx.t0

        tx.t0 = time.time()
        tx.manifest_tiles = []
        terrain_mesh._CTX.update(mats=tx.mats, cfg=tx.cfg, out=tx.out, vols=tx.vols, collapsed=collapsed, pos=tx.pos, depth=depth, dirn=tx.dirn,
                    CN=tx.CN, CW=tx.CW, CC=tx.CC, mat=tx.mat, keep=[np.array(sorted(kk), np.int64) for kk in tx.keep])
        if tx.cfg.get("maps"):  # the field the maps are baked from: the rock with its bake-only fine relief
            import copy
            tx.copy = copy
            from . import terrain_bake_layers, terrain_bake_maps
            bfs = []
            for k in range(tx.G.lods):  # (per LOD: the fine relief band-limited to its texel)
                bf = tx.copy.copy(tx.base)
                if tx.base.rock is not None and tx.base.rock.get("joints"):  # (the far LODs' maps: big structure only)
                    rk = dict(tx.base.rock)
                    rk["joints"] = {**rk["joints"], "depth": rk["joints"]["depth"] * [1.0, 0.5, 0.0][min(k, 2)]}
                    bf.rock = rk
                dens = tx.cfg["_density"][min(k, len(tx.cfg["_density"]) - 1)]
                if getattr(tx.base, "edits", None) is not None:  # (the turf's step crisper in the maps than the mesh)
                    bf.edit_riser = max(tx.base.edits.lip_cfg["maps"], 2.5 / dens)
                    bf.edit_wmin = 2.5 / dens
                if tx.base.rock is not None and float(tx.cfg["micro"]) > 0:
                    bf.micro = terrain_bake_maps.micro_relief(tx.base.rock, float(tx.cfg["micro"]), 1.0 / dens,
                                                         fine="detail" not in terrain_mesh._CTX)
                if tx.region is not None:  # (a cliff's visible face: the rock, its ground sunk toward the region's edge)
                    bf = tx.terrain_cliffs.CliffField(bf, tx.region).front_field()
                bfs.append(bf)
            # (the normal over ~0.4 m that picks layer weights and colour: from the rock WITHOUT the per-LOD fine relief,
            # so every LOD picks the same layers at a border; with it, the LOD's own band-limited rock structure moved
            # weights p95 0.26 between LOD 0 and LOD 2)
            # (and from the rock UNSUNK: the cliff front's sink toward the region's edge, metres within a metre, tipped
            # the 0.4 m normal of texels on the true ground beside it to the horizontal, and their weights to rock:
            # a dark line on the grass along every overlay edge, pushieworld note 104)
            gf = tx.base
            terrain_mesh._CTX.update(bakefield=bfs, weightfield=gf,
                        layer_rough=np.array([terrain_mesh.LAYERS[nm]["roughness"] for nm in tx.mats.layers]))
        # every tile's LODs (decimation, atlases), and as each tile is done its atlases' texels baked in pieces across
        # the pool, and each atlas's maps assembled and its GLB written once its pieces are in: a 3 x 3 block's
        # stragglers (one tile decimating for minutes) no longer hold the bake back
        tx.stats, tx.t_dec, wanted, got, left = [], 0.0, set(), {}, {}

        def on_done(fn, arg, r):
            if fn is _job_tile:
                entry, st, td, wt = r
                tx.manifest_tiles.append(entry)
                tx.stats.extend(st)
                tx.t_dec += td
                wanted.update(wt)
                tx.tile_wanted[entry["i"], entry["j"]] = set(wt)
                jobs = []
                for q in entry.pop("_bakes", []):
                    # (at most BAKE_PIECE texels a piece, and a small atlas still spread over ~16 jobs: a preview's one
                    # tile. Never by the pool's size: that follows free memory, and where a piece starts changes a few
                    # texels' facet lookups (the walk chains from the last point): exports differed run to run)
                    step = int(np.clip(q["n"] / 16, terrain_mesh.BAKE_PIECE / 6, terrain_mesh.BAKE_PIECE))
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
        kp = terrain_mesh._CTX["keep"]
        tkey = {}
        for ij in tx.tiles:
            if ij in tx.dense:
                rows = tx.rows_of[ij]
                rp = np.array([tx.pos[tuple(tx.CP[r])] for r in rows.tolist()], np.int64)
                tx.rpos_of[ij] = rp
                tp = {"dense": tx.dkey[ij], "keep": tx.inc._h(*[np.isin(rows, kp[k]) for k in range(tx.G.lods)]),
                      "keep at pos": tx.inc._h(*[np.isin(rp, kp[k]) for k in range(tx.G.lods)]),
                      "skirt depth": tx.inc._h(*[depth[k][rp] for k in range(tx.G.lods)]), "skirt dir": tx.inc._h(tx.dirn[rp]),
                      "normals": tx.inc._h(tx.CN[rp]), "weights": tx.inc._h(tx.CW[rp], tx.CC[rp]),
                      "density": tx.inc._h(tx.cfg["_density"], tx.mat)}
                tx.ns[ij]["tile parts"] = tp
                tkey[ij] = tx.inc._h("tile", *sorted(tp.items()))
            else:
                tkey[ij] = tx.inc._h(tx.fkey[ij][0], "tile without a mesh")
        redo = [ij for ij in tx.tiles if not (tx.tile_state.get(ij) and tx.tile_state[ij]["key"] == tkey[ij]
                                            and tx.inc.files_ok(tx.out, tx.tile_state[ij]["files"]))]
        tx.redone[f"tiles round {tx.rounds}"] = len(redo)
        stale = [ij for ij in redo if ij in tx.dense and any(tx.col_file.get((ij, k)) != tx.col_used[ij, k]
                                                          for k in range(tx.G.lods))]
        if redo:
            with _pool() as ex:
                if stale:  # (their dense meshes and collapses came from the last export: made again here)
                    tx.prof.pool_map(ex, _job_prep_tile, stale, "dense + collapses again (for tiles)", tx.tile_key)
                    for ij in stale:
                        for k in range(tx.G.lods):
                            tx.col_file[ij, k] = tx.col_used[ij, k]
                tx.prof.run_jobs(ex, [(_job_tile, ij, tx.tile_key(ij)) for ij in redo], on_done,
                              f"tiles (decimate, atlases; maps baked in pieces) round {tx.rounds}")
        for ij in tx.tiles:
            if ij not in redo:  # (unchanged: its entry, stats and files as the last export left them)
                c_ = tx.tile_state[ij]
                tx.manifest_tiles.append(tx.copy.deepcopy(c_["entry"]))
                tx.stats.extend(c_["stats"])
                wanted.update(int(tx.rpos_of[ij][p]) for p in c_["wanted"])
        order = {ij: n for n, ij in enumerate(tx.tiles)}
        tx.manifest_tiles.sort(key=lambda e: order[e["i"], e["j"]])
        tx.stats.sort(key=lambda st: (order[st[0], st[1]], st[2]))
        _maps_done(tx.manifest_tiles, tx.stats, got)
        for e in tx.manifest_tiles:
            ij = (e["i"], e["j"])
            if ij in redo:
                f_ = tx.first(tx.rpos_of[ij]) if ij in tx.rpos_of else {}
                tx.tile_state[ij] = {"key": tkey[ij], "entry": tx.copy.deepcopy(e), "stats": [st for st in tx.stats if st[:2] == ij],
                           "wanted": tuple(sorted(f_[r] for r in tx.tile_wanted.get(ij, ()))),
                           "files": tx.inc.sizes(tx.out, tx.inc.entry_files(e))}
        # a vertex a coarse LOD couldn't lose without folding (the dense mesh folded at every count, and an
        # earlier LOD's mesh couldn't drop it either): every LOD keeps it and the tiles are written again
        tx.timing["tiles (decimate, project, write)"] = tx.timing.get("tiles (decimate, project, write)", 0.0) + \
            time.time() - tx.t0
        tx.t0 = time.time()
        if not wanted or tx.rounds >= 2:
            break
        tx.rounds += 1
        for kk in tx.keep:
            kk |= wanted
        tx.log(f"{len(wanted)} border vertices kept for coarse LODs that folded; tiles written again")
    tx.shutil.rmtree(tx.workdir, ignore_errors=True)
    for ij in tx.tiles:
        tx.ns[ij]["tile"] = tx.tile_state[ij]
    tx.timing["of which decimation"] = tx.t_dec


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
