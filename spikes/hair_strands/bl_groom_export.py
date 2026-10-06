"""Inside Blender: does the stock Alembic / USD exporter carry Unreal's groom_* attributes on Hair Curves?
blender -b --factory-startup --python bl_groom_export.py -- <out dir>"""
import os
import subprocess
import sys

import bpy
import numpy as np

out = sys.argv[sys.argv.index("--") + 1]
os.makedirs(out, exist_ok=True)
for ob in list(bpy.data.objects):
    bpy.data.objects.remove(ob)
cu = bpy.data.hair_curves.new("groom")
n, m = 12, 6
cu.add_curves([m] * n)
P = np.zeros((n, m, 3), np.float32)
P[..., 0] = np.arange(n)[:, None] * 0.01
P[..., 2] = np.linspace(0, 0.1, m)[None]
cu.attributes["position"].data.foreach_set("vector", P.ravel())
for name, dt, dom, vals in (("groom_guide", "INT", "CURVE", (np.arange(n) % 4 == 0).astype(np.int32)),
                            ("groom_id", "INT", "CURVE", np.arange(n, dtype=np.int32)),
                            ("groom_group_id", "INT", "CURVE", np.zeros(n, np.int32)),
                            ("groom_root_uv", "FLOAT2", "CURVE", np.random.rand(n, 2).astype(np.float32)),
                            ("groom_color", "FLOAT_COLOR", "POINT", np.tile([0.3, 0.2, 0.1, 1.0], (n * m, 1)).astype(np.float32)),
                            ("radius", "FLOAT", "POINT", np.full(n * m, 0.00008, np.float32))):
    at = cu.attributes.get(name) or cu.attributes.new(name, dt, dom)
    field = {"INT": "value", "FLOAT": "value", "FLOAT2": "vector", "FLOAT_COLOR": "color"}[dt]
    at.data.foreach_set(field, vals.ravel())
ob = bpy.data.objects.new("groom", cu)
ob["groom_version_major"], ob["groom_version_minor"] = 1, 5
bpy.context.scene.collection.objects.link(ob)
bpy.context.view_layer.objects.active = ob
ob.select_set(True)
abc, usd = os.path.join(out, "groom.abc"), os.path.join(out, "groom.usda")
for kw in ({"export_custom_properties": True}, {}):
    try:
        bpy.ops.wm.alembic_export(filepath=abc, selected=True, global_scale=100.0, **kw)
        print("@@ abc written", os.path.getsize(abc), kw)
        break
    except Exception as e:  # noqa: BLE001
        print("@@ abc failed", kw, repr(e))
try:
    bpy.ops.wm.usd_export(filepath=usd, selected_objects_only=True)
    print("@@ usd written", os.path.getsize(usd))
except Exception as e:  # noqa: BLE001
    print("@@ usd failed", repr(e))
s = subprocess.run(["strings", abc], capture_output=True, text=True).stdout
print("@@ abc strings with groom/width/uv:", sorted({w for w in s.split() if any(k in w.lower() for k in ("groom", "width", "uv", "radius"))})[:40])
if os.path.exists(usd):
    t = open(usd).read()
    print("@@ usda lines:", [ln.strip()[:110] for ln in t.splitlines() if any(k in ln for k in ("groom", "widths", "BasisCurves", "primvars", "curveVertexCounts", "type ="))][:30])
# read the Alembic back
for o in list(bpy.data.objects):
    bpy.data.objects.remove(o)
bpy.ops.wm.alembic_import(filepath=abc)
for o in bpy.data.objects:
    d = o.data
    print("@@ back", o.name, o.type, [(a.name, a.data_type, a.domain) for a in d.attributes] if hasattr(d, "attributes") else None)
