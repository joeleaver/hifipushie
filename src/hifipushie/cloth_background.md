# Clothes: background (practice, sources, worked examples, where each lesson lives)

Why the cloth tools are built the way they are: how garment makers and artists work, the sources, two worked garment
kinds and the index of lessons. Not needed to make clothes; read it when changing the tools.

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
- Tailoring practice behind the knowledge base (see cloth_audit.md for the measured comparison):
  - shirt collars (stand, fall, roll, points): https://www.threadsmagazine.com/project-guides/fit-and-sew-tops/creating-professional-looking-shirt-collars
  - skirt and trouser blocks, ease and darts: Winifred Aldrich, Metric Pattern Cutting (the skirt block here follows it)
  - FreeSewing design docs (Simon, Carlton/Carlita instructions: belt, back pleat, roll line): https://freesewing.eu/docs/designs/
  - fabric measurement for virtual garments (bending, buckling): https://support.clo3d.com/hc/en-us/articles/115002797808-Adjust-Buckling-Ratio


## A new garment kind, start to finish (the skirt)

```
design_garment(name, "skirt", design={"kind": "skirt", "from": "skirt_block", "fit": "a_line",
               "fabric": "cotton_twill"}, spec={"quality": "draft"})
look_pattern(name, "skirt")                      # front, two backs, waistband; darts; ease per girth
check_garment(name, "skirt", stages=["construction", "place"])
dress(name, "skirt")                             # the draft
look_cloth(name, ["skirt"])                      # verdict + targets: hem level, waistband at the waist
design_garment(name, "skirt", design={"fit": "straight"})          # change the cut in the sheet, look again
```

`skirt_block` options (in the sheet's `pattern`): `length` (m below the waist), `ease` {waist, seat}, `flare` (m per
side seam at the hem), `darts`, `waistband` (height), `overlap`, `closure` (cb_zip, side_zip).

A draft source we don't have: write own `pieces` (outlines in metres with named points, `"role"`, `"wrap"`) and
`seams` on the garment, plus `generate` for bands sized from the edges they are sewn to:
`{"band": "neckband", "role": "neckband", "along": ["front:neckL>neckR", ...], "ratio": 0.85, "height": 0.02,
"ring": true, "fold": true, "wrap": {"to": "neck"}}`. The design sheet and every check still apply.

## A kind that drafts itself (suit trousers)

A kind in `garment_kb.json` can carry `draft` (block, block_options, `fit_options` per fit), and a detail choice can
carry `draft.ops` (the operation that makes it) and `trims`. Then the sheet is only the decisions:

```
design_garment(name, "trousers", design={"kind": "suit_trousers", "fit": "tailored"},
               spec={"quality": "draft", "backend": "zozo", "color": "#2e2f33"})
look_pattern(name, "trousers")       # leg cut from HIS leg, seat ease in the fit's band, fly, creases, band, trims
```

makes flat-front tailored trousers: the trouser block with the leg cut from the leg's own girths, an `extended`
waistband opening at the centre front, a `zip_fly`, `pressed` creases, shaped back darts, belt loops and a belt.
Change a decision in `details` (`"crease": "none"`, `"belt": "none"`, `"fly": {"choice": "zip_fly", "op": {"length":
0.16}}`), the cut in `fit` (tailored = slim leg, slim = skinny, classic = straight) or any number in `block_options`
(they lie over the kind's). An op of the same name in the sheet's own `ops` replaces the detail's.

What a pattern cutter decides first, and where it is here:
- **The leg** (`block_options.leg`: skinny, slim, tapered, straight, wide; or `knee` / `hem` in metres as half the
  finished circumference). Knee = the knee girth + the cut's ease, never tighter than the calf + its ease; hem = a
  share of the knee, never under heel-and-instep + 20 mm (the hem must pass the foot). `tailor.measure` reads
  `upperLeg`, `knee`, `calf`, `ankle`, `heel` off the body. Stage 2 says the ease per leg and whether the hem can be
  pulled on.
- **Length** (`length`: break, floor, shoe, ankle, cropped, calf, knee, shorts). "break" (the suit trousers'
  default) is cut 30 mm over the floor with the back 12 mm longer than the front; the start hangs each column to the
  floor, stops it on whatever faces up under it (the shoe) and gathers the extra into the bottom 9 cm: one soft break,
  no ankle showing (Garrett: hem 94 mm up at the front, on the vamp, 58 at the back). Give the shoes as colliders
  (`collide: ["shoes", "soles"]`) or the hem passes through them. Cutting the length from the shoe's own heights came
  out 5 cm short: cut from the floor. "shoe" ends the hem 3 cm over the floor with no back difference.
- **The legs start on the legs** (a tube round each leg's own axis, blended into the seat at the crotch): on one
  cylinder per leg a slim leg's front and back started as slabs 17-21 cm apart at the seams.
- **Tucked in or worn free** is decided on the trousers: `over: "shirt"` tucks the shirt (it is pressed under them);
  without it the shirt hangs over the waistband and hides the belt.
- **The crease** is the grain line: through the middle of knee and hem on both pieces. Without it a suit trouser
  reads as a pyjama leg whatever its cut.
- **Seat ease** is read from the centre seam's line to the side seam; the forks lie between the legs.
- **Back darts** (`back_dart` intake, `dart_length`, `dart_taper` 0..1): a shaped dart's legs run in toward the
  fold over its last third, so the tip dies away; straight legs end in a poke that reads as an open tuck.
- **Trims** (garment key `trims`, `cloth_trims.py`): a belt (with a buckle) and belt loops are built ON the
  finished waistband after the sim, as artists model them on the simulated trousers; they are in `look_cloth`,
  not in the sim, the scene or the export yet.

## Where each lesson lives

| Lesson (cloth_audit.md, 2026-10-03) | Where it is enforced |
|---|---|
| Sleeve cap ease 44% on the coat | Stage 2 seam check, cap band by kind |
| Stand stretched over a long neckline; collar shorter than its stand | Stage 2 band seams; simon's collar is drafted with no gap |
| Missing belt (side seams -20%) | Stage 2 plain seams; `belt` detail |
| Lapped pleat sewn shut | `back_vent: lapped_vent` evidence: a fold on the tail |
| No sleeve placket | `cuff: barrel` needs `sleeve_placket`; cuff seam band |
| No lapel roll, no facing, fronts frozen | `collar: notched_lapel` evidence; stage 3 made or draped |
| Collar never pressed; the 10 mm U | Fold lines with angle; stage 3 warns on a placed-only fold |
| The fall didn't cover the stand | `fall_cover` in stage 2; collar cover target in stage 5 |
| Every fabric the same bend | Fabrics with physical numbers; interfacing multiplier check |
| Layers held 5-17 mm apart | Layer gaps at the start (stage 4) and settled (stage 5) |
| Cloth reads thick (no crest under 7 mm at 1 cm) | Crest radius target; finals at 5 mm or less |
| 20 mm hems everywhere, 11 mm buttons on a coat | Hem depth per hem choice; the plan warns about coat buttons |
| Sleeves splayed on the hanger | Sleeve angle target |
| Pieces crossed or overstretched at the start | Stage 4 |

The suit rounds (2026-10-06..08: a shirt, a blazer from our blocks over it, suit trousers, on a test body and on
Garrett):

| Lesson | Where it is enforced |
|---|---|
| A garment worn over another is drafted over it | Automatic with `over` (draft log "drafted over"); layer tells in stage 5 (collar / cuff show, lapel gap, collar hug, crossings) |
| Jackets and coats are built on the form | Kind default `worn_top`; no check of its own (stage 4 start gaps show a failure) |
| Bands closed on themselves start closed | Stage 4 fails "<band> starts with its fastening N mm open" |
| Seams close: p95 gap <= 0.5 mm after the clean-up, closures <= 6 mm | Stage 5 targets `seam_gap_p95_mm`, `closure_gap_max_mm`; OPEN SEAM lines in the report |
| A strain-limited start: shear counts, 3% target, fine start under 1.6x | Stage 4 start strain (`start_strain_over_limit`); the fine settle's start check refuses before the GPU |
| Openings at the centre are joined or declared | Stage 3 openings: a seam, stitches, a closure, a closure worn open, or `design.open` |
| A chosen closure has a closure entry | Stage 3 fails a `front_closure` / `cuff` / `fly` with none |
| A trouser hem can be pulled on | Stage 2 hem per leg piece against heel + instep |
| Seat ease from the centre seam to the side seam | Stage 2 `leg_ease` |
| A jacket's hip room from `hips_ease`, not flare; the tent is the side panel's spring | NONE: read hem level and the open fronts on the sim (target `hem_level_mm` covers the hem only) |
| Don't lower a jacket stand to show the shirt collar | NONE: `layer_collar_show_mm` measures the result; the lapels' roll angles are in the report's fold lines |
| A shirt without a tie: only the collar open, collar spread | Kind default (`kinds.shirt.wear`, `collar_spread`); no check |
| Collar size from the neck | Applied by `collar_rule` on Simon; stage 4 HINT when a neck band is pushed > 8 mm off the neck |
| A placket / faced edge shows by its finish | Closure defaults by kind (`kinds.<k>.closure`: shirt box / french, jacket and coat facing, holes across); no check |
| Pit seams start too far apart on a fitted jacket | NONE yet: stage 4 lists seam start gaps; read them |
| The padded body folds in hollows | Fixed in the code; no check |
| Judge in clay / GLB, not the textured look; renders before a change show old code | NONE: discipline |

Still open (the checks say so where they can):
- Carlton's facing and lapel roll; pleats as folds (they are seam gaps: a fold that dies out inside a piece is a
  cone, and a pleat's layers are finer than a 1-2 cm mesh); double-layer (bagged) cuffs and collars;
- welt / flap / in-seam pockets; a lining's own pleat and fabric;
- button size and buttonhole direction are per closure now (`size`, `hole`) but not defaulted per kind (a jacket's
  closure needs `finish` / `hole` set by hand);
- a fitted jacket's pit seams (start); the jacket collar hugging the shirt collar (`collar_hug` 23-27 mm, target 6);
  front, back and collar disagreeing on the neck point (shoulder seam open ~10 mm there); the shirt's side seams
  standing as a fin the press can't flatten; hem height spread reads designed curves (a shirttail, a yoke) as
  unevenness;
- crease width and fold spacing measured by the tools; grain anisotropy.

