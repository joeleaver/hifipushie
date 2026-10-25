# STATE: canvas (canvas / interfacing BENDING STIFFNESS; the jacket with no workaround holds) -- 2026-10-25

GOAL (Joe): canvassed pieces keep their shape by STIFFNESS so the workaround holds go. No sim, no rented GPU.
Concept SLIM-CUT, worn open, falls straight (workspace/garrett_v20/concept_v8_front_apose.png). Rules: threads first
(C195); supports, not holds (C190); styling ends with smooth + pull down.
Sessions: s1 78507629; s2 claude/canvas2; s3 claude/canvas3 ($S3); s4 claude/canvas4 ($S4 /mnt/data/hifipushie/canvas/s4;
history cloth.md "canvas stiffness session 4"). Ledger C190-C199.
S4 FOUND (t1 fit = band, W1, threads-first fit, no plumb hold; $S3 ops_ts.json = t1_fz):
- t1_fz flared because its lower fronts never DROPPED (grain already plumb, lean -2..+8 deg): style() held every
  slide / turn grip for every later op, so cfHem stayed 42 mm high and 46 mm forward of k3. C199: "let_go": true on
  pull / turn / slide; relax "keep" (hold_region kwargs for that relax only). KAT test_a_hand_lets_go. Defaults same.
- Lower fronts to plumb = let go of the slide + turn, drop the inward pull, then a HANG of the lower fronts only
  (relax {"hang": true, "keep": other pieces + fronts above break}). A straight-down pull does nothing (stops at 0);
  hanging ALL free cloth sags the jacket in (hem 438).
RUNS (concept edge 450/550/650 71/78/94, hem+30 482, front len 748; stands = ahead of body waist/-100/-200/-300 L):
| s1_k3 (holds) | 59-64 / 72-74 / 95-97 | 480 | 748 | 31 22 28 16 | thr 8.78 (fronts 8.26) |
| t1_fz (s3) | 77-84 / 83-85 / 101-106 | 476 | 728 | 54 45 52 49 | 9.27 (7.31) |
| t1_lg let go | 64-72 / 70-78 / 93 | 474 | 730 | 61 52 60 63 | 9.05 (6.83) |
| t1_ha + hang all | 52-61 / 54-58 / 65-68 | 438 | 751 | 49 50 48 40 | 9.01 |
| t1_hb + hang lower fronts | 67-69 / 70-78 / 84-96 | 486 | 736 | 58 54 43 35 | 8.98 (6.80) |
| t1_hc = hb, hang 4000 ($S4/ops_hc.json) | 66-69 / 77-79 / 84-97 | 484 | 737 | 57 56 45 24 | 9.05 (6.83) |
SHOW-THROUGH: not C197. gap.py: fit_t1 at styling START has 46 / 37 % of the chest's front vertices behind the shirt
(fit_s1 12 / 8 %; t1f / t2 / h2 fits 41-60 %); C197 rules off one at a time leave 26-32 % (t1_fz 29 %) and re-tear the
plain front (p99 15.5-18.2). The threads-first fit puts the chest behind the shirt.
LOOK ($S4/check/cmp_{wholefront,upper_front,side}_hb_lg_k3.png): hb beats t1_fz (fronts fall near straight, corners
no longer kick) but still loses to k3: chest show-through, front bulges forward chest -> pocket, hem rises to the front,
left lapel edge doubles. DEFAULTS NOT flipped (threads 9.05 > 8.5; show-through). No blind review (gate not met).
Suite (17 garment files + test_bending, after the last code commit): 311 passed, 4 xfailed, PYTEST_EXIT 0 ($S4/suite.log).
NEXT: (1) the threads-first fit's layer contact: the chest behind the shirt at fit time (pattern_form floor vs the
shirt in the TF fit; compare fit_s1); fix there, not in styling. (2) threads p99 9.0: the excess is outside the fronts
(fronts 6.8): find the pieces (thr.py per piece on asm_t1_hc) - likely the fit. (3) the forward bulge chest -> pocket
(stands 45-57): hang the fronts from the break down too (keep only above the roll), measure stands. (4) L 650 84 vs R
97: asymmetry from the slide (L arc 32 vs R 21 mm). (5) GP_THREAD_FIRST_ALL lapel tear (13.2): not reached. (6) then
the flip test with ops_hc in the kb open recipe (needs the shirt photo / trace rows + Tess's coat path) and the blind LOOK.
