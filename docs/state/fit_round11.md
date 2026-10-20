# STATE: fit_round11 (Garrett jacket: Joe's break notch, lapel tops, front crease; then round 10's questions) -- 2026-10-19. NO SIMS.

STATE: steps 1, 1b, 1c done. Candidate r11d = r10i + EDGE_FIELD (C56) + HOLD_NAMED (C57) + HANG_FREE (C58).
Gate rows: front_edge_break PASS; lapel_on_base FAIL (12 %, limit 5); front_crease FAIL (dart median 33/21, limit 20).
NEXT: 4 renders + blind reviews of r11d; then 2a OPEN_HOLD A/B, 2b suppression style + body check + shoulders,
3 lapel turn / press.

## Causes
- Break notch (Joe): flat clean (step 0); on the form _swing_open meets only the LAST worn-open point (cfHem), the break
  landed ~50 vs 64; worn_open_edge held the edge at its swung x while the break's pin dragged one vertex 7-9 mm out.
  Fix: pattern_form.EDGE_FIELD (edge targets carry the points' corrections). Known answer
  test_open_front_edge_has_no_step_at_the_break. r11a: step 1.6/1.4 mm (r10i 6.9/8.4), break 64.0 both.

- Lapel tops (Joe): the hold's height came from the edge pins (roll line to the neck): shoulder / neck seams held CLOSED
  under the turned lapel. HOLD_NAMED: through-base 40-120 mm L 129 -> 42, R 125 -> 44 (r11c). KAT
  test_open_hold_stops_at_the_break_not_the_roll_top. Residual 8-12 % past the hinge: open.
- Front crease (Joe): the FRONT DART seam, dihedral median 73 deg (r6 closed 8): open edge + held side seams + the
  panel drawn onto the waist fold the slack at the dart. HANG_FREE (no seat attraction below the break on a worn-open
  piece): 33 / 21 deg; hem 449 -> 498 P. Residual: open (OPEN_HOLD A/B, 2a).

## Files
$FR11 = /mnt/data/hifipushie/dress_garrett/fit_round11/ (run.sh = this worktree): fr10.py, harness10.py (OUT = fr11),
brk.py (edge plot), brkm.py (edge_through_break flat + fitted), crops.py (break / lapeltop / panel ref | clay | diag), lapelemb.py, lapelab.py, crease.py, seamcrease.py, creasemap.py,
render10.py, review10.sh, m10.py, silrows.py. r11a: WORN='{"break": 0.064, "cfHem": 0.096}' SLEEVE_OVER=391
LAPEL_W=0.095 RUNNER=bin/capped run.sh harness10.py r11a base WORN_EDGE=true OPEN_HOLD=true
