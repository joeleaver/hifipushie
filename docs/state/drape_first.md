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
## R3f-5 (C502): the toile built in step 2's WEAR STATE (ties: none done up = open; missing = refused). OPEN: no lap, each
  front's edge where traced (cutaway below the break), roll as traced; girth rows read t.closed_mesh. Proof r3f5.
## R3f-6 (2026-11-17, C503): step 6 cuts the open jacket
- BUTTONS: step 4 records closed_buttons (toile_style.closed_buttons: on the closed state the button is on CF, lap_mm in
  from the edge along the surface; lap_mm now required for an open opening with buttons); cut_tapes.closure_marks
  carries them to each open front: on its own flat, at the button's z on the closure edge, from_edge_mm square in.
- LAYERS (cut_layers): anchor mm may be "60%" of the edge; the host's outline is split at the line's end anchors (two
  polygons closed by the line; the side holding `keeps` is the layer) instead of running the line on 5 m past its
  ends (that run-on re-entered the concave armhole / cutaway: two `inner` / `armhole` runs). A line leaving the host
  between anchors, or any layer edge in 2+ runs, is REFUSED by name. Jacket: facing hem anchor "60%" (hem 84 mm);
  canvas = chest piece: armhole 30 mm up from the underarm -> front edge 320 mm up from the hem (just below the break):
  edges armhole, front, inner, neck, notch, shoulder (armhole 50 -> front 200 still made 2 inner runs: refused).
- COLLAR (cut_collar.held_flatten): cause: the plain flatten shortened the collar's neck row ~7.5 % (front 101 3D -> 94
  flat; the stand leans out, the fall unfolds and the ARAP spreads it into the neck), and the front run is 4 mm short in
  3D already. Now ARAP against a rest stretched along the rows by e at the neck row tapering to 0 at the roll, e per
  garment neck edge by secant passes so each run = the garment edge's flat length. Rest e: front +31-40 %, back -5 %
  (the back piece's own flat neck is 6.5 % under its 3D: 93.8 vs 100.2): large; the collar's strain 8.5 % (vs rest).
- Proof /mnt/data/hifipushie/r3f6 (go.sh; toile_decl6 = lap_mm 20; cut_decl6; toile1 / mark1 / cut3 logs): toile PASS,
  mark PASS; cut: cut_flatten, layers, collar (seams 104.5/104.5, 104.7/104.6, 93.4/93.3, 93.2/93.4), seams, caught,
  closures PASS. FAIL: darts_drafted, style_lengths, girths, piece_tapes, place, panels (front 0.34 vs plan 0.40).
- Looks: r3f6/cut_3d_3.png, r3f6/flat_sheet_3.png. Judged: pieces as an open jacket's: fronts with the lapel on,
  a long narrow facing, a chest canvas, collar a crescent (ends bumpy, red with strain everywhere). The buttons are
  20 mm in from the open front's edge, where they would be on that edge closed, BUT the open front has no cloth to
  reach CF: the open toile is the closed field cut at the traced edges, so each front is ~62 mm (break) to 97 mm
  (waist) + lap too narrow (chest 952 vs body 968 + ease 140; panels front 163 mm a piece). Closed, these fronts
  would not meet: the buttons are right on the cloth, the cloth is wrong.
## Left: downstream readers (chain_garment piece_start, garment_details, draft_own_tool.flat_check) read FLAT from a
  FreeSewing draft dir, not pattern.json; R3e's girths (hips / seat back.R); side / sleeve_under tapes.

NEXT: the open toile's fronts must keep the closed garment's cloth (the open front = the closed front swung back about
the side, not cut at the traced edge): build the fronts closed for the pattern and open only for the look, or cut
step 6 from the closed toile and carry the open state as wear; then panels / girths; collar ends and strain; darts
from the strain ridge; style_lengths (compare only like lines).
