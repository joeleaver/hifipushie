# hifipushie notes: rig

Moved out of CLAUDE.md on 2026-10-09 so agents don't load every thread's history.

- `rig.py`: the export rig, a separate step over the modelling skeleton (the user, 2026-09-25: humanoids must be
  Mixamo-compatible and Unity/Unreal-retargetable, clean bone chains for non-humanoids too; spec bones stay for
  modelling). `humanoid` fits Mixamo's skeleton (mixamorig:Hips, Spine/1/2, Neck, Head, clavicles, arms, hand-kit
  fingers as Thumb/Index/Middle/Ring/Pinky 1-4, legs, ToeBase, *_End) to pelvis/chest/neck/head/limb joints (Neck
  at shoulder height, clavicles 20% out from it; `spec["rig"]["joints"]` overrides); `chains` for other creatures
  (`spec["rig"] = {"type": "chains", "root", "chains": {name: {"from", "joints"}}}`). `rig_weights`: each rig bone
  gets flesh: the piece of a modelling cone it lies along (`_cone_piece`: Spine/Spine1/Spine2 split the spine
  cone), modelling bones inside its segment, the rest by the nearest rig segment to their middle, blobs by their
  middle; empty rig bones get a thin cone. Then `weights` on the rig tree: exact per-flesh distance,
  exp(-(d - d_min) / (0.5 r)), limited to the nearest bone's family within two steps (unrelated bones crowding the
  4 slots made cracks), smoothed over the mesh, top 4, then `_settle` (smoothing with each vertex's 4 fixed, so a
  dropped bone fades instead of stepping: hairline cracks). Judge with the `rig` tool (test pose, front/side);
  export_asset(rig=True) writes the joints (identity rotations at their heads, rest pose as modelled) and skin.
  `skin_parts` (export and the rig tool): `parts.<p>.rig_bone` binds a part rigidly (a bag to Hips, a disc to
  RightHand: split between bones they tore); with a base, rig flesh is a cone per rig segment sized from the base
  body and every part blends the weights of the base quads' 4 nearest vertices (the export's skin under clothes is
  dropped, so clothes can't copy from it). A base's fingers (fingerN_k / thumb_k) fill the Mixamo hand.
  Export scene parts finer than the model voxel (`scene.part_voxel`) get their own grid (a 6 mm collar shredded at 7.8).
  `spec.geometry` strips `rig`.
  Twist chains + rigid head (2026-10-05, s0urc3's Garrett: a hand turned 75-105 deg was wrung at the wrist, the jaw
  lagged a head turn; renders `workspace/rig_renders/tw_*`): `_add_twist` appends leaf joints AFTER the Mixamo set
  (its names / order / indices / rest unchanged), children of their segment's joint: `<Side>ForeArmTwist1..3` and
  `LegTwist1` follow the Hand's / Foot's roll (share k/n at station k/n, 1.0 at the wrist), `ArmTwist1..2` and
  `UpLegTwist1` counter their own joint's roll (-1.0 at the shoulder / hip). `spec.rig.twist` = false | n | {arm,
  forearm, upleg, leg} (default 2/3/1/1: LBS between stations d apart keeps cos^2(d/2) of a section; forearm at
  105 deg on MakeHuman: none 0.49, two 0.80, three 0.87). Twist bones carry no flesh (`_segments` skips them):
  `_spread_twist` shares the segment bone's weight between the two stations a vertex lies between, so undriven the
  skin is the old skin. A fifth bone: the smallest weight is dropped, unless a split's smaller half is within
  `TWIST_MERGE` x it, then the split goes back (always dropping moved the goblin's arm/belly web 10 mm undriven;
  always merging sheared thigh triangles when driven; now <= 3.5 mm on 2% of its vertices). Driving is the engine's
  (glTF has no constraints): `drive_twist` / `roll_about` (swing-twist) are the reference, the GLB's twist joints
  have local +Y along the segment and `extras.hifipushie_twist`, the json has `rig.twist` + `rig.twist_recipe`
  (Godot / Unity / Unreal; `asset.TWIST_RECIPE`). `head_field`: h = 1 where a point is head, by the Head bone's
  flesh being no farther than any other's (kit characters), a floor from GNM's jaw landmarks (chin -> jaw angle,
  level behind, `HEAD_UNDER` lower), or typical proportions (a base without landmarks); `_rigid_head` blends weights
  to Head by h (falloff `HEAD_BAND` on the throat), a part >= 0.9 head on average is all head (teeth, tongue,
  eyes); the export then makes every vertex a face shape moves 3 mm or more Head 1.0, less in proportion from 0.5 mm (`rigid_near`; a big jaw's field reaches the goblin's chest by fractions of a mm). Judge with the
  rig tool's text (`rig.report`: `twist_check` per chain, `head_check`) and `pose={"RightHand": ["roll", 105]}`.
  Known: twist bones fix roll, not bend (shoulder dip, elbow crease stay); a 33 deg head turn folds the throat
  under the jaw over the 3 cm band. `tests/test_rig_twist.py`.
  Weights audit + template weights (2026-10-05/06; the user on the twist sheets: "the fingers are getting mangled and
  so is the jaw. We might have serious issues with how our skin weights are getting made"; renders `rig_renders/wa_*`).
  Three things were tangled: (1) the rig tool's look build (11 mm voxels on a human: fingers fused AT REST; the real
  export's hand is fine at rest); (2) the weights: by distance, one finger's bones held 0.2 of the next finger and
  moved it 4-8 mm, a thigh moved the other thigh 20 mm; (3) the RIG: on MakeHuman bodies the "neck" joint is the
  neck's BASE, so Head (placed on it) pivoted 10 cm low, at chin height, and Neck sat inside the chest.
  - `rig_audit.py`: `read_glb` (an export as an engine gets it), `audit` (each joint turned alone through
    `AUDIT_TURN`: rigid = its own skin against a rigid turn, leak = other bones' skin moved and whose, flipped
    triangles, volume on closed meshes; digit bleed; L/R asymmetry; sums, influences) and `audit_text` ("<- BAD").
    Ownership is by nearest bone segment, so it only judges CLEAR skin (`CLEAR` 0.7: the web between two fingers and
    the knuckle zone are nobody's; `BURIED` bones, clavicle and thumb metacarpal, are judged on their descendants):
    without that it called MakeHuman's own hand-made weights bad (bleed "0.94") while every pose was clean.
  - `rig_template.py`: a base body made from MakeHuman takes MakeHuman's hand-made weights (`makehuman.weights()`,
    rigs/default_weights.mhw, CC0) by TOPOLOGY (`base.surface()["src"]` = each quad vertex's template index, kept
    through the neck graft), its 139 bones folded onto the Mixamo joints (`_mixamo`; spine / neck bones by where
    they lie, `_central`; face, jaw, tongue, eye bones -> Head). Every other mesh (the export's low poly, clothes)
    reads the base's weights at the closest point of its SURFACE that faces the same way (`from_surface`,
    `AGAINST`): the 4 nearest base VERTICES of a finger's side were as often the next finger's. Then
    `_spread_twist`, then the rigid head. `spec.rig.weights = "distance"` for ours; the stylised template and kit
    characters have no hand-made weights and stay on distance (now also read by surface).
  - `rig.humanoid`: a template's `rig` hint ({rig joint: [joint a, joint b, t]}; `makehuman.body`) places Neck on
    the "neck" joint and Head 63% of the way to "head" (MakeHuman's own head bone); clavicles stay where they were.
    This MOVES Neck and Head on MakeHuman characters (names / order unchanged): re-export, and a game's cached rest
    pose changes.
  - Exported human (15k), same mesh re-skinned: BAD joints 13 -> 5 of 51; digit bleed 0.21 -> none; fingers'
    leak 4-8 mm -> 0; thigh on thigh 20 mm -> 0; knee rigid 5 mm -> 0. Left BAD are MakeHuman's own choices at our
    thresholds (elbow at 90 deg moves upper-arm skin 8.6 mm, the foot's weight runs 25 cm up the shin) and 35
    flipped triangles in one groin at 60 deg.
  - The mouth and jaw that looked "mangled": at REST the 15k export's mouth is already faceted and lumpy, and
    jawOpen alone (no weights) is lopsided: the low poly and the face shape, not the skin. Not fixed here.
  - Bone heat (Blender automatic weights) vs ours on kit characters (look builds): goblin 13 vs 17 BAD of 45 (rigid
    better, leak worse: 30 vs 13 mm arm <-> thigh), troll_anat 40 vs 38 of 51. Neither is good: their limbs are
    fused to the body in the look build. Not adopted; kit creatures' weights are an open problem.
  - Dressed characters (2026-10-05, the golfer's export re-skinned; renders `rig_renders/wa_golfer_*`): (1) the
    grafted neck/head copied the template neck LOOP's weights all the way up (Shoulder 0.38 / Arm 0.19): an arm at
    60 deg pulled the neck's side and the collar 25-36 mm. Now it hands over to the Neck joint within
    `rig_template.GRAFT_REACH` 4 cm. (2) The head rule is by height, so a collar's top (1-2 cm over the floor at the
    nape) was Head 1.0 and turned with the face (47 mm, 299 flipped): a part other than the skin (`spec.rig.skin_part`,
    "body", + face_shapes.parts) that is under `HEAD_WORN` 0.5 head is worn and takes no head rule;
    `parts.<p>.rig_head` overrides. (3) A worn part's transferred weights are smoothed `WORN_SMOOTH` 6 rounds over
    its own mesh, seam-split vertices welded (a collar's two faces and edge read three places: its wing crumpled).
    (4) The head floor climbs one jaw landmark up the ramus behind the jaw's angle; up to the Head joint it put the
    ear lobes in the band (30 flipped triangles under each ear). The audit counts smoothed cloth as leak and cloth
    folding at 60 deg as flipped: read its cloth rows with the renders. Open: a strap shell beside a rigidly bound
    bag shreds at the hip, hems fold (no hem bones), fingers touching round a held disc read the wrong finger.
    Then: `parts.<p>.rig_attach = "<part with rig_bone>"` (within `ATTACH` 8 cm of it the part blends to that
    joint: the strap's end goes with the bag; 48 flipped strap triangles at a 60 deg thigh -> 9), `rig_smooth`.
    A neighbour-majority mend of stray digit vertices was tried and dropped (it missed the one welded vertex in
    the web and worsened another). Hems: guide only (no hem bones).
  - Judge exports as an engine draws them: `rig(glb=)` leads with `asset.preview` of the GLB (maps + normal map;
    preview poses take `"turns": {joint: [x, y, z, deg]}`, carried into each imported bone's rest frame as
    rest^-1 R rest, plus face shapes) over the clay row. The human's "lumpy mouth" was clay: 7.5 mm facets at 15k
    (1,541 face triangles; 40k: 3,690, 4.9 mm) read smooth with the normal map, and jawOpen is symmetric as a
    shape. Real at 15k: a crease beside the nose in jawOpen and kinked smile corners (gone at 40k); real at both:
    the blink's lid line is ragged (open: seal the lids on the low poly as `Face.seal` does the lips).
  - Kit creatures on REAL exports: the goblin (goblin_talk) tears a slab of skin at the shoulder and webs when the
    arm rises, because its arms are modelled against the belly: one skin once meshed. `rig_audit.fused_limbs`
    (the rig tool's WARNING): the share of a limb segment's own flesh surface within `GAP` 8 mm of unrelated
    flesh (goblin_talk 25%, goblin_anat 2%, trolls 8-12%; warns over 20%). The audit takes ownership from the
    modelled flesh on kit characters (`flesh_distances`): by bone segment the arms "owned" 830 belly vertices and
    read 116 mm off a rigid turn.
  - Blink (`GnmFace._lid_seal`, `LID_SEAL` / `LID_OVER` / `LID_BAND`; render `wa_gnm_blink_seal.png`): the basis
    DID close the eye (front rays reaching the ball: 43% open, 0.1% blinked); the ragged line was each low-poly
    margin vertex landing at its own height. Now 14 bins across the eye put both margins on a parabola through the
    lower lid's (each vertex by its share of its margin's travel), then the band 1.5 mm either side is squeezed
    onto its own lid's side. Clean line in clay on the 40k human; 1-2% of rays see the ball at the outer corner
    (the fade past the corners). Not yet seen through a fresh export with maps; the face kit's `_blink` unchanged.
  - Fresh golfer export (2026-10-06, 30k / 2048, scratch `rigtwist/exp_golfer`): Khronos 0 errors 0 warnings;
    audit 11 BAD of 51 (old export 20, old meshes re-skinned 16-17), no digit bleed, Head not flagged; left: knee
    onto the shorts' hem 17-27 mm, arm onto the collar 18-20 mm, forearm 10 mm, cloth flips. workspace/dg_fix2's
    own spec has no `rig_attach` (only the examples do): its strap was exported unattached.
  - HANDOVER (rigtwist agent, context full): branch `worktree-agent-aaa260409e3ad0ff7`. Scratch scripts in the
    session scratchpad `rigtwist/`: aud.py (audit a GLB), reskin.py (re-skin a GLB's meshes with the code as it is;
    env GR / WS / ATT), wa2.py (dressed before/after sheets), blink.py (lid seal before/after + rays), facesheet.py
    (GLB with maps, 6 shapes), dbg8/10/12.py (whose vertices leak / where triangles flip / stray digit vertices),
    fused.py, val/v.mjs (Khronos), expg.py (golfer export). Open, in order: (1) the blink through a fresh export
    with maps + test in test_face_shapes; (2) goblin_anat and troll real exports audited (never run); (3) the
    goblin: its model must be fixed (arms clear), the tool says so; "fail soft" weights for fused limbs not built;
    (4) kinked smile corners at 15k; (5) the throat card; (6) hem bones; (7) a rig check in a real engine.
  - Rig round 2 (2026-10-05/06, "rig2" agent, branch `rig2`; renders `rig_renders/wb_*`; exports in
    /mnt/data/hifipushie/rig2/exp_*; scratch in the session scratchpad `rig2/`: run.sh <script> (worktree code on
    the main workspace), exp.py (export), sheets.py (posed sheets through `rig(glb=)`), reskin.py + cmp.py (re-skin
    an export's meshes with the code as it is, audit, clay rows side by side), throat.py (head falloff variants +
    fold numbers), lidline.py (blink gap per bin), geo.py (surface-geodesic weights spike), val/v.mjs (Khronos)).
    - Throat: the head's falloff on base bodies is `HEAD_FALL` 0.2 x head size (~5 cm), was 3 cm. Skin fold
      (`throat.py`: change of dihedral across the neck's edges) p99 at a Head-only 33 deg turn: bare human 40 -> 24
      deg, golfer 20 -> 12; nod 56 -> 43. A longer falloff on the FRONT of the throat only (the card's idea)
      changed nothing: the fold is at the sides and the nape. Kit characters and `rigid_near` keep 3 cm. A hard
      Head-only nod still folds (the chin meets the chest on these short necks): share it with Neck.
    - Blink: `_lid_seal`'s last step mapped the band either side of the line LINEARLY, which parked the upper
      margin ~0.5 mm above the line and the lower ~0.75 mm below: the thin slit that still showed (gap between the
      margins +0.4 .. +1.5 mm on the head mesh). `LID_PINCH` 3 draws the band to the line: -0.5 .. +0.2 mm.
      `tests/test_face_shapes.py::test_blink_lids_meet` (head mesh and pyfqmr-decimated to a third). A per-bin
      vertex measure is NOT valid on a 15k export (bins without a margin vertex read 25 mm): judge those by render.
    - `parts.<p>.rig_drop = [joints]` (`rig.drop_joints`): a garment's influences pruned, their weight up the chain
      to the nearest kept joint (a name without a side = both sides + the segment's twist joints). Golfer: shorts
      ["Leg"], shirt ["ForeArm"], collar ["Arm"]: knee -> hem 17-27 mm and elbow -> sleeve 10 mm gone, the hem stays
      a tube on the thigh (`wb_drop_knee90.png`). This is the cheap answer to hems; hem BONES still not built.
    - Export: with rig, parts bound to their own joint (`rig_bone`) don't bury their neighbours' faces
      (`surface.hidden(apart=)`, `ctx["apart"]`): the golfer's shorts had a HOLE where the hip bag sat, shown by
      a lifted thigh (a dark patch in every earlier thigh sheet, read as shadow).
    - Assets: `assets.pack(name, files=)`; `makehuman.root` needs only base.obj + default.mhskel, so a male body
      opens with the pack as it was before the female targets and default_weights.mhw were added (s0urc3 BLOCKER);
      missing weights -> distance weights + a WARNING in `rig` and the export log (`rig_template.weights_note`).
    - Kit creatures, spike (`geo.py`, goblin_anat look build at 256): weights from SURFACE GEODESIC distance to each
      bone's own skin (scipy dijkstra over the welded mesh, max with the Euclidean flesh distance) remove every
      leak and rigid error (arm 5.9 mm rigid / 14 mm leak -> 0, thigh on thigh 5 mm -> 0 at full strength, 4-5 at
      half), but blends get narrower and flipped triangles rise at elbows / knees (53 -> 130-270) and Spine2 (420).
      Digit bleed is unchanged on a look build (fingers fused at 3.6 mm voxels). Not adopted yet: see HANDOVER.
    - `rigid_near` (the face-shape pass in the export) skips parts no shape moves: the golfer's collar took Head
      0.56 from the moved throat skin beside it and turned with the face (26 mm at 33 deg) in every export WITH
      face shapes (Garrett too); the worn-part rule held in `skin_parts` only.
    - Fresh exports (all Khronos 0 / 0): `exp_golfer` (dg_fix2, 30k / 2048; BEFORE rig_drop and the hole fix:
      audit 10 BAD of 51, no digit bleed), `exp_gnm` (tw_gnm 15k + face shapes: 5 BAD), `exp_talk` (model
      `workspace/wb_dg_talk` = dg_fix2 + `base.head.interior` + mouth_gap 0.003, no wrap topology; 36k + face
      shapes, with rig_drop and the hole fix, BEFORE the rigid_near fix: its head-turn sheet shows the collar going
      with the head). Sheets `wb_golfer_*` (head33 good; nod: a lump of nape skin between hair and collar from the
      side; arm60 clean; thigh60 shows the hole; handroll105: forearm smooth, dark cracked patches where the hand
      grips the disc, unverified), `wb_talk_*` (thigh60 clean: no hole, hem a tube; blink closed with a clean line;
      jawopen good), `wb_gnm_*` (15k blink: closed, small dark notches at the eye corners; smile fine).
      workspace/dg_fix2's spec now has the strap's rig_attach and the three rig_drops (v8).
  - HANDOVER (rig2 agent, stopped by the session's usage limit, 2026-10-06). Branch `rig2`. Tests green on the
    head: test_rig_twist, test_rig_audit, test_tooling, test_face_shapes. State of jobs: a goblin_anat export
    (15k / 1024) was running into /mnt/data/hifipushie/rig2/exp_goblin_anat (log scratch `rig2/exp_goblin_anat.txt`)
    when the queues were stopped: check whether it finished. NOT started: troll_anat export, the golfer re-export
    (dg_fix2 with rig_drop + hole fix, into exp_golfer) and the talk re-export (rigid_near fix, into exp_talk):
    `bash rig2/run.sh exp.py <model> <out dir> '<json kwargs>'`, one at a time (they take the heavy slot; Oxidegen's
    exports hold it for long stretches). Next, in order: (1) those three exports, Khronos (`node val/v.mjs x.glb`),
    sheets (`run.sh sheets.py <model> <glb> <prefix> [poses]`), the talk head-turn sheet must show the collar
    staying; (2) kit creatures: run `run.sh geo.py goblin_anat 256 <glb>` (ours vs geodesic on the REAL export;
    `GATE=1.5,3.5 MIX=1` = the gated variant, the promising one: Euclidean blend kept, an influence cut where the
    path along the skin is over 1.5-3.5 limb radii), render both in the test pose (`reskin.py` saves weights,
    `cmp.py` draws them side by side), adopt it in `rig.weights` if the renders agree with the audit; watch the
    flipped triangles at Spine2 (413 on the look build: probably the pec / lat sheets) and digit bleed on the real
    mesh; (3) the audit card (id cmuvoqmmf00f8k6f29lu2bvex, NOT the project id) and the throat card
    (cmuvmbarn00f6k6f2jcsm4x7b) still need this round's numbers; the twist and rigid-face cards were already DONE;
    (4) open: hem bones, the nape lump on a nod, the hand / disc dark patches, the arm's 20-25 mm on trapezius
    skin near the neck (MakeHuman's own Arm weight; sheet looks fine), a rig check in a real engine.
  - Rig round 3 (2026-10-06, "rig3" agent, branch `worktree-agent-ac0c3684da084a02f`; renders `rig_renders/wc_*`;
    exports /mnt/data/hifipushie/rig3/exp_*; scratch in the session scratchpad `rig3/`: run.sh, exp.py, sheets.py
    (poses incl. nod_shared, knee90, rest_hips, hand_rest, smile_far / smile_near), strip.py (several sheets' engine
    rows side by side), reskin.py + cmp.py + leak.py (RS=<rs npz> = re-skinned weights), throat.py, geo.py,
    queue1-3.sh, tests.sh, gposes.json (Godot poses)).
    - Geodesic weights for kit creatures: NOT adopted. On the REAL goblin_anat export (15k) both variants are worse
      than ours by the audit (knee rigid p95 14 -> 22-28 mm, elbow 7-8 -> 15-17, leaks 20 -> 25-30 mm; only the
      shoulder's rigid error improves, 11 -> 3.7 mm, with 3x the flipped triangles) and they TEAR in the render
      (cracks in the armpit and the groin: `wc_geo_goblin_knee90.png`, glb = ours on top). On a decimated mesh the
      edge-path distance is 10-40% long and jumps between neighbours, so the gate cuts an influence on one vertex and
      not the next. The spike's good numbers were a look build's dense mesh. goblin_anat's own export (never checked
      before): Khronos 0 / 0, rest / arm 60 / thigh 60 read clean in the engine row (`wc_goblin_anat_*`); its audit
      says 29 of 45 BAD, which on stubby limbs (a blend zone as long as the segment) is the audit's human
      thresholds, not the skin. Digit bleed 0.40-0.45 on its 3-finger hands is real and unchanged.
    - Head falloff (the throat card): on base bodies the head's weight now fades down the neck's LENGTH
      (`HEAD_FALL` 0.44 x head size ~11 cm, was 5) inside the neck's column (`HEAD_COLUMN`: full within 9 cm of the
      Neck -> Head line, none past 15.5; outside it the old 5 cm, `HEAD_SHORT`), and `rigid_near`'s band on base
      bodies is `HEAD_NEAR` ~8 cm (was 3). What riggers paint: a head-to-neck gradient over the whole neck. Bare
      human 15k, Head alone (throat.py): turn 33 deg fold p99 / max 25.8 / 161 -> 11.7 / 30 deg, nod 25 deg 36 / 153
      -> 14.5 / 28, edges folded over 30 deg 16-33 -> 0 (`wc_throat_fall_gnm.png`). Either change alone did half.
      By height alone the long falloff reached the shoulders (trapezius skin moved 70 mm): hence the column. And
      under it a collar averaged over `HEAD_WORN` and turned with the face again (57 mm): which part is head or
      worn is judged on the SHORT field (`hf["part"]`). A `nape` factor (longer behind) changed nothing: left at 1.
      Garments never take the long falloff (tried: the collar crumples). Cost on a dressed character: on a hard
      Head-only nod the nape skin swings back against the collar's stand and pokes a sliver through it
      (`wc_throat_golfer_nod.png`); the chin still sinks into the collar. Both go when the nod is shared with Neck.
      Kit characters unchanged. `spec.rig.rigid_head` = {fall, band, under, column, nape}.
    - `rig_drop` takes shares: `{"UpLeg": 0.5}` = half that joint's weight (its twist joints' too) up the chain.
      The shirt hem on the golfer hardly reads it (its hem is already the pelvis's): no visible change at a 60 deg
      thigh, flipped 41 -> 23. Hems, what riggers do (web search + the guide's section from rig2): weights toward
      pelvis + thighs for shirts and shorts (have), skirt / coat chains driven by the thighs or springs in the
      engine (not built: no test garment needs it; build it with the first skirt, as leaf joints after the set).
    - THE TORN HANDS (the coordinator: "the most important thing you found"; the user's first complaint was mangled
      fingers). By stage on dg_fix2 (`rig3/stage.py`, sheets `wc_hand_stages_R.png`, `_L.png`): the body's field
      meshed at the export voxel is clean, fingers apart; `retopo.wrap` tears BOTH hands at the webs and the thumb's
      root, at rest, disc or no disc (the wrap sees only the body's prims): the stylised template's digit tubes and
      palm carried onto MakeHuman's close-set fingers ("untangle: 2251 faces still turned after 12 passes" was in
      every export log). Decimation, hidden-face pruning and the bake only inherit it. Fix at the cause: a base body
      ships its OWN quads (`retopo.base_quads`: `base.surface()["quads"]`, MakeHuman's or the template's own
      animation topology, each vertex dropped <= 4 mm onto the field (the cage stands 0.5 mm mean off it), a GNM head
      grafted on as before). `parts.body.topology = "wrap"` now means that on a base; `"template"` = the old carry
      (kit characters, which have no quads of their own, are unchanged). The whole body, before / after: folded edges
      217 -> 33, faces turned against the field 416 -> 12, non-manifold edges 18 -> 0, p99 off the field 2.26 ->
      1.41 mm; clusters at finger1_1.L 88, finger4_1.L 81, finger4_1.R 71, finger1_1.R 66, thumb_1.R 22, knee.L 46
      -> none on the hands (ankle.L / toe.L 9 / 8, under the shoes).
    - So it can't ship silently: `asset.mesh_quality` counts `turned` faces (normal against the field's gradient,
      faces near the surface only) and returns the defects' `spots`; `asset.defect_regions` groups folded edges +
      turned faces by the model's nearest joint (`DEFECT_CLUSTER` 12; spots inside another part don't count: the
      skin behind an eyeball), and the export's quality line says "WARNING ... TORN OR TANGLED at finger1_1.L
      (88), ..." with `quality.defects_by_joint` in the json. Tests: test_tooling `test_mesh_quality`,
      test_handwarp `test_export_topology_is_the_bases_own`. Decimated bodies (wb_dg_talk, no wrap) had clean hands.
    - The ragged shirt hem: the shirt is a SOLID shell with a smooth rounded rim (look build: fine); the export
      dropped its faces "hidden in another part" exactly where it goes under (its inside lies in the body /
      shorts), so the cut ran along the rim, a triangle deep and wavy, and shed shards over a lifted thigh.
      `asset._deep_hidden` (`HIDDEN_RIM` 12 mm): a hidden vertex with a visible vertex of its own part within the
      rim stays, in `prune_hidden` and `topology_parts`; the cut lies inside where nothing looks. Test
      `test_hidden_faces_are_cut_inside_the_rim`.
    - troll_anat's real export (15k / 1024, Khronos 0 / 0; `wc_troll_anat_*`): rest, thigh 60, knee 90 read fine;
      arm 60 drags a pale stretched patch of trapezius skin from the neck to the shoulder; fingers are fused
      (digit bleed 0.27-0.38, a finger joint moves its neighbours 20+ mm; audit 45 of 51 BAD). Body usable, hands not.
    - The golfer shipped with all of it (dg_fix2 30k / 2048, /mnt/data/hifipushie/rig3/exp_golfer, 849 s, Khronos
      0 / 0): body quality line 3 folded edges / 2 turned faces (was 217 / 416), p99 / max off the field 1.13 /
      2.7 mm (2.26 / 16.5); audit 6 BAD of 51 (rig2's export 10; left: arm onto 30 neck-side vertices 18 mm, Spine1
      onto the shirt hem 10 mm, cloth flips); sheets `wc2_golfer_*`, before / after `wc2_hand_before_after.png`
      (hand at rest, maps + clay: clean), `wc2_handroll_hem_before_after.png` (hand roll 105: no cracks; hem at a
      60 deg thigh: a smooth edge, no shards), `wc2_golfer_head_engine.png` (head 33: collar stays; nod: a lump of
      nape skin still stands over the collar's stand, Head-only AND shared with Neck: NOT fixed), Godot
      `wc2_golfer_godot.png`. The collar's line now says "TORN OR TANGLED at neck (24)": its fold (stand + fall)
      reads as folded edges; a look shows nothing torn. A designed fold is a false alarm there.
    - `rig_audit.fused_limbs` also warns when FINGERS are modelled touching (`DIGIT_AIR` 2 mm, past the first
      phalanx): the troll's are (12 mm radii on axes 18 mm apart: 7.5 mm into each other at the first phalanx, 3.5
      at the second), which is its fused mitten: MODEL, not weights. goblin_anat's fingers have 8-14 mm of air and
      still bleed 0.4: that one is weights (distance weights between thin close chains). The troll's pale patch
      from neck to shoulder is in the maps at rest too (clay is smooth at arm 60): paint / bake, not the skin.
    - `base_quads` skips the head graft for body.source "human" (the "onemesh" agent's fused source: its quads
      hold the head already).
    - The nape on a nod, by numbers (`rig3/nape.py`, `napes.py`): the golfer's collar stands to z 1.565, 0.8 cm under
      the hairline and 6 cm under the Head joint; the floor ran level from the jaw (z ~1.57) and the falloff is long
      (head size here is neck joint -> head top = 34 cm, so `HEAD_FALL` is ~15 cm, not 11), so the nape skin inside
      and just over the collar was Head 0.98. A 25 deg nod about the Head joint swung it 16-28 mm back and 40 mm
      up: 38 vertices came out past the collar's back by up to 8.4 mm, and the hair lifted 4.6 cm off it: the lump.
      (Not hidden skin: it is the skin above the collar's top.) `HEAD_OCCIPUT` 0.1: behind the Head joint the floor
      climbs to the skull's base; Head weight there 0.86, nothing past the collar (-2.9 mm; shared with Neck
      -11.5), bare-human folds unchanged. A higher floor or a shorter nape falloff clears more and folds the bare
      nape (nod p99 17-22, max 40-73 deg). The chin still sinks into the collar on a hard Head-only nod.
    - `parts.<p>.folds = true`: folded by design (a turned collar): counts stay in the quality line, no TORN alarm.
      Set on the collar of dg_fix2 and wb_dg_talk.
    - Kit digits, tried and dropped: making digits exclusive in `rig.weights` (a finger's skin never takes another
      finger's bones) turned the goblin's soft bleed (0.40-0.45, 13-17 vertices, 10 mm) into a few vertices wholly
      on the wrong finger (0.89, 19 mm); limited to past the first phalanx it changed nothing. The bleed sits at the
      knuckles: the anatomy's webs / pads and the first phalanges are handed to ONE finger's rig bone by their
      middle (`rig_weights`), so a neighbour's side skin reads that bone. Next try: webs and pads to the Hand bone,
      then exclusivity.
    - Goblin proof of the guide's rule: `wc2_goblin_fused_vs_clear_arm60.png` (examples/goblin_talk.json exported
      as it is: a torn jagged web under the raised arm; the same with goblin_anat's elbow / wrist + anatomy {}:
      clean). Both Khronos 0 / 0; models `workspace/wc_goblin_talk`, `wc_goblin_talk_clear`.
    - HANDOVER (rig3, 2026-10-06, context full). Exports in /mnt/data/hifipushie/rig3: exp_golfer (final:
      re-exported last with the nape floor + collar folds; check `rig3/queue6.txt` says "golfer3 exit 0" and judge
      `sheets.py dg_fix2 <glb> wc3_golfer nod nod_shared head33` for the nape), exp_talk (wb_dg_talk, decimated
      body + face shapes, final falloff of round 3 before the nape floor: `wc2_talk_strip.png`), exp_talk_wrap
      (`workspace/wc_dg_talk_wrap` = wb_dg_talk + parts.body.topology "wrap": FACE SHAPES ON THE BASE'S OWN QUADS,
      the case s0urc3's Garrett needs; if this note still says so it was NOT judged: log `rig3/exp_talk_wrap.txt`,
      then blink / jawOpen / smile / jaw_head33 sheets; expected trouble: the GNM head's fixed quads carry no mouth
      interior (bag, teeth, tongue are their own parts or missing), the lips' slit isn't re-meshed, `Face.seal`
      and the carry assume a decimated mesh), exp_troll_anat, exp_wc_goblin_talk(_clear). Open, in order: (1) that
      face-shape check; (2) kit digit weights (above); (3) the chin into the collar on a nod, the 9 neck-side
      vertices rigid_near's 8 cm band gives wholly to Head under the collar (talk export: Head leak 69 mm on 9
      vertices); (4) hem bones with the first skirt; (5) a Mixamo clip retargeted in Godot; (6) 15k smile corners;
      (7) the troll's fingers want re-modelling (the tool warns), its pale patch is card cmux1btxc000pk9f23weo12lj.
    - A real engine: `spikes/godot_rig/` (check.gd, sheet.py): Godot 4.7 loads the GLB with its own importer at run
      time, poses the Skeleton3D, drives the twist joints from `<name>.json` `rig.twist` by the recipe, sets face
      shapes, writes PNGs. `godot --path spikes/godot_rig -s check.gd -- x.glb x.json <prefix> poses.json` (opens a
      window for a few seconds). All 79 joints found (colon -> underscore), skin, maps, twist driving and shapes
      work as exported; nothing needed changing. Not checked: a Mixamo clip retargeted, Unity, Unreal.
    - 15k smile (`wc_gnm15k_smile_distances.png`): fine at full-figure distance, the corners kink from a bust
      shot inward; 36k (`wc_talk_smile.png`) is fine. Blink at 36k: closed, a clean line.
  - Regen round (2026-10-07, "regen" agent, branch `worktree-agent-a9a6d594238eb9139`; s0urc3 hand-patched every
    export of Garrett with keep_weights.py + fix_blink.py; renders `rig_renders/rg_*`; export
    /mnt/data/hifipushie/regen/exp_garrett; model `workspace/rg_garrett` = garrett_v20's spec with skin.only ["eyes"];
    scratch DURABLE in /mnt/data/hifipushie/regen/: run.sh <script> (worktree code, main workspace), seatlib.py
    (`game_pose`: s0urc3's seated_pose.json on a GLB's bones; clay rows coloured by part), rs.py + r.sh / g.sh
    (re-skin a GLB's meshes with the code as it is, audit, layers, sheet; RS_SMOOTH / RS_TWO = the old behaviour),
    proof.py (rows of (GLB, weights) with the SAME cameras), blink.py (Garrett's blink on v23's body mesh: under-eye
    measure, rays reaching the eyeball), blinksheet.py, final.py, chk.py / chk2.py / chk3.py (export vs v23), tests.sh).
    - Clothes seated: the cards' diagnosis (lookups alternating thigh / pelvis) was wrong, and so were a kernel
      lookup and a harmonic solve I tried first. Per part NOTHING was wrong (weight steps, stretch, folds read the
      same as the good export). The fault was BETWEEN parts: `WORN_SMOOTH` smoothed each garment over its OWN mesh, so
      two layers 2 mm apart drift (a jacket's hem toward the pelvis above it, the trousers on down the thigh); at 90
      deg of hip the jacket sinks into the trousers where it has less thigh, and the line where two coarse meshes
      cross is the sawtooth. Now `WORN_SMOOTH` 0 (`parts.<p>.rig_smooth` still there) and cloth reads the skin from
      both its faces (`rig_template.from_surface(two_sided=)`, `rig.TWO_SIDED`: what the smoothing papered over on
      collars). `parts.<p>.rig_weights` "surface" | "around" (`rig_template.around_surface`, a kernel average: worse
      for layers, each layer's kernel differs; kept for loose single garments) | "distance".
    - `rig_audit.layers` + `seated` + `layers_text`: vertices of one part lying on another at rest and > 3 mm under
      the same spot posed, per pair, with where; over `LAYER_BAD` 12 is BAD. In the rig tool's text (always, seated),
      `rig(pose="seated")`, the export log (WARNING) and json `rig.layers_seated`. Garrett seated, v23's meshes: old
      code jacket through trousers 18 (20 mm), new 0; weights audit 15 BAD -> 6 (the smoothing was also the leak at
      knees / elbows / feet). Golfer re-skinned: 7 -> 7 BAD, arm leak 18 -> 14 mm, thigh flips 41 / 30 -> 27 / 24.
    - Blink: on a 20k low poly most of the seal's 14 bins hold no margin vertex, so a bin's "highest lower-lid
      vertex" was a cheek vertex 13 mm under the eye, lifted to the lid line. `GnmFace._lid_edge` finds margins by
      their lid's posed envelope (`LID_EDGE`), `_lid_share` fades the correction by distance from the margin
      (`LID_REACH` 9 / 4 mm). `spec.face_shapes.lid_seal` false | amount | {amount, over, band, reach}.
      `faceshapes.unevenness` (a vertex's move outside its edge neighbours' range, per m of edge; tears and the
      blink's own margins left out) in the export log, WARNING over 0.2 for non-mouth shapes (the kit's mouth shapes
      read 0.2-1.6 at the slit's ends by design); json `parts.<p>.face_shape_unevenness`. A gradient or Laplacian
      measure does not separate the fault (a closing lid is steep). s0urc3's under-eye measure on the fresh
      export: 0.18 / 0.25 and 0.16 / 0.26 (faulty 0.41 / 0.73, their repair 0.15 / 0.20).
    - `skin.only` = [groups] (eyes, eye_rims, zones, lips, roughness, micro, features, shading); without "shading"
      `skin.part_base` is None, `_pre` is stripped (ordinary layers) and the part's shading is untouched.
    - Posing with s0urc3's seated_pose.json: twist joints REST ROTATED (+Y along the segment): take the rest
      rotation out of model quats, or thighs collapse to planks (cost me an hour of wrong diagnosis).
    - Found on the way, NOT fixed (main's state, not these cards): (1) a fresh export's meshes are no longer vertex
      for vertex v23's (hidden-face pruning changed since: `_deep_hidden`), so s0urc3's patches could not even be
      applied to it; (2) rig3's long head falloff makes Garrett's neck skin Head 0.70 on average 12-16 cm under the
      Head joint (v23: 0.16), out to |x| 12 cm: in the game's idle and at head 33 the audit reads "body through
      jacket_trim 52-73, body through shirt 40" (v23: 0), and Head 33 leaks 72 mm onto 300 shoulder-owned vertices;
      in clay it is modest (skin at the neckline); (3) this export's low poly has "TORN OR TANGLED at eye_front.L
      (12)": the left upper lid is a few big triangles with a hard vertical edge, a dark crease up the lid in every
      blink (v23's lid is smoother); the right eye has a small dark notch at the outer corner in a full blink.
  - Regen round 2 (2026-10-07, "regen2" then "regen3" agents, branch `regen3`; goal: a plain export of Garrett that
    is a drop-in for the game's hand-patched v23; export /mnt/data/hifipushie/regen/exp_garrett2; renders
    `rig_renders/rg3_*`; scratch DURABLE in /mnt/data/hifipushie/regen2/ and regen3/: run.sh <script> (worktree
    code, main workspace), rsq.py model glb tag (re-skin an export's meshes as the export does, Head / Neck audit,
    layers head33 / nod / game, neck fold numbers; COV_SMOOTH=0 NEAR_FIELD=0 = the old rules), fl.py (which
    triangles flip when a joint turns, with their Head weights), lk.py / mv.py / hf.py (Head weight, face-shape
    move and head field along the throat), au.py (audit + layers of any GLB), proof.py (same-camera rows, poses
    game / seated / head33 / nod / arm60), blinksheet.py out.png 'label|glb' ..., contract.py ref new (joint names
    in order, targets, rigid parts), rename.py (rg_garrett_* -> garrett_* names, for s0urc3's fix_blink.py
    --report, which looks for garrett_body), exp.py (the recipe's export), cmp.sh (old vs new on Garrett and
    wb_dg_talk)).
    - regen2: `flipfit.py` (after decimation an edge whose two triangles meet sharply and misfit the dense mesh is
      turned when both then fit: the dark crease up the left upper lid in blinks was a 14 mm edge across the lid
      fold); the lid seal's 0.3 mm overlap fades toward the eye corners (`LID_FADE`); the quality line leaves the
      mouth bag's folds out of the TORN alarm (`Face.inside_mouth`) and names clusters by the nearest landmark;
      `rig.skin_cover`: skin a worn part covers (a ray out along the normal meets it within 3 cm) takes no head rule
      (Garrett's neck skin under the collar was Head 0.70: through the jacket's collar in the idle and at head 33).
    - regen3: that cover share was a per-vertex ray test, so at the collar's top edge (nape, throat sides) on the
      20k low poly it stepped 0 -> 1 inside one triangle, plus single grazing-ray vertices: 38 triangles inside out
      at a 33 deg head turn, each with a Head ~0 and a Head ~1 corner. Now smoothed `COVER_SMOOTH` 4 rounds over
      the welded mesh: 38 -> 2 (v23 12). And the open collar's throat notch was Head 0.80 (v23 0.16, the field 0.38):
      `rigid_near`'s 8 cm band reached down from the throat skin jawOpen moves 3 mm+ (to the Adam's apple), and it
      blended Head over the head rule's own share (0.38 twice = 0.62). On base bodies (`field=` the head field)
      past `NEAR_SHORT` 0.375 of the band the share is no more than the field's, and h is the share wanted: notch
      0.37, a head turn drags it 11 mm instead of 25. Re-skinned previous meshes: head33 collar through body 13 ->
      1 (v23 8), nod 13 -> 2 (v23 109), neck fold p99 head33 121 -> 22 deg, nod 100 -> 48; wb_dg_talk Head flipped
      41 -> 16, head33 collar through body 79 -> 5. Kit characters unchanged (no field passed).
    - regen2's skin_cover result was named `cover` in `_export`, which already held the atlas coverage: KeyError at
      the json (the first export crashed at 552 s); now `skin_cov`.
    - PROOF (plain export, no patches): /mnt/data/hifipushie/regen/exp_garrett2 (recipe 20000 / 2048 / 320, rig, fbx,
      face shapes; Khronos 0 / 0 / 0; 79 joints same order as v23, 14 twist, 53 ARKit targets on body / eyes / teeth /
      tongue, eyes / teeth / tongue Head 1.0). Body quality: no TORN alarm (19 folded edges, 21 turned faces inside
      the mouth). Audit 5 BAD of 51 (v23 9): Head flipped 2 (v23 12), Head leak 20 mm on 21 shoulder vertices (v23
      13 mm / 7). Layers: game idle 0 BAD (previous export: body through jacket_trim 52, BAD); head33 collar through
      body 2 / 6.4 mm (v23 8 / 23.8); nod 2 + 1 (v23 109 + 122, BAD). fix_blink --report: 0.18 / 0.25, 0.16 / 0.26
      (v23 0.15 / 0.20, 0.16 / 0.27). Sheets `rig_renders/rg3_game.png`, `rg3_head33.png`, `rg3_nod.png` (v23 |
      previous | new, same cameras / part colours), `rg3_blink_closeup.png` (+ `rg3_blink_left_front_crop.png`): the
      vertical crease up the left upper lid is gone; a faint lighter facet wedge on the outer upper lid remains. Second
      character wb_dg_talk re-exported (36k, /mnt/data/hifipushie/regen3/exp_talk, Khronos 0 / 0): audit 14 -> 9 BAD
      (Head no longer BAD), nod collar through body 113 -> 22, body through collar 59 -> 0; blink `rg3_talk_blink.png`:
      the left eye's inner corner shows a white sliver of eyeball in a full blink, there before (smaller), a little
      larger now (LID_FADE's corner fade is the suspect; not isolated). "69 / 58 moved vertices not Head 1.00" in the
      export log is old (69 in the first regen export).
  - Regen round 4 (2026-10-08, "regen4" agent; s0urc3 tested exp_garrett2 in their game: 260/261 tests, idle hands
    over the lap, a lash smear on the closed left lid). Scratch DURABLE in /mnt/data/hifipushie/regen4/: a COPY of
    s0urc3's project (`s0urc3/`, never write in /home/joe/dev/s0urc3) with two scratch-only additions
    (tools/dump_pose.gd: posed body / trousers / bone bases per frame of a baked clip; a FIT print line in
    test_garrett.gd); game.sh <glb> <tag> (rename rg_garrett -> garrett, swap in, delete the old import AND the
    extracted garrett_<n>.png (else the old textures land on the new UVs), import, bake + review with a window,
    dump, test_garrett -> game_<tag>/); twist_bones.gd.fix + motion_retarget.gd.fix = a PROOF patch of their
    retarget (drive the twist bones before the fit and the bake; copy over the .orig to undo); lap.py / lapmap.py /
    lapv.py / gskin.py (their posed lap in Python, exact to their skinning; per-joint attribution), jgap.py /
    palm.py (which joint set the resting hand's height, palm tilt), wmod.py / wcopy.py (weight experiments on a
    GLB), notex.py / settarget.py / blinkvar.py / blinkL*.py (lid: texture off, normal map off, blink variants
    rendered), darkface.py / darktri.py / tuck.py, exp.py (the recipe export, asset_name "garrett").
    - REPRODUCED their numbers exactly in the copy (v23: 18/18, idle hand_thigh L 0.9 / R 8.4 mm, bake 100% / 100%
      on, lowest 0.5 cm; exp2: 17/18, R 14.3 mm, bake left 0% on, lowest 1.3 cm).
    - Hands, by measure: (1) their retarget (MotionRetarget: _leg_ik / _arm_offset / the SeatFit corrector set chain
      bones' GLOBAL rotations) leaves bones not in the clip (our twist joints) where they were: in the baked clip
      LeftUpLegTwist1 is turned 3.6 deg about a SIDEWAYS axis (a flexion; TwistBones would turn it 23.6 deg about the
      thigh). SeatFit, GarrettFit and the bake review all read that raw pose (no TwistBones), so on exp2 they see the
      lap 6.5 mm higher at the hip end than the game draws it. v23 can't show it: its clothes kept v18's weights
      (no twist joints). (2) GarrettFit's thigh table takes trouser vertices >= 0.5 on UpLeg alone: our trousers
      share the thigh with UpLegTwist1, so the table is sparse (merging the twist onto UpLeg offline: test passes,
      L 7.4 / R 2.5 mm). (3) SeatFit lays the palm flat on the lap normal averaged over 5 cm and lifts it until no
      fingertip joint is within 14 mm: v23's own trouser weights copied onto our trousers (lap within +-2 mm of
      v23's) still leave the left hand 13.6 mm up (palm 7 deg off v23's). With their retarget patched (proof): R 8.1
      / L 12.1 mm (fails by 0.1), bake still 1.2-1.4 cm. Nothing on the export side moves these past their
      thresholds without dropping thigh twist from the clothes; visually (rig_renders/rg4_hands_idle.png) the
      hands rest on the lap in all three.
    - Lid smear: texture only (a GLB with the base colour texture removed closes on a clean line; normal map off,
      seal off, seal without overlap, and a "tuck" of the lid's on-ball skin all keep it: rg4_lidL_isolate.png,
      rg4_lidL_seal.png, rg4_tuck.png). It is the model's own paint 162_lash_line (near the eyeballs within 2.4 mm)
      baked thick at the inner end of the upper lid; v23 has it too, smaller, at blink 0.75. Not fixed.
    - `export_asset(asset_name=)` (server + asset._export): files, nodes, meshes, materials, skin named for the game
      ("garrett": garrett_body, garrett_0_material, garrett_rig). /mnt/data/hifipushie/regen4/exp_garrett3 =
      exp_garrett2 vertex for vertex and weight for weight, named garrett (Khronos 0 / 0 / 0).
    - The tongue's own material in v23 came from the old `skin.part: "tongue"` hack (v20's spec); with skin.only
      ["eyes"] the tongue is on the shared material, as intended. Head falloff 84 mm (v23 32): rig3's deliberate
      neck gradient; `spec.rig.rigid_head.fall: 0.032` gives v23's back (at the cost rig3 measured in neck folds).
  - `rig` tool: `glb=` judges an exported GLB (its mesh, joints, weights), `pose={}` = rest, `focus` / `zoom` /
    `views`, `shapes`; warns when the look's voxel is too big for the fingers; prints the audit.
    `tests/test_rig_audit.py`.

