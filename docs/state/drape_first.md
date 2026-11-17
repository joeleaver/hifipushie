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
## R3f-10 (2026-11-17, C509): the roll line drawn ON the toile (toile_flap.roll_on_surface)
- One row on the surface pinned at CB (stand height), at the notch trace's top PIN_BACK (2) columns behind the side neck
  point (raised once so the side neck point reaches it) and R0; faired by bending along the surface, the lapel's roll
  running on below R0. Deleted: the Hermite through the air, ROLL_FROM. New info: roll_side_deg / _z_mm, trace_top_z_mm,
  stand_front_area_pct (stand / collar area seen from the front, side neck -> gorge).
- Proof /mnt/data/hifipushie/r3f10 (go.sh; toile1 / mark1 / cut1.log; dev_1..6.png; pin0/, pin2/ logs): toile PASS, mark
  PASS (gorge 46.5 / 46.5). Closed: side neck z 1577.3 vs trace top 1577.6 (R3f-9 ~1546); turns at the gorge 17.1, side
  neck 28.6, max 41.3 deg (85 mm from CB, the pinned top; R3f-9 22). The roll peaks 7 mm above the trace behind the side
  neck. Stand from the front 6 % of the collar's area (an edge 1-4 mm wide; sample count 81 %, edge-on).
- LOOK dev_6.png: the collar rises beside the neck to the trace's top like the reference, one piece with the lapel.
- COST: the collar flattens worse: strain 13.6 % (R3f-9 6.0), roll 335 3D / 300 flat; seams front 46.3 / 51.3 (was
  44.2), back 105.6 / 93.3 (was 93.2). PIN_BACK 0 (side pinned, 64 deg turn): strain 15.4, front 54.2 / 51.3, back +7.
- Cut rows untouched by the roll: flaps (front.R's lapel hinge found on 40 of 68 mm: neck / front split in 2 runs),
  layers (canvas line declared across front.L/R crosses the outline more than twice: a declaration), closures (over
  722 / under 1069 mm). girths:neck and place rows came with main's draft gate (merge), not from the roll.
## R3f-11 (2026-11-17, C510): the collar flattened as SHAPED cloth (cut_shape.py; Joe: "Declared ease")
- garment_cut `shaped` {"piece:run": pct} (+ stretch, - shrink; runs neck / a neck edge, roll, outer): laid on the grid's
  rows, the flat cut against that rest (flatten.rest_edges: per-vertex stretch on the edges), calibrated per run; beyond
  SHAPE_MAX_PCT 8 % (wool's steam shrink ~ a tailored cap's ease) refused by name; neck seams held within their ease;
  RESIDUAL_PCT 3 % strain gate; the row reports what each run ASKS (3D / unshaped flat) and the cone points.
- Proof /mnt/data/hifipushie/r3f11 (cut0.log unshaped, cut1.log shaped cut_decl11.json, collar_flat.png, proto/p5.py):
  asks roll +11.5, outer +3.3, neck front +8.6 / +11.9, back -5.7 / -5.4 %: roll and front neck BEYOND wool. Shaped at
  the limits: strain 13.6 % (unchanged); best any shaping within 8 % (Powell over 4 runs): 13.3 %; even +-30 %: ~10 %.
- WHY: the toile's collar is curved in itself: cone points of +125 deg on the roll row 22 columns from CB (each side,
  likely where the roll's pinned top / the fall's back-vs-front builds meet: unchecked) and a -57 deg saddle at CB. No shrink /
  stretch along a run removes a point defect. LOOK collar_flat.png: not an undercollar (wavy outer, neck edge humped
  at the side necks, red everywhere). Seams still off (front -3.4, back +13.5 mm); the back's own flat neck is 6 % short
  of its 3D (93.3 / 99.7).
## Left: downstream readers (chain_garment piece_start, garment_details, draft_own_tool.flat_check) read FLAT from a
  FreeSewing draft dir, not pattern.json; side / sleeve_under tapes.
NEXT: step 4: remove the collar's cone points (cut_shape.cone_points in the collar row): a roll smooth in the surface at
the side neck (no pinned corner) and the fall built as one surface round the back and down the front; then re-cut with
`shaped` at what each run asks (within 8 %); then flaps (front.R hinge), layers (canvas line), closures, girths.
