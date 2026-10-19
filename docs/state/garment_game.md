# STATE: garment-game proof (pattern-space remesh) -- 2026-10-19 (session 3 end: LOD poke-through)

## What this is
Proof, on Garrett's shirt + jacket, that a GAME garment can be made the way game artists make it: the drape is the
HIGH poly; the game mesh is a clean re-grid of the FLAT pattern mapped onto the drape (UVs = the garment's own pattern
atlas); folds baked high -> low; hidden shirt regions deleted by coverage in every game pose; LODs = coarser re-grids.
Opt-in, export untouched: src/hifipushie/garment_game.py, blender_garment_game.py, tests/test_garment_game.py.
Branch garment-game-lodpoke (from garment-game-blotches + main).

## Current (proof6g)
- Build: /mnt/data/hifipushie/garment_game/proof6g/{LOD0,_LOD1,_LOD2,_LOD3}/game_{jacket,shirt}.glb (same tris as v8).
- Sheet (concept | NEW | v8): /mnt/data/hifipushie/garment_game/sheet7/garment_game_sheet.png; trios sheet7/review,
  key sheet7/review_key.json; my before/after LOD look: sheet6/lod_compare_{a,b}.png, sheet7/lod_compare.png.
- MEASURE: garment_game.pierce_faces (triangle-triangle, registered in validated.GATE_MEASURES, known answers in
  _selftest_pierce_faces: crossing between vertices caught where the vertex test reads 0; parallel sheets 2 mm apart
  read 0; a plane through a 4x4 sheet finds exactly its 8 faces). Shirt faces crossing the jacket (pierce_lods.py):
  | LOD | rest proof5 -> 6g | max over 16 clip frames proof5 -> 6g |
  | 0 | 8 -> 0 | 325 -> 146 |
  | 1 | 94 -> 0 | 257 -> 51 |
  | 2 | 114 -> 4 | 197 -> 33 |
  | 3 | 145 -> 39 | 156 -> 43 |
- CAUSES (isolated): (a) the cull's coverage ray looked only OUTWARD, so a shirt vertex that already poked through the
  coarse jacket "looked uncovered" and was kept: the cull kept exactly the faults (sleeves). (b) a coarse cover's
  chords sink below the drape (jacket chord sag p95: 2.2 / 4.3 / 7.9 / 22 mm at LOD0-3) while the gap to the shirt is
  a few mm and ~0 at the jacket's free edges. (c) found on the way: remesh's winding test used face centroids, which
  sit inside the arm at h ~9 cm: LOD3 pieces were wound INWARD (31% of shirt normals outward; baked normals inverted).
- FIX: covered_cull also counts a cover within CULL_BACK_REACH = 2 cm BEHIND the vertex; build(layer_gap=
  chord_sag(this LOD's jacket, jacket drape), gap_rings=1) moves only the kept-but-covered ring (+ the faces straddling
  the jacket edge) that much toward the body; the bake casts from the ungapped surface (V_bake: baking from the moved
  surface hit the jacket and made LOD3 shirt blotches, sheet6); remesh winds per vertex (LOD3 now 90% outward).
- LOOK (fresh blind subagent, 15 key-shuffled trios, review-ab CLI at its weekly limit): LOD1-3 rows new 4 / v8 2
  (was 0 / 6); LOD0 rows new 6 / v8 3 (was 6 / 0 / 3 ties). Sleeve facets and the LOD3 chest strip are gone (my look).

## Open faults (worst first)
1. 3 m FRONT rows go to v8 at every LOD (LOD0, LOD1, LOD2): reviewer "blotchy, streaky jacket shading" on ours at 3 m
   front only. Not poke-through (other views clean). Isolate first: flat-ID + AO-off at g3m-front.
2. LOD3: 39 rest crossings left, at jacket edges (collar / lapel, upper sleeve, cuffs), not moved by a bigger gap or
   more rings (lever tested: 37 / 37 / 31). Shirt collar blocky at the neck, jacket collar notch crumpled (8 rows over
   9 cm). Next lever: shared sample lines at the jacket's free edges (shirt re-grid takes the jacket edge as a line).
3. Posed crossings (16 clip frames) 146 at LOD0 under the body-displacement pose (no skin weights yet): sleeves at
   the elbow. Needs the real skinning before it is judged.
4. Collar 0.5 m front: thin black gaps at the shirt collar edge (lost 1 of 3 collar rows this round).
5. GLB materials doubleSided AND explicit inner faces; posed metrics via body field; drapes differ (frozen_ae vs s5).

## NEXT
Fault 1 (3 m front shading: flat-ID + one-switch variants at g3m), then fault 2 (shared edge sample lines at LOD3).

## Commands (scripts in /mnt/data/hifipushie/garment_game/scripts/)
- Build + metrics: `GG_OUT=<dir> GG_GAP=sag GG_RINGS=1 bin/slot uv run python .../proof6.py` (~3 min).
- Face-level pierce: `bin/slot uv run python .../pierce_lods.py <build> <json>`; where: diag_cross.py; lever check diag_gap.py.
- Whole round: `bash .../run7.sh` (build, pierce, bake under capped, judge_all7.sh, sheet7.py). Blind A/B: ab6.sh
  (review-ab) or a fresh subagent on sheet7/review trios; unblind with review_key.json.
