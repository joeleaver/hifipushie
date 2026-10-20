# STATE: fit_round11 (Garrett jacket: Joe's break notch, lapel tops, front crease; then round 10's questions) -- 2026-10-19. NO SIMS.

STATE: step 1 done (break notch fixed: EDGE_FIELD, C56, gate row front_edge_break). Candidate r11a = r10i + EDGE_FIELD.
NEXT: 1b lapel tops embedded in the layer below (count turned-lapel vertices under their base / inside the shirt by band,
gorge -> break; crops lapeltop.{L,R}); 1c the vertical crease down the front below the break (dihedral along the panel,
fold rows in the flat; panel.{L,R} crops); then 2a OPEN_HOLD A/B, 2b suppression style + body check + shoulders, 2c hem
492 -> 448 + corner flicks, 3 lapel turn / press, 4 re-measure + renders + blind reviews.

## Causes
- Break notch (Joe): flat clean (step 0); on the form _swing_open meets only the LAST worn-open point (cfHem), the break
  landed ~50 vs 64; worn_open_edge held the edge at its swung x while the break's pin dragged one vertex 7-9 mm out.
  Fix: pattern_form.EDGE_FIELD (edge targets carry the points' corrections). Known answer
  test_open_front_edge_has_no_step_at_the_break. r11a: step 1.6/1.4 mm (r10i 6.9/8.4), break 64.0 both.

## Files
$FR11 = /mnt/data/hifipushie/dress_garrett/fit_round11/ (run.sh = this worktree): fr10.py, harness10.py (OUT = fr11),
brk.py (edge plot), brkm.py (edge_through_break flat + fitted), crops.py (break / lapeltop / panel ref | clay | diag),
render10.py, review10.sh, m10.py, silrows.py. r11a: WORN='{"break": 0.064, "cfHem": 0.096}' SLEEVE_OVER=391
LAPEL_W=0.095 RUNNER=bin/capped run.sh harness10.py r11a base WORN_EDGE=true OPEN_HOLD=true
