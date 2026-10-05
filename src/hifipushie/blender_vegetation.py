"""Blender side of vegetation: build a plant from its arrays (branch tubes as one mesh, leaves as instances of one
proto through Geometry Nodes), light it, render views. Run: blender -b --python blender_vegetation.py -- job.json

Job: {"npz", "views": [{"name", "azimuth", "elevation", "ortho": bool, "out", "size": [w, h], "leaves": bool,
"clay": bool}], "bark": [r, g, b], "leaf": [r, g, b], "sun": [azimuth, elevation], "save": path.blend}
"""

import json
import math
import sys

import bpy
import numpy as np
from mathutils import Matrix, Vector


def _mesh(name, V, F):
    me = bpy.data.meshes.new(name)
    me.vertices.add(len(V))
    me.vertices.foreach_set("co", np.asarray(V, np.float32).ravel())
    if len(F):
        me.loops.add(F.size)
        me.loops.foreach_set("vertex_index", np.asarray(F, np.int32).ravel())
        me.polygons.add(len(F))
        me.polygons.foreach_set("loop_start", np.arange(0, F.size, F.shape[1], dtype=np.int32))
        me.polygons.foreach_set("loop_total", np.full(len(F), F.shape[1], np.int32))
    me.update()
    me.validate()
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    return ob


def _mat(name, col, rough=0.8, translucent=0.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*col, 1)
    b.inputs["Roughness"].default_value = rough
    if translucent:
        b.inputs["Subsurface Weight"].default_value = translucent
        b.inputs["Subsurface Radius"].default_value = (0.1, 0.3, 0.05)
    m.use_backface_culling = False
    return m


def _leaves(points_ob, proto, mat):
    """Instance `proto` on the points' vertices: rotation from the 'rot' attribute (euler), scale from 'size'."""
    ng = bpy.data.node_groups.new("hp_leaves", "GeometryNodeTree")
    ng.interface.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    ng.interface.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    N, L = ng.nodes, ng.links
    gi, go = N.new("NodeGroupInput"), N.new("NodeGroupOutput")
    m2p = N.new("GeometryNodeMeshToPoints")
    inst = N.new("GeometryNodeInstanceOnPoints")
    info = N.new("GeometryNodeObjectInfo")
    info.inputs["Object"].default_value = proto
    rot = N.new("GeometryNodeInputNamedAttribute")
    rot.data_type = "FLOAT_VECTOR"
    rot.inputs["Name"].default_value = "rot"
    size = N.new("GeometryNodeInputNamedAttribute")
    size.data_type = "FLOAT"
    size.inputs["Name"].default_value = "size"
    setm = N.new("GeometryNodeSetMaterial")
    setm.inputs["Material"].default_value = mat
    L.new(gi.outputs[0], m2p.inputs["Mesh"])
    L.new(m2p.outputs["Points"], inst.inputs["Points"])
    L.new(info.outputs["Geometry"], inst.inputs["Instance"])
    e2r = N.new("FunctionNodeEulerToRotation")
    L.new(rot.outputs["Attribute"], e2r.inputs["Euler"])
    L.new(e2r.outputs["Rotation"], inst.inputs["Rotation"])
    L.new(size.outputs["Attribute"], inst.inputs["Scale"])
    L.new(inst.outputs["Instances"], setm.inputs["Geometry"])
    L.new(setm.outputs["Geometry"], go.inputs[0])
    md = points_ob.modifiers.new("leaves", "NODES")
    md.node_group = ng


def build(job):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    d = np.load(job["npz"])
    bark = _mat("bark", job.get("bark", [0.25, 0.19, 0.14]), 0.9)
    leaf = _mat("leaf", job.get("leaf", [0.16, 0.33, 0.08]), 0.55, translucent=0.15)
    clay = _mat("clay", [0.6, 0.6, 0.6], 0.8)
    wood = _mesh("wood", d["V"], d["F"])
    wood.data.materials.append(bark)
    for p in wood.data.polygons:
        p.use_smooth = True
    obs = {"wood": wood}
    if len(d["leaf_pos"]):
        proto = _mesh("leaf_proto", d["proto_V"], d["proto_F"])
        proto.hide_render = True
        proto.hide_viewport = True
        pts = _mesh("leaves", d["leaf_pos"], np.zeros((0, 3), np.int32))
        a = pts.data.attributes.new("rot", "FLOAT_VECTOR", "POINT")
        a.data.foreach_set("vector", d["leaf_rot"].astype(np.float32).ravel())
        a = pts.data.attributes.new("size", "FLOAT", "POINT")
        a.data.foreach_set("value", d["leaf_size"].astype(np.float32))
        _leaves(pts, proto, leaf)
        obs["leaves"] = pts
    # ground, sun, sky
    lo, hi = d["V"].min(0), d["V"].max(0)
    if len(d["leaf_pos"]):
        lo, hi = np.minimum(lo, d["leaf_pos"].min(0)), np.maximum(hi, d["leaf_pos"].max(0))
    R = float(max(hi[0] - lo[0], hi[1] - lo[1], hi[2]))
    bpy.ops.mesh.primitive_circle_add(vertices=64, radius=3 * R, fill_type="NGON", location=(0, 0, 0))
    ground = bpy.context.object
    ground_mat = _mat("ground", job.get("ground", [0.42, 0.44, 0.36]), 1.0)
    clay_ground = _mat("clay_ground", [0.3, 0.3, 0.3], 1.0)
    ground.data.materials.append(ground_mat)
    sa, se = [math.radians(v) for v in job.get("sun", [135, 50])]
    sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN"))
    sun.data.energy = 3.5
    sun.data.angle = math.radians(2)
    sc.collection.objects.link(sun)
    dvec = Vector((math.sin(sa) * math.cos(se), math.cos(sa) * math.cos(se), math.sin(se)))
    sun.rotation_euler = dvec.to_track_quat("Z", "Y").to_euler()
    w = bpy.data.worlds.new("w")
    w.use_nodes = True
    w.node_tree.nodes["Background"].inputs[0].default_value = (*job.get("sky", [0.62, 0.74, 0.9]), 1)
    w.node_tree.nodes["Background"].inputs[1].default_value = 0.9
    sc.world = w
    sc.render.engine = "BLENDER_EEVEE"
    sc.view_settings.view_transform = "Standard"
    try:
        sc.eevee.use_shadows = True
    except Exception:
        pass
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
    sc.collection.objects.link(cam)
    sc.camera = cam
    cen = Vector(((lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, hi[2] / 2))
    for v in job["views"]:
        az, el = math.radians(v.get("azimuth", 0)), math.radians(v.get("elevation", 0))
        back = Vector((-math.sin(az) * math.cos(el), -math.cos(az) * math.cos(el), math.sin(el)))
        # azimuth 0 looks along +y (the silhouette's x = world x)
        cam.rotation_euler = back.to_track_quat("Z", "Y").to_euler()
        wpx, hpx = v.get("size", [700, 900])
        sc.render.resolution_x, sc.render.resolution_y = wpx, hpx
        right = Vector((math.cos(az), -math.sin(az), 0))
        allp = d["V"] if not len(d["leaf_pos"]) else np.vstack([d["V"], d["leaf_pos"]])
        xs = allp @ np.array(right)
        cen = Vector(right) * float((xs.min() + xs.max()) / 2) + Vector((0, 0, hi[2] / 2))
        cam.location = cen + back * (4 * R)
        big = max(wpx, hpx)
        need = max(float(xs.max() - xs.min()) * big / wpx, float(hi[2]) * big / hpx) * 1.08
        if v.get("ortho", True):
            cam.data.type = "ORTHO"
            cam.data.ortho_scale = v.get("span") or need
        else:
            cam.data.type = "PERSP"
            cam.data.lens = 50
        cam.data.clip_end = 20 * R
        if "leaves" in obs:
            obs["leaves"].hide_render = not v.get("leaves", True)
        isclay = bool(v.get("clay"))
        w.node_tree.nodes["Background"].inputs[0].default_value = (0.2, 0.22, 0.25, 1) if isclay else (*job.get("sky", [0.62, 0.74, 0.9]), 1)
        ground.data.materials[0] = clay_ground if isclay else ground_mat
        wood.data.materials[0] = clay if isclay else bark
        ground.hide_render = bool(v.get("no_ground"))
        sc.render.film_transparent = bool(v.get("transparent"))
        sc.render.filepath = v["out"]
        bpy.ops.render.render(write_still=True)
        print("@@rendered", v["out"])
    if job.get("save"):
        bpy.ops.wm.save_as_mainfile(filepath=job["save"])


if __name__ == "__main__":
    build(json.loads(open(sys.argv[sys.argv.index("--") + 1]).read()))
