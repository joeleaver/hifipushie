# Humans on one mesh: make, measure, fit, without breaking what you weren't looking at

`human(name, age, sex, ..., source="human")` makes a whole dressed person on ONE mesh: MakeHuman's body topology
and GNM's head topology, stitched once, offline, at the neck (hand-finished template; nothing is grafted when your
character is built). The body's own head carries the face, so a baby has a baby's head and no neck, an old woman an
old woman's, and the neck is always continuous. Everything else works as on any model (look, skin, hair, garments,
rig, export_asset).
The eyeball is a real one (base.head.eye_radius: 12 mm for an adult, smaller in children, written by `human` and
`block_in_start`), not GNM's 14.6 mm eye scaled with the head; models made before 2026-10-10 lack the key (their
ball and drawn iris are ~20 % big on a large head): set it, then re-match the lids (`lid_read(match=True)`).

What a character artist does with a base mesh applies here: **the big proportions first (age, sex, build), then
the face's identity, then local corrections, then style, each judged on the whole figure.**

## What shapes the person

| layer | keys | what it is |
|---|---|---|
| body | `base.body`: age, sex (0 female .. 1 male), weight, muscle, height, bust, firmness, race | MakeHuman's macros with measured growth (WHO stature, Snyder proportions). The head follows by construction. |
| face identity | `base.head`: seed, spread, identity {component: sigma}, features {nose, jaw, lips, cheeks, chin, brow_ridge, eyes, cranium: -1.5..1.5}, dimorphism | GNM's scan-based identity (253 components, in sigma). The seed loses its own age / sex / weight: the body gives the head those. |
| expression / pose | `base.head`: expression, pose {smile, lid_upper, ...}, mouth_gap | not shape: don't fit a likeness with them |
| corrections | `base.head.shape.push_more` (written by `nudge_human`) | small smooth bumps for what the sliders can't do |
| style | `base.style`, `base.head.eyes`, `shape.planes`, `simplify` | an artistic decision: see the style sheets |

## The rule: measure -> change ONE thing -> read the side effects -> look at the whole -> go on

Sliders are ambiguous and a number can be hit while the face around it is wrecked. So you don't set sliders: you
state evidence and a solver finds them, and every reply tells you what ELSE happened.

1. `measure_human(name)`: the named measures (body in cm, face in mm from the 68 landmarks, ratios as "a/b"), the
   integrity lines and a clay picture of the head.
2. Change one thing:
   - `fit_human(name, {"nose_width": "+3"})`, `{"eye_width/face_width": 0.19}`, `{"jaw_width": "x0.95"}`: a
     **minimal-change** solve. Every measure you did not name is held; landmarks far from the ones involved are held
     in place; the step stops where something you didn't ask for would move more than twice its tolerance, or an
     identity component would leave the plausible range (2.6 sigma). `free=["body"]` for body measures (weight,
     muscle, height); `release=[...]` names measures you allow to move.
   - `nudge_human(name, "chin", move=[0, 0, -0.004])`: one landmark moved, the rest held, mirrored sides together.
     What the identity sliders can't do becomes a small correction layer and is REPORTED ("the sliders can't do
     this"): that names a missing slider, tell whoever maintains the model.
   - `human_reference(name, views=[{"size": [w, h], "yaw": 0, "points": {"nose_tip": [u, v], ...}}, ...])`: cameras
     and the face fitted together on named 2D points of one or more reference images (front + side + three-quarter
     share one face). The reply gives the reprojection error per view in px and mm and names the three worst points.
     Give each view its `"image"`: the face detector then reads it (478 points, each used where the detector really
     puts it on the head, with its own noise), and the fit is a MAP estimate: what the pictures don't show comes out
     as what usually goes with what they do. Add what you SEE at a glance as `read={"jaw_square": 1.5,
     "chin_projection": 1, "cheek_fullness": 1, "under_chin": 0.8, "nose_upturn": 1}` (macros in population sigmas:
     jaw / chin / nose / cheeks / brow / eyes / neck / ears / skull; say the negatives too: "square jaw" alone brings
     fat with it, "clean under the chin" keeps it bone). Measured on heads of known shape: one front picture + a read
     is as good as two pictures; ~20 clicked points (eye and mouth corners, nose tip / base / wings, chin, brow ends)
     beat the detector; a profile needs clicked points (no detection); a view that disagrees with the others by
     > 5 mm is dropped and named. The result is the most probable head, so it is SOFT: bony structure (jaw corner,
     brow ridge, hollows, a cleft) comes after it, from base.head.shape controls, never before.
3. Read the reply from the top:
   - `INTEGRITY: ok` or `BROKEN: ...` (faces folded by the change, edges stretched at lids / lips / nose / ears /
     the neck bridge, an eyeball through its lids, crossed lips). **A broken result is not saved.**
   - `NOT MET` / `held back to N%`: the request was only partly possible without moving the rest or leaving the
     plausible range. That is an answer, not a failure: ask for the measures that would have to move as well,
     release them, or accept that the request is a STYLE (eyes three times wider is not an identity).
   - `UNINTENDED: ...`: measures that moved though you didn't ask. Decide whether you accept each one.
   - `vertices: ...`: how far the mesh moved and how much of it lies away from what you asked about.
4. Look at the picture (before | after | where vertices moved), then at the whole dressed figure with `look(name)`.
   An eye that is right on a head that is wrong is wrong.
5. `measure_human(name, since=N)` shows everything that changed since version N; `revert(name, N)` goes back.

`force=True` widens the plausible range and saves over a broken mesh. It is for deliberate stylisation, and the
reply still lists the damage.

## Measures

Body (cm): stature, heads (stature / head height), head_height, sitting_height, biacromial (between the shoulder
joints), hip_breadth, trochanter_height (leg length), hand_length, foot_length, chest_circ, waist_circ, neck_circ.

Face (mm): interocular (eye centres), face_width (jaw line at the ears), jaw_width, chin_width, face_height
(nose bridge to chin), eye_width, eye_height (the opening), eye_spacing (inner corners), eye_to_chin, brow_height,
nose_length, nose_width, nose_projection, philtrum, mouth_width, lip_height, mouth_to_eye, chin_height.

Typical adult ratios to sanity-check a likeness: eye_width/face_width ~0.18, interocular/face_width ~0.41,
nose_width/mouth_width ~0.63, jaw_width/face_width ~0.67.

## Matching a reference image

**For a person's head from pictures, the artist block-in is the default** (guide(topic="block_in")): human_reference
fits the cameras, then block_in_start / block_in_look / block_in_step / lid_read. The fit tools below (fit_human,
nudge_human, a human_reference identity fit) are for measured targets and single corrections after it.

- Give named points, not adjectives. Landmarks: chin, nose_tip, nose_base, nose_bridge, lip_upper, lip_lower,
  mouth_corner.L/R, jaw.L/R, jaw_back.L/R, brow.L/R, brow_inner.L/R, eye_outer.L/R, eye_inner.L/R, lid_upper.L/R,
  lid_lower.L/R, ala.L/R, chin.L/R, eye.L/R (eyeball centres), or lm0..lm67 (the standard 68-point face
  convention, which most face landmark detectors output).
- More views are better evidence than more points: a frontal image says nothing about depth (nose projection, jaw
  depth, brow ridge stay as they were). A profile fixes those.
- Left and right are the PERSON's (.L = their left = image right in a front view).
- A fit matches shape at the points given. Much of a likeness, and most of a style, is shading, line and paint
  (skin, brows, hair, make-up): fix the shape first, then judge those under the style's own light.

## What goes wrong

- Hitting one measure with `force` and not reading UNINTENDED: the number is met and the face is someone else's.
- Fitting a smile, an open mouth or raised brows into the identity: pose the reference's expression first
  (`base.head.pose`) or pick neutral reference images.
- Asking the identity for a style (huge eyes, a tiny nose): it comes back held. Use the style layer.
- Wide `spread` on women and children masculinises a bald head: keep it at or under ~0.5.
- Measuring the old path: these tools need `base.body.source == "human"`.

## Feature controls on a head (base.head.shape), and what they taught

Each is a smooth field on the head's own landmarks, mirrored, with the landmarks riding. They are for a feature the
identity space can't give; every one must pass the integrity check and be judged in ALL views (six-view sheet +
the reference rows), not on the measure it was made for.

- `jawline` {below_lobe, forward, out, tuck, neck, sharp, smooth}: the jaw's visible edge (GNM's jaw contour, one
  diagonal from the ear lobe to the chin) carried onto an L: a ramus under the lobe, an angle `below_lobe` m under it,
  a straight border to the chin's corner; `sharp` = how far along the line the turn is spread (4-5 mm crisp);
  `tuck` draws the band outside the edge in, `neck` narrows the neck's sides under the corner.
- `chin` {width, square, project, height, under, cleft}: mental corners apart, the bottom levelled, the chin forward,
  the submental skin lifted (`under`: the chin-to-throat line runs back level before it turns down), a mid-line groove.
- `ears` {out, blend}: the auricle turned RIGIDLY about its attachment line (lobe -> top of the front attachment);
  the top swings out, the lobe stays. Check with the auricle's own edge lengths (rigid = unchanged).
- `nose_tip` deg | {up, round}: the nose's base line (alar base -> under the tip) tilted about the alar bases; `round`
  blunts the tip. `hood`, `hollow`, `jaw_angle` as before.
- `lean` m | {under_jaw, jowl, submental, radius}: soft tissue THINNED over the bone. The jaw's border and the chin
  keep their place; the skin under and behind the border (and under the chin) moves in along its own normal, `jowl`
  thins the lower cheek just over it. This is what turns "soft jaw, the border lost into the neck" into a jaw that
  reads, on ANY skull width, without a lump (5-7 mm under_jaw, 2-3 jowl). It is not weight run backwards (that
  narrows the skull) and not `hollow` (a dent under the cheekbone).
- `chin.cleft` needs `cleft_width` (4-5 mm) and `cleft_lobes` (2-3 mm: the two pads either side) to be SEEN: a
  3 mm groove 2.8 mm wide on a round chin was read by no one.

### Structure after a MAP fit: the order that worked (Garrett, blind-read by 3 readers per head)

1. The MAP head (`human_reference`, with a read), its deviation x1.5 at most.
2. BONE in the identity, not as local bumps: `humanmacro.apply(identity, {...}, held=True)` moves one macro with the
   others held (chin_projection +1.5..2.3, jaw_angle +2, brow_ridge +1). A chin pushed forward by `shape.chin.project`
   is a button with a hook under it; the macro brings the whole mandible's front. Check the evidence residual after
   each (nose_upturn +1 cost 0.3 mm in the front picture and was refused; +0.5 passes).
3. SOFT TISSUE by `shape.lean`. `shape.jawline` (the L) on a wide, full lower face drags the cheek into a jowl pouch
   with a crease: don't.
4. Surface marks last: cleft (with width and lobes), nose tip.
Gentle planes / hood / hollow at half strength are below what three blind readers can tell apart (their score
swings +-1.5 between identical heads' reads): judge those by eye, or leave them out.

Lessons from one hard likeness (a lean man fitted toward a broader reference):
- Numbers in tolerance are not a likeness. A width warp plus a moved jaw measured right and read as a bulldog; a
  full eye narrowing measured right and read as sad slits. Look, in every view, after every change.
- A squint, a frown, a set mouth in the reference are EXPRESSION: fit at most part of them into the neutral head.
- Choose the pivot from the anatomy: a nose tip turned about the mid bridge only swings the nose forward (the tip
  lies below that pivot); about the alar bases it tilts the base line. An ear turned about its root's middle makes a
  fin; about its attachment line it stands out as an ear does.
- A head bigger than its body's (style head_size) or warped at the nape must hand over through the whole neck, not
  at the stitch: a collar ring round the neck's base means the hand-over is too short.
- A blind read by one reader moves by ~10 descriptor-views between readers of similar heads: use several, and trust
  only what all of them say.

### Analysis by synthesis: the same detector on the picture and on the model's render

A detector's points are not the model's landmarks (lids: its upper-lid points sit 0.6-0.9 mm under GNM's, its
lower-lid points 1.5 mm over: an opening reads 2-2.5 mm small), so "the picture's lid is higher than the model's"
from points against landmarks means nothing. Run the SAME detector on the model's own render through the fitted
camera and compare its numbers with the picture's: definitions cancel. On one hard head this found what ten passes
of point fitting had not: eyes 4 mm too wide and 3 mm too open, brows 1.4 mm high, the face 3% too wide for its
height, and
that the picture's "frown / squint" scores (browDown 0.6, eyeSquint 0.6) are reproduced by the NEUTRAL head once its
eyes and brows are right: they were the man's face, not an expression. So:
- Don't pose a reference's "expression" by hand, and don't read it from the detector's blendshape scores: learnt on
  600 of our renders with known poses, the scores tell a pose from an identity hardly at all (cross-validated rms /
  sampled spread: smile 0.80, upper lid 0.83, brows 0.97, mouth width 0.92; 1 = nothing).
- Change one control, measure again: `base.head.eyes` (the eyes' size), held identity macros (eye_height, eye_width,
  brow_height, face / jaw / chin widths). Each step is seconds.
- It only holds where the picture and the render look alike to the detector. NOT for lips on a stubbled face (the
  shadow under the lip read as a 10.8 mm lower lip; matching it made duck lips) and weakly for mouth corners (the
  measure moves with lip fullness). On the one mesh the eyes' spacing is the body's: the eye_spacing macro moves
  nothing; compare widths as ratios to the pupils' distance.

### Age is soft tissue (base.head.shape; `headage.py`)

The identity has no age (the age direction of the body's field moves no macro by 0.1 sigma). An older face is the
same skull with tissue that has thinned, slid and folded: `nasolabial` (depth, length, bulge: the crease runs on the
skin description's own nasolabial line, so the painted fold and the form agree), `prejowl` (the sulcus on the jaw's
border + a slight jowl), `lid_fold` (upper-lid skin over the outer half; `hood` is the margin), `cheek_flat` (the
mid cheek thinned and slid down), `lips_thin`. Millimetres: 2 mm of fold reads; 4 mm of `hollow` under frontal light
reads as a bruise. Don't thin lips because a face is old: measure them (above) first.

### A picture as the albedo (`texture_from_reference`)

The projection test kept as paint: the fitted picture, de-lit roughly, as a decal layer over the skin description
where its camera saw skin square-on; ours on ears, under chin and nose, hair, eyeballs, neck, and for all relief and
highlights. It is the picture's resolution (say it: 1.3 mm a pixel is no pores) and the picture's shadows. Make it
again after the head's shape changes.

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
