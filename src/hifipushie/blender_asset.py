"""Runs inside headless Blender for export_asset: the low-poly mesh with UVs, and a preview of the finished asset.

blender -b --factory-startup --python blender_asset.py -- job.json
Jobs:
  {"mode": "lowpoly", "mesh": high.npz, "out": low.npz, "triangles": n, "min_part": n, "voxel": scene voxel,
   "textures": {atlas index: px}, "margins": {atlas index: px}, "angle": deg, "cone": deg, "symmetry": bool,
   "parts": {name: {"weight": triangle weight, "density": relative texels per metre, "atlas": index,
                    "focus": [[x, y, z, radius, density]], "copies": instances drawn (1)}}}
      Flat regions (faces within 0.5 deg of a seed face's normal and a quarter voxel of its plane) are dissolved
      to ngons and retriangulated first, so the collapse spends nothing on them. Then decimates all parts together
      to `triangles` drawn (quadric collapse, mirrored across X), which sets each part's share; weights and the
      floor (shrunk by the part's flat share) adjust those, and a part whose budget moved or whose mirrored collapse folded
      triangles over is decimated again on its own. Then per atlas: smart-projects its parts, cuts islands at
      focus regions, merges islands too thin or small to be worth their margin into a neighbour (when the
      merged chart still faces one way), joins neighbours sharing a long border when their union is a disk that
      unwraps evenly (`_grow`), scales every island to its density and packs them `margin` texels
      apart. Writes, per part, the vertices and per-corner uv / normal / MikkTSpace tangent + bitangent sign
      (exactly what the textures are baked against and the GLB carries), its atlas, and an info json.
  {"mode": "preview", "glb": path, "views": [{"dir", "up", "center", "scale", "out"}], "size": px, "hide": [part]}
      Imports the GLB (minus the hidden parts) and renders it with Cycles under a simple light rig, to check the
      textured asset.
"""

import json
import os
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


def _poly_arrays(ob):
    """(verts, loop vertex indices, loop starts) of an object: its polygons as they are (ngons too)."""
    me = ob.data
    co = np.empty(len(me.vertices) * 3, np.float32)
    me.vertices.foreach_get("co", co)
    vi = np.empty(len(me.loops), np.int32)
    me.loops.foreach_get("vertex_index", vi)
    ls = np.empty(len(me.polygons), np.int32)
    me.polygons.foreach_get("loop_start", ls)
    return co.reshape(-1, 3), vi, ls


def _poly_mesh(name, verts, loops, starts):
    me = bpy.data.meshes.new(name)
    me.vertices.add(len(verts))
    me.vertices.foreach_set("co", np.asarray(verts, np.float32).ravel())
    me.loops.add(len(loops))
    me.loops.foreach_set("vertex_index", np.asarray(loops, np.int32))
    me.polygons.add(len(starts))
    me.polygons.foreach_set("loop_start", np.asarray(starts, np.int32))
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


# ---- planar pre-pass -------------------------------------------------------------------------------------------
# Blender's collapse keeps roughly a fixed fraction of every part's faces, so a flat wall kept thousands of
# triangles with zero error while round things starved. Flat regions are dissolved to ngons first, so the collapse
# only spends its budget where the surface bends.

def _flat_mesh(name, V, L, S, pid=None):
    """A part's polygons (its flat regions as single ngons, from `planar.flatten`, run before Blender starts)
    triangulated again: the collapse then spends nothing on flat walls. `pid`: a part id per polygon, kept as a face
    attribute through the triangulation."""
    ob = _poly_mesh(name, V, L, np.r_[0, np.cumsum(S)[:-1]])
    ob.data.update(calc_edges=True)
    if pid is not None:
        ob.data.attributes.new("pid", "INT", "FACE").data.foreach_set("value", np.asarray(pid, np.int32))
    tri = ob.modifiers.new("tri", "TRIANGULATE")
    tri.quad_method, tri.ngon_method = "BEAUTY", "BEAUTY"
    bpy.context.view_layer.objects.active = ob
    bpy.ops.object.modifier_apply(modifier="tri")
    return ob


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


def _disk(faces) -> bool:
    """A chart can be unwrapped in one piece without cutting it when it is a disk: one boundary, no holes
    (Euler characteristic V - E + F = 1). Merging round a log would close it into a tube (0)."""
    vs, es = set(), set()
    for f in faces:
        vs.update(v.index for v in f.verts)
        es.update(e.index for e in f.edges)
    return len(vs) - len(es) + len(faces) == 1


def _stretch(bm, uvl, idx):
    """How unevenly an unwrapped chart spends its texels: area-weighted mean of (r + 1/r) / 2 over its faces,
    r = uv area / surface area normalised over the chart (1 = even), and whether any face turned over."""
    a3, au = [], []
    for i in idx:
        q = [lp[uvl].uv for lp in bm.faces[i].loops]
        au.append(sum((q[j] - q[0]).cross(q[j + 1] - q[0]) for j in range(1, len(q) - 1)) / 2)
        a3.append(bm.faces[i].calc_area())
    a3, au = np.array(a3), np.array(au)
    if au.sum() < 0:
        au = -au
    if a3.sum() <= 0 or au.sum() <= 0:
        return np.inf, True
    flipped = au[a3 > 1e-12 * a3.sum()].min(initial=1.0) <= 0
    r = np.maximum(au / au.sum(), 1e-12) / np.maximum(a3 / a3.sum(), 1e-12)
    return float((a3 * (r + 1 / r) / 2).sum() / a3.sum()), bool(flipped)


def _grow(obs, state, limit, share=0.3, rounds=12):
    """Join neighbouring charts that share a long border (a log's strips, a pot's wedges): each round pairs every
    chart with the neighbour it shares most of its perimeter with (at least `share` of the shorter one's),
    keeps pairs whose union is a disk, unwraps them all at once (conformal, along the seams) and accepts the
    ones that come out even (`_stretch` <= limit, nothing turned over); the rest get their seams and uvs back.
    Returns the number of joins per object. Accepted charts keep their unwrap (not projected flat)."""
    grown = {ob.name: 0 for ob in obs}
    for _ in range(rounds):
        trial = {}
        for ob in obs:
            members, group = state[ob.name]
            bm = bmesh.from_edit_mesh(ob.data)
            bm.faces.ensure_lookup_table()
            bm.edges.ensure_lookup_table()
            uvl = bm.loops.layers.uv.verify()
            chart = {}
            for k, idx in members.items():
                for i in idx:
                    chart[int(i)] = k
            per, shared = {k: 0.0 for k in members}, {}
            for e in bm.edges:
                lf = e.link_faces
                if len(lf) == 1:
                    per[chart[lf[0].index]] += e.calc_length()
                elif len(lf) == 2:
                    a, b = chart[lf[0].index], chart[lf[1].index]
                    if a != b:
                        ln = e.calc_length()
                        per[a] += ln
                        per[b] += ln
                        s = shared.setdefault((min(a, b), max(a, b)), [0.0, []])
                        s[0] += ln
                        s[1].append(e.index)
            cand = sorted(((ln / max(min(per[a], per[b]), 1e-12), a, b, es) for (a, b), (ln, es) in shared.items()),
                          key=lambda c: -c[0])
            used, pairs = set(), []
            for ratio, a, b, es in cand:
                if ratio < share:
                    break
                if a in used or b in used or group[members[a][0]] != group[members[b][0]]:
                    continue
                idx = np.concatenate([members[a], members[b]])
                if not _disk([bm.faces[i] for i in idx]):
                    continue
                used.update((a, b))
                old = {int(i): [lp[uvl].uv.copy() for lp in bm.faces[i].loops] for i in idx}
                for ei in es:
                    bm.edges[ei].seam = False
                pairs.append((a, b, idx, es, old))
            for f in bm.faces:
                f.select = False
            for p in pairs:
                for i in p[2]:
                    bm.faces[i].select = True
            bm.select_flush_mode()
            bmesh.update_edit_mesh(ob.data)
            trial[ob.name] = pairs
        if not any(trial.values()):
            break
        bpy.ops.uv.unwrap(method="CONFORMAL", margin=0.0, correct_aspect=True)
        accepted = 0
        for ob in obs:
            members, group = state[ob.name]
            bm = bmesh.from_edit_mesh(ob.data)
            bm.faces.ensure_lookup_table()
            bm.edges.ensure_lookup_table()
            uvl = bm.loops.layers.uv.verify()
            for a, b, idx, es, old in trial[ob.name]:
                st, flipped = _stretch(bm, uvl, idx)
                if st <= limit and not flipped:
                    members[b] = idx
                    del members[a]
                    grown[ob.name] += 1
                    accepted += 1
                    continue
                for ei in es:
                    bm.edges[ei].seam = True
                for i, uvs in old.items():
                    for lp, uv in zip(bm.faces[i].loops, uvs):
                        lp[uvl].uv = uv
            bmesh.update_edit_mesh(ob.data)
        if not accepted:
            break
    for ob in obs:
        bm = bmesh.from_edit_mesh(ob.data)
        for f in bm.faces:
            f.select = True
        bmesh.update_edit_mesh(ob.data)
    return grown


def _unwrap_atlas(obs, cfg, job, atlas):
    """Smart project, merge poor islands, project merged charts along their mean normal, scale every island to
    its part's density, pack. All objects in `obs` share the atlas."""
    size = job["textures"][str(atlas)]
    margin = job["margins"][str(atlas)] / size
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
    stats, state = {}, {}
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
        for k in changed:  # merged: project along the chart's mean normal
            m = nsum[k] / np.linalg.norm(nsum[k])
            ref = np.array([0.0, 0.0, 1.0]) if abs(m[2]) < 0.9 else np.array([1.0, 0.0, 0.0])
            u = np.cross(m, ref)
            u /= np.linalg.norm(u)
            v = np.cross(m, u)
            for i in members[k]:
                for lp in bm.faces[i].loops:
                    co = np.array(lp.vert.co)
                    lp[uvl].uv = (float(co @ u), float(co @ v))
        bmesh.update_edit_mesh(ob.data)
        state[ob.name] = (members, group)
    grown = _grow(obs, state, job.get("stretch", 1.08), job.get("share", 0.3)) if job.get("grow", True) else {}
    for ob in obs:
        d = cfg[ob.name]["density"]
        focus = cfg[ob.name].get("focus") or []
        members, group = state[ob.name]
        bm = bmesh.from_edit_mesh(ob.data)
        bm.faces.ensure_lookup_table()
        uvl = bm.loops.layers.uv.verify()
        for k, idx in members.items():
            faces = [bm.faces[i] for i in idx]
            g = group[idx[0]]
            dk = d * (focus[g][4] if g >= 0 else 1.0)
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
        stats[ob.name] = {"islands": len(members), "grown": grown.get(ob.name, 0)}
        bmesh.update_edit_mesh(ob.data)
    tc = time.time()
    bpy.ops.uv.select_all(action="SELECT")
    bpy.ops.uv.pack_islands(rotate=True, scale=True, margin_method="FRACTION", margin=margin,
                            shape_method="CONCAVE")
    bpy.ops.object.mode_set(mode="OBJECT")
    TIMES.append({"project_s": round(tb - ta, 1), "charts_s": round(tc - tb, 1), "pack_s": round(time.time() - tc, 1)})
    return stats


TIMES = []
PRE, PRE_MIN = 80, 1500  # parts are first collapsed on their own to 80x their average share (at least 1500):
# the joint collapse then keeps the shares the full-resolution one gives within ~3% (cabin5), in ~1/6 the time


def _sub(verts, faces, sel):
    """The vertices and re-indexed faces of a subset of faces."""
    fc = faces[sel]
    used = np.unique(fc)
    remap = np.full(len(verts), -1, np.int64)
    remap[used] = np.arange(len(used))
    return verts[used].astype(np.float64), remap[fc]


def _reduce(name, poly, V, F, target, symmetry):
    """Collapse-decimate a part (`poly`: its flattened polygons, (V, F): its triangles, for the fold check) to
    `target` faces. Mirrored across X when asked, unless that turns triangles over: Blender's mirrored collapses skip
    its fold check, and on flat faces they fold (black triangles)."""
    ob = _flat_mesh(name, *poly[:3])
    n = len(ob.data.polygons)
    if target >= n:
        return ob, False
    if symmetry:
        flat = ob.data.copy()
        _decimate(ob, target / n, True)
        tree = BVHTree.FromPolygons(V.tolist(), F.tolist(), all_triangles=True)
        if _folded(ob, tree, _face_normals(V, F)[0]) == 0:
            bpy.data.meshes.remove(flat)
            return ob, True
        old, ob.data = ob.data, flat
        bpy.data.meshes.remove(old)
    _decimate(ob, target / n, False)
    return ob, False


def budgets(counts, faces, weights, total, floor, copies=None):
    """Triangles per part: the joint decimation's counts (what each part needs for one geometric error everywhere)
    scaled by each part's weight and renormalised so the triangles drawn (a part's count x its copies: a shared
    prefab's instances) come to `total`, but at least its `floor` (or all it has) and never more than it has."""
    copies = copies or {}
    share = {pn: weights[pn] * max(counts.get(pn, 0), 1) for pn in faces}
    fixed = {}
    for _ in range(len(share) + 1):
        free = [pn for pn in share if pn not in fixed]
        if not free:
            break
        left = max(total - sum(fixed[pn] * copies.get(pn, 1) for pn in fixed), 0)
        tot = sum(share[pn] * copies.get(pn, 1) for pn in free)
        want = {pn: left * share[pn] / tot for pn in free}
        lo = {pn: min(floor[pn], faces[pn]) for pn in free}
        clamp = {pn: lo[pn] if w < lo[pn] else faces[pn] for pn, w in want.items() if w < lo[pn] or w > faces[pn]}
        fixed.update(clamp or want)
        if not clamp:
            break
    return {pn: int(round(fixed[pn])) for pn in faces}


def lowpoly(job):
    _clear()
    t0 = time.time()
    dec = job.get("decimated")  # {"path", "key"}: the decimated parts of an earlier call with the same inputs
    if dec and os.path.exists(dec["path"]):
        c = np.load(dec["path"])
        if str(c["key"]) == dec["key"]:
            info = json.loads(str(c["info"]))
            obs = []
            for i, pn in enumerate(str(n) for n in c["names"]):
                ob = _poly_mesh(pn, c[f"{i}_V"], c[f"{i}_L"], c[f"{i}_S"])
                ob.data.shade_smooth()
                obs.append(ob)
            return _unwrap_and_save(job, obs, info, t0, float(c["t1"]), float(c["t1b"]), cached=True)
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
    copies = {pn: int(cfg[pn].get("copies", 1)) for pn in names}
    ratio = min(1.0, total / sum(nfaces[pn] * copies[pn] for pn in names))  # drawn triangles: prefabs per copy
    flat_frac = {pn: 0.0 for pn in names}
    _, polys = _part_arrays(job)
    pre_file = None
    if ratio >= 1.0:  # nothing to decimate: the parts as they are
        keep = np.isin(fpart, [pidx[pn] for pn in names])
        pid_of = np.full(len(all_names), -1)
        for k, pn in enumerate(names):
            pid_of[pidx[pn]] = k
        joint = _mesh("joint", *_sub(verts, faces, keep))
        joint.data.attributes.new("pid", "INT", "FACE").data.foreach_set("value", pid_of[fpart[keep]].astype(np.int32))
    else:
        # flat regions are ngons already (`planar.flatten`: they cost nothing). Every part is first collapsed on
        # its own to PRE times its average share (parallel workers), so the joint collapse, which decides the
        # shares, runs on a few hundred thousand triangles instead of millions
        tf = time.time()
        nf, source = {}, {}
        for pn in names:
            v, lp, sz, gone = polys(pn)
            nf[pn] = int((np.asarray(sz) - 2).sum())
            flat_frac[pn] = float(np.mean(gone)) if len(gone) else 0.0
            source[pn] = (v, lp, sz)
        r = total / sum(nf[pn] * copies[pn] for pn in names)
        pre = {pn: [max(int(job.get("pre_min", PRE_MIN)), int(job.get("pre", PRE) * r * nf[pn])), sym] for pn in names}
        pre = {pn: t for pn, t in pre.items() if t[0] < 0.8 * nf[pn]}
        for pn, (v, lp, sz, _) in _reduce_parts(job, pre).items():
            source[pn] = (v, lp, sz)
        print(f"@@t pre-decimated {len(pre)} parts {time.time() - tf:.1f}s", flush=True)
        tf = time.time()
        Vs, Ls, Ss, Ps, off = [], [], [], [], 0
        for k, pn in enumerate(names):
            v, lp, sz = source[pn]
            Vs.append(v)
            Ls.append(np.asarray(lp, np.int64) + off)
            Ss.append(sz)
            Ps.append(np.full(len(sz), k))
            off += len(v)
        joint = _flat_mesh("joint", np.concatenate(Vs), np.concatenate(Ls), np.concatenate(Ss), np.concatenate(Ps))
        n = len(joint.data.polygons)
        fp = np.empty(n, np.int32)
        joint.data.attributes["pid"].data.foreach_get("value", fp)
        nfaces = {pn: int((fp == k).sum()) for k, pn in enumerate(names)}
        ratio = min(1.0, total / sum(nfaces[pn] * copies[pn] for pn in names))
        if ratio < 1.0:
            _decimate(joint, ratio, sym)
        print(f"@@t joint {n} faces {time.time() - tf:.1f}s", flush=True)
        pre_file = os.path.join(os.path.dirname(os.path.abspath(job["out"])), "lowpoly_pre.npz")
        np.savez(pre_file, **{f"{pn}|{k}": a for pn in pre for k, a in zip("VLS", source[pn])})
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
    #    The floor keeps round things round, so it shrinks with the part's flat share: a box needs no floor.
    floor = {pn: int(round(int(job.get("min_part", 300)) * (1 - flat_frac[pn]))) for pn in names}
    want = budgets(counts, nfaces, {pn: cfg[pn]["weight"] for pn in names}, total, floor, copies)
    obs, info, redo_parts = {}, {}, {}
    for k, pn in enumerate(names):
        redo, s = abs(want[pn] - counts[pn]) > 0.1 * max(counts[pn], 1), sym and ratio < 1.0
        if cfg[pn].get("split"):  # a slab of a split part: alone, its cut edges would open a crack
            redo = False
        if not redo:
            ob = _mesh(pn, *_sub(Vj, Fj, jpart == k))
            Vh, Fh = _sub(verts, faces, fpart == pidx[pn])
            if s and _folded(ob, BVHTree.FromPolygons(Vh.tolist(), Fh.tolist(), all_triangles=True),
                             _face_normals(Vh, Fh)[0]) > 0:
                bpy.data.objects.remove(ob)
                redo, s = True, False
            else:
                obs[pn] = ob
        if redo:
            redo_parts[pn] = [int(want[pn]), bool(s)]
        info[pn] = {"joint_count": counts[pn], "budget": want[pn], "flat": round(flat_frac[pn], 3), "symmetric": s}
    # 3. the parts decimated again on their own: independent, so in parallel Blender processes
    for pn, (v, lp, sz, s) in _reduce_parts(job, redo_parts, pre_file).items():
        obs[pn] = _flat_mesh(pn, v, lp, sz)
        info[pn]["symmetric"] = s
    if pre_file:
        os.remove(pre_file)
    obs = [obs[pn] for pn in names]
    for ob in obs:
        ob.data.shade_smooth()
    t1b = time.time()
    if dec:  # the unwrap may be redone with other atlases (a regroup): keep the decimation
        arrays = {}
        for i, ob in enumerate(obs):
            arrays[f"{i}_V"], arrays[f"{i}_L"], arrays[f"{i}_S"] = _poly_arrays(ob)
        np.savez(dec["path"], key=np.array(dec["key"]), names=np.array([ob.name for ob in obs]),
                 info=np.array(json.dumps(info)), t1=np.array(t1 - t0), t1b=np.array(t1b - t0), **arrays)
    return _unwrap_and_save(job, obs, info, t0, t1 - t0, t1b - t0)


def _part_arrays(job):
    """The high mesh's triangles and the flattened polygons, per part: (triangles of, polygons of)."""
    z = np.load(job["mesh"])
    verts, faces, part = z["verts"], z["faces"], z["part"]
    all_names = [str(n) for n in z["part_names"]]
    fpart = part[faces[:, 0]]
    fl = np.load(job["flat"]) if job.get("flat") else None
    flat_of = {str(n): i for i, n in enumerate(fl["names"])} if fl is not None else {}

    def tris(pn):
        return _sub(verts, faces, fpart == all_names.index(pn))

    def polys(pn):
        """The part's flattened polygons (vertices, loop vertices, loop sizes, which triangles were dissolved)."""
        if pn in flat_of:
            i = flat_of[pn]
            return fl[f"{i}_V"], fl[f"{i}_L"], fl[f"{i}_S"], fl[f"{i}_gone"]
        Vh, Fh = tris(pn)
        return Vh, Fh.ravel(), np.full(len(Fh), 3), np.zeros(len(Fh), bool)
    return tris, polys


def reduce(job):
    """Worker: decimate some parts on their own ({part: [target, symmetric]}), from `source` (an npz of earlier
    results, "<part>|V/L/S") where it has them, else from their flattened polygons; save their polygons."""
    _clear()
    tris, polys = _part_arrays(job)
    src = np.load(job["source"]) if job.get("source") else None
    arrays, sym = {}, {}
    for i, (pn, (target, s)) in enumerate(job["parts"].items()):
        tr = time.time()
        Vh, Fh = tris(pn)
        poly = (src[f"{pn}|V"], src[f"{pn}|L"], src[f"{pn}|S"]) if src is not None and f"{pn}|V" in src.files \
            else polys(pn)
        ob, sym[pn] = _reduce(pn, poly, Vh, Fh, target, s)
        _clean(ob)
        V, L, st = _poly_arrays(ob)
        arrays[f"{i}_V"], arrays[f"{i}_L"], arrays[f"{i}_S"] = V, L, np.diff(np.r_[st, len(L)])
        bpy.data.objects.remove(ob)
        print(f"@@t reduce {pn} {int((np.asarray(poly[2]) - 2).sum())} -> {target}: {time.time() - tr:.1f}s", flush=True)
    np.savez(job["out"], names=np.array(list(job["parts"])), sym=np.array(json.dumps(sym)), **arrays)


def _reduce_parts(job, parts, source=None):
    """{part: (vertices, loop vertices, loop sizes, symmetric)} for parts decimated on their own (from `source`, see
    `reduce`), spread over worker Blender processes (biggest parts first, each to the least loaded worker)."""
    import subprocess
    import tempfile
    if not parts:
        return {}
    z = np.load(job["mesh"])
    all_names = [str(n) for n in z["part_names"]]
    size = dict(zip(all_names, np.bincount(z["part"][z["faces"][:, 0]], minlength=len(all_names)).tolist()))
    n = max(1, min(len(parts), int(job.get("workers", min(8, max(1, (os.cpu_count() or 4) // 2))))))
    load, groups = [0] * n, [dict() for _ in range(n)]
    for pn in sorted(parts, key=lambda pn: -size.get(pn, 0)):
        i = int(np.argmin(load))
        groups[i][pn] = parts[pn]
        load[i] += size.get(pn, 0)
    out = {}
    with tempfile.TemporaryDirectory(prefix="hifipushie-reduce-") as tmp:
        procs = []
        for i, g in enumerate(groups):
            if not g:
                continue
            w = {"mode": "reduce", "mesh": job["mesh"], "flat": job.get("flat"), "parts": g, "source": source,
                 "out": os.path.join(tmp, f"r{i}.npz")}
            jp = os.path.join(tmp, f"r{i}.json")
            json.dump(w, open(jp, "w"))
            procs.append((subprocess.Popen([bpy.app.binary_path, "-b", "--factory-startup", "--python-exit-code", "1",
                                            "--python", os.path.abspath(__file__), "--", jp],
                                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True), w))
        for p, w in procs:
            log, _ = p.communicate()
            for line in log.splitlines():
                if line.startswith("@@t"):
                    print(line, flush=True)
            if p.returncode:
                raise RuntimeError(f"decimation worker failed:\n{log[-3000:]}")
            r = np.load(w["out"])
            sym = json.loads(str(r["sym"]))
            for i, pn in enumerate(str(x) for x in r["names"]):
                out[pn] = (r[f"{i}_V"], r[f"{i}_L"], r[f"{i}_S"], sym[pn])
    return out


def _object_arrays(ob) -> dict:
    """What the export bakes against and the GLB carries: vertices and per-corner vertex / uv / normal /
    MikkTSpace tangent + bitangent sign."""
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
    return {"verts": co.reshape(-1, 3), "corner_vert": vi, "uv": uv.reshape(-1, 2), "normal": nrm.reshape(-1, 3),
            "tangent": tan.reshape(-1, 3), "sign": sgn}


def unwrap(job):
    """Worker: unwrap and pack some atlases (`only`: atlas indices) from the decimation cache, save each part's
    arrays (`_object_arrays`), its stats and the timings."""
    _clear()
    c = np.load(job["decimated"]["path"])
    cfg = job["parts"]
    only = set(job["only"])
    atlases = {}
    for i, pn in enumerate(str(n) for n in c["names"]):
        if cfg[pn]["atlas"] in only:
            ob = _poly_mesh(pn, c[f"{i}_V"], c[f"{i}_L"], c[f"{i}_S"])
            ob.data.shade_smooth()
            ob.data.uv_layers.new(name="UVMap")
            atlases.setdefault(cfg[pn]["atlas"], []).append(ob)
    out, stats = {}, {}
    for ai, group in atlases.items():
        stats.update(_unwrap_atlas(group, cfg, job, ai))
        for ob in group:
            out.update({f"{ob.name}|{k}": v for k, v in _object_arrays(ob).items()})
    np.savez(job["out"], stats=np.array(json.dumps(stats)), times=np.array(json.dumps(TIMES)), **out)


def _unwrap_parallel(job, atlases):
    """{part: arrays}, stats and timings of the atlases unwrapped by worker Blender processes (heaviest atlases
    first, each to the least loaded worker): the pack is ~50 s an atlas, and a density export has dozens."""
    import subprocess
    import tempfile
    n = max(1, min(len(atlases), int(job.get("workers", min(8, max(1, (os.cpu_count() or 4) // 2))))))
    load, groups = [0] * n, [[] for _ in range(n)]
    for ai in sorted(atlases, key=lambda a: -sum(len(ob.data.polygons) for ob in atlases[a])):
        i = int(np.argmin(load))
        groups[i].append(ai)
        load[i] += sum(len(ob.data.polygons) for ob in atlases[ai])
    arrays, stats, times = {}, {}, []
    with tempfile.TemporaryDirectory(prefix="hifipushie-unwrap-") as tmp:
        procs = []
        for i, g in enumerate(groups):
            if not g:
                continue
            w = {**job, "mode": "unwrap", "only": g, "out": os.path.join(tmp, f"u{i}.npz")}
            jp = os.path.join(tmp, f"u{i}.json")
            json.dump(w, open(jp, "w"))
            procs.append((subprocess.Popen([bpy.app.binary_path, "-b", "--factory-startup", "--python-exit-code", "1",
                                            "--python", os.path.abspath(__file__), "--", jp],
                                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True), w))
        for p, w in procs:
            log, _ = p.communicate()
            if p.returncode:
                raise RuntimeError(f"unwrap worker failed:\n{log[-3000:]}")
            r = np.load(w["out"])
            stats.update(json.loads(str(r["stats"])))
            times += json.loads(str(r["times"]))
            for key in r.files:
                if "|" in key:
                    pn, k = key.rsplit("|", 1)
                    arrays.setdefault(pn, {})[k] = r[key]
    return arrays, stats, times


def _unwrap_and_save(job, obs, info, t0, joint_s, decimate_s, cached=False):
    cfg = job["parts"]
    t1b = time.time()
    atlases = {}
    for ob in obs:
        atlases.setdefault(cfg[ob.name]["atlas"], []).append(ob)
    dec = job.get("decimated")
    if len(atlases) > 1 and dec and os.path.exists(dec["path"]):  # independent atlases: in parallel
        arrays, stats, times = _unwrap_parallel(job, atlases)
        TIMES.extend(times)
    else:
        arrays, stats = {}, {}
        for ob in obs:
            ob.data.uv_layers.new(name="UVMap")
        for ai, group in atlases.items():
            stats.update(_unwrap_atlas(group, cfg, job, ai))
        for ob in obs:
            arrays[ob.name] = _object_arrays(ob)
    for pn, st in stats.items():
        info[pn].update(st)
    t2 = time.time()

    out = {"part_names": np.array([ob.name for ob in obs]), "atlas": np.array([cfg[ob.name]["atlas"] for ob in obs]),
           "info": np.array(json.dumps({"parts": info, "joint_s": joint_s, "decimate_s": decimate_s,
                                        "unwrap_s": t2 - t1b, "unwrap": TIMES, "decimation_cached": cached}))}
    for i, ob in enumerate(obs):
        out.update({f"{i}_{k}": v for k, v in arrays[ob.name].items()})
    np.savez(job["out"], **out)


def preview(job):
    _clear()
    bpy.ops.import_scene.gltf(filepath=job["glb"])
    for ob in list(bpy.data.objects):  # parts (or instances, prefabs) left out, e.g. the roof to see an interior
        # a part split for the atlases ("roof~2") goes with its part's name
        base = ob.name.split("~")[0]
        if any(n == h or n.endswith("_" + h) or ob.get("prefab") == h for h in job.get("hide", []) for n in (ob.name, base)):
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
{"lowpoly": lowpoly, "reduce": reduce, "unwrap": unwrap, "preview": preview}[job["mode"]](job)
