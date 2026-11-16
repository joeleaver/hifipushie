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

## Open on this branch (coordinator, after the fast suite; NOT fixed: the run's budget ran out before a test ran)
- test_chain_garment::test_presim_awaits_approval_then_resumes_from_the_saved_build ('STOPPED BEFORE THE HANG' missing),
  test_chain_garment::test_step8_fails_on_faces_past_the_cap ('todo' != 'failed'), test_chain_stages::
  test_the_job_ends_stage_failed_and_the_record_shows_the_stage (KeyError 'step'): from_chain now writes only step 8, and
  the presim (7a) / hang (8) bookkeeping still reads steps 5 / 6 as the chain build's. Fix the code for drape first (7a /
  8 must not wait on 5 / 6 written by the chain build; the stage_failed answer must not index a step it no longer
  writes), then change any test that asserts the old route, naming it.
- test_find_tool::test_find_tool_gives_params_and_an_example: the Clothes workflow text (mcp_app) now names
  garment_mark / garment_cut: update its expected text.
- test_recolour_masks::test_bad_masks_refused timed out (load?): run it alone.

NEXT: fix the four tests above on this branch (run only those files, -m ""), commit; then Joe / the coordinator judges
r3b's mark_sheet + flat_sheet; then R3c (collar, lapel unfold, facing) and the step-6 FAIL rows (tapes, folds, darts).
