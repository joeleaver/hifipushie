# STATE: drape first (docs/proposals/drape_first.md; approved 2026-11-16)

Steps 4-6 rebuilt the draper's way: TOILE (the garment's 3D surface on the body), MARK, CUT AND FLATTEN.
Runs R1 (C489) -> R2 (C490) -> R2b (C491) -> R3a (toile, C492) -> R3b (mark + cut, C493) -> R3c / R3c-2 (made pieces, C494).
History: docs/notes (grep C489-C494); spikes/r1_*, r2_*, r2b_*.

## Tools (each module's docstring is the spec)
- garment_toile = step 4 (toile*.py). Proof /mnt/data/hifipushie/r3a (all rows PASS).
- garment_mark = step 5 (mark.py, mark_lines.py, mark_split.py, mark_tool.py): marks cut their region exactly; rows marks,
  separate, pieces, seams. Proof /mnt/data/hifipushie/r3b: PASS (10 pieces, 17 step-1 seams).
- garment_cut = step 6 (cut.py, cut_tool.py, flatten.py, cut_made.py, cut_flap.py, cut_layers.py, cut_collar.py): each
  piece one disc, LSCM + ARAP, strain per piece; runs named; plain seams trued; then MADE pieces: flaps (lapel unfolded
  across its roll onto the front), layers (facing / canvas traced off the front's flat), collar (crescent drafted flat
  by draft_fall's rule, fitted by chain_net.project, every flat length held). The block -> draft_own_gate.gate.
  Writes cut/flat.npz, pattern.json, cut.json, flat_sheet.png, cut_3d.png.
- Record: steps 5 / 6 name garment_mark / garment_cut. chain_garment's from_chain writes only 8; a build that stops is
  step 7's failure, back to step 6 (R3b-2).

## R3c-2 (2026-11-16): R3c finished; the collar's fall turned down
- cut_collar.place: the fit STARTS with the fall turned down: back down over the stand GAP outside it, then laid on the
  toile along lay_down's lines (walked square to the neck line in the toile's surface, WALK_STEP); the stand leans in
  (LEAN 0.15). R3c's start flared the fall out inside the toile; the fit stood it up like a ruffled band.
- Proof /mnt/data/hifipushie/r3c (cut_decl.json, run.py cut, cut.log; R3c's log kept as cut_r3c.log):
  collar row FAIL -> PASS: lengths worst 6.74 % (0.58 mm) -> 0.022 % (0.0 mm); lands 2.0 -> 4.5 mm below the neck seam
  at CB (d 12); outer 3D 516.5 = flat 516.5 mm; fall clear >= 3.0 mm; flat 487 x 100 mm, bow 28 mm. PASS flaps,
  layers, seams 32, sewn 28/28, cut 16, caught, shape_fall 1.087, shape_fall_landing 1.024, shape_seam_curve. FAIL (R3d's):
  darts_drafted, style_lengths, girths, piece_tapes, planned_folds.
- Judged (cut/cut_3d.png neck views): smoother, a visible roll with a short fall turned down; still reads as a band
  standing above the shoulders, not the reference's collar lying on them.
- WHY NOT d: the line the fall lands on behind the shoulder (at d down the toile) is x1.14 the rule's flat outer on the
  jacket (x1.06 on the test's cone neck): the rule's outer edge is too short to reach d, so the fit rides it up to where
  it fits. Tried spreading the outer to that laid line: lands 8.1-10.3 mm, lengths still held, but outer/neck 1.25-1.36,
  bow 94-133 mm and shape_fall_landing FAILs (x1.17-1.28): reverted; the ratio is reported in the collar row
  ("landing line ... x1.1443 the flat outer"). Decide: is draft_fall's flat-offset rule or the toile's 3D landing line
  the truth for the outer edge? (A walk square to a curved neck fans at the side neck point; maybe the walk overstates.)
- Canvas: tried line [["armhole", 30, "hem"], ["hem", 150, "front"]] (a full-front canvas): the line crosses the armhole
  twice (edges armhole_2, inner_2..4) -> layers FAIL; reverted to the wedge. Needs a line kind that stays inside (e.g.
  an anchor on the side seam) or a chest-canvas shape rule.
- Tests: tests/test_cut_made.py (flap unfolds across its roll on a flat sheet; facing's front seam = host's edge, gorge 60
  / hem 80 mm; collar on a cone neck: lengths held, outer 3D = flat, outer edge back down at the neck seam level, edges
  named, fold). Brief's list: 89 pass; FAIL test_toolsets::test_short_descriptions (export_asset 727 chars: on main too).
  Deadcode clean.

## Left
- The collar's outer edge length (above); the canvas line.
- Step 6's gate FAILs: tapes on toile pieces (girths / piece_tapes), folds from step 2 (planned_folds: sleeve hems),
  darts from strain (front / back), the cap ease, the shoulder length vs step 1 (style_lengths; collar neck edges vs
  step 1's estimates +42-74 %). The under sleeve's underarm web flattens badly.
- Downstream readers (chain_garment piece_start, garment_details, draft_own_tool.flat_check) read FLAT from a FreeSewing
  draft dir, not pattern.json. ~120 "step 4" texts in chain_* / draft_* still mean the flat pattern.

NEXT: decide the collar's outer-edge rule (draft_fall vs the toile's landing line), then R3d (darts, hems, tapes, cap
ease, a chest-canvas line).
