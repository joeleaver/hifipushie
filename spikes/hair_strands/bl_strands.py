"""Inside Blender: our locks as guide curves of a Hair Curves object, the Essentials hair node groups on top
(duplicate -> clump -> curl -> frizz -> noise -> shrinkwrap -> profile), rendered as strands in EEVEE and Cycles."""
import glob
import json
import os
import sys
import time

import bpy
import numpy as np

job = json.load(open(sys.argv[sys.argv.index("--") + 1]))
sys.path.insert(0, job["src"])
import blender_scene  # noqa: E402

T0 = time.time()
blender_scene._open(job["blend"])
for c in bpy.data.collections:
    if c.name == "hair":
        for ob in list(c.objects):
            bpy.data.objects.remove(ob)
lib = glob.glob(os.path.join(bpy.utils.system_resource("DATAFILES"), "assets", "nodes", "procedural_hair_node_assets.blend"))[0]
want = ["Duplicate Hair Curves", "Clump Hair Curves", "Curl Hair Curves", "Frizz Hair Curves", "Hair Curves Noise",
        "Shrinkwrap Hair Curves", "Set Hair Curve Profile", "Braid Hair Curves", "Interpolate Hair Curves",
        "Trim Hair Curves", "Smooth Hair Curves"]
with bpy.data.libraries.load(lib) as (src, dst):
    dst.node_groups = [n for n in src.node_groups if n in want]
groups = {g.name: g for g in dst.node_groups}

body = next(o for o in bpy.data.objects if o.type == "MESH" and o.get("hp_part") == "body")


def strands(name, G, P):
    """A Hair Curves object from guides G (their own strand numbers P)."""
    cu = bpy.data.hair_curves.new(name)
    cu.add_curves([len(g["pts"]) for g in G])
    pts = np.concatenate([np.asarray(g["pts"], np.float32) for g in G])
    cu.attributes["position"].data.foreach_set("vector", pts.ravel())
    ob = bpy.data.objects.new(name, cu)
    bpy.context.scene.collection.objects.link(ob)
    cu.surface = body

    def add(group, **vals):
        mod = ob.modifiers.new(group, "NODES")
        mod.node_group = groups[group]
        for it in mod.node_group.interface.items_tree:
            if it.item_type != "SOCKET" or it.in_out != "INPUT":
                continue
            key = it.name if it.name in vals else f"{it.name}:{it.socket_type.replace('NodeSocket', '')}"
            if key in vals:
                try:
                    mod[it.identifier] = vals[key]
                except Exception as e:  # noqa: BLE001
                    print("@@ could not set", group, key, repr(e))
        return mod

    add("Duplicate Hair Curves", **{"Amount": int(P["amount"]), "Viewport Amount": 1.0, "Radius": float(P["radius"]),
                                    "Distribution Shape": 0.5, "Tip Roundness": 0.3, "Seed": 3})
    add("Clump Hair Curves", **{"Factor": float(P["clump"]), "Shape": 0.5, "Tip Spread": float(P.get("tip_spread", 0.004)),
                                "Distance Threshold": float(P["radius"]) * 1.2, "Preserve Length": True})
    if P.get("curl_radius", 0) > 0:
        add("Curl Hair Curves", **{"Factor": 1.0, "Subdivision": 2, "Curl Start": 0.15, "Radius": float(P["curl_radius"]),
                                   "Frequency": float(P["curl_freq"]), "Random Offset": 1.0})
    add("Frizz Hair Curves", **{"Factor": 1.0, "Distance": float(P["frizz"]), "Shape": 0.5, "Preserve Length": True})
    add("Hair Curves Noise", **{"Factor": 1.0, "Distance": float(P["noise"]), "Scale": 8.0, "Preserve Length": True})
    if P.get("shrinkwrap", True):
        add("Shrinkwrap Hair Curves", **{"Surface:Object": body, "Factor": 1.0, "Above Surface": 0.002,
                                         "Offset Distance": 0.002, "Smoothing Steps": 2, "Lock Roots": False})
    add("Set Hair Curve Profile", **{"Replace Radius": True, "Radius": float(P["strand_radius"]), "Shape": 0.4,
                                     "Factor Min": 0.5, "Factor Max": 0.15})
    return ob


m = bpy.data.materials.new("hp_strand")
m.use_nodes = True
nt = m.node_tree
nt.nodes.clear()
out = nt.nodes.new("ShaderNodeOutputMaterial")
hb = nt.nodes.new("ShaderNodeBsdfHairPrincipled")
hb.parametrization = "MELANIN"
hb.inputs["Melanin"].default_value = float(job.get("melanin", 0.72))
hb.inputs["Melanin Redness"].default_value = float(job.get("redness", 0.75))
hb.inputs["Roughness"].default_value = 0.32
hb.inputs["Radial Roughness"].default_value = 0.4
hb.inputs["Random Color"].default_value = 0.25
hb.inputs["Random Roughness"].default_value = 0.2
nt.links.new(hb.outputs[0], out.inputs["Surface"])

obs = []
for name, grp in job["groups"].items():
    ob = strands("hp_strands_" + name, grp["guides"], grp["params"])
    ob.data.materials.append(m)
    obs.append(ob)
t_build = time.time() - T0
dg = bpy.context.evaluated_depsgraph_get()
t1 = time.time()
n_curves = n_points = 0
for ob in obs:
    ev = ob.evaluated_get(dg)
    d = ev.data
    try:
        n_curves += len(d.curves)
        n_points += len(d.points)
    except Exception as e:  # noqa: BLE001
        print("@@ eval", repr(e))
print("@@ strands", json.dumps({"curves": n_curves, "points": n_points, "build_s": round(t_build, 1),
                                "eval_s": round(time.time() - t1, 1)}))
sc = bpy.context.scene
try:
    sc.render.hair_type = "STRAND"
except Exception:  # noqa: BLE001
    pass
for eng in job["engines"]:
    t = time.time()
    views = [{**v, "out": v["out"].replace(".png", f"_{eng}.png")} for v in job["views"]]
    blender_scene.render({**job, "opened": True, "views": views, "engine": eng,
                          "samples": job.get("cycles_samples", 24) if eng == "cycles" else 16})
    for ob in list(bpy.data.objects):
        if ob.name.startswith("hp_sun") or ob.name.startswith("hp_cam"):
            bpy.data.objects.remove(ob)
    print("@@ render", eng, round(time.time() - t, 1), "s for", len(views), "views")


def emit(name, rgb):
    mm = bpy.data.materials.new(name)
    mm.use_nodes = True
    mm.node_tree.nodes.clear()
    o = mm.node_tree.nodes.new("ShaderNodeOutputMaterial")
    e = mm.node_tree.nodes.new("ShaderNodeEmission")
    e.inputs["Color"].default_value = (*rgb, 1.0)
    mm.node_tree.links.new(e.outputs[0], o.inputs["Surface"])
    return mm


def render_set(suffix, eng="eevee", views=None):
    t = time.time()
    vs = [{**v, "out": v["out"].replace(".png", f"_{suffix}.png")} for v in (views or job["views"])]
    blender_scene.render({**job, "opened": True, "views": vs, "engine": eng, "samples": 16})
    for ob in list(bpy.data.objects):
        if ob.name.startswith("hp_sun") or ob.name.startswith("hp_cam"):
            bpy.data.objects.remove(ob)
    print("@@ render", suffix, round(time.time() - t, 1), "s")


vol = None
if job.get("volume"):  # the strand mass turned into one solid: points -> volume -> mesh (Geometry Nodes)
    vj = job["volume"]
    t = time.time()
    P = []
    for ob in obs:
        d = ob.evaluated_get(dg).data
        a_ = np.empty(len(d.points) * 3, np.float32)
        d.attributes["position"].data.foreach_get("vector", a_)
        P.append(a_.reshape(-1, 3)[::int(vj.get("every", 2))])
    P = np.concatenate(P)
    me = bpy.data.meshes.new("hp_volhair")
    me.vertices.add(len(P))
    me.vertices.foreach_set("co", P.ravel())
    vol = bpy.data.objects.new("hp_volhair", me)
    sc.collection.objects.link(vol)
    ng = bpy.data.node_groups.new("hp_volumize", "GeometryNodeTree")
    ng.interface.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    ng.interface.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    gi, go = ng.nodes.new("NodeGroupInput"), ng.nodes.new("NodeGroupOutput")
    m2p = ng.nodes.new("GeometryNodeMeshToPoints")
    p2v = ng.nodes.new("GeometryNodePointsToVolume")
    v2m = ng.nodes.new("GeometryNodeVolumeToMesh")
    sm = ng.nodes.new("GeometryNodeSetShadeSmooth")
    ng.links.new(gi.outputs[0], m2p.inputs[0])
    ng.links.new(m2p.outputs[0], p2v.inputs[0])
    for k_, v_ in (("Radius", float(vj["radius"])), ("Voxel Amount", 0.0), ("Voxel Size", float(vj["voxel"])), ("Density", 1.0)):
        try:
            p2v.inputs[k_].default_value = v_
        except Exception as e:  # noqa: BLE001
            print("@@ p2v", k_, repr(e))
    try:
        p2v.resolution_mode = "VOXEL_SIZE"
    except Exception:  # noqa: BLE001
        try:
            p2v.inputs["Resolution Mode"].default_value = "Size"
        except Exception as e:  # noqa: BLE001
            print("@@ p2v mode", repr(e))
    try:
        v2m.resolution_mode = "VOXEL_SIZE"
    except Exception:  # noqa: BLE001
        try:
            v2m.inputs["Resolution Mode"].default_value = "Size"
        except Exception as e:  # noqa: BLE001
            print("@@ v2m mode", repr(e))
    for k_, v_ in (("Voxel Size", float(vj["voxel"])), ("Threshold", float(vj.get("threshold", 0.3)))):
        try:
            v2m.inputs[k_].default_value = v_
        except Exception as e:  # noqa: BLE001
            print("@@ v2m", k_, repr(e))
    ng.links.new(p2v.outputs[0], v2m.inputs[0])
    ng.links.new(v2m.outputs[0], sm.inputs[0])
    ng.links.new(sm.outputs[0], go.inputs[0])
    vol.modifiers.new("volumize", "NODES").node_group = ng
    sm2 = vol.modifiers.new("smooth", "CORRECTIVE_SMOOTH")
    sm2.iterations, sm2.factor = 6, 0.6
    bm = bpy.data.materials.new("hp_volmat")
    bm.use_nodes = True
    bs = next(n for n in bm.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    bs.inputs["Base Color"].default_value = (0.09, 0.045, 0.03, 1)
    bs.inputs["Roughness"].default_value = 0.45
    ng.nodes.new("GeometryNodeSetMaterial")
    vol.data.materials.append(bm)
    dg = bpy.context.evaluated_depsgraph_get()
    n0 = len(vol.evaluated_get(dg).data.polygons)
    dec = vol.modifiers.new("dec", "DECIMATE")
    me_e = vol.evaluated_get(dg).to_mesh()
    me_e.calc_loop_triangles()
    tri0 = len(me_e.loop_triangles)
    dec.ratio = min(1.0, float(vj.get("triangles", 12000)) / max(tri0, 1))
    dg = bpy.context.evaluated_depsgraph_get()
    me_e = vol.evaluated_get(dg).to_mesh()
    me_e.calc_loop_triangles()
    print("@@ volume", json.dumps({"points": len(P), "faces": n0, "triangles": tri0,
                                   "decimated": len(me_e.loop_triangles), "s": round(time.time() - t, 1)}))
    for ob in obs:
        ob.hide_render = True
    render_set("vol")
    if job.get("id_views"):
        vol.modifiers[0].node_group.nodes  # (kept)
        g = emit("hp_green_v", (0, 1, 0))
        k = emit("hp_black_v", (0, 0, 0))
        saved = {o.name: list(o.data.materials) for o in bpy.data.objects if o.type == "MESH"}
        for o in bpy.data.objects:
            if o.type == "MESH":
                o.data.materials.clear()
                o.data.materials.append(g if o is vol else k)
        sc.view_settings.view_transform = "Standard"
        render_set("volid", views=job["id_views"])
        for o in bpy.data.objects:
            if o.type == "MESH" and o.name in saved:
                o.data.materials.clear()
                for mm in saved[o.name]:
                    o.data.materials.append(mm)
    vol.hide_render = True
    for ob in obs:
        ob.hide_render = False
if job.get("id_views"):
    g = emit("hp_green_s", (0, 1, 0))
    k = emit("hp_black_s", (0, 0, 0))
    for o in bpy.data.objects:
        if o.type == "MESH" or o in obs:
            o.data.materials.clear()
            o.data.materials.append(g if o in obs else k)
    sc.view_settings.view_transform = "Standard"
    render_set("id", views=job["id_views"])
if job.get("save"):
    bpy.ops.wm.save_as_mainfile(filepath=job["save"], compress=True)
    print("@@ saved", os.path.getsize(job["save"]) // 1024, "kB")
