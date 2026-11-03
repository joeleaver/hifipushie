# STATE: draft_pattern (garment step 4, T5 + T5b) -> codified.md C285, C295
Tool draft_pattern(name, garment, design, declarations, options, sa): the agent's own FreeSewing design (Node, no network,
fs read-only, 60 s) + declarations in step 1's names -> draft_own.block (the one converter) -> cloth.mesh -> the flat
gate -> step 4 + flat sheet. pattern_check and chain_garment's gate read an own draft's step 4. The spec's pattern
carries a digest of draft + declarations + options (a redraft into the same dir is a new chain job).
T5b (Joe: "Why would it build curved pieces as straight lines?"; the hussar stand was a straight trapezoid, the shirt
band a rectangle, its fall a triangle): the flat gate checks SHAPE per role (draft_shape.py, its docstring the spec),
targets measured on FreeSewing 4.10.2's own parts (scripts in /mnt/data/hifipushie/t5b/scripts/ref_*.py):
- shape_stand: neck edge's ends rise towards the free edge: stand >= 0.24 x the neckline's front drop (jaeger.collarStand
  0.47 halved), band under a fall > 0; free / neck edge <= 0.989 (jaeger 0.978) / <= 1.0 (band).
- shape_fall: outer edge (or fold line) / stand seam >= 1.012 (simon.collar 1.024, jaeger.collar 1.038).
- shape_cap: cap height / armhole depth in [0.47, 0.79] (brian 0.52, bent 0.72).
- shape_seam_curve: no straight edge (sagitta/chord < 0.005) sewn to a curved one (> 0.02), names the straight edge.
Found measuring: simon.collarStand at its DEFAULT options DROPS 7.9 mm at its ends (a near-vertical shirt band on a
neckline at the neck base); its own range reaches a rise (collarStandBend 0, collarStandCurve 5: +5.8 mm on the shirt).
So the band row asks only "rises at all"; the stand row's magnitude is jaeger's.
Guide (cloth_tools.md draft_pattern) + the FAIL answer: reuse FreeSewing's part for a role (`from:` + options); using
FreeSewing's parts is right, garment-specific glue in our code is what's banned.
Redrafts through draft_pattern (homes /mnt/data/hifipushie/t5b/{hussar,shirt}; designs + declarations + options in
examples/draft_own/): hussar stand = simon.collarStand, collarStandBend -6 / Curve 5 (past simon's shirt range, the
rising way: jaeger's target), width 0.123 x neck (48 mm), no button extension: rise +27.9 mm = 0.37 x drop 75 mm,
free/neck 0.979, every row PASS. Shirt band = simon.collarStand (Bend 0, Curve 5; extensions 2 x EXT), fall =
simon.collar, roll fold 0.1 x band height above the stand seam (simon collarWidth 120 %): rise +5.8 mm, fall 1.024,
every row PASS. Before: T8 hussar FAIL shape_stand + shape_seam_curve; T5 shirt FAIL seams (-20.6 %), stand, fall, curve.
Hussar builds (chain_garment, structure; reference /mnt/data/hifipushie/refs/hussar/front.webp): collar_height / collar_upright
T8 0.055 / 72.7 deg -> b1 (rise 0.37 D) 0.089 / 73.1 -> b2 (rise 0.52 D, Bend -9) 0.071 / 70.7. Judged at full size
(/mnt/data/hifipushie/t5b/hussar/neck_t8_b1_b2.png, neck_b2_vs_ref.png): b2's stand no longer dips to a V: it runs round
at one height and its ends meet at CF, but it is LOWER than the photo's (which reaches under the jaw) and hugs the neck;
the rows read it worse, so collar_upright / collar_height may not measure lean-in vs flare as the eye does: check the
rows (structure_rows, T13's file) before trusting them. Then (Joe's marks) b3 draft, NOT built: the stand's front top
corners rounded (16 mm) and the cutaway a square step out (60 mm) at the zip's end then a drop to the point, traced
from the photo (flat_b3_vs_ref.png): every row PASS. Not done: a "corner stays a corner" row: the converter keeps
FreeSewing's vertices exactly, so it can't fail in the flat; the build is where corners round off (T15's outline-vs-
reference row). The shape rows can't catch: an outline unlike the photo (a rounded vs stepped hem), a stand too low.
Unverified: the shirt's chain build with simon's band + fall; jaeger/carlton parts as `from:` (need their own fronts);
a straight skirt waistband would FAIL shape_seam_curve (a known false alarm); half stands (.L/.R) aren't measured.
NEXT: build b3 (hussar; check collar rows read lean-in right) and the shirt with the new band + fall (chain_garment to structure) and judge its collar at full size beside the
reference; if the hussar stand still leans out, raise its rise towards jaeger's 0.47 x drop and rebuild once.
