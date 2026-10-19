# STATE: fit_round1 (Garrett jacket v2 + shirt on the virtual dress form, collar check) -- 2026-10-19. NO SIMS.

STATE: 1 done, 2 PARKED (settle: tube KAT pass, cape KAT fail), 3 + 4 done. NEXT: step 5 fit v2 (fr1.py) on the form.
Durable files: /mnt/data/hifipushie/dress_garrett/fit_round1/. History: docs/notes/cloth.md "fit round 1".

## Plan (one agent, in order; commit after each)
1. diag turned stripes (DONE: tests/test_diag_render.py 16/16 pixel checks; renders fit_round1/diag_known/).
2. form gravity + real contact: PARKED. pattern_form.SETTLE (opt-in, off): tube KAT PASS, cape KAT FAIL (tent; local /
   global too slow for big rotations; needs a method change). Validation record unchanged, form_validated() False.
3. layer clearance: DONE (cloth_check.layer_clearance_rows; fr1.py jacket chest 0.15 / waist 0.16 / biceps 0.25 ease,
   shirt bicepsEase 0.10: all 4 rows PASS; shirt chestEase not moving its chest = open tooling).
4. shoulder pad: DONE (garment key shoulder_pad, pattern_form.padded_body; Garrett 10 mm; draft allowance open).
5. fit jacket v2 + shirt via pattern_check -> fit_garment.
6. collar check: 1 m neck close-ups front / 3/4 / side / back / top, clay + diag, beside the concept's neck; measured.
7. blind single-view review.
