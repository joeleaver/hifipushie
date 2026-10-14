# Terrain: places, routes, walls, cover, intent, addresses, views

Read guide(topic="terrain") first: describe the brief, then write the spec.

## Places, routes and walls
- **zones**: named regions, used everywhere below and as addresses. They can be:
  - `"quadrant:ne"`, `"north"`, `"south"`, `"east"`, `"west"`, `"centre"`, `"everywhere"` (these have soft edges)
  - `{"inside": "<closed ridge>", "inset"?: m}`
  - `{"polygon": [[x, y]...]}`, `{"near": address, "radius": m}`
  - a site's name (its pad), a line's name (its ground), `"<basin>.walls"`, `"<basin>.floor"`, `"<basin>.<band>"`
  - `{"above": m}`, `{"below": m}`, `{"slope": [lo, hi]}`
  - `{"all": [...]}`, `{"any": [...]}`, `{"not": zone}`, `"feather": m`
- **sites**: pads (village, farmyard, camp, spawn). `{"at": address, "radius": m, "level"?: m, "above_water"?: m,
  "fall"?: 0.02, "toward"?: address | "south", "overlooks"?: address}`. `overlooks` picks the gentlest fall toward
  the target that lets most of the pad see it (a dead-level pad's own edge hides what's below it from its middle). With a shore address (`"lake.west_shore"`) the pad sits inland of that point, just above the
  water. The report gives its level, how far it cuts into or builds out of the slope (a warning over 25 m) and, near
  water, how far above the water it ended up (a lake can settle lower than the level the pad was set from).
  Without a `level` the pad sits a little below the ground's middle there (cut into the slope rather than built out on
  a mound). `"flat"`: 0..1, how level it is: pads over 40 m radius (a village, a farmyard) default to 0.5, keeping half
  of the ground's own lie; smaller ones are flat. `"flat": 1` for a dead-level yard or a helipad.
  `"shoulder": m` is how far the pad's banks blend into the ground (default 20 m, or half the radius): give small pads
  (a tee, a bench, a basket) a few metres, or they flatten a 40 m disc around them.
  `"prop": name, "facing"?: address` marks the site as where the engine drops a prop (a disc golf basket, a bench, a
  sign): meta.json's site gets `prop` with its name, ground position `xyz` and `yaw` (the compass bearing it faces),
  and views draw a stand-in at its real size instead of the 12 m marker pole (a disc golf basket, a tee pad slab, a
  blocky building for a "lodge"/"building"/"house", else a small post).
- **routes**: paths the compiler finds, grades and carves (switchbacks come out of the search). In the 3D tiles' maps
  a route is worn ground only off mown turf: across a fairway or a green it is walked on grass.
  `{"from": address, "to": address, "via": [...], "max_grade": 0.12, "width": m, "avoid": [zones], "stay_in": zone,
  "max_earthworks": 25, "max_fill": m}` (`max_fill` limits banks alone, for a trail that shouldn't stand on one; it may then fail its grade). Cuts and fills stop at `max_earthworks` metres (beyond that it's a bridge or a tunnel); the
  report judges the road on the ground as built and says where it fails, where its bed ends off its stop (a cliff band
  in the way), and when no way at its grade existed at all.
  - A route starting or ending at a site runs on the pad's own surface and leaves it at the pad's height (no step at the
    pad's edge); over water it is a bridge or ford at its own height, so the grade is judged on the deck, not the channel.
  - Routes are planned on the ground nearly as built (each step may be a metre off its grade, which the carve evens
    out) at 85% of their limit, so what the plan promises the built road keeps; switchback legs too close for a bank
    between them are pushed apart where the ground allows (the report says where it doesn't).
  - Cliffs (over 50 deg) are walls to a route. Where they close a route's stops off from each other, it cuts a **break**:
    switchback legs at the route's grade across the cliff where it is lowest and nearest the way, as long as the cliff
    runs on beside the crossing, the ground shaped into benches with rock cut between them (a canyon wall trail).
    Breaks that don't open a way are taken out again. `"max_break": 250` (tallest cliff to break), `"leg": m` (longest
    leg), `"breaks": false` (none: a road that must go round). A cove's scar walls in its apron: open the cove's
    `"valley"` toward where the route goes.
- **lines**: things drawn as a line on the land: hedgerows, stone walls, fences, earth banks, ditches, lines of trees.
  ```
  {"name": {"type": "hedge" | "stone wall" | "fence" | "bank" | "ditch" | "trees",
            "along": [addresses] | "follows": route or river | "around": zone | "network": {"in": zone, "spacing": m},
            "side"?: "left" | "right" | "both", "offset"?: m, "from"?: 0..1, "to"?: 0..1,
            "gaps"?: [addresses], "gates"?: m, "width"?: m, "bank"?: m, "ditch"?: m, "ditch_side"?: "left" | "right",
            "height"?: m, "shrubs"?: m, "trees"?: m}}
  ```
  - Types: `hedge` (a 0.4 m bank under a 2.5 m hedge: shrubs every 1.8 m and a tree standing out of it every ~25 m),
    `stone wall` (1.2 m high, 0.7 m wide), `fence` (1.2 m), `bank` (1 m high, 4 m across), `ditch` (1 m deep, 3 m
    across), `trees` (a shelterbelt or avenue, a tree every 7 m). Any number can be given; `bank`/`ditch` add them to
    any type (a hedge with a ditch on its field side).
  - Where: `along` straight between addresses; `follows` a route or river at `offset` (default: just off the road),
    one side or both, `from`/`to` along it; `around` a zone's edge (a field, a yard, a site's pad: `{"near": "farm",
    "radius": 60}`); `network`: field boundaries over a zone, `{"in": zone, "spacing": m | [across, along], "pattern":
    "irregular" | "strips" | "cells", "angle": "contour" | bearing, "jitter": 0.25}`. `irregular` (default): enclosure
    fields cut again and again across their longer side, a little off square, their sizes 0.5-2x `spacing` by area,
    lying along the contours; plus the zone's own edge. `strips`: long lines along the contours with cross lines between
    (T-junctions). `cells`: rounder cells. Every boundary wanders a little; a network has a gate every ~110 m.
  - A line stops at water, pads and routes it crosses (a gateway), and never climbs ground steeper than `max_slope`
    (38 deg: a wall across a cliff stood as a billboard); `gaps` opens it at addresses, `gates` every so many metres.
    Its bank and ditch never touch a route's bed or a pad. A **sunken lane / hollow way**: hedges `follows` the route
    with `"bank": 2` both sides. Each line is a zone (its ground, for cover). Walls and fences are below the grid: the
    export lists every line (`meta.json` "lines": per piece, points on the ground, type, height, width) so the engine
    places the meshes; views draw walls and fences, and each hedge as one continuous mass `height` m tall (2.2). Hedge
    shrubs and standard trees go in `trees.csv` (kinds `shrub` and `broadleaf`; standards stand in clumps along some
    stretches, `"trees": 0` for none). The report gives each line's length, pieces, how far its bank's crest and its
    ditch stand from the ground a few metres either side (asked in brackets), and its trees and shrubs.
- **walls**: unclimbable edges around a zone where no basin gives you one.
  `{"around": zone, "min_slope": 45, "height": m, "except": [addresses or passes]}`. The ground just outside is
  raised to make them (a little taller than `height`: the grid rounds a wall's lip and foot). The check walks straight
  out from each point of the edge and measures the tallest stretch at least `min_slope` steep: it must reach `height`.
- **cover**: masks for the engine, density or weight 0..1 per layer.
  ```
  {"type": forest | conifer | deciduous | rock | scree | grass | meadow | mown | rough | scrub | snow | sand | mud,
   "in": zone, "density": 0..1, "slope": [lo, hi], "elevation": [lo, hi],
   "gradient": {"from": address, "to": address, "range": [a, b]},
   "near": {"what": "water" | address, "within": m}, "breakup": {"scale": m, "amount": 0..1},
   "avoid": ["water", "routes", "sites", zone...], "color": "#rrggbb"}
  ```
  Layers are painted in order, each over the ones before it (the map, the views and the export's splats agree): put
  broad ground (grass) first and what must show on top of it (sand on the beach, lava rock) after, or `avoid` it.
  `"order": 5` on a layer paints it by that number instead of its place in the spec (a patch can't reorder keys).
  Slope and elevation edges are broken by noise a few cells across, so boundaries aren't one ruled contour.
  `orchard` plants rows (`"rows": 6` m apart, `"along": "contour" | "east" | "north"`). `"count": 6` on any tree
  layer scales it to about that many trees ("a few trees"). Types have sensible defaults (forest avoids steep ground, water, roads and sites; rock favours slopes over
  32 deg), and anything you give overrides them.
  Grass by how it's kept reads differently in the 3D tiles' maps: `mown` (fairways, greens, lawns: even, cut crisp
  along the mower's line, mown in straight stripes ~7 m wide along each piece's long axis that read light and dark with
  the sun, a first cut ~2 m wide round it, darker and unstriped), `rough` (long grass: tussocks in the maps' relief,
  straw tips; `grass` and `meadow` are rough too) and `scrub` (low bushes, heath: sage grey-green clumps with dry
  gaps). Mown grass is its own ground layer (`turf`) with its own tiling detail. Unkept grass also turns to scrub on
  slopes past ~20 deg. All of it varies by itself (patches at 60 and 15 m, drier and paler on crests and sun-facing
  slopes, lusher in hollows, salt-burnt within ~30 m of the sea), and there is no grass in the splash zone (~1.6 m over
  the sea; beaches stay sand, with a wet swash band, swash lines, a wrack line and shingle patches up the beach).
  Cliff tops: the turf ends back from every lip along a ragged edge and the ground STEPS DOWN there by the turf's
  thickness onto a bare, eroded lip (geometry, not just colour: the heightmap, the cliff meshes and their maps all
  have it); rock breaks through in patches near lips. Tune it with `"ground_character": {"lip": {"band": 1.4 (m the
  edge sits back, wandering 0.15-2.6x), "turf": 0.4 (m step; 0 = colour only), "riser": 0.18, "max": 3.2}}`.
  `"ground_character": false` at the spec's top level turns all of it off (flat cover colours). `bunker` is sand dug
  into the ground (`"depth": 0.6` m, a crisp cut face and a slight turf lip, cut finer than the terrain grid; in the 3D
  tiles): give it zones round the greens (`{"any": [{"near": [x, y], "radius": 3}, ...]}`, two or three overlapping
  circles make a kidney).
  The 3D tiles' renders and `clutter.csv` (x, y, z, kind, scale, yaw, squash: the height's share of the scale) carry
  ground clutter from the same masks: bushes on scrub (on its dark clumps; never within ~1.8 m of a cliff's turf edge
  and low and wind-shorn, squashed, out to ~7 m from it), boulders in clusters on rock (the splash zone, where rock
  breaks through near lips; never on sand, sunk a little), and (renders only, near the eye) tussocks in rough grass
  (fewer and bigger clumps from ~20 to 70 m out, as an engine's grass draws further away) and dense tall grass round the
  eye: placeholders for an engine's detail scatter (bushes are twiggy stems under small leaf clusters). Trees keep back from cliff lips too
  (4 m in from the turf's edge; cypress 1.5 m).
  `"trees"` on a tree layer picks the tree's shape (views, and the kind column of trees.csv): `"conifer"` (a spire),
  `"broadleaf"` (a round crown), `"fruit"`, `"pine"` (a tall bare trunk under a lobed round crown: a Monterey or stone
  pine), `"cypress"` (a wind-shaped coastal tree: a short trunk leaning downwind, a flat crown swept one way; all lean
  the same way).
- **intent** (checks; nothing is changed):
  - `{"at": address, "above_flood": m}`
  - `{"path": [addresses], "max_grade": g}` (straight legs)
  - `{"from": address, "see": [addresses], "min_visible": m, "min_prominence": m, "skyline": true, "eye": 1.7}`. From
    a **site**, it tries the eye at the centre and at eight spots across the site, and reports how many see the target
    (a level pad's own edge can hide what's below it from the middle). For a peak, hill or mesa: how many metres of it
    show above what's in front of it (down to its own foot), **how far its top stands above the skyline beside and
    behind it** (a peak on a ring of mountains can be all "showing" and still not stand out: `min_prominence` checks
    this), and whether it's on the skyline (nothing behind it higher). For a lake (or a cove): the share of its surface
    you see and how tall the water stands in the view. A target can be `{"at": address, "height": 25}`: something built
    there (a lighthouse tower), aimed at its top.
  - `{"from": address, "hide": [targets]}`: the other way round, each must NOT be seen from there (a hidden beach).
- `"probe": [addresses]` reports the ground height and slope at each place.
- `"export": {"size": 513}` resamples the export to an engine grid (Unity 257/513/1025/2049; Unreal 505/1009/2017).

Sections of named things (peaks, sites, routes, intent, ...) are objects keyed by name; a list of objects is accepted too
(each named by its `"name"`, else `intent_1`, ...). Free text goes in `"story"`, `"notes"` or `"wishes"`. A `patch`
merges objects key by key but replaces lists whole (views, `through`, `via`): send the whole list.

**Addresses:**
- a peak/col/landform/site/pass name
- `"river.source"`, `"river.mouth"`
- `"river@0.4"`, `"ridge@0.4"`, `"route@0.5"` (fraction along it)
- `"lake.west_shore"` (also north/south/east/northeast/...)
- `"highest"`, `"highest:<zone>"`
- `"edge:w"` (the middle of the west edge), `"edge:s@0.3"` (30% along it from the west or south end), just inside
  the frame
- a zone name or `"quadrant:ne"` (its centre)
- a ridge, river or route by name (its middle); a sea's cove or named beach
- `[x, y]`, or `{"from": address, "offset": [dx, dy]}`

`"views": [{"name": "file_stem", "eye": address | [x, y, z], "lift": m, "look": address, "fov": deg, "sun"?: ...}]`
are perspective renders. The eye stands on the ground at an address; `lift` raises it. An eye in or against the ground
is raised to stand clear of it (the run says so).
- **sun**: each view picks its own sun by default (`"auto"`): a low light from the side, the one that makes the most
  contrast on the ground that view sees (arêtes, buttresses, gullies), with little of it in shadow. Forms only read in
  side light: with the sun behind the eye every face is lit alike and a pyramid peak looks like a smooth cone. Give
  your own per view or for all (`"sun"` at the top of the spec): a compass side or bearing where the sun is (`"sw"`,
  `225`), `{"from": "west", "height": 15}` (degrees above the horizon), or `"morning"`, `"noon"`, `"evening"`
  (northern hemisphere: morning in the east). The run says which sun each view got, and warns when yours is behind the
  eye (flat light) or ahead of it (against the light). The auto sun can come from the north: it is for judging forms,
  not a claim about the level's lighting.
