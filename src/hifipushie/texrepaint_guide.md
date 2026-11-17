# Texture repaint: redo a generated texture like a texture artist

For models whose colour came from the concept -> Gaussian splats -> fused sculpt -> artist retopo -> bake path. Their
maps are a good START but low-res (splats rendered at 512-768 px), sometimes WRONG on sides the concept never showed
(the image-to-3D model invents a back), and full of diffusion smears (half-letters, melted pictograms). A texture
artist doesn't fix pixels: they read the model as regions and materials, paint each cleanly from the concept, and
redraw graphics.

## Steps (call_tool names)
1. `texrepaint_start(name, glb, turnaround, concept, image, cover, invented)`: registers each turnaround panel to the
   model's silhouette (red outlines: every one must sit on its figure; the front fixes scale and ground line, side and
   back slide only sideways). Proposes a palette from the art where it lands on the model.
2. `texrepaint_regions(name, materials)`: name what a painter would paint separately: base clay, patches, pads, horns,
   pupils. colour = the LIT colour in the concept (shading splits one paint into two palette entries: merge them).
   Small dark features get `zones` (height fractions) so shadows under the body don't read as pupils or hooves.
   Read the contradictions: texture X where the art shows Y, with where and how big. They are fixed by the art;
   what no view shows keeps the texture's reading (the report gives the unseen share per material: say so).
3. `texrepaint_paint(name, keep=[...])`: 4K colour, normal (sculpt kept + material detail), roughness. Painted face
   details (eyes, nostrils, a mouth line) are not regions: point at them with `texrepaint_look` and `keep` them.
4. Graphics: `texrepaint_face(name, part)` shows the face front-on with numbered corners; read the same corners off
   the concept; `texrepaint_decal(...)` redraws it as flat colours with clean shapes. An image model's redraw can be
   passed as `graphic` instead.
5. `texrepaint_render(name)`: before / after, same cameras; judge beside the turnaround, not beside the old texture.

## Traps (each found on Mabel / Scraps / Hettie / Scraps' kart)
- Turnaround backdrops share the character's colours: registration uses the model's OWN texture as the target
  (colour agreement), never a border-colour matte.
- LOD copies share the UVs: texels belong to LOD0 (else the sign's face was LOD1's and came out empty).
- Fused parts can carry flipped normals: a decal face is chosen by position (front half of the plate), not normal.
- A graphic's UV island may be tiny (the kart sign: ~300 x 300 texels at 4K): the decal is clean but its sharpness is
  capped by the island; give hero graphics more UV space at the retopo stage.
- Lightness is half-weighted when classifying, so close values (taupe vs charcoal) flip with baked shading: separate
  them by zones, not by tuning colours.
