# The spec format and the workflow in brief

Read guide(topic="") (the playbook) first: describe the reference, then work big to small.

hifipushie models characters and creatures as a skeleton (joints + bones) with SDF blobs hung on it,
smooth-blended into one surface, meshed, and rendered as clay for you to look at.
Call `guide` once before modelling: it's the playbook (stages, stroke rules, parts, what goes wrong).

Conventions: metres, Blender axes. Z up, the creature FACES -Y, its left side is +X.
Names ending ".L" are auto-mirrored to ".R" across X, so store only the centre line and the left side.

Spec:
  joints: {name: {"pos": [x,y,z], "r": radius}}            joints don't render alone
  bones:  {name: {"a": joint, "b": joint, "r_a"?, "r_b"?, "flat"?: [width_scale, height_scale],
                  "blend"?, "op"?: "add"|"subtract", "layer"?: int, "group"?: str, "join"?: m}}   round cone
  blobs:  {name: {"at": joint | [x,y,z] | {"bone": name, "t": 0..1}, "offset"?: [x,y,z] (world axes),
                  "size": [rx,ry,rz] (semi-axes), "rot"?: [deg x,y,z], "blend"?, "op"?, "layer"?}}  ellipsoid;
          "shape": "blade": a thin rounded sheet (ears, leaves, fins, feathers), size [half width, half length
          (along local y), half thickness], "taper" 0..1 (narrower tip), "cup" m (edges lift to +z: an ear's
          hollow), "bend" m (the +y tip lifts to +z)
  kits:   {name: {"type": "hand" | "face", ...}}   parametric parts that expand into joints/bones/blobs
  anatomy: {} turns on modelling lore by joint type (found from the skeleton): every limb root (shoulder, hip, a
          quadruped's legs) gets a cap over the joint (deltoid, glute flare), the pit's folds (pec/lat beside the
          body) or a round mass behind (glute, triceps, for a limb leaving the body's end), and the joint's bones
          slim to bone size there, so limbs aren't balls plugged into the body. Per joint: {"shoulder.L": {"bulk",
          "cap", "front", "back", "insert", "narrow", "blend", "off"}}. Model limbs clear of the torso for rigging.
  parts:  {name: {"shell"?: base part, "offset"?, "color"?}}; any element takes "part": name (default "body").
          Each part is a separate mesh (and material later): eyes, teeth, clothing. A shell part is its base
          pushed out by offset, cut to its own layer-0 adds (a garment's region); strokes on it make folds.
          "hides": ["body", ...] (or {"parts", "margin" 0.001, "reach" 0.02, "rim" 0.004}): faces of those parts
          this part encloses (and poke-through patches ringed by it) are not drawn and are culled on export
          (shoes over feet, gloves, tight garments): the cover can take its real shape over the body.
  joints may be {"on": surface address (as for strokes), "lift", "shift", "r"}: seated on the surface
          (a tusk rooted on the lip, a horn on the skull), following it when the model changes.
  strokes: {name: {"op": "clay" | "crease" | "flatten", "path": [surface points], "width", "depth", ...}}
          sculpting on the surface itself (see below)
  paint:   {name: {"color": [r,g,b] | "#rrggbb", "opacity"?, "part"?, masks...}} colour layers applied in order
          over each part's clay colour; masks (multiplied): path (surface addresses, like strokes), near
          (elements or a kit), facing (normal direction), axis (world or along a bone), cavity, noise, ao,
          thickness, cells; or a "mask" stack with blend modes, breakup, levels, blur. "height" adds relief.
          Paint never changes geometry, so repainting is quick (see below).
  prefabs + instances: reusable pieces placed with a transform; "array" on a bone or blob repeats it (logs,
          planks, legs), with jitter; "tags" name groups; box/cylinder shapes, "hollow", cuts with "targets".
          kit_reference (REPETITION AND SOLIDS) documents them. Props and environments work too.
  top level: "blend" (default smooth-union radius, ~0.02-0.05 for a 1m creature), "symmetry".
Combination order: by layer, adds before subtracts within a layer. Use layer 1 for things that must sit
on top of carved areas (eyeballs in sockets). Bones/blobs sharing a "group" (e.g. the segments of a tail
or tentacle) are joined among themselves first, with a small "join" blend (0 = hard min; ~1/3 of the
radius rounds a bend without bulging), then blended into the body once: chains of fully blended
segments otherwise bulge at every joint.

Realistic humans: start from spec["base"] (a MakeHuman body + a GNM head, shaped by parameters), not from blobs
and kits; the playbook's section 4d. The skeleton-and-blobs approach below is for creatures, cartoons and props.
Kits: prefer them to hand-placing fingers and facial features. {"type": "hand", "wrist": "wrist.L"} under
"hand.L" makes a mirrored hand (fingers, spread, curl, thumb). A "face" kit on the head joint places eyes
with lids, brows, nose, lips and cheeks by rough position and seats each onto the head's actual surface,
so depths come out right and follow edits to the skull. Every parameter has a proportioned default;
kit_reference lists them. get_model shows the generated names (face_eye.L, hand_f2_3.L, ...), which you
can measure along, hang blobs on, or focus on. fit leaves kit output alone but it follows its anchors.
Strokes are how you sculpt once the forms are blocked out: each one displaces the existing skin along a
path addressed on the surface ({"bone": "forearm.L", "t": 0.3, "side": [0,-1,0]} = out from that bone
toward the front; {"at": joint, "offset", "dir"} = raycast), with a width, a depth and a profile (how hard
its edge is). clay = muscle masses, fat pads, ridges; crease = folds, wrinkles, grooves; flatten = planes.
"repeat" lays out a set (wrinkles, ribs) from one entry. They follow the surface and move with the bones.
Keep them broad and shallow relative to the part (a few mm on a 3 cm arm); widths under ~2 voxels alias.
kit_reference documents them fully.
Paint colours the finished surface (vertex colours, exported in the OBJ): base colour, countershading
(facing), markings along surface paths (with repeat/scatter for stripes and spots), regions around elements
(near: "hand.L", "face_eye.L"), dirt in creases (cavity), mottling (noise), and procedural weathering from
the surface itself: a "mask" stack combines generators (ao, cavity, thickness, facing, noise with warp/stretch,
voronoi cells, paths...) with blend modes, and "breakup" turns them into edge wear, grime and dust. A layer's
"height" adds fine relief (pores, scales, cracks) to the exported normal/height maps. ".L" layers mirror. Painted
looks render the model's Blender scene (EEVEE, paint as shader nodes, per pixel); judge with look(shading="flat")
(unlit colour) and look(paint_layer=...) to see one layer's mask (orange on grey clay): a layer that lights up
nowhere is misaddressed. kit_reference documents it fully, with recipes.
The Blender scene (workspace/<model>/scene.blend, `sync`) is the model's live, editable form: a person can open
it, move props and tweak exposed paint numbers, and `pull` / the next sync / look brings those edits back into
the spec. AO and sky there are per asset: a prop shades only itself, the building only itself.
export_asset makes the game-ready version: low poly + UV atlases (per-part texel density, texel_focus for
faces, triangle_weight) + PBR maps (basecolor, normal, roughness,
metallic, specular, ao, orm, height) and a GLB: normal and height texel by texel from the exact model, paint and AO
baked by Cycles from the Blender scene; paint layers carry roughness/metallic/specular too. Check the exported GLB re-imported into Blender and rendered in EEVEE set up like a game (the glTF importer's materials, alpha clip / hashed cards, no ray tracing) (and close-ups of the face) before calling it done.
Close-ups (look with focus + zoom) rebuild just that region at full resolution: use them to judge
faces and hands.

Workflow, in stages; after each, run check (and look) and fix before moving on. Going back is fine.
  1. Plan: set_plan with front and side outlines (2D ellipses/capsules/polys in world units), landmark heights
     (chin, shoulders, navel, crotch, knees... in head heights) and a few sections (width x depth at the
     chest, waist, hips, thigh). Look at the returned sheet and get the proportions right here, where it's
     cheap. With reference art, trace the plan from it.
  2. Blockout: put_model with the skeleton and big masses; tie landmarks to joints; then fit (against the
     plan) and check until silhouettes, landmarks and sections agree.
  3. Secondary forms: strokes for muscle masses, fat pads and planes; judge with look shading="raking" /
     "curvature" and strokes=True; check again (strokes shouldn't break the silhouette).
  4. Detail: creases, wrinkles, repeats and scatters, in close-ups.
  5. History: the spec's "story" (age, climate, use, directions, events), turned into geometry: weather ops
     (sag, lean, settle, jitter), lumpy, chips, things out of place. Nothing real is pristine; check audits it.
  6. Paint: base colours per part, then broad zones (countershading, limbs), then markings, then dirt/mottling,
     weathering from the story (facing the weather side, sky-exposed vs sheltered, wear paths).
Without a plan: put_model -> look -> edit_model in small batches -> look ...
If you have reference art, set_reference per view then compare. Once the body plan is right, fit
auto-adjusts joints, radii and blobs to the reference outlines; use compare's band tables for what fit can't
do (missing parts, wrong topology).
Renders can mislead about thickness; measure gives cross-section widths along a bone chain or world axis.
look can hide parts, clip with a plane (floor plans, cross-sections) and add perspective cameras (inside a
room); clearance checks walkable floor, headroom and door widths of environments.
Every change is checkpointed; history/revert let you experiment freely.

Hair is curve locks in the Blender scene, not part of the field: read guide(topic="hair"), then groom_hair (grow locks
from spec.hair.groom) -> look_hair (renders + gates: outline dents, bare volume, fit to a traced reference) -> groom_hair /
edit_model kind "hair.locks" ... ; hair_reference matches a reference picture (camera from face landmarks, traced part,
hairline and clumps carried onto the head); sync(hair_only=True) puts the locks in scene.blend, pull brings hand edits back.

Clothes are sewn, then finished: spec["cloth"] garments are drafted to the body's measurements (FreeSewing designs or
your own pattern pieces), sewn and settled by Blender's cloth sim, cleaned up, with seams/stitching/hems from the
pattern. Work in a maker's stages (guide(topic="cloth")): design_garment (the design sheet: kind, fabric, fit, every
construction choice; garment_reference lists them) -> look_pattern (the flat pattern sheet + checks: seams, ease, each
choice evidenced) -> check_garment (construction plan, arrangement on the body) -> dress (quality "draft" first; it
refuses to simulate over construction failures) -> look_cloth (renders, strain map, report, numeric targets) -> final.
Fit and hang are fixed in the pattern, never in the solver; made pieces are built on the drape; local faults (a
band's lay, a lapel's roll, a fold too many) are finished by hand on the draped result, as studios do. States worn / draped (tablecloths, blankets) / hung;
sync(cloth_only=True) puts garments in scene.blend, pull brings colour and sculpt edits back.

Terrain (landscapes and game levels) is separate: a height field described in a level designer's words (a basin, a
pass, a village site, a road, forest here, "this must be visible from there"). Read guide(topic="terrain"), then
set_terrain -> check_terrain / look_terrain -> set_terrain(patch=...) ... -> export_terrain. When the world's kind is one
the tool doesn't know, it returns questions for the designer: ask them, don't answer them yourself.
