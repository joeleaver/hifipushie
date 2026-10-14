# Hair locks: hairline, fins, hand-shaping, material and cards in detail

Read guide(topic="hair_locks") first.

### 3b. The hairline and the front

The hairline is one designed line, and the front's strands come out of it at an angle. look_hair measures both in
every matched view:
- **hairline edge**: the rendered hair's edge against the skin, followed along the traced hairline.
  - `rough_mm` (rms against its own running median) should be <= 1, and `tooth_mm` (the worst tip or notch) <= 3.
  - `teeth` names the lock that makes each tooth.
  - `holes` is skin showing just inside the edge.
- **strand direction just inside the hairline**: the strands' angle to the hairline, read off the reference and our
  render alike (structure tensor) in the band 4-28 mm inside it, in 6 stretches. 0 runs along the hairline like a
  headband; 90 comes straight out of it. A combed short cut typically reads 10-30 degrees: a shallow diagonal,
  not perpendicular.
- **where the bare volume shows**: by head region, "hairline" meaning within 15 mm of it.

What works for the front:
- **Front locks grow out of the edge.** Draw 3-4 front locks rooted along the hairline from the part's corner,
  rising at the reference's angle and sweeping over to the far temple, with `"root": 0.1-0.15, "climb": 0.025`.
  - The narrow root comes out of the layer and the lock's body forms 2-3 cm back.
  - With full-width roots, a row of root ends read as scales along the forehead.
  - A lock drawn along the hairline (a fringe) reads as a headband.
- **`to_hairline`** (on a drawn clump): an inset in m, negative to tuck it into the skin, or `{"inset", "reach"}`.
  The clump is moved across so its edge runs along the hairline, and cupped so that edge comes down onto the layer.
  Good for one lock that should BE the edge. Don't use it at a temple corner: offsetting a path round a tight
  corner folds it.
- **`groom.hairline_edge`** `{"inset", "reach"}` does the same for every clump whose edge comes within `reach` of the
  hairline. It can bend side rows round the temples into folds; prefer per-clump.
- **A root drawn on or past the hairline grows out of the skin** (its end is buried).
- **`volume.edge_sink`** (0..1): the underlayer's front edge sunk under the front locks. Unsunk, it stands up as a
  dark lip under the quiff. With a gentle `ramp` it hardly matters.
- **`parting.front`** (m, default 0.015): the part's dip fades in that far behind the hairline. Dipping right to
  the edge, it cut a V notch.
- The underlayer's rows follow the hairline, and traced `front_points` ease onto the default line at the temples.
  On a fixed grid the rim was a staircase of fine serrations; the old join stepped 4 mm at the temple corner.

### 3c. Fins, blunt root ends, folds

- **fins**: a lock edge standing over the layer by more than its own thickness + 3 mm. A wide flat lock laid
  across the volume's shoulder stands on one edge.
- **blunt root ends**: a lock's width where it rises out of the layer, times how steeply it rises. Over 15 mm, the
  cut end shows: crescent fins along a parting in the side view, scales along a hairline. Lower `root` (0.1-0.2) and
  raise `climb` (0.02-0.03 m) on rows that start at a parting or the crown.
  - Not on the side rows: their narrow roots left the temples bare (bare share 0.09 -> 0.13).
- **Folds at u ~0.15 on short rows** (the nape) were the root's climb out of the layer. On a lens tilted ~35
  degrees, that bend lies in the lens's own plane. They are hidden under the row above, but real.
  - Now the climb takes at least 12 mm (`climb`), and the root's tilt is half the lie's (ROOT_TILT).

### 5. Hand-shaping (when numbers won't get it)

- `sync(name, hair_only=True)`, then edit the curves in scene.blend: points, handles, Alt+S radius, Ctrl+T tilt, the
  modifier's Width / Thickness / Taper / Belly / Root / Edge. Shift+D adds a lock; X deletes one.
- Then `pull`. Edits come back as `"hand": true` locks that a regrow leaves alone; new curves come back as new locks;
  deletions go to `hair.removed` and are never regrown.
- A person can do this in their own running Blender: sync and pull use the live session.
- Single numbers can also be changed without Blender:
  `edit_model(name, [{"op": "set", "kind": "hair.locks", "name": "sweep3", "value": {"width": 0.07}}])`.
  Add `"hand": true` in the same value to keep the change through a regrow.
- What has worked:
  - A few BROAD locks (7-10 cm wide, ~6 mm thick, thin edges `edge` 1.6) lying on the volume, with a steady tilt.
  - A top fan from the part.
  - Sideburn, nape and behind-ear locks for coverage.
- To fix a gate dent: find the lock that makes that height of the outline and pull it out 2-4 mm.

### 6. Material

Material settings go in `spec.hair.look` (sRGB hex colours):

| Setting | What it does |
|---|---|
| gap, lit | the dark-to-lit range |
| root, edge | how far root and edges darken |
| vary | value per lock |
| sheen, sheen_amount | the band along the crown |
| band_shift | how far each lock's band slides along it: keep it above 0, or the bands line up into one stripe |
| grooves, groove_depth | strand grooves as bump: soft, uneven |
| anisotropic, roughness | highlight shape |
| tip, tip_amount | tips lighter or warmer |
| variation | 0..1 (strands; default 0.4): natural hair is never one colour. Locks drift in lightness, sub clumps and strands in hue and saturation. 0 = one flat colour (with `vary` 0) |
| sun | 0..1 (strands; default 0.2): SUN-LIGHTENED lengths. The hair lightens and warms with its AGE, metres from the scalp (full by 28 cm): roots stay the look's colour, a ponytail's ends are the lightest. A tail's hair counts from where the gathered hair ended, not from a new root |
| highlights, highlight_contrast | 0..1 (strands; default 0): lighter, warmer RIBBONS at two scales (many thin ~4 mm, a few broad soft ~15 mm, irregular edges), starting a few cm off the root, coming and going along their length, gathered where the sun reaches (the top layers, round the face, a tail's outside) and a little on some locks; contrast 0..1.5 (default 0.6) |
| root_dark | 0..1 (default 0.5): how dark the root's first stretch (`root` of the length) is; 1 = the gap colour. A tail's strands have no dark root |
| gloss | 0..1 (EEVEE strands; default 0): the highlight where light catches the hair, as two lobes: a sharp pale one shifted toward the root and a broader one in the hair's own warm colour shifted toward the tip |
| fly_light | 0..1 (strands; default 0.3): hairs that left the mass (fly-aways, the halo, wisps) read lighter |
| depth | 0..1 (strands; default 0.5): the under-layers of hair with `volume` are darker (the shadow EEVEE's strands do not cast on each other) |
| vary | the value noise per strand / sub clump under all of it |
| grey | greying (where: groom.grey) |

- All of this lives in the material, and the export bakes it into the maps. It never goes into geometry.
- Judge it with the material on AND in clay, and in close-ups (views "close", "close_back").

# Hair: soft, loose hair as strand cards

Sculpted locks (above) are the feature-animation answer. Soft, loose, wavy or tied hair is made another way in games:
**hair cards**. `spec.hair.style = "cards"` draws the same locks as cards; everything above about silhouette, flow,
hierarchy and the hairline still holds, because a lock stays the unit you design and edit.

## What the tools do (cards)

- `hair.style: "cards"`: every lock becomes a stack of cards inside its own lens: a dense layer underneath, clumped
  cards over it, wisps on top, fly-aways off it. The lock is still the Bezier curve you edit (numbers, or in
  Blender + pull).
- `hair.strands` (all optional):

  | key | what |
  |---|---|
  | wave, wavelength | m the lock swings side to side, m per swing. Full on free hair, a third on hair lying on the head |
  | curl | 0..1: how much of the wave leaves the lock's plane (1 = ringlets); free hair only |
  | random | how far cards differ in phase, amplitude, length |
  | clump | strands in the pictures gather into pointed sub clumps |
  | frizz | single strands wander |
  | flyaway | stray single-hair cards per card |
  | layers | 1-3 card layers per lock |
  | card_width | m, the widest card |
  | tips | how ragged the ends are |
  | baby | baby hairs per cm of hairline (0 = none) |
  | soft | m over which the hairline breaks up into strands |
  | round | how far normals bend to the volume's (soft shading) |

  A lock can carry its own `"strands": {...}`.
- The atlas is generated (8 tiles: dense x2, medium x2, sparse x2, fly-aways, baby hairs; colour + alpha, normal,
  and an aux map: root / id / depth / alpha).
- The underlayer is the hair cap: it wears a dense tile whose ragged end lies on the hairline.
- **Tied hair**: `groom.tie` (see groom_hair): hair gathered over the head to a tie point, a tail that leaves it
  (free under gravity, coiled into a bun, or plaited), the strands that escaped, the band.
- Locks that leave the head are `"space": "xyz"` (metres from the head centre) with `"free": 1`: their underside
  is hair, not the dark gap side (solid locks too).

How card makers work (the method, published layer budgets, tools): guide(topic="hair_background").
