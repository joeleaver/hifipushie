"""Texture repaint, inside Blender (headless: `blender -b --factory-startup --python <this> -- job.json`).

job["mode"] == "dump": import job["glb"]; write job["out"] (npz) with every mesh triangle that has UVs:
  P (T,3,3) world corners, N (T,3,3) corner normals, UV (T,3,2), img (T,) index into `images` (the base-colour image
  of the triangle's material, -1 none), obj (T,) index into `objects`; and save each base-colour / normal image the
  GLB packs to job["maps"]/<image>.png (the maps a repaint starts from) + a json of names.
job["mode"] == "render": import job["glb"]; swap images by name (job["swap"] {image name: png}), add roughness maps
  (job["rough"] {base image name: png}); render orthographic views job["views"] to job["out_dir"]/<tag>_<view>.png
  (EEVEE, soft studio light, mid-grey background; side = from the character's left so it faces left)."""
import json
import math
import os
import sys

import bpy
import mathutils
import numpy as np

VIEWS = {"front": (0, -1, 0), "back": (0, 1, 0), "side": (1, 0, 0), "side_r": (-1, 0, 0), "3q": (-0.8, -1, 0.45),
         "3qb": (0.7, 1, 0.3), "top": (0, -0.001, 1)}


def job():
    a = sys.argv[sys.argv.index("--") + 1:]
    return json.load(open(a[0]))


def load_glb(path):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=path)
    return [o for o in bpy.context.scene.objects if o.type == "MESH"]


def _linked_image(node_input):
    """the TexImage feeding a socket, through at most a few nodes (normal map, mix, separate colour)"""
    seen = 0
    stack = [l.from_node for l in node_input.links]
    while stack and seen < 12:
        n = stack.pop(); seen += 1
        if n.type == "TEX_IMAGE" and n.image is not None:
            return n.image, n
        for i in n.inputs:
            stack += [l.from_node for l in i.links]
    return None, None


def principled(mat):
    if mat is None or not mat.use_nodes:
        return None
    return next((n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED"), None)


def dump(j):
    objs = load_glb(j["glb"])
    images, names = [], []
    P, N, UV, IMG, OBJ = [], [], [], [], []
    os.makedirs(j["maps"], exist_ok=True)
    normals = {}
    for oi, o in enumerate(objs):
        names.append(o.name)
        dg = bpy.context.evaluated_depsgraph_get(); oe = o.evaluated_get(dg); me = oe.to_mesh()
        if not me.uv_layers:
            oe.to_mesh_clear(); continue
        me.calc_loop_triangles()
        W = o.matrix_world; R = W.to_3x3().inverted().transposed()
        co = np.array([W @ v.co for v in me.vertices], np.float32).reshape(-1, 3)
        uvl = np.empty(len(me.loops) * 2, np.float32); me.uv_layers.active.data.foreach_get("uv", uvl); uvl = uvl.reshape(-1, 2)
        cn = np.empty(len(me.loops) * 3, np.float32); me.corner_normals.foreach_get("vector", cn); cn = cn.reshape(-1, 3)
        Rm = np.array(R, np.float32); cn = cn @ Rm.T; cn /= np.maximum(np.linalg.norm(cn, axis=1, keepdims=True), 1e-9)
        lv = np.empty(len(me.loops), np.int32); me.loops.foreach_get("vertex_index", lv)
        mat_img = []
        for m in me.materials:
            pb = principled(m); im = None
            if pb is not None:
                im, _ = _linked_image(pb.inputs["Base Color"])
                nim, _ = _linked_image(pb.inputs["Normal"])
                if im is not None and nim is not None:
                    normals[im.name] = nim
            if im is not None and im.name not in images:
                images.append(im.name); _save(im, j["maps"])
            mat_img.append(images.index(im.name) if im is not None else -1)
        for t in me.loop_triangles:
            L = list(t.loops)
            P.append(co[lv[L]]); N.append(cn[L]); UV.append(uvl[L])
            IMG.append(mat_img[t.material_index] if mat_img else -1); OBJ.append(oi)
        oe.to_mesh_clear()
    for base, nim in normals.items():
        _save(nim, j["maps"])
    np.savez_compressed(j["out"], P=np.array(P, np.float32), N=np.array(N, np.float32), UV=np.array(UV, np.float32),
                        img=np.array(IMG, np.int32), obj=np.array(OBJ, np.int32))
    json.dump({"images": images, "objects": names, "normal_of": {k: v.name for k, v in normals.items()}},
              open(j["out"].replace(".npz", ".json"), "w"), indent=1)


def _save(im, folder):
    p = os.path.join(folder, im.name.replace("/", "_") + ".png")
    if os.path.exists(p):
        return
    im.filepath_raw = p; im.file_format = "PNG"
    try:
        im.save()
    except RuntimeError:
        im.save_render(p)


def render(j):
    objs = load_glb(j["glb"])
    sc = bpy.context.scene
    for o in list(bpy.context.scene.objects):
        if o.type == "MESH" and (("LOD" in o.name.upper() and "LOD0" not in o.name.upper()) or o.name in j.get("hide", [])):
            o.hide_render = True
    swap = j.get("swap", {}); rough = j.get("rough", {})
    for m in bpy.data.materials:
        pb = principled(m)
        if pb is None:
            continue
        im, node = _linked_image(pb.inputs["Base Color"])
        if im is not None and im.name in swap:
            node.image = bpy.data.images.load(swap[im.name], check_existing=False)
            if im.name in rough:
                t = m.node_tree.nodes.new("ShaderNodeTexImage"); t.image = bpy.data.images.load(rough[im.name])
                t.image.colorspace_settings.name = "Non-Color"
                t.interpolation = "Linear"
                for l in list(pb.inputs["Roughness"].links):
                    m.node_tree.links.remove(l)
                m.node_tree.links.new(t.outputs["Color"], pb.inputs["Roughness"])
                t.location = node.location.x, node.location.y - 300
                uvsrc = node.inputs["Vector"].links[0].from_socket if node.inputs["Vector"].links else None
                if uvsrc is not None:
                    m.node_tree.links.new(uvsrc, t.inputs["Vector"])
        nim, nnode = _linked_image(pb.inputs["Normal"])
        if nim is not None and nim.name in swap:
            nnode.image = bpy.data.images.load(swap[nim.name], check_existing=False)
            nnode.image.colorspace_settings.name = "Non-Color"
    for eng in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE"):
        try:
            sc.render.engine = eng; break
        except TypeError:
            continue
    sc.render.resolution_x = sc.render.resolution_y = int(j.get("res", 900))
    sc.render.film_transparent = False
    sc.view_settings.view_transform = "Standard"
    w = bpy.data.worlds.new("w"); sc.world = w; w.use_nodes = True
    w.node_tree.nodes["Background"].inputs[0].default_value = (0.42, 0.42, 0.42, 1); w.node_tree.nodes["Background"].inputs[1].default_value = 0.6
    vis = [o for o in sc.objects if o.type == "MESH" and not o.hide_render]
    pts = [o.matrix_world @ mathutils.Vector(c) for o in vis for c in o.bound_box]
    lo = mathutils.Vector([min(p[i] for p in pts) for i in range(3)]); hi = mathutils.Vector([max(p[i] for p in pts) for i in range(3)])
    c = (lo + hi) / 2; size = max(hi - lo) * 1.12
    if j.get("centre"):
        c = mathutils.Vector(j["centre"]); size = float(j.get("scale", size))
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam")); sc.collection.objects.link(cam); sc.camera = cam
    cam.data.type = "ORTHO"; cam.data.ortho_scale = size; cam.data.clip_end = 100
    for nm, e, d in (("key", 3.0, (-0.6, -1, 0.9)), ("fill", 1.2, (1, -0.4, 0.3)), ("rim", 1.5, (0.3, 1, 0.6))):
        L = bpy.data.objects.new(nm, bpy.data.lights.new(nm, "SUN")); sc.collection.objects.link(L)
        L.data.energy = e; L.data.angle = 0.5
        L.rotation_euler = (-mathutils.Vector(d)).to_track_quat("-Z", "Y").to_euler()
    for v in j["views"]:
        d = mathutils.Vector(VIEWS[v]).normalized(); cam.location = c + d * 5
        cam.rotation_euler = (c - cam.location).to_track_quat("-Z", "Y").to_euler()
        sc.render.filepath = os.path.join(j["out_dir"], f"{j['tag']}_{v}.png")
        bpy.ops.render.render(write_still=True)


if __name__ == "__main__":
    J = job()
    {"dump": dump, "render": render}[J["mode"]](J)
