# STATE: the character export as stages (asset_export._export) -- 2026-11-14

Joe (2026-11-14, to "restructure the 930-line character export function into stages?"): "Yes you should".
Goal: `_export` readable and under the 500-line rule, with not one statement changed. Ledger C461.

## Current best
- `asset_export._export` keeps its signature and docstring and is: the context (`Export`, made from its arguments),
  thirteen stage calls, the last one's return value. Stages, in order: _begin, _mesh, _density, _lowpoly, _bake
  (asset_export_parts.py, except _begin) | _hair, _clothes, _materials (asset_export_wear.py) | _rig, _shapes,
  _correctives (asset_export_rig.py) | _lods (asset_export_lods.py) | _finish (asset_export_finish.py).
  asset_export.py holds Export, _export, _begin and preview (199 lines); the largest module is 292, _lods is 182 lines.
- 85 of the function's 329 variables cross a stage: read and written as `ex.<name>` (the class's docstring lists which
  stage sets which). The other 244 are locals of the stage that uses them.
- Eight modules and one helper that one stage imports or defines and a later one reads are handed on by one added
  line each (`ex.rigmod = rigmod`): no import became earlier or unconditional.
- Three commits: (1) five `locals().get(...)` lookups became plain variables set to None first (hair_cards, above,
  below); (2) the staging, by tool; (3) the stages moved into modules, by the split tool; asset.MODULES lists them.

## Proofs
- Structure: `destage_check.py <root> src/hifipushie/asset_export.py _export ex <commit 1>` on commit 2: the stages
  put back into one body equal the old function statement for statement (112), comments in order (140).
  Commit 3: same_units, same_comments (16 units, 143 comments).
- Behaviour: /mnt/data/hifipushie/deadcode/proof_export.py runs five exports per tree into one fixed out dir:
  fixtures (prefabs, two atlases), troll (creature, rig, LODs), golfer (base body, hair locks, rig), gnm_talk (GNM
  head, face shapes, hero, LODs), cf_shirt (the dressed test character). Old tree = main at the branch point; files
  compared one by one. RESULT: see the ledger row (filled in when the run ends).
- Tests that read the export's source text read every export module with `ex.` read away (test_codified,
  test_garment_asset, test_skin).

## Tools (not in the repo): /mnt/data/hifipushie/deadcode/
stage_function.py (the staging; its docstring is the rule for what crosses a stage), plan_stage_export.py (stages by
anchor text, so it still holds when lines move: re-run it if main changes `_export` before landing),
destage_check.py, proof_export.py, plan_asset_export.py (the module split).

## Decisions in force
- A variable is the context's only if a stage reads it before certainly setting it (or it is an argument, or a def
  reads it and more than one stage sets it). Loop variables every stage sets for itself stay locals.
- Lazy imports stay lazy: a module one stage imports under a condition is not imported at the top of another.
- `preview` was not touched (the review-fixes session edits it).

## Open
1. The context is one flat bag of 85 names. Next cut, by hand and with the proof exports: group them (the call's
   arguments, the parts and atlases, the rig), and give stages narrower inputs.
2. _lods (182 lines) is one `if lods:` block; _lowpoly's retry loop is 45 lines: both can be staged the same way.
3. The other giant functions: terrain_tiles._export_tiles (799), vegetation_grow.grow (733), veg_export_glb.write_glb
   (578), hair_cards_job.cards_job (570), hair_loose_grow.grow (484), terrain_sea_apply.apply (486): the tool takes
   any function that ends in one return and uses no locals(), walrus or nonlocal.

NEXT: Joe's call: stage the next giant function with the same tool (terrain_tiles._export_tiles is the largest), or
item 1 here.
