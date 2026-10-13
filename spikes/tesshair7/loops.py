"""loops.py <model>: gather locks whose spines turn too much (loops / kinks): total turning (deg) along the drawn
spine, where they root (x off the part, y back from the front), their height range. Light, no Blender."""
import sys
import numpy as np
from hifipushie import hair, hair_cards as hc, store

m = sys.argv[1]
sp = store.load(m)
sc = hair.scalp(m, sp)
y0 = -float(sc.r(0.0, 30.0)) * np.cos(np.radians(30.0))
rows = []
for n, lk in sp["hair"]["locks"].items():
    if not n.startswith("tg") or lk.get("space") == "xyz":
        continue
    P = hair.lock_world(sc, lk, lk["pts"])
    S = hc.spine({**lk, "pts": P.tolist()}, 80)[0]
    T = np.diff(S, axis=0)
    T /= np.maximum(np.linalg.norm(T, axis=1, keepdims=True), 1e-9)
    turn = np.degrees(np.arccos(np.clip((T[1:] * T[:-1]).sum(1), -1, 1))).sum()
    h = np.asarray(lk["pts"])[:, 2]
    r = P[0] - sc.C
    rows.append((turn, n, r[0], r[1] - y0, h.min(), h.max(), lk["width"], lk.get("strands", {}).get("clump_size")))
rows.sort(reverse=True)
print("turn deg | lock | x off centre | y back | h min / max mm | width | clump_size")
for t, n, x, y, a, b, w, cs in rows[:14]:
    print(f"{t:6.0f}  {n:9s} {x*100:5.1f} cm {y*100:5.1f} cm  {a*1000:5.1f} / {b*1000:5.1f}  {w:.4f}  {cs}")
print("median turn", round(float(np.median([r[0] for r in rows])), 1))
