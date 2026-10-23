# STATE: dress_garrett_fit (Garrett jacket over the muslin shirt: muslin form fit + styling, NO sim) -- 2026-10-23, round 35

DESIGN FACTS (Joe, settled): the jacket is worn OPEN, unbuttoned; it falls straight down (no waist suppression, side
line plumb). Put "the reference jacket is worn open, unbuttoned" in every review's context. Renders show the OPEN jacket
only. Covered show-through is not a fault (C153); the shirt patches at the shoulders are culled later, don't chase them.
PROCESS: muslin fit (worn open, C171), styling by the kind's wear as data (C174 / C178), remeasurement; no sim; judged
beside the concept only (C165). Shirt = gc_garrett's shirt as worn, not tuned here. Jacket hps = "corner".
STATE: round 35 done; suite: see $FR35/suite.log. PATTERN unchanged (gc_garrett v5, r34's plumb pattern, flat fall girth
1113 / 1131 / 1273; gate g1 PASS_WAIVED 17b169ab / e31aac35, falls_straight PASS).
FIT (C181, default for plumb designs): pattern_form.PLUMB_HOLD holds the front|side and side|back seams below their
tops in y on the vertical through the top as it HUNG before the seat (soft, w 2, ramp 50 mm). Won the A/B over the same
rule as a first styling op (garment_pull.plumb: stops half way on stretch, fronts stay lapped) and over live / xy anchors.
READS g1s (default) | r34 p2s | concept: edge 450/550/650 59-60/87-92/122-126 | 24/11/6 | 71/78/94; waist 434 | 384 | 414;
hem 470 | 425 | 482; side line in max 21 | 40 | <= 20 (hem flares 30 out); V 232 | 221 | 237; lapel 150 137/136 | 135/131 |
127/134; roll 150/250 76/62 | 77/60 | 69/64; length 727 | 757 | 748; flaps sunk 0/25, off body 49-51.
LOOK: fronts OPEN (r34 closed), upper half as r34. Faults: the lower fronts open too far toward the hem (650: 124 vs 94)
with the hem corners thrown out sideways (coat tails), hem flared, fronts 21 mm short, side view a sack (front panel well
off the belly), shirt show-through at the armholes / chest sides (509 vs 475 verts).
NEXT: (1) the hem corners: the kb swing turns 48 deg about break -> sideF.b now that the seam sits back (y -27): read the
turn / pull-down ops op by op (runops) on asm_g1, cap the swing by the edge reads (or the front's hang) so 650 lands ~94
and the length stays ~748; (2) the side-view sack: front panel depth at the belly; (3) V 232 vs 237 (5 mm); (4) kb cutawayTop.
## Method ($FR35 = /mnt/data/hifipushie/dress_garrett/fit_round35; run.sh: this worktree; r34 tools in $FR34)
fs35.sh <tag> '<garment json>' [ops.json] (fit35 = on_form on the stored spec, capped -> asm_<tag>.pkl, stylekb, reads35);
gj35.sh <tag> (gate35 on the stored spec + style + reads + post35 sheets); tab35.sh r_*.log (the table rows);
path35.py (the side seams' path); mkops35.py (plumb op + kb). r34: flat34, runops.sh, op34, seam34, derive34.
## Dead ends (one line each)
- Gravity substitutes; release sims (cloth.md r20-r29); lapel pins in a release (r29b); roll rows graded (C156).
- Closed (buttoned) fit as the base for the lapel (C171). UNDER_FLOOR on by default (C172). Break swung out (r30).
- Opening pulls with no down: a free front swings up and open (r31). belly 14 @ 0.35 fails waist_suppression (r32).
- Point grips down the edge (@0.33 zigzag, @0.6 flare: C178). Swing hinged on the side seam (9 deg). Swing alone
  (forward pot belly, t5). Hem-point pull after the swing (150 mm drag, t7). Lay-back after the finish (grip held).
- The tube-sized plumb cut (C94): tapers under the chest; gated out by falls_straight (C179).
- Flare in the front panel's side edge (p1): laps the fronts more. Side hem pulled out before the swing (sp1/sp2): peplum.
- Plumb seams as a first styling op (b1 / b2): stops half way on stretch. xy holds (a1 / a4): box. Live anchor (a3): pinched sides.
