"""flatchk.py <model>: is the stage's unlit render the albedo? The flat render's colour on the forehead / bust against
the skin's tone colour (skin.tone_rgb) and the part's base colour."""
import sys

import numpy as np
from PIL import Image

import sheet1
import stage
from hifipushie import likeness as lk, likeness_texture as lt, skin, store

name = sys.argv[1]
sp = store.load(name)
sn = stage.ensure(name, with_hair=False)
vs, cams = sheet1.cameras(name)
mesh = lk.model_mesh(sp["base"])
L = np.asarray(mesh["L"], float)
centre = L[:68].mean(0)
io = float(np.linalg.norm(L[36:42].mean(0) - L[42:48].mean(0)))
cam = lt.ortho_camera(cams[0], centre, 2.1 * io, 2000)
rgb, ok = lt.scene_albedo(sn)(cam)
n = rgb.shape[0]
Image.fromarray(rgb).save("/mnt/data/hifipushie/garrett4/out/flat_ours.png")
print("tone", [round(c, 3) for c in skin.tone_rgb(skin.params(sp)["tone"])])
for tag, (y, x) in {"forehead": (0.2, 0.5), "bust/neck": (0.95, 0.5), "cheek": (0.5, 0.3)}.items():
    p = rgb[int(y * n) - 10:int(y * n) + 10, int(x * n) - 10:int(x * n) + 10].reshape(-1, 3)
    print(tag, (np.median(p, 0) / 255).round(3), "ok", ok[int(y * n), int(x * n)])
