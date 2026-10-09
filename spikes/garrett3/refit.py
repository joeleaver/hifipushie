"""refit.py <dst> [pose json | "hand"] [shape json]: Garrett's head again from the fresh head (lk_garrett v1), as
rs2_m3 / n3 were made (garrett4.main), with the picture's EXPRESSION taken from a file instead of set by hand:
the MAP is fitted with that pose on (so the squint / frown / set mouth do not go into the identity), the saved head
is the identity without it; <dst>/pose.json keeps the pose for the matched renders. Then the kept structure: neck
macro to the mean, held macros chin_projection +1.2 / jaw_angle +2, planes 2.3, lean 6 / 2.5, cleft with lobes, nose
tip up 5 / round 0.5 (a shape json patches / adds to base.head.shape: null deletes a key).
Prints the evidence residual per step and the macros read back."""
import copy
import json
import os
import sys

import garrett
import garrett3
import garrett4
import structure
from hifipushie import humanfit, humanfit_map, humanmacro as hm, store

D3 = os.environ.get("D3")
SHAPE = {"planes": 2.3, "lean": {"under_jaw": 0.006, "jowl": 0.0025},
         "chin": {"cleft": 0.004, "cleft_width": 0.005, "cleft_lobes": 0.003, "cleft_length": 0.018},
         "nose_tip": {"up": 5, "round": 0.5}}
MACROS = {"chin_projection": 1.2, "jaw_angle": 2.0}


def load_pose(arg):
    if arg in (None, "hand"):
        return dict(garrett3.POSE)
    p = json.load(open(arg))
    out = {}
    for k, v in p.items():
        mm, sd = (v if isinstance(v, (list, tuple)) else (v, 0.0))
        if abs(mm) > max(0.5 * sd, 0.2):            # what the scores can tell from zero
            out[k] = round(float(mm) / 1000.0, 5)
    return out


def main(dst, pose_arg=None, shape_arg=None, scale=1.25, read_extra=None):
    pose = load_pose(pose_arg)
    print("pose the fit is made with (m):", pose)
    meas = garrett4.measure()
    read = {**meas, **garrett3.SHAPE_READ, "eye_depth": meas["eye_depth"], **(read_extra or {})}
    sp = garrett.hist("lk_garrett", 1)
    vs = garrett.refs()
    b0 = copy.deepcopy(sp["base"])
    b0["head"]["expression"] = {k: 0.5 * float(v) for k, v in (b0["head"].get("expression") or {}).items()}
    b0["head"]["eyes"] = 1.0
    b0["head"]["pose"] = dict(pose)
    b, rep = humanfit_map.fit(b0, vs, read=read, read_sd=0.5)
    if rep.get("refused"):
        print("REFUSED:", rep["refused"][:200])
        b, rep = humanfit_map.fit(b0, vs, read=read, read_sd=0.5, force=True)
    print("fit with the pose:", [(v["rms_mm"], v["lens_mm"]) for v in rep["views"]], rep["plausibility"])
    print("read asked -> got:", {k: (v["asked"], v["got"]) for k, v in rep["read"].items()})
    b["head"]["identity"] = {k: float(v) * scale for k, v in b["head"]["identity"].items()}
    cams = rep["cameras"]
    b["head"].pop("pose", None)
    b = garrett4.neck_to(b, garrett4.NECK_CM)
    b = humanfit._with_identity(b, hm.apply(humanfit.identity(b), MACROS, held=True))
    shape = copy.deepcopy(SHAPE)
    if shape_arg:
        for k, v in json.load(open(shape_arg)).items():
            if v is None:
                shape.pop(k, None)
            else:
                shape[k] = v
    b["head"]["shape"] = shape
    store.save(dst, {**copy.deepcopy(sp), "base": b}, f"garrett3 refit: pose {pose}, MAP + measured widths + shape words, structure")
    (store.HOME / dst / "human_refs.json").write_text(json.dumps({"views": vs, "cameras": cams}, indent=1))
    (store.HOME / dst / "pose.json").write_text(json.dumps(pose, indent=1))
    structure.info(dst, b)
    z = hm.read(humanfit.identity(b))
    print("macros (sigma):", {k: round(float(v), 2) for k, v in z.items() if abs(v) > 0.8})


if __name__ == "__main__":
    a = sys.argv[1:]
    main(a[0], a[1] if len(a) > 1 else None, a[2] if len(a) > 2 else None)
