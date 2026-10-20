# STATE: fit_round12 (Garrett jacket: lapel-turn method, then torso / hem corner / lapel read) -- 2026-10-20. NO SIMS.

STATE: step 1 DONE as a stop-loss (method infeasible on an isometric fit); 2b / 2c next, then renders + reviews.
Candidate stays r11d's settings (r12 code with ROLL_TURN / CHEST_HOLD off = r11d).
NEXT: 2b torso (bare-body row profile vs concept minus ease; suppression as an R8 style param; shoulder width), 2c hem
cutaway (draft rule), 3 lapel read, 4 renders + blind reviews. 2a (open vs closed A/B) is moot until the method lands.
NEXT ROUND (coordinator: its own round, opt-in, don't start here): WOVEN SHEAR ENERGY in pattern_form's fit.
- Energy: per triangle, the deformation gradient in the pattern's grain frame (u = weft, v = warp, from M["uv"]):
  F = [f_u f_v] (3x2). Warp / weft stretch (|f_u| - 1, |f_v| - 1) at FIT_STIFF (stiff, as now); shear
  gamma = f_u . f_v / (|f_u||f_v|) at SHEAR_STIFF = a small fraction (woven wool: shear rigidity G ~ 0.5-1 gf/cm/deg
  (Kawabata KES-F) vs tensile, i.e. ~1-5 %); bending unchanged (Bergou).
- Where it plugs in: assemble's local-global relax. Today the local step fits a rotation per one-ring cell (ARAP on
  folds / made pieces) or an edge at its rest length along its current direction (FIT isometry, every triangle edge:
  shear-stiff). New local step for FIT cells: per triangle, project F to the nearest (R x [[1, g], [0, 1]]-family)
  target with g clamped / penalised by SHEAR_STIFF (ARAP-style "as-rigid-as-possible up to shear"), global step
  unchanged (the same sparse system, triangle-gradient rows instead of edge rows). Flag WOVEN (opt-in), FIT unchanged.
- Tests: (1) known answer test_open_front_turns_its_lapel_not_its_chest (xfail now): the lapel tube, chest held
  (ROLL_TURN + CHEST_HOLD), break 50 mm out by shear, no bulge (chest stand <= 8 mm), lapel on its base, p99 < 5 %;
  (2) a pure-shear sheet: a square sheared 20 deg costs < 5 % of a 2 % stretch; (3) the two-panel sleeve and every
  pattern_form KAT unchanged; (4) re-run validation 2 ($PF/v2/val2.py vs frozen_ae V_sim, 16 rows) before any default.

## Step 1 (method), measured (chest.py: chest = front above the break, off the flap, >= 40 mm from the roll line)
| run | chest drift p90 L/R mm | lapel through base L/R | break step mm | shirt sleeves out L/R | stretch p99 |
| r12c closed default | 0 / 0 (stand 28/36 p50/p90) | 0 / 0 | 1.7 / 1.7 | 10 / 13 | 9.7 |
| r11d (R11 candidate) | 62 / 56 | 13 / 12 % | 1.7 / 1.4 | 29 / 32 | 13.7 |
| r12a ROLL_TURN start | 52 / 54 | 9 / 23 % | 0.7 / 0.5 | 23 / 31 | 10.6 |
| r12b + HOLD_SLEEVES | 52 / 54 | 22 / 27 % | 0.8 / 0.6 | 18 / 19 | 10.3 |
| r12d + CHEST_HOLD | (torn) | | | | 73.9 (max 353) |
Tube KAT: start field alone drift 34 mm (rigid 35); + CHEST_HOLD drift 0, stand 6 mm, lapels 66/90 % through, p99 13 %.
Cause: an inextensible, shear-stiff front cannot open its break with chest + side held (tube: the arc break -> side
52 mm shorter than the cloth). C59. Holds NOT retired (nothing replaces them yet).

## Files
$FR12 = /mnt/data/hifipushie/dress_garrett/fit_round12/ (run.sh = this worktree; job.sh <tag> [overrides] = fit +
chest + thru; harness10.py CLOSED=1 = no worn-open pins). kat/rollkat.py (lapel tube sweep). asm_r12{a,b,c,d}.pkl.
