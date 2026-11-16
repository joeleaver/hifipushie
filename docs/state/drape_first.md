# STATE: drape first (docs/proposals/drape_first.md; approved 2026-11-16)

Steps 4-6 rebuilt the draper's way: TOILE (the garment's 3D surface on the body), MARK, CUT AND FLATTEN.
Runs R1 (C489) -> R2 (C490) -> R2b (C491) -> R3a (toile, C492) -> R3b (mark + cut, C493, this) -> R3c (collar).
History: docs/notes (grep C489-C493); spikes/r1_*, r2_*, r2b_* (R3c still reads r2b_flat.py's lapel unfold + collar).

## R3a (C492): garment_toile = step 4 (toile*.py). Proof /mnt/data/hifipushie/r3a (all rows PASS; sheet in ws).

## R3b (2026-11-16): garment_mark = step 5, garment_cut = step 6
- garment_mark(name, garment, declarations) (mark.py, mark_lines.py, mark_split.py, mark_tool.py): marks [{name, line
  {kind armhole | centre_back | panel (after, above) | shoulder | under_sleeve (fore_in_mm, hind_in_mm) | level (at)},
  region, into [g<0, g>0]}] in order, ".L" mirrored; absent {piece: why}; runs {"piece:edge": front|back|top|bottom}.
  Each mark cuts its region EXACTLY (one mesh, a label per face); other than two parts = refused by name. Rows marks,
  separate, pieces, seams (+ INFO extra_seams). Writes <look>/mark/mark.npz (V, F, lab, names), mark.json, mark_sheet.png.
- garment_cut(name, garment, declarations) (cut.py, cut_tool.py, flatten.py): free {piece: {edge: top|bottom|side|[..]}},
  ease {"piece:edge": [lo, hi]}. Each piece one disc, LSCM + ARAP, strain per piece + where; outline runs named (step 1's
  seams, to_<piece> for unnamed pairs, declared free edges); plain seams trued to their mean (scaled about the run's
  start); the block (pieces P flat + P3 3D outline, arcs, seams, closures, omit) -> draft_own_gate.gate = step 6's gate.
  Writes <look>/cut/flat.npz (per piece U, F, V, strain, outline), pattern.json (the block), cut.json, flat_sheet.png.
- Record: steps 5 / 6 name garment_mark / garment_cut; READS["5"] = 0, 1, 2, 4. chain_garment's from_chain writes only 8.
- Proof /mnt/data/hifipushie/r3b (ws = r3a copy; mark_decl.json, cut_decl.json, run.py mark|cut, mark.log, cut.log):
  STEP 5 PASS: 9 marks (armhole 616.7 mm each side, centre_back 684.6, front_side 677, side_back 470, sleeve seams 907),
  10 pieces (front 1414, side 528 / 554 L / R, back 1539 / 1514, sleeve top 1174, under 585 cm2), 17 step-1 seams marked,
  11 with absent pieces (collar, undercollar, facings, canvases), 4 underarm pairs step 1 doesn't name (under sleeve to
  front / back: the tailor's rule vs step 2's side share). STEP 6 FAIL: PASS cut_flatten, seams (21, trued), seam_ends,
  sewn 28/28, cut, closures, shape_seam_curve; FAIL darts_drafted (front_dart: no dart cut), style_lengths (shoulder 192
  vs step 1's 144 mm; back armhole 191 vs 129), girths + piece_tapes (no tapes declared on toile pieces), planned_folds
  (lapel roll, sleeve hems: no folds written). Strain mean: front 1.15 %, side 0.36, back 1.97 (36 % of area > 2 %: the
  shoulder blade, a dart / ease), sleeve top 1.02, under 0.89 (max 42 % stretch at the underarm web). Seams off as
  flattened: 17 of 21 > 1 %, worst 21.9 % (front / under sleeve at the underarm), all within 0.11 % after truing.
  Looks: r3b/ws/garrett/garments/jacket/mark/mark_sheet.png, cut/flat_sheet.png (untrued outlines, strain red at 6 %).
  Beside R2b's flats (r2b/out/flat_sheet.png): same pieces and method; no lapel unfolded onto the front yet.
- Tests: tests/test_mark_cut.py (open cylinder torso: one region each, strain < 0.5 %, seams equal, gate seams / sewn
  / cut PASS, a non-separating mark refused).

## Left
- R3c: the collar (own flat round the toile's neck); the lapel unfolded about its roll line onto the front (R2b's
  method: toile part lapel.L, roll_line); the facing / canvas from the front's flat (declared absent now).
- Step 6's gate FAILs to answer: tapes on toile pieces (girths / piece_tapes rows want draft declarations: write
  tapes from the toile's levels), folds from step 2 (lapel roll, hems), darts from strain (front / back), the cap ease
  (cut cap = armhole: 0 %), the shoulder length vs step 1. The under sleeve's underarm web flattens badly (the tailor's
  seams run through the cone's web).
- Downstream readers (chain_garment piece_start, garment_details, draft_own_tool.flat_check) read FLAT from a
  FreeSewing draft dir; they don't read pattern.json yet. ~120 "step 4" texts in chain_* / draft_* still mean the flat
  pattern (only the tool texts touched here say step 6).

## R3b-2 (2026-11-16): the coordinator's fast-suite failures fixed in the code
- The build is made FROM step 6's cut and never writes 5 / 6. garment_record.from_chain: a build that stops (stage gate,
  structure, refusal before any hang) is step 7's failure (the first step reading the build; back to the gate's step);
  the hang stays step 8. chain_stages.BACK: arrange / sew / start / chains / surfaces go back to step 6 (crease: 2).
  chain_presim.threads_gate: back to step 6 (the cut) or the toile (4), not "the chains (step 5)". look_chain's build look
  goes on 7 / 7a (was 6: now the cut's flat sheet); write_7a's fallback look is step 7's.
- Tests changed to the new route: test_chain_garment (_presim_model writes 0-6 as mark / cut would; step 8 back to 6),
  test_chain_stages (back_to 6; a stage failure on step 7), test_find_tool (7 results: the workflow now leads with
  toile / mark / cut). test_recolour_masks passed alone (load). test_toolsets::test_short_descriptions_point_at_the_guide
  fails on main too (export_asset's description 727 > 700 chars; not this branch).

## R3c (2026-11-16, budget hit before tests / ledger): step 6 makes the lapel, facings, canvases and collar
- cut_made.py (order: flaps, layers, collar; ".L" serves ".R"), cut_flap.py (toile part unfolded about its roll edge onto
  its piece, reflected, zipped to it; fold row <fold>.a/.b), cut_layers.py (a layer traced off its host's flat by a line of
  anchors [edge, mm, toward]), cut_collar.py (crescent drafted from the neck edges' flat lengths, outer by draft_fall's
  rule, then fitted by chain_net.project with the toile as contact; outer spread until the fit stops stretching it).
  cut_tool: block(folds), look3d -> cut/cut_3d.png.
- Proof /mnt/data/hifipushie/r3c (ws = r3b copy, cut_decl.json, cut.log): PASS flaps (hinge 2.7 mm mean, roll 367 / 358
  mm, across), layers (facing 890 cm2, canvas 851), seams 32, sewn 28/28, cut 16, caught, shape_fall 1.094,
  shape_fall_landing 1.032; FAIL collar (lengths held to 0.58 mm worst at the front neck [-0.075, -0.053, 1.53]:
  contact vs exact links), darts, style_lengths (neck edges vs step 1's estimates, shoulder, back armhole), girths,
  piece_tapes, planned_folds (only the sleeve hems now). Collar flat 488 x 104 mm, bow 32 mm (a crescent).
- Judged: the flat collar is curved; on the toile it STANDS like a ruffled band (lands 2 mm below the neck seam at CB
  vs d 12): it does not roll and fall like the reference. Canvas is a wedge (line to the front 150 mm above the hem).
- NOT DONE: tests/test_cut_made.py (written in the transcript: flap unfold, layer seam, collar draft+fit on a cylinder),
  ledger row (next free C494), cut.py docstring, README / toolset text for the new garment_cut declarations, deadcode.

NEXT: R3c-2: write tests/test_cut_made.py + ledger C494; make the collar's fall turn DOWN (start the fall lying on the
toile below the neck seam, not flared; stand lean); then R3d (darts, hems, tapes, cap ease).
