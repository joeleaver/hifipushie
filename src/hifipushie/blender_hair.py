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
VERSION = 8  # bump when the node group changes: scenes rebuild it
INPUTS = [  # (name, type, default, min, max) in modifier order; the spec's lock keys are these, lower case
    ("Width", "NodeSocketFloat", 0.03, 0.0, 1.0),
    ("Thickness", "NodeSocketFloat", 0.008, 0.0, 1.0),
    ("Cup", "NodeSocketFloat", 0.002, -0.1, 0.1),
    ("Taper", "NodeSocketFloat", 1.0, 0.0, 1.0),
    ("Belly", "NodeSocketFloat", 0.3, 0.0, 1.0),
    ("Root", "NodeSocketFloat", 0.6, 0.0, 1.0),
    ("Twist", "NodeSocketFloat", 0.0, -720.0, 720.0),
    ("Flip", "NodeSocketFloat", 0.0, -180.0, 180.0),
    ("Grey", "NodeSocketFloat", 0.0, 0.0, 1.0),
    ("Seed", "NodeSocketFloat", 0.0, 0.0, 1.0),
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
    if ng is None:
        ng = bpy.data.node_groups.new(GROUP, "GeometryNodeTree")
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
    s_abs = _math(nt, "POWER", _math(nt, "ABSOLUTE", ppos[1]), 0.8)
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
    geo = c2m.outputs[0]
    geo = _store(nt, geo, "hp_along", along)
    geo = _store(nt, geo, "hp_across", pacross)
    geo = _store(nt, geo, "hp_out", pout)
    geo = _store(nt, geo, "hp_tangent", tangent, "FLOAT_VECTOR")
    geo = _store(nt, geo, "hp_lock", I["Seed"])
    geo = _store(nt, geo, "hp_grey", I["Grey"])
    sm = nt.nodes.new("GeometryNodeSetShadeSmooth")
    nt.links.new(geo, sm.inputs["Geometry"])
    mat = nt.nodes.new("GeometryNodeSetMaterial")
    nt.links.new(sm.outputs[0], mat.inputs["Geometry"])
    mat.inputs["Material"].default_value = bpy.data.materials.get("hp_hair") or bpy.data.materials.new("hp_hair")
    nt.links.new(mat.outputs[0], go.inputs[0])
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
    key = repr(sorted(look.items()))
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
    band = _math(nt, "MULTIPLY", _smooth(nt, _math(nt, "SUBTRACT", 0.0, _math(nt, "ABSOLUTE", across)), -0.75, -0.1),
                 _math(nt, "MULTIPLY", top, _smooth(nt, along, 0.1, 0.35)))
    band = _math(nt, "MULTIPLY", band, _math(nt, "SUBTRACT", 1.0, _smooth(nt, along, 0.7, 1.0)))
    col = mix(col, rgb(look.get("sheen", "#9a6048")), _math(nt, "MULTIPLY", band, float(look.get("sheen_amount", 0.45))))
    col = mix(col, rgb(look.get("grey", "#9a948d")), _math(nt, "MULTIPLY", _math(nt, "MULTIPLY", grey, 0.7), expo))
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
    ng = bpy.data.node_groups.get(GROUP)
    if ng is not None:
        for n in ng.nodes:
            if n.type == "SET_MATERIAL":
                n.inputs["Material"].default_value = green
    for ob in bpy.data.objects:
        if ob.type not in ("MESH", "CURVE"):
            continue
        mat = red if ob.get("hp_hair_cap") else green if ob.get("hp_lock") else black
        if ob.type == "MESH":
            ob.data.materials.clear()
            ob.data.materials.append(mat)
        else:  # a lock: its node group's Set Material already says green; the curve's own slot too, and re-evaluate
            ob.data.materials.clear()
            ob.data.materials.append(green)
            ob.update_tag()
    bpy.context.view_layer.update()
    sc = bpy.context.scene
    sc.view_settings.view_transform = "Standard"
    if sc.world and sc.world.node_tree:
        bg = sc.world.node_tree.nodes.get("Background")
        if bg:
            bg.inputs["Strength"].default_value = 0.0


def clay():
    """The hair material as plain clay (a mid grey-brown, no gaps, sheen or grooves): judge the forms alone."""
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
        if ob.get("hp_lock") is not None and ob.get("hp_lock") not in want:  # (the underlayer isn't a lock)
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
    radius, tilt, modifier numbers), and "deleted": locks removed in the scene."""
    import json
    coll = bpy.data.collections.get(coll_name)
    if coll is None:
        return {}
    bpy.context.view_layer.update()
    out = {}
    for ob in coll.objects:
        if ob.get("hp_lock") is None or ob.type != "CURVE" or not ob.data.splines:
            continue
        now = read_one(ob)
        if json.dumps(now, sort_keys=True) != ob.get("hp_set"):
            out[ob["hp_lock"]] = now
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
    material(hair["look"])
    made = apply(hair["locks"], hair["look"])
    cap(hair["cap"], hair.get("cap_kind", "cap"))
    return made


def hair_points(coll_name: str = "hair", names: list | None = None):
    """Every evaluated vertex of the hair collection (locks and the underlayer), world space (n, 3) float32; names
    (a list) gets each object's name repeated per vertex (which lock makes which part of an outline)."""
    coll = bpy.data.collections.get(coll_name)
    if coll is None:
        return np.zeros((0, 3), np.float32)
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
