# Hard surface from the point cloud (hardsurf_*)

Concept -> point cloud (oxidegen make_point_cloud: fused closed mesh + its 50 renders, views.npz) -> clean FITTED parts
(never pressed) -> built, checked, baked (colour projected from the renders), rigid rig with numeric tests. Props,
vehicles, furniture, buildings. Playbook: src/hifipushie/hardsurf_guide.md (guide topic "hardsurf"). Ledger C513-C515.

## Current best
- Branch claude/hardsurface-pointcloud (worktree .claude/worktrees/hardsurface), based on claude/artist-retopo-55abea
  (reuses its Mesh / Poly / study views / runner): rebase onto main once that lands. NOT landed.
- Worked example: examples/hardsurf_hettie_kart.py (Hettie's crate kart, Braynard Racing) from the raw fused mesh;
  proof run in /mnt/data/hifipushie/hardsurf_proof/hettie: frame within 8 mm of the oxidegen spike's, wheel profiles
  within 1.5 mm, 20.7k faces (spike 20.6k), 69 % texels projected, nothing floats, clear steer 26 deg (spike 26),
  every joint's turn check passes. Renders match the landed kart (braynard-racing 583d296) by eye.
- Tests: tests/test_hardsurf.py (9; one slow: Blender build + check finds a floating part).

## Open faults (ranked)
1. Bake is slow under the Blender thread cap (Hettie ~20 min vs 7 min uncapped).
2. No MCP-level end-to-end test yet (tools are thin wrappers over hardsurf_run; the example drives hardsurf_run).
3. Small hard detail is still modelled by hand (radial / tubes); a "fuse finer round a part" step would help.
4. Framing can't tell front from back (flip) or the long axis of a near-square footprint (yaw0, warned).

## Decisions in force
- Hard surface fits, characters press (C513). The sculpt and the concept are evidence; the artist makes the game call
  and logs it (hardsurf_disagree, C515). Nothing kart-specific in the core: steering = hinge + follows.
- Parts moved off the sculpt carry bake_offset (C514); metals cleaned at bake (clean 0.45 default for metal >= 0.5).

## Dead ends
- Pressing a cage onto a hard-surface sculpt: imports the 3 mm lumps. Open3D / trimesh / shapely: not deps (numba
  occupancy grid + skimage contours + raster insets instead).

## Commands
- `uv run python examples/hardsurf_hettie_kart.py <fused.ply> <views.npz> <folder>`
- `uv run pytest -m "" tests/test_hardsurf.py`

## History
- The oxidegen spike: artifacts/budget3d_spike/retopo/karts/REPORT.md (oxidegen repo, untracked).
