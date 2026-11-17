"""Artist retopo, inside Blender: helpers shared by blender_artretopo_{press,bake,assemble,rig,rom,look}.py.
Each of those runs headless as `blender -b --factory-startup --python <script> -- job.json` and imports this
module from its own folder (no hifipushie import inside Blender)."""
import json
import math
import sys

import bpy
import mathutils


def job():
    a = sys.argv[sys.argv.index("--") + 1:]
    return json.load(open(a[0]))


def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    return bpy.context.scene


def load_ply(path, name):
    bpy.ops.wm.ply_import(filepath=str(path))
    o = bpy.context.selected_objects[0]; o.name = name
    return o


def select_only(*objs, active=None):
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = active or objs[0]


def apply_mod(o, m):
    bpy.context.view_layer.objects.active = o; bpy.ops.object.modifier_apply(modifier=m.name)


def ortho_camera(sc, scale):
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam")); sc.collection.objects.link(cam); sc.camera = cam
    cam.data.type = "ORTHO"; cam.data.ortho_scale = scale; cam.data.clip_end = 100
    return cam


def aim(cam, target, direction, dist=3.0):
    T = mathutils.Vector(target); cam.location = T + mathutils.Vector(direction).normalized() * dist
    cam.rotation_euler = (T - cam.location).to_track_quat("-Z", "Y").to_euler()


# "side": from the character's left (+x), so it faces left (hifipushie's side view); "side_r" from its right
VIEWS = {"front": (0, -1, 0), "back": (0, 1, 0), "side": (1, 0, 0), "side_r": (-1, 0, 0), "top": (0, -0.001, 1),
         "below": (0, -0.6, -1), "3q": (-0.8, -1, 0.45), "3qr": (0.8, -1, 0.3), "3qb": (0.7, 1, 0.3)}


def workbench(sc, res, colour="MATERIAL", light="STUDIO", bg=(1, 1, 1)):
    sc.render.engine = "BLENDER_WORKBENCH"; sc.render.resolution_x = sc.render.resolution_y = res
    sh = sc.display.shading; sh.light = light; sh.color_type = colour
    sc.world = bpy.data.worlds.new("w"); sc.world.color = bg
    return sh


def flat_mat(name, rgba):
    m = bpy.data.materials.new(name); m.diffuse_color = rgba
    return m


def wire_copy(sc, o, thick, rgba):
    w = o.copy(); w.data = o.data.copy(); sc.collection.objects.link(w)
    m = w.modifiers.new("wf", "WIREFRAME"); m.thickness = thick; m.use_replace = True; m.use_even_offset = False
    w.data.materials.clear(); w.data.materials.append(flat_mat("wire", rgba)); w.color = rgba
    return w


def emission_material(name, layer=None, rgba=None):
    """an emitter of a colour attribute (layer) or a flat colour: the source of an EMIT bake"""
    m = bpy.data.materials.new(name); m.use_nodes = True; t = m.node_tree; t.nodes.clear()
    em = t.nodes.new("ShaderNodeEmission"); out = t.nodes.new("ShaderNodeOutputMaterial")
    if layer is not None:
        vc = t.nodes.new("ShaderNodeVertexColor"); vc.layer_name = layer; t.links.new(vc.outputs["Color"], em.inputs["Color"])
    else:
        em.inputs["Color"].default_value = rgba
    t.links.new(em.outputs[0], out.inputs["Surface"])
    return m


def sun_world(sc, strength=1.2, sun=3.0):
    sc.world = bpy.data.worlds.new("w"); sc.world.use_nodes = True
    sc.world.node_tree.nodes["Background"].inputs[1].default_value = strength
    s = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN")); s.data.energy = sun
    s.rotation_euler = (math.radians(50), 0, math.radians(-35)); sc.collection.objects.link(s)


def vertex_colour_material(name, layer):
    m = bpy.data.materials.new(name); m.use_nodes = True; t = m.node_tree
    vc = t.nodes.new("ShaderNodeVertexColor"); vc.layer_name = layer
    b = t.nodes["Principled BSDF"]; t.links.new(vc.outputs["Color"], b.inputs["Base Color"]); b.inputs["Roughness"].default_value = 0.6
    return m
