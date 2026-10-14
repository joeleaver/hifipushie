# Props and environments

Read guide(topic="") (the playbook) first: describe the reference, then work big to small.

## 4b. Props and environments

- Build a repeated thing once: `prefabs` (a chair in its own frame) placed by `instances` (at, rot, scale,
  part); `array` on an element for rows and grids (logs, planks, shingles, legs), with `jitter`. Don't write a
  script that emits hundreds of elements: the spec stays readable and one edit changes every copy.
- Nothing made by hand or grown is uniform. Give arrays `vary` (per-copy ranges for any number: radii,
  bow, size), `flip` (logs alternate butt ends course to course), `jitter`; bones `bow` and `"ends": "flat"`
  for sawn timber; `lumpy` for knots and axe marks. Identical copies at even spacing read as CG at once.
- `tags` (and instance / array names, which are tags automatically) stand for all their members in paint
  `near`, cut `targets` and `delete`.
- Hard surfaces: `box` and `cylinder` blobs with `round`, `hollow` for vessels, and cuts with `targets` so an
  opening only bites what it should. Keep walls >= 2 voxels at the resolution you judge at.
- Prefabs face -Y (their front is local -Y, like a creature), origin on the floor under them (a door's at its
  hinge, the leaf along +X). `look(views=["top"], clip={"z": 2}, instances=True)` is the floor plan with an arrow
  on every instance's front: check it after placing furniture. Nothing else shows a dresser facing the wall.
- Partitions and plain walls are `walls`: a path, a height, boards or solid, and `openings` that cut the wall and
  hang the frame, window and door (hinge side, swing side, angle open). One entry per wall, not a board array,
  cuts, frame and door instances written by hand.
- Set props down with `"on"`: a cup `"on": "table1/top"`, jars on `"shelf#1"`, books on `"bookshelf1/shelf#2"`,
  an apple on the bowl it's in, a barrel on the ground. Give `at` as [x, y]; the z is found (and follows the
  furniture when it moves). Name the element (`table1/top`, `shelf#1`), not the whole piece: the top of a dresser
  with a plate rack is the rack.
- Clutter: `spec["scatter"]` = {name: {"use": {prefab: weight}, "on": support, "count", "area", "spacing", "rot",
  "scale", "seed", "tags"}} lays out instances "on" a shelf, a tabletop or the floor: whole footprints over the
  support, clear of each other, of props already there and of anything above (a plate rack, a wall). `check`
  says when fewer fitted. Footprints are circles round each prefab's origin (a skillet claims its handle's
  reach), so a crowded counter takes nothing more. Paint scattered props by prefab name (`near: ["apple"]`):
  a tag you gave hand-placed ones isn't on them.
- Seams between repeated members (chinking between logs, mortar between rails) are a bone `{"between": array,
  "inset"}`: it follows every copy's bow and gap. A flat slab behind irregular logs either peeks through as
  ragged streaks or bulges out.
- Vessels and fixtures (tubs, basins, sinks, jugs, pots): the body is ONE shape that already has the form (a
  round cone lying along the tub, widest near the rim: raise its axis and stretch its section down with `flat`;
  a half ellipsoid for a basin; a rounded box for a sink), `hollow`, with a box cut targeted at it to open the
  top. A rolled rim is the same shape grown a little, hollowed thicker and cut to a band at the rim height: a rim
  of a different shape floats beside the body with a dark gap. Set it down with `"on"` (a bowl whose centre
  was put by hand sank into the stand and showed the wood through its bottom), and a set-in sink needs its hole
  cut through the counter's body as well as its top. Judge thin walls in a close-up or the painted scene
  (prefabs mesh at their own voxel): a whole-model clay view shreds 9 mm walls. `examples/fixtures.json`
  has a clawfoot tub, a washbasin, a jug, a set-in sink and a hand pump to start from.
- Small loose props (bread, a book, a cup) are prefabs even when there's one: a prefab meshes in its own box at
  a voxel for its size, while an element in a big part shares that part's voxel (the bread came out at 30 mm).
- `check` walks a person through every door opening and names what blocks it (a door swung across the
  doorway, a chair). Model some ground (a big box, part "ground", lumpy) if there are props outside.
- `check` also lists props cutting into anything ("chair3 cuts 45 mm into table1/leg#2"): fix them by moving the
  prop, not by ignoring the list. Mark what's made to sit into things `prefabs.<p>.embed: true` (window and door
  frames in their walls) and parts that give `parts.<p>.soft: true` (rugs, bedding, cushions: feet sink into them).
  Moving one thing to fix a clash can make another (a stool moved into the bathroom doorway): read the doorways
  too.
- Cameras: `eye: [x, y]` stands a person there; asked to stand on a counter, bed or table, they step off onto the
  floor beside it (the info line says so). Give a 3D eye to put the camera anywhere.
