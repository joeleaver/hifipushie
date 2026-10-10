# The artist block-in: a person's head from pictures (THE DEFAULT for modelling humans)

A portrait sculptor doesn't fit numbers to a photo. They start from a head of the right kind, put it beside the
pictures, squint, name the single biggest difference in masses and planes, change ONE thing a little, and keep the
change only if the whole head now reads closer. The block-in tools give you exactly that loop on a one-mesh human
(`human(..., source="human")`): you are the artist, the tools are the turntable, the light, the calipers and the
log. It is the first stage for every person modelled from references; likeness / fit_likeness detail, skin, hair
and clothes come after it.

Why not a solver: a fit to landmarks and outlines got the outline right and the person wrong (older, more male, the
wrong mass inside the outline) because outlines and points don't see the front planes of the face, and a local
slider tweak at a time made faces uglier. Whole-face directions learnt from the population keep the face a face; your
eye catches what the points miss; the target table catches what your eye misses.

## The loop

1. **Start from a base of the right kind**: `block_in_start(name, refs, sex=...)`. The person's body (MakeHuman's
   age / weight / height from `refs`, a one-mesh human whose pictures are fitted by `human_reference`), the head's
   local layers OFF (sliders, warp, folds, pose, shape), the identity = GNM's sampler CLASS MEAN for the sex (and an
   ethnicity class only if you know it), `gnm_base` by age (0.5 young: a soft adult face; 0 from 50: MakeHuman's own
   aged head reads older and leaner, which an older person needs). Never start from a previous fit: it carries that
   fit's mistakes. The reply is the first sheet and table.
2. **Look** (`block_in_look`, also returned by every step): per picture photo | clay under THE PHOTO'S OWN fitted light
   (hair cap: bald clay reads male; the person's own brows, SEATED on the surface: the front picture's detector brow
   band painted where it lands on the skin, so in 3/4 and profile they foreshorten and the far brow hides behind the
   bridge (2D-pasted brows stuck out past the silhouette and hooked over the nose); a presentable light iris: dark
   iris caps dominate a clay read; the shadow side lifted to a display fill: a painted light left half a 3/4 black)
   | 50 % overlay | outline difference (photo red, clay green) | squinted photo |
   squinted clay. Registered at the eyes and nasion only (a 2D shift): like a tracing over a photo, never registered
   on the outline it is meant to judge.
3. **Squint and name the single BIGGEST difference** in sculptor's terms: masses and planes, not features. Profile
   convexity, the muzzle (how far mouth and teeth stand forward), the jaw line and its angle, chin mass, nose mass and
   angle, face length vs width, the cheek planes (front vs side, where they turn), the bridge, how deep the eyes sit.
   Check the sex and age read (bald clay is a weak sex judge; the hair cap helps).
4. **One small step** (0.3-0.7 sd): `block_in_step(name, {direction: amount}, seen=..., why=...)`. Each step writes
   a NEW model (default: the next number), so every round stays comparable; `seen` and `why` go in the log.
   - FREE `"chin_height": 0.5`: the population's conditional mean per +1 sd: the face stays whole. Try first for
     masses and proportions.
   - HELD `"chin_height!": 0.5`: that one macro, every other macro held (a pseudo-inverse column). For a single
     feature, or to put back a neighbour a free step dragged. Costs more |c| per unit (more unusual faces).
   - GAPS `"nd:radix_width": 1`: vocabulary the macros lacked, filled with data-backed coupled directions (below).
   - `sex`, `eth0..2`: the sampler's sex axis (+1 = female mean -> male mean) and ethnicity contrasts.
   - BASE keys, SET: `head_scale` (base.style.human.head_size: the head's UNIFORM size about the neck, x the body's
     own head; 1 = the body's), `gnm_base`, `dimorphism`, `weight`, `eye_size` (base.head.eyes: the eye AND its
     orbit scaled about the eye centre).
   - LOCAL residuals, SET: `local:<faceslide slider>` (base.head.sliders), for what no identity direction draws;
     the reply warns past 2.5 x the slider's population sd beyond GNM (ICT: nose_radix_width 0.09, nose_tip_width
     0.18, nose_dorsum_width 0.12).
   - LIDS, SET: `lid_upper`, `lid_lower` (metres, -0.001 = 1 mm up): by measure, see 7.
5. **Keep it only if the whole face reads closer AND no target went out.** The reply has the read (the moved macro,
   before -> after, and the largest coupled moves), the target table's delta (items that went out, came in or moved
   by half a tolerance) and the new sheet. Otherwise step again from the earlier model: that is the revert (the log
   marks the abandoned step). Free moves drag neighbours; the table catches it; put the neighbour back with a held
   step (length -> philtrum, lips -> chin, bridge / eye depth -> narrower eyes, chin height -> chin width).
6. **The table after every step** (five groups: head shape, jaw and chin, eye placement, nose, mouth: likeness items
   read the same way on the picture and on the model through its fitted camera, with tolerances). `flag` items are
   shown, not counted (jaw_angle_height reads the detector's guess at the jaw contour, not the gonion). A SIZE line
   appears when the long lengths are all off the same way: that is a uniform scale (the camera's distance or the head's
   size), not shape: refit the camera (`block_in_step(..., cameras=[i])`) or set `head_scale`, never chase it with
   head_size / eye_spacing identity steps.
7. **Lids by measure, not by identity**: `lid_read(name)` gives the lid margins against the iris (MRD1 / MRD2 style,
   in iris radii) on the front picture and on the model's render. `lid_read(name, match=True)` sets lid_upper /
   lid_lower to the photo's margins as a step. Eye size and "almond" shape are mostly lid position and seating; an
   identity step for eye height made eyes read NARROWER.
8. **Judge in whole-face hair-cap clay under both lights** (the photo's light in the sheet; `look` / `look_skin` for
   the clay key and the dressed head) **before any fine detail.** A block-in is done when the outline sits on the
   pictures in every view, the table passes (or every miss is explained: a painted view, a detector guess), and the
   squinted clay reads as the same person: age, sex, mass. Then likeness / fit_likeness for features, then skin.

A sheet every 3-4 rounds for the person you report to; read it yourself first, bluntly.

## The feature pass: ZOOM IN, step, ZOOM OUT (Joe: "focus more on each feature, then zoom back out after each change")

After the whole-face block-in (outline, size, masses and planes right), go feature by feature, big to small: jaw and
chin, cheeks, nose, eyes (with brows and lids), mouth, ears; then the whole face again; repeat the pass while it
pays. Each round:
1. ZOOM IN: `block_in_look(name, focus=<feature>)`: per view the feature's crop at full resolution, photo beside
   clay through the same camera, REGISTERED AT THAT FEATURE'S OWN LANDMARKS (a 2D shift: an offset elsewhere doesn't
   hide its shape), overlay, the feature's own detector contours (photo red, clay green), the clay under a RAKING
   light (forms, not tone), the feature's squint, and its own checklist rows (every likeness item of that feature;
   the lids' margins for eyes). Name its single biggest difference in that feature's own vocabulary (a nose: dorsum
   line, tip width / projection / rotation, alar flare, columella, nostril show; eyes: lid margins, canthal tilt,
   fold, how deep the ball sits; mouth: vermilion heights, bow, corners, width, projection).
2. ONE step aimed at it: a held macro (`name!`), a gap direction, a lid move: `block_in_step(..., feature=<feature>)`
   returns the feature's before | after crops and its rows, then the whole-face sheet.
3. ZOOM OUT: look at the whole-face sheet + full table. Keep the step only if the FEATURE got closer AND the whole
   face reads closer or equal (no target out). Log the zoom-out read: `block_in_look(new, read="...", keep=True|False)`.
   Not kept: step again from the earlier model.
A feature that no direction can reach is a vocabulary gap (below), not a reason for a big step.

## Coupling you will meet (free directions)

| step | drags |
|---|---|
| face_length | the philtrum (gets longer before the chin does) |
| philtrum (free) | the chin (shorter) |
| lip_projection | the chin's height |
| chin_height (free) | chin width |
| bridge_height, eye_depth | interocular distance (eyes narrower) |
| orbital_rim (nd) | a heavy brow and deep eyes come with it (the male pattern): hold them or the face reads older |

## Filling a vocabulary gap

When no direction expresses a difference you see: write a reader for it on GNM heads, measure it over ~2000 sampled
heads, and look at R2 (is it linear in the identity?), its sd (does the population vary it?) and its couplings. Add
it as a coupled direction (conditional mean within sex). R2 high and sd visible: a new direction (`nd:` table in
`blockin_data.npz`, built by faces6 newdirs.py). Low R2 or a tiny sd: a real capability gap: a small LOCAL residual is
justified. A coupling against what you see (a defined orbital rim pulling in a heavy brow) means the look lives
elsewhere (lids, skin) or needs a held variant (`nd:orbital_rim|hold_brow_ridge_eye_depth`).

Filled so far: gonial_height, orbital_rim, lower_orbit (also humanmacro macros), radix_width (R2 0.90, sd ~0.6 mm:
GNM barely varies it; ICT adds ~0.13 mm beyond GNM: a near-invisible gap, `local:nose_radix_width`), tip_width (R2
0.94, sd 1.3 mm: comes with wide alae, full forward lips and a low bridge; `nd:tip_width|held` keeps those), and held
variants `orbital_rim|hold_brow_ridge_eye_depth`, `gonial_height|hold_face_length_chin_height`.

## What goes wrong

- Big steps (> 1 sd): one move then explains three differences and you can't tell which one was right.
- Chasing a uniform size with identity steps (head_size!, eye_spacing!): the table's SIZE line; check camera and
  head_scale first.
- Judging on the outline overlay alone: the outline is the easy part. The planes inside it (cheeks, muzzle, orbit)
  are what makes the person; squint.
- Fixing eyes with identity: lids are pose (lid_read).
- A painted or stylised picture's light is not one light, and its camera may fit badly (the clay turns differently
  from the painting): judge shape on the photographic views first; refit that view's camera.

## Tool reference

### `block_in_start`
block_in_start(name, refs, sex=None, age=None, body=None, gnm_base=None, ethnicity=None, cameras="keep",
replace=False, save=None): the block-in's first model.
- refs: a one-mesh human whose pictures are fitted (`human_reference` wrote its human_refs.json: views + cameras):
  its body is taken (body = keys merged over it, e.g. {"weight": 0.3}); or a views list ([{"image", "size", "yaw",
  "points"}] as human_reference) with age / sex / body for a new body, cameras fitted on the new head.
- sex: "male" | "female" | 0..1 (default the body's): the base is that sex's class mean in GNM's semantic sampler.
- age: overrides the body's age; gnm_base: default by age (0.5 to 25, 0 from 50, linear between).
- ethnicity: one of GNM's sampler classes (middle_eastern, asian, white, black) for that class mean; omit it unless
  you know it (eth0..2 steps can move along the contrasts later).
- cameras: "keep" the refs model's fitted cameras (they were fitted on another head: fine for a start), "refit" them
  on the new head (camera only).
- name must be new (replace=True overwrites); the log (blockin_log.json) lives in this model's folder and every
  later step appends to it. save: the sheet's path (default workspace/human_renders/blockin_<name>.png).
Returns the first sheet and target table.

### `block_in_look`
block_in_look(name, views=None, table=True, save=None, before=None, focus=None, read="", keep=None): the sheet (see
the loop, 2) of any block-in
model, rows per view (views = indices), crops fixed at the start head's frame so rounds compare; table=False skips
the target table. before = another model (any earlier round): under each view a row photo | before | after | the
change (|after - before| x4, dark = moved) | squint before | squint after. block_in_step's sheet always has it.
The text gives each view's eye-registration shift (pixels: a large one means the camera misplaces the head).
- focus: one of eyes, nose, mouth, chin_jaw, cheeks, ears: the ZOOM-IN sheet (see the feature pass): rows per view
  (the ear only in turned views) photo | clay | overlay | local contours | raking light | squint photo | squint clay;
  with before = another model a second row photo | before | after | change | raking before | raking after. The text
  is that feature's checklist rows (+ the lid read for eyes). Default save workspace/human_renders/blockin_<name>_<feature>.png.
- read / keep: log your ZOOM-OUT verdict on the step that made `name` (the log keeps both reads: the step's `seen`
  is the zoom-in read).

### `block_in_step`
block_in_step(name, moves, out=None, seen="", why="", cameras=None, look=True, save=None, feature=None): one round.
- feature: the feature this step is for (a feature pass round): the reply also carries its focus sheet (before |
  after) and its own rows, and the log records the feature's pass count before -> after.
- moves: {direction: amount}: macros free / held (`name!`), `nd:<gap>`, `sex`, `eth0..2` add (amount in sd);
  `head_scale`, `gnm_base`, `dimorphism`, `weight`, `lid_upper`, `lid_lower` are SET. An unknown name lists the
  vocabulary.
- out: the new model's name (default: name with its number + 1, or name_01); an existing name is refused.
- seen: the biggest difference you named; why: why this move answers it. Both logged.
- cameras: view indices whose camera to refit on the result head (camera only, the head held), e.g. a painted view
  whose camera fitted poorly, or after a head_scale change.
- look=False returns the text only. Reply: |c| before -> after, the moved macro's read, the largest coupled moves,
  the target pass counts before -> after, the items that changed, and the new sheet (with before | after | change
  rows: a half-sd step is hard to see beside the photo alone) + table.

### `lid_read`
lid_read(name, match=False, out=None, seen="", save=None): the lid margins against the iris on the front picture (MediaPipe
iris and lids) and on the model's front render (the visible eyeball through the iris centre), in iris radii: upper
(MRD1-like), lower (MRD2-like), and the opening's aspect. match=True: lid_upper / lid_lower solved so the model's
margins (both eyes' mean) equal the photo's, written as a block-in step (out, seen as block_in_step) and returned
with its sheet (save) and table. The lid pose moves GNM's eye-region expression, which also nudges the nasion
landmark ~1 mm: nasion-based lengths (face height, middle third, nose length) shift a little with it.
