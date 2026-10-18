# Mouth / eye bias (2026-10-15, "mouth-eye-bias" agent, branch worktree-agent-a7da231d6ae3976e5)

The question: blind reviews of all four GNM-native heads (Tess tp_h3 / tp_k10, Garrett gp_h6c, two private heads) flag
the same faults in the same direction: the mouth reads WIDER with THINNER lips, the eyes SMALLER / NARROWER than the
photos. Is something systematic?

Scratch DURABLE in /mnt/data/hifipushie/mouthbias: env.sh, run.sh <script> (light slot), heavy.sh <script> (capped;
the script takes resources.heavy), out/, logs/. Scripts spikes/mouth_eye_bias. Per-person numbers of the private heads
live in workspace/private_notes/mouth_eye_bias.md only; here they are pooled.

## Read first (what earlier rounds found; not repeated)
- readmix "TALL LIPS" (docs/notes/readmix.md): at the TRUE head (HSRD scans) every lip read sees the photographed
  lips TALLER than the scan-fitted GNM border rows; LIP_PHOTO_BIAS (take that offset out of photo reads) is OFF
  (the scan surface did not confirm the gain). "The photo's colour border is not the lip's form: the vermilion edge
  goes to PAINT."
- gnm_atlas "Step 2: why the eye was narrow": GNM's canthal pocket painted as skin reads the inner corner ~1.6-2 mm
  short; fix = dressing (`skin.eyes.caruncle`, a number), not shape. It is OPT-IN (unset = the old faint spot).
- gnm_atlas "Readers, same on photo and dressed render": the photo's lower lip is LIGHTER than the skin under it
  (+3 L*), ours darker (-8.5) with a pale ring +5 L* under the lower border (skin:lip_border). Not acted on.
- eyes.md "Aperture vs paint": dressing changes the detector's eye opening (7.30 eyes-only -> 6.4 dressed, Garrett).

## Tools (spikes/mouth_eye_bias)
- meb.py <ref> <model..>: the same measures on photo / geom (the mesh at MediaPipe's learned GNM correspondence,
  mp_gnm.json, + its learned bias: where MediaPipe lands on OUR dressed renders of that surface) / clay (numba) at the
  front reference camera, on the photo's face axes, mm at the face. Measures: mouth width (61-291), upper (0-13) /
  lower (14-17) vermilion, bow depth, opening (159-145 / 386-374), fissure (33-133 / 263-362), inter- and outer
  canthal distance.
- mebr.py <ref> <model> [variant]: the dressed Blender stage (skin_read's stage: bare skin + eyes + lashes, no hair) at
  the same camera, flat (albedo) and lit (the photo's fitted light), MediaPipe on both. Variants: nolash, noskin,
  caruncle, nocanthus, norimlow ('+'-joined).
- mbord.py <ref> <model>: the vermilion COLOUR border (lipborder.read) on photo / renders vs the GNM border rows (what
  the lip paint is drawn through), as thickness above / below the seam along the mouth; and the tone step (L*, a*)
  lip minus the skin 1.5-2.5 mm outside the border.
- truthbias.py <truth models>: at the TRUE head (HSRD), MediaPipe on the photograph minus MediaPipe's correspondence
  on the true surface: how a real face of a shape reads against our drawing of the same shape.
- mcrop.py: photo | render crops (mouth, eyes) at the same framing.

## Round 1: where the bias enters (front reference camera of each head; mm, ours minus photo, MediaPipe on both)
Stages: geom = the mesh at MediaPipe's learned correspondence (the solve's own model of "our render"); lit = the dressed
Blender render under the photo's fitted light (skin_read stage). Tess = tp_h3, Garrett = gp_h6c; "private" = the two
private heads, pooled (their per-head rows: workspace/private_notes/mouth_eye_bias.md).

| measure | Tess geom / lit | Garrett geom / lit | private (2) geom / lit |
|---|---|---|---|
| mouth width | -1.5 / -1.7 | +1.6 / -1.6 | -0.5 / -0.6 |
| upper vermilion | -0.1 / -0.9 | +1.0 / +0.3 | +0.9 / +0.2 |
| lower vermilion | +1.8 / +0.1 | +1.2 / -0.5 | +1.3 / -0.2 |
| fissure R / L | -1.1 -1.7 / -1.6 -2.6 | +0.7 +0.1 / -0.3 -0.4 | -0.7 avg / -1.0 avg |
| opening R / L | -0.5 -0.7 / -0.7 -0.9 | +0.1 0.0 / +1.0 +0.3 | -0.7 avg / -0.6 avg |
| intercanthal | +2.5 / +3.1 | +0.2 / +1.2 | 0.0 / +0.2 |
| outer canthal | -0.3 / -1.1 | +1.0 / +0.5 | -1.4 / -1.7 |

- MOUTH WIDTH is NOT wider by the detector on any stage (lit: -1.7, -1.6, and the private pair mixed). The lip HEIGHTS
  by the detector are right within ~1 mm on the lit render (the solve made the geometry's lips TALLER than the photo by
  ~1 mm to get there: geom +1..+1.8 on the lower lip, everywhere). What reads "thin" is not the outline.
- THE LOWER LIP'S TONE is the one lip fault shared by all four (mbord.py; L* of the lower vermilion minus the skin
  1.5-2.5 mm under its border): photos (Tess / Garrett / private mean) +1.5 / +10 / 0.0 (the lower lip a lit pad over its own shadow),
  ours lit -10.6 / -1.8 / -6.5: 6-12 L darker than the photo on every head. Albedo alone (flat) -16 / -5.6 / -12.7.
  The colour border's PLACE matches (traced border thickness at the centre within -1.5..+1 mm of the photo's).
- EYES: the fissure is SHORT on all eight eyes in the lit render (-0.25 .. -2.6 mm, mean -1.1). Half of it is already
  in the solved shape (geom mean -0.6: the solve under-fits the corners), half is the drawing (lit - geom mean -0.5).
- Clay is useless as a stand-in for the look: the numba clay and an unpainted Blender stage read mouths 4-9 mm narrow
  and lips 2-5 mm thin (no colour edge for the detector): every check of lips / eyes must use the dressed render.

## At the TRUE head: our drawing of a shape vs a photograph of it (truthbias.py, 10 HSRD subjects, front)
MediaPipe on the photograph minus its correspondence on the scan-fitted surface (= where it lands on OUR dressed renders
of that surface): + = the photograph reads it bigger.

| measure | mean (sd) mm, n = 10 |
|---|---|
| mouth width | +0.36 (2.04) |
| upper vermilion | +1.61 (1.21): 10 / 10 positive |
| lower vermilion | +1.15 (1.28): 9 / 10 |
| fissure R / L | +1.19 (1.18) / +1.73 (0.98) |
| opening R / L | +0.55 (1.21) / +0.50 (1.02) |
| intercanthal | -1.42 (1.46) (the photo's inner corners further in) |
| outer canthal | +1.47 (2.35) (further out) |

THIS IS THE SYSTEMATIC BIAS: a real face of the same shape reads lips ~1.4 mm taller each and eyes ~1.5 mm longer (both
corners) and ~0.5 mm more open than our dressed render of it. Mouth width: no bias. The solve fits photos THROUGH the
correspondence (render domain), so it tries to make the geometry bigger than the truth to make up for the drawing; the
GNM prior resists, so the eyes stay ~1 mm short on the final heads. The lips are pinned by the colour-border reads
instead (readmix: those make the form TALLER than the truth), so their outline matches but their tone does not.
Source: the DRAWING (how lips and eye corners are painted / lit / lashed), not the readers and not GNM's mean.

## Round 2: which part of the drawing (mebr.py variants; Tess tp_h3 unless named; lit, ours minus photo, mm)
| variant | open R / L | fissure R / L | intercanthal | outer canthal |
|---|---|---|---|---|
| as dressed | -0.7 / -0.9 | -1.6 / -2.6 | +3.1 | -1.1 |
| no lashes | -0.8 / -0.7 | -1.1 / -2.0 | +2.9 | -0.2 |
| eyes.occlusion 0 (the lids' shadow on the ball, skin:eye_shade) | -0.1 / -0.1 | -1.1 / -2.0 | +2.9 | -0.2 |
| waterline 0 | -0.7 / -0.8 | -1.6 / -2.5 | +3.0 | -1.0 |
| occlusion + waterline + tear 0 | +0.1 / +0.3 | -0.9 / -1.9 | +2.5 | -0.3 |
| that + no lashes | -0.2 / +0.1 | -0.5 / -1.2 | +2.5 | +0.8 |
| eyes.caruncle 1 (Tess; Garrett the same) | -0.7 / -1.0 | -1.6 / -2.5 | +3.2 | -0.9 |
| eyes.canthus 0 | -0.6 / -0.9 | -1.7 / -2.6 | +3.4 | -0.9 |
| no skin at all (+ no lashes) | -2.4 / -2.4 | -2.4 / -3.1 | +4.0 | -1.4 |
| light: fill as world ambient (occluded) | -1.3 / -1.1 | -2.0 / -3.1 | +3.0 | -2.2 |
- The eye-OPENING deficit is skin:eye_shade (eyes.occlusion): +0.6..+0.8 mm back with it off; the fissure loses ~0.5 mm
  to it and ~0.5 mm to the lashes (one private head too: lashes off +0.4 / +0.6). caruncle / canthus / waterline: none.
- Tess's remaining inner-corner miss (+2.5) is her SOLVED SHAPE (geom +2.5): the solve's residual, not drawing.
- The ambient fill as an occluded world darkens the eye corners further (eyes smaller): the camera fill is not the fault.
- Lips: the pale rim under the lower lip (skin.lips.rim_lower 0, new key) changes nothing measurable (the skin 1.5-2.5 mm
  under the lip 74 -> 74 L*). The under-lip skin in the photos is 5-17 L darker than the skin over the upper lip (a
  shadow); ours 4 L (Tess 74 -> 57 photo, ours 78 -> 74). The occluded-ambient light: 74 -> 71 only.

## The current dressing on TRUE shapes (mebr.py on the HSRD truth heads rm_h23_T / h27 / h42 / h81: default skin, lashes,
## the photo's fitted light; ours minus the photograph, MediaPipe on both)
| measure | mean (sd) mm, n = 4 |
|---|---|
| mouth width | -1.17 (1.66) |
| upper vermilion | -2.47 (1.67): 4 / 4 thinner |
| lower vermilion | -2.62 (1.44): 4 / 4 |
| opening R / L | +0.24 (1.01) / -0.24 (0.53) |
| fissure R / L | -1.66 (0.67) / -1.82 (0.77): 8 / 8 eyes shorter |
| intercanthal | -0.14 (1.57) |
| outer canthal | -3.62 (1.48): 4 / 4 (our outer corners read further in) |
Same direction as the reviewers on all four heads: drawn with today's skin a TRUE lip reads ~2.5 mm thinner and a true
eye ~1.7 mm shorter than its photograph. This is the gate a dressing change must pass (re-run it after any lips / eyes
/ lashes default change: `heavy.sh mebr.py rm_hXX_T rm_hXX_T [variant]`, ~5 min a head).

## Round 3: the fix (drawing defaults; the skin agent owns these layers: sent to the coordinator as a proposal)
- `skin_features.EYE_OCCLUSION` (skin.eyes.occlusion's default; kept 1.0 here, PROPOSED 0.5): the lids' shadow on the
  ball (skin:eye_shade: a multiply over the ball's whole upper part, 0.1-0.55 r above its centre, and a band all round
  the lids) is what makes the detector's lid margins come in. Tess at 0.5: opening -0.7 / -0.9 -> -0.4 / -0.4,
  outer canthal -1.1 -> -0.6; at 0: -0.1 / -0.1. A narrower upper band (only the ~2 mm under the lash line) would keep
  more of the "eyes sit in the head" look than halving: the skin agent's call.
- `skin.lips.under_shade` (NEW, `skin.UNDER_SHADE` default 0, PROPOSED 1): the lower lip's shade on the skin under it:
  the lower lip's outline with a wide soft edge (its outer half falls off over ~2.5 mm), off the red, confined to a wide
  ellipse under the lip's middle; multiply [0.56, 0.45, 0.42]. Tess: under-lip skin 74 -> 71 L* (photo 57), the
  detector's lower lip +0.1 -> +0.3. Two earlier shapes failed by eye: a spot line hugging the border read as LIP LINER;
  a band offset 3 mm read as a detached grey stripe. The outline-edge form reads as shade. Conservative: the photos ask
  for ~10 L more (us 2 is in range of the parameter).
- `skin.lips.rim_lower` (NEW, default 1 = as before): the pale rim's share under the lower lip; measured no effect on
  the under-lip tone (the rim is 0.22 opacity, < 1 L there): left at 1, kept as a control.
- NOT fixed here, for the owners:
  - LASHES at the corners take ~0.5 mm of the fissure (two heads): lashes.py (eyes) could thin / shorten the first and
    last ~15 % of the row (real rows are sparse and short at the inner corner).
  - LIP PAINT is a flat matte fill out to sharp corner points; photos show a lit lower pad with a sheen highlight, a
    darker wet seam and dark rounded commissures where the red fades before the corner. That flatness (no volume cue)
    is what reads "thin" and "wide" to a person even where the detector's heights and width match.
  - Tess's inner canthi: the SOLVED shape (geom +2.5 mm intercanthal): a block-in matter (her approved head is not
    reshaped here).

## Round 4: after (occlusion 0.5 + lips.under_shade 1 as spec overrides), lit, ours minus photo, mm
| head | fissure R / L before -> after | opening R / L before -> after | lower lip before -> after |
|---|---|---|---|
| Tess | -1.6 -2.6 -> -1.3 -2.3 | -0.7 -0.9 -> -0.4 -0.3 | +0.1 -> +0.3 |
| Garrett | -0.3 -0.4 -> +0.8 +0.6 | +1.0 +0.3 -> +1.7 +1.2 (overshoots: his lid pose was set with the shade on) | -0.5 -> -0.5 |
| private (2), mean | -1.0 -> -0.4 | -0.6 -> -0.3 | -0.2 -> +0.1 |
Fissure signed mean over 8 eyes -1.08 -> -0.49; opening not systematic (two heads already over-open). Truth heads
(h42, h81): +0.2..+0.5 mm only: the parametric levers are NOT the main source at the truth.
Blind review of the after crops (out/review_after/review.md): FAIL on all four, the same two complaints in pixels:
eyes ~25 % narrower than the photo's VISIBLE eye (dark-framed almond from canthus tip to the lash line's outer end)
with the inner corners too far apart, and lips flat matte lenses running to blunt corners (no central lower-lip
volume, no creased / pocketed commissures). The detector's corners (MediaPipe 33 / 133) sit 1-2 mm beyond where our
visible eye ends: what a person reads as the eye's width is the white + lash framing, and ours stops short.

## HANDOVER (context budget reached, 2026-10-15)
STATE: diagnosis done; two drawing parameters built with tests, defaults UNCHANGED (skin.UNDER_SHADE 0 -> proposed 1,
skin_features.EYE_OCCLUSION 1 -> proposed 0.5, skin.RIM_LOWER 1 control); notes above. Truth-after renders for h23 /
h27 were still running (out/mebr_rm_h2*_T_occ50_us100.json).
WHERE THE BIAS ENTERS (the answer): the DRAWING. Our dressed render of a TRUE shape reads lips ~2.5 mm thinner each and
eyes ~1.7 mm shorter (outer corners -3.6) than its photograph (4 HSRD truth heads, current skin), and MediaPipe's
correspondence (learned on our dressed renders) says the same on 10 (lips +1.4, fissures +1.5). The solve fits photos
through that render-domain correspondence and the colour-border reads, so it enlarges the geometry to compensate: the
lips' outline then matches (geom lips ~1 mm taller than the photo) and the eyes only partly (prior), leaving fissures
~1 mm short on all eight eyes. Not the readers (same detector both sides), not lens (fitted cameras), not GNM's mean.
NEXT (in order of payoff):
1. Lip paint beyond GNM's border rows: readmix's lip_photo_bias.json "lip" table says a real vermilion's colour edge lies
   2.4 mm above (upper centre) / 3.9 mm below (lower centre) GNM's border vertex rows, less toward the corners. Draw the
   vermilion outline offset outward by that table (skin.OUTLINES_DENSE points + offsets), AND turn LIP_PHOTO_BIAS on in
   the solve together, so a solved head's form stays true and its look keeps the photo's red. Changes approved heads'
   solves: a proposal for Joe.
2. The visible eye: lash-line framing that runs to (and past) the outer canthus, darker lower lash line, the inner
   corner's canthal tip (the pocket's dark point, not a rounded white end); lashes thinner at the very corners.
   Measure with a "visible eye extent" reader (white + lash framing along the fissure line), not MediaPipe corners.
3. Lip volume in paint and light: lower-lip pad highlight / sheen under the photo's light, darker wet seam, rounded
   pocketed commissures where the red fades before the corner; under_shade 1-2.
4. Relearn mp_gnm.json on the CURRENT dressing after any drawing change (the solve's model of "our render").
