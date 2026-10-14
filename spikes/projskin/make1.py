"""make1.py <model> [k=v]: skin_project.make on a stored model, files to out/<model>/ (debug; nothing saved)."""
import sys, os, json, pickle, numpy as np
from PIL import Image
from hifipushie import skin_project as sp
m = sys.argv[1]; kw = dict(a.split("=", 1) for a in sys.argv[2:])
out = "/mnt/data/hifipushie/projskin/out/" + m; os.makedirs(out, exist_ok=True)
r = sp.make(m, delight=kw.get("delight", "1") == "1", ears=kw.get("ears", "0") == "1", size=int(kw.get("size", sp.SIZE)), parse=kw.get("parse", "mediapipe") or None)
for k in ("albedo", "raw"):
    Image.fromarray(r[k][..., :3]).save(f"{out}/{k}.png")
Image.fromarray(r["detail"]).save(f"{out}/detail.png"); Image.fromarray(r["conf"]).save(f"{out}/conf.png")
json.dump(r["report"], open(f"{out}/report.json", "w"), indent=1, default=str)
print(r["text"])
