"""Runs inside headless Blender: terrain tiles reassembled through Blender's own glTF importer (not our meshes), under a
sky and sun, with the sea as a plane, trees from trees.csv, and optionally the tile borders drawn as red lines.
Job: {"glbs": [paths], "sea": level | null, "trees": csv | null, "borders": npz (segs (m, 2, 3)) | null,
"size": [w, h], "samples", "views": [{"eye", "look", "fov", "sun": [bearing, height], "borders": bool, "out"}]}."""
import csv
import json
import math
import os
import sys

import bpy
import numpy as np
from mathutils import Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import blender_terrain as bt  # noqa: E402  (tree builders)


def _terrain_material():
    m = bpy.data.materials.new("terrain")
    m.use_nodes = True
    nt = m.node_tree
    b = nt.nodes["Principled BSDF"]
    at = nt.nodes.new("ShaderNodeAttribute")
    at.attribute_name = "Color"  # COLOR_0 as the importer names it
    nt.links.new(at.outputs["Color"], b.inputs["Base Color"])
    b.inputs["Roughness"].default_value = 0.92
    for k in ("Specular IOR Level", "Specular"):
        if k in b.inputs:
            b.inputs[k].default_value = 0.12
    return m


_IMAGES = {}


def _layered(m, layers):
    """The engine recipe on an imported baked material: each layer's tiling height texture laid triplanar (Blender's
    box projection) in world metres / scale, weighted by the _WEIGHTS attributes; the sum modulates the baked base
    colour and bumps the baked normal map (what the manifest's engine_recipe describes)."""
    nt = m.node_tree
    bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
    base_in = bsdf.inputs["Base Color"].links[0].from_socket if bsdf.inputs["Base Color"].links else None
    nrm_in = bsdf.inputs["Normal"].links[0].from_socket if bsdf.inputs["Normal"].links else None
    if base_in is None:
        return
    geo = nt.nodes.new("ShaderNodeNewGeometry")
    total = None
    for L in layers:
        if L["path"] not in _IMAGES:
            _IMAGES[L["path"]] = bpy.data.images.load(L["path"])
            _IMAGES[L["path"]].colorspace_settings.name = "Non-Color"
        mp = nt.nodes.new("ShaderNodeVectorMath")
        mp.operation = "SCALE"
        mp.inputs["Scale"].default_value = 1.0 / L["scale"]
        nt.links.new(geo.outputs["Position"], mp.inputs[0])
        tx = nt.nodes.new("ShaderNodeTexImage")
        tx.image = _IMAGES[L["path"]]
        tx.projection = "BOX"
        tx.projection_blend = 0.3
        nt.links.new(mp.outputs["Vector"], tx.inputs["Vector"])
        at = nt.nodes.new("ShaderNodeAttribute")
        at.attribute_name = L["attr"]
        sep = nt.nodes.new("ShaderNodeSeparateColor")
        nt.links.new(at.outputs["Color"], sep.inputs["Color"])
        w = at.outputs["Alpha"] if L["channel"] == 3 else sep.outputs[L["channel"]]
        c = nt.nodes.new("ShaderNodeMath")  # (height - 0.5) x strength x weight
        c.operation = "SUBTRACT"
        nt.links.new(tx.outputs["Color"], c.inputs[0])
        c.inputs[1].default_value = 0.5
        s = nt.nodes.new("ShaderNodeMath")
        s.operation = "MULTIPLY"
        nt.links.new(c.outputs[0], s.inputs[0])
        s.inputs[1].default_value = L["strength"]
        mw = nt.nodes.new("ShaderNodeMath")
        mw.operation = "MULTIPLY"
        nt.links.new(s.outputs[0], mw.inputs[0])
        nt.links.new(w, mw.inputs[1])
        if total is None:
            total = mw.outputs[0]
        else:
            a = nt.nodes.new("ShaderNodeMath")
            nt.links.new(total, a.inputs[0])
            nt.links.new(mw.outputs[0], a.inputs[1])
            total = a.outputs[0]
    # albedo x (1 + 0.8 h)
    f = nt.nodes.new("ShaderNodeMath")
    f.operation = "MULTIPLY_ADD"
    nt.links.new(total, f.inputs[0])
    f.inputs[1].default_value = 1.2
    f.inputs[2].default_value = 1.0
    mul = nt.nodes.new("ShaderNodeMix")
    mul.data_type = "RGBA"
    mul.blend_type = "MULTIPLY"
    mul.inputs["Factor"].default_value = 1.0
    nt.links.new(base_in, mul.inputs["A"])
    cv = nt.nodes.new("ShaderNodeCombineColor")
    for k in range(3):
        nt.links.new(f.outputs[0], cv.inputs[k])
    nt.links.new(cv.outputs["Color"], mul.inputs["B"])
    nt.links.new(mul.outputs["Result"], bsdf.inputs["Base Color"])
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Distance"].default_value = 0.05
    bump.inputs["Strength"].default_value = 0.8
    nt.links.new(total, bump.inputs["Height"])
    if nrm_in is not None:
        nt.links.new(nrm_in, bump.inputs["Normal"])
    nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])


def _flat(name, rgb):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*rgb, 1)
    b.inputs["Emission Color"].default_value = (*rgb, 1)
    b.inputs["Emission Strength"].default_value = 1.5
    return m


def _water(level):
    bpy.ops.mesh.primitive_plane_add(size=8000, location=(500, 400, level))
    w = bpy.context.object
    wm = bpy.data.materials.new("water")
    wm.use_nodes = True
    nt = wm.node_tree
    b = nt.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (0.05, 0.14, 0.17, 1)
    b.inputs["Roughness"].default_value = 0.2
    tc = nt.nodes.new("ShaderNodeTexCoord")
    mp = nt.nodes.new("ShaderNodeMapping")
    mp.inputs["Scale"].default_value = (0.25, 0.6, 0.25)
    nz = nt.nodes.new("ShaderNodeTexNoise")
    nz.inputs["Detail"].default_value = 6.0
    bp = nt.nodes.new("ShaderNodeBump")
    bp.inputs["Distance"].default_value = 0.4
    nt.links.new(tc.outputs["Object"], mp.inputs["Vector"])
    nt.links.new(mp.outputs["Vector"], nz.inputs["Vector"])
    nt.links.new(nz.outputs["Fac"], bp.inputs["Height"])
    nt.links.new(bp.outputs["Normal"], b.inputs["Normal"])
    w.data.materials.append(wm)
    return w


def _borders(segs, radius):
    me = bpy.data.meshes.new("borders")
    pts = segs.reshape(-1, 3)
    me.vertices.add(len(pts))
    me.vertices.foreach_set("co", pts.astype(np.float64).ravel())
    me.edges.add(len(segs))
    me.edges.foreach_set("vertices", np.arange(len(pts), dtype=np.int32))
    me.update()
    ob = bpy.data.objects.new("borders", me)
    bpy.context.scene.collection.objects.link(ob)
    bpy.context.view_layer.objects.active = ob
    ob.select_set(True)
    bpy.ops.object.convert(target="CURVE")
    ob.data.bevel_depth = radius
    ob.data.bevel_resolution = 1
    m = bpy.data.materials.new("border")
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (0.9, 0.05, 0.02, 1)
    b.inputs["Emission Color"].default_value = (1.0, 0.1, 0.03, 1)
    b.inputs["Emission Strength"].default_value = 2.0
    ob.data.materials.append(m)
    return ob


def run(job):
    for coll in (bpy.data.objects, bpy.data.meshes, bpy.data.cameras, bpy.data.lights, bpy.data.materials):
        for item in list(coll):
            coll.remove(item)
    mat = _terrain_material()
    ground = []
    done = set()
    for p in job["glbs"]:
        bpy.ops.import_scene.gltf(filepath=p)
        for ob in bpy.context.selected_objects:
            if ob.type == "MESH":
                if job.get("skirt_color"):  # skirts in their own flat colour, to see where they show
                    idx = np.zeros(len(ob.data.polygons), np.int32)
                    ob.data.polygons.foreach_get("material_index", idx)
                    ob.data.materials.clear()
                    ob.data.materials.append(mat)
                    ob.data.materials.append(_flat("skirt", job["skirt_color"]))
                    ob.data.polygons.foreach_set("material_index", idx)
                    ground.append(ob)
                    continue
                # baked tiles keep the importer's material (base colour, ORM, normal map from the GLB); the rest
                # (untextured tiles, skirts, buried backs) take the vertex-colour one
                for s, m in enumerate(ob.data.materials):
                    if not (m and m.name.startswith("terrain_baked") and job.get("textured", True)):
                        ob.data.materials[s] = mat
                    elif job.get("layers") and m.name not in done:
                        _layered(m, job["layers"])
                        done.add(m.name)
                if not len(ob.data.materials):
                    ob.data.materials.append(mat)
                ground.append(ob)
    if job.get("sea") is not None:
        _water(job["sea"])
    if job.get("trees"):
        by = {}
        with open(job["trees"]) as f:
            for r in csv.DictReader(f):
                by.setdefault(r["kind"] or "broadleaf", []).append((float(r["x"]), float(r["y"]), float(r["z"])))
        box = job.get("tree_box")
        eyes = np.array([v["eye"] for v in job["views"]], float).reshape(-1, 3)
        for kind, pts in by.items():
            pts = np.array(pts)
            if box:
                (x0, y0), (x1, y1) = box
                pts = pts[(pts[:, 0] >= x0) & (pts[:, 0] <= x1) & (pts[:, 1] >= y0) & (pts[:, 1] <= y1)]
            if len(pts) and len(eyes):  # no tree over a camera (views from inside a crown rendered all green)
                d = np.linalg.norm(pts[:, None, :2] - eyes[None, :, :2], axis=2).min(1)
                pts = pts[d > 7.0]
            if not len(pts):
                continue
            me = bpy.data.meshes.new("trees_" + kind)
            me.vertices.add(len(pts))
            me.vertices.foreach_set("co", pts.astype(np.float64).ravel())
            ob = bpy.data.objects.new("trees_" + kind, me)
            bpy.context.scene.collection.objects.link(ob)
            bt._instance(ob, kind)
    border_ob = None
    if job.get("borders"):
        d = np.load(job["borders"])
        border_ob = _borders(d["segs"], job.get("border_radius", 0.35))
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.samples = job.get("samples", 32)
    scene.cycles.use_denoising = True
    scene.render.resolution_x, scene.render.resolution_y = job["size"]
    scene.view_settings.view_transform = "AgX"
    world = bpy.data.worlds.new("sky")
    scene.world = world
    world.use_nodes = True
    sky = world.node_tree.nodes.new("ShaderNodeTexSky")
    world.node_tree.links.new(sky.outputs["Color"], world.node_tree.nodes["Background"].inputs["Color"])
    world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.12
    sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN"))
    sun.data.energy = 2.4
    sun.data.angle = 0.02
    scene.collection.objects.link(sun)
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
    cam.data.clip_start, cam.data.clip_end = 0.1, 8000
    scene.collection.objects.link(cam)
    scene.camera = cam
    lamp = bpy.data.objects.new("lamp", bpy.data.lights.new("lamp", "POINT"))  # a headlamp for views inside caves
    lamp.data.shadow_soft_size = 0.3
    scene.collection.objects.link(lamp)
    # a second, weaker light down the view: a headlamp alone blew out the walls beside the eye and left the passage
    # ahead dark (inverse square), which read as fog
    fill = bpy.data.objects.new("fill", bpy.data.lights.new("fill", "POINT"))
    fill.data.shadow_soft_size = 1.0
    scene.collection.objects.link(fill)
    for v in job["views"]:
        cam.location = Vector(v["eye"])
        lamp.data.energy = float(v.get("lamp", 0.0))
        scene.view_settings.exposure = float(v.get("exposure", 0.0))
        # the lamp a little above and to the right of the eye, so ledges and roofs cast a shadow line
        fwd = (Vector(v["look"]) - Vector(v["eye"])).normalized()
        right = fwd.cross(Vector((0, 0, 1)))
        right = right.normalized() if right.length > 1e-6 else Vector((1, 0, 0))
        lamp.location = Vector(v["eye"]) + Vector((0, 0, 0.4)) + 0.35 * right
        reach = min((Vector(v["look"]) - Vector(v["eye"])).length, float(v.get("fill_at", 8.0)))
        fill.location = Vector(v["eye"]) + fwd * reach + Vector((0, 0, 0.5))
        fill.data.energy = float(v.get("fill", 0.4)) * float(v.get("lamp", 0.0))
        cam.rotation_euler = (Vector(v["look"]) - Vector(v["eye"])).to_track_quat("-Z", "Y").to_euler()
        cam.data.angle = math.radians(v.get("fov", 55))
        b, h = [math.radians(x) for x in v.get("sun", (225, 30))]
        toward = Vector((math.cos(h) * math.sin(b), math.cos(h) * math.cos(b), math.sin(h)))
        sun.rotation_euler = (-toward).to_track_quat("-Z", "Y").to_euler()
        sky.sun_elevation, sky.sun_rotation = h, -b
        if border_ob is not None:
            border_ob.hide_render = not v.get("borders", False)
        scene.render.filepath = v["out"]
        bpy.ops.render.render(write_still=True)


if __name__ == "__main__":
    run(json.load(open(sys.argv[sys.argv.index("--") + 1])))
