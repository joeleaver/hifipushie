# Terrain: stream beds

Read guide(topic="terrain") first: describe the brief, then write the spec.

## Stream beds: what lies under and beside a river's water

A river's bed is never the meadow carried on under the water, and it is never empty. In the 3D tiles every river
with water gets a bed, a damp bank and clutter, made from the river's own path, level, width and grade. Nothing to
write for the default; the numbers below steer it.

**What real streams look like** (what the rules copy):
- **Bed material follows energy** (the grade). Montgomery & Buffington's reach types (GSA Bulletin 1997;
  [the paper](https://fs.usda.gov/rm/boise/publications/watershed/rmrs_1997_montomeryr001.pdf)): *cascade* (over
  ~6.5%: boulders and bedrock, tumbling water), *step-pool* (3-6.5%: rows of boulders across the channel with a
  plunge pool below each, one to four channel widths apart), *plane-bed* (1.5-3%: an even bed of cobbles and
  gravel), *pool-riffle* (under 1.5%: shallow coarse riffles and deep fine pools alternating every 5-7 channel
  widths, bars beside them), down to sand and silt where the water is slow. A game level's river is far shorter than
  a real one for the same fall, so its grades are several times steeper than its character: the rules read energy 0
  at a 4% grade and 1 at 30% (`"streams": {"grade": [0.04, 0.30]}`), and you can simply say what a river is (below).
- **Bends sort the bed.** The fast water runs against the OUTER bank and cuts it (a pool at its foot, a steep or
  undercut bank); the inside of the bend is slack and a bar of gravel and cobbles builds there, awash or just dry.
- **The wet margin.** The bank's foot is damp and darker for a hand or two above the water; stones at the water
  line carry moss and algae; under the water everything is darker, and pools collect fine dark sediment.
- **It is full of things.** Boulders (the big ones standing proud of the water, in clusters and rows, never evenly
  spaced or one size), cobble patches on bars and riffles, flat slabs along steep margins, driftwood caught on the
  upstream side of boulders and stranded on outer bends and bar heads, reeds and sedges along SLOW margins (never
  in a torrent, rarely on the cut outer bank), leaf litter in the slack.
- **How environment artists build it:** the bed's form first (it sells the river more than the water shader
  does), a bed material blended by a flow / wetness mask from wet silt and gravel up to dry soil, a small kit of
  rocks, pebble clusters, logs and bank plants scattered densest in the shallows and along the mask's edge, the wet
  zone darkened and glossier last.

**What the tiles carry** (when the spec has rivers with water; nothing changes on a terrain without):
- three more ground LAYERS, last in the layer list (so a terrain with rivers has a third weights group and the
  older layers keep their channels): `gravel` (cobbles and gravel under the water and on bars), `silt` (fine sediment
  in pools and slack margins), `bank` (the bank's damp foot); bedrock in the bed is `wet_rock` (present on any
  terrain with rivers). They are in the weights, base colour, roughness and the baked relief, each has a tiling detail
  swatch (`ground_detail.swatches`: packed cobbles; silt with pebbles and flecks) and a texture in every terrain style
  (styles contract 5).
- the bed's SHAPE in the heightmaps, cliff meshes and collision: pools deeper (against the outer bank), riffles
  shallower, a bar rising on the inner side (its top a few cm over the water), an uneven bed; sorted across the
  channel (coarse along the thalweg, fines toward the inner margin and in patches).
- the BANKS' foot: on the outer side the terrain's graded ramp is cut back to a low near-vertical step (0.35-0.85 m
  x the channel's size: bare damp earth, darkest under the turf's edge, the turf ending at its top, the water at
  its foot); on the inner side the ramp's foot is laid flat into the bar (dry gravel above the water). On a straight
  reach the sides ALTERNATE with the pools (the thalweg wanders from bank to bank: alternate bars), so even a river
  drawn as a gentle curve has bars and cut banks; a real bend (a radius of 2-4 channel widths: more `through`
  points) puts the cut bank on its outside. Ground above the cut, fords, routes and sites keep theirs, and the
  water's level is the river's own (never raised). A heightfield can't overhang: the cut is a steep step about a
  metre wide in the ground mesh, crisp in the baked maps.
- the river's water LEVEL is eased along its path in the terrain build (smooth, falling all the way, nowhere above
  the level a low bank allows): it used to drop a few dm to 2 m within one sample and run level between (a
  staircase for any water drawn or simulated on it).
- `clutter.csv` rows with a `place` column (`water` | `margin` | `bank` | `bar`; empty for the dry kinds): kinds
  `river_rock` (rounded boulders 0.35-1.8 m), `cobbles` (a patch of 5-15 cobbles, 0.6-1.6 m), `slab` (flat bank
  stones), `driftwood` (0.8-4.5 m; yaw = the log's long axis), `reeds` (clumps 0.5-1.4 m), `litter` (leaf and twig
  patches), `sedge` (tussocks along the wet margin and the bank's foot: denser on the slow inner side, a fringe
  along a cut bank's top) and `bush` rows with place `bank` (scrub on the bank top, in clumps). `scale` = the piece's largest plan dimension in metres, `squash` = its height relative to the asset's own
  proportions, `z` = the bed or ground under it. The manifest's `clutter` section names every kind with its ranges
  and the counts per river; `streams.rivers` gives each river's path with level, width and energy.
- two more columns after `place` (the manifest's `clutter.columns` lists them, `clutter.csv_version` is 2): `water`
  = the water surface's height minus the row's z in metres (> 0: the piece stands in that much water, so an engine
  darkens it below z + water; < 0: that far above the water; empty on dry ground) and `sink` = metres its pivot goes
  below z (about a third of the river rocks lie 0.2-0.45 of their height in the bed; empty = 0). Rocks are sorted
  along the channel (bigger on riffles and steps, smaller in pools) and steep reaches carry more `slab` rows.
  `clutter.kinds.<kind>.footprint` (`{"shape": "ellipsoid", "plan": [1, 0.85], "height": 0.44}`: shares of scale,
  the height x squash, over z - sink) is what a water simulation stamps per row at its own resolution: the tile
  heightmaps hold none of these pieces (1 m cells; the pieces are their own meshes and colliders).
- wood the water goes round (csv_version 3): `snag` (a fallen stem 2-6.5 m, 0.14-0.4 m thick: its top on the bed
  in the water, leaning up onto the bank where it comes to rest, pointing downstream; outer bends, and a few per
  10 m on steep wooded reaches near trees) and `limb` (a branch 1-6 m, 0.05-0.2 m: across the current on a
  boulder's upstream side, on a bar's head with its end in the shallows, or wedged bank to bank over a narrow
  channel). Seven columns at the END of the row, empty for every other kind: `x0,y0,z0,x1,y1,z1,diameter` (the
  capsule's axis ends, end 0 the lower; each end a radius over the bed or bank it rests on, nothing of it inside the
  ground, the rock or a boulder row's footprint); the footprint is `{"shape": "capsule"}` along that axis. A v2
  reader that reads by header keeps working.
- the export's notes say each river's reaches by character and its clutter ("stream clutter vale_river: 99
  river_rock, 205 cobbles, ... (23 of 76 rocks in the water stand proud of it)"), and WARN when a river has none.

**Steering it:**
- `rivers.<name>.bed = {"energy": 0.1}` says what the river IS whatever its grade (0 a slow silty lowland stream with
  reeds; 0.3 a gravel riffle-pool stream; 0.6 cobbles, boulders and steps; 1 a boulder and bedrock torrent); a list
  runs from source to mouth (`[0.9, 0.5, 0.15]`).
- `"streams": {"pool": 0.8, "riffle": 0.85, "bar": 0.10, "lump": 0.07, "damp": 0.9, "cut": [0.35, 0.85],
  "alternate": 0.75, "clutter": 1.0, "shape": true, "spacing": [2.5, 1.5]}`: pool depth (m, scaled by the channel's
  size), how much of the depth a riffle takes back, a bar's top over the water, the bed's unevenness, the damp band's
  height on the bank, the cut bank's height range (`[0, 0]` = banks as graded), how strongly the sides alternate
  along a straight reach (0 = only real bends sort the bed), clutter density, the shape on / off, pool spacing in
  channel widths at energy 0 and 1. `"streams": false` = the river as it was before
  (grass to the water, nothing in it).
- Reeds want a slow reach: if the report calls a reach you meant as a meadow stream "cascade", set its energy.

**Lake shores and beaches** use the same machinery. A lake (not the sea) is still water: its shallows' bed is gravel
and pebbles along the shore (in patches) and silt from a few metres in, the shore's foot is damp, and its margin
gets reeds (in stands, with gaps), sedge, cobble patches, a few rounded rocks, a little driftwood and litter; no
pools, bars or cut banks, and its bed's shape is the terrain's own (`"streams": {"lakes": false}` = rivers only). A
sea beach (wherever the tiles paint sand above the water near the coast) gets `pebbles` (patches on the shingle up
the beach, thin lower down), `wrack` (strips of weed and drift lying along the high water mark, where the sand's
colour already draws the wrack line; yaw = along the shore) and `driftwood` above that line, all with place
`shore`. The notes count them ("shore clutter (sea beaches): 150 pebbles, 87 wrack, 6 driftwood"; "stream clutter
lake pond: ...").
