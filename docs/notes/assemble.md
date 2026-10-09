# hifipushie notes: assemble

Moved out of CLAUDE.md on 2026-10-09 so agents don't load every thread's history.

- `assemble.py`: prefabs/instances and element `array`s expand into plain joints/bones/blobs before kits
  (`kits.expand` calls `assemble.expand`, content-cached), so everything downstream sees ordinary elements.
  `select` resolves names/tags (instances, arrays and `tags` lists are tags). `spec._csg` wraps a primitive as
  kind "csg" (`sdf.sd_csg`) for `hollow` and for subtract/intersect elements with `targets` (the cut is folded
  into each target, not a primitive of its own). Cuts only raise the field, so bounds/reach stay the target's.
  A subtract is folded only into targets its box (+ blend) overlaps: every log carrying every window cut made
  moving one window re-mesh the whole wall (the scene's per-part grids diff primitive fingerprints).
  Order in `expand`: `_walls` (spec["walls"] -> board/box blobs, targeted box cuts, frame/window/door instances
  tagged "from_wall" so `placements` and `scene.pull` know them; pull writes a swung door back as the opening's
  "open"), instances without "on" placed, arrays (then `_between`: flat bones between neighbouring copies of a
  bone array, found along its first step's offset; `_arrays_of` remembers the steps during expansion),
  then "on" instances (`_place_on`, dependency order; `top_of` raycasts a mini-spec of the named elements plus
  cuts into them; resolved positions go to `_ON[key]` so `placements` agrees), then weather on elements.
  `placements` pads [x, y] ats and includes wall-generated instances.

