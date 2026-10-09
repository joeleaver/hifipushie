"""corner.py <model>: which vertices of the one mesh's own quads stand out at the mouth's corners: every vertex
within 9 mm of a corner landmark with its lip-ring level (0 = the mouth loop, 2 = contact ring; None = further out
or the sock), GNM group flags, and how far FORWARD it stands of the plane fitted to ring-4+ skin round the corner."""
import sys

import numpy as np

from hifipushie import base as basemod, faceshapes, retopo, store

spec = store.load(sys.argv[1])
r = retopo.wrap(spec, log=[])
V, gnm = np.asarray(r["verts"], float), np.asarray(r["gnm"])
face = faceshapes.face_of(spec)
R = face._lip_rings()
lev = R["lev"]
g = basemod._gnm_data()
sock = np.asarray(g["groups"]["mouth_sock"]) > 0.5
skin = np.asarray(g["skin"], bool)
J = {k: np.asarray(v["pos"], float) for k, v in __import__("hifipushie").spec.expand_mirror(spec)["joints"].items() if k.startswith("lm_mouth_corner")}
print("out", face.out.round(2), "levels present", sorted(set(lev.values())))
for name, c in J.items():
    d = np.linalg.norm(V - c, axis=1)
    near = np.flatnonzero(d < 0.009)
    far = [i for i in near if gnm[i] >= 0 and lev.get(int(gnm[i]), 9) >= 4]
    ref = float(np.mean(V[far] @ face.out)) if far else float(c @ face.out)
    print(name, c.round(4), "near", len(near), "ref verts", len(far))
    rows = []
    for i in near:
        gi = int(gnm[i])
        rows.append((float(V[i] @ face.out - ref) * 1000, lev.get(gi) if gi >= 0 else None, "sock" if gi >= 0 and sock[gi] and not skin[gi] else ("skin" if gi >= 0 else "body"), float(d[i] * 1000)))
    for row in sorted(rows, key=lambda x: -x[0])[:14]:
        print("   forward %+5.1f mm  level %s  %s  %.1f mm from the corner" % row)
