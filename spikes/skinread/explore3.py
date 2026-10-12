"""explore3.py <model> [anchor]: the region reads (picture's albedo - ours, Lab) of a model, the anchor, the views."""
import os, pickle, sys, time
import numpy as np
from PIL import Image
from hifipushie import skin_read as sr

m = sys.argv[1]
G = os.environ["G"] + "/out"
fp = f"{G}/frames_{m}.pkl"
if os.path.exists(fp) and not os.environ.get("FRESH"):
    frames = pickle.load(open(fp, "rb"))
else:
    frames = sr.capture(m)
    pickle.dump(frames, open(fp, "wb"))
t = time.time()
c = sr.context(m, frames=frames, anchor=sys.argv[2] if len(sys.argv) > 2 else "auto")
print("context", round(time.time() - t, 1), "s;", len(c.X), "points")
print("anchor:", c.anchor["kind"], "|", c.anchor["note"])
for v in c.views:
    print(" view", v)
R = sr.regions(c)
print(f"{'region':16s} {'px':>8s}  ours L a b          picture L a b       d L a b   (by view)")
for k, wz in R.items():
    r = sr._region(c, wz)
    if not r["read"]:
        print(f"{k:16s} {r['px']:8.0f}  NOT READ"); continue
    print(f"{k:16s} {r['px']:8.0f}  {str(r['ours']):20s} {str(r['picture']):20s} {str(r['d']):22s} {r.get('by_view', '')}")
# pictures: P | R | T (picture's albedo) | A (ours) per view
rows = []
for f in frames:
    msk = np.zeros(sr.N * sr.N, bool); sel = c.view == f["view"]
    T = np.zeros((sr.N * sr.N, 3)); A = np.zeros((sr.N * sr.N, 3))
    T[c.pix[sel]] = c.T[sel] * (c.w[sel] > 0)[:, None]; A[c.pix[sel]] = c.A0[sel]
    rows.append(np.concatenate([sr._srgb(f["P"]), sr._srgb(f["R"]), sr._srgb(T.reshape(sr.N, sr.N, 3)), sr._srgb(A.reshape(sr.N, sr.N, 3))], 1))
Image.fromarray((np.clip(np.concatenate(rows, 0), 0, 1) * 255).astype(np.uint8)).save(f"{G}/ex3_{m}.png"); print(f"{G}/ex3_{m}.png")
