# Terrain: styles

Read guide(topic="terrain") first: describe the brief, then write the spec.

## Styles: the ground in the plants' art styles, zone by zone

One terrain can hold regions drawn in different styles (the vegetation styles' worlds: blobby, anime, ... and
realistic), so a blobby oak stands on blobby ground. The engine's shader draws the transition as the player walks
through it, so a pixel near a border needs BOTH styles' looks: the textures are shipped per style, not baked per tile.

```json
"zones": {"dumpling_downs": "west", "painted_east": "east"},
"styles": {"blobby": "dumpling_downs", "anime": ["painted_east", "knoll_hill"],
           "cartoon": {"in": "pencil_bay", "band": 30, "sheet": {"layers": {"grass": {"scale_m": 10}}}}}
```
- style -> a zone, any region address or a list; everywhere else is `realistic`. Zones are a partition: a style
  listed later wins where zones overlap. `band` (m, default 20) is the default transition width written into the
  weight maps; `sheet` overrides any number of the style's sheet.
- A style is a sheet of numbers over general operations (`src/hifipushie/terrain_styles/<name>.json` over
  `_base.json`; a new style is a new sheet): `colour` (saturation / value turned on the terrain's own layer colours:
  the same numbers as the plant style, so ground and plants step together), per ground layer (grass, turf, scrub,
  forest_floor, sand, earth, rock, wet_rock, snow; `like` another layer) a tileable texture built from ops: `blotch`
  (big soft colour fields, `steps` tones), `strokes` (directional brush dabs, warm-light / cool-shadow `tones`),
  `bands` (painted strata, level on cliffs), `ripples`, `dots`, `grain`, `cracks` (ink lines), `facets`, `pillow`;
  `scale_m` (the texture's side), `projection` top | triplanar (contract 2: soft layers are laid from the top
  everywhere, even on steep ground, as artists lay ground; only rock layers are triplanar, and their side planes wander
  `v_jitter_m` along the strike so painted strata don't repeat straight up a cliff); `macro` (how much of the baked tile colour's variation
  the style keeps: 1 realistic, 0 blobby), `macro_normal` (share of the baked normal kept), `detail` (the realistic
  tiling detail swatches), `overlay` (the style's own close-up swatch: anime brush dabs), `seasons` (per season per
  layer `{"mix": sRGB, "amount"}`, as the plants'), `snow` (numbers for the engine's snow, as the plants'), `rock`
  (the zone's rock shape: geometry, see below). Op keys worth knowing: `blotch` `share` (with 2 steps: the share of
  ground in the second tone, patches on a ground colour instead of a 50/50 camouflage) and `width` (spread of sizes);
  `strokes` `levels` (a painter's few mixed tones instead of a continuum); `dots` `clusters` [per m2, radius m]
  (flowers in clumps); any op's `paint` (an sRGB colour laid where it marks: white and yellow flower dots); `bands`
  `pinch` / `breaks` / `vary` (strata swell, wedge out as lenses and fade along the strike instead of ruled stripes);
  any op's `fade_small` (it gives way on small or thin rock: the layer then ships a plain texture, and the map
  `styles/rock_scale.png` says where: sea stacks and fins lose the anime strata). Sheet `layer_edge` {height,
  depth}: where two layers meet, their height maps decide a crisp painted edge (cartoon, anime) instead of a
  cross-fade. Contract 3.
- Cartoon and anime under hard-band cel light (the game's): any soft gradient in a texture or in the baked macro colour
  reads as a smudge, not as paint. Cartoon soft layers are flat fields in two crisp tones with a few marks (ink tufts,
  pale ticks, flower dots, pebbles) and `macro` 0; anime keeps 3 crisp value steps and 3-level dabs, `macro` 0.15.
  Judge with `look_terrain(styles=True)`'s ground view (eye level and 25 m up, mipmapped, anti-tiled, flat cel light).
- What artists do, and why it is built this way: stylised ground in games is a few tiling layer textures blended by
  weights (slope, height, painted masks), height-blended at layer edges, triplanar on cliffs, with anti-tiling
  ([Unity terrain height blend](https://github.com/unitycoder/TerrainHeightBlend-Shader), [stochastic
  tiling](https://github.com/unitycoder/Procedural-Stochastic-Terrain-Shader)); hand-painted textures are SHAPES in a
  few value steps, light warm and shadow cool, not noise; stylised rock is sculpted big -> medium planes -> polish
  (fewer, bigger planes, softened edges: [polycount](https://polycount.com/discussion/comment/2147949)). So a style's
  texture is an op stack with few, big shapes; its rock shape is geometry in the zone's tiles.
- Files (in every tiles export of a spec with styles, or alone with `export_terrain(name, styles_only=True)`, seconds,
  beside the last export): `materials/<style>/<layer>_albedo.png` (RGB sRGB, mean = the layer colour; ALPHA = the height, 8-bit linear, contract 4), `_normal.png`
  (tangent, glTF: +x east / along the face, +y north / up), `_height.png` (16-bit, 0.5 = 0, +- height_m),
  `materials/<style>/overlay_*`; `styles/<style>_sd.png` (signed distance to the style's zone edge, 16-bit,
  +- range_m, + inside) for a band of your own (ragged, moving), `styles/weights<g>.png` (the weights with `band`);
  manifest `styles` (also `styles.json`): `contract`, `order`, per style its zones, numbers, per layer files, size,
  colour (sRGB + linear), roughness, `seasons` (colour + `tint_linear` per season), `snow`, and `tiles` (which styles
  reach each tile), `recipe` (the per-pixel blend: style weights x layer weights x textures, macro, normals, seasons).
- Sheets shipped: `realistic`, `blobby` (flat soft colour fields, pillow rock), `anime` (painted dabs, painted strata),
  `cartoon` (two hard tones, ink tufts / cracks / pebbles, big flat rock facets), `pixar` (realistic forms cleaned,
  saturated, soft blades at 4-8x size).
- Rock shape (3D tiles only; the heightmap export, map and report are style-blind): a sheet's `rock` = `relief`
  (multipliers on this terrain's own rock character: `facets`, `bedding`, `size`; `blocks: false` drops the jointed
  blocks), `pillow` (`size`, `depth`, `round`: rock carved into rounded cushions), `soften_m` (the ground grid
  Gaussian-smoothed in the zone: rounded lips and forms; the heightmap tiles follow), `fallen` (share of fallen blocks),
  `micro` (share of the bake-only fine relief), `lip` (share of the turf's step at cliff lips; blobby 0), `band_m` (default 10: the hand-over between zones, in the field, so
  tiles and LODs agree and the seam checks hold). blobby: pillows, softened 1.5 m, no facets / beds / blocks / fallen;
  anime: facets x0.5, beds x1.5, no blocks; cartoon: facets x1.4 at 2.5x size, no beds / blocks; pixar: facets x0.7,
  beds x0.6, no blocks, softened 0.6 m. The realistic zones' field is unchanged bit for bit.
- The per-tile baked maps stay the realistic look; a styled pixel takes from them only what its `macro` /
  `macro_normal` say. No lighting is baked into any style's textures (AO is the baked map's).
- Look: `look_terrain(name, styles=True)` writes a swatch sheet (each style x layer: tiled albedo, lit, normal) and
  a season sheet and a transition strip per layer; with `tiles=True, views=[...]` it renders the last tiles export with
  each zone in its style (the recipe built in Blender: a reference for the engine's shader).
