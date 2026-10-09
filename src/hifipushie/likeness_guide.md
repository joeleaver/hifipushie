# Likeness: a checklist of what to look at, measured the same way on the reference and the model

Judging a face "by eye" finds one thing at a time (the face's width at the nose, then the eye's slant, then the
nose). Professionals who compare faces don't look at a face; they go through a LIST, in an order, feature by
feature, and write down what each one is. This guide is that list for our models, and the tools that read it:

- `likeness(name)`: every item measured on the reference pictures and on the model through each picture's fitted
  camera, ranked by miss, with FOCUS PANELS (photo | model, same crop and camera, the feature's points drawn) for the
  top misses and for the items that can only be judged by eye. Measures only.
- `likeness(name, targets=True)`: the target sheet (the references measured once: value, view, tolerance, confidence
  or "unmeasurable") and the stage plan.
- `fit_likeness(name, stage)`: one stage of the fit, big to small, each through an existing guarded control.
- `likeness_points(name, image, points, lines)`: hand-placed points and traced lines on a reference, for what no
  detector finds (the jaw's corner, the ear lobe, the neck's line).
- `reference_brief(kind, subject)` / `check_references(images, name)`: the shots to ask for, and what a given set of
  pictures can and can't support.

The checklist itself is data: `src/hifipushie/likeness.json` (items, stages; add items there).

## Where the list comes from

**Forensic facial comparison (FISWG / ASTM E3149).** The Facial Identification Scientific Working Group's "Facial
Image Comparison Feature List for Morphological Analysis", standardised as ASTM E3149-18, is the list examiners use:
a set of facial COMPONENTS (skin; face / head outline; face / head composition, i.e. proportions; hair; forehead;
eyebrows; eyes; cheeks; nose; ears; mouth; chin / jawline; neck; facial hair; facial lines; scars; facial marks;
alterations), each with characteristics (e.g. the nose: bridge, tip, wings, nostrils, columella) and descriptors
(shape, size, position, symmetry). Examiners go through every component and note similar / dissimilar, as far as the
image quality allows: a component that can't be seen is recorded as not assessable, not guessed. We take three things
from it: the components (our items cover all of them; skin, hair, lines and marks are paint or groom, so they are
judge-by-eye items here), the habit of going through ALL of them on purpose, and "not assessable" as an answer.
(AAFS factsheet for ASTM E3149-18: https://www.aafs.org/sites/default/files/media/documents/ASTM%20E3149-18%20Facial%20ID.pdf;
ASTM: https://store.astm.org/e3149-18.html.)

**Portrait and caricature artists: the order.** Artists block a likeness big to small: the head's overall shape
and proportions first (the face's thirds, where the eyes and mouth sit, the outline), then the features, then
details; Loomis's head construction (Drawing the Head and Hands, 1956) is the classic version. Caricaturists make the
same list explicit: identity lives in how a face DEPARTS from the average (Brennan's computational caricature, 1985:
exaggerate the differences from a mean face and recognition improves), so the features worth checking first are the
ones that carry those departures: face shape and widths, eye spacing and shape, the brow-to-eye distance, the nose,
the mouth's width and corners, the jaw and chin. Perception research agrees on the brows (Sadr, Jarudi & Sinha 2003,
"The role of eyebrows in face recognition", Perception 32: removing the brows hurt recognition MORE than removing
the eyes) and on configuration (the spacing between features matters as much as the features: Sinha et al. 2006,
"Face recognition by humans: 19 results", Proc. IEEE 94). Our stages follow this order: proportions, widths, eyes,
brows, nose, mouth, chin and jaw, ears.

**Anthropometry: the measures.** Farkas (Anthropometry of the Head and Face, 1994) defines the landmarks and the
standard measures behind every clinical face measurement: nasion (n), subnasale (sn), menton (gn), zygion (zy),
gonion (go), endocanthion / exocanthion (en / ex), alare (al), cheilion (ch), labrale superius / inferius, stomion,
pronasale (prn), columella. Our items are those measures (face height n-gn, bizygomatic zy-zy, bigonial go-go,
intercanthal en-en, palpebral fissure en-ex and height, alar width al-al, mouth width ch-ch, philtrum sn-ls,
vermilion heights, chin height li-gn, nasolabial angle at sn) plus the clinical angles (canthal tilt; the
nasolabial angle, ~90-95 degrees in men and 95-105 in women in the rhinoplasty literature) and the classical
proportion checks (lower third ~ middle third; alar width ~ intercanthal; mouth ~ 1.5 x alar).

## How each item is read

Every item is a 2D quantity in the reference picture, in mm at the face's depth through that picture's fitted
camera (human_refs.json), on the face's own axes (x across, y down the line nasion -> chin), so a tilted head reads
the same. Both sides use the same reader: MediaPipe's Face Landmarker (478 points, Apache-2.0, in its own venv,
$HIFIPUSHIE_MEDIAPIPE) on the photo, and on a clay render of the model through the same camera (eyeballs with iris
discs; brows drawn as strokes through the model's brow landmarks, because brows are paint). A detector's own
definition errors (where it puts a jaw contour on a soft jaw, iris centres vs eyeball centres) then fall the same way
on both sides. The model's own landmarks (GNM's 68) give a second reading: the table's "lm miss"; a '!' where the two
readings disagree by more than the tolerance means the miss depends on the definition: look at the panel.

Four kinds of item go beyond points:

- **Shape items** (the planes at temple / cheekbone / jaw, the cheek hollow, the nasolabial fold, the under-eye
  hollow, the brow ridge). Distances between landmarks can't see them, and a checklist without them rewards soft
  heads. They are read two ways. On the MODEL in 3D (`likeness_shape.measures3d`, mm: hull deficits of horizontal and
  vertical sections, the corner radius of the front-to-side turn, the brow in front of the cornea): these compare one
  model with another. Against the PHOTO by its shading: one light (ambient + a direction) is fitted to the photo's face
  skin on the model's own normals, the model is rendered lit that way, and the item is the photo's luminance minus
  that prediction in a region, against a reference region beside it, in % of the face's median. Negative = the photo
  is darker there than the model's shape explains (a deeper hollow, a sharper turn away from the light). It is
  confounded by albedo (stubble, brows, make-up) and assumes one light, so: tolerance 8%, scored on FRONT photos only
  (a turned or painted view shows the number in its panel, unscored), and the panel puts the model LIT LIKE THE PHOTO
  beside the photo. Trust the direction and the ranking between models, not the percent.
- **The jaw's L** (ramus angle from vertical, gonial angle, the lower border's straightness, the angle's height
  against the ear lobe and the mouth line, the neck's step in under the border). No detector finds a gonion, so these
  need a TRACE on the reference: `likeness_points(name, image, points, lines)` (stored in
  `<model>/likeness_points.json`; pixels of the full picture; `.R` / `.L` = the subject's right / left; `lines["jaw.R"]`
  runs from under the ear lobe DOWN the ramus, round the angle and FORWARD along the lower border to the chin;
  `lines["neck.R"]` is the neck's contour under it; `points["ear_lobe.R"]`). The model's side is its own contour found
  along the trace in its render: the depth edge where the jaw occludes the neck, else where its surface turns fastest.
  A model whose jaw is one soft diagonal from ear to chin reads a gonial angle near 160 and a leaning ramus.
- **Profile items without a profile** (nose projection, nasolabial angle, bridge profile, lips against the nose-chin
  line, chin projection): read from a three-quarter view when no profile exists, marked INFERRED ('~' in the table),
  tolerance x1.5. Never blank while a three-quarter picture exists; columella show, forehead slope and ears stay
  judge items.
- **Judge items** (hairline, lid fold, brow thickness, chin shape, neck, lines and marks, ears): no number; a focus
  panel with the model lit like the photo.

Turned views' cameras are REFITTED per model on the detector's points (the photo's 478 against the model's surface
under the same points of its render, unprojected through the render's depth; pose and focal, two rounds). The
table's `cam` column is the residual at each item's points in mm (it includes real shape misses) and widens that
item's tolerance by half of it: a painting's camera is loose, and its items shouldn't outrank a photo's.

The report leads with COVERAGE: how many items these pictures measure, infer, leave to the eye or can't support and
why, what a true profile would add, and each picture's problems (lens from the fitted focal, expression from the
detector's blendshapes, how hard the light is and how badly one light explains it, ears / forehead hidden).

What this still can't do: ears and the hairline have no points at all; resolution (a full-figure concept is ~1.3 mm
a pixel at the face: items whose tolerance is about a pixel are "low" confidence); the clay render is not the painted
model (lid margins read from shading, the iris disc's size is a guess); a generated or painted reference may squint
or frown (the coverage line says so) and its picture may not be one consistent face.

## The checklist (likeness.json), in the order to check it

1. **Proportions** (FISWG: face / head composition): face height (nasion to chin), face index (height / cheekbone
   width), middle third, lower third and their ratio, the mouth line's height in the lower face, forehead height
   and slope (judge).
2. **Widths and outline** (face / head outline, jawline): widths at the temples, cheekbones, nose base, mouth and jaw
   angles, chin width, the taper jaw / cheekbones.
3. **Structure** (planes, hollows, the jaw): temple / cheekbone / jaw planes, cheek hollow, nasolabial fold,
   under-eye hollow, brow ridge (shading + 3D); ramus angle, gonial angle, lower border, the angle against the ear
   lobe and the mouth, the neck's step (traced).
4. **Eyes**: eye spacing (iris to iris), inner corners apart, eye width, CANTHAL TILT, opening height, shape (height /
   width), the upper lid fold / hooding (judge).
5. **Brows**: height over the eye, arch, slant (head to tail), thickness (judge: paint).
6. **Nose**: length, alar width, alar / intercanthal, nostril base width (flare), the tip's height over subnasale,
   projection, nasolabial angle and bridge profile (profile; inferred from three-quarter), columella show (judge).
7. **Mouth**: width, mouth / nose, philtrum, upper and lower vermilion and their ratio, Cupid's bow, corner tilt,
   lips against the nose-chin line (profile; inferred).
8. **Chin and jaw**: chin height, chin projection (profile; inferred), the detector's jaw angle height (weak: prefer
   the traced items), chin shape, neck, lines and folds (judge).
9. **Ears**: height and length, protrusion (judge: no control yet).

## Staged fitting from the sheet

The same list drives the first fit, not only the check. `likeness(name, targets=True)` measures the references once
(the target sheet) and prints the plan; `fit_likeness(name, stage)` runs ONE stage:

| stage | controls (wired) | items they move | gaps (no control) |
|---|---|---|---|
| proportions | humanfit.solve | face height, middle third | lower third, mouth line, face index (ratios) |
| widths | fit_outline (front outline) | every width | - |
| structure | levers: shape.hollow, shape.planes, shape.jaw_angle, shape.under_eye, features.brow_ridge | cheek hollow, temple / cheekbone / jaw planes, under-eye (fill only), brow ridge, gonial angle and the angle's height | nasolabial fold, ramus angle, lower border, neck step |
| eyes | humanfit.solve + fit_hood + a nudge of the outer corners | spacing, intercanthal, eye width, lid opening, canthal tilt | eye shape (follows from width and hood) |
| brows | humanfit.solve | brow height | arch, slant |
| nose | humanfit.solve + nudges of the tip | alar width, length to the tip, projection | nasolabial angle, bridge profile, nostril base (base.head.regions by hand) |
| mouth | humanfit.solve + lever pose.smile | mouth width, philtrum, lip heights, corner tilt | lip ratio, lip projection |
| chin_jaw | humanfit.solve | chin height | chin projection, chin shape, neck |
| ears | none | - | everything |

A LEVER is a 1-D fit: the control is stepped once, the item re-measured (a full render + detection), a secant step
taken, and the best of the tries kept. Each stage is integrity-guarded (humanfit refuses a result that breaks the
mesh) and PINNED to the earlier stages' checklist items, re-measured: a step that makes one of them worse (by more
than half its tolerance, and past it) is not taken; a solve is first retried at half its asks. The reply lists the
stage's items before -> after, each lever's tries, the gaps, and anything earlier that still got worse: approve the
stage on its panels before the next (big to small, approved stages).

What the staged fit is and isn't: it gets a seed head's measured items inside tolerance in a couple of minutes a
stage, and with the structure stage it no longer leaves a soft head (hollow, planes and jaw corner are set from the
photo's shading). It does not make a likeness by itself: the shading levers are coarse (one light, albedo in the
way), the jaw's L and the fold have no control that draws them, and a face is more than its list. Use it for the
first pass, then judge the panels and the whole head.

## Stage 0: the character read

Before any millimetre, say who this is: "a lean, weathered man, long face on a square jaw, strong broad chin,
straight nose, heavy brow". A person knows a three-quarter view is wrong because it doesn't fit that macro; the
checklist's rows can all pass while the read fails. So:

1. `character_read(name)` gives the form: gestalt descriptors by group (build, face shape, jaw, chin, nose, brow,
   eyes, cheeks, overall), as portrait artists' head types, casting vocabulary and forensic class descriptors use
   them. Fill it LOOKING at the references (confidence clear / likely / hint, which picture shows it) and store it:
   `character_read(name, "reference", read=...)`.
2. Each descriptor is bound to bands on checklist items in every view, seen or not ("square jaw" = gonial angle
   <= 122, ramus <= 12 deg from vertical, jaw / cheekbone width >= 0.86, a neck step, a jaw corner in the shading).
   The stored read is a PRIOR: an item no picture measures takes the band; a measured reference value outside its
   own read is flagged (suspect that picture's camera or expression); the model outside the band is flagged. The
   bands are first values, not yet calibrated on real heads.
3. The round trip is the intuition check: `character_read(name, render=True)` draws the model from each reference
   camera and from views no reference shows (both profiles, the other three-quarter, low angle). A reader that has
   NOT seen the references (a fresh agent given only the form and the sheet) fills one form per panel; store each
   (`character_read(name, "<tag>", read, view)`), then `character_read(name, "<tag>")` is the diff: kept /
   CONTRADICTS (an opposite read instead) / missing / adds per view, and the controls the read needs that we lack.
   `likeness(name)` leads with it.

The USER's read wins: `character_read(name, "reference", read, author="user")` for their own words ("chunky, square
jaw, cleft chin, cute nose"). The LLM reader's descriptors stay unless one is the opposite of the user's; every
disagreement comes back as a QUESTION to put to the user (which should the model show? which picture shows it?),
never settled silently.

The six-view sheet is stage 0 AND the final check: `likeness(name)` renders it by default and leads with the diff.

**The projection test** (`project_reference(name)`): the reference picture projected onto the fitted head through its
camera as an unlit texture, seen from the six views. A smooth clay bust beside a photo of a skinned 50-year-old with
hair is not a fair comparison (on Garrett the clay read "young, round, soft" while the same head wearing the photo
read as the man); this one is. Where the picture smears or lands on the wrong part when the head turns (ears on the
cheeks = the face too narrow, as pass 6; the nose's side; the jaw's edge), the geometry is wrong there. Run it before
spending blind readers or skin renders.
A view that can't show a descriptor (a face shape in a profile, chin projection from the front) is left out of that
view's count. Repeatability (`likeness_read.agreement`): on one head three blind readers agreed on gaunt, heavy brow,
deep-set, hooded, straight nose, lean and square jaw; they did NOT agree on strong chin, narrow jaw or broad nose, so
weigh those by the profile panels and the contour items, not by one reader's word.

Limits: the renders are bald clay with drawn brows (no stubble or hair stand-in yet: a bald clay head reads heavier
and older); keep the summary sentence and read the sheet by eye too.

## A profile from a turned view (contours)

A three-quarter picture holds a profile at a known angle: the FAR side of the face against the background (forehead,
brow ridge, the far orbit and cheek, the mouth's line, the chin's corner, the under-jaw) and the nose's own edge
against the far cheek (bridge, tip, columella). Artists trace exactly these two lines. So when there is no true
profile, trace them:

    likeness_points(name, image, lines={"profile": [[u, v], ...], "nose": [[u, v], ...]})

"profile" runs from the forehead down round the chin (a dozen points by eye are enough: it is snapped to the
picture's edge against the background when read); "nose" from between the brows down the bridge, round the tip, back
to the columella's base (by hand: +-1 px). The model's own contours are found through the same camera (its render's
silhouette; the extreme of its nose's vertices), both are read in one frame (inner eye corners -> the mouth's
corners), and the contour items compare them: forehead slope, brow ridge over the orbit, the cheek's line at the
mouth's height, chin projection (the contour's chin corner against the brow's peak), chin depth below the mouth,
mentolabial fold, upper / lower lip out of the mouth's notch, nose tip projection, the tip's gap to the far cheek's
line, nose length, the bridge's bow. They replace the "inferred ~" detector readings of the same things on that
picture. Units are mm IN THE PICTURE (a turned view foreshortens depth), read alike on both sides.

What to know before believing them:
- 1 degree of camera yaw moves the nose's gap to the cheek line by ~1 mm. A generated painting need not be one
  projection: Garrett's desk painting reads 31 degrees by the detector's head pose, 45 by the fitted camera, and its
  nose is drawn as if turned further still. The far eye corner's gap to the contour is the cross-check (it agreed
  with the fitted camera there).
- The lips are named only where a notch between them breaks the contour; at 45 degrees the far cheek usually hides
  them ("the lips don't break this contour"), and the mouth's line is then the cheek's.
- The chin "corner" is the point standing furthest out of the chord from the mouth's height to the under-jaw: it
  exists on any chin, but on a round one it slides.

The fit (`fit_likeness(name, "profile")`, also run inside the nose and chin_jaw stages when the lines exist): the
contour's miss at the model vertices that make its contour becomes targets for `humanfit.fit_region` (GNM identity
components inside the nose region / the chin + lower lip region, every other landmark held, integrity-guarded), with
the part's landmarks held where the FRONT picture has them (a turned view says how far forward things stand; heights
and widths are the front view's), one camera through all rounds, up to five rounds judged on the contour's own rms.

## References: what we're handed, and what to ask for

Two modes (Joe: "We don't have any way of predicting what kind of reference photos we'll get, unless hifipushie is
the one responsible for generating them. But when we are, we can try to get the best ones we can.").

**Handed references.** Everything above is built to degrade honestly: each item says what it was measured from, with
a confidence, "inferred" from a weaker view, hand-placed points where the detector fails, and the coverage line.
`check_references(images, name=None)` judges a set before any fitting: views present (the detector's head pose),
lens (the fitted camera's focal when the model has one: under ~60 mm equivalent swells the nose), expression (smile,
open mouth, squint, raised or furrowed brows from the detector's blendshapes), the light's evenness, ears and
forehead covered (a colour heuristic: treat as a hint), and identity consistency between views (vertical proportions
that don't change with the head's turn should agree within 8%). It ends with the brief's shots to ask for.

**References we generate or ask for.** `reference_brief(kind="head" | "figure", subject)` is the shot list derived
from the checklist, with what makes each shot usable and prompt wording per shot (one shared identity block, so a
generator keeps the person):

- front, true left profile, three-quarter (45 deg); the front and three-quarter again under ONE side light (the
  planes: the shape items read shading); optional back and top; for a figure, full-body A-pose front and side;
- a long lens (85-135 mm equivalent) at eye height; neutral expression, mouth closed, eyes open to the horizon;
- soft even frontal light for the measuring shots; a plain background;
- hair off the ears and the hairline; the neck and jaw uncovered; nothing over the features;
- the same identity, light, scale and camera height in every view.

The brief's shape ({subject, common: {prompt, negative}, shots: [{id, view, light, purpose, must_show, prompt}],
text}) is shared with the clothing checklist's (`cloth_reference.reference_brief`), so one generator step can serve
both.

