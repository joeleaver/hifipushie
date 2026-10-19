# STATE: Garrett hair, shells: rewritten 2026-10-19 (sh8, the fade ships; nothing in flight)

## BEST GARRETT HAIR FOR EXPORT: sh8c (coordinator rule; NOT Joe-approved)
- **sh8c** = sh7T + fade $HG/shells/sh8/fade_f.json (HG=/mnt/data/hifipushie/hair_garrett). Hero GLB + fade map:
  $HG/cards/exp/sh8c/. Shipped head + hair (asset.export, fade BAKED into the head's base colour):
  $HG/shells/sh8/ship_f/ (ship.py: hg_G88a, the spec patched in process only).
- Fade_f vs sh7T's fade_c: surface_mm (fade length measured on the skin), edge_breakup_mm 2.5, front_breakup_deg 3,
  front_soft_deg 14, clump .35, darker paint (color #262220, shadow #3a3532 @ .85, grey #8a8580 x .3), density_gamma 1.8,
  shadow_gamma 1.6, nape edge -53..-58 deg + fade 40-50 mm, trim ramp at fa 100-106 (was 118-126: the dark block).
- Junction (sheet tiles, L* p50 / p90-p10; photo side 58.8|49.5, nape 27.8|24.3): see notes "sh8"; sideburn paint
  59.5 -> 50.3 (mesh 51.5: no two-tone), nape paint 58.7 -> 42.9.
- Black px g1left / g1back: 0/0. Card faces as sh7T (hero 12,628): the fade adds no geometry.
- EXPORT SETTINGS: hg_G88a's spec hair.export = {"headroom": 2.0, "style": "shells", "fade": <fade_f.json>,
  "constants": <ship.py CONST: sh6T's + SHELL_MIN_GAP 0.0004 + SHELL_HROW_DROP [{"fa": [65, 95], "el_max": -3.0},
  {"fa": [90, 180], "el_max": 20.0}]>}, look {"card_grey": 0.7, "grey": "#6c6966", "lit": "#524e4a", "gap": "#1e1b19"}.
  All names known on the merged branch. Write them into the workspace spec AFTER the branch lands (main lacks the code).

## How the fade ships (sh8)
- hair_fade.build: the map (scalp-chart coords) + skull radius; hair_fade.sample / bake_into: the same lookup as the look's
  node tree (blender_cards.skin_fade), numpy. asset._export builds it from hair.export.fade (ctx["skin_fade"]) after
  scene_maps; asset.bake mixes it into the skin part's LINEAR base colour per texel (exact surface point X). Roughness
  unchanged. No extra maps: any engine shows it. blender_scene.py untouched (head-stage code hash).
- Proof: GLB base-colour crops $HG/shells/sh8/glb_f_{nape,sideburn}.png (read from the GLB); re-imported judge run
  sh8c_shipr_8f880a9b (export ship_fr, rigged); sheet $HG/shells/sh8/sheet_photo_ship8c_sh7T.png. Blind A/B sh8c vs sh7T 2-1.

## Open faults
1. Nape fade still shorter / less sparse-tailed than the photo; teeth a bit regular (comb-like) at 1 m.
2. The shelf above / behind the ear (cap cut-out) not addressed (a-c first).
3. From sh5: scraggly front hairline / temples; back streaks long / high-contrast.

## Dead levers (don't retry)
Specks: SHELL_LIFT_EASE, BASE_DEPTH, BASE_EDGE_DEPTH, culling, shadows, AO, ray tracing, depth precision, whole-hair offset.
Look: SHELL_CARD_VALUE .65; EDGE_SHADE .3 / LAY_DEP_T .3 / LAY_LEN 1.1; SHELL_EDGE_LIFT 1 mm, SHADE_MAP darkening, fins.
Fade: clump as a plain multiplier (bald holes); sphere-mm fades below el -55 (streaks down the neck: use surface_mm).

## Tools ($HG/shells/sh8/)
run.sh (this worktree's code), q1.sh <tag> <fade json> (hero look shots + black counts), ship.py <out> <fade json>
(asset.export; run as CAP=28G run.sh 24 ship.py ...: the default 12G cap OOM-killed the bake), glbcrop.py <glb> <note|C>
<prefix> (base-colour crops from the GLB), junc.py (junction L*), mkfade.py, ../sh7/sheet.py, ../sh7/fprev.py.

## History (grep only)
docs/notes/hair.md "Garrett short-hair shells sh8 (fade ships)" (+ sh7 / sh6 / sh5).
NEXT: land the branch (coordinator), then write the export settings into hg_G88a's spec; longer sparse nape tail; shelf.
