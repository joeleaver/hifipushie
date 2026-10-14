"""whatlayer.py <model>: every skin paint layer's mean opacity x mask on the upper lip skin 1.5-6 mm above the lips and at
the mouth corners (atlas texels), with its colour: what is laid where a fuzzy band shows."""
import json, sys
import numpy as np
from scipy.spatial import cKDTree
from hifipushie import skin_project as sp, skin_read, store, likeness as lk, paint
m = sys.argv[1]
spec = store.load(m); at = sp.atlas(spec["base"]); regs = sp.region_masks(at)
X = sp.interp(at, at["V"]); N = sp.interp(at, lk._vertex_normals(at["V"], at["T"])); N /= np.linalg.norm(N, axis=1, keepdims=True)
dd = cKDTree(X[regs["lips"]]).query(X)[0] * 1000
zone = (regs["upper_lip_skin"] | regs["cheek"]) & (dd > 1.5) & (dd < 6.0)
idx = np.flatnonzero(zone)[::7]
st = skin_read.stage_spec(spec)
A = skin_read.Albedo(st, X[idx], N[idx], log=None)
masks = {}
A(masks=masks)
spec2, lys = A.layers()
col = {n: ly.get("color") for n, ly in lys}
for n, v in sorted(masks.items(), key=lambda kv: -float(np.mean(kv[1]))):
    if float(np.mean(v)) > 0.02:
        print(f"{n:32s} mean {float(np.mean(v)):.3f}  max {float(np.max(v)):.3f}  colour {col.get(n)}")
