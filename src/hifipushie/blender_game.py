"""The ENGINE stage without an engine (docs/notes/gates.md "Engine"): an exported character GLB re-imported into
Blender with the glTF importer's own materials, rendered in EEVEE set up like a game (no ray tracing, alpha-clipped
cards, shadow maps), its face shapes and the blink-multiply map driven as an engine drives them, posed by joint turns
or by a Mixamo-named clip from ANOTHER skeleton retargeted onto ours, optionally beside that skeleton playing the
same clip.

    blender -b --factory-startup --python game_eevee.py -- job.json

job: {"glb", "json" (the export's report), "out" (prefix), "shots": [...], "anim"?: source glb, "beside"?: m,
      "size"?: [w, h]}
shot: {"name", "views": ["front" | "three_quarter" | "side" | "back" | "left"], "focus": Mixamo bone, "lift": m,
       "dist": m, "fov": deg, "w", "h", "turns": {bone: [[x, y, z], deg]} (Blender axes, about the bone's head,
       turned in model space on top of its parent's), "shapes": {ARKit name: w}, "anim": [clip, seconds],
       "beside": true (the source skeleton shown playing the same clip), "hide": [part], "blink_map": bool,
       "hips_drop": m}

RETARGET (a game's humanoid retarget, by Mixamo bone names; our rig rests in an A-pose with unrotated joints, a
Mixamo clip's source in its own T-pose with rolled bone axes): every mapped bone, parents first, gets the world
rotation  D_src(t) . C . R_ours_rest  where D_src(t) = R_src(t) . R_src_rest^-1 is the source bone's world-space change
from ITS rest (independent of its bone axes / rolls) and C swings our bone's rest direction onto the source bone's
rest direction (A-pose onto T-pose: what a rest-pose correction does). Hips move by the source's hip displacement x
(our hip height / its hip height). Twist joints are then driven by the export's recipe: the driver's roll (swing-twist
of its local rotation about the twist joint's segment axis) x share."""
import bpy
import json
import math
import sys
from pathlib import Path
from mathutils import Matrix, Quaternion, Vector

job = json.load(open(sys.argv[sys.argv.index("--") + 1]))
P = "mixamorig:"


def clear():
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob, do_unlink=True)


def import_glb(path, **kw):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=path, **kw)
    new = [o for o in bpy.data.objects if o not in before]
    arm = next((o for o in new if o.type == "ARMATURE"), None)
    return new, arm


clear()
scene = bpy.context.scene
ours, arm = import_glb(job["glb"])
_jp = Path(job.get("json") or str(Path(job["glb"]).with_suffix(".json")))
if not _jp.exists() and Path(job["glb"]).stem.split("_LOD")[0] != Path(job["glb"]).stem:  # a LOD: its asset's report
    _jp = Path(job["glb"]).parent / (Path(job["glb"]).stem.split("_LOD")[0] + ".json")
info = json.load(open(_jp)) if _jp.exists() else {"parts": {}, "glb": job["glb"]}
meshes = [o for o in ours if o.type == "MESH"]

# ---- game-like EEVEE: no ray tracing, shadow maps, a plain world, two suns
scene.render.engine = "BLENDER_EEVEE" if "BLENDER_EEVEE" in [e.identifier for e in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items] else "BLENDER_EEVEE_NEXT"
ee = scene.eevee
for k, v in (("use_raytracing", False), ("use_gtao", True), ("taa_render_samples", 16), ("use_shadows", True)):
    if hasattr(ee, k):
        setattr(ee, k, v)
scene.view_settings.view_transform = job.get("view", "AgX")
scene.world = scene.world or bpy.data.worlds.new("w")
scene.world.use_nodes = True
bg = scene.world.node_tree.nodes.get("Background")
bg.inputs["Color"].default_value = (0.30, 0.32, 0.36, 1)
bg.inputs["Strength"].default_value = 0.8
for k, (d, e, ang) in enumerate((((-1.0, -1.2, 1.4), 3.0, 2.0), ((1.4, -0.6, 0.6), 1.0, 10.0), ((0.3, 1.5, 1.0), 1.5, 3.0))):
    ld = bpy.data.lights.new(f"sun{k}", "SUN")
    ld.energy, ld.angle = e, math.radians(ang)
    lo = bpy.data.objects.new(f"sun{k}", ld)
    lo.rotation_euler = Vector(d).to_track_quat("Z", "Y").to_euler()
    scene.collection.objects.link(lo)
cam_d = bpy.data.cameras.new("cam")
cam_d.clip_start, cam_d.clip_end = 0.01, 200
cam = bpy.data.objects.new("cam", cam_d)
scene.collection.objects.link(cam)
scene.camera = cam

# ---- materials: built FROM the export's shading notes (<asset>_shading.json, shading.py) by default, so the notes are
# tested every export; job "materials": "importer" keeps the glTF importer's own (cards alpha-dithered, blink hooked)
blink_nodes = []
skin_part = (info.get("skin") or {}).get("part", "body")
glb_dir = Path(job["glb"]).parent
sj = Path(job.get("shading") or (glb_dir / (Path(info["glb"]).stem + "_shading.json")))
notes = json.load(open(sj)) if sj.exists() and job.get("materials", "shading") == "shading" else None


def part_of(ob):
    n = ob.name.split(".")[0]
    for pn in sorted(info["parts"], key=len, reverse=True):
        if n.endswith("_" + pn.replace("/", "_")) or n == pn:
            return pn
    if n.endswith("_head"):
        return skin_part
    return None


IMG = {}


def img(fn, space):
    k = (fn, space)
    if k not in IMG:
        im = bpy.data.images.load(str(glb_dir / fn))
        im.colorspace_settings.name = "sRGB" if space == "sRGB" else "Non-Color"
        IMG[k] = im
    return IMG[k]


def tex(nt, m, key, space=None):
    t = nt.nodes.new("ShaderNodeTexImage")
    t.image = img(m["maps"][key]["file"], space or m["maps"][key]["space"])
    return t


def build(m):
    """a Blender material from one shading-notes entry (its formulas, in nodes)."""
    mat = bpy.data.materials.new(m["name"])
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    pb = nt.nodes.new("ShaderNodeBsdfPrincipled")
    nt.links.new(pb.outputs["BSDF"], out.inputs["Surface"])
    bc = tex(nt, m, "basecolor")
    albedo = bc.outputs["Color"]
    if "orm" in m["maps"]:
        o = tex(nt, m, "orm")
        sep = nt.nodes.new("ShaderNodeSeparateColor")
        nt.links.new(o.outputs["Color"], sep.inputs["Color"])
        nt.links.new(sep.outputs["Green"], pb.inputs["Roughness"])
        nt.links.new(sep.outputs["Blue"], pb.inputs["Metallic"])
    if "normal" in m["maps"]:
        nm = tex(nt, m, "normal")
        nmap = nt.nodes.new("ShaderNodeNormalMap")
        nt.links.new(nm.outputs["Color"], nmap.inputs["Color"])
        nt.links.new(nmap.outputs["Normal"], pb.inputs["Normal"])
    pb.inputs["Specular IOR Level"].default_value = 0.5
    kind = m["model"]
    P = m.get("params") or {}
    if kind == "skin":
        if "blink" in m["maps"]:  # albedo = basecolor * lerp(1, blink, 1 - eyeBlink)
            bt = tex(nt, m, "blink")
            mixf = nt.nodes.new("ShaderNodeMix")
            mixf.data_type = "RGBA"
            mixf.inputs["A"].default_value = (1, 1, 1, 1)
            nt.links.new(bt.outputs["Color"], mixf.inputs["B"])
            val = nt.nodes.new("ShaderNodeValue")
            val.name = "eye_open"
            nt.links.new(val.outputs["Value"], mixf.inputs["Factor"])
            mul = nt.nodes.new("ShaderNodeMix")
            mul.data_type, mul.blend_type = "RGBA", "MULTIPLY"
            mul.inputs["Factor"].default_value = 1.0
            nt.links.new(albedo, mul.inputs["A"])
            nt.links.new(mixf.outputs["Result"], mul.inputs["B"])
            albedo = mul.outputs["Result"]
            blink_nodes.append(val)
        ss = P.get("subsurface") or {}
        mfp = ss.get("mean_free_path_m")
        if mfp:
            pb.inputs["Subsurface Weight"].default_value = float(ss.get("weight", 1.0))
            mx = max(mfp)
            pb.inputs["Subsurface Radius"].default_value = [x / mx for x in mfp]
            pb.inputs["Subsurface Scale"].default_value = mx
        sp = P.get("specular") or {}
        if sp.get("coat"):
            pb.inputs["Coat Weight"].default_value = float(sp["coat"])
            pb.inputs["Coat Roughness"].default_value = float(sp.get("coat_roughness", 0.3))
    elif kind == "eye":
        pb.inputs["Coat Weight"].default_value = float(P.get("clearcoat", 1.0))
        pb.inputs["Coat Roughness"].default_value = float(P.get("clearcoat_roughness", 0.03))
    elif kind in ("hair_cards", "lashes"):
        alpha = bc.outputs["Alpha"]
        if kind == "hair_cards":  # albedo * COLOR_0, then the aux shade (root, clump depth, a value per strand)
            va = nt.nodes.new("ShaderNodeVertexColor")
            mul = nt.nodes.new("ShaderNodeMix")
            mul.data_type, mul.blend_type = "RGBA", "MULTIPLY"
            mul.inputs["Factor"].default_value = 1.0
            nt.links.new(albedo, mul.inputs["A"])
            nt.links.new(va.outputs["Color"], mul.inputs["B"])
            albedo = mul.outputs["Result"]
            if "aux" in m["maps"]:
                ax = tex(nt, m, "aux", "linear")
                sepx = nt.nodes.new("ShaderNodeSeparateColor")
                nt.links.new(ax.outputs["Color"], sepx.inputs["Color"])
                f1 = nt.nodes.new("ShaderNodeMath"); f1.operation = "MULTIPLY_ADD"  # 1 - 0.35 r
                f1.inputs[1].default_value, f1.inputs[2].default_value = -0.35, 1.0
                nt.links.new(sepx.outputs["Red"], f1.inputs[0])
                f2 = nt.nodes.new("ShaderNodeMath"); f2.operation = "MULTIPLY_ADD"  # lerp(0.65, 1, b)
                f2.inputs[1].default_value, f2.inputs[2].default_value = 0.35, 0.65
                nt.links.new(sepx.outputs["Blue"], f2.inputs[0])
                f3 = nt.nodes.new("ShaderNodeMath"); f3.operation = "MULTIPLY_ADD"  # 1 + 0.12 (2g - 1)
                f3.inputs[1].default_value, f3.inputs[2].default_value = 0.24, 0.88
                nt.links.new(sepx.outputs["Green"], f3.inputs[0])
                g12 = nt.nodes.new("ShaderNodeMath"); g12.operation = "MULTIPLY"
                nt.links.new(f1.outputs[0], g12.inputs[0]); nt.links.new(f2.outputs[0], g12.inputs[1])
                g = nt.nodes.new("ShaderNodeMath"); g.operation = "MULTIPLY"
                nt.links.new(g12.outputs[0], g.inputs[0]); nt.links.new(f3.outputs[0], g.inputs[1])
                sh = nt.nodes.new("ShaderNodeMix")
                sh.data_type, sh.blend_type = "RGBA", "MULTIPLY"
                sh.inputs["Factor"].default_value = 1.0
                nt.links.new(albedo, sh.inputs["A"])
                nt.links.new(g.outputs[0], sh.inputs["B"])
                albedo = sh.outputs["Result"]
            pb.inputs["Roughness"].default_value = 0.5
            pb.inputs["Specular IOR Level"].default_value = 0.3
        cut = nt.nodes.new("ShaderNodeMath")  # alpha TEST at the cutoff (dithered by EEVEE's AA)
        cut.operation = "GREATER_THAN"
        cut.inputs[1].default_value = float(P.get("alpha_cutoff", 0.33 if kind == "hair_cards" else 0.5))
        nt.links.new(alpha, cut.inputs[0])
        nt.links.new(cut.outputs[0], pb.inputs["Alpha"])
        mat.use_backface_culling = False
        if hasattr(mat, "surface_render_method"):
            mat.surface_render_method = "DITHERED"
    elif kind == "cloth":
        pb.inputs["Sheen Weight"].default_value = 0.25
        mat.use_backface_culling = False
    nt.links.new(albedo, pb.inputs["Base Color"])
    return mat


if notes is not None:
    built = {}
    by_part = {pn: m for m in notes["materials"] for pn in m["parts"]}
    for ob in meshes:
        pn = part_of(ob)
        m = by_part.get(pn)
        if m is None:
            print(f"shading notes: no material for {ob.name} (part {pn}): importer's kept", flush=True)
            continue
        if m["name"] not in built:
            built[m["name"]] = build(m)
        for ms in ob.material_slots:
            ms.material = built[m["name"]]
    print(f"materials from {sj.name}: {sorted(built)}", flush=True)
else:  # the importer's own, cards dithered, the blink map hooked in
    for ob in meshes:
        for ms in ob.material_slots:
            m = ms.material
            if m is not None and hasattr(m, "surface_render_method") and (
                    m.blend_method in ("CLIP", "HASHED") or "hair" in m.name or "lashes" in m.name):
                m.surface_render_method = "DITHERED"

# ---- the clip source
src_arm, src_objs = None, []
if job.get("anim"):
    src_objs, src_arm = import_glb(job["anim"], **({"guess_original_bind_pose": bool(job["src_bind_guess"])} if "src_bind_guess" in job else {}))
    src_roots = [(o, o.location.copy()) for o in src_objs if o.parent is None]


def wm(o, b, posed):
    """world matrix (rotation + head) of bone b of armature o, at rest or as posed."""
    return o.matrix_world @ (o.pose.bones[b].matrix if posed else o.data.bones[b].matrix_local)


def chain_child(b):
    """the child bone that continues b's chain, the SAME name in both skeletons (a hand's direction is to its MIDDLE
    finger: the first child by order was the thumb in one rig and the index in the other, and the hands came out
    rolled and cocked)."""
    common = [c.name for c in arm.data.bones[b].children if "Twist" not in c.name and "_End" not in c.name
              and (src_arm is None or c.name in src_arm.data.bones)]
    if not common:
        return None
    for pref in ("Middle1", "Spine", "Neck", "Head"):  # a hand's middle finger; the trunk's continuation
        hit = [c for c in common if pref in c and not (pref == "Head" and "HeadTop" in c)]
        if hit:
            return hit[0]
    return sorted(common)[0]


def rest_dir(o, b):
    bone = o.data.bones[b]
    h = o.matrix_world @ bone.head_local
    cn = chain_child(b) if o is arm or (src_arm is not None and o is src_arm) else None
    kids = [o.data.bones[cn]] if cn and cn in o.data.bones else [c for c in bone.children if "Twist" not in c.name]
    for c in kids:
        d = o.matrix_world @ c.head_local - h
        if d.length > 1e-6:
            return d.normalized()
    if bone.parent is not None:
        d = h - o.matrix_world @ bone.parent.head_local
        if d.length > 1e-6:
            return d.normalized()
    return Vector((0, 0, 1))


def across(o, b, posed=False):
    """a hand's (or foot's) second axis: index knuckle -> pinky knuckle (world), None if the bones aren't there."""
    side = "Left" if "Left" in b else "Right"
    i, k = P + side + "HandIndex1", P + side + "HandPinky1"
    if not b.endswith("Hand") or i not in o.data.bones or k not in o.data.bones:
        return None
    if posed:
        return (o.matrix_world @ o.pose.bones[k].head - o.matrix_world @ o.pose.bones[i].head).normalized()
    return (o.matrix_world @ o.data.bones[k].head_local - o.matrix_world @ o.data.bones[i].head_local).normalized()


def align(bn):
    """C: our rest bone onto the source's rest bone (swing the direction; for a hand also the roll, by the knuckles)."""
    a, s_ = rest_dir(arm, bn), rest_dir(src_arm, bn)
    C = a.rotation_difference(s_)
    xa, xs = across(arm, bn), across(src_arm, bn)
    if xa is not None and xs is not None:
        u = C @ xa
        u = (u - u.dot(s_) * s_).normalized()
        v = (xs - xs.dot(s_) * s_).normalized()
        ang = math.atan2(u.cross(v).dot(s_), u.dot(v))
        C = Quaternion(s_, ang) @ C
    return C


REST_POSED = ("Shoulder", "Arm", "Hand", "Leg", "Foot", "Toe", "Hips", "Spine")  # limbs (A-pose vs T-pose) and the trunk below the neck (its lean is the clip's); the neck and head keep our posture (aligned, our forward neck tipped the head back)


def rot(M):
    return M.to_3x3().normalized().to_quaternion()


def retarget(frame):
    scene.frame_set(frame)
    bpy.context.view_layer.update()
    if job.get("debug"):
        pb_ = src_arm.pose.bones[P + "LeftUpLeg"]
        print(f"@@dbg frame {frame} action {src_arm.animation_data.action.name if src_arm.animation_data and src_arm.animation_data.action else None} "
              f"src LeftUpLeg quat {tuple(round(x, 3) for x in pb_.rotation_quaternion)} head {tuple(round(x, 3) for x in pb_.head)}", flush=True)
    n = 0
    hips = P + "Hips"
    hip_t = (arm.matrix_world @ arm.data.bones[hips].head_local).z
    hip_s = (src_arm.matrix_world @ src_arm.data.bones[hips].head_local).z
    order = [b.name for b in arm.data.bones]  # parents before children
    Wt = arm.matrix_world
    for bn in order:
        pb = arm.pose.bones[bn]
        pb.rotation_mode = "QUATERNION"
        if bn not in src_arm.pose.bones or "Twist" in bn:
            continue
        D = rot(wm(src_arm, bn, True)) @ rot(wm(src_arm, bn, False)).inverted()
        # the rest-pose correction only where the two rests are DIFFERENT POSES (our A-pose arms vs a T-pose):
        # the trunk's and legs' rest directions are the character's own posture (a forward neck), never swung
        C = align(bn) if any(k in bn for k in REST_POSED) else Quaternion()
        Rw = D @ C @ rot(Wt @ arm.data.bones[bn].matrix_local)
        R_arm = rot(Wt).inverted() @ Rw
        bpy.context.view_layer.update()
        head = pb.matrix.translation.copy()
        if bn == hips:
            d = wm(src_arm, bn, True).translation - wm(src_arm, bn, False).translation
            head = (Wt.inverted() @ (Wt @ arm.data.bones[bn].head_local + d * (hip_t / max(hip_s, 1e-3))))
        pb.matrix = Matrix.LocRotScale(head, R_arm, Vector((1, 1, 1)))
        n += 1
    bpy.context.view_layer.update()
    return n


def pose_dir(o, b):
    """posed world direction of bone b: its head to its first non-twist child's head."""
    pb = o.pose.bones[b]
    h = o.matrix_world @ pb.head
    cn = chain_child(b)
    for c in ([o.pose.bones[cn]] if cn and cn in o.pose.bones else [c for c in pb.children if "Twist" not in c.name]):
        d = o.matrix_world @ c.head - h
        if d.length > 1e-6:
            return d.normalized()
    return None


def direction_errors():
    """per mapped limb / trunk bone: the angle (deg) between our posed bone direction and the source's (a retarget
    with rest correction puts limbs on the source's directions; the trunk keeps our posture's offset, measured
    against the rest offset)."""
    out = {}
    for b in arm.data.bones:
        bn = b.name
        if bn not in src_arm.pose.bones or "Twist" in bn or "_End" in bn:
            continue
        a, s_ = pose_dir(arm, bn), pose_dir(src_arm, bn)
        if a is None or s_ is None:
            continue
        err = math.degrees(a.angle(s_))
        if job.get("debug") and ("UpLeg" in bn or "ForeArm" in bn or bn.endswith(("Hips", "Spine", "Spine2", "Neck"))):
            print(f"@@dbg {bn}: ours {tuple(round(x, 3) for x in a)} src {tuple(round(x, 3) for x in s_)}", flush=True)
        if not any(k in bn for k in REST_POSED):  # trunk: against the rest offset
            err = abs(err - math.degrees(rest_dir(arm, bn).angle(rest_dir(src_arm, bn))))
        out[bn.replace(P, "")] = round(err, 1)
        xa, xs = across(arm, bn, True), across(src_arm, bn, True)
        if xa is not None and xs is not None:
            out[bn.replace(P, "") + ".roll"] = round(math.degrees(xa.angle(xs)), 1)
    h = P + "Hips"
    ra = (arm.matrix_world @ arm.pose.bones[P + "RightUpLeg"].head - arm.matrix_world @ arm.pose.bones[P + "LeftUpLeg"].head)
    rs = (src_arm.matrix_world @ src_arm.pose.bones[P + "RightUpLeg"].head - src_arm.matrix_world @ src_arm.pose.bones[P + "LeftUpLeg"].head)
    ra.z = rs.z = 0
    out["Hips.yaw"] = round(math.degrees(ra.angle(rs)), 1) if ra.length > 1e-6 and rs.length > 1e-6 else 0.0

    def body(o):  # world: trunk lean (hips -> neck from vertical), hips over the lower ankle / leg length, knee bends
        W = o.matrix_world
        pb = o.pose.bones
        hp, nk = W @ pb[P + "Hips"].head, W @ pb[P + "Neck"].head
        lean = math.degrees((nk - hp).angle(Vector((0, 0, 1))))
        legs = [(W @ o.data.bones[P + s + "UpLeg"].head_local - W @ o.data.bones[P + s + "Foot"].head_local).length
                for s in ("Left", "Right")]
        ank = min((W @ pb[P + s + "Foot"].head).z for s in ("Left", "Right"))
        knees = []
        for s in ("Left", "Right"):
            a, k, f = (W @ pb[P + s + n].head for n in ("UpLeg", "Leg", "Foot"))
            knees.append(round(180 - math.degrees((a - k).angle(f - k)), 1))
        return round(lean, 1), round((hp.z - ank) / max(legs), 3), knees
    lo, ls_ = body(arm), body(src_arm)
    out["trunk_lean_deg ours|src"] = f"{lo[0]}|{ls_[0]}"
    out["hips_over_ankle/leg ours|src"] = f"{lo[1]}|{ls_[1]}"
    out["knee_bend_LR ours|src"] = f"{lo[2]}|{ls_[2]}"
    return out


def seg_axis(bone):
    for c in bone.children:
        if "Twist" not in c.name:
            d = c.head_local - bone.head_local
            if d.length > 1e-6:
                return d.normalized()
    return (bone.tail_local - bone.head_local).normalized()


def drive_twist():
    n = 0
    for tw in info.get("rig", {}).get("twist", []):
        b, dname = tw["bone"], tw["driver"]
        if b not in arm.pose.bones or dname not in arm.pose.bones:
            continue
        tb = arm.data.bones[b]
        seg = seg_axis(tb.parent)  # armature space
        dp = arm.pose.bones[dname]
        dp.rotation_mode = "QUATERNION"
        q = dp.rotation_quaternion
        ax = (arm.data.bones[dname].matrix_local.to_3x3().inverted() @ seg).normalized()
        roll = 2 * math.atan2(Vector(q[1:]).dot(ax), q[0])
        roll = (roll + math.pi) % (2 * math.pi) - math.pi
        tp = arm.pose.bones[b]
        tp.rotation_mode = "QUATERNION"
        tax = (tb.matrix_local.to_3x3().inverted() @ seg).normalized()
        tp.rotation_quaternion = Quaternion(tax, float(tw["share"]) * roll)
        n += abs(roll) > 1e-4
    bpy.context.view_layer.update()
    return n


def turn(bn, axis, deg):
    pb = arm.pose.bones[bn]
    pb.rotation_mode = "QUATERNION"
    bpy.context.view_layer.update()
    M = pb.matrix.copy()
    R = Matrix.Rotation(math.radians(deg), 4, Vector(axis).normalized())
    T = Matrix.Translation(M.translation)
    pb.matrix = T @ R @ T.inverted() @ M
    bpy.context.view_layer.update()


def sticks(o, color, src=False, r=0.012):
    """the posed skeleton of armature o as boxes along its bones (head -> the chain child's head), parented to o's
    first root so it moves with it when placed beside: what the bones say, independent of the meshes."""
    import bmesh
    bm = bmesh.new()
    for pb in o.pose.bones:
        if "Twist" in pb.name or "_End" in pb.name:
            continue
        cn = chain_child(pb.name) if pb.name in arm.pose.bones else None
        kids = [o.pose.bones[cn]] if cn and cn in o.pose.bones else [c for c in pb.children if "Twist" not in c.name]
        for c in kids[:1]:
            a, b = o.matrix_world @ pb.head, o.matrix_world @ c.head
            d = b - a
            if d.length < 1e-4:
                continue
            q = Vector((0, 0, 1)).rotation_difference(d.normalized())
            res = bmesh.ops.create_cone(bm, cap_ends=True, segments=6, radius1=r, radius2=r * 0.5, depth=d.length)
            M = Matrix.Translation((a + b) / 2) @ q.to_matrix().to_4x4()
            bmesh.ops.transform(bm, matrix=M, verts=res["verts"])
    me = bpy.data.meshes.new("_sticks")
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new("_sticks" + ("_src" if src else ""), me)
    mat = bpy.data.materials.new("_sticks")
    mat.use_nodes = True
    mat.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (*color, 1)
    mat.node_tree.nodes["Principled BSDF"].inputs["Emission Color"].default_value = (*color, 1)
    mat.node_tree.nodes["Principled BSDF"].inputs["Emission Strength"].default_value = 0.6
    me.materials.append(mat)
    scene.collection.objects.link(ob)
    if src:  # (moved with the source when it is placed beside)
        ob["_src_offset"] = 1
    return ob


def set_action(o, clip):
    acts = [a for a in bpy.data.actions if a.name == clip or a.name.startswith(clip + "_") or a.name.startswith(clip)]
    if not acts:
        raise SystemExit(f"no clip {clip}: {[a.name for a in bpy.data.actions]}")
    o.animation_data_create()
    o.animation_data.action = acts[0]
    if hasattr(o.animation_data, "action_slot") and acts[0].slots:
        o.animation_data.action_slot = acts[0].slots[0]
    for t in list(o.animation_data.nla_tracks):
        t.mute = True


DIRS = {"front": (0, -1, 0.05), "three_quarter": (0.6, -0.8, 0.12), "side": (1, 0, 0.05), "left": (-1, 0, 0.05),
        "back": (0, 1, 0.1), "back_quarter": (-0.6, 0.8, 0.2)}
if arm is not None and arm.animation_data:
    arm.animation_data.action = None


def preview_frames():
    """asset.preview's job: explicit cameras (render.view_frames: dir, up, center + scale (ortho) or eye + fov, out)
    for each of job["poses"] ({ARKit name: weight, "turns": {bone: [x, y, z, deg]}}; None = the rest pose once)."""
    poses = job.get("poses")
    for i, pose in enumerate(poses if poses is not None else [{}]):
        pose = dict(pose or {})
        turns = pose.pop("turns", None) or {}
        if arm is not None:
            for pb in arm.pose.bones:
                pb.rotation_mode = "QUATERNION"
                pb.rotation_quaternion = (1, 0, 0, 0)
            bpy.context.view_layer.update()
            for bn, t in turns.items():
                if bn in arm.pose.bones:
                    turn(bn, t[:3], float(t[3]))
            drive_twist()
        for ob in meshes:
            if ob.data.shape_keys:
                for kb in ob.data.shape_keys.key_blocks[1:]:
                    kb.value = float(pose.get(kb.name, 0.0))
        blink = max([float(pose.get(k, 0.0)) for k in ("eyeBlinkLeft", "eyeBlinkRight")] + [0.0])
        for v in blink_nodes:
            v.outputs[0].default_value = 1.0 - blink
        for ob in meshes:
            ob.hide_render = any(ob.name.endswith("_" + h) for h in job.get("hide", []))
        bpy.context.view_layer.update()
        scene.render.resolution_x = scene.render.resolution_y = int(job.get("size", 512))
        for v in job["frames"]:
            d = Vector(v["dir"]).normalized()
            up = Vector(v["up"])
            right = up.cross(d).normalized()
            up = d.cross(right).normalized()
            if v.get("eye") is not None:
                cam_d.type, cam_d.angle = "PERSP", math.radians(v["fov"])
                cam_d.sensor_fit = "HORIZONTAL"
                cam.matrix_world = Matrix.Translation(Vector(v["eye"])) @ Matrix((right, up, d)).transposed().to_4x4()
            else:
                cam_d.type = "ORTHO"
                cam.matrix_world = Matrix.Translation(Vector(v["center"]) + d * 50) @ Matrix((right, up, d)).transposed().to_4x4()
                cam_d.ortho_scale = v["scale"]
            scene.render.filepath = v["out"][:-4] + (f"_p{i}" if poses is not None else "") + ".png"
            bpy.ops.render.render(write_still=True)
            print(f"wrote {scene.render.filepath}", flush=True)


if job.get("frames"):
    cam_d.clip_end = 1000
    preview_frames()
for pz in job.get("shots", []):
    for pb in arm.pose.bones:
        pb.rotation_mode = "QUATERNION"
        pb.rotation_quaternion = (1, 0, 0, 0)
        pb.location = (0, 0, 0)
    bpy.context.view_layer.update()
    nret = 0
    if src_arm is not None:
        for o in src_objs:
            o.hide_render = not (pz.get("beside") and pz.get("anim"))
    if pz.get("anim") and src_arm is not None:
        set_action(src_arm, pz["anim"][0])
        nret = retarget(int(round(float(pz["anim"][1]) * scene.render.fps)))
        de = direction_errors()
        body_ = {k: de.pop(k) for k in list(de) if not isinstance(de[k], (int, float))}
        worst = sorted(de.items(), key=lambda kv: -kv[1])[:6]
        print(f"@@direction {pz['name']}: max {worst[0][1]} deg; worst {worst}; {body_}", flush=True)
    for bn, t in (pz.get("turns") or {}).items():
        turn(P + bn if not bn.startswith(P) else bn, t[0], float(t[1]))
    if pz.get("hips_drop"):
        pb = arm.pose.bones[P + "Hips"]
        M = pb.matrix.copy()
        M.translation = M.translation - Vector((0, 0, float(pz["hips_drop"])))
        pb.matrix = M
        bpy.context.view_layer.update()
    ntw = drive_twist()
    shapes = pz.get("shapes") or {}
    for ob in meshes:
        if ob.data.shape_keys:
            for kb in ob.data.shape_keys.key_blocks[1:]:
                kb.value = float(shapes.get(kb.name, 0.0))
    blink = max([float(shapes.get(k, 0.0)) for k in ("eyeBlinkLeft", "eyeBlinkRight")] + [0.0])
    for v in blink_nodes:
        v.outputs[0].default_value = (1.0 - blink) if pz.get("blink_map", True) else 0.0
    for ob in meshes:
        ob.hide_render = any(ob.name.endswith("_" + h) for h in pz.get("hide", [])) or bool(pz.get("sticks_only"))
    if src_arm is not None and pz.get("sticks_only"):
        for o in src_objs:
            if o.type == "MESH":
                o.hide_render = True
    bpy.context.view_layer.update()
    fb = arm.pose.bones[P + pz.get("focus", "Spine2")]
    at = arm.matrix_world @ fb.head + Vector((0, 0, float(pz.get("lift", 0.0))))
    scene.render.resolution_x, scene.render.resolution_y = int(pz.get("w", 640)), int(pz.get("h", 640))
    cam_d.angle = math.radians(float(pz.get("fov", 30)))
    cam_d.sensor_fit = "VERTICAL"
    cam_d.type = "ORTHO" if pz.get("ortho") else "PERSP"
    if pz.get("ortho"):
        cam_d.ortho_scale = float(pz["ortho"]) * max(1.0, scene.render.resolution_x / scene.render.resolution_y)
    for v in pz.get("views", ["front"]):
        d = Vector(DIRS[v]).normalized()
        shift = Vector()
        if src_arm is not None and pz.get("beside") and pz.get("anim"):  # the source beside ours, on screen right
            right = Vector((0, 0, 1)).cross(d).normalized() * -1.0
            for o, l0 in src_roots:
                o.location = l0 + right * float(job.get("beside", 0.9))
            bpy.context.view_layer.update()
            shift = right * float(job.get("beside", 0.9)) / 2
        for o in [o for o in bpy.data.objects if o.name.startswith("_sticks")]:
            bpy.data.objects.remove(o, do_unlink=True)
        if pz.get("sticks") or pz.get("sticks_only"):  # the posed SKELETONS drawn (what the bones say, not the meshes)
            sticks(arm, (0.1, 0.5, 1.0))
            if src_arm is not None and pz.get("anim") and pz.get("beside"):
                sticks(src_arm, (1.0, 0.4, 0.1), src=True)
        eye = at + d * float(pz.get("dist", 1.5)) + shift
        look = at + shift
        cam.matrix_world = Matrix.Translation(eye) @ (look - eye).to_track_quat("-Z", "Y").to_matrix().to_4x4()
        scene.render.filepath = f"{job['out']}_{pz['name']}_{v}.png"
        bpy.ops.render.render(write_still=True)
        print(f"wrote {scene.render.filepath} (retargeted {nret}, twist {ntw})", flush=True)
print("done", flush=True)
