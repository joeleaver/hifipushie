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
crossed cards, standing where the tree has such a bough. How the foliage is cut for a budget (`veg_bough.fit`):
- While the foliage's triangles buy at least 8% of the tree's FINEST cut (boughs of about two twig lengths) on
  seven-corner cards (10 triangles a crossed pair), the LOD is that finest cut THINNED: at most 45% of its boughs
  even at LOD 0 (more only stack layers: overdraw), spread evenly through the crown, each drawn larger until together
  they cover what the whole cut covered (measured on the cards' own polygons from two sides).
  LOD 0, 1 and 2 then share ONE atlas, one material slot and one silhouette, and nothing pops at a switch. This is
  what a foliage artist does (remove cards, grow the rest). A 20k conifer's three LODs are all of this kind; the
  triangles the foliage doesn't use go to finer wood.
- OVERDRAW is the cost of card foliage, not triangles: a stand of 20k spruces that drew 6.6 card layers per covered
  pixel cost 1.6x the GPU time of a stylised spruce with as many triangles. Read `card area / covered` per LOD
  (the export's check, /mnt/data/hifipushie/realtrees/od_glb.py) and aim at 4-5 for LOD 0, 3-4 for LOD 1. And give a
  FOREST its stand forms (`environment.setting: "forest"`, `spacing`): open-grown conifers planted 3.5 m apart put
  the player's eye inside six skirts of foliage; an interior tree has a bare stem at eye level and a tenth of the cards.
- Under that, the tree is re-cut into fewer, larger boughs (whole limbs at a few hundred cards) on seven-corner
  cupped cards, its own atlas. A re-cut next to a fine cut does pop: in Godot a spruce's whole-limb LOD 1 covered
  0.85 of its LOD 0 and lost its top; and MID-sized boughs (2-3 m) on any card read as palm fronds or round leaves
  from 30 m. Fine or whole limbs, not between.
Judge every LOD at the distance and PIXEL SIZE it is drawn at (a 26 m tree at 64 m is ~310 px of a 1080p screen: a
6 m piece of crown is 150 px; needle detail is not there, silhouette and tone patches are), and in the engine
(`spikes/godot_veg/cards.gd`: covered area at each switch; overdraw = summed card area / covered area).
Raise the budget if the crown falls apart (a game tree: 10-40k; a hero tree 40-100k).

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
- **Seasons** are states of the plant (`"season": "spring" | "summer" | "autumn" | "winter" | "bare" | "dead"`, `"snow": 0-1`,
  `"wet": 0-1`, `leaves.autumn` = the autumn colour; evergreens keep their needles and colour) for the looks, and
  material variants in the export (KHR_materials_variants: spring / summer / autumn / winter / snow / wet). SNOW IS THE
  WINTER STATE WITH SNOW ON IT: the same slots hidden and shown as in winter (a leaf-dropping plant: crown hidden, the
  bare wood and a style's forks shown; an evergreen keeps its crown, whose `snow` variant is the ready-mixed pale colour /
  frosted picture; a clump by its own winter state), and the snow impostor is the bare tree under snow. Snow lying on
  wood (and per pixel on anything) is the engine's shader: `<name>_seasons.json` `snow` gives the numbers our looks use
  (linear colour, coverage, the normal's up threshold `by_normal.from` / `to` and the formula).
- **Collision**: capsules along the trunk and main limbs (extras) and a low `<name>_collision` mesh node (outside the
  scene), and `<name>_collision.glb`: the same mesh as a file, its node IN the scene and named `<name>_collision-colonly`
  (Godot's importer makes a static body of a node so named and drops the mesh).
- **The impostor** (`impostor=True`) is HEMI-OCTAHEDRAL: the plant baked from 8 x 8 directions spread over the upper
  hemisphere (an octahedral grid: the border of the atlas is the horizon, its middle straight down) into one atlas, and
  drawn as ONE quad that the engine's shader turns to the camera, blending the four baked views nearest the camera's
  direction (one parallax step by a depth map, so neighbouring views line up). It holds from the horizon to looking
  straight down: two crossed quads read as a cross or a bird from a hill (the consumer's island has a 330 m volcano).
  What engines do (Ryan Brucks' octahedral impostors for UE, https://shaderbits.com/blog/octahedral-impostors; Amplify
  Impostors, https://amplify.pt/_AI; the Godot port https://github.com/SIsilicon/Godot-Octahedral-Impostors): the
  hemisphere variant for things never seen from below (twice the resolution of the full sphere), frame blending.
  Maps: albedo (unlit, the shade of what stands above each point baked in at half strength: an engine casts no shadow
  inside a picture) with alpha; an OBJECT-SPACE normal map (glTF axes, rgb * 2 - 1: the quad turns, so tangent space
  means nothing) with the depth behind each view's middle plane in its alpha (not a glTF normalTexture: it is in the
  impostor material's `extras.hifipushie_impostor.normal_texture_index`, and as `impostorNormalTexture` files in the
  seasons json). A picture per season (seasons with the same shape share the normal / depth / shade frames: only the
  albedo is rendered again). extras / the seasons json `impostor`: `frames`, `size` (each view's square, m), `centre`
  (glTF), `recipe` (the shader in words) and `shader`: `spikes/godot_veg/impostor_octa.gdshader` is a reference
  Godot 4 shader to drop in (uniforms from those numbers; MeshInstance3D.extra_cull_margin = size / 2, since the
  stored quad is a vertical square; no shadows received). `veg_impostor.view(atlas, direction)` draws in numpy what
  the shader draws (the tests hold the bake to it). Cost: ~4 min of Blender for the first shape of the plant (64
  views x albedo, normal, Cycles shade, depth), ~1 min for each further season. `impostor="cross"` keeps the old two
  crossed quads (any viewer draws them without a shader; from the side only): albedo + tangent-space normal map,
  front and back faces of their own, and the engine must not let the quads RECEIVE shadows (a dark wedge).
  Installing it in Godot 4 (what `spikes/godot_veg/octa.gd` does): (1) copy `impostor_octa.gdshader` into the project;
  (2) import `<name>_LOD3.glb` (the impostor LOD file) and read `<name>_seasons.json`: `impostor` = {frames, size,
  centre}, `seasons.<season>.impostor` = the season's `baseColorTexture.file` (albedo atlas) and
  `impostorNormalTexture.file` (object-space normal + depth); (3) make a ShaderMaterial with that shader and set
  `albedo_atlas`, `normal_atlas` (load the PNGs; generate mipmaps), `frames`, `size`, `centre`; (4) on the impostor's
  MeshInstance3D set `material_override` to it and `extra_cull_margin = size / 2` (REQUIRED: the stored quad is a
  vertical square, the drawn one turns to the camera and leaves that box from above, so without the margin Godot culls
  it while it is on screen); (5) leave casting shadows on, receiving off (the shader's render_mode already has
  `shadows_disabled`); (6) per season swap the two textures. `impostor="cross"` (export_plant) writes the old two crossed
  quads instead: any viewer draws them with no shader, from the side only.
  Measured in Godot 4.7.2 (blobby oak, impostor vs LOD 2, three azimuths, orthographic, one sun; octa.gd +
  octa_measure.py): elevation 0 / 20 / 45 deg: coverage 1.01 / 1.01 / 1.02, luma 0.99 / 0.98 / 0.98, outline IoU 0.975 /
  0.939 / 0.910. The crossed quads on the same tree: coverage 0.96 / 0.92 / 0.66, luma 1.01 / 0.89 / 0.74, IoU 0.89 /
  0.84 / 0.63 (from a hill they read as a cross).
- **`<name>_seasons.json`** beside the GLB (written whenever there are variants). It LEADS with `contract`
  {"version", "changes" per version, "rule"} and `slot_list` [{"slot", "on": [{"mesh", "primitive"}], "hidden_in":
  [seasons], "channels": the vertex attributes on it}]: an engine that maps materials by slot name should refuse a
  version or a slot it doesn't know (a new slot drawn by default was how `bark_forks` showed in summer). Then:
  variant -> per material slot (the default material's name: bark, bark_forks, foliage, foliage_boughs<k>, impostor)
  its baseColorFactor, roughness, alpha mode and cut-off, `hidden`, `receive_shadows` (when false), and the base
  colour and normal pictures (image index in the GLB + the same PNG written beside it). For engines that drop
  KHR_materials_variants.
- **The export contract** (`veg_export.CONTRACT`, in the GLB's extras.hifipushie_plant.contract and the seasons
  json): version 10. 1 = slots bark / foliage (/ foliage_boughs<n>) / impostor, wind channels, COLOR_0, variants,
  collision file, seasons json. 2 = styled deciduous plants add slot `bark_forks` (the wood mesh's second primitive:
  hidden except in bare seasons); impostor pictures per season. 3 = impostor normal map + TANGENT + 16 vertices, its
  second picture no longer mirrored, baked shade; seasons json contract + slot_list + normal PNGs. 4 = style anime
  (leaf-cloud foliage: alpha-MASK cards with a dab atlas, TEXCOORD_3 = (clump gradient, clump id), Godot CUSTOM0.zw);
  seasons json `snow` numbers + `style`; impostor shade eased on bright colours. 5 = the `snow` variant of a
  leaf-dropping plant is its WINTER state (foliage hidden, `bark_forks` shown), not the crown painted white. 6 = the impostor
  is hemi-octahedral (one quad turned by the engine's shader, an N x N atlas of views, object-space normal + depth in
  `extras.hifipushie_impostor`, `impostorNormalTexture` files, the seasons json `impostor`, null for a plant exported
  without one: small plants); `impostor="cross"` = 5's quads;
  slot `heads` carries COLOR_0 (each part's colour: petals / dab / ball, the flower's centre, the stalk) under a white
  baseColorFactor. 7-9: see CONTRACT_LOG (ramp textures, cropped impostors, pixar's foliage_cards). 10 = the
  groundcover GRADE of small plants (its own folder; one `foliage` slot of single-sided alpha cards with TANGENT +
  a normalTexture per season, no COLOR_0; see "Groundcover grade"). Whoever adds,
  renames or re-purposes a slot or a vertex channel bumps the number and adds a line to CONTRACT_LOG and here.
- What importers do with the file (checked here: Blender 5.1, Godot 4.7; Unity and Unreal are NOT checked: nobody has opened these files there):
  Blender brings in every node (hide LOD1+ and `_collision`), flips v on every uv set (branch = 1 - uv1.v, flutter =
  1 - uv2.v; `_WIND` arrives unflipped as an attribute) and reads the variants. Godot imports the scene's nodes only
  (LOD 0 of the combined file: use the `_LOD<k>.glb` files; a node outside the scene, the collision mesh, never
  arrives: use `<name>_collision.glb`), keeps TEXCOORD_1 as UV2 unflipped and TEXCOORD_2 as CUSTOM0, drops `_WIND`,
  drops KHR_materials_variants entirely (only the default season's materials arrive: read `<name>_seasons.json`), and
  its default material ignores COLOR_0 (switch vertex colour on: a style's mass tones live there). Checked by the
  pushieworld demo in Godot 4.7.2.

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
`card.variants`); thousands of triangles in one tuft (the report warns over 3000; scatter wants 50-600: export the groundcover grade below).
Not built: scattering on terrain, grass as GPU blades, ivy and creepers that follow a surface, fan palms, bamboo,
reeds in water, mushrooms, per-plant colour maps from a terrain, bent/trampled states.

Through the year (`"season"` on the spec, the export's season variants; realistic and styled alike): a clump has
states, `clump.seasons` = {"spring" | "summer" | "autumn" | "winter" | "snow": {"color": [r, g, b] or {"mix": [r, g, b],
"amount": 0-1} (what the leaf colour goes to), "flatten": 0-1 (how far the cards lie down: winter grass), "scale"}},
merged over the defaults (spring: fresher and 0.8 the size; autumn: toward straw; winter: brown straw, flattened 0.6,
0.85 the size; snow = winter under snow). A layer shows only in its own `"seasons": ["summer", "autumn"]` (seed heads,
flowers in their months; default: always). A plant that isn't `leaves.evergreen` has died back in winter unless it
sets a winter state. In looks the plant is assembled in its season (flattened, smaller, layers gone). In the EXPORT
the geometry is the summer plant's and a season is a material variant: its colour, and the pictures of layers out
of season blanked in that season's atlas (styled: the `heads` slot hidden); flatten and scale are not in the file
(an engine can lean the cards by the wind channels; said in the reply).

### A field of grass: the sward (`"species": "sward" | "sward_mown" | "sward_rough"`)
Tufts scattered on a grid read as tufts on bare ground, not as a field. Plain grass is a SWARD: a 2 m TILE of blades
(no seed heads, no stalks), tiles laid edge to edge. What engines do: blades, not clumps: Ghost of Tsushima draws
~100k instanced blade ribbons in tiles round the camera, thinned and widened with distance, and past the grass
distance the terrain's own grass texture takes over in the same colour (Wohllaib, GDC 2021); card patches (alpha
quads with blades painted on) are the older way. Measured here in Godot with the game's shader (meadow, realistic,
standing at 1.7 m): card patches at 7 cards / m2 hide the ground as well for a third of the GPU time, but from 2-8 m
they read as a maze of little hedges (you see every card's line); tufts on the game's 0.9 m grid hide 10-40% of the
ground; blades hide 38 / 78 / 94 / 100% at 2 / 6 / 12 / 30 m. So: blades.
- `sward` keys: `variant` mown (4-6 cm, 1100 blades / m2) | meadow (14-30 cm, 520) | rough (22-55 cm, 380, straw
  mixed in), or the numbers themselves: height [lo, hi], density, width, lean [lo, hi] deg, bend deg, drift (share of
  blades leaning with the tile's combed direction), clump (patchiness), dry (share of straw blades), tone [lo, hi],
  ground / tip / straw colours, size (the tile, 2 m), lods [[share of blades, width x, segments], ...], rings (m: LOD k
  inside rings[k]), fade [start, end] m. Unknown keys are refused.
- Tileable by construction: roots jittered on a torus, every variation periodic noise over the tile; blades lean out
  over the edge into the neighbour. Place with random quarter turns, no random scale, no thinning.
- LODs are subsets of the same blades, wider so the ground covered stays about the same (share x width = 1): near 3
  segments a blade, from the second ring one triangle. Undersides are triangles of their own (normals never point down:
  an engine's back-face flip made black blades). The four meshes only bound the vertex count: what is DRAWN thins PER
  BLADE in the vertex shader (each blade has a rank; as the share for its distance passes the rank it sinks into the
  ground and the blades left widen), so LOD k's mesh at its ring draws exactly what LOD k - 1's draws there. Switching
  whole tiles showed as darker tile-aligned squares from above. Recipe + numbers in the seasons json `sward.lod`,
  channels TEXCOORD_4 / TEXCOORD_5, reference lines spikes/godot_veg/sward_blades.gdshaderinc; pick a tile's mesh by
  its NEAREST point. Realistic meadow: 5,000 / 1,200 / 210 / 54 triangles per m2, rings 5 / 12 / 24 m, fade to 60:
  2.0 M triangles round the player (was 3.4 M with rings 8 / 20 / 35 at the same ground hidden: 38 / 76 / 94 / 100% at
  2 / 6 / 12 / 30 m); pixar 2.2 M, anime 1.5 M, cartoon 0.8 M, blobby 0.7 M. The rings are the lever.
- The far end: past `fade.start` the engine shrinks the blades into the ground; from `fade.blend_from` (the second
  ring) to `fade.end` their albedo, NORMAL and roughness go to the ground's (a blade lit by its own normal is lighter
  than flat ground of the same colour, and a specular style shows roughness as a sheen: either left an arc where the
  field ended). Root colour = the terrain style's grass colour of that cover kind, through the plant style's `colour`.
- How a sward ENDS (a path, a pad, forest floor): never by leaving tiles out (a 2 m staircase). The engine gives a
  density 0..1 per blade (the terrain's grass weight at its world xz, or four corner values per tile); the same
  per-blade threshold thins them and they shorten toward the edge (`sward.density`; the blades left do not widen).
- Seasons: each season's factor is the TERRAIN style's seasonal tint of the grass (turf for mown) layer, so blades and
  ground turn together (whole in the json, may exceed 1). Winter is lying straw, not a tint (`sward.winter`: blades
  laid over along a direction that drifts over the world, shorter; laying each blade along its own normal tore
  blades). Snow buries the tile (`sward.snow`: it sinks by the snow depth, tips poke through in straw, the fade colour
  is the snow's); the old snow variant was summer blades tinted pale blue: a green field on white ground.
- Opaque geometry: no alpha, no texture, no mipmaps to set up. Wind = every plant's channels; `sward.wind` says how to
  run gusts across tiles. `sward.renderer` in the json = the six steps of a tile renderer (grid, quarter turns, LOD by
  nearest point, shader order, colour, what the terrain draws under it).
- Styles (sheet block `sward`: width, density, height, bend, tones, tip point | round, tuft + tuft_fan, round, dry,
  tip_light, taper, drift): blobby = few fat round-tipped blades in two tones; cartoon = broad pointed blades in fans
  of three; anime = long sweeping blades in three painted steps, light tips; pixar = a tenth more, slightly finer blades (half again as many cost 5 M triangles).
- Judge it as a FIELD in an engine, never as one tile: spikes/godot_veg/field.gd (tiles over 60 m with their rings and
  fade, eye level and 25 m up, the ground in the terrain's grass colour) + field_measure.py (ground hidden by
  distance, triangles, GPU ms). `look_plant` refuses a sward for that reason.
- Not built: flowers / seed heads mixed into the tile (scatter the groundcover-grade tufts over it), trampling,
  blades following a slope's normal (tiles are flat: fine to ~20 deg), seasons beyond a colour per season.

### Groundcover grade: the same clump for scatter (`export_plant(name, grade="groundcover")`)
(`<name>_seasons.json` says `"grade": "groundcover"`, the triangles per LOD and the mip-scaled alpha recipe: Godot drops material extras. NOT for every plant: the export refuses ferns (a rosette of a few broad arching fronds lies flat or turns into a thicket of strokes on a star of cards, and the full fern is 172-900 triangles), and a realistic daisy keeps 0.17 of its area (thin stalks; its full plant is 406 triangles): where the full plant is under ~1,000 triangles, scatter the full plant.)
A meadow scatters thousands of clumps round the player; the full small plant (270-4,750 triangles at LOD 0, pixar
grass's lush thin blades the most) is a hero asset. What game artists do for scatter: build the clump once at full
detail and BAKE it onto a few cards (SpeedTree / Megascans grass billboards); the far tier a few crossed cards. Here the
bake is the plant exactly as its full export draws it, in its style and in every season, so each style reads as itself.
- Tiers (LOD 0 / 1 / 2): 8 / 5 / 3 vertical cards through the foot (512 / 192 / 36 triangles with a grass's heads; a
  card is a grid that bends with the wind, front and back their own faces). Each card shows only what stands in its own
  wedge round the foot, square on: every blade is drawn ONCE, near where it really is (crossed cards that each show the
  whole clump draw it n times, doubled where they cross). Parts are kept whole (a blade, a leaf) when they point one way
  from the foot; a fan joined at its root is cut by pixel. Flower / seed heads (compact parts high on the plant,
  gathered into heads) get two small crossed cards each (a round head on a wedge card seen along it is a sliver); a
  low wide plant (clover, a fern's rosette) also gets a card lying flat, baked from above.
- Pictures: rendered 2x and averaged (a thin blade's coverage is its alpha; drawn from 0.28 coverage), the clump's shade
  baked in, a tangent-space normal map; each tier at the size it is seen at (448 / 128 / 64 px). Normals lean up (the
  ground's light) and toward their own face (straight up, a card seen from the side caught the styles' rim light).
- Seasons are variants of the one `foliage` slot (winter = the plant regrown lying, snow = winter under snow); no bark /
  heads slots: stalks and heads are in the pictures. Files in their own folder (default export_groundcover/):
  <name>_LOD0..2.glb, <name>.glb, <name>_seasons.json. First export ~5-10 min of Blender (cached by the spec).
- ENGINE, alpha through mipmaps: plain mipmaps average a thin blade with the air beside it and an alpha test drops it
  (pixar grass LOD 0 lost 93% of its area by 12 m in Godot). Import the textures WITHOUT mipmaps (coverage holds,
  some shimmer), or WITH them and alpha scaled up by the mip level in the shader (recipe in the material's
  extras.alpha_mips; 0.76-0.98 of the full plant's area from 2 to 12 m). Turn the importer's own mesh LOD generation off.
- Judge it in the engine against the full LOD 0 (spikes/godot_veg/meadow.gd "solo" + ground_measure.py: area, IoU,
  colour per distance) and as a meadow (meadow.gd: the game's placement, thinning and budgets).

## Styles: the same plant dressed another way

`"style": "realistic" | "blobby" | "anime" | "cartoon" | "pixar"` on the spec (grow_plant, a set's plants; pixar since
round 5). A style NEVER changes the growth: species, seed, skeleton, height, crown extent and lean are the realistic
tree's, node for node, so an engine can swap styles on one placement and the outline at 200 m is the same tree. The
report says what was simplified and measures that claim:

    style blobby: 4 limbs kept of 5 first-order + 10 of their forks (15 of 12125 axes drawn, 138 of 4451 m of wood; no twigs); 8 crown masses + a core joined over 3.55 m, for 17840 twigs, 3 tones
    same individual: outline IoU 0.86 against the realistic tree in leaf (true scale, feet together; azimuths 0/60/120: ...); height 20.2 m (realistic 19.8), crown width 23.8 m (realistic 25.7)

(IoU of the row-filled side outlines, both in the same metric frame: under 0.8, or a height off by 6%, is a WARNING.)

How artists make these (what the operations copy):
- Blob / low-poly trees are a trunk and a handful of smooth-shaded lumps, built from spheres or metaballs joined and
  remeshed; the shading comes from smooth normals over each lump, the colour from one flat tone per lump
  (https://www.blendernation.com/2016/09/26/make-low-poly-stylized-trees/,
  https://blenderartists.org/t/what-are-the-tips-and-tricks-to-make-stylized-low-poly-creations/1510574).
- Soft "Ghibli" foliage is leaf cards whose normals are TRANSFERRED from a rounded proxy hull round each clump (Blender's
  Data Transfer / Normal Edit modifier), so a clump shades as one soft volume and the cards only cut its edge
  (https://www.blendernation.com/2020/08/20/creating-ghibli-trees-in-3d/,
  https://trungduyng.substack.com/p/tutorial-blender-anime-foliage-pipeline, https://simonschreibt.de/gat/airborn-trees).
  The blobby crown below IS that proxy; later styles will put cards on it and take its normals.

A style is a sheet of ordinary numbers (`src/hifipushie/vegetation_styles/<name>.json`; get_plant shows the resolved
sheet under `style`) over a few general operations. Override any of them in the spec:
`"style": {"sheet": "blobby", "crown": {"masses": 5, "blend": 2.0}, "wood": {"limbs": 3}, "budget": 4000}`.
- `wood`: `limbs` [fewest, most] of the stoutest first-order limbs drawn (those at least 0.4 x the stoutest's girth)
  and `stubs` of each limb's stoutest forks (`stub_apart` m apart, at least `stub_min` m long, `stub_radius` x their
  limb): what carries the crown in leaf and what is left standing in winter (limbs alone were four bare noodles).
  Girth is TOY girth: `radius` x the grown radius, but a limb's base at least `limb_mass` x the crown masses' mean
  radius and the trunk `trunk_mass` x it (the pipe model's limbs read as wires under 4 m lumps); never thinner than
  `taper_floor` (trunk: `trunk_floor`) of the base; `foot` caps the root flare (the grown flare made the trunk a
  cone). Every limb and fork runs INTO the crown and ends there: it is drawn while its axis stays `keep_in` m + its own
  girth under the surface (to `reach_in` / `stub_reach` of its length), stops for good where it first comes out
  again, and a fork that never gets in is not drawn. `smooth` = bend smoothing passes. The wood is ONE field (each
  axis a chain of round cones, axes joined by a smooth union of `blend` x the branch's girth) meshed like the crown:
  forks are fillets, ends are round, normals are the field's. `flat` (bark = one colour), `share` (of the budget).
- `crown` kind "masses": the twigs' positions are clustered (k-means, no randomness), each cluster becomes an
  ellipsoid (principal axes x `spread` + `pad` twig lengths; no semi-axis under 0.75 x `min_feature` or under
  `roundness` x its longest: flat clusters read as lily pads; a mass never stands taller than the tree), plus a
  `core` mass in the middle (x the whole foliage's spread: foliage is a hollow shell, and masses fitted to a shell are
  a ring of balloons). They are joined by a smooth union over `blend_share` x their mean radius (at least `blend` m:
  1 m between 4 m masses left eight balloons; 0.9 gives one bumpy cloud) and meshed once (marching cubes on the
  field), then decimated per LOD and put back on the field. Closed, no leaves, no alpha. `masses` [lo, hi]: the
  fewest whose outline is within 0.01 IoU of the best (the report lists the IoU per count), or one number.
  `normals`: 0 = the field's own gradient (smooth over each mass and its blends) .. 1 = straight out of the crown's
  middle. `tones` steps of `tone` [dark, light] by each mass's height (top lighter; `warm_top`), one tone per mass.
  The fit is always made on the plant in leaf, whatever `season` it is shown in.
- `colour`: saturation / value on the species' leaf and bark colours. `wind`: `mass` = the least branch sway a mass
  has (it moves as a whole with the limb it sits on, in that limb's phase), `squash` (top vs bottom of a mass).
  `seasons`: what spring and snow mix the colour toward. `budget`: LOD 0's triangles when export_plant gets none.

The export keeps the realistic contract: nodes / meshes `wood` + `foliage` (LOD<k>_ prefixed), materials `bark` +
`foliage`, LODs at 100 / 45 / 18% + impostor, TEXCOORD_1 / TEXCOORD_2 / _WIND, KHR_materials_variants per season,
collision (capsules + mesh: the GROWN tree's, identical to the realistic export's: swapping styles must not change
gameplay). What differs, for the engine's shader:
the foliage is opaque untextured geometry; albedo = the material's baseColorFactor (one per season variant) x COLOR_0
(each mass's tone, <= 1: an engine's default imported material ignores vertex colour, switch it on; without it every
mass is one green). A season in which the plant is bare has `extras.hidden` on its foliage material and `hidden: true`
in the seasons json (the alpha cut-off above 1 is only there so viewers that read variants hide it); NORMAL is the smooth
mass normal; TEXCOORD_0 = (height within its mass 0..1, (mass index + 0.5) / masses) for ramps and per-mass ids.
No lighting is baked: cel bands and outlines are the engine's. extras.hifipushie_plant.style carries the sheet, the
"simplified" lines and every season's colour (sRGB).

Conifers (needle trees) take the sheet's `conifer` block, merged over the rest (override it under
`"style": {"sheet": "blobby", "conifer": {"crown": {...}}}`): crown kind "tiers" = stacked dumplings, `masses` [lo, hi]
of them, one per height band of the foliage, and the wood is the trunk alone (`limbs` [0, 0]). Each tier is an upright
EGG: round above its widest level (`tier_height` x its band), flat below it (`tier_under` x the band), seated
`tier_seat` up its band, as wide as the foliage in the band's lower part (`spread`, `pad`). So a tier's dome closes
under the next tier's wider foot: every tier overhangs the one below with an undercut (plain ellipsoids blended over
0.3 x their radius were a soft-serve cone). `blend_share` / `blend` small (0.1 / 0.35 m) keeps the undercuts.
`trunk_show` m of trunk stay bare under the lowest tier (`wood.trunk_mass` makes it fat); `tier_power` < 1 = upper
bands shorter; `tier_uneven` 0..1 = bands and widths differ (the seed's own numbers, the same every time);
`tier_cap` = the top tier no slimmer than that x its height (a narrow top band was a long finger); `tone`, `tones`,
`warm_top` and `colour.value` have their own conifer numbers (a spruce's dark needles gave one dark green top to
bottom). Cost: the Norway spruce's IoU falls from 0.85 (smooth tiers down to the ground) to ~0.75: the realistic
tree's skirt sweeps the ground and the toy has a bare foot and notches; the report warns under 0.8. Lower
`trunk_show` to get it back.

ANIME (`vegetation_styles/anime.json`, painted backgrounds: Ghibli, Genshin, BotW) is crown kind "clouds" (`veg_cloud.py`):
the same masses as the blobby crown, but they are the PROXY, not what is drawn. Every mass (clump) gets `layers` shells
(0.6 / 0.8 / 1.0 / 1.12 of its ellipsoid, weighted by `layer_weight`) of alpha cards facing out of it (tilted up to
`tilt` deg, rolled `roll`, cupped `cup`), `card` x the clump's radius across (at most `card_max`; lower LODs take
fewer, larger cards, up to `lod_grow` x); cards buried more than `bury` x a radius inside another clump are left out.
The picture is a generated grey DAB atlas (`crown.dab`: `count` brush dabs per tile, each the species' leaf outline
fattened, `length` x the tile, pointing out by `out` and down by `droop`, a solid `core`, a `ragged` rim; needle trees
a pointed spray stroke, shape "spray"); the material's colour and COLOR_0 multiply it. NORMAL = out of the card's own
clump's middle, mixed `normals` toward out of the crown's middle (artists transfer a proxy's normals onto the cards:
the clump shades as one soft volume and the cards only cut its edge). COLOR_0 = a 3-step painted gradient per clump,
one step per CARD (`tone` per step, `grad_range` of the clump's height, `grad_jitter`, inner layers darker by
`depth_dark`, the top warmer by `warm_top`); TEXCOORD_3 = (gradient 0 base .. 1 top of its clump, (clump + 0.5) /
clumps) for an engine's own ramp (Godot reads it as CUSTOM0.zw). Two sizes of cloud: `edge_share` of the foliage
furthest out of the crown's middle is clustered into `edge_count` x more, smaller clouds (one size read as one layer).
The cards are held under the realistic tree's height. Budget: what the triangle count buys, shared by area between
clumps and by `layer_weight` between layers; `clump_min_cards` raises small clumps (small top tiers were confetti)
and the big clumps give up what they gained, so LOD 0 stays within the sheet's `budget`.
Wood in anime: true radii, thin and dark (`colour.bark_mix` toward a dark warm neutral), with its forks (`stubs`) in
the ONE wood mesh (`wood.forks_in_leaf`: seen through the gaps, no `bark_forks` slot), and `wood.feed`: a clump with no
drawn wood within feed x its radius gets the grown tree's own path to it (outer clumps floated).
Anime conifers: clouds on TIERS (`masses_kind` "tiers", the blobby tier numbers), `under` 0.25 = cards facing the ground
under each bough are left out (the strong tier shadow), smaller softer spray strokes (110 a tile, a quarter of it long:
from 5 m half-tile strokes read as palm fronds) and spring = `seasons.spring.tips`: the spring picture paints the tip
`share` of every stroke `light` x lighter and `tint`ed (new growth), the rest `body` x (same alpha, same cards: only the
spring material's picture differs; the export's foliage_spring has its own baseColorTexture).
Anime small plants (`clump`): `fan` blades from each chosen card +-`fan_angle` (long thin sweeping blades), flowers as
colour DABS (`heads_kind` "dab": `dabs` flat ragged blobs of paint ~`ball` x the stalk long, facing up by `head_up`).
Every style's clump block takes `heads_kind`: "ball" (blobby: a ball on a stalk), "dab", "petals" (`petals` [fewest, most]
fat flat petals, `petal_length` / `petal_width`, cupped `cup`, round a `centre` disc).
Numbers (vegstyle3, Godot 4.7.2 at each LOD's switch distance, alpha scissor): oak IoU 0.91, covered area 0.94-1.0 of
LOD 0 at every switch, no interior shimmer; spruce IoU 0.80.

CARTOON (`vegetation_styles/cartoon.json`: Wind Waker, Animal Crossing) is the blobby crown made chunky, each operation
a number: `crown.scallop` small round bumps on every clump's sides and top (`scallop_size` x its radius, sunk
`scallop_sink`, joined crisper than the clumps by `scallop_join`: the scalloped edge), clumps joined over a small
`blend_share` (clear notches between them), `normals_clump` (the normal mostly straight out of its own clump's middle:
flat-ish shading per clump, the brief's "clump-centre normals"), 2 `tones` with `hue_jitter` (the hue moves a little
per clump), `big_leaves` single oversized leaves (`big_leaf` x the species' leaf length, the species' outline fattened,
thin closed plates rooted `big_leaf_sink` into the crown at its outermost points, pointing out and up by `big_leaf_up`;
fewer at lower LODs; each takes its clump's colour, id and wind, its tip flutters). The clump id is TEXCOORD_0.y as in
blobby. Wood: first-order limbs, `wood.taper` (girth at the foot x (1 + taper), easing to the top), `wood.flare` (a root
flare over the first ~12% of the bare trunk) and `wood.s_bend` (one S along the bare trunk, `s_bend` x its height out and
back, nothing moves above the crown's base: the crown stays where the realistic one is).
Cartoon conifers: tiers of `tier_shape` "cone": each tier a cone standing on its band's foot, `cone_height` x the band
tall (it reaches into the band above: the saw-tooth outline), its rim cut into `teeth` points `zig` x its radius in and
out (a zigzag outline from above and the side). The cones' triangles cover less of the realistic outline than its
parallel-sided bands: IoU ~0.8 is the style's price (wider `spread` buys IoU and costs width).
Cartoon small plants: few big wide blades, `heads_kind` {"ray": "petals", ...}: a daisy's flower as 5-8 fat flat petals
cupped round a centre disc (COLOR_0: white petals, yellow centre, green stalk), a grass's seed spike as a ball.

Cartoon, second pass: `big_leaves` stand on clumps' EDGES (out of the crown, not under it), pointing out and up, their
FACE turned sideways (toward the views that see that point on the outline; lying flat, face up, they were seen edge-on
from eye level as green shards), the species' outline softened by `big_leaf_soft` toward a plain ovate leaf (sharp lobes
read as a saw blade), `big_leaf` x the leaf length (26: ~3 m on a 20 m oak, as the toy proportion asks). `wood.flare` is a
concave root foot `flare_height` trunk DIAMETERS tall ((1 - s)^2.5; the trunk resampled finely there) and the trunk's foot
node stands under the ground (a round cone ends in a sphere: one centred on the ground read as a bulb / mound). Flowers
face the sky by `head_up` (0..1, the rest along the stalk; a head along a leaning stalk faced sideways and showed its
petals' shaded backs) and petals shade toward the sky on both faces. A season may paint the masses' EDGES (sheet
`seasons.<season>.tips` {"color", "band": [whole, gone] in TEXCOORD_0.x}: the cartoon fir's spring = lime new growth on
every tier's rim): the export writes it as a RAMP TEXTURE over TEXCOORD_0.x in that season's material (contract 7).
Anime seed / flower heads (`heads_kind` "dab") are small CLUSTERS of soft blobs strung along the head (`dabs`,
`dab_length`, `dab_size`, `dab_flat`): flat discs read as coins on sticks from the side.

PIXAR (`vegetation_styles/pixar.json`; Pixar / Disney forest sets: Brave, Up, Luca). What artists do: the canopy is
modelled as a few big sculpted, SOFT shells per branch cluster that hold the shape and the shading, and a layer of real
leaf cards is scattered over the outside so the silhouette and the near view are leafy while the inside reads solid;
normals of the cards are taken from the shell, colour is a rich gradient from dark interior to warm, light tips, and
light through the canopy (translucency / subsurface) is driven by how thick the canopy is
(https://www.fxguide.com/fxfeatured/pixars-luca/, https://graphics.pixar.com/library/ (tree / foliage papers),
https://www.blendernation.com/2020/08/20/creating-ghibli-trees-in-3d/ for the shell + cards method in Blender). Here:
- the shell = the blobby masses (`crown.masses` [8, 16], fewer and bigger: 20 small ones read as pom-poms), joined
  softly (`blend_share`), coloured per vertex by `crown.gradient` [interior, tip] (0.55 x out-of-the-crown + 0.45 x up),
  warmer at the tips by `warm_tip`, hue per mass kept; `normals` 0.5 = canopy-centre normals half way;
- `crown.cards` (a general op: any closed crown can take it): `count` of the species' TRUE leaf outlines per card
  (`length` x the card's half width each), sized so a leaf is `leaf` x the species' leaf length (1.5); cards stand on
  the shell at points drawn by area (`under` = less on its underside), `out` [least, most] m outside it (the outer
  20-30 cm), facing out (tilted `tilt`, rolled `roll`, cupped `cup`), at most `cover` x the shell's area, `share` of the
  crown's triangles; lower LODs fewer, larger cards (up to `lod_grow` 2x); `size_m` = a needle tree's spray size
  (needles are too small to size by), `rim` = weight toward the boughs' outer edges; NORMAL = the shell's under the card;
- TEXCOORD_3 = (gradient, THICKNESS m: how far a ray straight in stays inside the canopy, capped `thick_reach` 4 m;
  cards 0.02) on both; material extras.translucency {color, amount} = the warm light-through tint for the engine;
- wood: every structural limb and its forks at TRUE girth (`radius` 1, `limb_mass` 0), bends smoothed, in one mesh,
  `feed` carries outer clusters; conifers: drooping bough shells (`tier_shape` "cone", fine `teeth`) with needle-spray
  cards weighted to their rims; small plants: lush fine blades (`fan` 6, narrow), true flowers (petals at the realistic
  size), seed spikes as dab clusters.
Export: slot `foliage` = the shell, NEW slot `foliage_cards` = the cards (the foliage mesh's next primitive: MASK,
double sided, the leaf atlas x factor x COLOR_0, one material per season; contract 9). Budget = the realistic one (20k).

Impostor quad cropped (contract 8): the octahedral frames are squares the bake sphere's size; most frames draw much
less (a 24 m oak's frame is 33 m square). extras.hifipushie_impostor `crops` = each frame's own [u0, u1, v0, v1] (all
seasons, 3% margin), `crop` = their union (the stored quad); the reference shader builds the quad from the union of the
4 frames a view blends (`uniform vec4 crops[256]`, `has_crops`). `drawn_share` in the extras = the average frame's
share of the square (anime oak 0.63). Anime crowns at LOD1 / LOD2: `crown.lod_layers` [kept under lod 0.6, under 0.3]
(the OUTER layers: what is inside an outer shell of cards is hidden but still drawn) and `lod_area` (the cards' growth
exponent: 0.5 keeps the covered area and the pixels drawn; less = fewer pixels): oak [2, 1] at 0.3, spruce [2, 2] at
0.35; summed card area over covered area (overdraw before alpha) LOD1 7.1 -> ~5, LOD2 4.4 -> ~3.

Forks only when bare: a deciduous styled tree's wood is two primitives: slot `bark` (trunk + limbs, always drawn) and
slot `bark_forks` (the limbs' forks: hidden while the crown is there, where they cluttered its underside; shown in
the bare seasons through the variant `bark_forks_bare`, within `wood.forks_share` of the budget). Looks draw the
forks when the season is bare. The slot is in the seasons json's `slot_list` with the seasons that hide it.

Small plants in a style (sheet block `clump`; `"style": {"sheet": "blobby", "clump": {"blades": [4, 6]}}`): a clump's
cards are pictures, and a style without leaves has none, so every leaf card becomes geometry: `blades` [fewest, most]
FAT blades (closed paddles `width` x their length wide, `thick` x that through, curling over by `curl`, ending in a
point), chosen among the realistic cards tallest first and then by the farthest tip, so the tuft keeps its height and
spread (the report gives both against the realistic plant); every flowering picture (a part whose twig has a `flower`)
becomes a ball (`ball` x its length) on a thin stalk, at most `heads`. One tone per blade in `tones` steps of `tone`
(COLOR_0), normals leaned to the sky by `normals_up` so the tuft shades as one clump, wind = each blade bends from its
foot in its own phase (the realistic card's). `budget` (800): LODs take sides and rings off the same blades. In the
export the blades are slot `foliage`, the heads the foliage mesh's SECOND primitive, slot `heads` (COLOR_0 = each part's
colour under a white factor: petals or ball, the flower's centre, the stalk; hidden, like `bark_forks`, in the seasons
its layer doesn't show in). `heads_kind` "ball" | "dab" | "petals", or a table by the realistic flower's form
(`{"ray": "petals", "*": "ball"}`: a daisy's rays become petals, a grass's spike a ball). Winter in the EXPORT: when the
plant's winter state lays its blades down (veg_small's `flatten`), the lying blades are the foliage mesh's own primitive,
slot `foliage_winter`, shown only in winter and snow while `foliage` is hidden (contract 6). Chosen over a morph target
per season: the engine already hides and shows slots per season from the seasons json, a clump is a few hundred
triangles (the second set costs file size, not draw calls), and nothing has to keep blend weights in step with the
wind and the LODs.

Seasons in a style: spring (fresh yellow-green; an anime conifer's fresh tips), summer, autumn (`leaves.autumn`),
winter (deciduous: the bare drawn limbs and forks; evergreen: its crown), snow = THE WINTER STATE UNDER SNOW (contract
5: a deciduous tree is bare under snow, its forks shown, the snow impostor the bare tree; an evergreen's crown pale;
snow ON wood is the engine's shader from the seasons json's `snow` numbers). The realistic tree has spring too now: `"season": "spring"` / the export's "spring"
variant = `leaves.spring` colour (else the summer colour toward yellow-green) and leaves `leaves.spring_size` (0.75)
of their length. Blossom and catkins are not built. Small plants have their own states: see "Small plants".

What goes wrong: an IoU under ~0.85 usually means the realistic crown is ragged or hollow on one side (raise
`crown.masses`' upper end, or lower `spread`); masses like separate balloons = `blend_share` too small or no `core`;
limbs like wires = `limb_mass` / `trunk_mass`; a stick showing through a mass = raise `wood.keep_in`; a bare winter
tree of a few noodles = more `stubs`. Tiers like a soft-serve cone = `blend_share` too large or no
`tier_under`; a top like a finger = `tier_cap`; tiers of wildly different heights = `tier_uneven` over ~0.3.
Known: from 5 m the fork's fillet shows a ragged shadow edge in the looks (EEVEE's shadow terminator on large smooth
triangles; the clay view doesn't show it, and the consumer has not reported it from Godot). A styled fern or daisy is the grass rule
applied to its cards (paddles and balls): not yet judged.

## Not built yet

Say so in your report instead of faking it: LODs, wind animation data, autumn/snow/wet variants, collision
proxies; a pixar style, styles for stands, blossom; a multi-stem base, exposed roots, burrs,
fluted trunks, surface roots running out over the ground, hollows and cavities; thorns, flowers and fruit on twigs; banks, ditches and shorelines (only a slope and a
water level); a tree that sees the other plants you made (use `setting`/`neighbours`).

## Tool reference

The full documentation of this topic's tools: their MCP descriptions are the short form. guide(topic="<tool name>") returns one section. These tools are the `plants` toolset: enable_toolset("plants") turns it on.

### `grow_plant`

`grow_plant(name, spec=None, patch=None, note='', copy_from=None)`

Create or change a plant and grow it (guide(topic="vegetation") has the vocabulary and the stages). `spec`
replaces the whole spec; `patch` merges into the stored one (objects merge key by key, null deletes:
{"age": 60, "habit": {"apical": [0.6, 0.5]}, "environment": {"wind": {"from": "w", "strength": 0.5}}}).
A spec is botanical words: {"species": preset, "age": years, "seed", "height": m, "habit": {...overrides...},
"environment": {...}, "guides": {...}, "prune": [...], "envelope": {...}, "forces": [...], "leaves": {...},
"bark": {...}, "season", "decay", "style"}. "style": "realistic" (default) | "blobby" | "anime" | "cartoon" | "pixar", or
{"sheet": "blobby", "crown": {"masses": 6}, ...} to override a sheet's numbers: the SAME grown plant (skeleton,
height, crown extent, lean) dressed another way (blobby: few fat limbs + smooth closed masses; anime: painted leaf clouds; cartoon: scalloped clumps; pixar: every limb + a soft canopy shell with a layer of real leaf cards); the
report says what was simplified and the outline IoU against the realistic tree. Looks and exports follow the style.
"season": summer | spring | autumn | winter. The same spec always grows the same plant. Every version is kept
(plant_history). Returns the report: size, form measured on its own silhouettes, limbs, foliage, guides, the
reference match if it has one, WARNINGS last, and (for a patch) every changed value old -> new with what the tree
did. In a patch, lists REPLACE (give the whole per-order list; `"prune": null` removes every prune: use
edit_plant to add or remove one). copy_from: start `name` as a copy of another plant (+ patch): variants of one
description, e.g. {"seed": 2, "age": 14}. Use get_plant first to see the values you are about to override.
With no arguments but a name: the report of the stored plant; name "" lists the plants and the species presets.

### `edit_plant`

`edit_plant(name, ops, note='')`

Direct the plant the way an artist does between growth years; it regrows around every edit. ops, in order:
{"op": "guide", "name", "path": [[x, y, z], ...] (m), "from_year", "until_year", "vigour"}: a drawn axis at any
branch order (it starts from the nearest wood at from_year, lies exactly on the path, is never shed or bent, and
branches grow from it; a path from [0, 0, 0] at year 0 is the trunk). {"op": "remove_guide", "name"}.
{"op": "take_limb", "limb": "SW1", "name"?, "path"?}: a GROWN main limb (the report names them) becomes a guide of
the same place and shape, which you can then redraw; the rest of the tree regrows around it (it may change).
The same with "on": another guide's name (or "trunk") makes it leave THAT axis. Paths are splined through
their points ("straight": true keeps corners).
{"op": "prune", "box": [[lo], [hi]] | "sphere": [[c], r] | "above": z | "below": z (limbs LEAVING the trunk under
z) | "under": z (nothing but the trunk hangs under z)}: a clean cut on the finished tree, nothing else changes;
with "from_year" it is cut from that year on and the tree answers it (regrows elsewhere).
{"op": "remove_prune", "index"}, {"op": "clear_prunes"}.
{"op": "cut", "year": N, <a volume as for prune>, "every": years, "until_year", "sprouts": n}: the wood in the
volume is cut AT that year (and again every `every` years) and the stubs sprout `sprouts` new shoots each: a
pollard ("above": 2.5, "every": 6), a coppice ("above": 0.3), a lopped limb or a storm break (a box, sprouts 0-2).
{"op": "clear_cuts"}. {"op": "dead", "limb": name | id | guide (or a volume), "min_radius", "from": m along it},
{"op": "clear_dead"}. {"op": "envelope", "shape": ellipsoid | cone | column | dome, "radius", "top", "base",
"soft"} (a soft crown shape; no other keys = remove). {"op": "force", "dir": [x, y, z], "strength", "orders"},
{"op": "clear_forces"}. {"op": "set", "path": "habit.apical.0" | "age" | "leaves.length"..., "value"}.
Returns the report after regrowing, with what changed in size.

### `get_plant`

`get_plant(name='', species='')`

A plant's spec as stored ("own"), what it RESOLVES to once its species preset and the defaults are under it
("resolved": every habit, leaf, twig and bark value actually in force), what each number usually is
("habit_ranges", "leaf_twig_ranges") and how many growth steps its age makes. Read this before overriding
anything: an override replaces the resolved value, and per-order lists are replaced whole. With `species` and
no name: that preset resolved (to see what a species gives before using it).

### `look_plant`

`look_plant(name, views=None, azimuth=0.0, size=640, foliage=None, sheet=False, triangles=None)`

Images of a plant (Blender, 5-40 s). views, any of: "clay" (the bare skeleton as clay: judge the structure
here first), "bare" (in colour, no leaves), "leaf" (in leaf; these three are side views from `azimuth`, 0 = looking
along +y), "far" (at eye height from far enough that the tree is half the picture: how it reads in a scene), "near"
(standing by it, 2-5 m, looking up: trunk, bark, forks), "close" (foliage: leaves and twigs), "under" (from under
the crown, up along a limb), "ground" (eye 1 m up, 8 m from the lowest foliage: where the plant meets the ground;
the report's `ground:` line counts what rests on it and what was turned, shortened or left out), or a camera of your
own {"name", "eye": [x, y, z], "look": [x, y, z], "fov": deg, "clay": bool}. Default clay + leaf + far. The ground
is flat grass unless the spec has environment.ground {"slope": deg, "toward": [x, y], "water": z} (a hillside
falling that way; a water level z m against the foot). clay and bare show a pole banded every metre (every fifth
band red) beside the plant. triangles=N shows the plant as export_plant(triangles=N) writes it (thin wood left
out, fewer and larger cards): judge the budgeted plant before exporting it. Files carry the view, azimuth and
version in their names. foliage: "cards" (the twig
atlas on cut cards: what a game draws; default) or "mesh" (real leaf meshes: close-ups, video).
sheet=True returns the reference sheet instead (photo | outlines over each other | every view, with the numbers);
it needs plant_reference first. Files are also written to workspace/plants/<name>/. Read the images.

### `look_plants`

`look_plants(names, at=None, spacing=None, views=None, azimuth=0.0, size=640, foliage=None, triangles=None)`

Several plants standing together in one picture (a stand, a hedge line, a tree with its neighbours): do they
belong together, do their sizes relate? at: [[x, y], ...] m per plant, or spacing m apart on a loose ring
(default 0.35 x the tallest). views: "far" (default), "near", "clay", "top", or a camera {"eye", "look", "fov"}.
The first plant's environment (ground slope) sets the scene. The same plant may be named more than once.
A plant with a `set` (grow_plant patch {"set": {"count": 5}}): "oak#*" names its whole set, "oak#2" one of it.
`at` goes with the names in order (a set's plants #1, #2... in turn). triangles=N shows every plant at that
budget, as export_plant(triangles=N) writes it.

### `plant_form`

`plant_form(name='', species='', cases=None, fit=None, iters=30, seeds=2)`

A tree's form ACROSS AGES AND SETTINGS, measured the way foresters do, and optionally fitted: the habit that
looks right at one age is often a bare pole at half that age and a monster at twice. Each case grows the plant
(or a species preset) at {"age": years, "environment"?: {"setting": "open" | "edge" | "forest", "spacing": m,
"open_side": [x, y]}, "name"?} and measures height (m), width_over_height (crown width / height), crown_ratio
(live crown / height), widest_at (height of the widest level / height), dbh_cm, top_off (m the top stands off
the foot), nodes. A case may carry target bands for any of them, e.g. "crown_ratio": [0.3, 0.45] (from yield
tables, crown-ratio studies or boxes read off whole-tree photographs); the reply marks every miss.
Default cases: the plant at 0.2 / 0.45 / 1 / 2 x its age in the open, and at its age on a stand's edge and
inside a stand 4 m apart. fit = {habit path: [lo, hi]} (as plant_reference's) searches those numbers for the
least miss over ALL cases (`iters` rounds x `seeds`; minutes) and, for a stored plant, saves them.

### `plant_reference`

`plant_reference(name, image_path, crop=None, foot=None, polygon=None, tol=30.0, horizon=None, bare=False, credit='', fit=None, fit_iters=40)`

Give the plant a reference photo and measure against it. The silhouette is taken from the photo either by
`polygon` (the tree's outline traced on the photo in image pixels, closed: use this when the tree fills the frame
or stands against other trees) or by `crop` [x0, y0, x1, y1] + `foot` (the trunk's x in px): pixels more than
`tol` from the sky colour at the crop's edges are tree; below `horizon` (image y where ground or far trees
start) only the trunk counts. bare=True for a winter photo (compared without leaves). Returns outline IoU,
width/height, bole and widest height, ours vs the photo's.
fit = {habit path: [lo, hi]} searches those habit numbers for the best match (~1-2 min; e.g. {"apical.0":
[0.45, 0.65], "angle.0": [40, 80], "vigour": [3, 6], "sag": [0.2, 2]}; integer bounds stay integers) and saves them
into the plant's habit; it also charges limbs drooped under the crown's base, so it can't cheat the outline.

### `export_plant`

`export_plant(name, out_dir=None, triangles=None, set=False, lods=1, impostor=False, seasons=None, wet=False, lod_files=False, grade='full')`

Export the plant as a GLB (workspace/plants/<name>/export/<name>.glb unless out_dir): a `wood` mesh (bark
colour, normal and roughness as tiling textures on the branch uv) and a `foliage` mesh (every twig's card; the
twig atlas with alpha MASK, double sided, normals bent out from the crown, COLOR_0 = a per-twig tint).
triangles: LOD 0's budget (a game tree: 10-40k; without it everything grown is written, often 100-400k):
branches get fewer rings and sides, the thinnest wood is left out (marked wood stays), twigs are thinned and the
rest drawn larger. lods: 1-3 mesh LODs (100 / 45 / 18% of the budget); impostor=True adds a HEMI-OCTAHEDRAL impostor as
the last LOD: one quad the engine's shader turns to the camera, drawing the nearest of 8 x 8 views baked over the
upper hemisphere (holds from the horizon to straight down: trees seen from a hill; recipe in the material's extras,
reference Godot shader spikes/godot_veg/impostor_octa.gdshader; ~2-3 min of Blender per shape of the plant, ~40 s
per further season); impostor="cross" = the old two crossed quads (any viewer draws them; read as a cross from above). LOD 0 is the scene, the others hang on it
(MSFT_lod) and are listed in extras with the screen height to switch at; lod_files=True also writes each LOD as
its own <name>_LOD<k>.glb (Unreal, Unity, Godot take LODs as separate meshes).
Wind is always written: TEXCOORD_1 = (trunk, branch) sway weights, TEXCOORD_2 = (phase, flutter), the same four in
_WIND; the shader recipe is in extras. seasons: any of "spring", "summer", "autumn", "winter", "snow" as material variants
(KHR_materials_variants; a deciduous winter hides the foliage; "snow" frosts the foliage picture, snow on wood is
an engine shader: recipe in extras); wet=True adds a "wet" variant. Collision: capsules for the trunk and main
limbs in extras + a low `<name>_collision` mesh node outside the scene.
A plant with a `style` exports in its style with the same node, mesh and material names (wood / foliage; bark /
foliage), LODs, wind channels, variants and collision: its foliage is closed untextured geometry (colour = the
material's baseColorFactor per season x COLOR_0), `triangles` defaults to the style sheet's budget, and the reply
says what was simplified (also in extras.hifipushie_plant.style). A styled deciduous tree's wood has a second
primitive, slot `bark_forks` (hidden unless the season is bare); a styled small plant's foliage has one, slot
`heads` (flower / seed heads, hidden out of their seasons).
The impostor is lit by the engine: albedo (unlit, with the shade of what stands above baked in) + a tangent-space
normal map, a picture per season; its material must not receive shadows (the quads shadow each other).
<name>_seasons.json leads with `contract` (version: bumped whenever a slot or vertex channel changes) and
`slot_list` (every slot: its mesh / primitive, the seasons that hide it, its channels): an engine should refuse a
version or slot it doesn't know. Small plants (clumps) export their seasons as variants too (colour; layers out
of season hidden); their lying down in winter is in the looks only.
set=True writes the plant's `set` as ONE file (<name>_set.glb): a node per plant in a row, the bark and foliage
materials and textures shared (a forest kit); `triangles` is then each plant's own budget.
A SWARD (species sward / sward_mown / sward_rough: plain grass as a 2 m tile of blades, see the guide) exports as its
own files: <name>_LOD0..3.glb (fewer, wider blades), <name>.glb, <name>_seasons.json with a `sward` block (tile size,
LOD rings, the fade into the terrain's grass texture and its colours); triangles / lods / impostor don't apply.
grade="groundcover" (small plants: grass, daisy, clover, fern... in any style) = the SCATTER grade: the clump as it
is drawn in full, baked per season onto a few alpha cards: LOD 0 6 cards (288 triangles), LOD 1 4 (96), LOD 2 3 (36).
Each card shows the slice of the clump in its own wedge round the foot, so every blade is drawn once. Same slots
(foliage; seasons as variants of it, winter = the plant lying, snow = winter under snow), wind channels and seasons
json; adds TANGENT + a normalTexture; no bark / heads slots (stalks and flower heads are in the pictures). Written to
its own folder (default export_groundcover/) as <name>_LOD0..2.glb, <name>.glb (MSFT_lod) and <name>_seasons.json:
point the game's groundcover at that folder. ENGINE: import its PNGs WITHOUT mipmaps, or WITH them and alpha scaled up
by the mip level in the shader (recipe in the material's extras.alpha_mips; with plain mipmaps thin blades vanish past
~4 m), and turn the importer's own LOD generation off for these meshes. ~5-10 min of
Blender the first time (cached by the spec).

### `wind_plant`

`wind_plant(name, triangles=20000, seconds=4.0, strength=1.0, wind_from=270.0, azimuth=0.0)`

The plant in the wind, as a game would move it: its export (at `triangles`) is opened with Blender's glTF importer
and swayed from the file's own wind channels (trunk sway, limbs each in their own phase, leaf flutter) by the
shader recipe in the file's extras. strength 0.3 = a breeze, 1 = a fresh wind, 2 = a gale; wind_from = the compass
bearing it blows from (270 = from the west, +x is east). Returns a strip of six frames over their difference from
the first (bright = moving: the trunk's foot must stay dark, the crown's edge and the limb ends bright), the mp4's
path, and what the importer found (uv sets, attributes, variants). 30-90 s.

### `sync_plant`

`sync_plant(name, pull_only=False)`

The plant as a Blender file a person (or you, through a Blender session) can edit by hand:
workspace/plants/<name>/plant.blend holds the plant with its guides (orange, collection "guides") and its named
main limbs (blue, "limbs") as Bezier curves. First every edit made there comes back into the spec: a guide curve
moved or given more points = that guide redrawn; a limb curve moved = that limb taken over as a guide with the
new shape; a curve added to "guides" = a new guide; a guide curve deleted = removed. Then (unless pull_only) the
file is written again from the spec. A running Blender with the file open is read live and reloaded. Only
what moved from what the last sync wrote counts: syncing twice changes nothing. Returns what came back and the
report.

### `plant_history`

`plant_history(name, revert_to=None)`

List a plant's versions (plant_history(name)), or restore one: plant_history(name, revert_to=3) saves version
3's spec again as a new version, so nothing is lost.

### `grow_stand`

`grow_stand(name, spec=None, patch=None)`

A forest stand as a game builds one: a few grown trees per species and role, stood many times at a spacing,
with a floor. spec (or a merge `patch`; null deletes): {"species": "norway_spruce" or [{"species", "share",
"patch": plant spec patch}], "age": years, "ages": +- spread over the variants, "spacing": m between stems,
"size": [m, m] (the plot; x across, y deep), "variants": interior trees grown per species (3), "edge": any of
"n", "s", "e", "w" = sides open to the light (their outer rank is edge trees: foliage down the open side, turned
to face out), "rows": true = planting rows along y (a plantation's aisles), "jitter": 0-0.5 x spacing,
"scale": [0.9, 1.1] per-tree size, "clearings": [{"at": [x, y], "r"}], "paths": [{"points": [[x, y], ...],
"width"}], "floor": {"brash": fallen branches per m2 (0.35), "stumps" per m2, "ferns" per m2 (they stand where
light reaches: clearings, paths, open edges, a few patches), "fern": a clump preset, "moss": 0-1, "litter": 0-1},
"lod": {"near": m, "mid": m, "budgets": [null, 10000, 1500]}, "haze": {"distance": m, "color"}, "light":
{"ambient", "bounce", "sun_energy"}}. Interior trees are grown with environment.setting "forest" at this spacing
(bare stems, dead branches kept by the species' dead_keep, a small high live crown; their girth capped by the
stocking, habit.sdi_max), edge trees with "edge". Returns the forester's numbers (stems / ha, height, dbh, basal
area, live crown ratio, canopy cover, each variant) with warnings. No arguments but a name: the stored stand.

### `look_stand`

`look_stand(name, views=None, size=720, max_full=25)`

Pictures of a stand (Blender; 2-8 min: every variant is meshed at up to three levels of detail). views, any
of "inside" (default: eye 1.7 m among the stems), "aisle" (down a row), "edge" (from outside an open side),
"above" (a high oblique), "canopy" (from the floor, straight up), or a camera {"eye": [x, y, z], "look", "fov"}
in the plot's metres (0, 0 = its middle). Each tree is drawn at the level its distance from the nearest eye
gives (the stand's `lod`), at most `max_full` at full detail (GPU memory: a laptop holds a few dozen full
trees; hundreds at budgets). Distance haze and the canopy's diffuse light are the stand's `haze` / `light`.
The reply counts what was drawn.

### `export_stand`

`export_stand(name, out_dir=None, triangles=None, lods=3, impostor=True)`

Export the stand as a forest kit (workspace/stands/<name>/export unless out_dir): one GLB per variant with
`lods` mesh LODs from `triangles` (default 2 x the stand's mid budget) + an impostor, wind and collision as
export_plant writes them; the floor's meshes (brash0-3.obj, stump0-1.obj, the fern's GLB); layout.json = every
tree (x, y, yaw, scale, variant) and floor thing, the LOD distances, the haze. A heavy job (minutes per variant;
one at a time on the machine).
