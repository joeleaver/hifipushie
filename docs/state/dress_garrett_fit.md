# STATE: dress_garrett_fit (Garrett jacket + shirt: closed form fit + ONE release sim) -- 2026-10-20, round 17

STATE: round 17 step 0 (housekeeping) done: one thread page; rounds 1-16 archived in docs/notes/cloth.md
("fit rounds 1-16 STATE pages, archived"). NEXT: step 1, Joe's notch / gorge spot on r15e (validate notch.py first).

## Method (Joe 2026-10-20)
Open jacket = the BUTTONED fit on the dress form (pattern_form.assemble, top button fastened), then ONE short release
sim (cloth_release, MCP release_garment; docs/state/cloth_release.md). No gravity substitutes on the form.

## Current candidate (nothing approved)
- Closed form fit r15e: closed + ROLL_GAP + roll_radius 6 mm + LAPEL_W 0.081 ($FR15/asm via harness15.py, pattern gate
  PASS_WAIVED 51e12aabcedf45c7251a, vent waived).
- Released r16 (job_k, rented $0.0355): $FR16/asm_r16. Fronts stay crossed (below).
- $FRn = /mnt/data/hifipushie/dress_garrett/fit_round<n>. Target: workspace/garrett_v20/concept_v8_front_apose.png;
  checklist workspace/checklists/garrett_jacket.json (front_state open, buttons done 0: Joe's fact).

## Open faults (game visibility first)
1. Released fronts hang crossed: edge off CF 450/550/650 = 0/6-19/22-37 mm vs concept 71/78/94; break x -8/+11 vs 64.
2. Seams open 1-4 mm after the release sim (white lines; runner stitch_gap 2 mm, 4 sew frames).
3. Notch / gorge: collar end stands off the lapel (tip 12.6 L / 3.5 R mm), gorge seam twists 20-25 deg in ~1 cm.
4. Width: waist 320 vs 401, torso 350/425 371/321 vs 396/400 (ease into depth); square boxy shoulder.
5. Lapel outer edge has no thickness contrast (made lapel queued); pocket flaps sag 16-19 mm in the release.
6. Shirt-through 251 verts (r16); shirt sleeves through jacket at the armpit join.

## Switches (module default; what the candidate uses)
pattern_form: ROLL_GAP False (r15e on) | ROLL_TURN False | CHEST_HOLD 0 | OPEN_HOLD False | HOLD_SLEEVES False |
HOLD_NAMED True | OPEN_HANG True | WORN_EDGE False | EDGE_FIELD True | HANG_FREE True | SWING_UNPINNED True |
WOVEN False (WOVEN_FLAPS True). cloth: PAD_DRAFT False. Release job: zozo start_over 0.06 (Garrett start 5.2 % over).

## Dead ends (one line each; details in notes)
- Gravity substitutes on the form (WORN_EDGE slide, OPEN_HOLD + holds above the break, ROLL_TURN + CHEST_HOLD tear).
- Neck unheld or a 6 s settle in the release: <= 2 mm from r16 (not the cause of the crossed fronts).
- R8 straight silhouette (worse lapel_on_base); shoulder chord + PAD_DRAFT (no gain).

## NEXT (round 17 plan)
1. Notch: validate notch.py on planted flat / twisted seams, find + fix the cause, KAT + gate row, notch crops.
2. Crossed fronts: measure balance / wrap / roll spring / grain / shirt collider / held neck, flat + local sim
   (HP_RUN_ZOZO=1), fix the draft, sourced; one rented run on the fix.
3. Seam gaps after release: local run, check that fails r16.
4. Table concept | r15e | r16 | r17, renders $FR17/check/, blind reviews one view per turn.
Queued after: made lapel with edge thickness; collar funnel + shirt collar; shoulders; waist pinch; every visible part.

## History (grep only)
docs/notes/cloth.md "fit round <N>", "fit rounds 1-16 STATE pages, archived", "cloth_release".
