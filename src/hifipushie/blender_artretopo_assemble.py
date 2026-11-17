"""Artist retopo, step 3c (Blender): put the repaired maps into low_uv.glb -> final.glb (blender_artretopo_compare.py
renders it beside the sculpt).
    blender -b --factory-startup --python blender_artretopo_assemble.py -- job.json
job: dir.

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
print("ASSEMBLED")
