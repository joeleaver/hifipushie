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

### `dress`

`dress(name, garment=None, spec=None, state=None, quality=None, replace=False, wait=50.0, note='', force=False)`

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

`look_cloth(name, garments=None, views=None, strain=True, size=640, focus=None, zoom=0.4, textured=False, body=True, save=None, result=None, props=None)`

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
