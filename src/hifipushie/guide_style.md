# Style: how far from realism (5c)

Read guide(topic="") (the playbook) first: describe the reference, then work big to small.

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
