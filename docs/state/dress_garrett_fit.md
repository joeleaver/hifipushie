# STATE: dress_garrett_fit (Garrett jacket over the muslin shirt: muslin form fit + styling, NO sim) -- 2026-10-23, round 34

DESIGN FACTS (Joe, settled): the jacket is worn OPEN, unbuttoned; it falls straight down (no waist suppression, side
line plumb). Put "the reference jacket is worn open, unbuttoned" in every review's context. Renders show the OPEN jacket
only. Covered show-through is not a fault (C153); the shirt patches at the shoulders are culled later, don't chase them.
PROCESS: muslin fit (worn open, C171), styling by the kind's wear as data (C174 / C178), remeasurement; no sim; judged
beside the concept only (C165). Shirt = gc_garrett's shirt as worn, not tuned here. Jacket hps = "corner".
STATE: round 34 done. GATE (C179): plumb takes nothing in (C94 tube cut = op opt-in `tube: true`); plumb rows read the
fall girth (fronts CF -> side seam); row falls_straight (girth loss <= 2 %, no seam back in > 4 mm); a plumb design's
ease bands below the chest keep only their bottom. Round-33 pattern FAILs falls_straight (4.8 %, CB 37 / sideB 16 mm in).
PATTERN (stored, gc_garrett v5; gate PASS_WAIVED 17b169ab / e31aac35, gate_status MATCH): plumb + side contour on
["sideB", "side:sideF.a>sideF.b"] [chest 0, waist -3, hem -26.8 mm]: flat fall girth 1113 / 1131 / 1273 = the derived
targets (derive34.py: concept widths waist 414 / hem 482 on the worn section -> worn ~1170 / ~1240).
READS p2s (kb default) | r33 | concept: lapel 135/131 | 133/130 | 127/134; V 221 | 221 | 237; roll 77/60 | 75/57 | 69/64;
edge 450/550/650 24-15/11-7/6-2 | 45-39/51-53/68 | 71/78/94; waist 384 | 375 | 414; hem 425 | 415 | 482; length 757 |
753 | 748; threads p99 7.7 | 7.6. Side view: back plumb now. LOOK: fronts meet at CF below the waist = reads CLOSED.
FAULT (C180, seam34.py): the extra girth goes to depth + LAP: the form fit slides the front panel's side seam forward
(hem 60 deg from CF vs r33 74-81), the same front laps 11-26 mm past CF, the swing stops at 36-40 deg. Pulling the side
hem out first (sp2: hem 489) kicks the side corners out (peplum, local warp p90 ~20 %): not adopted.
NEXT: (1) keep a plumb design's side seam on the vertical under its underarm in the fit / as the first styling op
(a "plumb seam" hold: the hanging jacket's seam position), so the flare stands at the sides and the front panel stays
where r33 had it; re-read edge 450/550/650 (target 71/78/94) and hem / waist widths; (2) V 221 vs 237; (3) kb cutawayTop.
## Method ($FR34 = /mnt/data/hifipushie/dress_garrett/fit_round34; run.sh: this worktree)
flat34.py '<json>' (flat rows, light); gj34.sh <tag> '<json>' (gate34 capped -> asm_<tag>.pkl, stylekb -> asm_<tag>s.pkl,
reads34.sh -> r_<tag>.log / r_<tag>s.log); runops.sh <src> <tag> [ops.json] (op by op; sumops.py <tag>); mkops.py
(kb + inserted ops); post34.sh <tag> (sheets in check/); derive34.py (widths -> girths); seam34.py (front panel's place).
## Dead ends (one line each)
- Gravity substitutes; release sims (cloth.md r20-r29); lapel pins in a release (r29b); roll rows graded (C156).
- Closed (buttoned) fit as the base for the lapel (C171). UNDER_FLOOR on by default (C172). Break swung out (r30).
- Opening pulls with no down: a free front swings up and open (r31). belly 14 @ 0.35 fails waist_suppression (r32).
- Point grips down the edge (@0.33 zigzag, @0.6 flare: C178). Swing hinged on the side seam (9 deg). Swing alone
  (forward pot belly, t5). Hem-point pull after the swing (150 mm drag, t7). Lay-back after the finish (grip held).
- The tube-sized plumb cut (C94): tapers under the chest; gated out by falls_straight (C179).
- Flare in the front panel's side edge (p1): laps the fronts more. Side hem pulled out before the swing (sp1/sp2): peplum.
