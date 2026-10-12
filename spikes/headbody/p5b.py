import numpy as np
from hifipushie import makehuman, headfit
mb = makehuman.body({"age": 25, "sex": 1.0})
P = np.asarray(mb["P"], float)
print("stature", P[:,2].max(), "shoulder.L", mb["J"]["shoulder.L"], "neck", mb["J"]["neck"], "head", mb["J"]["head"], "chin", P[headfit.table()["lm68"][8]])
mid = np.flatnonzero(np.abs(P[:, 0]) < 1e-5)
fr = mid[P[mid, 1] < mb["J"]["neck"][1]]
bk = mid[P[mid, 1] >= mb["J"]["neck"][1]]
for nm, ids in (("FRONT", fr), ("BACK", bk)):
    ids = ids[(P[ids, 2] > 1.30) & (P[ids, 2] < 1.56)]
    ids = ids[np.argsort(-P[ids, 2])]
    print(nm, [(int(i), round(float(P[i, 2]), 3), round(float(P[i, 1]), 3)) for i in ids])
sh = mb["J"]["shoulder.L"]
c = np.flatnonzero((np.abs(P[:, 0] - sh[0]) < 0.03) & (np.abs(P[:, 1] - sh[1]) < 0.05) & (P[:, 2] > sh[2]))
c = c[np.argsort(-P[c, 2])][:6]
print("ACROMION candidates", [(int(i), np.round(P[i], 3).tolist()) for i in c])
