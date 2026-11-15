# STATE: the long export functions as stages (asset_export._export, terrain_tiles._export_tiles) -- 2026-11-14

Joe (2026-11-14): "Yes you should" (the character export), then "Yes, stage it" (the tile export).
Goal: each function readable and under the 500-line rule, with not one statement changed. Ledger C468 (`_export`).

## Current best
- `asset_export._export`: the context (`Export`, made from its arguments), thirteen stage calls, the last one's
  return value: _begin, _mesh, _density, _lowpoly, _bake (asset_export_parts.py, except _begin) | _hair, _clothes,
  _materials (asset_export_wear.py) | _rig, _shapes, _correctives (asset_export_rig.py) | _lods
  (asset_export_lods.py) | _finish (asset_export_finish.py). asset_export.py is 199 lines, the largest module 292.
  85 of 329 variables cross a stage (`ex.<name>`), 244 are locals; nine imports / defs handed on by one added line.
- `terrain_tiles._export_tiles`: the context (`TileExport`), eleven stage calls, cut at the function's own numbered
  sections: _setup, _keys (terrain_tiles.py, 243 lines, with export_tiles, preview_tiles, summary) | _cubes,
  _border_chains, _dense_meshes, _tile_lods (terrain_tiles_build.py, 363) | _ground_maps, _clutter, _trees
  (terrain_tiles_ground.py, 182) | _manifest, _finish (terrain_tiles_manifest.py, 275). 76 of 234 variables cross a
  stage (`tx.<name>`), 158 are locals; four imports handed on (copy, inc, shutil, terrain_cliffs: 6 added lines).
  terrain_mesh.MODULES and its overview name the three new modules (the export's state hashes all their code).
- Commits: `_export` three (locals() lookups by hand; staging; modules); `_export_tiles` two: the tool learned `nonlocal`.

## Proofs
- Structure: `destage_check.py <root> <file> <function> <ctx> <commit before>`: the stages put back into one body
  equal the old function statement for statement, comments in order. `_export`: 112 statements, 140 comments.
  `_export_tiles` (tx, against f776cb50): 171 statements, 94 comments, 1 name dropped from a nonlocal statement.
  Splits (same_units, same_comments against the staged file): 16 units, 143 comments; tiles (tag tiles-staged): 17, 96.
- Behaviour, `_export`: proof_export.py, five exports per tree, 124 files: equal except the body's TANGENT array in
  the last bit (max 1.8e-7) and 1-4 pixel values by 1 in a normal map; the old code against itself differs the same
  way (Blender's tangents). golfer fails the same on both.
- Behaviour, `_export_tiles`: proof_tiles.py (run_proof_tiles.sh <tree> <label>) on the coast of tests/test_tiles.py:
  `coast` (four tiles round the cliff tile, 2 LODs, baked maps, ground maps, clutter, trees, the checks) and `again`
  (two exports into one folder: the second reads the first's state). RESULT (2026-11-14, 202 files, tiles_diff.py):
  old against old: 196 byte for byte, 6 differ only in times, memory and the profile. Old against new: 194 byte for
  byte (every GLB, map, heightmap and csv), 4 the same way, 4 only in the code's hash (state.pkl's code and global
  key; checks.pkl's keys, every value equal). The coast has no streams, falls, caves or styles: those blocks of
  _manifest and _trees did not run. The checks fail on this cut of the coast, the same on all three runs.
- No test reads terrain_tiles.py's source text; those that read `_export`'s read every export module, `ex.` read away.

## Tools (not in the repo): /mnt/data/hifipushie/deadcode/
stage_function.py (the staging; its docstring is the rule for what crosses a stage), plan_stage_export.py and
plan_stage_tiles.py (stages by anchor: a statement's start, or a `#` comment of the function; re-run if main changes
the function before landing), destage_check.py, plan_asset_export.py and plan_terrain_tiles.py (the module splits),
proof_export.py, proof_tiles.py, run_proof_tiles.sh, compare_export.py, tiles_diff.py (differences by kind), glb_diff.py.

## Decisions in force
- A variable is the context's only if a stage reads it before certainly setting it (or it is an argument, or a def
  reads it and more than one stage sets it). Loop variables every stage sets for itself stay locals.
- Nonlocal (new, for on_done's `nonlocal t_dec`): a name a nested def declares nonlocal is the context's; it is
  dropped from that statement, and the statement goes when no name is left. destage_check drops exactly those names
  from the OLD function before comparing, prints how many, and fails on a bare use of one in the staged def.
- Lazy imports stay lazy: a module one stage imports under a condition is not imported at the top of another.
- A helper only one stage calls moves with it (`_maps_done` with _tile_lods): left behind it is an import cycle.
- `preview` (asset_export) was not touched (the review-fixes session edits it).

## Open
1. Both contexts are flat bags (85 and 76 names): group them and give stages narrower inputs, by hand, with the proofs.
2. Still long, one statement or block each: _tile_lods (181 lines, a while loop), _manifest (164), _lods (182); and
   the giant functions left: vegetation_grow.grow (733), veg_export_glb.write_glb (578), hair_cards_job.cards_job (570).
3. proof_tiles.py has no stream, cave or style case: add one before the tile export's stages are cut further.

NEXT: the coordinator lands tiles-stages (re-run the proofs; add the ledger row; every existing tile export goes cold
once: the code's hash changed). Then Joe's call: the next giant function (vegetation_grow.grow), or Open 1.
