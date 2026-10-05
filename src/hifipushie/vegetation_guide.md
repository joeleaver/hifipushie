# Vegetation: growing trees the way vegetation artists make them

A tree here is **grown**, not assembled. You describe the species' habit, its age and where it stands; a growth
model (buds competing for light, year by year) makes the skeleton; then you direct it the way a SpeedTree or Grove
artist does (draw limbs, prune, bend, shape the crown) and it regrows around your edits. The same spec always grows
the same tree. Units are metres, Z up, the trunk's foot at [0, 0, 0]; "azimuth 0" looks along +y.

Tools: `get_plant` (the stored spec, what it resolves to, and what each number usually is), `grow_plant` (create /
change / copy / report), `edit_plant` (guides, prunes, envelope, forces), `look_plant` (images of one plant),
`look_plants` (several standing together), `plant_reference` (measure against a photo, optionally fit),
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
- `trunk_diameter` (m at the foot, optional): thick wood is scaled to it (twigs stay as they are). Without it the
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
| `angle` | degrees a side branch leaves its parent at, per order (30 = ascending, 80 = nearly level) | [40-75, ...] |
| `tropism` | per order: + bends shoots up, - down. Hanging twigs: negative on the high orders ([0.4, 0.3, -0.1, -0.5, -1.2]) | |
| `plagio`, `elevation` | per order: pull toward a set elevation (deg above level), and how strongly: level limbs = plagio 0.3 toward 5; a conifer's flat branches | |
| `jitter` | per order: how crooked shoots run. Straight trunk 0.03-0.1; gnarled limbs 0.4+; straight limbs read as a broom | |
| `light` | pull toward open light (fills gaps, avoids its own shade) | 0.1-0.4 |
| `buds`, `whorl`, `divergence`, `plane` | per order: side buds per node (conifer trunk 4-6 with whorl true), degrees between successive buds (137.5 spiral, 180 two-ranked), flat sprays | |
| `bud_break` | per order: chance a bud can ever grow. Lower on order 1 = fewer, stronger limbs | 0.3-1 |
| `bud_life` | steps a bud stays able to grow: longer = denser inside | 3-7 |
| `max_order` | deepest branching (spruce 2, broadleaves 5) | |
| `shed` | light per segment under which a branch is dropped: higher = cleaner trunk and open interior; too high and the tree starves | 0-0.3 |
| `shadow` | [strength, falloff, depth] of each leaf's shade. Shade-tolerant, dense (spruce): [0.03, 3, 2]; light-demanding, open: [0.25, 1.6, 6] | |
| `clear` | m of trunk that never branches | 0-6 |
| `sag`, `sag_max` | bending under weight (it sets): long thin limbs droop | 0.3-3 |
| `ring` | m of radius all wood adds a year: girth. Stout trunk 0.002-0.003, slender 0.001 | |
| `pipe` | how fast branches thin (2 = thick limbs, 2.5 = thin) | 2-2.5 |
| `flare`, `flare_height` | the foot's swelling | 1.3-1.8 |
| `force_orders` | per order: how much wind and forces turn shoots (the trunk resists) | [0.15, 0.6, 1] |

Unknown habit keys are refused. Change a few at a time and read the report: nodes (300-90k is the working range),
height, form, limb angles.

### environment

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
- `ground: {"slope": deg, "toward": [x, y]}`: the hillside it stands on, for the pictures (the ground falls toward
  that direction). It does not change the growth: lean the trunk with a guide or wind.

### Direct control (edit_plant ops, or the same keys in a spec)

- `guides`: `{name: {"path": [[x, y, z], ...], "from_year", "until_year", "vigour"}}`. A drawn axis: at `from_year`
  it starts from the nearest existing wood (so draw its first point ON the trunk or limb it should leave), follows
  the path exactly, reaching its end by `until_year`; it is never shed or bent, and branches grow from it by the
  species' own rules. Works at any order: a limb, then a branch drawn on that limb (a later `from_year`). A path
  starting at [0, 0, 0] with `from_year` 0 is the trunk itself (a leaning, forked or twisted trunk).
  The path is splined through its points (`"straight": true` keeps corners). `"on": "<guide name>"` or
  `"on": "trunk"` makes it leave that axis; otherwise it leaves the stoutest wood near its first point.
  The report says, per guide, its order, whether it was drawn to its end, and how many branches left it.
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
- `envelope`: `{"shape": "ellipsoid" | "cone" | "column" | "dome", "radius", "top", "base", "soft", "center": [x, y],
  "lean": [dx, dy]}`: a soft crown shape (growth outside it is shaded out). `lean` moves the crown's middle that
  far by its top: a wedge or flag swept downwind. Use sparingly: an envelope makes a clipped look.
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
  `get_plant` lists these with the values in force.
  Foliage is drawn as cards (each twig's picture on a cut card: what a game draws) by default;
  `look_plant(foliage="mesh")` shows real leaf meshes. `card: {"twig": {...}, "leaf": {...}, "scale"}` changes what
  the card's picture is made from.
- `bark`: `kind` ("furrowed" ridges, "plates", "scales", "lenticel" smooth with dashes), `scale` (x the pattern's
  size: 0.5 = finer, for a small tree's trunk), `color`, `twig_color`, `base_color` + `base_height` (+ `base_kind`:
  an old dark foot), `upper_color` + `upper_from` (m).

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

## A stand or a group

Make one individual, then copies: `grow_plant(name="birch_b", copy_from="birch_a", patch={"seed": 2, "age": 13})`.
Give them the same `environment` (e.g. `setting: "forest"`). See them together with
`look_plants(names=[...], spacing=2.5)`: the only way to judge whether they belong together. Export each
(`export_plant(name, triangles=12000)`).

## Not built yet

Say so in your report instead of faking it: LODs, wind animation data, autumn/snow/wet variants, collision
proxies; shrubs, grass, flowers, palms; style sheets (blob to photoreal); a multi-stem base, exposed roots, burrs,
fluted trunks, deadwood on a live tree; thorns, flowers and fruit on twigs; a tree that sees the other plants you
made (use `setting`/`neighbours`).
