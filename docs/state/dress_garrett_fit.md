# STATE: dress_garrett_fit (Garrett jacket over the muslin shirt: muslin form fit + styling, NO sim) -- 2026-10-23, round 35

DESIGN FACTS (Joe, settled): the jacket is worn OPEN, unbuttoned; it falls straight down (no waist suppression, side
line plumb). Put "the reference jacket is worn open, unbuttoned" in every review's context. Renders show the OPEN jacket
only. Covered show-through is not a fault (C153); the shirt patches at the shoulders are culled later, don't chase them.
PROCESS: muslin fit (worn open, C171), styling by the kind's wear as data (C174 / C178), remeasurement; no sim; judged
beside the concept only (C165). Shirt = gc_garrett's shirt as worn, not tuned here. Jacket hps = "corner".
STATE: round 36 done; suite (17 files, capped -rs): see $FR36/suite.log. PATTERN unchanged (gc_garrett v5, r34 plumb
pattern; gate g1 PASS_WAIVED 17b169ab / e31aac35). FIT = r35's g1 (PLUMB_HOLD, C181), unchanged.
STYLING (C182, default): the kb swing stops where the edge below the break hangs plumb in the front view (turn
"plumb": [break, cutawayTop]): 41 / 39 deg (r35 48). CULL (C183, default): shirt poking out through the jacket where
it covers is hidden (pierce_out), never made pieces.
READS h1s (default) | r35 g1s | concept: edge 450/550/650 54-57/79-82/111 | 59-60/87-92/122-126 | 71/78/94; waist 434 |
434 | 414; hem+30 454 (sweep 472) | 470 | 482; side line in max 21, out 37 at the hem (fit's own; concept widens 42/side)
| same | <= 20 in; V 232 | 232 | 237; lapel 150 137/136 | same | 127/134; roll 76/62 | same | 69/64; length 727 | 727 |
748 (corner 728 on the FIT: the fit / pattern, not the swing); side view ahead of the body w/-100/-200/-300 38/47/55/42
| 44/52/61/47 (fit 36/26/25/9); flaps sunk 0/25, off body 49/51 (they lie on the front: the front's stand-off);
styling threads p99 8.2.
LOOK (check/*_h1sc.png): fronts open, lower corners no longer coat tails but the cut-away still swings out from the
waist (650: 111 vs 94); edge 450 dips in (54 vs 71: the edge break..cutawayTop sags in between, not gripped); side view
still a sack: the lower front ~11 mm proud of the chest's plumb line, 40-55 mm off the lower belly; armhole patches gone,
shards left at the sleeve heads; a tiny dark speck on the shirt chest (not a culled face; check).
SACK CAUSE (measured): the rigid swing about break -> sideF.b (hinge behind the edge moves it forward) + the lapped
width (opened, the panel spans a shorter chord to the held side seam and bows out). The lay-back pull stops on stretch
whatever its direction (normal 27 mm, back+down 18, with hem 21); freeing the side panels changes nothing.
NEXT: (1) the sack: lay the swung panel back onto the fit's side-view line (a stop like plumb: the front's side-view
depth back to the fit's / the chest plumb line) -- the stretch stop blocks it, so find what stretches (op36 + a strain map
on asm_p1_4) before changing the op; (2) the 450 dip: the edge break..cutawayTop hanging straight (grip from the break
jams: p2 / p3); (3) length 727 vs 748 on the fit itself; (4) cull shards at the sleeve heads.
## Method ($FR36 = /mnt/data/hifipushie/dress_garrett/fit_round36; run.sh: this worktree; r35 tools in $FR35)
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
