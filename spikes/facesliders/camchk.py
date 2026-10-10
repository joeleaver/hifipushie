"""camchk.py <model>: is a view's fitted camera where the picture says? Per view: the camera's yaw (its viewing
direction about the head's up axis), the detector's head yaw on the picture, likeness.compare's yaw doubt, and the
points' rms (px) through the stored camera."""
import json
import sys

import numpy as np

from hifipushie import humanfit, likeness, store

name = sys.argv[1]
refs = json.loads((store.HOME / name / "human_refs.json").read_text())
b = store.load(name)["base"]
cmp = likeness.compare(name, b)
for i, (v, cam) in enumerate(zip(refs["views"], refs["cameras"])):
    R = humanfit._cam_rot(cam)
    fwd = R.T @ np.array([0.0, 0.0, 1.0])     # the camera's viewing direction (world)
    yaw = float(np.degrees(np.arctan2(-fwd[0], fwd[1])))
    pn = cmp["pictures"][i] if i < len(cmp["pictures"]) else {}
    print(f"view {i} (hint yaw {v.get('yaw')}): camera dir {np.round(fwd, 3).tolist()} yaw {yaw:+.1f}; picture notes "
          f"{ {k: pn[k] for k in pn if 'yaw' in k} }")
