# STATE: dress_garrett_fit (Garrett jacket over the muslin shirt: muslin form fit + styling, NO sim) -- 2026-10-23, round 33

DESIGN FACTS (Joe, settled): the jacket is worn OPEN, unbuttoned; it falls straight down (no waist suppression, side
line plumb). Put "the reference jacket is worn open, unbuttoned" in every review's context. Renders show the OPEN jacket
only. Covered show-through is not a fault (C153); the shirt patches at the shoulders are culled later, don't chase them.
PROCESS: muslin fit (worn open, C171), styling by the kind's wear as data (C174 / C178), remeasurement; no sim; judged
beside the concept only (C165). Shirt = gc_garrett's shirt as worn, not tuned here. Jacket hps = "corner".
STATE: round 33 done. Suite (17 files, capped -rs): pytest exit 0, 289 passed, 4 xfailed, 0 skipped ($FR33/suite.log). gc_garrett store v4: the jacket's dead sim-era keys dropped (under pin, sculpt /
under_sculpt / finish); gate PASS_WAIVED pattern 5701667c body e31aac35 (= r32), gate_status now matches it (C176:
fit_garment works again on the layered jacket). Styling recipe (garment_kb jacket.wear.open) REPLACED (C178): swing the
lower front about break -> side hem, lay it back down + in, smooth, edge into one long curve (C177), hem down, relax.
READS k33 (= t12) | r32 a1s | concept: lapel 150 133/130 | same | 127/134; V 200 221 | 221 | 237; roll 150/250 75/57 |
same | 69/64 (upper half unchanged); edge 450/550/650 45-39/51-53/68 | 45-59/71-80/95-97 | 71/78/94; edge wiggle 3.6/2.1
| 6.8/6.9 mm; corner flare 3.0/3.7 | 10/18; crumple low 11/11 | 13/12; hem 415 | 422 | 482; waist 375 | 377 | 414;
side line L 39 R 53 (hem-row spikes) | 33/58 | <=20; length 753 | 738 | 748; threads p99 7.6 % | 8.3.
LOOK (mine, check/*_t12sc.png): lower fronts now clean straight edges, symmetric, plumb in the side view; no zigzag,
no flare. Still: fronts open less than the concept (68 vs 94 at 650), body tapers in from the chest (pattern, below).
FAULT 3 (fit read, fitread33.py / girth33.py): the muslin's threads at waist and hem are at the pattern's own lengths
(weft p50 -0.4..+0.2 %, shear p95 <= 3.8 deg): not squeezed. The PATTERN tapers: torso girth chest 1167, waist 1094,
seat 1057, hem 1021 mm (body seat 935): the hem hugs the seat (61 mm ease, back tilts in 16 deg). Needs: waist girth
>= chest (~1170-1210: suppression 7.75 % -> ~0; the gate allows <= 8 %), hem ~1230 (+210 mm, side + back seams flared
straight down from the underarm). The narrow hem also caps how far the fronts can open (both swing and grips stop on stretch).
NEXT: (1) the PATTERN: no waist suppression + hem flare per the
numbers above, gate, refit, restyle with the kb (re-read edge 450, still 39-45 vs 71: no styling lever, C178 notes); (2) V 221 vs 237; (3) the kb recipe needs cutawayTop (square fronts: none).
## Method ($FR33 = /mnt/data/hifipushie/dress_garrett/fit_round33; run.sh: this worktree)
Op by op: runops.sh <tag> (op33.py on $FR32/asm_a1.pkl with ops_<tag>.json; no json = the kb) -> op_<tag>.log,
asm_<tag>_<k>.pkl; sumops.py <tag>; fwd33.py (side-view hang); reads30.sh; post30.sh <tag> (sheets). Gate: hk1.py.
## Dead ends (one line each)
- Gravity substitutes; release sims (cloth.md r20-r29); lapel pins in a release (r29b); roll rows graded (C156).
- Closed (buttoned) fit as the base for the lapel (C171). UNDER_FLOOR on by default (C172). Break swung out (r30).
- Opening pulls with no down: a free front swings up and open (r31). belly 14 @ 0.35 fails waist_suppression (r32).
- Point grips down the edge (@0.33 zigzag, @0.6 flare: C178). Swing hinged on the side seam (9 deg). Swing alone
  (forward pot belly, t5). Hem-point pull after the swing (150 mm drag, t7). Lay-back after the finish (grip held).
