"""Runs inside headless Blender: load a mesh, render clay views with orthographic cameras.

Invoked as: blender -b --factory-startup --python blender_render.py -- job.json
or, kept running: ... -- --serve, reading one job path per line on stdin and answering "@@done" or
"@@error <message>" on stdout (saves Blender's startup on every look).
Job: {"mesh": "x.npz", "size": 512, "matcap": "...", "views": [
        {"name": "front", "dir": [0,-1,0], "up": [0,0,1], "center": [...], "scale": 1.2, "out": "front.png"}]}
"dir" points from the target toward the camera.
"""

import json
import sys

import bpy
import numpy as np
from mathutils import Matrix, Vector


def run(job):
    for coll in (bpy.data.objects, bpy.data.meshes, bpy.data.cameras):
        for item in list(coll):
            coll.remove(item)
    data = np.load(job["mesh"])
    verts, faces = data["verts"], data["faces"]

    me = bpy.data.meshes.new("creature")
    me.vertices.add(len(verts))
    me.vertices.foreach_set("co", verts.ravel())
    me.loops.add(faces.size)
    me.loops.foreach_set("vertex_index", faces.ravel())
    me.polygons.add(len(faces))
    me.polygons.foreach_set("loop_start", np.arange(0, faces.size, 3, dtype=np.int32))
    me.update()
    me.shade_smooth()
    if "normals" in data:  # exact field normals: shading doesn't show the voxel grid
        me.normals_split_custom_set_from_vertices(data["normals"].astype(np.float64))
    colors = data["colors"] if "colors" in data else (data["part_colors"] if "part_colors" in data else None)
    if colors is not None:  # the curvature view, or a clay colour per part
        colors = colors.astype(np.float64)
        if "colors" not in data:  # part/paint colours are sRGB, as picked; the attribute is linear
            rgb = colors[:, :3]
            colors[:, :3] = np.where(rgb <= 0.04045, rgb / 12.92, ((rgb + 0.055) / 1.055) ** 2.4)
        attr = me.color_attributes.new("col", "FLOAT_COLOR", "POINT")
        attr.data.foreach_set("color", colors.astype(np.float32).ravel())
    ob = bpy.data.objects.new("creature", me)
    bpy.context.scene.collection.objects.link(ob)

    scene = bpy.context.scene
    scene.render.engine = "BLENDER_WORKBENCH"
    scene.render.resolution_x = scene.render.resolution_y = job.get("size", 512)
    scene.render.film_transparent = False
    sh = scene.display.shading
    sh.light = "MATCAP"
    matcap = job.get("matcap", "clay_studio.exr")
    custom = None
    if "/" in matcap:  # a matcap image of our own (e.g. the raking light), not one Blender ships
        custom = bpy.context.preferences.studio_lights.load(matcap, "MATCAP")
        matcap = custom.name
    sh.studio_light = matcap
    sh.color_type = "SINGLE"
    if colors is not None:
        sh.color_type = "VERTEX"
    if "colors" in data:
        sh.light = "STUDIO"
    if job.get("flat"):  # unlit colour, to judge paint
        sh.light = "FLAT"
    sh.show_cavity = job.get("cavity", True) and not job.get("flat")
    sh.cavity_type = "BOTH"
    sh.show_object_outline = True
    scene.world = scene.world or bpy.data.worlds.new("w")
    scene.world.color = (0.22, 0.23, 0.26)
    scene.display_settings.display_device = "sRGB"
    scene.view_settings.view_transform = "Standard"

    cam_data = bpy.data.cameras.new("cam")
    cam_data.type = "ORTHO"
    cam_data.clip_start, cam_data.clip_end = 0.001, 1000
    cam = bpy.data.objects.new("cam", cam_data)
    scene.collection.objects.link(cam)
    scene.camera = cam

    for v in job["views"]:
        d = Vector(v["dir"]).normalized()
        up = Vector(v["up"])
        right = up.cross(d).normalized()  # camera looks along -d
        up = d.cross(right).normalized()
        center = Vector(v["center"])
        rot = Matrix((right, up, d)).transposed()
        cam.matrix_world = Matrix.Translation(center + d * 50) @ rot.to_4x4()
        cam_data.ortho_scale = v["scale"]
        scene.render.filepath = v["out"]
        bpy.ops.render.render(write_still=True)
    if custom is not None:
        bpy.context.preferences.studio_lights.remove(custom)


args = sys.argv[sys.argv.index("--") + 1:]
if args and args[0] == "--serve":
    import traceback
    for line in sys.stdin:
        path = line.strip()
        if not path:
            continue
        try:
            run(json.load(open(path)))
            print("@@done", flush=True)
        except Exception as e:  # keep serving; the caller reports it
            traceback.print_exc()
            print("@@error " + repr(e).replace("\n", " "), flush=True)
else:
    run(json.load(open(args[0])))
