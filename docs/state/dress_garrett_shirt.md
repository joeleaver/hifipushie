# STATE: dress_garrett_shirt (Garrett's shirt on its own, then under the round-26 jacket) -- 2026-10-20, shirt round 7

QUESTION (Joe 2026-10-20): "will all the lessons we learned on the jacket carry over and it won't take 30 rounds?"
Round 1: process carried, geometry didn't. Round 2: lessons made general (C103-C108). Round 3: base fit STUCK (C110).
Round 4: neck split (C113, opt-in), first-button rule (C114, off in v6). Round 5: CULL FIRST (C115), refused at preflight.
Round 6: NECKLINE FLAT CHECK (C116): the neckline is long, not short; the strain is the yoke over the shoulder.
Round 7: SHOULDER FLAT CHECK (C117): the slope DEFINITION (C61). Shirt kind now drafted on the chord.
Jacket thread: docs/state/dress_garrett_fit.md (read-only here).
STATE (round 7, numbers in cloth.md "shirt round 7"): Simon got the tape's LINE slope 10.92 deg (FreeSewing reads the
chord hps -> shoulder point: 22.51). Line draft: seam 161.6 mm / drop 30.6 vs body 169.6 / 64.5 -> pulled +7 % on the
form, yoke columns +3-9 %, back top +4-5 %. Over-the-shoulder flat length is LONG on both drafts (+17-60 mm over the
body's arc, back and front sides): yoke depth / front drop NOT short; seam 15-17 mm forward of the crest (fine for a yoke).
Chord: seam 171.7 / 65.7, columns +2-3 %. Start over-limit: whole 6.50 -> 5.87 % (kind rule, k7a); seen part 5.76 ->
5.03 % (c7a). Still over the 3 % preflight: NO arrangement, no renders, no review this round.
Left over (chord form): back band 400-500 mm below hps 33-44 % (sig p90 1.23, the tuck line, mostly below the seen cut
z 1.116); yoke neck corner (hps pin 2 cm up the neck, 33 % on the last segment at |x| 65) + lower outer (|x| ~138);
front.L just under the neck (|x| 11-24); in the seen job the yoke reads 435 over (form 303): the arrange pins / seen cut add.
Jacket (kind keeps the line; only the shirt under it changed): jfit7.sh j7line vs j7chord -> see "Jacket" below.
NEXT: (1) locate the seen job's extra yoke strain (seen 435 vs form 303: arrange pins or the cut?) and the yoke neck
corner (hps pin height: the tape's hps is 2 cm up the neck); (2) the back's tuck band only matters if it is in the
seen part; (3) under 3 % -> arrange the collar (seen7.py, FORM=form_k7a.pkl), render, blind review; (4) refit the
jacket over THIS shirt before any dressed render. The new draft needs a pattern_check PASS before any sim (C2).

## Big reads (concept | r3 f3a | r4 r4b | r5 d5 (v6 fit, unarranged) | r7 (chord, unarranged))
- V bottom below HPS: 60 | 74 | 62.4 PASS | not re-read | not re-read.
- Collar points apart: 147 | 57 | 45 | ~45 FAIL (not arranged); below HPS 50-61 | 84.5 | 82 | ~82 | not arranged.
- First fastened button: 83 | 123 | 64 | v6 rule off (~123) FAIL | unchanged.
- Start over-limit (preflight 3 %): - | 8.1 % | 7.2 % | seen 5.85 / 5.76 % | seen 5.03 %, whole 5.87 % FAIL.
- Shoulder seam flat (r7, gate row shoulder_seam_flat): line 161.6 / 30.6 FAIL -> chord 171.7 / 65.7 PASS (body 169.6 / 64.5).
- Over-the-shoulder flat vs body arc (r7, |x| 65 / 90 / 125): chord +99 / +89 / +70 mm: PASS (both sides).
- Neckline flat (r6): 444.2 vs bare neck 406.5 + 10-15 (book) / base ring 430.8 + ease: LONG, PASS.
- Cuff past jacket sleeve (17-23): r5 13.1 p50 FAIL. Collar above jacket collar (11-23): CB 7.3, side 8.1 FAIL.

## Jacket (r26g rows, shirt under on line vs chord; the jacket's own slope unchanged)
- pending: shirt_round7/jrows_j7line.log vs jrows_j7chord.log.

## Spec sh_garrett v6 (spacing off). Code: cloth.slope_measures + garment_kb kinds.shirt.shoulder_slope "chord";
cloth_check.shoulder_seam_row. Tests: see the last commit (21 clothing files).

## Commands ($S = /mnt/data/hifipushie/dress_garrett/shirt_round7; run.sh runs THIS worktree's code)
RUNNER=bin/capped ./run.sh fit7.py <tag> (SLOPE=line|chord tape override; the kind rule applies anyway) -> form_<tag>.pkl;
./run.sh over7.py | col7.py | dir7.py | back7.py <form pkl> (flat over the shoulder / columns / over faces / by height);
VERSION=6 SLOPE=.. FORM=<pkl> RUNNER=bin/capped ./run.sh seen7.py <tag> [submit] (round 5's seen5: seen part + collar
pins + preflight); ./run.sh probe_pre7.py <tag>; SHIRT_SLOPE=line|chord ./jfit7.sh <tag> (jacket r26g + rows).
Round 5 dress / render: shirt_round5/dress5.py, render_d5.py.
