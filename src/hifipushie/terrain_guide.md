# Terrain spec guide (experimental)

You describe terrain in JSON at two levels, and a compiler turns it into a height field plus masks:
- **Landform**: a skeleton of named ridges, rivers, peaks and cols, plus landforms (lake, fan, moraine, terrace).
  This sets the big shapes.
- **Design**: zones, walls, sites, routes, cover and intent, in a level designer's terms. These reshape the ground
  where they must (a flat pad, a graded road, an unclimbable edge) and paint masks.

You never paint heights directly. Metres; x east, y north, z up.

## Landform
- **Ridges** are crest lines with heights, and **rivers** are valley floors with heights. Between them the ground rises
  from floor to crest along the river's **valley profile**: "V" (straight sides), "U" (glacial: flat floor, steep upper
  walls), "gorge" (steep near the river) or "open" (gentle). Crests are "arete" (sharp) or "rounded".
- A ridge whose `through` list ends where it starts is **closed**: a ring, such as a crater rim or the walls round a basin.
- Where two rivers have no ridge between them, the compiler adds a **divide** (a rounded crest on the line between
  them, rising at the valleys' side grade). The report lists divides. Write your own ridge where you want a
  specific spur.
- The compiler also adds **ribs** (short spurs down from every ridge) and a slight wander to ridges between
  summits, so walls aren't smooth planes. Peaks and cols stay exactly where you put them. `"ribs": false` or
  `"wander": 0` on a ridge turns these off.
- **Frame edge**: `"border": 150` fixes the whole edge at 150 m. `{"n": 150, "s": "open", ...}` does it per side; an
  open side isn't fixed, so the ground there carries on as it goes. The default is open.
- **Dissection** (stream erosion) then cuts gullies. It lowers peaks a little; the report shows by how much.

## Design
- **Zones** are named regions, used by walls, cover, routes and as addresses. They can be:
  - `"quadrant:ne"` (also nw, se, sw), `"north"`/`"south"`/`"east"`/`"west"` (halves), `"centre"`, `"everywhere"`
  - `{"inside": "<closed ridge>", "inset": 300}` (inside a ring, shrunk by 300 m)
  - `{"polygon": [[x, y], ...]}`, `{"near": address, "radius": m}`
  - `{"above": m}`, `{"below": m}`, `{"slope": [lo_deg, hi_deg]}`
  - `{"all": [...]}`, `{"any": [...]}`, `{"not": zone}`, `"feather": m`, or another zone's name.
- **Walls**: `{"around": zone, "min_slope": 45, "height": 35, "except": [address, ...], "gap": 80}`. Leaving the zone
  means climbing at least min_slope for `height` metres. The ground just outside is raised where it isn't steep
  enough. `except` leaves gaps (a pass). The report gives the share of the edge that holds and where it's climbable.
- **Sites**: `{"at": address, "radius": m, "level"?: m, "above_water"?: m}` is a flat pad (village, camp, spawn).
  With a shore address (`"lake.west_shore"`), the pad sits inland of that point, just above the water. The report
  gives its level and how deep it cuts into the slope.
- **Routes**: `{"from": address, "to": address, "via": [...], "max_grade": 0.12, "width": 5, "avoid": [zones],
  "stay_in": zone}`. The compiler finds a path under the grade limit (switchbacks come out of the search), grades
  it and carves it. The report gives length, switchbacks, the steepest 20 m, cut/fill, and spots where hairpin
  legs crowd each other.
- **Cover** (masks for the engine: density or weight 0..1 per layer). Each layer is
  `{"type": forest|conifer|deciduous|rock|scree|grass|meadow|snow|sand|mud, "in": zone, "density": 0..1,
  "slope": [lo, hi], "elevation": [lo, hi], "gradient": {"from": address, "to": address, "range": [a, b]},
  "near": {"what": "water" | address, "within": m}, "breakup": {"scale": m, "amount": 0..1},
  "avoid": ["water", "routes", "sites", zone...], "color": "#rrggbb"}`.
  Types come with sensible defaults (forest avoids steep ground, water, routes and sites; rock favours slopes over
  32 deg); anything you give overrides them. `gradient` ramps density between two places ("thicker toward the
  north").
- **Intent** (checks only, nothing is changed):
  - `{"at": address, "above_flood": m}`
  - `{"path": [addresses], "max_grade": g}` (straight legs)
  - `{"from": address, "see": [addresses], "min_visible": m, "skyline": true}`: how much of each target shows, and
    whether a peak stands against the sky. For a lake: the share of its surface you can see.
- `"probe": [addresses]` reports the ground height and slope at each place.

## Spec skeleton
```json
{
  "extent": [[0, 0], [4000, 4000]], "cell": 10, "border": 150,
  "peaks": {"name": {"at": [x, y], "h": z}},
  "cols":  {"name": {"at": [x, y], "h": z}},
  "ridges": {"name": {"through": [peak/col | "ridge@0.4" | [x, y, z], ...], "crest": "arete" | "rounded"}},
  "rivers": {"name": {"source": [x, y, z], "through": [[x, y] or [x, y, z], ...],
                      "mouth": [x, y, z] | "into": "river", "hanging": m,
                      "valley": {"profile": "U" | "V" | "gorge" | "open", "floor": width_m}}},
  "landforms": {
    "name": {"type": "lake", "at": address, "radius": m, "level"?: m, "depth": m},
    "name": {"type": "fan", "at": "river.mouth", "radius": m, "height": m},
    "name": {"type": "moraine", "across": "river@0.8", "height": m, "width": m},
    "name": {"type": "terrace", "along": river, "from": 0.6, "to": 0.8, "side": "left" | "right", "height": m, "width": m}
  },
  "zones": {}, "walls": {}, "sites": {}, "routes": {}, "cover": {}, "intent": {}, "probe": [],
  "views": [{"name": "file_stem", "eye": address | [x, y, z], "lift": m, "look": address, "fov": deg}]
}
```
A lake without a `level` fills to the ground height at its centre. It gets a lobed shore, and a rim that holds the
water where the ground is lower. It's placed at one point, and water fills below the level around it; it doesn't
flood a whole enclosed valley.

**Addresses:**
- a peak/col/landform/site name
- `"river.source"`, `"river.mouth"`
- `"river@0.4"`, `"ridge@0.4"`, `"route@0.5"` (fraction along it)
- `"lake.west_shore"` (also north/south/east/northeast/...)
- `"highest"`, `"highest:<zone>"`
- a zone name or `"quadrant:ne"` (its centre)
- `[x, y]`, or `{"from": address, "offset": [dx, dy]}`

**Banks:** left/right looking downstream.

## Running
```
uv run python examples/terrain_run.py <your.json>            # report + map + mask sheet + 3D views (~1-2 min)
uv run python examples/terrain_run.py <your.json> --no3d     # report + map + mask sheet (~20 s)
uv run python examples/terrain_run.py <your.json> --export   # also writes the engine files (height + masks)
```
Outputs go to `workspace/terrain/`:
- `<stem>_map.png`: north-up hillshade with cover colours and 50 m contours. It shows rivers (blue), ridges (dashed
  red), divides (dotted red), routes (orange), sites (purple squares), walls (dark dots on the edge, bright red where
  climbable), names and a cover legend.
- `<stem>_masks.png`: each cover mask on its own (white = dense).
- `<view name>.png`: perspective views, with trees instanced from the forest masks.

Read the images. The report ends with WARNINGS: read them. The drainage "pits" count covers small hollows and is
informational.
