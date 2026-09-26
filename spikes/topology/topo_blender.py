"""Blender side of the topology spike. blender -b --factory-startup --python topo_blender.py -- job.json
modes: skin (graph -> Skin + Subsurf), quadriflow, decimate: write {verts, loops, sizes} npz; render: wire views."""
import json
import sys

import bpy
import numpy as np
from mathutils import Matrix, Vector


def clear():
    for coll in (bpy.data.objects, bpy.data.meshes, bpy.data.cameras, bpy.data.materials):
        for item in list(coll):
            coll.remove(item)


def mesh_obj(name, verts, loops, sizes):
    me = bpy.data.meshes.new(name)
    me.vertices.add(len(verts))
    me.vertices.foreach_set("co", np.asarray(verts, np.float32).ravel())
    me.loops.add(len(loops))
    me.loops.foreach_set("vertex_index", np.asarray(loops, np.int32))
    me.polygons.add(len(sizes))
    starts = np.r_[0, np.cumsum(sizes)[:-1]].astype(np.int32)
    me.polygons.foreach_set("loop_start", starts)
    me.update(calc_edges=True)
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    return ob


def save(ob, out):
    dg = bpy.context.evaluated_depsgraph_get()
    me = ob.evaluated_get(dg).to_mesh()
    V = np.empty(len(me.vertices) * 3, np.float32)
    me.vertices.foreach_get("co", V)
    L = np.empty(len(me.loops), np.int32)
    me.loops.foreach_get("vertex_index", L)
    S = np.empty(len(me.polygons), np.int32)
    me.polygons.foreach_get("loop_total", S)
    np.savez(out, verts=V.reshape(-1, 3), loops=L, sizes=S)
    print(f"@@saved {len(me.vertices)} verts {len(S)} faces", flush=True)


def activate(ob):
    for o in bpy.context.scene.objects:
        o.select_set(False)
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob


def skin(job):
    me = bpy.data.meshes.new("graph")
    P = np.asarray(job["nodes"], np.float32)
    E = np.asarray(job["edges"], np.int32)
    me.vertices.add(len(P))
    me.vertices.foreach_set("co", P.ravel())
    me.edges.add(len(E))
    me.edges.foreach_set("vertices", E.ravel())
    me.update()
    ob = bpy.data.objects.new("graph", me)
    bpy.context.scene.collection.objects.link(ob)
    mod = ob.modifiers.new("skin", "SKIN")
    mod.branch_smoothing = job.get("branch_smoothing", 0.0)
    mod.use_smooth_shade = True
    sk = me.skin_vertices[0].data
    for i, r in enumerate(job["radii"]):
        sk[i].radius = (r, r) if np.isscalar(r) else tuple(r)
        sk[i].use_root = i == job["root"]
    if job.get("subsurf", 2):
        s = ob.modifiers.new("sub", "SUBSURF")
        s.levels = s.render_levels = job["subsurf"]
    save(ob, job["out"])


def load_tris(job):
    z = np.load(job["mesh"])
    F = z["faces"]
    return mesh_obj("high", z["verts"], F.ravel(), np.full(len(F), 3))


def quadriflow(job):
    ob = load_tris(job)
    activate(ob)
    r = bpy.ops.object.quadriflow_remesh(mode="FACES", target_faces=int(job["faces"]), use_mesh_symmetry=True,
                                         use_preserve_sharp=False, use_preserve_boundary=False,
                                         smooth_normals=False, seed=0)
    print("@@qf", r, flush=True)
    save(ob, job["out"])


def decimate(job):
    ob = load_tris(job)
    mod = ob.modifiers.new("dec", "DECIMATE")
    mod.decimate_type = "COLLAPSE"
    mod.ratio = job["triangles"] / len(ob.data.polygons)
    mod.use_symmetry = True
    mod.symmetry_axis = "X"
    mod.use_collapse_triangulate = True
    save(ob, job["out"])


def render(job):
    """Posed meshes side by side? No: one mesh per job, a clay object + a wireframe copy, ortho views."""
    z = np.load(job["mesh"])
    ob = mesh_obj("clay", z["verts"], z["loops"], z["sizes"])
    ob.data.shade_smooth()
    wire = mesh_obj("wire", z["verts"], z["loops"], z["sizes"])
    w = wire.modifiers.new("w", "WIREFRAME")
    w.thickness = job.get("wire", 0.0012)
    w.use_even_offset = False
    w.use_relative_offset = False
    w.use_replace = True
    for i, ring in enumerate(job.get("rings") or []):  # closed polylines drawn as red tubes
        cu = bpy.data.curves.new(f"ring{i}", "CURVE")
        cu.dimensions = "3D"
        cu.bevel_depth = job.get("ring_width", 0.0025)
        sp = cu.splines.new("POLY")
        sp.points.add(len(ring) - 1)
        for k, q in enumerate(ring):
            sp.points[k].co = (q[0], q[1], q[2], 1)
        sp.use_cyclic_u = True
        ro = bpy.data.objects.new(f"ring{i}", cu)
        ro.color = (0.9, 0.1, 0.1, 1)
        bpy.context.scene.collection.objects.link(ro)
    ob.color = (0.85, 0.85, 0.85, 1)
    wire.color = (0.08, 0.09, 0.12, 1)
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_WORKBENCH"
    scene.render.resolution_x = scene.render.resolution_y = job.get("size", 800)
    sh = scene.display.shading
    sh.light = "MATCAP"
    sh.studio_light = "clay_studio.exr"
    sh.color_type = "OBJECT"
    sh.show_cavity = False
    if job.get("xray"):
        sh.show_xray = True
        sh.xray_alpha = job["xray"]
    scene.world = scene.world or bpy.data.worlds.new("w")
    scene.world.color = (0.22, 0.23, 0.26)
    scene.view_settings.view_transform = "Standard"
    cd = bpy.data.cameras.new("cam")
    cd.type = "ORTHO"
    cd.clip_start, cd.clip_end = 0.001, 1000
    cam = bpy.data.objects.new("cam", cd)
    scene.collection.objects.link(cam)
    scene.camera = cam
    for v in job["views"]:
        d = Vector(v["dir"]).normalized()
        up = Vector(v["up"])
        right = up.cross(d).normalized()
        up = d.cross(right).normalized()
        rot = Matrix((right, up, d)).transposed()
        cam.matrix_world = Matrix.Translation(Vector(v["center"]) + d * 50) @ rot.to_4x4()
        cd.ortho_scale = v["scale"]
        wire.hide_render = not v.get("wire", True)
        scene.render.filepath = v["out"]
        bpy.ops.render.render(write_still=True)


job = json.load(open(sys.argv[sys.argv.index("--") + 1]))
clear()
{"skin": skin, "quadriflow": quadriflow, "decimate": decimate, "render": render}[job["mode"]](job)
