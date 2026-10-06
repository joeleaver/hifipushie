"""blender -b --factory-startup --python groom_check.py -- <dir> <name>: the exported groom read back by Blender's
own Alembic and USD importers: curves, points, size, attributes."""
import bpy, sys, json
d, name = sys.argv[sys.argv.index("--") + 1:]
out = {}
for ext, op in (("abc", lambda p: bpy.ops.wm.alembic_import(filepath=p)), ("usdc", lambda p: bpy.ops.wm.usd_import(filepath=p))):
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    op(f"{d}/{name}_groom.{ext}")
    r = []
    for ob in bpy.data.objects:
        dg = bpy.context.evaluated_depsgraph_get()
        dat = ob.evaluated_get(dg).data
        if ob.type == "CURVES":
            r.append({"type": ob.type, "curves": len(dat.curves), "points": len(dat.points),
                      "dims": [round(x, 3) for x in ob.dimensions],
                      "attrs": sorted(a.name for a in dat.attributes if not a.name.startswith("."))})
        else:
            r.append({"type": ob.type, "name": ob.name})
    out[ext] = r
print("@@", json.dumps(out))
