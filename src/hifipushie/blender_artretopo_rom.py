"""Artist retopo, the range-of-motion pass (imported by blender_artretopo_posecheck.py inside Blender).

Each pose is [(bone, world axis, degrees)], [(bone, "lx", degrees)] (about the bone's own x: a finger's curl) or
[(bone, "aim", direction)] (resolved from the bone's CURRENT direction), applied parent-first about each joint.
The director's limits (2026-11-17): arms "up" = each arm AIMED 30 deg off vertical, out to the side (straighter clips
the head; it is not a pose these characters need); past 60 deg of arm lift about an axis the clavicle takes a share
(0.3), never for an aimed arm; a helper bone turns half as far as its joint (half the aim, for an aim). Measured per pose on the body: folds (faces whose normal opposes their
neighbours' mean), squashed edges (< 0.5 x rest length), stretched (> 1.8 x), min / max ratio. mouth_open_20's
stretched edges are the mouth bag opening (expected), not a fault."""
import math

import bpy
import bmesh
from mathutils import Matrix, Quaternion, Vector

import blender_artretopo_common as C

S30 = math.sin(math.radians(30)); C30 = math.cos(math.radians(30))
POSES = {
    "rest": [],
    "arms_side_80": [("LeftArm", (0, 1, 0), -80), ("RightArm", (0, 1, 0), 80)],
    "arms_up_150": [("LeftArm", "aim", (S30, 0, C30)), ("RightArm", "aim", (-S30, 0, C30))],
    "arms_forward_90": [("LeftArm", (1, 0, 0), -90), ("RightArm", (1, 0, 0), -90)],
    "arms_back_40": [("LeftArm", (1, 0, 0), 40), ("RightArm", (1, 0, 0), 40)],
    "elbows_120": [("LeftArm", (1, 0, 0), -30), ("RightArm", (1, 0, 0), -30), ("LeftForeArm", (1, 0, 0), -120), ("RightForeArm", (1, 0, 0), -120)],
    "leg_forward_80": [("LeftUpLeg", (1, 0, 0), -80)],
    "knee_up_100": [("LeftUpLeg", (1, 0, 0), -90), ("LeftLeg", (1, 0, 0), 100)],
    "leg_back_35": [("LeftUpLeg", (1, 0, 0), 35)],
    "leg_side_40": [("LeftUpLeg", (0, 1, 0), -40)],
    "crouch": [("LeftUpLeg", (1, 0, 0), -70), ("RightUpLeg", (1, 0, 0), -70), ("LeftLeg", (1, 0, 0), 110), ("RightLeg", (1, 0, 0), 110),
               ("LeftFoot", (1, 0, 0), -40), ("RightFoot", (1, 0, 0), -40)],
    "spine_forward_40": [("Spine", (1, 0, 0), 15), ("Spine1", (1, 0, 0), 15), ("Spine2", (1, 0, 0), 10)],
    "spine_side_30": [("Spine", (0, 1, 0), 10), ("Spine1", (0, 1, 0), 10), ("Spine2", (0, 1, 0), 10)],
    "spine_twist_45": [("Spine", (0, 0, 1), 15), ("Spine1", (0, 0, 1), 15), ("Spine2", (0, 0, 1), 15)],
    "head_turn_60": [("Neck", (0, 0, 1), 25), ("Head", (0, 0, 1), 35)],
    "head_down_up": [("Neck", (1, 0, 0), 20), ("Head", (1, 0, 0), 20)],
    "mouth_open_20": [("Jaw", (1, 0, 0), 20)],
}


def expand(spec, J, rig, HELP, PFX):
    """the clavicle's share (an arm turned past 60 deg about a world axis) and the half-angle helpers. An AIMED bone
    is resolved in set_pose from its CURRENT direction (a child's rest direction is wrong once its parent moved) and
    takes no clavicle share (it pulls an aimed arm inward); its helper turns half the aim there."""
    out = []
    clav = J.get("clavicle", 0.3)
    for bn, ax, deg in spec:
        if ax == "aim":
            out.append((bn, "aim", deg)); continue
        side = "Left" if bn.startswith("Left") else "Right" if bn.startswith("Right") else ""
        j = bn[len(side):]
        if ax != "lx" and j == "Arm" and clav and abs(deg) > 60:       # past 60 deg the clavicle lifts a share of it
            out.append((side + "Shoulder", ax, deg * clav)); deg = deg * (1 - clav)
        out.append((bn, ax, deg))
        if j in HELP:
            out.append((bn + "_bend", ax, deg * 0.5))
    return out


def set_pose(rig, spec, J, BONES, HELP, PFX):
    """each entry turns its bone about its joint, parents first: (bone, world axis, deg), (bone, "lx", deg) about the
    bone's own current x axis (a finger curling), (bone, "aim", direction) pointing the bone along a world direction"""
    spec = expand(spec, J, rig, HELP, PFX)
    order = [PFX + n for n, *_ in BONES]
    for pb in rig.pose.bones:
        pb.rotation_mode = "QUATERNION"; pb.rotation_quaternion = Quaternion(); pb.location = (0, 0, 0)
    bpy.context.view_layer.update()
    key = lambda n: order.index(PFX + n) if PFX + n in order else 10 ** 6 + order.index(PFX + n.replace("_bend", ""))

    def turn(pb, axis, ang):
        hd = pb.matrix.to_translation()
        pb.matrix = Matrix.Translation(hd) @ Matrix.Rotation(ang, 4, axis) @ Matrix.Translation(-hd) @ pb.matrix
        bpy.context.view_layer.update()

    for n in sorted({s[0] for s in spec}, key=key):
        pb = rig.pose.bones[PFX + n]
        for bn, ax, deg in spec:
            if bn != n:
                continue
            if ax == "aim":
                cur = (pb.matrix.to_3x3() @ Vector((0, 1, 0))).normalized()
                axis, ang = cur.rotation_difference(Vector(deg).normalized()).to_axis_angle()
                turn(pb, axis, ang)
                hb = rig.pose.bones.get(PFX + n + "_bend")
                if hb:
                    turn(hb, axis, ang / 2)
                continue
            if ax == "lx":
                ax = (pb.matrix.to_3x3() @ Vector((1, 0, 0))).normalized()
            turn(pb, Vector(ax), math.radians(deg))


class Rest:
    def __init__(self, body):
        bm = bmesh.new(); bm.from_mesh(body.data); bm.verts.ensure_lookup_table()
        self.length = [e.calc_length() for e in bm.edges]
        self.edges = [(e.verts[0].index, e.verts[1].index) for e in bm.edges]
        self.faces = [[v.index for v in f.verts] for f in bm.faces]
        self.nbr = [[g.index for e in f.edges for g in e.link_faces if g.index != f.index] for f in bm.faces]
        self.e2f = {}
        for f in bm.faces:
            for e in f.edges:
                self.e2f.setdefault(e.index, []).append(f.index)
        self.lo = [min(v.co[k] for v in bm.verts) for k in range(3)]
        self.hi = [max(v.co[k] for v in bm.verts) for k in range(3)]
        bm.free()


def posed(body):
    dg = bpy.context.evaluated_depsgraph_get(); ev = body.evaluated_get(dg); m = ev.to_mesh()
    co = [v.co.copy() for v in m.vertices]; ev.to_mesh_clear()
    return co


def measure(body, R):
    co = posed(body)
    ratio = [(co[i] - co[j]).length / max(L, 1e-9) for (i, j), L in zip(R.edges, R.length)]
    fn = [((co[f[1]] - co[f[0]]).cross(co[f[2]] - co[f[0]])).normalized() for f in R.faces]
    folds = 0
    for k in range(len(R.faces)):
        avg = Vector((0, 0, 0))
        for g in R.nbr[k]:
            avg += fn[g]
        if avg.length > 1e-9 and fn[k].dot(avg.normalized()) < 0.0:
            folds += 1
    return dict(folds=folds, squashed=sum(r < 0.5 for r in ratio), stretched=sum(r > 1.8 for r in ratio),
                min_ratio=round(min(ratio), 3), max_ratio=round(max(ratio), 3)), ratio


def spec_of(v):
    """a pose from JSON: [[bone, [axis], degrees] | [bone, "lx", degrees] | [bone, "aim", [direction]], ...]"""
    return [(b, a if a in ("aim", "lx") else tuple(a), tuple(d) if a == "aim" else float(d)) for b, a, d in v]


def run(J, sc, rig, body, LODS, props, BONES, HELP, PFX, poses):
    """pose, measure, render (front + 3/4) every pose in `poses` ({name: spec}); LOD1 in four of them"""
    D = J["dir"]; R = Rest(body); globals()["_REST"] = R
    H = R.hi[2] - R.lo[2]; ctr = [(a + b) / 2 for a, b in zip(R.lo, R.hi)]
    sh = C.workbench(sc, 520, colour="TEXTURE"); sh.show_cavity = False
    cam = C.ortho_camera(sc, 1.45 * H)
    res = {}
    for o in LODS:                  # LOD1 has its own pictures below
        o.hide_render = True
    for name, spec in poses.items():
        set_pose(rig, spec, J, BONES, HELP, PFX)
        r, _ = measure(body, R); res[name] = r; print("POSE", name, r)
        for vn, d in (("front", (0, -1, 0)), ("3q", (-0.9, -1, 0.35))):
            C.aim(cam, ctr, d); sc.render.filepath = f"{D}/rom_{name}_{vn}.png"; bpy.ops.render.render(write_still=True)
    if LODS and J.get("lod_renders", True):
        for nm in [n for n in ("rest", "arms_side_80", "knee_up_100", "mouth_open_20") if n in poses]:
            set_pose(rig, poses[nm], J, BONES, HELP, PFX)
            for o in sc.objects:
                if o.type == "MESH":
                    o.hide_render = not (o in LODS or o in props)
            C.aim(cam, ctr, (-0.9, -1, 0.35)); sc.render.filepath = f"{D}/lod1_{nm}.png"; bpy.ops.render.render(write_still=True)
        for o in sc.objects:
            if o.type == "MESH":
                o.hide_render = o in LODS
    set_pose(rig, [], J, BONES, HELP, PFX)
    return {"poses": res, "height": round(H, 4)}


def close_framing(J, H):
    """close-up views from the joints (left side, +x): (direction, target, ortho scale) per pose"""
    jt = {k: Vector(v) for k, v in J["joints"].items()}
    sh, el, kn = jt["shoulder"], jt["elbow"], jt["knee"]
    out = {"arms_side_80": ((-0.3, -1, 0.3), sh + Vector((0.05, 0, 0.0)) * H, 0.5 * H),
           "arms_up_150": ((-0.6, -1, 0.2), sh + Vector((0.06, 0, 0.1)) * H, 0.5 * H),
           "arms_forward_90": ((0.9, -0.6, 0.3), sh, 0.5 * H),
           "elbows_120": ((-0.5, -1, 0.1), el, 0.4 * H),
           "knee_up_100": ((-0.9, -1, 0.1), kn, 0.55 * H),
           "crouch": ((-1, -0.8, 0.2), Vector((0, kn.y, kn.z)), 0.6 * H)}
    if "jaw" in jt:
        m = jt["jaw"] * 0.3 + jt["jaw_tip"] * 0.7
        out.update({"rest#mouth_front": ((0, -1, 0.1), m, 0.22 * H), "mouth_open_20#front": ((0, -1, 0.1), m, 0.22 * H),
                    "mouth_open_20#3q": ((-0.7, -1, 0.0), m, 0.22 * H)})
    return out


def close_ups(J, sc, rig, body, BONES, HELP, PFX, poses, extra=None, standard=True):
    """grey clay, faces with an edge squashed < 0.5 or stretched > 1.8 in red, a thin wire"""
    D = J["dir"]; R = globals()["_REST"]; H = R.hi[2] - R.lo[2]
    sh = C.workbench(sc, 700); sh.show_cavity = True
    body.data.materials.clear()
    body.data.materials.append(C.flat_mat("grey", (0.82, 0.8, 0.77, 1))); body.data.materials.append(C.flat_mat("red", (0.9, 0.12, 0.1, 1)))
    C.wire_copy(sc, body, 0.0009 * H, (0.1, 0.1, 0.12, 1))
    cam = sc.camera
    frames = {k: v for k, v in close_framing(J, H).items() if k.split("#")[0] in poses} if standard else {}
    for k, v in (extra or {}).items():            # your own close-ups: {name: {view, target, scale}}
        if k.split("#")[0] not in poses:
            raise ValueError(f"close-up {k!r}: no pose {k.split('#')[0]!r} in this run")
        frames[k] = (tuple(v["view"]), Vector(v["target"]), float(v["scale"]))
    for name, (d, T, scale) in frames.items():
        set_pose(rig, poses[name.split("#")[0]], J, BONES, HELP, PFX)
        co = posed(body); badf = set()
        for k, ((i, j), L) in enumerate(zip(R.edges, R.length)):
            r = (co[i] - co[j]).length / max(L, 1e-9)
            if r < 0.5 or r > 1.8:
                badf.update(R.e2f.get(k, []))
        for p in body.data.polygons:
            p.material_index = 1 if p.index in badf else 0
        cam.data.ortho_scale = scale; C.aim(cam, T, d)
        sc.render.filepath = f"{D}/close_{name.replace('#', '_')}.png"; bpy.ops.render.render(write_still=True)
    set_pose(rig, [], J, BONES, HELP, PFX)
