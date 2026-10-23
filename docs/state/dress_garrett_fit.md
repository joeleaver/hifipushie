# STATE: dress_garrett_fit (Garrett jacket over the muslin shirt: muslin form fit + styling, NO sim) -- 2026-10-23, round 32

DESIGN FACTS (Joe, settled): the jacket is worn OPEN, unbuttoned; it falls straight down (no waist suppression, side
line plumb). Put "the reference jacket is worn open, unbuttoned" in every review's context. Renders show the OPEN jacket
only. Covered show-through is not a fault (C153); Joe 2026-10-23: the shirt patches at the shoulders are culled later,
don't chase them. PROCESS: muslin fit (worn open: the spec's worn_open, C171), styling by the kind's wear as data
(C174: ends smooth + pull down), remeasurement; no sim; judged beside the concept only (C165). Shirt = gc_garrett's
shirt as worn, not tuned here. Jacket hps = "corner" (store v2).
STATE: round 32 done. PATTERN: lapel widened by its point + belly (C175, R29): gc_garrett store v3 lapel gorge_drop
0.135, belly 0.01 @ 0.4; gate PASS_WAIVED 5701667c (waive32.json adds collar_stand_end: R28 opt-in, pre-existing).
Look a1s = that pattern's worn-open fit styled by the kb recipe (unchanged).
READS a1s | concept (k2 r31): lapel 150 133/130 | 127/134 (118/116); V 200 221 | 237 (190); point 151 @ 92 | 148 @ 93
(147 @ 73); roll 150/250 75/57 | 69/64; edge 450/550/650 45-59/71-80/95-97 | 71/78/94; side line L 33 R 58 | <=20;
hem 422 | 482 (451); length 738 | 748; crumple p95 12.5 | smooth (9.9/11.1); threads p99 8.3 %; flaps sunk 0/0.
LOOK: upper half the closest yet (broad lapels, notch at the concept's height); lower half WORSE than k2 (L edge zigzag
at the waist, R hem corner flared + dented, hem narrow, waist pinched 376 vs 414). Nothing approved. $0.
Suite: see the last commit (17 files, capped -rs).
NEXT: (1) the lower fronts: the kb styling recipe lands differently on the new front (a1 unstyled hem 398 = w1h's 400;
styled 422 vs k2 451): read the zigzag (which grip makes it: style one op at a time on asm_a1.pkl, reads per op) and
fix the recipe as DATA (garment_kb kinds.jacket.wear.open.style), both sides; smooth_border on front.X:break..cfHem is a
dead lever here (0 rounds: find why its stop fires at once); (2) edge 450 45-59 vs 71; (3) waist pinch 376 vs 414 + hem
422 vs 482 (the fit wraps the side panels in at the waist: a fit read, not styling); (4) V 221 vs 237 (belly 14 fails
waist_suppression: the row reads lapel width at the chest line; a larger belly needs that read to skip the lapel).
## Method ($FR32 = /mnt/data/hifipushie/dress_garrett/fit_round32; run.sh: this worktree)
Flat lapel: flat32.py '<lapel json>'... Gate + fit: [WAIVE32=1] gj.sh <tag> '<lapel json>' (gate32.py = pattern_gate +
its own on_form -> asm_<tag>.pkl, then stylekb.py -> asm_<tag>s.pkl, reads30.sh -> r_<tag>s.log). Styling variants:
stj.sh <src> <out> ops_<x>.json (stylekb with g["style"] = the list; ops_kb.json = the kb recipe). Render: post30.sh <tag>.
Store edit: setlapel.py. Suite: suite.sh.
## Sheets ($FR32/check): {wholefront,upper_front,upper_three,side}_a1sc.png (concept | clay | diag).
## Dead ends (one line each)
- Gravity substitutes; release sims (cloth.md r20-r29); lapel pins in a release (r29b); roll rows graded (C156).
- Closed (buttoned) fit as the base for the lapel: the roll can't open (C171).
- Opening pulls with no down (side + out): a free front swings up and open (r31 t3b / t5a).
- UNDER_FLOOR on by default (r31 f1): roll off the concept, sew gap 4.6 mm (C172).
- Widening the lapel by swinging the break out (r30): the rope fold; widen in the pattern (C175).
- belly 14 @ 0.35 (r32 a2): +5 mm V, gate waist_suppression FAIL. Grip at break..cfHem@0.15 (r32 e1): edge over-opens below.
