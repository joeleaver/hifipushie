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
  the rows; a garment exported before the LOD files is decimated with a WARNING naming export_garment.
- Seams: a seam is shared per stretch (garment_game.boundaries). Before, armholes, the neckline and the cuffs were
  open loops that only read closed at LOD0's grid. The shirt's outer mesh now has 3 openings at every LOD.
- Proof: cf_shirt + shirt, on a copy of the T14 proof workspace (approvals stubbed test-only):
  export_garment 188 s: LOD0 10,226 + 1,440 triangles (27 mm), LOD1 2,552 + 360 (76 mm), LOD2 1,156 + 162 (87 mm),
  LOD3 584 + 0 (119 mm); 0 open pattern edges each. export_asset (out3, 4 min once it had memory): the character's
  LOD1 / 2 / 3 carry exactly those counts (the log: "the garments' own LOD files ... not decimated").
  NOT YET CHECKED: each LOD's shirt equal to the garment's file vertex by vertex (the script ran last, with proof 4).
- Looks (EEVEE): dressed_export/look_dressed_lods_before_after.png (before left, after right; LOD1-3 top to bottom).

## Open faults (worst first)
1. NOT LANDED. Branch garment-lods (worktree .claude/worktrees/garment-lods), stopped at 98 % of the week's usage.
   No fast suite on its head yet (targeted: tests/test_garment_export.py, _asset.py, _game.py, _record.py pass).
2. Skin through the coarse sleeves. Proof 3 (before the lift): the shirt itself clean at LOD1-3 (no kink, no torn
   front), but skin patches at both armpits and forearms at LOD3, upper arms at LOD2, two at LOD1
   (look_dressed_lods_before_after_proof3.png; body poking after the push-under 41 / 64 / 157, decimated 6 / 0 / 33).
   garment_export.clear_body (a LOD's cloth lifted off the body where its faces cut under the skin) was added for it;
   its proof was RUNNING when the run stopped: read dressed_export/logs/proof_4.log (each LOD's "lifted clear" line),
   logs/equal_4.log (ALL EQUAL expected) and look_dressed_lods_before_after.png before trusting it.
3. Skin through both sleeves at the forearm at LOD0 too: the build's own (in the garment's step-10 look), not made here.
4. Approvals: a blind agent still cannot get a garment into a character (step 9 needs Joe or the coordinator). Joe's call.
5. A character's LOD GLB has no .json / _shading.json beside it, so asset_export.preview cannot draw a LOD (copied
   by hand for the sheets); find_tool("export the dressed character as one GLB") still leads with export_garment.
6. Not proven: the bend check at the LODs; a head + skin + hair AND a chain garment; one garment over another (an
   under garment's LOD0 cull is not applied to its own LOD file); an alpha-cut base map.

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
  matched on position + uv together (seam vertices share a position).

NEXT: read proof 4 (fault 2). Sleeves clean: one bin/suite on the branch head, then land it (main is merged in,
ledger row C439 is written), remove the worktree, tell the garment session. Not clean: clear_body's reach / cap
first. After that docs/state/mcp_rules.md items 5, 6, 10.
