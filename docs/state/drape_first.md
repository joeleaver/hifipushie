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
## R3f-10 (C509): the roll line drawn ON the toile (roll_on_surface), pinned at CB, PIN_BACK columns behind the side
  neck at the trace's top, and R0. Proof /mnt/data/hifipushie/r3f10: LOOK dev_6.png right (collar rises beside the neck
  to the trace, one piece with the lapel, stand ~6 % seen); COST strain 13.6 % (R3f-9 6.0). Details: codified.md C509.
## R3f-11 (C510): the collar flattened as SHAPED cloth (cut_shape.py, garment_cut `shaped`, +-8 % per run, refused
  beyond). Proof /mnt/data/hifipushie/r3f11: best shaping within 8 %: strain 13.3 %; cone points +125 / -57 deg.
## R3f-12 (2026-11-17, C511): WHERE THE CONE POINTS COME FROM (proof /mnt/data/hifipushie/r3f12, diag/*.py)
- Not the construction: respacing the roll / outer rows evenly (diag/proto1.py) leaves the cone at 130-136 deg; landing
  the fall's columns along ONE outer curve chosen to even the defect (proto2.py): 110 deg, strain 11.4 %.
- THE CREASE RULE (cut_shape.crease, diag/turn.py): at a roll vertex the angle defect = the roll's turning seen in
  the stand + seen in the fall. A fold lies in flat cloth only where they cancel (the fall flares). R3f-10's roll turns
  +78 deg per half IN the stand's surface (28 + 27 + 15 + 9 at the pinned top: up beside the neck to the trace, then
  down 66 mm to R0 in 84 mm), and the fall, folded down over the stand, turns +7 WITH it: defect = 2 x the turn. The
  pin only concentrates it; any roll from horizontal at CB to the lapel's roll at R0 turns that much in the stand.
- What the cloth would need (proto3.py, outer edge free in 3D): the fall's outer edge moved 38-80 mm at the side
  neck and UP (z 1528 -> 1577-1581): the fall standing up beside the neck like a band (R3f-3..7's rejected look);
  strain then 4.5-5.1 %. Shaping within 8 % turns a fall's edge only ~17 deg per half (CONE_MAX_DEG 15).
- Tools now: step 4 reports t.info["collar_surface"] (cone_points, stand_turn_deg, fall_turn_deg, flat_cut ok / cone
  points; CONE_MAX_DEG 15). The cut's neck girth: draft_girths CROSSED + twins: the collar alone, open (was 1870 mm
  summed over fronts / backs / sides whose neck tape runs down the lapel). Proof: proof.sh (toile1 / mark1 / cut1.log): toile, mark PASS;
  collar_surface cones +125 / -57, stand_turn 77.9, fall_turn 7.3; neck 380 mm [collar] OPEN; collar strain 13.63 %, flat
  386 x 97, seams front 47.9 / 51.3, back 106.8 / 93.3 (the toile unchanged: the R3f-11 numbers).
- Three tries didn't move it (proto1-3): no step-4 rebuild landed; R3f-10's toile kept (its look is right).
## Left: downstream readers (chain_garment piece_start, garment_details, draft_own_tool.flat_check) read FLAT from a
  FreeSewing draft dir, not pattern.json; side / sleeve_under tapes; biceps / chest rings still take torso pieces.
NEXT: JOE DECIDES the collar's trade (the crease rule): (a) the roll lower at the side neck (R3f-9: 6 %, collar low), (b)
the fall flares out over the shoulder by the roll's turn (outer edge longer: wider collar at the side neck), (c) a soft
roll: the fall stands off the stand where the roll turns, or (d) more shaping than 8 % (a bias undercollar, two pieces
with a CB seam: doesn't change the total turn). Then step 4 builds the fall by the crease rule, gated on collar_surface.
