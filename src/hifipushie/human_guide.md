# Humans on one mesh: make, measure, fit, without breaking what you weren't looking at

`human(name, age, sex, ..., source="human")` makes a whole dressed person on ONE mesh: MakeHuman's body topology
and GNM's head topology, stitched once, offline, at the neck (hand-finished template; nothing is grafted when your
character is built). The body's own head carries the face, so a baby has a baby's head and no neck, an old woman an
old woman's, and the neck is always continuous. Everything else works as on any model (look, skin, hair, garments,
rig, export_asset).
The head is GNM-NATIVE: every component GNM ships comes from ONE evaluation of its bases for the spec's
coefficients. `base.head.identity` holds GNM's whole identity (head_000..169, eyes_000..002, teeth_000..079; unset =
the mean) and `base.head.expression` its expression (left / right_eye_region_*, lower_face_region_*, tongue_*,
pupils_000).
- The EYEBALL is GNM's own two-sphere eye at its eye joint: the scleral sphere (14.6 mm x the head's scale: GNM holds
  it constant because its lids, blink and eye expressions are shaped round it), the corneal bulge (on by default;
  `base.cornea: false` turns it off, numbers override it), the iris drawn at GNM's limbus for the identity
  (`eyes_000`; `block_in_step {"iris_mm": mm}` sets it from a read; `skin.eyes.iris_size` overrides the DRAWN iris
  only) and the pupil as GNM's geometry has it (0.5 of the iris at rest; `base.head.expression.pupils_000`: -1 = 0.33,
  +1 = 0.67; `skin.eyes.pupil` overrides). `base.head.eye_radius` (m) is an explicit OVERRIDE: our own ball, seated
  by a search, which GNM's lids stand ~0.5 mm off; older heads have 0.012 written in their spec
  and keep it until rebuilt (block_in_start drops it).
- The MOUTH is GNM's own: the mouth bag (its sock joins the head's surface when the lips part), teeth with gums
  (part "teeth"; the identity's teeth_* components) and tongue (part "tongue"), moved by the same expression as the
  skin (the lower row and the tongue by lower_face_region_*, the tongue by tongue_*). No key needed.
  `base.head.interior` (the face kit's slit / bag / teeth / tongue) still works and is what an older spec with that
  key gets; `base.head.mouth: "gnm" | "kit" | "none"` asks for one. A style that moves the lips off GNM's surface
  (pushes, simplify, shape ops) cannot use GNM's teeth: the save and the export say so and fall back to the kit's
  interior (or none).
- Poses: `export_asset(face_shapes=...)` shapes are GNM expression coefficients; `faceshapes.GnmFace(spec)
  .shape_coeffs("jawOpen")` gives them to put in base.head.expression for a posed look.

What a character artist does with a base mesh applies here: **the big proportions first (age, sex, build), then
the face's identity, then local corrections, then style, each judged on the whole figure.**

Sub-topics (guide(topic=...)): `human_shape` (feature controls on the head, structure after a fit, analysis by
synthesis, age as soft tissue, a picture as albedo, the head at GNM's own size), `human_tools` (every human tool's
parameters; guide(topic="tool:human") is the `human` tool's own section). A person from pictures: `block_in` first.

## Describe the person first (before any slider, fit or step)

Write down from the references, as measurable items with a tolerance (mark what no picture shows as INFERRED):
age and sex read, build (weight, muscle), stature (from something of known size) and heads tall, the body's
proportions (shoulders vs hips, leg length, sitting height), the head's size against the body, and the 3-5 things
that make the face (the block-in's stage 0). Then choose `base.body` and the head from those items; never start
from another character's spec.

## Self-review loop (every change)

Look at the whole dressed figure AND the region you changed, beside the reference at the same framing; list what
reads wrong (MAJOR: wrong age / sex / build / proportion read, a broken mesh, a face that is someone else; MINOR);
fix the worst MAJOR with ONE change; read INTEGRITY and UNINTENDED before keeping it. A number met on a face that
reads as someone else is wrong.

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
