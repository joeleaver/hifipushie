"""Hair cards drawn as a game draws them (inside Blender, EEVEE without ray tracing): the material is the export's
shading notes in nodes (shading.py "hair_cards"), so judging a card export judges what an engine is told to do.

    albedo = basecolor.rgb * COLOR_0.rgb * (1 - 0.35 aux.r) * lerp(0.65, 1, aux.b) * (1 + 0.12 (2 aux.g - 1))
    coverage = basecolor.a > cutoff (dithered: TAA / alpha-to-coverage resolve it), two-sided, one normal
    specular: tinted, half strength (a card is many round hairs, not a mirror), roughness 0.5
    diffuse: wrapped  max(0, (N.L + w) / (1 + w)), w = 0.45 (the notes'): Principled gives max(0, N.L) with the
             shadow map; the rest of the wrap, wrap - max(0, N.L), is added per sun as emission (albedo x sun
             irradiance / pi x lift), unshadowed (light through hair). Suns are read before every frame (set_wrap_lights).

`game_material` is shared by blender_scene.hair_glb_look ("game" alpha) and can serve blender_game."""
import bpy

GLTF_SPEC = 1  # (c6) the preview reads the GLB's own highlight (specular, colour, ORM roughness, anisotropy); 0 = flat 0.25 isotropic, rough .5
ONE_NORMAL = 1  # (c5) cards shaded with one normal for both faces (the shading notes); 0 = Blender's back-face flip (before c5)
SHADE = {"root": 0.35, "depth": 0.35, "value": 0.12}  # the notes' aux shade terms (shading.py)


def _math(nt, op, a, b=None, c=None):
    n = nt.nodes.new("ShaderNodeMath")
    n.operation = op
    for i, v in enumerate((a, b, c)):
        if v is None:
            continue
        if isinstance(v, (int, float)):
            n.inputs[i].default_value = float(v)
        else:
            nt.links.new(v, n.inputs[i])
    return n.outputs[0]


def _mul_rgb(nt, a, b):
    m = nt.nodes.new("ShaderNodeMix")
    m.data_type, m.blend_type = "RGBA", "MULTIPLY"
    m.inputs["Factor"].default_value = 1.0
    nt.links.new(a, m.inputs["A"])
    nt.links.new(b, m.inputs["B"])
    return m.outputs["Result"]


_FADE_DONE: list = []


def skin_fade(note_file, strength=1.0):
    """(sh7) hair_fade's map (<name>_hair_skin_fade.json beside the hair GLB) mixed into the base colour of every
    non-hair mesh: albedo = mix(albedo, fade.rgb, fade.a x strength) where the surface lies on the skull's own skin
    (|p - centre| < skull(u, v) + ear_clear: never on the ear standing off it). u = azimuth / 360 round the scalp
    centre (0 = front -Y, 90 = +X), v = elevation over the map's span: what an engine does with the same two maps
    (or bakes into the head's albedo). Hair objects (materials reading the GLB's own images) are left alone."""
    import json
    import math
    import os
    _FADE_DONE.append(note_file)
    note = json.loads(open(note_file).read())
    d = os.path.dirname(note_file)
    img = bpy.data.images.load(os.path.join(d, note["file"]))
    sk = bpy.data.images.load(os.path.join(d, note["skull"]))
    sk.colorspace_settings.name = "Non-Color"
    C = note["centre"]
    el0, el1 = note["el"]
    done = set()
    for ob in bpy.data.objects:
        if ob.type != "MESH" or ob.get("hp_shadow_proxy") or ob.get("hp_card"):
            continue
        mats = [ms.material for ms in ob.material_slots if ms.material is not None and ms.material.use_nodes]
        if any(n.type == "TEX_IMAGE" and n.image and os.path.dirname(bpy.path.abspath(n.image.filepath)) == d
               for m in mats for n in m.node_tree.nodes):
            continue  # the hair itself
        for m in mats:
            if m.name in done:
                continue
            done.add(m.name)
            nt = m.node_tree
            bsdf = next((n for n in nt.nodes if n.type == "BSDF_PRINCIPLED"), None)
            if bsdf is None:
                continue
            sock = bsdf.inputs["Base Color"]
            src = sock.links[0].from_socket if sock.links else None
            N = nt.nodes.new
            geo = N("ShaderNodeNewGeometry")
            q = N("ShaderNodeVectorMath"); q.operation = "SUBTRACT"
            q.inputs[1].default_value = C
            nt.links.new(geo.outputs["Position"], q.inputs[0])
            sx = N("ShaderNodeSeparateXYZ"); nt.links.new(q.outputs[0], sx.inputs[0])

            def M(op, a, b=None, c=None):
                n_ = N("ShaderNodeMath"); n_.operation = op
                for i_, v_ in enumerate((a, b, c)):
                    if v_ is None:
                        continue
                    if isinstance(v_, (int, float)):
                        n_.inputs[i_].default_value = float(v_)
                    else:
                        nt.links.new(v_, n_.inputs[i_])
                return n_.outputs[0]
            ny = M("MULTIPLY", sx.outputs["Y"], -1.0)
            u = M("FRACT", M("MULTIPLY", M("ARCTAN2", sx.outputs["X"], ny), 1.0 / (2 * math.pi)))
            ln = N("ShaderNodeVectorMath"); ln.operation = "LENGTH"; nt.links.new(q.outputs[0], ln.inputs[0])
            r = ln.outputs["Value"]
            el = M("ARCSINE", M("DIVIDE", sx.outputs["Z"], r))
            v = M("MULTIPLY_ADD", el, 180.0 / math.pi / (el1 - el0), -el0 / (el1 - el0))
            uv = N("ShaderNodeCombineXYZ"); nt.links.new(u, uv.inputs[0]); nt.links.new(v, uv.inputs[1])
            ti = N("ShaderNodeTexImage"); ti.image = img; ti.extension = "CLIP"; ti.interpolation = "Linear"
            nt.links.new(uv.outputs[0], ti.inputs[0])
            ts = N("ShaderNodeTexImage"); ts.image = sk; ts.extension = "EXTEND"; ts.interpolation = "Linear"
            nt.links.new(uv.outputs[0], ts.inputs[0])
            skull = M("MULTIPLY_ADD", ts.outputs["Color"], 65535.0 / float(note["skull_scale"]), float(note["ear_clear"]))
            on = M("LESS_THAN", r, skull)
            fac = M("MULTIPLY", M("MULTIPLY", ti.outputs["Alpha"], on), float(strength))
            mx = N("ShaderNodeMix"); mx.data_type = "RGBA"; mx.blend_type = "MIX"
            nt.links.new(fac, mx.inputs["Factor"])
            if src is not None:
                nt.links.new(src, mx.inputs[6])
            else:
                mx.inputs[6].default_value = sock.default_value
            nt.links.new(ti.outputs["Color"], mx.inputs[7])
            nt.links.new(mx.outputs[2], sock)
            print(f"@@skin_fade {ob.name} / {m.name}", flush=True)


def game_material(name, base_img, aux_img=None, color_attr=None, cutoff=0.33, params=None):
    """A hair-card material from the notes' formula. params: {"specular": level, "roughness", "sheen": [r, g, b]
    linear (the specular tint), "backscatter": 0..1 (a warm translucent term weighted to thin hair, aux.b high),
    "back_tint": [r, g, b], "wrap": w (default 0.45, the notes'; 0 = plain Lambert), "shadow_leak": share of the sun's
    diffuse that ignores the shadow map (default SHADOW_LEAK, the notes' 0.45)}."""
    p = params or {}
    if p.get("skin_fade") and not _FADE_DONE:  # (sh7) the hair export's edge fade laid on the head's skin, once per scene
        skin_fade(p["skin_fade"], float(p.get("skin_fade_strength", 1.0)))
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    pb = nt.nodes.new("ShaderNodeBsdfPrincipled")
    bc = nt.nodes.new("ShaderNodeTexImage")
    bc.image = base_img
    albedo = bc.outputs["Color"]
    if color_attr:
        va = nt.nodes.new("ShaderNodeVertexColor")
        va.layer_name = color_attr
        albedo = _mul_rgb(nt, albedo, va.outputs["Color"])
    shade_b = None
    if aux_img is not None and float(p.get("aux_shade", 0.0)) > 0:
        ax = nt.nodes.new("ShaderNodeTexImage")
        ax.image = aux_img
        ax.image.colorspace_settings.name = "Non-Color"
        sep = nt.nodes.new("ShaderNodeSeparateColor")
        nt.links.new(ax.outputs["Color"], sep.inputs["Color"])
        f1 = _math(nt, "MULTIPLY_ADD", sep.outputs["Red"], -SHADE["root"], 1.0)
        f2 = _math(nt, "MULTIPLY_ADD", sep.outputs["Blue"], SHADE["depth"], 1.0 - SHADE["depth"])
        f3 = _math(nt, "MULTIPLY_ADD", sep.outputs["Green"], 2 * SHADE["value"], 1.0 - SHADE["value"])
        g = _math(nt, "MULTIPLY", _math(nt, "MULTIPLY", f1, f2), f3)
        cg = nt.nodes.new("ShaderNodeCombineColor")
        for k in ("Red", "Green", "Blue"):
            nt.links.new(g, cg.inputs[k])
        albedo = _mul_rgb(nt, albedo, cg.outputs["Color"])
        shade_b = sep.outputs["Blue"]
    leak = float(p.get("shadow_leak", SHADOW_LEAK)) if float(p.get("wrap", WRAP)) > 0 and not p.get("flat") else 0.0
    # (the notes' "keep ~0.55 of the shadow map": sun diffuse = (1 - leak) x shadowed Lambert + leak x unshadowed, i.e.
    # Lambert x (leak + (1 - leak) x shadow). Nodes can't read one sun's shadow term, so Principled's diffuse is scaled
    # by 1 - leak and the leak is added unshadowed in the wrap's emission. Preview limit: the world's ambient diffuse
    # is scaled by 1 - leak too; an engine applies the leak to the sun's shadow term only.)
    nt.links.new(albedo if leak <= 0 else _mul_rgb(nt, albedo, _rgb(nt, [1.0 - leak] * 3)), pb.inputs["Base Color"])
    pb.inputs["Roughness"].default_value = float(p.get("roughness", 0.5))
    pb.inputs["Specular IOR Level"].default_value = float(p.get("specular", 0.25))
    if p.get("sheen"):
        pb.inputs["Specular Tint"].default_value = (*[float(c) for c in p["sheen"]], 1.0)
    gl = p.get("gltf") if GLTF_SPEC and not p.get("plain_spec") else None
    if gl:  # (c6) the GLB's own highlight, as an engine reads it: KHR_materials_specular (factor 1 = Blender's IOR level
        # 0.5), its colour, the ORM roughness (G), KHR_materials_anisotropy (strength x flow.B along the flow's RG direction
        # in tangent space; else rotated by anisotropyRotation from the uv tangent). Before c6 a flat 0.25 isotropic, rough .5
        if "spec" in gl and "specular" not in p:
            pb.inputs["Specular IOR Level"].default_value = 0.5 * float(gl["spec"])
        if gl.get("spec_color") and not p.get("sheen"):
            pb.inputs["Specular Tint"].default_value = (*[float(c) for c in gl["spec_color"]], 1.0)
        if gl.get("orm") and "roughness" not in p:
            ti = nt.nodes.new("ShaderNodeTexImage")
            ti.image = bpy.data.images.load(gl["orm"], check_existing=True)
            ti.image.colorspace_settings.name = "Non-Color"
            sp_ = nt.nodes.new("ShaderNodeSeparateColor")
            nt.links.new(ti.outputs["Color"], sp_.inputs["Color"])
            nt.links.new(_math(nt, "MULTIPLY", sp_.outputs["Green"], float(gl.get("rough", 1.0))), pb.inputs["Roughness"])
        if float(gl.get("aniso", 0)) > 0:
            tg = nt.nodes.new("ShaderNodeTangent")
            tg.direction_type = "UV_MAP"
            if gl.get("uv"):
                tg.uv_map = gl["uv"]
            g2 = nt.nodes.new("ShaderNodeNewGeometry")
            bt = nt.nodes.new("ShaderNodeVectorMath")
            bt.operation = "CROSS_PRODUCT"
            nt.links.new(g2.outputs["Normal"], bt.inputs[0])
            nt.links.new(tg.outputs["Tangent"], bt.inputs[1])
            if gl.get("flow"):
                fi = nt.nodes.new("ShaderNodeTexImage")
                fi.image = bpy.data.images.load(gl["flow"], check_existing=True)
                fi.image.colorspace_settings.name = "Non-Color"
                fs = nt.nodes.new("ShaderNodeSeparateColor")
                nt.links.new(fi.outputs["Color"], fs.inputs["Color"])
                a_ = _math(nt, "MULTIPLY_ADD", fs.outputs["Red"], 2.0, -1.0)
                b_ = _math(nt, "MULTIPLY_ADD", fs.outputs["Green"], 2.0, -1.0)
                strength = _math(nt, "MULTIPLY", fs.outputs["Blue"], float(gl["aniso"]))
            else:
                import math
                r_ = float(gl.get("aniso_rot", 0.0))
                a_, b_, strength = math.cos(r_), math.sin(r_), float(gl["aniso"])
            v1 = nt.nodes.new("ShaderNodeVectorMath")
            v1.operation = "SCALE"
            nt.links.new(tg.outputs["Tangent"], v1.inputs[0])
            v2 = nt.nodes.new("ShaderNodeVectorMath")
            v2.operation = "SCALE"
            nt.links.new(bt.outputs["Vector"], v2.inputs[0])
            for v_, f_ in ((v1, a_), (v2, b_)):
                if isinstance(f_, float):
                    v_.inputs["Scale"].default_value = f_
                else:
                    nt.links.new(f_, v_.inputs["Scale"])
            ad_ = nt.nodes.new("ShaderNodeVectorMath")
            ad_.operation = "ADD"
            nt.links.new(v1.outputs["Vector"], ad_.inputs[0])
            nt.links.new(v2.outputs["Vector"], ad_.inputs[1])
            nz = nt.nodes.new("ShaderNodeVectorMath")
            nz.operation = "NORMALIZE"
            nt.links.new(ad_.outputs["Vector"], nz.inputs[0])
            nt.links.new(nz.outputs["Vector"], pb.inputs["Tangent"])
            if isinstance(strength, float):
                pb.inputs["Anisotropic"].default_value = strength
            else:
                nt.links.new(strength, pb.inputs["Anisotropic"])
    one_n = None
    if ONE_NORMAL and not p.get("flip_back"):  # (c5) the shading notes: "two-sided with ONE normal for both faces". Blender
        # flips the shading normal on a face seen from behind: a card seen past its edge at the outline (the back crown's
        # top cards, lying on the head and seen from below their plane) was shaded with a normal pointing INTO the head:
        # unlit, the black crown "shards" (c4: not winding, proxy, shadows or the atlas; the flat pass had none)
        g1 = nt.nodes.new("ShaderNodeNewGeometry")
        sg = _math(nt, "MULTIPLY_ADD", g1.outputs["Backfacing"], -2.0, 1.0)
        sc_ = nt.nodes.new("ShaderNodeVectorMath")
        sc_.operation = "SCALE"
        nt.links.new(g1.outputs["Normal"], sc_.inputs[0])
        nt.links.new(sg, sc_.inputs["Scale"])
        one_n = sc_.outputs["Vector"]
        nt.links.new(one_n, pb.inputs["Normal"])
    surf = pb.outputs["BSDF"]
    bs = float(p.get("backscatter", 0.0))
    if bs > 0:  # light through thin hair: a translucent term in the hair's colour, warmer, weighted to the outer layers
        tr = nt.nodes.new("ShaderNodeBsdfTranslucent")
        tint = _mul_rgb(nt, albedo, _rgb(nt, p.get("back_tint", [1.25, 1.0, 0.8])))
        nt.links.new(tint, tr.inputs["Color"])
        if one_n is not None:  # (light through the card from behind: the far side of the one normal)
            nt.links.new(one_n, tr.inputs["Normal"])
        mix = nt.nodes.new("ShaderNodeMixShader")
        w = _math(nt, "MULTIPLY", shade_b, bs * 0.5) if shade_b is not None else None
        if w is None:
            mix.inputs[0].default_value = bs * 0.3
        else:
            nt.links.new(w, mix.inputs[0])
        nt.links.new(surf, mix.inputs[1])
        nt.links.new(tr.outputs["BSDF"], mix.inputs[2])
        surf = mix.outputs["Shader"]
    wrap = float(p.get("wrap", WRAP))
    if wrap > 0 and not p.get("flat"):  # the notes' wrapped diffuse: the part of the wrap past Lambert, per sun
        geo = nt.nodes.new("ShaderNodeNewGeometry")
        lift = None
        for i in range(MAX_SUNS):
            dn = nt.nodes.new("ShaderNodeCombineXYZ")
            dn.name = f"hp_wrap_dir{i}"
            cn = nt.nodes.new("ShaderNodeRGB")
            cn.name = f"hp_wrap_col{i}"
            cn.outputs[0].default_value = (0.0, 0.0, 0.0, 1.0)
            dot = nt.nodes.new("ShaderNodeVectorMath")
            dot.operation = "DOT_PRODUCT"
            nt.links.new(one_n if one_n is not None else geo.outputs["Normal"], dot.inputs[0])
            nt.links.new(dn.outputs["Vector"], dot.inputs[1])
            d = dot.outputs["Value"]
            wv = _math(nt, "MAXIMUM", _math(nt, "MULTIPLY_ADD", d, 1.0 / (1.0 + wrap), wrap / (1.0 + wrap)), 0.0)
            lv = _math(nt, "SUBTRACT", wv, _math(nt, "MAXIMUM", d, 0.0) if leak <= 0 else
                       _math(nt, "MULTIPLY", _math(nt, "MAXIMUM", d, 0.0), 1.0 - leak))
            term = _mul_rgb(nt, cn.outputs[0], _gray(nt, lv))
            if lift is None:
                lift = term
            else:
                ad = nt.nodes.new("ShaderNodeMix")
                ad.data_type, ad.blend_type = "RGBA", "ADD"
                ad.inputs["Factor"].default_value = 1.0
                nt.links.new(lift, ad.inputs["A"])
                nt.links.new(term, ad.inputs["B"])
                lift = ad.outputs["Result"]
        em = nt.nodes.new("ShaderNodeEmission")
        nt.links.new(_mul_rgb(nt, albedo, lift), em.inputs["Color"])
        add = nt.nodes.new("ShaderNodeAddShader")
        nt.links.new(surf, add.inputs[0])
        nt.links.new(em.outputs["Emission"], add.inputs[1])
        surf = add.outputs["Shader"]
        mat["hp_wrap"] = wrap
    if p.get("flat"):  # a flat pass: the albedo unlit, same coverage (is a dark patch the picture or the light?)
        em = nt.nodes.new("ShaderNodeEmission")
        nt.links.new(albedo, em.inputs["Color"])
        surf = em.outputs["Emission"]
    cut = _math(nt, "GREATER_THAN", bc.outputs["Alpha"], float(cutoff))
    mip = int(p.get("shadow_mip", SHADOW_MIP))
    if mip > 1 and base_img is not None and not p.get("flat"):  # the shadow reads a coarse mip of the cut's coverage
        sh = nt.nodes.new("ShaderNodeTexImage")
        sh.image = _shadow_alpha(base_img, float(cutoff), mip)
        sh.image.colorspace_settings.name = "Non-Color"
        sh.interpolation = "Linear"
        lp = nt.nodes.new("ShaderNodeLightPath")
        mixf = nt.nodes.new("ShaderNodeMix")
        mixf.data_type = "FLOAT"
        nt.links.new(lp.outputs["Is Shadow Ray"], mixf.inputs["Factor"])
        nt.links.new(cut, mixf.inputs["A"])
        nt.links.new(sh.outputs["Color"], mixf.inputs["B"])
        cut = mixf.outputs["Result"]
        if hasattr(mat, "use_transparent_shadow"):
            mat.use_transparent_shadow = True
    tp = nt.nodes.new("ShaderNodeBsdfTransparent")
    mx = nt.nodes.new("ShaderNodeMixShader")
    nt.links.new(cut, mx.inputs[0])
    nt.links.new(tp.outputs["BSDF"], mx.inputs[1])
    nt.links.new(surf, mx.inputs[2])
    nt.links.new(mx.outputs["Shader"], out.inputs["Surface"])
    mat.use_backface_culling = bool(p.get("cull"))  # (c6) the GLB's doubleSided false: cards carry their own back faces
    if hasattr(mat, "use_backface_culling_shadow"):  # (shadows from both faces as before)
        mat.use_backface_culling_shadow = False
    if hasattr(mat, "surface_render_method"):
        mat.surface_render_method = "DITHERED"
    return mat


WRAP = 0.45     # shading.py hair_cards "diffuse: wrapped"
SHADOW_MIP = 16  # the cards' shadow reads their cut coverage (alpha > cutoff) box-averaged over this many texels (a
# coarse mip, ~mip 4): engines don't cast hair-card shadows from the full-res alpha (shadow maps sample a coarser mip or a
# dedicated shadow alpha), so a card shadow is soft, not grain. Full res (1) drew the neck speckle (b25: skin grain 0.42 vs
# the groom's 0.31, L* 61 vs 66). 1 = the cut alpha (before round 18).
_SHADOW_ALPHA = {}


def _shadow_alpha(img, cutoff: float, f: int):
    """A float image 1/f the size of `img`: the share of each f x f block whose alpha passes `cutoff` (the shadow's
    coverage, read with linear filtering)."""
    import numpy as np
    key = (img.name, round(cutoff, 4), f)
    if key in _SHADOW_ALPHA and _SHADOW_ALPHA[key].name in bpy.data.images:
        return _SHADOW_ALPHA[key]
    w, h = img.size
    px = np.empty(w * h * 4, np.float32)
    img.pixels.foreach_get(px)
    a = (px[3::4].reshape(h, w) > cutoff).astype(np.float32)
    hh, ww = h // f, w // f
    c = a[:hh * f, :ww * f].reshape(hh, f, ww, f).mean(axis=(1, 3))
    out = bpy.data.images.new(f"{img.name}_shadow{f}", ww, hh, alpha=False, float_buffer=True)
    rgba = np.repeat(c.reshape(-1, 1), 4, axis=1)
    rgba[:, 3] = 1.0
    out.pixels.foreach_set(rgba.ravel())
    out.pack()
    _SHADOW_ALPHA[key] = out
    return out
def shadow_proxy(path, cards=()):
    """The hair's shadow caster (shading.py hair_cards "shadows"): the export's `<glb stem>_shadow.obj` imported as an
    opaque mesh that casts shadows only (hidden from the camera and from every other ray), and the cards cast none.
    Returns the proxy object (None when the file is missing)."""
    import os
    if not path or not os.path.exists(path):
        return None
    before = set(bpy.data.objects)
    bpy.ops.wm.obj_import(filepath=str(path), forward_axis="NEGATIVE_Z", up_axis="Y")
    new = [o for o in bpy.data.objects if o not in before and o.type == "MESH"]
    if not new:
        return None
    ob = new[0]
    ob["hp_shadow_proxy"] = True
    m = bpy.data.materials.get("hp_shadow_proxy") or bpy.data.materials.new("hp_shadow_proxy")
    ob.data.materials.clear()
    ob.data.materials.append(m)
    for k in ("visible_camera", "visible_diffuse", "visible_glossy", "visible_transmission", "visible_volume_scatter"):
        if hasattr(ob, k):
            setattr(ob, k, False)
    ob.visible_shadow = True
    for c in cards:
        c.visible_shadow = False
    return ob


SHADOW_LEAK = 0.45  # shading.py hair_cards: "keep ~0.55 of the shadow map" (default from b22, 2026-10-16)
MAX_SUNS = 4


def _gray(nt, v):
    cc = nt.nodes.new("ShaderNodeCombineColor")
    for k in ("Red", "Green", "Blue"):
        nt.links.new(v, cc.inputs[k])
    return cc.outputs["Color"]


def set_wrap_lights():
    """Copy the scene's suns (hp_sun*: direction toward the light, colour x energy x diffuse factor / pi = the
    irradiance a white Lambert surface turns into radiance) into every wrap material. Call before each frame: views
    re-aim and re-weight the suns."""
    import math
    suns = [ob for ob in bpy.data.objects if ob.type == "LIGHT" and ob.data.type == "SUN" and not ob.hide_render]
    suns.sort(key=lambda o: o.name)
    for m in bpy.data.materials:
        if m.get("hp_wrap") is None or not m.node_tree:
            continue
        for i in range(MAX_SUNS):
            dn, cn = m.node_tree.nodes.get(f"hp_wrap_dir{i}"), m.node_tree.nodes.get(f"hp_wrap_col{i}")
            if dn is None or cn is None:
                continue
            if i < len(suns):
                ob = suns[i]
                z = ob.matrix_world.to_3x3().col[2].normalized()
                k = ob.data.energy * getattr(ob.data, "diffuse_factor", 1.0) / math.pi
                for j, a in enumerate("XYZ"):
                    dn.inputs[a].default_value = z[j]
                cn.outputs[0].default_value = (*[c * k for c in ob.data.color], 1.0)
            else:
                cn.outputs[0].default_value = (0.0, 0.0, 0.0, 1.0)


def _rgb(nt, c):
    n = nt.nodes.new("ShaderNodeRGB")
    n.outputs[0].default_value = (*[float(x) for x in c], 1.0)
    return n.outputs[0]


def id_material(base_img, cutoff=0.33):
    """Flat red where a card's alpha passes the cutoff (the hair mask of the id pass), transparent elsewhere."""
    mat = bpy.data.materials.new("hp_id_card")
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    e = nt.nodes.new("ShaderNodeEmission")
    e.inputs["Color"].default_value = (1, 0, 0, 1)
    bc = nt.nodes.new("ShaderNodeTexImage")
    bc.image = base_img
    cut = _math(nt, "GREATER_THAN", bc.outputs["Alpha"], float(cutoff))
    tp = nt.nodes.new("ShaderNodeBsdfTransparent")
    mx = nt.nodes.new("ShaderNodeMixShader")
    nt.links.new(cut, mx.inputs[0])
    nt.links.new(tp.outputs["BSDF"], mx.inputs[1])
    nt.links.new(e.outputs[0], mx.inputs[2])
    nt.links.new(mx.outputs["Shader"], out.inputs["Surface"])
    mat.use_backface_culling = False
    if hasattr(mat, "surface_render_method"):
        mat.surface_render_method = "DITHERED"
    return mat
