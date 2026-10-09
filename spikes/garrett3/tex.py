"""tex.py <model> [views e.g. 0 or 0,1] [posed=0]: the reference textures of a model (likeness_texture.make; nothing
saved in the spec), written to $D3/out/tex_<model>_<view>.png with a preview on grey ($D3/out/tex_<model>_preview.png:
colour | alpha | colour over grey, per view)."""
import copy
import os
import sys

import numpy as np
from PIL import Image

import stage
from hifipushie import likeness_texture as lt, store

D3 = os.environ.get("D3")
name = sys.argv[1]
views = [int(x) for x in sys.argv[2].split(",")] if len(sys.argv) > 2 else None
posed = len(sys.argv) > 3 and sys.argv[3] == "1"
sp = store.load(name)
b = copy.deepcopy(sp["base"])
if posed:
    b["head"]["pose"] = dict(stage.POSE)
r = lt.make(name, base=b, views=views, out_dir=f"{D3}/out", spec=sp)
print(r["text"])
tiles = []
for k, ly in r["layers"].items():
    im = np.asarray(Image.open(ly["image"]["file"]).convert("RGBA"), float)
    a = im[..., 3:] / 255
    grey = np.full_like(im[..., :3], 128.0)
    row = np.concatenate([im[..., :3], np.repeat(a * 255, 3, 2), im[..., :3] * a + grey * (1 - a)], 1)
    tiles.append(Image.fromarray(row.astype(np.uint8)).resize((3 * 512, 512), Image.LANCZOS))
S = Image.new("RGB", (3 * 512, 512 * len(tiles)))
for i, t in enumerate(tiles):
    S.paste(t, (0, 512 * i))
S.save(f"{D3}/out/tex_{name}_preview.png")
print("wrote", f"{D3}/out/tex_{name}_preview.png")
