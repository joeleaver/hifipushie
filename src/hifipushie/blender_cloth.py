"""Blender side of cloth.py: sew and settle a garment with the cloth modifier, or render garments.

Run: blender -b --factory-startup --python blender_cloth.py -- job.json
job "mode" "sim" (default): in.npz beside job.json (X start positions, uv flat pattern, F triangles, sew/stitch vertex
pairs, stiff per-vertex interfacing weight, bodyV/bodyT the collider, pins) -> out.npz {V}.
The flat pattern is the cloth's rest shape (the mesh's Basis; the start positions a shape key faded out, Dynamic Mesh), the sewing pairs are loose edges
(sewing springs pull them shut), interfaced pieces bend `stiff` times harder (bending vertex group). Stage 1 sews
without self-collision; stage 2 restarts from stage 1's result with self-collision on and settles.
"hang": the pins (vertices) are moved to the hook first and held (pin group); the body is left out.
mode "render": meshes from render.npz (any number of objects with per-vertex colours) through orthographic views.
"""
import json
import math
import sys
import time

import bpy
import numpy as np


def log(*a):
    print("cloth:", *a, flush=True)


def _mesh(name, V, F, edges=()):
    me = bpy.data.meshes.new(name)
    me.from_pydata([tuple(map(float, v)) for v in V], [tuple(map(int, e)) for e in edges],
                   [tuple(map(int, f)) for f in F])
    me.validate(clean_customdata=False)
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    return ob


def _rgb(hexs):
    hexs = hexs.lstrip("#")
    srgb = [int(hexs[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    return [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in srgb]


def _sim_object(name, X, F, sew, uv, stiff, pins, fab, self_collision, frames, quality=6):
    # The flat pattern is the mesh itself (Basis); the start positions are a shape key faded out over the first
    # frames, and Dynamic Mesh takes the rest lengths from the (now flat) input every frame. (rest_shape_key moves
    # the cloth onto the rest shape at the first frame: the garment started as the flat pattern, measured.)
    if uv.shape[1] == 2:
        flat = np.zeros((len(X), 3))
        flat[:, :2] = uv
    else:
        flat = uv
    if fab.get("rest", "placed") == "placed":  # rest lengths from the start positions (placed isometrically)
        ob = _mesh(name, X, F, edges=sew)
    else:
        ob = _mesh(name, flat, F, edges=sew)
        ob.shape_key_add(name="Basis")
        sk = ob.shape_key_add(name="placed")
        sk.data.foreach_set("co", np.asarray(X, np.float32).ravel())
        sk.value = 1.0
        sk.keyframe_insert("value", frame=1)
        sk.value = 0.0
        sk.keyframe_insert("value", frame=int(fab.get("ease_in", 4)))
    vg = ob.vertex_groups.new(name="stiff")
    for i in np.where(stiff > 0)[0]:
        vg.add([int(i)], float(stiff[i]), "REPLACE")
    if len(pins):
        pg = ob.vertex_groups.new(name="pin")
        pg.add([int(i) for i in pins], 1.0, "REPLACE")
    c = ob.modifiers.new("cloth", "CLOTH")
    s = c.settings
    s.quality = quality
    s.mass = fab["mass"]
    s.air_damping = fab.get("air", 1.0)
    s.tension_stiffness = s.compression_stiffness = fab["tension"]
    s.compression_stiffness = fab["compression"]
    s.shear_stiffness = fab["shear"]
    s.bending_stiffness = fab["bending"]
    s.bending_stiffness_max = fab["bending"] * fab.get("stiff", 20)
    s.shear_stiffness_max = fab["shear"] * 3
    s.vertex_group_bending = "stiff"
    s.vertex_group_shear_stiffness = "stiff"
    s.tension_damping = s.compression_damping = s.shear_damping = 5
    s.bending_damping = 0.5
    s.use_sewing_springs = True
    s.sewing_force_max = fab.get("sewing", 8.0)
    s.use_dynamic_mesh = fab.get("rest", "placed") != "placed"
    if len(pins):
        s.vertex_group_mass = "pin"
        s.pin_stiffness = 5.0
    cs = c.collision_settings
    cs.use_collision = True
    cs.distance_min = max(0.003, fab.get("thickness", 0.0005) * 2)
    cs.collision_quality = 3
    cs.use_self_collision = self_collision
    cs.self_distance_min = max(0.0025, fab.get("thickness", 0.0005) * 2)
    cs.self_friction = 5
    c.point_cache.frame_start = 1
    c.point_cache.frame_end = frames
    return ob


TRACE = {}


def _grab(ob):
    ev = ob.evaluated_get(bpy.context.evaluated_depsgraph_get())
    me = ev.to_mesh()
    V = np.zeros(len(me.vertices) * 3, np.float32)
    me.vertices.foreach_get("co", V)
    ev.to_mesh_clear()
    return V.reshape(-1, 3)


def _run(ob, frames, trace=()):
    sc = bpy.context.scene
    sc.frame_start, sc.frame_end = 1, frames
    t = time.time()
    for f in range(1, frames + 1):
        sc.frame_set(f)
        if f in trace:
            TRACE[f"{ob.name}_{f}"] = _grab(ob)
    dg = bpy.context.evaluated_depsgraph_get()
    ev = ob.evaluated_get(dg)
    me = ev.to_mesh()
    V = np.zeros(len(me.vertices) * 3, np.float32)
    me.vertices.foreach_get("co", V)
    ev.to_mesh_clear()
    return V.reshape(-1, 3).astype(np.float64), time.time() - t


def sim(job, d):
    fab = job["fabric"]
    X, F, uv = d["X"], d["F"], d["uv"]
    sew = np.r_[d["sew"], d["stitch"]] if len(d["stitch"]) else d["sew"]
    stiff = d["stiff"]
    state = job.get("state", "worn")
    pins = np.asarray(job.get("pins") or [], dtype=np.int64)
    sc = bpy.context.scene
    sc.render.fps = 24
    if not (isinstance(state, dict) and "hang" in state) or job.get("with_body"):
        body = _mesh("body", d["bodyV"], d["bodyT"])
        col = body.modifiers.new("collision", "COLLISION")
        body.collision.thickness_outer = 0.004
        body.collision.cloth_friction = 5.0
        body.collision.damping = 0.6
    if isinstance(state, dict) and "hang" in state:
        hook = np.asarray(job["hook"], float)
        # the whole garment moved so the pins' centre hangs just under the hook; each pin is sewn to an anchor
        # vertex at the hook (loose, pinned: the pin group can't hold cloth vertices themselves, Dynamic Mesh would
        # pull them to their flat-pattern positions)
        X = X + (hook - [0, 0, 0.01] - X[pins].mean(0))
        n0 = len(X)
        anchors = hook + (X[pins] - X[pins].mean(0)) * float(job.get("pin_spread", 0.3))
        X = np.r_[X, anchors]
        uv = np.r_[np.c_[uv, np.zeros(len(uv))], anchors]  # anchors stay at the hook in the input mesh
        stiff = np.r_[stiff, np.zeros(len(pins))]
        sew = np.r_[sew, np.c_[pins, n0 + np.arange(len(pins))]]
        pins = n0 + np.arange(len(pins))
        job["_n0"] = n0
        if job.get("rack"):
            for k, (a, b, r) in enumerate(job["rack"]):
                bpy.ops.mesh.primitive_cylinder_add(radius=r, depth=1.0, vertices=24)
                cyl = bpy.context.object
                a, b = np.asarray(a), np.asarray(b)
                cyl.location = tuple((a + b) / 2)
                cyl.scale = (1, 1, float(np.linalg.norm(b - a)))
                dirv = (b - a) / np.linalg.norm(b - a)
                cyl.rotation_mode = "QUATERNION"
                from mathutils import Vector
                cyl.rotation_quaternion = Vector((0, 0, 1)).rotation_difference(Vector(tuple(dirv)))
                cyl.modifiers.new("collision", "COLLISION")
    frames = int(job.get("frames", 90))
    # stage 1: sew without gravity (the seams close before anything can slide off the shoulders)
    f1 = int(job.get("sew_frames", 60))
    ob = _sim_object("garment", X, F, sew, uv, stiff, pins, fab, False, f1)
    ob.modifiers["cloth"].settings.effector_weights.gravity = 0.0
    ob.modifiers["cloth"].settings.sewing_force_max = float(job.get("sew_force", 30.0))  # 0 = unbounded (yanks pieces through the body)
    V, dt = _run(ob, f1, trace=job.get("trace", ()))
    gap = np.linalg.norm(V[sew[:, 0]] - V[sew[:, 1]], axis=1) if len(sew) else np.zeros(1)
    log(f"stage 1 (sew, no gravity): {len(X)} verts, {f1} frames, {dt:.1f} s, seam gaps mean "
        f"{gap.mean() * 1000:.1f} mm, max {gap.max() * 1000:.1f} mm, z {V[:, 2].min():.3f}..{V[:, 2].max():.3f}")
    stages = {"V1": V.copy()}
    # stage 2: gravity, settle
    bpy.data.objects.remove(ob)
    ob = _sim_object("garment2", V, F, sew, uv, stiff, pins, fab, False, frames)
    V, dt = _run(ob, frames)
    log(f"stage 2 (gravity): {frames} frames, {dt:.1f} s, z {V[:, 2].min():.3f}..{V[:, 2].max():.3f}")
    if job.get("self_collision", True):
        f3 = int(job.get("settle_frames", 24))
        bpy.data.objects.remove(ob)
        ob = _sim_object("garment3", V, F, sew, uv, stiff, pins, fab, True, f3)
        V, dt = _run(ob, f3)
        log(f"stage 3 (self-collision): {f3} frames, {dt:.1f} s")
    gap = np.linalg.norm(V[sew[:, 0]] - V[sew[:, 1]], axis=1) if len(sew) else np.zeros(1)
    log(f"final seam gaps mean {gap.mean() * 1000:.1f} mm, p95 {np.percentile(gap, 95) * 1000:.1f} mm")
    n0 = job.get("_n0", len(V))
    np.savez(job["out"], V=V[:n0], **{k: v[:n0] for k, v in stages.items()}, **{k: v[:n0] for k, v in TRACE.items()})


def render(job, d):
    """Objects from render.npz: for each name in job["objects"]: <name>_V, <name>_F, optional <name>_C (per-vertex
    RGB, linear), job colours; orthographic views front/side/back (+ an optional perspective three-quarter)."""
    sc = bpy.context.scene
    sc.render.engine = "BLENDER_WORKBENCH"
    sh = sc.display.shading
    sh.light = "STUDIO"
    sh.studio_light = "outdoor.sl" if "outdoor.sl" in [l.name for l in bpy.context.preferences.studio_lights] else sh.studio_light
    sh.show_cavity = True
    sh.cavity_type = "BOTH"
    sh.show_shadows = True
    sh.shadow_intensity = 0.35
    sc.render.film_transparent = False
    world = bpy.data.worlds.new("w")
    sc.world = world
    sc.display_settings.display_device = "sRGB"
    sc.view_settings.view_transform = "Standard"
    objs = []
    for o in job["objects"]:
        nm = o["name"]
        V, F = d[nm + "_V"], d[nm + "_F"]
        ob = _mesh(nm, V, F)
        for p in ob.data.polygons:
            p.use_smooth = True
        if o.get("thickness"):
            m = ob.modifiers.new("solid", "SOLIDIFY")
            m.thickness = float(o["thickness"])
            m.offset = 1.0
        if nm + "_C" in d.files:
            C = d[nm + "_C"]
            attr = ob.data.color_attributes.new("col", "FLOAT_COLOR", "POINT")
            rgba = np.c_[C, np.ones(len(C))].astype(np.float32)
            attr.data.foreach_set("color", rgba.ravel())
        else:
            ob.color = (*_rgb(o.get("color", "#cccccc")), 1.0)
        objs.append(ob)
    sh.color_type = "VERTEX" if any(nm + "_C" in d.files for nm in [o["name"] for o in job["objects"]]) else "OBJECT"
    if sh.color_type == "VERTEX":  # objects without colours get theirs as a flat attribute
        for o, ob in zip(job["objects"], objs):
            if o["name"] + "_C" not in d.files:
                attr = ob.data.color_attributes.new("col", "FLOAT_COLOR", "POINT")
                c = _rgb(o.get("color", "#cccccc")) + [1.0]
                attr.data.foreach_set("color", np.tile(np.array(c, np.float32), len(ob.data.vertices)))
    lo = np.min([np.min(d[o["name"] + "_V"], 0) for o in job["objects"]], 0)
    hi = np.max([np.max(d[o["name"] + "_V"], 0) for o in job["objects"]], 0)
    if job.get("box"):
        lo, hi = np.asarray(job["box"][0]), np.asarray(job["box"][1])
    c = (lo + hi) / 2
    size = float(max(hi[2] - lo[2], hi[0] - lo[0], hi[1] - lo[1])) * 1.08
    cam_d = bpy.data.cameras.new("cam")
    cam_d.type = "ORTHO"
    cam_d.ortho_scale = size
    cam = bpy.data.objects.new("cam", cam_d)
    sc.collection.objects.link(cam)
    sc.camera = cam
    res = int(job.get("resolution", 700))
    sc.render.resolution_x = int(res * job.get("aspect", 0.62))
    sc.render.resolution_y = res
    views = {"front": (0, -1, 0), "side": (-1, 0, 0), "back": (0, 1, 0), "side_r": (1, 0, 0)}
    from mathutils import Vector
    out = []
    for v in job.get("views", ["front", "side", "back"]):
        if isinstance(v, dict):
            dirv = np.asarray(v["dir"], float)
            name = v["name"]
        else:
            dirv = np.asarray(views[v], float)
            name = v
        dirv = dirv / np.linalg.norm(dirv)
        pos = c + dirv * 5
        cam.location = tuple(pos)
        cam.rotation_mode = "QUATERNION"
        look = Vector(tuple(-dirv))
        cam.rotation_quaternion = look.to_track_quat("-Z", "Y")
        sc.render.filepath = job["out_prefix"] + f"_{name}.png"
        bpy.ops.render.render(write_still=True)
        out.append(sc.render.filepath)
    log("rendered", ", ".join(out))


def main():
    path = sys.argv[sys.argv.index("--") + 1]
    job = json.loads(open(path).read())
    import os
    d = np.load(os.path.join(os.path.dirname(path), job.get("data", "in.npz")))
    for ob in list(bpy.data.objects):  # factory startup's cube, camera, light
        bpy.data.objects.remove(ob)
    if job.get("mode", "sim") == "render":
        render(job, d)
    else:
        sim(job, d)


main()
