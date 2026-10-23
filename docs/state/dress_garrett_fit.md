# STATE: dress_garrett_fit (Garrett jacket over the muslin shirt: muslin form fit + styling, NO sim) -- 2026-10-23, round 39

DESIGN FACTS (Joe, settled): the jacket is worn OPEN, unbuttoned; it falls straight down (no waist suppression, side
line plumb). Put "the reference jacket is worn open, unbuttoned" in every review's context. Renders show the OPEN jacket
only. Covered show-through is not a fault (C153); the shirt patches at the shoulders are culled later, don't chase them.
PROCESS: muslin fit (worn open, C171), styling by the kind's wear as data (C174 / C178), remeasurement; no sim; judged
beside the concept only (C165). Shirt = gc_garrett's shirt as worn, not tuned here. Jacket hps = "corner".
STATE: round 38 done (C185, C186); suite PYTEST_EXIT 0, 297 passed, 4 xfailed ($FR38/suite.log). PATTERN unchanged (gc_garrett v5; gate g1 PASS_WAIVED). FIT = r35's g1 (PLUMB_HOLD, C181);
$FR38/fit_g1.pkl is a read-only copy (a tag "g1" once wrote through the symlinks: never name a styled tag after a fit).
STYLING (default, kb jacket.wear.open): hold the side / back hems (C186), hold above break, relax, SLIDE (C184 un-lap, now lets go of its grip above
cutawayTop, C185), plumb SWING (C182), lay-back, smooths, hem down, relax, then each edge break..cutawayTop drawn to its
front-view CHORD (smooth_border spline 0, C185). CULL C183.
READS k3 (default) | r37 k1 | concept: edge 450/550/650 60-64/74-77/101 | 41-50/74-77/101 | 71/78/94; edge profile
400/450/500 L 64/61/63 R 63/63/63 (k1 42/39/63, 47/46/63); side view ahead w/-100/-200/-300 L 34/30/34/34 R 26/26/33/31;
hem+30 444 | 486 | 482; side line out at the hem 29-42 | 48-62 | ~42; length 736; V 232, lapel 137/136, roll 76/62
unchanged; threads p99 7.42 (fronts 8.43) | 7.73 (8.79).
LOOK (check/*_k3c.png, check/joespot_before_after.png): the inward curve under the break is gone, both edges run straight
and plumb from the break to the cut-away's top, then the cut-away; the sides fall straight; upper half as r37. Still: the
edge is plumb (64) where the concept leans out a little (71 at 450); hem+30 38 narrow; shard specks at the sleeve heads.
ROUND 39 (in progress, $FR39 = /mnt/data/hifipushie/dress_garrett/fit_round39): step 1 done: sleeve-head specks = shirt touching
the jacket (-3..+3 mm), culled by C187 (cloth_layers touch band + triangle-sampled cover); seen 208 -> 17.
SEAM (coordinator, Joe on r38's front|side seam, TOP): measured: seam at 91-93 deg (on the silhouette; r34 without the hold
66-79), fold across it 34-110 deg in the fit (r34 0-26): PLUMB_HOLD pins the seam LINE, the panels crease along it.
Trying pattern_form plumb hold "band" (panels move with the seam; default off): fits b40 / b80 via $FR39/fits39.sh.
NEXT: judge b40 / b80 (seamn39 fold, seam39 angle, Joe crop + side) -> default if it flattens the seam with edges /
upper half / hems kept; then step 2 (650), 3 (hem 444), 4 (450 lean), LOOK review.
## Method ($FR38 = /mnt/data/hifipushie/dress_garrett/fit_round38; run.sh: this worktree; fit_g1.pkl read-only)
sw38.sh <tag> <params json> (mkv38 variant of the kb style on g1 + reads, no render); tab38.sh <tags>; sty38.sh g1 <tag> (default
kb + reads + sheets); op38.py (op by op); flare38.py (per-piece hem moves); crop38.py (Joe's spot crop); diag38.py (forced shares).
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
- r38: soft (feathered) hold round the break; ramp power / lead; a 'roll' op past the break (19-24 % strain); 3D chord
  smooth (cut into the shirt); side / back follow faded at the hem (with_fade: flare unchanged).
