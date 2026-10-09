"""glbview.py <model> <glb> <out.png> [poses json]: the exported GLB as an engine gets it (asset.preview: Blender's
glTF importer, Cycles, the maps) from the head's six views under the look-dev light ($D3/light.json), one sheet.
With poses ('[{"jawOpen": 1}, ...]'): one sheet per pose, <out>_p<i>.png."""
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
nt = J["lm_nose_tip"]
c = np.array([0.0, nt[1] + 0.085, nt[2] + 0.03])
D = {"front": [0, -1, 0.0], "three_quarter": [-0.66, -0.75, 0.05], "profile_right": [-1, 0.0, 0.0],
     "profile_left": [1, 0.0, 0.0], "three_quarter_other": [0.66, -0.75, 0.05], "low_angle": [-0.2, -0.86, -0.47]}
cams = []
for n, d in D.items():
    d = np.asarray(d, float)
    d /= np.linalg.norm(d)
    cams.append({"eye": (c + d * 1.25).tolist(), "target": (c - [0, 0, 0.02]).tolist(), "fov": 19.0, "name": n})
lt = {k: v for k, v in shot.light().items()}
r = asset.preview(Path(glb), [], size=640, samples=48, cameras=cams, lighting=lt, poses=poses)
if poses is None:
    r.save(out)
else:
    for i, im in enumerate(r):
        im.save(out.replace(".png", f"_p{i}.png"))
print("wrote", out)
