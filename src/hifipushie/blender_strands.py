"""Inside Blender: hair as strands, on Blender's own hair system.

Guides are Hair Curves objects (collection "hair") attached to a scalp mesh that carries a UV map (u = azimuth,
v = elevation round the head centre) and a density attribute:
  hair_guides       our locks' spines (one curve a lock; per point `hp_side` / `hp_out` = the lock's half width and
                    half thickness there, as vectors). Children: the `hp_lens` group below (a lock is a FLAT clump:
                    strands spread across its lens section; Essentials' Duplicate spreads round a guide = a rope).
  hair_guides_free  the same for locks that leave the head (a tail, escaped strands).
  hair_under        the scalp layer's flow guides. Children: Essentials "Interpolate Hair Curves" on the scalp's UV,
                    density from the scalp's `hp_density` (hairline fade, parting).
On top of each, the Essentials groups a Blender artist knows (Clump, Curl, Frizz, Hair Curves Noise, Shrinkwrap, Set
Hair Curve Profile), loaded from Blender's own asset file, with the numbers hair_strands.py worked out from the spec.
A person combs / sculpts the guide curves (Sculpt mode) and tunes the modifiers; `read` hands both back.
"""
import glob
import hashlib
import json
import os

import bpy
import numpy as np

LENS = "hp_lens"
VERSION = 4  # bump when the lens group changes
ESSENTIALS = ["Clump Hair Curves", "Curl Hair Curves", "Frizz Hair Curves", "Hair Curves Noise",
              "Shrinkwrap Hair Curves", "Set Hair Curve Profile", "Braid Hair Curves", "Interpolate Hair Curves",
              "Trim Hair Curves", "Smooth Hair Curves", "Duplicate Hair Curves"]
OBJECTS = ("hair_guides", "hair_guides_free", "hair_under", "hair_scalp")


def essentials() -> dict:
    """Blender's own hair node groups (the Essentials asset library), appended once."""
    have = {n: bpy.data.node_groups.get(n) for n in ESSENTIALS}
    miss = [n for n, g in have.items() if g is None]
    if miss:
        lib = glob.glob(os.path.join(bpy.utils.system_resource("DATAFILES"), "assets", "nodes",
                                     "procedural_hair_node_assets.blend"))
        if not lib:
            raise RuntimeError("Blender's hair node assets (procedural_hair_node_assets.blend) aren't installed")
        with bpy.data.libraries.load(lib[0]) as (src, dst):
            dst.node_groups = [n for n in src.node_groups if n in miss]
        have = {n: bpy.data.node_groups.get(n) for n in ESSENTIALS}
    return have


def _sock(node, name, kind=None, out=False):
    for s in (node.outputs if out else node.inputs):
        if s.name == name and s.enabled and (kind is None or s.type == kind):
            return s
    raise KeyError(f"{node.bl_idname}: no socket {name} {kind}")


def lens_group():
    """`hp_lens`: every guide curve duplicated `hp_n` x Amount times, each copy moved across the lock's own section
    (a lens: `hp_side` x a + `hp_out` x b (1 - a^2), a and b per copy), its length varied (Tips, Roots), some copies
    let go toward the tip (Flyaway). Attributes kept: hp_lock (the guide's index), hp_rand (per strand)."""
    ng = bpy.data.node_groups.get(LENS)
    if ng is not None and ng.get("hp_version") == VERSION:
        return ng
    if ng is not None:
        ng.name = LENS + "_old"
    ng = bpy.data.node_groups.new(LENS, "GeometryNodeTree")
    ng["hp_version"] = VERSION
    ng.is_modifier = True
    it = ng.interface
    it.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    it.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    for name, typ, dv, lo, hi in (("Amount", "NodeSocketFloat", 1.0, 0.0, 20.0), ("Tips", "NodeSocketFloat", 0.3, 0.0, 0.9),
                                  ("Roots", "NodeSocketFloat", 0.03, 0.0, 0.5), ("Flyaway", "NodeSocketFloat", 0.05, 0.0, 1.0),
                                  ("Flyaway Distance", "NodeSocketFloat", 0.012, 0.0, 0.2),
                                  ("Edge", "NodeSocketFloat", 1.0, 0.2, 3.0), ("Seed", "NodeSocketInt", 0, 0, 10000)):
        s = it.new_socket(name, in_out="INPUT", socket_type=typ)
        s.default_value = dv
        s.min_value, s.max_value = lo, hi
    N, L = ng.nodes, ng.links
    gi, go = N.new("NodeGroupInput"), N.new("NodeGroupOutput")

    def named(name, dtype):
        n = N.new("GeometryNodeInputNamedAttribute")
        n.data_type = dtype
        n.inputs["Name"].default_value = name
        return n.outputs["Attribute"]

    def math(op, a, b=None, c=None):
        n = N.new("ShaderNodeMath")
        n.operation = op
        for i, v in enumerate((a, b, c)):
            if v is None:
                continue
            if isinstance(v, (int, float)):
                n.inputs[i].default_value = v
            else:
                L.new(v, n.inputs[i])
        return n.outputs[0]

    def vmath(op, a, b=None, scale=None):
        n = N.new("ShaderNodeVectorMath")
        n.operation = op
        L.new(a, n.inputs[0])
        if b is not None:
            L.new(b, n.inputs[1])
        if scale is not None:
            if isinstance(scale, (int, float)):
                n.inputs["Scale"].default_value = scale
            else:
                L.new(scale, n.inputs["Scale"])
        return n.outputs[0]

    def rand(lo, hi, seed_off):
        n = N.new("FunctionNodeRandomValue")
        n.data_type = "FLOAT"
        _sock(n, "Min", "VALUE").default_value = lo
        _sock(n, "Max", "VALUE").default_value = hi
        idx = N.new("GeometryNodeInputIndex")
        L.new(idx.outputs[0], n.inputs["ID"])
        L.new(math("ADD", gi.outputs["Seed"], float(seed_off)), n.inputs["Seed"])
        return _sock(n, "Value", "VALUE", out=True)

    def store(geo, name, value, dtype="FLOAT", domain="CURVE"):
        n = N.new("GeometryNodeStoreNamedAttribute")
        n.data_type, n.domain = dtype, domain
        n.inputs["Name"].default_value = name
        L.new(geo, n.inputs["Geometry"])
        L.new(value, n.inputs["Value"])
        return n.outputs["Geometry"]

    dup = N.new("GeometryNodeDuplicateElements")
    dup.domain = "SPLINE"
    L.new(gi.outputs["Geometry"], dup.inputs["Geometry"])
    L.new(math("ROUND", math("MULTIPLY", named("hp_n", "INT"), gi.outputs["Amount"])), dup.inputs["Amount"])
    geo = dup.outputs["Geometry"]
    # per copy (curve domain, so every point of a strand reads the same numbers)
    for name, lo, hi, off in (("hp_a", -1.0, 1.0, 1), ("hp_b", -1.0, 1.0, 2), ("hp_rand", 0.0, 1.0, 3),
                              ("hp_f", 0.0, 1.0, 4), ("hp_fa", 0.0, 6.2832, 5), ("hp_len", 0.0, 1.0, 6),
                              ("hp_root", 0.0, 1.0, 7)):
        geo = store(geo, name, rand(lo, hi, off))
    a = named("hp_a", "FLOAT")
    # a^Edge keeps strands off the lens's thin rim (Edge > 1) or pushes them to it (< 1)
    a_s = math("MULTIPLY", math("SIGN", a), math("POWER", math("ABSOLUTE", a), gi.outputs["Edge"]))
    b_s = math("MULTIPLY", named("hp_b", "FLOAT"), math("SUBTRACT", 1.0, math("MULTIPLY", a_s, a_s)))
    side, out = named("hp_side", "FLOAT_VECTOR"), named("hp_out", "FLOAT_VECTOR")
    off = vmath("ADD", vmath("SCALE", side, scale=a_s), vmath("SCALE", out, scale=b_s))
    # fly-aways: some copies drift off the lock toward the tip, in their own direction round it
    par = N.new("GeometryNodeSplineParameter")
    t = par.outputs["Factor"]
    fly = math("LESS_THAN", named("hp_f", "FLOAT"), gi.outputs["Flyaway"])
    fa = named("hp_fa", "FLOAT")
    fdir = vmath("ADD", vmath("SCALE", vmath("NORMALIZE", side), scale=math("COSINE", fa)),
                 vmath("SCALE", vmath("NORMALIZE", out), scale=math("ABSOLUTE", math("SINE", fa))))
    famt = math("MULTIPLY", math("MULTIPLY", fly, gi.outputs["Flyaway Distance"]), math("POWER", t, 1.6))
    off = vmath("ADD", off, vmath("SCALE", fdir, scale=famt))
    sp = N.new("GeometryNodeSetPosition")
    L.new(geo, sp.inputs["Geometry"])
    L.new(off, sp.inputs["Offset"])
    # lengths: every strand ends (and starts) somewhere of its own, so tips thin out and roots don't line up
    trim = N.new("GeometryNodeTrimCurve")
    trim.mode = "FACTOR"
    L.new(sp.outputs["Geometry"], trim.inputs["Curve"])
    ln = named("hp_len", "FLOAT")
    L.new(math("MULTIPLY", named("hp_root", "FLOAT"), gi.outputs["Roots"]), _sock(trim, "Start", "VALUE"))
    L.new(math("SUBTRACT", 1.0, math("MULTIPLY", math("MULTIPLY", ln, ln), gi.outputs["Tips"])),
          _sock(trim, "End", "VALUE"))
    L.new(trim.outputs["Curve"], go.inputs["Geometry"])
    return ng


def _set(mod, vals: dict):
    """Modifier inputs by socket name ("Name" or "Name:Type" where a group has two of a name); a value {"attribute":
    name} reads a named attribute (a field input)."""
    for it in mod.node_group.interface.items_tree:
        if it.item_type != "SOCKET" or it.in_out != "INPUT":
            continue
        key = f"{it.name}:{it.socket_type.replace('NodeSocket', '')}"
        key = key if key in vals else it.name
        if key not in vals:
            continue
        v = vals[key]
        if isinstance(v, dict) and "attribute" in v:
            mod[it.identifier + "_use_attribute"] = True
            mod[it.identifier + "_attribute_name"] = v["attribute"]
        elif isinstance(v, dict) and "object" in v:
            mod[it.identifier] = bpy.data.objects.get(v["object"])
        elif isinstance(v, dict) and "part" in v:
            mod[it.identifier] = next((o for o in bpy.data.objects if o.type == "MESH" and o.get("hp_part") == v["part"]
                                       and not o.name.startswith("hair_")), None)
        elif isinstance(v, (list, tuple)):
            mod[it.identifier] = tuple(v)
        else:
            cur = None
            try:
                cur = mod[it.identifier]
            except Exception:  # noqa: BLE001
                pass
            mod[it.identifier] = (int(v) if isinstance(cur, int) and not isinstance(cur, bool) and not isinstance(v, str)
                                  else v)


def get_inputs(mod) -> dict:
    out = {}
    for it in mod.node_group.interface.items_tree:
        if it.item_type != "SOCKET" or it.in_out != "INPUT" or it.socket_type in (
                "NodeSocketGeometry", "NodeSocketObject", "NodeSocketImage", "NodeSocketMaterial", "NodeSocketMenu"):
            continue
        try:
            v = mod[it.identifier]
        except Exception:  # noqa: BLE001
            continue
        if isinstance(v, (int, float, bool)):
            out[it.name] = v
    return out


def _coll():
    c = bpy.data.collections.get("hair")
    if c is None:
        c = bpy.data.collections.new("hair")
        bpy.context.scene.collection.children.link(c)
    return c


def _drop(name):
    ob = bpy.data.objects.get(name)
    if ob is None:
        return
    data = ob.data
    bpy.data.objects.remove(ob)
    if data is not None and data.users == 0:
        (bpy.data.meshes if isinstance(data, bpy.types.Mesh) else bpy.data.hair_curves).remove(data)


def scalp_object(path: str):
    z = np.load(path)
    V, F = z["verts"], z["faces"]
    me = bpy.data.meshes.new("hair_scalp")
    me.vertices.add(len(V))
    me.vertices.foreach_set("co", V.astype(np.float32).ravel())
    me.loops.add(F.size)
    me.loops.foreach_set("vertex_index", F.astype(np.int32).ravel())
    me.polygons.add(len(F))
    me.polygons.foreach_set("loop_start", np.arange(0, F.size, F.shape[1], dtype=np.int32))
    me.polygons.foreach_set("loop_total", np.full(len(F), F.shape[1], np.int32))
    me.update()
    uv = me.uv_layers.new(name="UVMap")
    uv.data.foreach_set("uv", z["uv"].astype(np.float32).ravel())
    for k in ("hp_density",):
        at = me.attributes.new(k, "FLOAT", "POINT")
        at.data.foreach_set("value", z[k].astype(np.float32))
    rest = me.attributes.new("rest_position", "FLOAT_VECTOR", "POINT")
    rest.data.foreach_set("vector", V.astype(np.float32).ravel())
    me.shade_smooth()
    ob = bpy.data.objects.new("hair_scalp", me)
    ob["hp_hair_scalp"] = 1
    ob.hide_render = True
    ob.display_type = "WIRE"
    _coll().objects.link(ob)
    return ob


def _stamp(a) -> str:
    return hashlib.sha1(np.round(np.asarray(a, np.float64), 5).tobytes()).hexdigest()[:16]


def curves_object(name: str, path: str, scalp, mat):
    """A Hair Curves object from a guides npz (counts, pts, per-point side/out, per-curve n, uv)."""
    z = np.load(path, allow_pickle=False)
    counts, P = z["counts"].astype(int), z["pts"].astype(np.float32)
    cu = bpy.data.hair_curves.new(name)
    cu.add_curves([int(c) for c in counts])
    cu.attributes["position"].data.foreach_set("vector", P.ravel())
    for k, dt, dom, field in (("side", "FLOAT_VECTOR", "POINT", "vector"), ("out", "FLOAT_VECTOR", "POINT", "vector"),
                              ("n", "INT", "CURVE", "value"), ("lock", "INT", "CURVE", "value"),
                              ("tile", "INT", "CURVE", "value")):
        if k in z.files:
            at = cu.attributes.new("hp_" + k, dt, dom)
            at.data.foreach_set(field, z[k].astype(np.float32 if dt == "FLOAT_VECTOR" else np.int32).ravel())
    if "uv" in z.files:
        at = cu.attributes.new("surface_uv_coordinate", "FLOAT2", "CURVE")
        at.data.foreach_set("vector", z["uv"].astype(np.float32).ravel())
    cu.surface = scalp
    cu.surface_uv_map = "UVMap"
    cu.materials.append(mat)
    ob = bpy.data.objects.new(name, cu)
    ob["hp_strands"] = 1
    ob["hp_names"] = json.dumps([str(n) for n in z["names"]]) if "names" in z.files else "[]"
    ob["hp_counts"] = json.dumps([int(c) for c in counts])
    ob["hp_set"] = json.dumps([_stamp(q) for q in np.split(P, np.cumsum(counts)[:-1])])
    _coll().objects.link(ob)
    return ob


def add_stack(ob, stack: list):
    """The modifier stack: [[group name, {inputs}], ...] in order; stamped with what was written (pull compares)."""
    groups = essentials()
    wrote = {}
    for i, (gname, vals) in enumerate(stack):
        ng = lens_group() if gname == LENS else groups[gname]
        mod = ob.modifiers.new(gname, "NODES")
        mod.node_group = ng
        _set(mod, vals)
        wrote[mod.name] = get_inputs(mod)
    ob["hp_stack"] = json.dumps(wrote, default=float)


def _lin(c):
    if isinstance(c, str):
        c = [int(c.lstrip("#")[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    return [x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in c]


def material(look: dict):
    """One material, two outputs: Cycles gets the Principled Hair BSDF (the truthful look), EEVEE a Principled
    built for strands (the hair BSDF draws near black there): colour root -> tip, a value per strand, an anisotropic
    highlight along the strand."""
    m = bpy.data.materials.get("hp_strand") or bpy.data.materials.new("hp_strand")
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    N, L = nt.nodes, nt.links
    info = N.new("ShaderNodeHairInfo")
    lit, gap = _lin(look.get("lit", "#56352d")), _lin(look.get("gap", "#221310"))
    tip = _lin(look.get("tip", "#7a5038"))
    grey = _lin(look.get("grey", "#9a948d"))
    # colour along the strand: darker at the root, the tip colour by tip_amount
    ramp = N.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.0
    ramp.color_ramp.elements[0].color = (*[g * 0.5 + c * 0.5 for g, c in zip(gap, lit)], 1)
    ramp.color_ramp.elements[1].position = max(0.02, float(look.get("root", 0.12)))
    ramp.color_ramp.elements[1].color = (*lit, 1)
    ta = float(look.get("tip_amount", 0.0))
    e = ramp.color_ramp.elements.new(1.0)
    e.color = (*[a * (1 - ta) + b * ta for a, b in zip(lit, tip)], 1)
    L.new(info.outputs["Intercept"], ramp.inputs["Fac"])
    # per strand value
    hsv = N.new("ShaderNodeHueSaturation")
    mr = N.new("ShaderNodeMapRange")
    vary = float(look.get("vary", 0.25))
    mr.inputs["To Min"].default_value, mr.inputs["To Max"].default_value = 1 - 0.6 * vary, 1 + 0.6 * vary
    L.new(info.outputs["Random"], mr.inputs["Value"])
    L.new(mr.outputs[0], hsv.inputs["Value"])
    L.new(ramp.outputs["Color"], hsv.inputs["Color"])
    col = hsv.outputs["Color"]
    ga = float(look.get("grey_amount", 0.0))
    if ga > 0:  # grey hairs: a share of the strands
        mix = N.new("ShaderNodeMix")
        mix.data_type = "RGBA"
        lt = N.new("ShaderNodeMath")
        lt.operation = "LESS_THAN"
        L.new(info.outputs["Random"], lt.inputs[0])
        lt.inputs[1].default_value = ga
        L.new(lt.outputs[0], mix.inputs["Factor"])
        L.new(col, mix.inputs["A"])
        mix.inputs["B"].default_value = (*grey, 1)
        col = mix.outputs["Result"]
    # Cycles
    oc = N.new("ShaderNodeOutputMaterial")
    oc.target = "CYCLES"
    hb = N.new("ShaderNodeBsdfHairPrincipled")
    hb.parametrization = "COLOR"
    L.new(col, hb.inputs["Color"])
    hb.inputs["Roughness"].default_value = float(look.get("roughness", 0.42)) * 0.75
    hb.inputs["Radial Roughness"].default_value = 0.4
    hb.inputs["Random Roughness"].default_value = 0.2
    hb.inputs["Coat"].default_value = 0.0
    L.new(hb.outputs[0], oc.inputs["Surface"])
    # EEVEE: strands are ribbons facing the camera; a rough dielectric with a soft sheen, darker inside the mass
    oe = N.new("ShaderNodeOutputMaterial")
    oe.target = "EEVEE"
    pb = N.new("ShaderNodeBsdfPrincipled")
    bright = N.new("ShaderNodeMix")
    bright.data_type = "RGBA"
    bright.blend_type = "MULTIPLY"
    bright.inputs["Factor"].default_value = 1.0
    L.new(col, bright.inputs["A"])
    g = float(look.get("eevee_gain", 1.6))  # the hair BSDF's multiple scattering brightens a mass of strands; a
    bright.inputs["B"].default_value = (g, g, g, 1)  # plain diffuse strand doesn't: lifted to match Cycles
    L.new(bright.outputs["Result"], pb.inputs["Base Color"])
    pb.inputs["Roughness"].default_value = float(look.get("roughness", 0.42))
    pb.inputs["Specular IOR Level"].default_value = float(look.get("specular", 0.5)) * 0.6
    pb.inputs["Anisotropic"].default_value = 0.0
    try:
        pb.inputs["Sheen Weight"].default_value = float(look.get("sheen_amount", 0.45)) * 0.3
        pb.inputs["Sheen Tint"].default_value = (*_lin(look.get("sheen", "#86524a")), 1)
    except KeyError:
        pass
    L.new(pb.outputs[0], oe.inputs["Surface"])
    m["hp_look"] = json.dumps(look, sort_keys=True)
    return m


def clear():
    for n in OBJECTS + ("hair_band",):
        _drop(n)


def show(sd: dict):
    """Apply a strands job (hair_strands.job): the scalp, the guide objects with their stacks."""
    clear()
    mat = material(sd["look"])
    scalp = scalp_object(sd["scalp"])
    made = []
    for grp in sd["groups"]:
        ob = curves_object(grp["name"], grp["guides"], scalp, mat)
        add_stack(ob, grp["stack"])
        made.append(grp["name"])
    if sd.get("band"):
        z = np.load(sd["band"])
        me = bpy.data.meshes.new("hair_band")
        me.from_pydata([tuple(map(float, v)) for v in z["verts"]], [], [tuple(map(int, f)) for f in z["tris"]])
        me.shade_smooth()
        bm = bpy.data.materials.get("hp_band") or bpy.data.materials.new("hp_band")
        bm.use_nodes = True
        b = next(n for n in bm.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
        b.inputs["Base Color"].default_value = (*_lin(sd["look"].get("band", "#23252b")), 1)
        b.inputs["Roughness"].default_value = 0.7
        me.materials.append(bm)
        ob = bpy.data.objects.new("hair_band", me)
        ob["hp_band"] = 1
        _coll().objects.link(ob)
    sc = bpy.context.scene
    try:
        sc.render.hair_type = "STRAND"
        sc.render.hair_subdiv = 1
    except Exception:  # noqa: BLE001
        pass
    try:
        sc.cycles.use_curves = True
    except Exception:  # noqa: BLE001
        pass
    return made


def stats() -> dict:
    dg = bpy.context.evaluated_depsgraph_get()
    out = {}
    for n in OBJECTS[:3]:
        ob = bpy.data.objects.get(n)
        if ob is None:
            continue
        d = ob.evaluated_get(dg).data
        out[n] = {"guides": len(ob.data.curves), "strands": len(d.curves), "points": len(d.points)}
    return out


def points(names: list | None = None, every: int = 3):
    """Evaluated strand points (world, every n-th), and which object each belongs to."""
    dg = bpy.context.evaluated_depsgraph_get()
    out = []
    for n in OBJECTS[:3]:
        ob = bpy.data.objects.get(n)
        if ob is None:
            continue
        d = ob.evaluated_get(dg).data
        a = np.empty(len(d.points) * 3, np.float32)
        d.attributes["position"].data.foreach_get("vector", a)
        a = a.reshape(-1, 3)[::every]
        out.append(a)
        if names is not None:
            names += [n] * len(a)
    return np.concatenate(out) if out else np.zeros((0, 3), np.float32)


def dump(path: str, every: int = 1):
    """Every evaluated strand (points, counts per curve, lock index, object) to an npz: the cards and the atlas bake
    are made from these."""
    dg = bpy.context.evaluated_depsgraph_get()
    P, C, K, O, R = [], [], [], [], []
    for oi, n in enumerate(OBJECTS[:3]):
        ob = bpy.data.objects.get(n)
        if ob is None:
            continue
        d = ob.evaluated_get(dg).data
        a = np.empty(len(d.points) * 3, np.float32)
        d.attributes["position"].data.foreach_get("vector", a)
        cnt = np.empty(len(d.curves), np.int32)
        d.curves.foreach_get("points_length", cnt)
        lk = np.zeros(len(d.curves), np.int32)
        if "hp_lock" in d.attributes and d.attributes["hp_lock"].domain == "CURVE":
            d.attributes["hp_lock"].data.foreach_get("value", lk)
        rd = np.zeros(len(d.curves), np.float32)
        if "hp_rand" in d.attributes and d.attributes["hp_rand"].domain == "CURVE":
            d.attributes["hp_rand"].data.foreach_get("value", rd)
        P.append(a.reshape(-1, 3))
        C.append(cnt)
        K.append(lk)
        R.append(rd)
        O.append(np.full(len(cnt), oi, np.int32))
    np.savez(path, pts=np.concatenate(P), counts=np.concatenate(C), lock=np.concatenate(K), obj=np.concatenate(O),
             rand=np.concatenate(R))


def _emit(name, rgb):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    o = nt.nodes.new("ShaderNodeOutputMaterial")
    e = nt.nodes.new("ShaderNodeEmission")
    e.inputs["Color"].default_value = (*rgb, 1.0)
    nt.links.new(e.outputs[0], o.inputs["Surface"])
    return m


def id_pass():
    """Strands green, the scalp inside the hairline red (it is shown for this pass: red pixels = scalp seen through
    the hair), all else black."""
    g, r = _emit("hp_id_lock", (0, 1, 0)), _emit("hp_id_mass", (1, 0, 0))
    for n in OBJECTS[:3]:
        ob = bpy.data.objects.get(n)
        if ob is not None:
            ob.data.materials.clear()
            ob.data.materials.append(g)
    sc = bpy.data.objects.get("hair_scalp")
    if sc is not None:
        sc.hide_render = False
        sc.data.materials.clear()
        sc.data.materials.append(r)
    b = bpy.data.objects.get("hair_band")
    if b is not None:
        b.data.materials.clear()
        b.data.materials.append(g)


def clay():
    m = bpy.data.materials.get("hp_strand")
    if m is None:
        return
    nt = m.node_tree
    nt.nodes.clear()
    o = nt.nodes.new("ShaderNodeOutputMaterial")
    b = nt.nodes.new("ShaderNodeBsdfPrincipled")
    b.inputs["Base Color"].default_value = (0.42, 0.33, 0.28, 1.0)
    b.inputs["Roughness"].default_value = 0.6
    nt.links.new(b.outputs[0], o.inputs["Surface"])


def read() -> dict:
    """What a person changed: guide curves whose points moved from the stamp the sync wrote (their new points), added
    and deleted curves, and modifier numbers that moved. {object: {"moved": {index: pts}, "names", "stack": {...}}}."""
    out = {}
    for n in OBJECTS[:3]:
        ob = bpy.data.objects.get(n)
        if ob is None or not ob.get("hp_strands"):
            continue
        cu = ob.data
        cnt = np.empty(len(cu.curves), np.int32)
        cu.curves.foreach_get("points_length", cnt)
        a = np.empty(len(cu.points) * 3, np.float32)
        cu.attributes["position"].data.foreach_get("vector", a)
        M = np.array(ob.matrix_world, np.float32)
        a = a.reshape(-1, 3) @ M[:3, :3].T + M[:3, 3]
        parts = np.split(a, np.cumsum(cnt)[:-1]) if len(cnt) else []
        stamps = json.loads(ob.get("hp_set") or "[]")
        names = json.loads(ob.get("hp_names") or "[]")
        moved, added = {}, []
        for i, q in enumerate(parts):
            if i < len(stamps):
                if _stamp(q) != stamps[i]:
                    moved[names[i] if i < len(names) else str(i)] = q.tolist()
            else:
                added.append(q.tolist())
        was = json.loads(ob.get("hp_stack") or "{}")
        stack = {}
        for mod in ob.modifiers:
            if mod.type != "NODES" or mod.node_group is None or mod.name not in was:
                continue
            now = get_inputs(mod)
            ch = {k: v for k, v in now.items() if k in was[mod.name] and abs(float(v) - float(was[mod.name][k])) > 1e-7}
            if ch:
                stack[mod.name] = ch
        out[n] = {"moved": moved, "added": added, "removed": max(0, len(stamps) - len(parts)), "stack": stack}
    return out
