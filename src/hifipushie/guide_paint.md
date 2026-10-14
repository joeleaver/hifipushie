# Paint

Read guide(topic="") (the playbook) first: describe the reference, then work big to small.

## 5. Paint

Paint is colour (and roughness, metallic, specular, height) laid on the finished surface: `spec["paint"]`
layers, applied in order over each part's clay colour (`parts[p].color`). Every mask is evaluated per point,
at mesh vertices in `look` and at every texel in `export_asset`, so the same spec gives the same result, only
sharper in the export. It never touches geometry, so a paint edit re-renders in a few seconds.
Colours are sRGB as you'd pick them (`"#7d8c5a"` or `[0.49, 0.55, 0.35]`).

- **Work like a painter, broad to fine:** a base colour per part (a layer with no mask), then big zones
  (`facing` for countershading: dark back `[0, 0.6, 0.8]`, pale belly `[0, -0.3, -1]`), then regions
  (`near` elements or a kit name: `"hand.L"`, `"face_eye.L"`, with `within` ~ the blend radius), then
  markings (`path`, addressed exactly like strokes; `repeat`/`scatter` for stripes and spots), then
  breakup (`noise` for mottling, `cavity: "concave"` for dirt in creases) at partial opacity.
- **Masks multiply**, so confine a broad mask with a local one: an `axis` along a bone ramps across the
  whole part (the feet lie past a forearm's end too), so a glove is `near: ["forearm.L", "hand.L"]` plus
  the axis ramp.
- **Check coverage** with `look(paint_layer=...)`: its info line gives the share of the surface in view the
  layer lands on. NOTHING means misaddressed; far more than you meant means a mask too loose (`within`, `range`).
- Judge with `shading="flat"` (unlit colour: exactly what you painted) and the clay view (how it reads with
  form). Paint can't be finer than the mesh: ~1 voxel full-body, finer in close-ups; markings a few mm wide
  need a close-up to judge.
- **Weathering comes from the surface, not from placing it by hand** (Substance-style smart masks). A layer's
  `"mask": [...]` stack combines generators with blend modes: `ao` (occluded places), `cavity` (creases /
  ridges), `thickness` (thin ears, fingers), `facing`, `noise` (`warp` for torn grunge, `stretch` for
  streaks and drips), `cells` (voronoi: scales, cracks, plates, warts), plus paths and regions. `breakup`
  on an entry lets noise eat into it crisply: convex cavity + breakup = edge wear, ao + breakup = grime,
  facing up + breakup = dust. `kit_reference` (PAINT) has the recipes. Keep each effect its own layer, and
  look at it alone with `look(paint_layer="grime")` (false colour: purple 0, yellow 1) before judging colour.
- **Materials first for props and clothing:** `{"material": "planks", "part": "floor"}` (or cloth, leather,
  wood, brick, stone, metal, rust) expands into base colour, pattern, relief, wear and dirt layers; masks on
  it confine it, `color`/`scale`/`wear`/`dirt`/`dir` tune it. Tiles and weaves are laid out triplanar: clean on
  flat walls and floors, blended on curved surfaces, so orient `dir` along the grain or rows.
  For anything built of many pieces (log walls, furniture, frames, firewood) give wood `"dir": "element"`: the
  grain follows each log, leg, rail and board, each its own piece of pattern, end grain on each piece's cut ends.
  One layer does a whole part; no layer per orientation.
- **One value per element:** `{"random": {"range": [lo, hi], "seed"}}` is 0..1 per element (every book, board,
  stone, array copy). Stack layers with rising narrow ranges ([0.25, 0.26], [0.5, 0.51], [0.75, 0.76]) for a
  quarter of the books in each colour; a wide range at low opacity for board-to-board tone. Prefab instances
  share one bake, so they share values.
- **Dust and other "tops" masks on small round props:** a `facing` range starting low (0.3-0.5) wraps the mask over
  rounded rims and lids, and its breakup tears the edge: the lids read crumpled. Start it high ([0.85, 0.98]) so
  only flat tops take it; look at the layer alone on a small prop before judging.
- **Relief without sculpting:** `"height": -0.001` on a cells layer grooves the scale borders; `0.002` on a
  cells-distance layer raises warts. It lands in the exported normal and height maps at texel resolution;
  `look` only tilts vertex normals, so judge it in a close-up with `shading="raking"` and on the exported GLB
  in EEVEE. Sculpt forms bigger than a few voxels with strokes instead.
- **Painted by hand:** when a mask is easier to paint than to describe (a worn path across a floor, a stain where
  someone set a pot down), give the layer `"painted": "new"` and `sync`. Every object of the layer's parts gets a
  colour attribute `hp_paint:<layer>`. The person (or you, over the Blender MCP) paints it in Vertex Paint, white =
  1. The next `pull`/`sync` stores it as a point cloud and writes its id into the layer. It survives re-meshing
  and model edits nearby, and works in stacks like any generator: multiply it with `noise` breakup so the painted
  edge isn't the brush's.
- **Images (a painting, a printed page, a poster, a label, a logo):** the `image` generator lays an image file or
  set text on the surface as a decal projected along `dir`. Give the thing it's printed on its own part (the
  canvas, the page, the disc), so the projection can't land on the frame or wall behind it:
  `{"part": "canvas", "color": "image", "image": {"file": "examples/images/landscape.jpg", "at": "canvas",
  "dir": "front", "size": [0.62, null]}}` (a blob's "front" = its local -Y face; `null` = from the image's aspect).
  Text: `"image": {"text": {"string": "...", "font": "serif", "size": 0.004, "align": "justify"}, "at": [x, y, z],
  "dir": [0, 0, 1], "up": [0, 1, 0], "size": [0.145, 0.21]}` (the page; `size` of the text = em height in m).
  `"color": "image"` paints the picture's colours; with a plain colour or in a mask stack it's a stencil
  (`channel` alpha / luma / r / g / b / coverage). Relief: a second layer `{"height": 0.0003, "image": {...,
  "channel": "luma"}}` (impasto, embossing). Foil: add `metallic`/`roughness` to the colour layer. A file is copied
  into `workspace/_images/` at save and named by its id. `look` draws decals per pixel (text readable in close-ups);
  exports raise the texel density over each decal (up to 2000/m: 4 mm text needs ~0.4 mm texels, ~10 per em; at
  2.5 mm it's grey smudges). A placement that hits nothing on the layer's part is refused at save. Planar
  projection stretches on steep curvature (a mug's sides past ~45 deg): wrap it instead (`"wrap"`):
  - `"cylinder"`: a label round a can, mug, bottle, a print round a sleeve. `"axis"`: a bone, [joint, joint],
    [x, y, z] with `at`, or {"at", "dir"}; default the `at` blob's own axis (a cylinder blob). `at` sets the
    label's height; `dir` the way its centre faces (default front). Width as `size` [w, h] in metres round the
    surface, or `"span"`: degrees round (then `size` [null, h] or the image's aspect). `"seam"`: where the wrap is
    cut (deg from the centre, default 180: behind). The surface's taper at the label is measured: on a taper (a
    bottle's shoulder) it's fan-cut like a paper neck label (rows round the axis, the ends along the cone's lines,
    even height; `"unroll": "cone"`), else a cylinder; `"unroll": "arc"` keeps each row's true length at its own
    radius instead (the ends lean on a taper). Mug: `{"file": ..., "wrap": "cylinder", "at": "body", "span": 300,
    "size": [null, 0.066]}` (the seam behind, the handle in the gap).
  - `"sphere"`: a globe or a ball: `at` = the centre, `axis` = the poles (default the blob's z), `span`
    [round, up] in degrees ([360, 180]: an equirectangular map), or `size` in metres at the surface.
  - `"surface"`: a sticker that lies on any curved surface like paper (a ball, a car door, a helmet): geodesic
    coordinates from its centre (`at`, seated on the surface; `up` orients it). Measured per vertex on its own
    fine mesh (the vector heat method's log map: angles within ~0.1 deg out to the corners of a sticker the size
    of the ball's radius), the picture sampled per pixel; stretch left is the surface's own curvature. Costs a
    few seconds once per placement (cached).
  Wraps measure the surface of the layer's parts (`"on"`: other parts). `"style": true` runs the picture's
  colours through the paint style's saturation/value. `.L` layers and `"mirror"` mirror wraps too.
  Placing by hand: after a `sync` every decal is a wire gizmo in the scene (collection "decals"; layers placed
  alike, a picture and its relief, share one). Move, turn or scale it in Blender and `pull` (or the next `sync`)
  writes it back: near its joint/blob as `"offset"` (world [x, y, z], so it keeps riding the blob), further than
  its own size away as a world `at`; a spin about its normal as `rotate`, a tilt as `dir`/`up`, a scale as
  `size`; a wrap's height (offset), turn round its axis (`dir`), tilt (`axis`), scale (`span`/`size`).
  Exports: the export report's `parts.<p>.seams` says whether the baked maps run on across UV chart borders
  (`excess` ~1 = invisible; > 1.5 is a WARNING in the log). Texels past each island are filled across its seam.
- Eyes, teeth and clothing are best as their own parts with their own colour; a `near` mask around the eye
  also paints the eyeball if the eyeball is in the body part.
