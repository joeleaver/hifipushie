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
import os
import math
import sys

import bpy
import numpy as np
from mathutils import Matrix, Vector


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


HAZE: dict = {}  # {"distance": m, "color": [r, g, b] (as seen), "strength"}: set from the job before materials are made


def _hazed(N, L, shader):
    """Air between the eye and the surface: the shader mixed toward the haze's colour by 1 - exp(-distance / haze
    distance). A stand closes with distance the way a forest does; without it far trunks are as crisp as near ones."""
    if not HAZE:
        return shader
    cam = N.new("ShaderNodeCameraData")
    e = _math(N, L, "EXPONENT", _math(N, L, "MULTIPLY", cam.outputs["View Distance"], -1.0 / float(HAZE.get("distance", 60.0))))
    fac = _math(N, L, "MULTIPLY", _math(N, L, "SUBTRACT", 1.0, e), float(HAZE.get("most", 0.92)))
    em = N.new("ShaderNodeEmission")
    em.inputs["Color"].default_value = (*lin(HAZE.get("color", [0.62, 0.68, 0.72])), 1)
    em.inputs["Strength"].default_value = float(HAZE.get("strength", 1.0))
    mx = N.new("ShaderNodeMixShader")
    L.new(fac, mx.inputs[0])
    L.new(shader, mx.inputs[1])
    L.new(em.outputs[0], mx.inputs[2])
    return mx.outputs[0]


def _haze_out(m):
    """Put the haze before an opaque material's output."""
    if not HAZE:
        return
    N, L = m.node_tree.nodes, m.node_tree.links
    out = N["Material Output"]
    if not out.inputs["Surface"].is_linked:
        return
    src = out.inputs["Surface"].links[0].from_socket
    L.new(_hazed(N, L, src), out.inputs["Surface"])


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
        zz = _math(N, L, "ADD", sep.outputs["Z"], _math(N, L, "MULTIPLY", _math(N, L, "SUBTRACT", bigv, 0.5), h0 * 1.2))
        fac_base = _math(N, L, "MULTIPLY", ramp01(zz, h0 * 1.5, h0 * 0.4), ramp01(rad.outputs["Fac"], 0.03, 0.08))
        col = mix(col, fac_base, lin(bark["base_color"]))
    if bark.get("upper_color") is not None:
        u0 = bark.get("upper_from", 0.5 * height)
        ub = bark.get("upper_blend", 0.2 * height)  # m the change takes (patchy: the noise moves it +- 0.15 x height)
        zz = _math(N, L, "ADD", sep.outputs["Z"], _math(N, L, "MULTIPLY", _math(N, L, "SUBTRACT", bigv, 0.5), 0.3 * height))
        col = mix(col, ramp01(zz, u0, u0 + max(ub, 0.01)), lin(bark["upper_color"]))
    tr_ = bark.get("twig_radius", [0.006, 0.02])  # m of radius: all twig colour under [0], none over [1]
    fac_twig = ramp01(rad.outputs["Fac"], float(tr_[1]), float(tr_[0]))
    if bark.get("twig_color") is not None:
        col = mix(col, fac_twig, lin(bark["twig_color"]))
    dead = N.new("ShaderNodeAttribute")  # dead wood: barkless, weathered silver-grey
    dead.attribute_name = "dead"
    col = mix(col, dead.outputs["Fac"], lin(bark.get("dead_color", [0.66, 0.63, 0.58])))
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


def _hull_dir(N):
    """Out from the crown's middle, per twig: the instancer's "hull" attribute (hp_twigs stores it from the object's own
    crown and turn, so copies of one plant share a material)."""
    at = N.new("ShaderNodeAttribute")
    at.attribute_type = "INSTANCER"
    at.attribute_name = "hull"
    return at.outputs["Vector"]


def _hull_normal(N, L, leaf):
    """The crown shaded as a volume (foliage artists' normal transfer): each leaf's normal bent toward the direction
    out from the crown's middle by `round` (0.7). With their own normals, hanging cards catch the sun edge-on and a lit
    crown rendered at 0.4 of a photo's brightness."""
    w = float(leaf.get("round", 0.7))
    if w <= 0 or leaf.get("crown") is None:
        return None
    geo = N.new("ShaderNodeNewGeometry")
    nrm = _hull_dir(N)
    mx = N.new("ShaderNodeMix")
    mx.data_type = "VECTOR"
    mx.inputs["Factor"].default_value = w
    a_, b_ = [i for i in mx.inputs if i.name == "A" and i.type == "VECTOR"][0], [i for i in mx.inputs if i.name == "B" and i.type == "VECTOR"][0]
    L.new(geo.outputs["Normal"], a_)
    L.new(nrm, b_)
    fin = N.new("ShaderNodeVectorMath")
    fin.operation = "NORMALIZE"
    L.new([o for o in mx.outputs if o.type == "VECTOR"][0], fin.inputs[0])
    return fin.outputs[0]


def _leaf_out(m, N, L, base, alpha, through, rough, leaf):
    """Leaf shading: Principled + light coming through (Translucent), mixed by `through`."""
    bsdf = N["Principled BSDF"]
    hull = _hull_normal(N, L, leaf)
    if hull is not None and not bsdf.inputs["Normal"].is_linked:
        L.new(hull, bsdf.inputs["Normal"])
    out = N["Material Output"]
    L.new(base, bsdf.inputs["Base Color"])
    if hasattr(rough, "links"):
        L.new(rough, bsdf.inputs["Roughness"])
    else:
        bsdf.inputs["Roughness"].default_value = rough
    tr = N.new("ShaderNodeBsdfTranslucent")
    tc = N.new("ShaderNodeVectorMath")
    tc.operation = "MULTIPLY"
    tc.inputs[1].default_value = leaf.get("through", [1.9, 1.9, 0.45])
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
    last = _hazed(N, L, mx.outputs[0])
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


def _weather(m, snow=0.0, wet=0.0, crown=None):
    """Snow lying on what faces up (wood by its own normal, foliage by the crown's outward direction: its upper side
    whitens) and rain (darker, glossier), put between a finished material's colour / roughness and its Principled."""
    if not snow and not wet:
        return
    N, L = m.node_tree.nodes, m.node_tree.links
    bsdf = N["Principled BSDF"]

    def src(name):
        s_ = bsdf.inputs[name]
        if s_.is_linked:
            a = s_.links[0].from_socket
            L.remove(s_.links[0])
            return a
        v = N.new("ShaderNodeRGB" if name == "Base Color" else "ShaderNodeValue")
        v.outputs[0].default_value = s_.default_value
        return v.outputs[0]

    col, rgh = src("Base Color"), src("Roughness")
    if wet:
        d = N.new("ShaderNodeVectorMath")
        d.operation = "SCALE"
        d.inputs["Scale"].default_value = 1 - 0.35 * wet
        L.new(col, d.inputs[0])
        col = d.outputs[0]
        # (leaves: a little gloss only. At 0.4 x roughness every card mirrored the sky: grey smears through the crown)
        rgh = _math(N, L, "MULTIPLY", rgh, 1 - (0.25 if crown is not None else 0.6) * wet)
    if snow:
        geo = N.new("ShaderNodeNewGeometry")
        if crown is not None:
            # snow lies on every plate and spray that faces up, wherever it is in the crown (by the crown's direction
            # alone only the top of the tree went white), more on the crown's upper side
            tsp = N.new("ShaderNodeSeparateXYZ")
            L.new(geo.outputs["True Normal"], tsp.inputs[0])
            csp = N.new("ShaderNodeSeparateXYZ")
            L.new(_hull_dir(N), csp.inputs[0])
            zz = _math(N, L, "ADD", _math(N, L, "MULTIPLY", _math(N, L, "ABSOLUTE", tsp.outputs["Z"]), 0.75),
                       _math(N, L, "MULTIPLY", csp.outputs["Z"], 0.4))
            cmb = N.new("ShaderNodeCombineXYZ")
            L.new(zz, cmb.inputs["Z"])
            vec = cmb.outputs[0]
        else:
            vec = geo.outputs["Normal"]
        sp = N.new("ShaderNodeSeparateXYZ")
        L.new(vec, sp.inputs[0])
        nz = N.new("ShaderNodeTexNoise")
        nz.inputs["Scale"].default_value = 6.0
        up = _math(N, L, "ADD", sp.outputs["Z"], _math(N, L, "MULTIPLY", _math(N, L, "SUBTRACT", nz.outputs[0], 0.5), 0.5))
        r = N.new("ShaderNodeMapRange")
        r.inputs["From Min"].default_value, r.inputs["From Max"].default_value = 1.0 - 1.3 * snow, 1.25 - 1.3 * snow
        L.new(up, r.inputs["Value"])
        mx = N.new("ShaderNodeMix")
        mx.data_type = "RGBA"
        L.new(r.outputs["Result"], mx.inputs["Factor"])
        L.new(col, mx.inputs["A"])
        mx.inputs["B"].default_value = (0.9, 0.92, 0.95, 1)
        col = mx.outputs["Result"]
        rgh = _math(N, L, "MAXIMUM", rgh, _math(N, L, "MULTIPLY", r.outputs["Result"], 0.6))
    L.new(col, bsdf.inputs["Base Color"])
    L.new(rgh, bsdf.inputs["Roughness"])


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
    if leaf.get("card_normal", 0.0) > 0:
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
    col = r.outputs["Color"]
    ms = ground.get("moss")
    if ms:  # {"color", "amount" 0..1, "size" m}: moss in soft-edged patches over the litter (brighter where it is deep)
        n3 = N.new("ShaderNodeTexNoise")
        n3.inputs["Scale"].default_value = 1.0 / max(float(ms.get("size", 2.5)), 0.05)
        n3.inputs["Detail"].default_value = 5.0
        L.new(co.outputs["Object"], n3.inputs["Vector"])
        mr = N.new("ShaderNodeMapRange")
        a_ = float(ms.get("amount", 0.4))
        mr.inputs["From Min"].default_value, mr.inputs["From Max"].default_value = 0.62 - 0.3 * a_, 0.72 - 0.3 * a_
        L.new(f(n3), mr.inputs["Value"])
        mx = N.new("ShaderNodeMix")
        mx.data_type = "RGBA"
        L.new(mr.outputs["Result"], mx.inputs["Factor"])
        L.new(col, mx.inputs["A"])
        mc = N.new("ShaderNodeVectorMath")
        mc.operation = "SCALE"
        mc.inputs[0].default_value = lin(ms.get("color", [0.3, 0.42, 0.14]))
        L.new(_math(N, L, "ADD", 0.7, _math(N, L, "MULTIPLY", f(n2), 0.6)), mc.inputs["Scale"])
        L.new(mc.outputs[0], mx.inputs["B"])
        col = mx.outputs["Result"]
    lt = ground.get("litter")
    if lt:  # needle litter: fine pale and dark flecks (fallen needles, twigs, cone scales), a strength 0..1
        n4 = N.new("ShaderNodeTexNoise")
        n4.inputs["Scale"].default_value = 60.0
        n4.inputs["Detail"].default_value = 2.0
        L.new(co.outputs["Object"], n4.inputs["Vector"])
        sc_ = N.new("ShaderNodeVectorMath")
        sc_.operation = "SCALE"
        L.new(col, sc_.inputs[0])
        L.new(_math(N, L, "ADD", 1.0 - 0.5 * float(lt), _math(N, L, "MULTIPLY", f(n4), float(lt))), sc_.inputs["Scale"])
        col = sc_.outputs[0]
    L.new(col, bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.9
    bump = N.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.5
    bump.inputs["Distance"].default_value = 0.05
    L.new(f(n2), bump.inputs["Height"])
    L.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    return m


def _instancer(points_ob, proto, crown, yaw=0.0):
    """Instance `proto` on the points' vertices: rotation from 'rot' (euler), scale from 'size'; 'tint' rides along.
    Each instance gets "hull" = the direction out from the plant's crown (`crown`, in the object's own frame), turned
    by the object's `yaw`: both are modifier inputs, so copies of the object share the node group and the material."""
    ng = bpy.data.node_groups.new("hp_twigs", "GeometryNodeTree")
    ng.interface.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    ng.interface.new_socket("Crown", in_out="INPUT", socket_type="NodeSocketVector")
    ng.interface.new_socket("Yaw", in_out="INPUT", socket_type="NodeSocketFloat")
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
    pos = N.new("GeometryNodeInputPosition")
    sub = N.new("ShaderNodeVectorMath")
    sub.operation = "SUBTRACT"
    L.new(pos.outputs[0], sub.inputs[0])
    L.new(gi.outputs["Crown"], sub.inputs[1])
    nrm = N.new("ShaderNodeVectorMath")
    nrm.operation = "NORMALIZE"
    L.new(sub.outputs[0], nrm.inputs[0])
    vr = N.new("ShaderNodeVectorRotate")
    vr.rotation_type = "Z_AXIS"
    L.new(nrm.outputs[0], vr.inputs["Vector"])
    L.new(gi.outputs["Yaw"], vr.inputs["Angle"])
    st = N.new("GeometryNodeStoreNamedAttribute")
    st.data_type = "FLOAT_VECTOR"
    st.domain = "INSTANCE"
    st.inputs["Name"].default_value = "hull"
    L.new(inst.outputs["Instances"], st.inputs["Geometry"])
    L.new(vr.outputs["Vector"], st.inputs["Value"])
    L.new(st.outputs["Geometry"], go.inputs[0])
    md = points_ob.modifiers.new("twigs", "NODES")
    md.node_group = ng
    ids = {it.name: it.identifier for it in ng.interface.items_tree if getattr(it, "in_out", "") == "INPUT"}
    md[ids["Crown"]] = [float(v) for v in crown]
    md[ids["Yaw"]] = float(yaw)
    points_ob["hp_yaw_id"] = ids["Yaw"]


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
        # the sky is what the camera sees; what LIGHTS the plant from it is far less blue (a clear sky's fill on shaded
        # bark rendered blue-black, shaded leaves 30-50 deg colder in hue than photos): the sky's colour pulled 70% to grey
        lp = N.new("ShaderNodeLightPath")
        grey = N.new("ShaderNodeMix")
        grey.data_type = "RGBA"
        grey.inputs["Factor"].default_value = job.get("sky_fill_grey", 0.7)
        L.new(sky.outputs["Color"], grey.inputs["A"])
        bw = N.new("ShaderNodeRGBToBW")
        L.new(sky.outputs["Color"], bw.inputs[0])
        warm = N.new("ShaderNodeVectorMath")
        warm.operation = "SCALE"
        warm.inputs[0].default_value = (1.05, 1.0, 0.92)
        L.new(bw.outputs[0], warm.inputs["Scale"])
        L.new(warm.outputs[0], grey.inputs["B"])
        pick = N.new("ShaderNodeMix")
        pick.data_type = "RGBA"
        L.new(lp.outputs["Is Camera Ray"], pick.inputs["Factor"])
        L.new(grey.outputs["Result"], pick.inputs["A"])
        L.new(sky.outputs["Color"], pick.inputs["B"])
        L.new(pick.outputs["Result"], bg.inputs["Color"])
        bg.inputs[1].default_value = job.get("sky_strength", 0.07)
    except Exception:
        bg.inputs[0].default_value = (*job.get("sky", [0.5, 0.66, 0.9]), 1)
        bg.inputs[1].default_value = 0.6
    sc.world = w
    return w, bg, sky


_BUILT: dict = {}


def add_plant(pj, tag, clay):
    """One plant from its npz at pj["at"] ([x, y], turned pj["yaw"] deg): returns its objects and its points. A plant
    stood again (the same npz) is a copy of the first's objects: meshes, materials and textures are shared (a stand of
    54 trees each with its own atlas textures lost the GPU context)."""
    at = np.array(list(pj.get("at", [0, 0])) + [float(pj.get("z", 0.0))])
    yaw = math.radians(pj.get("yaw", 0.0))
    k_sc = float(pj.get("scale", 1.0))
    c, s_ = math.cos(yaw), math.sin(yaw)
    Rz = np.array([[c, -s_, 0], [s_, c, 0], [0, 0, 1.0]])
    place = lambda P: (P * k_sc) @ Rz.T + at
    b = _BUILT.get(pj["npz"])
    if b is not None:
        col = bpy.context.scene.collection
        wood = b["wood"].copy()
        col.objects.link(wood)
        wood.location, wood.rotation_euler, wood.scale = at.tolist(), (0, 0, yaw), (k_sc,) * 3
        twigs = []
        for o in b["twigs"]:
            o2 = o.copy()
            col.objects.link(o2)
            o2.location, o2.rotation_euler, o2.scale = at.tolist(), (0, 0, yaw), (k_sc,) * 3
            if not o.get("hp_solid"):
                o2.modifiers["twigs"][o["hp_yaw_id"]] = float(yaw)
            twigs.append(o2)
        return {"wood": wood, "bark": b["bark"], "twigs": twigs, "points": place(b["local"]), "solid": b.get("solid"), "solid_mat": b.get("solid_mat")}
    d = np.load(pj["npz"])
    V = d["V"]
    has_tw = "tw_pos" in d and len(d["tw_pos"])
    bk = pj.get("bark") or {}
    bark = _flat(f"bark{tag}", lin(bk["flat"]), float(bk.get("roughness", 0.9))) if bk.get("flat") else bark_material(f"bark{tag}", bk, float(V[:, 2].max()))
    _weather(bark, float(pj.get("snow", 0.0)), float(pj.get("wet", 0.0)))
    _haze_out(bark)
    twig_wood = _flat(f"twig_wood{tag}", lin(bk.get("twig_color") or [0.45, 0.4, 0.35]), 0.8)
    wood = _mesh(f"wood{tag}", V, d["F"], d["uv"] if "uv" in d else None)
    wood.location, wood.rotation_euler, wood.scale = at.tolist(), (0, 0, yaw), (k_sc,) * 3
    a = wood.data.attributes.new("tan", "FLOAT_VECTOR", "POINT")
    a.data.foreach_set("vector", d["tan"].astype(np.float32).ravel())
    a = wood.data.attributes.new("dead", "FLOAT", "POINT")
    a.data.foreach_set("value", d["dead"].astype(np.float32) if "dead" in d else np.zeros(len(d["V"]), np.float32))
    a = wood.data.attributes.new("radius", "FLOAT", "POINT")
    a.data.foreach_set("value", d["radius"].astype(np.float32))
    if "cen" in d:  # (each part's middle in plan: a sector cut keeps a part whole, see _pass_material)
        a = wood.data.attributes.new("hp_c", "FLOAT_VECTOR", "POINT")
        a.data.foreach_set("vector", d["cen"].astype(np.float32).ravel())
    wood.data.materials.append(bark)
    wood.data.polygons.foreach_set("use_smooth", np.ones(len(wood.data.polygons), bool))
    if "wood_N" in d:  # (a style's wood is meshed from a field: its own normals)
        wood.data.normals_split_custom_set_from_vertices(d["wood_N"].astype(np.float32).tolist())
    twig_obs = []
    pts_all = [V]
    if has_tw:
        cards = pj.get("cards")
        lf_ = dict(pj.get("leaf") or {})
        tp_ = d["tw_pos"]
        lf_["crown"] = [float(tp_[:, 0].mean()), float(tp_[:, 1].mean()), float(np.percentile(tp_[:, 2], 30))]
        mat = card_material(f"cards{tag}", lf_, cards) if cards else leaf_material(f"leaf{tag}", lf_)
        _weather(mat, float(pj.get("snow", 0.0)), float(pj.get("wet", 0.0)), lf_["crown"])
        nv = int(d["tw_var"].max()) + 1
        pts_all.append(tp_)
        for i in range(nv):
            sel = d["tw_var"] == i
            if not sel.any():
                continue
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
            pts = _mesh(f"twigs{tag}_{i}", d["tw_pos"][sel], np.zeros((0, 3), np.int32))
            for nm_, kind, key, field in (("rot", "FLOAT_VECTOR", "tw_rot", "vector"), ("size", "FLOAT", "tw_scale", "value"),
                                          ("tint", "FLOAT", "tw_tint", "value")):
                at_ = pts.data.attributes.new(nm_, kind, "POINT")
                at_.data.foreach_set(field, d[key][sel].astype(np.float32).ravel())
            at_ = pts.data.attributes.new("hp_c", "FLOAT_VECTOR", "POINT")  # (a card stands where its point is: kept whole by a sector cut)
            at_.data.foreach_set("vector", np.c_[d["tw_pos"][sel][:, :2], np.ones(int(sel.sum()))].astype(np.float32).ravel())
            _instancer(pts, proto, lf_["crown"], yaw)
            pts.location = at.tolist()  # (the instances' own frames ride the object's turn)
            pts.rotation_euler = (0, 0, yaw)
            pts.scale = (k_sc,) * 3
            twig_obs.append(pts)
    solid = solid_mat = None
    if "solid_V" in d:  # a style's crown: one closed mesh, a colour per vertex (linear), its own smooth normals
        solid = _mesh(f"crown{tag}", d["solid_V"], d["solid_F"], d["solid_uv"] if "solid_uv" in d else None)
        ca = solid.data.color_attributes.new("col", "FLOAT_COLOR", "POINT")
        ca.data.foreach_set("color", np.c_[d["solid_col"], np.ones(len(d["solid_col"]))].astype(np.float32).ravel())
        if "solid_cen" in d:
            a = solid.data.attributes.new("hp_c", "FLOAT_VECTOR", "POINT")
            a.data.foreach_set("vector", d["solid_cen"].astype(np.float32).ravel())
        solid.data.polygons.foreach_set("use_smooth", np.ones(len(solid.data.polygons), bool))
        solid.data.normals_split_custom_set_from_vertices(d["solid_N"].astype(np.float32).tolist())
        solid_mat = bpy.data.materials.new(f"crown{tag}")
        solid_mat.use_nodes = True
        N_, L_ = solid_mat.node_tree.nodes, solid_mat.node_tree.links
        an = N_.new("ShaderNodeAttribute")
        an.attribute_name = "col"
        sj_ = pj.get("solid") or {}
        N_["Principled BSDF"].inputs["Roughness"].default_value = float(sj_.get("roughness", 0.85))
        if sj_.get("atlas"):  # leaf clouds: the dab atlas's tone x the vertex colour, cut out by its alpha (both sides drawn)
            tx = _image(N_, sj_["atlas"], True)  # (sRGB, as an engine reads a glTF base colour texture)
            mu = N_.new("ShaderNodeVectorMath")
            mu.operation = "MULTIPLY"
            L_.new(an.outputs["Color"], mu.inputs[0])
            L_.new(tx.outputs["Color"], mu.inputs[1])
            L_.new(mu.outputs[0], N_["Principled BSDF"].inputs["Base Color"])
            _weather(solid_mat, float(pj.get("snow", 0.0)), float(pj.get("wet", 0.0)))
            out_ = N_["Material Output"]
            last = _hazed(N_, L_, out_.inputs["Surface"].links[0].from_socket)
            tp = N_.new("ShaderNodeBsdfTransparent")
            am = N_.new("ShaderNodeMixShader")
            L_.new(_math(N_, L_, "GREATER_THAN", tx.outputs["Alpha"], float(sj_.get("alpha_cut", 0.5))), am.inputs[0])
            L_.new(tp.outputs[0], am.inputs[1])
            L_.new(last, am.inputs[2])
            L_.new(am.outputs[0], out_.inputs["Surface"])
            for attr, val in (("surface_render_method", "DITHERED"), ("use_transparent_shadow", True), ("blend_method", "HASHED")):
                try:
                    setattr(solid_mat, attr, val)
                except Exception:
                    pass
            solid_mat.use_backface_culling = False
        else:
            L_.new(an.outputs["Color"], N_["Principled BSDF"].inputs["Base Color"])
            _weather(solid_mat, float(pj.get("snow", 0.0)), float(pj.get("wet", 0.0)))
            _haze_out(solid_mat)
        solid.data.materials.append(solid_mat)
        solid.location, solid.rotation_euler, solid.scale = at.tolist(), (0, 0, yaw), (k_sc,) * 3
        solid["hp_solid"] = 1
        twig_obs.append(solid)
        pts_all.append(d["solid_V"])
    local = np.vstack(pts_all)
    _BUILT[pj["npz"]] = {"wood": wood, "bark": bark, "twigs": twig_obs, "local": local, "solid": solid, "solid_mat": solid_mat}
    return {"wood": wood, "bark": bark, "twigs": twig_obs, "points": place(local), "solid": solid, "solid_mat": solid_mat}


def add_scatter(sj, tag):
    """A plain mesh (faces coloured by `mat` -> colors) instanced at points on the ground: brash, stumps, stones."""
    d = np.load(sj["npz"])
    proto = _mesh(f"scatter{tag}", d["V"], d["F"])
    for i, c in enumerate(sj["colors"]):
        m = _flat(f"scatter{tag}_{i}", lin(c), float(sj.get("rough", 0.9)))
        _haze_out(m)
        proto.data.materials.append(m)
    proto.data.polygons.foreach_set("material_index", d["mat"].astype(np.int32))
    proto.data.polygons.foreach_set("use_smooth", np.ones(len(proto.data.polygons), bool))
    proto.hide_render = True
    proto.hide_viewport = True
    n = len(d["pos"])
    pts = _mesh(f"scatter_pts{tag}", d["pos"], np.zeros((0, 3), np.int32))
    rot = np.zeros((n, 3), np.float32)
    rot[:, 2] = np.radians(d["yaw"])
    for nm_, kind, val, field in (("rot", "FLOAT_VECTOR", rot, "vector"), ("size", "FLOAT", d["scale"], "value"),
                                  ("tint", "FLOAT", np.zeros(n), "value")):
        at_ = pts.data.attributes.new(nm_, kind, "POINT")
        at_.data.foreach_set(field, np.asarray(val, np.float32).ravel())
    _instancer(pts, proto, [0, 0, 0], 0.0)
    return pts


def add_curves(job):
    """The plant's guides and named limbs as Bezier curves a person can edit (collections "guides", "limbs";
    hide_render). Each is stamped with the points the sync wrote (`hp_set`): pull compares against it. The names the
    sync made are kept on the collection (`hp_made`), so a deleted curve is seen as deleted."""
    sc = bpy.context.scene
    for coll_name, colour in (("guides", (1.0, 0.45, 0.05, 1)), ("limbs", (0.2, 0.7, 1.0, 1))):
        items = [c for c in job.get("curves") or [] if c["kind"] == coll_name]
        coll = bpy.data.collections.get(coll_name)
        if coll is None:
            coll = bpy.data.collections.new(coll_name)
            sc.collection.children.link(coll)
        for o in list(coll.objects):
            bpy.data.objects.remove(o, do_unlink=True)
        for c in items:
            cu = bpy.data.curves.new(c["name"], "CURVE")
            cu.dimensions = "3D"
            cu.bevel_depth = float(c.get("radius", 0.03))
            cu.bevel_resolution = 1
            sp = cu.splines.new("BEZIER")
            sp.bezier_points.add(len(c["points"]) - 1)
            for bp, p_ in zip(sp.bezier_points, c["points"]):
                bp.co = p_
                bp.handle_left_type = bp.handle_right_type = "AUTO"
            ob = bpy.data.objects.new(c["name"], cu)
            ob["hp_set"] = json.dumps(c["points"])
            if c.get("key"):
                ob["hp_key"] = c["key"]
            ob.color = colour
            ob.hide_render = True
            ob.show_in_front = True
            m = bpy.data.materials.get("hp_" + coll_name) or _flat("hp_" + coll_name, list(colour[:3]), 0.6)
            cu.materials.append(m)
            coll.objects.link(ob)
        coll["hp_made"] = json.dumps([c["name"] for c in items])


def read_curves():
    """Every curve in "guides" / "limbs" as it stands now: world-space control points, the stamp, and what the sync
    made (for deletions). Works in a live session too."""
    out = {"file": bpy.data.filepath, "guides": [], "limbs": [], "made": {}}
    for coll_name in ("guides", "limbs"):
        coll = bpy.data.collections.get(coll_name)
        if coll is None:
            continue
        out["made"][coll_name] = json.loads(coll.get("hp_made", "[]"))
        for ob in coll.objects:
            if ob.type != "CURVE" or not ob.data.splines:
                continue
            sp = ob.data.splines[0]
            pts = sp.bezier_points if sp.type == "BEZIER" else sp.points
            P = [list(ob.matrix_world @ Vector(p_.co[:3])) for p_ in pts]
            out[coll_name].append({"name": ob.name, "points": [[round(x, 4) for x in q] for q in P],
                                   "set": json.loads(ob["hp_set"]) if "hp_set" in ob else None, "key": ob.get("hp_key")})
    return out


_PASS: dict = {}


def _pass_material(m, kind):
    """A copy of a finished material that draws one thing unlit, cut out by the same alpha: "albedo" = what goes into
    its Principled's Base Color (after weather; no sky reflected in it: lit by a white world, a picture came out pale),
    "normal" = the shading normal in world space x 0.5 + 0.5 (what the Principled is given: a leaf's normal bent out of
    the crown, a style's own smooth normals), "shade" = how much of the sky straight above reaches the point (Cycles'
    AO node with the normal forced up: 0 under a crown or a limb). An impostor's maps are made of these."""
    key = (m.name, kind)
    if key in _PASS:
        return _PASS[key]
    c = m.copy()
    c.name = f"{m.name}:{kind}"
    N, L = c.node_tree.nodes, c.node_tree.links
    out = next((n for n in N if n.type == "OUTPUT_MATERIAL" and n.is_active_output), None) or N["Material Output"]
    bsdf = next((n for n in N if n.type == "BSDF_PRINCIPLED"), None)
    alpha = None
    for n in N:  # the cut-out: a mix with a Transparent BSDF in its first slot
        if n.type == "MIX_SHADER" and n.inputs[1].is_linked and n.inputs[1].links[0].from_node.type == "BSDF_TRANSPARENT" and n.inputs[0].is_linked:
            alpha = n.inputs[0].links[0].from_socket
    em = N.new("ShaderNodeEmission")
    if kind == "albedo":
        if bsdf is not None and bsdf.inputs["Base Color"].is_linked:
            L.new(bsdf.inputs["Base Color"].links[0].from_socket, em.inputs["Color"])
        else:
            em.inputs["Color"].default_value = bsdf.inputs["Base Color"].default_value if bsdf is not None else (0.5, 0.5, 0.5, 1)
    elif kind == "normal":
        if bsdf is not None and bsdf.inputs["Normal"].is_linked:
            nsrc = bsdf.inputs["Normal"].links[0].from_socket
        else:
            nsrc = N.new("ShaderNodeNewGeometry").outputs["Normal"]
        ma = N.new("ShaderNodeVectorMath")
        ma.operation = "MULTIPLY_ADD"
        ma.inputs[1].default_value, ma.inputs[2].default_value = (0.5, 0.5, 0.5), (0.5, 0.5, 0.5)
        L.new(nsrc, ma.inputs[0])
        L.new(ma.outputs[0], em.inputs["Color"])
    elif kind == "depth":  # distance behind the view's middle plane, 0 = `near` .. 1 = `far` (set per view: hp_depth)
        cd = N.new("ShaderNodeCameraData")
        mr = N.new("ShaderNodeMapRange")
        mr.name = "hp_depth"
        mr.clamp = True
        L.new(cd.outputs["View Z Depth"], mr.inputs["Value"])
        L.new(mr.outputs[0], em.inputs["Color"])
    else:
        ao = N.new("ShaderNodeAmbientOcclusion")
        ao.samples = 16
        ao.inputs["Distance"].default_value = 1000.0
        ao.inputs["Normal"].default_value = (0, 0, 1)
        L.new(ao.outputs["AO"], em.inputs["Color"])
    last = em.outputs[0]
    # a view may keep only what stands in a double wedge round a vertical axis (`sector`: a groundcover card's slice of
    # its clump): azimuth about (hp_sec_cx, hp_sec_cy) within hp_sec_half of hp_sec_theta (mod 180 deg); half >= 90 deg
    # = everything (set per view in render)
    # a part is kept or cut WHOLE by where its middle stands (attribute hp_c = (x, y, 1) on the mesh, or on the instance
    # for cards): cut by pixel a blade or a flower head split across two cards, half on each
    geo = N.new("ShaderNodeNewGeometry")
    sxyz = N.new("ShaderNodeSeparateXYZ")
    L.new(geo.outputs["Position"], sxyz.inputs[0])
    px_, py_ = sxyz.outputs["X"], sxyz.outputs["Y"]
    for typ in ("INSTANCER", "GEOMETRY"):
        at_ = N.new("ShaderNodeAttribute")
        at_.attribute_type = typ
        at_.attribute_name = "hp_c"
        sp_ = N.new("ShaderNodeSeparateXYZ")
        L.new(at_.outputs["Vector"], sp_.inputs[0])
        nx_, ny_ = [], []
        for cur, comp in ((px_, "X"), (py_, "Y")):
            mx = N.new("ShaderNodeMix")
            mx.data_type = "FLOAT"
            mx.clamp_factor = True  # (flag 2 = a head: still its middle)
            L.new(sp_.outputs["Z"], mx.inputs["Factor"])
            L.new(cur, mx.inputs["A"])
            L.new(sp_.outputs[comp], mx.inputs["B"])
            (nx_ if comp == "X" else ny_).append(mx.outputs["Result"])
        px_, py_ = nx_[0], ny_[0]
        if typ == "GEOMETRY":
            flag_ = sp_.outputs["Z"]

    def _m(op, a, b=None, name=None, val=None):
        n_ = N.new("ShaderNodeMath")
        n_.operation = op
        if name:
            n_.name = name
        for i_, x_ in enumerate((a, b)):
            if x_ is None:
                continue
            if isinstance(x_, (int, float)):
                n_.inputs[i_].default_value = float(x_)
            else:
                L.new(x_, n_.inputs[i_])
        return n_
    dx = _m("SUBTRACT", px_, 0.0, "hp_sec_cx")
    dy = _m("SUBTRACT", py_, 0.0, "hp_sec_cy")
    az = _m("ARCTAN2", dy.outputs[0], dx.outputs[0])
    rel = _m("SUBTRACT", az.outputs[0], 0.0, "hp_sec_theta")
    wr = N.new("ShaderNodeMath")
    wr.operation = "WRAP"
    L.new(rel.outputs[0], wr.inputs[0])
    wr.inputs[1].default_value, wr.inputs[2].default_value = math.pi / 2, -math.pi / 2
    ab = _m("ABSOLUTE", wr.outputs[0])
    wedge = _m("LESS_THAN", ab.outputs[0], 10.0, "hp_sec_half").outputs[0]
    # heads (hp_c flag 2) go on cards of their own: a wedge view (mode 0) leaves them out unless hp_sec_heads, a head
    # view (mode 1) keeps only the head whose middle is within hp_sec_rho of (hp_sec_hx, hp_sec_hy); hp_sec_on 0 = no cut
    is_head = _m("GREATER_THAN", flag_, 1.5).outputs[0]
    not_head = _m("SUBTRACT", 1.0, is_head).outputs[0]
    keep_h = _m("MAXIMUM", not_head, 0.0, "hp_sec_heads").outputs[0]
    w_term = _m("MULTIPLY", wedge, keep_h).outputs[0]
    hx = _m("SUBTRACT", px_, 0.0, "hp_sec_hx")
    hy = _m("SUBTRACT", py_, 0.0, "hp_sec_hy")
    r2 = _m("ADD", _m("MULTIPLY", hx.outputs[0], hx.outputs[0]).outputs[0], _m("MULTIPLY", hy.outputs[0], hy.outputs[0]).outputs[0])
    hd = _m("LESS_THAN", _m("SQRT", r2.outputs[0]).outputs[0], 0.0, "hp_sec_rho").outputs[0]
    h_term = _m("MULTIPLY", is_head, hd).outputs[0]
    mode = _m("ADD", 0.0, 0.0, "hp_sec_mode").outputs[0]
    sel = N.new("ShaderNodeMix")
    sel.data_type = "FLOAT"
    L.new(mode, sel.inputs["Factor"])
    L.new(w_term, sel.inputs["A"])
    L.new(h_term, sel.inputs["B"])
    on = N.new("ShaderNodeMix")
    on.data_type = "FLOAT"
    on.name = "hp_sec_on"
    on.inputs["Factor"].default_value = 0.0
    on.inputs["A"].default_value = 1.0
    L.new(sel.outputs["Result"], on.inputs["B"])
    inside = on.outputs["Result"]
    fac = inside if alpha is None else _m("MULTIPLY", alpha, inside).outputs[0]
    tp = N.new("ShaderNodeBsdfTransparent")
    am = N.new("ShaderNodeMixShader")
    L.new(fac, am.inputs[0])
    L.new(tp.outputs[0], am.inputs[1])
    L.new(last, am.inputs[2])
    last = am.outputs[0]
    L.new(last, out.inputs["Surface"])
    _PASS[key] = c
    return c


def _pass_swap(kind):
    """Every mesh's materials swapped for their pass copies; returns what to hand to _pass_restore."""
    was = []
    for me in bpy.data.meshes:
        for i, m in enumerate(me.materials):
            if m is not None and ":" not in m.name and m.use_nodes:
                was.append((me, i, m))
                me.materials[i] = _pass_material(m, kind)
    return was


def _pass_restore(was):
    for me, i, m in was:
        me.materials[i] = m


def build(job):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    clay = _flat("clay", [0.8, 0.78, 0.74], 0.9)
    HAZE.clear()
    HAZE.update(job.get("haze") or {})
    _BUILT.clear()
    _PASS.clear()
    plants = [add_plant(pj, f"_{i}" if i else "", clay) for i, pj in enumerate(job["plants"])]
    for i, sj in enumerate(job.get("scatter") or []):
        add_scatter(sj, f"_s{i}")
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
        ground.rotation_euler = Matrix.Rotation(math.radians(gj["slope"]), 4, axis).to_euler()
    ground_mat = ground_material("ground", job.get("ground") or {})
    # the weather lies on the ground too (a snowy tree stood on a summer lawn)
    _weather(ground_mat, max(float(pj.get("snow", 0.0)) for pj in job["plants"]),
             max(float(pj.get("wet", 0.0)) for pj in job["plants"]))
    _haze_out(ground_mat)
    if gj.get("water") is not None:  # a water level (m, against the plant's foot): a lake shore, a ditch
        bpy.ops.mesh.primitive_circle_add(vertices=64, radius=max(60 * R, 400.0), fill_type="NGON", location=(0, 0, float(gj["water"])))
        water = bpy.context.object
        wm = _flat("water", lin(gj.get("water_color", [0.16, 0.26, 0.32])), 0.08)
        water.data.materials.append(wm)
    rulers = []
    if job.get("ruler"):  # a pole banded every metre (every fifth band red), beside the plant in the clay and bare views
        m_w, m_r, m_k = _flat("rule_w", [0.9, 0.9, 0.9], 0.6), _flat("rule_r", [0.8, 0.1, 0.08], 0.6), _flat("rule_k", [0.05, 0.05, 0.05], 0.6)
        for i in range(int(job["ruler"])):
            bpy.ops.mesh.primitive_cylinder_add(vertices=8, radius=0.035 + 0.004 * R, depth=1.0,
                                                location=(float(hi[0]) + 0.5, float((lo[1] + hi[1]) / 2), i + 0.5))
            o = bpy.context.object
            o.data.materials.append(m_r if i % 5 == 4 else (m_w if i % 2 == 0 else m_k))
            rulers.append(o)
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
    fill.data.color = job.get("bounce_color", [0.85, 0.8, 0.4])
    fill.data.use_shadow = False
    sc.collection.objects.link(fill)
    fill.rotation_euler = Vector((0, 0, -1)).to_track_quat("Z", "Y").to_euler()
    # under a closed canopy the light is the sky's, scattered down through the crowns: EEVEE's sun is shadowed out and
    # its world light is dim, so a stand's interior rendered as night. A shadowless light from above stands in for it
    amb = bpy.data.objects.new("ambient", bpy.data.lights.new("ambient", "SUN"))
    amb.data.color = job.get("ambient_color", [0.8, 0.88, 0.82])
    amb.data.use_shadow = False
    amb.data.energy = 0.0
    sc.collection.objects.link(amb)
    amb.rotation_euler = Vector((0.25, 0.15, 1)).normalized().to_track_quat("Z", "Y").to_euler()
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
            if v.get("basis") is not None:  # an exact camera frame (an impostor's view): image right, image up, toward the camera
                bs = v["basis"]
                rt, up_, bk = Vector(bs["right"]), Vector(bs["up"]), Vector(bs["back"])
                cam.matrix_world = Matrix(((rt.x, up_.x, bk.x, 0), (rt.y, up_.y, bk.y, 0), (rt.z, up_.z, bk.z, 0), (0, 0, 0, 1)))
                cam.location = Vector(bs["centre"]) + bk * float(bs.get("dist", 4 * R + 10))
            cam.data.type = "ORTHO"
            cam.data.ortho_scale = need
            cam.data.clip_start, cam.data.clip_end = 0.1, 20 * R + 50
        isclay = bool(v.get("clay"))
        isflat = bool(v.get("flat"))  # albedo only: no sun, an even white world (an impostor's picture: the engine lights it)
        if v.get("sun"):
            aim_sun(*v["sun"])
        fill.data.energy = 0.0 if isclay else job.get("bounce", 1.1)
        amb.data.energy = 0.0 if isclay else job.get("ambient", 0.0)
        for o in twig_obs:
            o.hide_render = not v.get("leaves", True)
        for l in list(w.node_tree.links):
            if l.to_socket == bg.inputs[0]:
                w.node_tree.links.remove(l)
        for l in list(w.node_tree.links):  # (a flat view's ramp on the world's strength)
            if l.to_socket == bg.inputs[1]:
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
            if p_.get("solid") is not None:
                p_["solid"].data.materials[0] = clay if isclay else p_["solid_mat"]
        sun.data.energy = 7.0 if isclay else job.get("sun_energy", 3.6)
        if isflat:
            for l in list(w.node_tree.links):
                if l.to_socket == bg.inputs[0]:
                    w.node_tree.links.remove(l)
            bg.inputs[0].default_value = (1, 1, 1, 1)
            bg.inputs[1].default_value = 1.0
            # an even white world from above fading to `under` from below: albedo with a little shade baked under
            # crowns and limbs (wholly unlit, an impostor was flat and pale beside the mesh LOD's shaded underside)
            WN, WL = w.node_tree.nodes, w.node_tree.links
            if "hp_flat_ramp" not in WN:
                geo_ = WN.new("ShaderNodeNewGeometry")
                sep_ = WN.new("ShaderNodeSeparateXYZ")
                mr_ = WN.new("ShaderNodeMapRange")
                mr_.name = "hp_flat_ramp"
                mr_.inputs["From Min"].default_value, mr_.inputs["From Max"].default_value = -1.0, 0.6
                mr_.inputs["To Min"].default_value, mr_.inputs["To Max"].default_value = float(job.get("flat_under", 0.35)), 1.0
                WL.new(geo_.outputs["Incoming"], sep_.inputs[0])
                WL.new(sep_.outputs["Z"], mr_.inputs["Value"])
            WL.new(WN["hp_flat_ramp"].outputs[0], bg.inputs[1])
            sun.data.energy = fill.data.energy = amb.data.energy = 0.0
        sc.view_settings.view_transform = "Standard" if isclay or isflat else job.get("view_transform", "Khronos PBR Neutral")
        sc.view_settings.exposure = 0.0 if isclay else job.get("exposure", 0.0)
        ground.hide_render = bool(v.get("no_ground"))
        for o in rulers:
            o.hide_render = not v.get("ruler", False)
        sc.render.film_transparent = bool(v.get("transparent"))
        sc.render.filepath = v["out"]
        swapped = None
        if v.get("pass"):  # one unlit thing per pixel (see _pass_material); "shade" needs rays: Cycles
            swapped = _pass_swap(v["pass"])
            sec = v.get("sector") or {}
            for m_ in bpy.data.materials:
                if m_.use_nodes and "hp_sec_half" in m_.node_tree.nodes:
                    nt_ = m_.node_tree.nodes
                    nt_["hp_sec_cx"].inputs[1].default_value = float((sec.get("centre") or [0, 0])[0])
                    nt_["hp_sec_cy"].inputs[1].default_value = float((sec.get("centre") or [0, 0])[1])
                    nt_["hp_sec_theta"].inputs[1].default_value = float(sec.get("theta", 0.0))
                    nt_["hp_sec_half"].inputs[1].default_value = float(sec.get("half", 10.0))
                    nt_["hp_sec_on"].inputs["Factor"].default_value = 1.0 if sec else 0.0
                    nt_["hp_sec_mode"].inputs[0].default_value = 1.0 if sec.get("head") is not None else 0.0
                    nt_["hp_sec_heads"].inputs[1].default_value = 1.0 if sec.get("heads", False) else 0.0
                    hh_ = sec.get("head") or [0.0, 0.0, 0.0]
                    nt_["hp_sec_hx"].inputs[1].default_value = float(hh_[0])
                    nt_["hp_sec_hy"].inputs[1].default_value = float(hh_[1])
                    nt_["hp_sec_rho"].inputs[1].default_value = float(hh_[2])
            if v["pass"] == "depth":
                for m_ in bpy.data.materials:
                    if m_.use_nodes and "hp_depth" in m_.node_tree.nodes:
                        mr_ = m_.node_tree.nodes["hp_depth"]
                        mr_.inputs["From Min"].default_value, mr_.inputs["From Max"].default_value = v["depth_range"]
            sc.view_settings.view_transform = "Standard" if v["pass"] == "albedo" else "Raw"
            sun.data.energy = fill.data.energy = amb.data.energy = 0.0
            if v["pass"] == "shade":
                sc.render.engine = "CYCLES"
                sc.cycles.device = "CPU"
                sc.cycles.samples = int(v.get("samples", 12))
                sc.cycles.use_denoising = False
                sc.cycles.max_bounces = 0
                sc.cycles.transparent_max_bounces = 64
        bpy.ops.render.render(write_still=True)
        if swapped is not None:
            _pass_restore(swapped)
            sc.render.engine = "BLENDER_EEVEE"
        print("@@rendered", v["out"])
    if job.get("curves") is not None:
        add_curves(job)
    if job.get("save"):
        for o in twig_obs:
            o.hide_render = False
        bpy.ops.wm.save_as_mainfile(filepath=job["save"], check_existing=False)
        b1 = job["save"] + "1"
        if os.path.exists(b1):
            os.remove(b1)


if __name__ == "__main__":
    args = sys.argv[sys.argv.index("--") + 1:]
    if args[0] == "pull":  # blender -b plant.blend --python this -- pull out.json
        open(args[1], "w").write(json.dumps(read_curves()))
    else:
        build(json.loads(open(args[0]).read()))
