# Clothes: simulation, reports, clean-up, detail and export (stages 5-6) in detail

Read guide(topic="cloth") first. Simulate only a garment whose description, sheet, pattern, construction and start
pass.

## Methods (sheet key `method`)

- **`simulate`:** everything is sewn and simulated. The default, and right for states like hung and draped, where
  the whole shape is physics.
- **`settle`:** construct, settle lightly, detail (backend "zozo"). How artists get clean worn clothes.
  - Made pieces (wholly interfaced, or the garment's `"made": [names]`) are built finished by the placement: folded,
    closed at their closures, hugging the neck or wrist, held as constructed and carried through the poses.
  - Draped cloth is sewn onto them and settled at `coarse` (2 cm) in a short schedule (60 frames sewing, 30
    posing, 60 settling). The seams still have to close in the solver.
  - The result is carried onto the `resolution` mesh without a fine sim: draped cloth by transfer and smoothing, made
    pieces placed again at the fine size.
  - Fine folds are authored from the drape (`detail.folds`, on by default here): where the coarse cloth is left
    compressed, real cloth would fold finer than the mesh; the compression gives where, which way and how deep, the
    fabric gives the spacing (shirting 8-17 mm). They go into the normal map. `detail.fold_gain` scales them.
  - Worse than simulate: the clay geometry is the coarse drape smoothed (big folds soft and few); where fine made
    pieces meet carried cloth some crossings stay.
  - `"fine_settle": true` (opt-in, not working yet) is the intended finish.
- Made pieces are constructed ONCE (`made_from`, default "fine") and the coarse sim carries a sampled copy. Read
  `made_reshaped` in the result's `constructed` (must be empty) and the log's "made pieces start N% stretched past
  their rest" (under ~100%).

## Quality

- `quality="draft"`: one 2 cm simulation, about a minute on Blender. Puffy on purpose: judge fit and big shape.
- `quality="final"` (default): the whole assembly at 2 cm (bodice sewn first, then sleeves and collar, then
  gravity), carried onto a 1 cm mesh and settled again with self-collision. About 3-5 minutes on Blender.
- `resolution` (final triangle size) and `coarse` (blocking size) change the two meshes. Below 1 cm Blender's cloth
  gets softer and slower (collars and cuffs crumpled at 7 mm).

## Solvers and where they run

- **Blender** (`"backend": "blender"`, default): local.
- **ZOZO** (`"backend": "zozo"`, ppf-contact-solver): contact never lets cloth pass through itself or the body,
  stretch is limited. It sims once at `resolution` (no coarse -> fine); the cloth rests on the FLAT pattern
  (placement "smooth": dressed on straight arms, elbows bent back in a "pose" stage); interfaced pieces rest as made.
  The release is `$HIFIPUSHIE_ZOZO` (or `$PPF_ROOT`), else the asset pack (`uv run hifipushie-assets fetch zozo`).
  It runs on the local GPU (`$HIFIPUSHIE_ZOZO_DEVICE` cuda | rocm | cpu), or, with `$HIFIPUSHIE_ZOZO_REMOTE` set,
  through that command (run with the job folder as its last argument; it must leave out.npz there). `zozo` holds
  solver options (`contact_gap`, `strain_limit`, `dt`, ...); the log's `zozo <stage>:` lines say where the time went.
  On a laptop GPU judge at `"resolution": 0.02` (a shirt ~10 min, a jacket over a shirt 30-50 min); 1 cm finals
  want a desktop-class GPU.
- **`"file"`**: the job folder is written and out.npz is waited for (`HIFIPUSHIE_CLOTH_WAIT` s): you or another
  machine run it.
- **`"remote"`**: `$HIFIPUSHIE_CLOTH_REMOTE` is run with the job folder as its last argument and must leave out.npz.
- A result is keyed on the job's inputs and the solver's code, not on where it ran: a result made elsewhere is found
  locally. `look_cloth(result=<out.npz>)` shows any job folder's result on its garment.
- ZOZO seams: its stitches leave draped seams a few mm open (the clean-up welds what's within 1.5 triangles);
  `zozo.stitch_stiffness` 8 closes them to ~1-3 mm at ~3x the time. A seam that STARTS far apart is a placement
  fault (stage 4).
- **A sim that crawls** (seconds a frame where similar garments ran fast) is a fault in its start until shown
  otherwise: a piece through ITSELF, a hem gathered onto a shoe through itself, a too-tight fit (no room: contact
  everywhere). A normal job is minutes; cancel one that runs several times longer, read the place stage, go back to
  the last working ease. Never resubmit a job unchanged, and run one stage at a time (overlapping runs submit the
  same sim twice).
- `export_asset` and garment exports start sims for garments that aren't cached: test exports on cached garments.

## Read the report

- **Verdict.** `CORRUPT`: a piece tangled (> 20 crossings), crumpled (> 3% of triangles squashed or folded flat) or a
  seam twisted; nothing else counts until it's fixed; the report says which pieces and where. `TOO SMALL`: negative
  ease from the pattern. `STRAINED at <girth>`: stretched past the fabric's limit + 6% across front and back at that
  girth. `fits`.
- **Integrity**: crossings before and after the clean-up.
- **Surface.** Crinkle = the median angle between neighbouring triangles (1 cm sim 8-10 deg, cleaned 5-6; under ~5
  reads smooth). Folds = rms height of folds narrower than ~15 cm (a 20 mm deep fold 10 cm across reads ~9; a shirt
  with 15% ease on an A-posed body 3-4 mm). Folds come from pose, ease and gravity, not sculpting.
- **Strain map.** Blue slack, green fine, yellow at the fabric's limit, red twice it. Red rings at seams and buttons
  are the sewing (left out of the numbers). Red across a whole region: too tight. Read where strain is before adding
  ease (a placket's fold rows strain along and across; they're left out of the fit).

### Targets (stage 5 block in `look_cloth`)

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

- Judge clay with shadows off (`HIFIPUSHIE_CLOTH_SHADOWS=0`): stencil shadows of a coarse mesh draw jagged edges that
  read as torn cloth.
- Small features (a notch, the side neck, a cuff) in close cameras: `look_cloth(focus="jacket:collar", zoom=0.35)`.
- Surfaces in clay, or the exported GLB. Textured EEVEE looks can show pale grainy shards the GLB doesn't have.
- An under garment is drawn pressed in a look with the garment over it; a tucked under garment is never drawn
  without the garment over it (it's flattened onto the outer one's inner face). Show the untucked one alone, or the
  tucked one with the outer garment on. Every look, the scene and the export go through `cloth.worn_together`; a
  render you make yourself from raw arrays must too, and must weld seams and draw the buttons.
- The sim cache is keyed on the sim's inputs and the solver's code: a placement or pattern change re-simulates; a
  clean-up, report or map change applies at the next look of a cached sim. Before comparing two renders, check both
  were made after the change you're judging.
- Colour sampled from a concept's lit cloth renders too light under the look's lights: go a shade darker.

## Clean-up (automatic, numbers in `cleanup`)

It does what a sculptor's first pass does:
- Taubin smoothing removes crinkle (4 passes at 1 cm, scaled by mesh size; `smooth`); no vertex moves more than
  `keep` (4 mm), so real folds stay.
- Interfaced pieces aren't smoothed (smoothing their tight folds crumpled them).
- Seams the simulation closed are welded and PRESSED (`press`, default on): cloth within 3 cm of a seam is smoothed
  across it, as an iron leaves it. Interfaced cloth and "welt" seams are left alone.
- Anything pulled toward the body is pushed back out to `clear`.
- Every look, the scene and the export wind each piece to face out and give a seam's two sides one normal.
- A closed lap is CONSTRUCTED closed: the over band of every closed closure is laid 1.2 mm off the under piece
  between its first and last closed fastening and each fastening's sides brought together (up to 12 mm; further is
  the sim's failure and is reported: "lap ... laid closed"). `cleanup.seat: false` shows the raw lap.
- The placket band is cut and lifted after the sim (`closures.split_band_edges`, `relief` 1.2 mm: a step 1.5 mm
  wide); `cleanup.band_edges: false` turns it off.
- Patch pockets are seated on their piece as it finally lies (`cleanup.pockets: false` = off).
- `cleanup: false` shows the raw simulation.

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

Real seams are pressed and barely show: a seam that reads as a raised welt across the room is wrong. Judge in
close-ups: `look_cloth(name, focus="shirt:collar", zoom=0.35, textured=True, views=["front", "three"], strain=False)`.
The same maps go into `scene.blend` and the export.

## Closures and bands

- A band buttoned to itself (waistband, cuff, collar stand) is a MADE piece held as placed, so it must START closed,
  smaller than the body where it sits plus clearance (2.5 mm round the torso, 4 mm on a wrist or neck). 2-3% waist
  ease is enough. A wrap `out` on a self-closed torso band is ignored.
- A buttoned shirt collar is constructed closed at its buttoned girth, 1.2 mm off the neck: it needs the right size
  (~13 mm over the neck's BASE; Simon `collarEase` 0.115).
- **The placket must show, in geometry AND maps.** Closure `finish` {"over", "under"}: `box` (a shirt's buttonhole
  side: three layers proud, a crisp inner fold, two rows `topstitch` 3 mm in), `french` (a shirt's button side: a
  rounded folded edge), `facing` (a faced edge), `plain`. Default by kind (`kinds.<k>.closure`: shirt box over
  french; jacket and coat facing, holes `across`, no topstitching unless asked). `hole`: auto | along | across.
  `button` {holes 4|2, color, roughness, thickness, tone}. A jacket or coat front is not a box placket. Jacket
  buttons default to 20 mm, a darker tone of the cloth.
- These keys are look only in the design table (no re-sim); in a garment's own `closures` entry they re-key the sim.
- The maps draw no button under a closed lap; the report says `!! closure ... sides N mm apart` when the sim left a
  fastening open.
- Buttons are constructed after the sim; ADDING or MOVING one re-keys the sim (marks are mesh vertices), changing its
  look doesn't.

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
