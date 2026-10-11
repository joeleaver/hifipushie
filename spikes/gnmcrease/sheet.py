"""sheet.py <out png> <spec>...: clay lid crops (lidgnm: raw GNM head, 0.079 mm/px, both eyes) of sampled identities,
annotated with the read lines. spec = <npz>:<i>[:label] (a sample) | npy:<path>[:label] (a 170 identity)."""
import os
import sys
EYE = os.environ.get("EYE") == "1"

import numpy as np
from PIL import Image, ImageDraw

import gk
import lidgnm
import perc

out = sys.argv[1]
ims = []
for sp in sys.argv[2:]:
    parts = sp.split(":")
    if parts[0] == "npy":
        c = np.load(parts[1])
        lab = parts[2] if len(parts) > 2 else parts[1]
    else:
        if not parts[0].endswith(".npz"):
            parts[0] = f"/mnt/data/hifipushie/gnmcrease/out/s_{parts[0]}.npz"
        z = np.load(parts[0], allow_pickle=True)
        c = z["C"][int(parts[1])]
        lab = parts[2] if len(parts) > 2 else f"{parts[0].split('/')[-1][:-4]}#{parts[1]}"
    g, _, _ = gk.geo(c)
    k, im, P, r = gk.clay(c)
    s = lidgnm.summary(r)
    a = lidgnm.annotate(im, P, r, "")
    d = ImageDraw.Draw(a)
    txt = (f"{lab}  clay dark {k['dark']:.2f} @{k['tps']:.1f}mm w {k['width']:.1f} | geo: depth {g['local']:.2f} narrow "
           f"{g['x_narrow']:.2f} hidden {g['x_hidden']:.2f} krad {g['x_krad']:.1f} @{g['hsoft']:.1f}mm")
    d.rectangle([0, 0, 1400, 34], fill=(255, 255, 255))
    d.text((8, 4), txt, fill=(0, 0, 0), font_size=24) if hasattr(d, "text") else None
    if EYE:
        a = a.crop((720, 60, 1360, 460))
        ImageDraw.Draw(a).text((6, 4), txt.split("|")[0] + "\n" + txt.split("|")[1], fill=(0, 0, 0), font_size=18)
    ims.append(a)
ncol = int(os.environ.get("NCOL", "2" if not EYE else "4"))
sc = 0.5 if not EYE else 0.75
w, h = int(ims[0].width * sc), int(ims[0].height * sc)
nrow = (len(ims) + ncol - 1) // ncol
S = Image.new("RGB", (w * ncol, h * nrow), (255, 255, 255))
for i, im in enumerate(ims):
    S.paste(im.resize((w, h), Image.LANCZOS), ((i % ncol) * w, (i // ncol) * h))
S.save(out)
print("wrote", out)
