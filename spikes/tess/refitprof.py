"""refitprof.py <model> [view index=2] [save 0|1]: refit a PROFILE camera on its clicked points with the turn held near a
true profile: humanfit's camera {r, t, f, yaw 90} with r a small rotation (regularised toward 0: the picture is a true
profile by its brief), t and f free; the face's landmarks of the model as the 3D points. The 8-point fit had wandered
to a 60 deg view (an az 150 tie). Prints the residual per point and the camera's view direction; save=1 writes it
into human_refs.json (cameras[index], the old one kept as "camera_8pt")."""
import json, sys

import numpy as np
from scipy.optimize import least_squares

from hifipushie import humanfit, store

name = sys.argv[1]
vi = int(sys.argv[2]) if len(sys.argv) > 2 else 2
save = len(sys.argv) > 3 and sys.argv[3] == "1"
f = store.HOME / name / "human_refs.json"
refs = json.loads(f.read_text())
v, cam0 = refs["views"][vi], refs["cameras"][vi]
st = humanfit.state(store.load(name)["base"])
L = st["L"]
names = [k for k in v["points"] if not k.startswith("lm")]
X = np.array([L[humanfit.point_index(k)] for k in names], float)
U = np.array([v["points"][k] for k in names], float)
F_FIX = float(__import__("os").environ.get("F", "2600"))
YAW = float(__import__("os").environ.get("YAW", "-90"))
W_REG = float(sys.argv[4]) if len(sys.argv) > 4 else 400.0  # px per radian of r


def cam_of(p):
    return {**cam0, "r": p[:3].tolist(), "t": p[3:6].tolist(), "f": F_FIX, "yaw": YAW}


def res(p):
    return np.r_[(humanfit.project(cam_of(p), X) - U).ravel(), W_REG * p[:3]]


p0 = np.r_[0.0, 0.0, 0.0, cam0["t"], cam0["f"]]
sol = least_squares(res, p0)
cam = cam_of(sol.x)
R = humanfit._cam_rot(cam)
fwd = R.T @ [0, 0, 1]
r = humanfit.project(cam, X) - U
mm = cam["t"][2] / cam["f"] * 1000
print(f"view dir {np.round(fwd, 3)} (true profile from her left = [-1, 0, 0]); f {cam['f']:.0f}")
for k, e in zip(names, r):
    print(f"  {k:16s} {np.linalg.norm(e):5.1f} px  ({np.linalg.norm(e) * mm:4.1f} mm)")
print(f"rms {np.sqrt((r ** 2).sum(1).mean()):.1f} px; old camera's view dir {np.round(humanfit._cam_rot(cam0).T @ [0, 0, 1], 3)}")
if save:
    refs.setdefault("camera_8pt", {})[str(vi)] = cam0
    refs["cameras"][vi] = cam
    f.write_text(json.dumps(refs, indent=1))
    print("saved into", f)
