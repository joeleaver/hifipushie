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
## R3f-3 (C500): one roll line (toile_collar module doc); proof /mnt/data/hifipushie/r3f3 (look.py = neck look WITH the body)
- The lapel's roll line carried straight up to the side stand (2/3 stand), round the back; collar seams regressed
  (front -15 / -12, back +6 / +4), landing 0.929 FAIL, strain 14.6 %; the fall at the side walked back to the neck.
## R3f-4 (2026-11-16, C501): front neckline + the fall lands on the traced outer edge
- toile_style.front_neck: above the roll's top (gorge point (0.069, 1.509), step 2's roll.L top) the over front's edge runs
  straight (front view) up and in to the HPS ((0.061, 1.548), step 3's neck tape side): drop 39 mm, 8 mm out; the old
  vertical edge + jog at the HPS gone. The collar's front neck = that edge (front_neck_edge), its gorge = the lapel
  mesh's own top edge (gorge_edge): front neck 53.7, gorge 51.3 mm (3D; garment 59.3 + 43.0).
- In front of the HPS the fall lands on collar_top.L past its corner (traced_outer / land_traced, OUTER_IN_M 10 mm).
- Proof /mnt/data/hifipushie/r3f4 (go.sh; toile_decl4.json = lapel 66 mm, fall 42; logs toile8 / mark7 / cut7):
  toile PASS, mark PASS; collar seams front.L -5.6, front.R -5.4, back.L +2.1, back.R +1.1 (FAIL > 3 in front);
  shape_fall 1.084 PASS, shape_fall_landing 0.965 PASS; strain 11.6 % (was 14.6); flat a crescent, bow 44.5, ends wing up.
- Looks: r3f4/look1.png (landing), look2.png (+ front neckline), look3.png (+ lapel 66); flat_sheet7.png.
  Judged: a green band now lies on the upper chest from the neck side to the notch (moved); the collar still stands
  round the neck at the side to ~z 1.60 (trace 1.578); the V between the lapels stays narrow: the toile is CLOSED (break
  at CF + lap) while the reference is open, roll near vertical at x ~0.075. Lapel 61 -> 66 (crop read 65-69 mm, scaled
  by the neck width): barely visible. Three tries; stopped.
- In the way: the front seam's 5.5 mm is the collar's flatten (3D 105 vs garment 102, flat 95 vs 101: the collar's
  neck edge comes out 9 % short where the stand leans and the fall unfolds, strain 11.6 %); the HPS end of the front
  edge climbs 11 mm up the neck wall (a constant-x cut on the neck's side).
## Left
- style_lengths (compare only like lines); downstream readers (chain_garment piece_start, garment_details,
  draft_own_tool.flat_check) read FLAT from a FreeSewing draft dir, not pattern.json; ~120 "step 4" texts mean the flat.
- R3e's: darts from the strain ridge; girths (hips / seat back.R, chest -44); side / sleeve_under tapes.

NEXT: R3f-5 (C502, in progress): the toile built in step 2's wear state (ties: none done up = OPEN): fronts unlapped,
edges on front_edge, roll as traced; then the collar on the shoulders.
