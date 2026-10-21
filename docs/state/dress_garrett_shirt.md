# STATE: dress_garrett_shirt (Garrett's shirt on its own, then under the round-26 jacket) -- 2026-10-21, shirt round 10

QUESTION (Joe 2026-10-20): "will all the lessons we learned on the jacket carry over and it won't take 30 rounds?"
Rounds 1-7: process carried, geometry didn't (C103-C117). Round 8: gate PASS, first button + V pass; spread stuck (C120).
Round 9: fold reads fixed (C121); fall sprung to its landing path (C122); torn corners measured (C123).
Jacket thread: docs/state/dress_garrett_fit.md (read-only here). Notes: cloth.md "shirt round 10".
ROUND 10 STEP 1 DONE (C124): the form's turn. The relax drew a turned flap only onto its own base (the stand), so past
the neck seam the fall hung as the rigid turn left it (a tube). pattern_form.FLAP_LAY (default on): past its base a
flap turned onto the outside lies on the garment's other cloth under it (yoke, fronts, other flaps), one THICK out.
- Shoulder KAT (stand + sprung fall, neck + 22 deg cone): off = tube 12 mm inside the bodice, ripple 25 deg; on = turn
  171.5, edge gap <= 0.9 mm, ripple 2.2. test_pattern_form.py test_sprung_fall_lies_on_the_shoulders.
- Garrett closed (k9a -> k10a): edge gap under p50 / p90 6.7 / 14.0 -> 2.5 / 3.8 mm.
- Jacket A/B same code (r10j0 off -> r10j2 on): collar free edge gap p50 25.3 -> 9.8 mm, p90 29.5 -> 18.4; turn
  169.3 -> 170.6; twist 6.9 -> 15.2 (FAIL by 0.2: the jacket fall is unsprung); stretch max 255 -> 139; lapels same.
- Read fix: fold_on_base counts only flap vertices standing OVER the base (21 of 25 jacket 'through' were past the
  stand's edge). Jacket collar 4 / 7 both runs (0.1-0.5 mm).
STEPS 2-4: closed k10b fold rows all PASS, edge on the shoulders (2.5 / 3.8 mm). Gate g10a PASS. Arrangement with
PATCH pins (cloth_release "patch") NOT RUN: ZOZO refused the start, 4 collar / stand pairs "at the edge of crossing";
moving the collar 1.5 mm off the stand left the same faces failing (2 levers: stop-loss). Renders of the CLOSED form
(check/*_k10b.png); reviews collar FAIL (6 MAJOR: fall reads as a cape, closed, sawtooth edge, stand high, points),
wholefront FAIL (6 MAJOR). Jacket refit not run. Collar points 17-18 % strain on the closed form (sprung draft, k9a too).
NEXT: (a) find which array ZOZO's start scan reads ("previous positions": rest of made pieces?) and clear the 4 pairs;
(b) arrangement -> collar_corners; (c) the sprung fall's size on the form (cape read) and its sawtooth outer edge;
(d) renders + reviews; (e) jacket refit; jacket draft spring (twist 15.2) is the jacket thread's.

## Big reads (concept | r8 s8c arranged | r9 k9a closed | r10)
- V bottom below HPS: 60 | 74.1 PASS | closed | -
- Collar points apart: 147 | 87.5 FAIL | 33.0 closed | -
- Collar points below HPS 50-61: 82 | 65.8 | 81.3 closed | -
- First fastened button: 83 | 77.3 PASS | 79.4 | -
- Collar turn (section): 180 +- 35 | 162 PASS | 166.4 | k10a 164.7
- Fall edge gap under (form) p50 / p90: on the shoulders | - | 6.7 / 14.0 | k10a 2.5 / 3.8
- Collar corners strain max (C123): <= 10 % | 31.0 FAIL | 18.4 (points: the sprung draft) | k10b 18.4 FAIL
- Gate: PASS | g9b FAIL (fold_turn_allowance) | g10a PASS

## Tests: round 10: 22 files under bin/capped: 326 passed, 2 skipped, 4 xfailed, exit 0 ($S/tests_r10.log).

## Commands ($S = /mnt/data/hifipushie/dress_garrett/shirt_round10; run.sh runs THIS worktree's code; RUNNER=bin/capped for
heavy). kat.py [FLAG=v] (KAT), katrows.py / dbg.py (its rows / section); fit10.py <tag> (closed form -> form_<tag>.pkl);
edge10.py / jrows10.py <pkl> (funnel read + corners / fold rows + free edge); thru.py (fold_on_base split);
harness10.py <tag> outer ROLL_GAP=true 'pj.STAND_RUN_OFF={"on": true, "end": 0.003, "over": 0.03}' LAYER_ALLOW=0.008
BRIDGE=true [FLAP_LAY=false] (jacket over the shirt -> asm_<tag>.pkl); seen10.py <tag> submit (patch pins, SEPARATE) / reads10.py (mk10.py writes them); render10.py <seen|-> <tag> [views]
(mkr10.py); gate10.py <tag>; xpairs.py (ZOZO start pairs -> pieces).
