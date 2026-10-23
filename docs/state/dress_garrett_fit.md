# STATE: dress_garrett_fit (Garrett jacket over the muslin shirt: muslin form fit + styling, NO sim) -- 2026-10-23, round 30

DESIGN FACTS (Joe, settled): the jacket is worn OPEN, unbuttoned; it falls straight down (no waist suppression, side
line plumb). Put "the reference jacket is worn open, unbuttoned" in every review's context. Renders show the OPEN jacket
only; the closed fit is an internal stage. Covered show-through is not a fault (C153); the cull hides only what no judged
view sees (C158). NEW PROCESS (Joe): muslin fit, styling, remeasurement; no release sim; judged beside the concept only
(C165: no r28 / r29 columns). Shirt = gc_garrett's shirt on the muslin fit, styled as worn (on_form), not tuned here.
STATE: round 30 done (handover ~100 tool calls). Suite (17 files, capped -rs, wf_simon on): exit 0, 283 passed, 4 xfailed, 0 skipped. Spec carries r29p2 (was missing: applyspec.py). Closed fit c1 misfits:
neck (collar / stand warp -17 / -19 %, twisted), fronts' neck-shoulder corner (weft -8 %), the lap at 250-350. ROLL: the
top button held it closed (C171); fitted worn open (spec's worn_open break 64) the roll is the concept's. Styled open
(no sim) with the new layer floor (C170; body + flaps; the shirt floor blocks opening). hps A/B: CORNER recommended.
Best look s5f (corner, worn-open fit, styled): lapel 150 133/134 (127/134), V 200 244 (237), edge 450/550/650 82/76/84
(71/78/94), shirt shows 13/15/25 (10-20), side line 29/26 (<=20), hem 426 (482), hem below HPS 754 (748), crumple p95
13.9/12.3, threads p99 7.4 %, shear p99 24.7. Look: best upper half yet; shirt pokes through at shoulders / upper chest,
front edges curl in at the waist (rope fold), pocket flaps dented, hem narrow, body boxy. Nothing approved. $0.
NEXT: (1) shirt poke-through at the shoulders (the pressed shirt vs the jacket's shoulder: read where, the pad?);
(2) the waist rope fold: the styled break swings to 126 off CF (concept 64): pull the break less / hold it at the fit's
64 and open only below; (3) pocket flaps: face-nearest patch floor or hold the stitched flap; (4) the under (shirt)
floor blocks opening (C170): fit-side gap; (5) corner stand warp p99 28 %; (6) flip HPS_CORNER for jackets = coordinator.
## Method ($FR30 = /mnt/data/hifipushie/dress_garrett/fit_round30; env.sh, run.sh: this worktree)
Fit: job30.sh <tag> (fit30.py: on_form; WORN=1 keeps the spec's worn_open; G_JSON / EDIT_OPS / FASTEN env) -> res_ /
asm_<tag>.pkl. Style: sty.sh <src> <out> [FLOOR=1 FLOOR_UNDER=0 OPS=json] (style30.py: fronts pulled side + 0.25 out as one border until
threads / shear stop, hem points, smooth, relax). Reads: reads30.sh <asm>... (crumple, neck29, lapel29, sideline,
flaps25 + through-base, roll30, hem30 rows + threads / shear); misfit30.py <asm> (muslin read). Corner: WORN=1
G_JSON='{"hps": "corner"}' job30.sh w1h; legacyat.py reads it in the legacy hps frame. Render: post30.sh <tag>. Suite: suite.sh.
## Sheets ($FR30/check): {wholefront,upper_front,upper_three,side}_s5fc.png (corner) / _s4fc.png (legacy).
## Dead ends (one line each)
- Gravity substitutes; release sims (cloth.md r20-r29); lapel pins in a release (r29b); roll rows graded (C156).
- Closed (buttoned) fit as the base for the lapel: the roll can't open (C171).
