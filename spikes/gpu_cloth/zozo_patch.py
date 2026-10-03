"""ZOZO membrane patch test (run with the release's python, zozo.sh env): which way poiss-rat moves stretch and shear.
A vertical 0.2 m square of cloth (uv = its own x, z: threads along x and z) under gravity:
  stretch: pinned along its top edge, it hangs: strain along the threads = height / 0.2 - 1
  shear:   pinned along its left edge, its free side drops in plane: shear angle = atan(right edge's drop / 0.2)
for each (label, young-mod, poiss-rat) given as label:young:nu, strain limit off, bending tiny.
    python zozo_patch.py fixed:200:0.3 woven:418:0.045"""
import sys

import numpy as np
from frontend import App

res = {}
for arg in sys.argv[1:]:
    label, young, nu = arg.split(":")
    for test in ("stretch", "shear"):
        app = App.create(f"patch_{label}_{test}")
        V, F = app.mesh.square(res=16, ex=[1, 0, 0], ey=[0, 0, 1])
        V = np.asarray(V, float)[:, :3] * 0.1  # 0.2 m square centred at 0 (square() may carry its own uv columns)
        F = np.asarray(F)
        uv = V[:, [0, 2]]
        app.asset.add.tri("sheet", np.c_[V, uv], F)
        scene = app.scene.create()
        s = scene.add("sheet")
        s.param.set("density", 1.0).set("young-mod", float(young)).set("poiss-rat", float(nu))
        s.param.set("bend", 0.01).set("strain-limit", 0.0)
        edge = np.where(V[:, 2] > 0.1 - 1e-6)[0] if test == "stretch" else np.where(V[:, 0] < -0.1 + 1e-6)[0]
        s.pin(list(map(int, edge)))
        scene = scene.build()
        sess = app.session.create(scene)
        sess.param.set("frames", 72).set("dt", 0.01).set("gravity", [0.0, 0.0, -9.8]).set("air-friction", 0.5)
        sess = sess.build()
        sess.start(blocking=True)
        Vall, fr = sess.get.vertex()
        P = np.asarray(Vall, float)[:len(V)]
        if test == "stretch":
            val = (P[:, 2].max() - P[:, 2].min()) / 0.2 - 1
        else:
            right = np.where(V[:, 0] > 0.1 - 1e-6)[0]
            val = np.degrees(np.arctan2(-(P[right, 2] - V[right, 2]).mean(), 0.2))
        res[(label, test)] = val
        print(f"{label}: young {young} nu {nu}: {test} {'strain %.4f' % val if test == 'stretch' else 'angle %.2f deg' % val}",
              flush=True)
print("RESULT", res)
