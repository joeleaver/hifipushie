# STATE: Tess export (assembly agent) -- rewritten 2026-10-19 after r72

## Current best
- RC = **rc2n**: /mnt/data/hifipushie/assembly/exp/rc2n_tess/rc2_tess.glb + _LOD1/2/3.glb, report rc2_tess.json.
  Model workspace/rc2_tess: base.head_approved "head/tess" (approved head tp_k19, gate checked at export), skin
  tp_k19_s28 (= skin's tp_k19_a0), frozen s18 garments (coat / sweater / jeans, FROZEN_KEYS + color/detail/roughness/sheen,
  no "over": the pickles' own chain is used), hair th_W18 groom tier hero + HP_FS_SET hair_clumps.FILL=1.0, r49 smile env.
- Export options: {"role": "hero", "lods": true, "cull_under_cloth": true, "cull_poses": "assembly/r56/poses/*.npz"}.
- Env (r62/chain_n.sh): HP_SMILE_FIT=fx/smile_w4_shape.npy HP_JAW_FIT=fx/jaw_w1_shape.npy HP_SMILE_FIT_EYE_GAIN=1.0
  HP_FS_SET="SMILE_FIT_SOFT=0;hair_clumps.FILL=1.0" HP_JAW_FIT_GAIN=1.045 HP_JAW_ROLL_TUCK=0 HP_SMILE_FIT_FOLD=0.6
  HP_JAW_TUCK_FADE=3 HP_SMILE_LOWLID_GAIN=1.6; HP_SHAPE_SCULPT unset.
- Triangles LOD0 90,659/103,000, LOD1 44,809/51,500, LOD2 24,854/25,750, LOD3 10,855/12,360: all under.
- rc2t (exp/rc2t_tess) carries the coat-speck fix + 1 mm face refine but lost the blind A/B 1-3 (lips hard decal, brows
  smudged). rc2p = stack-correct (a6 skin) but lost 1-3. Next build = rc2u, only when skin's CURRENT BEST changes
  (skin best is NOW tp_k19_a16 (r24 A/B 2-1 over a6): rc2u is due; see docs/state/skin.md).

## Open faults (by game visibility)
1. 1 m: face reads hooded / dark lid band, heavy straight brows, fuller mauve lips vs the approved head: SKIN stack, not export.
2. 1 m: dark blotch on her left ala (nostril). r72: bake == scene colour per texel (p50 0.0014): NOT an export bug; it is the
   skin's own colour + tiling detail speckle aliased at ~0.3 mm texels. Owner skin: tone, and A/B BAKE_SS 4 / pre-blurred
   skin_*_16 detail on a head-only rawbake (assembly/r71/rawbake2.py) before any export. Skin r24 replies: not the maps
   (stack even, blemishes ruled out) = the NOSE FORM (no crisp alar groove): head stage; asks for an a16 bake probe L vs R.
3. 1 m: lower-lip gloss reads wet plastic under the game rig (needs a lip roughness floor ~0.38).
4. 1 m: eye whites grey in game renders = game shading + skin's sclera tint, not the bake.
5. 3 m: crown silhouette ragged, pale card tips at the front (hair cards thread).
6. 3 m: tiny LOD2 orange specks at the right armpit; LOD2/3 lower-pocket folds; LOD3 jeans fly stitching, faceted buttons.
Closed: coat upper-back speck (rc2t, rays 74 -> 1).

## Decisions in force
- Ships only APPROVED pieces (workspace/approved.json); the export gate demands approved_head's skin.stack in the model.
- RC changes only by a blind A/B (bin/review-ab, else a fresh blind subagent), look-first, reference beside every result.
- Sheets for Joe: reference first, approved head beside the build (gr_r63_tess_joe.png layout).
- Every heavy job via resources.heavy + bin/capped (renders: gpulock). Never push; stage by path.

## Dead ends (don't retry)
- Inner-paint overlay as the nostril cause (r70): a uv mis-read. GOTCHA: trimesh GLB texcoords are already v-up; never `1 - uv`.
- Bake ray length / cage stray / a duplicate high poly / another uv map as the nostril cause (r71-r72): all ruled out.
- Cage capped at 0.45 x clearance (r64): kept in code, didn't fix the nostril.
- "Inner paint never through w_ dilation" guard: a no-op (put_given refills anyway).
- HP_SHAPE_SCULPT sculpt npzs (r48/r49): off.
- a6 brow strands in the export (rc2p): read drawn-on / hard-edged; lost the A/B.

## Commands (scratch /mnt/data/hifipushie/assembly, `. env.sh` first)
- Export: `bash chain_exp.sh "rc2_tess:<out>:{json opts}"` (template: r62/chain_n.sh, env above).
- Triangles: `python3 r55/tris.py <glb> <LOD1> <LOD2> <LOD3>`.
- Game check: `bash ge.sh <glb> <json> <outdir> <shots.json> [gdproj/xbot.glb]` (shots: r60/shots_crown, r54/shots_pl,
  r56/shots_zoom, r51/shots_lod0..3, r50/shots_rc).
- Face vs approved: `python3 r62/ah/glbshots.py <glb> <out> <tag>`. Sheet: `python3 r59/sheet.py <gen> <png> "<title>"`.
- Bake dump: HP_BAKE_DUMP=<dir> on export -> inner_<atlas>.npz. Head-only raw bake: r71/rawbake2.py.
- Blind A/B: /mnt/data/hifipushie/bin/review-ab (tiles as r61/tiles.py).
- RC gap list: /mnt/data/hifipushie/assembly/RC_tess.md (update per round).

## History (grep only)
docs/notes/game_ready.md "## r62" (rc2n made), "## r63" (eyes = skin), "## r68".."## r72" (nostril trace); RC_tess.md.
