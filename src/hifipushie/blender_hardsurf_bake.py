"""Hard surface from the point cloud, inside Blender: bake every part into ONE atlas.
    blender -b --factory-startup --python blender_hardsurf_bake.py -- job.json
job: {"parts": parts.glb, "sculpt": high.ply (framed, vertex colours), "views": views.npz (the point cloud's renders:
      rgb, depth, A (alpha), R, cam, f, size), "framed_to_views": 4x4, "depth_tol": 0.012, "res": 2048, "out": folder}
writes <out>/atlas_{color,normal,orm,vcol,proj_w,cover}.png, <out>/baked.glb

COLOUR is projected from the renders (sharp) at the SCULPT point each texel covers: a wide selected-to-active transfer
bake gives the sculpt's hit position + normal (the idealised part sits up to a few cm off the lumpy sculpt); each view
that sees that point square-on and passes the depth test votes (weight cos^6); the sculpt's vertex colour where no view
does; push-pull fill for the rest. Parts the artist MOVED carry bake_offset (measured position - placed position): they
bake where the sculpt has them, then go back. METALS (metal >= 0.5, or a part's `clean` 0..1) are pulled toward their
own median colour with dark smears lifted: the renders carry the generator's lighting and grime.
NORMALS come from the sculpt at the part's own short cage (extr, reach), scaled per part by `nmap` in the material."""
import bpy, bmesh, sys, os, math, json, mathutils
import numpy as np
J = json.load(open(sys.argv[sys.argv.index("--") + 1]))
D = J["out"]; RES = int(J.get("res", 2048)); os.makedirs(D, exist_ok=True)
bpy.ops.wm.read_factory_settings(use_empty=True); sc = bpy.context.scene
sc.render.engine = "CYCLES"; sc.cycles.device = "CPU"; sc.cycles.samples = 1
bpy.ops.import_scene.gltf(filepath=J["parts"])
parts = [o for o in sc.objects if o.type == "MESH"]
for o in parts:        # bake in world space: apply the import transforms
    o.select_set(True)
bpy.context.view_layer.objects.active = parts[0]
bpy.ops.object.parent_clear(type="CLEAR_KEEP_TRANSFORM")
bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
for o in [o for o in sc.objects if o.type != "MESH"]: bpy.data.objects.remove(o)
if os.environ.get("ONLY"):          # debug: bake a subset
    keep_ = os.environ["ONLY"].split(",")
    for o in [o for o in parts if o.name not in keep_]: bpy.data.objects.remove(o)
    parts = [o for o in sc.objects if o.type == "MESH"]
bpy.ops.wm.ply_import(filepath=J["sculpt"]); hi = bpy.context.selected_objects[0]; hi.name = "high"
for p in hi.data.polygons: p.use_smooth = True

# ---- one atlas: uniform texel density, all parts packed together
bpy.ops.object.select_all(action="DESELECT")
for o in parts: o.select_set(True)
bpy.context.view_layer.objects.active = parts[0]
bpy.ops.object.mode_set(mode="EDIT"); bpy.ops.mesh.select_all(action="SELECT")
for o in parts:
    if not o.data.uv_layers:
        pass
need = [o for o in parts if not o.get("has_uv")]
bpy.ops.object.mode_set(mode="OBJECT")
for o in need:          # parts the build gave no seams to: smart project
    bpy.ops.object.select_all(action="DESELECT"); o.select_set(True); bpy.context.view_layer.objects.active = o
    bpy.ops.object.mode_set(mode="EDIT"); bpy.ops.mesh.select_all(action="SELECT")
    if any(e.use_seam for e in o.data.edges):
        bpy.ops.uv.unwrap(method="ANGLE_BASED", margin=0.002)
    else:
        bpy.ops.uv.smart_project(angle_limit=math.radians(55), island_margin=0.002)
    bpy.ops.object.mode_set(mode="OBJECT")
bpy.ops.object.select_all(action="DESELECT")
for o in parts: o.select_set(True)
bpy.context.view_layer.objects.active = parts[0]
bpy.ops.object.mode_set(mode="EDIT"); bpy.ops.mesh.select_all(action="SELECT")
bpy.ops.uv.select_all(action="SELECT")
bpy.ops.uv.average_islands_scale()
bpy.ops.uv.pack_islands(margin=0.003, rotate=True)
bpy.ops.object.mode_set(mode="OBJECT")
for o in parts:
    for p in o.data.polygons: p.use_smooth = True

# ---- images
def img(name, float_=False, nc=False):
    im = bpy.data.images.new(name, RES, RES, float_buffer=float_, alpha=True)
    if nc: im.colorspace_settings.name = "Non-Color"
    im.generated_color = (0, 0, 0, 0); return im
I = {"normal": img("atlas_normal", nc=True), "vcol": img("atlas_vcol"), "pos": img("pos", True, True), "nrm": img("nrm", True, True),
     "orm": img("atlas_orm", nc=True), "cover": img("cover", nc=True), "hpos": img("hpos", True, True), "hnrm": img("hnrm", True, True), "pid": img("pid", True, True)}
I["normal"].generated_color = (0.5, 0.5, 1, 1)


def target_mat(o, image):
    m = bpy.data.materials.new(f"bake_{o.name}"); m.use_nodes = True; t = m.node_tree
    n = t.nodes.new("ShaderNodeTexImage"); n.image = image; t.nodes.active = n
    o.data.materials.clear(); o.data.materials.append(m); return m


def emit_mat(fn):
    """a material that emits fn(tree) -> socket"""
    m = bpy.data.materials.new("emit"); m.use_nodes = True; t = m.node_tree; t.nodes.clear()
    e = t.nodes.new("ShaderNodeEmission"); out = t.nodes.new("ShaderNodeOutputMaterial")
    t.links.new(fn(t), e.inputs["Color"]); t.links.new(e.outputs[0], out.inputs["Surface"]); return m, t


bk = sc.render.bake; bk.use_clear = False; bk.margin = 6; bk.margin_type = "EXTEND"
# sculpt emits its vertex colours (fallback colour) — one material, swapped for white when testing coverage
hm, ht = emit_mat(lambda t: (lambda c: (setattr(c, "layer_name", hi.data.color_attributes[0].name), c.outputs["Color"])[1])(t.nodes.new("ShaderNodeVertexColor")))
hi.data.materials.append(hm)


def bake_sel(o, image, typ, extr, reach):
    target_mat(o, image)
    bpy.ops.object.select_all(action="DESELECT"); hi.select_set(True); o.select_set(True); bpy.context.view_layer.objects.active = o
    bk.use_selected_to_active = True; bk.cage_extrusion = extr; bk.max_ray_distance = reach
    bpy.ops.object.bake(type=typ)


def bake_self(o, image, fn):
    m, t = emit_mat(fn); n = t.nodes.new("ShaderNodeTexImage"); n.image = image; t.nodes.active = n
    o.data.materials.clear(); o.data.materials.append(m)
    bpy.ops.object.select_all(action="DESELECT"); o.select_set(True); bpy.context.view_layer.objects.active = o
    bk.use_selected_to_active = False; bpy.ops.object.bake(type="EMIT")


def geo(t, k):
    g = t.nodes.new("ShaderNodeNewGeometry"); return g.outputs[k]


def value_rgb(vals):
    def f(t):
        c = t.nodes.new("ShaderNodeRGB"); c.outputs[0].default_value = (*vals, 1); return c.outputs[0]
    return f


# the idealised hard-surface part sits up to a few cm off the lumpy sculpt: the TRANSFER cage is wide (find the sculpt
# along the normal), the normal-map cage is the part's own (short: only real surface detail)
EX2, R2 = 0.04, 0.10
# parts the artist MOVED off the sculpt (bake_offset = where they were measured minus where they now sit) bake in place
import mathutils as _mu
MOVED = {o.name: _mu.Vector(list(o["bake_offset"])) for o in parts if "bake_offset" in o}
print("MOVED", {k: tuple(v) for k, v in MOVED.items()})
for o in parts:
    if o.name in MOVED: o.location += MOVED[o.name]
bpy.context.view_layer.update()
hpos_m = emit_mat(lambda t: geo(t, "Position"))[0]; hnrm_m = emit_mat(lambda t: geo(t, "Normal"))[0]; white_m = emit_mat(value_rgb((1, 1, 1)))[0]
for o in parts:
    ex, reach = float(o.get("extr", 0.012)), float(o.get("reach", 0.03))
    if float(o.get("nmap", 1.0)) > 0:
        bake_sel(o, I["normal"], "NORMAL", ex, reach)
    bake_sel(o, I["vcol"], "EMIT", EX2, R2)
    for img_, mat_ in ((I["hpos"], hpos_m), (I["hnrm"], hnrm_m), (I["cover"], white_m)):
        hi.data.materials[0] = mat_; bk.margin = 0 if img_ is I["cover"] else 6
        bake_sel(o, img_, "EMIT", EX2, R2)
    hi.data.materials[0] = hm; bk.margin = 6
    bake_self(o, I["pos"], lambda t: geo(t, "Position"))
    bake_self(o, I["nrm"], lambda t: geo(t, "Normal"))
    bake_self(o, I["orm"], value_rgb((1.0, float(o.get("rough", 0.6)), float(o.get("metal", 0.0)))))
    bake_self(o, I["pid"], value_rgb((float(parts.index(o) + 1), float(o.get("metal", 0.0)), float(o.get("clean", -1.0)))))
    print("BAKED", o.name, flush=True)


for o in parts:
    if o.name in MOVED: o.location -= MOVED[o.name]
bpy.context.view_layer.update()


def arr(im):
    x = np.empty(RES * RES * 4, np.float32); im.pixels.foreach_get(x); return x.reshape(RES, RES, 4)


pos, nrm, vcol, cover = arr(I["pos"]), arr(I["nrm"]), arr(I["vcol"]), arr(I["cover"])
hpos, hnrm = arr(I["hpos"]), arr(I["hnrm"])
island = nrm[..., 3] > 0.5
hit = cover[..., 0] > 0.5
pos[..., :3] = np.where(hit[..., None], hpos[..., :3], pos[..., :3])      # project at the SCULPT point the part covers
nrm[..., :3] = np.where(hit[..., None], hnrm[..., :3], nrm[..., :3])
# ---- projection from the splat renders
M = np.array(J["framed_to_views"], float); z = np.load(J["views"])
s, f = int(z["size"]), float(z["f"])
P = pos[..., :3][island].astype(np.float64); Nn = nrm[..., :3][island].astype(np.float64)
X = P @ M[:3, :3].T + M[:3, 3]; NX = Nn @ M[:3, :3].T; NX /= np.linalg.norm(NX, axis=1, keepdims=True) + 1e-9
acc = np.zeros((len(X), 3)); wsum = np.zeros(len(X)); best = np.zeros(len(X)); HIT = hit[island]
tol = float(J.get("depth_tol", 0.012))
for i in range(len(z["R"])):
    R, c = z["R"][i].astype(np.float64), z["cam"][i].astype(np.float64)
    Dm = z["depth"][i]; A = z["A"][i].astype(np.float32); RGB = z["rgb"][i].astype(np.float32) / 255
    p = (X - c) @ R.T; zz = p[:, 2]
    u = f * p[:, 0] / zz + s / 2 - 0.5; v = f * p[:, 1] / zz + s / 2 - 0.5
    ok = (zz > 0) & (u >= 0) & (u < s - 1) & (v >= 0) & (v < s - 1)
    ui, vi = np.clip(np.round(u).astype(int), 0, s - 1), np.clip(np.round(v).astype(int), 0, s - 1)
    d = Dm[vi, ui]; al = A[vi, ui]
    vd = c - X; vd /= np.linalg.norm(vd, axis=1, keepdims=True)
    cos = (NX * vd).sum(1)
    vis = ok & (al > 0.9) & (np.abs(d - zz) < np.where(HIT, tol, 3 * tol)) & (cos > 0.25)
    # bilinear colour
    u0, v0 = np.clip(np.floor(u).astype(int), 0, s - 2), np.clip(np.floor(v).astype(int), 0, s - 2); fu, fv = (u - u0)[:, None], (v - v0)[:, None]
    col = (RGB[v0, u0] * (1 - fu) * (1 - fv) + RGB[v0, u0 + 1] * fu * (1 - fv) + RGB[v0 + 1, u0] * (1 - fu) * fv + RGB[v0 + 1, u0 + 1] * fu * fv)
    w = np.where(vis, cos ** 6, 0.0)
    acc += col * w[:, None]; wsum += w; best = np.maximum(best, w)
proj = acc / np.maximum(wsum, 1e-9)[:, None]
srgb_v = vcol[..., :3][island]
# vcol image is sRGB-encoded in its float pixels? Blender pixels of a byte image are display values in 0..1
conf = np.clip((best - 0.02) / 0.15, 0, 1)[:, None]
outc = proj * conf + srgb_v * (1 - conf)
C = np.zeros((RES, RES, 4), np.float32); C[..., 3] = 1
C[island, :3] = outc
# texels neither seen by a view nor hit by the transfer: push-pull fill from their island neighbours
good = np.zeros((RES, RES), bool); good[island] = (conf[:, 0] > 0.3) | HIT
def pushpull(img, m):
    if min(m.shape) <= 2: return img
    h, w = m.shape[0] // 2, m.shape[1] // 2
    wm = m[:2 * h, :2 * w].reshape(h, 2, w, 2).astype(np.float32); wsum_ = wm.sum((1, 3))
    ci = (img[:2 * h, :2 * w] * m[:2 * h, :2 * w, None]).reshape(h, 2, w, 2, 3).sum((1, 3)) / np.maximum(wsum_, 1e-9)[..., None]
    coarse = pushpull(ci, wsum_ > 0)
    up = np.repeat(np.repeat(coarse, 2, 0), 2, 1); out = img.copy()
    fill = ~m[:2 * h, :2 * w]; out[:2 * h, :2 * w][fill] = up[fill]; return out
C[..., :3] = pushpull(C[..., :3], good)
# metals: the projected colour carries Idol's lighting and dark smears; an artist keeps the hue and wear but cleans it:
# pull each metal part toward its own median colour (clean = 0..1, default 0.45 for metal >= 0.5)
pidm = arr(I["pid"]); pid = np.rint(pidm[..., 0]).astype(int)
for k in np.unique(pid[island]):
    if k <= 0: continue
    m_ = island & (pid == k); metal_ = float(pidm[..., 1][m_].mean()); cl = float(pidm[..., 2][m_].mean())
    cl = cl if cl >= 0 else (0.45 if metal_ >= 0.5 else 0.0)
    if cl <= 0: continue
    med = np.median(C[m_, :3], 0); lum = C[m_, :3].mean(1, keepdims=True); lmed = med.mean()
    lifted = C[m_, :3] * np.clip(lmed / np.maximum(lum, 1e-3), 1.0, 1.8)          # dark smears lifted toward the median
    C[m_, :3] = np.clip(lifted * (1 - cl) + med * cl, 0, 1)
print("CLEANED metals")
print("FILLED texels", int((island & ~good).sum()))
W_ = np.zeros((RES, RES, 4), np.float32); W_[..., 3] = 1; W_[island, :3] = conf
HITF = hit[island]; print("HIT frac", float(HITF.mean()), "conf>0.5", float((conf[:, 0] > 0.5).mean()))
print("PROJECTED texels", int(island.sum()), "confident", float((conf > 0.5).mean()))
cimg = bpy.data.images.new("atlas_color", RES, RES, alpha=True); cimg.pixels.foreach_set(C.ravel())
wimg = bpy.data.images.new("proj_w", RES, RES, alpha=True); wimg.colorspace_settings.name = "Non-Color"; wimg.pixels.foreach_set(W_.ravel())
for k, im in (("color", cimg), ("normal", I["normal"]), ("orm", I["orm"]), ("vcol", I["vcol"]), ("proj_w", wimg), ("cover", I["cover"])):
    im.filepath_raw = f"{D}/atlas_{k}.png"; im.file_format = "PNG"; im.save()

# ---- final materials: shared atlas, per-part material (so the game can tint/swap)
for o in parts:
    m = bpy.data.materials.new(o.name); m.use_nodes = True; t = m.node_tree; b = t.nodes["Principled BSDF"]
    tc = t.nodes.new("ShaderNodeTexImage"); tc.image = cimg
    tn = t.nodes.new("ShaderNodeTexImage"); tn.image = I["normal"]; nm = t.nodes.new("ShaderNodeNormalMap"); nm.inputs["Strength"].default_value = float(o.get("nmap", 1.0)) or 0.0
    to = t.nodes.new("ShaderNodeTexImage"); to.image = I["orm"]; sp = t.nodes.new("ShaderNodeSeparateColor")
    t.links.new(tc.outputs["Color"], b.inputs["Base Color"]); t.links.new(tn.outputs["Color"], nm.inputs["Color"])
    t.links.new(nm.outputs["Normal"], b.inputs["Normal"]); t.links.new(to.outputs["Color"], sp.inputs["Color"])
    t.links.new(sp.outputs["Green"], b.inputs["Roughness"]); t.links.new(sp.outputs["Blue"], b.inputs["Metallic"])
    o.data.materials.clear(); o.data.materials.append(m)
bpy.data.objects.remove(hi)
bpy.ops.export_scene.gltf(filepath=f"{D}/baked.glb", export_format="GLB", export_extras=True)
print("DONE")
