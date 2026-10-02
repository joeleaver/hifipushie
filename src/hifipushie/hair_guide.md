# Hair: stylised, sculpted locks

This is about feature-animation hair: a few big designed shapes that read as hair, not thousands of strands. Each lock
is a Bezier curve in the model's Blender scene, swept with a cupped lens profile (wide and flat, thin edges, tapering
to a point) whose flat side lies on the volume under it. Hair isn't part of the SDF field, so hair edits never
rebuild the body.

Tools:
- `groom_hair(name, groom={patch}, replace, stage)`: merges a patch into `spec.hair.groom` and regrows the generated
  locks. Locks shaped by hand are kept. `drawn` can be patched by name instead of resent whole:
  `{"drawn": {"sweep2": {"width": 0.07}, "qf*": {"root": 0.12}, "fringe": null, "stray1": {"azel": [...]}}}`
  (patterns match several clumps, null drops one, a new name is added).
- `look_hair(name, views, layout)`: the renders, plus the gates measured on them. Views include `close_front` and
  `close_side` for the hairline and the part.
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
- Put a landmark beside the ear in the trace (`lm_jaw_0.R` or `.L`, the face's edge just in front of the ear at
  eye level). Face landmarks alone barely fix the camera's pitch, and the cranium is what hair sits on. On the
  golfer, the face-only camera put the bare skull at the reference's hair top, so every outline number on top was
  wrong by ~10 mm. One ear point moved the IoU from 0.60 to 0.73 with no change to the hair.
- Match every view of the character you have: `trace["views"] = {"far": {landmarks, hair, hairline, part?, clip_y,
  crop}}`. A view can be another figure in the same picture (it shares the lens, so only the pose is fitted) or
  another picture, such as a turnaround's side or back (give it its own `"image"`). Each view gets its own matched
  row and its own numbers in look_hair. Where two views disagree by more than the camera error, no single fix will
  satisfy both: split the difference and say so.

### 1. Silhouette

```
groom_hair(name, groom={"hairline": {...}, "parting": {...}, "volume": {...}}, stage="mass")
```

- The volume, in metres of hair over the scalp per region: front, top, crown, sides, back, nape.
- `ramp`: how the front rises. About 0.03 gives a quiff's rolled front. 0.02 is a wall the front locks jut over;
  0.06 leans the front back into a slope.
- `across`: how round it is across the top.
- `crest`: where across the head the top's crest runs (x in metres, his left positive). On a side part, put it just
  across the part on the swept side (golfer: 0.025): the quiff is highest there and falls away toward the swept
  side.
- `taper` `{"from": el, "to": el, "floor": f}`: sides and back keep their full volume down to elevation `from`
  (degrees), then ease to `floor` x that volume at `to`. This gives short tapered sides and back under a full
  occiput, instead of a bucket that is as full at the nape as higher up.
- `parting.full` piles volume onto the swept side. On the golfer it was the main reason that side stuck out 12 mm
  too far: set it from the outline numbers, not by eye.
- The hairline is a crisp, designed line: `hairline.front` (in brow-to-nose units), temples, sideburns, nape.

Check:
- Gate: the outline's dents. They must be <= 1.5 mm in front and 3/4. A pinched temple reads as a divot, and locks
  never fix that later.
- Height over the brows, width at the temples, and IoU / outline px against the trace.
- The outline per head region, in every matched view: front, top, side.L/R, back.L/R, back.
  - Each ray from the head centre is labelled by the part of the volume that makes the outline there.
  - `err` = ours minus the reference, in mm; + means ours sticks out further.
  - `ref_hair` / `our_hair` = how far each outline stands outside the bare head. A negative `ref_hair` means the bare
    head is already outside the reference there: hair can't fix that, so check the camera or the head.
  - `over_brow_mm` = [reference, ours]: the hair's top above the brows.
  - Change the region named, by the millimetres given.
- Measure before you decide what is wrong. On the golfer, "the hair hugs the skull" turned out to be hair 10-14 mm
  TOO TALL, too full on the swept side and thin at the back sides. What read as flat was the front's shape and the
  locks.
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
- **A quiff's front:** 4-5 rows from the part sweeping across and down over the far temple. Make the front two big
  (8-9 cm wide) and the rows behind 5.5-6.5 cm. Lay the front row 2+ cm behind the hairline, so it rides the front
  roll; laid along the hairline, it sits in the ramp and dips and twists. Draw gentle arcs: chevrons twist a wide
  lens. On the golfer, seven traced rows plus their under clumps in the front 6 cm stacked into slats and flakes.
- **Keep paths inside the hairline.** A clump that crosses the hairline drops to the skin there and stands up again
  as a fin. (On the golfer, the part-side clump curled past the temple.)
- **Folds:** look_hair lists "folded locks". These are places where the spine turns within the lock's own half width,
  so the inner edge runs backwards and the lens crumples into flakes. Ease the path or narrow the lock.
  - Drawn clumps are eased automatically on the head (`hair.ease_bends`).
  - A root takes the next point's tilt.
  - A root dives just under the underlayer, not to the scalp. Sent to the scalp, it climbed 2 cm in its first
    centimetre and folded: those were the flakes along the part.
- **Find the culprit:** `look_hair(name, views=[...], only=["pside*", "sweep1"])` shows only those locks on the
  underlayer, so you can see which locks make a busy patch.

### 3. Secondary: sides and back

Draw the sides and back as rows of broad drawn clumps on the head (`azel` paths), not as generated tiers. This
worked on the golfer test head (hair_t13): 47 locks, back bare share 0.07, a calm combed read.

```
{"name": "bk1", "azel": [[141, 68], [112, 54], [118, 36], [124, 14], [129, -12]], "width": 0.07, "taper": 0.7}
```

- **Upper back row** (bk1..bk5): roots at the crown (el ~65), tips half-way down the back. Converge them a little
  toward the back centre (az 180), and make the middle widest (0.09) and the ends narrower (0.065).
- **Lower row** (nk1..nk5): roots just under the upper row's tips, tips at the nape hairline. This row tucks under
  the one above, like shingles.
- **Sides, per side:** 2-3 sweeps from near the part or temple back to behind the ear (sideR1..3, sideL1..3), each
  lower one narrower.
- **Blunt tips:** taper 0.7-0.8. Pointed wedges side by side leave a row of bare triangles.
- **Under clumps:** each row's under clumps (between neighbours, automatic) show in the wedge gaps
  (`drawn_under`: a sink of 0.35 by default). Per row: `{"sweep": 1.0}` buries them, false drops them.
- **Gate:** bare-volume share of the visible hair < 0.10 in every view, the back too; lit bare volume < 0.03. The
  volume is filler, never a surface. Some of the front's share is the parting's own shadow line: judge that one in
  the picture.
- **Generated tiers:**
  - `tiers.strip` (shingled strips to the nape) read as tiles.
  - `tiers.gap` at 4 cm made a mop of small locks at mixed angles.
  - Use them only for quick coverage, never on a hero head. If you do, gap locks should be broad (6 cm) and kept to
    sides/back/nape.

### 3b. The hairline and the front

The hairline is one designed line, and the front's strands come out of it at an angle. look_hair measures both in
every matched view:
- **hairline edge**: the rendered hair's edge against the skin, followed along the traced hairline.
  - `rough_mm` (rms against its own running median) should be <= 1, and `tooth_mm` (the worst tip or notch) <= 3.
  - `teeth` names the lock that makes each tooth.
  - `holes` is skin showing just inside the edge.
- **strand direction just inside the hairline**: the strands' angle to the hairline, read off the reference and our
  render alike (structure tensor) in the band 4-28 mm inside it, in 6 stretches. 0 runs along the hairline like a
  headband; 90 comes straight out of it. On the golfer the reference reads 10-30 degrees: a shallow diagonal, not
  perpendicular.
- **where the bare volume shows**: by head region, "hairline" meaning within 15 mm of it.

What worked on the golfer (workspace/hair_r3, renders hr01-hr04):
- **Front locks grow out of the edge.** Draw 3-4 front locks rooted along the hairline from the part's corner,
  rising at the reference's angle and sweeping over to the far temple, with `"root": 0.1-0.15, "climb": 0.025`.
  - The narrow root comes out of the layer and the lock's body forms 2-3 cm back.
  - With full-width roots, a row of root ends read as scales along the forehead.
  - A lock drawn along the hairline (a fringe) reads as a headband.
- **`to_hairline`** (on a drawn clump): an inset in m, negative to tuck it into the skin, or `{"inset", "reach"}`.
  The clump is moved across so its edge runs along the hairline, and cupped so that edge comes down onto the layer.
  Good for one lock that should BE the edge. Don't use it at a temple corner: offsetting a path round a tight
  corner folds it.
- **`groom.hairline_edge`** `{"inset", "reach"}` does the same for every clump whose edge comes within `reach` of the
  hairline. On the golfer it bent the side rows round the temples into folds; prefer per-clump.
- **A root drawn on or past the hairline grows out of the skin** (its end is buried).
- **`volume.edge_sink`** (0..1): the underlayer's front edge sunk under the front locks. Unsunk, it stands up as a
  dark lip under the quiff. With a gentle `ramp` it hardly matters.
- **`parting.front`** (m, default 0.015): the part's dip fades in that far behind the hairline. Dipping right to
  the edge, it cut a V notch.
- The underlayer's rows follow the hairline, and traced `front_points` ease onto the default line at the temples.
  On a fixed grid the rim was a staircase of fine serrations; the old join stepped 4 mm at the temple corner.

### 3c. Fins, blunt root ends, folds

- **fins**: a lock edge standing over the layer by more than its own thickness + 3 mm. A wide flat lock laid
  across the volume's shoulder stands on one edge.
- **blunt root ends**: a lock's width where it rises out of the layer, times how steeply it rises. Over 15 mm, the
  cut end shows: crescent fins along a parting in the side view, scales along a hairline. Lower `root` (0.1-0.2) and
  raise `climb` (0.02-0.03 m) on rows that start at a parting or the crown.
  - Not on the side rows: their narrow roots left the temples bare (bare share 0.09 -> 0.13).
- **Folds at u ~0.15 on short rows** (the nape) were the root's climb out of the layer. On a lens tilted ~35
  degrees, that bend lies in the lens's own plane. They are hidden under the row above, but real.
  - Now the climb takes at least 12 mm (`climb`), and the root's tilt is half the lie's (ROOT_TILT).

### 4. Breakup

- Split the tips of a few big clumps: `"split": 2` (or `{"n": 2|3, "at": 0.6, "fan": 0.5, "keep": 0.2}`) on a
  drawn clump.
  - The clump stops a little past `at`.
  - n narrower locks start there, lie over it and fan apart.
  - The gaps between them are the negative space.
- Use it on 2-4 clumps, mostly at the outline and the fringe, not everywhere. Twos more than threes.
- Check every split in clay. A split in the middle of the top hardly shows: the clump on top covers it. The split
  pays off at the outline, at the tips of the fringe, and over the ears and nape.
- One or two small locks where the outline wants a break (a stray at the crown or temple) can be drawn too.
- The size hierarchy (look_hair) counts small locks as narrower than 0.4x the widest:
  - A 2-way split of a big clump only makes medium locks.
  - 3-way splits on the nape and swept-side rows, plus 3-5 strays (2-2.5 cm wide, `root` 0.3) at the crown, over
    the ears and at the far temple's outline, took the golfer from 0.8 / 0.2 / 0 to 0.64 / 0.27 / 0.09.
  - Narrowing the outer back rows and two side rows to ~5.5 cm moved them to medium.
  - Don't split the dominant front sweep. Splitting it re-laid the whole front (direction error 20 -> 26 deg) and
    raised a 13 mm fin.
  - 3-way splits at the nape read as a comb from behind: twos there if the back shows.
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
| Jagged, torn hairline | `teeth` in the hairline-edge line names the lock: narrow its root, or lay one front lock with `to_hairline` |
| A dark band under the quiff | "where the bare volume shows" says front hairline: front locks rooted at the edge, `volume.edge_sink` |
| A headband across the forehead | the front lock runs along the hairline: compare the strand direction with the reference, re-lay it diagonally |
| Scales along the hairline, crescents at the part | blunt root ends: `root` 0.1-0.2, `climb` 0.025 |
| A lock on its edge (fin) | the fins line names it: narrow it, lower `lie`, or move it off the volume's shoulder |

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
