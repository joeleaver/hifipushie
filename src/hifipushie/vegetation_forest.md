# Vegetation: sets, ages, stands and forests

Read guide(topic="vegetation") first.

## A stand or a group

Make one individual, then copies: `grow_plant(name="birch_b", copy_from="birch_a", patch={"seed": 2, "age": 13})`.
Give them the same `environment` (e.g. `setting: "forest"`). See them together with
`look_plants(names=[...], spacing=2.5)`: the only way to judge whether they belong together. Export each
(`export_plant(name, triangles=12000)`).

## A forest set: one description, several plants

`grow_plant(name, patch={"set": {"count": 5}})`: the plant's **set** = the same description grown from other seeds
at a spread of ages (`"age": [0.55, 1.0]` shares of the plant's age, youngest first; or `"ages": [years...]`), with
`"vigour": 0.12` (+-12% each), `"height": [lo, hi]` m, `"lean": deg` (each trunk leaning its own way), `"patch"`
(a patch for all, or a list of one per plant). A set is the species, not copies of one tree: the hero's guides,
prunes and one-off cuts are dropped (`"keep_guides": true` keeps them; repeated cuts, i.e. management, stay).
The report lists each plant (`name#1`...). `look_plants(["name#*"])` shows them together, `look_plant("name#3")`
one; `export_plant(name, set=True)` writes one file with a node per plant sharing the bark and foliage materials.
To turn a set's plant into a hero: `grow_plant("hero", copy_from="name#3")`. For a forest use
`environment.setting: "forest"` on the plant: the whole set grows with clear boles and high crowns.

## A species is a habit at EVERY age: `plant_form`

A habit tuned on one photo is one point. The Scots pine preset fitted to a single 80-year open-grown photo was a
bare pole with three limbs at 35 years, as wide as tall at 80 and wider than tall (dbh 2.9 m) at 150; in a stand it
was a crooked stick with antlers. `plant_form(name | species=)` grows the plant at several ages in the open, on a
stand's edge and inside a stand, and measures what foresters measure: height, crown width / height, live crown /
height, the height of the widest level, dbh. Give each case target bands and it marks the misses; give `fit` and it
searches habit numbers for the least miss over all cases at once (`vegetation.fit_form`).

Where targets come from, best first: yield tables and crown studies (height and dbh by age and stocking; crown
ratios of stand trees), species accounts (final height, girth, "conical when young, rounded or flat-topped when
old"), and boxes read off whole-tree photographs of known setting (tree box and crown box in pixels: width / height
and crown / height need no scale). Write down which is which.

What moves form with age (habit keys):
- `slowing[0]`: height growth tails off (a pine: 6 m at 15, 12 m at 35, 21 m at 80, 30 m at 160).
- `limb_pace` [-, 0.9, 0.75]: no side shoot outgrows that share of the leader's pace AT THAT AGE: the whole tree's
  shoots shorten together. Under 1 the leader stays ahead for life (a spire; a pole in a stand); near or over 1 old
  limbs catch it up (a rounded or flat old top). Without it, limbs born late outgrew an old slow leader.
- `tip_life[1]`: limbs stop reaching after that many steps and then die back: the crown base lifts on a veteran.
- `ring` per order + `pipe`: girth. In a stand `sdi_max` caps it by the stocking (Reineke: stems / ha x (dbh / 25
  cm)^1.6 <= the species' most; spruce 1500, pine 1000): 3 m apart a 50-year spruce is 30 cm, not 42.
- `clear` is NOT how a bole forms (it made a pole at every age): young trees branch from the ground and shade
  (`shed`, in a stand `stand_shed`) lifts the crown.
- Wood past its last living branch (no tip, bud or leaf beyond it) is shed like a shaded branch.

## A forest: `grow_stand`, `look_stand`, `export_stand`

A forest in a game is a KIT stood many times: per species a few interior trees (bare stems, dead branches, a small
live top) and edge trees (foliage down the open side), at three levels of detail, plus a floor. `grow_stand(name,
spec)` grows the kit and lays the plot out; the reply is the forester's table (stems / ha, mean height and dbh,
basal area, live crown ratio, canopy cover) with warnings: basal area over ~70 m2 / ha = stems too stout for the
spacing; canopy cover under 60% = scattered trees, not a forest.

    grow_stand("spruce_wood", {"species": "norway_spruce", "age": 50, "spacing": 3.0, "size": [60, 84],
               "edge": ["s"], "floor": {"ferns": 0.03}})
    look_stand("spruce_wood", views=["inside", "edge"])
    export_stand("spruce_wood")      # GLBs per variant (LODs + impostor), floor meshes, layout.json

- Stages, as environment artists work: (1) ONE interior tree and ONE edge tree per species right, by `plant_form`
  and `look_plant` (bare stem, dead zone, live crown ratio against photographs of stand interiors); (2) the stand's
  numbers (spacing for the age: 2-2.5 m young thicket, 3-4 m pole stage, 5-7 m old; mixed species by `share`);
  (3) `look_stand` from inside at eye level and from outside an open edge, beside photographs; (4) the floor;
  (5) export and the engine's scatter.
- Levels of detail: `lod.near` / `lod.mid` (m from the eye) and `budgets` [full, mid triangles, far triangles]. A
  look draws at most `max_full` trees with every twig (a laptop GPU can lose its context at a few dozen full spruces; trees of
  one variant and level share one mesh and one set of textures). Far trees at ~1500 triangles stand in for
  impostors in looks; the export writes real impostors.
- What makes an interior read as a forest and not as a row of poles: the dead zone (the species' `dead_keep`,
  dead-twig cards: `leaves.parts.dead`, a picture drawn as an irregular tangle: `forks`, `depth`, `crook`,
  `broken`, `lichen`); distance haze (`haze.distance` 60-120 m: far stems pale and merge, the horizon closes);
  the canopy's diffuse light (`light.ambient`: EEVEE has no sky light under a closed canopy, without it the
  interior is night); a floor that is not one colour (`floor`: brash under the stems, stumps, ferns where light
  reaches, moss patches, litter flecks); a plot deep enough that no sky shows between the stems at eye level
  (60+ m of trees ahead of the eye at 3 m spacing).
- At a budget a dead zone is a HAZE: `veg_bough.DEAD_SHARE` of the bough cards at most draw dead wood (the longest
  bough of each height band), baked from half its twigs. Every dead bough carded was a brown fur on the stem.
