# Clothes: tool reference

The cloth tools' full parameters and behaviour, one section per tool (guide(topic="<tool name>") returns one).

PICTURES ARE FOR SHAPE, TEXT IS FOR NUMBERS (C288): judge a look for shape (curves, which way an edge runs, which edges
share a colour); take every number and name from the tool's text answer, never read one off an image.

## Tool reference

### `chain_garment`
`chain_garment(name, garment, wear=None, opening=None, wait=50, rebuild=False, waive=None)`: THE start of every garment: to dress a character, to fit or drape clothes on a body. Reads the drafted pattern and the
body, never a fit. Built straight into the garment record's style plan (step 2, T7): each closure's pairs are tied as step 2's
`ties` say (which fastenings are done up: by number from the top, or a zip's share; never a named state, C391; any set,
none included: ONE build for every garment, an edge neither sewn nor tied is free, C399), the plan's collar_points_apart its spread; give wear / opening only without a plan (a contradiction is refused). Stages: stiff parts first, in the order of what holds what (a band, a stand or a collar on the neckline, a fall on its band), as chains of their cut lengths, stiffness from the
pattern's interfacing, resting on the high points; cuffs as stiff rings on the limb's own section; the soft pieces wrapped on a
garment-sized section and solved as a network with the body as a floor; surfaces filled between the chains; a band whose own closure is undone is
opened before any soft cloth (its sewn front limited by its cut distance to the topmost tied front pair, by nothing when none is
tied), and the plackets fold along a solved crease through that tied pair only; every fold step 2 plans (a lapel rolled to its
break, a cuff turned back) is then turned about the draft's own fold row to its turn_deg and lies on its lies_on, lengths exact,
gated per fold (stage "crease": turn within 15 deg, never sunk inside; chain_crease.py, C401); then the STRUCTURE check reads the build (never a hang) against the garment record's style plan (step 2's rows and numeric bends, each judged by its kind; C286) plus general rules: the fall lying, turned over its stand, each closure in its planned state (and a closed one meeting), the hem level left to right, the soft cloth not crumpled (soft_cloth_smooth: each soft piece's bump p90 <= 2x a smooth 40 mm tube's at its mesh size). No style plan, or a row with no build reading yet: UNMEASURED by name (waive with a reason or add the reading). A FAIL ends the job "structure_failed": the answer lists each failing row with its target, source and change: (what to change in your draft, or the build stage to fix); waive={row id: why} re-reads the saved build (no rebuild) and accepts those rows by name (PASS_WAIVED). After a pass the job stops at "awaiting_approval" (step 7a of the garment record: nothing is hung that wasn't approved built): the answer gives the sheet and the exact approve command for Joe or the coordinator; an agent never approves. Once approved, the same call resumes the hang from the saved build (HIFIPUSHIE_PRESIM_APPROVAL=optional: it hangs straight away). Then the soft cloth hangs under gravity (ZOZO, 5-10 min) with the stiff parts held; lengths last. The hang's gate (step 8): any face past the thread cap FAILS, with back to step 5 and a change: line; the cap is the cloth's, never a setting. wear: "closed" or
"open". opening: only with "open": collar points this many neck widths apart (default 1.7, 1.0 .. 2.6). A job: the call starts it
and answers with its stage after at most wait s (0 .. 280); a build takes 2-10 min, then the hang runs, both slower on a loaded
machine. Call again with the same arguments for the stage: that never starts a second build. Once built the answer carries the chains,
threads, seams and band numbers. A finished job answers with its result; a changed pattern starts anew; rebuild=True starts over.
Every answer's next: names the call. A worker that dies reads as failed, not as running for ever. Refuses: an unpassed pattern gate (next:
pattern_check); a line whose length can't hold (named, next: change it in your draft, draft_pattern); a start the solver would refuse (a tool
fault, named: report it). Nothing is pushed, cut or loosened to get past a refusal.

### `look_chain`
`look_chain(name, garment, wear="closed", focus=None, size=640, reference=None, save=None)`: the BUILD until its structure
check passed and the hang ended, then the hung result (the text says which). focus: none = whole figure, four views on the body; "neck" = the collar close, on
the body; a piece's name = that piece alone, large, four sides. Sewn seams are joined and every piece faces outward.
reference: an image path shown beside each view. Judge each view yourself against the reference, then review_view one view per call.

The full documentation of this topic's tools: their MCP descriptions are the short form. guide(topic="<tool name>") returns one section. These tools are the `cloth` domain: run them with call_tool(name, args); find_tool(\"<job>\") gives each one's parameters and an example call.

### `garment_record`
`garment_record(name, garment, sheet=False, step="")`: (step="N": that step's saved output in full, to retake it changing only what's refused) the garment record (src/hifipushie/garment_record.py; the steps:
docs/state/garment_steps.md). One file per garment, workspace/<model>/garments/<garment>.json: per step its output (or a
pointer), status, gate rows, reference, look and, on a FAIL, back_to. pattern_check writes step 4, chain_garment steps 5, 6
and 8, look_chain the build's look (6) and the hung garment's look (9). A write to a step whose previous step isn't ready
is refused by name; a changed step makes the later ones stale. Approvals: `bin/approve add garment
<model>.<garment>.<step> <record>#<digest> <sheet> joe|coordinator` (the answer prints it); they hold while the digest
does. Step 7a's approval is required unless HIFIPUSHIE_PRESIM_APPROVAL=optional. sheet=True renders the step-0
reference beside every look plus a status tile; every step's status is also in the text answer.

### `body_tape`
`body_tape(name, measurements=None, garment="", landmarks=False, add=False)`: garment step 3, measuring the model's base body BY NAME
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
- {"name", "kind": "girth", "through": [A, B], "around": "arm.L"}: a tilted girth round a limb's root, in the plane
  through two landmarks facing along the limb (an armhole: through shoulder_point.L and side_armpit.L; stepped down
  under B, and said, where the plane first cuts into the torso).
- {"name", "kind": "sum", "of": [names taken in the same call]}: a measurement no one tape can take, added from its
  parts (an armhole: its front and back arcs over the shoulder). Step 3 is written only when it holds every name step 1
  calls for (a missing one is refused by name); take the draft's own measurements in the same call.
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
add=True (with garment): step 3 is kept exactly as recorded and only the measurements given are taken and added (a
draft that needs one more measurement; C381).

### `garment_plan`
`garment_plan(name, garment, step, plan, look=True)`: steps 0, 1, 2 of the garment record (every
refusal ends with that step's full form), for ANY garment. You are the intelligence: look at the picture, know the construction;
the tool is the structure, the refusals and the look. step="read" (0): kind; views [{image, view, scale?}]; cloth {name:
{fabric (a garment_kb fabric fills gsm / thickness / bending length) or the numbers + source, stiffness, colour [r,g,b] or
{at: [[u, v]], view} (sampled), print {kind, repeat_mm, source}, grain}}; fit {view, landmarks {name: v | {at, from: how inferred}}, widths [{at (a landmark, or a garment height: 'hem'), garment [[u,v],[u,v]], body, body_from}] at that row, heights [{name, at: v, on: torso|leg|arm}]} (RATIOS on the picture, applied to the model; seen edges measured on the picture; landmarks = the points the landmark card draws, checked against each other; across and up-and-down scales agree, or scale_why). step="parts" (1): centre (u, the garment's centre line: X.L pieces / details / seams bring their X.R mirror),
pieces {name: {what, cloth, seen: seen|occluded|inferred, from (the convention, unless seen), build: full|simplified|omit,
why, stiff, layer, where {view, outline}, edges {edge: [i0, i1] spans tiling the outline} | [names]}}, details {name: {what, on, cloth, follows ["piece:edge"] (a trim along edges), count, seen, build, where {view, at | outline |
outlines (one per instance)}}},
closures {name: {what, pieces, details}}, seams [{a: "piece:edge", b, kind, caught?: ["piece:edge" sewn
into the same line], length: {body: [names]} | {style: {ratio, of: a body name | "piece:edge" | [step-0 height, another],
source}}}] (never mm read off the picture: it isn't the model; value_mm only with fixed: why); the answer lists the body measurements step 3 must take. step="style" (2): ties {closure:
{fastened: [numbers from the top, 1 = the top], of: how many, source} | {span: [from, to] share of its length done up (a
zip; 0 = top), source}} for EVERY closure, fastened [] = none done up (build straight into it; never build closed then
style open),
bends [{id, on: piece, fold: <crease name, declared on that piece at step 4>, turn_deg 0..180 (180 = folded right back), lies_on: piece | body | free, trace?, source} (a fold: collar roll, lapel roll to the break, turned cuff) | {id, on, what: row kind, target {value, unit, of?}, source}] (a bend in words only is refused, C392), pose {name, source}, rows [{id, what, target, source, note?, view, at}] (what = a structure_rows kind, refused otherwise with the list: collar_points_apart, collar_tilt, collar_rise, collar_points_drop, collar_height, fall_back_width, v_depth, front_edge_plumb, hem_front_back, sleeve_end, cuff_ease, garment_length, cutaway_drop, trim_row_count, trim_row_pitch, trim_lines_apart, not_judged; bases neck_width, shoulder_width, closure_length; a ratio is OF the kind's base; a px target becomes a ratio of the base row on its view, else mm by the view's scale; a numeric bend names its kind too)
(what the photo judges: the structure gate's targets), traces [{id, what, view, points [[u,v],..] (>= 4), corners
[indices where it turns sharply], source}] REQUIRED (the reference's key edges: hem, front edges, collar, sleeve ends,
roll_line, trim...; each checked on the picture's own edges, a run off every edge refused unless the trace says why;
step 6 compares the build's outline with them); a kind step 0 measured (garment_length) names its step-0 height
({height: 'hem'}); not_judged takes no target; the look is in the picture's own px with a ruler; the fit view's body marks are step 0's landmarks
(body_marks only for another view). Every refusal ends with the full form and the row and trace kinds, each saying
where it is measured. Refused by name: a seam on a piece not in the inventory, a built
piece with no seam, a target with no source, a state for a closure the inventory lacks. look (default): drawn over the
reference: seen solid, occluded dashed, inferred dotted, omitted grey, judged rows yellow; saved as the step's look.
Every `at` / `outline` / `points` is PIXELS of the named view's image (u right, v down from its top-left corner), never
0-1 fractions: values all within 0..1 on an image wider than 2 px are refused (multiply by the image's width / height).
Body measurement names in seams' `length.body` are body_tape's: FreeSewing's names the tape takes, or names you define
in step 1's `define` {name: girth|arc|length|height} (measured by that kind at step 3); others are refused with the
closest valid names. Rewriting step 1 carries steps 2 and 3 forward when they still validate against it (re-stamped,
said in the answer); only what no longer validates goes stale, with the reason.

### `garment_toile`
`garment_toile(name, garment, declarations)`: garment step 4 (drape first), THE TOILE: the garment's 3D surface on the
body, as a draper pins muslin on the stand before any pattern exists. Needs steps 0 (fit levels + planned girths,
heights), 1, 2 (traces) and 3 (tapes: neck among them). The toile = the body offset by step 0's ease at each fit level
(calibrated: each level's tape equals the plan), with the parts YOU declare (never inferred from a garment's name):
- `parts`: any of sleeves, opening, lapel, pad, collar. `hang_from`: a step-0 fit level the garment drops straight from (a
  jacket from the hips: flare to the lowest level's girth at the hem), or "none".
- `armhole {length_mm}`; `sleeves {ease_mm: [top, wrist], crown_mm, hem}` (hem: a step-2 sleeve-end trace, its length past the picture's wrist
  carried onto the model's wrist, or a step-0 height; smooth tubes
  through the arm's sections, the armhole a cone from the shoulder joint); `opening {closure, edge, lap_mm, buttons}`
  (closure: a step-1 closure, built in the wear state its step-2 ties give: none done up = open, the fronts parting on
  the traced edge, the roll as traced; all = closed, lapped by lap_mm; none recorded refused; edge: a step-2 trace); `lapel {roll, top, width_mm}` (traces; turned about the roll line); `pad {thickness_mm}` (its own part);
  `collar {stand_mm, fall_mm, notch}` (needs lapel; heights at CB read off the reference, notch a step-2 trace from the
  gorge corner). With a collar the lapels and the collar are ONE part "flap" turned back about ONE roll line drawn on the
  toile (break -> gorge point -> beside the neck at the notch trace's top -> CB at the stand's height); the stand leans on
  the neck inside it, the fall lies out over it; step 5's gorge mark splits it into collar + lapels (toile_flap.py).
A missing key is refused by name. Writes `<look dir>/toile/` toile.npz (each part "<part>:V/F", the sleeve axis, the
armhole, the roll line), toile.json, toile_sheet.png, and step 4 (output, gate rows, look). Gate rows: girth per level
(+-6 mm), clearance (nothing inside the body), closed (one surface, its free loops), neck (no stand: the back no higher
than the side neck points + 3 mm), outline vs step 2's traces LIKE WITH
LIKE (the picture's body and pose are not the model's): a side as its profile (the width is the girths'), a hem as its
height, a sleeve end as its length past the wrist, each from its own wrist (signed, +-10 mm); front edges and roll lines INFO, the collar's
row `collar` (roll and landing at CB). Then step 5 marks the seams on it, step 6 cuts and flattens it
(the flat pattern, draft_pattern's form, gated by pattern_check).

### `garment_mark`
`garment_mark(name, garment, declarations)`: garment step 5 (drape first), MARK: the seams drawn on the approved toile as
body lines, each cut exactly into it (src/hifipushie/mark.py's docstring is the spec). `marks`: in order, each
{name, line {kind, ...}, region, into [piece where g < 0, piece where g > 0]}; region "toile" at the start, else a part
an earlier mark made. Kinds: armhole (the toile's cone: [body, arm]), centre_back ([right, left]; the front stays open),
panel {after: a step-2 panel, above: "shoulder"} (step 2's share at every girth, by arc round the toile's section; the
shoulder line above the underarm: [ahead, behind]), shoulder ([front, back]), under_sleeve {fore_in_mm, hind_in_mm} (the
tailor's rule: [top, under]), level {at, offset_mm} ([below, above]). A ".L" mark mirrors to ".R". `absent` {step-1
piece: why} (cut later, e.g. a collar); `runs` {"piece:edge": front|back|top|bottom} when two pieces share two seams.
A mark that doesn't cut its region into two parts is REFUSED by name. Rows: marks, separate, pieces, seams (+ the pairs
step 1 doesn't name). Writes `<look dir>/mark/` mark.npz, mark.json, mark_sheet.png; step 5.

### `garment_cut`
`garment_cut(name, garment, declarations=None)`: garment step 6 (drape first), CUT AND FLATTEN (src/hifipushie/cut.py's
docstring is the spec): every marked piece flattened with least distortion; strain per piece and where (compression: a
dart wanted; stretch: ease); edges named by step 1's seams, `free` {piece: {edge: top | bottom | side | [classes]}} names
the toile's own edges (hem, neckline, opening, sleeve end); plain seams trued; `ease` {"piece:edge": [lo, hi]}. Pieces
the toile turns or hides are made here (cut_made.py, in this order): `flaps` {toile part: {onto, fold, edges}} unfolds a
turned flap (a lapel) across its roll edge onto its piece (cut_flap.py); `layers` {piece: {host, line: [[edge, mm,
toward], ...], keeps, edges, inner}} traces a facing / canvas off its host's flat (cut_layers.py); `collar` {pieces,
neck, outer, end, fold, fold_on} cuts the collar step 4 draped on the toile and unfolds its fall about the roll line
(cut_collar.py; its heights are garment_toile's collar part). The flat pattern (draft_pattern's block form, each piece with
its 3D outline) gets today's flat gate. Writes `<look dir>/cut/` flat.npz, pattern.json, cut.json, flat_sheet.png,
cut_3d.png; step 6.

### `draft_pattern`
`draft_pattern(name, garment, design, declarations, options=None, sa=10)`: garment step 6 (the flat pattern; it was step 4 before drape first), YOUR OWN pattern (no published
design, no recipe; src/hifipushie/draft_own.py's docstring is the spec). Needs steps 1 (parts, seams) and 3 (body_tape).
- design: a FreeSewing 4 ES module. Import blocks and extend them: `import { Design } from '@freesewing/core'`,
  `import { back, front } from '@freesewing/brian'` (also bent, jaeger, carlton parts; `@freesewing/library`: sleeve,
  topsleeve, undersleeve). A part: `{ name, from: back, hide: { from: true, inherited: true }, after, measurements,
  options, draft: ({ points, Point, paths, Path, snippets, Snippet, store, measurements, options, part }) => part }`.
  Each visible part draws `paths.seam` (the closed sewing line, mm, y down); hide the inherited paths you don't sew.
  Button marks: `snippets.btn1 = new Snippet('button', point)`; NOTCHES are `new Snippet('notch', point)` snippets,
  never outline points: the seam check matches each to its partner's (within 4 mm), so move or drop a base's notch
  you no longer sew to. A part made `from:` another does NOT inherit its `after:` (FreeSewing): list the parts it
  must be drafted after again, or the draft order breaks. End with `export default new Design({ parts: [...] })`.
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
  "<name>.m"), "pair": true (a piece worn on both sides, step 1's X.L + X.R: declared ONCE as pieces.X with edges.X,
  cut as a mirrored pair; "mirror" only flips one piece and copies no edges), "mirror", "cut", "grain" (degrees, or "lengthwise" / "crosswise" / "bias"), "place": {"to": "torso" | "arm" | "neck",
  "side": "front" | "back" | "side"}}} (row place reads each piece's place off its own length tapes and FAILs a contradiction); `edges` {piece:
  {edge: "a>b" | "a>via>b" (outline points) | {"path": a path of the part}}}; `seams` [{"a": "piece:edge" | [chain in
  order], "b": ..., "ease": [lo, hi] (a over b - 1), "why"}] (every step-1 seam; a seam sewn to several edges is one
  chain: a two-piece sleeve's cap edges against the armhole's front, side and back as ONE seam [cap chain] = [armhole
  chain], when its seams don't land on the body's); `stiff` [piece]; `folds` [{"name", "piece", "line": [p, q, ...] (outline points or snippets) | edge | a path of the part by name (a curved fold: a collar's roll line drawn as a path), "kind": "press" | "roll"}] (a step-1 seam of
  kind fold is a fold named like its edge); `closures` [{"name", "kind", "over", "under", "edge": {"over": edge,
  "under": edge}, "at": [[hole, button]]}] (holes on `over`, the piece that laps on top: a man's left front; buttons on
  `under`; each a SNIPPET's name, `snippets.btn1 = new Snippet('button', p)` -> "btn1", or a
  point ON the outline; a point inside the piece isn't a mark: C376) (an edge: a declared edge name, or "pointA>pointB" /
  "a>via>b" along the piece's outline); `vents` [{"name", "over": "piece:edge", "under": "piece:edge"}]: a vent's two
  sides (cut WITH their extensions), each edge from the hem up to the vent top where the seam starts; open below it, the
  seam sewn only above; the girths row counts the overlap once (draft_vents.py); `moves` [{"seam": ["A:edge",
  "B:edge"], "at": [[mm along A's edge from its start, mm toward B], ...]}]: a seam LINE moved between the two pieces it
  joins (a side body too narrow for step 2's shares): the converter re-cuts both, the seam stays one length, the edge
  beyond each end (armhole, hem) passes its strip across; never re-cut pieces by hand in design.mjs; the panels row's
  FAIL writes the entry (draft_moves.py); `omit` {piece: why} (a built step-1 piece you don't cut); `darts` [{"piece",
  "legs": [edge, edge]}]: a dart OPEN on the outline (the seam path in to its tip and out), each leg declared
  "outline point>tip", sewn to each other; a dart drawn INSIDE the piece (a fish dart, a dart ending in a pocket
  mouth) is declared as drawn, never cut open by hand: {"piece", "inside": <its closed path of the part>, "release":
  [part points..., named outline point]}: the tool cuts it through along release (through a pocket mouth to the nearest
  seam, or straight to it) and sews dart and cut shut (C416);
  `tapes` {piece: [step-3 tape names] | {edge: tape}}: the step-3 tapes EVERY piece was drafted on (a pair's base name
  covers both sides); step 5 starts the piece on them, never from a rule. An edge map names the tape an edge laid on the
  body lies along: a STIFF piece sewn to soft cloth names one for each sewn edge (a collar's neck edge on the tape of
  the line it sits on: a jacket's runs back neck, via the shoulder, down the gorge; measure that line in step 3 with
  body_tape if it isn't there). Row piece_tapes FAILs a piece with none, or a name step 3 hasn't taken (back to step 3).
  Row girths (G1) walks every girth the tapes name round the pieces it crosses, each level placed by a LENGTH tape the
  piece names (so name both: its girths and a length from its top past them), and holds the pattern to the body +
  step 0's ease for that girth (15 mm or 15 % of the ease); a closure's lap comes off by its marks; a piece in the ring
  whose tapes miss the girth FAILs; where step 3's girth is another definition than step 0's (hips: FreeSewing's iliac
  crest vs the tape's own), the row checks on step 0's, at its level, and says both. Draft the ease the plan asks for:
  step 5 can't add cloth. Row panels: each piece's share of a girth as step 2 placed it (each share read off the reference or the convention body_panels, never typed; seams where
  the style wants them, not where the block put them). Row caught: an edge step 1 catches in a seam (a canvas) is
  drawn out to that seam's edge, the piece inside its host. Row turned_width: a lapel / cuff turned along a traced fold
  is as wide as the traces show. A seam far off its ease names the points its long side should end at;
  `marks` {detail: mark | [marks]}: WHERE each built step-1 detail sits (a closure's holes and buttons are its own marks: each on
  the piece step 1 puts it on): a
  mark = {"piece", "mirror"?: true (again on the .L <-> .R piece), and ONE of: "at": [{"point": name, "dx", "dy"} (mm, dy UP the piece: FreeSewing's y is -dy) |
  {"edge": edge, "mm" | "t", "in"}], "rows": {"edge", "count", "from_mm" | "from_t", "pitch_mm" | "pitch_t" |
  "to_mm" | "to_t", "in"}, "points": "button*" (the part's named points), "follows": ["piece:edge"] (a strip along
  edges), "path": [positions]}; positions only (size, kind, colour are step 7's). A measurement the design reads
  that step 3 lacks, or one the design sets, is refused: retake step 3 with it by name.
  Example: `{"pieces": {"back": {"part": "my.back", "fold": "x0", "place": {"to": "torso", "side": "back"}}}, "edges":
  {"back": {"side.L": "hem>armhole"}}, "seams": [{"a": "front.L:side", "b": "back:side.L"}]}`.
- Refused by name (nothing written): a step-1 seam with no drafted edge or not sewn, a piece not in step 1, a built piece
  not drafted. Else the flat gate: seams (each pair within its declared ease, else +-1 %), cut, sewn, closures (lapped
  edges within 1 %), planned_folds (every fold step 2 turns declared on its piece by name; every roll fold has a step-2
  turn: C392), seam_links (every seam's two sides within 3 mm over each link, read on the mesh chain_garment makes of the
  draft: what step 5 refuses, step 4 FAILs, C395), seams_crossed (no seam joins two points of one piece far apart: an
  edge declared the wrong way, or a chain [e1, e2, ..] whose edges don't each start where the one before ended; C403), truing (info), and SHAPE per role (draft_shape.py; each FAIL says `change:`): a stand / band's neck
  edge rises at its front ends (stand >= 0.24 x the neckline's front drop, jaeger; band > 0) and its free edge is shorter;
  a fall's outer edge >= 1.012 x its whole neck line (simon; an undercollar's neck edges, or a shirt collar's seam to
  its band); shape_fall_landing (draft_fall.py, C408): the fall's outer edge against the line it lands on, (fall - stand)
  below the neck seam at CB read off the collar's roll fold (or its band), walked on the backs' flat pieces (the fronts'
  necks at their own length: the collar turns with the lapel) + lift, within 4 % (too long: straighten the collar; too
  short: spread it); a sleeve cap 0.47-0.79 x the armhole depth (brian, bent); no
  straight edge sewn to a curved one. Name a stand's free edge `top`, a fall's `outer`, neck edges `neck*`. A piece's
  `role` (optional; else its name decides) is one of garment_kb's roles (collar_stand, collar_fall, ...); a layer sewn
  edge to edge onto a piece by the same edge names (its canvas, inner collar) takes that piece's shape: no role needed. An outline seen in the reference
  is TRACED from it: corners stay corners (a stepped cutaway is `line`s meeting square), curves stay curves (a stand's
  rounded front top corner), never approximated by one arc; a lapel's gorge and its width at the notch are read off
  the reference, not kept from the block (a block's square gorge, down then across, makes a notched collar a deep U where
  the reference shows one sloping line from the neck point to the notch); judge the sheet's outlines beside the photo. The sheet is shape only (one big name per piece, each seam pair one colour, legend S<n> = the
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
build can feel it). A closure's holes (on over) and buttons (on under) are its own marks; a zip's tape takes its declared edges. draft_pattern refuses a
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
in EEVEE (asset_export.preview), four views, a chest close-up and the texture sheet, each beside the reference (C288: shape and
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
(details.pkl) are their own meshes and materials. Weights: read off the body (rig_skin.skin_parts: the base body's own at its
surface), Mixamo bone names (rig_report.rig_bones); a detail takes its nearest garment vertex's. Gate rows (numbers in the text):
triangles <= budget; UV stretch (3D / pattern area per triangle) p95 no more than the drape's + 0.03, p5 no more than 0.10
below it (chords across folds); no open pattern edges; the weight check (LeftArm raised 45 deg: each vertex's distance to
the body changes <= 12 mm p95 where the body moved). Refused unless step 9 is approved (internally an approved 7a exports the
build; step 10 is then not written: the text says so). Writes <job>/export/<garment>.glb (+ _export.json, the look GLBs)
and step 10; the look is SHAPE: the GLB with the body in EEVEE (asset_export.preview), rest beside the reference, and posed.
LODs: it also writes `<garment>_LOD1.glb` .. `_LOD3.glb`, the SAME pattern re-grid at a coarser grid (never a
decimation of LOD0: that kinks and tears a garment), each at the role's clothing budget for that LOD (0.25 / 0.11 / 0.05
of LOD0: what the character's export gives a part below the neck), stiff pieces with fewer rows (4 / 2 / 1), the same
pattern UVs and maps, weights read off the body again on each LOD's own mesh. Details per LOD: a piece (one button)
smaller than 2 px at the LOD's switch size on a 1920 px screen is LEFT OUT, the others are simplified to the LOD's share
and seated on the LOD's cloth; the text says which, with the size that decided it. Each LOD is a line in the text and an
entry in step 10's output (`lods`: file, triangles, grid); a LOD with an open pattern edge fails the gate, a LOD over its
share is information. The last look is the LOD files, LOD1 at the top, the garment alone.
Then the character: `export_asset(name, out_dir, role=..., rig=True)` takes this file and its LOD files as they are.
Not done: the normal bake of the folds (garment_game.bake), layering culls (a shirt under a jacket), the bend check at the LODs.

### `pattern_check`

`pattern_check(name, garment)`

STEP 4's FLAT GATE AGAIN, on a garment drafted with draft_pattern. draft_pattern runs this gate itself each time you
draft; pattern_check re-reads the same gate from the saved draft (after a tool change, or when chain_garment says step
4's gate is not PASS) and rewrites step 4 in the garment record. chain_garment refuses a garment whose step 4 is not
PASS. A garment with no draft of its own is refused: draft it with draft_pattern.
Returns the per-row table, FAIL first, and "next:". A FAIL is fixed in your draft (draft_pattern), never here.

