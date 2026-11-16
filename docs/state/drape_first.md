# STATE: drape first (docs/proposals/drape_first.md; approved 2026-11-16)

Steps 4-6 rebuilt the draper's way: TOILE (the garment's 3D surface on the body), MARK, CUT AND FLATTEN.
Runs R1 (C489) -> R2 (C490) -> R2b (C491) -> R3a (toile tool, this) -> R3b (mark + cut/flatten tools) -> R3c (collar).
History of R1-R2b: docs/notes (grep C489-C491); spikes/r1_*, r2_*, r2b_* (R3b still reads r2b_flat.py's method).

## R3a (2026-11-16): garment_toile = step 4 (src toile.py, toile_style.py, toile_gate.py, toile_geom.py, toile_tool.py)
- Tool: garment_toile(name, garment, declarations) (tools_cloth). Reads steps 0-3 (garment_record.READS["4"]) and the
  agent's declaration (parts [sleeves, opening, lapel, pad], hang_from, armhole.length_mm, sleeves {ease_mm, crown_mm,
  hem}, opening {lap_mm, edge, buttons}, lapel {roll, top, width_mm}, pad {thickness_mm}); refused by name. Writes
  <look dir>/toile/toile.npz (parts toile, lapel.L/R, pad.L/R as "<part>:V/F", cone, armhole, sleeve axis, roll line),
  toile.json, toile_sheet.png; step 4 (output, gate rows, look).
- Traces placed on the body by step 2's HEIGHT marks + step 1's centre column (the wrists' place across depends on the
  arm pose: with them the jacket's traces sat 5 cm wide). The toile is kept >= 2 mm off the body (union with the body's
  offset: R2b's arm push put it 14 mm in at the underarm).
- Record: steps 4 toile (garment_toile), 5 mark (no tool yet), 6 cut (no tool yet; garment_record.FLAT = "6": every
  pattern reader reads the flat pattern there: draft_own_tool, garment_details_tool, chain_garment piece_start,
  chain_structure, chain_layers, garment_carry). draft_pattern / pattern_check now write step 6 (refused until 5 is
  ready): the flat-pattern checker R3b feeds. chain_garment's from_chain still writes 5/6 (old route: R3b retires it).
- Proof: /mnt/data/hifipushie/r3a (ws = s4-31 copy, decl.json, run.py, run.log); sheet
  r3a/ws/garrett/garments/jacket/toile/toile_sheet.png. 30 s. Rows: girths chest 1111.6 / 1108.2, waist 987.7 / 987.6,
  hips 1103.8 / 1103.1 PASS, hem 1132.5 / 1138.8 FAIL (-6.3, tol 6; R2b 1137.2); clearance +1.5 mm PASS; closed (1
  surface, 0 non-manifold, 3 loops) PASS; outline FAIL hem 25-29 mm (traced hem ~14 mm above step 0's hem height),
  side 40-43 (worst at the armpit: the picture's arms stand off the body), sleeve_end 25-27 (sleeve hem 1.009 vs traced
  0.97); front_edge / roll / collar_top INFO (built closed / no collar). Lapel 60.9 mm (R2b 60.7), pad 4 mm.
- Tests: tests/test_toile.py (synthetic capsule body: girths, clearance, closed, tube, lap; refusals by name) PASS.

## Not done (budget hit at the end)
- Tests still expecting step 4 = draft: test_garment_record (4), test_draft_own::test_tool_writes_step4..., 
  test_garment_details (3), test_toolsets::test_every_tool_in_one_group (garment_toile needs its toolset group).
- Ledger row (C492) not written; docs/state/garment_steps.md step table not updated; main not merged; deadcode check,
  test_codified / test_moved / test_undefined_names not run.

NEXT: R3a finish: add garment_toile to its toolset group, fix the 8 tests for 4 toile / 6 flat, C492 row, step table,
merge main, checks; then Joe judges the toile sheet; R3b mark + cut/flatten.
