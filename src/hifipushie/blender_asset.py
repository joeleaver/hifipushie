"""Runs inside headless Blender for export_asset: the low-poly mesh with UVs, and a preview of the finished asset.

blender -b --factory-startup --python blender_asset.py -- job.json
Jobs:
  {"mode": "lowpoly", "mesh": high.npz, "out": low.npz, "triangles": n, "min_part": n, "texture": px,
   "margin": px, "angle": deg, "cone": deg, "symmetry": bool,
   "parts": {name: {"weight": triangle weight, "density": relative texels per metre, "atlas": index,
                    "focus": [[x, y, z, radius, density]]}}}
      Decimates all parts together to `triangles` (quadric collapse, mirrored across X), which sets each part's
      share; weights and the floor adjust those, and a part whose budget moved or whose mirrored collapse folded
      triangles over is decimated again on its own. Then per atlas: smart-projects its parts, cuts islands at
      focus regions, merges islands too thin or small to be worth their margin into a neighbour (when the
      merged chart still faces one way), scales every island to its density and packs them `margin` texels
      apart. Writes, per part, the vertices and per-corner uv / normal / MikkTSpace tangent + bitangent sign
      (exactly what the textures are baked against and the GLB carries), its atlas, and an info json.
  {"mode": "preview", "glb": path, "views": [{"dir", "up", "center", "scale", "out"}], "size": px, "hide": [part]}
      Imports the GLB (minus the hidden parts) and renders it with Cycles under a simple light rig, to check the
      textured asset.
"""

import json
import math
import sys
import time

import bmesh
import bpy
import numpy as np
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree


def _clear():
    for coll in (bpy.data.objects, bpy.data.meshes, bpy.data.cameras, bpy.data.lights, bpy.data.materials,
                 bpy.data.images):
        for item in list(coll):
            coll.remove(item)


def _mesh(name, verts, faces):
    me = bpy.data.meshes.new(name)
    me.vertices.add(len(verts))
    me.vertices.foreach_set("co", verts.astype(np.float32).ravel())
    me.loops.add(faces.size)
    me.loops.foreach_set("vertex_index", faces.astype(np.int32).ravel())
    me.polygons.add(len(faces))
    me.polygons.foreach_set("loop_start", np.arange(0, faces.size, 3, dtype=np.int32))
    me.update()
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    return ob


def _tri_arrays(ob):
    """(verts, triangles) of an object as arrays (one row per face if it is all triangles)."""
    me = ob.data
    co = np.empty(len(me.vertices) * 3, np.float32)
    me.vertices.foreach_get("co", co)
    me.calc_loop_triangles()
    vi = np.empty(len(me.loop_triangles) * 3, np.int32)
    me.loop_triangles.foreach_get("vertices", vi)
    return co.reshape(-1, 3).astype(np.float64), vi.reshape(-1, 3)


def _face_normals(V, F):
    n = np.cross(V[F[:, 1]] - V[F[:, 0]], V[F[:, 2]] - V[F[:, 0]])
    a = np.linalg.norm(n, axis=1)
    return n / np.maximum(a, 1e-30)[:, None], a / 2


def _folded(ob, tree, hn):
    """Area fraction of the object's faces facing against the nearest high-poly face: triangles the decimation
    turned over (they render black from outside)."""
    V, F = _tri_arrays(ob)
    n, a = _face_normals(V, F)
    cen = V[F].mean(1)
    bad = 0.0
    for i in range(len(F)):
        hit = tree.find_nearest(Vector(cen[i]))
        if hit[2] is not None and float(np.dot(n[i], hn[hit[2]])) < -0.5:
            bad += a[i]
    return bad / max(a.sum(), 1e-30)


def _decimate(ob, ratio, symmetry):
    mod = ob.modifiers.new("dec", "DECIMATE")
    mod.decimate_type = "COLLAPSE"
    mod.ratio = ratio
    mod.use_symmetry = symmetry
    mod.symmetry_axis = "X"
    bpy.context.view_layer.objects.active = ob
    bpy.ops.object.modifier_apply(modifier="dec")


def _clean(ob):
    bm = bmesh.new()  # collapse can leave slivers with no area (and so no normal): dissolve them
    bm.from_mesh(ob.data)
    bmesh.ops.dissolve_degenerate(bm, dist=1e-6, edges=bm.edges)
    bmesh.ops.delete(bm, geom=[f for f in bm.faces if f.calc_area() < 1e-12], context="FACES")
    bm.to_mesh(ob.data)
    bm.free()
    ob.modifiers.new("tri", "TRIANGULATE")
    bpy.context.view_layer.objects.active = ob
    bpy.ops.object.modifier_apply(modifier="tri")


# ---- charts ----------------------------------------------------------------------------------------------------

def _islands(bm):
    """Island label per face: faces joined across every edge that isn't a seam."""
    parent = np.arange(len(bm.faces))

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a
    for e in bm.edges:
        lf = e.link_faces
        if not e.seam and len(lf) == 2:
            a, b = find(lf[0].index), find(lf[1].index)
            if a != b:
                parent[a] = b
    return np.array([find(i) for i in range(len(bm.faces))])


def _charts(bm, texel, cone_deg, min_width=6.0, min_area=100.0, group=None):
    """Islands from the seams, with the poor ones merged: an island narrower than `min_width` texels (2 area /
    perimeter) or smaller than `min_area` texels^2 costs more in margin than it holds, so it joins the neighbour
    it shares the most boundary with, as long as every face of the merged chart stays within `cone_deg` of the
    chart's mean normal (so it can be projected flat without folding over). Returns {chart: face indices} and
    the set of charts that changed (they need projecting again)."""
    F = len(bm.faces)
    N = np.array([f.normal for f in bm.faces]).reshape(F, 3)
    A = np.array([f.calc_area() for f in bm.faces])
    lab = _islands(bm)
    members = {}
    for i, lb in enumerate(lab):
        members.setdefault(int(lb), []).append(i)
    members = {k: np.array(v) for k, v in members.items()}
    area = {k: float(A[v].sum()) for k, v in members.items()}
    nsum = {k: (N[v] * A[v, None]).sum(0) for k, v in members.items()}
    per = {k: 0.0 for k in members}
    shared = {}
    for e in bm.edges:
        lf = e.link_faces
        ln = e.calc_length()
        if len(lf) == 2:
            a, b = int(lab[lf[0].index]), int(lab[lf[1].index])
            if a != b:
                s = shared.setdefault((min(a, b), max(a, b)), [0.0, []])
                s[0] += ln
                s[1].append(e.index)
                per[a] += ln
                per[b] += ln
        elif len(lf) == 1:
            per[int(lab[lf[0].index])] += ln
    nbr = {k: set() for k in members}
    for a, b in shared:
        nbr[a].add(b)
        nbr[b].add(a)
    cosc = math.cos(math.radians(cone_deg))

    def poor(k):
        return 2 * area[k] / max(per[k], 1e-12) < min_width * texel or area[k] < min_area * texel * texel

    changed = set()
    bm.edges.ensure_lookup_table()
    again = True
    while again:
        again = False
        for k in sorted(members, key=lambda k: area[k]):
            if k not in members or not poor(k):
                continue
            for o in sorted(nbr[k], key=lambda o: -shared[(min(k, o), max(k, o))][0]):
                m = nsum[k] + nsum[o]
                nm = np.linalg.norm(m)
                idx = np.concatenate([members[k], members[o]])
                if nm < 1e-12 or (N[idx] @ (m / nm)).min() < cosc or (
                        group is not None and group[members[k][0]] != group[members[o][0]]):
                    continue
                ln, es = shared.pop((min(k, o), max(k, o)))
                for ei in es:
                    bm.edges[ei].seam = False
                members[o] = idx
                area[o] += area.pop(k)
                nsum[o] = m
                per[o] += per.pop(k) - 2 * ln
                del members[k]
                for x in nbr.pop(k):
                    if x == o:
                        continue
                    s = shared.pop((min(k, x), max(k, x)))
                    ox = (min(o, x), max(o, x))
                    if ox in shared:
                        shared[ox][0] += s[0]
                        shared[ox][1] += s[1]
                    else:
                        shared[ox] = s
                    nbr[x].discard(k)
                    nbr[x].add(o)
                    nbr[o].add(x)
                nbr[o].discard(k)
                changed.discard(k)
                changed.add(o)
                again = True
                break
    return members, nsum, changed


def _unwrap_atlas(obs, cfg, job):
    """Smart project, merge poor islands, project merged charts along their mean normal, scale every island to
    its part's density, pack. All objects in `obs` share the atlas."""
    size, margin = job["texture"], job["margin"] / job["texture"]
    bpy.ops.object.select_all(action="DESELECT")
    for ob in obs:
        ob.select_set(True)
    bpy.context.view_layer.objects.active = obs[0]
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    ta = time.time()
    bpy.ops.uv.smart_project(angle_limit=math.radians(job.get("angle", 66)), island_margin=margin,
                             correct_aspect=True, scale_to_bounds=False)
    bpy.ops.uv.select_all(action="SELECT")
    bpy.ops.uv.seams_from_islands()
    tb = time.time()
    # texel size (density-weighted metres) the atlas would have at half fill: what "thin" and "small" refer to
    load = sum(cfg[ob.name]["density"] ** 2 * sum(p.area for p in ob.data.polygons) for ob in obs)
    stats = {}
    for ob in obs:
        d = cfg[ob.name]["density"]
        texel = math.sqrt(load / 0.5) / size / d
        bm = bmesh.from_edit_mesh(ob.data)
        bm.faces.ensure_lookup_table()
        uvl = bm.loops.layers.uv.verify()
        # focus regions (a face, a hand): faces whose centre is inside one get its density; seams along their
        # edge so no island straddles it, and no merging across it
        focus = cfg[ob.name].get("focus") or []
        group = np.full(len(bm.faces), -1)
        if focus:
            cen = np.array([f.calc_center_median() for f in bm.faces]).reshape(-1, 3)
            for gi, (x, y, zz, r, _) in enumerate(focus):
                inside = np.linalg.norm(cen - [x, y, zz], axis=1) <= r
                group[inside & (group < 0)] = gi
            for e in bm.edges:
                lf = e.link_faces
                if len(lf) == 2 and group[lf[0].index] != group[lf[1].index]:
                    e.seam = True
        members, nsum, changed = _charts(bm, texel, job.get("cone", 75), group=group)
        for k, idx in members.items():
            faces = [bm.faces[i] for i in idx]
            g = group[idx[0]]
            dk = d * (focus[g][4] if g >= 0 else 1.0)
            if k in changed:  # merged: project along the chart's mean normal
                m = nsum[k] / np.linalg.norm(nsum[k])
                ref = np.array([0.0, 0.0, 1.0]) if abs(m[2]) < 0.9 else np.array([1.0, 0.0, 0.0])
                u = np.cross(m, ref)
                u /= np.linalg.norm(u)
                v = np.cross(m, u)
                for f in faces:
                    for lp in f.loops:
                        co = np.array(lp.vert.co)
                        lp[uvl].uv = (float(co @ u), float(co @ v))
            # scale the island so its uv area is its surface area times density^2 (pack keeps relative scale)
            a3 = sum(f.calc_area() for f in faces)
            auv = 0.0
            for f in faces:
                q = [lp[uvl].uv for lp in f.loops]
                auv += abs((q[1] - q[0]).cross(q[2] - q[0])) / 2
            if auv > 1e-20 and a3 > 0:
                s = dk * math.sqrt(a3 / auv)
                for f in faces:
                    for lp in f.loops:
                        lp[uvl].uv = lp[uvl].uv * s
        stats[ob.name] = {"islands": len(members)}
        bmesh.update_edit_mesh(ob.data)
    tc = time.time()
    bpy.ops.uv.select_all(action="SELECT")
    bpy.ops.uv.pack_islands(rotate=True, scale=True, margin_method="FRACTION", margin=margin,
                            shape_method="CONCAVE")
    bpy.ops.object.mode_set(mode="OBJECT")
    TIMES.append({"project_s": round(tb - ta, 1), "charts_s": round(tc - tb, 1), "pack_s": round(time.time() - tc, 1)})
    return stats


TIMES = []


def _sub(verts, faces, sel):
    """The vertices and re-indexed faces of a subset of faces."""
    fc = faces[sel]
    used = np.unique(fc)
    remap = np.full(len(verts), -1, np.int64)
    remap[used] = np.arange(len(used))
    return verts[used].astype(np.float64), remap[fc]


def _reduce(name, V, F, ratio, symmetry):
    """Collapse-decimate (V, F) to `ratio` of its faces. Mirrored across X when asked, unless that turns triangles
    over: Blender's mirrored collapses skip its fold check, and on flat faces they fold (black triangles)."""
    ob = _mesh(name, V, F)
    if ratio >= 1.0:
        return ob, False
    if symmetry:
        _decimate(ob, ratio, True)
        tree = BVHTree.FromPolygons(V.tolist(), F.tolist(), all_triangles=True)
        if _folded(ob, tree, _face_normals(V, F)[0]) == 0:
            return ob, True
        bpy.data.objects.remove(ob)
        ob = _mesh(name, V, F)
    _decimate(ob, ratio, False)
    return ob, False


def budgets(counts, faces, weights, total, floor):
    """Triangles per part: the joint decimation's counts (what each part needs for one geometric error everywhere)
    scaled by each part's weight and renormalised to `total`, but at least `floor` (or all it has) and never more
    than it has."""
    share = {pn: weights[pn] * max(counts.get(pn, 0), 1) for pn in faces}
    fixed = {}
    for _ in range(len(share) + 1):
        free = [pn for pn in share if pn not in fixed]
        if not free:
            break
        left = max(total - sum(fixed.values()), 0)
        tot = sum(share[pn] for pn in free)
        want = {pn: left * share[pn] / tot for pn in free}
        lo = {pn: min(floor, faces[pn]) for pn in free}
        clamp = {pn: lo[pn] if w < lo[pn] else faces[pn] for pn, w in want.items() if w < lo[pn] or w > faces[pn]}
        fixed.update(clamp or want)
        if not clamp:
            break
    return {pn: int(round(fixed[pn])) for pn in faces}


def lowpoly(job):
    _clear()
    t0 = time.time()
    z = np.load(job["mesh"])
    verts, faces, part = z["verts"], z["faces"], z["part"]
    all_names = [str(n) for n in z["part_names"]]
    cfg = job["parts"]
    fpart = part[faces[:, 0]]
    names = [pn for i, pn in enumerate(all_names) if pn in cfg and (fpart == i).any()]  # skip parts all hidden
    pidx = {pn: all_names.index(pn) for pn in names}
    nfaces = {pn: int((fpart == pidx[pn]).sum()) for pn in names}
    total = int(job["triangles"])
    sym = job.get("symmetry", True)

    # 1. one quadric decimation of all parts together: it spends triangles where they cut the geometric error
    #    most, so flat walls get few and small round things enough (area shares starve those). Parts share no
    #    vertices, so collapses never merge them; a face attribute carries the part through.
    keep = np.isin(fpart, [pidx[pn] for pn in names])
    V, F = _sub(verts, faces, keep)
    pid_of = np.full(len(all_names), -1)
    for k, pn in enumerate(names):
        pid_of[pidx[pn]] = k
    joint = _mesh("joint", V, F)
    joint.data.attributes.new("pid", "INT", "FACE").data.foreach_set("value", pid_of[fpart[keep]].astype(np.int32))
    ratio = min(1.0, total / len(F))
    if ratio < 1.0:
        _decimate(joint, ratio, sym)
    _clean(joint)
    Vj, Fj = _tri_arrays(joint)
    jpart = np.empty(len(Fj), np.int32)
    joint.data.attributes["pid"].data.foreach_get("value", jpart)
    counts = {pn: int((jpart == k).sum()) for k, pn in enumerate(names)}
    bpy.data.objects.remove(joint)
    t1 = time.time()

    # 2. per-part budgets from those counts, the weights and a floor. A part keeps its share of the joint result
    #    unless its budget moved or the mirrored collapse folded some of its triangles over (Blender skips its
    #    fold check for mirrored collapses; on flat faces they turn over and render black): then it is
    #    decimated again on its own
    want = budgets(counts, nfaces, {pn: cfg[pn]["weight"] for pn in names}, total, int(job.get("min_part", 300)))
    obs, info = [], {}
    for k, pn in enumerate(names):
        Vh, Fh = _sub(verts, faces, fpart == pidx[pn])
        redo, s = abs(want[pn] - counts[pn]) > 0.1 * max(counts[pn], 1), sym and ratio < 1.0
        if not redo:
            ob = _mesh(pn, *_sub(Vj, Fj, jpart == k))
            if s and _folded(ob, BVHTree.FromPolygons(Vh.tolist(), Fh.tolist(), all_triangles=True),
                             _face_normals(Vh, Fh)[0]) > 0:
                bpy.data.objects.remove(ob)
                redo, s = True, False
        if redo:
            ob, s = _reduce(pn, Vh, Fh, want[pn] / len(Fh), s)
            _clean(ob)
        ob.data.shade_smooth()
        obs.append(ob)
        info[pn] = {"symmetric": s, "joint_count": counts[pn], "budget": want[pn]}
    t1b = time.time()

    atlases = {}
    for ob in obs:
        ob.data.uv_layers.new(name="UVMap")
        atlases.setdefault(cfg[ob.name]["atlas"], []).append(ob)
    for group in atlases.values():
        for pn, s in _unwrap_atlas(group, cfg, job).items():
            info[pn].update(s)
    t2 = time.time()

    out = {"part_names": np.array([ob.name for ob in obs]), "atlas": np.array([cfg[ob.name]["atlas"] for ob in obs]),
           "info": np.array(json.dumps({"parts": info, "joint_s": t1 - t0, "decimate_s": t1b - t0,
                                        "unwrap_s": t2 - t1b, "unwrap": TIMES}))}
    for i, ob in enumerate(obs):
        me = ob.data
        me.calc_tangents(uvmap="UVMap")
        nl = len(me.loops)
        vi = np.empty(nl, np.int32)
        me.loops.foreach_get("vertex_index", vi)
        co = np.empty(len(me.vertices) * 3, np.float32)
        me.vertices.foreach_get("co", co)
        uv = np.empty(nl * 2, np.float32)
        me.uv_layers["UVMap"].data.foreach_get("uv", uv)
        nrm = np.empty(nl * 3, np.float32)
        me.loops.foreach_get("normal", nrm)
        tan = np.empty(nl * 3, np.float32)
        me.loops.foreach_get("tangent", tan)
        sgn = np.empty(nl, np.float32)
        me.loops.foreach_get("bitangent_sign", sgn)
        out.update({f"{i}_verts": co.reshape(-1, 3), f"{i}_corner_vert": vi, f"{i}_uv": uv.reshape(-1, 2),
                    f"{i}_normal": nrm.reshape(-1, 3), f"{i}_tangent": tan.reshape(-1, 3), f"{i}_sign": sgn})
    np.savez(job["out"], **out)


def preview(job):
    _clear()
    bpy.ops.import_scene.gltf(filepath=job["glb"])
    for ob in list(bpy.data.objects):  # parts left out, e.g. the roof and walls to see an interior
        if any(ob.name == h or ob.name.endswith("_" + h) for h in job.get("hide", [])):
            bpy.data.objects.remove(ob)
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = job.get("samples", 24)
    scene.cycles.use_denoising = True
    scene.render.resolution_x = scene.render.resolution_y = job.get("size", 512)
    scene.render.film_transparent = False
    scene.view_settings.view_transform = "Standard"
    scene.world = scene.world or bpy.data.worlds.new("w")
    scene.world.use_nodes = True
    bg = scene.world.node_tree.nodes.get("Background")
    bg.inputs["Color"].default_value = (0.23, 0.24, 0.27, 1)
    bg.inputs["Strength"].default_value = 0.6
    lights = [((-1.0, -1.2, 1.4), 3.2, 0.03), ((1.4, -0.6, 0.6), 1.2, 0.15), ((0.3, 1.5, 1.0), 2.0, 0.05)]
    for k, (d, e, ang) in enumerate(lights):  # key, fill, rim: sun lamps, so the model's scale doesn't matter
        ld = bpy.data.lights.new(f"sun{k}", "SUN")
        ld.energy, ld.angle = e, ang
        lo = bpy.data.objects.new(f"sun{k}", ld)
        lo.rotation_euler = Vector(d).to_track_quat("Z", "Y").to_euler()
        scene.collection.objects.link(lo)
    cam_data = bpy.data.cameras.new("cam")
    cam_data.type = "ORTHO"
    cam_data.clip_start, cam_data.clip_end = 0.001, 1000
    cam = bpy.data.objects.new("cam", cam_data)
    scene.collection.objects.link(cam)
    scene.camera = cam
    for v in job["views"]:
        d = Vector(v["dir"]).normalized()
        up = Vector(v["up"])
        right = up.cross(d).normalized()
        up = d.cross(right).normalized()
        cam.matrix_world = Matrix.Translation(Vector(v["center"]) + d * 50) @ Matrix((right, up, d)).transposed().to_4x4()
        cam_data.ortho_scale = v["scale"]
        scene.render.filepath = v["out"]
        bpy.ops.render.render(write_still=True)


job = json.load(open(sys.argv[sys.argv.index("--") + 1]))
{"lowpoly": lowpoly, "preview": preview}[job["mode"]](job)
