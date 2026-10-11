import json, os, sys
import numpy as np
from PIL import Image
from hifipushie import blockin_brows as bb, eye_ruler as er, likeness
G = os.environ["G"] + "/out"
bx = json.load(open(G + "/box.json")); K, box = bx["K"], bx["box"]
q = bb._inputs("gd_T12")
tag = sys.argv[1]
if tag == "photo":
    eyes = er.read(q["img"], q["P"], q["mm"], debug=True)
else:
    im = Image.open(f"{G}/s_{tag}.png").convert("RGB")
    P = np.asarray(likeness.detect([im])[0], float)[:, :2] / K + box[:2]
    eyes = er.read(im, P, q["mm"], scale=K, origin=box[:2], debug=True)
for e in eyes:
    g = e["_dbg"]
    print("a b", g["uu"][g["a"]], g["uu"][g["b"]])
    for j in range(0, len(g["uu"]), 6):
        print(f"u {g['uu'][j]:6.2f} up {g['up'][j]:5.2f} lo {g['lo'][j]:5.2f} con {g['con'][j]:5.2f} crestU {g['S'][er._iv(g['ru'][j]), er._iu(g['uu'][j])]:5.2f} crestL {g['S'][er._iv(g['rl'][j]), er._iu(g['uu'][j])]:5.2f}")
