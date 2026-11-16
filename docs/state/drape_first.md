# STATE: drape first (docs/proposals/drape_first.md; approved 2026-11-16)

Steps 4-6 rebuilt the draper's way: TOILE (the garment's 3D surface on the body), MARK, CUT AND FLATTEN.
Runs R1 (body + sleeves, done: C489) -> R2 (full toile, done) -> R3 (tools) -> blind trials.

## R2 (2026-11-16): the jacket's full toile, cut and flattened (spike; /mnt/data/hifipushie/r2: ws, out/, run.sh)
Code: `spikes/r2_toile.py` (toile), `spikes/r2_flat.py` (cut, flatten, unfold, compare), `spikes/r2_common.py`
(flatten, one_piece refusal, strip mesh, reference top line). R1's k per level reused (r1/toile/girths.json).
Toile (out/toile_sheet.png, collar_sheet.png; toile.json):
- PAD: ellipsoid (55/55/28 mm) smooth-unioned, top at the reference's jacket top line (picture x scaled so the
  shoulder_w row's point lands on D4's shoulder point, x1.148: the model's shoulders are wider than the picture's).
  Top line after: 1-8 mm above the reference over x 150-230 mm. Reads padded and square; a slight ledge at the tip.
- SLEEVES: a tube round a quadratic axis through the arm's section centres (pitch 3 deg forward), radius = section
  tape / 2pi + R1's 18-22 mm ease, monotone from the wrist up, held at the biceps: smooth, no bumps (round 395 -> 300).
- SKIRT: below step 0's hips level the seat's section straight down + 5.8 mm flare: hem 1137.2 / plan 1138.8.
- FRONT: buttoned, lap 20 mm past CF (convention: steps 1-2 give no lap), cutaway below the bottom button from step
  2's front_edge trace. LAPEL: roll line moved with the closure (break at CF + lap), lapel = toile under step 2's
  outline lifted 4 mm. Width 56.5 mm vs the reference's 59-63: a touch narrow; the notch barely reads.
- COLLAR: stand 28 + fall 40 (s4-31's) from the toile's neckline to the gorge. BACK NECK: no closing within 11 cm of
  the neck, the body cut at D4's neckline: no stand on the back body now.
- Girths (toile): chest 1097.5 / 1108.2 (-1 %: the tube's web), waist 986.1 / 987.6, hips 1102.1 / 1103.1.
Cut: every line an exact clip by a scalar (body marks as angle round the torso / shoulder y(x); sleeve by the rule
fore seam 30 mm in from the arm's front line, hind 20 mm in from its back line). Each piece must be ONE region, else
REFUSED with the mark named (one_piece): it fired on R1's armhole cut (plane AND radius + 35 mm bit an island out of the
side body, a hole into the under sleeve); armhole now = the plane alone, the sleeve = the part past it reaching the
wrist. All 8 pieces one region; body partition 3490.5 / 3490.5 cm2.
Flat (out/flat_sheet.png beside s4-31, cut_sheet.png; flat.json). Strain mean / area > 2 %:
front 1.6 / 30 % (66 % stretch at the shoulder by the pad: the pad belongs in its own piece), side 0.4 / 0.5 %,
back 2.0 / 39 % (blade: a shoulder dart / ease), top sleeve 1.2 / 13 % (crown), under sleeve 0.5 / 0.4 %,
lapel 0.06 / 0 %, under / top collar 5.5 / 63 % (bad).
Seams (flat a / b): front+side 531.1 / 532.6, side+back 518.8 / 516.0, shoulder 218.7 / 207.7 (+5.3 %: the pad),
sleeve seams 924.0 / 926.1, cap 476.9 vs armhole 459.6 (+3.8 %; s4-31 8.8 %). Lapel unfolded by reflection about the
roll line: hinge 3.7 mm mean (8.6 max), lands across the roll line. Top sleeve 62.7 % at the biceps (D4's split 53.5 %).
Girths on the flat less 2 laps: waist 990.8 / 987.6, hips 1052.8 / 1103.1 (the cutaway takes the lap there: not -40),
chest at the underarm (crosses the armholes) 962.8. Shares at the waist front / side / back 0.43 / 0.20 / 0.37.
vs s4-31 half widths (mm): waist front 221 / 199, side 102 / 125, back 192 / 189; hips 219 / 203, 120 / 116, 208 / 236.
Bboxes: front+lapel 307 x 724 / 261 x 739, back 279 x 753 / 265 x 724, top sleeve 250 x 535 / 208 x 583.
Verdict: body and sleeves are cuttable (side, under sleeve, sleeve seams, front/side/back seams true within 0.6 %);
the front + lapel is a forepart a cutter would recognise but its shoulder is distorted by the pad; the collar is NOT
cuttable: its fall edge is only 4 % longer than its neck edge in 3D (396 / 380 mm), so it flattens as a straight band
(388 x 79) with 40 % compression at CB, where s4-31's is a curved 414 x 95.

## Open faults (ranked)
1. Collar: the fall must spread over the shoulders (fall edge ~25 % longer than the neck edge); build the fall from the
   roll line out to an edge on the toile at the fall's width measured along the surface, not 12 mm past the neckline.
2. Pad as its own piece (shoulder pad / canvas), not a bump in the shell: the front's shoulder strain and shoulder seam
   +5.3 % come from it.
3. Lapel 56.5 mm vs 59-63, notch weak; collar / lapel meeting at the gorge unchecked.
4. Darts as output: back blade, front chest compression islands; crown stretch -> cap ease.

NEXT: R3 with faults 1-2 first (collar fall width along the surface; pad out of the shell), then steps 4-6 as tools.
