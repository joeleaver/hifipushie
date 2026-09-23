"""Runs inside headless Blender for export_asset: the low-poly mesh with UVs, and a preview of the finished asset.

blender -b --factory-startup --python blender_asset.py -- job.json
Jobs:
  {"mode": "lowpoly", "mesh": high.npz, "out": low.npz, "triangles": n, "min_part": n, "margin": 0..1,
   "angle": deg}
      Decimates each part (one object per part), unwraps them all into one UV atlas (smart project, islands
      packed together at one texel density) and writes, per part, the vertices and per-corner uv / normal /
      MikkTSpace tangent + bitangent sign: exactly what the textures are baked against and the GLB carries.
  {"mode": "preview", "glb": path, "views": [{"dir", "up", "center", "scale", "out"}], "size": px}
      Imports the GLB and renders it with Cycles under a simple light rig, to check the textured asset.
"""

import json
import math
import sys

import bmesh
import bpy
import numpy as np
from mathutils import Matrix, Vector


def _clear():
    for coll in (bpy.data.objects, bpy.data.meshes, bpy.data.cameras, bpy.data.lights, bpy.data.materials,
                 bpy.data.images):
        for item in list(coll):
            coll.remove(item)


def _mesh(name, verts, faces):
    me = bpy.data.meshes.new(name)
    me.vertices.add(len(verts))
    me.vertices.foreach_set("co", verts.astype(np.float32).ravel())
    me.loops.add(faces.size)
    me.loops.foreach_set("vertex_index", faces.astype(np.int32).ravel())
    me.polygons.add(len(faces))
    me.polygons.foreach_set("loop_start", np.arange(0, faces.size, 3, dtype=np.int32))
    me.update()
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    return ob


def lowpoly(job):
    _clear()
    z = np.load(job["mesh"])
    verts, faces, part = z["verts"], z["faces"], z["part"]
    names = [str(n) for n in z["part_names"]]
    fpart = part[faces[:, 0]]
    total = len(faces)
    obs = []
    for i, pn in enumerate(names):
        fc = faces[fpart == i]
        if not len(fc):  # all of it hidden
            continue
        used = np.unique(fc)
        remap = np.full(len(verts), -1, np.int64)
        remap[used] = np.arange(len(used))
        ob = _mesh(pn, verts[used], remap[fc])
        # every part gets its share of the budget, but never so few triangles that it turns into a crystal
        want = max(job["triangles"] * len(fc) / total, job["min_part"])
        ratio = min(1.0, want / len(fc))
        if ratio < 1.0:
            mod = ob.modifiers.new("dec", "DECIMATE")
            mod.decimate_type = "COLLAPSE"
            mod.ratio = ratio
            mod.use_symmetry = job.get("symmetry", True)
            mod.symmetry_axis = "X"
            bpy.context.view_layer.objects.active = ob
            bpy.ops.object.modifier_apply(modifier="dec")
        bm = bmesh.new()  # collapse can leave slivers with no area (and so no normal): dissolve them
        bm.from_mesh(ob.data)
        bmesh.ops.dissolve_degenerate(bm, dist=1e-6, edges=bm.edges)
        bmesh.ops.delete(bm, geom=[f for f in bm.faces if f.calc_area() < 1e-12], context="FACES")
        bm.to_mesh(ob.data)
        bm.free()
        tri = ob.modifiers.new("tri", "TRIANGULATE")
        bpy.context.view_layer.objects.active = ob
        bpy.ops.object.modifier_apply(modifier="tri")
        ob.data.shade_smooth()
        obs.append(ob)

    bpy.ops.object.select_all(action="DESELECT")
    for ob in obs:
        ob.select_set(True)
        ob.data.uv_layers.new(name="UVMap")
    bpy.context.view_layer.objects.active = obs[0]
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(angle_limit=math.radians(job.get("angle", 66)), island_margin=job["margin"],
                             correct_aspect=True, scale_to_bounds=False)
    bpy.ops.uv.pack_islands(rotate=True, margin=job["margin"])
    bpy.ops.object.mode_set(mode="OBJECT")

    out = {"part_names": np.array([ob.name for ob in obs])}
    for i, ob in enumerate(obs):
        me = ob.data
        me.calc_tangents(uvmap="UVMap")
        nl = len(me.loops)
        vi = np.empty(nl, np.int32)
        me.loops.foreach_get("vertex_index", vi)
        co = np.empty(len(me.vertices) * 3, np.float32)
        me.vertices.foreach_get("co", co)
        uv = np.empty(nl * 2, np.float32)
        me.uv_layers["UVMap"].data.foreach_get("uv", uv)
        nrm = np.empty(nl * 3, np.float32)
        me.loops.foreach_get("normal", nrm)
        tan = np.empty(nl * 3, np.float32)
        me.loops.foreach_get("tangent", tan)
        sgn = np.empty(nl, np.float32)
        me.loops.foreach_get("bitangent_sign", sgn)
        out.update({f"{i}_verts": co.reshape(-1, 3), f"{i}_corner_vert": vi, f"{i}_uv": uv.reshape(-1, 2),
                    f"{i}_normal": nrm.reshape(-1, 3), f"{i}_tangent": tan.reshape(-1, 3), f"{i}_sign": sgn})
    np.savez(job["out"], **out)


def preview(job):
    _clear()
    bpy.ops.import_scene.gltf(filepath=job["glb"])
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = job.get("samples", 24)
    scene.cycles.use_denoising = True
    scene.render.resolution_x = scene.render.resolution_y = job.get("size", 512)
    scene.render.film_transparent = False
    scene.view_settings.view_transform = "Standard"
    scene.world = scene.world or bpy.data.worlds.new("w")
    scene.world.use_nodes = True
    bg = scene.world.node_tree.nodes.get("Background")
    bg.inputs["Color"].default_value = (0.23, 0.24, 0.27, 1)
    bg.inputs["Strength"].default_value = 0.6
    lights = [((-1.0, -1.2, 1.4), 3.2, 0.03), ((1.4, -0.6, 0.6), 1.2, 0.15), ((0.3, 1.5, 1.0), 2.0, 0.05)]
    for k, (d, e, ang) in enumerate(lights):  # key, fill, rim: sun lamps, so the model's scale doesn't matter
        ld = bpy.data.lights.new(f"sun{k}", "SUN")
        ld.energy, ld.angle = e, ang
        lo = bpy.data.objects.new(f"sun{k}", ld)
        lo.rotation_euler = Vector(d).to_track_quat("Z", "Y").to_euler()
        scene.collection.objects.link(lo)
    cam_data = bpy.data.cameras.new("cam")
    cam_data.type = "ORTHO"
    cam_data.clip_start, cam_data.clip_end = 0.001, 1000
    cam = bpy.data.objects.new("cam", cam_data)
    scene.collection.objects.link(cam)
    scene.camera = cam
    for v in job["views"]:
        d = Vector(v["dir"]).normalized()
        up = Vector(v["up"])
        right = up.cross(d).normalized()
        up = d.cross(right).normalized()
        cam.matrix_world = Matrix.Translation(Vector(v["center"]) + d * 50) @ Matrix((right, up, d)).transposed().to_4x4()
        cam_data.ortho_scale = v["scale"]
        scene.render.filepath = v["out"]
        bpy.ops.render.render(write_still=True)


job = json.load(open(sys.argv[sys.argv.index("--") + 1]))
{"lowpoly": lowpoly, "preview": preview}[job["mode"]](job)
