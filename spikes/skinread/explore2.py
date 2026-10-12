"""explore2.py <model> <view>: the Python albedo at the view's pixels against Blender's flat render (ex1's npz)."""
import os, sys, time
import numpy as np
from PIL import Image
from hifipushie import skin_read as sr, store

m, vi = sys.argv[1], int(sys.argv[2])
G = os.environ["G"] + "/out"
t = time.time()
f = sr.capture(m, views=[vi], render=False)[0]
print("capture (no render)", round(time.time() - t, 1), "s; mm/px", round(f["mm"], 3), "parse", list(f["parse"]))
sk = f["skin"]
st = sr.stage_spec(store.load(m))
t = time.time()
alb = sr.Albedo(st, f["X"][sk], f["n"][sk], log=print)
A = alb()
print("albedo", len(A), "points", round(time.time() - t, 1), "s")
t = time.time(); A2 = alb(); print("again", round(time.time() - t, 2), "s")
img = np.zeros((sr.N, sr.N, 3)); img[sk] = A
B = np.load(f"{G}/ex1_{m}_{vi}.npz")["A"]
B = np.asarray(Image.fromarray(B).resize((sr.N, sr.N), Image.LANCZOS), float) / 255.0
tr = sr.trust(f) > 0.5
d = sr.lab(img[tr]) - sr.lab(sr._lin(B[..., :3])[tr])
print("python - blender flat, Lab over trusted px: mean", d.mean(0).round(2), "rms", np.sqrt((d ** 2).mean(0)).round(2), "n", tr.sum())
W = np.concatenate([sr._srgb(img), B[..., :3], np.repeat(sr.trust(f)[..., None], 3, 2)], 1)
Image.fromarray((np.clip(W, 0, 1) * 255).astype(np.uint8)).save(f"{G}/ex2_{m}_{vi}.png"); print(f"{G}/ex2_{m}_{vi}.png")
