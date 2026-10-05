"""Blender side of vegetation: build a plant from its arrays (branch tubes as one mesh with a bark shader, twigs as
instances of a few twig meshes through Geometry Nodes), light it, render views.
Run: blender -b --python blender_vegetation.py -- job.json

Job: {"npz", "views": [{"azimuth", "elevation", "out", "size": [w, h], "leaves": bool, "clay": bool, "focus": [x, y, z],
"span": m}], "bark": {...}, "leaf": {"color", "back", "translucency", "roughness"}, "sun": [azimuth, elevation],
"save": path.blend}. The npz: V, F, tan, radius (wood); twig{i}_V/F/mat/col per variant; tw_pos, tw_rot (euler),
tw_scale, tw_var.
"""

import json
import math
import sys

import bpy
import numpy as np
from mathutils import Vector


def _mesh(name, V, F):
    me = bpy.data.meshes.new(name)
    me.vertices.add(len(V))
    me.vertices.foreach_set("co", np.asarray(V, np.float32).ravel())
    if len(F):
        me.loops.add(F.size)
        me.loops.foreach_set("vertex_index", np.asarray(F, np.int32).ravel())
        me.polygons.add(len(F))
        me.polygons.foreach_set("loop_start", np.arange(0, F.size, F.shape[1], dtype=np.int32))
        me.polygons.foreach_set("loop_total", np.full(len(F), F.shape[1], np.int32))
    me.update()
    me.validate()
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    return ob


def _flat(name, col, rough=0.8):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*col, 1)
    b.inputs["Roughness"].default_value = rough
    return m


def _math(N, L, op, a, b=None):
    n = N.new("ShaderNodeMath")
    n.operation = op
    for i, v in enumerate((a, b)):
        if v is None:
            continue
        if isinstance(v, (int, float)):
            n.inputs[i].default_value = v
        else:
            L.new(v, n.inputs[i])
    return n.outputs[0]


def bark_material(name, bark, height):
    """Bark without UVs: a 3D noise stretched along each branch (the mesh's `tan` attribute), so no seams. kinds:
    furrowed (ridges along the branch), lenticel (pale bark with dark dashes round it: birch), plates (blocky).
    Optional base_color under base_height (a birch's black foot), upper_color above upper_from (a pine's orange
    crown wood), twig_color where the wood is thin."""
    kind = bark.get("kind", "furrowed")
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    N, L = m.node_tree.nodes, m.node_tree.links
    bsdf = N["Principled BSDF"]
    geo = N.new("ShaderNodeNewGeometry")
    tan = N.new("ShaderNodeAttribute")
    tan.attribute_name = "tan"
    rad = N.new("ShaderNodeAttribute")
    rad.attribute_name = "radius"
    dot = N.new("ShaderNodeVectorMath")
    dot.operation = "DOT_PRODUCT"
    L.new(geo.outputs["Position"], dot.inputs[0])
    L.new(tan.outputs["Vector"], dot.inputs[1])
    along = N.new("ShaderNodeVectorMath")  # t * (p . t)
    along.operation = "SCALE"
    L.new(tan.outputs["Vector"], along.inputs[0])
    L.new(dot.outputs["Value"], along.inputs["Scale"])
    perp = N.new("ShaderNodeVectorMath")
    perp.operation = "SUBTRACT"
    L.new(geo.outputs["Position"], perp.inputs[0])
    L.new(along.outputs[0], perp.inputs[1])
    ac, al = {"furrowed": (22.0, 2.5), "lenticel": (5.0, 70.0), "plates": (14.0, 6.0)}[kind]
    ac, al = ac * bark.get("scale", 1.0), al * bark.get("scale", 1.0)
    s1 = N.new("ShaderNodeVectorMath")
    s1.operation = "SCALE"
    s1.inputs["Scale"].default_value = ac
    L.new(perp.outputs[0], s1.inputs[0])
    s2 = N.new("ShaderNodeVectorMath")
    s2.operation = "SCALE"
    s2.inputs["Scale"].default_value = al
    L.new(along.outputs[0], s2.inputs[0])
    co = N.new("ShaderNodeVectorMath")
    co.operation = "ADD"
    L.new(s1.outputs[0], co.inputs[0])
    L.new(s2.outputs[0], co.inputs[1])
    if kind == "plates":
        tex = N.new("ShaderNodeTexVoronoi")
        tex.feature = "DISTANCE_TO_EDGE"
        L.new(co.outputs[0], tex.inputs["Vector"])
        val = _math(N, L, "MULTIPLY", tex.outputs["Distance"], 3.0)
    else:
        tex = N.new("ShaderNodeTexNoise")
        tex.inputs["Scale"].default_value = 1.0
        tex.inputs["Detail"].default_value = 5.0
        tex.inputs["Roughness"].default_value = 0.6
        L.new(co.outputs[0], tex.inputs["Vector"])
        val = tex.outputs["Fac"] if "Fac" in tex.outputs else tex.outputs[0]
    ramp = N.new("ShaderNodeValToRGB")
    c1, c2 = bark.get("color", [0.25, 0.2, 0.15]), bark.get("color2", [0.1, 0.08, 0.06])
    if kind == "lenticel":  # mostly the pale colour, dashes of the dark one
        ramp.color_ramp.elements[0].position, ramp.color_ramp.elements[1].position = 0.28, 0.4
        ramp.color_ramp.elements[0].color, ramp.color_ramp.elements[1].color = (*c2, 1), (*c1, 1)
    else:
        ramp.color_ramp.elements[0].position, ramp.color_ramp.elements[1].position = 0.3, 0.7
        ramp.color_ramp.elements[0].color, ramp.color_ramp.elements[1].color = (*c2, 1), (*c1, 1)
    L.new(val, ramp.inputs["Fac"])
    col = ramp.outputs["Color"]
    sep = N.new("ShaderNodeSeparateXYZ")
    L.new(geo.outputs["Position"], sep.inputs[0])
    big = N.new("ShaderNodeTexNoise")
    big.inputs["Scale"].default_value = 3.0
    bigv = big.outputs["Fac"] if "Fac" in big.outputs else big.outputs[0]

    def mix(a, fac, colour):
        mx = N.new("ShaderNodeMix")
        mx.data_type = "RGBA"
        L.new(fac, mx.inputs["Factor"])
        L.new(a, mx.inputs["A"])
        mx.inputs["B"].default_value = (*colour, 1)
        return mx.outputs["Result"]

    def ramp01(v, lo, hi):
        r = N.new("ShaderNodeMapRange")
        r.inputs["From Min"].default_value, r.inputs["From Max"].default_value = lo, hi
        r.clamp = True
        L.new(v, r.inputs["Value"])
        return r.outputs["Result"]

    if bark.get("base_color") is not None:  # the old foot: dark and rough, breaking up with height
        h0 = bark.get("base_height", 1.5)
        zz = _math(N, L, "ADD", sep.outputs["Z"], _math(N, L, "MULTIPLY", bigv, h0 * 1.2))
        fac = ramp01(zz, h0 * 1.6, h0 * 0.6)
        thick = ramp01(rad.outputs["Fac"], 0.03, 0.08)
        col = mix(col, _math(N, L, "MULTIPLY", fac, thick), bark["base_color"])
    if bark.get("upper_color") is not None:
        u0 = bark.get("upper_from", 0.5 * height)
        zz = _math(N, L, "ADD", sep.outputs["Z"], _math(N, L, "MULTIPLY", bigv, 0.15 * height))
        col = mix(col, ramp01(zz, u0, u0 + 0.2 * height), bark["upper_color"])
    if bark.get("twig_color") is not None:
        col = mix(col, ramp01(rad.outputs["Fac"], 0.02, 0.006), bark["twig_color"])
    L.new(col, bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = bark.get("roughness", 0.9)
    bump = N.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = bark.get("bump", 0.6)
    bump.inputs["Distance"].default_value = 0.02
    L.new(val, bump.inputs["Height"])
    L.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    return m


def leaf_material(name, leaf):
    """Leaves: colour x the twig mesh's per-vertex tone x a per-twig tint; light comes through (translucent)."""
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    m.use_backface_culling = False
    N, L = m.node_tree.nodes, m.node_tree.links
    bsdf = N["Principled BSDF"]
    out = N["Material Output"]
    col = N.new("ShaderNodeAttribute")
    col.attribute_name = "col"
    tint = N.new("ShaderNodeAttribute")
    tint.attribute_type = "INSTANCER"
    tint.attribute_name = "tint"
    k = _math(N, L, "MULTIPLY", col.outputs["Fac"], _math(N, L, "ADD", _math(N, L, "MULTIPLY", tint.outputs["Fac"], 0.5), 0.75))
    base = N.new("ShaderNodeVectorMath")
    base.operation = "SCALE"
    base.inputs[0].default_value = leaf.get("color", [0.16, 0.33, 0.08])
    L.new(k, base.inputs["Scale"])
    L.new(base.outputs[0], bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = leaf.get("roughness", 0.45)
    tr = N.new("ShaderNodeBsdfTranslucent")
    tc = N.new("ShaderNodeVectorMath")
    tc.operation = "MULTIPLY"
    tc.inputs[1].default_value = leaf.get("through", [1.6, 1.9, 0.6])
    L.new(base.outputs[0], tc.inputs[0])
    L.new(tc.outputs[0], tr.inputs["Color"])
    mx = N.new("ShaderNodeMixShader")
    mx.inputs[0].default_value = leaf.get("translucency", 0.35)
    L.new(bsdf.outputs[0], mx.inputs[1])
    L.new(tr.outputs[0], mx.inputs[2])
    L.new(mx.outputs[0], out.inputs["Surface"])
    return m


def _instancer(points_ob, proto):
    """Instance `proto` on the points' vertices: rotation from 'rot' (euler), scale from 'size'; 'tint' rides along."""
    ng = bpy.data.node_groups.new("hp_twigs", "GeometryNodeTree")
    ng.interface.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    ng.interface.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    N, L = ng.nodes, ng.links
    gi, go = N.new("NodeGroupInput"), N.new("NodeGroupOutput")
    m2p = N.new("GeometryNodeMeshToPoints")
    inst = N.new("GeometryNodeInstanceOnPoints")
    info = N.new("GeometryNodeObjectInfo")
    info.inputs["Object"].default_value = proto
    rot = N.new("GeometryNodeInputNamedAttribute")
    rot.data_type = "FLOAT_VECTOR"
    rot.inputs["Name"].default_value = "rot"
    size = N.new("GeometryNodeInputNamedAttribute")
    size.data_type = "FLOAT"
    size.inputs["Name"].default_value = "size"
    e2r = N.new("FunctionNodeEulerToRotation")
    L.new(gi.outputs[0], m2p.inputs["Mesh"])
    L.new(m2p.outputs["Points"], inst.inputs["Points"])
    L.new(info.outputs["Geometry"], inst.inputs["Instance"])
    L.new(rot.outputs["Attribute"], e2r.inputs["Euler"])
    L.new(e2r.outputs["Rotation"], inst.inputs["Rotation"])
    L.new(size.outputs["Attribute"], inst.inputs["Scale"])
    L.new(inst.outputs["Instances"], go.inputs[0])
    md = points_ob.modifiers.new("twigs", "NODES")
    md.node_group = ng


def build(job):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    d = np.load(job["npz"])
    lo, hi = d["V"].min(0), d["V"].max(0)
    has_tw = "tw_pos" in d and len(d["tw_pos"])
    if has_tw:
        lo, hi = np.minimum(lo, d["tw_pos"].min(0) - 0.3), np.maximum(hi, d["tw_pos"].max(0) + 0.3)
    bark = bark_material("bark", job.get("bark") or {}, float(hi[2]))
    twig_wood = _flat("twig_wood", (job.get("bark") or {}).get("twig_color") or [0.2, 0.15, 0.1], 0.8)
    leaf = leaf_material("leaf", job.get("leaf") or {})
    clay = _flat("clay", [0.8, 0.78, 0.74], 0.9)
    wood = _mesh("wood", d["V"], d["F"])
    a = wood.data.attributes.new("tan", "FLOAT_VECTOR", "POINT")
    a.data.foreach_set("vector", d["tan"].astype(np.float32).ravel())
    a = wood.data.attributes.new("radius", "FLOAT", "POINT")
    a.data.foreach_set("value", d["radius"].astype(np.float32))
    wood.data.materials.append(bark)
    wood.data.polygons.foreach_set("use_smooth", np.ones(len(wood.data.polygons), bool))
    twig_obs = []
    if has_tw:
        nv = int(d["tw_var"].max()) + 1
        for i in range(nv):
            proto = _mesh(f"twig_{i}", d[f"twig{i}_V"], d[f"twig{i}_F"])
            proto.data.materials.append(twig_wood)
            proto.data.materials.append(leaf)
            proto.data.polygons.foreach_set("material_index", d[f"twig{i}_mat"].astype(np.int32))
            ca = proto.data.attributes.new("col", "FLOAT", "POINT")
            ca.data.foreach_set("value", d[f"twig{i}_col"].astype(np.float32))
            proto.hide_render = True
            proto.hide_viewport = True
            sel = d["tw_var"] == i
            pts = _mesh(f"twigs_{i}", d["tw_pos"][sel], np.zeros((0, 3), np.int32))
            a = pts.data.attributes.new("rot", "FLOAT_VECTOR", "POINT")
            a.data.foreach_set("vector", d["tw_rot"][sel].astype(np.float32).ravel())
            a = pts.data.attributes.new("size", "FLOAT", "POINT")
            a.data.foreach_set("value", d["tw_scale"][sel].astype(np.float32))
            a = pts.data.attributes.new("tint", "FLOAT", "POINT")
            a.data.foreach_set("value", d["tw_tint"][sel].astype(np.float32))
            _instancer(pts, proto)
            twig_obs.append(pts)
    R = float(max(hi[0] - lo[0], hi[1] - lo[1], hi[2]))
    bpy.ops.mesh.primitive_circle_add(vertices=64, radius=3 * R, fill_type="NGON", location=(0, 0, 0))
    ground = bpy.context.object
    ground_mat = _flat("ground", job.get("ground", [0.3, 0.34, 0.2]), 1.0)
    clay_ground = _flat("clay_ground", [0.12, 0.12, 0.12], 1.0)
    ground.data.materials.append(ground_mat)
    sa, se = [math.radians(v) for v in job.get("sun", [135, 50])]
    sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN"))
    sun.data.angle = math.radians(2)
    sun.data.color = job.get("sun_color", [1.0, 0.95, 0.86])
    sc.collection.objects.link(sun)
    dvec = Vector((math.sin(sa) * math.cos(se), math.cos(sa) * math.cos(se), math.sin(se)))
    sun.rotation_euler = dvec.to_track_quat("Z", "Y").to_euler()
    w = bpy.data.worlds.new("w")
    w.use_nodes = True
    bg = w.node_tree.nodes["Background"]
    bg.inputs[1].default_value = job.get("sky_strength", 0.55)
    sc.world = w
    sc.render.engine = "BLENDER_EEVEE"
    sc.view_settings.view_transform = job.get("view_transform", "Khronos PBR Neutral")
    for attr, val in (("use_shadows", True), ("use_raytracing", False)):
        try:
            setattr(sc.eevee, attr, val)
        except Exception:
            pass
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
    sc.collection.objects.link(cam)
    sc.camera = cam
    allp = d["V"] if not has_tw else np.vstack([d["V"], d["tw_pos"]])
    for v in job["views"]:
        az, el = math.radians(v.get("azimuth", 0)), math.radians(v.get("elevation", 0))
        back = Vector((-math.sin(az) * math.cos(el), -math.cos(az) * math.cos(el), math.sin(el)))
        # azimuth 0 looks along +y (the silhouette's x = world x)
        cam.rotation_euler = back.to_track_quat("Z", "Y").to_euler()
        wpx, hpx = v.get("size", [700, 900])
        sc.render.resolution_x, sc.render.resolution_y = wpx, hpx
        right = Vector((math.cos(az), -math.sin(az), 0))
        xs = allp @ np.array(right)
        big = max(wpx, hpx)
        if v.get("focus") is not None:
            cen = Vector(v["focus"])
            need = v.get("span", 3.0) * big / min(wpx, hpx)
        else:
            cen = Vector(right) * float((xs.min() + xs.max()) / 2) + Vector((0, 0, hi[2] / 2))
            need = max(float(xs.max() - xs.min()) * big / wpx, float(hi[2]) * big / hpx) * 1.08
        cam.location = cen + back * (4 * R)
        cam.data.type = "ORTHO"
        cam.data.ortho_scale = need
        cam.data.clip_end = 20 * R
        isclay = bool(v.get("clay"))
        for o in twig_obs:
            o.hide_render = not v.get("leaves", True)
        bg.inputs[0].default_value = (0.035, 0.04, 0.05, 1) if isclay else (*job.get("sky", [0.72, 0.82, 0.97]), 1)
        ground.data.materials[0] = clay_ground if isclay else ground_mat
        wood.data.materials[0] = clay if isclay else bark
        sun.data.energy = 7.0 if isclay else job.get("sun_energy", 5.0)
        sc.view_settings.view_transform = "Standard" if isclay else job.get("view_transform", "Khronos PBR Neutral")
        ground.hide_render = bool(v.get("no_ground"))
        sc.render.film_transparent = bool(v.get("transparent"))
        sc.render.filepath = v["out"]
        bpy.ops.render.render(write_still=True)
        print("@@rendered", v["out"])
    if job.get("save"):
        bpy.ops.wm.save_as_mainfile(filepath=job["save"])


if __name__ == "__main__":
    build(json.loads(open(sys.argv[sys.argv.index("--") + 1]).read()))
