"""Artist retopo, step 3c (Blender): put the repaired maps into low_uv.glb -> final.glb; render the sculpt beside it.
    blender -b --factory-startup --python blender_artretopo_assemble.py -- job.json
job: dir, centre / scale (whole figure), head / head_scale (the head close-up).
Writes final.glb and fin_{body,head,back}_{high,final}.png.

GOTCHA: a glTF import PACKS its images; reloading one only reloads the packed copy. Load the file and SWAP it into
every image node that used the old one."""
import os
import sys

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import blender_artretopo_common as C  # noqa: E402

J = C.job(); D = J["dir"]
sc = C.reset()
bpy.ops.import_scene.gltf(filepath=f"{D}/low_uv.glb")
swapped = 0
for img in list(bpy.data.images):
    n = img.name.rsplit(".", 1)[0]
    for k in ("normal", "color"):
        if n == k or n.endswith("_" + k):
            tag = "low" if n in (k, f"low_{k}") else n[: -len(k) - 1]
            p = f"{D}/{k}.png" if tag == "low" else f"{D}/{tag}_{k}.png"
            if os.path.exists(p):
                new = bpy.data.images.load(p, check_existing=False)
                if k == "normal":
                    new.colorspace_settings.name = "Non-Color"
                new.pack()
                for m in bpy.data.materials:
                    if m.node_tree:
                        for nd in m.node_tree.nodes:
                            if nd.type == "TEX_IMAGE" and nd.image == img:
                                nd.image = new
                swapped += 1
print("SWAPPED", swapped)
bpy.ops.export_scene.gltf(filepath=f"{D}/final.glb", export_format="GLB")
parts = [o for o in sc.objects if o.type == "MESH" and not o.name.startswith("lod")]
for o in sc.objects:
    if o.type == "MESH" and o.name.startswith("lod"):
        o.hide_render = True
hi = C.load_ply(f"{D}/high.ply", "high")
hi.data.materials.append(C.vertex_colour_material("hv", hi.data.color_attributes[0].name))
sc.render.engine = "CYCLES"; sc.cycles.device = "CPU"; sc.cycles.samples = 24
sc.render.resolution_x = sc.render.resolution_y = 700
C.sun_world(sc)
cam = C.ortho_camera(sc, J["scale"])
back_c = list(J["centre"])
for vn, d, T, s_ in (("body", (-0.8, -1, 0.4), J["centre"], J["scale"]), ("head", (-0.6, -1, 0.25), J["head"], J["head_scale"]),
                     ("back", (0.7, 1, 0.3), back_c, J["scale"] * 0.87)):
    cam.data.ortho_scale = s_; C.aim(cam, T, d)
    for tag, shown in (("high", [hi]), ("final", parts)):
        for o in sc.objects:
            if o.type == "MESH" and not o.name.startswith("lod"):
                o.hide_render = o not in shown
        sc.render.filepath = f"{D}/fin_{vn}_{tag}.png"; bpy.ops.render.render(write_still=True)
print("ASSEMBLED")
