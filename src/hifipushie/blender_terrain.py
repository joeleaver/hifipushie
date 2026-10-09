"""Runs inside headless Blender: a terrain grid mesh (vertex colours) and its lakes, rendered in Cycles
under a sun (per view [bearing, height] deg: terrain_sun picks it) and sky from perspective cameras. Job: {"mesh",
"size": [w, h], "samples", "views": [{"eye": [x, y, z], "look": [x, y, z], "fov": deg, "sun": [b, h], "out": png}]}."""
import math

import json
import sys

import bpy
from mathutils import Matrix
import numpy as np
from mathutils import Vector


def _mesh(name, verts, faces, colors=None):
    me = bpy.data.meshes.new(name)
    me.vertices.add(len(verts))
    me.vertices.foreach_set("co", verts.ravel())
    me.loops.add(faces.size)
    me.loops.foreach_set("vertex_index", faces.ravel())
    me.polygons.add(len(faces))
    me.polygons.foreach_set("loop_start", np.arange(0, faces.size, 3, dtype=np.int32))
    me.update()
    me.shade_smooth()
    if colors is not None:
        a = me.color_attributes.new("col", "FLOAT_COLOR", "POINT")
        a.data.foreach_set("color", np.c_[colors, np.ones(len(colors))].astype(np.float32).ravel())
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    return ob


def _walls(pts, piece, info):
    """A dry-stone wall as a box ribbon along its line, following the ground (sunk a little); a fence as posts every
    2.5 m with a rail along their tops."""
    V, F, Vf, Ff, Vh, Fh = [], [], [], [], [], []
    rng = np.random.default_rng(5)
    for k, (h, w, fence) in enumerate(info):
        p = pts[piece == k].astype(float)
        if len(p) < 2:
            continue
        t = np.gradient(p[:, :2], axis=0)
        t /= np.linalg.norm(t, axis=1, keepdims=True) + 1e-9
        n = np.c_[-t[:, 1], t[:, 0]]
        if fence == 2:  # a hedge: one continuous mass, rounded, its top and sides lumpy (shrub by shrub it read as
            # strings of beads)
            m = len(p)
            lump = np.convolve(rng.normal(0, 1, m + 6), np.ones(4) / 4, "same")[3:3 + m]
            wid = np.convolve(rng.normal(0, 1, m + 6), np.ones(3) / 3, "same")[3:3 + m]
            base = len(Vh)
            prof = ((-0.5, 0.0), (-0.45, 0.55), (-0.25, 0.95), (0.25, 0.95), (0.45, 0.55), (0.5, 0.0))
            for i, (row, (nx, ny)) in enumerate(zip(p, n)):
                x, y, z = row[:3]
                zl, zr = (row[3], row[4]) if len(row) > 4 else (z, z)
                hh = h * (1 + 0.15 * lump[i])
                ww = w * (1 + 0.15 * wid[i])
                for sx, fz in prof:
                    zg = zr if sx < 0 else zl
                    Vh.append((x + nx * sx * ww, y + ny * sx * ww, (zg - 0.2) * (1 - fz) + (max(zl, zr) + hh) * fz))
            for i in range(m - 1):
                a, b = base + 6 * i, base + 6 * (i + 1)
                for q in range(5):
                    Fh.append((a + q, b + q, b + q + 1))
                    Fh.append((a + q, b + q + 1, a + q + 1))
            continue
        if not fence:  # a wall, a little narrower at its top (battered)
            base = len(V)
            for row, (nx, ny) in zip(p, n):
                x, y, z = row[:3]
                zl, zr = (row[3], row[4]) if len(row) > 4 else (z, z)
                zt = max(zl, zr) + h  # a level top over the higher side; the feet on each side's ground
                for sx, zz in ((-0.5, zr - 0.3), (0.5, zl - 0.3), (0.3, zt), (-0.3, zt)):
                    V.append((x + nx * sx * w, y + ny * sx * w, zz))
            for i in range(len(p) - 1):
                a, b = base + 4 * i, base + 4 * (i + 1)
                for q in ((0, 3), (3, 2), (2, 1)):  # outer side, top, other side
                    F.append((a + q[0], b + q[0], b + q[1]))
                    F.append((a + q[0], b + q[1], a + q[1]))
        else:
            s = np.r_[0, np.cumsum(np.linalg.norm(np.diff(p[:, :2], axis=0), axis=1))]
            for at in np.arange(0, s[-1] + 1e-6, 2.5):
                x, y, z = (np.interp(at, s, p[:, j]) for j in range(3))
                base = len(Vf)
                r = 0.06
                for dz in (-0.3, h):
                    Vf += [(x - r, y - r, z + dz), (x + r, y - r, z + dz), (x + r, y + r, z + dz), (x - r, y + r, z + dz)]
                for i in range(4):
                    j = (i + 1) % 4
                    Ff += [(base + i, base + j, base + 4 + j), (base + i, base + 4 + j, base + 4 + i)]
            base = len(Vf)  # the rail: a thin ribbon a little under the posts' tops
            for row, (nx, ny) in zip(p, n):
                x, y, z = row[:3]
                Vf += [(x + nx * 0.02, y + ny * 0.02, z + h - 0.25), (x + nx * 0.02, y + ny * 0.02, z + h - 0.05)]
            for i in range(len(p) - 1):
                a, b = base + 2 * i, base + 2 * (i + 1)
                Ff += [(a, b, b + 1), (a, b + 1, a + 1)]
    if V:
        ob = _mesh("stone_walls", np.array(V, np.float32), np.array(F, np.int32))
        ob.data.materials.append(_mat("stone_wall", (0.2, 0.19, 0.17, 1), 0.95))  # (grey stone, sRGB ~0.48)
    if Vh:
        ob = _mesh("hedges", np.array(Vh, np.float32), np.array(Fh, np.int32))
        ob.data.materials.append(_mat("hedge", (0.035, 0.07, 0.025, 1), 0.95))
    if Vf:
        ob = _mesh("fences", np.array(Vf, np.float32), np.array(Ff, np.int32))
        ob.data.materials.append(_mat("fence", (0.20, 0.15, 0.10, 1), 0.8))


def _mat(name, col, rough=0.8):
    m = bpy.data.materials.get(name)
    if m is None:
        m = bpy.data.materials.new(name)
        m.use_nodes = True
        b = m.node_tree.nodes["Principled BSDF"]
        b.inputs["Base Color"].default_value = col
        b.inputs["Roughness"].default_value = rough
    return m


def _limb(p0, p1, r0, r1, mat):
    """A tapered branch or trunk segment from p0 to p1."""
    p0, p1 = Vector(p0), Vector(p1)
    d = p1 - p0
    bpy.ops.mesh.primitive_cone_add(vertices=7, radius1=r0, radius2=r1, depth=d.length, location=(p0 + p1) / 2)
    o = bpy.context.object
    o.rotation_euler = d.to_track_quat("Z", "Y").to_euler()
    o.data.materials.append(mat)
    return o


def _blob(c, r, sq, mat, subdiv=2, jitter=0.0, rng=None):
    """A crown mass: a smooth squashed sphere, its vertices pushed about so it isn't a perfect ball."""
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=subdiv, radius=1.0, location=c)
    o = bpy.context.object
    o.scale = (r * sq[0], r * sq[1], r * sq[2])
    if jitter and rng is not None:
        for v in o.data.vertices:
            v.co *= 1.0 + rng.uniform(-jitter, jitter)
    o.data.materials.append(mat)
    for f in o.data.polygons:
        f.use_smooth = True
    return o


def _join(parts, name):
    bpy.ops.object.select_all(action="DESELECT")
    for p in parts:
        p.select_set(True)
    bpy.context.view_layer.objects.active = parts[-1]
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    bpy.ops.object.join()
    ob = bpy.context.object
    ob.name = name
    ob.hide_render = True
    ob.location = (0, 0, -1e4)
    return ob


def _species(kind, v):
    """Variant v of a Monterey cypress or pine, downwind = +x.
    cypress: a bent, often forked trunk, heavy dark crown masses swept and flattened downwind with gaps between;
    pine: a tall trunk, a rounded crown of 2-3 clumps."""
    import random
    rng = random.Random(97 * v + (1 if kind == "cypress" else 2))
    bark = _mat("bark", (0.1, 0.07, 0.05, 1), 0.9)
    parts = []
    if kind == "cypress":
        crown = _mat("crown_cypress", (0.018, 0.04, 0.025, 1))
        stems = 1 + (v % 3 != 0) + (v == 2)
        tops = []
        for k in range(stems):
            a = math.radians(rng.uniform(-35, 35))  # stems fan out across the wind
            lean = rng.uniform(0.35, 0.9)  # how far downwind per metre up
            h1 = rng.uniform(2.5, 4.0)
            p0 = (0.0, 0.0, -0.3)
            p1 = (lean * h1 * math.cos(a), lean * h1 * math.sin(a), h1)
            p2 = (p1[0] + rng.uniform(2.0, 4.5), p1[1] + rng.uniform(-1, 1), p1[2] + rng.uniform(0.8, 2.5))
            parts.append(_limb(p0, p1, 0.55 - 0.1 * k, 0.4, bark))
            parts.append(_limb(p1, p2, 0.4, 0.22, bark))
            tops.append(p2)
        for t in tops:  # heavy masses, flat, swept downwind, gaps between
            for j in range(rng.randint(2, 3)):
                c = (t[0] + rng.uniform(-1.5, 3.5), t[1] + rng.uniform(-2.5, 2.5), t[2] + rng.uniform(-0.6, 1.0))
                r = rng.uniform(2.0, 3.4)
                parts.append(_blob(c, r, (rng.uniform(1.2, 1.7), rng.uniform(0.8, 1.1), rng.uniform(0.35, 0.55)),
                                   crown, 2, 0.12, rng))
    else:
        crown = _mat("crown_pine", (0.03, 0.075, 0.04, 1))
        h = rng.uniform(9.0, 13.0)
        top = (rng.uniform(-0.8, 0.8), rng.uniform(-0.8, 0.8), h)
        parts.append(_limb((0, 0, -0.3), top, 0.45, 0.25, bark))
        n = rng.randint(2, 3)
        for j in range(n):
            ang = 2 * math.pi * j / n + rng.uniform(-0.4, 0.4)
            d = rng.uniform(1.2, 2.4)
            c = (top[0] + d * math.cos(ang), top[1] + d * math.sin(ang), h + rng.uniform(-1.2, 1.0))
            parts.append(_limb(top, (c[0], c[1], c[2] - 0.8), 0.22, 0.12, bark))
            parts.append(_blob(c, rng.uniform(2.4, 3.3), (1.0, 1.0, 0.72), crown, 3, 0.08, rng))
    return _join(parts, f"tree_{kind}_{v}")


VARIANTS = 4


CLUTTER_KINDS = ("bush", "tussock", "tallgrass", "boulder", "river_rock", "cobbles", "slab", "driftwood", "reeds",
                 "litter", "sedge", "pebbles", "wrack")
CLUTTER_VARIANTS = 4


def _clutter_mat(kind, sea=None):
    """Clutter materials: colour from the mesh's own "tc" attribute (blades: green at the root to straw at the tip;
    bush lumps: sage, some in flower), varied per instance (Object Info's random: brightness and a little hue); boulders
    dark, wetter and darker within ~1.5 m of the sea."""
    name = "clutter_" + kind
    m = bpy.data.materials.get(name)
    if m is not None:
        return m
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    b = nt.nodes["Principled BSDF"]
    at = nt.nodes.new("ShaderNodeAttribute")
    at.attribute_name = "tc"
    oi = nt.nodes.new("ShaderNodeObjectInfo")
    hsv = nt.nodes.new("ShaderNodeHueSaturation")
    nt.links.new(at.outputs["Color"], hsv.inputs["Color"])
    # per instance: value 0.75-1.25, hue +-0.02
    mv = nt.nodes.new("ShaderNodeMapRange")
    nt.links.new(oi.outputs["Random"], mv.inputs["Value"])
    mv.inputs["To Min"].default_value, mv.inputs["To Max"].default_value = 0.75, 1.25
    nt.links.new(mv.outputs["Result"], hsv.inputs["Value"])
    mh = nt.nodes.new("ShaderNodeMapRange")
    nt.links.new(oi.outputs["Random"], mh.inputs["Value"])
    mh.inputs["To Min"].default_value, mh.inputs["To Max"].default_value = 0.48, 0.52
    nt.links.new(mh.outputs["Result"], hsv.inputs["Hue"])
    col = hsv.outputs["Color"]
    if kind == "bush":  # leafy: a fine bump and dark gaps between leaf clusters (a lump read as a smooth stone)
        tc = nt.nodes.new("ShaderNodeTexCoord")
        vo = nt.nodes.new("ShaderNodeTexVoronoi")
        vo.inputs["Scale"].default_value = 28.0
        nt.links.new(tc.outputs["Object"], vo.inputs["Vector"])
        bp = nt.nodes.new("ShaderNodeBump")
        bp.inputs["Strength"].default_value = 0.7
        bp.inputs["Distance"].default_value = 0.02
        nt.links.new(vo.outputs["Distance"], bp.inputs["Height"])
        nt.links.new(bp.outputs["Normal"], b.inputs["Normal"])
        dk = nt.nodes.new("ShaderNodeMapRange")
        nt.links.new(vo.outputs["Distance"], dk.inputs["Value"])
        dk.inputs["From Min"].default_value, dk.inputs["From Max"].default_value = 0.0, 0.6
        dk.inputs["To Min"].default_value, dk.inputs["To Max"].default_value = 1.1, 0.75
        mx = nt.nodes.new("ShaderNodeMix")
        mx.data_type = "RGBA"
        mx.blend_type = "MULTIPLY"
        mx.inputs["Factor"].default_value = 1.0
        nt.links.new(col, mx.inputs["A"])
        cc = nt.nodes.new("ShaderNodeCombineColor")
        for k in range(3):
            nt.links.new(dk.outputs["Result"], cc.inputs[k])
        nt.links.new(cc.outputs["Color"], mx.inputs["B"])
        col = mx.outputs["Result"]
    if kind == "boulder" and sea is not None:  # wet: darker and glossier near the water
        geo = nt.nodes.new("ShaderNodeNewGeometry")
        sp = nt.nodes.new("ShaderNodeSeparateXYZ")
        nt.links.new(geo.outputs["Position"], sp.inputs["Vector"])
        wr = nt.nodes.new("ShaderNodeMapRange")
        nt.links.new(sp.outputs["Z"], wr.inputs["Value"])
        wr.inputs["From Min"].default_value, wr.inputs["From Max"].default_value = sea + 0.4, sea + 1.8
        wr.inputs["To Min"].default_value, wr.inputs["To Max"].default_value = 0.45, 1.0
        mx = nt.nodes.new("ShaderNodeMix")
        mx.data_type = "RGBA"
        mx.blend_type = "MULTIPLY"
        mx.inputs["Factor"].default_value = 1.0
        nt.links.new(col, mx.inputs["A"])
        cc = nt.nodes.new("ShaderNodeCombineColor")
        for k in range(3):
            nt.links.new(wr.outputs["Result"], cc.inputs[k])
        nt.links.new(cc.outputs["Color"], mx.inputs["B"])
        col = mx.outputs["Result"]
        rr = nt.nodes.new("ShaderNodeMapRange")
        nt.links.new(sp.outputs["Z"], rr.inputs["Value"])
        rr.inputs["From Min"].default_value, rr.inputs["From Max"].default_value = sea + 0.4, sea + 1.8
        rr.inputs["To Min"].default_value, rr.inputs["To Max"].default_value = 0.35, 0.85
        nt.links.new(rr.outputs["Result"], b.inputs["Roughness"])
    else:
        b.inputs["Roughness"].default_value = 0.85 if kind == "boulder" else 0.7
    nt.links.new(col, b.inputs["Base Color"])
    for k_ in ("Specular IOR Level", "Specular"):
        if k_ in b.inputs:
            b.inputs[k_].default_value = 0.25 if kind != "boulder" else 0.3
    return m


def _mesh_ob(name, verts, faces, cols, smooth=True):
    """An object from vertices, polygons and a per-vertex "tc" colour (linear)."""
    me = bpy.data.meshes.new(name)
    me.from_pydata([tuple(v) for v in verts], [], [tuple(f) for f in faces])
    a = me.color_attributes.new("tc", "FLOAT_COLOR", "POINT")
    a.data.foreach_set("color", np.c_[np.asarray(cols, float), np.ones(len(cols))].ravel())
    for f in me.polygons:
        f.use_smooth = smooth
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    return ob


def _tuft(rng, n, h, spread, lean, dry):
    """A grass tuft: n blades from a small root patch, each a curved strip (5 rows) narrowing to its tip, leaning out
    `lean` rad (more toward the tip), turned about its ROOT; green at the root to straw at the tip on dry blades."""
    V, F, C = [], [], []
    root, mid, tipg = np.array([0.025, 0.05, 0.01]), np.array([0.07, 0.12, 0.03]), np.array([0.10, 0.15, 0.04])
    straw = np.array([0.30, 0.24, 0.10])
    for i in range(n):
        a = rng.uniform(0, 2 * math.pi)
        r0 = spread * math.sqrt(rng.uniform(0, 1))
        base = np.array([r0 * math.cos(a), r0 * math.sin(a), -0.03])
        hh = h * rng.uniform(0.55, 1.15)
        ln = lean * rng.uniform(0.4, 1.3) + 0.9 * r0 / max(spread, 1e-6) * lean
        w = rng.uniform(0.006, 0.012)
        side = np.array([-math.sin(a), math.cos(a), 0.0])
        out = np.array([math.cos(a), math.sin(a), 0.0])
        d = rng.random() < dry
        k0 = len(V)
        p = base.copy()
        for j in range(5):
            t = j / 4
            ph = ln * (0.4 + 1.2 * t)  # (bending over toward the tip)
            if j:
                p = p + (hh / 4) * (math.sin(ph) * out + math.cos(ph) * np.array([0, 0, 1.0]))
            ww = w * (1 - t) ** 0.7 + 0.0005
            V += [p - ww * side, p + ww * side]
            c = (root * (1 - t) + mid * t) if t < 0.6 else mid * (1 - (t - 0.6) / 0.4) + tipg * (t - 0.6) / 0.4
            if d:
                c = c * (1 - t) + straw * t
            elif t > 0.75 and rng.random() < 0.15:
                c = c * 0.5 + straw * 0.5
            C += [c, c]
        for j in range(4):
            q = k0 + 2 * j
            F.append((q, q + 1, q + 3, q + 2))
    return np.array(V), F, np.array(C)


def _scrub(rng, v):
    """A coastal scrub bush (~1.1 m across, ~0.8 m tall): woody stems forking up and out from a root crown, and a few
    hundred small leaf clusters (flattened, jittered 20-face balls) along the twigs' ends and over a lumpy canopy
    shell, sparse enough that the dark inside and the twigs show between them. Built of lumps (14-22 smooth spheres)
    it read as a soft stone at a few metres. Sage grey-green, some clusters dry or grey, one variant in four with a
    few yellow flowers."""
    import bmesh
    bm = bmesh.new()
    sage = np.array([0.095, 0.125, 0.06]) * rng.uniform(0.85, 1.15)  # (linear; darker read as rubble at 10 m)
    wood = np.array([0.045, 0.035, 0.025])
    dry = np.array([0.11, 0.09, 0.06])
    flower = v == 1  # (one variant in four in flower: more read as rubble from 150 m)
    cols = []

    def tube(pts, r0, r1, sides=5):
        rings = []
        for i, p in enumerate(pts):
            t = i / (len(pts) - 1)
            d = pts[min(i + 1, len(pts) - 1)] - pts[max(i - 1, 0)]
            d = d / max(np.linalg.norm(d), 1e-9)
            a_ = np.cross(d, [0.0, 0.0, 1.0]) if abs(d[2]) < 0.95 else np.cross(d, [1.0, 0.0, 0.0])
            a_ /= np.linalg.norm(a_)
            b_ = np.cross(d, a_)
            r = r0 * (1 - t) + r1 * t
            rings.append([bm.verts.new(tuple(p + r * (math.cos(k * 2 * math.pi / sides) * a_ +
                                                   math.sin(k * 2 * math.pi / sides) * b_))) for k in range(sides)])
            cols.extend([wood] * sides)
        for ra, rb in zip(rings, rings[1:]):
            for k in range(sides):
                bm.faces.new((ra[k], ra[(k + 1) % sides], rb[(k + 1) % sides], rb[k]))

    # the canopy: a lumpy dome (a few lobes), as a radius per direction
    lobes = [(rng.uniform(0, 2 * math.pi), rng.uniform(0.15, 0.35)) for _ in range(int(rng.integers(3, 6)))]

    def canopy(az):
        return 0.5 * (1 + sum(h * math.cos(az - a0) ** 8 for a0, h in lobes))

    tips = []
    for _ in range(int(rng.integers(6, 10))):  # stems from the crown, forking once or twice
        az = rng.uniform(0, 2 * math.pi)
        out = np.array([math.cos(az), math.sin(az), 0.0])
        base = np.array([0.0, 0.0, -0.05]) + 0.06 * rng.normal(0, 1, 3) * [1, 1, 0]
        R = canopy(az) * rng.uniform(0.45, 0.8)
        top = np.array([0.0, 0.0, rng.uniform(0.3, 0.6)]) + out * R
        mid = base + 0.45 * (top - base) + np.array([0, 0, 0.12]) + 0.05 * rng.normal(0, 1, 3)
        pts = [base + (mid - base) * t for t in (0, 0.5, 1.0)] + [mid + (top - mid) * t for t in (0.5, 1.0)]
        tube(np.array(pts), 0.018, 0.006)
        tips.append(top)
        for _ in range(int(rng.integers(1, 3))):  # side twigs off the stem's upper half
            s0 = mid + (top - mid) * rng.uniform(0.0, 0.6)
            az2 = az + rng.uniform(-1.0, 1.0)
            e = s0 + rng.uniform(0.1, 0.22) * np.array([math.cos(az2), math.sin(az2), rng.uniform(0.4, 1.2)])
            tube(np.array([s0, 0.5 * (s0 + e) + 0.02 * rng.normal(0, 1, 3), e]), 0.007, 0.003, 4)
            tips.append(e)
    tips = np.array(tips)
    # leaf clusters: round each twig's end and over the canopy's shell down to the ground (biased outward: the inside
    # stays dark), small (big clusters read as crumpled paper)
    centres = [t + 0.07 * rng.normal(0, 1, 3) for t in tips for _ in range(5)]
    for _ in range(int(rng.integers(560, 720))):
        az = rng.uniform(0, 2 * math.pi)
        el = math.asin(rng.uniform(0.0, 1.0) ** 0.8)
        R = canopy(az) * (0.72 + 0.32 * rng.random() ** 0.4)
        centres.append(np.array([R * math.cos(el) * math.cos(az), R * math.cos(el) * math.sin(az),
                                 0.04 + 1.0 * R * math.sin(el)]))
    for c0 in centres:
        if rng.random() < 0.1:  # (gaps: twigs and the dark inside show through)
            continue
        r = rng.uniform(0.035, 0.07)
        res = bmesh.ops.create_icosphere(bm, subdivisions=1, radius=r, matrix=Matrix.Translation(tuple(c0)))
        sq = rng.uniform(0.45, 0.9)
        c = sage * rng.uniform(0.75, 1.3)
        u = rng.random()
        if u < 0.12:
            c = dry * rng.uniform(0.8, 1.2)
        elif u < 0.2:
            c = sage * 0.6 + np.array([0.07, 0.075, 0.06])  # (grey, silvery leaves)
        if flower and rng.random() < 0.15:
            c = np.array([0.30, 0.24, 0.04])
        for vert in res["verts"]:
            vert.co.z = c0[2] + (vert.co.z - c0[2]) * sq
            vert.co += Vector(rng.normal(0, 0.25 * r, 3))
            cols.append(c)
    bm.verts.index_update()
    V = np.array([tuple(vv.co) for vv in bm.verts])
    F = [tuple(vv.index for vv in f.verts) for f in bm.faces]
    bm.free()
    return V, F, cols


STREAM_KINDS = ("river_rock", "cobbles", "slab", "driftwood", "reeds", "litter", "sedge", "pebbles", "wrack")


def _lump(bm, rng, centre, size, rough, sub=2):
    """A rounded stone: an icosphere scaled to `size` (full extents x, y, z), turned about z, its surface varied by
    noise (`rough`), at `centre`. Returns its vertices."""
    import bmesh
    from mathutils import noise as mn
    res = bmesh.ops.create_icosphere(bm, subdivisions=sub, radius=0.5)
    off = Vector(rng.uniform(-50, 50, 3))
    a = rng.uniform(0, math.pi)
    ca, sa = math.cos(a), math.sin(a)
    for vert in res["verts"]:
        n = vert.co.normalized()
        f = 1 + rough * mn.fractal(n * 1.3 + off, 0.6, 2.0, 2)
        x, y, z = n.x * size[0] * 0.5 * f, n.y * size[1] * 0.5 * f, n.z * size[2] * 0.5 * f
        vert.co = Vector((centre[0] + x * ca - y * sa, centre[1] + x * sa + y * ca, centre[2] + z))
    return res["verts"]


def _stream_piece(kind, rng):
    """A stream clutter placeholder, 1 m across at scale 1 (its largest plan dimension), pivot at the ground with the
    piece part sunk: a water-worn boulder, a patch of cobbles, a flat bank slab, a bare log with a stub or two, a reed
    clump, a patch of leaf litter. Returns (V, F, colours, smooth)."""
    import bmesh
    if kind == "reeds":
        V, F, C = _tuft(rng, 70, 1.5, 0.32, 0.1, 0.3)
        V = np.asarray(V, float)
        V[:, :2] *= 1.0
        return V, F, np.asarray(C) * np.array([0.9, 1.0, 0.8]), True
    if kind == "sedge":  # (1 m across at scale 1: a dense arching tussock)
        V, F, C = _tuft(rng, 90, 1.0, 0.3, 0.55, 0.2)
        return np.asarray(V, float), F, np.asarray(C) * np.array([0.85, 1.0, 0.7]), True
    bm = bmesh.new()
    cols = []
    stone = lambda: np.array([0.085, 0.08, 0.07]) * rng.uniform(0.7, 1.5) * (1 + rng.normal(0, 0.06) * np.array([1, 0.2, -1]))
    if kind == "river_rock":
        hz = rng.uniform(0.5, 0.7)
        vs = _lump(bm, rng, (0, 0, 0.3 * hz), (1.0, rng.uniform(0.7, 0.9), hz), 0.12, 3)
        c = stone()
        cols += [c * (0.85 + 0.3 * rng.random())] * 0 + [c] * len(vs)
    elif kind == "slab":
        vs = _lump(bm, rng, (0, 0, 0.08), (1.0, rng.uniform(0.6, 0.85), rng.uniform(0.25, 0.35)), 0.22, 2)
        cols += [stone()] * len(vs)
    elif kind == "cobbles":
        for _ in range(int(rng.integers(8, 15))):
            r = 0.42 * math.sqrt(rng.random())
            a = rng.uniform(0, 2 * math.pi)
            sz = float(np.clip(rng.lognormal(math.log(0.13), 0.4), 0.06, 0.26))
            vs = _lump(bm, rng, (r * math.cos(a), r * math.sin(a), 0.18 * sz), (sz, sz * rng.uniform(0.65, 0.95),
                                                                               sz * rng.uniform(0.45, 0.7)), 0.08, 2)
            cols += [stone()] * len(vs)
    elif kind == "pebbles":
        for _ in range(int(rng.integers(14, 24))):
            r = 0.45 * math.sqrt(rng.random())
            a = rng.uniform(0, 2 * math.pi)
            sz = float(np.clip(rng.lognormal(math.log(0.07), 0.4), 0.03, 0.15))
            vs = _lump(bm, rng, (r * math.cos(a), r * math.sin(a), 0.1 * sz), (sz, sz * rng.uniform(0.6, 0.9),
                                                                              sz * rng.uniform(0.3, 0.5)), 0.05, 1)
            cols += [stone() * rng.uniform(0.9, 1.6)] * len(vs)
    elif kind == "wrack":  # (a dark ragged strip along +x)
        for _ in range(34):
            x = rng.uniform(-0.5, 0.5)
            sz = rng.uniform(0.08, 0.2)
            vs = _lump(bm, rng, (x, rng.normal(0, 0.05), 0.006), (sz, sz * 0.5, 0.015), 0.0, 1)
            cols += [np.array([0.03, 0.028, 0.012]) * rng.uniform(0.6, 1.6)] * len(vs)
    elif kind == "litter":
        for _ in range(26):
            r = 0.5 * math.sqrt(rng.random())
            a = rng.uniform(0, 2 * math.pi)
            sz = rng.uniform(0.05, 0.12)
            vs = _lump(bm, rng, (r * math.cos(a), r * math.sin(a), 0.004), (sz, sz * 0.5, 0.008), 0.0, 1)
            cols += [np.array([0.06, 0.04, 0.02]) * rng.uniform(0.6, 1.5)] * len(vs)
    else:  # driftwood: a bare log along +x, a little bent, tapering, with a branch stub or two
        wood = np.array([0.11, 0.095, 0.075]) * rng.uniform(0.75, 1.2)

        def tube(pts, r0, r1, sides=7):
            rings = []
            for i, p in enumerate(pts):
                t = i / (len(pts) - 1)
                d = pts[min(i + 1, len(pts) - 1)] - pts[max(i - 1, 0)]
                d = d / max(np.linalg.norm(d), 1e-9)
                a_ = np.cross(d, [0.0, 0.0, 1.0])
                a_ = a_ / max(np.linalg.norm(a_), 1e-9)
                b_ = np.cross(d, a_)
                r = r0 * (1 - t) + r1 * t
                rings.append([bm.verts.new(tuple(p + r * (math.cos(k * 2 * math.pi / sides) * a_ +
                                                       math.sin(k * 2 * math.pi / sides) * b_))) for k in range(sides)])
                cols.extend([wood * rng.uniform(0.85, 1.15)] * sides)
            for ra, rb in zip(rings, rings[1:]):
                for k in range(sides):
                    bm.faces.new((ra[k], ra[(k + 1) % sides], rb[(k + 1) % sides], rb[k]))
            for ring in (rings[0], rings[-1][::-1]):
                bm.faces.new(ring[::-1])
        r0 = rng.uniform(0.022, 0.04)
        bow = rng.uniform(-0.06, 0.06)
        pts = np.array([[x, bow * math.sin(math.pi * (x + 0.5)), r0 * 0.6 + 0.02 * math.sin(3 * x)]
                        for x in np.linspace(-0.5, 0.5, 7)])
        tube(pts, r0, r0 * rng.uniform(0.45, 0.8))
        for _ in range(int(rng.integers(1, 4))):
            x = rng.uniform(-0.3, 0.4)
            s0 = np.array([x, bow * math.sin(math.pi * (x + 0.5)), r0 * 0.6])
            az = rng.uniform(0.5, 1.3) * rng.choice([-1, 1])
            e = s0 + rng.uniform(0.12, 0.3) * np.array([math.cos(az), math.sin(az), rng.uniform(0.1, 0.6)])
            tube(np.array([s0, 0.5 * (s0 + e) + [0, 0, 0.02], e]), r0 * 0.4, r0 * 0.15, 5)
    bm.verts.index_update()
    V = np.array([tuple(vv.co) for vv in bm.verts])
    F = [tuple(vv.index for vv in f.verts) for f in bm.faces]
    bm.free()
    return V, F, np.array(cols), kind != "slab"


def _clutter_variant(kind, v, sea=None):
    """Variant v of a clutter placeholder (hidden; instanced): grass tufts (tussock: a dense clump ~0.45 m; tallgrass:
    a looser sheaf ~0.7 m), a coastal scrub bush (sage-green lumps, some in yellow flower, ~1 m), a boulder (a
    weathered lump, faceted by noise, flattened, its foot below ground)."""
    rng = np.random.default_rng(1000 * CLUTTER_KINDS.index(kind) + v)
    if kind in ("tussock", "tallgrass"):
        if kind == "tussock":
            V, F, C = _tuft(rng, 36, 0.42, 0.07, 0.5, 0.1)
        else:
            V, F, C = _tuft(rng, 22, 0.62, 0.16, 0.38, 0.12)
        ob = _mesh_ob(f"clutter_{kind}_{v}", V, F, C)
    elif kind == "bush":
        V, F, cols = _scrub(rng, v)
        ob = _mesh_ob(f"clutter_bush_{v}", V, F, np.array(cols))
    elif kind in STREAM_KINDS:
        V, F, C, smooth = _stream_piece(kind, rng)
        ob = _mesh_ob(f"clutter_{kind}_{v}", V, F, C, smooth=smooth)
    else:
        import bmesh
        from mathutils import noise as mn
        bm = bmesh.new()
        bmesh.ops.create_icosphere(bm, subdivisions=3, radius=0.5)
        sq = (rng.uniform(1.0, 1.4), rng.uniform(0.8, 1.05), rng.uniform(0.45, 0.7))
        off = Vector(rng.uniform(-50, 50, 3))
        for vert in bm.verts:
            n = vert.co.normalized()
            f = 1 + 0.22 * mn.fractal(n * 1.6 + off, 0.6, 2.0, 3) + 0.08 * mn.noise(n * 5.0 + off)
            vert.co = Vector((n.x * sq[0], n.y * sq[1], n.z * sq[2])) * 0.5 * f
            vert.co.z = max(vert.co.z, -0.22) + 0.06  # (a flat-ish foot, sunk into the ground)
        bm.verts.index_update()
        V = np.array([tuple(vv.co) for vv in bm.verts])
        F = [tuple(vv.index for vv in f.verts) for f in bm.faces]
        bm.free()
        base = np.array([0.05, 0.046, 0.04]) * rng.uniform(0.8, 1.2)
        C = base[None] * (0.85 + 0.3 * rng.random((len(V), 1)))
        ob = _mesh_ob(f"clutter_boulder_{v}", V, F, C, smooth=False)
    ob.data.materials.append(_clutter_mat(kind, sea))
    return ob


def _clutter_instance(points_ob, kind, sea=None):
    """Clutter on every vertex of points_ob: a variant picked at random, scaled by the vertex's "scale" (and "squash"
    in height), turned by its "yaw" (deg), all from terrain_ground.clutter."""
    ng = bpy.data.node_groups.new("clutter_" + kind, "GeometryNodeTree")
    ng.interface.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    ng.interface.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    N, L = ng.nodes, ng.links
    gi, go = N.new("NodeGroupInput"), N.new("NodeGroupOutput")
    inst = N.new("GeometryNodeInstanceOnPoints")
    L.new(gi.outputs[0], inst.inputs["Points"])
    coll = bpy.data.collections.new("clutter_" + kind)
    bpy.context.scene.collection.children.link(coll)
    for v in range(CLUTTER_VARIANTS):
        ob = _clutter_variant(kind, v, sea)
        for c in list(ob.users_collection):
            c.objects.unlink(ob)
        coll.objects.link(ob)
    coll.hide_render = True
    ci = N.new("GeometryNodeCollectionInfo")
    ci.inputs["Collection"].default_value = coll
    ci.inputs["Separate Children"].default_value = True
    ci.inputs["Reset Children"].default_value = True
    L.new(ci.outputs[0], inst.inputs["Instance"])
    inst.inputs["Pick Instance"].default_value = True
    pick = N.new("FunctionNodeRandomValue")
    pick.data_type = "INT"
    pick.inputs[4].default_value, pick.inputs[5].default_value = 0, CLUTTER_VARIANTS - 1
    L.new(pick.outputs[2], inst.inputs["Instance Index"])

    def attr(name):
        a = N.new("GeometryNodeInputNamedAttribute")
        a.data_type = "FLOAT"
        a.inputs["Name"].default_value = name
        return a.outputs["Attribute"]
    sc = N.new("ShaderNodeCombineXYZ")
    s_, q_ = attr("scale"), attr("squash")
    L.new(s_, sc.inputs["X"])
    L.new(s_, sc.inputs["Y"])
    mz = N.new("ShaderNodeMath")
    mz.operation = "MULTIPLY"
    L.new(s_, mz.inputs[0])
    L.new(q_, mz.inputs[1])
    L.new(mz.outputs[0], sc.inputs["Z"])
    L.new(sc.outputs["Vector"], inst.inputs["Scale"])
    rot = N.new("ShaderNodeCombineXYZ")
    rad = N.new("ShaderNodeMath")
    rad.operation = "RADIANS"
    L.new(attr("yaw"), rad.inputs[0])
    L.new(rad.outputs[0], rot.inputs["Z"])
    L.new(rot.outputs["Vector"], inst.inputs["Rotation"])
    L.new(inst.outputs["Instances"], go.inputs[0])
    points_ob.modifiers.new("clutter", "NODES").node_group = ng


def clutter(kind, rows, sea=None):
    """A points object for one clutter kind: rows [x, y, z, scale, yaw, squash], instanced (_clutter_instance)."""
    rows = np.asarray(rows, float).reshape(-1, 6)
    me = bpy.data.meshes.new("clutter_" + kind)
    me.vertices.add(len(rows))
    me.vertices.foreach_set("co", rows[:, :3].astype(np.float64).ravel())
    for k, name in ((3, "scale"), (4, "yaw"), (5, "squash")):
        a = me.attributes.new(name, "FLOAT", "POINT")
        a.data.foreach_set("value", rows[:, k].astype(np.float32))
    ob = bpy.data.objects.new("clutter_" + kind, me)
    bpy.context.scene.collection.objects.link(ob)
    _clutter_instance(ob, kind, sea)
    return ob


def _clutter_proto(kind):
    """(the old single placeholder: variant 0)"""
    ob = _clutter_variant(kind, 0)
    ob.hide_render = True
    ob.location = (0, 0, -1e4)
    return ob


def _proto(kind):
    """A low-poly tree, hidden from render, for the scatter to instance: a cone conifer or a round broadleaf."""
    if kind in ("cypress", "pine"):
        return _species(kind, 0)
    if kind in CLUTTER_KINDS:
        return _clutter_proto(kind)
    parts = []
    bpy.ops.mesh.primitive_cylinder_add(vertices=6, radius=0.45, depth=4, location=(0, 0, 2))
    parts.append(bpy.context.object)
    trunk = bpy.data.materials.new("trunk")
    trunk.diffuse_color = (0.12, 0.07, 0.04, 1)
    trunk.use_nodes = True
    trunk.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.12, 0.07, 0.04, 1)
    parts[-1].data.materials.append(trunk)
    if kind == "conifer":
        bpy.ops.mesh.primitive_cone_add(vertices=8, radius1=3.0, depth=13, location=(0, 0, 9))
        col = (0.025, 0.07, 0.03, 1)
    elif kind == "shrub":  # hedge shrubs: a low lumpy mass, set close they close up into a hedge
        parts[0].scale = (0.3, 0.3, 0.2)
        parts[0].location = (0, 0, 0.4)
        bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=2, radius=1.8, location=(0, 0, 1.5))
        bpy.context.object.scale = (1.0, 1.0, 0.8)
        col = (0.05, 0.10, 0.03, 1)
    elif kind == "fruit":  # orchard trees: small, round, low trunk
        parts[0].scale = (0.6, 0.6, 0.45)
        parts[0].location = (0, 0, 0.9)
        bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=2, radius=2.2, location=(0, 0, 3.2))
        col = (0.09, 0.16, 0.04, 1)
    else:
        bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=2, radius=4.5, location=(0, 0, 7.5))
        col = (0.07, 0.13, 0.03, 1)
    crown = bpy.data.materials.new("crown_" + kind)
    crown.use_nodes = True
    b = crown.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = col
    b.inputs["Roughness"].default_value = 0.8
    parts.append(bpy.context.object)
    for p_ in parts[1:]:  # every crown lobe (cypress and pine have several)
        p_.data.materials.append(crown)
    bpy.ops.object.select_all(action="DESELECT")
    for p in parts:
        p.select_set(True)
    bpy.context.view_layer.objects.active = parts[-1]
    # bake every part's own move/turn/scale into its mesh first: the instancer reads the joined mesh without the active
    # part's transform, so a scaled or turned last part (a cypress's flat crown, its leaning trunk) came out as a ball
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    bpy.ops.object.join()
    ob = bpy.context.object
    ob.name = "tree_" + kind
    ob.hide_render = True
    ob.location = (0, 0, -1e4)
    return ob


def _instance(points_ob, kind):
    """A tree on every vertex of points_ob, with a random size and turn."""
    ng = bpy.data.node_groups.new("inst_" + kind, "GeometryNodeTree")
    ng.interface.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    ng.interface.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    N, L = ng.nodes, ng.links
    gi, go = N.new("NodeGroupInput"), N.new("NodeGroupOutput")
    inst = N.new("GeometryNodeInstanceOnPoints")
    L.new(gi.outputs[0], inst.inputs["Points"])
    if kind in ("cypress", "pine"):  # a few shapes per species, picked at random per tree
        coll = bpy.data.collections.new("species_" + kind)
        bpy.context.scene.collection.children.link(coll)
        for v in range(VARIANTS):
            ob = _species(kind, v)
            for c in list(ob.users_collection):
                c.objects.unlink(ob)
            coll.objects.link(ob)
            ob.location = (0, 0, 0)
        coll.hide_render = True
        ci = N.new("GeometryNodeCollectionInfo")
        ci.inputs["Collection"].default_value = coll
        ci.inputs["Separate Children"].default_value = True
        ci.inputs["Reset Children"].default_value = True
        L.new(ci.outputs[0], inst.inputs["Instance"])
        inst.inputs["Pick Instance"].default_value = True
        pick = N.new("FunctionNodeRandomValue")
        pick.data_type = "INT"
        pick.inputs[4].default_value, pick.inputs[5].default_value = 0, VARIANTS - 1  # (the INT min/max sockets)
        L.new(pick.outputs[2], inst.inputs["Instance Index"])
    else:
        info = N.new("GeometryNodeObjectInfo")
        info.inputs["Object"].default_value = _proto(kind)
        L.new(info.outputs["Geometry"], inst.inputs["Instance"])
    size = N.new("FunctionNodeRandomValue")
    size.data_type = "FLOAT"
    size.inputs[2].default_value, size.inputs[3].default_value = 0.7, 1.3
    L.new(size.outputs[1], inst.inputs["Scale"])
    turn = N.new("FunctionNodeRandomValue")
    turn.data_type = "FLOAT_VECTOR"
    turn.inputs[1].default_value = (0, 0, 6.283)
    if kind == "cypress":  # wind-shaped: all lean the same way, downwind (inland from a westerly), give or take 20 deg
        turn.inputs[0].default_value = (0, 0, math.radians(10))
        turn.inputs[1].default_value = (0, 0, math.radians(50))
    L.new(turn.outputs[0], inst.inputs["Rotation"])
    L.new(inst.outputs["Instances"], go.inputs[0])
    points_ob.modifiers.new("trees", "NODES").node_group = ng


def _scatter(ground, kinds, per_m2=0.02):
    """Geometry nodes on the ground: for each tree kind, points distributed by its density attribute, a tree
    instanced on each with a random size and turn."""
    ng = bpy.data.node_groups.new("trees", "GeometryNodeTree")
    ng.interface.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    ng.interface.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    N, L = ng.nodes, ng.links
    gi, go = N.new("NodeGroupInput"), N.new("NodeGroupOutput")
    join = N.new("GeometryNodeJoinGeometry")
    L.new(gi.outputs[0], join.inputs[0])
    for i, kind in enumerate(kinds):
        attr = N.new("GeometryNodeInputNamedAttribute")
        attr.data_type = "FLOAT"
        attr.inputs["Name"].default_value = "trees_" + kind
        dist = N.new("GeometryNodeDistributePointsOnFaces")
        dist.distribute_method = "POISSON"  # spaced trees; the density factor input only exists in this mode
        dist.inputs["Distance Min"].default_value = 4.0
        dist.inputs["Density Max"].default_value = per_m2
        dist.inputs["Seed"].default_value = 7 + i
        L.new(gi.outputs[0], dist.inputs["Mesh"])
        L.new(attr.outputs["Attribute"], dist.inputs["Density Factor"])
        inst = N.new("GeometryNodeInstanceOnPoints")
        info = N.new("GeometryNodeObjectInfo")
        info.inputs["Object"].default_value = _proto(kind)
        L.new(dist.outputs["Points"], inst.inputs["Points"])
        L.new(info.outputs["Geometry"], inst.inputs["Instance"])
        size = N.new("FunctionNodeRandomValue")
        size.data_type = "FLOAT"
        # Random Value repeats socket names per data type: [vector min, max, float min, max, int min, max, ...]
        size.inputs[2].default_value, size.inputs[3].default_value = 0.6, 1.4
        size.inputs["Seed"].default_value = 3 + i
        L.new(size.outputs[1], inst.inputs["Scale"])
        turn = N.new("FunctionNodeRandomValue")
        turn.data_type = "FLOAT_VECTOR"
        turn.inputs[1].default_value = (0, 0, 6.283)
        L.new(turn.outputs[0], inst.inputs["Rotation"])
        L.new(inst.outputs["Instances"], join.inputs[0])
    L.new(join.outputs[0], go.inputs[0])
    mod = ground.modifiers.new("trees", "NODES")
    mod.node_group = ng


def _water_material(name):
    wm = bpy.data.materials.new(name)
    wm.use_nodes = True
    b = wm.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (0.07, 0.17, 0.2, 1)  # water scatters light back up (darker read as black from above)
    b.inputs["Roughness"].default_value = 0.25
    # a light swell: noise bump on the normal (a dead-flat surface was a perfect mirror)
    nt = wm.node_tree
    tc = nt.nodes.new("ShaderNodeTexCoord")
    mp = nt.nodes.new("ShaderNodeMapping")
    mp.inputs["Scale"].default_value = (0.25, 0.6, 0.25)  # (in metres: ripples ~4 m long; 30 m swells were too gentle to show)
    nz = nt.nodes.new("ShaderNodeTexNoise")
    nz.inputs["Scale"].default_value = 1.0
    nz.inputs["Detail"].default_value = 6.0
    bp = nt.nodes.new("ShaderNodeBump")
    bp.inputs["Strength"].default_value = 1.0
    bp.inputs["Distance"].default_value = 0.4
    nt.links.new(tc.outputs["Object"], mp.inputs["Vector"])
    nt.links.new(mp.outputs["Vector"], nz.inputs["Vector"])
    nt.links.new(nz.outputs["Fac"], bp.inputs["Height"])
    nt.links.new(bp.outputs["Normal"], b.inputs["Normal"])
    return wm


def props(props, names):
    """Sites carrying a prop, as stand-ins at their real size (scale cues): a disc golf basket, a tee pad, a blocky
    building with a hipped roof and window bands, else a small post. props: [[x, y, ground z, yaw deg]]."""
    pk = bpy.data.materials.new("prop")
    pk.use_nodes = True
    pk.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.9, 0.55, 0.02, 1)
    gm = bpy.data.materials.new("prop_metal")
    gm.use_nodes = True
    gm.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.55, 0.55, 0.58, 1)
    for (x, y, z, yaw), nm in zip(props, names):
        x, y, z = float(x), float(y), float(z)
        if "basket" in str(nm):  # a disc golf target: post, basket dish, chain band, yellow top band
            bpy.ops.mesh.primitive_cylinder_add(vertices=8, radius=0.03, depth=1.45, location=(x, y, z + 0.72))
            bpy.context.object.data.materials.append(gm)
            bpy.ops.mesh.primitive_cylinder_add(vertices=16, radius=0.33, depth=0.22, location=(x, y, z + 0.72))
            bpy.context.object.data.materials.append(gm)
            bpy.ops.mesh.primitive_cylinder_add(vertices=16, radius=0.28, depth=0.5, location=(x, y, z + 1.08))
            bpy.context.object.data.materials.append(gm)
            bpy.ops.mesh.primitive_cylinder_add(vertices=16, radius=0.31, depth=0.1, location=(x, y, z + 1.38))
            bpy.context.object.data.materials.append(pk)
        elif "tee" in str(nm):  # a tee pad: a flat slab 1.5 x 3 m, long side toward the basket
            bpy.ops.mesh.primitive_cube_add(size=1, location=(x, y, z + 0.03))
            o = bpy.context.object
            o.scale = (1.5, 3.0, 0.1)
            o.rotation_euler[2] = -math.radians(float(yaw))
            o.data.materials.append(gm)
        elif any(w in str(nm) for w in ("lodge", "building", "house", "clubhouse")):  # a blocky building
            bpy.ops.mesh.primitive_cube_add(size=1, location=(x, y, z + 4.5))
            o = bpy.context.object
            o.scale = (34.0, 16.0, 9.0)
            o.rotation_euler[2] = -math.radians(float(yaw))
            bm = bpy.data.materials.new("building")
            bm.use_nodes = True
            bm.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.55, 0.5, 0.42, 1)
            o.data.materials.append(bm)
            # a hipped roof: a four-sided cone turned square to the walls, then stretched over them
            bpy.ops.mesh.primitive_cone_add(vertices=4, radius1=1.0, depth=1.0, location=(0, 0, 0))
            r = bpy.context.object
            r.rotation_euler[2] = math.radians(45)
            bpy.ops.object.transform_apply(rotation=True)
            r.scale = (37.0 / 1.414, 19.0 / 1.414, 6.0)
            r.location = (x, y, z + 12.0)
            r.rotation_euler[2] = -math.radians(float(yaw))
            r.data.materials.append(_mat("roof", (0.16, 0.13, 0.12, 1), 0.7))
            for zz in (2.4, 6.4):  # a band of windows round each storey
                bpy.ops.mesh.primitive_cube_add(size=1, location=(x, y, z + zz))
                w = bpy.context.object
                w.scale = (34.3, 16.3, 1.5)
                w.rotation_euler[2] = -math.radians(float(yaw))
                w.data.materials.append(_mat("windows", (0.05, 0.07, 0.09, 1), 0.15))
        else:  # anything else: a small orange post
            bpy.ops.mesh.primitive_cylinder_add(vertices=6, radius=0.1, depth=1.2, location=(x, y, z + 0.6))
            bpy.context.object.data.materials.append(pk)

def run(job):
    for coll in (bpy.data.objects, bpy.data.meshes, bpy.data.cameras, bpy.data.lights, bpy.data.node_groups):
        for item in list(coll):
            coll.remove(item)
    d = np.load(job["mesh"])
    ground = _mesh("ground", d["verts"], d["faces"], d["colors"])
    m = bpy.data.materials.new("ground")
    m.use_nodes = True
    nt = m.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    attr = nt.nodes.new("ShaderNodeAttribute")
    attr.attribute_name = "col"
    nt.links.new(attr.outputs["Color"], bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.9
    # ground is matte: the default specular sheen at grazing angles (every view from a boat or a valley floor) lifted
    # dark cover to grey-brown (black lava read as brown rock)
    for k in ("Specular IOR Level", "Specular"):
        if k in bsdf.inputs:
            bsdf.inputs[k].default_value = 0.12
    # steep faces get a rock material's relief, as an engine's cliff material would: level beds and joints in the normal
    # (a heightfield face is smooth below its cell; faces read as plaster from close by)
    tc = nt.nodes.new("ShaderNodeTexCoord")
    mp = nt.nodes.new("ShaderNodeMapping")
    mp.inputs["Scale"].default_value = (0.08, 0.08, 0.9)  # stretched along the level: beds a metre or so apart
    nz = nt.nodes.new("ShaderNodeTexNoise")
    nz.inputs["Scale"].default_value = 1.0
    nz.inputs["Detail"].default_value = 4.0
    nz.inputs["Roughness"].default_value = 0.65
    vo = nt.nodes.new("ShaderNodeTexVoronoi")  # joints: blocks a few metres across
    vo.feature = "DISTANCE_TO_EDGE"
    vo.inputs["Scale"].default_value = 0.35
    geo = nt.nodes.new("ShaderNodeNewGeometry")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    steep = nt.nodes.new("ShaderNodeMapRange")  # 0 on flat ground, 1 on faces steeper than ~60 deg
    steep.inputs["From Min"].default_value, steep.inputs["From Max"].default_value = 0.8, 0.5
    add = nt.nodes.new("ShaderNodeMath")
    add.operation = "ADD"
    jt = nt.nodes.new("ShaderNodeMath")
    jt.operation = "MULTIPLY"
    jt.inputs[1].default_value = 0.6
    # a size spectrum: a few big blocks (~10 m) over the small ones (one size everywhere read as crumpled paper)
    vb = nt.nodes.new("ShaderNodeTexVoronoi")
    vb.feature = "DISTANCE_TO_EDGE"
    vb.inputs["Scale"].default_value = 0.09
    jb = nt.nodes.new("ShaderNodeMath")
    jb.operation = "MULTIPLY"
    jb.inputs[1].default_value = 2.5
    add2 = nt.nodes.new("ShaderNodeMath")
    add2.operation = "ADD"
    nt.links.new(tc.outputs["Object"], vb.inputs["Vector"])
    nt.links.new(vb.outputs["Distance"], jb.inputs[0])
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Distance"].default_value = 0.25
    nt.links.new(tc.outputs["Object"], mp.inputs["Vector"])
    nt.links.new(mp.outputs["Vector"], nz.inputs["Vector"])
    nt.links.new(tc.outputs["Object"], vo.inputs["Vector"])
    nt.links.new(vo.outputs["Distance"], jt.inputs[0])
    nt.links.new(nz.outputs["Fac"], add.inputs[0])
    nt.links.new(jt.outputs[0], add.inputs[1])
    nt.links.new(geo.outputs["Normal"], sep.inputs["Vector"])
    nt.links.new(sep.outputs["Z"], steep.inputs["Value"])
    nt.links.new(steep.outputs["Result"], bump.inputs["Strength"])
    nt.links.new(add.outputs[0], add2.inputs[0])
    nt.links.new(jb.outputs[0], add2.inputs[1])
    nt.links.new(add2.outputs[0], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    ground.data.materials.append(m)
    if "tree_xyz" in d.files and len(d["tree_xyz"]):  # the same tree instances the export writes
        for kind in sorted(set(d["tree_kind"].tolist())):
            pts = d["tree_xyz"][d["tree_kind"] == kind]
            for v in job["views"]:  # (an eye among trees rendered from inside a crown: all green)
                e = v["eye"]
                pts = pts[((pts[:, 0] - e[0]) ** 2 + (pts[:, 1] - e[1]) ** 2 > 7.0 ** 2) | (pts[:, 2] < e[2] - 20)]
            me = bpy.data.meshes.new("trees_" + kind)
            me.vertices.add(len(pts))
            me.vertices.foreach_set("co", pts.astype(np.float64).ravel())
            ob = bpy.data.objects.new("trees_" + kind, me)
            bpy.context.scene.collection.objects.link(ob)
            _instance(ob, kind)
    # ground beyond the frame, so the horizon isn't the sky's dark underside (it read as a sea)
    span = float(d["span"]) if "span" in d.files else 4000.0
    # a ring round the frame, never under it (a plane at the edge's height cut through a canyon and hid a valley's floor)
    # its inner edge is the frame's own edge (heights and all) sloping out to the far ground, so there's no gap to see
    # through where the frame's edge stands above it
    z0 = float(d["base"]) - 1 if "base" in d.files else 0.0
    V = d["verts"]
    nx = int(np.sum(V[:, 1] == V[0, 1]))
    ny = len(V) // nx
    g = np.arange(len(V)).reshape(ny, nx)
    loop = np.r_[g[0, :], g[1:, -1], g[-1, -2::-1], g[-2:0:-1, 0]]  # the boundary, anticlockwise
    inner = V[loop].astype(float)
    cx, cy = V[:, 0].mean(), V[:, 1].mean()
    out_d = inner[:, :2] - [cx, cy]
    far = np.c_[[cx, cy] + out_d / np.maximum(np.abs(out_d).max(1, keepdims=True), 1e-9) * 20 * span, np.full(len(loop), z0)]
    # the frame's edge carries on level for a while (a plateau stays a plateau, a valley floor a floor), then eases down
    def wrap_mean(a, k):  # a moving average round the loop (Blender's Python has no scipy)
        pad = np.concatenate([a[-k:], a, a[:k]])
        c = np.cumsum(np.concatenate([np.zeros((1,) + a.shape[1:]), pad]), axis=0)
        return (c[2 * k + 1:] - c[:-2 * k - 1]) / (2 * k + 1)

    mid = np.c_[[cx, cy] + out_d * 1.6, wrap_mean(inner[:, 2], 12)]
    verts_b = np.vstack([inner, mid, far])
    n = len(loop)
    tris = []
    for k in range(n):
        a, b = k, (k + 1) % n
        for off in (0, n):
            tris += [(off + a, off + n + a, off + n + b), (off + a, off + n + b, off + b)]
    if "sea" in d.files and np.isfinite(float(d["sea"])):  # the sea runs on flat past the frame (moved to its level below)
        verts_b[:, 2] = z0
    ecol = d["colors"][loop]
    soft = wrap_mean(ecol.astype(float), 30)  # (edge colours stretched out radially streaked)
    cols_b = np.vstack([ecol, soft, np.repeat(ecol.mean(0, keepdims=True), len(loop), 0)])
    plane = _mesh("beyond", verts_b, np.array(tris), cols_b)
    plane.data.polygons.foreach_set("use_smooth", [False] * len(plane.data.polygons))  # (long thin fans streaked)
    pm = bpy.data.materials.new("beyond")
    pm.use_nodes = True
    sea = float(d["sea"]) if "sea" in d.files else float("nan")
    b = pm.node_tree.nodes["Principled BSDF"]
    if np.isfinite(sea):  # a sea runs on past the frame: the plane is water at its level
        plane.location.z = sea - 0.3 - (float(d["base"]) - 1)  # (coincident with the water mesh, both rendered black)
        # the same water as in the frame (a glossier plane read as a pale shelf beside the frame's own sea)
        pm = _water_material("beyond_water")
    else:  # the edge's own colours carried out
        at = pm.node_tree.nodes.new("ShaderNodeAttribute")
        at.attribute_name = "col"
        pm.node_tree.links.new(at.outputs["Color"], b.inputs["Base Color"])
        b.inputs["Roughness"].default_value = 0.9
    plane.data.materials.append(pm)
    if "lw_pts" in d.files and len(d["lw_pts"]):  # stone walls and fences (below the grid): stand-ins on the ground
        _walls(d["lw_pts"], d["lw_piece"], d["lw_info"])
    if "markers" in d.files and len(d["markers"]):  # sites as thin red poles, to judge what a view sees
        mk = bpy.data.materials.new("marker")
        mk.use_nodes = True
        mk.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.8, 0.05, 0.03, 1)
        eyes = [v["eye"] for v in job["views"]]
        for x, y, z in d["markers"]:
            # (not where a camera stands: a view from a site's centre was inside its pole, all black)
            if any((x - e[0]) ** 2 + (y - e[1]) ** 2 < 4.0 ** 2 for e in eyes):
                continue
            bpy.ops.mesh.primitive_cylinder_add(vertices=6, radius=0.6, depth=12, location=(float(x), float(y), float(z) + 6))
            bpy.context.object.data.materials.append(mk)
    if "props" in d.files and len(d["props"]):  # sites carrying a prop: a small stand-in at its real size
        props(d["props"], d["prop_names"])
    if len(d["wfaces"]):
        foam = d["wfoam"] if "wfoam" in d.files else None
        water = _mesh("water", d["wverts"], d["wfaces"], None if foam is None else np.repeat(foam[:, None], 3, 1))
        wm = _water_material("water")
        nt = wm.node_tree
        b = nt.nodes["Principled BSDF"]
        if foam is not None:  # surf where it's shallow: white, rough
            at = nt.nodes.new("ShaderNodeAttribute")
            at.attribute_name = "col"
            sp = nt.nodes.new("ShaderNodeSeparateColor")
            nt.links.new(at.outputs["Color"], sp.inputs["Color"])
            mx = nt.nodes.new("ShaderNodeMix")
            mx.data_type = "RGBA"
            mx.inputs["A"].default_value = (0.07, 0.17, 0.2, 1)
            mx.inputs["B"].default_value = (0.85, 0.88, 0.88, 1)
            nt.links.new(sp.outputs[0], mx.inputs["Factor"])
            nt.links.new(mx.outputs["Result"], b.inputs["Base Color"])
            rm = nt.nodes.new("ShaderNodeMapRange")
            rm.inputs["To Min"].default_value, rm.inputs["To Max"].default_value = 0.25, 0.9
            nt.links.new(sp.outputs[0], rm.inputs["Value"])
            nt.links.new(rm.outputs["Result"], b.inputs["Roughness"])
        water.data.materials.append(wm)

    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.samples = job.get("samples", 24)
    scene.cycles.use_denoising = True
    scene.render.resolution_x, scene.render.resolution_y = job["size"]
    scene.view_settings.view_transform = "AgX"
    world = bpy.data.worlds.new("sky")
    scene.world = world
    world.use_nodes = True
    sky = world.node_tree.nodes.new("ShaderNodeTexSky")
    if hasattr(sky, "dust_density"):  # a clearer day: the default dust hazed the far sea into the sky
        sky.dust_density, sky.air_density = 0.3, 0.8
    world.node_tree.links.new(sky.outputs["Color"], world.node_tree.nodes["Background"].inputs["Color"])
    world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.12
    sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN"))
    sun.data.energy = 2.2
    sun.data.angle = 0.02
    scene.collection.objects.link(sun)
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
    span = float(np.ptp(d["verts"][:, :2], axis=0).max())
    cam.data.clip_start, cam.data.clip_end = max(0.05, span / 20000), span * 5
    scene.collection.objects.link(cam)
    scene.camera = cam
    for v in job["views"]:
        cam.location = Vector(v["eye"])
        cam.rotation_euler = (Vector(v["look"]) - Vector(v["eye"])).to_track_quat("-Z", "Y").to_euler()
        cam.data.angle = np.radians(v["fov"])
        b, h = np.radians(v.get("sun", (225, 28)))  # where the sun is: compass bearing, height (terrain_sun picks it)
        toward = Vector((np.cos(h) * np.sin(b), np.cos(h) * np.cos(b), np.sin(h)))
        sun.rotation_euler = (-toward).to_track_quat("-Z", "Y").to_euler()
        sky.sun_elevation, sky.sun_rotation = h, b  # the sky's glow and disc on the sun's side (5.1: rotation = bearing)
        scene.render.filepath = v["out"]
        bpy.ops.render.render(write_still=True)


if __name__ == "__main__":  # (blender_tiles imports the tree builders)
    run(json.load(open(sys.argv[sys.argv.index("--") + 1])))
