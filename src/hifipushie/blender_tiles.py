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


def _styled(m, S):
    """The styles recipe (terrain_style.RECIPE) on an imported baked material: per style, its layer textures laid in
    world metres (box projection = triplanar) weighted by the _WEIGHTS attributes, x mix(1, baked / R, macro); the
    styles mixed by the weight maps (north-up over the extent, sampled at world x, y); the baked normal mixed toward
    the geometry's by macro_normal, the styles' layer heights as a bump. A reference for an engine's shader."""
    nt = m.node_tree
    bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
    base_in = bsdf.inputs["Base Color"].links[0].from_socket if bsdf.inputs["Base Color"].links else None
    nrm_in = bsdf.inputs["Normal"].links[0].from_socket if bsdf.inputs["Normal"].links else None
    if base_in is None:
        return
    L = lambda t: nt.nodes.new(t)

    def math(op, a, b, clamp=False):
        n = L("ShaderNodeMath")
        n.operation = op
        n.use_clamp = clamp
        for k, v in enumerate((a, b)):
            if isinstance(v, (int, float)):
                n.inputs[k].default_value = v
            else:
                nt.links.new(v, n.inputs[k])
        return n.outputs[0]

    def mixc(op, a, b, fac=1.0):
        n = L("ShaderNodeMix")
        n.data_type = "RGBA"
        n.blend_type = op
        if isinstance(fac, (int, float)):
            n.inputs["Factor"].default_value = fac
        else:
            nt.links.new(fac, n.inputs["Factor"])
        for k, v in ((6, a), (7, b)):  # (the colour A / B sockets; "A" by name is the float one)
            if isinstance(v, (list, tuple)):
                n.inputs[k].default_value = (*v, 1.0)
            else:
                nt.links.new(v, n.inputs[k])
        return n.outputs[2]

    def image(path, srgb):
        key = (path, srgb)
        if key not in _IMAGES:
            im = bpy.data.images.load(path, check_existing=False)
            im.colorspace_settings.name = "sRGB" if srgb else "Non-Color"
            im.alpha_mode = "CHANNEL_PACKED"  # (style albedos carry the height in alpha: data, never transparency)
            _IMAGES[key] = im
        return _IMAGES[key]

    geo = L("ShaderNodeNewGeometry")
    # layer weights
    wts = {}
    for lay, (attr, ch) in S["weights"].items():
        at = L("ShaderNodeAttribute")
        at.attribute_name = attr
        if ch == 3:
            wts[lay] = at.outputs["Alpha"]
        else:
            sep = L("ShaderNodeSeparateColor")
            nt.links.new(at.outputs["Color"], sep.inputs["Color"])
            wts[lay] = sep.outputs[ch]
    # R = sum w_l x realistic colour_l (linear)
    R = None
    for lay, w in wts.items():
        t = mixc("MIX", [0, 0, 0], list(S["ref"][lay]), w)
        R = t if R is None else mixc("ADD", R, t)
    ratio = mixc("DIVIDE", base_in, R)
    # the style weight maps
    sw = {}
    ext = S["extent"]
    uv = L("ShaderNodeMapping")
    uv.vector_type = "POINT"
    nt.links.new(geo.outputs["Position"], uv.inputs["Vector"])
    sx, sy = 1.0 / (ext[1][0] - ext[0][0]), 1.0 / (ext[1][1] - ext[0][1])
    uv.inputs["Scale"].default_value = (sx, sy, 1.0)
    uv.inputs["Location"].default_value = (-ext[0][0] * sx, -ext[0][1] * sy, 0.0)
    for path, names in S["maps"]:
        tx = L("ShaderNodeTexImage")
        tx.image = image(path, False)
        tx.extension = "EXTEND"
        nt.links.new(uv.outputs["Vector"], tx.inputs["Vector"])
        sep = L("ShaderNodeSeparateColor")
        nt.links.new(tx.outputs["Color"], sep.inputs["Color"])
        for k, nm in enumerate(names):
            sw[nm] = tx.outputs["Alpha"] if k == 3 else sep.outputs[k]
    col, hgt, mn = None, None, None
    for st in S["styles"]:
        A, H = None, None
        for lay, T in st["layers"].items():
            if lay not in wts:
                continue
            mp = L("ShaderNodeVectorMath")
            mp.operation = "SCALE"
            mp.inputs["Scale"].default_value = 1.0 / T["size"]
            nt.links.new(geo.outputs["Position"], mp.inputs[0])
            ta = L("ShaderNodeTexImage")
            ta.image = image(T["albedo"], True)
            ta.projection = "BOX" if T.get("projection") == "triplanar" else "FLAT"  # (soft layers top-down)
            ta.projection_blend = 0.3
            nt.links.new(mp.outputs["Vector"], ta.inputs["Vector"])
            tcol = ta.outputs["Color"]
            sm, rs = T.get("small"), S.get("rock_scale")
            if sm and rs:  # (on small / thin rock the layer's plain texture: anime strata fade off stacks and fins)
                tp = L("ShaderNodeTexImage")
                tp.image = image(sm["albedo"], True)
                tp.projection = ta.projection
                tp.projection_blend = 0.3
                nt.links.new(mp.outputs["Vector"], tp.inputs["Vector"])
                rsx = L("ShaderNodeTexImage")
                rsx.image = image(rs["file"], False)
                rsx.extension = "EXTEND"
                nt.links.new(uv.outputs["Vector"], rsx.inputs["Vector"])
                sp = L("ShaderNodeSeparateColor")
                nt.links.new(rsx.outputs["Color"], sp.inputs["Color"])
                ks = []
                for ch, rng, key in ((0, rs["face_m"], "face_m"), (1, rs["thick_m"], "thick_m")):
                    mr = L("ShaderNodeMapRange")
                    mr.interpolation_type = "SMOOTHSTEP"
                    nt.links.new(sp.outputs[ch], mr.inputs["Value"])
                    mr.inputs["From Min"].default_value = sm[key][0] / rng
                    mr.inputs["From Max"].default_value = sm[key][1] / rng
                    ks.append(mr.outputs["Result"])
                tcol = mixc("MIX", tp.outputs["Color"], tcol, math("MULTIPLY", ks[0], ks[1]))
            t = mixc("MIX", [0, 0, 0], tcol, wts[lay])
            A = t if A is None else mixc("ADD", A, t)
            th = L("ShaderNodeTexImage")
            th.image = image(T["height"], False)
            th.projection = "BOX" if T.get("projection") == "triplanar" else "FLAT"  # (soft layers top-down)
            th.projection_blend = 0.3
            nt.links.new(mp.outputs["Vector"], th.inputs["Vector"])
            h = math("MULTIPLY", math("SUBTRACT", th.outputs["Color"], 0.5), 2 * T["height_m"])
            h = math("MULTIPLY", h, wts[lay])
            H = h if H is None else math("ADD", H, h)
        if A is None:
            continue
        a = mixc("MULTIPLY", A, mixc("MIX", [1, 1, 1], ratio, st["macro"]))
        w = sw.get(st["name"])
        if w is None:
            continue
        a = mixc("MIX", [0, 0, 0], a, w)
        col = a if col is None else mixc("ADD", col, a)
        hw = math("MULTIPLY", H, w)
        hgt = hw if hgt is None else math("ADD", hgt, hw)
        mw = math("MULTIPLY", w, st["macro_normal"])
        mn = mw if mn is None else math("ADD", mn, mw)
    if col is None:
        return
    nt.links.new(col, bsdf.inputs["Base Color"])
    nmix = L("ShaderNodeMix")
    nmix.data_type = "VECTOR"
    nt.links.new(mn, nmix.inputs["Factor"])
    nt.links.new(geo.outputs["Normal"], nmix.inputs[4])
    if nrm_in is not None:
        nt.links.new(nrm_in, nmix.inputs[5])
    else:
        nt.links.new(geo.outputs["Normal"], nmix.inputs[5])
    if S.get("bump", False):  # (the style layers' heights as a bump: off by default, Blender's bump over box-projected
        bump = L("ShaderNodeBump")  # textures drew thin contour-like lines on slopes; an engine uses the normal maps)
        bump.inputs["Distance"].default_value = 1.0
        nt.links.new(hgt, bump.inputs["Height"])
        nt.links.new(nmix.outputs[1], bump.inputs["Normal"])
        nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    else:
        nt.links.new(nmix.outputs[1], bsdf.inputs["Normal"])


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



def _grass(m, G):
    """The grass detail as the manifest's ground_detail recipe draws it: the turf swatch laid from above (uv = world
    x, y / size, a second sampling at 1.618 x offset, chosen between in ~8 m patches), weighted by the grass/scrub
    layers' weights and faded out with the view distance; albedo multiplies the baked base colour, the normal is RNM-combined onto the
    baked one."""
    nt = m.node_tree
    bsdf = next((n for n in nt.nodes if n.type == "BSDF_PRINCIPLED"), None)
    if bsdf is None or not bsdf.inputs["Base Color"].links:
        return
    base_in = bsdf.inputs["Base Color"].links[0].from_socket
    nrm_in = bsdf.inputs["Normal"].links[0].from_socket if bsdf.inputs["Normal"].links else None
    geo = nt.nodes.new("ShaderNodeNewGeometry")
    Nv = geo.outputs["Normal"]
    Nm = nrm_in if nrm_in is not None else Nv
    w = None
    for attr, ch in G["weights"]:
        at = nt.nodes.new("ShaderNodeAttribute")
        at.attribute_name = attr
        sep = nt.nodes.new("ShaderNodeSeparateColor")
        nt.links.new(at.outputs["Color"], sep.inputs["Color"])
        x = at.outputs["Alpha"] if ch == 3 else sep.outputs[ch]
        w = x if w is None else _math(nt, "ADD", w, x)
    if w is None:
        return
    cd = nt.nodes.new("ShaderNodeCameraData")
    fade = _smooth_band(nt, cd.outputs["View Distance"], G["fade"][0], G["fade"][1])
    w = _math(nt, "MULTIPLY", _math(nt, "MINIMUM", w, 1.0), fade)
    P = _sep(nt, geo.outputs["Position"])
    uv = _xyz(nt, P[0], P[1], 0.0)
    v1 = _vmath(nt, "SCALE", uv, scale=1.0 / G["size"])
    v2 = _vmath(nt, "ADD", _vmath(nt, "SCALE", uv, scale=1.0 / (G["size"] * 1.618)), _xyz(nt, 0.37, 0.71, 0.0))
    # the two samplings CHOSEN between by a smooth mask over ~8 m patches, not averaged: averaged, their normals
    # cancelled where the two lattices ran out of phase and added where in phase, and the beat of the 2 m and 3.2 m
    # periods (~5 m) shaded the turf in soft dark and light blotches under a high sun (hole 7 at noon)
    mz = nt.nodes.new("ShaderNodeTexNoise")
    mz.inputs["Scale"].default_value = 1.0 / 8.0
    mz.inputs["Detail"].default_value = 1.0
    nt.links.new(uv, mz.inputs["Vector"])
    mk = nt.nodes.new("ShaderNodeMapRange")
    mk.interpolation_type = "SMOOTHSTEP"
    mk.inputs["From Min"].default_value, mk.inputs["From Max"].default_value = 0.42, 0.58
    nt.links.new(mz.outputs["Fac"], mk.inputs["Value"])
    am = nt.nodes.new("ShaderNodeMix")
    am.data_type = "RGBA"
    nt.links.new(mk.outputs["Result"], am.inputs["Factor"])
    nt.links.new(_tex(nt, G["albedo"], v1), am.inputs["A"])
    nt.links.new(_tex(nt, G["albedo"], v2), am.inputs["B"])
    dec = lambda col: _vmath(nt, "SUBTRACT", _vmath(nt, "SCALE", col, scale=2.0), 1.0)
    nd = _sep(nt, _vmath(nt, "NORMALIZE", _mixv(nt, dec(_tex(nt, G["normal"], v1)), dec(_tex(nt, G["normal"], v2)),
                                                mk.outputs["Result"])))
    proj = lambda A: _vmath(nt, "NORMALIZE", _vmath(nt, "SUBTRACT", A, _vmath(
        nt, "SCALE", Nv, scale=_vmath(nt, "DOT_PRODUCT", Nv, A))))
    Tt, Bt = proj(_xyz(nt, 1.0, 0.0, 0.0)), proj(_xyz(nt, 0.0, 1.0, 0.0))
    Nd = _vmath(nt, "NORMALIZE", _vmath(nt, "ADD", _vmath(nt, "ADD", _vmath(nt, "SCALE", Tt, scale=nd[0]),
                                                           _vmath(nt, "SCALE", Bt, scale=nd[1])),
                                         _vmath(nt, "SCALE", Nv, scale=nd[2])))
    tt = _vmath(nt, "ADD", Nm, Nv)
    dn = _vmath(nt, "DOT_PRODUCT", Nd, Nv)
    uu = _vmath(nt, "SUBTRACT", _vmath(nt, "SCALE", Nv, scale=_math(nt, "MULTIPLY", dn, 2.0)), Nd)
    tu = _vmath(nt, "DOT_PRODUCT", tt, uu)
    tz = _vmath(nt, "DOT_PRODUCT", tt, Nv)
    r = _vmath(nt, "SUBTRACT", _vmath(nt, "SCALE", tt, scale=_math(nt, "DIVIDE", tu, _math(nt, "MAXIMUM", tz, 1e-4))),
               uu)
    nt.links.new(_vmath(nt, "NORMALIZE", _mixv(nt, Nm, _vmath(nt, "NORMALIZE", r), w)), bsdf.inputs["Normal"])
    mod = _mixv(nt, _xyz(nt, 1.0, 1.0, 1.0), _vmath(nt, "SCALE", am.outputs["Result"], scale=2.0), w)
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
            at = o.data.attributes.new("hp_id", "FLOAT_COLOR", "POINT")
            # (explicitly 0: a new colour attribute starts WHITE, so the sea read as tile 1 chart 1 and every
            # waterline counted as a tile border: pebble's chasm "tile jump excess 2.7-2.9" was the waterline)
            at.data.foreach_set("color", np.zeros(4 * len(o.data.vertices), np.float32))
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


def _flat(name, rgb, glow=1.5):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*rgb, 1)
    b.inputs["Emission Color"].default_value = (*rgb, 1)
    b.inputs["Emission Strength"].default_value = glow
    return m


_HAZE = []  # (the haze's emission nodes, one per material: their colour set per view)


def _haze(m, dist):
    """Aerial perspective on a material: what the camera sees of it fades toward the sky's colour at the horizon in
    the view's direction (measured per view, `_horizon`), by 1 - exp(-d / dist), d = the camera ray's length. Without it
    every distance read alike (flat cut-outs on a plain sea). (A Sky Texture inside the material lost its Vector input
    in the importer's scene and fell back to object coordinates: a pale gradient per tile.)"""
    if not m or not m.use_nodes:
        return
    nt = m.node_tree
    out = next((n for n in nt.nodes if n.type == "OUTPUT_MATERIAL" and n.is_active_output), None)
    if out is None or not out.inputs["Surface"].links:
        return
    src = out.inputs["Surface"].links[0].from_socket
    lp = nt.nodes.new("ShaderNodeLightPath")
    dv = nt.nodes.new("ShaderNodeMath")
    dv.operation = "DIVIDE"
    nt.links.new(lp.outputs["Ray Length"], dv.inputs[0])
    dv.inputs[1].default_value = -float(dist)
    ex = nt.nodes.new("ShaderNodeMath")
    ex.operation = "EXPONENT"
    nt.links.new(dv.outputs[0], ex.inputs[0])
    fac = nt.nodes.new("ShaderNodeMath")
    fac.operation = "SUBTRACT"
    fac.inputs[0].default_value = 1.0
    nt.links.new(ex.outputs[0], fac.inputs[1])
    cam = nt.nodes.new("ShaderNodeMath")
    cam.operation = "MULTIPLY"
    nt.links.new(fac.outputs[0], cam.inputs[0])
    nt.links.new(lp.outputs["Is Camera Ray"], cam.inputs[1])
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs["Strength"].default_value = 1.0
    mix = nt.nodes.new("ShaderNodeMixShader")
    nt.links.new(cam.outputs[0], mix.inputs["Fac"])
    nt.links.new(src, mix.inputs[1])
    nt.links.new(em.outputs[0], mix.inputs[2])
    nt.links.new(mix.outputs[0], out.inputs["Surface"])
    _HAZE.append(em)


def _horizon(scene, cam, look_dir, tmp):
    """The sky's colour (linear) at the horizon in the view's direction: a 16 x 16 render of the sky alone (every object
    hidden), camera level and narrow."""
    keep = (scene.render.resolution_x, scene.render.resolution_y, scene.cycles.samples, scene.cycles.use_denoising,
            scene.render.image_settings.file_format, scene.render.image_settings.color_depth, scene.render.filepath,
            tuple(cam.rotation_euler), cam.data.angle, scene.view_settings.view_transform)
    hidden = [o for o in scene.objects if o.type != "CAMERA" and not o.hide_render]
    for o in hidden:
        o.hide_render = True
    d = Vector((look_dir.x, look_dir.y, 0.0))
    d = d.normalized() if d.length > 1e-6 else Vector((0.0, 1.0, 0.0))
    d.z = 0.03
    cam.rotation_euler = d.normalized().to_track_quat("-Z", "Y").to_euler()
    cam.data.angle = math.radians(4.0)
    scene.render.resolution_x = scene.render.resolution_y = 16
    scene.cycles.samples, scene.cycles.use_denoising = 4, False
    scene.render.image_settings.file_format, scene.render.image_settings.color_depth = "OPEN_EXR", "32"
    scene.view_settings.view_transform = "Standard"
    scene.render.filepath = tmp
    bpy.ops.render.render(write_still=True)
    img = bpy.data.images.load(tmp)
    a = np.array(img.pixels[:], np.float32).reshape(-1, 4)[:, :3].mean(0)
    bpy.data.images.remove(img)
    os.remove(tmp)
    for o in hidden:
        o.hide_render = False
    (scene.render.resolution_x, scene.render.resolution_y, scene.cycles.samples, scene.cycles.use_denoising,
     scene.render.image_settings.file_format, scene.render.image_settings.color_depth, scene.render.filepath, rot,
     cam.data.angle, scene.view_settings.view_transform) = keep
    cam.rotation_euler = rot
    return a


def _rivers(rivers):
    """The rivers' water: per river a ribbon along its path at its own level ([x, y, level, half width] rows), clear
    enough that the bed shows through (transparent tinted by a little green, a glossy rippled surface by Fresnel)."""
    V, F = [], []
    for rows in rivers:
        R = np.asarray(rows, float)
        if len(R) < 2:
            continue
        t = np.gradient(R[:, :2], axis=0)
        t /= np.maximum(np.linalg.norm(t, axis=1, keepdims=True), 1e-9)
        nrm = np.c_[-t[:, 1], t[:, 0]]
        k0 = len(V)
        for i in range(len(R)):
            for sgn in (-1, 1):
                V.append((R[i, 0] + sgn * R[i, 3] * nrm[i, 0], R[i, 1] + sgn * R[i, 3] * nrm[i, 1], R[i, 2]))
        for i in range(len(R) - 1):
            F.append((k0 + 2 * i, k0 + 2 * i + 1, k0 + 2 * i + 3, k0 + 2 * i + 2))
    if not F:
        return
    me = bpy.data.meshes.new("river_water")
    me.from_pydata(V, [], F)
    ob = bpy.data.objects.new("river_water", me)
    bpy.context.scene.collection.objects.link(ob)
    m = bpy.data.materials.new("river_water")
    m.use_nodes = True
    nt = m.node_tree
    for n in list(nt.nodes):
        if n.type != "OUTPUT_MATERIAL":
            nt.nodes.remove(n)
    out = next(n for n in nt.nodes if n.type == "OUTPUT_MATERIAL")
    tr = nt.nodes.new("ShaderNodeBsdfTransparent")
    tr.inputs["Color"].default_value = (0.72, 0.84, 0.78, 1)
    gl = nt.nodes.new("ShaderNodeBsdfGlossy")
    gl.inputs["Roughness"].default_value = 0.06
    fr = nt.nodes.new("ShaderNodeFresnel")
    fr.inputs["IOR"].default_value = 1.33
    geo = nt.nodes.new("ShaderNodeNewGeometry")
    nz = nt.nodes.new("ShaderNodeTexNoise")
    nz.inputs["Scale"].default_value = 3.0
    nz.inputs["Detail"].default_value = 3.0
    nt.links.new(geo.outputs["Position"], nz.inputs["Vector"])
    bp = nt.nodes.new("ShaderNodeBump")
    bp.inputs["Distance"].default_value = 0.03
    bp.inputs["Strength"].default_value = 0.6
    nt.links.new(nz.outputs["Fac"], bp.inputs["Height"])
    nt.links.new(bp.outputs["Normal"], gl.inputs["Normal"])
    nt.links.new(bp.outputs["Normal"], fr.inputs["Normal"])
    mx = nt.nodes.new("ShaderNodeMixShader")
    nt.links.new(fr.outputs["Fac"], mx.inputs["Fac"])
    nt.links.new(tr.outputs["BSDF"], mx.inputs[1])
    nt.links.new(gl.outputs["BSDF"], mx.inputs[2])
    nt.links.new(mx.outputs["Shader"], out.inputs["Surface"])
    ob.data.materials.append(m)


def _water(level, L=None):
    """The sea: a plane with a noise ripple. L (the light preset) may set "water" (linear base colour) and
    "water_roughness"; water's IOR is 1.33 (the Principled default 1.5 reflected ~40% more of the pale low sky)."""
    L = L or {}
    # (out past the horizon: an 8 km plane ended ~4 km off and the sky below the horizon showed as a pale band between
    # the sea's edge and the sky; the eye's horizon is ~16 km from 20 m up, ~45 km from 150 m)
    bpy.ops.mesh.primitive_plane_add(size=200000, location=(500, 400, level))
    w = bpy.context.object
    wm = bpy.data.materials.new("water")
    wm.use_nodes = True
    nt = wm.node_tree
    b = nt.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = tuple(L.get("water", (0.05, 0.14, 0.17))) + (1,)
    b.inputs["Roughness"].default_value = float(L.get("water_roughness", 0.2))
    if "water" in L and "IOR" in b.inputs:
        b.inputs["IOR"].default_value = 1.33
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
                    if job.get("buried_color") and m and m.name.startswith("terrain_buried"):
                        # (the cliff shell's buried back in a flat colour: where an engine shows it, it is a fault)
                        ob.data.materials[s] = _flat("buried", job["buried_color"], 0.0)
                    elif not (m and m.name.startswith("terrain_baked") and job.get("textured", True)):
                        ob.data.materials[s] = mat
                    elif ch and m.name not in done:  # (first: under the detail recipe a channel view drew everything)
                        _channel(m, ch)
                        done.add(m.name)
                    elif job.get("styles") and m.name not in done:
                        _styled(m, job["styles"])
                        done.add(m.name)
                    elif job.get("layers") and m.name not in done:
                        _layered(m, job["layers"])
                        done.add(m.name)
                    elif job.get("detail") and m.name not in done:
                        stem = os.path.splitext(os.path.basename(p))[0]
                        ln = os.path.join(os.path.dirname(p), "maps", stem + "_lines.png")
                        _detail(m, job["detail"], ln if os.path.exists(ln) else None)
                        done.add(m.name)
                if not len(ob.data.materials):
                    ob.data.materials.append(mat)
                ground.append(ob)
    if job.get("grass") and job.get("textured", True) and not ch:  # the tiling turf over the baked maps
        for m in list(bpy.data.materials):
            if m.name.startswith("terrain_baked") and m.use_nodes:
                for g in (job["grass"] if isinstance(job["grass"], list) else [job["grass"]]):
                    _grass(m, g)  # (one swatch per kind: mown turf, long grass)
    if job.get("sea") is not None:
        _water(job["sea"], job.get("light") or {})
    if job.get("rivers"):
        _rivers(job["rivers"])
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
    for kind, rows in (job.get("clutter") or {}).items():  # ground clutter placeholders (bushes, grass, boulders)
        rows = np.asarray(rows, float)
        if not len(rows):
            continue
        if rows.shape[1] == 3:  # (positions only: a random size and turn)
            rng = np.random.default_rng(len(rows))
            rows = np.c_[rows, rng.uniform(0.7, 1.3, len(rows)), rng.uniform(0, 360, len(rows)), np.ones(len(rows))]
        bt.clutter(kind, rows, job.get("sea"))
    if job.get("props"):  # the sites' props as stand-ins (scale cues: a basket, a tee pad, the lodge)
        pr = job["props"]
        bt.props(np.array([p_[:4] for p_ in pr], float), [p_[4] for p_ in pr])
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
    if job.get("grade"):  # (a grade, e.g. "AgX - Punchy": what a game's tonemapper and colour grade would do)
        scene.view_settings.look = job["grade"]
    world = bpy.data.worlds.new("sky")
    scene.world = world
    world.use_nodes = True
    sky = world.node_tree.nodes.new("ShaderNodeTexSky")
    if job.get("haze") and hasattr(sky, "dust_density"):  # (the same clear sky the haze takes its colour from)
        sky.dust_density, sky.air_density = 0.3, 0.8
    L = job.get("light") or {}  # (a lighting preset: render_tiles(light=...))
    if hasattr(sky, "dust_density"):
        sky.dust_density = float(L.get("dust", sky.dust_density))
        sky.air_density = float(L.get("air", sky.air_density))
    if L.get("sky_sat"):  # (a camera's sky, as a photo shows it: deeper than Nishita's at the low elevations a level
        # view sees; camera and glossy rays only, so the light the sky casts (shadows' tint, the grass) stays as measured)
        wn = world.node_tree.nodes
        hs = wn.new("ShaderNodeHueSaturation")
        hs.inputs["Saturation"].default_value = float(L["sky_sat"])
        hs.inputs["Value"].default_value = float(L.get("sky_value", 1.0))
        world.node_tree.links.new(sky.outputs["Color"], hs.inputs["Color"])
        if L.get("sky_horizon_tint"):  # (Nishita's low sky is near white; a photo's stays blue to the horizon: tinted
            # toward the horizon, fading out by ~20 deg up)
            tc = wn.new("ShaderNodeTexCoord")
            sz = wn.new("ShaderNodeSeparateXYZ")
            world.node_tree.links.new(tc.outputs["Generated"], sz.inputs["Vector"])
            mr = wn.new("ShaderNodeMapRange")
            mr.inputs["From Min"].default_value, mr.inputs["From Max"].default_value = 0.0, 0.35
            mr.inputs["To Min"].default_value, mr.inputs["To Max"].default_value = 1.0, 0.0
            world.node_tree.links.new(sz.outputs["Z"], mr.inputs["Value"])
            tm_ = wn.new("ShaderNodeMix")
            tm_.data_type, tm_.blend_type = "RGBA", "MULTIPLY"
            tm_.inputs["B"].default_value = tuple(L["sky_horizon_tint"]) + (1.0,)
            world.node_tree.links.new(mr.outputs["Result"], tm_.inputs["Factor"])
            world.node_tree.links.new(hs.outputs["Color"], tm_.inputs["A"])
            hs_out = tm_.outputs["Result"]
        else:
            hs_out = hs.outputs["Color"]
        lp = wn.new("ShaderNodeLightPath")
        mx = wn.new("ShaderNodeMix")
        mx.data_type = "RGBA"
        mxr = wn.new("ShaderNodeMath")  # (and in reflections: the sea mirrors the sky the eye sees)
        mxr.operation = "MAXIMUM"
        world.node_tree.links.new(lp.outputs["Is Camera Ray"], mxr.inputs[0])
        if L.get("sky_glossy", True):
            world.node_tree.links.new(lp.outputs["Is Glossy Ray"], mxr.inputs[1])
        world.node_tree.links.new(mxr.outputs[0], mx.inputs["Factor"])
        world.node_tree.links.new(sky.outputs["Color"], mx.inputs["A"])
        world.node_tree.links.new(hs_out, mx.inputs["B"])
        world.node_tree.links.new(mx.outputs["Result"], wn["Background"].inputs["Color"])
    else:
        world.node_tree.links.new(sky.outputs["Color"], world.node_tree.nodes["Background"].inputs["Color"])
    world.node_tree.nodes["Background"].inputs["Strength"].default_value = float(L.get("sky_strength", 0.12))
    if job.get("haze") and not job.get("channel"):
        for m in list(bpy.data.materials):
            _haze(m, job["haze"])
    sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN"))
    sun.data.energy = float(L.get("sun_energy", 2.4))
    sun.data.angle = 0.02
    scene.collection.objects.link(sun)
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
    cam.data.clip_start, cam.data.clip_end = 0.1, 250000  # (the sea reaches the horizon)
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
        scene.view_settings.exposure = float(v.get("exposure") or L.get("exposure", 0.0))  # (a view's own wins)
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
        if L.get("meter") and not v.get("exposure"):  # (a camera's metering: a high sun's ground exposed down, a low
            # one's up, as a photographer would; at a fixed exposure a noon sun washed the grass out)
            scene.view_settings.exposure = float(L.get("exposure", 0.0)) - float(L["meter"]) * math.log2(
                max(math.sin(h), 0.08) / math.sin(math.radians(25.0)))
        toward = Vector((math.cos(h) * math.sin(b), math.cos(h) * math.cos(b), math.sin(h)))
        sun.rotation_euler = (-toward).to_track_quat("-Z", "Y").to_euler()
        # (Blender 5.1: sun_rotation = the bearing; -bearing put the sky's glow on the wrong side, blender_terrain)
        sky.sun_elevation, sky.sun_rotation = h, b
        if _HAZE:  # (the haze takes the horizon's colour in this view's direction, under this view's sun)
            hz = _horizon(scene, cam, fwd, v["out"] + ".horizon.exr")
            for em in _HAZE:
                em.inputs["Color"].default_value = (float(hz[0]), float(hz[1]), float(hz[2]), 1.0)
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
