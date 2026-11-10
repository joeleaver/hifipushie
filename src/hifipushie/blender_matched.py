"""blender -b --factory-startup --python blender_matched.py -- <job.json>
The matched render (matched.render): a mesh npz from a fitted concept camera at the image's own size, in
form-revealing clay: big area lights (key above-front-left of the camera, fill, rim) and a soft world, so creases,
necks and stalks read as form, not as black. Job: the camera json (az, el, roll, f_px, aim, dist, size) + mesh,
out, samples, colour, extent (the model's largest size, which scales the lights)."""
import json
import math
import sys

import bpy
import numpy as np
from mathutils import Matrix, Vector

job = json.load(open(sys.argv[sys.argv.index("--") + 1]))
bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene

data = np.load(job["mesh"])
verts, faces = data["verts"], data["faces"]
me = bpy.data.meshes.new("model")
me.vertices.add(len(verts))
me.vertices.foreach_set("co", verts.astype(np.float32).ravel())
me.loops.add(faces.size)
me.loops.foreach_set("vertex_index", faces.astype(np.int32).ravel())
me.polygons.add(len(faces))
me.polygons.foreach_set("loop_start", np.arange(0, faces.size, 3, dtype=np.int32))
me.polygons.foreach_set("loop_total", np.full(len(faces), 3, dtype=np.int32))
me.update()
me.shade_smooth()
if "normals" in data:
    me.normals_split_custom_set_from_vertices(data["normals"].astype(np.float64))
ob = bpy.data.objects.new("model", me)
sc.collection.objects.link(ob)
m = bpy.data.materials.new("clay")
m.use_nodes = True
b = m.node_tree.nodes["Principled BSDF"]
b.inputs["Base Color"].default_value = (*job["colour"], 1)
b.inputs["Roughness"].default_value = 0.8
me.materials.append(m)

# the camera: the same frame as matched.axes
a, e, r = (math.radians(job[k]) for k in ("az", "el", "roll"))
D = Vector((math.sin(a) * math.cos(e), -math.cos(a) * math.cos(e), math.sin(e)))
aim = Vector(job["aim"])
C = aim + job["dist"] * D
Fw = -D
Rv = Fw.cross(Vector((0, 0, 1))).normalized()
Uv = Rv.cross(Fw)
Rr = math.cos(r) * Rv + math.sin(r) * Uv
Ur = -math.sin(r) * Rv + math.cos(r) * Uv
cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
sc.collection.objects.link(cam)
sc.camera = cam
cam.matrix_world = Matrix.Translation(C) @ Matrix((Rr, Ur, -Fw)).transposed().to_4x4()
W, H = job["size"]
cam.data.sensor_fit = "HORIZONTAL" if W >= H else "VERTICAL"
cam.data.sensor_width = cam.data.sensor_height = 36.0
cam.data.lens = job["f_px"] * 36.0 / (W if W >= H else H)
cam.data.clip_start, cam.data.clip_end = 0.01, 10 * job["dist"]
sc.render.resolution_x, sc.render.resolution_y = W, H

# lights in the camera's frame, scaled to the model (Puddles, 0.8 m: the prototype's studio)
k = job["extent"] / 0.8
for (x, y, z), energy, size in (((-1.6, 1.0, 1.9), 110, 3.0), ((1.6, 0.6, 0.4), 30, 3.0), ((0.4, -2.6, 1.6), 70, 2.0)):
    loc = aim + k * (x * Rr + z * Uv + y * D)
    L = bpy.data.objects.new("l", bpy.data.lights.new("l", "AREA"))
    L.data.energy, L.data.size = energy * k * k, size * k
    sc.collection.objects.link(L)
    L.location = loc
    L.rotation_euler = (aim - loc).to_track_quat("-Z", "Y").to_euler()
sc.world = bpy.data.worlds.new("w")  # a dim grey world lights the model; camera rays see a light backdrop
sc.world.use_nodes = True
nt = sc.world.node_tree
bg = nt.nodes["Background"]
bg.inputs[0].default_value = (0.9, 0.9, 0.92, 1)
bg.inputs[1].default_value = 0.25
seen = nt.nodes.new("ShaderNodeBackground")
seen.inputs[0].default_value = (0.75, 0.75, 0.77, 1)
mix = nt.nodes.new("ShaderNodeMixShader")
path = nt.nodes.new("ShaderNodeLightPath")
nt.links.new(path.outputs["Is Camera Ray"], mix.inputs[0])
nt.links.new(bg.outputs[0], mix.inputs[1])
nt.links.new(seen.outputs[0], mix.inputs[2])
nt.links.new(mix.outputs[0], nt.nodes["World Output"].inputs[0])
sc.render.engine = "CYCLES"
sc.cycles.samples = int(job["samples"])
sc.cycles.use_denoising = True
sc.render.film_transparent = False
sc.render.filepath = job["out"]
bpy.ops.render.render(write_still=True)
