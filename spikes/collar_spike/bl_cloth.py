"""Blender side of the collar spike: the pattern's stand + collar (flat rest shape, wrapped start shape) settled by
Blender's own cloth sim. argv after '--': in.npz out.npz json-params."""
import sys, json
import numpy as np
import bpy, bmesh
argv = sys.argv[sys.argv.index("--") + 1:]
D = np.load(argv[0]); OUT = argv[1]; P = json.loads(argv[2]) if len(argv) > 2 else {}
bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
def mk(name, V, F, E=()):
    me = bpy.data.meshes.new(name); me.from_pydata([tuple(v) for v in V], [tuple(e) for e in E], [tuple(f) for f in F])
    me.update(); ob = bpy.data.objects.new(name, me); sc.collection.objects.link(ob); return ob
# body (collision)
body = mk("body", D["BV"], D["BF"])
body.modifiers.new("col", "COLLISION")
cs = body.collision
cs.thickness_outer = P.get("body_th", 0.0015); cs.cloth_friction = P.get("fric", 5.0); cs.damping = 0.5
# cloth: flat rest (Basis), wrapped start (shape key)
E = D["SEW"]
ob = mk("collar", D["REST"], D["T"], E)
ob.shape_key_add(name="Basis")
k = ob.shape_key_add(name="start"); k.data.foreach_set("co", D["X"].astype(np.float32).ravel()); k.value = 1.0
vg = ob.vertex_groups.new(name="pin"); vg.add([int(i) for i in D["PIN"]], 1.0, "REPLACE")
vb = ob.vertex_groups.new(name="bend")
W = D["BENDW"]
for w in np.unique(W):
    vb.add([int(i) for i in np.where(W == w)[0]], float(w), "REPLACE")
m = ob.modifiers.new("cloth", "CLOTH")
s = m.settings
s.quality = P.get("quality", 10)
s.mass = P.get("mass", 0.0003)
s.air_damping = P.get("air", 5.0)
s.tension_stiffness = s.compression_stiffness = P.get("tension", 40.0)
s.shear_stiffness = P.get("shear", 40.0)
s.bending_model = "ANGULAR"
s.bending_stiffness = P.get("bend_min", 0.5)
s.bending_stiffness_max = P.get("bend", 20.0)
s.vertex_group_bending = "bend"
s.bending_damping = P.get("bend_damp", 0.5)
s.vertex_group_mass = "pin"
s.pin_stiffness = 5.0
s.use_sewing_springs = not P.get("nosew", False)
s.sewing_force_max = P.get("sew", 5.0)
s.rest_shape_key = ob.data.shape_keys.key_blocks["Basis"]
s.effector_weights.gravity = P.get("grav", 0.05)
c = m.collision_settings
c.distance_min = P.get("cdist", 0.0015)
c.use_self_collision = P.get("self", True)
c.self_distance_min = P.get("sdist", 0.0012)
c.self_friction = 5.0
c.collision_quality = P.get("cq", 3)
m.point_cache.frame_start = 1; m.point_cache.frame_end = P.get("frames", 60)
dg = bpy.context.evaluated_depsgraph_get()
snaps = {}
for f in range(1, P.get("frames", 60) + 1):
    sc.frame_set(f)
    if f in (1, P.get("frames", 60)) or f % 20 == 0:
        dg = bpy.context.evaluated_depsgraph_get(); e = ob.evaluated_get(dg).to_mesh()
        a = np.zeros(len(e.vertices) * 3, np.float32); e.vertices.foreach_get("co", a)
        snaps[f] = a.reshape(-1, 3); ob.evaluated_get(dg).to_mesh_clear()
np.savez(OUT, X=snaps[max(snaps)], **{f"f{k}": v for k, v in snaps.items()})
print("BLDONE", len(snaps))
