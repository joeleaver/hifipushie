"""Blender script (blender -b -P raw_blender.py -- <mesh.npz> <out dir> <size>): RAW GNM as a plain-material mesh,
EEVEE, the ladder's three eye close-ups (front, three-quarter, side). mesh.npz: verts (GNM frame: x left, y up, z
forward), quads, mat (per quad: 0 skin, 1 sclera, 2 iris, 3 pupil), eyes (2, 3) centres, r."""
import sys

import bpy
import numpy as np
from mathutils import Vector

npz, out, size = sys.argv[sys.argv.index("--") + 1:][:3]
z = np.load(npz)
V, Q, M = z["verts"], z["quads"], z["mat"]
eyes, r = z["eyes"], float(z["r"])
bpy.ops.wm.read_factory_settings(use_empty=True)
me = bpy.data.meshes.new("gnm")
P = np.c_[V[:, 0], -V[:, 2], V[:, 1]]  # -> Blender: z up, facing -y, the head's left +x
me.from_pydata(P.tolist(), [], Q.tolist())
for name, col, rough in (("skin", (0.78, 0.6, 0.5, 1), 0.55), ("sclera", (0.92, 0.9, 0.87, 1), 0.25), ("iris", (0.3, 0.25, 0.15, 1), 0.3),
                         ("pupil", (0.01, 0.01, 0.01, 1), 0.3)):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = col
    b.inputs["Roughness"].default_value = rough
    me.materials.append(m)
me.polygons.foreach_set("material_index", M.astype(int).tolist())
me.polygons.foreach_set("use_smooth", [True] * len(Q))
me.update()
ob = bpy.data.objects.new("gnm", me)
bpy.context.scene.collection.objects.link(ob)
sc = bpy.context.scene
for eng in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE"):
    try:
        sc.render.engine = eng
        break
    except TypeError:
        pass
sc.render.resolution_x = sc.render.resolution_y = int(size)
sc.render.film_transparent = False
w = bpy.data.worlds.new("w")
w.use_nodes = True
w.node_tree.nodes["Background"].inputs[0].default_value = (0.8, 0.8, 0.8, 1)
w.node_tree.nodes["Background"].inputs[1].default_value = 0.6
sc.world = w
sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN"))
sun.data.energy = 3.0
sun.data.angle = 0.6
sun.rotation_euler = (np.radians(48), 0, np.radians(8))
sc.collection.objects.link(sun)
cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
sc.collection.objects.link(cam)
sc.camera = cam
E = np.c_[eyes[:, 0], -eyes[:, 2], eyes[:, 1]]
left = E[np.argmax(E[:, 0])]
mid = E.mean(0)
fwd = np.array([0.0, -1.0, 0.0])
for name, target, d, dist, fov in (("eyes_front", mid + fwd * r, [0.0, -1.0, 0.0], 0.9, 6.5), ("eyes_34", mid + fwd * r, [0.62, -0.75, -0.12], 0.9, 6.5),
                                   ("eye_side", left + fwd * 0.6 * r, [1.0, -0.12, 0.0], 0.6, 5.2)):
    d = np.asarray(d, float) / np.linalg.norm(d)
    cam.location = Vector((target + d * dist).tolist())
    cam.rotation_euler = (Vector(target.tolist()) - cam.location).to_track_quat("-Z", "Y").to_euler()
    cam.data.angle = np.radians(fov)
    cam.data.clip_start = 0.05
    sc.render.filepath = f"{out}/{name}.png"
    bpy.ops.render.render(write_still=True)
    print("wrote", sc.render.filepath)
