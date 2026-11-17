"""Hard surface from the point cloud, inside Blender: a RIGID-PARTS rig (hinges, spinners, sliders) and its tests.
    blender -b --factory-startup --python blender_hardsurf_rig.py -- job.json
job: {"parts": baked.glb, "out": rigged.glb, "report": rig.json, "renders": folder or null,
      "joints": [{"name", "kind": "hinge"|"spinner"|"slider", "parts": [names], "pivot": [x,y,z], "axis": [x,y,z],
                  "parent": joint name or null, "range": [lo, hi] (degrees; metres for a slider),
                  "follows": {"joint": name, "ratio": r} (optional: this joint = ratio x that one: linked doors, gear
                  trains, a steering link), "static": [names the moving parts must clear] (default: every part not
                  moved by this joint)}],
      "lod_ratio": 0.35 (a decimated _LOD1 copy of every part on the same UVs; 0 = none)}
Bones: root, then one bone per joint at its pivot pointing along its axis (rotation / translation about the bone's Y).
Parts no joint names ride root. Each joint gets an action (rest -> hi -> lo -> rest) exported as an NLA track.
TESTS (numbers, not pictures):
- `turns`: at hi, each moved part turned by the expected angle about the expected axis (deg, |axis . expected|), or
  slid by the expected distance; a follower by ratio x its leader. A sign error shows up here, not in a render.
- `clear`: the largest value in [0, hi] and [lo, 0] at which the moved parts don't cross `static` (binary search), so
  the range the model really allows is known; a range blocked at rest says the parts already cross.
Spinners: test at +-90 (a full turn reads as 0 deg); the game spins them, the test only checks the axis and sign."""
import bpy, bmesh, sys, json, math, os
from mathutils import Vector, Matrix
from mathutils.bvhtree import BVHTree
J = json.load(open(sys.argv[sys.argv.index("--") + 1]))
bpy.ops.wm.read_factory_settings(use_empty=True); sc = bpy.context.scene
bpy.ops.import_scene.gltf(filepath=J["parts"])
for o in [o for o in sc.objects if o.type != "MESH" or o.name.startswith("Icosphere")]: bpy.data.objects.remove(o)
parts = {o.name: o for o in sc.objects if o.type == "MESH"}
for o in parts.values():
    mw = o.matrix_world.copy(); o.parent = None; o.matrix_world = mw
JO = {j["name"]: j for j in J["joints"]}
for j in JO.values():
    missing = [p for p in j["parts"] if p not in parts]
    if missing: raise ValueError(f"joint {j['name']}: no parts named {missing}")

# ---- LOD1
lods = {}
if float(J.get("lod_ratio", 0.35)) > 0:
    for n, o in list(parts.items()):
        l = o.copy(); l.data = o.data.copy(); l.name = f"{n}_LOD1"; sc.collection.objects.link(l)
        dm = l.modifiers.new("dec", "DECIMATE"); dm.ratio = float(J.get("lod_ratio", 0.35))
        bpy.context.view_layer.objects.active = l; bpy.ops.object.modifier_apply(modifier="dec"); lods[n] = l

# ---- armature
arm = bpy.data.objects.new("rig", bpy.data.armatures.new("rig")); sc.collection.objects.link(arm)
bpy.context.view_layer.objects.active = arm; bpy.ops.object.mode_set(mode="EDIT"); eb = arm.data.edit_bones
r = eb.new("root"); r.head, r.tail = Vector((0, 0, 0)), Vector((0, -0.2, 0))
order = []
def place(name):
    if name in order: return
    j = JO[name]
    if j.get("parent"): place(j["parent"])
    b = eb.new(name); p = Vector(j["pivot"]); a = Vector(j["axis"]).normalized()
    b.head, b.tail = p, p + a * 0.1; b.parent = eb[j["parent"]] if j.get("parent") else eb["root"]; order.append(name)
for n in JO: place(n)
bpy.ops.object.mode_set(mode="OBJECT")
owner = {}
for n in order:
    for p in JO[n]["parts"]: owner[p] = n
for n, o in list(parts.items()) + list(lods.items()):
    b = owner.get(n.replace("_LOD1", ""), "root"); mw = o.matrix_world.copy()
    o.parent = arm; o.parent_type = "BONE"; o.parent_bone = b; bpy.context.view_layer.update(); o.matrix_world = mw
pb = arm.pose.bones
for b in pb: b.rotation_mode = "XYZ"


def pose(vals):
    """vals: {joint: value}; followers take ratio x their leader unless given"""
    for b in pb: b.rotation_euler = (0, 0, 0); b.location = (0, 0, 0)
    full = dict(vals)
    for n, j in JO.items():
        f = j.get("follows")
        if f and n not in vals and f["joint"] in full: full[n] = f["ratio"] * full[f["joint"]]
    for n, v in full.items():
        if JO[n]["kind"] == "slider": pb[n].location[1] = v
        else: pb[n].rotation_euler[1] = math.radians(v)
    bpy.context.view_layer.update(); return full


def moved_by(n):
    out = set(JO[n]["parts"])
    for m, j in JO.items():
        par = j.get("parent")
        while par:
            if par == n: out |= set(j["parts"]); break
            par = JO[par].get("parent")
        f = j.get("follows")
        if f and f["joint"] == n: out |= moved_by(m)
    return out


def tree(objs):
    dg = bpy.context.evaluated_depsgraph_get(); vs, fs = [], []
    for o in objs:
        e = o.evaluated_get(dg); m = e.to_mesh(); off = len(vs)
        vs += [e.matrix_world @ v.co for v in m.vertices]; fs += [[off + i for i in p.vertices] for p in m.polygons]; e.to_mesh_clear()
    return BVHTree.FromPolygons(vs, fs)


rep = {"joints": {}}
for n, j in JO.items():
    mov = moved_by(n); static = [parts[s] for s in j.get("static", [k for k in parts if k not in mov])]
    movers = [parts[k] for k in mov]
    def hits(v):
        pose({n: v}); return len(tree(static).overlap(tree(movers))) if static and movers else 0
    lo, hi = j["range"]; res = {}
    # turns: every moved part (incl. followers) at hi
    pose({}); m0 = {k: parts[k].matrix_world.copy() for k in mov}; full = pose({n: hi})
    turns = {}
    def mover(k):         # the joint up the part's chain that actually moved (a wheel steers with its pivot)
        jj = owner.get(k)
        while jj:
            if abs(full.get(jj, 0.0)) > 1e-9: return jj
            jj = JO[jj].get("parent")
        return None
    for k in sorted(mov):
        jj = mover(k)
        if jj is None: continue
        exp = full.get(jj, 0.0); M1 = parts[k].matrix_world
        if JO[jj]["kind"] == "slider":
            d = (M1.translation - m0[k].translation); turns[k] = {"moved_m": round(d.length, 4), "expected_m": round(abs(exp), 4),
                                                               "axis_dot": round(abs(d.normalized().dot(Vector(JO[jj]["axis"]).normalized())), 3) if d.length > 1e-6 else None}
        else:
            q = (M1.to_3x3() @ m0[k].to_3x3().inverted()).to_quaternion(); ax, ang = q.to_axis_angle()
            turns[k] = {"deg": round(math.degrees(ang), 2), "expected_deg": round(abs(exp), 2),
                        "axis_dot": round(abs(ax.dot(Vector(JO[jj]["axis"]).normalized())), 3)}
    res["turns"] = turns
    rest = hits(0.0); res["crossing_at_rest"] = rest
    def clear(end):
        if not rest and not hits(end): return end
        a, b = 0.0, end
        if rest: return 0.0
        for _ in range(10):
            mid = (a + b) / 2
            if hits(mid): b = mid
            else: a = mid
        return round(a, 4)
    res["clear"] = [clear(lo), clear(hi)]
    rep["joints"][n] = res
pose({})

# ---- actions: rest -> hi -> lo -> rest per joint (followers keyed with it)
arm.animation_data_create()
for n, j in JO.items():
    act = bpy.data.actions.new(n); arm.animation_data.action = act
    lo, hi = rep["joints"][n]["clear"]
    for fr, v in ((1, 0.0), (12, hi), (36, lo), (48, 0.0)):
        full = pose({n: v}); sc.frame_set(fr)
        for k, val in full.items():
            if JO[k]["kind"] == "slider": pb[k].keyframe_insert("location", index=1, frame=fr)
            else: pb[k].keyframe_insert("rotation_euler", index=1, frame=fr)
    tr = arm.animation_data.nla_tracks.new(); tr.name = n; tr.strips.new(n, 1, act); arm.animation_data.action = None
pose({})
if J.get("renders"):
    os.makedirs(J["renders"], exist_ok=True)
    sc.render.engine = "BLENDER_WORKBENCH"; sc.render.resolution_x = sc.render.resolution_y = 480
    sc.display.shading.color_type = "TEXTURE"; sc.world = bpy.data.worlds.new("w"); sc.world.color = (0.9, 0.9, 0.9)
    cam = bpy.data.objects.new("c", bpy.data.cameras.new("c")); sc.collection.objects.link(cam); sc.camera = cam; cam.data.type = "ORTHO"
    pts = [o.matrix_world @ Vector(c) for o in parts.values() for c in o.bound_box]
    C = sum(pts, Vector()) / len(pts); size = max(max(p[i] for p in pts) - min(p[i] for p in pts) for i in range(3))
    cam.data.ortho_scale = size * 1.2
    for l in lods.values(): l.hide_render = True
    for n, j in JO.items():
        for tag, v in (("rest", 0.0), ("hi", rep["joints"][n]["clear"][1]), ("lo", rep["joints"][n]["clear"][0])):
            pose({n: v}); d = Vector((-0.9, -1, 0.55)).normalized(); cam.location = C + d * 5
            cam.rotation_euler = (C - cam.location).to_track_quat("-Z", "Y").to_euler()
            sc.render.filepath = f"{J['renders']}/{n}_{tag}.png"; bpy.ops.render.render(write_still=True)
    pose({})
for tr in arm.animation_data.nla_tracks: tr.mute = False
bpy.ops.export_scene.gltf(filepath=J["out"], export_format="GLB", export_extras=True, export_animations=True,
                          export_animation_mode="NLA_TRACKS", export_force_sampling=True)
rep["faces"] = sum(len(o.data.polygons) for o in parts.values()); rep["lod1_faces"] = sum(len(o.data.polygons) for o in lods.values())
json.dump(rep, open(J["report"], "w"), indent=1); print("RIG", json.dumps(rep)[:2000])
