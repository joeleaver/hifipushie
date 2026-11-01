# STATE: chain garment -> garments built from the pattern's outline (library + tools since 2026-11-01)

Joe: "This is how we should build clothes, right here." "that should be the only path available to the agent for starting
clothing." "We need to get to a point where a blind agent can build a great-lookin piece of clothing without tons of
iterations or manual feedback."

## What exists
- `src/hifipushie/chain_net.py`: general core (Network, sewn nodes, chains, lines, mirror_map, Contact, Threads, project = fast
  projection with Levenberg damping and a per-point step cap, BendSolve = sparse LM, fill). Docstring is the spec.
- `src/hifipushie/chain_garment.py`: roles read from the pattern, stages, ZOZO job, worker, render_views. Docstring is the spec.
- Tools: `chain_garment(name, garment, wear, opening)`, `look_chain(name, garment, wear, focus, size, reference, save)`.
- `server.GATED_CLOTH` removes the old routes from the MCP layer; `HIFIPUSHIE_LEGACY_CLOTH=1` restores them. Python API untouched.
- zozo_hang.py + cloth_zozo.py came from the hang branch (worktree-agent-a31fb4eb7a07d59fa); made_shape.py etc did not (lazy imports,
  not used by the chain path; zozo_hang.settle / write_job would need them).
- Tests: tests/test_chain_garment.py. Dev scripts + renders: /mnt/data/hifipushie/chain_garment/ (dev/, renders/). Ledger C259-C264.

## Stages (closed): band -> fall -> rings -> soft chains -> surfaces -> threads, chains last -> fall rests on the cloth -> soft again
-> hang -> threads + chains last. Open: the closed build, then band opened, fall on it, plackets folded, soft again twice, hang.

## Known limits (ranked; see the last round's numbers below)
1. wf_simon's own pattern FAILS pattern_check (rows seams, flat_pattern; collar, front_closure, cuff, pockets, layering, fabric, colour
   unmeasured): the tool refuses it. The proof ran the worker directly (same code, gate skipped). A blind trial must reach a PASS first:
   check a default shirt can.
2. MAX_FREE_PCT is 6 %, far above "exact": free chains read 1-3 % after the hang on 20 mm soft links. Tighten when the last pass converges.
3. Cuffs: the cut closes 183 mm, the forearm section needs 200 mm at the seam end: the ring flares (one button, the overlap opens); held
   links there read up to 28 %. Sleeve hems are gathered into cuffs without pleats.
4. Soft mesh is 20 mm: seams sewn every 20 mm, chords coarse. Corner patch at the leaf's neck end was not ported (the chains are kept instead).
5. game_garment is gated: it reads sim drapes, not chain results. Export from chain results is not built.
6. Only a shirt roles set is proven: band + fall + rings + tubes + panels. A waistband ring, a lapel, a collar without a band are refused by name.
   One body only: no transfer test.

STATE: tool + gating landed on branch chain-garment; closed and open proved on wf_simon (see report). NEXT: blind trial, then the ranked limits.
