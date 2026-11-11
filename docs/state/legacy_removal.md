# STATE: legacy removal

Goal: delete superseded routes outright, then split what survives into files of about 500 lines, then re-review each area.
Rule (Joe, 2026-11-10): no backwards compatibility. No gate, no switch, no shim; tag main before a large deletion.

## Done
- Pass 1 (landed, d8f3e9b9; tag archive/before-legacy-pass1): nine unreferenced modules, 13 spikes.
- Clothes, cut 1 (branch legacy-cloth; tag archive/before-legacy-cloth; ledger C408):
  - the nine gated tools (fit_garment, style_garment, release_garment, arrange_garment, dress, look_cloth, check_garment,
    check_garment_reference, game_garment), HIFIPUSHIE_LEGACY_CLOTH and the guide's paragraph filter;
  - every function and constant nothing live reached after that: 284, with modules cloth_over and hang_reads whole;
  - their tests: 3 files whole, parts of 14. Source 214.2k -> 207.5k lines; 1,860 tests collect.
- The filter hid by word match ("sim", "dress", "on the form") in every guide topic: guide("gates") had no four-gate
  list, guide("tools") no domain table and no sync / pull / heavy_status sections. Both are back. The clothes guides keep
  exactly the text agents saw.
- Not done: module docstrings in trimmed files (drape, zozo_hang, fold_checks, garment_pull, cloth_check) still describe
  removed parts. Fix them when each file is split.

## What still reaches the old clothes code (measured; each cut assumes the ones above it)
| cut | frees | what it needs first |
|---|---|---|
| the seven ungated old tools: design_garment, look_pattern, alter_pattern, pattern_check, garment_reference, garment_from_reference, garment_reference_brief | about 4,000 lines | live texts name alter_pattern (structure_rows 23 times, chain refusals) and pattern_check (next_steps, garment_carry, draft_own_tool): reword them with the garment thread |
| a character's use of the old sims: asset._export -> cloth.export_part, scene.sync / pull, server.sync, server._garment_sheets | about 850 lines | decide how a dressed character is exported; export_asset reads clothes only from the old sims |
| the chain build's calls into the old build: chain_garment.load_garment -> cloth.build(place_only=True), pattern_form.form_source / form_refine | up to 5,400 lines | a small flat-mesh core in their place; changes what the build runs, so the garment thread decides and BUILD_VERSION moves |
| the old sim backend: cloth_job and blender_cloth keep cloth.place, cloth._build and cloth_made | not measured | zozo_hang uses cloth_job for job plumbing only: split that off |

After the first three cuts about 29k of the 45k lines in the old clothes modules are still reached by the chain path:
the draft tool (cloth.mesh, pieces, Body), the export (garment_game), the gates (cloth_check), pattern.py, tailor.py.
The earlier estimate of 33k deletable lines was by module import, not by function, and was too high.

## Tool (not in the repo): /mnt/data/hifipushie/deadcode/
dead.py (what the tools reach, function by function), why.py (why a symbol is live), frontier.py (links from live code
into the old modules), hyp.py (what a cut would free), apply.py (delete and keep imports consistent), check.py (source
and tests against main). Conservative: a class is kept whole, a module named in a string is kept whole.

## Also unreachable today, outside clothes (not touched)
blender_cards 446 lines, faceext 376, terrain_seams 201, flipfit 137, faceatlas 105, gnm_controls 90, blender_lashes 86.
Check blender_* by hand before deleting: Blender runs them by path.

NEXT: land legacy-cloth. Then agree new wording for the alter_pattern and pattern_check texts with the garment
coordinator and delete the seven ungated tools.
