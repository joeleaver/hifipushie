# STATE: legacy removal

Goal: delete superseded routes outright, then split what survives into files of about 500 lines, then re-review each area.
Rule (Joe, 2026-11-10): no backwards compatibility. No gate, no switch, no shim; tag main before a large deletion.

## Done
- Pass 1 (landed, d8f3e9b9; tag archive/before-legacy-pass1): nine unreferenced modules, 13 spikes.
- Clothes, cut 1 (landed, 551ff8d8; tag archive/before-legacy-cloth; ledger C409):
  - the nine gated tools (fit_garment, style_garment, release_garment, arrange_garment, dress, look_cloth, check_garment,
    check_garment_reference, game_garment), HIFIPUSHIE_LEGACY_CLOTH and the guide's paragraph filter;
  - every function and constant nothing live reached after that: 284, with modules cloth_over and hang_reads whole;
  - their tests: 3 files whole, parts of 14. Source 214.2k -> 207.5k lines; 1,860 tests collect.
- The filter hid by word match ("sim", "dress", "on the form") in every guide topic: guide("gates") had no four-gate
  list, guide("tools") no domain table and no sync / pull / heavy_status sections. Both are back. The clothes guides keep
  exactly the text agents saw.
- Clothes, cut 2 (landed, 5ba6e0e3; tag archive/before-legacy-cloth-2; ledger C411):
  - tools design_garment, look_pattern, alter_pattern, garment_reference, garment_from_reference,
    garment_reference_brief and the guide topic cloth_reference. No blind step trial called them (17 logs;
    garment_reference once, and its kind names confused the agent);
  - pattern_check takes (name, garment) and re-reads an own draft's flat gate; chain_garment the tool builds a garment
    only from its own draft. load_garment still loads design-sheet garments (cf_shirt, wf_simon) for regression runs;
  - every live message that named a deleted tool now says: change it in your draft (draft_pattern);
  - 281 functions and constants, fold_checks whole; their tests. Source 207.5k -> 202.4k lines; 1,792 tests collect.
- Proof for each cut, parent tree against branch, separate fresh homes: cf_shirt and wf_simon closed and open
  (load_garment + GarmentBuild.run) bit-identical in X; flat_check on the s4-19 jacket and s4-14 hussar identical.
  Harness: /mnt/data/hifipushie/deadcode/proof.py.
- Not done: module docstrings in trimmed files (drape, zozo_hang, fold_checks, garment_pull, cloth_check) still describe
  removed parts. Fix them when each file is split.

## What still reaches the old clothes code (measured after cut 2; each cut assumes the ones above it)
| cut | frees | what it needs first |
|---|---|---|
| a character's use of the old sims: asset._export -> cloth.export_part, scene.sync / pull, server.sync, server._garment_sheets | about 700 lines | decide how a dressed character is exported; export_asset reads clothes only from the old sims |
| the chain build's calls into the old build: chain_garment.load_garment -> cloth.build(place_only=True), pattern_form.form_source / form_refine | up to 5,300 lines | a small flat-mesh core in their place; changes what the build runs, so the garment thread decides and BUILD_VERSION moves |
| the design-sheet drafter (design_schema, design_targets, pattern_draft, pattern_jacket, pattern_styles, garment_design): reached only through cloth.pieces / cloth.validate for a garment with a "design" sheet | not measured | the regression garments cf_shirt and wf_simon re-made as own drafts; their error texts still name the deleted tools |
| the old sim backend: cloth_job and blender_cloth keep cloth.place, cloth._build and cloth_made | not measured | zozo_hang uses cloth_job for job plumbing only: split that off |

The first estimate of 33k deletable lines was by module import, not by function, and was too high.
The clothes guides (cloth_guide, cloth_design, cloth_construction, cloth_sim, cloth_faults, cloth_blocks,
cloth_background) are what was left after the old paragraphs went: they need one rewrite to steps 0-10.

## Tool (not in the repo): /mnt/data/hifipushie/deadcode/
dead.py (what the tools reach, function by function), why.py (why a symbol is live), frontier.py (links from live code
into the old modules), hyp.py (what a cut would free), apply.py (delete and keep imports consistent), check.py (source
and tests against main). Conservative: a class is kept whole, a module named in a string is kept whole.

## Also unreachable today, outside clothes (not touched)
blender_cards 446 lines, faceext 376, terrain_seams 201, flipfit 137, faceatlas 105, gnm_controls 90, blender_lashes 86.
Check blender_* by hand before deleting: Blender runs them by path.

NEXT: the split. server.py first (3.9k lines, every tool in one file: one module per tool domain), then the files
over 2,000 lines, one area at a time and only while no agent works in it. The remaining clothes cuts above each
wait on a decision named in their row.
