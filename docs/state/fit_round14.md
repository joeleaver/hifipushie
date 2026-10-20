# STATE: fit_round14 (WOVEN shear energy in pattern_form's fit; Garrett open front) -- 2026-10-20. NO SIMS.

DESIGN FACT (Joe, settled): Garrett's jacket is WORN OPEN. Reviews carry "the reference jacket is worn open".

STATE: HANDOVER. Steps 1-4 done. WOVEN stays OPT-IN (fails KAT (c) and validation 2); the open-front method
(ROLL_TURN + CHEST_HOLD + WOVEN, r14b) is TORN on Garrett and fails all three blind reviews: NOT default. Candidate stays r13b.
NEXT: (1) coordinator: take or drop the hem pin on cutawayTop (r14a: waist 335 -> 373, hem sweep 443 -> 494, but the L
corner curves back 82 vs the concept's 29 and the front crease sharp_mm 73 -> 181); (2) the open-front fault is NOT shear:
the front between the held chest and the moved roll line needs WEFT length change (KAT: +-30 % weft across the roll line);
the next lever is the turn field / hold geometry (where the roll line goes), not the cloth energy; (3) queued items from round 13.

## The energy (pattern_form.WOVEN, opt-in; FIT unchanged when off)
Per FIT triangle (off fold rows; made pieces stay ARAP; WOVEN_FLAPS: lapel flaps too) F = [f_u f_v] in the piece's GRAIN
frame (piece["grain"], 90 = warp along y; undercollar 45 = bias). Local step (projective dynamics): target
(P_s + s P_r) / (1 + s), P_s = unit warp / weft at any angle (stretch-free, sheared), P_r = nearest rotation. Each edge's
target = mean of its triangles' T e; global step = the same sparse system. Bending unchanged.
s = SHEAR_STIFF = 0.0111 from KES-F suiting: G 0.75 gf/cm/deg (0.6-0.9), EMT 6.4 % at Fm 500 gf/cm -> G/E 0.0055,
s/(1+s) = 2G/E. Info rows grain_stretch_pct (stretch ALONG the grain) + shear_deg. WOVEN_SLACK (compression-free) A/B only.

## Step 1 tests (tests/test_pattern_form.py)
(a) KAT test_woven_shear_costs_its_sourced_share_of_a_stretch PASS (1 %: shear/stretch 0.00550 = G/E on grain 90/45/0;
    warp/weft 2 % = (1+s) eps^2; a bias piece's frame turns with its grain). The brief's "20 deg < 5 % of 2 %" is xfail:
    KES-F gives 1.67 x (no source for 5 %).
(b) test_woven_fit_shears_a_held_sheet_instead_of_stretching PASS (free sheet placed 20 deg sheared: FIT 0.0, WOVEN 12.2 deg).
(c) test_open_front_turns_its_lapel_not_its_chest STILL XFAIL with WOVEN: chest 0 drift / 6 mm stand OK, break 49, but
    lapels 26 / 40 % through base (66 / 90 off), turn 143 / 150 (needs 160), grain stretch p99 12.6 %. Cause (kat_diag.py):
    the base strip along the roll line crumples in the WEFT (+-30 %), between the pressed row and the held chest; not shear.
(d) WOVEN off: 31 pass, 2 xfail (unchanged). WOVEN on: 3 fail, all on EDGE strain (shear changes diagonal edge lengths):
    diagonal_fold_170 (edge 11.4 % vs 0.5), two_panel_sleeve (girth/aspect pass, edge p99 22.5 % vs 6), open_front_hangs
    (side-seam test's stretch 0.144 vs 0.03).

## Step 3 validation 2 (val2.sh, current code; tol in val2.py)
| row | sim | WOVEN off | WOVEN on |
| passes | | 12/16 | 9/16 |
| shoulder / waist / hem sweep | 465/400/460 | +3.2 F/-2.8/+0.5 | -2.0/-6.1 F/-2.8 |
| sleeve opening / hem edge mm | 108.5/242 | -1.8/-5.1 | -5.5 F/+11.5 F |
| body length t | 0.428 | -0.003 | -0.031 F |
| open chest / hips mm | 65/75 | -8/-20.5 F | +1.5/-30.5 F |
| back standoff / collar CB | 23.1/22.4 | +25 F/+5.5 F | +15 F/+5.4 F |
| bias shear p50/p90/p99 deg (simshear.py) | 0.0/0.7/4.6 | 0.6/3.0/11.2 | 4.8/14.8/25.4 |
| fit time (shirt + jacket) | | 22 s | 38 s |
Gate: WOVEN moves the form FURTHER from the sim -> not default. The sim barely shears; WOVEN lets the seat's attraction
wrap the cloth by shear (waist / length / sleeve opening shrink).

## Files ($FR14 = /mnt/data/hifipushie/dress_garrett/fit_round14)
run.sh / job.sh / harness14.py (code-keyed, C49) / fr14.py (worn-open hem pin on cutawayTop); runs1.sh; val2.sh;
kat_diag.py; simshear.py; pf_tests.py (pytest with WOVEN 0/1); tests_{off,on}.log; val2_r14{off,on}.log.

## Step 4 Garrett ($FR14 meas_r14.log; r14z closed ref; WORN break 64 + cutawayTop 96 for r14*; r13b pinned cfHem 96)
| item | concept | r13b | r14a hem pin | r14b ROLL+CHEST+WOVEN | r14c ROLL+CHEST |
| chest drift p90 L/R mm | - | 49 / 54 | 61 / 63 | 23 / 23 | 4 / 4 |
| lapel through base L/R | 0 | 0.15 / 0.10 | 0.15 / 0.13 | 0.01 / 0.02 | 0.32 / 0.32 |
| front crease interior max / sharp mm | smooth | 49 / 73 | 73 / 181 | 88 / 498 | 172 / 528 |
| break below HPS | 386 | 361 | 358 | 276 / 281 | 299 / 297 |
| sleeves shirt-through L/R | 0 | 23 / 31 | 25 / 30 | 5 / 4 | 13 / 16 |
| edge stretch p99 / max % | - | 13.5 / 68 | 13.8 / 78 | 82 / 388 | 72 / 351 |
| grain stretch p99 / max %; tris > 10 % on fronts | - | | 17 / 77; 197 | 174 / 479; 842 | 161 / 361; 1108 |
| bias shear p50/p90/p99 deg | | | 0.8/3.6/13.6 | 4.6/25.4/55.3 | 1.1/5.5/35.3 |
| edge below 450 / 550 / 650 | 71/78/94 | 66/73/77 | 80/98/104 | 93/101/122 | 63/96/103 (L) |
| opening half 350 | - | 64 | 65 | 6 | 11 |
| corner top / curve-back L | 704 / 29 | 690 / 30 | 680 / 82 | 650 / 47 | 700 / 83 |
| waist width / hem sweep | 401 / 478 | 335 / 443 | 373 / 494 | 312 / 479 | 317 / 423 |
| torso width 600 / 700 | 455 / 476 | 453 / 443 | 474 / 483 | 447 / 458 | 421 / 425 |
| front length | 748 | 748 | 739 | 717 | 748 |
| fit time (jacket + shirt) | | 37 s | 40 s | 56 s | 34 s |
r14b: the break rides up 85 mm, the fronts meet at the sternum and flare below (peplum), the fronts tear (grain p99 174 %).
Renders check/ (r14b): wholefront / front / three / side / back (ref | clay | diag), crops break / lapeltop / panel /
hemcorner / shoulder per side. Blind reviews (review14.sh, "the reference jacket is worn open"): wholefront FAIL (opening
meets at the sternum + inverted V, no lapels / break, peplum flare, ragged hem, crumpled edges), front FAIL, three FAIL
(funnel collar, no lapel / notch, shirt collar a band).
