# STATE: long functions as stages (asset_export._export, terrain_tiles._export_tiles, vegetation_grow.grow) -- 2026-11-15

Joe: "Yes you should" (the character export), "Yes, stage it" (the tile export, 2026-11-14; `grow`, 2026-11-15).
Goal: each function readable and under the 500-line rule, with not one statement changed. Ledger C468 (`_export`).

## Current best
- `asset_export._export`: the context (`Export`, made from its arguments), thirteen stage calls, the last one's
  return value; the stages in asset_export_parts / _wear / _rig / _lods / _finish.py (asset_export.py 199 lines,
  the largest module 292). 85 of 329 variables cross a stage (`ex.<name>`).
- `terrain_tiles._export_tiles`: the context (`TileExport`), eleven stage calls, cut at the function's own numbered
  sections; the stages in terrain_tiles.py (243 lines), terrain_tiles_build (363), _ground (182), _manifest (275).
  76 of 234 variables cross a stage (`tx.<name>`). terrain_mesh.MODULES names the modules (the state hashes them).
- `vegetation_grow.grow` (branch grow-stages, NOT LANDED): its first 6 statements stay in `grow` as they are, the
  PROLOGUE (the resolved spec; a sward or a clump handed to its own module; the run that sets the unit from
  `height`: three early returns). Then the context (`Growth`: the 3 arguments and s, h, t0 from the prologue) and
  seven stage calls: _setting, _guides, _seedling (vegetation_grow.py, 151 lines) | _seasons
  (vegetation_grow_seasons.py, 424) | _wood, _dead_wood, _finish (vegetation_grow_wood.py, 260). 40 of 257 variables
  cross a stage (`gx.<name>`); `n` (nonlocal in `subset`) is one. vegetation.MODULES names both new modules.
- The loop that stays whole: `for step in range(steps)` is ONE statement of `grow`, 398 lines. A stage begins only at
  a statement of the function itself, so _seasons is 407 lines of statements: the loop, with new_axis and the
  loop's settings before it (begun at the loop alone, 44 names cross instead of 40). Its target is `gx.step`.

## Proofs
- Structure: `destage_check.py <root> <file> <function> <ctx> <commit before>` on the staged, unsplit file (a
  worktree at tag archive/before-{export,tiles,grow}-stage-split): the stages put back into one body equal the old
  function statement for statement, comments in order. `_export` (ex, d9d3e655): 112 statements, 140 comments.
  `_export_tiles` (tx, f776cb50): 171, 94, 1 name dropped from a nonlocal. `grow` (gx, b934a449): 85 = 6 prologue
  + 79 in 7 stages, 94, 1 dropped (n). Splits (same_units, same_comments): 16 units, 143 comments; tiles 17, 96; grow 9, 94.
- Behaviour, exports: proof_export.py, 124 files, equal but for Blender's tangents (last bit) and 1-4 pixels of a
  normal map, as old against old. proof_tiles.py, 202 files: 194 byte for byte, 4 differ in times, 4 in the code's hash.
- Behaviour, `grow`: proof_grow.py grows 60 plants per source tree (the 16 packaged presets at their default and
  at 0.6 of their age with seed + 7; 28 cases, most on a 22-year birch: height, guides, prunes, cuts, girths, a
  stand, wind, decay, dead wood, log), one sha1 each over every array and scalar `grow` returns (not stats.grow_s).
  Old, old again, new: three equal files. `--lines`: 23 of 692 lines with code ran in no plant (proof_grow/lines_new.txt).
- No test reads the source text of terrain_tiles.py or vegetation_grow*.py; `_export`'s readers read every module.

## Tools (not in the repo): /mnt/data/hifipushie/deadcode/
stage_function.py (the staging; its docstring is the rule for what crosses a stage and for the prologue),
destage_check.py, plan_stage_{export,tiles,grow}.py (stages by anchor: re-run if main changes the function first),
plan_{asset_export,terrain_tiles,vegetation_grow}.py (module splits), proof_{export,tiles,grow}.py, tiles_diff.py.

## Decisions in force
- A variable is the context's only if a stage reads it before certainly setting it (or it is an argument, or a def
  reads it and more than one stage sets it, or a nested def declares it nonlocal). Other loop variables stay locals.
- Prologue (new, for grow's early returns): a plan may begin its first stage after the function's first statement.
  The statements before it stay in the driver unchanged, returns included; the context is made after them from the
  arguments and the prologue's variables the stages need (read before the stages, in order, have certainly set
  them), each by its own name. Refused: such a variable set on some paths only; a def, lambda or generator in the
  prologue reading what a stage sets; a return after the prologue outside the last stage. destage_check compares
  the prologue one by one with the old function's first statements and prints how many it found.
- Lazy imports stay lazy. A helper only one stage calls moves with it. `preview` (asset_export) was not touched.

## Open
1. The contexts are flat bags (85, 76 and 40 names): group them, give stages narrower inputs, by hand, with proofs.
2. Still long: _seasons (407: its numbered sections can only become functions by hand, the step's locals passed),
   _tile_lods (181), _manifest (164), _lods (182); giants left: veg_export_glb.write_glb (578), cards_job (570).
3. proof_tiles.py has no stream, cave or style case; stage_function.py's class docstring order can vary (hash seed).

NEXT: the coordinator re-runs the proofs (/mnt/data/hifipushie/proof_grow/REPORT.md has every command), runs
bin/suite, lands grow-stages and adds the ledger row. Then Joe's call: write_glb, cards_job, or Open 1.
