"""The end of a tile export: the manifest and what an engine reads beside it, stale files removed, the checks, the
profile, the result.
Stages of the tile export (terrain_tiles._export_tiles calls them in order; terrain_mesh.py has the overview)."""
from __future__ import annotations

import json
import time

import numpy as np

from . import terrain_mesh
from . import profiling
from .terrain_relief import facet
from .terrain_seam_check import lake_outlines, seam_check
from .terrain_tile_jobs import TilesCheckFailed, budget_check
from .terrain_volumes import _sea

def _manifest(tx):
    """The manifest and what an engine reads beside it (streams, corridors, falls, grass, caves); the budget check."""
    tx.manifest = {
        "format": "hifipushie terrain tiles 1",
        "units": "m",
        "axes": {"world": "x east, y north, z up", "gltf": "glTF x = east, y = up, z = -north (node translation = "
                                                          "the tile's south-west corner; vertices local to it)"},
        "origin": tx.G.origin.tolist(), "tile_size": tx.G.tile, "grid": [tx.G.ni, tx.G.nj],
        "world_min": tx.G.lo.tolist(), "world_max": tx.G.hi.tolist(),
        "trimmed": "the extent was trimmed to whole coarsest voxels" if tx.G.trimmed else "",
        "voxel": tx.G.voxel,
        "lods": [{"lod": k, "error_m": tx.cfg["error"][k], "budget_triangles": tx.cfg["budget"][k],
                  "made": "LOD0's mesh with the border chains simplified (Douglas-Peucker at error_m, each LOD's chain "
                          "a subset of the one before) and decimated to error_m"} for k in range(tx.G.lods)],
        "skirts": "primitive 1 of each tile (extras.role = skirt, double-sided material): each shared border's chain "
                  "extruded into the rock by how far the neighbours' LOD chains differ there (chains are nested "
                  "subsets, so that's at most their tolerances)",
        "collision": f"collision_<i>_<j>.glb: LOD {tx.cfg['collision']} surface, no skirts, positions only (in cliffs "
                     "mode: the cliff shells, their buried backs included; load it WITH ground_collision_<i>_<j>.glb, "
                     "the heightmap's grid with the hole cells left out). A tile's collision is decimated further "
                     "when its LOD came out over collision_budget (tiles[].collision_triangles)",
        "sea_level": _sea(tx.T),
        "lakes": lake_outlines(tx.T),
        "materials": {
            "layers": [{"name": nm, **tx.mats.layer_ref(nm), "weights": f"_WEIGHTS{g}", "channel": c,
                        **({"textures": tx.layer_tex[nm]} if nm in tx.layer_tex else {}),
                        "triplanar": nm in ("rock", "wet_rock")}
                       for g, grp in enumerate(tx.groups) for c, nm in enumerate(grp)],
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
                         if tx.cfg.get("maps") else
                         "COLOR_0 is a display colour (linear) with a plain matte material, so tiles look right in "
                         "any glTF viewer",
            "splat_uv": f"splats cover the tile plus {tx.cfg['splat_margin']} texels into the neighbours each side, "
                        f"row 0 north; texel centre (c, r) at x = min.x + (c - {tx.cfg['splat_margin']} + 0.5) * "
                        f"tile / {tx.sp}, y = max.y - (r - {tx.cfg['splat_margin']} + 0.5) * tile / {tx.sp}" if tx.sp else "",
        },
        "heightmaps": {"samples": tx.hm, "spacing": tx.G.tile / max(tx.hm - 1, 1), "format": "float32 .npy absolute metres, "
                       "north-up; .png 16-bit over the range", "range": tx.hrange,
                       "note": "the 2.5D ground only (volumes aren't in heightmaps); edges shared with neighbours"}
        if tx.hm else None,
        "trees": "trees.csv (x, y, z, kind, layer), world metres",
        "volumes": tx.notes,
        "mode": tx.cfg["mode"],
        "config": {k: v for k, v in tx.cfg.items() if not k.startswith("_") and k not in ("only", "incremental")},
        "texel_density_used": [round(d, 3) for d in tx.cfg.get("_density", [])],
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
        } if tx.cfg.get("maps") else None,
        "tiles": tx.manifest_tiles,
    }
    if tx.detail is not None:
        tx.manifest["detail"] = tx.detail
    if tx.style_sec is not None:
        tx.manifest["styles"] = tx.style_sec
    if tx.clutter_sec is not None:
        tx.manifest["clutter"] = tx.clutter_sec
    if tx.mats.streams is not None:  # (the rivers as the bed rules read them: for an engine's water, wet shading, audio)
        tx.manifest["streams"] = {
            "rivers": {r["name"]: [[round(float(a), 2) for a in row] for row in
                                   np.c_[r["xy"], r["level"], r["width"], r["energy"]][r["live"]]]
                       for r in tx.mats.streams.reaches},
            "columns": "x, y, water level (m), water width (m, across), energy 0..1 (0 slow and silty .. 1 a boulder "
                       "torrent)",
            "layers": {"gravel": "cobbles and gravel under the water and on bars", "silt": "fine sediment in pools and "
                       "slack margins", "bank": "the bank's damp foot above the water", "wet_rock": "bedrock in the "
                       "bed (steep reaches) and rock faces by the water"},
            "bed": "the heightmaps and cliff meshes carry the bed's shape (pools, riffles, bars); the water's level is "
                   "the rivers' own (never raised)"}
    if tx.cfg.get("corridors"):  # (0.25 m heightmaps along the water for a nested water solve: pushieworld note 118)
        from . import terrain_corridors
        cbox = None
        if tx.cfg.get("only"):
            (i0, j0), (i1, j1) = tx.cfg["only"]
            cbox = [tx.G.bounds(i0, j0)[0][:2], tx.G.bounds(i1, j1)[1][:2]]
        with tx.prof.stage("corridors (parent)"):
            cm = terrain_corridors.write(tx.T, tx.field, tx.region, tx.out, tx.cfg, box=cbox, log=tx.log, grid=tx.G)
        if cm:
            tx.manifest["corridors"] = cm
    if getattr(tx.T, "falls", None):  # (waterfalls: for the engine's falling sheet and spray; terrain_falls)
        from . import terrain_falls
        from . import terrain_stream
        from . import terrain_stream_clutter, terrain_stream_water
        wr = terrain_stream_water.wet_design(tx.T)["pools"] or [None] * len(tx.T.falls)
        tx.manifest["falls"] = {"falls": [{**f, "pool": {**f["pool"], "wet_radius": r}} if f.get("pool") and r is not None
                                       else f for f, r in zip(tx.T.falls, wr)], "note": terrain_falls.META_NOTE}
    if tx.cfg.get("maps") and tx.cfg.get("grass_detail", True) and any(nm in tx.mats.layers for nm in ("grass", "scrub",
                                                                                                "turf", "sand")):
        from . import terrain_ground  # (the turf's tiling detail: terrain_ground_grass.grass_swatch, one per kind)
        from . import terrain_ground_clutter, terrain_ground_grass
        ge = terrain_ground_grass.write_grass(tx.out, tx.mats.layers)
        wl = lambda lay: [[f"_WEIGHTS{tx.mats.layers.index(nm) // 4}", tx.mats.layers.index(nm) % 4] for nm in lay
                          if nm in tx.mats.layers]
        for sw in ge["swatches"]:
            sw["weights"] = wl(sw["layers"])
        ge["weights"] = wl(ge["layers"])
        tx.manifest["ground_detail"] = ge
    if tx.region is not None:
        tx.manifest["cliffs"] = {
            "what": "the ground is the heightmap (ground tiles); `tiles` are 3D cliff meshes laid over it wherever the "
                    f"ground is steeper than {tx.cfg['cliff_slope']:g} deg or a volume opens (cave mouths, arches, "
                    "notches, shafts). Each cliff mesh is a closed shell of rock that pinches out buried under the "
                    "heightmap at its edges: nothing to stitch.",
            "heightmap": f"pushed {tx.region.push:.2f} m into the rock under the cliffs (eroded in plan), so the cliff "
                         "face covers it; holes only where a void opens through it (hole PNG per ground tile: 255 = "
                         "hole, one per heightmap cell, row 0 north)",
            "shell": {"sink_m": round(tx.region.sink, 2), "thick_m": round(tx.region.thick, 2),
                      "cave_wall_m": tx.region.wall, "margin_m": tx.cfg["cliff_margin"]},
            "hole_cells": int(tx.region.holes.sum()),
        }
        tx.manifest["ground"] = tx.ground
        tx.manifest["heightmaps"] = {"samples": int(tx.cfg["heightmap"]), "spacing": tx.region.d,
                                  "format": "float32 .npy absolute metres, C order, row 0 = the tile's north edge, "
                                            "column 0 = its west; .png 16-bit over the range",
                                  "holes": "heightmaps/holes_<i>_<j>.png only for tiles with holes (ground[].holes)",
                                  "range": tx.hrange, "note": "pushed under the cliff meshes; edges shared with "
                                  "neighbours; ground_<i>_<j>_lod<k>.glb are the same samples as grid meshes (stride "
                                  "2^k, hole cells left out, vertical skirts on shared borders)"}
    if tx.caves:  # a person walked through every passage
        tx.t0 = time.time()
        from . import terrain_caves_early, terrain_caves_walk
        with tx.prof.stage("cave walk (parent)"):
            tx.manifest["cave_paths"] = []
            tx.manifest["caves"] = terrain_caves_walk.check(tx.caves, tx.base, sea=_sea(tx.T), paths=tx.manifest["cave_paths"])
            # the same walk's floor on what an engine collides with (the collision meshes): its steps can be taller
            # than the field's (decimation at the collision LOD's error, a pile of blocks simplified to a riser)
            try:
                for ln in terrain_caves_early.collision_steps(tx.manifest["cave_paths"], tx.out, tx.manifest_tiles,
                                                        int(tx.cfg["collision"])):
                    tx.manifest["caves"].append(ln)
            except Exception as ex_:  # (a measure, never the export's failure)
                tx.log(f"cave steps on the collision meshes not measured: {ex_}")
        tx.timing["cave walk"] = time.time() - tx.t0
    tx.over = budget_check(tx.manifest_tiles, tx.cfg, tx.G.lods, [cv.name for cv in tx.caves] if tx.caves else [])
    tx.manifest["budget_check"] = {"limit": f"{terrain_mesh.OVER_BUDGET:g} x the LOD's budget", "over": tx.over}
    tx.manifest["dropped_pieces"] = {"limit_m2": float(tx.cfg.get("float_piece_m2", terrain_mesh.FLOAT_PIECE)), "pieces": tx.dropped_pieces}
    for o in tx.over[:12]:
        tx.log(f"OVER BUDGET: tile {o['tile'][0]},{o['tile'][1]} LOD {o['lod']}: {o['triangles']} triangles against "
            f"{o['budget']}: {o['why']}")
    (tx.out / "manifest.json").write_text(json.dumps(tx.manifest, indent=1))


def _finish(tx):
    """Stale files removed, the next export's state saved, the checks, the profile, the result (raises if a check failed)."""
    # files no tile names any more (a tile that lost its cliff, a LOD without maps now) go; then the state the next
    # export builds on
    keep_files = {f for e in tx.manifest_tiles + tx.ground for f in tx.inc.entry_files(e)}
    for f in list(tx.out.glob("*.glb")) + [p for d in tx.inc.OUT_DIRS for p in (tx.out / d).glob("*") if p.is_file()]:
        if str(f.relative_to(tx.out)) not in keep_files:
            f.unlink()
    tx.inc.save(tx.out, {"format": tx.inc.FORMAT, "code": tx.fp.parts["code"], "global": tx.fp.global_key, "global_parts": tx.fp.parts,
                   "tiles": tx.ns})
    tx.timing["total before check"] = time.time() - tx.t_all
    tx.t0 = time.time()
    if tx.cfg.get("checks", True):
        # (what the checks compute from each tile's files, kept by those files' bytes: an incremental export decodes
        # only the maps of the tiles it rewrote)
        memo = tx.inc.Memo(tx.out, "checks", tx.fp.parts["code"])
        with tx.prof.stage("check: seams (parent)"):
            check = seam_check(tx.out, memo=memo) if tx.manifest_tiles else {"summary": {"failures": 0}, "failures": []}
        if tx.region is not None:
            from . import terrain_cliffs
            tx.terrain_cliffs = terrain_cliffs
            from . import terrain_cliffs_checks, terrain_cliffs_ground
            with tx.prof.stage("check: ground (parent)"):
                gc = terrain_cliffs_ground.ground_check(tx.out, tx.manifest, tx.region, memo=memo,
                                                 tile_keys={ij: tx.fkey[ij][0] for ij in tx.tiles})
            check["summary"]["ground"] = gc["summary"]
            check["failures"] += gc["failures"]
            with tx.prof.stage("check: lakes (parent)"):
                lc = terrain_cliffs_checks.lake_check(tx.out, tx.manifest)
            check["summary"]["lakes"] = lc["summary"]
            check["failures"] += lc["failures"]
        # what the eye sees that the per-channel border comparison can't: squares locked to the terrain's grid in the
        # colour, and texel density jumping between neighbouring tiles (sharp rock beside soft)
        from . import terrain_seams
        with tx.prof.stage("check: grid squares (parent)"):
            gs = terrain_seams.grid_squares(tx.T, tx.mats)
        if tx.base.rock is not None:  # how regular the facets look (a lattice shows repeated diamonds from afar)
            from . import terrain_facets
            rk = tx.base.rock
            with tx.prof.stage("check: facet periodicity (parent)"):
                per = terrain_facets.periodicity(lambda P, fd: facet(P, 1.5 * rk["size"], rk["seed"], fd)
                                                 + 0.3 * facet(P, 0.6 * rk["size"], rk["seed"] + 5, fd))
            check["summary"]["facet_periodicity"] = per
            if max(per) > terrain_facets.PERIODIC:
                check["failures"].append(f"rock facets look regular (autocorrelation peaks {per}, limit "
                                         f"{terrain_facets.PERIODIC}): a quilt of repeated diamonds from afar")
        with tx.prof.stage("check: texel density (parent)"):
            td = terrain_seams.texel_density(tx.manifest) if tx.cfg.get("maps") else {"summary": {}, "failures": []}
        check["summary"]["grid_squares"], check["summary"]["texel_density"] = gs, td["summary"]
        if not gs["ok"]:
            check["failures"].append(f"the colour bends on every terrain cell line (x{gs['ratio']} the kinks between "
                                     f"them): cell-sized squares on the rock")
        check["failures"] += td["failures"]
        if tx.detail is not None:  # the swatch must tile: its wrap seam's jump against the steps beside it
            check["summary"]["swatch_wrap_seam"] = tx.detail["wrap_seam"]
            if not tx.detail["tileable"]:
                from . import terrain_swatch
                from . import terrain_swatch_detail
                check["failures"].append(f"the detail swatch's wrap seam shows (jump excess {tx.detail['wrap_seam']}, "
                                         f"limit {terrain_swatch.TILE_LIMIT})")
        for o in tx.over:
            check["failures"].append(f"tile {o['tile'][0]},{o['tile'][1]} LOD {o['lod']}: {o['triangles']} triangles "
                                     f"against a budget of {o['budget']}: {o['why']}")
        check["summary"]["over_budget"] = len(tx.over)
        check["summary"]["failures"] = len(check["failures"])
        check["summary"]["failed"] = check["failures"][:40]
        memo.save()
        tx.redone["check samples"] = {"reused": memo.hits, "computed": memo.misses}
    else:  # (a preview: `preview_tiles`)
        check = {"summary": {"failures": 0, "skipped": "checks off (a preview)"}, "failures": []}
    tx.timing["seam check"] = time.time() - tx.t0
    tx.manifest["seam_check"] = check["summary"]
    tx.manifest["timing_s"] = {k: round(v, 2) for k, v in tx.timing.items()}
    tx.manifest["profile"] = tx.prof.as_dict()
    # (in the profile: like the timings, it says how this export ran, not what it made)
    tx.manifest["profile"]["incremental"] = {"previous export used": tx.prev_state is not None,
                                          "why not": tx.why_cold if tx.prev_state is None else "", "tiles": len(tx.tiles),
                                          "redone": tx.redone}
    tx.log(f"incremental: {json.dumps(tx.manifest['profile']['incremental'])}")
    (tx.out / "profile.txt").write_text(profiling.table(tx.manifest["profile"]))
    tx.log(profiling.table(tx.manifest["profile"], top=25))
    if tx.peak is not None:  # (what the job used, sampled every 0.5 s: PSS of the parent and its workers)
        tx.manifest["memory_gb"] = {k: round(v, 2) for k, v in tx.peak.items()}
    (tx.out / "manifest.json").write_text(json.dumps(tx.manifest, indent=1))
    result = {"out": str(tx.out), "manifest": tx.manifest, "stats": tx.stats, "timing": tx.timing, "check": check}
    if check["failures"]:
        # (everything is written and the manifest is complete: the caller can still report it, see `summary`)
        raise TilesCheckFailed(f"seam check FAILED (the tiles and manifest.json were written to {tx.out}):\n"
                               + "\n".join(check["failures"][:30]), result)
    return result
