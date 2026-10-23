# STATE: dress_garrett_fit (Garrett jacket over the muslin shirt: muslin form fit + styling, NO sim) -- 2026-10-23, round 30

DESIGN FACTS (Joe, settled): the jacket is worn OPEN, unbuttoned; it falls straight down (no waist suppression, side
line plumb). Put "the reference jacket is worn open, unbuttoned" in every review's context. Renders show the OPEN jacket
only; the closed fit is an internal stage. Covered show-through is not a fault (C153); the cull hides only what no judged
view sees (C158). NEW PROCESS (Joe): muslin fit, styling, remeasurement; no release sim; judged beside the concept only
(C165: no r28 / r29 columns). Shirt = gc_garrett's shirt on the muslin fit, styled as worn (on_form), not tuned here.
STATE: round 30 in progress. Workspace spec now carries r29p2 (it was missing: applyspec.py). Closed fit c1 (on_form):
threads p99 9.8 %, shear p99 28.8; misfits at the neck (collar / stand warp -17 / -19 %, twisted), the fronts' neck /
shoulder corner (weft -8 %), the lap at 250-350 (button). ROLL: the top button holds it closed (C171); the worn-open fit
w1 (spec's worn_open break 64) has the concept's roll (70 / 58 / 63 vs 69 / 64 / 59). Layer floor added to garment_pull
(C170, KAT in test_garment_pull). Styling A/B (c1 / w1 x floor) and hps corner A/B running.
NEXT: styling results -> sheets -> reads table -> hps A/B -> suite.
## Method ($FR30 = /mnt/data/hifipushie/dress_garrett/fit_round30; env.sh, run.sh: this worktree)
Fit: job30.sh <tag> (fit30.py: on_form; WORN=1 keeps the spec's worn_open; G_JSON / EDIT_OPS / FASTEN env) -> res_ /
asm_<tag>.pkl. Style: sty.sh <src> <out> [FLOOR=1] (style30.py: fronts pulled side + 0.25 out as one border until
threads / shear stop, hem points, smooth, relax). Reads: reads30.sh <asm>... (crumple, neck29, lapel29, sideline,
flaps25 + through-base, roll30, hem30 rows + threads / shear); misfit30.py <asm> (muslin read).
## Dead ends (one line each)
- Gravity substitutes; release sims (cloth.md r20-r29); lapel pins in a release (r29b); roll rows graded (C156).
- Closed (buttoned) fit as the base for the lapel: the roll can't open (C171).
