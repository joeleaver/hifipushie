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

## Last round (wf_simon, final code; ZOZO output from the worker, 144 frames local, finish re-applied by dev/refinish.py)
closed: free chains 0.0 %, threads p99 5.62 max 26.95; open: free chains 0.003 %, threads p99 7.15 max 47.68; seam gap 0; no collider cut, nothing pushed.
Renders /mnt/data/hifipushie/chain_garment/renders/tool_{closed,open}_{fig,neck,collar}_*.png. Judged: closed ~70 %, open ~55-60 % of the references.

## Known limits (ranked)
1. Open: shoulder cloth rides over the collar leaves (leaves half buried), collar stands high, plackets ragged at the throat. Closed: same fault, milder.
2. wf_simon's own pattern FAILS pattern_check (seams, flat_pattern: S12 band 436.8 vs 441.2, ease -1.0 % at the limit; 7 rows unmeasured): the tool
   refuses it. The proof ran the worker directly (same code, gate skipped). A blind trial must reach a PASS first.
3. The tool's spawn + answer path was not run to a built result (it refused at the gate on wf_simon); the worker it spawns was.
4. Free cloth rises 7-8 mm on average in the hang (drop_mm negative): not understood.
5. Stiff chains are not all exact after surfaces: collar fold line 7.7 % closed / 16.3 % open, collar edge 9.3 % closed (held links, read not gated).
6. Cuffs: cut closes 183 mm, forearm needs 200 mm at the seam: the ring flares; held links read 28 %. Sleeve hems gather into cuffs without pleats.
7. Soft mesh 20 mm: seams every 20 mm, coarse. Corner patch at the leaf's neck end not ported. Post-hang lines across plackets may shorten.
8. game_garment gated: no export from chain results. Roles proven: band + fall + rings + tubes + panels only, one body, no transfer test.

STATE: tool + gating landed on branch chain-garment. NEXT: fault 1 (fall over the soft cloth), then a default shirt that passes pattern_check, then the blind trial.
