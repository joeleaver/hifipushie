# STATE: step 5 rewritten (docs/proposals/step5_rewrite.md; CHAINS ONLY; N2c: ASSEMBLE THEN DRESS)

Step 5 lays out the CHAINS (boundary + fold rows + lines across), lengths given, only bends chosen, nothing held.
Step 6 fills surfaces between them. Runs N1 (solver) -> N2 (plies) -> N2b (chains only) -> N2c (assemble, this) -> N3.

## Current code
- `chain_solve.py` (N1), `chain_solve_plies.py` (N2), `chain_lay_net.chain_network` (N2b: chains + Delaunay lines).
- `chain_lay.lay(net, cnet, keep, body, plan, holds, frame)` (N2c, replaces N2b's walk): ASSEMBLED start. Order: taped
  piece first, then the piece sewn to most placed nodes, followers after. Each piece: sewn nodes stay (one chain, a node
  per sewn group), the rest by `_ruled` (off the nearest placed point, continuing the surface already sewn there; a
  follower lies back on it; the first piece away from its partners' tapes), then `arap` (as rigid as possible, out of
  the frame). Folds turned at placement (`_fold_side`: the outline arc enclosing the smaller area with the row; a node
  turned once; not turned when its side carries > 25 % of a placed piece with no row: named). `bend`: one
  chain_net.project over nodes (links exact, lines exact/at most, out of frame). `measures`: links % per piece,
  loops_open_mm (node level), sides_differ_mm (each side of a seam vs its own cut: ease or a pattern fault), folds,
  inside. start.closed / start.named.
- `chain_settle.py`: skeleton(body) from landmarks, grown(body, s) (each vertex towards its skeleton point), girth_pulls
  (a piece's chain points near a loop tape's plane pulled to it at their angle), settle (chain_solve per GROW stage).
- Proof: `spikes/n2c_jacket.py <out> <loaded.pkl> [assemble]`, `spikes/n2c_render.py <run> <pkl> <ref> X.npy [quick]
  [thin]`. ws /mnt/data/hifipushie/n2c/ws; loaded.pkl /mnt/data/hifipushie/n2/mine. N2b spikes deleted.

## Numbers
- tests: test_chain_assemble 3 (tube closed by bends, links < 0.5 %; b 30 mm short named "a ~ b"; stiff collar roll
  160 turned to 10 deg off, links 0.006 %), test_chain_lay 4, test_chain_solve 9, test_chain_plies 3.
- JACKET run2 (/mnt/data/hifipushie/n2c/run2, report.json; assemble 122 s, settle 146 s, load 120-420): order
  undercollar, front.L, side.L, back.L, back.R, front.R, side.R, sleeves, collar, facings. Seam gaps 0 at every stage
  (one chain). Placement links (after ARAP, before bends): side.L 2922 %, side.R 1645, under sleeve.R 1548, front.R
  1472, back 506, front.L 311, undercollar 56, sleeve tops 62-87. After bends (28 projection passes, median move 86 mm,
  max 299): worst 554 % (collar), 1,864 of 4,317 links > 2 %, 58 loops open, 52 inside the frame. Settled (grown 0.65,
  1.0): worst 806 %, 2,262 > 2 %, 50 loops open, 12 inside; folds 60-120 deg off (hems stuck at 90); neckline pull
  59 mean / 124 max mm, chest 21-29 mean mm.
- Renders run2/X_asm_thin_quick_sheet.png, run2/X_quick_sheet.png: FAIL. The whole garment is a wad at the shoulders
  and upper chest; nothing reaches the hem or down the arms; collar and facings knot round the neck. Worse than N2b's
  start.

## Open faults (ranked)
1. Per-piece placement: ARAP from few seam nodes (front from a 24-node gorge, side from a seam the front already bent)
   gives links 300-2,900 % before any bend; the projection can't undo it. Check each placement ALONE (render + links)
   before sewing the next; suspects: `_ruled` B = 0 where no cloth is near (points collapse on the seam line), ARAP's
   push-out fighting its own solve, bad T/B where the placed line is short or curved.
2. The collar's fall turned though undercollar has no roll row (the 25 % rule didn't fire): step 4 question as before.
3. Hems: the turned hem side shares nodes with the other sleeve piece; both sit at 90 deg.
4. A bends-only angle solve (hinge per seam) was not written: projection is the only bend step.

## Decisions in force
- Seams are one chain from the start; nothing is closed by a solver (Joe 2026-11-12). No held set, no role names.
- A seam whose sides differ, or a loop bends can't close, is named (back to step 4), never stretched.

Run: `uv run pytest -q tests/test_chain_assemble.py tests/test_chain_lay.py tests/test_chain_solve.py tests/test_chain_plies.py`.
Ledger C426-C433, C435.

NEXT: N2c-2, fix per-piece placement: sew the torso one piece at a time on the jacket, render each alone with its links,
until every piece comes out of ARAP under 5 %; only then bends, settle and N3.
