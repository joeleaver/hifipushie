# Hair: short cuts as a baked cap + sparse cards (crops, short back and sides)

Read guide(topic="hair") first: describe the hairstyle in words before touching a knob.

A crop of 2-4 cm hair is not built like long hair. Cards cut one per clump read as torn paper or leaf litter at
bust distance, and cards only where hair stands off the head leave a bald dome inside a fringe (both tried). What game hair artists do, as far as it could be sourced:

- **The cap carries the look.** A mesh close over the skull wears a texture of the hair itself; breakdowns say a
  flat colour "can pass" but painted or baked fibres on the cap sell it, and for buzz cuts the advice is to bake the
  strand groom down into the head's texture (The Rookies breakdown; Polycount "hair study: shaved bun"; Thomas
  Pecht's buzz cut is described as "hair cards + baked hair cap, single texture"). Commercial short-hair assets
  ship colour, alpha, depth, direction (flow), id, normal, root and specular maps (3D Scan Store's real-time buzz
  cut); bake tools output flow, height, root / tip, normal and AO.
- **Cards over it are layers of falling opacity**: an opaque base that covers the scalp, then 2-3 sparser break-up
  layers, the last ones for the hairline and fly-aways (80.lv "Tips & tricks on hair for games"; Epic's Hair Card
  Generator: clumps of three cards, single-strand fly-away cards, a card group of its own for the hairline's short
  hairs, and for a buzz cut cards of two triangles). Root alpha fades so cards sink into the scalp; some cards
  stand across the others so the hair is not thick from one side and thin from the other (Polycount).
- **Shading**: anisotropic along the hair with a FLOW map on the cap (Reallusion's hair shader: the flow map
  "overcomes the obtuse look of low-poly hair cards"), depth / id / root packed for the shader (inZOI's mod docs),
  Kajiya-Kay or Marschner-style lobes (Scheuermann 2004; Karis 2016).
- **Alpha**: alpha test alone sparkles and thins with distance; mips must keep the alpha's coverage (Castano,
  "Computing alpha mipmaps"; Unity's mipMapsPreserveCoverage), or use alpha to coverage (Golus) or dither + TAA.
- Budgets seen: 5.3k polygons (a marketplace buzz cut), ~9k triangles single-sided (Jansen Turk's breakdown, which
  of his lengths unstated). Shell "fur" (copies of the mesh along the normals with strand dots) is documented for
  short fur, not found in a shipped human buzz cut.

What the tools build when a loose groom's mean lock is under 6 cm (`hair.SHORT_TIERS`; `hair_cap.py`):

1. **The cap's chart is baked from the strands.** Every strand of the groom (its locks' and the scalp layer's) is
   rasterised onto the scalp chart with a z-buffer by height over the scalp, each 0.55 mm wide in METRES (the
   chart's texels are ~0.3 x 0.1 mm and shrink toward the crown). Per texel: the top strand's value and whether it
   is a grey hair (each lock's own share, x `look.card_grey`, default 0.5: the top strand of every texel, fully lit,
   reads twice as silver as the same share among a path tracer's shadowed hairs), depth (how far it stands over the
   hair around it: the shade between hairs and clumps), a normal map from the strands' heights (`hair_cap.RELIEF`
   0.7 of the real slopes: the relief is what shades the hair darker away from the light), the strand's direction (the flow map). Under the
   strands an OPAQUE base wherever the groom is dense, from `strands.soft` inside the hairline: skin shows only
   where real strands are sparse. The chart is 2048 px; the atlas (tiles | chart) 4096 x 2048.
2. **The cap stands in the hair**, at 0.7 of the hair's height (its 85th percentile) over the scalp (`hair_cap.LIFT`, at most 15 mm), easing
   down to the skin over 12 mm at the hairline: the head's outline is hair, not a skull under a fringe.
3. **Cards everywhere the groom has length**, each standing at the TOP of its clump of strands (`hair.SHORT_TOP` x
   the clump's spread along its normal: a card on the clump's mean line is under the hair's outline), never under
   the cap, roots sunk in it, ending at the hairline (a card's few thick strands past it were wires on the skin), on tiles of a few
   THICK strands (16 / 9 strands a tile, 5-6 texels: a 1 cm card is seen 3-4 mips down, where a hundred 1-texel
   hairs are a grey film that an alpha test turns into a flake). The budget thins them evenly: cards that stand off
   the cap (the lifted front, the outline) and the hairline's go last. Tile strands are straightened (16 cm of
   wave squeezed onto 3 cm were white squiggles) and lit (the cap is the shade under them).
4. **One set of maps for every tier**: `export_hair(textures="shared")` (the default) writes hair_basecolor /
   normal / orm / aux / flow PNGs once and each `<name>_hair_<tier>.glb` refers to them by file name (they were
   embedded four times: 4 x 24 MB). `textures="embedded"` for a single self-contained GLB.
5. The material says KHR_materials_anisotropy with the flow map as its texture (direction in tangent space: red =
   along u, green = up the picture; blue = strength), roughness >= 0.85 (lower, with the strands' relief in the normal map, it shone like gel).

In an engine (checked in Godot 4.7):

- **Mipmaps.** Images a `GLTFDocument` loads at run time have none; the strand texture then sparkles at every
  distance. Import through the editor, or `Image.generate_mipmaps()` on the material's textures. This was most of
  the "sparkle".
- Godot's glTF importer does not read KHR_materials_anisotropy, specular or sheen: set `anisotropy_enabled`,
  `anisotropy` ~0.35 and `anisotropy_flowmap = hair_flow.png` by hand (at 0.6 with the normal map the hair went
  metallic), and `vertex_color_use_as_albedo = true` (COLOR_0 is the cards' root-to-tip ramp).
- Alpha: glTF MASK imports as alpha scissor at the cut-off (0.33). The cap is opaque inside the hairline, so only
  the hairline's band and the cards depend on it; `alpha_antialiasing_mode = ALPHA_TO_COVERAGE` with MSAA softens
  both. Godot has no import option that keeps alpha coverage in the mips: the tiles' strands are drawn thick so they
  survive it.
- The hero tier (16k) spends its extra triangles on a finer cap and twice the cards; at bust distance it is hard to
  tell from main (8k). Use main unless the camera goes closer than a bust shot.

Sources for this section: The Rookies, a real-time hair breakdown (https://www.therookies.co/projects/65082);
Polycount "Hair study: shaved bun" (https://polycount.com/discussion/237326/hair-study-shaved-bun) and "How should I
texture characters hair" (https://polycount.com/discussion/160776/how-should-i-texture-characters-hair), read as
search snippets; 80.lv "Tips & tricks on hair for games" (https://80.lv/articles/tips-tricks-on-hair-for-games/);
Epic, Hair Card Generator (https://dev.epicgames.com/documentation/unreal-engine/hair-card-generator-for-grooms-in-unreal-engine);
3D Scan Store real-time buzz cut (https://www.3dscanstore.com/hair/realtime-hair-buzzcut); Reallusion's hair shader
textures (https://manual.reallusion.com/Character-Creator-4/Content/ENU/4.0/15_Digital_Human_Shader/Hair/Textures-3-4.htm);
inZOI mod docs, hair texture set-up (https://mod-docs.playinzoi.com/docs/modkit-docs/modkit/project/caz/hair/05-texturesetup);
Castano, "Computing alpha mipmaps" (https://ludicon.com/castano/blog/articles/computing-alpha-mipmaps/); Karis, "Physically
based hair shading in Unreal" (https://blog.selfshadow.com/publications/s2016-shading-course/karis/s2016_pbs_epic_hair.pdf);
Godot forum, run-time glTF textures without mipmaps (https://forum.godotengine.org/t/not-applied-mipmap-at-gltf-runtime-loaded-model/94799);
Godot's gltf_document.cpp (no anisotropy / specular / sheen extension). No numbers for a short cut from a named
studio talk were found; a strand's width in texels and "bent normals for caps" have no source (ours by measure).
