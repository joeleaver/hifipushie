# STATE: canvas (canvas / interfacing BENDING STIFFNESS; the jacket with no workaround holds) -- 2026-10-25

GOAL (Joe): canvassed pieces keep their shape by STIFFNESS so the workaround holds go. No sim, no rented GPU.
Concept SLIM-CUT, worn open, falls straight (workspace/garrett_v20/concept_v8_front_apose.png). Rules: threads first
(C195); supports, not holds (C190); styling ends with smooth + pull down.
Sessions: s1 78507629; s2-s4 claude/canvas2-4; s5 claude/canvas5 ($S5 /mnt/data/hifipushie/canvas/s5; history cloth.md
"canvas stiffness session 5"). Ledger C190-C201.
S5 FOUND:
- SHOW-THROUGH = the keyed hinges vs a SOFT shirt (not threads first, not C197). Chest behind the shirt at fit end:
  unkeyed c0 / s1 4-12 %, keyed c1 / c2 / h2 / t1 37-56 %. Traced (fit5.py / gapt.py): sinks in relax1 (49 %) and the
  swing (75 %), before the C172 floor (from the seat). C200 (opt-in, env PF_UNDER_FLOOR=1 PF_UNDER_FLOOR_FROM=relax1):
  the floor from relax1, never from behind (placement side), on the shirt's own cloth (not its collar / stand), for
  the jacket's own cloth (not its collar / stand / flaps). Fit t5f: chest 0 / 0 % behind, fronts' threads 6.5 / 5.7.
- THREADS p99 ~9: the excess is the COLLAR END at the gorge (|x| 90-120, z 1.54-1.56, warp stretch; 58-69 % of values
  > 8.5 %), set in the fit, untouched by styling; k3 8.78 too. Not fixable in styling: a collar-end / draft fault.
- POCKET FLAPS: 25-vertex flap over a finer front; C201 patch_lie (ON, worn-open styling): covered base cloth laid
  THICK behind the flap (triangle projection). Measured none through after; diag still shows the flap outline irregular.
RUNS (concept edge 450/550/650 71/78/94, hem+30 482, front len 748; stands ahead of body waist/-100/-200/-300 L):
| s1_k3 (holds) | 59-64 / 72-74 / 95-97 | 480 | 748 | 31 22 28 16 | thr 8.78 |
| t1_hc (s4 cand. + patch_lie) | 66-69 / 77-79 / 84-97 | 484 | 737 | 57 56 45 24 | 9.15 (fronts 7.07) |
| t5f_hc (fit floor C200 + hc ops) | 31-49 / 49-64 / 73-86 | 469 | 730 | 55 62 61 49 | 10.23 (7.77) |
t5f_hc: R slide + turn do nothing; first relax tears the gorge plain cloth (front plain p99 16.7, z 1.52-1.54; fit
grain max 36 % there). The ops were tuned on t1's sunk chest; on t5f the fronts lap in.
LOOK ($S5/check/cmp_{wholefront,upper_front,side}_t1hc_t5fhc_k3.png; rows t1_hc / t5f_hc / k3, concept | clay | diag):
t5f_hc has the cleanest chest yet (no shirt through, lapels lie flat on the chest) but the fronts close toward CF from
the button down and the hem draws in (edge 31-49 at 450): worse than t1_hc for the opening, the main concept read.
t1_hc keeps the best opening and still shows the shirt at the left chest. DEFAULTS NOT flipped. No blind review.
Suite (18 files, after the last code commit 30dc65c4): 312 passed, 4 xfailed, PYTEST_EXIT 0 ($S5/suite.log).
NEXT: (1) re-style on t5f (the floor fit): find why the R slide / turn refuse (perop_t5f_hc.log: thread stop at the
torn gorge?) and the first relax's gorge tear (styling floor C197 on the new fit's neck: compare gap / where.py per op);
fix the fit's gorge (grain max 36 % at |x| 85 z 1.54) first. (2) then re-tune the open ops on t5f to reach edge
66-71 / 77 / 94 (more turn / slide on t5f; the chest no longer sinks so it needs less pull in). (3) forward bulge:
ops_ho (hang from the bust down) failed: "front.L:bust" is a MARK, not a point: use keep "at" / a point, or add mark
lookup to hold_region "above". (4) collar end strain (the p99 gate): the collar is short to its notch (draft). (5) KAT
for C200 owed (a stiff plate over a dome over a sphere: never sinks with the floor from relax1). (6) flip test as s4.
