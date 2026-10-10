"""yawscan.py <model> <view> [save_yaw]: how well does the view's evidence (calibrated detector points / clicks) fit a
camera at each base yaw? For yaw in a range: fit r (regularised toward 0 at W_REG px a radian), t, f; print the points'
rms (sigmas). A clear minimum = the picture's yaw; flat = the picture can't tell (a loose painting). save_yaw: store
that camera as the shared one (the old kept under cameras_old_<date>)."""
import json
import sys

import numpy as np
from scipy.optimize import least_squares

import joint as J0
from hifipushie import humanfit, humanfit_map as hm, store

name, vi = sys.argv[1], int(sys.argv[2])
save = float(sys.argv[3]) if len(sys.argv) > 3 else None
f = store.HOME / name / "human_refs.json"
refs = json.loads(f.read_text())
st = humanfit.state(store.load(name)["base"])
views = hm._resolve(st, [dict(v) for v in refs["views"]])
e = J0.evidence(st, views)[vi]
cam0 = refs["cameras"][vi]
W_REG = 300.0


def fit(yaw):
    c0 = {**cam0, "yaw": yaw, "r": [0.0, 0.0, 0.0]}

    def cam_of(p):
        return {**c0, "r": p[:3].tolist(), "t": p[3:6].tolist(), "f": float(p[6])}

    def res(p):
        cam = cam_of(p)
        Rc = humanfit._cam_rot(cam)
        z = ((e["X"] - np.asarray(cam["centre"])) @ Rc.T + np.asarray(cam["t"]))[:, 2]
        w = (z / cam["f"] * 1000) / e["sig"]
        return np.r_[((humanfit.project(cam, e["X"]) - e["uv"]) * w[:, None]).ravel(), W_REG * p[:3]]
    sol = least_squares(res, np.r_[0.0, 0.0, 0.0, cam0["t"], cam0["f"]], loss="huber", f_scale=2.5)
    cam = cam_of(sol.x)
    r = res(sol.x)[:-3].reshape(-1, 2)
    return float(np.sqrt((r ** 2).sum(1).mean())), cam


R0 = humanfit._cam_rot(cam0)
print("stored camera: yaw key", cam0.get("yaw"), "r", np.round(cam0["r"], 3), "view dir", np.round(R0.T @ [0, 0, 1], 3))
for y in np.arange(20, 61, 5.0):
    rms, cam = fit(float(y))
    d = humanfit._cam_rot(cam).T @ [0, 0, 1]
    print(f"  base yaw {y:5.0f}: rms {rms:5.2f} sigmas, view dir {np.round(d, 3)}, r {np.round(cam['r'], 3)}")
if save is not None:
    rms, cam = fit(save)
    refs.setdefault("cameras_old", {})[f"{vi}_2026-10-09"] = cam0
    refs["cameras"][vi] = cam
    f.write_text(json.dumps(refs, indent=1))
    print("saved yaw", save, "rms", round(rms, 2))
