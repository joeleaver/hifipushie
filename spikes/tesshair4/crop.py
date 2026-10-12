"""crop.py <model> <out png> [views=front,frontq,left,right] [box=180,100,620,460] [src size 800]: head crops of iso tiles side by side."""
import os, sys
from PIL import Image
m, out = sys.argv[1:3]
kw = dict(a.split("=", 1) for a in sys.argv[3:])
vs = kw.get("views", "front,frontq,left,right").split(",")
box = tuple(int(v) for v in kw.get("box", "180,100,620,460").split(","))
D = os.environ.get("TOUT", "/mnt/data/hifipushie/tesshair4/out")
w, h = (box[2] - box[0]) * 2, (box[3] - box[1]) * 2
s = Image.new("RGB", (w * len(vs), h))
for i, v in enumerate(vs):
    s.paste(Image.open(f"{D}/iso_{m}_a_{v}.png").crop(box).resize((w, h), Image.LANCZOS), (w * i, 0))
s.save(out if "/" in out else f"{D}/{out}")
