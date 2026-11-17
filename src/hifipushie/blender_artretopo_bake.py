"""Artist retopo, step 3 (Blender, Cycles CPU): UVs on the low mesh from the artist's seams, then bake the sculpt onto
it: tangent-space normals + base colour (an EMIT bake of the sculpt's vertex colours), plus the masks the repair step
(artretopo_fill.py) needs. Coverage counts a ray that met the sculpt from BEHIND (its dark interior) as a miss. Props (eyes, held things) are rebuilt as primitives and bake from the WHOLE sculpt.
    blender -b --factory-startup --python blender_artretopo_bake.py -- job.json
job: dir, high (the body sculpt: high_body.ply when props were cut), res, extrusion, reach (the cage extrusion and
max ray distance of the main bake: ~1-2 cm / 3-4 cm; fur and drips need the longer reach), thin_extrusion,
thin_reach (the second bake for thin parts), lod_res.
Writes low_uv.glb (low + props + lod1, maps wired in), color.png / normal.png (+ <tag>_color / _normal for props and
lod1), <tag>_cover.png (rays that found nothing stay black), <tag>_island.png (texels inside a UV island),
low_thin.png + *_thinbake.png (thin parts' short-offset bake), low_mouth.png (the mouth inside), low_invented.png +
low_diffused.png (invented skin and its colour spread over the SURFACE, seeded only from skin the bake truly hit;
skin within 2.5 cm of a cut part is invented too), <prop>_invented.png (prop texels touching the body).

Rules learnt (guide(topic="retopo") "Bake"): artist seams survive Catmull-Clark; unwrap ANGLE_BASED + pack. Thin parts
(horn / ear tips) read the far side with a long extrusion: a 2nd bake at 4 mm composited by a thickness mask. Invented
surfaces (pinned) and skin within 1.2 cm of a prop read the cut cavity (black): their colour is diffused over the
SURFACE per vertex from trusted neighbours (the bake's pixels are sRGB: convert to linear before diffusing, emission
is linear) and baked back; texture-space filling pulls colour from unrelated UV neighbours (shards): never."""
import json
import math
import os
import shutil
import sys

import bpy
import mathutils
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import blender_artretopo_common as C  # noqa: E402

J = C.job(); D = J["dir"]; RES = J.get("res", 2048)
EXTR, REACH = J.get("extrusion", 0.012), J.get("reach", 0.03)
sc = C.reset(); sc.render.engine = "CYCLES"; sc.cycles.device = "CPU"; sc.cycles.samples = 8
high = C.load_ply(f"{D}/{J.get('high', 'high.ply')}", "high"); low = C.load_ply(f"{D}/low.ply", "low")
P = json.load(open(f"{D}/props.json")) if os.path.exists(f"{D}/props.json") else {"eyes": [], "props": []}
full = C.load_ply(f"{D}/high.ply", "full") if (P["eyes"] or P["props"]) else None
ACC = []
for k, e in enumerate(P["eyes"]):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=32, ring_count=16, radius=e["R"], location=e["c"])
    o = bpy.context.active_object; o.name = f"eye_{k}"; ACC.append(o)
ROT = {"x": (0, math.pi / 2, 0), "y": (math.pi / 2, 0, 0), "z": (0, 0, 0)}
for k, it in enumerate(P["props"]):
    if it["type"] == "cylinder":
        bpy.ops.mesh.primitive_cylinder_add(vertices=32, radius=it["R"], depth=it["length"], location=it["c"], rotation=ROT[it["axis"]])
    else:
        bpy.ops.mesh.primitive_uv_sphere_add(segments=32, ring_count=16, radius=it["R"], location=it["c"])
    o = bpy.context.active_object; o.name = it.get("name", f"prop_{k}"); ACC.append(o)
for o in ACC:
    C.select_only(o); bpy.ops.object.shade_smooth()
    bpy.ops.object.mode_set(mode="EDIT"); bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(angle_limit=math.radians(60), island_margin=0.01); bpy.ops.object.mode_set(mode="OBJECT")
for o in (high, low):
    for p in o.data.polygons:
        p.use_smooth = True


def unwrap(o, seams_file):
    want = {tuple(sorted(e)) for e in json.load(open(seams_file))}
    for e in o.data.edges:
        e.use_seam = tuple(sorted(e.vertices)) in want
    C.select_only(o); bpy.ops.object.mode_set(mode="EDIT"); bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.unwrap(method="ANGLE_BASED", margin=0.004); bpy.ops.uv.pack_islands(margin=0.004)
    bpy.ops.object.mode_set(mode="OBJECT")
    return len(want)


n_seams = unwrap(low, f"{D}/low_seams.json")
layer = high.data.color_attributes[0].name if high.data.color_attributes else ""
high.data.materials.append(C.emission_material("high", layer))
bk = sc.render.bake


def bake_emit_self(o, mat, img, margin=2):
    """o's own emission (a mask, a colour attribute) into img on its own UVs"""
    keep = list(o.data.materials); o.data.materials.clear(); o.data.materials.append(mat)
    n = mat.node_tree.nodes.new("ShaderNodeTexImage"); n.image = img; mat.node_tree.nodes.active = n
    bk.use_selected_to_active = False; bk.margin = margin
    C.select_only(o); bpy.ops.object.bake(type="EMIT"); bk.use_selected_to_active = True; bk.margin = 8
    o.data.materials.clear()
    for m in keep:
        o.data.materials.append(m)


def vertex_mask(o, weights, tag, res):
    """per-vertex weights (0..1) baked as an image on o's own UVs"""
    ca = o.data.color_attributes.new("m", "FLOAT_COLOR", "POINT")
    for v in o.data.vertices:
        w = weights.get(v.index, 0.0); ca.data[v.index].color = (w, w, w, 1)
    img = bpy.data.images.new(tag, res, res)
    bake_emit_self(o, C.emission_material("m", "m"), img)
    img.filepath_raw = f"{D}/{tag}.png"; img.file_format = "PNG"; img.save()
    o.data.color_attributes.remove(o.data.color_attributes["m"])


def thickness_weights(o, near=0.03, far=0.045):
    """1 where the part is thinner than `near` (a ray inward finds the far side), fading to 0 at `far`"""
    from mathutils.bvhtree import BVHTree
    bvh = BVHTree.FromObject(o, bpy.context.evaluated_depsgraph_get()); out = {}
    for v in o.data.vertices:
        n = v.normal.normalized(); h = bvh.ray_cast(v.co - n * 0.0005, -n, far)
        if h[0] is not None:
            out[v.index] = 1.0 if h[3] < near else (far - h[3]) / (far - near)
    return out


def bake_onto(lo, hi, tag, res, extr, reach):
    """hi's normals + colour onto lo's UVs, then the coverage and island masks; the maps wired into lo's material"""
    imgs = {k: bpy.data.images.new(f"{tag}_{k}", res, res) for k in ("normal", "color")}
    imgs["normal"].colorspace_settings.name = "Non-Color"
    ml = bpy.data.materials.new(tag); ml.use_nodes = True; lt = ml.node_tree; bsdf = lt.nodes["Principled BSDF"]
    tex = {k: lt.nodes.new("ShaderNodeTexImage") for k in imgs}
    for k, n in tex.items():
        n.image = imgs[k]
    lo.data.materials.clear(); lo.data.materials.append(ml)
    C.select_only(hi, lo, active=lo)
    bk.use_selected_to_active = True; bk.cage_extrusion = extr; bk.max_ray_distance = reach; bk.margin = 8
    for k, typ in (("normal", "NORMAL"), ("color", "EMIT")):
        for n in tex.values():
            n.select = False
        tex[k].select = True; lt.nodes.active = tex[k]
        bpy.ops.object.bake(type=typ)
        imgs[k].filepath_raw = f"{D}/{k}.png" if tag == "low" else f"{D}/{tag}_{k}.png"; imgs[k].file_format = "PNG"; imgs[k].save()
    # coverage: the source glows white on its FRONT faces only; a texel whose ray found nothing, or found the sculpt
    # from behind (its dark, unseen interior), stays black
    cov = bpy.data.images.new(f"{tag}_cover", res, res); cn = lt.nodes.new("ShaderNodeTexImage"); cn.image = cov
    wm = C.emission_material("white", rgba=(1, 1, 1, 1)); wt = wm.node_tree
    geo = wt.nodes.new("ShaderNodeNewGeometry"); inv_ = wt.nodes.new("ShaderNodeMath"); inv_.operation = "SUBTRACT"
    inv_.inputs[0].default_value = 1.0; em_ = next(n for n in wt.nodes if n.type == "EMISSION")
    wt.links.new(geo.outputs["Backfacing"], inv_.inputs[1]); wt.links.new(inv_.outputs[0], em_.inputs["Strength"])
    keep = list(hi.data.materials); hi.data.materials.clear(); hi.data.materials.append(wm)
    for n in lt.nodes:
        n.select = False
    cn.select = True; lt.nodes.active = cn; bk.margin = 0
    bpy.ops.object.bake(type="EMIT"); bk.margin = 8
    cov.filepath_raw = f"{D}/{tag}_cover.png"; cov.file_format = "PNG"; cov.save()
    hi.data.materials.clear()
    for m in keep:
        hi.data.materials.append(m)
    # islands: the low mesh glowing white onto itself
    isl = bpy.data.images.new(f"{tag}_island", res, res)
    bake_emit_self(lo, C.emission_material("isl", rgba=(1, 1, 1, 1)), isl, margin=0)
    isl.filepath_raw = f"{D}/{tag}_island.png"; isl.file_format = "PNG"; isl.save()
    lo.data.materials.clear(); lo.data.materials.append(ml)
    nm = lt.nodes.new("ShaderNodeNormalMap")
    lt.links.new(tex["normal"].outputs["Color"], nm.inputs["Color"]); lt.links.new(nm.outputs["Normal"], bsdf.inputs["Normal"])
    lt.links.new(tex["color"].outputs["Color"], bsdf.inputs["Base Color"]); bsdf.inputs["Roughness"].default_value = 0.6
    print("BAKED", tag)


bake_onto(low, high, "low", RES, EXTR, REACH)
THIN = thickness_weights(low)
out = {"seams": n_seams, "thin_verts": sum(1 for w in THIN.values() if w > 0.5)}
if THIN:     # thin parts: a short offset stays on this side
    keep = {k: f"{D}/{k}.png" for k in ("normal", "color")}; keep["cover"] = f"{D}/low_cover.png"
    for k, p in keep.items():
        shutil.copy(p, p.replace(".png", "_thick.png"))
    bake_onto(low, high, "low", RES, J.get("thin_extrusion", 0.004), J.get("thin_reach", 0.015))
    for k, p in keep.items():
        shutil.copy(p, p.replace(".png", "_thinbake.png")); shutil.copy(p.replace(".png", "_thick.png"), p)
    vertex_mask(low, THIN, "low_thin", RES)
G = json.load(open(f"{D}/low_groups.json")) if os.path.exists(f"{D}/low_groups.json") else {}
if "mouth_inside" in G:
    vertex_mask(low, {i: w for i, w in enumerate(G["mouth_inside"]) if w > 0}, "low_mouth", RES)
inv = set(json.load(open(f"{D}/low_invented.json"))) if os.path.exists(f"{D}/low_invented.json") else set()
NEAR = 0.012                 # skin touching a prop reads the cut-out cavity behind it: invented too
from mathutils.bvhtree import BVHTree as _BV  # noqa: E402
CUT = []                     # parts cut out of the sculpt (a comb, a wattle): their cut edge reads raw interior
for cp in P.get("cut_parts", []):
    po = C.load_ply(f"{D}/{cp['file']}", "cut_part")
    CUT.append(_BV.FromObject(po, bpy.context.evaluated_depsgraph_get())); bpy.data.objects.remove(po)
for v in low.data.vertices:
    p = v.co
    for bv in CUT:
        h_ = bv.find_nearest(p)
        if h_[3] is not None and h_[3] < 0.025:
            inv.add(v.index)
    for e in P["eyes"]:
        if (p - mathutils.Vector(e["c"])).length < e["R"] + NEAR:
            inv.add(v.index)
    for it in P["props"]:
        c = mathutils.Vector(it["c"])
        if it["type"] == "sphere":
            if (p - c).length < it["R"] + NEAR:
                inv.add(v.index)
            continue
        a = "xyz".index(it["axis"]); o_ = [k for k in range(3) if k != a]
        r = math.hypot(p[o_[0]] - c[o_[0]], p[o_[1]] - c[o_[1]])
        if abs(p[a] - c[a]) < it["length"] / 2 + 2 * NEAR and r < it["R"] + 1.5 * NEAR:
            inv.add(v.index)
out["invented_verts"] = len(inv)
if inv:
    vertex_mask(low, {i: 1.0 for i in inv}, "low_invented", RES)
    # colour for the invented skin, spread over the SURFACE from the trusted skin round it, then baked back
    cimg = bpy.data.images.load(f"{D}/color.png", check_existing=False); W_, H_ = cimg.size
    px = np.empty(W_ * H_ * 4, np.float32); cimg.pixels.foreach_get(px); px = px.reshape(H_, W_, 4)
    uvl = low.data.uv_layers.active.data; nv = len(low.data.vertices)
    acc = np.zeros((nv, 3)); cnt = np.zeros(nv)
    for poly in low.data.polygons:
        for li in poly.loop_indices:
            vi = low.data.loops[li].vertex_index; u, v = uvl[li].uv
            acc[vi] += px[min(H_ - 1, int(v * H_)), min(W_ - 1, int(u * W_)), :3]; cnt[vi] += 1
    vc = acc / np.maximum(cnt, 1)[:, None]
    vc = np.where(vc <= 0.04045, vc / 12.92, ((vc + 0.055) / 1.055) ** 2.4)   # sRGB pixels -> linear emission
    # seed the spread only from skin the bake truly hit (coverage; a hit from behind counts as a miss)
    cv = bpy.data.images.load(f"{D}/low_cover.png", check_existing=False); cpx = np.empty(W_ * H_ * 4, np.float32)
    cv.pixels.foreach_get(cpx); cpx = cpx.reshape(H_, W_, 4)[..., 0]
    hitv = np.zeros(nv); hcnt = np.zeros(nv)
    for poly in low.data.polygons:
        for li in poly.loop_indices:
            vi = low.data.loops[li].vertex_index; u, v = uvl[li].uv
            hitv[vi] += cpx[min(H_ - 1, int(v * H_)), min(W_ - 1, int(u * W_))]; hcnt[vi] += 1
    known = np.array([i not in inv for i in range(nv)]) & (hitv / np.maximum(hcnt, 1) > 0.6)
    nbrs = [[] for _ in range(nv)]
    for e in low.data.edges:
        a_, b_ = e.vertices; nbrs[a_].append(b_); nbrs[b_].append(a_)
    have = known.copy(); val = np.where(known[:, None], vc, 0.0)
    for _ in range(400):
        new = val.copy()
        for i in range(nv):
            if known[i]:
                continue
            ks = [j for j in nbrs[i] if have[j]]
            if ks:
                new[i] = np.mean(val[ks], axis=0); have[i] = True
        val = new
    ca = low.data.color_attributes.new("diffused", "FLOAT_COLOR", "POINT")
    for i in range(nv):
        ca.data[i].color = (val[i][0], val[i][1], val[i][2], 1)
    imd = bpy.data.images.new("low_diffused", RES, RES); imd.colorspace_settings.name = cimg.colorspace_settings.name
    bake_emit_self(low, C.emission_material("dif", "diffused"), imd, margin=4)
    imd.filepath_raw = f"{D}/low_diffused.png"; imd.file_format = "PNG"; imd.save()
    low.data.color_attributes.remove(low.data.color_attributes["diffused"])
if full is not None:
    full.data.materials.append(C.emission_material("full", full.data.color_attributes[0].name if full.data.color_attributes else ""))
    from mathutils.bvhtree import BVHTree
    bb = BVHTree.FromObject(low, bpy.context.evaluated_depsgraph_get())
    for o in ACC:
        bake_onto(o, full, o.name, 512, 0.015, 0.045)
        if not o.name.startswith("eye"):    # an eyeball's visible part sits against its lids: keep its own bake
            near = {v.index: 1.0 for v in o.data.vertices if bb.find_nearest(o.matrix_world @ v.co)[3] < 0.008}
            vertex_mask(o, near, f"{o.name}_invented", 512)
        elif os.path.exists(f"{D}/{o.name}_invented.png"):
            os.remove(f"{D}/{o.name}_invented.png")
LOD = None
if os.path.exists(f"{D}/lod1.ply"):          # LOD1: its own UVs on the same seams, its own (smaller) bake
    LOD = C.load_ply(f"{D}/lod1.ply", "lod1")
    for p in LOD.data.polygons:
        p.use_smooth = True
    unwrap(LOD, f"{D}/lod1_seams.json")
    bake_onto(LOD, high, "lod1", J.get("lod_res", RES // 2), EXTR, REACH)
C.select_only(low, *ACC, *([LOD] if LOD else []), active=low)
bpy.ops.export_scene.gltf(filepath=f"{D}/low_uv.glb", use_selection=True, export_format="GLB")
out["props"] = [o.name for o in ACC]; out["lod1"] = bool(LOD)
json.dump(out, open(f"{D}/bake.json", "w"), indent=1)
print("BAKE", json.dumps(out))
