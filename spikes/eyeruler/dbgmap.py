import json, os, sys
import numpy as np
from PIL import Image
from hifipushie import blockin_brows as bb, eye_ruler as er, likeness
G = os.environ["G"] + "/out"
bx = json.load(open(G + "/box.json")); K, box = bx["K"], bx["box"]
q = bb._inputs("gd_T12")
rows = []
for tag in sys.argv[1:]:
    if tag == "photo":
        eyes = er.read(q["img"], q["P"], q["mm"], debug=True)
    else:
        im = Image.open(f"{G}/s_{tag}.png").convert("RGB")
        P = np.asarray(likeness.detect([im])[0], float)[:, :2] / K + box[:2]
        eyes = er.read(im, P, q["mm"], scale=K, origin=box[:2], debug=True)
    t = []
    for e in eyes:
        S = e["_dbg"]["K"][::-1] * 2.6 - 1.2
        sel = (er.V[::-1] < 9) & (er.V[::-1] > -8)
        a = np.clip((S[sel] + 1.2) / 2.6, 0, 1)
        t.append((a * 255).astype(np.uint8))
    rows.append(np.concatenate(t, 1))
Image.fromarray(np.concatenate(rows, 0)).save(G + "/dbgmap.png")
