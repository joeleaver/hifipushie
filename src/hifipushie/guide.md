# hifipushie playbook

How to get good results, learned the hard way. Read it once before modelling; come back to the section
you're in.

## 0. Seeing and showing

- `look`, `check` and `set_plan` return images to you. The person you're working with may not see tool
  images: pass `save="/path/file.png"` and share the file when they should see progress.
- Judge from the right view. Clay (default) for overall read; `shading="raking"` for masses, planes and
  shallow forms (clay hides them); `shading="curvature"` for blobbiness (an evenly tinted area is a blob)
  and for defects (stripes, speckle, kinks); `strokes=True` to check *where* strokes are before judging
  *what* they look like. Close-ups (`focus` + `zoom` 3-6) rebuild just that region at full resolution:
  judge faces, hands and every detail there, never from a full-body render.
- A close-up box cuts the model: flat caps where it crosses the body are the cut, not holes.
- See inside and underneath without a second model: `hide_parts=["roof"]` / `only_parts=["shorts"]` (no
  rebuild; the body under clothes, one part alone), `clip={"z": 2.2}` with `views=["top"]` for a floor plan
  (`{"-y": 0}` cuts off the front half; `{"point", "normal"}` any plane). Cut solids get flat caps in their
  part's colour, darkened: dark bands are cut walls, not paint.
- Environments: `camera={"eye": [x, y], "target": [x, y, z], "fov": 70}` renders a perspective panel from a
  person standing at (x, y) (eye 1.6 m above the floor found there); give a list for several. Judge a room
  from eye height, not only from outside. Perspective panels have no rulers: take sizes from the plan view or
  `clearance`, which answers "can someone walk here" in numbers: a top-view map of walkable floor, headroom
  and floor flatness over a region, or the clear width/height along a path through a doorway.
- Painting a big environment is the slow part of a look (AO at every vertex, ~2 min at 700k verts, once per
  build). Hidden, clipped and out-of-camera geometry isn't painted, and once the whole model has been painted,
  hide/clip/camera looks reuse it.

## 1. Work in stages, and check after each

1. **Plan** (`set_plan`): front and side outlines from ellipses, capsules and polygons in world units,
   landmark heights (crown, chin, shoulder, elbow, wrist, hip, knee, ankle), and 3-4 sections (width x
   depth at chest, belly, thigh...). Look at the sheet and fix proportions here: it costs one edit.
   Keep arms visibly apart from the torso in the front view, or the silhouette reads as one slab.
   Section `near` picks the slice part; add `"x": [lo, hi]` when arms touch the torso at that height.
2. **Blockout** (`put_model`): read joints straight off the plan, tie landmarks to joints
   (`"joint": "knee.L"`), then `fit` (against the plan; landmark joints keep their heights) and `check`.
   Aim for IoU > 0.95 and sections within ~5% before going on. Add kits (face, hands) here.
3. **Secondary forms** (strokes): muscle masses, fat pads, planes, big folds. `check` again: strokes
   shouldn't move the silhouette much.
4. **Detail** (strokes with repeat/scatter, in close-ups): wrinkles, creases, warts, pores.
5. **Parts** (clothing, eyes, teeth) can come in at 2-4; they're separate meshes.
6. **History** (section 5b): write `spec["story"]` at the start, and before paint turn each event into
   geometry: weather ops, sag, lean, lumpy, chips, things moved out of place. `check` audits perfection.
7. **Paint** last (section 5): it doesn't change the shape, so it can't break earlier stages. Weather it from
   the story too.

Going back is fine and cheap (history/revert). Expect the plan-vs-model IoU to drop a little as kits and
details add things the plan never drew (nose, ears, fingers).

## 2. Blockout pitfalls

- A joint whose radius is bigger than the bones meeting there shows as a ball (elbows, knees). Taper
  bones (`r_a`/`r_b`) and let the joint be no bigger than its bones.
- Blend is ~0.02-0.05 for a 1 m creature; small blends (0.01-0.025) on limb joints keep them from
  melting, big ones on the torso. Chains (tails, tentacles) go in one `group` with a small `join`.
- Kit faces sit on the head's surface. A jaw blob that sticks out past the skull swallows a drooping
  nose: shorten the droop or lengthen the nose until the tip clears the jaw (probe with `measure`).
- Kit features are ellipsoids and read as stuck-on balls (cheeks especially, and brows). Prefer strokes
  for brows, cheeks and fat pads; keep kits for eyes, lids, nose, lips and hands.
- Ears, leaves, fins, feathers, blades: a `"shape": "blade"` blob (a thin sheet with rounded edges; `taper` for a
  point, `cup` for an ear's hollow, `bend` for a curling tip), rotated so its local y runs root to tip and its
  local z faces the way the hollow opens. A cone reads as a spike, and an ellipsoid as a lump.
- Toes: the foot kit (`{"type": "foot", "ankle": "ankle.L", "ball": "toe.L"}`) makes the foot's body, ball, heel and
  toes. Drop a capsule "foot" bone it replaces, and any toe-groove strokes on it. Sizes follow the leg arriving
  at the ankle.
- Separate digits (toes, extra fingers, horns, tusks) are geometry, not strokes. Put them in the blockout
  (bones, the hand kit) and root attachments on the surface with seated joints (`"on"`, below).

## 3. Strokes

Strokes displace the existing skin along its normal: a stroke is a trail of dabs summed along a path
addressed on the surface. Rules that matter:

- **Broad and shallow.** Muscle masses on a 3 cm-radius limb: width 15-45 mm, depth 3-12 mm. Deep and
  narrow strokes read as stuck-on panels.
- **Taper depth to 0 at the ends** of masses (`"depth": [0, 0.01, 0]`). Full depth at the ends makes pills
  and sausages; the natural end taper is only about one width.
- **Profiles:** `soft` for masses (default for clay), `sharp` for crisp creases (default for crease),
  `round` for warts/knuckles, `flat` for deliberate planes. `flat` on a muscle makes a plate with a rim.
- **Creases need width >= 3 voxels** at the resolution you judge them at, or they break into cracks.
  At full-body 256 a voxel is ~4 mm on a 1 m model; in a close-up it's ~1-2 mm.
- **Address from the skeleton:** `{"bone": b, "t": 0..1, "side": [x,y,z], "around": deg}`; later points
  inherit (`{"t": 0.9}`). For faces, anchor on kit features: `{"at": "face_mouth_corner.L", "offset": ...}`,
  `face_nose_root`, `face_eye.L` (get_model lists generated names). Raw head-relative coordinates are
  where placement goes wrong.
- **Always check placement with `look(strokes=True)`** (orange clay, blue crease, green flatten) before
  judging form. Then raking for the masses, curvature for defects.
- Strokes apply after everything else in their layer. Keep body strokes on layer 0; a stroke on layer 1
  near the eyes also pushes the lids off the eyeballs.
- `repeat` lays out sets (forehead wrinkles, toes' grooves, ribs); `scatter` places random copies within
  ranges with a size range and min spacing (warts, pores). A ".L" scatter mirrors exactly: use a centre
  name addressing both sides (".R" bones exist) for asymmetry.
- What strokes can't do: split geometry (toes), make overhangs, or fix proportions. Those are blockout.

## 4. Parts

- Every element takes `"part"` (default `"body"`); each part is its own mesh and colour, exported as
  its own OBJ object. Kits take `"part"`; the face kit's `eyes.part` makes separate eyeballs.
- Clothing: `"parts": {"shorts": {"shell": "body", "offset": 0.007, "color": [r,g,b]}}`, then blobs/bones
  with `"part": "shorts"` mark where it exists (their union cuts the shell), strokes with
  `"part": "shorts"` make folds, and a belt can be a shell of the shorts. Shells are solid (the inside is
  hidden in the body); offsets of 1.5+ voxels at your judging resolution.
- Seated joints root attachments on the surface: `{"on": {"at": "face_mouth_corner.L", "offset": [...]},
  "lift": -0.003, "r": 0.0065}` for a tusk's root, and the same address with `"shift": [dx,dy,dz]` for its
  tip. They follow the surface when the face or body changes.

## 4b. Props and environments

- Build a repeated thing once: `prefabs` (a chair in its own frame) placed by `instances` (at, rot, scale,
  part); `array` on an element for rows and grids (logs, planks, shingles, legs), with `jitter`. Don't write a
  script that emits hundreds of elements: the spec stays readable and one edit changes every copy.
- Nothing made by hand or grown is uniform. Give arrays `vary` (per-copy ranges for any number: radii,
  bow, size), `flip` (logs alternate butt ends course to course), `jitter`; bones `bow` and `"ends": "flat"`
  for sawn timber; `lumpy` for knots and axe marks. Identical copies at even spacing read as CG at once.
- `tags` (and instance / array names, which are tags automatically) stand for all their members in paint
  `near`, cut `targets` and `delete`.
- Hard surfaces: `box` and `cylinder` blobs with `round`, `hollow` for vessels, and cuts with `targets` so an
  opening only bites what it should. Keep walls >= 2 voxels at the resolution you judge at.
- Prefabs face -Y (their front is local -Y, like a creature), origin on the floor under them (a door's at its
  hinge, the leaf along +X). `look(views=["top"], clip={"z": 2}, instances=True)` is the floor plan with an arrow
  on every instance's front: check it after placing furniture. Nothing else shows a dresser facing the wall.
- Partitions and plain walls are `walls`: a path, a height, boards or solid, and `openings` that cut the wall and
  hang the frame, window and door (hinge side, swing side, angle open). One entry per wall, not a board array,
  cuts, frame and door instances written by hand.
- Set props down with `"on"`: a cup `"on": "table1/top"`, jars on `"shelf#1"`, books on `"bookshelf1/shelf#2"`,
  an apple on the bowl it's in, a barrel on the ground. Give `at` as [x, y]; the z is found (and follows the
  furniture when it moves). Name the element (`table1/top`, `shelf#1`), not the whole piece: the top of a dresser
  with a plate rack is the rack.
- Clutter: `spec["scatter"]` = {name: {"use": {prefab: weight}, "on": support, "count", "area", "spacing", "rot",
  "scale", "seed", "tags"}} lays out instances "on" a shelf, a tabletop or the floor: whole footprints over the
  support, clear of each other, of props already there and of anything above (a plate rack, a wall). `check`
  says when fewer fitted. Footprints are circles round each prefab's origin (a skillet claims its handle's
  reach), so a crowded counter takes nothing more. Paint scattered props by prefab name (`near: ["apple"]`):
  a tag you gave hand-placed ones isn't on them.
- Seams between repeated members (chinking between logs, mortar between rails) are a bone `{"between": array,
  "inset"}`: it follows every copy's bow and gap. A flat slab behind irregular logs either peeks through as
  ragged streaks or bulges out.
- Vessels and fixtures (tubs, basins, sinks, jugs, pots): the body is ONE shape that already has the form (a
  round cone lying along the tub, widest near the rim: raise its axis and stretch its section down with `flat`;
  a half ellipsoid for a basin; a rounded box for a sink), `hollow`, with a box cut targeted at it to open the
  top. A rolled rim is the same shape grown a little, hollowed thicker and cut to a band at the rim height: a rim
  of a different shape floats beside the body with a dark gap. Set it down with `"on"` (a bowl whose centre
  was put by hand sank into the stand and showed the wood through its bottom), and a set-in sink needs its hole
  cut through the counter's body as well as its top. Judge thin walls in a close-up or the painted scene
  (prefabs mesh at their own voxel): a whole-model clay view shreds 9 mm walls. `examples/fixtures.json`
  has a clawfoot tub, a washbasin, a jug, a set-in sink and a hand pump to start from.
- Small loose props (bread, a book, a cup) are prefabs even when there's one: a prefab meshes in its own box at
  a voxel for its size, while an element in a big part shares that part's voxel (the bread came out at 30 mm).
- `check` walks a person through every door opening and names what blocks it (a door swung across the
  doorway, a chair). Model some ground (a big box, part "ground", lumpy) if there are props outside.
- `check` also lists props cutting into anything ("chair3 cuts 45 mm into table1/leg#2"): fix them by moving the
  prop, not by ignoring the list. Mark what's made to sit into things `prefabs.<p>.embed: true` (window and door
  frames in their walls) and parts that give `parts.<p>.soft: true` (rugs, bedding, cushions: feet sink into them).
  Moving one thing to fix a clash can make another (a stool moved into the bathroom doorway): read the doorways
  too.
- Cameras: `eye: [x, y]` stands a person there; asked to stand on a counter, bed or table, they step off onto the
  floor beside it (the info line says so). Give a 3D eye to put the camera anywhere.

## 5c. Style: how far from realism

The rules above (restraint, centimetre sag, subtle grime) are for realism. A stylised model says so in
`spec["style"]`, and most of the look still comes from choices you make in the spec:
- `style.shape`: "round" x every box/cylinder edge radius, "chunk" k (thin legs, tops, rails, handles and boards
  thicken up to k, never past 6 cm; their openings too), "lumpy" {"amount", "scale"} (0: smooth), "chips" x,
  "bow" x, "blend" x. Rebuilds geometry.
- `style.paint`: "saturation", "value" (HSV, every colour and part base), "pattern" x every pattern size (grain,
  stones, planks, noise), "weathering" x materials' wear and dirt. Paint only: no rebuild.
- Proportions are yours: fewer, fatter members (7-9 logs, not 13), steeper roofs with thick slabs and big
  overhangs, oversized doors and windows, a leaning chimney, a coloured door and trim. Swap busy realistic
  patterns (planks tiles on a shingled roof) for flat colour with a tone per piece (`random`) and shadow lines
  (`ao`). A thick roof slab needs its shingles on top of it, not at the old offset.
- `workspace/cabin_toon.py` builds cabin5 at three levels (storybook, cartoon, toybox) as a worked example.
- The silhouette is what reads as cartoon, and parts alone can't give it: `style.shape.deform` bends the whole
  building (deform.py): "sag" (a ridge that dips), "bulge" (walls that belly out), "taper" (a base wider than the
  eaves), "lean", "twist", "wobble" (a hand-drawn waver). Prefab instances stay rigid and ride the bend (props
  "on" a table ride with the table). Rigid windows and door frames in a bent wall can sit a little off their
  bent openings at strong settings. A deformed build costs ~2-3x an undeformed one.

## 5b. History: nothing real is pristine

Perfect things read as CG at a glance: identical copies at even spacing, everything square to the axes, flat
faces with no deviation, clean paint. Give every model a `story` (age, climate, use, named `directions` like
"weather" and "sun", and events), then make each event visible, in geometry first and paint second:
- **Time and gravity:** `weather` ops by tag: beams and floors `sag`, posts `lean`, stones `settle`, and
  `lumpy` surfaces. Arrays get `vary`/`jitter`/`flip` (see 4b).
- **Use and misuse:** `chips` on edges that get knocked (steps, table edges, stone corners), worn paths
  (paint `path` with wear), polish where hands go (`near` + low roughness), furniture pushed out of place
  (`weather` jitter on instances: chairs pulled out, a rug askew, a door ajar).
- **Weather:** the story's "weather" side darker and streaked (`facing: "weather"` + stretched noise),
  exposed tops rain-washed grey or mossy (`sky` open), sheltered places dusty (`sky` closed), drips below
  sills and nails, sun bleaching (`facing: "sun"`).
- **Set dressing, if it's a place:** nothing free-standing is square to the room; things are in a state of
  use (a pot on the stove, a blanket thrown back, a book open, boots by the door); clutter collects where
  people leave things (shelves, corners, the table), not evenly.
- **Restraint:** weathering should be noticed second, after the form. Sag is centimetres over metres
  (2-3 cm on a 3 m beam), a lean about a degree, furniture a few degrees off square, grime and bleaching a
  shift of tone (opacity ~0.15-0.3), not a new colour. Heavy-handed ageing reads as fake as none: push it
  until it reads, then back off by a third.
- Run `check`: it lists what still looks too perfect. The warnings are prompts, not rules: a machined part
  should be exact, a log wall shouldn't.

## 5. Paint

Paint is colour (and roughness, metallic, specular, height) laid on the finished surface: `spec["paint"]`
layers, applied in order over each part's clay colour (`parts[p].color`). Every mask is evaluated per point,
at mesh vertices in `look` and at every texel in `export_asset`, so the same spec gives the same result, only
sharper in the export. It never touches geometry, so a paint edit re-renders in a few seconds.
Colours are sRGB as you'd pick them (`"#7d8c5a"` or `[0.49, 0.55, 0.35]`).

- **Work like a painter, broad to fine:** a base colour per part (a layer with no mask), then big zones
  (`facing` for countershading: dark back `[0, 0.6, 0.8]`, pale belly `[0, -0.3, -1]`), then regions
  (`near` elements or a kit name: `"hand.L"`, `"face_eye.L"`, with `within` ~ the blend radius), then
  markings (`path`, addressed exactly like strokes; `repeat`/`scatter` for stripes and spots), then
  breakup (`noise` for mottling, `cavity: "concave"` for dirt in creases) at partial opacity.
- **Masks multiply**, so confine a broad mask with a local one: an `axis` along a bone ramps across the
  whole part (the feet lie past a forearm's end too), so a glove is `near: ["forearm.L", "hand.L"]` plus
  the axis ramp.
- **Check coverage** with `look(paint_layer=...)`: its info line gives the share of the surface in view the
  layer lands on. NOTHING means misaddressed; far more than you meant means a mask too loose (`within`, `range`).
- Judge with `shading="flat"` (unlit colour: exactly what you painted) and the clay view (how it reads with
  form). Paint can't be finer than the mesh: ~1 voxel full-body, finer in close-ups; markings a few mm wide
  need a close-up to judge.
- **Weathering comes from the surface, not from placing it by hand** (Substance-style smart masks). A layer's
  `"mask": [...]` stack combines generators with blend modes: `ao` (occluded places), `cavity` (creases /
  ridges), `thickness` (thin ears, fingers), `facing`, `noise` (`warp` for torn grunge, `stretch` for
  streaks and drips), `cells` (voronoi: scales, cracks, plates, warts), plus paths and regions. `breakup`
  on an entry lets noise eat into it crisply: convex cavity + breakup = edge wear, ao + breakup = grime,
  facing up + breakup = dust. `kit_reference` (PAINT) has the recipes. Keep each effect its own layer, and
  look at it alone with `look(paint_layer="grime")` (false colour: purple 0, yellow 1) before judging colour.
- **Materials first for props and clothing:** `{"material": "planks", "part": "floor"}` (or cloth, leather,
  wood, brick, stone, metal, rust) expands into base colour, pattern, relief, wear and dirt layers; masks on
  it confine it, `color`/`scale`/`wear`/`dirt`/`dir` tune it. Tiles and weaves are laid out triplanar: clean on
  flat walls and floors, blended on curved surfaces, so orient `dir` along the grain or rows.
  For anything built of many pieces (log walls, furniture, frames, firewood) give wood `"dir": "element"`: the
  grain follows each log, leg, rail and board, each its own piece of pattern, end grain on each piece's cut ends.
  One layer does a whole part; no layer per orientation.
- **One value per element:** `{"random": {"range": [lo, hi], "seed"}}` is 0..1 per element (every book, board,
  stone, array copy). Stack layers with rising narrow ranges ([0.25, 0.26], [0.5, 0.51], [0.75, 0.76]) for a
  quarter of the books in each colour; a wide range at low opacity for board-to-board tone. Prefab instances
  share one bake, so they share values.
- **Dust and other "tops" masks on small round props:** a `facing` range starting low (0.3-0.5) wraps the mask over
  rounded rims and lids, and its breakup tears the edge: the lids read crumpled. Start it high ([0.85, 0.98]) so
  only flat tops take it; look at the layer alone on a small prop before judging.
- **Relief without sculpting:** `"height": -0.001` on a cells layer grooves the scale borders; `0.002` on a
  cells-distance layer raises warts. It lands in the exported normal and height maps at texel resolution;
  `look` only tilts vertex normals, so judge it in a close-up with `shading="raking"` and in the export
  preview. Sculpt forms bigger than a few voxels with strokes instead.
- **Painted by hand:** when a mask is easier to paint than to describe (a worn path across a floor, a stain where
  someone set a pot down), give the layer `"painted": "new"` and `sync`. Every object of the layer's parts gets a
  colour attribute `hp_paint:<layer>`. The person (or you, over the Blender MCP) paints it in Vertex Paint, white =
  1. The next `pull`/`sync` stores it as a point cloud and writes its id into the layer. It survives re-meshing
  and model edits nearby, and works in stacks like any generator: multiply it with `noise` breakup so the painted
  edge isn't the brush's.
- Eyes, teeth and clothing are best as their own parts with their own colour; a `near` mask around the eye
  also paints the eyeball if the eyeball is in the body part.

### Game-ready export

`export_asset(name, out_dir)` writes a GLB plus every map (per atlas) as its own PNG (basecolor, normal, roughness, metallic,
specular, ao, orm, 16-bit height) and a json with the conventions. Nothing is baked from a high-poly mesh: every
texel is projected onto the exact surface, so detail the low poly drops (warts, wrinkles, creases) lives in the
normal and height maps, and paint is as sharp as the texture. Faces buried inside another part (skin under
solid clothing, eyeball backs) are removed first.
- Give materials their numbers in paint: `parts.<p>.roughness/metallic/specular` for defaults, layers for
  variation (wet lips `roughness: 0.2`, metal buckle `metallic: 1, roughness: 0.3`). The clay views don't show
  these; the export preview (Cycles) does.
- `triangles` (drawn: a prefab counts once per instance) ~15k suits a hero creature; 5k for a crowd; a
  furnished building 50-100k. `texture=1024` for quick checks, 2048 to ship.
- Prefabs with 2+ instances export once: one mesh (a primitive per part) and one set of texels, placed by a
  glTF node per instance, meshed in a box of their own (finer than the scene's voxel when small). Each is baked
  at its first instance (its paint, AO and sky as it stands there), so every chair gets that chair's grime. When
  copies must differ (one chair by the fire, sooty), set `prefabs.<p>.export: "unique"` or make it a second
  prefab. `lumpy`/`chips` on prefab elements are the same on every instance, in look too.
- Triangles follow geometric error, not area: one decimation of all parts together decides each part's share,
  so flat walls get few and small round things (eyes, pots, pillows) enough; every part gets at least
  max(300, triangles/100). Steer it per part with `parts.<p>.triangle_weight` (x its share).
- Texels: every part gets the same texels per metre unless `parts.<p>.texel_density` says otherwise (2 = twice
  as sharp, four times the atlas area). `parts.<p>.texel_focus: [{"at": "head", "radius": 0.15, "density":
  2.5}]` gives a region more (a character's face: the troll's went from 1.5 to 0.8 mm/texel at 1024).
- Read the log: the atlas fill and mm/texel per part. A creature fits one atlas (troll ~58% filled); a big
  environment doesn't (the cabin's 380 m^2 of logs and shingles gives ~30 mm/texel on one 1024 atlas). For
  environments ask for a density: `export_asset(texel_density=512, texture=2048)` opens as many atlases as it
  takes (texels per metre x each part's `texel_density`; 512/m = 2 mm/texel, for close interiors; 256/m for
  walls seen from a few metres), each the smallest power of two that holds its parts, a prefab's parts together.
  `parts.<p>.atlas: "interior"` still pins a part to a named atlas; `atlases=n` is the manual split.
  A part too big for one atlas at that density (a whole log wall, a roof, the ground) is cut into slabs along
  its longest side ("roof~0", "roof~1", ...: the log says so), an atlas's worth each; `hide=["roof"]` hides all
  of them. A prefab can't be split: the log names one that won't reach the density.
- Density costs texels, texels cost time and file size: the furnished four-room cabin (100k triangles) at 256/m
  is ~40 atlases of 2048 (250 MB GLB) and ~40 min; at 128/m about a quarter of the texels. Low poly ~8 min,
  per-atlas projection most of the rest, the Cycles paint/AO bake a few minutes. Progress goes to
  workspace/<model>/progress.log.
- Detail thinner than about a voxel at the export resolution (22 mm shingles at 256 across a 6 m cabin) makes
  a broken high mesh: inverted faces and normals the bake can't use. Those texels keep the low-poly surface
  (the log says how many per part). Build at a higher resolution or make the detail thicker.
- Judge the preview and close-ups (`asset.preview` focus/zoom; `hide=["roof", "walls"]` to see inside) for
  seams and the normal map's read.


### Rigging characters

The skeleton you model with is not the rig. Tusks, lip chains and a shorts leg are modelling bones. The export rig
is a separate, standard skeleton, and the `rig` tool fits it and skins the model:
- **Humanoids** (pelvis, chest, neck, head, shoulder/elbow/wrist, hip/knee/ankle .L/.R) get Mixamo's skeleton and
  names, with fingers from the hand kit. Mixamo animations, Unity Humanoid and Unreal's IK retargeter map it as is.
  Keep those joint names on anything humanoid.
- **Other creatures:** give `spec["rig"] = {"type": "chains", "root": "pelvis", "chains": {"spine": {"joints":
  [...]}, "tail": {"from": "spine", "joints": [...]}, "leg_front.L": {...}}}`: clean named chains.
- **Check the pose.** Run `rig` and look at its test pose (elbow, shoulder, hip, knee, spine, head). Look for tears,
  lumps left behind and creases. Move a rig joint with `spec["rig"]["joints"]` (e.g. the clavicle,
  "LeftShoulder"). Then `export_asset(..., rig=True)`.
- **Limits:** decimated triangles bend less cleanly than modelled edge loops. The rest pose is as modelled (arms
  down); retargeters handle that with their retarget pose.

## 6. When something looks wrong

- Don't guess and pile on fixes. Isolate: render the region with `shading="curvature"`, and remove
  suspects one at a time (strokes are easy to delete and restore via history) until the defect goes.
- Stripes or speckle across a stroke: its path crosses busy features (lids, nostrils) or it is very deep
  for its width; widen it, make it shallower, or move the path.
- Cracks and zigzags: something is thinner than ~2 voxels at that resolution (a crease, a shell, a lid
  gap). Widen it or look closer.
- A "hollow" or flat grey cap at the edge of a close-up is the close-up box cut.

## 7. Resolution and time

- `look` at 160-200 while blocking out, 256-300 for full-body judgement, close-ups at 200-240.
- Builds with many strokes take tens of seconds for close-ups; batch several edits per `edit_model`
  and look once, like a sculptor stepping back, rather than one stroke at a time.
