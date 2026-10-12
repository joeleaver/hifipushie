"""dbgj.py <model>: the strands job's per-lock attributes for the temple / sideburn strip's gather locks (n strands,
rs = start stagger factor, fn, ex), the object's Roots, and each lock's length: where do its strands start?"""
import sys

import numpy as np

from hifipushie import hair, store

m = sys.argv[1]
spec = store.load(m)
j = hair.job(m, spec)
sd = j["strands"]
print("physical roots", sd["physical"]["roots"], "count", sd["physical"]["count"])
for g in sd["groups"]:
    print(g["name"], g["locks"], "locks", g["strands"], "strands")
    if g["name"] != "hair_guides":
        continue
    z = np.load(g["guides"])
    names = [str(n) for n in z["names"]]
    cnt = z["counts"]
    P = z["pts"].reshape(len(cnt), -1, 3)
    L = np.linalg.norm(np.diff(P, axis=1), axis=2).sum(1)
    Lk = spec["hair"]["locks"]
    roots = sd["physical"]["roots"]
    for i, n in enumerate(names):
        lk = Lk.get(n)
        if lk and n.startswith("tg") and 45 < lk["pts"][0][0] < 100 and lk["pts"][0][1] < 12:
            print(f"  {n} len {L[i] * 100:.0f} cm n {int(z['n'][i])} rs {float(z['rs'][i]):.2f} -> starts over {roots * float(z['rs'][i]) * L[i] * 100:.1f} cm"
                  f" fn {float(z['fn'][i]) if 'fn' in z.files else 0:.2f} ex {float(z['ex'][i]) if 'ex' in z.files else 0:.2f} root az/el {lk['pts'][0][:2]}")
