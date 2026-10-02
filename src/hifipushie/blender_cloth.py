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


def _sim_object(name, X, F, sew, uv, stiff, pins, fab, self_collision, frames, quality=None, start=None,
                ease=15, self_only=None):
    """start: positions the cloth starts at while its rest shape stays X (the refine stage: the settled coarse garment
    carried onto a finer mesh whose rest is its own placement): X is the Basis, `start` a shape key faded out over
    `ease` frames, Dynamic Mesh takes the rest lengths from the input every frame. self_only: per-vertex bool, the
    only vertices whose triangles self-collide (the rest go in Blender's exclusion group)."""
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
    if start is not None:
        ob = _mesh(name, X, F, edges=sew)
        ob.shape_key_add(name="Basis")
        sk = ob.shape_key_add(name="start")
        sk.data.foreach_set("co", np.asarray(start, np.float32).ravel())
        sk.value = 1.0
        sk.keyframe_insert("value", frame=1)
        sk.value = 0.0
        sk.keyframe_insert("value", frame=max(2, int(ease)))
    elif fab.get("rest", "placed") == "placed":  # rest lengths from the start positions (placed isometrically),
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
    s.use_dynamic_mesh = start is not None or fab.get("rest", "placed") != "placed"
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
    if self_collision and self_only is not None and not np.all(self_only):
        xg = ob.vertex_groups.new(name="no_self")
        out = np.where(~np.asarray(self_only, bool))[0]
        if len(out):
            xg.add([int(i) for i in out], 1.0, "REPLACE")
        cs.vertex_group_self_collisions = "no_self"
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
        if f % 10 == 0 or f == frames:
            print(f"cloth: progress {ob.name} {f}/{frames} {time.time() - t:.0f}s", flush=True)
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
    # self-collision while sewing too: without it the bodice rising ~10 cm over the shoulders and the sleeves closing
    # passed folds through each other (fronts, sleeves) and the later stages locked the tangles in (every shirt CORRUPT)
    sew_self = bool(job.get("self_collision_sew", True)) and bool(job.get("self_collision", True))
    if asm:
        fixed = np.asarray(asm["fixed"], np.int64)
        fx = np.zeros(len(X), bool)
        fx[fixed] = True
        sew0 = sew[~fx[sew[:, 0]] & ~fx[sew[:, 1]]]
        f0 = int(job.get("sew_frames", 90))
        ob = _sim_object("garment0", X, F, sew0, uv, stiff, fixed, fab, sew_self, f0)
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
    ob = _sim_object("garment", X, F, sew, uv, stiff, hold, fab, sew_self, f1)
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
        _rack(job.get("rack") or [])
        fh = int(job.get("hang_frames", 120))
        bpy.data.objects.remove(ob)
        ob = _sim_object("garment_hang", Va, F, sew_h, uv_h, stiff_h, pins_h, fab, bool(job.get("self_collision", True)), fh)  # self-collision: hung without it the coat folded through itself (thousands of crossings)
        # the sewing force while hung: 200 (meant for the anchors to carry the weight) also drove every seam and drew the coat
        # up into a sack (its hem rose 0.65 -> 1.12 m, pattern strain p95 105%); at the sewing force (6) the anchors hold it
        ob.modifiers["cloth"].settings.sewing_force_max = float(job.get("hang_sew_force", job.get("sew_force", 6.0)))
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


def refine(job, d):
    """The refine stage (what garment artists do after blocking a drape at a coarse particle distance): the settled
    coarse garment carried onto the fine mesh (`S`, start) with the fine mesh's own placement as its rest shape (`X`),
    settled with gravity and self-collision while the rest lengths ease from the start's to the placement's. Worn: the
    body is the collider. Hung (`pins`): the pin patch held where it hangs, rack colliders, no body."""
    fab = job["fabric"]
    X, S, F, uv = d["X"], d["S"], d["F"], d["uv"]
    sew = np.r_[d["sew"], d["stitch"]] if len(d["stitch"]) else d["sew"]
    pins = np.asarray(job.get("pins") or [], dtype=np.int64)
    bpy.context.scene.render.fps = 24
    if job.get("body", True):
        body = _mesh("body", d["bodyV"], d["bodyT"])
        body.modifiers.new("collision", "COLLISION")
        body.collision.thickness_outer = 0.004
        body.collision.cloth_friction = 5.0
        body.collision.damping = 0.6
    _rack(job.get("rack") or [])
    X = np.asarray(X, float).copy()
    if len(pins):  # held where they hang: their input never moves
        X[pins] = S[pins]
    frames = int(job.get("refine_frames", 40))
    ob = _sim_object("garment_fine", X, F, sew, uv, d["stiff"], pins, fab, bool(job.get("self_collision", True)),
                     frames, start=S, ease=int(job.get("refine_ease", 15)))
    if len(pins):
        ob.modifiers["cloth"].settings.sewing_force_max = 0.0
    V, dt = _run(ob, frames)
    gap = np.linalg.norm(V[sew[:, 0]] - V[sew[:, 1]], axis=1) if len(sew) else np.zeros(1)
    log(f"refine ({len(X)} verts): {frames} frames, {dt:.1f} s, seam gaps mean {gap.mean() * 1000:.1f} mm, "
        f"p95 {np.percentile(gap, 95) * 1000:.1f} mm")
    np.savez(job["out"], V=V)


def _rack(rack):
    from mathutils import Vector
    for a_, b_, r in rack:
        bpy.ops.mesh.primitive_cylinder_add(radius=r, depth=1.0, vertices=24)
        cyl = bpy.context.object
        a_, b_ = np.asarray(a_), np.asarray(b_)
        cyl.location = tuple((a_ + b_) / 2)
        cyl.scale = (1, 1, float(np.linalg.norm(b_ - a_)))
        dirv = (b_ - a_) / np.linalg.norm(b_ - a_)
        cyl.rotation_mode = "QUATERNION"
        cyl.rotation_quaternion = Vector((0, 0, 1)).rotation_difference(Vector(tuple(dirv)))
        cyl.modifiers.new("collision", "COLLISION")
        # the default outer thickness (2 cm) made a hanger bar 3 cm thick inside the shoulders: it pushed the coat up
        # off it into a sack
        cyl.collision.thickness_outer = 0.003
        cyl.collision.cloth_friction = 5.0


def render(job, d):
    """Objects from render.npz: for each name in job["objects"]: <name>_V, <name>_F, optional <name>_C (per-vertex
    RGB, linear), job colours; orthographic views front/side/back (+ an optional perspective three-quarter)."""
    sc = bpy.context.scene
    if job.get("textured"):
        return _render_textured(job, d)
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


def _material(name, color, roughness=0.85, maps=None, sheen=0.3):
    """A Principled cloth material: base colour (or its basecolor map on the "pattern" uv), its normal map, sheen."""
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = (*_rgb(color), 1.0)
    bsdf.inputs["Roughness"].default_value = float(roughness)
    if "Sheen Weight" in bsdf.inputs:
        bsdf.inputs["Sheen Weight"].default_value = sheen
    maps = maps or {}
    rgb = nt.nodes.new("ShaderNodeRGB")  # the garment's colour, a person can change it (pulled back: `read`)
    rgb.name = "hp_color"
    rgb.outputs[0].default_value = (*_rgb(color), 1.0)
    if maps.get("shade"):  # the detail's shading (grooves darker, stitches) times the colour
        tex = nt.nodes.new("ShaderNodeTexImage")
        tex.image = bpy.data.images.load(maps["shade"], check_existing=True)
        tex.image.colorspace_settings.name = "Non-Color"
        mix = nt.nodes.new("ShaderNodeMix")
        mix.data_type = "RGBA"
        mix.blend_type = "MULTIPLY"
        mix.inputs["Factor"].default_value = 1.0
        nt.links.new(rgb.outputs[0], mix.inputs[6])
        nt.links.new(tex.outputs["Color"], mix.inputs[7])
        nt.links.new(mix.outputs[2], bsdf.inputs["Base Color"])
    elif maps.get("basecolor"):
        tex = nt.nodes.new("ShaderNodeTexImage")
        tex.image = bpy.data.images.load(maps["basecolor"], check_existing=True)
        nt.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
    else:
        nt.links.new(rgb.outputs[0], bsdf.inputs["Base Color"])
    mat["hp_set"] = [*_rgb(color), float(roughness)]
    if maps.get("normal"):
        tex = nt.nodes.new("ShaderNodeTexImage")
        tex.image = bpy.data.images.load(maps["normal"], check_existing=True)
        tex.image.colorspace_settings.name = "Non-Color"
        nm = nt.nodes.new("ShaderNodeNormalMap")
        nm.uv_map = "pattern"
        nm.inputs["Strength"].default_value = 1.0
        nt.links.new(tex.outputs["Color"], nm.inputs["Color"])
        nt.links.new(nm.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


def _render_textured(job, d):
    """EEVEE views of objects with their maps (detail close-ups): a key sun, a fill, a grey world."""
    from mathutils import Vector
    sc = bpy.context.scene
    sc.render.engine = "BLENDER_EEVEE" if "BLENDER_EEVEE" in [e.identifier for e in
                                                             bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items] \
        else "BLENDER_EEVEE_NEXT"
    sc.view_settings.view_transform = "Standard"
    world = bpy.data.worlds.new("w")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.32, 0.33, 0.35, 1)
    world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.6
    sc.world = world
    for k, (rot, en) in enumerate((((50, 10, -35), 3.0), ((70, 0, 150), 1.0))):
        ld = bpy.data.lights.new(f"sun{k}", "SUN")
        ld.energy = en
        lo = bpy.data.objects.new(f"sun{k}", ld)
        lo.rotation_euler = tuple(math.radians(a) for a in rot)
        sc.collection.objects.link(lo)
    for o in job["objects"]:
        nm = o["name"]
        V, F = d[nm + "_V"], d[nm + "_F"]
        ob = _mesh(nm, V, F)
        for p in ob.data.polygons:
            p.use_smooth = True
        if nm + "_UV" in d.files:
            UV = d[nm + "_UV"]
            uvl = ob.data.uv_layers.new(name="pattern")
            uvl.data.foreach_set("uv", UV[np.asarray(F).ravel()].astype(np.float32).ravel())
        if o.get("thickness"):
            m = ob.modifiers.new("solid", "SOLIDIFY")
            m.thickness = float(o["thickness"])
            m.offset = 1.0
        ob.data.materials.append(_material(f"m_{nm}", o.get("color", "#cccccc"), 0.85 if o.get("maps") else 0.6,
                                           o.get("maps"), sheen=0.3 if o.get("maps") else 0.0))
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
    for v in job.get("views", ["front"]):
        dirv = np.asarray(v["dir"] if isinstance(v, dict) else views[v], float)
        name = v["name"] if isinstance(v, dict) else v
        dirv = dirv / np.linalg.norm(dirv)
        cam.location = tuple(c + dirv * 5)
        cam.rotation_mode = "QUATERNION"
        cam.rotation_quaternion = Vector(tuple(-dirv)).to_track_quat("-Z", "Y")
        sc.render.filepath = job["out_prefix"] + f"_{name}.png"
        bpy.ops.render.render(write_still=True)
    log("rendered textured")


def read(folder):
    """What a person changed on the garments in the scene (for scene.pull): per cloth object whose mesh moved from
    what the sync wrote (`hp_npz`) its vertices in <folder>/cloth_<name>.npz, and material colour/roughness changed
    from `hp_set`."""
    import os
    out = {}
    coll = bpy.data.collections.get("cloth")
    if coll is None:
        return out
    for ob in coll.objects:
        if ob.type != "MESH" or not ob.get("hp_key"):
            continue
        st = {"key": ob["hp_key"]}
        me = ob.data
        V = np.zeros(len(me.vertices) * 3, np.float32)
        me.vertices.foreach_get("co", V)
        V = V.reshape(-1, 3)
        M = np.array(ob.matrix_world)
        if np.abs(M - np.eye(4)).max() > 1e-6:  # the object moved as a whole: its vertices where they stand
            V = (np.c_[V, np.ones(len(V))] @ M.T)[:, :3]
        src = ob.get("hp_npz")
        if src and os.path.exists(src):
            was = np.load(src)["verts"]
            if was.shape != V.shape or np.abs(was - V).max() > 3e-4:
                f = os.path.join(folder, f"cloth_{ob.name.replace(':', '_')}.npz")
                np.savez(f, verts=V)
                st["verts"] = f
        mat = me.materials[0] if len(me.materials) else None
        if mat is not None and mat.node_tree and mat.get("hp_set"):
            bsdf = mat.node_tree.nodes.get("Principled BSDF")
            was = list(mat["hp_set"])
            node = mat.node_tree.nodes.get("hp_color")
            col = list((node.outputs[0] if node else bsdf.inputs["Base Color"]).default_value)[:3]
            rough = float(bsdf.inputs["Roughness"].default_value)
            if max(abs(a - b) for a, b in zip(col, was[:3])) > 1e-4:
                srgb = [12.92 * c if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055 for c in col]
                st["color"] = "#" + "".join(f"{int(round(max(0, min(1, c)) * 255)):02x}" for c in srgb)
            if abs(rough - was[3]) > 1e-4:
                st["roughness"] = rough
        if len(st) > 1:
            out[ob.name] = st
    return out


def main():
    path = sys.argv[sys.argv.index("--") + 1]
    job = json.loads(open(path).read())
    import os
    d = np.load(os.path.join(os.path.dirname(path), job.get("data", "in.npz")))
    for ob in list(bpy.data.objects):  # factory startup's cube, camera, light
        bpy.data.objects.remove(ob)
    if job.get("mode", "sim") == "render":
        render(job, d)
    elif job.get("mode") == "refine":
        refine(job, d)
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
        ob["hp_npz"] = e["npz"]
        mat = _material(f"cloth:{e['name']}", e.get("color", "#8fb3d9"), float(e.get("roughness", 0.85)),
                        e.get("maps"))
        me.materials.append(mat)
        made.append(e["name"])
    return made


if __name__ == "__main__":
    main()
