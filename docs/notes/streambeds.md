# hifipushie notes: streambeds

Moved out of CLAUDE.md on 2026-10-09 so agents don't load every thread's history.

## Streambeds (2026-10-08, "streambeds" agent, branch `worktree-agent-aaf90ea1699c43e77`)

Joe through pushieworld (their note 110): "streambeds aren't textured right, and they aren't typically empty, they
have clutter and debris, rocks". With real water in the vale river its bed showed: meadow grass and earth, banks
included, nothing in the channel. Renders `workspace/terrain3d_renders/sb_*` (sb_pair_<view>.png = before | after
from the consumer's two cameras, the shallows and above; sb_after_styles_*; sb_up_* the steep upper reach);
references `workspace/level_refs/streams/` (8 CC photos, README); our copy of their spec v8 = terrain `sb_island`.
Scratch DURABLE in /mnt/data/hifipushie/streambeds/: run.sh <script> (this worktree's code, main workspace, capped),
run_base.sh (main 98df684 in base/src), tload.py (the built terrain from a PICKLE: the build cache is keyed on the
code of everything terrain.py imports, terrain_mesh included, so every edit was a 5.5 min rebuild; REBUILD=1 after
changing the 2.5D build), plan.py <terrain> <png> x0 y0 x1 y1 [res] (top-down colour + clutter + report, no export:
30-60 s, the fast loop), xsec.py <terrain> x y (a cross-section's shares, weights, colour), prev.py / rend.py /
views.json (preview_tiles round the river, views with river water and clutter placeholders), sheet.py (the stream
layers in every style + the detail swatches), pair.py, reg.py + cmp.py (pebble cold, branch vs main), tests.sh
(the terrain test files -> tests.log), q*.sh (queues).
- `terrain_stream.py`. `Streams(T)`: grids on the terrain's cells (so the incremental export windows them) round
  every river with water, from `T.river_water_lines` (path, level, half width): `sd` (distance to the water's nominal
  edge), `level`, `energy` (0..1 from the grade smoothed over ~15 m, or `rivers.<n>.bed.energy`), `bend` (signed: +
  inside), `phi` (pool phase: a pool every 6 channel widths at energy 0, 2.5 at 1), flow direction, `ford` (fords,
  routes, sites: left alone). Per point: `shares` (bed = ground under the water's level near the channel; of it
  gravel / silt / bedrock by energy, pool / riffle / bar and noise; `damp` = the bank's foot up to ~0.9 m over the
  water, moist to twice that), `colour`, `relief` (cobble lumps for the maps' normals), `dz` (the bed's shape).
  Hooked in three places only: `Field.__init__` builds it (None without rivers or with `"streams": false`),
  `terrain_ground.Edits` adds `dz` in `column` (so heightmaps, cliff meshes, collision and bakes agree),
  `Materials` appends the layers (`wet_rock` + gravel, silt, bank, LAST) and mixes weights / colour / relief.
- Real grades are no guide on a game level: the island's "farmland river with a ford" falls 95 m in 620 m (9-34%),
  all cascade by Montgomery & Buffington's 1.5 / 3 / 6.5%. Energy reads 0 at 4% and 1 at 30% (`streams.grade`), and
  the designer can say what a river is (`bed.energy`). The report names each reach's character.
- The bed's shape only moves ground that was under water (weight by depth, 0 at 5 cm), stays `min_depth` under the
  level except a bar's top (+10 cm inside bends), nothing at fords / routes / sites. Tests hold all of it.
- Clutter (`terrain_stream.clutter`, rows in clutter.csv with a new `place` column; kinds agreed with the
  "clutterkit" agent, which builds the meshes: river_rock, cobbles (a cluster patch), slab, driftwood, reeds,
  litter; scale = largest plan dimension in m, squash RELATIVE to the asset's own proportions, z = the surface, no
  sink (the old `boulder` rows stay sunk 0.12 x scale: said per kind in the manifest's `clutter.kinds`)). Candidates
  on a lattice anchored at the world's origin with hashed jitter (a block's rows are the level's rows), kept by
  probability from energy / pool / riffle / bar / bend / depth, rocks and logs thinned greedily by size (spacing
  follows size: no comb), logs afloat against the upstream side of big rocks lying across the flow, or stranded on
  outer bends and bar heads along it; reeds only on slow margins.
- Styles contract 5: gravel / silt / bank in every sheet, new op `stones` (round discs sized by their nearest
  neighbour + a smaller fill generation; Voronoi cells read as cracked mud). Detail swatches `cobble_swatch`
  (ellipsoid domes, small first so big stones lie on top) and `silt_swatch` in `ground_detail.swatches`.
- Renders: `render_tiles` draws the rivers' water (a ribbon per river at its level eased along the path: the raw
  level has steps of a few dm where a bank holds it down, a staircase as a ribbon; 45% of the Fresnel mirror so the
  bed shows at eye level) and the stream clutter as placeholders (`blender_terrain._stream_piece`).
- What misled on the way: the damp band "missing" in renders was there in the maps (xsec.py) but a metre wide on a
  30% bank under tall-grass placeholders; a `st` variable shadowed in `Materials._weights`; logs placed on the bed
  lay sunk under a metre of water (now at the surface); `swatch_sheet` takes SHEETS, not the resolved style dicts.
- Read (blunt): from the consumer's cameras the channel now reads as a cobble stream bed with boulders, a few
  logs and reeds, darker fines in patches; the steep upper reach is a boulder-choked torrent. Weak: the cobble
  swatch's relief is "bubble wrap" at grazing angles and the same from bank to bank; pools / riffles / bars barely
  read by eye (this river hardly bends: bend 0.65 at most on the lower reach); the styled (pixar) bed in the Blender
  recipe is flat speckle (albedo only); placeholders are eggs and pool noodles until clutterkit's meshes; the
  water's level steps are the terrain's own (not touched); no undercut outer banks (a heightfield can't), no lake
  shores / beaches yet (pebbles, wrack: same machinery, next).


## Rounds 2-3 (moved from CLAUDE.md at the 2026-10-09 merge)
- Round 2 (2026-10-09, the coordinator on sb_ref_*: "reads as a stream now"; still fake: banks as smooth bare ramps
  the same both sides, cobbles bank to bank, pools / riffles not reading, level steps, styled bed albedo only).
  - Banks (`Streams.cut`, `dz`): the bank's foot is shaped too. Outer side: the graded ramp cut back to a step
    (`cut` 0.35-0.85 m x channel size; everything lower than the cut's height within `0.5 + 2.4 x height` m of the
    nominal edge drops to 0.2 m under the water, the face a riser `cut_riser` wide; by height alone, on flat land
    lower than the cut the channel widened to the zone's edge); inner side: the ramp's foot laid flat into the bar
    (dry gravel above the water: `dry` in `shares`, counted as bed). The cut face is bank layer / bare damp earth,
    darkest under the turf's edge. A heightfield can't overhang: ~1 m wide step in the ground mesh, crisp in maps.
  - Alternate bars: the vale river hardly bends (tightest bend 0.4 of a full one), so real bends gave no bars. A
    `side` grid (+-1 by bank, 0 mid-channel) and `alternate` 0.75: the effective bend = the path's own minus
    side x sin(pi x phi), so pools sit against one bank then the other, a bar and the gentle bank opposite, as in a
    straight channel; real bends override. The report says when a river hardly bends and what the designer can do.
  - Sorting: `coarse` (along the thalweg, toward the outer bank) drives stone contrast, fines at the inner margin
    and in 3 m patches (silt layer), a few slabs awash on riffles, more moss at the water line; cobble swatch with
    fewer, flatter stones (gravel shows between). Pool 0.8 m, riffle 0.6.
  - Bank vegetation rows: kind `sedge` (tussocks along the wet margin and bank foot, denser inside, a fringe on a
    cut bank's top) and `bush` rows with place bank (clumps on the bank top).
  - LEVEL: `terrain_forms._ease_level` (in `water`, the 2.5D build): the level, min of the profile and the banks
    - 0.3 then a running min, dropped up to 2.45 m in one 2 m sample and ran level between (67 of 279 samples
    level). Now a smooth curve hung under the steps (60 x small Gaussian + cap, ends carried on at their own slope:
    held level, the source end sagged 5.8 m), falling everywhere: largest drop per sample 0.73 m, 0 level samples,
    lowered by 0.46 m on average / 2.35 m at the tallest step. One wide smoothing shifted under the steps sank it
    4.3 m. CONSUMER: river levels (meta `rivers`, manifest `streams.rivers`) and the bed heights under them change
    by those amounts on every terrain with rivers.
  - Incremental: `Streams.report_reaches` (whole-river arrays for the report) is in the fingerprint's SKIP_ATTRS;
    as `reaches` it made any river edit a global change. `"streams": {...}` numbers are scalars: global (cold).
  - Styled beds: the style layers always had normal + height maps; the Blender styles recipe leaves bump off (an
    earlier round's contour lines), so my render was albedo only. `render_tiles(styles_bump=True)`; stones taller
    in every sheet (0.045-0.1 m). `terrain_style.ground_view(sheets, refs, path, layers=("grass", "gravel"))` IS a
    styled look with normals and layer_edge: sb_styles_ground*.png (all five styles: stones in each style's
    language).
  - The cut bank in the ground mesh: the heightmap tiles sample the ground every metre, so a 0.35 m riser was a
    sawtooth of pale triangles along the bank; `cut_riser` 0.9 m in the mesh (a steep ramp), crisper in the maps.
  - Shores (`terrain_shore.py`): lakes (not the sea) join the Streams grids as STILL water (`still` grid: no pools,
    bars, cut banks, bed shape; bed gravel by the shore and silt from ~3 m in; reeds, sedge, cobbles, a few rocks at
    the margin; names "lake <name>"), so a terrain with a lake and no river also gains the layers. Sea beaches:
    `beach_clutter` (kinds pebbles, wrack, driftwood, place shore) where the tiles paint sand 0.15-3.4 m over the
    sea, wrack on terrain_ground.tint's own wrack line (same noise, seed 641). `terrain_stream.all_clutter` = both.
  - Checks: river block (6 tiles, every LOD) 0 failures; incremental on a river edit (energy along the whole river,
    36-tile block): 24 tiles redone, 0 of 998 files differ from a cold export.
- Round 3 (2026-10-09, "streambeds2" agent took the thread over; renders `terrain3d_renders/sb2_*`; scratch adds
  sw.py (the cobble swatch lit high and grazing), run_main.sh (main's src in mainsrc/), q9-q13.sh, rend.py BUMP=1).
  - Pools and riffles did not read because there was less than ONE in any view: spacing 6 channel widths on an 18 m
    river is a pool every ~110 m. `spacing` [2.5, 1.5] (a level compresses a river's length, not its width),
    `riffle` 0.85 (the crest keeps ~0.2 m of water: stones awash; at 0.6 a "riffle" was 0.6 m deep). Dry gravel on
    bars is PALE (x1.38 of the layer colour, wet x0.88): in the photos the bar is the brightest thing in a channel.
    With sides alternating every few widths the bank's foot is damp earth on one side and bar gravel on the other
    (test_streams' foot assertion changed to say so).
  - "Bubble wrap": two things. The baked relief was fbm ** 2 at one strength over the whole gravel layer; now
    flat-topped lumps on a threshold (stones standing on gravel), their share and strength from the bed's own
    sorting (`shares` inside `relief`: coarse thalweg and riffles rough, pools / inner margins / fines nearly
    smooth) and a 2.2 m boulder octave on steep reaches. The cobble detail swatch: stones in drifts with plain gravel
    between (a periodic density field), each sunk to its own depth and tilted, more elongated.
  - Styled beds in Blender: `render_tiles(styles_bump=True)` rendered the ground BLACK: a Bump node over the summed
    heights of every layer of every style = Cycles out of SVM stack (the skin thread's lesson again). Now the soft
    (top-projected) layers' NORMAL MAPS are added as a tilt to the surface normal; height images are no longer loaded.
  - Lake water in tile renders: strips over the lake's own wet cells at its level (a sheet over its box hung in the
    air beyond a dam). Render only. A lake's damp foot is 0.45 of a river's (a 3-4 m bare brown drawdown ring).
  - Pushieworld's verdict in the game (their note 114; pictures pushieworld docs/img/streambeds/): GOOD (cobbles
    through the water, damp foot, rocks and wood sit right); asked for water that flows round the rocks, rocks that
    don't read as garden stones, bank-to-bank variety, banks that aren't ramps. Their export predates round 2 (no cut
    banks, no alternate bars).
  - clutter.csv `csv_version` 2 (batch announced through the coordinator, agreed with clutterkit2): columns `water`
    (m, the water surface minus z; empty on dry ground) and `sink` (m the pivot goes below z) after `place`; manifest
    `clutter.columns` / `csv_version` / `kinds.<k>.footprint` (plan axes and height as shares of scale: the kit's
    realistic means, river_rock 0.44 above the pivot, slab 0.27). Rows in code are 11 wide (`terrain_stream.COLS`:
    ..., place, river, water, sink). NO "rocks as height" raster: the heightmaps are 1 m cells and the rocks 0.35-1.8 m;
    a consumer's water sim stamps rows itself from the footprint. A third of the river rocks sink 0.2-0.45 of their
    height, sizes follow riffle / pool, steep reaches get slabs in the channel and fewer round rocks.
  - Kaze tile 3,16 at 127,497 triangles for 12,000 (LOD 0) in the island export: main's own (the block (2,15)-(4,17)
    reads the same number with main c3d50e1's code); not a stream fault. For the tiles thread.
  - "cartoon gravel wrap seam 1.48-1.53": the seam row's step (4.3 levels) lies inside the spread of ORDINARY rows
    (mean 2.9, p95 4.0, max 5.8; realistic gravel the same picture: 3.9 against p95 3.8, max 4.5): no visible seam, the
    one-row measure is noisy on flat-toned stones with ink outlines. Left as it is; the check would be fairer against
    a high percentile of rows than their mean.
