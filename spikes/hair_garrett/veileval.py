"""veileval.py <model> [count]: evaluate the groom's strands in Blender and report the strands that pass in front of
the face (rel. the head centre: in front, below the brow, within the face's width): by object, and where they root."""
import sys
import tempfile
from pathlib import Path

import numpy as np

from hifipushie import hair, hair_loose, hair_strands as hs, store

name = sys.argv[1]
count = int(sys.argv[2]) if len(sys.argv) > 2 else 60000
spec = store.load(name)
sc = hair.scalp(name, spec)
g = hair.groom_params(spec)
col = hair_loose.collider(name, spec, sc)
tmp = Path(tempfile.mkdtemp(dir="/mnt/data/hifipushie/hair_garrett/tmp"))
locks = hair.resolve(spec, sc)
sd = hs.job(sc, g, spec, [k for k in locks if not k["name"].endswith("band")], tmp, count=count, col=col)
print("groups", [(gr["name"], gr["locks"], gr["strands"], [s[0] for s in gr["stack"]]) for gr in sd["groups"]])
out = str(tmp / "ev.npz")
print(hs.evaluate(sd, out=out))
D = dict(np.load(out, allow_pickle=False))
print({k: v.shape for k, v in D.items()})
cnt = D["counts"]
first = np.r_[0, np.cumsum(cnt)[:-1]]
P = D["pts"] - sc.C
sid = np.repeat(np.arange(len(cnt)), cnt)
over = (P[:, 1] < -0.075) & (P[:, 2] < 0.0) & (P[:, 2] > -0.11) & (np.abs(P[:, 0]) < 0.045)
bad = np.unique(sid[over])
obj = D.get("obj")
names = D.get("names")
print("strands", len(cnt), "over the face", len(bad))
if obj is not None:
    for o in np.unique(obj):
        nm = names[o] if names is not None and o < len(names) else o
        print("  obj", nm, "strands", int((obj == o).sum()), "over the face", int((obj[bad] == o).sum()))
R = P[first[bad]]
if len(R):
    print("roots of the veil strands (x, y, z rel. centre), percentiles 10/50/90:")
    print(np.percentile(R, [10, 50, 90], axis=0).round(3))
    for i in bad[:10]:
        Q = P[first[i]:first[i] + cnt[i]]
        print("   root", Q[0].round(3), "tip", Q[-1].round(3), "len", round(float(np.linalg.norm(np.diff(Q, axis=0), axis=1).sum()), 3))
