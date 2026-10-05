import sys, json, numpy as np
from hifipushie import hair, store
name = sys.argv[1]
spec = store.load(name)
h = spec["hair"]
print({k: (v if k != "locks" else len(v)) for k, v in h.items() if k not in ("groom",)})
print("groom", json.dumps({k: v for k, v in h.get("groom", {}).items() if k != "drawn"})[:900])
sc = hair.scalp(name, spec)
tiers = {}
for n, lk in h["locks"].items():
    P = hair.lock_world(sc, lk, lk["pts"])
    L = np.linalg.norm(np.diff(P, axis=0), axis=1).sum()
    key = (lk.get("tier"), n.rstrip("0123456789_").rstrip("0123456789"), bool(lk.get("free")))
    tiers.setdefault(key, []).append((lk["width"], lk["thickness"], L))
for k, v in tiers.items():
    a = np.array(v)
    print(k, len(v), "width", a[:, 0].min().round(3), a[:, 0].max().round(3), "thick", a[:, 1].mean().round(4), "len", a[:, 2].min().round(3), a[:, 2].max().round(3))
