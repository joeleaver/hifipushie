# Limb loops (creature topology from the skeleton, no template): STATE 2026-11-05

Branch limb-loops (worktree .claude/worktrees/limb-loops), from main 5d6f271e. Asked for by Braynard Racing (Puddles
seated: fold / crotch / seat after C373 + C374). Not pushed; coordinator lands. Exploring run (no gate). Ledger C375.

## What the tools hold now (limbloops.py docstring = spec)
- `parts.<p>.topology = "limbs"` (export_asset): `limbloops.build` from the export's own high mesh of that part;
  `parts.<p>.topology_triangles` (default 12000) for the decimated rest. No human template anywhere.
- Steps 1-2 of the plan, both proven on Puddles: (1) each limb root of the part gets a tube of RING (16) quad rings
  shot onto the exact surface, square steps, a crease ring + two packed rings at every hinge below the root, a
  lifted ring + quad fan at the end; (2) the root ring sits at the highest cross-section the limb owns (`_clear`:
  every ray < CLEAR 1.35 x its radius; a person's hip = the loop plane, a stub sunk in a belly = where it leaves the
  body), JUNCTION (2) rings walked out over the body (outward from the axis + UP_SHARE up it, inner side held at
  CROTCH 0.6 of the root's distance off the midline), the fine mesh cut inside the outer ring, zipped, then
  decimated with the rings as a locked border (cut AFTER decimating, the one-triangle crotch strip let both holes
  merge). Fins (doubled triangles) from the decimation dropped. `limbloops.quality`: closed rings at loop planes
  (ON_PLANE 0.4 r), field distance, turned faces (the `retopo.quality` its docstring names never existed in src).
- tests/test_limbloops.py (2 tests, 2.5 s): synthetic pig, both root rings closed, closed manifold, on surface.
- No BUILD_VERSION bump: opt-in topology, no other output changes. joint_density (topodensity) skipped for "limbs".

## Proof (workspace pudrt = copy of pud2 + topology "limbs"; files /mnt/data/hifipushie/limbloops, renders also in
the Braynard notes folder limb_loops/)
- Puddles' hip (z 0.17) and knee (0.115) are INSIDE the belly; the leg leaves it at z 0.10. Rings closed: root ring
  (hip slid to z 0.10) L/R 16 edges on plane; knee L/R 16 edges 12 mm off (a junction ring); the anatomy's hip plane
  itself: none (it is inside the body). Today's decimation: 0/6. Field 0.1 / 0.7 mm; 11 turned tris (decimated: 1).
- Model seated, same triangle count (12.5k), LBS: edges > 2x 48 -> 29; hips/legs (z < 0.2) > 2x 48 -> 17,
  > 1.5x 279 -> 161. With the stub correctives about the same. r3.png (rest wire), sit_corr.png (seated, top new).
- Seated by eye: the belly-thigh fold now runs along the rings (front / side clean, today's crumples); the crotch
  notch is still there in both (body strip between the junctions: weights, not loops); the seat about the same.
- Real export (pudrt.glb, 2026-11-05): by eye NOT a clear win (crotch pucker, belly fold). Superseded by the gate below.

## Gate on today's Puddles (2026-11-10, landed from branch limbs-gate, ledger C407): NO-GO
Bar: the quad-cage's (tag archive/quad-retopo), /mnt/data/hifipushie/limbsgate/measure.py; pud2 v83 exported both
ways (export_asset rig=True). Plain decimation: 11,225 tris, folds 9 (armpits), turned 8, body p99 0.42 / max 1.3 mm,
coverage p99 3.21. "limbs" (rest 9000): 10,558 tris, folds 122, turned 98, body p99 1.99 / max 39.9, coverage 3.88;
export audit TORN OR TANGLED at shoulder.R 67, elbow.R 47, head 19, neck 12. A shard at the right upper arm in the
bend renders (limbsgate/bend_*.png); seated, the belly is rougher and ragged where it meets the thighs.
- Fixed (general): a free arm hanging by the side (v76+) put the body's side inside its cut cylinder: 7 holes for 5
  limbs. The cut now keeps only the surface connected to the limb's tip (`_reached`; test), and the hole-count error
  names every hole and feature with its place.
- Open, first: the tears are on the RIGHT arm only, on a mirrored model: the arm's own rings or their zip treat
  the two sides differently (the left arm is clean). Find that before anything else.
1. Crotch notch: needs the pair key (C374 Open 2) or a crotch patch joining both legs' junctions with quads.
2. The rest of the body is still decimated triangles (2% quads). Later runs, in order:
   a. torso and head from the loft's own sections and the head ball's rings (quads everywhere on the body);
   b. shoulder and neck junctions (arms are their own part on Puddles: try them blended);
   c. loops round eyes / snout / a modelled-open mouth;
   d. `sheet` ears and tails as their own ring tubes (tail chain is a limb with no root plane);
   e. weights smoothed along rings (ring-wise mean of the bend weights: the jaggies at the thigh top);
   f. a quad-remesher fallback (QuadriFlow / Instant Meshes / QuadWild guided by a skeleton direction field) for
      shapes that aren't limb-like.
3. topodensity.hinge_mask still sizes a stub by length (C374 Open 4); "limbs" skips it.

## Dead ends
Ring evening by Laplacian along the ring (shrinks a junction ring back onto the leg); walking junction rings up the
limb only (into a belly's underside: they don't move); cutting the decimated body (holes merge at the crotch).

Commands: `/mnt/data/hifipushie/limbloops/{dev,posecheck,wire,glbcheck}.py`, `/mnt/data/hifipushie/limbsgate/{export,measure,bend}.py`
NEXT: nothing queued here. Clean loops for creatures now go through planned loops (branch loop-plan, Joe
2026-11-10); the right-arm asymmetry (mirror handedness in tube / junction / zip) is open if "limbs" is kept.
