# Terrain spec guide (experimental)

You describe terrain in JSON, in the terms a level designer uses (a basin, a pass, a wall, a lake, a village site,
a road, forest here and rock there, this must be visible from there). A compiler turns that into a height field
and cover masks. You never paint heights. Where you want a specific landform (a named ridge, a river, a moraine),
you can drop down and write it; otherwise the compiler fills in plausible ground (drainage, spurs, gullies)
between what you placed, and never moves anything you placed.

## The world: what kind of terrain, and how compressed
Start every spec with the kind of terrain the brief describes:
```json
"world": {"kind": "alpine valley", "compression": "auto", "base": 0}
```
Kinds:
- `alpine valley` (also valley, glen, mountains)
- `cirque` (corrie, tarn, mountain lake)
- `canyon` (gorge, ravine)
- `hills`
- `farmland` (farm, farmstead, meadow, pasture, tile)
- `plateau` (mesa, butte)
- `crater` (caldera, volcano, volcanic; "volcanic island" is crater + coast)
- `coast` (beach, sea cliffs)
- `dunes` (desert)
- `moor` (highland, upland)

Game levels compress real landscapes: a 4 km level is an alpine valley at about 0.6 scale. The compiler keeps three
scales apart:
- **The kind's proportions**, compressed. Distances shrink by `c` = your frame / the kind's real width; heights
  shrink less (√c), so mountains still feel tall. The extra steepness that costs goes into cliff bands, not into
  every slope.
- **Player-scale detail**, never compressed: erosion depth, surface roughness, crags, trees and tracks are real
  metres.
- **Heights you leave out** (a peak without `h`, a basin without `floor`) are chosen to fit the kind at that
  compression. The report lists them.

The report opens with the kind, its compression, and what was chosen. The realism check compares slopes against
the kind. Small kinds (farmland) and frames much smaller than the kind are treated as a *piece* of it (no
compression). With `"units": "none"`, the frame is taken as the kind's typical level size.

**Mixtures:** `"kind": "crater + coast"` (also "and", "with", ",") mixes known kinds: the first sets the size, heights
and roughness come from the most dramatic.

**A kind the tool doesn't know** ("fjord", "badlands"...) isn't guessed. The run stops (exit code 3) and prints
QUESTIONS FOR THE DESIGNER, and first what the tool **can't build** of what was asked (no tides or waves, no glowing lava,
no caves or overhangs, no glaciers...): tell the designer that before anything else. The questions: is it like one of the
known kinds or a mix of them (optional), how big it should feel, how dramatic the height is, what's underfoot, what's at
the lowest point, whether it's closed in, and its overall shape. **Ask the designer; don't answer for them**, and let them
answer in their own words (they're matched to the nearest option). Put their answers in
`"world": {"kind": "fjord", "answers": {"size": "a long trek", ...}}`. The kind is then defined from the answers,
recorded in the report (with how its shape is built from the vocabulary), and saved (`workspace/terrain/kinds.json`),
so the next spec can just say `"kind": "fjord"`. The report also says what can't be built of the kind, the answers
and the `"story"`.

## Scale and units
- `"extent": [[x0, y0], [x1, y1]]` is the frame. Axes: x east, y north, z up.
- `"units"`: `"m"` (default), `"km"`, `"ft"`, `"yd"`, `"mi"`, or `"none"`. With `"none"` the numbers are only
  proportions: the frame is taken as `"across"` metres wide (default 2000) and the report says what it assumed.
  Choose a real scale when you can: trees, roads, walls and walking grades are real-world sized.
- Any length may be written `"30%"`:
  - for an [x, y] position, 30% across the frame
  - for other lengths, 30% of the frame's longer side
  - for heights (h, level, floor, elevation, border, ...), 30% of `"relief"` (default: a quarter of the frame)
- `"cell"` is the grid spacing (default: frame / 400). Everything else scales with the frame: a 250 m tile and a
  4 km valley use the same words.
- `"detail"`: the last stages (rock character, checks, lakes, cover, the export and the views) run on a grid this many
  times finer than `cell`. `"auto"` (default) is 2 where the frame has sea cliffs or cliffs only 2-3 cells across,
  while the fine grid stays under ~1100 cells a side; `1` turns it off. A 70 deg face 2 cells across can't carry
  anything of its own. The report and the export are at the fine cell (the report says which).
- **tilt**: `{"down": "south" | bearing deg, "grade": 0.07}` leans the whole frame (a south-facing slope). A tile
  with no ridges, rivers or basins is open ground at `world.base`, plus tilt and hills.
- **Frame edge**: `"border": 150` fixes the whole edge at that height. `{"n": 150, "s": "open", ...}` does it per
  side. An open side isn't fixed, so the ground carries on as it goes (the default).

## The big shapes
- **peaks** `{"name": {"at": [x, y], "h": z, "radius"?: m}}`. A peak on no ridge is a lone hill or knoll: `radius`
  is its rounded TOP (not its footprint); its flanks fall at `flanks` degrees (default 18) to the ground, or give its
  footprint directly with `base_radius`. The report ends with the frame's highest ground and warns when it's nothing
  you placed.
  - `"form"`: `"pyramid"` (planar faces between arêtes, a point on top; the default in alpine valleys and cirques),
    `"horn"` (steeper, three faces hollowed into cirques between sharp arêtes: a Matterhorn), `"dome"` (rounded: the
    default elsewhere). Each ridge leaving the peak is one of its arêtes, at that ridge's own fall; more are added up
    to `"faces"` (pyramid 4, horn 3). The form carves the upper part of the mountain and never cuts into a
    neighbouring ridge, col or peak. `"arete"`: slope in degrees of the added arêtes; `"hollow"`: 0..1, how deep a
    horn's cirques are. The report says how far each summit falls in its first stretch (a dome barely falls), its
    arêtes and its faces' slope.
- **cols** (low points on a ridge) have the same shape.
- **ridges** `{"name": {"through": [peak/col | "ridge@0.4" | [x, y, z], ...], "crest": "arete" | "rounded"}}`. A
  ridge that ends where it starts is **closed**: a ring round a basin or crater.
- **basins**: a valley floor inside a closed ridge, or a horseshoe open to one side. Its walls are real mountainsides:
  they average the kind's face slope, with a hard cliff band that makes them unclimbable, and each stretch is as wide
  as the crest behind it needs. So high rims take room, and the report says how much floor is left.
  ```
  {"name": {"inside": "<closed ridge | open ridge>", "opens"?: "south" | "edge:s", "floor": [low, high], "falls_to": address,
            "shape": "bowl" | "flat" | "open",
            "rises_toward"?: address,
            "walls": {"min_slope": 45, "height": m, "average"?: deg, "except": [...]}}}
  ```
  - The floor rises from `low` at `falls_to` (usually a lake) to `high` at its edge, and all water drains there.
    `rises_toward` tilts it: mostly rising toward that address or compass direction (`"north"`, `"ne"`, ...).
  - Between the floor's edge and the crest is the basin's wall: the mountainside itself. It averages `average`
    degrees (default: the kind's), with a cliff band `height` metres tall at `min_slope`+ that makes it unclimbable.
    `average` can be at most `min_slope` + 8 (the band must stay steeper than the face around it; the report says if
    it was capped). Each stretch of wall is sized from where the floor actually meets it, so a low floor edge gets a
    wider wall. It's checked like a wall (share of the edge that holds, climbable spots).
  - `walls.character`: `"tiered"` (default: stacked cliff bands with benches, light buttresses), `"buttressed"`
    (rock ribs between couloirs), `"broken"`, `"smooth"`. `walls.bands`: how many cliff bands.
  - Passes through its ridge are exempt.
  - **A valley open to one side**: give `inside` a ridge that doesn't close (a horseshoe: west peaks, the head, east
    peaks) and `"opens": "south"` (the side its mouth faces; without it, the side between the ridge's two ends). The
    floor runs out through the mouth to the frame's edge with no wall there; the walls stop where the ridge ends. Put
    `falls_to` at the mouth (`"edge:s"`) for a valley draining out of the level, or on a lake inside it.
  - An enclosed basin would, in reality, fill with water to its lowest rim. The report says so; the lake keeps its
    own level.
- **passes**: a saddle through a ridge.
  ```
  {"name": {"at": address near the ridge, "through"?: ridge, "floor"?: m, "width": m,
            "max_grade": 0.15, "sides": deg}}
  ```
  - It notches the crest: the way is highest on the crest and falls at `max_grade` both ways until it daylights (the
    ground drops away below it). The descent beyond is a **route's** job, since routes switchback. The report says
    how long the way is on each side and how steep the ground runs on beyond it.
  - Without `floor`, the saddle sits just above the higher side.
  - It's a gap in any wall it crosses.
- **canyons**: cut into a plateau (the plateau is `world.base`, or `rim`).
  ```
  {"name": {"river": river, "rim"?: m, "width": m rim to rim, "floor": m (the floor's WIDTH; its heights come from the river),
            "strata"?: {"bands": 3, "cliff": deg, "talus": m}}}
  ```
  - The river gives the path and the floor heights. The walls climb through horizontal strata: each band a cliff
    over a ledge, with talus at the foot. The bands sit at the same elevation all along the canyon, and the ledge
    slope is solved so the walls meet the rim at your width.
  - A side canyon is a canyon on a river that flows `"into"` the main one.
  - Rim addresses: `"canyon.west_rim@0.4"` (also east/north/south/left/right) is on the lip, 40% along the canyon from
    its river's source. A site there is a lookout: it sits back on the plateau at plateau height and never builds out
    over the lip; `"lip": true` brings it forward so its middle is at the lip (a viewpoint that sees in).
- **mesas**: `{"name": {"at", "top": m, "radius": m, "cliff": deg, "talus": 0.4}}`: a flat caprock top, a cliff,
  and a talus apron. A mesa is an address and a sight target (its top).
- **volcanoes**: a cone with a volcano's profile, its crater, radial gullies, collapse scars and lava flows.
  ```
  {"name": {"at": [x, y], "h": m (the rim's top), "type": "strato" | "shield" | "cinder",
            "base_radius"?: m (its footprint on the ground beneath), "slope"?: deg (average flank), "top_slope"?: deg,
            "crater"?: {"radius": m (the rim), "depth": m, "walls": deg, "breach": compass | address, "lake": true | m} | false,
            "caldera"?: {...the same: a wide crater, cliff walls, a flat floor},
            "gullies"?: 0..1,
            "collapses"?: {name: {"toward": compass | address, "width": m, "depth": m, "head": 0.15, "reach": 0.85,
                                  "walls": 50, "debris": true}},
            "flows"?: {name: {"from": "crater" | compass (a flank vent on that side) | address, "length": m, "width": m,
                              "thick": m, "toward"?: address | compass, "front": 38}}}}
  ```
  - **strato** (default): concave flanks, steep near the top (~33 deg) easing to the foot; **shield**: broad and low
    (~6 deg), convex; **cinder**: a small straight cone at ~30 deg with a big crater. Give `base_radius` or `slope`
    (with neither, the average slope is the type's). The footprint and the rim's height wander a little; `h` is the
    rim's highest point.
  - The crater's walls fall at `walls` to a flat floor `depth` below the rim. `lake` fills it (true: a quarter of its
    depth; or a level). `breach` opens the rim toward a side (a breached crater holds no lake).
  - **gullies**: radial valleys between ribs, from just below the rim to the foot (default 0.6 on a strato cone).
  - **collapses**: a horseshoe amphitheatre in the flank opening toward `toward`: `width` rim to rim, its floor `depth`
    below the flank under the headwall, rising to meet the flank at `reach` (share of the footprint's radius from the
    centre; `head` is where the headwall stands), walls at `walls` deg falling from the rim to the floor, and hummocky
    debris spread beyond its mouth. With a sea its floor ends at the shore (put a cove at it for a harbour). The report
    warns if the headwall breaks into the crater (it drains a crater lake): move `head` out.
  - **flows**: lava runs downhill from its vent on the ground as built (down gullies, into scars) for `length` metres:
    a sheet `thick` metres deep with steep margins and front, levees, pressure ridges and a lobed toe. Where the ground
    beside it is higher it fills the hollow. Reaching the sea it builds a lava delta. The report measures how far each
    stands above the ground beside it: a flow that doesn't stand proud doesn't read.
  - Addresses: the volcano's name (its top: a sight target), `"<name>.crater"`, `"<name>_rim@0.25"` (on the rim, a
    quarter of the way round clockwise from north), each flow (`"flow@0.5"`), each collapse (its floor). Zones: each
    flow, `"lava"` (every flow), `"<name>.crater"`, each collapse (and `"<collapse>.walls"`, `"<collapse>.floor"`),
    `"debris"`: cover them, and name them in `cliffs.except` (`{"type": "rock", "in":
    "lava", "slope": [0, 90], "color": "#2b2826"}`).
  - A volcanic island: `"world": {"kind": "volcanic island", "base": -40}` (the sea floor) and `"sea": {"level": 0}`
    with no `land` zone: the coast is wherever the cone rises out of the water.
- **sea**: water below a level out to the frame's edge, and the coast where land meets it.
  ```
  "sea": {"level": 0, "land"?: zone, "wander": 0.3, "depth": 30, "shore": "rocky" | "beach" | "cliffs",
          "cliffs"?: {"height": m | [lo, hi], "except": [addresses/zones/coves], "only": [...]},
          "beaches"?: {name: {"at": address, "length": m, "at_foot": false, "width": 35}},
          "coves"?: {name: {"at": address | "south", "width": m, "depth": m, "beach": true, "apron": m,
                            "valley": river | address}}}
  ```
  - Where the sea is: outside the `land` zone (an island: `{"near": [x, y], "radius": m}`; a coast: `"north"`), or
    without one, the ground below `level` that reaches the frame's edge (tilt the frame down toward the sea).
  - The sea is the low ground the land falls to: an island needs no `border`, and a ring of peaks (a crater) inside
    the land slopes down to the sea all round, a cone.
  - A coast without a `land` zone: the land is `world.base` (plus `tilt` and hills), and the sea is wherever that is
    below `level` and reaches the frame's edge. Clifftop farmland at 60 m falling south: `"base": 60`, a tilt down to
    the south steep enough to bring the ground below the sea level before the frame's edge (or a `land` zone).
  - A coast drawn as a `land` zone with nothing else holding the ground up (no ridges, rivers, basins or `border`):
    the land is `world.base` too (plus `tilt` and hills), so you draw the coastline and set the land's height.
  - The coastline wanders a little (`wander`, 0 to keep the zone's outline). The seabed shelves down to `depth`.
  - Shore forms, per stretch: **rocky** (the land dropping into the water), **beach** (the land graded down to sand at
    the water), **cliffs** (the land ending in a ~70 deg face; where the land is lower than the asked height it ramps up
    to the cliff top from inland, never a rim with lower ground behind). `cliffs` with `except`/`only` picks stretches;
    an address inland (a headland's peak) means the coast nearest it.
  - Below the cliffs: a wave-cut platform of rocks awash (`cliffs.platform`: m out from the face's foot, 0 for none)
    and sea stacks standing off the face (`cliffs.stacks`: how many, mostly off headlands; default about one per
    350 m of cliff coast, up to 8; 0 for none; `{"count": 4, "at": address}`: a string of them running out to sea
    from the coast nearest that address, a headland's tip, smaller further out). The report counts them and their
    heights.
  - The cliffs' height is the land's height where it meets the sea: a peak whose flanks reach past the coast makes
    cliffs as tall as the flank there (the report measures them and warns). Size the land and the peaks together.
  - **Beaches** go on the coast nearest their `at`. A beach grades the land down to the water; with `"at_foot": true`
    the cliff stays and a strip of sand `width` metres wide lies at its foot (a hidden cove beach).
  - **Coves** bite a horseshoe bay into the land at a compass side or the coast nearest an address: a mouth narrower
    than the bay, headlands either side, a beach at the head and behind it an `apron` of gentle ground (default a third
    of the width) walled by a steep scar: room for a harbour. A cove is an address; a site `"at": "cove"` stands on its
    apron just above the water. `"valley"`: the cove is the drowned mouth of a valley (a river or an address): the scar
    opens toward it at a road's grade, so a lane can come down to the harbour.
  - The sea is a lake named `"sea"` to everything else: `"sea.south_shore"` (the coast on the land's south side),
    `"see": ["sea"]` (or a cove: its water), water in the export. Zones `"beach"`, `"cliffs"`, `"coast"` and `"sea"`
    work in cover (`{"type": "sand", "in": "beach"}`), rugged and routes; `{"near": "sea", "radius": m}` is within that
    distance of its water.
  - Views and sight lines from out at sea stand on the water.
- **fords**: `{"name": {"on": "river@0.5", "width": m, "depth": m}}`: a shallow crossing. Rivers carry water; routes
  cross at fords, and anywhere else the report says a bridge is needed. River water width: `rivers.x.water` (0 for a
  dry bed); steep reaches narrow to a torrent a few metres wide.
- **rivers** (optional detail):
  ```
  {"name": {"source": [x, y, z], "through": [[x, y] or [x, y, z]], "mouth": [x, y, z] | "into": river,
            "hanging": m, "valley": {"profile": "U" | "V" | "gorge" | "open", "floor": m}}}
  ```
  Between two rivers with no ridge between them, the compiler adds a divide.
- **landforms**:
  - `lake {"at", "radius", "level"?, "depth", "lobes"?: 0..0.5, "dam"?: true | "downhill" | false}`: a basin carved
    below its level. `dam: true` puts a rim all round where the ground is lower. `"downhill"` is a farm pond: one
    straight bank across the slope. `false` is a natural lake that holds only what the ground holds. Without `level`
    it fills to the ground at its centre (a basin's drain lake: the basin floor's low end). `lobes: 0` gives a round
    shore.
  - `fan {"at": "river.mouth", "radius", "height"}`
  - `moraine {"across": "river@0.8", "height", "width"}`
  - `terrace {"along": river, "from", "to", "side": "left" | "right", "height", "width"}` (banks: left and right
    looking downstream)
- **rock**: every steep face (sea cliffs, basin and canyon walls, mesas, scars, craters) gets rock character on its
  own: buttresses and couloirs along it (the face moved in and out, so its lip and foot are notched and it stays as
  steep and tall), ledges where the face is gentle enough for a tread, and a boulder foot below it.
  The faces break into planar facets and joints (`facets`), and buttresses are chiselled: straight flanks, sharp crests,
  V couloirs. `"rock": {"buttresses": 0..1, "ledges": 0..1, "facets": 0..1, "boulders": 0..1, "scale": m}` tunes it
  (defaults 1, 0.6, 1, 1, the
  kind's crag size); `"rock": false` turns it off. The zone `"cliff_foot"` is the ground below the faces (for scree). Never on routes, sites or water. The report measures how broken the
  faces are (the share of steep ground turned away from its face's line: a smooth wall is ~0%).
- **rugged**: ruggedness as geometry (crags, and ledges of benches and risers, in patches).
  `{"name": {"in": zone, "gradient"?: {"from", "to", "range": [a, b]}, "amount": 0..1, "scale"?: m, "ledges"?: m}}`.
  Rock cover then finds the steep bits. Use it for "rocky", "craggy" or "broken ground".
- **volumes** (3D rock the heightfield can't hold: arches, sea caves, overhangs). They only show in the 3D mesh tiles
  (`export_terrain(name, tiles=True)`) and their views; the heightmap export, map and report ground stay 2.5D.
  `{"name": {"type": "arch" | "cave" | "overhang", "at": address, ...}}`, each cut out of the rock with rounded,
  slightly rough edges (`"blend"` m, default 1; `"rough"` m, default 0.4; `"op": "add"` builds rock instead):
  - `arch {"at", "toward"?: bearing | address, "width"?, "height"?, "floor"?, "roof"?: 2, "search"?: 30}`: a passage
    through the land near `at` (within `search` metres), where it is shortest for its height and still has `roof` metres
    of rock over it: real sea arches go through a thin neck. Heading `toward` if given, else the best of every heading.
    Its floor defaults to 1 m below the sea (water runs through); height to 65% of the ground above the floor, width to
    0.8 of the height. The mouths flare and the line bends a little. The report says where it went and how thick its
    roof is.
  - `cave {"at", "toward"?, "length": 30, "width": 6, "height": 5, "chamber"?: radius, "rise"?: m, "narrow"?: 0.7,
    "wander"?: 0.08, "floor"?}`: a passage into the rock heading `toward` (default: uphill). Its mouth is where the
    rock starts along that line, so `at` can be in the water just off a cliff. It narrows to `narrow` of its size and
    ends in a domed chamber if `chamber` is given. A sea cave's floor defaults to half a metre under the sea.
  - `overhang {"at", "along"?: bearing, "length": 30, "depth": 5, "height": 3.5, "floor"?}`: a wave-cut notch along the
    cliff face nearest `at` (following the face), `depth` metres in under the lip, its floor half a metre under the
    sea. The report says how much rock stands over it.
  - In the mesh tiles every steep face (45-62 deg and up) and everything a volume shaped gets solid rock character:
    planar facets with joints between them and bedding (grooves and beds standing proud or set back), which can
    overhang. `"rock": {"facets": 0..1, "bedding": 0..1}` scales it (as for the heightfield's rock), `"rock": false` or
    `"export": {"tiles": {"rock": 0}}` turns it off. Rock near the water is dark and wet up to ~2 m, higher inside caves.
- The compiler adds on its own: **divides** between rivers, **ribs** (short spurs down from ridges), a slight
  **wander** to ridges between summits, and **erosion** after your design is placed (drainage networks, scree,
  cliff bands from harder rock). Erosion never touches sites, routes, passes or lake shores, and the large-scale
  heights you set are kept.
  `"erosion": {"strength": 1, "detail": 1, "strata": {"spacing": m, "hard": 0..1, "dip": deg, "dip_toward": deg},
  "talus": deg}` tunes it. `{"strength": 0}` turns it off, and `"ribs": false` / `"divides": false` turn those off.

## Places, routes and walls
- **zones**: named regions, used everywhere below and as addresses. They can be:
  - `"quadrant:ne"`, `"north"`, `"south"`, `"east"`, `"west"`, `"centre"`, `"everywhere"` (these have soft edges)
  - `{"inside": "<closed ridge>", "inset"?: m}`
  - `{"polygon": [[x, y]...]}`, `{"near": address, "radius": m}`
  - `{"above": m}`, `{"below": m}`, `{"slope": [lo, hi]}`
  - `{"all": [...]}`, `{"any": [...]}`, `{"not": zone}`, `"feather": m`
- **sites**: pads (village, farmyard, camp, spawn). `{"at": address, "radius": m, "level"?: m, "above_water"?: m,
  "fall"?: 0.02, "toward"?: address | "south", "overlooks"?: address}`. `overlooks` picks the gentlest fall toward
  the target that lets most of the pad see it (a dead-level pad's own edge hides what's below it from its middle). With a shore address (`"lake.west_shore"`) the pad sits inland of that point, just above the
  water. The report gives its level and how far it cuts into or builds out of the slope (a warning over 25 m).
  `"shoulder": m` is how far the pad's banks blend into the ground (default 20 m, or half the radius): give small pads
  (a tee, a bench, a basket) a few metres, or they flatten a 40 m disc around them.
  `"prop": name, "facing"?: address` marks the site as where the engine drops a prop (a disc golf basket, a bench, a
  sign): meta.json's site gets `prop` with its name, ground position `xyz` and `yaw` (the compass bearing it faces),
  and views draw a stand-in at its real size instead of the 12 m marker pole (a disc golf basket, a tee pad slab, a
  blocky building for a "lodge"/"building"/"house", else a small post).
- **routes**: paths the compiler finds, grades and carves (switchbacks come out of the search).
  `{"from": address, "to": address, "via": [...], "max_grade": 0.12, "width": m, "avoid": [zones], "stay_in": zone,
  "max_earthworks": 25, "max_fill": m}` (`max_fill` limits banks alone, for a trail that shouldn't stand on one; it may then fail its grade). Cuts and fills stop at `max_earthworks` metres (beyond that it's a bridge or a tunnel); the
  report judges the road on the ground as built and says where it fails, where its bed ends off its stop (a cliff band
  in the way), and when no way at its grade existed at all.
  - Routes are planned on the ground nearly as built (each step may be a metre off its grade, which the carve evens
    out) at 85% of their limit, so what the plan promises the built road keeps; switchback legs too close for a bank
    between them are pushed apart where the ground allows (the report says where it doesn't).
  - Cliffs (over 50 deg) are walls to a route. Where they close a route's stops off from each other, it cuts a **break**:
    switchback legs at the route's grade across the cliff where it is lowest and nearest the way, as long as the cliff
    runs on beside the crossing, the ground shaped into benches with rock cut between them (a canyon wall trail).
    Breaks that don't open a way are taken out again. `"max_break": 250` (tallest cliff to break), `"leg": m` (longest
    leg), `"breaks": false` (none: a road that must go round). A cove's scar walls in its apron: open the cove's
    `"valley"` toward where the route goes.
- **walls**: unclimbable edges around a zone where no basin gives you one.
  `{"around": zone, "min_slope": 45, "height": m, "except": [addresses or passes]}`. The ground just outside is
  raised to make them (a little taller than `height`: the grid rounds a wall's lip and foot). The check walks straight
  out from each point of the edge and measures the tallest stretch at least `min_slope` steep: it must reach `height`.
- **cover**: masks for the engine, density or weight 0..1 per layer.
  ```
  {"type": forest | conifer | deciduous | rock | scree | grass | meadow | snow | sand | mud,
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
(each named by its `"name"`, else `intent_1`, ...). Free text goes in `"story"`, `"notes"` or `"wishes"`.

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

## Running
Through the MCP tools (a terrain lives in `workspace/terrain/<name>/`, every version kept):
- `set_terrain(name, spec=...)` saves and builds it and returns the report; `set_terrain(name, patch=...)` merges a
  change into the stored spec (objects merge key by key, `null` deletes), so edits stay small.
- `check_terrain(name)`: the report again. `look_terrain(name, map=True, masks=True, views=[...])`: the images
  (views take ~30 s plus ~10 s each). `export_terrain(name, size=1025, engine="unity")`. `terrain_history(name,
  revert_to=3)`.
- Questions for the designer come back as JSON from any of them.

Or from a shell:
```
uv run python examples/terrain_run.py <your.json>            # report + map + mask sheet + 3D views (~1-2 min)
uv run python examples/terrain_run.py <your.json> --no3d     # report + map + mask sheet (~20 s)
uv run python examples/terrain_run.py <your.json> --export   # also the engine files
```
The shell run writes its outputs beside the spec:
- `<stem>_map.png`: north-up hillshade with cover colours and contours. It shows rivers (blue), ridges (dashed
  red), routes (orange), sites (purple squares), walls (dark dots on the edge, bright red where climbable), names
  and a cover legend.
- `<stem>_masks.png`: each cover mask alone (white = dense).
- With `--export`, `<stem>_export/` holds (`"export": {"size": 1025, "engine": "unity"}` in the spec):
  - the heightmap: `height.npy` (float32, absolute metres), `height.png` (16-bit) and `height.raw` (Unity: 16-bit
    little-endian, first row south), both offset to 0; `meta.json` "unity" gives the terrain size and position
  - square at the engine size, padded if the frame isn't square
  - density masks per cover layer, plus water, roads, sites, playable and walls masks (always written: with no walls,
    playable is the dry ground a person can walk)
  - `splat*.png`: RGBA weights for the ground layers that sum to 1 (tree layers are instances, not in the splats)
  - `trees.csv`: tree instances (x, y, z, kind, layer)
  - `meta.json`: extent, height encoding, sites with their planes (level, fall, direction), passes, routes, rivers
    with their bed and water (surface height and width per point), fords, lakes
- **3D mesh tiles** (`export_terrain(name, tiles=True)`, `terrain_run.py --tiles`): the ground and its volumes as a
  grid of seamless glTF tiles in `tiles/`, for any engine. Tune with `"export": {"tiles": {...}}` (metres):
  `"tile": 64` (tile size), `"voxel": 1` (the meshing voxel, dividing the tile; coarser LODs are LOD0 decimated),
  `"lods": 3`, `"origin": [x, y]` (the grid's origin, default the frame's south-west corner), `"error": [0.04, 0.15,
  0.5]` (how far each LOD may stray from the true surface), `"budget": [12000, 3000, 800]` (triangles per tile per LOD),
  `"skirt": 0.3` (minimum skirt depth), `"collision": 1` (the LOD the collision mesh comes from), `"heightmap": 65`
  (samples per tile, 2^k + 1; 0 = none), `"splat": 128` (splat texels per tile; 0 = none).
  - `tile_<i>_<j>_lod<k>.glb`: one node at the tile's south-west corner (glTF: x east, y up, z south), primitive 0
    the ground, primitive 1 the skirts (double-sided); per vertex NORMAL, COLOR_0 (a display colour, so a plain
    glTF viewer shows it right) and `_WEIGHTS0`, `_WEIGHTS1` (ground layer weights, 4 per attribute, summing to 1).
    `collision_<i>_<j>.glb`: positions only. `heightmaps/`, `splats/` (RGBA = the same layers, a margin into the
    neighbours), `trees.csv`.
  - `manifest.json`: the grid (origin, tile size, count), per tile its bounds, files, triangle counts and the volumes
    it holds, the LODs, the material layers (name, colour, roughness, triplanar scale, which attribute and channel),
    the sea level, timings and the seam check.
  - Tiles meet exactly: neighbours share identical border vertices and normals at every LOD, and each tile's skirts
    reach past the neighbour's other LODs, so any mix of LODs shows no cracks. Every export runs a seam check on the
    written files (watertight joins, identical borders, normals, LOD gaps covered, heightmap edges) and fails loudly.
- `<view name>.png`: the views, with trees instanced from forest masks, roads as pale worn tracks and each site marked
  by a thin red pole 12 m tall (to judge what a view sees).

Read the images, not just the report. The report is in your units and ends with WARNINGS: read them.
