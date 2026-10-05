# Clothes: designed, drafted, constructed, then settled

The aim is to work the way garment makers and garment artists actually work, so that what comes out reads as made
clothing. A tailor decides the garment before cutting. A pattern maker checks the pattern on the table before
sewing. A Marvelous Designer artist arranges, sews and simulates coarse before fine, and a ZBrush artist authors the
folds that matter. The tools follow those stages, and each stage gives you something to read and approve before the
next.

**The lesson this is built on (2026-10-03).** A day of solver tuning (stiffness, shear, plasticity, mesh size) chased
symptoms. The faults were construction: a sleeve cap with 44% ease, a collar stand stretched over a long neckline, a
missing belt, a lapped pleat sewn shut, a shirt with no sleeve placket, a coat with no lapel roll or facing, a collar
never pressed, every fabric with the same bend. So: **fix the construction first. Never tune the solver to hide a
pattern fault.** `dress` refuses to simulate while stages 1-3 fail.

Nothing is sculpted as a solid shell, and nothing is warped from one body onto another. The same machinery makes
other things from flat pieces: a tablecloth is one piece laid flat and draped on a table.

## The stages and their tools

| Stage | What a maker does | Tool | You get |
|---|---|---|---|
| 1. Design sheet | Decides kind, fabric, fit and every construction detail before drafting | `design_garment` (`garment_reference` to look choices up) | Every choice with its source (yours or the kind's default), the dimensions to work to, and what the draft source can't make |
| 2. Pattern | Drafts to the body's measurements, lays the pieces out, measures seams against each other | `look_pattern` | The pattern sheet image + checks: each choice evidenced in the pieces, seam ease, notches, ease against the body |
| 3. Construction plan | Plans the making: order, layers, what is pressed, what is interfaced, what is made on the table | `check_garment(stages=["construction"])` | Sewing order, layers and lap, fold lines with angles, interfacing, each piece made or draped, the sim's schedule |
| 4. Arrange | Pins the pieces round the dummy | `check_garment(stages=["place"])` | A render of the start + crossings, pushes, start stretch, layer gaps |
| 5. Draft | Blocks at 20 mm and judges fit and big shape | `dress(quality="draft")`, `look_cloth` | The report + numeric targets (collar cover, layer gaps, hem level, waistband, sleeves hung) |
| 6. Final | Refines, cleans up, details, exports | `dress(quality="final")`, `look_cloth(textured=True)`, `sync`, `export_asset` | The finished garment |

`check_garment(name, garment)` with no stages runs all of them in order and lists failures first.

Other tools:
- `dress(name, garment, spec={...}, state, quality, wait, force)` stores `spec["cloth"][garment]` (merged key by key)
  and starts the simulation in the background. `dress(name)` reports where every garment stands. `force=True`
  simulates over failing construction checks (to see a fault, not to ship it).
- `look_cloth(name, views, strain, focus, zoom, textured)` renders the garments with a strain row, the report and the
  stage 5 targets. `focus="shirt:collar"` with `zoom` in metres is a close-up.
- `edit_model` with kind `"cloth"` changes numbers directly. A cloth-only edit validates only the cloth.
- `sync(name, cloth_only=True)` puts simulated garments into `scene.blend` (collection "cloth"); `pull` brings colour,
  roughness and sculpted shape back.

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

## The workflow, stage by stage

### 0. Body

A garment is drafted to the body it's on (`tailor.measure`: FreeSewing's measurements taken off the surface), so the
model needs a `base` body (MakeHuman parameters). A prop for a drape (a table) needs no body.

### 1. The design sheet (`design_garment`)

*How makers do it:* a tailor's order sheet and a technical designer's spec name the collar, cuff, closure, pockets,
hem and fabric before anything is cut. In Marvelous Designer the same decisions are the first blocks you draw.

```
design_garment(name, "shirt", design={"kind": "shirt", "from": "simon", "fit": "regular",
               "fabric": "cotton_shirting", "details": {"cuff": "barrel", "hem": "shirttail"}},
               spec={"color": "#8fb3d9", "quality": "draft"})
```

- **kind:** shirt, blouse, tee, hoodie, jacket, coat, trousers, shorts, skirt, dress, flat. It sets the fit's ease
  bands, the default details, the sleeve cap's ease band and the sewing order.
- **from:** what drafts it. `simon` (shirt, FreeSewing), `carlton` (overcoat, FreeSewing), `skirt_block` (our own
  skirt draft). Leave it out and give own `pieces` + `seams` on the garment (name each piece's `"role"`).
- **fit:** the kind's fits (shirt slim/regular/relaxed, skirt straight/a_line/full). Stage 2 checks the pattern's
  ease per girth against its band.
- **fabric:** a fabric with physical numbers (weight, thickness, woven or knit, bending length) mapped to the solver's
  preset: cotton_shirting, oxford, linen, cotton_twill, denim, wool_suiting, wool_coating, jersey, rib_knit,
  french_terry. Different fabrics must bend differently: one preset on every garment reads generic.
- **details:** one choice per detail, or `{"type": choice, "options": {raw draft options}}`. Anything you leave out
  takes the kind's default, and the reply says so. `garment_reference(detail="collar")` lists the choices with what
  each is made of, its seams, fold lines, interfacing, dimensions and checks.
- **method:** `"simulate"` (sew and simulate everything) or `"settle"` (see stage 5).
- **pattern:** draft words passed through (`ease`, `length`, `sleeve_length`, `options`, `measurements`).

Hard failures here:
- a choice the draft source can't make (the reply names what it can make: say that choice in the sheet);
- a choice that needs another (a barrel cuff needs a sleeve placket; buttons need a placket).

Tailoring numbers the knowledge base carries (all checked in stage 2 where the pieces exist):

| Detail | Practice |
|---|---|
| Shirt collar | Stand 30-35 mm at CB, 25-30 at CF. The fall covers the stand and its seam by 6-10 mm at CB. Points 65-80 mm. Roll a few mm above the collar/stand seam |
| Barrel cuff | 60-70 mm tall. Closed girth = wrist + 25-40 mm. Overlap 20-25 mm. Needs a placket opening 120-150 mm |
| Sleeve cap ease | Shirt 0-3%, coat and jacket 3-6%, knit about 0 |
| Other seams | Within 1.5% unless designed to ease. Notches within 6 mm |
| Waistband | 30-40 mm finished. Closed = waist + 0-30 mm. Ends lap 25-40 mm |
| Rib neckband | 80-92% of the neckline's length |
| Hems | Shirttail 5-6 mm, straight 10-25, skirt and trouser blind hem 30-50, coat 40-50, knit 20-25 |
| Buttons | Shirt 10-12 mm, 70-110 mm apart. Coat 20-25 mm. The buttonhole side laps over |
| Notched lapel | A roll line, a facing, fronts interfaced but free to roll |
| Lapped vent | One CB extension (35-50 mm) laps the other, tacked at the top, never sewn full length |

### 2. The pattern, laid flat and looked at (`look_pattern`)

*How makers do it:* a pattern maker "walks" each seam (measures one edge along the other), checks notches meet, and
measures the pattern against the body before cutting. In MD you read the 2D window before you press simulate.

The sheet shows every piece at one scale: name, role, size, where it goes on the body, grain arrow, notches (red),
buttons and buttonholes, the draft's internal lines (grey), fold lines (blue dashed, with angle), interfacing
(hatched), and each seam in its own colour, numbered on both sides (S3a meets S3b). The seam list underneath gives
each seam's two lengths and ease.

Checks, failures first:
- **Evidence.** Every sheet choice is found in the pieces and the seam table: a turned collar has a fall, a stand, a
  seam between them, a fold line and interfacing; a barrel cuff is closed on itself by its button and interfaced;
  a waistband closes at waist + 0-30 mm.
- **Seams.** Ease per seam kind (sleeve cap by garment kind, bands -1..+1.5%, plain seams within 1.5%), and notches.
  Both sides of a seam are sewn by fraction of their length, so a notch mismatch on the sheet is a real misalignment.
- **Fit.** Ease against the body per girth, inside the fit's band. Negative ease on a woven is TOO SMALL.
- **Loose pieces.** Every piece is sewn to something.

Fix what fails in the sheet (`design_garment` again: a detail's `options`, `pattern.ease`, another choice), then
look again. Don't go on with failures you can fix.

### 3. The construction plan (`check_garment(stages=["construction"])`)

*How makers do it:* collars, cuffs, plackets and waistbands are made finished on the table (interfaced, turned,
pressed) before they meet the garment. In MD these are fold angle + fold strength on internal lines, Fold
Arrangement, bond/interfacing presets and layers. Nobody simulates a collar into shape.

The plan lists:
- **Sewing order**, torso pieces first (the simulation sews the bodice alone first too), then the kind's order.
- **Closures** (button stitches) and **layers**: which piece starts outside which, and whether the lap follows the
  kind's convention.
- **Fold lines** (garment key `folds`), each a line on a piece with an angle and a strength:
  `{"piece", "line", "angle", "strength", "kind": "press" | "roll", "radius"}`.
  - `angle` is the dihedral on the pattern's face side (the side placed away from the body): 180 flat, 0 folded right
    over onto the face (a collar's fall over its stand, a lapel rolled onto the chest, a turned-back cuff), 360 folded
    right under (a hem, a facing, a placket).
  - `line` is a line name of the piece, two point names, points in metres, `{"edge": "piece:a>b", "offset": m}` (parallel
    to an edge) or `{"mid": "x"}` (lengthwise through a band's middle).
  - `kind` "press" is one sharp crease; "roll" spreads the turn over an arc of `radius` (as many vertex rows as
    the mesh can carry; a tight roll on a coarse mesh is one crease). `strength` 0..1 is how hard the crease holds
    its angle. `flap` (a point or mark name) says which side turns when the default (the side with less sewn edge,
    then the smaller one) is wrong. A fold must run from edge to edge of its piece.
  - What a fold does (`folds.py`):
    - the mesh gets a row of vertices on the line, so edges run along the crease;
    - the placement lays the piece on its wrap unfolded and turns the flap about the row, as far as the fold asks or
      as it clears what is under it (its own base side, the pieces under it, the body), per station along the line:
      a collar's fall lies on its stand and opens over the shoulders;
    - the solver keeps it: made pieces rest as placed; ordinary cloth in ZOZO rests on the flat pattern with the
      hinges along the fold resting at its angle and bending 20x harder at strength 1 (`fold_press`); Blender's
      cloth rests on the placement, where a fold is a U 8 mm across (its collision distances).
  - `look_cloth` / the report measure each fold: the turn across it, the gap between flap and base
    (`folds.measure`).
  - How tight a fold can be depends on who makes it. A simulated crease is a wedge 5-7 degrees open (the first ring
    of vertices needs a contact gap), so its layers are 3-6 mm apart at 1-2 cm triangles. A constructed one (method
    "settle") is a U two cloth layers across: 1.6 mm.
- **Interfacing** and its bending multiplier (practice 5-20x the shell; whole pieces or a band along a line).
- **Made or draped, per piece.** Made pieces are constructed finished and keep their made shape (collar, stand,
  cuffs, waistband). Draped pieces are loose cloth shaped by body, gravity and seams (fronts, backs, sleeves, skirt
  panels). The sheet's `"made": {piece or role: "made" | "draped"}` overrides. It fails when draped cloth is wholly
  interfaced (it would be frozen as placed: this is what stopped the coat's lapels rolling).
- **The simulation's stages** as they will run.

### 4. Arrange (`check_garment(stages=["place"])`)

*How makers do it:* MD's arrangement points put each piece on a bounding cylinder round the body part it covers,
symmetric pairs symmetric, before any simulation.

The render shows the start: torso pieces on one cylinder round the trunk (wrap `"to": "torso"`, `"side"`, and
`"level": "waist"` for pieces that hang from the waist), sleeves round the arms, bands round the neck or wrist.
Checks:
- pieces through each other at the start (a failure for a contact solver, a warning for Blender);
- a neck band pushed more than 8 mm out of the neck (it is taller than the neck: lower it);
- start stretch past the solver's strain limit (ZOZO can't start there);
- layer gaps at the start.

### 5. Draft, then judge against numbers (`dress(quality="draft")`, `look_cloth`)

*How makers do it:* MD artists block at 20 mm particle distance and judge only fit and big shape; they refine after
the fit is right. A fitter reads drag lines: folds point at what is too tight or too long.

Two methods (sheet key `method`):
- **`simulate`:** everything is sewn and simulated. Today's default, and the right one for states like hung and
  draped, where the whole shape is physics.
- **`settle`:** construct, settle lightly, detail (backend "zozo"). This is how artists get clean worn clothes.
  - **Made pieces** (wholly interfaced, or the garment's `"made": [names]`) are built finished by the placement:
    folded at their fold lines, closed at their closures, hugging the neck or wrist. The solver never shapes them:
    they are held as constructed and ride the body through its poses.
  - **Draped cloth** is sewn onto them and settled at `coarse` (2 cm) in a short schedule (60 frames sewing, 30
    posing, 60 settling: 150 against 330). The seams still have to close in the solver: the placement is isometric,
    not sewn.
  - **The result** is carried onto the `resolution` mesh without a fine sim: the draped cloth by transfer and
    smoothing, the made pieces placed again at the fine size (their folds a U two layers across) and set where the
    coarse ones were held, their flaps laid on the cloth that arrived under them.
  - **Fine folds** are authored from the drape (`detail.folds`, on by default here; `cloth_detail.py`): where the
    coarse cloth is left compressed, real cloth would have folds finer than the mesh. The compression gives where,
    which way and how deep; the fabric gives the spacing (shirting 8-17 mm). They go into the normal map with the
    sewing details, so the look isn't limited by the sim mesh. `detail.fold_gain` scales them.
  - On the test shirt (2 cm settle + 1 cm construct, laptop GPU): 205 s against 290-450 s for the full 2 cm sim;
    sleeve crease width 3.4 mm (full 1 cm sim 6.7), fold spacing 8.7 mm (19.7), the collar's fall 5 mm below the
    neckline seam at centre back (12 mm above it).
  - What it does worse: the clay geometry is the coarse drape smoothed, so big folds are soft and few (the larger
    authored folds are put into the geometry of a 1 cm mesh, the fine ones are a normal map); where the constructed
    fine pieces meet the carried cloth (a collar's ends on the fronts) some crossings stay (18 on the test shirt).
  - `"fine_settle": true` (opt-in, not working yet) is the intended finish: a short settle at the fine size with
    the made pieces prescribed and their flaps pressing the cloth down, instead of moving cloth by hand.

A draft is one 2 cm simulation, about a minute. It looks puffy on purpose. Read:
- the **verdict**: CORRUPT (tangled or crumpled), TOO SMALL, STRAINED at a girth, or fits;
- the **targets** (stage 5 block in `look_cloth`), each judged at the quality it belongs to:

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

**Fix fit in the pattern** (ease, length, a detail's options), never by sculpting, and never by solver settings.

### 6. Final, clean-up, detail, export

*How makers do it:* MD finals run at 5 mm particle distance or less with thinner collision; the simulation is then a
blockout that is cleaned up (remesh, smooth the noise, keep the big folds), and seams, topstitching, hems and buttons
come last. The reference sections below cover each part.

#### Final quality

- `quality="final"` (the default):
  - The whole assembly runs at 2 cm: bodice sewn first, then the sleeves and collar, then gravity.
  - The result is carried onto a 1 cm mesh of the same pattern and settled again with self-collision.
  - This is the coarse-then-fine particle distance artists use. It takes about 3-5 minutes.
- `resolution` (final triangle size) and `coarse` (the blocking size) change the two meshes.
- Below 1 cm, Blender's per-edge bending makes the cloth softer and the solver slower. The collar and cuffs crumpled
  at 7 mm.

#### The ZOZO solver (`"backend": "zozo"`)

- ZOZO's contact solver (ppf-contact-solver) is the cloth solver being developed: contact never lets cloth pass
  through itself or the body, and the stretch is limited (cotton-like, a few %). Blender stays the local default.
- It sims once at `resolution` (no coarse -> fine). The cloth rests on the FLAT pattern (placement "smooth": dressed on
  straight arms, the elbows bent back in a "pose" stage); interfaced pieces (collar, stand, cuffs) rest as made.
- On this laptop's GPU judge at `"resolution": 0.02` (a shirt ~10 min, a hung coat ~30 min); 1 cm finals go to a rented
  GPU box ($HIFIPUSHIE_ZOZO_REMOTE). A result is keyed on the solver's own code, so a pod's result is found here.
- `zozo` holds solver options (`contact_gap`, `strain_limit`, `dt`, ...); the log's `zozo <stage>:` lines say where
  the time went (steps per frame, how much of each step the strain limit or contact allowed).
- `look_cloth(result=<out.npz>)` shows any job folder's result on its garment.

#### Read the report

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
  - Folds is the rms height of folds narrower than ~15 cm (a 20 mm deep fold 10 cm across reads ~9). A shirt with 15% ease on an
    A-posed body measured 3-4 mm: it hangs close. Folds come from pose, ease and gravity. They are not
    sculpted in.
- **Strain map.** Blue is slack, green fine, yellow at the fabric's limit, red twice it. Red rings sit at seams and
  buttons (the sewing springs: left out of the numbers). Red across a whole region means it's too tight.

#### Clean-up (automatic, numbers in `cleanup`)

It does what the sculpt pass does first:
- Taubin smoothing removes the crinkle. 4 passes at 1 cm, scaled by the mesh size; `smooth`.
- No vertex moves more than `keep` (4 mm). Crinkle is a few mm deep, so a bigger move would be flattening a real fold.
- Interfaced pieces (collar, stand, cuffs, plackets) aren't smoothed: they don't crinkle, and smoothing their tight
  folds crumpled them.
- Seams the simulation closed are welded.
- Anything pulled toward the body is pushed back out to `clear`.

`cleanup: false` shows the raw simulation.

#### Detail: seams, stitching, hems, buttons

These are drawn from the pattern itself into maps on the flat-pattern atlas (`detail`):
- a groove along every sewn edge, with the seam allowance's ridge beside it (`seam`, `seam_width`, `allowance`);
- a dashed topstitch `topstitch` m in from every edge (`stitch` length, `stitch_gap`);
- a turned-up hem `hem` m deep along free edges;
- buttons (discs with four holes) on marks named `button*`, and stitched slots on `buttonhole*`;
- the thread colour (`thread`, default a shade lighter than the cloth);
- fine folds authored from the drape (`folds`: true | false, default on for method "settle"; `fold_gain`;
  `fold_opts` overrides the fabric's `wavelength` [min, max], `length`, `sharp`).

Judge them in close-ups:
```
look_cloth(name, focus="shirt:collar", zoom=0.35, textured=True, views=["front", "three"], strain=False)
```
The same maps go into `scene.blend` and the export.

#### States

- `"worn"`: sewn on the body and settled.
- `"hung"` / `{"hang": {"hanger": {...}, "rail": {...} | false}}`: on a hanger, the way a person hangs it.
  - Dressed on the body first (a coat sewn in the air with nothing inside caved in). The hanger is then already
    INSIDE it: its arms under the body's shoulders along their slope, its hook up through the neck opening, clear of
    the collar, curled over a face-out bar that runs back to a post behind the garment.
  - The body is taken away and gravity settles the garment onto the hanger. Nothing is pinned: contact with the arms
    carries the weight. The seams are welded while it hangs (as sewing springs they opened under the weight).
  - hanger: `kind` "wood" (default: a shaped coat hanger, broad rounded shoulder ends) or "wire"; `width` tip to tip
    (default: the body's shoulder points less 2 cm); `bar` (a trouser bar); `slope` deg; `clear` (how far under
    the shoulder surface the arms' tops sit, 8 mm); `rise` (the hook above the arms). rail: `length`, `radius`,
    `posts`, or false.
  - The report's `hanger:` line says what carries it ("supported by: arms 98% (L 51, R 47), hook 1%... pins 0%") and
    whether the hanger is inside: rays forward, back and up from each arm must meet the cloth, the hook's rod must
    cross no cloth and the cloth must surround it at the collar. It leads the verdict with NOT ON ITS HANGER when
    pins carry it, one shoulder carries almost nothing, it is still moving, or the hanger isn't inside it.
- The old pinned hang `{"hang": {"pins": ["stand:bottomLeft"], "hook": [x, y, z], "rack": [[a, b, r], ...]}}` (a
  pin patch moved under the hook) still works; its report says the pins carry it.
- `"draped"` / `{"drape": {"over": "model" | "body"}}`:
  - Pieces wrapped `{"to": "flat", "at": [x, y, z]}` fall onto the model's surface: a tablecloth on a table, a blanket
    on a bed.

#### Hand pass in Blender (when numbers won't get it)

- `sync(name, cloth_only=True)`, then open `scene.blend`.
- Sculpt the garment there: smooth a buckle, push a fold, design a memory fold at the elbow. Recolour its `hp_color`
  node if needed.
- `pull(name)` keeps the shape as offsets on that simulation. A new simulation drops them (they belong to its
  surface), and the report says so.

#### Export

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
| A hung coat bunched up into a sack | A strong sewing force while hung (it drives every seam, not just the pins), or a rack collider thicker than it looks (Blender's default outer thickness is 2 cm) | Fixed: the sewing force stays at `sew_force` while hung, rack colliders are 3 mm thick. Hang it on a hanger (two bars inside the shoulders in `rack`), not a single pin: on one pin a coat folds in on itself |
| Collar or stand crumpled on a thin neck | The band is taller than the neck between the shoulders and the jaw. It started pushed out of the jaw, and that stretch went into its rest shape | The report's HINT; lower the stand (simon: `"options": {"collarStandWidth": 0.045}`) |
| Shirt rides up / sleeves dragged up the arm | Sewing everything at once lifts the bodice | Assembly order: the bodice is sewn first, cuffs held (`assemble`) |
| Puffed sleeve caps, a gathered knotted waist, a collar like a funnel, ruffled cuff joins | Construction, not the solver: cap ease, seam lengths that do not match, a missing piece, a fall too short for its stand, no placket | `look_pattern`: fix every failing seam and evidence line before simulating. Never tune stiffness to hide them |
| A lapel or collar that will not roll | The piece is wholly interfaced, so it rests as made (frozen as placed), or it has no fold line | Interface a band, add a fold line; stage 3 fails on this |
| A skirt slides down or one side seam gapes | Lower-body pieces start on a cylinder much wider than the waist and the sewing has to close 10+ cm; the body has no hip to hold a waistband | Keep the fit close (straight / a_line), waist ease under 3%; a waist-fitted start is still to do |
| `dress` says NOT simulated | Stages 1-3 fail | Read the failures, fix the sheet or the pattern; `force=True` only to look at the fault |

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


## Designing a garment that doesn't exist: block + operations

*How pattern makers do it.* Nobody drafts a new jacket from nothing. They start from a **block** (a sloper: the
basic bodice, sleeve, skirt or trouser drafted to the body by fixed rules, with wearing ease and no style) and
derive the design by a short list of operations. Helen Joseph-Armstrong reduces all of flat pattern making to three
principles:

1. **Dart manipulation.** The shaping a body needs is an angle at an apex (bust, shoulder blade, seat). It can be
   moved to any edge, into a seam, or released as ease, gathers, pleats or flare, without changing the fit.
2. **Added fullness.** Slash and spread to add cloth (or close to remove it); the hinge edge keeps its length.
3. **Contouring.** Where the garment lies closer than the block over a hollow, the excess is taken out along a seam.

Aldrich's and Mueller & Sohn's systems work the same way, and so do FreeSewing's own designs (Simon and Teagan come
from the Brian block; Carlton and Jaeger from Bent, which is Brian with a two-piece sleeve; trousers from Titan).
Marvelous Designer artists block a new garment out from basic shapes the same way before they refine it. Draping on
the form is the other route (cloth pinned on a dummy, then trued flat); here the simulation plays the dummy, after
the flat draft.

A ready-made draft (`from: simon`) is a reference and a proof. The capability is this:

```
design_garment(name, "jacket", design={
  "kind": "jacket", "block": "bodice", "fit": "regular", "fabric": "wool_suiting",
  "block_options": {"fitted": true},
  "ops": [
    {"op": "style_line", "piece": "front", "name": "princessF", "from": {"edge": "hps>shoulder", "t": 0.5},
     "to": {"edge": "hem>cfHem", "t": 0.45}, "via": ["bust"], "names": ["front", "side_front"], "take_in": 0.03},
    {"op": "style_line", "piece": "back", "name": "princessB", "from": {"edge": "hps>shoulder", "t": 0.5},
     "to": {"edge": "hem>cbHem", "t": 0.45}, "via": [[0.09, -0.30]], "names": ["back", "side_back"], "take_in": 0.035},
    {"op": "extend", "piece": "front", "edge": "cfNeck>cfHem", "amount": 0.02, "name": "stand"},
    {"op": "facing", "piece": "front", "edges": "stand", "width": 0.07},
    {"op": "sleeve", "cap_ease": 0.045}, {"op": "two_piece"}],
  "details": {...}})
look_pattern(name, "jacket")
```

`garment_reference(principles="derivations")` lists, per garment category, which block and which operations make
it and why (shirt, blazer, cropped jacket with a shawl collar, wrap dress, hoodie, raglan, A-line skirt, wide
trousers); `principles="blazer"` gives one; `"operations"`, `"blocks"` and `"rules"` give the vocabulary.

**Blocks** (`"block"`; options in `"block_options"`). Every construction point is named (cfNeck, hps, shoulder,
armholePitch, armhole, waist, hem, cfHem, bust, the darts' points...), so operations address points, never numbers.

| Block | Drafted from | The rules that matter |
|---|---|---|
| `bodice` | neck, shoulders, chest, waist, hips, lengths | Chest quarter = chest x (1 + ease) / 4. The front neck's depth is solved so the neckline is half the neck girth + ease. Armhole depth from waist-to-armpit. Waist suppression goes to the side seam, a dart, or is left for panel seams. Options: `fitted`, `darts`, `bust_dart`, `length` (hips, waist, or metres), `cb` / `cf` (fold, seam, open) |
| `knit` | the same | The bodice with 0-2% ease, no darts, a looser neck, a cap without ease |
| sleeve (op `sleeve`) | biceps, arm lengths, wrist, **the armhole** | Width = biceps + ease; cap length = armhole + cap ease; the cap's height is solved from those two. A wide sleeve gets a low cap, a narrow one a high cap |
| `trouser` | waist, seat, rise, leg lengths | Seat quarters -1 / +1 cm; fork = seat / 16 + 5 mm (back about double); the back seam slanted and raised; the back inseam 5 mm short |
| skirt (`from: skirt_block`) | waist, seat | Quarters with ease; the difference shared between side seam and darts |

**Operations** (`"ops"`, applied in order to HALF pieces, centre at x = 0; `unfold` runs last by itself):

| Op | What it does | What it keeps |
|---|---|---|
| `style_line` | Cuts a piece along a line between two outline points (through `via` points): panels, yokes, princess seams. `take_in` shaves both edges at the waist | The two edges are one line: sewn 1:1 |
| `take_in` | Contours an existing style line at a level | Both edges alike |
| `dart` | Moves a dart to another edge, turning the outline about its apex | Every seam length; the centre line stays put |
| `dart_to_ease` | Straightens a dart's edge: the intake becomes ease or gathers | Declares that ease on the seam |
| `flare` | Slash from an edge to a hinge and spread (negative: close) | The hinge edge's length; the edge is trued to a curve |
| `lengthen` | Moves everything below a level (name both front and back) | Mating seams |
| `extend` | Pushes an edge out: button stand, wrap, vent | The old edge as a line |
| `reshape` | Moves a named point, neighbours eased | |
| `facing` | A new piece traced from a piece along edges | Sewn 1:1, turned in |
| `collar` | Drafted from the neckline as it is now: `band` (stands), `flat` (lies flat), `roll` (between), `tailored` (a jacket's: `stand_height` + `fall` on a roll line, outer edge longer by `spring` so the fall lies on the shoulders, ending at the lapel's gorge; points cbNeck / cbRoll / cbOuter / endNeck / endRoll / endOuter) | Sewn edge = the neckline |
| `sleeve` | Drafted into the armhole as it is now, whatever was cut before | Cap = armhole + declared ease |
| `two_piece` | Top and under sleeve from the one-piece; `elbow` (m the wrist comes forward) bends each about its forearm seam's elbow point | Cap length, forearm seams equal, elbow ease on the hindarm declared |
| `contour` | Shapes an edge by an amount per level (`at`: [[level, m] ...]; top, chest, waist, hips, hem or a y): a shaped centre-back seam, a hem's spring. A style line's name shapes both its edges | Mirror seams equal; a panel seam's small difference declared |
| `join` | Two pieces sewn together become one, the seam gone: a side panel with no side seam, a yoke cut on | Every other seam and edge; says how much shaping the seam's curve carried (now lost) |
| `round_corner` | A corner rounded (`radius` or `along` [m, m]): a cut-away front hem, pocket corners. Before facings | The corner's name, on the curve |
| `pocket` | `type` patch / kangaroo / welt / flap: laid on a piece's outside and tacked along its sewn edges (`at` [x, y] the top edge's middle, `width`, `height`). `type` in_seam (`piece` front, `other` back, `top`, `opening`): the seam left open, two bags sewn to its lips, lying inside the front | The piece under it; the split seam's two parts |
| `lining` | Every body piece traced as `<piece>_lining`, sewn to each other as the shells are, laid inside them, sewn to the shell along `attach` (hems, sleeve hems, back neck). Last, before unfold | The shells' seam matches |
| `fisheye` | A double-pointed waist dart on a piece that runs past the waist (run on to the hem as a closed cut). `darts: true` on a hip-length bodice makes them | Its legs equal |
| `neckline` | Redraws the neckline on front and back together: `widen` along the shoulder, `front` / `back` lower, round / v / square | The shoulder seams equal |
| `shawl` | A shawl collar cut on with the front: stand, break point, roll line, the collar grown on past the neck point, a CB collar seam | Neck seam = the back neck; a roll fold |
| `lapel` | A notched lapel (stand, break point, lapel point, roll fold; `gorge: "straight"` + `gorge_drop` + `notch`: the tailored straight gorge); then `collar` with `"stop"` ends the collar at the gorge | The neckline; `lapel_edge` and `gorge` for a facing |
| `cut_away` | Cuts along a line and keeps the side holding a point: V necks, slanted hems, asymmetric fronts | The kept side's seams |
| `darts_to_seam` | Two darts of a piece joined through their tips into a panel seam | The darts' suppression |
| `raglan` | Front and back cut from neck to armhole, the shoulder parts joined to the sleeve (after `sleeve`) | The underarm's cap / armhole lengths |
| `kimono` | The sleeve cut in one with the body; placed in two parts (body on the torso, sleeve round the arm) | |
| `hood` | A two-piece hood on the neckline, placed round the head | Neck edge = the neckline |
| `pleat` | Spreads a piece by twice the depth along a line across it; two press folds | Seams skip the underlay |
| `buttons`, `stitch` | Button marks down a lapped front; a point stitch (a wrap's tie) | |
| `unfold` | Halves into whole pieces. Put it in the list yourself to work on ONE side afterwards (`front.L`): asymmetric designs | Seams mirrored |

`facing` takes several edges in a row (`["shawl_edge", "centre_front"]`): it is the part of the piece within its
width of them, so it follows the piece's own outline past their ends. `collar` takes `"ratio"` (a rib band cut 0.85
x the neckline, the ease declared). `take_in` gives the SIDE panel 65% of the shaping (`share`), as a tailor cuts.

Two things make these composable. **Points have names**, and a point spec can be a name or a place on an edge
(`{"edge": "hps>shoulder", "t": 0.5}`, or `"dist"` in metres, or `"y"` at a level). **Named edges survive
operations**: the draft carries `armhole_front`, `neck_back`, `hem_front`, `shoulder_front`, `centre_front`... and
every cut or dart move rewrites them and the seam table, so "the armhole" is still the armhole after a princess
seam has cut it in two.

Every seam is measured after the operations. Its two sides are the same length, or the operation that made them
differ **declared** the ease (a cap's ease, gathers from a dart, a stretched inseam): stage 2 shows it as
`declared` with the reason. Anything else is a failure to fix in the operations, not in the solver.

The rules of thumb (`garment_reference(principles="rules")`):
- **Ease** is wearing ease plus design ease. Woven chest: fitted 5-8%, shirt 10-20%, jacket 8-15% over a shirt,
  coat 15-30% over a jacket; knits 0 or negative. A skirt or trouser waist 0-3%.
- **Balance.** Front and back hang level from the shoulder. The front is longer over a bust by the dart's intake.
- **Grain** runs down the centre front and back, the sleeve's centre and the trouser crease.
- **Shaping** points at an apex and stops 15-25 mm short of it.
- **Proportions.** Button stand = the button's diameter. Facings 60-90 mm. A princess line crosses the shoulder a
  third to half way along and passes over the apex.

Checked against a known draft: our bodice block on the test body against FreeSewing's Brian at the same ease has
the same chest width, armhole depth, shoulder seam and side seam to 0.1 mm, back armhole within 2 mm, necklines
within 1 mm, and the back outline within 2 mm on average (`workspace/cloth_renders/pd_00_block_vs_brian.png`). Ours
hollows the front armhole 9 mm more (Aldrich's narrower across-front), and for the same biceps ease our sleeve is
35 mm narrower with a 26 mm higher cap: Brian widens its sleeve by its own rule, ours solves the cap for the width
asked.

**Trousers** are placed now: wrap `leg.L` / `leg.R` (the trouser block sets it). Each leg's pieces start on one
upright surface round that half of the body, cut flat between the legs; the fork lies on the flat; the inseam and
side seam start open and the sewing closes the legs. Give a waistband by `generate`, its `along` chain starting at
the band's own opening (a band wrapped `side: front` opens at centre back: start the chain at `back.R:cWaist`); a
chain that starts half a turn away sews the band on twisted (verdict CORRUPT, twisted seams).

**Three garments designed from prose through these tools** (sheets and draft renders `workspace/cloth_renders/
pd_20..22_*`), judged honestly:
- *Wide-leg trousers* (trouser block, relaxed, waistband generated): all stages pass; the 2 cm draft reads as
  trousers, verdict "fits", 0 crossings, strain p95 5.9%. Wrong: they slide 9 cm down (a waistband 17 mm over the
  waist holds nothing), pool on the feet (the block's length runs to 3 cm off the floor), and balloon at the hem.
- *Asymmetric wrap tunic* (bodice, neckline widened, princess lines, `unfold`, the left front extended 22 cm and
  both fronts cut to V lines, tied by a stitch): reads as a wrap tunic; 2 crossings, strain 11.8%, the hem hangs
  9 cm lower on the wrap side, the under front bunches at the neck. The gate was right three times on the way
  (waist ease outside the fit, a take-in that ran into the hips): shaping lives at the DRAFT's waist line, the
  check measures at the body's.
- *Cropped shawl-collar princess jacket* (bodice, princess lines, `shawl`, facing, one button, two-piece sleeve):
  the pattern and construction stages pass and the sheet reads as that jacket. The draft sim is CORRUPT: the
  cut-on collar starts standing up the front of the neck and Blender's sewing doesn't bring it round (twisted
  collar seams), and the two-piece sleeves bunch at the shoulders. This design needs a start that lays the collar
  round the neck (a fold-aware placement) and method "settle"; neither was available here.

**A blazer from our blocks against FreeSewing's Jaeger** on the same body (`pd_30_blazer_vs_jaeger.png`): centre
back length, shoulder seam, upper armhole and back neck agree within 1-5 mm, the armhole within 12 mm (2%), top +
under sleeve width within 2 mm. Where a tailor's draft differs from ours, and what to build next: Jaeger shapes the
centre back seam and cuts a side panel that drops from the armhole (ours: a straight CB and a diagonal style line);
its waist is 17% over the body where ours is 29% (the fitted block leaves 36 mm a quarter for seams we only half
used); its hem has 12% over the seat (ours 2%: hips ease is taken at the high hip); its sleeve is 30 mm longer,
bent far more at the elbow, with a hollowed under sleeve and a hem 39 mm wider; its gorge is a straight line and the
front hem is cut away in a curve.

Since then: `contour` (the shaped centre back, the hem's spring), `join` (the side panel with no side seam), the
straight gorge, `round_corner` (the cut-away hem), `fisheye`, the bent two-piece sleeve, and `take_in` on a straight
cut (it had shaped nothing: the cut had no vertices) bring the same blazer to waist +16% (Jaeger +17%) and hem +12%
(+12%).

One cloth on two parts of the body: a shawl collar's back (past the neck point) lies round the neck, a kimono
sleeve round the arm, while the rest of the piece lies on the torso. The draft cuts such a piece for placement only
(a "hinge"; the seam list shows the join as declared, "one cloth: cut here only to place them"). You don't write
hinges: `shawl` and `kimono` make them. A facing (and a lining, a pocket) is LAID ON the piece it was traced from,
so it follows that piece round a roll line.

A pleat is laid CLOSED by the placement (the cloth past its line runs back a depth and on again: three layers), a
raglan sleeve's shoulder parts stay on the torso, and a point may be given by level: `{"edge": ..., "y": "waist"}`.

Not built yet: a welt pocket's cut and bag; a lining with its own pleat and trimmed to the facing; pleats that die
inside a piece.

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

Still open (the checks say so where they can):
- Carlton's facing and lapel roll; pleats as folds (they are seam gaps: a fold that dies out inside a piece is a
  cone, and a pleat's layers are finer than a 1-2 cm mesh); double-layer (bagged) cuffs and collars;
- welt / flap / in-seam pockets; a lining's own pleat and fabric;
- button size and buttonhole direction per design in the detail maps;
- crease width and fold spacing measured by the tools; grain anisotropy.

## Construction audit and knowledge base

`cloth_audit.md` is the audit behind the numbers above. `garment_kb.json` is the knowledge base the sheet and checks
read (`garment_reference`): add a kind, a detail choice or a draft source there, with its evidence checks, and the
workflow covers it. `cloth_check.report(Bp, kind)` is the bare seam-table check.
