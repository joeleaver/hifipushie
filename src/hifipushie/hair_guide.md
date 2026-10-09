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

# Hair: soft, loose hair as strand cards

Sculpted locks (above) are the feature-animation answer. Soft, loose, wavy or tied hair is made another way in games:
**hair cards**. `spec.hair.style = "cards"` draws the same locks as cards; everything above about silhouette, flow,
hierarchy and the hairline still holds, because a lock stays the unit you design and edit.

## How game artists do it

The sources (listed at the end) agree on the method. Numbers are theirs.

1. **A strand atlas.** A handful of pictures of strand clumps, each running root to tip: usually 6-8 of them, in a
   density hierarchy. Sykutera's curly-hair atlas: 2 for volume, 3 for breakup, 1 of clumped strays and fly-aways, 1 of
   short curls for the neckline. They are baked from a real strand groom (XGen, Blender hair curves, FiberShop,
   Hair Card Designer, Fiberbake) or painted. Each picture comes as several maps: colour, **alpha**, and the three an
   engine hair shader asks for: a **root** gradient (root-to-tip colour ramp), a per-strand **ID** (value variation)
   and **depth** (strands deep in the clump darker, less specular; Unreal also offsets pixel depth with it), often
   packed in one texture, plus a normal or flow/tangent map.
2. **A hair cap first.** A "hair helmet" textured as hair under everything, so no scalp shows between cards and the
   head already has the hair's base shading. Where the cap meets the skin, the scalp itself is painted with a hairline
   shadow.
3. **Cards in layers, most opaque first** (80.lv, CGMA, Polycount):
   - a **base layer** of broad, nearly opaque cards blocking in the whole structure;
   - one to three **breakup layers** of less and less opaque cards over it (clumps of 2-3 cards each);
   - **fly-aways**: single-strand cards standing off the silhouette;
   - last, the **transitions**: the hairline, temples, nape and ears, with short **baby hairs** (4-5 variations
     round the neck, ears and temples, 2-3 on the forehead in the 80.lv ponytail).
   Cards are few-segment strips, with edge loops only where they bend; a lengthwise fold or cup gives them body.
   Roots are widened to hide the scalp. Leave negative space between clumps of curls.
4. **Tied hair** (the 80.lv ponytail): cover the scalp with cards that run to the tie; define the tail's volume
   with longer cards; then breakup cards, fly-aways and baby hairs. The tail hangs from the tie under gravity and
   is fullest a little below it.
5. **Shading.** Two-sided, one normal for both faces, bent toward the hair volume's own normal (transferred from
   the cap or a proxy) so the mass shades as one soft form; anisotropic highlight along the strands, shifted per
   strand by the ID map (Scheuermann); the root darker, tips lighter and more transparent; ambient occlusion baked
   per layer into vertex colours.
6. **Alpha.** Alpha blending sorts badly, so cards are drawn alpha-tested with dithering + temporal AA, or
   alpha-to-coverage (hair "doesn't need blending, just alpha testing", and coverage antialiases it); mips must not
   erode the alpha (visible scalp gaps come from too little overlap in the base layer or from mip erosion).
7. **Budgets.** Marketplace game hair: 10-15k triangles "low", 25-37k "mid"; hero hair in current AAA games up to
   ~100k. A whole character of the previous generation was 25-30k. Textures 1-2k for one head of hair. Three LODs,
   the far ones dropping the upper layers and fly-aways.
8. **Tools worth knowing:** GS CurveTools (Maya: cards bound to curves, so the groom stays curve-editable: what
   our locks are), Hair Card Designer and Fiberbake (Blender: atlas baking + card grooming), FiberShop (atlas
   baking), Unreal's Hair Card Generator (clusters a strand groom into clumps, one card per clump, textures shared
   between similar clumps).

What reads wrong: **plates** (cards too wide, too few, too opaque at the tips), **helmet** (no fly-aways, a clean
outline), a **hard hairline** (no fade, no baby hairs), **scalp gaps**, **one-sided shading** (cards dark from
behind), a **stiff tail** (no wave, every card the same length), **spaghetti** (only sparse cards, no base).

## What the tools do (cards)

- `hair.style: "cards"`: every lock becomes a stack of cards inside its own lens: a dense layer underneath, clumped
  cards over it, wisps on top, fly-aways off it. The lock is still the Bezier curve you edit (numbers, or in
  Blender + pull).
- `hair.strands` (all optional):

  | key | what |
  |---|---|
  | wave, wavelength | m the lock swings side to side, m per swing. Full on free hair, a third on hair lying on the head |
  | curl | 0..1: how much of the wave leaves the lock's plane (1 = ringlets); free hair only |
  | random | how far cards differ in phase, amplitude, length |
  | clump | strands in the pictures gather into pointed sub clumps |
  | frizz | single strands wander |
  | flyaway | stray single-hair cards per card |
  | layers | 1-3 card layers per lock |
  | card_width | m, the widest card |
  | tips | how ragged the ends are |
  | baby | baby hairs per cm of hairline (0 = none) |
  | soft | m over which the hairline breaks up into strands |
  | round | how far normals bend to the volume's (soft shading) |

  A lock can carry its own `"strands": {...}`.
- The atlas is generated (8 tiles: dense x2, medium x2, sparse x2, fly-aways, baby hairs; colour + alpha, normal,
  and an aux map: root / id / depth / alpha).
- The underlayer is the hair cap: it wears a dense tile whose ragged end lies on the hairline.
- **Tied hair**: `groom.tie` (see groom_hair): hair gathered over the head to a tie point, a tail that leaves it
  (free under gravity, coiled into a bun, or plaited), the strands that escaped, the band.
- Locks that leave the head are `"space": "xyz"` (metres from the head centre) with `"free": 1`: their underside
  is hair, not the dark gap side (solid locks too).

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
\n
More sources (cards):
- 80.lv, [Creating a ponytail hairstyle with Maya XGen and Unreal Engine](https://80.lv/articles/creating-a-ponytail-hairstyle-with-maya-xgen-unreal-engine/):
  scalp cards first, the tail's volume with longer cards, breakup, baby hairs (counts), FiberShop bakes, GS CurveTools, 3 LODs.
- 80.lv, [Creating hair for real-time projects](https://80.lv/articles/creating-hair-for-real-time-projects/):
  diffuse / alpha / depth / ID / root maps, layers placed by opacity, pixel depth offset.
- 80.lv, [Tips and tricks on hair for games](https://80.lv/articles/tips-tricks-on-hair-for-games/): opaque base,
  then breakup layers of less opaque cards, clumps of 2-3 cards, hairline and fly-aways last, AO per layer in the vertices.
- Thomas Sykutera (Games Artist), [Curly hair breakdown](https://gamesartist.co.uk/curly-hair-character-breakdown-thomas-sykutera/):
  the atlas's hierarchy, ~6 clump and 5 fly-away meshes reused, curls by bending cards along curves, a lengthwise
  fold, negative space, shader settings.
- Epic, [Photorealistic character: hair](https://docs.unrealengine.com/4.26/en-US/Resources/Showcases/PhotorealisticCharacter)
  and [Hair Card Generator](https://dev.epicgames.com/documentation/unreal-engine/hair-card-generator-for-grooms-in-unreal-engine):
  the hair shading model's textures (root, depth, ID), two-sided material, cards generated from clustered strands.
- Polycount, [alpha test vs alpha-to-coverage for hair](https://polycount.com/discussion/comment/2500017).
- Budgets: FlippedNormals game-hair listings ([short male](https://flippednormals.com/product/hair-short-male-hairstyle-16197):
  11k low / 25k mid), Ellie Porfyridou, [Real-time hair](https://www.digitalartsandentertainment.com/article/367/+Ellie+Porfyridou++Graduation+Work%3A++Real-time+Hair+) (up to ~100k in current games).
- Superhive, [Fiberbake](https://superhivemarket.com/products/fiberbake-hair-cards): strand effects (curl, clump,
  braid, frizz), atlas packing, a live triangle readout.

# From a strand groom to game hair: what artists do, and where we stand

Research of 2026-10-05 (the user: "do more research on how to turn blender hair into game-ready assets"). Claims
marked (snippet) were read in a search summary only, not on the page; "not found" means no source turned up.

## The method every tool shares

1. **Groom a few strand CLUMPS, not the head**: 4-16 variants from dense and opaque to sparse, fly-away and
   tip-heavy.
2. **Bake them orthographically onto a plane = the atlas.** Passes, the union across tools: opacity, depth / height,
   normal, root-to-tip gradient, per-strand id / random, AO, flow (tangent), colour. Unreal's minimal set is
   diffuse, depth, root, unique id (80.lv XGen breakdown); FiberShop writes 10 at 4K (albedo, alpha, height, normal,
   id, root/tip, flow, AO, translucency, specular; snippet); FiberBake (a Blender add-on, GPL, paid) bakes 12 with
   Cycles and packs the atlas: the proof that a Cycles bake of Hair Curves is the Blender way.
3. **Place cards in layers by opacity**: the base layer is the most opaque and hides the scalp; each layer above is
   more transparent; break-up and fly-aways last. Epic's Hair Card Generator tutorial gives the only published
   numbers (a messy bun, LOD 0, ~54.5k triangles):

   | layer | clumps | triangles | atlas islands |
   |---|---|---|---|
   | coverage | 50 | 2,000 | 25 |
   | mid | 200 | 7,500 | 60 |
   | top | 500 | 25,000 | 60 |
   | fly-aways | 371 single-strand cards | 10,000 | 25 |
   | short hairs | 500 | 10,000 | 75 |

   It makes the cards automatically: strands are clustered into clumps, three cards a clump, then the atlas. LODs
   either cut triangles on the same textures or regenerate cards into reserved atlas space.

Tools and what each teaches (none is a dependency: paid ones are method references only):
- Hair Tool (B. Styperek, paid): cards generated from hair curves or a geometry-nodes hair system; bakes normal, AO,
  diffuse, tangent, id, root, flow, depth; automatic UVs (snippet).
- D. Bystedt's "Hair cards from curves" (free geometry nodes): card meshes deformed along hair curves, twist aligned
  to the head surface. Cards from guides need nothing but nodes.
- GS CurveTools is Maya only (curve-controlled cards with per-point width and twist, layers). HairNet makes guides,
  not cards.
- Blender Conference 2024, "Mesh Hair with Geometry Nodes and Hair Curves" (S. Matsumoto): editable cards and tubes
  from nodes, hair curves used to make their textures.
- Hair cap and hairline: only tutorial-level sources. Houdini's docs describe finer "transitional" cards between
  layers; the usual scalp texture baked from the groom + single-strand cards along the hairline has no primary source.

## Engines

- **Unreal**: a Groom asset from an Alembic file. Schema (Epic's docs): `groom_version_major/minor` (1, 5),
  per curve `groom_guide`, `groom_group_id`, `groom_id`, `groom_root_uv`, optional `groom_closest_guides` /
  `groom_guide_weights`, per vertex `groom_color`, widths from the curves (`groom_width`). Each groom LOD is
  strands, cards or a mesh; card textures are Depth, Coverage, Tangent, Attributes (root uv / coord u / seed),
  Material, Auxiliary. Strands run on Windows, Mac (M2+), Linux, PS5, Xbox Series; cards and meshes everywhere.
  Card shading: the Hair shading model with the tangent in place of the normal, dithered opacity resolved by
  TAA / TSR, the depth map into pixel depth offset (snippet).
- **Unity**: `com.unity.demoteam.hair` (strands from Alembic curves, clustering LODs, GPU simulation); HDRP's Hair
  material is Kajiya-Kay ("approximate", for cards) or Marschner ("physical").
- **Godot**: no strand hair. Cards with alpha scissor / alpha hash + TAA or alpha-to-coverage, anisotropy with a
  flow map or a custom Kajiya-Kay shader.
- **glTF**: `MASK` + alpha-to-coverage, or two passes (an opaque clip pass ~0.7 for depth, then a blended pass for
  soft edges). `KHR_materials_anisotropy` is a brushed-metal lobe, not a hair BSDF: no transmission, no root / id
  inputs. Hair in glTF is cards + a recipe for the engine's own hair shader.
- **Blender writes strands**: Hair Curves go into Alembic and USD since 4.2 (release notes). Whether the stock
  exporter passes named `groom_*` attributes through is unverified (a third-party exporter writes them with
  pyalembic); Unreal wants centimetres (scale 100) and applied transforms.

## Budgets (what could be sourced)

Aloy (Horizon Zero Dawn): ~100k hair triangles on ~50 splines (snippet). A student LOD study: the same style at
65k / 30k / 13k / 6k / 4k / 2.5k, quality holding "down to a point"; complex female hair 19k. Epic's tutorial: ~54k
at LOD 0. Textures: 4K on marketplace assets, 512 px cited once for production (snippets). No published per-LOD
table for NPC or mobile hair was found; cards -> fewer cards -> a helmet mesh matches Unreal's strands / cards /
mesh LOD types but is not sourced as numbers.

## "Volumised" strands (the user's remembered production pipeline)

Nothing documented matches a strand-to-solid-mesh conversion. Sprite Fright's hair meshes were sculpted and
retopologised by hand beside the particle hair and "updated to match grooming" (production log, May 2021). Blender
Studio's procedural hair nodes post only notes that larger radii self-intersect when converted to mesh. No Charge or
Wing It write-up, no per-clump Points to Volume pipeline. The nearest real practice is a profile swept along each
clump's curve (Curve to Mesh): which is what our solid locks are.

**Tried once and closed (2026-10-06, `spikes/hair_strands/hs3/volumise.py`, render ht_12_volumise_try.png):** each
sub clump of Tess's tail (77 clumps), its strand points through Blender's Points to Volume (2 mm) -> Volume to Mesh
(0.8 mm voxels): 3.6 million triangles in 45 s, and the result is rows of beads (strand points are 1 cm apart, so
the spheres do not merge along a strand; resampling to under the radius multiplies the points by ten), with no
strand detail and no material. It would still need a remesh, a retopology and a bake to be an asset: a worse route
to what a swept lens lock already is. Stylised solid hair stays on locks (style "locks"); realistic hair is strands
+ cards. Do not reopen without a documented production pipeline to copy.

## Where our pipeline stands against that practice

| practice | ours today | gap |
|---|---|---|
| groom on strands | Hair Curves from the spec's locks (`style: "strands"`) | in progress |
| clump variants baked to an atlas, 8+ passes | a drawn numpy atlas (colour, alpha, normal, aux) | bake from the groom's own clumps with Cycles: alpha, depth, normal, root-tip, id, flow, AO; unlit colour |
| cards generated from clumps, 3 a clump, layered by opacity | cards cut from each lock, 1-3 layers | cut from the strand groom's clumps; Epic's five layers and triangle shares as the default recipe |
| scalp cap texture + hairline cards | a cap mesh wearing a hairline tile, baby cards | bake the scalp layer onto the scalp's UV; single-strand hairline cards |
| LODs: fewer triangles on one atlas, then a helmet | one budget | LOD chain; the solid locks / cap as the last LOD |
| engine shader: tangent-space hair BSDF, dithered alpha, depth offset | glTF MASK + anisotropy + extras | ship root / id / depth / flow maps + a recipe per engine |
| strands for film and high-end engines | none | Alembic groom (`groom_*`) + USD beside the cards |

## Sources (this section)

- Epic, Alembic for grooms: https://dev.epicgames.com/documentation/unreal-engine/using-alembic-for-grooms-in-unreal-engine
- Epic, Hair Card Generator tutorial: https://dev.epicgames.com/documentation/unreal-engine/creating-hair-cards-and-lods-using-hair-card-generator
- Epic, cards and meshes for grooms: https://dev.epicgames.com/documentation/unreal-engine/setting-up-cards-and-meshes-for-grooms-in-unreal-engine
- Epic, groom platform support: https://dev.epicgames.com/documentation/unreal-engine/groom-platform-support-in-unreal-engine
- Blender 4.2 release notes, I/O: https://developer.blender.org/docs/release_notes/4.2/pipeline_assets_io/
- Groom Exporter for Unreal (third party): https://blenderartists.org/t/groom-exporter-for-unreal-engine/1415778
- 80.lv, hair for real-time projects (XGen): https://80.lv/articles/creating-hair-for-real-time-projects/
- 80.lv, Bystedt's free hair cards from curves: https://80.lv/articles/free-hair-cards-from-curves-setup-for-blender/
- FiberBake: https://superhivemarket.com/products/fiberbake-hair-cards
- Unity demo team hair: https://github.com/Unity-Technologies/com.unity.demoteam.hair
- Blender Studio, procedural hair nodes: https://studio.blender.org/blog/procedural-hair-nodes
- Sprite Fright production log: https://studio.blender.org/films/sprite-fright/production-logs/2021/may
- BCon24, mesh hair with geometry nodes: https://conference.blender.org/2024/presentations/1990/
- DAE graduation work, real-time hair LODs: https://digitalartsandentertainment.com/article/367/+Ellie+Porfyridou++Graduation+Work%3A++Real-time+Hair+
- Godot BaseMaterial3D: https://docs.godotengine.org/en/4.3/classes/class_basematerial3d.html

# Strand grooms through the tools (realistic hair, and its game cards)

For realistic hair the locks stay what you reason in, but they become GUIDES: `groom_hair(name, style="strands")`
turns every lock into a flat clump of strands on Blender's Hair Curves, and a scalp layer of short hairs grows
everywhere inside the hairline (the soft hairline, the cover under the locks). Solid stylised hair is style "locks"
(the rest of this guide); nothing about it changes.

## The stages

1. **Groom the shapes** as for any hair: hairline, parting; LOOSE hair with `groom.loose` (below); tied hair with
   `groom.tie` (`{"at": [176, 30], "out": 0.03, "gather": {rows, locks, lift, width}, "tail": {length, fullness,
   locks}, "escape": 6}` + `parting.side: "none"`). Judge the silhouette first (`stage: "mass"`).
2. **Turn on strands and set the character of the hair** with `strands` (all 0..1 dials unless a unit is given; they
   cannot reach values that stop reading as hair):

   | dial | what it does | when wrong |
   |---|---|---|
   | count | strands in a look (30k default; 60-100k for a Cycles beauty) | too few: see-through in Cycles |
   | clump, clump_size (m), clump_shape | strands gather into sub clumps; where along the strand | 1 / shape 0: ropes |
   | stray | share of strands that only half join their clump | 0: each clump a rope with air between (pasta) |
   | wave (m), wavelength (m), curl, random | the lock's swing; `random` = how far sub clumps fall out of step | random 1 on a tail: pasta |
   | loose, frizz, flyaway | strands wandering together / singly / letting go | frizz high: a cloud |
   | tips, roots, taper | ragged ends, staggered roots, strands thinning to a point | tips 0: a cut brush |
   | under, under_length (m), soft (m), baby | the scalp layer and the hairline's fade | under 0: skin through the hair |

   A thin lock (< 16 mm) is a wisp: it swings less and slower by itself (at a lock's wave a few hairs side by side
   read as crimped ramen). Hair gathered into a tie narrows into it and every strand reaches it.
3. **Look**: `look_hair` renders the strands in EEVEE in seconds under a key, a fill and a rim light (`look.light`
   "salon"; "flat" = one sun). `engine="cycles"` path-traces them with the hair BSDF: the truthful look (1-4 min; it
   waits for the machine's heavy slot). EEVEE draws every strand at least a pixel wide, Cycles at its true width:
   a groom that looks full in EEVEE and thin in Cycles needs more `count`, not more thickness.
4. **Export for a game**: `export_hair(name, out_dir, tiers=["hero", "main", "npc", "far"], save="sheet.png")`.
   Cards are CUT FROM THE STRANDS: the strands of a lock are clustered (hero: the groom's sub clumps; main: pairs;
   npc: whole locks; far: only hair off the head) and each card's centre line is the mean of its clump's strands,
   its width their spread, so cards wave, part and end where the hair does, and a lower tier has fewer, WIDER cards,
   not the same cards thinned out. Under them: the cap (the scalp's own chart, hairline painted in) and, in a tied
   tail, a solid core shaped by the tail's strands. Under a budget, fly-aways and baby hairs go first and coverage
   last. The groom itself goes out as Alembic (cm, Unreal) and USD (groom_* primvars).
5. **Judge the export as an engine draws it.** The sheet shows the strands, then every tier's GLB re-imported on
   the head under a hard alpha TEST and dithered, then the cards as solid quads by layer. The table per tier and
   view: `iou` / `bare` (strand silhouette the tier leaves uncovered), `value` and `sat` x the strands', `stamps`
   (detached rectangular blobs: a card's quad showing), `straight` (outline made of plank edges), plus WARNINGs for
   card vertices under the skin and wisps whose root lies on bare skin. To find what makes a fault, `look_hair(tier=
   "hero", debug=...)`: "layers" (solid quads by layer), "cap_only", "cards_only", "no_normal", "unlit". If a
   pattern survives "unlit" it is in the colour (atlas or vertex colour); if it survives "no_normal" but not
   "unlit" it is the cards' geometry and shading.

## Loose hair: `groom.loose`

Hair that grows all over the scalp, is combed some way at its roots, then falls (or stands). It replaces the
generated tiers; the parting and hairline still apply. It is kept off the head, neck, shoulders and clothes by the
body's own signed distance, so it lies on the shoulders and down the back, and off the face unless it is a fringe.

| key | what | typical |
|---|---|---|
| length | m of hair from the root; or per region `{front, top, sides, back, nape}` (a layered cut, a short back and sides) | 0.3 shoulder, 0.5 mid-back, 0.04 a crop |
| level | every lock is cut where it crosses this height, m from the head centre (about the brows): a one-length cut | -0.105 jaw (a bob), -0.17 shoulders |
| spacing | m between lock roots (lock width follows) | 0.02 long hair, 0.015 short |
| body, lift | m the mass builds up as locks come down over each other; m of root volume | 0.02, 0.006; curls 0.035, 0.012 |
| stiff | 0 hangs at once .. 1 keeps the direction it left the scalp in | 0.2-0.3 long, 0.6 short, 1 an afro |
| out | 0 combed along the scalp .. 1 straight out of it | 0; tousled 0.3; an afro 1 |
| back, messy, uneven | combed back over the crown; root directions turned at random; lengths differ | |
| flow | per region, the way the hair is combed there as a world direction [x his left, y back, z up] | front [0.55, -0.45, 0.7] (up and forward to his left), sides [0, 0.75, -0.65] |
| out, stiff per region | either may be {region: value} | a lifted front: out {front 0.3, top 0.12, sides 0}, stiff {front 0.9, sides 0.55} |
| ends | the ends turn under (+) or flick out (-) | a bob 0.5 |
| face | 1 = hair is turned aside where it would hang over the face (curtains beside the cheeks); 0 = it falls where it falls | 1 |
| fringe | `{length, span (deg either side), depth (m behind the hairline), sweep (-1..1), level, stiff}`: combed forward over the forehead | length 0.07, level -0.004 (the brows) |

The texture is the `strands` dials, not the groom:

| hair | groom.loose | strands |
|---|---|---|
| loose waves, shoulder length | length 0.3, body 0.024, stiff 0.3, uneven 0.5, spacing 0.021 | wave 0.014, wavelength 0.09, curl 0.25, clump 0.55, loose 0.45 |
| bob with a fringe | level -0.105, length 0.3, ends 0.6, uneven 0.15, parting none, fringe | wave 0.002, clump 0.4, flyaway 0.02, tips 0.15, taper 0.3 |
| long straight | length 0.5, stiff 0.2, messy 0.05, spacing 0.02, parting centre | wave 0.003, wavelength 0.16, clump 0.45, loose 0.2 |
| tight curls (ringlets) | length 0.22, body 0.035, lift 0.012, stiff 0.45, out 0.25 | wave 0.03, wavelength 0.028, curl 1, random 1, clump 0.85, clump_size 0.012, clump_shape 0.1 |
| afro (coils) | length 0.085, out 1, stiff 1, body 0, lift 0, spacing 0.02 | wave 0.03, wavelength 0.012, curl 1, random 1, clump 0.3, frizz 0.8, count 40000 |
| short tousled | length {front .05, top .055, sides .03, back .035, nape .018}, stiff 0.6, out 0.3, messy 0.7, spacing 0.015 | clump 0.4, tip_spread 0.7, loose 0.6, tips 0.8 |
| short textured crop (a man's 2-3 cm cut, front lifted) | length {front .026, top .02, sides .022, back .022, nape .012}, spacing 0.009, width 2.4, lift 0.001, body 0.002, messy 0.35, uneven 0.8, flow + out + stiff per region (above), parting none, volume 3-4 mm | count 140000, thickness 1.6, clump 0.15, stray 0.9, roots 0.9, loose 0.18, frizz 0.15, wave 0.0004, curl 0, under_length 0.022; look scalp_tint 0.85 |
| short back and sides | length {front .045, top .04, sides .012, back .012, nape .006}, stiff 0.3, out 0.03, back 0.35 | clump 0.3, under_length 0.014 (the clipped sides ARE the scalp layer) |
| a child's fine hair | length 0.24, body 0.012, lift 0.004, stiff 0.2, fringe | thickness 0.6, count 60000, clump 0.2, clump_size 0.004 |

Curls: `wave` is capped at a third of `wavelength` (a wider swing folds over itself), so tight curls are small AND
short: set the wavelength (0.012 coils .. 0.03 ringlets .. 0.09 waves) and leave wave high. `random` above 0.6 lets
locks fall out of step and differ in wavelength: needed for curls (in step they are a crimped sheet with ridges
running round the head), wrong for a tail (pasta). `curl` 1 = a helix, 0 = a flat wave.

Looks of loose hair take in the bust: views `bust_front`, `bust_three_quarter`, `bust_side`, `bust_back`,
`bust_back_quarter`, `long_back`, `long_side`.

Cards of loose hair: under the cards lies a solid surface INSIDE the mass (`hair_cards.mass_shell`: the strands'
density meshed and decimated, faces toward the body dropped), so no air or skin shows between cards and a far tier
is little more than that surface; card vertices are kept off the whole body, not only the head.

## An existing sculpted groom as strands (a short men's cut)

A head that already has solid locks (hand-shaped or grown) becomes a strand groom without regrooming: the locks are
the guides. Worked on Garrett (624 thin hand locks, a short combed cut going grey), in this order:

1. `groom_hair(name, style="strands", strands={...})`. A short combed cut: `count` 100000, `clump` 0.3, `clump_size`
   0.006, `clump_shape` 0.5, `stray` 0.8, `loose` 0.4, `frizz` 0.2, `flyaway` 0.03, `tips` 0.6, `tip_spread` 0.5,
   `roots` 0.4, `under_length` 0.015, `wave` 0.003. Clump 0.4 with stray 0.6 at 60k strands read as strings.
2. **Grey.** A lock's own `grey` (0..1) is the SHARE of grey strands it grows, x `look.grey_locks` (default 1), plus
   `look.grey_amount` everywhere; `look.grey` is their colour. Locks made for the solid look often carry 0.35+
   everywhere: at grey_locks 1 the head is striped white. 0.6 was salt and pepper. The card tiers draw the same
   share (the locks' mean) in their pictures.
3. **Volume by measure.** Solid locks are modelled as thin shells on the volume; strands fill only each lock's own
   lens. Measure the outline against the reference (per level, mm per side), then `groom_hair(fuller={"sides":
   0.012})`: the locks rise and grow thicker by twice their lift, so the strands fill from the scalp up. (Lifted
   without thickening, a shell stands off the head over a short scalp layer; as solid locks the same lift is a
   stiff helmet.) Raise `count` with it: thicker locks spread the same strands thinner.
4. **The outline's cut.** Strands run to their lock's end and fan a little past it. A tapered nape is
   `groom_hair(trim={"below": -0.015, "where": ["nape"]})` (cut 15 mm INSIDE the hairline: the scalp layer carries
   the edge); with `below` positive it only removes what hangs over the skin.
5. **Colour in Cycles.** The hair BSDF's colour is not what a lit mass of strands renders as: uncalibrated, a dark
   grey-brown came out 3.5-4x too light. The look colour goes through a measured inverse (`hair_strands.CYCLES_FIT`;
   `look.cycles_fit: [1, 1]` turns it off). Mid and light colours land within ~5-40% of `look.lit`; near-black
   can't go under the highlights' own floor. Judge colour on the Cycles look, shape on the EEVEE one.
6. Dark slits between layers of locks are the scalp's tint in shadow (`look.scalp_tint`, default 0.85, made for
   dark hair): on grey or fair hair lower it (0.3-0.5).

## Short cuts as a baked cap + sparse cards (crops, short back and sides)

A crop of 2-4 cm hair is not built like long hair. Cards cut one per clump read as torn paper or leaf litter at
bust distance, and cards only where hair stands off the head leave a bald dome inside a fringe (both tried on
Garrett). What game hair artists do, as far as it could be sourced:

- **The cap carries the look.** A mesh close over the skull wears a texture of the hair itself; breakdowns say a
  flat colour "can pass" but painted or baked fibres on the cap sell it, and for buzz cuts the advice is to bake the
  strand groom down into the head's texture (The Rookies breakdown; Polycount "hair study: shaved bun"; Thomas
  Pecht's buzz cut is described as "hair cards + baked hair cap, single texture"). Commercial short-hair assets
  ship colour, alpha, depth, direction (flow), id, normal, root and specular maps (3D Scan Store's real-time buzz
  cut); bake tools output flow, height, root / tip, normal and AO.
- **Cards over it are layers of falling opacity**: an opaque base that covers the scalp, then 2-3 sparser break-up
  layers, the last ones for the hairline and fly-aways (80.lv "Tips & tricks on hair for games"; Epic's Hair Card
  Generator: clumps of three cards, single-strand fly-away cards, a card group of its own for the hairline's short
  hairs, and for a buzz cut cards of two triangles). Root alpha fades so cards sink into the scalp; some cards
  stand across the others so the hair is not thick from one side and thin from the other (Polycount).
- **Shading**: anisotropic along the hair with a FLOW map on the cap (Reallusion's hair shader: the flow map
  "overcomes the obtuse look of low-poly hair cards"), depth / id / root packed for the shader (inZOI's mod docs),
  Kajiya-Kay or Marschner-style lobes (Scheuermann 2004; Karis 2016).
- **Alpha**: alpha test alone sparkles and thins with distance; mips must keep the alpha's coverage (Castano,
  "Computing alpha mipmaps"; Unity's mipMapsPreserveCoverage), or use alpha to coverage (Golus) or dither + TAA.
- Budgets seen: 5.3k polygons (a marketplace buzz cut), ~9k triangles single-sided (Jansen Turk's breakdown, which
  of his lengths unstated). Shell "fur" (copies of the mesh along the normals with strand dots) is documented for
  short fur, not found in a shipped human buzz cut.

What the tools build when a loose groom's mean lock is under 6 cm (`hair.SHORT_TIERS`; `hair_cap.py`):

1. **The cap's chart is baked from the strands.** Every strand of the groom (its locks' and the scalp layer's) is
   rasterised onto the scalp chart with a z-buffer by height over the scalp, each 0.55 mm wide in METRES (the
   chart's texels are ~0.3 x 0.1 mm and shrink toward the crown). Per texel: the top strand's value and whether it
   is a grey hair (each lock's own share, x `look.card_grey`, default 0.5: the top strand of every texel, fully lit,
   reads twice as silver as the same share among a path tracer's shadowed hairs), depth (how far it stands over the
   hair around it: the shade between hairs and clumps), a normal map from the strands' heights (`hair_cap.RELIEF`
   0.35: at the real slopes, glossy, the cap was tin foil), the strand's direction (the flow map). Under the
   strands an OPAQUE base wherever the groom is dense, from `strands.soft` inside the hairline: skin shows only
   where real strands are sparse. The chart is 2048 px; the atlas (tiles | chart) 4096 x 2048.
2. **The cap stands in the hair**, at half the hair's height over the scalp (`hair_cap.LIFT`, at most 12 mm), easing
   down to the skin over 12 mm at the hairline: the head's outline is hair, not a skull under a fringe.
3. **Cards everywhere the groom has length**, lying just over the cap with their roots sunk in it, on tiles of a few
   THICK strands (16 / 9 strands a tile, 5-6 texels: a 1 cm card is seen 3-4 mips down, where a hundred 1-texel
   hairs are a grey film that an alpha test turns into a flake). The budget thins them evenly: cards that stand off
   the cap (the lifted front, the outline) and the hairline's go last. Tile strands are straightened (16 cm of
   wave squeezed onto 3 cm were white squiggles) and lit (the cap is the shade under them).
4. **One set of maps for every tier**: `export_hair(textures="shared")` (the default) writes hair_basecolor /
   normal / orm / aux / flow PNGs once and each `<name>_hair_<tier>.glb` refers to them by file name (they were
   embedded four times: 4 x 24 MB). `textures="embedded"` for a single self-contained GLB.
5. The material says KHR_materials_anisotropy with the flow map as its texture (direction in tangent space: red =
   along u, green = up the picture; blue = strength), roughness >= 0.72.

In an engine (checked in Godot 4.7, `spikes/godot_hair/look.gd`):

- **Mipmaps.** Images a `GLTFDocument` loads at run time have none; the strand texture then sparkles at every
  distance. Import through the editor, or `Image.generate_mipmaps()` on the material's textures. This was most of
  the "sparkle".
- Godot's glTF importer does not read KHR_materials_anisotropy, specular or sheen: set `anisotropy_enabled`,
  `anisotropy` ~0.35 and `anisotropy_flowmap = hair_flow.png` by hand (at 0.6 with the normal map the hair went
  metallic), and `vertex_color_use_as_albedo = true` (COLOR_0 is the cards' root-to-tip ramp).
- Alpha: glTF MASK imports as alpha scissor at the cut-off (0.33). The cap is opaque inside the hairline, so only
  the hairline's band and the cards depend on it; `alpha_antialiasing_mode = ALPHA_TO_COVERAGE` with MSAA softens
  both. Godot has no import option that keeps alpha coverage in the mips: the tiles' strands are drawn thick so they
  survive it.
- The hero tier (16k) spends its extra triangles on a finer cap and twice the cards; at bust distance it is hard to
  tell from main (8k). Use main unless the camera goes closer than a bust shot.

Sources for this section: The Rookies, a real-time hair breakdown (https://www.therookies.co/projects/65082);
Polycount "Hair study: shaved bun" (https://polycount.com/discussion/237326/hair-study-shaved-bun) and "How should I
texture characters hair" (https://polycount.com/discussion/160776/how-should-i-texture-characters-hair), read as
search snippets; 80.lv "Tips & tricks on hair for games" (https://80.lv/articles/tips-tricks-on-hair-for-games/);
Epic, Hair Card Generator (https://dev.epicgames.com/documentation/unreal-engine/hair-card-generator-for-grooms-in-unreal-engine);
3D Scan Store real-time buzz cut (https://www.3dscanstore.com/hair/realtime-hair-buzzcut); Reallusion's hair shader
textures (https://manual.reallusion.com/Character-Creator-4/Content/ENU/4.0/15_Digital_Human_Shader/Hair/Textures-3-4.htm);
inZOI mod docs, hair texture set-up (https://mod-docs.playinzoi.com/docs/modkit-docs/modkit/project/caz/hair/05-texturesetup);
Castano, "Computing alpha mipmaps" (https://ludicon.com/castano/blog/articles/computing-alpha-mipmaps/); Karis, "Physically
based hair shading in Unreal" (https://blog.selfshadow.com/publications/s2016-shading-course/karis/s2016_pbs_epic_hair.pdf);
Godot forum, run-time glTF textures without mipmaps (https://forum.godotengine.org/t/not-applied-mipmap-at-gltf-runtime-loaded-model/94799);
Godot's gltf_document.cpp (no anisotropy / specular / sheen extension). No numbers for a short cut from a named
studio talk were found; a strand's width in texels and "bent normals for caps" have no source (ours by measure).

## What went wrong on the way (so you can recognise it)

- Hair painted onto the face and shoulders like a stain: the collision proxy mesh was inside out (Shrinkwrap pulls
  what it takes for "inside" to the surface). `tests/test_hair_loose.py::test_collider_mesh_faces_out`.
- A curtain of hair over one eye, tufts standing along the parting: front hair has no direction from gravity (on
  the forehead it points over the face), and the mass was lifted at the roots. Hair is turned aside where it would
  hang in front of the face; the mass builds up as locks descend, not at their roots.
- Long hair fanned out over both arms: a lock lying on a shoulder kept its sideways direction. It slides off to
  the front or the back.

- A dark band above the forehead: lower card layers darkened twice (vertex colour AND the atlas's depth shade) and
  every upper card starting at one distance behind the line. One shade only; roots staggered and faded by alpha.
- Brown stamps along the hairline: baby-hair tiles full of parallel hairs touching the quad's border, lines thinner
  than a texel (an alpha test kept only where they crossed). A baby tile is 4-6 hairs with empty margins.
- A "wire mesh" tail: thin ribbons on separate wave phases with no opaque base. Cards from the strands' own clumps
  wave together; the core closes what is behind them.
- Wisps as dark slashes that seem to start on the cheek: one filled ribbon whose root faded in. A wisp is 2-3 thin
  cards of separate thick hairs on a tile whose root starts at full strength, rooted 8 mm inside the hairline. The
  measurement said they were NOT under the skin; the visible part began lower because the root was faded.
- Brick lines across the flow under an alpha test: staggered card roots on a tile that starts as a cut edge.
- Cards as white plates under a rim light: a card is one flat sheet standing for many round hairs; half the
  specular, tinted to the hair.

## Limits today

Cards are still smoother than strands at bust distance (less strand-to-strand contrast), a few dark slits show
between cards on a combed-back top, npc cards lift at the crown like roof tiles, and the far tier is a helmet and a
solid tail without wisps. The atlas is a numpy raster of Blender-evaluated strands (alpha, per-strand id, depth,
root gradient, a normal from depth), not a Cycles bake; a short cut's cap has flow, depth and a normal from the
strands' heights, long hair's cards only a constant flow. Clearance is checked
against the head as the scalp's rays see it, not against a game's decimated skin. Loose long hair has no core
surface (only tied tails do): its coverage is the dense first layer.
