"""jacchk.py <model> [y0 y1]: does the profile term's linear model hold at the lips? On the model's profile view: the
silhouette rows y0..y1 (photo px), their residual r (mm, + = model outside), the identity step dz that the rows alone
ask for (least squares with a small ridge, scaled to 2 mm of predicted change), the PREDICTED change B dz, and the
ACTUAL change after rebuilding the head with c + dz and re-reading the silhouette (same camera)."""
import json
import sys

import numpy as np

import fit5
import outl
from hifipushie import humanfit, store

m = sys.argv[1]
y0, y1 = (float(sys.argv[2]), float(sys.argv[3])) if len(sys.argv) > 3 else (790.0, 830.0)
sp = store.load(m)
refs = json.loads((store.HOME / m / "human_refs.json").read_text())
vi = [i for i, v in enumerate(refs["views"]) if abs(float(v.get("yaw", 0))) > 70][0]
v, cam = refs["views"][vi], refs["cameras"][vi]
o = outl.profile_auto(v, step=3)
o = o[(o[:, 1] >= y0) & (o[:, 1] < y1)]
c = humanfit.identity(sp["base"])


def read(cc):
    st = humanfit.state(fit5.spec_with(sp, cc)["base"])
    env = fit5.silhouette_env(st, cam, o)
    px = humanfit.project(cam, env["X"])
    J, z = fit5.proj_jac(cam, env["X"])
    mm = z / cam["f"] * 1000
    r = ((px - env["p"]) * env["n"]).sum(1) * mm
    A = np.einsum("ni,nij,knj->nk", env["n"], J, env["B"]) * mm[:, None]
    return r, A, env


r0, A, env = read(c)
dz = -np.linalg.solve(A.T @ A + 1e-2 * np.eye(len(c)), A.T @ r0)
pred = A @ dz
s = 2.0 / max(np.abs(pred).max(), 1e-9)
dz *= s
pred *= s
r1, _, env1 = read(c + dz)
print("rows", y0, y1, "| |dz|", round(float(np.linalg.norm(dz)), 2))
print("r0     ", np.round(r0, 2).tolist())
print("pred dr", np.round(pred, 2).tolist())
print("actual ", np.round(r1 - r0, 2).tolist())
print("same vertices matched:", float(np.mean(env["vs"] == env1["vs"])))
