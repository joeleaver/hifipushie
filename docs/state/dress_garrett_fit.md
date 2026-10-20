# STATE: dress_garrett_fit (Garrett jacket + shirt: closed form fit + ONE release sim) -- 2026-10-20, round 19

STATE: round 19 step 1 done: folds run_off (general; KAT) + R28 on -> r19a: gorge_lie across 11.9/9.5, tip 1.4/5.2,
plane 3.8/13.5 PASS (the flat end no longer folds back); twist 14.2/20.1 still FAILS (the LAPEL's roll at the gorge,
60-94 mm from cfNeck). R28 stays opt-in; r19a = candidate. Joe 2026-10-20: the concept's opening (edge off CF 71/78/94,
break x 64) is reached by ARRANGING the jacket (soft pins + settle), never by fit levers or the pattern.
NEXT: step 3 seam weld in cloth_release, then arrangement, then step 4 table / renders / blind reviews.

## Method (Joe 2026-10-20)
Open jacket = the BUTTONED fit on the dress form (pattern_form.assemble, top button fastened), then ONE short release
sim (cloth_release, MCP release_garment; docs/state/cloth_release.md). No gravity substitutes on the form.

## Current candidate (nothing approved)
- Closed fit r15e: CLOSED=1 LAPEL_W=0.081 ROLL_R=0.006 $FR18/job.sh <tag> ROLL_GAP=true (gate PASS_WAIVED
  51e12aabcedf45c7251a); $FR17/asm_r15e.pkl. Released r16 (job_k, rented $0.0355): $FR16/asm_r16.
  $FRn = /mnt/data/hifipushie/dress_garrett/fit_round<n> ($FR18/run.sh runs THIS worktree's code; absolute paths only).
- Target concept_v8_front_apose.png; checklist workspace/checklists/garrett_jacket.json (worn open: Joe's fact).

## Open faults (game visibility first)
1. Released fronts stay crossed: edge off CF 450/550/650 r16 0/6-19/22-37 vs 71/78/94; break x -8/+11 vs 64. Not the
   shirt, neck hold or settle length (r17). Draft: front balance = back (same hps + shoulder), one shoulder slope,
   20 mm wrap. History: 40 mm front balance (crest hps, j10-j13) made the open fronts SWING APART (+48 mm armhole
   asymmetry); 20 mm (garment_kb) levelled the hem but bunched the sleeves. FreeSewing Brian/Jaeger: one frame, one
   slope (no balance). R5: front 1-2 deg steeper in practice.
2. Notch (Joe): r15e gorge_lie twist 10.7/14.8 deg/cm, across 13/13, tip 9.8/8.0 mm (limits 10/15/6) FAIL. Cause
   (r17): the stand stood to the notch. R28 (stand runs off at s_x, the lapel roll's gorge crossing, ~100 mm before the
   end) fixes the flat (collar_stand_end 3 mm vs 15) but on the form r18a is WORSE (tip 12/14, across 19/54, plane
   58/73): band_init lies right (tip 2/4 mm), turn_flaps folds the end back over the lapel: the fall's crease
   still runs to the end.
   r18: FB 20 mm (fr18.py FB=0.02, release job_fb20nu) 450/550/650 0/0, 20/20, 49/56, break -9/+12; friction 0
   (job_nuf0) break -8/+11: neither. With the shirt collider the FB start fails (contact starts overlapping v820).
3. Seams open after the release: seam_gaps r16 p50 1.17 max 11.8 (458/579 > 1 mm); p50 = ZOZO contact gap (0.5 mm
   gap: p50 0.56); stitch_gap 0.5 mm dead. 4. Width (waist 320 vs 401), boxy square shoulder.
5. Lapel edge no thickness contrast; pocket flaps sag 16-19 mm in the release; shirt-through 251 verts (r16).

## Switches (module default; candidate)
pattern_jacket.STAND_RUN_OFF on False (R28, opt-in) | pattern_form: ROLL_GAP False (r15e on) | ROLL_TURN False |
CHEST_HOLD 0 | OPEN_HOLD False | HOLD_SLEEVES False | HOLD_NAMED True | OPEN_HANG True | WORN_EDGE False |
EDGE_FIELD True | HANG_FREE True | SWING_UNPINNED True | WOVEN False | PRESS_CARRIES_LAYERS False |
BASE_ACROSS_PRESSED False | PRESSED_W 1. cloth.PAD_DRAFT False. Release job: zozo start_over 0.06.

## Dead ends (one line each)
- Gravity substitutes on the form (WORN_EDGE, OPEN_HOLD above the break, ROLL_TURN + CHEST_HOLD tear).
- Release: neck unheld / 6 s settle / no shirt collider: break unchanged.
- Notch: more press weight, the fall's base onto the lapel, carrying the fall at the press; R28 alone (fall still folded).

## Commands ($FR18)
job.sh (fit; FB= front balance via fr18.py), gorge.py <asm..> [--phases], runoff_flat.py (R28 flat rows), seams.py,
g17.py build <tag> [placed= asm= under=none hold= zozo=] + zrun.py <job>/sim (HP_RUN_ZOZO=1 RUNNER=bin/capped) +
mk17.py <job> <tag> <base asm>, m10: $FR13/m10.py concept <asm..>.

## History (grep only)
docs/notes/cloth.md "fit round 18", "fit round 17", "fit rounds 1-16 STATE pages, archived", "cloth_release".
