"""Blender side of vegetation: build a plant from its arrays (branch tubes as one mesh with bark, foliage as
instances through Geometry Nodes: twig meshes, or cards cut round the twig atlas), light it under a real sky, render
views. Run: blender -b --python blender_vegetation.py -- job.json

Job: {"npz", "views": [...], "bark": {kind, color, ..., "maps": {albedo, normal, rough, tile}, "base_maps"},
"leaf": {color, through, translucency, roughness}, "cards": {color, normal, mask} | None, "sun": [azimuth, elevation],
"save": path.blend}. A view: {"out", "size": [w, h], "leaves": bool, "clay": bool} + either ortho ("azimuth",
"elevation", optional "focus" + "span") or perspective ("eye", "look", "fov").
The npz: V, F, tan, radius, uv (wood); twig{i}_V/F/mat/col per mesh variant or card{i}_V/F/uv per card; tw_pos, tw_rot
(euler), tw_scale, tw_var, tw_tint. Colours are sRGB (the repo's convention) and made linear here.
"""

import json
import math
import sys

import bpy
import numpy as np
from mathutils import Vector


def lin(c):
    return tuple(float(x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4) for x in c)


def _mesh(name, V, F, uv=None):
    me = bpy.data.meshes.new(name)
    me.vertices.add(len(V))
    me.vertices.foreach_set("co", np.asarray(V, np.float32).ravel())
    if len(F):
        F = np.asarray(F, np.int32)
        me.loops.add(F.size)
        me.loops.foreach_set("vertex_index", F.ravel())
        me.polygons.add(len(F))
        me.polygons.foreach_set("loop_start", np.arange(0, F.size, F.shape[1], dtype=np.int32))
        me.polygons.foreach_set("loop_total", np.full(len(F), F.shape[1], np.int32))
        if uv is not None:
            layer = me.uv_layers.new(name="uv")
            layer.data.foreach_set("uv", np.asarray(uv, np.float32)[F.ravel()].ravel())
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


def _image(N, path, colour=False):
    t = N.new("ShaderNodeTexImage")
    t.image = bpy.data.images.load(path)
    t.image.colorspace_settings.name = "sRGB" if colour else "Non-Color"
    return t


def bark_material(name, bark, height):
    """Bark: the species' tiling maps (albedo multiplier, normal, roughness) on the branch uv; without maps, a 3D
    noise stretched along each branch (the mesh's `tan` attribute). Colour zones on top: `base_color` (+ `base_maps`)
    under `base_height` (a birch's black fissured foot), `upper_color` above `upper_from` (a pine's orange crown
    wood), `twig_color` where the wood is thin."""
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    N, L = m.node_tree.nodes, m.node_tree.links
    bsdf = N["Principled BSDF"]
    geo = N.new("ShaderNodeNewGeometry")
    rad = N.new("ShaderNodeAttribute")
    rad.attribute_name = "radius"
    sep = N.new("ShaderNodeSeparateXYZ")
    L.new(geo.outputs["Position"], sep.inputs[0])
    big = N.new("ShaderNodeTexNoise")
    big.inputs["Scale"].default_value = 3.0
    bigv = big.outputs["Fac"] if "Fac" in big.outputs else big.outputs[0]

    def mix(a, fac, b, kind="RGBA"):
        mx = N.new("ShaderNodeMix")
        mx.data_type = kind
        L.new(fac, mx.inputs["Factor"])
        for sock, val in (("A", a), ("B", b)):
            s = mx.inputs[sock] if kind == "RGBA" else [i for i in mx.inputs if i.name == sock and i.type == "VALUE"][0]
            if hasattr(val, "links"):
                L.new(val, s)
            else:
                s.default_value = (*val, 1) if kind == "RGBA" else val
        return mx.outputs["Result"] if kind == "RGBA" else [o for o in mx.outputs if o.type == "VALUE"][0]

    def ramp01(v, lo, hi):
        r = N.new("ShaderNodeMapRange")
        r.inputs["From Min"].default_value, r.inputs["From Max"].default_value = lo, hi
        r.clamp = True
        L.new(v, r.inputs["Value"])
        return r.outputs["Result"]

    col = N.new("ShaderNodeRGB")
    col.outputs[0].default_value = (*lin(bark.get("color", [0.5, 0.45, 0.4])), 1)
    col = col.outputs[0]
    fac_base = None
    if bark.get("base_color") is not None:  # the old foot, breaking up with height, only on thick wood
        h0 = bark.get("base_height", 1.5)
        zz = _math(N, L, "ADD", sep.outputs["Z"], _math(N, L, "MULTIPLY", bigv, h0 * 1.2))
        fac_base = _math(N, L, "MULTIPLY", ramp01(zz, h0 * 1.6, h0 * 0.6), ramp01(rad.outputs["Fac"], 0.03, 0.08))
        col = mix(col, fac_base, lin(bark["base_color"]))
    if bark.get("upper_color") is not None:
        u0 = bark.get("upper_from", 0.5 * height)
        zz = _math(N, L, "ADD", sep.outputs["Z"], _math(N, L, "MULTIPLY", bigv, 0.15 * height))
        col = mix(col, ramp01(zz, u0, u0 + 0.2 * height), lin(bark["upper_color"]))
    fac_twig = ramp01(rad.outputs["Fac"], 0.02, 0.006)
    if bark.get("twig_color") is not None:
        col = mix(col, fac_twig, lin(bark["twig_color"]))
    maps = bark.get("maps")
    if maps:
        def tex_set(mp):
            a, n_, r = _image(N, mp["albedo"]), _image(N, mp["normal"]), _image(N, mp["rough"])
            return a.outputs["Color"], n_.outputs["Color"], r.outputs["Color"]
        alb, nrm, rgh = tex_set(maps)
        if bark.get("base_maps") and fac_base is not None:
            a2, n2, r2 = tex_set(bark["base_maps"])
            alb, nrm, rgh = mix(alb, fac_base, a2), mix(nrm, fac_base, n2), mix(rgh, fac_base, r2)
        sc = N.new("ShaderNodeVectorMath")  # the albedo map is a multiplier, stored at half
        sc.operation = "SCALE"
        sc.inputs["Scale"].default_value = 2.0
        L.new(alb, sc.inputs[0])
        mul = N.new("ShaderNodeMix")
        mul.data_type, mul.blend_type = "RGBA", "MULTIPLY"
        mul.inputs["Factor"].default_value = 1.0
        L.new(col, mul.inputs["A"])
        L.new(sc.outputs[0], mul.inputs["B"])
        L.new(mul.outputs["Result"], bsdf.inputs["Base Color"])
        nm = N.new("ShaderNodeNormalMap")
        nm.uv_map = "uv"
        nm.inputs["Strength"].default_value = bark.get("bump", 1.0)
        L.new(nrm, nm.inputs["Color"])
        L.new(nm.outputs["Normal"], bsdf.inputs["Normal"])
        L.new(rgh, bsdf.inputs["Roughness"])
    else:
        tan = N.new("ShaderNodeAttribute")
        tan.attribute_name = "tan"
        dot = N.new("ShaderNodeVectorMath")
        dot.operation = "DOT_PRODUCT"
        L.new(geo.outputs["Position"], dot.inputs[0])
        L.new(tan.outputs["Vector"], dot.inputs[1])
        along = N.new("ShaderNodeVectorMath")
        along.operation = "SCALE"
        L.new(tan.outputs["Vector"], along.inputs[0])
        L.new(dot.outputs["Value"], along.inputs["Scale"])
        perp = N.new("ShaderNodeVectorMath")
        perp.operation = "SUBTRACT"
        L.new(geo.outputs["Position"], perp.inputs[0])
        L.new(along.outputs[0], perp.inputs[1])
        s1 = N.new("ShaderNodeVectorMath")
        s1.operation = "SCALE"
        s1.inputs["Scale"].default_value = 22.0
        L.new(perp.outputs[0], s1.inputs[0])
        s2 = N.new("ShaderNodeVectorMath")
        s2.operation = "SCALE"
        s2.inputs["Scale"].default_value = 2.5
        L.new(along.outputs[0], s2.inputs[0])
        co = N.new("ShaderNodeVectorMath")
        co.operation = "ADD"
        L.new(s1.outputs[0], co.inputs[0])
        L.new(s2.outputs[0], co.inputs[1])
        tex = N.new("ShaderNodeTexNoise")
        tex.inputs["Detail"].default_value = 5.0
        L.new(co.outputs[0], tex.inputs["Vector"])
        val = tex.outputs["Fac"] if "Fac" in tex.outputs else tex.outputs[0]
        col = mix(col, ramp01(val, 0.6, 0.35), lin(bark.get("color2", [0.2, 0.17, 0.14])))
        L.new(col, bsdf.inputs["Base Color"])
        bsdf.inputs["Roughness"].default_value = bark.get("roughness", 0.9)
        bump = N.new("ShaderNodeBump")
        bump.inputs["Strength"].default_value = 0.6
        bump.inputs["Distance"].default_value = 0.02
        L.new(val, bump.inputs["Height"])
        L.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    return m


def _leaf_out(m, N, L, base, alpha, through, rough, leaf):
    """Leaf shading: Principled + light coming through (Translucent), mixed by `through`."""
    bsdf = N["Principled BSDF"]
    out = N["Material Output"]
    L.new(base, bsdf.inputs["Base Color"])
    if hasattr(rough, "links"):
        L.new(rough, bsdf.inputs["Roughness"])
    else:
        bsdf.inputs["Roughness"].default_value = rough
    tr = N.new("ShaderNodeBsdfTranslucent")
    tc = N.new("ShaderNodeVectorMath")
    tc.operation = "MULTIPLY"
    tc.inputs[1].default_value = leaf.get("through", [1.6, 1.9, 0.6])
    L.new(base, tc.inputs[0])
    L.new(tc.outputs[0], tr.inputs["Color"])
    mx = N.new("ShaderNodeMixShader")
    t = leaf.get("translucency", 0.35)
    if through is None:
        mx.inputs[0].default_value = t
    else:
        L.new(_math(N, L, "MULTIPLY", through, t), mx.inputs[0])
    L.new(bsdf.outputs[0], mx.inputs[1])
    L.new(tr.outputs[0], mx.inputs[2])
    last = mx.outputs[0]
    if alpha is not None:  # cut out by the atlas's alpha
        tp = N.new("ShaderNodeBsdfTransparent")
        am = N.new("ShaderNodeMixShader")
        L.new(_math(N, L, "GREATER_THAN", alpha, leaf.get("alpha_cut", 0.4)), am.inputs[0])
        L.new(tp.outputs[0], am.inputs[1])
        L.new(last, am.inputs[2])
        last = am.outputs[0]
        for attr, val in (("surface_render_method", "DITHERED"), ("use_transparent_shadow", True),
                          ("blend_method", "HASHED")):
            try:
                setattr(m, attr, val)
            except Exception:
                pass
    L.new(last, out.inputs["Surface"])
    m.use_backface_culling = False


def _tint(N, L):
    tint = N.new("ShaderNodeAttribute")
    tint.attribute_type = "INSTANCER"
    tint.attribute_name = "tint"
    return _math(N, L, "ADD", _math(N, L, "MULTIPLY", tint.outputs["Fac"], 0.5), 0.75)


def leaf_material(name, leaf):
    """Mesh leaves: colour x the twig mesh's per-vertex tone x a per-twig tint."""
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    N, L = m.node_tree.nodes, m.node_tree.links
    col = N.new("ShaderNodeAttribute")
    col.attribute_name = "col"
    base = N.new("ShaderNodeVectorMath")
    base.operation = "SCALE"
    base.inputs[0].default_value = lin(leaf.get("color", [0.45, 0.6, 0.3]))
    L.new(_math(N, L, "MULTIPLY", col.outputs["Fac"], _tint(N, L)), base.inputs["Scale"])
    _leaf_out(m, N, L, base.outputs[0], None, None, leaf.get("roughness", 0.45), leaf)
    return m


def card_material(name, leaf, cards):
    """Cards: the atlas's colour (x a per-twig tint x its shade), alpha, normal, and its mask's R = where light comes
    through, G = roughness."""
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    N, L = m.node_tree.nodes, m.node_tree.links
    c, n_, k = _image(N, cards["color"], True), _image(N, cards["normal"]), _image(N, cards["mask"])
    sepm = N.new("ShaderNodeSeparateColor")
    L.new(k.outputs["Color"], sepm.inputs[0])
    base = N.new("ShaderNodeVectorMath")
    base.operation = "SCALE"
    L.new(c.outputs["Color"], base.inputs[0])
    L.new(_math(N, L, "MULTIPLY", _tint(N, L), sepm.outputs[2]), base.inputs["Scale"])
    nm = N.new("ShaderNodeNormalMap")
    nm.uv_map = "uv"
    # (off by default: on instanced cards the tangent frame turned leaves near black from some sides)
    nm.inputs["Strength"].default_value = leaf.get("card_normal", 0.0)
    L.new(n_.outputs["Color"], nm.inputs["Color"])
    L.new(nm.outputs["Normal"], N["Principled BSDF"].inputs["Normal"])
    _leaf_out(m, N, L, base.outputs[0], c.outputs["Alpha"], sepm.outputs[0], sepm.outputs[1], leaf)
    return m


def ground_material(name, ground):
    """Grass seen from standing height: two greens and a dry tone in patches, a fine bump."""
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    N, L = m.node_tree.nodes, m.node_tree.links
    bsdf = N["Principled BSDF"]
    co = N.new("ShaderNodeTexCoord")
    n1 = N.new("ShaderNodeTexNoise")
    n1.inputs["Scale"].default_value = 0.35
    n1.inputs["Detail"].default_value = 6.0
    n2 = N.new("ShaderNodeTexNoise")
    n2.inputs["Scale"].default_value = 9.0
    n2.inputs["Detail"].default_value = 4.0
    L.new(co.outputs["Object"], n1.inputs["Vector"])
    L.new(co.outputs["Object"], n2.inputs["Vector"])
    r = N.new("ShaderNodeValToRGB")
    e = r.color_ramp.elements
    e[0].position, e[1].position = 0.3, 0.7
    e[0].color = (*lin(ground.get("color", [0.33, 0.42, 0.16])), 1)
    e[1].color = (*lin(ground.get("color2", [0.44, 0.5, 0.22])), 1)
    mid = r.color_ramp.elements.new(0.52)
    mid.color = (*lin(ground.get("dry", [0.5, 0.47, 0.25])), 1)
    f = lambda t: t.outputs["Fac"] if "Fac" in t.outputs else t.outputs[0]
    L.new(_math(N, L, "ADD", _math(N, L, "MULTIPLY", f(n1), 0.75), _math(N, L, "MULTIPLY", f(n2), 0.25)), r.inputs["Fac"])
    L.new(r.outputs["Color"], bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.9
    bump = N.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.5
    bump.inputs["Distance"].default_value = 0.05
    L.new(f(n2), bump.inputs["Height"])
    L.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
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


def _world(sc, job):
    """A clear sky (Blender's sky texture) with its sun where the sun lamp is; a flat colour if the build has none."""
    w = bpy.data.worlds.new("w")
    w.use_nodes = True
    N, L = w.node_tree.nodes, w.node_tree.links
    bg = N["Background"]
    sky = None
    try:
        sky = N.new("ShaderNodeTexSky")
        if hasattr(sky, "sun_disc"):
            sky.sun_disc = False
        for k_, v_ in (("dust_density", 0.3), ("air_density", 1.0)):
            if hasattr(sky, k_):
                setattr(sky, k_, v_)
        L.new(sky.outputs["Color"], bg.inputs["Color"])
        bg.inputs[1].default_value = job.get("sky_strength", 0.07)
    except Exception:
        bg.inputs[0].default_value = (*job.get("sky", [0.5, 0.66, 0.9]), 1)
        bg.inputs[1].default_value = 0.6
    sc.world = w
    return w, bg, sky


def add_plant(pj, tag, clay):
    """One plant from its npz at pj["at"] ([x, y], turned pj["yaw"] deg): returns its objects and its points."""
    d = np.load(pj["npz"])
    at = np.array(list(pj.get("at", [0, 0])) + [float(pj.get("z", 0.0))])
    yaw = math.radians(pj.get("yaw", 0.0))
    c, s_ = math.cos(yaw), math.sin(yaw)
    Rz = np.array([[c, -s_, 0], [s_, c, 0], [0, 0, 1.0]])
    place = lambda P: P @ Rz.T + at
    V = place(d["V"])
    has_tw = "tw_pos" in d and len(d["tw_pos"])
    bk = pj.get("bark") or {}
    bark = bark_material(f"bark{tag}", bk, float(V[:, 2].max()))
    twig_wood = _flat(f"twig_wood{tag}", lin(bk.get("twig_color") or [0.45, 0.4, 0.35]), 0.8)
    wood = _mesh(f"wood{tag}", V, d["F"], d["uv"] if "uv" in d else None)
    a = wood.data.attributes.new("tan", "FLOAT_VECTOR", "POINT")
    a.data.foreach_set("vector", (d["tan"] @ Rz.T).astype(np.float32).ravel())
    a = wood.data.attributes.new("radius", "FLOAT", "POINT")
    a.data.foreach_set("value", d["radius"].astype(np.float32))
    wood.data.materials.append(bark)
    wood.data.polygons.foreach_set("use_smooth", np.ones(len(wood.data.polygons), bool))
    twig_obs = []
    pts_all = [V]
    if has_tw:
        from mathutils import Euler, Matrix
        cards = pj.get("cards")
        mat = card_material(f"cards{tag}", pj.get("leaf") or {}, cards) if cards else leaf_material(f"leaf{tag}", pj.get("leaf") or {})
        nv = int(d["tw_var"].max()) + 1
        tw_pos = place(d["tw_pos"])
        pts_all.append(tw_pos)
        for i in range(nv):
            if cards:
                proto = _mesh(f"card{tag}_{i}", d[f"card{i}_V"], d[f"card{i}_F"], d[f"card{i}_uv"])
                proto.data.materials.append(mat)
                proto.data.polygons.foreach_set("use_smooth", np.ones(len(proto.data.polygons), bool))
            else:
                proto = _mesh(f"twig{tag}_{i}", d[f"twig{i}_V"], d[f"twig{i}_F"])
                proto.data.materials.append(twig_wood)
                proto.data.materials.append(mat)
                proto.data.polygons.foreach_set("material_index", d[f"twig{i}_mat"].astype(np.int32))
                ca = proto.data.attributes.new("col", "FLOAT", "POINT")
                ca.data.foreach_set("value", d[f"twig{i}_col"].astype(np.float32))
            proto.hide_render = True
            proto.hide_viewport = True
            sel = d["tw_var"] == i
            pts = _mesh(f"twigs{tag}_{i}", d["tw_pos"][sel], np.zeros((0, 3), np.int32))
            for nm_, kind, key, field in (("rot", "FLOAT_VECTOR", "tw_rot", "vector"), ("size", "FLOAT", "tw_scale", "value"),
                                          ("tint", "FLOAT", "tw_tint", "value")):
                at_ = pts.data.attributes.new(nm_, kind, "POINT")
                at_.data.foreach_set(field, d[key][sel].astype(np.float32).ravel())
            _instancer(pts, proto)
            pts.location = at.tolist()  # (the instances' own frames ride the object's turn)
            pts.rotation_euler = (0, 0, yaw)
            twig_obs.append(pts)
    return {"wood": wood, "bark": bark, "twigs": twig_obs, "points": np.vstack(pts_all)}


def build(job):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    clay = _flat("clay", [0.8, 0.78, 0.74], 0.9)
    plants = [add_plant(pj, f"_{i}" if i else "", clay) for i, pj in enumerate(job["plants"])]
    allp = np.vstack([p_["points"] for p_ in plants])
    lo, hi = allp.min(0) - 0.3, allp.max(0) + 0.3
    twig_obs = [o for p_ in plants for o in p_["twigs"]]
    R = float(max(hi[0] - lo[0], hi[1] - lo[1], hi[2]))
    bpy.ops.mesh.primitive_circle_add(vertices=64, radius=max(60 * R, 400.0), fill_type="NGON", location=(0, 0, 0))
    ground = bpy.context.object
    gj = job.get("ground") or {}
    if gj.get("slope"):  # a hillside: the ground falls toward `toward` at `slope` deg (the plant's foot stays put)
        tw_ = Vector(list(gj.get("toward", [1, 0])) + [0]).normalized()
        axis = Vector((0, 0, 1)).cross(tw_)
        from mathutils import Matrix
        ground.rotation_euler = Matrix.Rotation(math.radians(gj["slope"]), 4, axis).to_euler()
    ground_mat = ground_material("ground", job.get("ground") or {})
    clay_ground = _flat("clay_ground", [0.12, 0.12, 0.12], 1.0)
    ground.data.materials.append(ground_mat)
    sa, se = [math.radians(v) for v in job.get("sun", [140, 42])]
    sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN"))
    sun.data.angle = math.radians(1.5)
    sun.data.color = job.get("sun_color", [1.0, 0.96, 0.88])
    sc.collection.objects.link(sun)
    w, bg, sky = _world(sc, job)

    def aim_sun(az_deg, el_deg):
        a_, e_ = math.radians(az_deg), math.radians(el_deg)
        dvec = Vector((math.sin(a_) * math.cos(e_), math.cos(a_) * math.cos(e_), math.sin(e_)))
        sun.rotation_euler = dvec.to_track_quat("Z", "Y").to_euler()
        if sky is not None:
            for k_, v_ in (("sun_elevation", e_), ("sun_rotation", a_)):
                if hasattr(sky, k_):
                    setattr(sky, k_, v_)

    aim_sun(math.degrees(sa), math.degrees(se))
    # the ground's bounce: EEVEE has none, and shade lit by the sky alone turns every leaf blue
    fill = bpy.data.objects.new("bounce", bpy.data.lights.new("bounce", "SUN"))
    fill.data.color = job.get("bounce_color", [0.75, 0.8, 0.45])
    fill.data.use_shadow = False
    sc.collection.objects.link(fill)
    fill.rotation_euler = Vector((0, 0, -1)).to_track_quat("Z", "Y").to_euler()
    sc.render.engine = "BLENDER_EEVEE"
    for attr, val in (("use_shadows", True), ("use_raytracing", False)):
        try:
            setattr(sc.eevee, attr, val)
        except Exception:
            pass
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
    sc.collection.objects.link(cam)
    sc.camera = cam
    sky_links = [(l.from_socket, l.to_socket) for l in w.node_tree.links if l.to_socket == bg.inputs[0]]
    for v in job["views"]:
        wpx, hpx = v.get("size", [700, 900])
        sc.render.resolution_x, sc.render.resolution_y = wpx, hpx
        if v.get("eye") is not None:
            eye, look = Vector(v["eye"]), Vector(v["look"])
            cam.location = eye
            cam.rotation_euler = (eye - look).to_track_quat("Z", "Y").to_euler()
            cam.data.type = "PERSP"
            cam.data.sensor_fit = "VERTICAL"
            cam.data.angle = math.radians(v.get("fov", 40))
            cam.data.clip_start, cam.data.clip_end = 0.05, max(100 * R, 1000.0)
        else:
            az, el = math.radians(v.get("azimuth", 0)), math.radians(v.get("elevation", 0))
            back = Vector((-math.sin(az) * math.cos(el), -math.cos(az) * math.cos(el), math.sin(el)))
            # azimuth 0 looks along +y (the silhouette's x = world x)
            cam.rotation_euler = back.to_track_quat("Z", "Y").to_euler()
            right = Vector((math.cos(az), -math.sin(az), 0))
            xs = allp @ np.array(right)
            big = max(wpx, hpx)
            if v.get("focus") is not None:
                cen = Vector(v["focus"])
                need = v.get("span", 3.0) * big / min(wpx, hpx)
            else:
                cen = Vector(right) * float((xs.min() + xs.max()) / 2) + Vector((0, 0, hi[2] / 2))
                need = max(float(xs.max() - xs.min()) * big / wpx, float(hi[2]) * big / hpx) * 1.08
            cam.location = cen + back * (4 * R + 10)
            cam.data.type = "ORTHO"
            cam.data.ortho_scale = need
            cam.data.clip_start, cam.data.clip_end = 0.1, 20 * R + 50
        isclay = bool(v.get("clay"))
        if v.get("sun"):
            aim_sun(*v["sun"])
        fill.data.energy = 0.0 if isclay else job.get("bounce", 0.7)
        for o in twig_obs:
            o.hide_render = not v.get("leaves", True)
        for l in list(w.node_tree.links):
            if l.to_socket == bg.inputs[0]:
                w.node_tree.links.remove(l)
        if isclay:
            bg.inputs[0].default_value = (0.035, 0.04, 0.05, 1)
            bg.inputs[1].default_value = 0.9
        else:
            for a_, b_ in sky_links:
                w.node_tree.links.new(a_, b_)
            bg.inputs[1].default_value = job.get("sky_strength", 0.07) if sky_links else 0.6
        ground.data.materials[0] = clay_ground if isclay else ground_mat
        for p_ in plants:
            p_["wood"].data.materials[0] = clay if isclay else p_["bark"]
        sun.data.energy = 7.0 if isclay else job.get("sun_energy", 3.6)
        sc.view_settings.view_transform = "Standard" if isclay else job.get("view_transform", "AgX")
        sc.view_settings.exposure = 0.0 if isclay else job.get("exposure", 0.0)
        ground.hide_render = bool(v.get("no_ground"))
        sc.render.film_transparent = bool(v.get("transparent"))
        sc.render.filepath = v["out"]
        bpy.ops.render.render(write_still=True)
        print("@@rendered", v["out"])
    if job.get("save"):
        bpy.ops.wm.save_as_mainfile(filepath=job["save"])


if __name__ == "__main__":
    build(json.loads(open(sys.argv[sys.argv.index("--") + 1]).read()))
