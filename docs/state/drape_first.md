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
## R3f-6 (C503): layers (cut_layers: "60%" anchors, host split at the line's ends, multi-run lines refused); the open
  toile cut at its traced edges left each front ~62-97 mm + lap short (chest 952 vs 968 + 140): fixed by R3f-7.
## R3f-7 (2026-11-17, C504): the pattern is cut from the CLOSED toile
- toile_style.cut builds the CLOSED state always (t.meshes, toile.npz's plain parts: steps 5 / 6 read it); worn open, the
  OPEN state too (t.worn, its numbers t.info["worn"], toile.npz open/<part>, open/roll_line, open/collar_grid): the look,
  the outline rows, later the hang's start. lap_mm required for any opening. closed_buttons and closure_marks' carried
  path deleted: buttons on CF of the closed fronts (_on_centre). held_flatten deleted: the collar flattened as draped;
  its seams report collar / garment flat and 3D lengths + where they part in 3D (off_row_mm, gap_max_mm, gap_at_mm,
  wiggle_pct: cut_collar._apart).
- Proof /mnt/data/hifipushie/r3f7 (go.sh; toile_decl6, mark_decl, cut_decl6; toile1 / mark1 / cut3 logs): toile PASS,
  mark PASS (front.L 1417 cm2 vs 958 open). Cut PASS: cut_flatten, flaps, layers, seams, sewn, closures, caught, panels
  (front 0.41 / plan 0.40, back 0.37, side 0.22), shape_fall, shape_cap. FAIL: collar (front runs), darts_drafted,
  style_lengths, girths (chest -43 at the underarm as R3e; hips ring misses pieces: -224; biceps / chest tapes unnamed
  on sleeve_under / side), piece_tapes + place (undercollar / collar name no girth / place), shape_fall_landing (-6 %).
- COLLAR: back runs match (flat 94.6 / 93.3; 3D 99.3 / 99.7). Front: flat 93.7 vs 100.8; 3D 98.2 vs 102.3: the front's
  neck edge has a 7.1 mm jog AT THE GORGE POINT (69.6, -53, 1504 mm: where the front neckline meets the lapel's top),
  18 mm of it off the collar row, 3.9 % wiggle; the collar row rounds the corner. Then the flatten shortens the collar's
  neck 4.6 % (strain 8.7 % mean, red throughout): the stand + fall don't develop together.
- Looks: r3f7/cut_vs_open_toile.png (open toile look over the closed cut pieces), r3f7/cut_3d.png, r3f7/flat_sheet.png.
  Judged: the fronts close (over front laps the under at CF, lapels turned to a narrow V as closed); the collar a
  crescent but humped at CB with high strain; buttons placed on CF (closures PASS, marks on both fronts).
## Left: downstream readers (chain_garment piece_start, garment_details, draft_own_tool.flat_check) read FLAT from a
  FreeSewing draft dir, not pattern.json; side / sleeve_under tapes.
NEXT: the gorge-point jog (toile_style.front_neck meets the lapel's lifted top: make the front's neck edge and the
collar row one curve through the gorge point, in 3D); the collar's flatten strain (8.7 %: stand / fall shaping, a
tailor's stretch-and-shrink is a declared ease, not a hidden length); girths (hips ring, chest at the underarm); collar
piece tapes / place; darts from the strain ridge; style_lengths (compare like lines).
