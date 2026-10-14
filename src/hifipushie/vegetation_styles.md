# Vegetation: styles (the same plant dressed another way)

Read guide(topic="vegetation") first: the style is chosen from the description of the reference.

## Styles: the same plant dressed another way

`"style": "realistic" | "blobby" | "anime" | "cartoon" | "pixar"` on the spec (grow_plant, a set's plants). A style NEVER changes the growth: species, seed, skeleton, height, crown extent and lean are the realistic
tree's, node for node, so an engine can swap styles on one placement and the outline at 200 m is the same tree. The
report says what was simplified and measures that claim:

    style blobby: 4 limbs kept of 5 first-order + 10 of their forks (15 of 12125 axes drawn, 138 of 4451 m of wood; no twigs); 8 crown masses + a core joined over 3.55 m, for 17840 twigs, 3 tones
    same individual: outline IoU 0.86 against the realistic tree in leaf (true scale, feet together; azimuths 0/60/120: ...); height 20.2 m (realistic 19.8), crown width 23.8 m (realistic 25.7)

(IoU of the row-filled side outlines, both in the same metric frame: under 0.8, or a height off by 6%, is a WARNING.)

How artists make these (what the operations copy):
- Blob / low-poly trees are a trunk and a handful of smooth-shaded lumps, built from spheres or metaballs joined and
  remeshed; the shading comes from smooth normals over each lump, the colour from one flat tone per lump
  (https://www.blendernation.com/2016/09/26/make-low-poly-stylized-trees/,
  https://blenderartists.org/t/what-are-the-tips-and-tricks-to-make-stylized-low-poly-creations/1510574).
- Soft "Ghibli" foliage is leaf cards whose normals are TRANSFERRED from a rounded proxy hull round each clump (Blender's
  Data Transfer / Normal Edit modifier), so a clump shades as one soft volume and the cards only cut its edge
  (https://www.blendernation.com/2020/08/20/creating-ghibli-trees-in-3d/,
  https://trungduyng.substack.com/p/tutorial-blender-anime-foliage-pipeline, https://simonschreibt.de/gat/airborn-trees).
  The blobby crown below IS that proxy; later styles will put cards on it and take its normals.

A style is a sheet of ordinary numbers (`src/hifipushie/vegetation_styles/<name>.json`; get_plant shows the resolved
sheet under `style`) over a few general operations. Override any of them in the spec:
`"style": {"sheet": "blobby", "crown": {"masses": 5, "blend": 2.0}, "wood": {"limbs": 3}, "budget": 4000}`.
- `wood`: `limbs` [fewest, most] of the stoutest first-order limbs drawn (those at least 0.4 x the stoutest's girth)
  and `stubs` of each limb's stoutest forks (`stub_apart` m apart, at least `stub_min` m long, `stub_radius` x their
  limb): what carries the crown in leaf and what is left standing in winter (limbs alone were four bare noodles).
  Girth is TOY girth: `radius` x the grown radius, but a limb's base at least `limb_mass` x the crown masses' mean
  radius and the trunk `trunk_mass` x it (the pipe model's limbs read as wires under 4 m lumps); never thinner than
  `taper_floor` (trunk: `trunk_floor`) of the base; `foot` caps the root flare (the grown flare made the trunk a
  cone). Every limb and fork runs INTO the crown and ends there: it is drawn while its axis stays `keep_in` m + its own
  girth under the surface (to `reach_in` / `stub_reach` of its length), stops for good where it first comes out
  again, and a fork that never gets in is not drawn. `smooth` = bend smoothing passes. The wood is ONE field (each
  axis a chain of round cones, axes joined by a smooth union of `blend` x the branch's girth) meshed like the crown:
  forks are fillets, ends are round, normals are the field's. `flat` (bark = one colour), `share` (of the budget).
- `crown` kind "masses": the twigs' positions are clustered (k-means, no randomness), each cluster becomes an
  ellipsoid (principal axes x `spread` + `pad` twig lengths; no semi-axis under 0.75 x `min_feature` or under
  `roundness` x its longest: flat clusters read as lily pads; a mass never stands taller than the tree), plus a
  `core` mass in the middle (x the whole foliage's spread: foliage is a hollow shell, and masses fitted to a shell are
  a ring of balloons). They are joined by a smooth union over `blend_share` x their mean radius (at least `blend` m:
  1 m between 4 m masses left eight balloons; 0.9 gives one bumpy cloud) and meshed once (marching cubes on the
  field), then decimated per LOD and put back on the field. Closed, no leaves, no alpha. `masses` [lo, hi]: the
  fewest whose outline is within 0.01 IoU of the best (the report lists the IoU per count), or one number.
  `normals`: 0 = the field's own gradient (smooth over each mass and its blends) .. 1 = straight out of the crown's
  middle. `tones` steps of `tone` [dark, light] by each mass's height (top lighter; `warm_top`), one tone per mass.
  The fit is always made on the plant in leaf, whatever `season` it is shown in.
- `colour`: saturation / value on the species' leaf and bark colours. `wind`: `mass` = the least branch sway a mass
  has (it moves as a whole with the limb it sits on, in that limb's phase), `squash` (top vs bottom of a mass).
  `seasons`: what spring and snow mix the colour toward. `budget`: LOD 0's triangles when export_plant gets none.

The export keeps the realistic contract: nodes / meshes `wood` + `foliage` (LOD<k>_ prefixed), materials `bark` +
`foliage`, LODs at 100 / 45 / 18% + impostor, TEXCOORD_1 / TEXCOORD_2 / _WIND, KHR_materials_variants per season,
collision (capsules + mesh: the GROWN tree's, identical to the realistic export's: swapping styles must not change
gameplay). What differs, for the engine's shader:
the foliage is opaque untextured geometry; albedo = the material's baseColorFactor (one per season variant) x COLOR_0
(each mass's tone, <= 1: an engine's default imported material ignores vertex colour, switch it on; without it every
mass is one green). A season in which the plant is bare has `extras.hidden` on its foliage material and `hidden: true`
in the seasons json (the alpha cut-off above 1 is only there so viewers that read variants hide it); NORMAL is the smooth
mass normal; TEXCOORD_0 = (height within its mass 0..1, (mass index + 0.5) / masses) for ramps and per-mass ids.
No lighting is baked: cel bands and outlines are the engine's. extras.hifipushie_plant.style carries the sheet, the
"simplified" lines and every season's colour (sRGB).

Conifers (needle trees) take the sheet's `conifer` block, merged over the rest (override it under
`"style": {"sheet": "blobby", "conifer": {"crown": {...}}}`): crown kind "tiers" = stacked dumplings, `masses` [lo, hi]
of them, one per height band of the foliage, and the wood is the trunk alone (`limbs` [0, 0]). Each tier is an upright
EGG: round above its widest level (`tier_height` x its band), flat below it (`tier_under` x the band), seated
`tier_seat` up its band, as wide as the foliage in the band's lower part (`spread`, `pad`). So a tier's dome closes
under the next tier's wider foot: every tier overhangs the one below with an undercut (plain ellipsoids blended over
0.3 x their radius were a soft-serve cone). `blend_share` / `blend` small (0.1 / 0.35 m) keeps the undercuts.
`trunk_show` m of trunk stay bare under the lowest tier (`wood.trunk_mass` makes it fat); `tier_power` < 1 = upper
bands shorter; `tier_uneven` 0..1 = bands and widths differ (the seed's own numbers, the same every time);
`tier_cap` = the top tier no slimmer than that x its height (a narrow top band was a long finger); `tone`, `tones`,
`warm_top` and `colour.value` have their own conifer numbers (a spruce's dark needles gave one dark green top to
bottom). Cost: the Norway spruce's IoU falls from 0.85 (smooth tiers down to the ground) to ~0.75: the realistic
tree's skirt sweeps the ground and the toy has a bare foot and notches; the report warns under 0.8. Lower
`trunk_show` to get it back.

ANIME (`vegetation_styles/anime.json`, painted backgrounds: Ghibli, Genshin, BotW) is crown kind "clouds" (`veg_cloud.py`):
the same masses as the blobby crown, but they are the PROXY, not what is drawn. Every mass (clump) gets `layers` shells
(0.6 / 0.8 / 1.0 / 1.12 of its ellipsoid, weighted by `layer_weight`) of alpha cards facing out of it (tilted up to
`tilt` deg, rolled `roll`, cupped `cup`), `card` x the clump's radius across (at most `card_max`; lower LODs take
fewer, larger cards, up to `lod_grow` x); cards buried more than `bury` x a radius inside another clump are left out.
The picture is a generated grey DAB atlas (`crown.dab`: `count` brush dabs per tile, each the species' leaf outline
fattened, `length` x the tile, pointing out by `out` and down by `droop`, a solid `core`, a `ragged` rim; needle trees
a pointed spray stroke, shape "spray"); the material's colour and COLOR_0 multiply it. NORMAL = out of the card's own
clump's middle, mixed `normals` toward out of the crown's middle (artists transfer a proxy's normals onto the cards:
the clump shades as one soft volume and the cards only cut its edge). COLOR_0 = a 3-step painted gradient per clump,
one step per CARD (`tone` per step, `grad_range` of the clump's height, `grad_jitter`, inner layers darker by
`depth_dark`, the top warmer by `warm_top`); TEXCOORD_3 = (gradient 0 base .. 1 top of its clump, (clump + 0.5) /
clumps) for an engine's own ramp (Godot reads it as CUSTOM0.zw). Two sizes of cloud: `edge_share` of the foliage
furthest out of the crown's middle is clustered into `edge_count` x more, smaller clouds (one size read as one layer).
The cards are held under the realistic tree's height. Budget: what the triangle count buys, shared by area between
clumps and by `layer_weight` between layers; `clump_min_cards` raises small clumps (small top tiers were confetti)
and the big clumps give up what they gained, so LOD 0 stays within the sheet's `budget`.
Wood in anime: true radii, thin and dark (`colour.bark_mix` toward a dark warm neutral), with its forks (`stubs`) in
the ONE wood mesh (`wood.forks_in_leaf`: seen through the gaps, no `bark_forks` slot), and `wood.feed`: a clump with no
drawn wood within feed x its radius gets the grown tree's own path to it (outer clumps floated).
Anime conifers: clouds on TIERS (`masses_kind` "tiers", the blobby tier numbers), `under` 0.25 = cards facing the ground
under each bough are left out (the strong tier shadow), smaller softer spray strokes (110 a tile, a quarter of it long:
from 5 m half-tile strokes read as palm fronds) and spring = `seasons.spring.tips`: the spring picture paints the tip
`share` of every stroke `light` x lighter and `tint`ed (new growth), the rest `body` x (same alpha, same cards: only the
spring material's picture differs; the export's foliage_spring has its own baseColorTexture).
Anime small plants (`clump`): `fan` blades from each chosen card +-`fan_angle` (long thin sweeping blades), flowers as
colour DABS (`heads_kind` "dab": `dabs` flat ragged blobs of paint ~`ball` x the stalk long, facing up by `head_up`).
Every style's clump block takes `heads_kind`: "ball" (blobby: a ball on a stalk), "dab", "petals" (`petals` [fewest, most]
fat flat petals, `petal_length` / `petal_width`, cupped `cup`, round a `centre` disc).
Measured in an engine at each LOD's switch distance (alpha scissor): oak outline IoU ~0.9, covered area 0.94-1.0 of
LOD 0 at every switch; spruce IoU ~0.8.

CARTOON (`vegetation_styles/cartoon.json`: Wind Waker, Animal Crossing) is the blobby crown made chunky, each operation
a number: `crown.scallop` small round bumps on every clump's sides and top (`scallop_size` x its radius, sunk
`scallop_sink`, joined crisper than the clumps by `scallop_join`: the scalloped edge), clumps joined over a small
`blend_share` (clear notches between them), `normals_clump` (the normal mostly straight out of its own clump's middle:
flat-ish shading per clump, the brief's "clump-centre normals"), 2 `tones` with `hue_jitter` (the hue moves a little
per clump), `big_leaves` single oversized leaves (`big_leaf` x the species' leaf length, the species' outline fattened,
thin closed plates rooted `big_leaf_sink` into the crown at its outermost points, pointing out and up by `big_leaf_up`;
fewer at lower LODs; each takes its clump's colour, id and wind, its tip flutters). The clump id is TEXCOORD_0.y as in
blobby. Wood: first-order limbs, `wood.taper` (girth at the foot x (1 + taper), easing to the top), `wood.flare` (a root
flare over the first ~12% of the bare trunk) and `wood.s_bend` (one S along the bare trunk, `s_bend` x its height out and
back, nothing moves above the crown's base: the crown stays where the realistic one is).
Cartoon conifers: tiers of `tier_shape` "cone": each tier a cone standing on its band's foot, `cone_height` x the band
tall (it reaches into the band above: the saw-tooth outline), its rim cut into `teeth` points `zig` x its radius in and
out (a zigzag outline from above and the side). The cones' triangles cover less of the realistic outline than its
parallel-sided bands: IoU ~0.8 is the style's price (wider `spread` buys IoU and costs width).
Cartoon small plants: few big wide blades, `heads_kind` {"ray": "petals", ...}: a daisy's flower as 5-8 fat flat petals
cupped round a centre disc (COLOR_0: white petals, yellow centre, green stalk), a grass's seed spike as a ball.

Cartoon, second pass: `big_leaves` stand on clumps' EDGES (out of the crown, not under it), pointing out and up, their
FACE turned sideways (toward the views that see that point on the outline; lying flat, face up, they were seen edge-on
from eye level as green shards), the species' outline softened by `big_leaf_soft` toward a plain ovate leaf (sharp lobes
read as a saw blade), `big_leaf` x the leaf length (26: ~3 m on a 20 m oak, as the toy proportion asks). `wood.flare` is a
concave root foot `flare_height` trunk DIAMETERS tall ((1 - s)^2.5; the trunk resampled finely there) and the trunk's foot
node stands under the ground (a round cone ends in a sphere: one centred on the ground read as a bulb / mound). Flowers
face the sky by `head_up` (0..1, the rest along the stalk; a head along a leaning stalk faced sideways and showed its
petals' shaded backs) and petals shade toward the sky on both faces. A season may paint the masses' EDGES (sheet
`seasons.<season>.tips` {"color", "band": [whole, gone] in TEXCOORD_0.x}: the cartoon fir's spring = lime new growth on
every tier's rim): the export writes it as a RAMP TEXTURE over TEXCOORD_0.x in that season's material (contract 7).
Anime seed / flower heads (`heads_kind` "dab") are small CLUSTERS of soft blobs strung along the head (`dabs`,
`dab_length`, `dab_size`, `dab_flat`): flat discs read as coins on sticks from the side.

PIXAR (`vegetation_styles/pixar.json`; Pixar / Disney forest sets: Brave, Up, Luca). What artists do: the canopy is
modelled as a few big sculpted, SOFT shells per branch cluster that hold the shape and the shading, and a layer of real
leaf cards is scattered over the outside so the silhouette and the near view are leafy while the inside reads solid;
normals of the cards are taken from the shell, colour is a rich gradient from dark interior to warm, light tips, and
light through the canopy (translucency / subsurface) is driven by how thick the canopy is
(https://www.fxguide.com/fxfeatured/pixars-luca/, https://graphics.pixar.com/library/ (tree / foliage papers),
https://www.blendernation.com/2020/08/20/creating-ghibli-trees-in-3d/ for the shell + cards method in Blender). Here:
- the shell = the blobby masses (`crown.masses` [8, 16], fewer and bigger: 20 small ones read as pom-poms), joined
  softly (`blend_share`), coloured per vertex by `crown.gradient` [interior, tip] (0.55 x out-of-the-crown + 0.45 x up),
  warmer at the tips by `warm_tip`, hue per mass kept; `normals` 0.5 = canopy-centre normals half way;
- `crown.cards` (a general op: any closed crown can take it): `count` of the species' TRUE leaf outlines per card
  (`length` x the card's half width each), sized so a leaf is `leaf` x the species' leaf length (1.5); cards stand on
  the shell at points drawn by area (`under` = less on its underside), `out` [least, most] m outside it (the outer
  20-30 cm), facing out (tilted `tilt`, rolled `roll`, cupped `cup`), at most `cover` x the shell's area, `share` of the
  crown's triangles; lower LODs fewer, larger cards (up to `lod_grow` 2x); `size_m` = a needle tree's spray size
  (needles are too small to size by), `rim` = weight toward the boughs' outer edges; NORMAL = the shell's under the card;
- TEXCOORD_3 = (gradient, THICKNESS m: how far a ray straight in stays inside the canopy, capped `thick_reach` 4 m;
  cards 0.02) on both; material extras.translucency {color, amount} = the warm light-through tint for the engine;
- wood: every structural limb and its forks at TRUE girth (`radius` 1, `limb_mass` 0), bends smoothed, in one mesh,
  `feed` carries outer clusters; conifers: drooping bough shells (`tier_shape` "cone", fine `teeth`) with needle-spray
  cards weighted to their rims; small plants: lush fine blades (`fan` 6, narrow), true flowers (petals at the realistic
  size), seed spikes as dab clusters.
Export: slot `foliage` = the shell, NEW slot `foliage_cards` = the cards (the foliage mesh's next primitive: MASK,
double sided, the leaf atlas x factor x COLOR_0, one material per season; contract 9). Budget = the realistic one (20k).

Impostor quad cropped (contract 8): the octahedral frames are squares the bake sphere's size; most frames draw much
less (a 24 m oak's frame is 33 m square). extras.hifipushie_impostor `crops` = each frame's own [u0, u1, v0, v1] (all
seasons, 3% margin), `crop` = their union (the stored quad); the reference shader builds the quad from the union of the
4 frames a view blends (`uniform vec4 crops[256]`, `has_crops`). `drawn_share` in the extras = the average frame's
share of the square (anime oak 0.63). Anime crowns at LOD1 / LOD2: `crown.lod_layers` [kept under lod 0.6, under 0.3]
(the OUTER layers: what is inside an outer shell of cards is hidden but still drawn) and `lod_area` (the cards' growth
exponent: 0.5 keeps the covered area and the pixels drawn; less = fewer pixels): oak [2, 1] at 0.3, spruce [2, 2] at
0.35; summed card area over covered area (overdraw before alpha) LOD1 7.1 -> ~5, LOD2 4.4 -> ~3.

Forks only when bare: a deciduous styled tree's wood is two primitives: slot `bark` (trunk + limbs, always drawn) and
slot `bark_forks` (the limbs' forks: hidden while the crown is there, where they cluttered its underside; shown in
the bare seasons through the variant `bark_forks_bare`, within `wood.forks_share` of the budget). Looks draw the
forks when the season is bare. The slot is in the seasons json's `slot_list` with the seasons that hide it.

Small plants in a style (sheet block `clump`; `"style": {"sheet": "blobby", "clump": {"blades": [4, 6]}}`): a clump's
cards are pictures, and a style without leaves has none, so every leaf card becomes geometry: `blades` [fewest, most]
FAT blades (closed paddles `width` x their length wide, `thick` x that through, curling over by `curl`, ending in a
point), chosen among the realistic cards tallest first and then by the farthest tip, so the tuft keeps its height and
spread (the report gives both against the realistic plant); every flowering picture (a part whose twig has a `flower`)
becomes a ball (`ball` x its length) on a thin stalk, at most `heads`. One tone per blade in `tones` steps of `tone`
(COLOR_0), normals leaned to the sky by `normals_up` so the tuft shades as one clump, wind = each blade bends from its
foot in its own phase (the realistic card's). `budget` (800): LODs take sides and rings off the same blades. In the
export the blades are slot `foliage`, the heads the foliage mesh's SECOND primitive, slot `heads` (COLOR_0 = each part's
colour under a white factor: petals or ball, the flower's centre, the stalk; hidden, like `bark_forks`, in the seasons
its layer doesn't show in). `heads_kind` "ball" | "dab" | "petals", or a table by the realistic flower's form
(`{"ray": "petals", "*": "ball"}`: a daisy's rays become petals, a grass's spike a ball). Winter in the EXPORT: when the
plant's winter state lays its blades down (veg_small's `flatten`), the lying blades are the foliage mesh's own primitive,
slot `foliage_winter`, shown only in winter and snow while `foliage` is hidden (contract 6). Chosen over a morph target
per season: the engine already hides and shows slots per season from the seasons json, a clump is a few hundred
triangles (the second set costs file size, not draw calls), and nothing has to keep blend weights in step with the
wind and the LODs.

Seasons in a style: spring (fresh yellow-green; an anime conifer's fresh tips), summer, autumn (`leaves.autumn`),
winter (deciduous: the bare drawn limbs and forks; evergreen: its crown), snow = THE WINTER STATE UNDER SNOW (contract
5: a deciduous tree is bare under snow, its forks shown, the snow impostor the bare tree; an evergreen's crown pale;
snow ON wood is the engine's shader from the seasons json's `snow` numbers). The realistic tree has spring too now: `"season": "spring"` / the export's "spring"
variant = `leaves.spring` colour (else the summer colour toward yellow-green) and leaves `leaves.spring_size` (0.75)
of their length. Blossom and catkins are not built. Small plants have their own states: see "Small plants".

What goes wrong: an IoU under ~0.85 usually means the realistic crown is ragged or hollow on one side (raise
`crown.masses`' upper end, or lower `spread`); masses like separate balloons = `blend_share` too small or no `core`;
limbs like wires = `limb_mass` / `trunk_mass`; a stick showing through a mass = raise `wood.keep_in`; a bare winter
tree of a few noodles = more `stubs`. Tiers like a soft-serve cone = `blend_share` too large or no
`tier_under`; a top like a finger = `tier_cap`; tiers of wildly different heights = `tier_uneven` over ~0.3.
Known: from 5 m the fork's fillet shows a ragged shadow edge in the looks (EEVEE's shadow terminator on large smooth
triangles; the clay view doesn't show it). A styled fern or daisy is the grass rule
applied to its cards (paddles and balls): not yet judged.
