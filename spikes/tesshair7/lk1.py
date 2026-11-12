import sys, numpy as np
from hifipushie import hair, store
from hifipushie import hair_head, hair_spec
m, n = sys.argv[1], sys.argv[2]
sp = store.load(m); sc = hair_head.scalp(m, sp); lk = sp["hair"]["locks"][n]
P = hair_spec.lock_world(sc, lk, lk["pts"]) - sc.C
for p, q in zip(lk["pts"], P):
    print("az %7.2f el %6.2f h %6.1f mm   xyz cm %6.2f %6.2f %6.2f" % (q[0] and p[0], p[1], 1000 * p[2], *(100 * q)))
