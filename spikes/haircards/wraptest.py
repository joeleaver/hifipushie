"""Wrap diffuse check (blender_cards.game_material): one card, albedo 0.5, one sun, no world; the card's brightness at
N.L = cos(theta) over N.L = 1 must equal the notes' max(0, (N.L + 0.45) / 1.45). Run:
    capped blender -b --factory-startup --python spikes/haircards/wraptest.py -- [wrap] [shadow_leak]
Prints theta, N.L, measured ratio, expected ratio; exits 1 if any differs by more than 0.02."""
import math, sys, os, tempfile
import bpy
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "src", "hifipushie"))
import blender_cards

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
W = float(argv[0]) if argv else 0.45
LEAK = float(argv[1]) if len(argv) > 1 else 0.0  # shadow_leak: unshadowed, the result must not change
sc = bpy.context.scene
for ob in list(bpy.data.objects):
    bpy.data.objects.remove(ob)
sc.render.engine = "BLENDER_EEVEE" if "BLENDER_EEVEE" in [e.identifier for e in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items] else "BLENDER_EEVEE_NEXT"
sc.render.resolution_x = sc.render.resolution_y = 32
sc.eevee.taa_render_samples = 4
sc.view_settings.view_transform = "Standard"
sc.world = bpy.data.worlds.new("w")
sc.world.use_nodes = True
sc.world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.0
_png = os.path.join(tempfile.mkdtemp(), "alb.png")   # the pipeline's own way in: an image file, as the GLB's atlas
_g = bpy.data.images.new("alb0", 4, 4, alpha=True)
_g.pixels = [0.5, 0.5, 0.5, 1.0] * 16
_g.filepath_raw, _g.file_format = _png, "PNG"
_g.save()
img = bpy.data.images.load(_png)
img.colorspace_settings.name = "Non-Color"
bpy.ops.mesh.primitive_plane_add(size=2)
card = bpy.context.active_object
if os.environ.get("PLAIN"):
    _m = bpy.data.materials.new("p"); _m.use_nodes = True
    card.data.materials.append(_m)
else:
    card.data.materials.append(blender_cards.game_material("t", img, None, None, 0.33, {"specular": 0.0, "wrap": W, "shadow_leak": LEAK}))
cd = bpy.data.cameras.new("c"); cd.type = "ORTHO"; cd.ortho_scale = 1.0
cam = bpy.data.objects.new("c", cd); sc.collection.objects.link(cam); cam.location = (0, 0, 5); sc.camera = cam
ld = bpy.data.lights.new("hp_sun0", "SUN"); ld.energy = 3.0; ld.angle = 0.0
sun = bpy.data.objects.new("hp_sun0", ld); sc.collection.objects.link(sun)
sc.render.image_settings.file_format = "OPEN_EXR"
out = {}
tmp = tempfile.mkdtemp()
for th in (0, 45, 80, 90, 101.5, 110, 116.7, 140):
    t = math.radians(th)
    sun.rotation_euler = (t, 0, 0)   # its +Z (toward the light) tilts from the card normal by theta
    bpy.context.view_layer.update()
    blender_cards.set_wrap_lights()
    sc.render.filepath = os.path.join(tmp, f"t{th}.exr")
    bpy.ops.render.render(write_still=True)
    im = bpy.data.images.load(sc.render.filepath)
    px = np.array(im.pixels[:]).reshape(-1, 4)
    out[th] = float(np.median(px[:, 0]))
bad = 0
for th, v in out.items():
    nl = math.cos(math.radians(th))
    exp = max(0.0, (nl + W) / (1 + W)) if W > 0 else max(0.0, nl)
    r = v / out[0]
    bad += abs(r - exp) > 0.02
    print(f"WRAP theta {th:6.1f}  N.L {nl:+.3f}  measured {r:.3f}  expected {exp:.3f}  {'ok' if abs(r - exp) <= 0.02 else 'FAIL'}")
print("WRAP", "PASS" if not bad else "FAIL", f"(lit radiance {out[0]:.4f}, expected 0.5 x 3 / pi = {1.5 / math.pi:.4f})")
sys.exit(1 if bad else 0)
