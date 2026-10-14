# hifipushie notes: game_ready (one character, everything: head, body, skin, hair, clothes, rig, weights, ARKit, LODs)

"assembly" agent, 2026-10-14, branch `worktree-agent-ad0815704f43e0e00`. Goal: GAME-READY characters assembled from the
current pieces (never re-solving a head), every gap in the end-to-end path found, general tools fixed, a repeatable
recipe. Renders `workspace/human_renders/gr_*`; scratch DURABLE in /mnt/data/hifipushie/assembly/ (env.sh, run.sh
<script> = light slot, heavy.sh <gb> <script> = resources.heavy + capped; the recipe scripts; out/ logs).

## The recipe (per character)
1. ONE model holds the character: the outfit model's spec (body, props, garment definitions) + the approved head
   (`base.head`) and skin (`skin`) + the approved hair style through `tie_hair` (the tool path) + frozen garments.
   Tess: `mk_tess.py` -> model `ga_tess` (dt_tess + tp_h3_s2's head / skin + th_W18's style and look).
2. Garments: `cloth.freeze` each approved drape (with the code that made it), `{"frozen": path}` in the model.
3. `export_asset(rig=True, face_shapes=True, parts.body.topology "wrap")`, CAP=20G, heavy slot.
4. Gates (below): Khronos validator, rig audit, posed / expression renders, Godot.

## Frozen garments (cloth.freeze / thaw / carry; tests/test_game_ready.py)
Why: a cloth result is keyed on the body's key + the draft + the code. A head-only edit (lid fold, eye bags) changes the
body's key though the body below the head is identical vertex for vertex (dt_tess vs tp_h3_s2: 0.000 mm below z 1.5,
4 mm on the head), and other agents' cloth code moves on: wearing an approved drape on the final character meant a
re-sim. Now a finished drape is an asset: `cloth.freeze(res, g, path)` pickles the built result (no colliders / under
garment) + the garment expanded (design compiled, never re-drafted); a model's garment `{"frozen": path, color?,
roughness?, detail?}` wears it (`thaw`), carried onto the model's body (`carry`: same topology only; each garment
vertex moves with its 8 nearest body vertices, inverse-distance; what ends inside / within 1.5 mm is pushed out along
the body normal; `res["frozen"]` reports body / cloth max moves). garments(), cached(), the under-garment collider and
validate() know it. Garrett's jacket (c12_n18c) was simulated on a body of the same topology (20,616 vertices).
NOTE: the light run.py pickles the cloth agents keep (V, mesh names / piece / uv / F / sew / folds, made, buttons) are
NOT enough for the export's detail maps (marks, border, sew_seam, stitch lines, closures): freeze the FULL result.

## Built for the path (general)
- `lods.py` + export `lods=True | [shares]`: `<asset>_LOD<k>.glb` beside LOD0, same skeleton / weights / face shapes,
  the SAME maps (by file name). Each glTF-vertex patch (uv island x smoothing group x head/body mesh) is decimated
  alone by pyfqmr with its border held (no crack at seams or at the head/body ring), every new vertex reads uv,
  normal, tangent, 4 weights, shape deltas at its closest point of its own LOD0 patch. Hair cards drop whole layers
  from the top (the export orders card triangles by layer). Default shares 0.5 / 0.25 / 0.12 (Joe's call).
- export `cloth_triangles`: the garments' sim meshes (1 cm, two-sided: Tess's jeans 38k + sweater 28k triangles) are
  decimated the same way to a total.
- export `cull_under_cloth` (default on): skin and plain shells (socks) a garment covers along the normal (6 cm reach,
  1.2 cm tube) are left out, a 4 cm rim kept at every opening. Games do this: hidden, and it pokes through in poses.
- Godot game check `spikes/game_ready/check.gd` (+ `skin_blink.gdshader`; hair through spikes/godot_hair's card
  shader): bind / turns / face shapes / Mixamo-NAMED clips from another skeleton retargeted by bone name (world
  rest-relative rotations, each bone first swung from our A-pose rest onto the source's T-pose rest, hips by height),
  per-shot hide / blink_map. Wrapper /mnt/data/hifipushie/assembly/gd.sh (stops Godot when it logs "done": it does
  not always exit after quit()). Test clips: three.js's Xbot.glb (Mixamo idle / walk / run; downloaded to
  /mnt/data/hifipushie/assembly/anim/dl, NOT in the repo).
- Memory: a full dressed character at texture 4096 peaked 19-20 GB and was OOM-killed at CAP=20G (two such exports
  at once killed both). 2048 + `parts.body.texel_focus` on the head (density 3) is ~7-8 GB. One export at a time.

## Machine rules for renders (Joe, 2026-10-14)
- GPU lock: Blender under bin/capped takes a machine-wide lock per render call (BLENDER_SYSTEM_SCRIPTS gpulock);
  godot-quiet holds it for the whole run: keep each Godot run SHORT (one scene's shots, then exit). Never start Blender
  outside capped. "gpulock: waited N s" is queueing.
- Size check renders to what is judged: ~512 px close-ups of a joint / poke-through / mouth, ~768 px whole figure; the
  smallest judged thing >= 3-4 px; don't read sheets > ~1600 px when a crop answers; full sheets only for gate sheets.

## Gates (numbers + pictures per character)
(filled in as they run)

## STATE / NEXT
STATE: frozen garments in + tested; ga_tess being assembled.
