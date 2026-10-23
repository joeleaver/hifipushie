# STATE: canvas (canvas / interfacing BENDING STIFFNESS in the fit + styling; the jacket with no workaround holds) -- 2026-10-23

GOAL (Joe, after C190-C192): canvassed / interfaced pieces keep their shape by STIFFNESS so the workaround holds go.
Not a sim; no rented GPU. Concept SLIM-CUT (gc_garrett v6, C193). Session 1 = main 78507629 (history: cloth.md
"canvas stiffness"); session 2 = branch claude/canvas2 (cloth.md "canvas stiffness session 2"), files $S2 =
/mnt/data/hifipushie/canvas/s2 (run.sh = this worktree's code; fitc.py / sty2.sh / tab38.sh / thr.py as session 1).
JOE (s2, via coordinator): "It shouldn't really be a choice between stiffness and stretch." -> C195 THREADS FIRST:
- styling (garment_pull.STYLE_THREAD_FIRST, on with STYLE_BEND): bending-free rounds after each round (2) and to
  convergence at the end (<= 60), each face's warp / weft within max(styling-start length, 1 +/- STYLE_THREAD_CAP 1 %).
- fit (pattern_form.FIT_THREAD_FIRST, on with keyed bending): interfaced triangles' threads capped (2 %) each round.
- KAT test_stiffness_never_buys_shape_with_stretch: walked strip canvas 12.4 -> 1.1 %, on the arc; plain 0.15 %.
- Like-for-like (no holds) the keyed fit had NOT raised jacket threads: c0_none 11.48 vs c2_none 9.62; k3's 7.42
  had holds supplying the shape. The shirt / jacket STYLING bend did raise them (12.5 / 15 %): retest under C195.
CANVAS REGION (C196): cloth.interfacing "region" (polygon of piece points / marks; outline full; feathered out).
Session 1's canvas = a 100 mm band along the front edge break..lapelPoint (lapel + strip) + stand / collar.
Real half canvas = forepart shoulder + armhole to the pocket line + lapel (+ bridle on the roll line): drafted as
$S2/region_half.json. d1 (half canvas, keyed fit W1, NO threads first): edge 41-45/40-42/36, hem 393, threads 11.17:
worse (more stiff area, bought with stretch). Not adopted; retry under threads first (NEXT).
RUNS ($S2; concept 71/78/94, hem+30 482, V 237, lapel 127/134; k3 60-64/74-77/101 thr 7.42; c2_none 52-58/67-72/82-86 9.62):
| d1_none | half canvas, W1, no TF fit | 41-45 / 40-42 / 36 | hem 393 | V 226 | lapel 126/132 | thr 11.17 |
| h2_none | band, W2, no TF fit | 46-60 / 30-48 / 37-55 | 441 | 223 | 108/141 | 15.67 |
| t1_none | band, W1, TF fit; kb ops | 59-67 / 62-67 / 78-79 | 470 | 228 | 125/136 | 11.90 (fit grain 7.2) |
| t1_tfa | t1 + TF in every styling solve | 37 / 40-45 / 52-56 | 449 | 209 | 125/128 | (slide stops on stretch) |
| t1_b5 / t2_none / t1f_none | styling bend W5 + TF / TF fit W2 / + flap mesh refine | chainD / chainC: read |
t1's styled threads rise is in the kb STYLING of plain cloth (front plain p99 67 % by thr.py), not the stiffness;
with TF in all styling (t1_tfa) the slide stops early and the fronts fall short: the honest reach of today's ops.
SHIRT under TF (shdiag on shirt_s0): full ops no bend PASS 6.47; full ops + bend W5 PASS 7.12 (s1: 2 fail, 12.2);
v3 + bend W5 / W1: 2 FAIL (edge turn 52 deg, crumple 0.32), 6.6 (s1: pass at 12.5: bought with stretch). Shirt keeps
today's ops; styling bend stays off (+0.65 threads).
FAULTS on c2_none: pocket flaps ragged = coarse flap (25 vertices, 37 mm apart) over a coarser front, the front pokes
through between flap vertices (s1_k3 too) -> t1f (flap h 8 mm + the front under it). Hem corner flip / boxy side: open.
DEFAULTS: NOT flipped (FIT_BEND_KEYED off, plumb hold on, kb holds in): no variant yet matches k3 on edge AND threads.
NEXT: (1) read t1_b5, t2_none, t1f_none (tab38.sh <tag>; grep "threads p99" r_<tag>.log; thr.py); (2) find where
t1's kb styling tears plain front cloth (thr.py per op: dump asm after each op with stylekb2 + gp.thread_strain;
the slide / turn ops tuned on floppy cloth): retune that op under TF, prove it; (3) if a TF variant reaches edge 450
>= 60 & threads <= 8.5 (or reads >= k3 vs concept) -> flip: FIT_BEND_KEYED on, gc_garrett plumb_hold off, kb
jacket.wear.open holds out, KAT, ledger; (4) renders post38.sh <tag> + cmp.py + joeseam39.py, then the blind LOOK
(gates.md; context "the reference jacket is worn open, unbuttoned"; wholefront, upper_front, side). Suite: $S2/suite.log.
