"""gdcams.py <model> <out json>: the reference cameras (front, 3/4, profile; head crops) for look2.gd, in Godot's
axes (glTF: x, z, -y)."""
import json, sys

import numpy as np

import stage
from hifipushie import store

name, out = sys.argv[1], sys.argv[2]
refs = json.loads((store.HOME / name / "human_refs.json").read_text())
B = [-192, 0, 1344, 1536]  # (the whole picture as a square)
g = lambda v: [float(v[0]), float(v[2]), float(-v[1])]  # noqa: E731
cams = []
for i, nm in enumerate(("front", "three_quarter", "profile")):
    f = stage.fitted_frame(refs["cameras"][i], [200, 150, 950, 900], nm)
    e = np.asarray(f["eye"], float)
    from hifipushie import hair
    C = hair.scalp(name).C + np.array([0.0, 0.03, -0.05])  # the head + tail, centred (Godot ignores lens shift)
    cams.append({"name": nm, "eye": g(e), "target": g(C), "up": [0, 1, 0], "fov": 22.0})
json.dump(cams, open(out, "w"), indent=1)
print(json.dumps(cams)[:400])
