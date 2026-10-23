# STATE: dress_garrett_fit (Garrett jacket over the muslin shirt: muslin form fit + styling, NO sim) -- 2026-10-23, round 31

DESIGN FACTS (Joe, settled): the jacket is worn OPEN, unbuttoned; it falls straight down (no waist suppression, side
line plumb). Put "the reference jacket is worn open, unbuttoned" in every review's context. Renders show the OPEN jacket
only. Covered show-through is not a fault (C153); Joe 2026-10-23: the shirt patches at the shoulders are culled later,
don't chase them. PROCESS: muslin fit (worn open: the spec's worn_open, C171), styling by the kind's wear as data,
remeasurement; no sim; judged beside the concept only (C165). Shirt = gc_garrett's shirt as worn, not tuned here.
Jacket hps = "corner" in gc_garrett (coordinator's call from round 30's A/B; store version 2).
STATE: round 32 IN PROGRESS: lapel widened in the PATTERN (gorge_drop 0.135 + belly R29): a1 V 221, lapel 150 133/130;
lower fronts styled worse (zigzag L edge, R hem corner). a2 (belly 14 @0.35) running. cloth.md "fit round 32".
Round 31 result: Suite (17 files, capped -rs): pytest exit 0, 286 passed, 4 xfailed, 0 skipped ($FR31/suite.log, 17 min). Look k2 = w1h fit (r30, corner, worn open) styled by garment_kb kinds.jacket.wear.open.style
(C174: front above the break held; edge grips @0.33 / @0.6 / hem drawn side + 0.5 down until a thread would stretch;
smooth; hem pulled down; relax) with body + flap floors (local reach, C173).
READS k2 | concept: lapel 150 118/116 | 127/134; V 200 190 | 237; edge 450/550/650 48-53/70-71/97-103 | 71/78/94;
roll 150/250 69/55 | 69/64; shirt collar shows 12/15/20 | 10-20; side line L 60 (one row at the flap) R 32 | <=20;
hem 451 | 482; length 739 | 748; crumple p95 9.9/11.1 | smooth; flaps sunk 1/0 of 25; threads p99 8.8 %, shear 29.8.
LOOK: rope fold mostly gone, flaps read as flaps; upper half WEAKER than r30 s5f (narrow lapels, V 190 vs 237: the held
fit's lapel; r30's break swing had widened it); hem corners flare out; body boxy. Nothing approved. $0.
Fault 1 finding (C172): the shirt floor "blocked" opening because the FIT is already inside the shirt (131 through,
442 shirt vertices out); pattern_form.UNDER_FLOOR (hard contact) fixes that but moved the roll / opened a sew gap: OPT-IN.
NEXT: (1) the lapel / V: lapel 150 118 vs 127-134, V 190 vs 237 with the break held: read the fit's lapel (the roll
row vs the lapel edge) and widen in the PATTERN (lapel width / notch), not by swinging the break; (2) the edge at 450
48-53 vs 71 (the panel just below the break still wraps in): a grip nearer the break or less down there; (3) hem
corners flaring out + side line (one-row spike at the flap, -350: check the read); (4) hem 451 vs 482; (5) the cull
(C158) could hide under-layer faces piercing out where the jacket covers (coordinator's optional ask; not done).
## Method ($FR31 = /mnt/data/hifipushie/dress_garrett/fit_round31; env.sh, run.sh: this worktree)
Fit: WORN=1 job30.sh <tag> (fit30.py, on_form) -> asm_<tag>.pkl. Style as data: capped stylekb.py asm_<src>.pkl <tag>
(garment_pull.worn_style with the spec's jacket); experiments: sty.sh <src> <out> (style31.py; HOLD_BREAK=1, RECIPE=edge,
EDGE_AT, EDGE_DIR, FINISH, FLOOR=1 FLOOR_UNDER=0). Reads: reads30.sh <asm> > r_<tag>.log; lump31.py (front panel lumps
below the break); flapdbg.py; underdbg.py / underfloor.py (jacket vs shirt). Render: post30.sh <tag>. Suite: suite.sh.
## Sheets ($FR31/check): {wholefront,upper_front,upper_three,side}_k2c.png (concept | clay | diag).
## Dead ends (one line each)
- Gravity substitutes; release sims (cloth.md r20-r29); lapel pins in a release (r29b); roll rows graded (C156).
- Closed (buttoned) fit as the base for the lapel: the roll can't open (C171).
- Opening pulls with no down (side + out): a free front swings up and open, nothing stops it (r31 t3b / t5a).
- UNDER_FLOOR on by default (r31 f1): roll off the concept, sew gap 4.6 mm (C172).
