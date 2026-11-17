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

## R3f (C497): the collar draped on the toile (toile_collar.py), cut and unfolded at step 6 (cut_collar.py); proof r3f.
## R3f-2 / R3f-3 (C498, C500): collar seams name the same runs; one roll line (toile_collar doc); proofs r3f2, r3f3.
## R3f-4 (C501): front neckline gorge point -> HPS (toile_style.front_neck); fall lands on collar_top past its corner.
  Proof /mnt/data/hifipushie/r3f4: collar seams front -5.5 (flatten 9 % short), back +2 / +1; built CLOSED: V narrow.
## R3f-5 (2026-11-17, C502): the toile built in step 2's WEAR STATE (Joe: "Build it open")
- Wear state: step 2's ties (closure_ties: fastened [] = open, all = closed) for the declared opening.closure
  (toile_tool.wear_of -> Inputs.wear); none recorded or partly: refused by name (validate and Toile.build); lap_mm only
  needed closed. Jacket: ties.front_closure fastened [] of 2 ("both buttons free ... shirt placket and belt show").
- OPEN (toile_style.closure): no lap, no roll shift; below the break each front's edge = front_edge.L past its corner
  (x 62 mm at the break 1.195, 74 at 1.087, 97 at 0.979, 167 at the hem: cutaway); above the break the roll as traced
  (0.062 -> 0.069, near vertical) then front_neck; halves mirror it (two edges apart). Closed unchanged.
- Girths: the open toile is the closed field cut at the traced edges; girth rows read t.closed_mesh (the toile before
  the fronts were opened: the plan's ease is the garment's worn closed, C388): chest +2.6, waist +0.2, hips +0.9.
- Item 2 (hang straight from the chest at an open front): already so: at x 0.08 the toile's y holds -0.172..-0.175 from
  z 1.28 to 1.04 (the waist ease 50 mm keeps it off the body). No code.
- Collar (toile_collar): an open roll turns back over the shoulder at its top, so "carried straight on" put the side
  roll 41 mm BEHIND the neck seam's end (stand leaning back); now RH no further back than E0. Side top z 1.565 at x
  0.057 (collar_top trace 1.578: 13 mm LOW, no longer climbing the neck); outer / neck 1.34 per half (208 / 155).
- Proof /mnt/data/hifipushie/r3f5 (go.sh, toile_decl5.json; toile2 / mark1 / cut1 logs): toile PASS (14 rows PASS),
  mark PASS (10 pieces). Cut FAIL: collar seams front.L -10.9 / front.R -11.0 (was -5.5); cut_flatten: closure_marks
  (cut_tapes) put buttons where x = 0 crosses the fronts: an open front doesn't reach CF; layers: facing anchor hem 90 mm
  > front.L:hem 84 (the cutaway), canvas 'inner' / 'armhole' 2 runs. Collar flat strain 7.6 %, wavy crescent.
- Looks: r3f5/look1.png (open, before the side fix), look2.png (neck look with the body, beside the reference's crop);
  toile front with step 2's traces: ws/garrett/garments/jacket/toile/toile_sheet.png; flat: .../cut/flat_sheet.png.
  Judged: OPEN like the reference: the body (shirt) shows in a wide V of constant width down to the hem, the lapels lie
  back on the chest about a near-vertical roll; the collar's fall lies on the shoulder slope in front of the side neck
  point; at the side and back it is a stand + fall band round the neck (as the reference: it stands behind the shirt
  collar), 13 mm lower than traced at the side.
## Left
- style_lengths (compare only like lines); downstream readers (chain_garment piece_start, garment_details,
  draft_own_tool.flat_check) read FLAT from a FreeSewing draft dir, not pattern.json; ~120 "step 4" texts mean the flat.
- R3e's: darts from the strain ridge; girths (hips / seat back.R, chest -44); side / sleeve_under tapes.

NEXT: step 6 for an open garment: closure_marks place the buttons from the closed state (CF a lap inside the front
edge, or mark on the closed toile and carry them), facing anchor / canvas lines on the open front; collar front seams
-11 (the collar's flat neck edge short); side stand 13 mm under the trace. Then style_lengths.
