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
4. Gates (docs/notes/gates.md): checklists, the game-like EEVEE render (blender_game.py), bin/review every round.

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

## After gr_01 (Joe: "Tess is _terrible_"): what went wrong, the new process (docs/notes/gates.md)
- What went wrong, in my path: (1) I consumed the newest pieces, not APPROVED ones: a sweater whose own sheet said
  CORRUPT went in. Now: `bin/approve get <stage> <piece>`; Tess v3 is undressed (no garment approved: tp_h3's own top
  and briefs shells as a neutral placeholder; the outfit's lanyard / badge out too: they floated off the bare chest).
  The skin (tp_h3_s2) is a labelled DRAFT. (2) "It runs end to end" was reported as a result; gates were plumbing
  (Khronos, bone count). Now: checklists `workspace/checklists/tess_{hair_export,motion,rig,expressions,engine,
  assembly}.json` (copies in /mnt/data/hifipushie/assembly/checklists) + bin/review every round. (3) Godot is out of
  the gates (Joe: engine-agnostic): the engine stage is the GLB re-imported in Blender, EEVEE set up like a game.
- `blender_game.py` (was spikes/game_ready/game_eevee.py): THE engine-stage render. Materials are built FROM the
  export's shading notes (so the notes are tested every export), blink map driven by eyeBlink, face shapes, turns,
  Mixamo clips from another skeleton, side by side with that skeleton, ortho cameras ("ortho": m). asset.preview now
  calls it (engine="cycles" keeps the old path).
- `shading.py`: export_asset writes `<asset>_shading.json` + `.md` (per material: maps with colour space / size /
  texel size / meaning, formulas, glTF extensions and what a plain viewer misses, Unity / Unreal / Godot lines; face
  shapes and couplings; LODs with switch distances).

## Motion (checklist tess_motion; reviews /mnt/data/hifipushie/assembly/review/motion_r1..r3)
- Retarget = world-space rest-relative rotation of each source bone (independent of bone axes / rolls), our LIMB rests
  (Shoulder, Arm, ForeArm, Hand, fingers, legs, feet) first aligned onto the source's rest (A-pose onto T-pose: the
  bone direction, and for a hand its roll by the index -> pinky knuckle line), the trunk keeps our posture; hips by
  height ratio; twist joints by the export's recipe (frame-agnostic swing-twist). The direction a bone points to is
  measured to the child that continues the chain IN BOTH skeletons (a hand: the MIDDLE finger; by child order it was
  the thumb in ours and the index in Xbot's: rolled, cocked hands = Joe's "Gumby" wrists, together with Godot's
  name-only retarget which left our A-pose rest uncorrected).
- Measured (@@direction, every frame): limb bone directions 0.0 deg from the source's, hands' roll 4.3 deg (the knuckle
  line), trunk within its rest offset; Godot's own import-time retarget (spikes/game_ready/retarget.py) tilted her head
  back: not used.
- Review r3: remaining MAJORs are torso lean / crouch / arm silhouette. DISPUTED WITH NUMBERS (run 0.4 s): Hips / Spine /
  Spine2 / Neck world directions ours vs source (0.035,-0.15,0.988)/(0.04,-0.212,0.976), (-0.042,-0.164,0.986)/
  (-0.048,-0.117,0.992), Spine2 ours 20 deg forward vs source 14, Neck ours 41 vs 36; thighs and forearms identical:
  the bones are posed as the source's; what differs is the mannequin's body (broad shoulders, long thighs, its own
  torso shape). A fairer reference would be the clip on a skeleton of OUR proportions (not built).

## Hair in the export (checklist tess_hair_export; reviews hair_r1, hair_r2; STUCK reported)
- The re-seat itself is right by construction (tie_hair carry_from th_W18: hair.fit_to_head moves the hairline and
  scales with the head; tp_h3's head is 7 mm lower and 8 mm further forward than tess_a1's) but the review sees a
  longer, wider, looser tail and shorter face wisps on the new head and body (her shoulders / neck differ).
- Card export, measured by hair.check_tiers (iou / bare / value / sat vs the strands, alpha test):
  before (v2): hero iou 0.65-0.77, bare 0.20-0.34, sat 1.72-1.91; cause found: (a) the W18 groom (volume rows, halo,
  curls: 1,010 locks) cut 7,123 cards = 243k triangles for a 40k hero, the budget then dropped whole layers AND the
  tail (kept 0 tail cards, 420 halo hairs); (b) the cards had no desaturation while the EEVEE strands draw the look at
  eevee_sat 0.3. Fixed: the cut coarsens until every lock's coverage layer fits 45 % of the tier (`CUT_GROUPS`,
  `CUT_SHARE`); budget priority: hanging hair before second layers, single hairs last (`PRIO_FREE`, `PRIO_FLY`);
  `card_sat` defaults to eevee_sat ** 0.55 (measured). After: hero iou 0.80-0.87, bare 0.10-0.17, sat 1.02-1.21,
  value 0.81-1.12; main iou 0.78-0.86.
- Still FAIL in review (hair_r2): tail darker and narrower than the strands, a lighter top "helmet" with a seam to the
  side cards, cards fan from one point at the part, face-framing wisps missing, a pale crown patch from the back,
  card-edge patchwork. These are the card cut's craft (hair_cards.clump_cards / atlas tiles): the hair thread's code.
- Hair LODs = the groom's own card TIERS (main / npc / far: one atlas for all), not thinned LOD0 cards.

## STATE / NEXT
STATE (Tess v3, 89k LOD0 incl. 40k hero hair; LOD1 45.6k / LOD2 27.7k / LOD3 20.8k): motion directions exact, review
disputes recorded; hair cards improved by numbers but FAIL review (STUCK sent); skin draft; undressed.
NEXT: rig bends (tess_rig) and expressions (tess_expressions) review loops in blender_game; engine skin Lab boxes;
Garrett only after Tess passes.
