# Vegetation: small plants (grass, ferns, flowers, groundcover, palms)

Read guide(topic="vegetation") first: describe the reference before choosing a preset.

## Small plants: grass, ferns, flowers, groundcover, palms (assembled, not grown)

Game foliage artists do not grow a grass tuft: they make a few PICTURES (a fan of blades, a frond, a flower head),
cut each onto a card as tight as its outline, and ARRANGE cards in a clump; clumps are scattered by the thousand.
So a small plant here is `"plant": "clump"`: `leaves` (+ `leaves.parts`) are its pictures, `clump.layers` its
arrangement. Everything downstream is the tree's: `grow_plant`, `look_plant`, `export_plant` (budgets, LODs, wind),
sets (`set: {"count": 5}` = variants to scatter). Presets: `meadow_grass`, `fern`, `daisy`, `clover`, `feather_palm`;
`shrub` is GROWN (a tree with `habit.stems` 6: bushes branch like trees). `get_plant(species="fern")` shows a
preset's pictures and layers with what each layer key means.

Stages, as for a tree: (1) reference: height, spread, what the eye reads (a shuttlecock of fronds; white dots over a
green mat); (2) the pictures: look at the atlas (`look_plant` shows it for a clump); a picture must read by its
outline; (3) the arrangement: layers; (4) the look from standing height AND from above (that is how small plants are
seen); (5) the export at 50-600 triangles a plant.

```json
{"species": "daisy", "seed": 3,
 "leaves": {"parts": {"head": {"twig": {"flower": {"petals": 13, "color": [0.95, 0.8, 0.2]}}}}},
 "clump": {"size": 1.2, "layers": [
   {"name": "rosette", "part": "main", "count": 7, "ring": [0, 0.02], "lean": [62, 84], "facing": "up"},
   {"name": "stalks", "part": "head", "count": 4, "ring": [0, 0.04], "lean": [4, 20], "stem": [0.2, 0.36], "tilt": 78},
   {"name": "leaves", "part": "stemleaf", "count": 8, "on": "stalks", "along": [0.15, 0.7], "lean": [30, 60]}]}}
```

Layer keys: `part` (which picture), `count`, `ring` [m, m] from the middle, `lean` [deg, deg] off upright (0-25 a
standing tuft, 30-65 arching fronds, 70-90 a rosette on the ground, over 90 hanging), `scale`, `facing` ("up" =
the card's face to the sky: fronds, rosette leaves; "any" = standing cards turned any way: grass), `stem` [m, m]
(a stalk carries the card at its top; `stem_radius` 0 = the stalk is not drawn: leaves seen from above), `bend`,
`tilt` (90 = the card lies across its stalk's top: a daisy's head, a clover leaf), `on` + `along` (stand on another
layer's stalks: a palm's fronds on its trunk, leaves up a flower's stalk), `trunk` (the stalk is a barked trunk),
`clump.size` (the whole plant's scale). In a `grow_plant` patch `clump.layers` is replaced whole.

Pictures: `leaves.shape` "linear" (grass blade) / "strap" / "round" / "petal" besides the trees' shapes;
`twig.arrangement` "basal" (every leaf from the foot: a tuft) or "pinnate" (pairs along the stalk, `taper`: a
frond); `leaves.bend` (blades arc); `twig.flower` {form "ray" | "cup" | "spike", petals, radius, color, center};
`card.strips` 4-5 for long arching fronds (the card bends with `twig.droop`). `leaves.parts` = {name: overrides}.

What the practice is, and where it comes from: cards in clumps, normals pointing UP (or taken from a dome) so a
clump shades with the ground instead of flickering card by card (polycount's foliage threads; here
`leaves.normals: "up"` is the default for clumps); few distinct assets per ecotope, scattered by density maps
(Guerrilla, "GPU-based procedural placement in Horizon Zero Dawn", GDC 2017); grass in clumps that share height
and lean, wind by height along the blade (Sucker Punch, "Procedural Grass in Ghost of Tsushima", GDC 2021). Wind
here: each card bends from its foot in its own phase; long cards swing further.

What goes wrong: cards all upright in a tight ring read as a shaving brush (widen `lean`, add an outer layer of
shorter, flatter cards); a rosette that floats (lean 70+, `sink`); one picture repeated reads as a stencil (3-4
`card.variants`); thousands of triangles in one tuft (the report warns over 3000; scatter wants 50-600: export the groundcover grade below).
Not built: scattering on terrain, grass as GPU blades, ivy and creepers that follow a surface, fan palms, bamboo,
reeds in water, mushrooms, per-plant colour maps from a terrain, bent/trampled states.

Through the year (`"season"` on the spec, the export's season variants; realistic and styled alike): a clump has
states, `clump.seasons` = {"spring" | "summer" | "autumn" | "winter" | "snow": {"color": [r, g, b] or {"mix": [r, g, b],
"amount": 0-1} (what the leaf colour goes to), "flatten": 0-1 (how far the cards lie down: winter grass), "scale"}},
merged over the defaults (spring: fresher and 0.8 the size; autumn: toward straw; winter: brown straw, flattened 0.6,
0.85 the size; snow = winter under snow). A layer shows only in its own `"seasons": ["summer", "autumn"]` (seed heads,
flowers in their months; default: always). A plant that isn't `leaves.evergreen` has died back in winter unless it
sets a winter state. In looks the plant is assembled in its season (flattened, smaller, layers gone). In the EXPORT
the geometry is the summer plant's and a season is a material variant: its colour, and the pictures of layers out
of season blanked in that season's atlas (styled: the `heads` slot hidden); flatten and scale are not in the file
(an engine can lean the cards by the wind channels; said in the reply).

### A field of grass: the sward (`"species": "sward" | "sward_mown" | "sward_rough"`)
Tufts scattered on a grid read as tufts on bare ground, not as a field. Plain grass is a SWARD: a 2 m TILE of blades
(no seed heads, no stalks), tiles laid edge to edge. What engines do: blades, not clumps: Ghost of Tsushima draws
~100k instanced blade ribbons in tiles round the camera, thinned and widened with distance, and past the grass
distance the terrain's own grass texture takes over in the same colour (Wohllaib, GDC 2021); card patches (alpha
quads with blades painted on) are the older way. Measured here in Godot with the game's shader (meadow, realistic,
standing at 1.7 m): card patches at 7 cards / m2 hide the ground as well for a third of the GPU time, but from 2-8 m
they read as a maze of little hedges (you see every card's line); tufts on the game's 0.9 m grid hide 10-40% of the
ground; blades hide 38 / 78 / 94 / 100% at 2 / 6 / 12 / 30 m. So: blades.
- `sward` keys: `variant` mown (4-6 cm, 1100 blades / m2) | meadow (14-30 cm, 520) | rough (22-55 cm, 380, straw
  mixed in), or the numbers themselves: height [lo, hi], density, width, lean [lo, hi] deg, bend deg, drift (share of
  blades leaning with the tile's combed direction), clump (patchiness), dry (share of straw blades), tone [lo, hi],
  ground / tip / straw colours, size (the tile, 2 m), lods [[share of blades, width x, segments], ...], rings (m: LOD k
  inside rings[k]), fade [start, end] m. Unknown keys are refused.
- Tileable by construction: roots jittered on a torus, every variation periodic noise over the tile; blades lean out
  over the edge into the neighbour. Place with random quarter turns, no random scale, no thinning.
- LODs are subsets of the same blades, wider so the ground covered stays about the same (share x width = 1): near 3
  segments a blade, from the second ring one triangle. Undersides are triangles of their own (normals never point down:
  an engine's back-face flip made black blades). The four meshes only bound the vertex count: what is DRAWN thins PER
  BLADE in the vertex shader (each blade has a rank; as the share for its distance passes the rank it sinks into the
  ground and the blades left widen), so LOD k's mesh at its ring draws exactly what LOD k - 1's draws there. Switching
  whole tiles showed as darker tile-aligned squares from above. Recipe + numbers in the seasons json `sward.lod`,
  channels TEXCOORD_4 / TEXCOORD_5 (reference shader lines ship in the repo's spikes/godot_veg/sward_blades.gdshaderinc); pick a tile's mesh by
  its NEAREST point. Realistic meadow: 5,000 / 1,200 / 210 / 54 triangles per m2, rings 5 / 12 / 24 m, fade to 60:
  2.0 M triangles round the player (was 3.4 M with rings 8 / 20 / 35 at the same ground hidden: 38 / 76 / 94 / 100% at
  2 / 6 / 12 / 30 m); pixar 2.2 M, anime 1.5 M, cartoon 0.8 M, blobby 0.7 M. The rings are the lever.
- The far end: past `fade.start` the engine shrinks the blades into the ground; from `fade.blend_from` (the second
  ring) to `fade.end` their albedo, NORMAL and roughness go to the ground's (a blade lit by its own normal is lighter
  than flat ground of the same colour, and a specular style shows roughness as a sheen: either left an arc where the
  field ended). Root colour = the terrain style's grass colour of that cover kind, through the plant style's `colour`.
- How a sward ENDS (a path, a pad, forest floor): never by leaving tiles out (a 2 m staircase). The engine gives a
  density 0..1 per blade (the terrain's grass weight at its world xz, or four corner values per tile); the same
  per-blade threshold thins them and they shorten toward the edge (`sward.density`; the blades left do not widen).
- Seasons: each season's factor is the TERRAIN style's seasonal tint of the grass (turf for mown) layer, so blades and
  ground turn together (whole in the json, may exceed 1). Winter is lying straw, not a tint (`sward.winter`: blades
  laid over along a direction that drifts over the world, shorter; laying each blade along its own normal tore
  blades). Snow buries the tile (`sward.snow`: it sinks by the snow depth, tips poke through in straw, the fade colour
  is the snow's); the old snow variant was summer blades tinted pale blue: a green field on white ground.
- Opaque geometry: no alpha, no texture, no mipmaps to set up. Wind = every plant's channels; `sward.wind` says how to
  run gusts across tiles. `sward.renderer` in the json = the six steps of a tile renderer (grid, quarter turns, LOD by
  nearest point, shader order, colour, what the terrain draws under it).
- Styles (sheet block `sward`: width, density, height, bend, tones, tip point | round, tuft + tuft_fan, round, dry,
  tip_light, taper, drift): blobby = few fat round-tipped blades in two tones; cartoon = broad pointed blades in fans
  of three; anime = long sweeping blades in three painted steps, light tips; pixar = a tenth more, slightly finer blades (half again as many cost 5 M triangles).
- Judge it as a FIELD in an engine, never as one tile: tiles over 60 m with their rings and fade, at eye level and
  25 m up, the ground in the terrain's grass colour; measure ground hidden by distance, triangles, GPU time. `look_plant` refuses a sward for that reason.
- Not built: flowers / seed heads mixed into the tile (scatter the groundcover-grade tufts over it), trampling,
  blades following a slope's normal (tiles are flat: fine to ~20 deg), seasons beyond a colour per season.

### Groundcover grade: the same clump for scatter (`export_plant(name, grade="groundcover")`)
(`<name>_seasons.json` says `"grade": "groundcover"`, the triangles per LOD and the mip-scaled alpha recipe: Godot drops material extras. NOT for every plant: the export refuses ferns (a rosette of a few broad arching fronds lies flat or turns into a thicket of strokes on a star of cards, and the full fern is 172-900 triangles), and a realistic daisy keeps 0.17 of its area (thin stalks; its full plant is 406 triangles): where the full plant is under ~1,000 triangles, scatter the full plant.)
A meadow scatters thousands of clumps round the player; the full small plant (270-4,750 triangles at LOD 0, pixar
grass's lush thin blades the most) is a hero asset. What game artists do for scatter: build the clump once at full
detail and BAKE it onto a few cards (SpeedTree / Megascans grass billboards); the far tier a few crossed cards. Here the
bake is the plant exactly as its full export draws it, in its style and in every season, so each style reads as itself.
- Tiers (LOD 0 / 1 / 2): 8 / 5 / 3 vertical cards through the foot (512 / 192 / 36 triangles with a grass's heads; a
  card is a grid that bends with the wind, front and back their own faces). Each card shows only what stands in its own
  wedge round the foot, square on: every blade is drawn ONCE, near where it really is (crossed cards that each show the
  whole clump draw it n times, doubled where they cross). Parts are kept whole (a blade, a leaf) when they point one way
  from the foot; a fan joined at its root is cut by pixel. Flower / seed heads (compact parts high on the plant,
  gathered into heads) get two small crossed cards each (a round head on a wedge card seen along it is a sliver); a
  low wide plant (clover, a fern's rosette) also gets a card lying flat, baked from above.
- Pictures: rendered 2x and averaged (a thin blade's coverage is its alpha; drawn from 0.28 coverage), the clump's shade
  baked in, a tangent-space normal map; each tier at the size it is seen at (448 / 128 / 64 px). Normals lean up (the
  ground's light) and toward their own face (straight up, a card seen from the side caught the styles' rim light).
- Seasons are variants of the one `foliage` slot (winter = the plant regrown lying, snow = winter under snow); no bark /
  heads slots: stalks and heads are in the pictures. Files in their own folder (default export_groundcover/):
  <name>_LOD0..2.glb, <name>.glb, <name>_seasons.json. First export ~5-10 min of Blender (cached by the spec).
- ENGINE, alpha through mipmaps: plain mipmaps average a thin blade with the air beside it and an alpha test drops it
  (pixar grass LOD 0 lost 93% of its area by 12 m in Godot). Import the textures WITHOUT mipmaps (coverage holds,
  some shimmer), or WITH them and alpha scaled up by the mip level in the shader (recipe in the material's
  extras.alpha_mips; 0.76-0.98 of the full plant's area from 2 to 12 m). Turn the importer's own mesh LOD generation off.
- Judge it in the engine against the full plant's LOD 0 (area, outline IoU, colour per distance) and as a meadow with
  the game's placement, thinning and budgets.
