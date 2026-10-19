"""Blender job for garment_game: bake the drape (high) onto the pattern-space game mesh (low) and write a GLB.

blender -b --factory-startup --python blender_garment_game.py -- job.json
job = {"occluders_glb": GLB whose meshes (minus `skip` names) occlude the AO bake (the character), "skip": [...],
       "ao_distance": m, "ao_samples": n,
       "garments": [{"name", "low": npz (V, T, uv, N, outer_faces), "high": npz (V, F), "size": px,
                     "color": "#rrggbb", "roughness": r, "out_glb", "out_dir"}]}
Normal: tangent space (OpenGL, +Y), Cycles selected-to-active through a per-vertex cage (each low vertex pushed out
by 1.5x its faces' stray from the high + 2 mm, as asset.cage_verts). AO: from the high, everything else in the scene
occluding, the low and cage invisible to rays. Only the outer faces are baked; the inner faces share their uvs.
"""
import json
import sys
from pathlib import Path

import bpy
import numpy as np
from mathutils.bvhtree import BVHTree

job = json.load(open(sys.argv[sys.argv.index("--") + 1]))
bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
sc.render.engine = "CYCLES"
sc.cycles.device = "CPU"
sc.cycles.samples = int(job.get("ao_samples", 32))
if sc.world is None:
    sc.world = bpy.data.worlds.new("w")
sc.world.light_settings.distance = float(job.get("ao_distance", 0.15))


def mesh_ob(name, V, F, uv=None, N=None):
    me = bpy.data.meshes.new(name)
    me.from_pydata(np.asarray(V, float).tolist(), [], np.asarray(F, int).tolist())
    me.update()
    if uv is not None:
        lay = me.uv_layers.new(name="UVMap")
        li = np.zeros(len(me.loops), int)
        me.loops.foreach_get("vertex_index", li)
        lay.data.foreach_set("uv", np.asarray(uv, np.float32)[li].ravel())
    me.polygons.foreach_set("use_smooth", np.ones(len(me.polygons), bool))
    if N is not None:
        li = np.zeros(len(me.loops), int)
        me.loops.foreach_get("vertex_index", li)
        me.normals_split_custom_set(np.asarray(N, float)[li].tolist())
    ob = bpy.data.objects.new(name, me)
    sc.collection.objects.link(ob)
    return ob


def hide_rays(ob):
    for a in ("visible_camera", "visible_diffuse", "visible_glossy", "visible_transmission", "visible_shadow",
              "visible_volume_scatter"):
        setattr(ob, a, False)


occ = []
if job.get("occluders_glb"):
    bpy.ops.import_scene.gltf(filepath=job["occluders_glb"])
    skip = job.get("skip", [])
    for o in list(sc.objects):
        if o.type == "MESH" and any(s in o.name or s in o.data.name for s in skip):
            bpy.data.objects.remove(o, do_unlink=True)
    occ = [o for o in sc.objects if o.type == "MESH"]
    for o in sc.objects:  # rest pose: armatures off
        for m in getattr(o, "modifiers", []):
            if m.type == "ARMATURE":
                m.show_render = m.show_viewport = False

highs = {}
for g in job["garments"]:
    if g["high"] not in highs:
        h = np.load(g["high"])
        highs[g["high"]] = mesh_ob(f"high_{g['name']}", h["V"], h["F"])


def bake_one(g):
    lo = np.load(g["low"])
    V, T, uv, N, nout = lo["V"], lo["T"], lo["uv"], lo["N"], int(lo["outer_faces"])
    if "V_bake" in lo.files:  # a layer-gapped under garment bakes from the drape surface, ships at the gapped one
        V = lo["V_bake"]
    To = T[:nout]
    used = np.unique(To)
    remap = -np.ones(len(V), int); remap[used] = np.arange(len(used))
    Vo, Fo, uvo, No = V[used], remap[To], uv[used], N[used]
    high = highs[g["high"]]
    bvh = BVHTree.FromObject(high, bpy.context.evaluated_depsgraph_get())
    c = Vo[Fo]
    probes = np.concatenate([c.mean(1)[:, None], (c + np.roll(c, 1, 1)) / 2], 1)  # (f, 4, 3)
    stray = np.array([[bvh.find_nearest(p)[3] or 0.0 for p in f] for f in probes]).max(1)
    out = np.zeros(len(Vo)); np.maximum.at(out, Fo.ravel(), np.repeat(stray, 3))
    out = np.minimum(out * 1.5 + 0.002, 0.03)
    low = mesh_ob(f"bake_{g['name']}", Vo, Fo, uvo, No)
    cage = mesh_ob(f"cage_{g['name']}", Vo + No * out[:, None], Fo)
    hide_rays(low); hide_rays(cage)
    size = int(g["size"])
    imgs = {}
    for kind in ("normal", "ao"):
        im = bpy.data.images.new(f"{g['name']}_{kind}", size, size, alpha=False, float_buffer=False)
        im.colorspace_settings.name = "Non-Color"
        imgs[kind] = im
    mat = bpy.data.materials.new(f"bake_{g['name']}")
    mat.use_nodes = True
    tn = mat.node_tree.nodes.new("ShaderNodeTexImage")
    low.data.materials.append(mat)
    for kind, btype in (("normal", "NORMAL"), ("ao", "AO")):
        tn.image = imgs[kind]
        mat.node_tree.nodes.active = tn
        bpy.ops.object.select_all(action="DESELECT")
        high.select_set(True); low.select_set(True)
        bpy.context.view_layer.objects.active = low
        bpy.ops.object.bake(type=btype, use_selected_to_active=True, use_cage=True, cage_object=cage.name,
                            margin=8, normal_space="TANGENT", target="IMAGE_TEXTURES")
        p = Path(g["out_dir"]) / f"{g['name']}_{kind}.png"
        imgs[kind].filepath_raw = str(p); imgs[kind].file_format = "PNG"; imgs[kind].save()
    stats = {"cage_mm_p50": float(np.median(out) * 1e3), "cage_mm_max": float(out.max() * 1e3),
             "stray_mm_p99": float(np.percentile(stray, 99) * 1e3)}
    a = np.array(imgs["ao"].pixels[:]).reshape(-1, 4)[:, 0]
    stats["ao_mean"] = float(a.mean())
    for o in (low, cage):
        bpy.data.objects.remove(o, do_unlink=True)
    return imgs, stats


def combine_detail(g, imgs):
    """Baked normal (drape folds) + the garment's painted detail normal (seams, topstitching, hems, buttons): reoriented
    normal mapping (RNM); basecolor = the painted map when given."""
    if not g.get("detail_normal"):
        return
    det = bpy.data.images.load(g["detail_normal"])
    det.colorspace_settings.name = "Non-Color"
    if det.size[0] != imgs["normal"].size[0]:
        det.scale(*imgs["normal"].size)
    sz = imgs["normal"].size[0]
    A = np.array(imgs["normal"].pixels[:]).reshape(-1, 4)
    D = np.array(det.pixels[:]).reshape(-1, 4)
    t = A[:, :3] * [2, 2, 2] + [-1, -1, 0]
    # a texel turned past ~70 degrees is a ray that hit the wrong sheet (island rims, seams): flat instead
    bad = t[:, 2] < 0.35
    t[bad] = [0.0, 0.0, 1.0]
    u = D[:, :3] * [-2, -2, 2] + [1, 1, -1]
    r = t * (np.sum(t * u, 1) / np.maximum(t[:, 2], 1e-4))[:, None] - u
    r /= np.maximum(np.linalg.norm(r, axis=1, keepdims=True), 1e-9)
    A[:, :3] = r * 0.5 + 0.5
    imgs["normal"].pixels.foreach_set(A.ravel().astype(np.float32))
    imgs["normal"].filepath_raw = str(Path(g["out_dir"]) / f"{g['name']}_normal_combined.png")
    imgs["normal"].save()


def export_one(g, imgs):
    lo = np.load(g["low"])
    ob = mesh_ob(g["name"], lo["V"], lo["T"], lo["uv"], lo["N"])
    mat = bpy.data.materials.new(f"{g['name']}_material")
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
    hx = g["color"].lstrip("#")
    srgb = [int(hx[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    lin = [x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in srgb]
    bsdf.inputs["Base Color"].default_value = (*lin, 1.0)
    if g.get("basecolor"):
        tb = nt.nodes.new("ShaderNodeTexImage"); tb.image = bpy.data.images.load(g["basecolor"])
        nt.links.new(tb.outputs["Color"], bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = float(g.get("roughness", 0.85))
    bsdf.inputs["Metallic"].default_value = 0.0
    tn = nt.nodes.new("ShaderNodeTexImage"); tn.image = imgs["normal"]
    nm = nt.nodes.new("ShaderNodeNormalMap")
    nt.links.new(tn.outputs["Color"], nm.inputs["Color"]); nt.links.new(nm.outputs["Normal"], bsdf.inputs["Normal"])
    # glTF occlusion: the exporter's "glTF Material Output" group (engines read AO from it; Blender does not draw it)
    grp = bpy.data.node_groups.get("glTF Material Output")
    if grp is None:
        grp = bpy.data.node_groups.new("glTF Material Output", "ShaderNodeTree")
        grp.interface.new_socket("Occlusion", in_out="INPUT", socket_type="NodeSocketFloat")
    gn = nt.nodes.new("ShaderNodeGroup"); gn.node_tree = grp
    ta = nt.nodes.new("ShaderNodeTexImage"); ta.image = imgs["ao"]
    sep = nt.nodes.new("ShaderNodeSeparateColor")
    nt.links.new(ta.outputs["Color"], sep.inputs["Color"]); nt.links.new(sep.outputs["Red"], gn.inputs["Occlusion"])
    ob.data.materials.append(mat)
    bpy.ops.object.select_all(action="DESELECT")
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob
    bpy.ops.export_scene.gltf(filepath=g["out_glb"], export_format="GLB", use_selection=True, export_normals=True,
                              export_tangents=True, export_yup=True)
    # the mesh datablock goes too: one job exports every LOD under the same name, and a leftover mesh made the next
    # LOD "game_jacket.001" (judge's triangle / sidedness checks key by mesh name and refused LOD1-3)
    me_, mat_ = ob.data, mat
    bpy.data.objects.remove(ob, do_unlink=True)
    bpy.data.meshes.remove(me_)
    bpy.data.materials.remove(mat_)


report = {}
for g in job["garments"]:
    Path(g["out_dir"]).mkdir(parents=True, exist_ok=True)
    imgs, st = bake_one(g)
    combine_detail(g, imgs)
    export_one(g, imgs)
    report[g["name"]] = st
    print("@@garment", g["name"], json.dumps(st), flush=True)
json.dump(report, open(Path(job["garments"][0]["out_dir"]) / "bake_report.json", "w"), indent=1)
