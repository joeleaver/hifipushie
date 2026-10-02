# Clothes: sewn, simulated, cleaned up

Garments here are made the way a garment artist makes them in Marvelous Designer or CLO:
- flat pattern pieces, drafted to the body's own measurements;
- sewn round the body and settled by a cloth simulation;
- then cleaned up and detailed (seams, topstitching, hems, buttons).

Nothing is sculpted as a solid shell, and nothing is warped from one body onto another. The same machinery makes
other things from flat pieces. A tablecloth is one piece laid flat and draped on a table. A blanket is one piece
draped on a bed or a body.

Tools:
- `dress(name, garment, spec={...}, state, quality, wait)`:
  - Stores `spec["cloth"][garment]`, merged key by key (`replace=True` replaces it).
  - Starts the simulation in the background (one heavy job at a time on the machine).
  - Waits up to `wait` seconds, then returns either the progress or the finished report.
  - `dress(name)` with no spec reports where every garment's simulation stands. A simulation that is cached or
    already running is never started again.
- `look_cloth(name, views, strain, focus, zoom, textured)`: renders the garments on the body, with a strain-map row
  and the report.
  - `focus="shirt:collar"` (or `[x, y, z]`) with `zoom` in metres gives a close-up.
  - `textured=True` shows the sewing detail maps (seams, stitches, hems, buttons) in EEVEE.
- `edit_model` with kind `"cloth"` (`{"op": "set", "kind": "cloth", "name": "shirt", "value": {...}}`): changes
  numbers directly. A cloth-only edit validates only the cloth.
- `sync(name, cloth_only=True)`:
  - Puts the simulated garments into `scene.blend`, in the collection "cloth". Each gets its pattern UV, its detail
    maps, and an `hp_color` node a person can change.
  - Only simulated garments go in: a sync never starts a simulation.
- `pull(name)`: brings a person's Blender edits back.
  - Colour and roughness.
  - Shape: a sculpt or clean-up pass done in Blender comes back as per-vertex offsets on top of that simulation
    (`cloth.<g>.sculpt`). Offsets from an older simulation are reported and not applied.
- `export_asset`: writes each garment as a two-sided part. Its UV is the flat pattern, and its maps carry the
  sewing detail.

## How artists do it

The sources (Marvelous Designer's own manual and 2024 field guide, 80.lv breakdowns, Polycount, vkgamedev's fold
guide, the Hogarth fold notes, Pixar's papers; links at the end) agree on this order.

1. **Body and pose.**
   - Build on an A-posed avatar. It keeps a skin offset of about 3 mm while blocking.
   - Pose it afterwards, with the garment recorded along.
2. **Patterns.**
   - Flat pieces with a grain direction.
   - Arranged round the body on the arrangement points of bounding cylinders (torso, arms, neck), so every piece starts
     curved round the part it covers, symmetric pairs symmetric.
3. **Sewing.**
   - Segment to segment.
   - M:N sewing where a long edge gathers into a short one (cuff pleats, gathers).
   - Sew the garment closed before fastening buttons.
4. **Fabric per piece.** Stretch, shear, bending, buckling and density.
   - A common failure is one preset on every piece: everything drapes alike and reads generic.
   - Stiff fabrics (denim, wool) make few broad folds; light ones (silk, jersey) make narrow folds with rest areas
     between.
5. **Fold lines and layers.**
   - Collars, plackets, hems and creases are lines with a fold angle and strength, pre-folded before the simulation,
     not sculpted after.
   - Overlapping pieces get layer numbers, outer above inner. Without them, fronts and pockets pass through each
     other.
6. **Simulate coarse first.**
   - Particle distance (triangle size) about 20 mm and collision thickness about 2.5-3 mm while blocking and fitting.
   - A coarse mesh is fast and stable, and can only make the big folds: exactly what you judge first.
   - Build inside-out: freeze a finished inner layer before simulating the next.
7. **Fix locally.**
   - Pins and tacks where something dangles or slips.
   - Pressure only on a two-layer (padded) piece.
   - Shrink or steam for local fit.
   - Strengthen (temporary starch) while folding.
8. **Refine.**
   - Drop the particle distance to 5-10 mm on visible pieces for the final simulation (inner layers can stay coarse).
   - Lower the collision thickness and skin offset at the same time. Thick buffers left on a fine mesh look puffy.
   - Never refine before the fit is right.
9. **Clean-up sculpt.**
   - The simulation is a blockout. Remesh it, smooth away the simulation noise (crinkle, frozen buckles), and keep the
     big folds.
   - Every fold needs a cause:
     - an anchor;
     - tension (inverted triangles radiating from the pull point);
     - compression (stacked links at a bend);
     - gravity (pipes and drops).
   - Leave stretched areas and rest areas quiet. Break the symmetry. Never repeat a stamp.
10. **Detail last.**
    - Memory folds at the joints, seam folds, topstitch lines, hems (the turned-up edge), buttons, and real thickness
      (solidify).
    - Detail is often stamped as normal-map alphas or IMM stitch brushes.
11. **Game-ready.**
    - Retopology keeps the silhouette folds in the geometry and adds loops at joints.
    - UVs come from the pattern pieces: one island per piece, the grain straight.
    - Bake normal and AO from the high poly, at about 10 px/cm on a hero (faces 2-3x that).
    - The fabric material needs a sheen lobe, a tiling weave normal and roughness contrast.
12. **Test.** Check in bent poses and at game distance.

Fold vocabulary (Hogarth's seven, plus tension and compression):

| Fold | What it is | Where |
|---|---|---|
| Pipe | Tubes hanging from one support | Curtains, a skirt, a coat's back from the shoulders |
| Diaper | U-sags between two supports | Across a raised-arm chest, a cowl |
| Drop | Falls and twists from a raised support | A cape, a coat hung from one point |
| Half-lock | A tube bending at a joint, with an "eye" where it turns | Elbow, knee, waist |
| Zigzag | Alternating triangles from compression along a tube | Trouser legs, pushed-up sleeves |
| Spiral | Zigzag with twist | A tight sleeve |
| Inert | Cloth lying on a surface | A tablecloth's overhang on the floor, a blanket |

Stylised vs realistic: stylised clothing follows the same physics with fewer, bigger, cleaner folds and crisper
creases, from stiffer and thicker cloth (Pixar dresses real tailoring in stylised proportions). It is not just less
detail. Raise the fabric's bending, coarsen the final mesh, smooth more, and keep the detail maps.

## The workflow with the tools

### 0. Body

A garment is drafted to the body it's on (`tailor.measure`: FreeSewing's measurements taken off the surface), so the
model needs a `base` body (MakeHuman parameters). A prop for a drape (a table) needs no body: its whole surface is the
collider.

### 1. Pattern and size (draft quality)

```
dress(name, "shirt", spec={"pattern": {"from": "simon", "ease": {"chest": 0.12}, "length": 0.15},
                           "fabric": "shirting", "color": "#8fb3d9"}, quality="draft")
```

- **Designs.** `cloth_designs.json` holds the designs: `simon` (a shirt: yoke, fronts with plackets, collar on a
  stand, cuffs with pleats, buttons) and `carlton` (an overcoat).
- **Your own pieces.** `pieces` (a polygon in metres with named points) + `seams`.
- **Ease** is a fraction of the body's measurement.
- **Tailoring words** map to FreeSewing options: `length`, `sleeve_length`, `round_back`, `yoke_depth`,
  `back_darts`, `buttons`, `hem`, `cuff`, `sleeve`.
- **`measurements`** gives a fixed size (mm) instead of made-to-measure. Use it to put a stock size on a body it
  doesn't fit.

Draft is one 2 cm simulation, about 1 minute. It looks puffy and blobby on purpose: judge only the fit and the big
shape here.
- The report's **sizing row** comes from the flat pattern. Negative ease anywhere means the garment is TOO SMALL.
- The **on-the-body row** is the settled girths and the strain across front and back.
- **Fix fit in the pattern** (ease, length, measurements), never by sculpting.

### 2. Final quality

- `quality="final"` (the default):
  - The whole assembly runs at 2 cm: bodice sewn first, then the sleeves and collar, then gravity.
  - The result is carried onto a 1 cm mesh of the same pattern and settled again with self-collision.
  - This is the coarse-then-fine particle distance artists use. It takes about 3-5 minutes.
- `resolution` (final triangle size) and `coarse` (the blocking size) change the two meshes.
- Below 1 cm, Blender's per-edge bending makes the cloth softer and the solver slower. The collar and cuffs crumpled
  at 7 mm.

### 3. Read the report

- **Verdict.**
  - `CORRUPT`: a piece is tangled (> 20 crossings) or crumpled (> 3% of its triangles squashed or folded flat), or a
    seam is twisted. Nothing else counts until it's fixed. The report says which pieces and where.
  - `TOO SMALL`: negative ease from the pattern.
  - `STRAINED at <girth>`: cloth stretched past the fabric's limit plus 6% simulation noise across the front and back
    at that girth.
  - `fits`.
- **Integrity** compares the simulation and the cleaned surface: crossings before and after the clean-up.
- **Surface.**
  - Crinkle is the median angle between neighbouring triangles. A 1 cm simulation reads 8-10°, after clean-up 5-6°.
    Under ~5 reads smooth.
  - Folds is the depth of the folds, rms against the surface smoothed over ~15 cm. A shirt with 15% ease on an
    A-posed body measured only 2-4 mm: it hangs close. Folds come from pose, ease and gravity. They are not
    sculpted in.
- **Strain map.** Blue is slack, green fine, yellow at the fabric's limit, red twice it. Red rings sit at seams and
  buttons (the sewing springs: left out of the numbers). Red across a whole region means it's too tight.

### 4. Clean-up (automatic, numbers in `cleanup`)

It does what the sculpt pass does first:
- Taubin smoothing removes the crinkle. 4 passes at 1 cm, scaled by the mesh size; `smooth`.
- No vertex moves more than `keep` (4 mm). Crinkle is a few mm deep, so a bigger move would be flattening a real fold.
- Interfaced pieces (collar, stand, cuffs, plackets) aren't smoothed: they don't crinkle, and smoothing their tight
  folds crumpled them.
- Seams the simulation closed are welded.
- Anything pulled toward the body is pushed back out to `clear`.

`cleanup: false` shows the raw simulation.

### 5. Detail: seams, stitching, hems, buttons

These are drawn from the pattern itself into maps on the flat-pattern atlas (`detail`):
- a groove along every sewn edge, with the seam allowance's ridge beside it (`seam`, `seam_width`, `allowance`);
- a dashed topstitch `topstitch` m in from every edge (`stitch` length, `stitch_gap`);
- a turned-up hem `hem` m deep along free edges;
- buttons (discs with four holes) on marks named `button*`, and stitched slots on `buttonhole*`;
- the thread colour (`thread`, default a shade lighter than the cloth).

Judge them in close-ups:
```
look_cloth(name, focus="shirt:collar", zoom=0.35, textured=True, views=["front", "three"], strain=False)
```
The same maps go into `scene.blend` and the export.

### 6. States

- `"worn"`: sewn on the body and settled.
- `{"hang": {"pins": ["stand:bottomLeft"], "hook": [x, y, z], "rack": [[a, b, r], ...]}}`:
  - Dressed on the body first: a coat sewn in the air with nothing inside caved in.
  - Then the body is taken away and the coat hangs from a pin patch at the hook. Rack poles and arms are cylinder
    colliders.
  - Pins name outline points or marks (`piece:point`).
- `"draped"` / `{"drape": {"over": "model" | "body"}}`:
  - Pieces wrapped `{"to": "flat", "at": [x, y, z]}` fall onto the model's surface: a tablecloth on a table, a blanket
    on a bed.

### 7. Hand pass in Blender (when numbers won't get it)

- `sync(name, cloth_only=True)`, then open `scene.blend`.
- Sculpt the garment there: smooth a buckle, push a fold, design a memory fold at the elbow. Recolour its `hp_color`
  node if needed.
- `pull(name)` keeps the shape as offsets on that simulation. A new simulation drops them (they belong to its
  surface), and the report says so.

### 8. Export

`export_asset` writes:
- each garment two-sided (the inside of an open coat shows);
- the flat pattern as its UV, one island per piece with the grain straight;
- base colour with the stitches, and a normal map with the seams, hems and buttons.

## What goes wrong, and the fix

| What you see | Why | Fix |
|---|---|---|
| CORRUPT fronts / plackets | Overlapping pieces passed through each other while sewing | Self-collision is on in every stage (`self_collision_sew`). The outer front starts one layer (`wrap.out` 4 mm) outside the inner. |
| CORRUPT sleeves at the elbow | Round a bent arm, the sleeve's straight pattern overlapped itself inside the crook at the start | The excess is placed as a fin standing out in the mitre plane, which the simulation folds into the half-lock fold (`wrap.no_fin` turns it off) |
| A cuff or collar crumpled into a ball | Interfaced bands are stiff; a mismatch between rest shape and start makes them buckle | The fine mesh's rest is the coarse placement carried over; interfaced pieces aren't smoothed. If it persists: `resolution` 0.01, not finer. |
| Puffy, inflated look | Draft quality (2 cm triangles) or thick collision buffers | Final quality; the fine stage settles 1 cm triangles |
| Fine crinkle all over | Frozen buckles a triangle or two across (mass-spring cloth, low bending) | Clean-up passes (`cleanup.smooth`); a stiffer fabric (`bending`); a Blender sculpt + pull |
| Shrink-wrapped (folds < 2 mm, the body's forms show through) | Too little ease, or a too-light, stretchy fabric | More ease in the pattern; a heavier or stiffer fabric |
| Uniform, evenly spaced folds | One fabric everywhere, a symmetric pose | Different fabrics per garment; interfacing on bands; break symmetry by hand in Blender |
| STRAINED at chest/seat on a heavy body | The draft's ease is relative, but the body's shape (a belly) isn't in the block | `alterations` (`large_abdomen` is automatic); more ease where it's strained |
| Shirt rides up / sleeves dragged up the arm | Sewing everything at once lifts the bodice | Assembly order: the bodice is sewn first, cuffs held (`assemble`) |

## Sources

- Marvelous Designer manual: arrangement points, particle distance, layers, fold lines, simulation properties, fabric
  physical properties.
  - https://support.marvelousdesigner.com/hc/en-us/articles/47358324263705-Add-Arrangement-Point
  - https://support.marvelousdesigner.com/hc/en-us/articles/47358145573401
  - https://support.marvelousdesigner.com/hc/en-us/articles/47358288780441
  - https://support.marvelousdesigner.com/hc/en-us/articles/47358354961049-Fold-Pattern
  - https://support.marvelousdesigner.com/hc/en-us/articles/47358125463321-Simulation-Properties
  - https://support.marvelousdesigner.com/hc/en-us/articles/47358432358809
- Marvelous Designer Creator's Field Guide 2024 (blocking at 20 mm, final 5 mm or less, collision thickness and skin
  offset, freeze/deactivate, layer order):
  https://s3.marvelousdesigner.com/newmdweb/case/20240626/MD+User+Guide+2024.pdf
- Stylised garments with Marvelous Designer (Pixel; stiff bending, pressure on layer clones):
  https://blog.siggraph.org/2022/07/creating-stylized-garments-for-pixel-with-marvelous-designer.html/
- 80.lv breakdowns:
  - remesh + ProjectAll, the sculpt pass, IMM stitches:
    https://80.lv/articles/breakdown-detailed-3d-model-of-fantasy-archer
  - layers, freezing, retopology: https://80.lv/articles/the-punisher-clothes-production-retopology-texturing
  - stylised cloth: https://80.lv/articles/001agt-eureka-sculpting-stylized-cloth-pbr-texturing
  - thickness, export: https://80.lv/articles/making-a-dress-and-a-leather-jacket-in-marvelous-designer
  - retopology budgets: https://80.lv/articles/scavenger-clothes-production-and-retopology-in-maya
- Folds: force maps, tension/compression, quiet areas, order of the sculpt:
  https://vkgamedev.com/blog/sculpt-clothing-folds-blender-zbrush;
  Hogarth's seven folds: https://www.thivolan-art.com/post/how-to-construct-the-7-folds
- The simulation as a blockout, never shipped raw: https://polycount.com/discussion/150497/marvelous-designer
- UVs from the flat pattern: https://www.gamedev.zone/character-pipeline-2-clothing-retopo-from-marvelous-with-maya/
- Cloth shading (sheen/fuzz): https://dev.epicgames.com/documentation/en-us/unreal-engine/shading-models-in-unreal-engine
- Pixar's garment pipeline (a coarse authored mesh, a triangle simulation mesh, a render mesh with procedural thickness
  and seams): https://dl.acm.org/doi/fullHtml/10.1145/3532836.3536252
