# STATE: fit_round2 (Garrett jacket v2 + shirt on the virtual dress form, collar fixes) -- 2026-10-19. NO SIMS.

STATE: HANDOVER (budget). Steps 1, 1b, 1c done and committed. The coordinator added 1c (turn of cloth); its parts 3 / 4
(undercollar, lapel turn allowance) are NOT done. Steps 2-4 (gate PASS -> fit -> collar check -> blind review) NOT done
on the final pattern.
NEXT: (a) undercollar: a fall-shaped undercollar drafted a turn smaller (cloth_over.under_draft(uv, turn=pi/2 x t_fall
~3 mm), bias), sewn to the fall's outer edge, the seam rolling under. Prove it on the form's fold before relying on it.
(b) lapel turn allowance: the facing ~ a turn (pi/2 x 2 cloth + canvas) smaller past the roll line (Bp folds "lapel
roll"). (c) Then $FR2/fit.py waive.json (gate with refs) -> collar.py -> one cause at a time (ring hug, collar end to
gorge, notch on the form, shirt collar show, shirt through the back) -> blind review (bin/review --dry, one image/turn).
Files: $FR2 = /mnt/data/hifipushie/dress_garrett/fit_round2/ (run.sh runs THIS worktree's code; pass ABSOLUTE paths,
it cds; fr2.py = fr1 spec + env overrides POINT / FALL_FRONT / STAND_FRONT / FOLD_AT; flat.py, sweep.py, path.py flat
probes; fit.py <waive.json> gate + form -> asm.pkl, gate.json; collar.py check). History: cloth.md "fit round 2".

## Steps
1. Fall fold line: DONE. op_collar_two_piece adds fold "collar roll" (roll 10 deg, r 4 mm) 4 mm over the fall's seam
   (FALL_FOLD). Gate refusal existed (flat_pattern FAIL); test added (C41).
1b. Two-piece flat readers (cloth_check.collar_draft_two_piece, _notch_flat_two_piece; the rows read UNMEASURED before).
   R16 now uses practice values (agreed with the coordinator): stand from the roll line = neck/16 held to 25-30, fall = stand + 10.
   R15 fall end 0.5 x CB (notch gap). Round 1's "stand ~25 at CB" was the stand PIECE (now 24.3); from the roll line 28.3.
   Tests at necks 405 / 450 / 522 (C42).
1c. Turn of cloth (C43): pattern_jacket.turn_stack (wool 0.75 + hair canvas 0.5 INFERRED + 6 x shirting 0.25): t_fall
   2.0, under-stack 3.5, depth 6.6 mm, ring 5.5 -> +17.3 mm outer per half. fall_path = neckline offset by the drop
   (fall - stand, 10 mm) into back / front: 245.6 -> 264.8 (back +13.4, front +5.8). Spread SOLVED 43 deg (was a fixed
   13): outer 277 / roll line 236 per half. Gate row collar_fall_outer PASS 283.5 vs 282.0. Garrett flat: stand 28.3, fall
   38.3 (seen), f-s 10.0, notch 32.6 mm / 62.1 deg, tailor rows 11/11 PASS, flat_pattern PASS.
2. Gate with refs + waive.json (shirt pockets, jacket vent: not in the front-only concept; no vent drafted): shirt
   PASS_WAIVED. The jacket run in flight used the 1b pattern (before 1c), so it is superseded.
3-4: not run on the final pattern. Round-1 numbers stand as the baseline (fit_round1.md).

## Known open
form_validated() False (settle parked) -> form rows INFO. Shirt chestEase / waistEase don't move its measured chest /
waist. No back vent (R24 not drafted). Hair canvas thickness inferred, not measured. A spread of 43 deg is big against
the books' 1-1.5 cm per half: the path measure (flat offset of the neckline + run-on to the outlines) is the suspect.
Check it on the form (the fall edge's worn length vs its pattern length) before trusting it.
