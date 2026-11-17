"""Artist retopo: orthographic looks at one mesh (Blender workbench), for studying a sculpt and checking a cage.
    blender -b --factory-startup --python blender_artretopo_look.py -- job.json
job: mesh (a .ply or .glb), over (optional: a cage .ply drawn as a red wire over the mesh), style ("colour": vertex
colours / textures, "flat": textures unlit (the maps alone, as flat.py), "clay", "wire": clay + a dark wire), red
(optional: face indices drawn red: folds from the press), views, centre, scale, res, out (prefix: <out>_<view>.png)."""
import os
import sys

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import blender_artretopo_common as C  # noqa: E402

J = C.job()
sc = C.reset()
if J["mesh"].endswith(".glb"):
    bpy.ops.import_scene.gltf(filepath=J["mesh"]); objs = [o for o in sc.objects if o.type == "MESH" and not o.name.startswith("lod")]
    for o in sc.objects:
        if o.type == "MESH" and o.name.startswith("lod"):
            o.hide_render = True
else:
    objs = [C.load_ply(J["mesh"], "mesh")]
style = J.get("style", "colour"); S = J["scale"]
tex = style in ("colour", "flat")
colour = "MATERIAL" if not tex else ("TEXTURE" if J["mesh"].endswith(".glb") else "VERTEX")
sh = C.workbench(sc, J.get("res", 768), colour=colour, light="FLAT" if style == "flat" else "STUDIO",
                 bg=(0.3, 0.3, 0.3) if style == "flat" else (1, 1, 1))
sh.show_cavity = not tex
if not tex:
    for o in objs:
        o.data.materials.clear(); o.data.materials.append(C.flat_mat("clay", (0.86, 0.84, 0.80, 1)))
    if J.get("red"):
        o = objs[0]; o.data.materials.append(C.flat_mat("red", (0.9, 0.1, 0.1, 1)))
        for i in J["red"]:
            if i < len(o.data.polygons):
                o.data.polygons[i].material_index = 1
if style == "wire":
    for o in objs:
        C.wire_copy(sc, o, 0.0012 * S / 1.1, (0.1, 0.1, 0.12, 1))
if J.get("over"):
    cg = C.load_ply(J["over"], "over"); cg.hide_render = True
    C.wire_copy(sc, cg, 0.004 * S / 1.1, (0.85, 0.2, 0.1, 1))
cam = C.ortho_camera(sc, S)
for vn in J["views"]:
    C.aim(cam, J["centre"], C.VIEWS[vn])
    sc.render.filepath = f"{J['out']}_{vn}.png"; bpy.ops.render.render(write_still=True)
