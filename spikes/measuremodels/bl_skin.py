"""Blender side of mkset.py: a head mesh with vertex colours -> a skinned, lit EEVEE picture through a given camera.
blender -b --factory-startup -P bl_skin.py -- <set dir> <todo.json>"""
import json
import sys

import bpy
import numpy as np
from mathutils import Matrix, Vector

SET, TODO = sys.argv[sys.argv.index("--") + 1:][:2]


def clear():
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    for m in list(bpy.data.meshes):
        bpy.data.meshes.remove(m)
    for m in list(bpy.data.materials):
        bpy.data.materials.remove(m)


def skin_material(seed):
    m = bpy.data.materials.new("skin")
    m.use_nodes = True
    nt = m.node_tree
    b = nt.nodes["Principled BSDF"]
    col = nt.nodes.new("ShaderNodeAttribute")
    col.attribute_name = "col"
    gl = nt.nodes.new("ShaderNodeAttribute")
    gl.attribute_name = "gloss"
    tc = nt.nodes.new("ShaderNodeTexCoord")
    mot = nt.nodes.new("ShaderNodeTexNoise")   # mottling, cm scale
    mot.inputs["Scale"].default_value = 55.0
    mot.inputs["Detail"].default_value = 4.0
    nt.links.new(tc.outputs["Object"], mot.inputs["Vector"])
    ramp = nt.nodes.new("ShaderNodeMapRange")
    ramp.inputs["To Min"].default_value = 0.93
    ramp.inputs["To Max"].default_value = 1.07
    nt.links.new(mot.outputs["Fac"], ramp.inputs["Value"])
    mul = nt.nodes.new("ShaderNodeMixRGB")
    mul.blend_type = "MULTIPLY"
    mul.inputs["Fac"].default_value = 1.0
    nt.links.new(col.outputs["Color"], mul.inputs["Color1"])
    nt.links.new(ramp.outputs["Result"], mul.inputs["Color2"])
    nt.links.new(mul.outputs["Color"], b.inputs["Base Color"])
    b.inputs["Subsurface Weight"].default_value = 0.35
    b.inputs["Subsurface Radius"].default_value = (1.0, 0.35, 0.2)
    b.inputs["Subsurface Scale"].default_value = 0.006
    rr = nt.nodes.new("ShaderNodeMapRange")    # eyes and lips wet
    rr.inputs["To Min"].default_value = 0.46
    rr.inputs["To Max"].default_value = 0.06
    nt.links.new(gl.outputs["Fac"], rr.inputs["Value"])
    nt.links.new(rr.outputs["Result"], b.inputs["Roughness"])
    pore = nt.nodes.new("ShaderNodeTexNoise")
    pore.inputs["Scale"].default_value = 1400.0
    pore.inputs["Detail"].default_value = 2.0
    nt.links.new(tc.outputs["Object"], pore.inputs["Vector"])
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.12
    bump.inputs["Distance"].default_value = 0.0004
    nt.links.new(pore.outputs["Fac"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], b.inputs["Normal"])
    return m


def hair_material(tone):
    m = bpy.data.materials.new("hair")
    m.use_nodes = True
    nt = m.node_tree
    b = nt.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*tone, 1.0)
    b.inputs["Roughness"].default_value = 0.5
    tc = nt.nodes.new("ShaderNodeTexCoord")
    mp = nt.nodes.new("ShaderNodeMapping")
    mp.inputs["Scale"].default_value = (600.0, 25.0, 25.0)
    nt.links.new(tc.outputs["Object"], mp.inputs["Vector"])
    n = nt.nodes.new("ShaderNodeTexNoise")
    n.inputs["Scale"].default_value = 3.0
    nt.links.new(mp.outputs["Vector"], n.inputs["Vector"])
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.6
    bump.inputs["Distance"].default_value = 0.002
    nt.links.new(n.outputs["Fac"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], b.inputs["Normal"])
    return m


def mesh(name, V, F, mat):
    me = bpy.data.meshes.new(name)
    me.from_pydata([tuple(map(float, v)) for v in V], [], [tuple(map(int, f)) for f in F])
    me.update()
    for p in me.polygons:
        p.use_smooth = True
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    me.materials.append(mat)
    return ob


def one(iid):
    clear()
    z = np.load(f"{SET}/{iid}.npz")
    meta = json.load(open(f"{SET}/{iid}.json"))
    lk = meta["look"]
    sc = bpy.context.scene
    ob = mesh("head", z["V"], z["quads"], skin_material(lk["seed"]))
    ca = ob.data.color_attributes.new("col", "FLOAT_COLOR", "POINT")
    col = np.c_[z["col"], np.ones(len(z["col"]))].astype(np.float32)
    ca.data.foreach_set("color", col.ravel())
    ga = ob.data.attributes.new("gloss", "FLOAT", "POINT")
    ga.data.foreach_set("value", z["gloss"].astype(np.float32))
    if len(z["hairV"]):
        dark = [(0.02, 0.015, 0.012), (0.08, 0.05, 0.03), (0.25, 0.18, 0.1), (0.3, 0.3, 0.3)][lk["seed"] % 4]
        mesh("hair", z["hairV"], z["hairF"], hair_material(dark))
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
    sc.collection.objects.link(cam)
    cam.matrix_world = Matrix(z["cam"].tolist())
    cam.data.sensor_fit = "HORIZONTAL"
    cam.data.sensor_width = 36.0
    cam.data.lens = float(z["lens"])
    cam.data.clip_start, cam.data.clip_end = 0.05, 20.0
    sc.camera = cam
    w, h = [int(v) for v in z["size"]]
    sc.render.resolution_x, sc.render.resolution_y, sc.render.resolution_percentage = w, h, 100
    sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN"))
    sc.collection.objects.link(sun)
    d = Vector(lk["sun"])
    sun.rotation_euler = d.to_track_quat("Z", "Y").to_euler()
    sun.data.energy = lk["sun_w"]
    sun.data.angle = np.radians(lk["soft"])
    wd = bpy.data.worlds.new("w")
    wd.use_nodes = True
    nt = wd.node_tree
    bg = nt.nodes["Background"]
    lp = nt.nodes.new("ShaderNodeLightPath")
    seen = nt.nodes.new("ShaderNodeBackground")
    seen.inputs["Color"].default_value = (*lk["back"], 1.0)
    bg.inputs["Color"].default_value = (0.85, 0.9, 1.0, 1.0)
    bg.inputs["Strength"].default_value = lk["sky"]
    mix = nt.nodes.new("ShaderNodeMixShader")
    nt.links.new(lp.outputs["Is Camera Ray"], mix.inputs["Fac"])
    nt.links.new(bg.outputs["Background"], mix.inputs[1])
    nt.links.new(seen.outputs["Background"], mix.inputs[2])
    nt.links.new(mix.outputs["Shader"], nt.nodes["World Output"].inputs["Surface"])
    sc.world = wd
    sc.render.engine = "BLENDER_EEVEE"
    try:
        sc.eevee.taa_render_samples = 48
        sc.eevee.use_shadows = True
        sc.eevee.use_raytracing = True
    except Exception as ex:  # noqa: BLE001
        print("eevee option", ex)
    sc.view_settings.view_transform = "Standard"
    sc.render.image_settings.file_format = "PNG"
    sc.render.filepath = f"{SET}/{iid}.png"
    bpy.ops.render.render(write_still=True)
    print("rendered", iid, flush=True)


for i in json.load(open(TODO)):
    one(i)
