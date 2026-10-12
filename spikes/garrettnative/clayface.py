"""clayface.py <model> ..: the whole face in clay (reference | clay under the picture's light | overlay | raking),
front view, one file $G/out/<model>/clay/face_v0.png (blockin.focus with a "face" feature; under resources.heavy)."""
import os
import sys

from PIL import Image

from hifipushie import base, headfit, humanfit, onemesh, resources  # noqa: F401
from hifipushie import blockin as bi

bi.FEATURES.setdefault("face", {"lm": list(range(0, 68)), "pairs": [(8, 152), (27, 168)], "lines": [], "stages": (), "squint_mm": 6.0, "pad": 1.25})
G = "/mnt/data/hifipushie/garrettnative/out"
T = 640
for m in sys.argv[1:]:
    os.makedirs(f"{G}/{m}/clay", exist_ok=True)
    tmp = f"{G}/{m}/clay/_face.png"
    with resources.heavy(f"garrettnative clay face {m}", gb=6):
        bi.focus(m, "face", tmp, views=[0], T=T)
    im = Image.open(tmp)
    W = Image.new("RGB", (T * 4, T), "white")
    for k, c in enumerate((0, 1, 2, 4)):
        W.paste(im.crop((c * T, 18, (c + 1) * T, 18 + T)), (k * T, 0))
    W.save(f"{G}/{m}/clay/face_v0.png")
    os.remove(tmp)
    print(f"{G}/{m}/clay/face_v0.png")
