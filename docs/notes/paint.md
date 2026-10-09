# hifipushie notes: paint

Moved out of CLAUDE.md on 2026-10-09 so agents don't load every thread's history.

- `paint.py`: `spec["paint"]` layers. Most generators compile to shader nodes (`paintnodes`); what nodes can't
  do (paths, near distances, blur, ".L" mirroring, weave) is evaluated per point here (`layer_mask`,
  `_generate` on a `surface.Points`) and handed to the scene as vertex attributes. Paint never rebuilds geometry. `spec.geometry` strips paint and plan before expansion/compilation: keep it that way, or every paint
  edit re-seats strokes and rebuilds. A layer's mask (`layer_mask`) is a stack: flat keys become leading
  multiply entries, then `"mask": [...]`; each entry is one generator (`_generate`: path seated with the stroke
  machinery, `strokes._generate`, as a sum of dabs with a faces-the-same-way test against print-through; near
  (primitives' own SDFs; kit names expand to `<stem>_*<sfx>`); facing; axis; cavity; noise (value fBm on rotated
  lattices, optional stretch/domain warp); cells (3D Voronoi F1/F2/id); ao; thickness; nested mask) then
  `_post` (breakup = noise-shifted threshold, levels, invert), then blended. `blur` averages at jittered points
  (`_View.jittered`) but only where a cell grid of the unblurred mask shows variation (`_blurred`): keep that,
  it's 10x. ".L" layers take the max of the stack at the point and its mirror (`_View` mirrors position and
  normal; field inputs stay the point's own). `bump`: layers' `height` x mask summed, slope by central
  differences across the surface, tilts normals (vertex normals in look, the normal map + height map in the
  bake). Coverage counts only points not `hidden`. Colours are sRGB everywhere in the spec; `blender_render`
  converts part/paint colours to linear for the colour attribute. OBJ export writes `v x y z r g b` (Blender
  reads it). `look(shading="flat")` is unlit colour.

