# STATE: draft_pattern (garment step 4, T5 + T5b) -> codified.md C285, C295, C300, C303
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
r-hussar (2026-11-02, C303; HOME /mnt/data/hifipushie/r-hussar = t5c copy, scripts/ there, run.sh sets HOME + ASSETS):
D SEEN: draft_stand.reference takes D = the collar_front traces' bottoms below the hps marks (hussar 49 mm; else the body's
hps - cf_neck), D_back = the body's hps - cb_neck (-9: the neck base tilts, CB above the side neck); the flat's only when
neither is known (said in the row). RISE: an upright level-top stand is a vertical band: free edge straight, neck edge
FALLING at the ends by (1 - f)(D - D_b); target = f x jaeger x D_flat - (1 - f)(D - D_b), tol the heights'. shape_stand is
a VERDICT again on the HEIGHTS (c1 108 mm fronts -> collar_height FAIL; r1 / r2 82 / 48 -> PASS; T8's 46 -> collar_front
corners low: 3 builds agree with the rule); the CURVE's why is report-only ("INFO (curve would FAIL)"): r1 (+9) and r2
(-13 mm) both built the stand 31 deg up, so no build backs the rise yet. Tests: test_draft_own (D seen; leaning stand).
cfNeck REFUSAL (c1: front.L edge 30 % at cfNeck): the build's stand stage put c1's 108 mm fronts LYING OUT (stand rise
median 10.7 deg; band neck edge read 445.6 vs cut 430.7, worst link 32 %; the stand's CF end edge lying along the
neckline, its links 3x): dragged sideways, the front's neck corner tore (its mesh x1.5-1.7 there). Gone with the right
heights (r1 / r2: free worst 0.0 %, band neck = cut, stand rise median 48-49 deg). Not a separate draft fault.
REDRAFT (examples/draft_own/hussar.mjs + options): fronts 82 / CB 48 / side 53 mm (the row's targets); the CF neck 30 mm
lower (c1's built 19 mm below hps vs the trace's 49); the stand widened about CB until its neck edge = the neckline (the
lowered neck is longer, and collarEase also sizes the bodice neckline); HPS_AT from the store; bend 5 (neck edge -13 mm).
ROWS p95 mm (T15-on-T8 -> c1 -> r2): hem 32.5 -> 20.1 -> 22.5 FAIL (hem untouched; 2 step corners kept, tips lost);
collar_top 8.7 -> 10.4 -> 11.5 FAIL (built top 41 mm LOW, domed: lying out); collar_front R / L 11.8 / 6.3 -> 20.1 / 19.7
-> 11.8 / 12.9 FAIL; zip_line PASS -> FAIL -> FAIL (p95 6.0, max 22.1 > 20.6: at the neck); collar_height FAIL -> FAIL ->
PASS 0.151; collar_upright FAIL -> FAIL -> FAIL 31.3 deg (want 76-94). Overlay outline_r2.png (+ _top), render
sheet_r2_neck.png / sheet_r2_whole.png. JUDGED at full size beside the reference: NOT the hussar's stand: it lies out
like a funnel, ends far apart at the top, CB lying flat (8 mm of height at CB), crumpled seam; reference tall, upright,
level, ends nearly meeting. Heights right on the flat, wrong on the body because the BUILD lays the stand out.
BUILD FAULT (named, not fixed): chain_roles' stand stage only asks its top 12 mm over its bottom (`upright`), leans the
whole ring forward to clear the neck, then later stages drop it to 31 deg; the stand's own edge links read 237-278 % over
(gathered, so outside the free gate). UNVERIFIED: the rise rule (no upright build yet); D_back's -9 mm; the hem.
NEXT: the stand build (chain_roles stand stage + the stages after it): an upright stand keeps its heights square to the
ring as built (generators vertical, its CB standing), its gathered edge links within their cut; then rebuild r2 unchanged
and read collar_upright / collar_top; only then judge the rise rule and make the curve a verdict.
