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

## Hair export handover (to the hair-cards agent; the assembly agent keeps off hair_cards.py from here)
- Branch `worktree-agent-ad0815704f43e0e00`, commit f994fea (hair.py: CUT_GROUPS / CUT_SHARE coarsen the card cut to
  fit a tier; PRIO_FLY / PRIO_FREE budget order; full_look card_sat = eevee_sat ** CARD_SAT_EXP 0.55 when the look has
  eevee_sat and no card_sat) + asset.py (hair LODs = the groom's card tiers main / npc / far, lods.HAIR_TIERS) +
  tests/test_game_ready.py (test_cards_take_the_strands_desaturation, test_card_lod_thins_one_layer_by_whole_cards).
- Model ga_tess (tp_h3 head + th_W18 style / look through tie_hair carry_from th_W18). Re-seat strands: shots7 renders
  /mnt/data/hifipushie/assembly/hair/s_ga_tess_{v0,v1,v2,backl}.png beside th_W18's (tesshair7/out/s_th_W18_*).
- check_tiers (hair.export_hair check=True; tables in <dir>/ga_tess_hair.json "checks_text", sheets check_sheet.png):
  exp1 (before) /mnt/data/hifipushie/assembly/hair/exp1: hero iou 0.65-0.77, bare 0.20-0.34, sat 1.72-1.91, straight
  0.33-0.35; exp2 (cut + card_sat): iou 0.79-0.86, bare 0.11-0.18, sat 0.65-0.89; exp3 (+ priorities, sat exponent):
  hero iou 0.80-0.87, bare 0.10-0.17, value 0.81-1.12, sat 1.02-1.21, straight 0.19-0.37; main iou 0.78-0.86.
- Card cut before / after by family (hdiag.py: hair_cards.fit_budget patched to report): before, 7,123 cards / 243k
  triangles for 32k; kept gather layer 0 only, 0 tail cards, 420 halo. After: kept g hairline/dense layers 0-1, 85 tail
  dense + 11 medium (then tail first by PRIO_FREE), halo last.
- Reviews: /mnt/data/hifipushie/assembly/review/hair_r1/review.md, hair_r2/review.md (script hair_review.sh <export
  dir> 1 <out>): open MAJORs = tail darker / narrower, top "helmet" lighter with a seam to the side cards, cards fan from
  one point at the part, face-framing wisps missing, crown pale patch from behind, card-edge patchwork; re-seat: tail
  longer / looser, face wisps shorter than th_W18's.

## Motion: feet and the mannequin's "lean" (after motion_r4)
- Feet and toes now keep their own rest (both rests stand flat; our ankle -> toe-joint line is steeper than the
  mannequin's ankle -> ball, and aligning it stood the foot toe-down). ToeBase / Toe_End are in the rig and weighted (a
  30 deg toe turn moves the shoe front 34 mm, the sole 31).
- The mannequin's mesh vs its skeleton (bl_xbotlean.py: trunk centroid line vs Hips -> Neck): walk 1.5 / 3.5 deg,
  3.7 / 5.2, idle 2.2 / 1.8: its MESH does not lean more than its bones in walk; the forward read is its shape (a big
  chest ahead of the spine). (Run: 24 vs 12, but the hip band there includes the raised thigh.)

## Rig bends (checklist tess_rig; reviews rig_r1..r3; STUCK reported with gr_03)
- Bend helpers (rig.py `BEND`, half-angle joints, see the code comment) carry the hinge blend zone (166 vertices at an
  elbow, 199 at a knee, max weight 1.0) and are driven by the recipe (json rig.bend, bend_recipe; game render drives
  them). The game render's turns were adding to an already bent rest (MakeHuman's rest elbow is 38.7 deg): rig_r1 / r2
  judged 82 / 123 deg as "45 / 90"; now the asked joint angle is reported (@@turn) and the shots ask the true angle.
- rig_r3 (true angles): elbow 45 and 90, wrist 60, head turn 40 PASS; still MAJOR: elbow 120 crease pinch, knee 90 /
  120 back pinch + flat front, shoulder raised (deltoid tube, sharp armpit), seated hip (buttock bag, placeholder briefs
  dragged). Dual quaternion skinning and a delta mush (Corrective Smooth) over the same weights barely change these
  (sheet human_renders/gr_03_tess_rig_bends_stuck.png): the fix is pose correctives (corrective morph targets per
  joint angle, MetaHuman-style) and / or hand-painted hip / shoulder weights + more loops at the knee in the body
  topology. Not built.

- Would MakeHuman's own skeleton do better (A: default.mhskel + unfolded default_weights.mhw, B: our folded Mixamo
  rig)? Not for these bends, by construction: every bone the fold merges is a serial split of one segment
  (pelvis.L -> upperleg01 -> upperleg02 -> lowerleg01 -> lowerleg02 -> foot; clavicle -> shoulder01 -> upperarm01 ->
  upperarm02 -> lowerarm01) and turns rigidly with it in a hinge bend, so folding sums weights onto one bone with the
  same transform; LBS is linear in the weights, so A = B to the vertex. pelvis.L (buttock) and breast.L stay still in
  a hip / arm turn in MH too (they fold into Hips / Spine2). MH's extra bones only add (a) twist spread along the
  split segments (our twist joints) and (b) shoulder01 as a half-way clavicle joint, which only helps if something
  drives it: Mixamo clips don't; our ArmBend helper is that joint, driven. So the seated buttock bag and knee pinch are
  MakeHuman's own weights under plain LBS: the fix stays weights / loops in the file, then correctives.

## Expressions (checklist tess_expressions; reviews expr_r1..; shots shots_expr.json, crops.py)
- expr_r1 FAIL. Measured on the GLB (shapediag.py: stretched edges per shape; flipdiag.py: folded triangles;
  lipexp.py / ridge.py: GNM's own skin quads):
  - teeth: ONE part held both GNM rows; at the bite the field joined them, so jawOpen (lower row 20 mm, upper 0)
    stretched the joining triangles x5: the "shards". Now parts teeth / teeth_lower (base.TEETH_PARTS), each its
    own field and mesh, 1200 triangles a row (600 for both made a 1.6 mm max error; now 0.5).
  - lips: jawOpen solved its landmark turn with a near-free ridge (1e-6): coefficients to 6-10 sd, 31 flipped /
    37 >120 deg creases on GNM's skin. JAW_PRIOR 1e-4 on the jaw shapes: norm 5.7, the chin drops FURTHER (30 mm
    at 22 deg), 2 creases. GNM_OPEN 14 -> 22 deg (reviewer: "the jaw barely drops"). jawOpen_mouthClose now closes
    the gap jawOpen AS SOLVED opens (against the rigid turn the A2F combo warm f31 crossed the lips 3.8 mm).
  - smile targets 0.08 / 0.15 -> 0.12 / 0.21 mouth widths (corner out / up): "far too small".
  - the inner rolls are hidden in the closed neutral, so the bake filled them with skin: a brown fringe round
    every parted mouth. skin_features paints them (skin:inner_lip, GNM rings mouth loop .. contact ring).
- v7 (rows, prior, 22 deg, smile): a full upper row in the smile-with-teeth, lower teeth at jawOpen, wider smile.
  Still: brown fringe (fixed in v8), the neutral slit shows tooth tips, nostrils ragged (skin draft), the hair.

## Handover 2026-10-14 evening (assembly agent, context limit)
- Branch worktree-agent-ad0815704f43e0e00 (this worktree), not pushed; last commits: hair-card shading once
  (13e1d85), GNM mouth rows / jaw prior / 22 deg / smile (5832618), inner lip (1c249a3, 8d13770, + uncommitted ->
  committed with this note: inner lip painted IN THE BAKE by GNM index, asset.inner_paint / bake "inner_paint",
  skin_features.inner_lip_values; the scene-layer version painted the outer lips, v8).
- Scratch /mnt/data/hifipushie/assembly (env.sh, run.sh = light slot, heavy.sh, chain_exp.sh '<model>:<out>:<json>'
  = one export after another, ge.sh <glb> <json> <out prefix> <shots.json> = game-like EEVEE renders). Expression
  tools: shots_expr.json (neutral, blink, jaw 1.0, smile, smile+teeth, clay close-ups), crops.py (same crop of
  several renders), expr_review.sh <render prefix> <review dir> (bin/review against refs/tess_head_front*.png),
  shapediag.py (stretched edges per shape), flipdiag.py, teethshow.py (teeth seen from the front by ray),
  ridge.py / lipexp.py / coefs.py (GNM solve experiments), crosstest.py (A2F combos per jaw angle).
- Checklists: workspace/checklists/tess_*.json. Reviews: review/motion_r4 PASS; hair_r1..2 FAIL (handed to the
  hair-cards agent); rig_r1..3 (STUCK: knee / elbow 120 / shoulder / seated hip; MakeHuman's own skeleton is the
  same under LBS, see "Rig bends"); expr_r1 FAIL (round 2 not yet run).
- Exports: exp/ga_tess_v6 (approved head, before mouth fixes), v7 (rows + prior), v8 (scene inner-lip layer: WRONG,
  lipstick lips), v9 (layer tightened: no effect, the scene has no rolls), v10 RUNNING (bake inner paint).
  Renders eevee/x6..x9 (mouths.png = crop sheet per version).
- Open MAJORs (expressions): brown fringe at the parted lips (v10 should fix: check eevee/x10 mouths.png), neutral
  slit shows grey bits (teethshow: 0 teeth triangles visible at neutral, so it is the rolls' colour: v10 too),
  jaw-open inner upper lip shards (lip roll geometry; JAW_PRIOR cut creases 37 -> 2 on GNM's quads but the export
  still shows some), cheek raise / squint with the smile (cheekSquint is in the shots at 0.6: judge), no lash line
  at neutral (lashes: white glints on the cards in close-ups). Not ours: nostril rings, neck colour band, hair.
- Budget gate on v7+: eyes_mouth_lashes 8.2k of 5k (teeth 2 x 1200 + lashes 4880: lashes are never decimated in
  LODs either: a gap), hair 40k of 25k, body 16.9k of 15k, accessories 5.5k of 5k.
- NEXT: (1) render v10 (ge.sh ... eevee/x10/x shots_expr.json), crops, then expr_review.sh eevee/x10/x
  review/expr_r2; fix the worst MAJOR each round. (2) rig bends: repaint hip / shoulder / knee weights, more loops at
  knee / elbow / hip, then correctives in <asset>_rig.md/.json (seated hip first). (3) separate texture set for the
  head. (4) lashes in LODs. Garrett after Tess passes.

## Rig bends, round 2 (2026-10-14 night; reviews rig_r4..r6; sheet human_renders/gr_04_tess_rig_bends_stuck2.png)
- Arc weights (`rig.BEND_ARC`, `_arc_bend`, default; `rig.BEND_WEIGHTS = "overlap"` = before): each hinge with a bend
  helper repainted from geometry by SIDE: across the joint a vertex's turn phi goes 0 -> 1 over a zone that is wide on
  the outer side (knee front, olecranon, buttock, armpit) and narrow on the inner (crease); parent -> helper (half
  angle) -> joint. Geometric, so the briefs / top get the same weights as the skin under them. Shoulder needs a wide
  inner zone too (a narrow one kinked the raised shoulder's top); hip inner 0.10; midline side mask soft (ARC_MID).
- Pose correctives (`correctives.py`, export `correctives=True`): morph targets corr_<Side><Joint>_<motion><deg>
  (knee 90/130, elbow 60/100, shoulder raise 45/90; no hip: every hip target flattened the buttock and dragged the
  briefs), solved per mesh in the rest frame (delta = M^-1 (target - LBS)), target = the joint family's share turned
  round the pivot by phi x angle (radius kept) + a soft contact on the inner side's bisecting plane. Drivers: swing
  angle along the key axis, piecewise linear (json rig.correctives, <asset>_rig.md / .json via rignotes.py, one line
  per engine). blender_game drives them (drive_correctives; face-shape resets skip corr_ keys). LODs keep them.
  DEAD END: surface ARAP as the target. A bent tube held at both ends kinks like a straw (synthetic knee front 5.5 ->
  2.9 cm from the pivot, tests/test_rig_bend.py); what read as "rounded" in the c1 renders was that collapse.
- Tools: assembly/reweight.py <glb> <out> (re-weights a GLB with the current rig code, ARC='{json}' overrides),
  addcorr.py <glb> <out> [motions] (solves + appends correctives, json gets rig.correctives), corrplot.py (a slice
  through the joint, LBS vs corrected), loops.py / wire.py (wireframe close-ups), rig_review.sh, cmp.py.
- Reviews: rig_r4 (arc weights) FAIL, rig_r5 (+ ARAP correctives) FAIL, rig_r6 (+ arc correctives) FAIL. MAJORs that
  survived r3..r6 (4 approaches: MakeHuman-zone helpers / DQS / delta mush; arc weights; ARAP correctives; arc
  correctives with soft contact): back-of-knee V pinch, knee / elbow front "faceted, mitred pipe", seated briefs and
  buttock crumple, armpit corner + top's side edge dragged, shoulder cap flat. By eye knee / elbow at 90-120 are
  rounder than r3; the seated briefs are no better. Not tried: more loops at knee / elbow (the wrap topology is ~1.5 cm
  quads: 6 edges round a 90 deg knee front; the body is already 16.9k of the 15k hero budget), real bent-limb
  reference photos for the review (the "reference" is the rest pose; none found licence-clean quickly).

## Rig bends, round 3 and close (coordinator, 2026-10-14: keep arc weights + correctives; judge seated on bare skin;
## joint-aware density; what's left is KNOWN GAPS, no more looping on bends)
- Joint-aware body density (`topodensity.py`, export default, parts.body.joint_density): a loop across the limb in
  every hinge-zone quad (1121 faces on Tess: +2468 triangles), new vertices projected on the field; the rest of the
  body away from joints, hands, feet and neck decimated by as many (7824 -> 5356): same 39948. rig_r7 (v11): the
  knee / elbow front "faceted" MAJOR is gone.
- KNOWN GAPS (also in every <asset>_rig.md, rignotes.KNOWN_GAPS), rig_r7: inner creases at 90+ (elbow crook, back of
  knee) fold into a notch; elbow end-on reads as a cap; wrist 60 hinge kink; raised arm: shoulder-top step, no
  clavicle lift, armpit corner, the tight top's side edge follows the arm; seated hip 90: thigh lifts as a block,
  hard groin edge, flat thigh underside. Seated judged on bare skin (shots_bends3 hides the briefs).

## Expressions, rounds 2-4 (expr_r2 v10, expr_r3 v11, expr_r4 v12)
- v10: brown fringe gone (inner lip painted in the bake). v11: the mouth sock (GNM group mouth_sock, 406 low-poly
  vertices, hidden in the closed scene, so baked grey) painted wet red to dark (skin_features.mouth_interior_values,
  inner_paint channel 2, MOUTH_DEEP_COLOR / _RINGS): the grey lip dot and grey shards gone; neutral PASS from r3.
- Blink (routed from the skin agent: pale sliver under the lashes, red slits past the corners): measured with
  assembly/eyegap.py (rays from the front that first hit the eyeball; open height per third). v10/v11: 2.0 / 2.75 /
  1.75 mm open (inner / mid / outer): GNM's own blink doesn't close Tess's lids. The lid seal now runs on GNM-indexed
  heads too: v12 0.5 / 0.5 / 0.75 mm, blink PASS in expr_r4. v13 (running): LID_OVER 0.8 mm, overlap kept nearer the
  corners (LID_FADE 0.44-0.5). Checklist item blink_seam_measured (tol 0 mm) added to tess_expressions.json.
- Cheek / squint: CHEEK_RAISE (0.13, 0.04) x wg: cheekSquint 2.8 -> 6.3 mm; SQUINT_LOWER 0.35 -> 0.8 (0.8 lands in v13,
  v12 still 2.8 mm). Shots: smile = mouthSmile 1 + mouthUpperUp 0.3 + mouthLowerDown 0.15 + cheekSquint 0.6 +
  eyeSquint 0.6 (the reference smile shows teeth; an ARKit capture of it would carry those channels).
- expr_r4 (v12) open MAJORs: jaw open: lips part too little for the drop (a small "o"), upper teeth hidden behind the
  upper lip, a faceted bright-red mass in the upper opening (the tongue? check by hiding it), lower lip everted, corners
  pinch; smile: no eye involvement (v13), lips pressed in the middle, corners pinched with cheek pouches beside them,
  no nasolabial fold (skin.folds expression could carry it: skin_folds.expression); smile with teeth: teeth small /
  gapped / fang tips near the corners (GNM teeth at 1200 triangles a row: check decimation vs GNM's own), lower lip
  droops showing red interior.
- LODs: lashes thinned by whole lashes (lods.LASH_LODS 0.5 / 0.25 / 0.1: 2440 / 1216 / 488). LOD0 still 4880 (the
  hero eyes+mouth+lashes budget is 5k with teeth 2 x 1200: lash counts are the head's look, base.lashes, not mine).

## Handover 2026-10-14 late (assembly agent, context limit)
- Worktree branch worktree-agent-ad0815704f43e0e00, not pushed. Code this session: rig.py arc weights; correctives.py;
  topodensity.py; rignotes.py (<asset>_rig.md / .json, KNOWN_GAPS); asset.py hooks (correctives, density, rig notes,
  sock paint), lods.py (correctives kept in every LOD, lash thinning), faceshapes.py (cheek / squint / lid seal),
  skin_features.py (mouth interior), blender_game.py (drive_correctives), server.py (correctives option);
  tests/test_rig_bend.py (passes). test_face_shapes.py full run passed (13 ok) before the face-shape edits of this
  session: re-run it (bin/slot, ~30 min).
- Exports: exp/ga_tess_v11 (density, correctives, sock), v12 (+ lid seal), v13 RUNNING (lid overlap 0.8 mm, squint
  0.8; chain log out/chain_v13.log). Renders eevee/x11, x12 (expressions), r11 (bends). Reviews expr_r2..r4,
  rig_r4..r7 (bends CLOSED as known gaps by the coordinator).
- NEXT: (1) v13: eyegap.py (target 0 mm in every third), ge.sh ... eevee/x13/x shots_expr.json, expr_review.sh ->
  review/expr_r5; worst MAJOR first (jaw-open lips / teeth / interior, then smile corners and fold). (2) re-run
  tests/test_face_shapes.py. (3) separate head texture set (hero: 2048 head, 2048 body+clothes): the head and body are
  ONE export part ("body", split into head / body meshes only at write_glb), so the atlas step must give the head
  mesh's triangles their own atlas (or the part split into two parts before the unwrap; face shapes go by GNM index
  and the seam ring must stay identical). (4) Garrett after Tess.

## Expressions, rounds 5-7 (2026-10-15; expr_r5 v13, expr_r6 v14; v15-v17)
- Corrective resets: blender_game's two shape-key resets already skipped corr_ keys (53615db6); the export preview's
  pose loop (blender_asset) did not: fixed; tests/test_corrective_resets.py checks every `kb.value =` site (ast).
- Blink: v13 (LID_OVER 0.8) measured 0 / 0 / 0 mm open (eyegap.py, both eyes). expr_r5: "closure line straight,
  a strip pasted across the eye" -> LID_SAG 1.2 mm (the lid line dips mid-eye); expr_r6: blink no MAJOR.
  test_blink_lids_meet's crossing bound is now LID_OVER + 0.5 mm (the lower lid lags the dipped line ~0.35 mm).
- Smile: the landmark solve (corners out / up) gave pinched corners, cheek pouches, no fold. GNM's expression CVAE has
  class prototypes (gnm_sampler: happy, smile_wide, squint, surprise ...): `happy` x2 on Tess's GNM head pulls the
  corners up AND back into a crescent, bunches the cheeks and forms nasolabial folds (assembly/proto: proto.py ->
  OBJs, bl_objclay.py -> clay renders). mouthSmileL/R = its lower-face components x SMILE_PROTO[1], per side
  (tanh across the midline, SMILE_SIDE_MM), inner lips closed again by a solve in rounds (17 -> 0.2 mm);
  cheekSquint += its eye components. No height mask on it (the mask cut the cheek move). GNM's regional basis
  stops dead on the outer cheek (x2: 3 mm against 0 at x 62 mm): a terraced crease at the cheekbone in the export
  (crease.py: 50-59 deg on 5 mm edges) -> _soft_edge (moves under 0.7 of the largest blended toward their
  80-round quad average). Diagnostics: stair2.py (export target == GNM's own offsets at matched vertices, exact),
  creaseg.py, stairg.py.
- Teeth: the field rows (IMLS shell, 0.4 mm, decimated to 1200) were "jagged pegs with gaps, fang tips"; GNM's own
  1414 quads a row are clean (proto/tsheet.png). asset.own_mouth_meshes puts GNM's quads (rows AND tongue) into the
  high mesh; their raw vertices are own_surface (v15 forgot: prune_hidden dropped the rows); min_triangles 4000
  keeps them whole. Budget: rows 2 x 2828 + tongue: eyes_mouth_lashes was already over (8.2k of 5k).
- jawOpen: the upper lip held (JAW_UPPER_LIFT landmarks) barely moves in the basis (-0.5 mm of +6): uplip.py on v16:
  the upper lip edge 1.3 mm BELOW the incisal edge -> JAW_LIP_LIFT 4.5 mm direct lift of GNM's upper_lip group
  (feathered; jawOpen_mouthClose subtracts it). Tongue: rigid with the jaw (a turn about the ear line fitted to
  the lower row) + TONGUE_DROP 7 mm dorsum flattening (its back filled the opening: "red mass").
- Review crops: expr_review.sh now adds mouth / eye close-ups (excrops.py, boxes mapped by eye spacing): the
  reviewer couldn't judge teeth from 700 px faces.
- STATE (v17 exporting): open from expr_r6: jaw (no upper teeth, red interior, chin narrows to a V, corners
  notched), smile (stairs, grey gum slabs, lower lip everts in smile-with-teeth). Head-specific scripts take the
  model name (tp_h4 may replace ga_tess's head).

## Handover 2026-10-15 (assembly agent, context limit)
- Branch worktree-agent-ad0815704f43e0e00 (main merged at 7f472faf), not pushed. This session (see "Expressions,
  rounds 5-7" above, plus): smile lips kept in front of the teeth (faceshapes._clear_teeth, LIP_CLEAR); the smile's
  cheek "stairs" were BLENDER's split UV-seam normals (Blender ignores morph NORMAL deltas): blender_game now imports
  with merge_vertices (job "merge_vertices": false turns it off); the smile keeps the height mask (mouth shapes stay
  under the lower lids: test_gnm_head_shapes); blink's mid-eye dip on the UPPER lid only (LID_SAG; the lower lid
  untouched: test_blink_seal_leaves_the_cheek). blender_game debug switches: GE_NOAO, GE_NOSHADOW, GE_ENGINE
  (BLENDER_WORKBENCH = geometry check), GE_PLAIN; sun shadow texels 0.2 mm.
- Measured: v13 blink 0 / 0 / 0 mm (eyegap.py); v18 same. v17-v18 renders (eevee/m18/mouths.png): jaw open shows both
  rows and a low tongue, the closed smile is clean, the toothy smile shows an even upper row. Not yet reviewed:
  expr_r7 is owed on v20.
- RUNNING: v20 export (all of the above; out/chain_v20.log), test_face_shapes.py (out/test_face_shapes.log; the previous
  run passed every test up to test_gnm_head_shapes, which the mask restore fixes). Remote renders: ger.sh
  (spikes/offload/job_ge.py on NICO-TOP; commit first) were still QUEUED after ~40 min (offload/ge103021 smoke test,
  ge103502 = x18 set): check offload/*/client.log; if NICO-TOP stays busy, the 4-shot mouth set (shots_m4.json) is a
  light local check, the full set + review is the gate.
- NEXT: (1) x20 on NICO-TOP: `bash ger.sh exp/ga_tess_v20/ga_tess.glb exp/ga_tess_v20/ga_tess.json eevee/x20/x
  shots_expr2.json`, then `bash expr_review.sh eevee/x20/x review/expr_r7` (now with mouth / eye close-ups). Known
  leftovers to expect: grey-lavender gums and faceted red inner-cheek walls in jaw open (gums: the painted cloud is on
  CC-subdivided points, the rows are now GNM's raw quads: check the teeth bake, "4.5% texels kept the low-poly
  surface"; walls: the sock is 406 low-poly vertices), chin narrowing to a V at jawOpen (JAW_PRIOR solve), lower lip
  everting in smile-with-teeth. (2) re-run test_face_shapes until clean. (3) head texture set: per-part atlas is an
  int everywhere (rasterize already draws per triangle); cleanest is a per-triangle atlas for the body part's "head"
  mesh (p["meshes"]) through unwrap/pack, bake and write_glb's material per mesh. (4) Garrett on gp_h6c.
- Head-specific work is by model name (ga_tess); if Joe approves tp_h4, re-export with its model in chain_exp.sh.

## Expressions, rounds 7- (2026-10-15 late; expr_r7 on v21)
- Remote renders (ge103021 / ge103502) sat queued 30 min on NICO-TOP: canceled (bundle_client.py cancel <batch uuid>,
  OXIDEGEN_TOKEN from ~/.config/oxidegen/hifipushie-cloth-token). Local ge.sh is light: 13 frames in 23 s. excrops.py's
  boxes assume the shots' own sizes (700 / 600): rendering at 512 put every close-up on the chin (expr_r7 pairs 5-9 void).
- Lips "wet plastic" (coordinator, m18): the visible inner rolls carried INNER_PAINT_ROUGHNESS 0.25 (all red front
  vertices at 0.251: lips/liprough.py) -> 0.4; bag and gums 0.4 / specular 0.5. Streaks at grazing angles remain at
  0.4 (v21): the parted smile shows the rolls themselves (below).
- Gums: their albedo is right (lips/teethcol.py: gum sRGB 173 82 84, crowns 219 212 189); the "lavender" was sky
  specular on glossy surfaces (flat-albedo workbench render, lips/bl_albedo.py: no grey anywhere in the albedo).
- jawOpen (v20 albedo): the tongue filled the opening up to the upper incisors -> TONGUE_DROP 11 mm; upper crowns
  half under the lip -> JAW_LIP_LIFT 7.5 (v21: gum band, "teeth set back") -> 6. expr_r7 MAJORs: the opening an
  everted "O" (lips thicken; reference: thin lips round a wide oval) -> JAW_CORNER_OUT 0.06 mouth widths a side,
  JAW_LOWER_BACK 0.04 on the outer lower lip; corners' sock walls lit pink -> MOUTH_DEEP_RINGS 3 -> 2.
- Smile: the reference "smile" shows the upper teeth and barely squints: shots_expr3.json = the reference's mix
  (upperUp 0.5, lowerDown 0.3, eyeSquint 0.2, cheekSquint 0.3). With the lips parted, v21 showed the pink inner rolls
  where the teeth should be: mouthUpperUp / LowerDown moved the lip FORWARD (+0.02): now back onto the teeth.
  Still open from expr_r7: puffy cheeks with no nasolabial fold (smile), teeth "small pegs set back".
- Teeth size (lips/teethsize.py, v21): upper row 27 mm wide 6 mm behind its front (real inter-canine ~34), crowns
  ~7 mm visible (real 10.5); the upper lip's front 8.6 mm before the incisors at the midline.
- Budget: parts.<p>.max_triangles (asset._max_triangles -> blender_asset: a ceiling after the focus extra) for a
  LOD0 split; not yet set for the mouth (v18: eyes 566 + teeth 2 x 2828 + tongue 1824 + lashes 4880 = 12926 of 5000).
- expr_r8 (v22, shots_expr3): smile still no teeth (the smile's closed inner lips held against upperUp's 0.045 at the
  centre) -> upper up / lower down move the centre 0.09, sides 0.11, z 0 (back onto the teeth cut them through the
  seam). Tongue "a boxy panel with vertical sides" (11 mm flatten) -> TONGUE_SINK 6 mm rigid + 6 mm flatten: v23 shows a
  dark throat over a low tongue. Teeth "small pegs" -> base._grow_crowns: crowns 1.35x from the biting edge (gum carried),
  arch 1.05x. Blink close-up: a pale pink line at the closed margin; NOT the blink multiplier (GE_NOBLINKMAP render
  identical); faint in the flat albedo too (lips/bl_albedo_eye.py): open.
- expr_r9 (v23, squint 0.4 / 0.45): squint flips between "identical to neutral" (0.2 / 0.3) and "slits" (0.4 / 0.45):
  shots_expr5 0.3 / 0.35. Teeth "irregular, canines fang-like": GNM's mean row has canine tips ~1 mm BELOW the centrals
  and ~1 mm left / right difference (identity has no teeth coefficients) -> the edge levelled onto a smile arc
  (TEETH_ARC 0.8 mm at 16 mm). Inner corners "torn lining" (r7, r8, r9; clay: crumpled low-poly sock walls beside the
  teeth, lit pink) -> the sock dark by depth behind the lips' front (MOUTH_DARK_DEPTH 4-8 mm) on top of the rings.
  Jaw "squared, pinched corners, lower lip rolls out" -> corners 0.04, lower lip back 0.07.
- test_gnm_head_shapes: the smile moved far vertices 0.44 mm (GNM's prototype) -> MOUTH_REACH fade (12-15.5 cm).
- expr_r10 (v24): neutral "notch / wedge at the seam left of centre": the flat albedo (lips/bl_albedo.py, no shapes)
  shows the inner-lip pink as a jagged band ON the closed lips (the contact ring at 1, the next at 0.3) -> the
  contact ring fades (0.3), nothing past it. Corner rolls darkened by depth too: reverted (dark lines past the corners
  in the smile). Squint: 0.3 / 0.35 read "no squint", 0.4 / 0.45 "slits": shots_expr6 0.35 / 0.4.
- expr_r11 (v25): the depth-dark sock (4-8 mm) showed as dark shards in the closed seam -> 8-12 mm (v26). Still MAJOR:
  a lighter rectangular patch on the lower lip's left (in the albedo too: a bake / atlas artefact, not paint; open),
  the jaw opening "a rounded rectangle, a hole cut in the face" (lips don't roll over the teeth), the tongue "a flat
  slab", the teeth "small, floating, gaps", corner walls "lumpy, with voids", smile "torn seam, no clean incisors".
- tests/test_face_shapes.py passes in full on v25's code (mirror tolerance relative; far-field fade).

## Handover 2026-10-15 evening (assembly agent)
- Branch worktree-agent-ad0815704f43e0e00, not pushed; every step committed. v26 exporting (exp/ga_tess_v26: the
  sock dark from 8-12 mm). Local renders: `bash ge.sh exp/ga_tess_vN/ga_tess.glb exp/ga_tess_vN/ga_tess.json
  eevee/xN/x shots_expr6.json` (13 frames ~25 s; keep the shots' own sizes: excrops.py's boxes assume them), then
  `bash expr_review.sh eevee/xN/x review/expr_rM`. Diagnostics in /mnt/data/hifipushie/assembly/lips/: liprough.py
  (roughness at the lips), teethcol.py (tooth / gum colour by height), teethsize.py (arch widths, incisal edge per x,
  lip stand-off), bl_albedo.py / bl_albedo_eye.py (flat basecolor renders with shapes: what is paint vs shading).
- STUCK candidates (same MAJOR after 3 different approaches): (a) jawOpen inner corners (roughness 0.4; sock dark
  after 2 rings; dark by depth): the clay shows GNM's sock walls crumpled beside the teeth: a GEOMETRY fault
  (smooth the sock's jawOpen offsets, or more sock resolution), not paint. (b) teeth "small / floating / uneven"
  (lip lift + tongue sink; crowns 1.35x; edge levelled onto an arc): the reference's lips wrap the teeth; ours stand
  off them and open as a hole. Open, not tried: the chin narrowing to a V (JAW_PRIOR solve), smile cheeks without a
  nasolabial fold, the closed lid without a crease, the lower-lip rectangle (bake).
- Budget (item 2), measured on v18-v25 (unchanged): eyes 566 + teeth 2 x 2828 + tongue 1824 + lashes 4880 = 12926
  against budgets.json hero eyes_mouth_lashes default 5000, range [3000, 8000], basis "thin" (no per-part source).
  The lever is in place, untested on the look: parts.<p>.max_triangles (teeth / teeth_lower / tongue). Splits:
  within the range: teeth 2 x 1400 + tongue 900 + lashes at 3 segments (3660) + eyes 566 = 7926; at the default
  5000 the lashes must drop to ~1700 (fewer lashes: an eye-look change, Joe's call). Head + body (39948) + 12926 is
  52874 against the hero's 50000 LOD0.
- expr_r12 (v26): NEUTRAL REGRESSED: "the lips don't close, a dark jagged gap the full width, a pink-red sliver
  left of centre" (r7 on v21: neutral MINORs only). Changes since that touch the closed mouth: MOUTH_DEEP_RINGS 3 -> 2
  (v22), the sock dark by depth (v24-26), the contact ring's paint 1 -> 0.3 (v25), tooth crowns 1.35x / arch 1.05x
  (v23: may poke through the closed lips). First step for the next round: bisect these on the neutral (flat albedo +
  clay close-ups), revert what opened the seam.
- NEXT: that bisection; then the sock geometry at jawOpen; the budget split export (max_triangles) judged on the
  m4 mouth set + eye close-ups; head texture set; Garrett.

## Expressions, rounds 13- (2026-10-16; expr_r13 v27, expr_r14 v28)
- NEUTRAL SEAM REGRESSION, bisected on the exports v20..v26 (eevee/seam/: textured, clay and blink close-ups of the
  closed mouth, shots_seam.json): the CLAY was the same in every version: a flap left of centre (and a sliver right)
  above the seam since v20, at least. Sections of the export's head (seam/slice.py, slice_lev.py: quads coloured by lip
  ring) showed the UPPER inner roll (rings 0-1) folded FORWARD past the contact ring by ~1 mm at 6-9 mm either side of
  the midline: the low poly's open-mouthed rolls stood proud of the seam and rode the close (_lips_meet) with it. GNM's
  own full-res verts don't do it (gnm_world closes clean). What changed in v25 was only the PAINT: the contact ring's
  wet colour 1 -> 0.3 uncovered the skin's dark lip line on the upper lip as a jagged dark band (the flat albedo
  shows it), plus the flap. Fixes: faceshapes._rolls_behind (every vertex inside the contact ring kept ROLL_BEHIND
  0.3 mm behind the contact line along `out`, part of the meet a parting shape takes back) and the paint back to
  ring 1 / next 0.3. Gate: GnmFace.seam_showing = a front orthographic z-buffer of the closed mouth, mm^2 of pixels
  whose front-most triangle has a vertex inside the contact ring (one-pixel seam lines don't count): v26 4.57 ->
  0.00; logged per export ("closed lips' seam ... neutral 0.000, eyeBlinkLeft 0.000", WARNING over SEAM_SHOWING
  0.05) and asserted in test_jaw_leaves_the_body_under_the_neck. expr_r13 (v27): neutral MINORs only.
- v27 also: head tp_k19 (approved, sethead.py), parts.teeth / teeth_lower max_triangles 1400, tongue 900 (lashes
  unchanged: the lashes agent): eyes_mouth_lashes 9147 (566 + 2 x 1400 + 900 + 4880), head 23020 + body 16914 +
  9147 = 49081 of the hero's 50000 LOD0. Neck seam: the head and body share the seam ring's 110 vertices (0 mm).
- jawOpen corners, GEOMETRY: a fast loop without exporting: seam/exppose.py (the export's head = topology_body verts by
  GNM index, closed and posed as faceshapes.apply does, + GNM's teeth rows) -> OBJ -> seam/bl_objw.py clay (~1 min).
  The crumpled corner walls are the export's sock TUCK (retopo._with_mouth_sock narrows it 45% within 4 mm of the
  lips' loop): GNM's own sock posed in its own frame (seam/gnmpose.py) is smooth. Smoothing only what the shape adds
  did nothing; ironing the rest's sock too (Taubin 40 passes over GNM's quads, skin held, in the neutral: hidden there,
  seam_showing still 0) gives smooth cavity walls (seam/e_jaw_r40.png): faceshapes._smooth_sock.
- Lips onto the teeth (_wrap_teeth, WRAP_*): the rolls stand 3.7-4.9 mm (radially, from an arch centre 22 mm behind
  the incisors) off the teeth AT REST, so a wrap relative to rest (never further off than at rest) barely moves the
  smile; an absolute wrap (WRAP_KEEP 0) pulled the whole lip back behind the incisors (seam/e_st_k0.png: the lips'
  own thickness is in that gap). Kept relative (WRAP_KEEP 1). What reads wrong in the smile is the upper roll as a
  band facing forward-down between the vermilion and the teeth, not a stand-off.

- Smile, parted (_rolls_tucked): each lip's inner roll kept no further past its own lip's edge (the contact ring at
  its x, along `up`) than ROLL_TUCK_SLACK 0.3 mm: the band over the teeth goes, the upper edge meets the crowns and the
  lower incisors' edges show (seam/e_st_t.png). _smile_fold: a nasolabial crease (1.5 mm deep, 2.2 wide) along nose
  wing -> past the corner, the cheek pushed out 2 mm on its outer side, the corner lifted 2 mm (seam/e_f2.png).
- "Skin reads grey" WAS OURS: blender_game used AgX, which rolls lit skin off toward grey; the skin looks
  (skin_look.py) and glTF viewers use Khronos PBR Neutral. Now the default (seam/kpn_face_front.png vs
  eevee/x28/x_neutral_front.png beside refs/tess_head_front.png: warm, like the reference).
- expr_r14 (v28) / expr_r15 (v30: rolls behind, sock ironed, rolls tucked, smile fold, PBR Neutral): NEUTRAL and
  BLINK have no MAJOR (r15). Still MAJOR: jawOpen a round "O" (reference a wider oval), no tongue seen (a flat red
  back wall), upper teeth small / set back under a pink band, "hard black vertical strips" at both sides (the ironed
  sock walls, now flat planes edge-on: eevee/x29 crops), ragged corners; smile: no cheek / lower-lid raise, a dark
  purple band under the upper lip (the tucked roll's underside / gum in shadow), teeth flat rectangles in a straight
  row (the reference arcs up with the corners), a kink in the lower lip right of centre; smile+teeth: lower teeth
  floating blocks. tests/test_face_shapes.py passes in full on this code.

## Handover 2026-10-16 (assembly agent, context limit)
- Branch worktree-agent-ad0815704f43e0e00, every step committed, not pushed. Latest export exp/ga_tess_v30 (head
  tp_k19, teeth 2 x 1400 + tongue 900 split, lashes unchanged for the lashes agent). LOD0: head 23020 + body 16914 +
  eyes/mouth/lashes 9147 = 49081 of 50000 (eyes_mouth_lashes itself 9147 against its default 5000, range 3000-8000:
  over only by the lashes' 4880, the lashes agent's).
- Fast loop for mouth geometry (no export, ~1 min): seam/exppose.py <obj> "<shape=w,...>" [faceshapes.CONST=value ...]
  then blender -b --python seam/bl_objw.py -- <obj> <png> <ortho> <x> <z>. Sections: seam/dump.py (GLB -> npz, shapes
  applied) + slice.py / hslice.py; slice_lev.py on diag2.py's npz (lip rings coloured). Seam bisect renders:
  shots_seam.json -> eevee/seam/v<N>_*.
- NEXT, in order: (1) jawOpen sides: the ironed sock walls stand as flat planes edge-on (black strips): fewer Taubin
  passes, or iron only the tuck's rings near the loop and let the walls curve back to the bag; consider SOCK_NARROW
  / SOCK_TUCK in retopo (the tuck made the folds). (2) jawOpen opening an "O": JAW_CORNER_OUT up again with the
  sock now smooth (it was "squared, pinched" with the crumpled walls). (3) smile: lower-lid / cheek raise
  (CHEEK_RAISE, eyeSquint in shots_expr6), the dark band under the upper lip (tuck slack / the roll's paint), the
  lower-lip kink right of centre (look at e_sm.obj in clay). (4) teeth: crowns 1.35x kept for now (the smiles show
  a full row; untested reverting). (5) then the head texture set, then Garrett.

## Expressions r16 (2026-10-16, fresh session): lid orange, sock walls diagnosed
- LID ORANGE WAS OURS (the export), fixed: the blink-multiply map was written as the RAW LINEAR ratio (blender_scene bakes
  color / color_blink as linear floats; ratio = with / without) but declared sRGB in the shading notes (shading.py) and so
  sampled as sRGB by blender_game (and any engine): decoded ~ratio^2.2, the crease + lid occlusion ~twice as dark and
  shifted orange (blue darkened most). asset._srgb now encodes it like basecolor (commit 2acac6bb). Same-camera check
  (eevee/lid/, shots_lid.json; cmp.png = v30 as exported | v30 with the map re-encoded (v30s) | blink map off): the
  re-encoded lids are mildly warm, like skin_look's own studio render of ga_tess (eevee/lid/sl_face.png). SSS off and the
  plain glTF materials (s_n / g_n) ruled out SSS and the view transform. NEEDS a re-export to land in the GLB.
- NOSTRILS (not fixed, ours): orange-brown with bright speckles inside the nostrils in EVERY material mode (as exported,
  SSS off, plain glTF: eevee/lid/nos.png), while skin_look shows dark nostrils: it is in the BAKED basecolor / AO of the
  nostril cavity (suspect bake rays or the cage in the cavity, or the scene's occlusion that the atlas doesn't carry).
  Next: crop basecolor at the nostril charts, compare with the scene's colour pass there.
- LASHES (from the lashes agent): every LOD carries the full lash mesh (4880 tris, ~30% of LOD3). Once its branch
  (worktree-agent-ac021191615c62c32) merges, the LOD chain uses lashes.lod_config (its notes in its game_ready.md).
- jawOpen SIDE WALLS, diagnosed, not fixed. Loop: seam/r16/run2.sh <tag> "<shapes>" [k=v]: exppose2.py (= exppose.py, but
  RE-RUNS retopo._with_mouth_sock on the v27 topology with retopo constants as k=v too, and saves P/Xn/g npz) + clay
  render; ~2.5 min. seam/r16/lap.py <npz|gnmpose obj>...: p90 umbrella-Laplacian (mm) of the sock by ring from the skin.
  Ruled out (each changed nothing visible, jaw_*.png): the sock narrowing (SOCK_NARROW 0 / SINK 0: jaw_b), the
  nearest-vertex carry of the head's pushes (new retopo.SOCK_CARRY = False: jaw_c), the direct jaw moves (corner out,
  lip lift, upper lift, lower back all 0: jaw_e), wrap / tuck off (jaw_f). The roughness numbers: sock ring 1 / 2 are
  3.4 / 2.6 in OUR NEUTRAL (n_s0) vs GNM's own rest 0.85 / 2.0 (gnm_rest), deeper rings equal; jawOpen adds ~0.1. So the
  crumple is IN THE REST TOPOLOGY next to the lips' loop, before any shape; Taubin ironing (SOCK_SMOOTH) only flattens
  it into planes (the black edge-on strips). Carrying the neutral's lip moves (meet, corners, rolls behind) into the
  sock's first 4 rings harmonically (tried, reverted) only took ring 1 from 3.4 to 3.1: not the cause either.
  Likely cause: the skin's loop in V (field drop / head pushes / gnmloops) vs the sock placed from GNM's rest: the
  first rings shear. NEXT: in retopo._with_mouth_sock replace the nearest-vertex carry + narrowing by a graph-harmonic
  extension of the loop's offset (V[loop] - place(GNM[loop])) into the sock, fading to 0 over ~4-6 rings; re-measure with
  lap.py (target ring 1 ~1, as GNM's), then SOCK_SMOOTH lower / 0 and look at the clay; then the oval (JAW_CORNER_OUT),
  tongue (TONGUE_SINK / DROP: no tongue reads in the opening), smile items as in the 2026-10-16 handover.

## Handover 2026-10-16 r16 (assembly agent, tool-call limit)
- Committed: the blink map fix (2acac6bb); retopo.SOCK_CARRY (default True, no change to exports). Not exported yet:
  the next export (v31) carries the blink fix; run expr_review.sh on it, pair_0 should lose the orange lids.
- Order: (1) re-export v31, confirm lids in pair_0; (2) the sock's rest shear (above, NEXT); (3) jaw oval + tongue;
  (4) smile items; (5) nostril bake; (6) lashes LODs after the lashes merge; then the head texture set, Garrett.

## Expressions r17 (2026-10-16, fresh session): sock falloff, oval, tongue back
- THE r16 SOCK EXPERIMENTS NEVER RAN: seam/exppose2.py stripped the "sock tail" assuming the sock's vertices are the
  topology's LAST ones; in v27's topology_body they aren't (later steps append), so n0 = len and _with_mouth_sock
  returned early (every sock vertex already present): retopo k=v (SOCK_NARROW / SINK / CARRY) changed nothing. Fixed
  (exppose2 strips the sock's vertices wherever they are and reindexes the faces; a default re-add reproduces the
  exported sock to 0.0 mm; run2.sh uses seam/exppose2.py, keep r16/exppose2.py a copy). It also writes GNM's tongue now.
- retopo.SOCK_FALLOFF = 6 (commit fc7352cc): the lips' loop's offset from GNM's rest (V[loop] - place(GNM[loop]))
  extended into the sock as an umbrella-harmonic field (held at the loop, 0 from ring 6), eased by a smoothstep of the
  ring; replaces the nearest-vertex carry and the tuck (SOCK_FALLOFF_NARROW keeps a share of the tuck, default 0).
  lap.py p90 (mm) neutral unironed: ring 1 3.42 -> 2.00, rings 2-7 now equal GNM's own rest (1.95 2.09 1.45 2.04 2.62 vs
  1.97 2.13 1.42 2.04 2.62; GNM ring 1 0.85). Clay jawOpen (seam/r16/J_cmp_zoom.png: default | falloff unironed |
  ironed 10 | ironed 40): the black edge-on strip at the left wall is gone with the falloff; unironed is cleanest, so
  faceshapes.SOCK_SMOOTH 40 -> 0. Neutral seam_showing 0.0 in every variant.
- JAW_CORNER_OUT 0.05 -> 0.09 (seam/r16/J_oval.png: 0.05 | 0.07 | 0.09 | GNM): wider oval, no pinch now (commit 7f61836a).
- TONGUE (flat albedo, lips/bl_albedo.py, ALB_HIDE=tongue: seam/r16/alb_v30_jaw*.png): the "flat red back wall" IS the
  tongue's dorsum, a flat-coloured panel over ~70% of the opening; lit, it takes the same red as the walls. Added
  skin_features skin:tongue_back (TONGUE_BACK (0.012, 0.03) m behind its tip: darkens to MOUTH_DEEP_COLOR). Untested in
  an export yet (v32 should carry it if it started after 7f61836a; check the log's paint layers).
- NOSTRILS: flat basecolor from below (ALB_CAM=0.028,-35 bl_albedo.py: seam/r16/nos_basecolor.png): each nostril has a
  PALE skin-coloured crescent on the inner wall of the ala, the rest orange-brown. So it is in the basecolor (skin
  layers' projection / the CAVITY term in skin_layers.py ~l.520 only darkens UNMEASURED texels with low AO: the inner alar
  wall probably counts as measured, the photo's rim skin projected onto it). Not fixed. (ALB_MAP, swapping the ao png in,
  does not work yet: the active image node isn't the basecolor's.)
- RENDERS go to NICO-TOP (Joe's rule, 2026-10-16): assembly/rge.sh <export dir> <tag> <shots.json>... (job_ge.py, detached,
  offload/<tag>/; results/<tag>/j<N>/out.tar). Laptop only for small crops / flat passes.

- v31 (exp/ga_tess_v31) = v30 + the lid map's sRGB fix only (its import came before the r17 defaults). v32
  (exp/ga_tess_v32) = r17: sock falloff, unironed, oval 0.09, tongue_back at 12-30 mm. Neutral seam_showing 0.000.
  Flat albedo jawOpen v30 | v32 (seam/r16/alb_v30_v32_jaw.png): the oval is wider; the tongue went BLACK over all its
  visible dorsum (too much): TONGUE_BACK now (0.028, 0.05) (committed, not exported). Little white flecks at both lip
  corners in the flat albedo (v30 too): teeth tips through the corners? look in the lit renders.
- Renders submitted to NICO-TOP (detached clients, both queued at handover): offload/x31 (j0 = shots_expr6, j1 =
  shots_lid) and offload/x32 (same). When back: tar xf results/<tag>/j0/out.tar -> out/x_*.png, then
  `bash expr_review.sh offload/x31/results/x31/j0/out/x review/expr_r16` (lids in pair_0 / blink pair) and the same for
  x32 -> review/expr_r17.

## Handover 2026-10-16 r17 (assembly agent, tool-call limit)
- Branch worktree-agent-ad0815704f43e0e00, every step committed, not pushed.
- NEXT: (1) unpack x31 / x32 renders, run expr_review on both (x31: confirm the lids lost the orange; x32: jaw walls,
  oval, tongue). (2) re-export v33 for TONGUE_BACK (0.028, 0.05); look whether the tongue reads pink in the lower half
  and dark behind, like refs/tess_head_front_jaw_open.png; consider a central groove / lighter tip. (3) smile items
  (2026-10-16 handover). (4) nostrils: the pale crescent on the inner alar wall in BASECOLOR (seam/r16/nos_basecolor.png):
  check skin_layers' CAVITY gate (measured vs unmeasured) at those texels; fix bl_albedo ALB_MAP (swap the image linked
  to Base Color) to see the AO map there. (5) lashes LODs after the lashes merge.
- tests/test_face_shapes.py NOT re-run on r17's defaults (SOCK_SMOOTH 0, SOCK_FALLOFF 6, JAW_CORNER_OUT 0.09): run it
  (one file per process) before the next review.

## Expressions r18 (2026-10-16, fresh session)
- NOSTRIL CRESCENT diagnosed (nosdiag.py / nosdiag3.py in the scratch; seam/r17_nos_uv.png = UV crop albedo | measured |
  cav before | cav after): the nostril's unmeasured region is wider than its dark core; the cavity term's AO ramp
  (CAVITY 0.85 / 0.45) gives the inner alar wall (AO 0.7-0.85, filled from the rim's skin: lum 0.83-0.87 of open skin)
  almost nothing. Measured texels there are few and already dark (551 in the nose under AO 0.65, lum 0.25 vs 0.43).
  Fix (commit 6ef4386b): skin_layers.CAVITY_SPREAD = (2.5 mm, x2.0, AO under 0.97 eased over 0.12): the core's darkness
  blurred and carried over the rest of the SAME unmeasured region (max with its own; region gate as before). Not yet
  seen in a bake (v33 started before it: check whether its skin layers carry it).
- v33 (exp/ga_tess_v33) = TONGUE_BACK (0.028, 0.05), launched via chain_exp.sh (role hero).
- Lip-corner white flecks (flat albedo v30 / v32): teeth-coloured, the upper back teeth seen at the corners; judge in
  the lit x32 renders before changing anything.

- tests/test_face_shapes.py on r17's defaults (SOCK_SMOOTH 0, SOCK_FALLOFF 6, JAW_CORNER_OUT 0.09): 13 ok, 0 skipped,
  EXIT 0 (out/tfs_r18.log). RUN IT WITH env.sh SOURCED: without HIFIPUSHIE_ASSETS the GNM tests SKIP and it still says ok.
- x31 (v30 + lid sRGB fix) reviewed: review/expr_r16/review.md. LIDS CONFIRMED: neutral / blink have no lid-colour fault
  (MINOR only: flat closed-lid line, pale outer-corner gap, bunched lashes). NEW MAJOR in the neutral mouth close-up
  (pair_5): a dark slit along the lip line with a blue-grey speck left of centre (inside-mouth geometry through the seal).
  Old-sock export; check it in x32 / x33 before working on it. Nostrils: "orange-brown glowing holes" (MAJOR, other stage).
- v33 exported (exp/ga_tess_v33, 79566 tris, TONGUE_BACK 0.028-0.05): flat albedo seam/r18_v32_v33.png (v32 jaw | v33 jaw |
  v32 nostrils | v33 nostrils, the last at a different camera): the tongue now pink in front, dark behind. Lip-corner
  white flecks still there (teeth). Renders submitted: offload/x33 (shots_expr6 only), detached.
- NOSTRIL FIX NOT IN ANY BAKE, AND IT NEEDS A DECISION: the stack maps live in ga_tess's spec (skin.stack, made by
  skin_layers.apply). Re-running apply("ga_tess") changed EVERY map (max 170/255 over the whole atlas), dropped the
  crease / crease_strength and reset hand-set opacities (periorbital 0.5 -> 0.4, lips 0.9 -> 0.8): code drift since the
  stack was made. Restored exactly (store history; backup seam/ga_tess_spec_pre_r18.json). Options: (a) a narrow
  re-make: recompute only the cav delta and add it into the existing shade / redness maps (needs the stack image <-> atlas
  texel mapping: stack box, at["ii"]/["jj"]); (b) re-apply in full and re-set crease + opacities, then re-judge the whole
  skin (the skin isn't approved for tess: no skin/tess in approved.json). (a) is the safe one.

## Handover 2026-10-16 r18 (assembly agent, tool-call limit)
- Branch worktree-agent-ad0815704f43e0e00, committed, not pushed.
- NEXT: (1) x32 (still queued on NICO-TOP at handover) and x33: unpack (tar xf results/<tag>/j0/out.tar in that folder),
  `bash expr_review.sh offload/x32/results/x32/j0/out/x review/expr_r17` and the same for x33 -> review/expr_r18; jaw walls,
  oval, tongue, the neutral lip-seal slit. (2) nostrils: option (a) above, then a flat pass (bl_albedo with ALB_CAM; note
  the camera differed from r16's nos_basecolor.png: match it). (3) smile items (2026-10-16 handover: shots_expr6 already
  has cheek / eye squint). (4) lip-corner flecks in the lit renders. (5) lash LODs after the lashes merge.

## r19 (2026-10-16, fresh session)
- x32 / x33 still QUEUED on NICO-TOP at session start (projskin's s15 batch ahead); a background wait is on them.
- NOSTRILS, option (a) DONE: nosfix.py (scratch) = decompose(spread on) - decompose(spread off) on the SAME code (drift
  cancels: every other layer's delta 0.0000), the od delta multiplied into the EXISTING shade / redness stack images only
  (exp(-od) recovered from the stored multiplier at P0); opacities (periorbital 0.5, lips 0.9, brows 0.4) and crease 1.0
  kept. ga_tess saved (store history; pre-r18 backup seam/ga_tess_spec_pre_r18.json). The stack's head key (6249f59d9ca4)
  is not the spec head's (294e80bfe72e): head dict edited after the stack, same GNM topology (atlas shape checked).
  UV crop seam/r19_nos_fix_uv.png (albedo | shade before | after | albedo x shade x redness before | after): the left
  nostril's inner wall now dark; the RIGHT nostril keeps a pale lobe with a hard outline at its upper-outer side: hard-edged
  in the albedo itself = a projected (measured) texel patch, outside the cavity term by design -> skin stage (projskin), not
  export. Not in any export yet: v34 needed.
- v34 (exp/ga_tess_v34, role hero, exit 0) = v33 + the nostril delta. Flat basecolor from below (ALB_CAM=0.028,-35,
  ortho 0.06): seam/r19_nos_v33_v34.png: the WHITE HOOKS on each inner alar wall are UNCHANGED. They sit on MEASURED texels
  (seam/r17_nos_uv.png, measured panel: the hooks / the right nostril's outlined lobe are inside the measured area): the
  photo's rim skin / highlight projected onto the inner wall. Not reachable by the cavity term (unmeasured only, by
  design) and not export-side: OTHER STAGE (skin projection: projskin's measured-gate at nostril interiors, e.g. a
  facing / AO gate on what counts as measured). For the coordinator to route; the export takes the approved skin.
- x33 CANCELLED (superseded), then x34 (v34) cancelled for x35. x32 (v32) back: review/expr_r17/review.md, FAIL, 19 MAJOR.
  Tongue black (known, fixed since v33: TONGUE_BACK 28-50). NEUTRAL WORSE than x31: seam/r19_neutral_r16_r17.png (x31
  top | x32 bottom): x32 has jagged dark-red shards along the whole lip line, x31 only the slit + speck. Suspect r17's
  UNIRONED sock (SOCK_SMOOTH 0): crumpled sock through the seal (seam_showing 0.000 numerically, so the gate misses it).
  Smile / smile+teeth: purple show-through above the upper teeth, ragged upper-lip edge, torn corners, no eye squint /
  cheek lift (shots_expr6 HAS eyeSquint / cheekSquint: too weak or not reaching the lower lid), teeth uneven / jagged
  pushing into the upper lip, lower row floating fragments. jawOpen: 4 small upper teeth vs 8 lower (reference: big upper
  row), torn inner-lip rim. OTHER STAGES: hair cards broken across the forehead; nostrils dark brown holes.
- TEETH_BACK (skin_features, 012d13ea): each teeth row darkened 9-22 mm behind its front (strength 0.8, linear
  [0.1, 0.075, 0.06]): the buccal-corridor shadow (r16 pair_7: "teeth run all the way into the corners"). Depth check:
  canines at 5-9 mm (half-width ~17 mm), molars 22+ mm. v35 (exp/ga_tess_v35, exit 0) = v34 + TEETH_BACK.
- x35 (v35, shots_expr6) SUBMITTED to NICO-TOP, detached, queued behind the hair batches.

## Handover 2026-10-16 r19 (assembly agent, tool-call limit)
- Branch worktree-agent-ad0815704f43e0e00, committed, not pushed. Latest export exp/ga_tess_v35.
- NEXT (fix EVERY independent MAJOR per round, gates.md 2026-10-15): (1) x35 back: tar xf in
  offload/x35/results/x35/j0, `bash expr_review.sh offload/x35/results/x35/j0/out/x review/expr_r18`; judge TEETH_BACK
  in the smile close-ups, the tongue (pink front / dark back), the nostrils. (2) NEUTRAL SEAL: test SOCK_SMOOTH back on
  (x31's ironed sock had no shards) with r17's falloff kept; make the seal gate see shards (seam_showing 0.000 while the
  render shows them). (3) Smile, grouped by cause: geometry (upper-lip edge ragged / purple through: _rolls_tucked +
  sock under the upper roll; corners torn), teeth geometry (jagged, uneven, into the lip; lower row fragments; jawOpen
  upper row small: TEETH_CROWN_GROW / jaw prior), expression strength (eyeSquint / cheekSquint in shots_expr6 up, or
  CHEEK_RAISE). (4) Lash LODs: lashes branch still NOT merged to main (checked r19): blocked.
- Nostril white hooks: measured texels (skin stage), for the coordinator to route.

## Expressions r20 (2026-10-16, fresh session): the neutral's lip shards were a texel-projection fault
- x32's "dark-red shards along the closed lip line" are NOT GEOMETRY: the clay mouth close-ups x31 | x32 are identical
  (seam/r20_clay_n31_n32.png); GnmFace.seam_showing on the export's head (seam/seamx.py <export dir> [k=v]) is 0.000 for
  v31, v32 and v32 ironed, at view tilts -12..12 deg; the shading normals there are identical. They are in the BAKED maps:
  the flat albedo (lips/bl_albedo.py, ortho 0.045) of v32 has pale, hard-edged streaks torn across the upper lip's inner
  band (seam/r20_alb_n31_n32.png); lit, they read as dark-red shards.
- SOCK_SMOOTH 40 (v36) changed nothing (seam/r20_alb_31_32_36.png). CAUSE: retopo.SOCK_FALLOFF 6 (r17). The export's
  "body: N% of texels kept the low-poly surface" went 3.75% (v30/v31) -> 4.89% (v32-v36): texels of the upper lip's band
  projected onto the wrong exact surface (the moved sock). SOCK_FALLOFF 0 (v37): streaks gone, 3.75% again
  (seam/r20_alb_31_36_37.png). Commits b5e78222, 0722b0cf. SOCK_SMOOTH stays 40 (x31's sock = v37's sock).
- The r17 jaw-wall gain of the falloff is lost again (the black edge-on strips at the jaw's walls may come back: judge
  in x37). If the falloff is wanted for jawOpen, it must keep the sock off the lips' texel projection (asset.py ~l.1020:
  _project of each texel onto its part's exact surface; bad = moved > 6 vx).
- MEASURE (brief: "fix the measure first"): PARTLY DONE, FAIL as a gate. seam_showing now counts GNM's sock as inside
  (the rings' BFS runs over the skin only: sock faces read lev 99 = outside), takes `tilt` and `normals` (shading normal
  along the view per pixel, face._seam_facing). Neither catches x32: the fault isn't geometric. An image-side measure
  on the flat albedo (tears = luminance off a 7 px box mean, dark or light, off the seam line) did NOT separate v31 from
  v32 (the streaks are low-contrast in the albedo: |lum - blur| p99.9 0.023 vs 0.026) and on the lit 0.37 mm/px neutral
  it missed the band; not committed. What does separate: the head's astray-texel share (3.75 vs 4.89%), but it is a
  whole-part number. NEXT for the measure: the astray / moved-texel share restricted to the lips' texels (faces with a
  GNM lip-ring vertex), logged with a WARNING over the v31 value, and a test that builds v32's case (SOCK_FALLOFF 6).
  No test written this round.
- Smile strength: shots_expr7.json = shots_expr6 with cheekSquint 0.7 / eyeSquint 0.6 in both smiles (0.4 / 0.35 were
  below what an ARKit / Audio2Face capture gives for a full smile); the shapes themselves unchanged (CHEEK_RAISE, SQUINT_LOWER).
- NOT DONE this round (b, c): the smile's ragged upper-lip edge / torn corners; teeth (jagged upper row into the lip,
  floating lower fragments, ~4 upper teeth in jawOpen). The neutral fix may change what the smile shows (same baked band).
- Hair cards across the forehead: hair stage (noted, not touched). Lash LODs: blocked on the lashes merge.

## Handover 2026-10-16 r20 (assembly agent, tool-call limit)
- Branch worktree-agent-ad0815704f43e0e00 at 0722b0cf + this note, committed, not pushed; main's bef0229c cherry-picked.
- NICO-TOP, both QUEUED (detached): x35 (v35, shots_expr6) and x37 (v37 = SOCK_FALLOFF 0 + SOCK_SMOOTH 40, shots_expr7).
- NEXT: (1) x37 back: tar xf in offload/x37/results/x37/j0, `bash expr_review.sh offload/x37/results/x37/j0/out/x
  review/expr_r19`; check the neutral seal (pair_0 / pair_5), the jaw walls (falloff off), the smile's squint / cheek.
  x35 is superseded by x37 for the neutral; review it only if x37 is late (expr_r18). (2) the lip-texel astray measure +
  test (above). (3) smile lip edge / corners and teeth (b, c), grouped, one export, one batch.

## Expressions r21 (2026-10-16, fresh session)
- LIP GATE (asset.bake, asset.lip_front_share): the astray-texel share of the lips' FRONT band alone: texels in front
  of the inner rolls (inner_paint roll weight > 0.5, the sock left out), within 1.2 half-widths across / 0.6 up-down
  of the rolls' centre, the rolls themselves left out (hidden in the closed seam: 28% astray even when clean). Logged
  per part, report parts.<p>.lip_astray {share, warn}, WARNING over asset.LIP_ASTRAY_WARN 4.5%. Measured: SOCK_FALLOFF 0
  (= v31/v37) 2.48%, 6 (= v32) 6.51%. A NARROW margin (2.6x); first tries that failed: the whole head 3.75 vs 4.89%,
  the rolls incl. sock 89%, the rolls alone 28 vs 41% (both warn), a 50 mm ball 39 vs 45% (the buried sock dominates).
  tests/test_lip_astray.py (HEAVY: two exports, hero, face_shapes [jawOpen], no rig / LODs; outputs + texel dumps
  (HP_ASTRAY_DUMP) in /mnt/data/hifipushie/assembly/exp/lipgate/f0, f6; KEEP=1 re-measures the dumps in seconds;
  launcher /mnt/data/hifipushie/assembly/lipgate.sh) asserts the clean case under and v32's case over the threshold.
- SMILE WEIGHTS, sources: no published table of ARKit capture values for a full smile was found (searched Apple's
  ARFaceAnchor docs, ARKit-to-FACS cheat sheets, Express4D). What the sources do give: cheekSquint = FACS AU6 (cheek
  raiser, orbicularis oculi pars orbitalis), eyeSquint = AU7 (lid tightener, pars palpebralis), mouthSmile = AU12
  (melindaozel.com/arkit-to-facs-cheat-sheet); AU6 tracks AU12's INTENSITY (Krumhuber & Manstead 2009; Girard et al.
  2020, "the Duchenne smile is likely an artifact of smile intensity"): a full AU12 (mouthSmile 1.0) comes with a strong
  AU6. So cheekSquint 0.7 (close to the smile) and eyeSquint 0.6 (AU7 is weaker / less coupled) stand, as an inference
  from those, not a measured value. The measured route: Express4D (arXiv 2508.12438, Live Link Face CSVs, 61 ARKit
  coefficients at 60 fps, free-text prompts incl. smiles; dataset behind a Google form, not requested): mean
  cheekSquint / eyeSquint over its "smiling broadly" frames.

- Lip gate verified end to end: the full test rerun (both exports with the final code) PASSES. The export log is clean at 0
  (2.48%) and WARNS at 6 (6.51%).
- Planned for the round-3 fixes (from the expr_r17 crops; NOT applied; the x37 review comes first):
  (c) teeth: the GNM rows are GNM's own 1414 quads = 2828 tris (own_mouth_meshes), but the spec's parts
  teeth / teeth_lower max_triangles 1400 halves them. That decimation is the likely source of the jagged, uneven crowns
  and the lower-row "fragments". Try max_triangles 2900 per row (+~3k tris, inside hero). jawOpen shows ~4 upper
  teeth: the upper lip's corners hang over the laterals / canines. Try faceshapes.JAW_UPPER_LIFT outer 0.06 -> ~0.10
  (inner 0.12 kept), and check against the reference's 6-8 upper teeth.
  (b) the smile's purple band above the upper teeth and the ragged upper-lip edge: judge in x37 first (v37 fixed the
  baked band in the neutral; the smile shows the same band).

## Handover 2026-10-15 r21 (assembly agent, tool-call limit)
- Branch worktree-agent-ad0815704f43e0e00, committed, not pushed. Commits this session: 1fd7cf4e, 8ac93423, 736c6b1e
  + this note.
- DONE: (2) the lip gate (asset.lip_front_share, LIP_ASTRAY_WARN 4.5%, report lip_astray, tests/test_lip_astray.py
  PASS end to end). Smile weights: sources recorded above. cheekSquint 0.7 / eyeSquint 0.6 kept as an inference,
  not a measured value.
- NOT DONE: (1) x37 review: x37 (and x35) were still QUEUED on NICO-TOP at 19:44 (client processes alive, pids under
  rge.sh; behind other agents' GPU jobs). (3) the grouped fix round.
- NEXT: (1) when x37 lands: tar xf in offload/x37/results/x37/j0, `bash expr_review.sh offload/x37/results/x37/j0/out/x
  review/expr_r19`, count the MAJORs by cause. Check the jaw walls (black edge-on strips, falloff off), the neutral seal, the
  smile's squint and the upper-lip band. Cancel x35 if x37 is back (superseded). (2) one round grouped by cause: the
  teeth max_triangles + JAW_UPPER_LIFT above, plus whatever x37 shows. Then export v38 (the lip gate's line must read under
  4.5%), one NICO-TOP batch with shots_expr7, then the blind review.
- Disk: exp/lipgate holds two full exports (316 MB). Delete f0 / f6 except the astray_body_0.npz dumps once the gate
  is accepted.

## Expressions r22 (2026-10-15, fresh session)
- x37 review chained DETACHED: assembly/chain_x37.sh (offload wait x37 && tar xf && expr_review.sh ... review/expr_r19;
  writes review/expr_r19.ERROR if the wait fails or renders are missing, .DONE when the review is written). Log
  review/chain_x37.log. x37 still QUEUED at 19:45.
- (c) TEETH: spec parts teeth / teeth_lower max_triangles 1400 -> 2900 (ga_tess history 14): the rows are GNM's own
  2828 tris again (export log "teeth 2828 tris"). Flat jawOpen zoom v37 | v38 (assembly/teeth/r22_zoom_v37_v38.png):
  the incisal edges straighter and the laterals rounder; the outlines are still POLYGONAL (GNM's row is ~88 quads a
  tooth: coarse by design). If x37 / the next review still calls the crowns jagged, the next lever is one subdivision
  level of GNM's quads (own_mouth_meshes) under a lower cap, not more decimation. Export quality line: folded edges
  42 / 74 (was 23 / 26) against the FIELD's surface, which GNM's own mesh doesn't follow: not a fault by itself.
- jawOpen UPPER TEETH (teethcount.py <glb> jawOpen 1: per row, the front-projected area seen past the head mesh, its x
  extent, and the seen height at the centre +-4 mm). Reference (expr_r17 pair_6): 6-8 upper teeth, WHOLE crowns with the
  lip at the gum line. v37: 63 mm^2 seen, x -14..14 mm (~4 teeth), centre 2.2 mm seen. v38 (JAW_UPPER_LIFT outer 0.06 ->
  0.10, inner 0.12): 79 mm^2, x -18..17 mm (~6 teeth: width now matches), centre 2.8 mm seen: HEIGHT FAILS (the upper
  lip's wet inner band hangs over two thirds of the crowns: flat montage teeth/r22_alb_v37_v38.png). Trying inner 0.18
  (v38b). Lower row v38: 347 mm^2, centre 8.2 mm (reference: whole lower crowns).
- LIP GATE on v38: "body: 2.43% of the lips' 5966 front texels kept the low-poly surface" (< 4.5%, no WARNING).
- OPEN QUESTION FOR JOE (not acted on): the smile weights cheekSquint 0.7 / eyeSquint 0.6 are an INFERENCE (sources in
  r21). A measured value needs the Express4D dataset (arXiv 2508.12438), which is behind a Google form whose submission
  agrees to its terms: Joe's call whether to request it.

- x37 BACK (review/expr_r19/review.md, FAIL, 21 MAJOR in stage + 2 other stages). MAJORs grouped by CAUSE:
  1. TEETH (x37 = 1400-tri rows): jaw "4 upper teeth, floating stubs"; smile / smileteeth "sliced, uneven, hard dark
     edges, gap between centrals", lower row "tiny separate pegs". -> v38 GNM's own 2828 tris; jawOpen upper show v38c
     (JAW_LIP_LIFT 10 mm + JAW_UPPER_LIFT (0.18, 0.10)): ~8 upper teeth, whole crowns (teeth/r22_alb_v38_b_c.png).
  2. EXPRESSION WEIGHT: smile / smileteeth "eyes squint far too hard, slits". The r21 inference (cheekSquint 0.7 /
     eyeSquint 0.6) is REFUTED for this rig: shots_expr8 = cheekSquint 0.4 / eyeSquint 0.25.
  3. MOUTH-SOCK WALLS: jaw "flat dark-grey vertical slabs up both inner sides" (predicted r20: falloff 0 + SOCK_SMOOTH 40
     irons the walls into planes edge-on). Test v38d = v38c + SOCK_SMOOTH 0 (falloff stays 0: the lip texels don't move).
  4. COMMISSURES: jaw, smile, smileteeth "torn red inner-lip edges, black / grey gaps at the corners". NOT addressed.
  5. LIP CONTOURS in shapes: smile "upper lip with rectangular stepped notches a third in from each corner"; smile /
     smileteeth "doubled, smeared lower-lip contour half a lip-height below" (baked texels or the roll's shape: look at
     the flat albedo of the smile first); smileteeth "pink band above the upper teeth" (MINOR now). NOT addressed.
  6. TONGUE: jaw "tongue missing, flat dark-red back wall with a dark band" (flat albedo: the tongue IS there, pink, low
     and back: TONGUE_BACK darkening + its pose). NOT addressed.
  7. JAW SHAPE: "squared trapezoid opening", "lower face stretched into a narrow V". NOT addressed (jaw prior / CORNER_OUT).
  8. NEUTRAL SEAL: "dark-red interior line along most of the width, blue-grey fleck left of centre". Still open.
  OTHER STAGES: hair cards broken (hair); nostrils dark-ringed with orange-brown insides (skin).

- v38d (exp/ga_tess_v38d) = v38c + SOCK_SMOOTH 0 (source back at 40: v38d is a TEST export only). Lip gate 2.43% on
  v38c and v38d (no WARNING).
- x38 SUBMITTED to NICO-TOP (one batch, two jobs, shots_expr8): j0 = v38c, j1 = v38d. assembly/rge2.sh <tag>
  <export>:<shots> ... launches variants side by side. Reviews chained DETACHED: assembly/chain_x38.sh -> review/expr_r20_c
  (v38c) and expr_r20_d (v38d), with .DONE / .ERROR files; log review/chain_x38.log. (Launch the chain AFTER the client
  log says "queued": the first chain ran too early and got "offload: no batch named").

## Handover 2026-10-15 r22 (assembly agent, tool-call limit)
- Branch worktree-agent-ad0815704f43e0e00, committed, not pushed. Commits this session: c4df72ed, f7fa3aae, (jaw lift
  commit), c9d33ccb + this note. Spec ga_tess history 14: teeth / teeth_lower max_triangles 2900.
- DONE: x37 reviewed (expr_r19, FAIL, grouped above). v38c fixes the teeth cause (GNM's own count; jawOpen ~8 upper teeth,
  whole crowns) and the squint weights (shots_expr8). Lip gate under 4.5% on every v38 export.
- NEXT: (1) when x38 lands (review/expr_r20_c.DONE / _d.DONE): judge v38c vs v38d on the jaw walls (cause 3); keep
  SOCK_SMOOTH 0 only if v38d's walls read as a cavity AND the neutral seal / lips are no worse. Check the teeth (crowns
  smooth enough? if not: one subdivision of GNM's quads) and the squint. (2) causes 4-8 above (commissures, smile lip
  contours, tongue, jaw shape, neutral seal): start from flat-albedo crops of the smile (baked vs geometry). (3) FROM THE
  COORDINATOR (not started): two eye-region faults in the export, absent from the skin agent's gate render (sclera
  blotchiness .22 there vs photo .27; socket colour within 1 a*/b*): (a) the sclera is blotchy in the export, (b)
  orange-brown shading in the socket. Compare the export's eye / skin materials with the gate render's shader (sclera
  texture and colour space; the socket's AO or redness map baked in). Sheet: lashes/sheets/lash_r5_photo_ribbons_cards.png.
  The pink rim round the eye opening is the skin stage's waterline paint, not ours.
  (4) Joe's open question: the Express4D form (above).

## Expressions r23 (2026-10-15, fresh session)
- MEASURES (assembly/mouthhits.py, eyealb.py, tonguealb.py; copies in spikes/game_ready/): numpy flat passes of the GLB,
  no Blender, ~3 s. mouthhits: front orthographic ID + albedo of the mouth (0.25 mm/px) per shots_expr8 pose; the
  OPENING = teeth / tongue / head faces NOT seen from the front in the neutral (inner rolls, sock); its width at 15/50/85%
  of its height, walls (head edge-on share), torn (back faces), corners (back / edge-on within 6 mm), tongue share / top /
  albedo, edge jumps, the neutral seal band's darkest / median albedo. eyealb: sclera albedo (lum CoV, Lab) and the
  socket / lower lid against the cheek; TEX=<map> samples another map (ao).
- REFERENCE (refs/tess_head_front_jaw_open.png, traced on a 10-px grid, +-0.05): opening aspect 1.23, width at 15/50/85%
  0.76 / 0.97 / 0.73; tongue top at 0.48 of the opening height.
- BASELINE v38c: jawOpen aspect 1.16, width 0.91 / 0.99 / 0.70 (the squared TOP: upper lip flat, sides vertical), walls
  6.2% edge-on (v38d SOCK_SMOOTH 0: 4.2%, but the smile shows more sock face-on 12 vs 7.7%: not decisive, x38's review
  decides), tongue 34% of the opening, top at 0.41 (NOT low: higher than the reference), seen albedo (122, 58, 58) with a
  black band: the visible dorsum lies 36-42 mm behind the tip, inside TONGUE_BACK (28-50 mm); the tongue's front texels
  read (158, 77, 77): G/R 0.49 (reference tongue, lit, 0.66). Smile corners: 5-6% back faces, 22-25% edge-on (torn).
  Neutral seal: darkest/median p10 0.60. Smile doubled lower lip: in the ALBEDO, already in the neutral (a lighter lip-
  coloured band below the vermilion): the texture's lip vs the mesh's lip, not the shape (skin / projection).
- EYES (coordinator's two faults): the export's eyes are 0.6 mm/texel (the iris pixelated into the sclera: flat pass
  mh/v38c_eye_alb.png) and the SCLERA'S BAKED AO is mean 0.38, CoV 0.77, p5 0.02 (the rest pose's lid shadow, baked):
  the blotchy sclera. The socket's AO is 0.73 vs the cheek's 0.93 and its albedo -10 L, +2-3 b* vs the cheek: the
  orange-brown socket under engine AO. The skin agent's gate render uses the scene shader (no baked AO): why it is clean.
- v39 CHANGES (each with its target): asset.EYES_AO_OFF (the base's eyes part AO = 1: real-time eyes take the lids'
  occlusion as they stand) -> sclera AO >= 0.95; spec parts.eyes.texel_density 4 (ga_tess history 15) -> <= 0.2 mm/texel,
  sclera albedo lum CoV < 0.2 (v38c 0.29 / 0.36); TONGUE_BACK (0.028, 0.05) -> (0.04, 0.06) and the tongue colour
  [0.62, 0.3, 0.3] -> [0.62, 0.46, 0.43] -> seen tongue albedo G/R >= 0.6, no black band. SOCK_SMOOTH stays 40 (v38c).
  NOT in v39 (measured, next): the opening's squared top (15% width 0.91 -> ~0.78; JAW_UPPER_LIFT's outer lift vs the
  teeth count: needs a fast shape -> mouthhits path, not a 14-min export per try), the smile corners' back faces, the
  neutral seal, the lip texture's double band (skin stage?).

- v39 MEASURED (assembly/mh/v39.txt; the first launch failed: tpart is per triangle, fixed): tongue seen albedo
  (149, 110, 103), G/R 0.74, dark band gone (TARGET MET); eyes 0.2 mm/texel in atlas 1 (MET), flat pass
  mh/v39_eye_alb.png: iris detailed, visible sclera smooth white (v38c: blocky). eyealb's sclera band (6.5-11 mm off
  the axis) also takes faces UNDER the lids: its CoV (0.38 / 0.25) and AO (0.88 / 0.82, p5 0.01) don't measure the
  visible aperture: NEXT restrict it to faces seen in a front raster. Socket albedo unchanged (-10 L, +2-3 b*: the
  skin paint; its AO -10..-25 L vs the cheek stays, real cavity). Lip gate 2.50% (< 4.5%). Mouth shape numbers =
  v38c (unchanged by design). Upper teeth jawOpen 262 mm^2 seen, x -22..22.
- x39 SUBMITTED (one job, v39, shots_expr8); review chained DETACHED: assembly/chain_x39.sh -> review/expr_r21
  (.DONE / .ERROR, log review/chain_x39.log). x38 still QUEUED (chain_x38.sh alive -> expr_r20_c / _d).

## Handover 2026-10-15 r23 (assembly agent, tool-call limit)
- Branch worktree-agent-ad0815704f43e0e00, committed, not pushed (4452090a, AO-mask fix, this note). Spec ga_tess
  history 15: parts.eyes.texel_density 4.
- NEXT: (1) x38 reviews (expr_r20_c / _d): SOCK_SMOOTH 0 only if v38d's walls read better and the smile's sock is no
  worse (measured walls 6.2 -> 4.2%, smile sock face-on 7.7 -> 12%). (2) expr_r21 (v39): the tongue and eye rows;
  keep each change its MAJOR row confirms, revert regressions. (3) open causes, measured, not yet changed: jawOpen's
  squared top (15% width 0.91 vs ref 0.76: build a fast faceshapes -> mouthhits path before tuning JAW_UPPER_LIFT /
  JAW_CORNER_OUT against teethcount); smile corners' back faces 5-6%; neutral seal p10 0.60; the lower lip's double
  band is in the ALBEDO (skin / projection stage: route to the coordinator).

## STATE / NEXT
STATE / NEXT: see "Handover 2026-10-15 r23" above.

## r24 (2026-10-15, assembly agent): fast shape path, jaw arch, smile corners, seal target
- FAST PATH: export with HP_SHAPES_DUMP=<pkl> (asset.py pickles {spec, parts, face_shapes} right before
  faceshapes.apply), then spikes/game_ready/shapesfast.py <pkl> <glb for textures> <out> [CONST=v ...] [-- poses]:
  apply with faceshapes constants overridden (only the measured poses' shapes) -> mouthhits.measure + teethcount.count.
  ~1 min a try (apply 17-32 s) instead of a 14-min export. VALIDATED: unchanged constants give v39's jaw / smile
  numbers exactly. Dump of v39: /mnt/data/hifipushie/assembly/fast/v39dump.pkl. mouthhits.py is now load() / measure()
  (window widened to x +-42 mm: the smile's corners were at the old +-34 mm edge); old script kept as mouthhits_v1.py
  (eyeflat / tonguealb exec it).
- SCLERA (eyealb.py): only samples a front ray reaches past the head (lids): v39 left 284 / 1050 samples seen,
  L 49 CoV 0.52 (dark: was 58.5 / 0.38 over all front faces), right 240 / 924, L 68 CoV 0.29. The left eye's visible
  sclera is darker and blotchier than the right's: an asymmetry for the eye row of expr_r21.
- NEUTRAL SEAL target (lit crops, darkest / median luminance per column across the lips band): reference p10 0.27
  median 0.36; ours (x37 render) 0.29 / 0.34. The seam's darkness as rendered MATCHES the reference: no change. The
  albedo's p10 0.60 is not a fault by itself (shading darkens the seam in both). What the neutral crop shows instead is
  colour: a dark-red streak and a blue-grey fleck on the seam (x37), skin / bake, not the seam depth.
- SWEEPS on the fast path (assembly/fast/sweep1..5.log; v39 dump; numbers = mouthhits / teethcount):
  | try | jaw 15/50/85% | aspect | upper teeth seen (x range) | centre crown seen |
  | v39 (flat lift) | 0.91/0.99/0.70 | 1.16 | 262 mm^2 (-22..22) | 6.4 mm |
  | ARCH 0.5 pow 2 | 0.81/0.98/0.70 | 1.18 | 225 (-19..19) | 6.4 |
  | ARCH 0.7 pow 2, lifts .24/.14, corner .07 | 0.77/0.97/0.70 | 1.14 | 235 | 7.2 |
  | ARCH 0.9 pow 3, lifts .26/.16, corner .11 (TAKEN) | 0.79/0.96/0.71 | 1.15 | 294 (-19..20) | 7.8 |
  | + GNM_OPEN 20.5 | 0.80/0.97/0.67 | 1.18 | 286 | 7.8 (lower row 8.3 -> 7.2: not taken) |
  Reference 0.76/0.97/0.73, aspect 1.23. The aspect barely moves with CORNER_OUT (0.06-0.11: width 47.5-48.5 mm);
  only the jaw angle moves it (height). Left at 1.15: OPEN.
  SMILE CORNERS (cause found): the nasolabial crease (SMILE_FOLD, run SMILE_FOLD_PAST past the corner) cut INTO the
  commissure: back faces within 6 mm of each corner 5.4 / 6.7% -> 0 with depth 0 (but edge-on 46%). FOLD_PAST 0.15:
  1.4 / 2.4%; FOLD_PAST 0.15 + depth 1.2 mm: 0 / 0, edge-on 35 / 29% (was 25 / 24). SOCK_SMOOTH, WRAP_TEETH: no
  effect on the corners. SMILE_LIFT 0 halves edge-on but flattens the smile (not taken).
  SMILE UPPER LIP (found in the ID image): a 1 mm band of BACK faces along the upper inner lip over the incisors, 3.6%
  of the smile's opening = ROLL_TUCK pushing the roll so far behind the lip edge it flips. ROLL_TUCK_SLACK 0.3 -> 0.8
  mm: 0 back faces, but the inner lip shows face-on 7.7 -> 20.6% of the opening, teeth 85 -> 73%, corners edge-on
  50 / 40%. TAKEN (a flipped sliver renders dark; wet inner lip is what a smile shows), the review decides.
- v40 = these defaults (commit 2f2b3609), chain_v40.sh: export (+ dump fast/v40dump.pkl), mh/v40.txt, lip gate,
  x40 (shots_expr8) on NICO-TOP, then review/expr_r22. tests/test_face_shapes.py: all ok on r24 defaults.
- x38 JUDGED (review/expr_r20_c = v38c SOCK_SMOOTH 40, 18 MAJOR lines; _d = v38d SOCK_SMOOTH 0, 23): d's jaw walls
  read as crumpled red tissue instead of c's dark grey slabs (better), but d's smile is WORSE (lower lip cuts the upper
  teeth at uneven heights, "teeth look broken", lower lip sags; jaw "stretches into a V"). Rule (walls better AND smile
  no worse) -> SOCK_SMOOTH STAYS 40 (v40 has 40). Both reviews: tongue "missing" (the open mouth's floor reads as a flat
  red wall, the tongue's colour = the walls'), corners torn (v40 addresses: fast-path back faces 0), smile cheeks / folds
  too weak, lower teeth small and separated by a red gap in smileteeth, blue-grey patches on the upper inner lip in
  smile / smileteeth (v40's ROLL_TUCK_SLACK: the flipped roll). OTHER STAGES: hair cards, nostril rings, likeness.
- v40 export = fast-path numbers exactly (mh/v40.txt): jaw 0.79/0.96/0.71, smile / smileteeth back faces 0, lip gate
  2.50% (PASS < 4.5). Watch: jaw upper-edge 1-mm jumps > 0.5 mm 4 -> 9 (the arch: notches?).

## Handover 2026-10-15 r24 (assembly agent, tool-call limit)
- Branch worktree-agent-ad0815704f43e0e00, merged origin/main (1d64e88c), committed, not pushed.
- IN FLIGHT on NICO-TOP: x39 (v39, -> review/expr_r21 via chain_x39.sh) and x40 (v40 = r24 defaults, -> review/expr_r22
  via chain_x40.sh, launched by chain_v40.sh). Check with /mnt/data/hifipushie/bin/offload status; .DONE / .ERROR files.
- expr_r21 JUDGED (v39, 15 MAJOR lines vs v38c's 18): neutral / blink / eye close-ups: NO MAJOR -> eyes AO off + texel
  density 4 KEPT. Tongue: now brown-pink and fills the lower opening, but still "no tongue ... one flat brown-red plane"
  (same MAJOR, not a regression) -> colour KEPT; the cause is shape / shading: it reads as a front-facing panel with
  no tip behind the lower teeth and no curved top (next: tongue tip / dorsum curve, measured on the jaw crop). Still
  MAJOR in v39: torn jaw corners + notch at 11 o'clock on the upper lip, dark slab walls, smile without cheek raise /
  lower-lid lift (both smiles).
- NEXT: (1) DONE above. (2) expr_r22 vs expr_r20_c: jaw top (arched?), corners (torn?), smile upper lip (blue-grey gone,
  inner lip face-on 21% acceptable?); revert any row that got worse (fast path: shapesfast.py on fast/v40dump.pkl).
  (3) OPEN, measured: jaw aspect 1.15 vs 1.23 (only GNM_OPEN moves it; 20.5 cost lower teeth); the tongue reads
  as a wall (colour + top depth 0.43 of the opening, reference higher?); smileteeth lower teeth / red gap; smile
  cheek raise / folds; left sclera seen-from-front darker and blotchier than the right (L 49 vs 68).
- TOOLS: fast path = HP_SHAPES_DUMP export once, then spikes/game_ready/shapesfast.py (~1 min a try).

## r25 (assembly agent, 2026-10-15)
- expr_r22 (v40) JUDGED row by row against expr_r20_c and expr_r21 (stacked crops, reference | result, read before the
  review text). The MAJOR count went 15 -> 20, but r22's reviewer split each close-up into its own row, so the count
  doesn't compare. By row:
  - Neutral: same in all three (seam band, blue-grey fleck). Not a v40 change.
  - Jaw (JAW_ARCH 0.9 pow 3, lifts .26/.16, CORNER_OUT .11): reads the same as r21 (tall O, everted ring, torn
    corners, dark side slabs, flat tongue). The 11 o'clock notch MAJOR from r20_c / r21 is gone from r22. Upper teeth
    seen 262 -> 294 mm^2. KEPT, although the upper-edge 1-mm jumps measure 4 -> 9.
  - Smile and smileteeth (FOLD_PAST 0.15 + depth 1.2, ROLL_TUCK_SLACK 0.8): the navy / blue-grey slabs on the upper
    inner lip (a MAJOR in both r20_c and r21) are GONE. The cost is a ragged red inner rim, and the lower lip edge
    crossing the upper teeth (smile teeth seen 85 -> 73%). The corners are still torn (a MAJOR in every round).
    KEPT: no row is worse overall. Corner grazing 40-50% and the wet inner lip 21% stand as the next faults there.
- (6) LIKENESS GEOMETRY = tp_k19: PASS. spikes/game_ready/k19cmp.py compares the v40 GLB "head" mesh with base.head_of
  on tp_k19's own spec, both in Blender axes and metres. The base / head spec is byte-identical (ga_tess differs only in
  export settings, skin paint and hair). Export head to k19 surface: skull back p95 0.11 mm, brow p95 0.22, cheeks p95
  0.35, nose front p95 0.37, eyes front p95 0.66, front lips median 0.31 / p95 0.85 mm (max 8 at the sealed seam).
  Only interior faces (mouth sock, nostrils) are further out. Face widths at brow / eyes / cheekbone / mouth / jaw:
  149.9 / 157.4 / 145.4 / 119.3 / 88.6 mm, both meshes within 0.2 mm. So "face wider, nose broader" is NOT an
  export geometry difference: it's tp_k19's own shape (or shading / paint). It goes to the coordinator; tp_k19 is
  approved and only Joe reopens it.
- (5) LEFT SCLERA: it's the TEXTURE, not lighting. eyealb.py reads the baked basecolor (eyes AO off since v39): left
  sRGB [132 114 105] L 49 CoV 0.52 vs right [180 163 155] L 68 CoV 0.29. skin.eyes.sclera is #e9e3dc (233 227 220),
  so both eyes bake far darker than the paint. The asymmetry grew from v39 (L 58.5 vs 67) to v40 with texel density 4.
  eyeview.py (each eye's albedo seen from the front, right mirrored) shows pink-brown skin-coloured patches baked onto
  both eyeballs in DIFFERENT places. Suspect the high -> low colour bake picking up the lids / canthus paint, or GNM's
  eye texture. NEXT: bake the eyes' colour pass alone and compare it with the paint evaluated per vertex.
- (2) TONGUE as SHAPE: GNM HAS tongue shape controls (expr_tongue: tongue_mean, 000..030; spikes/game_ready/tonguectl.py
  tabulates them per unit in mm, GNM frame +y up / +z forward):
  - 000: tip out 7.9, down 2.2.
  - mean: tip up 5.7, bow 1.1.
  - 001: tip up 2.5, bow 0.3.
  - 002: tip up 1.9, bow 0.8.
  - 003 and later: under 0.5.
  New: faceshapes.JAW_TONGUE = (tip down, tip back, bow) m, a min-norm solve over GNM's leading tongue components
  (Face._tongue_shape, like tongueOut), added in jawOpen. DEFAULT 0 (off). Fast path (fast/sweep6.sh, s6_*):
  - t0 (off): tongue 0.335 of the opening, a flat pale panel.
  - t1 (4 mm down, 3 mm bow): a curved dorsum in the ID pass, tip down behind the lower row. But the tongue's visible
    albedo goes DARK (sRGB 44 29 27; tongue 0.17 of the opening). The tongue texture darkens from 42 mm back
    (tonguealb: 158 -> 50), and the new shape turns that back third toward the camera.
  - t2 (plus TONGUE_DROP 2 mm): 66 46 43.
  So the shape works, but the colour ramp blocks it. NEXT: start the tongue albedo's dark ramp further back (or key it
  to depth from the lips, not length), then JAW_TONGUE 0.004,0,0.003, TONGUE_DROP 0.002, and measure tongue share /
  colour / top.
- NOT DONE this session: (3) smile cheek raise / lower-lid lift measured on the reference, (4) smileteeth lower-teeth
  red gap cause. No export this round: nothing new is on by default, so v40 stays the current export.
- STATE: v40 = current, judged and kept. JAW_TONGUE is in the code, off. NEXT: tongue albedo ramp -> JAW_TONGUE on
  (fast path) -> (4) -> (3) -> export v41 (lip gate < 4.5%) -> one NICO-TOP batch (--stage) -> blind review.

## Handover 2026-10-15 r25 (assembly agent, tool-call limit)
- Worktree agent-ad0815704f43e0e00, committed, not pushed. No jobs in flight. x40 is done, review/expr_r22 is judged
  (above).
- Read "## r25" just above for the results and the NEXT chain. Fast path: fast/v40dump.pkl + shapesfast.py, sweeps in
  fast/sweep6.sh.
- Tools added: spikes/game_ready/k19cmp.py (export head vs an approved head), eyeview.py (both eyes' albedo, mirrored),
  tonguectl.py (GNM tongue controls table).

## r26 (assembly agent, 2026-10-15)
- (1) TONGUE. spikes/game_ready/tonguevis.py (fast path; the tongue's UVs replaced by its REST depth behind the tip on a
  gradient texture) says which part of the tongue the front sees in jawOpen (v40 dump, rest length 69.8 mm):
  | try | tongue share | visible rest depth p5 / p50 / p95 mm | sim. albedo with ramp 40-60 | with 52-68 |
  | off (v40) | 0.335 | 18 / 32.5 / 53 | 151 112 105 | 157 116 110 |
  | JAW_TONGUE 4,0,3 mm (drop 6) | 0.173 | 49 / 58 / 62 | - | - |
  | 4,0,3 drop 2 | 0.252 | 43 / 56 / 62 | - | - |
  | 2,0,3 drop 2 (TAKEN) | 0.291 | 41 / 54 / 62 | 101 70 66 (74% dark) | 148 108 102 (10% dark, the top) |
  | 0,0,3 drop 4 | 0.292 | 43 / 52.5 / 61 | 108 75 71 | 149 110 103 |
  | 2,0,2 drop 4 | 0.313 | 40 / 51 / 61 | 117 83 78 | 151 111 105 |
  The bowed shape turns the front 40 mm down behind the lower row in every variant; what shows is the dorsum 41-62 mm
  back. So TONGUE_BACK 0.04-0.06 -> 0.052-0.068 (only the far top, ~10% of the visible tongue, falls into shadow).
  Defaults now: JAW_TONGUE (0.002, 0, 0.003), TONGUE_DROP 0.006 -> 0.002, TONGUE_BACK (0.052, 0.068). The "tip behind
  the lower teeth" target is not met in rest terms (p5 41 mm): the lit G/R target (0.66) is read on the render.
- (2) SCLERA, cause found (assembly/eyecause.py, uvover.py on the v40 GLB). Not UV overlap: the eyes share texture 4
  with shoes / socks / soles, and no texel overlaps (left and right eyes share none either). Not the bake catching the
  lids: bake_maps renders only the part's own high mesh. It's the PAINT: skin:eye_shade.L/.R (multiply
  [0.6, 0.43, 0.41] x 0.6) takes the max of an upper-lid axis term and {"near": ["base"]}. Paint's near is the SIGNED
  field distance, and the eyeball lies INSIDE the head's field, so near = 1 over the whole ball. The visible sclera
  baked x(0.76, 0.66, 0.65) of the paint: right ratio 0.77 / 0.72 / 0.71 flat at every distance from the lids. That is
  the pink-brown cast. The left eye also shows sclera 3-12 mm above its centre (104 of 284 samples, ratio 0.32; the
  right eye has 2). Its lids sit higher there (tp_k19 geometry, not ours), so the height-keyed shadow lands on it.
  FIX: paint near "side": "both" = UNSIGNED distance (paint._near_mask and paintnodes._distance; documented in paint's
  docstring). eye_shade keys both terms to it: the lid band (within 0.02 r, soft 0.09 r), and the upper shadow x
  near-wide (0.04 r, 0.16 r). Predicted with the mesh distance: right 0.94 / 0.98 / 0.98 (sRGB 220 222 216), left
  0.70 / 0.70 / 0.68 (163 159 149; its dark upper samples aren't explained by the shade). v41 measures it (eyealb +
  eyecause in mh/v41.txt). OPEN if left stays dark: the eyeview image shows polygonal (per-chart) pink blocks, which
  look like rays reaching the wrong shell of the ball. Next look is the eyes' bake extrusion (asset.scene_maps out_ / in_).
- (4) smileteeth on the fast path (fast/s7_cur_*): the opening is 60% upper teeth, 5% lower, 17% interior face-on. The
  albedo shows a pink interior band between the rows and the lower crowns' tips only, with red on the tops of the upper
  crowns. Cause NOT yet isolated (next: the lower lip's inner roll vs mouthLowerDown 0.4 at jawOpen 0.2, on the fast path).
- (3) smile cheek raise and (5) torn corners / tall-O: NOT DONE this round (tool-call budget).
- FOV (coordinator, main b32d303f set_fov): merged main into this branch (0bf730f3). Every shots_expr8 shot is
  ORTHOGRAPHIC (ortho 0.08-0.26, no fov), so the expression renders' framing is unchanged; the review pairs still line up.
- v41 = r26 defaults: chain_v41.sh (export + fast/v41dump.pkl, mh/v41.txt incl. eyecause, lip gate < 4.5%,
  x41 on NICO-TOP through rge2.sh (GLB jobs: no model stage to pack, so --stage doesn't apply), then chain_x41.sh ->
  blind review review/expr_r23). Launched detached.

## Handover 2026-10-15 r26 (assembly agent, tool-call limit)
- Worktree agent-ad0815704f43e0e00, main merged (0bf730f3), committed, not pushed.
- IN FLIGHT: chain_v41.sh (out/chain_v41.log, mh/v41.txt / .DONE / .ERROR), then x41 on NICO-TOP (offload status x41),
  then review/expr_r23 (.DONE / .ERROR).
- JUDGE expr_r23 against expr_r22 row by row (reference | result crops first). Jaw row: tongue G/R (reference lit
  ~0.66), a curved dorsum instead of a panel, no black band. Eye rows: both scleras near the paint, left = right. Revert
  a change whose row got worse: JAW_TONGUE back to 0 and TONGUE_DROP to 0.006 / TONGUE_BACK to (0.04, 0.06); or eye_shade's
  "side" removed.
- NEXT: (4) the smileteeth red gap (fast path, above), (3) the cheek raise measured on the reference smile, (5) corners
  / tall-O, the left sclera if still dark (bake extrusion).
- v41 EXPORTED (mh/v41.txt): lip gate 2.50% PASS; jaw teeth seen as v40 (upper 294 mm^2, centre crowns 7.8 / 8.6 mm).
  Tongue albedo by rest depth: flat 158 117 110 to 54 mm, then 143 105 98 at 54-60 mm. The ramp moved as intended.
  SCLERA: FAIL, the bake is UNCHANGED (left ratio 0.57 / 0.50 / 0.48, right 0.77 / 0.72 / 0.71, the same as v40 to
  the digit). So the unsigned-near change did not reach the baked eye colour. Either the shade isn't the cause (my
  inference from the code, not measured per layer), or the scene reused a cached dist attribute / material. NEXT, before
  any further eye change: evaluate the eye_shade mask per eye vertex (paint.layer_mask on the scene's points) and
  check the scene cache for the eyes part; then the bake extrusion (per-chart pink blocks). x41 renders carry v40's eyes.

## r27 (assembly agent, 2026-10-15)
- (1) SCLERA, measured (assembly/eyepaint.py, eyedecal.py, eyetexdiff.py, eyevar.py on the v41 GLB):
  - The r26 change DID reach the bake: the eyes' embedded basecolor changed in 108k of 125k eye texels (mean sRGB
    168 143 137 -> 212 195 188, eyetexdiff.py v40 vs v41). eyealb's numbers stayed "identical" because its sclera band
    (6.5-11 mm off a ball-median axis) is a bad measure: on the LEFT eye 133 of its 284 visible samples are IRIS texels
    (r < 1.05 iris radii on the eye picture), on the right 50 of 240. The L 49 / R 68 "asymmetry" was the measure.
  - Classed by where each visible sample lands on the eye picture (eyedecal.py), the true sclera (r 1.05-1.8) baked
    L 195 176 170 / R 201 182 176: both eyes alike, (0.85, 0.79, 0.79) of #e9e3dc. The picture there is 223 213 206.
    Python paint (paint.apply at those points) predicts the bake within 3% (L 200 174 168, R 203 181 174): the fast path.
  - Causes, by layer (eyevar.py): the eye picture's outward warm / pink drift and veins (no shade, no tear: 221 209 202),
    then eye_shade (multiply [0.6, 0.43, 0.41] x 0.6, mask mean 0.53-0.58 on the visible sclera). Not a cached
    attribute, not the bake extrusion: the "pink blocks" are the shade + picture edge.
  - FIX (defaults): skin_swatch.eye_image drift halved (EYE_VERSION 1 in the image key), eye_shade colour
    [0.7, 0.64, 0.62] x 0.25 (was 0.6), eye_tear's near unsigned ("side": "both": it was 1 over the lower ball).
    Fast path: mid sclera L 219 205 199 / R 221 208 202 = (0.94, 0.90, 0.90) / (0.95, 0.92, 0.92) of the paint, L = R
    within 1.5%. The edge band (r 1.8-2.1, corners) stays darker: canthus multiply + veins (193 165 158 / 201 177 170).
    MEASURE from now on with eyedecal.py, not eyealb's band. Not exported yet (goes into v42).
- (3) SMILETEETH GAP, isolated on the fast path (fast/sweep7.sh, s7b_*; mouthhits.py now takes SH_OVR = pose weights
  as JSON). Reference (expr_r22 pair 9): the lower lip hugs just under the upper incisor edges, only the lower tips
  show, opening aspect ~4.2. The pink band is the mouth interior seen between the rows; its cause is the TEST POSE's
  mouthLowerDown 0.4 (and jawOpen 0.2), not a broken shape:
  | smileteeth weights | opening mm^2 | aspect | teeth | lower | tongue | interior |
  | jaw .2, lowerDown .4 (shots_expr8) | 888 | 3.65 | 0.60 | 0.050 | 0.119 | 0.166 |
  | jaw .2, lowerDown .2 | 802 | 3.99 | 0.66 | 0.031 | 0.089 | 0.168 |
  | jaw .2, lowerDown 0 (TAKEN) | 715 | 4.37 | 0.73 | 0.014 | 0.047 | 0.162 |
  | jaw .1, lowerDown 0 | 506 | 5.06 | 0.82 | 0.000 | 0.002 | 0.133 (15% width 0.19: corners shut) |
  | jaw .1, lowerDown .2 | 582 | 4.84 | 0.79 | 0.001 | 0.004 | 0.154 |
  jaw .2 / lowerDown 0 matches the reference read (lip under the upper edges, lower tips peeking, no band). Its
  remaining "interior" share (0.16) is the dark buccal corners, as in the reference. shots_expr9.json = shots_expr8
  with mouthLowerDown dropped from smileteeth / mouth_smileteeth. This is a POSE choice for the review shot (what an
  animator keys for this expression), not an asset change; the asset's mouthLowerDown is unchanged.
  Still open in that row: red gum streaks between the upper crowns (the teeth albedo's gingiva, uncovered by
  mouthUpperUp 0.6), in every variant.
- v42 = r27 defaults (sclera) exported by chain_v42.sh (detached): mh/v42.txt incl. eyedecal.py, lip gate < 4.5%,
  then WAITS for x41 to finish, submits x42 (shots_expr9) and reviews into review/expr_r24.
- (4) SMILE EYES / CORNERS, measured (assembly/lidlift.py: likeness.detect = MediaPipe 478 points; eye corners as the
  fixed line, io = interocular; reference = refs/tess_head_front*.png, ours = x40 front renders):
  | | lower lid up (% io) | eye opening / io, neutral -> pose | mouth corners up vs eye corners (% io) |
  | reference smile | +2.0 | 0.149 -> 0.116 (x0.78) | +12.1 |
  | ours smile | +1.7 | 0.156 -> 0.129 (x0.83) | +20.1 |
  | reference smile with teeth | +1.5 | 0.149 -> 0.136 (x0.91) | +14.1 |
  | ours smileteeth | +1.6 | 0.156 -> 0.127 (x0.81) | +18.8 |
  So the lower-lid lift and the squint MATCH the reference within ~0.5% io. The reviewer's "eyes barely rise" is not
  in the landmarks. Our mouth corners rise 5-8% io MORE than the reference (SMILE_LIFT / the smile prototype amount
  are the candidates; not changed). "No cheek lift / no nasolabial folds" is surface form that landmarks can't see.
  It needs a measured item first (gates rule): e.g. a raking-light or curvature profile across the cheek apex and
  the nasolabial line, reference vs ours. NOT changed this round.
- (5) torn corners, tall-O jaw: NOT started (budget).

## Handover 2026-10-15 r27 (assembly agent, tool-call limit)
- Worktree agent-ad0815704f43e0e00, committed, not pushed.
- IN FLIGHT (detached): x41 (queued on NICO-TOP, 20+ min) -> chain_x41.sh -> review/expr_r23 (.DONE / .ERROR).
  chain_v42.sh: the v42 export (out/exp_ga_tess_v42.log, mh/v42.txt / .DONE / .ERROR, lip gate < 4.5%), then
  `offload wait x41`, then x42 (shots_expr9) -> chain_x42.sh -> review/expr_r24.
- JUDGE expr_r23 against expr_r22 row by row (the jaw row = the tongue: JAW_TONGUE on, ramp 52-68 mm; revert to
  JAW_TONGUE 0 / TONGUE_DROP 0.006 / TONGUE_BACK (0.04, 0.06) if the jaw row is worse). x41 carries the OLD eyes.
  Then expr_r24 (v42: the sclera fix; smileteeth without mouthLowerDown) against expr_r23.
- SCLERA: measure with eyedecal.py (mh/v42.txt); target mid sclera (r 1.05-1.8) >= ~0.94 of #e9e3dc, L = R within 3%.
  Fast path predicted (0.94, 0.90, 0.90) L / (0.95, 0.92, 0.92) R. G/B stay ~0.9: the picture's veins + remaining drift.
  Going further means less drift / fewer veins in skin_swatch.eye_image (EYE_VERSION).
- NEXT: (a) the cheek/nasolabial measured item (above), then the fix; (b) the mouth corner rise (5-8% io too high);
  (c) the upper crowns' red gum streaks; (d) torn corners, tall-O jaw. Tools: eyepaint / eyedecal / eyevar /
  eyetexdiff / lidlift.py, fast/sweep7.sh (SH_OVR pose weights).

## Round 28 (2026-10-15/16, assembly agent): tongue reverted, smile corners, cheek lift, measured cheek item
- (1) expr_r23 (x41) vs expr_r22, jaw row, judged by look on pair_6 (close-ups, reference | result): r22 showed a pale
  papillae dorsum filling the lower half; r23 (JAW_TONGUE (2, 0, 3) mm + TONGUE_BACK 52-68 mm) sank it to a dark sliver
  behind the lower row, the back a maroon slab. WORSE, so the tongue is reverted: JAW_TONGUE 0, TONGUE_DROP 6 mm,
  TONGUE_BACK (0.04, 0.06). The dark vertical "struts" at the sides are the same in both (an older fault).
- (2) v42 (sclera fix): eyedecal mid sclera (r 1.05-1.8) 219 208 201 / 218 204 197 / 220 207 200 / 220 208 201 =
  (0.94, 0.92, 0.91) of #e9e3dc, L = R within 1%: PASS as predicted. The edge band (1.8-2.1) stays 189-212.
  Lip gate 2.50%. expr_r24 (x42, shots_expr9) by look: the whites read light and equal; smileteeth no longer shows the
  floating lower row or the void (the lower lip hugs the upper edges as in the reference). The reviewer still calls
  smileteeth "hardly different from the smile". Open MAJORs: jaw side struts and no tongue (v42 had r23's tongue),
  torn lip edges and corners, a red inner-lip band above the upper teeth in both smiles, no cheek / fold / lower-lid push.
- (3) MEASURED ITEM for the smile cheek (gates rule): assembly/cheekprof.py. MediaPipe frames in io units. A profile
  across the nasolabial line (perpendicular at 0.4 of nose wing -> corner) and one down through the cheek apex (eye
  centre x, lower lid -> corner height), as smile minus neutral luminance, plus the apex highlight's height below the lid.
  | | fold dip | apex below the lid, neutral -> pose (io) |
  | reference smile | -0.21 | 0.44 -> 0.37 (rises 0.07) |
  | x40 smile | -0.20 | 0.29 -> 0.27 (0.02) |
  | reference smile teeth | -0.33 | 0.44 -> 0.32 (0.12) |
  | x40 smileteeth | -0.26 | 0.29 -> 0.25 (0.04) |
  The fold's luminance dip is about right (smileteeth 20% shallow). The cheek doesn't rise: FAIL by 0.05-0.08 io
  (3-5 mm). Lighting differs between the photo and our shots, so read the deltas, not the absolute levels.
  Fix: faceshapes.CHEEK_LIFT (in _smile_fold). The cheek mass is raised 4 mm, a Gaussian of 12 mm centred 0.4 of the
  way from the lower lid to the mouth corner, pushed out 1 mm, smoothstepped to 0 at the lower lid (the lid lift
  already matches). A 3D proxy (smile3d.py "cheek gain centroid") proved uninformative, so the check is cheekprof on x43.
- (4) CORNERS: faceshapes.SMILE_CORNER_UP (share of the prototype's own corner rise, through the landmark solve) is
  0.6, and SMILE_LIFT goes 2 -> 1 mm. smile3d.py (3D, v41 dump): corner rise 21.6 / 20.3 -> 15.4 / 14.1% io. The
  renders read ~1.5 lower than 3D (x40: 20.1 / 18.8), so we predict ~13.9 / 12.6 against the reference's 12.1 / 14.1.
  Smile and smileteeth rise alike in ours but differ in the reference: one constant can't hit both.
  mouthhits (fast path): 0 back faces; lower-edge jumps 6 -> 1; smile opening 68.5 x 8.8 mm (was 12.2 tall, fill
  0.43 -> 0.59); corner edge-on 0.50 / 0.40 -> 0.53 / 0.58 (left a little worse).
- v43 = all of the above, via chain_v43.sh (detached): export, mh/v43.txt (eyedecal, smile3d), lip gate, x43
  (shots_expr9) -> review/expr_r25 + review/expr_r25_measures.txt (lidlift + cheekprof on the x43 front renders).
- RESULT v43 / x43 / review/expr_r25 (FAIL, 23 MAJOR lines vs 15 in r24; the formats differ). Measures (expr_r25_measures.txt):
  | | corner rise vs eyes (% io) | lower lid up | cheek apex rise (io) | fold dip |
  | reference smile / smileteeth | 12.1 / 14.1 | 2.0 / 1.5 | 0.07 / 0.12 | -0.21 / -0.33 |
  | x40 | 20.1 / 18.8 | 1.7 / 1.6 | 0.02 / 0.04 | -0.20 / -0.26 |
  | x43 (v43) | 16.8 / 15.9 | 1.8 / 2.0 | 0.08 / 0.08 | -0.17 / -0.20 |
  Smile arc (assembly/smilearc.py, corners above the inner lower lip, % io): reference 12.9 / 20.2, x40 18.6 / 26.1,
  x43 14.5 / 20.7. By landmarks x43 is closer on every item, and the cheek apex rise PASSES on the smile (smileteeth
  is 0.04 short). The fold dip got shallower (FAIL). The render offset vs 3D wasn't constant: 3D predicted 13.9 / 12.6.
  BUT by look (mine and the reviewer's, pair_7) the x43 smile reads FLATTER, almost a straight slit with less of
  the crescent. Reviewer: "corners barely rise", "cheeks don't rise". So the landmark checklist is INCOMPLETE (gates
  rule). The missing item is the lower lip's curve: the inner and outer lower-lip contour's sag against the
  corner-to-corner line (MediaPipe inner lower 78 95 88 178 87 14 317 402 318 324 308; outer 61 146 91 181 84 17 314 405
  321 375 291), reference vs ours. The reference's teeth show as a curved crescent; ours have a straight lower edge.
  Keep SMILE_CORNER_UP 0.6 or not ONLY after that item is measured. The jaw row still reads "no tongue" in r25,
  even with the tongue back on r22's constants, so r22's visible dorsum came from something else as well (diff the
  v37 / v41 tongue: tonguealb.py on both GLBs). The tongue revert didn't restore it: FAIL.

## Handover 2026-10-16 r28 (assembly agent, tool-call limit)
- Worktree agent-ad0815704f43e0e00, committed, not pushed. Nothing in flight (x43 done, review/expr_r25 done).
- Defaults now: tongue at r22's values; SMILE_CORNER_UP 0.6, SMILE_LIFT 1 mm, CHEEK_LIFT (4, 12, 1 mm, 0.4) = v43.
- Tools (assembly/): cheekprof.py (cheek / fold profiles), smile3d.py (3D corner rise from a dump, fast), smilearc.py,
  lidlift.py, fast/sweep8.sh / sweep9.sh.
- NEXT: (a) the lower-lip curve item (above) on the reference, x40 and x43, then decide SMILE_CORNER_UP. The likely
  fix is the mouth middle / lower lip dropping in the smile, not the corners rising. (b) The fold depth
  (SMILE_FOLD[0] 1.2 mm -> deeper, but watch the corner back faces: r24). (c) Smileteeth's cheek apex is 0.04 io short.
  (d) The jaw tongue: why r22 showed a dorsum and r23 / r25 don't. (e) The red inner-lip band above the upper teeth,
  torn lip edges, grey corner shapes, the jaw side struts. Then one export, ONE NICO-TOP batch, the blind review.

## Round 29 (2026-10-16, assembly agent): the smile's missing item measured
- (1) LOWER-LIP CURVE item (assembly/lipcurve.py: MediaPipe contours' sag below the corner-to-corner line, % io):
  | | inner lower mid / bow | outer lower mid / bow | inner upper mid |
  | reference smile | +12.6 / +2.6 | +26.7 / +4.9 | -0.6 |
  | x40 smile | +18.5 / +4.3 | +35.6 / +6.2 | +3.3 |
  | x43 smile | +14.5 / +3.4 | +32.4 / +5.6 | +0.6 |
  | reference smileteeth | +19.7 / +3.4 | +32.5 / +5.3 | -2.0 |
  | x43 smileteeth | +20.6 / +3.7 | +36.3 / +5.6 | -3.5 |
  Our lower lip already sags MORE than the reference's: the "drop the lower lip's middle" hypothesis is WRONG. The
  item doesn't explain the slit read. Looked at mouth crops (reference | x40 | x43): the reference's visible teeth top
  ARCHES UP in the middle and the lips meet the teeth with no red; ours has a straight top under a red inner-lip band.
- (1b) The item that does measure it (assembly/teethshape.py, photo / renders, % io; + = below the corner line):
  | | teeth top at 0.3 / 0.5 / 0.7 | red band above teeth at mid | upper / lower vermilion |
  | reference smile | -0.7 / -0.7 / +3.1 | 0 | 10.3 / 14.2 |
  | x40 smile | +6.9 / +7.4 / +6.9 | 4.8 | 11.1 / 17.1 |
  | x43 smile | +3.1 / +4.4 / +3.9 | 4.0 | 11.6 / 17.9 |
  | reference smileteeth | -1.9 / +0.1 / +1.4 | 2.0 | 8.8 / 13.0 |
  | x43 smileteeth | -0.2 / +2.1 / +1.6 | 5.8 | 11.4 / 15.7 |
  So the upper lip hangs over the teeth in the middle (top sags 4.4% io below the line where the reference's is
  0.7 above), and its wet inner side shows as the red band (r25 MAJOR "red inner-lip band above the upper teeth":
  same cause). The lower vermilion is 26% too thick. DECISION: SMILE_CORNER_UP 0.6 KEPT (corners 16.8 / 15.9 vs
  12.1 / 14.1: x43 moved toward the reference; the flat read is the upper lip, not the corners).
- Fix: faceshapes.SMILE_UPPER_LIFT (amount, arch, power): the smile lifts the upper vermilion (jawOpen's lip-lift
  helper, `_jaw_lip_lift` now takes amount / arch / power) by `amount` at the middle, x (1 - arch u^power) to 0 at the
  corners. Fast-path measure: assembly/crescent.py on the shapesfast ID pass (opening top, teeth top / bottom, the
  band between them at the middle, mm). v43 fast baseline (s9_new): opening top flat (bow +0.12 mm), band 1.0 mm.
  Sweep fast/sweep10.sh (0 / 3 / 5 mm, power 2 / 1.3).
- (1c) SMILE_UPPER_LIFT fast sweep (sweep10, crescent.py on the ID pass, mm, smile / smileteeth):
  | lift | opening top at mid | teeth top at mid | band above teeth at mid |
  | 0 (v43) | +0.9 / -3.6 | +1.9 / -1.9 | 1.0 / 1.8 |
  | 3 mm, power 2 | -0.7 / -5.2 | +1.1 / -2.0 | 1.8 / 3.2 |
  | 5 mm, power 2 | -2.4 / -7.1 | +0.8 / -2.6 | 3.2 / 4.5 |
  | 5 mm, power 1.3 | -2.2 / -6.8 | +0.8 / -2.2 | 3.0 / 4.5 |
  Lifting the vermilion raises the OPENING but not the TEETH: the inner lip stays on the incisors' face and shows as
  a taller band (the r25 MAJOR, worse). So the lift alone is wrong; sweep13 tests it with the smile out of the teeth
  wrap and with a tighter roll tuck.
- (4) TONGUE: x43's jaw close-up is pixel-identical to x40's (mean |diff| 0.0002; full jaw front 0.04), and
  review/expr_r22/pair_6 = expr_r25/pair_6. expr_r22's review ALSO said "There's no tongue ... flat dark-maroon wall".
  So r28's premise ("r22 showed a dorsum") was wrong: the revert DID restore r22 exactly, and r22's tongue failed too.
  Measured item (pair_6, a column down the middle, luminance): the reference tongue ramps 30 at its top -> 110 at the
  lower teeth (a lit dome, G/R 0.64); ours sits on a 45 plateau for two thirds and reaches 81 only at the front (G/R
  0.63: the colour is right, the SHADING is flat: its top faces up, out of the light). Albedo by depth is uniform 158 117
  110 to 42 mm (tonguealb). tonguefacing.py (fast path: the visible tongue's -n.y), sweep11:
  | | tongue share of opening | facing p25 / 50 / 75 |
  | v43 (drop 6, sink 6) | 0.310 | 0.43 / 0.50 / 0.55 |
  | drop 3 | 0.350 | 0.46 / 0.53 / 0.57 |
  | drop 0 | 0.390 | 0.48 / 0.55 / 0.59 |
  | sink 3 | 0.359 | 0.43 / 0.50 / 0.55 |
  | drop 0, sink 3 (TAKEN) | 0.410 | 0.50 / 0.57 / 0.60 |
- (5) INNER_LIP_COLOR [0.38, 0.11, 0.11] -> [0.38, 0.148, 0.11]: the band over the smile's upper teeth rendered
  (175, 101, 103) G/R 0.58 (magenta) against our vermilion's 0.62; the reference's wet inner lip (jaw open) is the
  vermilion's own hue (G/R 0.66 vs 0.65) and a little lighter. Above that band ours has a near-black line (64, 21, 24)
  2-5 mm tall: the lip's underside edge-on (the "torn edge"); the reference has none.
- (1d) sweep13 (lift 3 mm; mm, smile / smileteeth): out of the teeth wrap (nw3) = the same as wrapped (the wrap isn't
  what holds the roll); + ROLL_TUCK_SLACK 0.8 -> 0.3 mm (tk3): teeth top at mid +0.8 / -2.5 (v43 +1.9 / -1.9), teeth
  shown 7.0 / 14.8 (v43 6.0 / 14.0; reference smile ~6.8), band 1.5 / 2.8 (v43 1.0 / 1.8), torn 0 / 0, corner
  edge-on 0.45 / 0.55 (v43 0.54 / 0.58). TAKEN for v44: SMILE_UPPER_LIFT (3 mm, 1, 2) + ROLL_TUCK_SLACK 0.3 mm. The teeth
  top still doesn't ARCH (bow -0.25 mm vs the reference's ~ -1.2): open. The band grows 0.5 / 1.0 mm; with the inner
  lip recoloured to the vermilion's hue it should read as lip down to the teeth (v44 measures it: teethshape).
- (2) FOLD depth, sweep12 (with lift 3 mm): corner back faces (6 mm zone, R / L): 1.8 mm 0.8 / 2.4%, 2.4 mm 1.3 /
  7.6%, 2.4 mm wide 7.2 / 12.4% (1.2 mm: 0.4 / 0). Deepening tears the corners again: NOT taken. Next approach: the
  crease faded before the corner (SMILE_FOLD_PAST 0 or negative) so the depth stays off the corner, then deepen.
- (3) smileteeth cheek gap: not attempted this round (budget).
- v44 = chain_v44.sh (export + measures + lip gate -> x44 shots_expr9 on NICO-TOP -> review/expr_r26 + measures:
  lidlift, cheekprof, teethshape, lipcurve, tongue column). Launched detached.
- v44 export done. Lip gate 2.50% (PASS). mh/v44.txt, jaw: tongue 0.445 of the opening (v43 0.335), its top 0.24 of
  the opening below the top (v43 0.43; the reference is about 0.25). Smile and smileteeth equal the fast path's tk3,
  0 torn. x44 (shots_expr9) is RUNNING on NICO-TOP (client pid 850001). chain_x44 then writes review/expr_r26 and
  review/expr_r26_measures.txt (lidlift, cheekprof, teethshape, lipcurve, the tongue column; MEASURED at its end).

## Handover 2026-10-16 r29 (assembly agent, tool-call limit)
- Worktree agent-ad0815704f43e0e00, committed, not pushed. IN FLIGHT: x44 on NICO-TOP -> review/expr_r26 (chain_v44.sh,
  detached; `offload wait x44`; review/expr_r26.ERROR on failure).
- r29 findings: (a) the smile's lower lip already sags MORE than the reference's (lipcurve). The slit read is the
  upper lip covering the incisors' top: its inner roll lies on the teeth as a red band (teethshape). (b) r22's tongue
  = r25's, pixel for pixel, and both reviews said "no tongue". It is a shading fault (a flat top facing up), not
  colour or position.
- v44 defaults: SMILE_UPPER_LIFT (3 mm, 1, 2), ROLL_TUCK_SLACK 0.3 mm, TONGUE_DROP 0, TONGUE_SINK 3 mm,
  INNER_LIP_COLOR [0.38, 0.148, 0.11]. SMILE_CORNER_UP 0.6 kept.
- NEXT: (1) judge expr_r26, pairs first (smile rows: does it still read as a slit? jaw: tongue). Then the measures
  against the r29 tables. Revert any row that got worse (tongue -> sink 6 / drop 6; band -> slack 0.8, lift 0).
  (2) The teeth top doesn't ARCH yet (bow -0.25 vs about -1.2 mm). Try a lift with a sharper taper or one centred on
  the inner roll only, measured with crescent.py. (3) Fold depth: fade the crease before the corner
  (SMILE_FOLD_PAST <= 0) and then deepen it. sweep12 shows 1.8+ mm tears the corners as things stand. (4) The
  smileteeth cheek is 0.04 io short. (5) The near-black line under the upper lip's edge (the "torn edge": the lip's
  underside edge-on), the jaw's side struts, and the grey corners.

## Round 30 (2026-10-16, assembly agent, fresh session)
- faceshapes.SMILE_FOLD_CORNER (m, default 0 = off): the nasolabial crease and its cheek push smoothstep to 0 within
  this radius of the mouth corner, so the crease can be deepened without tearing the corner. fast/sweep14.sh (v44 dump):
  radius 6 / 9 mm x depth 1.2 / 1.8 / 2.4 / 3.0 mm, corner back faces (mouthhits).
- Fast-path ID check of the "band" (s13_tk3 = v44): at the smile's middle column the 1.25 mm band above the teeth is
  head faces hidden in the neutral (the upper vermilion's underside, pressed on the lower lip at rest) with the
  VERMILION's albedo (166, 93, 93 vs 165, 93, 93 above), then one edge-on pixel (the dark line), then teeth. So the
  band is the upper lip's own lower vermilion rolled forward over the teeth, not the inner-lip material.
- expr_r26 (x44 = v44) JUDGED, pairs first. My look: smile (pair_7) shows more teeth than x43 but the upper lip's edge is
  still a ragged red fringe over the teeth with dark corner gaps; smileteeth (pair_8) now shows PINK GUM SPIKES between
  the upper incisors (new) under the same fringe; jaw (pair_6): a lit tongue front is visible, but the dark vertical
  struts down both sides remain the loudest fault. Review FAIL (MAJORs: torn lip edges / corners, gum spikes, flat
  lip line, cheeks, jaw struts, "no tongue", smileteeth ~ smile, neutral lip shape + a fleck in the seam).
  Measures, x43 -> x44 (reference):
  | row | x43 | x44 | reference | |
  | corner rise smile / st (% io) | 16.8 / 15.9 | 15.8 / 15.9 | 12.1 / 14.1 | better (smile) |
  | cheek apex rise smile / st (io) | 0.08 / 0.08 | 0.08 / 0.09 | 0.07 / 0.12 | same |
  | fold dip smile / st | -0.17 / -0.20 | -0.157 / -0.164 | -0.21 / -0.33 | WORSE |
  | teeth top at mid smile / st (% io) | +4.4 / +2.1 | +2.4 / +1.6 | -0.7 / +0.1 | better |
  | red band above teeth at mid smile / st | 4.0 / 5.8 | 4.0 / 7.5 | 0 / 2.0 | st WORSE |
  | inner upper lip at mid smile / st | +0.6 / -3.5 | -1.2 / -5.3 | -0.6 / -2.0 | st WORSE (lip too high: gums) |
  | upper / lower vermilion smile (% io) | 11.6 / 17.9 | 13.4 / 18.6 | 10.3 / 14.2 | worse |
  | outer lower lip sag smile | +32.4 | +33.7 | +26.7 | worse |
  | tongue column | 45 plateau 2/3, 81 at front | 44 plateau ~1/3, ramps to 170 | 30 -> 110 ramp | better, kept |
  Decision: the tongue change is kept (more lit dorsum, closer ramp). SMILE_UPPER_LIFT 3 mm: the smile improved but
  smileteeth got worse (lip 3.3% io too high, gums show), so it drops to 1.5 mm and the teeth top goes to the
  edge lift (sweep15), which moves the lowest point of the lip (contact ring + rolls) rather than the vermilion.
- sweep14 (fold, v44 dump, mouthhits): with SMILE_FOLD_CORNER 6 or 9 mm every depth 1.2 / 1.8 / 2.4 / 3.0 mm gives
  0 corner back faces (r29 without it: 1.8 mm tore 0.8 / 2.4%, 2.4 mm 1.3 / 7.6%); corner edge-on falls with depth.
- sweep15 (SMILE_EDGE_LIFT, lift 3 mm; crescent + mouthhits, smile): 1.5 mm: interior face-on (the band) 0.27 ->
  0.22, teeth 0.63 -> 0.69, teeth top at 0.4 / 0.6 +0.5 / +0.6 -> 0.0 / +0.3 mm, 0 torn; 2.5 mm: band 0.14, teeth 0.73,
  but 2.1% back faces (torn); power 4 or 4 rings: the same tear. The middle station never moves (+0.8 mm): it falls
  in the gap between the central incisors (the gum papilla), so crescent's mid station reads the papilla; use 0.4 / 0.6.
- Combined (s16): lift 1.5 + edge 1.5 tears (3.7%): the edge passes the vermilion; lift 1.5 + edge 1.0 x 4 rings also
  (3.1%). TAKEN for v45 (s16_A): lift 3 + edge 1.5 + fold 2.4 mm at corner 9 mm: 0 torn both smiles, smile band
  0.27 -> 0.22, teeth top -0.8..-1.5 mm (above the corner line; the deeper fold lowered the corners' line ~1 mm).
  RISK (measured, not fixed): smileteeth's opening top goes -5.2 -> -7.3 mm (x44's inner upper lip was already 3.3% io
  too high there, the gum spikes): v45 will likely show more gum in smileteeth. Next: a smileteeth-only lowering
  (the smile's lifts scaled down when jawOpen / mouthUpperUp also lift), not done this round.
- v45 = chain_v45.sh (export + mh/v45 + lip gate -> x45 shots_expr9 on NICO-TOP -> review/expr_r27 + the same
  measures as r26). Launched detached.
- (5) JAW SIDE STRUTS measured (not fixed; for r31). mh/v44_jaw_id: the struts are the mouth sock's side walls seen
  EDGE-ON (blue class) running from the upper to the lower teeth along the tongue's sides, near-black albedo, with the
  inner cheeks outside them face-on and lit red (the "torn red flaps"). Luminance across the opening at mid height
  (pair_6, every 10 px): reference lip 134 -> sides 13-21 over ~15% of the width each side -> tongue / back 37-47;
  ours lip 107 -> inner cheek 56 / 87 (lit) -> 33 -> flat 44-52 -> a 1-sample black line (11) -> inner cheek 33-81 (lit).
  So the item is "side shadow": target the inner cheeks at ~15-20 over ~15% of the width with no sharp line. The
  fix is the sock's lateral walls darkened by depth / occlusion (or the walls pushed out behind the cheeks so the
  tongue meets them), measured with this row profile.
- (4) smileteeth cheek gap: not attempted (budget). (5) the dark line under the upper lip's edge and grey corners:
  not measured this round beyond the fast path's edge-on share (corner edge-on 0.45 / 0.55 -> ~0.40 / 0.49 in s16_A).
- RESULT v45 / x45 / review/expr_r27: FAIL (MAJORs as r26: torn inner lip edges and black corner holes, gum band and
  pink triangles in smileteeth, flat thick upper lip / heavy lower lip, "no tongue", jaw side strips, no cheek raise).
  By look pair_7 is nearly the same as x44. Measures, x44 -> x45 (reference):
  | row | x44 | x45 | reference | |
  | fold dip smile / st | -0.157 / -0.164 | -0.196 / -0.200 | -0.21 / -0.33 | better: KEPT (smile ~ pass, st short) |
  | red band at 0.4 / 0.6, smile (% io) | 2.3 / 2.8 | 3.0 / 3.5 | 0 / 0 | WORSE: edge lift REVERTED |
  | teeth top at 0.4 / 0.6, smile | +0.6 / +1.1 | +0.8 / +1.4 | -0.9 / +0.6 | worse |
  | upper / lower vermilion smile | 13.4 / 18.6 | 12.5 / 18.3 | 10.3 / 14.2 | a little better |
  | corner rise smile / st | 15.8 / 15.9 | 16.7 / 16.3 | 12.1 / 14.1 | worse (fold?) |
  The fast path's "interior face-on" share predicted the band would shrink; the render's red band grew. The fast
  path's band is the wrong proxy for what teethshape measures (red pixels inside MediaPipe's inner contour).

## Handover 2026-10-16 r30 (assembly agent, tool-call limit)
- Worktree agent-ad0815704f43e0e00, committed, not pushed. Nothing in flight. v45 exported (lip gate 2.50%), x45 rendered,
  review/expr_r27 + expr_r27_measures.txt written. Code defaults now = v45 minus SMILE_EDGE_LIFT (reverted to 0):
  SMILE_FOLD 2.4 mm + SMILE_FOLD_CORNER 9 mm kept.
- NEXT: (1) re-export (v46) is needed for the edge-lift revert to reach an asset; fold it into the next round's export.
  (2) The red band / teeth top needs a fast-path proxy that matches teethshape: render the fast path's ALBEDO crop
  through teethshape's red/white classes (or MediaPipe on the alb image) before sweeping again; the face-on share
  misled. (3) smileteeth: the upper lip is too high (in_up -5.3 vs -2.0% io, gum band + papillae): scale the smile's
  lifts down when jawOpen / mouthUpperUp also lift, measured with teethshape in_up. (4) jaw side shadow (row profile
  in r30 notes: target ~15-20 luminance over ~15% width each side, no sharp line). (5) corner rise rose 0.9% io with
  the deeper fold: check whether the fold's cheek push lifts the corner (SMILE_FOLD[2]). (6) smileteeth cheek gap 0.04 io.

## Round 31 (2026-10-16, assembly agent, fresh session): proxy calibration first
- PROXY (scratch, /mnt/data/hifipushie/assembly): flatcam.py = a flat pass of the face at the REVIEW camera (shots_expr9:
  ortho 0.26 m / 700 px; centre from MediaPipe landmarks on v45 neutral, cal/centre.json), numpy z-buffer, 2x2
  supersampled, head / teeth / lower teeth / tongue / eyes / body / lashes (alpha-tested). Shading FITTED to the renders
  (calib.py rasters, calib2.py fit, cal2/shade2.json): per channel, out = ao^k (alb x SH-1(n) + alb x per-part gain
  (teeth, lower teeth, tongue) + sheen x (1-|n.v|)^5), k 0.5, screen-space occlusion; mouth-box rms 18.8 / 255.
  The SAME teethshape / lipcurve / lidlift run on it (calcmp.py; each image measured at 5 sub-pixel / 1% scale jitters
  and averaged). fastproxy.py = the proxy from a dump (shapesfast's apply) for sweeps.
- NOISE FLOOR first (cal/noise.txt: x45 itself under 4 jitters): teethshape's red band at 0.4-0.6 sigma ~0.3 (smile) /
  ~0.6 (st) % io, teeth top 0.1 / 0.6, in_up 0.1 / 0.2, corner rise 0.1 / 0.3. So the r30 "red band grew 2.3/2.8 ->
  3.0/3.5" (x44 -> x45) was AT the noise floor of one measurement: not evidence the edge lift hurt. Measures are now
  jitter-averaged.
- CALIBRATION (cal2/cmp3_jit.txt), render / proxy, % io, x43 | x44 | x45; the proxy carries a constant per-row bias
  (MediaPipe places the inner lip ~2-3% io differently on the flat image); after removing the mean bias the residuals:
  | row | x43 | x44 | x45 | bias | residuals | tol 0.5 |
  | smile red band .4-.6 | 3.3/3.7 | 3.2/3.9 | 3.7/3.9 | +0.47 | 0.0 +0.2 -0.3 | PASS |
  | st red band .4-.6 | 3.6/2.5 | 4.1/2.2 | 4.4/2.2 | -1.73 | +0.6 -0.2 -0.5 | FAIL (misses st's rise) |
  | smile teeth top .4/.6 | 3.5/0.8 | 1.3/-0.9 | 1.5/-1.3 | -2.53 | -0.2 +0.4 -0.3 | PASS |
  | st teeth top | -1.4/-5.0 | -3.2/-6.2 | -3.1/-6.5 | -3.33 | -0.2 +0.2 -0.1 | PASS |
  | smile in_up mid | 0.8/-2.2 | -1.0/-4.4 | -1.3/-4.7 | -3.30 | +0.3 -0.2 -0.1 | PASS |
  | st in_up mid | -3.4/-6.7 | -5.2/-7.8 | -5.6/-7.9 | -2.77 | -0.5 +0.2 +0.4 | PASS (edge) |
  | smile corner rise | 16.5/14.0 | 16.2/14.3 | 17.1/14.2 | -2.47 | 0.0 +0.6 -0.5 | FAIL |
  | st corner rise | 16.0/12.4 | 15.7/12.6 | 16.3/12.8 | -3.37 | -0.2 +0.3 0.0 | PASS |
  | smile / st lips up | 11.5/13.0 .. | | | +1.8 / +2.7 | +-0.5 / +-0.5 | edge |
  VALIDATED for tuning: smile red band, teeth top (both), in_up (both), st corner rise. NOT validated: st red band,
  smile corner rise, opening height: judged in the render only. (Before the per-channel / sheen fit and jitter
  averaging the proxy failed most rows: cal/cmp_r1.txt, cal2/cmp.txt.)
- (3) ID TRACES at the review cameras (idtrace.py face shots, idclose.py mouth close-ups; cal2/idtrace*.txt, idclose.txt):
  * "black corner holes" (mouth_smile close-up): the darkest pixels in the opening (lum < 35) are 59% TEETH (the back
    teeth in shadow) and 41% head seen EDGE-ON; the outer fifth of the opening each side is ~1/3 head (inner rolls /
    sock face-on lum ~80, edge-on lum 72-77) beside teeth at 79-139. smileteeth: 1/3 of its dark pixels are skin seen in
    the neutral (lip faces turned in). No mesh holes (no 'nothing' hits). So the corners are the mouth's interior
    skin (rolls + sock walls, much of it edge-on) filling the opening past the dental arch, plus the shadowed premolars.
  * "no tongue" (jaw): the tongue IS the first hit over 5181 px, albedo (157, 117, 110), but its dorsum faces UP (n.z
    median 0.80, toward the camera only 0.57) under occlusion 0.59: 3921 px render at lum ~51, a flat plateau; only the
    front 86 px (facing the camera > 0.8) are lit (147). The reference's tongue is a ramp 30 -> 110. Cause = the flat,
    upward-facing dorsum (one normal) in the palate's shadow, not colour or position.
- (2) sweep17 (fast/sweep17.sh, fastproxy.py on the v45 dump, calibrated proxy, 5-jitter averages; PROXY values: subtract
  the row bias above for a render estimate). Base = r30 code (edge lift reverted).
  | variant | smile band .4-.6 | smile in_up | st band | st in_up | st corner rise | smile corner rise* |
  | base (c1_9) | 3.3 | -4.4 | 2.6* | -8.2 | 12.3 | 13.9 |
  | + corrective jawOpen_mouthSmile 1.0 (c1) | 3.3 | -4.4 | 1.4* | -6.9 | 12.7 | 13.9 |
  | c1 + ROLL_TUCK_SLACK 0 (t0) | 2.8 | -4.1 | 2.6* | -6.7 | 13.0 | 14.0 |
  | c1 + SMILE_UPPER_LIFT 4 mm (u4) | 3.6 | -5.1 | 2.0* | -7.8 | 12.4 | 13.8 |
  | c1 + fold cheek push 0 (f0) | 3.0 | -4.0 | 1.6* | -6.6 | 12.4 | 13.8 |
  (* = row not validated.) Render estimates: base smile in_up -1.1 (ref -0.6), st in_up -5.4 (ref -2.0); the corrective
  takes st to ~ -4.1 (1.3 of the 3.6% io wanted) BUT opens a dark / red dash in the upper lip's middle above the
  incisors (fast/s17/t0_cmp.png, top right): the vermilion pulled down under jawOpen's landmark lift (JAW_UPPER_LIFT
  solve) folds. Not shipped (SMILE_JAW_CANCEL 0; code kept: CORRECTIVES + playback's sided mean + the GNM shape).
  Next for st: cancel the jaw's landmark lift too (a corrective solve on UPPER_LIP with the jaw's JAW_UPPER_LIFT
  negated), not only the direct lift, and check the dash with the ID pass.
  Corner rise: the fold's cheek push does NOT raise the corner (f0: st 12.7 -> 12.4, within noise; smile unchanged); the
  x44 -> x45 corner rise +0.9 (smile) is at that row's render noise x2 and the proxy can't confirm it: left as is.
  Gum spikes: the pink papillae show where the st upper lip is too high; no separate fix this round.
  Jaw side shadow: NOT done (budget). Lever: skin_features' sock darkening by |x| beyond the dental arch (a
  MOUTH_DARK_SIDE ramp beside MOUTH_DARK_DEPTH); risk: the smile's corners use the same sock (the "black corner"
  complaint): measure both with idclose.py before exporting.
- v46 = r30 code - SMILE_EDGE_LIFT + ROLL_TUCK_SLACK 0. chain_v46.sh (export, mh/v46, lip gate, x46 shots_expr9 on
  NICO-TOP, review/expr_r28 + measures), launched detached. Note: faceshapes.playback now also returns
  jawOpen_mouthSmile (min(jawOpen, mean smile)) and asset's correctives metadata lists it although it isn't exported
  while SMILE_JAW_CANCEL is 0 (engines ignore unknown targets).
- RESULT v46 / x46 / review/expr_r28: FAIL (lip gate 2.50% PASS). MAJORs as r27: seam ragged + fleck, "no tongue", black
  vertical side lines in jaw, everted lip ring, jaw too long; smile: jagged inner upper lip with dark corner gaps, lower
  lip clips the upper teeth, slot shape, no cheek / fold / squint, heavy lower lip; smileteeth ~ smile, red spikes
  between the upper teeth; plus hair cards, nostrils, likeness (outside this thread).
- PROXY OUT-OF-SAMPLE CHECK (x46 was not in the calibration; fast/s17/t0_9_vs_x46.txt, 5-jitter averages):
  | row | x45 render | proxy predicted (bias-corrected) | x46 render | residual |
  | smile red band .4-.6 | 3.7 | 2.3 | 3.1 | -0.7 (direction right, size 1/2) |
  | smile teeth top .4/.6 | 1.5 | 1.3 | 1.1 | +0.1 |
  | smile in_up mid | -1.3 | -0.8 | -1.0 | +0.2 |
  | st teeth top | -3.1 | -3.0 | -3.0 | +0.1 |
  | st in_up mid | -5.6 | -5.3 | -5.3 | 0.0 |
  | st corner rise | 16.3 | 16.0 | 16.2 | -0.2 |
  | st red band (not validated) | 4.4 | 4.4 | 4.2 | +0.2 |
  | smile corner rise (not validated) | 17.1 | 16.5 | 16.5 | 0.0 |
  So the proxy now predicts geometry rows (teeth top, in_up, corner rise) within 0.2% io; the smile red band moved the
  predicted way but only half as far: treat band predictions as direction + half-size until recalibrated with x46 in.
  ROLL_TUCK_SLACK 0 is KEPT (band 3.7 -> 3.1, the ref 0).

## Handover 2026-10-16 r31 (assembly agent, tool-call limit)
- Worktree agent-ad0815704f43e0e00, committed, not pushed. Nothing in flight. v46 exported, x46 rendered,
  review/expr_r28 + expr_r28_measures.txt written. FAIL.
- The proxy (flatcam.py, calib.py, calib2.py, calcmp.py, fastproxy.py, idtrace.py, idclose.py in the scratch dir;
  cal/centre.json, cal2/shade2.json) is the tuning gate now: validated rows listed above, x46 as an out-of-sample
  check. Recalibrate with x46 added (calib.py cal3 v46:x46 v45:x45 v44:x44 v43:x43, then calib2.py) before the band
  is tuned again.
- NEXT: (1) smileteeth upper lip (st in_up -5.3 vs ref -2.0, gum spikes): the corrective jawOpen_mouthSmile is in code
  (SMILE_JAW_CANCEL 0 = off); cancelling only the direct lift gives 1.3 of 3.6% io and opens a dash in the upper lip:
  add the jaw solve's own UPPER_LIP landmark lift (JAW_UPPER_LIFT) negated to the corrective, check the dash on the
  fastproxy ID image. (2) smile red band 3.1 -> 0: levers left after slack 0: the inner rolls' tuck depth (ROLL_BEHIND),
  SMILE_UPPER_LIFT's arch (4 mm made it worse). (3) "no tongue": the dorsum is flat and faces up (n.z 0.80) in the
  palate's shadow: give it a dome / forward tilt in jawOpen (TONGUE_* shape), measured on the tongue column of pair_6.
  (4) jaw side lines: sock side-wall darkening by |x| (MOUTH_DARK_SIDE), measured with idclose.py on jaw AND smile
  corners. (5) corner holes: back teeth in shadow + edge-on rolls fill the outer fifth: a buccal-corridor read, judged
  in render.

## Round 32 (2026-10-16, assembly agent, fresh session)
- Merged origin/main (43dcdf5a cloth tooling, b32d303f game camera fov): clean.
- PROXY RECALIBRATED with x46 in (cal3: calib.py + calib2.py over v43..v46, k 0.5, mouth rms 21.0; cal3/cmp_jit.txt).
  Row biases (proxy - render, % io) barely moved: smile band +0.45 (residuals +-0.35), st band -1.73 (+-0.6, still not
  validated), smile teeth top -2.4, st teeth top -3.3, smile in_up -3.3, st in_up -2.7, st corner rise -3.5. fastproxy
  now takes CAL=cal3 and POSES=...,jaw (writes the jaw pid for tongueramp.py: the tongue's lit ramp down its middle).
- sweep18 (fast/sweep18.sh, v46 dump, PROXY values, 5-jitter means; b = v46 code):
  | variant | smile band | smile teeth top | smile in_up | st band | st teeth top | st in_up | st corner |
  | b | 2.7 | -1.4 | -4.1 | 2.6 | -6.3 | -8.0 | 12.6 |
  | c1 SMILE_JAW_CANCEL 1 | = | = | = | 2.6 | -5.9 | -6.7 | 13.1 |
  | lm c1 + SMILE_JAW_CANCEL_LM 1 (new: the corrective also takes back jawOpen's upper-lip LANDMARK lift) | = | = | = | 2.6 | -5.2 | -6.2 | 13.1 |
  | lm5 c1 + LM 0.5 | = | = | = | 2.6 | -5.8 | -6.7 | 12.9 |
  | s3 ROLL_TUCK_SLACK -0.3 mm | 1.2 | -1.6 | -3.8 | 2.3 | -6.3 | -7.7 | 13.2 |
  | s6 ROLL_TUCK_SLACK -0.6 mm | 1.0 | -1.4 | -3.7 | 2.1 | -6.7 | -7.8 | 13.4 |
  | u2 SMILE_UPPER_LIFT 2 mm | 1.8 | -1.1 | -3.0 | 1.6 | -6.1 | -7.0 | 13.1 |
  DASH: c1, lm5 AND lm all show the dark dash in the st upper lip's middle (fast/s18/st_lm.png): it comes with the
  DIRECT lift's cancel (the vermilion moved down, its inner roll not), not the landmark lift. Tested next: LM alone.
- TONGUE: GNM's bow components (JAW_TONGUE 0,0,3 / 6 mm; tip forward 0,-2,4 mm) SINK the tongue and tear black gaps
  at its front (fast/s18/tongue.png): rejected (as r26 / r28). New shaped offset TONGUE_DOME (front half rolled down
  quadratically on the top surface, whole tongue raised): sweep18c.
- MOUTH_DARK_SIDE (skin_features, new, ON at (0.55, 0.8, 3 mm, 6 mm)): the sock past 0.55-0.8 of the mouth half width,
  3-6 mm in, darkens (jaw: lit pink walls beside black edge-on lines). Texture: checked on the v47 export's proxy.
- sweep18b (LM cancel alone, no direct-lift cancel): lmo (LM 1) st in_up -8.0 -> -7.0, st band 2.6 -> 1.6, smile
  unchanged; lmo2 (LM 2) -7.3 (overshoots, worse); lc5 (direct 0.5 + LM 1.5) -6.9 with the dash. lmo still shows a
  FAINT dash (fast/s18/dash_zoom.png, top right): the corrective's dash is not only the direct lift.
- sweep18c/d: su (slack -0.6 mm + lift 2 mm): smile band 1.1, smile in_up -3.4, smile teeth top -1.8 (render est:
  band ~0.7-1.9 given the half-size caveat, in_up -0.1 vs ref -0.6, teeth top +0.6 vs ref +0.7), st in_up -7.4, st
  band 2.6; but su shows a dash in the st upper lip (dash_zoom.png bottom left), s6 alone a jagged speckle, s3 and u2
  alone clean (dash_zoom2.png), s3u2 faint specks (d_check.png). sul (su + LM 2): st band 3.4, worse.
- TONGUE: TONGUE_DOME (roll front 3-5 mm, raise 0-2 mm) and the TILT form (back raised 3 / 6 mm, linear to the tip)
  leave the jaw proxy's tongue UNCHANGED (ramp 61 74 75 79 67 for b, t3, t6, r2t4; same pixel count): the offset is not
  reaching the rendered tongue. Unexplained: JAW_TONGUE in the same branch does change it. Debug first (print the
  tongue's jawOpen delta norm with / without TONGUE_DOME in fastproxy's apply) before trusting any tongue sweep.
- NOT EXPORTED this round (tool-call budget, and every combination that moves the st upper lip shows a dash / specks).

## Handover 2026-10-16 r32 (assembly agent, tool-call limit)
- Worktree agent-ad0815704f43e0e00 (main merged), committed, not pushed. Nothing in flight. v46 / x46 / expr_r28 still
  the latest render: FAIL.
- Code (all default OFF except MOUTH_DARK_SIDE): SMILE_JAW_CANCEL_LM (corrective takes back jawOpen's upper-lip landmark
  lift), TONGUE_DOME (roll, tilt; currently ineffective, see above), MOUTH_DARK_SIDE (0.55, 0.8, 3 mm, 6 mm) ON but
  UNTESTED: the next export's proxy shows it (chain_v47.sh runs fastproxy on the v47 export before the render:
  fast/s47/cmp_<pose>.png, v46 | v47). Set it to None if the smile corners darken.
- Proxy: cal3 (x43..x46). Use CAL=cal3. Scripts new: tongueramp.py, mouthsheet.py; fast/sweep18*.sh.
- NEXT: (1) band: ship ROLL_TUCK_SLACK -0.0003 (s3: smile band 2.7 -> 1.2 proxy, clean); SMILE_UPPER_LIFT 2 mm (u2)
  helps band + in_up but s3u2 shows faint specks: check at 2x crop, else take s3 alone. (2) st upper lip: the dash
  comes with ANY corrective lowering of the upper vermilion under jawOpen: likely the inner roll tucked for jawOpen's
  lifted lip pokes through when the lip comes down; try running _rolls_tucked on the COMBINED smile+jaw pose (or
  tucking the corrective's own offsets against the jawOpen-posed rings). (3) tongue: debug TONGUE_DOME's path first.
  (4) then chain_v47.sh (SHOTS=shots_expr10 if a corrective is on: shots_expr9 lacks the jawOpen_mouthSmile weight),
  lip gate, ONE NICO-TOP batch, blind review expr_r29.

## Round 33 (2026-10-16, assembly agent, fresh session)
- sweep18d (v46 dump, cal3 proxy): s3u2 (ROLL_TUCK_SLACK -0.3 mm + SMILE_UPPER_LIFT 2 mm): smile band 2.7 -> 1.0, smile
  teeth top -1.3, smile in_up -4.1 -> -3.1, st band 2.6 -> 1.8, st in_up -8.0 -> -7.0. 2x crops (fast/s19/s3u2_crop.png):
  s3 and s3u2 carry the same thin lip-teeth contact line in the smile's middle, no new artefact from the lift. SHIPPED in v47.
- TONGUE_DOME "no effect" is NOT a plumbing bug (tonguedbg.py, tonguedbg2.py): apply() puts the offset on the tongue's
  jawOpen delta (tilt 6 mm: max 6.0 mm, mean dz +3.0 mm; roll 4 mm: max 2.7 mm), and the jaw raster moves with it (visible
  tongue verts move 1.9 mm, tongue normals turn ~7 deg, depth -2.6 mm). The tongue's pixel count can't change: the
  opening frames it. What's missing is the PROXY'S TONGUE SHADING: on v46 the render's ramp is 75 77 100 142 112 (mean 99),
  the proxy's 61 75 75 79 68 (mean 68). cal3 is not calibrated on the tongue, so tongue sweeps can't be judged in the proxy.
  Against the reference (30 -> 110) the render's tongue is too LIGHT at the top (75 vs 30) and hot in the middle (142).
  v47 carries TONGUE_DOME (0, 3 mm) (back raised: the top rows go up under the palate's shadow) as a RENDER test.
- (3) DASH: the hypothesis holds. The corrective's rolls were tucked against its own offsets alone. ROLL_TUCK_COMBINED
  (new, default on; inert while the corrective is off) tucks them against jawOpen + both smiles + the corrective. sweep19
  (s3u2 + SMILE_JAW_CANCEL 1, expr10 weights): c1n (old tuck) st band 2.8, st in_up -6.3, DASH (fast/s19/tuck_crop.png top
  right); c1y (combined) st band 1.3, in_up -5.6, clean; lmy (c1y + SMILE_JAW_CANCEL_LM 1) st band 0.7, st in_up -5.0
  (render est ~-2.3 with the -2.7 row bias, ref -2.0), st teeth top -4.4, clean (bottom right). lmy is v48's pick.
- (4) smile -> smileteeth in the reference (expr_r28 measures, % io): width 104 -> 114 (+10), lower lip in_lo +12.6 ->
  +19.7 (+7.1), lower teeth bottom ~+10 -> ~+19.5 (+9.5: lower teeth bared), upper lip in_up -0.6 -> -2.0 (only +1.4 up),
  opening mid 13.1 -> 22.6. Ours (x46): width 109 -> 110 (+1), in_lo +4.7, teeth bottom +4.5, in_up -1.1 -> -5.1 (+4.0 up).
  So the reference's smileteeth is a WIDER smile with the lower lip dropped, the upper lip nearly where the smile has it;
  ours opens mostly by lifting the upper lip (mouthUpperUp 0.6 + jawOpen 0.2, no mouthLowerDown or stretch). That's the
  pose weights, not the shapes: sweep19b tries st weights with mouthLowerDown 0.6-0.8, mouthStretch 0.3-0.5, upperUp 0.4-0.5
  (fastproxy ST_W env overrides the expr10 smileteeth weights).
- sweep19b (st weights, s3u2 code, expr10 column): w1 (jaw 0.2, upperUp 0.5, lowerDown 0.6), w2 (jaw 0.15, upperUp 0.5,
  lowerDown 0.8, stretch 0.3), w3 (jaw 0.2, upperUp 0.4, lowerDown 0.8, stretch 0.5): st opening 31.8 / 32.3 / 34.4 (base
  24.0, ref ~22), st in_up -9.0 / -9.2 / -9.1 (base -7.0: WORSE, GNM's mouthLowerDown also lifts the upper inner lip in
  this measure), st band 2.4 / 1.9 / 2.0. FAIL: no weights change. The width (+10% io in the reference) isn't in calcmp's
  rows yet: add a width row before the next weights sweep, and try mouthStretch / a stronger smile WITHOUT lowerDown.
- v47 EXPORTED (exp/ga_tess_v47, lip gate 2.50%). Its proxy (fast/s47: cmp_<pose>.png v46 | v47, log.txt): smile /
  smileteeth corners' mean luminance unchanged (133.9 -> 134.1, 118.4 -> 118.4, 128.2 -> 128.5, 113.8 -> 114.0):
  MOUTH_DARK_SIDE darkens nothing visible at the corners, KEPT. Middle: the red band under the upper lip becomes a thin
  dark lip-teeth contact line (a watch item for the render review). v47 tongue ramp in the proxy 62 74 75 79 67 (the
  proxy can't see the tongue, above). chain_v47.sh now stops before the render (chain_v47r.sh renders).
- v48 = v47 + the corrective on (SMILE_JAW_CANCEL 1, _LM 1, combined tuck): chain_v48.sh (proxy v47 | v48 in fast/s48),
  then chain_v48r.sh renders x48 with shots_expr10 as this round's ONE NICO-TOP batch (x47 not rendered: v48 contains it).
- v48 EXPORTED (exp/ga_tess_v48, 54 targets incl. jawOpen_mouthSmile, lip gate 2.50%). Proxy v47 | v48 (fast/s48/cmp_*.png):
  smile identical; smileteeth upper lip lowered, the pink gum / red band above the incisors gone, NO dash; corners unchanged.
  x48 (shots_expr10) launched on NICO-TOP via chain_v48r.sh (offload/x48, review/expr_r30 + measures).
- x48 / expr_r30 (review/expr_r30, measures review/expr_r30_measures.txt): FAIL.
  REGRESSION: smile AND smileteeth upper lip split into a hanging centre flap between two dark slots (pair_7 / pair_8,
  fast/s48/smile_r28_r30.png, st_r28_r30.png: r28 | r30 crops). In both poses, so it comes from the smile-side picks
  (ROLL_TUCK_SLACK -0.3 + SMILE_UPPER_LIFT 2 mm), NOT the corrective. The proxy showed only a short dark segment in the
  middle of the contact line (fast/s19/s3u2_crop.png). I read that segment as acceptable, and that was wrong: a dark
  segment in the proxy's lip-teeth line is a flap in the render. Defaults are reverted to v46's (slack 0, lift 3 mm) in the tree.
  Measures, x46 -> x48 (ref): smile in_up -1.1 -> -1.8 (-0.6) worse; st in_up -5.1 -> -4.6 (-2.0), only +0.5 against a
  proxy prediction of ~-2.3, so the corrective's st gain is far smaller in the render than in the proxy (the st band bias is
  not validated, as cal3 warned); st red above mid 7.5 -> 6.5; smile red above mid 4.3 -> 4.8. The gums between the
  incisors in the st are gone (the corrective lowered the lip there). Tongue column (TONGUE_DOME tilt 3 mm): our
  47 44 44 ... 104 116 vs x46's 47 45 44 ... 102 115, i.e. NO visible change in the render either; the review still says
  "no tongue". Width (st) 108 vs ref 114.
  Other review MAJORs (unchanged areas): jaw V-stretch, mouth too tall, torn cheek interior, teeth gaps, corners torn,
  no eye / cheek participation, neutral lips not sealed, blink lid smear, hair cards, likeness.

## Handover 2026-10-16 r33 (assembly agent, tool-call limit)
- Worktree agent-ad0815704f43e0e00, committed, not pushed. Nothing in flight. Latest render: x48 / expr_r30, FAIL with a
  regression (the upper-lip flap). v47 and v48 exports exist (exp/ga_tess_v47, _v48); x47 was not rendered.
- Tree defaults now: v48's minus the smile picks, i.e. slack 0 and lift 3 mm (v46's smile) + the corrective (SMILE_JAW_CANCEL
  1, _LM 1, ROLL_TUCK_COMBINED) + TONGUE_DOME (0, 3 mm) + MOUTH_DARK_SIDE. This combination is UNTESTED as a whole.
- Proven this round: ROLL_TUCK_COMBINED removes the corrective's dash (proxy, and no dash in the st render). TONGUE_DOME
  reaches the vertices and the raster, but neither the proxy NOR the render's tongue column changes at a 3 mm tilt. The
  visible tongue is framed by the opening, and its shading isn't driven by this tilt. Next lever for the 30 -> 110 ramp:
  the texture (TONGUE_BACK's darkening by rest depth, or a darkening by posed height under the palate), or the lighting
  occlusion of the palate. Not the shape.
- NEXT: (1) v49 = the tree as is: export, proxy v46 | v49 (smile must equal v46's), render. Judge the st upper lip (the
  corrective's in_up gain in the render is small: +0.5% io). (2) If the band work resumes: treat any dark segment in the
  proxy's lip-teeth line as a FAIL. Test s3 alone and u2 alone in ONE render batch to see which made the flap.
  (3) smileteeth vs smile: the reference widens by 10% io and drops the lower lip. Ours lifts the upper lip. lowerDown
  weights made in_up worse in the proxy (sweep19b). Add a width row to calcmp, then try mouthStretch / smile > 1 without
  lowerDown. (4) The tongue via the texture (above).

## r34 (2026-10-16, assembly agent): game distance, v49 + flap isolation
- Merged origin/main (14917ffb hides; asset.py conflict: own_mouth_meshes + _hide_covered both kept). Tests one file per
  process: test_hides 4 pass; test_face_shapes 13 pass after updating the goblin test (54 names with jawOpen_mouthSmile; that
  corrective is GNM-path only, so it moves nothing on the goblin: exempted).
- gates.md (main 9ca28f52, pushed): "Game distance" rule: 1 m / 3 m at 1080p, native-pixel crops, MAJORs classified
  game-visible vs close-up-only; close-up-only don't block unless visible at 1 m.
- Proxy dark-line check (scratch darkline.py: per teeth column, rows of lum < 40 between the teeth top and the lip; a
  segment = 3+ dark columns; the outer 8% of the teeth span each side = corners, skipped). On the v48 dump with the
  constants overridden (fast/s49_*, sheet fast/s49_mouths.png):
  | variant | smile segments | smileteeth segments |
  | p49 = tree (slack 0, lift 3 mm) | none | 381+9, 411+11 (FAIL, faint 1 px) |
  | p49s slack -0.3 mm alone | 379+3 | 352+3, 377+9, 399+20 |
  | p49u lift 2 mm alone | 336+6, 361+3, 377+3 | 341+21, 402+8 |
  | p48f both (x48's flap) | 383+4, 396+3 | 6 segments, 63 dark columns |
  Both picks add dark segments; together they are worst. The tree's own st has a faint one: proxy FAIL by the strict rule.
- calcmp.py now has width rows (lipcurve's corner-to-corner width, % io and % of neutral's). Reference: neutral 79.9,
  smile 103.8 (130%), smileteeth 114.0 (143%). Proxy p49: neutral ~74.7, smile 108.5 (145%), st 109.3 (146%). So the
  smile is already 5% io too wide and smileteeth only +0.8 over smile where the reference is +10: smileteeth widens by
  the stretch / corner pull, not the smile weight.
- STATE: chain_v49.sh running (exports v49, v49s, v49u with exp.py HP_FS_SET overrides -> own proxies + darkline in
  mh/v49.txt -> ONE NICO-TOP batch x49 with shots_expr11 (close-ups + g1_/g3_ game shots, 1920x1080, vfov 59) -> gsheet.py
  review/game_r31.png -> reviews expr_r31_game (v49 at 1 m / 3 m) and expr_r31 (close-ups)).
- x49 (one NICO-TOP batch, 3 jobs, $0): v49 / v49s / v49u exported (487-560 s each; lip gate 2.5%). NOTE: chain_v49's own
  proxies rebuilt shapes with the TREE constants (fastproxy recomputes from the dump), so mh/v49.txt's v49s / v49u
  darkline rows are v49's; the valid variant proxies are fast/s49_p49s / _p49u above. Pass the overrides to fastproxy next time.
- Game sheet review/game_r31.png (gsheet.py: native-pixel 1 m 400 px / 3 m 160 px crops of 1920x1080 vfov 59 frames; the
  reference scaled by MediaPipe interocular to ours and centred on the face; the first version scaled by frame size and
  was ~2x too small: fixed before the review). Reviews: expr_r31_game (v49, 1 m / 3 m) FAIL, expr_r31 (close-ups) FAIL.
- Flap isolation (close-ups, review/x49_flap_variants.png, v49 | v49s | v49u): v49 has no centre flap; slack -0.3 mm
  ALONE makes the flap with dark slots both sides (smile and st); lift 2 mm alone makes a milder slot right of centre.
  Both picks stay out. None of the three differs at 1 m or 3 m.
- MAJORs classified (game-distance review + my 1 m crop review/game_r31_mouth1m.png):
  GAME-VISIBLE (1 m, most also 3 m):
  1. jaw: the opening is a tall narrow pinched oval (reference: wide "ah", corners out), lips thinned to a rim (1 m + 3 m).
  2. jaw: both full tooth rows as pegs / fangs; reference shows the upper band and a few lower incisors (lower lip covers).
  3. smile / st: the upper lip pushed up into the nose (a "moustache" ledge, philtrum ~45% shorter) and the lower lip
     thick, everted, red flare under the teeth (1 m).
  4. smileteeth = smile at 1 m and 3 m: no widening, no extra tooth show (width row agrees: ref +10% io, ours +0.8).
  CLOSE-UP-ONLY (recorded, not blocking): lip-seam red slivers over the upper teeth, grey faces at the corners, uneven
  incisal edges, dark side bands in the jaw cavity, the faint st lip-teeth dark line (proxy darkline FAIL 381+9, 411+11).
  "No tongue" (close-up MAJOR): at 1 m the reference's lower opening reads pale pink, ours a dark red hole, but the
  game review did not name it; not yet a game-visible MAJOR, so the tongue texture lever (4) waits.
  Blink and neutral: no game-distance MAJOR.
- Causes for the game-visible set: (1, 2) jawOpen has no lateral corner pull and the lower lip doesn't ride up over the
  lower teeth: a jawOpen corner-width term (and lower lip cover) is shape work. (3) the upper lip lift (SMILE_UPPER_LIFT 3 mm
  + mouthUpperUp 0.5 in the pose) shortens the philtrum; the lower lip roll comes from mouthLowerDown 0.3 + rest volume.
  (4) smileteeth's width needs mouthStretch / corner pull, not more smile weight (calcmp width row first).

## Handover 2026-10-16 r34 (assembly agent, tool-call limit)
- Worktree agent-ad0815704f43e0e00 (merged origin/main), committed, not pushed (gates.md rule pushed from main, 9ca28f52).
  Nothing in flight. Latest: x49 (v49 tree, v49s, v49u) FAIL at game distance (4 game-visible MAJORs above).
- Tree = v49 (slack 0, lift 3 mm, corrective + ROLL_TUCK_COMBINED); keep it. Scratch: chain_v49.sh, gsheet.py (game
  sheet, use for every round), darkline.py (proxy lip-teeth line), exp.py HP_FS_SET, calcmp width rows, shots_expr11.json.
- NEXT, game-visible first: (1) jaw corner width + lower lip over the lower teeth (measure the jaw opening's width /
  height ratio on the reference vs ours first: a new calcmp row); (2) smile philtrum: lower the upper lip lift / UpperUp
  share in the pose, measured by a nose-to-lip row; (3) smileteeth width via mouthStretch, judged on the width row in the
  proxy before an export; (4) one export + ONE x50 batch with shots_expr11 + gsheet + both reviews.

## r35 (2026-10-16, assembly agent): smile philtrum, smileteeth width, jawOpen "ah", tongue
- New measure: scratch mouthrows.py (MediaPipe, % io): philtrum (2 -> 0), upper / lower vermilion, mouth width, opening h /
  inner w, and in the opening's lower half the teeth share, mean lum, hue, and lum / cheek (cheek patches 205 / 425).
  | row | ref neutral | ref smile | v49 smile (render) | ref st | v49 st | ref jaw | v49 jaw |
  | philtrum | 22.2 | 20.0 | 12.6 | 18.3 | 13.8 | 18.7 | 14.5 |
  | upper verm | 12.1 | 10.3 | 13.0 | 8.8 | 12.4 | 9.5 | 8.4 |
  | lower verm | 15.5 | 14.2 | 18.3 | 13.0 | 17.0 | 15.2 | 15.1 |
  | width | 79.9 | 103.8 | 108.8 | 114.0 | 109.1 | 89.8 | 81.8 |
  | opening h / inner w | - | 13.2 / 96 | 17.3 / 99.5 | 21.8 / 106.5 | 23.2 / 100.5 | 55.8 / 82.5 | 60.9 / 74.2 |
  The reference smile THINS both lips and barely moves the upper lip's outer edge (philtrum 90% of neutral); ours climbs
  to the nose (52%) and both lips thicken. Jaw lower half: lum / cheek 0.44 ref vs 0.44 close-up render but 0.36 in the
  1 m game frame (ref 0.43), hue 12 ref vs 1-4 ours (ours magenta-dark: the sock's MOUTH_DEEP_COLOR has G = B).
- Cause of the philtrum: mostly mouthSmile itself (SMILE_PROTO's own upper-lip rise + SMILE_UPPER_LIFT's 3 mm feathered
  into the upper-lip region), not only the pose's mouthUpperUp: upperUp 0 + lift 1.5 mm still left 16.4 (sweep35 u0).
- Fix (faceshapes): SMILE_UPPER_HOLD (1.0) takes back the outer upper edge's vertical travel (landmarks 50-52, half at
  49 / 53) in the prototype's solve AND the lift's own rise (a second solve with 61-63 kept where the lift put them: the
  inner edge still rides up the incisors, so the lip thins); SMILE_LOWER_HOLD (0.8) the same for the lower outer edge
  (56-58). jawOpen: JAW_CORNER_OUT 0.11 -> 0.55 (0.3: +3.8 width only) and GNM_OPEN 22 -> 20.
- Pose recipe shots_expr12 (scratch; the game-shot / close-up weights): smile = smile 0.92, upperUp 0.3, lowerDown 0.15
  (was 1 / 0.5 / 0.3); smileteeth = smile 1, upperUp 0.4, mouthStretch 0.4, jaw 0.2 + corrective 0.2, no lowerDown (was
  upperUp 0.6, no stretch). lowerDown in st (h3 / h4) bared the lower row with a dark gap between rows: out.
- Proxy (calibrated flat, v49 dump, sweep35 / 35b / 35c; mh/s35*.txt):
  | variant | smile phil / upV / loV / width | st phil / upV / loV / width | darkline |
  | p49 tree | 12.5 / 15.0 / 19.6 / 108.5 | 11.9 / 15.6 / 18.8 / 109.3 | smile ok, st FAIL faint |
  | h6 (kept) | 19.3 / 10.1 / 15.8 / 105.0 | 19.0 / 11.5 / 16.5 / 112.8 | smile 335+29, st 6 segs: FAIL |
  | h7 holds 0.8 / 0.6 | 18.6 / 10.7 / 16.4 / 105.5 | 18.2 / 12.1 / 16.9 / 113.5 | FAIL |
  | jd jaw (kept) | jaw width 89.6, opening 56.2, inner w 82.0, w/h 1.5 (ref 89.8 / 55.8 / 82.5 / 1.5) | | |
  The darkline rule FAILs on h6: a thin dark line under the upper lip (close-up item in r34's classification); the smile
  shows a thinner upper-teeth band than the reference (opening 11.7 vs 13.2). Game-visible rows chosen over it.
- Tongue (coordinator: game-visible): v50t = v50 + skin_features.TONGUE_BACK (0.04, 0.06) -> (0.05, 0.08) and
  MOUTH_DEEP_COLOR [0.035, 0.008, 0.008] -> [0.05, 0.016, 0.009] (warmer, a little lighter), as export overrides
  (exp.py HP_FS_SET now takes "module.CONST"). The flat proxy is not calibrated on the tongue: judged in the render.
- x50 (one NICO-TOP batch, 2 jobs, $0; v50 = tree, v50t = + tongue texture; shots_expr12). Game sheet review/game_r32.png,
  1 m mouths review/game_r32_mouth1m.png (rows: ref | v49 | v50t; jaw, smile, smileteeth, neutral). Rows at 1 m (mh/v50_rows.txt):
  | 1 m | phil | upV | loV | width | open h | lower-half lum / cheek, hue |
  | ref smile / v50 | 19.5 / 21.0 | 9.2 / 9.1 | 13.8 / 16.2 | 101.6 / 105.6 | 14.0 / 12.5 | |
  | ref st / v50 | 18.7 / 21.3 | 8.0 / 9.6 | 13.1 / 15.5 | 113.1 / 112.5 | 21.8 / 19.4 | |
  | ref jaw / v50 / v50t | 18.2 / 12.9 | 9.8 / 10.0 | 15.6 / 17.3 | 89.1 / 90.0 | 57.5 / 56.4 | 0.44, 12 / 0.35, 1 / 0.35, 2 |
- VERDICT: FAIL at game distance (review/expr_r32_game, on v50t): the moustache / short philtrum is gone and smileteeth is now
  wider than smile, BUT: (a) smile and st now read as a tight grimace with the upper lip "almost gone" over a thin strip of
  teeth (the rows say upV matches the reference: the reviewer reads lip VOLUME / colour, and our teeth band is short: open
  h 12.5 vs 14.0, st 19.4 vs 21.8); (b) st still too close to smile (teeth strip, little extra opening); (c) jawOpen reads as
  a snarl: both full tooth rows bared, lips a thin dark-red ring, opening rectangular with stretched corners (the width
  number matches, the SHAPE does not: corner pull makes a box, not an oval); (d) tongue not readable (MINOR at 1 m).
  Close-up review expr_r32: 12 MAJORs incl. a NEW one: jawOpen mouth corners torn (jagged red-brown tissue) - JAW_CORNER_OUT
  0.55 most likely; corners' inner geometry grey in smile / st.
- Tongue texture lever FAILED: v50t = v50 to within 0.5 lum (lower half at 1 m 52.8 vs 52.4, hue 2 vs 1): what fills the
  opening's lower half is not the tongue's back or the deep colour's tint. Next: measure WHICH mesh fills it (an ID pass of
  the 1 m jaw frame: sock vs tongue vs lips' inner rolls), then light / occlusion or the tongue's position.

## Handover 2026-10-16 r35 (assembly agent, tool-call limit)
- Worktree agent-ad0815704f43e0e00, committed, not pushed. Nothing in flight. Latest: x50 (v50, v50t) FAIL at game distance.
- Tree: SMILE_UPPER_HOLD 1.0, SMILE_LOWER_HOLD 0.8 (new), JAW_CORNER_OUT 0.55, GNM_OPEN 20. Pose recipe shots_expr12.
  Scratch: mouthrows.py (rows), sweep35*.sh (proxy sweeps with POSE_W pose overrides in fastproxy.py), chain_v50*.sh
  (gsheet must run under uv: python3 lacks skimage when MediaPipe's cache misses), exp.py HP_FS_SET "module.CONST".
- NEXT: (1) jaw: back off JAW_CORNER_OUT (0.3 with GNM_OPEN 20; check the corner tear in a close-up) and get the oval from
  the lips covering the teeth instead: lower lip up over the lower row (JAW_LOWER_BACK / a lower-lip rise), less
  JAW_UPPER_LIFT / JAW_LIP_LIFT so the upper gum line hides; add a "teeth shown height" row per row (upper / lower) to
  mouthrows first. (2) smile: holds at ~0.6 / 0.5 (between v49 and v50) so the upper lip keeps volume, and more teeth
  band (open h 14) via the inner edge only; st needs more opening (jaw 0.3) and its own corner pull. (3) tongue: ID pass
  first (above). (4) one export + ONE batch, game sheet + both reviews.

## r36 (2026-10-16, fitted shapes spike: the smile from Tess's own smile photo)
- Coordinator's change of approach: shapes FITTED to her expression photos instead of hand constants on ARKit-style moves.
- Fit (scratch `assembly/fitexpr.py`): scratch model fx_<key> = tp_k19's spec COPIED (tp_k19 untouched) with one front view
  (the full-res photo, the front camera as start, its own camera fitted with cameras-first on the held head),
  `face_ruler.read(tau=1e-4)` (identity held) with the per-picture expression as the nuisance over GNM's WHOLE face expression
  space: 40 PCA directions of the sampler's decoded expressions (every class, 300 each; 96.5% of the energy; second moment about
  neutral, 1 unit = 1 population sd), interior reads only (EXPR_TYPES: mp / lid / lip / iris). NONLINEAR: 4 rounds, each with
  the expression so far APPLIED (base.head.expression) and the prior on the whole (mean -z). Converges (|dz| 5.6 -> 0.24).
  The neutral photo fitted the same way (|z| 2.4-3.2: the identity's misfit) and SUBTRACTED: shape = smile - neutral.
  mp_neff 80 (default 16 x3 the mp sigmas; the lips' opening hardly read) and prior sd 1 / 2 all give the same smile (3D on
  tp_k19: corners up 7.4 / back 9.4 / out 6.1 mm, eye aperture -23..-30%, apples up 4.5 mm, mouth width +25%, inner gap 8.3 mm).
- faceshapes: `SMILE_FIT` (env HP_SMILE_FIT = .npy of 383 coefficients): mouthSmile = its lower-face comps per side, cheekSquint
  = its eye comps per side; no SMILE_PROTO / holds / lifts / fold; the lower teeth row rigid (its own coefficients bent the rows).
- Proxy (fastproxy on v49dump, cal3; pose smile = mouthSmile 1 + cheekSquint 1), smile minus neutral, % io (smilerows.py):
  | row | reference | v50 (h6) | fitted (f36c) |
  | width change | +42.6 | +52.5 | +42.2 |
  | corner rise L / R | +24.7 / +14.7 | +15.5 / +17.1 | +17.7 / +17.5 |
  | apple rise L / R | +9.3 / -0.5 (R read slides) | +2.0 / +3.1 | +0.9 / +1.9 |
  | eye aperture L / R % | -25 / -19 | -18 / -22 | -20 / -21 |
  mouthrows: ref phil 20.0 upV 10.3 loV 14.2 open h 13.2 teeth 0.57 | v50 19.3 10.1 15.8 11.7 0.72 | fit 21.4 9.7 13.8 14.4 0.32.
  The fit fixes the width (v50's sideways pull) and the opening, but the TEETH are hidden (0.32): the upper inner lip drapes over
  the upper row in a wavy line (our teeth placement / rolls vs her lips; the reads see the lips, not the teeth).
STATE: SMILE_FIT path in tree (off by default); x51 = one export v51f + one NICO-TOP batch (shots_fit36) for the 1 m look.
NEXT: 1 m sheet reference | v50 (x50 j0) | v51f, blind review, verdict to the coordinator.
- x51 (v51f = tree + HP_SMILE_FIT, test_face_shapes exit 0, lip gate 2.50%), ONE NICO-TOP batch (shots_fit36), sheet
  `review/game_r36.png` (ref | v50 | v51f at 1 m and 3 m), zoom `review/game_r36_smile1m_zoom.png`. VERDICT (own look at 1 m): FAIL:
  the fitted smile does NOT beat v50. It has the right width and the squint, but the upper lip hangs pale and full over the
  upper teeth, and the teeth edge is ragged. It reads as a tight, tense smile, not her open smile. v50's crescent still reads more
  as a smile (though too wide). The blind review was not run (tool budget); smileteeth / jawOpen were not fitted (the gate is "beats v50").
- WHY (numbers above): the photo reads constrain the LIPS (open h 14.4 vs ref 13.2, width +42.2 vs +42.6, loV 13.8 vs 14.2), but
  nothing reads the TEETH against them: teeth share of the opening 0.32 vs ref 0.57. Her upper lip rides up OFF the incisors and
  the incisors fill the opening; on our export the GNM teeth sit higher / further back than hers, so the same lip opening shows
  inner-lip roll and cavity. The apples also come out low (proxy +0.9 / +1.9 % io vs ref ~+4.4 mean; 3D on GNM +4.5 mm, so the
  carry / the mouth mask may also cut them). Both are interior placement and carry problems, not the expression basis: GNM's basis
  reproduced the outer lips, corners and lids within read noise (rms o/sig mp 0.47, lip 1.4, lid 1.4).

## Handover 2026-10-16 r36 (fitted shapes)
- Worktree agent-ad0815704f43e0e00, committed, not pushed. Nothing in flight. Tree default unchanged (SMILE_FIT off = v50).
- Scratch: fitexpr.py (FX_IT, FX_SD, FX_NEFF, FX_TAG; fx/<key>.npz, fx/pca_40.npz), fxlook.py (clay on GNM through the fitted
  camera + 3D rows), smilerows.py (coupled rows: corner rise, width, apple, eye aperture, % io), shots_fit36.json, chain_f51.sh,
  gsheet.py GS_POSES subset. The fitted smile coefficients are at fx/smile_n80_shape.npy.
- NEXT: (1) a TEETH read in the fit, or a teeth hold: place the upper row so its incisal edge sits where the photo shows it
  relative to the lower lip (ref: the incisors reach ~the lower lip's inner edge), then refit. Or keep the fitted skin and only
  move the teeth/sock (interior) to the photo's teeth line. (2) apples: check the mouth_mask / eye_mask cut on the fitted
  lower-face + eye components (3D GNM apples +4.5 mm against +1-2 % io on the export). (3) then smileteeth / jawOpen the same
  way, export, batch, blind review.

## r37 (2026-10-16, assembly agent): teeth placement + apples for the fitted smile
- New read (scratch `assembly/teethline.py`, MediaPipe, % io): down the mouth's centre columns, the teeth runs relative to the
  upper inner lip (13; + = below), visible teeth height, the band above the first teeth row, the edge's distance to 14.
  | photo / model | open | upper teeth run | band above | edge to 14 |
  | ref smile | 13.1 | +0.8 .. +11.7 | 0.8 | 1.5 |
  | ref smileteeth | 20.2 | +1.0 .. +15.4 | 1.0 | 4.8 |
  | ref jawOpen | 54.1 | 0 .. +11.3 (lower row 7.5 above 14) | 0 | - |
  | x51 render smile (v51f) | 14.7 | +5.6 .. +9.1 | 5.6 | 5.6 |
  | proxy jawOpen (hand shape, tree) | 56.2 | -0.9 .. +13.8 (lower 9.5) | - | - |
- Proxy sweep (fastproxy `TEETH_D` = rigid upper / lower shifts after the shapes, "n:up,fwd,up,fwd;..." mm; r37/t1, t2;
  mask off): smile teeth share (mouthrows lower half) 0.33 tree | u-1.5 f1 0.45 | u-2 f1 0.48 | u-2 f1.5 0.65 | u-2 f2 0.81
  (ref 0.57); neutral front: 0 teeth pixels in every variant. BUT the band above the teeth stays 5.1-5.6 in every variant:
  the upper lip's CENTRE droops over the central incisors (a wavy inner edge: tubercle down, lower lip centre up; crop
  r37/t1_crops.png). That is lip shape, not teeth placement: the fit reads mp 13 as the lip's vertex, and the inner roll
  hangs ~3 mm below it in the render. Rigid teeth only lengthen the visible teeth DOWNWARD.
- The jaw photo CONTRADICTS a lower upper row: tree jawOpen already shows 13.8 of upper teeth vs the photo's 11.3, u-2 f1
  17.4. jawOpen is still the hand shape (its lip lift), so this constraint can only be used once jawOpen is fitted too.
  => teeth placement from three photos needs all three shapes FITTED; with only the smile fitted, it is a one-photo solve.
- Apples (smilerows, proxy; ref L +10.1 / R +1.3, mean 5.7): mask on 0.9 / 1.9 | SMILE_FIT_MASK off 1.4 / 2.3 (eye aperture
  -24 / -24, ref -28 / -22) | + SMILE_FIT_SOFT 0 (no soft-edge averaging on the fitted halves) 2.8 / 3.6, width +44.0 (ref
  +40.3) | soft 20: 1.1 / 2.5. The cut was mostly `_soft_edge` (moves under 70% of the largest averaged 80 rounds: the apple's
  ~4.5 mm against the corners' ~12 mm), the mouth mask second.
- Code: base.head.teeth_place {"upper" / "lower": [up mm, forward mm]} (rigid in the mouth frame, gnm_mouth: feeds the build's
  teeth parts and the face shapes); faceshapes SMILE_FIT_MASK (False) / SMILE_FIT_SOFT (80; export override 0).
- Skin routing (4), checked on v51f: the blink-multiply map darkens 61.6k texels, median x0.953, p5 x0.882: at most ~3-6 L,
  NOT the lids' 12 L excess. Next suspect: the skin paint's occlusion layer (workspace/ga_tess/skin_layers/occlusion.png) in
  basecolor + the renderer's own occlusion on top (the shading notes say lid occlusion is "already in basecolor"). The lower
  lip's doubled edge, lower-lid lightness and the right rim were NOT checked this round (tool budget).
- x52 (v52 = ga_tess_v52 copy, teeth_place upper [-2, +1.25], HP_SMILE_FIT, SMILE_FIT_SOFT 0, mask off; lip gate 2.48%; ONE NICO-TOP
  batch, $0, shots r37/shots_r37.json incl. g1_jaw and lashes-hidden `nolash_neutral` / `nolash_eyes` for the lashes stage).
  Close-up smile rows (render): teeth share 0.35 (v51f) -> 0.83 (ref 0.57: OVERSHOOT, the proxy predicted ~0.56: the real
  teeth / wrap differ from the proxy's post-hoc shift); visible teeth h 3.5 -> 8.2 (ref 14.4); band above STILL 5.3 (ref ~0);
  apples +2.5 / +4.1 (ref +9.3 / -0.5); width +45.5 (ref +42.6); eye aperture -17.5 / -14.4 (ref -25 / -19: weaker than the proxy).
  Mouth zoom review/game_r37_mouthzoom.png (ref | v50 | v51f | v52). VERDICT (own look): FAIL. v52 beats v51f (teeth fill the
  opening, no cavity), but the upper lip's centre still hangs in a V over the central incisors and the teeth edge sags with
  it; v50's clean arc still reads more like her smile. Gate (3) not met: smileteeth / jawOpen NOT fitted.
- TOOLING FAILS this round: gsheet.py wrote no review/game_r37.png and no crops (r37/gsheet.log: not read, tool budget), so the
  blind review saw no images (review/expr_r37_game: "FAIL, no images"); r37/post_v52.sh should have stopped on missing crops.
- TEST FAIL: tests/test_face_shapes.py with HP_SMILE_FIT + SMILE_FIT_MASK False: test_gnm_head_shapes "mouth shapes stay below
  the lower lids": mouthSmileLeft moves 0.77 mm above them. Fix proposal: a fit-only mouth mask that fades over the last
  ~20% under the lower lid (keeps the apples, passes the rule), instead of no mask.

## Handover 2026-10-16 r37 (assembly agent, tool-call limit)
- Worktree agent-ad0815704f43e0e00, committed, not pushed. Nothing in flight. Tree default unchanged (SMILE_FIT off = v50).
  New: base.head.teeth_place, faceshapes SMILE_FIT_MASK / SMILE_FIT_SOFT. Model copy workspace/ga_tess_v52 (scratch, not approved).
- Scratch r37/: sweep_t.sh (proxy TEETH_D sweeps + teethline + mouthrows + neutral teeth pixels), apple.sh, t2.sh, mcrop.py,
  chain_v52.sh, post_v52.sh, shots_r37.json; teethline.py (teeth line read) in assembly/.
- NEXT: (1) the upper lip's centre droop is the remaining smile fault and is LIP shape: add the lip's visible inner edge
  (the inner roll's lowest point at the centre, not the contact vertex) or a teeth-top read to the expression fit, then refit;
  (2) teeth_place: back the upper row to ~[-1, +0.75] (share overshoot 0.83 vs 0.57) and re-solve it with jawOpen FITTED (the
  hand jawOpen shows 13.8 of upper teeth vs the photo's 11.3, so the jaw photo cannot be used until then); (3) fix gsheet for
  r37 (read r37/gsheet.log) and run the blind review on x52's renders already on disk (offload/x52/results/x52/j0/out);
  (4) the fit-only mouth mask for the test; (5) skin routing: lid occlusion layer vs export basecolor, lower-lip doubled edge,
  lower-lid band, right rim (lashes-hidden renders are in x52: x_nolash_neutral_front.png, x_nolash_eyes_front.png).

## r38 (2026-10-16, assembly agent)
- (1) gsheet / review bug FIXED (scratch assembly/gsheet.py, backup .bak-r38): post_v52 passed prefixes ending "x_" and gsheet
  appended "_g1_" (x__g1_..., FileNotFoundError before anything was written; the review then got 0 pairs and printed its usage).
  Now: a trailing "_" is stripped; the reference is scaled from the first tag that HAS a 1 m render; a missing render is a red
  MISSING cell, listed on stderr and in <sheet>.ERROR (<sheet>.ok when complete); exit 1 when the newest tag has no cell or a
  reference cell failed. r38/review_tag.sh <crops> <tag> <out>: pairs from the crops, ERROR file + exit 1 on 0 pairs or an empty
  review.md. r37 sheet re-made: assembly/review/game_r37.png (v50 | v51f | v52; v51f has no jaw, v52 no 3 m jaw).
- Blind reviews of r37 at 1 m / 3 m (review/expr_r38_v50, expr_r38_v52): both FAIL. Smile, in both: the eyes don't squint, the
  apples don't lift, the corners barely rise, the opening is a thin flat slit. v50 also gets "clenched": a strip of upper teeth
  plus lower teeth. Jaw, in both: both full rows edge to edge, lips pulled back ("scream / snarl"), the chin not dropped far
  enough. Neutral: stern brows and lids.
STATE: (1) done. NEXT: (2) fit-only fade, (3) inner-edge read (assembly/fx_inner.py) and refit the smile.
- (2) faceshapes.SMILE_FIT_FADE = 0.2 (src): with SMILE_FIT_MASK off, the fitted mouthSmile still fades to 0 AT the lower lids
  over the last 20% of the nose-base -> lower-lid height (the apples kept up to just under the lids); cheekSquint is family "mid"
  (never masked). tests/test_face_shapes.py with HP_SMILE_FIT set: ALL PASS incl. test_gnm_head_shapes (r37: FAIL, 0.77 mm above
  the lids). Log assembly/r38/test.log.
STATE: (2) done (apples measured with the refit below). NEXT: (3).
- (3) the lips' VISIBLE INNER EDGES in the expression fit: assembly/fx_inner.py (fitexpr FX_INNER=1; FX_INNER_LO = the lower lip's
  MediaPipe inner points; FX_INNER_SIGK). On an open photo mouth MediaPipe's inner points 81 82 13 312 311 (and 178 87 14 317 402)
  are read against the LOWEST (highest) projected vertex of the upper (lower) lip's rings in a +-1.5 mm column, not the fixed
  contact vertex (envelope Jacobian). Smile fits: n80 (old) contact read +2 mm, roll 3+ mm low; n80i (upper only) roll -1.4 mm;
  n80j (+ lower) -1.3 / +1.6; n80k (+ sig x0.5) -1.0 / +0.4. Proxy (cal3, soft 0, teeth u-2 f+1): band above the teeth
  4.9 (n80) -> 3.4 (j) -> 2.3 % io (k; ref -0.2); teeth h 7.7 -> 11.9 (ref 14.4); open 14.3 -> 16.4 (ref 13.1); apples
  +2.1 / +3.1 -> +3.9 / +4.8 (ref +10.1 / +1.3, mean 5.7); corners +17.9 / +18.0 -> +19.0 / +18.1 (ref +21.1 / +11.2). k chosen.
- (4) faceshapes.JAW_FIT (env HP_JAW_FIT, src): jawOpen = the fitted jaw photo's lower-face components (fx/jaw_n80i_shape.npy,
  upper inner edge read), the lower row + tongue rigid. Clay (review/fx_jaw_n80i_x1.png): a rounded "O" with the chin down,
  as the photo (the hand jawOpen read "rectangular, lips pulled back, both rows edge to edge" in the blind review).
  Teeth placement, proxy over neutral / smile / jaw (r38/jk): neutral 0 teeth px at every placement; jaw upper run
  [+0.6, +10.1] at u-2 f+1 vs the photo [+0.7, +12.1] (the FITTED jaw no longer contradicts lowering the upper row: r37's hand
  jawOpen did); smile teeth h 11.9 vs 14.4 but share 0.71 vs 0.57 (the opening is taller: 16.4 vs 13.1). Chosen [-2, +1].
- v53 = workspace/ga_tess_v53 (copy of v52, teeth_place upper [-2, +1]; scratch, not approved), exported with HP_SMILE_FIT =
  fx/smile_n80k_shape.npy, HP_JAW_FIT = fx/jaw_n80i_shape.npy, SMILE_FIT_SOFT 0, SMILE_FIT_FADE 0.2 (r38/chain_v53.sh; lip gate
  2.34%, v52 2.48). tests/test_face_shapes.py with both fits: 13/13 pass (r38/test_jaw.log). NICO-TOP batch x53
  (r38/shots_r38.json: neutral / smile / jaw at close-up, mouth close-ups, 1 m and 3 m for all three); r38/post_v53.sh then
  writes review/game_r38.png (ref | v50 | v52 | v53), r38/teeth_x53.txt, the blind review review/expr_r38_v53 (r38/POST_DONE).

## Handover 2026-10-16 r38 (assembly agent, tool-call limit)
- Worktree agent-ad0815704f43e0e00, committed, not pushed. IN FLIGHT at handover: x53 (offload status x53) -> r38/post_v53.sh
  (detached, waits for mh/v53.RENDERED). Tree defaults unchanged without the env vars (HP_SMILE_FIT / HP_JAW_FIT unset = v50).
- New src: faceshapes.SMILE_FIT_FADE (fitted mouthSmile fades to 0 at the lower lids), faceshapes.JAW_FIT / _jaw_fit.
  New scratch: fx_inner.py (+ fitexpr FX_INNER hook), gsheet.py fixed (loud MISSING / .ERROR), r38/review_tag.sh, r38/prox.sh,
  r38/sweep_t.sh (FIT=, HP_JAW_FIT passes through), chain_v53.sh, post_v53.sh.
- NEXT: (1) read review/game_r38.png and review/expr_r38_v53/review.md: does the v53 smile beat v50 at 1 m? Both v50 and v52 FAILED
  the blind review (eyes don't squint, apples flat, corners low, thin slit; jaw "scream": rectangular, both rows). (2) If yes:
  fit smileteeth the same way (FX_INNER=1 FX_INNER_LO=... FX_INNER_SIGK=0.5 FX_NEFF=80, fxlook ... neutral_n80) and wire it
  like SMILE_FIT. (3) Refit jaw with FX_INNER_LO + SIGK 0.5 (jaw_n80i had the upper edge only; its opening 48 vs the photo 55.5
  % io). (4) The smile's band above the teeth is still +2.3 % io (ref -0.2) and the apples +3.9 / +4.8 (ref mean 5.7): the
  prior holds the fit; the agent's finishing pass (or a smaller FX_SD on the mouth PCs) is the next lever. (5) eyes_mouth_lashes
  is 12003 of 5000 triangles in the hero budget (export WARNING, unchanged from earlier rounds?) - check.
- RESULT x53 (review/game_r38.png, review/expr_r38_v53): blind review FAIL. Smile: no eye squint, no apple lift, no fold, corners
  narrow / low, both rows show. Jaw: opens about 60% of the reference, the lips are thick and rolled, the brows don't react.
  My read: the v53 smile arc is clean (no V, a full upper row): it beats v52 and is about even with v50. The v53 jaw is the
  closest yet (an oval, not the "scream") but too shallow. Export teeth rows: smile band +3.4 (v52 +5.3, ref -0.2), teeth h
  11.8 (ref 14.4); jaw open 50.7 (ref 55.5). smileteeth NOT fitted (the smile does not clearly beat v50). Sent to main.

## r39 (2026-10-16, assembly agent): fit weights for squint / apples, budget
- Brows in the photos (scratch assembly/r39/browmeas.py, MediaPipe brow points over the eye corners, % io, minus neutral):
  jawOpen in +1.5 .. -1.4 (no brow raise: within MediaPipe's noise; NOT fitted, and jawOpen exports only lower-face
  components anyway); smile -0 .. -2.6, smileteeth -1 .. -3.1 (a slight brow LOWERING with the squint).
- assembly/fx_weights.py (fitexpr FX_WEIGHTS=1): FX_LID_SIGK (the eye ruler's lid reads' sigma x k: the r38 smile left the
  lids at rms 1.38 sigma) and DIFFERENTIAL MediaPipe reads for regions the solve never reads (cheeks, brow line: 1.9-3.3 mm
  error, biased to an average face): a neutral-photo run at its fitted expression records each point's residual
  (FX_DIFF_REC -> fx/diff_neutral.json, rms 2.0 mm), the expression runs read (o - o_neutral), i.e. the photo's CHANGE
  against the model's, FX_DIFF_SIG mm, FX_DIFF_NEFF 8. There is still no read for the nasolabial fold itself.
- Budget (5): eyes_mouth_lashes 12003 = eyes 567 + teeth 2828 + teeth_lower 2828 + tongue 900 + lashes 4880. What grew:
  the rows' max_triangles 1400 -> 2900 in r20s (ga_tess history 14: decimation was the SUSPECTED source of jagged crowns,
  never confirmed alone); lashes were always 4880 (610 ribbons x 4 segments x 2). The hero's parts: head 25000 + body
  15000 + eyes_mouth_lashes 5000 + accessories 5000 = 50000 (budgets.json; eyes_mouth_lashes basis "thin", no source,
  range 3000-8000). v54 split: lashes segments 2 (2440; LOD1 already ships that), teeth_lower 1400 (mostly hidden; the
  jaw shows it), tongue 700, upper row whole 2828, eyes 567 = 7935: inside the range, over the default. The default
  needs the upper row decimated too (visible in the smile) or fewer lashes (an eye-look change: Joe's call).
- Refits (assembly/r39/fit.sh; every run FX_INNER + lower inner edge, differential cheeks + brow line vs fx/diff_neutral.json):
  smile w1 (inner sig x0.5, lids x0.5, diff 1.5 mm), w2 (x0.35, x0.35, 1.0 mm), jaw w1 (as smile w1). The lid reads stay at
  ~1.3 sigma(old) in mm whatever their weight (rms 1.38 -> 2.65 at x0.5 -> 3.64 at x0.35): the 40-PC prior space cannot
  close her lids further with the mouth held; the apples' differential reads end +1.4 / +2.0 mm short (photo lifts more).
  Proxy (cal3, teeth u-2 f+1, % io; ref smile eyeL -27.9 eyeR -21.9, apples +10.1 / +1.3, corners +21.1 / +11.2, open 13.1,
  teeth share 0.57):
  | fit | eyeL / eyeR | apples L / R | corners L / R | open | teeth h | band above | share |
  | n80k (r38) | -19.4 / -17.9 | +3.9 / +4.8 | +19.0 / +18.1 | 16.4 | 11.9 | 2.3 | 0.71 |
  | n80k + CARRY | -19.1 / -17.0 | +4.1 / +4.9 | +19.0 / +18.0 | 16.5 | 11.9 | 2.4 | 0.70 |
  | w1 + CARRY | -23.4 / -21.0 | +3.9 / +4.5 | +18.4 / +15.7 | 16.7 | 11.9 | 2.3 | 0.60 |
  | w2 + CARRY | -20.5 / -16.9 | +3.6 / +4.2 | +18.5 / +15.4 | 17.3 | 11.9 | 2.6 | 0.56 |
  w1 chosen: the eyes close most of the way to the photo (L -23.4 of -27.9, R -21.0 of -21.9), the lip arc kept (band 2.3).
  SMILE_FIT_CARRY (src) changed the proxy by under 1 % io: the fade had taken little; kept (whole fitted smile at 1).
  Apples did NOT reach the photo (mean +4.2 vs +5.7; the photo's are lopsided L +10 / R +1). No fold read exists.
  Jaw w1 (fxlook 3D): inner gap 36.6 -> 39.3 mm, vermilion upper 5.7 -> 4.6, lower 8.9 -> 7.6 mm (thinner); proxy open
  53.9 % io (teethline; the photo 54.1 on the same read), upper teeth run [-0.1, +12.3] (photo [0, +11.3]). The lower
  inner-edge reads still end +2.3 .. +3.3 mm (the photo's lower lip lower than ours).
- (2) smile lower teeth: not changed this round beyond the fit (open 16.7 vs 13.1: the lower lip still sits low, so the
  lower row shows); teeth_place lower not swept (tool budget).
- v54 = workspace/ga_tess_v54 (v53 + lashes segments 2, teeth_lower max 1400, tongue 700), SFIT fx/smile_w1_shape.npy,
  JFIT fx/jaw_w1_shape.npy; assembly/r39/run_v54.sh: tests -> export (chain_v54) -> NICO-TOP x54 -> post_v54 (game_r39.png,
  ref | v50 | v53 | v54, teeth rows, blind review review/expr_r39_v54).
- TEST FAIL with smile w1: test_gnm_head_shapes, mouthSmileLeft / Right must mirror (corner 54 vs 48 within 8%): w1's
  corner x 8.2 vs 7.0 mm. The differential cheek reads carry the photo's lopsided smile (apples L +10 / R +1) into the fit,
  and the per-side shapes then differ. A per-person asymmetry belongs in the weights, not in Left vs Right shapes; a
  symmetric differential read (mirror-pair averaged) is the fix to try next. Fallback w3 = w1 without the differential
  reads (lids x0.5, inner x0.5 + lower edge): proxy eyes -21.3 / -18.7 (k -19.4 / -17.9, ref -27.9 / -21.9), apples +3.9 /
  +4.7, corners +19.3 / +18.2, open 16.9, band 2.9, share 0.72. Jaw w3 (no diff): gap 39.6, vermilion 4.6 / 7.7 (= w1).
  Tests 13/13 with smile w3 + jaw w1 (r39/test_jaw_w1.log). v54 exported with smile_w3 + jaw_w1 (r39/run_v54b.sh, CHOSEN).
- RESULT x54 (review/game_r39.png ref | v50 | v53 | v54; ONE NICO-TOP batch, done in 10 min; lip gate 2.54%; eyes_mouth_lashes
  7996 of 5000, inside the range 3000-8000; teeth_lower at 1400 has FEWER folds than whole: 26 vs 74 folded edges).
  Render rows (% io; ref | v53 | v54): jaw open 55.5 | 50.7 | 54.0 (LANDED), upper teeth run [+0.7,+12.1] | [+2.9,+12.3] |
  [+1.6,+13.8]; smile eye aperture L/R -25.1/-18.8 | -17.5/-14.1 | -17.7/-13.9 (NOT moved), apples +9.3/-0.5 | +2.3/+4.0 |
  +2.5/+4.0, band above the teeth -0.2 | 3.4 | 3.9, teeth share 0.57 | 0.82 | 0.89.
  BLIND REVIEW (review/expr_r39_v54): FAIL. Smile: eyes don't squint, cheeks flat, no fold, mouth narrow / flat, teeth a
  flat strip (both rows), upper lip too thin. Jaw: no brow / lid reaction (my MediaPipe read of her photo says the brows
  move within +-1.5% io: the reviewer reads her widened eyes as surprise), the opening narrower (~75%) and boxy, a red
  rim round the opening, the interior flat purple-grey, small spread teeth.
  OWN LOOK: v54 jaw is the tallest, closest yet, but still rimmed red and narrow; v54 smile reads as v53. FAIL.
- KEY FINDING: the squint is lost between the proxy and the render, not in the fit. Proxy eyes w3 -21.3 / -18.7 (fit 3D
  -30 / -18.5), render -17.7 / -13.9, v53 and v54 the same in the render though their fits differ. The suspects, in
  order: the lashes' lid-following shapes (lashes.shapes_from_lids) or the export's lid handling (lid seal / lid rings)
  holding the margin; the render camera / lighting reading the aperture differently from cal3. Check: the exported GLB's
  cheekSquint morph deltas at the lower-lid margin vertices against the proxy's, before any more fitting.

## Handover 2026-10-16 r39 (assembly agent, tool-call limit)
- Worktree agent-ad0815704f43e0e00, committed, not pushed. Nothing in flight. Tree defaults unchanged without env vars,
  except the new SMILE_FIT_CARRY (True; only acts with HP_SMILE_FIT).
- New: src faceshapes.SMILE_FIT_CARRY; scratch assembly/fx_weights.py (FX_LID_SIGK, differential reads FX_DIFF_*),
  fx/diff_neutral.json, fx/{smile_w1,smile_w2,smile_w3,jaw_w1,jaw_w3}_shape.npy, r39/ (fit.sh, run_v54b.sh, chain_v54.sh,
  post_v54.sh, browmeas.py). Model copy workspace/ga_tess_v54 (scratch, not approved). tp_k19 untouched.
- NEXT: (1) find where the render loses the squint (GLB cheekSquint deltas at the lid margin vs the proxy); (2) symmetric
  differential cheek reads (average mirror pairs), so the apples can be fitted without breaking the Left/Right mirror test;
  (3) smile lower lip: open 17.3 vs 13.1, so the lower row shows; sweep teeth_place lower / the lower inner-edge weight;
  (4) jaw: the red rim (lip inner-roll paint at stretch) and the opening's width (75%); (5) smileteeth NOT fitted
  (gate (1)-(3) not met); (6) budget: 7996 in the range; reaching the 5000 default needs the upper row decimated or fewer
  lashes (Joe's call); budgets.json eyes_mouth_lashes has no source ("thin").

## r40 (2026-10-16, assembly agent, fresh session): the squint trace, budget derived, the jaw rim measured
- (1) SQUINT TRACE (scratch assembly/r40/: regsplit.py, squint.py, fitid.py, lidpos.py, lidcurve.py, lidcmp.py). Every stage
  read the same way: an ID pass (flatcam.raster, front ortho) of the eyeball's visible top / bottom in its centre columns,
  with the export GLB's eyeballs in every row; mouthSmile L/R + cheekSquint L/R at 1.
  | stage | eyeL change | eyeR change | upper / lower lid travel L (mm) | neutral opening |
  | fit, GNM landmarks 44-46 / 37-41 (fxlook) | -30.0 | -18.5 | | |
  | fit, the export's component split (left_eye + right_eye + lower_face) | -30.0 | -18.5 | | (no loss: the squint is all in the eye comps) |
  | fitted GNM head (tp_k19 posed, read-only), ID pass | -29.0 | -16.0 | -1.25 / +1.25 (R -0.70 / +0.72) | 8.6-8.7 mm |
  | proxy head (v49 dump + faceshapes) | -24.0 | -13.8 | = export, to 0.1 px | 9.9-10.0 mm |
  | exported GLB v54, lashes off | -24.0 | -13.8 | -1.27 / +1.13 (R -0.59 / +0.78) | 9.9-10.0 mm |
  | exported GLB v54, lashes on | -28.4 | -15.9 | | |
  | render x54, MediaPipe (smilerows) | -17.7 | -13.9 | | photo -25.1 / -18.8 |
  FINDING: the carry loses NO lid travel (fit -> GLB within 0.08 mm, test below). The share drops because the export head's
  NEUTRAL opening is 1.3 mm taller than the GNM head's (10.0 vs 8.7 mm: both margins ~0.7 mm further out along the whole eye,
  lidcurve.py; nearest-vertex offsets near the lids only ~0.1 mm mean, max 1.1 mm at the margins: suspected the SDF meshing /
  projection rounding the thin lid margins). The proxy's MediaPipe -21.3 / -18.7 vs the render's -17.7 / -13.9 on the SAME
  geometry is the detector on two renderers (flat proxy vs EEVEE), not a geometry loss: compare MediaPipe only render vs photo.
  The neutral opening difference is an export-vs-approved-head fidelity item (tp_k19's own GNM head is 8.7 mm): NOT changed
  here (approved piece); for the coordinator.
  FIX: faceshapes.SMILE_FIT_EYE_GAIN (env HP_SMILE_FIT_EYE_GAIN, default 1 = as fitted): the fitted smile's eye components x
  gain (the mouth half unchanged). Predicted (ID pass, dump path): gain 1.4 -> -36.7 / -20.5; at the render's MediaPipe/ID ratio
  (L 0.74, R 1.0) gain 1.3 lands near the photo's -25 / -19. v55 uses 1.3.
  TEST: tests/test_face_shapes.py test_exported_squint_matches_fit (HP_SQUINT_GLB + HP_SQUINT_SPEC + HP_SMILE_FIT): per eye,
  the GLB's lid margin travel vs the fitted GNM head's (eye comps x gain), front rays against the GLB's eyeballs, 0.25 mm.
  v54 at gain 1: L upper -1.36 (fit -1.36) lower +1.17 (+1.14), R -0.64 (-0.69) / +0.77 (+0.69): PASS.
STATE: (1) traced and fixed (gain). NEXT: budget, jaw rim, v55.
- BUDGET (coordinator's decision): budgets.json hero eyes_mouth_lashes 5000 "thin" -> 7996 "derived", components recorded
  (eyes 628, teeth 2828 whole, teeth_lower 1400, tongue 700, lashes 2440). The parts' defaults then summed 102996 > the hero's
  LOD0 100000: lod0_triangles 100k -> 103k (note in the file; test_budgets updated). Tongue 700: the x54 1 m jaw review names
  no tongue faceting; kept (not lower: the jaw interior is already a MAJOR, "flat"). NOTE the brief named "lashes 960": the
  export has 2440 (610 ribbons x 2 segments x 2); not cut (eye look change, Joe's call). Ask the coordinator what 960 was.
- (2) JAW RIM measured (r40/rim.py, flat ID pass of jawOpen=1 on the v54 GLB): the rim is the HEAD mesh's lip inner roll,
  not the sock. Head pixels within 6 px of the opening: 1956 facing edge-on / away (ny <= 0.7), albedo 104,61,54 .. 133,83,73
  (darker and redder than the lip 8-16 px out: 145,97,83), their triangles stretched 1.55-1.61x median (p90 2.0-2.2x) by the
  jaw; the sock seen inside the opening is only 195 px (59,27,26). So: the lips' inner roll turns toward the camera and its
  texture stretches 1.6x (the streaks in the close-up). Levers (untested): less roll-out in the fitted jawOpen (the lower
  inner-edge reads end 2.3-3.3 mm short), or the inner roll's albedo graded to the lip's. Width / box shape and the flat
  interior: not addressed this round.
- v55 = exp/ga_tess_v55 (model ga_tess_v54 re-exported, no spec change) with HP_SMILE_FIT_EYE_GAIN 1.3 (+ smile_w3, jaw_w1,
  SOFT 0; assembly/r40/run_v55.sh). tests/test_face_shapes.py 13/13 + the new test (skips without its env); on the v55 GLB:
  L upper -1.83 (fit -1.81) lower +1.56 (+1.49), R -0.88 (-0.91) / +1.03 (+0.89) mm: PASS. ID pass -32.9 / -18.1 (lashes off).
  Export WARNING: eyes_mouth_lashes 8032 of 7996 (the eyes mesh came out 427 verts vs 416: +36 triangles; not chased).
- RESULT x55 (ONE NICO-TOP batch, 17 min; review/game_r40.png ref | v53 | v54 | v55; rows r40/rows_x55.txt, MediaPipe, % io):
  | item | photo | v54 | v55 |
  | smile eye aperture L / R | -25.1 / -18.8 | -17.7 / -13.9 | -21.6 / -17.8 |
  | apples L / R | +9.3 / -0.5 | +2.5 / +4.0 | +2.6 / +4.6 |
  | smile open / band above teeth | 13.1 / -0.2 | 17.3 / +3.9 | 16.9 / +3.5 |
  | jaw open | 55.5 | 54.0 | 53.0 |
  The squint moved where the gain put it (R at the photo, L 86%). BLIND REVIEW (review/expr_r40_v55): FAIL. Smile: "the eyes
  don't take part" (lower lids flat, no crescent, no crinkle at the outer corners), cheeks don't lift / bunch, no full fold
  from the nose wing, the opening a flat slot with both rows (a white strip). Neutral: stern low flat brows, heavy lids,
  eyes ~15-20% smaller and rounder than the photo's almond. Jaw: boxy opening, both full rows, no tongue read, tense brows.
  OWN LOOK (ref | v54 | v55 at 1 m): v55's eyes are a little narrower than v54's, but still read open and staring next to the
  photo's crescent eyes; the photo's squint is the lower lid's SHAPE (raised and curved up under the iris, a soft bulge under
  it) more than the aperture number. FAIL.

## Handover 2026-10-16 r40 (assembly agent, tool-call limit)
- Worktree agent-ad0815704f43e0e00, committed, not pushed. Nothing in flight.
- New src: faceshapes.SMILE_FIT_EYE_GAIN (env HP_SMILE_FIT_EYE_GAIN, default 1); tests test_exported_squint_matches_fit
  (+ _lid_edges); budgets.json eyes_mouth_lashes derived 7996 with components, hero lod0 103k (test_budgets updated).
  Scratch assembly/r40/: squint.py, regsplit.py, fitid.py, lidpos.py, lidcurve.py, lidcmp.py, rim.py, run_v55.sh.
- KEY FINDINGS: (a) the squint is NOT lost in the export carry (lid travel within 0.15 mm, now a test). (b) The export
  head's neutral eye opening is 10.0 mm against tp_k19's GNM head 8.7 mm (both margins ~0.7 mm out along the whole eye):
  a fidelity gap between the export and the APPROVED head, which also shows in the neutral review ("eyes smaller, rounder,
  heavy socket" is about shape, though; check which way): for the coordinator; probably the SDF meshing / projection rounding
  the lid margins. (c) The aperture number alone does not make the reviewer read a squint: the lower lid's shape is the item.
  (d) The jaw's red rim = the lips' inner roll on the head mesh, stretched 1.6x and seen edge-on (not the sock).
- NEXT: (1) a measured item for the lower lid's SHAPE in the smile (the margin's curvature under the iris and the bulge
  below it, photo vs render) before more gain; (2) trace the neutral opening (10.0 vs 8.7 mm): which export step moves the
  margins (dump the head after each step); (3) jaw: less inner-roll roll-out (lower inner-edge reads end 2.3-3.3 mm short)
  or grade the roll's albedo to the lip's; the boxy shape and both rows; (4) smile lower lip covering the lower row
  (open 16.9 vs 13.1); (5) smileteeth: not fitted; (6) budget: eyes 8032 vs 7996 (+36), and the brief's "lashes 960" vs the
  export's 2440: ask the coordinator.

## Handover 2026-10-16 r41 (assembly agent, tool-call limit)
- Worktree agent-ad0815704f43e0e00 (origin/main merged), committed, not pushed. Nothing in flight.
- (1) EYE OPENING FIDELITY FIXED. Trace (scratch assembly/r41/: trace.py, iso.py, who.py, faces.py, fixtest.py): the cage
  (base.surface quads) equals tp_k19's GNM mesh (0.01 mm); `retopo.base_quads` drops every vertex onto the body field with
  surface.newton, and the field (CC'd + smoothed) rounds the lids: the eye regions' EXTERIOR skin moved up to 1.0 mm (upper lid
  +0.44 up / +0.27 back on average). The lids' insides were already kept (inner) and the margin ring itself moved only 0.07 mm,
  but the skin just above / below opened the eye. Swap test: GLB faces with source positions = 8.56 / 8.61 mm (source),
  source faces with dropped positions = 9.85 / 9.89 (export): positions, not faces. FIX `retopo.LID_KEEP` / `lid_keep`: GNM's
  expression_basis_left_eye / _right_eye vertices keep the cage (the source) position, fading over LID_KEEP_RINGS = 3 rings.
  Test `test_exported_neutral_eye_opening_matches_source` (9 columns per eye, 0.2 mm; env HP_SQUINT_GLB + HP_SQUINT_SPEC):
  v55 FAILS (upper +0.35..+0.80, lower -0.50..-0.80 mm), v56 PASSES (all columns within 0.05 mm, opening 8.80 = 8.80).
  Squint test at SMILE_FIT_EYE_GAIN 1.0: lid travel = fit (L -1.36/+1.14, R -0.69/+0.69 mm), neutral 8.67 / 8.69 (fit 8.68 / 8.69).
- v56 = exp/ga_tess_v56 (model ga_tess_v54, smile_w3 + jaw_w1, GAIN 1.0, LID_KEEP). Tests face_shapes / headbody / onemesh /
  budgets all ok. NICO-TOP x56 (one batch); sheet review/game_r41.png (ref | v54 | v55 | v56, 1 m + 3 m); blind review
  review/expr_r41_v56: FAIL. Eyes: neutral now "slightly narrower than the reference" (MINOR: that is the APPROVED head's
  opening now); smile squint MINOR "close but from the upper lid". MediaPipe smile eye L/R -20.5 / -16.0 (photo -25.1 / -18.8).
- REGRESSION TO FIX: lip gate 2.69% -> 4.27% (lips' front texels astray; 6022 -> 5674 texels). Bisected: v56b = v56 with
  retopo.LID_KEEP=0 gives 2.69% again, so LID_KEEP causes it, although the kept region ends at z 1.491 (>1 cm above the lips):
  probably the uv charts / atlas packing change with the lids' geometry. Not visible on the 1 m sheet; check a lip close-up.
- (2) LOWER LID SHAPE, measured item r41/lidshape.py (MediaPipe lower margin in the eye's corner-chord frame, % chord, centre
  lift and parabola k; k > 0 = cupped): photo smile centre -6.5 / -8.2, k 24 / 30 (change from neutral +4.7 / +4.5, k -17);
  v55 -11.6 / -12.3, k 44 / 46; v56 -10.6 / -11.3, k 40 / 42 (change +3.2 / +2.4, k -12 / -9). The lower lid rises 60% of
  the photo's and stays cupped. Refits in flight became done: smile w4 (lid reads x0.25) lid rms 5.01 sig = ~1.25 mm, w3's
  2.64 x 0.5 = 1.32 mm: the lid reads barely move (prior / GNM space); fxlook eyeL -29.8 / eyeR -18.8. w5 (x0.15) in
  r41/fit_smile_w5.log. NEXT: a lower-lid-specific read (the lower margin's centre lift + curvature) or GNM's lower-lid
  components freed from the prior; judge w4/w5 with lidshape on proxies before any export.
- (3) JAW not changed this round (open 53.1 vs 55.5; review MAJOR boxy + thick red rim, both rows). NEXT as r40: tuck the
  inner rolls back under jawOpen (rolls behind the lip edge exist vertically; add a backward / inward curl for jawOpen).
- BUDGET: lashes stay ribbon (2440); drops to ~960 when the lashes CARDS branch (worktree agent-ac021191615c62c32: 896 cards +
  64-tri lash line) merges. eyes 8032 vs 7996 (+36): noted, fine.
- STATE: export head = approved head at the lids (tested); GAIN 1.0. NEXT: lip gate regression (LID_KEEP), lower-lid shape, jaw rim.

## r42 (2026-10-16, assembly agent, fresh session): the whole face kept, the bake not projecting it, jaw levers, lower-lid read
- (1) PER-REGION FIDELITY (scratch assembly/r42/fid.py <model> <src> [glb ...]: (a) cage vertices by GNM region, cage -> dropped
  onto the field; (b) feature items on GNM-indexed vertices; (c) each GLB vs the source by front depth rays per region).
  The drop (retopo.base_quads' newton onto the SMOOTHED field) moved, with LID_KEEP only (v56): lips' skin mean 1.15 / p95 3.6 /
  max 5.8 mm (upper), 1.17 / 4.4 / 6.6 (lower); lip regions 0.26-0.29 mean, max 3.6-5.3; nose 0.12 (max 0.75); chin 0.15.
  Items, dropped - source: lower vermilion height -3.55 mm at the centre (12.88 -> 9.33), -2.8 / -1.8 at +-15%, -1.0 / -1.7
  at +-30%; upper -1.5 centre, -1.3 at +-15%; mouth width +0.40; corners 0.24-0.38 down; nose tip 0.34 back; philtrum
  0.16 shallower. "Neutral lips THIN" (r41 review) = this fidelity bug, as the coordinator read it.
  GLB front depth vs source (v56): lips mean 0.26-0.34 / p95 0.66-0.93 mm, nose 0.26 / 0.52, chin 0.38 / 0.60; orbital 0.02.
- FIX retopo.FACE_KEEP (+ FACE_KEEP_GROUPS: expression_basis_left_eye / _right_eye / _mouth_nose_ears; face_keep(), lid_keep()
  now its eyes-only case), fading over LID_KEEP_RINGS 3. With it every region's vertices and every item are the cage's (0.000
  mm; nose max 0.011). Test test_face_keep_regions_match_source (env HP_FACE_KEEP_SPEC = a one-mesh model's spec.json, e.g.
  ga_tess_v54's): regions max < 0.1 mm and items within 0.1 mm; FAILS without FACE_KEEP (upper lip 3.6 mm).
- (3) LIP GATE cause (read, not yet measured on an export): asset.bake projects every texel onto the part's field, and with the
  face kept the low poly at the lips stands up to 6.6 mm off that (smoothed) field: lip texels went astray (> 6 voxels) and the
  rest took the smoothed lips' normals. LID_KEEP raised it 2.69 -> 4.27% the same way, presumably through the fade rings / the
  lips' charts. FIX asset.face_keep_paint: a per-corner "keep" weight (retopo.face_keep on the part's own faces, GNM ids from
  topology_<part>.npz); bake() blends the projection out by it (kept texels = the low poly's own position + normal). The tissue
  modifiers (skin.folds) / strokes on a kept face would be lost by this; ga_tess has none (note for heads that do).
- (5) JAW: faceshapes.JAW_FIT_GAIN (HP_JAW_FIT_GAIN; 1.045 = 55.5 / 53.1) and JAW_ROLL_TUCK (HP_JAW_ROLL_TUCK, share of the
  mouth's width at full jawOpen, x each roll vertex's opening travel / 20% width): the wet-lip rings (skin_features.
  inner_lip_values = 1, 174 vertices; GNM's lip groups are exterior only) pushed back level toward the sock. v57: 0.05 (2.5 mm).
  Width not addressed.
- (4) LOWER LID: differential lower-lid reads (fx_weights FX_DIFF_MP = MediaPipe's 7 lower-margin points per eye, FX_DIFF_FEATS
  "eye contour", neutral recorded at diff_neutral_lowlid.json; r42/fit_lid.sh): w6 (sig 0.6) / w7 (0.35). r42/pick.py measures
  the lower lid on the fxlook sheets (photo smile | neutral clay | fitted clay): w3 / w4 / w6 / w7 all within ~1 % chord of the
  photo's ABSOLUTE smile shape, but the fit's CHANGE from neutral is +2.4..+3.0 % centre, k -9..-11, against the photo's +4.7
  / +4.5, k -17: the fit lifts the lower lid ~60%, the reads barely move it (w6 lip rms rose 0.81 -> 1.78: worse). v56's
  render change (+3.2 / +2.4) = the fit's: the export carries it. So the remaining gap is the FIT (GNM space + prior), not the
  export. NEXT lever (a hand pass on the solve, measured target): the smile's lower-lid travel x ~1.7 (4.6 / 2.7) in the
  export's cheekSquint (lower margin rings only), judged by lidshape on the render.
- v57 = exp/ga_tess_v57 (r42/run_v57.sh: FACE_KEEP + keep paint, smile = pick's best (w4), jaw gain 1.045 + tuck 0.05).
- v57 RESULTS (smile w4, jaw gain 1.045, tuck OFF: with JAW_ROLL_TUCK 0.05 test_onemesh test_face_shapes_by_index_on_own_quads
  FAILS, jawOpen uneven 0.53 > UNEVEN_LIMIT: the tucked rings step against their neighbours; needs a fade over rings before use).
  Tests (face_shapes incl. the new region test, headbody, onemesh, budgets) ok; squint + neutral-opening tests PASS on the v57 GLB
  (opening 8.80 = 8.80). LIP GATE 0.00% of 7571 front texels (was 2.69 / 4.27): kept texels are no longer projected, so the
  gate now only watches the fade rings and beyond: it can't fail on the kept lips any more (by construction, not a cleaner bake).
  GLB front depth vs tp_k19 (fid.py (c)), v56 -> v57, mean / p95 mm: upper lip 0.26/0.66 -> 0.14/0.44, lower lip 0.34/0.93 ->
  0.24/0.65, lip regions 0.20-0.21 -> 0.15-0.19, nose 0.26/0.52 -> 0.07/0.18, chin 0.38 -> 0.25, orbital 0.02. NOT within
  0.1 mm at the lips / chin in the GLB (the cage is exact): what is left comes after base_quads (the export's neutral seals the
  lips' slit, faceshapes; the head/body seam), not measured apart yet.
- LID RIM (coordinator, routed from skin; projskin/cut/r7/lidx.py, L minus cheek, image-left / image-right eye): photo -20.2 /
  -21.0; x52 render (no lashes file failed detection; x_neutral_front) +2.5 / +9.0; FLAT BASECOLOR (r42/rimchk.py: albedo only,
  no light / AO) v52 -6.8 / -4.4, v56 -5.8 / -2.8, v57 -6.2 / -2.9. So (a) the baked basecolor keeps only ~1/3 of the rim's
  darkening on both eyes and is 2.4-3.4 L lighter on the image-right eye (the reversal starts in the bake, small); (b) the render
  adds +9 / +12 L on top (lighting / AO, larger image-right): both lids end lighter than the cheek. FACE_KEEP didn't move it.
  NEXT: the gate albedo at the same rims (flat) to see if the bake loses it (projection / scene sample), and x52's key light.
- STATE: v57 exported, NICO-TOP x57 done; r42/run_v57.sh continues to sheet review/game_r42.png + review/expr_r42_v57 (not read).

## Handover 2026-10-16 r42 (assembly agent, tool-call limit)
- Worktree agent-ad0815704f43e0e00 (origin/main merged), committed, not pushed. In flight: assembly/r42/run_v57.sh's tail (gsheet
  -> review/game_r42.png, rows_x57.txt, lidshape_x57.txt, review/expr_r42_v57; r42/POST_DONE says done / which step failed).
- NEXT: (1) read the v57 sheet + blind review, lidshape_x57 (lower lid); (2) the lips' 0.14-0.24 mm GLB residual: split by
  export step; (3) JAW_ROLL_TUCK with a ring fade (unevenness test); jaw width; (4) the smile's lower-lid travel x ~1.7 in the
  export (the fit lifts 60% of the photo's change); (5) lid rim: gate albedo vs our basecolor, x52 key light.

## r43 (2026-10-16, assembly agent, fresh session): the lip residual is the neutral's close; lower-lid gain; roll tuck that passes
- (1) LIP / CHIN RESIDUAL SPLIT BY STEP (scratch assembly/r43/split.py <model> <shapes dump> <glb>; dump = v57's export again
  with HP_SHAPES_DUMP, fast/v57dump.pkl): per region, cage (GNM ids) vs (1) the low poly as faceshapes.apply gets it, (2) + the
  neutral (face.neutral), (3) the GLB (nearest). (1) and (3) are 0.00 mm everywhere (max 0.01 at the nose): base_quads +
  FACE_KEEP, the sock, the topology write / read-back, and the GLB write keep the approved shape exactly. ALL of the residual is
  (2), GnmFace.neutral, which closes the mouth: upper lip mean 1.32 / p95 3.94 / max 5.42 mm, lower 1.44 / 5.10 / 6.06, lip
  regions 0.58-0.68, chin 0.34 (0.55 p95), cheek 0.28, nose 0.06, orbital 0.01. That is not a lost step: tp_k19's lips are
  PARTED (r43/gap.py: inner-lip landmark gaps 1.32 / 0.64 / 1.03 mm), and the game neutral seals them (the basis close moves the
  outer lips ~0.4 mm and the chin 0.3 mm (jaw up); lips_meet / rolls_behind do the rest at the inner rolls, hidden from the
  front: front depth only 0.14-0.24 mm). Lever if Joe wants the parted approved lips kept: hold the outer lips / chin harder in
  the close (`_solve(..., hold=0.2)`), the seal on the rolls only. Not changed this round (a design call: sealed vs parted neutral).
- (2) LOWER LID: faceshapes.SMILE_LOWLID_GAIN (HP_SMILE_LOWLID_GAIN): the fitted smile's eye carry x (1 + (g-1) w), w = the lower
  lid from 1 mm above its margin (lm68 corners + lower points) to 3 mm below, fading to 0 at 2 above / 7 below (30 mm chord),
  x sin(pi t) along the chord (centre most: less cupped). Proxy r43/lidgain.py (lm68, front projection, % chord): change
  neutral -> smile at g 1.0 +3.88 / +2.51, 1.7 +5.77 / +3.79, 2.0 +6.58 / +4.35; upper lid unchanged at every g (lever moves its
  row). Renders measured +3.0 / +2.5 against the photo's +4.7 / +4.5: v58 uses 1.9 (~x1.64). Why the FIT lifts only 60% was not
  reopened (r42: the reads barely move it; this is the agent's hand pass on the solve).
- (4) JAW: JAW_ROLL_TUCK's unevenness was ONE vertex (r43/uneven_dbg.py on test_onemesh's head: GNM 10766, lower lip, iv 1):
  _clear_teeth pushed it back out of the lower teeth after the tuck, 1.75 mm proud of its tucked ring (0.39 mm already untucked).
  Feathering over GNM's quads didn't change it (0.638 at 4 and 12 rounds). FIX: the tuck is 1 on every roll vertex, smoothed in
  space (Gaussian JAW_TUCK_FADE x 0.5 mm, default 3), and gives way where the teeth stop it (8 passes: the push-out _clear_teeth
  would make is taken off the tuck, smoothed again): tuck 0.05 -> uneven 0.181 (fade 3; 0.191 fade 4; tuck 0.03 0.144) < 0.2.
  JAW_WIDEN lever added (lips + sock stretched from the mouth's middle; proxy r43/jawprox.py: 0.06 -> inner width 47.2 -> 50.0
  mm) but left OFF: r43/mouthw.py (MediaPipe, % io) jaw open: photo outer w 89.8 / inner 82.5 / inner h 55.8; x57 86.8 / 79.2 /
  55.4; but the NEUTRAL is narrower too (photo 79.9, x57 74.5: the approved base face), and relative to its own neutral our
  opening already widens more (x1.165 vs the photo's x1.124). Widening would make up for the base face (another stage). Vermilion
  thickness by landmarks matches (jaw: upper 9.3 vs 9.5, lower 15.2 vs 15.2): the "thick everted ring" is the wet inner roll
  showing in front, which the tuck targets.
- LIGHTING (the reviewer's "harsh side light, strong shadow on the neck"): the expression sheets render in blender_game's game
  rig: a plain grey world (0.8) + three SUNS, key 3.0 from the head's right-front-above (-1, -1.2, 1.4) with a 2 deg angle (hard
  shadow maps, 0.2 mm texels), fill 1.0 (10 deg), back 1.5. The approved head sheet (spikes/reruns/jsheet.py, stage.shoot) is lit
  with the PHOTO's fitted lighting (stage.photo_light per view). So the export preview is NOT judged in the light the head was
  approved in: hard 3:1 side key vs the photo's soft light. This alone can read as "a different person" (brow / nose-bridge
  shadows, longer face) and puts the neck shadow there; it may also be part of the lid-rim +9 / +12 L (key from one side). NEXT
  (export / preview question, mine): render the gate's front views ALSO under stage.photo_light (or the approved sheet's own setup)
  so the blind review compares like with like; keep the game rig for the 1 m / 3 m game reads.
- (3) cheeks and (5) the rim's bake asymmetry: not done this round (tool budget).
- v58 = exp/ga_tess_v58 (r43/run_v58.sh: v57 + SMILE_LOWLID_GAIN 1.9 + JAW_ROLL_TUCK 0.05 fade 3; shapes dump fast/v58dump.pkl).
  Tests ok (face_shapes, headbody, onemesh incl. jawOpen evenness, budgets); squint test updated for the gain: L lower +2.11 vs fit
  1.07 x 1.9, R +1.22 vs 0.61 x 1.9 PASS; neutral opening 8.80 = 8.80 PASS; lip gate 0.00%. split_v58 = v57's (every mesh step
  exact, the residual is the neutral's close). NICO-TOP x58 (one batch, 10 min); sheet review/game_r43.png (ref | v56 | v57 | v58).
  LOWER LID (lidshape, change neutral -> smile, % chord): v58 +4.6 / +3.7, k -17.3 / -13.9 (photo +4.7 / +4.5, k -17.5 / -16.4;
  v57 +3.0 / +2.5): matched on one eye, 82% on the other. But smilerows' eye closure now OVERSHOOTS: -28.3 / -23.4 vs photo
  -25.1 / -18.8 (v57 -19.7 / -16.3): the upper lid is the approved head's (lower opening); next try 1.6. Smile width read 39.6
  (v57 43.3, photo 42.6): unexplained (the lower-face carry is unchanged), check before trusting.
  JAW (mouthw, % io): inner h 56.5 (photo 55.8), inner w 80.1 (82.5), vermilion up 8.4 / lo 14.6 (photo 9.5 / 15.2; v57 9.3 / 15.2):
  the tuck thinned them past the photo. Review flipped from "thick everted ring" (v57) to "thin and stretched" (v58): next tuck ~0.025.
  BLIND REVIEW review/expr_r43_v58: FAIL. Smile: cheeks don't lift (MAJOR, unchanged), mouth ~10% narrower and grin-like, teeth
  show with a dark gap under them. Neutral: eyes narrow / hooded (the approved head's opening: another stage). Jaw: boxy opening,
  lips thin and stretched. OTHER: hair; LIGHTING named as a MAJOR by the reviewer (hard cast shadow down the nose, neck, shoulder):
  confirms the lighting note above. My look: v58's smile squints a little more; cheeks flat; the jaw rim is less red than v57.

## Handover 2026-10-16 r43 (assembly agent, tool-call limit)
- Worktree agent-ad0815704f43e0e00 (origin/main merged), committed, not pushed. Nothing in flight.
- NEXT: (1) the gate's front views ALSO under the approved head sheet's light (stage.photo_light), so the review compares like with
  like (the game rig's hard 3:1 key stays for the 1 m / 3 m reads); (2) SMILE_LOWLID_GAIN ~1.6 (closure overshoots at 1.9) and the
  tuck ~0.025; (3) cheeks: the apple lift and the nasolabial fold, measured (cheekprof, fold depth) against the photo, fit prior or
  carry, proven on the dump (fast/v58dump.pkl + spikes/game_ready/shapesfast.py) before an export; (4) the rim's bake asymmetry;
  (5) sealed vs parted neutral (tp_k19's lips part 0.6-1.3 mm): a design question for Joe / coordinator.

## r44 (2026-10-16, assembly agent, fresh session): parted neutral, likeness light, lid gain 1.6, tuck 0.025, fold carry, rim
- (a) NEUTRAL LIPS PARTED (coordinator: keep them as the approved head has them; sealing is mouthClose's / the visemes').
  faceshapes.NEUTRAL_PARTED (HP_NEUTRAL_PARTED, default ON; one mesh own quads only, a kit face keeps its sealed neutral):
  GnmFace.neutral computes the old close (basis close + lips_meet + corners + rolls_behind) but returns 0 and stores it; the
  close is ADDED to mouthClose (displacements). "meet" is None (nothing to take back); the teeth wrap uses the open rest; the
  seam-showing check reads mouthClose instead of the rest. Proxy on v58's dump (scratch assembly/r44/parted.py): neutral 0.000 mm
  off the cage in every region (r43/split.py column (2)+(1)); seam showing rest 3.23 mm^2 (parted), mouthClose 0.0, open+close
  268.9 (268.6 with the sealed rest: same), mouthClose uneven 0.085. Teeth / tongue get no close share at mouthClose (small).
- (b) LIGHT: blender_game shots take their own "lighting" (light_rig: blender_scene's format incl. window highlights; the game rig
  when absent). Likeness views (pl_* shots: front close-ups + 1 m / 3 m) render under stage.photo_light("tp_k19") (scratch
  r44/photo_light_tp_k19.json), game reads under the game rig; sheet = both, stacked and labelled (r44/stack.py). Rule in
  docs/notes/gates.md "Game distance" (pushed on main c3167d49). Local check r44/lt/cmp.png: the photo light reads soft and even.
- (2) LOWER LID gain 1.6 (proxy r43/lidgain.py, lm68 % chord, change neutral -> smile): 1.0 +3.88 / +2.51, 1.6 +5.50 / +3.61, 1.9
  +6.31 / +4.16; upper lid unchanged. Linear from the renders (v57 g1.0 -> v58 g1.9): closure at 1.6 ~ -25.4 / -21.0 (photo
  -25.1 / -18.8), lift ~ +4.1 / +3.3 (photo +4.7 / +4.5). The right eye closes too much while lifting too little: the approved
  head's lower neutral opening (another stage).
- (3) TUCK 0.025: no cheap mesh proxy worked (r44/tuckprox.py's front z-buffer of the rolls read ~1 mm everywhere: frame or
  label fault, not trusted). Renders: tuck 0 -> 9.3 / 15.2 % io, 0.05 -> 8.4 / 14.6 (photo 9.5 / 15.2): 0.025 should land ~8.85 /
  14.9, i.e. still under the photo's upper vermilion (tuck 0 is closest by that row; the tuck is for the "thick everted ring").
  jawOpen uneven (r44 proxy) 0.057 at 0.025.
- (4) CHEEKS: faceshapes.SMILE_FIT_FOLD (HP_SMILE_FIT_FOLD, default 0): the hand smile's nasolabial fold + cheek mass (SMILE_FOLD,
  CHEEK_LIFT) carried on the fitted smile, without its corner lift. Proxy r44/foldprox.py (smile L on v58's dump): apple up 3.31
  / 5.59 / 7.11 mm and fold depth -0.96 / -2.11 / -2.89 mm at 0 / 0.6 / 1.0; the corner's move unchanged; uneven 0.094 -> 0.098.
  v59 uses 0.6.
- (5) RIM: flat albedo of the export's SOURCE stage (r44/gatealb.py ga_tess_v54: stage.shoot flat, hair off) vs the v58 GLB's
  basecolor (r42/rimchk.py), lidx (r44/lidx.py = projskin's with eyetone.EYE; reference band now upper cheek 21-26 mm under the
  margin), L minus cheek, eye R (image left) / eye L (image right):
  | | rim | lid band | socket |
  | photo | -20.2 / -21.0 | -17.3 / -6.9 | -8.9 / -1.6 |
  | source stage flat (ga_tess_v54) | -8.0 / -6.5 | -13.8 / -12.1 | -13.1 / -11.1 |
  | v58 GLB basecolor | -6.2 / -2.9 | -5.9 / -3.6 | -6.2 / -3.2 |
  (tp_k19's stage flat: all ~0: its skin has no projected stack; the export's skin is ga_tess_v54's projskin stack.) So the BAKE
  loses about half of the source's eye-region darkening (lid band -13.8 -> -5.9) and makes it asymmetric (image-right eye loses
  more: rim -6.5 -> -2.9), while the source is near symmetric (1.5 L). Not a framing / tone fault (ratios differ by zone). NOT
  FIXED this round: next, sample the baked "color" pass at the eye-region texels against the stage's colour at the same surface
  points (kept texels use the low poly's position: the stage mesh is the CC'd field, up to 1 mm off at the lids; the stack image
  is uv-wrapped, so a uv / chart mismatch between stage mesh and low poly at the lids would smear it).
- v59 = exp/ga_tess_v59 (scratch r44/run_v59.sh: v58 + NEUTRAL_PARTED + lid gain 1.6 + tuck 0.025 + SMILE_FIT_FOLD 0.6). ONE
  NICO-TOP batch x59: j0 = v59 (game-rig shots + pl_* photo-lit), j1 = v58 pl_* only (before, same light). Sheet review/game_r44.png
  (LIKENESS block over GAME block), blind reviews review/expr_r44_v59_photo + _game, rows r44/rows_x59.txt, lidshape_x59,
  cheekprof_x59, rim_v59, split_v59 (lips / chin vs the cage), squint_test.log. r44/POST_DONE = done or the failed step.
- v59 RESULTS SO FAR: tests (face_shapes, headbody, onemesh, budgets) ok; lip gate 0.00% of 7571; neutral eye opening 8.80 = 8.80
  PASS (squint_test.log); FIDELITY (r44/split_v59.txt): upper / lower lip, lip regions, chin: low poly, neutral and GLB all 0.00 mm
  off the approved cage (mean / p95 / max; nose max 0.01): the export reproduces tp_k19's parted lips exactly (target ~0.1 mm).
  NICO-TOP x59 j0 + j1 QUEUED (not started after ~10 min) when this session hit its tool-call limit.

## Handover 2026-10-16 r44 (assembly agent, tool-call limit)
- Worktree agent-ad0815704f43e0e00, committed, not pushed (gates.md rule pushed on main c3167d49). IN FLIGHT: scratch
  assembly/r44/run_v59.sh (detached): waits on `offload wait x59`, then sheet review/game_r44.png (LIKENESS block under the photo
  light over GAME block under the game rig, ref | v58 | v59), rows_x59 / lidshape_x59 / cheekprof_x59 / rim_v59, blind reviews
  review/expr_r44_v59_photo and _game. r44/POST_DONE says "done" or the failed step. Don't resubmit while it waits.
- NEXT: (1) read the sheet + both reviews, judge it yourself first (look-first), then report to the coordinator (FAIL as FAIL);
  check the lower lid (closure vs -25.1 / -18.8, lift vs +4.7 / +4.5), the vermilion at tuck 0.025 (expected ~8.85 / 14.9 vs 9.5
  / 15.2: if the review no longer calls the ring thick, tuck 0 may be the honest pick), the apples / fold (cheekprof, review);
  (2) the rim bake fix (r44 (5): the bake halves the source's eye-region darkening and makes it asymmetric; compare the baked
  colour at eye-region texels with the stage colour at the same surface points); (3) mouthClose now carries the seal: check a
  viseme / mouthClose render once (proxy says seam 0.0 mm^2).

## r45 (2026-10-16, assembly agent, fresh session): v59 read, the rim "bake loss" was the measurement, cheek levers don't shade
- v59 REVIEWS (both FAIL). Expression MAJORs, game rig: v58 7 (smile 3+1, neutral 1, jaw 2) -> v59 5 (smile 2+1, neutral 0, jaw
  1+1); photo light (first time, no v58 baseline under it): 12 (smile 4+1, neutral 2+1, jaw 3+1). Both still call the eyes / cheeks
  "not taking part" in the smile, and the jaw a thick red ring. The photo reviewer's neutral MAJORs (pursed lips, small eyes)
  are on geometry that is 0.00 mm off tp_k19 (r44 split_v59): skin colour / light, or tp_k19 itself (approved, not ours).
- ROWS v59 (r44/rows_x59, lidshape_x59, cheekprof_x59; v58 -> v59 vs photo): eye aperture change -26.2 / -22.0 -> -25.2 / -20.5
  (photo -25.1 / -18.8: matched); lower lid lift +3.2 / +2.6 (photo +4.7 / +4.5) and its flattening k -11.7 / -9.8 (photo -17.5 /
  -16.4): the photo's lower lid goes STRAIGHT, ours stays a U. Apple rise (MediaPipe) +0.8 / +1.7 -> +1.2 / +1.8 (photo +9.3 /
  -0.5). Fold dip -0.059 -> -0.044, dip-to-peak 0.140 -> 0.123 (photo -0.211, 0.339). Jaw upper vermilion 8.9 (photo 9.5).
- (1) THE CARRY REACHES THE GLB (r45/glbfold.py, the proxy's points read on the GLB's own targets): apple up +3.61 -> +5.89 mm,
  out +1.22 -> +1.72, fold -0.94 -> -2.10 mm (proxy +5.59 / -2.11), corner unchanged. And the RENDER doesn't lose it: a Lambert
  proxy under the photo light from the GLB targets (r45/shadeprox.py) gives fold dip-to-peak 0.122 (v58) -> 0.125 (v59), like
  the render. So the levers move the mesh but not the shading: a 2 mm crease 2.2 mm wide and an apple slid UP (tangential)
  read as nothing under a soft high key. On the dump (r45/shadedump.py, same proxy): SMILE_FIT_FOLD 0 / 1.0, CHEEK_LIFT out 1 ->
  3 / 4 mm, lift 4 -> 6 mm all give dip-to-peak 0.11-0.13 and a cheek that DARKENS everywhere on the profile (peak -0.02 / -0.03,
  photo +0.13): the fitted smile tilts the cheek away from the light. NOT FIXED: the cheek needs a form whose upper face turns
  toward the light (a ball with its top under the lid, the fold's lip overhanging), not more of the same Gaussian. No lever
  proved, so v60 keeps v59's cheeks.
- (2) RIM / LID "BAKE LOSS" = MEASUREMENT FAULT: r44 read the GLB's basecolor alone; the crease line + the lid's share of the
  occlusion live in <atlas>_blink_multiply.png (skin.md BLINK), which the engine (and blender_game) multiplies in. Basecolor x
  blink (r45/rimchk2.py, sRGB decoded, multiplied linear) against the source stage flat, L minus cheek, eye R / eye L:
  | | rim | lid band | socket |
  | source stage flat (ga_tess_v54) | -8.0 / -6.5 | -13.8 / -12.1 | -13.1 / -11.1 |
  | v59 basecolor alone (r44's read) | -5.8 / -3.2 | -6.0 / -3.9 | -6.1 / -3.5 |
  | v59 basecolor x blink (engine) | -4.6 / -3.3 | -12.7 / -12.3 | -11.7 / -9.2 |
  Lid band within 1.1 / 0.2 L of the source, L/R gap 0.4 (source 1.7): PASS. The bake made no asymmetry (the basecolor-only
  asymmetry was the blink map's). The RIM (0.5-1.5 mm above the margin) is still ~3.3 L light on both sides (band rows -5 -4 -7
  vs -10 -10 -9): a 1 mm strip at 2.9 texels / mm (r45/texd.py: eye region 2.9, head 2.8) is 3 texels, and its margin folds
  back; fail by 1.3 L against the ~2 L target, symmetric. Gate reads from now on use the _albx (r45/run_v60.sh).
  Eye-region geometry: the kept low poly sits within 0.06 mm (p5 / p95) of the body field over the orbital, infraorbital and
  nose regions (r45/stray2.py), so the bake's rays don't land on other anatomy there; the lips are up to 3.5 mm inside.
- (3) jawOpen teeth: the rows don't support "lower lip covering the lower row": the photo shows a lower tooth band 9.3 units tall
  (runs [+47.1, +56.4], teethline.py), v59 7.2 ([+43.2, +50.4]); the two reviewers disagree (photo: lower teeth too visible;
  game: "only just visible"). No change.
- (4) jaw upper lip: tuck 0.025 gave 8.9 (photo 9.5) and the reviewers still call the ring thick, so the ring is colour / contrast,
  not vermilion height. v60 = v59 with JAW_ROLL_TUCK 0 (rows 9.3 / 15.2 at 0 in r44).

## r46 (2026-10-18, assembly agent, fresh session): the smile rebuilt from a different construction; feature tiles
Why: Joe 2026-10-18 "Tess's smile is truly horrific" and "issues with the way her lips interact with her teeth". r35-r45 tuned
gains on the fitted smile; none moved the read (r45: the levers move the mesh tangentially). Rule this round: change the
construction, not the gains.
- LOOK PROCESS FIX (coordinator): faces reviewed on FEATURE TILES (gates.md LOOK, rule added): scratch r46/tiles.py <out> <tag>
  <ref> <render> (MediaPipe per-feature similarity; mouth, eye x2, cheek x2; 480 px, no captions). v60 baseline tiles:
  r46/tiles_v60/ (smile / neutral / jaw). bin/review FAILED to run (the headless reviewer's account hit its weekly limit, resets
  2026-10-19 13:00 MT): the blind review ran as a fresh subagent with the gates reviewer brief instead (same inputs: images only).
  Alignment caveat: cheek tiles land a few mm off on ours (the face's proportions differ from the photo's; similarity on 16 lms).
- DESCRIBE (r46/smiledesc.py <neutral> <smile> ...; % io; rows r46/desc_rows.txt). Photo smile | photo smile_teeth | v60:
  | item | photo smile | photo smile_teeth | v60 smile |
  | corner path img-L (out, up, angle) | +5.9 +8.7 56 deg | +13.0 +12.3 43 | +11.6 +11.4 44 |
  | corner path img-R | +17.6 +14.3 39 | +20.9 +15.8 37 | +13.3 +12.2 42 |
  | crescent: upper inner lip vs corners | -0.2 | -1.5 | -1.0 |
  | tooth band width (% corner span, >= 2% io) | 62 | 69 | 85 |
  | tooth band mid / edge (u 0 vs 0.6) | 10.8 / 2.9 (3.75) | 18.3 / 10.2 (1.79) | 10.8 / 12.0 (0.90) |
  | corner darkness (lum u .85 / mid) | 0.44 | 0.54 | 0.47 |
  | apple up (lm 50 / 280) | +2.9 / +9.0 | +7.5 / +9.7 | +5.9 / +5.4 |
  The photo's tooth band is a tapered lens (centre tall, nothing past the canines); ours is a uniform strip running to 85%
  of the corner span: the "denture strip". Corner back-travel and the cheek's forward projection are NOT measurable from the
  front-only photos (no 3/4 or side smile photo exists): INFERRED items, judged on the 3/4 clay of candidates only.
STATE: tiles + describe rows done, v60 tile review running. NEXT: GNM candidates (happy / smile_wide / blends / fitted) raw on
tp_k19's identity in GNM's own mouth, clay tiles front + 3/4 beside the photo; lip-teeth items on those meshes.
- v60 TILE BASELINE (blind review, fresh subagent with the gates brief, images only; text summarised in this note): FAIL.
  smile 12 MAJOR (mouth 5: "straight horizontal slot, corners don't lift", "teeth bared to the corners, red flesh between the
  end teeth, no dark corridor", "lower lip thin flat band", "notch over the centrals, red sliver between lip and teeth", "no
  nasolabial folds / no cheek bunching"; eyes 3: no lower-lid rise / roll, eye fully open; cheeks 4: flat cheek, pinched
  corner); neutral 1 MAJOR (parted lips: the approved NEUTRAL_PARTED, coordinator's call); jaw 6 MAJOR (lower row hidden,
  thick swollen lip ring, box-like interior / low tongue, narrow upper arch, thick rolled corner rims). Overall: "a clenched,
  teeth-baring grimace, not a smile. The face above the mouth is completely neutral". Eleven 1 m-frame reviews never said this.
  OTHER STAGES: gold specular blobs inside both nostrils, pale bumps on the right upper lid, no upper-lid crease.
- CANDIDATES RAW (r46/cands.py: tp_k19's GNM identity + expression, GNM's own teeth / gums / sock, no faceshapes levers;
  clay front / raking / 3/4 r46/bl_cand.py; sheets r46/cand_all.png, r46/cand_ball.png, r46/cand_ball2.png; rows
  r46/cand_rows.txt; mm, corner (out, up, fwd), apple (up, fwd), lip (gap to teeth, incisor recess)):
  | cand | corner | apple | upper lip | read (clay) |
  | fitted_w4 (v60's) | +6.8 +7.5 -10.8 | +3.9 +2.2 | 2.9 / 4.7 | straight slot, both rows bared |
  | happy x1 | +5.1 +6.5 -7.6 | +3.2 +1.5 | 5.2 / 7.9 | same strip, weaker |
  | happy x2 (old SMILE_PROTO) | +10.2 +13.1 -15.2 | +6.4 +3.0 | 5.9 / 5.7 | cheeks bunch + fold, but everted lips, both rows bared: grimace |
  | smile_wide x1 / x2 | ~ happy | ~ happy | | same as happy |
  | duchenne (happy .6 wide .2 squint .2) x1.5 | +7.3 +9.1 -10.7 | +4.5 +2.2 | 5.4 / 6.9 | mild strip |
  NO GNM prototype ships a real smile: every class parts the lips uniformly corner to corner (the denture strip is in GNM's
  data, not only our levers). Corners go up AND back in all (fwd -8 to -16 mm); cheeks move forward only 1.5-3 mm.
- THE NEW CONSTRUCTION, "ball" (r46/ball.py <name> K=V ...): a least-squares solve IN GNM's expression space (lower face + eye
  comps: data-backed moves only) whose targets are the cheek, not the lips: (a) cheek / infraorbital / zygomatic / lower orbital
  skin follows happy+squint x KC (the bunching + fold), + an optional forward bump under each lid (FWD); (b) corners up / out /
  back; (c) the lip opening as the photo's tapered lens (inner gaps 62-66 / 61-67 / 63-65), the lower inner lip at the upper
  incisal edge (covers the lower row), the upper inner lip UPIN above it; (d) nose / chin / forehead held. Output a 383 .npy =
  an HP_SMILE_FIT input (no code change). On GNM's own mouth (clay, ball_f / ball_g, cand_ball2.png) it READS AS A SMILE: a
  crescent opening narrowing to the corners, upper row only, the lower lip following the incisal curve, cheek bunching and a
  fold at 3/4. Lever check: FWD 0 -> 4 mm moves the apple forward only +0.5 mm (GNM's space can't project the cheek forward:
  a dead lever there; the forward ball would need a non-GNM term).
- IN THE EXPORT (fast flat proxy fastproxy.py on v60's dump, the batch's smile weights mouthSmile 1 + cheekSquint 1; tiles
  r46/fp/tiles, sheets r46/fp_cmp2.png, fp_cmp3.png; rows r46/fp/desc.txt, % io):
  | item | photo | v60 (proxy) | ball_g | ball_h (UPIN 7) | ball_i (UPIN 9) |
  | corner up img-L / img-R | +8.7 / +14.3 | +11.7 / +11.7 | +16.5 / +14.7 | ~+16 / +15.1 | +16.4 / +14.8 |
  | upper inner lip vs corners (+ below) | -0.2 | -1.0 | +1.9 | +3.8 | +3.4 |
  | tooth band width / mid / ratio | 62 / 10.8 / 3.75 | 85 / 10.1 / 0.89 | 69 / 4.1 / 0.58 | 77 / 5.3 / 0.86 | 69 / 5.3 / 0.78 |
  | corner darkness | 0.44 | 0.46 | 0.68 | 0.64 | 0.57 |
  Look: the cheek tile now shows a rounded apple and a fold line (v60: flat), the band is narrower and the lower lip covers the
  lower row, BUT the upper lip hangs over the upper crowns (half covered; the photo shows whole crowns under a full draped lip)
  and the corners overshoot up. The UPIN and UP targets did NOT move the export (dead levers in the export path: corners +15
  at UP 7 and 5; upper inner lip unchanged at UPIN 7 / 9): the export's teeth are placed by base.head.teeth_place (bigger,
  not GNM's raw position; r46/teethrel.py: GNM raw has the upper inner lip 3.6 mm above the incisal edge, crowns 8.1 mm behind
  it) and the smile path re-clears / wraps the lips, so a lip-to-teeth target solved against GNM's teeth lands wrong.
STATE: construction picked = "ball" (GNM-space solve with cheek targets), proven on GNM's own mouth; in the export the cheek
reads better but the lip-teeth relation does not follow the targets. No NICO-TOP batch this round (nothing proven to send).

## Handover r46 (assembly agent, tool-call budget)
- Committed in worktree agent-ad0815704f43e0e00, not pushed. Nothing in flight. bin/review is down until 2026-10-19 13:00 MT
  (headless reviewer's weekly limit): run the blind review as a fresh subagent with the gates brief until then.
- Scratch r46/: smiledesc.py (describe rows), tiles.py (feature tiles; the LOOK input from now on), cands.py + bl_cand.py (GNM
  raw candidates, clay), ball.py (the construction), teethrel.py, fp/ (proxies + tiles), tiles_v60/ (baseline tiles).
- NEXT (exact): (1) solve the ball's lip targets against the EXPORT's teeth, not GNM's: read the export neutral's upper incisal
  edge and lm 61-67 on the dump (GnmFace in faceshapes.apply: f.head["lm68"], parts["teeth"]) and pass inc / lm offsets into
  ball.py, or add the lip rows to faceshapes' SMILE_FIT path after _clear_teeth (the lips are moved there). Target: upper inner
  lip at the photo's -0.2 % io vs corners, band 62% span, mid 10.8 % io, mid/edge >= 2. (2) Corners: find what lifts them in
  the export to +15 when the solve says +8.6 (_soft_edge / the fade carry / the corner hold?) before tuning UP. (3) The cheek
  ball's forward projection is not in GNM's space (FWD dead): a non-GNM term (the hand CHEEK_LIFT shaped as a ball under the
  lid, upper face turned to the light) only if the tiles still read flat. (4) Then ONE NICO-TOP batch: HP_SMILE_FIT=r46/cand/
  <ball>.npy, HP_SMILE_FIT_FOLD=0, HP_SMILE_LOWLID_GAIN=1 (no r35-r45 gains), photo-light tiles + game rig frames, review on
  tiles. Neutral untouched (smile is a delta; split check still 0.00 mm required).
- Jaw (coordinator's addendum): items to measure next round on the export: lip-to-incisal gap, inner-lip band width, recess.
  The tile review confirms the donut ring + hidden lower row + low tongue (6 MAJOR).

## r47 (2026-10-18, assembly agent, fresh session): lip-teeth numbers in the export, the ball solved in the export's frame, the teeth
Scratch /mnt/data/hifipushie/assembly/r47/.
- (1) LIP-TEETH NUMBERS (r47/whydead.py <ball.npy>: GnmFace's own neutral of tp_k19, mm world; "exp" = the upper incisal edge
  where the export puts it, base.head.teeth_place upper [-2, +1]; the export's teeth part == base.gnm_mouth's mesh exactly):
  | | 62 above edge raw / exp | 66 above edge exp | gap 62-66 | 62 recess exp | corners up |
  | neutral (export) | +0.7 / +2.7 | +3.2 | -0.6 | +4.8 | 0 |
  | ball_g raw delta | +8.6 / +10.6 | +3.7 | +6.9 | +0.1 | +10.9 |
  | ball_g after _soft_edge (+clear) | +8.2 / +10.2 | +4.7 | +5.5 | +0.7 | +10.9 |
  | ball_i (UPIN 9) after soft | +6.5 / +8.5 | +3.6 | +4.9 | +0.3 | +10.1 |
  r46's "GNM raw: upper inner lip 3.6 mm above the edge, crowns 8.1 behind" was cands.py's identity-only V0; the export's
  neutral (GnmFace c["V"]) has 62 only +0.7 above GNM's edge, and teeth_place drops the row 2 mm: +2.7.
- (2) WHY THE EXPORT IGNORED THE BALL'S TARGETS: three causes, all measured above. (a) The solve's frame: ball.py solved
  against cands' V0, whose lips sit ~3 mm higher on the teeth than the export's neutral, and GNM's edge, 2 mm above the
  export's. (b) _soft_edge (SMILE_FIT_SOFT 80 rounds where a move is < 70% of the largest: every inner-lip move) closes the
  centre gap 1.3-1.4 mm and lifts the lower inner lip +1.0-1.1 mm: the lower lip rides 3.6-4.7 mm UP the upper crowns
  (the "lip hangs over the crowns" read was the LOWER lip covering their lower third, plus the band shrinking). _clear_teeth
  moves < 0.7 mm. (c) Corners: NOT the export. The raw solve already lifts them +10.9 mm against UP 7: the cheek term (KC)
  wins over the corner rows at WLM 3.
  FIX = r47/ball2.py <name> K=V: the ball solved in the export's frame (GnmFace neutral, the export's incisal edge), with the
  export's _soft_edge + _clear_teeth applied inside the loop and every target moved by its residual (ITER rounds). Targets
  from the photo rows: UPIN 0.108 io = 7.15 mm (band mid 10.8 % io), LOWIN -0.3 (lower inner lip just under the edge),
  UP 0.115 io = 7.6 mm, side gaps TAPER 0.75 of the centre.
  | after soft+clear (mm) | target | b2a (WLM 3) | b2b (WLM 6) | b2c (WLM 10, KC 1.6) |
  | 62 above exp edge | 7.15 | 7.26 | 6.87 | 6.95 |
  | 66 above exp edge | -0.30 | -0.37 | +0.21 | +0.34 |
  | corners up | 7.6 | 8.76 | 7.68 | 7.61 |
  | side gaps 61-67/63-65 vs centre | 5.6 / 7.5 | 8.0 / 7.6 | 6.5 / 6.7 | 6.6 / 6.6 |
  The TAPER is NOT reachable in GNM's space (side gaps stay = centre at any weight tried): the tooth band stays a strip.
  Fast proxy (fastproxy.py on v60's dump, smile weights mouthSmile 1 + cheekSquint 1; r47/fp, tiles r47/fp/tiles, sheet
  r47/cmp_mouth.png / cmp_cheek_imgL.png photo | v60 render | b2b | b2c) rows (% io, smiledesc):
  | | photo | v60 proxy | b2b | b2c |
  | corner up img-L / img-R | +8.7 / +14.3 | +9.8 / +9.0 | +10.3 / +9.2 | +10.5 / +9.3 |
  | upper inner lip vs corners | -0.2 | -8.0 | -3.3 | -3.6 |
  | band width / mid / mid:edge | 62 / 10.8 / 3.75 | 85 / 13.5 / 0.87 | 77 / 11.2 / 0.95 | 77 / 11.2 / 0.88 |
  | corner darkness | 0.44 | 0.45 | 0.60 | 0.58 |
  Look (proxy, flat light): the upper lip drapes over whole upper crowns, the lower lip meets the incisal edges and hides the
  lower row (v60: both rows bared, notch over the centrals); the cheek tile keeps the apple shading and a fold line (v60
  flat), so (4) the forward cheek term was not needed for this round. Still wrong: the band runs to the corners (no taper),
  lips thin, corner corridor too light.
STATE: b2b picked (closest on the lips with corners on target). NEXT: teeth (3), then v61 batch.
- (3) TEETH (coordinator's item). r47/teethedge.py: ortho front raster of the upper row at 0.05 mm, three sources: GNM raw
  (tp_k19 identity), base.gnm_mouth (after _grow_crowns + teeth_place) and the export's teeth part (v60 dump).
  | | edge rms / max vs a parabola, |x| < 11 mm | notch share | central w | central h (edge -> gum) | w / h per mouth width |
  | GNM raw | 0.58 / 2.41 mm | 2.7% | 8.3 mm | 9.9 mm | 0.164 / 0.198 |
  | gnm_mouth = export | 0.46 / 2.33 mm | 3.0% | 8.7 mm | 13.0 mm | 0.174 / 0.259 |
  The export's teeth ARE gnm_mouth's mesh (identical bbox and rows; no decimation, no wrap, no re-meshing). The incisal edge
  is SMOOTHER than GNM's raw and the central width per mouth width is 6% wider than GNM's; the crown is 1.35x taller
  (TEETH_CROWN_GROW: 13 mm edge to gum vs ~10.5 adult). On the pictures (r47/teethimg.py, % of mouth width): edge rms
  photo smile 0.68 / smile_teeth 0.90, v60 0.49; central width photo 13.1, v60 13.1; gap depth photo 0.13-0.19, v60 0.20.
  So the coarse, staggered, gapped read is NOT the export's geometry and not tooth size: GNM's crowns are coarse quads
  (front outline ~8 straight segments per crown, r47/teethedge.png) with ~2 mm incisal embrasures, and the dark lines run the
  full crown height in the renders while the geometry's notches are small: the next suspects are the teeth's shading
  (normals / baked AO / basecolor between crowns), not their shape. Lever check: an opt-in incisal square-up in _grow_crowns
  (corners eased onto the arc within S mm) moved edge rms 0.46 -> 0.40 (S 2.5) / 0.34 (S 3.5) and max 2.33 -> 2.07: a small
  move on a row that is already better than the photo's; NOT kept (reverted), not in the batch. "Look small": the size
  rows match the photo; v60 showed less crown because the lower lip covered their lower third (fixed by (2)).
STATE: teeth geometry cleared; shading suspects named. NEXT: v61 batch (r47/run_v61.sh, running), tiles, blind review.
- (5) v61 BATCH (r47/run_v61.sh: v54 spec, HP_SMILE_FIT=r47/cand/b2b.npy, no r35-r45 smile gains (FOLD 0, LOWLID 1, EYE 1,
  SMILE_FIT_SOFT default), jaw as v60; NICO-TOP x61 on r44/shots_r44.json). Tests exit 0; split: neutral - low poly 0.00 mm
  (neutral exact). Tiles (photo | v60 | v61): r47/sheet_smile_mouth.png, sheet_smile_cheek_imgL.png, sheet_jaw_mouth.png,
  sheet_jaw_cheek_imgL.png (singles r47/tiles_v60/, r47/tiles_v61/); rows r47/desc_x61.txt, teethline_x61.txt.
  | smile row (% io, photo-lit front) | photo | v60 | v61 |
  | corner up img-L / img-R | +8.7 / +14.3 | +11.4 / +12.2 | +12.0 / +12.0 |
  | upper inner lip vs corners | -0.2 | -1.0 | +1.9 |
  | tooth band width / mid / mid:edge | 62 / 10.8 / 3.75 | 85 / 10.8 / 0.90 | 77 / 2.4 / 0.32 |
  | teeth shown (teethline, h) | 14.4 | 12.0 | 6.0 |
  | corner darkness | 0.44 | 0.47 | 0.52 |
  LOOK FIRST (mine): v61 smile is WORSE at the centre: the upper lip sags in a V over the centrals and the lower lip rises to
  meet it, so the band pinches to a sliver in the middle (an inverted lens) and the teeth read as a V. Lower row hidden
  (gain kept). Jaw unchanged from v60 (as intended). Blind review (fresh subagent, gates brief, tiles only): smile FAIL 9 MAJOR
  (flat almond opening, not a crescent; teeth tilt in a V with a notch at the centrals; no corner lift; no corner darkness;
  thin upper lip without a bow, flat smeared lower lip; no lower-lid rise; no orbital narrowing; no nasolabial fold); jaw
  FAIL 4 MAJOR (thick ring lips, box opening, flat interior / low tongue, lower row hidden). Teeth MINOR only (short, uniform).
- WHY THE PROXY LIED (found after the batch): fastproxy's smile is shots_expr10's pose = mouthSmile 1 + mouthUpperUp 0.5 +
  mouthLowerDown 0.3 + cheekSquint 0.4 + eyeSquint 0.25; the batch (shots_r44) renders mouthSmile 1 + cheekSquint 1. The
  UpperUp / LowerDown share opened the lips several mm in every r46 / r47 proxy, so the "lips drape on whole crowns, lower lip
  on the edge" read (and r46's "dead lever" reading) was a different pose. ball2's numbers (whydead / achieved) are of the
  smile shape alone and stand; the proxy look does not. Also the r46 note's "the batch's smile weights" claim was wrong.
STATE: v61 FAIL, worse than v60 at the centre; cause of the proxy / batch mismatch found. NEXT: see Handover r47.

## Handover r47 (assembly agent, tool-call budget)
- Committed in worktree agent-ad0815704f43e0e00, not pushed. Nothing in flight (x61 collected). Code: none changed (the
  teeth square-up was tried and reverted). bin/review down until 2026-10-19 13:00 MT: blind review = fresh subagent.
- NEXT (exact): (1) Proxy at the batch's pose FIRST: fastproxy with POSE_W='{"smile": {"mouthSmileLeft": 1, "mouthSmileRight":
  1, "cheekSquintLeft": 1, "cheekSquintRight": 1}}' (shots_expr10 column), check it reproduces v61's sag (band mid ~2.4 % io)
  before trusting it. (2) Then find what pinches the centre: ball2's achieved rows say 62 is 6.9 mm above the edge after
  _soft_edge / _clear_teeth, yet the render shows ~2 mm: the steps after _smile_fit in apply (SMILE_FIT_FADE / CARRY at the
  family border, the side split SMILE_SIDE_MM at the midline: both halves faded across x = 0 is exactly where the V is, the
  bake / one-mesh carry) - measure lm 62 / 66 on the dump's applied mouthSmileL+R+cheekSquint (fs.apply on v61dump.pkl,
  body gnm_index) step by step, as whydead.py does for the GNM-side steps. (3) The taper (lens) is not reachable in GNM's
  space: needs a non-GNM term at the side gaps once (2) is fixed. (4) Teeth: geometry cleared (export == gnm_mouth, edge
  smoother than GNM's); if the read stays, look at their shading (normals / AO / basecolor between crowns), not their shape.

## r48 (2026-10-18, assembly agent, fresh session): proxy == batch, the smile sculpted on the export mesh, teeth, jaw
Scratch /mnt/data/hifipushie/assembly/r48/. Coordinator's change of method: stop solving the smile in GNM's space; sculpt it.
- (A) PROXY == BATCH. New scratch module `poses.py`: the ONE pose table = the batch's shots file (poses.BATCH =
  r44/shots_r44.json, what rge2.sh ships as shots.json; unnamed shots named by position as job_ge writes them).
  fastproxy.py now takes `S10 = poses.pose_table(POSES)` (default POSES neutral,smile,jaw); shots_expr9/10, POSE_W, ST_W and
  the `_9` column are gone (old copy r47/fastproxy_r47.py). `test_proxy_batch.py [run_*.sh]` fails if (1) a proxy pose's
  weights != the batch file's, (2) a batch script ships another shots file, (3) fastproxy names another table, (4) the batch
  didn't write that pose. New proxy: exit 0; the r47 proxy: 4 FAIL (smile weights, tables). Proxy on v61dump (39 s):
  | smile (% io) | proxy v61 | batch v61 flat | batch v61 photo-lit |
  | corners up L / R | +12.0 / +11.7 | +14.2 / +14.2 | +12.0 / +12.0 |
  | upper inner lip vs corners | +2.3 | +4.1 | +1.9 |
  | band per column (centre) | 8.3 8.3 **4.7** 7.7 8.3 | 8.8 **4.7** 7.7 | 8.4 **2.4** 7.2 |
  | band mid / edge | 4.7 / 6.8 | 4.7 / 7.1 | 2.4 / 7.5 |
  The proxy reproduces v61's centre sag (same 4.7 dip as the batch's flat render; r48/fp/proxy_vs_batch_v61.png: the same V
  notch over the centrals). Proxy reads count from here on.
STATE: (A) done. NEXT: (B) measure the midline step by step, then sculpt.
- (B) SCULPT (code: faceshapes `HP_SHAPE_SCULPT` = npz of "<part>|<shape>" deltas (export frame, Blender axes, m) added to
  that part's shape in `apply` after `displacements`, checked by vertex count (a changed mesh: WARNING, not applied); the
  rest untouched, so the neutral stays exact. "<teeth part>|_neutral" = a sculpted teeth REST (normals turned with it).
  Script r48/sculpt.py <dump> <npz> on v60's dump (base = v60's smile w4, SOFT 0, FOLD 0.6, LOWLID 1.6: v61's V was worse), on
  the batch's pose (poses.shapes("smile")), per 0.5 mm column of the corner span: LOW = the lower lip's front edge raised to
  max(upper incisal edge - LOWIN 0.3 mm, upper-edge arc - the photo's band(u)) (photo band symmetrised from r46 desc_rows,
  % io x io 64.9 mm), median-filtered, symmetric; the whole lip column translated (not per vertex: per-vertex raising tore
  it, s1) and moved forward so the edge stays CLEAR 0.8 mm in front of the upper crowns (s2); tissue ABOVE the edge (the inner
  roll behind the crowns) kept still (s3 pulled it forward over the centrals: a lip bump at the midline); falloff 8 mm down.
  UP = the upper front edge eased (UPFIT 0.6) onto its own symmetric parabola: v60's upper edge sits 1.6 mm BELOW its arc at
  the midline (the V/notch is there already in v60, smaller than v61's). Split L/R by tanh 10 mm (L + R = the sculpt exactly).
  Midline step measure (r47 NEXT 2) NOT done: superseded by sculpting the result directly.
  | smile, proxy (% io) | photo | v60 | s4 (lips) | s5 (lips + teeth) |
  | band per column u -.6..+.6 | 0.7 8.6 9.3 12.2 10.8 11.5 10.1 7.9 5.0 | 12.4 14.8 14.8 13.0 11.3 13.0 14.2 10.7 10.1 | 5.9 9.5 9.5 10.7 10.7 9.5 10.7 8.3 4.8 | 5.3 9.5 9.5 10.7 10.7 9.5 10.7 8.3 4.8 |
  | band width / mid / mid:edge | 62 / 10.8 / 3.75 | 77 / 11.3 / 1.00 | 69 / 10.7 / 2.00 | 69 / 10.7 / 2.12 |
  | upper inner lip vs corners | -0.2 | -1.7 | +1.5 | +1.5 |
  | corners up img-L / img-R | +8.7 / +14.3 | +10.8 / +10.6 | +15.0 / +14.6 | +15.2 / +14.7 |
  | corner darkness | 0.44 | 0.46 | 0.54 | 0.54 |
  Look (proxy, r48/fp/cmp_s5_mouth.png photo | v60 | s4 | s5): the opening is now a tapered crescent, the lower lip meets the
  upper incisal edge and hides the lower row (v60: both rows bared in a strip). Still wrong: the lower lip reads pale and thin
  (the photo's is full and red), small white specks at the opening's ends, corners not dark enough, the corner rise went UP
  (+4 % io: the raised lower lip lifts landmark 61/291 too).
- (C) TEETH: r48/teeth.py levels the upper row's front tips per column onto a tidy arch (centrals longest, laterals LAT 0.7 mm
  and canines CAN 0.4 mm shorter, smooth steps at the crown widths 8.6 / 6.6 mm, ARC 0.6 mm at 16 mm), fading to 0 at the gum,
  moves clipped to 2.5 mm; stored as "teeth|_neutral" in the same npz (s5).
  | arch (export teeth part, mm) | edge vs target rms / max | tip above the centrals: KR LR CR CL LL KL |
  | v60 (= gnm_mouth) | 0.77 / 2.85 | +1.57 +0.31 +0.01 +0.00 +0.37 +1.43 |
  | s5 | 0.43 / 2.67 | +1.03 +0.62 +0.00 +0.00 +0.76 +0.99 |
  Centrals now clearly longest, laterals step up ~0.7 mm, canines ~1 mm (target 0.4 + arc: the canine tips are pointed, the
  max is the canine's cusp flank). Between-crown dark lines: unchanged (shading, not shape: not addressed this round).
- (D) JAW: not done this round (budget); the sculpt hook takes "body|jawOpen" the same way.
STATE: v62 batch launched (r48/run_v62.sh: v60 settings + HP_SHAPE_SCULPT r48/sc/s5.npz; NICO-TOP x62, tiles photo | v60 | v62).
- (E) v62 BATCH (r48/run_v62.sh; tests exit 0; split: neutral - low poly 0.00 mm, sculpt applied: export log "body mouthSmileLeft
  + sculpt, max 6.5 mm", "teeth rest + sculpt, max 2.5 mm"; NICO-TOP x62 queued ~40 min behind rs_r9). Sheets (photo | v60 | v62):
  r48/sheet_smile_mouth.png, sheet_smile_cheek_imgL.png, sheet_jaw_mouth.png; rows r48/desc_x62.txt, teethline_x62.txt.
  | smile, photo-lit (% io) | photo | v60 | v62 |
  | band per column u -.6..+.6 | 0.7 8.6 9.3 12.2 10.8 11.5 10.1 7.9 5.0 | 13.2 15.0 13.8 12.6 10.8 12.0 15.0 10.8 10.8 | 6.0 10.1 9.5 11.9 10.7 8.9 10.1 9.5 5.4 |
  | band width / mid / mid:edge | 62 / 10.8 / 3.75 | 85 / 10.8 / 0.90 | 69 / 10.7 / 1.89 |
  | upper inner lip vs corners | -0.2 | -1.0 | +1.9 |
  | corners up img-L / img-R | +8.7 / +14.3 | +11.4 / +12.2 | +15.3 / +16.4 |
  | corner darkness | 0.44 | 0.47 | 0.60 |
  | teeth shown h (teethline) | 14.4 | 12.0 | 10.7 |
  | upper arch (export, mm): edge rms / max; tips KR LR C LL KL | (photo: even, centrals longest) | 0.77 / 2.85; +1.6 +0.3 0 +0.4 +1.4 | 0.43 / 2.67; +1.0 +0.6 0 +0.8 +1.0 |
  LOOK FIRST (mine): v62 FAIL. The taper is real (band 85 -> 69 % width, mid:edge 0.9 -> 1.9, lower row hidden), but the sculpt
  made new artefacts: the lower lip's edge is torn/stepped at the centre-left (a central crown shows through a notch), white
  shards at both ends of the opening, the lower lip pale and smeared; corners rose too far (+15/+16 vs photo +9/+14).
  Blind review (fresh subagent, gates LOOK rule, tiles only; A = v60, B = v62): all FAIL; v60 closer on all three sheets.
  B's MAJORs: tear/flap at the left corner, lower lip broken at the centre with a tooth through it, teeth still jagged /
  staggered, lower lip a smear, upper lip thinner, white spike at the right corner; jaw: lateral crowns read as FANGS (the
  levelling's lateral step 0.7 mm + canine taper sharpened the lateral tips) and corner spikes. Shared MAJORs (A and B): no
  cheek / lower-lid / crow's-feet response, no nasolabial fold, lips smeared / rimmed, jaw ring lips + round opening.
STATE: v62 FAIL (worse than v60 by review). The sculpt hook works and the proxy == batch; the column-translation sculpt is too
crude at the lip edge.

## Handover r48 (assembly agent, tool-call budget)
- Committed in worktree agent-ad0815704f43e0e00, not pushed. Nothing in flight (x62 collected). Code: faceshapes
  HP_SHAPE_SCULPT (opt-in). Scratch: poses.py + test_proxy_batch.py (proxy == batch; run it on every run_*.sh), fastproxy.py
  (batch poses only), r48/sculpt.py, r48/teeth.py, r48/try.sh <tag> [K=V] (sculpt -> proxy -> tile sheet in ~1.5 min).
- COORDINATOR NOTE received mid-round (not acted on: budget): the happy/ experiment's mix (mouthSmile 0.8, cheekSquint 1.0,
  eyeSquint 0.5, mouthDimple 0.6, mouthPress 0.2, mouthUpperUp 0.108) reads as a mild real smile and beat v60 blind; no
  weighting gets the band under 81% width (taper must be sculpted); the exported eye/cheekSquint barely move eyes/cheeks.
- NEXT (exact): (1) Make that mix THE smile pose in r44/shots_r44.json (copy to r48/shots_r48.json, set poses.BATCH to it,
  run_v63 ships it; test_proxy_batch must pass). (2) Re-sculpt on that pose with try.sh, fixing the lower-lip edge: move the
  edge as a smooth CURVE (fit the target edge as one even polynomial in u, move each lip vertex by the column's raise with a
  falloff in distance to that curve along the surface, not z-bands), keep the vermilion's texture height (raise the chin skin
  less than the lip: falloff starts at the vermilion's lower border), keep the corners where they were (zero the raise within
  4 mm of 61/291: the specks/tears and the extra corner lift come from there). Check every try on cmp_<tag>_mouth.png before
  numbers. (3) Teeth: drop the lateral step (LAT 0.3, CAN 0.2) or level per CROWN rigidly (segment crowns by x between the
  embrasures) so tips aren't sharpened into fangs; the dark between-crown lines are shading (normals / AO / basecolor), still
  untouched. (4) Strengthen eye/cheekSquint (their shapes barely move: the GNM happy prototype's eye/cheek share) as part of the
  smile sculpt. (5) Jaw (D) not started: the same hook takes "body|jawOpen".

## r49 (2026-10-18, assembly agent, fresh session): the controls-only smile is the baseline; sculpts tried on the proxy, then stopped by Joe's decision
Scratch /mnt/data/hifipushie/assembly/r49/.
- (1) BASELINE: r49/shots_r49.json = shots_r44 with every smile shot (8) set to the happy/ experiment's mix A2 (mouthSmile 0.8,
  cheekSquint 1.0, eyeSquint 0.5, mouthDimple 0.6, mouthPress 0.2, mouthUpperUp 0.108, symmetric). poses.BATCH now points at it;
  test_proxy_batch.py exit 0 (smile + jaw weights match). r49/try.sh <tag> [npz] = proxy on v60's dump at the batch pose -> tiles
  (r46/tiles.py) + smiledesc + lidlift + the fold gate (r49/gate.py); r49/mont.py = photo | results tile montage.
- Rows, proxy (MediaPipe; % io) photo | baseline A2: lower lid up +2.0 | +3.1; eye opening smile / neutral 0.116/0.149 = 0.78 |
  0.094/0.146 = 0.64; apple up (lm 50 / 280) +2.9 / +9.0 | +5.1 / +4.2; band width 62 | 77 % of corner span, mid:edge 3.75 | 1.55.
  So on THIS metric the eyes already close MORE than the photo's (upper lid -2.9 mm, lower +2.4 mm per eye on the mesh, r49/lids.py;
  cheekSquint's fitted eye components drop the upper lid ~3 mm); the "+4.7 / +4.5" lid target was r44's lidshape on v59 renders.
- Fold gate (r49/gate.py, new folds = edges turned > 90 deg in the pose but not the neutral): the BASELINE itself has 117 new
  folded edges / 135 flipped faces in the mouth region (the shapes' own lip rolls), 12 / 3 in eye/cheek. Zero is not the baseline.
- Sculpts tried on the proxy only (none batched, none shipped): sq4 (GNM happy x1.5 cheek share, export-mesh smoothed + 0.4 of
  cheekSquint's upper-lid drop given back): opening 0.73, eye/cheek folds 6, a faint streak on the cheek; lip lifts lp1-lp6 (an
  even polynomial need from the image band, upper/lower split, corner hold, Taubin relax of the posed lips): the relax (c5) removed
  the lower-lip notches / shards and halved the mouth folds (117 -> 55) but opened the band; taper at best mid:edge 2.3 (c2/c3,
  with new shards) or 2.1 with relax (c6, roughness 2.6 mm: not smooth). Nothing beat the baseline cleanly.
- DECISION (Joe, 2026-10-18, via the coordinator): "let's stop hand tuning it and just use the expression parameters from now on."
  Tess's smile = mix A2 as the shots pose (proxy == batch passing). No sculpts, no per-character deltas, no hand-shaped smile:
  HP_SHAPE_SCULPT stays off, r48's teeth levelling is not shipped. Items a-d (squint, taper, teeth, jaw by hand) stopped.
  The neutral stays exact.
STATE: stopped by decision; nothing in flight (no batch launched this round).

## Handover r49 (assembly agent)
- EXPRESSIONS ARE PARAMETER MIXES ONLY (Joe, 2026-10-18). The smile pose = A2 in r49/shots_r49.json (poses.BATCH); run
  test_proxy_batch.py on every run_*.sh. HP_SHAPE_SCULPT (faceshapes, opt-in) stays off; r48/r49 sculpt npzs are dead ends.
- Committed in this worktree (notes only; scratch scripts in /mnt/data/hifipushie/assembly/r49), not pushed.
- Open findings for whoever picks expressions up next: with A2 the eye closes more than the photo's (0.64 vs 0.78 of the neutral
  opening, MediaPipe); a lower eyeSquint / cheekSquint weight is a parameter-only lever to test on a blind tile review. The tooth
  band (77% width) is not reachable by weights (happy/ NOTES). The baseline's lower-lip notches are in the shapes themselves.

## r50 RC (2026-10-18)
Joe: "let's just focus on what's remaining to get game ready Garrett and Tess." Not polish: Tess's release-candidate game
asset end to end with the current best pieces, and an honest gap list (/mnt/data/hifipushie/assembly/RC_tess.md). Scratch
/mnt/data/hifipushie/assembly/r50/. Approved (bin/approve list, 2026-10-18): head tp_k19, body dt_tess (spec v86), coat dt_tess
(dc22 twill hang b02), hair th_W18 / hc_s2 (strand groom; cards not approved). Unapproved: skin (projskin), sweater, jeans, shoes,
lanyard / badge, expressions (A2 mix = parameters only), rig, LODs.
- Step 0: previous Tess exports (v54-v62) were UNDRESSED (tp_h3 top / briefs placeholders) on a weight-0.15 body, not dt_tess's
  approved v86 body (weight 0.5). The RC needs a new model on dt_tess's body.
STATE: surveying the threads' pieces (frozen drapes, cards build, projskin). NEXT: mk the RC model.
- Step 1: no frozen pickles exist in the dress-tess thread (/mnt/data/hifipushie/dress_tess has none). r50/freeze.py freezes
  dt_tess's CACHED drapes (cloth.cached, never simulates; read-only use of the model) -> r50/frozen/{coat,sweater,jeans}.pkl.
  r50/mk_rc.py builds model rc_tess: dt_tess (body v86 + props + garment defs) + v54's base.head (tp_k19 + teeth_place) + the
  skin stack + v54's groom (th_W18 re-seated on tp_k19, copied, no re-tie) + frozen garments; top / briefs stand-ins dropped.
  r50/shots_rc.json: turn, neutral / A2 smile (asserted == shots_r49) / jaw / blink at 0.75 m, walk / idle / run (Xbot), 1 m
  and 3 m 1080p (neutral, smile), 3 m body.
STATE: freezing (heavy slot). NEXT: mk_rc, export (v60's face-shape settings: what A2 was measured on), game check.
- Step 2: frozen from dt_tess's cache (12:09): coat key 59dd2d0143597d57 (16,883 v), sweater ac35eb1dfaa337db (9,257 v), jeans
  3e42fc7c870b3383 (10,772 v), r50/frozen/*.pkl. Model rc_tess saved (parts body, eyes, hair, socks, shoes, soles, lanyard, clip,
  badge, badge_card, outsole, laces, teeth, teeth_lower, tongue; cloth coat / sweater / jeans frozen).
  Export r50/run_rc.sh (v60 face-shape env, HP_SHAPE_SCULPT unset; hero, lods, cull_under_cloth) -> exp/rc_tess, log out/exp_rc_tess.log.
STATE: export running (heavy slot, CAP=20G). NEXT: the GLB game check (ge.sh, local, r50/shots_rc.json + Xbot clips).
- Step 3 EXPORT DONE (1495 s): exp/rc_tess/rc_tess.glb (41 MB) + _LOD1..3. Rig 87 bones (Mixamo, 14 twist), 54 ARKit targets
  on 5 parts, head 22,962 + body 7,738 tris (two meshes, one skeleton). Frozen drapes carried max 5.1 mm (jeans pushed 1,089 v).
  HAIR = MAIN's cards cut from the strand groom (952 cards, 24,998 tris, default path), NOT the cards thread's b32 hero
  (coordinator, round 24: b32 = haircards/exp/b32, code 4352c62a on worktree-agent-a54a66de6d6970c0b, NOT on main; needs
  hair.export.tier "hero"): b32 needs its branch on main before an assembly can use it.
  Budgets (GLB triangle count; budgets.lod_triangles): LOD0 95,446 / hero 103,000 OK; LOD1 46,074 / 51,500 OK; LOD2 34,704 /
  25,750 OVER; LOD3 25,864 / 12,360 OVER. Body (3,238) and cloth (coat ~3.5k, jeans 3,002) go flat after LOD1, and hair
  drops layers once (coordinator: cards 11,996 -> 5,324, then flat). Export warnings: clothing 25,850 / 25,000, eyes_mouth_lashes
  10,445 / 7,996 OVER; eyeBlinkLeft lip-seam 3.23 mm^2 (limit 0.05); mouthLowerDownLeft unevenness 0.35 (limit 0.2); teeth
  42 folded edges.
STATE: game render (local ge.sh, shots_rc + Xbot) running. NEXT: look, gap list, blind review, Joe sheet.
- Step 4 GAME CHECK + GAP LIST (copy of /mnt/data/hifipushie/assembly/RC_tess.md below). Look-first (mine, before the review): body,
  coat and Mixamo walk / idle / run hold at 3 m (no pokes, coat swings); the HEAD is the weak part: hair slicked / stringy with a
  spiky flecked crown vs the soft wavy reference, the face reads narrower-eyed / heavier-browed, smile lopsided, skin plastic.
  Joe sheet: workspace/human_renders/gr_r50_tess_rc.png (reference first; turnaround, expressions, walk / run).

### Tess RC (r50, 2026-10-18): gap list to "game ready"

GLBs: /mnt/data/hifipushie/assembly/exp/rc_tess/rc_tess.glb (LOD0, 95,446 tris, 41 MB) + rc_tess_LOD1/2/3.glb; report rc_tess.json,
shading rc_tess_shading.{json,md}. Model workspace/rc_tess (r50/mk_rc.py). Game check: r50/ge/x_*.png (re-imported GLB, game EEVEE).
Joe sheet: workspace/human_renders/gr_r50_tess_rc.png.

Legend: DONE (approved / works) | CURRENT-BEST (unapproved, ships as is) | BROKEN (blocks game ready)

#### Top blockers (visible at 1 m / 3 m)
1. HAIR - BROKEN at 1 m: slicked, stringy, wet-looking crown with a spiky top and white flecks; the reference is soft, full and wavy
   with a centre part. The RC carries MAIN's cards cut from the strand groom (952 cards, 24,998 tris), not the cards thread's
   b32 hero (code 4352c62a, unmerged branch worktree-agent-a54a66de6d6970c0b; needs hair.export.tier "hero"). Hair LODs drop
   layers once only (11,996 -> 5,324, then flat) in this RC's code.
   UPDATE (cards thread, coordinator): best cards are now b36 (haircards/exp/exa29b/hc_s2.glb + LOD1-3; LOD3 not fit from behind yet),
   the hair LOD bug is fixed (hair.share_atlas), and eyes / mouth / lashes fit the 5,000 budget there. The next RC re-export takes
   b36 once its code is on main.
2. LIKENESS in the game render - BROKEN at 1 m: the exported head under game light reads narrower-eyed and heavier-browed than
   the reference; skin reads smooth / plastic.
3. SMILE (A2 mix) - CURRENT-BEST with a MAJOR: lopsided (her left eye squints more in the front view), the tooth band is narrow
   (r49: 77% width unreachable by weights), and the eyes close more than the photo (0.64 vs 0.78 of the neutral opening).
4. LODs vs budgets - BROKEN past LOD1: LOD2 34,704 / hero 25,750 and LOD3 25,864 / 12,360 OVER. Body (3,238) and cloth (coat
   ~3.5k, jeans 3,002) stop reducing after LOD1. Main-NPC budget is over at every LOD (LOD0 95k / 50k).
5. Export warnings: clothing 25,850 / 25,000 and eyes_mouth_lashes 10,445 / 7,996 OVER; eyeBlinkLeft opens the lip seam 3.23 mm^2
   (limit 0.05); mouthLowerDownLeft unevenness 0.35 (limit 0.2); teeth 42 folded edges.

6. EYES (assembly items, coordinator): in the re-imported model the lid rims and inner corners show pink-lilac, and the upper
   lashes look like a stiff comb from the side.

#### By stage
| stage | status | notes |
|---|---|---|
| head | DONE (tp_k19 approved) | game-light read is off (blocker 2) |
| body | DONE (dt_tess v86 approved) | two meshes, one skeleton, seam ring shared |
| skin | CURRENT-BEST | v54's projskin stack (projection + stack); skin thread's later r9 / r10 not swapped in; plastic at 1 m |
| hair | BROKEN | blocker 1; groom th_W18 / hc_s2 approved, its card export is not |
| garments | coat DONE (dc22 hang approved); sweater, jeans, shoes, lanyard / badge CURRENT-BEST | frozen this round from dt_tess's cache (no frozen pickles existed); carried max 5.1 mm; nothing pokes in walk / run at 3 m |
| assembly / export | DONE (runs) | one GLB, rig, 54 ARKit targets on 5 parts, LODs, cull_under_cloth |
| rig and weights | CURRENT-BEST | 87 bones Mixamo; walk / idle / run retarget clean at 3 m; close-up bends not checked this round |
| expressions | CURRENT-BEST | parameter mixes only (Joe); smile = A2; blink and jaw read; blocker 3 |
| LODs | BROKEN | blocker 4 |
| budgets | hero LOD0 / LOD1 OK; LOD2 / 3 OVER; main NPC OVER | |
| engine check | DONE (plumbing) | game EEVEE on the re-imported GLB; blind review below |

Not checked this round: close-up joint bends (elbow / knee / shoulder), 1 m poke checks in extreme poses, the cards build b32.

## Handover r50 (assembly agent)
- RC = exp/rc_tess (model rc_tess, r50/mk_rc.py; drapes frozen by r50/freeze.py into r50/frozen; export r50/run_rc.sh; game check
  r50/ge via ge.sh + r50/shots_rc.json + Xbot.glb). Recipe repeatable: freeze -> mk_rc -> run_rc -> ge.sh -> tiles / sheet.
- Next RC export: b36 cards (once the cards branch is on main) + the skin thread's newest stack (skin_from=) + LOD2/3 body and
  cloth reduction (the general LOD gap); then a close-up bends check and a re-review.
- Open question for the coordinator: v60's HP_SMILE_FIT (w4, a per-character fitted smile shape) is still in the export env; under
  Joe's "parameter mixes only" rule it may count as a per-character delta. Joe's call.
STATE: RC exported and checked, gap list written; blind review result appended below when it lands.
- BLIND REVIEW r50 (images only): VERDICT FAIL, 9 MAJOR: likeness (different, younger person: rounder / wider face, smaller eyes);
  nostril smudges (3 m); smile = flat mouth + eyes squinted shut (a grimace); hair crown spike + white flecks, hairline clumps /
  wide part; coat blotchy grey smears, grey gap at its inner edge. Walk / run deform cleanly. Copied into RC_tess.md.
  Coordinator's added assembly items: pink-lilac lid rims / inner corners, upper lashes a stiff comb from the side; b36 cards.
STATE: r50 done, stopped. NEXT: see Handover r50.

## r51 RC2 (2026-10-18, assembly agent, fresh session)
Goal: Tess RC2 with the current best of every piece and the export-side gaps closed. Scratch /mnt/data/hifipushie/assembly/r51/.
- Step 0 MERGES: origin/main (f01962ee) -> conflicts faceshapes (main's character_fits taken), job_ge (anim clip), notes. Then the
  hair-cards head (67b4a637: b35 / b36, share_atlas, ROOT_SEAT, drop_far_fly, lash ribbon_fit): asset.py takes the cards branch's
  `ribbons=` lash LODs and DROPS main's lods.thin_strands call (both thinned the lashes: double thinning); lashes VERSION 22
  (per-lid segments + taper_out). Then projskin2 (8dccdfee: skin r14, gnm_fold.WRAP_MAX lid-fold clamp, the lid slit designed in
  mesh_quality, brow clump / feather / opacity): s25 needs that code. skin.py kept main's de-named comment; small notes hunks kept
  main's (de-named) side. Cherry-picked from Garrett's assembly branch: 9367787f (OSL bake fallback), 9521465a (two-sided cloth
  decimation rebuilds the inner shell from the decimated outer: Garrett's jacket blotches), 2044fe0d (cards take the strands'
  EEVEE lift). Tests: game_ready, hair_lods, cloth, cloth_layers, cloth_made, skin, face_shapes.
- Step 1 LOD FLOOR found: lods.lod_part decimates per glTF patch (uv island x smoothing group x mesh) with preserve_border, so
  every island's border is kept: the template-wrap body and the pattern-piece cloth stop at their border counts (r50: body 3,238,
  coat ~3.5k, jeans 3,002 from LOD1 to LOD3). Not min_triangles (only shoes / soles / outsole set it) and not MIN_PART.
  FIX (general): lods.LOD_WELD: a part whose per-patch result is over LOD_WELD_OVER (1.25) x its share is decimated WELDED per
  mesh (only true borders kept), each new triangle given the uv island of the nearest LOD0 triangle, its corners resampled on
  that island (seams stay seams). report["welded"]. Test test_lod_reduces_past_uv_island_borders (a 40x40 grid in 4x4-cell
  islands: per-patch floor > 1.25 x share, welded <= it at 0.25 and 0.1). The shares are budgets.py's (above 1/.5/.25/.1, below
  1/.25/.11/.05), unchanged.
- Step 2 BAKE CAGE (skin r14's nostril pinwheel fans / ragged rim: one cage extrusion per part = the part's WORST stray, ~6 mm on
  "body" = GNM head + wrapped body): asset.BAKE_CAGE / cage_verts: each low-poly vertex pushed along its averaged normal by its own
  faces' stray x1.5 + 2 voxels; blender_scene.bake_maps bakes through it (use_cage, cage_object). Test test_bake_cage_is_per_vertex.
- Step 3 MODEL rc2_tess = r50/mk_rc.py dst=rc2_tess skin_from=tp_k19_s25 (CURRENT BEST SKIN: fixes the stale-skin causes of the
  lilac lids, waxy skin, dark nostrils per skin r14) + r51/mk_rc2.py: hair.export.tier hero on the th_W18 groom (hc_s2's locks sit
  on a different identity: not copied; the cards CODE is b36's), base.lashes.upper clump .8 / sizes 4-8 / vary .5 / rows .35 (the
  stiff comb: a candidate, judged in the game check). Garments = r50's freezes (no newer dress-tess pickles). Smile = r49 / v60 env.
  Export r51/run_rc2.sh -> exp/rc2_tess (heavy slot, CAP=20G).
STATE: export running. NEXT: budgets per LOD, game check (ge.sh, r50/shots_rc.json), look, blind tiles, Joe sheet, RC_tess.md.

- Step 4: export queued behind the memory gate (heavy.sh: 26 of 40 GB declared by exa26 hc_s2 / projskin r14g4 / hx hg_G88a) at
  ~15:40. r51/ge_all.sh (detached) waits for r51/EXPORT_DONE, then writes r51/tris.txt (GLB triangles per mesh, r51/tris.py) and runs
  the game check: LOD0 with r50/shots_rc.json + gdproj/xbot.glb -> r51/ge/x_*; LOD0 at 3.1 m (l0_*) and LOD1 / 2 / 3 at their
  switch distances 3.1 / 6.2 / 12.9 m (budgets lod_screen_size .5 / .25 / .12, 1.75 m sphere, fov 59 on 1920) front / 3/4 / back
  -> r51/ge/l{1,2,3}_*; then r51/GE_DONE. Logs out/exp_rc2_tess.log, r51/ge.log.
STATE: export + game check chained, unattended (tool-call budget). NEXT: see Handover r51.

## Handover r51 (assembly agent, tool-call budget)
- Code (branch worktree-agent-ad0815704f43e0e00, committed): merges of origin/main, hair-cards (b36), projskin2 (skin r14) +
  Garrett cherry-picks (OSL bake, two-sided cloth decimation, card EEVEE lift); lods.LOD_WELD (the LOD2 / 3 floor); asset.cage_verts
  (per-vertex bake cage). The cage is NOT yet proven in a real bake: if the export fails in bake_maps, set asset.BAKE_CAGE = False
  and re-run r51/run_rc2.sh (then the nostril fans stay; skin r14's note).
- When r51/GE_DONE exists: (1) read r51/tris.txt vs budgets.lod_triangles (hero 103,000 / 51,500 / 25,750 / 12,360; r50 LOD2 34,704,
  LOD3 25,864) and the export log's "welded" LOD lines / quality lines (lid slit folds expected <= ~2 for Tess per skin r13);
  (2) LOOK FIRST at r51/ge/x_neutral_*, x_smile_*, x_turn_side (lashes: candidate clump .8 / vary .5 in base.lashes.upper; revert it
  in workspace/rc2_tess if it reads worse), the coat in x_turn_* / x_walk_* (blotchy smears + grey inner gap: 9521465a should
  fix), the lid rims / inner corners (s25 skin), nostrils at 3 m (x_g3_*); then l1-l3 at switch distance incl. the back;
  (3) blind feature tiles (bin/review after 2026-10-19 13:00 MT, else a fresh blind subagent; r50's tiles layout in r50/tiles);
  (4) the labelled Joe sheet (workspace/human_renders/gr_r51_tess_rc2.png, reference first) and RC_tess.md (gap list: LODs,
  eyes, coat lines updated from what the renders show).
- Not done this round: the game check, review, sheet, RC_tess.md update. Open question (r50) unchanged: HP_SMILE_FIT in the env.
- Not on main: everything above (main lacks projskin2's WRAP_MAX / slit code, the cards' b35-b36 code and Garrett's session-4 fixes).
STATE: r51 stopped at the tool-call budget with the export queued and the game check chained.
- Coordinator items handled: (1) skin by explicit id: r50/mk_rc.py now REQUIRES skin_from (the v54 default shipped the stale skin);
  rc2_tess = tp_k19_s25. Per-vertex cage done (asset.cage_verts, test); Garrett's export takes it too (his skin gp_h6c_s21).
  (2) b37: merged 408c55ef (notes only past 67b4a637: b37's code = what rc2 exports with). The export started ~15:45, bake ran
  by 612 s through the cage; the "kept the low-poly surface" lines for badge / lanyard / lips match r50's (8 such lines there).

## r52 (2026-10-18, assembly agent, fresh session): collect RC2, LOOK, blind tiles, Joe sheet
Scratch /mnt/data/hifipushie/assembly/r52/.
- Step 0: RC2 export still running at 15:45 (started after a 115 s memory wait; log out/exp_rc2_tess.log at cloth / bake stage,
  no errors). No full test run from r51 was recorded: r52/tests.sh runs game_ready, hair_lods, budgets, face_shapes, skin, cloth,
  cloth_layers, cloth_made in a light slot (r52/tests_summary.txt). bin/review not before 2026-10-19 13:00 MT: blind subagent.
STATE: waiting on r51/EXPORT_DONE -> GE_DONE; tests running. NEXT: tris vs budgets, look, tiles, sheet.
- Step 1 RC2 EXPORT: exit 0 (exp/rc2_tess, ~13 min). Triangles (r51/tris.txt) vs budgets.py hero: LOD0 91,666 / 103,000 OK;
  LOD1 44,976 / 51,500 OK; LOD2 30,316 / 25,750 OVER (r50 34,704); LOD3 19,924 / 12,360 OVER (r50 25,864). Clothing 25,886 / 25,000
  OVER (LOD0). r51's weld fixed the body (850 / 650 at LOD2 / 3) but the cloth still floors: coat 3,492, jeans 3,006, sweater 2,440
  at LOD2 AND LOD3; plus ~4.9k of accessories < MIN_PART kept whole (shoes 745, tongue 700, eyes 637, laces 540 ...).
  CAUSE (r52/borders.py on the LOD3 GLB): pattern-piece cloth is mostly BORDER (coat 3,492 tris, 2,074 border edges; sim seams
  are not shared vertices, 0.1-0.5 mm apart), and pyfqmr preserve_border keeps every border edge even welded.
  FIX (general): lods.LOD_BORDER_OVER (1.25): a welded mesh still over 1.25 x its share is redecimated with preserve_border=False
  (fqmr collapses border vertices only into border vertices: outlines stay outlines, coarser). Test test_lod_reduces_pattern_pieces
  (8x8 separate pieces 0.2 mm apart: share met, every vertex within a cell of LOD0; floors without it). On rc2's real meshes
  (r52/relod.py, shares .25 / .11 / .05): coat 3,740 / 1,514 / 688 (was 3,740 / 3,508 / 3,508), jeans 2,039 / 897 / 407 (3,000 flat),
  sweater 988 / 434 / 229 (2,420 flat). Expected LOD2 ~24.7k, LOD3 ~12.3k. Seam gaps at LOD2 / 3 still to LOOK at: re-export
  r52/run_rc2b.sh -> exp/rc2b_tess (rc2_tess left intact for the game check).
- Tests (r52/tests_summary.txt, one file at a time per the coordinator): game_ready, hair_lods, budgets PASS; rest running.
- Step 2 LOOK FIRST (r51/ge, mine, before the review): nostrils at 3 m clean (no pinwheel fans: the cage works); lid rims no longer
  lilac; lashes thin and soft, not a stiff comb (candidate kept); coat smears and the grey strip at the inner front edge UNCHANGED
  (both in LOD0; Garrett's two-sided decimation fix is not their cause); hair crown a white shiny patch / flat helmet, stringy
  temple strands. NEW MAJOR: LOD1 / 2 / 3 from the back show the jeans (dark blotches) through the coat skirt and the sweater
  (orange) at the elbows / back: garments are decimated one by one, the error exceeds the layer gaps. LOD0 clean.
- Step 3 BLIND TILES (bin/review not available before 10-19 13:00: fresh blind subagent, images only): r52/blind/00-24 =
  ref | A | B (r50 vs r51, side randomized, key r52/abkey.json): 20 feature tiles (mouth, eyes, cheeks x neutral / smile / jaw /
  blink, r46/tiles.py) + hair, nose 3 m (crop missed the face: redo), body front / back / walk. VERDICT FAIL both, ~a tie
  (MAJOR r51 vs r50 ~ 41 / 43). r51 better: cheeks, jaw-open mouth, 3 of 5 eye tiles; worse: smile right lip corner (white blob /
  notch), hair crown, ponytail. Shared MAJORs: hard grey shadow wedge nostril -> upper lip / nasolabial; bruise-like under-eye
  rings; grey speckled sclera; crusty nostril fringe; dark stripes on the ears; pale lid patch + lash smear at blink; smile eyes
  nearly shut; jaw-open lower lip an inflated tube; coat smears.
- Step 4 SHEET workspace/human_renders/gr_r51_tess_rc2.png (r52/sheet.py: reference first, red REF captions; expressions,
  turnaround + walk / run / idle, 1 m / 3 m, LOD0-3 backs at switch distance). RC_tess.md rewritten (top blockers first).
- Tests: game_ready, hair_lods, budgets, face_shapes PASS (r52/tests_summary.txt); skin, cloth, cloth_layers, cloth_made still
  running one by one (r52/tests.sh, detached, light slot).
STATE: RC2 reviewed; LOD_BORDER_OVER committed, its re-export rc2b + LOD looks chained unattended (r52/ge_b.sh -> r52/GE_DONE).

## Handover r52 (assembly agent, tool-call budget)
- Collect: r52/tests_summary.txt (skin / cloth / cloth_layers / cloth_made: the coordinator wants these verified; fix any merge
  breakage before trusting RC2); r52/tris.txt (rc2b LODs vs 25,750 / 12,360; expected ~24.7k / ~12.3k) and r52/ge/l{1,2,3}_*_back:
  do the border collapses open seam gaps on the coat / jeans? If they do, weld coincident seam vertices (r52/borders.py: jeans
  seams close at 2 mm) before the border pass instead.
- NEXT export-side blocker: LOD poke-through (RC_tess.md #1). Fix generally in asset.py's LOD loop (~line 2647, lods.lod_parts):
  per LOD, for each garment under another (cover order as cull_under_cloth / cover_by), move under-layer vertices that lie outside
  the decimated cover inward below it (cloth's push_under idea), or drop covered under-layer faces (under_cloth_keep against the
  LOD cover). Test: two nested decimated shells, no inner vertex outside the outer. Then re-export + l1-l3 back looks.
- Then: the coat smears / inner-edge strip (LOD0, bake or shade), the nose-to-lip shadow wedge (skin / bake: shared by r50 and
  RC2), smile lip-corner blob, hair crown (cards thread).

## r53 (2026-10-18, assembly agent, fresh session): tests, rc2b LODs, LOD layer poke-through, coat smears
Scratch /mnt/data/hifipushie/assembly/r53/.
- Step 0 (16:00): r52's chain still running: rc2b export at the bake (~560 s), test_skin running (cloth, cloth_layers,
  cloth_made after it, r52/tests.sh one at a time); game_ready / hair_lods / budgets / face_shapes PASS.
- Step 1 POKE FIX (general, export): lods.push_under_layers(parts, stack): after each garment is decimated alone for a LOD,
  every outward vertex of an under garment whose nearest cover along its normal (lods.under_depth: ray both ways, within
  LOD_UNDER_REACH 20 mm) is less than LOD_UNDER_GAP (2 mm) outside it moves in along that normal to 2 mm under; a two-sided
  garment's inner shell follows its outer twin (the _lod_shell layout); positions only (weights, uv, shapes per vertex stay).
  asset.export builds the stack from the garments' "over" chains (coat > sweater > jeans: jeans under [sweater, coat]) and
  logs "LODk: under garments put back ... poking a -> b"; asset.LOD_PUSH_UNDER switches it. Test
  test_lod_under_garment_stays_under (nested tubes, 6 mm bumps through a 3 mm gap: poking > 50 -> 0, min depth >= gap, the
  inner shell keeps its offset, the uncovered end and the cover untouched). Re-export chained: r53/chain.sh waits for
  r52/GE_DONE, then rc2c (= rc2b + push) -> exp/rc2c_tess and the full game check (r53/ge_all.sh -> r53/ge, r53/tris.txt).
STATE: push committed (7794219c); rc2b finishing, rc2c chained. NEXT: rc2b tris / seam looks, tests, coat smear source.
- Step 2 COAT SMEARS = THE COAT'S NORMAL MAP, not the bake / AO / decimation (r53/probe: rc2's LOD0 GLB in the game check,
  only cloth_coat_normal.png swapped; sheet r53/probe/ab2.png = original | normal at 35% | flat normal, front; original |
  35% back). The diagonal grey streaks over the fronts, sleeves and back are the authored woven surface in the normal map
  (spec cloth.coat.detail surface "twill", crush 0.0016 m, crush_stretch 6, crush_spread 8: long diagonal crush ridges, plus
  fine_folds), lit by the game rig; the basecolor is clean (233 grey-white, seam lines only). Flat: the coat reads clean
  (geometry folds stay); 35%: still some cloth life, no smears. ROUTED to dress-tess (cloth detail is theirs): crush depth
  ~0.0006 or stretch lower, judged in the game check, not the cloth look. The GREY STRIP at the inner front edge is NOT the
  normal map (it stays with a flat one): it is the inside of the opposite front (the coat's inner shell, normal turned in)
  seen through the opening, lit by ambient only (no bounce in EEVEE's game rig), its edge hard where the 0.8 mm shell
  turns. Geometry / light, not the bake: routed to dress-tess with the crop r53/probe/strip.png (a rolled front edge or a
  facing that turns out would soften it).
STATE: smears' cause found + routed. NEXT: rc2b tris / seam looks, tests, then rc2c's poke looks.
- Step 3 FACE MAJORs, bake or skin? (r53/probe, rc2's LOD0 face 0.75 m, maps swapped one at a time; sheets face_ao.png,
  face_fn.png, face_soft.png). (a) AO: the game check never reads the ORM's occlusion (blender_game.build: orm G / B only;
  glTF occlusion is ambient-only in engines): white AO renders bit-identical, so the baked AO causes none of them.
  (b) the skin normal map flat: wedge, rings and ear stripes all stay. (c) the game rig's key with a 25 deg angle instead of
  2 deg (shots' "lighting"): the HARD GREY NOSTRIL -> UPPER-LIP WEDGE IS THE KEY LIGHT'S CAST SHADOW of the nose (gone soft),
  and the DARK STRIPES ON THE EARS are the hanging temple strands' cast shadows (gone soft). Neither is in the textures. The
  2 deg key is the game-readability rig (hard shadow maps); the blind review judged likeness under it: per gates.md
  likeness belongs under the reference's fitted light (stage.photo_light), so the next review's face tiles must use it.
  (d) The UNDER-EYE RINGS stay under every swap (softer under the soft key): they are in the basecolor (the skin stack
  bake of tp_k19_s25) or the lid geometry: ROUTED to skin (r15) with face_fn.png. Sclera speckle not resolved at this
  distance: the eyes' own maps (skin / GNM eyes): routed with it.
STATE: face MAJORs split: wedge + ear stripes = review light (hard key); rings / sclera -> skin r15. NEXT: rc2b + rc2c looks.
- Step 4 TESTS: all 8 PASS (r52/tests_summary.txt: game_ready, hair_lods, budgets, face_shapes, skin, cloth, cloth_layers,
  cloth_made). rc2b (LOD_BORDER_OVER) triangles (r52/tris.txt) vs budgets.py hero: LOD0 91,666 / 103,000; LOD1 42,554 / 51,500;
  LOD2 24,222 / 25,750; LOD3 12,100 / 12,360: ALL UNDER (rc2: 30,316 / 19,924 over). Coat 3,736 / 1,512 / 688, jeans 2,038 /
  898 / 408, sweater 986 / 434 / 282. LOOK (r53/rc2_vs_rc2b_lods.png: rc2 | rc2b, back + front per LOD at switch): the
  poke-through unchanged (no push in rc2b) AND NEW at LOD2 / LOD3: grey slits / triangles at the coat's seams and pockets and
  a ragged LOD3 hem: the border collapses opened the sim seams (handover's warning). FIX lods.LOD_SEAM_WELD (2 mm):
  in the welded decimation, border vertices that close are joined first (_weld_seams), so a seam is an inner edge and only
  hems / front edges / cuffs stay borders. On rc2's real meshes (r52/relod.py) the coat and jeans now reach their shares
  WITHOUT border collapses (coat 3,740 / 1,514 / 688, jeans 2,040 / 896 / 408); the sweater still needs them (1,431 flat
  without). test_lod_reduces_pattern_pieces extended: border length after the LOD = the sheet's outline only (border
  collapses alone: > 1.6 x, the slits). Committed c9f0b1da; rc2c restarted with push + weld (r53/chain.sh, 16:20).
STATE: rc2c (push_under_layers + seam weld) exporting. NEXT: rc2c LOD backs / fronts vs rc2, tris, blind LOD review, sheet.
- Step 5 GARMENT-UNDER-GARMENT CULL (coordinator, after Joe asked about trimming unviewable triangles): cull_under_cloth
  skipped cloth parts, so the jeans / sweater kept every triangle under the coat. Now asset.export also drops an under
  garment's faces its covers hide (asset.cloth_under_keep: under_cloth_keep's test, reach 60 mm and 40 mm rim, against the
  sim meshes of every garment above it by the "over" chain; a two-sided garment tested on its OUTER shell only, each inner
  triangle following its twin (inner vertices face in: as "uncovered" they would keep every rim), made pieces / buttons
  kept; asset.cull_tris recounts the shell layout) at LOD0, so every LOD inherits it. asset.CLOTH_UNDER_CULL switches it.
  push_under_layers stays for the rims left at the openings. Test test_cloth_under_cloth_culled (two-sided tube under a
  shorter cover: covered middle dropped on both shells, the part past the opening + the rim kept, shell layout valid).
  NOT done: a per-frame exposure test over the walk / run / idle clips (needs skinning in numpy); exposure is checked by
  LOOKING at the clip frames in the game check (x_walk_*, x_run_*, x_idle_*) for holes. Committed ae0bab9e; rc2c restarted
  16:29 with cull + push + weld.
STATE: rc2c exporting (cull + push + weld). NEXT: tris, clip frames + LOD backs vs rc2, sheet, RC_tess.md.
- Step 6 rc2c (exp/rc2c_tess, GLBs rc2_tess*.glb; cull + push + weld): export clean. Cull: sweater 2,010 of 3,956 and jeans
  3,466 of 8,158 triangles dropped at LOD0; clothing 20,410 / 25,000 (was 25,886 OVER). Triangles (r53/tris.txt): LOD0 86,190
  / 103,000, LOD1 41,188 / 51,500, LOD2 23,678 / 25,750, LOD3 11,784 / 12,360: ALL UNDER. Push log: poking vertices 4-9 per
  garment per LOD -> 0. LOOK (r53/rc2_vs_rc2c_lods.png, rc2 | rc2c): BACKS at LOD1 / 2 / 3 CLEAN: no jeans / sweater through
  the coat, no seam slits, hem whole. Still wrong: FRONTS at LOD1-3 show grey faceted patches at the hip pockets and lapels
  (rc2 had them too: the made pieces / pockets decimated as "rest" over the coat, not the layer push), and LOD2's back shows
  pale blotches on the jeans' lower legs (new or newly visible: NOT checked, zoom r53/ge/l2_lod2_at_switch_back.png first).
  Clips (r53/clips.png: walk side / 3/4, run, idle, turn back): no hole in the jeans / sweater at these frames (coarse view).

## Handover r53 (assembly agent, tool-call budget)
- DONE: tests 8/8 PASS; lods.push_under_layers, lods.LOD_SEAM_WELD, garment-under-garment cull (asset.cloth_under_keep /
  cull_tris), 3 tests; rc2c exported and game-checked (r53/ge). Coat smears = the coat's normal map (twill crush relief) and
  the grey strip = the inner shell under ambient: both ROUTED to dress-tess (r53/probe/ab2.png, strip.png). Face: the nose
  wedge and ear stripes are the 2 deg key's cast shadows (r53/probe/face_soft.png); AO is unused by the game check; the
  under-eye rings / sclera ROUTED to skin r15 (face_fn.png).
- NEXT: (1) zoom r53/ge/l2_lod2_at_switch_back.png (pale blotches on the jeans' calves) and the LOD1-3 fronts' grey pocket /
  lapel facets: likely the made pieces (pockets, collar: "rest" triangles after the shells) decimated alone; try keeping
  made pieces whole or pushing them over the decimated outer shell. (2) a per-frame exposure test for the cull (pose LOD0 at
  walk / run / idle frames, any culled face visible?) if the coordinator wants it beyond the clip looks. (3) blind review:
  LOD0 face / body of rc2c = rc2 except the culled under faces, so a face review vs RC2 is moot; a blind LOD-back review
  rc2 vs rc2c (r51/ge vs r53/ge l1-l3) and the sheet (r52/sheet.py r53/ge ...) + RC_tess.md update were not done.

## r54 (2026-10-18, assembly agent, fresh session): made pieces over the LOD shell, worn parts under, exposure, reviews
Scratch /mnt/data/hifipushie/assembly/r54/ (glbio.py: a GLB mesh as an export part; probe1-5.py; zoom renders zoom/, zoom4.png).
- Step 1 POCKET / LAPEL FANS (LOD1-3 fronts; zoom4.png = rc2c LOD2 calf back | pocket front | lapel | LOD1 pocket, game rig
  at 1-1.3 m): the coat's made pieces (pockets, lapels, buttons: the 1,176 triangles after its 2 x 6,298 shell triangles,
  probe1) were decimated at the coat's share (LOD2 0.11 -> 134 triangles: pockets became fans of a few long triangles) and
  sat 2.6 mm (median) over a shell whose decimation error is several mm: 35 of 128 made vertices under the decimated outer
  shell at LOD2 (probe2). FIX (lods): _lod_shell decimates the made pieces at max(share, LOD_MADE_FLOOR 0.35) and
  _lift_made puts every made vertex whose decimated outer shell is less than LOD_MADE_GAP (1 mm) inside it (within
  LOD_MADE_REACH 8 mm along its normal) back out to 1 mm over it. On the real coat (probe5): made 412 triangles at LOD2 / 3,
  lifted 35-42 vertices, shell through 0 (was 35); coat LOD1 / 2 / 3 4,026 / 1,796 / 1,040 (+290 / +278 / +354).
- Step 2 PALE CALF BLOTCHES (LOD2 back) = THE SOCKS through the jeans: the socks (446 triangles, < MIN_PART, kept whole) end
  mid-calf under the jeans; the decimated jeans sank into them: socks vertices poking through the jeans 1 at LOD0 -> 101
  at LOD2 (probe4, lods.under_depth); the body through the sweater at the collarbone (the skin patch on the LOD2 lapel crop)
  is the same fault. Not the atlas (no jeans triangle samples pale texels at any LOD, probe3). FIX (asset.export, general):
  parts worn under garments that are not garments (any part with >= LOD_PUSH_WORN_MIN 20 LOD0 vertices under a garment,
  except the head's meshes: their neck seam ring meets the body's) join the LOD push-under stack against every garment,
  with a LOD0 mask (lods.under_at_lod0): only vertices whose nearest LOD0 vertex was UNDER a garment move (a shoe collar
  over the hem stays over). Tests test_lod_made_pieces_stay_over_their_shell (rumpled shell + pocket 1.5 mm over: bare
  decimation puts the shell through, the fix keeps >= 30% and 0 through) and test_lod_worn_parts_pushed_only_where_under_
  at_lod0; 6 LOD / cull tests PASS. Committed 5cd4cf17; re-export rc2d (= rc2c + these) -> exp/rc2d_tess, r54/chain.sh
  (export, tris, game check LOD0 + LODs at switch + close-ups r54/ge/z1-3).
STATE: fixes committed, rc2d exporting. NEXT: exposure test over clips, photo-light face renders (r54/pl), reviews, sheet.
- Step 3 PER-FRAME EXPOSURE of the garment cull (general, committed b93283fc): blender_game shots take "dump": npz (every
  mesh's rest and posed world vertices, the clip retargeted + shapes evaluated; views [] renders nothing).
  asset.cull_exposed_keep(p, covers, name, cover_names, poses, keep) poses the under garment and its covers from the dumps
  (each vertex takes its nearest dump rest vertex's posed position, normals from the posed winding), reruns
  cloth_under_keep per frame and keeps any triangle uncovered in ANY frame; asset.export(cull_poses=<glob | list>) applies it
  inside the garment cull (report[un]["cull_exposed"]). Two-pass by design: dump from an export WITHOUT the garment cull
  (rc2b's LOD0: same garment vertices), then export with cull_poses. Test test_cull_restores_faces_exposed_in_a_pose (cover
  rides up 6 cm: the band it leaves comes back; a still pose restores nothing). Tess (r54/expo.py, 16 frames: walk 0-0.9 s,
  run 0-0.5 s, idle 0-3 s; r54/poses/*.npz): jeans culled 3,466, exposed in some frame 1,664 (worst run 0.0: 988; idle 34);
  sweater culled 2,010, exposed 668 (idle ~400: the arms down vs the A-pose rest). NOTE the test is the cull's own ray
  coverage (cover within 60 mm along the normal), not camera visibility: a coat skirt flaring > 60 mm off the jeans counts
  as "exposed" though a camera may still not see them. Conservative on purpose (the brief: any culled face ever exposed
  comes back): ~2.3k triangles back at LOD0 (LOD0 ~88.5k / 103k, clothing ~22.7k / 25k, still under). (My GLB probe must
  turn glTF Y-up into Blender Z-up first: the first run "exposed" everything.) rc2d re-export restarted WITH cull_poses.
STATE: exposure check committed; rc2d = rc2c + made-piece floor / lift + worn-part push + exposure restore, exporting.
- Step 4a FACE REVIEW UNDER stage.photo_light (likeness, per gates.md; r54/pl/rc2c_pl_*: r44's photo_light_tp_k19 rig, the
  RC's A2 smile shapes; LOD0 face of rc2c = rc2d's). Tiles r54/blind/face_{neutral,smile,jaw}.png (ref | result, no
  captions), fresh blind reviewer: DIFFERENT on all three. MAJORs: face outline long / narrow with a pointed chin (ref a
  softer oval, rounder chin); eyes small flat slits, weak lid fold / lash line; brows thick flat bars set high (ref arched,
  tapered, close); lips a flat pink smear, no bow, too wide; hair slicked cap + stringy temple strips, paper-flap tail (ref
  loose waves, centre part); smile: eyes near shut, narrow straight grin, blocky teeth, no cheek lift / nasolabial; jaw:
  lips a uniform gasket ring. Artefacts under the photo light: dark smudges / stripes at the temples where the hair cards
  meet skin, a hard edge along jaw / under the chin, a flat grey band under the lower lids (worst at smile), card edges on
  the fringe. NO nostril wedge and NO ear stripes under the photo light: CONFIRMS r53 (both are the game rig's 2 deg key
  casting hard shadow maps, not textures). Rings / speckle not seen at this size.
  GAME RIG KEY, realistic? A 2 deg sun is a near-point source (the real sun is 0.53 deg, so it is if anything softer than
  daylight): outdoor noon light does put a hard nose shadow on the lip. But game character lighting rarely shows it that
  hard: shadow maps are filtered (PCF / PCSS, cascades of a few cm per texel at 1 m) and faces get soft self-shadow or
  contact-shadow tweaks. A game-like key would be ~5-15 deg angle (or a filter radius of that size). Not changed here: the
  rig is the readability check's (gates.md); flagged for the coordinator.
- Step 5 rc2d export (exp/rc2d_tess, cull_poses = r54/poses/*.npz): sweater 666 and jeans 1,664 culled triangles restored
  (exposed in a clip frame; worst idle 0.0 / run 0.0). LODs, tris (r54/tris.txt) and the game check (r54/ge: x_*, l0-l3_*,
  close-ups z1-z3_{calf_back,pocket_front,lapel_front}) chained by r54/chain.sh -> r54/GE_DONE.
STATE: rc2d exported (LODs / game check running at handover). NEXT: see handover.

## Handover r54 (assembly agent, tool-call budget)
- DONE (committed locally, never pushed): lods.LOD_MADE_FLOOR / _lift_made (made pieces over the decimated shell),
  asset LOD_PUSH_WORN + lods.under_at_lod0 masks (socks / body under garments at every LOD), blender_game shot "dump" +
  asset.cull_exposed_keep + export(cull_poses=) (cull checked over 16 walk / run / idle frames); 3 tests, PASS with the
  LOD / cull tests. Face review under the photo light: DIFFERENT x3 (gap list in step 4a); wedge / ear stripes confirmed as
  the game rig's hard key (not textures).
- rc2d TRIANGLES (r54/tris.txt): LOD0 89,408 / 103,000, LOD1 42,162 / 51,500, LOD2 24,604 / 25,750 OK; LOD3 12,524 / 12,360
  OVER by 164 (the made-piece floor's ~+354). Fix: a lower floor at LOD3 (e.g. LOD_MADE_FLOOR 0.2 for ratios < 0.08) or
  take it from the coat's share. ALSO: the worn-part rule picked up props worn OVER the garments (badge, badge_card, clip,
  lanyard, laces, shoes: their back faces see the garment outside them, so 25-103 "under" vertices each); only a few moved
  (badge 6), but the rule should require a part to be MOSTLY under (e.g. under / in-reach > 0.5) or skip parts whose
  normals face away from the cover. Socks / body entries: check the full log line in out/exp_rc2d_tess.log.
- rc2d LOOK (r54/zoom4_rc2d.png = r54/ge/z2 calf back | z2 pocket | z2 lapel | z1 pocket, vs r54/zoom4.png rc2c): the
  POCKET FANS ARE UNCHANGED, so step 1's diagnosis was WRONG or incomplete: the made pieces are no longer under the shell
  (0 by under_depth), yet the grey radial fans remain. Likely the fans are shading on the pocket's own triangles (normals /
  tangents carried by nearest-LOD0 barycentric transfer onto long fan triangles, or the pocket lies in the OUTER shell's
  uv islands, not in "rest"): next, render LOD2 with a flat normal map / plain material to split geometry from shading,
  and check which triangles the fans are (outer vs rest). The buttons now read as grey cones (made floor lets them be
  decimated? they were kept whole below MIN_PATCH before: check). Calves: one blotch of two gone (left calf one remains);
  the collarbone skin patch and the coat hem's dark slivers are GONE; the orange sweater at the lapel edges is smaller but
  still there.
- NEXT: (0) the pocket fans (above), LOD3 floor, the worn-part rule, re-export (cull_poses as in run_rc2d.sh). (1) when r54/GE_DONE (chain still running at handover): tris (r54/tris.txt vs hero 103,000 / 51,500 / 25,750 / 12,360; LOD3 was 11,784 + ~354 made
  floor: watch it), LOOK at r54/ge/z{1,2,3}_* (pockets / lapels / calves) and l1-l3 backs/fronts vs r53/ge. (2) blind LOD-back
  review rc2 (r51/ge/l*_back) vs rc2d (r54/ge/l*_back): review-ab CLI only after 2026-10-19 13:00 MT, else a fresh blind
  subagent. (3) Joe's sheet: python3 r52/sheet.py r54/ge workspace/human_renders/gr_r54_tess_rc2d.png "<title>" (reference
  first, captions; add the photo-light face row from r54/pl/ if the sheet takes it). (4) RC_tess.md: top blockers updated
  below at handover, refresh with the LOD look. (5) The coat freeze from dress-tess had not landed: re-export with it when
  it does (dump poses again from a no-garment-cull export if the coat / garment meshes change: cull_poses maps by rest
  position within 2 mm, unmatched vertices count as uncovered, i.e. kept).

## Garrett (2026-10-18, assembly agent "assembly_garrett", first session; branch worktree-agent-a369eb41a63e51a4a)
Joe: "focus on what's remaining to get game ready Garrett and Tess." Tess's recipe run on Garrett end to end with today's
pieces, to surface every gap. Scratch /mnt/data/hifipushie/assembly_garrett/ (env.sh, run.sh = light, export.sh = heavy
slot CAP=20G, rge.sh = NICO-TOP game check for ANY asset name + its LODs, mk_ag_garrett.py, mkshots.py, freeze*.sh, logs/).
Gap list: /mnt/data/hifipushie/assembly_garrett/RC_garrett.md.
- Pieces (bin/approve list): head gp_h6c APPROVED; body (dg_garrett) NOT approved; jacket c12_n18c approved on his OLD body
  (j17k used: the drape on dg_garrett's body, WIP); skin gp_h6c_s15 (projskin round garrett_g14; rounds g15 / g16 = s16 / s17
  exist) NOT approved; hair hg_G88a (strands) NOT approved; shirt, trousers, shoes NOT approved.
- CODE: the export needs THREE unmerged branches: the Tess assembly branch (worktree-agent-ad0815704f43e0e00, 179 commits
  past main: main's game_ready.md is ~2000 lines behind), hair-heads2 (G88a's groom keys: loose.blend / body_along /
  lift_fall / trace), projskin2 (skin.zone_colors in gp_h6c_s15). This branch = all three merged (clean merges).
- Model ag_garrett (mk_ag_garrett.py): dg_garrett (body + shoes / socks / soles + garment defs) + gp_h6c_s15's base.head,
  base.lashes, skin + hg_G88a's hair copied whole (locks too) + frozen jacket j17k and the shirt as drawn under it
  (dress-garrett's run.py freeze=, their code, cached only). A frozen garment takes ONLY cloth.FROZEN_KEYS: the script keeps
  color / detail / roughness / sheen and drops the sim keys. A garment with no frozen drape is DROPPED (it would be simulated).
- TROUSERS BROKEN: t5 (q_dg_t5.txt overrides on dg_garrett) is no longer in the cloth cache (cached_only -> None: its key
  moved, likely with the shirt under it), and the light out/dg_t5.pkl lacks what the export's maps need. Garrett exports with
  bare MakeHuman legs. Owner: dress-garrett (freeze= at the end of every final sim).
- TESS ASSUMPTIONS found: (a) v60's face shapes use TESS's fitted smile / jaw (HP_SMILE_FIT=fx/smile_w4_shape.npy,
  HP_JAW_FIT=fx/jaw_w1_shape.npy: env vars applied to WHATEVER head is exported): Garrett gets the generic (hand prototype)
  shapes, so the A2 mix (measured on Tess's fitted shapes) is not the same smile on him. FIX: faceshapes.env_fits() + a
  WARNING line in the export for each one set (test_game_ready.test_per_character_face_fits_from_the_environment_are_reported).
  The right fix is per-character fits in the SPEC (base.head), not env: open. (b) base.head.teeth_place and teeth_lower
  max_triangles exist only in Tess's v54 head. (c) assembly/rge2.sh copied ga_tess.glb by name: rge.sh here takes any name.
  (d) spikes/offload/job_ge.py never passed an anim source, so "anim" shots had no clip: FIXED (anim.glb in the job folder).
  (e) dress-garrett's run.py freeze= names any garment garrett_jacket.pkl (their script). (f) Tess's gate tests
  (HP_FACE_KEEP_SPEC, HP_SQUINT_SPEC) point at her specs.
STATE: export ag_garrett_v1 running ({"role": "hero", "lods": true}). NEXT: game check (rge.sh), sheet, blind review.
### Handover (assembly_garrett session 1, tool-call budget)
- DONE: model ag_garrett; jacket + shirt frozen (assembly_garrett/frozen/); three branches merged here; two general fixes
  (env_fits warning + test; job_ge anim); RC_garrett.md gap list (top: trousers BROKEN, code on 3 unmerged branches,
  face shapes Tess-tuned).
- IN FLIGHT: export exp/ag_garrett_v1 (heavy slot; logs/exp_v1.log, "EXPORT EXIT"). Nothing else waits.
- NEXT: (1) read exp_v1.log: hair card count, budgets per LOD, the cloth cut-under; (2) bash rge.sh ag1 exp/ag_garrett_v1
  shots_ag.json, then bin/offload wait ag1; (3) Joe sheet (training front photo first, big labels); (4) blind tile review;
  (5) ask dress-garrett for a full freeze of the trousers (their run.py freeze= after the final sim).
- NOT done: no renders, no sheet, no review, no look-first verdict (nothing rendered yet).
- UPDATE: export ag_garrett_v1 FAILED at the bake (~70 s): "Cycles ran out of shader stack on material(s) ['part:body']"
  (the s15 skin stack + paint layers; the guard in the export refuses a black bake). Before it: body quality TORN OR TANGLED
  at lm_lid_lower_in.L (by eye_front.L), 120 folded edges; teeth_lower 68 folded edges. NEXT (first): count body layers with
  height in paint.layers(ag_garrett) vs Tess's rc_tess (same code), find which s15 / projskin2 layers cost the stack, and ask
  the skin agent (owner) to thin them or mark broad masks "vertex": true; then re-export (export.sh ag_garrett ag_garrett_v1).
  Nothing is in flight now.

## r55 (2026-10-18, assembly agent, fresh session): pocket fans, buttons, LOD3 budget, worn-under rule
Scratch /mnt/data/hifipushie/assembly/r55/ (p1-p7.py: probes on exp/rc2d_tess GLBs; NOTE glTF is Y-up: height = y,
front = +z; my first pocket-box counts used Blender axes and were all 0).
- POCKET FANS (coordinator: not fixed by r54): NOT made pieces and NOT the shell over them. rc2d LOD0's made group (the
  triangles after the two shells) is the collar / lapels (1,320) + 4 buttons (174 each) + 8 thread bits (6): its bbox is
  the chest; the hip pockets are drawn on the OUTER shell (one cloth layer there: 1 neighbour within 6 mm, p50). At LOD2,
  144 of 270 pocket-box triangles (outer 72 + its rebuilt inner 72) are WOUND AGAINST their corners' normals: decimation
  folded them over; rendered back-facing they shade dark = the radial fans. LOD0 / LOD1 there: 0. Not the seam weld (off:
  still 26 folded there; a "don't weld along the same border" filter changed nothing: reverted). FIX (lods.lod_part,
  LOD_REWIND): every decimated triangle wound against its transferred vertex normals is wound the other way (coat probe:
  folded 69 / 29 at LOD2 / LOD3 -> 0).
- BUTTONS as grey cones: they sat in the made group, decimated welded with the lapels. FIX (lods._small_pieces,
  LOD_KEEP_PIECE 200): a made piece that is its own small connected piece is its own mesh, kept whole at ratio >= 0.1
  (LOD1-2), LOD_KEEP_PIECE_FAR 0.15 below (LOD3).
- LOD3 BUDGET: made floor now min(LOD_MADE_FLOOR 0.35, LOD_MADE_FLOOR_X 2 x ratio) (LOD2 stays ~0.27-0.35, LOD3 ~0.15);
  buttons whole add ~600 at LOD2 (25.3k of 25,750 expected). LOD3 was still ~70 over, so: small parts (< MIN_PART, kept
  whole) take max(ratio, LOD_SMALL_FAR 0.5) where their ratio < LOD_SMALL_FAR_RATIO 0.15 (LOD3 only), never the eyes
  (LOD_SMALL_KEEP: the cornea). ~4.9k of LOD3 was small parts kept whole; expect ~-2k.
- WORN-UNDER RULE: lods.under_at_lod0(share=True) gives the share of in-reach vertices that are UNDER a garment; asset
  LOD_PUSH_WORN_SHARE 0.85. rc2d LOD0 (p7): socks 0.99, body 0.89, shoes 1.00 (collar under the jeans hem: 46 vertices,
  those are under), vs badge 0.49, lanyard 0.48, clip 0.58, laces 0.67, badge_card 0.83 (thin margin).
- Test test_lod_buttons_whole_folds_rewound_small_parts_far; test_lod_made_pieces_stay_over_their_shell's floor check
  follows the X rule. (The rewind assert holds on the test sheet but I did not show the sheet folds without the fix.)
- Dress-tess: no "FROZEN FOR EXPORT" in agent-ac06d0eb5553e576b's cloth.md: no coat freeze to take.
STATE: fixes in code + tests pass. NEXT: re-export rc2e (cull_poses as rc2d), tris, game check + close-ups, look.
- LEFT CALF BLOTCH (rc2d LOD2, p8.py): 22 SOCK vertices through the decimated jeans (x 0.17, 19 cm up, back); body / shoes
  0. The r54 mask moved only vertices UNDER the jeans at LOD0, and these had no jeans within reach there (a loose leg). FIX
  (asset LOD_PUSH_WORN_NOT_OVER): every vertex NOT OVER a garment at LOD0 may move (the shoe collar over the hem still
  stays). Coat 74 / sweater 42 vertices "through the jeans" at LOD2 are the coat / sweater over them (expected).
  (Process slip: killing my stale export with `kill -9` on a "hv.py" pattern may have killed another agent's hv.py job
  around 17:41; a haircards hv.py job was running again at 17:42.)
STATE: committed; rc2e export restarted with all r55 fixes (r55/chain.sh: export, tris, game check, close-ups z1-3).
- rc2e EXPORTED (exp/rc2e_tess; all r55 fixes; cull_poses r54/poses). Triangles (export log): LOD0 89,342 / 103,000,
  LOD1 42,608 / 51,500, LOD2 23,227 / 25,750, LOD3 10,033 / 12,360: ALL UNDER (LOD3 was 12,524). NOTE the small-part rule
  also fired at LOD2 (the body-side ratio there is < 0.15: shoes 371, laces 288, clip 248 ...; tongue / eyes whole): fine
  for the budget, but set LOD_SMALL_FAR_RATIO to ~0.1 if LOD2 props look coarse. Worn-push now: shoes (100%), socks (99%),
  body (93%); badge / clip / lanyard / laces / badge_card out.
- LOOK (r55/l2_rc2d_vs_rc2e.png: LOD2 at its switch distance, rc2d front | rc2e front | rc2d back | rc2e back): the grey
  radial POCKET FANS are GONE (pocket outlines read as pockets), the LEFT CALF BLOTCH is GONE. Close-ups (r55/ge/z*),
  buttons, lapel-edge sweater: renders were still running at handover (r55/ge_all.sh -> r55/GE_DONE).

## Handover r55 (assembly agent, tool-call budget)
- DONE (committed locally, never pushed): lods LOD_REWIND (folded decimated triangles wound to their normals: the pocket
  fans), LOD_KEEP_PIECE (buttons whole at LOD1-2), made floor min(0.35, 2 x ratio), LOD_SMALL_FAR (small parts halve where
  their ratio < 0.15), asset LOD_PUSH_WORN_SHARE 0.85 + LOD_PUSH_WORN_NOT_OVER (sock through the LOD2 jeans). Tests pass
  (test_game_ready 30). rc2e exported; triangles all under; LOD2 look: fans and calf blotch gone.
- NOT DONE: (a) the NEW COAT FREEZE from dress-tess s18 (coordinator, at handover):
  /mnt/data/hifipushie/dress_tess/frozen/2026-10-18_s18/{coat,sweater,jeans}.pkl (cloth.freeze, dt_tess v112; coat left front
  = mirror of the approved right, crush 0.56 mm; sweater / jeans unchanged). Put them into rc2_tess's cloth (find how
  r50/mk_rc.py / r51/mk_rc2.py took the previous coat), then since the coat mesh changes: dump poses again from an export
  WITHOUT the garment cull (r54 step 3: cull_poses maps by rest position within 2 mm), export with cull_poses, game check.
  Check at 1 m front: the left front, the grey strip at the inner front edge, the smears. (b) LOOK at r55/ge/z{1,2,3}_*
  (buttons, lapel-edge orange) when r55/GE_DONE. (c) blind A/B on the LOD backs, rc2 (r51/ge/l*_back) vs the new export.
  (d) Joe's sheet: python3 r55/sheet.py <ge dir> workspace/human_renders/gr_r55_tess.png "<title>" (r55/sheet.py adds a
  PHOTO LIGHT row from r54/pl beside the references, GAME RIG captions on the game row, LOD2 pocket / calf close-ups).
  (e) RC_tess.md (/mnt/data/hifipushie/assembly/RC_tess.md): add the r55 numbers; blockers 5 (LOD fans / calves) -> fixed
  on rc2e pending the close-up look.
- Process slip: a `kill -9` on a "hv.py" pattern while stopping my stale export may have killed another agent's hv.py job
  (~17:41).
- r55 CLOSE-UP LOOK (r55/zoom4_rc2e.png = z2 calf back | z2 pocket | z2 lapel | z3 pocket; vs r54/zoom4_rc2d.png): calf
  blotch GONE. LOD2 pockets: the dark grey fans are gone, but FAINT PALE FAN STREAKS remain (the folds are still there
  geometrically, only wound right now: the next step is to prevent the fold, e.g. re-decimate the folded region at a
  higher share or reject folding collapses). Buttons: round, no longer grey cones, slightly lumpy. Orange sweater at the
  lapel edges: UNCHANGED (two small patches; not addressed). LOD3 pockets read as slits (fine at 12.9 m).

## r56 (2026-10-18, assembly agent, fresh session): s18 coat freeze, pocket fans at the root, buttons, rc2f
Scratch /mnt/data/hifipushie/assembly/r56/ (q1-q9.py probes on the rc2e coat GLB; mk_rc2f.py; chain1.sh).
- (1) LOOK rc2e close-ups (r55/ge/z{1,2,3}_{lapel,pocket}_front): LOD1 buttons round grey discs, ORANGE SWEATER specks at
  both lapel edges (notch, chest pocket corner) already at LOD1; LOD2 left hip pocket still shows the radial fan lines,
  dark jeans triangles through the coat at the crotch opening (LOD2 / LOD3); LOD3 buttons cones (0.15, far: accepted),
  the sweater neckband gone at LOD3 (skin + a grey rectangle at the lapel V).
- (2) rc2_tess now wears dress-tess s18's freeze (r56/mk_rc2f.py: each garment = dt_tess's definition, so the look keys
  FROZEN_KEYS take from the spec come with it: coat detail.woven.crush 0.00056 (rc2 had 0.0016), + frozen = the s18
  pickle). Backup of the old spec: r56/rc2_tess_spec_before.json. Pass 1 (r56/chain1.sh): export rc2f0_tess WITHOUT the
  garment cull / LODs / face shapes, then the 16 clip frames dumped to r56/poses (r54 step 3).
- POCKET FANS, root cause (q5-q7): not folds. The patch pockets are their OWN small pieces of the coat's outer shell (106
  triangles each, 62 of their vertices on the border, wound inward, the inner shell facing out), and the welded decimation
  holds borders: at LOD2 each became a ~60-triangle fan from one vertex (no interior left), the long triangles shading as
  pale streaks; LOD_REWIND only turned the wrongly wound ones. No dihedral > 120 deg anywhere at LOD0 / LOD2. A fold guard
  (cut out the LOD0 triangles around folds, decimate them apart at 2x / 4x) did not help (still "folds" at 4x: the lookup,
  not geometry): left in code OFF (LOD_FOLD_GUARD = ()). FIX lods.LOD_KEEP_OUTER_PIECES: small pieces (< LOD_KEEP_PIECE)
  of the outer shell are kept whole at LOD1-2 like buttons (LOD_KEEP_PIECE_FAR at LOD3), inner shell rebuilt with them.
  rc2e coat (q8): pocket-box slivers (min angle < 8 deg) LOD1 135 -> 50, LOD2 70 -> 20; coat +172 / +428 / +110 triangles
  at LOD1 / 2 / 3 (rc2e LOD2 23,227 of 25,750: room).
- BUTTONS LUMPY: _lift_made lifted made vertices one by one over the decimated shell (q9: 57 button vertices lifted, up to
  7.7 mm: a lump). FIX LOD_LIFT_RIGID: a small made piece takes its largest lift along its mean lift direction, all
  vertices (p50 1.1, p95 4.6 mm off LOD0 at LOD2; it hovers a few mm at LOD2 distance instead of bulging).
- Test test_lod_small_outer_pieces_whole_and_made_pieces_lifted_rigidly.
STATE: fixes + test in code; pass 1 (dump) running. NEXT: pass 2 = rc2f export with cull_poses r56/poses, game check,
1 m front coat look, lapel sweater patches.
- Pass 1 done: exp/rc2f0_tess (no garment cull, no LODs / shapes; 646 s, LOD0 101,348 uncull'd); 16 frames in r56/poses
  (walk 0-0.9, run 0-0.5, idle 0-3). Carry of the s18 jeans onto rc2_tess's body: max 3.58 mm. Pass 2 (r56/chain2.sh:
  rc2f export with cull_poses r56/poses + all r56 lods fixes, tris, close-ups z0-z3 incl. coat 1 m front + coat back,
  LOD switch shots, x_* game check) started on its own.
- (Process: `setsid ... & echo $!` records setsid's parent, not the job: real PIDs in r56/PIDS.)
STATE: rc2f exporting. NEXT: tris, look z0-z3 (1 m coat, lapel orange), blind A/B (r56/tiles.py), sheet (r56/sheet.py).
- rc2f EXPORTED (1474 s). Triangles: LOD0 91,971 / 103,000, LOD1 47,349 / 51,500, LOD2 28,116 / 25,750 OVER, LOD3 10,620 /
  12,360. Cause: LOD_KEEP_OUTER_PIECES also kept the SWEATER's outer-shell fragments left by the garment cull (1,557 of its
  2,268 outer triangles in pieces < 200): 3,836 at LOD1 and LOD2. FIX LOD_PATCH_GAP 6 mm: a small outer piece is kept only if
  its vertices' median distance to the REST of the outer shell's surface is under it (a patch pocket lies on the panel).
  q12 on rc2f LOD0: coat 384 kept (pockets), sweater 0; sweater 4,536 -> 1,542 / 612 / 334 at 0.34 / 0.135 / 0.074.
  (Nearest-VERTEX distance kept no pocket: the panel's vertices are ~25 mm apart; it has to be the surface.)
- LOOK rc2f (r56/ge/z0-z3, LOD0 coat at 1 m front, coat back 1.6 m): LOD0 coat CLEAN at 1 m: no blotchy smears (crush 0.56),
  pockets crisp, left / right fronts alike, no grey strip at the inner front edge (only a short thin line at her left front
  edge). Back clean. LOD2: hip pockets now clean outlines (no fan); buttons round; her left CHEST pocket at LOD2 reads as a
  crumpled patch (kept whole over a coarser panel; LOD_PATCH_GAP keeps it too). ORANGE at the lapel side: already at LOD0
  (her left chest beside the chest pocket) and LOD1 (her right chest): the sweater through the coat in the rest pose, NOT
  the LODs. r56/q10-q11 (under_depth, rc2e): ~20-50 chest sweater vertices with the coat inside them at every LOD, 2
  visible from the front at LOD1 (q11). Not fixed.
STATE: LOD_PATCH_GAP committed (LOD tests 11 pass); rc2g (= rc2f + it) export + z/l/x renders + sheet queued unattended:
r56/chain3.sh (waits for chain2's GE_DONE; PIDs in r56/PIDS).

## Handover r56 (assembly agent, tool-call budget)
- RUNNING (unattended, my PIDs in /mnt/data/hifipushie/assembly/r56/PIDS: chain2 bash 3001151 (rc2f LOD / x renders ->
  r56/GE_DONE), chain3 bash 3876188 (after GE_DONE: rc2g export -> r56/geg/{z0-3,l1-3,l0,x}_*, r56/tris_g.txt, then the sheet
  workspace/human_renders/gr_r56_tess.png -> r56/SHEET_DONE). ~25 min export + ~30 min renders.
- NEXT: (a) r56/tris_g.txt: LOD2 must be under 25,750 (expected ~24.9k); if over, LOD_KEEP_OUTER_PIECES=False costs only the
  pocket fix. (b) LOOK geg/z2_pocket + z2_lapel (chest pocket crumple), then (c) blind A/B: python3 r56/tiles.py (edit its
  r56/ge paths to r56/geg; pairs rc2 r51 LOD backs / fronts + rc2e r55 close-ups vs new; key blind/abkey.json) to a fresh
  blind subagent (review-ab CLI only after 2026-10-19 13:00 MT). (d) Check the sheet (r56/sheet.py = r55's + COAT 1 m LOD0
  tile), send to Joe. (e) LAPEL ORANGE is a LOD0 sweater-through-coat poke beside her left chest pocket (rest pose): look at
  the garment cull / push-under at LOD0 (lods.push_under_layers runs per LOD; LOD0 has no push) or ask dress-tess.
- Did NOT do this session: the A/B and the sheet (budget); LOD_SMALL_FAR_RATIO untouched (LOD2 props not judged coarse).
- Process: `nohup setsid bash x.sh & echo $!` records setsid's parent, not the job: find the real PID with pgrep -f <script>.

## r57 (2026-10-18, assembly agent, fresh session): the orange sweater at the lapels, rc2g check, A/B, sheet
Scratch /mnt/data/hifipushie/assembly/r57/ (q13-q15.py probes on the rc2f GLBs; shellfind.py recovers a GLB part's
outer-shell count: outer triangles, then the inner ones in the same order).
- ORANGE AT THE LAPELS, two causes (q11 / q13-q14 on rc2f):
  (a) LOD0 has no push-under at all: rc2f LOD0 sweater vertex [0.201, 1.249, 0.078] (her left chest, beside the chest
      pocket) 0.4 / 1.0 mm outside the coat's two shells (the 1 m speck); 3 sweater vertices poking at LOD0 in all, and
      ~5 mm on her upper back (z -0.07, y 1.24: hidden from the front, seen from behind).
  (b) LOD1 right chest [-0.154, 1.27, 0.086]: three long sweater faces 3.5 mm OUTSIDE the coat while all their vertices
      are 2.0 mm under it (push_under_layers had done its job per vertex; the coat bends between them).
  FIX (general): lods.push_under_layers also tests each outward face's centroid along the face normal
  (LOD_UNDER_FACES; lods.cover_depth = under_depth's ray test for any points); asset.export runs it at LOD0 too
  (LOD0_PUSH_UNDER, gap LOD0_UNDER_GAP 1.5 mm = cloth.PUSH_UNDER_GAP; garment layers only: asset._garment_stack).
  q15 on rc2f: LOD0 sweater poking 3 -> 0 (24 vertices moved, max 6.2 mm, the upper back); LOD1 chest faces uncovered
  from the front 5 -> 0 (4 poking faces, max move 5.1 mm); with faces off LOD1 stays 5.
  (Without the shell layout every inner-shell vertex reads as poking: 897, moves of 60 mm. The export's parts carry
  p["shell"]; offline probes on GLBs need shellfind.)
- Test test_lod_under_faces_pushed_where_the_cover_dips_between_vertices; LOD / under tests 12 pass (pytest: the file's
  own __main__ sits mid-file and runs only the tests above it).
STATE: fix + test committed; rc2g (r56 chain3, WITHOUT this fix) exporting. NEXT: rc2g tris + looks, then rc2h with the fix.
- rc2g (r56 chain3, without the r57 push) triangles: LOD0 89,995 / 103,000, LOD1 43,273 / 51,500, LOD2 24,096 / 25,750,
  LOD3 10,146 / 12,360: ALL UNDER (LOD_PATCH_GAP worked: sweater 280 at LOD2).
- LOOK rc2g (r56/geg; montage r57/rc2g_lods.png): LOD0 coat at 1 m CLEAN (pockets crisp, no smears, buttons round).
  LOD2 close-ups: her LEFT hip pocket a twisted vertical flap standing off the panel, her left chest pocket a crumpled
  flap (both kept whole over a coarser panel that no longer matches them); a LARGE orange patch at her right chest and a
  speck beside her left hip pocket (= the r57 face-poke cause; still visible as a speck at the 6.2 m switch distance,
  front). LOD backs at switch distances clean; LOD2 back: a pale fleck on the jeans' left calf.
STATE: rc2g under budget, LOD2 pockets / orange open. NEXT: rc2h (r57/chain4.sh: push-under at LOD0 + faces) looks.
- BLIND A/B (fresh subagent, review-ab CLI not available before 2026-10-19 13:00; r57/tiles.py r56/geg r57/blind_g, key
  r57/blind_g/abkey.json): rc2g vs rc2 (r51) LODs at switch distances front / back, vs rc2e (r55) LOD1-2 lapel / pocket
  close-ups. rc2g better on ALL 10 tiles; MAJORs rc2g 1 vs old 20. rc2g's one MAJOR: LOD2 lapel close-up, a large orange
  patch at her right chest / shoulder (the r57 face-poke). Old faults named: jeans through the coat back, orange
  elbows, fanned pockets / lapels, lumpy buttons, a jeans flap at the hip.
- SHEET workspace/human_renders/gr_r56_tess.png checked: reference first per pair; fixed misleading / clipped captions
  (row 2 photo-light faces are rc2c renders from r54: now captioned "rc2c ..." and said in the title; "GAME RIG neutral"
  overflowed into the next column; the rc2c smile tile is a mouth crop: "rc2c mouth"). r56/sheet_r56_orig.py = before.
STATE: rc2g A/B won 10 / 10; sheet fixed. NEXT: rc2h looks (r57/geh) vs rc2g.
- rc2h (exp/rc2h_tess = rc2g + the r57 push: LOD0 sweater 4 vertices / 1 face and jeans 2 / 1 poking -> 0; LOD1 / 2 / 3
  sweater 10 / 6 / 2 -> 0): triangles identical to rc2g (positions only). LOOK r57/lapel_g_vs_h.png (rc2g top, rc2h
  bottom, LOD0 / 1 / 2 lapel close-ups): the orange specks are UNCHANGED (LOD0 her left chest by the armhole, LOD1 her
  right chest, LOD2 a large hexagonal patch at her right chest by the armhole + a speck under her left chest pocket).
  So the r57 push fixed real pokes (q15) but NOT these specks. Ruled out: holes in the coat along +z (q16: a ray grid
  behind both chest sides hits the coat everywhere, LOD0 and LOD2), orange in the coat's basecolor atlas (0 orange texels).
  Suspects, unchecked: the sweater SLEEVE / armhole poking out at the coat's armscye seen at the close-up camera's angle
  (q13 only tested +z rays, centroids, |x| 0.11-0.3), or the sweater's shading leaking through a coat face the renderer
  culls (back-facing coat triangles: the coat is two-sided by shells, materials single-sided?).
STATE: rc2h exported + rendered (r57/geh, sheet workspace/human_renders/gr_r57_tess.png); specks open.

## Handover r57 (assembly agent, tool-call budget)
- Nothing running (r57/chain4 finished; r56 chains finished).
- Best RC: rc2h (exp/rc2h_tess; r57 push-under at LOD0 + per face, commits 378e0965 ...). Triangles LOD0 89,995 / 103,000,
  LOD1 43,273 / 51,500, LOD2 24,096 / 25,750, LOD3 10,146 / 12,360: all under. Joe's sheet for rc2g:
  workspace/human_renders/gr_r56_tess.png (captions fixed); rc2h: gr_r57_tess.png (same layout; checked; title shortened: the old one ran off the sheet and claimed "sweater kept under the coat", which the specks contradict).
- Blind A/B rc2g vs rc2 / rc2e: rc2g 10 / 10, MAJORs 1 vs 20 (r57/blind_g). Not rerun for rc2h (same look).
- NEXT: (a) THE ORANGE SPECKS: render an object-ID (flat colour per part) frame from r56/shots_zoom.json's lapel camera
  at LOD0 and LOD2 to name the part and spot that shows orange (sweater body vs sleeve), then cast rays FROM THAT CAMERA
  (not +z) through the speck pixel to see which layer is first. (b) LOD2 pockets: her left hip pocket stands off as a
  twisted flap and her left chest pocket crumples at LOD2 (kept whole over a coarser panel): project kept pieces onto the
  decimated panel + a lift, or drop LOD_KEEP_OUTER_PIECES at LOD2 only and accept fans (A/B them). (c) LOD2 back: pale
  fleck on the jeans' left calf.

## r58 (2026-10-18, assembly agent, fresh session): the orange specks named, LOD2 pockets, calf fleck, rc2i
Scratch /mnt/data/hifipushie/assembly/r58/.
- SPECKS NAMED: blender_game GE_FLATID=1 (debug: a flat emission colour per object, back faces at a third, legend printed
  as @@flatid) on rc2h LOD0 / LOD2 from r56's lapel / pocket / calf cameras (r58/fid/): the LOD2 hexagonal patch at her
  right armhole is the SWEATER's front faces (same colour as the sweater in the opening), not a coat hole or coat back
  faces. The shot poses nothing (r58/lapel2_dump.npz: every mesh 0.0 mm from rest), so it is the GLB's own geometry.
  r58/pick.py (Blender ray_cast through the pixel from the shot's camera): sweater f74 at (-0.182, -0.079, 1.272)
  (Blender axes) 5 mm IN FRONT of the coat (f464 / its inner twin), the body 6 mm behind. The vertex test, the r57
  centroid test and my +z / camera-ray probes of vertices and centroids (r58/q1.py, q1v.py) all said covered: the coat
  bends between the sweater's sample points (LOD2 sweater 140 outer faces, a few cm each). r58/q2.py: a barycentric grid
  (4 steps per edge) finds 16 poking faces at LOD2 where the centroids find 0 (LOD1 6 vs 0, LOD3 2 vs 0, LOD0 19 vs 2).
- FIX (general, lods.push_under_layers): each outward face is tested at lods.face_grid(LOD_UNDER_FACE_GRID = 4): the
  centroid + 12 grid points without the corners; a point more than LOD_UNDER_FACE_DEEP (8 mm) outside its cover is a face
  running out from under the cover's edge (sweater cuffs past the coat sleeve: -20 mm), left alone. r58/q3.py on rc2h
  LOD2: the pick ray's first layer sweater -> COAT at both speck pixels; 5 poking faces, 26 vertices moved, max 9.5 mm.
  Test test_lod_under_face_grid_finds_pokes_away_from_vertices_and_centroids (a dent at an edge middle: centroids miss
  it, the grid fixes it; the DEEP cap leaves a run-out alone); LOD / under tests 13 pass.
STATE: specks fixed in code + test, committed. NEXT: LOD2 pockets, calf fleck, then export rc2i.
- LOD2 POCKETS (general, lods._lod_shell): LOD_SEAT_PATCHES re-seats outer pieces kept whole (patch pockets) on the
  DECIMATED panel: each piece vertex at its closest point on the decimated rest of the outer shell + its LOD0 signed offset
  along that face's normal (_patch_offsets / _seat_patches, within LOD_SEAT_REACH 2 cm; report key patches_seated).
  Test test_lod_patch_pockets_seated_on_the_decimated_panel (a pocket 2.6 mm over a bumpy two-sided panel ends 2.6 +- 0.3 mm
  over the 10% panel; worse without). Offline probe from the GLB is not possible (the GLB's outer splits at uv seams into
  small pieces): judged in the rc2i export.
- CALF FLECK (LOD2 back) NAMED, not fixed: flat-ID = SOCKS (r58/fid/z2_calf_back.png, with dark back faces); r58/pickcalf.py:
  sock faces at her left ankle back (Blender (0.153, -0.02, 0.17)) 4-8 mm outside the jeans hem. The decimated sock top
  under the jeans is crumpled: its vertex normals point every way within 1 cm (r58/q6.py), so push-under (along each
  vertex's own normal) pushes the wrong way / finds the far side (offline: still socks first at all 3 pixels).
STATE: seat + test committed; rc2i (r58 grid push + seat) exporting via r58/chain5.sh. NEXT: looks, A/B vs rc2h, sheet.
- rc2i (exp/rc2i_tess = rc2h + r58 face-grid push-under + seated patch pockets; r58/chain5.sh). Triangles LOD0 89,995 /
  103,000, LOD1 43,273 / 51,500, LOD2 24,134 / 25,750, LOD3 10,150 / 12,360: ALL UNDER.
- LOOK (mine, r58/h_vs_i.png, rc2h | rc2i): the LOD0 / LOD1 chest specks are GONE, and so is the LOD2 hexagonal patch at
  her right armhole; LOD2 left chest pocket reads flatter. Still there: a small orange speck under her left chest pocket at
  LOD2, her left hip pocket at LOD2 (flatter than rc2h's twisted flap but still a crumpled flap), the sock fleck on the
  left calf (expected, not fixed), and the grey neck gap at LOD3 (sweater collar cut off: both builds).
- BLIND A/B (fresh subagent, 9 tiles rc2h vs rc2i, r58/blind, key abkey.json): rc2i better on 6 tiles, rc2h on 1 (LOD2
  hips: the reviewer says rc2i's left hip pocket is "crumpled with a folded flap" and names a skin-coloured patch in the jeans
  fly), same on 2 (far LODs). MAJORs rc2i 4 vs rc2h 8. Faults both builds share: the LOD3 grey neckline gap, crumpled
  LOD1/LOD2 pockets, the calf shard.
- SHEET workspace/human_renders/gr_r58_tess.png: row 2 (photo-light faces) is now from the CURRENT build (rc2i,
  r54/shots_pl.json -> r58/pl/rc2i_pl_pl_*), so the whole sheet is one build. Captions shortened ("photo neutral" etc.:
  the long ones ran into the next column). Checked: reference first in each pair, nothing clipped.
STATE: rc2i is the best RC, 6/1/2 vs rc2h. NEXT: see the Handover.

## Handover r58 (assembly agent, tool-call budget)
- Nothing running (r58/chain5 finished).
- Best RC: rc2i (exp/rc2i_tess). Commits 5e8f95be (face-grid push-under, GE_FLATID), 7cd962d2 (seated pockets), + notes.
- Debug tools: GE_FLATID=1 bash ge.sh ... (a flat colour per part, legend as @@flatid); r58/pick.py / pickcalf.py (Blender
  ray_cast through a pixel from a shot's camera: every surface along the ray). Name the part before you theorise.
- NEXT: (a) LOD2 left hip pocket still crumples: check the report's patches_seated for the coat at LOD2 (is that pocket in
  small_o at all? LOD_PATCH_GAP 6 mm may leave it out, so it is decimated with the panel), flat-ID it, and pick-ray it.
  (b) Calf / ankle sock shard: the decimated sock top under the jeans hem is crumpled (normals every way), so push along
  the LOD0 normal of the nearest LOD0 vertex (under_at_lod0 masks have positions; add normals) or cull the sock's covered
  top. (c) LOD3 grey neckline gap (the sweater collar cut off); (d) a skin-coloured patch in the jeans fly at LOD2 (named
  by the reviewer; unchecked); (e) a small orange speck under her left chest pocket at LOD2.

## r59 (2026-10-18, assembly agent, fresh session): the white crown, LOD2 pocket / sock / fly, LOD3 neckline, rc2j
Scratch /mnt/data/hifipushie/assembly/r59/.
- WHITE CROWN NAMED (r59/cr/crown_grid*.png, r59/pickc.py = a ray pick through any game shot's pixel, with the material):
  GE_FLATID: the patch is the HAIR part (cards and some cap faces, material rc2_tess_hair_material_hair). Lights with
  specular 0 (shot "lighting" = the game rig with "specular": 0): GONE; specular only: the patch alone. Without the hair
  normal map: still there. Hair roughness 0.75 / 0.65: GONE. So it is the export's hair material: (1) the card ORM's
  roughness is max(look 0.42, 0.5) x (1.25 - 0.4 aux.b) = 0.425 on the outer, lit hair (below its own 0.5 floor), and
  (2) the combined character GLB (asset.py) gives the hair the default KHR_materials_specular (white, x2 = F0 0.04),
  where hair.py's own hair GLB and blender_hair's card material use half, in the sheen's colour. An isotropic lobe at
  0.42 on the crown's flat cards mirrors the key as one white plate. Garrett v5's GLB: the same ([2,2,2], roughness
  0.42 min): a shared cause. Specular level alone (0.25 / 0.15 tinted) did NOT remove it; roughness did.
- FIX (general, both characters): hair.CARD_ROUGH_MIN 0.6 (export ORM floor), asset.py's hair material
  KHR_materials_specular factor hair.CARD_SPECULAR 0.5 x colour hair.card_specular_tint(sheen) (no texture: F0 0.02 x
  tint), shading notes params specular_level 0.25 / specular_tint (+ a formula line), blender_game reads them (older notes:
  0.3 white as before). Probe on a copy of rc2i with the floor-0.6 ORM + tinted 0.25 (r59/cr/f6_*): the plate is gone, a
  faint warm sheen remains. Debug env added to blender_game: GE_HAIR_NONORMAL, GE_HAIR_ROUGH, GE_HAIR_SPEC=level[,r,g,b].
  Note: 0.5 x (1.25 - 0.4 b) <= 0.625, so the floor flattens almost all the aux variation (mean 0.600).
STATE: crown fixed in code (needs an export). NEXT: LOD2 pocket / sock / fly, LOD3 neckline, then export rc2j.
- LOD2 FLY NAMED (r59/fly.png: LOD0-3 crops; r59/pickc.py on the LOD2 pocket shot): the pick ray at the skin sliver hits
  the BODY (crotch) and then the coat's inside, NO jeans: a slit opened in the LOD2 jeans at the fly. r59/bnd.py (boundary
  edges, positions merged 0.2 mm): jeans LOD0 0 boundary edges in the crotch box, LOD2 12. Suspect: the LOD_BORDER_OVER
  redecimation (border collapses) of the jeans' outer panel, whose border is shared with a made piece (the fly) decimated
  apart. FIX (general, lods._welded_pieces): LOD_BORDER_SHARED skips that redecimation for a group whose border touches
  another group of the part within LOD_SEAM_WELD. Same suspect for the LOD3 NECKLINE (r59/neck.png: at LOD3 the
  sweater's top, collar band and upper chest, is gone down to a diagonal line, the culled body's edge shows): judged in
  the export. Cost: groups that relied on border collapses keep more triangles: check budgets.
- SOCK SHARD (general, lods.push_under_layers): LOD_UNDER_LOD0_NORMAL: after the rounds, a masked (worn, non-garment)
  part's vertices that still poke or have no cover along their own normal move along their nearest LOD0 vertex's normal
  (under_at_lod0(share=True) now also returns the LOD0 normals; asset passes them in the masks). LOD tests 12 pass.
STATE: fly / neckline / sock fixes in code. NEXT: export rc2j (r59/chain.sh), look, A/B vs rc2i, sheet.
- rc2j (exp/rc2j_tess = rc2i + r59 hair material + LOD_BORDER_SHARED on + LOD0-normal push; r59/chain.sh). Triangles LOD0
  89,995 / 103,000, LOD1 43,273 / 51,500, LOD2 24,134 / 25,750 (every part's count IDENTICAL to rc2i), LOD3 11,440 / 12,360
  (rc2i 10,150: jeans 346 -> 1,012, coat 976 -> 1,338): ALL UNDER. GLB hair: specularFactor 0.5, colour (1, 0.70, 0.49),
  ORM roughness min 0.60. Push-under LOD2 remaining: socks 9 -> 8, body 7 -> 4 (the LOD0-normal pass helps little).
- LOOK (mine, r59/crown_i_vs_j.png, r59/i_vs_j.png): the crown's white plate is GONE (a faint warm sheen left). Unchanged:
  the LOD2 fly slit (skin + grey), the LOD2 left hip pocket's crumpled flap, the LOD2 shin / calf sock shard; the LOD3
  neckline is NOT fixed (worse: see A/B).
- BLIND A/B (fresh subagent, 6 tiles, r59/blind, key r59/abkey.json): rc2j better on crown front, crown 3/4, face 1 m,
  calf (slight); same on LOD2 hips; rc2i better on LOD3 neck (rc2j: "a large grey wedge-shaped hole across the throat",
  lapels more shattered: the LOD_BORDER_SHARED side effect). The reviewer still calls a duller crown patch MAJOR on rc2j
  and stepped card edges on the crown silhouette (cards build).
- LOD_BORDER_SHARED turned OFF (committed): the fly hypothesis was wrong (LOD2 untouched by it, slit unchanged) and it
  made LOD3 worse + 1.3k triangles. The next export = rc2j's hair + LOD0-normal push without it (LOD3 back to ~10.15k).
- SHEET workspace/human_renders/gr_r59_tess.png (rc2j, one build; unchecked by me).
STATE: rc2j beats rc2i 4/1/1 on the hair; LOD3 regression is off in code. NEXT: Handover.

## Handover r59 (assembly agent, tool-call budget)
- Nothing running (r59/chain.sh finished, SHEET_DONE). Commits: a7618d2d (hair material), 9053d387 (LOD shared borders +
  LOD0-normal push), + this (LOD_BORDER_SHARED off, notes).
- Best RC: rc2j for the hair (the crown plate fixed), but its LOD3 carries the LOD_BORDER_SHARED regression: RE-EXPORT
  (rc2k = current code) before giving it to Joe; expect LOD2 = rc2j, LOD3 = rc2i's geometry with the r59 push.
- Debug tools: r59/pickc.py <glb> <focus bone> <lift> <dist> <dir> <W> px py ... (ray pick through any ge shot pixel,
  with the material); r59/bnd.py (boundary edges of a part in a box); blender_game GE_HAIR_NONORMAL / GE_HAIR_ROUGH /
  GE_HAIR_SPEC; shot "lighting" with per-light "specular": 0 / "diffuse": 0 splits diffuse from specular.
- NEXT: (a) LOD2 FLY SLIT: no jeans along the pick ray at the crotch at LOD2 (12 boundary edges vs 0 at LOD0), NOT from
  the border-collapse redecimation. Probe the jeans' _lod_shell offline (dump the LOD0 jeans part dict from the export, run
  lods.lod_part at 0.25, boundary edges in the crotch box after each step: decimate / seat / _lift_made / push-under).
  (b) Sock shard (LOD2 shin/calf): still there; the LOD0-normal pass moved few. Cull the sock's covered top at LOD2+ instead
  (faces whose LOD0 points were all under the jeans). (c) LOD3 neckline: the sweater's top is gone at LOD3 (138 triangles):
  check whether its collar band is a made piece dropped by LOD_KEEP_PIECE_FAR / the made floor. (d) LOD2 left hip pocket
  flap: unchanged. (e) Crown: the card silhouette steps and a dull sheen remain: cards thread. Garrett v5 shares the
  hair-material cause; his next export picks the fix up.

## r60 (2026-10-18, assembly agent, fresh session): rc2k re-export, the LOD2 fly slit probed offline, sock / neckline / pocket
Scratch /mnt/data/hifipushie/assembly/r60/. Hair: the cards thread's round 36 did NOT make f1 the default ("no round-36
build beats f1"): nothing to take.
- rc2k export started (r60/k.sh = rc2j's chain with the current code: LOD_BORDER_SHARED off) with a new debug dump:
  asset.export HP_LOD_DUMP=<pkl> pickles the LOD inputs (parts minus cards / prefabs, rigged, layer_stack, under_masks,
  ratios, above / below) so a part's LOD steps can be probed offline (r60/probe.py <pkl> <part> <k>: new boundary edges
  > 1 cm from LOD0's, clustered, after lod_part and after push-under).
STATE: rc2k exporting. NEXT: probe the jeans at LOD2 on the dump.
- SOCK SHARD (general, lods.cull_covered + asset): from LOD_UNDER_CULL_FROM = 2 on, every part worn under garments (the
  under_masks parts minus the skin: socks) drops the faces whose LOD0 points were all under a garment and more than
  LOD_UNDER_CULL_RIM = 15 mm from the nearest LOD0 point that was not (the LOD0 cull keeps a 40 mm rim for close-ups; at
  LOD2+ that rim is what showed through the jeans' calf). under_masks now carry the LOD0 "under" mask as a 5th entry.
  Test test_lod_worn_part_drops_its_covered_rim_far; LOD / cull tests 15 pass.
STATE: sock cull in code (not in rc2k). NEXT: the fly probe on the dump.
- rc2k exported (exp/rc2k_tess, current code + the dump): LOD0-2 = rc2j's counts, LOD3 10,150 (LOD_BORDER_SHARED off, as
  expected). No renders of rc2k (superseded by rc2l below).
- FLY SLIT NAMED (r60/probe.py on the dump; "lost" = LOD0 outer vertices more than 6 mm / 1 cm from the LOD surface):
  jeans LOD2 (0.11, welded): 95 of 107 crotch vertices > 6 mm off, max 41 mm; 1,080 of 2,268 outer vertices > 6 mm over the
  whole part. NOT the border-over pass (LOD_BORDER_OVER=0: identical), not the patch seating, not _lift_made, not the
  seam weld's chaining (a non-chaining weld: identical; r60/weldpairs.py: the crotch seams are coincident pairs, no
  non-manifold edges either way). It is fqmr itself: to reach 369 outer triangles it raises its error threshold until it
  collapses ACROSS the crotch fold (front to back): the slit. (LOD_WELD off: 0 lost, but 2,540 triangles; LOD_SEAM_WELD
  1 mm: crotch fine, but 170 new open borders, and only by luck of fqmr's schedule.)
- FIX (general, lods._welded_pieces): LOD_DEV_MAX = 15 mm at ratio LOD_DEV_REF 0.11, scaled by (0.11 / ratio) (LOD1 6.6,
  LOD3 33 mm): a welded group whose farthest LOD0 vertex (lods._deviation, barycentric grid) lies past it is redecimated at
  1.3 x the target, LOD_DEV_TRIES = 2 (4 put LOD3's coat 976 -> 2,304), with border collapses where the border-over pass
  was taken. Also kept: LOD_SEAM_WELD_NO_CHAIN (clusters grown nearest pair first, never two vertices of one edge, never
  wider than r): changed nothing here, safer. Probe (guard off -> on): jeans LOD2 crotch max 41 -> 11 mm, whole-part >6 mm
  1,080 -> 89; coat LOD2 447 -> 117 (the lost cluster at her LEFT HIP POCKET (+x 0.22, z 0.85) gone: item (5)); sweater
  LOD3 138 -> 216 triangles, the neckline cluster (z 1.36) no longer lost: item (4) = the same decimation, not a dropped
  made piece. Triangles (r60/counts.py): LOD1 +1.6k (sweater 638 -> 1,080, jeans 1,784 -> 2,920), LOD2 +1.0k (coat +486,
  sweater +196, jeans +340), LOD3 +1.1k: all still under (~44.9k / 51.5k, ~25.2k / 25.75k, ~11.2k / 12.36k).
  Tests: test_lod_welded_decimation_redone_where_it_strays (+ the two budget tests run with the guard off); 36 pass.
STATE: fly / neckline / hip pocket / sock fixed in code. NEXT: export rc2l (r60/chain_l.sh: renders, sheet), look, A/B vs rc2i.
- rc2l (exp/rc2l_tess = current code: r59 hair material, LOD0-normal push, LOD_DEV guard, cull_covered; r60/chain_l.sh).
  Triangles LOD0 89,995 / 103,000, LOD1 44,849 / 51,500, LOD2 25,543 / 25,750, LOD3 11,612 / 12,360: ALL UNDER (LOD2 with
  only 207 to spare: shoes 371 -> 628 and soles 143 -> 243 are welded groups the guard also grew).
  cull_covered dropped only 1 sock triangle at LOD2 / LOD3 (+ 1-3 shoe): the sock rim is NOT deep under the jeans.
- LOOK (mine, r60/i_vs_l.png, r60/pocket2_i_vs_l.png, r60/neck_i3_l3_l2.png; rc2i = r58/gei vs rc2l = r60/gel):
  LOD2 FLY SLIT GONE (the crotch meets, no skin / grey sliver). LOD2 LEFT HIP POCKET: the crumpled flap GONE (a soft dark
  crease at its lower outer corner remains). LOD2 CALF SOCK SHARD GONE (by the guard's jeans, not by the cull). LOD3
  NECKLINE: the sweater's rib collar and upper chest are BACK. NEW at LOD3: an orange sweater wedge pokes out of the coat at
  her right armhole, and jagged dark wedges on the neck above the collar (rc2i's LOD3 neck was smooth): the bigger LOD3
  sweater / body vs the coarse coat. LOD2 lapel: two tiny orange specks at her right armpit (as rc2i).
- SHEET workspace/human_renders/gr_r60_tess.png (rc2l; checked by me: layout reference | result, captions right; row 2's
  photo-light faces are rc2j's r59/pl renders: LOD0 head identical in rc2l). Face likeness unchanged (still the blocker).
STATE: rc2l fixes 4 of the 5 handover items; LOD3 armhole wedge + neck wedges new. NEXT: blind A/B (running), handover.
- BLIND A/B (fresh subagent; review-ab's claude -p not before 2026-10-19 13:00 MT; 11 tiles r60/blind, key r60/blind/abkey.json,
  rc2i vs rc2l): rc2l better 5 (LOD2 calf, LOD2 lapel, LOD3 lapel / neck, LOD2 back, LOD0 coat 1 m), rc2i better 2 (LOD2
  pocket: though the reviewer's only MAJOR there was rc2i's pocket shard + crotch slivers; LOD3 pocket: crumpled buttons),
  same 4. MAJORs rc2l 1 (LOD3 sweater wedge at her right armhole) vs rc2i 6 (pocket shard, calf shard x2, hem wedge,
  neckline missing, chest pocket shredded).
STATE: rc2l = best RC (beats rc2i 5/2/4, majors 1 vs 6). NEXT: Handover.

## Handover r60 (assembly agent, tool-call budget)
- Nothing running (r60/chain_l.sh finished: SHEET_L_DONE). Commits: b582d3c9 (HP_LOD_DUMP), 8b6dfedd (cull_covered),
  5b4bbf94 (LOD_DEV guard + non-chaining weld + tests), + notes. 36 game-ready / hair LOD tests pass.
- BEST RC: rc2l = exp/rc2l_tess (sheet workspace/human_renders/gr_r60_tess.png). Hair cards: f1 is NOT the cards default
  (hair.md round 36): nothing taken.
- Debug kit: HP_LOD_DUMP=<pkl> on an export, then r60/probe.py <pkl> <part> <k> [lods.CONST=v ...] (new open borders,
  "lost" LOD0 vertices > 6 mm / 1 cm, clusters, a crotch box) and r60/counts.py <pkl> (per part per LOD, guard off -> on):
  try a LOD change on the dump in ~1 min instead of a 25 min export. r60/lodin.pkl = rc2k's inputs (same as rc2l's).
- NEXT: (a) LOD3 orange wedge at her right armhole (z3_lapel_front): the sweater at LOD3 (216) vs the coat (1,462): run
  push-under / probe on the dump; try LOD_UNDER_FACE_DEEP or a coat guard bound at LOD3. (b) LOD3 neck: jagged dark wedges
  above the collar (body / head mesh at LOD3; the guard grew the body group 2,682 -> 2,950): compare normals there.
  (c) LOD2 headroom only 207 triangles: the guard grew shoes / soles (small welded parts); exempt parts under MIN_PART
  (or LOD_SMALL_FAR) from the guard if budget is needed. (d) cull_covered is in but nearly inert (1 sock triangle): keep
  or remove after (a). (e) remaining: crumpled LOD3 buttons, soft crease under the LOD2 left hip pocket, crown card
  silhouette steps (cards thread), the face likeness (head stages).

## r61 (2026-10-18, assembly agent, fresh session): LOD3 armhole wedge, LOD3 neck, buttons / pocket, LOD2 margin, rc2m
Scratch /mnt/data/hifipushie/assembly/r61/. Hair: the cards thread's r37c (f1 filled crown default, exar37c) is the new
best (coordinator): take it for rc2m if it merges. New offline kit on the r60 dump (r60/lodin.pkl): r61/full.py <pkl> <k>
[lods.CONST=v] [nopush=part] [save=lp.pkl] = the export's whole LOD k step (per-part ratios, lod_parts, push-under with the
far face depth, cull_covered) + triangles, pokes of every under garment (face grid, covered at LOD0), the front-neck band
(normals vs LOD0, push moves); r61/vis.py <pkl> <lp.pkl> <part> <eye> = a splatted z-buffer: points hidden at LOD0 that
are SEEN at LOD k from an eye; r61/dbg.py <lp.pkl> = sweater vs coat depth in the armhole window. ~15 s a try.
- ARMHOLE WEDGE NAMED: a LOD3 sweater face stands 11.8 mm IN FRONT of the coat at (-0.18, -0.08, 1.22) (her right
  armhole, front view) with its vertices under: push-under's face test skips face points more than LOD_UNDER_FACE_DEEP
  (8 mm) outside as "a face that runs". Not a coat seam opening (the armscye border gap is the same at LOD0 and LOD3).
  FIX (general, lods + asset): LOD_UNDER_FACE_DEEP_FAR = 15 mm at the far LOD (below ratio < LOD_SMALL_FAR_RATIO): the
  face lands 1.5 mm under (dbg); 30 mm pushed a cuff out instead.
- NECK WEDGES NAMED: push-under moved 74 of 465 front-neck skin vertices up to 49 mm (under the sweater's collar): LOD3's
  big triangles dragged the visible neck above it (faces > 30 deg off LOD0's normal: no push 51, rc2l 129). FIX (general):
  LOD_UNDER_WORN_MAX = 10 mm, a worn part (masked: the skin, socks, shoes) moves at most this far: 129 -> 91; body seen-through
  points at LOD2 / LOD3 from 4 eyes unchanged (vis.py: 301 / 315 front etc. both ways); socks 0 pokes (4 mm: 73 but 7 sock
  pokes). Test test_lod_worn_part_push_is_capped; LOD tests 18 pass.
STATE: (1) fixed in code, offline numbers only. NEXT: (2) LOD3 buttons, LOD2 hip-pocket crease.
- LOD3 BUTTONS (general, lods._hull_pieces): at the far LOD (ratio < LOD_KEEP_PIECE_RATIO) each small made piece
  (LOD_KEEP_PIECE: buttons) that is not flat (LOD_KEEP_PIECE_HULL_FLAT 0.08, thinnest / widest SVD spread) becomes its convex
  hull on its own vertices (corner attributes of each vertex's first corner, normals turned out where they face in), then
  decimated to the same triangle count (hull_x): a closed lens instead of fqmr's 26 crumpled triangles of a holed dome.
  Coat LOD3 1,462 -> 1,380. (r61/btn.py: the crumple number is noisy against a holed LOD0; judged on the export.)
- LOD2 HIP-POCKET CREASE: not worked (budget); still open.
- LOD2 MARGIN (general): LOD_DEV_MIN_TRIS = 1000 (= MIN_PART): groups smaller than this skip the r60 deviation guard (at the
  small parts' small_far ratio 0.5 its bound is 3.3 mm, so it grew shoes 371 -> 629, soles 143 -> 243, badge 116 -> 150;
  rc2i's were fine). Offline LOD2 (no cards) 16,691 -> 16,299: rc2m LOD2 ~25,150 / 25,750 expected (margin ~600).
- SOCK CULL (cull_covered): KEPT. It costs nothing, and with the worn push now capped at 10 mm it is the backstop for a
  deep sock rim; the r60 dump predates its 5th mask entry, so it is only measured in the export (report covered_culled).
- HAIR r37c (coordinator): a trial merge of 2af333de conflicts in hair.py, hair_clumps.py, lashes.py (+ notes): NOT taken
  (hair code is the cards thread's; merge it on main first). rc2m keeps rc2l's hair.
Tests: 37 game-ready / hair LOD pass. Commits 48946829, d690c7b6.
STATE: (1)-(4) in code. NEXT: export rc2m (r61/chain_m.sh = r60/chain_l.sh with rc2m), look, A/B vs rc2l.
- rc2m exported (exp/rc2m_tess, r61/chain_m.sh; dump r61/lodin_m.pkl with the 5-entry masks). Triangles LOD0 89,995 / 103,000,
  LOD1 44,849 / 51,500, LOD2 25,152 / 25,750 (margin 207 -> 598), LOD3 11,127 / 12,360 (coat 1,380, shoes 371, soles 143).
  cull_covered: 1 sock triangle at LOD2 / LOD3 (as rc2l).
STATE: rc2m exported, renders running. NEXT: look, blind A/B vs rc2l, sheet.
- LOOK (mine, r61/lm_z3_lapel_front.png, lm_z3_pocket_front.png: rc2l | rc2m): LOD3 ORANGE ARMHOLE WEDGE GONE. LOD3 NECK: the
  dark jagged wedges above the collar GONE (a faint pale band at the collar top remains). LOD3 BUTTONS: rounder grey
  pebbles instead of crumpled shards, still faceted (a reviewer calls both "faceted lumps"). LOD2 hip-pocket crease as rc2l.
- BLIND A/B (fresh subagent; review-ab's CLI not before 2026-10-19 13:00 MT; 13 tiles r61/blind, key r61/blind/abkey.json,
  rc2l vs rc2m): rc2m better 3 (LOD3 lapel: the MAJOR wedge gone; LOD3 coat 1 m; LOD0 coat 1 m, noise), rc2l better 1 (LOD2
  lapel: two orange specks at her right armpit vs one, minor), same 9. MAJORs rc2m 0 vs rc2l 1. Shared minors: LOD3 buttons
  faceted, LOD2 / LOD3 right lower pocket fold, jeans fly stitching as jagged dashes at LOD3, jagged shoe soles from the back.
- SHEET workspace/human_renders/gr_r61_tess.png (checked: reference | result throughout; the title is cut at the right edge;
  row 2 photo faces as r59/r60's renders). Face likeness unchanged: still the blocker (head stages), not this thread.
STATE: rc2m = best RC (beats rc2l 3/1/9, MAJORs 0 vs 1). NEXT: handover.

## Handover r61 (assembly agent, tool-call budget)
- Nothing running (r61/chain_m.sh finished: SHEET_M_DONE). Commits 48946829 (far face depth + worn push cap), d690c7b6 (hull
  buttons + guard exemption), + notes. 37 game-ready / hair LOD tests pass.
- BEST RC: rc2m = exp/rc2m_tess (sheet gr_r61_tess.png). Triangles LOD0 89,995, LOD1 44,849, LOD2 25,152 (margin 598),
  LOD3 11,127: all under.
- Debug kit (new): r61/full.py (whole LOD k step offline + pokes + neck band), r61/vis.py (z-buffer seen-through test from an
  eye), r61/btn.py (small pieces), r61/dbg.py; r61/lodin_m.pkl = rc2m's inputs WITH the 5-entry masks (cull_covered probes).
- HAIR r37c NOT merged: 2af333de conflicts with this branch in hair.py, hair_clumps.py, lashes.py: land the cards thread on
  main first, then re-export (rc2n) on top.
- NEXT: (a) LOD2 orange specks at her right armpit (z2_lapel, 1-2 specks: run vis.py at k=2 from the lapel camera);
  (b) LOD2 / LOD3 right lower pocket fold and LOD2 left hip-pocket crease (coat panel under a seated patch);
  (c) LOD3 buttons still faceted: try a fixed low-poly lens (e.g. 24-triangle disc fitted to the hull's PCA) if it matters
  at LOD3 distance (it is a close-up-only fault); (d) jeans fly stitching jagged at LOD3 (texture / decimated uv);
  (e) face likeness (head stages), crown card silhouette (cards thread).
### Session 2 (assembly_garrett, 2026-10-18)
- Per-character face fits: `faceshapes.character_fits(spec)` (export wraps the whole bake in it): base.head.face_fits =
  {"smile": .npy, "jaw": .npy, "sculpt": .npz} (relative = model folder) replaces the env vars; keys left out are cleared;
  no face_fits = env kept + one WARNING each. Also fixed: the session-1 warning called log() on the _Log list (would have
  crashed any export with HP_SMILE_FIT set). Tests: test_per_character_face_fits_*. Garrett has no fits yet (generic shapes).
- v1 FAILED at the bake: "Cycles ran out of shader stack on part:body". Per-pass compile (assembly_garrett/stack/svm.py,
  8x8 frames, ~25 s): the BSDF, color, aoh and color_blink passes all overflow SVM; rms fits. Garrett's body: 61 expanded
  layers, 20 with height (gp_h6c_s15's skin); Tess's ga_tess: 47 / 8. FIX (general, bake path): `asset.bake_needs_osl`
  runs bake_maps with check_only (every pass compiled on the parts' materials, seconds) and, on an overflow, bakes with
  OSL (`scene.cycles.shading_system`, CPU; no stack limit). Checked on the real scene (stack/cmp.py): OSL renders the body's
  colour (SVM: background), and on shoes (fits SVM) OSL == SVM pixel for pixel. Test test_bake_falls_back_to_osl_*.
  Not fixed: the LIVE scene / looks in Cycles still overflow on that skin (EEVEE is fine); the skin's layers untouched.
- Body TORN at lm_lid_lower_in.L / lm_eye_outer.L/R (120 folded edges, 83 turned): SOURCE = gp_h6c_s15's base.head.lid_fold
  (variant ag_v_nofold: 6 folded / 1 turned, no TORN cluster; ag_v_noshape (minus head.shape): unchanged 120). Owner: the
  skin agent (lid_fold). teeth_lower 68 folded / 39 turned in all three: not the head edits; Tess's 26 / 3 came with her
  teeth_lower max_triangles budget (Tess-only head key, gap (b)).
STATE: v1 re-export running with the OSL fallback (logs/exp_v1b.log), lid_fold kept as specified. NEXT: game check.
- v1 re-export (OSL bake ran: body color 183 s / rms 165 / aoh 165 / blink 191) FAILED later in cloth.export_part:
  cloth_made.drawn KeyError 'thickness': the frozen SHIRT's made stand / collar carry none (the jacket's collar does).
  FIX: drawn() falls back to made / fabric thickness / MADE_THICKNESS 2 mm; test test_drawn_made_parts_without_thickness.
  Hair in v1's log: 3586 tris as cards = 96 cards + the cap 3100 (asked 12000: only 486 tris of locks; most of the
  budget unused: G88a's strands give few cards). LOD0 budget hero: 52996 body / 25000 cloth / 103000 total.
- v2 model ag_garrett2 (mk_ag_garrett.py dst=ag_garrett2 frozen=... dress_garrett/frozen_ae: jacket + shirt from dg_ae_j18,
  trousers dg_t6). The shirt is the one drawn under the JACKET (garrett_shirt.pkl), not garrett_shirt_under_trousers.pkl:
  one shirt drape only; check the tuck at the waist.
### Handover (assembly_garrett session 2, tool-call budget)
- IN FLIGHT: export exp/ag_garrett_v2 (logs/exp_v2.log, "EXPORT EXIT"; ~35 min with the OSL bake). Nobody collects it:
  the next session starts there. v1 was never completed (superseded by v2: legs no longer bare).
- NEXT: (1) read exp_v2.log (quality lines: lid TORN cluster expected from lid_fold; trousers crossings; budgets per LOD);
  (2) bash rge.sh ag2 exp/ag_garrett_v2 shots_ag.json + bin/offload wait ag2; (3) look first, then tiles review (r46
  tiles.py on the training front photo); trousers at 1 m: the pale spot below the fly (shirt through?) and the 35 vs 0
  crossings mismatch from dress-garrett's report; (4) Joe sheet; (5) owners: skin agent for lid_fold's tear, teeth_lower
  budget (Tess-only key) for the 68 folded edges.
- NOT done: no renders, no game check, no review, no Joe sheet, no look-first verdict (no export has completed yet).
### Session 3 (assembly_garrett, 2026-10-18)
- v2 export (ag_garrett2) completed its bake (OSL, 830 s); quality lines as session 2 predicted (body TORN cluster at the lids from
  lid_fold, teeth_lower 68 folded, shoes 20 folded / 38 turned). Budgets LOD0 hero: 52996 body / 25000 cloth / 103000 total.
- Coordinator: the fly's pale spot = the trousers' own shirt tails through the crotch (10 tips); fixed by dress-garrett
  (1b9ac8a2, push_under wide second pass) + trousers re-frozen (frozen_ae from dg_af_t6f). The cherry-pick conflicted (it
  sits on 6 more dress-garrett commits: drawn collars, collar_options.widen): MERGED their branch
  worktree-agent-a772e41978c43cfa6 instead (clean; cloth tests pass). Frozen set pinned in assembly_garrett/frozen_af/.
- v3 = ag_garrett3 (frozen_af: jacket + garrett_shirt.pkl + the new trousers), export exp/ag_garrett_v3 (logs/exp_v3.log), queued
  on the heavy slot behind v2.
STATE: v2 finishing (LODs / GLB), v3 queued. NEXT: game check on v2 (look + review), then v3 for the fly.
- v2 EXPORT EXIT 0 (exp/ag_garrett_v2/ag_garrett2*.glb). v3 EXPORT EXIT 0 (exp/ag_garrett_v3/ag_garrett3*.glb, merged code, ~29 min:
  bake 608 s). v2 already loaded the re-frozen trousers (frozen_ae rewritten 13:23, read at ~13:32), so v2 / v3 cloth counts are
  identical; the RC is v3. The game check batch ag2 (queued) carries v3's GLBs (swapped into its job folders before it started).
- BUDGETS (hero): LOD0 73326 of 103000 (body 38790 -> head 22867 + body 7250 after cull, cloth 25434 of 25000 OVER, eyes / mouth /
  lashes 9908 of 7996 OVER, hair 3586 of 25000). LOD1 34534 (0.47 of LOD0, asked 0.5), LOD2 25874 (0.35, asked 0.25), LOD3 22482
  (0.31, asked 0.12): LOD2 / 3 miss their ratio: per-part floors (teeth_lower 1458, eyes 651, socks / soles / shoes ~2400, cloth
  ~8100 at LOD3) and the hair is the cap only at LOD1+ (0 cards).
- Rig audit, SEATED (hips / knees 90): body through trousers 157 verts (25.7 mm, crotch z 0.78), shirt through trousers 63 (9.9 mm,
  waist z 0.96), trousers through jacket 32 (29.1 mm), trousers through shirt 30: BAD in v2 and v3 alike (rest is clean).
STATE: game check ag2 (= v3) queued on NICO-TOP behind rs_r12. NEXT: look, tiles, blind review, Joe sheet.
- GAME CHECK ag2 (= v3, NICO-TOP, ~3 min once it ran): offload/ag2/results/ag2/j0..3/x/out/ (j0 LOD0 all shots, j1-3 LODs).
  LOOK FIRST (mine, before the review): the jacket is covered in BLACK TRIANGLES front and back (maps clean: geometry; likely the
  two-sided shell's inner side through the outer after decimation 17572 -> 4780, unverified); hair is a near-black swept-up
  pompadour where the photo / concept show short receding grey; suit reads black, not charcoal, no belt; smile closes the eyes;
  jaw-open reads as a red "O". At 1 m: the fly's pale spot is NOT visible (shirt meets the waistband cleanly, the tuck is a flat
  line, acceptable), the lid tear is NOT visible; hair = 96 cards + cap: a dark sculpted helmet with a fine streak texture and a
  hard hairline (LOD1+ = the cap only). The face itself reads as a plausible middle-aged man; skin reads well at 3 m.
- BLIND REVIEW (fresh subagent, images only; bin/review is out until 2026-10-19 13:00 MT): 17 pairs (feature tiles from r46
  tiles.py on the training front photo for neutral / smile / jaw; concept | figure; 3/4 photo | 3/4 head): FAIL, 8 top MAJORs
  (assembly_garrett/rv3/review.md): hair, jacket triangles + collar, smile shuts eyes, jaw "O" + teeth + red interior, brows
  as blocks, stubble speckle with hard edges, under-eye ledge, upper-lip shading seam.
- JOE SHEET: assembly_garrett/sheets/garrett_v3_joe.png (rows TURNAROUND / FACE / MOTION + GAME DISTANCE, reference photo
  first in each row, every column captioned; joesheet.py). Not sent: renders go to NICO-TOP / the coordinator forwards.
- RC_garrett.md gap list updated (rows A-I, top: jacket triangles, hair colour / style, suit colour, smile, jaw).
### Handover (assembly_garrett session 3)
- DONE: v2 + v3 exported (v3 = RC), dress-garrett merged (fly fix), budgets per LOD read, game check, look, blind review, Joe sheet.
- Nothing in flight.
- NEXT (by owner): (1) export / cloth: find the jacket's black triangles: count crossings between the jacket's outer and inner
  (two-sided) shells in lowpoly vs high (exp/ag_garrett_v3/lowpoly*.npz); if decimation, decimate one side and offset the other
  (general fix, test); (2) hair agent: G88a's colour in its own sheet vs the strand atlas, and the groom vs the photo (short, grey,
  receding); (3) face shapes: per-character fits (base.head.face_fits) for Garrett's smile / jaw; (4) skin agent: brows, stubble
  edges, under-eye ledge, upper-lip seam; (5) dress-garrett: charcoal, belt, seated crossings.
STATE: session 3 done. NEXT: jacket triangles (1) first; it is the one fault this assembly owns.
### Session 4 (assembly_garrett, 2026-10-18; coordinator's look at sheets/garrett_v3_joe.png: 5 blockers)
- (1) JACKET BLACK BLOTCHES: CAUSE = the cloth decimation (asset: lods.lod_part at cloth_triangles / n) decimated the two-sided
  garment's OUTER and INNER shells (0.8 mm apart, no shared vertices: separate patches) independently. Measured on v3's own
  cloth parts (s4/jk_cross.py, inner vertices against the outer surface): jacket sim 0.5% outside (max 0.3 mm) -> decimated
  13.8% outside, 110 > 1 mm, max 9.6 mm (shirt 12.1% / 8.5 mm, trousers 10.8% / 4.0 mm). The inner faces are wound inward
  (culled from outside) but cast shadows and show at grazing angles: soft black blotches (the back crop in the v3 render is
  blotches, not crisp triangles). Normals / uv / maps are not it: an orthographic z-buffer with backface culling (jk_vis.py)
  finds <1% visible pixels with a normal facing away, the atlas is uniform (56,56,48). FIX (general): cloth.export_part
  marks the part `shell` {"outer": n, "thickness"}; lods._lod_shell decimates the outer shell + the rest (made pieces,
  buttons) and REBUILDS the inner from the decimated outer (offset along its normal, wound back, normal / sign negated,
  uv / tangent / weights / shapes copied); the LOD keeps `shell`, so LOD1-3 do the same. Jacket after: 0.4% outside,
  max 0.1 mm (shirt 4.6% / 3.2 mm: its made stand + collar slabs; trousers 0.1% / 0.6 mm). Test
  test_two_sided_cloth_decimation_keeps_the_inner_shell_inside. Render proof: v4's game check.
  Side note: the made collar slab (cloth_made.solid) rim faces carry the sheet's +-normal (230 jacket faces with every
  corner normal against the winding): 2 mm rims, not the blotches; left as is.
STATE: (1) fixed in code + test. NEXT: (2) hair colour.
- (2) HAIR NEAR-BLACK: CAUSE = the card atlas of a `seen` look (G88a: look.seen = the photo's hair colour [.242 .232 .226]) at
  card_gain 1.0: seen_look sets lit = seen and leaves the lift to the renderer; the EEVEE strands draw lit x eevee_gain 1.6,
  the cards' atlas came out AS seen (v3 hair_basecolor opaque mean sRGB [0.242 0.232 0.227]). FIX (general, hair.full_look):
  a seen look with no card_gain takes eevee_gain as card_gain (an explicit / measured card_gain wins; explicit-colour looks
  such as Tess's unchanged). Test test_cards_from_a_seen_look_take_the_strands_lift. Proof: v4's game check.
- (3) SUIT COLOUR: NOT the export. Spec jacket #3a3836 / trousers #2f2e2e; the GLB's atlases carry exactly that (median 58,56,54 /
  47,46,46), roughness 0.85, no AO darkening. Albedo ratio jacket / shirt (linear) 0.082 vs the concept's rendered ratio 0.070:
  the garment colours ARE charcoal relative to the shirt. The v3 render's ratio was 0.024 (3.4x darker than its albedo): the
  lighting plus, likely, the crossing inner shell's shadows from (1). Re-measure on v4. Belt: none in dg_garrett (report only).
- Coordinator relay (dress-garrett ah): merged worktree-agent-a772e41978c43cfa6 (3b870bd9: frozen made parts' "replaces" from
  info.hides; conflict in cloth_made.drawn resolved keeping the thickness fallback chain, their MADE_THICKNESS 0.8 mm); jacket
  re-frozen (collar ends faired) -> pinned frozen_ag/. Model ag_garrett4 (frozen_ag), export exp/ag_garrett_v4 RUNNING
  (logs/exp_v4.log). Expression candidates (s4/expr_mixes.json: smiles s0 (= A2) .. s6, jaw j0 .. j5) rendering on v3's GLB:
  offload/ex4 (NICO-TOP).
STATE: (1)-(3) done in code; v4 exporting; expression batch ex4 running. NEXT: pick smile / jaw from ex4 tiles.
- (4) SMILE / (5) JAW (parameter mixes only, on v3's GLB morph targets, NICO-TOP batch ex4, sheets s4/ex_smile.png, s4/ex_jaw.png;
  no expression photos of Garrett exist: target = a natural warm smile with the eyes open). A2 (eyeSquint 0.5, cheekSquint 1.0)
  shuts his eyes on the generic shapes. CHOSEN smile = s6: mouthSmile 0.85, cheekSquint 0.45, eyeSquint 0.1, mouthDimple 0.3,
  mouthUpperUp 0.25, jawOpen 0.08 (eyes open, upper teeth show, cheeks lift a little). s2 (eyeSquint 0) keeps the eyes widest but
  reads as a thin closed-lip grin. CHOSEN jaw = j3: jawOpen 0.6, mouthLowerDown 0.2, mouthStretch 0.2 (an open mouth with both
  teeth rows, corners widened, not the jawOpen-1.0 "O"). Stored: shots_ag.json / shots_lod.json (smile*, jaw*; v3's kept as
  shots_ag_v3.json) and s4/garrett_expr.json. No spec slot for mixes (base.head.face_fits holds fitted shape .npy files only).
  What the parameters CAN'T do: the mouth interior is flat saturated red (the cavity's material / no darkening with depth),
  upper teeth read as separate pegs, the neutral's own lids sit low (narrow eyes before any squint: head / skin, not a mix);
  the smile's nasolabial fold barely deepens (generic shapes; a fitted smile would need Garrett smile photos).
STATE: (4) / (5) chosen. NEXT: v4 export -> game check (rge.sh ag4) -> look, blind tiles, Joe sheet.
- v4 = ag_garrett4 (frozen_ag: dress-garrett's re-frozen jacket + shirt + trousers; code = fixes (1) (2) + 3b870bd9), EXPORT EXIT 0:
  exp/ag_garrett_v4/ag_garrett4.glb + _LOD1..3. Cloth 28956 / 17572 / 45276 -> 8086 / 4846 / 12356 (clothing 25288 of 25000 OVER;
  eyes / mouth / lashes 9908 of 7996 OVER); hair atlas mean sRGB 0.242 -> 0.305 (= x1.6 linear). Same quality lines as v3 (lid
  TORN from lid_fold, teeth_lower 68 folded). Game check ag4 (NICO-TOP, 4 jobs): offload/ag4/results/ag4/j*/x/out/.
- LOOK FIRST (mine): (1) the jacket's blotches are GONE front and back (s4/v3_v4_jacket.png: v3 | v4 front, v3 | v4 back). A white
  sliver on the left lapel near the top remains (v3 too; seen at 1 m and in the walk). (2) hair reads dark grey with lighter strands,
  no longer black, but still darker than the photo and the wrong STYLE (tall swept-back mass vs short receding grey): hair thread.
  (3) suit still reads black: v4 render ratio jacket / shirt 0.024 (albedo 0.082, concept 0.070); the material is the same as the
  shirt's except the colour (normal maps flat, ORM equal), so the game light / view gives the dark cloth ~0.21 of its albedo
  against ~0.78 for the shirt: unexplained, NOT the spec and NOT the export material. (4) smile s6: eyes open at the front, warm,
  upper teeth row; at 3/4 still a slight squint. (5) jaw j3: an open mouth but still a red interior. Blink: fine.
- BLIND REVIEW (fresh subagent, images only, 7 pairs): FAIL. Top MAJORs: hair colour / style (identity); face too long / soft vs
  his broad square lower face; eyes sleepy / hooded with under-eye bags (also spoils the smile: the reviewer still saw a squint);
  jaw-open lips flare into a ring + red interior; the white lapel sliver + a white speck on the upper back; dark strands hanging
  onto the nape (cards); back hair a uniform cap. minors: no belt, shirt hem line flat, black not charcoal, stubble stipple.
- JOE SHEET: sheets/garrett_v4_joe.png (TURNAROUND / FACE / 3/4 + GAME; reference first in each row, captioned).
### Handover (assembly_garrett session 4)
- DONE: (1) jacket blotches: cause + general fix (lods._lod_shell) + test, proven in v4; (2) hair cards' gain for seen looks + test
  (lifted x1.6; colour still dark / style wrong: hair thread); (3) suit colour: spec and export are right (measured), the dark read
  is the render light on dark cloth (open); (4) smile s6 / (5) jaw j3 in shots_ag.json / shots_lod.json / s4/garrett_expr.json;
  dress-garrett merged (3b870bd9); v4 exported + game check + blind review + Joe sheet. Nothing in flight.
- NEXT (owners): dress-garrett: the white lapel sliver (left lapel top, both v3 / v4) + the back speck; belt; if Joe wants the
  suit lighter in game light, the garment colour (#3a3836 -> e.g. #4a4845) is theirs. Export / game check: why dark cloth renders
  at ~0.21 of albedo vs the shirt ~0.78 under the game rig (one-material test: the jacket's material with the shirt's colour).
  Hair thread: groom style vs the photo (short, receding, grey), nape strands. Head / skin: lids (sleepy, bags), long lower face.
  Face shapes: jaw interior (cavity colour), a fitted smile needs Garrett smile photos (none exist).

## r55 (2026-10-18, assembly agent, fresh session): pocket fans, buttons, LOD3 budget, worn-under rule
Scratch /mnt/data/hifipushie/assembly/r55/ (p1-p7.py: probes on exp/rc2d_tess GLBs; NOTE glTF is Y-up: height = y,
front = +z; my first pocket-box counts used Blender axes and were all 0).
- POCKET FANS (coordinator: not fixed by r54): NOT made pieces and NOT the shell over them. rc2d LOD0's made group (the
  triangles after the two shells) is the collar / lapels (1,320) + 4 buttons (174 each) + 8 thread bits (6): its bbox is
  the chest; the hip pockets are drawn on the OUTER shell (one cloth layer there: 1 neighbour within 6 mm, p50). At LOD2,
  144 of 270 pocket-box triangles (outer 72 + its rebuilt inner 72) are WOUND AGAINST their corners' normals: decimation
  folded them over; rendered back-facing they shade dark = the radial fans. LOD0 / LOD1 there: 0. Not the seam weld (off:
  still 26 folded there; a "don't weld along the same border" filter changed nothing: reverted). FIX (lods.lod_part,
  LOD_REWIND): every decimated triangle wound against its transferred vertex normals is wound the other way (coat probe:
  folded 69 / 29 at LOD2 / LOD3 -> 0).
- BUTTONS as grey cones: they sat in the made group, decimated welded with the lapels. FIX (lods._small_pieces,
  LOD_KEEP_PIECE 200): a made piece that is its own small connected piece is its own mesh, kept whole at ratio >= 0.1
  (LOD1-2), LOD_KEEP_PIECE_FAR 0.15 below (LOD3).
- LOD3 BUDGET: made floor now min(LOD_MADE_FLOOR 0.35, LOD_MADE_FLOOR_X 2 x ratio) (LOD2 stays ~0.27-0.35, LOD3 ~0.15);
  buttons whole add ~600 at LOD2 (25.3k of 25,750 expected). LOD3 was still ~70 over, so: small parts (< MIN_PART, kept
  whole) take max(ratio, LOD_SMALL_FAR 0.5) where their ratio < LOD_SMALL_FAR_RATIO 0.15 (LOD3 only), never the eyes
  (LOD_SMALL_KEEP: the cornea). ~4.9k of LOD3 was small parts kept whole; expect ~-2k.
- WORN-UNDER RULE: lods.under_at_lod0(share=True) gives the share of in-reach vertices that are UNDER a garment; asset
  LOD_PUSH_WORN_SHARE 0.85. rc2d LOD0 (p7): socks 0.99, body 0.89, shoes 1.00 (collar under the jeans hem: 46 vertices,
  those are under), vs badge 0.49, lanyard 0.48, clip 0.58, laces 0.67, badge_card 0.83 (thin margin).
- Test test_lod_buttons_whole_folds_rewound_small_parts_far; test_lod_made_pieces_stay_over_their_shell's floor check
  follows the X rule. (The rewind assert holds on the test sheet but I did not show the sheet folds without the fix.)
- Dress-tess: no "FROZEN FOR EXPORT" in agent-ac06d0eb5553e576b's cloth.md: no coat freeze to take.
STATE: fixes in code + tests pass. NEXT: re-export rc2e (cull_poses as rc2d), tris, game check + close-ups, look.
- LEFT CALF BLOTCH (rc2d LOD2, p8.py): 22 SOCK vertices through the decimated jeans (x 0.17, 19 cm up, back); body / shoes
  0. The r54 mask moved only vertices UNDER the jeans at LOD0, and these had no jeans within reach there (a loose leg). FIX
  (asset LOD_PUSH_WORN_NOT_OVER): every vertex NOT OVER a garment at LOD0 may move (the shoe collar over the hem still
  stays). Coat 74 / sweater 42 vertices "through the jeans" at LOD2 are the coat / sweater over them (expected).
  (Process slip: killing my stale export with `kill -9` on a "hv.py" pattern may have killed another agent's hv.py job
  around 17:41; a haircards hv.py job was running again at 17:42.)
STATE: committed; rc2e export restarted with all r55 fixes (r55/chain.sh: export, tris, game check, close-ups z1-3).
- rc2e EXPORTED (exp/rc2e_tess; all r55 fixes; cull_poses r54/poses). Triangles (export log): LOD0 89,342 / 103,000,
  LOD1 42,608 / 51,500, LOD2 23,227 / 25,750, LOD3 10,033 / 12,360: ALL UNDER (LOD3 was 12,524). NOTE the small-part rule
  also fired at LOD2 (the body-side ratio there is < 0.15: shoes 371, laces 288, clip 248 ...; tongue / eyes whole): fine
  for the budget, but set LOD_SMALL_FAR_RATIO to ~0.1 if LOD2 props look coarse. Worn-push now: shoes (100%), socks (99%),
  body (93%); badge / clip / lanyard / laces / badge_card out.
- LOOK (r55/l2_rc2d_vs_rc2e.png: LOD2 at its switch distance, rc2d front | rc2e front | rc2d back | rc2e back): the grey
  radial POCKET FANS are GONE (pocket outlines read as pockets), the LEFT CALF BLOTCH is GONE. Close-ups (r55/ge/z*),
  buttons, lapel-edge sweater: renders were still running at handover (r55/ge_all.sh -> r55/GE_DONE).

## Handover r55 (assembly agent, tool-call budget)
- DONE (committed locally, never pushed): lods LOD_REWIND (folded decimated triangles wound to their normals: the pocket
  fans), LOD_KEEP_PIECE (buttons whole at LOD1-2), made floor min(0.35, 2 x ratio), LOD_SMALL_FAR (small parts halve where
  their ratio < 0.15), asset LOD_PUSH_WORN_SHARE 0.85 + LOD_PUSH_WORN_NOT_OVER (sock through the LOD2 jeans). Tests pass
  (test_game_ready 30). rc2e exported; triangles all under; LOD2 look: fans and calf blotch gone.
- NOT DONE: (a) the NEW COAT FREEZE from dress-tess s18 (coordinator, at handover):
  /mnt/data/hifipushie/dress_tess/frozen/2026-10-18_s18/{coat,sweater,jeans}.pkl (cloth.freeze, dt_tess v112; coat left front
  = mirror of the approved right, crush 0.56 mm; sweater / jeans unchanged). Put them into rc2_tess's cloth (find how
  r50/mk_rc.py / r51/mk_rc2.py took the previous coat), then since the coat mesh changes: dump poses again from an export
  WITHOUT the garment cull (r54 step 3: cull_poses maps by rest position within 2 mm), export with cull_poses, game check.
  Check at 1 m front: the left front, the grey strip at the inner front edge, the smears. (b) LOOK at r55/ge/z{1,2,3}_*
  (buttons, lapel-edge orange) when r55/GE_DONE. (c) blind A/B on the LOD backs, rc2 (r51/ge/l*_back) vs the new export.
  (d) Joe's sheet: python3 r55/sheet.py <ge dir> workspace/human_renders/gr_r55_tess.png "<title>" (r55/sheet.py adds a
  PHOTO LIGHT row from r54/pl beside the references, GAME RIG captions on the game row, LOD2 pocket / calf close-ups).
  (e) RC_tess.md (/mnt/data/hifipushie/assembly/RC_tess.md): add the r55 numbers; blockers 5 (LOD fans / calves) -> fixed
  on rc2e pending the close-up look.
- Process slip: a `kill -9` on a "hv.py" pattern while stopping my stale export may have killed another agent's hv.py job
  (~17:41).
- r55 CLOSE-UP LOOK (r55/zoom4_rc2e.png = z2 calf back | z2 pocket | z2 lapel | z3 pocket; vs r54/zoom4_rc2d.png): calf
  blotch GONE. LOD2 pockets: the dark grey fans are gone, but FAINT PALE FAN STREAKS remain (the folds are still there
  geometrically, only wound right now: the next step is to prevent the fold, e.g. re-decimate the folded region at a
  higher share or reject folding collapses). Buttons: round, no longer grey cones, slightly lumpy. Orange sweater at the
  lapel edges: UNCHANGED (two small patches; not addressed). LOD3 pockets read as slits (fine at 12.9 m).

## r56 (2026-10-18, assembly agent, fresh session): s18 coat freeze, pocket fans at the root, buttons, rc2f
Scratch /mnt/data/hifipushie/assembly/r56/ (q1-q9.py probes on the rc2e coat GLB; mk_rc2f.py; chain1.sh).
- (1) LOOK rc2e close-ups (r55/ge/z{1,2,3}_{lapel,pocket}_front): LOD1 buttons round grey discs, ORANGE SWEATER specks at
  both lapel edges (notch, chest pocket corner) already at LOD1; LOD2 left hip pocket still shows the radial fan lines,
  dark jeans triangles through the coat at the crotch opening (LOD2 / LOD3); LOD3 buttons cones (0.15, far: accepted),
  the sweater neckband gone at LOD3 (skin + a grey rectangle at the lapel V).
- (2) rc2_tess now wears dress-tess s18's freeze (r56/mk_rc2f.py: each garment = dt_tess's definition, so the look keys
  FROZEN_KEYS take from the spec come with it: coat detail.woven.crush 0.00056 (rc2 had 0.0016), + frozen = the s18
  pickle). Backup of the old spec: r56/rc2_tess_spec_before.json. Pass 1 (r56/chain1.sh): export rc2f0_tess WITHOUT the
  garment cull / LODs / face shapes, then the 16 clip frames dumped to r56/poses (r54 step 3).
- POCKET FANS, root cause (q5-q7): not folds. The patch pockets are their OWN small pieces of the coat's outer shell (106
  triangles each, 62 of their vertices on the border, wound inward, the inner shell facing out), and the welded decimation
  holds borders: at LOD2 each became a ~60-triangle fan from one vertex (no interior left), the long triangles shading as
  pale streaks; LOD_REWIND only turned the wrongly wound ones. No dihedral > 120 deg anywhere at LOD0 / LOD2. A fold guard
  (cut out the LOD0 triangles around folds, decimate them apart at 2x / 4x) did not help (still "folds" at 4x: the lookup,
  not geometry): left in code OFF (LOD_FOLD_GUARD = ()). FIX lods.LOD_KEEP_OUTER_PIECES: small pieces (< LOD_KEEP_PIECE)
  of the outer shell are kept whole at LOD1-2 like buttons (LOD_KEEP_PIECE_FAR at LOD3), inner shell rebuilt with them.
  rc2e coat (q8): pocket-box slivers (min angle < 8 deg) LOD1 135 -> 50, LOD2 70 -> 20; coat +172 / +428 / +110 triangles
  at LOD1 / 2 / 3 (rc2e LOD2 23,227 of 25,750: room).
- BUTTONS LUMPY: _lift_made lifted made vertices one by one over the decimated shell (q9: 57 button vertices lifted, up to
  7.7 mm: a lump). FIX LOD_LIFT_RIGID: a small made piece takes its largest lift along its mean lift direction, all
  vertices (p50 1.1, p95 4.6 mm off LOD0 at LOD2; it hovers a few mm at LOD2 distance instead of bulging).
- Test test_lod_small_outer_pieces_whole_and_made_pieces_lifted_rigidly.
STATE: fixes + test in code; pass 1 (dump) running. NEXT: pass 2 = rc2f export with cull_poses r56/poses, game check,
1 m front coat look, lapel sweater patches.
### Session 5 (assembly_garrett, 2026-10-18; Joe on v4: "that's a totally different hairstyle")
- MERGES: the Tess assembly branch (worktree-agent-ad0815704f43e0e00 at 26f63b47: r51-r56 export fixes: per-vertex bake cage,
  LOD_WELD / LOD_BORDER_OVER / LOD_SEAM_WELD, garment-under-garment cull + cull_poses, per-LOD push-under, made floor / pieces /
  rigid lift, LOD_REWIND, LOD_KEEP_OUTER_PIECES; conflicts asset / lods / test_game_ready resolved to the Tess side, Garrett's
  test_drawn_made_parts_without_thickness kept), dress-garrett (worktree-agent-a772e41978c43cfa6: 8a56a9a9 collar v3 sim, cloth_over),
  hair-heads2 (9b8f12c4: Garrett cards c4 defaults), projskin2 up to 1e277ea2 (gp_h6c_s21 promoted: notes only past what was in;
  the later stubble / tear-line code is unjudged and NOT merged). Tests: game_ready, hair_lods, cloth, face_shapes, seams,
  cloth_made, cloth_over: no failures.
- v5 model ag_garrett5 (mk_ag_garrett.py dst=ag_garrett5 skin_from=gp_h6c_s21 card_gain=2.1 frozen=frozen_s5/...): skin s21 by
  explicit id; hair hg_G88a + hair.export.card_gain 2.1 (= c4L); garments pinned in assembly_garrett/frozen_s5/ from
  dress_garrett/frozen_ae (jacket = the v3 collar, 15:29; shirt / trousers = v4's, same md5).
- Export in two passes (Tess r56's recipe, s5/chain.sh): v5p (no garment cull / LODs / face shapes) -> 16 clip frames dumped
  (s5/poses) -> v5 = hero, lods, cull_under_cloth + cull_poses -> NICO-TOP game check ag5 (s5/shots_ag5.json = shots_ag + hair
  front / 3/4 / side / back + LOD0 at 3.1 m; LOD1-3 at their switch distances 3.1 / 6.2 / 12.9 m front / 3/4 / back).
STATE: chain running (pass 1 in the heavy slot queue). Suit-colour probe on v4 running (s5/suit: flat-grey / mask renders).
NEXT: collect, look first, then the review.
- (4b) DARK SUIT, measured (s5/suit: v4's GLB under the game rig, local ge.sh; three renders of the same shots (torso 1.6 m front /
  3/4, g3_body 3 m): the cloth basecolors replaced by flat 50% grey, by a red / green / blue mask, and the original). Effective
  albedo = orig / flat x 0.5 per garment (median px, linear): shirt 0.469 (albedo 0.491), jacket 0.021-0.032 (albedo 0.042),
  trousers 0.012-0.023 (albedo 0.028). Irradiance is EQUAL (flat grey: jacket 0.41 / shirt 0.36 front): the light reaches the
  jacket as well as the shirt; no shadowing, no inverted normals. Rendered jacket / shirt ratio 0.066-0.076 vs albedo 0.086 and
  the concept's 0.070: session 4's "0.024, 3.4x darker" was a measurement fault (regions), not the render. The suit reads black
  because #3a3836 IS that dark (sRGB 58 = linear 0.042), and the game render matches the concept's ratio. Lighter in game =
  a garment colour change (dress-garrett's, Joe's call); the export / renderer are right. Small residual: the jacket renders at
  ~0.73 of its albedo (trousers ~0.5) where the shirt is 0.95 (twill normal map + roughness; not chased).
- (4a) WHITE SLIVER / SPECK, export side (s5/specks/specks_glb.py = dress-garrett's specks.py on an EXPORTED GLB's meshes, rest pose,
  2 mm z-buffer, a speck = an under layer front-most where the jacket encloses it). v4 LOD0: front: shirt at mm [-214 24 1302]
  (49 px, right underarm / chest side) and [54 57 1494] (7 px, left collar / lapel top = the sliver); back: shirt at
  [-210 -62 1457] (30 px, right shoulder blade = the back speck); front3q_R: body at [-215 20 1301] (82 px). The frozen draw
  has none of these (dress-garrett: back 0): the decimated LOD0 jacket lets the shirt / body through. Re-run on v5 (Tess's
  push-under per LOD + garment-under-garment cull are in now).
- HAIR TIER TRAP (general, export): asset.export's LOD0 hair is cut at hair.export.tier, default None = EXPORT_CARDS' 12000-triangle
  budget, the OLD per-lock cut (pass 1: 96 cards + cap = 3586 tris, the v3 / v4 helmet); only LOD1-3 get lods.HAIR_TIERS
  (main / npc / far). c4L's hero tier needs hair.export.tier "hero" in the spec: set on ag_garrett5 (s5/settier.py), pass 2
  restarted: LOD0 hair now 14624 tris, 1502 cards (c4L hero 14570). So v3 / v4's "pompadour" at LOD0 was partly this: the export
  never used the hair agent's tiers at LOD0. NEXT (code): default LOD0 to the role's tier ("hero" for hero) when unset.
STATE: v5 pass 2 exporting (hero hair). NEXT: game check ag5, look, specks on v5, A/B.
- Pass 1 done: exp/rc2f0_tess (no garment cull, no LODs / shapes; 646 s, LOD0 101,348 uncull'd); 16 frames in r56/poses
  (walk 0-0.9, run 0-0.5, idle 0-3). Carry of the s18 jeans onto rc2_tess's body: max 3.58 mm. Pass 2 (r56/chain2.sh:
  rc2f export with cull_poses r56/poses + all r56 lods fixes, tris, close-ups z0-z3 incl. coat 1 m front + coat back,
  LOD switch shots, x_* game check) started on its own.
- (Process: `setsid ... & echo $!` records setsid's parent, not the job: real PIDs in r56/PIDS.)
STATE: rc2f exporting. NEXT: tris, look z0-z3 (1 m coat, lapel orange), blind A/B (r56/tiles.py), sheet (r56/sheet.py).
- rc2f EXPORTED (1474 s). Triangles: LOD0 91,971 / 103,000, LOD1 47,349 / 51,500, LOD2 28,116 / 25,750 OVER, LOD3 10,620 /
  12,360. Cause: LOD_KEEP_OUTER_PIECES also kept the SWEATER's outer-shell fragments left by the garment cull (1,557 of its
  2,268 outer triangles in pieces < 200): 3,836 at LOD1 and LOD2. FIX LOD_PATCH_GAP 6 mm: a small outer piece is kept only if
  its vertices' median distance to the REST of the outer shell's surface is under it (a patch pocket lies on the panel).
  q12 on rc2f LOD0: coat 384 kept (pockets), sweater 0; sweater 4,536 -> 1,542 / 612 / 334 at 0.34 / 0.135 / 0.074.
  (Nearest-VERTEX distance kept no pocket: the panel's vertices are ~25 mm apart; it has to be the surface.)
- LOOK rc2f (r56/ge/z0-z3, LOD0 coat at 1 m front, coat back 1.6 m): LOD0 coat CLEAN at 1 m: no blotchy smears (crush 0.56),
  pockets crisp, left / right fronts alike, no grey strip at the inner front edge (only a short thin line at her left front
  edge). Back clean. LOD2: hip pockets now clean outlines (no fan); buttons round; her left CHEST pocket at LOD2 reads as a
  crumpled patch (kept whole over a coarser panel; LOD_PATCH_GAP keeps it too). ORANGE at the lapel side: already at LOD0
  (her left chest beside the chest pocket) and LOD1 (her right chest): the sweater through the coat in the rest pose, NOT
  the LODs. r56/q10-q11 (under_depth, rc2e): ~20-50 chest sweater vertices with the coat inside them at every LOD, 2
  visible from the front at LOD1 (q11). Not fixed.
STATE: LOD_PATCH_GAP committed (LOD tests 11 pass); rc2g (= rc2f + it) export + z/l/x renders + sheet queued unattended:
r56/chain3.sh (waits for chain2's GE_DONE; PIDs in r56/PIDS).

## Handover r56 (assembly agent, tool-call budget)
- RUNNING (unattended, my PIDs in /mnt/data/hifipushie/assembly/r56/PIDS: chain2 bash 3001151 (rc2f LOD / x renders ->
  r56/GE_DONE), chain3 bash 3876188 (after GE_DONE: rc2g export -> r56/geg/{z0-3,l1-3,l0,x}_*, r56/tris_g.txt, then the sheet
  workspace/human_renders/gr_r56_tess.png -> r56/SHEET_DONE). ~25 min export + ~30 min renders.
- NEXT: (a) r56/tris_g.txt: LOD2 must be under 25,750 (expected ~24.9k); if over, LOD_KEEP_OUTER_PIECES=False costs only the
  pocket fix. (b) LOOK geg/z2_pocket + z2_lapel (chest pocket crumple), then (c) blind A/B: python3 r56/tiles.py (edit its
  r56/ge paths to r56/geg; pairs rc2 r51 LOD backs / fronts + rc2e r55 close-ups vs new; key blind/abkey.json) to a fresh
  blind subagent (review-ab CLI only after 2026-10-19 13:00 MT). (d) Check the sheet (r56/sheet.py = r55's + COAT 1 m LOD0
  tile), send to Joe. (e) LAPEL ORANGE is a LOD0 sweater-through-coat poke beside her left chest pocket (rest pose): look at
  the garment cull / push-under at LOD0 (lods.push_under_layers runs per LOD; LOD0 has no push) or ask dress-tess.
- Did NOT do this session: the A/B and the sheet (budget); LOD_SMALL_FAR_RATIO untouched (LOD2 props not judged coarse).
- Process: `nohup setsid bash x.sh & echo $!` records setsid's parent, not the job: find the real PID with pgrep -f <script>.

## r57 (2026-10-18, assembly agent, fresh session): the orange sweater at the lapels, rc2g check, A/B, sheet
Scratch /mnt/data/hifipushie/assembly/r57/ (q13-q15.py probes on the rc2f GLBs; shellfind.py recovers a GLB part's
outer-shell count: outer triangles, then the inner ones in the same order).
- ORANGE AT THE LAPELS, two causes (q11 / q13-q14 on rc2f):
  (a) LOD0 has no push-under at all: rc2f LOD0 sweater vertex [0.201, 1.249, 0.078] (her left chest, beside the chest
      pocket) 0.4 / 1.0 mm outside the coat's two shells (the 1 m speck); 3 sweater vertices poking at LOD0 in all, and
      ~5 mm on her upper back (z -0.07, y 1.24: hidden from the front, seen from behind).
  (b) LOD1 right chest [-0.154, 1.27, 0.086]: three long sweater faces 3.5 mm OUTSIDE the coat while all their vertices
      are 2.0 mm under it (push_under_layers had done its job per vertex; the coat bends between them).
  FIX (general): lods.push_under_layers also tests each outward face's centroid along the face normal
  (LOD_UNDER_FACES; lods.cover_depth = under_depth's ray test for any points); asset.export runs it at LOD0 too
  (LOD0_PUSH_UNDER, gap LOD0_UNDER_GAP 1.5 mm = cloth.PUSH_UNDER_GAP; garment layers only: asset._garment_stack).
  q15 on rc2f: LOD0 sweater poking 3 -> 0 (24 vertices moved, max 6.2 mm, the upper back); LOD1 chest faces uncovered
  from the front 5 -> 0 (4 poking faces, max move 5.1 mm); with faces off LOD1 stays 5.
  (Without the shell layout every inner-shell vertex reads as poking: 897, moves of 60 mm. The export's parts carry
  p["shell"]; offline probes on GLBs need shellfind.)
- Test test_lod_under_faces_pushed_where_the_cover_dips_between_vertices; LOD / under tests 12 pass (pytest: the file's
  own __main__ sits mid-file and runs only the tests above it).
STATE: fix + test committed; rc2g (r56 chain3, WITHOUT this fix) exporting. NEXT: rc2g tris + looks, then rc2h with the fix.
- rc2g (r56 chain3, without the r57 push) triangles: LOD0 89,995 / 103,000, LOD1 43,273 / 51,500, LOD2 24,096 / 25,750,
  LOD3 10,146 / 12,360: ALL UNDER (LOD_PATCH_GAP worked: sweater 280 at LOD2).
- LOOK rc2g (r56/geg; montage r57/rc2g_lods.png): LOD0 coat at 1 m CLEAN (pockets crisp, no smears, buttons round).
  LOD2 close-ups: her LEFT hip pocket a twisted vertical flap standing off the panel, her left chest pocket a crumpled
  flap (both kept whole over a coarser panel that no longer matches them); a LARGE orange patch at her right chest and a
  speck beside her left hip pocket (= the r57 face-poke cause; still visible as a speck at the 6.2 m switch distance,
  front). LOD backs at switch distances clean; LOD2 back: a pale fleck on the jeans' left calf.
STATE: rc2g under budget, LOD2 pockets / orange open. NEXT: rc2h (r57/chain4.sh: push-under at LOD0 + faces) looks.
- BLIND A/B (fresh subagent, review-ab CLI not available before 2026-10-19 13:00; r57/tiles.py r56/geg r57/blind_g, key
  r57/blind_g/abkey.json): rc2g vs rc2 (r51) LODs at switch distances front / back, vs rc2e (r55) LOD1-2 lapel / pocket
  close-ups. rc2g better on ALL 10 tiles; MAJORs rc2g 1 vs old 20. rc2g's one MAJOR: LOD2 lapel close-up, a large orange
  patch at her right chest / shoulder (the r57 face-poke). Old faults named: jeans through the coat back, orange
  elbows, fanned pockets / lapels, lumpy buttons, a jeans flap at the hip.
- SHEET workspace/human_renders/gr_r56_tess.png checked: reference first per pair; fixed misleading / clipped captions
  (row 2 photo-light faces are rc2c renders from r54: now captioned "rc2c ..." and said in the title; "GAME RIG neutral"
  overflowed into the next column; the rc2c smile tile is a mouth crop: "rc2c mouth"). r56/sheet_r56_orig.py = before.
STATE: rc2g A/B won 10 / 10; sheet fixed. NEXT: rc2h looks (r57/geh) vs rc2g.
- rc2h (exp/rc2h_tess = rc2g + the r57 push: LOD0 sweater 4 vertices / 1 face and jeans 2 / 1 poking -> 0; LOD1 / 2 / 3
  sweater 10 / 6 / 2 -> 0): triangles identical to rc2g (positions only). LOOK r57/lapel_g_vs_h.png (rc2g top, rc2h
  bottom, LOD0 / 1 / 2 lapel close-ups): the orange specks are UNCHANGED (LOD0 her left chest by the armhole, LOD1 her
  right chest, LOD2 a large hexagonal patch at her right chest by the armhole + a speck under her left chest pocket).
  So the r57 push fixed real pokes (q15) but NOT these specks. Ruled out: holes in the coat along +z (q16: a ray grid
  behind both chest sides hits the coat everywhere, LOD0 and LOD2), orange in the coat's basecolor atlas (0 orange texels).
  Suspects, unchecked: the sweater SLEEVE / armhole poking out at the coat's armscye seen at the close-up camera's angle
  (q13 only tested +z rays, centroids, |x| 0.11-0.3), or the sweater's shading leaking through a coat face the renderer
  culls (back-facing coat triangles: the coat is two-sided by shells, materials single-sided?).
STATE: rc2h exported + rendered (r57/geh, sheet workspace/human_renders/gr_r57_tess.png); specks open.

## Handover r57 (assembly agent, tool-call budget)
- Nothing running (r57/chain4 finished; r56 chains finished).
- Best RC: rc2h (exp/rc2h_tess; r57 push-under at LOD0 + per face, commits 378e0965 ...). Triangles LOD0 89,995 / 103,000,
  LOD1 43,273 / 51,500, LOD2 24,096 / 25,750, LOD3 10,146 / 12,360: all under. Joe's sheet for rc2g:
  workspace/human_renders/gr_r56_tess.png (captions fixed); rc2h: gr_r57_tess.png (same layout; checked; title shortened: the old one ran off the sheet and claimed "sweater kept under the coat", which the specks contradict).
- Blind A/B rc2g vs rc2 / rc2e: rc2g 10 / 10, MAJORs 1 vs 20 (r57/blind_g). Not rerun for rc2h (same look).
- NEXT: (a) THE ORANGE SPECKS: render an object-ID (flat colour per part) frame from r56/shots_zoom.json's lapel camera
  at LOD0 and LOD2 to name the part and spot that shows orange (sweater body vs sleeve), then cast rays FROM THAT CAMERA
  (not +z) through the speck pixel to see which layer is first. (b) LOD2 pockets: her left hip pocket stands off as a
  twisted flap and her left chest pocket crumples at LOD2 (kept whole over a coarser panel): project kept pieces onto the
  decimated panel + a lift, or drop LOD_KEEP_OUTER_PIECES at LOD2 only and accept fans (A/B them). (c) LOD2 back: pale
  fleck on the jeans' left calf.

## r58 (2026-10-18, assembly agent, fresh session): the orange specks named, LOD2 pockets, calf fleck, rc2i
Scratch /mnt/data/hifipushie/assembly/r58/.
- SPECKS NAMED: blender_game GE_FLATID=1 (debug: a flat emission colour per object, back faces at a third, legend printed
  as @@flatid) on rc2h LOD0 / LOD2 from r56's lapel / pocket / calf cameras (r58/fid/): the LOD2 hexagonal patch at her
  right armhole is the SWEATER's front faces (same colour as the sweater in the opening), not a coat hole or coat back
  faces. The shot poses nothing (r58/lapel2_dump.npz: every mesh 0.0 mm from rest), so it is the GLB's own geometry.
  r58/pick.py (Blender ray_cast through the pixel from the shot's camera): sweater f74 at (-0.182, -0.079, 1.272)
  (Blender axes) 5 mm IN FRONT of the coat (f464 / its inner twin), the body 6 mm behind. The vertex test, the r57
  centroid test and my +z / camera-ray probes of vertices and centroids (r58/q1.py, q1v.py) all said covered: the coat
  bends between the sweater's sample points (LOD2 sweater 140 outer faces, a few cm each). r58/q2.py: a barycentric grid
  (4 steps per edge) finds 16 poking faces at LOD2 where the centroids find 0 (LOD1 6 vs 0, LOD3 2 vs 0, LOD0 19 vs 2).
- FIX (general, lods.push_under_layers): each outward face is tested at lods.face_grid(LOD_UNDER_FACE_GRID = 4): the
  centroid + 12 grid points without the corners; a point more than LOD_UNDER_FACE_DEEP (8 mm) outside its cover is a face
  running out from under the cover's edge (sweater cuffs past the coat sleeve: -20 mm), left alone. r58/q3.py on rc2h
  LOD2: the pick ray's first layer sweater -> COAT at both speck pixels; 5 poking faces, 26 vertices moved, max 9.5 mm.
  Test test_lod_under_face_grid_finds_pokes_away_from_vertices_and_centroids (a dent at an edge middle: centroids miss
  it, the grid fixes it; the DEEP cap leaves a run-out alone); LOD / under tests 13 pass.
STATE: specks fixed in code + test, committed. NEXT: LOD2 pockets, calf fleck, then export rc2i.
- LOD2 POCKETS (general, lods._lod_shell): LOD_SEAT_PATCHES re-seats outer pieces kept whole (patch pockets) on the
  DECIMATED panel: each piece vertex at its closest point on the decimated rest of the outer shell + its LOD0 signed offset
  along that face's normal (_patch_offsets / _seat_patches, within LOD_SEAT_REACH 2 cm; report key patches_seated).
  Test test_lod_patch_pockets_seated_on_the_decimated_panel (a pocket 2.6 mm over a bumpy two-sided panel ends 2.6 +- 0.3 mm
  over the 10% panel; worse without). Offline probe from the GLB is not possible (the GLB's outer splits at uv seams into
  small pieces): judged in the rc2i export.
- CALF FLECK (LOD2 back) NAMED, not fixed: flat-ID = SOCKS (r58/fid/z2_calf_back.png, with dark back faces); r58/pickcalf.py:
  sock faces at her left ankle back (Blender (0.153, -0.02, 0.17)) 4-8 mm outside the jeans hem. The decimated sock top
  under the jeans is crumpled: its vertex normals point every way within 1 cm (r58/q6.py), so push-under (along each
  vertex's own normal) pushes the wrong way / finds the far side (offline: still socks first at all 3 pixels).
STATE: seat + test committed; rc2i (r58 grid push + seat) exporting via r58/chain5.sh. NEXT: looks, A/B vs rc2h, sheet.
- rc2i (exp/rc2i_tess = rc2h + r58 face-grid push-under + seated patch pockets; r58/chain5.sh). Triangles LOD0 89,995 /
  103,000, LOD1 43,273 / 51,500, LOD2 24,134 / 25,750, LOD3 10,150 / 12,360: ALL UNDER.
- LOOK (mine, r58/h_vs_i.png, rc2h | rc2i): the LOD0 / LOD1 chest specks are GONE, and so is the LOD2 hexagonal patch at
  her right armhole; LOD2 left chest pocket reads flatter. Still there: a small orange speck under her left chest pocket at
  LOD2, her left hip pocket at LOD2 (flatter than rc2h's twisted flap but still a crumpled flap), the sock fleck on the
  left calf (expected, not fixed), and the grey neck gap at LOD3 (sweater collar cut off: both builds).
- BLIND A/B (fresh subagent, 9 tiles rc2h vs rc2i, r58/blind, key abkey.json): rc2i better on 6 tiles, rc2h on 1 (LOD2
  hips: the reviewer says rc2i's left hip pocket is "crumpled with a folded flap" and names a skin-coloured patch in the jeans
  fly), same on 2 (far LODs). MAJORs rc2i 4 vs rc2h 8. Faults both builds share: the LOD3 grey neckline gap, crumpled
  LOD1/LOD2 pockets, the calf shard.
- SHEET workspace/human_renders/gr_r58_tess.png: row 2 (photo-light faces) is now from the CURRENT build (rc2i,
  r54/shots_pl.json -> r58/pl/rc2i_pl_pl_*), so the whole sheet is one build. Captions shortened ("photo neutral" etc.:
  the long ones ran into the next column). Checked: reference first in each pair, nothing clipped.
STATE: rc2i is the best RC, 6/1/2 vs rc2h. NEXT: see the Handover.

## Handover r58 (assembly agent, tool-call budget)
- Nothing running (r58/chain5 finished).
- Best RC: rc2i (exp/rc2i_tess). Commits 5e8f95be (face-grid push-under, GE_FLATID), 7cd962d2 (seated pockets), + notes.
- Debug tools: GE_FLATID=1 bash ge.sh ... (a flat colour per part, legend as @@flatid); r58/pick.py / pickcalf.py (Blender
  ray_cast through a pixel from a shot's camera: every surface along the ray). Name the part before you theorise.
- NEXT: (a) LOD2 left hip pocket still crumples: check the report's patches_seated for the coat at LOD2 (is that pocket in
  small_o at all? LOD_PATCH_GAP 6 mm may leave it out, so it is decimated with the panel), flat-ID it, and pick-ray it.
  (b) Calf / ankle sock shard: the decimated sock top under the jeans hem is crumpled (normals every way), so push along
  the LOD0 normal of the nearest LOD0 vertex (under_at_lod0 masks have positions; add normals) or cull the sock's covered
  top. (c) LOD3 grey neckline gap (the sweater collar cut off); (d) a skin-coloured patch in the jeans fly at LOD2 (named
  by the reviewer; unchecked); (e) a small orange speck under her left chest pocket at LOD2.

## r59 (2026-10-18, assembly agent, fresh session): the white crown, LOD2 pocket / sock / fly, LOD3 neckline, rc2j
Scratch /mnt/data/hifipushie/assembly/r59/.
- WHITE CROWN NAMED (r59/cr/crown_grid*.png, r59/pickc.py = a ray pick through any game shot's pixel, with the material):
  GE_FLATID: the patch is the HAIR part (cards and some cap faces, material rc2_tess_hair_material_hair). Lights with
  specular 0 (shot "lighting" = the game rig with "specular": 0): GONE; specular only: the patch alone. Without the hair
  normal map: still there. Hair roughness 0.75 / 0.65: GONE. So it is the export's hair material: (1) the card ORM's
  roughness is max(look 0.42, 0.5) x (1.25 - 0.4 aux.b) = 0.425 on the outer, lit hair (below its own 0.5 floor), and
  (2) the combined character GLB (asset.py) gives the hair the default KHR_materials_specular (white, x2 = F0 0.04),
  where hair.py's own hair GLB and blender_hair's card material use half, in the sheen's colour. An isotropic lobe at
  0.42 on the crown's flat cards mirrors the key as one white plate. Garrett v5's GLB: the same ([2,2,2], roughness
  0.42 min): a shared cause. Specular level alone (0.25 / 0.15 tinted) did NOT remove it; roughness did.
- FIX (general, both characters): hair.CARD_ROUGH_MIN 0.6 (export ORM floor), asset.py's hair material
  KHR_materials_specular factor hair.CARD_SPECULAR 0.5 x colour hair.card_specular_tint(sheen) (no texture: F0 0.02 x
  tint), shading notes params specular_level 0.25 / specular_tint (+ a formula line), blender_game reads them (older notes:
  0.3 white as before). Probe on a copy of rc2i with the floor-0.6 ORM + tinted 0.25 (r59/cr/f6_*): the plate is gone, a
  faint warm sheen remains. Debug env added to blender_game: GE_HAIR_NONORMAL, GE_HAIR_ROUGH, GE_HAIR_SPEC=level[,r,g,b].
  Note: 0.5 x (1.25 - 0.4 b) <= 0.625, so the floor flattens almost all the aux variation (mean 0.600).
STATE: crown fixed in code (needs an export). NEXT: LOD2 pocket / sock / fly, LOD3 neckline, then export rc2j.
- v5 EXPORTED (EXIT 0): exp/ag_garrett_v5/ag_garrett5.glb + _LOD1..3 (pass 2, 1858 s; OSL bake). Triangles LOD0 84,405 / 103,000
  (head 22,873, body 7,250, hair cards 14,624 (c4L hero), clothing 27,032 of 25,000 OVER, eyes / mouth / lashes 7,994 of 7,996,
  accessories 4,632); LOD1 39,577, LOD2 22,628, LOD3 8,540 (now under every share). Quality lines: teeth_lower 68 folded, shoes 21
  folded; NEW: face shapes "closed lips' seam" eyeBlinkLeft 11.67 mm^2 (limit 0.05: unexplained, check). Game check ag5 (NICO-TOP)
  offload/ag5/results/ag5/j0/out/. LOD1-3 renders came out MAGENTA: the Tess-branch export writes LOD GLBs with maps BY FILE NAME
  beside them, rge.sh copied only the GLB (fixed in rge.sh: copies each GLB's image uris; LOD batch ag5l prepared in offload/ag5l/
  but did NOT start: "no batch named ag5l": relaunch it, not collected).
- LOOK FIRST (mine, s5/look_hair.png): the hair is now SHORT and the right family (no pompadour, close sides, nape tapered) but
  NOT yet his cut: too dark (dark grey vs his light silver), top too short / tight with no sweep (photo: longer top swept to his
  right, more volume, hair lower on the forehead), a black / glossy patch at the crown (coordinator: the hair material, below),
  a lighter thin streak at the crown front. Expressions as v4 (smile s6 fine at front, jaw j3 red interior). Suit charcoal-black
  as measured (4b). Turnaround / walk / run: no new artefacts seen at 4.6 m.
- Specks on v5 (s5/specks/specks_glb.py): SAME as v4 (left collar / lapel top shirt [53 57 1494] mm, right shoulder-blade shirt
  [-210 -63 1456], right underarm body [-215 23 1301], trousers at the right hip back): at LOD0 rest, so neither push-under nor
  the garment cull reaches them: export-side, owner = this assembly (LOD0 cloth decimation of the jacket: 5,254 tris).
- Coordinator: the white glossy crown patch = the export's hair material (roughness map 0.42 under its 0.5 floor, plain white
  specular at double strength). Fix a7618d2d (Tess r59) CHERRY-PICKED here (hair roughness >= 0.6, specular halved + sheen-tinted;
  game preview reads it). v5 does NOT have it: the next export will.
- BLIND REVIEW (fresh subagent, 10 trios s5/ab/t*.png, key s5/ab_key.json, v4 vs v5): coordinator's summary: the short cut (v5)
  won 8/10 trios; top faults: hair surface / crown, the face, the shirt collar slivers, jacket specks, nape drips.
- JOE SHEET: sheets/garrett_v5_joe.png (HAIR front / 3/4 + side / back, FACE, TURN, MOTION, GAME 1 m / 3 m, LODs; reference first
  in each row, every column captioned). Its LOD1-3 cells are MAGENTA (missing maps in the job, not the asset): rebuild that row
  from offload/ag5l when it has run.
### Handover (assembly_garrett session 5)
- DONE: merges (Tess assembly r51-r56, dress-garrett 8a56a9a9, hair-heads2 c4, projskin2 to s21) + tests; v5 = c4L hero cards (tier
  hero: the LOD0 tier trap found), skin gp_h6c_s21 by id, frozen_s5 (collar v3), two-pass cull_poses; dark suit explained (render
  matches albedo / concept: a colour decision); specks located (export, LOD0); a7618d2d cherry-picked; Joe sheet; blind A/B.
- NOT DONE / NEXT: (1) relaunch the LOD batch: cd offload/ag5l && BATCH=ag5l remote.sh ... jobs/j1 j2 j3 (as rge.sh), rebuild the
  sheet's LOD row; (2) v6 export with a7618d2d (crown material) + hair default tier per role in code (asset: LOD0 tier = "hero"
  for role hero when hair.export.tier is unset; test); (3) LOD0 jacket specks: raise the jacket's share at LOD0 or push the shirt
  under the decimated jacket at LOD0 too (lods.push_under_layers runs per LOD: check it runs for LOD0); (4) clothing 27,032 of
  25,000 OVER; (5) eyeBlinkLeft lip-seam warning; (6) owners: hair-cards (silver sides, longer swept top, hairline, nape drips),
  head / skin (face), dress-garrett (shirt collar slivers, belt, suit colour if Joe wants lighter).
- Nothing of mine in flight (tests3 = game_ready + hair_lods after the cherry-pick, writes s5/logs/tests3.log; not collected).
- UPDATE: LOD batch ag5l DID finish (3 succeeded); renders offload/ag5l/results/ag5l/j*/out/, sheet sheets/garrett_v5_lods.png (not looked at).
STATE: session 5 done. NEXT: look at garrett_v5_lods.png, then v6 with the crown fix.
- LOD2 FLY NAMED (r59/fly.png: LOD0-3 crops; r59/pickc.py on the LOD2 pocket shot): the pick ray at the skin sliver hits
  the BODY (crotch) and then the coat's inside, NO jeans: a slit opened in the LOD2 jeans at the fly. r59/bnd.py (boundary
  edges, positions merged 0.2 mm): jeans LOD0 0 boundary edges in the crotch box, LOD2 12. Suspect: the LOD_BORDER_OVER
  redecimation (border collapses) of the jeans' outer panel, whose border is shared with a made piece (the fly) decimated
  apart. FIX (general, lods._welded_pieces): LOD_BORDER_SHARED skips that redecimation for a group whose border touches
  another group of the part within LOD_SEAM_WELD. Same suspect for the LOD3 NECKLINE (r59/neck.png: at LOD3 the
  sweater's top, collar band and upper chest, is gone down to a diagonal line, the culled body's edge shows): judged in
  the export. Cost: groups that relied on border collapses keep more triangles: check budgets.
- SOCK SHARD (general, lods.push_under_layers): LOD_UNDER_LOD0_NORMAL: after the rounds, a masked (worn, non-garment)
  part's vertices that still poke or have no cover along their own normal move along their nearest LOD0 vertex's normal
  (under_at_lod0(share=True) now also returns the LOD0 normals; asset passes them in the masks). LOD tests 12 pass.
STATE: fly / neckline / sock fixes in code. NEXT: export rc2j (r59/chain.sh), look, A/B vs rc2i, sheet.
- rc2j (exp/rc2j_tess = rc2i + r59 hair material + LOD_BORDER_SHARED on + LOD0-normal push; r59/chain.sh). Triangles LOD0
  89,995 / 103,000, LOD1 43,273 / 51,500, LOD2 24,134 / 25,750 (every part's count IDENTICAL to rc2i), LOD3 11,440 / 12,360
  (rc2i 10,150: jeans 346 -> 1,012, coat 976 -> 1,338): ALL UNDER. GLB hair: specularFactor 0.5, colour (1, 0.70, 0.49),
  ORM roughness min 0.60. Push-under LOD2 remaining: socks 9 -> 8, body 7 -> 4 (the LOD0-normal pass helps little).
- LOOK (mine, r59/crown_i_vs_j.png, r59/i_vs_j.png): the crown's white plate is GONE (a faint warm sheen left). Unchanged:
  the LOD2 fly slit (skin + grey), the LOD2 left hip pocket's crumpled flap, the LOD2 shin / calf sock shard; the LOD3
  neckline is NOT fixed (worse: see A/B).
- BLIND A/B (fresh subagent, 6 tiles, r59/blind, key r59/abkey.json): rc2j better on crown front, crown 3/4, face 1 m,
  calf (slight); same on LOD2 hips; rc2i better on LOD3 neck (rc2j: "a large grey wedge-shaped hole across the throat",
  lapels more shattered: the LOD_BORDER_SHARED side effect). The reviewer still calls a duller crown patch MAJOR on rc2j
  and stepped card edges on the crown silhouette (cards build).
- LOD_BORDER_SHARED turned OFF (committed): the fly hypothesis was wrong (LOD2 untouched by it, slit unchanged) and it
  made LOD3 worse + 1.3k triangles. The next export = rc2j's hair + LOD0-normal push without it (LOD3 back to ~10.15k).
- SHEET workspace/human_renders/gr_r59_tess.png (rc2j, one build; unchecked by me).
STATE: rc2j beats rc2i 4/1/1 on the hair; LOD3 regression is off in code. NEXT: Handover.

## Handover r59 (assembly agent, tool-call budget)
- Nothing running (r59/chain.sh finished, SHEET_DONE). Commits: a7618d2d (hair material), 9053d387 (LOD shared borders +
  LOD0-normal push), + this (LOD_BORDER_SHARED off, notes).
- Best RC: rc2j for the hair (the crown plate fixed), but its LOD3 carries the LOD_BORDER_SHARED regression: RE-EXPORT
  (rc2k = current code) before giving it to Joe; expect LOD2 = rc2j, LOD3 = rc2i's geometry with the r59 push.
- Debug tools: r59/pickc.py <glb> <focus bone> <lift> <dist> <dir> <W> px py ... (ray pick through any ge shot pixel,
  with the material); r59/bnd.py (boundary edges of a part in a box); blender_game GE_HAIR_NONORMAL / GE_HAIR_ROUGH /
  GE_HAIR_SPEC; shot "lighting" with per-light "specular": 0 / "diffuse": 0 splits diffuse from specular.
- NEXT: (a) LOD2 FLY SLIT: no jeans along the pick ray at the crotch at LOD2 (12 boundary edges vs 0 at LOD0), NOT from
  the border-collapse redecimation. Probe the jeans' _lod_shell offline (dump the LOD0 jeans part dict from the export, run
  lods.lod_part at 0.25, boundary edges in the crotch box after each step: decimate / seat / _lift_made / push-under).
  (b) Sock shard (LOD2 shin/calf): still there; the LOD0-normal pass moved few. Cull the sock's covered top at LOD2+ instead
  (faces whose LOD0 points were all under the jeans). (c) LOD3 neckline: the sweater's top is gone at LOD3 (138 triangles):
  check whether its collar band is a made piece dropped by LOD_KEEP_PIECE_FAR / the made floor. (d) LOD2 left hip pocket
  flap: unchanged. (e) Crown: the card silhouette steps and a dull sheen remain: cards thread. Garrett v5 shares the
  hair-material cause; his next export picks the fix up.

## r60 (2026-10-18, assembly agent, fresh session): rc2k re-export, the LOD2 fly slit probed offline, sock / neckline / pocket
Scratch /mnt/data/hifipushie/assembly/r60/. Hair: the cards thread's round 36 did NOT make f1 the default ("no round-36
build beats f1"): nothing to take.
- rc2k export started (r60/k.sh = rc2j's chain with the current code: LOD_BORDER_SHARED off) with a new debug dump:
  asset.export HP_LOD_DUMP=<pkl> pickles the LOD inputs (parts minus cards / prefabs, rigged, layer_stack, under_masks,
  ratios, above / below) so a part's LOD steps can be probed offline (r60/probe.py <pkl> <part> <k>: new boundary edges
  > 1 cm from LOD0's, clustered, after lod_part and after push-under).
STATE: rc2k exporting. NEXT: probe the jeans at LOD2 on the dump.

## Garrett, session 6 (2026-10-18, assembly_garrett, fresh; scratch /mnt/data/hifipushie/assembly_garrett/s6/)
- (1) LOD0 HAIR TIER (code, asset.hair_tier_default): a card / strand groom with no hair.export.tier now takes the role's
  tier at LOD0 (ROLE_HAIR_TIER: hero -> hero, main_npc -> main, secondary_npc -> npc, crowd -> far; logged); no role keeps
  EXPORT_CARDS' old per-lock cut with a WARNING (never silent). An explicit tier wins: Tess's ga_tess / rc2_tess specs set
  tier "hero", so her export is unchanged. Test test_lod0_hair_tier_defaults_to_the_role.
- (2) MERGED the Tess assembly branch to b582d3c9 (r56-r59: face-grid push-under at LOD0 (13 points per face), seated patch
  pockets, cull_exposed_keep / cull_poses, LOD_BORDER_SHARED off, a7618d2d crown material). Notes conflict = union.
  Specks re-checked on the v6 GLB (s6/logs/specks_v5.log vs specks_v6.log, s5/specks/specks_glb.py).
- (3) CLOTHING BUDGET (code, asset.decimate_cloth): one shared ratio cloth_triangles / n overshot (made pieces, held borders
  keep floors: v5 shirt 9,422 for a 7,885 share; 27,032 of 25,000). Now up to CLOTH_BUDGET_ROUNDS 4 rounds scale the ratio by
  the overshoot until the sum fits (WARNING if not). Test test_cloth_decimated_under_its_budget_despite_floors. Cost: the
  jacket loses ~8% of its LOD0 triangles too (watch the specks).
- (4) eyeBlinkLeft LIP SEAM WARNING, CAUSE: faceshapes measured the blink on the PARTED rest (GNM parted neutral, r44) while
  the "closed" check uses mouthClose; eyeBlinkLeft alone = the parted lips' gap (Garrett 11.67, Tess rc2 3.23 mm^2 too, with
  mouthClose 0.000). Not a blink fault. Fix: the blink is measured with mouthClose added ("eyeBlinkLeft+mouthClose"), the
  parted rest logged ungated beside it. Confirmation = v6 log line (expect ~0 for blink+close, ~11 for the rest).
- (5) HAIR: c6M (hair.md BEST GARRETT CARDS) = c4L cards + hair.BACK_FACES 1: hair-heads2 merged at f82d9685 (c6 BEST, cut
  defaults back to c4L), NOT c8's TILE_REP_DRAWN default (unjudged). The character GLB's hair material is single-sided when
  the cards carry their own back faces (asset; hair-heads2 only did it for export_hair). Model ag_garrett6 = ag_garrett5's
  spec (tier hero, card_gain 2.1, skin s21, frozen_s5).
STATE: v6 chain running (s6/chain.sh: export -> specks v5 / v6 -> rge ag6 on NICO-TOP; PIDs s6/PIDS). NEXT: collect, LOOK, A/B, sheet.
- v6 EXPORTED (exp/ag_garrett_v6, 2,100 s). Triangles LOD0 93,729 / 103,000 (clothing 24,832 / 25,000 UNDER now; hair_cards
  26,148 / 25,000 OVER: c6M's back faces double the card triangles: hair-cards' call), LOD1 39,713, LOD2 19,366, LOD3 8,550.
  LOD0 hair 26,148 = hero tier. SEAM: "mouthClose 0.000, eyeBlinkLeft+mouthClose 0.000 (parted rest, not gated: 11.670)":
  the cause CONFIRMED (the parted rest, not the blink); no warning now.
- SPECKS (s6/logs/specks_v5/v6.log): NOT fixed. The left collar / lapel-top shirt sliver [54 57 1494] 34 -> 33 px; front
  speck px 6,512 -> 8,806, back 663 -> 1,842 (the jacket 5,254 -> 5,022 tris). CAUSE FOUND: Garrett's frozen garments carry
  no "over" key (spec cloth.* = color / frozen only), so asset._garment_stack is EMPTY: no garment push-under ran at
  LOD0-3 (the log has no "LOD0: under garments" line; LOD1-3 list only shoes / socks / body). The Tess fixes never applied
  to him. The game check shows it plainly at LOD1-3: white shirt shards through the jacket fronts / sleeves, LOD3 a black
  shirt front. v6b = ag_garrett6b (spec: jacket.over trousers, trousers.over shirt) exporting (s6/chain_b.sh: export + specks).
- LOOK (mine, s6/look_v5_v6.png, game check offload/ag6): faces same; v6 crown sheen fainter than v5's white plate (front),
  still a light patch; the back keeps a hard horizontal crown LEDGE (cap edge) in both; the white speck at the jacket's
  upper back in both. BLIND A/B (fresh subagent, s6/ab, key s6/ab_key.json): v6 better 6, same 3, v5 0. Its MAJORs: hair
  shingled / too dark vs the grey photo, crown ledge from the back (both), crown sheen (v6 milder, still there).
- SHEET sheets/garrett_v6_joe.png (1990 x 1530, s6/sheet.py: reference first per row, captions, magenta check per cell).
STATE: v6 = RC (best, 6/0/3 vs v5); v6b (garment over chain) exporting. NEXT: v6b specks vs v6; if fewer, game check ag6b.
- v6b (over chain) at LOD0: "cloth_shirt poking 223 vertices / 220 faces -> 3 (672 moved)": the garment push-under now RUNS
  (v6 had none). LODs / specks were still running at the handover.

### Handover (assembly_garrett session 6, tool-call budget)
- DONE: (1) LOD0 hair tier by role (asset.hair_tier_default, test; Tess unchanged: her specs set tier hero). (2) Tess branch
  merged to b582d3c9 (r56-r59). (3) clothing under budget (asset.decimate_cloth rounds, test): 24,832 / 25,000. (4) blink seam
  warning = measuring the blink on the PARTED rest; fixed the check (blink+mouthClose 0.000; rest 11.67 logged). (5) hair-heads2
  merged at f82d9685 (c6M: back faces; single-sided hair material in the character GLB); v6 exported + game check ag6; blind A/B
  v6 6 / v5 0 / same 3; sheet sheets/garrett_v6_joe.png. Specks cause: no "over" chain on Garrett's frozen garments.
- RUNNING (unattended, PIDs s6/PIDS): s6/chain_b.sh = v6b export (exp/ag_garrett_v6b) then specks -> s6/logs/specks_v6b.log,
  writes s6/CHAIN_B_DONE. No game check queued for it.
- NEXT: (a) compare specks_v6b vs specks_v6 (the [54 57 1494] collar sliver, back px); if better: LODSHOTS=1 bash rge.sh ag6b
  exp/ag_garrett_v6b s5/shots_ag5.json, look at LOD1-3 (v6's LOD1-3 had white shirt shards through the jacket, LOD3 a black
  shirt front), A/B vs v6, rebuild the sheet (s6/sheet.py: change O to ag6b). (b) Code: _garment_stack could fall back to the
  cull's own "cut under" pairs when no "over" is given (frozen garments lose it), so this can't silently happen again.
  (c) Owners: hair-cards (hair_cards 26,148 / 25,000 with back faces; crown ledge from the back; crown sheen fainter but there;
  hair too dark / shingled vs the grey photo), dress-garrett (frozen garments should keep "over"; shirt collar slivers).
STATE: session 6 done; v6 = RC, v6b in flight. NEXT: (a) above.

## Garrett, session 7 (2026-10-18, assembly_garrett, fresh; scratch /mnt/data/hifipushie/assembly_garrett/s7/)
- (2) GUARD (code, asset.garment_over): the frozen pickles DO carry "over" (jacket over shirt, trousers over shirt: d["g"]),
  but the export read the spec's raw {"frozen", "color"} dict, so _garment_stack and the r53 under-garment cull were empty.
  Now a frozen garment without "over" in the spec falls back to the "over" frozen with it (the chain cloth's own layered cut
  uses via thaw; memoised by path / mtime / size), logged ("garment layers: ... using the frozen garments' own chain");
  2+ garments with no chain anywhere = WARNING. Spec "over" wins. On ag_garrett6: {cloth_shirt: [jacket, trousers]} (the
  frozen chain has no jacket-over-trousers; v6b's spec chain jacket > trousers > shirt adds it). Test
  test_frozen_garments_keep_their_over_chain_in_the_export.
STATE: guard committed; v6b export at LOD2 (s6/chain_b.sh, not mine: collecting). NEXT: v6b specks, crown ledge.
- (3) CROWN LEDGE from the back = THE CARDS (hair thread), not the export. Evidence (s7/standoff.py, s7/crown.py; GLB
  geometry only): along the back (x = 0 / +-30 mm) the hair's outer radius (p98) minus the head's, by elevation about
  (0, 0, 1.66): 3-4 mm up to ~60-66 deg, then 9-10 mm from ~66-72 deg to the top: a 6-7 mm STEP. c6M's own hero GLB
  (hair_garrett/cards/exp/c6M/hg_G88a_hair_hero.glb) on the same head gives the SAME numbers to the mm, so the export
  (cap / card seam, single-sided material) adds nothing. The z-buffer from the back shows the crown solidly covered by
  cards (no scalp / cap showing there): the "plate" is the top class's cards standing 10 mm off, seen at a grazing angle,
  their lower ends the jagged rim (game-check x_hair_back.png). c6o's own back render (out/s_hg_G88a_c6o_g1back.png, other
  light / camera) hides it. Routed to hair-cards: the top layer needs to come down to the back's standoff (or the back
  layer to grade up to it) across el ~60-75 deg.
STATE: guard committed; ledge routed (cards). NEXT: v6b specks when s6/chain_b.sh ends (export at LOD3 + worn push-under).
