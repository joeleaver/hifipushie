import sys, numpy as np
from hifipushie import sdf, store
from hifipushie.spec import compile_prims
spec = store.load(sys.argv[1]); prims = compile_prims(spec)
base = [p for p in prims if p.kind == "base" and p.part == "body"]; fold = [p for p in prims if p.kind == "fold"]
pr = fold[0].params; P, U, N = pr["pts"], pr["up"], pr["nrm"]
for tt in (0.0, 1.0, 2.0, 3.0, 4.0):
    Q = P + tt * 0.001 * U
    d = (sdf.field_at(base, Q) - sdf.field_at(base + [fold[0]], Q)) * 1000
    print(tt, np.round(d[20:52], 2))
