"""Hard surface from the point cloud, inside Blender: the checks a game-ready rigid model must pass, as numbers.
    blender -b --factory-startup --python blender_hardsurf_check.py -- job.json
job: {"parts": a .glb of parts, "report": out.json, "touch": 0.004, "ignore": [names]}
- FLOATING: parts within `touch` of each other are connected; every group apart from the biggest is floating (a part
  that would hang in the air in game: a bell short of its rods, a coil off its can, an axle that reaches nothing).
- OVERLAPS: pairs of parts whose surfaces cross (face pairs), biggest first. Some are meant (an axle in its hub, a
  plank into a batten); read them, don't zero them.
Armatures and objects named *_LOD1 / Icosphere (the glTF importer's bone shape) are ignored."""
import bpy, bmesh, sys, json
from mathutils.bvhtree import BVHTree
J = json.load(open(sys.argv[sys.argv.index("--") + 1]))
bpy.ops.wm.read_factory_settings(use_empty=True); sc = bpy.context.scene
bpy.ops.import_scene.gltf(filepath=J["parts"]); bpy.context.view_layer.update()
skip = set(J.get("ignore", []))
parts = [o for o in sc.objects if o.type == "MESH" and "_LOD1" not in o.name and not o.name.startswith("Icosphere") and o.name not in skip]
TOUCH = float(J.get("touch", 0.004))


def tree(o):
    bm = bmesh.new(); bm.from_mesh(o.data); bm.transform(o.matrix_world); t = BVHTree.FromBMesh(bm); bm.free(); return t


T = {o.name: tree(o) for o in parts}
overl = {}


def touching(p, q):
    n = len(T[p.name].overlap(T[q.name]))
    if n:
        overl[(p.name, q.name)] = n; return True
    vs = [q.matrix_world @ v.co for v in q.data.vertices][:: max(1, len(q.data.vertices) // 400)]
    return any((r := T[p.name].find_nearest(x, TOUCH))[0] is not None for x in vs)


group = {o.name: i for i, o in enumerate(parts)}
for i, p in enumerate(parts):
    for q in parts[i + 1:]:
        if touching(p, q):
            a, b = group[p.name], group[q.name]
            if a != b:
                for k, g in group.items():
                    if g == b: group[k] = a
comps = {}
for k, g in group.items(): comps.setdefault(g, []).append(k)
comps = sorted(comps.values(), key=len, reverse=True)
rep = {"parts": len(parts), "floating": [sorted(c) for c in comps[1:]],
       "overlaps": [{"a": a, "b": b, "face_pairs": n} for (a, b), n in sorted(overl.items(), key=lambda kv: -kv[1])]}
json.dump(rep, open(J["report"], "w"), indent=1)
print("CHECK floating", rep["floating"] or "none", "overlapping pairs", len(rep["overlaps"]))
