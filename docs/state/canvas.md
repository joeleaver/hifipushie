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
RUNS ($S2; concept 71/78/94, hem+30 482, V 237; k3 60-64/74-77/101, thr 7.42; c2_none 52-58/67-72/82-86, 472, 9.62):
| d1_none | half canvas, W1, no TF | 41-45 / 40-42 / 36 | hem 393 | V 226 | thr 11.17 |
| h2_none | band, W2, no TF | (chainA) |
| t1_none / t2_none / t1f_none | band, TF, W1 / W2 / W1 + flap mesh refine | (chainC) |
SHIRT under TF ($S2/chain_sh.sh: sh_none_full, sh_tf5_full, sh_tf5_v3, sh_tf1_v3): (running)
FAULTS on c2_none: pocket flaps ragged = coarse flap (25 vertices, 37 mm apart) over a coarser front: the front pokes
through between flap vertices (s1_k3 has it too) -> t1f refines flap + front under it (mesh_refine data).
DEFAULTS: not flipped (FIT_BEND_KEYED off, plumb hold on, kb holds in).
NEXT: read chainA / chainC / shirt tables (tab38.sh <tag>; thr.py; grep FAILS sh_*.log); pick the best TF variant;
if edge 450 >= 60 & threads <= 8.5 or reads >= k3 -> flip defaults (step 3 of the brief), else report the honest
reach; renders: post38.sh <tag> then the LOOK review (gates.md).
