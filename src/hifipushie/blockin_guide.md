# The artist block-in: a person's head from pictures (THE DEFAULT for modelling humans)

A portrait sculptor doesn't fit numbers to a photo. They start from a head of the right kind, put it beside the
pictures, squint, name the single biggest difference in masses and planes, change ONE thing a little, and keep the
change only if the whole head now reads closer. The block-in tools give you that loop on a one-mesh human with a GNM
head: you are the artist; the tools are the turntable, the light, the calipers and the log. It is the first stage
for every person modelled from references; likeness detail, skin, hair and clothes come after it, on the head it
produces.

Why not just a solver: a fit to landmarks and outlines gets the outline right and the person wrong (older, more male,
the wrong mass inside the outline), because outlines and points don't see the front planes of the face; and local
slider tweaks one at a time make faces uglier. Whole-face directions learnt from the population keep the face a face;
your eye catches what the points miss; the measurements catch what your eye misses. The solve gives the base; you
make the final artistic calls with hand steps.

Enable the tools with `enable_toolset("human")` (and `likeness`). Sub-topics (guide(topic=...)): `blockin_solve`
(the joint solve in detail: what it reads, cameras, lens and distance, detectors, what it can't read),
`blockin_steps` (the step vocabulary: free / held / mm / sculpt / base keys / identity components; coupling; filling
a vocabulary gap; GNM's control atlas), `blockin_features` (the orbit, the eye step, the eye ruler, brows and iris,
the lips step, the picture's expression), `blockin_tools` (every block-in tool's parameters), `gnm_driving` (the
driving manual: what you see -> the GNM control), `likeness` (the feature checklist after the block-in).

## Stage 0: describe the references and the head (before any step)

1. **The references**: what each picture is (photo, painting, generated), its view (front, 3/4, true side) and
   whether its stated angle holds, the lens if known (EXIF), the light, the expression, what each can and can't
   show (a 3/4 doesn't show the nasion's depth; a front alone has no depth), conflicts between pictures and which one
   is the authority per item.
2. **The person in words**: sex and age read, build, and the 3-5 masses and planes that make this face (profile
   convexity, muzzle, jaw line and angle, chin mass, nose mass and angle, face length vs width, cheek planes, bridge,
   how deep the eyes sit, brow ridge).
3. **Measurable items per feature** (the likeness checklist; `face_ruler` reads most of them in mm off the pictures):
   face width and height ratios, eye spacing and opening, nose width / length / tip, mouth width and lip heights, jaw
   and chin, brow ridge, profile points. Each with the picture's value, the reader's error and a tolerance; mark what
   no picture can read (e.g. eye depth without a known-angle profile; chin width) as INFERRED.

## The loop

1. **Start from a base of the right kind**: `block_in_start(name, refs, sex=...)`: the body from the refs, the
   identity = GNM's class mean for the sex (an ethnicity class only if you know it), on a GNM-NATIVE head (GNM's own
   base, eyeball, mouth, at its own size, the body fitted to it). Nothing of ours is on its surface; the reply lists
   what was dropped and what was left. Never start from a previous fit: it carries that fit's mistakes.
2. **Measure first**: `face_ruler(name)` reads the millimetre measures off the pictures (skin outlines and iris
   centres through the fitted cameras) against the model, largest gap first, with the reader's error and the `mm:`
   move that closes each. Run it again after every step. When a ruler row and your eye disagree, check the row:
   it is usually right.
3. **The joint solve before any hand move**: `block_in_solve(name, cameras="free")`, 3-4 calls until its |dc| falls
   under ~2-3 (stop at the first DAMPED step). One solve over every view (outlines, irises, limbus, lid margins, lip
   borders, anchors) under GNM's prior, cameras partly free. Read its reply: AT THE BOUND, DISAGREE, the CAMERA and
   DISTANCE lines, and the lists MOVED WITH NO READ / MOVED FAR ON A WEAK READ (treat those as INFERRED; check them by
   eye or put them back). It does NOT see the surface inside the silhouette (cheek volume, the lid's fold, the nose's
   planes): those are hand steps. Details: `blockin_solve`.
4. **Look**: `block_in_look(name)` (every step returns it too): per picture photo | clay under the photo's own fitted
   light | 50 % overlay | outline difference | squinted photo | squinted clay. Judge on the judging sheet: the
   reference beside the result, and the reference pictures projected as the head's skin + a blend.
5. **Squint and name the single BIGGEST difference** in sculptor's terms: masses and planes, not features. Check the
   sex and age read. Then look the phrase up in the driving manual (`gnm_controls(phrase="...")`, guide topic
   `gnm_driving`): the control, its sign, mm per unit, what to hold, what it drags. If the difference is measurable,
   use the `mm:` move.
6. **One small step**: `block_in_step(name, {direction: amount}, seen=..., why=...)`, 0.3-0.7 sd (a big mass 1-2 sd).
   Each step writes a NEW model, so rounds stay comparable. Free (`chin_height`), held (`chin_height!`), millimetres
   (`mm:pupils_apart`), sculpt (`sculpt:<zone>`) for a feature no macro reaches. Details: `blockin_steps`.
7. **Keep it only if the whole face reads closer AND no target went out** (the target table's delta is in the
   reply). Otherwise step again from the earlier model; free moves drag neighbours: put them back with a held step.
8. **The feature pass** once the whole face is right (below), then the eyes (orbit first, then the lid step), the
   lips and the picture's expression (`blockin_features`).
9. **Done** when the outline sits on the pictures in every view, the table passes (or every miss is explained: a
   painted view, a detector guess), and the squinted clay reads as the same person: age, sex, mass. Then likeness,
   skin, hair, clothes, on THIS head.

## The feature pass: ZOOM IN, step, ZOOM OUT

After the whole-face block-in, go feature by feature, big to small: jaw and chin, cheeks, nose, eyes (with brows and
lids), mouth, ears; then the whole face again; repeat while it pays. Each round:
1. ZOOM IN: `block_in_look(name, focus=<feature>)`: the feature's crop per view, photo beside clay registered at
   that feature's own landmarks, overlay, its contours, the clay under a RAKING light (forms, not tone), its squint
   and its checklist rows. Name its biggest difference in its own vocabulary (a nose: dorsum line, tip width /
   projection / rotation, alar flare, columella, nostril show; eyes: lid margins, canthal tilt, fold, depth; mouth:
   vermilion heights, bow, corners, width, projection).
2. ONE step aimed at it: `block_in_step(..., feature=<feature>)` returns its before | after crops and rows.
3. ZOOM OUT: the whole-face sheet + full table. Keep the step only if the FEATURE got closer AND the whole face reads
   closer or equal. Log it: `block_in_look(new, read="...", keep=True|False)`.
A feature no direction can reach is a vocabulary gap: ask the atlas (`gnm_controls(query="bridge walls")`), then
SCULPT it (macros held), and only then a local residual.

## Craft rules (each once)

- Masses and planes before features, features before detail; one change at a time, small.
- Measure what you can in mm (the ruler) and move in mm; judge what can't be measured by eye, squinted.
- Don't move a measure whose row is inside its reader's error (eye depth from photos is often NOT READ).
- A uniform size difference (the table's SIZE line) is the camera's distance or the head's size, never shape: refit
  the camera, don't chase it with identity steps.
- The outline is the easy part: the planes inside it (cheeks, muzzle, orbit) make the person.
- The orbit before the lids: eye depth and the brow over the eye are big masses; the lid hangs between them.
- Measure the eye with the eye ruler, never by eye; GNM's own eyeball is the default (don't shrink it for an iris:
  the iris has its own size, `iris_mm`).
- A painted or stylised picture's light and camera fit worse: judge shape on the photographic views first.
- When every picture shows the same expression, geometry can't tell it from identity: say so when you report.
- Report what was read and what was inferred; a head is not "matched" on numbers alone.

## Self-review loop (every round)

1. Reference beside result at the same camera: the block-in sheet per view (photo | clay under its light | blend |
   outline) and, every few rounds, the judging sheet (reference projected as skin + blend), whole face and per
   feature (focus crops).
2. Per region (overall mass and proportions, profile, jaw and chin, cheeks, nose, eyes and brows, mouth, ears), list
   what reads wrong against the reference, concretely (where, what, how far off in mm where the ruler reads it).
   Mark each MAJOR (a different person: wrong mass, plane, proportion, age or sex read) or MINOR. Order: masses and
   planes before features, features before detail.
3. Fix the worst MAJOR with one small step (or a solve call if the cameras moved); keep it only if the whole face
   reads closer and no target went out.
4. Repeat until no region has a MAJOR. Read your own sheet first and bluntly before showing it to anyone.

A head that passes every table row but doesn't read as the person is wrong; a row that fails because the reader is
wrong is explained, not chased.

## What goes wrong

| Mistake | Instead |
|---|---|
| Big steps (> 1 sd): one move explains three differences | Small steps, one difference each |
| Chasing a uniform size with `head_size!` / `eye_spacing!` | The SIZE line: refit the camera or `head_scale` |
| Judging on the outline overlay alone | Squint; the planes inside the outline |
| Fixing eyes with identity steps | Lids are their own step (`lid_read`); the orbit first |
| Hand moves before the joint solve | `block_in_solve` from the start head first |
| Moving a measure on a row inside its error | Leave it; it is the population's guess (INFERRED) |
| Chasing the detector's chin rows when a side view exists | They read 2-4 mm off by construction: judge the chin on the blends |
| Starting from a previous fit | `block_in_start` from the class mean |
| Asking for tilted views to fix the jaw | A true 45 deg 3/4 and a true 90 deg side are what help |
