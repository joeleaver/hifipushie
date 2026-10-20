# STATE: fit_round15 (Garrett jacket CLOSED at the top button; judged ABOVE the break) -- 2026-10-20. NO SIMS.

DIRECTION (coordinator): closed fit as the base (top button fastened; WOVEN / ROLL_TURN / CHEST_HOLD / OPEN_HOLD /
WORN_EDGE off). The open hang below the break waits on Joe.

STATE: HANDOVER. Candidate r15e = closed + ROLL_GAP + roll_radius 6 mm + LAPEL_W 0.081. Blind reviews upper_front FAIL,
upper_three FAIL. New switches pattern_form.ROLL_GAP and cloth.PAD_DRAFT: both opt-in, neither A/B'd on Tess.
NEXT: (1) coordinator / Joe: closed vs open is NOT the same above the button on this concept. The concept's break sits
64 mm off CF, ours closed sits -19, so the roll line pivots and the V differs by construction (v_width 200: 237 vs 149).
Decide whether the upper front is judged against a closed target or waits for the open method. (2) The lapel's outer edge
has no contrast (edge step 1-4 vs the concept's 3-30): it needs a made lapel (facing + canvas) whose edge carries
thickness. The render-only 2.2 mm Solidify doesn't read. (3) Gorge / notch ~100 px too low, plus the collar funnel. Both
are collar work (queued). (4) Shoulder: chord + PAD_DRAFT doesn't pay. Reviewers call the shoulder boxy, with a straight
vertical armhole seam on the front.

## Files ($FR15 = /mnt/data/hifipushie/dress_garrett/fit_round15)
run.sh, job.sh (CLOSED=1), harness15.py (code-keyed C49; `cloth.X=` overrides join the key), fr15.py (ROLL_R env),
meas.sh, edgeprof.py (front-view lapel rows: roll / outer-edge step x, 10-90 width, contrast, face width; ours resampled
to the concept's 0.88 px/mm), render15.py (upper_front / upper_three / lapel / lapeltop / shoulder per side / side / back;
RTHICK=1 renders the cloth with thickness), look.sh, review15.sh, meas_*.log, review_upper_{front,three}_r15e.log.

## Table (concept | r13b open | r15z closed | r15e closed candidate)
| item | concept | r13b | r15z | r15e |
| named break below HPS | 386 | 386 | 383 | (same draft) |
| visible lapel bottom below HPS | 386 | 361 | 360 | 326 |
| opening half 150 / 250 / 350 | 69/64/59 | 75/67/64 | 33/8/0 | 49/18/0 (closed: by construction) |
| v_width 200 | 237 | 243 | 160 | 149 |
| lapel face width 120/160/200/220 L (edgeprof) | 68/58/49/44 | - | 88/75/59/51 | 67/58/47/39 |
| roll step 10-90 width mm (front view) | 3-10 | - | 2-3 | 2-3 (silhouette on the shirt: this measure can't see a roll) |
| outer edge contrast 120-220 | 3-11 (29-31 at 260-300) | - | 0-3 | 0-4 |
| chest stand-off p50/p90 | - | 37/56 | 28/36 | ~same |
| shoulder rows 30/45/60 (r15b; r15c chord; r15d chord+pad) | 277/354/424 | 442/478/479 | 379/456/455 | 386/456/455; 313/376/449; 313/416/450 |
| sleeves shirt-through L/R (r15b; r15c; r15d) | 0 | 23/31 | 10/11 | 12/10 (r15b 10/9; r15c 34/37; r15d 31/28) |
| torso width 350 / 425 (front view) | 396 / 400 | 364 / 336 | 374 / 325 | 373 / 325 |
| side stand-off off the body 350 / 425 | ~57 / 61 | 43 / 20-38 | 47 / 24 | 47 / 24 |
| back stand-off 425 (sim 16-27) | - | 35 | 38 | 38 |
