# Vegetation: trees and plants the way vegetation artists make them

A tree here is **grown**, not assembled: you describe the species' habit, its age and where it stands; a growth
model (buds competing for light, year by year) makes the skeleton; then you direct it as a SpeedTree or Grove artist
does (draw limbs, prune, bend, shape the crown) and it regrows around your edits. A **style** then dresses the same
grown tree as realistic, blobby, anime, cartoon or pixar (storybook) foliage and wood. Small plants (grass, ferns,
flowers) are assembled from pictures on cards. Units are metres, Z up, the trunk's foot at [0, 0, 0]; +y is north,
"azimuth 0" looks along +y. The same spec always grows the same tree.

Enable the tools with `enable_toolset("plants")`. Sub-topics (guide(topic=...)): `vegetation_spec` (every spec key:
habit, environment, guides, cuts, prunes, envelope, leaves, bark, the report, botanical keys, what goes wrong),
`vegetation_styles` (the five styles and their sheets), `vegetation_forest` (sets, ages, stands, forests),
`vegetation_small` (grass, ferns, flowers, swards, groundcover), `vegetation_export` (LODs, wind, seasons, impostors,
collision, the export contract, engines), `vegetation_tools` (every plant tool's parameters).

**The rule everything else follows: describe what the reference shows before growing anything.** Style, branching
structure, canopy massing, bark and proportions, as measurable items. Every preset, style and number you pick must be
justified by that description. A preset grown and tuned toward a stylised concept gives a clean tree that is the
wrong tree (a realistic broom-branched oak with scaly plate bark and noisy leaf clutter, for a storybook oak of soft
cloud clumps on a tall trunk that twists and divides as it rises).

## Stage 0: describe the reference (before any preset, style or number)

Write these down as items with a value, how you'll measure it on yours, and a tolerance; mark what the reference
doesn't show as inferred. With a photo or concept, register it (`plant_reference`) so every report carries outline
numbers against it.

1. **Style.** Realistic, or stylised, and which: blobby / low-poly (smooth lumps, flat tones), anime / painted
   (Ghibli-like clouds of painted leaf dabs), cartoon (chunky scalloped clumps, a few oversized leaves), pixar /
   storybook (big soft canopy clumps covered in real-looking leaves, a rich dark-to-light gradient). Are individual
   leaves visible at the reference's distance, or only masses? How is it shaded (soft volumes, cel steps, flat)?
2. **Branching structure (the wood, read as if the leaves were off).** Trunk height to the first division as a share
   of the tree's height; how the trunk divides (one leader to the top, a fork into 2-3 leaders, dissolving into
   limbs); how many main limbs, where each leaves (spread up the trunk, or all from one point), their angle and how
   they curve, twist or droop; how thick the trunk is against the height; root flare. Is the trunk straight, leaning,
   twisting? A tree whose limbs all leave from one height reads as a broom.
3. **Canopy massing.** Overall silhouette (dome, vase, column, cone, umbrella, flag); width / height; where the crown
   starts (bole as a share of the height); how many distinct masses or clumps, their size against the crown, and
   whether sky / limbs show between them; how dense the edge is (ragged, scalloped, smooth).
4. **Bark.** Texture and its scale against the trunk (smooth, furrowed, plates, scales, painted flowing grooves, flat
   colour), colour and contrast, moss or a darker foot.
5. **Leaves and colour.** Leaf shape and size if seen; foliage colour in light and shade (sampled, sRGB), the value
   range from interior to tips, season.
6. **Size and setting.** Height in metres (from people, doors, houses beside it), age, open-grown / edge / forest,
   wind, slope, what it must do in the game (walk under it: clearance under the limbs; seen from far: silhouette).

Then choose and justify: species preset (or the nearest in habit), `style`, age / height, environment, and the
direction edits the structure needs. Example: "storybook oak: `style` pixar (soft clumps, real leaves on them), crown
masses ~8-12 big clumps with limbs showing between them; trunk 35-45% of the height before it divides into 3-4
sinuous leaders at different heights (drawn guides: a twisting trunk path from the ground, limbs `on: trunk` at
rising heights), not the oak preset's low dissolving crown; bark: the style's flat colour or `furrowed` at a large
`scale` with low contrast, not plates".

## The stages (don't skip ahead: foliage hides a bad skeleton)

| # | Stage | Tools | Gate before going on |
|---|---|---|---|
| 0 | Describe the reference | `plant_reference` | The description above, written |
| 1 | Skeleton | `get_plant(species=...)`, `grow_plant`, `look_plant(views=["clay"])` | The bare tree (clay, wood only) matches the structure items: trunk, divisions, limb count / heights / angles, crown base |
| 2 | Direction | `edit_plant` (guides, take_limb, prune, cut, envelope, forces) | The drawn limbs that make THIS tree are in; structure items pass |
| 3 | Style, foliage and bark | `grow_plant(patch={"style": ...})`, `look_plant(views=["leaf", "close", "near"])` | Massing, leaf, bark and colour items pass |
| 4 | Distance and game | `look_plant(views=["far"], triangles=N)` | The export's own picture at the budget reads as the reference at the distance it's seen from |
| 5 | Export | `export_plant` | Every LOD judged at its switch distance |

Typical loop in stages 1-2: grow (1 s) -> look clay (5 s) -> change two or three numbers or one guide.

**Before overriding anything, read it:** `get_plant(species="oak")` or `get_plant(name)` shows every value in force
with its usual range. An override REPLACES the resolved value; a per-order list is replaced whole. Change numbers by
small steps (vigour 5.5 -> 7 on a broadleaf is 100k+ nodes and a metre-thick trunk). Every save echoes old -> new and
what the tree did.

## Craft rules (each once; details in the sub-topics)

Structure
- Judge the skeleton bare first (clay, wood only); foliage hides a broom, a pole or a squat trunk.
- Habit numbers give the species' general form; drawn guides give THIS tree's structure. Three deliberate drawn limbs
  make a hero tree. A path from [0, 0, 0] with `from_year` 0 is the trunk itself (leaning, forked, twisting).
- Main limbs leave at different heights and curve; straight limbs (low `jitter`) read as a broom, limbs all from one
  height as a fan. A trunk that dissolves early (`apical` < 0.5) gives a squat tree; keep a leader longer (`apical`
  higher, `apical_old` / `apical_fade`) or draw the leaders.
- Size: `age` is the main control; `height` rescales an unedited tree; `trunk_diameter` / `limb_diameter` set girth.
- Setting changes form as much as species: open-grown, a stand's edge, a stand's interior are three different trees.

Foliage, bark, style
- A style never changes the growth: fix structure in the realistic tree, then dress it.
- Stylised crowns are MASSES: their count, size and the gaps between them carry the look (`style.crown.masses`,
  `blend_share`). Leaf detail at the wrong scale (individual realistic leaves where the reference shows clumps) reads
  as noise.
- Leaf colour is the leaf as you SEE it in the sun, not a dark albedo; foliage is shaded as a volume.
- Bark scale and contrast must match the reference at the viewing distance; a realistic bark kind on a stylised tree
  reads as reptile scales.

Distance and budget
- The export is another object: judge `look_plant(..., triangles=N)`, which renders exactly what `export_plant(...,
  triangles=N)` writes, not the full-detail tree.
- At 70 m a tree is silhouette, mass and colour; judge every LOD at the pixel size it's drawn at.
- Card foliage costs overdraw, not triangles: aim at 4-5 card layers per covered pixel for LOD 0.

## Self-review loop (every round, from stage 1)

1. Render yours at the reference's framing and distance (`look_plant` views and camera; `plant_reference` puts the
   outline beside the photo), and put it BESIDE the reference, region by region: overall silhouette, trunk and its
   divisions, main limbs (wood-only view too), canopy masses and gaps, crown edge, foliage surface, bark, colour.
2. For each region list what reads wrong against the reference, concretely (where, what, how far off). Mark each
   MAJOR (wrong style, wrong structure or proportion, wrong silhouette or massing, a visible defect) or MINOR. Order:
   structure and form before material (leaves, bark), material before colour.
3. Fix the worst MAJOR at its stage (usually the description, the style choice, a guide or habit numbers). Regrow.
4. Repeat until no region has a MAJOR. Re-measure the stage 0 items each round (table: item | reference | ours |
   pass): width / height, bole, trunk share before the first division, limb count and heights, mass count.

A tree that matches the numbers can still read as the wrong tree: an outline IoU of 0.9 says nothing about branch
character, massing or bark. A clean tree that isn't the reference is wrong. Argue a MAJOR away only with evidence
that the reference doesn't show it.

## Common mistakes

| Mistake | Instead |
|---|---|
| Growing the species preset and tuning it toward a concept | Describe style, structure and massing first; pick the style and draw the structure |
| Realistic foliage and bark for a stylised concept | `style` (pixar / anime / cartoon / blobby) from the description; the style's own bark |
| A squat trunk with every limb fanning from one point (a broom) | Draw the trunk and its divisions as guides at rising heights; raise `apical` / keep a leader; add `jitter` |
| Judging only the leafy render | Wood-only and clay views first; foliage hides structure |
| Judging the full-detail tree, exporting a budget | `look_plant(triangles=N)` with the export's budget |
| Changing many habit numbers at once, or big jumps | Two or three at a time, small steps, read the report |
| Copying the reference's outline with an `envelope` | Envelopes read clipped (topiary); use guides, wind and prunes |
| Open-grown trees planted as a forest | `environment.setting` "forest" / "edge", `spacing` |

## Reading the report

```
form (in leaf, two side views): width/height 1.17, bole 0.20 of the height, widest at 0.50
limbs: 5 first-order branches, leaving the trunk at 69 deg, their far halves 5 deg above level
```
- width/height: 0.3-0.6 columnar / conic, 0.8-1 oval, > 1.1 spreading.
- bole: the lowest height a quarter as wide as the widest (a forest tree 0.5+, an open-grown oak 0.2, a spruce 0).
- limbs' far-half elevation: ~70 a vase, ~40 spreading, ~5 level, negative weeping.
- The named limbs list ("SW2" = the second limb up the trunk, ending south-west) with heights: read where the main
  limbs leave. WARNINGS name what to change.
- With `plant_reference`: outline IoU 0.75+ with width / height and bole within ~0.05 matches the outline only.

## Known gaps (say so in your plan instead of faking them)

Blossom and catkins; thorns, flowers and fruit on twigs; a multi-stem base on a tree (shrubs have `habit.stems`);
exposed roots running over the ground, burrs, fluted trunks, hollows; banks, ditches and shorelines (only a slope and
a water level); a tree that sees other plants you made (use `setting` / `neighbours`); a painted stylised bark
texture (styles draw bark as one flat colour; realistic kinds are furrowed, plates, scales, lenticel); ivy and
creepers, fan palms, bamboo, reeds, mushrooms; scattering on terrain.
