"""Run inside Blender: import an exported plant GLB through Blender's own glTF importer, report what arrived (the
importer check: objects, uv sets, colour and custom attributes, material variants), and render it swaying from the
file's own wind channels, exactly as an engine's vertex shader would move it (veg_export.WIND_RECIPE).

blender -b --factory-startup --python blender_veg_wind.py -- job.json
job: {"glb", "out" (a folder for f_000.png ...), "frames", "fps", "size": [w, h], "strength" 0..2, "from": deg (the wind
blows from this azimuth), "height": the plant's height (m), "azimuth": camera, "report": path of the import report}
"""
import json
import math
import sys

import bpy
import numpy as np
from mathutils import Vector


def _per_vertex(me, loop_vals):
    out = np.zeros((len(me.vertices), loop_vals.shape[1]))
    li = np.zeros(len(me.loops), np.int64)
    me.loops.foreach_get("vertex_index", li)
    out[li] = loop_vals
    return out


def main(job):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=job["glb"])
    sc = bpy.context.scene
    rep = {"objects": [], "blender": bpy.app.version_string}
    movers = []
    for ob in sc.objects:
        if ob.type != "MESH":
            rep["objects"].append({"name": ob.name, "type": ob.type})
            continue
        me = ob.data
        info = {"name": ob.name, "type": "MESH", "vertices": len(me.vertices), "triangles": sum(len(p.vertices) - 2 for p in me.polygons),
                "uv_layers": [u.name for u in me.uv_layers], "color_attributes": [c.name for c in me.color_attributes],
                "attributes": [a.name for a in me.attributes if a.name.startswith("_")],
                "materials": [m.name for m in me.materials if m],
                "variants": len(getattr(me, "gltf2_variant_mesh_data", []) or [])}
        if len(me.uv_layers) >= 3:
            uv = []
            for k in (1, 2):
                a = np.zeros(len(me.loops) * 2)
                me.uv_layers[k].data.foreach_get("uv", a)
                uv.append(_per_vertex(me, a.reshape(-1, 2)))
            # Blender's importer flips v on EVERY uv set: the v components come back as 1 - value
            w = np.c_[uv[0][:, 0], 1 - uv[0][:, 1], uv[1][:, 0], 1 - uv[1][:, 1]]
            if "_WIND" in me.attributes:  # the same four, unflipped: check the two agree
                a = np.zeros(len(me.attributes["_WIND"].data) * 4)
                key = "color" if me.attributes["_WIND"].data_type in ("FLOAT_COLOR", "BYTE_COLOR") else "value"
                try:
                    me.attributes["_WIND"].data.foreach_get(key, a)
                    cw = a.reshape(-1, 4)
                    cw = cw if me.attributes["_WIND"].domain == "POINT" else _per_vertex(me, cw)
                    info["wind_custom_vs_uv_max_diff"] = round(float(np.abs(cw - w).max()), 5)
                except Exception as e:  # noqa: BLE001
                    info["wind_custom_error"] = str(e)[:120]
            info["wind_ranges"] = {k: [round(float(w[:, i].min()), 3), round(float(w[:, i].max()), 3)]
                                   for i, k in enumerate(("trunk", "branch", "phase", "flutter"))}
            co = np.zeros(len(me.vertices) * 3)
            me.vertices.foreach_get("co", co)
            nr = np.zeros(len(me.vertices) * 3)
            me.vertices.foreach_get("normal", nr)
            movers.append((ob, co.reshape(-1, 3), nr.reshape(-1, 3), w))
        rep["objects"].append(info)
    rep["scene_variants"] = [v.name for v in getattr(sc, "gltf2_KHR_materials_variants_variants", [])]
    if job.get("report"):
        open(job["report"], "w").write(json.dumps(rep, indent=1))
    print("@@import", json.dumps(rep))
    if not job.get("frames"):
        return
    for ob in sc.objects:  # the collision mesh and other LODs, should the importer have brought them in
        if "collision" in ob.name or any(f"LOD{k}" in ob.name for k in (1, 2, 3)):
            ob.hide_render = True
    H = float(job.get("height", 10.0))
    bpy.ops.mesh.primitive_plane_add(size=40 * H)
    g = bpy.context.object
    gm = bpy.data.materials.new("ground")
    gm.use_nodes = True
    gm.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.18, 0.2, 0.08, 1)
    gm.node_tree.nodes["Principled BSDF"].inputs["Roughness"].default_value = 1.0
    g.data.materials.append(gm)
    sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN"))
    sun.data.energy = 3.6
    sc.collection.objects.link(sun)
    az = math.radians(job.get("azimuth", 0.0))
    sa = az + math.radians(235)
    sun.rotation_euler = Vector((math.sin(sa) * 0.77, math.cos(sa) * 0.77, 0.64)).to_track_quat("Z", "Y").to_euler()
    w = bpy.data.worlds.new("w")
    w.use_nodes = True
    w.node_tree.nodes["Background"].inputs[0].default_value = (0.45, 0.6, 0.85, 1)
    w.node_tree.nodes["Background"].inputs[1].default_value = 0.9
    sc.world = w
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
    sc.collection.objects.link(cam)
    sc.camera = cam
    eye = Vector((-math.sin(az) * 2.6 * H, -math.cos(az) * 2.6 * H, 1.7))
    look = Vector((0, 0, 0.5 * H))
    cam.location = eye
    cam.rotation_euler = (eye - look).to_track_quat("Z", "Y").to_euler()
    cam.data.sensor_fit = "VERTICAL"
    cam.data.angle = math.radians(26)
    cam.data.clip_end = 200 * H
    sc.render.engine = "BLENDER_EEVEE"
    sc.render.resolution_x, sc.render.resolution_y = job.get("size", [480, 540])
    try:
        sc.view_settings.view_transform = "Khronos PBR Neutral"
    except Exception:  # noqa: BLE001
        pass
    wf = math.radians(job.get("from", 270.0))
    wdir = -np.array([math.sin(wf), math.cos(wf), 0.0])
    st = float(job.get("strength", 1.0))
    fps = float(job.get("fps", 12))
    for f in range(int(job["frames"])):
        t = f / fps
        gust = st * (0.65 + 0.35 * math.sin(0.9 * t) + 0.15 * math.sin(2.1 * t + 1.0))
        for ob, P, N, wv in movers:
            tr, br, ph, fl = wv[:, 0], wv[:, 1], wv[:, 2], wv[:, 3]
            sway = tr * (0.02 * H * gust) * (0.6 + 0.4 * math.sin(1.0 * t)) + br * (0.25 * gust) * np.sin(2.3 * t + 6.283 * ph)
            d = wdir[None] * sway[:, None]
            d[:, 2] -= 0.35 * np.abs(sway) * br  # a swung limb dips
            d += N * (fl * 0.02 * (0.5 + gust) * np.sin(9.0 * t + 40 * ph + P @ np.array([3.0, 3.0, 3.0])))[:, None]
            ob.data.vertices.foreach_set("co", (P + d).ravel())
            ob.data.update()
        sc.render.filepath = f"{job['out']}/f_{f:03d}.png"
        bpy.ops.render.render(write_still=True)
    print("@@frames", job["frames"])


if __name__ == "__main__":
    main(json.loads(open(sys.argv[sys.argv.index("--") + 1]).read()))
