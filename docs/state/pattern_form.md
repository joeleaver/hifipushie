# STATE: pattern_form (virtual fit) -- 2026-10-19, branch pattern-form-validate2 (pattern-form-fit + garrett-muslin1). NO SIMS.

## What it is
pattern_form.assemble = the garment's FIT from its pattern (no sim). Joe: "We shouldn't need a sim to drape it."
Scripts: $PF = /mnt/data/hifipushie/pattern_form; validation 2 in $PF/v2 (env2.sh runs this worktree's code):
val2.py (the 16-row validation, `record` writes validation.json), open1.py (opening per stage), shoulder.py, cap.py,
hemback.py, refcheck.py (reference check), look2.py (pairs + sheet). History: docs/notes/cloth.md "virtual fit".

## Relax (validation 1, proven): FIT = edge isometry + Bergou bending on the sewn surface (KAT two-panel sleeve on the arm).

## Reference (validation 2): frozen_ae's RAW SIM, res["V_sim"], not res["V"]
V is hand work (closure step mirrored the L hem, sculpt moved hps 17 mm): face strain p99 74 % vs V_sim 9.4 %; the strain
measure itself is right (V_sim edge p50 0.1 %). Read the R front where the sim is asymmetric (its L hem rode up). C35.

## Validation ($PF/validation.json = v2/val2_final.json): 12 of 16 PASS -> form_validated() False
PASS waist -2.7 %, hem sweep +1.3, sleeve opening -1.8, forearm girth -0.9 / aspect +0.10, hem girth (f 0.85) -1.8 /
aspect +0.06, sleeve hem edge -5 mm, body length t -0.003, opening break +1 / waist +3.5 mm, collar CB +2.1 mm.
FAIL shoulder width +3.2 % (tol 3), opening chest -10.5 / hips -19.5 mm (tol 10), back standoff +26 mm (tol 10).

## Causes found (each isolated; stop-loss where noted)
1 Opening: the first relax ran with the worn-open pins, so the swing turned 0 deg. FIXED (SWING_UNPINNED): hips 49 -> 55,
  chest 50 -> 55. Remaining: the seat's attraction draws the swung front back onto the body (hips swung 72 -> 43 seated).
  WORN_EDGE (front edge pinned at its swung x) opens it to within 8 mm but slides the fronts sideways (hem sweep +23 %):
  opt-in, OFF. EDGE_FREE / SWING_BELOW: no effect. Stop-loss.
2 Shoulder / sleeve head: the declared support (sleeve_head) is already on the form's body (same body as the sim).
  details.shoulder "pad_and_head" but NO shoulder_pad declared: PATTERN item -> tailoring agent. Cap ease isn't bunched
  as strain; the cap stands 7 mm off the arm with 2x the ridges and juts 27 mm past the shoulder point where the sim
  drops: no weight. SEAT_GRAVITY small gain, HANG (constant pull) went through the arm. Stop-loss; HANG = 0.
3 Back: SHAPE differs, stands 35-52 mm off at the small of the back vs the sim's 16-27 (blades and seat agree). Not
  bending (FIT_BEND 0.3 no change): the slack the sim drops into folds stays as a smooth bridge. No fake folds.
4 Sleeve hem girth -4.6 % was a measure artefact (the f 0.9 plane cut the form's hem edge, 5 mm higher): f 0.85 -1.8 %.
Missing physics behind 1-3: the cloth's weight with real contact (a weight term needs contact as a hard constraint, not
the proximal push, or it pierces).

## Gate
garrett-muslin1 merged: form rows INFO until validated. The gate reads cloth_check.form_validated() = FORM_VALIDATED
(override) or pattern_form.form_validated() (VALIDATED flag AND a passing record). C37, test in test_pattern_gate.py.

## LOOK ($PF/look_v2final: 3m/, 1m/ pair_{clay,construction,strain}_<view>.png; diag_sheet.png)
diag_render.look_pairs makes clay + construction + strain pairs per view BY DEFAULT (C36). Review $PF/review_v2final:
FAIL: shirt through both upper sleeves (magenta; the form's shirt sleeve 393 mm round at the biceps vs the jacket's 378),
shoulder / upper-back +10 % band, fronts cling and pull in at the hem (sim hangs straight), square shoulder corner.

## NEXT
1. Weight with contact (a static fit under gravity): the one lever behind opening, cap and back. Prove it on the KATs.
2. Shirt under the jacket on the form: press the shirt sleeve (PRESS_UNDER) -> magenta at the upper arm.
3. Shoulder / yoke +10 % band (pins vs isometry at the neck point). 4. Tailoring agent: declare shoulder_pad.
5. Re-run v2/val2.py ... record; set VALIDATED only from a passing record.
