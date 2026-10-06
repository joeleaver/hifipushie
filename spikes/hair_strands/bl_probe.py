"""Run inside Blender: where the Essentials hair node groups are, and each group's inputs."""
import glob
import os
import bpy

root = os.path.dirname(bpy.app.binary_path)
print("@@ version", bpy.app.version_string, root)
files = glob.glob(os.path.join(bpy.utils.system_resource("DATAFILES"), "assets", "**", "*.blend"), recursive=True)
for f in files:
    print("@@ file", f, os.path.getsize(f) // 1024, "kB")
hair = [f for f in files if "hair" in os.path.basename(f).lower()]
for f in hair:
    with bpy.data.libraries.load(f) as (src, dst):
        dst.node_groups = list(src.node_groups)
    for ng in dst.node_groups:
        if ng is None or not ng.asset_data:
            continue
        ins = [(i.name, i.socket_type.replace("NodeSocket", ""), getattr(i, "default_value", None))
               for i in ng.interface.items_tree if i.item_type == "SOCKET" and i.in_out == "INPUT"]
        print("@@ group", ng.name, "|", "; ".join(f"{n}:{t}" for n, t, d in ins))
