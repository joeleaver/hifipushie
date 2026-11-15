# STATE: long functions as stages (_export, _export_tiles, grow, write_glb, cards_job) -- 2026-11-15

Joe: "Yes you should" (the character export), "Yes, stage it" (the tile export, 2026-11-14; `grow`, 2026-11-15), "Yes,
both" (`write_glb`, `cards_job`). Goal: each function readable and under the 500-line rule, no statement changed.

## Current best
- `asset_export._export` (C468): the context (`Export`, made from its arguments), thirteen stage calls, the last one's
  return value; the stages in asset_export_parts / _wear / _rig / _lods / _finish.py (asset_export.py 199 lines,
  the largest module 292). 85 of 329 variables cross a stage (`ex.<name>`).
- `terrain_tiles._export_tiles` (C470): the context (`TileExport`), eleven stage calls, cut at the function's own
  numbered sections; the stages in terrain_tiles.py (243 lines), terrain_tiles_build (363), _ground (182), _manifest
  (275). 76 of 234 variables cross a stage (`tx.<name>`). terrain_mesh.MODULES names the modules (hashed by the state).
- `vegetation_grow.grow` (C474): its first 6 statements stay in `grow` as they are, the PROLOGUE (three early returns).
  Then the context (`Growth`: the 3 arguments and s, h, t0 from the prologue) and seven stage calls: _setting, _guides,
  _seedling (vegetation_grow.py, 151 lines) | _seasons (vegetation_grow_seasons.py, 424) | _wood, _dead_wood, _finish
  (vegetation_grow_wood.py, 260). 40 of 257 variables cross a stage (`gx.<name>`).
- `veg_export_glb.write_glb` (C475): the context (`PlantGlb`), nine stage calls: _subject, _builders, _finish
  (veg_export_glb.py, 217 lines) | _bark, _foliage_materials, _leaf_materials, _forks, _impostor_materials (_materials,
  226) | _plants (_plants, 267). 53 of 173 variables cross a stage (`pg.<name>`); five nested builders are handed on.
- `hair_cards_job.cards_job` (C478): the context (`CardsJob`), twelve stage calls: _settings, _pictures, _lock_marks
  (hair_cards_job.py, 210 lines) | _cards, _shell_cards (hair_cards_job_cards.py, 275) | _cap, _baby, _budget, _bake,
  _meshes, _clearance, _write (hair_cards_job_finish.py, 253). 54 of 211 variables cross a stage (`cj.<name>`).

## Proofs
- Structure: `destage_check.py <root> <file> <function> <ctx> <commit before>` on the staged, unsplit file (a worktree
  at its tag archive/before-<name>-stage-split): the stages put back into one body equal the old function statement
  for statement, comments in order. `_export` (ex, d9d3e655): 112 statements, 140 comments. `_export_tiles` (tx,
  f776cb50): 171, 94. `grow` (gx, b934a449): 85 = 6 prologue + 79, 94. `write_glb` (pg, 159ad8ba): 70, 47. `cards_job`
  (cj, 41452738): 78, 141. Splits (same_units, same_comments): 16 units, 143 comments; 17, 96; 9, 94; 12, 47; 15, 141.
- Behaviour, exports: proof_export.py, 124 files, equal but for Blender's tangents (last bit) and 1-4 pixels of a
  normal map, as old against old. proof_tiles.py, 202 files: 194 byte for byte, 4 differ in times, 4 in the code's hash.
- Behaviour, `grow`: proof_grow.py, 60 plants per source tree, one sha1 each over every array and scalar `grow`
  returns (not stats.grow_s). Old, old again, new: three equal files; 23 of 692 code lines ran in no plant.
- Behaviour, `write_glb`: proof_glb.py, 25 exports (119 files, 43 GLBs): every binary chunk equal; the json differs
  only at stats.grow_s (a duration), as old against old. 7 lines ran in no case; impostor pictures were synthetic.
- Behaviour, `cards_job`: proof_cards.py, 31 jobs on a ball head (loose, tied, short, shells, drawn; every tier; knobs
  set as export scripts set them), one sha1 each over what hair_job.job returns. Old (the fixed function), old again,
  new: three equal files. 58 of 513 code lines ran in no case (the swoop, the fade, an arch card's own lines).
- No test reads a staged module's source text but `_export`'s. Records: /mnt/data/hifipushie/proof_*/REPORT.md.

## Tools (not in the repo): /mnt/data/hifipushie/deadcode/
stage_function.py (its docstring is the rule: what crosses a stage, the prologue), destage_check.py, plan_stage_<x>.py
(stages by anchor: re-run if main changes the function), plan_<module>.py (module splits), proof_<name>.py, *_diff.py.

## Decisions in force
- A variable is the context's only if a stage reads it before certainly setting it (or it is an argument, or a def
  reads it and more than one stage sets it, or a nested def declares it nonlocal). Other loop variables stay locals.
- Prologue: a plan may begin its first stage late. The statements before it stay in the driver unchanged, returns
  included; the context is made after them from the arguments and those of their variables the stages need.
- Lazy imports stay lazy. A helper only one stage calls moves with it. `preview` (asset_export) was not touched.
- A read the old function could reach unset (UnboundLocalError) is an AttributeError on the context once staged.

## Open
1. The contexts are flat bags (85, 76, 40, 53, 54 names): group them, give stages narrower inputs, by hand, with proofs.
2. Still long, because a stage begins only at a statement of the function and a loop or an `if` is one statement:
   _seasons (407, its loop 398), _plants (247, its loop 241), _cards (214, its `if` 203), _tile_lods (181); also
   _manifest (164), _lods (182). proof_tiles.py has no stream, cave or style case.
3. A staging proves the function equals the old one, faults included (C477): run the old one at its defaults first.

NEXT: no giant function is left. Joe's call: Open 1, or the long files still whole (resources, sdf, spec).
