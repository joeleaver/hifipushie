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


def _sim_object(name, X, F, sew, uv, stiff, pins, fab, self_collision, frames, quality=None):
    quality = int(quality or fab.get("quality", 6))
    # The flat pattern is the mesh itself (Basis); the start positions are a shape key faded out over the first
    # frames, and Dynamic Mesh takes the rest lengths from the (now flat) input every frame. (rest_shape_key moves
    # the cloth onto the rest shape at the first frame: the garment started as the flat pattern, measured.)
    if uv.shape[1] == 2:
        flat = np.zeros((len(X), 3))
        flat[:, :2] = uv
    else:
        flat = uv
    shrink = None
    if fab.get("rest", "placed") == "placed":  # rest lengths from the start positions (placed isometrically),
        ob = _mesh(name, X, F, edges=sew)    # corrected per vertex toward the flat pattern's (Shrinking group)
        Fa = np.asarray(F)
        E = np.r_[Fa[:, [0, 1]], Fa[:, [1, 2]], Fa[:, [2, 0]]]
        lf = np.linalg.norm(flat[E[:, 0]] - flat[E[:, 1]], axis=1)
        lx = np.linalg.norm(np.asarray(X)[E[:, 0]] - np.asarray(X)[E[:, 1]], axis=1)
        num, den = np.zeros(len(X)), np.zeros(len(X))
        for k in (0, 1):
            np.add.at(num, E[:, k], lf)
            np.add.at(den, E[:, k], lx)
        r = np.where(den > 0, num / np.maximum(den, 1e-12), 1.0)
        shrink = np.clip(1.0 - r, -0.3, 0.3)
    else:
        ob = _mesh(name, flat, F, edges=sew)
        ob.shape_key_add(name="Basis")
        sk = ob.shape_key_add(name="placed")
        sk.data.foreach_set("co", np.asarray(X, np.float32).ravel())
        sk.value = 1.0
        sk.keyframe_insert("value", frame=1)
        sk.value = 0.0
        sk.keyframe_insert("value", frame=int(fab.get("ease_in", 20)))
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
    # interfacing also stops a piece stretching (a cuff caught on the hand's base stretched 30-70% as plain shirting)
    s.vertex_group_structural_stiffness = "stiff"
    s.tension_stiffness_max = fab["tension"] * fab.get("stiff_tension", 6)
    s.compression_stiffness_max = fab["compression"] * fab.get("stiff_tension", 6)
    s.tension_damping = s.compression_damping = s.shear_damping = 5
    s.bending_damping = 0.5
    s.use_sewing_springs = True
    s.sewing_force_max = fab.get("sewing", 8.0)
    s.use_dynamic_mesh = fab.get("rest", "placed") != "placed"
    if shrink is not None and fab.get("rest_fix") and np.ptp(shrink) > 1e-4:
        lo, hi = float(shrink.min()), float(shrink.max())
        sg = ob.vertex_groups.new(name="shrink")
        wts = (shrink - lo) / (hi - lo)
        for i in range(len(wts)):
            sg.add([i], float(wts[i]), "REPLACE")
        s.vertex_group_shrink = "shrink"
        s.shrink_min, s.shrink_max = lo, hi
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
    # Every garment is dressed first (sewn on the body, then settled under gravity), whatever its final state: a
    # coat sewn in the air with nothing inside it caved in and crumpled into a ball. "hang" then takes the body
    # away and hangs the dressed garment from its pins.
    body = _mesh("body", d["bodyV"], d["bodyT"])
    body.modifiers.new("collision", "COLLISION")
    body.collision.thickness_outer = 0.004
    body.collision.cloth_friction = 5.0
    body.collision.damping = 0.6
    hang = isinstance(state, dict) and "hang" in state
    frames = int(job.get("frames", 90))
    # stage 0 (assembly order, as a shirt is made): the bodice is sewn alone (its shoulder seams close over the
    # shoulders and lift it ~10 cm into place) with the sleeves and collar held where they were placed against the
    # body. Sewn all at once, the rising bodice dragged the sleeves 5-10 cm up the forearms (ruffled cuffs).
    asm = job.get("assemble")
    if asm:
        fixed = np.asarray(asm["fixed"], np.int64)
        fx = np.zeros(len(X), bool)
        fx[fixed] = True
        sew0 = sew[~fx[sew[:, 0]] & ~fx[sew[:, 1]]]
        f0 = int(job.get("sew_frames", 90))
        ob = _sim_object("garment0", X, F, sew0, uv, stiff, fixed, fab, False, f0)
        ob.modifiers["cloth"].settings.effector_weights.gravity = 0.0
        ob.modifiers["cloth"].settings.sewing_force_max = float(job.get("sew_force", 6.0))
        V0, dt = _run(ob, f0)
        TRACE["stage0"] = V0
        bpy.data.objects.remove(ob)
        Xn = V0.copy()
        Xn[fixed] = X[fixed]
        log(f"stage 0 (bodice sewn alone): {f0} frames, {dt:.1f} s, z {V0[~fx, 2].min():.3f}..{V0[~fx, 2].max():.3f}")
        X = Xn
    # stage 1: sew without gravity (the seams close before anything can slide off the shoulders)
    f1 = int(job.get("sew_frames", 90))
    hold = np.asarray((asm or {}).get("hold", []), np.int64)
    ob = _sim_object("garment", X, F, sew, uv, stiff, hold, fab, False, f1)
    ob.modifiers["cloth"].settings.effector_weights.gravity = 0.0
    ob.modifiers["cloth"].settings.sewing_force_max = float(job.get("sew_force", 6.0))  # 0 = unbounded (yanks pieces through the body)
    V, dt = _run(ob, f1, trace=job.get("trace", ()))
    gap = np.linalg.norm(V[sew[:, 0]] - V[sew[:, 1]], axis=1) if len(sew) else np.zeros(1)
    log(f"stage 1 (sew, no gravity): {len(X)} verts, {f1} frames, {dt:.1f} s, seam gaps mean "
        f"{gap.mean() * 1000:.1f} mm, max {gap.max() * 1000:.1f} mm, z {V[:, 2].min():.3f}..{V[:, 2].max():.3f}")
    stages = {"V1": V.copy()}
    # stage 2: gravity, settle (worn)
    bpy.data.objects.remove(ob)
    f2 = int(job.get("worn_frames", 40)) if hang else frames
    # self-collision already while settling: the overlapping fronts passed through each other under gravity and the
    # last stage then locked the tangle in (55 crossings per front)
    ob = _sim_object("garment2", V, F, sew, uv, stiff, [], fab, bool(job.get("self_collision", True)), f2)
    V, dt = _run(ob, f2)
    log(f"stage 2 (gravity, worn): {f2} frames, {dt:.1f} s, z {V[:, 2].min():.3f}..{V[:, 2].max():.3f}")
    n0 = len(V)
    if hang:
        stages["worn"] = V.copy()
        bpy.data.objects.remove(body)
        hook = np.asarray(job["hook"], float)
        # moved so the pins' centre hangs just under the hook; each pin is sewn to an anchor vertex at the hook
        # (loose, pinned: a cloth vertex in the pin group is held at its input position, which moves nothing here
        # but keeps the anchors put)
        V = V + (hook - [0, 0, 0.01] - V[pins].mean(0))
        anchors = hook + (V[pins] - V[pins].mean(0)) * float(job.get("pin_spread", 0.3))
        Va = np.r_[V, anchors]
        sew_h = np.r_[sew, np.c_[pins, n0 + np.arange(len(pins))]]
        stiff_h = np.r_[stiff, np.zeros(len(pins))]
        uv_h = np.r_[np.c_[uv, np.zeros(len(uv))], anchors] if uv.shape[1] == 2 else np.r_[uv, anchors]
        pins_h = n0 + np.arange(len(pins))
        for k, (a_, b_, r) in enumerate(job.get("rack") or []):
            bpy.ops.mesh.primitive_cylinder_add(radius=r, depth=1.0, vertices=24)
            cyl = bpy.context.object
            a_, b_ = np.asarray(a_), np.asarray(b_)
            cyl.location = tuple((a_ + b_) / 2)
            cyl.scale = (1, 1, float(np.linalg.norm(b_ - a_)))
            dirv = (b_ - a_) / np.linalg.norm(b_ - a_)
            cyl.rotation_mode = "QUATERNION"
            from mathutils import Vector
            cyl.rotation_quaternion = Vector((0, 0, 1)).rotation_difference(Vector(tuple(dirv)))
            cyl.modifiers.new("collision", "COLLISION")
        fh = int(job.get("hang_frames", 120))
        bpy.data.objects.remove(ob)
        ob = _sim_object("garment_hang", Va, F, sew_h, uv_h, stiff_h, pins_h, fab, False, fh)
        ob.modifiers["cloth"].settings.sewing_force_max = float(job.get("hang_sew_force", 200.0))  # anchors carry its weight
        V, dt = _run(ob, fh, trace=(1, 2, 5, 10, 30, 60))
        for f in (1, 2, 5, 10, 30, 60):
            T_ = TRACE.get(f"garment_hang_{f}")
            if T_ is not None:
                log(f"  hang frame {f}: z p5 {np.percentile(T_[:n0, 2], 5):.3f} p50 {np.median(T_[:n0, 2]):.3f}")
        log(f"stage 3 (hung): {fh} frames, {dt:.1f} s, z {V[:, 2].min():.3f}..{V[:, 2].max():.3f}")
        X, F_, sew, uv, stiff, pins = Va, F, sew_h, uv_h, stiff_h, pins_h
    if job.get("self_collision", True):
        f3 = int(job.get("settle_frames", 24))
        bpy.data.objects.remove(ob)
        ob = _sim_object("garment3", V, F, sew, uv, stiff, pins if hang else [], fab, True, f3)
        if hang:
            ob.modifiers["cloth"].settings.sewing_force_max = 0.0
        V, dt = _run(ob, f3)
        log(f"stage 4 (self-collision): {f3} frames, {dt:.1f} s")
    gap = np.linalg.norm(V[sew[:, 0]] - V[sew[:, 1]], axis=1) if len(sew) else np.zeros(1)
    log(f"final seam gaps mean {gap.mean() * 1000:.1f} mm, p95 {np.percentile(gap, 95) * 1000:.1f} mm")
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


def show(entries: list) -> list:
    """Garments in the scene (scene.sync): each {"name", "key", "npz" (verts, faces, uv), "color" sRGB hex,
    "thickness", "roughness"} becomes a mesh object in the collection "cloth" with its pattern uv, a Principled
    material and a Solidify (the cloth's thickness, outward). Garments no longer in the spec are removed."""
    coll = bpy.data.collections.get("cloth")
    if coll is None:
        coll = bpy.data.collections.new("cloth")
        bpy.context.scene.collection.children.link(coll)
    want = {e["name"] for e in entries}
    for ob in list(coll.objects):
        if ob.name not in want:
            bpy.data.objects.remove(ob)
    made = []
    for e in entries:
        old = bpy.data.objects.get(e["name"])
        if old is not None and old.get("hp_key") == e["key"]:
            continue
        if old is not None:
            bpy.data.objects.remove(old)
        z = np.load(e["npz"])
        V, F, UV = z["verts"], z["faces"], z["uv"]
        me = bpy.data.meshes.new(e["name"])
        me.from_pydata(V.tolist(), [], F.tolist())
        me.validate()
        uvl = me.uv_layers.new(name="pattern")
        uvl.data.foreach_set("uv", UV[F.ravel()].astype(np.float32).ravel())
        for poly in me.polygons:
            poly.use_smooth = True
        ob = bpy.data.objects.new(e["name"], me)
        coll.objects.link(ob)
        ob["hp_key"] = e["key"]
        sol = ob.modifiers.new("thickness", "SOLIDIFY")
        sol.thickness = float(e.get("thickness", 0.0008))
        sol.offset = 1.0
        mat = bpy.data.materials.new(f"cloth:{e['name']}")
        mat.use_nodes = True
        bsdf = mat.node_tree.nodes.get("Principled BSDF")
        bsdf.inputs["Base Color"].default_value = (*_rgb(e.get("color", "#8fb3d9")), 1.0)
        bsdf.inputs["Roughness"].default_value = float(e.get("roughness", 0.85))
        if "Sheen Weight" in bsdf.inputs:
            bsdf.inputs["Sheen Weight"].default_value = 0.3
        me.materials.append(mat)
        made.append(e["name"])
    return made


if __name__ == "__main__":
    main()
