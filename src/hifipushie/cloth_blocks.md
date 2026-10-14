# Clothes: designing a garment with no ready-made draft (block + operations)

Read guide(topic="cloth") first: the description of the garment decides the block and the operations.

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

Our bodice block matches FreeSewing's Brian at the same ease to a few mm (chest, armhole depth, shoulder and side
seams, necklines); our sleeve solves its cap for the width asked, so it is narrower with a higher cap than Brian's.

**Trousers** are placed now: wrap `leg.L` / `leg.R` (the trouser block sets it). Each leg's pieces start on one
upright surface round that half of the body, cut flat between the legs; the fork lies on the flat; the inseam and
side seam start open and the sewing closes the legs. Give a waistband by `generate`, its `along` chain starting at
the band's own opening (a band wrapped `side: front` opens at centre back: start the chain at `back.R:cWaist`); a
chain that starts half a turn away sews the band on twisted (verdict CORRUPT, twisted seams).

Lessons from designing garments from prose with these tools:
- Shaping lives at the DRAFT's waist line; the fit check measures at the body's.
- A waistband only a little over the waist holds nothing up: trousers with a loose band slide down.
- A block's length runs to near the floor: set the length you described, or the hem pools on the feet.
- A cut-on collar (shawl) and a two-piece sleeve need a careful start: read the place stage before simulating.

One cloth on two parts of the body: a shawl collar's back (past the neck point) lies round the neck, a kimono
sleeve round the arm, while the rest of the piece lies on the torso. The draft cuts such a piece for placement only
(a "hinge"; the seam list shows the join as declared, "one cloth: cut here only to place them"). You don't write
hinges: `shawl` and `kimono` make them. A facing (and a lining, a pocket) is LAID ON the piece it was traced from,
so it follows that piece round a roll line.

A pleat is laid CLOSED by the placement (the cloth past its line runs back a depth and on again: three layers), a
raglan sleeve's shoulder parts stay on the torso, and a point may be given by level: `{"edge": ..., "y": "waist"}`.

Not built yet: a welt pocket's cut and bag; a lining with its own pleat and trimmed to the facing; pleats that die
inside a piece.
