# hifipushie notes: terrain

Moved out of CLAUDE.md on 2026-10-09 so agents don't load every thread's history.

## Terrain (experimental; merged to main 2026-09-26)

Goal (the user's, 2026-09-25): terrain an LLM can author in designer language, not raise/lower/flatten brushes.
Three scales kept apart: the *implied world* (the brief's kind of terrain at real size), the *level footprint*
(compressed: game levels shrink distances), the *player* (exact: 1.8 m, trees, tracks). Design intent is
authoritative; realism fills in between and never moves what the designer placed. Five rounds of blind tests
(fresh agents given only `terrain_guide.md` and a prose brief) drove everything; ledger on the Overboard card
"Terrain: an LLM vocabulary..." (project hifipushie).

Modules (separate from the creature pipeline; heightfield, not SDF):
- `terrain.py`: spec normalisation (units, "30%" values), skeleton (peaks, cols, open/closed ridges with wander,
  rivers), base from three harmonic fields (t, floor, crest) plus automatic divides and ribs, basins (floor ramps by
  relative distance to the drain; walls are real mountainsides: width per stretch from the crest behind, average
  slope, tiered cliff bands, `character`), lone hills as domes, tilt, landforms (lake with ring/downhill/no dam,
  fan, moraine, terrace), lakes filled to their own level, report, map/mask-sheet/Cycles views, export.
- `terrain_world.py`: terrain kinds with real reference ranges, compression (c = frame / real width, heights by
  sqrt c; small kinds and small frames crop), heights chosen when left out, player-scale detail. Unknown kinds raise
  `Questions` for the designer (their answers define the kind, saved to `workspace/terrain/kinds.json`).
- `terrain_design.py`: zones, passes (a notch that ends where it daylights; descents are routes), walls, sites (pads
  with fall/overlooks), routes (least-cost on 32 headings, graded, carved; explain failures), cover masks and tree
  instances, sight lines (from across a site), realism check, intent.
- `terrain_forms.py`: canyons cut into a plateau through horizontal strata, mesas, river water, fords, rim addresses.
- `terrain_erode.py`: fastscapelib (dependency) stream power + diffusion after the design, protected places, heights
  restored at large scale, per-cell hardness (cliffs stand), thermal slumping. Blender has no terrain erosion.
- `blender_terrain.py`: Cycles preview (tree instances, water, ground beyond the frame).
- `terrain_guide.md`: the user-facing vocabulary (what blind agents read). Run: `examples/terrain_run.py <spec>
  [--no3d] [--export]` (exit 3 = questions for the designer).

Lessons worth keeping: a report must measure the *built* ground, never restate the plan (a pass "ramp" sat over a
65 m cliff; strata "ledges" were 40-52 deg); unbounded reaches bite (lake banks, pad banks and pass ramps each once
shaved or buried whole mountains); erosion scaled to the geology cuts trenches across a game level (cap it in
metres); whole walls as steep as "unclimbable" read as curtains (put the steepness in cliff bands); when a result
regresses, bisect by building one spec at each commit and diffing heights.

- `terrain_sea.py`: the sea (below a level, outside a `land` zone or the low ground reaching the frame's edge; it is
  low ground for the base, so a crater ring inside the land becomes a cone) and its coast as a continuous signed
  distance (re-cut from cells, cliffs were a staircase): shore forms per stretch (rocky, beach, cliffs at ~70 deg
  leaning into the water, beaches at a cliff's foot), coves (horseshoe bays with a beach, an apron and a scar at the
  head, optionally opening toward a valley). The sea is a lake named "sea" downstream (shores, sight lines, export).
  Two blind rounds (island, Cornish coast, `workspace/s1_*`, `s2_*`): the big shapes read (a cone with a crater lake
  and wave-cut cliffs); what still looks fake is eye-level character (plaster-smooth scars and cliffs, no stacks,
  ledges or boulders; domes for peaks; lava as a tan bump), and trails fail at cove scars (routes through cliffs).
- Route breaks (`terrain_design._breaks`, `_cut_break`): cliffs over 50 deg are walls to the route search (30 m
  smoothing hid them), except around the stops; where they close a route off, the barrier is the gap between what each
  end reaches at its grade, broken where lowest, thinnest and nearest the way: switchback legs along the cliff (as long
  as its top and foot run on, dry; its own downhill direction, not the line between the two points), benches with rock
  cut between, capped near the step's height; rolled back if it doesn't open the way. Many dead ends on the way there:
  steps along a relaxed path (fragile), fixed short legs (a 1 km trench), the frame's edge as a barrier, pairs far off
  the route. Planner rebuild (2026-09-26): the search runs on the full-resolution grid (every other cell hid one-cell
  cliff bands) over ground smoothed ~6 m with a 1 m bump allowance per step (30 m smoothing hid 45 deg risers: plans
  went where no road could be built), roads are planned at 0.85 of the limit, the grid path is NOT smoothed (every
  smoothing tried moved turns off the checked ground, over lips and down risers), crowded switchback legs (closer
  than their beds plus a 45 deg bank) are blocked and re-planned. Same pass rate on the test set, worst cases far
  smaller (mean as-built/limit 4.9 -> 2.6); roads are longer and jaggier (grid staircase). Next if routes matter
  more: a road planner in (x, y, road height) state so earthworks are part of the plan.
- `terrain_volcano.py` (2026-09-28): `volcanoes`, built into the base after `_hills` (large-scale ground, before
  texture, sea, erosion). Cone profiles (strato concave exponential from avg + top slope, shield convex, cinder
  straight, crater share 0.4 of the footprint); the flank blends local ground to the rim height (an offset from the
  centre's ground raised a cone's uphill rim 43 m on a slope); crater/caldera pit, breach (a small collapse from the
  floor), lake (a lake landform injected into the spec); radial gullies in two generations; collapses (U outline,
  walls from the rim at `walls` so `width` is rim to rim, floor = the flank's own long profile minus a sink easing
  to the mouth; a straight floor stood above a concave flank), debris hummocks; flows traced down the smoothed
  built ground with inertia and a slow random walk, a sheet over it (surface = smoothed ground on the path +
  thickness; the ground wins where higher: a flow fills a gully), levees, bowed pressure ridges, lobed edges,
  deltas at the sea. `settle` after erosion restores designed volcano forms and peak forms within the kind's gully
  depth (erosion had smeared 20 m gullies and taken 20-30 m off rims). Report measures rim (per bearing: first near
  top outward from the floor; a shield's flat top ran on past its caldera), lake + spill side, flank slopes by thirds,
  collapse width across its head, flow thickness over the ground it buried (the old "stands above the ground beside"
  read 60-81 m for an 18 m flow on a cone).
- `terrain_rock.py` (2026-09-28): rock character on every face over ~40 deg after erosion/settle: buttresses and
  couloirs as the ground resampled a horizontal distance along the fall line (profile kept, lip and foot notched;
  strike coordinate from the heavily smoothed gradient, ribs elongated along the fall line with wandering spacing:
  short blobs read as raindrops, even spacing as a comb; a third of the strength on 40-50 deg mountainsides), ledges
  (heights pulled toward a staircase, off designed walls: treads broke their unclimbable run), a boulder foot. Peak
  arêtes, routes, sites, water kept out. Measured: share of face cells turned > 25 deg from the face's line (canyon
  2% -> 37%), cliffs' width in cells (a 70 deg face 2-3 cells across renders as facets: `write_mesh` now resamples
  2x cubic for the render). Sea cliffs get stacks and a wave-cut platform (`terrain_sea`).
- Peak forms (`terrain_forms.peak_forms`, after volcanoes): pyramid/horn = planes through the summit and each pair of
  neighbouring arêtes (continuous across them), arêtes along the ridges that leave the peak at their gentlest fall
  (never cutting the ridge) but at least the form's own slope near the top (following the ridge made a 2 km "horn"),
  fillers up to the face count; faces hollowed next to the arêtes (sin^0.7: sharp crests); carve only the upper part
  (height-weighted), never into other ridges/cols/peaks (a 35 deg guard cone round them: a face cut a col 110 m down),
  fill only hollows the carving made (a basin floor in the zone had been filled whole). Default pyramid in alpine
  kinds. Measured: summit fall, faces, arête crest angle across (knife ~100, rounded 150+).
- Cover masks cut on the slope of the ground smoothed a cell, thresholds (slope and elevation) shifted by noise a few
  cells across (cut on the raw slope, snow and rock speckled cell by cell and every boundary was a pasted line).
  Floors and plateau tops get a gentle swell at player scale in `_texture` (they were flat plaster from the air).
  The rocky shore keeps land dry only a few cells in (`0.2 * min(sd, 3 cells)`; uncapped it lifted ground 400 m
  inland to 80 m: found by another agent's level).
- Views (`blender_terrain`): matte ground (specular 0.12: dark cover read brown at grazing angles), water with a
  noise ripple (bump on ~4 m features: 30 m swells were too gentle and it stayed a mirror), no site pole where a camera
  stands (views from a site rendered inside it, all black). The ground beyond the frame is a ring round it, never
  under it: its inner edge is the frame's own edge (heights and colours), carried on level then eased down to the
  30th-percentile edge height (a plane at the lowest point read as a sea on every alpine horizon; a plane at the edge
  height cut through a canyon). Blender's Python has no scipy.
- Blind rounds 2026-09-28 (`workspace/terrain/b1_volcano`, `b2_alps`, `b2_coast`; testers ran from this worktree while
  the agent developed in a scratch copy of `src/` on PYTHONPATH): the volcano, the horn and the stacks read only after
  the fixes that followed each round (collapse width, flow measure, arête slope near the top, stacks placeable and
  broken). Still open then (most since done, see Terrain2 below): a basin must be a closed ring, lake
  levels vs sites on their shores, village pads always on mounds, rugged barely visible on domes, sea cliffs 2 cells
  wide in plan (soft vertical drapes), horns still near-symmetric, no cairns/markers, lighting fixed from the SW.
- `terrain_sun.py` (2026-09-28, the user's decision): each view's sun. "auto" (default) builds a small image of the
  view (a ray per column, the ground point each pixel lands on; water left out: sea views had been scored on the
  seabed), shades it with each side sun (45-135 deg off the line of sight, 12-40 deg high, cast shadows) and scores
  neighbour-pixel contrast x3 plus overall, docked when >30% is dark or all of it dim. `views[].sun` / spec `"sun"`:
  side, bearing, {"from", "height"}, "morning"... The run notes each view's sun and warns on flat (behind the eye,
  >135 deg) or against-the-light suns. The Sky texture's sun follows (Blender 5.1: `sun_rotation = bearing`; `-bearing`
  put the sun disc in frame on the wrong side). The fixed SW sun had hidden b2_alps' pyramid faces (render 17).
- Terrain2 (2026-09-28, branch worktree-agent-a671e877e8eeb1ea4, renders 17-21):
  - Rock (`terrain_rock`): noise ribs read as melted wax and round pits (main's read of 17). Now: chiselled ribs
    (`_chisel`: piecewise-linear across the face, V couloirs); `facets` (a plane least-squares fitted per jittered
    cell, tipped, creased with its neighbour; weighted by how planar the ground was: a plane over a small cliff and its
    clifftop was a 50 deg ramp through a 70 deg face, the "drape"); pits the faceting closes are filled; buttress shift
    resamples the ground, never cross-fades (the fade bevelled every lip and foot); `bedding` on cliffs >55 deg (steps
    of max(2 m, 6 cells): 3 m beds on a 1 m grid were sub-cell, rms 0.24 m, invisible); scree `aprons` (cones at 33 deg
    below cliffs, in patches, sized to the face). Rugged crags are `facets` of the noise. Report: pits/km2 (> max(0.5 m,
    0.1 cell), rubble left out), roundness (median |laplacian| x cell), apron area. Views: a rock bump on faces >~55 deg
    (Voronoi joints at two sizes + stretched noise beds) in the ground material: sub-cell relief, like an engine's
    cliff material.
  - `terrain_detail.py`: `detail` (auto 2 with sea cliffs or cliffs < 3 cells across, fine side <= 1100). After erosion,
    `refine` resamples EVERY grid-shaped array on T (walks vars, dicts, lists; heights cubic in range, masks/ids nearest,
    NaN arrays nearest) and moves T to the fine grid; `terrain_sea.recut` re-cuts sea cliffs from `sd`/`top` (face
    plane, lip). Rock, checks, lakes, cover, export and views then run fine. ~2x build time.
  - Sea (`terrain_sea`): cliff lines jut and bay (sd moved by noise at ~3x the cliff height, only near cliff coast),
    wandering bevel, talus aprons (in `st_mask`, which recut and rock leave alone), placed `geos` dict, per-stretch
    `cliffs.heights`, shore `"rocks"` (graded bank + boulder strip, zone "rocks"), `cliff_feet()` + address
    `cliff_foot:<address>` (terrain3d's hook for caves/notches) + meta "cliff_feet". The sea beyond the frame uses the
    frame's water material (a glossier plane read as a pale shelf).
  - Basins open to a side: `inside` an open ridge + `opens` (compass or "edge:s"): the polygon is the ridge closed by
    rays out of the frame; walls stop past the nearer end (`mouth`, exempt in the wall check); zone `{"inside": ridge}`
    uses the basin's inside.
  - Rivers (`forms.water`): the level never stands above the banks (min of the ground beside, falling downstream) and
    banks are graded 1:3 within 30 m (not canyons, sites, routes): the river had been a stepped slab in a trench.
  - Lone hills combine by max (a saddle), not sum (+6 m stacking). Erosion's deepest cut is capped at 2x the kind's
    gully (tanh). Pads: level at the 40th percentile (cut in), big pads (r > 40) keep half the ground's lie (`flat`);
    the report says how far above the water beside it a pad ended and warns when its lake settled lower.
  - Blind round t2 (`workspace/terrain/t2_coast`, `t2_alps`, `t2_farm`; renders 24, 25). Fixed: routes on a pad run on
    its surface (`_profile` pins pad points; between two pads the grade is at least what their heights need, past the
    limit if it must: an even FAIL and a warning naming the pads, not a 4 m step at one pad edge); the as-built grade
    is judged on the deck over water and not on pads; ridge dome peaks rounded over `radius` (they were cusps: 41 deg
    "pimples"); the tilt's lift on ridge peaks is said; a land-zone coast with rivers keeps `world.base` away from them
    (the solve between rivers and seabed sank the land 16 m); rugged runs after the water (sea/lake zones work), on dry
    land only, and rock no longer re-facets it (spires); geos are flooded to their head last (platform/talus refilled
    them) and reported; stacks shrink 0.8x outwards; cliff heights judged per stretch; report lines for trench rivers,
    uncovered ground, detail left off, detail's cost; a river over a dammed lake's dam is a 0.15 m spillway.
    `terrain_rock.bed_step/bed_offset/params` are shared with terrain3d's solid rock (same beds, facet sizes, colour);
    views darken rock at the waterline (+0.4..2.2 m, the tiles' wet band).
- Terrain forms (2026-09-29, branch worktree-agent-a13c3e7dac22b5635, renders 26-32, blind round t3_coast/alps/farm):
  - Rock big structure first (`terrain_rock._structure`): buttresses/gullies spaced ~0.9x the local face height
    (`face_height`, octave bands 20-320 m, 17% amplitude, strong/slabby stretches), on a frame smoothed at their own
    scale (the ribs' frame turned round every spur: blades), the shift clamped to the room above/below (past a thin
    crest it pulled the far side up as saw teeth) and smoothed 1.2 cells (chisel knots made 1-cell spires at cliff feet);
    ribs inside are small (0.15 crag / 0.035 face height) and change every 3.5 spacings down the fall line (long thin
    fins read as wax). The faces' shift runs on into the sea (kept, waterline cells stood as spires). Tiers (`_tiers`) on
    non-sea cliffs; sea cliffs get ledges in their own profile (`terrain_sea._cliff_face`, T.sea["run"] = lip->foot, used by
    cliff_feet). `T.rock` ledges/gullies/tone; `terrain_rock.colour(T)` / `base_colour` for 3D rock (terrain3d uses it).
    Aprons are concave cones fed from gullies, ending at their toe (a -inf past it; they had spread 400 ha). write_mesh
    splits quads along the flatter diagonal.
  - Coves: asymmetric (`_headland_sides`: auto = the higher side), a cliffed headland (`head_m` forces cliffs), a low
    point opposite, the bay swung away, and a hollow (`rim`): on a 55 m plateau coves were pits ringed by 60 m walls.
    Report measures the bay/mouth along the axis on the coastline field (stacks and rocks awash were "a 1 m mouth").
  - Basin `walls.from_top` (`terrain._from_top`, `_wall_profile` branch): bands laid by horizontal distance floor edge ->
    ridge line (the harmonic t crowded to the ends: every band at the wrong slope), H over the wall from the floor edge to
    the ridge's own height; zones `<basin>.<band>` re-cut on the built ground by its form (`design._profile_zones`: scree
    down gullies and fans, forest up ribs; ruled stripes otherwise), auto cover per band (`_profile_cover`).
  - `terrain_detail.ground` after refine: undulation in a size spectrum (2.5/1/0.4 x scale), swales from D8 drainage of
    the undulating ground (stretched noise seamed along divides), hummocks in patches on gentle dry ground, hollows > 0.6 m
    refilled; off routes/sites/passes/water/intent sight lines (1 m hummocks blocked pebble_disc's holes).
  - Lakes with `dam: "moraine" | "rock bar"` (`_natural_dam`): across the valley at the lake's downstream end, level from
    the floor when left out, lake side a bank, downstream face 22/58 deg to the floor (ending the profile at lake level
    left a 300 m plateau and a 50 m scarp), a V spillway cut at the lake level; lakes with such a dam may run 8 r up.
  - `terrain_lines.py`: `lines` (hedge/stone wall/fence/bank/ditch/trees; along/follows/around/network). Networks default
    to `_subdivided_fields` (convex splits across the longer axis, sizes by noise: a grid read as a ladder, Voronoi as
    honeycomb). Lines stop at water/pads/crossed routes and slopes > 38 deg; banks/ditches never touch routes/pads (they
    had broken a lane's grade); ditches >= 3 cells; bank/ditch measured per cell against a local ring mean. Views: walls
    with each foot on its side's ground, fences, hedges as one lumpy ribbon (shrub balls read as beads; shrubs stay in
    trees.csv), no tree within 7 m of an eye. Export meta "lines".
  - Blind round t3: layouts land; still fake: rock faces up close (heightfield: smooth fins, no beds at 50 m range), the
    head as a mesa, stacks at a headland fuse like a causeway, hedges uniform dark, ground "lumpy" still subtle at eye
    level, the ground beyond the frame streaks, cliffs/scree bands under peak forms don't hold their asked slopes.
- `terrain_tools.py` + tools in `server.py`: `set_terrain` (spec or merge `patch`; `workspace/terrain/<name>/` with
  history), `check_terrain`, `look_terrain`, `export_terrain`, `terrain_history`; builds cached by spec content;
  questions come back as JSON (`Questions.data`). `guide(topic="terrain")`. `examples/terrain_tool.py` calls the same
  functions from a shell (for sessions whose MCP server predates the tools).
- `terrain_mesh.py` + `terrain_caves.py` + `blender_tiles.py` (3D terrain, 2026-09-28; card "3D terrain: SDF-meshed,
  seamless tiled mesh export"): the design stays heightfield + 3D shapes: `volumes` (arch, cave, overhang) and
  `caves` (skeletons: entrances and chambers joined by passages; kinds sea/karst/lava), all `Tube`s (a polyline with
  an elliptical section per node, rounded ends, a flat floor; rough fbm on walls and roof only). Output is optionally
  glTF mesh tiles (`export_terrain(tiles=True)`, `terrain_run.py --tiles`, cfg `spec.export.tiles`). Field, global and
  pointwise: `(z - h) / sqrt(1 + |grad h|^2)` with h the grid as an UNprefiltered cubic B-spline (C2, no overshoot at
  cliffs), each volume by smooth max/min, then solid rock relief (`rock_relief`: `_pl_facets`, random heights on a
  rotated lattice interpolated linearly over the Freudenthal tetrahedra = planar facets meeting in C0 creases, 2
  octaves; beds with a V notch and a proud or set-back offset each, stepping over in a ramp ~2 voxels wide, on
  terrain_rock's own `bed_step`/`bed_offset`) on ground steeper than 45-62 deg (a smooth grid mask, `Field.steep`)
  and near volumes (capped at 0.2 of a passage's size), never on floors. THE FIELD MUST BE CONTINUOUS: a jump (the
  nearest Voronoi cell's plane alone, a per-bed offset, the slope mask switching within 0.2 m at a cliff lip, a
  volume's box cutting inside its blend/NEAR reach) meshed as steps whose field normals pointed sideways = black
  triangular shards; blending cells smoothly read as mush. Crisp needs creases: MC vertices beside a crease are moved
  onto it (`snap_creases`: the QEM point of the ring's tangent planes, DC-style) and `split_normals` gives a corner
  its own normal only where it faces away (>75 deg; at 30 deg the zigzag creases showed as shaded teeth). Normals at
  1/8 voxel. Sub-voxel creases still zigzag; the seam check counts shards (`_shards`, `SHARD_LIMIT` per LOD). Rock
  colour = the heightfield views' rock (`rock_colours`: terrain_rock.colour when present, else kind + rock cover
  layers), toned per bed/facet, darkened by a field occlusion (F half a metre out along the normal). Facets ~8 m;
  voxel 0.5 m.
  Meshing: marching cubes (lewiner) per tile on the global lattice (voxel divides the tile; z planes offset 0.137
  voxel: flat floors at round heights lay on lattice planes and left non-manifold slivers), z only over the tile's
  own range (cost in area). Lattice values kept >= 1e-3 voxel from 0; border vertices keyed by lattice edge, each
  computed ONCE (crossing, Newton steps in the border plane, field normal, weights) and substituted into both tiles:
  bit-identical. LODs are LOD0 decimated, not re-meshed: each shared plane's chain (`_polylines`) is simplified by
  Douglas-Peucker once per LOD, nested (LOD k keeps a subset of LOD k-1; rows joined along a chain and closer than
  1e-3 voxel are welded into one first, in the chains and every tile's dense mesh, `_weld_rows`: two crossings 7e-7 m
  apart were one float32 vertex in the GLB, a degenerate sliver and a non-manifold edge in pebble's karst passage;
  pebble welds 180), and both tiles collapse the dropped border
  vertices along the border (`_collapse_border`: half-edge collapse, link condition, no flips, never stranding a
  vertex; one that can't go is kept at every LOD by both tiles, and the settle loop reruns). Mixed-LOD gaps are then
  <= the tolerances (0.5 m; re-meshing at 2x/4x voxels gave 2.9 m). Interior: pyfqmr (dependency) with
  `preserve_border`, the fewest triangles within `error` (p99 |F| at face centres/edge midpoints) by a log search,
  capped by `budget`; its fins (twin faces) are dropped, non-manifold or hole-opening candidates rejected, other
  aggressiveness values tried; a LOD that folds at every count is decimated from an earlier LOD's mesh with its border
  collapsed, and if even that can't drop a vertex, every LOD keeps it and all tiles are written again. Interior
  re-projected. Skirts: in the border plane against the normal, as deep as the other LODs' chains stray (+25%),
  clamped to rock thickness; where the rock is too thin for the skirt a gap needs, every LOD keeps that vertex.
  Tiles run in a fork process pool (`_CTX`, up to 16 workers): marching cubes, dense projection, collapses, tiles
  and maps all parallel. LOD k>0 is decimated from LOD k-1's mesh (border collapsed to its chain), the dense mesh
  only if that fails; `_decimate`'s count search halves from the last good mesh (then 0.75, 0.88) instead of a log
  search over the dense mesh: pebble 256 s -> 61 s, LOD0 +6% triangles. `seam_check` reads the GLBs back (per-LOD watertight except the outer
  edge, identical border vertices/edges/normals, every LOD pair's gap under a skirt, heightmap edges) and raises; it
  caught a LOD2 fin, a vertex stranded at a tile corner, sliver non-manifolds at round-height floors and holes from
  dropped fins. Arches go where the land is shortest for their height (within `search` m); notches 5 m deep with the
  floor in the water; `wet_rock` layer and splash band (sea to +2.2 m, higher inside volumes); trees with no solid
  ground under them dropped. Caves: `terrain_caves.check` walks a person through every passage (floor by vertical
  field columns, headroom, width at 3 heights, the body as a capsule tested by SIGN on a ring of points and allowed
  0.8 m sideways: the field is no distance near relief and blends; steps <= 0.6 m; water depth) into the manifest.
  Karst: a wide bedding-plane tube with a flat roof (`Tube(roof=)`) over a slot, smooth walls (no facets) with thin
  beds as ledges (`Tube(beds=)`, `wall_beds`), shaft entrances in dolines (`dig_doline` lowers the Field's own copy
  of H: a grassy bowl, uneven rim; plus a rocky pit tube at the throat; depth limited by the rock over the passage).
  Lava: `"flow": name` runs a tube down a terrain_volcano flow line, floors on the flow's smoothed grade (following
  the surface put 1-3 m steps in), benches, breakdown `Mound`s (cones: tubes/ellipsoids have round ends that made
  steps or domes) under skylights and in collapse pits, standing on the lowest floor under them. Test level
  `examples/lava_field.json`. Chambers take `"in": m` from a directed address (`cliff_foot:<address>`).
  Renders through Blender's glTF importer (`render_tiles`: lod "checker" mixes LODs, `skirt_color` shows skirts,
  `lamp`/`exposure`/`fill` for views inside caves (a second light down the view: a lone headlamp blew out the near
  walls and read as fog), no tree within 7 m of an eye). pebble_disc, 0.5 m voxel, 208 tiles: LOD0 ~370k triangles,
  0 seam failures, shards 0.0005% of LOD0, Khronos 0 errors, ~1 min. Rock parameters agreed with terrain2 (no dip,
  their bed step/offset, a matching wet band in their views); rock colour is now theirs per cell.
  Views: an eye near a pit or skylight must stand within a few metres of it (from 10+ m the ground hides it), and a
  render job's `box` applies to every view in it.
- Cliff overlay + baked maps (2026-09-29, "cliffs" agent; the user: games put 3D cliff faces over the heightmap, and
  the caves read low-poly/sawtooth). export.tiles `mode`: "cliffs" (default) | "full".
  - `terrain_cliffs.py`: `Region` (S = steep > `cliff_slope` 42 deg + the rock character's mask, grown `cliff_margin`,
    and round openings; pointwise, a grid read bilinearly), the ground = heightmap eroded in plan by a ball of radius
    push x S (push = relief + 0.6 m, only `push_open` 0.9 m round openings: pushed deeper round a lava skylight it
    went through the tube's roof and every round of holes pushed it further), holes = heightmap cells standing in a
    void (iterated with the region). `CliffField` = a closed rock shell: front = the full field with its ground part
    sunk by sink x (1 - S), back = `thick` m behind the smooth ground or `cave_wall` m round a void, joined by smax
    (a hard max shaded shards); where sink(1 - S) > thick it pinches out buried: no open edges. Points away from the
    region and voids return +1e3 (air), so each void's box is grown to hold its whole shell (the tube's own box is cut
    ~2 m under its floor: the shell ended in a flat face there with zero normals). The same tile machinery meshes it
    (`_tile_mc` reads `zpad`/`vol_pad`, `empty` skips tiles); faces off the visible front are primitive role
    "buried" (the seam check merges them for structure, shards count the visible ones). Ground tiles:
    heightmap npy/png, holes png, grid GLBs (stride 2^k, vertical skirts), `ground_check` (borders, heightmap never in
    a void, never through a cliff face).
  - `terrain_sharp.py`: extended marching cubes on the exact field (per cell with a normal cone > 20 deg: QEF vertex,
    fan, flip edges onto the crease; patches at tile borders keep their boundary, so chains stay canonical) and
    `crease_error` (sharp edges' distance off the surface, face normals vs the field's). Modest on its own (dense tile:
    crease p95 7.2 -> 6.5 cm, normals p95 17.9 -> 16.1 deg): half the sawtooth was sub-voxel bed ramps, now 2 voxels
    wide in the meshed field, the crisp notch in the maps.
  - `terrain_bake.py`: per tile per LOD its own atlas (faces labelled by the axis they face, smoothed; components;
    split where the projection overlaps and where longer than half the atlas; placed bottom-left on 4-texel blocks by
    FFT correlation; atlas as tall as used), then every texel projected onto the front field + `micro_relief`
    (bake-only facets 1.2/0.45 m, cracks, the bedding notch, laminae; band-limited to the LOD's texel: unfiltered it
    aliased and the two sides of a border disagreed), normal (tangent, +Y up the image, our TANGENT), height,
    AO (field SDF samples along 5 directions), base colour and weights from a 0.4 m normal (the fine normal flipped
    rock/grass per texel), roughness. Gutters are baked by extrapolating the nearest chart triangle. Ground maps use
    planar uv with texel centres on the tile edges (a half-texel inset put the sides a texel apart). The Materials
    bed tone eases between beds (a step aliased). `map_seams` decodes both sides' maps at shared border points
    (limits per LOD `MAP_SEAM`). Tiling layer textures (`layer_textures`: tileable spectra, no Voronoi honeycomb) +
    the manifest's `engine_recipe`; `render_tiles(textured="layered")` builds it in Blender (box-projected height per
    layer x _WEIGHTS attributes modulating the baked colour and bumping the baked normal).
  - Lessons: a close view magnifies texels: sharp features in maps stair-step (the bed notch at 10 px/m), so LOD 0 is
    16 px/m and map features are smooth at the texel; geometry creases below ~2 voxels mesh as sawtooth whatever the
    mesher: put them in the maps.
  - Round 2 (after the user saw seams and the machine OOM'd twice): NEVER filter across an atlas image (a sparse
    texel grid + blur bled each chart into its unrelated neighbours: lines along every chart edge, tile borders
    included): AO is per vertex (identical both sides of a border) interpolated per texel, the 0.4 m normal per texel.
    Tangents MikkTSpace-style (Blender's glTF importer ignores TANGENT; so do most engines). Colour tone from smooth
    noise (the facet lattice made a checker of squares). `map_seams` decodes every channel from both sides of each
    border (world normal, colour, ORM, height, weights) at each LOD and LOD 0 vs the coarsest; `scratch`-style check in
    Blender (its own tangents) agreed (p95 2.7 deg at LOD 0). `terrain_cliffs.floating`: pieces of the cliff meshes
    that never reach the heightmap fail the check (a 3 m fin's top cut off by relief, 14 m over the sea; sealed air
    pockets between the shell and the rock round a cave). Causes fixed: `Field.thin` (a grey opening of H: fins and
    stack tops narrower than twice the relief's reach take 10% of it), `_drop_specks` (closed pieces < 4 m2 off the
    tile border), the shell reaches 2 m past the cave wall. Rock geometry: joint sets (`_joints`: three families of long
    vertical planes, candidate planes ~1.6 m apart each present or not and jittered (many small blocks, a few big),
    patchy bands of strength, 0.22 m grooves (flat faces, rounded floor, 1.5 voxels wide) fading out a few metres
    under the open ground (on deep cave walls and at 0.3 m they made black shards); a first version with regular spacing,
    per-bed stagger and pillowed blocks read as hammered metal from 150 m; the far LODs' maps get half / none of
    them) and facet size following the
    face's structure (`_structure_grain`: concave/gully/top of face = small broken facets, buttresses big planes).
    Wet band edge wanders, roughness varies (`_grain`). Memory: dense meshes streamed through `<out>/_work`, field
    calls chunked; `WORKER_GB` 2.0 measured; the manifest's `memory_gb` (resources.peak_memory) states each export's
    peak: pebble 9.1 GB job / 1.07 GB worker / 0.75 GB parent, lava 7.2 GB, alps 10x10 block ~17 GB. MC lattice
    values are clamped to 3 voxels (a 1e3 "air" pulled a float32 crossing onto a node: "isn't on one lattice edge").
  - Round 3, "seams/squares" (2026-09-30, seams agent, renders q01-): tile and chart borders were already invisible
    (measured in render space, every channel); the squares were patterns, all lattice-locked: (1) `Materials._grid`
    sampled the per-cell colour/cover grids bilinearly: a kink on every cell line, 5 m squares on the alps' rock (now
    a cubic B-spline, no prefilter); (2) `_pl_facets` creases lay on one rotated cubic lattice (a few fixed crease
    directions at a fixed spacing: a quilt of diamonds, mostly in the normal map). Warping the lattice
    (`_pl_walk(vec=True)`) barely helped (periodicity 0.55 -> 0.46); a 3D Delaunay of Poisson-disk seeds has slivers
    (needles 4x the lattice's slope). Now `terrain_facets`: random heights on the 2D Delaunay triangles of hashed
    Poisson-disk seeds (deterministic and local: tiles agree), laid triplanar on the face from `Field.face_dir`
    (normal ~ (fd, 1), weights^4, projections under 3% dropped continuously, blend renormalised), 1.4x up the face;
    `facet()` uses it for rock_relief and the bake's micro relief, the warped lattice only for a volume's share
    (caves: the ground's gradient says nothing there). Periodicity 0.30 max; the heightfield's own facets
    (terrain_rock, `T.rock["facet_delta"]`) are taken back out of Field.H where the solid rock has relief (two facet
    systems made a moire of lozenges). Cost: none measurable once points are triangulated per 64-size piece (one box over a sparse map-wide sample asked for 57M seeds: parent 7 GB); alps 9-tile block 14.4 min, pebble 12.5; (3) every joint
    family cut every face: long diagonal grooves crosshatched into diamonds; a family now fades where its planes run
    along the face (`Field.face_dir`, continuous where the slope vanishes); (4) each tile lowered its own texel
    density to fit texture_max (13.8-16/m side by side on a wall): one density per LOD for the export now, from the
    largest tile's visible area (`_job_dense` returns it, `DENSITY_FILL`), `texel_density_used` in the manifest.
    Checks (`terrain_seams`/`terrain_facets`, in the export's seam check): `facet_periodicity` (autocorrelation peak
    above its radial mean, 4 plane orientations; fails > 0.4), `grid_squares` (colour kinks on cell lines vs between:
    bilinear 2.4-5.9, now 1.1; fails > 1.5), `texel_density` (neighbours within 1.25x); `render_tiles(ids=True)`
    writes an exact id pass (glb, chart, distance) per view and `terrain_seams.measure` gives each border class's
    jump excess (step across vs the steps beside it: creases on chart borders don't count; ~1.0 = invisible);
    `channel=` "base"/"ao" (unlit), "normal", "clay" isolates a channel. `floating` treats pieces running off an
    `only` block as continuing (a wall steep across the whole block never came down inside it).
  - Round 4, the ruled bed (2026-09-30, renders s01_*): the user's "reads like a seam" on the alps wall at 40 m was the
    bedding, uniform along the whole wall: one proud/set-back offset, one 0.3 m V groove (creases +-1.5 m: the second
    edge under the line), one tone per bed, the maps' notch on nearly everywhere, all on a plane whose offset changes
    over ~750 m (isolated by channel: strong in "normal", faint in "base", nothing in "clay"). Now `bed_planes`: per
    plane along the strike a presence (patches ~20 m, off in gullies; absent = the step ramps over metres, no notch,
    tone eased over metres), a sharpness and per bed an offset and tone that vary along the strike (`_bed_noise`: the
    bed index as the lattice's third coordinate); beds wander in height (~0.5 m / 25 m + 0.15 m / 7 m, in the gridded
    offset); the notch's width wanders and breaks more. Presence/sharpness are only evaluated near a plane (field ~+15-35%,
    noisy machine). Open: the joints are still dead-straight vertical grooves 25-50 m long from 150 m (4 rulers);
    bowing their planes (~0.4 m over 40 m) fixed that but pushed pebble's LOD 0 shards 0.004 -> 0.011% (limit 0.01).
    `terrain_seams.straight_lines` (also in `views`): Canny off borders/silhouettes, Hough, longest run per peak; a
    ruler = >= 25 m (distance x pixel angle) or >= 40% of the view, and >= 1.6x the view's median edge gradient.
  - Export speed (2026-09-30, "profiling" agent; the user: "it's taking a very long time to output those rocks").
    `profiling.py`: spans + counters per process (`count` is also credited to the innermost open span, so "field.solid
    pts @ bake/surface" says who asked), `Report.pool_map` / `run_jobs` (jobs that unlock jobs) time every pooled job
    in its worker: wall, busy, utilisation, straggler tail, slowest jobs per stage. The export writes it to the
    manifest (`profile`), `profile.txt`, the log, and per tile LOD (`lods[k].timing_s`). HIFIPUSHIE_CPROFILE=<dir> dumps
    a cProfile per job; py-spy (`uvx py-spy record --subprocesses --format raw`) works on the whole export.
    Measured: the maps bake was 96% of the tile stage's CPU. That was 21M texels (pebble), each ~15 field points
    (Newton 9, the 0.4 m normal 4, weights 1) at ~17 us, and a field point was ~60% terrain_facets and ~27% value
    noise. Changes (identical up to fp rounding; the facet change moves values ~1e-15, which on the alps block
    tips pyfqmr into other, equally valid LODs):
    - Atlases are baked in pieces (`_textured_prep` -> `_job_bake` -> `_job_finish`, BAKE_PIECE texels, texels in
      Morton order) as soon as their tile is meshed. `terrain_bake.texels/bake_texels/assemble` are bake() split up.
    - Facet triangulations are cached per fixed block (GROUP 32).
    - The joint-band and bed-notch noise are evaluated only where a groove/notch exists.
    - One BLAS thread per pool worker (`resources.blas_threads`: forked workers inherited 4 and spun them, cpu 5x
      wall).
    - 25k-point field calls: memory-bound, +34% throughput at 12-16 workers. The machine saturates ~66k texels/s.
    - The PSS sampler reads every 2 s (smaps_rollup every 0.5 s kept a parent thread ~40% busy).
    Pebble 656 -> ~425 s of stages. Alps 3x3 on main after the bedding fix: 938 -> 627 s export. The alps block's
    critical path is now decimation: a LOD whose budget the previous LOD can't reach falls back to the 265k-face
    dense mesh with pyfqmr retries (80-210 s a LOD; Overboard card).
    The per-texel exact bake can't scale much further in numpy: a V3 prototype (height by secant along the low-poly
    normal, normals from neighbouring texels) cut field points 15 -> 7/texel for ~1.9x, but normals moved p90 4 deg.
    A compiled field (numba/C) is the next lever (card). For rock design rounds use `preview_tiles` (one LOD, low
    density, no checks; `examples/terrain_rock_look.py` exports + renders the tiles round a point): ~40 s a tile.
  - Compiled field (2026-09-30, "compiled field" agent; the user: "prototype the compiled field"). `fieldjit.py`: numba
    (dependency) kernels behind the numpy leaves, which keep their signatures and stay the reference
    (HIFIPUSHIE_JIT=0): noise._hash/_value_noise/fbm, Field.column/steep_at/grain_at/face_dir, `_gridded`,
    Materials._grid, Region.s, terrain_facets.facets/pl2d/_seeds, _pl_walk. BIT-IDENTICAL, exports byte-identical:
    each kernel repeats numpy/scipy's operations in their order (map_coordinates' spline weights and 4x4 accumulation
    from ni_splines.c/ni_interpolation.c; find_simplex's lifted walk, directed walk, brute force and start chaining from
    _qhull.pyx). Facets locate through a bucket grid per triangulation and fall back to scipy's walk only within 1e-9
    of an edge (where the walk's choice of triangle shows in the last bit). What can't be matched stays in numpy and is
    passed in: `x ** 4` (SVML pow), matmuls (BLAS FMA). Points must be (n,) float64 / int64 (other int widths wrap
    differently: numpy path). `fieldjit.warm()` runs in the parent before the pool forks (5 s cold, 0.5 s from
    numba's cache in __pycache__). `tests/test_fieldjit.py`: kernels + pebble/lava/alps fields, 0 differing values.
    Measured (shared, loaded laptop): leaves 3-34x per point (value noise 34x, column 8x, facets 3-5x), the bake's
    whole field ~3.5x, the pool 1.2M -> 3.1M points/s at 15 workers; pebble export 466 -> 182 s, alps 3x3 494 ->
    276 s, peak memory unchanged (5-6 GB, workers 0.4-0.6 GB). Not 10x because the composition (rock_relief,
    micro_relief, bed_planes, joints) is still numpy, and facet triangulation misses are cold per worker (a 2.5x
    bigger cache missed as often), ~16 ms each now. Alps was then 95% one decimation straggler: pyfqmr stalls far
    above the budget from a dense mesh and `_decimate` counted down to 16 (~100 runs); it now stops at the stall and
    steps from its last mesh (same meshes, 4-12x fewer runs: alps 3x3 276 -> 130 s, byte-identical;
    HIFIPUSHIE_DECIMATE_DUMP=<dir> saves a dense fallback's inputs to replay).
    terrain_blocks compiled (2026-10-01, "compiled blocks" agent): `_blocks_bed_coord`, `_blocks_offsets` (bed slots,
    bed values, minor joints per bed with the box filters, the maps' sharp window), `_blocks_masters`, `_blocks_ids`,
    per point, bit-identical (test_blocks + the terrain tests with blocks on). Numpy-only pieces come in: each
    super-bed's cuts (`h ** 1.2`, SVML pow) and every bed's joint frames (sin/cos) as tables over the points' K range
    (`_blocks_tables`, cached), the master joints' plan projections (`q[:, :2] @ n2`, BLAS, on numpy's own subset),
    the carve (logaddexp) applied after. Exact shortcuts: a value-noise corner of weight exactly 0 adds +0.0 to a sum
    that is never -0.0, so it's skipped (a bed or family index as a coordinate zeroes half the corners); a window
    wholly under the interval is exactly 0 (not the side above: (t+a)-(t-a) rounds, and numpy's tiny nonzero counts).
    structure() 11.7 -> 1.6-1.9 us/pt (synthetic, every family on); the pebble bake field 6.6 -> 3.6 us/pt.
    Remaining numpy in the composition: rock_relief/micro_relief's glue, bed_planes/_bed_noise (value noise compiled),
    block_colour, fallen_sd (small share).
  - Round 5, jointed and bedded rock (2026-09-30, "rock" agent, renders r01-r12, r*_vs_main; the user: "keep working
    on the rock" after q09/q10/s01 read flat, soft and blotchy: removing the lattice patterns removed structure).
    `terrain_blocks.py`, the medium scale (0.3-10 m), added in rock_relief (spec `rock.blocks` 0..1, default on; off
    brings the old joints, laminae, crack net and full bedding back):
    - beds: super-beds (`super` ~0.5 x facet size, a monotone `_warp` of height: they pinch and swell) each split at 0-5
      random cuts (`_cuts`): often one massive bed, sometimes a thin package. Thin beds (< 0.7 m) sit back as a package,
      thick ones stand out, how much changing along the strike (~9 m); beds undulate (10 and 28 m: one octave left
      ledge shadows ruler-straight for 40 m) and are rough (+-0.15 m over 3 m). Minor joints only inside their bed,
      spaced 1.3 x its thickness, each bed's set turned +-20 deg and dipping 72-90 deg, a third of boundaries absent
      (blocks merge), faces tipped, one or two corners chipped, a few blocks missing or proud. A few master joints
      (`_masters`): en echelon segments 20-50 m up the face, leaning +-15 deg, wavy at two scales, a rounded groove. The
      big beds (bed_planes) step at 0.4 and lose their notch with blocks: they ran whole cliffs as ruled lines.
    - CONTINUITY: every piecewise-constant value is box-filtered in its own coordinate (`_win`: a box of +-ramp softened
      by `SOFT`, so creases are C1 curves over 0.2 m; the filter width carried through the warp's slope). A ramp per
      boundary jumped where two boundaries came closer than the ramp; the box filter averages thin beds/blocks. A
      per-bed/per-block choice must use a per-cell constant (the nominal thickness), never the point's warped one.
      Detail under ~2 voxels in the MESHED field makes shards at tile borders (rough edges over 1 m, razor-edged
      fallen blocks: pebble LOD 0 0.09%): rough at 3 m, fallen blocks rounded >= 0.2 m and smooth-chipped. The
      structure mostly carves (`_carve`: set back `back` 0.3 m, building softly capped at `build` 0.12 m): proud beds
      over a cliff's lip built a slab in the air (a piece floating 27 m over pebble's heightmap: `floating` failed).
      The field's reach takes the blocks' MEASURED range (-0.12..1.44 m, 1.6 used); the cliff overlay's push and shell
      (`rock["relief"]`) keep main's sizes: thickening the shell by the blocks re-cut the shells round pebble's karst
      passage and notch (a face lying in a tile border plane at a corner: "border edges differ"; a non-manifold sliver;
      a 4-triangle piece floating 2 m up). Volumes' walls keep main's facets and bedding (the blocks' changes are
      weighted by 1 - u): the export's border machinery is fragile there and any change of their shells re-rolls it.
    - The maps get the structure filtered over +-max(2 texels, `terrain_bake.SHARP_MIN` 0.25 m) instead of the mesh's
      +-0.5 m (`structure(..., sharp=)`, micro_relief's `f.sharp`; weighted like rock_relief's blocks, so not in caves).
      0.1 m failed the seam check's LOD 0 vs LOD 2 normals (p50 7 deg, limit 6: it compares border points up to 0.6 m
      apart, and crisp 1 m-scale structure varies within that); 0.25 m measured 5.6. The layer/colour normal (0.4 m)
      is taken from the field without the per-LOD fine relief (`weightfield`): with it, weights differed p95 0.26.
    - colour (`block_colour`): bed and block tones easing to neutral 0.25 m from their edges (no step to alias), open
      joints only (8%) and some bed planes as faint lines, master joints dark, stains hanging from each super-bed's top
      (candidates every 3 m, a fifth present, 0.25-0.8 m wide, 2-12 m long), dull lichen on tops, the old tone noise at
      0.35, the field occlusion floor 0.75 (0.55 outlined every slot in black).
    - fallen blocks (`fall_zone`, `fallen_sd`): chipped rounded boxes at the faces' feet on gentler ground, >= 1.8 voxels
      (0.3 m ones meshed a non-manifold sliver at a tile border), smin 0.3 into the ground; the cliff Region covers them.
      Blocks on cave walls weighted (1 - u)^3 (at a cave mouth the face's blocks stepped its roof).
    - What read wrong on the way: every block outlined + right-angle joints + uniform courses = masonry / dry-stone wall
      (r01-r03); long straight master joints = knife cuts; a recess the same along a whole bed = a ruled black line;
      fat stretched-noise stains = ink blots, thin regular ones = a comb; even bed splits = plywood; isolated near-black
      blobs at 40 m (deep slot ends?) still open. Judge 40 m and closer at the export's 16 texels/m, not preview density.
    - Measured (`examples/rock_measure.py`, the alps wall): 1-3 m relief band 0.064 -> ~0.09 m rms; blocks median
      ~2.7 m2, p90 ~21; beds p10/50/90 0.7/2.8/5.5 m; joint traces off the beds' perpendicular p10/50/90 5/17/38 deg (32%
      within 10: not all right angles); drawn cracks 6% of all edges.
    - Tools: `examples/rock_round.py` + `rock_views.json` (fixed views: far pass 6/m on the block, near pass 16/m on one
      tile; `--noblocks` = main's rock for before/after), `examples/rock_measure.py`.
    - COST: numpy terrain_blocks made a field point ~4.6-6.6 us vs ~1 without (alps 3x3 ~940 s, pebble ~900 s). Now
      compiled (`fieldjit.blocks_*`, 2026-10-01, see "Compiled field"): alps 3x3 125 s, pebble 223 s (184 before the
      check), main's were 130 / ~182.
  - Detail by scale (2026-10-01, "detail" agent, renders m01_*/m02_*; the user: full unique tiles would overwhelm a
    game, and 16/m was still mush at 10 m). Geometry >= ~1 m; unique maps are MACRO only (`texel_density` default
    8/4/2, was 16/6/2.5); below ~0.5 m a tiling swatch per rock type (`terrain_swatch.py`, export cfg `detail`, default
    on). Experiment (`examples/detail_round.py` + `detail_sheet.py`, u16/m4/m8/u32 on rock_views): 4/m lost the block
    structure (0.3-1 m: block edges, bed steps, cracks) at 15-40 m; 8/m + detail matched 16/m at 40/150 m and was
    far sharper at 10 m; 32/m bought nothing at 40 m and was still mush at 10 m.
    - Swatch: 4 m at 256/m, every term periodic (terrain_facets seeds hashed on a torus, `_seeds(period=)`; FFT
      spectra band-limited to <= a quarter of the swatch: swatch-sized features repeat visibly): facets 0.45/0.16/0.07
      m, few deep fractures of varied width, spall scars with a conchoidal bowl, pits, clustered mineral grain in albedo
      and roughness, lichen. No laminae (lines at fixed v repeated every 4 m up a wall as ruled stripes). Anti-tiling:
      a second sampling at 1.618x, chosen by a periodic variation mask at uv / 24 m. `tileability` (wrap seam jump
      excess) is an export check (TILE_LIMIT 1.5).
    - Projection: a global strike UV can't exist (round a peak the faces close into a ring: a least-squares strike
      coordinate came out at 0.37 m/m, 2.7x stretch). Instead strike-binned planes: 8 vertical (u = p . d_k) + top, v =
      the bed coordinate (z + bed_offset), the plane from the field normal averaged over 1.5 m (position only: tiles
      and LODs agree). Per vertex `_DETAIL` = (strike x, y, side share, bed v) for a seamless blend of the two nearest
      planes; TEXCOORD_2 = each triangle's nearest plane (stock engine detail maps; seams). Blender's importer mixes
      custom attributes of different widths: keep them all VEC4 and on every primitive.
    - Lines map (RGBA per tile LOD, embedded as texture 3): SIGNED distances to the open bed planes / open joints
      (`structure_lines`, sign by a probe) + strengths faded within ~1 texel, so cracks are cut crisp at any density
      (unsigned distances beaded; the sign flip half-way between planes must be gated, and joints faded near their
      bed's planes or every crack end drew a hook). These lines leave the macro colour (`Materials.lines_in_maps`).
      micro_relief drops its 0.45 m facets when the detail is on (the smallest facet size held most of the bake's
      per-area triangulation misses: 3800 -> 958).
    - GLB: the baked material's extras.hifipushie_detail (texture indices, the swatches by uri in materials/);
      manifest "detail" (files, wrap seams, recipe). `render_tiles(textured="detail")` draws the recipe in Blender.
    - Cost (loaded machine): alps 3x3 bake 1140 -> 595 CPU s, export 187 -> 149 s; pebble bake 2577 -> 954, export
      337 -> 234 s; all checks pass, Khronos 0 errors. Decimation is now the alps block's critical path.
    - Open: no dip in the projection; TEXCOORD_2 seams not judged in a render.
  - Rock by measurement (2026-10-01, "rockmid" agent, renders n01-n03; the user, on m02: 40 m only equal to the unique
    bake, 10 m "faceted plaster"; then "compare away" with CC0 scans "to learn how to generate our own").
    - Scans: asset pack `rock_scans` (optional; Poly Haven rock_face_03 2.7 m, rock_06 1.5 m, cliff_side 1.83 m,
      rock_wall_02 2 m; 2K diff/nor_gl/rough/disp; CC0). `terrain_swatch.scan_swatch(set)` (albedo/rough as mean-1
      multipliers, height scale fitted to the normal map), export cfg `detail_source: "scan:<set>"`.
      `examples/scan_compare.py` renders swatches through the same detail pipeline (one preview export, swatch files
      swapped) + `swatch_stats` per swatch. assets.py sends a User-Agent (Poly Haven answers 403 without).
    - What the scans had (swatch_stats): surface slope 0.08-0.21 rms per octave, flat from 1 m to 1 cm (ours 0.02-0.07),
      median slope 0.2-0.4 (ours 0.08), albedo 0.10-0.23 rms per octave (ours 0.01-0.04: stucco), albedo uncorrelated
      with concavity and +0.2 with proud places. Retuned (`TUNE`): polygonal facets at 0.32/0.09/0.03 m
      (`periodic_cells`: Voronoi planes on a torus, soft-min over the 6 nearest seeds with softness a share of the LOCAL
      spacing (a share of the size speckled the dense patches); blending two nearest jumped at every corner), two
      fracture nets, every facet its own tone, clustered pits (crisp cups; thresholded noise read as cauliflower), veins,
      iron. Now slope 0.08-0.20/octave, albedo 0.05-0.11. Sub-texel lines alias into dashes: fracture/vein half-width
      >= 1.5 texels, faded by depth/darkness, never narrowed to 0.
    - Fade by repetition, not by energy (a fine-band-energy fade blurred 40 m: the 8/m macro can't carry it; mipmaps
      handle aliasing): `repetition_profile` lays the anti-tiled swatch as the shader does, reads the mip level a GPU
      picks, measures contrast and periodicity per footprint in LOCAL windows (a whole-view autocorrelation averaged
      the repeat away across the anti-tiling mask's patches: rock_face_03 read as a grid at 40 m but scored 0.28); the
      detail fades where both show (REPEAT 0.3 / 2%: every scan, 1.5-2.7 m, is 0.37-0.61 from 37 m and shows a grid;
      ours, 4 m, stays 0.16-0.26). Ours fades only past ~400 m; the scans would fade from 26-37 m, so a scan source
      needs a bigger set or stochastic/hex tiling before it ships. Manifest detail.fade, recipe step 6, render_tiles
      sets the pixel angle per view.
    - The id pass's sea plane read as tile 1 (a new colour attribute starts white): every waterline counted as a tile
      border. Pebble's chasm "tile jump excess 2.7-2.9" was that; fixed, there are no tile borders in those views, and
      the arch view's tile excess is 0.99 (was 1.61).
    - Lines: joints drawn by `joint_openness` (a smooth field: fracture corridors running through beds) and only in beds
      >= 1.4-2.4 m (bed-bound joints in thin beds were "pen ticks"); the family drawn at a point is the strongest there,
      not the nearest; the map is measured at the texel's LOW-POLY point (at the projected point every texel of a
      triangle bridging a ledge sat on the bed plane: filled triangles); shader crack half-width never 0 (a 0-6 cm width
      under +-2.5 cm jitter gated it on and off: dashes). Debug: `render_tiles(detail_show="lines")`.
    - Block tones: per block +-4% (13% read as pasted rectangles), per bed 6%, partial fresh spalls; tone bands along
      the beds (6 x 0.9 m) and each ledge's underside darker for ~1 m (`BLOCK_TONE`). Thin packages recess only in
      stretches and bed cracks are open over about a third of a plane in ~8 m pieces (both ran the pebble chasm as
      ruled lines; terrain_blocks + fieldjit, bit-identical).
  - Lines from the rock, swatch albedo, the pebble band (2026-10-01, "rock5" agent, renders p01-p0x).
    - The thorns/sawteeth were not the mesh's zigzag but the lines map's own values (measured on a kept bake,
      HIFIPUSHIE_KEEP_BAKE=1 keeps each atlas's texels in <out>/_bakes; `terrain_bake.bake_lines` re-bakes the lines map
      alone): the signed distance went to the nearest plane of the texel's OWN bed (noise inside a thin package, a plane
      every few cm) and the strength was gated to ~1 texel round the line so the noise stayed dark: the drawn line
      followed that 1-texel band, stepping texel row to texel row (period = the voxel). Joints the same (ids' nearest
      boundary switches half-way). Now `structure_lines`: the distance to the nearest DRAWN bed plane (`_drawn_beds`)
      or joint boundary (`_drawn_joints`), strength 1.5-2.5 texels wide (`LINE_GATE_TX`), faded where it meets the
      next line's sign flip (`guard`), distances across the surface (/ sine to the plane, from the interpolated normal;
      a surface within ~20 deg of the plane fades the line). Moving texels level onto the exact rock first changed
      nothing measurable (dropped). Jitter (structure tensor, fine vs coarse direction, lines-only renders): alps 10 m
      11.3 -> 1.2 deg, 40 m 5.4 -> 1.0 (line ends per 100 px 12 -> 1.4), pebble 15 m 4.2 -> 2.0, 40 m 3.5 -> 2.2.
      Clean, a bed crack read as a ruled ink stroke at 10 m: its opening wanders over ~1.7 m, it closes for a metre or
      two every few metres (4.5 m noise) and breaks where a joint crosses. tests/test_swatch: clean ramps, continuous
      strength.
    - Swatch albedo (TUNE): softened per-facet tones (hard ones that strong read as terrazzo), weathering patches,
      grime round and under fractures, a skew (`exp`: long pale tail, short dark one, as the scans). Per octave 0.05-0.07
      -> 0.13 at 0.25-1 m falling to 0.06-0.09 below 6 cm (scans 0.10-0.12 flat: flat at that level read as speckled
      dirty granite on pebble's dark rock at 15 m, so the energy sits in the larger octaves); percentiles of the
      multiplier = rock_face_03's.
    - Pebble's mid-cliff band: a thin package (super-bed 0's two beds of 0.24-0.32 m, z 2.3-2.9 m) set back along the
      whole chasm. Not in the mesh (clay shows nothing: the mesh's +-0.5 m filter averages it away) but in the MAPS
      (the bake's +-0.25 m filter keeps the slot; the bed above's underside faces straight down: a dark band in the
      normal channel, 0.2 m tall, 8 m long). The package's depth now wanders: flush for a metre or two every few
      metres, lumpy over ~1 m (`_bed_value`, fieldjit bit-identical); the maps' thin-plane notches and the darker tone
      follow it (`terrain_blocks.package_recess`). At 40 m the band is three shorter pieces; at 15 m one stretch that
      really recesses is still a dark slot.
    - The cliff overlay's edge was a TRENCH: the front sank by sink x (1 - S) and the heightmap was pushed by push x S,
      so they crossed where both were metres down (pebble S 0.73, 2.5 m under the true ground): every cliff-top edge
      sagged into a channel with a V crease (the "terraces" along pebble's cliff tops in the 150 m view were this). Now
      the front sinks only where S < SINK_EDGE 0.2 (`terrain_cliffs.sink_share`) and the heightmap is pushed by push x
      S^PUSH_POW 3: they cross ~2 cm down, the cliff mesh covers a little more of the margin. Arch view: overlay step
      0.086 -> 0.011, excess 1.96 -> 1.39 (regression export 1.25); heightmap_through_cliff unchanged (0.50%). Also
      `terrain_seams.classes` leaves out pairs across a depth JUMP (2% of the distance is 3 m at 150 m: the ground in
      front of the arch's cliff mesh counted as an overlay border). A faint line with small dents remains at the
      crossing.
    - Debugging tools used (scratch, worth knowing): render_tiles(channel=base/ao/normal/clay) splits a dark feature
      into colour vs maps vs mesh (the band was normal-only, the trench clay); a pixel's world point from the id pass's
      distance + the view ray; field profiles along the face normal per field (base, bake = CliffField front + micro).
    - Regression (cold, loaded machine: cloth sims and another export holding the heavy slot, 7 workers): pebble export
      271 s (main ~162-176; bake/lines 31 of 500 CPU s in the bake jobs), 0 failures, floating 0, shards LOD 0/1/2
      0.006/0.014/0.31%, Khronos 1040 files 0/0; alps 3x3 105 s (main 84-96), 0 failures, Khronos 72 files 0/0; views:
      0 rulers, chart 0.99-1.04, tile 0.97-1.0, overlay (arch) 1.25.
  - Whole-level look (2026-10-02, "level" agent, renders L01-L04; the user on pebble from 150 m: "WTF?", the point's
    arch "a cave with a cover over it"). Judged against photos of real coast (workspace/level_refs, CC BY-SA, never in
    the repo: Durdle Door, a Cornish sea cave, Cornish cliff tops, Pebble Beach's 7th) through the real export path.
    - The "cover": the point's arch was a 38 m tunnel (7 x 5.5 m) under a 30 m headland, turf to its lip. Arches now
      go through a FIN: where the land along the arch is more than 1.25 x `through` (0.9 x height, >= 4 m), bays are
      cut in from the sea down to its floor on both sides (`cut_neck`, a 2.5D ground edit in Field.H like dolines;
      `neck` m either side), so the tip stands on the arch. Height/span/roof by `_arch_size`: span <= 0.8 x height (8 m
      cap), roof >= max(`roof`, ROOF_SPAN 0.5 x span). The search prefers open sea past both mouths (land standing over
      0.75 of the opening within 60 m; rocks awash don't count). `through_view` (notes/manifest): rays along the opening
      above the water, share that come out clear + what lies beyond each mouth, WARNING < 50%.
    - Roofs: caves lower where the rock over them thins and end where even 1.8 m wouldn't keep max(1.5, 0.5 x span) of
      roof, chambers shrink to fit; notches die out to a nick under a low cliff (the chasm notch had -1.2 m: broke
      through). Cave default 4.5 x 6 (taller than wide: sea caves follow joints); the report flags wider-than-tall.
    - `terrain_ground.py` (colour + layer weight only, pointwise: tiles and LODs agree, tests/test_level_look): a turf
      edge set back ~1.4 m x (0.15-2.6 wandering) from every lip (distance to > 50 deg cells on the tops), shaded just
      under it; rock breaking through within 7 m of lips; no grass in the splash zone (~1.6 m over the sea, beaches stay
      sand); green on ledges below the top; patches at 60 / 15 m, drier on crests and sun-facing slopes, lusher in
      hollows, salt-burnt within ~30 m of the sea (toned down after L01 read straw-yellow: hue 61 vs the photo's 86);
      cover kinds mown (8 m straight mower stripes along each piece's principal axis from its centre: a frame turning
      with the zone put metres of phase into every degree; a darker first cut), rough (tussocks, straw tips), scrub
      (dark grey-green clumps; unkept grass turns to scrub past ~20 deg), sand (wet swash, a wrack line at the high
      water mark, grit), `bunker` covers dug 0.6 m into Field.H with a cut edge and a turf lip. The display grid is
      softened ~1 cell and sampled at a 0.6 m domain warp (cover edges were the grid's staircase: stickers).
      `"ground_character": false` turns it all off.
    - Eye level: the ground maps are 4 texels/m: plaster at 1.7 m. A tiling turf swatch (`grass_swatch`: blades
      splatted on the torus, clumps, dry blades; 2 m, 256/m) laid from above on grass/scrub weights, fading 20-70 m
      (manifest `ground_detail` + recipe; `blender_tiles._grass`). Ground clutter (`terrain_ground.clutter`, from the
      same masks): bushes on scrub clumps, boulders in the splash zone and near lips (clutter.csv for engines), tussocks
      in rough near the eye (renders only); placeholders in `blender_terrain._clutter_proto`.
    - Sea stacks as solid prisms (`Stack`, op add over the heightfield's stack: lobed, ~84 deg sides, a tilted notched
      top, 0.35 m bevel): on 1 m cells the heightfield's 76 deg stacks were rounded loaves. Trees out of the splash zone
      and off faces over 45 deg (a cypress stood on the wave-cut platform).
    - Tile views (`render_tiles`, `look_terrain(tiles=True)`): the sun is terrain_sun's per view ("auto" default; the
      fixed SW sun front-lit the 150 m view flat), the sky's sun_rotation = bearing (it was -bearing), aerial haze (a
      mix toward the horizon's colour by 1 - exp(-d / haze), d = the camera ray's length; the colour is MEASURED per
      view by a 16 px render of the sky alone: a Sky Texture inside a material lost its Vector input in the importer's
      scene and fell back to object coordinates, a pale gradient on every tile, L01's "quilt"), the sites' props as
      stand-ins (baskets, tee pads, the lodge: `blender_terrain.props`), trees, clutter.
    - Arch placement also rewards height (6 m / height) and daylight (3 per blocked mouth): pebble's arch went from a
      3.9 x 4.9 m hole on a spur to 5.7 x 7.1 m through a 6 m fin (bays cut from 30 m of land), 83% see-through.
    - Clutter shapes: tussocks are blades turned about their ROOT (about their middle they crossed into teepees);
      boulders only where the maps make rock (the shore rule alone put them on beach sand); bushes on 5 m clump noise.
    - Measured (renders vs the Pebble 7th photo): grass hue 61 deg / sat 0.24 at 150 m in L01 (photo rough 86 / 0.46,
      fairway 91-97 / 0.36-0.43); inside the arch's opening 0.28 of the lit rock's luminance. Open: the fairway still
      pale at eye level, bushes perch on cliff tops, the turf lip is colour only (no geometric step), stacks bulky.
  - Eye-level ground (2026-10-02, "eyelevel" agent, renders E04-E0x; the user, after L04: the fairway one pale minty
    green, the beach smooth, boulders low-poly, the turf lip colour only, bushes perched on lips, stacks bulky, the arch
    smooth). Judged against the Pebble 7th photo by measure (HSV of ground pixels by kind from the id pass's world
    points; texture = luminance std / mean in 7 px windows at the photo's 640 px scale).
    - Ground edits finer than the grid (`terrain_ground.Edits`, built in Field.__init__, applied in `Field.column`, so
      the heightmap, the cliff overlay, collision and both bakes agree): the turf's STEP at its ragged edge back from
      every lip (`LIP` turf 0.7 m, riser +-0.35 m in the mesh; the maps bake it crisper, +-max(0.12, 2.5 texels):
      `bf.edit_riser`, `Region.height(riser=)` for the ground maps), and bunkers cut crisp (a signed distance per trap
      at 0.25 m, `signed_distance`; they were H edits at 2 m cells: soft dishes). `zone` (cells) gates the cost. Two
      traps found by the checks: the Region took the bunkers' faces as cliffs (square 4 m pits round every bunker:
      Region reads the slope from `_column`, the grid's own ground), and recomputing the column's slope factor from
      the edits moved every cliff face below a lip ((z - h) s metres under the top: floating pieces, shards, map seams
      lod1 p95 16 deg). The field is just steeper than 1 across a riser now. No overhang: 0.2 m under 0.5 m voxels
      would be shards; the undercut is the colour's `under` and the maps' crisper riser.
    - Mown grass is its own layer `turf` (LAYER_OF mown/lawn/fairway/green), with its own swatch; covers are painted
      per point with the layers' own weights (`Materials._paint`, the bare ground's grid under them, roads over),
      mown pieces cut along the mower's line (a 1 m signed distance, edge +-0.3 m: +-0.12 put the earth layer's weight
      over the LOD 0/2 seam limit), a first cut (`CUT` 2.2 m, kind "cut") taken out of the rough, stripes 7 m with a
      normal-map lean along the mower's way (`STRIPE` tilt 0.25 rad, tone +-16%, edges softened to 2.5 texels) and
      mottling at 3 / 0.8 m. Maps-only relief (`Ground.relief` -> `Materials.relief`, tilted into the baked normals in
      `bake_texels(texel=)`): tussock clumps 1.2 m, clumps 2.6 m, scrub lumps; each octave fades where it's under 3-5
      texels, and cliff tiles count their texel 2.5x (`RELIEF_CHART`: their charts' texel grids differ across a
      border). Swatches per kind (`SWATCHES`: turf short and dense, long grass clumpy with straw, sand ripples / grit /
      pebbles via `sand_swatch`), manifest `ground_detail.swatches`, each with its fade (turf 30-110 m).
    - Colours: the defaults and pebble's were too pale for the renderer (albedo v 0.48 rendered 0.58-0.72 under the
      hazy sky). mown [0.20, 0.40, 0.13], rough [0.30, 0.43, 0.17]; less straw/salt on rough; sand darker. Most of
      the "pale minty" was the light: `render_tiles(light="clear")` / `look_terrain(light="clear")` (LIGHTS: Nishita
      dust 0.02, sun 3.2 W, sky 0.08, exposure -0.35) put the fairway at h 98 s 0.39 v 0.46 vs the photo's 98-100 /
      0.36-0.39 / 0.38-0.54. `grade=` sets an AgX look ("Punchy" changed almost nothing).
    - Clutter (`terrain_ground.clutter`, rows [x, y, z, kind, scale, yaw, squash]; clutter.csv gains `squash`): bushes
      never within `CLUTTER_LIP.keep` 1.8 m of the turf's edge and squashed/broader out to 7 m (wind-shorn), only
      where the maps paint grass; tall grass (`tallgrass`, 0.3 m grid within 28 m of each eye, thinning out); boulders
      in clusters, only on rock (weight > 0.55-0.8), sunk 0.12 x scale; trees kept `TREE_LIP` 4 m (cypress 1.5) in
      from the turf's edge (the export drops them, noted). Render protos (`blender_terrain._clutter_variant`, 4
      variants each, picked per instance, scale/yaw/squash from point attributes): blade tufts (curved strips, green
      root to straw tips on a few), sage bushes (lumps with a leafy Voronoi bump), boulders faceted by noise, wet and
      darker near the sea. No bush or boulder within 2.5 m of an eye.
    - Stacks (`Stack`): the heightfield's stack is a slim core (`terrain_sea.STACK_CORE` 0.45) and the solid stack
      replaces it (`clip`: the ground cleared in a cylinder over the plinth; crossing surfaces in its notch made
      shards): lobes changing up the stack (`twist` 6 m), beds standing out / sitting back +-0.2 r handing over in 1 m,
      a waterline notch, 10 deg lean, a broken top. Thin fins and stacks take little relief (`Field.thin`), so their
      beds show in colour instead (`THIN_TONE`): the arch's fin still reads smooth in geometry.
    - Regression numbers and open items: see the Overboard card "Whole-level look".
  - Thin rock, lips, routes, sea and sky (2026-10-02, "terrain7" agent, renders T0x in workspace/terrain3d_renders).
    - Thin rock keeps its relief: `Field.thin` (grey opening) no longer cuts the relief's weight (`Field.relief_w`;
      `Field.steep` keeps the cut for the cliff Region, fallen blocks and the facet-delta removal). `_local_thickness`:
      per thin piece (labelled, padded 2 r_open), per ~1 m height level, the Hildebrand-Ruegsegger local thickness of
      {H > z} (largest disc covering the cell, via an EDT per radius: disc dilations cost R^2 per cell), 2 cells into
      the air, smoothed; `Field.thin_at(p)` -> (half-thickness, t), trilinear. The relief is soft-clamped there
      (`thin_cap`: THIN_RELIEF 0.35 x hw x tanh(R / that)), so it can't carve through or cut a top off. Near caves and
      notches (THIN_VOID 8 m, not arches) the old rule stays: full relief over a sea-cave mouth cut a roof piece free
      4 m up (`floating` caught it), and capping by the slab between face and void instead folded cave walls into
      shards. Thin rock also gets `strata` (interbedded 1-3 m beds, about half soft and set back up to 1 m, eased over
      +-0.5 m, wandering along the strike) in geometry AND colour (Materials: soft darker/warmer, hard paler,
      THIN_STRATA tone). Honest read: relief on pebble is ~0.5 m rms whatever the rule, invisible at 30-60 m; the fin
      reads layered only through the colour bands. Durdle Door's crisp many-bedded look is still far: accepted (the
      main session) as a limit of the 0.5 m voxel; thin rock would need finer voxels (beds < 2 voxels mesh as shards).
    - The pale flat triangles at lips were the cliff mesh's "buried" split: a face whose CENTRE was > 0.3 m off the
      visible front went to the plain matte (COLOR_0) primitive, and big faces across the turf step have their centre
      off it with every corner on it. Now buried = centre off and not all corners on the front (requiring every corner
      off promoted the back's edge faces round caves into the visible prim: shards and map seams).
    - Routes are worn ground only off mown turf (`Materials._route`, gated by the mown + first-cut kinds).
    - `light="clear"`: `sky_sat`/`sky_value` (Hue/Saturation on camera and glossy rays only: the light the sky casts
      is unchanged), `sky_horizon_tint` (Nishita's low sky is near white; multiplied toward blue up to ~20 deg),
      `water` / `water_roughness` (a deep blue body, IOR 1.33), `haze_scale` 3. Hole 7 at noon (`skysea.py`-style, from
      the id pass): sky top s 0.45 (photo 0.44), low sky s 0.02 -> 0.15 (0.33), far sea s 0.12 -> 0.25 (0.49), near sea
      0.44; AgX's highlight desaturation limits the rest.
    - The fairway's soft blotches under a high sun (hole 7 at noon) were the baked ROUGHNESS: `terrain_bake` multiplied
      every layer's roughness by a ~1 m fbm grain (0.85-1.2: turf 0.77-1.0), and a high sun shows that as sheen
      patches. Full grain on rock/wet rock only, +-3% elsewhere. Found by channel: base colour and clay were clean, the
      turf detail off changed nothing (`render_tiles` channel views had been ignored under the detail recipe: fixed;
      `grass=False` leaves the turf detail out). The turf detail's two samplings are chosen by an 8 m mask now, not
      averaged (recipe text updated).
    - The pale band at the horizon: the sea was an 8 km plane under an 8 km camera clip; now 200 km / 250 km.
    - Regression (cold, loaded machine): pebble 363 s, 0 failures, floating 0, shards LOD 0/1/2 0.0066/0.026/0.30%,
      Khronos 1040 files 0/0; alps 3x3 165 s, 0 failures, Khronos 72 files 0/0; test_fieldjit (bit-identical),
      test_swatch, test_level_look (+ thin rock, routes), test_tooling pass. Margin: pebble's cliff-map `lod1` normal
      p95 is 14.2 deg against a 15 limit (main 12.6; grading mown ground smooth took it to 14.95: dropped). The points
      over 15 deg sit twice as often near the turf's edge (26% vs 13% of border points) and not on thin rock: likely the
      faces across the turf step now baked as visible. Watch it.
    - Bushes: `blender_terrain._scrub` (stems forking from a crown, ~600 small leaf clusters over a lumpy shell with
      gaps); lumps read as stones, big clusters as crumpled paper. Tussocks 20-70 m out are more and bigger
      (`terrain_ground.CLUTTER_MID`).
  - Incremental export, build cache, decimation tail (2026-10-01, "incremental" agent; the user: exports take long).
    - `terrain_incremental.py`: an edit re-exports only the tiles it can reach; the rest of the export dir is left
      untouched. INVARIANT: an incremental export equals a cold one byte for byte (manifest timing/profile aside); test
      with a cold export of the same spec and a file-by-file compare. Nothing is decided from the spec: `Fingerprint`
      walks what the workers read (the export's field, base Field, Materials + T.cover, Region, DetailProjection, swatch
      entry, cfg, code digest); arrays on a known grid (T's cells [iy, ix], the region lattice [ix, iy], `_gridded`
      splines via `f.frame`) are cropped per tile to its box + MARGIN 24 m (+3 cells), volumes count where their reach
      box (incl. the cliff shell's void box) meets it, everything else is GLOBAL (a change: cold, the log names the
      member, e.g. a site edit changes `materials.rock_ref` and every tile's grain: erosion and global percentiles make
      heightfield edits global). An object type the walk can't hash turns incremental off. Later stages chain keys:
      dense (field key + its canonical border rows' CP/CN and their order: welds keep the lowest row), each border
      collapse (dense key + which rows the LOD keeps; failures stored as positions in the tile's rows), each tile's LODs
      (dense + keep masks, skirt depth/dir, CN/CW/CC at its rows as `pos` finds them, density). The parent's global
      steps (border vertices, chains, keep sets, skirts, density) always run in full, as cold: a neighbour whose shared
      chain moved gets a new key by itself. A reused stage's work files are made again only if a later stage needs them
      (`_job_dense_full`, `_job_prep_tile`). State: <out>/_incremental/state.pkl (deleted at the start, written before the
      checks); `export.tiles incremental: false` or HIFIPUSHIE_TILES_COLD=1 force cold. Files nothing names any more are
      removed at the end (top-level GLBs, maps/, heightmaps/, splats/).
    - Bugs it found (cold exports were not functions of their inputs): bake pieces were sized by the pool's worker
      count, which follows free memory (a few texels' facet lookups moved: exports differed run to run; now n/16);
      `terrain_bake._bary` clipped a sliver triangle's gutter weights without renormalising, so gutter texels were
      baked at a fraction of their position, hundreds of metres away (pebble tile 10,3 read the arch at x 220; now the
      triangle's nearest point); map_seams iterated a set of channel names (key order in seam_check.json by hash seed).
    - Checks: `map_seams` decodes each tile LOD's maps once for all its borders across a fork pool (was once per
      border, serial: 80% of the checks), `floating`'s clearances per tile; both kept in `inc.Memo`
      (<out>/_incremental/checks.pkl) by their files' bytes. Swatch kept by seed + code (`_swatch`).
    - `terrain_cache.py`: built terrains pickled (zlib 1) in ~/.cache/hifipushie/terrain (HIFIPUSHIE_TERRAIN_CACHE,
      cap HIFIPUSHIE_TERRAIN_CACHE_GB 1.5, LRU), keyed by the spec minus THREE_D (caves, volumes, export, views: the
      build never sees them, cached or not, so a cave edit reuses the build), kinds.json and `codehash.digest("terrain")`
      (`codehash.py`: sources of the package modules a root imports, statically, incl. lazy imports; package *.json;
      numeric library versions). terrain.load and terrain_tools.build go through it. alps 128 MB pickled, 39 MB stored.
    - Decimation tail: a coarse LOD's dense-mesh fallback (a failed border collapse on the previous LOD's mesh, or a
      budget it can't reach) reaches PRE 32 x its budget in one pyfqmr pass first, then the same budget search with the
      dense mesh's tolerance (`_decimate(pre=)`). Replayed (HIFIPUSHIE_DECIMATE_DUMP) on the alps block's 12 fallbacks:
      85 -> 37 s, faces <= before in every case, summed error p99 6.2 -> 5.7 m; 4x/8x were faster but further off.
  - First consumer export (2026-10-07, "tiles" agent, branch worktree-agent-aa0a9fde6c2eee6d8; pushieworld's slice_a,
    512 m of sheer coast with a sea cave: /home/joe/dev/pushieworld/docs/hifipushie-notes.md 19-30; our copy is terrain
    `tl_slice_a`; scratch DURABLE in /mnt/data/hifipushie/tiles: run.sh <script> (this worktree's code on the main
    workspace), exp.py <terrain | spec.json> <tag> ['<cfg json>'] (export into out/<tag>, summary + heaviest tiles),
    diag1.py <terrain> i j (one tile's marching cubes: triangles by depth, visible / buried, open edges; 60 s, no
    heavy slot), diag2.py (the dense mesh's own error), dec.py (pyfqmr at several counts), shards.py <tag> <lod>
    (where shard faces are), recheck.py <tag> (the seam check alone on an export), queue.sh (slice, pebble, alps one
    after another), tests.sh, val.mjs <dir> (Khronos over a directory), man.py <manifest> (heaviest tiles)).
    The failure: tile (4,1) at 495,898 / 495,622 / 495,475 triangles against 12000 / 3000 / 800 (three more tiles
    at 100-313k), 748 s for that tile, 44 open edges at z -94.9, a traceback instead of a report.
    - ROOT CAUSE (not the cave): the cliff shell's back was `thick` behind the COLUMN's own plane, (z - h) x cos(slope)
      > -thick. On an even slope that is a shell `thick` thick; under a sheer face's columns (84 deg sea cliffs on
      0.64 m cells: cos 0.04-0.1) it is thick / cos = 50-100 m straight down: a buried sheet thinner than a voxel under
      every cliff, and behind the face a slab only as thick as the face is wide in plan. `_tile_mc` sized the lattice as
      ground - zpad / max(cos, 0.15) (88 m), which cut the sheet open (the open edges). Tile (4,1)'s marching cubes:
      439k triangles, 262k of them more than 10 m under their column's ground, none of those visible. pyfqmr folds a
      sub-voxel two-sided sheet into fins at any count, `valid` rejects every candidate, `_decimate` hands back the
      dense mesh after 5 aggressiveness retries per count on 500k faces (the 200 s a LOD). Capping the sheet's depth
      alone was not enough (238k triangles, and pyfqmr still non-manifold above ~1,300): the slab behind the face had
      to go too.
    - FIX: `Region.back` = the ground eroded by a ball of radius `thick` (ndimage.grey_erosion with a spherical
      structure, smoothed 0.7 cell; a terrain-frame grid, so the incremental fingerprint windows it), read like the
      ground (`back_at` -> height, slope factor); the shell is {front < 0} and {z above the back}. Identical on an
      even slope. `CliffField.zlow` (the lattice's bottom) is that back - 1 m. (4,1): 233k marching-cubes triangles,
      zmin -7.8, LODs 11,996 / 2,989 / 633, 12.5 s.
    - `_decimate`'s error on a cliff shell is measured on faces with every corner on the visible rock, by
      `field.front` (the buried back's field values are not metres: the dense mesh's own p99 was 0.59 "m", and that
      was the tolerance: once decimation worked, LOD 0 of the cave tile came out at 1,132 triangles).
    - Budgets fail loudly: `budget_check` -> manifest `budget_check.over` (tile, lod, triangles, budget, why), an
      "OVER BUDGET" log line and a check failure per tile LOD over `OVER_BUDGET` 2 x its budget. Collision:
      `collision_budget` (default 2 x its LOD's budget): `_collision_mesh` decimates for collision alone when the LOD
      is heavier; tiles[].collision_triangles. tiles[].seconds; the summary lists the slowest tiles over 60 s.
    - Failed checks are a report: `TilesCheckFailed(RuntimeError)` carries the result; `summary(result)` leads with
      "CHECKS FAILED (n). The export is COMPLETE on disk ..." and each failure with its tiles (shards: most-affected
      tiles; map seams: the worst borders and the limit); `export_terrain` and terrain_run.py return / print that.
      manifest seam_check.failed repeats the list.
    - Tried and taken back: border vertices on a crease taking a normal from a 1-voxel stencil (72 of slice_a's 77
      LOD 0 shard faces have a border vertex: border normals are never split, and one side's exact normal at a sheer
      lip is square to the other side's faces). It made shards WORSE (slice_a LOD 0 0.012 -> 0.043%, pebble 0.005 ->
      0.05%) and the lod1 map seams too. The idea may be right, the wide stencil is not.
    - Small ones: heightmap .npy in C order (`.T` had saved fortran_order True: a plain reader got the tile
      transposed); the buried primitive's material is `terrain_buried` (Godot drops extras and saw a second skirt);
      guide + manifest: holes PNGs are heightmaps/holes_<i>_<j>.png and only for tiles with holes, texel_density
      default [8, 4, 2], primitive roles / materials, the two collision files. Report: a spec with `caves` /
      `volumes` says "3D rock: ... built in the mesh tiles only" instead of CAN'T BUILD YET; a cover LIST is named
      by type (meadow, conifer; was cover_1..6: file names of exported masks change with it); the "no coast" error
      gives the sea level and each edge's lowest ground; a route to a cove says to route to a site at it; a hollow
      behind sea cliffs says the raised cliff tops dam it (slice_a: top 18.8 m where the tilt alone gives 3.3).
    - tests/test_tiles.py (a 128 m synthetic sheer coast, "cell" 0.64, 32 m tiles; ~60 s, no heavy slot): shell
      depth and closed, budget holds from the dense mesh, budget_check, a failing export comes back as a report with
      its files on disk, C-order heightmap.
    - Results (cold, loaded machine). slice_a: 161-230 s wall (was 1050), every tile within budget (LOD 0 per tile
      2,514-12,000, LOD 1 561-3,000, LOD 2 147-800; the cave tile 11,996 / 2,989 / 633), 0 open edges, 0 floating, 3.9
      GB. It still FAILS three checks, now as a report, none of them the curtain: LOD 0 shards 0.012% (limit 0.01;
      77 faces, 72 with a border vertex, most in tiles 7,1 / 4,1), cliff-map normals across borders at LOD 1 p95
      17.1 deg (limit 15; worst borders 2,3|3,3 37, 5,0|5,1 29), LOD 0 vs LOD 2 weights1 p95 0.284 (limit 0.25).
      Pebble (examples/pebble_disc.json, 208 tiles): 245 s, shards 0.005 / 0.023 / 0.198%, floating 0, Khronos 1044
      files 0 / 0, but the LOD 1 map-normal seam is p95 15.55 against the limit of 15 (main: 14.2, already noted as
      thin margin): it FAILS by that. Alps 3x3: 133 s, 0 failures, shards 0 / 0.003 / 0.004%, Khronos 72 files 0 / 0.
      test_fieldjit, test_level_look, test_swatch, test_tooling, test_tiles pass.
    - OPEN, in order: (1) the LOD 1 map-normal seam (pebble 15.55, slice_a 17.1): find what the worst borders have in
      common (recheck.py prints them; a few borders at 30-60 deg carry the p95: likely a cliff piece's edge texels at
      4 texels/m, or the two tiles' charts across a crease), fix or re-set the limit with main; (2) shards at border
      vertices on sheer lips (a per-face split that both tiles make alike, or a crease-aware border normal that is
      not a wide stencil); (3) weights1 across LOD 0 / LOD 2 on slice_a; (4) the Khronos validator needs an
      externalResourceFunction for the detail swatches' uris (val.mjs has it; without, IO_ERROR per image);
      (5) a time estimate before the export (tiles x cliff area) was asked by the consumer, not built.

  - The island (2026-10-07, "tiles2" agent, branch `worktree-agent-a84a66da1629ad251`; consumer notes 79-84: the first
    2048 m island export, 1024 tiles, 10 failed checks + faults seen in Godot; our copies are terrains `tl2_island`,
    `tl2_slice_a`; scratch DURABLE in /mnt/data/hifipushie/tiles2: run.sh <script> (this worktree's code, main
    workspace), exp.py <terrain> <tag> '<cfg>' (export into out/<tag>; give `"heavy_gb": 8` for a 3x3 block or the
    memory queue waits for 16 GB), cave1/2/3.py (early cave walk, report lines, a passage's profile), pair.py /
    near.py / cedges.py (a border's unmatched vertices / edges between two tiles), sub.py (the seam check on a
    read-only subset of an export, symlinked into out/), float1-5.py (cliff pieces near a point; field columns; volumes
    at a point; ASCII section of base vs shell; free solid components in a box), col.py (base / shell / front on a
    column), white.py (faces by primitive in a box), exposed.py (exposed_buried on any export), probe_ex.py (each
    exposed buried face with the fields at it), vdist.py (a tile LOD's vertices off the surface), dec1.py / dec2.py (one
    tile's dense mesh cached, then `_decimate` / pyfqmr counts with error, validity, non-manifold spots), rend.py
    (Kaze from pushieworld's camera spots, buried backs magenta), rend2.py (any one view), kq.sh (Kaze block with the
    solid-stack shell off / on)).
    - CAVES WALKED IN THE REPORT (`terrain_caves.early`, from `Terrain.report`): the export's own `check` walk through
      `light_field` (Field(T, volumes + cave tubes, rock=None): the height field with the caves cut out, no rock
      relief; 7-8 s on the island, the export's verdicts on all four passages; the test compares with the full field),
      plus `survey` per passage (rise over its sloping run, steepest 10 m, rock over the roof away from the mouths) and
      each chamber's dome cover, WARNINGs with the fix in spec terms (the chamber's `z` / `depth` that makes the climb
      `GRADE_WALK` 25%, how long the passage would have to be, a lava flow's walkable `from` / `to` stretch or "no
      stretch"). Island: kaze geo_door -> hall 33% (put hall at z ~37), its passage breaks out under a valley;
      crown_tube's flow falls 60%. slice_a: the smugglers' hall ("in": 30 past the knoll) breaks out to the sky by 6.5 m.
      Lava tubes follow their flow (the line's s is a fraction: one via point before). Cached terrains re-register
      mixture kinds (KeyError 'crater+coast' on a cache hit in a fresh process). `tests/test_caves_early.py`.
    - PROGRESS: `profiling.Report(progress=log)`: each stage's start, pooled stages' done / total, elapsed, ETA (30 s,
      a tenth when the count moves); run_jobs names each kind of job; pool_map collects as jobs finish (results in
      order). export_terrain(tiles) writes <tiles>/export_log.txt and MCP progress (`ctx: Context`,
      anyio.from_thread). `tests/test_progress.py`.
    - THE KAZE HOLES / PENCIL SHARD (white triangles 10-20 m across in Godot): the cliff shell's BURIED back drawn in
      the open. Two causes: the shell's back is the heightfield's ground moved in, and inside a sea stack (solid add
      volume over the heightfield's slim core) that left the stack hollow from the sea floor to ~16 m; and
      `_decimate` judged only faces with every corner on the visible rock, so LOD 1-2 pulled the back's faces out
      unjudged (Pencil 23,6 LOD 2: one 617 m2 buried face). Now: (1) the decimation's error counts every face whose
      centre is not deep in the rock (`front >= -thr`); (2) a face is buried only if its centre is deeper in the rock
      than max(thr, `BURIED_DEEP` 0.1 x sqrt(area)) and a corner is off it (a big flat LOD 0 face over rounded rock is
      surface); (3) `terrain_buried`'s baseColorFactor = the rock's mean colour there x `BURIED_SHADE` 0.6 (Godot
      ignores COLOR_0: white plates before); (4) check `terrain_cliffs.exposed_buried` (point 0.5 m out of a buried
      face in the air and over the pushed heightmap; > 2 m2 per tile LOD fails). (5) `CliffField._with_adds`: the
      shell is the whole rock inside 1 m of an add volume, behind `WHOLE_ADDS` (env HIFIPUSHIE_WHOLE_ADDS=1): on the
      OLD stacks it broke pyfqmr (a sub-voxel sealed pocket at stack0's waterline notch: a non-manifold edge at every
      count, the budget search fell to a third of the budget). Kaze block: island as shipped 3,16 LOD 1 / 2 exposed 223 / 104 m2;
      on the stacks agent's new jointed Column (main dbfe15e) 0 / 0 / 0 at every LOD with the solid shell off (kaze2)
      and on (kaze3); off stays the default (fewer floats, steadier counts). Seen from pushieworld's camera spots:
      no wedges (rend/new_*). Pencil block: 0 failures. Crown block: 0 failures. Tried and dropped: decimating front and
      back as two meshes joined at a locked seam (the front half would not go under ~60k faces at LOD 1); an absolute
      "no back in the open" rule (it made the dense mesh's tolerance infinite).
    - False alarms fixed in the seam check (`_plane_chain`, by position, chains only): a sliver in a border plane
      (11,8 / 12,8) and edges on a tile corner's vertical line (21,6 / 22,6 at LOD 2).
    - Fallen blocks seat on the lowest ground under their footprint minus `FALL_SEAT` x the relief's reach (a block
      hung over relief-carved rock: the crown-flank floats). Moves blocks in every export with fallen blocks.
    - slice_a's cave_mouth picture: the consumer's camera [271, 135, 2] is INSIDE rock (base field -1.2 there; the
      passage's axis 4.6 m west); from inside the passage (rend2.py mouth1) the cave reads clean at LOD 0.
    - `render_tiles(buried_color=)` draws the buried backs flat (no glow: it lit a cave magenta).
    - A face is also buried only if the point `EXPOSED_OFF` 0.5 m out along its normal is still in rock or under the
      pushed heightmap (pebble's borderline skin faces, centre 0.33 m in, faced open air).
    - Map-normal seams (the tiles agent's open item 1; pebble lod1 p95 15.6-15.8 > 15, slice_a 17-18): the borders
      carrying it had triangles of 0.1-2 texels at a sheer crease, each tile's texels reading different rock (decoded
      tangent normals 40-67 deg apart, vertex normals identical). `terrain_bake.bake_texels(border=)`: every LOD's
      cliff normal map eased to the low poly's own normal within `BORDER_FLAT` 1.5 texels of the tile's edge
      (`_bake_border`). Pebble: lod1 p95 15.8 -> 5.0, lod0_vs_lod2 p50 4.2 (eased at LOD 1-2 only it read 7.3 > 6).
    - `Field.build_w` (the stacks agent's per-call relief weight) was left on the Field: the incremental fingerprint
      read it as a global input that changed every export (main 6642cf4 never reused a tile). Reset per call.
      slice_a cave edit: 4 of 64 tiles redone, byte-identical with a cold export.
    - slice_a's two floating pieces ([359, 57.6, 9] 132-138 triangles, [291.2, 103.9, 23] 8-10) came with main's
      stacks-foot code (main 6642cf4 alone has them too); after stacks-style: see the last regression below.
    - `terrain_cache`: a fresh build is handed back through a pickle round trip (as a cache hit would be): a fresh
      terrain shared T.cover's arrays with the export's Materials cache, and the export after a cache miss reused no tile.
    - LAST REGRESSION (main 52b6ee3 merged, a3e70d1): the seven terrain test files pass; pebble 0 failures (282 s);
      alps 3x3 0; slice_a 1 (the [291.3, 103.8, 23] float: main's stacks code); slice_b incremental 4 of 64 tiles,
      0 files differing from cold. Kaze block (2,15)-(4,17): 1 failure, LOD 2 shards 0.73% (limit 0.5; main alone
      0.15%). NOT a new fault: LOD 2's decimation bridges air round the stacks (faces with their centre 1-2 m in the
      open). Main called them buried and drew them in the buried material: 2,997 m2 of buried faces in open air at
      LOD 2 (the consumer's white plates), 2,024 m2 more as surface. Here 0 buried in the air, 2,598 m2 as surface,
      of which ~250 m2 more have corner normals against the face (the shard count). Tried: calling faces turned
      against their corners' normals buried (no change: these face the air). OPEN: LOD 2 round stacks (a tighter
      error near add volumes, or interior corners whose normal opposes the face split onto the face normal).
    - Caves made walkable (2026-10-08, branch `tiles2-caves` from main 667b4a9; pushieworld notes 94-95; our copy of
      their v7 spec is terrain `tl2_island7`, + their old crown_tube as `tl2_island7_lava`; scratch cave4.py (a
      passage's planned vs walked floor), cone1.py, lava7.py, fullwalk.py (the walk in the export's field)).
      kaze_cave's 0.70 m step at the geo door: the door's floor (address ground - 0.3) stood over the geo floor where
      the door ended up after the pull back (-0.78), and the karst floor took its beds' wander at once (+1.5 m in 6 m);
      the passage's width / height (the old advice) can't move a step. Now a hillside mouth's floor is no higher than
      the ground at the door (`"z"` on an entrance sets it), the beds' wander eases in over MOUTH_EASE 20 m and is
      spread over BED_SPREAD 12 m (taken at once it climbed a 0.6 m staircase: the slot's floor is flat between 3 m
      nodes). Largest step 0.70 -> 0.26 m. The walk line names its largest step's place, and `_walk_fix` the lever by
      cause (a step by a mouth: the door's `z` / `at`; inside: the climb; blocked / tight / low: width, height).
      Lava `"grade"` (+ `"swing"`, default 30 m): `_switchbacks` = corners alternating either side of the flow along
      the slope's CONTOUR (the ground's broad gradient: a flow is a 14 m ridge of its own), the fewest corners nearest
      the flow that give the sloping length after a level landing at every turn (as long as the two legs still
      overlap: without them a walker stood on the next leg's floor, 2 m lower); floor = the highest line no steeper
      than the grade (landings and pits level) that is nowhere above its depth under the ground sampled across the
      tube (a min-plus envelope: kept "near its depth" it rode out of the ground where a leg left the flow); a pit's
      pile no taller than 0.3 x the tube. crown_tube (115 m fall in 180 m, a 35 deg cone) at grade 0.2 needs swing 54
      (the report says so with 30): 1,088 m of tube, pits 47 / 19 m deep, PASSES (largest step 0.35 m).
      Floating guard (the coordinator's ask): `_drop_specks` also drops closed cliff pieces off the tile border that
      never reach the pushed heightmap (+0.15 m) under `float_piece_m2` (FLOAT_PIECE 50 m2), from the dense mesh (so
      every LOD agrees); logged and listed in manifest `dropped_pieces`. Bigger ones still fail `floating` (a stack's
      head is a real fault). Pieces on a tile border are never dropped (both tiles would have to agree).
    - Island checks + the "regression" (2026-10-08, branch `tiles2-seams` from 383bcbf; pushieworld notes 97-100;
      scratch nrm90b.py (a border's worst normal pair, every copy), shardz.py (shard faces by tile / depth / area),
      rimprof.py (ground / pushed heightmap / S / holes / front along a line), tubetime.py (field cost of a tile's
      tubes), dec1/dec2.py (a tile's decimation by count, non-manifold edges)).
      Their 2:24 export on 383bcbf was COLD (code changed), not an incremental slowdown: tiles 15-16, 25-27 took
      1,445-1,495 s of marching cubes and 450-728 s of dense LOD0 EACH: crown_tube's graded switchbacks (1,088 m at
      1.5 m nodes = 731 segments) and `Tube.sd` tested every point against every segment. Now runs of TUBE_RUN 16
      segments, each at the points within its reach (box widened by the ellipse's aspect: a plain reach box changed
      values); identical within the reach (test_long_tube_by_runs). 6 crown tiles: marching cubes 54 s, dense 101 s.
      The summary's "border collapse + skirts 4,621 s" was the settle round's TILES (labels took the last round's
      span from the previous round's tiles on): stages are summed over rounds, dense LOD0 is its own line, and the
      summary always says "incremental: cold export (why)" or what was redone.
      (a) "normals differ by 90.00 deg" at 5,16 / 5,17: both tiles' identical ZERO normals (buried border vertices
      where the field is flat at the normal stencil; arccos 0 = 90), 54 Khronos ACCESSOR_VECTOR3_NON_UNIT errors on
      the Kaze block. `_project` retries wider stencils, then up; the seam check reports zero normals as their own
      failure. (b) LOD 0 shards: Pencil's 3.55 of 3.59 m2 are 3 m under the sea on the 21|22 border, Kaze's mostly
      grazing (dot -0.01..-0.3) at borders. `_unflip_corners`: a corner turned against its face gets the face's normal
      (not on tile borders: split there, the two tiles' border normals differed 96-142 deg, since `_compact` drops
      the canonical copy once no face uses it). Kaze LOD 2 0.79 -> 0.50%, LOD 0/1 0.006 / 0.034%; Pencil LOD 0 still
      0.0129% (the underwater border cluster). (c) the 4,18 buried non-manifold edge doesn't reproduce on 383bcbf.
      Visible and missed by every check: a dark crack with the shell's back in it (and teeth) round kaze_cave's
      doline. Region S was cut at its grown mask (0.64 -> 0 in one lattice step) and openings pushed the heightmap
      linearly (front 0.3-0.6 m above it). `_grow` bounds the blur 3 sigma out; openings push by op^PUSH_POW. A faint
      line and a few notches remain (rend/shk3_*). slice_a's weights1 lod0_vs_lod2 is main's (667b4a9 alone fails
      the same block identically). Manifest `cave_paths` (note 100): per passage the walk's points [x, y, floor | null]
      every 0.5 m, width_m, headroom_m.
      Results: pebble 0 failures (266 s, Khronos 1,044 files 0/0), alps 3x3 0, slice_a 0 (the stacks float is gone
      on main), slice_b incremental 4 of 64 tiles, 0 files differ from cold; Kaze block 1 (LOD 2 shards 0.5005%, at
      border vertices), Pencil 1 (LOD 0 0.0129%, underwater). OPEN: tile 16,25 LOD 2 2,790 / 800: pyfqmr leaves a
      non-manifold edge 4-6 m inside the rock at every count from its dense mesh ([1047.8, 1649.5, 66.1]: where the
      graded tube runs close under the shell's back), so `_decimate` keeps LOD 1's mesh; border-vertex shards (a
      canonical way for both tiles to split a border corner).
      The two not-visible shard trips are left as they are (the coordinator's call): Kaze LOD 2 0.5005% at tile-border
      vertices, Pencil LOD 0 0.0129% (a cluster 3 m under the sea on the 21|22 border).
    - Tile 16,25 LOD 2 and steps on the collision mesh (2026-10-08, branch `tiles2-tube` from main 4e612c9; scratch
      col2.py (a column through the shell: every sign change), replay.py (pyfqmr counts on a decimation dump),
      csteps*.py (collision steps / risers along cave_paths, on any export incl. pushieworld's, read only)).
      16,25 (crown_tube's switchbacks under it) stays at ~2,800 of 800 triangles: ACCEPTED as valid but heavy.
      Tried: the shell's rind round a void (dv < cave_wall) read the tube's ROUGH distance, whose level sets 3-5 m out
      folded into 0.4 m slivers (a column: shell 64.85 | air | 65.75-66.15 | air); with Tube.sd(plain=True) and the
      back joined to the rind by smin 2.5 m (a 1.2 m air layer between them) the dense mesh decimates manifold at
      every count in dec2.py, but the block export still stalled (2,840) and a single-tile export of 16,25 reached
      699: the stall is the border chains' kept vertices with neighbours (skirt edges 696 vs 485), not the folds.
      Both changes were reverted (not needed for a valid mesh; they move every cave's shell). `budget_check` now
      names a cave under an over-budget tile and what to change ("route the passage under the middle of a tile or
      deeper"). Next if it matters: why 16,25 keeps ~700 border edges at LOD 2 (the `thin` rule: rock too thin for a
      skirt round the tube keeps vertices at every LOD; or collapse failures from a neighbour).
      Steps (pushieworld note 101: their walker needed a 0.6 m step-up on crown_tube's way to the lower pit):
      `terrain_caves.collision_steps` walks each cave_paths passage on the LOD `collision` meshes (`collision_floor`:
      the highest triangle under the walk's floor + 0.9 m) and writes per passage collision_floor,
      largest_step_m, largest_step_collision_m, tallest_riser_collision_m (+ _at: runs steeper than 45 deg at 0.1 m)
      into the manifest and a line per passage into the export notes. On THEIR export: centre-line steps 0.29 m,
      the tallest riser 0.2 m (60 deg) at [1084.4, 1756.4, 3.2] where the lower pit's pile of blocks meets the tube
      floor; with a 0.4 m body footprint the same. No 0.6 m riser on the path: their controller's 0.6 is either a
      capsule catching the rough pile (Mound rough 0.25 m at 1.5 m scale) or something off the path: asked them where.
  - Dashed cracks on the grass (2026-10-08, "tiles3" agent, branch `worktree-agent-a2322e8cd3d4f3416`; pushieworld note
    104, the user saw thin dark dashed "seams" on the crater rim's grass, on the cliff meshes, baked maps only; renders
    /mnt/data/hifipushie/tiles3/renders/t3_*; scratch DURABLE there: run.sh / run_orig.sh <script> (this worktree /
    orig/ = the branch point + only the new check, the "before"), exp.py <terrain> <tag> '<cfg>' (OLD=1: the old relief
    cut), rend.py <terrain> <tiles dir> <prefix> [channel] (rim / close / west views of the rim; env VIEWS, IDS=1,
    PARTS=ground|cliffs), mirror.py (theirs/ = a symlinked read-only copy of their export, render it like ours),
    topdown.py + channels.py + comp.py (a top-down raster of which mesh is on top, and the cliff maps decoded there:
    base, ORM, normal map vs vertex normal), prof2.py (every mesh a vertical line meets along a transect, with its
    baked colour / AO), rimprof.py (ground / heightmap / S / front along a line), trans.py (the bake field's surface and
    normal across a line, pieces switched off), px2w.py (render pixel -> world point from the id pass's distance; the
    id pass's glb index did NOT match render_job.json's list: untrusted), q1.sh (tests + regressions)).
    Two causes, both in the cliff tiles' maps, neither in any check:
    (1) THE VISIBLE ONE: the overlay edge. Where the front sinks (S < SINK_EDGE) it dives metres within a metre (S rises
    0.13/m on the rim: the dive is ~75 deg) and crosses the heightmap a few cm down; the crossing interleaves (heightmap
    and front 2 cm apart for metres). The texels of the strip that shows were coloured ROCK: the layer weights' 0.4 m
    normal came from the SUNK front, so on the true ground up to 0.4 m beside the dive it tipped to the horizontal
    (Gs (-0.70, 0.69, 0.16) at S 0.23), base colour 0.18 vs the grass's 0.43; and the dive's AO was its vertices' (5 m
    down: 0.04), interpolated up to the strip. Fix: weights from the rock UNSUNK (`weightfield` = base); every texel and
    AO vertex on the sunk part read the true ground over it (`CliffField.lift`: w = 1 below SINK_EDGE easing out by
    SINK_EDGE + UNSUNK_BAND 0.05 of S; colour at the lifted point; normal map = the ground's normal, `terrain_bake._unsunk`;
    AO at the lifted vertex, `terrain_cliffs.lifted`; the tile-border easing to the low poly's normal skipped there).
    Geometry is unchanged (the dive and the crossing are where they were: the strip just reads as grass now).
    (2) A real field step, found on the way: `Field._solid` evaluated the rock relief only where its weight > 0.01 and
    took it at full weight there: 1% of the relief (a 2-3 cm step, up to 22 mm on test_tiles' coast) along the weight's
    0.01 contour metres out on the grass. Now eased in (RELIEF_CUT / RELIEF_FADE 0.1). Thin rock's strata had the same
    (sqrt(1e-3) = 3%): eased. Both move field values only where the weight is under 0.1 / 0.02.
    CHECK `soft_ground_jumps` (seam_check (7), FAILS over JUMP_LIMIT 3 sampled texels per tile LOD): every 7th texel on
    soft ground (rock layers < JUMP_SOFT 0.2 and rock relief weight < JUMP_RELIEF 0.1) compares the bake normal at 3 cm
    and 6 cm (`terrain_bake` JUMP_H); a step in the value reads 1/h, a smooth surface or a designed riser the same. On
    the rim block (tiles 15-16 x 16-18 of tl2_island7): the branch point's code + the check FAILS (10 tile LODs over
    the limit, 15,17 LOD 0: 40), this branch 0. Left out of the check, each after a false alarm: rock structure
    (relief weight; creases on a 37 deg grassy rock face), designed steps (`designed_step`: the Edits zone = turf
    risers, bunker edges and lips; fallen blocks: pebble 588 texels), built edges within cave_wall + 2 m of a volume
    (`near_volume`: stack feet under the sea).
    Regressions (cold, a loaded machine, under /mnt/data/hifipushie/bin/capped): pebble 0 failures (1,274 s; shards
    0.002 / 0.007 / 0.31%, lod1 map normals p95 6.2), alps 3x3 0, slice_a 0, slice_b incremental 4 of 64 tiles and 0 of
    1,488 files differing from a cold export; the seven terrain test files pass.
    Note 106 (downs_pond's dam missing from the tile heightmaps; scratch dam.py <terrain> x y, lakechk.py <tiles dir>
    [name x y r level area], rep.py <terrain> <words>): the dam's lake-side face was a 12 m wall at 50-65 deg, so the
    cliff Region took it (S = 1) and the heightmap was eroded by the 3.8 m push ball, crest and all. The wall was the
    BUILD's: `terrain._lake`'s bank started at the water's edge (nothing inside the radius), so on a slope it stood
    as tall as the fall across the lake. Now: the bank runs on down at 1:2 under the water, crest >= 3 cells,
    `T.dams[name]` = the cells the embankment raised; `Region` takes those cells (+ margin + push) out of the cliff
    region (no cliff mesh, no push: the heightmap carries the dam); `Terrain._bank_report` (measured: depth at the
    dam vs asked, freeboard by raising the water 0.25 m at a time until it leaves, the dam's thickness half the
    freeboard up) with warnings (on a slope, freeboard < 1 m, under 3 cells thick); manifest `lakes` {level, at,
    area_m2, depth_m, outline rings} (`terrain_mesh.lake_outlines`); check `terrain_cliffs.lake_check` (each lake
    flooded on the written heightmaps from its outline: fails over LAKE_AREA 1.5x, under 1 / 1.5, or leaking).
    Their export: 87,490 m2+ and leaking for 3,300 (FAILS); the pond block re-exported: 2,954 for 2,964 m2. The
    island's pond is now 9 m deep at the dam for depth 2 (warned), freeboard >= 1 m, dam 12 m thick.
    tests/test_tiles.py::test_dam_stays_in_the_heightmap. Every dammed lake's ground changes.
    The pond block (tiles 8-10 x 8-10) alone fails LOD 2 shards 1.12% (5 faces, none at the pond; 3 cliff tiles, a
    tiny visible area): not compared with main.
    Note 107 (a dead-flat seabed shelf at -8.4 m off the island's downs_beach, ruler-straight sides; scratch
    depth.py <terrain> <png> x0 x1 y0 y1 = a depth map + the measure, run_orig.sh for the before; picture
    terrain3d_renders/t3_seabed_before_after.png): `terrain_sea`'s beach profile was level - 0.6 + max(sd, -3 widths)
    x 2.6 / width, i.e. held at -8.4 m from 3 beach widths out, and the beach's share is carried offshore from each
    cell's NEAREST coast point, so the shelf ran to the frame's edge and ended in one step along the lines where the
    nearest coast point stops being beach. Now the profile runs on at its own grade until it meets the sea's floor (a
    soft max) and the share fades between 3 and 8 widths out. `terrain_sea.seabed(T)` (in the report: "sea floor
    (measured)"; SHELF): flat shelves over 0.4 ha above the sea's depth, straight steps over 60 m offshore, each a
    WARNING. Island before: 8.8 ha at -8.4 m around [377, 123] + 0.6 ha, steps 469 m and 133 m, 39% of the box's sea
    cells at -8.4; after: 0 / 0 / 0.2%. Every beach's seabed changes. tests/test_tiles.py
    ::test_beach_shelves_on_to_the_sea_floor.
  - Note 117 (2026-10-09, "terrain117" agent; their island re-export on 0168d10, 5 rivers / 8 falls; our copy terrain
    `t117_island`; scratch DURABLE /mnt/data/hifipushie/terrain117/: run.sh / run_orig.sh (this worktree / HEAD before,
    niced + capped), fullwalk.py (the caves walked in the export's field), timing.py (light vs export walk side by side),
    probe.py / probe2.py x y z (a column through the export field, each volume's d; relief weights there and the
    ground round it), steep.py (a tube under a steep tilt), dec.py i j (a tile's dense mesh, pyfqmr counts, what
    folds), exp.py, tests.sh).
    (a) crown_tube failed the tile walk (width 0, 1.3 m step at [998, 1676]) though set_terrain's passed: the face's
    rock relief. `Field._solid` weights relief by `relief_at` (a COLUMN grid: the ground's steepness) wherever |F| <
    reach, and inside a void F is small however deep it is: 12 m under a 56 deg slope (relief weight 0.94; 0.44 on
    the old spec's ground, the rivers' base made it steeper and moved the switchbacks) the 1.8 m facets came in at
    full size and built a sheet of rock across the tube 1.3 m over its floor. The light field (set_terrain) has no
    relief, so never saw it. Not the river cut or a fall (crown_beck is 400 m east). Now within NEAR of a cave void
    (dvoid, arches excluded) the face's weight fades out between 1 and 2 x the relief's reach under the open ground;
    the cave's own passage-scaled share (`near`, `_relief_cap`) stays. Walks: export field crown 3.2 m headroom / 4.8
    width / 0.35 step (light 3.7 / 4.8 / 0.35); kaze and pencil unchanged. The two walks still differ by that
    passage-scaled relief (kaze headroom 4.4 light vs 3.4 export; pencil 3.9 vs 5.4, the light field has no stacks):
    same verdicts, numbers within ~1 m. Exact agreement means walking the export field in set_terrain: 41 s instead
    of 18 s on the island (field 14 s + walk 27 s): not done. tests/test_caves_walkable::test_deep_cave_under_a_steep_face
    (HEAD: headroom 0.85 m / width 1.55 m short of the plain field; now < 0.5).
    (b) 16,25 at ~250k triangles at every LOD: not the shell's thickness as budget_check guessed. pyfqmr pinched two
    sheets (crown_tube's wall and the rock kept round it / the shell's back, within a voxel) onto one shared edge
    (4 faces) at EVERY count (2-4 such edges), `valid` called each a fold, and the tile kept its dense mesh. Now
    `_split_nonmanifold` / `_unpinch` (in `_decimate.run`): faces round a pinched edge paired by angle (alternating
    direction; both ways round tried), each pinched vertex copied once per fan and stepped PINCH_GAP 5 mm into its
    own sheet (at one position the seam check, welding GLBs by position, found the pinch again); never on an open
    edge (tile borders stay canonical). Single-tile export of 16,25: LOD 0/1/2 11,991 / 3,000 / 800 (before 250,951
    / 250,602 / 250,442), collision 3,000, 0 check failures (watertight per LOD, 0 floating, 0 buried in the open),
    228 s (was 918). Buried passages are NOT dropped from LOD 1/2: forcing the decimation was enough, and the
    collision still holds the cave (the walk on the LOD 1 collision: largest step 0.24 m). Not run: the full island
    or a block with neighbours (the coordinator: single tiles on a loaded machine); unpinching never touches a border
    vertex. tests/test_tiles::test_pinched_sheets_split.
  - Note 118 (2026-10-09, "terrain117"): river-corridor heightmaps for gdamp's nested 0.25 m water solve,
    `terrain_corridors.py`, opt-in export.tiles `"corridors": true | {spacing 0.25, buffer 15, size 128}` (kept out of
    the tiles' incremental fingerprint). Rects (axis aligned, <= 128 m, overlapping) along each river's water line
    (half width + 15 m), each lake's outline ring (+ 15 m) and each fall's pool (dropped when a river's rect holds it);
    `corridors/corridor_<n>.npy` float32, row 0 north; manifest `corridors.rects` [{file, extent, cols, rows, spacing,
    follows}]. Value = the top surface as the tiles build it: the ground tile's pushed heightmap (`Region.height`,
    with the stream bed edits) and over it the meshed (cliff) field's topmost crossing (down from 10 m over the
    ground in steps of half the field's value, <= 0.5 m, then bisection to 1 mm). `pushed_grid`: Region.height's push
    ball on a 0.25 m grid by shifted views (its offsets are -push + 0.25 k: a grid moved by -push), equal to it
    exactly, 0.1 s where the ball took 15-25 s for a fall's 40 k samples. Island: 24 rects, 3.4 M samples, 13 MB,
    143 s (+ ~40 s field setup alone; inside an export the field exists). Against LOD 0 (scratch corcmp.py: vertical
    rays on the ground + cliff GLBs, surface primitives): lowland vale_river tile 27,13 (ground on top): |dz| p50
    0.006, p95 0.029, p99 0.066, max 0.19 m (the 1 m ground grid can't hold the bed's finer shape); crown_beck's fall
    tile 20,23 (cliff on top): p50 0.018, p95 0.064, p99 0.13, max 0.71 m (vertical differences on 70-85 deg faces:
    the mesh's 0.04 m is along the normal). tests/test_corridors.py.
  - Terrain styles (2026-10-07, "terrainstyle" agent, branch `worktree-agent-aaa51cb5f5cb72005` (delivery 1 merged as main 1e54176); consumer brief:
    /home/joe/dev/pushieworld/docs/hifipushie-notes.md 18, 58-59; renders `workspace/terrain3d_renders/ts_*`; scratch
    DURABLE in /mnt/data/hifipushie/terrainstyle/: run.sh <script>, sheet.py <png> [styles] [layers] (swatch sheet +
    strips, no terrain), mk_slice.py (terrain `ts_slice_a` = tl_slice_a + zones dumpling_downs west / painted_east
    east + styles blobby / anime; writes the styles alone into ts_slice_a_styles/), exp.py (tiles export into out/),
    prev.py <terrain> <tag> x y r '<views>' (preview_tiles + styled renders), rend.py (renders of an existing export,
    textured styles | baked), diffield.py / diff2.py / diff3.py (which Field grids differ outside a styled zone)).
    - `terrain_style.py` + `terrain_styles/<name>.json` over `_base.json` (realistic, blobby, anime, cartoon, pixar):
      spec `"styles": {style: zone | [addresses] | {"in", "band", "sheet"}}`, everywhere else realistic; zones are a
      PARTITION (a later style wins overlaps; realistic = no zone), weights = smoothstep over each style's band of the
      signed distance to its own piece, normalised (two adjacent zones meet 50/50, no realistic between them). Layer
      textures = op stacks (blotch, strokes, bands, ripples, dots, grain, cracks, facets, pillow: periodic on the torus,
      tone -1..1 x albedo with warm / cool tints, height m), mean = the layer colour (the terrain's realistic colour turned
      by the sheet's saturation / value = the plant style's numbers). Written PNGs are cached by their inputs + this
      module's code ($HIFIPUSHIE_STYLE_CACHE): a cached write is byte-identical (test). `write` / `export_styles` /
      manifest `styles` (contract 1, order, styles[].layers[l] files / size / colour / roughness / seasons tint_linear,
      snow numbers, tiles[].styles, maps sd + weights, recipe); in every tiles export of a spec with styles, or alone:
      `export_terrain(name, styles_only=True)` (seconds, updates manifest.json). `look_terrain(styles=True)`: swatch,
      season and transition sheets; with tiles=True the views with the recipe (`render_tiles(textured="styles")`,
      `blender_tiles._styled`). "styles" is in terrain_cache.THREE_D (the 2.5D build never sees it).
    - Rock shape in the field (`Field.styles` from `terrain_style.rock_styles`, weights on the terrain grid with the
      sheet's `rock.band_m`, default 10 m): `relief` multipliers on the realistic rock numbers (`rock_variant`), `pillow`
      (`pillow_carve`: 3D jittered cells, grooves smoothstep^2, C1), `soften_m` (Gaussian on Field.H in the zone, also
      takes the heightfield's facet_delta out there), `fallen`, `micro`. `_styled_relief` mixes realistic's and each
      style's relief by weight. INVARIANT kept: with no rock-shaping style the field is the old code path; with one, the
      realistic zone is bit-identical (test_rock_shape_by_zone) because `_structure_grain` (a GLOBAL percentile) and
      `_local_thickness` (thin pieces span zones; per-piece height levels) read the UNSOFTENED ground. Any new global
      statistic in Field must do the same.
    - First delivery: /mnt/data/hifipushie/terrainstyle/ts_slice_a_styles/ (materials/<style>/..., styles/, styles.json,
      swatches.png, seasons.png); full export with styles (OLD geometry: before the rock shapes) out/ts_slice_a: same 3
      known check failures as main (LOD 0 shards 0.012%, ...).
    - Read so far: textures tile (wrap seam <= 1.4 on every layer); blobby = flat soft fields (good), its rock texture is
      nearly blank (a first "pillow" texture read as flagstone paving: pillows belong in geometry); anime grass reads as
      painted dabs, anime rock as crisp painted bands; cartoon tufts are blobs, not ink ticks; pixar blades too subtle.
      ts_06_top_border (styled recipe, old geometry): flatter and paler than the baked look, faint contour-like lines on
      the blobby grass slopes (not the bump: still there without it; likely the turf-lip risers' geometry, which the
      baked colour hides: not isolated).
    - Styled GEOMETRY seen once (ts_04_*: preview_tiles, 9 tiles round [240, 90], one LOD, no checks): blobby cliffs are
      rounded pillow lumps (read as melted / pillowy, not yet "pebble-smooth"), anime cliffs carry strong painted strata
      with bedding ledges, the two meet at the zone line as different rock (the brief allows it). NOT RUN YET (the heavy
      slot was held for another session): a full ts_slice_a export with styled geometry and its seam / shard / floating
      checks, and the pebble / alps 3x3 regressions (no styles: the field code path is unchanged when no style shapes
      rock, so they should be byte-identical; verify).
    - Round 2 (consumer notes 71-75, Godot): CONTRACT 2 = soft layers always top-projected (side planes at v = world
      height turned their tone patches into ~0.5-1 m terraces up slopes: the "contour lines"), rock triplanar with
      `v_jitter_m` (strata wander along the strike; anime rock 12 m, 3 m jitter: its 8 m repeat up a cliff). `tileable`
      compares the seam with ALL neighbouring rows' mean step + one 8-bit level (one row beside it: a pebble on the
      seam read 4.04 for cartoon sand; flat blobby swatches read 1.7 on 1e-4 steps); `bands` are shifted half a band
      off the wrap row (an edge on it was a real seam line). Blobby rock by measure (rockform.py: horizontal sections
      of the south cliffs x 20-120, band-passed 0.5-8 m): pillows 3.5 m / soften 1.5 -> 6 m, stretch 1.8 (cells taller
      than wide: seams run up the face), depth 1.0, round 0.5, soften 3: undercut share 0.078 -> 0.001 (unstyled
      0.041), convex share 0.512 -> 0.534, lobes / 10 m 1.33 -> 1.22. NOT yet rendered.
    - Open, in order: (1) those exports + checks; (2) the tufts op for cartoon (done) vs dab size of pixar blades (too
      subtle); (3) blobby rock = rounder, fewer, bigger pillows (size 3.5 -> 6, depth 0.8 -> 1.0?) and pebble-smooth
      fallen boulders (fallen 0 today: none); (4) the shader recipe as a Godot .gdshader (consumer wish 5); (5) snow by
      height / hollows (numbers only today).
  - Terrain styles 2 (2026-10-07/08, "terrainstyle2" agent, branch `worktree-agent-a4a49e9b179132f6a`, main merged in;
    CONTRACT 3; scratch DURABLE in /mnt/data/hifipushie/terrainstyle2/: run.sh / run_base.sh <script> (this worktree /
    634977c's src in base_src/, its resources.py replaced by the current one: the old slot starved behind new-queue jobs
    for 40 min), reg.py <pebble|alps> <tag> (cold regression export), cmp.py <a> <b> (every file of two exports),
    exp.py, prev.py, rend.py, gv.py <out> <style[:before],...> (game-like ground views), ba.py (swatch sheet before /
    after; before/<style>.json = the sheets at the branch start), bt.py '<bands op json>' <out> (one anime rock
    texture), rs.py <terrain> <out> (rock_scale fade map), imdiff.py, q1-q3.sh; renders `terrain3d_renders/ts2_*`).
    - Regressions (the previous agent's owed jobs): pebble (3792 files) and alps 3x3 (297) exported cold with this branch
      (before the stacks merge) and with 634977c (just before the styles work): BYTE-IDENTICAL, 0 check failures. The
      styled-geometry ts_slice_a export: on the merged branch 2 failures (lod0_vs_lod2 weights1 p95 0.277 > 0.25, the
      slice's known one; a 124-triangle piece of the anime STACK column floating 9.6 m up at [359, 57.5]: the stacks'
      code, reported to main), LOD 0 shards 0.011 -> passing, lod1 map normals 17.1 -> passing.
    - Turf-lip risers off (ts2_lip_off vs _on, previews at [150, 140]): the faint dark lines on blobby slopes REMAIN
      without risers: they are where the cliff overlay's shell meets the heightmap (the "line with small dents at the
      crossing" from the rock5 round), longest in blobby because softening widens the overlay. Not fixed. What the
      risers did make on blobby: pale crumbs along every lip -> style rock key `lip` (share of the turf step;
      blobby 0; `Edits.lip_scale`, realistic cells exactly 1: bit-identical, tested).
    - Cartoon soft layers (the consumer: soft blotches read as gradients under hard-band cel light): flat fields in two
      crisp tones (`blotch` `share` = the second tone's share, `width` = size spread), dark ink tufts, pale ticks, white
      and yellow flower dots in clumps (`dots` `clusters`, op key `paint` = an sRGB colour laid where the op marks), no
      grain; `macro` 0 (the baked colour's soft variation was most of the smudge). Anime: 3 crisp value steps (soft
      0.08), dabs in 3 tones (`strokes` `levels`), no dark gap between dabs, a few pale flower dabs, `macro` 0.15.
      Sheet key `layer_edge` {height, depth} (cartoon 0.35 / 0.04, anime 0.4 / 0.08): the layers re-weighted by their
      height maps where they meet (`terrain_style.edge_weights`, recipe step 1) = crisp painted layer edges; the
      cartoon layers carry a 0.7 m height-only blotch so the edge wobbles.
    - `terrain_style.ground_view` (in look_terrain(styles=True), and gv.py): eye level and 25 m up over grass with a
      winding earth path, mipmapped trilinear sampling, the recipe's anti-tiling, the style's layer_edge and macro
      stand-in, flat cel light. The judge for ground textures: the swatch sheet's tiles hid both the mush at distance
      and the soft layer edges. Sheets ts2_ground_ba.png, ts2_swatches_ba.png in the scratch dir.
    - Anime strata (`bands`): `pinch` (each band's thickness wanders; an edge moves by half the change of the bands
      either side, so neighbours absorb it: a cumulative sum random-walked whole stacks of strata metres up and down),
      `breaks` (lenses: a band wedges to nothing and back over `break_len`, never a vertical edge: fading a band's TONE
      along u drew vertical streaks), `vary` (tone strength along the strike); anime rock 24 m tile (12 was too short
      for strike variation). Ops marked `fade_small` give way on small / thin rock: the layer ships
      `<l>_plain_albedo/_normal.png` (texture(plain=True)) and manifest `layers[l].small` {albedo, normal, face_m,
      thick_m}; `styles/rock_scale.png` (RG: face height / 64 m, half-thickness in plan / 32 m; `rock_scale(T)`: relief
      within 40 m averaged over steep cells, EDT of the ground standing over the middle of the relief within 100 m,
      max within 15 m; sea stacks stamped at their solid column's radius, not the heightfield's slim core).
      `SMALL_FADE` face [4, 12] m, thick [3, 10] m. In Blender's styled render (blender_tiles._styled) too; layer_edge is
      NOT in the Blender render (ground_view has it). ts2_s3_stack1.png: the stack plain, the cliffs behind in
      wandering strata.
    - Consumer changes for contract 3 (CONTRACT_LOG): layer_edge re-weighting; `small` plain textures by rock_scale;
      read size_m (anime rock 24, cartoon grass 16, anime grass 12) and macro (cartoon 0, anime 0.15) from the
      manifest.
    - Item 3 of the brief (the hard wandering edge in island_vale.png) was dropped: pushieworld found it is the tree
      rows' sun shadow (their note 88).
    - Contract 4 (2026-10-08, branch `terrainstyle2-c4`, pushieworld note 92): every `<layer>_albedo.png` (and the
      plain `small.albedo`) is RGBA, alpha = the height at 8 bits (same normalisation as `_height.png`, which is still
      written), flagged `layers[l].albedo_alpha = "height"`; Blender loads style images CHANNEL_PACKED. Test: alpha
      equals the 16-bit height within half a level, cache bytes identical; ts_slice_a styles-only worst wrap seam over
      RGB and alpha 1.18.
    - Open: the overlay-crossing lines (above); cartoon tufts / flowers read small at eye level (judge in Godot: one
      flower clump per ~30 m2); anime dabs barely read at eye level now (were mush); a dedicated ground_view for rock
      (strata on a cliff from 40 m) instead of the Blender render; pixar untouched.
  - Sea stacks (2026-10-07, "stacks" agent, branch `worktree-agent-aeb27454ed1610793`; the user on pushieworld's Kaze
    coast in Godot: "Seastacks don't look like real seastacks, they're kind of a mess"; references
    workspace/level_refs/stacks/ (9 CC photos: Old Harry, Twelve Apostles, Duncansby, Yesnaby, Bedruthan, Reynisdrangar,
    Old Man of Hoy, Risin og Kellingin; README with licences); sheets /mnt/data/hifipushie/stacks/st_sheet3.png (photos |
    old clay | new clay | each style) and st_island_before_after.png (tl2_island Kaze, anime textured, preview_tiles);
    scratch DURABLE there: run.sh / run_main.sh <script> (this worktree's / main's code, orig/ = git archive of main),
    iso.py (one island stack meshed from the export's field: full | real (styles off) | norelief | alone), col.py /
    variety.py (Columns alone + 3D measures), styles_row.py (stack0 in each style), tune.py '<json list of FORM
    overrides>' (silhouette + 3D measures over 8 columns), measure.py (photo masks + the same silhouette measures),
    clay.sh out.png az el meshes.npz... (Blender workbench, an ortho panel per mesh; CROP=m), sheet.py, prev.py <tag>
    [styles|baked|clay] (preview_tiles round the island's stacks + sea views; ~40 min of it is the heavy queue),
    exp.py (tiles export with checks), hang.py / slice.py / pieces.py (a column's loose or hanging pieces),
    oldstack.py (the old Stack, for before / after)).
    - DIAGNOSIS (iso.py, r00_base.png): the mess was the Stack prism's OWN form, not the style or the field: the full
      field (anime), styles off, rock relief off and the Stack's sd alone mesh nearly the same pile of tyres (beds
      1.6 m thick each +-0.2 r proud / set back all round, lobes 0.55 r changing every 6 m, a lowered broken top that
      cut sections loose: tiles2's floating pieces at z 38-39 over stack0). The dark stripes in Godot are the anime
      sheet's rock `bands` texture (still there: even painted strata over every face; terrainstyle's call).
    - Measures (photos vs ours; measure.py, tune.py): silhouette edges over 15-92% of the height: swell (edge minus its
      25%-height smoothing / width), bulges (outward maxima per height-in-widths), straight (curvature under 1.5% of the
      width over 3% of the height), top_over_base (width at 85% / 15% of the height); 3D: vertical_nz (side area's
      median |nz|), planar (side area within 8 deg of six azimuths), top_flat. Photos (4 Apostles + Hoy; the Duncansby
      and Reynisdrangar masks are unreliable): swell 0.039, bulges 1.75, straight 0.59, top/base 0.61 (0.48-0.80),
      h/w 1.9. Old: 0.036 / 3.65 / 0.28, vertical 0.29, planar 0.30. New (Column alone, 8 cases): 0.019 / 1.11 /
      0.56, top/base 0.64 (batter 4.5), h/w 2.6, vertical 0.14, planar 0.56 (the field's facets add the fine breakup on top). Real
      stacks DO taper (0.6); they don't end in a point.
    - `terrain_stack.py` (Column, FORM, form): the plan = two joint families' faces (65-115 deg apart, own offsets,
      chamfered corners, a stray joint slicing one side off), edges a smooth max (`bevel`); CUTS = box windows in
      (height, position along the face) with soft edges (`ramp`, wider for deep cuts so |grad| stays < 3): steps where
      blocks fell above OR below a bed over part of a face, soft beds (1.2 per m, 0.3-0.8 m thick) eroded back 0.15-0.35 m on part of 2-4
      faces at irregular heights (ledges, never rings: all round on every bed was the pile of tyres), open joints as slots,
      corners gone from a bed up; faces batter in 4.5 deg (capped at 35% of the offset), wander, light warps (`rough` 0.02: at
      0.08 they read as draped cloth); the top flat and dipping, 1-3 parts of it fallen lower; stage auto: broad,
      slender, stump, rarely (p_spire 0.12 of slender ones) a spire tapering IN LEDGES to a crest >= 2 m wide at the
      top (two planes meeting in a knife edge meshed as a comb of slivers; a smooth taper read as a bullet / cathedral
      spire); the notch deepest on one exposed side, its height per face in the tide band, uneven along the face; 2-5
      fallen blocks LEANING on the foot (drawn in until they overlap the column: alone in deep water they float). Every
      section keeps >= 50% of its plan offset and >= max(1 m, 0.18 x offset). Cut depths scale with height / width on
      squat stacks (a stump cut like a tower read as a carved chair). terrain_mesh.Stack wraps it (same name and
      interface + `over`, `sea`, `stage`); `stacks(T)` takes each stack's style form from
      `terrain_style.stack_form` (the `rock.stack` of the style weighing over half at its centre; "stack" is a
      ROCK_KEYS key that does NOT count as shaping the field, so the realistic-zone invariant is untouched). Sheets:
      anime crisp (bevel 0.25, bigger steps, more spires), blobby a rounded pebble pillar (bevel 2.2, no slots or
      spires), cartoon chunky and battered (few thick beds, big steps), pixar soft (many shallow beds, top-heavy).
      The field is scaled 0.8 (overlapping cuts steepened it to ~3.5).
    - tests/test_stacks.py: one piece down to the plinth (every section connected below, face + edge connectivity at
      0.5 m: a voxel touching only by a corner is what marching cubes cuts loose), continuous (|grad| < 3), vertical
      and planar walls, deterministic, overrides checked, every sheet's keys known.
    - Sea cliff talus (terrain_sea): the smooth 13 m domes between the island's stacks were the apron at 0.3 x the
      cliff's height; now `TALUS_SHARE` 0.08 x height + `TALUS_BASE` 4 m (<= 0.3 x) at `TALUS_SLOPE` 36 deg out from
      the foot, its blocks the 3D tiles' fallen blocks (fall_zone finds it). Changes every cliffed coast's heightfield.
      With 2 m / 32 deg the low apron lay in the splash band and its fallen blocks flipped rock / wet rock / sand
      between LOD 0 and LOD 2 (pebble lod0_vs_lod2 orm p95 0.213 > 0.15); 4 m / 36 deg passes.
    - pebble_disc tiles (this branch vs main, same machine): the only failure is main's own (lod1 map normals p95
      15.78 vs main 15.55, limit 15); shards LOD 0/1/2 0.0082 / 0.0252 / 0.230% (main 0.005 / 0.023 / 0.198);
      floating 0; Khronos 1044 files 0 / 0 (round 3 export). Tests also: no sealed air in a column at 0.2 m, no recess
      narrower than ~1 m (thin air 0.07-0.22% of the solid: bevel corners), test_level_look, test_terrain_style,
      test_tiles pass.
    - Detached foot pieces (2026-10-08, branch `stacks-foot`; tiles2: 30 triangles 0.75 m over the heightmap at
      [228.6, 981, -0.8] by tl2_island stack2): (1) the rock relief BUILT 0.3-0.4 m out from the column over its notch
      (a lip in the air); a Stack's relief now builds at most `terrain_mesh.STACK_BUILD` 0.05 m (`vol.build`, weighted
      by the stack's relief share `Field.build_w`: continuous, fields without stacks untouched); (2) the column's rock
      ended at base - 1 m while the sea floor round it is deeper: its rim hung over the floor and the relief cut it into
      pieces. `Column(foot=)` = the lowest ground within 2 radii - 1.5 m (`stacks(T)`); (3) fallen blocks seat
      `BOULDER_SEAT` 1.2 m inside the column. Test: tests/test_stacks.py::test_no_piece_detached_at_the_foot (a
      synthetic cliff coast with 3 stacks: every solid piece round each foot reaches the ground; failed before).
    - Styled stacks floating (2026-10-08, branch `stacks-style`; terrainstyle2: ts_slice_a's anime stack, a 124-triangle
      piece 9.6 m up at [359, 57.5]): it was not the Column but the heightfield's LOBED stack core (terrain_sea): lobes
      took it to ~1.75 x its radius, past the clip cylinder round it (terrain_mesh.stacks' rc), so a sliver of it stood
      outside the solid stack, cut loose 5-12 m up by the clip below. The core is round now (the heightfield's stacks
      change; the random stream is the same). The test over every style's form found two more: cartoon's relief
      (facets 1.4) carved a fin of a column loose, and the stack's relief cap was weighted by the relief's size share,
      so it held only partly (an anime top carved 0.46 m). Now relief on a stack is clipped to [-STACK_BUILD 0.05,
      STACK_CARVE 0.3] m with weight 1 on and in the stack (`Field.build_w` = smoothstep(NEAR, 0, d)). Test:
      test_stacks.py::test_no_piece_detached[style] (realistic + each sheet's `rock.stack`, foot to top, 0.3 m).
    - Not a stack (2026-10-08, branch `stacks-slice`; tiles2's tl2_slice_a regression: 10 triangles floating at
      [291.3, 103.8, 23], 88 m from the nearest stack): in the CARTOON zone the style's big facets (relief facets 1.4,
      size 2.5) built a slab 0.46 m out over a sheer lip with a groove carved under it, a 0.4 m thick piece standing
      clear of the face. In the field before any stack work too (main52); the stack merges only moved the mesh enough
      to show it. Style sheet key `rock.build` (m, terrain_style.ROCK_KEYS; Field._styled_relief: the style's relief
      never builds more than that, carving unlimited); cartoon 0.05 (0.15 still left a speck). Unbuilt-from-relief
      floating slabs could exist elsewhere (anime's proud beds build 1.5 x): not scanned. Test:
      test_terrain_style.py::test_style_relief_build_cap (without the cap the coast's cartoon cliffs build 0.77 m).
    - Open: turf / bird lime on the tops (colour); the anime bands on stacks (terrainstyle); tiles2's solid-stack
      cliff shell on these stacks.

More lessons (plan C, 2026-09-25): measuring the built ground finds build bugs, not just report bugs. Canyon strata were
eroded to 51 deg mounds (now restored after erosion: `terrain_forms.settle`, which also fills hollows it would dam);
basin walls came out 9 deg steeper than asked (sized from the floor's high end: now per stretch from where the floor
meets them); the wall check passed any 2 m step (now the tallest steep run along each outward ray; walls are built
taller by ~0.6 cell of rise because the grid rounds lip and foot). Binary erosion protection makes pillars at its edge:
protect earthworks in proportion (`masks["earthworks"]`). Keeping hard cliff cells from creeping made pinnacles
(scattered hard cells stand): restore designed forms after erosion instead.

**Plan C (agreed 2026-09-25): done 2026-09-26.** C5, the blind round through the tools
(valley, farm, canyon, island; `workspace/c5_*/`), found layouts land and edits are easy, but at eye level none reads as
its brief (smooth caldera walls, dome peaks, no sea or cone, a featureless plateau), plus trust leaks since fixed (see the
Overboard card). Roads are judged as built with earthworks capped at 25 m, so several mountain roads now honestly FAIL:
they need breaks through cliff bands (plan A). Next, in the order the round asked: sea and coast, volcano cone, route
breaks through cliffs, peak forms and wall structure, surroundings beyond the frame.
1. DONE: trust leaks and bugs from round 5 (every report number measured; see lessons above; peaks report how far their
   top stands above the skyline beside/behind them, `min_prominence`).
2. DONE: export (Unity `.raw` + size/position, tree layers out of the splats, masks always, rivers' water, fords, site
   planes in meta).
3. DONE: questions (mixtures "crater + coast", a shape question, what can't be built said first; answers in the
   designer's words matched to options).
4. DONE: MCP tools.
Then maybe A (more forms per kind: sea/coast, cones, lava, canyon breaks) and B (realism: SDF cliffs).

