"""Runs inside headless Blender: a terrain grid mesh (vertex colours) and its lakes, rendered in Cycles
under a sun (per view [bearing, height] deg: terrain_sun picks it) and sky from perspective cameras. Job: {"mesh",
"size": [w, h], "samples", "views": [{"eye": [x, y, z], "look": [x, y, z], "fov": deg, "sun": [b, h], "out": png}]}."""
import math

import json
import sys

import bpy
import numpy as np
from mathutils import Vector


def _mesh(name, verts, faces, colors=None):
    me = bpy.data.meshes.new(name)
    me.vertices.add(len(verts))
    me.vertices.foreach_set("co", verts.ravel())
    me.loops.add(faces.size)
    me.loops.foreach_set("vertex_index", faces.ravel())
    me.polygons.add(len(faces))
    me.polygons.foreach_set("loop_start", np.arange(0, faces.size, 3, dtype=np.int32))
    me.update()
    me.shade_smooth()
    if colors is not None:
        a = me.color_attributes.new("col", "FLOAT_COLOR", "POINT")
        a.data.foreach_set("color", np.c_[colors, np.ones(len(colors))].astype(np.float32).ravel())
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    return ob


def _proto(kind):
    """A low-poly tree, hidden from render, for the scatter to instance: a cone conifer or a round broadleaf."""
    parts = []
    bpy.ops.mesh.primitive_cylinder_add(vertices=6, radius=0.45, depth=4, location=(0, 0, 2))
    parts.append(bpy.context.object)
    trunk = bpy.data.materials.new("trunk")
    trunk.diffuse_color = (0.12, 0.07, 0.04, 1)
    trunk.use_nodes = True
    trunk.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.12, 0.07, 0.04, 1)
    parts[-1].data.materials.append(trunk)
    if kind == "conifer":
        bpy.ops.mesh.primitive_cone_add(vertices=8, radius1=3.0, depth=13, location=(0, 0, 9))
        col = (0.025, 0.07, 0.03, 1)
    elif kind == "fruit":  # orchard trees: small, round, low trunk
        parts[0].scale = (0.6, 0.6, 0.45)
        parts[0].location = (0, 0, 0.9)
        bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=2, radius=2.2, location=(0, 0, 3.2))
        col = (0.09, 0.16, 0.04, 1)
    else:
        bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=2, radius=4.5, location=(0, 0, 7.5))
        col = (0.07, 0.13, 0.03, 1)
    crown = bpy.data.materials.new("crown_" + kind)
    crown.use_nodes = True
    b = crown.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = col
    b.inputs["Roughness"].default_value = 0.8
    bpy.context.object.data.materials.append(crown)
    parts.append(bpy.context.object)
    bpy.ops.object.select_all(action="DESELECT")
    for p in parts:
        p.select_set(True)
    bpy.context.view_layer.objects.active = parts[-1]
    bpy.ops.object.join()
    ob = bpy.context.object
    ob.name = "tree_" + kind
    ob.hide_render = True
    ob.location = (0, 0, -1e4)
    return ob


def _instance(points_ob, kind):
    """A tree on every vertex of points_ob, with a random size and turn."""
    ng = bpy.data.node_groups.new("inst_" + kind, "GeometryNodeTree")
    ng.interface.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    ng.interface.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    N, L = ng.nodes, ng.links
    gi, go = N.new("NodeGroupInput"), N.new("NodeGroupOutput")
    inst = N.new("GeometryNodeInstanceOnPoints")
    info = N.new("GeometryNodeObjectInfo")
    info.inputs["Object"].default_value = _proto(kind)
    L.new(gi.outputs[0], inst.inputs["Points"])
    L.new(info.outputs["Geometry"], inst.inputs["Instance"])
    size = N.new("FunctionNodeRandomValue")
    size.data_type = "FLOAT"
    size.inputs[2].default_value, size.inputs[3].default_value = 0.7, 1.3
    L.new(size.outputs[1], inst.inputs["Scale"])
    turn = N.new("FunctionNodeRandomValue")
    turn.data_type = "FLOAT_VECTOR"
    turn.inputs[1].default_value = (0, 0, 6.283)
    L.new(turn.outputs[0], inst.inputs["Rotation"])
    L.new(inst.outputs["Instances"], go.inputs[0])
    points_ob.modifiers.new("trees", "NODES").node_group = ng


def _scatter(ground, kinds, per_m2=0.02):
    """Geometry nodes on the ground: for each tree kind, points distributed by its density attribute, a tree
    instanced on each with a random size and turn."""
    ng = bpy.data.node_groups.new("trees", "GeometryNodeTree")
    ng.interface.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    ng.interface.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    N, L = ng.nodes, ng.links
    gi, go = N.new("NodeGroupInput"), N.new("NodeGroupOutput")
    join = N.new("GeometryNodeJoinGeometry")
    L.new(gi.outputs[0], join.inputs[0])
    for i, kind in enumerate(kinds):
        attr = N.new("GeometryNodeInputNamedAttribute")
        attr.data_type = "FLOAT"
        attr.inputs["Name"].default_value = "trees_" + kind
        dist = N.new("GeometryNodeDistributePointsOnFaces")
        dist.distribute_method = "POISSON"  # spaced trees; the density factor input only exists in this mode
        dist.inputs["Distance Min"].default_value = 4.0
        dist.inputs["Density Max"].default_value = per_m2
        dist.inputs["Seed"].default_value = 7 + i
        L.new(gi.outputs[0], dist.inputs["Mesh"])
        L.new(attr.outputs["Attribute"], dist.inputs["Density Factor"])
        inst = N.new("GeometryNodeInstanceOnPoints")
        info = N.new("GeometryNodeObjectInfo")
        info.inputs["Object"].default_value = _proto(kind)
        L.new(dist.outputs["Points"], inst.inputs["Points"])
        L.new(info.outputs["Geometry"], inst.inputs["Instance"])
        size = N.new("FunctionNodeRandomValue")
        size.data_type = "FLOAT"
        # Random Value repeats socket names per data type: [vector min, max, float min, max, int min, max, ...]
        size.inputs[2].default_value, size.inputs[3].default_value = 0.6, 1.4
        size.inputs["Seed"].default_value = 3 + i
        L.new(size.outputs[1], inst.inputs["Scale"])
        turn = N.new("FunctionNodeRandomValue")
        turn.data_type = "FLOAT_VECTOR"
        turn.inputs[1].default_value = (0, 0, 6.283)
        L.new(turn.outputs[0], inst.inputs["Rotation"])
        L.new(inst.outputs["Instances"], join.inputs[0])
    L.new(join.outputs[0], go.inputs[0])
    mod = ground.modifiers.new("trees", "NODES")
    mod.node_group = ng


def run(job):
    for coll in (bpy.data.objects, bpy.data.meshes, bpy.data.cameras, bpy.data.lights, bpy.data.node_groups):
        for item in list(coll):
            coll.remove(item)
    d = np.load(job["mesh"])
    ground = _mesh("ground", d["verts"], d["faces"], d["colors"])
    m = bpy.data.materials.new("ground")
    m.use_nodes = True
    nt = m.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    attr = nt.nodes.new("ShaderNodeAttribute")
    attr.attribute_name = "col"
    nt.links.new(attr.outputs["Color"], bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.9
    # ground is matte: the default specular sheen at grazing angles (every view from a boat or a valley floor) lifted
    # dark cover to grey-brown (black lava read as brown rock)
    for k in ("Specular IOR Level", "Specular"):
        if k in bsdf.inputs:
            bsdf.inputs[k].default_value = 0.12
    ground.data.materials.append(m)
    if "tree_xyz" in d.files and len(d["tree_xyz"]):  # the same tree instances the export writes
        for kind in sorted(set(d["tree_kind"].tolist())):
            pts = d["tree_xyz"][d["tree_kind"] == kind]
            me = bpy.data.meshes.new("trees_" + kind)
            me.vertices.add(len(pts))
            me.vertices.foreach_set("co", pts.astype(np.float64).ravel())
            ob = bpy.data.objects.new("trees_" + kind, me)
            bpy.context.scene.collection.objects.link(ob)
            _instance(ob, kind)
    # ground beyond the frame, so the horizon isn't the sky's dark underside (it read as a sea)
    span = float(d["span"]) if "span" in d.files else 4000.0
    # a ring round the frame, never under it (a plane at the edge's height cut through a canyon and hid a valley's floor)
    # its inner edge is the frame's own edge (heights and all) sloping out to the far ground, so there's no gap to see
    # through where the frame's edge stands above it
    z0 = float(d["base"]) - 1 if "base" in d.files else 0.0
    V = d["verts"]
    nx = int(np.sum(V[:, 1] == V[0, 1]))
    ny = len(V) // nx
    g = np.arange(len(V)).reshape(ny, nx)
    loop = np.r_[g[0, :], g[1:, -1], g[-1, -2::-1], g[-2:0:-1, 0]]  # the boundary, anticlockwise
    inner = V[loop].astype(float)
    cx, cy = V[:, 0].mean(), V[:, 1].mean()
    out_d = inner[:, :2] - [cx, cy]
    far = np.c_[[cx, cy] + out_d / np.maximum(np.abs(out_d).max(1, keepdims=True), 1e-9) * 20 * span, np.full(len(loop), z0)]
    # the frame's edge carries on level for a while (a plateau stays a plateau, a valley floor a floor), then eases down
    def wrap_mean(a, k):  # a moving average round the loop (Blender's Python has no scipy)
        pad = np.concatenate([a[-k:], a, a[:k]])
        c = np.cumsum(np.concatenate([np.zeros((1,) + a.shape[1:]), pad]), axis=0)
        return (c[2 * k + 1:] - c[:-2 * k - 1]) / (2 * k + 1)

    mid = np.c_[[cx, cy] + out_d * 1.6, wrap_mean(inner[:, 2], 12)]
    verts_b = np.vstack([inner, mid, far])
    n = len(loop)
    tris = []
    for k in range(n):
        a, b = k, (k + 1) % n
        for off in (0, n):
            tris += [(off + a, off + n + a, off + n + b), (off + a, off + n + b, off + b)]
    if "sea" in d.files and np.isfinite(float(d["sea"])):  # the sea runs on flat past the frame (moved to its level below)
        verts_b[:, 2] = z0
    ecol = d["colors"][loop]
    soft = wrap_mean(ecol.astype(float), 30)  # (edge colours stretched out radially streaked)
    cols_b = np.vstack([ecol, soft, np.repeat(ecol.mean(0, keepdims=True), len(loop), 0)])
    plane = _mesh("beyond", verts_b, np.array(tris), cols_b)
    plane.data.polygons.foreach_set("use_smooth", [False] * len(plane.data.polygons))  # (long thin fans streaked)
    pm = bpy.data.materials.new("beyond")
    pm.use_nodes = True
    sea = float(d["sea"]) if "sea" in d.files else float("nan")
    b = pm.node_tree.nodes["Principled BSDF"]
    if np.isfinite(sea):  # a sea runs on past the frame: the plane is water at its level
        plane.location.z = sea - 0.3 - (float(d["base"]) - 1)  # (coincident with the water mesh, both rendered black)
        b.inputs["Base Color"].default_value = (0.07, 0.17, 0.2, 1)
        b.inputs["Roughness"].default_value = 0.08
    else:  # the edge's own colours carried out
        at = pm.node_tree.nodes.new("ShaderNodeAttribute")
        at.attribute_name = "col"
        pm.node_tree.links.new(at.outputs["Color"], b.inputs["Base Color"])
        b.inputs["Roughness"].default_value = 0.9
    plane.data.materials.append(pm)
    if "markers" in d.files and len(d["markers"]):  # sites as thin red poles, to judge what a view sees
        mk = bpy.data.materials.new("marker")
        mk.use_nodes = True
        mk.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.8, 0.05, 0.03, 1)
        eyes = [v["eye"] for v in job["views"]]
        for x, y, z in d["markers"]:
            # (not where a camera stands: a view from a site's centre was inside its pole, all black)
            if any((x - e[0]) ** 2 + (y - e[1]) ** 2 < 4.0 ** 2 for e in eyes):
                continue
            bpy.ops.mesh.primitive_cylinder_add(vertices=6, radius=0.6, depth=12, location=(float(x), float(y), float(z) + 6))
            bpy.context.object.data.materials.append(mk)
    if "props" in d.files and len(d["props"]):  # sites carrying a prop: a small stand-in at its real size
        pk = bpy.data.materials.new("prop")
        pk.use_nodes = True
        pk.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.9, 0.55, 0.02, 1)
        gm = bpy.data.materials.new("prop_metal")
        gm.use_nodes = True
        gm.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.55, 0.55, 0.58, 1)
        for (x, y, z, yaw), nm in zip(d["props"], d["prop_names"]):
            x, y, z = float(x), float(y), float(z)
            if "basket" in str(nm):  # a disc golf target: post, basket dish, chain band, yellow top band
                bpy.ops.mesh.primitive_cylinder_add(vertices=8, radius=0.03, depth=1.45, location=(x, y, z + 0.72))
                bpy.context.object.data.materials.append(gm)
                bpy.ops.mesh.primitive_cylinder_add(vertices=16, radius=0.33, depth=0.22, location=(x, y, z + 0.72))
                bpy.context.object.data.materials.append(gm)
                bpy.ops.mesh.primitive_cylinder_add(vertices=16, radius=0.28, depth=0.5, location=(x, y, z + 1.08))
                bpy.context.object.data.materials.append(gm)
                bpy.ops.mesh.primitive_cylinder_add(vertices=16, radius=0.31, depth=0.1, location=(x, y, z + 1.38))
                bpy.context.object.data.materials.append(pk)
            elif "tee" in str(nm):  # a tee pad: a flat slab 1.5 x 3 m, long side toward the basket
                bpy.ops.mesh.primitive_cube_add(size=1, location=(x, y, z + 0.03))
                o = bpy.context.object
                o.scale = (1.5, 3.0, 0.1)
                o.rotation_euler[2] = -math.radians(float(yaw))
                o.data.materials.append(gm)
            else:  # anything else: a small orange post
                bpy.ops.mesh.primitive_cylinder_add(vertices=6, radius=0.1, depth=1.2, location=(x, y, z + 0.6))
                bpy.context.object.data.materials.append(pk)
    if len(d["wfaces"]):
        water = _mesh("water", d["wverts"], d["wfaces"])
        wm = bpy.data.materials.new("water")
        wm.use_nodes = True
        b = wm.node_tree.nodes["Principled BSDF"]
        b.inputs["Base Color"].default_value = (0.07, 0.17, 0.2, 1)  # water scatters light back up (darker read as black from above)
        b.inputs["Roughness"].default_value = 0.25
        # a light swell: noise bump on the normal (a dead-flat surface was a perfect mirror)
        nt = wm.node_tree
        tc = nt.nodes.new("ShaderNodeTexCoord")
        mp = nt.nodes.new("ShaderNodeMapping")
        mp.inputs["Scale"].default_value = (0.25, 0.6, 0.25)  # (in metres: ripples ~4 m long; 30 m swells were too gentle to show)
        nz = nt.nodes.new("ShaderNodeTexNoise")
        nz.inputs["Scale"].default_value = 1.0
        nz.inputs["Detail"].default_value = 6.0
        bp = nt.nodes.new("ShaderNodeBump")
        bp.inputs["Strength"].default_value = 1.0
        bp.inputs["Distance"].default_value = 0.4
        nt.links.new(tc.outputs["Object"], mp.inputs["Vector"])
        nt.links.new(mp.outputs["Vector"], nz.inputs["Vector"])
        nt.links.new(nz.outputs["Fac"], bp.inputs["Height"])
        nt.links.new(bp.outputs["Normal"], b.inputs["Normal"])
        water.data.materials.append(wm)

    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.samples = job.get("samples", 24)
    scene.cycles.use_denoising = True
    scene.render.resolution_x, scene.render.resolution_y = job["size"]
    scene.view_settings.view_transform = "AgX"
    world = bpy.data.worlds.new("sky")
    scene.world = world
    world.use_nodes = True
    sky = world.node_tree.nodes.new("ShaderNodeTexSky")
    world.node_tree.links.new(sky.outputs["Color"], world.node_tree.nodes["Background"].inputs["Color"])
    world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.12
    sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN"))
    sun.data.energy = 2.2
    sun.data.angle = 0.02
    scene.collection.objects.link(sun)
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
    span = float(np.ptp(d["verts"][:, :2], axis=0).max())
    cam.data.clip_start, cam.data.clip_end = max(0.05, span / 20000), span * 5
    scene.collection.objects.link(cam)
    scene.camera = cam
    for v in job["views"]:
        cam.location = Vector(v["eye"])
        cam.rotation_euler = (Vector(v["look"]) - Vector(v["eye"])).to_track_quat("-Z", "Y").to_euler()
        cam.data.angle = np.radians(v["fov"])
        b, h = np.radians(v.get("sun", (225, 28)))  # where the sun is: compass bearing, height (terrain_sun picks it)
        toward = Vector((np.cos(h) * np.sin(b), np.cos(h) * np.cos(b), np.sin(h)))
        sun.rotation_euler = (-toward).to_track_quat("-Z", "Y").to_euler()
        sky.sun_elevation, sky.sun_rotation = h, -b  # the sky's glow on the sun's side (Nishita: rotation 0 = north)
        scene.render.filepath = v["out"]
        bpy.ops.render.render(write_still=True)


run(json.load(open(sys.argv[sys.argv.index("--") + 1])))
