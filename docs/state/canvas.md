# STATE: canvas (canvas / interfacing BENDING STIFFNESS in the fit + styling; then the jacket with fewer holds) -- 2026-10-23

GOAL (Joe, after the hold audit C190 / C191): canvassed / interfaced pieces (jacket forepart chest + lapels, undercollar /
collar; shirt collar, stand, cuffs, placket) keep their shape through STIFFNESS, so the workaround holds can go.
Not a sim; no rented GPU. Joe (coordinator relay): the concept is SLIM-CUT, modern: step 0 slims the pattern first.
STEP 0 (ease, slim-cut): flat ease (canvas/ease.py, layers.py) before: chest 1113 (+15.0 %), waist 1131, hips 1196,
seat 1225, hem+30 1270 (+32 % on the seat), biceps ~417 chord (armhole-bound), sleeve hem 319. Slim-cut practice: chest
+7.5-10.5 cm (two-button 10.5: RJCC 2015 doi 10.7741/rjcc.2015.23.5.835), FreeSewing Jett biceps 15 %. FLOOR: the
shirt under it (chest 1067 flat) + 2 pi x 6 mm = 1104 (layer_clearance_chest). Slim edit (canvas/slim.json): chest_ease
0.141 (1104), round 34's let-out removed (hem 1270 -> 1103: plumb at the chest's girth), sleeve hem 320 -> 285,
biceps_ease 0.2 (404). Gate run gate_slim.py s1 (in progress) -> fit_s1.pkl (the slim fit, PLUMB_HOLD default).
BENDING MODEL (bending.py): edge HINGES (4-point stencil from the flat pattern, face B unfolded across the edge,
reads |e| x fold angle), E = sum w_e 3/(A0+A1) |S x - t|^2 x scale x mean edge^2; rest t = SIGNED made fold along the
hinge normal for interfaced cloth, flat for plain. Weights per vertex: BEND_KIND canvas 20 / fusible 8 / plain 1
(interfaced entry key "kind"; default fusible), fabric factor opt-in (BEND_FABRIC off). Vertex-Laplacian (Bergou H^2)
FAILED: saddles cost nothing, a canvas strip fell as plain (proof1.py).
STYLING: garment_pull.STYLE_BEND (OFF; env GP_STYLE_BEND=1), STYLE_BEND_W 5, STYLE_BEND_PLAIN 0.2; rest = the shape
style() started from (M["_bend_rest"]); weights M["bend_w"] (on_form now stores them in the mesh).
FIT: pattern_form.FIT_BEND_KEYED (OFF; env PF_BEND_KEYED=1, garment key bend_keyed) scales the fit's Bergou term per vertex.
KATs tests/test_bending.py (4 pass): stencil reads 30 deg; 120 mm strip clamped: plain tip drop 100 / fusible 12 /
canvas 4.8 mm of 108; rolled collar (12 mm, held on its stand): fusible r 11.9 edge 23.8 (24), plain falls (edge -1.9);
a 150 deg fold stays 150.2.
RUNS: $CV = /mnt/data/hifipushie/canvas (run.sh -> this worktree; scripts copied from supports / fit_round38).
NEXT: gate s1 result -> store the slim spec (gate_slim.py s1 save) if PASS_WAIVED; record "slim-cut, modern" on
dress_garrett_fit.md; then jacket: fit (PF_BEND_KEYED) + style (GP_STYLE_BEND) with the canvas kind on the fronts'
interfaced band; remove holds one at a time (PLUMB_HOLD, hold above break, side / back hem hold), reads vs concept.
