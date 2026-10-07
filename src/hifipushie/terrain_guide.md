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
no glaciers...; caves and overhangs only in the 3D mesh tiles): tell the designer that before anything else. The questions: is it like one of the
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
  with no ridges, rivers or basins is open ground at `world.base`, plus tilt and hills. The tilt leans ridges and the
  peaks and cols on them too (not lone hills): the report says by how much at each, and what `h` to give instead.
- **Frame edge**: `"border": 150` fixes the whole edge at that height. `{"n": 150, "s": "open", ...}` does it per
  side. An open side isn't fixed, so the ground carries on as it goes (the default).

## The big shapes
- **peaks** `{"name": {"at": [x, y], "h": z, "radius"?: m}}`. A peak on no ridge is a lone hill or knoll: `radius`
  is its rounded TOP (not its footprint); its flanks fall at `flanks` degrees (default 18) to the ground, or give its
  footprint directly with `base_radius`. The report ends with the frame's highest ground and warns when it's nothing
  you placed.
  - `"form"`: `"pyramid"` (planar faces between arêtes, a point on top; the default in alpine valleys and cirques),
    `"horn"` (steeper, three faces hollowed into cirques between sharp arêtes: a Matterhorn), `"dome"` (rounded: the
    default elsewhere; on a ridge its top is rounded over `radius`, default 3% of the frame). Each ridge leaving the peak is one of its arêtes, at that ridge's own fall; more are added up
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
  - **The wall as a profile**, from the crest down, as you'd say it: `"walls": {"from_top": ["cliffs", "scree",
    "forest"]}`, or with shares of the wall's height: `[["cliffs", 0.4], ["scree", 0.25], ["forest", 0.35]]`. Bands:
    `cliffs` (min_slope + 14, at least 62 deg), `crags` (50), `slabs` (42), `scree` (35, concave), `forest` (28),
    `meadow` (20). The wall's width follows from them (`walls.average` is ignored then). Peak forms (pyramid, horn)
    still carve the top of the wall under a peak, so the top band is gentler there. Each band is a zone (`"valley.cliffs"`, `"valley.scree"`, ...;
    also `"valley.wall"` and `"valley.floor"`) and gets its cover (rock, scree, conifer forest, meadow) unless a layer
    of yours is `"in"` it; your own tree layers stay out of its bare bands. Scree runs down into the forest in tongues.
    The report measures each band's share of the height and slope as built.
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
  "sea": {"level": 0, "land"?: zone, "wander": 0.3, "depth": 30, "shore": "rocky" | "beach" | "cliffs" | "rocks",
          "cliffs"?: {"height": m | [lo, hi], "except": [addresses/zones/coves], "only": [...],
                      "heights"?: {zone or address: m | [lo, hi]}, "geos"?: {name: {"at", "length", "width"}},
                      "jut": 1, "talus": 1},
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
    to the cliff top from inland, never a rim with lower ground behind), **rocks** (the land eased down to a metre or so
    above the water, ending in a strip of boulders at the waterline, `rocks_width` m (default 6): grass running down to
    low rocks; the zone `"rocks"` is that strip). `cliffs` with `except`/`only` picks stretches; an address inland (a
    headland's peak) means the coast nearest it. `cliffs.heights` sets the height per stretch (`{"the_point": [14, 18]}`).
  - A cliff line juts and bays at tens of metres (buttresses and bights, `jut`: 0 for a straight line), its lip rolls
    over by varying amounts, and aprons of fallen blocks lean on its foot in patches (`talus`: 0 for none). Cliffs over
    ~15 m step back at a ledge (two over ~30 m) that wanders in height and pinches out (`tiers`: 0 for one face).
  - **Geos** (zawns): narrow clefts the sea runs up between vertical walls. Without a `geos` entry a cliff coast gets a
    few at random; `"geos": {"chasm": {"at": address, "length": 60, "width": 8}}` places them (the coast nearest `at`,
    cut `length` m inland, narrowing, the sea running to its head); `"geos": 0` for none. The report gives each placed
    geo's floor at its mouth and head and how far up it the sea runs.
  - The foot of the sea cliffs is an address: `"cliff_foot:<address>"` (the foot nearest it; plain `"cliff_foot"`: nearest
    the frame's middle), its direction pointing into the rock. The export lists the feet (`cliff_feet` in meta.json).
  - Below the cliffs: a wave-cut platform of rocks awash (`cliffs.platform`: m out from the face's foot, 0 for none)
    and sea stacks standing off the face (`cliffs.stacks`: how many, mostly off headlands; default about one per
    350 m of cliff coast, up to 8; 0 for none; `{"count": 4, "at": address}`: a string of them running out to sea
    from the coast nearest that address, a headland's tip, smaller further out). The report counts them and their
    heights.
  - The cliffs' height is the land's height where it meets the sea: a peak whose flanks reach past the coast makes
    cliffs as tall as the flank there (the report measures them and warns). Size the land and the peaks together.
  - **Beaches** go on the coast nearest their `at`. A beach grades the land down to the water; with `"at_foot": true`
    the cliff stays and a strip of sand `width` metres wide lies at its foot (a hidden cove beach).
  - **Coves** bite a bay into the land at a compass side or the coast nearest an address: wider inside than at the
    mouth, a beach at the head and behind it an `apron` of gentle ground (default a third of the width) walled by a
    steep scar: room for a harbour. They're asymmetric: a rocky **headland** on one side runs out past the mouth (cliffs
    all round it, standing at least `headland_height` m, default ~22% of the width, at least 18; the land's own height
    if that's more), the bay swings away from it, and a low rocky point on the other side narrows the mouth. The cove
    sits in a hollow: the land round the bay (not the headland) eases down to a rim `rim` m over the water (default a
    tenth of the width, 4-18) at `rim_slope` (16 deg), so a cove in a high plateau isn't a pit ringed by cliffs (coves with a beach only; gentle ground only, at most `rim_depth` m, default a tenth of the width, 6-25). `"headland"`: `"auto"` (the side where the land is higher),
    a compass side or address, `"left"`/`"right"` (looking in from the sea), `"both"`, `"none"`; `"headland_length"` m.
    The report measures the bay's widest water, the mouth's narrowest gap and each headland's top. A cove is an address;
    a site `"at": "cove"` stands on its apron just above the water. `"valley"`: the cove is the drowned mouth of a
    valley (a river or an address): the scar opens toward it at a road's grade, so a lane can come down to the harbour.
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
  The source and the mouth need a height (z); through points may leave it out. The river's heights are its bed: set
  them near the ground they cross (the report warns of a **trench**, the bed far below the ground either side: a
  basin floor above the river's heights cut it into a slot gorge). Its water never stands above its banks, and the banks
  are graded down to it. A river leaving a dammed lake runs over the dam as a spillway at the lake's level. In a coast
  drawn as a `land` zone, the land away from the rivers stays at `world.base`.
  Between two rivers with no ridge between them, the compiler adds a divide.
- **landforms** `{"name": {"type": "lake" | "fan" | "moraine" | "terrace", ...}}` (the type is always given):
  - `lake {"at", "radius", "level"?, "depth", "lobes"?: 0..0.5, "dam"?: true | "downhill" | false | "moraine" | "rock bar"}`: a basin carved
    below its level. `dam: true` puts a rim all round where the ground is lower. `"downhill"` is a farm pond: one
    straight bank across the slope. `false` is a natural lake that holds only what the ground holds. Without `level`
    it fills to the ground at its centre (a basin's drain lake: the basin floor's low end). `lobes: 0` gives a round
    shore.
    - **A lake held partway down a sloping valley**: `"dam": "moraine"` (a rounded, hummocky ridge of till bowed
      downstream) or `"rock bar"` (a rock step: gentle on the lake side, a steep face below). It runs right across the
      valley at the lake's downstream end (`radius` below its centre), ends against the valley sides on its own, and has
      a spillway channel at the lake's level where the river leaves (or the crest's lowest point). The water runs back
      up the valley as far as the floor lies below the level. Downstream is the river through the lake, `"toward"`
      (compass or address), or the way the valley falls. Leave `level` out and it's set a little over the floor at the
      dam's site; `"freeboard"` (crest over the water), `"dam_width"`. The zone `"<lake>.dam"` is the dam.
  - `fan {"at": "river.mouth", "radius", "height"}`
  - `moraine {"across": "river@0.8", "height", "width"}`
  - `terrace {"along": river, "from", "to", "side": "left" | "right", "height", "width"}` (banks: left and right
    looking downstream)
- **rock**: every steep face (sea cliffs, basin and canyon walls, mesas, scars, craters) gets rock character on its
  own, big structure first: buttresses with flat fronts and V gullies a face-height or so apart (20-40 m on a sea
  cliff, a few hundred on an alpine wall), strong in some stretches and slabby in others; tall cliffs step back in
  tiers with a ledge where grass holds (`"tiers": 0..1`; sea cliffs have their own, `sea.cliffs.tiers`); then ribs,
  facets and beds inside that (the face moved in and out, so its lip and foot are notched and it stays as steep and
  tall), ledges where the face is gentle enough for a tread, and a boulder foot below it; scree cones below the
  gullies. Rock varies in tone (pale buttresses, dark gullies).
  The faces break into planar facets and joints (`facets`), buttresses are chiselled (straight flanks, sharp crests, V
  couloirs), cliffs over ~60 deg are stepped by level beds where the grid is fine enough (`bedding`), and scree cones
  lean on the foot of the cliffs in patches (`aprons`: room below a wall for scree and, lower down, trees).
  `"rock": {"buttresses": 0..1, "tiers": 0..1, "ledges": 0..1, "facets": 0..1, "bedding": 0..1, "boulders": 0..1, "aprons": 0..1,
  "scale": m}` tunes it (defaults 1, 1, 0.6, 1, 1, 1, 1, the kind's crag size); `"rock": false` turns it off. The zone
  `"cliff_foot"` is the ground below the faces, aprons included (for scree cover). Never on routes, sites or water. The
  report measures how broken the faces are (the share of steep ground turned away from its face's line: a smooth wall is
  ~0%), closed pits per km2 (round hollows: rock breaks in planes), how rounded the faces are, and the aprons' area.
  Views add a rock material's relief on faces steeper than ~55 deg (beds and joints below the grid's size), as an
  engine's cliff material would.
- **rugged**: ruggedness as geometry (crags, and ledges of benches and risers, in patches).
  `{"name": {"in": zone, "gradient"?: {"from", "to", "range": [a, b]}, "amount": 0..1, "scale"?: m, "ledges"?: m}}`.
  Rock cover then finds the steep bits. Use it for "rocky", "craggy" or "broken ground". Crags are blocks with flat
  faces; only dry land is made rugged (never the seabed or a lake bed), and zones made from the water ("near" the sea)
  work. The report compares its detail with similar ground outside it.
- **volumes** (3D rock the heightfield can't hold: arches, sea caves, overhangs). They only show in the 3D mesh tiles
  (`export_terrain(name, tiles=True)`) and their views; the heightmap export, map and report ground stay 2.5D.
  `{"name": {"type": "arch" | "cave" | "overhang", "at": address, ...}}`, each cut out of the rock with rounded,
  slightly rough edges (`"blend"` m, default 1; `"rough"` m, default 0.4; `"op": "add"` builds rock instead):
  - `arch {"at", "toward"?: bearing | address, "width"?, "height"?, "floor"?, "roof"?: 2, "search"?: 30,
    "through"?: m, "neck"?: m}`: a passage through the land near `at` (within `search` metres), where it is shortest for
    its height, keeps a roof of at least `roof` metres and half its span, has open sea (no land standing over most of
    the opening within 60 m) past both mouths, and is tall enough to read (taller wins, all else equal). Heading `toward` if given, else the best of every heading. Its floor defaults to 1 m below the sea
    (water runs through); height to 65% of the ground above the floor (less if the roof needs it), width to 0.8 of the
    height (capped at 8 m): arches are taller than wide. Real sea arches go through a FIN of rock about as thick as the
    arch is tall (Durdle Door); through a wider headland one read as a tunnel with a turf lid. So where the land is more
    than 1.25 x `through` (default 0.9 x the height, at least 4 m) along its line, bays are cut in from the sea on both
    sides down to its floor, `neck` metres (default 1.2 x its width, at least 6) either side of it, leaving a fin
    `through` m thick: the tip beyond stands on the arch. The report says where it went, the neck, the roof, and a
    see-through check (the share of rays along the opening that come out clear, and what lies beyond each mouth:
    "WARNING" when under half shows daylight).
  - `cave {"at", "toward"?, "length": 30, "width": 4.5, "height": 6, "chamber"?: radius, "rise"?: m, "narrow"?: 0.7,
    "wander"?: 0.08, "floor"?, "roof_rule"?: true}`: a passage into the rock heading `toward` (default: the address's own
    direction, e.g. `"at": "cliff_foot:<address>"` goes straight into the cliff; else uphill). Its mouth is where the
    rock starts along that line, so `at` can be in the water just off a cliff. It narrows to `narrow` of its size and
    ends in a domed chamber if `chamber` is given. A sea cave's floor defaults to half a metre under the sea. Sea caves
    follow joints: make them taller than wide (the report says when one isn't). The rock over it is kept at least
    1.5 m and half its span thick: it lowers where the ground over it thins, ends where even 1.8 m wouldn't fit, and
    a chamber shrinks to fit (all said in the report; `"roof_rule": false` keeps your sizes and lets it break through).
  - `overhang {"at", "along"?: bearing, "length": 30, "depth": 5, "height": 3.5, "floor"?}`: a wave-cut notch along the
    cliff face nearest `at` (following the face; `"cliff_foot:<address>"` sets it along that cliff), `depth` metres in under the lip, its floor half a metre under the
    sea. Where the cliff behind is too low to roof it (1.5 m and half its height) it is shallower, dying out to a nick on
    a low stretch. The report says how much rock stands over it.
  - In the mesh tiles every steep face (45-62 deg and up) and everything a volume shaped gets solid rock character:
    planar facets meeting in crisp creases and bedding (a notch at each bed, beds standing proud or set back), which
    can overhang. Its colour is the heightfield's own rock there (the kind's rock, any rock cover layer such as a
    cliff's grey or black lava), toned per bed and facet and darker in crevices. `"rock": {"facets": 0..1, "bedding": 0..1}` scales it (as for the heightfield's rock), `"rock": false` or
    `"export": {"tiles": {"rock": 0}}` turns it off. Rock near the water is dark and wet up to ~2 m, higher inside caves.
    Thin rock (an arch's fin, slim stacks and headlands, anything narrower than ~20 m) keeps its relief, bounded by
    how thick the rock is at that height (it never carves through or cuts a top off), and shows its strata: beds
    1-3 m thick, the soft ones set back and darker, the hard ones flush and paler, as the sea picks them out.
- **caves** (mesh tiles only, like volumes): a cave is a skeleton of named entrances and chambers joined by passages.
  ```
  {"name": {"kind": "sea" | "karst" | "lava", "width"?: m, "height"?: m,
            "entrances": {"door": {"at": address, "shaft"?: true}},
            "chambers": {"hall": {"at": address, "depth"?: m | "z"?: m, "size"?: m | [across, up]}},
            "passages": [["door", "hall"], {"from": "hall", "to": "top", "via"?: [[x, y], ...], "width"?, "height"?}]}}
  ```
  - `kind` sets the shapes:
    - `sea`: floors at the water, wide low passages, domed chambers.
    - `karst`: keyhole passages (a wide bedding-plane tube with a flat roof, a slot below it), smooth dissolved walls
      with thin beds standing out as ledges (`"ledges"`: m, default 0.45), floors on the rock's bedding planes. A shaft
      entrance opens in a **doline**: a grassy funnel ~36 m across with an uneven rim and a rocky pit at its throat
      (`"doline": {"radius": 18, "depth"?, "scarp"?}` on the entrance; `false` for a bare shaft). The doline's depth is
      limited by the rock over the passage: put the cave deeper (chambers `depth` 18+) for a deeper funnel.
    - `lava`: wide round tubes at a steady depth under the ground they follow (on its smoothed grade, not its bumps),
      benches along the walls, skylights where the roof is thin with fallen blocks under them; its entrances are
      always collapse pits (the roof fallen in, a low cone of blocks to climb down), as wide as the tube.
      `{"kind": "lava", "flow": "<flow name>", "from": 0.25, "to": 0.85}` runs a tube down a volcano's lava flow
      between those shares of its length, a collapse pit at each end (no entrances or passages needed).
  - An entrance is where a passage meets the open: at a cliff or hillside along the way in, or a shaft straight down
    from the ground with `"shaft": true` (a blowhole, a sinkhole).
  - A chamber's floor is `depth` metres under the ground over it (karst 18 m, lava 7.5 m) or at height `z`; a sea
    cave's chambers sit at the water. `"in": m` puts a chamber that far into the rock from an address with a
    direction: `{"at": "cliff_foot:<address>", "in": 30}` is 30 m in from the foot of that cliff.
  - Passages run level through the chambers at either end and slope between them, so a passage that climbs needs
    room: the walk below tells you if it's too steep.
  - Every export walks a person (1.8 m tall, 0.5 m wide) through every passage and reports, in the manifest and the
    summary: floor range, least headroom, least width, the largest step between half-metre samples (0.6 m allowed),
    water depth (wading, or how far you swim), and PASSES or what stops them and where.
- **ground**: gentle ground rolls at player scale on its own: field-scale undulation (1-2 m over ~100 m), swales
  (broad shallow hollows where water gathers, down the slope) and hummocks in patches, by the kind (none in dunes).
  Never on sites, routes, passes or water; it doesn't make ponds. `"ground": {"undulation": 0..2, "swales": 0..2,
  "hummocks": 0..2, "scale": m}` tunes it, `"ground": false` turns it off. The report measures how much the gentle
  ground varies about its ~50 m trend (plaster-smooth ground is under ~0.1 m).
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

## Styles: the ground in the plants' art styles, zone by zone

One terrain can hold regions drawn in different styles (the vegetation styles' worlds: blobby, anime, ... and
realistic), so a blobby oak stands on blobby ground. The engine's shader draws the transition as the player walks
through it, so a pixel near a border needs BOTH styles' looks: the textures are shipped per style, not baked per tile.

```json
"zones": {"dumpling_downs": "west", "painted_east": "east"},
"styles": {"blobby": "dumpling_downs", "anime": ["painted_east", "knoll_hill"],
           "cartoon": {"in": "pencil_bay", "band": 30, "sheet": {"layers": {"grass": {"scale_m": 10}}}}}
```
- style -> a zone, any region address or a list; everywhere else is `realistic`. Zones are a partition: a style
  listed later wins where zones overlap. `band` (m, default 20) is the default transition width written into the
  weight maps; `sheet` overrides any number of the style's sheet.
- A style is a sheet of numbers over general operations (`src/hifipushie/terrain_styles/<name>.json` over
  `_base.json`; a new style is a new sheet): `colour` (saturation / value turned on the terrain's own layer colours:
  the same numbers as the plant style, so ground and plants step together), per ground layer (grass, turf, scrub,
  forest_floor, sand, earth, rock, wet_rock, snow; `like` another layer) a tileable texture built from ops: `blotch`
  (big soft colour fields, `steps` tones), `strokes` (directional brush dabs, warm-light / cool-shadow `tones`),
  `bands` (painted strata, level on cliffs), `ripples`, `dots`, `grain`, `cracks` (ink lines), `facets`, `pillow`;
  `scale_m` (the texture's side), `projection` top | triplanar; `macro` (how much of the baked tile colour's variation
  the style keeps: 1 realistic, 0 blobby), `macro_normal` (share of the baked normal kept), `detail` (the realistic
  tiling detail swatches), `overlay` (the style's own close-up swatch: anime brush dabs), `seasons` (per season per
  layer `{"mix": sRGB, "amount"}`, as the plants'), `snow` (numbers for the engine's snow, as the plants'), `rock`
  (the zone's rock shape: geometry, see below).
- What artists do, and why it is built this way: stylised ground in games is a few tiling layer textures blended by
  weights (slope, height, painted masks), height-blended at layer edges, triplanar on cliffs, with anti-tiling
  ([Unity terrain height blend](https://github.com/unitycoder/TerrainHeightBlend-Shader), [stochastic
  tiling](https://github.com/unitycoder/Procedural-Stochastic-Terrain-Shader)); hand-painted textures are SHAPES in a
  few value steps, light warm and shadow cool, not noise; stylised rock is sculpted big -> medium planes -> polish
  (fewer, bigger planes, softened edges: [polycount](https://polycount.com/discussion/comment/2147949)). So a style's
  texture is an op stack with few, big shapes; its rock shape is geometry in the zone's tiles.
- Files (in every tiles export of a spec with styles, or alone with `export_terrain(name, styles_only=True)`, seconds,
  beside the last export): `materials/<style>/<layer>_albedo.png` (sRGB, mean = the layer colour), `_normal.png`
  (tangent, glTF: +x east / along the face, +y north / up), `_height.png` (16-bit, 0.5 = 0, +- height_m),
  `materials/<style>/overlay_*`; `styles/<style>_sd.png` (signed distance to the style's zone edge, 16-bit,
  +- range_m, + inside) for a band of your own (ragged, moving), `styles/weights<g>.png` (the weights with `band`);
  manifest `styles` (also `styles.json`): `contract`, `order`, per style its zones, numbers, per layer files, size,
  colour (sRGB + linear), roughness, `seasons` (colour + `tint_linear` per season), `snow`, and `tiles` (which styles
  reach each tile), `recipe` (the per-pixel blend: style weights x layer weights x textures, macro, normals, seasons).
- The per-tile baked maps stay the realistic look; a styled pixel takes from them only what its `macro` /
  `macro_normal` say. No lighting is baked into any style's textures (AO is the baked map's).
- Look: `look_terrain(name, styles=True)` writes a swatch sheet (each style x layer: tiled albedo, lit, normal) and
  a transition strip per layer.

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
  grid of seamless glTF tiles in `tiles/`, for any engine. Two modes (`"mode"`):
  - `"cliffs"` (default, how games do it): the ground is the heightmap (`ground_<i>_<j>_lod<k>.glb` grid meshes, the
    same samples as `heightmaps/height_<i>_<j>.npy`: float32 metres, C order, row 0 the tile's NORTH edge, column 0
    its west; and, only for the tiles that have holes, `heightmaps/holes_<i>_<j>.png` (255 = hole, one pixel per
    heightmap cell, row 0 north; the ground entry's `holes` in the manifest) where a cave mouth, arch or shaft opens
    through it; the ground GLBs and `ground_collision_<i>_<j>.glb` leave those cells out), and `tile_<i>_<j>_lod<k>.glb` are 3D cliff meshes laid over it wherever the ground is steeper than
    `"cliff_slope": 42` (deg) or a volume opens, reaching `"cliff_margin": 4` m past it. Under a cliff the heightmap is
    pushed a few metres into the rock, so the cliff face covers it; each cliff mesh is a closed shell of rock that
    sinks under the heightmap at its edges (its buried back is primitive `extras.role = "buried"`: skip it if you
    like). Nothing to stitch. `"cave_wall": 3` m of rock is kept round every cave.
  - `"full"`: the whole ground as 3D mesh tiles (no heightmap in the scene).
  Both bake maps per tile per LOD (`"maps": true`): each tile has its own UV atlas and embeds base colour, ORM
  (occlusion, roughness) and a tangent-space normal map from the exact rock (with bake-only fine detail: small facets,
  cracks, the bedding notch), so detail comes from textures, not triangles. `"texel_density": [8, 4, 2]`
  (texels per metre per LOD: the unique maps carry the macro look only, the tiling rock detail in `materials/` and
  the manifest's `detail.recipe` draw what is finer than ~0.5 m), `"texture_max": 2048`, `"ground_density": 4`, `"micro": 1` (fine rock detail; 0 none).
  Beside the GLBs: `maps/<tile>_height.png` (16-bit displacement) and `maps/<tile>_weights<g>.png` (layer weights),
  `materials/<layer>_albedo/_normal/_height.png` (tileable detail textures) and the manifest's `engine_recipe` (how
  an engine blends the layers over the baked maps, triplanar on rock). The ground gets tiling detail too, one swatch
  per kind (`materials/turf_detail_*.png` on mown turf, `grass_detail_*.png` on long grass and scrub,
  `sand_detail_*.png` on sand: ripples, grit, pebbles; the manifest's `ground_detail.swatches` with its recipe: laid
  from above at 2 m, fading out by 20-70 m; `"grass_detail": false` leaves it out). Below that the ground's maps carry
  its own relief in their normals (tussocks, scrub lumps, the mower stripes' lean).
  See them as an engine would: `look_terrain(name, views=[...], tiles=True)` renders the last tiles export (baked maps,
  rock and turf detail, arches and caves, trees, the sites' props as stand-ins for scale: baskets, tee pads, a lodge),
  under a raking sun chosen per view (`"sun"` as for views) with aerial haze (`haze`: metres for 63%, default 5000);
  `light="clear"` swaps the default hazy sky for a deep blue clear one and a strong sun (what a sunny photo shows:
  judge colours against photos in it; the sky as a camera sees it, deeper than the light it casts, and a deep blue sea). Other settings (metres):
  `"tile": 64` (tile size), `"voxel": 0.5` (the meshing voxel, dividing the tile; coarser LODs are LOD0 decimated),
  `"lods": 3`, `"origin": [x, y]` (the grid's origin, default the frame's south-west corner), `"error": [0.04, 0.15,
  0.5]` (how far each LOD may stray from the true surface), `"budget": [12000, 3000, 800]` (triangles per tile per LOD: a tile LOD over twice its budget FAILS the export's
  checks, named with its count and why; `"collision_budget"` caps the collision mesh, default twice its LOD's),
  `"skirt": 0.3` (minimum skirt depth), `"collision": 1` (the LOD the collision mesh comes from), `"heightmap": 65`
  (samples per tile, 2^k + 1; 0 = none), `"splat": 128` (splat texels per tile; 0 = none).
  - `tile_<i>_<j>_lod<k>.glb`: one node at the tile's south-west corner (glTF: x east, y up, z south), primitives
    by `extras.role` and material: "surface" first (what is seen; material `terrain_baked`), then in cliffs mode
    "buried" (the shell's back under the heightmap: skip it, or draw it; material `terrain_reference`), then "skirt"
    (double-sided, material `terrain_skirt`). An importer that drops extras (Godot) can go by the material name. Per
    vertex NORMAL, TANGENT, TEXCOORD_0 (the baked maps),
    TEXCOORD_1 (the splat) and `_WEIGHTS0`, `_WEIGHTS1` (ground layer weights, 4 per attribute, summing to 1); with
    `"maps": false`, COLOR_0 (a display colour) instead of the baked material.
TEXCOORD_2 and `_DETAIL` belong to the tiling
    rock detail (the manifest's `detail`).
    `collision_<i>_<j>.glb`: positions only (cliffs mode: the cliff shells, backs included; load them together with
    `ground_collision_<i>_<j>.glb`, the heightmap grid with its hole cells cut). `heightmaps/`, `splats/` (RGBA = the same layers, a margin into the
    neighbours), `trees.csv`.
  - `manifest.json`: the grid (origin, tile size, count), per tile its bounds, files, triangle counts and the volumes
    it holds, the LODs, the material layers (name, colour, roughness, triplanar scale, which attribute and channel),
    the sea level, timings and the seam check.
  - Tiles meet exactly: neighbours share identical border vertices and normals at every LOD, and each tile's skirts
    reach past the neighbour's other LODs, so any mix of LODs shows no cracks. Every export runs a seam check on the
    written files (watertight joins, identical borders, normals, LOD gaps covered, heightmap edges, and black shards:
    faces whose corner normals point away from them, over 0.01% / 0.05% / 0.5% of LOD 0 / 1 / 2; baked maps decoded
    from both sides of every shared border; in cliffs mode the ground tiles' borders, heightmap never standing in a
    void, never showing through a cliff face, no cliff-mesh piece floating clear of the ground) and fails loudly. The
    manifest's `memory_gb` says what the export used (it runs one heavy job at a time, workers sized by free memory).
- `<view name>.png`: the views, with trees instanced from forest masks, roads as pale worn tracks and each site marked
  by a thin red pole 12 m tall (to judge what a view sees).

Read the images, not just the report. The report is in your units and ends with WARNINGS: read them.
