import bpy, sys, numpy as np
name, out = sys.argv[sys.argv.index("--") + 1:]
ob = bpy.data.objects[name]
me = ob.data
V = np.array([ob.matrix_world @ v.co for v in me.vertices])
L = np.array([i for p in me.polygons for i in p.vertices]); S = np.array([p.loop_total for p in me.polygons])
np.savez(out, verts=V, loops=L, sizes=S)
print("@@", name, V.min(0).round(3), V.max(0).round(3), len(V), len(S))
