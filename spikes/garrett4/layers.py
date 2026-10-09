"""layers.py <model> <out.jpg> <layer> [layer ...]: each skin layer's MASK through the front reference's camera
(stage.shoot(layer=)), side by side, 512 px: where a layer really lies."""
import os
import sys

from PIL import Image

import sheet1
import stage

name, out, layers = sys.argv[1], sys.argv[2], sys.argv[3:]
vs, cams = sheet1.cameras(name)
fr = stage.fitted_frame(cams[0], sheet1.crop_of(vs[0]), "front")
frames = [fr] + [f for f in stage.view_frames(__import__("hifipushie").store.load(name)) if f["name"] == "three_quarter"]
S = Image.new("RGB", (512 * len(layers), 512 * len(frames)))
for i, l in enumerate(layers):
    ims = stage.shoot(name, frames, None, size=512, hair_on=False, layer=l)
    for j, f in enumerate(frames):
        S.paste(ims[f["name"]], (512 * i, 512 * j))
S.save(out, quality=88)
print("wrote", out)
