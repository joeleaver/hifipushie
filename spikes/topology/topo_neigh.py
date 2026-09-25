import sys, numpy as np, topo_eval as E, topo_loops as T
for path in sys.argv[1:]:
    z = np.load(path)
    for o in (-1.2, -0.6, 0.6, 1.2):
        pl = T.joint_planes(offsets=(o,))
        print(path.split('/')[-2], f"offset {o:+}:", T.fmt(T.ring_check(z['verts'], z['loops'], z['sizes'], pl)))
