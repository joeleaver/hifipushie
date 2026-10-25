# STATE: canvas (canvas / interfacing BENDING STIFFNESS; the jacket with no workaround holds) -- 2026-10-25

GOAL (Joe): canvassed pieces keep their shape by STIFFNESS so the workaround holds go. No sim, no rented GPU.
Concept SLIM-CUT, worn open, falls straight (workspace/garrett_v20/concept_v8_front_apose.png). Rules: threads first
(C195); supports, not holds (C190); styling ends with smooth + pull down.
Sessions: s1 78507629; s2-s5 claude/canvas2-5; s6 claude/canvas6 ($S6 /mnt/data/hifipushie/canvas/s6; history cloth.md
"canvas stiffness session 6"). Ledger C190-C204.
S6 FOUND / DID (all on fit_t5f = the fit floor C200, keyed; styled with s5's ops_hc or $S6/ops_ps.json):
- GORGE TEAR = the HELD stand + collar (worn_style froze every piece no op names; the gorge cloth sewn to the held
  stand tore as the fronts relaxed: 13.8 % with no floor at all) + the shirt's collar leaf as floor (the max 72.7).
  C202 (default ON): made pieces sewn to a moved piece move with it (MADE_FREE); worn_style under = (V, F, mesh): the
  shirt's own cloth floors the jacket's own cloth (UNDER_OWN). First relax 16.0 / 72.7 -> 11.9 / 25.6 (p99 / max).
- The jacket's made pieces on the shirt's made pieces (GP_UNDER_MADE=1, opt-in): tears the freed collar / stand at CB
  (34 / 35 %) and refuses the turn. Off (default): no floor for them (as the fit, C200); the shirt collar then shows
  through the jacket's at the back neck (poke-through ~2000 shirt vertices vs t5f_hc 317).
- R SIDE DID NOTHING: the slide / turn plumb from break to cutawayTop is RELATIVE; the first relax takes both breaks
  in 11-15 mm (64 -> 49-53; the fit's worn_open form rule put them at 64), so R's cutawayTop is already "plumb".
  C204 (op options, ON in ops_ps): turn "plumb_from": "start", slide by {"plumb", "from": "start"}: the line through the
  break as the styling found it. R slide 0 -> 14 mm.
- COLLAR: not short to its gorge / notch (sewn edges match flat). Its free edge is 3-9 % long in 3D in every fit
  (k3 too). C203 (PJ_UNDER_RING, opt-in, NOT proven): +11 mm a half; the fit's collar end still 119 faces > 12 %; styled
  with made on made it got worse (collar 44 %). The fit's collar-end strain relaxes once the collar is FREE (C202:
  collar faces > 12 % 94 -> 30, threads p99 5.9).
RUNS (concept edge 450/550/650 71/78/94, hem+30 482, front len 748; threads = pooled per-piece p99 / fronts):
| s1_k3 (holds) | 59-64 / 72-74 / 95-97 | 480 | 748 | thr 8.78 |
| t1_hc (s4) | 66-69 / 77-79 / 84-97 | 484 | 737 | 9.15 (7.07) |
| t5f_hc (s5) | 31-49 / 49-64 / 73-86 | 469 | 730 | 10.23 (7.77) |
| t5f_hc6 (C202, uncompacted floor) | 37-56 / 57-76 / 84-97 | 480 | 732 | 5.92 (4.33), poke 1986 |
| t5f_hc7 (C202 + made on made) | 39-44 / 52-58 / 71-82 | 464 | 737 | 15.57 (collar 34) |
| t5f_ps8 (C202 default + C204, ops_ps) | 66-46 / 80-67 / 106-93 | 498 | 729 | 6.46 (fronts 4-5; collar 15.2) |
t5f_ps8 LOOK ($S6/check/cmp_{wholefront,upper_front,side}_t5fhc_ps8_k3.png, rows t5f_hc / t5f_ps8 / k3): more
open than t5f_hc, chest clean, threads best yet; but the lower fronts FLARE (A-line, hem 498 vs 482, L 650 +12), L / R
asymmetric (R 450 -25), the shirt collar shows over the jacket's at the back neck (poke 1742), the flaps still ragged.
Suite (18 files, after the last code commit): 313 passed, 4 xfailed, PYTEST_EXIT 0 ($S6/suite.log).
DEFAULTS NOT flipped (edge rows 15-35 mm short of the concept at 450). No blind review (gate not met).
NEXT: (1) the breaks go in 11-15 mm in the first relax (fit 64 -> 49-53): find what pulls them (the free collar /
stand? the lapel's roll? trace brk.py per round) and stop it there; then re-tune ops_ps for 71 / 78 / 94. (2) the
jacket collar inside the shirt collar at CB: the FIT leaves it there (C200 floors cloth on cloth only); fix the fit's
layering of made pieces (the shirt collar a floor for the jacket's collar from the seat?) before UNDER_MADE can go on.
(3) the forward bulge (stand-off 55-62 vs k3 16-31): hang below the roll with a POINT ("at"), not a mark (s5 crash).
(4) C200's KAT still owed: tubes (kat200.py) never sink (no relax1 / swing phase in the tube fit): needs a jacket-like
case (a lapel-folded front). (5) flip test as s4 once 1-2 pass.
