# Vegetation: growing trees the way vegetation artists make them

A tree here is **grown**, not assembled. You describe the species' habit, its age and where it stands; a growth
model (buds competing for light, year by year) makes the skeleton; then you direct it the way a SpeedTree or Grove
artist does (draw limbs, prune, bend, shape the crown) and it regrows around your edits. The same spec always grows
the same tree. Units are metres, Z up, the trunk's foot at [0, 0, 0]; "azimuth 0" looks along +y.

Tools: `get_plant` (the stored spec, what it resolves to, and what each number usually is), `grow_plant` (create /
change / copy / report), `edit_plant` (guides, prunes, envelope, forces), `look_plant` (images of one plant),
`look_plants` (several standing together), `wind_plant` (the export swaying), `sync_plant` (the Blender file a person
edits), `plant_reference` (measure against a photo, optionally fit),
`export_plant` (GLB, with a triangle budget), `plant_history` (`plant_history(name)` lists versions,
`plant_history(name, revert_to=3)` restores one). `grow_plant(name="")` lists the plants and the species presets.

**Before overriding anything, read it:** `get_plant(species="birch")` or `get_plant(name)` shows every value in
force (the preset's and the defaults') with its usual range. An override REPLACES the resolved value; a per-order
list is replaced whole (to change the limbs' jitter, give the whole list). Change numbers by small steps from what
is there: vigour 5.5 -> 7 on a broadleaf is 100k+ nodes and a metre-thick trunk. Every save echoes old -> new and
what the tree did (nodes, height, trunk).

## Work in stages (don't skip ahead: foliage hides a bad skeleton)

1. **Reference.** Decide what the tree is: species (or the nearest one), age, how it grew (open field, forest,
   windy hill), and three or four things that make it recognisable (e.g. oak: short stout bole, heavy level limbs,
   dome as wide as tall). If you have a photo, register it with `plant_reference` so every report carries numbers
   against it.
2. **Skeleton.** `grow_plant` with a species preset + age + environment. Look at `clay` first: trunk, the main
   limbs' number, angle and crookedness, where the crown starts. Read the report's form line (width/height, bole,
   widest height) and limbs line. Change habit numbers (below) until the bare tree reads as the species.
   Typical loop: grow (1 s) -> look clay (5 s) -> change two or three numbers.
3. **Direction.** Only now use `edit_plant`: draw the limbs that make this tree THIS tree (a low limb reaching over
   a path, a forked trunk, a leaning trunk), prune what's in the way, clear the trunk, give the crown an envelope.
   Guides are exact; everything else regrows around them. Few, deliberate edits: three drawn limbs make a hero tree.
4. **Foliage and bark.** `look_plant(views=["leaf", "close", "near"])`. Tune `leaves` (shape, length, twig) and
   `bark` (kind, colours) for the species. Check `far` last: at 70 m a tree is silhouette, mass and colour.
5. **Export.** `export_plant`.

Judge honestly at each stage and say what still looks wrong; a tree that matches the numbers can still read as the
wrong species (straight limbs read as a broom; an even cone reads as a witch's hat).

## The spec

```json
{"species": "oak", "age": 90, "seed": 1, "height": 20,
 "habit": {"apical": [0.5, 0.54], "jitter": [0.14, 0.4, 0.45]},
 "environment": {"setting": "open", "wind": {"from": "w", "strength": 0.5}, "light": [0.3, 0, 1]},
 "guides": {"low_limb": {"path": [[0, 0, 2.5], [2.5, 0, 3.2], [6, 0, 3.4]], "from_year": 15, "until_year": 60}},
 "prune": [{"below": 3.0}], "envelope": null, "forces": [],
 "leaves": {"shape": "lobed", "length": 0.11}, "bark": {"kind": "furrowed"}, "season": "summer"}
```

- `species`: a preset (a bundle of habit + leaves + bark). Everything in it can be overridden key by key. For a
  species without a preset start from the nearest in habit (hawthorn: start from `oak`, make it small and thorny-
  dense; young alder: `birch`; fir, larch: `norway_spruce`; any pine: `scots_pine`) and change what differs.
- `age` (years): the main size control. Young trees are narrow and keep their leader; old broadleaves lose it.
- `seed`: another individual of the same description (use for forest variants).
- `height` (m, optional): scales the growth so an UNEDITED tree of this description is this tall; guides and prunes
  stay in metres. How size comes about: growth steps = age / `habit.years_per_step` (2-80); each step a shoot adds
  up to `shoot_max` segments of `unit` x `length` m. So a 9 m tree in 14 steps has 0.65 m segments (coarse, few
  nodes); for the same height with finer segments lower `years_per_step` (more steps) and let `height` rescale the
  unit, or leave `height` out and set age and unit yourself. Without `height` the tree is as tall as it grows.
- `dead`: `[{"limb": "SW2", "min_radius": 0.03}, {"above": 15, "min_radius": 0.04}]`: wood that died and stayed
  on the living tree (a limb by its name, or a volume: box, sphere, above): leafless, barkless silver-grey
  (`bark.dead_color`), everything thinner than `min_radius` broken off. A stag-headed veteran = `above` just under
  the top; a snag limb = one limb (`"from": m` = only past that far along it; a guide's name works as the limb).
  The report says how much died and broke off. (A whole dead tree: `season: "dead"` + `decay`.)
- `roots`: `{"count": 5, "spread": 1.6, "height": 0.5}`: root flares at the foot: the trunk's section swells toward
  each root by `spread` x at the ground, fading over `height` m (spread 2+ and height 1+ = buttresses). The trunk
  always runs 0.3-0.5 m into the ground, so it meets a slope without a gap.
- `trunk_diameter` (m at the foot, optional): thick wood is scaled to it (twigs stay as they are), limbs too;
  with `limb_diameter` (m: the stoutest limb where it leaves the trunk) the two are sized apart: a very fat old
  trunk under ordinary limbs. (Over a long life `habit.ring` x age is what makes everything fat.) With
  `trunk_taper` (0-1: the share of that diameter the trunk loses by its top; 0.1 = a column, as a pollard's) the
  trunk keeps its girth whatever it carries. Without it the
  girth comes from what the trunk carries plus `habit.ring` per year, so a denser crown means a fatter trunk.
- Variants: `grow_plant(name="b", copy_from="a", patch={"seed": 2, "age": 14})`. Individuals of one stand share
  everything but seed, age and small habit differences.
- `season`: "summer" or "winter" (bare). `decay: {"min_radius": 0.05}`: a dead tree (wood thinner than this has
  fallen).

### habit (per-order lists: element 0 = the trunk, 1 = limbs, 2 = their branches...; the last element repeats)

| key | what it does | typical |
|---|---|---|
| `years_per_step` | years one growth flush stands for (old trees: 2-3) | 1-2.5 |
| `unit` | m per shoot segment at full vigour: overall scale | 0.25-0.5 |
| `vigour` | growth per unit of light: more = bigger, denser | 3-8 |
| `apical` | the share a continuing shoot takes from its side branches. Trunk > 0.55: one leader to the top (conifer, birch, poplar); < 0.5: the trunk dissolves into limbs (old oak, willow) | 0.44-0.66 |
| `apical_old`, `apical_fade` | the trunk's `apical` once old, and when (shares of the age): a tree that starts with a leader and broadens | 0.36-0.46, [0.25, 0.6] |
| `leader`, `leader_until` | segments a year the trunk's tip is sure of, and until when (share of the age): a guaranteed straight leader | 1 |
| `shoot_max` | most segments a shoot grows in a step, per order | [2, 2] |
| `length` | segment length x unit per order. Limbs much shorter than the trunk's = a narrow crown (spruce [1, 0.32, 0.45]) | |
| `angle` | degrees a side branch leaves its parent at, by the PARENT's order: [0] = limbs off the trunk, [1] = branches off limbs (30 = ascending, 80 = nearly level). The first segment keeps this angle; tropism, light and plagio bend what follows | [40-75, ...] |
| `tropism` | per order: + bends shoots up, - down. Hanging twigs: negative on the high orders ([0.4, 0.3, -0.1, -0.5, -1.2]) | |
| `plagio`, `elevation` | per order: pull toward a set elevation (deg above level), and how strongly: level limbs = plagio 0.3 toward 5; a conifer's flat branches | |
| `jitter` | per order: how crooked shoots run. Straight trunk 0.03-0.1; gnarled limbs 0.4+; straight limbs read as a broom | |
| `light` | pull toward open light (fills gaps, avoids its own shade) | 0.1-0.4 |
| `buds`, `whorl`, `divergence`, `plane` | per order: side buds per node (conifer trunk 4-6 with whorl true), degrees between successive buds (137.5 spiral, 180 two-ranked), flat sprays | |
| `bud_break` | by the NEW shoot's order ([1] = limbs off the trunk): chance a bud can ever grow. Lower [1] = fewer, stronger limbs | 0.3-1 |
| `bud_each` | true: `bud_break` is drawn for every bud of a whorl by itself (a pine keeps one or two limbs of each whorl of four: limbs at many heights, a deep crown); false: for the whole whorl (whole tiers or none: a pagoda when `bud_break` is low) | false |
| `bud_life` | steps a bud stays able to grow: longer = denser inside | 3-7 |
| `max_order` | deepest branching (spruce 2, broadleaves 5) | |
| `shed` | light per segment under which a branch is dropped: higher = cleaner trunk and open interior; too high and the tree starves | 0-0.3 |
| `shadow` | [strength, falloff, depth] of each leaf's shade. Shade-tolerant, dense (spruce): [0.03, 3, 2]; light-demanding, open: [0.25, 1.6, 6] | |
| `tip_life` | per order: growth steps an axis keeps extending, 0 = for ever. Short-lived hanging branchlets 6-10 (spruce); limbs that stop reaching 20-30 | [0] |
| `slowing` | per order: steps after which an axis's new segments are half as long (0 = never). Old branchlets creep: their young, needle-bearing ends stay close to the limb all along it instead of hanging metres below (spruce [0, 0, 4]) | [0] |
| `uneven` | per order: each axis grows at its own pace, +- this share: a ragged outline instead of a turned cone | 0-0.5 |
| `clear` | m of trunk that never branches | 0-6 |
| `sag`, `sag_max` | bending under weight (it sets): long thin limbs droop | 0.3-3 |
| `ring` | m of radius wood adds a year whatever it carries: girth. Stout trunk 0.002-0.003, slender 0.001. One number for all wood, or per order: a conifer's old low branches stay thin (`[0.003, 0.0005, 0.0002]`; with one number a 50-year spruce's lowest limbs were 32 cm thick under a 60 cm trunk: a cage of brown hoops) | |
| `pipe` | how fast branches thin (2 = thick limbs, 2.5 = thin) | 2-2.5 |
| `flare`, `flare_height` | the foot's swelling | 1.3-1.8 |
| `force_orders` | per order: how much wind and forces turn shoots (the trunk resists) | [0.15, 0.6, 1] |

Unknown habit keys are refused. Change a few at a time and read the report: nodes (300-90k is the working range),
height, form, limb angles.

### environment

- **Where it stands is one word**: `setting` "open" | "edge" | "forest". The same species grows three trees: open-grown
  (foliage to the ground on a conifer, a low broad crown on a broadleaf), a stand's edge (`"open_side": [x, y]`:
  foliage down that side only, the closed side self-pruned), a stand's interior (a long clean bole, a live crown
  only in the top third to half, and under it the limbs the shade killed: thin, grey, leafless, drooping stubs that
  stay `habit.dead_keep` years: a spruce's ladder of dead whorls 25-40 years, a pine sheds cleaner 8-12, a birch
  2-4). A forest set wants all three of each species. `habit.stand_shed` is how much harder a species self-prunes
  in a stand than in the open (spruce 0.17: it holds a skirt in the open).
- `setting`: "open" (default: low broad crown) or "forest" (the tree grows inside a closed stand of its own height:
  the canopy's top rises with it, so only the top of the crown is in the light: a tall bare bole and a narrow
  high crown). `stand` tunes it, all as shares of the tree's own height at the time: `gap` 0.18 = the radius of
  open sky straight above it (smaller = narrower crown), `depth` 0.35 = how far below the canopy's top the light
  reaches (smaller = higher crown base), `strength` 0-1.5 = how dark the stand is (lower it if the tree starves),
  `floor` 0.5 = shade at ground level. For young trees in a grove use `strength` 0.5-0.8.
- `wind: {"from": "w" | [x, y, 0], "strength": 0-1}`: the tree leans downwind, the windward side is thinned. 0.3 = an
  exposed field, 0.7 = a coastal hill. ("from w" blows toward +x.)
- `light: [x, y, z]`: where the light comes from (a tree at a forest edge leans out).
- `neighbours: [{"at": [x, y], "height": m, "radius": m}]`: single crowns beside it. Each shades everything lower
  than its `height` (m, reached when the tree is ~80% of its age) within 2 x `radius` of `at`, and pushes growth
  away. Give real sizes: a neighbour 1.6 m away with radius 4 covers the whole tree and starves it; for a close
  neighbour use radius 1-2. The tree does not see other plants you made: neighbours are only these blobs.
- `light: [x, y, z]`: where the light comes from (default straight up [0, 0, 1]). Keep z near 1: [0.3, 0, 1] is a
  tree at a wood's edge leaning out; [1, 0, 0.8] sweeps every limb sideways.
- The ground is a plane nothing is drawn under (`ground: {"level": m}` moves it; with `slope` it tilts), except the
  trunk's own foot (0.3-0.5 m into it on purpose). Three rules keep it so, at every budget and in the export:
  growth (a shoot never grows under `habit.ground_clear` m over it: a hanging shoot stops there, any other slides
  along and its end turns up), weight (the ground stops a sagging limb: it rests there, and what it carries turns
  with it), and cards (a card is a polygon round its anchor, and a hanging one reaches its whole length below it: a
  twig or bough card whose corner would be under `leaves.clear` m, default 0.03, is turned up about its foot,
  shortened to no less than 0.4 of its size, or left out). The report's `ground:` line says how much wood rests on
  it and how many cards were turned / shortened / left out, and WARNs with counts if anything is still under it;
  `look_plant(views=["ground"])` shows the place. Curtains that should end over a browse or mowing line:
  `habit.ground_clear` 0.5-1.5 (shoots stop growing there) with `leaves.clear` a little lower (the cards' ends), or
  the blunt cut `prune: [{"under": m}]`.
- `ground: {"slope": deg, "toward": [x, y], "water": z}`: the hillside it stands on and a water level (m against
  the plant's foot: -0.5 = half a metre below it), for the pictures. It does not change the growth: lean the trunk
  with a guide or wind. Only a uniform slope: no banks or ditches.

- In a stand (`setting` forest or edge) conifers look nothing like their open-grown selves, and the difference is
  dead wood (references: workspace/veg_refs/forest/README.md). `environment.spacing` (m between the stand's trees, 2.5-4
  planted, 5-8 thinned) sets how wide a crown the tree may keep; without it the gap is 18% of the height (a wide,
  thinned stand). `habit.stand_shed` kills shaded limbs (on an edge only on the closed side: the open side keeps its
  skirt). With `habit.dead_keep` years, a limb the shade killed STAYS as dead wood: the limb as it was, its dead
  branches on it, then decaying year by year (`deadwood`: {"break" share of its length lost by the end, "stub" m,
  "twig" [m, m] radius under which twigs have fallen at death / at the end, "droop" [deg, deg], "bow", "shrink"}):
  the youngest dead whorls under the live crown are whole and twiggy, the oldest near the ground short spurs. Its
  fine twigs are drawn by cards, not tubes (a 2 mm twig is under a pixel from anywhere): `leaves.parts.dead` =
  {"bare": true, "wood_color", "twig": {per_m, length, ...}, "card": {...}} is a bare-twig picture in the same atlas
  (spruce and pine presets have one). Looks of a stand tree stand on litter with a dim brown bounce (not a lawn).
  Read the report's dead wood line; a spruce at 3 m spacing should show a live crown of a third to a half.

### Direct control (edit_plant ops, or the same keys in a spec)

- `guides`: `{name: {"path": [[x, y, z], ...], "from_year", "until_year", "vigour"}}`. A drawn axis: at `from_year`
  it starts from the nearest existing wood (so draw its first point ON the trunk or limb it should leave), follows
  the path exactly, reaching its end by `until_year`; it is never shed or bent, and branches grow from it by the
  species' own rules. Works at any order: a limb, then a branch drawn on that limb (a later `from_year`). A path
  starting at [0, 0, 0] with `from_year` 0 is the trunk itself (a leaning, forked or twisted trunk).
  `until_year` paces it: the axis advances evenly so that it reaches the path's end in that year, whatever the
  species' own shoot speed (without it: ~2 segments a step). `"bare": m` leaves its first metres without side
  branches (a limb bare near the trunk, foliage on its outer part). `habit.clear` holds on a drawn trunk too.
  The path is splined through its points (`"straight": true` keeps corners). `"on": "<guide name>"` or
  `"on": "trunk"` makes it leave that axis; otherwise it leaves the stoutest wood near its first point.
  The report says, per guide, its order, whether it was drawn to its end, and how many branches left it.
- `cuts`: `[{"year": 10, "above": 2.5, "every": 6, "until_year": 34, "sprouts": 6}]` (edit_plant op `cut`): the
  management and accidents that give a tree its character. The wood in the volume (the same volumes as `prune`)
  is cut AT that year, again every `every` years up to `until_year` (default the tree's age), and each stub then
  sprouts `sprouts` new shoots (0 = a dead stub) which grow on by the habit: a **pollard** (`above` the trunk
  height you want, every 4-8 years: a column trunk with a knuckled head of rods; make the rods straight and upright
  with tropism + low jitter on orders 1+ and `max_order` 2), a **coppice** (`above` 0.3), a **lopped limb** or a
  **storm break** (a box or sphere round it, one year, sprouts 0-2). `"boll": 1.4-1.8` swells the cut end into
  the knuckled head a pollard gets from being cut again and again. Timing: the first cut after the trunk has passed
  the cut height (the report warns when a cut found nothing); the LAST cut 4-8 years before the tree's age
  (`until_year`), or the head is two-year stubble; `habit.clear` must be under the cut height (a bole that may
  never branch can't sprout). A pollard's `height` is ignored (it sizes the uncut tree). The report lists each cut made. A cut the tree
  never regrows from is a `prune`.
- Named limbs: the report lists the tree's main limbs ("SW2" = the second limb up the trunk that ends to the
  south-west; +y is north, +x east) with where each leaves the trunk, its girth, its end, and the span of what it
  carries. `edit_plant` op `{"op": "take_limb", "limb": "SW2", "name": "low_bough"}` makes that grown limb a guide of
  the same place and shape; then redraw it (op `guide` with a new path), or give `"path"` at once. The names
  belong to THIS grown tree: after an edit the other limbs may be renamed or change (the tree regrows around every
  edit), a taken limb keeps its name and path. Each limb also has an **id** ("Lk7f3", from its bud's lineage) that
  lasts through edits; wherever a limb is named (`dead`, take_limb) a compass name, an id or a guide's name works,
  and a compass name is stored as the id. "Length" follows the limb's stoutest wood to a shoot's end.
- `prune`: `[{"box": [[lo], [hi]]}, {"sphere": [[c], r]}, {"above": z}, {"below": z}, {"under": z}]`. `below`
  removes limbs that LEAVE the trunk under that height (a limb starting higher may still hang lower); `under`
  removes everything but the trunk under that height (a browse line, a lifted crown); `above` tops the tree.
  A prune is a clean cut on the finished tree: nothing else changes. With `"from_year"` the cut is kept from that
  year on while the tree grows, and it answers (the freed light and growth go elsewhere, so the rest changes too).
  In a `grow_plant` patch `"prune": [...]` replaces the whole list and `null` removes all: use `edit_plant` ops
  (`prune`, `remove_prune` by index, `clear_prunes`) to change one.
- Edits that feed back into growth (habit numbers, guides, wind, a prune with `from_year`) change the whole tree
  somewhat: buds compete for the same light and growth. Randomness is tied to each bud's lineage, so what an edit
  doesn't shade or starve keeps its shape, but expect the node count to move.
- `envelope`: `{"shape": "ellipsoid" | "cone" | "column" | "dome" | "umbrella", "radius", "top", "base", "soft", "center": [x, y],
  "lean": [dx, dy]}`: a soft crown shape (growth outside it is shaded out). `lean` moves the crown's middle that
  far by its top: a wedge or flag swept downwind. "umbrella" = a flat wide top over a narrow underside (a
  wind-clipped pine): with `{"above": z}` in `prune` it gives a flat top. Use sparingly: an envelope makes a
  clipped look (a pine under a tight envelope reads as topiary: prefer wind + a prune).
- `forces`: `[{"dir": [x, y, z], "strength": 0.1-0.5, "orders": [1, 2]}]`: a steady push on growing shoots (a
  tree reaching over water, limbs swept one way).

### leaves and bark

- `leaves`: `shape` ("ovate", "triangular", "lanceolate", "lobed", or needles: "needle_tuft" round shoot ends,
  "needle_spray" flat sprays), `length` (m: birch 0.05, hawthorn 0.04, oak 0.11), `width` (x length), `lobes`,
  `serrate` 0-0.2, `color` (sRGB 0-1), `hang` 0-1 (leaves hang from the twig).
  `twig` (the unit of foliage: a short shoot with its leaves): `length` 0.2-0.8 m, `leaves` 8-30 on it,
  `arrangement` "alternate" | "opposite" | "spiral", `per_m` 3-12 twigs per metre of young shoot, `steps` 2-6 (shoots
  up to this many growth steps old carry twigs: more = foliage deeper into the crown, a denser mass), `spread`
  25-55 deg off the shoot, `up` -0.9..0.6 (+ twigs turn up to the light, - they hang), `droop` -0.1..1.2 (the
  twig's own sag), `min_order` 1-2, `where` "shoots" | "ends". A thin crown: raise `steps` and `per_m` first.
  Needles: `needle_width` (a needle's width / length: 0.08-0.45 on mesh twigs, far wider than life so they cover
  what hundreds of real needles do), `twig.leaves` 90-220 needles, `twig.side_shoots` (flat sprays).
  `get_plant` lists these with the values in force.
  `leaves.color` is the leaf as you SEE it in the sun (sRGB), not a dark "albedo": a summer birch in a photo is
  about [0.64, 0.7, 0.35] (hue 60-75, value 0.6-0.7), a spruce [0.3, 0.36, 0.2]. Foliage is shaded as a volume
  (`leaves.round` 0.7: each leaf's normal bent outward from the crown's middle); 0 = every card by its own normal
  (dark, spiky).
  Foliage is drawn as cards (each twig's picture on a cut card: what a game draws) by default;
  `look_plant(foliage="mesh")` shows real leaf meshes. `card: {"twig": {...}, "leaf": {...}, "scale" 0.8-1.5,
  "cross" 1 | 2 (2 = two crossed cards: tufts), "strips" 0 | 3-5 (a ladder of quads along a long hanging twig)}`:
  A card's picture should be a SPRAY, not one shoot: `card.twig.side_shoots` 4-8 side twigs (`side_angle` deg off
  the twig: 30-40 a fan, 8-15 hanging strands; `side_length` 0.6-1.0 of the twig; `side_taper` 0.58 = shorter toward
  the tip, 0.1 = even strands; needle sprays: `spray_angle`, `sub_shoots`). One shoot per card read as bamboo.
  `card.twig` / `card.leaf` override the twig and leaf ONLY for the card's picture (which can afford many more,
  thinner leaves or needles than a mesh twig: `card.twig.leaves` 400 with `card.leaf.needle_width` 0.03-0.1).
- `bark`: `kind` ("furrowed" ridges, "plates", "scales", "lenticel" smooth with dashes), `scale` (x the pattern's
  size: 0.5 = finer, for a small tree's trunk), `color`, `twig_color`, `base_color` + `base_height` (+ `base_kind`:
  an old dark foot), `upper_color` + `upper_from` (m) + `upper_blend` (m the change takes; patchy), `twig_radius` ([m, m]: wood
  thinner than the first is all `twig_color`, thicker than the second none; a pine's [0.015, 0.05] keeps the orange
  to its stout wood: every thin branch orange read as a fan of sticks).

## Reading the report

```
form (in leaf, two side views): width/height 1.17, bole 0.20 of the height, widest at 0.50
limbs: 5 first-order branches, leaving the trunk at 69 deg, their far halves 5 deg above level
```
- width/height: 0.3-0.6 columnar/conic, 0.8-1 oval, > 1.1 spreading.
- bole: where the crown starts, measured as the lowest height a quarter as wide as the widest (so one long low
  limb lowers it, and clearing the trunk can move it either way: read "the lowest shoot ends hang at" beside it).
  A forest tree 0.5+, an open-grown oak 0.2, a spruce 0.
- crown line: how far the crown's middle sits from the trunk's foot, as a share of its radius (0.5+ = swept).
- shoot ends: the share pointing steeply down (weeping) or up.
- trunk DIAMETER is at the foot, with its flare.
- limbs' far-half elevation: ~70 = a vase, ~40 = spreading, ~5 = level, negative = weeping.
- WARNINGS name what to change.

With a reference (`plant_reference`): outline IoU 0.75+ with width/height and bole within ~0.05 is a match of the
outline; it says nothing about branch character or foliage: look.

## What goes wrong

- Everything droops to the ground: `sag` too high or `tropism` too negative on low orders; the fit rewards it less
  now, but check `clay`.
- A broom of straight spokes: raise `jitter` on orders 1+.
- A thin sparse tree (few hundred nodes): raise `vigour`, lower `shed`, lengthen `bud_life`.
- Hundreds of thousands of nodes: lower `vigour`, `bud_break` on the high orders, or `max_order`.
- A conifer's branches die as stubs: its shade is too wide/deep for its short internodes: `shadow` [0.03, 3, 2].
- A guide "stops short": more years (`until_year`), more `vigour`, or a shorter path.
- A wind-bent tree lies flat: lower the wind's strength or `force_orders[0]`.
- `height` asked, something else grown: `height` sizes the unedited tree; with a drawn trunk, the path decides.
- Size runs away with age (a 130-year pine at 35 m): presets are tuned at their own `age` (get_plant shows it); for
  an old tree of normal size set `height` or lower `vigour`.
- A conifer in tiers with bare trunk between (a pagoda): whorls break whole or not at all: `bud_each: true`.
- A weeping tree as a column of curtains to the ground: the hanging orders grow for ever and nothing sheds inside.
  Give them `tip_life` (6-8 steps), some `shed` (0.05), and let the order below them run level (`plagio` toward
  20-25 deg) so the curtains start from the crown's OUTSIDE; `prune: [{"under": 1.2}]` is the browse line.
- A conifer's lower half is a cage of bare brown hoops: measure before changing anything. Usual causes: one `ring`
  number thickening every old branch like a trunk (give it per order); needles only on the last years' growth of
  each limb, because the branchlets along it stopped (`tip_life`) or ran on down for metres (`slowing` keeps them
  short and alive); foliage cards too small to hide the limb they hang from.
- An unknown key anywhere (a prune's `until_year`, a misspelt habit key) is refused with the keys that exist.

## A stand or a group

Make one individual, then copies: `grow_plant(name="birch_b", copy_from="birch_a", patch={"seed": 2, "age": 13})`.
Give them the same `environment` (e.g. `setting: "forest"`). See them together with
`look_plants(names=[...], spacing=2.5)`: the only way to judge whether they belong together. Export each
(`export_plant(name, triangles=12000)`).

## A forest set: one description, several plants

`grow_plant(name, patch={"set": {"count": 5}})`: the plant's **set** = the same description grown from other seeds
at a spread of ages (`"age": [0.55, 1.0]` shares of the plant's age, youngest first; or `"ages": [years...]`), with
`"vigour": 0.12` (+-12% each), `"height": [lo, hi]` m, `"lean": deg` (each trunk leaning its own way), `"patch"`
(a patch for all, or a list of one per plant). A set is the species, not copies of one tree: the hero's guides,
prunes and one-off cuts are dropped (`"keep_guides": true` keeps them; repeated cuts, i.e. management, stay).
The report lists each plant (`name#1`...). `look_plants(["name#*"])` shows them together, `look_plant("name#3")`
one; `export_plant(name, set=True)` writes one file with a node per plant sharing the bark and foliage materials.
To turn a set's plant into a hero: `grow_plant("hero", copy_from="name#3")`. For a forest use
`environment.setting: "forest"` on the plant: the whole set grows with clear boles and high crowns.

## A species is a habit at EVERY age: `plant_form`

A habit tuned on one photo is one point. The Scots pine preset fitted to a single 80-year open-grown photo was a
bare pole with three limbs at 35 years, as wide as tall at 80 and wider than tall (dbh 2.9 m) at 150; in a stand it
was a crooked stick with antlers. `plant_form(name | species=)` grows the plant at several ages in the open, on a
stand's edge and inside a stand, and measures what foresters measure: height, crown width / height, live crown /
height, the height of the widest level, dbh. Give each case target bands and it marks the misses; give `fit` and it
searches habit numbers for the least miss over all cases at once (`vegetation.fit_form`).

Where targets come from, best first: yield tables and crown studies (height and dbh by age and stocking; crown
ratios of stand trees), species accounts (final height, girth, "conical when young, rounded or flat-topped when
old"), and boxes read off whole-tree photographs of known setting (tree box and crown box in pixels: width / height
and crown / height need no scale). Write down which is which: `workspace/veg_refs/pine_form/` has the pine's.

What moves form with age (habit keys):
- `slowing[0]`: height growth tails off (a pine: 6 m at 15, 12 m at 35, 21 m at 80, 30 m at 160).
- `limb_pace` [-, 0.9, 0.75]: no side shoot outgrows that share of the leader's pace AT THAT AGE: the whole tree's
  shoots shorten together. Under 1 the leader stays ahead for life (a spire; a pole in a stand); near or over 1 old
  limbs catch it up (a rounded or flat old top). Without it, limbs born late outgrew an old slow leader.
- `tip_life[1]`: limbs stop reaching after that many steps and then die back: the crown base lifts on a veteran.
- `ring` per order + `pipe`: girth. In a stand `sdi_max` caps it by the stocking (Reineke: stems / ha x (dbh / 25
  cm)^1.6 <= the species' most; spruce 1500, pine 1000): 3 m apart a 50-year spruce is 30 cm, not 42.
- `clear` is NOT how a bole forms (it made a pole at every age): young trees branch from the ground and shade
  (`shed`, in a stand `stand_shed`) lifts the crown.
- Wood past its last living branch (no tip, bud or leaf beyond it) is shed like a shaded branch.

## A forest: `grow_stand`, `look_stand`, `export_stand`

A forest in a game is a KIT stood many times: per species a few interior trees (bare stems, dead branches, a small
live top) and edge trees (foliage down the open side), at three levels of detail, plus a floor. `grow_stand(name,
spec)` grows the kit and lays the plot out; the reply is the forester's table (stems / ha, mean height and dbh,
basal area, live crown ratio, canopy cover) with warnings: basal area over ~70 m2 / ha = stems too stout for the
spacing; canopy cover under 60% = scattered trees, not a forest.

    grow_stand("spruce_wood", {"species": "norway_spruce", "age": 50, "spacing": 3.0, "size": [60, 84],
               "edge": ["s"], "floor": {"ferns": 0.03}})
    look_stand("spruce_wood", views=["inside", "edge"])
    export_stand("spruce_wood")      # GLBs per variant (LODs + impostor), floor meshes, layout.json

- Stages, as environment artists work: (1) ONE interior tree and ONE edge tree per species right, by `plant_form`
  and `look_plant` (bare stem, dead zone, live crown ratio against photographs of stand interiors); (2) the stand's
  numbers (spacing for the age: 2-2.5 m young thicket, 3-4 m pole stage, 5-7 m old; mixed species by `share`);
  (3) `look_stand` from inside at eye level and from outside an open edge, beside photographs; (4) the floor;
  (5) export and the engine's scatter.
- Levels of detail: `lod.near` / `lod.mid` (m from the eye) and `budgets` [full, mid triangles, far triangles]. A
  look draws at most `max_full` trees with every twig (a laptop GPU lost its context at 60 full spruces; trees of
  one variant and level share one mesh and one set of textures). Far trees at ~1500 triangles stand in for
  impostors in looks; the export writes real impostors.
- What makes an interior read as a forest and not as a row of poles: the dead zone (the species' `dead_keep`,
  dead-twig cards: `leaves.parts.dead`, a picture drawn as an irregular tangle: `forks`, `depth`, `crook`,
  `broken`, `lichen`); distance haze (`haze.distance` 60-120 m: far stems pale and merge, the horizon closes);
  the canopy's diffuse light (`light.ambient`: EEVEE has no sky light under a closed canopy, without it the
  interior is night); a floor that is not one colour (`floor`: brash under the stems, stumps, ferns where light
  reaches, moss patches, litter flecks); a plot deep enough that no sky shows between the stems at eye level
  (60+ m of trees ahead of the eye at 3 m spacing).
- At a budget a dead zone is a HAZE: `veg_bough.DEAD_SHARE` of the bough cards at most draw dead wood (the longest
  bough of each height band), baked from half its twigs. Every dead bough carded was a brown fur on the stem.

## By hand in Blender

`sync_plant(name)` writes `workspace/plants/<name>/plant.blend`: the plant with its guides (orange curves) and its
named main limbs (blue curves). A person moves curve points there (or a whole limb), adds a curve to the "guides"
collection, or deletes one; the next `sync_plant` brings that back as spec edits (a moved limb becomes a guide)
and writes the file again. The spec stays the source of truth: nothing else in the file is read back.

## The export is another object: look at it

A budget leaves out thin wood and draws fewer, larger cards. `look_plant(name, views=["leaf", "far"],
triangles=12000)` renders exactly what `export_plant(name, triangles=12000)` writes. Judge that picture, not the
full-detail one. A budget first gives branches fewer rings and sides, then leaves out the thinnest wood (wood you
marked, dead wood and drawn guides, stays down to a quarter of that girth), and draws the twigs that stand on wood
it kept; the export WARNS when cards would float.
When a budget buys fewer than a quarter of the twigs, the foliage is drawn as **bough cards** instead: the tree's own
limb ends (wood, branchlets, every twig) baked into pictures, each bough seen from its face and from its side on two
crossed cards, standing where the tree has such a bough. The smaller the budget, the larger the boughs the foliage is
cut into, so LODs step down from the same tree (a set shares one bough atlas per LOD). Judge them at the distance
they are for: `look_plant(name, views=["far"], triangles=8000)`. Broadleaves and pines hold up to 8k; a spruce's
low LODs are gappier than the full tree. Raise the budget if the crown falls apart (a game tree: 10-40k; a hero tree 40-100k).

## From a botanical description to our keys

Take leaf and needle arrangement from a flora's TEXT (or a botanical plate), not from photos: photos are for the
whole tree's read and for colour. What a description says, and the key it sets:

| the flora says | key | values |
|---|---|---|
| leaves alternate / spirally arranged (2/5, 3/8) | `leaves.twig.arrangement: "spiral"`, `divergence` | 144 (2/5), 135-137.5 (3/8), 120 (1/3): the fraction is geometry; which species has which is an ASSUMPTION here |
| leaves alternate in two ranks (distichous: elm, beech, lime) | `arrangement: "alternate"` | |
| leaves opposite (maple, ash) / whorled | `arrangement: "opposite"` / `"whorled"` | |
| leaf blade length, width / length | `leaves.length` (m), `leaves.width` | oak 0.10-0.12, 0.65; birch 0.03-0.07; willow 0.04-0.16, 0.12 |
| petiole length / blade length | `leaves.petiole` | oak 0.03 (2-3 mm stalk); birch 0.3-0.5 (slender: the leaves tremble) |
| leaves or shoots pendulous | `leaves.hang`, `twig.up` < 0, `twig.droop`, habit `tropism` < 0 on the last orders | |
| sun leaves at all angles / shade leaves in a flat mosaic | `twig.light` 0-1 (blades turned to the sky), `twig.face` 0-1 (whole twigs flat to the sky) | sun 0.3-0.6, shade 0.8-1 |
| needles singly on pegs all round the shoot (spruce) | `leaves.shape: "needle_spray"`, `twig.needles: "radial"`, `parted` (thinner underneath), `forward` | |
| needles in fascicles of 2/3/5 on dwarf shoots (pines) | `shape: "needle_tuft"`, `twig.needles: "fascicles"`, `card.twig.fascicle` 2/3/5, `card.twig.needle_angle` [75, 30] (old needles stand out, the youngest lie forward: a bottlebrush), `card.twig.bud`, `card.cross` 2 + `card.end` true (a card across the shoot: the tuft is round from its end too) | |
| needles flat, in two ranks with a parting (fir, yew, hemlock) | `twig.needles: "ranked"` | |
| needle length | `leaves.length` | spruce 0.01-0.025, Scots pine 0.04-0.06 |
| needles persist N years | `leaves.retention` (years) | spruce 4-10, Scots pine 2-6 |
| branches in regular whorls | habit `whorl`, `buds` | |
| branchlets pendulous from level limbs | habit `tropism` < 0 and `tip_life` on that order | |
| crown conic / domed / flat-topped / columnar | habit `apical`, `apical_old`, `leader`, `tip_life`, `uneven` | |
| bark | `bark.kind` (furrowed, plates, scales, lenticel) + colours, `upper_color` | |

What the presets rest on (quoted from the sources):
- Norway spruce: needles "four-sided and attached singly to small persistent peg-like structures (pulvini)", staying
  "between four and ten years", branches "in regular whorls" (en.wikipedia.org/wiki/Spruce); leaves "1-2.5 cm, 4-angled
  in cross section", "light to dark green", branches "the upper level or ascending, the lower drooping", "crown conic"
  (conifers.org/pi/Picea_abies.php).
- Scots pine: needles in fascicles of "two", "(2.5-)4-6(-9) cm long", "moderately to often strongly glaucous",
  "persisting for 2-6(-9) years"; crown "dense, broadly domed or even flat-topped"; bark "thick, scaly-plated,
  grey-brown" low, "thin, flaking, orange-red" above (conifers.org/pi/Pinus_sylvestris.php).
- Silver birch: "the twigs are slender and often pendulous"; leaves "triangular with broad, untoothed, wedge-shaped
  bases, slender pointed tips", "3 to 7 cm long", "short, slender stalks"; bark white, with age "irregular, dark, and
  rugged" at the base (en.wikipedia.org/wiki/Betula_pendula).
- Pedunculate oak: crown "spreading and unevenly domed ... massive lower branches"; leaves "arranged alternately along
  the twigs", "10-12 cm long by 7-8 cm wide, with a short (typically 2-3 mm) petiole", "3-6 rounded lobes"; bark
  "greyish-brown and closely grooved, with vertical plates" (en.wikipedia.org/wiki/Quercus_robur).
- Weeping willow: leaves "alternate and spirally arranged, narrow, light green, 4-16 cm long and 0.5-2 cm broad",
  "gold-yellow in autumn"; shoots "yellowish-brown" (en.wikipedia.org/wiki/Salix_babylonica).
ASSUMPTIONS, not from a source: the `divergence` fraction given to each preset (oak and willow 144 = 2/5, birch
120 = 1/3) and every `light` / `face` value (how far blades and twigs turn to the sky) were set by hand from general
botany, and the SpeedTree manual's leaf pages refused the fetch. Replace them when a flora states the phyllotaxis.

## Game-ready: LODs, wind, seasons, collision

`export_plant(name, triangles=20000, lods=3, impostor=True, seasons=["summer", "autumn", "winter"], wet=True,
lod_files=True)`:
- **LODs**: 100 / 45 / 18% of the budget from the same tree, then (impostor) two crossed quads with the plant's
  picture. `<name>.glb` shows LOD 0 and hangs the rest on it (MSFT_lod; extras list each LOD's triangles and the screen
  height to switch under). `lod_files` writes `<name>_LOD<k>.glb` too: most engines take LODs as separate meshes.
- **Wind**: every vertex carries trunk sway (0 at the foot, 1 at the top), branch sway (0 where its limb leaves the
  trunk, 1 at the limb's end), a phase per limb, and leaf flutter (0 at a card's foot, 1 at its tip): TEXCOORD_1 =
  (trunk, branch), TEXCOORD_2 = (phase, flutter), and all four in `_WIND`. The shader recipe is in the file's extras.
  `wind_plant(name)` renders the export swaying by that recipe: look at it (the foot still, limbs out of step).
- **Seasons** are states of the plant (`"season": "summer" | "autumn" | "winter" | "bare" | "dead"`, `"snow": 0-1`,
  `"wet": 0-1`, `leaves.autumn` = the autumn colour; evergreens keep their needles and colour) for the looks, and
  material variants in the export (KHR_materials_variants: summer / autumn / winter / snow / wet). Snow lying on wood
  is an engine shader (by the normal's up component; recipe in extras): the "snow" variant only frosts the leaves.
- **Collision**: capsules along the trunk and main limbs (extras) and a low `<name>_collision` mesh.
- What importers do with the file (checked here: Blender 5.1, Godot 4.7; Unity and Unreal are NOT checked: nobody has opened these files there):
  Blender brings in every node (hide LOD1+ and `_collision`), flips v on every uv set (branch = 1 - uv1.v, flutter =
  1 - uv2.v; `_WIND` arrives unflipped as an attribute) and reads the variants. Godot imports the scene's nodes only
  (LOD 0; use the LOD files), keeps TEXCOORD_1 as UV2 unflipped and TEXCOORD_2 as CUSTOM0, drops `_WIND`.

## Small plants: grass, ferns, flowers, groundcover, palms (assembled, not grown)

Game foliage artists do not grow a grass tuft: they make a few PICTURES (a fan of blades, a frond, a flower head),
cut each onto a card as tight as its outline, and ARRANGE cards in a clump; clumps are scattered by the thousand.
So a small plant here is `"plant": "clump"`: `leaves` (+ `leaves.parts`) are its pictures, `clump.layers` its
arrangement. Everything downstream is the tree's: `grow_plant`, `look_plant`, `export_plant` (budgets, LODs, wind),
sets (`set: {"count": 5}` = variants to scatter). Presets: `meadow_grass`, `fern`, `daisy`, `clover`, `feather_palm`;
`shrub` is GROWN (a tree with `habit.stems` 6: bushes branch like trees). `get_plant(species="fern")` shows a
preset's pictures and layers with what each layer key means.

Stages, as for a tree: (1) reference: height, spread, what the eye reads (a shuttlecock of fronds; white dots over a
green mat); (2) the pictures: look at the atlas (`look_plant` shows it for a clump); a picture must read by its
outline; (3) the arrangement: layers; (4) the look from standing height AND from above (that is how small plants are
seen); (5) the export at 50-600 triangles a plant.

```json
{"species": "daisy", "seed": 3,
 "leaves": {"parts": {"head": {"twig": {"flower": {"petals": 13, "color": [0.95, 0.8, 0.2]}}}}},
 "clump": {"size": 1.2, "layers": [
   {"name": "rosette", "part": "main", "count": 7, "ring": [0, 0.02], "lean": [62, 84], "facing": "up"},
   {"name": "stalks", "part": "head", "count": 4, "ring": [0, 0.04], "lean": [4, 20], "stem": [0.2, 0.36], "tilt": 78},
   {"name": "leaves", "part": "stemleaf", "count": 8, "on": "stalks", "along": [0.15, 0.7], "lean": [30, 60]}]}}
```

Layer keys: `part` (which picture), `count`, `ring` [m, m] from the middle, `lean` [deg, deg] off upright (0-25 a
standing tuft, 30-65 arching fronds, 70-90 a rosette on the ground, over 90 hanging), `scale`, `facing` ("up" =
the card's face to the sky: fronds, rosette leaves; "any" = standing cards turned any way: grass), `stem` [m, m]
(a stalk carries the card at its top; `stem_radius` 0 = the stalk is not drawn: leaves seen from above), `bend`,
`tilt` (90 = the card lies across its stalk's top: a daisy's head, a clover leaf), `on` + `along` (stand on another
layer's stalks: a palm's fronds on its trunk, leaves up a flower's stalk), `trunk` (the stalk is a barked trunk),
`clump.size` (the whole plant's scale). In a `grow_plant` patch `clump.layers` is replaced whole.

Pictures: `leaves.shape` "linear" (grass blade) / "strap" / "round" / "petal" besides the trees' shapes;
`twig.arrangement` "basal" (every leaf from the foot: a tuft) or "pinnate" (pairs along the stalk, `taper`: a
frond); `leaves.bend` (blades arc); `twig.flower` {form "ray" | "cup" | "spike", petals, radius, color, center};
`card.strips` 4-5 for long arching fronds (the card bends with `twig.droop`). `leaves.parts` = {name: overrides}.

What the practice is, and where it comes from: cards in clumps, normals pointing UP (or taken from a dome) so a
clump shades with the ground instead of flickering card by card (polycount's foliage threads; here
`leaves.normals: "up"` is the default for clumps); few distinct assets per ecotope, scattered by density maps
(Guerrilla, "GPU-based procedural placement in Horizon Zero Dawn", GDC 2017); grass in clumps that share height
and lean, wind by height along the blade (Sucker Punch, "Procedural Grass in Ghost of Tsushima", GDC 2021). Wind
here: each card bends from its foot in its own phase; long cards swing further.

What goes wrong: cards all upright in a tight ring read as a shaving brush (widen `lean`, add an outer layer of
shorter, flatter cards); a rosette that floats (lean 70+, `sink`); one picture repeated reads as a stencil (3-4
`card.variants`); thousands of triangles in one tuft (the report warns over 3000; scatter wants 50-600).
Not built: scattering on terrain, grass as GPU blades, ivy and creepers that follow a surface, fan palms, bamboo,
reeds in water, mushrooms, per-plant colour maps from a terrain, bent/trampled states.

## Not built yet

Say so in your report instead of faking it: LODs, wind animation data, autumn/snow/wet variants, collision
proxies; style sheets (blob to photoreal); a multi-stem base, exposed roots, burrs,
fluted trunks, surface roots running out over the ground, hollows and cavities; thorns, flowers and fruit on twigs; banks, ditches and shorelines (only a slope and a
water level); a tree that sees the other plants you made (use `setting`/`neighbours`).
