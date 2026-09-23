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
6. **Paint** last (section 5): it doesn't change the shape, so it can't break earlier stages.

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
- **Check coverage** in `look`'s info line: a layer covering NOTHING is misaddressed; one covering far more
  than you meant has a mask too loose (`within`, `range`).
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
- **Relief without sculpting:** `"height": -0.001` on a cells layer grooves the scale borders; `0.002` on a
  cells-distance layer raises warts. It lands in the exported normal and height maps at texel resolution;
  `look` only tilts vertex normals, so judge it in a close-up with `shading="raking"` and in the export
  preview. Sculpt forms bigger than a few voxels with strokes instead.
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
- `triangles` ~15k suits a hero creature; 5k for a crowd; a furnished building 50-100k. `texture=1024` for
  quick checks, 2048 to ship.
- Triangles follow geometric error, not area: one decimation of all parts together decides each part's share,
  so flat walls get few and small round things (eyes, pots, pillows) enough; every part gets at least
  max(300, triangles/100). Steer it per part with `parts.<p>.triangle_weight` (x its share).
- Texels: every part gets the same texels per metre unless `parts.<p>.texel_density` says otherwise (2 = twice
  as sharp, four times the atlas area). `parts.<p>.texel_focus: [{"at": "head", "radius": 0.15, "density":
  2.5}]` gives a region more (a character's face: the troll's went from 1.5 to 0.8 mm/texel at 1024).
- Read the log: the atlas fill and mm/texel per part. A creature fits one atlas (troll ~58% filled); a big
  environment doesn't (the cabin's 380 m^2 of logs and shingles gives ~30 mm/texel on one 1024 atlas). Give
  parts their own atlas with `parts.<p>.atlas: "interior"` (one material each in the GLB), or
  `export_asset(atlases=n)` to split the rest by load; keep what's seen close up (interior, props) apart from
  what's big and seen from afar.
- Detail thinner than about a voxel at the export resolution (22 mm shingles at 256 across a 6 m cabin) makes
  a broken high mesh: inverted faces and normals the bake can't use. Those texels keep the low-poly surface
  (the log says how many per part). Build at a higher resolution or make the detail thicker.
- Judge the preview and close-ups (`asset.preview` focus/zoom; `hide=["roof", "walls"]` to see inside) for
  seams and the normal map's read.

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
