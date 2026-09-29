"""Runs inside headless Blender: a terrain grid mesh (vertex colours) and its lakes, rendered in Cycles
under a sun (per view [bearing, height] deg: terrain_sun picks it) and sky from perspective cameras. Job: {"mesh",
"size": [w, h], "samples", "views": [{"eye": [x, y, z], "look": [x, y, z], "fov": deg, "sun": [b, h], "out": png}]}."""
import math

import json
import sys

import bpy
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


def _proto(kind):
    """A low-poly tree, hidden from render, for the scatter to instance: a cone conifer or a round broadleaf."""
    if kind in ("cypress", "pine"):
        return _species(kind, 0)
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
        pk = bpy.data.materials.new("prop")
        pk.use_nodes = True
        pk.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.9, 0.55, 0.02, 1)
        gm = bpy.data.materials.new("prop_metal")
        gm.use_nodes = True
        gm.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.55, 0.55, 0.58, 1)
        for (x, y, z, yaw), nm in zip(d["props"], d["prop_names"]):
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
