# STATE: Garrett export (assembly_garrett) -- rewritten 2026-10-19 after session 15

## Current best
- Skin best is NOW gp_h6c_a11 (skin r24 A/B; v6-v8 carry a6 / ag10 skin).
- RC = **v6**: /mnt/data/hifipushie/assembly_garrett/exp/ag_garrett_v6/ (model ag_garrett6: tier hero, card_gain 2.1, skin s21,
  frozen_s5 garments; c6M hair cards). Blind A/B wins: v6 > v5 6/0/3, v6 > v7f 2-1. Sheet sheets/garrett_v6_joe.png.
- Best on eyes / forehead: **v7f** (exp/ag_garrett_v7f/ag_garrett10.glb: ag_garrett10 = age lines w1 + baked skin micro detail +
  lip floor): forehead shine fixed (+0.7 L* vs stage), but lost the A/B on stubble specks, under-eye hollows, heavy brows.
- v7g (exp/ag_garrett_v7g) = v7f + BAKE_PREFILTER + LOD skin cull + r68 face refine: looks = v7f (both fixes did NOT act).
- IN FLIGHT: **v8** = ag_garrett11 (ag_garrett10 + sh4T hair SHELLS from hg_G88a, merged hair-heads2 3bab7bc7), s15/chain16.sh
  (PID s15/PIDS) -> exp/ag_garrett_v8 -> s15/glb_v8 -> specks_v8.log -> offload/ag11 local game jobs -> s15/CHAIN16_DONE. Unjudged.
  Hair constants are module constants, not spec keys: s15/sh4t.py sets them; export only through it.
- COLLARS (2026-10-19, branch garrett-collar-diag 0f5cf7fa, NOT on main yet): **v8m** = v8 + made pieces decimated as sheets
  (exp/ag_garrett_v8m). Collar back-face px 1505 -> 285 (freeze 64); blind A/B v8m vs v8 3-1-1 (clay 3/0, textured 3/4 lost:
  the fix shows the FREEZE's own crumpled near shirt collar). Tiles: collar/garrett_collar_tiles.png. v8m unjudged on the
  full sheet (face / hair identical code paths).
- Export options: {"role": "hero", "lods": true, "cull_under_cloth": true, "cull_poses": "assembly_garrett/s5/poses/*.npz"}.

## Open faults (by game visibility)
1. 1 m: stubble as coarse black / white specks around the mouth (bake point-samples a 0.06 mm map). BAKE_PREFILTER (3a7843e1)
   did not act in v7g (atlas identical). Next: print tagged hp_px_m nodes / job texel_m in the bake job (suspect: stale scene
   cache built before the tag, or texel_m 0) and route the bake's Blender stdout into the export log.
2. 1 m: brows darker / heavier / arched vs approved soft grey; under-eye hollows; iris blue-grey (#585c54; skin r23 KEEPS it, photo favours it) vs approved
   gp_h6c #61584f: SKIN thread (routed).
3. 1 m: hair (v6 cards): crown ledge from the back (cards' top layer 10 mm off vs 3-4 mm: hair thread), shingled / dark vs photo.
   v8 shells are the test.
4. 3 m: right underarm notch at LOD1-2 back. LOD_SKIN_CULL_FROM 1 (abff2b9d) kept 98% (pose test "uncovered in a clip frame"
   is too loose): needs "visible in that frame". Seated clips not in the game shots: holes there unchecked.
5a. 1 m: collars: export fault FIXED in v8m (made slabs decimated as one mesh: front / back crossed). Left: jacket lapel EDGE
   back-face line (thin, also in the freeze draw), and the freeze's own shirt collar (rumpled, stands inside the jacket vs the
   concept's spread collar): dress-garrett, not export.
5. 3 m: pale cuff flecks above both cuffs LOD1-2 (minor; export / dress-garrett). Left collar / lapel sliver (dress-garrett).
Fixed: forehead shine (v7f), fly (clean at all LODs), clothing under budget, garment "over" chain fallback (s7), blink seam check.

## Decisions in force
- COORDINATOR: export head geometry = the APPROVED head (approved.json head/garrett = gp_h6c); asset.export gates on it, and on
  approved_head's skin.stack. skin.folds relief > 1 mm (FOLD_FORM_MAX_MM) is head form: clamped + WARNING, export raises unless
  the model carries the clamped value.
- Age texture beyond the approved head (wrinkles w1) = Joe / coordinator's call; v7f carries w1 as an experiment.
- Colour comparisons under asset.GAME_LIGHT (PBR Neutral), stage refs s12/stage_pbr/{gp_h6c, gp_h6c_a6}; never AgX renders.
- RC changes only by blind A/B (bin/review-ab after 13:00 MT, else a fresh blind subagent), reference = approved stage.
- Exports declare 24 GB to resources.heavy (hv.py 24, CAP 28G): v7e was OOM-killed sharing the slice with Tess's export.

## Dead ends (don't retry)
- Tuning the export for the "plastic" look: the cause was missing micro detail (now baked).
- Specular map hookup as the forehead-shine fix (41a49a9c: kept, -0.4 L* only).
- Treating the crown ledge as an export fault: same numbers in the hair thread's own GLB.
- Lip roughness floor for Garrett: no-op (his lip already > .38).

## Commands (A=/mnt/data/hifipushie/assembly_garrett; `. $A/env.sh`, W = this worktree)
- Export: see s15/chain16.sh (capped uv run python s15/sh4t.py assembly/hv.py 24 assembly/exp.py <model> <outdir> '<opts>').
- GLB face renders: blender -b --factory-startup --python s12/glb_r.py -- <glb> <outdir>.
- Specks: uv run python s5/specks/specks_glb.py <glb>. LOD diff crops: s11/cmp.py.
- Game check (local): LODSHOTS=1 bash s12/rge_local.sh <tag> exp/<dir> s5/shots_ag5.json (offload: bash rge.sh ...).
- Joe sheet: cd $A; OFF=<tag> python s12/sheet.py (set output name inside), approved head beside. RC table: $A/RC_garrett.md.

## History (grep only)
docs/notes/game_ready.md "## Garrett, session 6".."15" (s12 colour path, s13 shine, s14 stubble / notch, s15 v8); RC_garrett.md.
