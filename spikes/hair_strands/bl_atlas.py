"""Inside Blender: the strand atlas BAKED from real strand clumps: per tile a few straight guides hanging in a plane,
the Essentials hair nodes on them (duplicate, clump, frizz, trim), an orthographic Cycles render with a transparent
film. Tiles: [(kind, px)] as hair_cards.TILES; the picture is 0.16 m wide x 0.25 m tall."""
import glob
import json
import os
import sys
import time

import bpy
import numpy as np

job = json.load(open(sys.argv[sys.argv.index("--") + 1]))
t0 = time.time()
for ob in list(bpy.data.objects):
    bpy.data.objects.remove(ob)
lib = glob.glob(os.path.join(bpy.utils.system_resource("DATAFILES"), "assets", "nodes", "procedural_hair_node_assets.blend"))[0]
want = ["Duplicate Hair Curves", "Clump Hair Curves", "Frizz Hair Curves", "Hair Curves Noise", "Set Hair Curve Profile",
        "Trim Hair Curves"]
with bpy.data.libraries.load(lib) as (src, dst):
    dst.node_groups = [n for n in src.node_groups if n in want]
groups = {g.name: g for g in dst.node_groups}
W, H = 0.16, 0.25
KIND = {"dense": (5, 70, 0.1, 0.95, 0.1), "medium": (4, 32, 0.45, 0.85, 0.3), "sparse": (3, 14, 0.7, 0.75, 0.4),
        "hairline": (5, 60, 0.1, 0.95, 0.1), "fly": (3, 2, 0.0, 0.8, 0.4), "baby": (6, 6, 0.0, 0.35, 0.5)}
m = bpy.data.materials.new("strand")
m.use_nodes = True
nt = m.node_tree
nt.nodes.clear()
o = nt.nodes.new("ShaderNodeOutputMaterial")
hb = nt.nodes.new("ShaderNodeBsdfHairPrincipled")
hb.parametrization = "MELANIN"
hb.inputs["Melanin"].default_value = float(job.get("melanin", 0.72))
hb.inputs["Melanin Redness"].default_value = 0.75
hb.inputs["Random Color"].default_value = 0.35
nt.links.new(hb.outputs[0], o.inputs["Surface"])
x = 0.0
rng = np.random.default_rng(4)
for kind, px in job["tiles"]:
    w = px / 1024 * W
    if kind in KIND:
        ng_, amount, clump, length, ragged = KIND[kind]
        cu = bpy.data.hair_curves.new("t")
        cu.add_curves([12] * ng_)
        P = []
        for g in range(ng_):
            gx = x + w * (0.12 + 0.76 * (g + 0.5) / ng_) + rng.normal(0, w * 0.02)
            zs = np.linspace(0, -H * length, 12)
            P.append(np.stack([np.full(12, gx) + rng.normal(0, w * 0.015) * np.linspace(0, 1, 12), np.zeros(12), zs], 1))
        cu.attributes["position"].data.foreach_set("vector", np.concatenate(P).astype(np.float32).ravel())
        ob = bpy.data.objects.new("tile", cu)
        bpy.context.scene.collection.objects.link(ob)

        def add(group, **vals):
            mod = ob.modifiers.new(group, "NODES")
            mod.node_group = groups[group]
            for it in mod.node_group.interface.items_tree:
                if it.item_type == "SOCKET" and it.in_out == "INPUT" and it.name in vals:
                    mod[it.identifier] = vals[it.name]

        add("Duplicate Hair Curves", **{"Amount": amount, "Viewport Amount": 1.0, "Radius": w * 0.38 / ng_ * 1.6,
                                        "Distribution Shape": 0.5, "Tip Roundness": 0.0, "Seed": int(rng.integers(99))})
        if clump > 0:
            add("Clump Hair Curves", **{"Factor": clump, "Shape": 0.6, "Tip Spread": 0.0005, "Preserve Length": True})
        add("Frizz Hair Curves", **{"Factor": 1.0, "Distance": 0.00025 if kind not in ("fly", "baby") else 0.0012,
                                    "Preserve Length": True})
        add("Trim Hair Curves", **{"Scale Uniform": True, "Length Factor": 1.0 - ragged * 0.5, "Random Offset": ragged,
                                   "Seed": int(rng.integers(99))})
        add("Set Hair Curve Profile", **{"Replace Radius": True, "Radius": 0.00009, "Shape": 0.4, "Factor Max": 0.3})
        cu.materials.append(m)
    x += w
sc = bpy.context.scene
cam = bpy.data.cameras.new("c")
cam.type = "ORTHO"
cam.ortho_scale = H
co = bpy.data.objects.new("c", cam)
sc.collection.objects.link(co)
co.location = (W / 2, -1.0, -H / 2)
co.rotation_euler = (np.pi / 2, 0, 0)
sc.camera = co
sun = bpy.data.objects.new("s", bpy.data.lights.new("s", "SUN"))
sun.data.energy = 3.5
sun.data.angle = 0.6
sun.rotation_euler = (np.radians(55), 0, np.radians(15))
sc.collection.objects.link(sun)
sc.world = bpy.data.worlds.new("w")
sc.world.use_nodes = True
sc.world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.6
sc.render.engine = "CYCLES"
sc.cycles.samples = 48
sc.cycles.device = "CPU"
sc.render.film_transparent = True
sc.render.resolution_x, sc.render.resolution_y = 1024, 1600
sc.render.resolution_percentage = 100
sc.view_settings.view_transform = "Standard"
sc.render.filepath = job["out"]
sc.render.image_settings.file_format = "PNG"
sc.render.image_settings.color_mode = "RGBA"
bpy.ops.render.render(write_still=True)
print("@@ atlas baked", round(time.time() - t0, 1), "s")
