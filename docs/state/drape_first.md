# STATE: drape first (docs/proposals/drape_first.md; approved 2026-11-16)

Steps 4-6 rebuilt the draper's way: TOILE (the garment's 3D surface on the body), MARK, CUT AND FLATTEN.
Runs R1 (C489) -> R2 (C490) -> R2b (C491) -> R3a (toile, C492) -> R3b (mark + cut, C493) -> R3c / R3c-2 (made pieces, C494)
-> R3d (lengths from the toile, C495) -> R3e (cap ease, girth rings, C496) -> R3f / R3f-2 (collar draped, C497-C498).
History: docs/notes (grep C489-C495); spikes/r1_*, r2_*, r2b_*.

## Tools (each module's docstring is the spec)
- garment_toile = step 4 (toile*.py). Proof /mnt/data/hifipushie/r3a (all rows PASS).
- garment_mark = step 5 (mark.py, mark_lines.py, mark_split.py, mark_tool.py, mark_flap.py): marks cut their region
  exactly; rows marks, separate, pieces, seams, gorge. Proof /mnt/data/hifipushie/r3b: PASS (10 pieces, 17 step-1 seams).
- garment_cut = step 6 (cut.py, cut_tool.py, flatten.py, cut_made.py, cut_flap.py, cut_layers.py, cut_collar.py, cut_ease.py): each
  piece one disc, LSCM + ARAP, strain per piece; runs named; plain seams trued; then MADE pieces: flaps (lapel unfolded
  across its roll onto the front), layers (facing / canvas traced off the front's flat), collar (cut from step 4's
  flap behind its gorge marks, fall unfolded about the roll). The block -> draft_own_gate.gate.
  Writes cut/flat.npz, pattern.json, cut.json, flat_sheet.png, cut_3d.png.
- Record: steps 5 / 6 name garment_mark / garment_cut. chain_garment's from_chain writes only 8; a build that stops is
  step 7's failure, back to step 6 (R3b-2).
## R3d-R3e (C495-C496): step 6 tapes / places / collar lines from the toile; cap ease as a crowned rest length;
  girth rings by body part; button marks. Details in codified.md.
## R3f..R3f-8 (C497-C507): collar draped on the toile and unfolded at the cut; front neckline gorge -> HPS; toile in
  step 2's wear state, the pattern cut from the CLOSED toile (worn open: t.worn too, for the look); the suit collar's
  stand leans back against the neck, the fall covers it. Details in codified.md C497-C507.
## R3f-9 (C508): lapels + collar ONE turned flap (toile_flap.py, step 4; mark_flap.py splits it at the gorge, step 5).
  Proof /mnt/data/hifipushie/r3f9: strain 5.96 %, but the collar lay low at the side neck. Details: codified.md C508.
## R3f-10 (C509): the roll line drawn ON the toile (roll_on_surface), pinned at CB, PIN_BACK columns behind the side
  neck at the trace's top, and R0. Proof /mnt/data/hifipushie/r3f10: LOOK dev_6.png right (collar rises beside the neck
  to the trace, one piece with the lapel, stand ~6 % seen); COST strain 13.6 % (R3f-9 6.0). Details: codified.md C509.
## R3f-11 (C510): the collar flattened as SHAPED cloth (cut_shape.py, garment_cut `shaped`, +-8 % per run, refused
  beyond). Proof /mnt/data/hifipushie/r3f11: best shaping within 8 %: strain 13.3 %; cone points +125 / -57 deg.
## R3f-12 (C511): the cone points come from the roll's turn (crease rule, cut_shape.crease): R3f-10's roll turns +78 deg
  per half in the stand, the fall +7 with it: defect = 2 x the turn. Step 4 reports t.info["collar_surface"].
## R3g (2026-11-17, C512): FLATTEN BY THE THREADS (proof /mnt/data/hifipushie/r3g: cut_g.log, diag_collar.py)
- flatten_threads.py: ARAP's local step keeps warp and weft unit and the threads' angle within the jam (35 deg,
  pattern_form.SHEAR_LOCK_DEG), a weak pull to square (SHEAR_WEAK 0.02: free shear is a gauge and wandered). Every cut
  piece: garment_cut `grain` {piece: deg} (default 90); the collar's own `grain` (default 45 to its CB: the bias).
  strain_mean_pct = THREAD strain; iso_strain_mean_pct the old reading; rep.threads: warp / weft / shear split.
- cut_shape: runs / cone points read warp, weft, shear; the 8 % (an assumption, no source found) is on THREAD stretch;
  `curvature`: the piece's total angle defect beside what one thread quad carries (Hazzidakis: 4 x jam = 140 deg).
- Body pieces (straight grain): thread strain front 0.24 (iso was 1.15), side 0.06 (0.35), back 0.31-0.38 (2.0),
  sleeve_top 2.0 (3.3), sleeve_under 0.8 (1.0): shear takes most of what read as strain (caveat: darts read from it).
- THE COLLAR ON THE BIAS DOES NOT FLATTEN: thread strain 5.81 % mean (iso 13.6 before), shear 22.9 deg mean, 24 % of
  area past the jam; straight grain 3.6 % (bias no better). Curvature total -300 deg (stand -202, roll +133, fall
  -231; per half -137 vs 140 one thread quad carries); side-neck cones +125 read threads 20-42 % max, shear 40-43.
  Neck seams on the bias: 3D agree (50.3 / 51.5, 99.6 / 99.7) but the runs' threads 15-27 % max: front flat 43.4 /
  garment 51.3, back 111.1 / 95.4. Flat collar lumpy, red all over: NOT a tailored undercollar shape.
- New FAILs vs R3f-12: seams (sleeve_under cap vs side armhole -2.9 %: a bias edge's flat length is a shear state)
  and shape_fall_landing (outer 541 / 510: same). Flaps / layers FAILs as before.
## Left: downstream readers (chain_garment piece_start, garment_details, draft_own_tool.flat_check) read FLAT from a
  FreeSewing draft dir, not pattern.json; side / sleeve_under tapes; biceps / chest rings still take torso pieces;
  seam truing / shape rows compare flat lengths of bias edges (shear can take them up): not thread-aware yet.
NEXT: JOE DECIDES: the bias alone doesn't make R3f-10's collar one piece (its curvature, not its grain). Options: (a) a
seam along the roll (stand cut separately: the roll's +133 deg goes in the seam; stand and fall each within what
shear carries: untested), (b) the crease rule's trades (R3f-12: roll lower / fall flares / soft roll), (c) more
shaping. Then step 4 builds it, gated on collar_surface + curvature.
