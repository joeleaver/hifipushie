# hifipushie tools: toolsets and the core reference

The server's tools are grouped in toolsets. A session starts with the core; `enable_toolset(name)` adds a set (the
client refreshes its tool list on the server's list_changed notification: Claude Code does, within the same turn;
in Claude Code a new tool may be deferred: find it with ToolSearch), `enable_toolset("")` lists them and which are
on. Before working in a domain, enable its set and read its guide topic. Hosts that don't refresh: start the server
with `HIFIPUSHIE_TOOLSETS=all`, or a list like `hair,cloth` (default `core`); `HIFIPUSHIE_CALL_TOOL=1` adds
`call_tool(name, args)`, which runs any tool, enabled or not.

| toolset | holds | full docs |
|---|---|---|
| core | guide, enable_toolset, list_models, get_model, kit_reference, put_model, edit_model, look, check, measure, history, revert | here |
| plan | set_plan, set_reference, compare, fit, clearance, style_check | here |
| scene | sync, pull, heavy_status, heavy_queue | here |
| export | export, export_asset, rig | here |
| human | human, measure_human, fit_human, nudge_human, human_reference, block_in_start, block_in_look, block_in_step, lid_read, skin, look_skin, skin_reference | guide(topic="human"), guide(topic="block_in"), guide(topic="skin") |
| likeness | likeness, fit_likeness, likeness_points, character_read, project_reference, texture_from_reference, reference_brief, check_references | guide(topic="likeness") |
| hair (+ scene) | groom_hair, look_hair, hair_reference, export_hair | guide(topic="hair") |
| cloth (+ scene) | design_garment, look_pattern, check_garment, dress, look_cloth, garment_reference, garment_from_reference, check_garment_reference, garment_reference_brief | guide(topic="cloth"), guide(topic="cloth_reference") |
| terrain | set_terrain, check_terrain, look_terrain, export_terrain, terrain_history | guide(topic="terrain") |
| plants | grow_plant, edit_plant, get_plant, look_plant, look_plants, plant_form, plant_reference, export_plant, wind_plant, sync_plant, plant_history, grow_stand, look_stand, export_stand | guide(topic="vegetation") |
| clutter | make_clutter, look_clutter, clutter_kit | guide(topic="clutter") |

Every tool's MCP description is the short form; its full text (parameters, behaviour, timings) is a section of the
topic named above, and guide(topic="<tool name>") returns just that section.

## Tool reference

The full documentation of this topic's tools: their MCP descriptions are the short form. guide(topic="<tool name>") returns one section. These are the core, plan, scene and export toolsets.

### `guide`

`guide(topic='')`

The hifipushie playbook: how to work in stages (plan, blockout, secondary forms, detail), rules for
strokes and parts, how to judge renders and diagnose artifacts. Read it before modelling.
topic="terrain": the terrain vocabulary (landscapes and game levels in a level designer's words: world kinds,
basins, passes, canyons, sites, routes, walls, cover, intent checks), for set_terrain and the other terrain tools.
topic="hair": stylised hair as sculpted locks, the way artists groom it (silhouette, big shapes, clumps, breakup),
with groom_hair, look_hair, hair_reference and sync(hair_only=True).
topic="cloth": garments the way pattern makers and garment artists make them, in stages (design sheet, flat
pattern and its checks, construction plan, arrangement, draft, final), with design_garment, look_pattern,
check_garment, garment_reference, dress, look_cloth and sync(cloth_only=True).
topic="cloth_reference": reading garments from reference art as tech designers, tailors and garment artists do
(the checklist, big to small), with garment_from_reference, check_garment_reference and garment_reference_brief
(the shot list for getting good references, and a validator for a set of pictures).
topic="skin": human skin the way character artists texture it, in stages (base tone, colour zones, large
features, fine features, micro detail, cosmetics, shading check), with skin, look_skin and skin_reference.
topic="vegetation": trees the way vegetation artists make them (a species' habit, age and setting grown, then
limbs drawn and pruned, judged against a photo, foliage and bark, export), with grow_plant, edit_plant,
look_plant, plant_reference, export_plant and plant_history.
topic="human": whole people on ONE mesh (human(source="human")) and how to measure and fit them without breaking
what you weren't looking at: measure_human, fit_human (set measures, a solver finds the sliders), nudge_human
(move a landmark), human_reference (match named points in reference images), with integrity and side-effect
reports on every change.
topic="block_in": THE DEFAULT for a person's head from pictures: the artist block-in loop (a base of the right kind,
an eye-registered sheet beside the pictures, one small whole-face step a round, a target table, lids by measure), with
block_in_start, block_in_look, block_in_step and lid_read.
topic="clutter": the small things a terrain is scattered with (boulders, river rocks, cobbles, slabs, driftwood,
bushes, litter, reeds) as game assets in five styles, with make_clutter, look_clutter and clutter_kit.
topic="likeness": the facial-likeness checklist (forensic examiners' feature list, likeness artists' order,
anthropometry): what to look at and measure on a reference, for the likeness and fit_likeness tools.

### `enable_toolset`

`enable_toolset(name='')`

Add a toolset's tools to this session (the server may start with only the core). name: a toolset or a comma
list, "all"; "" lists the toolsets, what each holds and which are on. The new tools appear after the client
refreshes its tool list (notifications/tools/list_changed); if they don't, restart with HIFIPUSHIE_TOOLSETS.

### `list_models`

`list_models()`

List saved models.

### `get_model`

`get_model(name)`

Return a model's stored spec (JSON) plus a measurement summary.

### `kit_reference`

`kit_reference()`

Parameters and defaults for the kits (hand, face), strokes (clay, crease, flatten), paint and plans.

### `put_model`

`put_model(name, spec, note='')`

Create a model or replace its whole spec. Missing keys get defaults. The stored plan (set_plan) is kept
unless the new spec gives one, or "plan": null to drop it. Returns a summary.

### `edit_model`

`edit_model(name, ops, note='')`

Apply a batch of edits atomically. Ops:
{"op":"set","kind":"joints|bones|blobs|kits|strokes|paint|parts|anatomy|prefabs|instances|...","name":n,"value":{...}}
    merge fields, creates if new; a null field removes it. kind is any top-level key holding named entries.
{"op":"set_key","key":"story|style|rig|weather|...","value":v}  replace a whole top-level key; null removes it
{"op":"delete","kind":...,"name":n}
{"op":"rename","kind":...,"name":n,"to":m}  joint/bone renames update references
{"op":"move","joints":[names],"delta":[dx,dy,dz]}   shift a group of joints (e.g. a whole leg)
{"op":"scale_r","joints":[names],"factor":f}         thicken/thin at those joints
{"op":"global","value":{"blend":0.04}}
Edit only ".L" and centre elements; ".R" follows automatically.

### `look`

`look(name, views=None, size=448, grid=False, focus=None, zoom=1.0, resolution=160, matcap='clay_studio.exr', strokes=False, shading='clay', paint=True, paint_layer=None, hide_parts=None, only_parts=None, clip=None, camera=None, instances=False, save=None)`

Build the mesh and return a clay contact sheet.
views: any of front, side, top, three_quarter (default set), back, left, three_quarter_back, below.
All panels share one scale; front/side/top get rulers in world units (grid=True adds grid lines).
focus=[x,y,z] + zoom>1 for close-ups (e.g. the face). resolution = voxels across the longest axis
(160 is quick; 256-320 for detail). In a close-up, resolution counts across the region around the
focus instead, so small features (lids, lips, fingers) get proportionally finer voxels; parts outside
that region are left out. strokes=True draws every stroke's path on the views (orange clay, blue crease,
green flatten, named at their start; hidden parts left out): check placement before judging form.
shading: "clay" (soft studio matcap), "raking" (one low light from the left: shows shallow forms, planes
and dents the clay hides), "curvature" (warm = convex, cool = concave, grey = flat, stronger = tighter:
an evenly tinted area is blobby; crisp forms show as bright lines), "flat" (unlit colour: judge paint).
paint: show the spec's paint layers (default); False shows plain clay per part.
paint_layer: show that one layer's mask in false colour instead (purple 0, teal 0.5, yellow 1), to see
where a mask stack lands before judging colours.
hide_parts / only_parts: leave those parts out / show only those (no rebuild; "hair" hides the hair's locks): the body under clothes, the
inside of a house without its roof, one part alone. With only_parts the views frame the parts shown.
clip: cut the model with a plane and drop what's beyond it, e.g. {"z": 2.2} drops everything above
z = 2.2 (a plan view of a house: use views=["top"]; a torso cross-section), {"-y": 0} drops everything
with y < 0 (the front half, seen from the front), {"x": 0} the +X half; any plane: {"point": [x,y,z],
"normal": [x,y,z]} drops the side the normal points into; a list applies several. Cut solids get flat
caps in their part's colour, darkened, so walls read as walls. Views keep the uncut model's framing.
camera: a perspective panel from inside or around the model: {"eye": [x,y,z], "target": [x,y,z],
"fov"?: degrees across (default 70), "name"?}. eye [x, y] stands a person there: on the lowest floor with
1.8 m of headroom, eye 1.6 m above it ("eye_height" to change); target [x, y] looks level at eye height.
A list gives several panels. Alone it replaces the default views (views adds orthographic ones back).
Perspective panels have no rulers (sizes change with depth) and no stroke overlay.
Painted looks (paint=True, shading "clay" or "flat", no strokes; clip and close-ups too) are rendered from the model's
Blender scene (synced first: see `sync`) in EEVEE with real lights; paint_layer then shows that layer's
mask glowing orange on grey clay. Painted clips leave out what's beyond the plane (it casts no shadow either)
and cap the cut solids; painted close-ups frame the scene's own meshes. The geometric views (raking,
curvature, strokes, instances) show plain clay per part; shading="clay" with paint=False gives clay clips and
close-ups at the build resolution.
instances=True marks every placed prefab instance on the orthographic views: a dot at its origin, an arrow
along its front (the prefab's local -Y: build prefabs facing -Y, like creatures) and its name. With a top
view (and a clip) it's the floor plan with which way each piece of furniture faces.
save: also write the contact sheet to this PNG path (to show someone who can't see tool images).

### `check`

`check(name, resolution=160, save=None, only_parts=None, hide_parts=None)`

Check the model against its plan: per view, the plan against the model's silhouette (grey = both,
blue = plan only: the model is missing it, red = the model sticks out); IoU and edge-error bands in world units (placed exactly, no rescaling); landmark joints vs
their planned heights; planned sections vs measured width and depth. Run it after every stage.
Always also audits realism: missing story, identical copies at even spacing, things square to the axes,
identical parts, big perfectly flat faces, paint without wear or dirt (works without a plan too).
And walks a person through every doorway (box cuts with targets reaching the floor, 1.6 m+ tall): a door
swung across the opening, furniture in the way, a step too high; names what blocks it. And lists props
(instances) cutting into anything else, how deep and into what (a chair pushed into a table leg).
only_parts / hide_parts: which parts the silhouettes count (judge the body, not the prop it holds); default:
the plan's "parts" (a list of part names), else all.

### `measure`

`measure(name, along, samples=11, lo=None, hi=None)`

Cross-section sizes as numbers, from the exact field (independent of build resolution).
along = a bone name or a list of bones (a chain, e.g. a tail or leg): planes perpendicular to each bone
at `samples` evenly spaced t, giving the distance from the axis to the surface on each side (w-/w+ along
the bone's width axis, h-/h+ along its height axis; compare with joint radii) and the connected section
area. Use it to find pinches, bulges and lumps along a limb.
along = "x" | "y" | "z": planes across that world axis (optionally only between lo and hi), listing every
separate part in each slice with its ranges on the other two axes, e.g. "y" gives body width and
height from nose to tail, "z" shows where the legs merge into the body.

### `history`

`history(name)`

List saved versions of a model.

### `revert`

`revert(name, version)`

Restore an earlier version (saved as a new version, so nothing is lost).

### `set_plan`

`set_plan(name, plan, note='', save=None)`

Set (or replace) a model's plan: the 2D blockout you model against. Creates the model if it doesn't
exist. Returns the plan drawn with rulers, so you can check proportions before modelling anything.
plan = {"views": {"front"|"side"|"top": {"shapes": {name: shape}}}, "landmarks": {name: {"z", "joint"?}},
        "sections": {name: {"z", "near": [x, y], "width", "depth"}}}
shape = {"ellipse": [cu, cv, ru, rv], "rot"?} | {"capsule": [u0, v0, u1, v1], "r": r | [r0, r1]} |
        {"poly": [[u, v], ...], "smooth"?: true}, plus "op": "subtract" to cut out. u, v are the view's
world axes (front X,Z; side Y,Z with the creature facing -Y; top X,Y); ".L" shapes mirror in front/top.
kit_reference has the details.

### `set_reference`

`set_reference(name, view, image_path, flip=False, threshold=40.0)`

Attach a reference image for view "front", "side" or "top". The silhouette comes from the alpha
channel if present, else from difference against the corner background colour (threshold).
Our side view shows the creature facing LEFT; set flip=True if the reference faces right.
Returns the extracted mask so you can check it.

### `compare`

`compare(name, views=None, fit='auto', resolution=160, against='auto', only_parts=None, hide_parts=None)`

Compare model silhouettes to the references. Per view: IoU, a diff image
(grey = match, red = model has extra, blue = model is missing) and band tables of edge errors
in world units, which tell you which joint/blob to move and by how much.
fit: "auto" searches the reference scale/offset for best overlap, so only shape differences remain
(absolute size is ignored); "height"/"width" instead match that dimension, bottom-aligned.
against: "refs" (set_reference images), "plan" (the model's plan, placed exactly: no rescaling), or "auto"
(the plan if there is one). only_parts / hide_parts: which parts the silhouette counts (the body without the
prop it holds); default: the plan's "parts", else all.

### `fit`

`fit(name, views=None, only=None, lock=None, params=None, iterations=20, max_step=0.02, stiffness=0.05, align='auto', resolution=160, against='auto', only_parts=None, hide_parts=None)`

Auto-fit the model to its reference silhouettes and save the result as a new version.
Moves joints, joint/bone radii, blob offsets and blob sizes (params: any of "pos", "r", "offset",
"size") to minimise the distance between model and reference outlines. Only what the given views can
see changes: a side-only fit leaves X alone. Details (subtract ops, layer>=1 blobs) stay fixed unless
named in `only`; `only`/`lock` take joint, bone and blob names. max_step caps any move per iteration (m);
stiffness is a spring toward the starting values (higher = more conservative).
Block out the body plan by hand first: fitting is local and can't fix a missing or misplaced limb.
against: "refs", "plan" (fit the blockout onto the plan's outlines, placed exactly; joints tied to plan
landmarks keep their planned height) or "auto" (the plan if there is one). only_parts / hide_parts: which parts
the silhouettes count, and whose elements may move (default: the plan's "parts", else all). Returns the diff images, IoU before/after and every change; `revert` undoes it.

### `clearance`

`clearance(name, region=None, path=None, floor=None, height=1.8, radius=0.25, step=0.2, spacing=None)`

Can a person walk here? Walkability of an environment from the exact field (vertical and horizontal rays;
independent of build resolution). Give one of:
region = [[x0, y0], [x1, y1]]: a top-view character map over that floor area ('.' a person fits, ',' floor
and headroom but within `radius` of a wall or object, 'h' headroom below `height`, '#' blocked: wall,
furniture, or less than half the height free, ' ' no floor at that level) plus walkable area, floor
flatness (spread, largest step between neighbouring cells) and least headroom. `spacing` defaults to ~60
columns across.
path = [[x, y], ...]: along the polyline every 5 cm, floor height, headroom and clear width (rays left and
right of the direction of travel at five heights above the floor), a table every 25 cm plus the narrowest
point and a verdict: does a person `height` tall and 2 x `radius` wide pass (doors: walk a path through).
floor: the level to stand on (z); default the most common height with `height` of free space above it.
step: floor bumps up to this count as floor (thresholds, rugs); more is an obstacle or a step.

### `style_check`

`style_check(name, colours=True, save=None)`

Measure a model against its style sheet's rules (spec.style.sheet; sheets: stylised_realist, ...). A sheet is a
reusable bundle of a style's decisions: base head fit/pose defaults, part settings (skin subsurface), paint
layers on the landmark joints, the look preset (lights) and the rules it was written from; the model's own spec
wins key by key (null deletes a sheet key). Rules measured: face ratios on the posed head (chin over philtrum,
nose and mouth widths), the eye opening (height/width, iris share, how much of the iris each lid covers) and,
with colours=True, skin saturation/hue lit vs shadow sampled from a front render in the style's look (syncs the
scene first; save= keeps that render). Each line: PASS/FAIL, value, target, why.

### `sync`

`sync(name, resolution=256, hair_only=False, cloth_only=False)`

Bring the model's Blender scene (workspace/<model>/scene.blend) in line with the spec, after taking back
what a person changed in it (moved/turned/scaled instances, exposed paint numbers: see `pull`). One object
per part and per prefab (collection instances), paint as shader nodes, AO and sky baked by Cycles (each
asset shades only itself; props never shade the building). Only what changed is redone: moving a prop is
~2 s, a paint change rebuilds only the parts it touches (a few s), new geometry is meshed and measured. Open the
.blend in Blender to look around and edit; the next sync or look brings the edits back.
Live: when the person's running Blender has this scene.blend open with the Blender MCP add-on's server started
(port 9876, or $BLENDER_MCP_PORT), sync and pull run inside that session: changes appear in their viewport as
they're made, their unsaved moves and tweaks come back, and the session is saved to scene.blend afterwards.
hair_only: only the hair's curve locks (after pulling what a person changed in the scene; seconds): enough after
groom_hair or lock edits when the body hasn't changed. look_hair doesn't need it (it renders the spec's hair).
Garments (spec["cloth"]) go in as meshes in the collection "cloth" with their pattern uv, sewing-detail maps and a
colour node a person can change; only simulated ones (dress) go in, a sync never starts a sim. cloth_only: just
the garments (seconds). A person's sculpt of a garment in Blender comes back with pull as offsets on that sim.

### `pull`

`pull(name)`

Take back what a person changed in the model's Blender scene, without re-syncing it: instances they moved,
turned or scaled become instance edits (the story's weather offsets taken back out), and exposed paint
numbers (a layer's opacity and colour, mask ranges, noise scale, near distances; nodes named hp:...) come
back into the spec, and garments: their colour node, roughness, and their shape (a sculpt/clean-up in Blender,
kept as per-vertex offsets on top of that sim: cloth.<g>.sculpt). Only values changed from what the last sync wrote count. Reports instances that now cut
into something (scene.clear_of slides one out). Reads the person's running Blender when it has the scene open
(unsaved edits too), else the saved file.

### `heavy_status`

`heavy_status()`

Who holds the machine's heavy-job memory and who is waiting, across every session and agent on this machine:
each running heavy job (export_asset, export_terrain tiles, cloth sims, stand exports, Cycles hair looks) with
its declared peak GB, pid, start time and working directory; the waiting queue in the order it will be served
and why each waits (memory, the GPU, behind older jobs). Jobs are admitted by a memory budget in FIFO order;
small jobs may pass one that waits for memory a few times; one GPU job at a time. A cancelled tool call
releases its job.

### `heavy_queue`

`heavy_queue()`

The machine's heavy-job queue (exports, cloth sims, terrain tiles), with nothing about the host in it: each
running job's kind, label, GB declared and minutes running; each waiting job's position, GB, why it waits
(memory, the GPU, behind older jobs), GB of jobs ahead of it and minutes waited. Your own session's jobs are
marked "<- yours", with a last line like "yours: 3rd in queue, 18 GB ahead". Fast; changes nothing.

### `export`

`export(name, path, resolution=256)`

Build at the given resolution and write an OBJ (Z up, metres). Import it into Blender with
bpy.ops.wm.obj_import(filepath=..., forward_axis='Y', up_axis='Z').

### `export_asset`

`export_asset(name, out_dir, triangles=15000, texture=2048, resolution=256, atlases=1, texel_density=None, instancing=True, preview=True, hide=None, save=None, rig=False, fbx=False, face_shapes=False, asset_name=None)`

Export a game-ready asset: a low-poly mesh (about `triangles` drawn, one mesh per part), UV atlases and PBR
textures baked from the exact model: basecolor, normal (tangent space, MikkTSpace, OpenGL/glTF green-up),
roughness, metallic, specular, ao, orm (R ao, G roughness, B metallic, glTF packing) and height (16-bit; low
poly + height = the sculpt; its range is in the json). Writes <name>.glb (glTF 2.0: Y up, facing +Z, metres,
one material per atlas with KHR_materials_specular), the PNGs and <name>.json (conventions, per part:
triangles, mm per texel, islands; per prefab: instances and savings; timings) into out_dir.
Every texel is projected onto the exact surface, so sculpted detail the low poly drops lands in the normal
and height maps. The paint maps (basecolor, roughness, metallic, specular) and the AO map are baked by Cycles
from the model's Blender scene (synced first), per pixel from its shader nodes; AO is each asset's own (a
prop never shadows the building or another prop: the engine lights them). Roughness, metallic and specular
come from paint layers and part settings (kit_reference, PAINT).
Instancing (default on): every prefab (even with one instance: a movable asset) is exported once (mesh "<prefab>", parts "<prefab>/<part>",
meshed in its own box at up to `resolution` voxels across it) with a glTF node per instance (extras.prefab),
and baked once, at its first instance (paint, AO, sky as it stands there). prefabs.<p>.export = "unique" bakes
its instances into the scene instead (when paint must differ per copy). `triangles` counts drawn triangles.
Budgets: triangles go where one joint decimation of all parts puts them (geometric error, so flat walls get
few and small round parts enough; every part gets at least max(300, triangles/100) per copy, or its parts.<p>.min_triangles: lower it for many-instance prefabs like chain links). Per part in
spec["parts"][p]: "triangle_weight" (x its share), "texel_density" (x its texels per metre), "texel_focus":
[{"at": point | joint | blob, "radius": m, "density": w}] (islands there get w x more: a character's face),
"atlas": name (its own atlas and material, e.g. "interior"), "uv": "planar" (a swappable flat surface: a clock's
dial, a sign, a screen: its own material with upright 0..1 planar UVs, so an engine swaps its texture by one
property; the json's parts.<p>.material names that material).
Atlases: texel_density (texels per metre, e.g. 512) opens as many atlases as that needs at `texture`^2 at most
(a prefab's parts stay on one), each the smallest power of two that holds its parts; the log says if any
part falls short. Without it, atlases=n splits the parts over n atlases of `texture`^2 by texture load.
preview: render the exported GLB with Cycles (as an engine would load it) to check the textures; hide:
parts, instances or prefabs left out of it (e.g. roof and walls, to see an interior).
rig: the export rig (the `rig` tool's: Mixamo's skeleton for humanoids, named chains otherwise) and the parts
skinned to it, 4 weights per vertex: characters. Humanoids also get twist bones (extra leaf joints after the
Mixamo set; each has node extras.hifipushie_twist {driver, mode, share, axis} and the json's rig.twist +
rig.twist_recipe say how an engine drives them from the hand's / arm's roll; undriven they change nothing) and
a rigid head (face, jaw, teeth, tongue, eyes and whatever a face shape moves are Head 1.0). rig may be
{"twist": false | count | {"arm", "forearm", "upleg", "leg"}, "rigid_head": false} to override spec["rig"].
Decimated triangles bend less cleanly than modelled edge loops at elbows and knees; judge it with the `rig`
tool first. fbx: also <name>.fbx (Blender converts the
GLB: skeleton, skin, embedded textures, no leaf bones, Y-primary bone axis), for Unity/Unreal import.
face_shapes: True (all) or a list of ARKit blendshape names: morph targets for lipsync and expressions on a
character with the face kit and a mouth that can open (kits.face.mouth.interior: slit, mouth bag, teeth,
tongue), or a GNM base head (base.head.interior + mouth_gap >= 0.002: shapes from GNM's expression basis). On
the one human mesh with its own quads (base.body.source "human", parts.body.topology "wrap") the head's vertices
ARE GNM's: shapes go by vertex index (no projection), GNM's mouth sock closes the mouth, the lips close on GNM's
contact ring, and mouth_gap is best left out (GNM's own lips; the export closes them). True
= all 52 ARKit names (mouth and jaw, lids, brows, cheeks, nose, and eyeLook*, which turn the eyeballs' own part)
plus the corrective jawOpen_mouthClose, which a player sets to min(jawOpen, mouthClose) each frame: mouthClose
alone only seals the lips (Audio2Face drives it with the jaw shut). On every part that moves (the head's part,
teeth, tongue, eyeballs), the same vertices as the neutral (mouth closed), each shape its full extent at weight
1, additive; names in glTF mesh.extras.targetNames, FBX blend shapes, and the json's face_shapes. Tune amounts /
the jaw / the blink's lid seal (`lid_seal`: false | amount | {amount, over, band, reach}) in
spec["face_shapes"] (kit_reference FACE SHAPES). The slit's part is meshed fine enough to keep the slit open.
The log lists each skin part's most uneven shapes (a vertex moving outside its neighbours' range; smooth ~0) and
WARNs over 0.2: a sawtooth in whatever is painted there. Check blinks posed: rig(glb=, shapes={"eyeBlinkLeft": 1}).
asset_name: what the exported files, nodes, meshes and materials are called (default the model's name; a game
that already loads "garrett.glb" with garrett_body etc. gets the same names from a model saved as rg_garrett).
Takes one to a few minutes at 2048 for a prop or creature (texture=1024 for quick checks), ~25 min for a
furnished building; progress in workspace/<model>/progress.log.

### `rig`

`rig(name, pose=None, resolution=160, size=640, save=None, drive_twist=True, glb=None, focus=None, zoom=1.0, views=None, shapes=None, engine=True)`

The export rig, a separate step over the modelling skeleton (spec bones stay for modelling): fits it,
skins the model and renders a test pose (front and side), so weights are judged before export_asset(rig=True).
Humanoids (pelvis, chest, neck, head, shoulder/elbow/wrist, hip/knee/ankle .L/.R) get Mixamo's skeleton and
names (mixamorig:Hips ... LeftHandIndex4, fingers from the hand kit): Mixamo animations, Unity Humanoid and
Unreal's IK retargeter map it as is. spec["rig"] = {"joints": {"LeftShoulder": joint or [x, y, z], ...}} moves
a rig joint; {"type": "chains", "root": joint, "chains": {"spine": {"joints": [...]}, "tail": {"from": "spine",
"joints": [...]}, "leg_front.L": {...}}} gives any creature clean named chains ("<chain>_01"...).
Twist bones (humanoids): extra leaf joints AFTER the Mixamo set, "<Side><Arm|ForeArm|UpLeg|Leg>Twist<k>",
children of their segment's joint, that spread a roll along the segment instead of wringing one joint (a hand
turned palm down is ~75 deg of forearm roll: without them the wrist takes it all). The forearm's and shin's
FOLLOW the hand's / foot's roll (shares rising to 1.0 at the wrist); the upper arm's and thigh's COUNTER their
own joint's roll (-1.0 at the shoulder: the deltoid stays put). Nothing animates them: an engine drives them
from the listed shares (the export's json has the recipe per engine), and undriven they change nothing.
spec["rig"]["twist"] = false | count | {"arm": 2, "forearm": 3, "upleg": 1, "leg": 1} (the default; up to 4).
The head is rigid: skull, face, jaw, teeth, tongue and eyes are Head 1.0, the falloff to the neck is on the
throat (spec["rig"]["rigid_head"] = false | {"band": m, "under": m}).
pose: "seated" (hips and knees at 90 degrees: characters sit, and clothes that cross each other show there), or
{rig bone: [[axis x, y, z] or "roll", degrees]} instead of the default test pose ("roll" = about the
bone's limb: the forearm for a Hand, its own length for an Arm); drive_twist=False leaves the twist bones still
(what an engine without drivers shows). The text reports each twist chain's test (hand rolled 75 and 105 deg:
twist by station along the forearm, what is left at the wrist, the worst cross-section's area against rest:
a candy wrapper is a dip under ~0.8), the head's weights by height, and the WEIGHTS AUDIT: every joint turned
alone through its usual range, with how far its own skin ends from a rigid turn, how far other bones' skin moved
(and whose), flipped triangles, weight one digit's bones hold on another digit, left / right asymmetry, sums and
influence counts; lines ending "<- BAD" are what to fix. Then LAYERS, seated: for each pair of parts, how many
vertices of one lie on the other at rest and are under it posed (clothes crossing each other or the skin: a
jagged line). Clothes read the skin's weights under them, so layers agree; parts.<p>.rig_weights ("surface" |
"around" | "distance") and rig_smooth (rounds over the part's own mesh, 0) change that per part (guide: rigging).
glb: an exported <name>.glb to judge INSTEAD of this tool's own build: the real low poly with the weights and
joints an engine gets. Do this for hands and faces: the look build here is coarse (the text says when its voxel
is too big for the fingers: they fuse at rest and no pose of them means anything). focus: a rig bone to centre
on (with zoom, e.g. focus="LeftHand", zoom=6), views: e.g. ["front", "left", "back"]; shapes: {face shape:
weight} added before posing (glb only: {"jawOpen": 1} with a head turn). pose = {} renders the rest pose: look
at it first, so a mesh fault isn't blamed on the weights. Rest pose = as modelled. With glb the image has two
rows: the GLB as an engine draws it (its maps and normal map: judge faces and silhouettes there) over its bare
mesh in clay (facets and folds); engine=False leaves the first out (faster).

### `call_tool`

`call_tool(name, args=None)`

Run any hifipushie tool by name, enabled or not (registered only with HIFIPUSHIE_CALL_TOOL=1, for hosts that
ignore list_changed). args: that tool's arguments. enable_toolset("") lists the tools; guide(topic=<tool>) has
each one's parameters.
