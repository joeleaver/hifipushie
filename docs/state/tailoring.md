# STATE: tailoring (jacket drafting principles) -- 2026-10-19, first session. NO SIMS.

## What exists
- Principles: docs/notes/tailoring_principles.md R1-R26 (learned from FreeSewing Jaeger, MIT; our words; [G]/[J]).
- Code: src/hifipushie/pattern_jacket.py: rules(tape, button_mm) (every value sourced R<n>), ops jacket_neck (R3/R4),
  waist_suppression (R8/R10: shares CB 16 / side-back 32 / side-front 32 / dart 20 %, scaled to land on the target,
  fades out by the hip line), collar_two_piece (R16-R18: straight stand + sprung fall), jacket_pockets (R21/R22);
  jacket_ops(ops, tape, button_mm, pockets) rewrites a jacket design's ops with them. op_neckline takes signed=True.
- Gate: cloth_check.tailor_rows_for -> pattern_jacket.tailor_rows, appended to pattern_gate for jacket / coat /
  blazer: back_neck_width, back_neck_rise, waist_suppression, hips_clearance, front_dart, front_overlap,
  collar_neck_edge_straight, collar_stand_cb, collar_fall_cb, pockets (each with its rule + tolerance).
- Tests: tests/test_tailoring.py (rules are relations; the rows pass the rule draft and FAIL muslin 1's faults;
  tracks Jaeger at a small / medium / large man; skipped without Node + pack).
- freesewing_draft.mjs also prints the draft's store numbers (reductions, collar lengths, pocket sizes).

## Garrett v2 (flat, /mnt/data/hifipushie/tailoring/)
- v2.py = muslin-1 patch.spec() + jacket_ops; gate_v2.json; sheet_jacket_v2.png (beside
  /mnt/data/hifipushie/dress_garrett/muslin1/sheet_jaeger.png). Flat gate: seams PASS, truing PASS, all 10 tailor rows
  PASS. Girth (cloth.sizing): chest +8.2 %, waist +18.7 % (Jaeger +20.1), hips +4.4 % (Jaeger +4.8), seat +10.5 %.
- three.py / three.log: ours vs Jaeger at small / Garrett / large: 18 measures, all within tolerance (table in log).
- NOT a gate on the form (pattern_gate's on_form) and no LOOK review yet; nothing approved.

## Open points
- Fall spring: ours ~40 mm (full) longer outer edge, Jaeger ~0-7; books ~1-1.5 cm per half. Decide on the drape.
- Our stand is longer than Jaeger's (479 vs 341 full) because Garrett's gorge is the concept's (notch 115 below HPS).
- Flap pockets can't cross the side-front seam (op_pocket inside one piece); chest welt not on by default.
- Truing reads the fall's CB roll seam (a chain over the fold) as an end: listed in truing_corners (tooling).
- Hips read 3-6 % under Jaeger's flat hip girth (still >= hips + 4 %).

## NEXT
Coordinator: review sheet_jacket_v2.png beside sheet_jaeger.png; if accepted, dress-garrett takes jacket_ops into
its spec (design ops + alters as v2.py) and runs the form / LOOK stages. Then Tess's coat from the same rules.

## History (grep only)
docs/notes/cloth.md "tailoring 2026-10-19".
