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
- `crater` (caldera, volcano)
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
QUESTIONS FOR THE DESIGNER, and first what the tool **can't build** of what was asked (no sea yet, no volcano forms,
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
- **tilt**: `{"down": "south" | bearing deg, "grade": 0.07}` leans the whole frame (a south-facing slope). A tile
  with no ridges, rivers or basins is open ground at `world.base`, plus tilt and hills.
- **Frame edge**: `"border": 150` fixes the whole edge at that height. `{"n": 150, "s": "open", ...}` does it per
  side. An open side isn't fixed, so the ground carries on as it goes (the default).

## The big shapes
- **peaks** `{"name": {"at": [x, y], "h": z, "radius"?: m}}`. A peak on no ridge is a lone hill or knoll with a
  rounded top of that radius.
- **cols** (low points on a ridge) have the same shape.
- **ridges** `{"name": {"through": [peak/col | "ridge@0.4" | [x, y, z], ...], "crest": "arete" | "rounded"}}`. A
  ridge that ends where it starts is **closed**: a ring round a basin or crater.
- **basins**: a valley floor inside a closed ridge. Its walls are real mountainsides: they average the kind's face
  slope, with a hard cliff band that makes them unclimbable, and each stretch is as wide as the crest behind it
  needs. So high rims take room, and the report says how much floor is left.
  ```
  {"name": {"inside": "<closed ridge>", "floor": [low, high], "falls_to": address,
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
  - Rim addresses: `"canyon.west_rim@0.4"` (also east/north/south/left/right) is on the lip, 40% along the canyon. A
    site there is a lookout: it sits back on the plateau at plateau height and never builds out over the lip.
- **mesas**: `{"name": {"at", "top": m, "radius": m, "cliff": deg, "talus": 0.4}}`: a flat caprock top, a cliff,
  and a talus apron. A mesa is an address and a sight target (its top).
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
- **rugged**: ruggedness as geometry (crags, and ledges of benches and risers, in patches).
  `{"name": {"in": zone, "gradient"?: {"from", "to", "range": [a, b]}, "amount": 0..1, "scale"?: m, "ledges"?: m}}`.
  Rock cover then finds the steep bits. Use it for "rocky", "craggy" or "broken ground".
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
- **routes**: paths the compiler finds, grades and carves (switchbacks come out of the search).
  `{"from": address, "to": address, "via": [...], "max_grade": 0.12, "width": m, "avoid": [zones], "stay_in": zone}`.
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
  `orchard` plants rows (`"rows": 6` m apart, `"along": "contour" | "east" | "north"`). `"count": 6` on any tree
  layer scales it to about that many trees ("a few trees"). Types have sensible defaults (forest avoids steep ground, water, roads and sites; rock favours slopes over
  32 deg), and anything you give overrides them.
- **intent** (checks; nothing is changed):
  - `{"at": address, "above_flood": m}`
  - `{"path": [addresses], "max_grade": g}` (straight legs)
  - `{"from": address, "see": [addresses], "min_visible": m, "min_prominence": m, "skyline": true, "eye": 1.7}`. From
    a **site**, it tries the eye at the centre and at eight spots across the site, and reports how many see the target
    (a level pad's own edge can hide what's below it from the middle). For a peak, hill or mesa: how many metres of it
    show above what's in front of it (down to its own foot), **how far its top stands above the skyline beside and
    behind it** (a peak on a ring of mountains can be all "showing" and still not stand out: `min_prominence` checks
    this), and whether it's on the skyline (nothing behind it higher). For a lake: the share of its surface you see.
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
- `[x, y]`, or `{"from": address, "offset": [dx, dy]}`

`"views": [{"name": "file_stem", "eye": address | [x, y, z], "lift": m, "look": address, "fov": deg}]` are
perspective renders. The eye stands on the ground at an address; `lift` raises it. An eye in or against the ground is
raised to stand clear of it (the run says so).

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
- `<view name>.png`: the views, with trees instanced from forest masks.

Read the images, not just the report. The report is in your units and ends with WARNINGS: read them.
