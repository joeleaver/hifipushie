# STATE: fit_round3 (Garrett jacket v2 + shirt, round-2 collar on the dress form) -- 2026-10-19. NO SIMS.

STATE: HANDOVER. Steps 0-4 done; renders + blind review: FAIL on all 5 views (my own read agrees).
NEXT (one cause at a time, re-measure after each): (a) the collar fall does not turn: form fold "collar roll" ends at
-34 deg (turned_deg NaN for the collar; it needs ~170): find why the fold machinery stops (pattern_form fold rows,
FALL_FOLD angle 10 / strength 0.6) before touching the draft. (b) No notch reads although notch_gap / angle pass: the
checklist is incomplete. Add a measured "notch step" item (the outline's step where the collar end meets the lapel
point, from the reference) before any change. (c) Lapel edges jagged / standing off the chest. (d) Shirt through the
jacket (365 faces, worse than round 1's 268) and the shirt's front V too deep. Review refs: side / back / top reuse the
FRONT concept crop (the concept is front-only): the reviewer compared a side view with a front photo. Get honest refs.
Files: $FR3 = /mnt/data/hifipushie/dress_garrett/fit_round3/ (run.sh = this worktree; fit.py waive.json -> asm.pkl,
gate.json; collar.py -> collar_measures.json + check/<view>_{ref,clay,diag}.png; sheet.py -> check/<view>.png;
review.sh -> review_<view>/ + review_<view>.log). History: cloth.md "fit round 3".

## Steps
0. DONE (C44). Spread 43 deg came from pi x (under-stack + fall) at the outer edge + a constant 10 mm drop. The path
   measure itself was right (hand: ~22 mm, fold_line 19.2). Now ring_outer = fall/2 + cloth/2, drop tapered u^2:
   need 277 -> 259, spread 17 deg, outer 265 vs neck seam 246 per half.
1. DONE (C45). undercollar (fused, bias, 3.1 mm in), op_lapel_turn R27 (facing +3.1 mm past the roll line). Records:
   fused, so the form surface does not change. R18 rewritten: practice = two-piece UNDERcollar + one-piece top collar.
2. DONE. Gate with refs + waive.json: shirt PASS_WAIVED, jacket PASS_WAIVED.
3. DONE. Form fit + collar measures (collar_measures.json):
   | item | round 1 | round 3 | target |
   | fall top over HPS (CB) | 71 | 51.8 (stand top 43.8) | ~stand top (fall turned over it) |
   | stand gap to neck | 15-34 | 6 / 10 / 24 / 38 (CB -> front) | hug over the shirt collar, ~2-5 |
   | notch gap / angle | 57 / 74 | 26.5 / 61.4 | 20-40 / 60-90 (but no notch reads) |
   | collar end to gorge | 15 | 14.9 | ~0 |
   | shirt collar shows (back / side) | -11 / -8 | +7.7 / +6.2 | +10-15 |
   | shirt faces through the jacket | 268 | 365 | 0 |
   Shirt's own stand to the neck: 3.5 / 4.1 / 6.3 at back -> side, 21-27 at the front (90-180 deg). Round 2's
   suspicion holds only at the front (the open shirt V), so it does not explain the jacket stand's gap at the side.
4. DONE. check/{front,three,side,back,top}.png (ref | clay | diag). bin/review one view per run: FAIL x5. In-stage
   MAJORs: no notch (all views), lapel edges jagged / fragmented, lapels stand off the chest, the collar is a thick
   rolled / tall band (not turned), shirt collar leaves oversized and outside the jacket at the front, shirt through
   the shoulder.

## Known open
form_validated() False -> form rows INFO. Hair canvas thickness inferred. No back vent (R24). One-piece top collar not
drafted. The front's canvas is not in ring_outer (< 1 mm of length).
