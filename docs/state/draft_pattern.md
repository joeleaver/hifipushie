# STATE: draft_pattern (garment step 4, T5 + T5b) -> codified.md C285, C295, C300
Tool draft_pattern(name, garment, design, declarations, options, sa): the agent's own FreeSewing design (Node, no network,
fs read-only, 60 s) + declarations in step 1's names -> draft_own.block (the one converter) -> cloth.mesh -> the flat
gate -> step 4 + flat sheet. pattern_check and chain_garment's gate read an own draft's step 4. The spec's pattern
carries a digest of draft + declarations + options (a redraft into the same dir is a new chain job).
T5b (C295): the flat gate checks SHAPE per role (draft_shape.py, its docstring the spec; targets on FreeSewing 4.10.2's own
parts, /mnt/data/hifipushie/t5b/scripts/ref_*.py): shape_fall (outer / stand seam >= 1.012), shape_cap ([0.47, 0.79] x
armhole depth), shape_seam_curve (no straight edge sewn to a curved one), shape_stand (below).
T5c (2026-11-02, C300; draft_stand.py): T5b's shape_stand forced EVERY stand's neck edge to rise (jaeger: the hugging
stand); Joe on the hussar: "it got the collar curves the wrong direction again" (its stand stands away, top LEVEL, tall
at CF). Now step 2's collar_top trace decides (draft_stand docstring = the derivation: the stand as a band, neck edge =
the drafted neckline, free edge = the trace): h_side (top above the hps marks), T (its drop to the front ends, a rounded
corner passed over: last point within 60 deg of level), f = T / D. Targets: rise f x 0.47 x D +- 0.24 D; front ends
h_side + D - T; CB h_side + D_back (1 - f); lean <= 0.989 only if f >= 0.5; tol 2 x 3 px x mm/px + marks residual. FAIL
says which way to curve, how much taller / lower. No trace: INFO (curve + heights reported); a band under a fall: INFO.
draft_own_tool.stand_ref loads the body's landmarks (cloth.Body) for the placement. Tests: tests/test_draft_own.py.
Hussar (HOME /mnt/data/hifipushie/t5c/hussar = t5b copy + T15's traces/body_marks in step 2; scripts/ there): b3 (T5b)
FAILs the new row: rise +39 mm (want +10 +- 18), fronts 46 (want 53 + 75 - 20 = 108 +- 15), CB 46 (want 67). Redraft c1
(examples/draft_own/hussar.mjs + options): simon.collarStand, Bend -1 (rise +9.4), top line redrawn at the traced height
over each place of the neck edge (back 1 - cos, front sin), corners rounded 16 mm: every flat row PASS
(flat_c1_vs_ref.png: the flat top dips at the side neck, tall ears at CB and the fronts).
Build c1 (chain_garment, structure): REFUSED "a length can't hold: front.L edge 30 % off its cut at front.L:cfNeck";
the rows read before it (outline_c1.png / outline_c1_top.png), T15-on-T8 -> c1 (p95 mm): hem 32.5 -> 20.1 FAIL;
collar_top 8.7 -> 10.4 FAIL (the whole top 32 mm too HIGH); collar_front R/L 11.8 / 6.3 -> 20.1 / 19.7 FAIL (worst at the
CF bottom); zip_line PASS -> FAIL (max 28.5, at the refusal); collar_height, collar_upright FAIL. Built (zs.py): the collar
at CF spans 4 mm of height, at CB 7 mm: the stand does NOT stand, it lies out / collapses; it is too tall at CF.
FOUND: D on the flat (75 mm) is not the neckline's drop on the body: hps z 1547, cf_neck 1531 (16 mm), the photo's
neckline at CF (collar_front bottoms, v 100 vs hps v 63) ~39 mm. The derivation's "D on the flat ~ the vertical drop"
is wrong for a jacket front (it tilts over the chest), so the front target is ~30-60 mm too tall: a build-proven fault.
Judged: no full-size render (stopped by the coordinator); verdict from the overlays + numbers: worse at the collar.
UNVERIFIED: the derivation with a body-side D; whether a straight neck edge stands on a tilted neckline at all (c1 lies
out at CB: maybe a level-top stand still needs some rise); the shirt's chain build; half stands (.L/.R).
NEXT: in draft_stand, take D (and D_back) from the photo / body, not the flat: the neckline's vertical drop in the view
(collar_front traces' bottom ends vs the hps marks, else the body's hps - cf_neck z); retest; redraft the fronts
(~h_side + 39 - 20 ~ 72 mm) and rebuild once; fix the cfNeck length refusal first if it persists (look_pattern there).
