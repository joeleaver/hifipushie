"""Runs inside headless Blender: terrain tiles reassembled through Blender's own glTF importer (not our meshes), under a
sky and sun, with the sea as a plane, trees from trees.csv, and optionally the tile borders drawn as red lines.
Job: {"glbs": [paths], "sea": level | null, "trees": csv | null, "borders": npz (segs (m, 2, 3)) | null,
"size": [w, h], "samples", "views": [{"eye", "look", "fov", "sun": [bearing, height], "borders": bool, "out"}]}."""
import csv
import json
import math
import os
import sys

import bpy
import numpy as np
from mathutils import Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import blender_terrain as bt  # noqa: E402  (tree builders)


def _terrain_material():
    m = bpy.data.materials.new("terrain")
    m.use_nodes = True
    nt = m.node_tree
    b = nt.nodes["Principled BSDF"]
    at = nt.nodes.new("ShaderNodeAttribute")
    at.attribute_name = "Color"  # COLOR_0 as the importer names it
    nt.links.new(at.outputs["Color"], b.inputs["Base Color"])
    b.inputs["Roughness"].default_value = 0.92
    for k in ("Specular IOR Level", "Specular"):
        if k in b.inputs:
            b.inputs[k].default_value = 0.12
    return m


_IMAGES = {}
_PIXEL_ANGLE = []  # (the detail fade's per-view pixel angle nodes, set before each render)


def _layered(m, layers):
    """The engine recipe on an imported baked material: each layer's tiling height texture laid triplanar (Blender's
    box projection) in world metres / scale, weighted by the _WEIGHTS attributes; the sum modulates the baked base
    colour and bumps the baked normal map (what the manifest's engine_recipe describes)."""
    nt = m.node_tree
    bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
    base_in = bsdf.inputs["Base Color"].links[0].from_socket if bsdf.inputs["Base Color"].links else None
    nrm_in = bsdf.inputs["Normal"].links[0].from_socket if bsdf.inputs["Normal"].links else None
    if base_in is None:
        return
    geo = nt.nodes.new("ShaderNodeNewGeometry")
    total = None
    for L in layers:
        if L["path"] not in _IMAGES:
            _IMAGES[L["path"]] = bpy.data.images.load(L["path"])
            _IMAGES[L["path"]].colorspace_settings.name = "Non-Color"
        mp = nt.nodes.new("ShaderNodeVectorMath")
        mp.operation = "SCALE"
        mp.inputs["Scale"].default_value = 1.0 / L["scale"]
        nt.links.new(geo.outputs["Position"], mp.inputs[0])
        tx = nt.nodes.new("ShaderNodeTexImage")
        tx.image = _IMAGES[L["path"]]
        tx.projection = "BOX"
        tx.projection_blend = 0.3
        nt.links.new(mp.outputs["Vector"], tx.inputs["Vector"])
        at = nt.nodes.new("ShaderNodeAttribute")
        at.attribute_name = L["attr"]
        sep = nt.nodes.new("ShaderNodeSeparateColor")
        nt.links.new(at.outputs["Color"], sep.inputs["Color"])
        w = at.outputs["Alpha"] if L["channel"] == 3 else sep.outputs[L["channel"]]
        c = nt.nodes.new("ShaderNodeMath")  # (height - 0.5) x strength x weight
        c.operation = "SUBTRACT"
        nt.links.new(tx.outputs["Color"], c.inputs[0])
        c.inputs[1].default_value = 0.5
        s = nt.nodes.new("ShaderNodeMath")
        s.operation = "MULTIPLY"
        nt.links.new(c.outputs[0], s.inputs[0])
        s.inputs[1].default_value = L["strength"]
        mw = nt.nodes.new("ShaderNodeMath")
        mw.operation = "MULTIPLY"
        nt.links.new(s.outputs[0], mw.inputs[0])
        nt.links.new(w, mw.inputs[1])
        if total is None:
            total = mw.outputs[0]
        else:
            a = nt.nodes.new("ShaderNodeMath")
            nt.links.new(total, a.inputs[0])
            nt.links.new(mw.outputs[0], a.inputs[1])
            total = a.outputs[0]
    # albedo x (1 + 0.8 h)
    f = nt.nodes.new("ShaderNodeMath")
    f.operation = "MULTIPLY_ADD"
    nt.links.new(total, f.inputs[0])
    f.inputs[1].default_value = 1.2
    f.inputs[2].default_value = 1.0
    mul = nt.nodes.new("ShaderNodeMix")
    mul.data_type = "RGBA"
    mul.blend_type = "MULTIPLY"
    mul.inputs["Factor"].default_value = 1.0
    nt.links.new(base_in, mul.inputs["A"])
    cv = nt.nodes.new("ShaderNodeCombineColor")
    for k in range(3):
        nt.links.new(f.outputs[0], cv.inputs[k])
    nt.links.new(cv.outputs["Color"], mul.inputs["B"])
    nt.links.new(mul.outputs["Result"], bsdf.inputs["Base Color"])
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Distance"].default_value = 0.05
    bump.inputs["Strength"].default_value = 0.8
    nt.links.new(total, bump.inputs["Height"])
    if nrm_in is not None:
        nt.links.new(nrm_in, bump.inputs["Normal"])
    nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])


def _img(path):
    if path not in _IMAGES:
        _IMAGES[path] = bpy.data.images.load(path)
        _IMAGES[path].colorspace_settings.name = "Non-Color"
        _IMAGES[path].alpha_mode = "CHANNEL_PACKED"  # (data in RGB where alpha is 0: the lines map)
    return _IMAGES[path]


def _vmath(nt, op, a, b=None, scale=None):
    n = nt.nodes.new("ShaderNodeVectorMath")
    n.operation = op
    nt.links.new(a, n.inputs[0])
    if b is not None:
        if isinstance(b, (int, float)):
            n.inputs[1].default_value = (b, b, b)
        else:
            nt.links.new(b, n.inputs[1])
    if scale is not None:
        if isinstance(scale, (int, float)):
            n.inputs["Scale"].default_value = scale
        else:
            nt.links.new(scale, n.inputs["Scale"])
    return n.outputs["Value"] if op in ("DOT_PRODUCT", "LENGTH", "DISTANCE") else n.outputs["Vector"]


def _math(nt, op, a, b=None):
    n = nt.nodes.new("ShaderNodeMath")
    n.operation = op
    for k, x in enumerate((a, b)):
        if x is None:
            continue
        if isinstance(x, (int, float)):
            n.inputs[k].default_value = x
        else:
            nt.links.new(x, n.inputs[k])
    return n.outputs[0]


def _mixv(nt, a, b, fac):
    n = nt.nodes.new("ShaderNodeMix")
    n.data_type = "VECTOR"
    nt.links.new(fac, n.inputs["Factor"])
    nt.links.new(a, n.inputs[4])
    nt.links.new(b, n.inputs[5])
    return n.outputs[1]


def _xyz(nt, x, y, z):
    c = nt.nodes.new("ShaderNodeCombineXYZ")
    for k, s in enumerate((x, y, z)):
        if isinstance(s, (int, float)):
            c.inputs[k].default_value = s
        else:
            nt.links.new(s, c.inputs[k])
    return c.outputs[0]


def _sep(nt, v):
    s = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(v, s.inputs[0])
    return s.outputs


def _tex(nt, path, vec):
    t = nt.nodes.new("ShaderNodeTexImage")
    t.image = _img(path)
    nt.links.new(vec, t.inputs["Vector"])
    return t.outputs["Color"]


def _plane_sample(nt, D, u, v, T, B, Nv):
    """The swatch at (u, v) metres on a plane whose +u / +v run along world T / B: (albedo, world-space detail normal,
    built from the tangent-space map on T and B projected onto the surface). Anti-tiling: the swatch at 1x and at
    variation_scale x (offset), chosen place by place by the variation mask at (u, v) / variation_m."""
    uv = _xyz(nt, u, v, 0.0)
    vec1 = _vmath(nt, "SCALE", uv, scale=1.0 / D["size"])
    off = _xyz(nt, D["variation_offset"][0], D["variation_offset"][1], 0.0)
    vec2 = _vmath(nt, "ADD", _vmath(nt, "SCALE", uv, scale=1.0 / (D["size"] * D["variation_scale"])), off)
    mask = _tex(nt, D["variation"], _vmath(nt, "SCALE", uv, scale=1.0 / D["variation_m"]))
    mask = _sep(nt, mask)[0]
    alb = nt.nodes.new("ShaderNodeMix")
    alb.data_type = "RGBA"
    nt.links.new(mask, alb.inputs["Factor"])
    nt.links.new(_tex(nt, D["albedo"], vec1), alb.inputs["A"])
    nt.links.new(_tex(nt, D["albedo"], vec2), alb.inputs["B"])
    dec = lambda col: _vmath(nt, "SUBTRACT", _vmath(nt, "SCALE", col, scale=2.0), 1.0)
    n = _sep(nt, _mixv(nt, dec(_tex(nt, D["normal"], vec1)), dec(_tex(nt, D["normal"], vec2)), mask))
    proj = lambda A: _vmath(nt, "NORMALIZE", _vmath(nt, "SUBTRACT", A, _vmath(
        nt, "SCALE", Nv, scale=_vmath(nt, "DOT_PRODUCT", Nv, A))))
    Tp, Bp = proj(T), proj(B)
    w = _vmath(nt, "ADD", _vmath(nt, "ADD", _vmath(nt, "SCALE", Tp, scale=n[0]), _vmath(nt, "SCALE", Bp, scale=n[1])),
               _vmath(nt, "SCALE", Nv, scale=n[2]))
    return alb.outputs["Result"], _vmath(nt, "NORMALIZE", w)


def _smooth_band(nt, x, lo, hi):
    """1 below lo falling smoothly to 0 at hi."""
    mr = nt.nodes.new("ShaderNodeMapRange")
    mr.interpolation_type = "SMOOTHSTEP"
    nt.links.new(x, mr.inputs["Value"])
    mr.inputs["From Min"].default_value, mr.inputs["From Max"].default_value = lo, hi
    mr.inputs["To Min"].default_value, mr.inputs["To Max"].default_value = 1.0, 0.0
    return mr.outputs["Result"]


def _lines(nt, D, path, geo):
    """The structure's lines from the tile's lines map (atlas UV): per set (bed planes, joints) a signed distance s
    (m) and a strength a; crack = a x (1 - smoothstep(0.012, 0.05, |s| + jitter)), shadow = a x (1 - smoothstep(0.03,
    0.2, |s|)). Returns (crack, shadow) sockets: the strongest of the two sets."""
    uv = nt.nodes.new("ShaderNodeUVMap")
    uv.uv_map = "UVMap"
    t = nt.nodes.new("ShaderNodeTexImage")
    t.image = _img(path)
    t.extension = "EXTEND"
    nt.links.new(uv.outputs["UV"], t.inputs["Vector"])
    sep = nt.nodes.new("ShaderNodeSeparateColor")
    nt.links.new(t.outputs["Color"], sep.inputs["Color"])
    nz = nt.nodes.new("ShaderNodeTexNoise")  # (the crack's edge wanders a centimetre or two)
    nz.inputs["Scale"].default_value = 9.0
    nz.inputs["Detail"].default_value = 4.0
    nt.links.new(geo.outputs["Position"], nz.inputs["Vector"])
    jit = _math(nt, "MULTIPLY", _math(nt, "SUBTRACT", nz.outputs["Fac"], 0.5), 0.8)  # (x the width: +-40%)
    nw = nt.nodes.new("ShaderNodeTexNoise")
    nw.inputs["Scale"].default_value = 0.7
    nt.links.new(geo.outputs["Position"], nw.inputs["Vector"])
    w0, w1 = D.get("crack_width", (0.012, 0.045))
    wfac = _math(nt, "MAXIMUM", _math(nt, "MULTIPLY", _math(nt, "SUBTRACT", nw.outputs["Fac"], 0.3), 2.5), 0.0)
    crack = shadow = None
    for sc, ac in ((sep.outputs[0], sep.outputs[2]), (sep.outputs[1], t.outputs["Alpha"])):
        s = _math(nt, "ABSOLUTE", _math(nt, "MULTIPLY", _math(nt, "SUBTRACT", sc, 0.5), 2 * D["line_d"]))
        # (the crack's half-width wanders along it, never zero, wider where it is more open: a width that fell to 0 with
        # a +-2.5 cm edge jitter gated the line on and off every ~10 cm, beaded dashes)
        wid = _math(nt, "MULTIPLY", _math(nt, "ADD", w0, _math(nt, "MULTIPLY", wfac, w1 - w0)),
                    _math(nt, "ADD", 0.5, _math(nt, "MULTIPLY", ac, 0.5)))
        edge = _math(nt, "MULTIPLY", wid, _math(nt, "ADD", 1.0, jit))  # (the edge wanders +-40% of the width)
        k = _math(nt, "MULTIPLY", ac, _smooth_band(nt, _math(nt, "SUBTRACT", s, edge), 0.0, 0.02))
        h = _math(nt, "MULTIPLY", ac, _smooth_band(nt, s, 0.015, 0.06))  # (0.14 m wide, it drew the low poly's zigzag
        # round each line as teeth: the line lies on a step the 0.5 m voxels can only zigzag)
        crack = k if crack is None else _math(nt, "MAXIMUM", crack, k)
        shadow = h if shadow is None else _math(nt, "MAXIMUM", shadow, h)
    return crack, shadow


def _detail(m, D, lines=None):
    """The tiling rock detail as the manifest's detail recipe draws it (a custom shader's version: seamless). The
    swatch on the two strike planes nearest the vertex's smoothed strike (_DETAIL.xy; planes every 45 deg, u = world
    position . the plane's direction, v = _DETAIL.w, the bed coordinate), blended by angle (sharpened like triplanar), and
    on the top plane (u = x, v = y) by 1 - side share (_DETAIL.z). Its normal (tangent space on each plane's own
    axes) is combined with the baked macro normal by RNM (reoriented normal mapping, in world space about the vertex
    normal); its albedo (x 2) multiplies the baked base colour; all weighted by the rock layers' weights."""
    import math as _m
    nt = m.node_tree
    bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
    base_in = bsdf.inputs["Base Color"].links[0].from_socket if bsdf.inputs["Base Color"].links else None
    nrm_in = bsdf.inputs["Normal"].links[0].from_socket if bsdf.inputs["Normal"].links else None
    if base_in is None:
        return
    geo = nt.nodes.new("ShaderNodeNewGeometry")
    Nv = geo.outputs["Normal"]
    Nm = nrm_in if nrm_in is not None else Nv
    w = None  # the rock layers' weight
    for attr, ch in D["rock"]:
        at = nt.nodes.new("ShaderNodeAttribute")
        at.attribute_name = attr
        sep = nt.nodes.new("ShaderNodeSeparateColor")
        nt.links.new(at.outputs["Color"], sep.inputs["Color"])
        x = at.outputs["Alpha"] if ch == 3 else sep.outputs[ch]
        w = x if w is None else _math(nt, "ADD", w, x)
    if D.get("strength", 1.0) != 1.0:
        w = _math(nt, "MULTIPLY", w, D["strength"])
    wn = wa = w
    if D.get("fade"):  # the detail fades with the pixel's footprint (view distance x the pixel's angle, set per view):
        # only where its repetition would show (terrain_swatch.repetition_fade; mipmaps handle the rest), on log
        # footprint
        pa = nt.nodes.new("ShaderNodeValue")
        pa.name = "hp_pixel_angle"
        pa.outputs[0].default_value = 1e-3
        _PIXEL_ANGLE.append(pa)
        cd = nt.nodes.new("ShaderNodeCameraData")
        lnp = _math(nt, "LOGARITHM", _math(nt, "MULTIPLY", cd.outputs["View Distance"], pa.outputs[0]), _m.e)
        wn = wa = _math(nt, "MULTIPLY", w, _smooth_band(nt, lnp, _m.log(D["fade"][0]), _m.log(D["fade"][1])))
    da = nt.nodes.new("ShaderNodeAttribute")
    da.attribute_name = "_DETAIL"
    det = _sep(nt, da.outputs["Vector"])
    v = da.outputs["Alpha"]
    P = _sep(nt, geo.outputs["Position"])
    step = 2 * _m.pi / D["bins"]
    t = _math(nt, "DIVIDE", _math(nt, "ARCTAN2", det[1], det[0]), step)
    k0 = _math(nt, "FLOOR", t)
    f = _math(nt, "SUBTRACT", t, k0)
    f4 = _math(nt, "POWER", f, 4.0)
    g4 = _math(nt, "POWER", _math(nt, "SUBTRACT", 1.0, f), 4.0)
    wf = _math(nt, "DIVIDE", f4, _math(nt, "ADD", f4, g4))
    up = _xyz(nt, 0.0, 0.0, 1.0)
    side = []
    for dk in (0.0, 1.0):
        phi = _math(nt, "MULTIPLY", _math(nt, "ADD", k0, dk), step)
        c, s = _math(nt, "COSINE", phi), _math(nt, "SINE", phi)
        u = _math(nt, "ADD", _math(nt, "MULTIPLY", P[0], c), _math(nt, "MULTIPLY", P[1], s))
        side.append(_plane_sample(nt, D, u, v, _xyz(nt, c, s, 0.0), up, Nv))
    sa = nt.nodes.new("ShaderNodeMix")
    sa.data_type = "RGBA"
    nt.links.new(wf, sa.inputs["Factor"])
    nt.links.new(side[0][0], sa.inputs["A"])
    nt.links.new(side[1][0], sa.inputs["B"])
    sn = _vmath(nt, "NORMALIZE", _mixv(nt, side[0][1], side[1][1], wf))
    ta, tn = _plane_sample(nt, D, P[0], P[1], _xyz(nt, 1.0, 0.0, 0.0), _xyz(nt, 0.0, 1.0, 0.0), Nv)
    alb = nt.nodes.new("ShaderNodeMix")
    alb.data_type = "RGBA"
    nt.links.new(det[2], alb.inputs["Factor"])
    nt.links.new(ta, alb.inputs["A"])
    nt.links.new(sa.outputs["Result"], alb.inputs["B"])
    Nd = _vmath(nt, "NORMALIZE", _mixv(nt, tn, sn, det[2]))
    # RNM about the vertex normal: t = Nm + Nv; u = 2 (Nd.Nv) Nv - Nd; r = t (t.u) / (t.Nv) - u
    tt = _vmath(nt, "ADD", Nm, Nv)
    dn = _vmath(nt, "DOT_PRODUCT", Nd, Nv)
    uu = _vmath(nt, "SUBTRACT", _vmath(nt, "SCALE", Nv, scale=_math(nt, "MULTIPLY", dn, 2.0)), Nd)
    tu = _vmath(nt, "DOT_PRODUCT", tt, uu)
    tz = _vmath(nt, "DOT_PRODUCT", tt, Nv)
    r = _vmath(nt, "SUBTRACT", _vmath(nt, "SCALE", tt, scale=_math(nt, "DIVIDE", tu, _math(nt, "MAXIMUM", tz, 1e-4))),
               uu)
    n_out = _vmath(nt, "NORMALIZE", _mixv(nt, Nm, _vmath(nt, "NORMALIZE", r), wn))
    dark = None
    if lines:  # the structure's crisp lines: darker, and a groove (bump) where the crack is
        crack, shadow = _lines(nt, D, lines, geo)
        bump = nt.nodes.new("ShaderNodeBump")
        bump.inputs["Distance"].default_value = 0.04
        nt.links.new(_math(nt, "MULTIPLY", _math(nt, "ADD", crack, _math(nt, "MULTIPLY", shadow, 0.5)), -1.0),
                     bump.inputs["Height"])
        nt.links.new(n_out, bump.inputs["Normal"])
        nt.links.new(w, bump.inputs["Strength"])
        n_out = bump.outputs["Normal"]
        dark = _math(nt, "ADD", _math(nt, "MULTIPLY", crack, 0.45), _math(nt, "MULTIPLY", shadow, 0.3))
        if D.get("show") == "lines":  # (debug: the lines alone, unlit)
            em = nt.nodes.new("ShaderNodeEmission")
            nt.links.new(dark, em.inputs["Strength"])
            out = next(n for n in nt.nodes if n.type == "OUTPUT_MATERIAL")
            nt.links.new(em.outputs["Emission"], out.inputs["Surface"])
    nt.links.new(n_out, bsdf.inputs["Normal"])
    # albedo: base x (1 + wa (2a - 1)) x (1 - w dark): the lines are structure and never fade
    two = _vmath(nt, "SCALE", alb.outputs["Result"], scale=2.0)
    mod = _mixv(nt, _xyz(nt, 1.0, 1.0, 1.0), two, wa)
    if dark is not None:
        mod = _vmath(nt, "SCALE", mod, scale=_math(nt, "SUBTRACT", 1.0, _math(nt, "MULTIPLY", dark, w)))
    mul = nt.nodes.new("ShaderNodeMix")
    mul.data_type = "RGBA"
    mul.blend_type = "MULTIPLY"
    mul.inputs["Factor"].default_value = 1.0
    nt.links.new(base_in, mul.inputs["A"])
    nt.links.new(mod, mul.inputs["B"])
    nt.links.new(mul.outputs["Result"], bsdf.inputs["Base Color"])


def _upstream(sock, kind):
    """The first node of type `kind` feeding a socket (walking back through the importer's links)."""
    seen = [sock]
    while seen:
        s = seen.pop()
        for ln in s.links:
            n = ln.from_node
            if n.type == kind:
                return n
            seen += [i for i in n.inputs if i.is_linked]
    return None


def _channel(m, ch):
    """One baked channel alone, to see which carries a seam: "base" (base colour, unlit), "ao" (ORM occlusion,
    unlit), "normal" (the normal map on a flat grey), "clay" (geometry only: flat grey, no normal map)."""
    nt = m.node_tree
    b = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
    out = next(n for n in nt.nodes if n.type == "OUTPUT_MATERIAL")
    base = _upstream(b.inputs["Base Color"], "TEX_IMAGE")
    orm = _upstream(b.inputs["Roughness"], "TEX_IMAGE")
    if ch in ("base", "ao"):
        em = nt.nodes.new("ShaderNodeEmission")
        if ch == "base" and base is not None:
            nt.links.new(base.outputs["Color"], em.inputs["Color"])
        elif orm is not None:
            sep = nt.nodes.new("ShaderNodeSeparateColor")
            nt.links.new(orm.outputs["Color"], sep.inputs["Color"])
            nt.links.new(sep.outputs["Red"], em.inputs["Color"])
        nt.links.new(em.outputs["Emission"], out.inputs["Surface"])
        return
    for ln in list(b.inputs["Base Color"].links):
        nt.links.remove(ln)
    b.inputs["Base Color"].default_value = (0.2, 0.2, 0.2, 1)
    if ch == "clay":
        for ln in list(b.inputs["Normal"].links):
            nt.links.remove(ln)


def _id_attr(ob, tile):
    """A FLOAT_COLOR point attribute hp_id = (tile, chart, 0): charts are the mesh's pieces joined by shared vertices
    (the export splits vertices wherever the uv jumps, so each piece is one atlas chart)."""
    me = ob.data
    nv = len(me.vertices)
    lv = np.zeros(len(me.loops), np.int64)
    me.loops.foreach_get("vertex_index", lv)
    ls = np.zeros(len(me.polygons), np.int64)
    me.polygons.foreach_get("loop_start", ls)
    lt = np.zeros(len(me.polygons), np.int64)
    me.polygons.foreach_get("loop_total", lt)
    F = lv.reshape(-1, 3) if len(lv) == 3 * len(ls) else None
    if F is None:
        F = np.array([lv[s_:s_ + 3] for s_ in ls])
    lab = np.arange(nv)
    for _ in range(100000):  # min-label propagation over faces, with pointer jumping
        fm = lab[F].min(1)
        new = lab.copy()
        for c in range(3):
            np.minimum.at(new, F[:, c], fm)
        new = new[new]
        if np.array_equal(new, lab):
            break
        lab = new
    _, cid = np.unique(lab, return_inverse=True)
    at = me.attributes.new("hp_id", "FLOAT_COLOR", "POINT")
    col = np.zeros((nv, 4), np.float32)
    col[:, 0], col[:, 1], col[:, 3] = tile, cid + 1, 1
    at.data.foreach_set("color", col.ravel())


def _id_material():
    """Emission of (tile, chart, view distance): an exact id pass (1 sample, no filter) for the render-space seam
    measure."""
    m = bpy.data.materials.new("hp_ids")
    m.use_nodes = True
    nt = m.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    at = nt.nodes.new("ShaderNodeAttribute")
    at.attribute_name = "hp_id"
    sep = nt.nodes.new("ShaderNodeSeparateColor")
    nt.links.new(at.outputs["Color"], sep.inputs["Color"])
    cd = nt.nodes.new("ShaderNodeCameraData")
    cc = nt.nodes.new("ShaderNodeCombineColor")
    nt.links.new(sep.outputs["Red"], cc.inputs["Red"])
    nt.links.new(sep.outputs["Green"], cc.inputs["Green"])
    nt.links.new(cd.outputs["View Distance"], cc.inputs["Blue"])
    em = nt.nodes.new("ShaderNodeEmission")
    nt.links.new(cc.outputs["Color"], em.inputs["Color"])
    o = nt.nodes.new("ShaderNodeOutputMaterial")
    nt.links.new(em.outputs["Emission"], o.inputs["Surface"])
    return m


def _render_ids(scene, path):
    """The id pass for the current camera, saved as float32 .npy (rows top first): tile, chart, distance (0 = sky)."""
    vl = bpy.context.view_layer
    keep = (scene.cycles.samples, scene.cycles.use_denoising, scene.render.filter_size, scene.render.image_settings.
            file_format, scene.render.image_settings.color_depth, scene.render.filepath, vl.material_override,
            scene.world.node_tree.nodes["Background"].inputs["Strength"].default_value, scene.view_settings.view_transform)
    for o in scene.objects:  # (water and other meshes occlude with id 0)
        if o.type == "MESH" and not o.data.attributes.get("hp_id"):
            o.data.attributes.new("hp_id", "FLOAT_COLOR", "POINT")
    hidden = [o for o in scene.objects if o.type == "CURVE"]  # (the drawn borders; trees occlude with id 0)
    was = [o.hide_render for o in hidden]
    for o in hidden:
        o.hide_render = True
    scene.cycles.samples, scene.cycles.use_denoising, scene.render.filter_size = 1, False, 0.01
    scene.render.image_settings.file_format, scene.render.image_settings.color_depth = "OPEN_EXR", "32"
    scene.view_settings.view_transform = "Standard"
    vl.material_override = _IDMAT[0]
    scene.world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.0
    tmp = path + ".exr"
    scene.render.filepath = tmp
    bpy.ops.render.render(write_still=True)
    img = bpy.data.images.load(tmp)
    a = np.array(img.pixels[:], np.float32).reshape(img.size[1], img.size[0], 4)[::-1, :, :3]
    np.save(path, a)
    bpy.data.images.remove(img)
    os.remove(tmp)
    (scene.cycles.samples, scene.cycles.use_denoising, scene.render.filter_size, scene.render.image_settings.file_format,
     scene.render.image_settings.color_depth, scene.render.filepath, vl.material_override,
     scene.world.node_tree.nodes["Background"].inputs["Strength"].default_value,
     scene.view_settings.view_transform) = keep
    for o, w in zip(hidden, was):
        o.hide_render = w


_IDMAT = []


def _flat(name, rgb):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*rgb, 1)
    b.inputs["Emission Color"].default_value = (*rgb, 1)
    b.inputs["Emission Strength"].default_value = 1.5
    return m


def _water(level):
    bpy.ops.mesh.primitive_plane_add(size=8000, location=(500, 400, level))
    w = bpy.context.object
    wm = bpy.data.materials.new("water")
    wm.use_nodes = True
    nt = wm.node_tree
    b = nt.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (0.05, 0.14, 0.17, 1)
    b.inputs["Roughness"].default_value = 0.2
    tc = nt.nodes.new("ShaderNodeTexCoord")
    mp = nt.nodes.new("ShaderNodeMapping")
    mp.inputs["Scale"].default_value = (0.25, 0.6, 0.25)
    nz = nt.nodes.new("ShaderNodeTexNoise")
    nz.inputs["Detail"].default_value = 6.0
    bp = nt.nodes.new("ShaderNodeBump")
    bp.inputs["Distance"].default_value = 0.4
    nt.links.new(tc.outputs["Object"], mp.inputs["Vector"])
    nt.links.new(mp.outputs["Vector"], nz.inputs["Vector"])
    nt.links.new(nz.outputs["Fac"], bp.inputs["Height"])
    nt.links.new(bp.outputs["Normal"], b.inputs["Normal"])
    w.data.materials.append(wm)
    return w


def _borders(segs, radius):
    me = bpy.data.meshes.new("borders")
    pts = segs.reshape(-1, 3)
    me.vertices.add(len(pts))
    me.vertices.foreach_set("co", pts.astype(np.float64).ravel())
    me.edges.add(len(segs))
    me.edges.foreach_set("vertices", np.arange(len(pts), dtype=np.int32))
    me.update()
    ob = bpy.data.objects.new("borders", me)
    bpy.context.scene.collection.objects.link(ob)
    bpy.context.view_layer.objects.active = ob
    ob.select_set(True)
    bpy.ops.object.convert(target="CURVE")
    ob.data.bevel_depth = radius
    ob.data.bevel_resolution = 1
    m = bpy.data.materials.new("border")
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (0.9, 0.05, 0.02, 1)
    b.inputs["Emission Color"].default_value = (1.0, 0.1, 0.03, 1)
    b.inputs["Emission Strength"].default_value = 2.0
    ob.data.materials.append(m)
    return ob


def run(job):
    for coll in (bpy.data.objects, bpy.data.meshes, bpy.data.cameras, bpy.data.lights, bpy.data.materials):
        for item in list(coll):
            coll.remove(item)
    mat = _terrain_material()
    ground = []
    done = set()
    ch = job.get("channel")
    for ti, p in enumerate(job["glbs"]):
        bpy.ops.import_scene.gltf(filepath=p)
        for ob in bpy.context.selected_objects:
            if ob.type == "MESH":
                if job.get("ids"):
                    _id_attr(ob, ti + 1)
                if job.get("skirt_color"):  # skirts in their own flat colour, to see where they show
                    idx = np.zeros(len(ob.data.polygons), np.int32)
                    ob.data.polygons.foreach_get("material_index", idx)
                    ob.data.materials.clear()
                    ob.data.materials.append(mat)
                    ob.data.materials.append(_flat("skirt", job["skirt_color"]))
                    ob.data.polygons.foreach_set("material_index", idx)
                    ground.append(ob)
                    continue
                # baked tiles keep the importer's material (base colour, ORM, normal map from the GLB); the rest
                # (untextured tiles, skirts, buried backs) take the vertex-colour one
                for s, m in enumerate(ob.data.materials):
                    if not (m and m.name.startswith("terrain_baked") and job.get("textured", True)):
                        ob.data.materials[s] = mat
                    elif job.get("layers") and m.name not in done:
                        _layered(m, job["layers"])
                        done.add(m.name)
                    elif job.get("detail") and m.name not in done:
                        stem = os.path.splitext(os.path.basename(p))[0]
                        ln = os.path.join(os.path.dirname(p), "maps", stem + "_lines.png")
                        _detail(m, job["detail"], ln if os.path.exists(ln) else None)
                        done.add(m.name)
                    elif ch and m.name not in done:
                        _channel(m, ch)
                        done.add(m.name)
                if not len(ob.data.materials):
                    ob.data.materials.append(mat)
                ground.append(ob)
    if job.get("sea") is not None:
        _water(job["sea"])
    if job.get("trees"):
        by = {}
        with open(job["trees"]) as f:
            for r in csv.DictReader(f):
                by.setdefault(r["kind"] or "broadleaf", []).append((float(r["x"]), float(r["y"]), float(r["z"])))
        box = job.get("tree_box")
        eyes = np.array([v["eye"] for v in job["views"]], float).reshape(-1, 3)
        for kind, pts in by.items():
            pts = np.array(pts)
            if box:
                (x0, y0), (x1, y1) = box
                pts = pts[(pts[:, 0] >= x0) & (pts[:, 0] <= x1) & (pts[:, 1] >= y0) & (pts[:, 1] <= y1)]
            if len(pts) and len(eyes):  # no tree over a camera (views from inside a crown rendered all green)
                d = np.linalg.norm(pts[:, None, :2] - eyes[None, :, :2], axis=2).min(1)
                pts = pts[d > 7.0]
            if not len(pts):
                continue
            me = bpy.data.meshes.new("trees_" + kind)
            me.vertices.add(len(pts))
            me.vertices.foreach_set("co", pts.astype(np.float64).ravel())
            ob = bpy.data.objects.new("trees_" + kind, me)
            bpy.context.scene.collection.objects.link(ob)
            bt._instance(ob, kind)
    if ch == "clay":  # (untextured parts too: geometry alone)
        bb = mat.node_tree.nodes["Principled BSDF"].inputs["Base Color"]
        for ln in list(bb.links):
            mat.node_tree.links.remove(ln)
        bb.default_value = (0.2, 0.2, 0.2, 1)
    if job.get("ids"):
        _IDMAT.append(_id_material())
    border_ob = None
    if job.get("borders"):
        d = np.load(job["borders"])
        border_ob = _borders(d["segs"], job.get("border_radius", 0.35))
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.samples = job.get("samples", 32)
    scene.cycles.use_denoising = True
    scene.render.resolution_x, scene.render.resolution_y = job["size"]
    scene.view_settings.view_transform = "AgX"
    world = bpy.data.worlds.new("sky")
    scene.world = world
    world.use_nodes = True
    sky = world.node_tree.nodes.new("ShaderNodeTexSky")
    world.node_tree.links.new(sky.outputs["Color"], world.node_tree.nodes["Background"].inputs["Color"])
    world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.12
    sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN"))
    sun.data.energy = 2.4
    sun.data.angle = 0.02
    scene.collection.objects.link(sun)
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
    cam.data.clip_start, cam.data.clip_end = 0.1, 8000
    scene.collection.objects.link(cam)
    scene.camera = cam
    lamp = bpy.data.objects.new("lamp", bpy.data.lights.new("lamp", "POINT"))  # a headlamp for views inside caves
    lamp.data.shadow_soft_size = 0.3
    scene.collection.objects.link(lamp)
    # a second, weaker light down the view: a headlamp alone blew out the walls beside the eye and left the passage
    # ahead dark (inverse square), which read as fog
    fill = bpy.data.objects.new("fill", bpy.data.lights.new("fill", "POINT"))
    fill.data.shadow_soft_size = 1.0
    scene.collection.objects.link(fill)
    for v in job["views"]:
        cam.location = Vector(v["eye"])
        lamp.data.energy = float(v.get("lamp", 0.0))
        scene.view_settings.exposure = float(v.get("exposure", 0.0))
        # the lamp a little above and to the right of the eye, so ledges and roofs cast a shadow line
        fwd = (Vector(v["look"]) - Vector(v["eye"])).normalized()
        right = fwd.cross(Vector((0, 0, 1)))
        right = right.normalized() if right.length > 1e-6 else Vector((1, 0, 0))
        lamp.location = Vector(v["eye"]) + Vector((0, 0, 0.4)) + 0.35 * right
        reach = min((Vector(v["look"]) - Vector(v["eye"])).length, float(v.get("fill_at", 8.0)))
        fill.location = Vector(v["eye"]) + fwd * reach + Vector((0, 0, 0.5))
        fill.data.energy = float(v.get("fill", 0.4)) * float(v.get("lamp", 0.0))
        cam.rotation_euler = (Vector(v["look"]) - Vector(v["eye"])).to_track_quat("-Z", "Y").to_euler()
        cam.data.angle = math.radians(v.get("fov", 55))
        for pa in _PIXEL_ANGLE:  # (the detail fade: radians per pixel across the image's width)
            pa.outputs[0].default_value = 2 * math.tan(cam.data.angle / 2) / job["size"][0]
        b, h =[math.radians(x) for x in v.get("sun", (225, 30))]
        toward = Vector((math.cos(h) * math.sin(b), math.cos(h) * math.cos(b), math.sin(h)))
        sun.rotation_euler = (-toward).to_track_quat("-Z", "Y").to_euler()
        sky.sun_elevation, sky.sun_rotation = h, -b
        if border_ob is not None:
            border_ob.hide_render = not v.get("borders", False)
        scene.render.filepath = v["out"]
        bpy.ops.render.render(write_still=True)
        if job.get("ids"):
            if border_ob is not None:
                border_ob.hide_render = True
            _render_ids(scene, os.path.splitext(v["out"])[0] + "_ids.npy")


if __name__ == "__main__":
    run(json.load(open(sys.argv[sys.argv.index("--") + 1])))
