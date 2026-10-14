# Clothes: pattern, construction and arrangement (stages 2-4) in detail

Read guide(topic="cloth") first. These stages run in seconds and decide most of what a simulation can do.

## Stage 2: the pattern, laid flat (`look_pattern`)

*How makers do it:* a pattern maker "walks" each seam (measures one edge along the other), checks notches meet, and
measures the pattern against the body before cutting. In Marvelous Designer you read the 2D window before you press
simulate.

The sheet shows every piece at one scale: name, role, size, where it goes, grain arrow, notches (red), buttons and
buttonholes, the draft's internal lines (grey), fold lines (blue dashed, with angle), interfacing (hatched), and
each seam in its own colour, numbered on both sides (S3a meets S3b). The seam list gives each seam's two lengths and
ease; `dimensions:` and `draft:` lines give the details' sizes and the draft's derived numbers.

Checks, failures first:
- **Evidence.** Every sheet choice is found in the pieces and the seam table: a turned collar has a fall, a stand, a
  seam between them, a fold line and interfacing; a barrel cuff is closed on itself and interfaced; a waistband
  closes at waist + 0-30 mm.
- **Seams.** Ease per seam kind (sleeve cap by garment kind, bands -1..+1.5%, plain seams within 1.5%), and
  notches. Both sides of a seam are sewn by fraction of their length, so a notch mismatch is a real misalignment.
- **Fit.** Ease against the body per girth, inside the fit's band. Negative ease on a woven is TOO SMALL.
- **Loose pieces.** Every piece is sewn to something.

These checks prove the draft is consistent, not that it is the garment in the reference: also measure the
description's items on the draft (guide(topic="cloth"), stage 2). Fix what fails in the sheet (`design_garment`
again), then look again.

## Stage 3: the construction plan (`check_garment(stages=["construction"])`)

*How makers do it:* collars, cuffs, plackets and waistbands are made finished on the table (interfaced, turned,
pressed) before they meet the garment. In MD these are fold angle + strength on internal lines, fold arrangement,
interfacing presets and layers. Nobody simulates a collar into shape.

The plan lists:
- **Sewing order**, torso pieces first (the simulation sews the bodice alone first too), then the kind's order.
- **Closures** (button stitches) and **layers**: which piece starts outside which, and whether the lap follows the
  kind's convention.
- **Fold lines**, **interfacing**, **made or draped** per piece, and the simulation's stages as they will run.

### Fold lines (garment key `folds`)

`{"piece", "line", "angle", "strength", "kind": "press" | "roll", "radius"}`:
- `angle` is the dihedral on the pattern's face side (the side away from the body): 180 flat, 0 folded right over
  onto the face (a collar's fall over its stand, a lapel rolled onto the chest, a turned-back cuff), 360 folded right
  under (a hem, a facing, a placket).
- `line`: a line name of the piece, two point names, points in metres, `{"edge": "piece:a>b", "offset": m}` (parallel
  to an edge) or `{"mid": "x"}` (lengthwise through a band's middle). A fold runs from edge to edge of its piece.
- `kind` "press" is one sharp crease; "roll" spreads the turn over an arc of `radius` (as many vertex rows as the
  mesh carries). `strength` 0..1 is how hard the crease holds its angle. `flap` (a point or mark name) says which
  side turns when the default (less sewn edge, then the smaller side) is wrong.
- What a fold does (`folds.py`): the mesh gets a row of vertices on the line; the placement lays the piece unfolded
  and turns the flap about the row, as far as the fold asks or as it clears what's under it; the solver keeps it
  (made pieces rest as placed; ZOZO rests ordinary cloth on the flat pattern with the fold's hinges at their angle and
  20x stiffer at strength 1; Blender rests on the placement, a fold a U 8 mm across).
- `look_cloth` and the report measure each fold: the turn across it and the gap between flap and base.
- A simulated crease is a wedge 5-7 deg open (contact gap), its layers 3-6 mm apart at 1-2 cm triangles. A
  constructed one (method "settle") is a U two cloth layers across: 1.6 mm.
- End a roll fold a few cm above a fastening (over front ~2 cm above button 1, under front ~6 cm): a roll line that
  crosses a band's inner row at a shallow angle makes a sliver triangle and the start fails.

### Interfacing, made and draped

- Interfacing multiplies bending (practice 5-20x the shell): whole pieces or a band along a line (`interfaced`).
- Made pieces are constructed finished and keep their shape (collar, stand, cuffs, waistband). Draped pieces are
  loose cloth shaped by body, gravity and seams (fronts, backs, sleeves, skirt panels). The sheet's `"made": {piece
  or role: "made" | "draped"}` overrides. Stage 3 fails when draped cloth is wholly interfaced (it would be frozen
  as placed: a lapel that can't roll).
- Never mark a notched collar draped: a stiff interfaced strip resting on the flat pattern bent round the neck is a
  fat roll. Made pieces sewn to each other (a collar on its stand) are one construction, set by the piece with the
  most seam to draped cloth.
- `made_folds` (a made REGION of a draped piece past a fold line) didn't pay on lapels (seams dragged open,
  crossings at the gorge). Leave it off; a firm lapel roll (`roll_radius` 0.003, `roll_strength` 1.0) does the job.

### Closures (garment / design-table key `closures`)

One entry per closure:
`{"name": "front", "kind": "buttons", "over": "front.L", "under": "front.R", "edge": {"over": "a>b", "under": "a>b"},
"band": {"over": 0.03, "under": 0.018}, "state": "closed"}`.
- `over` laps over `under` (the same piece for a cuff or waistband). Fastenings are marks `buttonhole<n>` on `over`
  paired with `button<n>` on `under` (other prefixes `holes`, `buttons`; or `"at": [[over mark, under mark], ...]`).
- `band` + `edge` give the placket its own edge in the mesh and raise it by its layers.
- `state`: "closed", "open", `{"open_above": mark}` (the fastenings above a mark undone) or `{"open_top": n}` (the n
  highest undone, whatever their names).
- The entry makes the button stitches, the buttons as small geometry (also in the export and scene) and a report
  line per closure (closed is <= 6 mm apart). A `front_closure`, `cuff` or `fly` chosen on the sheet with no closure
  entry fails here; a closure that didn't hold fails stage 5. `kind: "zip"` takes `"seam": [arc, arc]`.
- How it is WORN is the closure's `state`, set on the garment without repeating the entry: a garment's entry of a
  name is laid over the design's key by key (`[{"name": "front", "state": "open"}]`: a jacket hanging open, its
  buttons still on the under front; stage 3 lists it "worn open").
- In a drafted garment the op `{"op": "buttons", "piece": "front", "n": 2, "state": "open", "size": 0.02}` writes
  the closure itself (left front over right).
- A front worn `open` starts the fronts apart (`open_gap`, default 0.16 m at the hem). Started lapped like a
  buttoned one, an open jacket hangs closed and tents.

### Built on the form (shirts, jackets, coats, knits with seam-laid bands)

A tailor builds a forepart on a form, not round a cylinder. Kinds with `worn_top` (garment key overrides) start each
front and back where it is WORN: below the armpit on the torso cylinder, above it laid up the body column by column
and hung so its top lands on the shoulder ridge; side panels hang with them. Shoulder and CB seams are pinned shut,
the collar laid on that neckline and pinned to it, lapels PRESSED onto the forepart, and the start relaxed with
those pins held. On a cylinder, a jacket's shoulder seams started 23-25 cm apart and the lapels unrolled.

### A piece laid from its seam

Wrap `{"to": "seam"}` places a piece from the edge it is sewn to (a tailored collar's stand on the jacket's
neckline, a collar on its stand), along the body, at the pattern's lengths; `"turn": {"at": m, "deg": 172, "gap":
m}` lays its fall over, `"turn": {"line": [[x, y], ...]}` turns it about a line in its own pattern. List the piece
after the pieces it is sewn to. `"worn": true` lays it on the edge as that edge will lie worn. The draft op `collar`
type `tailored` sets all of it after a `lapel` (a notched collar's roll line stands `stand_height` at CB and comes
down to the neck edge where the lapel's roll line crosses the neckline; `"roll": "parallel"` keeps a constant stand).

### Tailoring tells for an open jacket

- **The tent** (fronts bowing forward to the hem) is the SIDE PANEL'S HEM SPRING, not the canvas or the front
  balance: a `contour` letting each panel edge out 16 mm at the hem is 64 mm of flare a side, and an open front
  swings it forward. Cut panel seams straight below the waist (`{"op": "contour", "edge": ["sideF", "sideB"], "at":
  [["waist", 0], ["hem", 0]]}`); room over the hips from `hips_ease`. Keep the chest canvas: it keeps the two sides
  alike. A stiff front (canvas bands + a hard roll) carries the chest's slope down to the break: keep the roll soft
  (`roll_strength` ~0.3) on an open front if it boards.
- **Front balance** (raising the front's neck point over a forward chest) pulled the sleeves up and bunched them:
  leave it 0. If tried, raise only the neck point, gorge and CF, or redraft the sleeve into the new armhole.
- **The button stance** (lapel `stand`) sets where the open fronts' edges sit; more stance closes them.
- **The pose matters:** raised arms lift the sleeves and pull the fronts apart (arms 25 -> 45 deg: front edges
  2 -> 12 cm apart at the hips). Judge against a reference in its own pose.
- Press the under garment harder (`under_cap` 0.004) so the outer one keeps its girth.

## Stage 4: arrange (`check_garment(stages=["place"])`)

*How makers do it:* MD's arrangement points put each piece on a bounding cylinder round the body part it covers,
symmetric pairs symmetric, before any simulation.

The render shows the start: torso pieces on one cylinder round the trunk (wrap `"to": "torso"`, `"side"`, `"level":
"waist"` for pieces that hang from the waist), sleeves round the arms, bands round the neck or wrist, trouser legs
each on a tube round its own leg (`leg.L` / `leg.R`, set by the trouser block). Checks:
- pieces through each other (or through THEMSELVES) at the start (a failure for a contact solver, a warning for
  Blender);
- a neck band pushed more than 8 mm out of the neck (it is taller than the neck: lower it);
- start stretch past the solver's strain limit (ZOZO can't start there; the start relaxation brings triangles near
  3%, and the fine settle refuses a start over 1.6x, naming pieces and places);
- a self-closed band (waistband, cuff, buttoned stand) that starts open: it must START closed ("<band> starts with its
  fastening N mm open"); give it 2-3% ease or seat it where the body is smaller;
- layer gaps at the start; seam gaps at the start.

**What a seam does in the sim is mostly decided here.** A seam the solver must close from far apart closes badly or
not at all, and stiffer stitches don't help. Read the start's seam gaps before simulating, and fix the start, not
the solver:
- Stretch is shear too: edges within 5% of the pattern can be 9-12% stretched along the diagonal.
- One cylinder for a fitted torso leaves the waist's arc in one seam: on a suppressed-waist jacket the side-back
  seam starts 135-160 mm open and ends open. Not fixed yet: read that seam's start gap on any fitted jacket.
- A jacket's armhole too high for the body (sleeve starting down the arm, `sleeve_down` over 0.02, armhole start
  gaps far over ~9 cm): lower it (`armhole_depth` 0.12-0.14).
- Start an armhole's seam chain where the sleeve's top meets the shoulder seam (started at the front pitch, the
  sleeve is sewn in rotated).
- A waistband's `along` chain starts at the band's own opening (a band wrapped `side: front` opens at CB: start at
  `back.R:cWaist`); half a turn off sews it on twisted.
- A padded body (the under garment pushed out) can fold in hollows (the neck under an open collar, the pit); if a
  layered start shows a piece far off where it should be, suspect the pad (`under_cap`, the under collar).
- New lower-body designs: read the leg start seam gaps (a few cm, not 15+).

**Mirror check.** One side of a symmetric garment wrong after the sim: before changing the draft or solver, look at
the start (`check_garment(stages=["place"])`, no simulation) and compare every sim input with its mirror image: pattern, body / padded collider,
poses, start positions, carried made pieces, stiffness and fold arrays.
