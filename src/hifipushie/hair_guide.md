# Hair: stylised, sculpted locks

This is about feature-animation hair: a few big designed shapes that read as hair, not thousands of strands. Each lock
is a Bezier curve in the model's Blender scene, swept with a cupped lens profile (wide and flat, thin edges, tapering
to a point) whose flat side lies on the volume under it. Hair isn't part of the SDF field, so hair edits never
rebuild the body.

Tools:
- `groom_hair(name, groom={patch}, replace, stage)`: merges a patch into `spec.hair.groom` and regrows the generated
  locks. Locks shaped by hand are kept.
- `look_hair(name, views, layout)`: the renders, plus the gates measured on them.
- `hair_reference(name, trace, image_path, apply)`: matches a reference picture.
- `edit_model` with kind `"hair.locks"` / `"hair.groom"` / `"hair"`: edits numbers directly.
- `sync(name, hair_only=True)`: puts the locks in scene.blend for a person to shape. `pull` brings their edits back.
- `export_asset`: exports the hair as its own atlas.

## How artists do it

The sources (Hossimo, Dan Eder on 80.lv, Pablander, Brooke Eggleston, Emmyroid, MelanciaComics, Scheuermann, Animal
Logic, Blender Studio, Disney's Tangled notes) agree on the order. The numbers are theirs where they give any.

1. **Plan from the reference.**
   - Squint at it, or blur it, to find the few big high-contrast chunks.
   - Find the hairline, the parting, and the whorl/crown that everything flows from.
   - A good design still reads when blurred, and from its outline alone.
2. **Silhouette first: one volume.**
   - A single solid mass fills the planned outline and covers the scalp completely.
   - It sits a little off the skull: hair has thickness, and painted-on hair loses its volume.
   - Judge it against the reference from the front, the 3/4 views and the back.
   - Animal Logic's production tool works the same way: artists model an explicit outer silhouette and the hair is
     made inside it.
3. **Big shapes: split the mass along the flow.**
   - Divide it into sections: fringe/front, top, sides, back.
   - The part makes two masses on its own.
   - Lines run unbroken from the part or crown to the tips. Long hair uses S-curves, but no two S's are the same.
4. **Clumps, layered.**
   - Each section breaks into clumps that sit on top of each other like shingles, not side by side.
   - Higher and front clumps lie over the roots of the ones below and behind.
   - The darkest values are deep in the overlaps.
   - Sizes vary on purpose. MelanciaComics' 6-3-1: big shapes ~60% of the area (they carry the silhouette), medium
     ~30% (direction, leading the eye), small ~10% (breaking up the big forms).
5. **Breakup, sparingly.**
   - Split some tips into twos and threes, leaving negative space between them. These gaps are what make hair read
     as hair rather than a carved helmet.
   - Add a few smaller clumps and one or two strays at the outline.
   - Stylised hair keeps this pass light: many thin tips read as noise ("spaghetti").
6. **Shading.**
   - Roots and gaps dark, from a root-to-tip gradient and occlusion between clumps.
   - Each lock a slightly different value.
   - An anisotropic highlight band running along each lock, shifted per lock so the bands don't line up into one
     stripe (Scheuermann's shifted Kajiya-Kay lobes, with noise on the shift).
   - Optional: a rim on the edges, and the tips a shade lighter.

What to avoid:
- **Helmet:** the volume or one smooth surface showing, with grooves drawn on it.
- **Spaghetti / noodles:** many thin locks.
- **Clay:** too few shapes, nothing separating.
- **Uniform locks:** the same width, length and spacing, with parallel tangents.
- **Twins and symmetry:** repeated shapes, mirrored sides.
- **Wig:** a hairline that doesn't grow from the skin.
- **Claws:** tips standing up off the head.
- **Curling ends.**

## The workflow with the tools

Look after every change: a look takes 4-30 s. The gates are numbers, but judge the pictures too. The clay row shows
the shapes without colour; the thumbnail shows how the hair reads small.

### 0. Setup

- The head needs face landmarks: a `base` head gives `lm_*` joints. A kit head takes `groom.centre` (a joint).
- `sync` the model once so the Blender scene exists. look_hair renders a head-cropped copy of it.
- With a reference picture, match it first (the rule: every hair look is judged against the reference, from the
  reference's own camera). Trace the image by reading pixels off zoomed crops with a grid:
  - 8-10 landmarks;
  - the part, from its front end back;
  - the hairline;
  - the visible hair outline;
  - each big clump's flow, root to tip, with its width in px.
- Then call `hair_reference(name, trace={...}, image_path=...)`. It fits the camera; expect a few px of error per
  landmark, and more means a mislabelled point. Check the returned picture: landmarks green, the reprojection cyan.
- `apply=True` carries the trace onto the head: the parting line, hairline front points, and drawn clumps along the
  traced flows, plus rows behind and on the part side that the picture can't show.

### 1. Silhouette

```
groom_hair(name, groom={"hairline": {...}, "parting": {...}, "volume": {...}}, stage="mass")
```

- The volume, in metres of hair over the scalp per region: front, top, crown, sides, back, nape.
- `ramp`: how the front rises.
- `across`: how round it is across the top.
- The hairline is a crisp, designed line: `hairline.front` (in brow-to-nose units), temples, sideburns, nape.

Check:
- Gate: the outline's dents. They must be <= 1.5 mm in front and 3/4. A pinched temple reads as a divot, and locks
  never fix that later.
- Height over the brows, width at the temples, and IoU / outline px against the trace.
- Get the outline right here: it's the one thing every later stage inherits.

### 2. Big shapes

```
groom_hair(name, groom={"drawn": [...]}, stage="locks")
```

Draw the big clumps rather than generating them on a hero head.

How to draw them:
- Each one is `{"name": "sweep1", "top": [[x, y], ...]}`, metres from the head centre seen from above, root first.
  Or use `"azel": [[az, el], ...]` on the head itself.
- `"width"`: the clump's widest, in metres. Optional: `"taper"`, `"lie"`.
- Name rows stem + number (sweep1, sweep2, ...). An under-layer clump is then laid between each pair of neighbours,
  so their parting tips show hair, not the volume.
- `look_hair(name, views=["layout"])` draws the plan from above.

Rules from the artists:
- **Count:** about 8-12 big clumps on a short or medium cut. Fewer reads as clay; more becomes a mop.
- **Hierarchy:** one or two dominant sweeps (the fringe / front sweep) wider than the rest. look_hair reports the
  hierarchy by area; aim near 0.6 / 0.3 / 0.1.
  - Widths that are all equal (spread cv < 0.2) are the "uniform locks" look: make the front sweep 1.3-1.6x the
    others and the part side 0.6-0.7x.
- **Flow:** a fan from the part (or the crown whorl).
  - Rows never cross, and tips run calmly the same way.
  - Each row is a little longer and lower than the one in front; vary the lengths so the tips don't end on one line.
- **Overlap:** front rows over the roots of the rows behind, higher clumps over lower ones. The roots lie flat; they
  don't climb out of the parting.
- **Asymmetry:** the part side short and flat, the swept side full (`parting.flat`, `parting.full`).

### 3. Secondary: sides and back

- `tiers.strip`: strips along the combed streams converging under the nape, in shingled segments.
- `tiers.gap`: gap locks wherever the volume still shows.
- Gate: bare-volume share of the visible hair < 0.10 in every view, the back too; lit bare volume < 0.03. The volume
  is filler, never a surface.
- Generated strips can read as tiles or shingles. If so, use fewer and broader locks: 6-8 broad locks brushed back to
  the nape, by hand (step 5) or as drawn clumps with `azel` paths.

### 4. Breakup

- Split the tips of a few big clumps: `"split": 2` (or `{"n": 2|3, "at": 0.6, "fan": 0.5, "keep": 0.2}`) on a
  drawn clump.
  - The clump stops a little past `at`.
  - n narrower locks start there, lie over it and fan apart.
  - The gaps between them are the negative space.
- Use it on 2-4 clumps, mostly at the outline and the fringe, not everywhere. Twos more than threes.
- One or two small locks where the outline wants a break (a stray at the crown or temple) can be drawn too.
- Gate: the clump steps at the outline (notches) should read: 2-5 mm. A perfectly smooth outline reads as a helmet;
  steps much deeper than that read as spikes.

### 5. Hand-shaping (when numbers won't get it)

- `sync(name, hair_only=True)`, then edit the curves in scene.blend: points, handles, Alt+S radius, Ctrl+T tilt, the
  modifier's Width / Thickness / Taper / Belly / Root / Edge. Shift+D adds a lock; X deletes one.
- Then `pull`. Edits come back as `"hand": true` locks that a regrow leaves alone; new curves come back as new locks;
  deletions go to `hair.removed` and are never regrown.
- A person can do this in their own running Blender: sync and pull use the live session.
- Single numbers can also be changed without Blender:
  `edit_model(name, [{"op": "set", "kind": "hair.locks", "name": "sweep3", "value": {"width": 0.07}}])`.
  Add `"hand": true` in the same value to keep the change through a regrow.
- What has worked:
  - A few BROAD locks (7-10 cm wide, ~6 mm thick, thin edges `edge` 1.6) lying on the volume, with a steady tilt.
  - A top fan from the part.
  - Sideburn, nape and behind-ear locks for coverage.
- To fix a gate dent: find the lock that makes that height of the outline and pull it out 2-4 mm.

### 6. Material

Material settings go in `spec.hair.look` (sRGB hex colours):

| Setting | What it does |
|---|---|
| gap, lit | the dark-to-lit range |
| root, edge | how far root and edges darken |
| vary | value per lock |
| sheen, sheen_amount | the band along the crown |
| band_shift | how far each lock's band slides along it: keep it above 0, or the bands line up into one stripe |
| grooves, groove_depth | strand grooves as bump: soft, uneven |
| anisotropic, roughness | highlight shape |
| tip, tip_amount | tips lighter or warmer |
| grey | greying (where: groom.grey) |

- All of this lives in the material, and the export bakes it into the maps. It never goes into geometry.
- Judge it with the material on AND in clay, and in close-ups (views "close", "close_back").

### 7. Export

`export_asset` includes the hair:
- The locks at 24 x 10 plus the underlayer.
- Its own atlas, with KHR_materials_anisotropy (along the lock) and sheen.
- Bound rigidly to `parts.hair.rig_bone`.

## What goes wrong, and the fix

| Symptom | Fix |
|---|---|
| Tips standing up (claws) | `lie` lower, the tip tucked onto the layer below |
| Ends curling | fewer control points; the tip's tilt from the point before |
| A mop | too many small locks at mixed angles: fewer, broader, one flow |
| Helmet | volume visible between clumps: widen and overlap the big clumps, add under clumps, split some tips |
| Tiles or shingles on the sides | uniform generated strips: broad hand or drawn locks |
| Comb | equal tips on one line: vary lengths; split only some |
| One highlight stripe across the head | band_shift up |

Adding small locks makes every one of these worse. Fix the big shapes first.

## Sources

- Hossimo, [The right way to think about doing hair as an artist](https://hossimo.com/articles/tips-and-tricks-an-artist-friendly-approach-to-sculpt-groom-hair/):
  primary / secondary / tertiary, no scalp at the first stage, the blur test.
- Dan Eder (80.lv), [Sculpting stylized hair in ZBrush](https://80.lv/articles/guide-sculpting-stylized-hair-in-zbrush):
  blockout first; repetition, wobble, symmetry and clipping as the common mistakes.
- Pablander Academy, [Sculpting stylised hair in ZBrush](https://www.pablander.academy/tutorials/sculpting-stylised-hair-in-zbrush):
  squint for the big chunks, volume then crevices.
- Brooke Eggleston, [How to draw and design hair for characters](https://brookeseggleston.com/blog/how-to-draw-and-design-hair-for-characters):
  big / medium / small, the part as two shapes, S-curves, negative space, the wig look.
- Emmyroid, [Clip Studio tips](https://tips.clip-studio.com/en-us/articles/10830): ribbons, the whorl and part, no
  repeated S, "grass", shadow / highlight / rim.
- MelanciaComics, [Clip Studio tips](https://tips.clip-studio.com/en-us/articles/15907): the 6-3-1 size rule.
- 80.lv, [Voluminous hair](https://80.lv/articles/004adk-005cg-cgma-student-project-voluminous-hair): opaque layers
  first, root gradients, a grey value per strand group.
- Scheuermann, [Hair rendering and shading (ATI, GDC 2004)](https://web.engr.oregonstate.edu/~mjb/cs557/Projects/Papers/HairRendering.pdf):
  two shifted anisotropic lobes, noise on the shift, AO.
- Animal Logic, [Hair Tubes (SIGGRAPH Asia 2023)](https://animallogic.com/wp-content/uploads/2023/12/HairTubes.pdf):
  artists model the silhouette as a mesh and strands are made inside it.
- Blender Studio, [Procedural hair nodes](https://studio.blender.org/blog/procedural-hair-nodes/): strand / clump
  tools; for big stylised locks, curves with a profile remain the editable choice.
- AWN, [Rapunzel lets her hair down](https://www.awn.com/animationworld/rapunzel-lets-her-hair-down-tangled): rhythm,
  volume, twist and a designed swoop.
