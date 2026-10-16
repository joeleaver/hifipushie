# Blockout, strokes and parts

Read guide(topic="") (the playbook) first: describe the reference, then work big to small.

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
- Footwear (and gloves, tight garments): `"shoes": {..., "hides": ["body", "socks"]}` (soles too) hides the skin
  the shoe encloses, so a toe spring or a slim last never shows toes through it. The body's shape is untouched.
- Seated joints root attachments on the surface: `{"on": {"at": "face_mouth_corner.L", "offset": [...]},
  "lift": -0.003, "r": 0.0065}` for a tusk's root, and the same address with `"shift": [dx,dy,dz]` for its
  tip. They follow the surface when the face or body changes.
