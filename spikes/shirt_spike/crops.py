"""crops.py <tag>: close-ups clay | strain of the fault regions (collar front, CF / placket in 3/4, sleeve end, side)."""
import sys, pickle
import numpy as np
from PIL import Image, ImageDraw
from hifipushie import cloth, resources
D = "/mnt/data/hifipushie/shirt_spike/"; t = sys.argv[1]
d = pickle.load(open(f"{D}{t}.pkl", "rb")); X = np.asarray(d["A"], float); M = d["mesh"]; F = np.asarray(M["F"])
body = {"name": "body", "V": d["bodyV"], "F": d["bodyF"], "color": "#c4bcb4"}
clay = [body, {"name": "shirt", "V": X, "F": F, "color": "#c9ccd2", "thickness": 0.0004, "offset": 0.0}]
diag = [body, {"name": "shirt", "V": X, "F": F, "mesh": M, "layer": 0, "color": "#c9ccd2"}]
import os
REG = os.environ.get("REG", "faults")
RC = {"front": ([[-0.12, -0.2, 1.40], [0.12, 0.12, 1.62]], [0, -1, 0.12]),
      "q": ([[-0.14, -0.2, 1.40], [0.14, 0.12, 1.62]], [-0.6, -0.8, 0.12]),
      "side": ([[-0.12, -0.2, 1.40], [0.12, 0.12, 1.62]], [-1, 0, 0.05]),
      "back": ([[-0.12, -0.12, 1.40], [0.12, 0.2, 1.62]], [0, 1, 0.12]),
      "top": ([[-0.14, -0.2, 1.40], [0.14, 0.14, 1.62]], [0, -0.35, 1])}
RT = {"throat": ([[-0.06, -0.2, 1.44], [0.06, 0.0, 1.56]], [0, -1, 0.1]),
      "throat_q": ([[-0.07, -0.2, 1.44], [0.07, 0.0, 1.56]], [-0.6, -0.8, 0.1]),
      "throat_low": ([[-0.06, -0.2, 1.44], [0.06, 0.0, 1.56]], [0, -1, -0.6])}
RP = {"tips": ([[-0.13, -0.2, 1.43], [0.13, 0.0, 1.55]], [0, -1, 0.1]),
      "tips_q": ([[-0.13, -0.2, 1.43], [0.13, 0.0, 1.55]], [-0.6, -0.8, 0.1]),
      "tips_low": ([[-0.13, -0.2, 1.43], [0.13, 0.0, 1.55]], [0, -1, -0.5])}
R0 = {"collar": ([[-0.11, -0.2, 1.42], [0.11, 0.1, 1.6]], [0, -1, 0.15]),
     "cf_q": ([[-0.15, -0.25, 1.2], [0.15, 0.1, 1.6]], [-0.6, -0.8, 0.1]),
     "sleeve_end": ([[0.36, -0.3, 1.02], [0.58, -0.08, 1.22]], [0, -1, 0]),
     "side": ([[-0.3, -0.2, 1.0], [0.0, 0.2, 1.6]], [-1, 0, 0])}
R = {"collar": RC, "throat": RT, "tips": RP}.get(REG, R0)
row = []
with resources.heavy(f"crops {t}", gb=4.0, gpu=True):
    for nm, (box, dirv) in R.items():
        v = [{"name": nm, "dir": dirv}]
        a = cloth.render(clay, f"{D}{t}_c{REG[0]}_{nm}", views=v, resolution=520, box=box)[0]
        b = cloth.render(diag, f"{D}{t}_s{REG[0]}_{nm}", views=v, resolution=520, box=box, diag=[os.environ.get("DIAG", "strain")] if "," not in os.environ.get("DIAG", "") else os.environ["DIAG"].split(","))[0]
        row.append((nm, Image.open(a).convert("RGB"), Image.open(b).convert("RGB")))
H = 380; sc = lambda im: im.resize((int(im.size[0] * H / im.size[1]), H))
W = sum(sc(a).size[0] + sc(b).size[0] for _, a, b in row)
sh = Image.new("RGB", (W, H + 26), "white"); x = 0; dr_ = ImageDraw.Draw(sh)
for nm, a, b in row:
    a, b = sc(a), sc(b); sh.paste(a, (x, 26)); dr_.text((x + 4, 6), f"{nm}: clay | strain", fill="black"); x += a.size[0]; sh.paste(b, (x, 26)); x += b.size[0]
sh.save(f"{D}{t}_{REG}.png"); print(f"{D}{t}_{REG}.png")
