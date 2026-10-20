# STATE: fit_round10 (Garrett jacket: silhouette big to small, sleeves, lapel width) -- 2026-10-19. NO SIMS.

STATE: HANDOVER. Candidate r10i = r9h + OPEN_HOLD (seams held at the closed fit + plumb hang, opt-in) + jacket sleeve
room (biceps_ease 0.3435 -> 0.319 after the cap rule) + lapel width 0.095. Every front-edge / roll / V / lapel-outer /
button row PASSES; the peplum is gone (side seams at the closed fit's x). Waist 343 F, hem 448 F (r10c 492 P), break
row 361 F. Blind reviews FAIL wholefront / front / three. OPEN_HOLD NOT made the default (no closed-vs-open A/B review).
NEXT: (1) the torso is ~35 mm narrow from the armpit to the waist vs the concept (396/395/405 at 350/400/450 vs ours
361/341/349) and the hem lost 30 mm to r10g's sleeve change: decide chest / waist ease from the concept's row profile
(draft lever waist_ease: 0.14 -> 0.34 moved the waist only +19 mm: girth goes to depth, CB stands 41-49 mm off);
(2) lapels don't read as a turned face (reviewers: limp strips, no crisp edge, lumpy folds at the gorge): lapel turn /
press on the chest, crisp edge; (3) queued: collar funnel + shirt collar, pockets / plackets / buttons as drafted parts.

## Causes
- Peplum (r9h): WORN_EDGE opened the fronts by the edge only; an isometric front then slides round the body. Fix
  (C53): pattern_form.open_seam_holds + worn_open_edge's plumb hang (OPEN_HOLD / OPEN_HANG); not on buttoned pieces.
  Known answer test_open_front_hangs_without_moving_its_side_seams.
- Waist pinch: the form is faithful (horizontal edges at the waist 1.00); the draft's 14 % waist ease (R8 suit
  default) makes an hourglass where the concept's torso is straight; but the whole upper torso is also narrow (not only
  the waist), and girth added at the waist goes into depth. Not fixed: open (NEXT 1).
- Shirt through the upper arms: the jacket sleeve was drafted from the bare arm (396 mm at the biceps) over a shirt
  sleeve of 391: no room for a layer. Fix (C54): width >= under + 2 pi (EASE + THICK); pattern_form.sleeve_room
  check + test_sleeve_over_a_sleeve_has_room; Garrett via fr10 SLEEVE_OVER (the spec: biceps_ease, sourced). Shirt
  sleeve vertices outside the jacket 36/45 -> 12/12 (all at the armpit join, hidden by the arm).
- Lapels narrow: op_lapel width 0.072 (checklist 70-85, M&S) vs the concept's front-view outer edge; lever check 0.085
  -> 125/123, 93/91; 0.095 -> 131/130, 97/97 (P). Sourced from the concept rows (fr10 LAPEL_W).

## Table: docs in /mnt/data/hifipushie/dress_garrett/fit_round10/checklist_r10.md (R10 column); logs m10_chain{2,3,4}.log

## Files
$FR10 = /mnt/data/hifipushie/dress_garrett/fit_round10/ (run.sh = this worktree): fr10.py (WAIST_EASE, LAPEL_W,
SLEEVE_OVER), harness10.py, m10.py, silrows.py (torso width by row vs concept), waist.py, thru.py, sleeve.py, sleevew.py,
chain1-4.sh, asm_r10{a..i}.pkl, render10.py, review10.sh, check/{wholefront,front,three}.png (ref | clay | diag),
check/{side,back}.png (clay | diag), review_*.log.
r10i: WORN='{"break": 0.064, "cfHem": 0.096}' SLEEVE_OVER=391 LAPEL_W=0.095 run.sh harness10.py r10i base
WORN_EDGE=true OPEN_HOLD=true
