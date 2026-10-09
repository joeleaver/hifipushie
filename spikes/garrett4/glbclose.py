"""glbclose.py <model> <glb> <out.png> [poses json]: close-ups of the exported GLB's mouth and eyes (asset.preview,
no denoiser), front and three-quarter, 640 px each; with poses one sheet per pose (<out>_p<i>.png)."""
import json
import sys
from pathlib import Path

import numpy as np

import shot
import skin_look_j
from hifipushie import asset, store

name, glb, out = sys.argv[1:4]
poses = json.loads(sys.argv[4]) if len(sys.argv) > 4 else None
J = skin_look_j.J(store.load(name))
cams = []
for tag, j, dz in (("mouth", "lm_lip_seam", 0.0), ("eyes", "lm_nose_bridge", 0.0)):
    p = np.asarray(J[j], float) + [0, 0, dz]
    for vn, d in (("front", [0, -1, 0.0]), ("three_quarter", [-0.6, -0.8, 0.0])):
        d = np.asarray(d, float) / np.linalg.norm(d)
        cams.append({"eye": (p + d * 0.6).tolist(), "target": p.tolist(), "fov": 13.0, "name": f"{tag}_{vn}"})
r = asset.preview(Path(glb), [], size=640, samples=64, cameras=cams, lighting=shot.light(), poses=poses, denoise=False)
if poses is None:
    r.save(out)
else:
    for i, im in enumerate(r):
        im.save(out.replace(".png", f"_p{i}.png"))
print("wrote", out)
