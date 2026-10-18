"""mouthcrops.py out.png img ...: mouth crops at a common io scale (MediaPipe frame), side by side, 1.6 io wide."""
import sys, numpy as np
from PIL import Image
from hifipushie import likeness
out, fs = sys.argv[1], sys.argv[2:]
ims = [Image.open(f).convert("RGB") for f in fs]; L = likeness.detect(ims); tiles = []
for im, l in zip(ims, L):
    l = np.asarray(l, float)[:, :2]; io = np.linalg.norm(l[[33, 133]].mean(0) - l[[362, 263]].mean(0))
    c = l[[61, 291, 13, 14]].mean(0); h = 0.8 * io
    tiles.append(im.crop((int(c[0] - h), int(c[1] - 0.55 * h), int(c[0] + h), int(c[1] + 0.55 * h))).resize((400, 275)))
S = Image.new("RGB", (400 * len(tiles), 275))
for i, t in enumerate(tiles): S.paste(t, (400 * i, 0))
S.save(out)
