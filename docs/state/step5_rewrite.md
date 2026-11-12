# STATE: step 5 rewritten (docs/proposals/step5_rewrite.md, approved 2026-11-11; cut to CHAINS ONLY 2026-11-12)

Step 5 lays out the CHAINS (boundary + fold rows + a few lines across), lengths given, only bends chosen, one solve with
nothing held. Step 6 fills surfaces between them. Runs N1 (solver) -> N2 (plies term) -> N2b (chains only, this) -> N3.

## Current best (N1 solver + N2 plies term + N2b chains)
- `chain_solve.py`: `solve(net, X0, body, ties, folds, pulls, stiffness, plies=...)` -> (X, report); PD -> LM -> projection.
  Takes any Network: on the chain network it runs in 40 s (jacket, 3,000 nodes) vs 160 s on the whole cloth.
- `chain_solve_plies.py`: followers as a term on the host's ring normal (N2).
- `chain_lay_net.py` (N2b): `chain_network(net)` -> (cnet, keep): net's chains at their cut (links copied, not re-derived)
  + per-piece Delaunay lines across (inside the outline, never across a fold row; each row link a face each side), no
  interior points. Jacket 4,302 points / 3,000 nodes / 9,755 lines.
- `chain_lay.py` (N2b): `lay(net, cnet, keep, body, plan)` -> {X0, pulls, folds, ties, plies, reads, start}. Taped edge on
  its tape (lay_on_tape, then re-laid on the lifted line by its own arc), every other piece from its longest run sewn to
  laid cloth (along the partner's line by own arc), rest of the outline walked link by link at its cut aimed at a guide
  (geodesic walk on the body from the run's middle, turned every 15 deg to where its other seams + its highest length
  path say; side away from the cloth it's sewn to, a follower towards it), .R = mirror of .L, fold rows from laid ends.
  Unsewn followers (canvas) seeded on the host by bind. chain_seed.py deleted.
- Proof: `spikes/n2b_chains_jacket.py <out> <loaded.pkl> [start|noplies]`, `spikes/n2b_render.py <run> <pkl> <ref> X.npy
  [quick]` (tubes by piece). ws /mnt/data/hifipushie/n2b/ws, loaded.pkl /mnt/data/hifipushie/n2/mine.

## Numbers
- tests/test_chain_lay.py 4 pass (chains only; strip on a curved tape exact; band + panel seam < 1 mm; stiff collar's row
  turned 160 deg on a neck, links < 2 %). test_chain_solve 9, test_chain_plies 3.
- JACKET run3 (/mnt/data/hifipushie/n2b/run3, report.json): start links: within each piece exact but its one closing link
  (front 317 %, back 840 %, sleeves 1,500-3,200 %, undercollar 5,100 %, collar 10,100 %), 446 of 4,317 over 2 % (mostly
  followers + 157 collar points put at their guide). Seam gaps (mm): front~undercollar 0.8, back~side 2.9, back~sleeve
  20-47, side~sleeve 46, front~side 99, collar~undercollar 103, front~sleeve_top 114, sleeve_top~under 125, back~front
  (shoulder) 132, facing~front 201, collar~facing 203-253, back.L~back.R (CB) 304.
- After the solve (40 s, load 85-110): links worst 849 % (undercollar), 1,635 of 3,031 over 2 %; sleeves and sides <= 5 %;
  hems turned within 1.5 deg; lapels 41-63 deg off, collar fall 48-63 off; 16 inside (10.8 mm); neckline pull 54 mean /
  134 max mm; plies crossed 17-265.
- Render run3/X_chains_sheet.png: FAILS. Start (X0_chains_sheet.png) reads as a jacket: backs, sides, fronts on the torso,
  sleeves down the arms, hem at the seat; facings stand up like horns. The solve balls the torso, collar and fronts into
  the neck and shoulders; only the sleeves keep their line.

## Open faults (ranked)
1. Start seam gaps up to 30 cm: a piece walked from ONE run drifts at its far seams (CB, shoulder, facing). The solve
   merges each seam at its mean and the torso tears inward. Lay each piece fitted to ALL its laid seams (a run per seam,
   the outline between runs walked from both), or lay the torso ring first (front, side, back closed round the chest
   tape) before the neck. Collar: 157 points (its inner roll rows' ends) not reached by any walk.
2. Followers sewn to their host are walked on it, but the facing goes up off the lapel (its side vote); canvas bound on
   long Delaunay triangles cuts through the body (ply term at chain level needs host triangles near the follower).
3. Undercollar has no roll row: the collar's planned fall can't happen on a stiff flat host (step 2/4 question).
4. Girth tapes (chest, waist, hips) are not pulls yet: only the taped edge pulls.

## Decisions in force
- No held set, no role names, no wear state in chain_solve*, chain_lay*. Pulls soft. Followers are a term.
- The start is isometric per piece; gaps are measured, never stretched (C433).

## Dead ends
- PD stiff springs; LM alone; contact rows in PD; stale CG; chord steps (C426). Whole-surface seed (C431, deleted).
- Frame transported along the outline walk (holonomy: 10-60 cm loop gaps): replaced by the guide (one geodesic per point).

Run: `uv run pytest -q tests/test_chain_lay.py tests/test_chain_solve.py tests/test_chain_plies.py`. Ledger C426-C433.

NEXT: N2c, close the start's seams: lay each piece from all its laid seams (or torso ring first), then re-solve; only then
N3 (step 6 fill + wiring).
