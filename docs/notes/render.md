# hifipushie notes: render

Moved out of CLAUDE.md on 2026-10-09 so agents don't load every thread's history.

- `render.py` + `blender_render.py`: headless Blender workbench/matcap renders, contact sheet with rulers.
  `look(strokes=True)` draws stroke paths (visibility by raycasting the field); `shading="raking"` uses a
  generated low-side-light matcap, `"curvature"` colours vertices by the field's Laplacian (convex warm).
  `smin` is cubic (C2): the quadratic one left curvature jumps at every fillet edge, visible in highlights.
  `look(hide_parts/only_parts/clip)` goes through `store.view_mesh` (`<stem>_view.npz`: a face subset, verts
  beyond a clip plane pulled onto it, `src` = indices into the base mesh) and `store.section_caps` (grid cells
  on each plane inside a shown part's exact field, part colour darkened; shell parts only fill what solid parts
  don't, so clothes cut as a rim), loaded by Blender as an extra object. `camera` panels are perspective
  (`render.camera_frame`, `blender_render` switches the camera type per view; no rulers, no stroke overlay);
  an eye [x, y] stands on `measure.stand_height`. Camera-only looks also cull faces outside the frusta.
  Painted looks go to the Blender scene (`scene.look`, see "Next session"); these views are clay per part.
  `measure.clearance` (tool `clearance`): walkability
  from vertical columns of `field_at` (floors, headroom), a capsule clearance test and horizontal width rays.

