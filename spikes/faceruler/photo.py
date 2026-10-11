"""photo.py <model> [out.png]: the face ruler on a block-in model's reference pictures (read only: no model is changed).
Prints the table; out.png = per view the picture with the model's outline (green), the picture's outline (red) and the
matched samples (yellow), the iris reads (magenta = picture, cyan = model)."""
import sys
import time

import numpy as np
from PIL import Image, ImageDraw

from hifipushie import face_ruler as fr

name = sys.argv[1]
t = time.time()
res = fr.compare(name)
print(res["text"])
print(f"({time.time() - t:.0f} s; reads {res['n']})")
if len(sys.argv) > 2:
    tiles = []
    for v in res["views"]:
        im = v["img"].copy()
        d = ImageDraw.Draw(im)
        _, ps = fr.clay(res["head"], v["cam"], passes=True)
        cm = fr._curve(ps["part"] >= 0)
        d.line([tuple(p) for p in cm], fill=(0, 220, 0), width=2)
        if v.get("outline") is not None:
            d.line([tuple(p) for p in np.asarray(v["outline"])], fill=(240, 0, 0), width=2)
        for ob in res["obs"]:
            if ob["view"] != v["kind"]:
                continue
            if ob["type"] == "outline":
                d.line([tuple(ob["p"]), tuple(ob["q"])], fill=(255, 255, 0), width=1)
            else:
                for q, col in ((ob["q"], (255, 0, 255)), (ob["p"], (0, 255, 255))):
                    d.ellipse([q[0] - 5, q[1] - 5, q[0] + 5, q[1] + 5], outline=col, width=2)
        tiles.append(im.resize((im.size[0] // 2, im.size[1] // 2), Image.LANCZOS))
    W = Image.new("RGB", (sum(t_.size[0] for t_ in tiles), max(t_.size[1] for t_ in tiles)), "white")
    x = 0
    for t_ in tiles:
        W.paste(t_, (x, 0))
        x += t_.size[0]
    W.save(sys.argv[2])
