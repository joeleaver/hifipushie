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
- Gate on the jacket (R3a-2, C492): the outline compared LIKE WITH LIKE (the picture's body / pose are not the model's):
  side = its profile off the toile's torso edge less the median, the arm zone (above underarm - 3 cm) left out; hem =
  its height (median); sleeve end = its length along the arm (a FAIL -> back to step 0's height). The drop's flare is
  calibrated where the hem tape is read (was 6.3 mm short).
- Proof: /mnt/data/hifipushie/r3a (ws = s4-31 copy, decl.json, run.py, run2.log; run.log the first run); sheet
  r3a/ws/garrett/garments/jacket/toile/toile_sheet.png. ~40 s. ALL PASS: girths chest 1111.6 / 1108.2, waist 987.7 /
  987.6, hips 1103.9 / 1103.1, hem 1135.7 / 1138.8 (R2b 1137.2); clearance +1.5 mm; closed (1 surface, 3 loops); outline
  side p95 4.0 / 3.6 mm (offset +34 / +30 read: the photo's man is wider), hem height 8 mm, sleeve length 15 / 12 mm.
  front_edge / roll / collar_top INFO (built closed / no collar). Lapel 60.9 mm (R2b 60.7), pad 4 mm.
- Tests: tests/test_toile.py (synthetic capsule body: girths, clearance, closed, tube, lap; refusals by name) PASS;
  test_garment_record / test_draft_own / test_garment_details assert 4 toile, 5 mark, 6 flat; test_toolsets ADDED.
- Step table (docs/state/garment_steps.md) rows 4 toile, 5 mark, 6 cut and flatten. draft_pattern / pattern_check
  write step 6 (the flat-pattern checker R3b feeds); FreeSewing is no longer step 4's source.

## Left for R3b / R3c
- R3b: MARK (step 5) and CUT AND FLATTEN (step 6) as tools from toile.npz (spikes/r2b_flat.py's method), the flat
  pattern in draft_pattern's form so pattern_check gates it; retire chain_garment's from_chain writes of 5/6; the
  ~120 "step 4" comments / messages in chain_* and draft_* still mean the flat pattern (only details / draft_own_tool
  texts renamed).
- R3c: the collar from its own flat fitted round the toile's neck.

## R3a-3 (coordinator's two faults; budget hit mid-fix, UNPROVEN WIP in the last commit)
1. Sleeves short: the sheet shows the toile's sleeve ending above the traced wrist line; the sleeve-end row passed it
   (it projected the photo's points on the MODEL's arm axis: the photo arm is 3 cm further in, so across leaked into
   along and flipped the sign). Found: the photo's sleeve end sits AT the photo's wrist mark (step 2 body mark
   wrist.L 1005,880 px -> x 0.40 z 0.999; trace median z ~0.995); the toile's hem ~24-32 mm short of the model's wrist
   (0.433, 0.98). Also toile_style took the hem point as the NEAREST of 9 axis points by z (4-5 cm apart). The TRACE is
   right (it is read off the picture's own wrist; step 0's 0.973 of shoulder->wrist maps onto a different arm length).
   Done (untested): toile_style.sleeve_hem_point (dense axis; `sleeves.hem` may name a step-2 trace: its place past the
   picture's wrist carried onto the model's wrist along the arm), along_from_wrist, arm_dir; Inputs.wrists field.
   TODO: toile_tool.inputs fills Inputs.wrists ({"photo": mapped body-mark wrist.L (folded), "model": at["wrist.L"]
   x,z}) from _mapped's placement; validate() accepts a step-2 trace for sleeves.hem; toile_gate._sleeve_end = d =
   along_from_wrist(trace, photo wrist) - along of the hem point from the model wrist (signed: + = toile short), FAIL
   past SLEEVE_MM 10; decl.json sleeves.hem "sleeve_end.L"; rerun; a test (short sleeve FAILs).
2. Back neck stand: the neck tape's back point (cb_neck z 1.560) is where the neck turns vertical, 11 mm ABOVE the side
   neck points (hps z 1.549): cut there, the toile climbs the back of the neck (R2b hid it under its collar; same
   neckline, d4 lines.json). Done (untested): toile_style.neckline lowers the tape's back to hps - BACK_NECK_DEPTH_M
   (15 mm, cos^2 to CB). TODO: gate row `neck` (back toile points, y > hps y, no higher than hps z + 3 mm: catches the
   old cut at +11), rerun, look at the side / back tiles, a test.

NEXT: R3a-3 finish the two TODOs above (start: toile_tool.inputs wrists), rerun the jacket, then Joe / the coordinator
judges the sheet; then R3b mark + cut/flatten.
