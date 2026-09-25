# Character topology spike (2026-09-25)

Troll body, rig test pose (`rig.test_pose`), same `rig.rig_weights` on every mesh. Run from the repo root with
`PYTHONPATH=spikes/topology uv run python spikes/topology/<script>`; outputs land next to the scripts (git-ignored).

- `topo_spike.py [model] [spacing] [subsurf]`: Blender Skin modifier over the rig graph (+ skull, ears), radii by
  rays, rings added at bending joints, shot onto the field along normals, relaxed; vs Blender QuadriFlow vs
  decimation at the same triangle count.
- `topo_curve.py`: QuadriFlow vs decimation error by region (rest / head / hands) over 2.5k-40k triangles.
- `topo_qfa.py <triangles>`: QuadriFlow with our sizing field (`topo_eval.sizing`: edge <= k / max principal
  curvature, shorter near bending joints, normalised to the budget) vs plain QuadriFlow vs decimation.
- `quadriflow-sizing.patch`: against github.com/hjwdzh/QuadriFlow (BSD-3). `QF_SIZING=<file>` (one relative edge
  length per input vertex) replaces the always-1 `rho` and drives the scale field; `QF_LAMBDA` anchors it (10).
  Also fixes `rho[vn] = 0.5f * (rho[v0], rho[v1])` (comma operator) in subdivide.cpp. Build: clone into
  `spikes/topology/QuadriFlow`, `git apply ../quadriflow-sizing.patch`, `cmake -DCMAKE_POLICY_VERSION_MINIMUM=3.5
  -DCMAKE_BUILD_TYPE=Release ..`, `make`.

Findings: see "Character topology spike: results" in CLAUDE.md.
