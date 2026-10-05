# Vegetation: growing trees the way vegetation artists make them

A tree here is **grown**, not assembled. You describe the species' habit, its age and where it stands; a growth
model (buds competing for light, year by year) makes the skeleton; then you direct it the way a SpeedTree or Grove
artist does (draw limbs, prune, bend, shape the crown) and it regrows around your edits. The same spec always grows
the same tree. Units are metres, Z up, the trunk's foot at [0, 0, 0]; "azimuth 0" looks along +y.

Tools: `grow_plant` (create / change / report), `edit_plant` (guides, prunes, envelope, forces), `look_plant`
(images), `plant_reference` (measure against a photo, optionally fit), `export_plant` (GLB), `plant_history`.
`grow_plant(name="")` lists the plants and the species presets.

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
  stay in metres.
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

- `setting`: "open" (default: low broad crown) or "forest" (a canopy rising with the tree: tall bare bole, narrow
  high crown). `stand: {"gap": 0.18, "depth": 0.35, "strength": 1}` tunes it.
- `wind: {"from": "w" | [x, y, 0], "strength": 0-1}`: the tree leans downwind, the windward side is thinned. 0.3 = an
  exposed field, 0.7 = a coastal hill. ("from w" blows toward +x.)
- `light: [x, y, z]`: where the light comes from (a tree at a forest edge leans out).
- `neighbours: [{"at": [x, y], "height": m, "radius": m}]`: crowns beside it that shade it.

### Direct control (edit_plant ops, or the same keys in a spec)

- `guides`: `{name: {"path": [[x, y, z], ...], "from_year", "until_year", "vigour"}}`. A drawn axis: at `from_year`
  it starts from the nearest existing wood (so draw its first point ON the trunk or limb it should leave), follows
  the path exactly, reaching its end by `until_year`; it is never shed or bent, and branches grow from it by the
  species' own rules. Works at any order: a limb, then a branch drawn on that limb (a later `from_year`). A path
  starting at [0, 0, 0] with `from_year` 0 is the trunk itself (a leaning, forked or twisted trunk).
  The report says, per guide, its order, whether it was drawn to its end, and how many branches left it.
- `prune`: `[{"box": [[lo], [hi]]}, {"sphere": [[c], r]}, {"above": z}, {"below": z}]` (+ `from_year`). `below`
  clears the trunk of limbs under that height; `above` tops the tree.
- `envelope`: `{"shape": "ellipsoid" | "cone" | "column" | "dome", "radius", "top", "base", "soft"}`: a soft crown
  shape (growth outside it is shaded out). Use sparingly: an envelope makes a clipped look.
- `forces`: `[{"dir": [x, y, z], "strength": 0.1-0.5, "orders": [1, 2]}]`: a steady push on growing shoots (a
  tree reaching over water, limbs swept one way).

### leaves and bark

- `leaves`: `shape` ("ovate", "triangular", "lanceolate", "lobed", or needles: "needle_tuft" round shoot ends,
  "needle_spray" flat sprays), `length` (m), `width` (x length), `lobes`, `serrate`, `color` (sRGB), `hang`,
  `twig: {"length", "leaves", "arrangement": "alternate" | "opposite" | "spiral", "per_m", "steps", "droop", "up",
  "spread", "min_order", "where": "shoots" | "ends"}` (the twig is the unit of foliage: a short shoot with its
  leaves; `per_m` twigs per metre of young shoot, on shoots up to `steps` growth steps old).
  `card: {...}` overrides for the picture game cards are cut from.
- `bark`: `kind` ("furrowed", "plates", "scales", "lenticel"), `color`, `twig_color`, `base_color` + `base_height`
  (+ `base_kind`: an old dark foot), `upper_color` + `upper_from` (m).

## Reading the report

```
form (in leaf, two side views): width/height 1.17, bole 0.20 of the height, widest at 0.50
limbs: 5 first-order branches, leaving the trunk at 69 deg, their far halves 5 deg above level
```
- width/height: 0.3-0.6 columnar/conic, 0.8-1 oval, > 1.1 spreading.
- bole: where the crown starts (the lowest height a quarter as wide as the widest). A forest tree 0.5+, an
  open-grown oak 0.2, a spruce 0.
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

## Not built yet

LODs, wind animation data, autumn/snow/wet variants, collision proxies, shrubs, grass, flowers, palms, style
sheets (blob to photoreal), forest sets as one call (use `seed` and `age` per plant for now).
