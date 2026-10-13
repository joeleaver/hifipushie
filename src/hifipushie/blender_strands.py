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
VERSION = 17  # bump when the lens group changes
ESSENTIALS = ["Clump Hair Curves", "Curl Hair Curves", "Frizz Hair Curves", "Hair Curves Noise",
              "Shrinkwrap Hair Curves", "Set Hair Curve Profile", "Braid Hair Curves", "Interpolate Hair Curves",
              "Trim Hair Curves", "Smooth Hair Curves", "Duplicate Hair Curves"]
OBJECTS = ("hair_guides", "hair_guides_free", "hair_guides_wisp", "hair_under", "hair_scalp", "hair_collide")


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
                                  ("Roots", "NodeSocketFloat", 0.03, 0.0, 1.0), ("Flyaway", "NodeSocketFloat", 0.05, 0.0, 1.0),
                                  ("Flyaway Distance", "NodeSocketFloat", 1.0, 0.0, 4.0),
                                  ("Edge", "NodeSocketFloat", 1.0, 0.2, 3.0),
                                  ("Clump", "NodeSocketFloat", 0.4, 0.0, 1.0), ("Clump Shape", "NodeSocketFloat", 0.6, 0.0, 1.0),
                                  ("Tip Spread", "NodeSocketFloat", 0.3, 0.0, 1.0), ("Wave", "NodeSocketFloat", 0.0, 0.0, 0.05),
                                  ("Wavelength", "NodeSocketFloat", 0.07, 0.005, 1.0), ("Curl", "NodeSocketFloat", 0.0, 0.0, 1.0),
                                  ("Loose", "NodeSocketFloat", 0.001, 0.0, 0.02),
                                  ("Wave Random", "NodeSocketFloat", 0.3, 0.0, 1.0),
                                  ("Stray", "NodeSocketFloat", 0.5, 0.0, 1.0),
                                  ("Halo", "NodeSocketFloat", 0.0, 0.0, 1.0),
                                  ("Halo Distance", "NodeSocketFloat", 0.012, 0.0, 0.05),
                                  ("Halo Length", "NodeSocketFloat", 0.05, 0.005, 0.3),
                                  ("Fine", "NodeSocketFloat", 0.0, 0.0, 1.0),
                                  ("Seed", "NodeSocketInt", 0, 0, 10000)):
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
                              ("hp_root", 0.0, 1.0, 7), ("hp_cs", 0.0, 1.0, 8)):
        geo = store(geo, name, rand(lo, hi, off))
    a = named("hp_a", "FLOAT")
    par = N.new("GeometryNodeSplineParameter")
    t = par.outputs["Factor"]
    slen = N.new("GeometryNodeSplineLength").outputs["Length"]
    s_m = math("MULTIPLY", t, slen)  # metres along the lock
    side, out = named("hp_side", "FLOAT_VECTOR"), named("hp_out", "FLOAT_VECTOR")
    side_n, out_n = vmath("NORMALIZE", side), vmath("NORMALIZE", out)
    # sub clumps: the lock's width is cut into hp_k pieces; each strand belongs to the piece it starts in and is
    # drawn toward that piece's own line as it runs out (Clump x t^shape), then lets go again at the very tip
    K = math("MAXIMUM", named("hp_k", "FLOAT"), 1.0)
    kf = math("MINIMUM", math("FLOOR", math("MULTIPLY", math("MULTIPLY", math("ADD", a, 1.0), 0.5), K)),
              math("SUBTRACT", K, 1.0))
    cid = math("ADD", math("MULTIPLY", named("hp_lock", "INT"), 131.0), kf)

    def crand(lo, hi, seed_off):  # a number per sub clump
        n = N.new("FunctionNodeRandomValue")
        n.data_type = "FLOAT"
        _sock(n, "Min", "VALUE").default_value = lo
        _sock(n, "Max", "VALUE").default_value = hi
        L.new(cid, n.inputs["ID"])
        L.new(math("ADD", gi.outputs["Seed"], float(seed_off)), n.inputs["Seed"])
        return _sock(n, "Value", "VALUE", out=True)

    ac = math("SUBTRACT", math("MULTIPLY", math("DIVIDE", math("ADD", math("ADD", kf, 0.5), crand(-0.3, 0.3, 11)), K),
                               2.0), 1.0)
    # shape 0: gathered from the root (a rope) .. 1: only toward the tip
    expo = math("ADD", 0.35, math("MULTIPLY", gi.outputs["Clump Shape"], 2.65))
    open_tip = math("SUBTRACT", 1.0, math("MULTIPLY", gi.outputs["Tip Spread"],
                                          math("POWER", math("MAXIMUM", math("MULTIPLY", math("SUBTRACT", t, 0.7), 3.3333), 0.0), 2.0)))
    # (hp_clx: a lock's own clump, as what it adds to the object's: (lock - object) / object; absent = 0)
    clump_l = math("MINIMUM", math("MULTIPLY", gi.outputs["Clump"], math("ADD", 1.0, named("hp_clx", "FLOAT"))), 0.95)
    c = math("MULTIPLY", math("MULTIPLY", clump_l, math("POWER", t, expo)), open_tip)
    # not every strand joins its clump as hard: with all of them on one line a clump is a rope with dark air between
    # it and the next (pasta); strays fill between the clumps
    cs = named("hp_cs", "FLOAT")
    c = math("MULTIPLY", c, math("SUBTRACT", 1.0, math("MULTIPLY", gi.outputs["Stray"], math("MULTIPLY", cs, cs))))
    a_e = math("ADD", a, math("MULTIPLY", math("SUBTRACT", ac, a), c))
    # a^Edge keeps strands off the lens's thin rim (Edge > 1) or pushes them to it (< 1)
    # (hp_ex: a lock's own Edge, as what it adds to the object's: (lock - object) / object; absent = 0)
    a_s = math("MULTIPLY", math("SIGN", a_e), math("POWER", math("ABSOLUTE", a_e),
                                                   math("MULTIPLY", gi.outputs["Edge"], math("ADD", 1.0, named("hp_ex", "FLOAT")))))
    bb = named("hp_b", "FLOAT")
    b_e = math("ADD", bb, math("MULTIPLY", math("SUBTRACT", crand(-0.7, 0.7, 12), bb), c))
    b_s = math("MULTIPLY", b_e, math("SUBTRACT", 1.0, math("MULTIPLY", a_s, a_s)))
    off = vmath("ADD", vmath("SCALE", side, scale=a_s), vmath("SCALE", out, scale=b_s))
    # each sub clump swings on its own (the lock's own wave is in the guide): loose hair is clumps out of step
    env = math("MINIMUM", math("DIVIDE", s_m, 0.03), 1.0)
    env = math("MULTIPLY", math("MULTIPLY", env, env), math("SUBTRACT", 3.0, math("MULTIPLY", env, 2.0)))
    # (sub clumps swing nearly in step, Wave Random apart: a tail moves as sheets of hair; every clump on its own
    # phase and wavelength is pasta. hp_ws / hp_wl: a thin wisp swings less and slower than a lock)
    wr_ = gi.outputs["Wave Random"]
    wl = math("MULTIPLY", math("MULTIPLY", gi.outputs["Wavelength"], named("hp_wl", "FLOAT")),
              math("ADD", 1.0, math("MULTIPLY", math("MULTIPLY", wr_, 0.25), crand(-1.0, 1.0, 13))))
    ph = math("ADD", math("DIVIDE", math("MULTIPLY", s_m, 6.2832), wl),
              math("MULTIPLY", math("MULTIPLY", wr_, 3.1416), crand(-1.0, 1.0, 14)))
    amp = math("MULTIPLY", math("MULTIPLY", math("MULTIPLY", gi.outputs["Wave"], named("hp_ws", "FLOAT")),
                                math("ADD", 1.0, math("MULTIPLY", math("MULTIPLY", wr_, 0.7), crand(-1.0, 0.4, 15)))), env)
    off = vmath("ADD", off, vmath("SCALE", side_n, scale=math("MULTIPLY", amp, math("SINE", ph))))
    off = vmath("ADD", off, vmath("SCALE", out_n, scale=math("MULTIPLY", math("MULTIPLY", amp, gi.outputs["Curl"]),
                                                               math("COSINE", ph))))
    # single strands wander a little off their clump, slowly along the strand (not frizz: a different line)
    wr = named("hp_fa", "FLOAT")
    wph = math("ADD", math("DIVIDE", math("MULTIPLY", s_m, 6.2832), math("MULTIPLY", math("MULTIPLY", gi.outputs["Wavelength"], named("hp_wl", "FLOAT")), 0.61)),
               math("MULTIPLY", wr, 7.0))
    wam = math("MULTIPLY", math("MULTIPLY", gi.outputs["Loose"], env), math("ADD", 0.3, t))
    off = vmath("ADD", off, vmath("SCALE", side_n, scale=math("MULTIPLY", wam, math("SINE", wph))))
    off = vmath("ADD", off, vmath("SCALE", out_n, scale=math("MULTIPLY", wam, math("MULTIPLY", 0.6, math("COSINE", math("MULTIPLY", wph, 1.31))))))
    # fly-aways: some copies let go of the lock part way along and drift off it, bending as they go
    fly = math("LESS_THAN", named("hp_f", "FLOAT"), gi.outputs["Flyaway"])
    fa = named("hp_fa", "FLOAT")
    t0 = math("MULTIPLY", named("hp_root", "FLOAT"), 0.6)  # where it lets go
    ft = math("MAXIMUM", math("DIVIDE", math("SUBTRACT", t, t0), math("SUBTRACT", 1.0, t0)), 0.0)
    fang = math("ADD", fa, math("MULTIPLY", ft, 2.2))
    fdir = vmath("ADD", vmath("SCALE", side_n, scale=math("COSINE", fang)),
                 vmath("SCALE", out_n, scale=math("ADD", 0.25, math("ABSOLUTE", math("SINE", fang)))))
    famt = math("MULTIPLY", math("MULTIPLY", math("MULTIPLY", fly, math("MULTIPLY", gi.outputs["Flyaway Distance"],
                                                                         named("hp_fd", "FLOAT"))),
                                 math("ADD", 0.3, named("hp_rand", "FLOAT"))), math("POWER", ft, 1.7))
    off = vmath("ADD", off, vmath("SCALE", fdir, scale=famt))
    # the halo: short broken hairs. A copy starts anywhere along the lock, runs Halo Length x (0.4..1.4) and, over
    # that run, lifts off the lock's outer side and curls sideways: it ends in the air (a fly-away keeps its lock's
    # whole length and its end)
    halo = math("GREATER_THAN", named("hp_f", "FLOAT"), math("SUBTRACT", 1.0, gi.outputs["Halo"]))
    h0 = math("MULTIPLY", named("hp_root", "FLOAT"), 0.8)
    hspan = math("MINIMUM", math("DIVIDE", math("MULTIPLY", gi.outputs["Halo Length"],
                                                 math("ADD", 0.4, named("hp_len", "FLOAT"))),
                                 math("MAXIMUM", slen, 0.001)), 1.0)
    h1 = math("MINIMUM", math("ADD", h0, hspan), 1.0)
    htau = math("MINIMUM", math("MAXIMUM", math("DIVIDE", math("SUBTRACT", t, h0), math("MAXIMUM", hspan, 0.001)), 0.0), 1.0)
    hd = math("MULTIPLY", math("MULTIPLY", halo, gi.outputs["Halo Distance"]), math("ADD", 0.3, named("hp_rand", "FLOAT")))
    hang = math("ADD", fa, math("MULTIPLY", htau, 3.6))
    hoff = vmath("ADD", vmath("SCALE", out_n, scale=math("MULTIPLY", hd, math("POWER", htau, 1.5))),
                 vmath("SCALE", side_n, scale=math("MULTIPLY", math("MULTIPLY", hd, 0.7),
                                                   math("MULTIPLY", htau, math("SINE", hang)))))
    off = vmath("ADD", off, hoff)
    geo = store(geo, "hp_sub", kf)
    # single hairs (the halo, a lock of `hairs`): the EEVEE material draws them part transparent (a strand is never
    # drawn under a pixel wide: alone against skin or the backdrop, 0.08 mm hairs came out as 1 mm wires)
    # (hp_fn: a lock's own share, the hairline's thin rim; absent = 0)
    geo = store(geo, "hp_fine", math("MAXIMUM", math("MAXIMUM", halo, gi.outputs["Fine"]), named("hp_fn", "FLOAT")))
    geo = store(geo, "hp_cv", crand(0.0, 1.0, 17))  # a value per sub clump: the material's streaks
    # (hp_fly: the hairs that have LEFT the mass (fly-aways, the halo, an object of single hairs): the look's fly_light.
    # Not hp_fn, the hairline's thin rim: lightened, it was a grey veil over the forehead's corners, th_V75)
    geo = store(geo, "hp_fly", math("MAXIMUM", math("MAXIMUM", halo, gi.outputs["Fine"]), fly))
    # (tesshair7, the colour model: natural hair is never one colour) hp_ch: a second number per sub clump, (0, 1]:
    # which sub clumps are highlight ribbons (0 = an object without the lens: never); hp_lv: a number per LOCK,
    # -1..1: locks differ in lightness, and highlights gather on some locks
    # HIGHLIGHT RIBBONS by where the strand starts across its lock (hp_hk a lock = its width / 6 mm; absent = the sub
    # clumps), at TWO scales with random edges: many THIN ones (hp_ch, ~4 mm) and a few BROAD soft ones (hp_cb,
    # ~15 mm), each its own number in (0, 1]: evenly 6 mm wide they were regular pinstripes (th_V86). And hp_cm, a
    # value per ~1.5 mm of the lock's width, -1..1: strand-to-strand contrast that survives a pixel (single strands
    # average away at head size)
    hk_ = math("MAXIMUM", named("hp_hk", "FLOAT"), 0.0)
    hk_ = math("ADD", hk_, math("MULTIPLY", math("LESS_THAN", hk_, 0.5), K))
    x01 = math("MULTIPLY", math("ADD", a, 1.0), 0.5)

    def band(scale, seed_off, lo, hi, jitter):
        n_ = N.new("FunctionNodeRandomValue")
        n_.data_type = "FLOAT"
        _sock(n_, "Min", "VALUE").default_value = lo
        _sock(n_, "Max", "VALUE").default_value = hi
        # (the edges wander: + a number per lock, and the strand's own jitter so a band's rim is soft)
        pos = math("ADD", math("MULTIPLY", math("MULTIPLY", x01, hk_), scale),
                   math("ADD", math("MULTIPLY", named("hp_cs", "FLOAT"), jitter), lrand(0.0, 1.0, seed_off + 30)))
        L.new(math("ADD", math("MULTIPLY", named("hp_lock", "INT"), 131.0), math("FLOOR", pos)), n_.inputs["ID"])
        L.new(math("ADD", gi.outputs["Seed"], float(seed_off)), n_.inputs["Seed"])
        return _sock(n_, "Value", "VALUE", out=True)

    def lrand(lo, hi, seed_off):  # a number per lock
        n_ = N.new("FunctionNodeRandomValue")
        n_.data_type = "FLOAT"
        _sock(n_, "Min", "VALUE").default_value = lo
        _sock(n_, "Max", "VALUE").default_value = hi
        L.new(named("hp_lock", "INT"), n_.inputs["ID"])
        L.new(math("ADD", gi.outputs["Seed"], float(seed_off)), n_.inputs["Seed"])
        return _sock(n_, "Value", "VALUE", out=True)

    geo = store(geo, "hp_ch", band(1.5, 18, 0.0001, 1.0, 0.5))
    geo = store(geo, "hp_cb", band(0.4, 22, 0.0001, 1.0, 0.25))
    geo = store(geo, "hp_cm", band(4.0, 23, -1.0, 1.0, 0.0))
    lr = N.new("FunctionNodeRandomValue")
    lr.data_type = "FLOAT"
    _sock(lr, "Min", "VALUE").default_value = -1.0
    _sock(lr, "Max", "VALUE").default_value = 1.0
    L.new(named("hp_lock", "INT"), lr.inputs["ID"])
    L.new(math("ADD", gi.outputs["Seed"], 19.0), lr.inputs["Seed"])
    geo = store(geo, "hp_lv", _sock(lr, "Value", "VALUE", out=True))
    sp = N.new("GeometryNodeSetPosition")
    L.new(geo, sp.inputs["Geometry"])
    L.new(off, sp.inputs["Offset"])
    # lengths: every strand ends (and starts) somewhere of its own, so tips thin out and roots don't line up;
    # sub clumps differ in length too (the ragged end of a tail)
    trim = N.new("GeometryNodeTrimCurve")
    trim.mode = "FACTOR"
    L.new(sp.outputs["Geometry"], trim.inputs["Curve"])
    ln = named("hp_len", "FLOAT")
    cl = crand(0.0, 1.0, 16)
    start = math("MINIMUM", math("MULTIPLY", math("MULTIPLY", named("hp_root", "FLOAT"), gi.outputs["Roots"]),
                                 named("hp_rs", "FLOAT")), 0.6)
    L.new(math("ADD", start, math("MULTIPLY", halo, math("SUBTRACT", h0, start))), _sock(trim, "Start", "VALUE"))
    short = math("ADD", math("MULTIPLY", math("MULTIPLY", ln, ln), 0.6), math("MULTIPLY", math("MULTIPLY", cl, cl), 0.4))
    end = math("MAXIMUM", math("SUBTRACT", 1.0, math("MULTIPLY", math("MULTIPLY", short, gi.outputs["Tips"]),
                                                       named("hp_ts", "FLOAT"))), 0.08)
    L.new(math("ADD", end, math("MULTIPLY", halo, math("SUBTRACT", h1, end))), _sock(trim, "End", "VALUE"))
    L.new(trim.outputs["Curve"], go.inputs["Geometry"])
    return ng


PROFILE = "hp_profile"


def profile_group():
    """`hp_profile`: a strand's radius along it: Radius, thinner at the very root (Root x) and tapering over the last
    `Taper` of its length to Tip x (a hair that was never cut ends in a point; cut hair is blunt: Tip 1)."""
    ng = bpy.data.node_groups.get(PROFILE)
    if ng is not None and ng.get("hp_version") == VERSION:
        return ng
    if ng is not None:
        ng.name = PROFILE + "_old"
    ng = bpy.data.node_groups.new(PROFILE, "GeometryNodeTree")
    ng["hp_version"] = VERSION
    ng.is_modifier = True
    it = ng.interface
    it.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    it.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    for name, dv, lo, hi in (("Radius", 0.00005, 0.0, 0.01), ("Tip", 0.25, 0.0, 1.0), ("Taper", 0.3, 0.01, 1.0),
                             ("Root", 0.8, 0.0, 1.0)):
        sk = it.new_socket(name, in_out="INPUT", socket_type="NodeSocketFloat")
        sk.default_value, sk.min_value, sk.max_value = dv, lo, hi
    N, L = ng.nodes, ng.links
    gi, go = N.new("NodeGroupInput"), N.new("NodeGroupOutput")

    def math(op, a, b=None):
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

    t = N.new("GeometryNodeSplineParameter").outputs["Factor"]
    x = math("MINIMUM", math("MAXIMUM", math("DIVIDE", math("SUBTRACT", t, math("SUBTRACT", 1.0, gi.outputs["Taper"])),
                                             gi.outputs["Taper"]), 0.0), 1.0)
    tip = math("ADD", 1.0, math("MULTIPLY", math("SUBTRACT", gi.outputs["Tip"], 1.0), math("MULTIPLY", x, x)))
    r0 = math("MINIMUM", math("DIVIDE", t, 0.06), 1.0)
    root = math("ADD", gi.outputs["Root"], math("MULTIPLY", math("SUBTRACT", 1.0, gi.outputs["Root"]), r0))
    sr = N.new("GeometryNodeSetCurveRadius")
    L.new(gi.outputs["Geometry"], sr.inputs[0])
    L.new(math("MULTIPLY", math("MULTIPLY", gi.outputs["Radius"], tip), root), sr.inputs["Radius"])
    L.new(sr.outputs[0], go.inputs["Geometry"])
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


def scalp_object(path: str, tint=(0.02, 0.012, 0.008), amount: float = 0.85):
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
    ob.display_type = "WIRE"
    # the scalp under hair is in the hair's shadow and full of roots: tinted with the hair's dark colour by the
    # density (what a groomer paints on the skin, and what the game hair's cap texture is)
    m = bpy.data.materials.get("hp_scalp_tint") or bpy.data.materials.new("hp_scalp_tint")
    m.use_nodes = True
    nt = m.node_tree
    b = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
    b.inputs["Base Color"].default_value = (*tint, 1.0)
    b.inputs["Roughness"].default_value = 0.7
    b.inputs["Specular IOR Level"].default_value = 0.1
    at = nt.nodes.get("hp_density") or nt.nodes.new("ShaderNodeAttribute")
    at.name = at.attribute_name = "hp_density"
    mu = nt.nodes.get("hp_mul") or nt.nodes.new("ShaderNodeMath")
    mu.name, mu.operation = "hp_mul", "MULTIPLY"
    mu.inputs[1].default_value = float(amount)
    nt.links.new(at.outputs["Fac"], mu.inputs[0])
    nt.links.new(mu.outputs[0], b.inputs["Alpha"])
    m.surface_render_method = "DITHERED"
    me.materials.append(m)
    ob.visible_shadow = False
    if amount <= 0:
        ob.hide_render = True
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
                              ("k", "INT", "CURVE", "value"), ("fd", "FLOAT", "CURVE", "value"),
                              ("rs", "FLOAT", "CURVE", "value"), ("ts", "FLOAT", "CURVE", "value"),
                              ("ws", "FLOAT", "CURVE", "value"), ("wl", "FLOAT", "CURVE", "value"),
                              ("tile", "INT", "CURVE", "value"), ("gr", "FLOAT", "CURVE", "value"),
                              ("clx", "FLOAT", "CURVE", "value"), ("fn", "FLOAT", "CURVE", "value"),
                              ("ex", "FLOAT", "CURVE", "value"), ("a0", "FLOAT", "CURVE", "value"),
                              ("a1", "FLOAT", "CURVE", "value"), ("sh", "FLOAT", "CURVE", "value"),
                              ("hk", "FLOAT", "CURVE", "value"), ("su", "FLOAT", "CURVE", "value")):
        if k in z.files:
            at = cu.attributes.new("hp_" + k, dt, dom)
            at.data.foreach_set(field, z[k].astype(np.int32 if dt == "INT" else np.float32).ravel())
    if "uv" in z.files:
        at = cu.attributes.new("surface_uv_coordinate", "FLOAT2", "CURVE")
        at.data.foreach_set("vector", z["uv"].astype(np.float32).ravel())
    if scalp is not None:
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
        ng = lens_group() if gname == LENS else profile_group() if gname == PROFILE else groups[gname]
        mod = ob.modifiers.new(gname, "NODES")
        mod.node_group = ng
        _set(mod, vals)
        wrote[mod.name] = get_inputs(mod)
    ob["hp_stack"] = json.dumps(wrote, default=float)


def _lin(c):
    if isinstance(c, str):
        c = [int(c.lstrip("#")[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    return [x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in c]


EEVEE_SAT = 0.35  # EEVEE strands: the look colour's saturation kept (material(): what Cycles' hair BSDF leaves of it)


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
    rd_ = float(np.clip(look.get("root_dark", 0.5), 0.0, 1.0))  # how dark the root's first stretch is (1 = the gap colour)
    ramp.color_ramp.elements[0].color = (*[g * rd_ + c * (1 - rd_) for g, c in zip(gap, lit)], 1)
    ramp.color_ramp.elements[1].position = max(0.02, float(look.get("root", 0.12)))
    ramp.color_ramp.elements[1].color = (*lit, 1)
    ta = float(look.get("tip_amount", 0.0))
    e = ramp.color_ramp.elements.new(1.0)
    e.color = (*[a * (1 - ta) + b * ta for a, b in zip(lit, tip)], 1)
    # (a strand that does not start at the scalp (a tail's, hp_a0 > 0) has no dark root: it enters the ramp past it)
    a0n = N.new("ShaderNodeAttribute")
    a0n.attribute_name = "hp_a0"
    k0 = N.new("ShaderNodeMath")
    k0.operation = "MULTIPLY"
    k0.use_clamp = True
    L.new(a0n.outputs["Fac"], k0.inputs[0])
    k0.inputs[1].default_value = 100.0
    rpos = max(0.02, float(look.get("root", 0.12)))
    f1 = N.new("ShaderNodeMath")  # root + (1 - root) x intercept
    f1.operation = "MULTIPLY_ADD"
    L.new(info.outputs["Intercept"], f1.inputs[0])
    f1.inputs[1].default_value = 1.0 - rpos
    f1.inputs[2].default_value = rpos
    fm_ = N.new("ShaderNodeMix")
    fm_.data_type = "FLOAT"
    L.new(k0.outputs[0], fm_.inputs["Factor"])
    L.new(info.outputs["Intercept"], fm_.inputs[2])
    L.new(f1.outputs[0], fm_.inputs[3])
    # (... nor do the hairline's fine rim and single hairs (hp_fine): dark roots there were a hard dark edge at the
    # temples and black wires for wisps, th_W04)
    fnr = N.new("ShaderNodeAttribute")
    fnr.attribute_name = "hp_fine"
    fmx = N.new("ShaderNodeMath")
    fmx.operation = "MAXIMUM"
    L.new(fm_.outputs[0], fmx.inputs[0])
    L.new(fnr.outputs["Fac"], fmx.inputs[1])
    L.new(fmx.outputs[0], ramp.inputs["Fac"])
    # per strand value
    hsv = N.new("ShaderNodeHueSaturation")
    mr = N.new("ShaderNodeMapRange")
    vary = float(look.get("vary", 0.25))
    mr.inputs["To Min"].default_value, mr.inputs["To Max"].default_value = 1 - 1.0 * vary, 1 + 1.4 * vary
    # a value per strand and, stronger, per sub clump (hp_cv): hair reads as streaks of lighter and darker locks
    cv = N.new("ShaderNodeAttribute")
    cv.attribute_name = "hp_cv"
    mixv = N.new("ShaderNodeMath")
    mixv.operation = "ADD"
    half = N.new("ShaderNodeMath")
    half.operation = "MULTIPLY"
    half.inputs[1].default_value = 0.35
    L.new(info.outputs["Random"], half.inputs[0])
    half2 = N.new("ShaderNodeMath")
    half2.operation = "MULTIPLY"
    half2.inputs[1].default_value = 0.65
    L.new(cv.outputs["Fac"], half2.inputs[0])
    L.new(half.outputs[0], mixv.inputs[0])
    L.new(half2.outputs[0], mixv.inputs[1])
    L.new(mixv.outputs[0], mr.inputs["Value"])
    L.new(ramp.outputs["Color"], hsv.inputs["Color"])
    # THE COLOUR MODEL (tesshair7; Joe: "one flat brown"). What production grooms vary (Blender's Principled Hair
    # BSDF: melanin + Random Color per strand; MetaHuman's groom colour ramp root -> tip; Redshift's Hair Random Color
    # on hue / saturation / value; highlights keyed to the clump): here on the look colour's hue, saturation and value,
    #   variation   locks differ in lightness (hp_lv), sub clumps and strands a little in hue (with `vary`: value)
    #   sun         the hair's AGE lightens and warms it: by metres from the scalp (hp_a0..hp_a1: a tail starts where
    #               the gathered hair ended, not at a new root), full by 28 cm
    #   highlights  a share of sub clumps, gathered on some locks, is lighter and warmer from a few cm off the root
    #   fly_light   single fine hairs (fly-aways, the halo, wisps, the hairline's rim) read lighter
    def at_(name):
        n_ = N.new("ShaderNodeAttribute")
        n_.attribute_name = name
        return n_.outputs["Fac"]

    def M(op, a, b=None, c=None, clamp=False):
        n_ = N.new("ShaderNodeMath")
        n_.operation = op
        n_.use_clamp = clamp
        for i_, v_ in enumerate((a, b, c)):
            if v_ is None:
                continue
            if isinstance(v_, (int, float)):
                n_.inputs[i_].default_value = float(v_)
            else:
                L.new(v_, n_.inputs[i_])
        return n_.outputs[0]

    def smooth(x, lo, hi):
        n_ = N.new("ShaderNodeMapRange")
        n_.interpolation_type = "SMOOTHSTEP"
        L.new(x, n_.inputs["Value"])
        n_.inputs["From Min"].default_value, n_.inputs["From Max"].default_value = lo, hi
        n_.inputs["To Min"].default_value, n_.inputs["To Max"].default_value = 0.0, 1.0
        return n_.outputs["Result"]

    var = float(np.clip(look.get("variation", 0.4) or 0.0, 0.0, 1.0))
    sun = float(np.clip(look.get("sun", 0.2) or 0.0, 0.0, 1.0))
    hl = float(np.clip(look.get("highlights", 0.0) or 0.0, 0.0, 1.0))
    hlc = float(np.clip(look.get("highlight_contrast", 0.6), 0.0, 1.5))
    fly = float(np.clip(look.get("fly_light", 0.3) or 0.0, 0.0, 1.0))
    val, hue, sat = mr.outputs[0], None, None
    lv = at_("hp_lv")
    if var > 0:
        # (a lock is up to 4 cm wide: at +-20 % each a tail's locks read as flat painted slabs, th_V70. The contrast
        # belongs to the sub clumps (vary, highlights); locks only drift)
        val = M("MULTIPLY", val, M("MULTIPLY_ADD", lv, 0.14 * var, 1.0))
        val = M("MULTIPLY", val, M("MULTIPLY_ADD", at_("hp_cm"), 0.32 * var, 1.0))  # strand-to-strand, ~1.5 mm
        hue = M("MULTIPLY_ADD", M("SUBTRACT", cv.outputs["Fac"], 0.5), 0.02 * var, 0.5)
        sat = M("MULTIPLY_ADD", M("SUBTRACT", info.outputs["Random"], 0.5), 0.3 * var, 1.0)
    if sun > 0 or hl > 0:
        age = M("MULTIPLY_ADD", M("SUBTRACT", at_("hp_a1"), at_("hp_a0")), info.outputs["Intercept"], at_("hp_a0"))
        hue = hue if hue is not None else M("ADD", 0.5, 0.0)
        sat = sat if sat is not None else M("ADD", 1.0, 0.0)
        if sun > 0:
            fs = M("MULTIPLY", smooth(age, 0.0, 0.28), sun)
            # (+ 50 % value at sun 1, a little warmer: at + 60 % with + 25 % saturation a sun 0.9 tail was orange straw, th_V9a3)
            val = M("MULTIPLY", val, M("MULTIPLY_ADD", fs, 0.5, 1.0))
            hue = M("MULTIPLY_ADD", fs, 0.004, hue)  # (+ 0.012 turned a brown tail olive under EEVEE's desaturation, th_V84)
            sat = M("MULTIPLY_ADD", fs, 0.3, sat)  # (lighter AND warmer: at + 10 % the light lengths went ashy grey, th_W06)
        if hl > 0:
            # ribbons at two scales, gathered where the sun reaches (hp_su: the top layers, round the face, a tail's
            # outside) and a little on some locks: many thin ones, a few broad SOFT ones (lower contrast, a wide edge)
            su_ = M("MULTIPLY_ADD", at_("hp_su"), 0.5, M("MULTIPLY", lv, 0.08))
            ch_, cb_ = at_("hp_ch"), at_("hp_cb")
            thr_t, thr_b = 1.0 - 0.5 * hl, 1.0 - 0.28 * hl
            # (absent attributes are 0: an object without the lens never lights up)
            f_t = M("MULTIPLY", smooth(M("ADD", ch_, su_), thr_t, thr_t + 0.05), M("GREATER_THAN", ch_, 0.0))
            f_b = M("MULTIPLY", smooth(M("ADD", cb_, su_), thr_b, thr_b + 0.2), M("GREATER_THAN", cb_, 0.0))
            # (broad ribbons soft: at 0.6 they were flat tan painted bands down a tail, th_W04)
            fh = M("MULTIPLY", M("MULTIPLY", M("MAXIMUM", f_t, M("MULTIPLY", f_b, 0.35)), smooth(age, 0.01, 0.07)), hlc)
            # (a ribbon comes and goes along its length, each on its own rhythm: uniform it was pale tape, th_V73)
            fh = M("MULTIPLY", fh, M("MULTIPLY_ADD", M("SINE", M("ADD", M("MULTIPLY_ADD", age, 38.0, M("MULTIPLY", ch_, 40.0)),
                                                                  M("MULTIPLY", cb_, 25.0))), 0.42, 0.58))
            # (not every strand of a ribbon is lightened: all of them, it was a strip of pale tape, th_V74)
            # (half the strands of a ribbon, and little saturation: + 100 % saturation turned them tan, th_W04)
            fh = M("MULTIPLY", fh, M("LESS_THAN", info.outputs["Random"], 0.5))
            # (a tail's ribbons at half contrast: hair off the head has no layers over it to break a ribbon up, and
            # full ones were flat pale bands down the tail, th_W05)
            fh = M("MULTIPLY", fh, M("SUBTRACT", 1.0, M("MULTIPLY", M("GREATER_THAN", at_("hp_a0"), 0.005), 0.5)))
            val = M("MULTIPLY", val, M("MULTIPLY_ADD", fh, 0.85, 1.0))
            hue = M("MULTIPLY_ADD", fh, 0.006, hue)
            sat = M("MULTIPLY_ADD", fh, 0.45, sat)
    if fly > 0:
        val = M("MULTIPLY", val, M("MULTIPLY_ADD", at_("hp_fly"), 0.6 * fly, 1.0))
    dep = float(np.clip(look.get("depth", 0.5) or 0.0, 0.0, 1.0))
    if dep > 0:  # the under-layers of a standing mass are darker (hp_sh, a lock's depth in it: hair_flow's volume)
        val = M("MULTIPLY", val, M("MULTIPLY_ADD", at_("hp_sh"), -0.75 * dep, 1.0))
        # ... and inside a lock the strands on its head side are darker than those on its outer face (hp_b: -1 the
        # head's side .. 1 the outer face): what shows between clumps is dark, the gaps read as depth
        val = M("MULTIPLY", val, M("MULTIPLY_ADD", M("SUBTRACT", at_("hp_b"), 1.0), 0.2 * dep, 1.0))
    L.new(val, hsv.inputs["Value"])
    if hue is not None:
        L.new(hue, hsv.inputs["Hue"])
        L.new(sat, hsv.inputs["Saturation"])
    col = hsv.outputs["Color"]
    ga = float(look.get("grey_amount", 0.0))
    gl = float(look.get("grey_locks", 1.0))  # x each lock's own grey (its "grey": temples, sideburns)
    if ga > 0 or gl > 0:  # grey hairs: a share of the strands, the look's + the lock's own (hp_gr)
        mix = N.new("ShaderNodeMix")
        mix.data_type = "RGBA"
        lt = N.new("ShaderNodeMath")
        lt.operation = "LESS_THAN"
        L.new(info.outputs["Random"], lt.inputs[0])
        gra = N.new("ShaderNodeAttribute")
        gra.attribute_name = "hp_gr"
        sh = N.new("ShaderNodeMath")
        sh.operation = "MULTIPLY_ADD"
        sh.use_clamp = True
        L.new(gra.outputs["Fac"], sh.inputs[0])
        sh.inputs[1].default_value = gl
        sh.inputs[2].default_value = ga
        L.new(sh.outputs[0], lt.inputs[1])
        L.new(lt.outputs[0], mix.inputs["Factor"])
        L.new(col, mix.inputs["A"])
        mix.inputs["B"].default_value = (*grey, 1)
        col = mix.outputs["Result"]
    # Cycles
    oc = N.new("ShaderNodeOutputMaterial")
    oc.target = "CYCLES"
    hb = N.new("ShaderNodeBsdfHairPrincipled")
    hb.parametrization = "COLOR"
    # the hair BSDF's colour is not what a lit mass of strands comes out as (multiple scattering lightens and
    # warms it: dark brown rendered ginger-blond): the look colour goes through the inverse of a measured fit,
    # rendered = A x colour^p per linear channel (hair_strands.CYCLES_FIT, spikes/hair_strands/hs4/cal2.py)
    A_, p_ = [float(v) for v in look.get("cycles_fit") or (1.0, 1.0)]
    # on the colour's LUMINANCE, the hue kept: colour x (Y / A)^(1/p) / Y. Per channel (the first version), the
    # 1/p power (x3.3) tripled every channel ratio: a faintly warm grey (#5a4f47) rendered light brown.
    # look.cycles_sat: the look colour's saturation kept for Cycles (as eevee_sat for EEVEE). The hair BSDF gives
    # back less chroma than it is given on a thin groom and MORE on a dense dark one (deep multiple scattering reddens:
    # Tess's tied hair measured chroma 13-15 where her pictures have 8-9, tesshair5): fitted per look by measure
    cs_ = look.get("cycles_sat")
    col_c = col
    if cs_ is not None and float(cs_) != 1.0:
        sat_c = N.new("ShaderNodeHueSaturation")
        sat_c.inputs["Saturation"].default_value = float(cs_)
        L.new(col, sat_c.inputs["Color"])
        col_c = sat_c.outputs["Color"]
    bw = N.new("ShaderNodeRGBToBW")
    L.new(col_c, bw.inputs["Color"])
    ymax = N.new("ShaderNodeMath")
    ymax.operation = "MAXIMUM"
    ymax.inputs[1].default_value = 1e-4
    L.new(bw.outputs["Val"], ymax.inputs[0])
    ya = N.new("ShaderNodeMath")
    ya.operation = "DIVIDE"
    ya.inputs[1].default_value = max(A_, 1e-6)
    L.new(ymax.outputs[0], ya.inputs[0])
    yp = N.new("ShaderNodeMath")
    yp.operation = "POWER"
    yp.inputs[1].default_value = 1.0 / max(p_, 1e-3)
    L.new(ya.outputs[0], yp.inputs[0])
    kk = N.new("ShaderNodeMath")
    kk.operation = "DIVIDE"
    L.new(yp.outputs[0], kk.inputs[0])
    L.new(ymax.outputs[0], kk.inputs[1])
    sc_ = N.new("ShaderNodeVectorMath")
    sc_.operation = "SCALE"
    L.new(col_c, sc_.inputs[0])
    L.new(kk.outputs[0], sc_.inputs["Scale"])
    L.new(sc_.outputs["Vector"], hb.inputs["Color"])
    mel = look.get("cycles_melanin")
    if mel is not None:
        # PHYSICAL hair colour (Blender's Principled Hair BSDF, melanin parametrization: eumelanin amount + redness,
        # Random Color varies it per strand): the light transport (multiple scattering, transmission, the coloured
        # TRT lobe) comes from the shader, our colour model rides on it as a TINT = the strand's colour / the look's
        # lit colour (ribbons, sun, roots, depth), never brighter than 1.6
        hb.parametrization = "MELANIN"
        hb.inputs["Melanin"].default_value = float(mel)
        hb.inputs["Melanin Redness"].default_value = float(look.get("cycles_redness", 0.5))
        hb.inputs["Random Color"].default_value = float(look.get("cycles_random_color", 0.12))
        lit_v = [max(x, 1e-4) for x in lit]
        dv = N.new("ShaderNodeVectorMath")
        dv.operation = "DIVIDE"
        L.new(col, dv.inputs[0])
        dv.inputs[1].default_value = lit_v
        mn = N.new("ShaderNodeVectorMath")
        mn.operation = "MINIMUM"
        L.new(dv.outputs["Vector"], mn.inputs[0])
        mn.inputs[1].default_value = (1.6, 1.6, 1.6)
        L.new(mn.outputs["Vector"], hb.inputs["Tint"])
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
    # the look's colours are asked for CYCLES, whose hair BSDF gives back far less chroma than it is given (asked
    # R/B 2.3, rendered 1.16-1.30: hair notes) so they are set far warmer than they should come out; drawn as they are,
    # EEVEE showed every dressed render's hair orange-blond and the grey locks tan (Garrett). EEVEE takes them toward
    # their own luminance by look.eevee_sat (0.35: that measured R/B), so its strands read as Cycles renders them
    sat_e = N.new("ShaderNodeHueSaturation")
    sat_e.inputs["Saturation"].default_value = float(look.get("eevee_sat", EEVEE_SAT))
    L.new(col, sat_e.inputs["Color"])
    L.new(sat_e.outputs["Color"], bright.inputs["A"])
    g = float(look.get("eevee_gain", 1.6))  # the hair BSDF's multiple scattering brightens a mass of strands; a
    bright.inputs["B"].default_value = (g, g, g, 1)  # plain diffuse strand doesn't: lifted to match Cycles
    L.new(bright.outputs["Result"], pb.inputs["Base Color"])
    pb.inputs["Roughness"].default_value = float(look.get("roughness", 0.42))
    pb.inputs["Specular IOR Level"].default_value = float(look.get("specular", 0.5)) * 0.6
    pb.inputs["Anisotropic"].default_value = 0.0
    gl_ = float(np.clip(look.get("gloss", 0.0) or 0.0, 0.0, 1.0))
    if gl_ > 0:
        # THE HIGHLIGHT where light catches the arcs (tesshair7 round two; hers: a soft warm band over the dome). A
        # hair has two lobes (Marschner; Kajiya-Kay in real-time practice): a sharp near-white one off the cuticle,
        # shifted toward the ROOT, and a broader one that passed through the hair and took its colour, shifted toward
        # the TIP. EEVEE's strand is a camera-facing ribbon with a round normal, so each lobe is a specular with its
        # normal tilted along the strand's tangent: the Principled's own (toward the root) and its coat, tinted
        # (toward the tip). (EEVEE has no anisotropic reflection: the tangent is used for the tilt only.)
        geo_n = N.new("ShaderNodeNewGeometry")

        def tilted(k):
            sc_n = N.new("ShaderNodeVectorMath")
            sc_n.operation = "SCALE"
            L.new(info.outputs["Tangent Normal"], sc_n.inputs[0])
            sc_n.inputs["Scale"].default_value = k
            ad_n = N.new("ShaderNodeVectorMath")
            ad_n.operation = "ADD"
            L.new(geo_n.outputs["Normal"], ad_n.inputs[0])
            L.new(sc_n.outputs["Vector"], ad_n.inputs[1])
            no_n = N.new("ShaderNodeVectorMath")
            no_n.operation = "NORMALIZE"
            L.new(ad_n.outputs["Vector"], no_n.inputs[0])
            return no_n.outputs["Vector"]
        L.new(tilted(-0.12), pb.inputs["Normal"])
        # (a softer primary: sharper, crossing strands at the crown glinted as a white wire grid, th_W04)
        pb.inputs["Roughness"].default_value = max(float(look.get("roughness", 0.42)) * (1.0 - 0.15 * gl_), 0.4)
        pb.inputs["Specular IOR Level"].default_value = float(look.get("specular", 0.5)) * 0.6 + 0.3 * gl_
        try:
            pb.inputs["Coat Weight"].default_value = 0.7 * gl_
            pb.inputs["Coat Roughness"].default_value = 0.45
            L.new(tilted(0.22), pb.inputs["Coat Normal"])
            warm = N.new("ShaderNodeHueSaturation")
            warm.inputs["Saturation"].default_value = 1.6
            warm.inputs["Value"].default_value = 3.0
            L.new(sat_e.outputs["Color"], warm.inputs["Color"])
            L.new(warm.outputs["Color"], pb.inputs["Coat Tint"])
        except KeyError:
            pass
    try:
        pb.inputs["Sheen Weight"].default_value = float(look.get("sheen_amount", 0.45)) * 0.3
        pb.inputs["Sheen Tint"].default_value = (*_lin(look.get("sheen", "#86524a")), 1)
    except KeyError:
        pass
    fa_ = float(look.get("fine_alpha", 0.5))
    if fa_ < 1.0:  # single hairs (hp_fine) part transparent in EEVEE (dithered: the samples blend it)
        fn = N.new("ShaderNodeAttribute")
        fn.attribute_name = "hp_fine"
        al = N.new("ShaderNodeMath")
        al.operation = "MULTIPLY_ADD"
        L.new(fn.outputs["Fac"], al.inputs[0])
        al.inputs[1].default_value = fa_ - 1.0
        al.inputs[2].default_value = 1.0
        L.new(al.outputs[0], pb.inputs["Alpha"])
        try:
            m.surface_render_method = "DITHERED"
        except Exception:  # noqa: BLE001
            m.blend_method = "HASHED"
    # THE GAME HAIR SHADER TERMS (tesshair7; engine-agnostic: what UE's groom / card shaders and Kajiya-Kay / Marschner
    # approximations do; the coordinator: "the photo's warm translucent lengths, the glow where hair is thin against
    # the light, the lighter see-through tips and the golden lobe are light transport, not pigment"). The two
    # highlight lobes are `gloss` (above). Here:
    #   tip_alpha 0..1   see-through TIPS: alpha falls toward the tip (dithered), over the last 30 % of a strand
    #   backscatter 0..1 light through THIN hair: a warm translucent term (lit from BEHIND the strand) weighted to
    #                    thin hair (tips, fine / single hairs): brighter and warmer where the hair is thin or back-lit
    #   scatter 0..1     fake multiple scattering: the core (deep in the mass, hp_sh) darker AND richer (saturated),
    #                    the outer layers lighter
    ta_ = float(np.clip(look.get("tip_alpha", 0.0) or 0.0, 0, 1))
    alpha_out = al.outputs[0] if fa_ < 1.0 else None
    if ta_ > 0:
        ss_t = N.new("ShaderNodeMapRange")
        ss_t.interpolation_type = "SMOOTHSTEP"
        L.new(info.outputs["Intercept"], ss_t.inputs["Value"])
        ss_t.inputs["From Min"].default_value, ss_t.inputs["From Max"].default_value = 0.7, 1.0
        ss_t.inputs["To Min"].default_value, ss_t.inputs["To Max"].default_value = 1.0, 1.0 - ta_
        if fa_ < 1.0:
            mul = N.new("ShaderNodeMath")
            mul.operation = "MULTIPLY"
            L.new(al.outputs[0], mul.inputs[0])
            L.new(ss_t.outputs["Result"], mul.inputs[1])
            alpha_out = mul.outputs[0]
        else:
            alpha_out = ss_t.outputs["Result"]
        try:
            m.surface_render_method = "DITHERED"
        except Exception:  # noqa: BLE001
            m.blend_method = "HASHED"
    sc_k = float(np.clip(look.get("scatter", 0.0) or 0.0, 0, 1))
    if sc_k > 0:  # (on the EEVEE base colour: richer, darker core; lighter outer layers)
        shv = N.new("ShaderNodeAttribute")
        shv.attribute_name = "hp_sh"
        rich = N.new("ShaderNodeHueSaturation")
        sm = N.new("ShaderNodeMath")
        sm.operation = "MULTIPLY_ADD"
        L.new(shv.outputs["Fac"], sm.inputs[0])
        sm.inputs[1].default_value = 0.6 * sc_k
        sm.inputs[2].default_value = 1.0
        L.new(sm.outputs[0], rich.inputs["Saturation"])
        vm = N.new("ShaderNodeMath")
        vm.operation = "MULTIPLY_ADD"
        L.new(shv.outputs["Fac"], vm.inputs[0])
        vm.inputs[1].default_value = -0.45 * sc_k
        vm.inputs[2].default_value = 1.0 + 0.12 * sc_k
        L.new(vm.outputs[0], rich.inputs["Value"])
        L.new(bright.outputs["Result"], rich.inputs["Color"])
        L.new(rich.outputs["Color"], pb.inputs["Base Color"])
    out_sh = pb.outputs[0]
    bs_ = float(np.clip(look.get("backscatter", 0.0) or 0.0, 0, 1))
    if bs_ > 0:
        tr = N.new("ShaderNodeBsdfTranslucent")  # (lit from behind the strand: what passes through thin hair)
        warm_t = N.new("ShaderNodeHueSaturation")
        warm_t.inputs["Saturation"].default_value = 1.5
        warm_t.inputs["Value"].default_value = 2.2
        warm_t.inputs["Hue"].default_value = 0.51
        L.new(bright.outputs["Result"], warm_t.inputs["Color"])
        L.new(warm_t.outputs["Color"], tr.inputs["Color"])
        thin = N.new("ShaderNodeMapRange")
        thin.interpolation_type = "SMOOTHSTEP"
        L.new(info.outputs["Intercept"], thin.inputs["Value"])
        thin.inputs["From Min"].default_value, thin.inputs["From Max"].default_value = 0.4, 1.0
        fz = N.new("ShaderNodeAttribute")
        fz.attribute_name = "hp_fine"
        mx = N.new("ShaderNodeMath")
        mx.operation = "MAXIMUM"
        L.new(thin.outputs["Result"], mx.inputs[0])
        L.new(fz.outputs["Fac"], mx.inputs[1])
        wt = N.new("ShaderNodeMath")
        wt.operation = "MULTIPLY_ADD"
        L.new(mx.outputs[0], wt.inputs[0])
        wt.inputs[1].default_value = 0.7 * bs_
        wt.inputs[2].default_value = 0.3 * bs_
        mixs = N.new("ShaderNodeMixShader")
        L.new(wt.outputs[0], mixs.inputs["Fac"])
        L.new(pb.outputs[0], mixs.inputs[1])
        addt = N.new("ShaderNodeAddShader")
        L.new(pb.outputs[0], addt.inputs[0])
        L.new(tr.outputs[0], addt.inputs[1])
        L.new(addt.outputs[0], mixs.inputs[2])
        out_sh = mixs.outputs[0]
    if alpha_out is not None and (ta_ > 0 or bs_ > 0):
        # (the transparency as ONE final mix with a transparent shader: the translucent term is outside the
        # Principled, and its own Alpha would have left that term opaque at the tips)
        for lk_ in list(pb.inputs["Alpha"].links):
            nt.links.remove(lk_)
        trn = N.new("ShaderNodeBsdfTransparent")
        fin = N.new("ShaderNodeMixShader")
        L.new(alpha_out, fin.inputs["Fac"])
        L.new(trn.outputs[0], fin.inputs[1])
        L.new(out_sh, fin.inputs[2])
        out_sh = fin.outputs[0]
    L.new(out_sh, oe.inputs["Surface"])
    m["hp_look"] = json.dumps(look, sort_keys=True)
    return m


def clear():
    for n in [o.name for o in strand_objects()] + list(OBJECTS) + ["hair_band"]:
        _drop(n)


def show(sd: dict):
    """Apply a strands job (hair_strands.job): the scalp, the guide objects with their stacks."""
    clear()
    mat = material(sd.get("look") or {})
    lk = sd.get("look") or {}
    tint = list(_lin(lk["scalp"])) if lk.get("scalp") else [0.5 * a + 0.5 * b for a, b in zip(
        _lin(lk.get("gap", "#221310")), _lin(lk.get("lit", "#56352d")))]  # (scalp: from look.seen, hair.seen_look)
    scalp = None if not sd.get("scalp") else scalp_object(sd["scalp"], tint,
                         float(lk.get("scalp_tint", 0.85)))
    if sd.get("collide"):
        z = np.load(sd["collide"])
        me = bpy.data.meshes.new("hair_collide")
        me.from_pydata([tuple(map(float, v)) for v in z["verts"]], [], [tuple(map(int, f)) for f in z["faces"]])
        me.update()
        co = bpy.data.objects.new("hair_collide", me)
        co["hp_hair_scalp"] = 2
        co.hide_render = True
        co.display_type = "BOUNDS"
        _coll().objects.link(co)
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


def cycles_width(k: float):
    """Strands x k wide for a path-traced render (look.cycles_width). A path tracer draws a strand at its true width;
    EEVEE never draws one under a pixel, so the same groom is far denser there. A groom of 70k strands stands in for
    100-150k hairs: at true width its head hair is a see-through veil over the scalp in Cycles."""
    for ob in strand_objects():
        for mod in ob.modifiers:
            if mod.type == "NODES" and mod.node_group and mod.node_group.name.startswith(PROFILE):
                for it in mod.node_group.interface.items_tree:
                    if it.item_type == "SOCKET" and it.in_out == "INPUT" and it.name == "Radius":
                        mod[it.identifier] = float(mod[it.identifier]) * float(k)
        ob.update_tag()


def strand_objects() -> list:
    return sorted((o for o in bpy.data.objects if o.get("hp_strands")), key=lambda o: o.name)


def stats() -> dict:
    dg = bpy.context.evaluated_depsgraph_get()
    out = {}
    for ob in strand_objects():
        d = ob.evaluated_get(dg).data
        out[ob.name] = {"guides": len(ob.data.curves), "strands": len(d.curves), "points": len(d.points)}
    return out


def points(names: list | None = None, every: int = 3):
    """Evaluated strand points (world, every n-th), and which object each belongs to."""
    dg = bpy.context.evaluated_depsgraph_get()
    out = []
    for ob in strand_objects():
        d = ob.evaluated_get(dg).data
        a = np.empty(len(d.points) * 3, np.float32)
        d.attributes["position"].data.foreach_get("vector", a)
        a = a.reshape(-1, 3)[::every]
        out.append(a)
        if names is not None:
            names += [ob.name] * len(a)
    return np.concatenate(out) if out else np.zeros((0, 3), np.float32)


def dump(path: str):
    """Every evaluated strand to an npz: pts, counts (points per strand), and per strand lock (the guide's lock
    index), sub (its sub clump), rand, radius (at its root), obj (index into names). The cards, the atlas and the
    cap texture are made from these."""
    dg = bpy.context.evaluated_depsgraph_get()
    cols = {k: [] for k in ("pts", "counts", "lock", "sub", "rand", "radius", "obj")}
    names = []
    for oi, ob in enumerate(strand_objects()):
        names.append(ob.name)
        d = ob.evaluated_get(dg).data
        a = np.empty(len(d.points) * 3, np.float32)
        d.attributes["position"].data.foreach_get("vector", a)
        cnt = np.empty(len(d.curves), np.int32)
        d.curves.foreach_get("points_length", cnt)

        def curve_attr(name, dtype):
            v = np.zeros(len(d.curves), dtype)
            at = d.attributes.get(name)
            if at is not None and at.domain == "CURVE":
                at.data.foreach_get("value", v)
            return v
        rad = np.zeros(len(d.points), np.float32)
        at = d.attributes.get("radius")
        if at is not None and at.domain == "POINT":
            at.data.foreach_get("value", rad)
        first = np.r_[0, np.cumsum(cnt)[:-1]]
        cols["pts"].append(a.reshape(-1, 3))
        cols["counts"].append(cnt)
        cols["lock"].append(curve_attr("hp_lock", np.int32))
        cols["sub"].append(curve_attr("hp_sub", np.float32))
        cols["rand"].append(curve_attr("hp_rand", np.float32) if "hp_rand" in d.attributes
                            else np.random.default_rng(oi).uniform(0, 1, len(cnt)).astype(np.float32))
        cols["radius"].append(rad[first] if len(cnt) else rad[:0])
        cols["obj"].append(np.full(len(cnt), oi, np.int32))
    np.savez(path, names=np.asarray(names), **{k: np.concatenate(v) for k, v in cols.items()})


def export_groom(abc: str | None, usd: str | None) -> dict:
    """The evaluated strands as ONE Hair Curves object "groom" written to Alembic (curves + widths, centimetres: what
    Unreal's groom importer needs at the least) and USD (BasisCurves + widths + the groom_* attributes as primvars:
    Blender's Alembic writer drops per-curve attributes, its USD writer keeps them)."""
    dg = bpy.context.evaluated_depsgraph_get()
    P, C, G, R, I = [], [], [], [], []
    COL = []
    import hair_colour as hcol  # (the colour model in numpy: this file's directory is on sys.path inside Blender)
    mat_ = bpy.data.materials.get("hp_strand")
    look = json.loads(mat_["hp_look"]) if mat_ is not None and mat_.get("hp_look") else {}
    lit_, gap_ = np.asarray(_lin(look.get("lit", "#56352d"))), np.asarray(_lin(look.get("gap", "#221310")))
    rd_, rpos = float(look.get("root_dark", 0.5)), max(0.02, float(look.get("root", 0.12)))
    for gi_, ob in enumerate(strand_objects()):
        d = ob.evaluated_get(dg).data
        a = np.empty(len(d.points) * 3, np.float32)
        d.attributes["position"].data.foreach_get("vector", a)
        cnt = np.empty(len(d.curves), np.int32)
        d.curves.foreach_get("points_length", cnt)
        rad = np.full(len(d.points), 0.00008, np.float32)
        at = d.attributes.get("radius")
        if at is not None and at.domain == "POINT":
            at.data.foreach_get("value", rad)
        P.append(a.reshape(-1, 3))
        C.append(cnt)
        R.append(rad)

        def cattr(name, default=0.0):
            at_ = d.attributes.get(name)
            v_ = np.full(len(cnt), default, np.float32)
            if at_ is not None and at_.domain == "CURVE" and at_.data_type in ("FLOAT", "INT"):
                at_.data.foreach_get("value", v_)
            return np.repeat(v_, cnt)
        # the colour a strand has in the look (hair_colour: variation, depth, sun by age, highlight ribbons), per
        # POINT, linear RGB: the dark root, then lit x tone. Unreal's groom reads groom_color; USD keeps it as a primvar
        tpt = np.concatenate([np.linspace(0.0, 1.0, int(c_)) for c_ in cnt]) if len(cnt) else np.zeros(0)
        a0_, a1_ = cattr("hp_a0"), cattr("hp_a1")
        age = a0_ + (a1_ - a0_) * tpt
        tone = hcol.strand_tone(look, age, cattr("hp_lv"), cattr("hp_sh"), np.maximum(cattr("hp_ch"), cattr("hp_cb") * 0.9),
                                cattr("hp_cm"), cattr("hp_su"), cattr("hp_fly"))
        rootf = np.where(a0_ > 0.005, 1.0, hcol._ss(tpt / rpos))
        base = (gap_ * rd_ + lit_ * (1 - rd_))[None] * (1 - rootf)[:, None] + lit_[None] * rootf[:, None]
        COL.append((base * tone[:, None]).astype(np.float32))
        G.append(np.full(len(cnt), gi_, np.int32))
    P, C, R, G = np.concatenate(P), np.concatenate(C), np.concatenate(R), np.concatenate(G)
    cu = bpy.data.hair_curves.new("groom")
    cu.add_curves([int(c) for c in C])
    cu.attributes["position"].data.foreach_set("vector", P.ravel())
    (cu.attributes.get("radius") or cu.attributes.new("radius", "FLOAT", "POINT")).data.foreach_set("value", R)
    n = len(C)
    cu.attributes.new("groom_group_id", "INT", "CURVE").data.foreach_set("value", G)
    cu.attributes.new("groom_id", "INT", "CURVE").data.foreach_set("value", np.arange(n, dtype=np.int32))
    cu.attributes.new("groom_guide", "INT", "CURVE").data.foreach_set("value", (np.arange(n) % 40 == 0).astype(np.int32))
    cu.attributes.new("groom_width", "FLOAT", "POINT").data.foreach_set("value", (R * 2 * 100).astype(np.float32))
    if COL:
        cu.attributes.new("groom_color", "FLOAT_VECTOR", "POINT").data.foreach_set("vector", np.concatenate(COL).ravel())
    ob = bpy.data.objects.new("groom", cu)
    ob["groom_version_major"], ob["groom_version_minor"] = 1, 5
    ob["groom_tool"] = "hifipushie"
    bpy.context.scene.collection.objects.link(ob)
    for o in bpy.context.view_layer.objects:
        o.select_set(o is ob)
    bpy.context.view_layer.objects.active = ob
    out = {"strands": int(n), "points": int(len(P))}
    if COL:
        cc_ = np.concatenate(COL)
        yy_ = cc_ @ np.array([0.2126, 0.7152, 0.0722])
        out["color"] = {"attribute": "groom_color", "mean": [round(float(x), 4) for x in cc_.mean(0)],
                        "value_p10_p90": [round(float(np.percentile(yy_, 10)), 4), round(float(np.percentile(yy_, 90)), 4)]}
    if abc:
        bpy.ops.wm.alembic_export(filepath=abc, selected=True, global_scale=100.0, export_custom_properties=True)
        out["abc"] = os.path.getsize(abc)
    if usd:
        bpy.ops.wm.usd_export(filepath=usd, selected_objects_only=True)
        out["usd"] = os.path.getsize(usd)
    bpy.data.objects.remove(ob)
    return out


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
    for ob in strand_objects():
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
    for ob in strand_objects():
        n = ob.name
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
