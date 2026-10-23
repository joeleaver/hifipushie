# STATE: dress_garrett_fit (Garrett jacket over the muslin shirt: muslin form fit + styling, NO sim) -- 2026-10-23, round 38

DESIGN FACTS (Joe, settled): the jacket is worn OPEN, unbuttoned; it falls straight down (no waist suppression, side
line plumb). Put "the reference jacket is worn open, unbuttoned" in every review's context. Renders show the OPEN jacket
only. Covered show-through is not a fault (C153); the shirt patches at the shoulders are culled later, don't chase them.
PROCESS: muslin fit (worn open, C171), styling by the kind's wear as data (C174 / C178), remeasurement; no sim; judged
beside the concept only (C165). Shirt = gc_garrett's shirt as worn, not tuned here. Jacket hps = "corner".
STATE: round 38 step 1 (C185). PATTERN unchanged (gc_garrett v5; gate g1 PASS_WAIVED). FIT = r35's g1 (PLUMB_HOLD, C181);
$FR38/fit_g1.pkl is a read-only copy (a tag "g1" once wrote through the symlinks: never name a styled tag after a fit).
STYLING (default, kb jacket.wear.open): hold above break, relax, SLIDE (C184 un-lap, now lets go of its grip above
cutawayTop, C185), plumb SWING (C182), lay-back, smooths, hem down, relax, then each edge break..cutawayTop drawn to its
front-view CHORD (smooth_border spline 0, C185). CULL C183.
READS k2 (default) | r37 k1 | concept: edge 450/550/650 60-64/75-77/102 | 41-50/74-77/101 | 71/78/94; edge profile
400/450/500 L 63/61/63 R 63/63/63 (k1 42/39/63, 47/46/63); side view ahead w/-100/-200/-300 L 34/31/34/38 R 26/27/35/34;
hem+30 504 | 486 | 482; side line out at the hem 33-64 | 48-62 | ~42; length 736; V 232, lapel 137/136, roll 76/62
unchanged; threads p99 7.37 (fronts 8.41) | 7.73 (8.79).
LOOK (check/*_k2c.png, check/joespot_before_after.png): the inward curve under the break is gone, both edges run straight
and plumb from the break to the cut-away's top, then the cut-away; upper half as r37. Still: the edge is plumb (64) where
the concept leans out a little (71 at 450); side panels flare at the hem; shard specks at the sleeve heads.
NEXT: (2) the side hem flare (cause: the styling: the slide's side/back follow + swing; fit alone 29-37 out, flare38.py:
side.L at the hem moves +20 out, +18 back, 32 -> 53 mm off the body); (3) 650 = 102 vs 94; (4) sleeve-head specks.
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
