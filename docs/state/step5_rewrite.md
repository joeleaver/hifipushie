# STATE: step 5 rewritten (docs/proposals/step5_rewrite.md; CHAINS ONLY; N2h: SMOOTH CHAINS)

Step 5 lays out the CHAINS (boundary + fold rows + lines across), lengths given, only bends chosen, nothing held.
Step 6 fills surfaces between them. Runs N1 -> N2 -> N2b -> N2c -> N2d -> N2e -> N2f -> N2g -> N2h (this).

## Current code
- `panel_start.starts`: each piece placed from its own tapes (girth roll / edge on its tape). NEW `_ways`: a girth piece
  rolls the way its SEAMS say (one flat cuts a pair, so a flat may show either face: the jacket's front flat shows its
  inside). Settled before edge-taped pieces read their sides. Test: test_girth_piece_rolls_the_way_its_seams_say.
- `chain_panels.Panels` + `fit_start`: rolled panels fitted to that start. Its ruled hinges turn the WRONG way on the
  jacket (way read off the flat: collar fall up into a funnel). The N2g driver sets every hinge's turn to 0 (start
  unturned) and leaves turning to the solve's fold terms.
- `chain_assemble` (rigid assembly / dress / close): KEPT. N2g did not pass, so the brief's deletion did not apply.
- N2h: chain_solve bending is CLOTH (`cloth_bend`: CLOTH_B / CLOTH_ES x link weight / h^2, x BEND_KIND), plus
  second differences along chains (`chain_solve_terms.chain_bend_rows`); the last word is `chain_solve_final.step`
  (constrained Gauss-Newton: soft terms minimised, links / edges / ties / contact linearised equalities, restoring by a
  damped GN step). `chain_solve_terms.smoothness`: zigzag = a chain point turning against both neighbours.
  `chain_solve_terms.EXACT_INTERFACED` (knob): the jacket proof sets it False (exact Delaunay rulings = a board).
- Proof: `spikes/n2h_jacket.py <out> <loaded.pkl> [measure] [bindall]`: start, then chain_solve on the unsewn network
  with seam pairs pulled to their midpoints (SEAM_W 0.1, 1, 10), then the sewn network. Render `spikes/n2c_render.py <run>
  <pkl> <ref> X_start.npy|X.npy quick`. ws /mnt/data/hifipushie/n2h (loaded.pkl in /mnt/data/hifipushie/n2/mine).

## Numbers (jacket, n2h/run2; 4,326 points, 3,023 sewn links; load 63-76; X_quick_sheet.png)
- Links: every SEWN link within 0.03 % of its cut (0 over 2 %; N2g median 5.1 %, max 1233 %, 2960 over). Per side
  (each side vs its own cut): 260 over 2 %, max 20 %: the seam truing / cap ease (132 links whose sides differ > 2 %).
- Smoothness (turn minus flat turn per chain point): median 2.3 deg, p99 49, zigzags 54 (N2g, same measure: 13.2 /
  164 / 1,075). Most left: sleeve_top.R 10, fronts 7-8.
- Folds at plan within 0.2-4 deg (collar fall 89 / 90, lapels 83-85 / 85, hems 87-94 / 90; N2g lapels 11-31).
- Inside 0, under gap 0. Tapes 44 mm mean off, max 101. Seams moved to meet up to 158 mm (sleeve seams, shoulders
  149); merge jump up to 108 mm (facing ~ front).
- Final step: hard terms hold, but every solve ran to its 200-pass cap (the SOFT phase does not settle: radius stays
  5 mm). Wall 773 s (stages 146-157, sewn 271; final step 227 s of the sewn solve). Run1 (rulings exact): links stuck
  27-43 % off on collar / undercollar / canvas.
- Beside the reference: torso wraps the body, chains smooth. Collar: a small tight ring at the neck base, no visible
  roll or fall over the back. Lapels: no V opening; front edges run up the centre front to the neck and cross there.
  Sleeves: thin bundles down the arms, the cap seams not reading as round armholes; small loops at the wrists. Hem:
  roughly level, slightly scalloped at the fronts.

## Open faults (ranked)
1. Final step's soft phase hits its cap (200): needs a proper trust region / merit (or fewer, cheaper passes).
2. Front edges / lapels closed at the centre front; collar a ring: the shapes, not the chains, are now wrong.
3. Hinge way convention (chain_panels vs chain_lay.fold_rows: Panels multiplies by the row's handedness, fold_rows
   does not): not done. Shoulder seams start 200-280 mm apart: not done. Collar ply across its fall: not done.
4. Synthetic arch / ease tests (tests/test_chain_smooth.py) pass on main's solver too: the jacket's zigzags came from
   competing terms + the projection, which the tests don't reproduce.

Run: `uv run pytest -q tests/test_chain_smooth.py tests/test_chain_solve.py tests/test_chain_panels.py tests/test_chain_lay.py`.
Ledger C426-C433, C435, C438, C440, C444, C446, C448.

NEXT: N2h2: final step converges (trust region on a merit); then lapels open and collar fall from the start (hinge
way convention on a mirrored pair), judge X beside the reference.
