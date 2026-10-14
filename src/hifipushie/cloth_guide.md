# Clothes: read, design, draft, construct, then simulate

Garments here are made the way garment makers make them: decided on a design sheet, drafted to the body's
measurements, checked flat, constructed (folds, interfacing, closures), arranged round the body, then simulated
coarse before fine. Nothing is sculpted as a shell and nothing is warped from one body onto another. A tablecloth or
a blanket is the same machinery: one flat piece draped on a prop.

**The two rules everything else follows:**
1. **Describe the garment from the reference before choosing anything.** Kind, construction, fabric, measurements
   against the body, how it is worn. Every template, kind and default you pick must be justified by that
   description. Starting from the nearest template and fixing faults one at a time gives a clean garment that is
   the wrong garment (a sweatshirt block with torso-deep armholes where the reference is a fitted knit crewneck).
2. **Construction before solver.** A fault in the cloth is a pattern, sewing or made-piece fault until shown
   otherwise. Measure the DRAFT against the description before any simulation; never tune solver settings
   (stiffness, mesh size, contact) to hide a pattern fault. `dress` refuses to simulate while stages 1-3 fail.

Enable the tools with `enable_toolset("cloth")`. Sub-topics (guide(topic=...)): `cloth_reference` (reading a
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
| 2 | Pattern | Drafts to the body, walks seams, measures against the body | `look_pattern` | Seams, ease and evidence pass; the draft's measurements match the description |
| 3 | Construction | Plans sewing order, layers, folds, interfacing, made pieces | `check_garment(stages=["construction"])` | Passes |
| 4 | Arrange | Pins the pieces round the body | `check_garment(stages=["place"])` | No crossings, start stretch under the limit, seam gaps small |
| 5 | Draft sim | Blocks at 2 cm, judges fit and big shape only | `dress(quality="draft")`, `look_cloth` | Verdict "fits", draft targets pass, self-review has no MAJOR in shape |
| 6 | Final | Refines, cleans up, details, exports | `dress(quality="final")`, `look_cloth(textured=True)`, `export_asset` | Self-review passes at every region |

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

Then pick the kind, draft source or block, fit, fabric and details, and say which item justifies each. Example: "a
knit crewneck: kind `hoodie` (the KB's pullover knit kind) with `"block": "knit"` (not a woven bodice, not a
sweatshirt draft), set-in `{"op": "sleeve"}`, details collar `rib_neckband` / cuff `rib` / hem `rib_band` / pockets
`none`, `worn_top: true`, underarm 2-4 cm below the armpit, rib band heights read from the reference (a crew
neckband is usually 2-3 cm, cuffs and hem 5-7 cm), hem at the high hip, fabric jersey (a sweatshirt: french_terry)". Kinds, details and fabrics: guide(topic="cloth_design"), `garment_reference(kind=...)` (read
the kind's `lessons` before designing it).

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
- Fix fit in the pattern (ease, length, a detail's options), never by sculpting, never by solver settings.
- Made pieces (collars, stands, cuffs, waistbands, plackets, lapels) are constructed, not simulated into shape; they
  are laid at their CUT length and width, never on eased cloth. Buttons and trims are built on the finished drape:
  never re-simulate to add one.
- Different fabrics bend differently. One fabric on every garment reads generic; knits drape soft and rounded.
- A garment worn over another is drafted over it (`over`): its neck and armhole follow the under garment.
- A self-closed band (waistband, cuff, buttoned stand) must START closed; give it 2-3% ease.
- Room over the hips comes from the block (`hips_ease`), never from hem flare.
- Stale options persist: `design_garment` merges key by key. Read the resolved sheet back every time; clear with
  `false`, null or `replace=True`.

Simulation
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

## Self-review loop (every round, stage 5 on)

1. Render yours at the reference's framing (`look_cloth` views and `focus="garment:piece"` close-ups), and put it
   BESIDE the reference crop, region by region: neckline / collar, shoulders and sleeve heads, armhole and underarm,
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
| Picking the nearest template (hoodie, simon shirt) and fixing faults one at a time | Describe first; choose kind / block / details from the description |
| A knit made on a woven block, or a sweatshirt cut for a fitted sweater (deep armholes, boxy) | `"block": "knit"`, set-in `sleeve`, rib details, `worn_top: true`; check armhole depth vs the armpit on the draft |
| Simulating to find out whether the pattern is right | Read `look_pattern` and measure the draft first; a sim takes minutes, a pattern sheet seconds |
| Raising stiffness, stitch strength or resolution to fix puffed caps, gathered seams, a funnel collar, open seams | These are construction faults: cap ease, seam lengths, a missing piece, a seam that starts far apart (stage 4) |
| Reporting "seams closed, 0 crossings, fits" as done | Done is: the description's items pass and the self-review has no MAJOR |
| Judging a 2 cm draft's detail or a textured render's grain | Draft = fit and shape; clay for form; textured close-ups for details |
| An open jacket's fronts tenting forward | Side-panel hem spring: cut the panel seams straight below the waist (cloth_faults) |
| Lowering a jacket's collar stand to show more shirt collar | Lower the back neck and the notch instead (cloth_design) |
| Buttons missing in a render, so a sim is queued | Buttons are built after the sim; the render must draw them |

Full fault table with causes and fixes: guide(topic="cloth_faults").

## Known gaps (decide them in the description, don't discover them at the end)

- Knit surface texture (stitch gauge, rib texture on bands) isn't in the detail maps: a knit reads from its drape,
  bands and silhouette only.
- Jeans: arcuate back-pocket stitching, rivets, coin pocket and indigo wear / fades aren't built; garments take one
  colour plus the sewing detail maps.
- A fitted jacket's side-back and underarm seams start far open (one start cylinder at the widest level): read their
  start gaps on every fitted jacket.
- A notched collar's ends where they meet the lapels can crumple; `collar_ends: "draped"` is experimental.
- Welt pockets' cut and bag, a lining with its own pleat, pleats that die inside a piece.

## Where sims run

Two solvers: Blender's cloth (the default, local) and ZOZO's contact solver (`"backend": "zozo"`: intersection-free,
strain limited). A ZOZO job runs on this machine's GPU, or through your own remote command
(`$HIFIPUSHIE_ZOZO_REMOTE`, run with the job folder; it must leave out.npz there). Backend `"file"` writes the job
folder and waits for someone to bring back out.npz; backend `"remote"` runs `$HIFIPUSHIE_CLOTH_REMOTE` with the job
folder. Results are keyed on the job, not where it ran. Details and timings: guide(topic="cloth_sim").
