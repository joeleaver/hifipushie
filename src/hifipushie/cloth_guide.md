# Clothes: read, design, draft, fit on the form, style as worn

Garments here are made the way garment makers make them: decided on a design sheet, drafted to the body's
measurements, checked FLAT (the pattern gate), assembled on the dress form and judged there, and only then, optionally,
simulated as a wrinkle source. Nothing is sculpted as a shell and nothing is warped from one body onto another. A
tablecloth or a blanket is the same machinery: one flat piece draped on a prop.

**The order (2026-10-19; the tools enforce it and their texts end with the next step):**
pattern (`design_garment`, `look_pattern`, `alter_pattern`) -> `pattern_check` (the flat gate: every sim refuses
without its PASS) -> `fit_garment` (the pattern assembled on the form, no sim) -> judge clay + diag beside the
reference, ONE view per `review_view` call -> styled as worn (fit_garment's wear ops / `style_garment`) -> optional
sim (`dress`), a wrinkle source only -> game mesh (garment_game). Closing seams, building made pieces or hand-finishing AFTER a sim is not a step: measured on Garrett's
jacket 2026-10-19 it pushed face strain p99 from 4.7 % to 66-74 %. A fault is fixed on the pattern and re-checked.

**Measure first (Joe 2026-10-20: "we need to be better at measuring up front"):** before any draft, every body
measurement the draft consumes must arrive in THAT draft's definition (measure_defs; the gate row
`measure_definitions` FAILs a draft with an undeclared measurement; table and sources: docs/notes/measurements.md).
Read the drafted pattern against the body flat before fitting: shoulder seam vs the body's neck point -> shoulder
point (length and drop), neckline vs the neck base + ease, hip line height, plumb girth. Most lost rounds on Garrett's
jacket and shirt were definition mismatches (shoulder slope, hip level, neck point) found late by fitting.
Under garments are fitted first and judged where they show. An open front or open collar is a worn state reached by
STYLING the muslin fit (pull until it would stretch, smooth, pull down), not by a release sim or an arrangement.

**The fit and styling rules (2026-10-25; ledger docs/notes/codified.md):**
- The MUSLIN fit is the fit (C162): woven cloth, threads held, the bias shears up to the weave's jam, a soft neck pin
  (C166, C167). Misfit reads as thread strain by region; cloth never stretches to reach a landmark.
- SUPPORTS, NOT HOLDS (C190): hold only what physically carries the garment (shoulder / neck contact, sewn seams,
  fastened closures, the layer under), soft and named. Holds standing in for gravity made pinches, narrow hems, a
  side seam standing like a cord and rigid-grip creases.
- THREADS FIRST, THEN BENDING (C195): stiffness never buys shape with stretch. Collars and canvassed fronts hold their
  shape by drafted canvas / interfacing (C196); if two goods trade off, the model is wrong.
- Styling (C142, C174, C199): pull until a thread would stretch; a hand lets go after its move and what hangs free
  drops; every styling ends with smooth + pull down.
- Judge beside the REFERENCE only: your current or approved garments are never the baseline (C165). Verdict: overall
  standing first, then faults ranked.

**The two rules everything else follows:**
1. **Describe the garment from the reference before choosing anything.** Kind, construction, fabric, measurements
   against the body, how it is worn. Every template, kind and default you pick must be justified by that
   description. Starting from the nearest template and fixing faults one at a time gives a clean garment that is
   the wrong garment (a sweatshirt block with torso-deep armholes where the reference is a fitted knit crewneck).
2. **Construction before solver.** A fault in the cloth is a pattern, sewing or made-piece fault until shown
   otherwise. Measure the DRAFT against the description before any simulation; never tune solver settings
   (stiffness, mesh size, contact) to hide a pattern fault. `dress` refuses to simulate while stages 1-3 fail.
3. **Validate the pattern before any sim; judge on the form.** `pattern_check` measures the flat pattern and writes
   the record every sim needs; `fit_garment` shows the garment assembled from that pattern on the body (clay + diag:
   panels, seams, turned flaps, strain, layer pierce) with its strain p99 (gate <= 6 %). Fit, silhouette and
   construction are judged there, beside the reference. A sim is optional and only adds wrinkles; it never fixes a
   pattern, and nothing is closed, rebuilt or sculpted on the drape afterwards (strain p99 4.7 % -> 66-74 % that way).
   Fine detail (rib, stitching, small creases) goes in the normal map.

Run the tools with `call_tool(name, args)`. Traps (symptom -> real cause): guide(topic="traps"); tailoring
principles: guide(topic="tailoring"). Sub-topics (guide(topic=...)): `cloth_reference` (reading a
reference item by item), `cloth_design` (design-sheet keys, tailoring numbers, knits, jeans, wear rules),
`cloth_construction` (folds, interfacing, closures, layers, the start), `cloth_sim` (solvers, where sims run,
reports, clean-up, detail maps, states, export), `cloth_faults` (what goes wrong and the fix), `cloth_blocks`
(designing a garment with no ready-made draft: blocks + operations), `cloth_background` (how makers work, sources,
worked examples), `cloth_tools` (every cloth tool's parameters).

## The stages

| # | Stage | What a maker does | Tool | Gate before going on |
|---|---|---|---|---|
| 0 | Read | Describes the garment from the reference | `garment_from_reference` (or by hand) | The description below, written, with values |
| 1 | Design sheet | Decides kind, fabric, fit and every detail before cutting | `design_garment` (`garment_reference` for choices) | Every choice traced to a description item; no hard failures |
| 2 | Pattern | Drafts to the body, walks seams, trues corners, measures against the body | `look_pattern`, `alter_pattern` | Seams walk, ease and evidence pass; the draft's measurements match the description |
| 3 | Pattern gate (flat) | Checks the pattern against the checklist before cutting cloth | `pattern_check` | PASS (FAIL / UNMEASURED rows block every sim) |
| 4 | Construction + placement | Plans sewing order, layers, folds, interfacing; places the pieces round the body | `check_garment(stages=["construction", "place"])` | Passes |
| 5 | Muslin fit on the form | Fits the muslin on the dress form (threads held, bias shears, soft neck pin; an open front with its break open) and judges it | `fit_garment` | Strain p99 <= 6 %, no layer pierce; clay + diag judged beside the reference, one `review_view` per view, no MAJOR |
| 5b | Style it as worn | fit_garment already sets it as its kind is worn (a shirt without a tie: the wear's style ops open the collar, C146); otherwise pull a collar open, a shirt down, a cuff up, then smooth ripples, each as far as the cloth goes without stretching (never pins at a guessed spot); each hand lets go after its move, what hangs free drops, and every styling ends with smooth + pull down. Hold only real supports. Handles are turning areas; holds feathered and per piece; long edges smoothed toward one curve; measured beside the reference every look | `fit_garment` (default) / `style_garment` | The open collar reads PASS (item / target / ours); pulls stopped by stretch (not max_move); tips as clean as the fit's; judged like the fit |
| 6 | Optional sim | Only a wrinkle source over a fit already judged | `dress`, `look_cloth` (clay + diag by default) | Fit unchanged from the form; never closed, rebuilt or hand-finished after |
| 7 | Game mesh | Remeshes in pattern space, bakes the detail | garment_game, `export_asset` | judge_asset self-checks pass; reviewed one view per call |

`check_garment(name, garment)` with no stages runs 1-4 (and "sim" after a dress) in order, failures first. A model
needs a `base` body first (the draft is measured off it); a drape over a prop needs none.

## Stage 0: describe the garment (before any template or default)

Write this down per garment, as items with a value, how you'll measure it on yours, and a tolerance. Mark each item
read / measured / inferred (not visible in the reference: say so, don't guess). `garment_from_reference` gives you
the item list as a form and turns your answers into a design-sheet patch and a target table
(guide(topic="cloth_reference")); if you work by hand, cover the same ground:

1. **Type and construction.** Woven or KNIT. Garment kind in words (crewneck sweater, dress shirt, two-button
   notched jacket, five-pocket jeans). Sleeve type (set-in, raglan, drop shoulder, kimono). Neckline and collar
   (crew rib band, shirt collar on a stand, notched lapel, hood). Closures (none / pullover, buttons, zip, fly).
   Bands, cuffs and hem finish (rib, barrel cuff, turned hem). Pockets.
2. **Fabric.** Fibre and weight (shirting, denim, wool suiting, jersey, rib knit, french terry); surface (knit gauge,
   twill, sheen); how it drapes (crisp, soft, heavy). Colour, sampled a shade darker than the lit concept.
3. **Measurements against the body**, read from the reference with body landmarks as the ruler:
   - lengths: hem (HPS to hem, or where the hem sits: mid hip, below the seat), sleeve end (wrist bone, knuckles);
   - **armhole depth: how far the underarm seam sits below the ARMPIT** (a fitted knit or shirt 2-4 cm, a jacket
     about 3 cm, a drop-shoulder or sweatshirt much more). Read it from the folds and seam at the underarm;
   - shoulder seam: at the shoulder point, or dropped onto the arm;
   - ease: close, a hand's room, loose, at chest / waist / hip; does it hang straight or follow the waist;
   - band and cuff heights, collar stand and points, lapel width, pocket placement.
4. **How it is worn.** Open or closed, which buttons are done up, tucked or not, layered over what, collar open,
   sleeves pushed up, the pose's effect (raised arms pull fronts apart).
5. **Folds the reference shows.** Where (elbows, knees, the hem stack, under the bust), how many, how sharp.
6. **Surface details that make it read.** Rib, topstitching (and its colour), plackets, buttons, rivets, seams.
   Note any the tools can't build yet (see "Known gaps") so they're decided, not forgotten.

Then pick the kind, draft source or block, fit, fabric and details, and say which item justifies each. Kinds,
details and fabrics: guide(topic="cloth_design"), `garment_reference(kind=...)` (read the kind's `lessons` before
designing it).

**Knit tops and the kind `hoodie`.** There is no "sweater" kind. `hoodie` is the knowledge base's generic
PULLOVER-KNIT kind (the name is a historical accident): its defaults are a hooded sweatshirt's (french_terry, a
loose `regular` / `boxy` fit of 10-35% ease, hood, kangaroo pocket, topstitched seams, and in its derivation a
dropped shoulder with the sleeve in a DEEPER armhole). A fitted crewneck sweater uses this kind but overrides almost
all of that from the description:
- `"block": "knit"` with a set-in `{"op": "sleeve"}` (no dropped-shoulder reshape), shoulder seam at the shoulder point;
- details collar `rib_neckband` (a crew neckline at the neck's base), cuff `rib`, hem `rib_band`, pockets `none`;
- the fit and ease you read (a fitted knit 0-10%), fabric `jersey`, garment key `worn_top: true`;
- **armhole depth: the target is the underarm 2-4 cm below the armpit. Don't trust the kind's default: measure the
  draft's armhole bottom against the body's armpit on the pattern sheet (stage 2) and fix it before any sim.**
- band heights read from the reference (a crew neckband is usually 2-3 cm, cuffs and hem 5-7 cm), hem where the
  reference puts it.
A sweatshirt (drop shoulder, deep armhole, boxy, french terry) is a different garment: the description decides which.

## Stage 2: measure the draft against the description

`look_pattern` checks that the draft is internally right (seams walk, notches meet, every choice evidenced, ease in
the fit's band). That is necessary, not sufficient: a sweatshirt pattern passes all of it. Also measure what the
description named, on the pattern sheet (10 cm bar, piece sizes, the `dimensions:` and `draft:` lines) against the
body:
- armhole depth (the armhole's lowest point below the HPS) against the body's HPS-to-armpit; block option
  `armhole_depth` (a share of waist-to-armpit) lowers it: 0.12-0.14 is ~3 cm on a jacket;
- body length from the HPS at CB; sleeve length; band, cuff and collar heights; ease per girth;
- the neckline: a crewneck sits at the neck's base, not scooped.
Print a table: item | reference | draft | pass. Fix the biggest miss in the design sheet, then look again. Don't
dress a garment whose draft misses its description.

## Craft rules (each once; the reasons and numbers are in the sub-topics)

Pattern and construction
- WRAPPED FOLDS ARE DRAPED (Joe 2026-10-21, C130): a collar (stand + fall), cuff, waistband, turtleneck or curved hem is
  described WORN in the garment key "drape": [{"name", "along": [the edges it is sewn to, CB in the middle], "state":
  "closed", "layers": [{"piece": "stand", "kind": "stand", "height": m or {"cb", "end"}, "ext": m past CF},
  {"piece": "collar", "kind": "fall", "rise": m above the stand, "land": m below the neck seam on the layer under it,
  "end_in": m short of CF, "point": m}], "source"}]; drape.draft builds it on the dress form's cloth, flattens it and
  writes "out" (the pieces replace the design's, same names). Never hand-edit "out": change the worn spec and draft
  again (gate row drape_band_current refuses a stale piece; drape_band_flat: flattening strain p99 <= 2 %). Drape ONE
  state (closed); the other (open) is the styling target, checked with drape.reach. Round 1: the op and KATs work;
  Garrett's stand still flares (docs/state/drape_band.md), so the drafted pieces are not yet a passing collar.
- Fix FIT and construction in the pattern (ease, length, truing, a walked seam, a detail's options), never by
  sculpting, never by solver settings, never by a pass on the drape after a sim.
- Made pieces (collars, stands, cuffs, waistbands, plackets, lapels) are drafted and walked against the edge they're
  sewn to (`alter_pattern` "match"), laid at their CUT length and width, and judged on the form (`fit_garment`, diag
  "turned" shows a flap on the wrong side).
- Different fabrics bend differently. One fabric on every garment reads generic; knits drape soft and rounded.
- A garment worn over another is drafted over it (`over`): its neck and armhole follow the under garment.
- A self-closed band (waistband, cuff, buttoned stand) must START closed; give it 2-3% ease.
- Room over the hips comes from the block (`hips_ease`), never from hem flare.
- Stale options persist: `design_garment` merges key by key. Read the resolved sheet back every time; clear with
  `false`, null or `replace=True`.

Simulation (optional: a wrinkle source at most, over a fit + styling already judged; never a fitting, release or
opening step)
- One simulation at a time; one change per sim. Know the noise (about 2 mm): only a difference over about 5 mm is
  the change. Read each build's numbers from its own report.
- Draft (2 cm) judges fit and big shape only; details are judged at final.
- A sim that crawls (seconds a frame where similar garments ran fast) is a fault in its start: cancel it, read the
  place stage, don't resubmit unchanged.
- One side wrong on a symmetric garment = an asymmetric input. Before touching the draft, look at the start
  (`check_garment(stages=["place"])`) and compare every sim input with its mirror (pattern, body, start, made pieces).

Judging
- Measure what you name, on BOTH sides (a "notch" is the apex where collar end meets lapel, not the collar's tip).
- Front-view widths are what sticks out (shoulder width = the sleeve heads: cap ease, not the block's shoulder).
- Judge clay with shadows off and close cameras for small features; textured looks for seams, plackets, buttons.
- Judge against the reference in ITS pose (raise the arms on a copy if it raises them).
- A tucked under garment is never drawn without the garment over it.
- A render made before a code or pattern change shows the old result: check both renders in a comparison are current.

## Self-review loop (every round, from the form fit on)

1. Render yours at the reference's framing (`fit_garment`; after an optional sim `look_cloth` and
   `focus="garment:piece"` close-ups), clay AND diag, and put each view BESIDE the reference crop, region by region
   (one `review_view` call per view: no contact sheets): neckline / collar, shoulders and sleeve heads, armhole and underarm,
   chest and fronts, waist and hem, sleeves and cuffs, closures and plackets, back, folds, surface.
2. For each region list what reads wrong against the reference, concretely (where, what, how far off). Mark each
   MAJOR (the wrong garment, wrong construction, wrong proportion or silhouette, a visible defect) or MINOR.
   Order: construction and form before material, material before colour.
3. Fix the worst MAJOR at its stage (usually the description, the sheet or the pattern; rarely the solver). Re-run
   from that stage.
4. Repeat until no region has a MAJOR. Also re-measure the stage 0 items every round (table: item | reference | ours |
   pass). `check_garment_reference` does the measuring and the side-by-side panels when you used
   `garment_from_reference`.

A clean result that isn't the reference is wrong: no crossings, no strain and a "fits" verdict say the simulation
worked, not that the garment is the one in the picture. Don't argue a MAJOR away with numbers; argue only with
evidence that the reference doesn't show it.

## Common mistakes

| Mistake | Instead |
|---|---|
| Taking a kind's defaults as the design (`hoodie` gives a sweatshirt; simon a dress shirt) and fixing faults one at a time | Describe first; override the kind's defaults item by item from the description, and measure the draft |
| A knit made on a woven block, or a sweatshirt cut for a fitted sweater (deep armholes, boxy) | `"block": "knit"`, set-in `sleeve`, rib details, `worn_top: true`; check armhole depth vs the armpit on the draft |
| Simulating to find out whether the pattern is right | Read `look_pattern` and measure the draft first; a sim takes minutes, a pattern sheet seconds |
| Raising stiffness, stitch strength or resolution to fix puffed caps, gathered seams, a funnel collar, open seams | These are construction faults: cap ease, seam lengths, a missing piece, a seam that starts far apart (stage 4) |
| Reporting "seams closed, 0 crossings, fits" as done | Done is: the description's items pass and the self-review has no MAJOR |
| Judging a 2 cm draft's detail or a textured render's grain | Draft = fit and shape; clay for form; textured close-ups for details |
| An open jacket's fronts tenting forward | Side-panel hem spring: cut the panel seams straight below the waist (cloth_faults) |
| Lowering a jacket's collar stand to show more shirt collar | Lower the back neck and the notch instead (cloth_design) |
| Buttons missing in a render, so a sim is queued | Buttons are built after the sim; the render must draw them |
| A hold standing in for gravity (a hem, a side seam or a styling grip held to keep a shape) | Hold only real supports (shoulders, neck, seams, fastened closures, the layer under); let go and let it hang (C190, C199) |
| Raising stiffness until the shape holds, paid for in stretch | Threads first: no stiffness that stretches a thread; draft a canvas / interfacing region (C195, C196) |
| Judging a new garment against your own old or approved garment ("no worse than before") | Judge beside the reference only; old garments are not a baseline (C165) |

Full fault table with causes and fixes: guide(topic="cloth_faults").

## Known gaps (decide them in the description, don't discover them at the end)

- Fabric surface in the detail maps: `detail.surface` "knit" (stockinette V stitches, rib on the band roles;
  `detail.knit` wale / course / depth / trough) or "twill" / "plain" (a woven cloth: twill ribs only where the atlas
  resolves them, plus the crush, the short creases a worn cotton takes everywhere; `detail.woven` crush (m, 0.0003) /
  crush_size / crush_dir / crush_spread). A woven garment with no surface reads smooth and rubbery at game distance:
  measure fine (3-6 mm) contrast on a flat panel against the reference before tuning `crush`.
- Jeans: arcuate back-pocket stitching, rivets, coin pocket and indigo wear / fades aren't built; garments take one
  colour plus the sewing detail maps.
- A fitted jacket's side-back and underarm seams start far open (one start cylinder at the widest level): read their
  start gaps on every fitted jacket.
- A notched collar's ends where they meet the lapels can crumple; `collar_ends: "draped"` is experimental.
- Worn garments are drafted from a `base` body's measurements: a creature built from blobs has none. It can take a
  flat piece draped over the model (`{"drape": {"over": "model"}}`) or a clothing shell part with fold strokes
  (guide(topic="parts")).
- Welt pockets' cut and bag, a lining with its own pleat, pleats that die inside a piece.

## Where sims run

Two solvers: Blender's cloth (the default, local) and ZOZO's contact solver (`"backend": "zozo"`: intersection-free,
strain limited). A ZOZO job runs on this machine's GPU, or through your own remote command
(`$HIFIPUSHIE_ZOZO_REMOTE`, run with the job folder; it must leave out.npz there). Backend `"file"` writes the job
folder and waits for someone to bring back out.npz; backend `"remote"` runs `$HIFIPUSHIE_CLOTH_REMOTE` with the job
folder. Results are keyed on the job, not where it ran. Details and timings: guide(topic="cloth_sim").
