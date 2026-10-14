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

ORDER: the artist block-in (guide(topic="block_in"): base of the right kind, whole-face steps judged by eye and by a
target table drawn from this checklist) comes FIRST and gets the masses, planes and proportions right; the staged
fitting below is for features after it.
Sub-topics (guide(topic=...)): `likeness_reading` (where the list comes from: FISWG, artists, anthropometry; how
each item is read, shape items, the jaw's L, profile items, judge items, coverage), `likeness_profile` (a profile
from a turned view: contour traces), `likeness_references` (handed references vs references we ask for),
`likeness_tools` (every likeness tool's parameters; guide(topic="tool:likeness") is the `likeness` tool's section).

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
hair is not a fair comparison (a clay head can read "young, round, soft" while the same head wearing the photo
reads as the person); this one is. Where the picture smears or lands on the wrong part when the head turns (ears on the
cheeks = the face too narrow, as pass 6; the nose's side; the jaw's edge), the geometry is wrong there. Run it before
spending blind readers or skin renders.
A view that can't show a descriptor (a face shape in a profile, chin projection from the front) is left out of that
view's count. Repeatability (`likeness_read.agreement`): on one head three blind readers agreed on gaunt, heavy brow,
deep-set, hooded, straight nose, lean and square jaw; they did NOT agree on strong chin, narrow jaw or broad nose, so
weigh those by the profile panels and the contour items, not by one reader's word.

Limits: the renders are bald clay with drawn brows (no stubble or hair stand-in yet: a bald clay head reads heavier
and older); keep the summary sentence and read the sheet by eye too.

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

## Self-review loop (every stage)

1. The six-view sheet and the focus panels: the reference beside the model through the SAME camera and crop, per
   item; the projection test where clay vs photo is unfair.
2. Go through EVERY item of the list in order (not the one that caught your eye); per item: similar / dissimilar /
   not assessable, with the measured miss. Mark each miss MAJOR (it changes who the face is: proportions, widths,
   structure, the character read) or MINOR. Big to small: proportions before features before details.
3. Fix the worst MAJOR with one stage or step (the block-in's moves for masses); re-measure; keep it only if no earlier
   item got worse.
4. Repeat until no MAJOR; then the character read round trip (fresh readers on the renders) as the final check.
Every row can pass while the read fails: the character read and the whole head decide.
