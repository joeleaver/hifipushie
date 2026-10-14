# Hair: background (practice, sources, engines, what went wrong)

Why the hair tools are built the way they are: production practice, sources, engines and budgets, and the
failures met on the way. Not needed to make hair; read it when changing the tools.

## How game artists do it

The sources (listed at the end) agree on the method. Numbers are theirs.

1. **A strand atlas.** A handful of pictures of strand clumps, each running root to tip: usually 6-8 of them, in a
   density hierarchy. Sykutera's curly-hair atlas: 2 for volume, 3 for breakup, 1 of clumped strays and fly-aways, 1 of
   short curls for the neckline. They are baked from a real strand groom (XGen, Blender hair curves, FiberShop,
   Hair Card Designer, Fiberbake) or painted. Each picture comes as several maps: colour, **alpha**, and the three an
   engine hair shader asks for: a **root** gradient (root-to-tip colour ramp), a per-strand **ID** (value variation)
   and **depth** (strands deep in the clump darker, less specular; Unreal also offsets pixel depth with it), often
   packed in one texture, plus a normal or flow/tangent map.
2. **A hair cap first.** A "hair helmet" textured as hair under everything, so no scalp shows between cards and the
   head already has the hair's base shading. Where the cap meets the skin, the scalp itself is painted with a hairline
   shadow.
3. **Cards in layers, most opaque first** (80.lv, CGMA, Polycount):
   - a **base layer** of broad, nearly opaque cards blocking in the whole structure;
   - one to three **breakup layers** of less and less opaque cards over it (clumps of 2-3 cards each);
   - **fly-aways**: single-strand cards standing off the silhouette;
   - last, the **transitions**: the hairline, temples, nape and ears, with short **baby hairs** (4-5 variations
     round the neck, ears and temples, 2-3 on the forehead in the 80.lv ponytail).
   Cards are few-segment strips, with edge loops only where they bend; a lengthwise fold or cup gives them body.
   Roots are widened to hide the scalp. Leave negative space between clumps of curls.
4. **Tied hair** (the 80.lv ponytail): cover the scalp with cards that run to the tie; define the tail's volume
   with longer cards; then breakup cards, fly-aways and baby hairs. The tail hangs from the tie under gravity and
   is fullest a little below it.
5. **Shading.** Two-sided, one normal for both faces, bent toward the hair volume's own normal (transferred from
   the cap or a proxy) so the mass shades as one soft form; anisotropic highlight along the strands, shifted per
   strand by the ID map (Scheuermann); the root darker, tips lighter and more transparent; ambient occlusion baked
   per layer into vertex colours.
6. **Alpha.** Alpha blending sorts badly, so cards are drawn alpha-tested with dithering + temporal AA, or
   alpha-to-coverage (hair "doesn't need blending, just alpha testing", and coverage antialiases it); mips must not
   erode the alpha (visible scalp gaps come from too little overlap in the base layer or from mip erosion).
7. **Budgets.** Marketplace game hair: 10-15k triangles "low", 25-37k "mid"; hero hair in current AAA games up to
   ~100k. A whole character of the previous generation was 25-30k. Textures 1-2k for one head of hair. Three LODs,
   the far ones dropping the upper layers and fly-aways.
8. **Tools worth knowing:** GS CurveTools (Maya: cards bound to curves, so the groom stays curve-editable: what
   our locks are), Hair Card Designer and Fiberbake (Blender: atlas baking + card grooming), FiberShop (atlas
   baking), Unreal's Hair Card Generator (clusters a strand groom into clumps, one card per clump, textures shared
   between similar clumps).

What reads wrong: **plates** (cards too wide, too few, too opaque at the tips), **helmet** (no fly-aways, a clean
outline), a **hard hairline** (no fade, no baby hairs), **scalp gaps**, **one-sided shading** (cards dark from
behind), a **stiff tail** (no wave, every card the same length), **spaghetti** (only sparse cards, no base).

## Sources

- Hossimo, [The right way to think about doing hair as an artist](https://hossimo.com/articles/tips-and-tricks-an-artist-friendly-approach-to-sculpt-groom-hair/):
  primary / secondary / tertiary, no scalp at the first stage, the blur test.
- Dan Eder (80.lv), [Sculpting stylized hair in ZBrush](https://80.lv/articles/guide-sculpting-stylized-hair-in-zbrush):
  blockout first; repetition, wobble, symmetry and clipping as the common mistakes.
- Pablander Academy, [Sculpting stylised hair in ZBrush](https://www.pablander.academy/tutorials/sculpting-stylised-hair-in-zbrush):
  squint for the big chunks, volume then crevices.
- Brooke Eggleston, [How to draw and design hair for characters](https://brookeseggleston.com/blog/how-to-draw-and-design-hair-for-characters):
  big / medium / small, the part as two shapes, S-curves, negative space, the wig look.
- Emmyroid, [Clip Studio tips](https://tips.clip-studio.com/en-us/articles/10830): ribbons, the whorl and part, no
  repeated S, "grass", shadow / highlight / rim.
- MelanciaComics, [Clip Studio tips](https://tips.clip-studio.com/en-us/articles/15907): the 6-3-1 size rule.
- 80.lv, [Voluminous hair](https://80.lv/articles/004adk-005cg-cgma-student-project-voluminous-hair): opaque layers
  first, root gradients, a grey value per strand group.
- Scheuermann, [Hair rendering and shading (ATI, GDC 2004)](https://web.engr.oregonstate.edu/~mjb/cs557/Projects/Papers/HairRendering.pdf):
  two shifted anisotropic lobes, noise on the shift, AO.
- Animal Logic, [Hair Tubes (SIGGRAPH Asia 2023)](https://animallogic.com/wp-content/uploads/2023/12/HairTubes.pdf):
  artists model the silhouette as a mesh and strands are made inside it.
- Blender Studio, [Procedural hair nodes](https://studio.blender.org/blog/procedural-hair-nodes/): strand / clump
  tools; for big stylised locks, curves with a profile remain the editable choice.
- AWN, [Rapunzel lets her hair down](https://www.awn.com/animationworld/rapunzel-lets-her-hair-down-tangled): rhythm,
  volume, twist and a designed swoop.
\n
More sources (cards):
- 80.lv, [Creating a ponytail hairstyle with Maya XGen and Unreal Engine](https://80.lv/articles/creating-a-ponytail-hairstyle-with-maya-xgen-unreal-engine/):
  scalp cards first, the tail's volume with longer cards, breakup, baby hairs (counts), FiberShop bakes, GS CurveTools, 3 LODs.
- 80.lv, [Creating hair for real-time projects](https://80.lv/articles/creating-hair-for-real-time-projects/):
  diffuse / alpha / depth / ID / root maps, layers placed by opacity, pixel depth offset.
- 80.lv, [Tips and tricks on hair for games](https://80.lv/articles/tips-tricks-on-hair-for-games/): opaque base,
  then breakup layers of less opaque cards, clumps of 2-3 cards, hairline and fly-aways last, AO per layer in the vertices.
- Thomas Sykutera (Games Artist), [Curly hair breakdown](https://gamesartist.co.uk/curly-hair-character-breakdown-thomas-sykutera/):
  the atlas's hierarchy, ~6 clump and 5 fly-away meshes reused, curls by bending cards along curves, a lengthwise
  fold, negative space, shader settings.
- Epic, [Photorealistic character: hair](https://docs.unrealengine.com/4.26/en-US/Resources/Showcases/PhotorealisticCharacter)
  and [Hair Card Generator](https://dev.epicgames.com/documentation/unreal-engine/hair-card-generator-for-grooms-in-unreal-engine):
  the hair shading model's textures (root, depth, ID), two-sided material, cards generated from clustered strands.
- Polycount, [alpha test vs alpha-to-coverage for hair](https://polycount.com/discussion/comment/2500017).
- Budgets: FlippedNormals game-hair listings ([short male](https://flippednormals.com/product/hair-short-male-hairstyle-16197):
  11k low / 25k mid), Ellie Porfyridou, [Real-time hair](https://www.digitalartsandentertainment.com/article/367/+Ellie+Porfyridou++Graduation+Work%3A++Real-time+Hair+) (up to ~100k in current games).
- Superhive, [Fiberbake](https://superhivemarket.com/products/fiberbake-hair-cards): strand effects (curl, clump,
  braid, frizz), atlas packing, a live triangle readout.

# From a strand groom to game hair: what artists do, and where we stand

Research of 2026-10-05 (the user: "do more research on how to turn blender hair into game-ready assets"). Claims
marked (snippet) were read in a search summary only, not on the page; "not found" means no source turned up.

## Engines

- **Unreal**: a Groom asset from an Alembic file. Schema (Epic's docs): `groom_version_major/minor` (1, 5),
  per curve `groom_guide`, `groom_group_id`, `groom_id`, `groom_root_uv`, optional `groom_closest_guides` /
  `groom_guide_weights`, per vertex `groom_color`, widths from the curves (`groom_width`). Each groom LOD is
  strands, cards or a mesh; card textures are Depth, Coverage, Tangent, Attributes (root uv / coord u / seed),
  Material, Auxiliary. Strands run on Windows, Mac (M2+), Linux, PS5, Xbox Series; cards and meshes everywhere.
  Card shading: the Hair shading model with the tangent in place of the normal, dithered opacity resolved by
  TAA / TSR, the depth map into pixel depth offset (snippet).
- **Unity**: `com.unity.demoteam.hair` (strands from Alembic curves, clustering LODs, GPU simulation); HDRP's Hair
  material is Kajiya-Kay ("approximate", for cards) or Marschner ("physical").
- **Godot**: no strand hair. Cards with alpha scissor / alpha hash + TAA or alpha-to-coverage, anisotropy with a
  flow map or a custom Kajiya-Kay shader.
- **glTF**: `MASK` + alpha-to-coverage, or two passes (an opaque clip pass ~0.7 for depth, then a blended pass for
  soft edges). `KHR_materials_anisotropy` is a brushed-metal lobe, not a hair BSDF: no transmission, no root / id
  inputs. Hair in glTF is cards + a recipe for the engine's own hair shader.
- **Blender writes strands**: Hair Curves go into Alembic and USD since 4.2 (release notes). Whether the stock
  exporter passes named `groom_*` attributes through is unverified (a third-party exporter writes them with
  pyalembic); Unreal wants centimetres (scale 100) and applied transforms.

## Budgets (what could be sourced)

Aloy (Horizon Zero Dawn): ~100k hair triangles on ~50 splines (snippet). A student LOD study: the same style at
65k / 30k / 13k / 6k / 4k / 2.5k, quality holding "down to a point"; complex female hair 19k. Epic's tutorial: ~54k
at LOD 0. Textures: 4K on marketplace assets, 512 px cited once for production (snippets). No published per-LOD
table for NPC or mobile hair was found; cards -> fewer cards -> a helmet mesh matches Unreal's strands / cards /
mesh LOD types but is not sourced as numbers.

## "Volumised" strands (the user's remembered production pipeline)

Nothing documented matches a strand-to-solid-mesh conversion. Sprite Fright's hair meshes were sculpted and
retopologised by hand beside the particle hair and "updated to match grooming" (production log, May 2021). Blender
Studio's procedural hair nodes post only notes that larger radii self-intersect when converted to mesh. No Charge or
Wing It write-up, no per-clump Points to Volume pipeline. The nearest real practice is a profile swept along each
clump's curve (Curve to Mesh): which is what our solid locks are.

**Tried once and closed (2026-10-06, `spikes/hair_strands/hs3/volumise.py`, render ht_12_volumise_try.png):** each
sub clump of Tess's tail (77 clumps), its strand points through Blender's Points to Volume (2 mm) -> Volume to Mesh
(0.8 mm voxels): 3.6 million triangles in 45 s, and the result is rows of beads (strand points are 1 cm apart, so
the spheres do not merge along a strand; resampling to under the radius multiplies the points by ten), with no
strand detail and no material. It would still need a remesh, a retopology and a bake to be an asset: a worse route
to what a swept lens lock already is. Stylised solid hair stays on locks (style "locks"); realistic hair is strands
+ cards. Do not reopen without a documented production pipeline to copy.

## Where our pipeline stands against that practice

| practice | ours today | gap |
|---|---|---|
| groom on strands | Hair Curves from the spec's locks (`style: "strands"`) | in progress |
| clump variants baked to an atlas, 8+ passes | a drawn numpy atlas (colour, alpha, normal, aux) | bake from the groom's own clumps with Cycles: alpha, depth, normal, root-tip, id, flow, AO; unlit colour |
| cards generated from clumps, 3 a clump, layered by opacity | cards cut from each lock, 1-3 layers | cut from the strand groom's clumps; Epic's five layers and triangle shares as the default recipe |
| scalp cap texture + hairline cards | a cap mesh wearing a hairline tile, baby cards | bake the scalp layer onto the scalp's UV; single-strand hairline cards |
| LODs: fewer triangles on one atlas, then a helmet | one budget | LOD chain; the solid locks / cap as the last LOD |
| engine shader: tangent-space hair BSDF, dithered alpha, depth offset | glTF MASK + anisotropy + extras | ship root / id / depth / flow maps + a recipe per engine |
| strands for film and high-end engines | none | Alembic groom (`groom_*`) + USD beside the cards |

## Sources (this section)

- Epic, Alembic for grooms: https://dev.epicgames.com/documentation/unreal-engine/using-alembic-for-grooms-in-unreal-engine
- Epic, Hair Card Generator tutorial: https://dev.epicgames.com/documentation/unreal-engine/creating-hair-cards-and-lods-using-hair-card-generator
- Epic, cards and meshes for grooms: https://dev.epicgames.com/documentation/unreal-engine/setting-up-cards-and-meshes-for-grooms-in-unreal-engine
- Epic, groom platform support: https://dev.epicgames.com/documentation/unreal-engine/groom-platform-support-in-unreal-engine
- Blender 4.2 release notes, I/O: https://developer.blender.org/docs/release_notes/4.2/pipeline_assets_io/
- Groom Exporter for Unreal (third party): https://blenderartists.org/t/groom-exporter-for-unreal-engine/1415778
- 80.lv, hair for real-time projects (XGen): https://80.lv/articles/creating-hair-for-real-time-projects/
- 80.lv, Bystedt's free hair cards from curves: https://80.lv/articles/free-hair-cards-from-curves-setup-for-blender/
- FiberBake: https://superhivemarket.com/products/fiberbake-hair-cards
- Unity demo team hair: https://github.com/Unity-Technologies/com.unity.demoteam.hair
- Blender Studio, procedural hair nodes: https://studio.blender.org/blog/procedural-hair-nodes
- Sprite Fright production log: https://studio.blender.org/films/sprite-fright/production-logs/2021/may
- BCon24, mesh hair with geometry nodes: https://conference.blender.org/2024/presentations/1990/
- DAE graduation work, real-time hair LODs: https://digitalartsandentertainment.com/article/367/+Ellie+Porfyridou++Graduation+Work%3A++Real-time+Hair+
- Godot BaseMaterial3D: https://docs.godotengine.org/en/4.3/classes/class_basematerial3d.html

# Strand grooms through the tools (realistic hair, and its game cards)

For realistic hair the locks stay what you reason in, but they become GUIDES: `groom_hair(name, style="strands")`
turns every lock into a flat clump of strands on Blender's Hair Curves, and a scalp layer of short hairs grows
everywhere inside the hairline (the soft hairline, the cover under the locks). Solid stylised hair is style "locks"
(the rest of this guide); nothing about it changes.

## What went wrong on the way (so you can recognise it)

- Hair painted onto the face and shoulders like a stain: the collision proxy mesh was inside out (Shrinkwrap pulls
  what it takes for "inside" to the surface). `tests/test_hair_loose.py::test_collider_mesh_faces_out`.
- A curtain of hair over one eye, tufts standing along the parting: front hair has no direction from gravity (on
  the forehead it points over the face), and the mass was lifted at the roots. Hair is turned aside where it would
  hang in front of the face; the mass builds up as locks descend, not at their roots.
- Long hair fanned out over both arms: a lock lying on a shoulder kept its sideways direction. It slides off to
  the front or the back.

- A dark band above the forehead: lower card layers darkened twice (vertex colour AND the atlas's depth shade) and
  every upper card starting at one distance behind the line. One shade only; roots staggered and faded by alpha.
- Brown stamps along the hairline: baby-hair tiles full of parallel hairs touching the quad's border, lines thinner
  than a texel (an alpha test kept only where they crossed). A baby tile is 4-6 hairs with empty margins.
- A "wire mesh" tail: thin ribbons on separate wave phases with no opaque base. Cards from the strands' own clumps
  wave together; the core closes what is behind them.
- Wisps as dark slashes that seem to start on the cheek: one filled ribbon whose root faded in. A wisp is 2-3 thin
  cards of separate thick hairs on a tile whose root starts at full strength, rooted 8 mm inside the hairline. The
  measurement said they were NOT under the skin; the visible part began lower because the root was faded.
- Brick lines across the flow under an alpha test: staggered card roots on a tile that starts as a cut edge.
- Cards as white plates under a rim light: a card is one flat sheet standing for many round hairs; half the
  specular, tinted to the hair.


# Hair cards: the method every card tool shares

1. **Groom a few strand CLUMPS, not the head**: 4-16 variants from dense and opaque to sparse, fly-away and
   tip-heavy.
2. **Bake them orthographically onto a plane = the atlas.** Passes, the union across tools: opacity, depth / height,
   normal, root-to-tip gradient, per-strand id / random, AO, flow (tangent), colour. Unreal's minimal set is
   diffuse, depth, root, unique id (80.lv XGen breakdown); FiberShop writes 10 at 4K (albedo, alpha, height, normal,
   id, root/tip, flow, AO, translucency, specular; snippet); FiberBake (a Blender add-on, GPL, paid) bakes 12 with
   Cycles and packs the atlas: the proof that a Cycles bake of Hair Curves is the Blender way.
3. **Place cards in layers by opacity**: the base layer is the most opaque and hides the scalp; each layer above is
   more transparent; break-up and fly-aways last. Epic's Hair Card Generator tutorial gives the only published
   numbers (a messy bun, LOD 0, ~54.5k triangles):

   | layer | clumps | triangles | atlas islands |
   |---|---|---|---|
   | coverage | 50 | 2,000 | 25 |
   | mid | 200 | 7,500 | 60 |
   | top | 500 | 25,000 | 60 |
   | fly-aways | 371 single-strand cards | 10,000 | 25 |
   | short hairs | 500 | 10,000 | 75 |

   It makes the cards automatically: strands are clustered into clumps, three cards a clump, then the atlas. LODs
   either cut triangles on the same textures or regenerate cards into reserved atlas space.

Tools and what each teaches (none is a dependency: paid ones are method references only):
- Hair Tool (B. Styperek, paid): cards generated from hair curves or a geometry-nodes hair system; bakes normal, AO,
  diffuse, tangent, id, root, flow, depth; automatic UVs (snippet).
- D. Bystedt's "Hair cards from curves" (free geometry nodes): card meshes deformed along hair curves, twist aligned
  to the head surface. Cards from guides need nothing but nodes.
- GS CurveTools is Maya only (curve-controlled cards with per-point width and twist, layers). HairNet makes guides,
  not cards.
- Blender Conference 2024, "Mesh Hair with Geometry Nodes and Hair Curves" (S. Matsumoto): editable cards and tubes
  from nodes, hair curves used to make their textures.
- Hair cap and hairline: only tutorial-level sources. Houdini's docs describe finer "transitional" cards between
  layers; the usual scalp texture baked from the groom + single-strand cards along the hairline has no primary source.

