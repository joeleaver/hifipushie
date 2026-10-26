# STATE: canvas (canvas / interfacing BENDING STIFFNESS; the jacket with no workaround holds) -- 2026-10-25 (s9)

GOAL (Joe): canvassed pieces keep their shape by STIFFNESS so the workaround holds go. No sim, no rented GPU.
Concept SLIM-CUT, worn open, falls straight (workspace/garrett_v20/concept_v8_front_apose.png). Rules: threads first
(C195); supports, not holds (C190); styling ends with smooth + pull down; current garments are not a baseline.
Sessions: s1 78507629; s2-s9 claude/canvas2-9 ($S9 /mnt/data/hifipushie/canvas/s9; history cloth.md "canvas stiffness
session 9"). Ledger C190-C210.
DEFAULT (C205 + C206 + C209): interfaced garments fitted keyed, shirt floor from relax1, no plumb hold, styled on the
shirt's own cloth, the FIT sews patch stitches; NEW (C209): a garment that declares interfacing is STYLED with its
bending under STYLE_TF_PD (GP_STYLE_BEND unset = per garment; GP_TF_PD default 1), the threads' term weighted
STYLE_TF_PD_MEM (10) x the stiff cloth's bending. e1 = the d2 fit styled by the repo default ($S9/asm_e1.pkl).
S9 FINDINGS:
- (a) FIXED (C209): the op that tore under C207 was not a grip: the hem pull took 0 steps; its plain relax solve (20
  rounds, nothing moved, grips free or not) tore front.L's canvassed lapel 6.9 -> 19.5 %, its settle -> 63 %
  (solvelog9 / probe9 / step9 on cap_pull_pd.pkl). Cause: the canvas bending (K diag median 13681) swamped the threads
  (L diag 3.5): the global step was bending only, and the Jacobi cap after it tore (one round: global 12.7 -> cap
  43.6 %). Threads weighted 10 x the bending: the same solve 6.9 %; full styling pd10: threads p99 8.19 (fronts 5.3,
  collar 10.8 vs d2 22.5), >20 % faces 20 vs 70.
- (b) MEASURED, NOT THE DRAFT (C210): the collar's neck edge / stand top need +4.4 / +2.4 % over flat to ride the
  shirt collar in the FIT (rad9 / need9); the STYLING pulls the stand top in at CB (r 78 -> 69 mm, shirt collar
  fall ~76-80) and down (z 39 -> 33 over HPS; shirt fold at 54-58): need +8.6 %. So the shirt shows at CB because the
  styling sinks the jacket collar (d2 389 shirt verts outside the jacket at CB; m1 0). At the side (90 deg) the jacket
  roll sits 20-36 mm below the shirt top and 25 mm off the neck (r 94 vs shirt band 68): the collar flares off the
  neck instead of hugging it. No draft change made.
- (c) lapel / V: fit_d2 lapel 150 125/127, V 200 220, break 315-320 below HPS; styled d2 122 / 209 / 329-335; pd10
  119 / 201 / 320-324 (concept 127-134 / 237 / 386; r32: 133 / 221). Narrowed 8 mm in the fit since r32 and 11-19 more
  in the styling; the break sits 50-65 mm HIGH (the V is shallower by the numbers, it reads deeper because the lapel
  faces turn sideways: not measured yet).
RUNS (concept edge 450/550/650 71/78/94, hem+30 482, front len 748; threads = pooled p99 (fronts; collar)):
| d2 (s8 default) | 52-50 / 65-72 / 90-105 | 471 | 735 | 7.64 (4.0; 22.5) |
| pd10 = e1 (C209, DEFAULT) | 56-62 / 69-71 / 80-69 | 457 | 729 | 8.19 (5.3; 10.8) |
LOOK pd10 vs d2 (check/cmp_pd10_d2_*.png): about the same jacket: upper fronts a little straighter, collar threads
halved, but the lower fronts still cut away and hem in more (457), a crease on the right front at the pocket; V / lapel
/ gorge tabs / shirt collar at the back unchanged. No blind review (edge rows not within +-8 mm).
SUITE: see cloth.md session 9 / $S9/suite.log.
NEXT (in order; scripts in $S9: perop9.py <fit> <tag> [ops] (per op, per piece), solvelog9.py, cap9.py + probe9.py
(capture an op's input, probe its solve), rad9 / need9 / over9.py (collar vs shirt), rd.sh / post.sh / sheet.py):
1. Collar sinks in the styling: perop9 on e1 + opcol9.py <fit> <tag> (cbTop r / z, shirt-over at CB per op) to name the
   op that pulls the collar down / in; fix it there (a made band is supported by the shirt collar it rides on: C208's
   made-on-made floor in the STYLING may now hold without tearing, retry m1 under C209).
2. The side of the neck: the jacket roll 25 mm off the neck at 90 deg; read the stand's lean (neck edge r vs top r)
   on the fit; if the stand top is as long as its neck edge the collar can't hug: a drafting rule (top edge shorter
   by the lean), test_tailoring + Tess's coat path.
3. Lapel face yaw (the lapel turned sideways reads narrow): measure the lapel face normal at HPS-150 vs the concept's
   flat-on lapel; the break 50-65 mm high vs 386: pattern (break_y 0.425) or fit (worn_open break 64)?
4. Hem 457 vs 482 / 650 edge 80-69 vs 94: the lower fronts hem in under C209; then flare, bulge, C200's KAT.
