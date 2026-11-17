# Artist retopo: a fused concept sculpt -> a rigged game character

For cartoon / Pixar-style / non-realistic characters and most organic shapes. The input is a fused mesh made from a
concept image (oxidegen `make_point_cloud`: its `mesh_ply` file): a dense, lumpy, one-piece SCULPT with vertex colours.
You retopologise it the way a human artist does: you study it, decide where every loop goes, and write a LOW CAGE of
quads as code. The tools subdivide it, press it onto the sculpt, bake the sculpt's detail and colour into normal and
colour maps, rig it, and bend it through a range of motion so you can see where it breaks.

Your decisions are the product: which loops, where, how many, what is invented. The tools give you slices, gridded
views, numbers, and refuse a broken cage. Nothing chooses loops for you.

Two worked characters are the reference for every decision below: `examples/retopo/mabel_cage.py` (a cow on two
legs: arms fused to the torso, wide stubby legs, painted eyes, horns, ears, a big muzzle with a mouth) and
`examples/retopo/scraps_cage.py` (a goat: thin legs, googly eyeballs and a gas-mask canister held in the teeth, both
rebuilt as primitives, fur drips, swept horns, crescent ears): guide(topic="retopo_mabel") and
guide(topic="retopo_scraps") show them. Read the one closest to your character before you write a line; copy its
structure, never its numbers.

## The frame
Metres-ish (a fused concept spans about one unit), z up, the character faces -y, its left is +x, mirror plane x = 0.
oxidegen's mesh_ply: feet on z = 0, but turned by the concept camera's yaw (a 3/4 concept leaves the character ~30
deg off the front): `retopo_start` finds its mirror plane and turns it back (it says by how much); check the face
really looks toward -y. (The two examples were made in an older frame centred on the origin, feet at z -0.5: their
numbers are theirs.) Paired parts are built once in a `for sd in (+1, -1):` loop with x * sd.
Horizontal ring directions: `az(deg)`, 0 = front (-y), 90 = +x side, 180 = back, 270 = -x.

## The steps (tools; each makes files in the character's folder; each is its own call)
1. `retopo_start(name, mesh, concept)`: copy the sculpt and the concept; input check (watertight, outward, symmetric);
   a gridded front / side / top sheet. Look at it beside the concept: is the face really toward -y?
2. Study: `retopo_slices` (horizontal and vertical cuts with numbers), `retopo_look` (gridded views of any part,
   `centre` + `scale` to frame a head or a hand), `retopo_measure` (a tip's extreme vertex, ray hits, a part's
   thickness, the colour at a point). Write down the numbers you will use (see "Study").
3. Eyes and props: if the concept has eyeballs that stand out (googly eyes) or a held / worn hard object (a canister,
   a cup, a weapon), rebuild each as a primitive: `retopo_fit` (sphere; pick an eye's vertices by colour: read the
   colour with `retopo_measure what="colour"`), `retopo_fit_cylinder` (from cross-sections), then `retopo_primitives` (cut
   them out of the sculpt -> high_body.ply). Skip for painted eyes and soft parts.
4. `retopo_cage(name, code)`: your cage. Refused if it isn't a closed quad manifold (the refusal names the open
   edges' places). Look at the red cage over the sculpt from every side before going on.
5. `retopo_press`: subdivide, press, relax. Folds are counted and listed; look at them:
   `retopo_look(mesh="low", style="wire", folds=True, centre=..., scale=...)`. `retopo_check` repeats any check.
6. `retopo_bake` (UVs from your seams, raw normal + colour bakes and masks) -> `retopo_fill` (the repairs) ->
   `retopo_assemble` (final.glb, shown beside the sculpt). `retopo_compare` renders any result beside the sculpt from
   any view; `retopo_look(mesh="final", style="flat")` shows the maps alone.
7. `retopo_armature(name, joints)`: the skeleton from your joints, weights, LOD1 weights -> rigged.glb.
8. `retopo_rom`: the range of motion (16 standard poses, or yours): numbers, a sheet, close-ups (red faces: edges
   squashed below half or stretched past 1.8 x their rest length). Fix the worst pose at its cause (a loop, a joint,
   a pin), not with a weight knob.
9. `retopo_lod` (LOD1 rigged on its own), then `retopo_report`.

## Study (before any code)
An artist turns the model round and measures it. You slice it.
- `retopo_slices(axis="z", at=[...])` every 3-5 cm from the feet to the crown: each region's centroid and extent. The
  torso is the big region; arms and legs are the small ones beside / under it. Where an arm's region MERGES with the
  torso's (one region where you expected two), the concept drew the arm pressed to the body: the arms are FUSED there
  (decision below). A leg's width tells you thin (< ~1/3 of the hip width) or wide.
- `retopo_slices(axis="x", at=[...])` through an ear or a horn sideways; `axis="y"` along a horn that sweeps back.
- `retopo_look(mesh="high", centre=<head>, scale=0.4 * height)`: eyes, muzzle, mouth line, ear and horn roots; read
  their centres off the grid.
- Write a short list before coding: ring heights (hips, waist, chest, armpit, shoulder top, neck, under the jaw,
  cheeks, eyes, brow, crown), the arm's thickness and its free part's start, leg thickness, muzzle oval (centre,
  half width, half height), eye centres, ear and horn root positions and tip boxes.

## The cage
### Principles
- Quads only, closed, every vertex on a face. 16 round every body ring (k: 0 front, 4 +x side, 8 back, 12 -x side);
  6 round a thin limb, 6 round a horn, 8 round an ear, 12 round the muzzle root. Same counts ring to ring.
- A ring is a CONTOUR: `c.hring(z, dirs, centre, pick)` slices at z, takes the region nearest `pick`, puts a vertex
  where each direction's ray from `centre` leaves it. Down a limb, every ring uses the SAME directions as the hole it
  grows from (`c.dirs_from(hole, centre)`): no twist. A crescent section (a cupped ear) breaks centre rays: use
  `c.ring_even` (the outline resampled by length).
- A limb grows out of a HOLE: leave cells out of a band (`c.bridge(a, b, skip={...})`) and list the hole's boundary
  in order; the limb's first ring bridges to it. Holes come in sizes 2 x 1 cells (6 vertices: a thin arm or horn) and
  2 x 2 (8: an eye, an ear).
- Ends close with `c.cap_grid` (crown 6 x 2, pelvis floor 4 x 4, hoof 3 x 2), `c.cap6` / `c.cap8`, or to a point
  (`c.close_to(ring, tip)`).
- Every position comes from the sculpt (a slice, a ray, `c.front(x, z)`, `c.closest(p)`) or is INVENTED on purpose
  and pinned (`c.pin`): pinned vertices are not pressed; subdivision interpolates them. Invent where the sculpt has no
  usable surface: under a fused arm, behind a prop, inside the mouth and eyes, across a deep crease.
- Mirror by building both sides in one loop over `sd`. The cage is your code: comment each decision with its reason
  (the comments are your decision log's evidence).

### Torso and neck
Rings from the hips to the shoulder tops (5-6 rings), the neck (2), then the head rings. Ring centres on the mirror
plane: `centre=c.centre_of(z, pick)`. The shoulder holes are cells left out of the top band: `skip={3, 4, 11, 12}`.

### Shoulders, and arms fused to the body
The shoulder root must be AS TALL AS THE ARM IS THICK (armpit to shoulder top = the arm's own thickness): a small root
necks the raised arm through a hole. If the slices show the arm fused to the torso (the concept drew arms down):
1. put the real armpit at the height that gives that root, even if the sculpt is fused above it;
2. under the arm, the torso's side carries on as an INVENTED surface: move those ring vertices to the torso's real
   half width and pin them (Mabel: `TORSO_SIDE`);
3. the arm grows on smooth vertex TRACKS from the root to its first free ring: `mids = c.tracks(hole, ring0, down,
   pinned_out=(sd, 0, 0))` (cubic Hermite: each track leaves the body along the sculpt's normal and arrives along the
   arm; tracks starting on invented vertices leave sideways and stay invented). Bridge hole -> mids -> rings.
The rig adds a shoulder half-angle helper and gives the clavicle 0.3 of any arm lift past 60 deg.

### Limbs fused along their length (a wing pressed to the flank, an arm glued to the side)
Where the slices show one region for body + limb all the way down, give the limb its own cross-section: `c.ring_clip(
origin, normal, u, v, n, keep_side=((x_in, y), (1, 0)), pick2d, start_dir)` keeps the part of the contour beyond the
flank line x_in (measured per height: where the body's side would be), resamples it evenly and pins the vertices on
the cut (the limb's invented inner side). The torso's vertices under the limb are invented ~1.2 cm inside x_in.

### Wings
A wing is an ARM: the Mixamo arm chain inside the paddle (shoulder at the wing root, elbow and wrist along its
leading edge) plus finger chains across the tip: joints `"fingers": {"Index": [4 points], "Middle": [...], "Ring":
[...]}` (left side) add LeftHandIndex1..3 etc. A folding / grip pose: the upper arm aimed at an elbow point beside the
belly, the forearm aimed at the rim, the fingers curled about their own x axis (`["LeftHandIndex1", "lx", -40]` for
each joint of each finger). No wing loops of their own yet: build it from ring_clip contours like a fused arm.

### Feet with toes (a bird's foot, a paw)
A foot HUB: the leg's last ring, two rings round the foot (6 round, the band's FACES centred on the toe directions),
holes left in the band between them for each toe (`bridge(hub0, hub1, skip={faces})`), the sole a cap grid. Each toe
a 4-ring tube out of its hole: rings in planes across the toe at fractions of its length; its tip is the sculpt's
furthest point inside a narrow cone round the toe's guessed direction (`c.extreme_cone(hub_centre, direction, 12)`:
a box tip picks the neighbouring toe); close a 4-ring toe with `c.close_small(ring, tip)` (a tip ring and one quad:
a fan of quads to a point folds).

### Legs: thin or wide
- THIN legs (a goat's, a bird's): close the torso with a pelvis FLOOR (`cap_grid(T[0], 4, 4, ...)`) and cut a hole
  in it per leg, sized to the leg (`holes={(3, 1), (3, 2), (0, 1), (0, 2)}`). The crotch between the holes belongs to
  the hips. (A half-hip loop as the root of a 5 cm leg swings the whole crotch with it.)
- WIDE stubby legs (a cow's, a bear's): split the hip ring through one crotch vertex (`c.bottom(0, y)`, pinned with the
  back's middle vertex: a deep crease, relaxed across); each leg loop = half the hip ring + the crotch vertex.
Seams: the root loop, an inner line down the leg (the vertex facing the other leg), the sole.

### Head
Rings under the jaw, cheeks, eye bottoms, eye middles, brow, crown, closed by a 6 x 2 grid (from inside the head
looking up when the crown is lumpy). Deep creases are PINNED so the press relaxes across them instead of into them:
the throat under an overhanging jaw, the jaw's corners where that crease turns up the cheek.

### Muzzle and mouth
- The muzzle's ROOT is its own oval loop of 12, seen from the front (centre, half width, half height measured from the
  front view), made from the head rings' vertices moved onto the oval (`c.front(x, z)`; below the chin from under it).
- Concentric loops forward to the nose pad: `c.inset(root, centre_xz, 0.78)` then `0.5`, bridged.
- The MOUTH: the small loop's bottom arc (lip=[1, 2, 3]) and its corners (0, 4) go ON the lip crease: look at the
  muzzle from the side; where an upper lip overhangs, the crease is a notch under it, not the inset loop's arc on the
  front (Mabel's sat 3 cm too high and read as a smile): `c.put(r2[k], c.crease(c.V[r2[k]][0], z_lo, z_hi))`.
  `c.mouth(r1, r2, lip=[1, 2, 3])` splits it into two lip lines 0.5 mm apart (both pinned: pressed, they weld shut;
  further apart, the subdivided slit gapes), closes the upper lip / nose pad with a grid, adds the mouth bag
  ("sock": ellipse rings with real height behind the slit; a flat bag folds over itself when the jaw opens) and its
  cap (a thin lip-roll ring first, so the lips meet at rest), and writes the groups `jaw` (lower lip, the loop below it, the bag's lower half; corners 0.5), `mouth_inside`
  (painted dark, flat normals; head + jaw weights only) and `freeze` (not relaxed). `jaw_extra=[...]`: chin vertices
  that ride the jaw too. A prop held in the teeth: the lips and jaw WRAP a shell just outside it (invented, pinned).

### A beak (or any mouth that opens along a line through the muzzle)
The beak is a muzzle: its root loop, concentric insets, a cap grid to the tip. It opens along a PATH from each corner
at the base through the loops to the tip: `up = c.split(path_inner)` copies the path's inner vertices 1.5 mm up and
gives the faces above them the copies (both lines pinned); the opening loop is `[corner] + path + [corner] + [up[i]
for i in reversed(path)]`; `rings, cap = c.bag(opening, rings=((0.75, 0.045, 0.016), (0.5, 0.075, 0.022)))` puts the
sock behind it. Write the groups yourself as `c.mouth` does: jaw (the lower half of the beak and of every ring, the
corners and the base row 0.5, the cap's front row 1, its middle 0.5), mouth_inside (the rings + cap less the opening),
freeze (opening + rings + cap). And `head_only` (next).

### head_only: a muzzle or beak that sits on the chest
`c.groups["head_only"] = set(root) | {the insets, the cap grid, the opening, the bag}`: the rig blends those vertices
to Head (keeping their Jaw share). Without it a beak resting on the chest has its lower half owned by Neck / Spine and
smears when the head turns.

### Eyes
- Painted / flat eyes: an eye hole of 4 cells, two concentric insets (0.62, 0.3), one quad. The eye loops sit on the
  muzzle's top edge and under the brow.
- Eyeballs that stand out (googly): rebuild each as a sphere (`retopo_fit`, then `retopo_primitives`). Snap the eye hole
  onto the circle where the eyeball meets the skin (`c.snap_to_sphere(hole, centre, R + 4 mm, axis, 62)`, each
  vertex keeping its angle round the eye axis, then `c.closest`), a lid ring ON the eyeball (52 deg), a hidden ring
  inside it (35 deg) and a `cap8`, all pinned. The eyeball is parented rigidly to the Head bone.

### Ears
Out of a 2 x 2 hole in the head bands. Rings in planes x = const going outward: `c.ring_even((x * sd, 0, 0), X, Y, Z,
8, pick, start_dir)` (an ear's section is a crescent). Close to the ear's REAL tip: `c.close_to(ring,
c.extreme(box_lo, box_hi, (sd, 0, 0)))`, the whole sculpt's furthest vertex out that way.

### Horns
Out of two cells of the crown grid. Rings in planes across the horn (z = const for a horn going up, y = const for one
sweeping back). EVEN the root's directions round the tube (`dirs` at equal angles starting from the hole's first
vertex): a hole's 3-on-top / 3-below directions make a crease along the horn. The hole's front edge becomes the
horn's top when it rises and sweeps back. Close to the extreme vertex along the horn (`c.extreme`).

### Soft parts kept as their own pieces (a comb, a wattle, a crest)
1. Cut it out: `retopo_primitives(parts=[{name, cut: [shapes], bone, extrusion, reach, near}])` -> part_<name>.ply (it
   rides `bone` by name: a wattle the Jaw, a comb the Head). Skin within 2.5 cm of it bakes as invented.
2. Its own small cage: `retopo_cage(name, code, part=<name>)` (rings sliced off the whole sculpt; `low`, the pressed
   body, is in scope). Clip its base UNDER THE BODY's own surface ring by ring: `c.ring_clip(..., keep_side=((0.0,
   low.top(0, y)[2] - 0.008), (0, 1)), ...)` (a flat cut leaves it floating over a sloping crown with a dark gap). A
   lobe lying against the body (a wattle on the collar) can't be parted by a slice: rings from its own cut-out points
   (part_<name>.ply), idealised (an ellipse per height, smoothed along it).
3. `retopo_press(name, part=<name>)`; the bake picks it up (its extrusion / reach; texels within `near` of the body are
   invented: its base bakes the skin); the fill refills its CONTACT SHADOW (texels darker than 0.6 x its median: the
   splat baked the body's shadow into it).

### Props and accessories
A hard object (canister, cup, gem, button eye) is a primitive, not part of the skin: `retopo_primitives` items
`{name, type: cylinder|sphere, axis, c, R, length, bone}` (bone "Jaw" for a thing held in the teeth, else "Head" or
leave it). Measure it from x-plane cross-sections (`retopo_slices(axis="x")`). The cut (`cut` shapes, or each
primitive grown 6 mm) leaves the skin around it open: slice rings off the WHOLE sculpt (closed contours; the tools do)
while rays and the press land on the body. A ring that would land on the prop is invented as a shell just outside it.

### Messy surfaces (fur clumps, drips, wool)
Press at a COARSE level (`levels=1`: ~2 cm quads can't follow clumps), then subdivide once more UNPRESSED
(`after=1`): the form stays clean and the clumps return through the normal map (bake extrusion 2 cm, reach 4 cm).
Smoothing the sculpt first (Taubin) barely moves fur: don't.

### Seams (UVs)
Mark them on the cage (`c.seam(loop)`, `c.seam(chain, closed=False)`); Catmull-Clark keeps them. The set that worked:
down the back (crown to pelvis), every limb root + an inner line down the limb + the sole, ear and horn roots (+ an
ear's inner line), eye holes, the NECK ring (the head is its own island: the face gets texels).

## Press (`retopo_press`)
Defaults are the ones that worked: `levels=1, relax=6, after=1` -> ~9k quads for a 0.5k-quad cage; LOD1 is the
pressed level-1 mesh (~2.3k quads, the same loops). Pressing is along normals both ways (3 cm limit): thin and
touching parts keep their own side. Folds = faces whose normal disagrees with the sculpt's there: on fur ~100 of 9k
are the clumps the form doesn't follow (fine); a cluster on a limb or face is a cage fault (a ring crossing itself, a
hole with twisted order). Look: `retopo_look(mesh="low", style="wire", centre=..., scale=...)`.

## Bake (`retopo_bake`)
- extrusion / reach: a smooth sculpt 0.012 / 0.03; fur, drips, a lumpy coat 0.02 / 0.04.
- Thin parts (ear and horn tips) get a second bake at 4 mm composited by a thickness mask (automatic).
- Repairs (automatic): rays that found nothing are filled from their neighbours; invented skin and skin within
  1.2 cm of a prop read the cut cavity (black), so their colour is diffused over the SURFACE from trusted skin
  (sRGB -> linear first) and their normals are flat; the mouth inside is dark and flat.
- final_cmp.jpg: the sculpt (left) beside yours (right): whole figure, back, head. Judge it: the silhouette, the
  face, the colour patches. Black smudges = a bake miss or an invented area that should be smaller.
- `head=[x, y, z]` frames the head close-up when the default (the top third's centre) misses it.

## Rig (`retopo_armature`)
Joints you give (metres, LEFT side for paired joints; read them off slices and side views; inside the body, at the
joint's pivot, not on the surface): hips, spine, spine1, spine2, neck, head, head_top, clavicle, shoulder, elbow,
wrist, hand_end, hip, knee, ankle, toe, toe_end; for a mouth: jaw (the hinge, under the ear) and jaw_tip (the chin).
The rig: Mixamo bone names (`mixamorig:`), bone heat weights, half-angle helpers on shoulder, elbow and knee, the
clavicle taking 0.3 of an arm lift past 60 deg, a Jaw leaf bone under Head driven by the cage's jaw group, the mouth
inside on the head (+ jaw) only, empty vertices copying their nearest weighted neighbour, props parented rigidly
(eyes to Head; a held prop to Jaw), LOD1 weights copied from the full mesh.

### Weighting passes (automatic, in order)
Bone heat, then: half-angle helpers (shoulder, elbow, knee); the jaw from the cage's group (what bone heat gave the
jaw beyond it goes to Head); feather fingers by geometry (tents along the tip, gaussians across the finger lanes: bone
heat blurs them into each other); head_only to Head; SHOULDERS NEVER OWN THE MIDLINE (a clavicle's weight fades to
Spine2 from 15 % to 60 % of the shoulder's |x|: bone heat gave a chin on the chest to both clavicles); `neck_ramp`;
empty vertices from their nearest neighbour; every short total normalised to 1.
NO NECK (a hen, a blob): give joints `"neck_ramp": [z0, z1]` (the collar band): Spine2 / Neck / Head are re-laid by
height over it so a head turn twists softly through the collar instead of creasing one row. Its head_turn_60 still
counts ~240 stretched edges: pure twist shear (r 0.24 m x 60 deg over 20 cm), it reads fine; 60 deg is a neckless
body's design limit.

### A racer's grip on a wheel
Joints `"wheel": {"c": [x, y, z], "r": radius, "tilt": deg}`, `"grip_deg"` (where on the rim, from 3 o'clock) and
`"fingers"`: retopo_rom adds `wheel_grip`, solved by two-bone IK (each wrist just outside its grip point, elbow out and
down, the hand aimed over the rim) and a search over the fingers' curl (the tips nearest the rim's centre line); the
wheel is drawn only in that pose. Never hand-set grip angles.

## Range of motion (`retopo_rom`)
16 standard poses: rest, arms_side_80, arms_up_150, arms_forward_90, arms_back_40, elbows_120, leg_forward_80, knee_up_100,
leg_back_35, leg_side_40, crouch, spine_forward_40, spine_side_30, spine_twist_45, head_turn_60, head_down_up,
mouth_open_20. The director's limits: arms "up" means each arm AIMED 30 deg off vertical, out to the side, not
straighter (that clips the head; these characters don't need it).
What the two references reached (squashed / stretched edges of ~18k):
| pose | Scraps (thin legs) | Mabel (stubby legs, huge head) |
|---|---|---|
| arms_side_80 | 0 / 0 | 0 / 13 |
| arms_up_150 | 20 / 54 | 24 / 51 |
| elbows_120 | 17 / 0 | 39 / 11 |
| knee_up_100 | 34 / 2 | 133 / 29 |
| crouch | 49 / 0 | 183 / 24 |
| head_turn_60 | 2 / 0 | 13 / 55 |
mouth_open_20's few hundred "stretched" edges are the mouth bag opening: expected. Read the close-ups, not only the
counts: a red band across a joint's crease (knee, elbow) is compression and reads as a crease; a red tear at an
armpit or a lip corner is a fault. Stubby legs crease at the knee whatever the weights (Mabel): accept or rebuild
the leg's loops; huge heads stretch the shoulders in arms_up.
LIMITS ARE PER CHARACTER, not one human table: a short wing paddle can't do elbows_120 (the stretch sits on 0.7 mm
edges at the wing root), a neckless body turns its head 60 deg at most. Run the poses the character really needs,
with its own angles (your own poses, below), and say which standard ones you dropped and why.
Your own poses: `poses=["rest", "arms_up_150", {"wave": [["LeftArm", "aim", [0.5, -0.3, 0.8]],
["LeftForeArm", [1, 0, 0], -60]]}]` (a bone, a world axis and degrees, or "aim" and a direction; the clavicle
share and the half-angle helpers are added for you) and close-ups `close={"wave": {"view": [-0.6, -1, 0.2],
"target": [x, y, z], "scale": 0.3}}` ("wave#2" for a second view of a pose).
Fix at the cause: an armpit tearing = the shoulder root too small or not invented under the arm; a thigh web on
knee_up = a hip loop as the leg's root (use a pelvis floor); a mouth corner tearing = jaw weights missing the 0.5
corners. Weight knobs (global smoothing, limb fades, a hip helper) made every one of these worse.

## Gotchas (each cost a round)
- A closed cage's facing: Blender's recalc guesses inward on some cages; the press re-winds and checks the SIGNED
  VOLUME. Your fused input must have positive volume (retopo_start says).
- Slice the WHOLE sculpt for rings; a cut one (props removed) has open contours (dropped).
- Colour diffusion: the bake's pixels are sRGB; emission is linear: convert before mixing.
- glTF import packs its images: reloading doesn't take; load the file and swap it into the nodes.
- glTF import splits vertices at UV seams: import with merge_vertices=True before weighting (else seams tear).
- Bone heat already makes a vertex group named after the Jaw bone: reuse it; a second "Jaw.001" is never driven.
- Un-subdividing triangles for a LOD leaves speckles: LOD1 is the coarse pressed mesh with its own unwrap and bake.
- Nearest-point pressing folds thin cupped ears and touching armpits: press along normals.
- Texture-space filling pulls colour from unrelated UV neighbours (shards): fill on the surface.
- final.glb / rigged.glb hold LOD1 on top of LOD0: every render but LOD1's own must hide the lod objects, or LOD1's
  bake z-fights through as black "shards" (the dark shards seen on Scraps' lips were this). The tools do.
- A bake ray that meets the sculpt from BEHIND reads its dark interior: coverage counts it as a miss (the tools do);
  colour is spread into invented skin only from skin the bake truly hit.
- An AIMED bone is aimed from its CURRENT direction at pose time (its parent may have moved) and takes no clavicle
  share (that pulls an aimed arm inward); its helper turns half the aim.

## Dead ends
Weight smoothing over the whole body; raising the hips; a thigh-weight fade by distance; a hip half-angle helper
(5 x stretches); Taubin smoothing of fur; a flat copy of the closed slit as the mouth bag; a half-hip loop as a thin
leg's root; ring fitting from a skeleton chain (the old quad-retopo); a rule engine deriving loops from a description
(loop-plan): both replaced by this.

## Not covered yet (extension points)
Wings (Hettie, The Major): rigged as arms + finger chains (above); a wing's own loop layout beyond ring_clip
contours is untested (Hettie is in progress in the oxidegen spike). Soft parts' own cages (comb, wattle), a beak's
mouth split along its mid-line, and toes: in progress there too. Hard-surface props and vehicles (the karts): a different press (no relax across hard edges) and a vehicle rig;
not this path. Hands with fingers: a hand ring + finger holes like an ear's, untested.

## Tool reference

### `retopo_start`
`retopo_start(name, mesh, concept=None)`: name is the character (folder `<HIFIPUSHIE_HOME>/retopo/<name>`; a path
with "/" is used as is). mesh: the fused sculpt PLY (oxidegen make_point_cloud's mesh_ply). concept: the image. Returns
the concept, a gridded front / side / top sheet, the input check (vertices, bounds, height, signed volume, open edges,
parts, mirror error; `faults` must be empty or explained).

### `retopo_look`
`retopo_look(name, mesh="high", views=["front","side","top"], centre=None, scale=None, step=0.05, style="colour",
over=None)`: mesh high | body | cage | low | lod1 | final; views front, back, side (from its left: faces left),
side_r, top, below, 3q, 3qr; centre [x, y, z] and scale (the view's width) frame a part; step the grid spacing;
style colour (vertex colours / textures) | clay | wire; over "cage" draws the cage in red. Grid labels are
coordinates.

### `retopo_slices`
`retopo_slices(name, axis="z", at=[...], mesh="high")`: planes z = const (horizontal; in-plane x across, y up the
sheet) or x / y = const; every region with centroid, ranges, area (cm2), holes, largest first, and one sheet with the
outlines in colour per plane. Use the centroids as rings' `pick` and `centre`.

### `retopo_fit`
`retopo_fit(name, near, radius, rgb=None, tol=60)`: least-squares sphere through the sculpt's vertices within radius
of near (and coloured within tol of rgb 0-255: pick an eye's white or yellow). Returns c, R, rms (rms under ~1.5 mm:
it is a ball).

### `retopo_primitives`
`retopo_primitives(name, eyes=[{c, R}], items=[{name, type, axis, c, R, length, bone}], cut=None, margin=0.006,
parts=[{name, cut: [shapes], bone}])`: writes props.json, high_body.ply (the sculpt minus the cut shapes, biggest part
kept) and part_<name>.ply per part. cut shapes: {type: sphere, c, R} or
{type: cylinder, axis, c, R, span: [lo, hi] along the axis, bounds: {"y": [lo, hi]} optional}. Shows the body.

### `retopo_cage`
`retopo_cage(name, code, part=None)`: code is Python run with: `c` (the Cage), `s` (the body sculpt), `full` (the whole sculpt), `low` (the pressed body, if any),
`props` (props.json), `az`, `X`, `Y`, `Z`, `np`, `math`, `fit_sphere`. Cage API:
- vertices: `c.add(p)`, `c.put(i, p)`, `c.pin(i | [i...])`, `c.V[i]`
- sculpt: `c.front(x, z)`, `c.top(x, y)`, `c.bottom(x, y)`, `c.crease(x, z_lo, z_hi)`, `c.hit(origin, d, last=False)`, `c.closest(p)`,
  `c.centre_of(z, pick)`, `c.extreme(lo, hi, direction)`; `s.slice(origin, normal, u, v)` -> regions (`.centroid`,
  `.area`, `.exterior`, `.contains(p)`, `.ray_exit(c, d)`), `s.normal_at(p)`
- rings: `c.hring(z, dirs, centre=None, pick=(0, 0))`, `c.ring(origin, normal, u, v, dirs, centre2d, pick2d)`,
  `c.ring_even(origin, normal, u, v, n, pick2d, start_dir, ccw=True)`, `c.ring_clip(origin, normal, u, v, n,
  keep_side=((x, y), (nx, ny)), pick2d, start_dir, ccw=True, pin_inner=True)`, `c.dirs_from(loop, centre_xy, axes=(0, 1))`,
  `c.inset(loop, centre_xz, scale)`, `c.snap_to_sphere(loop, centre, R, axis, theta_deg)` (points),
  `c.tracks(hole, ring0, down, pinned_out=None, n=2)` (rings)
- faces: `c.bridge(a, b, skip=())`, `c.bridge_new(prev, points, pin=False)`, `c.quad(a, b, c, d)`,
  `c.cap_grid(loop, nx, ny, interior)` -> {(i, j): vertex}, `c.fill(grid, nx, ny, holes=())`, `c.cap6(r)`,
  `c.cap8(r, centre_point, pin=False)`, `c.close_to(r, tip_point)`
- `c.split(path, offset=(0, 0, 0.0015))` -> {vertex: upper copy}, `c.bag(opening, rings)` -> (rings, cap),
  `c.extreme_cone(origin, direction, deg=12, min_dist=0.03, box=None)`, `c.close_small(ring4, tip)`
- `c.mouth(r1, r2, lip=[1, 2, 3], gap=0.0005, bag=((0.95, 0.005, 0.0015), (0.75, 0.018, 0.016), (0.5, 0.04,
  0.022)), jaw_extra=[])`
- `c.seam(loop, closed=True)`, `c.groups[name] = {vertex: weight} | {vertices}`
Refused (nothing saved past the code) when edges are open, non-manifold, or a face isn't 4 distinct vertices. Notes
(not refusals): inconsistent winding (the press fixes it), quads folded across a diagonal (look at them).

### `retopo_press`
`retopo_press(name, levels=1, relax=6, after=1, part=None)`: see Press (part: a separate part's cage, no LOD1). Returns cage volume, LOD1 quads, low quads, folds (and
where), invented vertices; a sheet of the cage over the sculpt and the low mesh, 4 views.

### `retopo_measure`
`retopo_measure(name, what, point=None, direction=None, lo=None, hi=None, radius=0.01, mesh="high")`: what "extreme"
(lo, hi: the box corners; direction: the vertex furthest that way inside it; a horn / ear tip), "ray" (point,
direction: every hit, nearest first, with its distance), "thickness" (point: from the nearest surface point inward
along its normal to the far side), "colour" (point, radius: the mean vertex colour, 0-255).

### `retopo_check`
`retopo_check(name, what="low")`: "input" (as retopo_start), "cage" (as retopo_cage's refusal), "low" (the press's
numbers + the low mesh's volume and open edges).

### `retopo_fit_cylinder`
`retopo_fit_cylinder(name, axis, at, pick)`: axis x | y | z; at: stations along it (inside the prop); pick: a point in
the section's plane near the prop's centre (axis x: (y, z); y: (x, z); z: (x, y)). Returns c, R, R_spread and every
slice's circle (centre, R, rms): stations whose R departs from the rest are past the cylinder's ends (or a rim:
a second, wider cylinder).

### `retopo_bake`
`retopo_bake(name, res=2048, extrusion=0.012, reach=0.03, thin_extrusion=0.004, thin_reach=0.015)`: see Bake. Writes
the raw maps and masks and low_uv.glb; ~3 minutes on the CPU. Shows the raw colour and normal maps.

### `retopo_fill`
`retopo_fill(name)`: repairs every baked tag (low, lod1, each prop) in place; returns the misses and invented texels
per tag.

### `retopo_assemble`
`retopo_assemble(name)`: the repaired maps into low_uv.glb -> final.glb (body, props, LOD1); renders final_cmp.jpg
(sculpt left, yours right: whole figure 3/4, back, head).

### `retopo_compare`
`retopo_compare(name, result="final.glb", views=None, head=None)`: result final.glb | rigged.glb | lod1_rigged.glb |
low.ply (clay); views [{name, view: [dx, dy, dz] (from the target toward the camera), target: [x, y, z], scale}];
head frames the standard head view.

### `retopo_armature`
`retopo_armature(name, joints, helpers=["Arm","ForeArm","Leg"])`: see Rig. ~1 minute. Writes rigged.glb, rigged.blend,
rig.json (bones, helpers, jaw vertices, which bone holds each prop, LOD1 weights).

### `retopo_rom`
`retopo_rom(name, poses=None, clavicle=0.3, close=None, close_ups=True)`: see Range of motion. ~2-4 minutes. Returns
the ROM sheet (every pose, front + 3/4), the standard close-ups, the mouth close-ups, your close-ups, the numbers.

### `retopo_lod`
`retopo_lod(name)`: LOD1 (the pressed coarse mesh, its own 1K bake, weights copied from the full mesh) with the rig
and props -> lod1_rigged.glb; a picture of it.

### `retopo_report`
`retopo_report(name, decisions, out_dir=None)`: decisions is your log in markdown (what you read off the sculpt, every
loop decision and its reason, each look and what you changed after it, what is still wrong and why). Copies the
deliverables (final.glb, rigged.glb, sheets, numbers, every cage version) and writes report.md.
