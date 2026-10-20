# STATE: dress_garrett_fit (Garrett jacket + shirt: closed form fit + ONE release sim) -- 2026-10-20, round 19

STATE: round 19 done (budget). Step 1: folds run_off (general, KAT) + R28 -> r19a: gorge across/tip PASS (11.9/9.5,
1.4/5.2), twist 14/20 FAILS (the LAPEL's roll at the gorge, 60-94 mm from cfNeck); R28 stays opt-in. Step 2 skipped
(Joe: physics alone won't open it; arrangement instead). Step 3: weld_seams (545/581 welded; 36 real openings, all at
the neck/HPS: held stand vs free bodice). Step 4: local release r19rel -> welded r19w; table, renders, 3 blind reviews
(all FAIL: closed-looking fronts, collar standing up the neck, narrow lapels, shirt poke-through, boxy shoulders).
Spend this round $0 (local ZOZO only). Nothing approved, nothing for Joe as a result.
NEXT: (1) arrangement tool (arrange_garment: soft pins moved to the concept's edge rows 71/78/94 @ 450/550/650, break
x 64, short settle with the shirt + gravity, pins released, springback reported) -- runner needs a pin move_to /
unpin stage (cloth_zozo carryPoses already uses g.pin().move_to); (2) neck openings: the held neck pieces vs the
settling bodice (release only the hold after the sew phase, or hold the bodice's neck ring with them); (3) the collar
standing up the neck (all 3 reviews MAJOR) + lapel twist at the gorge; (4) shirt poke-through at waist sides /
shoulder tips.

## Method (Joe 2026-10-20)
Open jacket = the BUTTONED fit on the dress form (pattern_form.assemble, top button fastened), then ONE short release
sim (cloth_release, MCP release_garment; docs/state/cloth_release.md). No gravity substitutes on the form.
The concept's opening (edge off CF 71/78/94 at 450/550/650, break x 64, V width 237) stays the TARGET, reached by
ARRANGING the jacket by hand (soft pins + settle, as a person settles a coat), never by fit levers or the pattern
(Joe 2026-10-20; checklist rows opening_arranged, no_front_through_front, break_height, fronts_hang_no_lift).

## Current candidate (nothing approved)
- Fit r19a: CLOSED=1 LAPEL_W=0.081 ROLL_R=0.006 $FR19/job.sh r19a ROLL_GAP=true 'pj.STAND_RUN_OFF={"on": true,
  "end": 0.003, "over": 0.03}' (placed_8ba6d38b12cd; NO pattern gate record for this pattern yet). Release: g17.py
  build r19a + zrun.py (local) + mk17.py -> asm_r19rel; weld (tab19.py) -> $FR19/asm_r19w.pkl.
  $FRn = /mnt/data/hifipushie/dress_garrett/fit_round<n> ($FR19/run.sh runs THIS worktree's code).

## Table (concept | r15e fit | r16 release | r19w release+weld; L/R)
edge off CF 450/550/650: 71/66, 78/72, 94/85 | 0/0, 0/0, 6/4 | 0/0, 6/19, 22/37 | 0/0, 17/18, 34/35
break x / below HPS: 64 / 386 | -15,+15 / 326 | -8,+11 / 325 | -8,+11 / 328 ; V width 200: 237 | 149 | 151 | 149
lapel outer 150: 127/134 | 110/100 | 108/102 | 107/101 ; waist 401 | 324 | 320 | 321 ; hem 478 | 431 | 447 | 457 P
gorge twist/across/tip L;R: lim 10/15/6 | 10.7/13/9.8; 14.8/13/8.0 | 12.1/33/10.8; 13/24/7.8 | 10.8/12.5/5.3; 13.9/20/2.1
seam_gaps max (open>1mm): r15e 0.03 (0) | r16 11.8 (458) | r19rel 12.0 (461) | r19w 12.0 (36). stretch p99 9.7|6.1|7.4 %.
front.L|front.R crossing pair present in all four (the closed fit's overlap carried into every release).

## Open faults (game visibility first)
1. Opening: to be ARRANGED (above). 2. Collar stands up the neck like a band (reviews: all MAJOR). 3. Lapels narrow,
gorge twist (lapel roll). 4. Shirt poke-through (waist sides, shoulder tips). 5. Neck seam openings 5-12 mm at HPS.
6. Waist 321 vs 401 / pinched waist + flared skirt; boxy square shoulder; thick front-edge ridge.

## Switches (module default; candidate)
pattern_jacket.STAND_RUN_OFF on False, over 0.03 (R28 + crease run-off; candidate on) | pattern_form: ROLL_GAP False
(candidate on) | others as round 18 (ROLL_TURN False, CHEST_HOLD 0, OPEN_HOLD False, HOLD_NAMED True, OPEN_HANG True,
EDGE_FIELD True, HANG_FREE True, SWING_UNPINNED True, WOVEN False, PRESSED_W 1). Release: zozo start_over 0.06.

## Dead ends (one line each)
- Gravity substitutes on the form; release neck unheld / 6 s settle / no shirt / front balance 20 mm / friction 0.
- Notch: more press weight, fall base onto lapel, R28 without the crease run-off, longer crease fade (0.06: dead).

## Commands ($FR19)
job.sh, gorge.py <asm> [--phases|--along], g17.py build <tag> placed= asm= zozo=, zrun.py <job>/sim (HP_RUN_ZOZO=1
RUNNER=bin/capped), mk17.py <job> <tag> <base asm>, tab19.py (weld + rows), m10: $FR13/m10.py concept <asm..>,
render17.py <asm> <tag> <views> (RUNNER=bin/capped), bin/review (reviews in check/rv_*).

## History (grep only)
docs/notes/cloth.md "fit round 19", "fit round 18", "fit round 17", "cloth_release".
