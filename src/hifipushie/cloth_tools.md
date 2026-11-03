# Clothes: tool reference

The cloth tools' full parameters and behaviour, one section per tool (guide(topic="<tool name>") returns one).

PICTURES ARE FOR SHAPE, TEXT IS FOR NUMBERS (C288): judge a look for shape (curves, which way an edge runs, which edges
share a colour); take every number and name from the tool's text answer, never read one off an image.

## Tool reference

### `chain_garment`
`chain_garment(name, garment, wear=None, opening=None, wait=50, rebuild=False, waive=None)`: THE start of every garment: to dress a character, to fit or drape clothes on a body. Reads the drafted pattern and the
body, never a fit. Built straight into the garment record's style plan (step 2, T7): the band closure's state is the wear
(open / partly: built open, never closed first), the front fastened from its first button (partly: `fastened_from`), the
plan's collar_points_apart its spread; give wear / opening only without a plan (a contradiction is refused). Stages: band and collar (or other stiff parts) as chains of their cut lengths, stiffness from the
pattern's interfacing, resting on the high points; cuffs as stiff rings on the limb's own section; the soft pieces wrapped on a
garment-sized section and solved as a network with the body as a floor; surfaces filled between the chains; an open band is
opened before any soft cloth (its sewn front limited by its cut distance to the first fastened button), and the plackets fold along a
solved crease; then the STRUCTURE check reads the build (never a hang) against the garment record's style plan (step 2's rows and numeric bends, each judged by its kind; C286) plus general rules: the fall lying, turned over its stand, each closure in its planned state (and a closed one meeting), the hem level left to right, the soft cloth not crumpled (soft_cloth_smooth: each soft piece's bump p90 <= 2x a smooth 40 mm tube's at its mesh size). No style plan, or a row with no build reading yet: UNMEASURED by name (waive with a reason or add the reading). A FAIL ends the job "structure_failed": the answer lists each failing row with its target, source and change: (the alter_pattern op, design option or build stage to fix); waive={row id: why} re-reads the saved build (no rebuild) and accepts those rows by name (PASS_WAIVED). After a pass the job stops at "awaiting_approval" (step 7a of the garment record: nothing is hung that wasn't approved built): the answer gives the sheet and the exact approve command for Joe or the coordinator; an agent never approves. Once approved, the same call resumes the hang from the saved build (HIFIPUSHIE_PRESIM_APPROVAL=optional: it hangs straight away). Then the soft cloth hangs under gravity (ZOZO, 5-10 min) with the stiff parts held; lengths last. The hang's gate (step 8): any face past the thread cap FAILS, with back to step 5 and a change: line; the cap is the cloth's, never a setting. wear: "closed" or
"open". opening: only with "open": collar points this many neck widths apart (default 1.7, 1.0 .. 2.6). A job: the call starts it
and answers with its stage after at most wait s (0 .. 280); a build takes 2-10 min, then the hang runs, both slower on a loaded
machine. Call again with the same arguments for the stage: that never starts a second build. Once built the answer carries the chains,
threads, seams and band numbers. A finished job answers with its result; a changed pattern starts anew; rebuild=True starts over.
Every answer's next: names the call. A worker that dies reads as failed, not as running for ever. Refuses: an unpassed pattern gate (next:
pattern_check); a line whose length can't hold (named, next: alter_pattern there); a start the solver would refuse (a tool
fault, named: report it). Nothing is pushed, cut or loosened to get past a refusal.

### `look_chain`
`look_chain(name, garment, wear="closed", focus=None, size=640, reference=None, save=None)`: the BUILD until its structure
check passed and the hang ended, then the hung result (the text says which). focus: none = whole figure, four views on the body; "neck" = the collar close, on
the body; a piece's name = that piece alone, large, four sides. Sewn seams are joined and every piece faces outward.
reference: an image path shown beside each view. Judge each view yourself against the reference, then review_view one view per call.

The full documentation of this topic's tools: their MCP descriptions are the short form. guide(topic="<tool name>") returns one section. These tools are the `cloth` domain: run them with call_tool(name, args); find_tool(\"<job>\") gives each one's parameters and an example call.

### `design_garment`

`design_garment(name, garment, design=None, spec=None, replace=False, note='')`

Stage 1 of the clothing workflow (guide(topic="cloth")): the design sheet, decided before any drafting, as a
pattern maker does. STRICT (C241): every sheet key, detail param, op, op parameter, block option and FreeSewing
option is checked; an unknown one is an error listing the valid ones with units, sign and default; a failed call
saves nothing; each FreeSewing option set is reported with the default it REPLACES (Simon's lengthBonus default
0.25: 0.05 gives 0.05, not 0.30). Units, signs, which keys go on which route: guide(topic="cloth_design"). Stored in spec["cloth"][garment]["design"] (merged key by key, null deletes; replace=True
replaces the garment). design: {"kind": shirt | blouse | tee | hoodie | jacket | coat | trousers | shorts | skirt |
dress | flat, "from": a draft source that can make it (simon, carlton, skirt_block; or DESIGN it: "block":
bodice | knit | trouser | skirt, "block_options": {...}, "ops": [pattern operations] (garment_reference(principles=
"operations" | "derivations"): a garment with no ready-made draft is a block + operations); or leave out and give own
pieces + seams in spec), "fit": the kind's fit (slim, regular, a_line...), "fabric": a fabric (cotton_shirting,
oxford, linen, cotton_twill, denim, wool_suiting, wool_coating, jersey, rib_knit, french_terry) or a solver preset,
"details": {collar: shirt_collar | band | convertible | notched_lapel | shawl | hood | rib_neckband | ...,
cuff: barrel | french | rib | hemmed | ..., sleeve_placket, front_closure, placket, waistband, skirt_closure, hem,
darts, ...: a choice or {"type": choice, "options": {raw draft options}}}, "pattern": {draft words: ease, length,
options...}, "notes"}. Left-out details take the kind's defaults (garment_reference(kind=...)).
spec: other garment keys (color, state, quality, backend, resolution...), merged the same way.
Returns the resolved sheet (every choice, where it came from, the dimensions to work to) with hard failures first:
a choice the source can't make, a choice that needs another (a barrel cuff needs a sleeve placket). Next:
look_pattern.

### `look_pattern`

`look_pattern(name, garment, save=None)`

Stage 2 of the clothing workflow: the garment drafted to the body and laid out flat on a pattern sheet (every
piece at one scale with one large name, grain arrow, notches, buttons/buttonholes, fold lines (blue dashed),
interfacing (hatched), each seam pair in one colour on both its edges, a 10 cm bar and a big colour legend; shape
only: every piece's size and every seam's lengths and ease are in the text answer), plus the checks before any sim, failures first: every design-sheet choice
evidenced in the pieces and seam table (a turned collar has a fold line, a barrel cuff is closed and interfaced,
the fall covers the stand...), every seam's ease in its band (sleeve cap by kind, bands, plain seams), notches
aligned, ease against the body per girth inside the fit's band, every piece sewn to something, the details'
dimensions. Fix failures in the design sheet (design_garment) or the garment's pattern options before going on.
Next: pattern_check.

### `check_garment`

`check_garment(name, garment, stages=None, images=True, save=None)`

Run the clothing workflow's checks (guide(topic="cloth")), failures first. stages (default all, in order):
"design" (the sheet), "pattern" (the draft vs the sheet and the body), "construction" (sewing order, layers and
lap, fold/press lines with angles, interfacing and what rests as made, the sim's stage schedule; fails when
something that must roll is frozen as made), "place" (the pieces arranged round the body before any sim: pieces
through each other, pushed off the body, start stretch past the solver's strain limit, layer gaps; renders the
start), "sim" (after dress: the verdict plus the numeric targets: layer gaps, collar cover and points, hem level,
waistband height, sleeves on a hanger, crest radius, strain; each judged at the quality it belongs to).
images: the pattern sheet and the placed start as images (save=path writes them with _pattern/_place suffixes).

### `garment_record`
`garment_record(name, garment, sheet=False)`: the garment record (src/hifipushie/garment_record.py; the steps:
docs/state/garment_steps.md). One file per garment, workspace/<model>/garments/<garment>.json: per step its output (or a
pointer), status, gate rows, reference, look and, on a FAIL, back_to. pattern_check writes step 4, chain_garment steps 5, 6
and 8, look_chain the build's look (6) and the hung garment's look (9). A write to a step whose previous step isn't ready
is refused by name; a changed step makes the later ones stale. Approvals: `bin/approve add garment
<model>.<garment>.<step> <record>#<digest> <sheet> joe|coordinator` (the answer prints it); they hold while the digest
does. Step 7a's approval is required unless HIFIPUSHIE_PRESIM_APPROVAL=optional. sheet=True renders the step-0
reference beside every look plus a status tile; every step's status is also in the text answer.

### `body_tape`
`body_tape(name, measurements=None, garment="", landmarks=False)`: garment step 3, measuring the model's base body BY NAME
(src/hifipushie/body_tape.py; its docstring is the spec). Measure what steps 1-2 (parts, style plan) call for: each seam
you will draft needs a length or a girth on the body; name it and say how it is taken. measurements: a list of
- a FreeSewing name as a string ("chest", "hpsToWaistBack", ...; tailor.measure's list, in FreeSewing's definition through
  measure_defs; {"name", "kind": "freesewing", "consumer": null} for the tape's own),
- {"name", "kind": "girth", "at": LEVEL} round the torso, level; {"square_to": "arm.L" | "forearm.L" | "thigh.L" |
  "shin.L" | "neck", "t" | "along" (m) | "at" (a landmark)} round a limb; "fullest" / "narrowest": [LEVEL, LEVEL]
  (body) or [t0, t1] (limb). The tape is the section's convex hull (it bridges hollows).
- {"name", "kind": "arc", "from", "to", "over": "front" | "back" | "top" | "bottom" | "left" | "right", "taut": true}:
  over the surface, the shortest plane arc through both landmarks bulging to that side.
- {"name", "kind": "length", "from", "to", "via": [...], "over": "surface" | "straight", "side"}; or {"from", "down_to":
  LEVEL, "side": "back" | "front"}: the tailor's tape down the body at the start's x, taut (hpsToWaistBack's way).
- {"name", "kind": "height", "from", "to"}: vertical between LEVELs or landmarks ("floor").
LEVEL: armpit, chest, waist, high_hip, hips, seat, crotch (tailor's definitions), any landmark's height, {"z": m},
{"between": [LEVEL, LEVEL], "t": f}, {"at": LEVEL, "dz": m}. Landmarks (landmarks=True lists them with positions and
how each is found): hps.L, shoulder_point.L, neck_side.L, cf_neck, cb_neck, bust.L, cf_/cb_/side_<level> (.L/.R), crotch,
floor, crown, every joint (inside the body: straight and vertical only; "joint:<name>" where a name is taken).
A refusal says what is wrong and what to say instead (an unknown landmark lists them; a level outside the body gives
the body's range); the others are still measured. The look (always made): every tape on the body front / side / back,
numbered, solid where seen, a large legend naming each number; every value is in the text answer (read
values there, never off the look); workspace/<model>/tape/step3_measure.png, or with garment the
record's look folder, and step 3 of the record is written (refused until step 2 is ready). Example:
`body_tape("wf_simon", [{"name": "back_waist_to_seat", "kind": "length", "from": "cb_waist", "to": "cb_seat", "side":
"back"}, "chest"], garment="hussar")`.

### `garment_plan`
`garment_plan(name, garment, step, plan, look=True)`: steps 0, 1, 2 of the garment record (src/hifipushie/garment_plan.py:
its docstring is the full form), for ANY garment. You are the intelligence: look at the picture, know the construction;
the tool is the structure, the refusals and the look. step="read" (0): kind; views [{image, view, scale?}]; cloth {name:
{fabric (a garment_kb fabric fills gsm / thickness / bending length) or the numbers + source, stiffness, colour [r,g,b] or
{at: [[u, v]], view} (sampled), print {kind, repeat_mm, source}, grain}}; fit {view, landmarks {name: v | {at, from: how inferred}}, widths [{at (a landmark, or a garment height: 'hem'), garment [[u,v],[u,v]], body, body_from}] at that row, heights [{name, at: v, on: torso|leg|arm}]} (RATIOS on the picture, applied to the model; seen edges measured on the picture; landmarks = the points the landmark card draws, checked against each other). step="parts" (1):
pieces {name: {what, cloth, seen: seen|occluded|inferred, from (the convention, unless seen), build: full|simplified|omit,
why, stiff, layer, where {view, outline}}}, details {name: {what, on, cloth, follows ["piece:edge"] (a trim along edges), count, seen, build, where {view, at | outline |
outlines (one per instance)}}},
closures {name: {what, pieces, details}}, seams [{a: "piece:edge", b, kind, length: {body: [names]} | {style: {ratio |
value_mm, of, source}}}]; the answer lists the body measurements step 3 must take. step="style" (2): state {closure:
{state: open|closed|partly, source}} for EVERY closure (build straight into it; never build closed then style open),
bends [{id, on, target {value, unit, of (a ratio's base)} | {is}, source}], pose {name, source}, rows [{id, what, target, source, note?, view, at}] (what = a structure_rows kind, refused otherwise with the list: collar_points_apart, collar_tilt, collar_rise, collar_points_drop, collar_height, fall_back_width, v_depth, front_edge_plumb, hem_front_back, sleeve_end, cuff_ease, garment_length, cutaway_drop, trim_row_count, trim_row_pitch, trim_lines_apart, not_judged; bases neck_width, shoulder_width, closure_length; a ratio is OF the kind's base; a px target becomes a ratio of the base row on its view, else mm by the view's scale; a numeric bend names its kind too)
(what the photo judges: the structure gate's targets). Refused by name: a seam on a piece not in the inventory, a built
piece with no seam, a target with no source, a state for a closure the inventory lacks. look (default): drawn over the
reference: seen solid, occluded dashed, inferred dotted, omitted grey, judged rows yellow; saved as the step's look.
Every `at` / `outline` / `points` is PIXELS of the named view's image (u right, v down from its top-left corner), never
0-1 fractions: values all within 0..1 on an image wider than 2 px are refused (multiply by the image's width / height).
Body measurement names in seams' `length.body` are body_tape's: FreeSewing's names the tape takes, or names you define
in step 1's `define` {name: girth|arc|length|height} (measured by that kind at step 3); others are refused with the
closest valid names. Rewriting step 1 carries steps 2 and 3 forward when they still validate against it (re-stamped,
said in the answer); only what no longer validates goes stale, with the reason.

### `draft_pattern`
`draft_pattern(name, garment, design, declarations, options=None, sa=10)`: garment step 4, YOUR OWN pattern (no published
design, no recipe; src/hifipushie/draft_own.py's docstring is the spec). Needs steps 1 (parts, seams) and 3 (body_tape).
- design: a FreeSewing 4 ES module. Import blocks and extend them: `import { Design } from '@freesewing/core'`,
  `import { back, front } from '@freesewing/brian'` (also bent, jaeger, carlton parts; `@freesewing/library`: sleeve,
  topsleeve, undersleeve). A part: `{ name, from: back, hide: { from: true, inherited: true }, after, measurements,
  options, draft: ({ points, Point, paths, Path, snippets, Snippet, store, measurements, options, part }) => part }`.
  Each visible part draws `paths.seam` (the closed sewing line, mm, y down); hide the inherited paths you don't sew.
  Button marks: `snippets.btn1 = new Snippet('button', point)`. End with `export default new Design({ parts: [...] })`.
  REUSE FreeSewing's parts for a role it already drafts (simon collarStand / collar / cuff, jaeger / carlton collar
  parts, bent's two-piece sleeve, brian's sleeve): `{ name: 'my.band', from: collarStand, after: [front], draft:
  ({ part }) => part }` with its options overridden (options.json / `options`): FreeSewing's parts carry a patternmaker's
  curves (a stand's neck edge bends, a fall's outer edge is longer). Using them is RIGHT; drawing a curved piece as
  straight lines is what the flat gate refuses. (What's banned is garment-specific glue in hifipushie's code, never
  FreeSewing's parts.) SEE a design's parts before declaring: `pattern_parts(design)` (a pack design or your own
  source: what it exports, HIDDEN bases, each part's seam outline as point names in order; part=: its points and paths).
  Measurements are step 3's names (FreeSewing's or your own); the design's full list (every part it drafts, through
  from / after) is checked against step 3 BEFORE drafting and the missing ones named. Node runs it without network, fs read-only, 60 s; an
  error comes back as `design.mjs line N: message` with the line.
- declarations (step 1's names): `pieces` {piece: {"part", "fold": "x0" (cut on the fold at x 0: mirrored points are
  "<name>.m"), "mirror", "cut", "grain", "place": {"to": "torso" | "arm.L" | "neck", "side", ...}}}; `edges` {piece:
  {edge: "a>b" | "a>via>b" (outline points) | {"path": a path of the part}}}; `seams` [{"a": "piece:edge" | [chain in
  order], "b": ..., "ease": [lo, hi] (a over b - 1), "why"}] (every step-1 seam; a seam sewn to several edges is one
  chain); `stiff` [piece]; `folds` [{"name", "piece", "line": [p, q] | edge, "kind": "press" | "roll"}] (a step-1 seam of
  kind fold is a fold named like its edge); `closures` [{"name", "kind", "over", "under", "edge": {"over": edge,
  "under": edge}, "at": [[hole mark, button mark]]}]; `omit` {piece: why} (a built step-1 piece you don't cut).
  Example: `{"pieces": {"back": {"part": "my.back", "fold": "x0", "place": {"to": "torso", "side": "back"}}}, "edges":
  {"back": {"side.L": "hem>armhole"}}, "seams": [{"a": "front.L:side", "b": "back:side.L"}]}`.
- Refused by name (nothing written): a step-1 seam with no drafted edge or not sewn, a piece not in step 1, a built piece
  not drafted. Else the flat gate: seams (each pair within its declared ease, else +-1 %), cut, sewn, closures (lapped
  edges within 1 %), truing (info), and SHAPE per role (draft_shape.py; each FAIL says `change:`): a stand / band's neck
  edge rises at its front ends (stand >= 0.24 x the neckline's front drop, jaeger; band > 0) and its free edge is shorter;
  a fall's outer edge >= 1.012 x its stand seam (simon); a sleeve cap 0.47-0.79 x the armhole depth (brian, bent); no
  straight edge sewn to a curved one. Name a stand's free edge `top`, a fall's `outer`. An outline seen in the reference
  is TRACED from it: corners stay corners (a stepped cutaway is `line`s meeting square), curves stay curves (a stand's
  rounded front top corner), never approximated by one arc; judge the sheet's outlines beside the photo. The sheet is shape only (one big name per piece, each seam pair one colour, legend S<n> = the
text's S<n>); the text lists every piece (size, cut, stiff) and every seam pair (both edges, both lengths, ease,
PASS/FAIL); step 4 written; pattern_check re-reads it.

### `pattern_parts`
`pattern_parts(design, name="", garment="", part="", options=None, look=False)`: the part inspector
(src/hifipushie/pattern_parts.py). design: a pack design name (brian, bent, jaeger, carlton, simon, teagan) or your own
design's source. Run in Node like draft_pattern. Without part: the measurements the design needs (every part it drafts),
every part in draft order (HIDDEN = a base other parts copy, not a piece you get; from / after), its points and paths
counts and its `seam` outline as point names in the order it runs (aliases at one spot "a=b"), then the options (default
[min..max]). part="jaeger.front": that part's points (x right, y down, mm) and every path as point names in order;
look=True draws it (shape only, the seam's points named large). Declare edges along that order: "a>b", "a>via>b".
name + garment: drafted with step 3's measurements; else with stated DEFAULT values (coordinates only indicative).
A design reaching a part only through `from` (jaeger's front via frontFacing.from) shows it here as HIDDEN or not.

### `garment_details`
`garment_details(name, garment, details, wear="open", look=True)`: step 7, details and trims (src/hifipushie/garment_details.py
docstring: the vocabulary). WHERE each detail sits is decided ONCE, on the pattern, at step 4, as a pattern maker marks
button and trim placement: draft_pattern's declarations `marks` {detail: mark | [marks]}, in pattern terms (named
points and edges, mm): `at` [{point, dx, dy} | {edge, mm | t, in}], `rows` {edge, count, from_mm | from_t, pitch_mm |
pitch_t (of the edge) | to_mm | to_t, in}, `points` "button*", `follows` ["piece:edge"] (+ in, default half the width),
`path` [positions], a motif's `lines` [[[across, along] mm]] + `knots` (repeated at its rows: a frog), `mirror` (the
.L/.R twin by the same names), `stiffens` (a braid / binding / zip tape that stiffens its edge: declared there so the
build can feel it). A closure's buttons are its own marks; a zip's tape takes its declared edges. draft_pattern refuses a
built step-1 detail with no mark. Here, `details` gives geometry only: {detail: {kind point|line|motif, size_mm (point,
knot), width_mm (line, motif cord), thickness_mm (default the cloth's), shape dome|disc|box, colour (default the step-0
cloth's)}}. A position here is refused; so is a detail not in step 1, omitted there, or made of cloth (pocket, flap,
epaulette: a pattern PIECE, built by chain_garment). Every built inventory detail placed with step 1's count = PASS
(step 7 done + 7a written with this look); else FAIL rows naming each (no mark: back to 4). Details are anchored
barycentrically on the flat mesh and re-made on any positions of it: the build, and the HUNG garment (they never enter
the sim: they are carried; call again after the hang to carry them, or they are carried when the hang exists). Their
meshes stay separate from the cloth (details.pkl in the job dir, one per detail with its colour: export, T11). Solid
details over another garment (a jacket over shirt buttons) need a clearance check: layering (T9), not done here. The look
is SHAPE (C288): the build with its details beside the reference + the flat pieces with the details; the numbers
(count, marks in pattern terms, sizes) are in the text. chain_garment's step 7 is done only when every inventoried detail
is placed (or there are none); until then 7a can't be written, so the build waits for this call.

### `garment_appearance`
`garment_appearance(name, garment, appearance=None, wear="open", role="main_npc", look=True)`: step 9a, the garment's
material painted on its FLAT PATTERN (garment_appearance.py docstring: the method). The export's UVs are the pattern packed
in one square (garment_appearance.layout, shared with export_garment), so everything is in pattern coordinates (metres).
Layers: base colour per cloth (step 0's reading; each piece's cloth from step 1, an unlisted piece gets the main cloth: said),
variation (value noise, amount 0.03 at 80 mm by default), the print (step 0's check / stripe at its repeat_mm, line_mm
default 5 % of the repeat) turned to each piece's grain (M["grain"], deg, 90 = along y), surface (weave / leather pebble as
normal + roughness; DROPPED when finer than 3 texels: said), stitching (dashed, length_mm 2.5, offset_mm 3 inside seams
and hems: border edges sewn = seam, free = hem), wear (0 by default; a wear > 0 needs `why` from the story; at the plan's
`where`: elbows, shoulders, knees, seat, hips: the rig's joints, where the build touches the body; and free edges), fray
(only the plan's pieces' hems: alpha cut + threads along the grain; the GLB material becomes alpha-tested). The block, in
step 2's output as `appearance` (garment_plan validates it) or this call's argument (same check):
`{<cloth>: {wear, why, where: [...], edges, fray: {pieces, depth_mm}, stitch: {colour, length_mm, offset_mm, edges:
seams+hems|hems|seams|none}, variation: {amount, scale_mm}, print: {kind, repeat_mm, line_mm}}, details: {<detail>:
{material: metal|braid|plastic|horn|wood|cloth|leather, colour}}}`. Maps at the role's clothing texture set (budgets.json
textures.sets): <job>/appearance/<garment>_{base,mr,normal}.png + _appearance.json. The look: the textured garment + body
in EEVEE (asset.preview), four views, a chest close-up and the texture sheet, each beside the reference (C288: shape and
colour judged by eye, numbers in the text). Writes step 9a; export_garment then puts the maps on its GLB (without 9a it
exports flat colours and the record refuses step 10).

### `export_garment`
`export_garment(name, garment, wear="open", role="main_npc", look=True)`: step 10, the chain garment as a game asset
(src/hifipushie/garment_export.py docstring: the method). The hung garment (final.pkl; else the build) is the HIGH poly; the
game mesh is a re-grid of the FLAT PATTERN mapped onto it (garment_game's remesh: seams sampled once and shared, stiff
(made) pieces to 8 rows across, fold lines kept as vertex rows), outer + inner faces + rims on free edges, so the UVs ARE
the pattern (pieces packed in one square). The grid is the finest that fits the role's `clothing` LOD0 budget
(budgets.json; details count too), between 6 and 40 mm; over budget at 40 mm is refused with what to change (a bigger role,
fewer pieces built in full at step 1, simpler details at step 7); a budget is never changed to pass. Step 7's details
(details.pkl) are their own meshes and materials. Weights: read off the body (rig.skin_parts: the base body's own at its
surface), Mixamo bone names (rig.rig_bones); a detail takes its nearest garment vertex's. Gate rows (numbers in the text):
triangles <= budget; UV stretch (3D / pattern area per triangle) p95 no more than the drape's + 0.03, p5 no more than 0.10
below it (chords across folds); no open pattern edges; the weight check (LeftArm raised 45 deg: each vertex's distance to
the body changes <= 12 mm p95 where the body moved). Refused unless step 9 is approved (internally an approved 7a exports the
build; step 10 is then not written: the text says so). Writes <job>/export/<garment>.glb (+ _export.json, the look GLBs)
and step 10; the look is SHAPE: the GLB with the body in EEVEE (asset.preview), rest beside the reference, and posed.
Not done: LODs, the normal bake of the folds (garment_game.bake), layering culls (a shirt under a jacket).

### `alter_pattern`

`alter_pattern(name, garment, ops, replace=False, note='')`

A pattern maker's alteration on the FLAT pattern: ops appended to the garment key "alter" (replace=True replaces the
list) and applied in order after the draft (pattern.apply). Units: metres, fractions for ease, degrees. Coordinates:
x right, **y UP** (+y toward the neck / the cap). Ops (pattern.ALTER_OPS; every key checked, an unknown or missing
one is an error listing the op's keys with units and defaults):
- slash_spread {piece, line, amount (m opened at the free end, + adds cloth), hinge "a" | "b" | "none"}
- turn {piece, line (a straight fold line), keep (a point on the side kept)}
- move {piece, point, by [dx, dy] m (y UP: [0, -0.01] lowers the point 10 mm), falloff 0.05 m}
- scale {piece, line, amount (m added parallel across the line, - shortens)}
- slit {piece, line, width 0.003, name}; trim {piece, edge "a>b", length m OR match [edges], name}
- true {piece, at, keep, deg 90, blend 0.04}: the edge leaving point `at` bent so the piece's corner there is `deg`,
  the kept seam unmoved (necklines / armholes meet the shoulder seam at ~90 deg)
- match {piece, edge "piece:a>b", to ["piece:a>b", ...] (a LIST), line (or {piece: line}), ease}: WALK THE SEAM, the
  pieces lengthened across `line` until `edge` equals the summed `to` edges x (1 + ease)
A line is a line name, [[x, y], [x, y]] m, or two point names ("name+[dx,dy]" offsets). A draft op (round_corner,
reshape...) is refused here with the reason: draft ops run on a block draft (design_garment ops). Nothing is saved
unless the whole call succeeds (drafted, placed, seams walked and the sheet rendered before the save). Each op that
changes a default carries "source" (where the number came from; the gate warns without one).
Returns the flat pattern sheet and every seam walked (A | B lengths, ease, notches off; truing junctions where the
build has them), then the next step: seams that don't walk -> "match" them; else pattern_check (the gate record is
per pattern, so any alteration needs a new one).

### `pattern_check`

`pattern_check(name, garment, refs=None, waive=None, views=None, size=480, diag=None, save=None)`

THE PATTERN GATE (codified C11): the garment drafted and placed on its body (no sim) and every cloth_checklist item
of its kind measured there: seam lengths / ease / notches, lengths and widths, design choices, the neckline
standoff; where this build has them, truing (junction angles), the collar draft and notch, flat tailor rows. Items
with no pattern-stage measure or no reference reading are UNMEASURED and block; drape items are SIM (judged later);
trial-placement readings are INFO until the form is validated. The record (/mnt/data/hifipushie/pattern_gate/<key>.json,
keyed by the pattern's content hash + the body's) is what chain_garment checks: it refuses
without a PASS for exactly this pattern + body.
refs: the reference reading (cloth_reference.read's output or its saved path). waive: {item id: reason} accepts a
FAIL / UNMEASURED row by name (recorded; PASS_WAIVED).
Returns: the FLAT pattern sheet (shape only: pieces, grain, notches, seam pairs by colour; the pieces' sizes and the
seams' lengths and ease are in the text), the DIAG views of the
placed pattern (by default two rows: panels + seams + turned, then strain + layers; diag=False none, or your own
modes / rows), and the per-item table FAIL / UNMEASURED first, then "next:": on a FAIL the rows to fix and "don't
simulate"; on a PASS chain_garment. views (default front, three, side, back), size (px), save (PNG path prefix).
Renders take the GPU lock.

### `fit_garment`

`fit_garment(name, garment, views=None, size=560, clay=True, diag=None, force=False, save=None, styled=True)`

The virtual dress form: the garment assembled from its pattern on the body with NO sim, as a MUSLIN (C162: woven,
threads held, the bias shears, a soft neck pin; this fit IS the fit, no release sim follows) (pattern_form: landmarks
pinned, seams closed, folds on their lines, relaxed against the flat pattern; a layered garment over its under one).
On a build without the dress form it shows the placed rest and says so. Refuses until pattern_check has a PASS
for this exact pattern (force=True looks anyway and the text says FORCED).
Returns the clay strip, the diag sheet (default panels + seams + turned; strain + layers; diag=False none), the face
strain vs the flat pattern (p99 and max; the gate is p99 <= 6 %, KES EMT for suiting), the layer pierce (faces of the
under garment through this one), the folder of single-view PNGs for review_view, and "next:": a red strain or a
pierce names the pattern fix; otherwise judge clay + diag beside the reference, one view per review_view call.
HOW IT HANGS (hang_reads, every fit): rows hang_wings (thin double layer standing out at the side seams), hang_sleeves
(the gap over the TOP of the arm: a hanging sleeve rests there), hang_shoulders (cloth proud of its neighbourhood at
the shoulder point) and hang_hollow (cloth inside the body section's convex hull: between the legs, the seat). Until
the fit has a hang step they FAIL as the FIT's faults (owner "fit"): listed with their fix, never a pattern change,
and they block neither the detail rows nor an outer garment. No reference image: review_view(reference="") runs the
blind "how clothes hang" look on each view.
A sim after this is optional, a wrinkle source only; never close or hand-finish after a sim (measured 2026-10-19:
strain p99 4.7 % -> 66-74 %). views, size, clay, save.
WORN AS ITS KIND SAYS (C146): after the closed fit, the wear's style ops (garment_kb kinds.<kind>.wear.<tie|no_tie>
.style; the same op list as style_garment) set it as it is worn. A shirt without a tie (the default) gets its collar
opened as Joe's references show (the shirt spike's c1): its first fastened button ~90 mm below the band's CF corner
(the wear's closure spacing), the band ends turned open about Simon's hinge marks, the points pulled out, the collar's
outer edge smoothed into one curve, the tips un-buckled. The text then prints the OPEN COLLAR READS, item | target |
ours | PASS / FAIL against Joe's photo / trace (garment_pull.OPEN_COLLAR_TARGETS: inner corners and points apart over
the neck width, V angle and depth, leaf front edge, the outer edge one arc, collar / tip crumple, folded faces, mirror).
styled=False shows the closed fit; a garment with its own worn_open (the old fold / pin route) or "style": false is
not styled. A garment's own "style" may be a list (replaces the wear's) or edits by op kind, e.g. {"turn": {"tol":
0.005, "steps": 16}} (Garrett: his concept's first button 83 below HPS leaves the fronts too little cloth for the full
65 deg band-end turn, so it turns until it would stretch). The fastened buttons are held with the cloth round them
(C147: Garrett's first button was pulled 8.7 mm open before).

### `style_garment`

`style_garment(name, garment, ops, free=None, hold_below=None, views=None, size=560, clay=True, diag=None, force=False,
save=None)`

STYLING BY HAND, as far as the cloth goes without stretching (C142 / C143, Joe 2026-10-21). A man pulls his shirt
down along the G-line, pops his cuffs and opens his collar points out and to the side; a woman pulls her skirt down.
That isn't gravity: it's "flatten this along interesting geometry without stretching it much", and it's how people
put clothes on. Pull and smooth are the two styling operations. The garment is fitted on the form (fit_garment's fit,
no sim), then `ops` run in order, each from where the last left the cloth:
- `{"pull": {"handles": [...], "step"?, "tol"?, "max_move"?}}`: every handle is dragged the same distance, in 3 mm
  steps, with the cloth solved against its flat pattern each step (per-face ARAP, sewn pairs welded, no bending). The
  pull stops at the last step whose stretch p99 is within `tol` (0.5 %) of the least the pull has reached. Slack is
  taken up first, then the knee. Never pin a handle at a guessed coordinate: pins dragged the shirt's corners to
  22-152 %. Never tune stiffness either.
  A handle is {"at", "dir", "side_from"?, "patch"?, "turn"?}:
  - "at" is what the hand grips: "piece:point", "piece:a..b" (the piece's border between two points: a hem, a cuff's
    edge, a front edge) or a list.
  - A POINT grabs the cloth within `patch` (25 mm on its pattern) and the patch TURNS with the cloth each step. One
    vertex dragged pinched and twisted the collar's tip (15-18 %, 60-80 deg). A rigid patch folded the cloth over at
    its edge (18 / 28 faces).
  - A border moves as one (the hand holds its line).
  - "dir" is a vector [x, y, z], "side" (away from CF), "out" (the body normal), "up", "down", a weighted mix like
    {"side": 1, "out": 0.3, "up": 0.3}, or "easy" / {"easy": base}. With "easy" the cloth chooses: each step probes 9
    directions round the base and takes the least stretch (about 9x the time). Don't bake in out / up weights: the
    shirt's points came out too high with up 0.3.
  - Mirrored handles (each lead near the other's mirror image) are pulled in mirrored directions. Without that, the
    fit's own asymmetry tilted the two "out" directions apart and one collar point rode 2 mm higher.
  - Take "side" from a landmark well off CF ("side_from": a hinge, a neck point). It is refused within 15 mm of x = 0,
    where a band's two ends cross and the side flips.
- `{"turn": {"turns": [{"at", "about": [point a, point b], "deg", "toward"?, "side_from"?}], "steps"?}}`: a grip
  turned about a line in stages. Examples: a band end swung open about its hinge, a cuff turned up about its fold.
  "toward" is a direction that picks the sense. A turn grips the cloth within "patch" (15 mm) of what it names: the
  band end's 3 corner vertices turned alone pinched a lobe at its top corner (14-22 % vs 3 % closed). "tol" (C147):
  turn UNTIL IT WOULD STRETCH (the pull's rule; "deg" is then the most): without it the turn goes the full "deg"
  whatever it costs. A point "piece:@closure" names that piece's vertex of the closure's top fastened pair (a front's
  roll line runs from it to the neck point: {"about": ["front.L:@front", "front.L:neck"]}).
- `{"smooth": {"pieces": [...], "lam"?, "rounds"?, "tol"?}}`: a hand flattening ripples. In the brushed pieces it
  alternates two moves: each vertex moved toward its one-ring centroid along its normal, then the pattern solve with
  everything outside held. It stops at the pull's stretch rule, or when the roughness stops dropping.
- `{"smooth": {"border": "piece:a..b..c", "spline"?, "lam"?, "release"?}}`: a BORDER smoothed into one swoop (C145;
  Joe: "one continuous swoop instead of three different angles"). The border is walked along the boundary, e.g.
  `collar:leftTopEdge..topMid..rightTopEdge` (point -> CB -> point). Each round it is drawn toward ONE least-squares
  spline (10 knots) and the rest re-solved, until it would stretch or its kink stops dropping. The 25 mm at each end
  stays put. Local neighbour averaging stalled after 2 rounds and roughened the collar. "release": pieces freed from
  the region holds for this op (the collar's fall from its hug; grips stay held). The collar's side-view kinks went
  21 / 27 -> 10 / 20 deg (the spike's sp10: 12 / 12).
- `{"smooth": {"pieces": [...], "near": ["piece:point", ...], "radius"?}}`: a LOCAL smooth within `radius` (40 mm)
  of each point, its stop read there alone. A band-end turn buckles the free collar tips (crumple p95 0.23 mm) and a
  whole-collar smooth doesn't see them; round each point they come back to the closed collar's 0.06-0.08 (C146).
- `{"push": {"pieces": [...], "gap"?}}`: the body as a floor for these pieces ONLY: the fronts, once the throat is
  opened, sink into the chest; pushed off they lie open with soft folds. Never every piece: a push dented the band.
- `{"relax": {"iters"?}}`: the free cloth relaxed against its pattern (nothing gripped).
- `{"hold": {"pieces", "within_deg"?, "feather_to"?, "feather_pieces"?, "of"?: "back" | "front", "center"?, "at"?}}`:
  Hold only a REAL support (C190: shoulder / neck contact, a sewn seam, a fastened closure, the layer under), soft
  and named; a hold standing in for gravity makes pinches, cords and rigid-grip creases. "feather_pieces" feathers only those (the BAND, not the collar's fall: feathering the fall too made an S of the
  collar's edge, in-out-in to the tip; band only gives one arc, C146). Keep a region
  where it is NOW for every later op. With `feather_to` (deg), the band beyond `within_deg` is FEATHERED: after every
  later pull it is drawn back toward where the hold found it, by a share fading 1 -> 0, then pinned and re-solved
  (3 rounds). A hard border kinked the collar's edge (29 deg at the border); held to 70 deg and feathered to 130 the
  kink fell to about 20 deg. Example: the collar + band within 70 deg of CB round the band's centre,
  feathered to 130, so the collar hugs the neck at the back and sides and only the front flares (C144). Relax first:
  holding the unrelaxed closed collar locked in its strain (p99 7.5 vs 6.1 %). Unheld, the opened front's slack
  spread round the whole ring: the fall stood 8 / 14 mm further off the neck at CB / the side.
- What a pull or turn gripped stays where it ended for the later ops. A pull that grips it again picks it up ("pull
  the points, move the collar's inner corners apart 6 mm, pull the points again").
- A grip overlapping held cloth is refused (the two fight: 280 % in the shirt spike).
- free: the pieces that may move (default: the gripped, brushed and region-held pieces). hold_below:
  "closure:front" (that closure's top fastened button) or "piece:point" also holds the free cloth below it.
- Returns:
  - clay + diag;
  - per op: how far each handle went (mm, steps), what stopped it ("stretch", or "max_move": something it should
    pull against is free), the stretch p99 (start / least / end) and the smooth's roughness and stretch;
  - crumple p95 per free piece, fit -> styled (layered flaps read ~2 mm in the fit already);
  - each pulled point's tip (crumple, stretch max, twist, folded faces near it) beside the fit's (the library also
    reads an edge's side-view swoop: garment_pull.edge_turns);
  - the result npz and the folder for review_view.
- Known answer (tests/test_garment_pull.py): Simon's shirt on wf_simon, closed fit,
  `free=["collar", "stand", "front.L", "front.R"], hold_below="closure:front"`. Ops: band ends turned 30 deg about
  stand:<s>BottomHinge..TopHinge toward "side"; collar points `collar:<s>TopEdge` pulled {"side": 1, "out": 0.3,
  "up": 0.3} from `collar:<s>TopHinge`; collar + stand smoothed. Result: points 142 apart, 64 / 60 below HPS, collar
  crumple p95 0.28 mm, tips as clean as the closed collar's. The hug (the spike's f2, the best read so far): relax,
  hold stand + collar within 70 deg of CB feathered to 130, band ends turned 40 deg as `stand:<s>BottomEdge..<s>TopCf`
  areas, points pulled {"side": 1, "out": 0.3}, the outer edge smoothed as a border (fall released), smoothed.
  Result: points 144 apart, 73 / 73 mm below HPS, the fall 72-73 mm off the neck axis at CB / the sides (closed
  67-68), band corner 1.5-2.5 %, edge kinks 10 / 20 deg.
- Finish every styling with smooth + pull down (C174); a hand lets go after its move and what hangs free drops (C199).
- Judge it like a fit: clay + diag beside the reference, one view per review_view. Too far or not far enough: change
  the direction, the sequence or what is held, never the solver, and never a stiffness that stretches a thread (C195).

### `dress`

`dress(name, garment=None, spec=None, state=None, quality=None, replace=False, wait=50.0, note='', force=False)`

REFUSES without a pattern_check PASS for this exact pattern + body (the text says what to run; `force` skips
only the stage 1-3 checks, never the pattern gate: its override is the logged HIFIPUSHIE_SIM_WITHOUT_PATTERN_GATE).
A sim is optional, a wrinkle source after the form fit is judged; never close or hand-finish after it.
Put a garment on the model and simulate it: drafted to the body's measurements, sewn, settled by Blender's
cloth, cleaned up (guide(topic="cloth") is the workflow). Garments live in spec["cloth"][garment].
spec: the garment (merged into the stored one key by key, null deletes; replace=True replaces it), e.g.
  {"pattern": {"from": "simon", "ease": {"chest": 0.12}, "length": 0.15}, "fabric": "shirting", "color": "#8fb3d9"}
  Keys: pattern (from: a design in cloth_designs.json: simon (shirt), carlton (coat); ease per girth, length,
  sleeve_length, options, measurements (a fixed size instead of made to measure), alterations), or own pieces +
  seams (a tablecloth is one piece wrapped "flat"), fabric (preset: shirting, jersey, linen, denim, wool_coating,
  or {"preset", overrides}), color, roughness, state, quality, resolution (final triangle size, 0.01), coarse
  (the blocking sim's, 0.02), cleanup ({smooth, weld, clear, keep, seams (welded seams pressed flat)} or false),
  detail (seam/stitch/hem maps: {seam, topstitch, stitch, hem, buttons, thread} or false), closures (how its
  openings are fastened: an entry of a name is laid over the design's own key by key, so [{"name": "collar",
  "state": "open"}] is a shirt with the top button undone, {"open_above": mark} undoes the fastenings above a mark;
  see the guide). How a garment is WORN (a jacket worn open, a collar opened) is STYLING, not a sim: fit_garment
  fits it on the form and styles it by its wear's ops (worn_open + the kind's "open" wear; style_garment /
  pull_garment for more). A sim is at most a wrinkle source on a styled fit, never the way to open a front.
state: "worn" (default: sewn on the body and settled), "draped" (laid flat and dropped on the model's surface: a
  tablecloth, a blanket; {"drape": {"over": "model" | "body"}}), or "hung" (dressed first, a hanger put inside
  it under the shoulders with its hook through the neck opening, the body taken away: it settles onto the hanger,
  nothing pinned; {"hang": {"hanger": {"kind": "wood" | "wire", "width", "bar", "slope", "clear", "rise"},
  "rail": {"length", "radius", "posts"} | false}}). The report's "hanger" line says what carries it.
quality: "draft" (one coarse 2 cm sim, ~1 min: judge fit and big shape) or "final" (default: the coarse sim, then
  refined at 1 cm and cleaned up, ~3-5 min).
backend (spec key): "blender" (default, local), "zozo" (ZOZO's contact solver: intersection-free, strain
  limited; one sim at `resolution`, placement "smooth"; on the local GPU, or through your own command in
  $HIFIPUSHIE_ZOZO_REMOTE; `zozo` = solver options; judge at "resolution": 0.02 on a laptop GPU), "file" (the job
  folder is written and its out.npz waited for) or "remote" ($HIFIPUSHIE_CLOTH_REMOTE runs the job folder): see
  guide(topic="cloth_sim").
The sim runs in the background (one at a time on the machine); this waits up to `wait` s and returns either the
report (when done) or the progress. Call dress(name) again (no spec) or look_cloth to see where it is: a sim
already running or cached isn't started again. Returns the save, then per garment: status, report.
Before a sim starts, the workflow's stages 1-3 are checked (design sheet, pattern, construction: the same as
check_garment); hard failures stop it (the spec is still saved) unless force=True. A day of solver tuning once
chased what were construction faults: fix the pattern first.

### `look_cloth`

`look_cloth(name, garments=None, views=None, strain=True, size=640, focus=None, zoom=0.4, textured=False, body=True, save=None, result=None, props=None, diag=None)`

diag (DEFAULT on): the diagnostic sheet of the simulated garments together (diag_render: panels + seams + turned, then strain + layers; diag=False none, a mode list one row, a list of lists your rows), flat emission colour so a kink, a flap turned into the body or a shirt through a jacket is obvious where clay shows only shading; single views are kept for review_view. Not drawn for close-ups (focus) or a carried result. The text ends with the next step: judge beside the reference (or set one).

Garments worn under another are drawn laid under EVERY garment above them (jeans under the sweater and the coat). props: the model's parts drawn with the body (default every non-shell part with its own elements: a lanyard, its badge, laces), each meshed in its own close-up box fine enough to show a 1.6 mm card; [] = none.

Look at the model's simulated garments (10-40 s): clay renders on the body (views from front, side, back,
three (3/4 front), three_back, side_r; default front, side, back, three) and a strain map row (blue slack, green
fine, yellow at the fabric's limit, red twice it), with each garment's report: the verdict (CORRUPT = tangled or
crumpled cloth, TOO SMALL = negative ease, STRAINED = past the fabric's limit on the body), ease per girth from
the pattern and on the body, integrity (crossings, crumpled pieces, where), surface numbers (crinkle, fold
depth: sim -> after the clean-up) and the clean-up.
focus: [x, y, z] or "garment:piece" (e.g. "shirt:collar") for a close-up `zoom` m across. textured: EEVEE with
the sewing detail maps (seam grooves, topstitching, hems, buttons) instead of clay; use it with focus.
A garment still simulating reports its progress instead (dress starts sims).
result: a cloth job's out.npz (e.g. from a GPU box) applied to the one garment named instead of its cached sim
(clean-up, report and renders as usual; not cached).

### `garment_reference`

`garment_reference(kind=None, detail=None, principles=None)`

The clothing knowledge base (garment_kb.json): garment kinds (fit ease bands, default details, sewing order),
detail choices (collar, cuff, sleeve_placket, front_closure, placket, waistband, fly, skirt_closure, pockets, hem,
yoke, darts, pleats, back_vent, belt, lining, shoulder, topstitch) with what each is made of, its seams, fold
lines, interfacing, the dimensions a tailor works to and the evidence checks that prove it's in a pattern; fabrics
with physical numbers; what each draft source (simon, carlton, skirt_block) can and can't make; the numeric
targets a simulated garment is judged by. kind: one kind's entry; detail: one detail kind's choices. No args: the
index.
principles: how to DESIGN a garment that has no ready-made draft (block + operations): "blocks" (the basic
patterns and the rules they are drafted by), "operations" (dart moves, slash and spread, style lines, extensions,
facings, collars from the neckline, sleeves into the armhole: what each does and what it keeps matched),
"derivations" (per garment category: which block, which operations, why; or one name, e.g. "blazer"), "rules"
(ease, balance, grain, shaping, seams, proportions), "all".

### `release_garment`

`release_garment(name, garment, release=None, submit=False)`

WORN OPEN = the closed fit + ONE release sim (Joe 2026-10-20): fits the garment CLOSED on the dress form, then
writes one short cloth job STARTED from that fit (rest = the flat pattern, the closure in `release` (default
["front"]) not sewn, the under garment pressed under as a collider, neck pieces held, 2 s of gravity + 1 s settle)
and preflights it. submit=True runs it (rented when HIFIPUSHIE_GPU=bundle: counts against the $5/day; refused
without the pattern gate's PASS). Returns the start report, the preflight and, after a run, how far each piece
moved from the fit. Details: cloth_release's docstring; docs/state/cloth_release.md.

### `arrange_garment`

`arrange_garment(name, garment, pins, keep=False, pull=None, release=None, hold_ring_mm=0.0, submit=False)`

ARRANGE a worn garment BY HAND (Joe 2026-10-20: as a man settles his coat after sitting): an openness or pose
physics alone won't give is placed, never drafted or fitted in. The release job (release_garment) plus SOFT pins:
each pin {"at": "piece:point" | "piece:a..b" (the piece's border between two named points), and "to": [x, y, z]
| "by": [dx, dy, dz] (+ "by_end" for an edge: blended along it) | "targets": [[x, y, z] per vertex], "name"?}
pulled to its target over 1 s of gravity (the under garment, real friction), held 1 s, then let go for a 1 s
settle. Reports per pin how near it got, the SPRINGBACK once let go and the stretch near the pins vs the rest.
Springback over 10 mm: rerun with keep=True (light pins kept: the result is recorded "placed by hand").
pull: the pins' spring (default cloth_release.ARRANGE_PULL); hold_ring_mm: also hold the bodice that close to
the held neck pieces (their seam can't part). submit=True runs it (rented when HIFIPUSHIE_GPU=bundle).
Details: cloth_release's docstring ("ARRANGE"); docs/state/cloth_release.md.
