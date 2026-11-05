# Limb loops (creature topology from the skeleton, no template): STATE 2026-11-05

Branch limb-loops (worktree .claude/worktrees/limb-loops), from main 5d6f271e. Asked for by Baynard Racing (Puddles
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
the Baynard notes folder limb_loops/)
- Puddles' hip (z 0.17) and knee (0.115) are INSIDE the belly; the leg leaves it at z 0.10. Rings closed: root ring
  (hip slid to z 0.10) L/R 16 edges on plane; knee L/R 16 edges 12 mm off (a junction ring); the anatomy's hip plane
  itself: none (it is inside the body). Today's decimation: 0/6. Field 0.1 / 0.7 mm; 11 turned tris (decimated: 1).
- Model seated, same triangle count (12.5k), LBS: edges > 2x 48 -> 29; hips/legs (z < 0.2) > 2x 48 -> 17,
  > 1.5x 279 -> 161. With the stub correctives about the same. r3.png (rest wire), sit_corr.png (seated, top new).
- Seated by eye: the belly-thigh fold now runs along the rings (front / side clean, today's crumples); the crotch
  notch is still there in both (body strip between the junctions: weights, not loops); the seat about the same.
- Real export (pudrt.glb, export_asset(rig=True); body 12.1k tris vs today's pud2.glb 14.9k), seated LBS: hips/legs
  (z < 0.2) edges > 2x 63 -> 57, > 1.5x 265 -> 153; with the UpLeg correctives 104 -> 80, 441 -> 313. By eye NOT a
  clear win: side better (the leg flows into the belly, no shelf); front the crotch pucker is MORE prominent and a
  fold runs across the belly at z 0.21; back small dents / specks (bake or turned faces: unchecked) and a sharper
  seat point. glb_{pud2,pudrt}_seated_{lbs,corr}.png. This export ran before the fin fix (2 non-manifold edges).

## Open, ranked by what shows in the kart
0. Before Baynard uses it: re-export (fin fix in), find the back specks, and fix the crotch (1): today the GLB
   reads worse in front. Keep pud2's default topology in the kart until then.
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

## Commands
`/mnt/data/hifipushie/limbloops/{dev.py <model>, posecheck.py <model> a.npz b.npz, wire.py out.png a.npz.., glbcheck.py}`

NEXT: coordinator lands (bin/suite PASS, fast tier 12.2 min: over its 10 min rule, not from this branch's 2.5 s test);
next run: crotch patch (both legs' junctions joined by quads) + re-export, judged on the GLB front; then 2a.
