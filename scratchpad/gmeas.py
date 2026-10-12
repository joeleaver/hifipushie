import sys
from hifipushie import store, cloth
names = sys.argv[1:]
out = {n: cloth.Body(cloth.body_mesh(store.load(n))).m["mm"] for n in names}
for k in sorted(out[names[0]]):
    print(f"{k:28s}", *[f"{out[n].get(k, float('nan')):8.0f}" for n in names])
