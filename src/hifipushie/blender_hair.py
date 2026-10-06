"""Hair locks inside Blender (imported by blender_scene.py; runs in Blender's Python).

Every lock is a legacy Bezier curve object in the "hair" collection: the control points are the lock's spine (what a
person grabs, G/R/S in edit mode, Alt+S radius, Ctrl+T tilt all work), and a Geometry Nodes modifier ("hp_lock", one
shared node group) turns the spine into the lock's mesh live: resampled, its flat side turned to face away from the
head's centre (+ a twist root to tip), swept with a lens profile (width x thickness, the edges cupped toward the head),
scaled along its length (a root that swells out of the scalp, a belly, a taper to a point). The modifier's inputs are
the lock's numbers (Width, Thickness, Cup, Taper, Belly, Twist...): a person can change those in the modifier panel and
pull takes them back to the spec like the control points.

The mesh carries attributes for the material and the export: hp_along (0 root .. 1 tip), hp_across (-1..1 over the
width), hp_out (profile height: +1 the outer face, -1 the face on the head), hp_lock (0..1 per lock), hp_grey,
hp_tangent (the spine's direction).
"""

import bpy
import numpy as np

GROUP = "hp_lock"
VERSION = 11  # bump when the node group changes: scenes rebuild it
INPUTS = [  # (name, type, default, min, max) in modifier order; the spec's lock keys are these, lower case
    ("Width", "NodeSocketFloat", 0.03, 0.0, 1.0),
    ("Thickness", "NodeSocketFloat", 0.008, 0.0, 1.0),
    ("Cup", "NodeSocketFloat", 0.002, -0.1, 0.1),
    ("Taper", "NodeSocketFloat", 1.0, 0.0, 1.0),
    ("Belly", "NodeSocketFloat", 0.3, 0.0, 1.0),
    ("Root", "NodeSocketFloat", 0.6, 0.0, 1.0),
    ("Twist", "NodeSocketFloat", 0.0, -720.0, 720.0),
    ("Flip", "NodeSocketFloat", 0.0, -180.0, 180.0),
    ("Edge", "NodeSocketFloat", 0.8, 0.2, 4.0),
    ("Grey", "NodeSocketFloat", 0.0, 0.0, 1.0),
    ("Seed", "NodeSocketFloat", 0.0, 0.0, 1.0),
    ("Free", "NodeSocketFloat", 0.0, 0.0, 1.0),
    ("Centre", "NodeSocketVector", (0.0, 0.0, 0.0), None, None),
    ("Segments", "NodeSocketInt", 32, 2, 256),
    ("Sides", "NodeSocketInt", 16, 3, 64),
]
KEYS = {n.lower(): n for n, *_ in INPUTS if n not in ("Centre", "Segments", "Sides", "Seed", "Grey")}


def _math(nt, op, a, b=None, c=None):
    n = nt.nodes.new("ShaderNodeMath")
    n.operation = op
    for i, v in enumerate((a, b, c)):
        if v is None:
            continue
        if isinstance(v, (int, float)):
            n.inputs[i].default_value = v
        else:
            nt.links.new(v, n.inputs[i])
    return n.outputs[0]


def _vmath(nt, op, a, b=None, scale=None):
    n = nt.nodes.new("ShaderNodeVectorMath")
    n.operation = op
    for i, v in enumerate((a, b)):
        if v is None:
            continue
        if isinstance(v, (tuple, list)):
            n.inputs[i].default_value = v
        else:
            nt.links.new(v, n.inputs[i])
    if scale is not None:
        if isinstance(scale, (int, float)):
            n.inputs["Scale"].default_value = scale
        else:
            nt.links.new(scale, n.inputs["Scale"])
    return n.outputs["Value" if op in ("DOT_PRODUCT", "LENGTH", "DISTANCE") else "Vector"]


def _sep(nt, v):
    n = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(v, n.inputs[0])
    return n.outputs


def _comb(nt, x, y, z):
    n = nt.nodes.new("ShaderNodeCombineXYZ")
    for i, v in enumerate((x, y, z)):
        if isinstance(v, (int, float)):
            n.inputs[i].default_value = v
        else:
            nt.links.new(v, n.inputs[i])
    return n.outputs[0]


def _smooth(nt, x, lo, hi):
    n = nt.nodes.new("ShaderNodeMapRange")
    n.interpolation_type = "SMOOTHSTEP"
    nt.links.new(x, n.inputs["Value"])
    for k, v in (("From Min", lo), ("From Max", hi)):
        if isinstance(v, (int, float)):
            n.inputs[k].default_value = v
        else:
            nt.links.new(v, n.inputs[k])
    return n.outputs["Result"]


def _store(nt, geo, name, value, dtype="FLOAT", domain="POINT"):
    n = nt.nodes.new("GeometryNodeStoreNamedAttribute")
    n.data_type, n.domain = dtype, domain
    nt.links.new(geo, n.inputs["Geometry"])
    n.inputs["Name"].default_value = name
    if isinstance(value, (int, float)):
        n.inputs["Value"].default_value = value
    else:
        nt.links.new(value, n.inputs["Value"])
    return n.outputs["Geometry"]


def _capture(nt, geo, value, dtype="FLOAT"):
    n = nt.nodes.new("GeometryNodeCaptureAttribute")
    n.domain = "POINT"
    n.capture_items.new(dtype, "v")
    nt.links.new(geo, n.inputs[0])
    nt.links.new(value, n.inputs[1])
    return n.outputs[0], n.outputs[1]


def node_group():
    """The shared lock node group (rebuilt when VERSION moves)."""
    ng = bpy.data.node_groups.get(GROUP)
    if ng is not None and ng.get("hp_version") == VERSION:
        return ng
    kept = {}
    if ng is None:
        ng = bpy.data.node_groups.new(GROUP, "GeometryNodeTree")
    else:  # a rebuild re-creates the input sockets (new identifiers): every lock's modifier values would fall back to
        # the defaults (width 0), which the next pull read as the person's edits and wrote into the spec
        for ob in bpy.data.objects:
            for mod in ob.modifiers:
                if mod.type == "NODES" and mod.node_group == ng:
                    kept[(ob.name, mod.name)] = get_inputs(mod)
    ng.nodes.clear()
    ng.interface.clear()
    ng.interface.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    ng.interface.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    for name, typ, d, lo, hi in INPUTS:
        s = ng.interface.new_socket(name, in_out="INPUT", socket_type=typ)
        s.default_value = d
        if lo is not None:
            s.min_value, s.max_value = lo, hi
    ng["hp_version"] = VERSION
    nt = ng
    gi = nt.nodes.new("NodeGroupInput")
    go = nt.nodes.new("NodeGroupOutput")
    I = gi.outputs  # noqa: E741

    res = nt.nodes.new("GeometryNodeResampleCurve")
    nt.links.new(I["Geometry"], res.inputs["Curve"])
    nt.links.new(I["Segments"], res.inputs["Count"])
    curve = res.outputs[0]

    # the flat side faces away from the head's centre (orthogonal to the spine), turned by Flip + Twist x along
    pos = nt.nodes.new("GeometryNodeInputPosition").outputs[0]
    tan = nt.nodes.new("GeometryNodeInputTangent").outputs[0]
    par = nt.nodes.new("GeometryNodeSplineParameter").outputs["Factor"]
    out = _vmath(nt, "NORMALIZE", _vmath(nt, "SUBTRACT", pos, I["Centre"]))
    d = _vmath(nt, "DOT_PRODUCT", out, tan)
    n0 = _vmath(nt, "NORMALIZE", _vmath(nt, "SUBTRACT", out, _vmath(nt, "SCALE", tan, scale=d)))
    rot = nt.nodes.new("ShaderNodeVectorRotate")
    rot.rotation_type = "AXIS_ANGLE"
    nt.links.new(n0, rot.inputs["Vector"])
    nt.links.new(tan, rot.inputs["Axis"])
    ang = _math(nt, "RADIANS", _math(nt, "ADD", I["Flip"], _math(nt, "MULTIPLY", I["Twist"], par)))
    nt.links.new(ang, rot.inputs["Angle"])
    sn = nt.nodes.new("GeometryNodeSetCurveNormal")
    nt.links.new(curve, sn.inputs["Curve"])
    sn.inputs["Mode"].default_value = "Free"
    nt.links.new(rot.outputs[0], sn.inputs["Normal"])
    curve = sn.outputs[0]

    curve, along = _capture(nt, curve, par)
    curve, tangent = _capture(nt, curve, tan, "VECTOR")

    # width along the lock: swells out of the scalp (Root: the width there), the widest at Belly, to a point at the tip
    # (Taper: 1 a point, 0 no taper)
    rise = _math(nt, "ADD", I["Root"], _math(nt, "MULTIPLY", _math(nt, "SUBTRACT", 1.0, I["Root"]),
                                             _smooth(nt, along, 0.0, _math(nt, "MAXIMUM", I["Belly"], 0.02))))
    fall = _smooth(nt, along, I["Belly"], 1.0)
    tipw = _math(nt, "SUBTRACT", 1.0, _math(nt, "MULTIPLY", I["Taper"], _math(nt, "POWER", fall, 0.8)))
    radius = nt.nodes.new("GeometryNodeInputRadius").outputs[0]
    scale = _math(nt, "MULTIPLY", _math(nt, "MULTIPLY", rise, tipw), radius)

    # the profile: a lens (width x thickness), its edges cupped toward the head
    circ = nt.nodes.new("GeometryNodeCurvePrimitiveCircle")
    circ.mode = "RADIUS"
    nt.links.new(I["Sides"], circ.inputs["Resolution"])
    circ.inputs["Radius"].default_value = 1.0
    ppos = _sep(nt, nt.nodes.new("GeometryNodeInputPosition").outputs[0])
    # a lens, not an ellipse: the sides come to soft edges (|sin| ^ 0.7 fattens the middle, thins the edges)
    s_abs = _math(nt, "POWER", _math(nt, "ABSOLUTE", ppos[1]), I["Edge"])  # Edge > 1: thin crisp edges, a flat back
    sy = _math(nt, "MULTIPLY", _math(nt, "SIGN", ppos[1]), s_abs)
    across = ppos[0]
    y = _math(nt, "SUBTRACT", _math(nt, "MULTIPLY", sy, _math(nt, "MULTIPLY", I["Thickness"], 0.5)),
              _math(nt, "MULTIPLY", I["Cup"], _math(nt, "MULTIPLY", across, across)))
    x = _math(nt, "MULTIPLY", across, _math(nt, "MULTIPLY", I["Width"], 0.5))
    # captured on the unit circle, before it's scaled (captured after, "across" was +-W/2: +-2 mm, and the material's
    # gaps, sheen band and grooves never showed)
    prof, pacross = _capture(nt, circ.outputs["Curve"], across)
    prof, pout = _capture(nt, prof, sy)
    sp = nt.nodes.new("GeometryNodeSetPosition")
    nt.links.new(prof, sp.inputs["Geometry"])
    nt.links.new(_comb(nt, y, x, 0.0), sp.inputs["Position"])  # profile x runs along the curve normal
    prof = sp.outputs[0]

    c2m = nt.nodes.new("GeometryNodeCurveToMesh")
    nt.links.new(curve, c2m.inputs["Curve"])
    nt.links.new(prof, c2m.inputs["Profile Curve"])
    nt.links.new(scale, c2m.inputs["Scale"])
    c2m.inputs["Fill Caps"].default_value = True
    # the profile is the unit circle with x and y swapped (a mirror), so Curve to Mesh winds every face inward: flip
    # them. Inward faces rendered fine where nothing culls back faces (Cycles, the scene), but the glTF importer and
    # engines cull them on a single-sided material: EEVEE then drew each lens's dark underside, near-black hair
    flip = nt.nodes.new("GeometryNodeFlipFaces")
    nt.links.new(c2m.outputs[0], flip.inputs["Mesh"])
    geo = flip.outputs[0]
    geo = _store(nt, geo, "hp_along", along)
    geo = _store(nt, geo, "hp_across", pacross)
    geo = _store(nt, geo, "hp_out", pout)
    geo = _store(nt, geo, "hp_tangent", tangent, "FLOAT_VECTOR")
    geo = _store(nt, geo, "hp_lock", I["Seed"])
    geo = _store(nt, geo, "hp_grey", I["Grey"])
    geo = _store(nt, geo, "hp_free", I["Free"])
    sm = nt.nodes.new("GeometryNodeSetShadeSmooth")
    nt.links.new(geo, sm.inputs["Geometry"])
    mat = nt.nodes.new("GeometryNodeSetMaterial")
    nt.links.new(sm.outputs[0], mat.inputs["Geometry"])
    mat.inputs["Material"].default_value = bpy.data.materials.get("hp_hair") or bpy.data.materials.new("hp_hair")
    nt.links.new(mat.outputs[0], go.inputs[0])
    for (on, mn), vals in kept.items():
        ob = bpy.data.objects.get(on)
        if ob is not None and ob.modifiers.get(mn) is not None:
            _set_inputs(ob.modifiers[mn], vals)
            ob.update_tag()
    return ng


def _hex(c):
    c = c.lstrip("#")
    s = [int(c[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    return [x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in s] + [1.0]


def material(look: dict):
    """The hair material: dark in the gaps between locks and underneath, the lit colour on top, a broad warm sheen
    along each lock's crown, grey where hp_grey says, fine strand grooves as bump (baked into the export's normal
    map). look: {"gap", "lit", "sheen", "grey", "roughness", "grooves", "groove_depth"}."""
    m = bpy.data.materials.get("hp_hair") or bpy.data.materials.new("hp_hair")
    key = repr(sorted(look.items())) + " v2"
    if m.get("hp_look") == key and m.node_tree and len(m.node_tree.nodes) > 3:
        return m
    m["hp_look"] = key
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    nt.links.new(bsdf.outputs[0], out.inputs["Surface"])

    def attr(name, kind="Fac"):
        a = nt.nodes.new("ShaderNodeAttribute")
        a.attribute_name = name
        return a.outputs["Vector" if kind == "Vector" else "Fac"]

    along, across, outf, lock, grey = (attr(n) for n in ("hp_along", "hp_across", "hp_out", "hp_lock", "hp_grey"))
    tangent = attr("hp_tangent", "Vector")

    def rgb(c):
        n = nt.nodes.new("ShaderNodeRGB")
        n.outputs[0].default_value = _hex(c)
        return n.outputs[0]

    def mix(a, b, f):
        n = nt.nodes.new("ShaderNodeMix")
        n.data_type = "RGBA"
        for k, v in (("A", a), ("B", b)):
            nt.links.new(v, n.inputs[k])
        if isinstance(f, (int, float)):
            n.inputs["Factor"].default_value = f
        else:
            nt.links.new(f, n.inputs["Factor"])
        return n.outputs["Result"]

    # how exposed a point of a lock is: the outer face's crown (1) down to its edges and the face on the head (0),
    # the root in the scalp dark too
    edge = _smooth(nt, _math(nt, "ABSOLUTE", across), float(look.get("edge", 0.55)), 1.0)
    top = _smooth(nt, outf, -0.6, 0.4)
    # a lock hanging clear of the head (hp_free, a tail) is hair on its underside too: only locks lying on the head
    # have a gap side (seen from the head's side, a free tail was near black)
    top = _math(nt, "MAXIMUM", top, _math(nt, "MULTIPLY", attr("hp_free"), 0.85))
    root = _smooth(nt, along, 0.0, float(look.get("root", 0.12)))
    expo = _math(nt, "MULTIPLY", _math(nt, "MULTIPLY", _math(nt, "SUBTRACT", 1.0, edge), top), root)
    col = mix(rgb(look.get("gap", "#2a1712")), rgb(look.get("lit", "#6b3d2e")), expo)
    # a little per-lock variation (contrast between locks, not within them)
    var = _math(nt, "MULTIPLY", _math(nt, "SUBTRACT", lock, 0.5), float(look.get("vary", 0.25)))
    hsv = nt.nodes.new("ShaderNodeHueSaturation")
    nt.links.new(col, hsv.inputs["Color"])
    nt.links.new(_math(nt, "ADD", 1.0, var), hsv.inputs["Value"])
    col = hsv.outputs[0]
    # the sheen: a broad warm band along each lock's crown
    # (each lock's band slides along it by its own amount: bands at the same place on every lock line up into one
    # stripe across the head, the thing artists break up first)
    sh = _math(nt, "ADD", along, _math(nt, "MULTIPLY", _math(nt, "SUBTRACT", lock, 0.5),
                                       float(look.get("band_shift", 0.25))))
    band = _math(nt, "MULTIPLY", _smooth(nt, _math(nt, "SUBTRACT", 0.0, _math(nt, "ABSOLUTE", across)), -0.75, -0.1),
                 _math(nt, "MULTIPLY", top, _smooth(nt, sh, 0.1, 0.35)))
    band = _math(nt, "MULTIPLY", band, _math(nt, "SUBTRACT", 1.0, _smooth(nt, sh, 0.7, 1.0)))
    col = mix(col, rgb(look.get("sheen", "#9a6048")), _math(nt, "MULTIPLY", band, float(look.get("sheen_amount", 0.45))))
    col = mix(col, rgb(look.get("grey", "#9a948d")), _math(nt, "MULTIPLY", _math(nt, "MULTIPLY", grey, 0.7), expo))
    if float(look.get("tip_amount", 0.0)) > 0:  # tips a shade lighter/warmer (sun-bleached ends)
        col = mix(col, rgb(look.get("tip", "#7a5038")),
                  _math(nt, "MULTIPLY", _smooth(nt, along, 0.55, 1.0), float(look["tip_amount"])))
    nt.links.new(col, bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = float(look.get("roughness", 0.42))
    bsdf.inputs["Specular IOR Level"].default_value = float(look.get("specular", 0.5))
    bsdf.inputs["Anisotropic"].default_value = float(look.get("anisotropic", 0.7))
    nt.links.new(tangent, bsdf.inputs["Tangent"])
    # strand grooves: fine parallel ridges across the width (bump only)
    g = float(look.get("grooves", 9))
    if g > 0:
        # uneven spacing per lock (a warp of the across coordinate seeded by the lock) and softened: evenly spaced
        # sharp ridges read as corduroy
        warp = _math(nt, "ADD", across, _math(nt, "MULTIPLY", 0.18, _math(nt, "SINE", _math(
            nt, "ADD", _math(nt, "MULTIPLY", across, 2.3), _math(nt, "MULTIPLY", lock, 37.0)))))
        wave = _math(nt, "SINE", _math(nt, "ADD", _math(nt, "MULTIPLY", warp, g * 3.14159),
                                       _math(nt, "MULTIPLY", lock, 11.0)))
        wave = _math(nt, "MULTIPLY", wave, _math(nt, "ABSOLUTE", wave))  # soft-signed: broad valleys, soft ridges
        bump = nt.nodes.new("ShaderNodeBump")
        bump.inputs["Strength"].default_value = float(look.get("groove_depth", 0.25))
        bump.inputs["Distance"].default_value = 0.0005
        nt.links.new(_math(nt, "MULTIPLY", wave, _math(nt, "SUBTRACT", 1.0, edge)), bump.inputs["Height"])
        nt.links.new(bump.outputs[0], bsdf.inputs["Normal"])
    return m


def id_pass():
    """Flat emission colours for a pixel count: the hair underlayer red, every lock green, all else black."""
    def emit(name, rgb):
        m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
        m.use_nodes = True
        nt = m.node_tree
        nt.nodes.clear()
        o = nt.nodes.new("ShaderNodeOutputMaterial")
        e = nt.nodes.new("ShaderNodeEmission")
        e.inputs["Color"].default_value = (*rgb, 1.0)
        nt.links.new(e.outputs[0], o.inputs["Surface"])
        return m
    red, green, black = emit("hp_id_mass", (1, 0, 0)), emit("hp_id_lock", (0, 1, 0)), emit("hp_id_else", (0, 0, 0))
    strands = bpy.data.objects.get("hair_scalp") is not None
    atlas_img = bpy.data.images.get("hp_hair_atlas")

    def cut(name, rgb):  # a card: the colour where its strands are (alpha over a half), nothing elsewhere
        m = emit(name, rgb)
        nt = m.node_tree
        o = next(n for n in nt.nodes if n.type == "OUTPUT_MATERIAL")
        e = next(n for n in nt.nodes if n.type == "EMISSION")
        tex = nt.nodes.new("ShaderNodeTexImage")
        tex.image = atlas_img
        tr = nt.nodes.new("ShaderNodeBsdfTransparent")
        mx = nt.nodes.new("ShaderNodeMixShader")
        nt.links.new(_math(nt, "GREATER_THAN", tex.outputs["Alpha"], 0.5), mx.inputs[0])
        nt.links.new(tr.outputs[0], mx.inputs[1])
        nt.links.new(e.outputs[0], mx.inputs[2])
        nt.links.new(mx.outputs[0], o.inputs["Surface"])
        m.surface_render_method = "DITHERED"
        m.use_backface_culling = False
        return m
    red_c, green_c = (cut("hp_id_mass_c", (1, 0, 0)), cut("hp_id_lock_c", (0, 1, 0))) if atlas_img else (red, green)
    ng = bpy.data.node_groups.get(GROUP)
    if ng is not None:
        for n in ng.nodes:
            if n.type == "SET_MATERIAL":
                n.inputs["Material"].default_value = green
    for ob in bpy.data.objects:
        if ob.type not in ("MESH", "CURVE") or (strands and (ob.get("hp_hair_scalp") or ob.get("hp_band"))):
            continue
        mat = red if ob.get("hp_hair_cap") else green if ob.get("hp_lock") else black
        if ob.get("hp_cards"):
            mat = red_c if ob.get("hp_hair_cap") else green_c
        if ob.type == "MESH":
            ob.data.materials.clear()
            ob.data.materials.append(mat)
        else:  # a lock: its node group's Set Material already says green; the curve's own slot too, and re-evaluate
            ob.data.materials.clear()
            ob.data.materials.append(green)
            ob.update_tag()
    if strands:
        import blender_strands
        blender_strands.id_pass()
    bpy.context.view_layer.update()
    sc = bpy.context.scene
    sc.view_settings.view_transform = "Standard"
    if sc.world and sc.world.node_tree:
        bg = sc.world.node_tree.nodes.get("Background")
        if bg:
            bg.inputs["Strength"].default_value = 0.0


def clay():
    """The hair material as plain clay (a mid grey-brown, no gaps, sheen or grooves): judge the forms alone."""
    if bpy.data.objects.get("hair_scalp") is not None:
        import blender_strands
        blender_strands.clay()
    m = bpy.data.materials.get("hp_hair")
    if m is None:
        return
    nt = m.node_tree
    bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
    for k in ("Base Color", "Normal"):
        for ln in list(bsdf.inputs[k].links):
            nt.links.remove(ln)
    bsdf.inputs["Base Color"].default_value = (0.33, 0.25, 0.21, 1.0)
    bsdf.inputs["Roughness"].default_value = 0.6
    bsdf.inputs["Anisotropic"].default_value = 0.0
    m["hp_look"] = "clay"
    mc = bpy.data.materials.get("hp_hair_cards")
    if mc is not None and mc.node_tree:  # the cards as clay: their alpha kept, no picture, no relief
        b2 = next(n for n in mc.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
        for k in ("Base Color", "Normal"):
            for ln in list(b2.inputs[k].links):
                mc.node_tree.links.remove(ln)
        b2.inputs["Base Color"].default_value = (0.33, 0.25, 0.21, 1.0)
        b2.inputs["Roughness"].default_value = 0.6
        b2.inputs["Anisotropic"].default_value = 0.0


def _set_inputs(mod, vals: dict):
    ng = mod.node_group
    for item in ng.interface.items_tree:
        if item.item_type != "SOCKET" or item.in_out != "INPUT" or item.name not in vals:
            continue
        v = vals[item.name]
        mod[item.identifier] = tuple(v) if isinstance(v, (list, tuple)) else v


def get_inputs(mod) -> dict:
    out = {}
    for item in mod.node_group.interface.items_tree:
        if item.item_type == "SOCKET" and item.in_out == "INPUT" and item.socket_type != "NodeSocketGeometry":
            v = mod[item.identifier]
            out[item.name] = list(v) if hasattr(v, "__len__") else v
    return out


def apply(locks: list, look: dict, coll_name: str = "hair", segments: int = 32, sides: int = 16):
    """Bring the hair collection in line with the locks: [{"name", "pts": [[x,y,z]...] (world), "handles"?:
    [[lx,ly,lz,rx,ry,rz]...], "radius"?: [...], "tilt"?: [...], "inputs": {Width...}, "hash"}]. A lock whose hash
    is unchanged is left alone (a person's unsynced edit to it survives: pull first)."""
    material(look)
    ng = node_group()
    coll = bpy.data.collections.get(coll_name)
    if coll is None:
        coll = bpy.data.collections.new(coll_name)
        bpy.context.scene.collection.children.link(coll)
    want = {lk["name"]: lk for lk in locks}
    for ob in list(coll.objects):
        # (the underlayer isn't a lock) a lock the spec no longer has, or a copy of a lock (Shift+D keeps hp_lock)
        # that a pull outside this session named as a lock of its own
        if ob.get("hp_lock") is not None and (ob.get("hp_lock") not in want or ob.name != ob.get("hp_lock")):
            cu = ob.data
            bpy.data.objects.remove(ob)
            if cu is not None and cu.users == 0:
                bpy.data.curves.remove(cu)
    have = {ob.get("hp_lock"): ob for ob in coll.objects}
    made = []
    for name, lk in want.items():
        ob = have.get(name)
        if ob is not None and ob.get("hp_hash") == lk["hash"] and ob.modifiers.get("hp_lock") \
                and ob.modifiers["hp_lock"].node_group == ng:
            continue
        if ob is None:
            cu = bpy.data.curves.new(name, "CURVE")
            ob = bpy.data.objects.new(name, cu)
            coll.objects.link(ob)
        cu = ob.data
        cu.dimensions = "3D"
        cu.resolution_u = 12
        cu.twist_mode = "MINIMUM"
        cu.splines.clear()
        sp = cu.splines.new("BEZIER")
        P = lk["pts"]
        sp.bezier_points.add(len(P) - 1)
        H = lk.get("handles")
        for i, bp in enumerate(sp.bezier_points):
            bp.co = P[i]
            if H and H[i]:
                bp.handle_left_type = bp.handle_right_type = "FREE"
                bp.handle_left, bp.handle_right = H[i][:3], H[i][3:]
            else:
                bp.handle_left_type = bp.handle_right_type = "AUTO"
            bp.radius = (lk.get("radius") or [1.0] * len(P))[i]
            bp.tilt = (lk.get("tilt") or [0.0] * len(P))[i]
        mod = ob.modifiers.get("hp_lock") or ob.modifiers.new("hp_lock", "NODES")
        mod.node_group = ng
        _set_inputs(mod, {**lk["inputs"], "Segments": segments, "Sides": sides})
        ob["hp_lock"], ob["hp_hash"] = name, lk["hash"]
        ob["hp_set"] = _state(ob)  # what the sync wrote: pull reports only what moved from it
        made.append(name)
    import json
    coll["hp_made"] = json.dumps(sorted(want))  # the locks this sync left in the scene: pull reports deletions
    return made


def _state(ob) -> str:
    import json
    return json.dumps(read_one(ob), sort_keys=True)


def read_one(ob) -> dict:
    sp = ob.data.splines[0]
    M = ob.matrix_world
    pts, hnd = [], []
    for bp in sp.bezier_points:
        pts.append([round(v, 5) for v in (M @ bp.co)])
        free = bp.handle_left_type in ("FREE", "ALIGNED") or bp.handle_right_type in ("FREE", "ALIGNED")
        hnd.append([round(v, 5) for v in list(M @ bp.handle_left) + list(M @ bp.handle_right)] if free else None)
    return {"pts": pts, "handles": hnd if any(hnd) else None,
            "radius": [round(bp.radius, 4) for bp in sp.bezier_points],
            "tilt": [round(bp.tilt, 4) for bp in sp.bezier_points],
            "inputs": {k: (round(v, 5) if isinstance(v, float) else v) for k, v in get_inputs(ob.modifiers["hp_lock"]).items()
                       if k not in ("Centre", "Segments", "Sides")}}


def read(coll_name: str = "hair") -> dict:
    """{lock: its state} for every lock a person changed since the sync wrote it (moved points or handles,
    radius, tilt, modifier numbers); "__deleted__": locks the sync made that are gone from the scene; "__new__":
    curves added in the collection (a lock duplicated with Shift+D, or a new Bezier curve), keyed by their object
    name as a lock name (the object is renamed to it, so the next sync keeps it)."""
    import json
    import re
    coll = bpy.data.collections.get(coll_name)
    if coll is None:
        return {}
    bpy.context.view_layer.update()
    out, new = {}, {}
    seen = set()
    for ob in coll.objects:
        if ob.type != "CURVE" or not ob.data.splines or ob.get("hp_hair_cap"):
            continue
        lk = ob.get("hp_lock")
        if lk is not None and ob.name == lk:
            seen.add(lk)
            now = read_one(ob)
            if json.dumps(now, sort_keys=True) != ob.get("hp_set"):
                out[lk] = dict(now, hash=ob.get("hp_hash"))  # which spec lock the sync built it from
            continue
        # added in Blender: a copy of a lock (its name "sweep1.001") or a curve with no lock behind it
        sp = ob.data.splines[0]
        if sp.type != "BEZIER" or len(sp.bezier_points) < 2:
            continue
        name = re.sub(r"[^A-Za-z0-9_]", "_", ob.name)
        if ob.modifiers.get("hp_lock") is None:  # a bare curve: give it the lock sweep so it reads back
            mod = ob.modifiers.new("hp_lock", "NODES")
            mod.node_group = node_group()
        if ob.data.users > 1:  # Alt+D shares the curve: make it its own
            ob.data = ob.data.copy()
        ob.name = name
        ob["hp_lock"] = ob.name
        ob["hp_hash"] = ""
        new[ob.name] = read_one(ob)
    made = set(json.loads(coll.get("hp_made", "[]")))
    gone = sorted(made - seen)
    if gone:
        out["__deleted__"] = gone
    if new:
        out["__new__"] = new
    return out


def evaluated_mesh(coll_name: str = "hair", segments: int | None = None, sides: int | None = None):
    """Every lock's evaluated mesh in world space, joined: verts, faces (triangles), and the attributes."""
    coll = bpy.data.collections.get(coll_name)
    dg = bpy.context.evaluated_depsgraph_get()
    V, F, A = [], [], {}
    off = 0
    for ob in sorted(coll.objects, key=lambda o: o.name):
        mod = ob.modifiers.get("hp_lock")
        if mod is None:
            continue
        if segments or sides:
            _set_inputs(mod, {**({"Segments": segments} if segments else {}), **({"Sides": sides} if sides else {})})
            ob.update_tag()
            dg = bpy.context.evaluated_depsgraph_get()
            dg.update()
        ev = ob.evaluated_get(dg)
        me = ev.to_mesh()
        me.calc_loop_triangles()
        n = len(me.vertices)
        v = np.empty(n * 3, np.float32)
        me.vertices.foreach_get("co", v)
        v = v.reshape(-1, 3) @ np.array(ob.matrix_world)[:3, :3].T + np.array(ob.matrix_world)[:3, 3]
        t = np.empty(len(me.loop_triangles) * 3, np.int32)
        me.loop_triangles.foreach_get("vertices", t)
        V.append(v)
        F.append(t.reshape(-1, 3) + off)
        for an in ("hp_along", "hp_across", "hp_out", "hp_lock", "hp_grey"):
            a = np.zeros(n, np.float32)
            if an in me.attributes:
                me.attributes[an].data.foreach_get("value", a)
            A.setdefault(an, []).append(a)
        tg = np.zeros(n * 3, np.float32)
        if "hp_tangent" in me.attributes:
            me.attributes["hp_tangent"].data.foreach_get("vector", tg)
        A.setdefault("hp_tangent", []).append(tg.reshape(-1, 3))
        off += n
        ev.to_mesh_clear()
    return np.concatenate(V), np.concatenate(F), {k: np.concatenate(v) for k, v in A.items()}


def cap(path, kind: str = "cap", coll_name: str = "hair"):
    """The underlayer on the scalp (dark: what shows between locks) or, kind "mass", the groom's whole volume."""
    z = np.load(path)
    V, F = z["verts"], z["faces"]
    coll = bpy.data.collections.get(coll_name)
    if coll is None:
        coll = bpy.data.collections.new(coll_name)
        bpy.context.scene.collection.children.link(coll)
    old = bpy.data.objects.get("hair_cap")
    if old is not None:
        me = old.data
        bpy.data.objects.remove(old)
        if me.users == 0:
            bpy.data.meshes.remove(me)
    me = bpy.data.meshes.new("hair_cap")
    me.vertices.add(len(V))
    me.vertices.foreach_set("co", V.astype(np.float32).ravel())
    nq = len(F)
    me.loops.add(nq * 4)
    me.loops.foreach_set("vertex_index", F.astype(np.int32).ravel())
    me.polygons.add(nq)
    me.polygons.foreach_set("loop_start", np.arange(0, nq * 4, 4, dtype=np.int32))
    me.update()
    me.validate()
    across, out = {"cap": (1.0, -1.0), "under": (0.45, 0.5), "mass": (0.0, 1.0)}[kind]
    given = {"hp_across": z["across"] if "across" in z else None, "hp_lock": z["lock"] if "lock" in z else None}
    for an, v in (("hp_along", 0.5), ("hp_across", across), ("hp_out", out), ("hp_lock", 0.5), ("hp_grey", 0.0)):
        a = me.attributes.new(an, "FLOAT", "POINT")
        val = given.get(an)
        a.data.foreach_set("value", np.full(len(V), v, np.float32) if val is None else val.astype(np.float32))
    if "tangent" in z:
        a = me.attributes.new("hp_tangent", "FLOAT_VECTOR", "POINT")
        a.data.foreach_set("vector", z["tangent"].astype(np.float32).ravel())
    me.shade_smooth()
    me.materials.append(bpy.data.materials["hp_hair"])
    ob = bpy.data.objects.new("hair_cap", me)
    ob["hp_hair_cap"] = kind
    coll.objects.link(ob)
    return ob


def show(hair: dict):
    """Apply a hair job (hair.job): the locks and the cap."""
    if not hair:
        return []
    import blender_strands
    if hair.get("strands"):  # strand hair (blender_strands.py): Hair Curves guides, no solid locks, no shell
        coll = bpy.data.collections.get("hair")
        for ob in list(coll.objects) if coll else []:
            if ob.get("hp_lock") is not None or ob.get("hp_hair_cap") or ob.get("hp_cards"):
                bpy.data.objects.remove(ob)
        return blender_strands.show(hair["strands"])
    blender_strands.clear()
    material(hair["look"])
    made = apply(hair["locks"], hair["look"])
    cd = hair.get("cards")
    coll = bpy.data.collections["hair"]
    for ob in coll.objects:  # as cards, a lock's curve stays (what a person edits) but its solid lens is hidden
        mod = ob.modifiers.get("hp_lock") if ob.get("hp_lock") is not None else None
        if mod is not None and mod.show_render == bool(cd):
            mod.show_render = mod.show_viewport = not cd
            ob.update_tag()
    for n in ("hair_cards", "hair_cap"):
        old = bpy.data.objects.get(n)
        if old is not None and (old.get("hp_cards") or n == "hair_cards"):
            me = old.data
            bpy.data.objects.remove(old)
            if me.users == 0:
                bpy.data.meshes.remove(me)
    if cd:
        mat = card_material(hair["look"], cd["color"], cd["normal"])
        dbg = cd.get("debug")
        if dbg == "layers":
            _debug_layers(mat)
        elif dbg in ("no_normal", "unlit"):  # isolate what makes a pattern: the normal map, or the lighting at all
            nt = mat.node_tree
            bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
            for l in list(bsdf.inputs["Normal"].links):
                nt.links.remove(l)
            if dbg == "unlit":
                src = bsdf.inputs["Base Color"].links[0].from_socket
                nt.links.new(src, bsdf.inputs["Emission Color"])
                bsdf.inputs["Emission Strength"].default_value = 1.0
                for l in list(bsdf.inputs["Base Color"].links):
                    nt.links.remove(l)
                bsdf.inputs["Base Color"].default_value = (0, 0, 0, 1)
                bsdf.inputs["Specular IOR Level"].default_value = 0.0
        card_object("hair_cap", cd["cap"], mat, coll)["hp_hair_cap"] = "under"
        card_object("hair_cards", cd["mesh"], mat, coll)
        if dbg in ("cap_only", "cards_only"):
            ob = bpy.data.objects["hair_cards" if dbg == "cap_only" else "hair_cap"]
            ob.hide_render = ob.hide_viewport = True
    else:
        cap(hair["cap"], hair.get("cap_kind", "cap"))
    return made


def card_material(look: dict, color_png: str, normal_png: str):
    """The cards' material: the strand atlas (colour x the vertex colour's root-to-tip ramp, alpha dithered, a
    normal map), anisotropic along the hair, the same from both sides."""
    m = bpy.data.materials.get("hp_hair_cards") or bpy.data.materials.new("hp_hair_cards")
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    nt.links.new(bsdf.outputs[0], out.inputs["Surface"])
    for old in ("hp_hair_atlas", "hp_hair_atlas_n"):
        if old in bpy.data.images:
            bpy.data.images.remove(bpy.data.images[old])
    img = bpy.data.images.load(color_png)
    img.name = "hp_hair_atlas"
    img.pack()
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = img
    tex.name = "hp_atlas"
    imn = bpy.data.images.load(normal_png)
    imn.name = "hp_hair_atlas_n"
    imn.colorspace_settings.name = "Non-Color"
    imn.pack()
    texn = nt.nodes.new("ShaderNodeTexImage")
    texn.image = imn
    col = nt.nodes.new("ShaderNodeAttribute")
    col.attribute_name = "hp_col"
    mul = nt.nodes.new("ShaderNodeMix")
    mul.data_type, mul.blend_type = "RGBA", "MULTIPLY"
    mul.inputs["Factor"].default_value = 1.0
    nt.links.new(tex.outputs["Color"], mul.inputs["A"])
    nt.links.new(col.outputs["Color"], mul.inputs["B"])
    mul.name = "hp_base"
    nt.links.new(mul.outputs["Result"], bsdf.inputs["Base Color"])
    nt.links.new(tex.outputs["Alpha"], bsdf.inputs["Alpha"])
    nm = nt.nodes.new("ShaderNodeNormalMap")
    nm.inputs["Strength"].default_value = float(look.get("strand_relief", 0.6))
    nt.links.new(texn.outputs["Color"], nm.inputs["Color"])
    nt.links.new(nm.outputs[0], bsdf.inputs["Normal"])
    tan = nt.nodes.new("ShaderNodeAttribute")
    tan.attribute_name = "hp_tangent"
    nt.links.new(tan.outputs["Vector"], bsdf.inputs["Tangent"])
    # a card is a flat sheet standing for many round hairs: at the lock's own gloss it mirrors a light as one white
    # plate. Rougher, half the specular, and the highlight takes the hair's colour (as light through hairs does)
    bsdf.inputs["Roughness"].default_value = max(float(look.get("roughness", 0.42)), 0.5)
    bsdf.inputs["Specular IOR Level"].default_value = float(look.get("specular", 0.5)) * 0.5
    try:
        bsdf.inputs["Specular Tint"].default_value = (*[min(1.0, 3.0 * c) for c in [((int(look.get("sheen", "#86524a").lstrip("#")[i:i + 2], 16) / 255) ** 2.2) for i in (0, 2, 4)]], 1)
    except (KeyError, TypeError):
        pass
    bsdf.inputs["Anisotropic"].default_value = float(look.get("anisotropic", 0.7)) * 0.7
    for attr, val in (("surface_render_method", "DITHERED"), ("use_transparent_shadow", True),
                      ("blend_method", "HASHED")):
        try:
            setattr(m, attr, val)
        except (AttributeError, TypeError):
            pass
    m.use_backface_culling = False
    return m


LAYER_COLORS = {-1: (0.35, 0.35, 0.35), 0: (0.8, 0.1, 0.1), 1: (0.1, 0.7, 0.1), 2: (0.1, 0.2, 0.9), 3: (0.9, 0.8, 0.1),
                4: (0.9, 0.1, 0.9), 5: (0.1, 0.8, 0.8)}  # cap grey, coverage red, mid green, top blue, yellow, ...


def _debug_layers(m):
    """The cards as solid quads (alpha off), coloured by layer: what the geometry is without its pictures. Back
    faces are drawn darker (a card seen from behind)."""
    nt = m.node_tree
    bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
    for sk in ("Alpha", "Base Color", "Normal", "Tangent"):
        for l in list(bsdf.inputs[sk].links):
            nt.links.remove(l)
    bsdf.inputs["Alpha"].default_value = 1.0
    bsdf.inputs["Anisotropic"].default_value = 0.0
    at = nt.nodes.new("ShaderNodeAttribute")
    at.attribute_name = "hp_layer"
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.interpolation = "CONSTANT"
    el = ramp.color_ramp.elements
    ks = sorted(LAYER_COLORS)
    el[0].position, el[0].color = 0.0, (*LAYER_COLORS[ks[0]], 1)
    el[1].position, el[1].color = (ks[1] + 0.5) / 8, (*LAYER_COLORS[ks[1]], 1)
    for k in ks[2:]:
        e = el.new((k + 0.5) / 8)
        e.color = (*LAYER_COLORS[k], 1)
    mr = nt.nodes.new("ShaderNodeMath")
    mr.operation = "MULTIPLY_ADD"
    mr.inputs[1].default_value, mr.inputs[2].default_value = 1 / 8, 1 / 8
    nt.links.new(at.outputs["Fac"], mr.inputs[0])
    nt.links.new(mr.outputs[0], ramp.inputs["Fac"])
    geo = nt.nodes.new("ShaderNodeNewGeometry")
    mix = nt.nodes.new("ShaderNodeMix")
    mix.data_type, mix.blend_type = "RGBA", "MULTIPLY"
    nt.links.new(geo.outputs["Backfacing"], mix.inputs["Factor"])
    nt.links.new(ramp.outputs["Color"], mix.inputs["A"])
    mix.inputs["B"].default_value = (0.35, 0.35, 0.35, 1)
    nt.links.new(mix.outputs["Result"], bsdf.inputs["Base Color"])


def card_object(name: str, path: str, mat, coll):
    """A card mesh (hair_cards.mesh's npz) as an object: uv, its bent normals as custom normals, hp_col, hp_tangent."""
    z = np.load(path)
    V, T = z["verts"], z["tris"]
    me = bpy.data.meshes.new(name)
    me.vertices.add(len(V))
    me.vertices.foreach_set("co", V.astype(np.float32).ravel())
    me.loops.add(len(T) * 3)
    me.loops.foreach_set("vertex_index", T.astype(np.int32).ravel())
    me.polygons.add(len(T))
    me.polygons.foreach_set("loop_start", np.arange(0, len(T) * 3, 3, dtype=np.int32))
    me.update()
    me.validate()
    uvl = me.uv_layers.new(name="UVMap")
    lv = np.empty(len(me.loops), np.int32)
    me.loops.foreach_get("vertex_index", lv)
    uvl.data.foreach_set("uv", z["uv"][lv].astype(np.float32).ravel())
    a = me.attributes.new("hp_col", "FLOAT_COLOR", "POINT")
    a.data.foreach_set("color", np.concatenate([z["col"], np.ones((len(V), 1))], 1).astype(np.float32).ravel())
    a = me.attributes.new("hp_tangent", "FLOAT_VECTOR", "POINT")
    a.data.foreach_set("vector", z["tangent"].astype(np.float32).ravel())
    for an in ("along", "layer"):
        a = me.attributes.new("hp_" + an, "FLOAT", "POINT")
        a.data.foreach_set("value", z[an].astype(np.float32))
    me.shade_smooth()
    if len(V) == len(me.vertices):
        me.normals_split_custom_set_from_vertices(z["normal"].astype(np.float32).tolist())
    me.materials.append(mat)
    ob = bpy.data.objects.new(name, me)
    ob["hp_cards"] = 1
    coll.objects.link(ob)
    return ob


def hair_points(coll_name: str = "hair", names: list | None = None):
    """Every evaluated vertex of the hair collection (locks and the underlayer), world space (n, 3) float32; names
    (a list) gets each object's name repeated per vertex (which lock makes which part of an outline)."""
    coll = bpy.data.collections.get(coll_name)
    if coll is None:
        return np.zeros((0, 3), np.float32)
    if bpy.data.objects.get("hair_scalp") is not None:
        import blender_strands
        return blender_strands.points(names)
    dg = bpy.context.evaluated_depsgraph_get()
    out = []
    for ob in coll.objects:
        ev = ob.evaluated_get(dg)
        me = ev.to_mesh()
        v = np.empty(len(me.vertices) * 3, np.float32)
        me.vertices.foreach_get("co", v)
        M = np.array(ob.matrix_world, np.float32)
        out.append(v.reshape(-1, 3) @ M[:3, :3].T + M[:3, 3])
        if names is not None:
            names += [ob.name] * len(out[-1])
        ev.to_mesh_clear()
    return np.concatenate(out) if out else np.zeros((0, 3), np.float32)


def _mesh_object(name, V, F, loops_uv=None, attrs=None):
    me = bpy.data.meshes.new(name)
    me.from_pydata([tuple(map(float, v)) for v in V], [], [tuple(map(int, f)) for f in F])
    me.update()
    for an, a in (attrs or {}).items():
        a = np.asarray(a, np.float32)
        at = me.attributes.new(an, "FLOAT_VECTOR" if a.ndim == 2 else "FLOAT", "POINT")
        at.data.foreach_set("vector" if a.ndim == 2 else "value", a.ravel())
    if loops_uv is not None:
        uvl = me.uv_layers.new(name="UVMap")
        uvl.data.foreach_set("uv", loops_uv.astype(np.float32).ravel())
    me.shade_smooth()
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    return ob


def export_bake(job):
    """The hair as a game asset: the locks at a low resolution (job "segments"/"sides") plus the underlayer
    decimated; each lock's uv runs round its lens and along it (one island per lock; the underlayer smart-projected),
    islands scaled to their real size and packed by Blender; then Cycles bakes the full-resolution locks (their node
    material: base colour and roughness as emission; normals with the grooves' bump) onto it, selected-to-active.
    Writes <out>/hair_low.npz (verts, tris, per-corner uv) and hair_{color,rough}.npy (linear floats),
    hair_normal.png (tangent space)."""
    import os
    import bmesh
    out = job["out"]
    show(job["hair"])
    coll = bpy.data.collections["hair"]
    cap = next(ob for ob in coll.objects if ob.get("hp_hair_cap"))
    Vl, Fl, Al = evaluated_mesh("hair", segments=job.get("segments", 12), sides=job.get("sides", 6))
    dec = cap.modifiers.new("dec", "DECIMATE")
    dec.ratio = job.get("cap_ratio", 0.08)
    sh = cap.modifiers.new("shrink", "DISPLACE")  # pulled in under the low-poly locks (decimated, it poked through them)
    sh.strength = -float(job.get("cap_inset", 0.003))
    sh.mid_level = 0.0
    dg = bpy.context.evaluated_depsgraph_get()
    ev = cap.evaluated_get(dg)
    cm = ev.to_mesh()
    cm.calc_loop_triangles()
    cv = np.empty(len(cm.vertices) * 3, np.float32)
    cm.vertices.foreach_get("co", cv)
    ct = np.empty(len(cm.loop_triangles) * 3, np.int32)
    cm.loop_triangles.foreach_get("vertices", ct)
    cv, ct = cv.reshape(-1, 3), ct.reshape(-1, 3)
    ev.to_mesh_clear()
    cap.modifiers.remove(dec)
    cap.modifiers.remove(sh)
    ang = (np.arctan2(Al["hp_out"], Al["hp_across"]) / (2 * np.pi)) % 1.0
    uvp = np.stack([ang, Al["hp_along"]], 1)
    cu = uvp[Fl].copy()
    wrap = (cu[..., 0].max(1) - cu[..., 0].min(1)) > 0.5  # a face across the profile's seam
    cu[..., 0] = np.where(wrap[:, None] & (cu[..., 0] < 0.5), cu[..., 0] + 1.0, cu[..., 0])
    V = np.concatenate([Vl, cv])
    F = np.concatenate([Fl, ct + len(Vl)])
    uv_c = np.concatenate([cu, np.zeros((len(ct), 3, 2))])
    # the low poly carries the locks' attributes (the underlayer: its own constants), so it bakes from its own
    # material: selected-to-active from the full-resolution locks picked up neighbouring locks where they overlap
    # (shingles), smearing one lock's colour and normals onto the next
    nc = len(cv)
    cap_a = {"hp_along": 0.5, "hp_across": 1.0, "hp_out": 0.0, "hp_lock": 0.5, "hp_grey": 0.0}  # gap-dark
    attrs = {k: np.concatenate([Al[k], np.full(nc, cap_a[k], np.float32)]) for k in cap_a}
    attrs["hp_tangent"] = np.concatenate([Al["hp_tangent"], np.tile([0.0, 1.0, 0.0], (nc, 1))])
    low = _mesh_object("hp_low", V, F, loops_uv=uv_c.reshape(-1, 2), attrs=attrs)
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    bpy.context.view_layer.objects.active = low
    low.select_set(True)
    bm = bmesh.new()
    bm.from_mesh(low.data)
    bm.faces.ensure_lookup_table()
    nlock = len(Fl)
    for f in bm.faces:
        f.select_set(f.index >= nlock)
    bm.to_mesh(low.data)
    bm.free()
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.uv.smart_project(angle_limit=1.15, island_margin=0.0)
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.select_all(action="SELECT")
    bpy.ops.uv.average_islands_scale()
    bpy.ops.uv.pack_islands(margin=job.get("margin", 0.004), rotate=True)
    bpy.ops.object.mode_set(mode="OBJECT")
    for ob in list(coll.objects):  # the curves aren't needed any more: the low bakes from itself
        bpy.data.objects.remove(ob)
    size = int(job.get("texture", 1024))
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    sc.cycles.samples = int(job.get("samples", 4))
    sc.cycles.device = "CPU"
    mat = bpy.data.materials["hp_hair"]
    low.data.materials.append(mat)
    tex = mat.node_tree.nodes.new("ShaderNodeTexImage")
    mat.node_tree.nodes.active = tex
    kw = dict(use_selected_to_active=False, margin=8, target="IMAGE_TEXTURES")
    for what in ("color", "rough", "normal"):
        img = bpy.data.images.new(f"hair_{what}", size, size, alpha=False, float_buffer=(what != "normal"))
        if what == "normal":
            img.colorspace_settings.name = "Non-Color"
        tex.image = img
        for o in bpy.context.view_layer.objects:
            if o is not None:
                o.select_set(False)
        low.select_set(True)
        bpy.context.view_layer.objects.active = low
        if what == "normal":
            _emit_hair(mat, None)
            bpy.ops.object.bake(type="NORMAL", normal_space="TANGENT", **kw)
            img.filepath_raw = os.path.join(out, "hair_normal.png")
            img.file_format = "PNG"
            img.save()
        else:
            _emit_hair(mat, "Base Color" if what == "color" else "Roughness")
            bpy.ops.object.bake(type="EMIT", **kw)
            px = np.array(img.pixels[:], np.float32).reshape(size, size, 4)
            np.save(os.path.join(out, f"hair_{what}.npy"), px)
    me = low.data
    me.calc_loop_triangles()
    lv = np.empty(len(me.vertices) * 3, np.float32)
    me.vertices.foreach_get("co", lv)
    tri = np.empty(len(me.loop_triangles) * 3, np.int32)
    me.loop_triangles.foreach_get("vertices", tri)
    tl = np.empty(len(me.loop_triangles) * 3, np.int32)
    me.loop_triangles.foreach_get("loops", tl)
    uvs = np.empty(len(me.loops) * 2, np.float32)
    me.uv_layers.active.data.foreach_get("uv", uvs)
    np.savez(os.path.join(out, "hair_low.npz"), verts=lv.reshape(-1, 3), tris=tri.reshape(-1, 3),
             uv=uvs.reshape(-1, 2)[tl])
    print("@@hair_export", len(tri) // 3)


def _emit_hair(mat, what):
    """The hair material's output as an emission of one of its Principled inputs (None: back to the BSDF)."""
    nt = mat.node_tree
    bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
    out = next(n for n in nt.nodes if n.type == "OUTPUT_MATERIAL")
    if what is None:
        nt.links.new(bsdf.outputs[0], out.inputs["Surface"])
        return
    em = nt.nodes.get("hp_bake_em") or nt.nodes.new("ShaderNodeEmission")
    em.name = "hp_bake_em"
    mat.cycles.emission_sampling = "NONE"
    for ln in list(em.inputs["Color"].links):
        nt.links.remove(ln)
    inp = bsdf.inputs[what]
    if inp.is_linked:
        nt.links.new(inp.links[0].from_socket, em.inputs["Color"])
    else:
        v = inp.default_value
        em.inputs["Color"].default_value = (v, v, v, 1.0) if not hasattr(v, "__len__") else tuple(v)
    nt.links.new(em.outputs[0], out.inputs["Surface"])
