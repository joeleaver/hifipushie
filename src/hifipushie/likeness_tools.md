# Likeness: tool reference

## Tool reference

The full documentation of this topic's tools: their MCP descriptions are the short form. guide(topic="<tool name>") returns one section. These tools are the `likeness` toolset: enable_toolset("likeness") turns it on.

### `likeness`

`likeness(name, targets=False, top=8)`

The likeness CHECKLIST on a one-mesh human against its reference pictures (human_refs.json, from
human_reference): ~50 facial features in artists' order (proportions, face widths, eyes, brows, nose, mouth,
chin / jaw, ears; guide(topic="likeness")), each MEASURED the same way on the photo and on the model through the
picture's fitted camera (MediaPipe's 478 points on the photo and on a clay render of the model, so a detector's
definition errors cancel; the model's own landmarks as a second reading: '!' where they disagree). The reply: a
table ranked by miss / tolerance (beyond tolerance first), what can't be measured from these views and why
("profile needed", "judge by eye"), and FOCUS PANELS (photo | model at the same crop and camera, the feature's
points on both: red photo, blue model) for the top misses and the judge-by-eye items: look there, on purpose.
It leads with a one-glance COVERAGE: what these pictures support, what is inferred from a weaker view (profile
items from a three-quarter view, tolerance x1.5), what only by eye, what not and why, and each picture's problems
(lens, expression, light, ears / hairline). SHAPE items (planes, cheek hollow, folds, under-eye, brow ridge) are
read from the photo's shading against the model lit like the photo, with the model's own 3D number beside; the JAW's
L (ramus, gonial angle, lower border, neck step) from a trace (likeness_points) against the model's contour.
Turned views' cameras are refitted on the detector's points; the residual per item is in the table.
targets=True instead measures the references alone and stores the target sheet (<model>/likeness_targets.json:
value, view, tolerance, confidence or "unmeasurable" per item) with the stage plan: what fit_likeness will do,
which items have a control and which are gaps. Measures only; never edits the model.

### `fit_likeness`

`fit_likeness(name, stage, force=False, save=True)`

ONE stage of the likeness fit from the checklist, in artists' order: "proportions" (face height, the thirds),
"widths" (the outline, level by level: fit_outline), "eyes" (spacing, size; hooded lids by fit_hood), "brows",
"nose", "mouth", "chin_jaw", "ears". The stage's items that miss beyond tolerance (front view) ask humanfit's
minimal-change solver for exactly those measures; every earlier stage's measures are pinned, so the nose can't
undo the widths. Integrity-guarded: a result that breaks the mesh is refused, not saved. The reply: the stage's
items before -> after, items with no solver measure (GAPS: what a person does by hand), earlier stages' items that
got worse, and the stage's focus panels. Approve each stage (look at the panels) before calling the next.
Run likeness(name, targets=True) first for the target sheet and the plan.
stage "profile": only the nose and the chin, fitted to a turned view's CONTOURS (likeness_points lines "profile" =
the far side of the face against the background, "nose" = the nose's own edge): GNM components inside the nose /
chin region moved until the model's own contour through that camera lies on the traced one, heights and widths
held where the front picture has them. The nose and chin_jaw stages run it too when the lines exist.

### `likeness_points`

`likeness_points(name, image, points=None, lines=None, by='', replace=False)`

Hand-placed points on a reference picture for features the detector can't find (stored in
<model>/likeness_points.json; the format onemesh2's traces use). Pixels of the FULL picture (u right, v down);
.R / .L = the subject's right / left. points: {"gonion.R", "ear_lobe.R", "tragus.R", "menton", "pogonion",
"jaw_notch.R": [u, v]}; lines: {"jaw.R": [[u, v], ...] (from just under the ear lobe DOWN the ramus, round the
angle, FORWARD along the lower border to the chin), "neck.R": [[u, v], ...] (the neck's contour under that border,
top to bottom), "profile": the far side of the face against the background in a turned view, forehead down round
the chin (snapped to the picture's edge when read), "nose": the nose's own edge in that view, from between the
brows down the bridge, round the tip, back to the columella's base}. Merged name by name (null deletes one) unless replace. The jaw items (ramus angle, gonial angle,
lower border, gonion against the ear lobe and the mouth, the neck's step) read them; the focus panels draw them.

### `character_read`

`character_read(name, tag='', read=None, view='', render=False, author='llm')`

Stage 0 of the likeness checklist: the CHARACTER READ (what a person knows from one look: "square jaw, strong
chin, straight nose"), as a form of gestalt descriptors, each bound to bands on checklist items in every view.
- character_read(name): the form to fill while LOOKING at the reference pictures.
- character_read(name, "reference", read={"descriptors": {id: {"confidence": clear|likely|hint, "picture", "note"}},
  "summary"}): store the references' read (the prior). author="user" when the read is the USER's own words
  ("chunky, square jaw, cleft chin, cute nose"): theirs wins group by group, and where it differs from the LLM
  reader's the reply lists QUESTIONS to ask them (never settle those silently).
- character_read(name, render=True): a sheet of the model from each reference camera and from views no reference
  shows (both profiles, the other three-quarter, low angle). Give that sheet and the form to a reader that has NOT
  seen the references (a fresh agent), one read per panel, and store each: character_read(name, "<tag>", read, view).
- character_read(name, "<tag>"): the diff, reference vs the model's blind reads view by view (kept / CONTRADICTS /
  missing / adds, and the controls the read needs that we lack). Read it before the millimetres.

### `project_reference`

`project_reference(name, view=0, save='')`

The fastest honest judge of a fitted head's GEOMETRY: reference picture number `view` (of the model's fitted
references: human_reference first) projected onto the model through its fitted camera as an unlit texture, then
shown from the reference cameras, both profiles, the other three-quarter and a low angle. A clay bust beside a
photo of a skinned, haired person compares two different things; this compares like with like. Where the
likeness holds when the head is turned, the geometry carries it; where the picture smears, doubles or slides
(ears landing on cheeks = the face too narrow; the nose's side, the jaw's edge, the chin in profile), the
geometry is wrong THERE. Skin the reference's camera does not see is dim clay. The picture's own light is on the
surface: judge outlines and proportions in turned views, not shading.

### `texture_from_reference`

`texture_from_reference(name, views=None, opacity=0.9, delight=True, match='tone', remove=False)`

The fitted reference pictures as the head's ALBEDO (the projection test, kept as paint): each picture is
projected onto the model through its fitted camera (human_reference first), its light taken out roughly (one
fitted light on the model's own normals), and laid over the skin as an ordinary paint layer "ref_texture_<view>"
(an image decal along that camera's axis, colour = the image, alpha = how far to trust it).
What is the picture and what is ours: the PICTURE gives colour where its camera saw skin square-on (zones, brows,
stubble shadow, lips, lines: at the picture's own resolution, said in the reply); OURS stays on ears, under the
chin and nose, hair, eyeballs, skin turned away, neck and body, and for ALL relief, roughness and scattering (the
skin description's pores and highlights still shape the surface). Cast shadows and a painter's strokes stay in:
use a photograph with even light; a painting's brushwork lands on the skin.
views: which of the model's fitted pictures (default all with an image; each later one lies OVER the earlier:
list the most trusted last). opacity: the layer's strength. delight=False keeps the picture's light.
match: "tone" (default: the picture's median skin colour is brought to the skin description's tone, so the
picture gives its variation and the join with the procedural skin doesn't show), "level" (lightness only), ""
(as de-lit). remove=True takes the layers out.
The decal is made on the head's shape as it is NOW: after any change of the head's shape call this again (a
stale layer is reported by name). Then sync + look, or look_skin.

### `reference_brief`

`reference_brief(kind='head', subject='')`

The REFERENCE BRIEF derived from the likeness checklist, for references we generate or ask for: the shot list
(front, true left profile, three-quarter, the side-light passes for the planes, optional back and top; kind
"figure" adds full-body A-pose front and side for the body's proportions), what each shot must show (long lens at
eye height, neutral closed mouth, eyes level, even soft light + a side-light pass, plain background, hair off the
ears and hairline, the same identity / light / scale in every view, nothing over the features), which checklist
items each serves, and the prompt wording for an image generator per shot (one shared identity block).

### `check_references`

`check_references(images, name=None)`

What a set of reference pictures can and can't support for the likeness checklist, and why: the views present
(the detector's head pose), the lens (a fitted camera's focal, with `name`: the model's human_refs.json), the
expression (the detector's blendshapes: smile, mouth open, squint, raised or furrowed brows), the light's evenness,
ears / hairline covered (a colour heuristic), and identity consistency between views (vertical proportions that
don't change with the head's turn). Ends with which reference_brief shots to ask for.
