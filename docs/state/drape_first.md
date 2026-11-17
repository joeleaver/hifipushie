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

## R3f-2 (C498): collar seams name the same runs (neck_corner, NECK_LEAN_M, runs_of, split_gorge); fall along the surface
## R3f-3 (2026-11-16, C499): one roll line (toile_collar module doc)
- The lapel's roll line carried straight up past its top to the side stand (2/3 stand, the draft rule), round the back;
  the stand a span leaning out in front of SPAN_FROM; the fall lands from the roll's foot. Neck edge: seam (ends at the
  HPS on this toile) + the front's neck down to the roll top (45) + the lapel's top (47).
- Proof /mnt/data/hifipushie/r3f3 (go.sh; toile6 / mark2 / cut2 logs; look.py = neck look WITH the body, body.npz).
  toile PASS; mark PASS; cut: roll joins the lapel's at 8.8 deg; outer 44 mm out at the side; flat 383 x 136, outer
  1.31 x neck (shape_fall PASS 1.313), bow 62: a crescent but lumpy, strain 14.6 %; shape_fall_landing 0.929 FAIL;
  collar seams FAIL: front.L -15.0, front.R -12.1, back.L +5.7, back.R +4.0 (R3f-2 had matched them).
- Looks: r3f3/look6.png (reference | neck front / left / back), r3f3/flat_collar6.png (strain colour), look_r3f2.png.
  Judged: NOT the reference yet. Front view: the roll now runs straight up from the lapel (right), but the collar still
  rises beside the neck and the fall at the side lies on the shoulder TOP (edge-on from the front), so no broad band on
  the upper chest / shoulder slope as in the reference. Tries: stand 2/3 walked (no change), 1/3 (small), span (ears).
- In the way: (1) the toile's neck seam ends AT the HPS and the gorge point (roll top) is 20 mm outside it: the collar's
  front neck is a 45 mm vertical edge, so the side zone has no neckline to sew a lying collar to; (2) the leaning stand +
  wide fall don't develop together (strain 14.6 %, front seam short); (3) the earlier looks had no body: look.py now
  renders it (the neck hides the back collar as in the reference).
## Left
- style_lengths (compare only like lines); downstream readers (chain_garment piece_start, garment_details,
  draft_own_tool.flat_check) read FLAT from a FreeSewing draft dir, not pattern.json; ~120 "step 4" texts mean the flat.
- R3e's: darts from the strain ridge; girths (hips / seat back.R, chest -44); side / sleeve_under tapes.

NEXT: R3f-4: the front neck. Read the reference's neckline (front view: where the collar's neck edge runs from the HPS to
the gorge) and cut the toile's front neck there (not the opening's vertical edge), so the stand sits on a real neckline
and the fall lies on the upper chest; then the seams (front -15) and the strain (14.6 %). Then style_lengths.
