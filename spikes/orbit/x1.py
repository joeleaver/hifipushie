"""x1.py: what GNM offers for orbit measures (sets, groups, the lid rings' top / lateral / bottom points)."""
import numpy as np

import lidmap as lm
from hifipushie import base as basemod, gnm_controls as gc, gnm_mm, humanmacro as hm

sp = gnm_mm._space()
print("sets", {k: len(v) for k, v in sp["sets"].items()})
print("groups", sorted(sp["gr"].keys()))
g = gc.gnm()
print("gc keys", sorted(g.keys()))
T = sp["T"] * 1000
t = lm.topo()
ctr, r = lm.eye_frame_raw(None)
print("eye centre", ctr, "r", r, "eye group mean", T[sp["gr"]["left_eye"]].mean(0), "max z of eye", T[sp["gr"]["left_eye"]][:, 2].max())
L = sp["WL"] @ T
print("nasion", L[27], "brow lm 24", L[24], L[22], L[26], "lm42..47", L[42:48])
for k in range(0, 15):
    ids = t["loops"][k]
    P = T[ids] - ctr
    ang = np.degrees(np.arctan2(P[:, 1], P[:, 0]))

    def at(a):
        i = np.argmin(np.abs((ang - a + 180) % 360 - 180))
        return P[i]
    print(k, len(ids), "top", np.round(at(90), 1), "lat", np.round(at(0), 1), "bot", np.round(at(-90), 1), "med", np.round(at(180), 1))
print("hm macros", hm.NAMES)
g0 = basemod._gnm_data()
print(sorted(g0.keys()))
