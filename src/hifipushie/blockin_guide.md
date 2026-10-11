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
     orbit scaled about the eye centre), `eye_radius` (base.head.eye_radius, m: an ABSOLUTE eyeball, 0.012 for an
     adult, drawn iris ~6 mm; it seats itself under the lid rims; eye_size still multiplies it, head_scale doesn't).
     block_in_start and every NEW one-mesh human (human tool) set it (by age: 0.012 from the late teens). Models
     made before 2026-10-10 lack it: their ball is GNM's 14.6 mm eye x the head's scale (a 7.3 mm iris on a big
     head); when you work on one, step `eye_radius: 0.012`, then `lid_read(match=True)` (the lids' iris-radius
     read changes with the iris).
   - DESIGNED age / soft-tissue ops, SET: `shape:<op>`: faceslide's age sliders in their units (`age_nasolabial`
     +1 = a 2 mm fold, `age_prejowl`, `age_cheek_flat`, `age_lid_fold`, `face_planes`, `face_lean`, `cheek_hollow`
     +1 = 4 mm) and headage's ops without a slider (`eye_bag`, `lip_bow`, `lip_roll` in m, `lips_thin` a share).
     Hand-authored, NOT learnt from people: the reply and the log flag them DESIGNED. Place them by eye, zoomed in
     (focus=cheeks / mouth) under the raking light against the pictures; the cheeks rows (nasolabial_fold,
     cheek_hollow: shading contrast, photo minus clay) should close. Garrett: age_nasolabial 0.5 closed the fold's
     gap 22 -> 19 % (front) and 28 -> 20 % (3/4).
   - LOCAL residuals, SET: `local:<faceslide slider>` (base.head.sliders), for what no identity direction draws;
     the reply warns past 2.5 x the slider's population sd beyond GNM (ICT: nose_radix_width 0.09, nose_tip_width
     0.18, nose_dorsum_width 0.12).
   - LIDS, SET: `lid_upper`, `lid_lower` (metres, -0.001 = 1 mm up): by measure, see 7.
   - SCULPT, the GNM way (THE standard fix for a feature no macro reaches, before any local): `"sculpt:<zone>": mm`
     moves a named zone (its mean normal, + out of the face) by the LEAST-COST identity change over all 170 comps with
     every macro HELD (the face's measured proportions stay) and a locality penalty on the skin > 6 mm away;
     `relief:<zone>` moves it against its 5 mm surround (- deepens a groove: alar crease, nasolabial, lid fold).
     Options after `|`: `hold=<zone>+<zone>` (zones kept still), `free=<macro>+..` (macros let go), `loc=<w>`. Zones:
     `gnm_controls(zones=True)`. Garrett's narrow bridge: `"sculpt:bridge_walls|hold=dorsum": -1.0` = walls 0.746 ->
     0.590 at |dc| 3.5 (the designed local nose_dorsum_width -0.8 gave 0.670); -2.0 reaches his concept's 0.504. A
     sculpt of 1 mm usually costs |dc| 2.5-4: big next to a macro step, but it moves a real face's |c| (~13), not away.
   - RAW CONTROLS: `"gnm:<control>": amount`: any identity-space control of the atlas (`head_042`, `z:05` a sampler
     latent, `label:sex`, `pc:nose_region3`): see `gnm_controls`.
5. **Keep it only if the whole face reads closer AND no target went out.** The reply has the read (the moved macro,
   before -> after, and the largest coupled moves), the target table's delta (items that went out, came in or moved
   by half a tolerance) and the new sheet. Otherwise step again from the earlier model: that is the revert (the log
   marks the abandoned step). Free moves drag neighbours; the table catches it; put the neighbour back with a held
   step (length -> philtrum, lips -> chin, bridge / eye depth -> narrower eyes, chin height -> chin width).
6. **The table after every step** (five groups: head shape, jaw and chin, eye placement, nose, mouth: likeness items
   read the same way on the picture and on the model through its fitted camera, with tolerances). `flag` items are
   shown, not counted (jaw_angle_height reads the detector's guess at the jaw contour, not the gonion; alar_width and mouth_over_alar read MediaPipe's alar points, which sit on the cheek past the alae: judge the alae by eye in focus=nose). A SIZE line
   appears when the long lengths are all off the same way: that is a uniform scale (the camera's distance or the head's
   size), not shape: refit the camera (`block_in_step(..., cameras=[i])`) or set `head_scale`, never chase it with
   head_size / eye_spacing identity steps.
7. **The EYE STEP: lids and fold the way GNM is built** (Joe: "we shouldn't really ever use our 'fix' [lidfold]"):
   GNM's identity is the relaxed neutral and its eye-region EXPRESSION is the lids' state; its lids have folds as
   identity + expression configurations. `lid_read(name)` reads the picture (lid margins against the iris in iris
   radii, MRD1 / MRD2 style; the fold line's height over the lashes and darkness, lidfold.read_lid) beside the model.
   `lid_read(name, match=True)` is the step: one solve over the identity + GNM's symmetric eye-region expression
   (blockin_eyes.py) for the margins, the fold line's height (the crease's) and that a line is there (>= 1.2 mm deep
   when the picture's line is dark), or a covered platform when the picture shows no line (hooded); the rest of the
   face held (68 landmarks off the eyes within ~0.3 mm). It ships as head.identity + head.expression, the lid pose
   cleared; never lidfold (head.fold: old models only). Judge it with focus=eyes under raking light AND dressed
   (look_skin views eye / face): a crease under ~1 mm deep doesn't read dressed. Tess (b2_T06): lids 0.65 / 0.88
   vs her 0.67 / 0.88, crease 1.1 mm deep at 5.3 mm (her line 5.15 mm), |dc| 3.0, |e| 1.8, table unchanged.
   The socket is HELD in the solve (humanmacro orbital_rim / lower_orbit / eye_depth on the mesh with the expression,
   sigma 0.15 sd): unheld, the fold came with orbital_rim +1.1..1.4 / lower_orbit -1.1..-1.6 sd (dark, tired sockets);
   held, +0.3 / -0.05 for the same crease depth (~0.9-1.0 mm). Honest limit (gnm_atlas "## gnmdetail"): GNM's fold is
   a ~2.5 mm-wide valley, not the photo's 1 mm slit; at ~1 mm deep it reads only as a soft step in EEVEE, a line from
   ~1.6 mm (|dc| ~7.6) or under Cycles.
   `match="pose"` is the older lid_upper / lid_lower offsets. Eye size and "almond" shape are mostly lids and seating:
   an identity step for eye height made eyes read NARROWER.
7b. **The picture's own expression** (`block_in_expression(name)`): GNM's identity is the RELAXED neutral; a picture
   that smiles (fuller lips, lifted corners, a cheek apple) or squints is compared against that neutral, and the smile
   leaks into mouth / cheek identity steps. The tool fits each detector picture's expression on the current head
   (identity and camera held; GNM lower-face expression comps, small prior; eyes=True adds eye-region comps, which can fight the lid pose) and stores it per view in the
   references; every later look / focus / table / lid read / camera refit draws the clay WITH that picture's
   (lower-face) expression on top of the head's own (the eye step's eye-region expression); the model itself stays neutral. Fit it once the big forms are in (on the class mean it would soak up
   identity: block_in_start(expression=True) only for pictures you know are neutral-ish), and refit after big
   identity moves (the reply's chi2 says how much the expression explains). clear=True drops them.
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
A feature that no direction can reach is a vocabulary gap (below), not a reason for a big step. First ask the atlas
which GNM controls move it (`gnm_controls(query="bridge walls")`), then SCULPT it (macros held), and only then a local.

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

## GNM's controls (the atlas: gnm_controls)

Every way to move GNM's head, measured (gnmcontrols, 2026-10-10): 170 identity comps + eyes 3 + teeth 80, the region
principal directions (pc:), 100 symmetric eye-region and 150 lower-face expression comps + tongue / pupil, the joints,
the identity sampler's 64 latents (+ 16 principal latent directions) and its labels (sex, 4 ethnicities), the
expression sampler's 20 class prototypes, and our block-in moves. For each: where it acts (50 named zones: alar_crease,
vermilion borders, jowls, lid_fold, bridge_walls ...), mm per unit of prior cost, how local it is, the macros it drags,
its face-ID effect, the nearest block-in move, and its sheet (workspace/human_renders/gnm_atlas/<family>_<page>.png:
-2 | 0 | +2 front / 3/4 / profile in hair-cap clay + the move's map; index.html lists them all).
What it taught (use it when choosing a step):
- GNM's identity comps are WHOLE-FACE: median specificity 1.5 (the moved zone vs the face's rms), at any index; no
  single comp is "the alar crease". A local feature is a COMBINATION: that is what sculpt solves for.
- Per unit of prior cost the most identity-laden moves are the ORBIT / BRIDGE complex (bridge_height, eye_depth,
  orbital_rim, brow_ridge, nose_projection: face-ID 0.15-0.19 per sd): steps there change who it is fastest.
- Per mm moved, the fine comps (120-169: 0.04 mm per unit) are 5x as identity-laden as the first ten.
- The identity sampler's latent space is a GENERATOR, not a fitting space: our people and GNM's own N(0, I) heads
  are not on its 64-d manifold (residual > |c|); its labels are clean whole-face directions (label:sex, label:white
  narrows and steepens the bridge, label:asian / black widen it).
- The expression sampler's 20 class prototypes are data-backed whole-face expressions (eyes and mouth together: happy
  squints the eyes): the vocabulary for a picture's expression.

## Tool reference

### `gnm_controls`
gnm_controls(query="", control="", families=None, top=12, sort="score", per_family=0, sign=0, zones=False): the atlas.
- query: a feature in words ("alar crease", "jowl", "lip border", "bridge walls", "lid crease", "tear trough") or a
  zone name -> the controls that move it, ranked by sort: score (mm per unit of prior cost x specificity, capped at 4:
  the cheapest, most local movers; default), efficiency, local (mm per unit), specific, perc (face-ID), relief (the
  zone against its surround: deepening / softening a line). sign +1 / -1 keeps controls whose + moves it out / in
  (with relief: rises / sinks). per_family=k: the best k of each family instead of one ranking.
- control: one control described: its zones, macros, face-ID, nearest block-in move, sheet.
- zones=True: the zone list.
Each row: control | family | local mm per unit | mm per unit prior cost (its |coefficient| per unit) | specificity |
relief | out / in | face rms | face-ID | macros dragged (sd per unit) | nearest block-in moves | sheet. Act on it with
block_in_step: `"gnm:<control>": amount` (identity controls) or `"sculpt:<zone>": mm` (a combination, macros held).

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
- moves: {direction: amount}: macros free / held (`name!`), `nd:<gap>`, `sex`, `eth0..2`, `pc:<region><i>`,
  `gnm:<control>` add (amount in sd); `sculpt:<zone>` / `relief:<zone>` add the least-cost GNM move per mm (macros
  held; the reply gives its |dc|, the macros let go and the skin moved elsewhere);
  `head_scale`, `gnm_base`, `dimorphism`, `weight`, `lid_upper`, `lid_lower` are SET. An unknown name lists the
  vocabulary.
- out: the new model's name (default: name with its number + 1, or name_01); an existing name is refused.
- seen: the biggest difference you named; why: why this move answers it. Both logged.
- cameras: view indices whose camera to refit on the result head (camera only, the head held), e.g. a painted view
  whose camera fitted poorly, or after a head_scale change.
- look=False returns the text only. Reply: |c| before -> after, the moved macro's read, the largest coupled moves,
  the target pass counts before -> after, the items that changed, and the new sheet (with before | after | change
  rows: a half-sd step is hard to see beside the photo alone) + table.

### `block_in_expression`
block_in_expression(name, out=None, views=None, clear=False, seen="", why="", look=True, save=None): a round that
changes no shape: a new model (out) whose references carry each picture's fitted expression (views: default every
view with a detector, |yaw| < 70; a profile's few clicks can't separate expression from shape). Reply: per view chi2
before -> after on the detector points, |e| and the largest comps, then the table delta and a sheet before (neutral)
| after (with the expression). Stored in human_refs.json "expressions" (one {GNM expression comp: value} per view,
{} = neutral); blockin.view_base(base, refs, vi) gives the head as that picture shows it.

### `lid_read`
lid_read(name, match=False, out=None, seen="", save=None): the picture's lid margins against the iris (MediaPipe iris and
lids, in iris radii: upper MRD1-like, lower MRD2-like, the opening's aspect) and the model's (its front render, the
visible eyeball through the iris centre). match=True: the EYE STEP (loop, 7): identity + GNM eye-region expression
solved for the margins and the fold line, a new block-in step (out, seen as block_in_step); returns the focus=eyes
sheet (before | after) and the solve's report (picture vs model before / after: lids, visible platform, crease depth
and height, |dc|, |e|). ~4 min. match="pose": the older lid pose offsets (lid_upper / lid_lower, metres).

