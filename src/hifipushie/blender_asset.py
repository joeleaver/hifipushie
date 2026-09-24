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
      merged chart still faces one way), scales every island to its density and packs them `margin` texels
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

def _components(n, a, b):
    """Connected component label per node (min node index) of the graph with edges (a, b): hooking plus pointer
    jumping, a few passes over the edges instead of a Python BFS."""
    lab = np.arange(n)
    while True:
        la, lb = lab[a], lab[b]
        hi, lo = np.maximum(la, lb), np.minimum(la, lb)
        diff = hi != lo
        if not diff.any():
            return lab
        np.minimum.at(lab, hi[diff], lo[diff])
        while True:
            nxt = lab[lab]
            if (nxt == lab).all():
                break
            lab = nxt


def _neighbours(indptr, nbr, f):
    """(source, neighbour) pairs of the faces `f` in a CSR adjacency."""
    cnt = indptr[f + 1] - indptr[f]
    src = np.repeat(f, cnt)
    off = np.arange(cnt.sum()) - np.repeat(np.cumsum(cnt) - cnt, cnt)
    return src, nbr[np.repeat(indptr[f], cnt) + off]


def planar_regions(V, F, plane_tol, angle_deg=0.5, min_faces=8, rounds=40):
    """Region label per face (-1: none) for groups of connected faces that lie on one plane: every face's normal
    within `angle_deg` of its region's SEED face and its centre within `plane_tol` of the seed's plane. Testing
    against the seed rather than neighbour to neighbour keeps gently curved organic surfaces from chaining into
    one region. Regions are disks (V - E + F = 1: ones with holes, like a wall round a window, are split), so each
    dissolves to one simple ngon."""
    nf = len(F)
    e1, e2 = V[F[:, 1]] - V[F[:, 0]], V[F[:, 2]] - V[F[:, 0]]
    nrm = np.cross(e1, e2)
    area = np.linalg.norm(nrm, axis=1)
    tiny = area < 1e-12
    nrm = nrm / np.maximum(area, 1e-30)[:, None]
    cen = V[F].mean(1)
    cos_t = np.cos(np.radians(angle_deg))

    # manifold edges (exactly two faces) as face pairs
    he = F[:, [0, 1, 1, 2, 2, 0]].reshape(-1, 2)
    key = np.minimum(he[:, 0], he[:, 1]).astype(np.int64) * len(V) + np.maximum(he[:, 0], he[:, 1])
    order = np.argsort(key, kind="stable")
    ks = key[order]
    first = np.r_[True, ks[1:] != ks[:-1]]
    run = np.diff(np.r_[np.flatnonzero(first), len(ks)])
    start = np.flatnonzero(first)[run == 2]
    fa, fb = order[start] // 3, order[start + 1] // 3

    def fits(f, n0, c0):
        """Faces `f` against reference normals/centres: parallel (degenerate faces skip that) and in plane."""
        par = (nrm[f] * n0).sum(1) > cos_t
        return (par | tiny[f]) & (np.abs(((cen[f] - c0) * n0).sum(1)) < plane_tol)

    ok = fits(fa, nrm[fb], cen[fb]) & fits(fb, nrm[fa], cen[fa])
    ok &= ~(tiny[fa] & tiny[fb])
    a, b = np.r_[fa[ok], fb[ok]], np.r_[fb[ok], fa[ok]]
    o = np.argsort(a, kind="stable")
    a, b = a[o], b[o]
    indptr = np.searchsorted(a, np.arange(nf + 1))

    label = np.full(nf, -1)
    pool = np.zeros(nf, bool)
    pool[a] = True
    nreg = 0
    for _ in range(rounds):
        sel = pool[a] & pool[b]
        comp = _components(nf, a[sel], b[sel])
        size = np.bincount(comp[pool], minlength=nf)
        big = pool & (size[comp] >= min_faces) & ~tiny
        if not big.any():
            break
        # seed per component: the face nearest its area-weighted mean normal (the dominant plane)
        fi = np.flatnonzero(big)
        mn = np.zeros((nf, 3))
        np.add.at(mn, comp[fi], nrm[fi] * area[fi, None])
        score = (nrm[fi] * mn[comp[fi]]).sum(1)
        o = np.lexsort((-score, comp[fi]))
        seeds = fi[o][np.r_[True, comp[fi][o][1:] != comp[fi][o][:-1]]]
        rid = nreg + np.arange(len(seeds))
        sn, sc = nrm[seeds], cen[seeds]
        label[seeds] = rid
        pool[seeds] = False
        front = seeds
        while len(front):
            src, nb = _neighbours(indptr, b, front)
            m = pool[nb] & (comp[nb] == comp[src])
            src, nb = src[m], nb[m]
            r = label[src] - nreg
            m = fits(nb, sn[r], sc[r])
            nb, r = nb[m], r[m]
            nb, i = np.unique(nb, return_index=True)
            label[nb] = r[i] + nreg
            pool[nb] = False
            front = nb
        nreg += len(seeds)

    # disks only: split regions whose Euler characteristic isn't 1 across their longest extent, re-split pieces
    for _ in range(8):
        label = _relabel(label, fa, fb)
        chi = _euler(F, label, fa, fb)
        bad = np.flatnonzero(chi != 1)
        if not len(bad):
            break
        fi = np.flatnonzero(np.isin(label, bad))
        lr = label[fi]
        cnt = np.bincount(lr)[lr][:, None]
        mid = np.zeros((label.max() + 1, 3))
        np.add.at(mid, lr, cen[fi])
        d = cen[fi] - mid[lr] / cnt
        cov = np.zeros((label.max() + 1, 3, 3))
        np.add.at(cov, lr, d[:, :, None] * d[:, None, :])
        axis = np.linalg.eigh(cov)[1][:, :, -1]
        side = (d * axis[lr]).sum(1) > 0
        label[fi[side]] += label.max() + 1
    else:
        label = _relabel(label, fa, fb)
        label[np.isin(label, np.flatnonzero(_euler(F, label, fa, fb) != 1))] = -1
    size = np.bincount(label[label >= 0], minlength=max(label.max() + 1, 1))
    label[(label >= 0) & (size[np.maximum(label, 0)] < min_faces)] = -1
    return _relabel(label, fa, fb)


def _relabel(label, fa, fb):
    """Split every region into its connected pieces and number them 0..n-1 (-1 stays)."""
    m = (label[fa] == label[fb]) & (label[fa] >= 0)
    comp = _components(len(label), fa[m], fb[m])
    comp[label < 0] = -1
    u, inv = np.unique(comp, return_inverse=True)
    return inv - (1 if u[0] == -1 else 0)


def _euler(F, label, fa, fb):
    """V - E + F of every region (1 for a disk). Edges: three per face less the ones two of its faces share."""
    n = label.max() + 1
    if n <= 0:
        return np.zeros(0, int)
    fi = np.flatnonzero(label >= 0)
    lr = label[fi]
    nfc = np.bincount(lr, minlength=n)
    inner = np.bincount(label[fa][(label[fa] == label[fb]) & (label[fa] >= 0)], minlength=n)
    k = np.sort((np.repeat(lr, 3).astype(np.int64) * (F.max() + 1) + F[fi].ravel()))
    nv = np.bincount(k[np.r_[True, k[1:] != k[:-1]]] // (F.max() + 1), minlength=n)
    return nv - (3 * nfc - inner) + nfc


def _loops(F, label):
    """Each region's boundary as one vertex loop, wound like its faces: (region per loop, loop start, loop length,
    vertices), for the regions whose boundary is one simple loop (every boundary vertex left once) enclosing at
    least one interior vertex (a strip of faces with none gains nothing from being dissolved)."""
    n = label.max() + 1
    fi = np.flatnonzero(label >= 0)
    hs = F[fi][:, [0, 1, 2]].ravel()
    ht = F[fi][:, [1, 2, 0]].ravel()
    hr = np.repeat(label[fi], 3).astype(np.int64)
    nv = F.max() + 1
    fwd = (hr * nv + hs) * nv + ht
    twin = (hr * nv + ht) * nv + hs
    fs = np.sort(fwd)
    pos = np.minimum(np.searchsorted(fs, twin), len(fs) - 1)
    bd = fs[pos] != twin  # boundary: the reverse half-edge isn't in the region
    bs, bt, br = hs[bd], ht[bd], hr[bd]
    # the region's vertices, and whether each boundary vertex is left exactly once
    kv = np.sort(hr * nv + hs)
    nvert = np.bincount(kv[np.r_[True, kv[1:] != kv[:-1]]] // nv, minlength=n)
    start = br * nv + bs
    o = np.argsort(start, kind="stable")
    bs, bt, br, start = bs[o], bt[o], br[o], start[o]
    dup = np.r_[start[1:] == start[:-1], False] | np.r_[False, start[1:] == start[:-1]]
    ok = np.ones(n, bool)
    ok[br[dup]] = False
    nb = np.bincount(br, minlength=n)
    ok &= nvert > nb  # an interior vertex
    # successor of each boundary half-edge: the one leaving its end vertex in the same region
    succ = np.searchsorted(start, br * nv + bt)
    succ = np.minimum(succ, len(start) - 1)
    bad = start[succ] != br * nv + bt
    ok[br[bad]] = False
    succ[bad] = np.flatnonzero(bad)
    # list ranking by pointer doubling: steps from each half-edge to the one before its region's head
    m = len(start)
    head = np.full(n, m)
    np.minimum.at(head, br, np.arange(m))
    nxt = succ.copy()
    end = nxt == head[br]
    nxt[end] = np.flatnonzero(end)
    dist = (~end).astype(np.int64)
    for _ in range(int(np.ceil(np.log2(max(nb.max(), 2)))) + 1):
        dist += dist[nxt]
        nxt = nxt[nxt]
    ok[br[(nxt[nxt] != nxt) | (dist[head[br]] + 1 != nb[br])]] = False  # more than one loop
    keep = ok[br]
    o = np.lexsort((-dist[keep], br[keep]))
    verts = bs[keep][o]
    regs = np.flatnonzero(ok & (nb > 0))
    length = nb[regs]
    return regs, np.r_[0, np.cumsum(length)[:-1]], length, verts


def _flatten(ob, plane_tol):
    """Dissolve the object's planar regions (`planar_regions`) to ngons and triangulate them again. The mesh is
    rebuilt in numpy (bmesh's dissolve is quadratic in region size: 25 s on a 380k-face stone part). A face
    attribute "pid" (the part id) survives: a region never spans two parts, they share no vertices. Returns the
    face count and which of the input faces were dissolved."""
    V, F = _tri_arrays(ob)
    none = np.zeros(len(F), bool)
    if plane_tol <= 0:
        return len(F), none
    label = planar_regions(V, F, plane_tol)
    if label.max() < 0:
        return len(F), none
    regs, lstart, length, lverts = _loops(F, label)
    if not len(regs):
        return len(F), none
    me = ob.data
    pid = None
    if "pid" in me.attributes:
        pid = np.empty(len(F), np.int32)
        me.attributes["pid"].data.foreach_get("value", pid)
    gone = np.isin(label, regs)
    kept = np.flatnonzero(~gone)
    rep = np.full(label.max() + 1, -1)
    rep[label[gone]] = np.flatnonzero(gone)  # a face of each region, for its attributes
    loops = np.r_[F[kept].ravel(), lverts]
    sizes = np.r_[np.full(len(kept), 3), length]
    used = np.unique(loops)
    remap = np.full(len(V), -1, np.int64)
    remap[used] = np.arange(len(used))
    new = bpy.data.meshes.new(me.name)
    new.vertices.add(len(used))
    new.vertices.foreach_set("co", V[used].astype(np.float32).ravel())
    new.loops.add(len(loops))
    new.loops.foreach_set("vertex_index", remap[loops].astype(np.int32))
    new.polygons.add(len(sizes))
    new.polygons.foreach_set("loop_start", np.r_[0, np.cumsum(sizes)[:-1]].astype(np.int32))
    new.update(calc_edges=True)
    if pid is not None:
        new.attributes.new("pid", "INT", "FACE").data.foreach_set("value", np.r_[pid[kept], pid[rep[regs]]])
    ob.data = new
    bpy.data.meshes.remove(me)
    tri = ob.modifiers.new("tri", "TRIANGULATE")
    tri.quad_method, tri.ngon_method = "BEAUTY", "BEAUTY"
    bpy.context.view_layer.objects.active = ob
    bpy.ops.object.modifier_apply(modifier="tri")
    return len(new.polygons), gone


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


def _reduce(name, V, F, target, symmetry, plane_tol):
    """Collapse-decimate (V, F) to `target` faces, after dissolving its flat regions (`_flatten`). Mirrored across X
    when asked, unless that turns triangles over: Blender's mirrored collapses skip its fold check, and on flat faces
    they fold (black triangles)."""
    ob = _mesh(name, V, F)
    n = _flatten(ob, plane_tol)[0]
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
    keep = np.isin(fpart, [pidx[pn] for pn in names])
    V, F = _sub(verts, faces, keep)
    pid_of = np.full(len(all_names), -1)
    for k, pn in enumerate(names):
        pid_of[pidx[pn]] = k
    joint = _mesh("joint", V, F)
    joint.data.attributes.new("pid", "INT", "FACE").data.foreach_set("value", pid_of[fpart[keep]].astype(np.int32))
    copies = {pn: int(cfg[pn].get("copies", 1)) for pn in names}
    ratio = min(1.0, total / sum(nfaces[pn] * copies[pn] for pn in names))  # drawn triangles: prefabs per copy
    flat_frac = {pn: 0.0 for pn in names}
    plane_tol = 0.25 * float(job.get("voxel", 0.0))
    if ratio < 1.0:
        # flat regions go to ngons first (they cost nothing), then the collapse ratio counts what's left
        n, flat = _flatten(joint, plane_tol)
        pids = pid_of[fpart[keep]]
        flat_frac = {pn: float(flat[pids == k].mean()) for k, pn in enumerate(names)}
        fp = np.empty(n, np.int32)
        joint.data.attributes["pid"].data.foreach_get("value", fp)
        nfaces = {pn: int((fp == k).sum()) for k, pn in enumerate(names)}
        ratio = min(1.0, total / sum(nfaces[pn] * copies[pn] for pn in names))
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
    #    The floor keeps round things round, so it shrinks with the part's flat share: a box needs no floor.
    floor = {pn: int(round(int(job.get("min_part", 300)) * (1 - flat_frac[pn]))) for pn in names}
    want = budgets(counts, nfaces, {pn: cfg[pn]["weight"] for pn in names}, total, floor, copies)
    obs, info = [], {}
    for k, pn in enumerate(names):
        Vh, Fh = _sub(verts, faces, fpart == pidx[pn])
        redo, s = abs(want[pn] - counts[pn]) > 0.1 * max(counts[pn], 1), sym and ratio < 1.0
        if cfg[pn].get("split"):  # a slab of a split part: alone, its cut edges would open a crack
            redo = False
        if not redo:
            ob = _mesh(pn, *_sub(Vj, Fj, jpart == k))
            if s and _folded(ob, BVHTree.FromPolygons(Vh.tolist(), Fh.tolist(), all_triangles=True),
                             _face_normals(Vh, Fh)[0]) > 0:
                bpy.data.objects.remove(ob)
                redo, s = True, False
        if redo:
            ob, s = _reduce(pn, Vh, Fh, want[pn], s, plane_tol)
            _clean(ob)
        ob.data.shade_smooth()
        obs.append(ob)
        info[pn] = {"symmetric": s, "joint_count": counts[pn], "budget": want[pn], "flat": round(flat_frac[pn], 3)}
    t1b = time.time()
    if dec:  # the unwrap may be redone with other atlases (a regroup): keep the decimation
        arrays = {}
        for i, ob in enumerate(obs):
            arrays[f"{i}_V"], arrays[f"{i}_L"], arrays[f"{i}_S"] = _poly_arrays(ob)
        np.savez(dec["path"], key=np.array(dec["key"]), names=np.array([ob.name for ob in obs]),
                 info=np.array(json.dumps(info)), t1=np.array(t1 - t0), t1b=np.array(t1b - t0), **arrays)
    return _unwrap_and_save(job, obs, info, t0, t1 - t0, t1b - t0)


def _unwrap_and_save(job, obs, info, t0, joint_s, decimate_s, cached=False):
    cfg = job["parts"]
    t1b = time.time()
    atlases = {}
    for ob in obs:
        ob.data.uv_layers.new(name="UVMap")
        atlases.setdefault(cfg[ob.name]["atlas"], []).append(ob)
    for ai, group in atlases.items():
        for pn, s in _unwrap_atlas(group, cfg, job, ai).items():
            info[pn].update(s)
    t2 = time.time()

    out = {"part_names": np.array([ob.name for ob in obs]), "atlas": np.array([cfg[ob.name]["atlas"] for ob in obs]),
           "info": np.array(json.dumps({"parts": info, "joint_s": joint_s, "decimate_s": decimate_s,
                                        "unwrap_s": t2 - t1b, "unwrap": TIMES, "decimation_cached": cached}))}
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
{"lowpoly": lowpoly, "preview": preview}[job["mode"]](job)
