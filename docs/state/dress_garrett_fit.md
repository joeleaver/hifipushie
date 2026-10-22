# STATE: dress_garrett_fit (Garrett jacket over the approved shirt gc1: closed form fit + ONE release sim + arrangement) -- 2026-10-22, round 27

DESIGN FACTS (Joe, settled): the jacket is worn OPEN, unbuttoned; it falls straight down (no waist suppression, side
line plumb). Put "the reference jacket is worn open, unbuttoned" in every review's context ("fastened" = known misread).
Renders show the OPEN, ARRANGED jacket only; the closed fit is internal. Under-layer show-through is NOT a fault (C153).
The shirt is gc1 (workspace gc_garrett, styled open, Joe approved its throat; /mnt/data/hifipushie/garrett_collar/
gc1_styled.pkl), used AS IS (never refitted; its side lump is another thread's). C85: the jacket over the styled shirt.
STATE: round 27 done: r27sc = closed fit r27a0 over gc1 -> ONE local ZOZO release + arrangement (side seams held) ->
recull (BELT=50). A/B sim vs no-sim styling (r27q2c): the SIM stays the method (C157). Nothing approved. $0 spent.
NEXT: (1) step 3 not started: pocket flaps (now p50 5 mm off the front, 0-1 sunk; still read "puffy"? look), hem
corners, length (cfHem 736 vs concept 748 on r27sc: re-read the 748 first), collar standing up the neck / ragged at the
neck top (shirt collar points pierce it), lapels / gorge narrow. (2) garment_pull needs a layer floor (C157) before
styling can replace the sim. (3) shared bug: cloth._worn_levels leaves a stray start vertex on graded meshes (fix27.py).

## Method
Closed fit: pattern_form.assemble over gc1 (harness mode gc1: under = gc1's styled vertices), top button fastened, the
form's lapel recipe (FORM_REFINE_LAPEL, NO extra row refine: C156). Release + arrange: g25.py arrange=1 keep=1 pull=100
side=1 (local ZOZO). Cull: recull.py BELT=50 (stand-in until trousers).

## C137 on the jacket (step 1, measured: fit_round27/rowmesh.py, foldreads.py)
Rows across = folds.rows from the roll radius (ROLL_R 6 mm in the recipe): lapel 4 hinges 3.76 mm apart (pi r/4 = 4.7:
PASS), collar 2.52 mm. Grading the roll lines to 2.2 mm (r27a) made the fit WORSE (lapel.L turn 161 -> 79 FAIL, collar
twist 10 -> 33 deg/cm, front.L p99 12.6 -> 24.8 %): NOT adopted (C156). Closed r27a0 fold reads: lapel turn 161 / 154
PASS, lapel.R on base 0.11 FAIL (r26i 0.04), twist PASS, fold_crisp FAIL (reads a roll as pressed: reader question),
collar on base FAIL (n 7, as r26i).

## A/B (same views, check/*_r27sc vs *_r27q2c)
(a) sim r27sc: lapels on their base (0.01 / 0.10), flaps on the fronts, shirt collar shows in the V; collar top ragged.
(b) styling r27q2c (ops_q2.json): straighter hem, stretch p99 5.8, but lapels THROUGH their fronts (0.27 / ~0.6), flaps
sunk 8 / 4 of 25, fronts sunk into the shirt, edge 64-67 at every row (no flare to the hem). Sim wins (C157).

## Table (concept | r26k | r27sc sim | r27q2c styled)
widths chest/waist/hip/seat/hem+30: 397/401-414/-/-/482 | 411/382/400/411/430 | 407/391/396/396/399 | 414/388/393/429/428
side line in (max L/R): - | 18/12 | 32/21 | (read broken by the sunk front)
edge off CF 450/550/650 L|R: 71,78,94 | 65,78,95 / 67,64,87 | 67,77,93 / 65,71,86 | 66,64,67 / 65,65,67
break below HPS: - | 347/342 | 321/322 | 284/336.  hem cfHem: 748 | 758 | 736 | 747. stretch p99: | 14.2 | 9.5 | 5.8
flaps off front p50 (sunk/25): | 2.8/3.7 (1/0) | 5.1/4.7 (0/1) | 0.0/8.4 (8/4)

## Commands ($FR27 = /mnt/data/hifipushie/dress_garrett/fit_round27; run.sh runs THIS worktree's code)
Closed: MODE=gc1 [ROWS_H=0] ./fitcheck.sh <tag> LAYER_ALLOW=0.008 BRIDGE=true (placed_5beb81fe9475 for r27a0).
Release: BASE=asm_<c>.pkl ./arr.sh <tag> arrange=1 keep=1 pull=100 side=1 start=asm_<c>.pkl placed=<placed pkl>.
Styling: RUNNER=bin/capped ./run.sh style27.py asm_<c>.pkl <tag> [ops.json]. Renders: BELT=50 ./cullrender.sh <src>
<dst> wholefront,upper_front,upper_three,side. Rows: table27.sh asm.pkl; foldreads.py; rowmesh.py.

## Dead ends (one line each)
- Gravity substitutes; release neck unheld / 6 s settle / friction 0; fronts' crossing fixes (see cloth.md r20-r25).
- Plumb cut at the side seams (r26a); open edge hung plumb in depth (r26e).
- Roll rows graded to 2.2 mm on the jacket (r27a, C156). No-sim styling without a layer floor (r27p / q / q2, C157).
