# STATE: codify checks (hard-won rules as checks that fail loudly) -- 2026-10-19, session 1

## Current (branch worktree-agent-abd5ef7c5d758a6b3; tests: tests/test_codified.py, 16 pass + 1 skip)
| rule | where enforced | test |
|---|---|---|
| 1/2 approved head, folds <= 1 mm | asset.approved_head / fold_form_gate: ONLY on export branches (-ad08..., -a369...); coordinator merges | test_export_gates_on_the_approved_head_and_fold_form (skips until merged) |
| 3 expressions = parameter mixes | faceshapes.refuse_sculpt (env HP_SHAPE_SCULPT, face_fits.sculpt, _sculpted, teeth rest); opt-out HIFIPUSHIE_ALLOW_SHAPE_SCULPT=1 (WARNING); EXPRESSION_PRESETS["smile_tess"], expression() | test_sculpted_expression_deltas_are_refused, test_expression_presets_are_arkit_mixes |
| 4 hair budget | asset.hair_budget + budget_check (card faces vs default, drawn vs range max = FAIL -> _export raises; vertices); hair.BUDGET_UNIT "card_faces" (cards fitted to card faces) | test_hair_budget_* |
| 5 view transform (AgX vs PBR Neutral) | asset.GAME_LIGHT on export branch only (6a91c65f); no refusal anywhere | none (see NEXT) |
| 6 half-sided hair | asset.write_glb raises on a single-sided card material whose extras say no back faces | test_single_sided_cards_without_back_faces_are_refused |
| 7 proxy pose == batch pose | scratch only (/mnt/data/hifipushie/assembly/r48 test_proxy_batch.py); no repo proxy tool | SKIPPED |
| 8 reviews | reviewgate.refuse_inputs (caption band, sheet size, numbers / claims) -> bin/review(-ab) exit 5; exit 4 kept; reviewgate.majors raises ReviewNotRun | test_review_*; spikes/hair_garrett/count_review.py skips + exit 4 on a review that didn't run |
| 9 heavy memory | resources.heavy raises without gb= or kind=; asset.export_gb >= EXPORT_HUMAN_GB 24 for base/skin/hair specs | test_undeclared_heavy_job_is_refused, test_human_export_declares_24_gb |
| 10 git safety | bin/hooks/guard.py via bin/install-hooks (INSTALLED in the shared hooks dir) | test_git_guard_*, test_no_private_prefix_in_tracked_files |
| 11 doc sizes | CLAUDE.md < 8 KB, docs/state/*.md <= 60 lines | test_claude_md_under_8_kb, test_state_pages_at_most_60_lines |
| 12 validated measures | validated.known_answer + GATE_MEASURES (hair_checks x4, asset.hair_budget, budget_check) | test_gate_measures_are_validated |
| 13 incremental == cold, BUILD_VERSION | store.build; golden tests/data/build_golden.json per BUILD_VERSION | test_incremental_build_equals_cold_build, test_build_version_bumped_* |

## Hooks (shared .git/hooks: pre-commit, pre-push -> hifipushie_guard.py, a snapshot; re-run bin/install-hooks after edits)
- pre-commit: refuses workspace/ paths and files > 5 MB. pre-push: only refs/heads/main (deletes allowed); no workspace/,
  > 5 MB, private-model prefix in added lines / paths / messages. Prefixes: $HIFIPUSHIE_PRIVATE_PREFIXES or the untracked
  /mnt/data/hifipushie/private_prefixes (written this session); unknown prefixes = push refused.
- Tested on scratch commits here (workspace/ refused; branch push refused; clean main range passes), then reset.

## Tools moved into the repo (bin/): review, review-ab, approve, capped, slot (copies of /mnt/data/hifipushie/bin)
- /mnt/data paths unchanged (running agents). After merging, the coordinator runs bin/link-tools (symlinks
  /mnt/data/hifipushie/bin/<tool> -> main checkout's bin/<tool>, .bak kept). /mnt/data review / review-ab already call
  the input gate from the main checkout's src (WARNING "gate unavailable" until reviewgate.py is on main). Backups *.bak-20261019.

## Decisions in force
- Hair: role default counts card faces; drawn <= range max (hero 50k / main 20k / secondary 8k / crowd 1.5k). Coordinator 2026-10-19.
- Expressions: parameter mixes only; sculpt refused unless HIFIPUSHIE_ALLOW_SHAPE_SCULPT=1 (logged).

## NEXT
1. Rule 5: once GAME_LIGHT is on main, make face_light_check take both renders' view transforms and raise when they differ.
2. Rule 7: a repo proxy tool doesn't exist; when one lands, record the pose table hash in its output and compare to the batch's.
3. Gate measures not yet self-tested: likeness_* rows, face_ruler / eye_ruler, cloth_check, asset.face_light_check (branch),
   skin_read crop stats, spikes' tiles.py. Add each to validated.GATE_MEASURES with a known-answer test.

## History (grep only): docs/notes/audit.md "## codify checks 2026-10-19"
