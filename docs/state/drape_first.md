# STATE: drape first (docs/proposals/drape_first.md; approved 2026-11-16)

Steps 4-6 rebuilt the draper's way: TOILE (the garment's 3D surface on the body), MARK, CUT AND FLATTEN.
Runs R1 (C489) -> R2 (C490) -> R2b (C491) -> R3a (toile, C492) -> R3b (mark + cut, C493) -> R3c / R3c-2 (made pieces, C494)
-> R3d (lengths from the toile, C495) -> R3e (cap ease, girth rings, C496) -> R3f / R3f-2 (collar draped, C497-C498).
History: docs/notes (grep C489-C495); spikes/r1_*, r2_*, r2b_*.

## Tools (each module's docstring is the spec)
- garment_toile = step 4 (toile*.py). Proof /mnt/data/hifipushie/r3a (all rows PASS).
- garment_mark = step 5 (mark.py, mark_lines.py, mark_split.py, mark_tool.py): marks cut their region exactly; rows marks,
  separate, pieces, seams. Proof /mnt/data/hifipushie/r3b: PASS (10 pieces, 17 step-1 seams).
- garment_cut = step 6 (cut.py, cut_tool.py, flatten.py, cut_made.py, cut_flap.py, cut_layers.py, cut_collar.py, cut_ease.py): each
  piece one disc, LSCM + ARAP, strain per piece; runs named; plain seams trued; then MADE pieces: flaps (lapel unfolded
  across its roll onto the front), layers (facing / canvas traced off the front's flat), collar (cut from step 4's
  draped collar, fall unfolded about the roll; the front's neck cut at the gorge corner, past it "notch"). The block -> draft_own_gate.gate.
  Writes cut/flat.npz, pattern.json, cut.json, flat_sheet.png, cut_3d.png.
- Record: steps 5 / 6 name garment_mark / garment_cut. chain_garment's from_chain writes only 8; a build that stops is
  step 7's failure, back to step 6 (R3b-2).

## R3d-R3e (C495-C496), details in docs/notes/codified.md
- Step 6 takes tapes / places / collar lines from the toile (R3d); cap ease as a crown flattened at its rest length,
  girth rings by body part, button marks on both fronts (R3e). Proof /mnt/data/hifipushie/r3e. Still FAIL there:
  darts_drafted, style_lengths, girths (hips / seat rings miss back.R; chest -44 at the underarm).

## R3f (C497): the collar draped on the toile (toile_collar.py), cut and unfolded at step 6 (cut_collar.py)
- garment_toile part collar {stand_mm, fall_mm, notch}; neck edge = toile neck seam + gorge across the lapel top; stand
  walked up to the roll; fall turned down. Proof /mnt/data/hifipushie/r3f. Draft-and-fit route deleted.

## R3f-2 (2026-11-16, C498): seams name the same runs; the fall lies on the toile along the surface
- Seams (they were front 66 / 111, back 134 / 127 mm): the toile's opening leaves the neck ~7 mm BEHIND the body's
  HPS and drops 30 mm down the neck's side, so the shoulder mark met the opening edge, not the neck: back.L:neck carried
  that drop (127 flat; the toile's seam is 99). Now toile.npz neck_corner (where the neck seam ends); mark_lines leans
  the shoulder line's inner end onto it (NECK_LEAN_M); cut.runs_of merges short free runs shortest first, and a run
  under FREE_CORNER_MM between a seam and a free edge (or inside one) joins it (the drop is neck, not front);
  cut_collar.split_gorge cuts the front's neck at the collar's gorge corner (past it: free "notch", 44 mm), before the
  facing is traced. Now back 92.7 / 93.0, front 108.3 / 103.1 (L, +5.2 > 3: FAIL), 106.2 / 103.3 (R); seams row PASS.
- Fall: toile_collar lands the fall at fall - h along the toile's surface (was a 3D chord of fall from the roll).
  Reading (reference_front.png, 1.05 mm/px): the collar's visible width at the side, roll (shirt-collar edge) to
  outer edge, ~38 mm projected at mid side -> fall 42 (toile_decl2.json). Lands 16.6 mm below the seam at CB (was 9.8);
  fall 50 tried: 23.5 below, outer 1.032 x neck (not kept: no reading for it).
- Why it is still a band: behind the HPS it is right (neck 93 / roll 88 / outer 110 mm per half: x1.18); IN FRONT the
  roll row is 132 against a neck + gorge of 99 and an outer of 93 (the stand's walk "up square to the gorge" swings the
  roll outward; the fall converges onto the collar point), so the whole flat comes out outer 403 / neck 400 = 1.009.
  At the HPS the fall walks DOWN the neck's side (outer only 10 mm out), not out over the shoulder.
- Proof /mnt/data/hifipushie/r3f2 (go.sh; toile4 / mark4 / cut7 logs = fall 42): toile PASS (collar row PASS); mark
  PASS; cut: seams PASS 0 off, shape_fall 1.015 PASS, shape_fall_landing 0.986 PASS, collar FAIL (front.L seam +5.2;
  flat 377 x 88, outer 1.009 x neck, strain 10.5 %). Looks: r3f2/look_neck_cut3d.png (reference | neck front / left /
  back), ws/.../cut/flat_sheet.png. Judged: still a smooth band standing round the neck, no lie-out on the shoulders;
  the flat collar is a wavy straight strip, not a crescent.

## Left
- style_lengths (compare only like lines); downstream readers (chain_garment piece_start, garment_details,
  draft_own_tool.flat_check) read FLAT from a FreeSewing draft dir, not pattern.json; ~120 "step 4" texts mean the flat.
- R3e's: darts from the strain ridge; girths (hips / seat back.R, chest -44); side / sleeve_under tapes.

NEXT: R3f-3: the collar's front: the roll must continue the lapel's roll line (toile roll_line) from the gorge to the
HPS, not walk "up square to the gorge" (roll front 132 vs neck 99), and the fall at the HPS must go OUT over the
shoulder slope (the walk square to the neck edge goes down the neck's side): then outer > 1.2 x neck and a crescent.
Consider a lower stand at the side (h tapers from CB). Then front.L seam +5.2.
