"""hl.py <model>: the hairline's elevation and height by azimuth, the ear's landmarks, lock counts by name prefix,
the look and strand dials (what a round starts from)."""
import collections
import sys

import numpy as np

from hifipushie import hair, store

m = sys.argv[1]
sp = store.load(m)
sc = hair.scalp(m, sp)
g = hair.groom_params(sp)
line = hair.hairline(sc, g)
for a in list(range(0, 181, 10)):
    p = sc.point(float(a), float(line[a]), 0.0) - sc.C
    print(a, round(float(line[a]), 1), "xyz", np.round(p, 3))
print("C", sc.C, {k: np.round(np.asarray(v) - sc.C, 3) for k, v in sc.lm.items() if "ear" in k or "brow_outer" in k or "jaw_0" in k})
c = collections.Counter(n.rstrip("0123456789_") for n in sp["hair"]["locks"])
print(c)
print("look", sp["hair"].get("look"))
print("strands", sp["hair"].get("strands"))
print("groom", {k: v for k, v in sp["hair"]["groom"].items() if k != "hairline"})
print("hairline", str(sp["hair"]["groom"].get("hairline"))[:600])
print("parts.hair", (sp.get("parts") or {}).get("hair"))
