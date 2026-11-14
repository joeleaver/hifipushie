# STATE: step 5 rewritten (docs/proposals/step5_rewrite.md; CHAINS ONLY; N2j: LINES ACROSS ARE REAL CHAINS)

Step 5 lays out the CHAINS (boundary + fold rows + lines across), lengths given, only bends chosen, nothing held.
Step 6 fills surfaces between them. Runs N1 -> ... -> N2j -> D1 (contact makes the stretch) -> D2 (start outside: not enough).

## Current code
- `chain_lines.lines` (N2j): per piece a lattice every 30 mm, cut by outline / fold rows; real chains, links exact.
- `chain_lay_net.chain_network`: lines are chains (kind 2 along, 3 across); faces Delaunay, edges at most flat.
- `panel_start.starts` + `chain_panels.Panels.fit_start`: the rolled-panel start from each piece's own tapes.
- NEW (D2) `Panels.outside(TH, contact, gap, log)`: every panel moved out of the body by its OWN numbers (least squares:
  mean move soft, a point under the gap hard, analytic-normal jacobian), bounded: rigid motion within OUT_BOUND, a roll
  may only OPEN (curvature towards 0), taper +-0.05. Unbounded, the side piece curled into a 15 mm cone and left 28 cm.
- Proof scripts: `spikes/d2_girths.py` (girths, flat vs tapes), `spikes/d2_start.py <out> <pkl> <n2j run>` (outside on
  N2j's start, writes a run dir for `spikes/d1_where.py`), render `spikes/n2c_render.py <run> <pkl> <ref> X.npy quick`.

## D2 (2026-11-14; out /mnt/data/hifipushie/d2/{out,run}, ws d2/ws)
GIRTHS (pattern at its level, CF to CF, darts out, seam lines; vs tape + 2 pi GAP 28 mm): chest just under the
armhole 1035 vs 997 (+38; at the hollow's own vertex -19); waist 894 vs 811 (+83); hips at body height 1007 vs 993
(+15); seat at body height 1003 vs 1027 (-25), hem 984 (-44); biceps at the cap's foot 339 vs 345 (-6; +22 over the
bare arm); elbow +57; wrist +48; armhole 460 vs 431 (+29); back neck 176 vs body 193. Planned ease (garment_plan) is far
larger (chest 1108, waist 988, hips 1103): the draft has 70-130 mm less than the plan. Short of body + gap: seat / hem
(open, cut-away front: not a closed loop), biceps by 6 mm (sleeve 3.5 mm off instead of 4.5). Judged not the cause of
44-75 % stretch, but a step-4 question: the draft's ease vs the plan's.
START: inside 1,561 -> 20 points (deepest 50.6 -> 11.4 mm), under gap 2,112 -> 61 (sleeve_top 18 + 18, collar 12,
canvas 11, side 1 + 1); panels moved mean 32, max 119 mm; L / R now equal. BUT seams' start distance 68 -> 87 mm mean,
317 max, and the start already holds links across panel boundaries far off (collar 5,128 %, p99 25 %; N2j's own: 618 %).
E5 (contact, no tapes, sewn solve from that start): 873 of 6,437 links > 2 % (D1: 354), worst 75 %, collar 250,
undercollar 145, back.R 125 / back.L 117, sleeves 40-61; 20 points inside (22 mm), 1,518 under gap; not converged.
Render: d2/run/E5_X_quick_sheet.png (start: X_start_quick_sheet.png). Beside the reference: a boxy tube, sleeves crumpled
at the shoulder ending above the elbow, collar a stand-up band round the neck with no fall. Far from the reference.
Reading: inside points were not the whole story. Now symmetric, the stretch follows the SEAMS (pieces started 87 mm apart
and merged at once by the sewn solve) and the collar's broken start. E6 not run (E5 failed its bar first).
Seam ease (D1, unchanged): 130 of 754 seam links differ > 2 % between sides: sleeve caps ~5 %, under the elbow to 29 %
locally, collar to front to 18 %.

## Open faults (ranked)
1. A start whose SEAMS meet: panels fitted with contact AND their seams (rigid + roll per panel, seam pairs as residuals,
   contact a hard inequality) instead of outside() alone; or N2j's continuation (unsewn stages) from the outside start.
2. The collar's start: links across its panels thousands of % off before any solve (hinge rows / ruled panels at 0 turn).
3. Ease as a declaration; draft ease vs plan (girths above); collar fall, sleeves thin (from N2i).

Run: `uv run pytest -q tests/test_chain_panels.py tests/test_chain_lines.py tests/test_chain_solve.py`.
Ledger C426-C433, C435, C438, C440, C444, C446, C448, C457, C462, C465, C466.

NEXT: D3: start with seams closed and contact together (panels' numbers fitted to seam pairs + contact), fix the collar's
cross-panel links at the start; then rerun d1_where E5 from it: links < 2 %, 0 inside, before tapes (E6).
