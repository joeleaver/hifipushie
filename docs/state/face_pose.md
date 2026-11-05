# Face pose: shapes in a look, rest expression (STATE, 2026-11-04)

For: Baynard Racing's racers (Puddles the pig, face kit + mouth interior); general to any face-kit model.

## Current best (branch face-pose)
- `look(name, shapes={...} | "rest" | preset)`: the model meshed as export_asset meshes it (asset.split with
  face.voxels(), resolution 256; cached build/face_fine.npz by geometry), the export's own faceshapes.apply on the
  face's region (quick=True: no diagnostics), neutral + lip seal cached (build/face_neutral.npz). Weights absolute;
  correctives by formula, a hand-set one kept and said. Clay (paint=False) is exact; painted carries the moves onto
  the scene meshes (blender_scene._shape_pose: nearest posed point of the same part, this render only).
- `face_shapes.rest = {ARKit: w}`: carried, not baked. GLB mesh.weights = rest (Playweft pw-gltf reads them as
  defaults), mesh.extras.restExpression, json face_shapes.rest + rest_how, rig.md "Face shapes: rest expression".
- Code: facepose.py (spec in its docstring), faceshapes.apply(quick=, neutrals=), server.look(shapes=),
  scene.look(shape_pose=) + scene.slit_voxel, asset REST_HOW / write_glb weights, rignotes face section.
- Tests: tests/test_facepose.py (5). Proof sheet: examples/face_pose_match.py.

## Evidence (pudpose = copy of puddles, grin jawOpen .8, lowerDown .6, smile .3, jawOpen_mouthSmile .24)
- Timing: export_asset (rig + 52 shapes) 324 s; posed look ~10 s (pose 3.5-4 s + render); first after a geometry
  change ~35 s (fine mesh 14-25 s + seal 17 s); painted posed close-up 11 s.
- Match (/mnt/data/hifipushie/facepose/match_sheet.png): GLB verts by the mouth -> posed look, body median 0.36 mm
  (neutral floor 0.34), p95 0.99 (0.54), max 3.4 (1.5: decimated mouth corners); teeth/tongue = neutral floor.
- Rest, baked vs carried (compare_rest.json): baked misses closed mouth 57 mm, MBP 57, AA 20, grin+mouthClose 24
  (clamped negative weights; jawOpen_mouthClose from relative weights). Carried: exact by construction.

## Open faults
1. Painted posed looks: the scene meshes the body coarser than the slit; lips can stretch there (said in the info).
2. On Puddles jawOpen_mouthSmile moves nothing (body: 5 of 6 targets move) — the 0.24 vs min()=0.30 is moot there.
3. The running MCP server needs a restart to get look(shapes=).

## Decisions in force
- Rest carried as default weights (evidence above); absolute weights everywhere; posed look at resolution 256.

## NEXT
Coordinator: land branch face-pose (suite result in the hand-over); Puddles' session can judge grins with
look("puddles", shapes=..., paint=False, focus=<mouth>, zoom=4) and set face_shapes.rest.
