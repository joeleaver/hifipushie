# STATE: fit_round14 (WOVEN shear energy in pattern_form's fit; Garrett open front) -- 2026-10-20. NO SIMS.

DESIGN FACT (Joe, settled): Garrett's jacket is WORN OPEN. Reviews carry "the reference jacket is worn open".

STATE: steps 1-3 done (WOVEN implemented, opt-in, OFF). Gate for default FAILS (KAT (c) and validation 2). Step 4 running.
NEXT: Garrett r14z/a/b/c (runs1.sh), table + renders + blind reviews; WOVEN stays opt-in unless step 4 changes the picture.

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
