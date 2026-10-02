# Face shapes (ARKit morph targets for lipsync) — design note, 2026-10-01

oxidegen's lipsync design (oxidegen `docs/lipsync.md`, section B) asks the sculpt artist for named face shapes on a
character's game-ready export: glTF morph targets (and FBX blend shapes) with ARKit blendshape names, neutral = mouth
closed, each shape full extent at 1.0, additive, the same names on every part that moves with the mouth, and a mouth
that opens onto an interior. This is the prototype: `src/hifipushie/faceshapes.py`, the face kit's
`mouth.interior` (`kits._interior`), `export_asset(face_shapes=...)`, example `examples/goblin_talk.json`, contact
sheet `goblin_talk_shapes.jpg` (here; made by `examples/face_shapes_sheet.py`), tests `tests/test_face_shapes.py`.

## How a shape is made: a displacement of space, not a re-projection

The export never bakes from a high-poly mesh; it projects low-poly points onto the exact field. The first idea was to
pose the face kit per shape (re-expand with jaw/lip/lid params moved) and project the SAME low-poly vertices onto the
posed field. Rejected for the prototype, because nearest-surface projection is what breaks on exactly these motions:
a jaw opening 4-5 cm slides vertices along the surface instead of carrying them, a lip vertex lands on the tooth or
the bag wall behind it, and surfaces that appear (the inside of the mouth) have no vertices waiting there.

Instead each shape is a smooth displacement field D(x) built from the kit's own anatomy, and the target is the neutral
vertex moved by D. Topology and vertex order are identical by construction; nothing is re-meshed or re-projected;
shapes are deltas, so they add; it costs ~0.1 s for 36 shapes (geometry only, textures stay neutral). Anatomy read from
the kit-expanded spec (`Face`): the lips' parting line (the groove chain's joints: height = the smile, depth = the lips'
front), corners, lip radii, the slit and bag, the teeth/tongue parts, a jaw pivot (in front of the ear: back level
with the head joint, half way from mouth to eyes; overridable), lids (`spec._lids` margins), brows and cheeks (their
blobs, or defaults off the eyes/mouth).

Regions (weights) are measured at the vertex's MESHED position (mouth open by the slit, where upper and lower lip are
told apart by which side of the parting line they're on) and the move is applied at the NEUTRAL position:
- jaw: below the parting line (a crisp step across the slit; the boundary rises toward the pivot past the corners and
  softens with depth, so cheeks and the bag's back wall stretch), in front of the pivot, fading under the chin
  (`jaw.depth`). jawOpen = rotation about the pivot (18 deg default), Forward/Left/Right = translations.
- lips: either side of the parting line, a few lip radii high, out to the corners, front to the bag wall.
- corners (smile, frown, dimple, stretch), mouth region (mouthLeft/Right, pucker's contraction), halves (press,
  lowerDown, upperUp), cheeks (cheekPuff along the normal), brows (inner/outer ends, centre).
- eyeBlink: the upper lid turned down over the eyeball about the eye's own left-right axis (so it slides on the ball),
  the lower lid up a quarter; skin round the lid follows the move of the point under it on the lid's outer sphere.
- rigid: the nose (the kit's nose prims' own field: a goblin's nose hangs over its upper lip and moved with it) and the
  eyeballs; teeth: the lower row (connected pieces below the parting line) rides the jaw; the tongue rides the jaw,
  tongueOut slides it out past the lips with a 0.35 jawOpen (so it doesn't push through closed lips).
Amounts are fractions of mouth width / head radius, so they scale with the character; `spec["face_shapes"]` overrides
`amount` per name and the jaw (`pivot`, `open` deg, `depth`). It is stripped from geometry (no rebuild).

Left/Right are the character's own (ARKit convention): Left = +X for a creature facing -Y.

## The mouth interior

`kits.face.mouth.interior: true | {slit, lips, bag, teeth, tongue}`:
- slit: a "band" sweep subtract along the parting line (mirrored), from in front of the lips back into the bag,
  tapering to nothing at the corners. The lips' inner faces are real surfaces in the mesh.
- bag: a rounded-box subtract behind the lips.
- teeth: two band sweeps along a dental arch, part "teeth" (upper hangs from the gum to just past the parting line,
  lower row behind it); buried faces are dropped by the export (`prune_hidden`).
- tongue: an ellipsoid on the bag floor, part "tongue".
The export meshes the slit's part at <= slit / 2.2 (`Face.voxels`, `split(voxels=)`): 1.44 mm on the goblin, or the slit
closes at the scene voxel. The NEUTRAL closes it: each lip moved half the slit toward the parting line (`Face.close`),
after the bake and the skin (both use the meshed, open low poly); the per-corner normals and tangents turn with it.
So a look (and the high mesh) shows a parted-lip line; the export's neutral is closed.

## Tool / spec surface

- `export_asset(..., face_shapes=True | [names])` (MCP tool and REST/artist parity automatically: the artist exposes
  the tool's schema). True = the 27 required + 9 recommended names. Fails early (before meshing) when the face kit has
  no `mouth.interior` or a name isn't ARKit.
- GLB: per moving part, `primitives[0].targets` = [{POSITION, NORMAL}] as sparse accessors (deltas, glTF axes; normal
  delta = the vertex normal's turn applied to the exported corner normal), `mesh.weights` all 0,
  `mesh.extras.targetNames`. Parts that don't move (eyes, clothes, the rest) carry no targets. Khronos validator: 0
  errors, 0 warnings.
- FBX (`fbx=True`): Blender's converter keeps them as shape keys with the same names (checked by re-import: body /
  teeth / tongue 36 each). Works with `rig=True` (skinned + morphs).
- json: `face_shapes: {names, parts: {part: [names]}, convention}` and `parts.<p>.face_shapes`.
- `asset.preview(poses=[{name: weight}])` renders a pose list in one Blender run; `faceshapes.read_glb` decodes the
  targets (checks, tests); `faceshapes.COMBOS` = review combos (AA, OO, MBP, EE, FV, smile, open+close).

## What works / what looks wrong (goblin_talk, 15k tris, texture 1024, ~95 s export)

Works: jawOpen (teeth, tongue, bag read as a mouth), tongueOut, smile/frown/dimple/stretch, press, lowerDown/upperUp,
funnel/pucker, rolls (a move, not a turn: the turn tore), brows, cheekPuff, blink closes the eye; combos AA/OO/EE/FV
read. Round trip exact (tests).

Looks wrong / limits:
- Blink: the low poly round the lids is coarse (decimation), so the lid's 15 mm move shows facets on the skin round
  it. Needs more triangles at the lids (a triangle focus like texel_focus) or the template wrap's eye rings.
- jawOpen + mouthClose (ARKit "lips sealed, jaw open") meets half way: the upper lip stretches down like a curtain;
  real faces move the lower lip more. Corner spikes (slit walls) at that extreme.
- The neutral's closed lips show the dark mouth-interior paint in the seam groove (the `near` paint layer's `within`).
- Shapes are anatomy formulas tuned on one cartoon goblin; amounts are guesses a director should tune per style.
- Kit-built faces only (face kit with `mouth.interior`). Base bodies with a GNM head have their own (non-ARKit) linear
  expression space: a separate job. Only one face kit per model; prefab parts never get targets.
- Skin parts near the face (a hat brim, hair shell) would take the brow/cheek moves too: no ownership test beyond
  "the nose and eyeballs stay".
- NORMAL targets only (no TANGENT deltas); Blender's importer ignores both (recomputes), engines may use them.

## Open questions for the director
- Art style of the mouth interior (bag colour, teeth as one strip vs individual teeth, tongue size) and the default
  slit/bag sizes. Conservative defaults taken.
- tongueOut includes 0.35 jawOpen (conservative: never pushes through closed lips) vs a pure tongue shape.
- mouthClose: halfway vs mostly-lower-lip.
- Which recommended shapes to skip for non-human faces (no lids -> flat blinks, logged).
- Jaw angle (18 deg) and amounts per style (cartoon vs realistic).
