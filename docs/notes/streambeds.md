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

