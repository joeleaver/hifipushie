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

## Round 4 (2026-10-09, "streambeds3": merged main's slim CLAUDE.md, verified the csv_version 2 batch)
- The batch (befcc0b) is the delivery: clutter.csv `csv_version` 2 (`water`, `sink` after `place`), manifest
  `clutter.columns` / `csv_version` / `kinds.<k>.footprint`; styles contract stays 5. Row check (scratch vrows.py) on
  the river block: river_rock in water n=244, water 0.05-1.9 m (median 0.29), every one sunk (sink/scale 0.02-0.24,
  a third deep); slabs on margins / riffles sunk 0.02-0.07 x scale; cobbles in water / on bars / margins; driftwood in
  water lies at the surface (water = 0.06 on all 30: lodged floating, never on the bed, by design).
- Pebble (no river) cold vs main: every mesh / map identical; clutter.csv + manifest differ only by the two new
  columns and the sea-beach rows (pebbles 118, wrack 7, driftwood 4); main's boulder / bush rows identical on their 8
  columns.
- Fix: a one-tile block export (`only` one tile, no shared borders) crashed: the placeholder border key had Fa == Fb,
  0/0 -> a NaN vertex -> `fieldjit._blocks_tables` OverflowError. `terrain_mesh` border vertices now take t = 0 there.
- Still wrong (judged on sb2_shallows): placeholder egg rocks (smooth, one colour: the consumer's "garden stones" is
  the kit's asset look, no csv field for wet / angular yet); the cobble bed swatch still reads alike bank to bank in a
  close view; logs float at the surface everywhere (none half-sunk in the bed).

## Rivers on existing ground cut their own valley (2026-10-09, "streambeds3"; pushieworld note 115)
- Cause: a river's bed is a low pin of the harmonic base (floor field). crown_beck (bed heights read off the final
  ground, down the volcano's flank) pinned the floor at 99-172 m where it had been ~seabed, and the volcano then stood
  on the raised base: +69 m, 122 ha (our numbers at the base stage: 143 ha > 5 m, max +74; divides part of it).
- `Terrain._river_base`: a probe solve without the auto rivers; a river CUTS (excluded from the solve and divides,
  its valley cut in after: floor at its bed, sides at clip(profile side grade, 0.3, 3), smooth-min shoulder ~6 m,
  only lowers, floor cells join `_fixed_river`) when it runs over a volcano / lone hill (median height of those forms
  under its path > max(5 m, 0.15 x its fall): `_before_forms` = H before volcano/hills) or its bed follows the ground
  made without it (|median gap| < 5 m) and it isn't in a basin. `valley.cut` true/false forces it. Report line per
  cutting river; the trench warning allows the cut's own sides (grade x offset).
- Regression (base-stage H, before vs after, max |d| 0.0): b2_alps, gdamp_river_world, gdamp_tarn_coast, t2_alps,
  t2_farm, t3_alps, t3_coast, t3_farm, tl2_island7, tl2_slice_a, island (pw_island_base). A first rule ("bed not above
  the ground made without it") cut alpine / gdamp valley-making rivers (changes up to 1.4 km): don't.
- pw_island_rivers: crown_beck, downs_brook (over the volcano / knolls) and kaze_burn (bed = ground) cut; raised
  > 5 m: 0.5 ha, all at pencil_spout, whose bed runs ~32 m ABOVE the headland's ground (pinned: it makes land there).
- Unknown river keys: report warning (`RIVER_KEYS`). Test: tests/test_river_cut.py (ground beyond 2 valley widths
  unchanged at the base stage).
- Scratch: rbase.py (raise/lower by distance band between two specs), hsave.py / hreg.py + hcmp.py (base H old vs
  new; run_main.sh = mainsrc/ = this branch before the change), specs copied as workspace/terrain/pw_* (theirs).

## Waterfalls (2026-10-09, "streambeds3"; terrain_falls.py)
- Spec `rivers.<r>.falls: [{"at", "drop", "width"?}]` (Pushieworld drafted exactly this). Profile: the drop comes out
  of the reach below the lip (compressed to the next fall / mouth; the river above keeps its heights); too little
  left below (at 1, a sea cliff) -> the reach above is raised evenly. First version took the drops out of the whole
  river and raised the reaches above by up to the drop: on ground-following rivers the lip stood in the air, the bank
  rule pulled the water down and 4 of 8 island falls came out 0-2 m.
- forms.water: grade without the steps (a fall isn't a torrent), the bank rule lifted round each lip (guard), easing
  per reach, `step_levels` keeps each step in the WATER (lower below the lip down a 1% line until it meets its own
  level, never under the mouth's): a gorge below the fall where the ground was low. `stamp` on the finished ground
  (both water passes): amphitheatre (pool's edge + 1:1 sides) below, lip band across the valley at the upstream level
  (Wz = half width + max(4, 0.8 drop)), shallow sheet over the lip, plunge pool (r = clip(0.5 w + 0.15 d, 0.6 d, ...),
  depth clip(0.25 d + 0.8, 1.2, 6)), face + lip hard (hardness 0.03). Face = one cell: 80-88 deg at 0.5-2 m cells for
  drops over ~6 m; the report warns under 60 deg and when the ground can't hold the drop.
- Meta: meta.json `falls` + `falls_note` (only when there are falls), tiles manifest `falls` {falls, note}: lip line
  (2 xyz at the lip's water level), drop, asked, width, flow, pool {xyz at its level, radius, depth (null in the sea)},
  into river | lake | sea.
- Streams: `plunge` / `foot` grids (only with falls): pool form forced, river_rock ring round the pool (bigger),
  slabs at the face's foot. Vocabulary: "waterfall" no longer a limit (cascade = several falls).
- pw_island_rivers: vale 6.0 (asked 6, 72 deg), crown 16.8/15 (83), 10.6/10 (80), 1.6/6 (lip 2 m over the sea: the
  ground can't), kaze 13.1/12 (81), 17.2/25 at 0.97 (the cliff is ~20 m), downs 8.0/8 (74), pencil 2.6/10 (bed drawn
  over low ground near the cove). Tests: tests/test_falls.py (inland 3 + 12 m, sea cliff 30 m, clutter, errors).
