# STATE: dress_garrett_fit (Garrett jacket over the muslin shirt: muslin form fit + styling, NO sim) -- 2026-10-23, round 37

DESIGN FACTS (Joe, settled): the jacket is worn OPEN, unbuttoned; it falls straight down (no waist suppression, side
line plumb). Put "the reference jacket is worn open, unbuttoned" in every review's context. Renders show the OPEN jacket
only. Covered show-through is not a fault (C153); the shirt patches at the shoulders are culled later, don't chase them.
PROCESS: muslin fit (worn open, C171), styling by the kind's wear as data (C174 / C178), remeasurement; no sim; judged
beside the concept only (C165). Shirt = gc_garrett's shirt as worn, not tuned here. Jacket hps = "corner".
STATE: round 37; suite (17 files, capped -rs) PYTEST_EXIT 0, 296 passed, 4 xfailed ($FR37/suite.log). PATTERN unchanged (gc_garrett v5; gate g1 PASS_WAIVED). FIT = r35's g1 (PLUMB_HOLD, C181).
STYLING (default, kb jacket.wear.open): hold above break, relax, SLIDE (C184: un-lap, the lapped edge slid round the body
keeping its offset, ramp break -> cutawayTop, side + back following, until stretch: half the lap), plumb SWING (C182, now
28 deg), lay-back, smooths, hem down, relax. CULL C183 (pierce_out).
READS k1 (default) | r36 h1s | concept: edge 450/550/650 41-50/74-77/101 | 54-57/79-82/111 | 71/78/94; side view ahead
of the body w/-100/-200/-300 L 35/28/31/35 R 20/26/32/32 | 38/47/55/42, 27/38/50/38 | (fit 36/26/25/9); hem+30 486 |
454 | 482; side line out at the hem 53-62 | 29-37 | ~42; corner 748/743 | 739/735 | 748; waist 438 | 434 | 414;
V 232, lapel 137/136, roll 76/62 unchanged; threads p99 7.73 (fronts 8.79) | 7.36 (8.24).
LOOK (check/*_k1c.png): side view flatter, the lower front no longer bellies past the chest line; the cut-away opens
like the concept below the waist; the edge pinches in under the break (450 dip, worse); side panels kick out at the
hem (a slight skirt flare); shard specks at the sleeve heads remain; upper half as r36.
UN-LAP ALONE (u5f) stops at half the lap: the BREAK CORNER (373-400 below HPS, x 40-70) stretches first; edge 39-47/
51-55/67-69, on the body. Per-vertex plumb (no ramp) tears that corner (17.6 % at a third of the lap).
NEXT: (1) the 450 dip = the break corner: the cloth just under the held break can't follow (top-3 % strain there in
every slide): let the hold above the break end softly (feather / release a ~30 mm patch round the break) or let the
roll extend below the break, measured on V / lapel / roll; (2) the side hem flare from the side + back follow (try
"with" ramped to 0 at the hem or a hem-held side panel); (3) 21 mm short fronts largely gone (corner 748); check
front_length 741; (4) shard specks at the sleeve heads.
## Method ($FR37 = /mnt/data/hifipushie/dress_garrett/fit_round37; run.sh: this worktree; r36 tools in $FR36)
op37.py (op by op), mku37.py (slide variants), diag37.py (slide forced to shares: strain map), sty37.sh <fit> <out> [ops].
op36.py <asm> <tag> [ops.json] (op by op + edge33 + fwd36 reads); mkops36.py (kb + plumb, variants); sty36.sh <fit>
<out> [ops] (style + reads36 + edgeprof36 + prof36 + fwd33 + post36 sheets); tab36.sh r_*.log.
## Dead ends (one line each)
- Swing gripped from the break (r36 p2 / p3): jams at 0 deg. Lay-back direction / hem / free sides (q2 q3 r1): stretch-bound.
- Gravity substitutes; release sims (cloth.md r20-r29); lapel pins in a release (r29b); roll rows graded (C156).
- Closed (buttoned) fit as the base for the lapel (C171). UNDER_FLOOR on by default (C172). Break swung out (r30).
- Opening pulls with no down: a free front swings up and open (r31). belly 14 @ 0.35 fails waist_suppression (r32).
- Point grips down the edge (@0.33 zigzag, @0.6 flare: C178). Swing hinged on the side seam (9 deg). Swing alone
  (forward pot belly, t5). Hem-point pull after the swing (150 mm drag, t7). Lay-back after the finish (grip held).
- The tube-sized plumb cut (C94): tapers under the chest; gated out by falls_straight (C179).
- Flare in the front panel's side edge (p1): laps the fronts more. Side hem pulled out before the swing (sp1/sp2): peplum.
- Plumb seams as a first styling op (b1 / b2): stops half way on stretch. xy holds (a1 / a4): box. Live anchor (a3): pinched sides.
