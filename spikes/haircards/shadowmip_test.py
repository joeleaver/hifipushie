"""Coarse-mip card shadow check (blender_cards.game_material shadow_mip): a striped-alpha card (50 mm stripes) over a white
floor, sun overhead, the card hidden from the camera. mip 1: the floor's shadow is striped; mip 16: one soft grey.
    capped blender -b --factory-startup --python shadowmip_test.py -- <worktree src/hifipushie>"""
import sys, os, tempfile
import bpy
import numpy as np
sys.path.insert(0, sys.argv[sys.argv.index("--") + 1])
import blender_cards
sc = bpy.context.scene
for ob in list(bpy.data.objects):
    bpy.data.objects.remove(ob)
sc.render.engine = "BLENDER_EEVEE" if "BLENDER_EEVEE" in [e.identifier for e in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items] else "BLENDER_EEVEE_NEXT"
sc.render.resolution_x = sc.render.resolution_y = 64
sc.eevee.taa_render_samples = 16
sc.view_settings.view_transform = "Standard"
sc.world = bpy.data.worlds.new("w"); sc.world.use_nodes = True
sc.world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.0
png = os.path.join(tempfile.mkdtemp(), "alb.png")
g = bpy.data.images.new("alb0", 32, 32, alpha=True)
a = ((np.arange(32) // 4) % 2).astype(np.float32)
px = np.zeros((32, 32, 4), np.float32); px[..., :3] = 0.3; px[..., 3] = a[None, :]
g.pixels = px.ravel(); g.filepath_raw, g.file_format = png, "PNG"; g.save()
img = bpy.data.images.load(png)
bpy.ops.mesh.primitive_plane_add(size=4); floor = bpy.context.active_object
fm = bpy.data.materials.new("f"); fm.use_nodes = True; floor.data.materials.append(fm)
bpy.ops.mesh.primitive_plane_add(size=0.4, location=(0, 0, 0.3)); card = bpy.context.active_object
card.visible_camera = False
cd = bpy.data.cameras.new("c"); cd.type = "ORTHO"; cd.ortho_scale = 1.0
cam = bpy.data.objects.new("c", cd); sc.collection.objects.link(cam); cam.location = (0, 0, 5); sc.camera = cam
ld = bpy.data.lights.new("hp_sun0", "SUN"); ld.energy = 3.0; ld.angle = 0.0
sun = bpy.data.objects.new("hp_sun0", ld); sc.collection.objects.link(sun)
sc.render.image_settings.file_format = "OPEN_EXR"
tmp = tempfile.mkdtemp()
for mip in (1, 16):
    card.data.materials.clear()
    card.data.materials.append(blender_cards.game_material(f"t{mip}", img, None, None, 0.33, {"specular": 0.0, "wrap": 0.0, "shadow_mip": mip}))
    blender_cards.set_wrap_lights()
    sc.render.filepath = os.path.join(tmp, f"m{mip}.exr")
    bpy.ops.render.render(write_still=True)
    im = bpy.data.images.load(sc.render.filepath)
    r = np.array(im.pixels[:]).reshape(64, 64, 4)[..., 0]
    lit = float(np.median(r[:4, :4]))
    sub = r[20:44, 20:44] / max(lit, 1e-6)  # under the card (0.4 m of 1 m = 26 px)
    print(f"SHADOWMIP mip {mip}: lit {lit:.3f}, under the card mean {sub.mean():.3f} std {sub.std():.3f} min {sub.min():.3f} max {sub.max():.3f}")
