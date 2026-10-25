# STATE: canvas (canvas / interfacing BENDING STIFFNESS; the jacket with no workaround holds) -- 2026-10-25

GOAL (Joe): canvassed pieces keep their shape by STIFFNESS so the workaround holds go. No sim, no rented GPU.
Concept SLIM-CUT, worn open, falls straight (workspace/garrett_v20/concept_v8_front_apose.png). Rules: threads first
(C195: "not a choice between stiffness and stretch"); supports, not holds (C190).
Sessions: s1 main 78507629; s2 claude/canvas2 ($S2 /mnt/data/hifipushie/canvas/s2); s3 claude/canvas3
($S3 /mnt/data/hifipushie/canvas/s3; history cloth.md "canvas stiffness session 3").
S3 FOUND: t1's plain-front tear (p99 67 %, max 650 %) was the LAYER FLOOR, not a styling op (perop.py per-op reads):
- shirt's open collar (thin two-sided leaf) shoved jacket gorge vertices through it in opposite directions, first relax
  260 %; the lapel's own flap floor fought every round (9 mm a round), canvas 122 %.
- C197 (default ON): floor has a side (behind -> own depth; push only from the tracked side), flap / patch read against
  the base vertex it started over (nearest once slid off), static floor contacts held for the rest of the solve.
  KAT test_a_floor_has_a_side. Front plain p99 66.8 -> 16.3; first relax canvas p99 25.9 -> 4.8 (= no floor).
- C198 (opt-in per op, "thread_stop": true): pull / smooth_border refuse a step once any face passes max(start, 1 %)
  + 2 %. KAT test_thread_stop_never_tears_a_face. On by default it broke 3 shirt open-collar tests.
RUNS (concept edge 450/550/650 71/78/94, hem+30 482, V 237, lapel 127/134; s1_k3 59-64/72-74/95-97 thr 8.78):
| t1_none (s2) | old floors | 59-67 / 62-67 / 78-79 | 470 | 228 | 125/136 | 11.90 |
| t1_fy | floors + border stop | 75-78 / 75-78 / 91-96 | 484 | 234 | 125/143 | 9.88 (fronts 8.65) |
| t1_fz | + pull stop (ops_ts.json) | 77-84 / 83-85 / 101-106 | 476 | 228 | 121/142 | 9.27 (fronts 7.31) |
| t1_fza | t1_fz + GP_THREAD_FIRST_ALL | 69-82 / 76-82 / 94-103 | 459 | 222 | 122/140 | 13.20: canvas torn (open) |
| d2_none | half canvas, TF fit | 42-44 / 42 / 36-38 | 408 | 220 | 121/125 | 7.98 |
Under thread stops every pull stops at 0-3 mm: the kb pulls drew the fronts back IN by stretching. Without them the
fronts over-open and flare A-line. LOOK t1_fz vs s1_k3 ($S3/check/cmp_{wholefront,upper_front,side}_t1fz_s1k3.png,
joeseam_s1k3_t1fz.png): WORSE than k3 (flare, hem corners kick out, shirt shows through the left chest, left lapel
edge doubled). DEFAULTS NOT flipped (threads 9.27 > 8.5 and the look loses to k3). No blind review (no candidate).
NEXT: (1) the shirt show-through on t1_fz's left chest: a side effect of C197 rule 1 (behind -> own depth) or the
contacts? A/B GP_FLOOR_SIDE_TRACK / GP_FLOOR_CONTACT on t1_fz (perop.py fit_t1 tag ops_ts.json; rd.sh; post38.sh).
(2) the fronts' fall: replace the kb's inward pulls (front cutawayTop..cfHem "down 0.5, out -1"; hem "down") with a
move that brings the lower fronts in by MOVING (a slide / turn back toward plumb, or a gentler turn deg: the turn at
60 deg now over-opens) and keep thread_stop; target 650 ~94, falls straight. (3) residual plain strain: the first relax
(front plain p99 9.3 -> 12.4) and the slide; GP_THREAD_FIRST_ALL tears the canvassed lapel at z 1.26-1.33 (t1_fza):
find why (cap vs held contacts?) before using it. (4) then step 3/4 of s2's NEXT (flip test, renders, blind LOOK).
(5) pocket-flap floor, hem corner flip: not reached.
Suite (17 garment files + test_bending): see $S3/suite.log (quoted in the commit after it).
