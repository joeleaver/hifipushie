# STATE: fit_round3 (Garrett jacket v2 + shirt, round-2 collar on the dress form) -- 2026-10-19. NO SIMS.

STATE: steps 0-1 done (fall path measure fixed C44; undercollar + lapel turn C45).
NEXT: step 2: $FR3/fit.py waive.json (gate with refs, must PASS / PASS_WAIVED), then the form fit (asm.pkl).
Files: $FR3 = /mnt/data/hifipushie/dress_garrett/fit_round3/ (run.sh runs THIS worktree's code; fr2.py / fit.py /
collar.py copied from round 2, OUT -> fit_round3; probe0.py = the step-0 hand check). History: cloth.md "fit round 3".

## Steps
0. Fall spread sanity: DONE. Round 2's 43 deg came from the ring term, not the path. Hand check on the flat jacket:
   back neckline turns 90.7 deg, front 34.9 -> a 10 mm offset adds ~22 mm by hand, fold_line 19.2 (run-on): the path
   measure was right. But (a) pi x ring used ring = under-stack + fall (5.5 mm -> 17.3 mm): the outer edge lies on the
   jacket body, not over the stand + shirt collar, so its stand-off is fall/2 + cloth/2 = 1.375 mm -> 4.3 mm;
   (b) the drop (10 mm) was applied along the whole neckline, but the fall's end barely passes the seam (drop_end
   -1.4 mm): now tapered u^2 like the heights (back mean 9.3, front 4.0). Need 277.4 -> 259.4, spread 43 -> 17 deg;
   outer edge 265 vs neck seam 246 per half (+20; books 10-15 + the stand's 4 mm lean-in). pattern_jacket.fall_need;
   gate row collar_fall_outer uses it; test_fall_outer_edge_is_the_books_spread_not_the_under_stack (3 sizes).
1. DONE. undercollar piece (fused to the fall, bias 45, outer edge pi/2 x 2.0 = 3.1 mm in); op_lapel_turn (R27): the
   facing's lapel edge let out 3.1 mm (0 at the break), 366 -> 369 mm, eased. Both fused cut-piece records: the form
   surface is unchanged. R18 rewritten: books cut the UNDERcollar in two + a one-piece top collar; our stand + fall
   are the undercollar's pieces (open: the one-piece top collar is not drafted).
2. Gate with refs + waive.json: TODO.
3. Fit + re-measure round 1's table: TODO (first check: the shirt's own collar standing ~24 mm off the neck).
4. Collar check PNGs ($FR3/check) + blind review: TODO.

## Known open
form_validated() False -> form rows INFO. Hair canvas thickness inferred. No back vent (R24). The front's canvas is
not in ring_outer (0.25 mm more stand-off at the front: < 1 mm of length).
