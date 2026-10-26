# Terrain spec guide (experimental)

You describe terrain in JSON, in the terms a level designer uses (a basin, a pass, a wall, a lake, a village site,
a road, forest here and rock there, this must be visible from there). A compiler turns that into a height field
and cover masks. You never paint heights. Where you want a specific landform (a named ridge, a river, a moraine),
you can drop down and write it; otherwise the compiler fills in plausible ground (drainage, spurs, gullies)
between what you placed, and never moves anything you placed. Axes: x east, y north, z up; metres by default.

Run the tools with `call_tool(name, args)`. Sub-topics (guide(topic=...)): `terrain_world` (world kinds,
compression, unknown kinds and the designer's questions, scale and units, tilt, the frame's edge), `terrain_shapes`
(peaks, cols, ridges, basins, passes, canyons, mesas, volcanoes, sea and coast, fords, rivers, landforms, rock,
rugged, volumes and caves, ground), `terrain_places` (zones, sites, routes, lines, walls, cover, intent checks,
addresses, views and sun), `terrain_streams` (stream beds, banks, lake shores), `terrain_styles` (the ground in the
plants' art styles), `terrain_running` (the tools and shell runs, the export: heightmaps, splats, 3D mesh tiles),
`terrain_tools` (every terrain tool's parameters).

**The rule everything else follows: describe the level from the brief before writing a spec.** What kind of land it
is, how big it should feel, what the player must see and reach, and what must be hidden: as items the compiler's
checks can measure. A terrain that compiles cleanly but doesn't do what the brief asks is wrong.

## Stage 0: describe the brief (before any key)

Write down, from the designer's brief and any reference art or maps, each with how you'll check it:
1. **The kind of land** (alpine valley, cirque, canyon, hills, farmland, plateau, crater, coast, dunes, moor, or a
   mix), and the style it should read in (realistic, or one of the plants' styles). An unknown kind is a QUESTION for
   the designer, not a guess.
2. **Size and drama**: the frame in metres, how big it should feel (a stroll, a long trek), how tall the heights are
   against it, the real scale it compresses.
3. **The big shapes** the brief names: peaks, ridges, basins, passes, rivers, lakes, the sea, cliffs, landmarks.
4. **Places and routes**: sites (village, camp, spawn: size, flatness), roads and paths (max grade), crossings, walls
   (where the player can't go).
5. **Sight lines** (the designer's intent): what must be visible from where, what must stand on the skyline, what
   must be hidden. These become `intent` checks.
6. **Cover and ground**: forest, rock, grass, sand, farmland: where and how dense.
7. **What can't be built**: tides, waves, glowing lava, glaciers; caves and overhangs only in the 3D mesh tiles. Say
   so to the designer first.

## The stages

| # | Stage | Keys (sub-topic) | Gate |
|---|---|---|---|
| 1 | World and frame | `world` {kind, compression}, `extent`, `units`, `cell`, `tilt`, `border` (`terrain_world`) | The report's kind, compression and chosen heights match the brief's size and drama; no open QUESTIONS |
| 2 | Big shapes | peaks, ridges, basins, passes, canyons, rivers, sea... (`terrain_shapes`) | The map's landforms are the brief's; realism check passes; WARNINGS read |
| 3 | Places and routes | zones, sites, routes, lines, walls (`terrain_places`) | Sites flat enough, routes within grade, walls where the brief says |
| 4 | Intent | `intent` (see / hide / above_flood / max_grade), `probe` | Every intent check passes |
| 5 | Cover, detail, style | cover, rock, rugged, ground, stream beds, styles (`terrain_places`, `terrain_streams`, `terrain_styles`) | Views read as the brief's land at player scale |
| 6 | Export | `export_terrain` (heightmaps / splats, or 3D mesh tiles) (`terrain_running`) | The seam check passes; the tiles seen as an engine would read as the views did |

Loop: `set_terrain(name, spec=...)` once, then small `set_terrain(name, patch=...)` changes; `check_terrain` for the
report; `look_terrain(name, map=True, masks=True, views=[...])` for the images.

## Craft rules (each once)

- **Ask the designer; don't answer for them.** Questions come back as JSON from any terrain tool (an unknown kind, a
  conflict): put them to the designer and let them answer in their own words.
- Never paint heights: say what the land is and where things are; drop down to a named landform only where the brief
  needs that exact shape.
- Player-scale detail is real metres (erosion, crags, trees, tracks); only the kind's proportions compress.
- Choose a real scale when you can: trees, roads, walls and walking grades are real-world sized.
- Turn every "must be visible / hidden / reachable / dry" in the brief into an `intent` check, and read its result.
- Forms only read in side light: judge views with the auto sun (or your own low side sun), never with the sun behind
  the eye.
- A patch merges objects key by key but replaces lists whole (views, `through`, `via`): send the whole list.
- Read the images, not just the report, and read the report's WARNINGS.

## Self-review loop (every round)

1. The map (north-up hillshade with rivers, ridges, routes, sites, walls) and the views from the places the player
   stands, beside the brief's sketch / reference art at the same framing where there is one.
2. Region by region (the big shapes, each site and route, the skyline from key places, the cover, the edges of the
   frame) list what reads wrong against the brief, concretely. Mark each MAJOR (the wrong kind of land, a landform
   missing or misplaced, a failed intent, an unreachable site, a wall where the player should pass) or MINOR. Order:
   big shapes before places, places before cover and detail.
3. Fix the worst MAJOR with one patch; re-run; re-read the intent checks.
4. Repeat until no MAJOR and every intent passes.

## Common mistakes

| Mistake | Instead |
|---|---|
| Answering the tool's questions for the designer | Ask the designer; put their words in `world.answers` |
| Writing heights everywhere | Leave heights out where the kind decides; the report lists what it chose |
| A peak "showing" that doesn't stand out | `min_prominence` and `skyline` in the intent |
| A site whose middle can't see what its edge can | Intent from a site tries nine eyes: read how many see it |
| Judging forms in flat light | The auto sun, or a low side sun per view |
| Sending part of a list in a patch | Lists are replaced whole |
| Promising tides, lava, glaciers, overhangs in a heightmap | Say what can't be built first; caves and overhangs are 3D mesh tiles only |

## Known gaps (say so to the designer)

- Nothing measures that a place is reachable only by climbing: build it as a wall exception plus a `hide` check, and
  say the climb itself isn't checked.
- A long sea inlet between walls (a fjord) has no recipe yet: it's an unknown kind, so the designer's answers define it.
