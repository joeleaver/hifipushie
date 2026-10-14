# Block-in: tool reference

## Tool reference

### `gnm_controls`
gnm_controls(query="", control="", families=None, top=12, sort="score", per_family=0, sign=0, zones=False, phrase="", ruler=""): the atlas.
- query="mm": the 23 millimetre measures (`mm:<measure>` moves): what + looks like, the view to read it in, its
  population sd. ruler="modelA,modelB": the RULER between two models' GNM identities (B - A in mm and sd, largest
  first, each row with the `mm:` move that closes it): e.g. an earlier round, or a head you liked, as the target.
- phrase: a DIFFERENCE you see, in an artist's words ("the muzzle stands forward in profile", "pupils further apart",
  "double chin", "eyes and brows sit lower over the nose") -> the driving manual's best entries (guide topic
  gnm_driving: the control, its sign, mm per unit, what to hold, what it drags, the phrases it is confused with).
  Start here when you have named a difference; block_in_step's reply also lists them for its `seen` text.
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
replace=False, save=None, expression=False, attach="native", carry=False): the block-in's first model.
- refs: a one-mesh human whose pictures are fitted (`human_reference` wrote its human_refs.json: views + cameras):
  its body is taken (body = keys merged over it, e.g. {"weight": 0.3}); or a views list ([{"image", "size", "yaw",
  "points"}] as human_reference) with age / sex / body for a new body, cameras fitted on the new head.
- sex: "male" | "female" | 0..1 (default the body's): the base is that sex's class mean in GNM's semantic sampler.
- attach: "native" (default): GNM's own head: true base, its eyeball / mouth / teeth, its own size (x the stature's
  allometry: `base.head.size`), the body fitted (stature exact, the neck base laid on GNM's). Head keys with no
  meaning there are dropped and named (`base.style.human.head_size`, `base.head.scale` ...). "body": the old
  body-carried head; then gnm_base: default by age (0.5 to 25, 0 from 50, linear between). gnm_base with
  attach="native" is refused (it IS the true base).
- carry: False (default): the refs model's `strokes`, `skin.folds`, `skin.fold_expressions` are removed and
  `skin.wrinkles` set to {"amount": 0}: a new head has nothing of ours on its surface (garrett_a1's nine sculpt
  strokes once rode unseen on every head started from it). True keeps them. The reply's DROPPED line names every
  key removed, its LEFT line what stayed of the refs model's dressing (skin tone / zones / paint layers / micro relief).
- age: overrides the body's age.
- ethnicity: one of GNM's sampler classes (middle_eastern, asian, white, black) for that class mean; omit it unless
  you know it (eth0..2 steps can move along the contrasts later).
- cameras: "keep" the refs model's fitted cameras; when its head stood at another size or place (a body-carried
  head under a native start: one was 0.85 of GNM's size) they are CARRIED by the two heads' similarity (each view
  and its yaw kept; the reply says "carried ... x1.21"). "refit" refits them on the new head by its landmarks
  (camera only). Either way the first block_in_solve lays them on the head (its cameras="refit", by itself).
- name must be new (replace=True overwrites); the log (blockin_log.json) lives in this model's folder and every
  later step appends to it. save: the sheet's path (default in the workspace's human_renders).
Returns the first sheet and target table. The rest mouth is closed by GNM's expression (head.lip_close; lip_seal and
mouth_gap dropped), see 7c.

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
  is that feature's checklist rows (+ the lid read for eyes). Default save: the workspace's human_renders
- read / keep: log your ZOOM-OUT verdict on the step that made `name` (the log keeps both reads: the step's `seen`
  is the zoom-in read).

### `block_in_step`
block_in_step(name, moves, out=None, seen="", why="", cameras=None, look=True, save=None, feature=None): one round.
- feature: the feature this step is for (a feature pass round): the reply also carries its focus sheet (before |
  after) and its own rows, and the log records the feature's pass count before -> after.
- moves: {direction: amount}: macros free / held (`name!`), `nd:<gap>`, `sex`, `eth0..2`, `pc:<region><i>`,
  `gnm:<control>` add (amount in sd); `sculpt:<zone>` / `relief:<zone>` add the least-cost GNM move per mm (macros
  held; the reply gives its |dc|, the macros let go and the skin moved elsewhere);
  `weight`, `lid_upper`, `lid_lower` are SET; `head_scale`, `gnm_base`, `dimorphism`, `eye_size` are SET on a
  body-carried head and REFUSED on a GNM-native one (they do nothing there; the refusal says why). `neck_mm`: the
  neck's girth at its narrowest in real mm (native heads; the least identity change, the head's size and the face's
  measures held; the reply gives |dc|). `{"attach": "native"}` alone: the head switched to GNM-native, its cameras
  carried onto the new size and place, dead keys dropped and named. An unknown name lists the vocabulary.
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

### `block_in_solve`
ONE JOINT STEP: face_ruler's solve over every reference view (skin outlines + the one-sided skin | hair edge, irises, limbus, lid margins, lip borders, MediaPipe's mesh for eye contours / mouth corners / lip seam and border; GNM's prior on the whole identity; cameras under a prior) applied whole as a block-in step, the solve's cameras kept. Use it FIRST from block_in_start's head, 3-4 calls until |dc| < 2, instead of closing measures one at a time. cameras: "free" | "trust" (a third of the freedom) | "refit" (cameras fitted on ANOTHER head: laid on this one first; first call only): a PRIOR on each camera's whole move since the start (shift, scale, roll, yaw, pitch, distance), never a clip; a view with a known lens (lens_mm / EXIF) keeps its distance to +-7 %. detector: "mesh" (default: MediaPipe's mesh as absolute reads of the features it is good at) | "anchors" (its 68 landmarks as differential anchors, as before). dense: "off" (default) | "on" (our dense landmark network: a coarse read on real faces). hair_edge: "on" (default) | "off". anchors: "differential" | "absolute" | "none". chin_points: "auto" (default: the detector's chin points are left out when the set has a side view, 60 deg or more) | "on" | "off". parse: "auto" (outlines from the face parser where the plain-background reader finds too few) | "on" | "off". Nothing is forced: a component that would pass 3 sd is held at the bound (AT THE BOUND in the reply), no read is down-weighted for it. The reply lists OUTLINE READS per view (NO OUTLINE warns), the CAMERA lines, DISAGREE (read groups left past 2 sigma), what MOVED WITH NO READ, what moved far on a weak read and what is unread (treat those as inferred), a view whose stated kind disagrees with its fitted camera, and a DAMPED step. hold: "none" (default) | "auto". expression: "none" (default) | "view" | "shared" (the pictures' expression as a nuisance; did not validate). It does not see the surface inside the silhouette (cheeks), nor the chin's own width and the jaw's lower edge from front / shallow views. Parameters: name, out, share, seen, save, cameras, anchors, chin_points, parse, hold, expression, size, neck, dense, detector, hair_edge. See section 3b.
SIZE: the head's OVERALL SIZE is not something a picture reads (a bigger head further away is the same
image; every camera's scale and distance are free), so the solve HOLDS it at the block-in's start head's (the class
mean on that body) and leaves shape free: `size="held"`, the default; the reply's notes say so. Left free
(`size="free"`) it drifts with GNM's width / size component (-3 % .. +8 % on test heads).
`size="iris"`: the front picture's iris against GNM's mean limbus (GNM's eyeball is absolute: 6.0 +- 0.44 mm) pulls
it weakly (weight 0.34 against GNM's +- 5 % spread of size: combined +- 4 %), where the iris is at least 12 px in
radius and the head has GNM's own eyeball; `size="iris_pin"`: the iris' size whole (an average iris assumed; the
chain see-saws a little). `blockin.iris_size(name)` gives the check without solving ("an average iris says the head
is x % against its size now"). Do not compare two solved heads' millimetres without it: size first.
NECK (native heads): the neck's girth is not read directly by any picture, and GNM's identity moves it
36 mm per sd (its female class mean is 363 mm, 11 % over ANSUR II's 330 +- 18; its male 385 against 398 +- 25). The
solve carries an anthropometric PRIOR on it: `neck="prior"`, the default: ANSUR's mean for the model's sex and stature
with ANSUR's own sd (a row in the solve, as size is). It is a prior and not a hold on purpose: on known heads the free
solve finds the true neck to 13.5 mm rms through GNM's correlations with the jaw it does read, the prior keeps that
(14.3) and a 1 % hold at the mean loses it (31; lower face +0.9 mm on a thin-necked head); face / lower face / chin
shape errors 2.17 / 2.45 / 1.82 mm without the term, 2.03 / 2.23 / 1.57 with the prior. `neck="held"` pins the mean
(+- 1 %), `neck=<mm>` holds a girth you measured, `neck="free"` releases it. The reply has a line "NECK: girth a -> b
mm ... no direct read (INFERRED)". A body-carried head has no neck term (its neck is the body's). Outside the solve:
`block_in_step {"neck_mm": mm}` (the least identity change, size and the face's measures held).
HEAD SIZE on a native head: GNM's own metres x `base.head.size`, by default the stature's allometry (ANSUR: head
height goes as stature ^ 0.29 women / 0.24 men; 1.000 at 1.627 / 1.755 m); the solve's size hold keeps the IDENTITY's
size at the start head's on top of that, and the reply says so ("HEAD SIZE: ..."). `blockin.iris_size` (the iris as a
ruler) reads in real millimetres there.
CAMERAS OF ANOTHER HEAD: the solve first measures whether the cameras belong to this head (its landmarks through them
against the pictures' stored points). A head switched to native by an edit is refused with the step that carries
them (`block_in_step(name, {"attach": "native"})`); cameras carried or refitted by block_in_start are laid on the head
by the first call (`cameras="refit"` in place of "free", said in the reply; "trust" is honoured).

### `lid_read`
lid_read(name, match=False, out=None, seen="", save=None, expression=False, donor=None, fold=None): the picture's lid margins
against the iris (MediaPipe iris and lids, in iris radii: upper MRD1-like, lower MRD2-like, the opening's aspect) and
the model's (its front render, the visible eyeball through the iris centre): a quick look, biased (the detector's iris
centre is ~1 mm low); the numbers to trust are `eye_ruler(name)`'s. match=True: the EYE STEP (loop, 7), IDENTITY ONLY:
the orbit check (ORBIT: UNREAD / OFF / read: set the orbit first), the opening solved for the RULER's margins (7
columns, mm) and canthi (the detector's two lid points in iris radii only when the picture's iris is under 30 px), the
lid as one structure on GNM's lid rings (fold="crisp", the default: recipe A, a designed crisp fold on the picture's
fold line, brows and measures held; fold="donor" / donor="s376" | "s540" | a block-in model's name: toward that lid)
with the eyeball guard; a new block-in step (out, seen as block_in_step); returns the focus=eyes sheet (before | after) and the report.
expression=True adds GNM's eye-region expression to the opening's solve: only for a real pose (a squint). ~5 min.
match="pose": the older lid pose offsets (lid_upper / lid_lower, metres).

### `eye_ruler`
eye_ruler(name, model=None, save=None): the front picture's eyes against the model's mesh, in mm at the model (the
fitted camera's mm / px), each eye in its own frame: origin = the iris centre, u toward the outer corner along the line
through both iris centres, v up; both eyes' mean. Rows: iris diameter (limbus circle), pupils apart, inner canthus (the
caruncle's tip; model = GNM's lm68 inner corner), outer canthus (where the visible eyeball ends), fissure length,
canthal tilt, the upper and lower margins at u -6 / -3 / 0 / 3 / 6, the opening at the pupil, mm of iris the upper lid
hides, where the upper lid peaks, the caruncle showing, the fold line / visible lid platform over the margin, the brow
hair's lower edge over the margin. diff = model - picture; * = beyond the tolerance (2 x the reader's rms error on 14
dressed fitted-camera renders of known GNM heads: iris 0.12 mm, margins 0.25, corners 0.45-0.63, fissure 1.0, tilt
1.8 deg, peak 0.6, brow 0.7). The lower margin's picture read has 0.35 mm taken off (it reads the waterline's top).
Not trustworthy: the fold line on a RENDER (a soft fold is not a line: +-3 mm; the model's crease is read from the
mesh instead) and on a photo whose line is fainter than 0.08; anything on a picture whose iris is under 30 px (a
NOTE says so). model=<other>: that model against `name`'s picture and camera (same refs). The returned image is the
picture's two eyes (nose side left) with its read drawn (green margins, red canthi, yellow limbus, cyan fold line,
magenta brow edge) and the model's margin ring / margins / inner-corner landmark in blue, laid over by iris centre.
MOVES name the tools: `lid_read(match=True)` (the eye step solves these margins and corners), `iris_mm` (GNM's limbus),
`mm:pupils_apart`, `skin.eyes.caruncle`, `brow_read(match=True)`. Python: eye_ruler.read(img, P, mmpx) on any picture
(a dressed render through the same camera reads the same way), eye_ruler.model(spec, cam), eye_ruler.compare(name).

### `face_ruler`
face_ruler(name, save=None): the block-in model against ALL its reference pictures, in millimetres. First the ORBIT
rows (loop 3a: eye depth as a side view shows it, each with its error; the cameras' solved yaw / pitch and which
limbus was read are in the notes under the table), then gnm_mm's 27
measures (the orbit's four rims and hollow, and pupils apart, eyes forward / height, brows over the eyes, forehead forward, nose tip / base forward, nose
length / width, upper / lower lip and chin forward, philtrum and chin length, cheekbone / jaw / chin / mouth / skull /
neck width, the vault's top and back, the line under the chin). Each row: picture - model (GNM's mm and population
sd), +- the reader's error, the move `"mm:<measure>": gap` for `block_in_step`, the view it shows in. Largest (in sd)
first. Rows inside the error say so; rows marked NOT READ are measures these pictures do not show (their number is
the population's guess from what was read: do not act on it).
How it reads (face_ruler.py): no detector landmarks and no eye. (1) Each picture's SKIN OUTLINE against a plain
background (the profile's forehead-nose-lips-chin-throat line, the 3/4's far brow / cheek / jaw, the front's jaw and
neck where hair does not cover them; hair, cloth and loose strands are left out: skin just inside the edge is required)
compared with the model's own silhouette through the same fitted camera, at 1.5 mm steps along it. (2) The iris
centres on the front picture (eye_ruler's limbus circle) against the model's. (3) One solve for the GNM identity
change that explains all of it under GNM's own population prior, each picture's camera left free by 2 mm / 5 % / 1.2 deg
(a camera fitted from the model's landmarks is that far off, measured) and refined between rounds; the 23 measures are
read off the solved change. So a row is not a caliper reading but the most likely value given every outline at once.
Errors (validated on pictures of known GNM heads; reader - mesh truth, rms mm): camera known: profile chain (tip, nose
base, lips, chin forward) 0.1-0.3, eyes 0.05-0.3, brows 0.2, philtrum / chin / nose length 0.2-0.6, mouth width 0.3,
nose width 0.9 (never seen directly: inferred), widths 1-1.8, skull 0.2-0.5 (1-1.8 under hair). Camera FITTED from
the model (a photo's case): profile chain 0.1-0.6, eyes forward / height 0.5-0.9, pupils 1.2, lengths 0.5-1.0, widths
2-3.6 and skull 1-3 (a fitted camera's scale is free: absolute size is the least known thing in a photo). The one
mesh takes the head's size from the body, so a uniform size gap is not in the table: `head_scale` is its own key.
On a BLOCK-IN model (the one mesh; dressed pictures of 8 known heads through real fitted cameras, hair masked, size
taken out): tip / upper lip / chin forward 0.4-0.6, pupils 0.8, under_chin 0.9, lengths 0.8-1.7, brows / eyes height /
forehead 1.1-1.2, eyes_forward 2.8 and subnasale_forward 2.0 (weak: 1.4-1.9x), widths and skull 2.3-5; NOT readable
there: neck_width, nose_width, lower_lip_forward, mouth_width (the table marks them). The table's +- is never under
these. Gaps are in GNM's mm = the `mm:` dose (the one mesh makes ~0.88 of GNM's move).
Limits: plain backgrounds only (no outline otherwise: the table says how many reads each picture gave); lips,
nostrils, brows' shape are not read on photos (eye_ruler / lip_read / brow_read do those); a non-neutral expression
moves the lips and chin rows. The returned image is the pictures with the model's outline (green, through the
refined cameras), the reads (yellow) and the iris centres (magenta picture, cyan model): check that yellow sits on
skin edges only. Python: face_ruler.compare(name); on any pictures face_ruler.read(head, views) with head =
gnm_head(c) or model_head(spec); clay pictures of GNM heads also read pupils, lip edges and brow tops by colour.

### `brow_read`
brow_read(name, match=False, out=None): the DRESSED brows (the skin's hair picture, skin.hair.brows) against the front
picture's brow hair, through its fitted camera, in mm at the model: the hair band's lower edge and middle line at 9
columns across each brow (half contrast against the skin; + = ours lower, toward the eye), a WARNING past 1.5 mm; and
the IRIS line: the picture's limbus diameter in mm at the model against the drawn iris (GNM's limbus for the identity,
or skin.eyes.iris_size), the `iris_mm` step that makes them equal (its eyes_000 in sd), the picture's iris colour. match=True fits skin.hair.brows' placement (drop, tilt, apart, fall, thickness,
taper; "lift" folded in) to the picture's band and writes it (out: another model; default in place). Paint only.
Why: GNM's brow landmarks are the ridge's, not the hair's; brows set by eye on one head travel with the dressing onto
the next and end up on the lid's fold (4-7 mm low on one head). Run it after the eye step, before judging a dressed eye.
An iris 1.18 x too big (where the lids are matched in iris radii: a picture under 30 px of iris) opens the eye 1.18 x
too tall and crowds the brow: step `iris_mm` to the picture's, then run the eye step again.

### `lip_read`
lip_read(name, match=False, out=None, seen="", save=None): the front picture's lips (the vermilion borders traced on
the a* edge from MediaPipe's outer lip contour, the seam between MediaPipe's inner contours, the Cupid's bow: peaks over
the centre trough, mm) against the model through the front camera (with the picture's fitted expression): border miss
upper / lower (rms mm, and the mean offset, + = the model's outside), seam miss, bow picture / model, the neutral's
contact gaps (max / median / min mm), the inner rolls' smallest gap (- = crossing: normal for GNM's closing, the
field leaves them out) and how the mouth is closed (lip_close / seal / mouth_gap / expression). match=True: the LIPS
STEP (loop, 7c), a new block-in step (out, seen as block_in_step); returns the focus=mouth sheet (before | after) and
the solve's report. ~3 min.
