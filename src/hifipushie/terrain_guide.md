# Terrain spec guide (experimental)

You describe terrain in JSON, in the terms a level designer uses (a basin, a pass, a wall, a lake, a village site,
a road, forest here and rock there, this must be visible from there). A compiler turns that into a height field
and cover masks. You never paint heights. Where you want a specific landform (a named ridge, a river, a moraine),
you can drop down and write it; otherwise the compiler fills in plausible ground (drainage, spurs, gullies)
between what you placed, and never moves anything you placed.

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
- **Frame edge**: `"border": 150` fixes the whole edge at that height. `{"n": 150, "s": "open", ...}` does it per
  side. An open side isn't fixed, so the ground carries on as it goes (the default).

## The big shapes
- **peaks** `{"name": {"at": [x, y], "h": z, "radius"?: m}}`. A peak on no ridge is a lone hill or knoll with a
  rounded top of that radius.
- **cols** (low points on a ridge) have the same shape.
- **ridges** `{"name": {"through": [peak/col | "ridge@0.4" | [x, y, z], ...], "crest": "arete" | "rounded"}}`. A
  ridge that ends where it starts is **closed**: a ring round a basin or crater.
- **basins**: a valley floor inside a closed ridge.
  ```
  {"name": {"inside": "<closed ridge>", "floor": [low, high], "falls_to": address,
            "shape": "bowl" | "flat" | "open",
            "walls": {"min_slope": 45, "profile": "straight" | "concave" | "convex", "height": m, "except": [...]}}}
  ```
  - The floor rises from `low` at `falls_to` (usually a lake) to `high` at its edge, and all water drains there.
  - Between the floor's edge and the crest is the basin's wall: the mountainside itself, as wide as `min_slope`
    allows. It's checked like a wall (share of the edge that holds, climbable spots).
  - Passes through its ridge are exempt.
  - An enclosed basin would, in reality, fill with water to its lowest rim. The report says so; the lake keeps its
    own level.
- **passes**: a saddle through a ridge.
  ```
  {"name": {"at": address near the ridge, "through"?: ridge, "floor"?: m, "width": m,
            "max_grade": 0.15, "sides": deg}}
  ```
  - It's highest where it crosses the crest and ramps down to the ground on both sides, lengthening each ramp until
    it's `max_grade`.
  - Without `floor`, the saddle sits just above the higher side.
  - It's a gap in any wall it crosses.
- **rivers** (optional detail):
  ```
  {"name": {"source": [x, y, z], "through": [[x, y] or [x, y, z]], "mouth": [x, y, z] | "into": river,
            "hanging": m, "valley": {"profile": "U" | "V" | "gorge" | "open", "floor": m}}}
  ```
  Between two rivers with no ridge between them, the compiler adds a divide.
- **landforms**:
  - `lake {"at", "radius", "level"?, "depth", "lobes"?: 0..0.5, "dam"?: true}`: a basin carved below its level,
    with a rim that holds the water where the ground is lower. Without `level` it fills to the ground at its centre.
    `lobes: 0` gives a round shore.
  - `fan {"at": "river.mouth", "radius", "height"}`
  - `moraine {"across": "river@0.8", "height", "width"}`
  - `terrace {"along": river, "from", "to", "side": "left" | "right", "height", "width"}` (banks: left and right
    looking downstream)
- **rugged**: ruggedness as geometry (crags, and ledges of benches and risers, in patches).
  `{"name": {"in": zone, "gradient"?: {"from", "to", "range": [a, b]}, "amount": 0..1, "scale"?: m, "ledges"?: m}}`.
  Rock cover then finds the steep bits. Use it for "rocky", "craggy" or "broken ground".
- The compiler adds on its own: **divides** between rivers, **ribs** (short spurs down from ridges), a slight
  **wander** to ridges between summits, and **dissection** (stream erosion). Peaks lose a little height to erosion;
  the report shows authored against built heights. `"ribs": false`, `"divides": false` and `"dissection":
  {"strength": 0}` turn these off.

## Places, routes and walls
- **zones**: named regions, used everywhere below and as addresses. They can be:
  - `"quadrant:ne"`, `"north"`, `"south"`, `"east"`, `"west"`, `"centre"`, `"everywhere"` (these have soft edges)
  - `{"inside": "<closed ridge>", "inset"?: m}`
  - `{"polygon": [[x, y]...]}`, `{"near": address, "radius": m}`
  - `{"above": m}`, `{"below": m}`, `{"slope": [lo, hi]}`
  - `{"all": [...]}`, `{"any": [...]}`, `{"not": zone}`, `"feather": m`
- **sites**: flat pads (village, farmyard, camp, spawn). `{"at": address, "radius": m, "level"?: m,
  "above_water"?: m}`. With a shore address (`"lake.west_shore"`) the pad sits inland of that point, just above the
  water. The report gives its level and how far it cuts into or builds out of the slope (a warning over 25 m).
- **routes**: paths the compiler finds, grades and carves (switchbacks come out of the search).
  `{"from": address, "to": address, "via": [...], "max_grade": 0.12, "width": m, "avoid": [zones], "stay_in": zone}`.
- **walls**: unclimbable edges around a zone where no basin gives you one.
  `{"around": zone, "min_slope": 45, "height": m, "except": [addresses or passes]}`. The ground just outside is
  raised to make them.
- **cover**: masks for the engine, density or weight 0..1 per layer.
  ```
  {"type": forest | conifer | deciduous | rock | scree | grass | meadow | snow | sand | mud,
   "in": zone, "density": 0..1, "slope": [lo, hi], "elevation": [lo, hi],
   "gradient": {"from": address, "to": address, "range": [a, b]},
   "near": {"what": "water" | address, "within": m}, "breakup": {"scale": m, "amount": 0..1},
   "avoid": ["water", "routes", "sites", zone...], "color": "#rrggbb"}
  ```
  Types have sensible defaults (forest avoids steep ground, water, roads and sites; rock favours slopes over
  32 deg), and anything you give overrides them.
- **intent** (checks; nothing is changed):
  - `{"at": address, "above_flood": m}`
  - `{"path": [addresses], "max_grade": g}` (straight legs)
  - `{"from": address, "see": [addresses], "min_visible": m, "skyline": true}`. For a peak or hill: how many metres
    of it rise above everything in front of it (its own flanks count as it), and whether it stands against the
    sky. For a lake: the share of its surface you see.
- `"probe": [addresses]` reports the ground height and slope at each place.
- `"export": {"size": 513}` resamples the export to an engine grid (Unity 257/513/1025/2049; Unreal 505/1009/2017).

**Addresses:**
- a peak/col/landform/site/pass name
- `"river.source"`, `"river.mouth"`
- `"river@0.4"`, `"ridge@0.4"`, `"route@0.5"` (fraction along it)
- `"lake.west_shore"` (also north/south/east/northeast/...)
- `"highest"`, `"highest:<zone>"`
- a zone name or `"quadrant:ne"` (its centre)
- `[x, y]`, or `{"from": address, "offset": [dx, dy]}`

`"views": [{"name": "file_stem", "eye": address | [x, y, z], "lift": m, "look": address, "fov": deg}]` are
perspective renders. The eye stands on the ground at an address; `lift` raises it.

## Running
```
uv run python examples/terrain_run.py <your.json>            # report + map + mask sheet + 3D views (~1-2 min)
uv run python examples/terrain_run.py <your.json> --no3d     # report + map + mask sheet (~20 s)
uv run python examples/terrain_run.py <your.json> --export   # also the engine files (height, masks, meta.json)
```
Outputs go to `workspace/terrain/`:
- `<stem>_map.png`: north-up hillshade with cover colours and contours. It shows rivers (blue), ridges (dashed
  red), routes (orange), sites (purple squares), walls (dark dots on the edge, bright red where climbable), names
  and a cover legend.
- `<stem>_masks.png`: each cover mask alone (white = dense).
- `<view name>.png`: the views, with trees instanced from forest masks.

Read the images, not just the report. The report is in your units and ends with WARNINGS: read them.
