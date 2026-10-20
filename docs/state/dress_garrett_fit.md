# STATE: dress_garrett_fit (Garrett jacket + shirt: closed form fit + ONE release sim) -- 2026-10-20, round 17

STATE: HANDOVER mid-round 17. Done: step 0 (one thread page), step 1 measure + cause (notch NOT fixed), step 2 partial
(the shirt collider ruled out). Not done: steps 3 (seam gaps) and 4 (table, renders, reviews). Spend this round $0.
NEXT: (a) notch: a METHOD change (below); (b) crossed fronts: measure front-on-front contact at the break and run one
local release with the roll line's bending rest flat, before any draft change; (c) step 3; (d) step 4.

## Method (Joe 2026-10-20)
Open jacket = the BUTTONED fit on the dress form (pattern_form.assemble, top button fastened), then ONE short release
sim (cloth_release, MCP release_garment; docs/state/cloth_release.md). No gravity substitutes on the form.

## Current candidate (nothing approved)
- Closed fit r15e: CLOSED=1 LAPEL_W=0.081 ROLL_R=0.006 $FR17/job.sh <tag> ROLL_GAP=true (25 s; gate PASS_WAIVED
  51e12aabcedf45c7251a). Rebuilt on this code as $FR17/asm_r15e.pkl (identical stretch; TRACE=1 keeps every phase).
- Released r16 (job_k, rented $0.0355): $FR16/asm_r16. $FRn = /mnt/data/hifipushie/dress_garrett/fit_round<n>.
- Target concept_v8_front_apose.png; checklist workspace/checklists/garrett_jacket.json (worn open: Joe's fact).

## Open faults (game visibility first)
1. Released fronts stay crossed: edge off CF 450/550/650 r16 0/6-19/22-37 vs 71/78/94; break x -8/+11 vs 64. Not the
   shirt (r17nu, no collider: break -9/+12, 450 still 0), not the neck hold (r16n), not the settle length (r16L).
   Flat: front balance = back (same hps + shoulder in one frame), 20 mm wrap, 23 mm cutaway.
2. Notch (Joe): gorge_lie r15e L/R twist 10.7/14.8 deg/cm, across 13/13, collar end tip 9.8/8.0 mm, end plane 30 deg
   (gate row gorge_lie FAIL; limits 10 / 15 / 6). Cause: the STAND's end stands up past the gorge seam's first ring
   (rises 7-30 mm off the lapel's plane within 22 mm of the notch), the fall on it = the tab. The fit has nothing that
   lays the stand END flat on the lapel. r16 worse (across p50 24/14).
3. Seams open 1-4 mm after the release (white lines). 4. Width (waist 320 vs 401), boxy square shoulder.
5. Lapel edge no thickness contrast; pocket flaps sag 16-19 mm in the release; shirt-through 251 verts (r16).

## Switches (module default; candidate)
pattern_form: ROLL_GAP False (r15e on) | ROLL_TURN False | CHEST_HOLD 0 | OPEN_HOLD False | HOLD_SLEEVES False |
HOLD_NAMED True | OPEN_HANG True | WORN_EDGE False | EDGE_FIELD True | HANG_FREE True | SWING_UNPINNED True |
WOVEN False | PRESS_CARRIES_LAYERS False (r17: fall carried with the laid stand; final unchanged) |
BASE_ACROSS_PRESSED False (r17: dead lever) | PRESSED_W 1 (4: across 12 -> 10, tip same). cloth.PAD_DRAFT False.
Release job: zozo start_over 0.06.

## Dead ends (one line each)
- Gravity substitutes on the form (WORN_EDGE, OPEN_HOLD above the break, ROLL_TURN + CHEST_HOLD tear).
- Release: neck unheld / 6 s settle / no shirt collider: break unchanged.
- Notch: more press weight, the fall's base onto the lapel, carrying the fall at the press: the stand still stands.
- round 16 notch.py (counted the surface bend, the roll, the in-plane gap): use pattern_form.gorge_lie.

## Commands ($FR17)
job.sh (fit), gorge.py <asm..> [--phases] [--along], layers.py / tip.py (collar end per phase / per vertex),
g17.py build <tag> [under=none hold= zozo=] + zrun.py <job>/sim (local, RUNNER=bin/capped) + mk17.py <job> <asm>,
m10: $FR13/m10.py concept <asm..>; render17.py <asm> <tag> [views] (notch crops framed on each side's own notch).

## History (grep only)
docs/notes/cloth.md "fit round 17", "fit rounds 1-16 STATE pages, archived", "cloth_release".
