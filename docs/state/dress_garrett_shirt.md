# STATE: dress_garrett_shirt (Garrett's shirt on its own, then under the round-26 jacket) -- 2026-10-21, shirt round 12

LANDED FROM THE SHIRT SPIKE (2026-10-21, docs/state/collar_spike.md, ledger C137-C140; BUILD_VERSION 17: cached builds
redo). Shared defaults changed under this thread: Simon's band sewn EDGE TO EDGE onto the placket tops + its drafted ends
kept (cloth_designs simon band_ends false); the KB no_tie open-neck rolls REMOVED (they turned the neckline the band is
sewn to: band ends tipped ~45 deg, collar fronts ran in over them); collar + stand meshed at 2 mm on the form (a 5 mm mesh
turned the 3 mm roll as two kinks + a shelf); pattern_form._turn_flaps no longer flips a fall inside its stand on a
near-tie. sh_garrett still declares its own "open neck.R" fold (R only: mirror C138) + worn_open: re-check both before
the next Garrett round; the open state that works is staged flat-pattern ARAP from the closed fit (spikes/shirt_spike).
QUESTION (Joe 2026-10-20): "will all the lessons we learned on the jacket carry over and it won't take 30 rounds?"
Rounds 1-7: process carried, geometry didn't (C103-C117). Round 8: gate PASS, first button + V pass; spread stuck (C120).
Rounds 9-11: fold reads (C121), fall sprung (C122), corners measured (C123), flap lies on what is under it (C124),
landing line (C125), held seam ends parted (C126), sawtooth = show-through (C127). Jacket thread:
docs/state/dress_garrett_fit.md (read-only here). Notes: cloth.md "shirt round 12".
ROUND 12 (cut short by the coordinator: a general "drape band" pattern op, Joe-approved, comes next and replaces the flat
collar draft and much of the arrangement; jacket refit skipped, no new levers on the fall's turn or the sawtooth):
- C129 proportions: the coordinator's flat option (stand 0.07 = 28.5 mm) FAILED checklist:collar_band [30, 38] (Joe's
  concept_v8 pass). Stored the nearest in band, same fall: collarStandWidth 0.075 (30.5 mm), collarWidth 1.68,
  collarBend 0.015 -> fall 52.3 flat at CB, points 66.6, spring 73.6, cover 7.8. Gate g12b PASS (spec v10, source names
  both). Coordinator: confirm 0.075 or waive the band.
- C128 seam: part_stitches dropped every stitch between two "held" ends, and made (solved) pieces counted as held. Now only
  PRESCRIBED ends (carryIdx) drop a stitch. KAT test_arranged_made_pieces_keep_their_seam: control 33.0 mm open, fixed sim
  gap 1.73 / welded 0.27. Garrett a12a: collar | stand sim gap max 1.27 mm (contact gap; r11 14.5 mm opened). PASS.
- k12a closed form: collar turn 164.5, corners 11.2 % (one corner), V 67.1, first button 79.2.
- a12a arranged (same pins as a11a, SEPARATE=0, start_over 0.06, start over 5.18 %): spread 130.1 / points 64.3 / V 74.0
  / button 77.6 / state spread: PASS. Turn 154 (r11 143; >= 165 not met), fold_on_base 21 % FAIL, twist 18.2 FAIL,
  corners 15.1 % FAIL (stand ends 12.9-15.1), weld max 3.6 (yoke|back, sleeve|yoke contact; no collar seam opening).
- Fall un-turning (step 2), MEASURED ONLY from a12a's report: pins 0/2 = collar points (7-vertex 12 mm patches on the
  fall's outer edge), held 27.5 / 47.1 mm off the start, pin 2 springback 4.2-5.4; pins 1/3 = cfNeck by 20 mm. The point
  pins drag the fall's outer edge sideways and lift it; nothing holds the turn (made rest only). Not fixed.
- Render a12a + blind collar review: FAIL (collar stands up round the neck, points knotted, V closed to under the chin,
  no buttons, colour). Own read: the stand is lower and the seam closed, but it still reads as a wing collar stood up
  round the neck, the fall not lying on the shoulders; ends lumpy. Not near the concept. Wholefront review not run.

## Big reads (concept | r11 a11a arranged | r12 a12a arranged)
- V bottom below HPS: 60 (45-75) | 74.3 | 74.0 PASS
- Collar points apart: 147 +-20 | 138.2 | 130.1 PASS
- Collar points below HPS 50-61 (gate band): | 56.7 | 64.3 PASS (row)
- First fastened button: 83 | 77.1 | 77.6 PASS
- Collar turn (section): 180 +- 35, want >= 165 | 143 | 154 (closed k12a 164.5)
- Collar | stand seam gap (sim): <= contact | 14.5 open | 1.27 PASS
- Stand at CB (flat): 30-38 | 36.6 | 30.5 PASS
- Corners strain max: <= 10 % | 13.5 | 15.1 FAIL
- fold_on_base (arranged): <= 5 % | 6.6 | 21 FAIL
- Reviews: PASS | collar FAIL, wholefront FAIL | collar FAIL (wholefront not run)

## Tests: round 12: the 22 named files under bin/capped: 327 passed, 3 skipped, 4 xfailed, exit 0 ($S/tests_r12.log).

HANDED OVER (2026-10-21): the collar (stand + fall: proportions, turn, lie, spread) now belongs to the DRAPE BAND
thread: docs/state/drape_band.md. sh_garrett v11 carries a drape entry (round 1, not passing: stand flares, gate row
drape_band_flat FAIL); revert to v10 for anything that needs Simon's collar.
NEXT (shirt, non-collar): (a) [done: handed to] the drape band op (worn cross-section swept along the neck, flattened): it should own the
stand height, the fall's turn and its lie; (b) if arrangement survives it: pins on the stand ends / fronts' neckline, the
fall carried by FLAP_LAY rather than pinned on its points (a12a: point pins held 27-47 mm off the start); (c) corners
(stand ends 13-15 % arranged); (d) sawtooth resolution A/B (yoke 10 mm vs fall 5 mm), untouched; (e) jacket refit.

## Commands ($S = /mnt/data/hifipushie/dress_garrett/shirt_round12; run.sh runs THIS worktree's code; RUNNER=bin/capped
for heavy). apply12.py SW CW CB [source] (stores the collar options); flat12.py opt.X=v; gate12.py <tag>; fit12.py <tag>
(form); FORM=<pkl> SEPARATE=0 seen12.py <tag> submit (arrangement); reads12.py <tag>; seam12.py <tag> [Vsim|V]
(collar|stand seam gap); FORM=<pkl> render12.py <seen> <tag>; rev12.sh <view> <tag> (blind review).
