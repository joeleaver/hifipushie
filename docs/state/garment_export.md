# STATE: garment export (step 10, T11) -- 2026-11-02

Tool: `export_garment(name, garment, wear="open", role="main_npc", look=True)` (cloth group; guide(topic="export_garment")).
Code: garment_export.py (method), garment_export_tool.py (tool body, looks), garment_glb.py (small skinned GLB);
garment_game.boundaries takes per-piece h, remesh_panel takes fold lines. Tests: tests/test_garment_export.py. C291.

Proof (cf_shirt, the T10 workspace COPIED to /mnt/data/hifipushie/t11/ws; record steps 0-9 STUBBED done + step 9 approved in
a stub file by /mnt/data/hifipushie/t11/stub_record.py, test only; run with HIFIPUSHIE_APPROVED=/mnt/data/hifipushie/t11/approved_stub.json):
- GLB: /mnt/data/hifipushie/t11/ws/cf_shirt/chain/shirt_open/export/shirt.glb (+ shirt_export.json, look GLBs)
- 11968 / 12000 tris (main_npc clothing): garment 10528 (outer 4918 + inner 4918 + rims 692) + details 1440; grid 29 mm
- stretch p5 0.76 / p95 1.02 (drape's own 0.84 / 1.05); open edges 0; LeftArm 45 deg: distance-to-body change p95 0.4 mm
- looks: .../export/shirt_rest.png, shirt_arm.png; sheets .../garments/shirt/step10_rest.png, step10_arm.png
- My look: reads as the build (collar, placket + buttons, curved hem, cuffs), folds smoothed (no bake); the sleeve
  follows the raised arm, no gap at the shoulder. Source was the BUILD (no hung garment exists for this shirt).

Open (worst first):
1. The weight check is near-tautological (garment and body weights are both read off the same surface): it catches a
   broken transfer, not bad body weights. A real check: a game pose set rendered + pierce_faces against the posed body.
2. No normal / AO bake of the drape's folds (garment_game.bake exists for the old drapes; hook it to chain results).
3. No LODs (coarser re-grids per budgets lod_ratios), no layering cull (a shirt under a jacket: garment_game.covered_cull).
4. Details keep their T10 triangle counts (1440 for 14 buttons: 12% of a main_npc budget); not decimated.
5. Never run on a hung garment (final.pkl) nor on the hussar jacket.

NEXT: run on a hung garment with a real step 9 approval; then the fold bake (2).
