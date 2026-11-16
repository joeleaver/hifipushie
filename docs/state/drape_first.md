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
- Gate (C492): girth per level, clearance, closed, NECK (no back toile point over the side neck points + 3 mm: a cut at
  the neck tape's back climbed the neck as a stand, +11 mm), outline LIKE WITH LIKE (the picture's body / pose are not
  the model's): side = profile off the toile's torso edge less the median, arm zone left out; hem = height (median);
  sleeve end = length PAST THE WRIST, each read from its own wrist along the arm (signed, +-10 mm; the R3a-2 row read the
  photo on the model's axis and passed sleeves 24-32 mm short). sleeves.hem may name a step-2 trace (its distance past
  the picture's wrist mark carried onto the model's wrist); the back neckline is drafted HPS - 15 mm at CB.
- Proof (R3a-3): /mnt/data/hifipushie/r3a (ws = s4-31 copy, decl.json with sleeves.hem "sleeve_end.L", run.py, run3.log;
  run with HIFIPUSHIE_ASSETS=<repo>/workspace/_templates). Sheet r3a/ws/garrett/garments/jacket/toile/toile_sheet.png.
  ALL PASS: girths chest 1111.6 / 1108.2, waist 987.7 / 987.6, hips 1103.9 / 1103.1, hem 1135.7 / 1138.8; clearance
  +1.6 mm; closed (3 loops); neck -0.7 mm (CB cut z 1.534, tape 1.560, HPS 1.549); side p95 4.0 / 3.6; hem height 8 mm;
  sleeve end L 0.0 (by construction), R +3.0 mm short; sleeve hem z 0.987 (was 1.009). Looked: the sleeves end at the
  traced lines; at CB the toile stops at z 1.534 where the back still slopes (the neck turns vertical ~1.56); the back
  view still reads a round neck at the side neck points (no collar yet: R3c).
- Tests: tests/test_toile.py (synthetic body: girths, clearance, closed, tube, lap, neck, a short sleeve FAILs, a hem
  from the trace PASSes, a back-neck stand FAILs; refusals by name) PASS;
  test_garment_record / test_draft_own / test_garment_details assert 4 toile, 5 mark, 6 flat; test_toolsets ADDED.
- Step table (docs/state/garment_steps.md) rows 4 toile, 5 mark, 6 cut and flatten. draft_pattern / pattern_check
  write step 6 (the flat-pattern checker R3b feeds); FreeSewing is no longer step 4's source.

## Left for R3b / R3c
- R3b: MARK (step 5) and CUT AND FLATTEN (step 6) as tools from toile.npz (spikes/r2b_flat.py's method), the flat
  pattern in draft_pattern's form so pattern_check gates it; retire chain_garment's from_chain writes of 5/6; the
  ~120 "step 4" comments / messages in chain_* and draft_* still mean the flat pattern (only details / draft_own_tool
  texts renamed).
- R3c: the collar from its own flat fitted round the toile's neck.

NEXT: Joe / the coordinator judges the R3a-3 sheet and approves step 4 on the jacket; then R3b mark + cut/flatten.
