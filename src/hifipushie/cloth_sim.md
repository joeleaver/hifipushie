# Clothes: simulation, reports, clean-up, detail and export (stages 5-6) in detail

Read guide(topic="cloth") first. Simulate only a garment whose description, sheet, pattern, construction and start
pass.

## Methods (sheet key `method`)

## Quality

- `quality="draft"`: one 2 cm simulation, about a minute on Blender. Puffy on purpose: judge fit and big shape.
- `quality="final"` (default): the whole assembly at 2 cm (bodice sewn first, then sleeves and collar, then
  gravity), carried onto a 1 cm mesh and settled again with self-collision. About 3-5 minutes on Blender.
- `resolution` (final triangle size) and `coarse` (blocking size) change the two meshes. Below 1 cm Blender's cloth
  gets softer and slower (collars and cuffs crumpled at 7 mm).

## Solvers and where they run

## Read the report

| Target | Value | Judged at |
|---|---|---|
| Collar fall below the neckline seam at CB | 6-14 mm | draft |
| Hem height spread | under 15 mm | draft |
| Waistband seam against the body's waist | within 25 mm | draft |
| Sleeves on a hanger, from vertical | under 8 deg | draft |
| Strain p95 | under 9% | draft |
| Layer gaps (fronts, collar over stand) | under 2 mm light wovens, 4 mm coating | final |
| Collar points off the shirt | under 3 mm | final |
| Tightest folds (crest radius p10) | under 4 mm shirting, 10 mm coating; needs 5 mm triangles | final |
| Crease width, fold spacing | 2.5-5 mm and 8-18 mm shirting; 10-20 and 30-60 coating | not measured by the tools yet |

These targets say the cloth behaves; the description's items say it's the right garment. Both must pass.

## Judging what you see

## Clean-up (automatic, numbers in `cleanup`)

## Made pieces constructed after the drape (garment key `construct`)

A tailored jacket's lapels and notched collar are BUILT on the finished drape (`construct: {"collar": true}`;
lapels "made" by default):
- **At their cut length and width.** A made piece laid on eased cloth takes the ease (a collar end came out a narrow
  strap). The fall is boarded at its pattern length (`collar_options.board_length`), each end column at its cut
  length (`end_length`); check 3D / pattern length per station (want ~1).
- **One smooth turn from the end to the back** (`collar_options.transition` "board", default): blended lays knot.
- **A canvassed lapel rolls:** `lapel_options.roll_top` (7 mm default) graded from the break to the gorge, flat by
  its outer edge. Over ~10 mm lifts the gorge into the collar end.
- **The notch needs a rim:** the collar end lies on the lapel by its own thickness (`collar_options.end_over` 1.0);
  flush, the V doesn't read. Its shape is the draft's (`lapel.notch`, `collar.point`).
- Under garments under made pieces are laid under them (`cloth_layers.tucked`), never into the body; what no view
  direction sees is cut (`cloth_layers.cut`).

## Detail: seams, stitching, hems, buttons (`detail`)

Drawn from the pattern into maps on the flat-pattern atlas:
- every seam by its FINISH (`seam_finish` for the garment, `seam_finishes` {seam index | "pieceA/pieceB" | piece:
  finish}; default the kind's): `pressed_open` (tailored jackets, coats, trousers, skirts: a faint groove, no
  stitching), `pressed_to_side` (knits, blouses), `topstitched` (one row 6 mm out), `edgestitched`, `felled` (shirts,
  jeans: two rows), `welt` (a seam made to stand: piping). `seam`, `seam_width`, `allowance` override the numbers;
- a dashed `topstitch` m in from free edges (none on blind-stitched hems; 6 mm otherwise); a turned-up `hem` m deep;
- buttons on marks `button*`, stitched slots on `buttonhole*`; the `thread` colour (default a shade lighter);
- fine folds from the drape (`folds`, `fold_gain`, `fold_opts` {`wavelength` [min, max], `length`, `sharp`}).

## Closures and bands

## States

- `"worn"`: sewn on the body and settled.
- `"hung"` / `{"hang": {"hanger": {...}, "rail": {...} | false}}`: dressed on the body first, a hanger put INSIDE it
  (arms under the shoulders, hook up through the neck opening), the body taken away; gravity settles it onto the
  hanger, nothing pinned. hanger: `kind` "wood" (default) or "wire"; `width` (default the shoulder points less 2 cm);
  `bar`; `slope` deg; `clear` (8 mm); `rise`. rail: `length`, `radius`, `posts`, or false. The report's `hanger:`
  line says what carries it and leads with NOT ON ITS HANGER when pins carry it, one shoulder carries almost nothing,
  it is still moving or the hanger isn't inside. The old pinned hang (`pins`, `hook`, `rack`) still works.
- `"draped"` / `{"drape": {"over": "model" | "body"}}`: pieces wrapped `{"to": "flat", "at": [x, y, z]}` fall onto
  the model's surface (a tablecloth on a table, a blanket on a bed).

## Hand pass in Blender (when numbers won't get it)

`sync(name, cloth_only=True)`, open `scene.blend`, sculpt the garment (smooth a buckle, push a fold, a memory fold
at the elbow; recolour its `hp_color` node), then `pull(name)`: the shape is kept as offsets on that simulation. A
new simulation drops them, and the report says so.

## Export

`export_asset` writes each garment two-sided (the inside of an open coat shows), the flat pattern as its UV (one
island per piece, grain straight), base colour with the stitches, and a normal map with seams, hems and buttons.
