"""What lies on the tiles: heightmap and splat tiles, ground clutter, trees.csv and the layer textures.
Stages of the tile export (terrain_tiles._export_tiles calls them in order; terrain_mesh.py has the overview)."""
from __future__ import annotations

import time

import numpy as np

from . import terrain_mesh
from .terrain_tile_jobs import _job_ground, _job_maps, _pool
from .terrain_volumes import _sea

def _ground_maps(tx):
    """Heightmap and splat tiles on the same grid, in parallel."""

    # ---- 4. heightmap and splat tiles on the same grid (in parallel)
    tx.t0 = time.time()
    tx.hrange = [float(np.nanmin(tx.T.H)), float(np.nanmax(tx.T.H))]
    tx.hm, tx.sp = int(tx.cfg["heightmap"]), int(tx.cfg["splat"])
    for sub in ("heightmaps", "splats"):
        (tx.out / sub).mkdir(exist_ok=True)
    terrain_mesh._CTX.update(hrange=tx.hrange)
    tx.ground = []
    if tx.region is not None:
        # the ground: pushed heightmaps, holes, grid meshes; splats as before (on the heightmap's own tiles)
        pbr = {"baseColorFactor": [1, 1, 1, 1], "metallicFactor": 0.0, "roughnessFactor": 0.92}
        tx.cfg["_hrange"] = tx.hrange
        tx.cfg["_layer_rough"] = np.array([terrain_mesh.LAYERS[nm]["roughness"] for nm in tx.mats.layers])
        tx.cfg["_ground_mat"] = [{"name": "terrain_reference", "pbrMetallicRoughness": pbr},
                              {"name": "terrain_skirt", "doubleSided": True, "pbrMetallicRoughness": pbr}]
        terrain_mesh._CTX.update(region=tx.region, mats=tx.mats, cfg=tx.cfg, out=tx.out)
        gkey = {ij: tx.inc._h(tx.fkey[ij][0], "ground") for ij in tx.tiles}
        og = {ij: tx.old[ij]["ground"] for ij in tx.tiles if "ground" in tx.old.get(ij, {})}
        redo = [ij for ij in tx.tiles if not (ij in og and og[ij]["key"] == gkey[ij] and tx.inc.files_ok(tx.out, og[ij]["files"]))]
        tx.redone["ground tiles"] = len(redo)
        got_g = {}
        if redo:
            with _pool() as ex:
                got_g = dict(zip(redo, tx.prof.pool_map(ex, _job_ground, redo, "ground tiles", tx.tile_key)))
        tx.ground = [got_g[ij] if ij in got_g else tx.copy.deepcopy(og[ij]["entry"]) for ij in tx.tiles]
        for ij, e in zip(tx.tiles, tx.ground):
            tx.ns[ij]["ground"] = og[ij] if ij not in got_g else \
                {"key": gkey[ij], "entry": tx.copy.deepcopy(e), "files": tx.inc.sizes(tx.out, tx.inc.entry_files(e))}
        tx.cfg.pop("_hrange"), tx.cfg.pop("_ground_mat"), tx.cfg.pop("_layer_rough")
        tx.manifest_tiles = [e for e in tx.manifest_tiles if any(e["lods"])]
        tx.timing["ground tiles"] = time.time() - tx.t0
        tx.t0 = time.time()
    ents = tx.ground or tx.manifest_tiles
    mkey = {(e["i"], e["j"]): tx.inc._h(tx.fkey[e["i"], e["j"]][0], "maps", e["min"]) for e in ents}
    om = {ij: tx.old[ij]["maps"] for ij in mkey if "maps" in tx.old.get(ij, {})}
    redo = [e for e in ents if not ((e["i"], e["j"]) in om and om[e["i"], e["j"]]["key"] == mkey[e["i"], e["j"]]
                                    and tx.inc.files_ok(tx.out, om[e["i"], e["j"]]["files"]))]
    tx.redone["heightmaps + splats"] = len(redo)
    got_m = {}
    if redo:
        with _pool() as ex:
            got_m = {(e["i"], e["j"]): x for e, x in zip(redo, tx.prof.pool_map(
                ex, _job_maps, [(e["i"], e["j"], e["min"]) for e in redo], "heightmaps + splats",
                lambda a: f"{a[0]},{a[1]}"))}
    for e in ents:
        ij = (e["i"], e["j"])
        extra = got_m[ij] if ij in got_m else tx.copy.deepcopy(om[ij]["extra"])
        tx.ns[ij]["maps"] = om[ij] if ij not in got_m else \
            {"key": mkey[ij], "extra": tx.copy.deepcopy(extra), "files": tx.inc.sizes(tx.out, tx.inc.entry_files(extra))}
        e.update(extra)
    tx.timing["heightmaps + splats"] = time.time() - tx.t0


def _clutter(tx):
    """Ground clutter (bushes on the scrub, boulders on the shore) as placements for an engine's detail scatter."""

    tx.clutter_sec = None
    # ---- 4b. ground clutter (bushes on the scrub, boulders on the shore): placements an engine's detail scatter can use
    if tx.T.spec.get("ground_character", True) is not False and tx.mats.ground is not None:
        from . import terrain_ground
        from . import terrain_ground_clutter, terrain_ground_grass
        with tx.prof.stage("clutter (parent)"):
            ks = ("bush", "boulder")
            cb = None
            if tx.cfg.get("only"):  # (a block of tiles: only its ground)
                (i0, j0), (i1, j1) = tx.cfg["only"]
                cb = [tx.G.bounds(i0, j0)[0][:2].tolist(), tx.G.bounds(i1, j1)[1][:2].tolist()]
            C = terrain_ground_clutter.clutter(tx.T, tx.mats, tx.base, ks, box=cb)
            # (a stream's rocks, cobbles, driftwood, reeds, a lake's margin, a beach's pebbles and wrack:
            # terrain_stream_clutter.all_clutter)
            from . import terrain_stream
            from . import terrain_stream_clutter, terrain_stream_water
            SC = terrain_stream_clutter.all_clutter(tx.T, tx.mats, tx.base, box=cb) if terrain_stream.config(tx.T) is not None else None
            if SC is not None and not len(SC) and tx.mats.streams is None:
                SC = None
            with open(tx.out / "clutter.csv", "w") as f:
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
            tx.notes.append(f"clutter.csv: {int((C[:, 3] == 0).sum())} bushes, {int((C[:, 3] == 1).sum())} boulders")
            tx.clutter_sec = {"kinds": {"bush": {"scale_m": [0.6, 1.9], "squash": [0.45, 1.0], "z": "surface",
                                              "what": "a scrub / heath bush (squash < 1: wind-shorn by a cliff lip)"},
                                     "boulder": {"scale_m": [0.36, 1.96], "squash": [1.0, 1.0],
                                                 "z": "sunk 0.12 x scale", "what": "an angular rock (shore, rock "
                                                 "breaking through near cliff lips)"}},
                           "columns": terrain_stream.CSV_COLUMNS, "csv_version": terrain_stream.CSV_VERSION}
            if SC is not None:
                sm = terrain_stream_clutter.manifest(tx.mats.streams, SC)
                tx.clutter_sec = {**sm, "kinds": {**tx.clutter_sec["kinds"], **sm["kinds"]}, "columns": tx.clutter_sec["columns"],
                               "csv_version": tx.clutter_sec["csv_version"]}
                if tx.mats.streams is not None:
                    tx.notes.extend(tx.mats.streams.report())
                tx.notes.extend(terrain_stream_clutter.summary(tx.mats.streams, SC, cb))


def _trees(tx):
    """trees.csv, the layer textures, the styles' textures and zone maps."""

    # ---- 5. trees and the manifest
    _st = tx.prof.stage("trees + layer textures (parent)")
    _st.__enter__()
    from . import terrain_design_cover
    inst = terrain_design_cover.trees(tx.T)
    with open(tx.out / "trees.csv", "w") as f:
        f.write("x,y,z,kind,layer\n")
        layers = getattr(tx.T, "tree_layers", {})
        zs = np.zeros(0) if not len(inst) else tx.region.height(inst[:, 0], inst[:, 1]) if tx.region is not None \
            else tx.base.column(inst[:, 0], inst[:, 1])[0]
        # a tree stands only where the solid ground is under it: not over an arch's mouth or a notch the volumes cut
        # away (a cypress stood in the water at the arch), nor on a face the rock relief moved
        if len(inst):
            below = tx.base.value(np.c_[inst[:, :2], zs - 0.3])
            ok = below < 0
            n_drop = int((~ok).sum())
            # nor in the splash zone (a cypress stood on the wave-cut platform at pebble's point), nor on a cliff face
            # (more than 45 deg: the trees' masks are cut on the heightfield, the solid rock is steeper)
            sea = _sea(tx.T)
            wet = (zs < sea + 2.5) if sea is not None else np.zeros(len(zs), bool)
            _, gq = tx.base.value_gradient(np.c_[inst[:, :2], zs], 0.25)
            steep = gq[:, 2] / np.maximum(np.linalg.norm(gq, axis=1), 1e-9) < 0.7
            n_wet, n_steep = int((ok & wet).sum()), int((ok & ~wet & steep).sum())
            ok &= ~wet & ~steep
            # nor perched on a cliff's lip: a tree's roots want soil, so none within its crown of the turf's edge
            # (terrain_ground.TREE_LIP m in from it; wind-shorn cypress may stand closer)
            n_lip = 0
            if getattr(tx.base, "edits", None) is not None and len(inst):
                from . import terrain_ground
                from . import terrain_ground_clutter, terrain_ground_grass
                Pq = np.c_[inst[:, :2], zs]
                bare_, d_, edge_, top_ = tx.base.edits.bare(Pq)
                kinds_ = [layers.get(int(li), ("", ""))[1] for li in inst[:, 3]]
                tx.need = np.array([terrain_ground.TREE_LIP.get(k_, terrain_ground.TREE_LIP["default"]) for k_ in kinds_])
                lip = (top_ > 0.3) & (d_ - edge_ < tx.need)
                n_lip = int((ok & lip).sum())
                ok &= ~lip
            inst, zs = inst[ok], zs[ok]
            if n_drop:
                tx.notes.append(f"{n_drop} trees dropped: no solid ground under them")
            if n_wet or n_steep or n_lip:
                tx.notes.append(f"{n_wet} trees dropped in the splash zone (under 2.5 m over the sea), {n_steep} on "
                             f"faces steeper than 45 deg, {n_lip} on cliff lips (closer to the turf's edge than "
                             "terrain_ground.TREE_LIP)")
        for (x, y, _, li), z in zip(inst, zs):
            nm, kind = layers.get(int(li), ("", ""))
            f.write(f"{x:.2f},{y:.2f},{z:.2f},{kind},{nm}\n")
    tx.groups = [tx.mats.layers[g:g + 4] for g in range(0, len(tx.mats.layers), 4)]
    tx.layer_tex = {}
    if tx.cfg.get("maps"):
        from . import terrain_bake_layers, terrain_bake_maps
        tx.layer_tex = terrain_bake_layers.layer_textures(tx.out, {nm: tx.mats.layer_ref(nm) for nm in tx.mats.layers})
    tx.style_sec = None
    if tx.T.spec.get("styles"):  # (per-style tileable layer textures + zone maps for the engine's shader: terrain_style)
        from . import terrain_style_files
        tx.style_sec = terrain_style_files.write(tx.out, tx.T, {nm: tx.mats.layer_ref(nm) for nm in tx.mats.layers},
                                        tiles=[(i, j, tuple(float(x) for x in np.concatenate(tx.G.bounds(i, j))))
                                               for j in range(tx.G.nj) for i in range(tx.G.ni)], layers=tx.mats.layers)
    tx.detail = terrain_mesh._CTX.get("detail_entry")
    _st.__exit__(None, None, None)
