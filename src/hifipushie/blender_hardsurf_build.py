"""Hard surface from the point cloud, inside Blender: parts (hardsurf_parts' JSON) -> one object per part with artist UV
seams, smooth-by-angle shading, and each part's distance from the sculpt (how far the idealised part sits from it).
    blender -b --factory-startup --python blender_hardsurf_build.py -- job.json
job: {"parts": parts.json, "out": parts.glb, "report": build.json, "sculpt": high.ply (optional: distances)}
Part types: lathe, tube, loft, rbox, plate, plate3d, torus, radial (see hardsurf_parts.TYPES). Corners of a lathe profile
sharper than 40 deg get support loops (a point 3 mm along each neighbouring segment), so it shades crisp with or without
subdivision. Each part may carry: bone, rough, metal, nmap, extr, reach, bake_offset, clean (kept as custom props)."""
import bpy, bmesh, sys, json, math, mathutils
from mathutils import Vector, Matrix
J = json.load(open(sys.argv[sys.argv.index("--") + 1]))
bpy.ops.wm.read_factory_settings(use_empty=True); sc = bpy.context.scene
P = json.load(open(J["parts"]))


def frame_of(axis):
    n = Vector(axis).normalized(); u = n.cross(Vector((0, 0, 1)) if abs(n.z) < 0.9 else Vector((1, 0, 0))).normalized(); v = n.cross(u)
    return n, u, v


def obj_from_bm(bm, name):
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free(); o = bpy.data.objects.new(name, me); sc.collection.objects.link(o); return o


def support(profile, eps=0.003, ang=40):
    """insert a point eps along each neighbouring segment at corners sharper than ang degrees (hard-surface support loops)"""
    p = [Vector((t, r)) for t, r in profile]; out = [p[0]]
    for i in range(1, len(p) - 1):
        d0, d1 = (p[i] - p[i - 1]), (p[i + 1] - p[i])
        if d0.length < 1e-6 or d1.length < 1e-6: continue
        turn = math.degrees(d0.angle(d1))
        if turn > ang:
            e0, e1 = min(eps, d0.length * 0.3), min(eps, d1.length * 0.3)
            out += [p[i] - d0.normalized() * e0, p[i], p[i] + d1.normalized() * e1]
        else:
            out.append(p[i])
    out.append(p[-1]); return [(q.x, q.y) for q in out]


def lathe(pt):
    prof = support(pt["profile"], pt.get("eps", 0.003)) if pt.get("support", True) else pt["profile"]
    n, u, v = frame_of(pt["axis"]); o = Vector(pt["origin"]); S = pt.get("seg", 32); ph = math.radians(pt.get("phase", 0))
    bm = bmesh.new(); rows = []
    for t, r in prof:
        if r < 1e-4: rows.append([bm.verts.new(o + n * t)])
        else: rows.append([bm.verts.new(o + n * t + r * (math.cos(ph + 2 * math.pi * k / S) * u + math.sin(ph + 2 * math.pi * k / S) * v)) for k in range(S)])
    seams = []
    for A, B in zip(rows[:-1], rows[1:]):
        if len(A) == 1 and len(B) == 1: continue
        if len(A) == 1:
            for k in range(S): bm.faces.new((A[0], B[(k + 1) % S], B[k]))
        elif len(B) == 1:
            for k in range(S): bm.faces.new((A[k], A[(k + 1) % S], B[0]))
        else:
            for k in range(S): bm.faces.new((A[k], A[(k + 1) % S], B[(k + 1) % S], B[k]))
        seams.append((A[0], B[0]))
    if len(rows[0]) > 1 and pt.get("cap", True): bm.faces.new(rows[0][::-1])
    if len(rows[-1]) > 1 and pt.get("cap", True): bm.faces.new(rows[-1])
    bm.edges.ensure_lookup_table(); bm.verts.ensure_lookup_table()
    for x, y in seams:
        e = bm.edges.get((x, y))
        if e: e.seam = True
    # seams round the caps' rims and at profile corners (where an artist would split the UV islands)
    for row in (rows[0], rows[-1]):
        if len(row) > 1:
            for k in range(S):
                e = bm.edges.get((row[k], row[(k + 1) % S]))
                if e: e.seam = True
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return bm


def ring_seam_bm(rings, closed_rings=True, caps=True):
    bm = bmesh.new(); R = [[bm.verts.new(Vector(p)) for p in ring] for ring in rings]; N = len(R[0])
    for A, B in zip(R[:-1], R[1:]):
        for k in range(N if closed_rings else N - 1): bm.faces.new((A[k], A[(k + 1) % N], B[(k + 1) % N], B[k]))
    bm.edges.ensure_lookup_table()
    for A, B in zip(R[:-1], R[1:]):
        e = bm.edges.get((A[0], B[0])); e and setattr(e, "seam", True)
    if caps:
        for row in (R[0], R[-1]):
            f = bm.faces.new(row)
            for k in range(N):
                e = bm.edges.get((row[k], row[(k + 1) % N])); e and setattr(e, "seam", True)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces); return bm


def tube_rings(path, r, seg, closed):
    pts = [Vector(p) for p in path]; n = len(pts); rings = []
    tang = [((pts[(i + 1) % n] if (closed or i < n - 1) else pts[i]) - (pts[i - 1] if (closed or i > 0) else pts[i])).normalized() for i in range(n)]
    t0 = tang[0]; nrm = t0.cross(Vector((0, 0, 1)) if abs(t0.z) < 0.9 else Vector((1, 0, 0))).normalized()
    for i in range(n):
        if i:  # parallel transport
            ax = tang[i - 1].cross(tang[i])
            if ax.length > 1e-8: nrm = Matrix.Rotation(tang[i - 1].angle(tang[i]), 3, ax.normalized()) @ nrm
        b = tang[i].cross(nrm)
        rings.append([pts[i] + r * (math.cos(2 * math.pi * k / seg) * nrm + math.sin(2 * math.pi * k / seg) * b) for k in range(seg)])
    return rings


def smooth_path(path, closed, step=0.02):
    """Catmull-Rom through the points, resampled about every `step` m"""
    P_ = [Vector(p) for p in path]; n = len(P_); out = []
    segs = n if closed else n - 1
    for i in range(segs):
        p0 = P_[(i - 1) % n] if (closed or i > 0) else P_[0]; p1 = P_[i]; p2 = P_[(i + 1) % n]; p3 = P_[(i + 2) % n] if (closed or i + 2 < n) else P_[-1]
        m = max(2, int((p2 - p1).length / step))
        for k in range(m):
            t = k / m
            out.append(0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t * t + (-p0 + 3 * p1 - 3 * p2 + p3) * t ** 3))
    if not closed: out.append(P_[-1])
    return [tuple(q) for q in out]


def tube(pt):
    bms = []
    for path in pt["paths"]:
        closed = pt.get("closed", False)
        pth = smooth_path(path, closed, pt.get("step", 0.02)) if pt.get("smooth", True) else path
        rings = tube_rings(pth, pt["r"], pt.get("seg", 12), closed)
        if closed: rings.append(rings[0])
        bm = ring_seam_bm(rings, caps=not closed)
        bms.append(bm)
    return bms


def rbox(pt):
    bm = bmesh.new(); bmesh.ops.create_cube(bm, size=1.0)
    sx, sy, sz = pt["size"]
    for v in bm.verts: v.co = Vector((v.co.x * sx, v.co.y * sy, v.co.z * sz))
    bv = pt.get("bevel", 0.01)
    if bv > 0: bmesh.ops.bevel(bm, geom=list(bm.edges), offset=bv, segments=pt.get("bseg", 3), profile=0.5, affect="EDGES", clamp_overlap=True)
    rot = pt.get("rot", [0, 0, 0]); M = mathutils.Euler([math.radians(x) for x in rot]).to_matrix()
    for v in bm.verts: v.co = M @ v.co + Vector(pt["c"])
    return bm


def plate(pt):
    bm = bmesh.new(); vs = [bm.verts.new((x, y, -pt["thick"] / 2)) for x, y in pt["pts2d"]]; f = bm.faces.new(vs)
    ex = bmesh.ops.extrude_face_region(bm, geom=[f]); top = [g for g in ex["geom"] if isinstance(g, bmesh.types.BMVert)]
    for v in top: v.co.z += pt["thick"]
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bv = pt.get("bevel", 0.004)
    if bv > 0: bmesh.ops.bevel(bm, geom=list(bm.edges), offset=bv, segments=2, profile=0.5, affect="EDGES", clamp_overlap=True)
    rot = pt.get("rot", [0, 0, 0]); M = mathutils.Euler([math.radians(x) for x in rot]).to_matrix()
    for v in bm.verts: v.co = M @ v.co + Vector(pt["c"])
    return bm


def plate3d(pt):
    """a flat outline given as 3D points (roughly planar), extruded by thick along its normal, bevelled"""
    P_ = [Vector(p) for p in pt["pts3d"]]; c = sum(P_, Vector()) / len(P_)
    n = sum(((P_[i] - c).cross(P_[(i + 1) % len(P_)] - c) for i in range(len(P_))), Vector()).normalized()
    bm = bmesh.new(); vs = [bm.verts.new(p - n * pt["thick"] / 2) for p in P_]; f = bm.faces.new(vs)
    ex = bmesh.ops.extrude_face_region(bm, geom=[f])
    for v in [g for g in ex["geom"] if isinstance(g, bmesh.types.BMVert)]: v.co += n * pt["thick"]
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bv = pt.get("bevel", 0.006)
    if bv > 0: bmesh.ops.bevel(bm, geom=list(bm.edges), offset=bv, segments=pt.get("bseg", 2), profile=0.5, affect="EDGES", clamp_overlap=True)
    return bm


def radial(pt):
    """rounded boxes repeated round an axis (tractor lugs, bolt studs). arms: [[axial_offset, twist_deg, phase_frac], ...]
    each box: size [axial, tangential, radial], centred at radius r; twist turns it about its radial direction"""
    n, u, v = frame_of(pt["axis"]); o = Vector(pt["origin"]); N = pt["count"]; sa, st, sr = pt["size"]; bm = bmesh.new()
    for ax_off, tw, ph in pt.get("arms", [[0, 0, 0]]):
        for k in range(N):
            a_ = 2 * math.pi * (k + ph) / N; d = math.cos(a_) * u + math.sin(a_) * v; t = n.cross(d)
            b2 = bmesh.new(); bmesh.ops.create_cube(b2, size=1.0)
            for vv in b2.verts: vv.co = Vector((vv.co.x * sa, vv.co.y * st, vv.co.z * sr))
            bv = pt.get("bevel", 0.004)
            if bv > 0: bmesh.ops.bevel(b2, geom=list(b2.edges), offset=bv, segments=pt.get("bseg", 2), profile=0.5, affect="EDGES", clamp_overlap=True)
            R = Matrix((n, t, d)).transposed() @ Matrix.Rotation(math.radians(tw), 3, "Z")
            c = o + n * ax_off + d * pt["r"]
            for vv in b2.verts: vv.co = R @ vv.co + c
            me = bpy.data.meshes.new("tmp"); b2.to_mesh(me); b2.free(); bm.from_mesh(me); bpy.data.meshes.remove(me)
    return bm


def torus(pt):
    n, u, v = frame_of(pt["axis"]); c = Vector(pt["c"]); S, s = pt.get("seg", 32), pt.get("rseg", 10)
    rings = []
    for k in range(S):
        a_ = 2 * math.pi * k / S; d = math.cos(a_) * u + math.sin(a_) * v; cc = c + d * pt["R"]
        rings.append([cc + pt["r"] * (math.cos(2 * math.pi * j / s) * d + math.sin(2 * math.pi * j / s) * n) for j in range(s)])
    rings.append(rings[0]); return ring_seam_bm(rings, caps=False)


def loft(pt):
    return ring_seam_bm(pt["rings"], caps=pt.get("caps", True))


BUILD = {"radial": radial, "plate3d": plate3d, "lathe": lathe, "tube": tube, "rbox": rbox, "plate": plate, "torus": torus, "loft": loft}
made = []
for pt in P["parts"]:
    out = BUILD[pt["type"]](pt)
    bms = out if isinstance(out, list) else [out]
    pieces = []
    for i, bm in enumerate(bms):
        bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-6)
        pieces.append(obj_from_bm(bm, f"{pt['name']}_{i}"))
    o = pieces[0]
    if len(pieces) > 1:
        bpy.ops.object.select_all(action="DESELECT")
        for q in pieces: q.select_set(True)
        bpy.context.view_layer.objects.active = o; bpy.ops.object.join()
    o.name = pt["name"]; o.data.name = pt["name"]
    for k in ("bone", "rough", "metal", "nmap", "extr", "reach", "bake_offset", "clean"):
        if k in pt: o[k] = pt[k]
    o["has_uv"] = True
    made.append(o)
    if pt.get("mirror") == "x":
        m = o.copy(); m.data = o.data.copy(); sc.collection.objects.link(m)
        for v in m.data.vertices: v.co.x = -v.co.x
        m.data.flip_normals(); nm = pt.get("mirror_name") or pt["name"] + "_m"; m.name = nm; m.data.name = nm
        if "mirror_bone" in pt: m["bone"] = pt["mirror_bone"]
        made.append(m)
# UVs from the seams; smart project where a part has none (boxes, plates); smooth shading + smooth-by-angle
for o in made:
    bpy.ops.object.select_all(action="DESELECT"); o.select_set(True); bpy.context.view_layer.objects.active = o
    bpy.ops.object.mode_set(mode="EDIT"); bpy.ops.mesh.select_all(action="SELECT")
    if any(e.use_seam for e in o.data.edges): bpy.ops.uv.unwrap(method="ANGLE_BASED", margin=0.002)
    else: bpy.ops.uv.smart_project(angle_limit=math.radians(50), island_margin=0.002)
    bpy.ops.object.mode_set(mode="OBJECT")
    bpy.ops.object.shade_smooth_by_angle(angle=math.radians(50))
bpy.ops.object.select_all(action="SELECT")
bpy.ops.export_scene.gltf(filepath=J["out"], export_format="GLB", export_extras=True, use_selection=True)
rep = {"faces": {o.name: len(o.data.polygons) for o in made}}
if J.get("sculpt"):          # how far each idealised part sits from the sculpt (vertices -> nearest sculpt point)
    from mathutils.bvhtree import BVHTree
    bpy.ops.wm.ply_import(filepath=J["sculpt"]); hi = bpy.context.selected_objects[0]
    bm = bmesh.new(); bm.from_mesh(hi.data); tree = BVHTree.FromBMesh(bm); bm.free()
    import statistics as st_
    dist = {}
    for o in made:
        d = sorted(tree.find_nearest(o.matrix_world @ v.co)[3] for v in o.data.vertices)
        off = Vector(o.get("bake_offset", (0, 0, 0)))
        if off.length > 0:      # moved on purpose: measured where it was baked
            d = sorted(tree.find_nearest(o.matrix_world @ v.co + off)[3] for v in o.data.vertices)
        dist[o.name] = {"median_mm": round(st_.median(d) * 1000, 1), "p95_mm": round(d[int(0.95 * (len(d) - 1))] * 1000, 1)}
    rep["distance_to_sculpt"] = dist
json.dump(rep, open(J["report"], "w"), indent=1)
print("PARTS", rep["faces"], "TOTAL", sum(rep["faces"].values()))
