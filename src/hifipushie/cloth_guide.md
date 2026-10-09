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
| Shirt collar | Stand 30-35 mm at CB, 25-30 at CF, but never taller than the neck allows: neck height (trapezius to jaw) - 13 mm, at least 20 (`collar_rule`). The fall covers the stand and its seam by 6-10 mm at CB (fall = stand + 12). Points 65-80 mm. Roll a few mm above the collar/stand seam. Buttoned girth ~13 mm over the neck's base |
| Jacket collar over a shirt | Stand at CB = the shirt's stand + a few mm (20 mm shirt band -> 24 mm; short neck 19 / fall 31). The shirt collar shows 10-20 mm above it at CB. Lower the back neck, not the stand |
| Jacket length and sleeve | Hem covers the seat. Sleeve ends 10-15 mm short of the shirt cuff |
| Barrel cuff | 60-70 mm tall. Closed girth = wrist + 25-40 mm. Overlap 20-25 mm. Needs a placket opening 120-150 mm |
| Sleeve cap ease | Shirt 0-3%, coat and jacket 3-6%, knit about 0 |
| Other seams | Within 1.5% unless designed to ease. Notches within 6 mm |
| Waistband | 30-40 mm finished. Closed = waist + 0-30 mm. Ends lap 25-40 mm |
| Rib neckband | 80-92% of the neckline's length |
| Hems | Shirttail 5-6 mm, straight 10-25, skirt and trouser blind hem 30-50, coat 40-50, knit 20-25 |
| Buttons | Shirt 10-12 mm, 70-110 mm apart. Coat 20-25 mm. The buttonhole side laps over |
| Notched lapel | A roll line, a facing, fronts interfaced but free to roll |
| Lapped vent | One CB extension (35-50 mm) laps the other, tacked at the top, never sewn full length |

**Settings that decide how it is worn and built.** Design-sheet keys go in `design`; garment keys in `spec`
(`design_garment(..., spec={...})`). Each line says what it fixed, so you know when to reach for it.

| Key | Where | What it does, and when |
|---|---|---|
| `tie` | garment / sheet | false (default): a shirt worn with only its collar button open; true: closed to the top |
| `closures` `[{"name", "state"}]` | garment | How an opening is worn: `{"name": "front", "state": "open"}` hangs a jacket open (buttons stay on); laid over the design's entry by name |
| `collar_spread` | garment | An open shirt collar's spread [out, down, from] deg (default [18, 14, 65]); false keeps it a ring |
| closure `finish`, `topstitch`, `hole`, `button` | closure entry | How the placket / faced edge, buttonholes and buttons look (Closures and bands, stage 6) |
| `block_options.leg` | sheet (trousers) | skinny, slim, tapered, straight, wide: the leg's cut from the leg's own girths |
| `block_options.length` | sheet (trousers) | `"break"` (suit trousers' default): 30 mm over the floor, back 12 mm longer, the hem resting on the shoe with one soft break. Not cut from the shoe's heights (that came out 5 cm short) |
| `block_options.hips_ease` | sheet (jackets) | Room over the hips; give a heavier man 0.14. Never get it from hem flare |
| `block_options.length_bonus` | sheet | Length added to the bodice (m). A jacket covers the seat (Garrett: 0.18) |
| `block_options.front_balance` | sheet | Tried, not adopted (it pulled the sleeves up). Leave 0 |
| `block_options` | sheet | Merge over the kind's own draft options key by key (a "replaces" report on 10-07 was the hem gate misreading) |
| `lapel` op `roll_radius`, `roll_strength` | sheet ops | The roll line's fold. 0.003 / 1.0 holds the lapel on the front (gap 9-11 mm, default 0.006 / 0.5: 12-15) |
| `lapel` op `gorge_drop`, `break_y`; `neckline` op `back` | sheet ops | Where the notch sits and how low the back neck is: how much shirt collar shows. `neckline` goes FIRST in the ops |
| `over` | garment | Worn over another garment: drafted over it, placed and simulated on it pressed. A shirt tucked into trousers = the TROUSERS `over` the shirt (only then does the belt show; worn free, the shirt hangs over the belt). The tuck has passed the coarse sim but not yet the fine settle: try `fine_settle: false` |
| `under_cap` | garment (outer) | How far the under garment's loose cloth may stand off the body (0.008; jackets over shirts 0.004) |
| `under_fall` | garment (outer) | How far over the pressed cloth the under garment's collar FALL lies under this garment (0.004 for jackets / coats, off otherwise; false = as simulated) |
| `pad_over` | garment (outer) | How far up a body normal the under garment still pads that vertex, x its own distance to the body (1.1 for jackets / coats: a standing collar pads the neck, not the shoulder under it; 1.5 otherwise) |
| `collar_ends` | garment | A notched collar past the neck's side: "made" (default: the whole collar held as laid) or "draped" (EXPERIMENTAL: solved with the lapel, resting as made; `{"back": m}` = from how far before the roll line meets the neck edge, default 0.07). Started open it stood up as flaps, started closed the solver died at frame 0-1 (non-PD blocks): not usable yet |
| `support` | garment | Pads on the body, not cloth: `[{"kind": "shoulder_pad", "thickness": 0.012}, "sleeve_head"]`. Without them a jacket's shoulders slope soft; pads add tension at the pit seams |
| `worn_top` | garment / kind | true for jackets and coats (the kind's default): fronts and backs built on the form |
| `press_lay` | garment | How far a pressed lapel starts off its front (0.003). 0.005 where an open shirt collar's points lie under the lapels |
| `worn_envelope` | garment | Smoothing rounds of the surface a worn top is laid on (0 = the padded body itself). 10 where the under garment's open collar makes steps (Garrett); 30 rode the jacket up (collar showing -5 mm) |
| `made`, `made_folds` | garment / sheet | Override made / draped per piece; `made_folds` held lapels and paid nothing (stage 3). Leave them off |
| `collide` | garment | Model parts the cloth rests on besides the body: `["shoes", "soles"]` so a trouser hem lands on the shoe |
| `interfaced` | garment | Whole pieces or bands: `{"piece": "front.L", "near": ["break", "lapelPoint"], "within": 0.1}` is a jacket's chest canvas |
| `zozo.stitch_stiffness` | garment | 1 default. 8 closes trouser / skirt seams that ZOZO leaves 3-15 mm open, at ~3x the time. It does NOT fix seams that start far apart (a jacket's pit seams got worse at 3) |
| `fine_settle` | garment | false skips the fine settle (a garment whose fine start fails the start check, e.g. trousers over a shirt) |

**Stale options.** `design_garment` merges the sheet key by key, so an option you set rounds ago is still there
(`block_options.darts: true` did nothing on a hip-length bodice, then made fish-eye darts under a princess line once
that code arrived). Read the sheet back in the reply; give `false`, null, or `replace=True` to clear.

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
  A made REGION of a draped piece: garment key `"made_folds": ["lapel"]` (fold names or prefixes) makes the flap past
  each such fold line made (method "settle"): a tailored lapel, pad-stitched to the canvas and pressed with its roll,
  is held as laid and carried with the made piece it is sewn to (the collar along the gorge: collar + lapel + gorge
  one pressed unit), while the rest of the front stays draped, joined along the roll line. On the suit jackets it did
  NOT pay: held from where they start, the flaps dragged the shoulder seams 13 cm open (before fronts were built on
  the form), and later the lapel gap only went 12-15 -> 10-13 mm with 8 new crossings at the gorge. Leave it off; the
  lapel's own roll (`lapel` op `roll_radius` 0.003, `roll_strength` 1.0) took the gap to 9-11 mm. Never mark a
  notched collar `"made": {"collar": "draped"}`: a stiff interfaced strip resting on the flat pattern bent round the
  neck is a fat roll.
- **Closures.** How each opening is fastened, as construction and not as a seam: garment / design-table key
  `closures`, one entry per closure:
  `{"name": "front", "kind": "buttons", "over": "front.L", "under": "front.R", "edge": {"over": "a>b", "under":
  "a>b"}, "band": {"over": 0.03, "under": 0.018}, "state": "closed"}`. `over` laps over `under` (the same piece for
  a cuff or a waistband). Fastenings are the marks `buttonhole<n>` on `over` paired with `button<n>` on `under`
  (other prefixes: `holes`, `buttons`; or `"at": [[over mark, under mark], ...]`). `band` + `edge` give the placket
  its own edge in the mesh and raise it by its extra layers; `state` is "closed", "open" or `{"open_above": mark}`
  (the top button undone) or `{"open_top": n}`. The entry makes the button stitches, the buttons as small geometry (also in the export
  and the Blender scene) and a line in the report per closure: fastenings closed, how far apart their two sides
  ended (closed is <= 6 mm). A `front_closure`, `cuff` or `fly` chosen on the sheet with no closure entry fails
  here; a closure that didn't hold fails stage 5. `kind: "zip"` takes `"seam": [arc, arc]` (sewn when closed).
  **How it is worn** is the closure's `state`, set on the garment without repeating the entry: a garment's
  `closures` entry of a name is laid over the design table's (or the draft's) key by key, so
  `"closures": [{"name": "collar", "state": "open"}]` is a shirt with its top button undone and
  `[{"name": "front", "state": "open"}]` a jacket hanging open (its buttons stay on the under front, no stitches;
  stage 3 lists it as "worn open", not as a missing closure). In a drafted garment the op
  `{"op": "buttons", "piece": "front", "n": 2, "state": "open", "size": 0.02}` writes the closure itself (left
  front over right, a fastening per mark; it used to write bare stitches).
  `{"open_top": n}` undoes the n highest fastenings whatever their marks are called. **A shirt is worn the way its
  kind is** (garment_kb.json `kinds.shirt.wear`): without a tie (garment / sheet key `"tie"`, default false) ONLY
  the collar button is undone. Every front button stays closed, the first high on the chest; the V comes from the
  collar spreading and the fronts above the first button rolling softly back. `"tie": true` closes the collar too.
  The garment's own `closures` entries still win. (Until 2026-10-08 the rule also undid the top front button: two
  buttons open, which the user called wrong. Simon's `extraTopButton` must stay false: an extra top button with
  nothing fastened to it draws as a hole on the open collar.)
  **An open collar is laid SPREAD** (garment key `collar_spread` [out deg, down deg, from deg], default [18, 14, 65],
  or false): the stand still hugs the back and sides of the neck, and from about the neck's side forward it swings out
  and tips down so the points lie on the collarbones. A made stand is carried as constructed, so an open collar laid
  as a ring stands up round the neck as a ring to the end of the sim. The stand's ends start ~10 cm apart at the throat
  (the wear rule's `gap` 0.10: at 7 cm the V read as a narrow slit).
- **Layers.** `"over": "<garment>"` wears this garment over another of the model (dress that one first). The one
  underneath is frozen and pressed to 8 mm off the body where it is loose (`under_cap`), and is what this garment
  is placed on and collides with. `"support": ["shoulder_pad", "sleeve_head"]` are pads on the body, not cloth.
  After the sim the report lists the tailoring tells against their targets: the under collar showing above this
  collar at centre back (10-20 mm), the under cuff past this sleeve (10-15 mm), lapels lying on the fronts, this
  collar hugging the one under it, and no crossings between the layers. The export leaves out what this garment
  hides of the one underneath.
  A garment worn over another is DRAFTED over it, as a tailor measures for a jacket over the shirt: its neck is the
  under garment's neckline (its collar size) plus the collar's thickness round, and its armhole is lowered by the
  under garment's thickness in the armpit (the draft log says "drafted over <garment>"). Drafted from the bare body,
  a jacket's collar was shorter than the shirt collar it goes round and climbed it (the shirt collar hidden), and
  its armhole sat 12 mm under the shirt's, so its underarm seams stood open over the shirt. Body girths (chest,
  waist, seat) stay the bare body's: give the design's ease for what goes under it. Proportions are still yours:
  the outer collar's stand at centre back is about the under collar's stand less what should show (10-15 mm), so a
  short neck with a 20 mm shirt band takes a ~24 mm jacket stand; the outer sleeve ends 10-15 mm short of the
  under cuff (a jacket sleeve near the wrist bone: `length_bonus` about -0.03 over a shirt that reaches the hand).
  **Don't lower the jacket's collar stand to show more shirt collar**: the lapel's roll line comes down from the
  stand, and with a lower stand the collar's turn pulls the lapels up; both lapels unrolled into a funnel round the
  neck (20 mm stand on the test body: 49 / 113 deg; 16 mm on Garrett: 33-41 deg; 24 / 19 mm rolled at 150-170 deg).
  Lower the jacket's back NECK instead, and set its notch lower: `{"op": "neckline", "widen": 0.012, "back": 0.035}`
  FIRST in the ops (it must come before the style lines), lapel `gorge_drop` ~0.12 and `break_y` ~0.46 (not yet
  simulated: judge it). The jacket collar should lie low and flat round the back of the neck outside the shirt
  collar, with the shirt collar showing above it at the back and sides.
- **Built on the form (jackets, coats).** A tailor builds a forepart on a form, not round a cylinder. Garments whose
  kind says so (garment_kb.json `kinds.<k>.worn_top`: jacket, coat; garment key `"worn_top"` overrides) start each
  front and back where it is WORN: below the armpit on the torso cylinder, above it laid up the body column by
  column (a front up the chest and over the shoulder) and hung so its top lands on the shoulder's ridge; the side
  panels hang with them. The shoulder and centre back seams are pinned shut, the collar is laid on that neckline
  and the neckline pinned to it, lapels are PRESSED onto the forepart (the flap's mirror image across the roll
  line), and the start relaxes with those pins held. On the cylinder a jacket's shoulder seams started 23-25 cm
  apart and its collar 13-25 cm from its neckline; the sewing could not close that with a made collar held, and the
  left lapel unrolled (99 deg) with its gorge crumpled. Built on the form: shoulder seams 2 mm, collar seam 4 mm,
  both lapels rolled (150-165 deg), every seam closed after the sim.
- **The tent (an open jacket's fronts bowing forward to the hem).** It was NOT the front balance and NOT the chest
  canvas (with the canvas taken out the left front stood 15 cm off the body at the hem instead of 13; the canvas keeps
  the two sides alike, keep it). It was the SIDE PANEL'S HEM SPRING: a `contour` letting each panel edge out 16 mm at
  the hem is 64 mm of flare a side, and an open front swings it forward. Cut the panel seams straight below the waist
  (`{"op": "contour", "edge": ["sideF", "sideB"], "at": [["waist", 0], ["hem", 0]]}`): the right front then hangs
  4 cm off the body at the hem (was 12) and front and back hems are level within ~1 cm. Room over the hips comes from
  the block (`block_options.hips_ease`, 0.14 on a heavier man), never from hem flare: without it the jacket was
  "TOO SMALL at hips", rode up 4 cm and burst its side seams. Read it on the sim: the hem's level all round and the
  open front's edge against a line dropped from the chest.
- **Front balance** (bodice block option `"front_balance"`, metres: the front's neck point and shoulder raised,
  easing to nothing at the chest line). Tailors lengthen the front over a forward chest. Tried at 20 mm: the hem came
  level but the raised front armhole pulled the sleeves up and bunched them (cuffs 24-40 mm short, sleeve seams 64 mm
  open). NOT adopted; leave it 0. If tried again, keep the armhole: raise only the neck point, gorge and centre front,
  or redraft the sleeve into the new armhole.
- Pressing the under garment harder (`under_cap` 0.004) keeps the outer one's girth for itself.
- **A piece laid from its seam.** Wrap `{"to": "seam"}` places a piece from the edge it is sewn to (a tailored
  collar's stand on the jacket's neckline, a collar on its stand), along the body, at the pattern's lengths; `"turn":
  {"at": m, "deg": 172, "gap": m}` lays its fall over. List the piece after the pieces it is sewn to. Use it where a
  ring round the neck (`"to": "neck"`) is wrong: a neckline that lies on the shoulders and runs down to a lapel.
  `"worn": true` lays it on the edge as that edge will lie WORN (each torso piece's point at its pattern x and height
  on the front / back of the body), not where the pieces start: a made piece is held where it is placed, and torso
  pieces start apart. `"turn": {"line": [[x, y], ...]}` turns it about a LINE in its own pattern instead of a
  constant distance from the edge. The draft op `collar` type `tailored` sets all of it after a `lapel`: a notched
  collar's roll line stands `stand_height` at centre back and comes down to the neck edge where the lapel's roll line
  crosses the neckline; past that point the whole collar lies turned, where the turned lapel will lie, sewn to the
  gorge (`"roll": "parallel"` keeps the old constant stand).
- **Made pieces sewn to each other are one construction** (a collar on its stand): they ride the body and are set
  on the fine mesh as one group, by the piece with the most seam to draped cloth. Nothing to declare.
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
- a band closed on itself that starts open;
- layer gaps at the start.

What a seam does in the sim is mostly decided here. A seam the solver must close from far apart closes badly or
not at all, and stiffer stitches don't help (they made a jacket's pit seams worse). Read the start's seam gaps
before simulating, and fix the start, not the solver:
- **Stretch is shear too.** A start whose edges are all within 5% of the pattern can be 9-12% stretched along the
  diagonal (a column leaning 0.1 against its rows is already ~5%). A strain-limited solver (ZOZO) can't start past its
  limit ("ccd failed" at frame 0, or "contact starts overlapping"); the start relaxation now brings every triangle
  near 3%, and the fine settle refuses a start over 1.6x before it reaches the GPU, naming pieces and places.
- **One cylinder for a fitted torso leaves the waist's arc in one seam.** Torso pieces start on one cylinder as wide
  as the garment's widest level; at a jacket's suppressed waist the arc left between front (from CF) and back (from
  CB) all falls into the side panel's back seam: it started 135-160 mm open and the side-back and underarm seams
  ended 67-110 mm open. Not fixed yet (a per-level start for jackets is the planned fix). Read the side-back seam's
  start gap on any fitted jacket.
- **Trouser legs start on the legs**, each leg's pieces on a tube round its own axis (side seams 15 mm, inseams 8 mm
  apart at the start, was 17-21 cm on one cylinder a leg); the hem is compressed over the foot and the shoe.
- **A padded body folds round hollows.** The body an outer garment is placed on is the body pushed out by the under
  garment; pushed further than a hollow is wide (the neck under an open collar, the armpit), it folded, and every
  clearance read the fold backwards: a gorge pushed 56 mm out across the shirt collar (4x stretch, ZOZO failing at
  frame 0), a sleeve start crossing the side panel in the pit and sent 11 cm down the arm. The pad is unfolded now;
  if a layered start shows a piece far off where it should be, suspect the pad.

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
- Seams: ZOZO's stitches are weak by default and leave draped seams a few mm open (a jacket: mean 4 / p95 18 mm;
  the clean-up welds what's within 1.5 triangles). `zozo.stitch_stiffness` 8 closes them to ~1-3 mm at ~3x the time
  (the suit trousers use it). A seam that STARTS far apart is a placement fault: stiffness can't fix it and made a
  jacket's pit seams worse (stage 4).
- A Garrett-sized jacket over a shirt at 2 cm: ~6-13 min on a rented 4090, ~30-50 min on this laptop.

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

#### Judging what you see

- **Surfaces in clay, or the exported GLB through `asset.preview`.** Textured EEVEE looks show pale grainy shards on
  cloth that the GLB doesn't have. A pale zigzag down a seam in a render you made yourself from raw arrays is the
  seam's two rows of vertices drawn unwelded; `look_cloth` welds closed seams.
- **An under garment is drawn pressed** in a look with the garment over it (what the outer one was simulated on).
  Drawn as its own sim, a shirt's sleeves showed through a jacket in white patches.
- **A render made before a merge or code change shows the old code.** The sim cache is keyed on the sim's own
  inputs and the solver's code: a change to placement or the pattern re-simulates, a change to the clean-up,
  report or maps applies at the next look of a cached sim. A sim made before a change of the cache key (a merge)
  needs a re-sim for new looks. Before comparing two renders, check both were made after the change you're judging.
- **Body measurements moved on 2026-10-06** (the down-the-body tapes are taut, the shoulder slope is the shoulder
  line's): every draft changed (armhole 6 cm higher, a jacket 7 cm shorter at CB). Results before then aren't
  comparable.
- **Colour.** A colour sampled from a concept painting's lit cloth reads too light under the look's lights: a shirt
  at #d0cbc7 rendered near white; the concept's lit shirt samples ~#a9a5a2. Go a shade darker (#bdb8b4).
- **`export_asset` / `garments(simulate=True)` start sims for garments that aren't cached.** Test exports on models
  whose sims are cached.

#### Clean-up (automatic, numbers in `cleanup`)

It does what the sculpt pass does first:
- Taubin smoothing removes the crinkle. 4 passes at 1 cm, scaled by the mesh size; `smooth`.
- No vertex moves more than `keep` (4 mm). Crinkle is a few mm deep, so a bigger move would be flattening a real fold.
- Interfaced pieces (collar, stand, cuffs, plackets) aren't smoothed: they don't crinkle, and smoothing their tight
  folds crumpled them.
- Seams the simulation closed are welded.
- Seams are PRESSED (`press`, default on): the cloth within 3 cm of each welded seam is smoothed across it, as a
  tailor's iron leaves it. A solver's stitch passes no bending, so each side tilts on its own and the seam stands as
  a crease. Interfaced cloth and seams with the finish "welt" are left alone.
- Anything pulled toward the body is pushed back out to `clear`.

Every look, the scene and the export wind each piece to face out (`piece_flips`) and give a seam's two sides one
shared normal. Pattern pieces come out wound either way, and half the blazer's pieces faced in.

`cleanup: false` shows the raw simulation.

#### Detail: seams, stitching, hems, buttons

These are drawn from the pattern itself into maps on the flat-pattern atlas (`detail`):
- every seam by its FINISH (`seam_finish` for the garment, `seam_finishes` {seam index | "pieceA/pieceB" | piece:
  finish} for single seams; the default is the kind's, garment_kb.json `seam_finishes`): `pressed_open` (tailored
  jackets, coats, trousers, skirts: a 0.3 mm groove about 1 mm wide, a faint rise over the allowances either side,
  no stitching), `pressed_to_side` (knits, blouses), `topstitched` (one row 6 mm out), `edgestitched`, `felled`
  (shirts: two rows on one side), `welt` (a seam made to stand: piping, cording; not pressed). `seam`, `seam_width`
  and `allowance` override every finish's numbers;
- a dashed topstitch `topstitch` m in from free edges (hems, a collar's edge). The default comes from the kind's hem:
  none on blind-stitched hems (jackets, coats, suit trousers, skirts), 6 mm otherwise;
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

#### Closures and bands (what holds a garment shut)

- A closed lap is CONSTRUCTED closed. A contact solver holds two layers its contact gap apart (3-5 mm at 1-2 cm
  triangles), so a buttoned placket comes out of the sim standing off the shirt. After the clean-up the over band of
  every closed `closures` entry is laid 1.2 mm off the under piece between its first and last closed fastening, and
  each fastening's two sides are brought together (up to 12 mm; further apart is the sim's failure and is reported).
  The report says what moved ("lap front laid closed after the sim: ...") and what the sim itself left
  (`closures_sim`). Above an open collar and below the last button the fronts part, as worn. `cleanup.seat: false`
  shows the raw sim.
- A band buttoned to itself (waistband, cuff, collar stand) is a MADE piece: the sim holds it as placed, so it must
  START closed. Stage 4 fails "<band> starts with its fastening N mm open" on any band that doesn't (every
  placement path). The band is then smaller than the body where it sits plus its clearance: 2.5 mm round the torso
  (a waistband grips), 4 mm on a wrist or neck. Give it more ease (2-3% at the waist is enough now), or seat it
  where the body is smaller. A wrap `out` on a self-closed torso band is ignored: 4 mm out is 25 mm of girth.
- A buttoned shirt collar is CONSTRUCTED closed: the stand is laid at its buttoned girth 1.2 mm off the neck and held
  free of body contact, so it needs no solver standoff. What it needs is the right size: about 13 mm over the neck's
  BASE, where the stand sits (Simon `collarEase` 0.115 over the tape's neck, which is taken at the narrowest; at 0.03
  it started 30 mm open, at 0.07 17 mm). (Before 2026-10-06 the advice was to leave a short neck's collar open: that
  was the solver's standoff, now gone.)
- **Collar proportions come from the wearer's neck** (design tables with `"collar_rule": "simon"`, Simon's has it;
  garment_kb `kinds.shirt.collar`): stand = the neck's height (trapezius to jaw) less a finger's room (13 mm), within
  20-35 mm; fall at CB = stand + 12 mm (covers the stand's seam); points 70 mm. A 30 mm stand on a 35 mm neck was
  pushed 7 mm off the chin and its fall would not turn (stood up 15 deg); 20 mm turned it 155 deg. The garment's own
  pattern options still win.
- **The placket must show, in geometry AND maps, and its look depends on the closure's finish** (closure keys
  `finish` {"over", "under"}: `box` (a shirt's buttonhole side: three layers proud, a crisp fold at the inner edge,
  the tuck's shadow, two rows `topstitch` 3 mm in), `french` (a shirt's button side: a rounded folded edge, no rows),
  `facing` (a faced edge, one row), `plain` (nothing); default by the garment's kind (`kinds.<k>.closure`: shirt box over french, jacket and coat facing with holes across and no topstitching unless asked), else box over french. `hole`: auto | along | across (auto:
  vertical down a placket, along a cuff); `button` {holes 4|2, color, roughness, thickness}). The pattern alone was
  right and the shirt still read as plain cloth: the band was a 0.8 mm lift over one 1 cm triangle (invisible in
  clay), the front edge was drawn as a hem, buttonholes as outlined slots, buttons as rivets. **A jacket or coat front
  is not a box placket**: its edge is faced and its buttonholes run ACROSS (horizontal); give its closure
  the jacket and coat kinds default to `"finish": "facing"` and `"hole": "across"`. These keys are look only: in the design table they
  don't re-simulate; in a garment's own `closures` entry they change the sim key (re-sim).

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
| A skirt slides down or one side seam gapes | Lower-body pieces start on a cylinder much wider than the waist and the sewing has to close 10+ cm; the body has no hip to hold a waistband | Keep the fit close (straight / a_line), waist ease 2-3%; the band now starts closed at the waist (a waist-SHAPED start for the panels was tried and dropped: 10-30% shear); `zozo.stitch_stiffness` 8 closes the seams |
| Every seam a raised welt with a valley beside it, visible across the room ("huge and structural") | Real seams are pressed and barely show. Three causes of ours: (1) pieces wound opposite ways, so welded normals cancelled and Solidify stepped; (2) the solver's free hinge left a 20-45 deg crease at each seam, where the cloth's own neighbouring normals differ by 10; (3) the maps drew a 1.2 mm groove 5 mm wide between 0.6 mm ridges, 45% darker, with topstitching on every seam and hem | Fixed by `piece_flips` with shared normals, the clean-up's `press` and seam finishes. Measure before you tune: the angle between a seam's two sides' normals against the cloth's own, per seam (blazer 29 -> 14 deg, side seams 20 -> 9). A seam that should stand gets `seam_finishes` "welt" |
| The placket band invisible in clay and at outfit distance | The solver's lap sank 3-4 mm between the band's edges (deeper than any step), and the step was spread over a 1 cm triangle | After the sim `closures.split_band_edges` cuts a vertex row 1.5 mm outside a box band's inner fold (vertices appended: ids hold), `press_band` lays the band flat across, `relief` lifts it 1.2 mm: a step 1.5 mm wide (`cleanup.band_edges` false turns it off) |
| `ccd failed` at frame 0, or the fine settle refuses its start, with a triangle 3-4x stretched next to a placket | A roll fold's line ends just past the band's inner row and crosses it at a shallow angle: a sliver | End the roll a few cm above the fastening (the over front's 2 cm above button 1, the under front's 6 cm) |
| `dress` says NOT simulated | Stages 1-3 fail | Read the failures, fix the sheet or the pattern; `force=True` only to look at the fault |
| An open jacket's fronts bow forward to the hem (a tent from the side) | The side panel's hem spring (`contour` +16 mm per edge at the hem = 64 mm of flare a side), not the canvas, not front balance | Panel seams straight below the waist (`contour` [["waist", 0], ["hem", 0]]); hip room from `hips_ease` |
| Both lapels unroll into a funnel round the neck | The collar stand was lowered (to show more shirt collar): the roll line comes down from it and the collar's turn pulls the lapels up | Keep the stand (shirt stand + a few mm); lower the back neck (`neckline` op first) and the notch (`gorge_drop`, `break_y`) |
| Lapels stand off the front (gap over 10 mm) | The roll line's fold is soft | `lapel` op `roll_radius` 0.003, `roll_strength` 1.0. Not `made_folds` (no gain, crossings at the gorge) |
| A notched collar is a fat roll round the neck | The collar marked draped: a stiff strip resting on the flat pattern, bent round the neck | Leave the collar made (the default) |
| The jacket collar hides the shirt collar; the jacket's armhole / underarm seams stand open over the shirt | The jacket drafted from the bare body: its neck shorter than the shirt collar it goes round, its armhole under the shirt's | `over: "shirt"` drafts it over the shirt (automatic with `over`). Check the draft log says "drafted over shirt" |
| A jacket hangs 2-5 cm high: shirt collar hidden, cuffs too short, side seams open | Something held its top up: a back built up the nape over the shirt collar, the worn surface smoothed over the neck's hollows (`worn_envelope` too high), too little hip room | The back stops at the under garment's neckline (automatic); `worn_envelope` 0-10; `hips_ease` |
| Seams round the armpit (side-back, underarm) end 40-110 mm open | They START 75-160 mm open: one start cylinder at the garment's widest level leaves the suppressed waist's arc in one seam; pads add tension | Not fixed yet (a per-level start). Stitch stiffness makes it worse. Read the start gaps (stage 4) |
| A layered start: a piece pushed far out, a sleeve started 11 cm down the arm, ZOZO "ccd failed" at frame 0 | The padded body folded in a hollow (the neck under an open collar, the pit) and clearances read it backwards | Unfolded automatically now; if it recurs, the pad (`under_cap`, the under garment's collar) |
| A jacket's collar stands as wings 4-6 cm over the shoulders beside the neck, a thick roll behind | The shirt under it: its open stand stood 2 cm off the neck and its fall floated 15-20 mm over the shoulder; the body the jacket is built on was padded as high as that collar for 4-5 cm out along the shoulder (a point 3 cm up a shoulder vertex's normal padded it), the forepart's neck point was laid on top and the made collar bridged outward | A stand that hugs the neck (the shirt's job: ~10 mm off the skin). Under a worn top the shirt's fall is pressed onto the shoulder (`under_fall`) and a standing collar pads only the body it stands against (`pad_over` 1.1). Measure the ridge beside the neck: jacket's lowest cloth over what is under it should be 5-12 mm, not 30-50 |
| A notched collar's ends crumple or stand off where they meet the lapels | The whole collar was held as laid while the fronts it is sewn to settled 14 mm (10 out, 4-8 down) | Not solved. `collar_ends` "draped" (only the band behind the neck's side held) gave the best front (lapel gap 5.7 / 7.0, the notch reads) but flaps behind the neck when started open, and a solver failure when started closed; the default stays "made" |
| White flecks of shirt through a jacket's sleeves / armholes | The clean-up moved jacket cloth through the shirt under it | Fixed: crossings with the under garment send those vertices back to the sim's surface |
| A shirt worn without a tie shows two buttons open | The old wear rule also undid the top front button | Only the collar button opens now (`tie` false); Simon's `extraTopButton` stays false (a stray top button draws as a hole) |
| The top front button of an open-collared shirt ends 2 cm open, a slit of skin beside the band | The stand is made (it ends as it starts) and its centre-front points started further apart than the fronts can follow: a front's neck corner lies ~3 cm from its roll line, so the two corners part by at most ~5.3 cm x (1 - cos roll), 7-8 cm at a soft roll; gap 0.10 + spread 25 deg started them 167 mm apart. And the fronts started on the torso cylinder 10 cm from the stand | The wear rule's numbers must be consistent: collar `gap` 0.008 (the stand hugs the neck), spread 18 / 14 / 65 (centre-front points ~80 mm apart); the kind's `worn_top`: the fronts' tops start ON the body with their neck seam pinned to the stand. Button 1: 19 -> 3 mm |
| An open collar stands 2 cm off the nape and the neck's sides; a jacket's collar rides up over it as a shelf | The stand was laid round the neck at its length + `gap`: every cm of gap is 1.6 mm of radius | An open stand still hugs the neck; only its fronts part: small `gap`, the opening from `collar_spread` (which turns each half by its PATTERN side: ends lapping past the centre front were swung with the wrong side and crossed) |
| A shirt under a jacket shows as a crumpled white surface with no placket and no buttons | The under garment was drawn as the PRESSED collider (what the jacket was simulated over), which has no relief, buttons or band | `cloth.worn_together` (looks, scene sync, export, the reference figure all go through it): the under garment's finished surface, only the cloth the outer garment covers laid 4 mm under its inner face (`cloth_layers.tucked`), buttons made again, covered ones left out. Scratch scripts must call it too, not draw `under_V` |
| A jacket's buttons are small white shirt buttons | The closure's button defaults were the shirt's for every garment | Kind defaults: `kinds.jacket.closure` size 20 mm, `button.tone` 0.55 x the cloth's colour, roughness 0.6 (`cloth.button_color`: one colour path) |
| A worn top on the bare body: 'contact starts overlapping' at frame 0 | Body.clearance over-reads; a worn back's edge started 1.5 mm off a shoulder blade | place() ends a worn start with `_clear_exact` against the body's triangles |
| An open shirt collar stands up round the neck like a ring | A made stand is carried as constructed: laid ring-like, it stays a ring | `collar_spread` (default [18, 14, 65]): the front swings out and down onto the collarbones. More (40 / 20) drags the fronts' top corners apart: button 1 ended 36 mm open; a narrower collar gap (6 cm) made the fronts gape between buttons 1 and 2 |
| A second, undone-looking button beside a closed one | The solver left that fastening's two sides 1-2 cm apart and the maps drew the under front's button, which peeked out beside the real one | The maps draw no button under a closed lap (`closures.covered_buttons`); the report still says `!! closure ... sides N mm apart` |
| A cached build or a look killed for memory (exit 137) with one huge start triangle | `_piece_crossings` searched every edge against every triangle at the largest triangle's radius | Fixed (per-size search, chunked); a start with a huge triangle is still worth reading (st.py-style: worst start triangles) |
| A shirt's placket doesn't show (plain cloth with dots for buttons) | The band was a 0.8 mm lift on one 1 cm triangle; maps drew a hem, outlined slots, rivet buttons | Closure `finish` (box over, french under for shirts): band edge in the mesh, rows, buttonholes, flat 4-hole buttons. A jacket front is `facing` with holes `across` |
| A shirt collar's fall stands up (won't turn) | The stand is taller than the neck between trapezius and jaw, so it is pushed off the chin | `collar_rule` sizes it from the neck (stand = neck height - 13 mm, >= 20 mm); or Simon `collarStandWidth` 0.055 (20 mm) |
| A buttoned collar starts 17-30 mm open | Too little collar ease at the neck's base | Simon `collarEase` 0.115 (13 mm over the neck base) |
| STRAINED at the waist on a shirt with plenty of ease | The placket's fold rows (squashed across, stretched along), not the fit | Fold rows are left out of the fit now. Read where the strain is before adding ease |
| Shirt fronts stand 3-5 mm proud of each other down the placket | The solver holds two layers its contact gap apart | Laid closed after the sim (automatic, report "lap ... laid closed") |
| Suit trousers read as pyjamas | No crease, a wide cropped leg, no fly | `kind: "suit_trousers"` (crease, slim leg, fly, waistband, darts, belt) |
| Trouser hem 5 cm short, or the ankle showing, or puddled on the foot | Length cut from the shoe's heights, or the shoe isn't a collider | `length: "break"` (30 mm over the floor, back 12 mm longer) + `collide: ["shoes", "soles"]` |
| Back darts read as open tucks | Straight dart legs end in a poke | `dart_taper` 0.6 (the suit_trousers default) |
| No belt shows on trousers with belt loops | The shirt hangs free over the waistband | Tuck it: the trousers `over: "shirt"` |
| A skirt or trousers' waistband open at CB, a V down the back | The made band started open on a cylinder at the hips and was held so | Fixed: self-closed bands start closed at their closed girth on the narrowest level; stage 4 fails a band that doesn't. Give 2-3% waist ease |
| A jacket front reads open "0 stitches" in stage 2 | A front worn open has its buttons as a closure with no stitches | Fixed (closures' fastenings count); state "open" is fine |
| A sleeve sewn in rotated (the top notch 27 mm off the shoulder seam) | The armhole's seam chain started at the front pitch, not the shoulder | Start an armhole chain where the sleeve's top meets the shoulder seam |
| ZOZO "ccd failed", max_sigma ~11 at frame 0 | A sliver edge (under 1 mm) in the mesh: a fold row or a mark next to the outline | Fixed in the mesher; the fine start check names the place if one comes back |
| An open jacket hangs CLOSED and stands 5-12 cm forward of the body below the chest (a tent) | (1) It was started lapped like a buttoned one: the fronts stay lapped, the sides hug the hips and all the ease stands in front. (2) A stiff front (canvas bands + a lapel roll at strength 1) is a board that carries the upper chest's slope down to the break | A front closure worn `open` starts the fronts apart (`open_gap`, default 0.16 m at the hem: the loose tube an open jacket is). Keep the roll soft (`roll_strength` ~0.3) and the canvas light; read `section.py`-style numbers: where the two front edges are, and the stand-off by height |
| A layered job stops at frame 0: "contact starts overlapping" / "newton stalled ... a prescribed pin driven into geometry that cannot yield" | The start is laid on the PADDED body, but the collider is the body + the under garment's own mesh: a pressed sleeve fold, a placket ridge under a 2 cm triangle's middle, an open collar's wing under a made (held) jacket collar | Fixed: the start is cleared against the collider's triangles both ways (3 mm), made pieces are lifted over the garment under them. If it comes back: look at the job's in.npz against its frame-0 collider (`bodyV0`), not the bent body |
| Trousers over a shirt fail before the sim ("the fine settle's start is stretched ... back 3.9x at the waist corner") or the band sits under the shirt tail | The waist was taped on the bare body, and the start was cleared against the shirt read as a closed body | Fixed: a garment hung from the waist (`over`) is drafted from the waist taped over the tucked garment + the layer gap; give the trousers `under_cap` ~0.003 (the shirt pressed close) |
| ZOZO builder: assertion `left > right` 0.0 / 0.0 while "computing constraints" | A collider vertex whose faces have no area (an under garment's welded seam slivers), or none at all | Fixed in the collider (faces under 0.0005 mm2 and the vertices they orphan are left out) |
| Trousers read high-waisted; the belt sits far above the concept's | The block puts its top at the NATURAL waist | Block option `waist_drop` (m under the waist; men's tailored trousers 0.04-0.08): girth there, rise, lengths and placement follow |
| On another body the same jacket's sleeves start 3-6 cm down the arm, seams 10-12 cm open, and the sim stalls in the first frames | The armhole is too high for that body's shoulder line (hps lower: armhole depth from hps 263 mm where 294 worked): the under sleeve crosses back / side panel at the pit and is sent down the arm round after round | A jacket's armhole sits ~3 cm under the pit: bodice option `armhole_depth` 0.12-0.14 (default 0.02 is a shirt's); check `sleeve_down` <= 0.02 and armhole start gaps ~9 cm at the start |
| A build eats 12+ GB before any sim | A broken start (one triangle 10-30 cm across) searched for crossings with one radius | Fixed: such a start raises "the start is broken: a triangle of <piece> is X m across" |
| An open jacket's fronts hang together below the button where the reference's hang 12-15 cm apart | The pose: the reference's arms are raised further (45 deg vs 25): raised arms lift the sleeves and pull the fronts round to the sides | Judge against a reference in ITS pose (turn the arm joints about the shoulder on a copy of the model and dress that): same jacket, arms 25 -> 45 deg: front edges 2 -> 12 cm apart at the hips. Sleeve length and cuff show are read in that pose too |

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
| `crease` | A pressed crease down a piece's `crease` line (a trouser leg's grain line), front and back: a press fold standing out (`angle` 205, `strength` 0.6) | The pattern (a fold line only) |
| `fly` | The centre front seam from the waist down `length` (0.18) becomes an opening closed by a zip (a closure, left over right; `state` "open" leaves it unsewn); its J of topstitching is a `fly_stitch` line drawn in the detail maps | The seam below it |
| `waistband` | A straight band generated from the waist edges at unfold; `opening: "front"` opens it over a fly (left end over, the right end's `overlap` runs on under it with the button), default at the centre back | Band length = the waist edges |
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

## Construction audit and knowledge base

`cloth_audit.md` is the audit behind the numbers above. `garment_kb.json` is the knowledge base the sheet and checks
read (`garment_reference`): add a kind, a detail choice or a draft source there, with its evidence checks, and the
workflow covers it. `cloth_check.report(Bp, kind)` is the bare seam-table check. Lessons live in three places
there: per kind (`garment_reference(kind="jacket")` -> `lessons`: read them before designing that kind), per
detail choice, and the general list at the end. Add every new lesson to the narrowest of those and to the table
"What goes wrong, and the fix" above.
