"""Blender side of lps.py: a scanned head (real geometry, photographed albedo, its normal map) path-traced through
given cameras, and the TRUE shading normals (normal map included) through the same cameras.
blender -b --factory-startup -P bl_scan.py -- <job.npz> <job.json> <out dir>"""
import json
import sys

import bpy
import numpy as np
from mathutils import Matrix, Vector

NPZ, JOB, OUT = sys.argv[sys.argv.index("--") + 1:][:3]
z = np.load(NPZ)
job = json.load(open(JOB))
sc = bpy.context.scene
for o in list(bpy.data.objects):
    bpy.data.objects.remove(o, do_unlink=True)
me = bpy.data.meshes.new("scan")
me.from_pydata([tuple(map(float, v)) for v in z["V"]], [], [tuple(map(int, f)) for f in z["F"]])
me.update()
for p in me.polygons:
    p.use_smooth = True
uvl = me.uv_layers.new(name="uv")
uv = z["uv"]
uvl.data.foreach_set("uv", uv[np.asarray([l.vertex_index for l in me.loops])].ravel().astype(np.float32))
ob = bpy.data.objects.new("scan", me)
sc.collection.objects.link(ob)


def tex(nt, path, raw=False):
    t = nt.nodes.new("ShaderNodeTexImage")
    t.image = bpy.data.images.load(path)
    if raw:
        t.image.colorspace_settings.name = "Non-Color"
    return t


skin = bpy.data.materials.new("skin")
skin.use_nodes = True
nt = skin.node_tree
b = nt.nodes["Principled BSDF"]
col = tex(nt, job["albedo"])
nrm = tex(nt, job["normal"], True)
spc = tex(nt, job["spec"], True)
nm = nt.nodes.new("ShaderNodeNormalMap")
nt.links.new(nrm.outputs["Color"], nm.inputs["Color"])
nt.links.new(col.outputs["Color"], b.inputs["Base Color"])
nt.links.new(nm.outputs["Normal"], b.inputs["Normal"])
rr = nt.nodes.new("ShaderNodeMapRange")
rr.inputs["To Min"].default_value = 0.62
rr.inputs["To Max"].default_value = 0.34
nt.links.new(spc.outputs["Color"], rr.inputs["Value"])
nt.links.new(rr.outputs["Result"], b.inputs["Roughness"])
b.inputs["Subsurface Weight"].default_value = 0.3
b.inputs["Subsurface Radius"].default_value = (1.0, 0.35, 0.2)
b.inputs["Subsurface Scale"].default_value = 0.005

truth = bpy.data.materials.new("truth")
truth.use_nodes = True
nt = truth.node_tree
for n in list(nt.nodes):
    nt.nodes.remove(n)
nrm2 = tex(nt, job["normal"], True)
nm2 = nt.nodes.new("ShaderNodeNormalMap")
nt.links.new(nrm2.outputs["Color"], nm2.inputs["Color"])
mad = nt.nodes.new("ShaderNodeVectorMath")
mad.operation = "MULTIPLY_ADD"
mad.inputs[1].default_value = (0.5, 0.5, 0.5)
mad.inputs[2].default_value = (0.5, 0.5, 0.5)
nt.links.new(nm2.outputs["Normal"], mad.inputs[0])
em = nt.nodes.new("ShaderNodeEmission")
nt.links.new(mad.outputs["Vector"], em.inputs["Color"])
out = nt.nodes.new("ShaderNodeOutputMaterial")
nt.links.new(em.outputs["Emission"], out.inputs["Surface"])
me.materials.append(skin)

cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
sc.collection.objects.link(cam)
cam.data.sensor_fit = "HORIZONTAL"
cam.data.sensor_width = 36.0
cam.data.clip_start, cam.data.clip_end = 0.05, 20.0
sc.camera = cam
sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN"))
sc.collection.objects.link(sun)
wd = bpy.data.worlds.new("w")
wd.use_nodes = True
wt = wd.node_tree
bg = wt.nodes["Background"]
lp = wt.nodes.new("ShaderNodeLightPath")
seen = wt.nodes.new("ShaderNodeBackground")
mix = wt.nodes.new("ShaderNodeMixShader")
wt.links.new(lp.outputs["Is Camera Ray"], mix.inputs["Fac"])
wt.links.new(bg.outputs["Background"], mix.inputs[1])
wt.links.new(seen.outputs["Background"], mix.inputs[2])
wt.links.new(mix.outputs["Shader"], wt.nodes["World Output"].inputs["Surface"])
sc.world = wd
sc.render.engine = "CYCLES"
sc.cycles.device = "CPU"
sc.cycles.use_denoising = False
sc.render.threads_mode = "FIXED"
sc.render.threads = 8
sc.render.image_settings.file_format = "PNG"
for v in job["views"]:
    cam.matrix_world = Matrix(v["M"])
    cam.data.lens = v["lens"]
    w, h = v["size"]
    sc.render.resolution_x, sc.render.resolution_y, sc.render.resolution_percentage = w, h, 100
    sun.rotation_euler = Vector(v["sun"]).to_track_quat("Z", "Y").to_euler()
    sun.data.energy = v["sun_w"]
    sun.data.angle = np.radians(v["soft"])
    bg.inputs["Color"].default_value = (0.85, 0.9, 1.0, 1.0)
    bg.inputs["Strength"].default_value = v["sky"]
    seen.inputs["Color"].default_value = (*v["back"], 1.0)
    me.materials[0] = skin
    sc.cycles.samples = 96
    sc.view_settings.view_transform = "Standard"
    sc.render.film_transparent = False
    sc.render.image_settings.color_depth = "8"
    sc.render.image_settings.color_mode = "RGB"
    sc.render.filepath = f"{OUT}/{v['id']}.png"
    bpy.ops.render.render(write_still=True)
    me.materials[0] = truth
    sc.cycles.samples = 8
    sc.view_settings.view_transform = "Raw"
    sc.render.film_transparent = True
    sc.render.image_settings.color_depth = "16"
    sc.render.image_settings.color_mode = "RGBA"
    sc.render.filepath = f"{OUT}/{v['id']}_truth.png"
    bpy.ops.render.render(write_still=True)
    print("rendered", v["id"], flush=True)
