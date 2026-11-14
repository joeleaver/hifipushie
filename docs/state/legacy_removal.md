# STATE: legacy removal

Goal: delete superseded routes outright, then split what survives into files of about 500 lines, then re-review each area.
Rule (Joe, 2026-11-10): no backwards compatibility. No gate, no switch, no shim; tag main before a large deletion.

## Done
- Pass 1 (landed, d8f3e9b9; tag archive/before-legacy-pass1): nine unreferenced modules, 13 spikes.
- Clothes, cut 1 (landed, 551ff8d8; tag archive/before-legacy-cloth; ledger C409):
  - the nine gated tools (fit_garment, style_garment, release_garment, arrange_garment, dress, look_cloth, check_garment,
    check_garment_reference, game_garment), HIFIPUSHIE_LEGACY_CLOTH, the guide's paragraph filter (it had hidden text
    in every topic: back), 284 functions and constants nothing live reached, their tests. Source 214.2k -> 207.5k lines.
- Clothes, cut 2 (landed, 5ba6e0e3; tag archive/before-legacy-cloth-2; ledger C411):
  - tools design_garment, look_pattern, alter_pattern, garment_reference, garment_from_reference,
    garment_reference_brief and the guide topic cloth_reference: no blind step trial called them (17 logs);
  - pattern_check takes (name, garment) and re-reads an own draft's flat gate; chain_garment the tool builds a garment
    only from its own draft. load_garment still loads design-sheet garments (cf_shirt, wf_simon) for regression runs;
  - every live message that named a deleted tool now says: change it in your draft (draft_pattern); 281 functions and
    constants and their tests. Source 207.5k -> 202.4k lines.
- Proof for each cut (parent tree vs branch, fresh homes): cf_shirt and wf_simon builds bit-identical in X; flat_check
  on the s4-19 jacket and s4-14 hussar identical.
- The split (tags archive/before-split-*): constants never move (C422); every other unit moves unchanged.
  1 server.py (3,913 lines; C413) -> mcp_app, tool_common, tools_find, one tools_<domain>.py each; tool surface identical.
  2 terrain_mesh.py (5,680; C414) -> 15 modules. 3 hair.py (5,694; C415) -> 15. 4 face_ruler.py, base.py, faceshapes.py
    (9.1k; C417) -> 10, 10, 9; class GnmFace in five mixins. 5 skin_read.py, blockin.py, likeness.py (7.1k; C419) -> 8, 9, 10.
  6 terrain.py, clutter.py, hair_clumps.py (6.7k; C424) -> 8, 8, 6; class Terrain in terrain_model. 7 skin_project.py,
    vegetation.py, terrain_design.py (5.7k) -> 9, 6, 7. 8 (C427) rig, retopo, hair_cards, hair_flow, veg_style, asset,
    lods, paint, terrain_style, humanfit, hair_read, images (19.5k) -> 71; asset.export stays (the export scripts call it).
  9 (landed 2026-11-12; C428) skin, skin_features, terrain_cliffs, onemesh, scene, veg_export, terrain_stream,
    hair_strands, veg_tools, assemble (11.4k) -> 43 modules. 10 (2026-11-14; C447) veg_leaf, skin_layers, faceslide, judge, blockin_eyes, terrain_caves, skin_marks, gnm_fold, terrain_swatch, terrain_bake, gnm_controls, eye_ruler (10.7k) -> 54.
- CONSTANTS STAY (C422): scripts outside the repo set module.NAME (assembly/exp.py HP_FS_SET, assembly_garrett/s15/
  sh4t.py, haircards/t47/r47.sh). A family's base holds every constant and alone runs code at import (rule test).
- MOVED NAMES (C427): 7,470 uses in scripts outside the repo named functions the splits moved. The AttributeError now
  says where the name is (moved.refuse in every base); `bin/repoint <script.py> --write` rewrites a script; the repo's
  own spikes/ and examples/ are repointed (C428). Rule tests: test_undefined_names, test_constants_address, test_moved.
- Still over 500 lines because one function is: asset_export 956 (_export 888), terrain_tiles 928 (_export_tiles 799),
  vegetation_grow 750 (grow 733), veg_export_glb 601 (write_glb 578), hair_cards_job 600 (cards_job 570): refactoring.
- NOT split, and why: blender_* (Blender runs them by path); fieldjit (numba kernels cached beside the file); artist
  (a CLI); the clothes files (the chain-build cut first). Everything else over 1,000 lines is split.

## What still reaches the old clothes code (measured after cut 2; each cut assumes the ones above it)
| cut | frees | what it needs first |
|---|---|---|
| a character's use of the old sims: asset_export._export -> cloth.export_part, scene_sync.sync / pull, server.sync, server._garment_sheets | about 700 lines | decide how a dressed character is exported; export_asset reads clothes only from the old sims |
| the chain build's calls into the old build: chain_garment.load_garment -> cloth.build(place_only=True), pattern_form.form_source / form_refine | up to 5,300 lines | a small flat-mesh core in their place; changes what the build runs, so the garment thread decides and BUILD_VERSION moves |
| the design-sheet drafter (design_schema, design_targets, pattern_draft, pattern_jacket, pattern_styles, garment_design): reached only through cloth.pieces / cloth.validate for a garment with a "design" sheet | not measured | the regression garments cf_shirt and wf_simon re-made as own drafts; their error texts still name the deleted tools |
| the old sim backend: cloth_job and blender_cloth keep cloth.place, cloth._build and cloth_made | not measured | zozo_hang uses cloth_job for job plumbing only: split that off |

The clothes guides (cloth_guide, cloth_design, cloth_construction, cloth_sim, cloth_faults, cloth_blocks,
cloth_background) are what was left after the old paragraphs went: they need one rewrite to steps 0-10.

## Tools (not in the repo): /mnt/data/hifipushie/deadcode/
Dead code: dead.py, why.py, frontier.py, hyp.py, apply.py, check.py. A split: sections.py, rebound.py, external_uses.py
(before; units_brief.py lists a file's units for the plan); pipeline.sh <root> <tag> <module> runs split_module / split_class / rehome / add_modules / regap / retail /
repoint, the proof, same_comments and same_order (a rehome plan needs MID_IMPORTS too). Proofs: same_units, same_members, rehomed_all, shadow_check, surface.

## Also unreachable today, outside clothes (not touched; check blender_* by hand, Blender runs them by path)
faceext 376 lines, terrain_seams 201 of 308 (its measure side), flipfit 137, faceatlas 105, gnm_controls 90. NOT unreachable: blender_cards, blender_lashes (blender_scene imports both inside functions).

Full run of every test after the splits (C430): nothing of the splits fails. Area re-review 2026-11-12: reports in /mnt/data/hifipushie/review_20261112/; its fixes: docs/state/mcp_rules.md.
NEXT: the long files still whole: terrain_sea, hair_loose, terrain_ground, skin_folds (their callers are in files other sessions have in flight: split once those land), resources, sdf, spec; then the five giant functions (asset_export is 1,004 lines). The clothes files wait for the chain-build cut.
