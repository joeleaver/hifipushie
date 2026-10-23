# STATE: dress_garrett_fit (Garrett jacket over the muslin shirt: muslin form fit + styling, NO sim) -- 2026-10-23, round 34

DESIGN FACTS (Joe, settled): the jacket is worn OPEN, unbuttoned; it falls straight down (no waist suppression, side
line plumb). Put "the reference jacket is worn open, unbuttoned" in every review's context. Renders show the OPEN jacket
only. Covered show-through is not a fault (C153); the shirt patches at the shoulders are culled later, don't chase them.
PROCESS: muslin fit (worn open, C171), styling by the kind's wear as data (C174 / C178), remeasurement; no sim; judged
beside the concept only (C165). Shirt = gc_garrett's shirt as worn, not tuned here. Jacket hps = "corner".
STATE: round 34 in progress. Step 1 DONE (C179): plumb takes nothing in (C94 tube cut = op opt-in `tube: true`); plumb
rows read the fall girth (fronts CF -> side seam); new gate row falls_straight (fall girth loss <= 2 %, no body seam back in
> 4 mm). Round-33 pattern FAILs it (4.8 %, CB 37 mm, sideB 16 mm in); plain plumb PASSes (flat 1113 chest -> hem).
Step 2 RUNNING: pattern p1 = plumb + side contour [chest 0, waist -2.25 mm, hem -20 mm] on sideF + sideB (8 edges):
flat fall girth chest 1113 / waist 1131 / hem 1272 = the derived targets (derive34.py on the r32 muslin a1: concept
widths waist 414 / hem 482, depth held at the waist, back plumb from the seat at the hem -> worn ~1170 / ~1240; flat
target = r33 flat 1055 + (worn target - r33 worn 1094 / 1021) = 1131 / 1274). gj34.sh p1: gate -> fit -> kb style -> reads.
CONCEPT ROWS: lapel 150 127/134; V 200 237; roll 150/250 69/64; edge 450/550/650 71/78/94; hem 482; waist 414; side line
<= 20; length 748. R33 (k33): lapel 133/130, V 221, roll 75/57, edge 39-45/51-53/68, waist 375, hem 415, length 753.
NEXT: read p1's gate (falls_straight PASS) + muslin + styled reads vs the concept; sheets (post34.sh); if the edge at
450/550/650 still opens less than the concept with the right hem, find why; then V 221 vs 237.
## Method ($FR34 = /mnt/data/hifipushie/dress_garrett/fit_round34; run.sh: this worktree)
flat34.py '<json>' (flat rows, light); gj34.sh <tag> '<json>' (gate34 capped -> asm_<tag>.pkl, stylekb -> asm_<tag>s.pkl,
reads34.sh -> r_<tag>.log / r_<tag>s.log); post34.sh <tag> (recull + concept | clay | diag sheets in check/);
derive34.py <asm> (concept widths -> girth targets).
## Dead ends (one line each)
- Gravity substitutes; release sims (cloth.md r20-r29); lapel pins in a release (r29b); roll rows graded (C156).
- Closed (buttoned) fit as the base for the lapel (C171). UNDER_FLOOR on by default (C172). Break swung out (r30).
- Opening pulls with no down: a free front swings up and open (r31). belly 14 @ 0.35 fails waist_suppression (r32).
- Point grips down the edge (@0.33 zigzag, @0.6 flare: C178). Swing hinged on the side seam (9 deg). Swing alone
  (forward pot belly, t5). Hem-point pull after the swing (150 mm drag, t7). Lay-back after the finish (grip held).
- The tube-sized plumb cut (C94): tapers under the chest; gated out by falls_straight (C179).
