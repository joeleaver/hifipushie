# STATE: a dressed character out as one GLB (export_asset + chain garments) -- 2026-11-12

Goal: one character with its clothes out the far end as one game-ready GLB, by tools alone (the area re-review's first
move: /mnt/data/hifipushie/review_20261112/export.md). Code: garment_export.py + garment_export_tool.py (step 10 and its
LOD files), garment_asset.py (the hand-over), asset_export.py (the clothes branch, the rig block, the LOD loop),
garment_game.boundaries (seams). Tests: tests/test_garment_asset.py, tests/test_garment_export.py. Ledger C434, C439.

## Current best
- export_asset ships a chain garment (a garment with a garment record) AS export_garment WROTE IT at step 10: its mesh,
  pattern UVs, step 9a's maps and its own skin weights (matched to the export rig by bone name). Its details (buttons)
  are one part on a palette texture. Nothing is rebuilt; cloth.export_part gets only garments without a record.
- LODs (C439): export_garment also writes <garment>_LOD1..3.glb: the same pattern re-grid at a coarser grid, at the
  role's clothing budget per LOD (0.25 / 0.11 / 0.05), stiff pieces 4 / 2 / 1 rows, weights read off the body again.
  The character's LOD k takes that file; nothing of a chain garment is decimated. A detail piece under 2 px at the
  LOD's switch size is left out (the shirt's buttons at LOD3), the others simplified and seated on the LOD's cloth.
- A garment whose look (step 9) is not approved, or with no current step 10, is LEFT OUT, and the answer's first line
  says NOT IN THIS EXPORT with the call that puts it in. A step 10 whose own gate FAILED ships with a WARNING naming
  the rows; one exported before the LOD files is decimated with a WARNING naming export_garment.
- Seams are shared per stretch (garment_game.boundaries): armholes, neckline and cuffs were open loops before, at LOD0
  too. The shirt's outer mesh has 3 openings at every LOD (its outline, two cuffs).
- Proof: cf_shirt + shirt, on a copy of the T14 proof workspace (approvals stubbed test-only):
  export_garment 190 s: LOD0 10,226 + 1,440 triangles (27 mm), LOD1 2,552 + 360 (76 mm), LOD2 1,156 + 162 (87 mm),
  LOD3 584 + 0 (119 mm); 0 open pattern edges each. export_asset (out3, 4 min once it had memory; 18 min decimating):
  each LOD's shirt in the character's GLB EQUALS the garment's file to float32 (positions + uv, triangles, normals,
  weights by bone name), against files a second export_garment run wrote again: the re-grid repeats exactly.
- Looks (EEVEE): dressed_export/look_dressed_lods_before_after_proof3.png (before | after, LOD1-3 top to bottom).

## Open faults (worst first)
1. SKIN THROUGH THE COARSE SLEEVES at the character's LODs: both armpits, the forearms and a speck at the front hem at
   LOD3; the backs of the upper arms at LOD2; two patches at LOD1 (body poking after the push-under 41 / 64 / 157;
   decimated it was 6 / 0 / 33, with twice the triangles at LOD2 / 3). The shirt itself is clean at every LOD (no kink,
   no torn front or collar). Flat faces of a 9-12 cm grid cut under the skin the LOD0 cull leaves (40 mm rims,
   armpits). Tried and taken out: lifting each face's corners along the body's normal until its points clear the skin
   (to 50 mm) bloats the shirt (balloon sleeves, spiked shoulders). Next to try: cut the skin under a chain garment's
   LOD harder in asset_export (the skin left under LOD k's own cloth), not move the cloth.
2. Skin through both sleeves at the forearm at LOD0 too: the build's own (in the garment's step-10 look), not made here.
3. Approvals: a blind agent still cannot get a garment into a character (step 9 needs Joe or the coordinator). Joe's call.
4. asset_export.preview cannot draw a character's LOD GLB (no .json / _shading.json beside it: LOD0's copied by hand
   for the sheets); find_tool("export the dressed character as one GLB") still leads with export_garment.
5. Not proven: the bend check at the LODs; a head + skin + hair AND a chain garment; one garment over another (an
   under garment's LOD0 cull is not applied to its own LOD file); an alpha-cut base map; read()'s maps by file name.

## Decisions in force
- The character takes step 10's FILES, never the garment's pickle, a rebuild or a decimation: what was looked at ships.
- Weights map by bone name; a bone the rig no longer has is refused with "export_garment again". A failed step-10
  gate ships with a WARNING (one line in garment_asset.exported makes it "left out" if Joe wants it stricter).
- A LOD over its share is information; an open pattern edge at a LOD fails step 10's gate. The LOD look is the
  garment alone (the whole body under a coarse LOD shows through everywhere and says nothing).

## Commands
- The proof again (copy first; never write into /mnt/data/hifipushie/t14). Env for both calls:
  HIFIPUSHIE_HOME=/mnt/data/hifipushie/dressed_export/ws HIFIPUSHIE_APPROVED=/mnt/data/hifipushie/dressed_export/approved_stub.json
  HIFIPUSHIE_ASSETS=<main checkout>/workspace/_templates bin/capped uv run python -c '...':
  `from hifipushie import garment_export_tool as g; print(g.run("cf_shirt", "shirt", "open", "main_npc", True)[1])`
  `from hifipushie import server; print(server.export_asset("cf_shirt", "<out>", role="main_npc", rig=True, preview=False))`
- Equal to the garment's files: garment_asset.read(<garment LOD glb>) against garment_asset.read(<character LOD glb>),
  matched on position + uv together (seam vertices share a position); the character's meshes are "<asset>_cloth_<g>".

NEXT: fault 1 (the skin under a chain garment's LOD cut in asset_export's LOD loop, proved on the before / after sheet);
then docs/state/mcp_rules.md items 5, 6, 10.
