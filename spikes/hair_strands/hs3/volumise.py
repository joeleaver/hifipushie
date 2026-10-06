"""blender -b --factory-startup --python volumise.py -- <strands.npz> <out.png> [radius_mm=2.0] [voxel_mm=0.8]:
the one per-clump "volumise" try: each sub clump's strand points -> Points to Volume -> Volume to Mesh (Blender's
own nodes), a mesh per clump, rendered beside nothing else. Prints triangles and seconds."""
import bpy, sys, time, json
import numpy as np
a = sys.argv[sys.argv.index("--") + 1:]
z = np.load(a[0])
kw = dict(x.split("=") for x in a[2:])
rad, vox = float(kw.get("radius_mm", 2.0)) / 1000, float(kw.get("voxel_mm", 0.8)) / 1000
for ob in list(bpy.data.objects):
    bpy.data.objects.remove(ob)
names = [str(n) for n in z["names"]]
first = np.r_[0, np.cumsum(z["counts"])]
free = names.index("hair_guides_free")
sel = np.nonzero(z["obj"] == free)[0]
key = z["lock"][sel].astype(int) * 100 + z["sub"][sel].astype(int)
ng = bpy.data.node_groups.new("vol", "GeometryNodeTree")
ng.interface.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
ng.interface.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
N, L = ng.nodes, ng.links
gi, go = N.new("NodeGroupInput"), N.new("NodeGroupOutput")
def _mode(n):
    try:
        n.resolution_mode = "VOXEL_SIZE"
    except AttributeError:
        k = next(i for i in n.inputs if i.name == "Resolution Mode")
        try:
            k.default_value = "Size"
        except TypeError:
            k.default_value = "VOXEL_SIZE"
m2p = N.new("GeometryNodeMeshToPoints")
p2v = N.new("GeometryNodePointsToVolume")
_mode(p2v)
p2v.inputs["Voxel Size"].default_value = vox
p2v.inputs["Radius"].default_value = rad
v2m = N.new("GeometryNodeVolumeToMesh")
_mode(v2m)
v2m.inputs["Voxel Size"].default_value = vox
v2m.inputs["Threshold"].default_value = 0.3
sm = N.new("GeometryNodeSetShadeSmooth")
L.new(gi.outputs[0], m2p.inputs[0]); L.new(m2p.outputs[0], p2v.inputs[0]); L.new(p2v.outputs[0], v2m.inputs[0])
L.new(v2m.outputs[0], sm.inputs[0]); L.new(sm.outputs[0], go.inputs[0])
mat = bpy.data.materials.new("h")
mat.use_nodes = True
b = mat.node_tree.nodes["Principled BSDF"]
b.inputs["Base Color"].default_value = (0.11, 0.045, 0.02, 1)
b.inputs["Roughness"].default_value = 0.4
t = time.time()
tris, nclump = 0, 0
C = []
for k in np.unique(key):
    idx = sel[key == k]
    P = np.concatenate([z["pts"][first[i]:first[i + 1]] for i in idx])
    if len(P) < 50:
        continue
    me = bpy.data.meshes.new(f"c{k}")
    me.from_pydata([tuple(map(float, p)) for p in P], [], [])
    ob = bpy.data.objects.new(f"c{k}", me)
    bpy.context.scene.collection.objects.link(ob)
    md = ob.modifiers.new("vol", "NODES")
    md.node_group = ng
    me.materials.append(mat)
    C.append(P.mean(0))
    nclump += 1
dg = bpy.context.evaluated_depsgraph_get()
for ob in bpy.data.objects:
    ev = ob.evaluated_get(dg).data
    ev.calc_loop_triangles()
    tris += len(ev.loop_triangles)
    if ev.materials and ev.materials[0] is None:
        pass
print("@@", json.dumps({"clumps": nclump, "triangles": tris, "seconds": round(time.time() - t, 1), "radius_mm": rad * 1000, "voxel_mm": vox * 1000}))
c = np.mean(C, 0)
cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
bpy.context.scene.collection.objects.link(cam)
from mathutils import Vector
cam.location = Vector(c) + Vector((-0.55, 0.25, 0.1))
cam.rotation_euler = (Vector(c) - cam.location).to_track_quat("-Z", "Y").to_euler()
cam.data.lens = 60
bpy.context.scene.camera = cam
for d, e in (((-0.4, -0.7, 0.6), 3.0), ((0.5, 0.6, 0.5), 3.5)):
    ld = bpy.data.lights.new("s", "SUN"); ld.energy = e
    s = bpy.data.objects.new("s", ld); bpy.context.scene.collection.objects.link(s)
    s.rotation_euler = Vector(d).to_track_quat("Z", "Y").to_euler()
sc = bpy.context.scene
sc.render.engine = "BLENDER_EEVEE"
sc.render.resolution_x = sc.render.resolution_y = 640
sc.world = bpy.data.worlds.new("w"); sc.world.use_nodes = True
sc.world.node_tree.nodes["Background"].inputs[0].default_value = (0.55, 0.58, 0.62, 1)
sc.render.filepath = a[1]
bpy.ops.render.render(write_still=True)
