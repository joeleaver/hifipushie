"""Artist retopo, step 4 (Blender): rig (Mixamo names), weight, LOD1 weights, export (the ROM is its own step:
blender_artretopo_posecheck.py loads rigged.blend).
    blender -b --factory-startup --python blender_artretopo_rig.py -- job.json
job: dir, joints ({name: [x, y, z]}, the LEFT side (+x) for paired joints; see JOINTS; "fingers": {name: [4 points
from the knuckle to the tip]} adds Left/RightHand<name>1..3 chains: a hand's fingers, a wing tip's feathers),
helpers (joints that get a half-angle bend helper: default Arm, ForeArm, Leg = shoulder, elbow, knee), clavicle (the share of an arm's lift past
60 deg the clavicle takes: 0.3), helper_smooth, jaw_smooth, (nothing else).
Reads final.glb (else low_uv.glb), low.ply + low_groups.json (the jaw), props.json (which bone holds each prop).
Writes rigged.glb, rigged.blend, rig.json (bones, helpers, joints, object names, weighting numbers).

Weighting, in order (each step a lesson, guide(topic="retopo") "Rig"):
1. import with merge_vertices=True (glTF splits vertices at UV seams; bone heat then tears the seams in pose)
2. Blender bone heat (automatic weights). No global smoothing and no limb fade: both made the ROM worse.
3. half-angle helpers on shoulder, elbow, knee (a _bend bone turned half as far as its joint takes the joint's
   share of the vertices weighted to both sides): stretches gone at the knee and shoulder. NO hip helper (5x
   stretches). The hand-over is Laplacian-smoothed `helper_smooth` times.
4. the jaw: the cage's own jaw group replaces bone heat's guess (bone heat makes a group named after the Jaw bone:
   reuse it; a second "...Jaw.001" group is never driven); the mouth inside is the head's (and jaw's) only; the
   border smoothed `jaw_smooth` times.
5. any vertex left with no weight copies its nearest weighted neighbour.
Props parent rigidly to a bone: eyes to Head, a prop held in the teeth to Jaw (props.json "bone")."""
import json
import os
import sys

import bpy
import bmesh
from mathutils import Vector
from mathutils.kdtree import KDTree

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import blender_artretopo_common as C  # noqa: E402

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

# ---- 3. half-angle helpers
ALLH = {"Arm": "Shoulder", "ForeArm": "Arm", "UpLeg": None, "Leg": "UpLeg"}
HELP = {j: ALLH[j] for j in J.get("helpers", ["Arm", "ForeArm", "Leg"]) if j in ALLH}
kids = {}
for n, par, *_ in BONES:
    kids.setdefault(par, []).append(n)


def subtree(n):
    out = [n]
    for k in kids.get(n, []):
        out += subtree(k)
    return out


if HELP:
    bpy.context.view_layer.objects.active = rig; bpy.ops.object.mode_set(mode="EDIT")
    for side in ("Left", "Right"):
        for j, par in HELP.items():
            jb = arm_d.edit_bones[PFX + side + j]
            h = arm_d.edit_bones.new(PFX + side + j + "_bend"); h.head = jb.head; h.tail = jb.head + (jb.tail - jb.head) * 0.3
            h.parent = arm_d.edit_bones[PFX + (side + par if par else "Hips")]; h.roll = jb.roll
    bpy.ops.object.mode_set(mode="OBJECT")
    for side in ("Left", "Right"):
        for j in HELP:
            sub = {PFX + x for x in subtree(side + j)}
            hg = VG.new(name=PFX + side + j + "_bend")
            for v in body.data.vertices:
                ws = {VG[g.group].name: g.weight for g in v.groups}
                a_ = sum(w for n, w in ws.items() if n in sub)
                b_ = sum(w for n, w in ws.items() if n not in sub and not n.endswith("_bend"))
                hgt = 2 * min(a_, b_)
                if hgt <= 1e-4:
                    continue
                sa = (a_ - hgt / 2) / a_ if a_ > 0 else 0; sb = (b_ - hgt / 2) / b_ if b_ > 0 else 0
                for n, w in ws.items():
                    if not n.endswith("_bend"):
                        VG[n].add([v.index], w * (sa if n in sub else sb), "REPLACE")
                hg.add([v.index], hgt, "REPLACE")
    bm_ = bmesh.new(); bm_.from_mesh(body.data); bm_.verts.ensure_lookup_table()
    nb = [[e.other_vert(v).index for e in v.link_edges] for v in bm_.verts]; bm_.free()
    for side in ("Left", "Right"):
        for j, par in HELP.items():
            names = [PFX + side + j + "_bend", PFX + side + j, PFX + (side + par if par else "Hips")]
            W = {n: [0.0] * len(body.data.vertices) for n in names}
            for v in body.data.vertices:
                for g in v.groups:
                    n = VG[g.group].name
                    if n in W:
                        W[n][v.index] = g.weight
            zone = [i for i in range(len(nb)) if any(W[n][i] > 0 for n in names)]
            tot = [sum(W[n][i] for n in names) for i in range(len(nb))]
            for _ in range(J.get("helper_smooth", 6)):
                for n in names:
                    w = W[n]; W[n] = w[:]
                    for i in zone:
                        W[n][i] = 0.5 * w[i] + 0.5 * sum(w[k] for k in nb[i]) / len(nb[i])
            for i in zone:
                ssum = sum(W[n][i] for n in names) or 1
                for n in names:
                    val = W[n][i] / ssum * tot[i]
                    if val > 1e-4:
                        VG[n].add([i], val, "REPLACE")
                    else:
                        VG[n].remove([i])

# ---- 4. the jaw
njaw = 0
if "jaw" in JT and os.path.exists(f"{D}/low_groups.json"):
    G = json.load(open(f"{D}/low_groups.json")); jaw = G.get("jaw"); inside = G.get("mouth_inside")
    ref = C.load_ply(f"{D}/low.ply", "ref")
    kd = KDTree(len(ref.data.vertices))
    for v in ref.data.vertices:
        kd.insert(v.co, v.index)
    kd.balance()
    gj = VG.get(PFX + "Jaw") or VG.new(name=PFX + "Jaw"); gh = VG[PFX + "Head"]
    for v in body.data.vertices:
        ix = kd.find(body.matrix_world @ v.co)[1]; w = jaw[ix] if jaw else 0.0
        if inside and inside[ix] > 1e-3:      # the inside of the mouth is the head's (and the jaw's) only
            for g in list(v.groups):
                if g.group != gh.index:
                    VG[g.group].remove([v.index])
            gh.add([v.index], 1.0, "REPLACE")
        others = [g for g in v.groups if g.group != gj.index]
        tot = sum(g.weight for g in others) or 1.0
        for g in others:
            g.weight = g.weight / tot * (1 - w)
        if w > 1e-3:
            gj.add([v.index], w, "REPLACE"); njaw += 1
        else:
            gj.remove([v.index])
    bpy.data.objects.remove(ref)
    if J.get("jaw_smooth", 4):
        C.select_only(body); VG.active_index = gj.index
        bpy.ops.object.mode_set(mode="WEIGHT_PAINT")
        bpy.ops.object.vertex_group_smooth(group_select_mode="ACTIVE", factor=0.5, repeat=J.get("jaw_smooth", 4))
        bpy.ops.object.vertex_group_normalize_all(lock_active=True)
        bpy.ops.object.mode_set(mode="OBJECT")

# ---- 5. empty vertices copy their nearest weighted neighbour
wsum = {v.index: sum(g.weight for g in v.groups) for v in body.data.vertices}
empty = [i for i, w in wsum.items() if w < 1e-3]
if empty and len(empty) < len(wsum):
    kd2 = KDTree(len(wsum) - len(empty))
    for v in body.data.vertices:
        if wsum[v.index] >= 1e-3:
            kd2.insert(v.co, v.index)
    kd2.balance()
    for i in empty:
        src = body.data.vertices[kd2.find(body.data.vertices[i].co)[1]]
        for g in src.groups:
            VG[g.group].add([i], g.weight, "REPLACE")
for o in props:
    base = o.name.split(".")[0]
    bone = HOLD.get(base, "Head") if not base.startswith("eye") else "Head"
    if bone == "Jaw" and "jaw" not in JT:
        bone = "Head"
    mw = o.matrix_world.copy(); o.parent = rig; o.parent_type = "BONE"; o.parent_bone = PFX + bone
    bpy.context.view_layer.update(); o.matrix_world = mw
info = {"source": os.path.basename(SRC), "bones": len(arm_d.bones), "helpers": list(HELP), "jaw_verts": njaw,
        "empty_filled": len(empty), "props": {o.name: o.parent_bone for o in props}, "groups": len(VG)}
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
