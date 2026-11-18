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
## R3g (C512): flatten by the threads (flatten_threads.py; warp / weft kept, shear free to 35 deg; body pieces 90,
  the collar 45 deg). Body thread strain 0.06-2.0 %. The bias collar stays 5.81 % (curvature -300 deg, cones +125).
## R3h (2026-11-17, C513): GENTLER COLLAR (Joe's pick). Proof /mnt/data/hifipushie/r3h (measure.py, hmeas.py, dev.py,
  chain.sh: toile.log / mark.log / cut.log; dev_<n>.json per try).
- WHAT MAKES THE CONE (measured, R3f-10 toile): the neck edge turns -67 deg in the surface at the side neck point
  (the toile's neck seam ends, the front neckline leaves straight for the gorge). The 30 mm stand carries that corner
  up: the roll turns +28 / +27 / +15 deg in the stand at columns 21-23 from CB (pinned at the trace's top 2 columns
  behind); the fall, folded DOWN, turns WITH it (+17 / +14 / +8): roll defects +44 / +39 / +22 = the +125 cone.
  A fold cancels only if the fall turns the other way: impossible for a fall below a roll that peaks.
- TRIES (dev_2..8): PIN_BACK 8: cone 178, 10.5 %. Side pin soft (weight 0.08): side 13 mm under the trace, cone 130,
  6.0 %; (0.02): side 34 mm under (stand gone, inverted), cones -44, 2.2 %. Front neckline curved into the HPS:
  broke the neck edge. Fall re-landed along its outer edge (KEPT, toile_flap.fan_fall): curvature -300 -> -184
  (half -78.5; stand -202, roll +144, fall -231 -> -126), thread 5.81 -> 4.84 %, cones unchanged (+125 / -57).
- Height kept: roll at the side neck point 1577.3 vs the trace's top 1577.6 mm. Step 4's collar row now FAILS cone
  points over cut_shape.CONE_MAX_DEG (15 deg / 5 columns, toile_gate.collar_row): the jacket's toile FAILS there.
- Cut (bias): thread 4.84 % (warp 3.82, weft 2.74), shear 21.9 deg mean, 23.7 % past the jam; flat 387 x 104,
  neck 315 / roll 318 / outer 524 (1.66 x neck), lumpy and red: NOT a tailored undercollar. Neck seams flat / garment:
  front 42.9 / 51.3, 45.9 / 51.6; back 111.1 / 95.4, 115.0 / 96.7 (threads 16.5-19.9 %). Gorge 47.4 / 47.4 PASS.
  Roll asks +5.3 %, outer -8.6 % (threads 32 / 28 %): no shaping within 8 % covers it.
- Not done: thread-aware seam / shape_fall_landing checks (cap -2.9 %, 524 / 479): out of budget.
## Left: downstream readers (chain_garment piece_start, garment_details, draft_own_tool.flat_check) read FLAT from a
  FreeSewing draft dir, not pattern.json; side / sleeve_under tapes; biceps / chest rings still take torso pieces;
  seam truing / shape rows compare flat lengths of bias edges (shear can take them up): not thread-aware yet.
NEXT: JOE DECIDES: a one-piece collar that rises to the trace beside the neck keeps a +125 deg cone (its roll peaks
there over the neck edge's corner); gentler = ~34 mm lower beside the neck (no stand there). Options: (a) a seam
along the roll (stand cut separately, the corner goes in the seam; the look unchanged), (b) accept the lower collar,
(c) the front neckline curved into the HPS (removes the corner itself; changes the fronts: needs its own run).
