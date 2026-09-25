"""Runs inside headless Blender: a terrain grid mesh (vertex colours) and its lakes, rendered in Cycles
under a low sun and sky from perspective cameras. Job: {"mesh", "size": [w, h], "samples",
"views": [{"eye": [x, y, z], "look": [x, y, z], "fov": deg, "out": png}]}."""

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
    ground.data.materials.append(m)
    kinds = [k[len("trees_"):] for k in d.files if k.startswith("trees_")]
    for k in kinds:
        a = ground.data.attributes.new("trees_" + k, "FLOAT", "POINT")
        a.data.foreach_set("value", d["trees_" + k].astype(np.float32))
    if kinds:
        _scatter(ground, kinds)
    if len(d["wfaces"]):
        water = _mesh("water", d["wverts"], d["wfaces"])
        wm = bpy.data.materials.new("water")
        wm.use_nodes = True
        b = wm.node_tree.nodes["Principled BSDF"]
        b.inputs["Base Color"].default_value = (0.02, 0.05, 0.07, 1)
        b.inputs["Roughness"].default_value = 0.05
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
    sun.rotation_euler = (np.radians(62), 0, np.radians(-35))  # low, from the south-west
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
        scene.render.filepath = v["out"]
        bpy.ops.render.render(write_still=True)


run(json.load(open(sys.argv[sys.argv.index("--") + 1])))
