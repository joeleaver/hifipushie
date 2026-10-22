# Measurements: every measurement a draft consumes, its consumer's definition, ours (measure audit 2026-10-20)

STATE (2026-10-20): measure_defs.py hands each consumer its own definition, through the adapters chord /
iliac_crest / under_arm. Every garment drafted today (Garrett shirt + jacket, Tess coat + sweater) HOLDS its mismatches
on the legacy values (garment_kb kinds.<kind>.definition_holds), so no current draft moved. New kinds (tee, hoodie,
blouse, dress...) get the consumer definitions at their first draft. Gate row `measure_definitions`: FAIL if a consumer
has nothing declared, INFO "HELD" for holds, PASS otherwise.
NEXT (coordinator): lift holds one at a time, one refit per lift (back-to-known-good): see "What lifting a hold moves".
Then decide on the waist (ambiguous; strict xfail test_freesewing_waist_is_the_narrowest_section).

Code: `src/hifipushie/measure_defs.py` (CONSUMERS, ADAPTERS, holds, gate row), `tailor.py` (the tape),
`cloth.slope_measures` (the boundary: draft_measures and the worn path call it), `cloth_check.measure_definitions_row`.
Tests: `tests/test_measure_defs.py`: a synthetic mannequin with analytic answers, plus the check that every
`measurements.<x>` read in the FreeSewing sources (Simon, Jaeger, Carlton and what they extend) and every `m["x"]`
read in pattern_blocks' bodice / trouser has a declared definition. Audit scripts: /mnt/data/hifipushie/measure_audit/.

Sources. FS = FreeSewing 4.10.2: the docs pages freesewing.org/docs/measurements/<name> (markdown on codeberg,
markdown/org/docs/measurements/<name>/en.md) and the design source in our pack (brian/src/base.mjs etc.). ANSUR II =
the public 2012 data (/mnt/data/hifipushie/headbody/ansur). Ours = tailor.py docstring + code. "own" = only our own
rules consume it, so the tape's definition is the rule's.
Consumers: S Simon (Garrett's shirt), J Jaeger, C Carlton (tables in cloth_designs.json; all extend Brian); B the
bodice / knit block (pattern_blocks.bodice: Garrett's jacket, Tess's coat and sweater; Brian's rules); R the jacket
rules (pattern_jacket.rules); SL the sleeve block; T the trouser / skirt blocks (Garrett's trousers, Tess's jeans).

## The table (G = Garrett dg_garrett, T = Tess dt_tess; mm, slope in degrees; ours -> theirs where they differ)

| measurement | consumers: their definition (source) | ours | verdict | G | T |
|---|---|---|---|---|---|
| shoulderSlope | S J C B: the angle at the HPS of the beam to the shoulder point at x = shoulderToShoulder / 2 (FS docs: degrees, points not named; brian base.mjs points.shoulder; our bodice sy = (sx - nw) tan) = the hps -> shoulder point CHORD | line fit over the top of the shoulder (SHOULDER_SLOPE "line"); chord in at | MISMATCH -> adapter chord (C61, C117) | 10.92 -> 22.51 | 12.63 -> 21.98 |
| hips | S J C B R: round the body at the top of the hip bones, the iliac crest (FS docs hips); not the seat | hip joint + 2 cm (the trochanter's level). The docstring said FS's hips were "where trousers sit": wrong | MISMATCH -> adapter iliac_crest (tape highHip: crotch + 0.125 x stature, ANSUR II iliocristale) | 942.8 -> 805.0 | 912.6 -> 757.1 |
| waistToHips | S J C B R: waist down to the top of the hip bone, at the side (FS docs) | waist -> hip joint + 2 cm | MISMATCH -> adapter iliac_crest (tape waistToHighHip) | 151.7 -> 23.4 | 151.3 -> 44.8 |
| hips, waistToHips | T: only as a pair, to interpolate a dropped waist (pattern_blocks.dropped_waist) | as above | match (any level, same for both) | 942.8 / 151.7 | 912.6 / 151.3 |
| highBust | B: bust dart = (chest - highBust) / 2 when > 8 mm; S J C: only with draftForHighBust (off). FS: round the chest just under the arms, above the bust; may tilt | was = chest (a placeholder: no bust dart was ever drafted) | MISMATCH -> adapter under_arm (tape highBustUnder: the narrowest torso section in the 4 cm under the armpit) | 967.9 -> 951.7 | 854.7 -> 847.9 |
| hpsToWaistBack | S J C: HPS straight down the back to the waist (FS docs) | taut tape over the back from the hps | adapter (existing, cloth.length_level): re-based on the nape, napeToWaistBack + 0.05 neck, so the hps landmark doesn't move the hem | 515.0 -> 509.5 | 452.5 -> 462.6 |
| neck | S J C B: round the neck where a shirt collar sits (FS docs; height not pinned) | square to the neck, 2 cm above the neck joint | ambiguous (same intent). Over another garment: round its collar (over_measures; jacket 406.5 -> 453) | 406.5 | 339.8 |
| shoulderToShoulder | S J C B: shoulder tip to shoulder tip across the back (FS docs) | taut tape across the back between the shoulder points | match; but Brian (and our bodice) then use HALF of it as a horizontal half width: the pattern's shoulder point sits wider than the body's | 481.6 (straight 434.0: +23.8 / side) | 376.0 (352.8: +11.6 / side) |
| waist | S J C B R T: round the narrowest part, below the ribs, horizontal (FS docs) | skeletal: 70 % pelvis -> chest joint (a belly doesn't move it) | AMBIGUOUS, not adapted (strict xfail): moving it moves every hps -> waist length | 788.8 (narrowest 783.8, 15 mm up) | 686.6 (649.6, 50 mm up) |
| chest | S J C B R: round the fullest part, horizontal (FS docs) | fullest torso section 2-12 cm under the armpit | match | 967.9 | 854.7 |
| hpsToBust | S J C B: HPS straight down to the bust line (FS docs: surface or vertical not stated) | taut tape from the hps to a point 95 mm out on the chest section (not the apex) | ambiguous (B's bust apex x is 0.47 x chest quarter: bustSpan is never measured) | 249.0 | 239.7 |
| waistToArmpit | S J C B R: waist up the side to the armpit (FS docs) | vertical, waist -> the highest torso section clear of the arms | match. Over a garment: lowered by its thickness in the pit (over_measures) | 246.0 | 219.5 |
| biceps | S J C SL: fullest part of the upper arm (FS docs) | fullest section square to the arm, 25-75 % shoulder -> elbow | match | 316.8 | 288.7 |
| wrist | S J C: where the arm joins the hand (FS docs) | square to the forearm, 1 cm above the wrist joint | match | 143.7 | 123.6 |
| shoulderToWrist | S J C SL: shoulder tip down the slightly bent arm to the wrist, over it (FS docs) | shoulder point -> elbow -> wrist joint centres | ambiguous (centres, not surface) | 553.8 | 477.2 |
| shoulderToElbow | SL (FS docs: shoulder tip down the arm to the elbow) | shoulder point -> elbow joint | ambiguous | 290.4 | 263.8 |
| seat | C T B (hem): fullest part of the seat, horizontal (FS docs) | fullest section 12 cm under the hips line up to it | match | 960.0 | 967.0 |
| waistToSeat | C T: vertical, waist to the seat line (FS docs) | vertical | match | 206.7 | 231.3 |
| waistToFloor | C T: vertical (FS docs) | vertical | match | 1115.1 | 1019.8 |
| waistToKnee | T: vertical, waist to the knee (FS docs) | vertical, to the knee joint | match | 578.0 | 554.9 |
| waistToUpperLeg | T: body rise (Aldrich crotch depth). FS: waist to the upperLeg line (no FS consumer here) | vertical waist -> crotch | match for its only consumer; the name is FS's, the meaning Aldrich's | 244.7 | 249.3 |
| knee | T: round the knee, horizontal (FS docs) | at the knee joint | match | 353.1 | 340.6 |
| heel | T: round heel and instep, foot pointed (FS docs) | a 45 deg plane through the ankle, the foot as modelled | ambiguous (foot not pointed) | 340.3 | 252.6 |
| calf, ankle | T (own) | fullest / slimmest between knee and ankle | match (own) | 382.1 / 226.5 | 345.6 / 176.4 |
| napeToWaistBack | B (length), length_level (own) | the neck loop's CB down the back, taut | match (own) | 489.2 | 445.6 |
| hpsToArmpitBack | B underarm (own) | the hps back tape stopped at the armpit's level | match (own) | 258.0 | 228.9 |
| hpsToSeatFront / Back | B front_balance (own) | hps tapes 60 mm off centre to the seat | match (own) | 678.4 / 710.7 | 660.4 / 677.1 |
| plumbGirth | R (C94, own) | hull of the torso sections seat .. chest | match (own) | 995.3 | 1017.0 |
| neckHeight | collar rule (own) | run of neck sections within 8 % of the narrowest | match (own) | 35.0 | 50.0 |
| chestDepth / waistDepth | large_abdomen (own; ANSUR II chest / waist depth) | y extent of the sections | match | 233.3 / 201.3 | 205.7 / 158.4 |
| neckBase, napeBaseToWaistBack, neckBaseFrontDrop | B neckline "ring" (own, opt-in HP_HPS=base) | ANSUR II 5.2.29 base-of-neck ring | match (own; not on by default) | - | - |
| hps (landmark) | S J C B: "where your neck meets your shoulder" (FS docs, every hps* tape) | the neck loop 2 cm up the neck, widest point ("widest"); opt-in "corner": the shoulder's crest just outside the neck, never above the loop, the hps tapes rebased by its drop (tailor._neck_corner, C156) | MISMATCH, PARKED: adapter neck_corner, every garment holds it unless garment key hps "corner" (garrett collar r3: ridge fixed, front pillow + fall buckle left) | corner 23 mm lower, 24 back | wf_simon 5 mm lower |
| bustSpan | B (optional) | never measured (FS: straight horizontal apex to apex) | ambiguous: falls back to 0.47 x chest quarter | - | - |

Summary: 38 consumed measurements: 25 match (14 of them our own rules' definitions), 8 ambiguous, 5 mismatched
(shoulderSlope, hips, waistToHips, highBust newly adapted; hpsToWaistBack already adapted). The landmarks under them
(the hps / neck split, C113; the shoulder point) are definitions too: the hps is the neck loop's widest point
(HP_HPS "widest", C-history in tailor.measure), FS's "where the neck meets the shoulder, mid shoulder top".

## What lifting a hold moves (no garment refitted in this audit)
- Garrett shirt (Simon; holds hips, waistToHips, highBust): hips 942.8 -> 805.0 narrows the hem (hipsEase on it),
  waistToHips 151.7 -> 23.4 shortens Brian's cbHips by 128 mm: Simon's length (cbHips x (1 + lengthBonus)) drops
  ~128 x (1 + bonus) mm. The shirt's lengthBonus / tuck were tuned on the wrong hips: refit = re-tune the length to the
  reference, not keep the bonus. highBust inert. Shoulder already on the chord (shirt round 7).
- Garrett jacket (bodice + rules; holds shoulderSlope, hips, waistToHips, highBust): chord 10.92 -> 22.51 moves the
  shoulder point down ~23 mm (C61: the shirt poked through on the chord in fit round 13; pad_measures then flattens it);
  hips -> the hem quarter and hips_ease rows; length "hips" = waist + waistToHips: 128 mm shorter before length_bonus
  (0.12); highBust: an 8.1 mm bust dart appears (a man's pecs read 16 mm over the under-arm section: the 8 mm
  threshold is a women's-block rule; check it before lifting). Jacket r26 rows (sideline widths, plumb, hem 758) all move.
- Tess coat / sweater (bodice / knit; s18 freeze): chord 12.63 -> 21.98 (shoulder point ~20 mm lower; the sweater's
  "square wide shoulders" reviews s26-s27 are this direction), hips 912.6 -> 757.1 and waistToHips 44.8: the hem /
  hips quarters (the coat's length is absolute, 1.05 m: unchanged; the sweater's 0.522 m: unchanged), highBust 3.4 mm:
  no dart. Frozen pkls are unaffected; the next rebuild after a lift is a refit.
- Garrett trousers, Tess jeans (trouser block): nothing (pair rule).
- shoulderToShoulder used as a horizontal half width (not held: no adapter yet): every B / Brian draft puts its
  shoulder point 23.8 mm (Garrett) / 11.6 mm (Tess) per side wider than the body's. Garrett's jacket queue item
  "wide square shoulders" and Tess's sweater reviews (s26-s27 "square wide shoulders") point at it. The fix would be a
  draft-side rule (half the straight width), not a tape change: a coordinator call.
