# STATE: garment export (step 10, T11 -> T11b) -- 2026-11-02

Tool: `export_garment(name, garment, wear="open", role="main_npc", look=True)`. Code: garment_export.py (method),
garment_export_tool.py (tool body), garment_glb.py (GLB), garment_loops.py (T11b: the loop re-grid), garment_bend.py
(T11b: weights + the bend check), garment_bend_look.py (T11b: close-ups). Tests: tests/test_garment_export.py. C291, C293.

T11b (fix run; Joe: the shirt kinked at the shoulder top + pinched at the armpit with the arm at 45 deg; gate passed):
- Cause, measured on T11's GLB: WEIGHTS: rig.skin_parts' transfer (closest skin point, WORN_SMOOTH 0) gave neighbours
  weights 69 % apart (p99, 100 % max) where cloth stands off the skin (p95 3.6 cm). The bare body bends smoothly at the
  front shoulder (its own crease: a small one at the back armpit, and it TEARS at the bent elbow: the body's). MESH: no
  loops. BUILD: the underarm cloth is already folded at rest (dihedral 129 deg at the back panel's underarm).
- Mesh: rings parallel to every border (LOOP_RINGS 2), grain grid inside, a loop across sleeves at the elbows (rig's
  hinge joints), quads paired: quad share 0.81, seams shared, open edges 0, 11736 / 12000 tris (grid 28 mm).
- Weights: projected skin point + geodesic smoothing (radius 2 cells / 2x stand-off, 2-6 cm: 6 cm here).
- Check (replaces weight_check): 4 poses, strain over the skin (p99 <= thread cap 0.02), no new crease past the soft
  cloth's sharpest rest fold (67 deg) beyond the skin's own. UV stretch row: INFORMATIONAL (T11 chose its limits after the
  numbers; no named tolerance exists).
- Before (T11 mesh + weights) -> after: arm_raised_45 FAIL 3 new creases (shoulder top) -> FAIL 0 creases but strain
  p99 +0.106 (armpit); arm_forward_60 FAIL 7 -> FAIL 6 + strain 0.066; elbow_bent_90 FAIL 1 -> FAIL 4 (inner elbow;
  skin through 19: the body's elbow tears); arms_down FAIL 13 -> FAIL 3. The old route FAILs in all 4 poses (proved).
- My look at full size (ws copy /mnt/data/hifipushie/t11b/ws/cf_shirt/garments/shirt/step10_*.png): NOT clean yet.
  Raised arm: the shoulder-top step is softer, but a slit shows skin at the front armpit / sleeve cap and the sleeve
  steps against the back panel at the seam. Bent elbow: skin pokes through at the elbow (the body's own tear there).

Open (worst first):
1. The armpit: cloth folded at rest in the build (steps 5-6) + a 6 cm smooth spreading the armpit's stretch; try a
   smaller radius at the armhole only, or seams weighted as one ring (both sides the same blend), then re-check.
2. The body's elbow tear (MakeHuman weights + bend bones) under every sleeve: fix in rig, not the garment.
3. Fold bake, LODs, layering cull, detail decimation (T11's list) still open.

NEXT: the armpit (1), proven by the bend rows + the raised-arm close-up; then the body's elbow (2).
