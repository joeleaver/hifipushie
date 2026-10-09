# Humans on one mesh: make, measure, fit, without breaking what you weren't looking at

`human(name, age, sex, ..., source="human")` makes a whole dressed person on ONE mesh: MakeHuman's body topology
and GNM's head topology, stitched once, offline, at the neck (hand-finished template; nothing is grafted when your
character is built). The body's own head carries the face, so a baby has a baby's head and no neck, an old woman an
old woman's, and the neck is always continuous. Everything else works as on any model (look, skin, hair, garments,
rig, export_asset).

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
