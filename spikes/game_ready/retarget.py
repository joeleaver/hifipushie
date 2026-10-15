"""retarget.py <godot project dir> <file.glb>=<skeleton node path> ...: set up Godot's OWN humanoid retargeting (import-time
BoneMap onto SkeletonProfileHumanoid + the rest fixer: apply node transforms, normalize position tracks, overwrite axis,
fix silhouette) for Mixamo-named GLBs (ours and any Mixamo clip source), so a clip made on one plays on the other
through the shared "%GeneralSkeleton:<profile bone>" tracks. Writes bonemap_mixamo.tres and each GLB's .import
_subresources (run `godot --import` after; the .import files exist after a first import).

This is the engine's standard path (what a game team does), instead of a hand retarget by bone name: the rest fixer
brings both skeletons to the profile's T-pose rest with the profile's bone axes, so an A-pose rig and a T-pose clip
agree (bone rolls included); unmapped bones (our twist joints) keep their names and are driven by our recipe."""
import re
import sys
from pathlib import Path

SIDES = {"Left": "Left", "Right": "Right"}
MAP = {"Hips": "Hips", "Spine": "Spine", "Chest": "Spine1", "UpperChest": "Spine2", "Neck": "Neck", "Head": "Head"}
for s in SIDES:
    MAP.update({f"{s}Shoulder": f"{s}Shoulder", f"{s}UpperArm": f"{s}Arm", f"{s}LowerArm": f"{s}ForeArm",
                f"{s}Hand": f"{s}Hand", f"{s}UpperLeg": f"{s}UpLeg", f"{s}LowerLeg": f"{s}Leg", f"{s}Foot": f"{s}Foot",
                f"{s}Toes": f"{s}ToeBase"})
    MAP.update({f"{s}ThumbMetacarpal": f"{s}HandThumb1", f"{s}ThumbProximal": f"{s}HandThumb2",
                f"{s}ThumbDistal": f"{s}HandThumb3"})
    for prof, mix in (("Index", "Index"), ("Middle", "Middle"), ("Ring", "Ring"), ("Little", "Pinky")):
        for k, ph in enumerate(("Proximal", "Intermediate", "Distal"), 1):
            MAP[f"{s}{prof}{ph}"] = f"{s}Hand{mix}{k}"

OPTS = {"retarget/bone_renamer/rename_bones": "true", "retarget/bone_renamer/unique_node/make_unique": "true",
        "retarget/bone_renamer/unique_node/skeleton_name": '"GeneralSkeleton"',
        "retarget/rest_fixer/apply_node_transforms": "true", "retarget/rest_fixer/normalize_position_tracks": "true",
        "retarget/rest_fixer/reset_all_bone_poses_after_import": "true", "retarget/rest_fixer/overwrite_axis": "true",
        "retarget/rest_fixer/fix_silhouette/enable": "true", "retarget/rest_fixer/fix_silhouette/threshold": "15.0",
        "retarget/remove_tracks/unmapped_bones": "false"}


def bonemap(path: Path) -> None:
    lines = ['[gd_resource type="BoneMap" load_steps=2 format=3]', "",
             '[sub_resource type="SkeletonProfileHumanoid" id="prof"]', "", "[resource]",
             'profile = SubResource("prof")']
    lines += [f'bone_map/{k} = &"mixamorig_{v}"' for k, v in MAP.items()]
    path.write_text("\n".join(lines) + "\n")


def patch_import(imp: Path, skel: str) -> None:
    s = imp.read_text()
    node = ", ".join([f'"retarget/bone_map": Resource("res://bonemap_mixamo.tres")'] + [f'"{k}": {v}' for k, v in OPTS.items()])
    sub = '_subresources={\n"nodes": {\n"PATH:%s": {\n%s\n}\n}\n}' % (skel, node)
    s = re.sub(r"_subresources=\{.*?\}\n(?=gltf/)", sub + "\n", s, flags=re.S)
    imp.write_text(s)


if __name__ == "__main__":
    proj = Path(sys.argv[1])
    bonemap(proj / "bonemap_mixamo.tres")
    for a in sys.argv[2:]:
        f, skel = a.split("=", 1)
        patch_import(proj / (f + ".import"), skel)
        print("patched", f, skel)
