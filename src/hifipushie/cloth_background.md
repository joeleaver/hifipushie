# Clothes: background (practice, sources, worked examples)

Why the cloth tools are built the way they are: how garment makers and artists work, the sources, two worked garment
kinds. Not needed to make clothes; read it when changing the tools.

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


## A new garment kind, start to finish (the skirt)

`skirt_block` options (in the sheet's `pattern`): `length` (m below the waist), `ease` {waist, seat}, `flare` (m per
side seam at the hem), `darts`, `waistband` (height), `overlap`, `closure` (cb_zip, side_zip).

A draft source we don't have: write own `pieces` (outlines in metres with named points, `"role"`, `"wrap"`) and
`seams` on the garment, plus `generate` for bands sized from the edges they are sewn to:
`{"band": "neckband", "role": "neckband", "along": ["front:neckL>neckR", ...], "ratio": 0.85, "height": 0.02,
"ring": true, "fold": true, "wrap": {"to": "neck"}}`. The design sheet and every check still apply.

## A kind that drafts itself (suit trousers)

A kind in `garment_kb.json` can carry `draft` (block, block_options, `fit_options` per fit), and a detail choice can
carry `draft.ops` (the operation that makes it) and `trims`. Then the sheet is only the decisions:

makes flat-front tailored trousers: the trouser block with the leg cut from the leg's own girths, an `extended`
waistband opening at the centre front, a `zip_fly`, `pressed` creases, shaped back darts, belt loops and a belt.
Change a decision in `details` (`"crease": "none"`, `"belt": "none"`, `"fly": {"choice": "zip_fly", "op": {"length":
0.16}}`), the cut in `fit` (tailored = slim leg, slim = skinny, classic = straight) or any number in `block_options`
(they lie over the kind's). An op of the same name in the sheet's own `ops` replaces the detail's.
