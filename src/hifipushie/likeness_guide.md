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

What this can't do, and says so:
- Profile items (columella show, the true nasolabial angle and projection, ear position) need a profile picture; from
  a three-quarter view a few are read foreshortened (the same camera on both sides, so they still compare).
- Ears, the hairline, brow thickness, lines and marks, chin shape, neck: no detector points; they are JUDGE items,
  shown in focus panels, not measured.
- Resolution: a full-figure concept is ~1.3 mm a pixel at the face; items whose tolerance is about a pixel are marked
  "low" confidence in the target sheet.
- The clay render is not the painted model: lid margins on clay read from shading; the iris disc's size is a guess.

## The checklist (likeness.json), in the order to check it

1. **Proportions** (FISWG: face / head composition): face height (nasion to chin), face index (height / cheekbone
   width), middle third (nasion to subnasale), lower third (subnasale to chin) and their ratio, the mouth line's
   height in the lower face, forehead height (judge: hair).
2. **Widths and outline** (face / head outline, jawline): widths at the temples, cheekbones, nose base, mouth and jaw
   angles, chin width, the taper jaw / cheekbones.
3. **Eyes**: eye spacing (iris to iris), inner corners apart, eye width, CANTHAL TILT, opening height, shape (height /
   width), the upper lid fold / hooding (judge).
4. **Brows**: height over the eye, arch, slant (head to tail), thickness (judge: paint).
5. **Nose**: length, alar width, alar / intercanthal, nostril base width (flare), the tip's height over subnasale,
   projection and nasolabial angle (three-quarter, profile), bridge profile (hump / scoop), columella show (profile).
6. **Mouth**: width, mouth / nose, philtrum, upper and lower vermilion and their ratio, Cupid's bow, corner tilt.
7. **Chin and jaw**: chin height, jaw angle height, chin shape (judge), neck under the jaw (judge), lines and folds
   (judge: shape.hollow, skin).
8. **Ears**: height and length, protrusion (judge: no control yet).

## Staged fitting from the sheet

The same list drives the first fit, not only the check. `fit_likeness(name, stage)` runs ONE stage:

| stage | control (wired) | items it moves | gaps (no solver measure: by hand) |
|---|---|---|---|
| proportions | humanfit.solve | face_height, middle third (nose_length) | lower third, mouth line, face index (ratios) |
| widths | fit_outline (front outline) | every width | the jaw angle's height (shape.jaw_angle) |
| eyes | humanfit.solve + fit_hood | spacing, intercanthal, eye width; lid opening (hood) | canthal tilt, eye shape |
| brows | humanfit.solve | brow height | arch, slant |
| nose | humanfit.solve | alar width | length to tip, projection, nasolabial angle, bridge (base.head.regions by hand) |
| mouth | humanfit.solve | mouth width, philtrum, lip heights (summed) | corner tilt, lip ratio |
| chin_jaw | humanfit.solve | chin height | jaw angle height, chin shape |
| ears | none | - | everything |

Each stage asks the solver only for its items' misses (front view, where a 2D miss in mm is the 3D measure's), with
the earlier stages' measures pinned; humanfit's integrity gate refuses a result that breaks the mesh. The reply
lists the stage's items before -> after, items no control reaches, and any EARLIER stage's item that got worse:
approve the stage on its panels before the next (big to small, approved stages).

Known limits of the staged fit (2026-10-08, first run on a fresh Garrett): pins are on the solver's landmark
measures, not on the checklist items, so a later stage can still move an earlier item (the brows stage moved the
middle third; the reply says so); the checklist measures distances and angles, not SHAPE (cheek planes, hollows,
folds), so a face can meet every number and still read soft: judge the panels and the whole head.
