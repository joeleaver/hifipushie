# STATE: step 5 rewritten (docs/proposals/step5_rewrite.md; CHAINS ONLY; N2j: LINES ACROSS ARE REAL CHAINS)

Step 5 lays out the CHAINS (boundary + fold rows + lines across), lengths given, only bends chosen, nothing held.
Step 6 fills surfaces between them. Runs N1 -> ... -> N2j -> D1 (contact makes the stretch) -> D2 (start outside: not
enough) -> D3 (the roomier s4-31 jacket: contact stretch gone, shape not).

## Current code
- `chain_lines.lines` (N2j): per piece a lattice every 30 mm, cut by outline / fold rows; real chains, links exact.
- `chain_lay_net.chain_network`: lines are chains (kind 2 along, 3 across); faces Delaunay, edges at most flat.
- `panel_start.starts` + `chain_panels.Panels.fit_start`: the rolled-panel start from each piece's own tapes.
- `Panels.outside` (D2): each panel moved out of the body by its own numbers, bounded.
- D3: step 4's `draft_tapes.row` (piece_tapes) refuses what panel_start refuses: a sewn piece with no girth, an edge
  map naming several tapes. s4-31's approved jacket broke both (facings on a length only; collar on two neck halves).
- Drivers: `spikes/n2j_jacket.py <out> <pkl> measure` (network + start), `spikes/d2_start.py` (outside start),
  `spikes/d1_where.py <out> <pkl> <run> E1|E5|E6` (now also writes the solve's contact and tape reads),
  `spikes/n2c_render.py <run> <pkl> <ref> X.npy [quick]`. Loading: /mnt/data/hifipushie/d3/load.py (needs
  HIFIPUSHIE_ASSETS=/home/joe/dev/hifipushie/workspace/_templates).

## D3 (2026-11-16; /mnt/data/hifipushie/d3: ws (s4-31 copy, PATCHED: facings + chest/waist/hips, collar and
undercollar edges on the `neck` loop; original jacket.json.orig), loaded.pkl, n2j/, run/, out/, runs.log)
| run | over 2 % | worst | inside | where |
| E1 pattern alone | 24 / 6,423 (D1 0) | 7.6 % | - | armhole cap ease (sleeve side 7-8 % longer, ~36 mm an armhole); 0.2 mm link at sleeve_top.R hem corner |
| start (outside) | - | - | 0 (D2 20) | seams 126 mm apart mean, 413 max (D2 87 / 317) |
| E5 + contact | 75 (D2 873, D1 354) | 5.0 % | 0 | collar fold rows 43, undercollar 19, under-sleeve caps 12 |
| E6 + tapes, folds | 1,459 (D1 1,224) | 409 % | 113, 34 mm | collar 356, backs 420, undercollar 179, sleeves 250 |
E6 tapes off 30-290 mm (backs' chest 289, fronts 200-235); folds: lapel rolls at -85 as planned, collar fall -69 / -104
of -90 (median off 38-56 deg), sleeve hems near plan. Wall: E1 185 s, E5 219 s, E6 195 s (load 10-16).
LOOK (beside run/X_start_quick_sheet.png, E5_X_quick_sheet.png, E6_X_quick_sheet.png, E6_X_chains_sheet.png):
E5: every piece, backs too, folded flat in a slab IN FRONT of the chest: links exact, 0 inside, nothing round the body.
E6: wraps the torso, back hem at the seat (right length); collar a crumpled ring at the neck base, no roll, no fall;
lapels not turned back; fronts meet at CF with a jog, not open to a break; sleeves are not tubes down the arms (knots at
the elbow / back of the waist); every chain wiggles. Far from the reference.
Reading: the roomier pattern removed the CONTACT stretch (E5 75 vs 873), so D1 / D2's ease question was real. What is
left follows the START: seams 126 mm apart merged at once by the sewn solve, tapes pulling each piece to its own tape;
and with no tapes the merge folds the garment flat (E5). Link / inside counts cannot judge step 5: look every run.

## Open faults (ranked)
1. A start whose SEAMS meet (panels fitted to seam pairs + contact together), or N2j's unsewn continuation from it.
2. Seams must not tunnel: E5 moved the backs through the body to the front (contact is per point, not per link).
3. Ease as a declaration: the cap's 7-8 % (step 4 should say which side gives it up); collar start.

Run: `uv run pytest -q tests/test_chain_panels.py tests/test_chain_lines.py tests/test_chain_solve.py`.
Ledger C426-C433, C435, C438, C440, C444, C446, C448, C457, C462, C465, C466, C486.

NEXT: D4: a start whose seams meet (seam pairs + contact fitted together on the panels' numbers) on the D3 copy
(/mnt/data/hifipushie/d3/ws), then E5 / E6 from it, judged on the drawing first; s4-31 must redeclare its facing and
collar tapes (step 4 now refuses them) before Joe re-approves.
