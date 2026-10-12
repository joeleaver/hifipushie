"""cc.py <model> [tag=c]: crops of the close-up tiles (cu.sh) at full pixels: $TOUT/_f.png (front hairline),
_q.png (three-quarter temple), _l.png (profile temple)."""
import os
import sys

from PIL import Image

m = sys.argv[1]
t = sys.argv[2] if len(sys.argv) > 2 else "c"
D = os.environ.get("TOUT", "/mnt/data/hifipushie/tesshair5/out")
for v, box, o in (("front", (130, 120, 830, 560), "_f"), ("frontq", (130, 120, 830, 720), "_q"), ("left", (130, 150, 830, 750), "_l")):
    f = f"{D}/iso_{m}_{t}_{v}.png"
    if os.path.exists(f):
        Image.open(f).crop(box).save(f"{D}/{o}.png")
