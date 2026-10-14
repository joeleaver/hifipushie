# Terrain: the world, its compression, scale and units

Read guide(topic="terrain") first: describe the brief, then write the spec.

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
