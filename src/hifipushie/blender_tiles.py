"""Runs inside headless Blender: terrain tiles reassembled through Blender's own glTF importer (not our meshes), under a
sky and sun, with the sea as a plane, trees from trees.csv, and optionally the tile borders drawn as red lines.
Job: {"glbs": [paths], "sea": level | null, "trees": csv | null, "borders": npz (segs (m, 2, 3)) | null,
"size": [w, h], "samples", "views": [{"eye", "look", "fov", "sun": [bearing, height], "borders": bool, "out"}]}."""
import csv
import json
import math
import os
import sys

import bpy
import numpy as np
from mathutils import Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import blender_terrain as bt  # noqa: E402  (tree builders)


def _terrain_material():
    m = bpy.data.materials.new("terrain")
    m.use_nodes = True
    nt = m.node_tree
    b = nt.nodes["Principled BSDF"]
    at = nt.nodes.new("ShaderNodeAttribute")
    at.attribute_name = "Color"  # COLOR_0 as the importer names it
    nt.links.new(at.outputs["Color"], b.inputs["Base Color"])
    b.inputs["Roughness"].default_value = 0.92
    for k in ("Specular IOR Level", "Specular"):
        if k in b.inputs:
            b.inputs[k].default_value = 0.12
    return m


def _flat(name, rgb):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*rgb, 1)
    b.inputs["Emission Color"].default_value = (*rgb, 1)
    b.inputs["Emission Strength"].default_value = 1.5
    return m


def _water(level):
    bpy.ops.mesh.primitive_plane_add(size=8000, location=(500, 400, level))
    w = bpy.context.object
    wm = bpy.data.materials.new("water")
    wm.use_nodes = True
    nt = wm.node_tree
    b = nt.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (0.05, 0.14, 0.17, 1)
    b.inputs["Roughness"].default_value = 0.2
    tc = nt.nodes.new("ShaderNodeTexCoord")
    mp = nt.nodes.new("ShaderNodeMapping")
    mp.inputs["Scale"].default_value = (0.25, 0.6, 0.25)
    nz = nt.nodes.new("ShaderNodeTexNoise")
    nz.inputs["Detail"].default_value = 6.0
    bp = nt.nodes.new("ShaderNodeBump")
    bp.inputs["Distance"].default_value = 0.4
    nt.links.new(tc.outputs["Object"], mp.inputs["Vector"])
    nt.links.new(mp.outputs["Vector"], nz.inputs["Vector"])
    nt.links.new(nz.outputs["Fac"], bp.inputs["Height"])
    nt.links.new(bp.outputs["Normal"], b.inputs["Normal"])
    w.data.materials.append(wm)
    return w


def _borders(segs, radius):
    me = bpy.data.meshes.new("borders")
    pts = segs.reshape(-1, 3)
    me.vertices.add(len(pts))
    me.vertices.foreach_set("co", pts.astype(np.float64).ravel())
    me.edges.add(len(segs))
    me.edges.foreach_set("vertices", np.arange(len(pts), dtype=np.int32))
    me.update()
    ob = bpy.data.objects.new("borders", me)
    bpy.context.scene.collection.objects.link(ob)
    bpy.context.view_layer.objects.active = ob
    ob.select_set(True)
    bpy.ops.object.convert(target="CURVE")
    ob.data.bevel_depth = radius
    ob.data.bevel_resolution = 1
    m = bpy.data.materials.new("border")
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (0.9, 0.05, 0.02, 1)
    b.inputs["Emission Color"].default_value = (1.0, 0.1, 0.03, 1)
    b.inputs["Emission Strength"].default_value = 2.0
    ob.data.materials.append(m)
    return ob


def run(job):
    for coll in (bpy.data.objects, bpy.data.meshes, bpy.data.cameras, bpy.data.lights, bpy.data.materials):
        for item in list(coll):
            coll.remove(item)
    mat = _terrain_material()
    ground = []
    for p in job["glbs"]:
        bpy.ops.import_scene.gltf(filepath=p)
        for ob in bpy.context.selected_objects:
            if ob.type == "MESH":
                if job.get("skirt_color"):  # skirts in their own flat colour, to see where they show
                    idx = np.zeros(len(ob.data.polygons), np.int32)
                    ob.data.polygons.foreach_get("material_index", idx)
                    ob.data.materials.clear()
                    ob.data.materials.append(mat)
                    ob.data.materials.append(_flat("skirt", job["skirt_color"]))
                    ob.data.polygons.foreach_set("material_index", idx)
                    ground.append(ob)
                    continue
                ob.data.materials.clear()
                ob.data.materials.append(mat)
                ground.append(ob)
    if job.get("sea") is not None:
        _water(job["sea"])
    if job.get("trees"):
        by = {}
        with open(job["trees"]) as f:
            for r in csv.DictReader(f):
                by.setdefault(r["kind"] or "broadleaf", []).append((float(r["x"]), float(r["y"]), float(r["z"])))
        box = job.get("tree_box")
        for kind, pts in by.items():
            pts = np.array(pts)
            if box:
                (x0, y0), (x1, y1) = box
                pts = pts[(pts[:, 0] >= x0) & (pts[:, 0] <= x1) & (pts[:, 1] >= y0) & (pts[:, 1] <= y1)]
            if not len(pts):
                continue
            me = bpy.data.meshes.new("trees_" + kind)
            me.vertices.add(len(pts))
            me.vertices.foreach_set("co", pts.astype(np.float64).ravel())
            ob = bpy.data.objects.new("trees_" + kind, me)
            bpy.context.scene.collection.objects.link(ob)
            bt._instance(ob, kind)
    border_ob = None
    if job.get("borders"):
        d = np.load(job["borders"])
        border_ob = _borders(d["segs"], job.get("border_radius", 0.35))
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.samples = job.get("samples", 32)
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
    sun.data.energy = 2.4
    sun.data.angle = 0.02
    scene.collection.objects.link(sun)
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
    cam.data.clip_start, cam.data.clip_end = 0.1, 8000
    scene.collection.objects.link(cam)
    scene.camera = cam
    for v in job["views"]:
        cam.location = Vector(v["eye"])
        cam.rotation_euler = (Vector(v["look"]) - Vector(v["eye"])).to_track_quat("-Z", "Y").to_euler()
        cam.data.angle = math.radians(v.get("fov", 55))
        b, h = [math.radians(x) for x in v.get("sun", (225, 30))]
        toward = Vector((math.cos(h) * math.sin(b), math.cos(h) * math.cos(b), math.sin(h)))
        sun.rotation_euler = (-toward).to_track_quat("-Z", "Y").to_euler()
        sky.sun_elevation, sky.sun_rotation = h, -b
        if border_ob is not None:
            border_ob.hide_render = not v.get("borders", False)
        scene.render.filepath = v["out"]
        bpy.ops.render.render(write_still=True)


if __name__ == "__main__":
    run(json.load(open(sys.argv[sys.argv.index("--") + 1])))
