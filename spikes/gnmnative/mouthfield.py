"""mouthfield.py <model>: GNM's mouth in the FIELD of a model: the prims made, signs checked (the bag's cavity at the
sock's centroid, teeth inside their own solids), the jaw's opening for the model's expression, and a sagittal section
through the mouth printed as characters (. outside, # head, T teeth, G tongue) for a first look without a render."""
import sys

import numpy as np

from hifipushie import base as basemod
from hifipushie import sdf, store
from hifipushie import spec as specmod

name = sys.argv[1]
sp = store.load(name)
prims = specmod.compile_prims(sp)
by = {}
for p in prims:
    by.setdefault(p.part, []).append(p)
print({k: [(p.name, p.kind, p.op) for p in v][:8] for k, v in by.items()})
e = specmod.expand_mirror(sp)
head = basemod.head_of({"joints": e["joints"]}, sp["base"])
print("mouth mode", basemod.mouth_mode(sp["base"], head), "| lips off GNM", round(1000 * head["mouth_off"], 3), "mm | note:",
      basemod.mouth_note(sp["base"], head))
mp = basemod.gnm_mouth(head)
M, o, up, side = mp["frame"]
print("gap mm", round(mp["gap"] * 1000, 2), "sock centroid behind M mm", round(float((M - mp["sock"]["verts"].mean(0)) @ o) * 1000, 1))
bag = next((p for p in prims if p.name == "gnm_mouth_bag"), None)
if bag is not None:
    c = mp["sock"]["verts"].mean(0)
    print("bag cavity sdf at the sock's centroid (negative = cavity):", float(sdf.SDF[bag.kind](c[None], bag.params)[0]) * 1000, "mm")
for k in ("teeth_upper", "teeth_lower", "tongue"):
    p = next(q for q in prims if q.name == f"gnm_{k}")
    c = mp[k]["verts"].mean(0)
    V = mp[k]["verts"]
    d = sdf.SDF[p.kind](V, p.params)
    print(f"{k}: field at its own vertices mm min {d.min() * 1000:.2f} max {d.max() * 1000:.2f}; at its centroid {float(sdf.SDF[p.kind](c[None], p.params)[0]) * 1000:.2f}")
# sagittal section x = 0 (and x = 12 mm): rows = up, columns = depth (front left)
for x in (0.0, 0.012):
    ys = np.arange(-0.012, 0.062, 0.001)
    zs = np.arange(0.03, -0.035, -0.001)
    P = np.array([[M + side * x - o * y + up * z for y in ys] for z in zs])
    f = {k: sdf.field_at(v, P, clip=False) for k, v in by.items() if k in ("body", "teeth", "tongue")}
    print(f"\nsection at x = {x * 1000:.0f} mm (left = front, 1 mm cells)")
    for i in range(len(zs)):
        row = ""
        for j in range(len(ys)):
            ch = "."
            if f["body"][i, j] < 0:
                ch = "#"
            if "tongue" in f and f["tongue"][i, j] < 0:
                ch = "G"
            if "teeth" in f and f["teeth"][i, j] < 0:
                ch = "T"
            row += ch
        print(row)
