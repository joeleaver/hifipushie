# Humans: tool reference

## Tool reference

The full documentation of this topic's tools: their MCP descriptions are the short form. guide(topic="<tool name>") returns one section. These tools are the `human` toolset: enable_toolset("human") turns it on.

### `human`

`human(name, age=30, sex=0.5, weight=0.5, muscle=None, height=None, seed=None, outfit=None, tone=None, skin=None, head=None, bust=None, firmness=None, note='', source='makehuman', style=None)`

A whole person from a description, saved as an ordinary model: "a 3-year-old girl" = human("mia", age=3,
sex="female"). The body has that age's MEASURED proportions and size by default (stature from WHO's growth
medians, the head-to-body proportion from children's anthropometry: 4.6 heads tall at 1 year, 5.4 at 3, 6.4 at 7,
7.1 at 11, 8 adult; a toddler has a belly and no neck to speak of, a child no waist), the head follows it, and the
figure is dressed. Then edit it like any model (edit_model, skin, look, look_skin, groom_hair, rig, export_asset).
age: years, 0..100 (under ~1 the shape stays a one-year-old's, scaled). sex: 0 / "female" .. 1 / "male" (under
~10 it changes little, as in life). weight, muscle: 0..1 (0.5 average). height: m, instead of the median.
seed: the face (another number, another person). outfit: "tee_shorts" (default from 2 years), "onesie" (default
under 2), "underwear", "none". tone: Fitzpatrick 1..6 or the skin tool's tone dict; skin: more skin keys, or
false for clay only. head: base.head keys to merge (e.g. {"features": {"cheeks": 0.5}}, {"pose": {"smile": 0.004}}).
bust, firmness: 0..1, a woman's chest (MakeHuman's cup size and firmness; base.body bust / firmness). By default
an adult woman stands ~3 cm ahead of the breast bone (an A/B cup; MakeHuman's own average is 1.8 cm), growing in
from 11 to 17 years, softer with age, lifted when dressed (as a bra holds it); children and men have none.
Clothes are cloth with their own volume (they hang from the chest and belly, bridge the bust, cover the navel);
a baby's onesie goes over a nappy. The face is the seed's: features, lids and mouth differ per person.
source: "makehuman" (default: a GNM head grafted onto the MakeHuman body at build time) or "human" = ONE MESH
(onemesh.py: GNM's head topology stitched once onto MakeHuman's body; the body's own head carries the face, so
there is no neck tube, cross-fade or head scale, and the skin weights are hand-made everywhere).
style (source "human" only): a style sheet name ("human_feature", "human_cartoon", "human_anime",
"human_lowpoly": ROUND 0 values, not yet fitted to references) or base.style keys, e.g. {"eyes": 1.3, "human":
{"head_size": 1.2, "nose": 0.4, "jaw": 0.2, "legs": 1.1, "limbs": 0.85}}: macro sliders that reshape the SAME mesh
(head_size, cranium, eye_spacing, eye_height, nose, nose_width, jaw, chin, cheeks, mouth, mouth_height,
exaggerate; legs, arms, torso, shoulders, hips, hands, feet, limbs, waist, chest), each clamped to a range tried
on renders. A style is an artistic decision: shape is only part of it (shading, line and paint are not here).
Returns the body measured against the references for its age and sex.

### `measure_human`

`measure_human(name, since=None, picture=True)`

A one-mesh human MEASURED: the named measures an edit can be stated in (body in cm: stature, heads tall,
breadths, girths, limb lengths; face in mm from its landmarks: interocular, face / jaw / chin width, eye width and
height, nose length / width / projection, philtrum, mouth width, lip and chin height...; ratios as "a/b"), the
integrity gates (folded faces, edge stretch at lids / lips / nose / ears / the neck bridge, lids over the eyeballs,
lips not crossed, plausibility in sigma) and a clay picture of the head. since = an earlier version number: what
changed since then, as the side-effects report every edit gives (all measures before -> after, UNINTENDED flags).
Work like this: measure -> change ONE thing with fit_human / nudge_human -> read the INTEGRITY and UNINTENDED lines
and look at the whole picture -> only then go on. A fit matches shape; much of a style is shading, line and paint.

### `fit_human`

`fit_human(name, set, free=None, release=None, force=False, save=True, note='', figure=True)`

Set MEASURES on a one-mesh human and let the solver find the sliders: set = {"nose_width": 34} (a value),
{"eye_width": "+2"} (a change), {"jaw_width": "x0.95"}, {"eye_width/face_width": 0.19} (a ratio); several at once
are solved together. free: ["identity"] (default: the face's GNM identity components), "body" (weight, muscle,
height) for body measures. It is a MINIMAL-CHANGE solve: every measure you did not name is held, landmarks far
from the ones involved are held in place, and the step stops where a measure that wasn't asked for would move
more than twice its tolerance or an identity component would leave the plausible range (2.6 sigma). So a request
the face can't meet comes back PARTLY met with the residual: it is not obeyed blindly. release = measures you
allow to move; force = widen the range and save even a broken mesh. The reply leads with INTEGRITY: ok / BROKEN,
lists what else moved (UNINTENDED), and shows before | after | where vertices moved. A broken result is not
saved. Requests like "eyes three times wider" are a STYLE (style sliders), not an identity: they come back held.
figure: the reply's picture also shows the whole DRESSED figure before | after (two builds, a minute or two);
false for a quick dry run.

### `nudge_human`

`nudge_human(name, landmark, move=None, to=None, radius=0.015, force=False, save=True, note='', figure=True)`

Direct manipulation: move ONE face landmark by `move` [x, y, z] in metres (x = its left, -y = forward, z = up)
or `to` a world point; every other landmark is held and a side landmark's mirror moves the mirrored way. The
identity sliders take what they can within the plausible range; the rest becomes a small smooth correction at
the landmark (a Gaussian push, radius m, kept through later changes) and is reported as "the sliders can't do
this": that names a slider the model lacks. Same reply as fit_human (INTEGRITY, UNINTENDED, the picture).
landmarks: chin, nose_tip, nose_base, nose_bridge, lip_upper, lip_lower, mouth_corner.L, jaw.L, jaw_back.L,
brow.L, brow_inner.L, eye_outer.L, eye_inner.L, lid_upper.L, lid_lower.L, ala.L, chin.L (and .R).

### `human_reference`

`human_reference(name, views, fit=True, free=None, force=False, save=True, note='', figure=True, read=None, method='map', measure=False)`

Match a one-mesh human's FACE to reference images by named points: views = [{"image": path (optional, kept for
the record), "size": [w, h] (pixels), "yaw": 0 front / 45 three-quarter from its left / 90 its left side (a hint),
"points": {landmark: [u, v]}}] with u right, v down. One camera per view is fitted (pose + focal) and, with fit,
the identity sliders, all views sharing ONE face (a front + side + three-quarter turnaround fits jointly). Points:
the nudge_human landmarks, eye.L / eye.R (eyeball centres) or lm0..lm67 (the 68-point face convention, e.g. from
a detector). The reply: reprojection error per view in px and mm with the three worst points named, INTEGRITY,
what moved, the picture. Stored in <model>/human_refs.json with the fitted cameras. A single frontal image says
nothing about depth (nose projection, jaw depth stay as they were); the fit matches SHAPE at the points given.
method "map" (default; humanfit_map, the reference-modelling study): a view WITH its image is read by the face
detector (MediaPipe's 478 points, each used at its calibrated place on the head with its own noise); clicked
points (the named landmarks) count +-1.5 mm; the identity is pulled toward the population's mean by its own
statistics, so what the pictures don't show comes out as what usually goes with what they do. Points lm0..lm67
(a detector's 68) are ignored when the image is there. read = a CHARACTER READ as evidence, in macros and
population sigmas: {"jaw_square": 1.5, "chin_projection": 1, "cheek_fullness": 1, "nose_upturn": 1} (names:
humanmacro.MACROS; say what a person sees at a glance: it is worth more than a second picture). A profile needs
clicked points (the detector doesn't find profiles). The reply adds the head's strongest macros.
measure=True (method map): macros MEASURED on the front picture join the read as evidence (humanmeasure: face
length, jaw / chin / face widths, brow height, nose length ... regressed from the detector's points; each with
its own sigma; what you say in `read` wins). RENDERS ONLY: the regression is calibrated on rendered heads and not
validated on photographs; on the study's truth renders it replaced a said read in-model (face 2.17 -> 1.94 mm).
method "points" = the old least-squares on the given points alone (it makes heads WORSE than the untouched one
on detector points: kept for comparison).
