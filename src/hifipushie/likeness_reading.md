# Likeness: where the list comes from, and how each item is read

Read guide(topic="likeness") first.

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
