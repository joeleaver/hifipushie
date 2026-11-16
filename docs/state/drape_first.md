# STATE: drape first (docs/proposals/drape_first.md; approved 2026-11-16)

Steps 4-6 rebuilt the draper's way: TOILE (the garment's 3D surface on the body), MARK, CUT AND FLATTEN.
Runs R1 (C489) -> R2 (C490) -> R2b (C491) -> R3a (toile, C492) -> R3b (mark + cut, C493) -> R3c / R3c-2 (made pieces, C494)
-> R3d (lengths from the toile, C495) -> R3e (cap ease, girth rings, C496) -> R3f (collar draped on the toile, C497).
History: docs/notes (grep C489-C495); spikes/r1_*, r2_*, r2b_*.

## Tools (each module's docstring is the spec)
- garment_toile = step 4 (toile*.py). Proof /mnt/data/hifipushie/r3a (all rows PASS).
- garment_mark = step 5 (mark.py, mark_lines.py, mark_split.py, mark_tool.py): marks cut their region exactly; rows marks,
  separate, pieces, seams. Proof /mnt/data/hifipushie/r3b: PASS (10 pieces, 17 step-1 seams).
- garment_cut = step 6 (cut.py, cut_tool.py, flatten.py, cut_made.py, cut_flap.py, cut_layers.py, cut_collar.py, cut_ease.py): each
  piece one disc, LSCM + ARAP, strain per piece; runs named; plain seams trued; then MADE pieces: flaps (lapel unfolded
  across its roll onto the front), layers (facing / canvas traced off the front's flat), collar (crescent drafted flat
  by draft_fall's rule, fitted by chain_net.project, every flat length held). The block -> draft_own_gate.gate.
  Writes cut/flat.npz, pattern.json, cut.json, flat_sheet.png, cut_3d.png.
- Record: steps 5 / 6 name garment_mark / garment_cut. chain_garment's from_chain writes only 8; a build that stops is
  step 7's failure, back to step 6 (R3b-2).

## R3d (C495): step 6 takes its lengths from the toile
- Collar outer edge = the toile's landing contour at depth w - 2h (cut_collar.landing_line); tapes / place per piece
  (cut_tapes.py); planned hems as folds; declared ease kept, ".L" serves ".R". Proof /mnt/data/hifipushie/r3d.

## R3e (2026-11-16, C496): cap ease, girth rings, closure marks; collar leans back; darts NOT started
- Cap: toile.crown: inside the cone a roll CAP_BAND_M wide rises CAP_RISE x ease x tube radius over the crown (10 mm);
  under the arm tube / torso meet at a crease (UNDER_BLEND_M). The seam is shared, so a dome alone flattens to its
  seam's length (a bump's curvature nets to zero): step 6 flattens the band at its REST length (cut_ease: + e along the
  seam, e peaks at the shoulder point, W_FLOOR at the underarm, calibrated per sleeve piece by secant). Jacket: cap /
  armhole L 513 / 475 = +8.1 %, R 518 / 470 = +10.3 % (R3d -2.5..-8.8 %); cap_back 13-14 %, cap_front 6-11 %, under
  2-3 %; declared ease kept, seams 0 off. sleeve_top strain 3.3 % mean against its rest (the eased crown).
- Collar: stand 20 / fall 32 mm read off the reference (front view: the collar top at CB 333 px is ~5 mm above the side
  neck points 337 px; the toile's CB neck seam is 15 mm under them). Lower stand alone landed HIGHER (4.7 mm: the outer
  edge is the same 600 mm contour); LEAN 0.15 -> -0.25 (the stand leans back) lands 9.4 of 12 mm. Still reads as a
  band round the neck with its ends curling up at the sides (landing line behind the shoulder x0.959 the flat outer).
- Girths: rings take one body part (most pieces naming the girth: a sleeve_under naming chest no longer pulls the
  sleeves in); step 6 writes button / buttonhole marks at x = 0 on both closed fronts (toile opening.buttons_z), the
  closure's edges as arcs. Waist 989 / 988 (was 1029); chest 1064 / 1108 (-44, at the underarm); biceps 376 (no ease
  planned) OK; hips 865 / seat 816 OPEN rings missing back.R (CB vent?); cut_tapes doesn't name chest on side / biceps
  on sleeve_under.
- Proof /mnt/data/hifipushie/r3e (go.sh, toile_run.py + toile_decl.json, run.py mark mark_decl.json, run.py cut
  cut_decl4.json; toile2 / mark2 / cut5 logs): toile 14 PASS; mark PASS; cut PASS seams 32 0 off, collar, piece_tapes,
  place, panels, shape_fall 1.261, landing 1.000, shape_cap 0.70, sewn, closures; FAIL darts_drafted, style_lengths, girths.
- Tests: tests/test_cut_r3e.py (eased band flattens longer by e, unstrained against rest; marks on both fronts).

## R3f (2026-11-16, C497): the collar draped on the toile (step 4), cut and unfolded at step 6
- toile_collar.py: garment_toile part `collar {stand_mm, fall_mm, notch}` (needs lapel): neck edge = the toile mesh's
  neck free edge (CB -> the over front's corner) + the gorge across the lapel top to the notch trace's first point; the
  stand walked up the toile by h(s) to the roll; the fall a SPAN of fall_mm from the roll to where it lands (hugging the
  neck's foot made a fold the flat can't keep); gate row `collar`. cut_collar.py only cuts / flattens (the fall unfolds
  about the roll row) and names edges; the draft / place / landing_line route deleted. Tests: test_toile_collar.py.
- Heights: stand 20 / fall 32 from R3e's reading (collar top at CB ~5 mm above the side neck points, CB seam 15 under
  them -> stand 20); fall 32 has no direct reading in the front view.
- Proof /mnt/data/hifipushie/r3f (go.sh; toile6 / mark5 / cut5 logs): toile PASS (roll 18 mm above the seam, outer 9.8
  below, 0.2 mm off the toile); mark PASS; cut collar FAIL: flat 382 x 75, outer 397 = 0.996 x neck (a straight band,
  not s4-31's 414 x 95), strain 10.8 % (5-7 behind, 15-30 at the gorge corner), seams front 66 / 111, back 134 / 127;
  shape_fall_landing PASS. Looks: toile/toile_sheet.png, cut/cut_3d.png, r3f/look_neck_cut3d.png. Judged: no ruffle,
  lands on the shoulders, still reads as a band behind the neck; the flat is not an undercollar.
- NOT DONE (budget): merge of main, deadcode check, test_toolsets / test_readme and tool texts (garment_toile's
  description / cloth_tools.md may still describe the step-6 collar declaration with stand_mm / fall_mm / end_mm).

## Left
- style_lengths: compare only where step 1 estimated the same line (collar neck edges, shoulder): R3d item 6.
- Downstream readers (chain_garment piece_start, garment_details, draft_own_tool.flat_check) read FLAT from a FreeSewing
  draft dir, not pattern.json. ~120 "step 4" texts in chain_* / draft_* still mean the flat pattern.

NEXT: R3f-2: merge main + checks + tool texts (above); the fall must lie OUT over the shoulders (outer 0.996 x neck)
and stand / fall develop together (lean the stand, or a shrunk-stand rest shape); the gorge corner's strain; the
garment's front.L:neck runs to the collar point (lapel top = roll top + collar_top to its corner) and back.L:neck is
127 vs the toile's 99 mm seam per half: find why before seams can equal. Then R3e's: darts from the strain ridge (darts_drafted; back blade and front chest strain show on flat_sheet); the
collar's side curl (fall too long for its landing at the side: x0.959); girths: hips / seat rings (back.R), chest -44 at
the underarm (which piece loses width), side / sleeve_under tapes; style_lengths (compares step 1's estimates).
