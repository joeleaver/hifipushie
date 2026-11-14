# STATE: step 5 rewritten (docs/proposals/step5_rewrite.md; CHAINS ONLY; N2g: PANEL START + FLEXIBLE SOLVE)

Step 5 lays out the CHAINS (boundary + fold rows + lines across), lengths given, only bends chosen, nothing held.
Step 6 fills surfaces between them. Runs N1 -> N2 -> N2b -> N2c -> N2d -> N2e -> N2f -> N2g (this).

## Current code
- `panel_start.starts`: each piece placed from its own tapes (girth roll / edge on its tape). NEW `_ways`: a girth piece
  rolls the way its SEAMS say (one flat cuts a pair, so a flat may show either face: the jacket's front flat shows its
  inside). Settled before edge-taped pieces read their sides. Test: test_girth_piece_rolls_the_way_its_seams_say.
- `chain_panels.Panels` + `fit_start`: rolled panels fitted to that start. Its ruled hinges turn the WRONG way on the
  jacket (way read off the flat: collar fall up into a funnel). The N2g driver sets every hinge's turn to 0 (start
  unturned) and leaves turning to the solve's fold terms.
- `chain_assemble` (rigid assembly / dress / close): KEPT. N2g did not pass, so the brief's deletion did not apply.
- Proof: `spikes/n2g_jacket.py <out> <loaded.pkl> [measure] [bindall]`: start, then chain_solve on the unsewn network
  with seam pairs pulled to their midpoints (SEAM_W 0.1, 1, 10), then the sewn network. Render `spikes/n2c_render.py <run>
  <pkl> <ref> X_start.npy|X.npy quick`. ws /mnt/data/hifipushie/n2g (loaded.pkl in /mnt/data/hifipushie/n2/mine).

## Numbers (jacket; 4,326 points, 2,994 nodes; load 80-89)
- N2f start as landed (n2g/s0): front rolled mirrored. Seams front ~ sleeve 299 / 317 mm (mean / max), front ~ back 263,
  front ~ side 246, collar ~ facing 98 / 147. Links: 161 over 2 % (row links between panels; max 717 % collar).
  Inside 1686.
- Start with `_ways`, unturned (n2g/run2/X_start_quick_sheet.png): front ~ side 90 / 93, front ~ sleeve 66-99,
  back ~ front (shoulder) 203 / 282, back ~ sleeve 113-147, collar ~ facing 101 / 138, back ~ back 119 / 128.
  Links: 156 over 2 % (max 710 %). Inside 1414. Panel fit rms 18.6 mm.
- Solved (run2: only pieces sewn to nothing bound; n2g/run2/X_quick_sheet.png): FAIL. Links median 5.1 %, max
  1233 % (collar), 2960 of 4341 over 2 %. The projection stops at its 40-pass cap without converging. Seams are shared
  nodes: sides moved up to 164 mm to meet (back ~ front 116 / 164). Merge jump after the stages: up to 109 mm
  (facing ~ front). Folds: hems 75-93 of 90 per row (R undersleeve 39), collar fall 68 / 90, lapels L 31 / 110, R 11 / 61
  of 85 / 85. Inside 47. Tapes 56-73 mm mean off (biceps, chest, waist). Wall: 227 s (stages 46 / 37 / 31, sewn 51).
- run1 (every follower bound): the collar bound point for point on the undercollar fought its own fall: links 3966 %.
- Beside the reference: the torso wraps the body with no lean and the sleeves are tubes down the arms (better than any
  assembly so far). Collar: a crumpled knot at the neck base, no roll, no fall. Lapels: not turned back, the front
  edges run straight up to the neck. Sleeve caps sit on the armholes roughly. Hem: stepped (fronts lower than back
  and sides). The links are far off their cut.

## Open faults (ranked)
1. Links don't hold: the projection hits 40 passes. Find the infeasible constraint set (seam sides that differ: sleeve
   top/under 58 mm, collar/undercollar 34 mm; contact vs links; at-most edges). Read the projection's worst rows per pass.
2. Hinge way convention: Panels' hinge way and chain_lay.fold_rows' toward disagree. One convention, tested on a
   mirrored pair and a flat drawn inside-up.
3. Shoulder: a vertical girth roll can't go over the shoulder (start seams 200-280 mm).
4. Collar / undercollar: a fold on a ply that is bound flat; bind only the undercollar's free edge, or fold both.

Run: `uv run pytest -q tests/test_chain_panels.py tests/test_chain_lay.py tests/test_chain_solve.py tests/test_chain_plies.py`.
Ledger C426-C433, C435, C438, C440, C444, C445.

NEXT: N2h: make the sewn chain_solve hold its links from the N2g start (projection infeasibility, named per constraint), and fix the hinge-way convention, then judge X beside the reference.
