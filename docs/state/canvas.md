# STATE: canvas (canvas / interfacing BENDING STIFFNESS; the jacket with no workaround holds) -- 2026-10-25 (s7)

GOAL (Joe): canvassed pieces keep their shape by STIFFNESS so the workaround holds go. No sim, no rented GPU.
Concept SLIM-CUT, worn open, falls straight (workspace/garrett_v20/concept_v8_front_apose.png). Rules: threads first
(C195); supports, not holds (C190); styling ends with smooth + pull down.
Sessions: s1 78507629; s2-s7 claude/canvas2-7 ($S7 /mnt/data/hifipushie/canvas/s7; history cloth.md "canvas stiffness
session 7"). Ledger C190-C205.
S7 FLIP (C205, DEFAULT NOW): a garment declaring interfacing is fitted keyed, UNDER_FLOOR from relax1 (C200), no default
plumb hold; fit_garment styles it on the shirt's own cloth (C202); kb jacket.wear.open = s6 ops_ps (old recipe kept as
style_holds_superseded). gc_garrett from repo defaults = t5f_ps8 to 0.000 mm ($S7/repro_d1.log; fit_d1 / asm_d1.pkl).
S7 FAULT TRACES (exp1.py: the styling's first N ops on fit_t5f with flags varied; en.py / en2.py / edgelen.py / flap.py):
- (a) BREAKS IN 11-15 mm: NOT the floors (no floor at all: same), not the made pieces (MADE_FREE off: same), not the
  stitches, not the pad (padded body: same). The fit holds the fronts curved round the chest (seat attraction, the
  worn-open pin w60 on the break, the neck pins) within its 2 % thread cap (warp +2.3 % p50 round the break); the
  styling has no force that keeps a front on the body, so the first relax springs it back toward its flat rest
  (break->HPS chord +9-10 mm, fronts forward 6-11 mm, in 11-15, the neck down 6-16). STYLE_BEND (canvas rest = the fit)
  makes it WORSE (W 0.5 / 1.5 / 5: the lapel lifts 20-45 mm forward, break 57-138): the styling's bending does not hold
  the moulded shape it is given (suspect bending.Bending's rest at the turned lapel / fold hinges). Hang-first: worse.
- (e) RAGGED FLAPS: the FIT never sews a patch's stitch (assemble's sew set has no M["stitch"]): each flap's stitched
  top edge ends 10-58 mm off its pocket line; worn_style welds the stitch -> the flap is yanked 19-46 mm, threads
  0.6 -> 23 % in the first relax (and drags the front: thread energy at the pocket rises).
S6 (kept): C202 made pieces move with what they are sewn to + the shirt's own cloth as the styling floor (default);
GP_UNDER_MADE (made on made) opt-in: tears the freed collar / stand at CB (34 / 35 %); C203 PJ_UNDER_RING opt-in, not
proven; C204 plumb from the styling's start (in ops_ps).
RUNS (concept edge 450/550/650 71/78/94, hem+30 482, front len 748; threads = pooled per-piece p99 / fronts):
| s1_k3 (holds) | 59-64 / 72-74 / 95-97 | 480 | 748 | thr 8.78 |
| t1_hc (s4) | 66-69 / 77-79 / 84-97 | 484 | 737 | 9.15 (7.07) |
| t5f_hc (s5) | 31-49 / 49-64 / 73-86 | 469 | 730 | 10.23 (7.77) |
| t5f_hc6 (C202, uncompacted floor) | 37-56 / 57-76 / 84-97 | 480 | 732 | 5.92 (4.33), poke 1986 |
| t5f_hc7 (C202 + made on made) | 39-44 / 52-58 / 71-82 | 464 | 737 | 15.57 (collar 34) |
| t5f_ps8 (C202 default + C204, ops_ps) | 66-46 / 80-67 / 106-93 | 498 | 729 | 6.46 (fronts 4-5; collar 15.2) |
t5f_ps8 LOOK ($S6/check/cmp_{wholefront,upper_front,side}_t5fhc_ps8_k3.png): more open, chest clean, threads best;
but lower fronts FLARE (hem 498 vs 482, L 650 +12), L / R asymmetric (R 450 -25), shirt collar over the jacket's at
the back neck (poke 1742), flaps ragged. No s7 looks yet (= t5f_ps8: the default reproduces it exactly).
SUITE (18 files, after the flip): 313 passed, 4 xfailed, PYTEST_EXIT 0 ($S7/suite.log). Repro ran before the shirt
narrowing (the jacket declares both keys: same path). First flip suite: 3 shirt reds ($S7/suite_flip.log), fixed.
NEXT (in order, on the new default; exp1.py <fit> <tag> <N first ops> [k=v garment_pull flags | under=0 | body=0 |
pad=1 | nostitch=1] is the probe):
(e first, cheap) the fit sews a patch's stitch: add M["stitch"] to assemble's sew set (pattern_form ~l.2402, flag
  FIT_STITCH env PF_FIT_STITCH, default on if proven); refit (repro.py d2, ~12 min fit + 5 min style), read flap.py
  (stitch gap ~0), edgeop.py, perpiece5, then the default changes (record the new numbers, not t5f_ps8's).
(a) the styling has no support keeping a front on the chest: a front springs to flat. Look first at why STYLE_BEND with
  rest = the fit LIFTS the lapel (bending.Bending rest at the folded lapel hinges: test a canvassed strip folded 170 deg
  + relaxed: it must stay); if the styling bending then holds the moulded chest, the breaks stay at 64 -> re-read R 450.
(b) jacket collar over the shirt's at CB in the fit (C200 floors cloth on cloth only), then GP_UNDER_MADE on.
(c) flare / hem 498 vs 482 / length 729 vs 748; (d) bulge; (f) C200 KAT on a lapel-folded front.
Then looks (wholefront, upper_front, side; concept | new default | t5f_ps8, clay + diag) and, at +-8 mm, the blind review.
