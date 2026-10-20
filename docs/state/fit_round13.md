# STATE: fit_round13 (Garrett jacket: R25 hem corner, shoulders, torso width) -- 2026-10-20. NO SIMS.

DESIGN FACT (Joe 2026-10-20, settled, do not re-litigate): the concept jacket is NOT buttoned; it is WORN OPEN
(front_state open, buttons done 0). Recorded in workspace/checklists/garrett_jacket.json (front_state / buttons_done
"source", reference_facts) and fr13.spec (closures_source). Blind reviews carry "the reference jacket is worn open" in the
context; the wholefront reviewer STILL read it as fastened (dispute with Joe's fact, never "fix").

STATE: HANDOVER. Steps 1-4 done; candidate r13b (default code: cutaway on, shoulder line). Reviews FAIL x3.
NEXT: (1) WOVEN-SHEAR CELL ENERGY round (plan: docs/state/fit_round12.md NEXT ROUND). Then, from this round:
(a) the worn-open cfHem pin on a named corner-top point (C62: the cutaway moved it to the curve; waist 356 -> 335, hem
sweep 498 -> 443); (b) SHOULDER_SLOPE chord + the jacket's girth / pad allowance over the shirt, then make it default after
a Tess check (shared tape); (c) torso width split (sides 20-45 off the body vs ~60); lapel read; collar + shirt collar.

## Results (front view; concept | r13a old corner | r13b R25 cutaway | r13c + chord shoulder)
| item | concept | r13a | r13b | r13c |
| edge_below 450 / 550 / 650 | 71/66, 78/72, 94/85 | 71, 85, 91 | 66, 73, 77 | 66, 73, 78 |
| hem corner top / curve-back mm (hemours) | 704/670, 29/35 | 690, 48/36 | 690/680, 30/33 | 730, 39/44 |
| flat cutaway rows (start / angle / round) | - | FAIL | PASS (-14, 2.5, 100) | PASS |
| shoulder width 30 / 45 / 60 below HPS | 277/354/424 | 442/478/479 | 442/478/479 | 310/402/464 |
| shirt off body at the shoulder (x 160-220) | 0 | 13-23 | 10-21 | 3-5 |
| torso width 350 / 425 / 500 | 396/400/429 | 373/357/396 (r11d) | 364/336/359 | 392/337/375 |
| waist width / hem sweep | 401 / 478 | 356 / 498 | 335 / 443 | 336 / 447 |
| shirt outside the jacket (thru) | 0 | 310 | 293 | 503 |
| break / button1 / button2 | 386 / 399 / 518 | 357 / 394 / 498 | 360 / 397 / 502 | 359 / 395 / 499 |
Causes: shoulders = tape shoulderSlope line fit (10.9) vs FreeSewing's chord (22.5) [C61]; corner = R25 undrafted [C60];
torso = girth present (+280 over body), split wrong (sides), not fixed.

## Files
$FR13 = /mnt/data/hifipushie/dress_garrett/fit_round13/ (run.sh = this worktree; job.sh <tag> [pf / tailor.X overrides];
harness10.py (key: code incl. tailor, pattern_tailor, pattern_draft + tailor overrides); fr13.py (CUTAWAY=0 = old corner);
hemtrace.py, hemours.py, shoulderprof.py, shoulderrows.py, girthsplit.py, draftfront.py, flatedge.py; renders.sh,
review13.sh; asm_r13{a,b,c}.pkl; check/ (r13b views + crops, r13c shoulder / hemcorner crops); review_*.log).
