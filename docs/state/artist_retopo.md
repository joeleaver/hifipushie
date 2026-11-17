# Artist retopo (a fused concept sculpt -> rigged game character): STATE 2026-11-17

Director 2026-11-17: cartoon / Pixar / non-realistic characters and most organic shapes go concept -> oxidegen
make_point_cloud (mesh_ply) -> THIS -> rig -> ROM -> refine. It replaces loop-plan (branch loop-plan stays unmerged,
untouched) and limb loops. Codified from the oxidegen spike artifacts/budget3d_spike/retopo/ (3 rounds, Mabel +
Scraps); its lessons are in retopo_guide.md (the playbook) and the tools. Ledger C505 (provisional until blind runs).

## Where things are
- Code: artretopo_{poly,mesh,sculpt,cage,mouth,check,run,steps,fill,sheets,study,report}.py (numpy / scipy / PIL;
  no trimesh / shapely / cv2), blender_artretopo_{common,press,bake,assemble,rig,rom,look}.py, tools_retopo.py
  (retopo_start, _look, _slices, _fit, _props, _cage, _press, _bake, _rig, _report), tests/test_artretopo.py.
- Playbook: guide(topic="retopo") = src/hifipushie/retopo_guide.md; worked cages: examples/retopo/{mabel,scraps}_cage.py
  (guide topics retopo_mabel / retopo_scraps). Blind kit: docs/blind/artist_retopo.md.
- Regression: /mnt/data/hifipushie/artretopo/regression/ (run.py, scraps_props.json, mabel/, scraps/).

## Regression (spike's high.ply, its final settings) vs the spike
- Cages: identical vertex for vertex (Mabel 478 v / 476 q; Scraps 568 / 566; Scraps' lower lip now pinned too).
- Press (levels 1, relax 6, after 1): Mabel 7616 quads, 4 folds (spike 4-5); Scraps 9056, 96 (spike 101-108).
- Bake repair: Scraps misses 43.8k / invented 1162 verts (spike 45.8k / 1146). final_cmp: same look, a little cleaner
  at the lip crevice and ear edge (hole fill is now nearest + smoothing, not OpenCV TELEA).
- ROM: every pose within +-3 edges of the spike, both characters; arms_up (aimed 30 deg off vertical): Mabel 4/128
  (spike's aimed run 4/123), Scraps 41/39 (41/39). The spike's rom_final.txt files predate the aimed pose.

## Prod input (oxidegen mesh_ply, v186): read this before a blind run
mesh_ply is turned by the concept camera's yaw, so a 3/4 concept leaves the character ~33 deg off: NOT mirror-
symmetric about x = 0 (mirror error 0.11-0.15). retopo_start now finds the mirror plane and turns it back (Mabel
+33.25, Scraps -32.75, The Major +33.75 deg; error -> 0.005-0.01; Mabel then matches the spike's frame within ~1 cm).
Facing is checked by eye (mirror symmetry can't tell face from back; the nearest turn is taken). Feet on z = 0.

## Changes from the spike (on purpose)
LIMB_FADE, global weight smoothing, the bake's pre-fill cmp renders deleted; helpers fixed to shoulder / elbow / knee;
props generalised (props.json primitives with a bone each; the canister = 3 cylinders); every framing (renders,
close-ups) from the bounds and joints, not constants; LOD1 hidden in ROM renders (it ghosted unposed in the spike's);
mouth builder shared (Cage.mouth); cage refused if open / non-manifold.

## Open (ranked)
1. No blind run yet: Puddles and Max first (the director starts them with docs/blind/artist_retopo.md).
2. Mabel knee_up 133 / crouch 182 squashed (stubby-leg knee crease); huge-head arms_up stretch.
3. Wings (Hettie, The Major), hands with fingers, hard-surface props / karts (oxidegen kart-retopo): not covered.
4. No CLAUDE.md thread line: it is at 8189 of 8192 bytes (test_codified); the coordinator adds one if it trims.

NEXT: Joe reads the regression sheets, bin/suite, coordinator lands; then blind Puddles + Max from prod mesh_ply.
