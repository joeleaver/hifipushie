"""dev.py [model]: the one mesh with and without the lids' loops (gnmloops.ENABLED): old template vertices must be
bit-identical; the built field's deviation at the old surface's points (CC level-1 vertices), max / p99 over the
head and over the eye region, and how many points the loops added."""
import sys

import numpy as np

from hifipushie import base, gnmloops, humans, onemesh, store
from hifipushie.spec import expand_mirror

if len(sys.argv) > 1:
    sp = store.load(sys.argv[1])
else:
    sp = humans.spec(age=40, sex=1.0, seed=3, skin=False, source="human")
e = expand_mirror(sp)
out = {}
for on in (False, True):
    gnmloops.ENABLED = on
    onemesh._CACHE.clear(); base._CACHE.clear()
    tpl = onemesh.template(sp["base"])
    sf = base.surface(e, sp["base"])
    out[on] = (tpl, sf)
t0, s0 = out[False]; t1, s1 = out[True]
n0 = len(t0["P"])
print("template verts", n0, "->", len(t1["P"]), "faces", len(t0["S"]), "->", len(t1["S"]))
print("old vertices identical:", np.array_equal(t0["P"], t1["P"][:n0]), "fid identical:", np.array_equal(t0["fid"], t1["fid"][:n0]))
V0 = s0["verts"]
f0 = base._sd_body(V0, s0)
d = np.abs(base._sd_body(V0, s1) - f0)
d0 = np.abs(f0)
hd = base.head_of(e, sp["base"])
eye = np.asarray(hd["eyes"])
near = np.min([np.linalg.norm(V0 - c, axis=1) for c in eye], axis=0) < 0.03
head = V0[:, 2] > np.asarray(hd["eyes"])[0][2] - 0.15
for lab, m in (("head", head), ("eyes 3 cm", near)):
    print(f"{lab}: |field new - field old| at old points max {1000*d[m].max():.4f} mm p99 {1000*np.percentile(d[m],99):.4f} mean {1000*d[m].mean():.4f}; (old field's own residual there max {1000*d0[m].max():.4f}")
far = ~near & head
print("far from eyes max", 1000 * d[far].max())
w = np.argsort(-d)[:5]
print("worst points (mm from left eye):", np.round(1000 * (V0[w] - eye[0]), 1).tolist(), np.round(1000 * d[w], 3).tolist())
