"""Blender side of clutter looks: GLBs standing on rough grass under a sun and a sky (clutter.look).
blender -b --factory-startup -P blender_clutter.py -- job.json
job = {"items": [{"glb", "at": [x, y, z], "yaw": deg, "scale": s, "squash": q}], "views": [{"eye", "look", "fov", "out", "res": [w, h]}],
       "ground": [r, g, b] linear, "sun": [az, el], "clay": false, "engine": "eevee"}"""
import json, math, sys
import bpy
from mathutils import Vector

job = json.load(open(sys.argv[sys.argv.index("--") + 1]))
bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
cache = {}
for it in job["items"]:
    if it["glb"] in cache:
        new = []
        for o in cache[it["glb"]]:
            c = o.copy()
            sc.collection.objects.link(c)
            new.append(c)
        obs = new
    else:
        before = set(bpy.data.objects)
        bpy.ops.import_scene.gltf(filepath=it["glb"])
        obs = [o for o in bpy.data.objects if o not in before]
        cache[it["glb"]] = obs
    roots = [o for o in obs if o.parent is None or o.parent not in obs]
    s = it.get("scale", 1.0)
    e = bpy.data.objects.new("inst", None)
    sc.collection.objects.link(e)
    for r in roots:
        r.parent = e
    e.location = it.get("at", [0, 0, 0])
    e.rotation_euler = (0, 0, math.radians(it.get("yaw", 0)))
    e.scale = (s, s, s * it.get("squash", 1.0))
if job.get("albedo"):  # another season's picture in place of the summer one
    for im in bpy.data.images:
        if im.filepath and "_albedo" in im.filepath:
            im.filepath = im.filepath.rsplit("/", 1)[0] + "/" + job["albedo"]
            im.reload()
if job.get("clay"):
    m = bpy.data.materials.new("clay")
    m.use_nodes = True
    m.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.6, 0.6, 0.6, 1)
    m.node_tree.nodes["Principled BSDF"].inputs["Roughness"].default_value = 0.8
    for o in bpy.data.objects:
        if o.type == "MESH":
            o.data.materials.clear()
            o.data.materials.append(m)
bpy.ops.mesh.primitive_plane_add(size=400)
g = bpy.context.object
gm = bpy.data.materials.new("ground")
gm.use_nodes = True
b = gm.node_tree.nodes["Principled BSDF"]
b.inputs["Base Color"].default_value = (*job.get("ground", [0.09, 0.12, 0.04]), 1)
b.inputs["Roughness"].default_value = 1.0
nt = gm.node_tree
gcol = job.get("ground", [0.09, 0.12, 0.04])
mix = nt.nodes.new("ShaderNodeMix")
mix.data_type = "RGBA"
mix.inputs[6].default_value = (*[c * 0.7 for c in gcol], 1)
mix.inputs[7].default_value = (*[gcol[0] * 1.5, gcol[1] * 1.15, gcol[2] * 1.3], 1)
for sc_, w_ in ((3.0, 0.6), (40.0, 0.4)):
    n_ = nt.nodes.new("ShaderNodeTexNoise")
    n_.inputs["Scale"].default_value = sc_
    n_.inputs["Detail"].default_value = 6
    if sc_ < 10:
        nt.links.new(n_.outputs[0], mix.inputs[0])
    else:
        bump = nt.nodes.new("ShaderNodeBump")
        bump.inputs["Strength"].default_value = 0.6
        bump.inputs["Distance"].default_value = 0.03
        nt.links.new(n_.outputs[0], bump.inputs["Height"])
        nt.links.new(bump.outputs[0], b.inputs["Normal"])
nt.links.new(mix.outputs[2], b.inputs["Base Color"])
g.data.materials.append(gm)
az, el = job.get("sun", [215, 42])
bpy.ops.object.light_add(type="SUN")
sun = bpy.context.object
sun.data.energy = 4.0
sun.data.angle = math.radians(3)
d = Vector((math.cos(math.radians(el)) * math.sin(math.radians(az)), math.cos(math.radians(el)) * math.cos(math.radians(az)), math.sin(math.radians(el))))
sun.rotation_euler = d.to_track_quat("Z", "Y").to_euler()
w = bpy.data.worlds.new("w")
sc.world = w
w.use_nodes = True
w.node_tree.nodes["Background"].inputs[0].default_value = (0.55, 0.68, 0.9, 1)
w.node_tree.nodes["Background"].inputs[1].default_value = 0.55
try:
    sc.render.engine = "BLENDER_EEVEE_NEXT"
except Exception:
    sc.render.engine = "BLENDER_EEVEE"
if job.get("engine") == "cycles":
    sc.render.engine = "CYCLES"
    sc.cycles.samples = 48
sc.view_settings.view_transform = "Khronos PBR Neutral" if "Khronos PBR Neutral" in [i.identifier for i in type(sc.view_settings).bl_rna.properties["view_transform"].enum_items] else "Standard"
cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
sc.collection.objects.link(cam)
sc.camera = cam
for v in job["views"]:
    cam.location = v["eye"]
    cam.rotation_euler = (Vector(v["look"]) - Vector(v["eye"])).to_track_quat("-Z", "Y").to_euler()
    cam.data.lens_unit = "FOV"
    cam.data.angle = math.radians(v.get("fov", 45))
    cam.data.clip_start, cam.data.clip_end = 0.05, 2000
    sc.render.resolution_x, sc.render.resolution_y = v.get("res", [1280, 720])
    sc.render.filepath = v["out"]
    bpy.ops.render.render(write_still=True)
