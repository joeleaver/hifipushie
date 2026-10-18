"""The engine-agnostic rig notes beside an exported GLB: <asset>_rig.json (machine-readable: every driven joint and
pose corrective with its driver) and <asset>_rig.md (the same for a person, with one line per engine for wiring it).
What travels in the file (skeleton, weights, morph targets) works in any engine as is; these are the drivers glTF can't
carry (twist and bend helpers, pose correctives). Written by asset.export next to the shading notes."""
from __future__ import annotations

import json
from pathlib import Path

ENGINES = {
    "unreal": "Import the GLB / FBX as a Skeletal Mesh. Twist and bend helpers: a Control Rig (or AnimBP) after the "
              "animation: twist = 'Get Transform' of the driver, swing-twist about the segment axis, 'Set Rotation' x "
              "share; bend = 'Copy Bone' at weight 0.5. Pose correctives: a Pose Driver node per joint (Swing, driven "
              "curves named as the targets) or the Control Rig writing the curves from the formula below.",
    "unity": "Humanoid or Generic avatar from the GLB (glTFast / UniGLTF). Twist: Twist Correction constraint (Animation "
             "Rigging) per twist bone at its share; bend: Multi-Rotation Constraint at 0.5 on the helper. Pose "
             "correctives: a LateUpdate script setting SkinnedMeshRenderer.SetBlendShapeWeight(index of the target, "
             "100 x weight) from the joint's localRotation.",
    "godot": "Import the GLB (Skeleton3D + MeshInstance3D). Twist / bend: a script (or SkeletonModifier3D) after the "
             "AnimationPlayer setting set_bone_pose_rotation of each helper from its driver's pose. Pose correctives: "
             "MeshInstance3D.set_blend_shape_value(find_blend_shape_by_name(target), weight) in the same script.",
}


KNOWN_GAPS = [  # what the weights + correctives don't fix (review rig_r7, 2026-10-14; Tess, a MakeHuman one-mesh body)
    "Inner creases at 90 deg and past (crook of the elbow, back of the knee): the skin folds into a notch instead of "
    "the biceps / calf pressing flat against the other segment (no contact or muscle shape in LBS).",
    "Elbow seen end-on at 90 deg: the forearm's near end reads as a rounded cap.",
    "Wrist at 60 deg: a hinge-like kink at the back of the wrist (no helper or corrective at the wrist).",
    "Arm raised: a small step on top of the shoulder where the deltoid meets the arm, the clavicle / trapezius don't "
    "lift (Mixamo clips don't turn the Shoulder joint), a hard armpit corner; a tight top's side edge follows the arm.",
    "Seated (hip 90 deg): the thigh lifts as a block with a hard groin edge, the buttock stays with the pelvis and the "
    "thigh's underside flattens (no hip corrective: every solved one flattened the buttock).",
]


def write(info: dict, out_dir: Path, aname: str) -> tuple[Path, Path] | None:
    rig = info.get("rig")
    if not rig:
        return None
    data = {"asset": aname, "bones": len(rig.get("bones", [])), "base_bones": rig.get("base_bones"),
            "rest": rig.get("rest"), "twist": rig.get("twist", []), "twist_recipe": rig.get("twist_recipe"),
            "bend": rig.get("bend", []), "bend_recipe": rig.get("bend_recipe"),
            "correctives": rig.get("correctives", []), "corrective_recipe": rig.get("corrective_recipe"),
            "head": rig.get("head"), "engines": ENGINES, "known_gaps": KNOWN_GAPS,
            "axes": "Blender axes (Z up, the character faces -Y); glTF axes = (x, z, -y)"}
    jp = out_dir / f"{aname}_rig.json"
    jp.write_text(json.dumps(data, indent=1))
    L = [f"# {aname}: rig notes", "", f"{data['bones']} joints ({data['base_bones']} Mixamo-named base joints, then "
         "twist and bend helpers). The skeleton, skin weights and morph targets are in the GLB and work in any engine; "
         "the drivers below are what glTF can't carry. Without them the character still deforms, a little worse at "
         "rolled forearms, bent elbows / knees and raised arms.", "", f"Axes: {data['axes']}.", ""]
    if data["twist"]:
        L += ["## Twist joints", "", str(data["twist_recipe"].get("what") if isinstance(data["twist_recipe"], dict)
                                         else data["twist_recipe"]), "", "| joint | driver | share |", "|---|---|---|"]
        L += [f"| {t.get('bone')} | {t.get('driver')} | {t.get('share')} |" for t in data["twist"]] + [""]
    if data["bend"]:
        L += ["## Bend helpers", "", str(data["bend_recipe"]), "", "| helper | parent | driver | share |",
              "|---|---|---|---|"]
        L += [f"| {b['bone']} | {b['parent']} | {b['driver']} | {b['share']} |" for b in data["bend"]] + [""]
    if data["correctives"]:
        L += ["## Pose correctives", "", str(data["corrective_recipe"]), "",
              "| target | joint | axis_rest (Blender) | from | key | to |", "|---|---|---|---|---|---|"]
        L += [f"| {c['target']} | {c['joint']} | {c['axis_rest']} | {c['from_deg']} | {c['key_deg']} | "
              f"{c['to_deg'] if c['to_deg'] is not None else '-'} |" for c in data["correctives"]] + [""]
    L += ["## Known gaps", "", "What the weights and correctives don't fix yet (judged in game-like EEVEE renders):", ""]
    L += [f"- {g}" for g in KNOWN_GAPS] + [""]
    L += ["## Wiring per engine", ""] + [f"- {k.title()}: {v}" for k, v in ENGINES.items()] + [""]
    mp = out_dir / f"{aname}_rig.md"
    mp.write_text("\n".join(L))
    return jp, mp
