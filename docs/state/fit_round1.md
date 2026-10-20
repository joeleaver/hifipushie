# STATE: fit_round1 (Garrett jacket v2 + shirt on the virtual dress form, collar check) -- 2026-10-19. NO SIMS.

STATE: 1, 3, 4 done; 2 PARKED; 5 run (gate FAILs, fit forced for the check); 6 done (collar FAILS); 7 not run.
NEXT: give the v2 collar's fall its fold line (the gate's flat_pattern FAIL) and re-run $FR1/fit.py + collar.py, then
the blind review (bin/review --dry, one image per turn). Pass refs (refread/garrett_concept_refs_v2.json) to the gate.
Files: $FR1 = /mnt/data/hifipushie/dress_garrett/fit_round1/ (run.sh, fr1.py spec, fit.py, collar.py, check/, asm.pkl).
History: docs/notes/cloth.md "fit round 1".

## Steps
1. diag turned = stripes over the piece colour: DONE (tests/test_diag_render.py 16/16 pixel checks).
2. form gravity + contact: PARKED. pattern_form.SETTLE opt-in OFF; tube KAT PASS, cape KAT FAIL (open_settle_cape_on_bar:
   tent, local / global too slow for big rotations -> needs a method change). Validation record unchanged, form_validated False.
3. layer clearance rows (cloth_check.layer_clearance_rows): DONE; fr1 ease (jacket chest 0.15 / waist 0.16 / biceps 0.25,
   shirt bicepsEase 0.10): all 4 PASS. Open tooling: the shirt's chestEase / waistEase don't move its measured chest / waist.
4. shoulder pad (garment key shoulder_pad, pattern_form.padded_body): DONE, 10 mm; draft allowance not added (open).
5. gate: shirt FAIL (UNMEASURED: no refs), jacket FAIL (UNMEASURED + flat_pattern: no fold line on the collar fall).
6. collar ($FR1/collar_measures.json): stand CB 23.5 (book 25); fall stands up, top 71 mm over HPS; stand 15-34 mm off the
   neck; notch gap 57 mm / 74 deg (J 45); collar end 15 mm off the gorge; shirt collar shows -11 back / -8 sides (want
   +10-15). Through-under 268 faces (shirt through the upper back).

## Dead ends
- HANG-style gravity without contact in the solve (780 % stretch); unclamped steps tunnel the form.
