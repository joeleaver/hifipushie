# Clothes: pattern, construction and arrangement (stages 2-4) in detail

Read guide(topic="cloth") first. These stages run in seconds and decide most of what a simulation can do.

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

*How makers do it:* collars, cuffs, plackets and waistbands are made finished on the table (interfaced, turned,
pressed) before they meet the garment. In MD these are fold angle + strength on internal lines, fold arrangement,
interfacing presets and layers. Nobody simulates a collar into shape.

The plan lists:
- **Sewing order**, torso pieces first (the simulation sews the bodice alone first too), then the kind's order.
- **Closures** (button stitches) and **layers**: which piece starts outside which, and whether the lap follows the
  kind's convention.
- **Fold lines**, **interfacing**, **made or draped** per piece, and the simulation's stages as they will run.

### Fold lines (garment key `folds`)

### Geometry or maps: a game artist's call (folded bands, `represent`)

A narrow folded detail that lies close to the surface reads, at game distance, as a seam, a topstitch and a texture,
not as folded geometry: a T-shirt's rib neckband looks like "just a seam" on a real tee, and a game artist paints it.
Keep it in the PATTERN (it sets the neckline, its length, its stretch); choose how the FIT shows it:
- generated band `"represent": "flush"` (`details.collar.generate`, or a `generate` entry with `fold`): fitted as one
  layer at its finished height, cut as a cone that leans onto the slope round the neck (`lean_deg`, default 45), the
  fold, rib and a topstitch in the detail maps. Use it for thin ribs and hems seen at game distance.
- `"represent": "folded"` (default): the real construction, two layers with both raw edges in the seam. Use it where
  the fold IS the read: a thick heavy rib with a rounded top edge, a hero close-up, collars, cuffs, lapels. A narrow
  folded band needs a fine mesh (`mesh_refine` ~4 mm on it) or it rounds into a tube: at 9 mm triangles an 18 mm band's
  layers stood 9.6 mm apart (a roll), at 4 mm 3.0 mm.
Judge it beside the reference close-up: if the reference shows a seam line and texture, flush; if it shows a
separate rounded edge, folded.

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
