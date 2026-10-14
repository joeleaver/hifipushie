# Humans: head shape controls, structure after a fit, age, the native head

Read guide(topic="human") first.

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

### Structure after a MAP fit: the order that worked (blind-read by 3 readers per head)

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

## The head at GNM's own size on a fitted body: `base.head.attach: "native"`

By default the one mesh carries GNM's head at the size and place of the MakeHuman body's own head (and MakeHuman's
heads are small: a woman's is ~10 % under a measured one, so its figures stand ~8-9 heads tall and their eyeballs and
irises come out small). `human(..., head={"attach": "native"})` or `edit_model set_key base.head.attach "native"`
turns that round:
- the HEAD is GNM's own evaluation (template + identity + expression) in GNM's real metres, every vertex from the
  seam ring (low on the neck) up; nothing of the body's head, no blend, no head style sliders (`base.style.human`
  head_size, cranium, eye_spacing ... and `base.head` gnm_base / dimorphism / scale are ignored and named in the report);
- the BODY is fitted: its height is solved so the figure stands at `base.body.height` under this head, and its neck and
  shoulders are moved to meet GNM's neck at the ring;
- the head is SEATED BY ITS OWN NECK BASE (GNM's own shoulder slope fitted on the body's shoulders) and the body's neck
  base is laid on GNM's forms next to the ring; the rule is general, nothing is tuned per character;
- `base.head.size`: by default the head goes a little with the stature, as people's do (stature ^ ~0.27: 1.000 at the
  sex's mean stature, 1.025 on a 1.95 m man); a number fixes it;
- `measure_human` prints the attach CHECKS against ANSUR for the sex and stature (head height, top of head and chin
  over the pit of the throat, neck girth) and FLAGS: a NECK CONFLICT (head's neck against the body's own past 8 %, and
  which side is unusual), a head + neck short for a very tall body, a child's body (GNM is an adult head);
- `measure_human` prints the attachment: head height, heads tall (adults measure ~7.5), eyes apart, eyeball radius,
  neck girth head / body at the ring, and NOTES when the two disagree by more than 12 % (then change the body's
  weight / muscle, not the head).
- export: with `parts.body.topology: "wrap"` the GLB holds TWO skinned meshes, `head` (GNM's topology, the face
  shapes) and `body`, sharing the seam ring's 110 vertices exactly (position, normal, uv, weights), on one skeleton.
  `base.head.mesh: "welded"` writes one mesh. A decimated body has no ring: one mesh, with a WARNING.
- after switching a model with fitted reference cameras to native the cameras belong to another head:
  `block_in_step(name, {"attach": "native"})` does the switch AND carries them (block_in_solve refuses stale cameras
  and names that step); hair and clothes made on the old head must be remade.
- `block_in_start` makes a native head BY DEFAULT with nothing of ours on its surface (no strokes, no
  skin.folds, no wrinkle relief carried from the refs model); on it block_in_step refuses head_scale / gnm_base /
  dimorphism / eye_size. The `human` tool itself is unchanged: its default head is still the grafted one, and
  `source="human"` a body-carried seeded face; pass `head={"attach": "native"}` for a native one.
- the NECK: GNM's female class-mean neck is 363 mm (ANSUR 330 +- 18) and MakeHuman's female neck ~290 at any weight:
  a class-mean woman is flagged NECK CONFLICT. block_in_solve puts ANSUR's prior on the neck's girth (guide topic
  block_in_solve); without pictures, `block_in_step {"neck_mm": mm}` sets it.
