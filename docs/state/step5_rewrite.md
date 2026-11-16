# STATE: step 5 rewritten (docs/proposals/step5_rewrite.md; CHAINS ONLY; D4: SEAMS ON BODY LINES)

Step 5 lays out the CHAINS (boundary + fold rows + lines across), lengths given, only bends chosen, nothing held.
Step 6 fills surfaces between them. Runs N1 -> ... -> N2j -> D1 -> D2 -> D3 (roomier jacket: contact stretch gone, shape
not) -> Z1 (ZOZO sewing: no) -> D4 (the dress-form start: seams pinned on body lines).

## Current code
- `chain_lines.lines` (N2j) lattice chains; `chain_lay_net.chain_network`; `panel_start.starts` + `chain_panels.Panels`
  (rolled panels, `outside`); `chain_solve.solve` (+ _final): links hard, contact, folds, pulls soft, plies a term.
- D4: `chain_seams.fused(M)`: sewn nodes that close a piece on itself through other pieces (a check, tested; NOT yet a
  refusal anywhere). s4-31's approved jacket fails it: 22 same-piece pairs, all in the two armholes.
- Drivers: `spikes/d4_lines.py <out> <loaded.pkl> <d3 run> <ref>` (body lines, seams laid, ARAP bends, followers; writes
  cnet.pkl (armholes re-sewn), X_start.npy, laid.npz, lines.json, lines_quick_sheet.png), `spikes/d4_resew.py`
  (bad_groups, resew_armholes), `spikes/d4_solve.py <start dir> <loaded.pkl> [w]`, `spikes/n2c_render.py`.
  Wrapper /mnt/data/hifipushie/d4/run.sh slot|capped <script> ... (HIFIPUSHIE_HOME=/mnt/data/hifipushie/d4/ws).

## D4 (2026-11-16; /mnt/data/hifipushie/d4: ws (D3's patched copy), start/, solve.log)
FOUND FIRST: the approved s4-31 pattern's own sew pairs (pat.M["sew"], before join_seams) fuse each armhole: the front's
top 54 mm sewn to the UNDER sleeve, the back's shoulder corner to the top sleeve's front pitch; by union shoulder point,
underarm (front / side / back) and pitches were ONE node (13 vertices) in every step-5 run since. Links stay exact (the
armhole hangs in loops from the node), so E1's 24 links and every count missed it. The spike re-sews each armhole by
arc from the shoulder point (body front -> side -> back; cap from the crown toward the front pitch): 57 nodes a side,
body 498 mm, cap 542 (ease 8.8 %); fused pairs 22 -> 0.
Lines (lines_quick_sheet.png): neck loop from CB, hps -> shoulder point, the armhole loop (armhole_front + back tapes:
428 mm, scaled about the shoulder point to the armhole's 498: the jacket's armhole sits below the arm root), front/side
and side/back through step 2's chest shares (0.40, 0.62) at chest / waist / hips / seat (step 2 declares the chest
only), CB mid line, sleeve fore / hind from the armhole's junctions through biceps / elbow / wrist split by the sleeve
pieces' widths. They read as a jacket's style lines on a dress form. Seam vs line: shoulder -14 %, armhole +4 %,
front/side 476 on 536, side/back 513 on 477, CB 704 on 727, sleeves fore 353 / hind 515 on 511 / 514, neck 194 on 203.
| run | over 2 % | worst | inside | seams | where |
| D3 E6 | 1,459 / 6,423 | 409 % | 113, 34 mm | merged by the solve | collar 356, backs 420, sleeves 250 |
| D4 start | 3,998 | 6,408 % | 1,802, 111 mm | 0 mm (by construction) | ARAP is not isometric; collar 648 |
| D4 solved | 895 | 511 % | 50, 33 mm | 0 | collar 243, undercollar 195, sleeves 354, backs 80, fronts 7 |
Solve: 270 s (load 12-20), final not converged; seam pulls end 35 mm mean / 100 max off their lines; folds: lapel
rolls 64-87 of 85 deg, collar fall 76 of 90 (median off 43), sleeve hems -74 / 139 of +-90.
LOOK (start/X_start_quick_sheet.png, X_solved_quick_sheet.png beside reference_front.png): the torso wraps the body,
the armholes are rings at the arm root, the sleeves are tubes down the arms (D3: knots), hem at the hip (reference: at
the seat). NOT the jacket: collar a crumple at the neck base, no stand / fall; lapels not turned back to a break; fronts
hang near the sides of the chest, not open from a break; sleeves short of the wrist and crinkled; chains wiggle.
Verdict: laying seams on body lines does give a start whose seams meet (exactly, as nodes) and puts armholes and
sleeves where they belong, which no earlier start did; it does not alone make the jacket. What is left is the lines the
garment hangs on that step 3 never measured and step 4 never declared: the collar / gorge line and the break, the
armhole where the jacket's sits, side lines per girth.

## Open faults (ranked)
1. Step 4's flat gate must refuse a fused node (chain_seams.fused) and send the seam table back; s4-31 re-declares its
   armhole seams (and its facing / collar tapes, D3) before Joe re-approves.
2. Steps 2-4 declare the dress form: step 2 shares per girth (chest, waist, hips, seat); step 3 measures the jacket's
   armhole line, the gorge / collar line to the break, CB / CF mid lines, sleeve lines; step 4 names per seam its line,
   the end it starts from and which side gives up ease (cap 8.8 %); the break point on CF.
3. Step 5 from those declarations: seams laid by arc (general rule, no table), bends between, one solve; the collar and
   lapels laid on their own lines (the spike left them to ARAP and the folds: a crumple).

Run: `uv run pytest -q tests/test_chain_*.py`. Ledger C426-C433, C435, C438, C440, C444, C446, C448, C457, C462, C465,
C466, C486, C487, C488 (D4).

NEXT: the tool changes, one run each: (a) step 4 flat gate refuses `chain_seams.fused` (re-check every approved
pattern); (b) steps 2-3 declare and measure the dress-form lines (shares per girth, jacket armhole, gorge / break);
(c) step 5 lays seams on the declared lines (promote d4_lines' laying + ARAP without the table) and is judged beside
the reference on the jacket redeclared by s4-31.
