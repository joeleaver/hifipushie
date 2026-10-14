# Seeing and showing

Read guide(topic="") (the playbook) first: describe the reference, then work big to small.


- `look`, `check` and `set_plan` return images to you. The person you're working with may not see tool
  images: pass `save="/path/file.png"` and share the file when they should see progress.
- Judge from the right view. Clay (default) for overall read; `shading="raking"` for masses, planes and
  shallow forms (clay hides them); `shading="curvature"` for blobbiness (an evenly tinted area is a blob)
  and for defects (stripes, speckle, kinks); `strokes=True` to check *where* strokes are before judging
  *what* they look like. Close-ups (`focus` + `zoom` 3-6) rebuild just that region at full resolution:
  judge faces, hands and every detail there, never from a full-body render.
- A close-up box cuts the model: flat caps where it crosses the body are the cut, not holes.
- See inside and underneath without a second model: `hide_parts=["roof"]` / `only_parts=["shorts"]` (no
  rebuild; the body under clothes, one part alone), `clip={"z": 2.2}` with `views=["top"]` for a floor plan
  (`{"-y": 0}` cuts off the front half; `{"point", "normal"}` any plane). Cut solids get flat caps in their
  part's colour, darkened: dark bands are cut walls, not paint.
- Environments: `camera={"eye": [x, y], "target": [x, y, z], "fov": 70}` renders a perspective panel from a
  person standing at (x, y) (eye 1.6 m above the floor found there); give a list for several. Judge a room
  from eye height, not only from outside. Perspective panels have no rulers: take sizes from the plan view or
  `clearance`, which answers "can someone walk here" in numbers: a top-view map of walkable floor, headroom
  and floor flatness over a region, or the clear width/height along a path through a doorway.
- Painting a big environment is the slow part of a look (AO at every vertex, ~2 min at 700k verts, once per
  build). Hidden, clipped and out-of-camera geometry isn't painted, and once the whole model has been painted,
  hide/clip/camera looks reuse it.
