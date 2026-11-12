# STATE: a dressed character out as one GLB (export_asset + chain garments) -- 2026-11-12

Goal: one character with its clothes out the far end as one game-ready GLB, by tools alone (the area re-review's first
move: /mnt/data/hifipushie/review_20261112/export.md). Code: garment_asset.py (the hand-over), asset_export.py (the clothes
branch and the rig block), tools_export.py (the answer's first line). Tests: tests/test_garment_asset.py. Ledger C434.

## Current best
- export_asset ships a chain garment (a garment with a garment record) AS export_garment WROTE IT at step 10: its mesh,
  pattern UVs, step 9a's maps and its own skin weights (matched to the export rig by bone name). Its details (buttons)
  are one part on a palette texture. Nothing is rebuilt. The old route (cloth.export_part, a re-simulation of the draft)
  gets only garments without a record.
- A garment whose look (step 9) is not approved, or with no current step 10, is LEFT OUT, and the answer's first line
  says NOT IN THIS EXPORT with the call that puts it in. A step 10 whose own gate FAILED ships with a WARNING.
- Proof: cf_shirt + shirt, on a copy of the T14 proof workspace (approvals stubbed test-only):
  /mnt/data/hifipushie/dressed_export/out1/cf_shirt.glb (rigged, 87 bones, role main_npc, LOD1-3, 18 min under load).
  In the character's GLB the shirt IS the garment's file: 10,296 + 1,440 triangles; positions, UVs, normals and weights
  equal to float32. The body under it is culled as for any garment (clothing 11,736 of 12,000 in the budget line).
- Looks (coordinator's read, EEVEE): dressed_export/look_dressed_close.png (the garment's own step-10 look above, the
  character's GLB below: the same shirt, collar, placket, check on the grain); look_dressed_lods.png.

## Open faults (worst first)
1. LODs: the chain shirt goes through the generic LOD decimation. LOD1 (3,244 triangles) reads; LOD2 kinks the chest
   and the yoke; LOD3 (950) tears the fronts and the collar. Fix: a re-grid per LOD from the garment's own drape
   (garment_export.fit_budget at each LOD's share of the budget), never decimation.
2. Skin shows through both sleeves at the forearm in small patches. It is in the garment's own step-10 look too (the
   build / hang), carried here, not made here. The layers audit: "body through cloth_shirt: 144 vertices, worst 21.3 mm".
3. Approvals: a blind agent still cannot get a garment into a character (step 9 needs Joe or the coordinator). Joe's call.
4. The record keeps no NAMES for step 10's gate rows (garment_record._row keeps "id"; step 10 writes "row"), so the
   WARNING can only count them. The garment thread's file: told.
5. export_garment's "next:" does not name export_asset, and find_tool("export the dressed character as one GLB") still
   leads with export_garment. Agent-surface fixes: next.
6. Not proven: a character with a head, skin and hair AND a chain garment (no such model has a step-10 garment yet);
   one garment over another (the spec's "over"); an alpha-cut base map (carried as alpha_cutoff 0.5, no real case).

## Decisions in force
- The character takes step 10's FILE, never the garment's pickle or a rebuild: what was looked at is what ships.
- Weights map by bone name; a bone the rig no longer has is refused with "export_garment again" (an index would move
  the cloth with the wrong bone).
- A failed step-10 gate ships with a WARNING (its bend rows fail today on the body's own elbow tear): one line in
  garment_asset.exported turns that into "left out" if Joe wants it stricter.

## Commands
- The proof again (copy first; never write into /mnt/data/hifipushie/t14):
  HIFIPUSHIE_HOME=/mnt/data/hifipushie/dressed_export/ws HIFIPUSHIE_APPROVED=/mnt/data/hifipushie/dressed_export/approved_stub.json
  HIFIPUSHIE_ASSETS=<main checkout>/workspace/_templates bin/capped uv run python -c
  'from hifipushie import server; print(server.export_asset("cf_shirt", "<out>", role="main_npc", rig=True, preview=False))'
- Equal to the garment's file: garment_asset.read(<garment glb>) against garment_asset.read(<character glb>), matched on
  position + uv together (554 seam vertices share a position).

NEXT: fault 1 (LOD re-grids), then fault 5 with the review's other agent-surface fixes.
