"""phdiag.py <model>: faces6, WHAT THE PHOTOMETRIC TERM WANTS on its own at a model: its Jacobian over the macro basis
(fitM.basis) and the residual give the term's own Gauss-Newton step with the identity prior (z = (J'J/s^2 + B'B +
ridge)^-1 J'(-r0)/s^2 at PHOTO_SIG); printed in macro names (largest first), with the residual's rms before and
after the linear step, per view. Run with PH_INNER=1 (full oval) vs 0.8 to see what the oval's edge does."""
import json
import os
import sys

import numpy as np
from PIL import Image

import fitM
import photom
from hifipushie import humanfit, likeness, store

m = sys.argv[1]
sig = float(os.environ.get("PHOTO_SIG", "0.25"))
refs = json.loads((store.HOME / m / "human_refs.json").read_text())
st = humanfit.state(store.load(m)["base"])
mesh = likeness.model_mesh_from_state(st)
B, names = fitM.basis()
VB = photom.vertex_basis(st)
for vi in (0, 1):
    v = refs["views"][vi]
    img = Image.open(v["image"]).convert("RGB")
    pv = photom.View(v, refs["cameras"][vi], mesh, likeness.detect([img])[0])
    pv.fit_light(mesh)
    r0, J, keep = photom.jacobian([pv], mesh, VB, [B[:, j] for j in range(B.shape[1])])
    rid = np.full(B.shape[1], fitM.Z_RIDGE)
    for j, val in fitM.RIDGE_OVERRIDE.items():
        rid[j] = val
    H = J.T @ J / sig ** 2 + B.T @ B + np.diag(rid)
    z = np.linalg.solve(H, -J.T @ r0 / sig ** 2)
    after = r0 + J @ z
    top = sorted(zip(names, z), key=lambda t: -abs(t[1]))[:12]
    print(f"view {vi} (inner {photom.INNER}): n {len(r0)}, rms {np.sqrt(np.mean(r0 ** 2)):.4f} -> {np.sqrt(np.mean(after ** 2)):.4f}; "
          f"step |c| {np.linalg.norm(B @ z):.2f}; " + json.dumps([(n, round(float(x), 2)) for n, x in top]), flush=True)
