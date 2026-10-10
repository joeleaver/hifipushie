"""fscross.py <fsdump pkl> [result out.npz]: crossings by piece pair in the fine start (and in a fine result)."""
import sys, pickle
from collections import Counter
import numpy as np
from hifipushie import cloth

d = pickle.load(open(sys.argv[1], "rb"))
M, plan = d["M"], d["plan"]
sets = [("start", plan["start"]), ("drape", plan["drape"])]
if len(sys.argv) > 2:
    sets.append(("result", np.load(sys.argv[2])["V"]))
for lab, X in sets:
    Eh, Th = cloth._crossing_hits(X, M)
    c = Counter(tuple(sorted((M["names"][M["piece"][e[0]]], M["names"][M["piece"][t[0]]]))) for e, t in zip(Eh, Th))
    print(lab, dict(c))
