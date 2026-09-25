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


def run(job):
    for coll in (bpy.data.objects, bpy.data.meshes, bpy.data.cameras, bpy.data.lights):
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
    cam.data.clip_start, cam.data.clip_end = 1, 20000
    scene.collection.objects.link(cam)
    scene.camera = cam
    for v in job["views"]:
        cam.location = Vector(v["eye"])
        cam.rotation_euler = (Vector(v["look"]) - Vector(v["eye"])).to_track_quat("-Z", "Y").to_euler()
        cam.data.angle = np.radians(v["fov"])
        scene.render.filepath = v["out"]
        bpy.ops.render.render(write_still=True)


run(json.load(open(sys.argv[sys.argv.index("--") + 1])))
