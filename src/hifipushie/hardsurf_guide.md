# Hard surface from the point cloud (hardsurf_*)

A concept image becomes a point cloud (oxidegen `make_point_cloud`: Gaussian splats, rendered from 50 views and fused
into a closed mesh). For a CHARACTER you press a cage onto that sculpt (retopo_*). For HARD SURFACE (props, vehicles,
furniture, machines, buildings) you don't: the sculpt is lumpy (3 mm voxels, splat noise), and pressing re-imports the
lumps. A hard-surface artist **measures and idealises**: fits clean primitives to the sculpt, then bakes the colour and
the real detail onto them. Worked example: guide(topic="hardsurf_example") (Hettie's crate kart, Braynard Racing).

## The flow
1. `hardsurf_start` (fused mesh, the renders' views.npz, the concept) -> `hardsurf_frame`: stand it on its footprint,
   square it up, scale to ONE dimension you know (an overall length, a wheelbase, a table height). Check the views:
   the front must face -y. A near-square footprint is warned: give `yaw0` (PCA can't pick the long axis).
2. READ the sculpt against the concept, part by part (`hardsurf_look` with centre/scale for close-ups, `hardsurf_vote`).
   Name every part a modeller would make separately: things that turn, move, or are made of a different material.
3. FIT each part (`hardsurf_fit`):
   - **turned** (anything round about an axis: wheels, cans, bottles, knobs, posts, lamps). The revolution vote throws
     out whatever touches it at a few angles and averages the noise round the turn.
   - **sweep** (a slab: seats, planks, walls, signs, panels): read a `hardsurf_vote` width vote, draw the profile off it
     (or the biggest region of it), sweep it across the width with quarter-round sides; `side` blends a second profile
     over the outer part (bolsters, raised rims).
   - **outline_tube** (a frame round a floor), **trace** (a tube's centreline + radius), **ring** (a rim's centre +
     radius), **part** (boxes, plates, 3D plates, tori, `radial` arrays for lugs / studs / rivets / teeth).
4. `hardsurf_build` -> each part's distance from the sculpt. `hardsurf_check` -> FLOATING groups (attach them) and
   overlapping pairs (read them). Look beside the sculpt, then beside the concept.
5. `hardsurf_bake` (one atlas; colour projected from the renders) -> `hardsurf_rig` (rigid joints, numeric tests).
6. Log every call where the sculpt and the concept (or the game) disagree: `hardsurf_disagree`.

## What the sculpt gets wrong (read it, don't trust it)
- **Fused splats fill under floors** down to the ground (shadow/occlusion): read the floor's TOP, model a floor.
- **Splats invent and exaggerate** where the concept is unclear: an extra part lying on the ground behind a vehicle, a
  sign 25 % too tall, a round bar bulged to a deep oval. Concepts are pictures, not specs either: the artist owns the
  call (clearances, hitbox, what's there), and logs it.
- **Small hard detail is 1-3 voxels**: bolts, lugs, slots, rivets, thin rods survive only as blurry colour. Model them
  as parts (`radial`, small tubes) or fuse finer where it matters (crop the splat round the part, fuse at 1-2 mm).
- **Non-round parts, and shells thinner than ~2 voxels or noisy, fail the revolution vote** (a fused bell's mouth
  votes 0.2-0.5; lugs average away; a round 6 mm cup wall is fine): `turned` warns over 30 % weak votes; read the vote
  map and draw the profile by hand.
- Touching parts merge in a vote (a crate wall reads wider because the tyre is in the same section): crop windows.

## Colour and detail
- Colour comes from the point cloud's RENDERS (768 px), not the fused vertex colours (3 mm, dull): projected at the
  sculpt point each texel covers (a wide transfer bake finds it), depth-tested, weighted by how square-on the view is.
  Typical: 70-87 % of texels projected, the rest vertex colour + push-pull fill.
- A part you MOVE off the sculpt (a crate wall back 7 cm, an axle forward) keeps `bake_offset` = measured - placed:
  it bakes where the sculpt has it. Without it, it projects whatever is behind (black).
- Metals carry the generator's lighting and dark smears: `clean` (default 0.45 for metal >= 0.5) pulls them to their
  median colour and lifts the smears. Set `nmap` low (0.3-0.5) on clean metal and tubes: the sculpt's lumps are noise.

## Rig (rigid parts)
Joints are hinges, spinners and sliders at a pivot about an axis; `follows` links one to another by a ratio (a second
door, a gear train, a steering wheel turning 3.3x its road wheels). The tests are NUMBERS: each moved part turned by the
expected angle about the expected axis (a sign error shows here), and the CLEAR range (the largest value before the
moved parts cross the rest). A range blocked at rest means the parts already cross: fix the model, not the range.

## Checking yourself
- Overlays and comparisons share ONE camera (frame them by the sculpt), and LOD copies are hidden in renders.
- Clean is not right: put every result beside the concept and the sculpt.
