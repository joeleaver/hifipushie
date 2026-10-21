# STATE: dress_garrett_shirt (Garrett's shirt on its own, then under the round-26 jacket) -- 2026-10-21, shirt round 11

QUESTION (Joe 2026-10-20): "will all the lessons we learned on the jacket carry over and it won't take 30 rounds?"
Rounds 1-7: process carried, geometry didn't (C103-C117). Round 8: gate PASS, first button + V pass; spread stuck (C120).
Round 9: fold reads (C121), fall sprung (C122), torn corners measured (C123). Round 10: a turned flap lies on what is
under it (C124). Jacket thread: docs/state/dress_garrett_fit.md (read-only here). Notes: cloth.md "shirt round 11".
ROUND 11:
- C125 landing path: the fall's landing line is the neckline at the CB cover all round (was tapered to the points'
  height): spring 127 -> 81 mm, gate g11a PASS. On the form the edge did NOT move (CB 10 / sides 22 mm below the seam,
  k10b = k11a): the cape is the fall's DEPTH. Worn fall 51.8 at CB (concept ~35-45), ends 85 from the roll (concept read
  45-49 projected). Forced by the 36.6 mm stand + cover rule. Flat option (NOT applied: changes the stand):
  collarStandWidth 0.07 / collarWidth 1.79 / collarBend 0.015 -> stand 28.5, fall ~44 worn, ends 66, cover 9.5.
- C127 sawtooth: the edge is smooth; the yoke / fronts show through the fall's 0-5 mm band (8.5 %, depth p50 0.75 mm),
  edge row bent (dihedral p90 8). FLAP_LAY_SMOOTH lever DEAD (opt-in, 0). Open: resolution (yoke 10 mm vs fall 5 mm).
- C126 ZOZO start scan: the 4 pairs were the collar | stand SEAM (held made pieces, stitches dropped, sides 0.3 um
  apart; float32 scan vs float64 build check). part_stitches clears held ends 0.1 mm apart. a11a RAN (local).
- a11a (patch pins, SEPARATE=0): spread / height / V / button all PASS; corners 13.5 % FAIL; collar roll turn 143 FAIL;
  the collar | stand seam opens to 14.5 mm (dropped held stitches: nothing sews it). Reviews: collar FAIL (stand to the
  jaw, fall standing as wings, overlapping layers), wholefront FAIL. Jacket refit not run.
NEXT: (a) decide the collar proportions (stand 36.6 -> ~28.5 with a shallower fall; coordinator / Joe: the stand was set
at 0.09 on purpose, see the spec's source); re-run k + a with it; (b) the held collar | stand seam must stay sewn in the
arrangement (stitch held ends, or weld made pieces) before the next sim; (c) fall turned only 143 arranged: the patch
pins pull it up; (d) sawtooth: resolution A/B; (e) jacket refit when the collar review is close.

## Big reads (concept | r10 k10b closed | r11 a11a arranged)
- V bottom below HPS: 60 (45-75) | 62.1 closed | 74.3 PASS
- Collar points apart: 147 +-20 | closed | 138.2 PASS
- Collar points below HPS 50-61: | 81.3 closed | 56.7 PASS
- First fastened button: 83 | 79.4 | 77.1 PASS
- Collar turn (section): 180 +- 35 | 164.7 | form 165.7, arranged 143 FAIL
- Fall spring (flat): a few cm | 127 mm | 81 mm (gate PASS)
- Fall worn depth at CB: ~35-45 | 51.8 | 51.8 (unchanged)
- Corners strain max: <= 10 % | 18.4 FAIL | 13.5 FAIL
- Edge band show-through (0-5 mm): 0 | 7.0 % | 8.5 %
- Reviews: PASS | collar FAIL, wholefront FAIL | collar FAIL, wholefront FAIL

## Tests: round 11: 28 cloth / pattern files under bin/capped: 331 passed, 7 skipped, 4 xfailed, exit 0 ($S/tests_r11.log).

## Commands ($S = /mnt/data/hifipushie/dress_garrett/shirt_round11; run.sh runs THIS worktree's code; RUNNER=bin/capped
for heavy). flat11.py [opt.X=v | key=json] (flat collar + spring reads); gate11.py <tag>; fit11.py <tag> (form);
edge11.py <pkl> <lab> (edge vs neck seam + corners); zig.py / thru11.py <pkl> (sawtooth reads); xscan.py <seen pkl>
[faces] (our start scan); FORM=<pkl> SEPARATE=0 seen11.py <tag> submit (arrangement); reads11.py <tag>; corners11.py
<tag>; FORM=<pkl> render11.py <seen> <tag>.
