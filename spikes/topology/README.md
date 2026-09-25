# Character topology spike (2026-09-25)

Troll body, rig test pose (`rig.test_pose`), same `rig.rig_weights` on every mesh. Run from the repo root with
`PYTHONPATH=spikes/topology uv run python spikes/topology/<script>`; outputs land next to the scripts (git-ignored).

- `topo_spike.py [model] [spacing] [subsurf]`: Blender Skin modifier over the rig graph (+ skull, ears), radii by
  rays, rings added at bending joints, shot onto the field along normals, relaxed; vs Blender QuadriFlow vs
  decimation at the same triangle count.
- `topo_curve.py`: QuadriFlow vs decimation error by region (rest / head / hands) over 2.5k-40k triangles.
- `topo_qfa.py <triangles>`: QuadriFlow with our sizing field (`topo_eval.sizing`: edge <= k / max principal
  curvature, shorter near bending joints, normalised to the budget) vs plain QuadriFlow vs decimation.
- `topo_loops.py`: joint crease planes (bisecting the two bones), sliced into the high mesh (cuts decided per edge,
  so neighbours agree), the loop component nearest the joint kept as a feature; and `ring_check`: walk quad edge loops
  from edges near the crease plane, report the closed ring nearest the plane (or the longest open walk: a spiral).
- `topo_feat.py <triangles>` (env `OFFSETS=-0.6,0,0.6`, `TAG`): sized QuadriFlow with the joint loops as features;
  ring check, errors, posed renders with the rings in red. `topo_neigh.py <result.npz>...`: rings at offsets beside
  the crease (do neighbouring loops close too?).
- `quadriflow-hifipushie.patch`: against github.com/hjwdzh/QuadriFlow (BSD-3). `QF_SIZING=<file>` (one relative edge
  length per input vertex) replaces the always-1 `rho` and drives the scale field; `QF_LAMBDA` anchors it (10).
  `QF_FEATURES=<file>` (lines "px py pz nx ny nz R", world units): edges with both ends on a plane within R are
  sharp edges and get boundary-style orientation + position constraints (`mCQ`/`mCO`; stock `-sharp` only
  constrains the integer stage, which doesn't make the field run along the curve). Also fixes `rho[vn] = 0.5f * (rho[v0], rho[v1])` (comma operator) in subdivide.cpp. Build: clone into
  `spikes/topology/QuadriFlow`, `git apply ../quadriflow-hifipushie.patch`, `cmake -DCMAKE_POLICY_VERSION_MINIMUM=3.5
  -DCMAKE_BUILD_TYPE=Release ..`, `make`.

Findings: see "Character topology spike: results" in CLAUDE.md.
