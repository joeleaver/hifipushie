# Hair: tool reference

## Tool reference

The full documentation of this topic's tools: their MCP descriptions are the short form. guide(topic="<tool name>") returns one section. These tools are the `hair` toolset: enable_toolset("hair") turns it on.

### `groom_hair`

`groom_hair(name, groom=None, replace=False, stage=None, note='', style=None, strands=None, look=None, fuller=None, trim=None)`

Grow the hair's locks from spec["hair"]["groom"] (the designer's words and numbers) and save them.
Hair is curve locks (Bezier curves swept with a cupped lens profile) in the model's Blender scene, not part of
the SDF body; guide(topic="hair") is the workflow. Needs a head with face landmarks (a `base` head) or a
groom "centre" joint.
groom: a patch merged into the stored groom first (objects merge key by key, null deletes), e.g.
  {"volume": {"top": 0.04}, "parting": {"side": "left", "offset": 0.03}, "drawn": [...]}.
  Keys: hairline (front, temples, sideburns = m below the FOUND ear's top, nape, ear = m over it, ear_from "mesh" | "brow", front_points), parting (side, offset, length, line, flat,
  full, depth), volume (front, top, crown, sides, back, nape: m of hair over the scalp; ramp, across, crest: x of the top's crest, taper: {from, to, floor} short tapered sides and back), length
  (per region, m), flow (per region: {"back"|"down"|"up"|"away"|...: weight}), tiers ({tier: {width, thickness,
  spacing, where, length, taper, belly, root, ...} | false}: strip = shingled side/back strips, gap = covers
  bare volume, big/crown = the generated top, fill, edge), drawn (big clumps drawn by hand: [{"name", "top":
  [[x, y] m from the head centre seen from above, root first] | "azel": [[az, el] deg], "width", "thickness"?,
  "taper"?, "lie"?, "root"? (width at the root: 0.1 grows out of the layer), "climb"? (m the root takes to rise),
  "to_hairline"? (inset m or {inset, reach}: the edge laid on the hairline), "split"?}]; name rows stem+number so
  an under-layer clump fills between neighbours; patch one by name: {"drawn": {"sweep2": {...}, "qf*": {...},
  "old": null}}), hairline_edge ({inset, reach} for every clump near the hairline), volume.edge_sink,
  parting.front, grey, noise, seed.
  tie ({"at": [az, el] deg (az 180 = the back, el up), "out": m off the scalp, "gather": {rows, locks, lift,
  width, uneven}, "tail": {length, fullness, locks, stiff, uneven, taper, coil, plait}, "escape": n wisps the tie
  missed, "band": m, "curtain": {span deg, to deg, over deg, lift m}: the front from a soft part sweeps down and
  out over the temples and the ears' tops before it turns back (a loose low ponytail; without it every lock runs
  straight back), "frame": {count a side, az [a0, a1], length [l0, l1], width [w0, w1], wave, wavelength}:
  styled face-framing pieces in front of the ears, soft and wavy, mixed lengths}: hair gathered over the head into a
  tie and a tail leaving it; parting.side "none", or "centre" with a short soft part (length 0.04, width 0.006,
  depth 0.4: no bare furrow running back).
  A LOW or SIDE tie (a low side ponytail): gather {"toward": "crown", "rows": 4, "locks": 80, "reach": 0.9,
  "inner_roots": 0}: by default the inner rows root on the way to the tie, which for a low side tie leaves the far
  side of the top to the hairline row alone (a headband round the hairline, a bare wedge behind the part, stubble
  on the crown: look from BEHIND and from the far side, the references' cameras never show it);
  gather.hairline_strands {"density": 2, "clump": 0}: the hairline row is the one that lies over bare skin at the
  temples (thin there, its sub clumps draw as contour lines on the skin).
  curtain {"arch": deg, "arch_at": deg}: rounds a pointed forehead (the two curtains run straight diagonals from
  the part: a triangle): the run over the forehead raised for locks rooted arch_at deg from the part, none at the
  part (a negative dip does it by closeness to the part: the centre rises and bares a notch); per side
  ("left"/"right": {"arch": ..}) when one corner needs more. "smooth": rounds of smoothing where the way's arcs meet.
  frame {"hairs": 3, "curve": 0.14, "count": [10, 6], "width": [0.001, 0.003], "strands": {"clump": 0, "flyaway":
  0, "flat": 1, "loose": 0.9}}: loose SINGLE hairs beside the face: each piece is 1..hairs strands in their own
  object (a lock is never under ~8 strands side by side: comb strips; more of those is worse), bowed off its line
  in its own plane. look.fine_alpha (0.5): EEVEE draws single hairs part transparent (a strand is never under a
  pixel wide; Cycles draws true widths).
  tail {"sway": 0.016, "sway_length": 0.22, "flick": 0.022, "strands": {"clump": 0.55, "tips": 0.9, "tip_spread":
  0.1}}: big soft waves = the tail's AXIS swings (strand / lock waves only crimp a straight tail), flick turns the
  locks' ends out, a lock's own clump / tips make pointed separate locks instead of a blunt brush),
  loose ({"length": m | {front, top, sides, back, nape}, "level": m from the head centre (a one-length cut ends
  there: about -0.10 the jaw, -0.17 the shoulders), "spacing": m between lock roots, "body": m the mass builds
  up, "lift": m of root volume, "stiff": 0 hangs .. 1 keeps its root direction, "out": 0 combed along the scalp
  .. 1 straight out of it, "back": 0..1 combed back over the crown, "messy", "uneven", "ends": + under / - out,
  "face": 1 = kept off the face, "fringe": {length, span deg, depth, sweep, level, stiff}}: hair grown all over
  the scalp that FALLS on the neck, shoulders and back (or stands: an afro is out 1 + stiff 1 + curl): a bob,
  loose waves, long straight hair, a fringe, a crop, tousled hair. guide(topic="hair") has recipes per style).
style: "locks" (solid sculpted locks: stylised hair, the default), "strands" (the locks become GUIDES of a strand
  groom on Blender's Hair Curves: realistic hair; the game export cuts cards from those strands), "cards".
strands: a patch of the strand dials (hair.strands; guide(topic="hair_checklist"), "Strand dials"): count, thickness,
  taper, clump, clump_size, clump_shape, stray, tip_spread, loose, wave (m), wavelength (m), curl, random, frizz,
  flyaway, tips, roots, under, under_length, flat, soft, baby. look: a patch of the material (lit, gap, tip,
  tip_amount, vary, root, roughness, light "salon" | "flat").
  look, the colour model (strands): variation 0..1 (default 0.4), sun 0..1 (sun-lightened lengths, by the hair's
  age from the scalp; default 0.2), highlights 0..1 + highlight_contrast (lighter warmer ribbons; default 0),
  fly_light 0..1, depth 0..1 (under-layers of hair with volume darker), root_dark 0..1, gloss 0..1 (the two
  highlight lobes in EEVEE). Flat on purpose: variation 0, sun 0, vary 0. The groom export carries the model as a
  per-point `groom_color`, the game cards as vertex tone (hair_colour.py).
  look also: grey_amount (share of grey strands everywhere), grey_locks (x each lock's own "grey": greying
  temples and sideburns are locks with more grey), grey (its colour), scalp_tint, cycles_fit.
fuller: {region: m} (front, top, sides, back, nape): the EXISTING locks made fuller there, as a barber's "more at
  the sides": every lock point rises by that much (eased in from the hairline) and the lock grows thicker by twice
  its lift, so a strand groom fills from the scalp up; negative = closer. Measure the outline against the
  reference first (hair_reference's outline_regions, in mm) and give the miss. Solid sculpted locks ("locks")
  are only lifted (thickened they'd be slabs). trim: {"below": m, "where": [regions]} (or a list): every lock is
  cut where it runs more than `below` outside the hairline in those regions (negative = cut that far INSIDE it:
  a tapered nape is {"below": -0.015, "where": ["nape"]}). With only fuller / trim given nothing is regrown.
stage: "mass" shows only the groom's volume as one shell (judge the silhouette first), "locks" the locks.
Locks edited by hand (in Blender and pulled, or by edit_model) carry "hand": true and are kept; locks deleted in
Blender (hair.removed) aren't grown again; replace=True regrows everything and forgets both.
Edit single locks with edit_model: {"op": "set", "kind": "hair.locks", "name": lock, "value": {"width": 0.07}};
the material with {"op": "set", "kind": "hair", "name": "look", "value": {"lit": "#5a3a2c"}}.
Then look_hair. Returns the counts per tier.

### `tie_hair`

`tie_hair(name, style=None, carry_from=None, look=None, note='')`

A tied-back hairstyle from a STYLE (stored as spec.hair.groom.tied; see "Tied-back hair as a STYLE" above for the
table of words): style is MERGED into the model's tied style (name only what changes: a riff), the hair becomes a
strand groom (hair.style "strands") and is regrown; any groom.tie / groom.loose the model had is replaced by what
the style makes. carry_from: first wear that model's whole hair (hairline, look, strand dials, tied style), scaled
to this head (traced hairline heights move with the head centre). look: a patch of the hair's material.
style keys: tie (nape | low | mid | high | top | deg), side (centre | left | right | deg, the person's own),
tightness 0..1, lift 0..1, volume (0..1 or {amount, crown, sides, nape, root, arc, layers, hold}: the hair stands up
from the roots / the part and arcs over, in layers; 0 = a cap on the skull; default = lift),
part (centre | left | right | none), ears (tucked | covered), tail ({kind: tail | bun |
plait | none, length m, fullness 0..1 (sleek .. bushy), wave 0..1 (straight .. loose waves), tousle 0..1 (brushed ..
a ragged end and strays), to: back | shoulder} or just the kind), wisps (0..1 or {amount, where: [part, front, temple,
sideburn, nape], length [m, m], softness 0..1, loose: n thick locks a side}: soft clumps of fine hairs at the hairline;
default from neatness), front (0..1 or {looseness, drape, locks}: the hair in front of the ears alone looser, hanging
over the forehead corners, with thick loosened locks), hairline (0..1: 0 = a hard edge, 1 = thins out with baby hairs; default 0.8 - 0.3 x
neatness), escaped (single hairs: n a side or
{count, where, length}; default none), neatness 0..1, half (true) + length m, detail ({"tie": .., "strands": ..}: hair_tied's own
keys, when a word is missing).
Returns what was grown (gather / tail / wisps / escaped hairs), the style as stored, and what it made in numbers (the
tie's place, how far the hair stands off the head, the tail). Then look_hair(name, views=["around"]) (needs `sync`
once). Heavy the first time on a body (its collider, ~1 min), 1-2 s after.

### `look_hair`

`look_hair(name, views=None, size=480, clay=True, layout=False, reference=None, save=None, only=None, tier=None, debug=None, engine='eevee', stage=None, measure=None)`

A fast look at the hair (4-30 s): the head cropped from the model's Blender scene with the hair from the spec,
rendered in EEVEE. Rows: the material, the same in clay (shape without colour: judge clumps there), and with a
matched reference camera (hair_reference) the matched render, its clay, the reference, a 50% blend and the traced
lines over the render (reference yellow, model cyan). A thumbnail shows how it reads small.
views: any of front, three_quarter, three_quarter_r, side, back, top, close, close_back (default front,
three_quarter, side, back, top); "around" = six sides with the bust (bust_front, bust_three_quarter, bust_side,
bust_back_quarter, bust_back, bust_side_r): the row for hair that hangs and for the angles nobody tuned. layout=True adds the groom seen from above as a sketch: hairline, parting, every
lock's spine (drawn clumps black with names, others by tier), roots and tips; views=["layout"] gives only that
(no render). reference: an image to show beside the views (default: the traced reference). only: lock names or
patterns (["sweep*", "pside0"]) shown alone on the underlayer, to see which locks make a busy patch (the gates
then measure that subset).
Returns the images and the measured gates: the outline's dents (front, 3/4: a pinched temple reads as a divot),
the bare-volume share per view (the volume showing between locks reads as a helmet), and with a trace the fit to
the reference (part start px / direction deg, hairline px, silhouette IoU, outline px, clump directions).
A strand groom (hair.style "strands") renders its strands; engine="cycles" path-traces them with the hair BSDF
(for reference only, never the judging render: minutes, and it waits for the machine's heavy slot). tier: "hero" | "main" | "npc" | "far"
shows the game CARDS of that tier instead (cut from the strands); debug then isolates what makes a fault:
"layers" (cards as solid quads coloured by layer: cap grey, 0 red, 1 green, 2 blue, 3 yellow), "cap_only",
"cards_only", "no_normal", "unlit". export_hair judges the exported files themselves.
views "ref0", "ref1", ...: the FITTED cameras of the model's reference pictures (human_refs.json: the block-in /
face solve's cameras), the whole picture squared: the hair as each picture shows it, always the hair of the spec as
it is NOW (a look never reads a mask or render back from an earlier one).
stage: another model with the same head whose scene is used (a riff's copy of a head needs no scene of its own:
`look_hair("riff", stage="the_head")`).
measure: {"view": "ref2", "mask": png, "tie": [x, y], "colour": true}: the current hair against that picture. mask =
a hair mask in the picture's own pixels (white = hair); the text then gives IoU, area, the outlines' distance (mm)
and, with tie = the tie's pixel in the picture, what hangs below it against hers (area %, length, width, reach in mm).
colour: CIE L* / chroma / hue of the dense hair's shadow / mid / highlight thirds, ours | the picture's, and
`variation` (hair.colour_variation: L_sd, strand_sd (against its 1.5 mm neighbourhood), ribbon_sd (1.5 mm against
9 mm: clumps, highlight ribbons), mass_sd (9 against 40 mm: form, roots / lengths), ribbons {share, contrast} = the
share of the hair that is a LIGHT ribbon and its lift in L*, chroma_sd, hue_sd): set look.variation / sun / highlights
by these (a photo: ribbon_sd ~3, light ribbons ~10 % of the hair at + 6 L*; a flat look reads ~2 and 3 %), for the
engine rendered: the numbers to set look.eevee_gain / eevee_sat (EEVEE) or look.cycles_fit / cycles_width /
cycles_sat (Cycles) by. The look's own lights are used (look.light), not the picture's: compare bands, not single
pixels. (look_hair(engine="cycles") uses 10 transmission bounces: 2 render dark hair near black.)
Needs the scene once: `sync` the model (or its stage) first.

### `hair_from_reference`
`hair_from_reference(name, out="", read_only=False, authority=None, compare=None, seed=0)`: the HAIR READER. The
model's fitted reference pictures (human_refs.json, from the block-in / face solve) are MEASURED, never used as a
texture (as skin_from_reference): face parsers (MediaPipe multiclass + BiSeNet) give hair / skin / backdrop, a
pixel-level hairness runs from the backdrop's colour to the dense hair's, the model's scalp projected through each
camera is the bare skull. It reads:
- stand-off (mm from the skull's edge to the solid hair's edge, by region: front, top, crown, sides, back, nape; per
  view and the median; NEGATIVE where the skull pokes through the hair = the head and the picture disagree there:
  fix the head or trust another view, not the groom) -> rule 1
- halo density (mean hairness 0.5-4 mm past the solid edge: 0 a cut-out .. 1 solid), edge roughness (mm against its
  own 15 deg trend), wisps (detached hair pieces within 12 mm, per 10 cm of outline) -> rules 4, 7
- hairline: every hair / bare-skin boundary pixel cast onto the scalp (height per |az|, left and right together, and
  their difference), softness (20 -> 80 % hair across the line, mm), baby hairs (thin specks on the skin side, per cm)
  -> rule 6
- parting: a sharp flip of the strands' direction over the top WITH a line of scalp (front-ish views); else NOT SEEN
  and the start has no part (INFERRED); the front's sweep (which way it is combed) -> rule 5
- colour from ONE authority view (default the most frontal; the others are printed as checks: pictures disagree on
  colour between views): colour_bands + colour_variation, a two-mode split into pigmented hair (`seen`) and light /
  grey strands (`grey`, their share), and the light share BY REGION (salt and pepper greys at the sides first)
  -> rules 8-11
- length: not in a picture of a short cut (it lies over itself): INFERRED from the stand-off.
The START (saved to `out`, a copy, or the model; read_only shows it without saving): style strands; a short cut
(mean stand-off < 30 mm) gets `groom.loose` as a combed short cut (rule 14): lengths by region (INFERRED: a taper),
`lift` per region = the stand-off less the strands' own ~5 mm (groom.volume does nothing to loose hair), thin laid
locks, flow one way per region (the front over by the measured sweep), lay (prior), hairline front_points (MEASURED),
parting (MEASURED or none), grey by region; look seen / grey (a grey STRAND: the lightest quarter of the light pixels,
since strands finer than a pixel mix with dark ones) / grey_amount / variation; strands: fine, straight, dense, with
halo / flyaway / soft / baby from the read. `colour_step` (in the compare reply) then corrects seen and grey per
linear channel by picture / render on the authority view: one step took the mean L* from 30 to 40 (picture 42).
Longer hair: hairline, parting and look only (groom the shape by hand). Every line says what it came from.
`compare={0: "s_v0.png", 1: ...}`: the same read on OUR renders through those fitted cameras (square renders as
look_hair's "ref<i>" views), as a table ours | picture: the round's measure, like with like.

### `hair_reference`

`hair_reference(name, trace=None, image_path=None, apply=False, widen=1.8, save=None)`

Match the hair to a reference picture: store its trace, fit the reference's camera to the model's face, and
 optionally carry the traced groom onto the head. From then on every look_hair adds a matched row and fit numbers.
 trace (or the stored one when omitted): see below; trace it by reading pixels off the image (zoomed crops with
 a grid help). image_path sets/overrides trace["image"].
 The camera (pose + focal length) is solved by least squares from trace["landmarks"] (the model's lm_* joints ->
 their pixels); expect a few px of error per landmark, more means a mislabelled point.
 apply=True: the trace carried through the camera onto the head becomes the groom's parting line, hairline
 front_points and drawn clumps (rays onto the groom's volume; hidden roots carried back to the part; rows behind
 the traced ones; widths = traced px x mm/px x widen, since clumps overlap) and is merged into spec.hair.groom.
 Then groom_hair to grow the locks, and look_hair.
 Returns the trace drawn on the reference (landmarks green, the fitted camera's reprojection cyan) and the errors.
 A trace is reference-image pixels (u right, v down) of the picture you're matching:
   {"image": path (or pass image_path), "landmarks": {lm joint: [u, v], ...} (8-10 face points: eye corners, brow
    middles, nose tip, mouth corners, chin; the model's lm_* joints), "part": [[u, v], ...] (the parting from its front
    end back), "hairline": [[u, v], ...] (temple to temple across the forehead), "hair": [[u, v], ...] (closed outline of
    the visible hair above clip_y), "clip_y": v (below it ear, sideburn and beard aren't traced), "clumps": [{"name",
    "line": [[u, v], ...] root -> tip along the strands, "width": px across the clump}], "crop"?: [x0, y0, x1, y1] (the
    square the matched views show; default: round the hair and landmarks), "views"?: {name: {the same keys for
another view of the character: another figure in the same picture (same lens), or a turnaround's side/back with
its own "image"; landmarks, hair, hairline, clip_y and crop needed}}}. Every view gets its own matched row and
outline numbers in look_hair.
 Clump names: one starting "part_side" is the short clump falling from the part toward the near ear; one whose root is
 across the head from the part is the sweep's fall down the far side; the rest are the rows sweeping from the part,
 front first.

### `export_hair`

`export_hair(name, out_dir, tiers=None, groom=True, check=True, save=None)`

The hair alone, game-ready, from a strand groom (hair.style "strands"; guide(topic="hair_export")):
one GLB a tier in out_dir (`<name>_hair_<tier>.glb`; tiers hero 40k / main 16k / npc 6k / far 1.5k triangles;
default main, npc, far), all on ONE atlas: cards cut from the groom's own strands (a lower tier = fewer, wider
cards from bigger clumps; far = the cap + a solid tail), the cap wearing the scalp's chart, alpha MASK, two
sided, the recipe for an engine's hair shader in the material's extras. groom=True also writes the strands
(`<name>_groom.abc` in cm for Unreal's groom import, `<name>_groom.usdc` with groom_* primvars).
check=True re-imports every GLB on the head (as an engine gets it) and judges it against the strands in the same
views and light, under a hard alpha TEST and dithered: per view iou / bare (strand silhouette left uncovered),
value and saturation x the strands', detached rectangular blobs (cards showing as stamps), straight outline
share (plank ends), with WARNING lines. save: the sheet (strands | each tier alpha test, dithered, cards as solid
quads by layer | the atlas); each row is also written beside it as <save stem>_<tier>_<test|dither|solid>.png.
Minutes with check (about one a tier). Returns the sheet and the table.
