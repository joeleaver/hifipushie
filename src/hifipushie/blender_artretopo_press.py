"""Artist retopo, step 2 (Blender): subdivide the cage, PRESS it onto the sculpt, relax, check for folds, render wires.
    blender -b --factory-startup --python blender_artretopo_press.py -- job.json
job: dir, high (the sculpt to press onto: high_body.ply when props were cut), levels (Catmull-Clark levels before
pressing), relax (smooth-and-press rounds), after (extra subdivision levels AFTER pressing, unpressed: the form;
then the pressed mesh is also LOD1), centre, scale (render framing).
Reads cage.ply + cage_{pinned,seams,groups}.json; writes low.ply, low_seams.json, low_groups.json, low_invented.json,
lod1.ply + lod1_seams.json (when after > 0), press.json (numbers), wire_{cage,low}_{front,side,back,3q}.png.

Pressing is ALONG each vertex's normal, both ways (shrinkwrap PROJECT, limit 3 cm), so thin and touching parts keep
their own side; nearest-point folds thin cupped ears and touching armpits. (mode "nearest" presses
to the nearest point instead: only for a test.) Pinned cage vertices (cage_pinned.json: invented
surfaces) carry press weight 0 (subdivision interpolates them); the `freeze` group (the designed mouth) isn't relaxed.
Fold check: a face whose normal disagrees with the nearest sculpt normal (dot < 0.2), invented faces skipped."""
import json
import os
import sys

import bpy
import bmesh

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import blender_artretopo_common as C  # noqa: E402

J = C.job(); D = J["dir"]; LEVELS = J.get("levels", 1); RELAX = J.get("relax", 6); AFTER = J.get("after", 1)
sc = C.reset()
high = C.load_ply(f"{D}/{J.get('high', 'high.ply')}", "high")
cage = C.load_ply(f"{D}/cage.ply", "cage")
bm = bmesh.new(); bm.from_mesh(cage.data); bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
if bm.calc_volume(signed=True) < 0:      # recalc guesses the side; a closed cage's signed volume doesn't
    bmesh.ops.reverse_faces(bm, faces=bm.faces)
out = {"cage_volume": round(bm.calc_volume(signed=True), 5)}
bm.to_mesh(cage.data); bm.free()

pin = set(json.load(open(f"{D}/cage_pinned.json"))) if os.path.exists(f"{D}/cage_pinned.json") else set()
g = cage.vertex_groups.new(name="press")
g.add([v.index for v in cage.data.vertices if v.index not in pin], 1.0, "REPLACE")
if pin:
    g.add(sorted(pin), 0.0, "REPLACE")
SEAMS = json.load(open(f"{D}/cage_seams.json")) if os.path.exists(f"{D}/cage_seams.json") else []
GROUPS = json.load(open(f"{D}/cage_groups.json")) if os.path.exists(f"{D}/cage_groups.json") else {}
want = {tuple(sorted(e)) for e in SEAMS}
for e in cage.data.edges:
    if tuple(sorted(e.vertices)) in want:
        e.use_seam = True
for name, ids in GROUPS.items():
    gg = cage.vertex_groups.new(name=name); gg.add([v.index for v in cage.data.vertices], 0.0, "REPLACE")
    if isinstance(ids, dict):
        for i, w in ids.items():
            gg.add([int(i)], float(w), "REPLACE")
    else:
        gg.add(ids, 1.0, "REPLACE")
low = cage.copy(); low.data = cage.data.copy(); low.name = "low"; sc.collection.objects.link(low)
sub = low.modifiers.new("sub", "SUBSURF"); sub.levels = sub.render_levels = LEVELS
C.apply_mod(low, sub)


def press(o, nearest=False):
    sw = o.modifiers.new("sw", "SHRINKWRAP"); sw.target = high; sw.vertex_group = "press"
    if nearest:
        sw.wrap_method = "NEAREST_SURFACEPOINT"
    else:
        sw.wrap_method = "PROJECT"; sw.use_negative_direction = True; sw.use_positive_direction = True
        sw.project_limit = 0.03; sw.cull_face = "OFF"
    C.apply_mod(o, sw)


press(low, nearest=J.get("mode") == "nearest")
for _ in range(RELAX):          # relax along the surface: smooth, then back onto the sculpt
    sm = low.modifiers.new("sm", "SMOOTH"); sm.factor = 0.5; sm.iterations = 2
    if "freeze" in low.vertex_groups:
        sm.vertex_group = "freeze"; sm.invert_vertex_group = True
    C.apply_mod(low, sm)
    press(low)


def export_ply(o, path):
    C.select_only(o)
    bpy.ops.wm.ply_export(filepath=path, export_selected_objects=True, export_colors="NONE", export_uv=False,
                          export_normals=False, apply_modifiers=True)


if AFTER:   # the coarse pressed mesh is LOD1 (same loops); the FORM is it subdivided further, unpressed
    export_ply(low, f"{D}/lod1.ply")
    json.dump([list(e.vertices) for e in low.data.edges if e.use_seam], open(f"{D}/lod1_seams.json", "w"))
    out["lod1_faces"] = len(low.data.polygons)
    sub2 = low.modifiers.new("sub2", "SUBSURF"); sub2.levels = sub2.render_levels = AFTER
    C.apply_mod(low, sub2)
elif os.path.exists(f"{D}/lod1.ply"):
    os.remove(f"{D}/lod1.ply")
from mathutils.bvhtree import BVHTree  # noqa: E402
bvh = BVHTree.FromObject(high, bpy.context.evaluated_depsgraph_get())
gp = low.vertex_groups["press"].index
pw = {v.index: next((x.weight for x in v.groups if x.group == gp), 1.0) for v in low.data.vertices}
json.dump([list(e.vertices) for e in low.data.edges if e.use_seam], open(f"{D}/low_seams.json", "w"))
json.dump({name: [next((x.weight for x in v.groups if x.group == low.vertex_groups[name].index), 0.0) for v in low.data.vertices]
           for name in GROUPS}, open(f"{D}/low_groups.json", "w"))
json.dump([i for i, w in pw.items() if w < 0.5], open(f"{D}/low_invented.json", "w"))
bad = []
for f in low.data.polygons:
    if min(pw[i] for i in f.vertices) < 0.5:
        continue
    loc, nrm, _, _ = bvh.find_nearest(f.center)
    if nrm is not None and f.normal.dot(nrm) < 0.2:
        bad.append(f.index)
low.data.materials.append(C.flat_mat("ok", (0.86, 0.84, 0.80, 1))); low.data.materials.append(C.flat_mat("bad", (0.9, 0.1, 0.1, 1)))
for i in bad:
    low.data.polygons[i].material_index = 1
export_ply(low, f"{D}/low.ply")
out.update({"pinned_cage_verts": len(pin), "seam_edges": sum(e.use_seam for e in low.data.edges),
            "low_verts": len(low.data.vertices), "low_faces": len(low.data.polygons), "folded": len(bad),
            "folded_at": [list(map(lambda x: round(x, 3), low.data.polygons[i].center)) for i in bad[:12]],
            "invented_verts": sum(1 for w in pw.values() if w < 0.5)})
json.dump(out, open(f"{D}/press.json", "w"), indent=1)

# ---- render: solid grey + dark wire on top (red faces = folded)
C.workbench(sc, 900)
cam = C.ortho_camera(sc, J["scale"])
for o in (high, cage, low):
    o.color = (0.86, 0.84, 0.80, 1)
high.data.materials.append(C.flat_mat("h", (0.86, 0.84, 0.80, 1)))
wc = C.wire_copy(sc, cage, 0.004 * J["scale"] / 1.1, (0.85, 0.2, 0.1, 1))
wl = C.wire_copy(sc, low, 0.0012 * J["scale"] / 1.1, (0.1, 0.1, 0.12, 1))
for tag, shown in {"cage": [high, wc], "low": [low, wl]}.items():
    for o in sc.objects:
        if o.type == "MESH":
            o.hide_render = o not in shown
    for vn in ("front", "side", "back", "3q"):
        C.aim(cam, J["centre"], C.VIEWS[vn])
        sc.render.filepath = f"{D}/wire_{tag}_{vn}.png"; bpy.ops.render.render(write_still=True)
print("PRESS", json.dumps(out))
