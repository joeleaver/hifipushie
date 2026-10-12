"""ovl.py <model> <out png> [truth model]: the joint solve's reads drawn on the model's reference pictures
(face_ruler.overlay: green = the model's outline, yellow = outline reads, circles = point reads), full size, and the
outline reads' residual by region of the head (face set: jaw below the mouth / above). With a truth model: the TRUE
head's outline through the same cameras in red (the benchmark: where the reads should have pulled)."""
import sys
import numpy as np
from PIL import ImageDraw
from hifipushie import blockin as bi, face_ruler as fr, store
m, out = sys.argv[1], sys.argv[2]
c = fr.compare(m, rounds=1, lids=True, lips=True, parse="auto", adapt=True, cmax=3.0, prior_off=None,
               kinds=(bi._refs(m).get("blockin") or {}).get("kinds"), readers=(bi._refs(m).get("blockin") or {}).get("readers"))
im = fr.overlay(c, height=1536)
if len(sys.argv) > 3:
    ht = c["head"]["rebuild"](bi.identity(store.load(sys.argv[3])))
    d = ImageDraw.Draw(im)
    x0 = 0
    for v in c["views"]:
        _, ps = fr.clay(ht, v["cam"], passes=True)
        cm = fr._curve(ps["part"] >= 0)
        k = 1536 / v["img"].size[1]
        if cm is not None:
            d.line([(x0 + p[0] * k, p[1] * k) for p in cm], fill=(255, 0, 0), width=2)
        x0 += int(v["img"].size[0] * k)
im.save(out)
L = np.asarray(c["head"]["L"], float)
for vw in sorted({ob["view"] for ob in c["obs"] if ob["type"] == "outline"}):
    for nm, sel in (("below the mouth", lambda z: z < L[48, 2]), ("mouth to brow", lambda z: (z >= L[48, 2]) & (z < L[19, 2])), ("above", lambda z: z >= L[19, 2])):
        o = np.array([ob["o"] for ob in c["obs"] if ob["type"] == "outline" and ob["view"] == vw and sel(np.array(ob["X"][2]))])
        if len(o):
            print(f"{vw:8s} {nm:16s} n {len(o):3d}  mean {o.mean():+5.2f}  rms {np.sqrt((o ** 2).mean()):5.2f} mm")
print(out)
