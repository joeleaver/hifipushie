# STATE: drape first (docs/proposals/drape_first.md; approved 2026-11-16)

Steps 4-6 rebuilt the draper's way: TOILE (the garment's 3D surface on the body), MARK, CUT AND FLATTEN.
Runs R1 (C489) -> R2 (C490) -> R2b (C491) -> R3a (toile, C492) -> R3b (mark + cut, C493) -> R3c / R3c-2 (made pieces, C494)
-> R3d (lengths from the toile, C495).
History: docs/notes (grep C489-C495); spikes/r1_*, r2_*, r2b_*.

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

## R3c-2 (C494): the collar's fit starts with the fall turned down (lay_down's walks, LEAN); canvas = the wedge
(a full-front line crosses the armhole twice: needs a line kind that stays inside).

## R3d (2026-11-16, C495): step 6 takes its lengths from the toile
- Collar: outer edge = the toile's landing line: cut_collar.landing_line, the CONTOUR at the fall's depth (w - 2h) below
  the neck line, end caps out (+ lift). R3c-2's walks fanned x2 at the side neck point and crossed where the neck line
  turns in (behind the shoulders 311 walked vs 268 contour); the whole line 590 = x1.14 the rule's 516 (the rule misses
  the corner's fan in front). shape_fall_landing compares the flat outer with that toile line (B["landing"]).
  Jacket: lands 7.5 of 12 mm at CB (R3c-2 4.5), lengths 0.75 % / 0.05 mm, outer 600 = 1.26 x neck, flat a deep crescent
  (467 x 172 mm, bow 100). Judged (cut_3d.png neck views): fall reaches further out over the shoulders at the sides,
  but the collar still reads as a high stand round the neck, not the reference's collar lying flat on the shoulders.
- Tapes / place (cut_tapes.py): each piece names the step-3 tapes it lies on (a girth only where it crosses its plane;
  a drafted collar: an edge map to the neck girth; a layer: its host's) and its wrap {to, side} off the toile.
- Folds: garment_cut `folds` {piece: {fold: edge}}: sleeve hems as press folds on the hem edge.
- Cap ease: the toile gives none (seams share vertices); flattened, the cap is 2.5-8.8 % SHORT of the armhole (top
  -3.6 / -2.5, under -8.8 %): the toile's cap is a saddle, not a dome (the underarm web). Not declared on the jacket (it
  would FAIL seams honestly); declared ease is now kept as cut and ".L" serves ".R" (tested).
- Proof /mnt/data/hifipushie/r3d (go.sh, run.py, cut_decl2.json, cut4.log; spike/ walk_diag, contour_diag): PASS
  collar, seams 32, piece_tapes 16/16, place, planned_folds 7/7, panels, shape_fall 1.261, shape_fall_landing 1.000,
  shape_cap 0.64, sewn, cut, caught, closures. FAIL: darts_drafted (not started), style_lengths (not started), girths.
- girths (now read, was "no girth"): closure 'front_closure' has no fastening marks on the fronts (step 6 writes none);
  chest 1083 vs 1108 planned (-25, tol 21); waist 1029 vs 988 (+41, tol 31); hips level doesn't go round; the chest /
  biceps "taken at the underarm" rings pull in the sleeves (sleeve_top in the chest ring, fronts in the biceps ring).
- Tests: tests/test_cut_r3d.py (contour turns a corner by d x angle; hem folds + mirror; tapes on two sheets; declared
  cap ease kept, mirrored; undeclared trued).

## Left
- Darts from strain (front chest / waist suppression, back blade; front_dart through the pocket mouth): R3d item 2.
- style_lengths: compare only where step 1 estimated the same line (collar neck edges, shoulder): R3d item 6.
- girths on the toile's flat: fastening marks for the closure, the underarm rings, the waist 41 mm loose.
- The cap: a toile cap that is a dome (step 4), then declare its ease. The collar still stands high.
- Downstream readers (chain_garment piece_start, garment_details, draft_own_tool.flat_check) read FLAT from a FreeSewing
  draft dir, not pattern.json. ~120 "step 4" texts in chain_* / draft_* still mean the flat pattern.

## R3e (2026-11-16, C496): in progress (branch r3e-drape; proof /mnt/data/hifipushie/r3e)

NEXT (R3d's): R3e: darts from the strain ridge (darts_drafted), style_lengths like with like, girths' closure marks and
underarm rings; then why the collar stands (stand 30 mm vs the reference's).
