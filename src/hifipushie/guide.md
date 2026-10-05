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

Big to small, like an artist: silhouette, then big masses, then secondary forms, then detail. **Get each stage
approved (by the person, or against the reference and a measured gate) before starting the next.** Detail comes
last. Grooves, pores and strands put on a wrong mass only hide the problem and are thrown away when the mass
changes. Every stage needs a look that takes seconds (a cropped scene, a few views, a thumbnail at game size,
the reference beside it), or the loop stalls.

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

## 4d. Realistic humans start from a base, not blobs

When the subject is a realistic human (or stylised-realist: near-real proportions), don't build the body from joints,
blobs and the face/hand kits. Start from `spec["base"]`: a MakeHuman body (CC0, parametric age / weight / muscle /
height) with a Google GNM head (realistic faces, identity and expression components), e.g.

    "base": {"body": {"source": "makehuman", "age": 45, "weight": 0.72, "muscle": 0.3, "height": 1.78},
             "head": {"source": "gnm", "scale": 1.12}, "eyes": "eyes"}

Then shape it with parameters, not sculpting: body macros, `base.head.fit` / `regions` / `pose` / `shape`, a style
sheet (`style.sheet`), garments, hair locks. The less hand-editing, the less margin for error. Worked example:
`examples/disc_golfer_mh.json` (resolved) / `disc_golfer_style.json` (on a sheet). Blobs, anatomy and kits remain the
way to build creatures, cartoons and anything a parametric human can't reach. `check` warns when a spec looks
humanoid but has no base.

## 4c. Hair: curve locks, big to small, the way an artist grooms

Hair isn't part of the field: each lock is a Bezier curve in the Blender scene swept with a cupped lens profile, its
flat side on the volume under it. The workflow (silhouette as one volume, then 8-12 big drawn clumps, then the sides
and back, then a light breakup, material last), the artists' rules behind it and the tools (groom_hair, look_hair,
hair_reference, sync(hair_only=True), pull) are in guide(topic="hair"). Read it before touching hair.

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

### Style sheets (characters)

Stylisation is a set of decisions, not a multiplier: what's pushed (a jaw, a brow mass, a dark iris), what's
removed (nostril detail, wrinkles, pores), which planes the face is built from, how colour carries form (warm,
saturated skin whose shadows turn redder; brows and stubble as solid designed shapes, never noise), and the light
it's judged in. A sheet bundles those so another character takes the same style:
- `spec["style"]["sheet"] = "stylised_realist"` (package `styles/`, or your own in `<HOME>/_styles/`): its partial
  spec (base.style and head fit/pose defaults, part settings like skin `subsurface`, paint layers addressed on the
  `lm_*` landmark joints, `style.look` = the lights renders use) sits under the model's spec; the model wins key by
  key, `null` deletes a sheet key, and save keeps only what differs from the sheet. Turn a recipe on by setting
  one key (the sheet's `stubble.L` is opacity 0: `{"stubble.L": {"opacity": 0.55}}`).
- Head shape toward the sheet: `base.head.fit` (proportions in interocular units, now also `nose_width`,
  `mouth_width`, `eye_seam`) and `base.head.pose` (landmark moves in metres, solved as the least change of GNM's
  expressions: `smile`, `mouth_raise` (a shorter philtrum), `mouth_width`, `lid_upper`, `lid_lower`, `brow_inner`,
  `brow_outer`). Character comes on top: a resting smile, a relaxed brow.
- `style_check(name)` measures the model against the sheet's rules (chin/philtrum, nose, mouth, eye opening and
  how much iris the lids cover, skin saturation and hue lit vs shadow in the sheet's look) and says why each
  rule exists. Judge renders next to the reference in the sheet's look, not the grey studio.
- `style.look` works without a sheet too: {"lights": [{"dir", "energy", "color", "angle", "shadow"}], "world":
  {"color", "strength"}, "view": "AgX" | "Khronos PBR Neutral" | ..., "look": "AgX - Punchy" | "None", "exposure"}.
  AgX rolls bright colours off toward white (lit skin never passed V ~0.8 whatever its paint); "Khronos PBR
  Neutral" keeps albedo hue and saturation up to the highlights, as glTF viewers show an export.

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
- **Images (a painting, a printed page, a poster, a label, a logo):** the `image` generator lays an image file or
  set text on the surface as a decal projected along `dir`. Give the thing it's printed on its own part (the
  canvas, the page, the disc), so the projection can't land on the frame or wall behind it:
  `{"part": "canvas", "color": "image", "image": {"file": "examples/images/landscape.jpg", "at": "canvas",
  "dir": "front", "size": [0.62, null]}}` (a blob's "front" = its local -Y face; `null` = from the image's aspect).
  Text: `"image": {"text": {"string": "...", "font": "serif", "size": 0.004, "align": "justify"}, "at": [x, y, z],
  "dir": [0, 0, 1], "up": [0, 1, 0], "size": [0.145, 0.21]}` (the page; `size` of the text = em height in m).
  `"color": "image"` paints the picture's colours; with a plain colour or in a mask stack it's a stencil
  (`channel` alpha / luma / r / g / b / coverage). Relief: a second layer `{"height": 0.0003, "image": {...,
  "channel": "luma"}}` (impasto, embossing). Foil: add `metallic`/`roughness` to the colour layer. A file is copied
  into `workspace/_images/` at save and named by its id. `look` draws decals per pixel (text readable in close-ups);
  exports raise the texel density over each decal (up to 2000/m: 4 mm text needs ~0.4 mm texels, ~10 per em; at
  2.5 mm it's grey smudges). A placement that hits nothing on the layer's part is refused at save. Planar
  projection stretches on steep curvature (a mug's sides past ~45 deg): wrap it instead (`"wrap"`):
  - `"cylinder"`: a label round a can, mug, bottle, a print round a sleeve. `"axis"`: a bone, [joint, joint],
    [x, y, z] with `at`, or {"at", "dir"}; default the `at` blob's own axis (a cylinder blob). `at` sets the
    label's height; `dir` the way its centre faces (default front). Width as `size` [w, h] in metres round the
    surface, or `"span"`: degrees round (then `size` [null, h] or the image's aspect). `"seam"`: where the wrap is
    cut (deg from the centre, default 180: behind). The surface's taper at the label is measured: on a taper (a
    bottle's shoulder) it's fan-cut like a paper neck label (rows round the axis, the ends along the cone's lines,
    even height; `"unroll": "cone"`), else a cylinder; `"unroll": "arc"` keeps each row's true length at its own
    radius instead (the ends lean on a taper). Mug: `{"file": ..., "wrap": "cylinder", "at": "body", "span": 300,
    "size": [null, 0.066]}` (the seam behind, the handle in the gap).
  - `"sphere"`: a globe or a ball: `at` = the centre, `axis` = the poles (default the blob's z), `span`
    [round, up] in degrees ([360, 180]: an equirectangular map), or `size` in metres at the surface.
  - `"surface"`: a sticker that lies on any curved surface like paper (a ball, a car door, a helmet): geodesic
    coordinates from its centre (`at`, seated on the surface; `up` orients it). Measured per vertex on its own
    fine mesh (the vector heat method's log map: angles within ~0.1 deg out to the corners of a sticker the size
    of the ball's radius), the picture sampled per pixel; stretch left is the surface's own curvature. Costs a
    few seconds once per placement (cached).
  Wraps measure the surface of the layer's parts (`"on"`: other parts). `"style": true` runs the picture's
  colours through the paint style's saturation/value. `.L` layers and `"mirror"` mirror wraps too.
  Placing by hand: after a `sync` every decal is a wire gizmo in the scene (collection "decals"; layers placed
  alike, a picture and its relief, share one). Move, turn or scale it in Blender and `pull` (or the next `sync`)
  writes it back: near its joint/blob as `"offset"` (world [x, y, z], so it keeps riding the blob), further than
  its own size away as a world `at`; a spin about its normal as `rotate`, a tilt as `dir`/`up`, a scale as
  `size`; a wrap's height (offset), turn round its axis (`dir`), tilt (`axis`), scale (`span`/`size`).
  Exports: the export report's `parts.<p>.seams` says whether the baked maps run on across UV chart borders
  (`excess` ~1 = invisible; > 1.5 is a WARNING in the log). Texels past each island are filled across its seam.
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
- **Check the pose.** Run `rig` and look at its test pose (elbow, shoulder, hip, knee, spine, head, a hand rolled
  palm down). Look for tears,
  lumps left behind and creases. Move a rig joint with `spec["rig"]["joints"]` (e.g. the clavicle,
  "LeftShoulder"). Then `export_asset(..., rig=True)`.
- **Twist bones** (humanoids, on by default). What riggers do: a limb's roll is never left to one joint. A hand
  turned palm down is ~75 deg of roll about the forearm (105 in gestures); in a person the radius turns over the
  ulna along the whole forearm and the wrist itself doesn't twist. With one bone per segment the wrist takes it all
  and the skin wrings there (the "candy wrapper"). So the rig adds leaf joints along each segment, after the
  Mixamo set and children of the segment's own joint, as Unreal's mannequin does (`lowerarm_twist_01/02`,
  `upperarm_twist_01/02`, `thigh_twist`, `calf_twist`) and VRM's roll constraint describes:
  - `<Side>ForeArmTwist1..3` and `<Side>LegTwist1` FOLLOW the hand's / foot's roll: share k/n at station k/n,
    1.0 at the wrist (nothing is left to the wrist joint, nothing turns at the elbow);
  - `<Side>ArmTwist1..2` and `<Side>UpLegTwist1` COUNTER their own joint's roll: -1.0 at the shoulder / hip (the
    deltoid stays with the clavicle), easing to 0 at the elbow / knee.
  Numbered away from the body. Nothing animates them, so a Mixamo clip plays as before and, undriven, the skin is
  what it was without them (their weights are the segment's own weight shared out along it). An engine drives
  them: glTF has no constraints, so each joint's `extras.hifipushie_twist` (driver, mode, share, axis) and the
  export json's `rig.twist` / `rig.twist_recipe` (Godot, Unity, Unreal) say how. Counts:
  `spec["rig"]["twist"] = false | n | {"arm": 2, "forearm": 3, "upleg": 1, "leg": 1}` (the default; up to 4).
  More bones = smaller steps: between two stations turned d apart, linear skinning keeps cos^2(d/2) of the
  section's area.
- **The head is rigid.** Skull, face, jaw, teeth, tongue, eyes (and, in an export with face shapes, every vertex a
  shape moves) are weighted 1.0 to Head; the falloff to the neck is on the throat under the jawline, and clavicles
  never reach the face. From the jaw landmarks on a GNM head, from the head's own primitives on a kit character.
  `spec["rig"]["rigid_head"] = false | {"band": m, "under": m}`. On a base body the falloff is ~5 cm high (`band`):
  at 3 cm a Head-only turn of 33 deg sheared the throat into a shelf under the jaw. It still folds on a hard
  Head-only turn or nod: animate a head turn as riggers and mocap do, shared between Neck and Head (about 40 / 60).
- **Clothes follow the skin under them.** On a base body every part reads the body's weights at the nearest point
  of its surface, then the weights are evened over the garment's own mesh. A part that only reaches up beside the
  jaw (a collar, a scarf, a strap) is worn on the body: it keeps the neck's weights and does not turn with the
  head; a part that is mostly on the head (a cap, glasses) is all head. `parts.<p>.rig_head = true | false` says
  so outright (a hood that should turn with the head: true); `parts.<p>.rig_bone` binds a prop to one joint, and
  `parts.<p>.rig_attach = "<bound part>"` hands a part over to that prop's joint where it comes within
  `rig_attach_length` (8 cm) of it: a strap's end goes with its bag, the rest of it with the body.
  `parts.<p>.rig_smooth = rounds` (6) evens a garment's weights more or less.
- **Hems.** Shorts, a shirt's hem, a skirt are sheets hanging off the body, and skinning can only bend them with
  the limb under them: past ~45 deg of thigh the crotch of a pair of shorts and a loose hem fold. What game riggers
  do, in order of cost: delete the skin under the garment (the export does: hidden faces are dropped, so nothing
  pokes through), smooth the garment's weights so the hem takes some of the pelvis and of both thighs (done:
  raise `rig_smooth` on a long hem), and for skirts, coats and anything that must swing, extra bones (a ring of
  short chains from the waist, driven by the thighs or by a spring / cloth solver in the engine: Unity's cloth and
  dynamic-bone components, Unreal's Chaos cloth and its RBAN skirt chains, VRM spring bones). This rig has no hem
  bones: a skirt will follow the thighs and fold between them. Judge with `rig(pose={"LeftUpLeg": [[1, 0, 0],
  -60]}, glb=...)` and keep hems short or close-fitting if the character has to kick.
- **Model limbs clear of the body before rigging.** An arm lying against the belly is one skin with it once
  meshed: raised, it tears a slab out of the torso and trails a web, whatever the weights (the goblin did). `rig`
  prints a WARNING naming the limb and how much of its surface touches other flesh; fix the spec (joints out to an
  A-pose until air shows between limb and body, or thinner flesh there), not the weights. A rigger handed such a
  mesh would send it back, or cut the limb free and re-model the pit; weighting the fused patch to the body only
  hides the tear behind a stretched web.
- **Check the numbers.** `rig` prints, under the bone list, a twist test per chain (the hand rolled 75 and 105
  deg, the arm 60, foot and thigh 40): the skin's twist by station along the segment, what is left at the joint,
  the largest step, the worst section's area against rest (flagged CANDY WRAPPER under 0.8) and the worst
  triangles; and the head's weights by height with how far each row lags a rigid head turned 33 deg (want Head
  1.00 / 0.0 mm from the jaw up). `pose={"RightHand": ["roll", 105]}` poses a roll yourself ("roll" = about the
  bone's limb); `drive_twist=False` shows what an engine without drivers gets.
- **Limits:** decimated triangles bend less cleanly than modelled edge loops. The rest pose is as modelled (arms
  down); retargeters handle that with their retarget pose. Twist bones fix roll, not bend: a raised shoulder still
  dips and an elbow bent far still creases (linear blend skinning). Sources for the conventions: Unreal's Twist
  Corrective / mannequin skeleton docs (dev.epicgames.com/documentation/unreal-engine/animation-blueprint-twist-
  corrective-in-unreal-engine), Unity's Muscle Definitions (docs.unity3d.com/Manual/MuscleDefinitions.html: twist
  shared between a limb's two joints, no extra bones), VRM's node constraint spec (github.com/vrm-c/vrm-
  specification, VRMC_node_constraint: roll constraint for twist bones), Godot's BoneTwistDisperser3D
  (docs.godotengine.org/en/latest/classes/class_bonetwistdisperser3d.html), Cascadeur's twist-bone notes
  (cascadeur.com/help/rig/advanced_rigging/advanced_rigging_techniques/twist_bones).

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
