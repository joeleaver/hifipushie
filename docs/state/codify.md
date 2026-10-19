# STATE: codify (durable lessons into the repo) -- rewritten 2026-10-19, session 2 (integration). Nothing in flight.

## Current best (all on the integration branch, a fast-forward of main 59b30291; see History)
- docs/notes/codified.md: THE LEDGER, one row per durable lesson, status re-graded on the landed code.
  Totals: 105 rows: ENFORCED 25, DOC 73, CHECK-PLANNED 3, TASTE 4 (before: ENFORCED 9, ENFORCED-BRANCH 4,
  CHECK-PLANNED 8, DOC 80, TASTE 4). No ENFORCED-BRANCH rows left.
- docs/notes/character_recipe.md (stage-order recipe), docs/notes/traps.md (symptom -> cause), CLAUDE.md pointer.
- Checks (tests/test_codified.py, 20 pass, none skip): approved head + fold form (asset.approved_head,
  fold_form_gate, FOLD_FORM_MAX_MM), sculpt refusal + EXPRESSION_PRESETS, hair budget in card faces
  (hair.BUDGET_UNIT, card_allowance, asset.hair_budget), single-sided cards need back faces, review input gate
  (reviewgate), heavy-job declaration, git guard hooks, doc sizes, incremental == cold, gate-measure self-tests.
- Rule 5 (new): asset.same_view / game_light_view / MixedViewTransform; scene.look and asset.preview refuse the game
  rig (GAME_LIGHT lights) under any view but its own; face_light_check(..., views=(stage, shipped)) is REQUIRED and
  raises on a mix. Test: test_mixed_view_transforms_are_refused.
- Rule 12 (new): known-answer self-tests for asset.face_light_check and cloth_check.seams (validated.GATE_MEASURES).
- Hooks: shared .git/hooks == bin/hooks/guard.py (checked; no reinstall needed).

## Open items (by impact on the next character)
1. main ref not moved: main is checked out in the main checkout, which an isolated worker can't touch. Coordinator:
   in the main checkout, `git merge --ff-only <integration head>` (fast-forward, no rewrite), then bin/link-tools.
2. Gate measures still without a self-test: likeness_* rows, face_ruler / eye_ruler, skin_read crop stats,
   spikes' tiles.py. Add each to validated.GATE_MEASURES with a known-answer test.
3. Renders don't carry their view transform in the PNG: scripts comparing files must pass views= themselves.
   Next step if it bites: write the view into the PNG text chunk in blender_scene / blender_game and read it back.
4. Rule 7 (proxy pose == batch pose): no repo proxy tool yet; ledger E10 stays CHECK-PLANNED.
5. Hair STATE pages (tess_hair, garrett_hair) still describe the old drawn-to-default fit; rewrite on next hair session.
6. hair_clumps.FILL vs ARCH_FILL (ledger A11): rename to BAKE_FILL, warn in HP_FS_SET.
7. tests/test_skin.py::test_features_and_shader_budget fails on main 59b30291 too (skin:wrinkle_folds carries a
   per-pixel noise mask): pre-existing, not from this landing; skin thread owns it.

## Decisions in force
- ENFORCED only when code refuses / a test fails, verified by grep on the landed tree; a default or warning is DOC.
- Hair: the role default counts card faces; drawn <= the range max (and the tier's drawn max when it names one).
- Colour is compared under one view transform; the game rig only under Khronos PBR Neutral.
- No private-head names, codes or relations in any of these files.

## Dead ends
- (none)

## Commands
- `uv run python -m pytest -q tests/test_codified.py` (under /mnt/data/hifipushie/bin/slot).
- Verify a claim: `grep -n <name> src/hifipushie/*.py tests/*.py`.
- Size: `wc -c CLAUDE.md` (< 8192); `wc -l docs/state/*.md` (<= 60 each).

## History
- Landed as squashes: ledger / recipe / traps; codify checks; Tess assembly export gates; Garrett assembly
  (game light, face-light check, push-under, hair allowance); then rule 5 + rule 12. Notes: grep audit.md "codify".
NEXT: coordinator fast-forwards main and runs bin/link-tools; then items 2-6.
