"""Artist retopo: the sculpt beside the result, rendered alike (Cycles, sun + sky, orthographic).
    blender -b --factory-startup --python blender_artretopo_compare.py -- job.json
job: dir, result (final.glb | rigged.glb | lod1_rigged.glb | low.ply ...), views [{name, view: [dx, dy, dz], target,
scale}], res, samples. Writes fin_<name>_high.png and fin_<name>_final.png per view."""
import os
import sys

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import blender_artretopo_common as C  # noqa: E402

J = C.job(); D = J["dir"]
sc = C.reset()
res = J.get("result", "final.glb")
if res.endswith(".glb"):
    bpy.ops.import_scene.gltf(filepath=f"{D}/{res}")
    parts = [o for o in sc.objects if o.type == "MESH" and (res.startswith("lod1") or not o.name.startswith("lod"))]
else:
    parts = [C.load_ply(f"{D}/{res}", "result")]
    parts[0].data.materials.append(C.flat_mat("clay", (0.8, 0.78, 0.75, 1)))
for o in sc.objects:
    if o.type == "MESH" and o not in parts:
        o.hide_render = True
hi = C.load_ply(f"{D}/high.ply", "high")
hi.data.materials.append(C.vertex_colour_material("hv", hi.data.color_attributes[0].name))
sc.render.engine = "CYCLES"; sc.cycles.device = "CPU"; sc.cycles.samples = J.get("samples", 24)
sc.render.resolution_x = sc.render.resolution_y = J.get("res", 700)
C.sun_world(sc)
cam = C.ortho_camera(sc, 1.0)
for v in J["views"]:
    cam.data.ortho_scale = v["scale"]; C.aim(cam, v["target"], v["view"])
    for tag, shown in (("high", [hi]), ("final", parts)):
        for o in sc.objects:
            if o.type == "MESH" and (o in parts or o is hi):
                o.hide_render = o not in shown
        sc.render.filepath = f"{D}/fin_{v['name']}_{tag}.png"; bpy.ops.render.render(write_still=True)
print("COMPARED")
