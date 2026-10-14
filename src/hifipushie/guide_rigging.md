# Rigging characters

Read guide(topic="") (the playbook) first: describe the reference, then work big to small.

### Rigging characters

The skeleton you model with is not the rig. Tusks, lip chains and a shorts leg are modelling bones. The export rig
is a separate, standard skeleton, and the `rig` tool fits it and skins the model:
- **Humanoids** (pelvis, chest, neck, head, shoulder/elbow/wrist, hip/knee/ankle .L/.R) get Mixamo's skeleton and
  names, with fingers from the hand kit. Mixamo animations, Unity Humanoid and Unreal's IK retargeter map it as is.
  Keep those joint names on anything humanoid.
- **Other creatures:** give `spec["rig"] = {"type": "chains", "root": "pelvis", "chains": {"spine": {"joints":
  [...]}, "tail": {"from": "spine", "joints": [...]}, "leg_front.L": {...}}}`: clean named chains.
- **Check the pose.** Run `rig` and look at its test pose (elbow, shoulder, hip, knee, spine, head, a hand rolled
  palm down). Look for tears,
  lumps left behind and creases. Move a rig joint with `spec["rig"]["joints"]` (e.g. the clavicle,
  "LeftShoulder"). Then `export_asset(..., rig=True)`.
- **Twist bones** (humanoids, on by default). What riggers do: a limb's roll is never left to one joint. A hand
  turned palm down is ~75 deg of roll about the forearm (105 in gestures); in a person the radius turns over the
  ulna along the whole forearm and the wrist itself doesn't twist. With one bone per segment the wrist takes it all
  and the skin wrings there (the "candy wrapper"). So the rig adds leaf joints along each segment, after the
  Mixamo set and children of the segment's own joint, as Unreal's mannequin does (`lowerarm_twist_01/02`,
  `upperarm_twist_01/02`, `thigh_twist`, `calf_twist`) and VRM's roll constraint describes:
  - `<Side>ForeArmTwist1..3` and `<Side>LegTwist1` FOLLOW the hand's / foot's roll: share k/n at station k/n,
    1.0 at the wrist (nothing is left to the wrist joint, nothing turns at the elbow);
  - `<Side>ArmTwist1..2` and `<Side>UpLegTwist1` COUNTER their own joint's roll: -1.0 at the shoulder / hip (the
    deltoid stays with the clavicle), easing to 0 at the elbow / knee.
  Numbered away from the body. Nothing animates them, so a Mixamo clip plays as before and, undriven, the skin is
  what it was without them (their weights are the segment's own weight shared out along it). An engine drives
  them: glTF has no constraints, so each joint's `extras.hifipushie_twist` (driver, mode, share, axis) and the
  export json's `rig.twist` / `rig.twist_recipe` (Godot, Unity, Unreal) say how. Counts:
  `spec["rig"]["twist"] = false | n | {"arm": 2, "forearm": 3, "upleg": 1, "leg": 1}` (the default; up to 4).
  More bones = smaller steps: between two stations turned d apart, linear skinning keeps cos^2(d/2) of the
  section's area.
- **The head is rigid.** Skull, face, jaw, teeth, tongue, eyes (and, in an export with face shapes, every vertex a
  shape moves) are weighted 1.0 to Head; the falloff to the neck is on the throat under the jawline, and clavicles
  never reach the face. From the jaw landmarks on a GNM head, from the head's own primitives on a kit character.
  `spec["rig"]["rigid_head"] = false | {"fall": m, "band": m, "under": m, "column": [r0, r1]}`. On a base body the
  head's weight fades down the whole neck (`fall`, ~11 cm, inside the neck's column; ~5 cm on the shoulders beside
  it), as a rigger paints it: a narrow band under the jaw is a hinge (a Head-only turn of 33 deg sheared the throat
  into a shelf). Garments are not part of it: a collar stays on the shoulders and the neck turns inside it. A hard
  Head-only nod still drives the chin into the chest or collar and pushes the nape back against a collar's stand:
  animate a head move as riggers and mocap do, shared between Neck and Head (about 40 / 60).
- **Clothes follow the skin under them.** On a base body every part reads the body's weights at the nearest point
  of its surface (cloth from both its faces: a collar's under side reads the shoulder it lies on). Layers that lie
  on each other (a jacket over trousers, a cuff over a shirt) so get the same weights where they overlap and stay
  in order when posed; that is why a garment's weights are NOT smoothed over its own mesh by default: smoothed,
  each layer drifts its own way (the jacket's hem toward the pelvis, the trousers on down the thigh) and seated
  they cross in a zigzag. `parts.<p>.rig_weights = "surface"` (the default) | `"around"` (an average of the skin
  round the nearest point, wider the farther the cloth hangs from the skin: for a loose cape or skirt worn alone,
  not for layers) | `"distance"` (the part's own distance weights to the rig's bones, whatever the body has).
  A part that only reaches up beside the
  jaw (a collar, a scarf, a strap) is worn on the body: it keeps the neck's weights and does not turn with the
  head; a part that is mostly on the head (a cap, glasses) is all head. `parts.<p>.rig_head = true | false` says
  so outright (a hood that should turn with the head: true); `parts.<p>.rig_bone` binds a prop to one joint, and
  `parts.<p>.rig_attach = "<bound part>"` hands a part over to that prop's joint where it comes within
  `rig_attach_length` (8 cm) of it: a strap's end goes with its bag, the rest of it with the body.
  `parts.<p>.rig_smooth = rounds` (0) evens a garment's weights over its own mesh (a garment worn alone whose
  weights read ragged; never one layer of several: give the layers the same number, or none).
  **Characters sit.** `rig(pose="seated")` (hips and knees at 90) and the audit's `layers` lines: for each pair of
  parts, the vertices of one that lie on the other at rest and are more than 3 mm under it posed. Over 12 is BAD:
  the two parts cross there, and the line where two coarse meshes cross is a sawtooth. The per-joint audit turns a
  thigh 60 deg and doesn't see it.
  `parts.<p>.rig_drop = [joints]` prunes a garment's influences, as a rigger does after a weight transfer: the
  garment never follows those joints, and their weight goes up the chain to the nearest joint it keeps. Shorts that
  end at the knee: `["Leg"]` (the shin bent their hem 17-27 mm; with it the hem stays a tube on the thigh and the
  knee bends inside it). Short sleeves: `["ForeArm"]` on the shirt. A collar: `["Arm"]`. `{joint: share}` moves only
  that share up (`{"UpLeg": 0.5}` on a long shirt or tunic: its hem half with the pelvis). A name without a side
  means both sides; a segment's twist joints go with it. Don't drop what the garment covers: long trousers need
  the shin.
- **Hems.** Shorts, a shirt's hem, a skirt are sheets hanging off the body, and skinning can only bend them with
  the limb under them: past ~45 deg of thigh the crotch of a pair of shorts and a loose hem fold. What game riggers
  do, in order of cost: delete the skin under the garment (the export does: hidden faces are dropped, so nothing
  pokes through), smooth the garment's weights so the hem takes some of the pelvis and of both thighs
  (`rig_smooth` on a long hem worn over nothing, or `rig_drop` shares), and for skirts, coats and anything that must swing, extra bones (a ring of
  short chains from the waist, driven by the thighs or by a spring / cloth solver in the engine: Unity's cloth and
  dynamic-bone components, Unreal's Chaos cloth and its RBAN skirt chains, VRM spring bones). This rig has no hem
  bones: a skirt will follow the thighs and fold between them. Judge with `rig(pose={"LeftUpLeg": [[1, 0, 0],
  -60]}, glb=...)` and keep hems short or close-fitting if the character has to kick.
- **Model limbs clear of the body before rigging.** An arm lying against the belly is one skin with it once
  meshed: raised, it tears a slab out of the torso and trails a web, whatever the weights. `rig`
  prints a WARNING naming the limb and how much of its surface touches other flesh; fix the spec (joints out to an
  A-pose until air shows between limb and body, or thinner flesh there), not the weights. A rigger handed such a
  mesh would send it back, or cut the limb free and re-model the pit; weighting the fused patch to the body only
  hides the tear behind a stretched web.
- **Read the export's quality lines.** Each part's line counts folded edges and faces turned against the surface,
  and says `TORN OR TANGLED at <joint> (n), ...` when they cluster by a joint (a hand torn at the finger webs, a
  tangle in an armpit): look at that place in clay (`rig(glb=..., focus=..., zoom=...)`) before shipping; the json
  has `parts.<p>.quality.defects_by_joint`. A part folded by design (a turned collar, a cuff, pleats) reads the
  same: `parts.<p>.folds = true` keeps its counts and drops the alarm. A character on a base body exports the base's own quads
  (`parts.body.topology = "wrap"`): hands and feet come out as modelled; `"template"` carries the stylised
  template's topology on instead (it tore MakeHuman's hands) and is only for comparison.
- **Check the numbers.** `rig` prints, under the bone list, a twist test per chain (the hand rolled 75 and 105
  deg, the arm 60, foot and thigh 40): the skin's twist by station along the segment, what is left at the joint,
  the largest step, the worst section's area against rest (flagged CANDY WRAPPER under 0.8) and the worst
  triangles; and the head's weights by height with how far each row lags a rigid head turned 33 deg (want Head
  1.00 / 0.0 mm from the jaw up). `pose={"RightHand": ["roll", 105]}` poses a roll yourself ("roll" = about the
  bone's limb); `drive_twist=False` shows what an engine without drivers gets.
- **Limits:** decimated triangles bend less cleanly than modelled edge loops. The rest pose is as modelled (arms
  down); retargeters handle that with their retarget pose. Twist bones fix roll, not bend: a raised shoulder still
  dips and an elbow bent far still creases (linear blend skinning). Sources for the conventions: Unreal's Twist
  Corrective / mannequin skeleton docs (dev.epicgames.com/documentation/unreal-engine/animation-blueprint-twist-
  corrective-in-unreal-engine), Unity's Muscle Definitions (docs.unity3d.com/Manual/MuscleDefinitions.html: twist
  shared between a limb's two joints, no extra bones), VRM's node constraint spec (github.com/vrm-c/vrm-
  specification, VRMC_node_constraint: roll constraint for twist bones), Godot's BoneTwistDisperser3D
  (docs.godotengine.org/en/latest/classes/class_bonetwistdisperser3d.html), Cascadeur's twist-bone notes
  (cascadeur.com/help/rig/advanced_rigging/advanced_rigging_techniques/twist_bones).
