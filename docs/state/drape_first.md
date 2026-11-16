# STATE: drape first (docs/proposals/drape_first.md; approved 2026-11-16)

Steps 4-6 rebuilt the draper's way: TOILE (the garment's 3D surface on the body), MARK, CUT AND FLATTEN.
Runs R1 (body + sleeves, C489) -> R2 (full toile, C490) -> R2b (armhole, pad, collar fall: C491) -> R3 (tools) -> trials.

## R2 in short (spikes/r2_*.py, /mnt/data/hifipushie/r2)
Full jacket toile (pad, smooth sleeve tubes, straight skirt, buttoned lap, lapel, collar), cut by scalars (a piece that
is not ONE region is refused), flattened LSCM + ARAP, lapel unfolded about the roll line. Body and sleeves cuttable;
faults: no sleeve crown (cap ease 3.8 %), front 66 % stretch at the shoulder (pad bump + crown in the body), the
collar a straight band (fall edge only 4 % longer than the neck edge), lapel 56.5 mm.

## R2b (2026-11-16): spikes/r2b_toile.py, r2b_flat.py, r2b_common.py; /mnt/data/hifipushie/r2b (run.sh, out/)
- ARMHOLE (rule, r2b_common.Cone): the body's armhole (D4's loop: shoulder point at the pad's edge, front / back pitch
  close in at the arm root, underarm) carried out along rays from the shoulder joint (apex 5 cm in along the arm's
  axis): a cone, never a plane fitted to the loop. The sleeve tube now runs up into the shoulder (axis from -6 cm),
  capped by the cone, so the armhole cuts the tube's crown. The torso is pushed off the arm only inside the cone above
  the body's underarm, from 2 cm outside it below (the eased tube fuses with the torso under the arm: the armhole
  dropped 9 cm, side+back seam 431; now 473, R2 519). Azimuth-varying pushes made fins at the pitch: z-switched only.
- PAD: a wedge under the shell, its own piece (out/pad_sheet.png): T at the shoulder point, thinning to 0 13 cm toward
  the neck and 3 cm past the point, cos^2 over +-11 cm front / back, 2 mm cloth gap. Sized to the reference's top line:
  only the 4 mm floor is needed once the tube's crown rises (toile top at the tip 1.502 vs ref 1.4997); pad piece
  93 x 62 x 31 mm box. Inward of the point the toile is still 5-7 mm under the reference (x 120-190 mm).
- COLLAR: fall laid 40 mm along the toile from the neckline (r2b_common.march), stand leaning out 15 %: fall edge
  +10 % in 3D (380 -> 413; R2 +4 %), flat 387 x 99 (s4-31 414 x 95), still 5 % mean strain, 66 % area > 2 %: the
  flat has neck 407 / roll 414 / fall 408: a saddle (fall edge not longer than the roll). NOT cuttable yet.
- LAPEL: widened square from the roll line x61/56.5: 60.7 mm (ref 59-63). Notch untouched.
Flat (out/flat_sheet.png beside s4-31; cut_sheet.png; flat.json). Strain mean / area > 5 % / max:
front 1.24 / 2.1 / 8.8 % stretch (R2 1.6 / 5.2 / 66), side 0.34 / 0.1, back 2.03 / 3.6 / 29 (blade: dart),
top sleeve 1.12 / 2.5 (one 64 % pinch at the front pitch, 0.212 -0.067 1.392), under sleeve 1.0 / 3.2 (underarm tips).
Top sleeve: a rounded cap, 95 mm rise across its armhole edge in the flat (R2: flat top with a spike).
Seams flat a / b: front+side 514.6 / 518.6, side+back 471.6 / 467.3, shoulder 217.2 / 213.3 (+1.8 %, R2 +5.3),
sleeve seams 878.8 / 895.0 (-1.8 %), cap 546.9 vs armhole 529.8: ease 3.2 % (s4-31 8.8 %; target 6-10).
Girths on the flat less laps: waist 990.6 / 987.6, hips 1052.8 / 1103.1 (cutaway), chest at z 1.322 crosses the armholes.
Bboxes r2b / s4-31: front 299 x 723 / 261 x 739, back 291 x 753 / 265 x 724, top sleeve 262 x 530 / 208 x 583,
under 159 x 450 / 160 x 518. Toile girths: hem 1137.2 / 1138.8, hips 1102.1 / 1103.1, waist 986.1 / 987.6.

## Open faults (ranked)
1. Collar: a saddle. Build it the tailor's way: lengths growing neck < roll < fall edge; likely from its flat (s4-31's
   curved collar) fitted round the toile's neck by the chain route for stiff pieces, not lofted between curves.
2. Cap ease 3.2 %: the tube's crown is barely domed (radius held from the biceps up); give the crown its own fullness
   (radius rising over the pad) so the cap comes out 6-10 % over the armhole; the 64 % pinch at the front pitch.
3. Top sleeve 262 wide vs 208 (63 % share at the biceps): move the under sleeve seams per the rule or the reference.
4. Back: 3.6 % of area over 5 % (blade): a shoulder dart / ease as output. Lapel notch weak; skin shows through at the
   front shoulder in the render (toile within a few mm of the body there, as in R2).

NEXT: R3 with the collar (fault 1) and crown fullness (fault 2) first, then steps 4-6 as tools (cone armhole into src).
