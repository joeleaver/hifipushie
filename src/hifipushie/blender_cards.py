"""Hair cards drawn as a game draws them (inside Blender, EEVEE without ray tracing): the material is the export's
shading notes in nodes (shading.py "hair_cards"), so judging a card export judges what an engine is told to do.

    albedo = basecolor.rgb * COLOR_0.rgb * (1 - 0.35 aux.r) * lerp(0.65, 1, aux.b) * (1 + 0.12 (2 aux.g - 1))
    coverage = basecolor.a > cutoff (dithered: TAA / alpha-to-coverage resolve it), two-sided, one normal
    specular: tinted, half strength (a card is many round hairs, not a mirror), roughness 0.5

`game_material` is shared by blender_scene.hair_glb_look ("game" alpha) and can serve blender_game."""
import bpy

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


def game_material(name, base_img, aux_img=None, color_attr=None, cutoff=0.33, params=None):
    """A hair-card material from the notes' formula. params: {"specular": level, "roughness", "sheen": [r, g, b]
    linear (the specular tint), "backscatter": 0..1 (a warm translucent term weighted to thin hair, aux.b high),
    "back_tint": [r, g, b]}."""
    p = params or {}
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
    nt.links.new(albedo, pb.inputs["Base Color"])
    pb.inputs["Roughness"].default_value = float(p.get("roughness", 0.5))
    pb.inputs["Specular IOR Level"].default_value = float(p.get("specular", 0.25))
    if p.get("sheen"):
        pb.inputs["Specular Tint"].default_value = (*[float(c) for c in p["sheen"]], 1.0)
    surf = pb.outputs["BSDF"]
    bs = float(p.get("backscatter", 0.0))
    if bs > 0:  # light through thin hair: a translucent term in the hair's colour, warmer, weighted to the outer layers
        tr = nt.nodes.new("ShaderNodeBsdfTranslucent")
        tint = _mul_rgb(nt, albedo, _rgb(nt, p.get("back_tint", [1.25, 1.0, 0.8])))
        nt.links.new(tint, tr.inputs["Color"])
        mix = nt.nodes.new("ShaderNodeMixShader")
        w = _math(nt, "MULTIPLY", shade_b, bs * 0.5) if shade_b is not None else None
        if w is None:
            mix.inputs[0].default_value = bs * 0.3
        else:
            nt.links.new(w, mix.inputs[0])
        nt.links.new(surf, mix.inputs[1])
        nt.links.new(tr.outputs["BSDF"], mix.inputs[2])
        surf = mix.outputs["Shader"]
    cut = _math(nt, "GREATER_THAN", bc.outputs["Alpha"], float(cutoff))
    tp = nt.nodes.new("ShaderNodeBsdfTransparent")
    mx = nt.nodes.new("ShaderNodeMixShader")
    nt.links.new(cut, mx.inputs[0])
    nt.links.new(tp.outputs["BSDF"], mx.inputs[1])
    nt.links.new(surf, mx.inputs[2])
    nt.links.new(mx.outputs["Shader"], out.inputs["Surface"])
    mat.use_backface_culling = False
    if hasattr(mat, "surface_render_method"):
        mat.surface_render_method = "DITHERED"
    return mat


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
