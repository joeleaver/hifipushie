# Clothes: tool reference

The cloth tools' full parameters and behaviour, one section per tool (guide(topic="<tool name>") returns one).

## Tool reference

The full documentation of this topic's tools: their MCP descriptions are the short form. guide(topic="<tool name>") returns one section. These tools are the `cloth` toolset: enable_toolset("cloth") turns it on.

### `design_garment`

`design_garment(name, garment, design=None, spec=None, replace=False, note='')`

Stage 1 of the clothing workflow (guide(topic="cloth")): the design sheet, decided before any drafting, as a
pattern maker does. Stored in spec["cloth"][garment]["design"] (merged key by key, null deletes; replace=True
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
piece at one scale with its name, role, size, grain arrow, notches, buttons/buttonholes, fold lines (blue dashed,
with angle), interfacing (hatched), each seam in its own colour numbered on both sides S3a/S3b, a 10 cm bar, the
seam list with each seam's ease), plus the checks before any sim, failures first: every design-sheet choice
evidenced in the pieces and seam table (a turned collar has a fold line, a barrel cuff is closed and interfaced,
the fall covers the stand...), every seam's ease in its band (sleeve cap by kind, bands, plain seams), notches
aligned, ease against the body per girth inside the fit's band, every piece sewn to something, the details'
dimensions. Fix failures in the design sheet (design_garment) or the garment's pattern options before going on.
Next: check_garment(stages=["construction", "place"]).

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

### `alter_pattern`

`alter_pattern(name, garment, ops, replace=False, note='')`

A pattern maker's alteration on the FLAT pattern: ops appended to the garment key "alter" (replace=True replaces the
list) and applied in order after the draft (pattern.apply). Ops: slash_spread, turn, move, scale, slit, trim
({"length"} or {"match": [edges]}), and where this build has them (they land from the dress-garrett branches):
"true" ({"piece", "at", "keep", "deg": 90, "blend": 0.04}: the edge leaving point `at` bent so the piece's corner
there is `deg`, the kept seam unmoved: necklines / armholes meet the shoulder seam at ~90 deg) and "match"
({"piece", "edge", "to": [edges], "line", "ease"}: WALK THE SEAM, the pieces lengthened across `line` until `edge`
equals the summed `to` edges x (1 + ease): a collar's neck edge = its neckline). An op this build doesn't know is
an error and nothing is saved (the alteration is drafted and placed before the save). Each op that changes a default
carries "source" (where the number came from; the gate warns without one).
Returns the flat pattern sheet and every seam walked (A | B lengths, ease, notches off; truing junctions where the
build has them), then the next step: seams that don't walk -> "match" them; else pattern_check (the gate record is
per pattern, so any alteration needs a new one).

### `pattern_check`

`pattern_check(name, garment, refs=None, waive=None, views=None, size=480, diag=None, save=None)`

THE PATTERN GATE (codified C11): the garment drafted and placed on its body (no sim) and every cloth_checklist item
of its kind measured there: seam lengths / ease / notches, lengths and widths, design choices, the neckline
standoff; where this build has them, truing (junction angles), the collar draft and notch, flat tailor rows. Items
with no pattern-stage measure or no reference reading are UNMEASURED and block; drape items are SIM (judged later);
dress-form readings are INFO until the form is validated. The record (/mnt/data/hifipushie/pattern_gate/<key>.json,
keyed by the pattern's content hash + the body's) is what every sim checks: `dress` and every cloth job refuse
without a PASS for exactly this pattern + body.
refs: the reference reading (cloth_reference.read's output or its saved path). waive: {item id: reason} accepts a
FAIL / UNMEASURED row by name (recorded; PASS_WAIVED).
Returns: the FLAT pattern sheet (pieces, grain, notches, seam list with lengths and ease), the DIAG views of the
placed pattern (by default two rows: panels + seams + turned, then strain + layers; diag=False none, or your own
modes / rows), and the per-item table FAIL / UNMEASURED first, then "next:": on a FAIL the rows to fix and "don't
simulate"; on a PASS fit_garment. views (default front, three, side, back), size (px), save (PNG path prefix).
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
  openings are fastened AND worn: an entry of a name is laid over the design's own key by key, so
  [{"name": "collar", "state": "open"}] is a shirt with the top button undone, [{"name": "front", "state":
  "open"}] a jacket hanging open, {"open_above": mark} undoes the fastenings above a mark; see the guide).
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
