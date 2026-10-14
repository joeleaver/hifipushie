"""blender_gen.py (runs INSIDE Blender, on a dressed head stage's scene.blend): the denselm sample renderer.
  blender -b <stage>/scene.blend --python blender_gen.py -- <job.npz> <out dir>
One scene, many samples: per sample the stage's meshes are RE-POSED, never rebuilt. Every vertex of the skin (and of
the lashes) is bound once to its closest point of the one mesh's skin (triangle + barycentric weights) and carried by
that point's displacement (new identity + expression - the stage's own); the eyeballs move rigidly with their centres
and turn for gaze. The paint lives in vertex attributes (wpos / wnrm / hp*), so it rides along untouched and the
material is compiled ONCE. Then camera, lights / world, exposure; EEVEE; a transparent PNG.
Labels: each landmark's pixel through Blender's own camera (bpy_extras world_to_camera_view) and its visibility by
a ray cast from the camera against the evaluated scene (skin, eyeballs, lashes, hair alike).

job.npz: P0 (N, 3) the one mesh at the stage's shape, F (M, 3) its skin triangles, D (S, N, 3) float16 displacements,
eye0 (2, 3), eye (S, 2, 3), gaze (S, 2, 3, 3), cam_eye (S, 3), cam_R (S, 3, 3: world <- camera, looking along -Z), fov (S,), shift (S, 2), LM (S, L, 3) world landmarks, light (S,) json strings, size, samples, first.
Writes <out>/<index:06d>.png and <out>/labels.npz (xy (S, L, 2) px from the top left, vis (S, L), depth (S, L) m,
sec (S,) render seconds)."""
import json
import os
import sys
import time

import bpy
import numpy as np
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree


def _lin(c):
    c = np.asarray(c, float)
    return tuple(np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4))


def bind(V, P0, F):
    """each point of V -> (three one-mesh vertices, weights): its closest point on the skin triangles."""
    tree = BVHTree.FromPolygons([tuple(p) for p in P0.tolist()], [tuple(f) for f in F.tolist()])
    fi = np.zeros(len(V), np.int64)
    C = np.zeros((len(V), 3))
    for i, p in enumerate(V.tolist()):
        loc, _n, idx, _d = tree.find_nearest(p)
        fi[i] = idx
        C[i] = loc
    T = F[fi]
    a, b, c = P0[T[:, 0]], P0[T[:, 1]], P0[T[:, 2]]
    v0, v1, v2 = b - a, c - a, C - a
    d00, d01, d11 = (v0 * v0).sum(1), (v0 * v1).sum(1), (v1 * v1).sum(1)
    d20, d21 = (v2 * v0).sum(1), (v2 * v1).sum(1)
    den = np.maximum(d00 * d11 - d01 * d01, 1e-18)
    w1 = (d11 * d20 - d01 * d21) / den
    w2 = (d00 * d21 - d01 * d20) / den
    W = np.clip(np.stack([1 - w1 - w2, w1, w2], 1), 0, 1)
    W /= W.sum(1, keepdims=True)
    return T, W.astype(np.float32), np.linalg.norm(V - C, axis=1)


def coords(me):
    V = np.empty(len(me.vertices) * 3, np.float32)
    me.vertices.foreach_get("co", V)
    return V.reshape(-1, 3).astype(np.float64)


def put(me, V):
    me.vertices.foreach_set("co", np.ascontiguousarray(V, np.float32).ravel())
    me.update()


def lights(scene, lt, target, hdri_dir):
    for ob in [o for o in bpy.data.objects if o.name.startswith(("hp_sun", "hp_window"))]:
        d = ob.data
        bpy.data.objects.remove(ob)
        bpy.data.lights.remove(d)
    scene.view_settings.view_transform = lt.get("view", "AgX")
    scene.view_settings.exposure = float(lt.get("exposure", 0.0))
    w = scene.world or bpy.data.worlds.new("w")
    scene.world = w
    w.use_nodes = True
    nt = w.node_tree
    bg = nt.nodes.get("Background")
    wc = lt.get("world") or {}
    for n in [n for n in nt.nodes if n.type in ("TEX_ENVIRONMENT", "MAPPING", "TEX_COORD")]:
        nt.nodes.remove(n)
    if wc.get("hdri"):
        env = nt.nodes.new("ShaderNodeTexEnvironment")
        p = os.path.join(hdri_dir, wc["hdri"])
        env.image = bpy.data.images.get(wc["hdri"]) or bpy.data.images.load(p)
        mp = nt.nodes.new("ShaderNodeMapping")
        tc = nt.nodes.new("ShaderNodeTexCoord")
        mp.inputs["Rotation"].default_value = (0.0, 0.0, float(wc.get("turn", 0.0)))
        nt.links.new(tc.outputs["Generated"], mp.inputs["Vector"])
        nt.links.new(mp.outputs["Vector"], env.inputs["Vector"])
        nt.links.new(env.outputs["Color"], bg.inputs["Color"])
    else:
        bg.inputs["Color"].default_value = (*_lin(wc.get("color", [0.8, 0.8, 0.8])), 1)
    bg.inputs["Strength"].default_value = float(wc.get("strength", 0.5))
    for i, L in enumerate(lt.get("lights") or []):
        ld = bpy.data.lights.new(f"hp_sun{i}", "SUN")
        ld.energy, ld.angle = float(L.get("energy", 3.0)), np.radians(float(L.get("angle", 10.0)))
        ld.color = _lin(L.get("color", [1.0, 1.0, 1.0]))
        if L.get("shadow") is False:
            ld.use_shadow = False
        if "specular" in L:
            ld.specular_factor = float(L["specular"])
        sun = bpy.data.objects.new(f"hp_sun{i}", ld)
        scene.collection.objects.link(sun)
        sun.rotation_euler = Vector(L["dir"]).to_track_quat("Z", "Y").to_euler()


def main():
    argv = sys.argv[sys.argv.index("--") + 1:]
    z = np.load(argv[0], allow_pickle=False)
    out = argv[1]
    os.makedirs(out, exist_ok=True)
    scene = bpy.context.scene
    t0 = time.time()
    if len(argv) > 2:           # the dressing's hair (hair.job): curve locks + the underlayer, shown as look_hair shows them
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "src", "hifipushie"))
        import blender_hair
        blender_hair.show(json.load(open(argv[2])))
        bpy.context.view_layer.update()
    P0, F = z["P0"].astype(np.float64), z["F"].astype(np.int64)
    body = bpy.data.objects["body"]
    eyes = bpy.data.objects.get("eyes")
    Mb = np.array(body.matrix_world)
    assert np.allclose(Mb, np.eye(4), atol=1e-6), "the stage's body is expected at the origin"
    Vb = coords(body.data)
    Tb, Wb, db = bind(Vb, P0, F)
    print(f"@@bind body {len(Vb)} verts in {time.time() - t0:.1f} s; distance to the one mesh: median {np.median(db) * 1e3:.2f} mm, "
          f"p99 {np.percentile(db, 99) * 1e3:.2f}, max {db.max() * 1e3:.2f}", flush=True)
    meshes = []                 # every other mesh rides the skin (lashes, the hair's underlayer)
    for ob in bpy.data.objects:
        if ob.type == "MESH" and ob.name not in ("body", "eyes") and not ob.hide_render and len(ob.data.vertices):
            M = np.array(ob.matrix_world)
            Vl = coords(ob.data)
            # (stage 1) GNM's teeth and tongue are bound to THEIR OWN surfaces, never to the skin beside them
            Fo = z["F_" + ob.name].astype(np.int64) if ("F_" + ob.name) in z.files else F
            Tl, Wl, dl_ = bind(Vl @ M[:3, :3].T + M[:3, 3], P0, Fo)
            print(f"@@bind {ob.name} {len(Vl)} verts: median {np.median(dl_) * 1e3:.2f} mm, p99 {np.percentile(dl_, 99) * 1e3:.2f}", flush=True)
            meshes.append((ob, Vl, Tl, Wl, np.linalg.inv(M)[:3, :3]))
    if eyes is not None:
        Ve = coords(eyes.data)
        e0 = z["eye0"].astype(np.float64)
        side = np.argmin(np.linalg.norm(Ve[:, None] - e0[None], axis=2), 1)
    # other objects that ride the head (hair locks: curve control points), bound the same way
    riders = []
    for ob in bpy.data.objects:
        if ob.type == "CURVE" and not ob.hide_render:
            pts = [p for s in ob.data.splines for p in (s.bezier_points if s.type == "BEZIER" else s.points)]
            if not pts:
                continue
            M = np.array(ob.matrix_world)
            Mi = np.linalg.inv(M)
            bez = [hasattr(p, "handle_left") for p in pts]
            X = np.array([(M @ np.r_[np.array(p.co)[:3], 1.0])[:3] for p in pts])
            T_, W_, _ = bind(X, P0, F)
            riders.append((ob, pts, bez, X, T_, W_, M, Mi))
    ee = scene.eevee
    scene.render.engine = "BLENDER_EEVEE"
    ee.use_raytracing = True
    ee.ray_tracing_method = "SCREEN"
    ee.use_fast_gi = True
    ee.fast_gi_method = "GLOBAL_ILLUMINATION"
    ee.taa_render_samples = int(z["samples"])
    for k, v in json.loads(str(z["eevee"])).items() if "eevee" in z.files else ():
        tgt = ee.ray_tracing_options if hasattr(ee.ray_tracing_options, k) and not hasattr(ee, k) else ee
        setattr(tgt, k, type(getattr(tgt, k))(v))
    size = int(z["size"])
    scene.render.resolution_x = scene.render.resolution_y = size
    scene.render.resolution_percentage = 100
    scene.render.film_transparent = True
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.render.image_settings.compression = 30
    cam_data = bpy.data.cameras.new("hp_cam")
    cam_data.clip_start, cam_data.clip_end = 0.01, 100
    cam_data.sensor_fit = "HORIZONTAL"
    cam = bpy.data.objects.new("hp_cam", cam_data)
    scene.collection.objects.link(cam)
    scene.camera = cam
    hdri_dir = os.path.join(bpy.utils.system_resource("DATAFILES"), "studiolights", "world")
    S = len(z["D"])
    first = int(z["first"]) if "first" in z.files else 0
    LM = z["LM"]
    TOL = z["tol"] if "tol" in z.files else np.full(LM.shape[1], 0.0012)
    XY = np.zeros((S, LM.shape[1], 2), np.float32)
    VIS = np.zeros((S, LM.shape[1]), np.uint8)
    DEP = np.zeros((S, LM.shape[1]), np.float32)
    SEC = np.zeros((S, 3), np.float32)
    for s in range(S):
        t = time.time()
        D = z["D"][s].astype(np.float64)
        put(body.data, Vb + (D[Tb] * Wb[:, :, None]).sum(1))
        for ob, Vl, Tl, Wl, Mi3 in meshes:
            put(ob.data, Vl + (D[Tl] * Wl[:, :, None]).sum(1) @ Mi3.T)
        if eyes is not None:
            e1, G = z["eye"][s].astype(np.float64), z["gaze"][s].astype(np.float64)
            Vn = np.empty_like(Ve)
            for k in (0, 1):
                m = side == k
                Vn[m] = (Ve[m] - e0[k]) @ G[k].T + e1[k]
            put(eyes.data, Vn)
        for ob, pts, bez, X, T_, W_, M, Mi in riders:
            dX = (D[T_] * W_[:, :, None]).sum(1) @ Mi[:3, :3].T
            for p, b_, d in zip(pts, bez, dX):
                if b_:
                    v = Vector(d)
                    p.co, p.handle_left, p.handle_right = p.co + v, p.handle_left + v, p.handle_right + v
                else:
                    p.co = (p.co[0] + d[0], p.co[1] + d[1], p.co[2] + d[2], p.co[3])
            ob["_dl_d"] = 1
        Rc = Matrix(z["cam_R"][s].tolist()).to_4x4()
        cam.matrix_world = Matrix.Translation(Vector(z["cam_eye"][s].tolist())) @ Rc
        cam_data.type = "PERSP"
        cam_data.angle = float(np.radians(z["fov"][s]))
        cam_data.shift_x, cam_data.shift_y = map(float, z["shift"][s])
        lt = json.loads(str(z["light"][s]))
        lights(scene, lt, None, hdri_dir)
        bpy.context.view_layer.update()
        t1 = time.time()
        scene.render.filepath = os.path.join(out, f"{first + s:06d}.png")
        bpy.ops.render.render(write_still=True)
        t2 = time.time()
        dg = bpy.context.evaluated_depsgraph_get()
        eye = Vector(z["cam_eye"][s].tolist())
        for i, p in enumerate(LM[s].tolist()):
            v = Vector(p)
            co = world_to_camera_view(scene, cam, v)
            XY[s, i] = (co.x * size, (1.0 - co.y) * size)
            DEP[s, i] = co.z
            ray = v - eye
            dist = ray.length
            hit, loc, _n, _i, _o, _m = scene.ray_cast(dg, eye, ray / dist, distance=dist - float(TOL[i]))
            VIS[s, i] = 0 if hit else 1
        for ob, pts, bez, X, T_, W_, M, Mi in riders:      # hair back to its rest shape
            dX = (D[T_] * W_[:, :, None]).sum(1) @ Mi[:3, :3].T
            for p, b_, d in zip(pts, bez, dX):
                if b_:
                    v = Vector(d)
                    p.co, p.handle_left, p.handle_right = p.co - v, p.handle_left - v, p.handle_right - v
                else:
                    p.co = (p.co[0] - d[0], p.co[1] - d[1], p.co[2] - d[2], p.co[3])
        SEC[s] = (t1 - t, t2 - t1, time.time() - t2)
        if s < 3 or s % 50 == 0:
            print(f"@@sample {s}: pose {t1 - t:.2f} s, render {t2 - t1:.2f} s, labels {time.time() - t2:.2f} s", flush=True)
    np.savez_compressed(os.path.join(out, "labels.npz"), xy=XY, vis=VIS, depth=DEP, sec=SEC)
    print(f"@@done {S} samples in {time.time() - t0:.0f} s", flush=True)


main()
