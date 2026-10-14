# Terrain: the big shapes

Read guide(topic="terrain") first: describe the brief, then write the spec.

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
  cross at fords, and anywhere else the report says a bridge is needed. River water:
  `rivers.x.water` = how far the water reaches either side of the line (a HALF width: 3 makes a 6 m river; 0 for a
  dry bed; default floor / 3, 3-25 m); steep reaches (grade 4% up) narrow it to a torrent, 2 m either side at 20%+:
  `"water": {"width": 5, "steep": 4}` sets that floor (the report says how much of each river narrows). meta.json `rivers.<r>.water` gives per point the FULL
  width the water covers as the built ground holds it (cut banks included), centred on the point.
- **rivers** (optional detail):
  ```
  {"name": {"source": [x, y, z], "through": [[x, y] or [x, y, z]], "mouth": [x, y, z] | "into": river,
            "hanging": m, "valley": {"profile": "U" | "V" | "gorge" | "open", "floor": m, "cut"?: true | false},
            "falls"?: [{"at": 0..1, "drop": m, "width"?: m}]}}
  ```
  Unknown keys are a report warning. **A river drawn on ground the design already made** (down a volcano's or hill's
  flank, or with its heights read off the existing ground) **cuts its own valley**: the base is solved without it and
  its valley (floor at the bed, sides at the profile's grade) is cut in, so the land beyond the valley stays put (held
  as the solve's low ground it raised the land round it by tens of metres). Automatic (the report says which rivers
  cut and why); `valley.cut` forces it either way. Rivers well above or below the ground made without them (they make
  the valley: a vale, alpine and basin rivers) are solved as before. Set a cutting river's heights under the ground by
  the depth of valley you want.
  **Waterfalls** `falls`: each a step of `drop` m at `at` (0..1 along the river; 1 = its mouth: a river ending at the
  foot of a sea cliff falls off the cliff's top into the sea). The drops come out of the river's own fall (source and
  mouth keep their heights, the reaches between grow gentler; together under 90% of it; falls at least 3 drops apart).
  Built: a band of hard rock across the valley at the upstream level (the lip), a face one cell across (the report
  gives its angle: under 60 deg the cells are too coarse for the drop; `detail` / `cell`), an amphitheatre cut back
  round a plunge pool (radius ~ half the width + 0.15-0.6 x the drop, 1.2-6 m deep), the river running on from the
  pool. `width` = the falling sheet (default the water's width). meta.json and the tiles' manifest carry `falls`:
  the lip line (two xyz at the lip's water level), drop, width, flow direction, the pool (centre xyz at its level,
  radius, depth, wet_radius: how far its level stands where the basin closes) and `into` (river | lake | sea), for the
  engine's falling sheet and spray; the stream clutter puts
  boulders round the pool and fallen blocks at the face's foot.
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
      A flow down a steep cone falls faster than anyone walks. `"grade": 0.2` makes the tube walkable: it
      switchbacks across the flow (legs along the slope's contours, up to `"swing"` m either side of the flow's
      line, default 30), a level landing at each turn and under each pit's pile of blocks, never steeper than the
      grade, and never higher than its depth under the ground (where the ground falls faster it runs deeper, and
      its pits get deeper). The report says how many switchbacks, how wide, how deep the pits are, and when the
      swing is too narrow for the grade ("needs switchbacks 54 m either side ... Give it "swing": 54").
  - An entrance is where a passage meets the open: at a cliff or hillside along the way in, or a shaft straight down
    from the ground with `"shaft": true` (a blowhole, a sinkhole). A hillside mouth's floor is the ground where the
    door opens (no higher: at a cliff foot, a geo's floor), and a karst floor leaves it on the passage's plain grade,
    taking on its bedding planes over the first ~20 m. `"z": m` on the entrance sets the door's floor yourself.
  - A chamber's floor is `depth` metres under the ground over it (karst 18 m, lava 7.5 m) or at height `z`; a sea
    cave's chambers sit at the water. `"in": m` puts a chamber that far into the rock from an address with a
    direction: `{"at": "cliff_foot:<address>", "in": 30}` is 30 m in from the foot of that cliff.
  - Passages run level through the chambers at either end and slope between them, so a passage that climbs needs
    room: the walk below tells you if it's too steep.
  - Every export walks a person (1.8 m tall, 0.5 m wide) through every passage and reports, in the manifest and the
    summary: floor range, least headroom, least width, the largest step between half-metre samples (0.6 m allowed),
    water depth (wading, or how far you swim), and PASSES or what stops them and where.
  - The report of set_terrain / check_terrain walks them already (seconds, not the export's hour): the same walk
    through the height field with the caves cut out, without the rock's relief (the export walks again in the
    finished rock), plus each passage's climb ("climbs 49 m over 149 m of slope (33%)": a cave floor walks up to 25%,
    sustained over 10 m), the rock over each passage's roof and each chamber's dome (under 1 m it opens to the sky),
    and a WARNING with what to change: the chamber's `z` / `depth` that makes the climb walkable, how long the passage
    would have to be, the stretch of a lava flow gentle enough for a tube (`from` / `to`) or its `grade`. A walk that
    fails names what stops it by kind: a step by a mouth is where the passage's floor meets the ground outside (the
    entrance's `z` or `at`), a step further in is the floor rising faster than it runs (a longer passage, closer
    floors), only blocked / tight / low passages change with `width` / `height`.
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
