"""gaze.py [model]: the eyes' centres, the look_at target, the gaze's down angle, the photo camera's centre."""
import sys

import numpy as np

from hifipushie import humanfit, likeness, store

name = sys.argv[1] if len(sys.argv) > 1 else "ll_garrett"
b = store.load(name)["base"]
st = humanfit.state(b)
E = np.asarray(st["head"]["eyes"])
la = np.asarray(b.get("look_at", [0, -4, 1.66]), float)
print("eye centres", E.round(4).tolist(), "look_at", la.tolist())
for e in E:
    d = la - e
    print("gaze down deg", round(float(np.degrees(np.arctan2(-d[2], np.hypot(d[0], d[1])))), 2))
cam = likeness._refs(name)["cameras"][0]
c = np.asarray(cam["centre"], float)
Rc = humanfit._cam_rot(cam)
X0 = c - Rc.T @ np.asarray(cam["t"], float)
print("camera world position", X0.round(3).tolist())
for e in E:
    d = X0 - e
    print("eye -> camera: up deg", round(float(np.degrees(np.arctan2(d[2], np.hypot(d[0], d[1])))), 2))
print("camera", {k: (np.round(np.asarray(v, float), 3).tolist() if isinstance(v, list) else v) for k, v in cam.items() if k in ("centre", "t", "f", "yaw", "pitch", "roll", "rot")})
