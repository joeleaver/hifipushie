"""Artist retopo, step 4 (Blender): rig (Mixamo names), weight, LOD1 weights, export (the ROM is its own step:
blender_artretopo_posecheck.py loads rigged.blend).
    blender -b --factory-startup --python blender_artretopo_rig.py -- job.json
job: dir, joints ({name: [x, y, z]}, the LEFT side (+x) for paired joints; see JOINTS; "fingers": {name: [4 points
from the knuckle to the tip]} adds Left/RightHand<name>1..3 chains: a hand's fingers, a wing tip's feathers),
helpers (joints that get a half-angle bend helper: default Arm, ForeArm, Leg = shoulder, elbow, knee), clavicle (the share of an arm's lift past
60 deg the clavicle takes: 0.3), helper_smooth, jaw_smooth, (nothing else).
Reads final.glb (else low_uv.glb), low.ply + low_groups.json (the jaw), props.json (which bone holds each prop).
Writes rigged.glb, rigged.blend, rig.json (bones, helpers, joints, object names, weighting numbers).

Weighting: import with merge_vertices=True (glTF splits vertices at UV seams; bone heat then tears them), Blender
bone heat, then the passes in blender_artretopo_weights.py (helpers, jaw, fingers, head_only, shoulder midline, neck
ramp, empty, normalise). No global smoothing and no limb fade: both made the ROM worse.
Props parent rigidly to a bone: eyes to Head, a prop held in the teeth to Jaw (props.json "bone")."""
import json
import os
import sys

import bpy
from mathutils import Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import blender_artretopo_common as C  # noqa: E402
import blender_artretopo_weights as W  # noqa: E402

PFX = "mixamorig:"
J = C.job(); D = J["dir"]; JT = J["joints"]
sc = C.reset()
SRC = f"{D}/final.glb" if os.path.exists(f"{D}/final.glb") else f"{D}/low_uv.glb"
bpy.ops.import_scene.gltf(filepath=SRC, merge_vertices=True)
meshes = [o for o in sc.objects if o.type == "MESH"]
body = max(meshes, key=lambda o: len(o.data.vertices)); body.name = "body"
LODS = [o for o in meshes if o.name.startswith("lod")]
props = [o for o in meshes if o is not body and o not in LODS]
PJ = json.load(open(f"{D}/props.json")) if os.path.exists(f"{D}/props.json") else {"eyes": [], "props": []}
HOLD = {it.get("name", f"prop_{k}"): it.get("bone", "Head") for k, it in enumerate(PJ["props"])}
HOLD.update({cp["name"]: cp.get("bone", "Head") for cp in PJ.get("cut_parts", [])})     # parts ride a bone by name

# ---- skeleton: (bone, parent, head joint, tail joint)
BONES = [("Hips", None, "hips", "spine"), ("Spine", "Hips", "spine", "spine1"), ("Spine1", "Spine", "spine1", "spine2"),
         ("Spine2", "Spine1", "spine2", "neck"), ("Neck", "Spine2", "neck", "head"), ("Head", "Neck", "head", "head_top"),
         ("HeadTop_End", "Head", "head_top", "head_top+")]
for side, sg in (("Left", 1), ("Right", -1)):
    S = lambda n, sg=sg: f"{n}.{sg}"
    BONES += [(f"{side}Shoulder", "Spine2", S("clavicle"), S("shoulder")), (f"{side}Arm", f"{side}Shoulder", S("shoulder"), S("elbow")),
              (f"{side}ForeArm", f"{side}Arm", S("elbow"), S("wrist")), (f"{side}Hand", f"{side}ForeArm", S("wrist"), S("hand_end")),
              (f"{side}UpLeg", "Hips", S("hip"), S("knee")), (f"{side}Leg", f"{side}UpLeg", S("knee"), S("ankle")),
              (f"{side}Foot", f"{side}Leg", S("ankle"), S("toe")), (f"{side}ToeBase", f"{side}Foot", S("toe"), S("toe_end"))]
if "jaw" in JT:
    BONES.append(("Jaw", "Head", "jaw", "jaw_tip"))      # an extra leaf bone after the Mixamo set
for fname, pts in (JT.get("fingers") or {}).items():    # Mixamo finger chains (a hand's fingers; feathers at a wing tip)
    for side, sg in (("Left", 1), ("Right", -1)):
        prev = f"{side}Hand"
        for k in range(3):
            JT[f"f_{fname}_{k}"], JT[f"f_{fname}_{k + 1}"] = pts[k], pts[k + 1]
            bn = f"{side}Hand{fname}{k + 1}"; BONES.append((bn, prev, f"f_{fname}_{k}.{sg}", f"f_{fname}_{k + 1}.{sg}")); prev = bn


def jp(name):
    if name.endswith("+"):
        return jp(name[:-1]) + Vector((0, 0, 0.05))
    if "." in name:
        n, sg = name.split("."); p = Vector(JT[n]); return Vector((p.x * int(sg), p.y, p.z))
    return Vector(JT[name])


arm_d = bpy.data.armatures.new("rig"); rig = bpy.data.objects.new("rig", arm_d); sc.collection.objects.link(rig)
bpy.context.view_layer.objects.active = rig; bpy.ops.object.mode_set(mode="EDIT")
for n, par, h, t in BONES:
    b = arm_d.edit_bones.new(PFX + n); b.head, b.tail = jp(h), jp(t)
    if par:
        b.parent = arm_d.edit_bones[PFX + par]; b.use_connect = (b.parent.tail - b.head).length < 1e-4
for b in arm_d.edit_bones:          # rolls: z forward (-y), so bending forward is about local x for every limb
    b.align_roll(Vector((0, -1, 0)))
bpy.ops.object.mode_set(mode="OBJECT")

# ---- 2. bone heat
C.select_only(body, rig, active=rig)
bpy.ops.object.parent_set(type="ARMATURE_AUTO")
VG = body.vertex_groups

# ---- 3-8: helpers, jaw, fingers, head_only, shoulder midline, neck ramp, empty, normalise (blender_artretopo_weights)
J["joints"] = JT
HELP, winfo = W.run(J, D, body, rig, BONES, PFX)
for o in props:
    base = o.name.split(".")[0]
    bone = HOLD.get(base, "Head") if not base.startswith("eye") else "Head"
    if bone == "Jaw" and "jaw" not in JT:
        bone = "Head"
    mw = o.matrix_world.copy(); o.parent = rig; o.parent_type = "BONE"; o.parent_bone = PFX + bone
    bpy.context.view_layer.update(); o.matrix_world = mw
info = {"source": os.path.basename(SRC), "bones": len(arm_d.bones), **winfo,
        "props": {o.name: o.parent_bone for o in props}, "groups": len(VG)}
print("RIG", json.dumps(info))

# ---- LOD1 weights (nearest face, interpolated; same skeleton), save, export
for lo in LODS:
    C.select_only(lo, body, active=body)
    bpy.ops.object.data_transfer(use_reverse_transfer=False, data_type="VGROUP_WEIGHTS", vert_mapping="POLYINTERP_NEAREST",
                                 layers_select_src="ALL", layers_select_dst="NAME", use_create=True)
    am = lo.modifiers.new("arm", "ARMATURE"); am.object = rig; lo.parent = rig
    info["lod1"] = {"faces": len(lo.data.polygons), "groups": len(lo.vertex_groups)}
json.dump({"bones": BONES, "helpers": HELP, "joints": JT, "prefix": PFX, "body": body.name, "rig": rig.name,
           "lods": [o.name for o in LODS], "props": [o.name for o in props], "info": info},
          open(f"{D}/rig.json", "w"), indent=1)
C.select_only(body, rig, *LODS, *props, active=rig)
bpy.ops.export_scene.gltf(filepath=f"{D}/rigged.glb", use_selection=True, export_format="GLB")
bpy.ops.wm.save_as_mainfile(filepath=f"{D}/rigged.blend")
print("RIGGED")
